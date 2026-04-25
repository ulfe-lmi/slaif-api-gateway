"""Safe service-layer schemas for pricing lookup and FX conversion."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PricingLookupResult:
    """Enabled pricing rule selected for a provider/model/endpoint."""

    provider: str
    model: str
    endpoint: str
    currency: str
    input_price_per_1m: Decimal
    cached_input_price_per_1m: Decimal | None
    output_price_per_1m: Decimal
    reasoning_price_per_1m: Decimal | None
    pricing_rule_id: uuid.UUID | None
    valid_from: datetime
    valid_until: datetime | None


@dataclass(frozen=True, slots=True)
class FxConversionResult:
    """FX rate metadata used for conversion into EUR."""

    from_currency: str
    to_currency: str
    rate: Decimal
    fx_rate_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class ChatCostEstimate:
    """Maximum possible chat-completions cost estimate after policy and routing."""

    provider: str
    requested_model: str
    resolved_model: str
    native_currency: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_input_cost_native: Decimal
    estimated_output_cost_native: Decimal
    estimated_total_cost_native: Decimal
    estimated_total_cost_eur: Decimal
    pricing_rule_id: uuid.UUID | None
    fx_rate_id: uuid.UUID | None
