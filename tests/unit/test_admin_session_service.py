import uuid
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.services.admin_session_service import (
    AdminAuthenticationError,
    AdminSessionError,
    AdminSessionService,
)
from slaif_gateway.utils.passwords import hash_admin_password


class _AdminUsersRepo:
    def __init__(self, admin_user: AdminUser | None) -> None:
        self.admin_user = admin_user
        self.last_login_at = None

    async def get_admin_user_by_email(self, email: str) -> AdminUser | None:
        if self.admin_user is not None and self.admin_user.email == email:
            return self.admin_user
        return None

    async def get_admin_user_by_id(self, admin_user_id: uuid.UUID) -> AdminUser | None:
        if self.admin_user is not None and self.admin_user.id == admin_user_id:
            return self.admin_user
        return None

    async def set_last_login_at(self, admin_user_id: uuid.UUID, last_login_at: datetime) -> bool:
        self.last_login_at = last_login_at
        if self.admin_user is not None and self.admin_user.id == admin_user_id:
            self.admin_user.last_login_at = last_login_at
            return True
        return False


class _AdminSessionsRepo:
    def __init__(self, admin_user: AdminUser | None) -> None:
        self.admin_user = admin_user
        self.admin_session = None

    async def create_admin_session(self, **kwargs) -> AdminSession:
        self.admin_session = AdminSession(id=uuid.uuid4(), **kwargs)
        if self.admin_user is not None:
            self.admin_session.admin_user = self.admin_user
        return self.admin_session

    async def get_admin_session_with_user_by_hash(self, session_token_hash: str) -> AdminSession | None:
        if self.admin_session is None:
            return None
        if self.admin_session.session_token_hash != session_token_hash:
            return None
        if self.admin_user is not None:
            self.admin_session.admin_user = self.admin_user
        return self.admin_session

    async def set_csrf_token_hash(self, admin_session_id: uuid.UUID, csrf_token_hash: str) -> bool:
        if self.admin_session is None or self.admin_session.id != admin_session_id:
            return False
        self.admin_session.csrf_token_hash = csrf_token_hash
        return True

    async def set_last_seen_at(self, admin_session_id: uuid.UUID, last_seen_at: datetime) -> bool:
        if self.admin_session is None or self.admin_session.id != admin_session_id:
            return False
        self.admin_session.last_seen_at = last_seen_at
        return True

    async def revoke_admin_session(self, admin_session_id: uuid.UUID, *, revoked_at: datetime) -> bool:
        if self.admin_session is None or self.admin_session.id != admin_session_id:
            return False
        self.admin_session.revoked_at = revoked_at
        return True


class _AuditRepo:
    def __init__(self) -> None:
        self.rows = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)
        return kwargs


def _admin_user(*, active: bool = True) -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash=hash_admin_password("correct horse"),
        role="admin",
        is_active=active,
    )


def _service(admin_user: AdminUser | None = None) -> tuple[AdminSessionService, _AdminSessionsRepo, _AuditRepo]:
    users = _AdminUsersRepo(admin_user)
    sessions = _AdminSessionsRepo(admin_user)
    audit = _AuditRepo()
    service = AdminSessionService(
        settings=Settings(APP_ENV="test", ADMIN_SESSION_SECRET="s" * 40, ADMIN_SESSION_TTL_SECONDS=60),
        admin_users_repository=users,
        admin_sessions_repository=sessions,
        audit_repository=audit,
    )
    return service, sessions, audit


@pytest.mark.asyncio
async def test_correct_password_authenticates() -> None:
    admin_user = _admin_user()
    service, _sessions, audit = _service(admin_user)

    result = await service.authenticate_admin(email="ADMIN@example.org", password="correct horse")

    assert result.id == admin_user.id
    assert audit.rows[-1]["action"] == "admin_login_succeeded"


@pytest.mark.asyncio
async def test_wrong_password_fails_safely() -> None:
    service, _sessions, audit = _service(_admin_user())

    with pytest.raises(AdminAuthenticationError):
        await service.authenticate_admin(email="admin@example.org", password="wrong")

    assert audit.rows[-1]["action"] == "admin_login_failed"


@pytest.mark.asyncio
async def test_inactive_admin_cannot_authenticate() -> None:
    service, _sessions, _audit = _service(_admin_user(active=False))

    with pytest.raises(AdminAuthenticationError):
        await service.authenticate_admin(email="admin@example.org", password="correct horse")


@pytest.mark.asyncio
async def test_create_session_stores_only_hashes() -> None:
    admin_user = _admin_user()
    service, sessions, _audit = _service(admin_user)

    created = await service.create_admin_session(admin_user_id=admin_user.id)

    assert created.session_token not in sessions.admin_session.session_token_hash
    assert created.csrf_token not in sessions.admin_session.csrf_token_hash
    assert sessions.admin_session.session_token_hash.startswith("sha256:")
    assert sessions.admin_session.csrf_token_hash.startswith("sha256:")


@pytest.mark.asyncio
async def test_validate_session_works_and_rejects_expired_or_revoked() -> None:
    admin_user = _admin_user()
    service, sessions, _audit = _service(admin_user)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    created = await service.create_admin_session(admin_user_id=admin_user.id, now=now)

    context = await service.validate_admin_session(session_token=created.session_token, now=now)
    assert context.admin_user.id == admin_user.id

    sessions.admin_session.expires_at = now - timedelta(seconds=1)
    with pytest.raises(AdminSessionError):
        await service.validate_admin_session(session_token=created.session_token, now=now)

    sessions.admin_session.expires_at = now + timedelta(seconds=60)
    sessions.admin_session.revoked_at = now
    with pytest.raises(AdminSessionError):
        await service.validate_admin_session(session_token=created.session_token, now=now)


@pytest.mark.asyncio
async def test_revoke_session_logs_out() -> None:
    admin_user = _admin_user()
    service, sessions, audit = _service(admin_user)
    created = await service.create_admin_session(admin_user_id=admin_user.id)

    assert await service.revoke_admin_session(session_token=created.session_token)
    assert sessions.admin_session.revoked_at is not None
    assert audit.rows[-1]["action"] == "admin_logout"


def test_plaintext_tokens_are_not_returned_in_hash_helpers() -> None:
    service, _sessions, _audit = _service(_admin_user())
    token = "plaintext-session-token"

    assert token not in service.hash_session_token(token)
    assert token not in service.hash_csrf_token(token)
