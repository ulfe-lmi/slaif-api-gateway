import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_catalog import (
    AdminFxRateDetail,
    AdminFxRateListRow,
    AdminPricingRuleDetail,
    AdminPricingRuleListRow,
    AdminProviderDetail,
    AdminProviderListRow,
    AdminProviderSummary,
    AdminRouteDetail,
    AdminRouteListRow,
)
from slaif_gateway.services.admin_catalog_dashboard import AdminCatalogNotFoundError
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


def _login(monkeypatch, client: TestClient) -> None:
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
    client.cookies.set("slaif_admin_session", "session-plaintext")


def _provider() -> AdminProviderDetail:
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
    return AdminProviderDetail(**asdict(row), route_summaries=(), pricing_summaries=())


def _route() -> AdminRouteDetail:
    provider = _provider()
    row = AdminRouteListRow(
        id=uuid.uuid4(),
        requested_model="gpt-test-mini",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider="openai",
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
    return AdminRouteDetail(
        **asdict(row),
        provider_config=AdminProviderSummary(
            id=provider.id,
            provider=provider.provider,
            display_name=provider.display_name,
            enabled=provider.enabled,
            base_url=provider.base_url,
            api_key_env_var=provider.api_key_env_var,
        ),
    )


def _pricing() -> AdminPricingRuleDetail:
    provider = _provider()
    row = AdminPricingRuleListRow(
        id=uuid.uuid4(),
        provider="openai",
        upstream_model="gpt-test-mini",
        endpoint="/v1/chat/completions",
        currency="EUR",
        input_price_per_1m=Decimal("0.100000000"),
        cached_input_price_per_1m=Decimal("0.050000000"),
        output_price_per_1m=Decimal("0.200000000"),
        reasoning_price_per_1m=None,
        request_price=None,
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
    return AdminPricingRuleDetail(
        **asdict(row),
        provider_config=AdminProviderSummary(
            id=provider.id,
            provider=provider.provider,
            display_name=provider.display_name,
            enabled=provider.enabled,
            base_url=provider.base_url,
            api_key_env_var=provider.api_key_env_var,
        ),
    )


def _fx() -> AdminFxRateDetail:
    row = AdminFxRateListRow(
        id=uuid.uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.920000000"),
        source="manual",
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=None,
        created_at=datetime.now(UTC),
    )
    return AdminFxRateDetail(**asdict(row))


def test_admin_catalog_routes_redirect_when_unauthenticated() -> None:
    client = TestClient(_app())

    for path in ("/admin/providers", "/admin/routes", "/admin/pricing", "/admin/fx"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_admin_provider_routes_return_html_and_accept_filters(monkeypatch) -> None:
    provider = _provider()
    seen: dict[str, object] = {}

    async def list_providers(self, **kwargs):
        seen.update(kwargs)
        return [provider]

    async def get_provider_detail(self, provider_config_id):
        assert provider_config_id == provider.id
        return provider

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_providers",
        list_providers,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_provider_detail",
        get_provider_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get("/admin/providers", params={"provider": "openai", "enabled": "true", "limit": "20"})
    detail = client.get(f"/admin/providers/{provider.id}")

    assert response.status_code == 200
    assert detail.status_code == 200
    assert "Provider Configs" in response.text
    assert provider.api_key_env_var in detail.text
    assert seen["provider"] == "openai"
    assert seen["enabled"] is True
    assert seen["limit"] == 20


def test_admin_route_routes_return_html_and_accept_filters(monkeypatch) -> None:
    route = _route()
    seen: dict[str, object] = {}

    async def list_routes(self, **kwargs):
        seen.update(kwargs)
        return [route]

    async def get_route_detail(self, route_id):
        assert route_id == route.id
        return route

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_routes",
        list_routes,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_route_detail",
        get_route_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(
        "/admin/routes",
        params={"provider": "openai", "requested_model": "gpt", "match_type": "exact", "visible": "true"},
    )
    detail = client.get(f"/admin/routes/{route.id}")

    assert response.status_code == 200
    assert detail.status_code == 200
    assert route.requested_model in response.text
    assert route.upstream_model in detail.text
    assert seen["requested_model"] == "gpt"
    assert seen["visible"] is True


def test_admin_pricing_and_fx_routes_return_html_and_accept_filters(monkeypatch) -> None:
    pricing = _pricing()
    fx_rate = _fx()
    seen_pricing: dict[str, object] = {}
    seen_fx: dict[str, object] = {}

    async def list_pricing_rules(self, **kwargs):
        seen_pricing.update(kwargs)
        return [pricing]

    async def get_pricing_rule_detail(self, pricing_rule_id):
        assert pricing_rule_id == pricing.id
        return pricing

    async def list_fx_rates(self, **kwargs):
        seen_fx.update(kwargs)
        return [fx_rate]

    async def get_fx_rate_detail(self, fx_rate_id):
        assert fx_rate_id == fx_rate.id
        return fx_rate

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_pricing_rules",
        list_pricing_rules,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_pricing_rule_detail",
        get_pricing_rule_detail,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_fx_rates",
        list_fx_rates,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_fx_rate_detail",
        get_fx_rate_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    pricing_list = client.get(
        "/admin/pricing",
        params={"provider": "openai", "model": "gpt", "currency": "EUR", "active": "true"},
    )
    pricing_detail = client.get(f"/admin/pricing/{pricing.id}")
    fx_list = client.get("/admin/fx", params={"base_currency": "USD", "quote_currency": "EUR"})
    fx_detail = client.get(f"/admin/fx/{fx_rate.id}")

    assert pricing_list.status_code == 200
    assert pricing_detail.status_code == 200
    assert fx_list.status_code == 200
    assert fx_detail.status_code == 200
    assert pricing.upstream_model in pricing_list.text
    assert pricing.currency in pricing_detail.text
    assert "USD / EUR" in fx_list.text
    assert "0.920000000" in fx_detail.text
    assert seen_pricing["model"] == "gpt"
    assert seen_pricing["active"] is True
    assert seen_fx["base_currency"] == "USD"
    assert seen_fx["quote_currency"] == "EUR"


def test_admin_catalog_missing_records_are_safe(monkeypatch) -> None:
    async def missing(self, record_id):
        raise AdminCatalogNotFoundError("missing")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_provider_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_route_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_pricing_rule_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_fx_rate_detail",
        missing,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    assert client.get("/admin/providers/not-a-uuid").status_code == 404
    assert client.get(f"/admin/providers/{uuid.uuid4()}").status_code == 404
    assert client.get("/admin/routes/not-a-uuid").status_code == 404
    assert client.get(f"/admin/routes/{uuid.uuid4()}").status_code == 404
    assert client.get("/admin/pricing/not-a-uuid").status_code == 404
    assert client.get(f"/admin/pricing/{uuid.uuid4()}").status_code == 404
    assert client.get("/admin/fx/not-a-uuid").status_code == 404
    assert client.get(f"/admin/fx/{uuid.uuid4()}").status_code == 404
