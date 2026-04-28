"""Repository helpers for audit_log table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
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
    ) -> list[AuditLog]:
        """Return audit log rows for read-only admin dashboard pages."""
        statement: Select[tuple[AuditLog]] = select(AuditLog)
        if actor_admin_id is not None:
            statement = statement.where(AuditLog.admin_user_id == actor_admin_id)
        if action is not None:
            statement = statement.where(func.lower(AuditLog.action).like(f"%{action.lower()}%"))
        if target_type is not None:
            statement = statement.where(func.lower(AuditLog.entity_type).like(f"%{target_type.lower()}%"))
        if target_id is not None:
            statement = statement.where(AuditLog.entity_id == target_id)
        if request_id is not None:
            statement = statement.where(func.lower(AuditLog.request_id).like(f"%{request_id.lower()}%"))
        if start_at is not None:
            statement = statement.where(AuditLog.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(AuditLog.created_at <= end_at)

        statement = statement.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_audit_log_for_admin_detail(self, audit_log_id: uuid.UUID) -> AuditLog | None:
        return await self._session.get(AuditLog, audit_log_id)


def _sanitize_optional_metadata(values: dict[str, object] | None) -> dict[str, object] | None:
    if values is None:
        return None
    return sanitize_metadata_mapping(values, drop_content_keys=True)
