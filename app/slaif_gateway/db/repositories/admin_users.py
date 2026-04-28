"""Repository helpers for admin_users table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AdminUser


class AdminUsersRepository:
    """Encapsulates CRUD-style access for AdminUser rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_admin_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        role: str = "admin",
        is_active: bool = True,
    ) -> AdminUser:
        admin_user = AdminUser(
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )
        self._session.add(admin_user)
        await self._session.flush()
        return admin_user

    async def get_admin_user_by_id(self, admin_user_id: uuid.UUID) -> AdminUser | None:
        return await self._session.get(AdminUser, admin_user_id)

    async def get_admin_user_by_email(self, email: str) -> AdminUser | None:
        statement = select(AdminUser).where(AdminUser.email == email)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_admin_users(self, *, limit: int = 100, offset: int = 0) -> list[AdminUser]:
        statement: Select[tuple[AdminUser]] = (
            select(AdminUser).order_by(AdminUser.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_admin_password_hash(self, admin_user_id: uuid.UUID, password_hash: str) -> bool:
        admin_user = await self.get_admin_user_by_id(admin_user_id)
        if admin_user is None:
            return False
        admin_user.password_hash = password_hash
        await self._session.flush()
        return True

    async def set_admin_active(self, admin_user_id: uuid.UUID, is_active: bool) -> bool:
        admin_user = await self.get_admin_user_by_id(admin_user_id)
        if admin_user is None:
            return False
        admin_user.is_active = is_active
        await self._session.flush()
        return True

    async def set_last_login_at(self, admin_user_id: uuid.UUID, last_login_at: datetime) -> bool:
        admin_user = await self.get_admin_user_by_id(admin_user_id)
        if admin_user is None:
            return False
        admin_user.last_login_at = last_login_at
        await self._session.flush()
        return True
