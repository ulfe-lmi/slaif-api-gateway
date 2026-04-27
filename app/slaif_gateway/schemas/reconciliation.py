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
