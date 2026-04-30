"""Safe admin dashboard CSV exports for usage and audit metadata."""

from __future__ import annotations

import csv
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import Protocol

from slaif_gateway.db.models import AuditLog, UsageLedger
from slaif_gateway.utils.redaction import is_sensitive_key, redact_text
from slaif_gateway.utils.sanitization import is_content_key, sanitize_metadata

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_CONTENT_TEXT_RE = re.compile(r"\b(prompt|completion|request body|response body|raw request|raw response)\b", re.I)
_AUTHORIZATION_BEARER_RE = re.compile(r"(?i)\bauthorization\s*[:=]?\s*bearer\s+\S+")


USAGE_CSV_COLUMNS = (
    "created_at",
    "completed_at",
    "request_id",
    "gateway_key_id",
    "key_public_id",
    "owner_id",
    "owner_email",
    "institution_id",
    "cohort_id",
    "endpoint",
    "provider",
    "requested_model",
    "resolved_model",
    "streaming",
    "accounting_status",
    "success",
    "http_status",
    "error_type",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "estimated_cost_eur",
    "actual_cost_eur",
    "native_currency",
    "latency_ms",
)

AUDIT_CSV_COLUMNS = (
    "created_at",
    "actor_admin_id",
    "action",
    "target_type",
    "target_id",
    "request_id",
    "ip_address",
    "user_agent_summary",
    "old_values_sanitized",
    "new_values_sanitized",
    "reason",
)


class UsageExportRepository(Protocol):
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


class AuditExportRepository(Protocol):
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

    async def add_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        admin_user_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        note: str | None = None,
    ) -> AuditLog: ...


@dataclass(frozen=True, slots=True)
class AdminCsvExportResult:
    """Safe CSV response body plus audit metadata."""

    filename_prefix: str
    content: str
    row_count: int
    audit_log_id: uuid.UUID


class AdminCsvExportService:
    """Build CSRF-triggered admin CSV exports without provider or external calls."""

    def __init__(
        self,
        *,
        usage_ledger_repository: UsageExportRepository,
        audit_repository: AuditExportRepository,
    ) -> None:
        self._usage = usage_ledger_repository
        self._audit = audit_repository

    async def export_usage_csv(
        self,
        *,
        actor_admin_id: uuid.UUID,
        reason: str,
        limit: int,
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
        ip_address: str | None = None,
        user_agent: str | None = None,
        audit_request_id: str | None = None,
    ) -> AdminCsvExportResult:
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
            offset=0,
        )
        content = build_usage_csv(rows)
        audit_row = await self._audit.add_audit_log(
            admin_user_id=actor_admin_id,
            action="admin_usage_export_csv",
            entity_type="usage_ledger_export",
            old_values=None,
            new_values={
                "row_count": len(rows),
                "limit": limit,
                "filters": _safe_filter_metadata(
                    {
                        "provider": provider,
                        "model": model,
                        "endpoint": endpoint,
                        "status": status,
                        "gateway_key_id": gateway_key_id,
                        "owner_id": owner_id,
                        "institution_id": institution_id,
                        "cohort_id": cohort_id,
                        "request_id": request_id,
                        "streaming": streaming,
                        "start_at": start_at,
                        "end_at": end_at,
                    }
                ),
            },
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=audit_request_id,
            note=reason,
        )
        return AdminCsvExportResult(
            filename_prefix="usage-export",
            content=content,
            row_count=len(rows),
            audit_log_id=audit_row.id,
        )

    async def export_audit_csv(
        self,
        *,
        actor_admin_id: uuid.UUID,
        reason: str,
        limit: int,
        actor_filter_admin_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        request_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        audit_request_id: str | None = None,
    ) -> AdminCsvExportResult:
        rows = await self._audit.list_audit_logs_for_admin(
            actor_admin_id=actor_filter_admin_id,
            action=_clean(action),
            target_type=_clean(target_type),
            target_id=target_id,
            request_id=_clean(request_id),
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=0,
        )
        content = build_audit_csv(rows)
        audit_row = await self._audit.add_audit_log(
            admin_user_id=actor_admin_id,
            action="admin_audit_export_csv",
            entity_type="audit_log_export",
            old_values=None,
            new_values={
                "row_count": len(rows),
                "limit": limit,
                "filters": _safe_filter_metadata(
                    {
                        "actor_admin_id": actor_filter_admin_id,
                        "action": action,
                        "target_type": target_type,
                        "target_id": target_id,
                        "request_id": request_id,
                        "start_at": start_at,
                        "end_at": end_at,
                    }
                ),
            },
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=audit_request_id,
            note=reason,
        )
        return AdminCsvExportResult(
            filename_prefix="audit-export",
            content=content,
            row_count=len(rows),
            audit_log_id=audit_row.id,
        )


def build_usage_csv(rows: list[UsageLedger]) -> str:
    """Render safe usage-ledger metadata rows as CSV."""
    return _build_csv(
        USAGE_CSV_COLUMNS,
        (
            {
                "created_at": row.created_at,
                "completed_at": row.finished_at,
                "request_id": row.request_id,
                "gateway_key_id": row.gateway_key_id,
                "key_public_id": row.gateway_key.public_key_id if row.gateway_key is not None else None,
                "owner_id": row.owner_id,
                "owner_email": row.owner_email_snapshot,
                "institution_id": row.institution_id,
                "cohort_id": row.cohort_id,
                "endpoint": row.endpoint,
                "provider": row.provider,
                "requested_model": row.requested_model,
                "resolved_model": row.resolved_model,
                "streaming": row.streaming,
                "accounting_status": row.accounting_status,
                "success": row.success,
                "http_status": row.http_status,
                "error_type": row.error_type,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "total_tokens": row.total_tokens,
                "cached_tokens": row.cached_tokens,
                "reasoning_tokens": row.reasoning_tokens,
                "estimated_cost_eur": row.estimated_cost_eur,
                "actual_cost_eur": row.actual_cost_eur,
                "native_currency": row.native_currency,
                "latency_ms": row.latency_ms,
            }
            for row in rows
        ),
    )


def build_audit_csv(rows: list[AuditLog]) -> str:
    """Render safe audit-log metadata rows as CSV."""
    return _build_csv(
        AUDIT_CSV_COLUMNS,
        (
            {
                "created_at": row.created_at,
                "actor_admin_id": row.admin_user_id,
                "action": row.action,
                "target_type": row.entity_type,
                "target_id": row.entity_id,
                "request_id": row.request_id,
                "ip_address": row.ip_address,
                "user_agent_summary": _safe_text(row.user_agent, max_length=160),
                "old_values_sanitized": _safe_metadata_summary(row.old_values),
                "new_values_sanitized": _safe_metadata_summary(row.new_values),
                "reason": _safe_text(row.note, max_length=500),
            }
            for row in rows
        ),
    )


def sanitize_csv_cell(value: object) -> str:
    """Return a redacted, formula-safe CSV cell string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        text = value.isoformat()
    elif isinstance(value, Decimal):
        text = str(value)
    elif isinstance(value, uuid.UUID):
        text = str(value)
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = _safe_text(str(value), max_length=2000)
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _build_csv(columns: tuple[str, ...], rows: Iterable[Mapping[str, object]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: sanitize_csv_cell(row.get(column)) for column in columns})
    return output.getvalue()


def _safe_metadata_summary(value: Mapping[str, object] | None) -> str:
    if not value:
        return ""
    safe = _drop_export_unsafe_metadata(sanitize_metadata(value, drop_content_keys=True))
    if not safe:
        return ""
    return json.dumps(safe, sort_keys=True, default=str)


def _drop_export_unsafe_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        safe: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if is_sensitive_key(key) or is_content_key(key):
                continue
            cleaned = _drop_export_unsafe_metadata(item)
            if cleaned is not None:
                safe[key] = cleaned
        return safe
    if isinstance(value, list | tuple):
        safe_items = []
        for item in value:
            cleaned = _drop_export_unsafe_metadata(item)
            if cleaned is not None:
                safe_items.append(cleaned)
        return safe_items
    if isinstance(value, str):
        return _safe_text(value, max_length=1000)
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, Decimal | datetime | uuid.UUID):
        return str(value)
    return _safe_text(str(value), max_length=1000)


def _safe_filter_metadata(values: Mapping[str, object]) -> dict[str, object]:
    return {
        key: str(value) if isinstance(value, uuid.UUID | datetime) else value
        for key, value in values.items()
        if value is not None and value != ""
    }


def _safe_text(value: str | None, *, max_length: int) -> str:
    if value is None:
        return ""
    redacted = redact_text(_AUTHORIZATION_BEARER_RE.sub("***", value))
    if _CONTENT_TEXT_RE.search(redacted):
        return "***"
    if len(redacted) > max_length:
        return f"{redacted[:max_length]}..."
    return redacted


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
