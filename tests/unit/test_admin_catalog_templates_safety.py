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


def _catalog_records():
    provider_row = AdminProviderListRow(
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
    provider = AdminProviderDetail(**asdict(provider_row), route_summaries=(), pricing_summaries=())
    provider_summary = AdminProviderSummary(
        id=provider.id,
        provider=provider.provider,
        display_name=provider.display_name,
        enabled=True,
        base_url=provider.base_url,
        api_key_env_var=provider.api_key_env_var,
    )
    route_row = AdminRouteListRow(
        id=uuid.uuid4(),
        requested_model="gpt-safe-mini",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider="openai",
        upstream_model="gpt-safe-mini",
        priority=10,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities_summary="vision",
        notes="safe route note",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    route = AdminRouteDetail(**asdict(route_row), provider_config=provider_summary)
    pricing_row = AdminPricingRuleListRow(
        id=uuid.uuid4(),
        provider="openai",
        upstream_model="gpt-safe-mini",
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
        metadata_summary="source",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    pricing = AdminPricingRuleDetail(**asdict(pricing_row), provider_config=provider_summary)
    fx_row = AdminFxRateListRow(
        id=uuid.uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.920000000"),
        source="manual",
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=None,
        created_at=datetime.now(UTC),
    )
    fx_rate = AdminFxRateDetail(**asdict(fx_row))
    return provider, route, pricing, fx_rate


def test_admin_catalog_pages_render_only_safe_metadata(monkeypatch) -> None:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-that-must-not-render",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)
    app.state.db_sessionmaker = _FakeSessionmaker()
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="password_hash_must_not_render",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session_hash_must_not_render",
        csrf_token_hash="csrf_hash_must_not_render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user
    provider, route, pricing, fx_rate = _catalog_records()

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    async def list_providers(self, **kwargs):
        return [provider]

    async def get_provider_detail(self, provider_config_id):
        return provider

    async def list_routes(self, **kwargs):
        return [route]

    async def get_route_detail(self, route_id):
        return route

    async def list_pricing_rules(self, **kwargs):
        return [pricing]

    async def get_pricing_rule_detail(self, pricing_rule_id):
        return pricing

    async def list_fx_rates(self, **kwargs):
        return [fx_rate]

    async def get_fx_rate_detail(self, fx_rate_id):
        return fx_rate

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_providers",
        list_providers,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_provider_detail",
        get_provider_detail,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_routes",
        list_routes,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_route_detail",
        get_route_detail,
    )
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
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "session-token-must-not-render")

    combined = "\n".join(
        [
            client.get("/admin/providers").text,
            client.get(f"/admin/providers/{provider.id}").text,
            client.get("/admin/routes").text,
            client.get(f"/admin/routes/{route.id}").text,
            client.get("/admin/pricing").text,
            client.get(f"/admin/pricing/{pricing.id}").text,
            client.get("/admin/fx").text,
            client.get(f"/admin/fx/{fx_rate.id}").text,
        ]
    )

    assert provider.provider in combined
    assert provider.api_key_env_var in combined
    assert route.requested_model in combined
    assert pricing.currency in combined
    assert "USD / EUR" in combined
    assert "password_hash_must_not_render" not in combined
    assert "session_hash_must_not_render" not in combined
    assert "session-token-must-not-render" not in combined
    assert settings.ADMIN_SESSION_SECRET not in combined
    assert settings.OPENAI_UPSTREAM_API_KEY not in combined
    assert settings.OPENROUTER_API_KEY not in combined
    assert "sk-provider-secret-placeholder" not in combined
    assert "sk-or-provider-secret-placeholder" not in combined
    assert "token_hash" not in combined
    assert "encrypted_payload" not in combined
    assert "nonce" not in combined
    assert "plaintext gateway key" not in combined.lower()
    assert "providersecret" not in combined
    assert "prompt text must not render" not in combined
    assert "completion text must not render" not in combined
