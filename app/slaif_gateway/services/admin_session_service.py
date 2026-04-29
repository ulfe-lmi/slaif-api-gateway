"""Admin web authentication and server-side session helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.services.admin_login_rate_limit import AdminLoginRateLimitService, normalize_admin_login_email
from slaif_gateway.utils.passwords import verify_admin_password

_SESSION_TOKEN_BYTES = 32
_CSRF_TOKEN_BYTES = 32


class AdminAuthenticationError(Exception):
    """Raised when admin authentication fails with a safe generic error."""


class AdminLoginRateLimitedError(AdminAuthenticationError):
    """Raised when admin login is temporarily blocked by failed-attempt policy."""


class AdminSessionError(Exception):
    """Raised when an admin session is missing, expired, revoked, or invalid."""


@dataclass(frozen=True, slots=True)
class CreatedAdminSession:
    """Safe session creation result with transient plaintext tokens."""

    admin_user: AdminUser
    admin_session: AdminSession
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AdminSessionContext:
    """Validated admin session context."""

    admin_user: AdminUser
    admin_session: AdminSession


class AdminSessionService:
    """Authenticate admin users and manage server-side admin sessions."""

    def __init__(
        self,
        *,
        settings: Settings,
        admin_users_repository: AdminUsersRepository,
        admin_sessions_repository: AdminSessionsRepository,
        audit_repository: AuditRepository,
        login_rate_limit_service: AdminLoginRateLimitService | None = None,
    ) -> None:
        self._settings = settings
        self._admin_users = admin_users_repository
        self._admin_sessions = admin_sessions_repository
        self._audit = audit_repository
        self._login_rate_limit = login_rate_limit_service or AdminLoginRateLimitService(
            settings=settings,
            audit_repository=audit_repository,
        )

    async def authenticate_admin(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> AdminUser:
        timestamp = _utcnow(now)
        normalized_email = normalize_admin_login_email(email)
        rate_limit = await self._login_rate_limit.check_login_allowed(
            normalized_email=normalized_email,
            ip_address=ip_address,
            now=timestamp,
        )
        if not rate_limit.allowed:
            await self._login_rate_limit.record_lockout_event(
                normalized_email=normalized_email,
                admin_user_id=None,
                ip_address=ip_address,
                user_agent=user_agent,
                now=timestamp,
            )
            raise AdminLoginRateLimitedError("Too many failed login attempts")

        admin_user = await self._admin_users.get_admin_user_by_email(normalized_email)
        password_matches = False
        if admin_user is not None and password:
            password_matches = verify_admin_password(password, admin_user.password_hash)
        authenticated = (
            admin_user is not None
            and admin_user.is_active
            and password_matches
        )
        if not authenticated:
            await self._login_rate_limit.record_failed_login(
                normalized_email=normalized_email,
                admin_user_id=admin_user.id if admin_user is not None else None,
                ip_address=ip_address,
                user_agent=user_agent,
                now=timestamp,
            )
            raise AdminAuthenticationError("Invalid email or password")

        await self._admin_users.set_last_login_at(admin_user.id, timestamp)
        await self._audit.add_audit_log(
            action="admin_login_succeeded",
            entity_type="admin_user",
            admin_user_id=admin_user.id,
            entity_id=admin_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        refreshed = await self._admin_users.get_admin_user_by_id(admin_user.id)
        return refreshed or admin_user

    async def create_admin_session(
        self,
        *,
        admin_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> CreatedAdminSession:
        timestamp = _utcnow(now)
        admin_user = await self._admin_users.get_admin_user_by_id(admin_user_id)
        if admin_user is None or not admin_user.is_active:
            raise AdminSessionError("Admin user is not active")

        session_token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        csrf_token = secrets.token_urlsafe(_CSRF_TOKEN_BYTES)
        expires_at = timestamp + timedelta(seconds=self._settings.ADMIN_SESSION_TTL_SECONDS)
        admin_session = await self._admin_sessions.create_admin_session(
            admin_user_id=admin_user.id,
            session_token_hash=self.hash_session_token(session_token),
            csrf_token_hash=self.hash_csrf_token(csrf_token),
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            last_seen_at=timestamp,
        )
        return CreatedAdminSession(
            admin_user=admin_user,
            admin_session=admin_session,
            session_token=session_token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    async def validate_admin_session(
        self,
        *,
        session_token: str,
        now: datetime | None = None,
        touch: bool = True,
    ) -> AdminSessionContext:
        timestamp = _utcnow(now)
        session_hash = self.hash_session_token(session_token)
        admin_session = await self._admin_sessions.get_admin_session_with_user_by_hash(session_hash)
        if admin_session is None:
            raise AdminSessionError("Admin session is invalid")
        if not hmac.compare_digest(admin_session.session_token_hash, session_hash):
            raise AdminSessionError("Admin session is invalid")
        if admin_session.revoked_at is not None:
            raise AdminSessionError("Admin session has been revoked")
        if admin_session.expires_at <= timestamp:
            raise AdminSessionError("Admin session has expired")
        if not admin_session.admin_user.is_active:
            raise AdminSessionError("Admin user is not active")
        if touch:
            await self._admin_sessions.set_last_seen_at(admin_session.id, timestamp)
        return AdminSessionContext(admin_user=admin_session.admin_user, admin_session=admin_session)

    async def refresh_csrf_token(
        self,
        *,
        admin_session_id: uuid.UUID,
    ) -> str:
        csrf_token = secrets.token_urlsafe(_CSRF_TOKEN_BYTES)
        updated = await self._admin_sessions.set_csrf_token_hash(
            admin_session_id,
            self.hash_csrf_token(csrf_token),
        )
        if not updated:
            raise AdminSessionError("Admin session is invalid")
        return csrf_token

    def verify_session_csrf_token(self, admin_session: AdminSession, csrf_token: str) -> bool:
        if not csrf_token:
            return False
        candidate_hash = self.hash_csrf_token(csrf_token)
        return hmac.compare_digest(admin_session.csrf_token_hash, candidate_hash)

    async def revoke_admin_session(
        self,
        *,
        session_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        timestamp = _utcnow(now)
        try:
            context = await self.validate_admin_session(session_token=session_token, now=timestamp, touch=False)
        except AdminSessionError:
            return False
        revoked = await self._admin_sessions.revoke_admin_session(
            context.admin_session.id,
            revoked_at=timestamp,
        )
        if revoked:
            await self._audit.add_audit_log(
                action="admin_logout",
                entity_type="admin_session",
                admin_user_id=context.admin_user.id,
                entity_id=context.admin_session.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return revoked

    def hash_session_token(self, session_token: str) -> str:
        return _hmac_token(self._require_admin_session_secret(), "admin-session", session_token)

    def hash_csrf_token(self, csrf_token: str) -> str:
        return _hmac_token(self._require_admin_session_secret(), "admin-csrf", csrf_token)

    def _require_admin_session_secret(self) -> str:
        secret = self._settings.ADMIN_SESSION_SECRET
        if not secret:
            raise AdminSessionError("ADMIN_SESSION_SECRET is required for admin sessions")
        return secret


def _hmac_token(secret: str, purpose: str, token: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{purpose}:{token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256:{digest}"


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
