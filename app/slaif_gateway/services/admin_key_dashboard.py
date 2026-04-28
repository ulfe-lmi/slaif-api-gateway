"""Read-only service for admin dashboard key pages."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow


class AdminKeyNotFoundError(Exception):
    """Raised when an admin dashboard key detail is not found."""


class _GatewayKeysAdminRepository(Protocol):
    async def list_keys_for_admin(
        self,
        *,
        status: str | None = None,
        owner_email: str | None = None,
        public_key_id: str | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        expired: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GatewayKey]: ...

    async def get_key_for_admin_detail(self, gateway_key_id: uuid.UUID) -> GatewayKey | None: ...


class AdminKeyDashboardService:
    """Build safe read-only key dashboard DTOs from repository rows."""

    def __init__(self, *, gateway_keys_repository: _GatewayKeysAdminRepository) -> None:
        self._gateway_keys = gateway_keys_repository

    async def list_keys(
        self,
        *,
        status: str | None = None,
        owner_email: str | None = None,
        public_key_id: str | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        expired: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[AdminKeyListRow]:
        timestamp = _utcnow(now)
        rows = await self._gateway_keys.list_keys_for_admin(
            status=_clean_filter(status),
            owner_email=_clean_filter(owner_email),
            public_key_id=_clean_filter(public_key_id),
            institution_id=institution_id,
            cohort_id=cohort_id,
            expired=expired,
            now=timestamp,
            limit=limit,
            offset=offset,
        )
        return [_to_list_row(row, now=timestamp) for row in rows]

    async def get_key_detail(
        self,
        gateway_key_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> AdminKeyDetail:
        timestamp = _utcnow(now)
        row = await self._gateway_keys.get_key_for_admin_detail(gateway_key_id)
        if row is None:
            raise AdminKeyNotFoundError("Gateway key not found")
        return _to_detail(row, now=timestamp)


def _to_detail(row: GatewayKey, *, now: datetime) -> AdminKeyDetail:
    list_row = _to_list_row(row, now=now)
    return AdminKeyDetail(
        **asdict(list_row),
        revoked_at=row.revoked_at,
        revoked_reason=row.revoked_reason,
        created_by_admin_user_id=row.created_by_admin_user_id,
        last_used_at=row.last_used_at,
        last_quota_reset_at=row.last_quota_reset_at,
        quota_reset_count=row.quota_reset_count,
    )


def _to_list_row(row: GatewayKey, *, now: datetime) -> AdminKeyListRow:
    owner = getattr(row, "owner", None)
    institution = getattr(owner, "institution", None) if owner is not None else None
    cohort = getattr(row, "cohort", None)
    return AdminKeyListRow(
        id=row.id,
        public_key_id=row.public_key_id,
        key_prefix=row.key_prefix,
        key_hint=row.key_hint,
        owner_id=row.owner_id,
        owner_display_name=_owner_display_name(owner),
        owner_email=getattr(owner, "email", None),
        institution_id=getattr(institution, "id", None),
        institution_name=getattr(institution, "name", None),
        cohort_id=row.cohort_id,
        cohort_name=getattr(cohort, "name", None),
        status=row.status,
        computed_display_status=compute_key_display_status(row.status, row.valid_from, row.valid_until, now=now),
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
        cost_used_eur=_decimal(row.cost_used_eur),
        tokens_used_total=row.tokens_used_total,
        requests_used_total=row.requests_used_total,
        cost_reserved_eur=_decimal(row.cost_reserved_eur),
        tokens_reserved_total=row.tokens_reserved_total,
        requests_reserved_total=row.requests_reserved_total,
        allowed_models_summary=_allowed_values_summary(row.allow_all_models, row.allowed_models),
        allowed_endpoints_summary=_allowed_values_summary(row.allow_all_endpoints, row.allowed_endpoints),
        allowed_providers_summary=_allowed_providers_summary(row.metadata_json),
        rate_limit_policy_summary=_rate_limit_policy_summary(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def compute_key_display_status(
    status: str,
    valid_from: datetime,
    valid_until: datetime,
    *,
    now: datetime | None = None,
) -> str:
    """Return the admin-display lifecycle state without changing stored status."""
    timestamp = _utcnow(now)
    if status in {"revoked", "suspended"}:
        return status
    if valid_from > timestamp:
        return "not_yet_valid"
    if valid_until <= timestamp:
        return "expired"
    return "active"


def _owner_display_name(owner: object | None) -> str | None:
    if owner is None:
        return None
    name = str(getattr(owner, "name", "") or "").strip()
    surname = str(getattr(owner, "surname", "") or "").strip()
    display = f"{name} {surname}".strip()
    return display or None


def _allowed_values_summary(allow_all: bool, values: list[str] | tuple[str, ...] | None) -> str:
    if allow_all:
        return "All"
    cleaned = [str(value) for value in values or [] if str(value).strip()]
    return ", ".join(cleaned) if cleaned else "None"


def _allowed_providers_summary(metadata_json: dict[str, object] | None) -> str:
    if not isinstance(metadata_json, dict):
        return "All"
    providers = metadata_json.get("allowed_providers")
    if providers is None:
        return "All"
    if isinstance(providers, list):
        cleaned = [str(provider) for provider in providers if str(provider).strip()]
        return ", ".join(cleaned) if cleaned else "None"
    return "None"


def _rate_limit_policy_summary(row: GatewayKey) -> str:
    parts: list[str] = []
    if row.rate_limit_requests_per_minute is not None:
        parts.append(f"{row.rate_limit_requests_per_minute} req/min")
    if row.rate_limit_tokens_per_minute is not None:
        parts.append(f"{row.rate_limit_tokens_per_minute} tokens/min")
    if row.max_concurrent_requests is not None:
        parts.append(f"{row.max_concurrent_requests} concurrent")
    metadata_policy = row.metadata_json.get("rate_limit_policy") if isinstance(row.metadata_json, dict) else None
    if isinstance(metadata_policy, dict):
        window_seconds = metadata_policy.get("window_seconds")
        if isinstance(window_seconds, int) and not isinstance(window_seconds, bool):
            parts.append(f"{window_seconds}s window")
    return ", ".join(parts) if parts else "Default"


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
