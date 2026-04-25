"""Safe service-layer schemas for quota reservations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class QuotaReservationRequest:
    """Validated quota reservation input without secrets or request payload content."""

    gateway_key_id: uuid.UUID
    request_id: str
    estimated_cost_eur: Decimal
    estimated_tokens: int
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class QuotaReservationResult:
    """Safe quota reservation result for API and service layers."""

    reservation_id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    reserved_cost_eur: Decimal
    reserved_tokens: int
    status: str
    expires_at: datetime

