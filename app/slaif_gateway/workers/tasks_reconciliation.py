"""Celery tasks for safe quota/accounting reconciliation inspection."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog

from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.session import create_engine_from_settings, create_sessionmaker_from_engine
from slaif_gateway.metrics import (
    add_reconciliation_items,
    increment_reconciliation_run,
    observe_reconciliation_backlog,
)
from slaif_gateway.schemas.reconciliation import (
    ProviderCompletedReconciliationCandidate,
    ProviderCompletedReconciliationResult,
    ProviderCompletedReconciliationSummary,
    ReservationReconciliationResult,
    ReservationReconciliationSummary,
    StaleReservationCandidate,
)
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService
from slaif_gateway.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

_TYPE_EXPIRED = "expired_reservation"
_TYPE_PROVIDER_COMPLETED = "provider_completed_finalization_failed"


@celery_app.task(name="slaif_gateway.reconciliation.inspect_backlog")
def inspect_reconciliation_backlog_task() -> dict[str, object]:
    """Inspect reconciliation backlog without mutating quota/accounting state."""
    return asyncio.run(_inspect_reconciliation_backlog(settings=get_settings()))


@celery_app.task(name="slaif_gateway.reconciliation.reconcile_expired_reservations")
def reconcile_expired_reservations_task(
    *,
    limit: int | None = None,
    dry_run: bool | None = None,
    actor_admin_id: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Run expired reservation reconciliation only when explicit settings allow mutation."""
    return asyncio.run(
        _reconcile_expired_reservations(
            settings=get_settings(),
            limit=limit,
            dry_run=dry_run,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
    )


@celery_app.task(name="slaif_gateway.reconciliation.reconcile_provider_completed")
def reconcile_provider_completed_task(
    *,
    limit: int | None = None,
    dry_run: bool | None = None,
    actor_admin_id: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Run provider-completed reconciliation only when explicit settings allow mutation."""
    return asyncio.run(
        _reconcile_provider_completed(
            settings=get_settings(),
            limit=limit,
            dry_run=dry_run,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
    )


async def _inspect_reconciliation_backlog(*, settings: Settings) -> dict[str, object]:
    engine = create_engine_from_settings(settings)
    try:
        session_factory = create_sessionmaker_from_engine(engine)
        async with session_factory() as session:
            service = _service(session)
            expired_cutoff = _expired_reservation_cutoff(settings)
            provider_cutoff = _provider_completed_cutoff(settings)
            expired = await service.list_expired_pending_reservations(
                now=expired_cutoff,
                limit=settings.RECONCILIATION_EXPIRED_RESERVATION_LIMIT,
            )
            provider_completed = await service.list_provider_completed_recovery_rows(
                limit=settings.RECONCILIATION_PROVIDER_COMPLETED_LIMIT,
                older_than=provider_cutoff,
            )
            payload = {
                "status": "success",
                "dry_run": True,
                "expired_reservations": _expired_backlog_payload(expired),
                "provider_completed": _provider_completed_backlog_payload(provider_completed),
            }
            observe_reconciliation_backlog(
                reconciliation_type=_TYPE_EXPIRED,
                count=len(expired),
            )
            observe_reconciliation_backlog(
                reconciliation_type=_TYPE_PROVIDER_COMPLETED,
                count=len(provider_completed),
            )
            increment_reconciliation_run(
                reconciliation_type="inspect",
                status="success",
                dry_run=True,
            )
            logger.info(
                "Reconciliation backlog inspected.",
                expired_reservations=len(expired),
                provider_completed=len(provider_completed),
                dry_run=True,
            )
            return payload
    except Exception:
        increment_reconciliation_run(
            reconciliation_type="inspect",
            status="failure",
            dry_run=True,
        )
        logger.exception("Reconciliation backlog inspection failed.")
        raise
    finally:
        await engine.dispose()


async def _reconcile_expired_reservations(
    *,
    settings: Settings,
    limit: int | None = None,
    dry_run: bool | None = None,
    actor_admin_id: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    requested_dry_run = settings.RECONCILIATION_DRY_RUN if dry_run is None else dry_run
    effective_dry_run = requested_dry_run or not settings.RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS
    effective_limit = _effective_limit(limit, settings.RECONCILIATION_EXPIRED_RESERVATION_LIMIT)
    actor_id = _parse_actor_admin_id(actor_admin_id)
    engine = create_engine_from_settings(settings)
    try:
        session_factory = create_sessionmaker_from_engine(engine)
        async with session_factory() as session:
            async with session.begin():
                summary = await _service(session).reconcile_expired_pending_reservations(
                    now=_expired_reservation_cutoff(settings),
                    limit=effective_limit,
                    dry_run=effective_dry_run,
                    actor_admin_id=actor_id,
                    reason=reason,
                )
            payload = _reservation_summary_payload(summary)
            status = "success"
            increment_reconciliation_run(
                reconciliation_type=_TYPE_EXPIRED,
                status=status,
                dry_run=effective_dry_run,
            )
            add_reconciliation_items(
                reconciliation_type=_TYPE_EXPIRED,
                status="checked",
                dry_run=effective_dry_run,
                count=summary.checked_count,
            )
            add_reconciliation_items(
                reconciliation_type=_TYPE_EXPIRED,
                status="reconciled",
                dry_run=effective_dry_run,
                count=summary.reconciled_count,
            )
            logger.info(
                "Expired reservation reconciliation task completed.",
                dry_run=effective_dry_run,
                checked_count=summary.checked_count,
                reconciled_count=summary.reconciled_count,
            )
            return payload
    except Exception:
        increment_reconciliation_run(
            reconciliation_type=_TYPE_EXPIRED,
            status="failure",
            dry_run=effective_dry_run,
        )
        logger.exception("Expired reservation reconciliation task failed.", dry_run=effective_dry_run)
        raise
    finally:
        await engine.dispose()


async def _reconcile_provider_completed(
    *,
    settings: Settings,
    limit: int | None = None,
    dry_run: bool | None = None,
    actor_admin_id: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    requested_dry_run = settings.RECONCILIATION_DRY_RUN if dry_run is None else dry_run
    effective_dry_run = requested_dry_run or not settings.RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED
    effective_limit = _effective_limit(limit, settings.RECONCILIATION_PROVIDER_COMPLETED_LIMIT)
    actor_id = _parse_actor_admin_id(actor_admin_id)
    engine = create_engine_from_settings(settings)
    try:
        session_factory = create_sessionmaker_from_engine(engine)
        async with session_factory() as session:
            async with session.begin():
                summary = await _service(session).reconcile_provider_completed_recovery_rows(
                    limit=effective_limit,
                    dry_run=effective_dry_run,
                    actor_admin_id=actor_id,
                    reason=reason,
                    older_than=_provider_completed_cutoff(settings),
                )
            payload = _provider_completed_summary_payload(summary)
            increment_reconciliation_run(
                reconciliation_type=_TYPE_PROVIDER_COMPLETED,
                status="success",
                dry_run=effective_dry_run,
            )
            add_reconciliation_items(
                reconciliation_type=_TYPE_PROVIDER_COMPLETED,
                status="checked",
                dry_run=effective_dry_run,
                count=summary.checked_count,
            )
            add_reconciliation_items(
                reconciliation_type=_TYPE_PROVIDER_COMPLETED,
                status="reconciled",
                dry_run=effective_dry_run,
                count=summary.reconciled_count,
            )
            logger.info(
                "Provider-completed reconciliation task completed.",
                dry_run=effective_dry_run,
                checked_count=summary.checked_count,
                reconciled_count=summary.reconciled_count,
            )
            return payload
    except Exception:
        increment_reconciliation_run(
            reconciliation_type=_TYPE_PROVIDER_COMPLETED,
            status="failure",
            dry_run=effective_dry_run,
        )
        logger.exception("Provider-completed reconciliation task failed.", dry_run=effective_dry_run)
        raise
    finally:
        await engine.dispose()


def _service(session) -> ReservationReconciliationService:
    return ReservationReconciliationService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
        usage_ledger_repository=UsageLedgerRepository(session),
        audit_repository=AuditRepository(session),
    )


def _expired_reservation_cutoff(settings: Settings) -> datetime:
    return datetime.now(UTC) - timedelta(
        seconds=settings.RECONCILIATION_EXPIRED_RESERVATION_OLDER_THAN_SECONDS
    )


def _provider_completed_cutoff(settings: Settings) -> datetime | None:
    seconds = settings.RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS
    if seconds <= 0:
        return None
    return datetime.now(UTC) - timedelta(seconds=seconds)


def _parse_actor_admin_id(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(value)


def _effective_limit(value: int | None, default: int) -> int:
    limit = default if value is None else value
    if limit <= 0:
        raise ValueError("reconciliation task limit must be positive")
    return limit


def _expired_backlog_payload(rows: list[StaleReservationCandidate]) -> dict[str, object]:
    return {
        "candidate_count": len(rows),
        "reservation_ids": [str(row.reservation_id) for row in rows],
    }


def _provider_completed_backlog_payload(
    rows: list[ProviderCompletedReconciliationCandidate],
) -> dict[str, object]:
    return {
        "candidate_count": len(rows),
        "usage_ledger_ids": [str(row.usage_ledger_id) for row in rows],
        "reservation_ids": [str(row.reservation_id) for row in rows],
    }


def _reservation_summary_payload(summary: ReservationReconciliationSummary) -> dict[str, object]:
    return {
        "type": _TYPE_EXPIRED,
        "dry_run": summary.dry_run,
        "checked_count": summary.checked_count,
        "candidate_count": summary.candidate_count,
        "reconciled_count": summary.reconciled_count,
        "skipped_count": summary.skipped_count,
        "results": [_reservation_result_payload(row) for row in summary.results],
    }


def _reservation_result_payload(row: ReservationReconciliationResult) -> dict[str, object]:
    return {
        "reservation_id": str(row.reservation_id),
        "previous_status": row.previous_status,
        "new_status": row.new_status,
        "ledger_created": row.ledger_created,
        "audit_created": row.audit_created,
        "dry_run": row.dry_run,
    }


def _provider_completed_summary_payload(
    summary: ProviderCompletedReconciliationSummary,
) -> dict[str, object]:
    return {
        "type": _TYPE_PROVIDER_COMPLETED,
        "dry_run": summary.dry_run,
        "checked_count": summary.checked_count,
        "candidate_count": summary.candidate_count,
        "reconciled_count": summary.reconciled_count,
        "skipped_count": summary.skipped_count,
        "results": [_provider_completed_result_payload(row) for row in summary.results],
    }


def _provider_completed_result_payload(row: ProviderCompletedReconciliationResult) -> dict[str, object]:
    return {
        "usage_ledger_id": str(row.usage_ledger_id),
        "reservation_id": str(row.reservation_id),
        "previous_accounting_status": row.previous_accounting_status,
        "new_accounting_status": row.new_accounting_status,
        "reservation_status": row.reservation_status,
        "reconciled": row.reconciled,
        "dry_run": row.dry_run,
    }
