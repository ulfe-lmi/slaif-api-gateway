import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.db.models import FxRate, ModelRoute, PricingRule, ProviderConfig
from slaif_gateway.schemas import admin_catalog
from slaif_gateway.services.admin_catalog_dashboard import AdminCatalogDashboardService, AdminCatalogNotFoundError


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _provider(**overrides) -> ProviderConfig:
    values = {
        "id": uuid.uuid4(),
        "provider": "openai",
        "display_name": "OpenAI",
        "kind": "openai_compatible",
        "base_url": "https://api.openai.example/v1",
        "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
        "enabled": True,
        "timeout_seconds": 300,
        "max_retries": 2,
        "notes": "safe provider note",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return ProviderConfig(**values)


def _route(**overrides) -> ModelRoute:
    values = {
        "id": uuid.uuid4(),
        "requested_model": "gpt-test-mini",
        "match_type": "exact",
        "endpoint": "/v1/chat/completions",
        "provider": "openai",
        "upstream_model": "gpt-test-mini",
        "priority": 10,
        "enabled": True,
        "visible_in_models": True,
        "supports_streaming": True,
        "capabilities": {"vision": False},
        "notes": "safe route note",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return ModelRoute(**values)


def _pricing(**overrides) -> PricingRule:
    values = {
        "id": uuid.uuid4(),
        "provider": "openai",
        "upstream_model": "gpt-test-mini",
        "endpoint": "/v1/chat/completions",
        "currency": "EUR",
        "input_price_per_1m": Decimal("0.100000000"),
        "cached_input_price_per_1m": Decimal("0.050000000"),
        "output_price_per_1m": Decimal("0.200000000"),
        "reasoning_price_per_1m": None,
        "request_price": None,
        "pricing_metadata": {"source": "manual"},
        "valid_from": NOW - timedelta(days=1),
        "valid_until": None,
        "enabled": True,
        "source_url": "https://pricing.example.org/openai",
        "notes": "safe pricing note",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return PricingRule(**values)


def _fx(**overrides) -> FxRate:
    values = {
        "id": uuid.uuid4(),
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": Decimal("0.920000000"),
        "valid_from": NOW - timedelta(days=1),
        "valid_until": None,
        "source": "manual",
        "created_at": NOW,
    }
    values.update(overrides)
    return FxRate(**values)


class _ProvidersRepo:
    def __init__(self, row=None):
        self.row = row or _provider()
        self.list_kwargs = {}

    async def list_provider_configs_for_admin(self, **kwargs):
        self.list_kwargs = kwargs
        return [self.row]

    async def get_provider_config_for_admin_detail(self, provider_config_id):
        return self.row if provider_config_id == self.row.id else None

    async def get_provider_config_by_provider(self, provider):
        return self.row if provider == self.row.provider else None


class _RoutesRepo:
    def __init__(self, row=None):
        self.row = row or _route()
        self.list_kwargs = {}

    async def list_model_routes_for_admin(self, **kwargs):
        self.list_kwargs = kwargs
        return [self.row]

    async def get_model_route_for_admin_detail(self, route_id):
        return self.row if route_id == self.row.id else None


class _PricingRepo:
    def __init__(self, row=None):
        self.row = row or _pricing()
        self.list_kwargs = {}

    async def list_pricing_rules_for_admin(self, **kwargs):
        self.list_kwargs = kwargs
        return [self.row]

    async def get_pricing_rule_for_admin_detail(self, pricing_rule_id):
        return self.row if pricing_rule_id == self.row.id else None


class _FxRepo:
    def __init__(self, row=None):
        self.row = row or _fx()
        self.list_kwargs = {}

    async def list_fx_rates_for_admin(self, **kwargs):
        self.list_kwargs = kwargs
        return [self.row]

    async def get_fx_rate_for_admin_detail(self, fx_rate_id):
        return self.row if fx_rate_id == self.row.id else None


def _service(providers=None, routes=None, pricing=None, fx_rates=None) -> AdminCatalogDashboardService:
    return AdminCatalogDashboardService(
        provider_configs_repository=providers or _ProvidersRepo(),
        model_routes_repository=routes or _RoutesRepo(),
        pricing_rules_repository=pricing or _PricingRepo(),
        fx_rates_repository=fx_rates or _FxRepo(),
    )


@pytest.mark.asyncio
async def test_catalog_lists_return_safe_rows_and_pass_filters() -> None:
    providers = _ProvidersRepo()
    routes = _RoutesRepo()
    pricing = _PricingRepo()
    fx_rates = _FxRepo()
    service = _service(providers=providers, routes=routes, pricing=pricing, fx_rates=fx_rates)

    provider_rows = await service.list_providers(provider="openai", enabled=True, limit=25, offset=5)
    route_rows = await service.list_routes(
        provider="openai",
        requested_model="gpt",
        match_type="exact",
        enabled=True,
        visible=True,
        limit=25,
        offset=5,
    )
    pricing_rows = await service.list_pricing_rules(
        provider="openai",
        model="gpt",
        endpoint="/v1/chat/completions",
        currency="eur",
        enabled=True,
        active=True,
        limit=25,
        offset=5,
        now=NOW,
    )
    fx_rows = await service.list_fx_rates(
        base_currency="usd",
        quote_currency="eur",
        source="manual",
        active=True,
        limit=25,
        offset=5,
        now=NOW,
    )

    assert provider_rows[0].api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
    assert route_rows[0].capabilities_summary == "vision"
    assert pricing_rows[0].metadata_summary == "source"
    assert fx_rows[0].rate == Decimal("0.920000000")
    assert providers.list_kwargs == {"provider": "openai", "enabled": True, "limit": 25, "offset": 5}
    assert routes.list_kwargs["requested_model"] == "gpt"
    assert routes.list_kwargs["visible"] is True
    assert pricing.list_kwargs["currency"] == "EUR"
    assert pricing.list_kwargs["active"] is True
    assert fx_rates.list_kwargs["base_currency"] == "USD"
    assert fx_rates.list_kwargs["quote_currency"] == "EUR"


@pytest.mark.asyncio
async def test_catalog_details_return_safe_related_metadata() -> None:
    provider = _provider()
    route = _route(provider=provider.provider)
    pricing = _pricing(provider=provider.provider)
    fx_repo = _FxRepo()
    service = _service(
        providers=_ProvidersRepo(provider),
        routes=_RoutesRepo(route),
        pricing=_PricingRepo(pricing),
        fx_rates=fx_repo,
    )

    provider_detail = await service.get_provider_detail(provider.id)
    route_detail = await service.get_route_detail(route.id)
    pricing_detail = await service.get_pricing_rule_detail(pricing.id)
    fx_detail = await service.get_fx_rate_detail(fx_repo.row.id)

    assert provider_detail.route_summaries[0].requested_model == route.requested_model
    assert provider_detail.pricing_summaries[0].upstream_model == pricing.upstream_model
    assert route_detail.provider_config is not None
    assert route_detail.provider_config.api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
    assert pricing_detail.provider_config is not None
    assert pricing_detail.provider_config.provider == "openai"
    assert fx_detail.base_currency == "USD"


@pytest.mark.asyncio
async def test_catalog_missing_records_raise_safe_not_found() -> None:
    service = _service()

    with pytest.raises(AdminCatalogNotFoundError):
        await service.get_provider_detail(uuid.uuid4())
    with pytest.raises(AdminCatalogNotFoundError):
        await service.get_route_detail(uuid.uuid4())
    with pytest.raises(AdminCatalogNotFoundError):
        await service.get_pricing_rule_detail(uuid.uuid4())
    with pytest.raises(AdminCatalogNotFoundError):
        await service.get_fx_rate_detail(uuid.uuid4())


def test_catalog_dtos_do_not_expose_secret_field_names() -> None:
    dto_names = "\n".join(
        field
        for cls in (
            admin_catalog.AdminProviderListRow,
            admin_catalog.AdminProviderDetail,
            admin_catalog.AdminRouteListRow,
            admin_catalog.AdminRouteDetail,
            admin_catalog.AdminPricingRuleListRow,
            admin_catalog.AdminPricingRuleDetail,
            admin_catalog.AdminFxRateListRow,
            admin_catalog.AdminFxRateDetail,
        )
        for field in cls.__dataclass_fields__
    )
    assert "api_key_value" not in dto_names
    assert "token_hash" not in dto_names
    assert "encrypted_payload" not in dto_names
    assert "nonce" not in dto_names
