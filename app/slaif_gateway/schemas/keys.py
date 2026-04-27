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
    rate_limit_policy: dict[str, int | None] | None = None
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
    rate_limit_policy: dict[str, int | None] | None = None


@dataclass(slots=True)
class SuspendGatewayKeyInput:
    """Input payload for suspending an active gateway key."""

    gateway_key_id: uuid.UUID
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class ActivateGatewayKeyInput:
    """Input payload for activating a suspended gateway key."""

    gateway_key_id: uuid.UUID
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class RevokeGatewayKeyInput:
    """Input payload for revoking an active or suspended gateway key."""

    gateway_key_id: uuid.UUID
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class UpdateGatewayKeyValidityInput:
    """Input payload for changing a gateway key validity window."""

    gateway_key_id: uuid.UUID
    valid_until: datetime
    valid_from: datetime | None = None
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class UpdateGatewayKeyLimitsInput:
    """Input payload for changing gateway key lifetime limits."""

    gateway_key_id: uuid.UUID
    cost_limit_eur: Decimal | None = None
    token_limit_total: int | None = None
    request_limit_total: int | None = None
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class UpdateGatewayKeyRateLimitsInput:
    """Input payload for changing Redis-backed operational rate limits."""

    gateway_key_id: uuid.UUID
    rate_limit_policy: dict[str, int | None] | None = None
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class ResetGatewayKeyUsageInput:
    """Input payload for administrative usage-counter repair/reset."""

    gateway_key_id: uuid.UUID
    reset_used_counters: bool = True
    reset_reserved_counters: bool = False
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None


@dataclass(slots=True)
class RotateGatewayKeyInput:
    """Input payload for rotating a gateway key without sending email."""

    gateway_key_id: uuid.UUID
    actor_admin_id: uuid.UUID | None = None
    reason: str | None = None
    revoke_old_key: bool = True
    new_valid_from: datetime | None = None
    new_valid_until: datetime | None = None
    preserve_limits: bool = True
    preserve_allowed_models: bool = True
    preserve_allowed_endpoints: bool = True
    preserve_rate_limit_policy: bool = True


@dataclass(frozen=True, slots=True)
class GatewayKeyManagementResult:
    """Safe metadata returned from gateway key management operations."""

    gateway_key_id: uuid.UUID
    public_key_id: str
    status: str
    updated_at: datetime
    valid_from: datetime
    valid_until: datetime
    cost_limit_eur: Decimal | None = None
    token_limit_total: int | None = None
    request_limit_total: int | None = None
    cost_used_eur: Decimal | None = None
    tokens_used_total: int | None = None
    requests_used_total: int | None = None
    cost_reserved_eur: Decimal | None = None
    tokens_reserved_total: int | None = None
    requests_reserved_total: int | None = None
    last_quota_reset_at: datetime | None = None
    quota_reset_count: int | None = None
    rate_limit_policy: dict[str, int | None] | None = None


@dataclass(frozen=True, slots=True)
class RotatedGatewayKeyResult:
    """One-time rotation result that contains the replacement plaintext key."""

    old_gateway_key_id: uuid.UUID
    new_gateway_key_id: uuid.UUID
    new_plaintext_key: str
    new_public_key_id: str
    one_time_secret_id: uuid.UUID
    old_status: str
    new_status: str
    valid_from: datetime
    valid_until: datetime
