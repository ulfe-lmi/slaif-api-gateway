"""Service helpers for admin user bootstrap operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from slaif_gateway.db.models import AdminUser
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
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
        admin_sessions_repository: AdminSessionsRepository,
    ) -> None:
        self._admin_users = admin_users_repository
        self._audit = audit_repository
        self._admin_sessions = admin_sessions_repository

    async def create_admin_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        is_superadmin: bool = False,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
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
        # 218-a: the GUI supplies the authenticated superadmin actor and
        # its explicit audit reason; the offline CLI omits both, so its
        # audit rows keep their exact pre-218 shape.
        new_values: dict[str, object] = {
            "email": admin_user.email,
            "display_name": admin_user.display_name,
            "role": admin_user.role,
            "is_active": admin_user.is_active,
        }
        if reason is not None:
            new_values["reason"] = reason
        await self._audit.add_audit_log(
            action="admin_user_created",
            entity_type="admin_user",
            admin_user_id=actor_admin_id,
            entity_id=admin_user.id,
            new_values=new_values,
        )
        return admin_user

    async def reset_admin_password(
        self,
        *,
        admin_user_id_or_email: str,
        password_hash: str,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUser:
        admin_user = await self._get_admin_user(admin_user_id_or_email)
        # 218-a: take the target row lock (fresh ORM values) BEFORE any
        # mutation. This is the same lock AdminSessionService
        # authenticate_admin takes before password verification, so a
        # concurrent login/reset pair serializes on the row in EITHER
        # ordering: a login that started first holds the lock until its
        # session row is flushed (and the reset's revocation below then
        # catches that session); a reset that started first commits the
        # new hash before the login's fresh locked read verifies.
        locked = await self._admin_users.get_admin_user_for_update(admin_user.id)
        if locked is None:
            raise RecordNotFoundError("Admin user")
        updated = await self._admin_users.set_admin_password_hash(locked.id, password_hash)
        if not updated:
            raise RecordNotFoundError("Admin user")
        # 218-a: the reset deliberately revokes ALL of the target's
        # existing sessions in the SAME transaction as the hash change;
        # if the target is the acting admin, that includes the actor's
        # own session (the route then returns a secret-free outcome).
        # The revocation outcome key is chosen to survive the existing
        # audit-metadata sanitizer (session-/password-named keys are
        # dropped there by pre-218 law; the ACTION name plus actor,
        # target, and reason carry the accountability, and this counter
        # records the revocation outcome in committed metadata).
        revoked_count = await self._admin_sessions.revoke_all_sessions_for_admin(
            locked.id, revoked_at=datetime.now(UTC)
        )
        new_values: dict[str, object] = {
            "password_changed": True,
            "revoked_count": revoked_count,
        }
        if reason is not None:
            new_values["reason"] = reason
        await self._audit.add_audit_log(
            action="admin_user_password_reset",
            entity_type="admin_user",
            admin_user_id=actor_admin_id,
            entity_id=locked.id,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        refreshed = await self._admin_users.get_admin_user_by_id(locked.id)
        if refreshed is None:
            raise RecordNotFoundError("Admin user")
        return refreshed

    async def list_admin_users(
        self, *, limit: int, offset: int = 0
    ) -> list[AdminUser]:
        # 218-a: offset support for the bounded GUI list; the CLI
        # keeps its first-page call (offset defaults to 0).
        return await self._admin_users.list_admin_users(limit=limit, offset=offset)

    async def get_admin_user(self, admin_user_id_or_email: str) -> AdminUser:
        """218-a: shared bounded lookup (raises RecordNotFoundError).

        The GUI reset form uses this to display the SERVER-DERIVED
        identity of the fixed UUID target before the operator confirms;
        it performs no writes and no audit.
        """
        return await self._get_admin_user(admin_user_id_or_email)

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
