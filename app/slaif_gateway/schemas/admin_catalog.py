"""Safe DTOs for read-only admin provider, routing, pricing, and FX pages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AdminProviderSummary:
    id: uuid.UUID
    provider: str
    display_name: str
    enabled: bool
    base_url: str
    api_key_env_var: str


@dataclass(frozen=True, slots=True)
class AdminProviderListRow:
    id: uuid.UUID
    provider: str
    display_name: str
    kind: str
    enabled: bool
    base_url: str
    api_key_env_var: str
    timeout_seconds: int
    max_retries: int
    notes: str | None
    route_count: int | None
    pricing_rule_count: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminRouteSummary:
    id: uuid.UUID
    requested_model: str
    match_type: str
    endpoint: str
    upstream_model: str
    priority: int
    enabled: bool
    visible_in_models: bool


@dataclass(frozen=True, slots=True)
class AdminPricingRuleSummary:
    id: uuid.UUID
    upstream_model: str
    endpoint: str
    currency: str
    enabled: bool
    valid_from: datetime
    valid_until: datetime | None


@dataclass(frozen=True, slots=True)
class AdminProviderDetail(AdminProviderListRow):
    route_summaries: tuple[AdminRouteSummary, ...]
    pricing_summaries: tuple[AdminPricingRuleSummary, ...]


@dataclass(frozen=True, slots=True)
class AdminRouteListRow:
    id: uuid.UUID
    requested_model: str
    match_type: str
    endpoint: str
    provider: str
    upstream_model: str
    priority: int
    enabled: bool
    visible_in_models: bool
    supports_streaming: bool
    capabilities: dict[str, object]
    capabilities_summary: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminRouteDetail(AdminRouteListRow):
    provider_config: AdminProviderSummary | None


@dataclass(frozen=True, slots=True)
class AdminPricingRuleListRow:
    id: uuid.UUID
    provider: str
    upstream_model: str
    endpoint: str
    currency: str
    input_price_per_1m: Decimal | None
    cached_input_price_per_1m: Decimal | None
    output_price_per_1m: Decimal | None
    reasoning_price_per_1m: Decimal | None
    request_price: Decimal | None
    enabled: bool
    valid_from: datetime
    valid_until: datetime | None
    source_url: str | None
    notes: str | None
    metadata_summary: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminPricingRuleDetail(AdminPricingRuleListRow):
    provider_config: AdminProviderSummary | None


@dataclass(frozen=True, slots=True)
class AdminFxRateListRow:
    id: uuid.UUID
    base_currency: str
    quote_currency: str
    rate: Decimal
    source: str | None
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminFxRateDetail(AdminFxRateListRow):
    pass
