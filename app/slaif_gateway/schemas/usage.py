"""Safe usage reporting schemas."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class UsageSummaryRow:
    """Aggregated usage values for one reporting group."""

    grouping_key: str
    grouping_label: str | None
    request_count: int
    success_count: int
    failure_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    estimated_cost_eur: Decimal
    actual_cost_eur: Decimal
    provider_reported_cost: Decimal | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None


@dataclass(frozen=True, slots=True)
class UsageExportRow:
    """Safe usage ledger projection for CSV/JSON export."""

    created_at: datetime
    request_id: str
    gateway_key_id: uuid.UUID
    owner_id: uuid.UUID | None
    cohort_id: uuid.UUID | None
    provider: str
    requested_model: str | None
    resolved_model: str | None
    endpoint: str
    streaming: bool
    success: bool | None
    accounting_status: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    estimated_cost_eur: Decimal | None
    actual_cost_eur: Decimal | None
    native_currency: str | None
    upstream_request_id: str | None


@dataclass(frozen=True, slots=True)
class UsageReportFilters:
    """Shared filters for usage summary and export queries."""

    start_at: datetime | None = None
    end_at: datetime | None = None
    provider: str | None = None
    model: str | None = None
    owner_id: uuid.UUID | None = None
    cohort_id: uuid.UUID | None = None
    gateway_key_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class UsageDayGroup:
    """Normalized day group key."""

    day: date

    @property
    def key(self) -> str:
        return self.day.isoformat()
