import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_catalog import (
    AdminPricingRuleDetail,
    AdminPricingRuleListRow,
    AdminProviderListRow,
    AdminProviderSummary,
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


def _pricing_detail(**overrides) -> AdminPricingRuleDetail:
    provider = _provider_choice()
    row = AdminPricingRuleListRow(
        id=uuid.uuid4(),
        provider=provider.provider,
        upstream_model="gpt-test-mini",
        endpoint="/v1/chat/completions",
        currency="EUR",
        input_price_per_1m=Decimal("0.100000000"),
        cached_input_price_per_1m=Decimal("0.050000000"),
        output_price_per_1m=Decimal("0.200000000"),
        reasoning_price_per_1m=None,
        request_price=Decimal("0.010000000"),
        enabled=True,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=None,
        source_url="https://pricing.example.org/openai",
        notes="safe pricing note",
        pricing_metadata={"source": "manual"},
        metadata_summary="source",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    values = asdict(row)
    values.update(overrides)
    return AdminPricingRuleDetail(
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
        "provider": "openai",
        "upstream_model": "gpt-test-mini",
        "endpoint": "/v1/chat/completions",
        "currency": "EUR",
        "input_price_per_1m": "0.100000000",
        "cached_input_price_per_1m": "0.050000000",
        "output_price_per_1m": "0.200000000",
        "reasoning_price_per_1m": "",
        "request_price": "0",
        "pricing_metadata": '{"source": "manual"}',
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_until": "",
        "enabled": "true",
        "source_url": "https://pricing.example.org/openai",
        "notes": "safe pricing note",
        "reason": "pricing update",
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


def test_pricing_rule_create_get_requires_login() -> None:
    client = TestClient(_app())

    response = client.get("/admin/pricing/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_pricing_rule_create_get_renders_csrf_form(monkeypatch) -> None:
    _patch_provider_choices(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/pricing/new")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "OPENAI_UPSTREAM_API_KEY" in response.text
    assert "provider key values" in response.text
    assert "sk-provider-secret" not in response.text


def test_pricing_rule_post_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def create_pricing_rule(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.create_pricing_rule",
        create_pricing_rule,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/pricing/new", data=_valid_form(csrf_token=""))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_pricing_rule_post_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def create_pricing_rule(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.create_pricing_rule",
        create_pricing_rule,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/pricing/new", data=_valid_form(csrf_token="wrong"))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_pricing_rule_valid_create_calls_service_with_decimal_values(monkeypatch) -> None:
    seen: dict[str, object] = {}
    pricing_rule_id = uuid.uuid4()
    _patch_provider_choices(monkeypatch)

    async def create_pricing_rule(self, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=pricing_rule_id)

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.create_pricing_rule",
        create_pricing_rule,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post("/admin/pricing/new", data=_valid_form(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/pricing/{pricing_rule_id}?message=pricing_rule_created"
    assert seen["provider"] == "openai"
    assert seen["model"] == "gpt-test-mini"
    assert seen["input_price_per_1m"] == Decimal("0.100000000")
    assert seen["request_price"] == Decimal("0")
    assert seen["pricing_metadata"] == {"source": "manual"}
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "pricing update"
    assert all(not isinstance(value, float) for value in seen.values())
    assert "api_key_value" not in seen


def test_pricing_rule_create_rejects_invalid_fields_before_service(monkeypatch) -> None:
    called = False
    _patch_provider_choices(monkeypatch)

    async def create_pricing_rule(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.create_pricing_rule",
        create_pricing_rule,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    invalid_decimal = client.post("/admin/pricing/new", data=_valid_form(input_price_per_1m="not-decimal"))
    negative_price = client.post("/admin/pricing/new", data=_valid_form(output_price_per_1m="-0.1"))
    invalid_currency = client.post("/admin/pricing/new", data=_valid_form(currency="EURO"))
    invalid_window = client.post(
        "/admin/pricing/new",
        data=_valid_form(valid_from="2026-02-01T00:00:00+00:00", valid_until="2026-01-01T00:00:00+00:00"),
    )
    missing_model = client.post("/admin/pricing/new", data=_valid_form(upstream_model=""))
    secret_metadata = client.post(
        "/admin/pricing/new",
        data=_valid_form(pricing_metadata='{"api_key": "sk-real-looking-secret"}'),
    )

    assert invalid_decimal.status_code == 400
    assert negative_price.status_code == 400
    assert invalid_currency.status_code == 400
    assert invalid_window.status_code == 400
    assert missing_model.status_code == 400
    assert secret_metadata.status_code == 400
    assert called is False


def test_pricing_rule_edit_get_renders_safe_current_values(monkeypatch) -> None:
    pricing = _pricing_detail()
    _patch_provider_choices(monkeypatch)

    async def get_pricing_rule_detail(self, pricing_rule_id):
        assert pricing_rule_id == pricing.id
        return pricing

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_pricing_rule_detail",
        get_pricing_rule_detail,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get(f"/admin/pricing/{pricing.id}/edit")

    assert response.status_code == 200
    assert pricing.upstream_model in response.text
    assert "OPENAI_UPSTREAM_API_KEY" in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "sk-provider-secret" not in response.text


def test_pricing_rule_edit_calls_service_with_actor_and_reason(monkeypatch) -> None:
    seen: dict[str, object] = {}
    pricing_rule_id = uuid.uuid4()
    _patch_provider_choices(monkeypatch)

    async def update_pricing_rule(self, pricing_or_id, **kwargs):
        seen["pricing_or_id"] = pricing_or_id
        seen.update(kwargs)
        return SimpleNamespace(id=pricing_rule_id)

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.update_pricing_rule",
        update_pricing_rule,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/pricing/{pricing_rule_id}/edit",
        data=_valid_form(output_price_per_1m="0.300000000"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/pricing/{pricing_rule_id}?message=pricing_rule_updated"
    assert seen["pricing_or_id"] == pricing_rule_id
    assert seen["output_price_per_1m"] == Decimal("0.300000000")
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "pricing update"


def test_pricing_rule_edit_rejects_secret_metadata_before_service(monkeypatch) -> None:
    called = False
    pricing_rule_id = uuid.uuid4()
    _patch_provider_choices(monkeypatch)

    async def update_pricing_rule(self, pricing_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.update_pricing_rule",
        update_pricing_rule,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/pricing/{pricing_rule_id}/edit",
        data=_valid_form(pricing_metadata='{"token_hash": "hash"}'),
    )

    assert response.status_code == 400
    assert "Enter valid pricing metadata." in response.text
    assert called is False


def test_pricing_rule_enable_requires_csrf(monkeypatch) -> None:
    called = False
    pricing_rule_id = uuid.uuid4()

    async def set_pricing_rule_enabled(self, pricing_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.set_pricing_rule_enabled",
        set_pricing_rule_enabled,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/pricing/{pricing_rule_id}/enable", data={"reason": "test"})

    assert response.status_code == 400
    assert called is False


def test_pricing_rule_disable_requires_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    pricing_rule_id = uuid.uuid4()

    async def set_pricing_rule_enabled(self, pricing_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.set_pricing_rule_enabled",
        set_pricing_rule_enabled,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/pricing/{pricing_rule_id}/disable",
        data={"csrf_token": "dashboard-csrf", "reason": "retire pricing"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/pricing/{pricing_rule_id}?message=pricing_rule_disable_confirmation_required"
    )
    assert called is False


def test_pricing_rule_enable_disable_call_service(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    pricing_rule_id = uuid.uuid4()

    async def set_pricing_rule_enabled(self, pricing_or_id, **kwargs):
        calls.append({"pricing_or_id": pricing_or_id, **kwargs})
        return SimpleNamespace(id=pricing_rule_id)

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.set_pricing_rule_enabled",
        set_pricing_rule_enabled,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    enable = client.post(
        f"/admin/pricing/{pricing_rule_id}/enable",
        data={"csrf_token": "dashboard-csrf", "reason": "ready"},
        follow_redirects=False,
    )
    disable = client.post(
        f"/admin/pricing/{pricing_rule_id}/disable",
        data={"csrf_token": "dashboard-csrf", "reason": "maintenance", "confirm_disable": "true"},
        follow_redirects=False,
    )

    assert enable.status_code == 303
    assert disable.status_code == 303
    assert calls[0]["enabled"] is True
    assert calls[1]["enabled"] is False
    assert calls[0]["actor_admin_id"] == admin_user.id
    assert calls[1]["actor_admin_id"] == admin_user.id
