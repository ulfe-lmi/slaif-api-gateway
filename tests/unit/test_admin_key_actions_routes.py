import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse

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


def test_update_policy_requires_reason_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def update_gateway_key_policy(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_policy",
        update_gateway_key_policy,
    )

    async def render_key_policy_error(*args, **kwargs):
        return HTMLResponse(kwargs["error"], status_code=400)

    monkeypatch.setattr(
        "slaif_gateway.api.admin._render_key_policy_error",
        render_key_policy_error,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/policy",
        data={
            "csrf_token": "dashboard-csrf",
            "allowed_models": "gpt-5.2\ngpt-5.1",
            "allowed_endpoints": "/v1/models\n/v1/chat/completions",
        },
    )

    assert response.status_code == 400
    assert "Enter an audit reason before updating request policy" in response.text
    assert called is False


def test_update_policy_calls_key_service_with_actor_reason_and_policy(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def update_gateway_key_policy(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_policy",
        update_gateway_key_policy,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/policy",
        data={
            "csrf_token": "dashboard-csrf",
            "allowed_models": "gpt-5.2\ngpt-5.1",
            "allowed_endpoints": "/v1/models\n/v1/chat/completions",
            "reason": "fix swapped policy",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_policy_updated"
    payload = seen["payload"]
    assert payload.gateway_key_id == gateway_key_id
    assert payload.actor_admin_id == admin_user.id
    assert payload.reason == "fix swapped policy"
    assert payload.allowed_models == ["gpt-5.2", "gpt-5.1"]
    assert payload.allowed_endpoints == ["/v1/models", "/v1/chat/completions"]
    assert payload.allow_all_models is False
    assert payload.allow_all_endpoints is False


def test_update_chat_live_burn_disabled_blank_margins_preserves_existing(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()
    gateway_key = SimpleNamespace(
        id=gateway_key_id,
        metadata_json={
            "chat_streaming_live_burn": {
                "version": 1,
                "enabled": True,
                "cost_margin_eur": "-0.250000000",
                "token_margin": -250,
            },
            "rate_limit_policy": {"window_seconds": 30},
        },
    )

    class FakeKeysRepository:
        async def get_gateway_key_by_id(self, requested_gateway_key_id):
            assert requested_gateway_key_id == gateway_key_id
            return gateway_key

    class FakeKeyService:
        async def update_gateway_key_chat_streaming_live_burn(self, payload):
            seen["payload"] = payload

    @asynccontextmanager
    async def fake_runtime(request):
        yield FakeKeysRepository(), FakeKeyService()

    monkeypatch.setattr("slaif_gateway.api.admin._admin_key_management_runtime_scope", fake_runtime)
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/chat-streaming-live-burn",
        data={
            "csrf_token": "dashboard-csrf",
            "reason": "pause live burn",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/keys/{gateway_key_id}?message=key_chat_streaming_live_burn_updated"
    )
    payload = seen["payload"]
    assert payload.gateway_key_id == gateway_key_id
    assert payload.actor_admin_id == admin_user.id
    assert payload.reason == "pause live burn"
    assert payload.chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": False,
        "cost_margin_eur": "-0.250000000",
        "token_margin": -250,
    }


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
