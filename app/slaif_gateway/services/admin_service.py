"""Service helpers for admin user bootstrap operations."""

from __future__ import annotations

import uuid

from slaif_gateway.db.models import AdminUser
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.services.record_errors import DuplicateRecordError, RecordNotFoundError


class AdminService:
    """Small service layer for admin user CLI operations."""

    def __init__(
        self,
        *,
        admin_users_repository: AdminUsersRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._admin_users = admin_users_repository
        self._audit = audit_repository

    async def create_admin_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        is_superadmin: bool = False,
    ) -> AdminUser:
        normalized_email = _normalize_email(email)
        if await self._admin_users.get_admin_user_by_email(normalized_email) is not None:
            raise DuplicateRecordError("Admin user", "email")

        role = "superadmin" if is_superadmin else "admin"
        admin_user = await self._admin_users.create_admin_user(
            email=normalized_email,
            display_name=display_name.strip(),
            password_hash=password_hash,
            role=role,
            is_active=True,
        )
        await self._audit.add_audit_log(
            action="admin_user_created",
            entity_type="admin_user",
            entity_id=admin_user.id,
            new_values={
                "email": admin_user.email,
                "display_name": admin_user.display_name,
                "role": admin_user.role,
                "is_active": admin_user.is_active,
            },
        )
        return admin_user

    async def reset_admin_password(
        self,
        *,
        admin_user_id_or_email: str,
        password_hash: str,
    ) -> AdminUser:
        admin_user = await self._get_admin_user(admin_user_id_or_email)
        updated = await self._admin_users.set_admin_password_hash(admin_user.id, password_hash)
        if not updated:
            raise RecordNotFoundError("Admin user")
        await self._audit.add_audit_log(
            action="admin_user_password_reset",
            entity_type="admin_user",
            entity_id=admin_user.id,
            new_values={"password_changed": True},
        )
        refreshed = await self._admin_users.get_admin_user_by_id(admin_user.id)
        if refreshed is None:
            raise RecordNotFoundError("Admin user")
        return refreshed

    async def list_admin_users(self, *, limit: int) -> list[AdminUser]:
        return await self._admin_users.list_admin_users(limit=limit)

    async def _get_admin_user(self, admin_user_id_or_email: str) -> AdminUser:
        value = admin_user_id_or_email.strip()
        admin_user: AdminUser | None
        try:
            admin_user = await self._admin_users.get_admin_user_by_id(uuid.UUID(value))
        except ValueError:
            admin_user = await self._admin_users.get_admin_user_by_email(_normalize_email(value))
        if admin_user is None:
            raise RecordNotFoundError("Admin user")
        return admin_user


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("Email cannot be empty")
    return normalized
