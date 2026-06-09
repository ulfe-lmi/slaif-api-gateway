"""Service-layer schemas for gateway key authentication results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AuthenticatedGatewayKey:
    """Safe authentication context for a validated gateway key."""

    gateway_key_id: uuid.UUID
    owner_id: uuid.UUID
    cohort_id: uuid.UUID | None
    public_key_id: str
    status: str
    valid_from: datetime
    valid_until: datetime
    allow_all_models: bool
    allowed_models: tuple[str, ...]
    allow_all_endpoints: bool
    allowed_endpoints: tuple[str, ...]
    allowed_providers: tuple[str, ...] | None
    cost_limit_eur: Decimal | None
    token_limit_total: int | None
    request_limit_total: int | None
    rate_limit_policy: dict[str, int | None]
    cost_used_eur: Decimal = Decimal("0")
    tokens_used_total: int = 0
    cost_reserved_eur: Decimal = Decimal("0")
    tokens_reserved_total: int = 0
    responses_policy: dict[str, object] | None = None
    chat_streaming_live_burn_policy: dict[str, object] | None = None
    responses_streaming_live_burn_policy: dict[str, object] | None = None
    key_purpose: str = "standard"
    capability_policy_mode: str = "standard"
