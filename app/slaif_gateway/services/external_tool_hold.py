"""PostgreSQL-authoritative external-tool accounting hold foundation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.external_tool_fence import ExternalToolFenceResolveInput
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldInput,
    ExternalToolAccountingHoldProjection,
    ExternalToolHoldAction,
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReconciliationInput,
    ExternalToolHoldReconciliationResult,
    ExternalToolHoldReasonCode,
    safe_hold_metadata,
    validate_partial_facts,
)
from slaif_gateway.services.external_tool_fence import (
    FENCE_ACTIVE,
    FENCE_HELD,
    ExternalToolFenceConflictError,
    ExternalToolFenceService,
)

_EXTERNAL_TOOL_FENCED = "external_tool_fenced"


class ExternalToolAccountingHoldError(Exception):
    """Safe domain error for hold placement."""

    status_code = 409
    error_code = "external_tool_accounting_hold_error"


class InvalidExternalToolAccountingHoldError(ExternalToolAccountingHoldError):
    status_code = 400
    error_code = "invalid_external_tool_accounting_hold"


class ExternalToolAccountingHoldInvariantError(ExternalToolAccountingHoldError):
    status_code = 500
    error_code = "external_tool_accounting_hold_invariant"


class ExternalToolAccountingHoldService:
    """Place a hold without committing; the caller owns the transaction."""

    def __init__(
        self,
        *,
        gateway_keys_repository: GatewayKeysRepository,
        quota_reservations_repository: QuotaReservationsRepository,
        usage_ledger_repository: UsageLedgerRepository,
        audit_repository: AuditRepository,
        fence_service: ExternalToolFenceService | None = None,
    ) -> None:
        self._gateway_keys_repository = gateway_keys_repository
        self._quota_reservations_repository = quota_reservations_repository
        self._usage_ledger_repository = usage_ledger_repository
        self._audit_repository = audit_repository
        self._fence_service = fence_service or ExternalToolFenceService(
            gateway_keys_repository=gateway_keys_repository,
            quota_reservations_repository=quota_reservations_repository,
            usage_ledger_repository=usage_ledger_repository,
            audit_repository=audit_repository,
        )

    async def place(
        self, hold_input: ExternalToolAccountingHoldInput
    ) -> ExternalToolAccountingHoldProjection:
        now = _aware_now(hold_input.now)
        _validate_input(hold_input)
        validate_partial_facts(
            partial_total_tokens=hold_input.partial_total_tokens,
            estimated_cost_eur=hold_input.estimated_cost_eur,
        )

        # Reservation first, then key: every hold mutation follows the same
        # lifecycle order and therefore cannot invert the fence lock order.
        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            hold_input.reservation_id
        )
        if reservation is None:
            raise ExternalToolAccountingHoldInvariantError("Hold reservation is missing")
        gateway_key = await self._gateway_keys_repository.get_gateway_key_for_update(
            hold_input.gateway_key_id
        )
        if gateway_key is None:
            raise ExternalToolAccountingHoldInvariantError("Hold gateway key is missing")

        self._validate_reservation_and_fence(hold_input, reservation, gateway_key)
        ledgers = await self._usage_ledger_repository.get_usage_records_by_reservation_id(
            reservation.id
        )
        if len(ledgers) == 1 and gateway_key.external_tool_fence_state == FENCE_HELD:
            ledger = ledgers[0]
            if _ledger_matches_hold(
                ledger,
                reason_code=hold_input.reason_code,
                evidence_quality=hold_input.evidence_quality,
                partial_total_tokens=hold_input.partial_total_tokens,
                estimated_cost_eur=hold_input.estimated_cost_eur,
            ):
                return _projection(gateway_key, reservation, ledger)
            raise ExternalToolFenceConflictError(
                code="external_tool_accounting_hold_retry_conflict"
            )
        if ledgers:
            raise ExternalToolAccountingHoldInvariantError(
                "A new hold requires zero linked usage ledgers"
            )
        if (
            gateway_key.cost_reserved_eur != reservation.reserved_cost_eur
            or gateway_key.tokens_reserved_total != reservation.reserved_tokens
            or gateway_key.requests_reserved_total != reservation.reserved_requests
        ):
            raise ExternalToolAccountingHoldInvariantError(
                "Hold requires the complete reservation balance to remain reserved"
            )

        status = (
            "estimated"
            if hold_input.partial_total_tokens is not None
            or hold_input.estimated_cost_eur is not None
            else "interrupted"
        )
        ledger = await self._usage_ledger_repository.create_usage_record(
            request_id=reservation.request_id,
            gateway_key_id=gateway_key.id,
            endpoint=reservation.endpoint,
            provider=reservation.external_tool_provider or "unknown",
            requested_model=reservation.requested_model,
            started_at=now,
            quota_reservation_id=reservation.id,
            streaming=hold_input.streaming,
            success=None,
            accounting_status=status,
            total_tokens=hold_input.partial_total_tokens or 0,
            estimated_cost_eur=hold_input.estimated_cost_eur,
            actual_cost_eur=None,
            usage_raw={},
            response_metadata=safe_hold_metadata(
                reason_code=hold_input.reason_code,
                evidence_quality=hold_input.evidence_quality,
                held_at=now,
            ),
        )
        await self._gateway_keys_repository.set_external_tool_fence(
            gateway_key,
            state=FENCE_HELD,
            reservation_id=reservation.id,
            request_id=reservation.request_id,
            acquired_at=gateway_key.external_tool_fence_acquired_at,
            expires_at=gateway_key.external_tool_fence_expires_at,
        )
        await self._audit_repository.add_audit_log(
            action="external_tool_accounting_hold_created",
            entity_type="gateway_key",
            entity_id=gateway_key.id,
            request_id=reservation.request_id,
            new_values={
                "state": "held",
                "reservation_id": str(reservation.id),
                "usage_ledger_id": str(ledger.id),
                "reason_code": hold_input.reason_code.value,
                "evidence_quality": hold_input.evidence_quality.value,
                "accounting_status": status,
            },
            note="external tool accounting hold created",
        )
        return _projection(gateway_key, reservation, ledger)

    async def list_holds(
        self, *, limit: int = 100
    ) -> list[ExternalToolAccountingHoldProjection]:
        """Return only exact held shapes for operator inspection."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise InvalidExternalToolAccountingHoldError("Hold limit must be positive")
        projections: list[ExternalToolAccountingHoldProjection] = []
        for ledger in await self._usage_ledger_repository.list_external_tool_accounting_hold_records(
            limit=limit
        ):
            if ledger.quota_reservation_id is None:
                continue
            reservation = await self._quota_reservations_repository.get_reservation_by_id(
                ledger.quota_reservation_id
            )
            if reservation is None:
                continue
            gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id(
                ledger.gateway_key_id
            )
            if gateway_key is None:
                continue
            try:
                self._validate_reservation_and_fence(
                    ExternalToolAccountingHoldInput(
                        gateway_key_id=gateway_key.id,
                        reservation_id=reservation.id,
                        request_id=reservation.request_id,
                        reason_code=ExternalToolHoldReasonCode(
                            ((ledger.response_metadata or {}).get("external_tool_accounting_hold") or {})[
                                "reason_code"
                            ]
                        ),
                        evidence_quality=ExternalToolHoldEvidenceQuality(
                            ((ledger.response_metadata or {}).get("external_tool_accounting_hold") or {})[
                                "evidence_quality"
                            ]
                        ),
                        streaming=ledger.streaming,
                        now=ledger.created_at,
                        partial_total_tokens=ledger.total_tokens or None,
                        estimated_cost_eur=ledger.estimated_cost_eur,
                    ),
                    reservation,
                    gateway_key,
                )
            except (KeyError, ValueError, ExternalToolAccountingHoldError):
                continue
            if ledger.accounting_status not in ("estimated", "interrupted"):
                continue
            projections.append(_projection(gateway_key, reservation, ledger))
        return projections[:limit]

    async def reconcile(
        self, request: ExternalToolHoldReconciliationInput
    ) -> ExternalToolHoldReconciliationResult:
        """Dry-run or explicitly execute one audited hold reconciliation."""
        _validate_reconciliation_input(request)
        if not request.execute:
            ledger, reservation, gateway_key = await self._load_candidate(request.reservation_id)
            return _reconciliation_result(
                request, ledger=ledger, reservation=reservation, gateway_key=gateway_key
            )

        # Deliberately lock ledger -> reservation -> key.  All mutation and
        # repeat validation happens while these locks are held.
        ledger = await self._usage_ledger_repository.get_usage_record_by_id_for_update(
            await self._ledger_id_for_reservation(request.reservation_id)
        )
        if ledger is None:
            raise ExternalToolAccountingHoldInvariantError("Hold ledger is missing")
        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            request.reservation_id
        )
        if reservation is None:
            raise ExternalToolAccountingHoldInvariantError("Hold reservation is missing")
        gateway_key = await self._gateway_keys_repository.get_gateway_key_for_update(
            reservation.gateway_key_id
        )
        if gateway_key is None:
            raise ExternalToolAccountingHoldInvariantError("Hold gateway key is missing")

        prior = _reconciliation_metadata(ledger)
        if reservation.status in ("finalized", "released") and gateway_key.external_tool_fence_state == "none":
            if _reconciliation_matches(prior, request):
                return _reconciliation_result(
                    request, ledger=ledger, reservation=reservation, gateway_key=gateway_key, idempotent=True
                )
            raise ExternalToolFenceConflictError(
                code="external_tool_accounting_reconciliation_conflict"
            )
        self._validate_locked_candidate(ledger, reservation, gateway_key)

        now = _aware_now(datetime.now(UTC))
        if request.action == ExternalToolHoldAction.FINALIZE_ACTUAL:
            assert request.actual_cost_eur is not None
            assert request.actual_total_tokens is not None
            assert request.success is not None
            overrun_cost = request.actual_cost_eur > reservation.reserved_cost_eur
            overrun_tokens = request.actual_total_tokens > reservation.reserved_tokens
            await self._gateway_keys_repository.finalize_reserved_counters(
                gateway_key,
                reserved_cost_eur=reservation.reserved_cost_eur,
                reserved_tokens_total=reservation.reserved_tokens,
                reserved_requests_total=reservation.reserved_requests,
                actual_cost_eur=request.actual_cost_eur,
                actual_tokens_total=request.actual_total_tokens,
                actual_requests_total=1,
                last_used_at=now,
            )
            await self._quota_reservations_repository.mark_pending_reservation_finalized(
                reservation, finalized_at=now
            )
            metadata = _terminal_metadata(
                ledger,
                action=request.action.value,
                actor_admin_id=request.actor_admin_id,
                reason=request.reason,
                actual_cost_eur=request.actual_cost_eur,
                actual_total_tokens=request.actual_total_tokens,
                success=request.success,
                overrun_cost=overrun_cost,
                overrun_tokens=overrun_tokens,
            )
            await self._usage_ledger_repository.update_external_tool_hold_ledger(
                ledger,
                accounting_status="finalized",
                success=request.success,
                actual_cost_eur=request.actual_cost_eur,
                total_tokens=request.actual_total_tokens,
                response_metadata=metadata,
                finished_at=now,
            )
        else:
            await self._gateway_keys_repository.subtract_reserved_counters(
                gateway_key,
                cost_reserved_eur=reservation.reserved_cost_eur,
                tokens_reserved_total=reservation.reserved_tokens,
                requests_reserved_total=reservation.reserved_requests,
            )
            await self._quota_reservations_repository.mark_pending_reservation_released(
                reservation, released_at=now
            )
            metadata = _terminal_metadata(
                ledger,
                action=request.action.value,
                actor_admin_id=request.actor_admin_id,
                reason=request.reason,
                actual_cost_eur=Decimal("0"),
                actual_total_tokens=0,
                success=False,
                overrun_cost=False,
                overrun_tokens=False,
                confirmed_no_charge=True,
            )
            await self._usage_ledger_repository.update_external_tool_hold_ledger(
                ledger,
                accounting_status="failed",
                success=False,
                actual_cost_eur=Decimal("0"),
                total_tokens=0,
                response_metadata=metadata,
                finished_at=now,
            )

        await self._audit_repository.add_audit_log(
            action="external_tool_accounting_hold_reconciled",
            entity_type="gateway_key",
            entity_id=gateway_key.id,
            admin_user_id=request.actor_admin_id,
            request_id=reservation.request_id,
            old_values={"fence_state": "held", "reservation_status": "pending"},
            new_values={
                "action": request.action.value,
                "reservation_status": reservation.status,
                "accounting_status": ledger.accounting_status,
                "actual_cost_eur": str(ledger.actual_cost_eur),
                "actual_total_tokens": ledger.total_tokens,
                "success": ledger.success,
            },
            note="external tool accounting hold reconciled",
        )
        await self._fence_service.resolve(
            ExternalToolFenceResolveInput(
                gateway_key_id=gateway_key.id,
                request_id=reservation.request_id,
            ),
            permit_held=True,
        )
        return _reconciliation_result(
            request, ledger=ledger, reservation=reservation, gateway_key=gateway_key
        )

    async def _ledger_id_for_reservation(self, reservation_id: UUID) -> UUID:
        rows = await self._usage_ledger_repository.get_usage_records_by_reservation_id(
            reservation_id
        )
        if len(rows) != 1:
            raise ExternalToolAccountingHoldInvariantError(
                "Reconciliation requires exactly one linked hold ledger"
            )
        return rows[0].id

    async def _load_candidate(self, reservation_id: UUID):
        rows = await self._usage_ledger_repository.get_usage_records_by_reservation_id(
            reservation_id
        )
        if len(rows) != 1:
            raise ExternalToolAccountingHoldInvariantError(
                "Reconciliation requires exactly one linked hold ledger"
            )
        ledger = rows[0]
        reservation = await self._quota_reservations_repository.get_reservation_by_id(reservation_id)
        if reservation is None:
            raise ExternalToolAccountingHoldInvariantError("Hold reservation is missing")
        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id(
            reservation.gateway_key_id
        )
        if gateway_key is None:
            raise ExternalToolAccountingHoldInvariantError("Hold gateway key is missing")
        self._validate_locked_candidate(ledger, reservation, gateway_key)
        return ledger, reservation, gateway_key

    @staticmethod
    def _validate_reservation_and_fence(hold_input, reservation, gateway_key) -> None:
        if reservation.gateway_key_id != hold_input.gateway_key_id:
            raise ExternalToolAccountingHoldInvariantError("Hold reservation key mismatch")
        if reservation.request_id != hold_input.request_id:
            raise ExternalToolAccountingHoldInvariantError("Hold request ID mismatch")
        if reservation.quota_mode != _EXTERNAL_TOOL_FENCED or reservation.status != "pending":
            raise ExternalToolAccountingHoldInvariantError("Hold requires a pending fenced reservation")
        if gateway_key.external_tool_fence_state not in (FENCE_ACTIVE, FENCE_HELD):
            raise ExternalToolAccountingHoldInvariantError("Hold requires an active fence")
        if gateway_key.external_tool_fence_reservation_id != reservation.id:
            raise ExternalToolAccountingHoldInvariantError("Hold fence reservation mismatch")
        if gateway_key.external_tool_fence_request_id != reservation.request_id:
            raise ExternalToolAccountingHoldInvariantError("Hold fence request mismatch")
        if reservation.external_tool_provider is None or reservation.external_tool_route_id is None:
            raise ExternalToolAccountingHoldInvariantError("Hold requires bound route facts")

    @staticmethod
    def _validate_locked_candidate(ledger, reservation, gateway_key) -> None:
        if gateway_key.external_tool_fence_state != FENCE_HELD:
            raise ExternalToolAccountingHoldInvariantError("Reconciliation requires a held fence")
        if reservation.status != "pending" or reservation.quota_mode != _EXTERNAL_TOOL_FENCED:
            raise ExternalToolAccountingHoldInvariantError("Reconciliation requires a pending fenced reservation")
        if (
            ledger.quota_reservation_id != reservation.id
            or ledger.gateway_key_id != gateway_key.id
            or gateway_key.external_tool_fence_reservation_id != reservation.id
            or gateway_key.external_tool_fence_request_id != reservation.request_id
            or ledger.request_id != reservation.request_id
            or ledger.endpoint != reservation.endpoint
            or ledger.provider != reservation.external_tool_provider
            or ledger.requested_model != reservation.requested_model
            or reservation.external_tool_route_id is None
        ):
            raise ExternalToolAccountingHoldInvariantError("Hold ledger ownership mismatch")
        if (
            gateway_key.cost_reserved_eur != reservation.reserved_cost_eur
            or gateway_key.tokens_reserved_total != reservation.reserved_tokens
            or gateway_key.requests_reserved_total != reservation.reserved_requests
        ):
            raise ExternalToolAccountingHoldInvariantError("Hold reservation counters are inconsistent")
        hold = (ledger.response_metadata or {}).get("external_tool_accounting_hold")
        if (
            not isinstance(hold, dict)
            or hold.get("version") != 1
            or hold.get("state") != "held"
            or hold.get("needs_reconciliation") is not True
            or ledger.accounting_status not in ("estimated", "interrupted")
            or ledger.success is not None
        ):
            raise ExternalToolAccountingHoldInvariantError("Ledger is not an unresolved hold")


def _validate_reconciliation_input(request: ExternalToolHoldReconciliationInput) -> None:
    if not isinstance(request.action, ExternalToolHoldAction):
        raise InvalidExternalToolAccountingHoldError("Unknown reconciliation action")
    if request.actor_admin_id is None or not isinstance(request.actor_admin_id, UUID):
        raise InvalidExternalToolAccountingHoldError("An admin actor is required")
    if not isinstance(request.reason, str) or not request.reason.strip() or len(request.reason) > 500:
        raise InvalidExternalToolAccountingHoldError("A bounded reconciliation reason is required")
    if request.action == ExternalToolHoldAction.FINALIZE_ACTUAL:
        if request.confirm_no_charge:
            raise InvalidExternalToolAccountingHoldError("No-charge confirmation is incompatible")
        if (
            not isinstance(request.actual_cost_eur, Decimal)
            or not request.actual_cost_eur.is_finite()
            or request.actual_cost_eur < 0
        ):
            raise InvalidExternalToolAccountingHoldError("Actual cost must be finite and non-negative")
        if (
            not isinstance(request.actual_total_tokens, int)
            or isinstance(request.actual_total_tokens, bool)
            or request.actual_total_tokens < 0
        ):
            raise InvalidExternalToolAccountingHoldError("Actual tokens must be non-negative")
        if not isinstance(request.success, bool):
            raise InvalidExternalToolAccountingHoldError("Provider outcome must be explicit")
    elif not request.confirm_no_charge:
        raise InvalidExternalToolAccountingHoldError("No-charge release requires explicit confirmation")


def _reconciliation_metadata(ledger) -> dict[str, object] | None:
    value = (ledger.response_metadata or {}).get("external_tool_accounting_reconciliation")
    return value if isinstance(value, dict) else None


def _reconciliation_matches(metadata, request) -> bool:
    if not isinstance(metadata, dict):
        return False
    return (
        metadata.get("action") == request.action.value
        and metadata.get("actor_admin_id") == str(request.actor_admin_id)
        and metadata.get("reason") == request.reason.strip()
        and metadata.get("actual_cost_eur")
        == (str(request.actual_cost_eur) if request.actual_cost_eur is not None else "0")
        and metadata.get("actual_total_tokens")
        == (request.actual_total_tokens if request.actual_total_tokens is not None else 0)
        and metadata.get("success")
        == (request.success if request.success is not None else False)
        and metadata.get("confirmed_no_charge") is request.confirm_no_charge
    )


def _terminal_metadata(
    ledger,
    *,
    action: str,
    actor_admin_id: UUID,
    reason: str,
    actual_cost_eur: Decimal,
    actual_total_tokens: int,
    success: bool,
    overrun_cost: bool,
    overrun_tokens: bool,
    confirmed_no_charge: bool = False,
) -> dict[str, object]:
    metadata = dict(ledger.response_metadata or {})
    hold = dict(metadata.get("external_tool_accounting_hold") or {})
    hold["needs_reconciliation"] = False
    hold["state"] = "reconciled"
    metadata["external_tool_accounting_hold"] = hold
    metadata["external_tool_accounting_reconciliation"] = {
        "version": 1,
        "action": action,
        "actor_admin_id": str(actor_admin_id),
        "reason": reason.strip(),
        "actual_cost_eur": str(actual_cost_eur),
        "actual_total_tokens": actual_total_tokens,
        "success": success,
        "cost_source": "operator_reconciliation",
        "confidence": "operator_asserted",
        "overrun_cost": overrun_cost,
        "overrun_tokens": overrun_tokens,
        "confirmed_no_charge": confirmed_no_charge,
    }
    return metadata


def _reconciliation_result(request, *, ledger, reservation, gateway_key, idempotent=False):
    return ExternalToolHoldReconciliationResult(
        reservation_id=reservation.id,
        usage_ledger_id=ledger.id,
        action=request.action.value,
        executed=request.execute,
        fence_state=gateway_key.external_tool_fence_state,
        reservation_status=reservation.status,
        accounting_status=ledger.accounting_status,
        actual_cost_eur=ledger.actual_cost_eur,
        actual_total_tokens=ledger.total_tokens,
        success=ledger.success,
        idempotent=idempotent,
    )

def _validate_input(value: ExternalToolAccountingHoldInput) -> None:
    if not isinstance(value.reason_code, ExternalToolHoldReasonCode):
        raise InvalidExternalToolAccountingHoldError("Unknown hold reason code")
    if not isinstance(value.evidence_quality, ExternalToolHoldEvidenceQuality):
        raise InvalidExternalToolAccountingHoldError("Unknown hold evidence quality")
    if not isinstance(value.streaming, bool):
        raise InvalidExternalToolAccountingHoldError("Streaming must be boolean")
    if not value.request_id or len(value.request_id) > 255:
        raise InvalidExternalToolAccountingHoldError("Request ID is invalid")


def _aware_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _ledger_matches_hold(
    ledger,
    *,
    reason_code: ExternalToolHoldReasonCode,
    evidence_quality: ExternalToolHoldEvidenceQuality,
    partial_total_tokens: int | None,
    estimated_cost_eur: Decimal | None,
) -> bool:
    hold = (ledger.response_metadata or {}).get("external_tool_accounting_hold")
    return (
        ledger.accounting_status in ("estimated", "interrupted")
        and ledger.success is None
        and isinstance(hold, dict)
        and hold.get("version") == 1
        and hold.get("state") == "held"
        and hold.get("reason_code") == reason_code.value
        and hold.get("evidence_quality") == evidence_quality.value
        and ledger.total_tokens == (partial_total_tokens or 0)
        and ledger.estimated_cost_eur == estimated_cost_eur
    )


def _projection(gateway_key, reservation, ledger):
    hold = (ledger.response_metadata or {}).get("external_tool_accounting_hold") or {}
    held_at = _parse_timestamp(hold.get("held_at"), ledger.created_at)
    return ExternalToolAccountingHoldProjection(
        gateway_key_id=gateway_key.id,
        reservation_id=reservation.id,
        usage_ledger_id=ledger.id,
        request_id=reservation.request_id,
        fence_state=gateway_key.external_tool_fence_state,
        accounting_status=ledger.accounting_status,
        reason_code=str(hold.get("reason_code", "")),
        evidence_quality=str(hold.get("evidence_quality", "")),
        held_at=held_at,
        created_at=ledger.created_at,
        expires_at=reservation.expires_at,
        provider=reservation.external_tool_provider or ledger.provider,
        endpoint=reservation.endpoint,
        requested_model=reservation.requested_model,
        reserved_cost_eur=reservation.reserved_cost_eur,
        reserved_tokens=reservation.reserved_tokens,
        reserved_requests=reservation.reserved_requests,
        partial_total_tokens=ledger.total_tokens or None,
        estimated_cost_eur=ledger.estimated_cost_eur,
    )


def _parse_timestamp(value: object, fallback: datetime) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return fallback
