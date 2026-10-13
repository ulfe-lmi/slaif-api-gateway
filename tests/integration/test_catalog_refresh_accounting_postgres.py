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

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.accounting import ActualUsage
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
    FX_NEW,
    FX_NEW_EUR,
    FX_OLD_EUR,
    MODEL,
    OR_INPUT,
    OR_INPUT_B,
    OR_OUTPUT,
    PROVIDER,
    UPSTREAM,
    _apply,
    _baseline_block_from_doc,
    _cleanup,
    _export_baseline,
    _phase,
    _refresh_bundle_bytes,
    _review,
    _review_usd_refresh_run,
    _run_dir_for,
    _seed_catalog,
    _seed_catalog_usd,
    _seal_key_bytes,
    _usd_bundle_bytes,
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

# ---------------------------------------------------------------------------
# Objective 182-b B2: default-isolation admission capture and historical
# accounting over the both-provider USD catalog (native USD prices plus the
# derived USD->EUR FX). The ACTUAL reviewed apply supersedes BOTH the price
# row and the FX row; admissions observe complete old or complete new fact
# pairs, one paired SQL capture, and historical costs/IDs through
# reservation -> refresh -> finalization/recovery.
# ---------------------------------------------------------------------------

B2_OLD_INPUT, B2_OLD_OUTPUT = Decimal(OR_INPUT), Decimal(OR_OUTPUT)
B2_NEW_INPUT = Decimal(OR_INPUT_B)
B2_OLD_FX, B2_NEW_FX = FX_OLD_EUR, FX_NEW_EUR
B2_NATIVE_50_25 = (
    B2_OLD_INPUT * Decimal(50) + B2_OLD_OUTPUT * Decimal(25)
) / Decimal(10**6)  # 0.0000405 USD
B2_EUR_50_25 = Decimal("0.0000375")  # 0.0000405 * 0.925925926 at 9-decimal storage


def _usd_pair(capture: Any) -> tuple[str, Decimal, Decimal, str, str, Decimal]:
    """The complete admission fact tuple: price AND FX row IDs with values."""
    assert capture.fx is not None
    return (
        str(capture.pricing.pricing_rule_id),
        capture.pricing.input_price_per_1m,
        capture.pricing.output_price_per_1m,
        capture.pricing.currency,
        str(capture.fx.fx_rate_id),
        capture.fx.rate,
    )


def test_default_isolation_paired_capture_price_and_fx_across_actual_apply(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A default READ COMMITTED reader spanning the ACTUAL apply never sees a
    mixed price/FX pair: the deterministic capture while the apply holds the
    catalog locks (uncommitted) is the complete OLD pair, the post-commit
    capture is the complete NEW pair, and explicit at-boundary captures
    resolve the old/new history exactly."""
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(tmp_path, url, "itg-b2-pair", OR_INPUT_B, FX_NEW)
    key = _seal_key_bytes(tmp_path)
    async def _old_pair(e) -> Any:
        return _usd_pair(await _capture(e))

    old_pair = _phase(url, _old_pair)
    assert old_pair[1:4] == (B2_OLD_INPUT, B2_OLD_OUTPUT, "USD")
    assert old_pair[5] == B2_OLD_FX

    async def _span(engine) -> dict[str, Any]:
        lock_held = asyncio.Event()
        real_lock = apply_mod.lock_catalog_tables

        async def _signal_locks(connection: Any) -> None:
            await real_lock(connection)
            lock_held.set()

        monkeypatch.setattr(apply_mod, "lock_catalog_tables", _signal_locks)

        async def _writer() -> Any:
            return await apply_mod.apply_reviewed_run(
                run_dir=run_dir,
                seal_key=key,
                database_url=url,
                reason="itg: b2 default-isolation span",
                actor="ops@itg",
            )

        async with engine.connect() as conn:
            isolation = (
                await conn.execute(text("SELECT current_setting('transaction_isolation')"))
            ).scalar_one()
        before = await _capture(engine)
        writer_task = asyncio.create_task(_writer())
        await lock_held.wait()
        mid = await _capture(engine)
        apply_result = await writer_task
        after = await _capture(engine)
        return {
            "isolation": isolation,
            "before": before,
            "mid": mid,
            "after": after,
            "apply": apply_result,
        }

    out = _phase(url, _span)
    assert out["isolation"] == "read committed"
    assert isinstance(out["apply"], apply_mod.ApplyResult), out["apply"]
    assert out["apply"].status == "committed"
    old, mid, new = (
        _usd_pair(out["before"]),
        _usd_pair(out["mid"]),
        _usd_pair(out["after"]),
    )
    # every capture is a complete old-or-new fact tuple, never a mix
    assert old == old_pair
    assert mid == old_pair  # writer holds the catalog locks but has not committed
    assert new != old
    assert new[1:4] == (B2_NEW_INPUT, B2_OLD_OUTPUT, "USD")
    assert new[5] == B2_NEW_FX
    assert new[0] != old[0] and new[4] != old[4]  # price AND FX rows superseded

    t = datetime.fromisoformat(out["apply"].effective_at)

    def _at_phase(at: datetime) -> Any:
        async def _cap(e) -> Any:
            return _usd_pair(await _capture(e, at=at))

        return _phase(url, _cap)

    before_t = _at_phase(t - timedelta(seconds=1))
    after_t = _at_phase(t + timedelta(seconds=1))
    assert before_t == old_pair
    assert after_t == new
    _phase(url, _cleanup)


def test_one_paired_sql_capture_and_zero_extra_price_fx_sql(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    """The admission capture is ONE statement joining pricing_rules and
    fx_rates, and the service estimate built from the supplied capture
    issues ZERO additional price/FX statements."""
    url = migrated_postgres_url
    _review_usd_refresh_run(tmp_path, url, "itg-b2-sql", OR_INPUT_B, FX_NEW)

    async def _proof(engine) -> dict[str, Any]:
        seen: list[str] = []

        def _record(
            conn: Any, cursor: Any, statement: str,
            parameters: Any, context: Any, executemany: Any,
        ) -> None:
            seen.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _record)
        try:
            capture = await _capture(engine)
            capture_statements = list(seen)
            seen.clear()
            session = _factory(engine)()
            try:
                estimate = await _pricing_service(session).estimate_chat_completion_cost(
                    route=_route(),
                    policy=_policy(),
                    endpoint=ENDPOINT,
                    pricing=capture.pricing,
                    fx=capture.fx,
                )
            finally:
                await session.close()
            return {
                "capture_statements": capture_statements,
                "estimate_statements": list(seen),
                "capture_price_id": str(capture.pricing.pricing_rule_id),
                "capture_fx_id": str(capture.fx.fx_rate_id),
                "estimate": estimate,
            }
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _record)

    out = _phase(url, _proof)
    capture_statements = out["capture_statements"]
    assert len(capture_statements) == 1
    statement = capture_statements[0].lower()
    assert "pricing_rules" in statement
    assert "fx_rates" in statement
    assert out["estimate_statements"] == []
    est = out["estimate"]
    assert str(est.pricing_rule_id) == out["capture_price_id"]
    assert str(est.fx_rate_id) == out["capture_fx_id"]
    assert est.native_currency == "USD"
    assert est.fx_rate == B2_OLD_FX
    assert est.estimated_total_cost_native == Decimal("0.000135")
    _phase(url, _cleanup)


def test_retained_capture_estimate_survives_refresh_to_finalization(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    """The REAL service-built admission estimate (capture row IDs included)
    is RETAINED through reservation -> refresh -> finalization: the ledger
    bills the old native/EUR facts with old pricing/FX provenance while a
    fresh admission after the refresh carries the new facts."""
    url = migrated_postgres_url
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog_usd(e))

    async def _admit(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            key_row = await _create_gateway_key(session)
            service = _pricing_service(session)
            capture = await service.capture_pricing_and_fx(
                provider=PROVIDER, model=UPSTREAM, endpoint=ENDPOINT
            )
            estimate = await service.estimate_chat_completion_cost(
                route=_route(),
                policy=_policy(),
                endpoint=ENDPOINT,
                pricing=capture.pricing,
                fx=capture.fx,
            )
            request_id = f"req-b2-retain-{uuid.uuid4().hex}"
            reservation = await _reserve(session, key_row, estimate, request_id)
            await session.commit()
            return {
                "key_id": str(key_row.id),
                "request_id": request_id,
                "reservation_id": str(reservation.reservation_id),
                "estimate": estimate,
                "price_id": str(capture.pricing.pricing_rule_id),
                "fx_id": str(capture.fx.fx_rate_id),
            }

    admitted = _phase(url, _admit)
    estimate: ChatCostEstimate = admitted["estimate"]
    assert estimate.estimated_total_cost_native == Decimal("0.000135")
    assert estimate.pricing_rule_id == uuid.UUID(admitted["price_id"])
    assert estimate.fx_rate_id == uuid.UUID(admitted["fx_id"])

    # the ACTUAL reviewed apply supersedes the USD price AND the FX row
    baseline_doc = _export_baseline(tmp_path, url, "baseline-b2-retain.json")
    bundle = _usd_bundle_bytes(
        run_id="itg-b2-retain",
        baseline_block=_baseline_block_from_doc(baseline_doc),
        or_input=OR_INPUT_B,
        fx_rate=FX_NEW,
        now=datetime.now(UTC),
    )
    path = tmp_path / "itg-b2-retain.bundle.json"
    path.write_bytes(bundle)
    reviewed = _review(
        [str(path), "--baseline-file", str(tmp_path / "baseline-b2-retain.json")],
        tmp_path,
    )
    assert reviewed.exit_code == 0, reviewed.output
    run_dir = _run_dir_for("itg-b2-retain", tmp_path)
    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 0, applied.output

    async def _fresh_admission(engine) -> dict[str, Any]:
        capture = await _capture(engine)
        session = _factory(engine)()
        try:
            fresh_estimate = await _pricing_service(session).estimate_chat_completion_cost(
                route=_route(),
                policy=_policy(),
                endpoint=ENDPOINT,
                pricing=capture.pricing,
                fx=capture.fx,
            )
        finally:
            await session.close()
        return {
            "price_id": str(capture.pricing.pricing_rule_id),
            "fx_id": str(capture.fx.fx_rate_id),
            "input": capture.pricing.input_price_per_1m,
            "fx_rate": capture.fx.rate,
            "estimate_price_id": str(fresh_estimate.pricing_rule_id),
            "estimate_fx_id": str(fresh_estimate.fx_rate_id),
        }

    fresh = _phase(url, _fresh_admission)
    assert fresh["price_id"] != admitted["price_id"]
    assert fresh["fx_id"] != admitted["fx_id"]
    assert fresh["input"] == B2_NEW_INPUT
    assert fresh["fx_rate"] == B2_NEW_FX
    assert fresh["estimate_price_id"] == fresh["price_id"]
    assert fresh["estimate_fx_id"] == fresh["fx_id"]

    async def _finalize(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            key_row = await GatewayKeysRepository(session).get_gateway_key_by_id(
                uuid.UUID(admitted["key_id"])
            )
            result = await AccountingService(session).finalize_successful_response(
                uuid.UUID(admitted["reservation_id"]),
                _authenticated_key(key_row),
                _route(),
                _policy(),
                estimate,
                _provider_response(),
                request_id=admitted["request_id"],
            )
            ledger = await UsageLedgerRepository(session).get_usage_record_by_request_id(
                admitted["request_id"]
            )
            await session.refresh(key_row)
            return {
                "status": result.accounting_status,
                "actual_native": ledger.actual_cost_native,
                "actual_eur": ledger.actual_cost_eur,
                "currency": ledger.native_currency,
                "meta_price_id": ledger.response_metadata.get("pricing_rule_id"),
                "meta_fx_id": ledger.response_metadata.get("fx_rate_id"),
                "key_used": key_row.cost_used_eur,
            }

    out = _phase(url, _finalize)
    assert out["status"] == "finalized"
    assert out["actual_native"] == B2_NATIVE_50_25
    assert out["actual_eur"] == B2_EUR_50_25
    assert out["currency"] == "USD"
    # historical provenance: the OLD capture's row IDs, not the refreshed rows
    assert out["meta_price_id"] == admitted["price_id"]
    assert out["meta_fx_id"] == admitted["fx_id"]
    assert out["key_used"] == B2_EUR_50_25
    _phase(url, _cleanup)


def test_provider_completed_recovery_after_refresh_uses_real_old_capture_facts(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    """Provider-completed recovery after the ACTUAL refresh repairs from the
    REAL capture-derived persisted facts (old price/FX IDs, old costs) and
    issues ZERO pricing_rules/fx_rates statements -- history is never
    re-priced from the refreshed catalog."""
    url = migrated_postgres_url
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog_usd(e))

    async def _admit_and_fail_finalization(engine) -> dict[str, Any]:
        factory = _factory(engine)
        async with factory() as session:
            key_row = await _create_gateway_key(session)
            service = _pricing_service(session)
            capture = await service.capture_pricing_and_fx(
                provider=PROVIDER, model=UPSTREAM, endpoint=ENDPOINT
            )
            estimate = await service.estimate_chat_completion_cost(
                route=_route(),
                policy=_policy(),
                endpoint=ENDPOINT,
                pricing=capture.pricing,
                fx=capture.fx,
            )
            request_id = f"req-b2-recovery-{uuid.uuid4().hex}"
            reservation = await _reserve(session, key_row, estimate, request_id)
            # the provider completed; finalization failed after the response,
            # leaving the recovery-state ledger row with capture-derived facts
            actual = AccountingService(session).compute_actual_cost(
                _provider_response(),
                _route(),
                ActualUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75),
                estimate,
            )
            now = datetime.now(UTC)
            ledger = await UsageLedgerRepository(session).create_usage_record(
                success=None,
                accounting_status="failed",
                error_type="accounting_finalization_failed",
                error_message="accounting_finalization_failed",
                request_id=request_id,
                quota_reservation_id=reservation.reservation_id,
                gateway_key_id=key_row.id,
                endpoint=ENDPOINT,
                provider=PROVIDER,
                requested_model=MODEL,
                resolved_model=UPSTREAM,
                upstream_request_id="upstream-itg-b2-recovery",
                streaming=True,
                http_status=200,
                prompt_tokens=50,
                completion_tokens=25,
                input_tokens=50,
                output_tokens=25,
                cached_tokens=0,
                reasoning_tokens=0,
                total_tokens=75,
                estimated_cost_eur=estimate.estimated_total_cost_eur,
                actual_cost_eur=actual.actual_cost_eur,
                actual_cost_native=actual.actual_cost_native,
                native_currency=actual.native_currency,
                usage_raw={"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
                response_metadata={
                    "needs_reconciliation": True,
                    "recovery_state": "provider_completed_finalization_failed",
                    "pricing_rule_id": str(estimate.pricing_rule_id),
                    "fx_rate_id": str(estimate.fx_rate_id),
                },
                started_at=now - timedelta(seconds=2),
                finished_at=now,
                latency_ms=2000,
            )
            await session.commit()
            return {
                "key_id": str(key_row.id),
                "ledger_id": str(ledger.id),
                "price_id": str(estimate.pricing_rule_id),
                "fx_id": str(estimate.fx_rate_id),
                "actual_native": actual.actual_cost_native,
            }

    admitted = _phase(url, _admit_and_fail_finalization)
    assert admitted["actual_native"] == B2_NATIVE_50_25

    # the ACTUAL reviewed apply supersedes the USD price AND the FX row
    baseline_doc = _export_baseline(tmp_path, url, "baseline-b2-recovery.json")
    bundle = _usd_bundle_bytes(
        run_id="itg-b2-recovery",
        baseline_block=_baseline_block_from_doc(baseline_doc),
        or_input=OR_INPUT_B,
        fx_rate=FX_NEW,
        now=datetime.now(UTC),
    )
    path = tmp_path / "itg-b2-recovery.bundle.json"
    path.write_bytes(bundle)
    reviewed = _review(
        [str(path), "--baseline-file", str(tmp_path / "baseline-b2-recovery.json")],
        tmp_path,
    )
    assert reviewed.exit_code == 0, reviewed.output
    run_dir = _run_dir_for("itg-b2-recovery", tmp_path)
    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 0, applied.output

    async def _recover(engine) -> dict[str, Any]:
        seen: list[str] = []

        def _record(
            conn: Any, cursor: Any, statement: str,
            parameters: Any, context: Any, executemany: Any,
        ) -> None:
            seen.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _record)
        try:
            factory = _factory(engine)
            async with factory() as session:
                service = ReservationReconciliationService(
                    gateway_keys_repository=GatewayKeysRepository(session),
                    quota_reservations_repository=QuotaReservationsRepository(session),
                    usage_ledger_repository=UsageLedgerRepository(session),
                    audit_repository=AuditRepository(session),
                )
                dry = await service.reconcile_provider_completed_recovery(
                    usage_ledger_id=uuid.UUID(admitted["ledger_id"]), dry_run=True
                )
                executed = await service.reconcile_provider_completed_recovery(
                    usage_ledger_id=uuid.UUID(admitted["ledger_id"]),
                    dry_run=False,
                    reason="itg: operator repair after refresh",
                )
                key_row = await GatewayKeysRepository(session).get_gateway_key_by_id(
                    uuid.UUID(admitted["key_id"])
                )
                await session.refresh(key_row)
                ledger = await UsageLedgerRepository(session).get_usage_record_by_id(
                    uuid.UUID(admitted["ledger_id"])
                )
                return {
                    "dry_reconciled": dry.reconciled,
                    "reconciled": executed.reconciled,
                    "recovery_sql": list(seen),
                    "key_used": key_row.cost_used_eur,
                    "ledger_status": ledger.accounting_status,
                    "actual_native": ledger.actual_cost_native,
                    "actual_eur": ledger.actual_cost_eur,
                    "currency": ledger.native_currency,
                    "meta_price_id": ledger.response_metadata.get("pricing_rule_id"),
                    "meta_fx_id": ledger.response_metadata.get("fx_rate_id"),
                }
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _record)

    out = _phase(url, _recover)
    assert out["dry_reconciled"] is False
    assert out["reconciled"] is True
    # recovery must never query the refreshed catalog to reprice history
    for statement in out["recovery_sql"]:
        lowered = statement.lower()
        assert "pricing_rules" not in lowered
        assert "fx_rates" not in lowered
    assert out["ledger_status"] == "finalized"
    assert out["actual_native"] == B2_NATIVE_50_25
    assert out["actual_eur"] == B2_EUR_50_25
    assert out["currency"] == "USD"
    assert out["meta_price_id"] == admitted["price_id"]
    assert out["meta_fx_id"] == admitted["fx_id"]
    assert out["key_used"] == B2_EUR_50_25
    _phase(url, _cleanup)
