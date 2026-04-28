"""Safe DTOs for read-only admin usage, audit, and email delivery pages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AdminUsageListRow:
    id: uuid.UUID
    request_id: str
    gateway_key_id: uuid.UUID
    key_public_id: str | None
    owner_id: uuid.UUID | None
    owner_display_name: str | None
    institution_id: uuid.UUID | None
    cohort_id: uuid.UUID | None
    endpoint: str
    provider: str
    requested_model: str | None
    resolved_model: str | None
    streaming: bool
    success: bool | None
    accounting_status: str
    http_status: int | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    estimated_cost_eur: Decimal | None
    actual_cost_eur: Decimal | None
    native_currency: str | None
    latency_ms: int | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdminUsageDetail(AdminUsageListRow):
    client_request_id: str | None
    quota_reservation_id: uuid.UUID | None
    upstream_request_id: str | None
    error_type: str | None
    error_message: str | None
    usage_summary: str
    response_metadata_summary: str


@dataclass(frozen=True, slots=True)
class AdminAuditListRow:
    id: uuid.UUID
    actor_admin_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    request_id: str | None
    ip_address: str | None
    user_agent_summary: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminAuditDetail(AdminAuditListRow):
    old_values_summary: str
    new_values_summary: str
    note: str | None


@dataclass(frozen=True, slots=True)
class AdminEmailDeliveryListRow:
    id: uuid.UUID
    owner_id: uuid.UUID | None
    owner_email: str | None
    gateway_key_id: uuid.UUID | None
    public_key_id: str | None
    one_time_secret_id: uuid.UUID | None
    status: str
    to_email: str
    subject: str
    template_name: str
    sent_at: datetime | None
    failed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminEmailDeliveryDetail(AdminEmailDeliveryListRow):
    provider_message_id: str | None
    failure_reason: str | None
    email_delivery_status: str
    one_time_secret_status: str
    can_send_now: bool
    can_enqueue: bool
    safe_blocking_reason: str | None
