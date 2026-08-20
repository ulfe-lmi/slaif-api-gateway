"""Safe input and projection types for external-tool accounting holds.

The hold contract deliberately carries identifiers, bounded accounting facts,
and low-cardinality state only.  Provider/tool bodies, URLs, arguments,
results, credentials, and operator evidence are not part of this API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class ExternalToolHoldReasonCode(StrEnum):
    """Closed set of safe reasons for an unresolved provider outcome."""

    MISSING_FINAL_USAGE = "missing_final_usage"
    MISSING_FINAL_COST = "missing_final_cost"
    AMBIGUOUS_FINAL_COST = "ambiguous_final_cost"
    INTERRUPTION_DISCONNECT = "interruption_disconnect"
    PROVIDER_ERROR_UNKNOWN_CHARGE = "provider_error_unknown_charge"


class ExternalToolHoldEvidenceQuality(StrEnum):
    """Quality of the bounded accounting facts available at hold time."""

    MISSING = "missing"
    PARTIAL_ESTIMATE = "partial_estimate"
    AMBIGUOUS = "ambiguous"


class ExternalToolHoldAction(StrEnum):
    """Allowed explicit operator reconciliation actions."""

    FINALIZE_ACTUAL = "finalize-actual"
    RELEASE_NO_CHARGE = "release-no-charge"


@dataclass(frozen=True, slots=True)
class ExternalToolAccountingHoldInput:
    """Flush-only request to place one durable accounting hold."""

    gateway_key_id: UUID
    reservation_id: UUID
    request_id: str
    reason_code: ExternalToolHoldReasonCode
    evidence_quality: ExternalToolHoldEvidenceQuality
    streaming: bool
    now: datetime
    partial_total_tokens: int | None = None
    estimated_cost_eur: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ExternalToolAccountingHoldProjection:
    """Safe projection of a committed or candidate accounting hold."""

    gateway_key_id: UUID
    reservation_id: UUID
    usage_ledger_id: UUID
    request_id: str
    fence_state: str
    accounting_status: str
    reason_code: str
    evidence_quality: str
    held_at: datetime
    created_at: datetime
    expires_at: datetime
    provider: str
    endpoint: str
    requested_model: str | None
    reserved_cost_eur: Decimal
    reserved_tokens: int
    reserved_requests: int
    partial_total_tokens: int | None
    estimated_cost_eur: Decimal | None


@dataclass(frozen=True, slots=True)
class ExternalToolHoldReconciliationInput:
    """Validated operator request; execution is still opt-in."""

    reservation_id: UUID
    action: ExternalToolHoldAction
    execute: bool
    actor_admin_id: UUID | None = None
    reason: str | None = None
    actual_cost_eur: Decimal | None = None
    actual_total_tokens: int | None = None
    success: bool | None = None
    confirm_no_charge: bool = False


@dataclass(frozen=True, slots=True)
class ExternalToolHoldReconciliationResult:
    """Safe dry-run or committed reconciliation result."""

    reservation_id: UUID
    usage_ledger_id: UUID
    action: str
    executed: bool
    fence_state: str
    reservation_status: str
    accounting_status: str
    actual_cost_eur: Decimal | None
    actual_total_tokens: int | None
    success: bool | None
    idempotent: bool = False


def safe_hold_metadata(
    *,
    reason_code: ExternalToolHoldReasonCode,
    evidence_quality: ExternalToolHoldEvidenceQuality,
    held_at: datetime,
) -> dict[str, object]:
    """Build the versioned, content-free metadata stored with a hold ledger."""

    return {
        "external_tool_accounting_hold": {
            "version": 1,
            "state": "held",
            "reason_code": reason_code.value,
            "needs_reconciliation": True,
            "evidence_quality": evidence_quality.value,
            "held_at": held_at.isoformat(),
        }
    }


def validate_partial_facts(
    *,
    partial_total_tokens: int | None,
    estimated_cost_eur: Decimal | None,
) -> None:
    """Reject unsafe or negative partial accounting facts before mutation."""

    if partial_total_tokens is not None and (
        isinstance(partial_total_tokens, bool)
        or not isinstance(partial_total_tokens, int)
        or partial_total_tokens < 0
    ):
        raise ValueError("partial_total_tokens must be a non-negative integer")
    if estimated_cost_eur is not None:
        if not isinstance(estimated_cost_eur, Decimal) or not estimated_cost_eur.is_finite():
            raise ValueError("estimated_cost_eur must be a finite Decimal")
        if estimated_cost_eur < 0:
            raise ValueError("estimated_cost_eur must be non-negative")
