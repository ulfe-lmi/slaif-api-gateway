import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import (
    AdminAuthenticationError,
    AdminSessionContext,
    AdminSessionService,
)
from slaif_gateway.utils.passwords import hash_admin_password


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return self


class _FakeSessionmaker:
    def __call__(self):
        return _FakeSession()


class _AdminUsersRepo:
    def __init__(self, admin_user: AdminUser) -> None:
        self.admin_user = admin_user

    async def get_admin_user_by_email(self, email: str) -> AdminUser | None:
        if self.admin_user.email == email:
            return self.admin_user
        return None

    async def get_admin_user_by_id(self, admin_user_id: uuid.UUID) -> AdminUser | None:
        if self.admin_user.id == admin_user_id:
            return self.admin_user
        return None

    async def set_last_login_at(self, admin_user_id: uuid.UUID, last_login_at: datetime) -> bool:
        if self.admin_user.id != admin_user_id:
            return False
        self.admin_user.last_login_at = last_login_at
        return True


class _AdminSessionsRepo:
    async def create_admin_session(self, **kwargs):
        return AdminSession(id=uuid.uuid4(), **kwargs)

    async def get_admin_session_with_user_by_hash(self, session_token_hash: str):
        return None


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)

    async def count_recent_admin_login_failures(self, **kwargs) -> int:
        return 0

    async def get_latest_admin_login_lockout(self, **kwargs):
        return None


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _admin_user(*, role: str, active: bool = True) -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email=f"{role}@example.org",
        display_name=f"{role.title()} User",
        password_hash=hash_admin_password("correct horse"),
        role=role,
        is_active=active,
    )


def _admin_session(admin_user: AdminUser) -> AdminSession:
    session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.admin_user = admin_user
    return session


def _service(admin_user: AdminUser) -> AdminSessionService:
    audit = _AuditRepo()
    return AdminSessionService(
        settings=_settings(),
        admin_users_repository=_AdminUsersRepo(admin_user),
        admin_sessions_repository=_AdminSessionsRepo(),
        audit_repository=audit,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "superadmin"])
async def test_active_admin_roles_are_currently_full_operator_login_roles(role: str) -> None:
    """Current v1 policy: active admin and superadmin accounts both authenticate."""
    admin_user = _admin_user(role=role)
    service = _service(admin_user)

    result = await service.authenticate_admin(email=admin_user.email.upper(), password="correct horse")

    assert result.id == admin_user.id
    assert result.role == role


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "superadmin"])
async def test_inactive_admin_roles_cannot_authenticate(role: str) -> None:
    admin_user = _admin_user(role=role, active=False)
    service = _service(admin_user)

    with pytest.raises(AdminAuthenticationError):
        await service.authenticate_admin(email=admin_user.email, password="correct horse")


def test_active_normal_admin_can_use_representative_operator_action(monkeypatch) -> None:
    """Current v1 policy: role=admin is a full dashboard operator, not read-only RBAC."""
    admin_user = _admin_user(role="admin")
    admin_session = _admin_session(admin_user)
    seen: dict[str, object] = {}
    provider_id = uuid.uuid4()

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == "valid-csrf"

    async def create_provider_config(self, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=provider_id)

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.create_provider_config",
        create_provider_config,
    )
    client = TestClient(_app())
    client.cookies.set("slaif_admin_session", "session-plaintext")

    response = client.post(
        "/admin/providers/new",
        data={
            "csrf_token": "valid-csrf",
            "provider": "openai",
            "display_name": "OpenAI",
            "kind": "openai_compatible",
            "base_url": "https://api.openai.example/v1",
            "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
            "enabled": "true",
            "timeout_seconds": "120",
            "max_retries": "1",
            "notes": "safe metadata",
            "reason": "role semantics regression",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/providers/{provider_id}?message=provider_config_created"
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "role semantics regression"
    assert "session-plaintext" not in response.text
    assert "correct horse" not in response.text
