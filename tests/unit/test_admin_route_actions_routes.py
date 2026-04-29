import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_catalog import (
    AdminProviderListRow,
    AdminProviderSummary,
    AdminRouteDetail,
    AdminRouteListRow,
)
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


def _provider_choice(**overrides) -> AdminProviderListRow:
    values = {
        "id": uuid.uuid4(),
        "provider": "openai",
        "display_name": "OpenAI",
        "kind": "openai_compatible",
        "enabled": True,
        "base_url": "https://api.openai.example/v1",
        "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
        "timeout_seconds": 300,
        "max_retries": 2,
        "notes": "safe provider note",
        "route_count": None,
        "pricing_rule_count": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return AdminProviderListRow(**values)


def _route_detail(**overrides) -> AdminRouteDetail:
    provider = _provider_choice()
    row = AdminRouteListRow(
        id=uuid.uuid4(),
        requested_model="gpt-test-mini",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider=provider.provider,
        upstream_model="gpt-test-mini",
        priority=10,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities={"vision": False},
        capabilities_summary="vision",
        notes="safe route note",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    values = asdict(row)
    values.update(overrides)
    return AdminRouteDetail(
        **values,
        provider_config=AdminProviderSummary(
            id=provider.id,
            provider=provider.provider,
            display_name=provider.display_name,
            enabled=provider.enabled,
            base_url=provider.base_url,
            api_key_env_var=provider.api_key_env_var,
        ),
    )


def _valid_form(**overrides) -> dict[str, str]:
    values = {
        "csrf_token": "dashboard-csrf",
        "requested_model": "gpt-test-mini",
        "match_type": "exact",
        "endpoint": "/v1/chat/completions",
        "provider": "openai",
        "upstream_model": "gpt-test-mini",
        "priority": "10",
        "enabled": "true",
        "visible_in_models": "true",
        "supports_streaming": "true",
        "capabilities": '{"vision": false}',
        "notes": "safe route note",
        "reason": "routing update",
    }
    values.update(overrides)
    return values


def _patch_provider_choices(monkeypatch, provider: AdminProviderListRow | None = None) -> None:
    async def list_providers(self, **kwargs):
        return [provider or _provider_choice()]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_providers",
        list_providers,
    )


def test_model_route_create_get_requires_login() -> None:
    client = TestClient(_app())

    response = client.get("/admin/routes/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_model_route_create_get_renders_csrf_form(monkeypatch) -> None:
    _patch_provider_choices(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/routes/new")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "OPENAI_UPSTREAM_API_KEY" in response.text
    assert "provider key values" in response.text
    assert "sk-provider-secret" not in response.text


def test_model_route_post_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def create_model_route(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.create_model_route",
        create_model_route,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/routes/new", data=_valid_form(csrf_token=""))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_model_route_post_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def create_model_route(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.create_model_route",
        create_model_route,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/routes/new", data=_valid_form(csrf_token="wrong"))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_model_route_valid_create_calls_service_with_safe_metadata(monkeypatch) -> None:
    seen: dict[str, object] = {}
    route_id = uuid.uuid4()
    _patch_provider_choices(monkeypatch)

    async def create_model_route(self, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=route_id)

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.create_model_route",
        create_model_route,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post("/admin/routes/new", data=_valid_form(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/routes/{route_id}?message=model_route_created"
    assert seen["requested_model"] == "gpt-test-mini"
    assert seen["match_type"] == "exact"
    assert seen["provider"] == "openai"
    assert seen["capabilities"] == {"vision": False}
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "routing update"
    assert "api_key_value" not in seen


def test_model_route_create_rejects_invalid_fields_before_service(monkeypatch) -> None:
    called = False
    _patch_provider_choices(monkeypatch)

    async def create_model_route(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.create_model_route",
        create_model_route,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    invalid_match = client.post("/admin/routes/new", data=_valid_form(match_type="regex"))
    invalid_priority = client.post("/admin/routes/new", data=_valid_form(priority="-1"))
    missing_model = client.post("/admin/routes/new", data=_valid_form(requested_model=""))
    secret_metadata = client.post(
        "/admin/routes/new",
        data=_valid_form(capabilities='{"api_key": "sk-real-looking-secret"}'),
    )

    assert invalid_match.status_code == 400
    assert invalid_priority.status_code == 400
    assert missing_model.status_code == 400
    assert secret_metadata.status_code == 400
    assert called is False


def test_model_route_edit_get_renders_safe_current_values(monkeypatch) -> None:
    route = _route_detail()
    _patch_provider_choices(monkeypatch)

    async def get_route_detail(self, route_id):
        assert route_id == route.id
        return route

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_route_detail",
        get_route_detail,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get(f"/admin/routes/{route.id}/edit")

    assert response.status_code == 200
    assert route.requested_model in response.text
    assert "OPENAI_UPSTREAM_API_KEY" in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "sk-provider-secret" not in response.text


def test_model_route_edit_calls_service_with_actor_and_reason(monkeypatch) -> None:
    seen: dict[str, object] = {}
    route_id = uuid.uuid4()
    _patch_provider_choices(monkeypatch)

    async def update_model_route(self, route_or_id, **kwargs):
        seen["route_or_id"] = route_or_id
        seen.update(kwargs)
        return SimpleNamespace(id=route_id)

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.update_model_route",
        update_model_route,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/routes/{route_id}/edit",
        data=_valid_form(upstream_model="gpt-upstream-mini"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/routes/{route_id}?message=model_route_updated"
    assert seen["route_or_id"] == route_id
    assert seen["upstream_model"] == "gpt-upstream-mini"
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "routing update"


def test_model_route_edit_rejects_secret_metadata_before_service(monkeypatch) -> None:
    called = False
    route_id = uuid.uuid4()
    _patch_provider_choices(monkeypatch)

    async def update_model_route(self, route_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.update_model_route",
        update_model_route,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/routes/{route_id}/edit",
        data=_valid_form(capabilities='{"token_hash": "hash"}'),
    )

    assert response.status_code == 400
    assert "secret-looking" in response.text
    assert called is False


def test_model_route_enable_requires_csrf(monkeypatch) -> None:
    called = False
    route_id = uuid.uuid4()

    async def set_model_route_enabled(self, route_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.set_model_route_enabled",
        set_model_route_enabled,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/routes/{route_id}/enable", data={"reason": "test"})

    assert response.status_code == 400
    assert called is False


def test_model_route_disable_requires_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    route_id = uuid.uuid4()

    async def set_model_route_enabled(self, route_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.set_model_route_enabled",
        set_model_route_enabled,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/routes/{route_id}/disable",
        data={"csrf_token": "dashboard-csrf", "reason": "pause route"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/routes/{route_id}?message=model_route_disable_confirmation_required"
    )
    assert called is False


def test_model_route_enable_disable_call_service(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    route_id = uuid.uuid4()

    async def set_model_route_enabled(self, route_or_id, **kwargs):
        calls.append({"route_or_id": route_or_id, **kwargs})
        return SimpleNamespace(id=route_id)

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.set_model_route_enabled",
        set_model_route_enabled,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    enable = client.post(
        f"/admin/routes/{route_id}/enable",
        data={"csrf_token": "dashboard-csrf", "reason": "ready"},
        follow_redirects=False,
    )
    disable = client.post(
        f"/admin/routes/{route_id}/disable",
        data={"csrf_token": "dashboard-csrf", "reason": "maintenance", "confirm_disable": "true"},
        follow_redirects=False,
    )

    assert enable.status_code == 303
    assert disable.status_code == 303
    assert calls[0]["enabled"] is True
    assert calls[1]["enabled"] is False
    assert calls[0]["actor_admin_id"] == admin_user.id
    assert calls[1]["actor_admin_id"] == admin_user.id
