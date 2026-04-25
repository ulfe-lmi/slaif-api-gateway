"""Safe service-layer schemas for accounting finalization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ActualUsage:
    """Validated provider usage metadata without prompt or completion content."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    other_usage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActualCost:
    """Computed final cost metadata for a provider response."""

    actual_cost_eur: Decimal
    actual_cost_native: Decimal
    native_currency: str
    provider_reported_cost_native: Decimal | None = None
    provider_reported_currency: str | None = None


@dataclass(frozen=True, slots=True)
class FinalizedAccountingResult:
    """Safe result returned after successful usage accounting finalization."""

    usage_ledger_id: uuid.UUID
    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    estimated_cost_eur: Decimal
    actual_cost_eur: Decimal
    actual_cost_native: Decimal | None
    native_currency: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    accounting_status: str


@dataclass(frozen=True, slots=True)
class ProviderFailureAccountingResult:
    """Safe result returned after releasing a reservation for provider failure."""

    usage_ledger_id: uuid.UUID | None
    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    released: bool
    accounting_status: str
    error_type: str | None = None
    error_code: str | None = None
