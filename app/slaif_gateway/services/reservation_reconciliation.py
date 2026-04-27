"""Manual reconciliation for expired pending quota reservations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from slaif_gateway.db.models import QuotaReservation
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.reconciliation import (
    ReservationReconciliationResult,
    ReservationReconciliationSummary,
    StaleReservationCandidate,
)
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError
from slaif_gateway.services.reconciliation_errors import (
    ReconciliationInvariantError,
    ReservationNotExpiredError,
    ReservationNotPendingError,
    StaleReservationNotFoundError,
)
from slaif_gateway.utils.redaction import redact_text

_UNKNOWN_PROVIDER = "unknown"
_STALE_RESERVATION_ERROR_TYPE = "stale_quota_reservation"
_AUDIT_ACTION = "quota_reservation_expired"


class ReservationReconciliationService:
    """List and reconcile expired pending reservations within caller transactions."""

    def __init__(
        self,
        *,
        gateway_keys_repository: GatewayKeysRepository,
        quota_reservations_repository: QuotaReservationsRepository,
        usage_ledger_repository: UsageLedgerRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._gateway_keys_repository = gateway_keys_repository
        self._quota_reservations_repository = quota_reservations_repository
        self._usage_ledger_repository = usage_ledger_repository
        self._audit_repository = audit_repository

    async def list_expired_pending_reservations(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[StaleReservationCandidate]:
        """Return expired pending reservations without mutating state."""
        checked_at = _aware_now(now)
        rows = await self._quota_reservations_repository.list_expired_pending_reservations(
            now=checked_at,
            limit=limit,
        )
        return [_candidate(row) for row in rows]

    async def reconcile_expired_pending_reservation(
        self,
        reservation_id: uuid.UUID,
        *,
        now: datetime | None = None,
        dry_run: bool = False,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> ReservationReconciliationResult:
        """Release counters and mark one expired pending reservation as expired."""
        checked_at = _aware_now(now)
        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            reservation_id
        )
        if reservation is None:
            raise StaleReservationNotFoundError()
        if reservation.status != "pending":
            raise ReservationNotPendingError()
        if _aware_now(reservation.expires_at) > checked_at:
            raise ReservationNotExpiredError()

        if dry_run:
            return _result(
                reservation,
                previous_status=reservation.status,
                new_status=reservation.status,
                ledger_created=False,
                audit_created=False,
                dry_run=True,
            )

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id_for_quota_update(
            reservation.gateway_key_id
        )
        if gateway_key is None:
            raise ReconciliationInvariantError("Gateway key was not found during reconciliation")

        try:
            await self._gateway_keys_repository.subtract_reserved_counters(
                gateway_key,
                cost_reserved_eur=reservation.reserved_cost_eur,
                tokens_reserved_total=reservation.reserved_tokens,
                requests_reserved_total=reservation.reserved_requests,
            )
        except QuotaCounterInvariantError as exc:
            raise ReconciliationInvariantError(exc.safe_message, param=exc.param) from exc

        previous_status = reservation.status
        reservation = await self._quota_reservations_repository.mark_pending_reservation_expired(
            reservation,
            released_at=checked_at,
        )
        ledger_created = await self._create_expired_ledger_if_absent(
            reservation=reservation,
            reconciled_at=checked_at,
            reason=reason,
        )
        audit_created = await self._create_audit_log(
            reservation=reservation,
            actor_admin_id=actor_admin_id,
            reason=reason,
            reconciled_at=checked_at,
        )

        return _result(
            reservation,
            previous_status=previous_status,
            new_status=reservation.status,
            ledger_created=ledger_created,
            audit_created=audit_created,
            dry_run=False,
        )

    async def reconcile_expired_pending_reservations(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        dry_run: bool = False,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> ReservationReconciliationSummary:
        """Reconcile a deterministic batch of expired pending reservations."""
        candidates = await self.list_expired_pending_reservations(now=now, limit=limit)
        results: list[ReservationReconciliationResult] = []
        for candidate in candidates:
            results.append(
                await self.reconcile_expired_pending_reservation(
                    candidate.reservation_id,
                    now=now,
                    dry_run=dry_run,
                    actor_admin_id=actor_admin_id,
                    reason=reason,
                )
            )

        reconciled_count = 0 if dry_run else len(results)
        return ReservationReconciliationSummary(
            checked_count=len(candidates),
            candidate_count=len(candidates),
            reconciled_count=reconciled_count,
            skipped_count=0,
            dry_run=dry_run,
            results=results,
        )

    async def _create_expired_ledger_if_absent(
        self,
        *,
        reservation: QuotaReservation,
        reconciled_at: datetime,
        reason: str | None,
    ) -> bool:
        existing = await self._usage_ledger_repository.get_usage_record_by_request_id(
            reservation.request_id
        )
        if existing is not None:
            return False

        await self._usage_ledger_repository.create_failure_record(
            request_id=reservation.request_id,
            quota_reservation_id=reservation.id,
            gateway_key_id=reservation.gateway_key_id,
            endpoint=reservation.endpoint,
            provider=_UNKNOWN_PROVIDER,
            requested_model=reservation.requested_model,
            resolved_model=None,
            streaming=False,
            http_status=None,
            error_type=_STALE_RESERVATION_ERROR_TYPE,
            error_message=_safe_reason(reason),
            prompt_tokens=0,
            completion_tokens=0,
            input_tokens=0,
            output_tokens=0,
            cached_tokens=0,
            reasoning_tokens=0,
            total_tokens=0,
            estimated_cost_eur=reservation.reserved_cost_eur,
            actual_cost_eur=Decimal("0"),
            actual_cost_native=Decimal("0"),
            native_currency="EUR",
            usage_raw={},
            response_metadata={"reconciled_status": "expired"},
            started_at=_aware_now(reservation.created_at),
            finished_at=reconciled_at,
            latency_ms=_latency_ms(_aware_now(reservation.created_at), reconciled_at),
        )
        return True

    async def _create_audit_log(
        self,
        *,
        reservation: QuotaReservation,
        actor_admin_id: uuid.UUID | None,
        reason: str | None,
        reconciled_at: datetime,
    ) -> bool:
        await self._audit_repository.add_audit_log(
            admin_user_id=actor_admin_id,
            action=_AUDIT_ACTION,
            entity_type="quota_reservation",
            entity_id=reservation.id,
            old_values={"status": "pending"},
            new_values={
                "status": reservation.status,
                "released_at": reconciled_at.isoformat(),
                "released_cost_eur": str(reservation.reserved_cost_eur),
                "released_tokens": reservation.reserved_tokens,
                "released_requests": reservation.reserved_requests,
            },
            request_id=reservation.request_id,
            note=_safe_reason(reason),
        )
        return True


def _candidate(row: QuotaReservation) -> StaleReservationCandidate:
    return StaleReservationCandidate(
        reservation_id=row.id,
        gateway_key_id=row.gateway_key_id,
        request_id=row.request_id,
        status=row.status,
        reserved_cost_eur=row.reserved_cost_eur,
        reserved_tokens=row.reserved_tokens,
        reserved_requests=row.reserved_requests,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


def _result(
    reservation: QuotaReservation,
    *,
    previous_status: str,
    new_status: str,
    ledger_created: bool,
    audit_created: bool,
    dry_run: bool,
) -> ReservationReconciliationResult:
    return ReservationReconciliationResult(
        reservation_id=reservation.id,
        gateway_key_id=reservation.gateway_key_id,
        request_id=reservation.request_id,
        previous_status=previous_status,
        new_status=new_status,
        released_cost_eur=reservation.reserved_cost_eur,
        released_tokens=reservation.reserved_tokens,
        released_requests=reservation.reserved_requests,
        ledger_created=ledger_created,
        audit_created=audit_created,
        dry_run=dry_run,
    )


def _aware_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _latency_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _safe_reason(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_text(value.strip())[:256] or None
