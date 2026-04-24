"""Repository helpers for audit_log table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AuditLog


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
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            note=note,
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
