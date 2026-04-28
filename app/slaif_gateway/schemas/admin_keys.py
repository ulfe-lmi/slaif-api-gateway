"""Safe DTOs for read-only admin key dashboard pages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AdminKeyListRow:
    """Safe key metadata for the admin key list."""

    id: uuid.UUID
    public_key_id: str
    key_prefix: str
    key_hint: str | None
    owner_id: uuid.UUID
    owner_display_name: str | None
    owner_email: str | None
    institution_id: uuid.UUID | None
    institution_name: str | None
    cohort_id: uuid.UUID | None
    cohort_name: str | None
    status: str
    computed_display_status: str
    can_suspend: bool
    can_activate: bool
    can_revoke: bool
    can_rotate: bool
    valid_from: datetime
    valid_until: datetime
    cost_limit_eur: Decimal | None
    token_limit_total: int | None
    request_limit_total: int | None
    cost_used_eur: Decimal
    tokens_used_total: int
    requests_used_total: int
    cost_reserved_eur: Decimal
    tokens_reserved_total: int
    requests_reserved_total: int
    allowed_models_summary: str
    allowed_endpoints_summary: str
    allowed_providers_summary: str
    rate_limit_policy_summary: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminAuditEntrySummary:
    """Safe audit metadata for future detail-page expansion."""

    action: str
    created_at: datetime
    admin_user_id: uuid.UUID | None
    note: str | None


@dataclass(frozen=True, slots=True)
class AdminKeyDetail(AdminKeyListRow):
    """Safe key metadata for the admin key detail page."""

    revoked_at: datetime | None
    revoked_reason: str | None
    created_by_admin_user_id: uuid.UUID | None
    last_used_at: datetime | None
    last_quota_reset_at: datetime | None
    quota_reset_count: int
    recent_audit_entries: tuple[AdminAuditEntrySummary, ...] = ()
