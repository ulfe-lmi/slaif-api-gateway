"""Objective 182 AP4: coherent admission capture and finalization on real
PostgreSQL 16 (disposable owned instance via TEST_DATABASE_URL).

Proves, with committed state:

- a REPEATABLE READ reader paused across the atomic price supersession
  observes only the complete old pair (snapshot), a new transaction the
  complete new pair, and explicit ``at`` captures resolve the old row just
  before T and the new row just after T (history at the boundary);
- a reservation estimated from the OLD capture finalizes AFTER the refresh
  at the OLD capture's cost (the estimate carries the per-million prices;
  the refreshed database rows never re-price an admitted request);
- provider-completed reconciliation after the refresh repairs from the
  PERSISTED ledger facts, not from current catalog prices.

Structural note: ``accounting.compute_actual_cost`` is estimate-based
(``_ = at``, no database re-read) and reconciliation reads persisted cost
facts, so no ``accounting.py``/``reservation_reconciliation.py`` change was
necessary for AP4 (the order allows those paths only if a proof reveals
necessity).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.catalog_refresh import apply as apply_mod
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.reservation_reconciliation import (
    ReservationReconciliationService,
)

from tests.integration.test_catalog_refresh_apply_postgres import (
    ENDPOINT,
    MODEL,
    PROVIDER,
    UPSTREAM,
    _apply,
    _cleanup,
    _export_baseline,
    _phase,
    _refresh_bundle_bytes,
    _review,
    _run_dir_for,
    _seed_catalog,
    _seal_key_bytes,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL accounting tests.",
)

OLD_INPUT, OLD_OUTPUT = "0.25", "1"
NEW_INPUT = "0.26"  # the refresh moves the input price; output stays 1.0

OLD_ACTUAL_50_25 = (
    Decimal(OLD_INPUT) * Decimal(50) + Decimal(OLD_OUTPUT) * Decimal(25)
) / Decimal(10**6)  # 0.0000375
NEW_COST_WOULD_BE_50_25 = (
    Decimal(NEW_INPUT) * Decimal(50) + Decimal(OLD_OUTPUT) * Decimal(25)
) / Decimal(10**6)  # 0.0000380


def _factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _pricing_service(session: AsyncSession) -> PricingService:
    return PricingService(
        pricing_rules_repository=PricingRulesRepository(session),
        fx_rates_repository=FxRatesRepository(session),
    )


async def _capture(engine, *, at: datetime | None = None, session: AsyncSession | None = None):
    close_session = session is None
    if close_session:
        session = _factory(engine)()
    try:
        return await _pricing_service(session).capture_pricing_and_fx(
            provider=PROVIDER, model=UPSTREAM, endpoint=ENDPOINT, at=at
        )
    finally:
        if close_session:
            await session.close()


def _pair(capture: Any) -> tuple[Decimal, Decimal, str]:
    return (
        capture.pricing.input_price_per_1m,
        capture.pricing.output_price_per_1m,
        capture.pricing.currency,
    )


async def _create_gateway_key(session: AsyncSession) -> Any:
    owner = await OwnersRepository(session).create_owner(
        name="AtomicApply",
        surname="Accounting",
        email=f"atomic-apply-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1.000000000"),
        token_limit_total=10000,
        request_limit_total=10,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


def _authenticated_key(row) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=row.id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        public_key_id=row.public_key_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        allow_all_models=row.allow_all_models,
        allowed_models=tuple(row.allowed_models),
        allow_all_endpoints=row.allow_all_endpoints,
        allowed_endpoints=tuple(row.allowed_endpoints),
        allowed_providers=None,
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
        rate_limit_policy={},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=MODEL,
        resolved_model=UPSTREAM,
        provider=PROVIDER,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=MODEL,
        priority=100,
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": MODEL, "messages": [], "max_completion_tokens": 100},
        requested_output_tokens=100,
        effective_output_tokens=100,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )


def _estimate_from_capture(capture: Any) -> ChatCostEstimate:
    """The admission estimate as the gateway builds it from the capture:
    the per-million prices live in the estimate itself, so finalization
    cannot re-price from later database state."""
    pricing = capture.pricing
    fx_rate = Decimal("1") if capture.fx is None else capture.fx.rate
    input_cost = pricing.input_price_per_1m * Decimal(100) / Decimal(10**6)
    output_cost = pricing.output_price_per_1m * Decimal(100) / Decimal(10**6)
    total = input_cost + output_cost
    return ChatCostEstimate(
        provider=PROVIDER,
        requested_model=MODEL,
        resolved_model=UPSTREAM,
        native_currency=pricing.currency,
        estimated_input_tokens=100,
        estimated_output_tokens=100,
        estimated_input_cost_native=input_cost,
        estimated_output_cost_native=output_cost,
        estimated_total_cost_native=total,
        estimated_total_cost_eur=total * fx_rate,
        pricing_rule_id=pricing.pricing_rule_id,
        fx_rate_id=None if capture.fx is None else capture.fx.fx_rate_id,
        input_price_per_1m=pricing.input_price_per_1m,
        output_price_per_1m=pricing.output_price_per_1m,
        fx_rate=fx_rate,
    )


def _reserve(session: AsyncSession, gateway_key, estimate: ChatCostEstimate, request_id: str) -> Any:
    return QuotaService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
    ).reserve_for_chat_completion(
        authenticated_key=_authenticated_key(gateway_key),
        route=_route(),
        policy=_policy(),
        cost_estimate=estimate,
        request_id=request_id,
    )


def _provider_response() -> ProviderResponse:
    return ProviderResponse(
        provider=PROVIDER,
        upstream_model=UPSTREAM,
        status_code=200,
        json_body={},
        upstream_request_id="upstream-itg-182",
        usage=ProviderUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75),
    )


def _review_refresh_run(tmp_path: Path, url: str, run_id: str) -> Path:
    """Seed, export a matching baseline, review a price-changing bundle."""
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog(e))
    baseline_doc = _export_baseline(tmp_path, url, f"baseline-{run_id}.json")
    bundle = _refresh_bundle_bytes(
        run_id=run_id, baseline_doc=baseline_doc, input_price=NEW_INPUT, now=datetime.now(UTC)
    )
    path = tmp_path / f"{run_id}.bundle.json"
    path.write_bytes(bundle)
    reviewed = _review(
        [str(path), "--baseline-file", str(tmp_path / f"baseline-{run_id}.json")],
        tmp_path,
    )
    assert reviewed.exit_code == 0, reviewed.output
    return _run_dir_for(run_id, tmp_path)


def test_paired_capture_never_mixed_across_atomic_refresh(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    run_dir = _review_refresh_run(tmp_path, url, "itg-acc-pair")
    key = _seal_key_bytes(tmp_path)

    # the old pair, captured before the atomic writer
    old = _phase(url, lambda e: _capture(e))
    assert _pair(old) == (Decimal(OLD_INPUT), Decimal(OLD_OUTPUT), "EUR")

    async def _paused_reader(engine) -> dict[str, Any]:
        out: dict[str, Any] = {}
        async with engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="REPEATABLE READ")
            await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            out["before"] = await _capture(engine, session=session)
            out["apply"] = await apply_mod.apply_reviewed_run(
                run_dir=run_dir,
                seal_key=key,
                database_url=url,
                reason="itg: ap4 refresh",
                actor="ops@itg",
            )
            # the SAME reader transaction, after the writer committed:
            # its snapshot still holds the complete old pair
            out["after"] = await _capture(engine, session=session)
            await session.close()
            await conn.rollback()
        return out

    paused = _phase(url, _paused_reader)
    new = _phase(url, lambda e: _capture(e))

    assert paused["apply"].status == "committed"
    assert _pair(paused["before"]) == (Decimal(OLD_INPUT), Decimal(OLD_OUTPUT), "EUR")
    assert _pair(paused["after"]) == (Decimal(OLD_INPUT), Decimal(OLD_OUTPUT), "EUR")
    assert _pair(new) == (Decimal(NEW_INPUT), Decimal(OLD_OUTPUT), "EUR")

    # the boundary T: explicit at-captures resolve the history exactly
    t = datetime.fromisoformat(paused["apply"].effective_at)
    t26 = t.isoformat()[:26]
    before_t = _phase(url, lambda e: _capture(e, at=t - timedelta(seconds=1)))
    after_t = _phase(url, lambda e: _capture(e, at=t + timedelta(seconds=1)))
    assert _pair(before_t) == (Decimal(OLD_INPUT), Decimal(OLD_OUTPUT), "EUR")
    assert _pair(after_t) == (Decimal(NEW_INPUT), Decimal(OLD_OUTPUT), "EUR")
    assert before_t.pricing.pricing_rule_id != after_t.pricing.pricing_rule_id

    # the close-then-create history is intact in the database, at one T
    async def _history(engine) -> list[Any]:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id::text, input_price_per_1m, "
                    "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
                    "to_char(valid_until, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
                    "FROM pricing_rules ORDER BY valid_from"
                )
            )
            return list(rows.all())

    history = _phase(url, _history)
    assert len(history) == 2
    assert history[0][1] == Decimal(OLD_INPUT)
    assert history[1][1] == Decimal(NEW_INPUT)
    assert history[0][3][:26] == t26  # old row closed at T
    assert history[1][2][:26] == t26  # new row opened at the same T
    _phase(url, _cleanup)


def test_finalize_after_refresh_uses_old_capture_cost(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog(e))

    async def _setup(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            key_row = await _create_gateway_key(session)
            capture = await _pricing_service(session).capture_pricing_and_fx(
                provider=PROVIDER, model=UPSTREAM, endpoint=ENDPOINT
            )
            estimate = _estimate_from_capture(capture)
            request_id = f"req-itg-{uuid.uuid4().hex}"
            reservation = await _reserve(session, key_row, estimate, request_id)
            await session.commit()
            return {
                "key_id": str(key_row.id),
                "request_id": request_id,
                "reservation_id": str(reservation.reservation_id),
            }

    setup = _phase(url, _setup)

    # now the atomic refresh changes BOTH prices
    baseline_doc = _export_baseline(tmp_path, url, "baseline-acc-fin.json")
    bundle = _refresh_bundle_bytes(
        run_id="itg-acc-finalize",
        baseline_doc=baseline_doc,
        input_price=NEW_INPUT,
        now=datetime.now(UTC),
    )
    path = tmp_path / "itg-acc-finalize.bundle.json"
    path.write_bytes(bundle)
    reviewed = _review(
        [str(path), "--baseline-file", str(tmp_path / "baseline-acc-fin.json")], tmp_path
    )
    assert reviewed.exit_code == 0, reviewed.output
    run_dir = _run_dir_for("itg-acc-finalize", tmp_path)
    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 0, applied.output

    # the database now carries the NEW input price ...
    current = _phase(url, lambda e: _capture(e))
    assert (current.pricing.input_price_per_1m, current.pricing.output_price_per_1m) == (
        Decimal(NEW_INPUT),
        Decimal(OLD_OUTPUT),
    )

    # ... but the admission estimated on the OLD capture finalizes at the
    # OLD capture's cost: 0.25*50 + 1.0*25 per 1e6
    async def _finalize(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            key_row = await GatewayKeysRepository(session).get_gateway_key_by_id(
                uuid.UUID(setup["key_id"])
            )
            old_input, old_output = Decimal(OLD_INPUT), Decimal(OLD_OUTPUT)
            estimate = ChatCostEstimate(
                provider=PROVIDER,
                requested_model=MODEL,
                resolved_model=UPSTREAM,
                native_currency="EUR",
                estimated_input_tokens=100,
                estimated_output_tokens=100,
                estimated_input_cost_native=old_input * Decimal(100) / Decimal(10**6),
                estimated_output_cost_native=old_output * Decimal(100) / Decimal(10**6),
                estimated_total_cost_native=(old_input + old_output) * Decimal(100) / Decimal(10**6),
                estimated_total_cost_eur=(old_input + old_output) * Decimal(100) / Decimal(10**6),
                pricing_rule_id=None,
                fx_rate_id=None,
                input_price_per_1m=old_input,
                output_price_per_1m=old_output,
            )
            result = await AccountingService(session).finalize_successful_response(
                uuid.UUID(setup["reservation_id"]),
                _authenticated_key(key_row),
                _route(),
                _policy(),
                estimate,
                _provider_response(),
                request_id=setup["request_id"],
            )
            ledger = await UsageLedgerRepository(session).get_usage_record_by_request_id(
                setup["request_id"]
            )
            await session.refresh(key_row)
            return {
                "status": result.accounting_status,
                "ledger_cost": ledger.actual_cost_eur,
                "key_used": key_row.cost_used_eur,
            }

    out = _phase(url, _finalize)
    assert out["status"] == "finalized"
    assert out["ledger_cost"] == OLD_ACTUAL_50_25
    assert out["key_used"] == OLD_ACTUAL_50_25
    assert out["ledger_cost"] != NEW_COST_WOULD_BE_50_25
    _phase(url, _cleanup)


def test_provider_completed_recovery_after_refresh_uses_persisted_facts(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog(e))

    # admission on the OLD prices: reservation + ledger facts (a finalization
    # that failed after the provider completed -- the recovery state)
    reserved = (
        Decimal(OLD_INPUT) * Decimal(100) + Decimal(OLD_OUTPUT) * Decimal(100)
    ) / Decimal(10**6)

    async def _setup(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            key_row = await _create_gateway_key(session)
            request_id = f"req-provider-completed-itg-{uuid.uuid4().hex}"
            reservation = await QuotaReservationsRepository(session).create_reservation(
                gateway_key_id=key_row.id,
                request_id=request_id,
                endpoint=ENDPOINT,
                requested_model=MODEL,
                reserved_cost_eur=reserved,
                reserved_tokens=100,
                reserved_requests=1,
                status="pending",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            await GatewayKeysRepository(session).add_reserved_counters(
                key_row,
                cost_reserved_eur=reserved,
                tokens_reserved_total=100,
                requests_reserved_total=1,
            )
            now = datetime.now(UTC)
            ledger = await UsageLedgerRepository(session).create_usage_record(
                success=None,
                accounting_status="failed",
                error_type="accounting_finalization_failed",
                error_message="accounting_finalization_failed",
                request_id=request_id,
                quota_reservation_id=reservation.id,
                gateway_key_id=key_row.id,
                endpoint="chat.completions",
                provider=PROVIDER,
                requested_model=MODEL,
                resolved_model=UPSTREAM,
                upstream_request_id="upstream-itg-recovery",
                streaming=True,
                http_status=200,
                prompt_tokens=50,
                completion_tokens=25,
                input_tokens=50,
                output_tokens=25,
                cached_tokens=0,
                reasoning_tokens=0,
                total_tokens=75,
                estimated_cost_eur=reserved,
                actual_cost_eur=OLD_ACTUAL_50_25,
                actual_cost_native=OLD_ACTUAL_50_25,
                native_currency="EUR",
                usage_raw={"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
                response_metadata={
                    "needs_reconciliation": True,
                    "recovery_state": "provider_completed_finalization_failed",
                    "prompt": "sensitive prompt body",
                    "completion": "sensitive completion body",
                },
                started_at=now - timedelta(seconds=2),
                finished_at=now,
                latency_ms=2000,
            )
            await session.commit()
            return {
                "key_id": str(key_row.id),
                "ledger_id": str(ledger.id),
            }

    setup = _phase(url, _setup)

    # the atomic refresh moves the input price while the completion is pending
    baseline_doc = _export_baseline(tmp_path, url, "baseline-acc-rec.json")
    bundle = _refresh_bundle_bytes(
        run_id="itg-acc-recovery",
        baseline_doc=baseline_doc,
        input_price=NEW_INPUT,
        now=datetime.now(UTC),
    )
    path = tmp_path / "itg-acc-recovery.bundle.json"
    path.write_bytes(bundle)
    reviewed = _review(
        [str(path), "--baseline-file", str(tmp_path / "baseline-acc-rec.json")], tmp_path
    )
    assert reviewed.exit_code == 0, reviewed.output
    run_dir = _run_dir_for("itg-acc-recovery", tmp_path)
    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 0, applied.output

    async def _recover(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            service = ReservationReconciliationService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            dry = await service.reconcile_provider_completed_recovery(
                usage_ledger_id=uuid.UUID(setup["ledger_id"]), dry_run=True
            )
            executed = await service.reconcile_provider_completed_recovery(
                usage_ledger_id=uuid.UUID(setup["ledger_id"]),
                dry_run=False,
                reason="itg: operator repair after refresh",
            )
            key_row = await GatewayKeysRepository(session).get_gateway_key_by_id(
                uuid.UUID(setup["key_id"])
            )
            await session.refresh(key_row)
            ledger = await UsageLedgerRepository(session).get_usage_record_by_id(
                uuid.UUID(setup["ledger_id"])
            )
            return {
                "dry_reconciled": dry.reconciled,
                "reconciled": executed.reconciled,
                "key_used": key_row.cost_used_eur,
                "ledger_status": ledger.accounting_status,
                "ledger_cost": ledger.actual_cost_eur,
            }

    out = _phase(url, _recover)
    assert out["dry_reconciled"] is False
    assert out["reconciled"] is True
    assert out["ledger_status"] == "finalized"
    # the persisted capture cost -- NOT the post-refresh price
    assert out["ledger_cost"] == OLD_ACTUAL_50_25
    assert out["key_used"] == OLD_ACTUAL_50_25
    assert out["key_used"] != NEW_COST_WOULD_BE_50_25
    _phase(url, _cleanup)
