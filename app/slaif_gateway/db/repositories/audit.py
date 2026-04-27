"""Repository helpers for audit_log table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AuditLog
from slaif_gateway.utils.redaction import redact_text
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping


class AuditRepository:
    """Encapsulates append/list access for AuditLog rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
    ) -> AuditLog:
        row = AuditLog(
            admin_user_id=admin_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=_sanitize_optional_metadata(old_values),
            new_values=_sanitize_optional_metadata(new_values),
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            note=redact_text(note) if note is not None else None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_audit_logs(
        self,
        *,
        admin_user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        statement: Select[tuple[AuditLog]] = select(AuditLog)
        if admin_user_id is not None:
            statement = statement.where(AuditLog.admin_user_id == admin_user_id)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if action is not None:
            statement = statement.where(AuditLog.action == action)

        statement = statement.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())


def _sanitize_optional_metadata(values: dict[str, object] | None) -> dict[str, object] | None:
    if values is None:
        return None
    return sanitize_metadata_mapping(values, drop_content_keys=True)
