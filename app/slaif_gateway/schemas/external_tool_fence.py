"""Safe schema types for the external-tool exclusive quota fence foundation.

These types carry only durable identifiers, numeric totals, timestamps, and
canonical low-cardinality capability/destination IDs. They never carry prompt
text, request/response bodies, tool arguments or results, raw MCP values, URLs,
authorization material, or provider response content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from slaif_gateway.services.external_tool_policy_contract import (
    ExternalToolAdmissionDecision,
)


@dataclass(frozen=True, slots=True)
class ExternalToolFenceRouteFacts:
    """Safe endpoint/provider/route identification facts for acquisition."""

    endpoint: str
    requested_model: str
    provider: str
    route_id: UUID


@dataclass(frozen=True, slots=True)
class ExternalToolFenceAcquireInput:
    """The only inputs the fence acquisition service accepts.

    ``decision`` must be the exact objective-012
    ``ExternalToolAdmissionDecision`` type; the service re-validates its
    positive fenced contract (allowed, fenced mode, positive effective call
    cap, canonical allowed reason, and all four exclusive obligations true)
    before any mutation.
    """

    gateway_key_id: UUID
    request_id: str
    route: ExternalToolFenceRouteFacts
    capabilities: tuple[str, ...]
    destination_ids: tuple[str, ...]
    decision: ExternalToolAdmissionDecision
    now: datetime
    ttl: timedelta = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class ExternalToolFenceResult:
    """Acquisition result DTO: IDs, state, numeric totals, canonical IDs."""

    gateway_key_id: UUID
    request_id: str
    reservation_id: UUID
    fence_state: str
    reserved_cost_eur: Decimal
    reserved_tokens: int
    reserved_requests: int
    acquired_at: datetime
    expires_at: datetime
    capabilities: tuple[str, ...]
    destination_ids: tuple[str, ...]
    idempotent: bool


@dataclass(frozen=True, slots=True)
class ExternalToolFenceProjection:
    """Read-only fence projection exposing IDs, timestamps, and state only."""

    gateway_key_id: UUID
    fence_state: str
    reservation_id: UUID | None
    request_id: str | None
    acquired_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExternalToolFenceResolveInput:
    """Narrow idempotent resolution request keyed to an unresolved fence."""

    gateway_key_id: UUID
    request_id: str


@dataclass(frozen=True, slots=True)
class ExternalToolFenceResolveResult:
    """Resolution outcome: the resulting state and whether it cleared the fence."""

    gateway_key_id: UUID
    fence_state: str
    resolved: bool
