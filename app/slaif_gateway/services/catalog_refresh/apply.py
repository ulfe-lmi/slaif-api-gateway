"""Bounded atomic apply orchestrator for reviewed catalog-refresh runs (182).

Trust and safety contract (order 182, A1-A3):

- The ONLY execution authority is one authenticated verified capture
  (``sealing.load_verified_capture``): sealed bytes, HMAC, canonical bundle,
  execution context, and the replayed report. This module never reopens or
  reparses run files after authentication; the recorded identity comes from
  the captured receipt fields, not a re-read of receipt.json.
- Lifecycle binding: when the CLI passes the run-directory handle it
  already checked, the authenticated capture is read through that held
  descriptor after a hop-by-hop boundary re-check; the service never
  re-anchors a checked path by name and never closes a caller-owned
  descriptor.
- No source HTTP, inference, research, email, provider discovery, or
  credential loading. The operator database URL is configuration only and
  never enters errors, audit rows, or the durable application record.
- ONE transaction: bounded waits -> fixed-order catalog table locks
  (SHARE ROW EXCLUSIVE, which serializes with ordinary catalog writers AND
  with other applies) -> target check -> committed-outcome lookup by
  canonical bundle identity FIRST -> stale-baseline comparison on the locked
  writer view -> all mutations -> the application record -> the audit row
  -> commit. Any failure rolls every part back together.
- Supersession is close-then-create at the ONE effective T chosen for the
  transaction, guarded on the reviewed row facts (identity, values, opening
  instant, the reviewed closing instant with exact NULL-safe equality,
  still-active-at-T). History is preserved, never re-priced in place.
- Idempotency: a retry of the same reviewed bundle returns the committed
  result instead of applying, charging, or auditing twice; the durable
  uniqueness boundary (bundle_sha256, plan_sha256) is the
  check-then-insert backstop, resolved read-only after the rollback.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from slaif_gateway.db.models import AdminUser
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.catalog_refresh import (
    CatalogRefreshApplication,
    CatalogRefreshApplicationsRepository,
    apply_transaction_prelude,
    current_database_actor,
    lock_catalog_tables,
)
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.catalog_refresh import APPLY_PLAN_SCHEMA_VERSION
from slaif_gateway.services.catalog_refresh.baseline import (
    _target_parts_from_url,
    project_catalog_rows,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.sealing import (
    VerifiedCapture,
    load_verified_capture,
)
from slaif_gateway.services.catalog_refresh.validation import (
    sql_capture_for_mode,
    validate_bundle,
)
from slaif_gateway.services.fx_rate_service import FxRateService
from slaif_gateway.services.model_route_service import ModelRouteService
from slaif_gateway.services.pricing_rule_service import PricingRuleService
from slaif_gateway.services.provider_config_service import ProviderConfigService

if TYPE_CHECKING:
    from slaif_gateway.services.catalog_refresh.filesystem import AnchoredDir

_MODES = ("bootstrap", "refresh")


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Safe outcome of one apply attempt (no database URL, no credentials)."""

    status: str  # "committed" | "already_committed"
    run_id: str
    bundle_sha256: str
    plan_sha256: str
    effective_at: str | None
    counts: dict[str, int]
    record: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ApplyStatus:
    """Read-only visibility of the committed outcome for a reviewed run."""

    run_id: str
    bundle_sha256: str
    committed: bool
    records: list[dict[str, Any]] = field(default_factory=list)


def _parse_iso(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _canon_row_map(rows: tuple[Any, ...]) -> dict[str, str]:
    """Canonical per-row identity map for one catalog table.

    ``updated_at`` is excluded: it is purely informational and changes with
    unrelated row touches, while every other projected field is part of the
    reviewed row facts the apply must not drift from.
    """
    out: dict[str, str] = {}
    for row in rows:
        payload = row.model_dump(mode="json")
        payload.pop("updated_at", None)
        out[str(row.id)] = json.dumps(payload, sort_keys=True)
    return out


def _stale_tables(live: tuple, captured: Any) -> list[str]:
    """Compare the locked live projection against the captured baseline.

    Returns the names of the tables whose projected row facts differ (empty
    list means the catalog is exactly where the review left it).
    """
    pairs = (
        ("provider_configs", live[0], captured.providers),
        ("model_routes", live[1], captured.routes),
        ("pricing_rules", live[2], captured.pricing),
        ("fx_rates", live[3], captured.fx),
    )
    drifted: list[str] = []
    for name, live_rows, captured_rows in pairs:
        if _canon_row_map(tuple(live_rows)) != _canon_row_map(tuple(captured_rows)):
            drifted.append(name)
    return drifted


def _safe_record(row: CatalogRefreshApplication) -> dict[str, Any]:
    return {
        "run_id": row.run_id,
        "bundle_sha256": row.bundle_sha256,
        "receipt_hmac_sha256": row.receipt_hmac_sha256,
        "plan_sha256": row.plan_sha256,
        "mode": row.mode,
        "operator_actor": row.operator_actor,
        "db_actor": row.db_actor,
        "admin_user_id": str(row.admin_user_id) if row.admin_user_id is not None else None,
        "reason": row.reason,
        "effective_at": row.effective_at.isoformat() if row.effective_at is not None else None,
        "applied_provider_ids": list(row.applied_provider_ids or []),
        "applied_route_ids": list(row.applied_route_ids or []),
        "applied_pricing_created_ids": list(row.applied_pricing_created_ids or []),
        "applied_pricing_superseded_old_ids": list(row.applied_pricing_superseded_old_ids or []),
        "applied_pricing_superseded_new_ids": list(row.applied_pricing_superseded_new_ids or []),
        "applied_fx_created_ids": list(row.applied_fx_created_ids or []),
        "applied_fx_superseded_old_ids": list(row.applied_fx_superseded_old_ids or []),
        "applied_fx_superseded_new_ids": list(row.applied_fx_superseded_new_ids or []),
        "created_providers": row.created_providers,
        "created_routes": row.created_routes,
        "created_pricing": row.created_pricing,
        "created_fx": row.created_fx,
        "superseded_pricing": row.superseded_pricing,
        "superseded_fx": row.superseded_fx,
        "outcome": row.outcome,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
    }


def _pricing_create_kwargs(
    dimensions: dict[str, str | None],
    *,
    currency: str,
    source_url: str | None,
    valid_from: datetime,
) -> dict[str, Any]:
    def _dec(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return {
        "input_price_per_1m": Decimal(dimensions["input"]),
        "output_price_per_1m": Decimal(dimensions["output"]),
        "cached_input_price_per_1m": _dec(dimensions.get("cached_input")),
        "reasoning_price_per_1m": _dec(dimensions.get("reasoning")),
        "request_price": _dec(dimensions.get("request")),
        "currency": currency,
        "source_url": source_url,
        "valid_from": valid_from,
        "valid_until": None,
        "enabled": True,
    }


async def _lookup_committed(
    engine: AsyncEngine, *, bundle_sha256: str, plan_sha256: str
) -> CatalogRefreshApplication | None:
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            session = AsyncSession(bind=connection)
            repo = CatalogRefreshApplicationsRepository(session)
            return await repo.find_by_identity(
                bundle_sha256=bundle_sha256, plan_sha256=plan_sha256
            )


async def _lookup_committed_by_bundle(
    engine: AsyncEngine, *, bundle_sha256: str
) -> list[CatalogRefreshApplication]:
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            session = AsyncSession(bind=connection)
            repo = CatalogRefreshApplicationsRepository(session)
            return await repo.find_committed_by_bundle(bundle_sha256=bundle_sha256)


async def _execute_transaction(
    capture: VerifiedCapture,
    *,
    operations: list[dict[str, Any]],
    plan_sha256: str,
    bundle_sha256: str,
    database_url: str,
    reason: str,
    actor: str,
    admin_id: uuid.UUID | None,
    ack_warnings: tuple[str, ...] = (),
) -> ApplyResult:
    server_host, server_port, database, engine_url = _target_parts_from_url(database_url)
    engine: AsyncEngine = create_async_engine(engine_url, pool_pre_ping=True)
    try:
        try:
            async with engine.begin() as connection:
                # 1) bounded waits, then the fixed-order catalog locks.
                await apply_transaction_prelude(connection)
                await lock_catalog_tables(connection)
                db_actor = await current_database_actor(connection)

                # 2) target check: the operator URL must be the reviewed
                #    baseline target (refresh mode); bootstrap proves the
                #    catalog is empty below.
                mode = "bootstrap" if capture.bundle.baseline.mode == "first_install" else "refresh"
                if mode == "refresh":
                    target = capture.baseline.target
                    if (server_host, server_port, database) != (
                        target.server_host,
                        target.server_port,
                        target.database,
                    ):
                        raise CatalogRefreshBlockedError(
                            "apply_target_mismatch",
                            "the operator database URL does not match the reviewed baseline target",
                        )

                session = AsyncSession(bind=connection, expire_on_commit=False)
                repo_apps = CatalogRefreshApplicationsRepository(session)

                # 3) committed-outcome lookup by canonical bundle identity
                #    FIRST: a retry resolves its prior committed outcome even
                #    if the catalog has since moved (it never overwrites).
                committed = await repo_apps.find_committed_by_bundle(
                    bundle_sha256=bundle_sha256
                )
                if committed:
                    if len(committed) > 1:
                        raise CatalogRefreshBlockedError(
                            "apply_duplicate_record",
                            "multiple committed application records exist for this bundle; refusing silently",
                        )
                    row = committed[0]
                    return ApplyResult(
                        status="already_committed",
                        run_id=row.run_id,
                        bundle_sha256=bundle_sha256,
                        plan_sha256=row.plan_sha256,
                        effective_at=row.effective_at.isoformat() if row.effective_at else None,
                        counts={
                            "created_providers": row.created_providers,
                            "created_routes": row.created_routes,
                            "created_pricing": row.created_pricing,
                            "created_fx": row.created_fx,
                            "superseded_pricing": row.superseded_pricing,
                            "superseded_fx": row.superseded_fx,
                        },
                        record=_safe_record(row),
                    )

                # 4) current execution gates, AFTER the known-committed
                #    lookup: a retry of an already-applied bundle always
                #    resolves its prior outcome first, even if source
                #    aging, a finite window expiry, or a re-derived plan
                #    drift has since made a fresh review different. These
                #    gates are pure recomputation (no SQL) and run on the
                #    locked writer connection before any mutation.
                report, _artifacts = validate_bundle(
                    capture.bundle,
                    capture.baseline,
                    capture.policy,
                    sql_capture=sql_capture_for_mode(capture.bundle.baseline.mode),
                    acquisition=capture.execution_context.acquisition,
                    generator=capture.execution_context.generator,
                    now=datetime.now(UTC),
                )
                if report.state == "BLOCKED":
                    codes = sorted({w.code for w in report.warnings if w.severity == "BLOCKER"})
                    raise CatalogRefreshBlockedError(
                        "apply_freshness_blocked",
                        "the plan is blocked at apply time by: " + ", ".join(codes),
                    )
                pending = sorted(
                    {w.code for w in report.warnings if w.severity != "BLOCKER"}
                    - set(ack_warnings)
                )
                if pending:
                    raise CatalogRefreshBlockedError(
                        "apply_warnings_unacknowledged",
                        "unacknowledged review findings at apply time: "
                        + ", ".join(pending)
                        + "; pass --ack-warnings for each reviewed code",
                    )
                derived_plan = report.apply_plan
                if (
                    derived_plan is None
                    or derived_plan.get("plan_sha256") != plan_sha256
                ):
                    raise CatalogRefreshBlockedError(
                        "apply_plan_mismatch",
                        "the re-derived plan differs from the authenticated reviewed plan; refusing to change reviewed semantics",
                    )

                # 5) stale-baseline comparison on the LOCKED writer view
                #    (same projection the read-only export uses).
                live = await project_catalog_rows(connection)
                if mode == "bootstrap":
                    if any(len(rows) for rows in live):
                        raise CatalogRefreshBlockedError(
                            "apply_bootstrap_not_empty",
                            "bootstrap requires an empty catalog; a populated or drifted database is never converted to a bootstrap",
                        )
                else:
                    drifted = _stale_tables(live, capture.baseline)
                    if drifted:
                        raise CatalogRefreshBlockedError(
                            "apply_baseline_stale",
                            "the catalog drifted from the reviewed baseline in: "
                            + ", ".join(drifted)
                            + "; re-collect and re-review",
                        )

                # 6) the one effective T for this successful transaction.
                effective_at = datetime.now(UTC)

                # 7) operator-supplied admin identity, verified in-txn.
                if admin_id is not None:
                    admin_row = (
                        await session.execute(
                            select(AdminUser).where(AdminUser.id == admin_id)
                        )
                    ).scalar_one_or_none()
                    if admin_row is None:
                        raise CatalogRefreshBlockedError(
                            "apply_admin_unknown",
                            "the supplied admin ID does not exist in this database",
                        )

                pricing_repo = PricingRulesRepository(session)
                fx_repo = FxRatesRepository(session)
                audit_repo = AuditRepository(session)
                provider_service = ProviderConfigService(
                    provider_configs_repository=ProviderConfigsRepository(session),
                    audit_repository=audit_repo,
                )
                route_service = ModelRouteService(
                    model_routes_repository=ModelRoutesRepository(session),
                    audit_repository=audit_repo,
                )
                pricing_service = PricingRuleService(
                    pricing_rules_repository=pricing_repo,
                    audit_repository=audit_repo,
                )
                fx_service = FxRateService(
                    fx_rates_repository=fx_repo,
                    audit_repository=audit_repo,
                )

                applied_providers: list[str] = []
                applied_route_ids: list[str] = []
                pricing_created_ids: list[str] = []
                pricing_superseded_old: list[str] = []
                pricing_superseded_new: list[str] = []
                fx_created_ids: list[str] = []
                fx_superseded_old: list[str] = []
                fx_superseded_new: list[str] = []

                for op in operations:
                    op_type = op["type"]
                    if op_type == "create_provider":
                        row = await provider_service.create_provider_config(
                            provider=op["provider"],
                            display_name=op["display_name"],
                            base_url=op["base_url"],
                            api_key_env_var=op["api_key_env_var"],
                            enabled=bool(op["enabled"]),
                            notes=None,
                            kind=op.get("kind", "openai_compatible"),
                            timeout_seconds=int(op.get("timeout_seconds", 300)),
                            max_retries=int(op.get("max_retries", 2)),
                            actor_admin_id=admin_id,
                            reason=reason,
                            confirm_insecure_http=False,
                        )
                        applied_providers.append(str(row.id))
                    elif op_type == "create_route":
                        row = await route_service.create_model_route(
                            requested_model=op["requested_model"],
                            match_type=op["match_type"],
                            provider=op["provider"],
                            upstream_model=op["upstream_model"],
                            priority=int(op["priority"]),
                            visible_in_models=bool(op["visible_in_models"]),
                            enabled=bool(op["enabled"]),
                            notes=None,
                            endpoint=op["endpoint"],
                            supports_streaming=bool(op["supports_streaming"]),
                            capabilities=dict(op.get("capabilities") or {}),
                            actor_admin_id=admin_id,
                            reason=reason,
                        )
                        applied_route_ids.append(str(row.id))
                    elif op_type == "create_pricing":
                        row = await pricing_service.create_pricing_rule(
                            provider=op["provider"],
                            model=op["model"],
                            endpoint=op["endpoint"],
                            actor_admin_id=admin_id,
                            reason=reason,
                            notes=None,
                            pricing_metadata=None,
                            **_pricing_create_kwargs(
                                op["dimensions"],
                                currency=op["currency"],
                                source_url=op.get("source_url"),
                                valid_from=effective_at,
                            ),
                        )
                        pricing_created_ids.append(str(row.id))
                    elif op_type == "supersede_pricing":
                        old = op["old"]
                        new = op["new"]
                        closed = await pricing_repo.close_active_pricing_rule(
                            pricing_rule_id=uuid.UUID(old["row_id"]),
                            provider=op["provider"],
                            upstream_model=op["model"],
                            endpoint=op["endpoint"],
                            currency=old["currency"],
                            valid_from=_parse_iso(old["valid_from"]),
                            expected_valid_until=_parse_iso(old["valid_until"]),
                            effective_at=effective_at,
                        )
                        if not closed:
                            raise CatalogRefreshBlockedError(
                                "apply_supersession_guard_failed",
                                "the reviewed active pricing row drifted at apply time; nothing was mutated",
                            )
                        row = await pricing_service.create_pricing_rule(
                            provider=op["provider"],
                            model=op["model"],
                            endpoint=op["endpoint"],
                            actor_admin_id=admin_id,
                            reason=reason,
                            notes=None,
                            pricing_metadata=None,
                            **_pricing_create_kwargs(
                                new["dimensions"],
                                currency=new["currency"],
                                source_url=new.get("source_url"),
                                valid_from=effective_at,
                            ),
                        )
                        pricing_superseded_old.append(old["row_id"])
                        pricing_superseded_new.append(str(row.id))
                    elif op_type == "create_fx":
                        row = await fx_service.create_fx_rate(
                            base_currency=op["base_currency"],
                            quote_currency=op["quote_currency"],
                            rate=Decimal(op["rate"]),
                            valid_from=effective_at,
                            valid_until=None,
                            source=op.get("source"),
                            actor_admin_id=admin_id,
                            reason=reason,
                        )
                        fx_created_ids.append(str(row.id))
                    elif op_type == "supersede_fx":
                        old = op["old"]
                        new = op["new"]
                        closed = await fx_repo.close_active_fx_rate(
                            fx_rate_id=uuid.UUID(old["row_id"]),
                            base_currency=op["base_currency"],
                            quote_currency=op["quote_currency"],
                            rate=Decimal(old["rate"]),
                            valid_from=_parse_iso(old["valid_from"]),
                            expected_valid_until=_parse_iso(old["valid_until"]),
                            effective_at=effective_at,
                        )
                        if not closed:
                            raise CatalogRefreshBlockedError(
                                "apply_supersession_guard_failed",
                                "the reviewed active FX row drifted at apply time; nothing was mutated",
                            )
                        row = await fx_service.create_fx_rate(
                            base_currency=op["base_currency"],
                            quote_currency=op["quote_currency"],
                            rate=Decimal(new["rate"]),
                            valid_from=effective_at,
                            valid_until=None,
                            source=new.get("source"),
                            actor_admin_id=admin_id,
                            reason=reason,
                        )
                        fx_superseded_old.append(old["row_id"])
                        fx_superseded_new.append(str(row.id))
                    else:
                        raise CatalogRefreshBlockedError(
                            "apply_unknown_operation",
                            "the reviewed plan contains an operation type this apply cannot execute",
                        )

                counts = {
                    "created_providers": len(applied_providers),
                    "created_routes": len(applied_route_ids),
                    "created_pricing": len(pricing_created_ids),
                    "created_fx": len(fx_created_ids),
                    "superseded_pricing": len(pricing_superseded_old),
                    "superseded_fx": len(fx_superseded_old),
                }

                # 8) the durable application record (same transaction).
                record = await repo_apps.create_application_record(
                    run_id=capture.bundle.run_id,
                    bundle_sha256=bundle_sha256,
                    receipt_hmac_sha256=capture.receipt["hmac_sha256"],
                    plan_sha256=plan_sha256,
                    mode=mode,
                    operator_actor=actor,
                    db_actor=db_actor,
                    admin_user_id=admin_id,
                    reason=reason,
                    effective_at=effective_at,
                    applied_provider_ids=applied_providers,
                    applied_route_ids=applied_route_ids,
                    applied_pricing_created_ids=pricing_created_ids,
                    applied_pricing_superseded_old_ids=pricing_superseded_old,
                    applied_pricing_superseded_new_ids=pricing_superseded_new,
                    applied_fx_created_ids=fx_created_ids,
                    applied_fx_superseded_old_ids=fx_superseded_old,
                    applied_fx_superseded_new_ids=fx_superseded_new,
                    created_providers=counts["created_providers"],
                    created_routes=counts["created_routes"],
                    created_pricing=counts["created_pricing"],
                    created_fx=counts["created_fx"],
                    superseded_pricing=counts["superseded_pricing"],
                    superseded_fx=counts["superseded_fx"],
                )

                # 9) the audit row (same transaction, existing repository).
                await audit_repo.add_audit_log(
                    action="catalog_refresh_applied",
                    entity_type="catalog_refresh_application",
                    admin_user_id=admin_id,
                    entity_id=record.id,
                    new_values={
                        "run_id": record.run_id,
                        "plan_sha256": plan_sha256,
                        "effective_at": effective_at.isoformat(),
                        **counts,
                    },
                    note="catalog refresh apply committed (atomic reviewed plan)",
                )

                return ApplyResult(
                    status="committed",
                    run_id=record.run_id,
                    bundle_sha256=bundle_sha256,
                    plan_sha256=plan_sha256,
                    effective_at=effective_at.isoformat(),
                    counts=counts,
                    record=_safe_record(record),
                )
        except IntegrityError:
            # The uniqueness boundary lost a race (a concurrent same-bundle
            # apply committed first); everything we wrote rolled back.
            committed = await _lookup_committed(
                engine, bundle_sha256=bundle_sha256, plan_sha256=plan_sha256
            )
            if committed is None:
                raise CatalogRefreshBlockedError(
                    "apply_commit_conflict",
                    "duplicate application conflict without a committed record; no mutation occurred",
                ) from None
            return ApplyResult(
                status="already_committed",
                run_id=committed.run_id,
                bundle_sha256=bundle_sha256,
                plan_sha256=committed.plan_sha256,
                effective_at=committed.effective_at.isoformat() if committed.effective_at else None,
                counts={
                    "created_providers": committed.created_providers,
                    "created_routes": committed.created_routes,
                    "created_pricing": committed.created_pricing,
                    "created_fx": committed.created_fx,
                    "superseded_pricing": committed.superseded_pricing,
                    "superseded_fx": committed.superseded_fx,
                },
                record=_safe_record(committed),
            )
        except CatalogRefreshBlockedError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the failure surface safe
            raise CatalogRefreshBlockedError(
                "apply_database_error",
                f"apply failed: {type(exc).__name__}",
            ) from exc
    finally:
        await engine.dispose()


async def apply_reviewed_run(
    *,
    run_dir: Path,
    seal_key: bytes,
    database_url: str,
    reason: str,
    actor: str,
    admin_id: uuid.UUID | None = None,
    ack_warnings: tuple[str, ...] = (),
    run_handle: AnchoredDir | None = None,
) -> ApplyResult:
    """Apply one authenticated reviewed run atomically (A1/A2/A3).

    Refusals are safe code+detail errors. Authentication, the review state,
    and the existence/schema of the sealed plan are checked BEFORE any
    database contact. The current execution gates (apply-time freshness,
    unacknowledged findings, re-derived plan identity) run inside the
    transaction AFTER the known-committed lookup and before any mutation,
    so a retry of an already-applied bundle always returns its committed
    outcome first. Wrong target, stale baseline, non-empty bootstrap,
    unknown admin, and close-guard drift refuse inside the transaction;
    nothing is mutated in any refusal path.
    """
    actor = actor.strip()
    reason = reason.strip()
    if not actor or not reason:
        raise CatalogRefreshBlockedError(
            "apply_intent_incomplete",
            "apply requires non-blank operator actor and reason assertions",
        )

    if run_handle is not None:
        run_handle.assert_name_binding(str(run_dir))
    capture = load_verified_capture(run_dir, seal_key, run_handle=run_handle)
    if capture.result.state not in ("READY", "READY_WITH_WARNINGS"):
        raise CatalogRefreshBlockedError(
            "apply_state_not_applicable",
            f"the sealed review state is {capture.result.state}; only READY or READY_WITH_WARNINGS runs are applicable",
        )

    # The AUTHENTICATED sealed plan is the reviewed artifact: it must exist
    # and use a supported schema before any database contact. The CURRENT
    # execution gates (apply-time freshness, unacknowledged findings,
    # re-derived plan identity) run inside the transaction AFTER the
    # known-committed lookup, so a retry of an already-applied bundle
    # always resolves its prior outcome first.
    sealed_document = json.loads(capture.content["validation.json"])
    sealed_plan = sealed_document.get("apply_plan")
    if not sealed_plan or not sealed_plan.get("operations"):
        raise CatalogRefreshBlockedError(
            "apply_no_plan",
            "the reviewed run carries no executable apply plan (nothing to apply)",
        )
    if sealed_plan.get("schema_version") != APPLY_PLAN_SCHEMA_VERSION:
        raise CatalogRefreshBlockedError(
            "apply_plan_unsupported",
            "the sealed apply plan uses an unsupported schema version",
        )

    return await _execute_transaction(
        capture,
        operations=list(sealed_plan["operations"]),
        plan_sha256=str(sealed_plan["plan_sha256"]),
        bundle_sha256=capture.receipt["semantic_bundle_sha256"],
        database_url=database_url,
        reason=reason,
        actor=actor,
        admin_id=admin_id,
        ack_warnings=ack_warnings,
    )


async def apply_status(
    *,
    run_dir: Path,
    seal_key: bytes,
    database_url: str,
    run_handle: AnchoredDir | None = None,
) -> ApplyStatus:
    """Read-only committed-outcome visibility for one reviewed run.

    Lock-free: status never takes catalog locks, never blocks writers, and
    never mutates. The run is authenticated first so the lookup is by the
    canonical bundle identity, not an operator-supplied value.
    """
    if run_handle is not None:
        run_handle.assert_name_binding(str(run_dir))
    capture = load_verified_capture(run_dir, seal_key, run_handle=run_handle)
    bundle_sha256 = capture.receipt["semantic_bundle_sha256"]
    _host, _port, _database, engine_url = _target_parts_from_url(database_url)
    engine: AsyncEngine = create_async_engine(engine_url, pool_pre_ping=True)
    try:
        try:
            rows = await _lookup_committed_by_bundle(engine, bundle_sha256=bundle_sha256)
        except Exception as exc:  # noqa: BLE001 - keep the failure surface safe
            raise CatalogRefreshBlockedError(
                "apply_status_failed",
                f"status lookup failed: {type(exc).__name__}",
            ) from exc
    finally:
        await engine.dispose()
    return ApplyStatus(
        run_id=capture.bundle.run_id,
        bundle_sha256=bundle_sha256,
        committed=bool(rows),
        records=[_safe_record(row) for row in rows],
    )
