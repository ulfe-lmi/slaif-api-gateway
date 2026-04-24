"""Service-layer schemas for gateway key workflows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class CreateGatewayKeyInput:
    """Input payload for creating a new gateway key."""

    owner_id: uuid.UUID
    valid_from: datetime
    valid_until: datetime
    cohort_id: uuid.UUID | None = None
    created_by_admin_id: uuid.UUID | None = None
    cost_limit_eur: Decimal | None = None
    token_limit_total: int | None = None
    request_limit_total: int | None = None
    allowed_models: list[str] = field(default_factory=list)
    allowed_endpoints: list[str] = field(default_factory=list)
    rate_limit_policy: dict[str, int] | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class CreatedGatewayKey:
    """One-time service result that contains plaintext key material."""

    gateway_key_id: uuid.UUID
    owner_id: uuid.UUID
    public_key_id: str
    display_prefix: str
    plaintext_key: str
    one_time_secret_id: uuid.UUID
    valid_from: datetime
    valid_until: datetime
