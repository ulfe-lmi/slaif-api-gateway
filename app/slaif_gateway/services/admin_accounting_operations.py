"""Reviewed accounting-recovery operations for the admin console (216-a, G14).

Bounded admin surface over the EXISTING Core reconciliation services
(``ReservationReconciliationService`` and ``ExternalToolAccountingHoldService``)
and the read-only ``ExternalToolFenceService`` projection. The browser supplies
NO authority: the actor and session come from the admin session, the reviewed
targets/assertions come from the signed review token, and every apply re-loads
the exact selected rows (and their relevant linked rows) under canonical locks
BEFORE re-checking the reviewed source facts and BEFORE any mutation.

Four read-only candidate views and four reviewed recovery action families:

- expired pending reservations: reconcile one or an explicit bounded selection;
- external-tool accounting holds: finalize-actual or release-no-charge (single
  target, explicit operator assertions);
- provider-completed finalization-failed: reconcile one or an explicit bounded
  selection (stored authoritative evidence only, no GUI cost override);
- unresolved external-tool fences: read-only inspection only - there is NO
  generic release/reset/unblock action.

There is NO duplicated accounting engine, NO ad hoc SQL settlement, NO provider
evidence uploader, and NO usage reset. Core counter arithmetic and eligibility
checks are preserved by reusing the existing single-target apply methods. The
apply lock order mirrors Core: all selected row locks first (reservations for
expired; ledgers then linked reservations for provider-completed; the single
hold ledger, reservation, and key), then every DISTINCT linked gateway key in
ascending key UUID order via the existing fresh (populate_existing) key lock
BEFORE any source check or settlement. Row locks therefore always precede key
locks, and key locks are always acquired in the same deterministic order for
every caller selection, so one key's lock is never held while another row's
prerequisite is acquired in an arbitrary browser order and disjoint selections
over the same keys can never invert key-lock acquisition. The fresh key lock
also refreshes cached key totals; Core's per-row quota re-lock then reuses the
transaction's locked fresh instance, and the key's running balances stay OUT
of every fingerprint, so unrelated ordinary traffic cannot invalidate an
otherwise valid review. A single
already-resolved (idempotent) target is accepted with no duplicate effect; ANY
included target whose relevant source facts changed since the preview refuses
and rolls back the WHOLE selected batch.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolHoldAction,
    ExternalToolHoldReconciliationInput,
)
from slaif_gateway.services.external_tool_fence import ExternalToolFenceService
from slaif_gateway.services.external_tool_hold import (
    ExternalToolAccountingHoldError,
    ExternalToolAccountingHoldService,
)
from slaif_gateway.services.reconciliation_errors import (
    ProviderCompletedRecoveryAlreadyReconciledError,
    ReconciliationError,
)
from slaif_gateway.services.reservation_reconciliation import (
    ReservationReconciliationService,
)

# 216-a: the GUI reviewed-selection ceiling (deliberate; the CLI positive
# limits are unchanged). One action family per operation.
MAX_REVIEWED_TARGETS = 200

# Review action families (mirror the review-intent accounting purposes).
ACTION_EXPIRED = "expired"
ACTION_PROVIDER_COMPLETED = "provider_completed"
ACTION_HOLD_FINALIZE = "hold_finalize_actual"
ACTION_HOLD_RELEASE = "hold_release_no_charge"

# Per-target outcome labels (honest distinction; never a partial "success").
OUTCOME_SETTLED = "settled"
OUTCOME_ALREADY_RESOLVED = "already_resolved"
# Preview-only proposal labels.
PREVIEW_ELIGIBLE = "eligible"
PREVIEW_ALREADY_RESOLVED = "already_resolved"
PREVIEW_REFUSED = "refused"

# Intended-action labels (plain language). Dry-run result statuses are
# CURRENT facts: an expired dry-run reports new_status=pending, and
# provider/hold dry-runs report the current accounting/reservation state.
# These labels state what applying WOULD do; they never claim a state.
ACTION_LABEL_EXPIRED = (
    "Release the reserved cost, tokens and requests; mark the reservation expired"
)
ACTION_LABEL_PROVIDER = (
    "Finalize the usage from the stored provider evidence (no cost override)"
)
ACTION_LABEL_HOLD_FINALIZE = (
    "Finalize the hold with your operator-asserted actuals "
    "(operator_asserted, never provider-verified)"
)
ACTION_LABEL_HOLD_RELEASE = (
    "Release the hold with no charge (explicit no-charge confirmation sealed)"
)


class AccountingOperationError(ReconciliationError):
    """Safe base error for reviewed accounting operations."""

    status_code = 409
    error_code = "accounting_operation_error"
    message = "Accounting recovery operation failed"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        # Base contract: ReconciliationError.__init__ assigns the
        # ``self.safe_message`` INSTANCE attribute; a subclass read-only
        # property with the same name would make that assignment raise
        # AttributeError (every changed/invalid refusal path -> 500).
        super().__init__(message or self.message)
        self.code = code or self.error_code


class AccountingSelectionError(AccountingOperationError):
    """The reviewed selection itself is invalid (empty, oversized, not unique)."""

    status_code = 400
    error_code = "accounting_selection_invalid"
    message = "The reviewed accounting selection is invalid"


class AccountingSourceChangedError(AccountingOperationError):
    """A reviewed row changed since the preview; the apply must be refused."""

    status_code = 409
    error_code = "accounting_source_changed"
    message = "A reviewed accounting row changed since the preview"


@dataclass(frozen=True, slots=True)
class AccountingReviewTarget:
    """One reviewed exact target: its id plus the reviewed source fingerprint."""

    id: uuid.UUID
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AccountingTargetPreview:
    """Safe preview of one selected target: current facts and the proposal.

    ``observed``/``proposed`` carry the remaining readable metadata; the
    numeric readouts (tokens/requests/cost) are explicit fields so the
    review page can render separately sortable request/token columns.
    Core dry-run statuses are CURRENT facts and stay in ``observed`` only:
    a preview never presents them as a post-apply state.
    """

    id: uuid.UUID
    fingerprint: str
    proposal: str  # PREVIEW_ELIGIBLE | PREVIEW_ALREADY_RESOLVED | PREVIEW_REFUSED
    safe_detail: str
    action_label: str  # the intended action (never a state claim)
    observed: dict[str, Any]
    proposed: dict[str, Any]
    observed_tokens: int | None
    observed_requests: int | None
    observed_cost_eur: str | None
    proposed_tokens: int | None
    proposed_requests: int | None
    proposed_cost_eur: str | None


@dataclass(frozen=True, slots=True)
class AccountingTargetOutcome:
    """Per-target apply outcome (settled or already-resolved)."""

    id: uuid.UUID
    status: str
    safe_detail: str


@dataclass(frozen=True, slots=True)
class AccountingOperationResult:
    """Classified result of one applied reviewed accounting operation."""

    action: str
    target_count: int
    settled_count: int
    already_resolved_count: int
    committed: bool
    unconfirmed: bool
    outcomes: tuple[AccountingTargetOutcome, ...] = field(default_factory=tuple)


def _digest(parts: Sequence[Any]) -> str:
    normalized = "\x1f".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _metadata_facts(response_metadata: Mapping[str, Any] | None) -> tuple[str, str]:
    metadata = response_metadata or {}
    return (
        str(metadata.get("needs_reconciliation", "")),
        str(metadata.get("recovery_state", "")),
    )


def fingerprint_expired_reservation(reservation: Any) -> str:
    """Content-free relevant-source fingerprint for one expired reservation.

    Binds the target's identity AND its relevant relationships (gateway key and
    request ids) plus the reserved balances and lifecycle facts - but never the
    gateway key's running totals, so unrelated ordinary traffic cannot
    invalidate an otherwise valid review.
    """
    return _digest(
        [
            "expired",
            str(reservation.id),
            str(reservation.gateway_key_id),
            reservation.request_id,
            reservation.status,
            str(reservation.reserved_cost_eur),
            reservation.reserved_tokens,
            reservation.reserved_requests,
            reservation.quota_mode,
            reservation.expires_at.isoformat() if reservation.expires_at is not None else "",
        ]
    )


def fingerprint_provider_completed(ledger: Any, reservation: Any) -> str:
    """Content-free relevant-source fingerprint for one provider-completed row.

    Binds the ledger's stored authoritative evidence AND the linked reservation
    facts (status, reserved balances, gateway key / request ids) plus the
    recovery metadata - but never the gateway key's running totals.
    """
    needs_reconciliation, recovery_state = _metadata_facts(ledger.response_metadata)
    return _digest(
        [
            "provider_completed",
            str(ledger.id),
            ledger.accounting_status,
            str(ledger.actual_cost_eur),
            ledger.total_tokens,
            ledger.prompt_tokens,
            ledger.completion_tokens,
            str(ledger.quota_reservation_id),
            str(ledger.gateway_key_id),
            ledger.request_id,
            needs_reconciliation,
            recovery_state,
            # linked reservation facts:
            str(reservation.id),
            str(reservation.gateway_key_id),
            reservation.status,
            str(reservation.reserved_cost_eur),
            reservation.reserved_tokens,
            reservation.reserved_requests,
            reservation.request_id,
        ]
    )


def fingerprint_hold(reservation: Any, ledger: Any, gateway_key: Any) -> str:
    """Content-free relevant-source fingerprint for one held external-tool row.

    Binds the reservation, the held ledger, and the fence state on the gateway
    key - the exact facts Core's hold reconciliation re-validates - but never
    the gateway key's running reserved/used totals.
    """
    return _digest(
        [
            "hold",
            str(reservation.id),
            str(reservation.gateway_key_id),
            reservation.request_id,
            reservation.status,
            reservation.quota_mode,
            str(reservation.reserved_cost_eur),
            reservation.reserved_tokens,
            reservation.reserved_requests,
            str(ledger.id),
            ledger.accounting_status,
            str(ledger.success),
            str(gateway_key.external_tool_fence_state),
        ]
    )


def _validate_selection(targets: Sequence[AccountingReviewTarget]) -> None:
    if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= MAX_REVIEWED_TARGETS:
        raise AccountingSelectionError(
            "Select at least one and at most 200 reviewed rows for one operation"
        )
    seen: set[uuid.UUID] = set()
    for target in targets:
        if not isinstance(target.id, uuid.UUID) or not isinstance(target.fingerprint, str):
            raise AccountingSelectionError("Reviewed target is malformed")
        if target.id in seen:
            raise AccountingSelectionError("Reviewed selection contains duplicate rows")
        seen.add(target.id)


def _validate_id_sequence(ids: Sequence[uuid.UUID]) -> None:
    if not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= MAX_REVIEWED_TARGETS:
        raise AccountingSelectionError(
            "Select at least one and at most 200 reviewed rows for one operation"
        )
    for value in ids:
        if not isinstance(value, uuid.UUID):
            raise AccountingSelectionError("Reviewed target id is malformed")
    if len(set(ids)) != len(ids):
        raise AccountingSelectionError("Selection contains duplicate rows")


def _aware_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _validate_hold_assertions(
    action: ExternalToolHoldAction,
    confirm_no_charge: bool,
    actual_cost_eur: Decimal | None,
    actual_total_tokens: int | None,
    success: bool | None,
) -> None:
    """Bridge-level mirror of the shared Core mutually-exclusive intent law.

    The explicit no-charge choice is an operator decision, never inferred
    from the selected mode, and conflicting branches refuse BEFORE any read
    or write. Core's shared validator re-enforces the same law at execution.
    """
    if not isinstance(confirm_no_charge, bool):
        raise AccountingSelectionError("The no-charge confirmation is invalid")
    if action is ExternalToolHoldAction.RELEASE_NO_CHARGE:
        if not confirm_no_charge:
            raise AccountingSelectionError(
                "Release with no charge requires explicit no-charge confirmation"
            )
        if actual_cost_eur is not None or actual_total_tokens is not None or success is not None:
            raise AccountingSelectionError(
                "Release with no charge cannot include actual cost, token, or outcome values"
            )
        return
    # FINALIZE_ACTUAL
    if confirm_no_charge:
        raise AccountingSelectionError(
            "Finalize with actuals cannot include a no-charge confirmation"
        )
    if (
        not isinstance(actual_cost_eur, Decimal)
        or not actual_cost_eur.is_finite()
        or actual_cost_eur < 0
        or isinstance(actual_total_tokens, bool)
        or not isinstance(actual_total_tokens, int)
        or actual_total_tokens < 0
        or not isinstance(success, bool)
    ):
        raise AccountingSelectionError(
            "Finalize with actuals requires explicit finite non-negative cost, "
            "non-negative integer tokens, and an explicit outcome"
        )


def _summarize(
    action: str, target_count: int, outcomes: Sequence[AccountingTargetOutcome]
) -> AccountingOperationResult:
    settled = sum(1 for outcome in outcomes if outcome.status == OUTCOME_SETTLED)
    already = sum(1 for outcome in outcomes if outcome.status == OUTCOME_ALREADY_RESOLVED)
    return AccountingOperationResult(
        action=action,
        target_count=target_count,
        settled_count=settled,
        already_resolved_count=already,
        committed=True,
        unconfirmed=False,
        outcomes=tuple(outcomes),
    )


class AdminAccountingOperationsService:
    """Reviewed exact-target bridge over the existing Core reconciliation services.

    Every method runs on the caller's session. The read views and previews
    mutate nothing. The apply methods assume an active caller transaction (the
    API opens ``session.begin()``); they raise on any refused/changed target so
    the whole selected mutation rolls back atomically.
    """

    def __init__(
        self,
        *,
        reservation_service: ReservationReconciliationService,
        hold_service: ExternalToolAccountingHoldService,
        fence_service: ExternalToolFenceService,
        quota_reservations_repository: QuotaReservationsRepository,
        usage_ledger_repository: UsageLedgerRepository,
        keys_repository: GatewayKeysRepository,
    ) -> None:
        self._reservation = reservation_service
        self._hold = hold_service
        self._fence = fence_service
        self._quota = quota_reservations_repository
        self._usage = usage_ledger_repository
        self._keys = keys_repository

    # -- read-only candidate views ------------------------------------------------
    async def list_expired_candidates(self, *, limit: int = 100) -> list[Any]:
        return await self._reservation.list_expired_pending_reservations(limit=limit)

    async def list_fence_candidates(self, *, limit: int = 100) -> list[Any]:
        return await self._fence.list_unresolved_fences(limit=limit)

    async def list_hold_candidates(self, *, limit: int = 100) -> list[Any]:
        return await self._hold.list_holds(limit=limit)

    async def list_provider_completed_candidates(
        self,
        *,
        limit: int = 100,
        provider: str | None = None,
        model: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
    ) -> list[Any]:
        return await self._reservation.list_provider_completed_recovery_rows(
            limit=limit,
            provider=provider,
            model=model,
            gateway_key_id=gateway_key_id,
        )

    # -- previews (dry_run=True / execute=False; write nothing) -------------------
    async def preview_expired(
        self,
        reservation_ids: Sequence[uuid.UUID],
        *,
        now: datetime | None = None,
    ) -> list[AccountingTargetPreview]:
        _validate_id_sequence(reservation_ids)
        checked_at = _aware_now(now)
        previews: list[AccountingTargetPreview] = []
        for reservation_id in reservation_ids:
            reservation = await self._quota.get_reservation_by_id(reservation_id)
            if reservation is None:
                previews.append(_refused_preview(reservation_id, "reservation_not_found"))
                continue
            fingerprint = fingerprint_expired_reservation(reservation)
            observed = {
                "status": reservation.status,
                "quota_mode": reservation.quota_mode,
                "expires_at": reservation.expires_at.strftime("%Y-%m-%d %H:%M:%S")
                if reservation.expires_at is not None
                else None,
            }
            try:
                result = await self._reservation.reconcile_expired_pending_reservation(
                    reservation_id,
                    now=checked_at,
                    dry_run=True,
                )
            except ReconciliationError as exc:
                proposal, detail = _expired_refusal(reservation, exc)
            else:
                previews.append(
                    AccountingTargetPreview(
                        id=reservation_id,
                        fingerprint=fingerprint,
                        proposal=PREVIEW_ELIGIBLE,
                        safe_detail="would_release",
                        # The dry-run new_status is the CURRENT pending
                        # status (already in observed); the released
                        # quantities are what applying would write.
                        action_label=ACTION_LABEL_EXPIRED,
                        observed=observed,
                        proposed={},
                        observed_tokens=reservation.reserved_tokens,
                        observed_requests=reservation.reserved_requests,
                        observed_cost_eur=str(reservation.reserved_cost_eur),
                        proposed_tokens=result.released_tokens,
                        proposed_requests=result.released_requests,
                        proposed_cost_eur=str(result.released_cost_eur),
                    )
                )
                continue
            previews.append(
                AccountingTargetPreview(
                    id=reservation_id,
                    fingerprint=fingerprint,
                    proposal=proposal,
                    safe_detail=detail,
                    action_label=ACTION_LABEL_EXPIRED,
                    observed=observed,
                    proposed={},
                    observed_tokens=reservation.reserved_tokens,
                    observed_requests=reservation.reserved_requests,
                    observed_cost_eur=str(reservation.reserved_cost_eur),
                    proposed_tokens=None,
                    proposed_requests=None,
                    proposed_cost_eur=None,
                )
            )
        return previews

    async def preview_provider_completed(
        self,
        usage_ledger_ids: Sequence[uuid.UUID],
        *,
        now: datetime | None = None,
    ) -> list[AccountingTargetPreview]:
        _validate_id_sequence(usage_ledger_ids)
        previews: list[AccountingTargetPreview] = []
        for usage_ledger_id in usage_ledger_ids:
            ledger = await self._usage.get_usage_record_by_id(usage_ledger_id)
            if ledger is None or ledger.quota_reservation_id is None:
                previews.append(_refused_preview(usage_ledger_id, "ledger_not_found"))
                continue
            reservation = await self._quota.get_reservation_by_id(ledger.quota_reservation_id)
            if reservation is None:
                previews.append(_refused_preview(usage_ledger_id, "reservation_not_found"))
                continue
            fingerprint = fingerprint_provider_completed(ledger, reservation)
            observed = {
                "accounting_status": ledger.accounting_status,
                "provider": ledger.provider,
            }
            try:
                result = await self._reservation.reconcile_provider_completed_recovery(
                    usage_ledger_id=usage_ledger_id,
                    dry_run=True,
                    now=_aware_now(now),
                )
            except ReconciliationError as exc:
                proposal, detail = _provider_completed_refusal(ledger, exc)
            else:
                previews.append(
                    AccountingTargetPreview(
                        id=usage_ledger_id,
                        fingerprint=fingerprint,
                        proposal=PREVIEW_ELIGIBLE,
                        safe_detail="would_finalize",
                        # The dry-run new_accounting_status is the CURRENT
                        # state (already in observed); the used quantities
                        # come from the stored evidence applying would write.
                        action_label=ACTION_LABEL_PROVIDER,
                        observed=observed,
                        proposed={},
                        observed_tokens=ledger.total_tokens,
                        observed_requests=None,
                        observed_cost_eur=str(ledger.actual_cost_eur)
                        if ledger.actual_cost_eur is not None
                        else None,
                        proposed_tokens=result.used_tokens,
                        proposed_requests=None,
                        proposed_cost_eur=str(result.used_cost_eur)
                        if result.used_cost_eur is not None
                        else None,
                    )
                )
                continue
            previews.append(
                AccountingTargetPreview(
                    id=usage_ledger_id,
                    fingerprint=fingerprint,
                    proposal=proposal,
                    safe_detail=detail,
                    action_label=ACTION_LABEL_PROVIDER,
                    observed=observed,
                    proposed={},
                    observed_tokens=ledger.total_tokens,
                    observed_requests=None,
                    observed_cost_eur=str(ledger.actual_cost_eur)
                    if ledger.actual_cost_eur is not None
                    else None,
                    proposed_tokens=None,
                    proposed_requests=None,
                    proposed_cost_eur=None,
                )
            )
        return previews

    async def preview_hold(
        self,
        reservation_id: uuid.UUID,
        *,
        action: ExternalToolHoldAction,
        actual_cost_eur: Decimal | None,
        actual_total_tokens: int | None,
        success: bool | None,
        confirm_no_charge: bool,
    ) -> AccountingTargetPreview:
        _validate_hold_assertions(
            action,
            confirm_no_charge,
            actual_cost_eur,
            actual_total_tokens,
            success,
        )
        reservation = await self._quota.get_reservation_by_id(reservation_id)
        ledger = await self._hold_ledger_for_reservation(reservation_id)
        gateway_key = (
            await self._keys.get_gateway_key_by_id(reservation.gateway_key_id)
            if reservation is not None
            else None
        )
        if reservation is None or ledger is None or gateway_key is None:
            return _refused_preview(reservation_id, "hold_not_found")
        fingerprint = fingerprint_hold(reservation, ledger, gateway_key)
        observed = {
            "fence_state": gateway_key.external_tool_fence_state,
            "accounting_status": ledger.accounting_status,
        }
        input_ = ExternalToolHoldReconciliationInput(
            reservation_id=reservation_id,
            action=action,
            execute=False,
            actual_cost_eur=actual_cost_eur,
            actual_total_tokens=actual_total_tokens,
            success=success,
            confirm_no_charge=confirm_no_charge,
        )
        try:
            # execute=False writes nothing and reports CURRENT state only;
            # the rejection (if any) is the information the preview needs.
            await self._hold.reconcile(input_)
        except ExternalToolAccountingHoldError as exc:
            proposal, detail = _hold_refusal(exc)
            return AccountingTargetPreview(
                id=reservation_id,
                fingerprint=fingerprint,
                proposal=proposal,
                safe_detail=detail,
                action_label=(
                    ACTION_LABEL_HOLD_FINALIZE
                    if action is ExternalToolHoldAction.FINALIZE_ACTUAL
                    else ACTION_LABEL_HOLD_RELEASE
                ),
                observed=observed,
                proposed={},
                observed_tokens=reservation.reserved_tokens,
                observed_requests=reservation.reserved_requests,
                observed_cost_eur=str(reservation.reserved_cost_eur),
                proposed_tokens=None,
                proposed_requests=None,
                proposed_cost_eur=None,
            )
        # The dry-run accounting/reservation statuses are CURRENT facts
        # (already in observed) and are never presented as post-apply state.
        if action is ExternalToolHoldAction.FINALIZE_ACTUAL:
            # Explicit operator-asserted actuals (operator_asserted, never
            # provider-verified) are what applying would write.
            proposed: dict[str, Any] = {"proposed_success": success}
            proposed_tokens = actual_total_tokens
            proposed_requests: int | None = None
            proposed_cost_eur = str(actual_cost_eur)
        else:
            # Release with no charge: the reserved amounts are what applying
            # would release (no actuals asserted, no zero defaults).
            proposed = {}
            proposed_tokens = reservation.reserved_tokens
            proposed_requests = reservation.reserved_requests
            proposed_cost_eur = str(reservation.reserved_cost_eur)
        return AccountingTargetPreview(
            id=reservation_id,
            fingerprint=fingerprint,
            proposal=PREVIEW_ELIGIBLE,
            safe_detail="would_reconcile",
            action_label=(
                ACTION_LABEL_HOLD_FINALIZE
                if action is ExternalToolHoldAction.FINALIZE_ACTUAL
                else ACTION_LABEL_HOLD_RELEASE
            ),
            observed=observed,
            proposed=proposed,
            observed_tokens=reservation.reserved_tokens,
            observed_requests=reservation.reserved_requests,
            observed_cost_eur=str(reservation.reserved_cost_eur),
            proposed_tokens=proposed_tokens,
            proposed_requests=proposed_requests,
            proposed_cost_eur=proposed_cost_eur,
        )

    # -- applies (single caller transaction; raise on refused/changed) -----------
    async def apply_expired(
        self,
        *,
        targets: Sequence[AccountingReviewTarget],
        actor_admin_id: uuid.UUID,
        reason: str,
        now: datetime | None = None,
    ) -> AccountingOperationResult:
        _validate_selection(targets)
        checked_at = _aware_now(now)
        expected = {target.id: target.fingerprint for target in targets}
        # Fresh canonical locks on every selected reservation BEFORE any source
        # comparison or mutation (all row locks precede any key lock).
        rows = await self._quota.get_reservations_by_ids_for_update(
            [target.id for target in targets]
        )
        loaded = {row.id: row for row in rows}
        if len(loaded) != len(expected):
            raise AccountingSourceChangedError("A reviewed reservation is no longer present")
        # Distinct linked gateway keys, ascending key UUID: after ALL selected
        # row locks and BEFORE any source check or settlement (see module
        # docstring). The fresh lock refreshes cached key totals; Core's
        # per-row quota re-lock reuses these locked fresh instances.
        for gateway_key_id in sorted({row.gateway_key_id for row in rows}):
            if await self._keys.get_gateway_key_for_update(gateway_key_id) is None:
                raise AccountingSourceChangedError(
                    "A reviewed reservation's gateway key is no longer present"
                )
        # Source comparison is TWO-PHASE: every included row's reviewed
        # fingerprint is checked BEFORE Core is called for ANY row, so one
        # changed row refuses the WHOLE selection (no settled/already mix).
        outcomes: list[AccountingTargetOutcome] = []
        pending_rows: list[Any] = []
        for reservation in rows:  # ascending id: deterministic Core-consistent order
            if fingerprint_expired_reservation(reservation) != expected[reservation.id]:
                raise AccountingSourceChangedError(
                    "A reviewed reservation's source facts changed since the preview"
                )
            if reservation.status != "pending":
                # Unchanged terminal state: a safe already-resolved no-op.
                outcomes.append(
                    AccountingTargetOutcome(
                        reservation.id, OUTCOME_ALREADY_RESOLVED, "already_terminal"
                    )
                )
                continue
            pending_rows.append(reservation)
        for reservation in pending_rows:
            await self._reservation.reconcile_expired_pending_reservation(
                reservation.id,
                now=checked_at,
                dry_run=False,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
            outcomes.append(AccountingTargetOutcome(reservation.id, OUTCOME_SETTLED, "released"))
        return _summarize(ACTION_EXPIRED, len(expected), outcomes)

    async def apply_provider_completed(
        self,
        *,
        targets: Sequence[AccountingReviewTarget],
        actor_admin_id: uuid.UUID,
        reason: str,
        now: datetime | None = None,
    ) -> AccountingOperationResult:
        _validate_selection(targets)
        checked_at = _aware_now(now)
        expected = {target.id: target.fingerprint for target in targets}
        # Fresh canonical locks on every selected ledger (Core locks ledger
        # first), then the linked reservations (Core locks reservation second).
        ledgers = await self._usage.get_usage_records_by_ids_for_update(
            [target.id for target in targets]
        )
        loaded = {row.id: row for row in ledgers}
        if len(loaded) != len(expected):
            raise AccountingSourceChangedError(
                "A reviewed provider-completed row is no longer present"
            )
        reservation_ids = {
            row.quota_reservation_id for row in ledgers if row.quota_reservation_id is not None
        }
        if len(reservation_ids) != len(ledgers):
            raise AccountingSourceChangedError(
                "A reviewed provider-completed row lost its linked reservation"
            )
        reservations = {
            row.id: row
            for row in await self._quota.get_reservations_by_ids_for_update(list(reservation_ids))
        }
        # Distinct linked gateway keys (ledgers and reservations), ascending
        # key UUID: after ALL selected row locks and BEFORE any source check
        # or settlement (see module docstring). The fresh lock refreshes
        # cached key totals; Core's per-row quota re-lock reuses these locked
        # fresh instances.
        for gateway_key_id in sorted(
            {row.gateway_key_id for row in ledgers}
            | {reservation.gateway_key_id for reservation in reservations.values()}
        ):
            if await self._keys.get_gateway_key_for_update(gateway_key_id) is None:
                raise AccountingSourceChangedError(
                    "A reviewed provider-completed row's gateway key is no longer present"
                )
        # Source comparison is TWO-PHASE: every included row's reviewed
        # fingerprint is checked BEFORE Core is called for ANY row, so one
        # changed row refuses the WHOLE selection (no settled/already mix).
        outcomes: list[AccountingTargetOutcome] = []
        pending_ledgers: list[Any] = []
        for ledger in ledgers:  # ascending id: deterministic Core-consistent order
            reservation = reservations.get(ledger.quota_reservation_id)
            if reservation is None:
                raise AccountingSourceChangedError(
                    "A reviewed provider-completed row lost its linked reservation"
                )
            if fingerprint_provider_completed(ledger, reservation) != expected[ledger.id]:
                raise AccountingSourceChangedError(
                    "A reviewed provider-completed row's source facts changed since the preview"
                )
            if ledger.accounting_status == "finalized":
                outcomes.append(
                    AccountingTargetOutcome(
                        ledger.id, OUTCOME_ALREADY_RESOLVED, "already_finalized"
                    )
                )
                continue
            pending_ledgers.append(ledger)
        for ledger in pending_ledgers:
            try:
                await self._reservation.reconcile_provider_completed_recovery(
                    usage_ledger_id=ledger.id,
                    dry_run=False,
                    actor_admin_id=actor_admin_id,
                    reason=reason,
                    now=checked_at,
                )
            except ProviderCompletedRecoveryAlreadyReconciledError:
                outcomes.append(
                    AccountingTargetOutcome(
                        ledger.id, OUTCOME_ALREADY_RESOLVED, "already_finalized"
                    )
                )
                continue
            outcomes.append(AccountingTargetOutcome(ledger.id, OUTCOME_SETTLED, "finalized"))
        return _summarize(ACTION_PROVIDER_COMPLETED, len(expected), outcomes)

    async def apply_hold(
        self,
        *,
        target: AccountingReviewTarget,
        action: ExternalToolHoldAction,
        actual_cost_eur: Decimal | None,
        actual_total_tokens: int | None,
        success: bool | None,
        confirm_no_charge: bool,
        actor_admin_id: uuid.UUID,
        reason: str,
    ) -> AccountingOperationResult:
        if not isinstance(target, AccountingReviewTarget):
            raise AccountingSelectionError("Hold review must select exactly one row")
        _validate_hold_assertions(
            action,
            confirm_no_charge,
            actual_cost_eur,
            actual_total_tokens,
            success,
        )
        # Find the linked ledger (plain read, matching Core's pre-read), then
        # acquire fresh canonical locks in Core's ledger -> reservation -> key
        # order BEFORE any source comparison or mutation.
        linked = await self._usage.get_usage_records_by_reservation_id(target.id)
        if not linked:
            raise AccountingSourceChangedError("The reviewed hold ledger is no longer present")
        ledger_rows = await self._usage.get_usage_records_by_ids_for_update([linked[0].id])
        if not ledger_rows:
            # The plain pre-read saw the linked ledger but the fresh locked
            # read no longer does (row vanished): refuse safely BEFORE any
            # indexing or Core call, with the existing safe error.
            raise AccountingSourceChangedError(
                "The reviewed hold ledger is no longer present"
            )
        reservation_rows = await self._quota.get_reservations_by_ids_for_update([target.id])
        if not reservation_rows:
            raise AccountingSourceChangedError("The reviewed hold reservation is no longer present")
        ledger = ledger_rows[0]
        reservation = reservation_rows[0]
        key_rows = await self._keys.get_gateway_key_for_update(reservation.gateway_key_id)
        if key_rows is None:
            raise AccountingSourceChangedError("The reviewed hold gateway key is no longer present")
        if fingerprint_hold(reservation, ledger, key_rows) != target.fingerprint:
            raise AccountingSourceChangedError(
                "The reviewed hold's source facts changed since the preview"
            )
        input_ = ExternalToolHoldReconciliationInput(
            reservation_id=target.id,
            action=action,
            execute=True,
            actor_admin_id=actor_admin_id,
            reason=reason,
            actual_cost_eur=actual_cost_eur,
            actual_total_tokens=actual_total_tokens,
            success=success,
            confirm_no_charge=confirm_no_charge,
        )
        result = await self._hold.reconcile(input_)
        status = OUTCOME_ALREADY_RESOLVED if result.idempotent else OUTCOME_SETTLED
        return _summarize(
            action.value,
            1,
            [AccountingTargetOutcome(target.id, status, "reconciled")],
        )

    # -- helpers ------------------------------------------------------------------
    async def _hold_ledger_for_reservation(self, reservation_id: uuid.UUID) -> Any:
        rows = await self._usage.get_usage_records_by_reservation_id(reservation_id)
        return rows[0] if rows else None


def _refused_preview(reservation_id: uuid.UUID, detail: str) -> AccountingTargetPreview:
    return AccountingTargetPreview(
        id=reservation_id,
        fingerprint="",
        proposal=PREVIEW_REFUSED,
        safe_detail=detail,
        action_label="",
        observed={},
        proposed={},
        observed_tokens=None,
        observed_requests=None,
        observed_cost_eur=None,
        proposed_tokens=None,
        proposed_requests=None,
        proposed_cost_eur=None,
    )


def _expired_refusal(reservation: Any, exc: ReconciliationError) -> tuple[str, str]:
    if getattr(exc, "error_code", None) == "reservation_not_pending":
        return PREVIEW_ALREADY_RESOLVED, "already_terminal"
    if getattr(exc, "error_code", None) == "reservation_not_expired":
        return PREVIEW_REFUSED, "not_expired"
    if reservation.quota_mode == "external_tool_fenced":
        return PREVIEW_REFUSED, "external_tool_fenced"
    message = str(exc)
    if "Provider completed" in message or "needs_reconciliation" in message:
        return PREVIEW_REFUSED, "needs_reconciliation"
    if getattr(exc, "error_code", None) == "stale_reservation_not_found":
        return PREVIEW_REFUSED, "reservation_not_found"
    return PREVIEW_REFUSED, "not_eligible"


def _provider_completed_refusal(ledger: Any, exc: ReconciliationError) -> tuple[str, str]:
    code = getattr(exc, "error_code", None)
    if isinstance(exc, ProviderCompletedRecoveryAlreadyReconciledError) or code in (
        "provider_completed_recovery_already_reconciled",
    ):
        return PREVIEW_ALREADY_RESOLVED, "already_finalized"
    if code == "provider_completed_recovery_not_found":
        return PREVIEW_REFUSED, "ledger_not_found"
    if code == "provider_completed_recovery_metadata_missing":
        return PREVIEW_REFUSED, "evidence_incomplete"
    if code == "provider_completed_recovery_not_repairable":
        return PREVIEW_REFUSED, "not_repairable"
    return PREVIEW_REFUSED, "not_eligible"


def _hold_refusal(exc: ExternalToolAccountingHoldError) -> tuple[str, str]:
    code = getattr(exc, "error_code", None)
    if code == "invalid_external_tool_accounting_hold":
        return PREVIEW_REFUSED, "invalid_assertions"
    return PREVIEW_REFUSED, "not_held"
