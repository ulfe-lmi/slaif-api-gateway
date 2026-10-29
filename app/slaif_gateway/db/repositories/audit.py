"""Repository helpers for audit_log table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AuditLog
from slaif_gateway.utils.admin_list_filters import (
    as_uuid_tuple,
    as_value_tuple,
    or_equals,
)
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
        actor_admin_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        action: str | Sequence[str] | None = None,
        target_type: str | Sequence[str] | None = None,
        target_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        request_id: str | Sequence[str] | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Return audit log rows for read-only admin dashboard pages."""
        actor_ids = as_uuid_tuple(actor_admin_id)
        actions = as_value_tuple(action)
        target_types = as_value_tuple(target_type)
        target_ids = as_uuid_tuple(target_id)
        request_ids = as_value_tuple(request_id)
        # 195-a: OR WITHIN a field, AND ACROSS fields; all predicates apply
        # in SQL BEFORE LIMIT/OFFSET (so multi target_type parents OR-scope
        # the target picker too). Pre-195 per-member normalization preserved
        # exactly (case-insensitive substring for action/target_type/
        # request-id, exact equality for the UUID ids).
        statement: Select[tuple[AuditLog]] = select(AuditLog)
        if actor_ids is not None:
            statement = statement.where(or_equals(AuditLog.admin_user_id, actor_ids))
        if actions is not None:
            statement = statement.where(
                or_(
                    *[
                        func.lower(AuditLog.action).like(f"%{value.lower()}%")
                        for value in actions
                    ]
                )
            )
        if target_types is not None:
            statement = statement.where(
                or_(
                    *[
                        func.lower(AuditLog.entity_type).like(f"%{value.lower()}%")
                        for value in target_types
                    ]
                )
            )
        if target_ids is not None:
            statement = statement.where(or_equals(AuditLog.entity_id, target_ids))
        if request_ids is not None:
            statement = statement.where(
                or_(
                    *[
                        func.lower(AuditLog.request_id).like(f"%{value.lower()}%")
                        for value in request_ids
                    ]
                )
            )
        if start_at is not None:
            statement = statement.where(AuditLog.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(AuditLog.created_at <= end_at)

        statement = statement.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_audit_log_for_admin_detail(self, audit_log_id: uuid.UUID) -> AuditLog | None:
        return await self._session.get(AuditLog, audit_log_id)

    async def get_latest_email_error_for_delivery(
        self, email_delivery_id: uuid.UUID
    ) -> AuditLog | None:
        """202-a: latest exact email-error audit entry for one delivery.

        Exact entity_type `email_delivery` + exact entity_id, actions
        limited to the two known error-recording actions; deterministic
        `(created_at DESC, id DESC)` tie-break. Not a broad admin
        substring/action search.
        """
        statement = (
            select(AuditLog)
            .where(
                AuditLog.action.in_(("email_key_failed", "email_key_ambiguous")),
                AuditLog.entity_type == "email_delivery",
                AuditLog.entity_id == email_delivery_id,
            )
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def count_recent_admin_login_failures(
        self,
        *,
        normalized_email: str,
        ip_address: str | None,
        since: datetime,
    ) -> int:
        """Count recent failed admin-login attempts by email or client IP."""
        conditions = [AuditLog.new_values["email"].as_string() == normalized_email]
        if ip_address is not None:
            conditions.append(AuditLog.ip_address == ip_address)

        statement = (
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "admin_login_failed",
                AuditLog.created_at >= since,
                or_(*conditions),
            )
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def get_latest_admin_login_lockout(
        self,
        *,
        normalized_email: str,
        ip_address: str | None,
        since: datetime,
    ) -> AuditLog | None:
        """Return the latest active admin-login lockout audit row for email or IP."""
        conditions = [AuditLog.new_values["email"].as_string() == normalized_email]
        if ip_address is not None:
            conditions.append(AuditLog.ip_address == ip_address)

        statement = (
            select(AuditLog)
            .where(
                AuditLog.action == "admin_login_rate_limited",
                AuditLog.created_at >= since,
                or_(*conditions),
            )
            .order_by(desc(AuditLog.created_at))
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


def _sanitize_optional_metadata(values: dict[str, object] | None) -> dict[str, object] | None:
    if values is None:
        return None
    return sanitize_metadata_mapping(values, drop_content_keys=True)
