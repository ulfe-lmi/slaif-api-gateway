"""Repository helpers for admin_sessions table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AdminSession


class AdminSessionsRepository:
    """Encapsulates CRUD-style access for AdminSession rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_admin_session(
        self,
        *,
        admin_user_id: uuid.UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
        last_seen_at: datetime | None = None,
    ) -> AdminSession:
        admin_session = AdminSession(
            admin_user_id=admin_user_id,
            session_token_hash=session_token_hash,
            csrf_token_hash=csrf_token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            last_seen_at=last_seen_at,
        )
        self._session.add(admin_session)
        await self._session.flush()
        return admin_session

    async def get_admin_session_by_hash(self, session_token_hash: str) -> AdminSession | None:
        result = await self._session.execute(
            select(AdminSession).where(AdminSession.session_token_hash == session_token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_admin_session(self, admin_session_id: uuid.UUID, *, revoked_at: datetime) -> bool:
        statement = (
            update(AdminSession)
            .where(AdminSession.id == admin_session_id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = await self._session.execute(statement)
        return result.rowcount > 0

    async def revoke_all_sessions_for_admin(self, admin_user_id: uuid.UUID, *, revoked_at: datetime) -> int:
        statement = (
            update(AdminSession)
            .where(AdminSession.admin_user_id == admin_user_id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = await self._session.execute(statement)
        return int(result.rowcount or 0)
