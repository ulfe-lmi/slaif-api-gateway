"""Read-only admin dashboard service for usage, audit, and email delivery activity."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from slaif_gateway.db.models import AuditLog, EmailDelivery, UsageLedger
from slaif_gateway.schemas.admin_activity import (
    AdminAuditDetail,
    AdminAuditListRow,
    AdminEmailDeliveryDetail,
    AdminEmailDeliveryListRow,
    AdminUsageDetail,
    AdminUsageListRow,
)
from slaif_gateway.utils.redaction import is_sensitive_key, redact_text
from slaif_gateway.utils.sanitization import is_content_key, sanitize_metadata


class UsageLedgerDashboardRepository(Protocol):
    async def list_usage_for_admin(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        status: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        request_id: str | None = None,
        streaming: bool | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UsageLedger]: ...

    async def get_usage_for_admin_detail(self, usage_ledger_id: uuid.UUID) -> UsageLedger | None: ...


class AuditDashboardRepository(Protocol):
    async def list_audit_logs_for_admin(
        self,
        *,
        actor_admin_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        request_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]: ...

    async def get_audit_log_for_admin_detail(self, audit_log_id: uuid.UUID) -> AuditLog | None: ...


class EmailDeliveryDashboardRepository(Protocol):
    async def list_email_deliveries_for_admin(
        self,
        *,
        status: str | None = None,
        owner_email: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
        one_time_secret_id: uuid.UUID | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmailDelivery]: ...

    async def get_email_delivery_for_admin_detail(self, email_delivery_id: uuid.UUID) -> EmailDelivery | None: ...


class AdminActivityNotFoundError(LookupError):
    """Raised when a requested activity row is not present."""


class AdminActivityDashboardService:
    """Project usage, audit, and email delivery rows into safe dashboard DTOs."""

    def __init__(
        self,
        *,
        usage_ledger_repository: UsageLedgerDashboardRepository,
        audit_repository: AuditDashboardRepository,
        email_deliveries_repository: EmailDeliveryDashboardRepository,
    ) -> None:
        self._usage = usage_ledger_repository
        self._audit = audit_repository
        self._email_deliveries = email_deliveries_repository

    async def list_usage(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        status: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        request_id: str | None = None,
        streaming: bool | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminUsageListRow]:
        rows = await self._usage.list_usage_for_admin(
            provider=_clean(provider),
            model=_clean(model),
            endpoint=_clean(endpoint),
            status=_clean(status),
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
            request_id=_clean(request_id),
            streaming=streaming,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )
        return [_usage_list_row(row) for row in rows]

    async def get_usage_detail(self, usage_ledger_id: uuid.UUID) -> AdminUsageDetail:
        row = await self._usage.get_usage_for_admin_detail(usage_ledger_id)
        if row is None:
            raise AdminActivityNotFoundError("Usage ledger row was not found")
        return _usage_detail(row)

    async def list_audit_logs(
        self,
        *,
        actor_admin_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        request_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminAuditListRow]:
        rows = await self._audit.list_audit_logs_for_admin(
            actor_admin_id=actor_admin_id,
            action=_clean(action),
            target_type=_clean(target_type),
            target_id=target_id,
            request_id=_clean(request_id),
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )
        return [_audit_list_row(row) for row in rows]

    async def get_audit_detail(self, audit_log_id: uuid.UUID) -> AdminAuditDetail:
        row = await self._audit.get_audit_log_for_admin_detail(audit_log_id)
        if row is None:
            raise AdminActivityNotFoundError("Audit log row was not found")
        return _audit_detail(row)

    async def list_email_deliveries(
        self,
        *,
        status: str | None = None,
        owner_email: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
        one_time_secret_id: uuid.UUID | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminEmailDeliveryListRow]:
        rows = await self._email_deliveries.list_email_deliveries_for_admin(
            status=_clean(status),
            owner_email=_clean(owner_email),
            gateway_key_id=gateway_key_id,
            one_time_secret_id=one_time_secret_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )
        return [_email_delivery_list_row(row) for row in rows]

    async def get_email_delivery_detail(self, email_delivery_id: uuid.UUID) -> AdminEmailDeliveryDetail:
        row = await self._email_deliveries.get_email_delivery_for_admin_detail(email_delivery_id)
        if row is None:
            raise AdminActivityNotFoundError("Email delivery row was not found")
        return _email_delivery_detail(row)


def _usage_list_row(row: UsageLedger) -> AdminUsageListRow:
    return AdminUsageListRow(
        id=row.id,
        request_id=row.request_id,
        gateway_key_id=row.gateway_key_id,
        key_public_id=row.gateway_key.public_key_id if row.gateway_key is not None else None,
        owner_id=row.owner_id,
        owner_display_name=_owner_display_name(row),
        institution_id=row.institution_id,
        cohort_id=row.cohort_id,
        endpoint=row.endpoint,
        provider=row.provider,
        requested_model=row.requested_model,
        resolved_model=row.resolved_model,
        streaming=row.streaming,
        success=row.success,
        accounting_status=row.accounting_status,
        http_status=row.http_status,
        prompt_tokens=int(row.prompt_tokens or 0),
        completion_tokens=int(row.completion_tokens or 0),
        total_tokens=int(row.total_tokens or 0),
        cached_tokens=int(row.cached_tokens or 0),
        reasoning_tokens=int(row.reasoning_tokens or 0),
        estimated_cost_eur=row.estimated_cost_eur,
        actual_cost_eur=row.actual_cost_eur,
        native_currency=row.native_currency,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
        completed_at=row.finished_at,
    )


def _usage_detail(row: UsageLedger) -> AdminUsageDetail:
    base = _usage_list_row(row)
    return AdminUsageDetail(
        **asdict(base),
        client_request_id=_safe_optional_text(row.client_request_id),
        quota_reservation_id=row.quota_reservation_id,
        upstream_request_id=_safe_optional_text(row.upstream_request_id),
        error_type=_safe_optional_text(row.error_type),
        error_message=_safe_optional_text(row.error_message),
        usage_summary=_metadata_summary(row.usage_raw),
        response_metadata_summary=_metadata_summary(row.response_metadata),
    )


def _audit_list_row(row: AuditLog) -> AdminAuditListRow:
    return AdminAuditListRow(
        id=row.id,
        actor_admin_id=row.admin_user_id,
        action=row.action,
        target_type=row.entity_type,
        target_id=row.entity_id,
        request_id=_safe_optional_text(row.request_id),
        ip_address=str(row.ip_address) if row.ip_address is not None else None,
        user_agent_summary=_safe_optional_text(_truncate(row.user_agent, 120)),
        created_at=row.created_at,
    )


def _audit_detail(row: AuditLog) -> AdminAuditDetail:
    base = _audit_list_row(row)
    return AdminAuditDetail(
        **asdict(base),
        old_values_summary=_metadata_summary(row.old_values),
        new_values_summary=_metadata_summary(row.new_values),
        note=_safe_optional_text(row.note),
    )


def _email_delivery_list_row(row: EmailDelivery) -> AdminEmailDeliveryListRow:
    return AdminEmailDeliveryListRow(
        id=row.id,
        owner_id=row.owner_id,
        owner_email=row.owner.email if row.owner is not None else None,
        gateway_key_id=row.gateway_key_id,
        public_key_id=row.gateway_key.public_key_id if row.gateway_key is not None else None,
        one_time_secret_id=row.one_time_secret_id,
        status=row.status,
        to_email=row.recipient_email,
        subject=_safe_text(row.subject),
        template_name=row.template_name,
        sent_at=row.sent_at,
        failed_at=row.failed_at,
        created_at=row.created_at,
    )


def _email_delivery_detail(row: EmailDelivery) -> AdminEmailDeliveryDetail:
    base = _email_delivery_list_row(row)
    one_time_secret_status, blocking_reason = _email_delivery_action_state(row)
    can_send = blocking_reason is None
    return AdminEmailDeliveryDetail(
        **asdict(base),
        provider_message_id=_safe_optional_text(row.provider_message_id),
        failure_reason=_safe_optional_text(row.error_message),
        email_delivery_status=row.status,
        one_time_secret_status=one_time_secret_status,
        can_send_now=can_send,
        can_enqueue=can_send,
        safe_blocking_reason=blocking_reason,
    )


def _email_delivery_action_state(row: EmailDelivery) -> tuple[str, str | None]:
    if row.status == "sending":
        return (
            "present",
            "This delivery is already in progress. Do not retry automatically; rotate the key if delivery cannot be confirmed.",
        )
    if row.status == "ambiguous":
        return (
            "present",
            "SMTP may have accepted this email, but finalization did not complete. Do not retry; rotate the key if receipt cannot be confirmed.",
        )
    if row.status not in {"pending", "failed"}:
        return "unavailable", "Only pending or failed key email deliveries can be sent."
    if row.one_time_secret is None:
        return "unavailable", "The one-time secret is unavailable; rotate the key and create a new delivery."
    if row.one_time_secret.status == "consumed" or row.one_time_secret.consumed_at is not None:
        return "consumed", "The one-time secret was already consumed; lost keys must be rotated."
    now = datetime.now(UTC)
    if row.one_time_secret.status == "expired" or row.one_time_secret.expires_at <= now:
        return "expired", "The one-time secret is expired; rotate the key and create a new delivery."
    if row.one_time_secret.status != "pending":
        return "unavailable", "The one-time secret is not pending; rotate the key and create a new delivery."
    if row.one_time_secret.purpose not in {"gateway_key_email", "gateway_key_rotation_email"}:
        return "unavailable", "The one-time secret is not valid for key email delivery."
    if row.one_time_secret.owner_id != row.owner_id or row.one_time_secret.gateway_key_id != row.gateway_key_id:
        return "unavailable", "The one-time secret does not match this email delivery."
    return "present", None


def _owner_display_name(row: UsageLedger) -> str | None:
    parts = [row.owner_name_snapshot, row.owner_surname_snapshot]
    display = " ".join(part for part in parts if part)
    if row.owner_email_snapshot:
        return f"{display} <{row.owner_email_snapshot}>" if display else str(row.owner_email_snapshot)
    if display:
        return display
    if row.owner is not None:
        return f"{row.owner.name} {row.owner.surname} <{row.owner.email}>"
    return None


def _metadata_summary(value: Mapping[str, object] | None) -> str:
    if not value:
        return "No metadata"
    safe = _drop_dashboard_unsafe_metadata(sanitize_metadata(value, drop_content_keys=True))
    if not safe:
        return "No safe metadata"
    return json.dumps(safe, sort_keys=True, default=str)


def _drop_dashboard_unsafe_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        safe: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if is_sensitive_key(key) or is_content_key(key):
                continue
            cleaned = _drop_dashboard_unsafe_metadata(item)
            if cleaned is not None:
                safe[key] = cleaned
        return safe
    if isinstance(value, list | tuple):
        return [
            cleaned
            for item in value
            if (cleaned := _drop_dashboard_unsafe_metadata(item)) is not None
        ]
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _safe_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _safe_text(value)


def _safe_text(value: str) -> str:
    redacted = redact_text(value)
    return re.sub(r"(?i)\bauthorization\s*=\s*(?:bearer\s+)?[^\s;,]+", "authorization=***", redacted)


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None or len(value) <= max_length:
        return value
    return f"{value[: max_length - 1]}..."
