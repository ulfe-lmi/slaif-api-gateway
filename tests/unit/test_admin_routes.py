import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import (
    CreatedAdminSession,
    AdminAuthenticationError,
    AdminSessionContext,
)


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


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _admin_user() -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
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


def test_get_admin_login_returns_html_and_csrf_token() -> None:
    client = TestClient(_app())

    response = client.get("/admin/login")

    assert response.status_code == 200
    assert "Admin Login" in response.text
    assert "csrf_token" in response.text
    assert "slaif_admin_login_csrf" in response.headers["set-cookie"]


def test_post_admin_login_success_sets_cookie_and_redirects(monkeypatch) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def authenticate_admin(self, **kwargs):
        return admin_user

    async def create_admin_session(self, **kwargs):
        return CreatedAdminSession(
            admin_user=admin_user,
            admin_session=admin_session,
            session_token="session-plaintext",
            csrf_token="csrf-plaintext",
            expires_at=admin_session.expires_at,
        )

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.authenticate_admin",
        authenticate_admin,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.create_admin_session",
        create_admin_session,
    )
    client = TestClient(_app())
    get_response = client.get("/admin/login")
    csrf_token = _csrf_from_html(get_response.text)

    response = client.post(
        "/admin/login",
        data={"email": admin_user.email, "password": "correct", "csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert "slaif_admin_session=session-plaintext" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]


def test_post_admin_login_wrong_password_fails_safely(monkeypatch) -> None:
    async def authenticate_admin(self, **kwargs):
        raise AdminAuthenticationError("Invalid email or password")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.authenticate_admin",
        authenticate_admin,
    )
    client = TestClient(_app())
    get_response = client.get("/admin/login")
    csrf_token = _csrf_from_html(get_response.text)

    response = client.post(
        "/admin/login",
        data={"email": "missing@example.org", "password": "wrong", "csrf_token": csrf_token},
    )

    assert response.status_code == 401
    assert "Invalid email or password." in response.text
    assert "missing@example.org" not in response.text


def test_get_admin_redirects_when_unauthenticated() -> None:
    response = TestClient(_app()).get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_get_admin_returns_dashboard_when_authenticated(monkeypatch) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client = TestClient(_app())
    client.cookies.set("slaif_admin_session", "session-plaintext")

    response = client.get("/admin")

    assert response.status_code == 200
    assert "Dashboard Foundation" in response.text
    assert "dashboard-csrf" in response.text


def test_post_admin_logout_requires_csrf(monkeypatch) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    client = TestClient(_app())
    client.cookies.set("slaif_admin_session", "session-plaintext")

    response = client.post("/admin/logout", data={"csrf_token": "bad"})

    assert response.status_code == 400
    assert "Invalid CSRF token" in response.text


def test_post_admin_logout_clears_cookie(monkeypatch) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)
    revoked = {"called": False}

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, session, csrf_token):
        return csrf_token == "valid-csrf"

    async def revoke_admin_session(self, **kwargs):
        revoked["called"] = True
        return True

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.revoke_admin_session",
        revoke_admin_session,
    )
    client = TestClient(_app())
    client.cookies.set("slaif_admin_session", "session-plaintext")

    response = client.post(
        "/admin/logout",
        data={"csrf_token": "valid-csrf"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert "slaif_admin_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert revoked["called"] is True


def test_admin_routes_disabled_when_feature_flag_is_off() -> None:
    client = TestClient(_app(_settings(ENABLE_ADMIN_DASHBOARD=False)))

    response = client.get("/admin/login")

    assert response.status_code == 404


def test_admin_login_without_session_secret_fails_safely() -> None:
    client = TestClient(_app(_settings(ADMIN_SESSION_SECRET=None)))

    response = client.get("/admin/login")

    assert response.status_code == 503
    assert "Admin login is not available." in response.text
