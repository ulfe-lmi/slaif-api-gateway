import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.key_errors import GatewayKeyAlreadySuspendedError


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


def _login_for_actions(monkeypatch, client: TestClient, *, valid_csrf: str = "dashboard-csrf") -> AdminUser:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == valid_csrf

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def test_unauthenticated_key_action_redirects_to_login() -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())

    response = client.post(f"/admin/keys/{gateway_key_id}/suspend", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_key_action_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def suspend_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.suspend_gateway_key",
        suspend_gateway_key,
    )
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/keys/{gateway_key_id}/suspend")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_key_action_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def activate_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.activate_gateway_key",
        activate_gateway_key,
    )
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/activate",
        data={"csrf_token": "wrong"},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_suspend_calls_key_service_with_actor_and_reason(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def suspend_gateway_key(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.suspend_gateway_key",
        suspend_gateway_key,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/suspend",
        data={"csrf_token": "dashboard-csrf", "reason": "workshop pause"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_suspended"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "workshop pause"


def test_activate_calls_key_service_with_actor_and_reason(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def activate_gateway_key(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.activate_gateway_key",
        activate_gateway_key,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/activate",
        data={"csrf_token": "dashboard-csrf", "reason": "resume access"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_activated"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "resume access"


def test_revoke_requires_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def revoke_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.revoke_gateway_key",
        revoke_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/revoke",
        data={"csrf_token": "dashboard-csrf", "reason": "course ended"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/keys/{gateway_key_id}?message=revoke_confirmation_required"
    )
    assert called is False


def test_revoke_requires_reason_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def revoke_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.revoke_gateway_key",
        revoke_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/revoke",
        data={"csrf_token": "dashboard-csrf", "confirm_revoke": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=revoke_reason_required"
    assert called is False


def test_revoke_calls_key_service_with_actor_and_reason(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def revoke_gateway_key(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.revoke_gateway_key",
        revoke_gateway_key,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/revoke",
        data={
            "csrf_token": "dashboard-csrf",
            "reason": "course ended",
            "confirm_revoke": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_revoked"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "course ended"


def test_invalid_lifecycle_error_redirects_with_safe_message(monkeypatch) -> None:
    gateway_key_id = uuid.uuid4()

    async def suspend_gateway_key(self, payload):
        raise GatewayKeyAlreadySuspendedError()

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.suspend_gateway_key",
        suspend_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/suspend",
        data={"csrf_token": "dashboard-csrf"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/keys/{gateway_key_id}?message=gateway_key_already_suspended"
    )


def test_no_get_mutation_routes_exist(monkeypatch) -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    for action in ("suspend", "activate", "revoke"):
        response = client.get(f"/admin/keys/{gateway_key_id}/{action}")
        assert response.status_code == 405
