import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_catalog import AdminProviderDetail, AdminProviderListRow
from slaif_gateway.services.admin_session_service import AdminSessionContext


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

    async def refresh_csrf_token(self, **kwargs):
        return valid_csrf

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == valid_csrf

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def _provider_detail(**overrides) -> AdminProviderDetail:
    row = AdminProviderListRow(
        id=uuid.uuid4(),
        provider="openai",
        display_name="OpenAI",
        kind="openai_compatible",
        enabled=True,
        base_url="https://api.openai.example/v1",
        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
        timeout_seconds=300,
        max_retries=2,
        notes="safe provider note",
        route_count=None,
        pricing_rule_count=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    values = asdict(row)
    values.update(overrides)
    return AdminProviderDetail(**values, route_summaries=(), pricing_summaries=())


def _valid_form(**overrides) -> dict[str, str]:
    values = {
        "csrf_token": "dashboard-csrf",
        "provider": "openai",
        "display_name": "OpenAI",
        "kind": "openai_compatible",
        "base_url": "https://api.openai.example/v1",
        "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
        "enabled": "true",
        "timeout_seconds": "120",
        "max_retries": "1",
        "notes": "safe metadata",
        "reason": "catalog update",
    }
    values.update(overrides)
    return values


def test_provider_config_create_get_requires_login() -> None:
    client = TestClient(_app())

    response = client.get("/admin/providers/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_provider_config_create_get_renders_csrf_form(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/providers/new")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "api_key_env_var" in response.text
    assert "provider key value" in response.text
    assert "sk-provider-secret" not in response.text


def test_provider_config_post_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def create_provider_config(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.create_provider_config",
        create_provider_config,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/providers/new", data=_valid_form(csrf_token=""))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_provider_config_post_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def create_provider_config(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.create_provider_config",
        create_provider_config,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/providers/new", data=_valid_form(csrf_token="wrong"))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_provider_config_valid_create_calls_service_with_safe_metadata(monkeypatch) -> None:
    seen: dict[str, object] = {}
    provider_id = uuid.uuid4()

    async def create_provider_config(self, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=provider_id)

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.create_provider_config",
        create_provider_config,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post("/admin/providers/new", data=_valid_form(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/providers/{provider_id}?message=provider_config_created"
    assert seen["provider"] == "openai"
    assert seen["api_key_env_var"] == "OPENAI_UPSTREAM_API_KEY"
    assert "api_key_value" not in seen
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "catalog update"


def test_provider_config_create_rejects_secret_looking_env_var_before_service(monkeypatch) -> None:
    called = False

    async def create_provider_config(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.create_provider_config",
        create_provider_config,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/providers/new",
        data=_valid_form(api_key_env_var="sk-real-looking-secret"),
    )

    assert response.status_code == 400
    assert "environment variable name" in response.text
    assert called is False


def test_provider_config_edit_get_renders_safe_current_values(monkeypatch) -> None:
    provider = _provider_detail()

    async def get_provider_detail(self, provider_config_id):
        assert provider_config_id == provider.id
        return provider

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_provider_detail",
        get_provider_detail,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get(f"/admin/providers/{provider.id}/edit")

    assert response.status_code == 200
    assert provider.api_key_env_var in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "sk-provider-secret" not in response.text


def test_provider_config_edit_calls_service_with_actor_and_reason(monkeypatch) -> None:
    seen: dict[str, object] = {}
    provider_id = uuid.uuid4()

    async def update_provider_config(self, provider_or_id, **kwargs):
        seen["provider_or_id"] = provider_or_id
        seen.update(kwargs)
        return SimpleNamespace(id=provider_id)

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.update_provider_config",
        update_provider_config,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/providers/{provider_id}/edit",
        data=_valid_form(provider="openrouter", api_key_env_var="OPENROUTER_API_KEY"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/providers/{provider_id}?message=provider_config_updated"
    assert seen["provider_or_id"] == str(provider_id)
    assert seen["provider"] == "openrouter"
    assert seen["api_key_env_var"] == "OPENROUTER_API_KEY"
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "catalog update"


def test_provider_config_edit_rejects_secret_looking_env_var_before_service(monkeypatch) -> None:
    called = False
    provider_id = uuid.uuid4()

    async def update_provider_config(self, provider_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.update_provider_config",
        update_provider_config,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/providers/{provider_id}/edit",
        data=_valid_form(api_key_env_var="sk-or-real-looking-secret"),
    )

    assert response.status_code == 400
    assert "environment variable name" in response.text
    assert called is False


def test_provider_enable_requires_csrf(monkeypatch) -> None:
    called = False
    provider_id = uuid.uuid4()

    async def set_provider_enabled(self, provider_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.set_provider_enabled",
        set_provider_enabled,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/providers/{provider_id}/enable", data={"reason": "test"})

    assert response.status_code == 400
    assert called is False


def test_provider_disable_requires_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    provider_id = uuid.uuid4()

    async def set_provider_enabled(self, provider_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.set_provider_enabled",
        set_provider_enabled,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/providers/{provider_id}/disable",
        data={"csrf_token": "dashboard-csrf", "reason": "pause provider"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/providers/{provider_id}?message=provider_config_disable_confirmation_required"
    )
    assert called is False


def test_provider_enable_disable_call_service(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    provider_id = uuid.uuid4()

    async def set_provider_enabled(self, provider_or_id, **kwargs):
        calls.append({"provider_or_id": provider_or_id, **kwargs})
        return SimpleNamespace(id=provider_id)

    monkeypatch.setattr(
        "slaif_gateway.services.provider_config_service.ProviderConfigService.set_provider_enabled",
        set_provider_enabled,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    enable = client.post(
        f"/admin/providers/{provider_id}/enable",
        data={"csrf_token": "dashboard-csrf", "reason": "ready"},
        follow_redirects=False,
    )
    disable = client.post(
        f"/admin/providers/{provider_id}/disable",
        data={"csrf_token": "dashboard-csrf", "reason": "maintenance", "confirm_disable": "true"},
        follow_redirects=False,
    )

    assert enable.status_code == 303
    assert disable.status_code == 303
    assert calls[0]["enabled"] is True
    assert calls[1]["enabled"] is False
    assert calls[0]["actor_admin_id"] == admin_user.id
    assert calls[1]["actor_admin_id"] == admin_user.id
