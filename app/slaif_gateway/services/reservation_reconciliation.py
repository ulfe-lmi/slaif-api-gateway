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
    ProviderCompletedReconciliationCandidate,
    ProviderCompletedReconciliationResult,
    ProviderCompletedReconciliationSummary,
    ReservationReconciliationResult,
    ReservationReconciliationSummary,
    StaleReservationCandidate,
)
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError
from slaif_gateway.services.reconciliation_errors import (
    ProviderCompletedRecoveryAlreadyReconciledError,
    ProviderCompletedRecoveryInvariantError,
    ProviderCompletedRecoveryMetadataMissingError,
    ProviderCompletedRecoveryNotFoundError,
    ProviderCompletedRecoveryNotRepairableError,
    ReconciliationInvariantError,
    ReservationNotExpiredError,
    ReservationNotPendingError,
    StaleReservationNotFoundError,
)
from slaif_gateway.utils.redaction import redact_text

_UNKNOWN_PROVIDER = "unknown"
_STALE_RESERVATION_ERROR_TYPE = "stale_quota_reservation"
_AUDIT_ACTION = "quota_reservation_expired"
_PROVIDER_COMPLETED_RECOVERY_STATE = "provider_completed_finalization_failed"
_PROVIDER_COMPLETED_RECONCILED_STATE = "provider_completed_reconciled"
_PROVIDER_COMPLETED_AUDIT_ACTION = "provider_completed_reconciliation"


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

        existing_ledger = await self._usage_ledger_repository.get_usage_record_by_request_id(
            reservation.request_id
        )
        if (
            not dry_run
            and existing_ledger is not None
            and (getattr(existing_ledger, "response_metadata", None) or {}).get("needs_reconciliation")
            is True
        ):
            raise ReconciliationInvariantError(
                "Provider completed before accounting finalization failed; do not release as zero-cost stale reservation"
            )

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

    async def list_provider_completed_recovery_rows(
        self,
        *,
        limit: int = 100,
        gateway_key_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        older_than: datetime | None = None,
    ) -> list[ProviderCompletedReconciliationCandidate]:
        """Return provider-completed finalization-failed rows without mutation."""
        rows = await self._usage_ledger_repository.list_provider_completed_recovery_records(
            limit=limit,
            gateway_key_id=gateway_key_id,
            provider=provider,
            model=model,
            older_than=older_than,
        )
        return [_provider_completed_candidate(row) for row in rows if _is_repairable_shape(row)]

    async def reconcile_provider_completed_recovery(
        self,
        *,
        usage_ledger_id: uuid.UUID | None = None,
        reservation_id: uuid.UUID | None = None,
        dry_run: bool = True,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> ProviderCompletedReconciliationResult:
        """Finalize a provider-completed accounting recovery row."""
        if (usage_ledger_id is None) == (reservation_id is None):
            raise ProviderCompletedRecoveryNotRepairableError(
                "Provide exactly one of usage_ledger_id or reservation_id"
            )

        reconciled_at = _aware_now(now)
        ledger = await self._usage_ledger_repository.get_provider_completed_recovery_record_for_update(
            usage_ledger_id=usage_ledger_id,
            reservation_id=reservation_id,
        )
        if ledger is None:
            maybe_existing = None
            if usage_ledger_id is not None:
                maybe_existing = await self._usage_ledger_repository.get_usage_record_by_id(
                    usage_ledger_id
                )
            if maybe_existing is not None and maybe_existing.accounting_status == "finalized":
                raise ProviderCompletedRecoveryAlreadyReconciledError()
            raise ProviderCompletedRecoveryNotFoundError()

        _validate_provider_completed_ledger(ledger)
        if ledger.quota_reservation_id is None:
            raise ProviderCompletedRecoveryMetadataMissingError(
                "Recovery row has no quota reservation"
            )

        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            ledger.quota_reservation_id
        )
        if reservation is None:
            raise ProviderCompletedRecoveryNotRepairableError("Quota reservation was not found")
        if reservation.id != ledger.quota_reservation_id:
            raise ProviderCompletedRecoveryInvariantError("Recovery row reservation mismatch")
        if reservation.gateway_key_id != ledger.gateway_key_id:
            raise ProviderCompletedRecoveryInvariantError("Recovery row gateway key mismatch")
        if reservation.status != "pending":
            raise ProviderCompletedRecoveryNotRepairableError("Quota reservation is not pending")

        if dry_run:
            return _provider_completed_result(
                ledger,
                reservation,
                previous_accounting_status=ledger.accounting_status,
                new_accounting_status=ledger.accounting_status,
                reconciled=False,
                dry_run=True,
            )

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id_for_quota_update(
            ledger.gateway_key_id
        )
        if gateway_key is None:
            raise ProviderCompletedRecoveryInvariantError("Gateway key was not found")

        try:
            await self._gateway_keys_repository.finalize_reserved_counters(
                gateway_key,
                reserved_cost_eur=reservation.reserved_cost_eur,
                reserved_tokens_total=reservation.reserved_tokens,
                reserved_requests_total=reservation.reserved_requests,
                actual_cost_eur=ledger.actual_cost_eur,
                actual_tokens_total=ledger.total_tokens,
                actual_requests_total=1,
                last_used_at=reconciled_at,
            )
        except QuotaCounterInvariantError as exc:
            raise ProviderCompletedRecoveryInvariantError(
                exc.safe_message,
                param=exc.param,
            ) from exc

        previous_status = ledger.accounting_status
        reservation = await self._quota_reservations_repository.mark_pending_reservation_finalized(
            reservation,
            finalized_at=reconciled_at,
        )
        ledger = await self._usage_ledger_repository.mark_provider_completed_reconciled(
            ledger.id,
            response_metadata=_reconciled_metadata(
                ledger.response_metadata,
                reconciled_at=reconciled_at,
                actor_admin_id=actor_admin_id,
                reason=reason,
            ),
            finished_at=reconciled_at,
        )
        await self._create_provider_completed_audit_log(
            ledger=ledger,
            reservation=reservation,
            actor_admin_id=actor_admin_id,
            reason=reason,
            reconciled_at=reconciled_at,
        )

        return _provider_completed_result(
            ledger,
            reservation,
            previous_accounting_status=previous_status,
            new_accounting_status=ledger.accounting_status,
            reconciled=True,
            dry_run=False,
        )

    async def reconcile_provider_completed_recovery_rows(
        self,
        *,
        limit: int = 100,
        dry_run: bool = True,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
        now: datetime | None = None,
        older_than: datetime | None = None,
    ) -> ProviderCompletedReconciliationSummary:
        """Reconcile a deterministic batch of provider-completed recovery rows."""
        candidates = await self.list_provider_completed_recovery_rows(
            limit=limit,
            older_than=older_than,
        )
        results: list[ProviderCompletedReconciliationResult] = []
        for candidate in candidates:
            results.append(
                await self.reconcile_provider_completed_recovery(
                    usage_ledger_id=candidate.usage_ledger_id,
                    dry_run=dry_run,
                    actor_admin_id=actor_admin_id,
                    reason=reason,
                    now=now,
                )
            )

        reconciled_count = 0 if dry_run else len(results)
        return ProviderCompletedReconciliationSummary(
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

    async def _create_provider_completed_audit_log(
        self,
        *,
        ledger,
        reservation: QuotaReservation,
        actor_admin_id: uuid.UUID | None,
        reason: str | None,
        reconciled_at: datetime,
    ) -> bool:
        await self._audit_repository.add_audit_log(
            admin_user_id=actor_admin_id,
            action=_PROVIDER_COMPLETED_AUDIT_ACTION,
            entity_type="usage_ledger",
            entity_id=ledger.id,
            old_values={
                "accounting_status": "failed",
                "reservation_status": "pending",
                "needs_reconciliation": True,
            },
            new_values={
                "accounting_status": ledger.accounting_status,
                "reservation_status": reservation.status,
                "needs_reconciliation": False,
                "reconciled_at": reconciled_at.isoformat(),
                "actual_cost_eur": str(ledger.actual_cost_eur),
                "total_tokens": ledger.total_tokens,
            },
            request_id=ledger.request_id,
            note=_safe_reason(reason),
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


def _provider_completed_candidate(row) -> ProviderCompletedReconciliationCandidate:
    return ProviderCompletedReconciliationCandidate(
        usage_ledger_id=row.id,
        reservation_id=row.quota_reservation_id,
        gateway_key_id=row.gateway_key_id,
        request_id=row.request_id,
        provider=row.provider,
        requested_model=row.requested_model,
        resolved_model=row.resolved_model,
        endpoint=row.endpoint,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        estimated_cost_eur=row.estimated_cost_eur,
        actual_cost_eur=row.actual_cost_eur,
        created_at=row.created_at,
        recovery_state=(row.response_metadata or {}).get("recovery_state", ""),
    )


def _provider_completed_result(
    ledger,
    reservation: QuotaReservation,
    *,
    previous_accounting_status: str,
    new_accounting_status: str,
    reconciled: bool,
    dry_run: bool,
) -> ProviderCompletedReconciliationResult:
    return ProviderCompletedReconciliationResult(
        usage_ledger_id=ledger.id,
        reservation_id=reservation.id,
        gateway_key_id=ledger.gateway_key_id,
        request_id=ledger.request_id,
        previous_accounting_status=previous_accounting_status,
        new_accounting_status=new_accounting_status,
        reservation_status=reservation.status,
        used_cost_eur=ledger.actual_cost_eur,
        used_tokens=ledger.total_tokens,
        reconciled=reconciled,
        dry_run=dry_run,
    )


def _is_repairable_shape(row) -> bool:
    try:
        _validate_provider_completed_ledger(row)
    except ProviderCompletedRecoveryMetadataMissingError:
        return False
    except ProviderCompletedRecoveryNotRepairableError:
        return False
    return True


def _validate_provider_completed_ledger(row) -> None:
    metadata = row.response_metadata or {}
    if metadata.get("needs_reconciliation") is not True:
        raise ProviderCompletedRecoveryNotRepairableError("Recovery row is not marked for reconciliation")
    if metadata.get("recovery_state") != _PROVIDER_COMPLETED_RECOVERY_STATE:
        raise ProviderCompletedRecoveryNotRepairableError("Recovery row has an unsupported recovery state")
    if row.quota_reservation_id is None:
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row is missing reservation metadata")
    if row.gateway_key_id is None:
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row is missing gateway key metadata")
    if not row.provider or not row.endpoint:
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row is missing provider metadata")
    if row.prompt_tokens is None or row.completion_tokens is None or row.total_tokens is None:
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row is missing usage metadata")
    if row.total_tokens <= 0:
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row has no final usage tokens")
    if row.estimated_cost_eur is None or row.actual_cost_eur is None:
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row is missing cost metadata")
    if row.actual_cost_eur <= Decimal("0"):
        raise ProviderCompletedRecoveryMetadataMissingError("Recovery row has no positive actual cost")


def _reconciled_metadata(
    metadata: dict[str, object] | None,
    *,
    reconciled_at: datetime,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> dict[str, object]:
    updated = dict(metadata or {})
    updated["needs_reconciliation"] = False
    updated["recovery_state"] = _PROVIDER_COMPLETED_RECONCILED_STATE
    updated["reconciled_at"] = reconciled_at.isoformat()
    if actor_admin_id is not None:
        updated["reconciled_by_admin_id"] = str(actor_admin_id)
    safe_reason = _safe_reason(reason)
    if safe_reason is not None:
        updated["reconciliation_reason"] = safe_reason
    return updated


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
