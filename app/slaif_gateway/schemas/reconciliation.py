"""Safe schemas for quota reservation reconciliation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StaleReservationCandidate:
    """Safe projection of an expired pending quota reservation."""

    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    status: str
    reserved_cost_eur: Decimal
    reserved_tokens: int
    reserved_requests: int
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReservationReconciliationResult:
    """Result for one stale reservation reconciliation attempt."""

    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    previous_status: str
    new_status: str
    released_cost_eur: Decimal
    released_tokens: int
    released_requests: int
    ledger_created: bool
    audit_created: bool
    dry_run: bool


@dataclass(frozen=True, slots=True)
class ReservationReconciliationSummary:
    """Summary for a batch reconciliation operation."""

    checked_count: int
    candidate_count: int
    reconciled_count: int
    skipped_count: int
    dry_run: bool
    results: list[ReservationReconciliationResult] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProviderCompletedReconciliationCandidate:
    """Safe projection of a provider-completed finalization-failed row."""

    usage_ledger_id: uuid.UUID
    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    provider: str
    requested_model: str | None
    resolved_model: str | None
    endpoint: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_eur: Decimal
    actual_cost_eur: Decimal
    created_at: datetime
    recovery_state: str


@dataclass(frozen=True, slots=True)
class ProviderCompletedReconciliationResult:
    """Result for one provider-completed recovery reconciliation attempt."""

    usage_ledger_id: uuid.UUID
    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    previous_accounting_status: str
    new_accounting_status: str
    reservation_status: str
    used_cost_eur: Decimal
    used_tokens: int
    reconciled: bool
    dry_run: bool


@dataclass(frozen=True, slots=True)
class ProviderCompletedReconciliationSummary:
    """Summary for provider-completed recovery reconciliation."""

    checked_count: int
    candidate_count: int
    reconciled_count: int
    skipped_count: int
    dry_run: bool
    results: list[ProviderCompletedReconciliationResult] = field(default_factory=list)
