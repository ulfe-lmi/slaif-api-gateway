from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import (
    ModelNotAllowedForKeyError,
    ModelNotFoundError,
    ModelRouteDisabledError,
    ProviderDisabledError,
    ProviderNotAllowedForKeyError,
    UnsupportedRouteMatchTypeError,
)


class FakeModelRoutesRepository:
    def __init__(self, routes: list[SimpleNamespace]) -> None:
        self._routes = routes

    async def list_model_routes(
        self,
        *,
        endpoint: str | None = None,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SimpleNamespace]:
        _ = (limit, offset)
        rows = self._routes
        if endpoint is not None:
            rows = [row for row in rows if row.endpoint == endpoint]
        if provider is not None:
            rows = [row for row in rows if row.provider == provider]
        return rows


class FakeProviderConfigsRepository:
    def __init__(self, providers: list[SimpleNamespace]) -> None:
        self._providers = providers

    async def list_provider_configs(self, *, enabled=None, limit=100, offset=0):
        _ = (limit, offset)
        rows = self._providers
        if enabled is not None:
            rows = [row for row in rows if row.enabled == enabled]
        return rows


def _make_key(
    *,
    allow_all_models: bool = True,
    allowed_models: tuple[str, ...] = (),
    allowed_providers: tuple[str, ...] | None = None,
) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=allow_all_models,
        allowed_models=allowed_models,
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=allowed_providers,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={
            "requests_per_minute": None,
            "tokens_per_minute": None,
            "max_concurrent_requests": None,
        },
    )


def _route(
    requested_model: str,
    *,
    match_type: str = "exact",
    provider: str = "openai",
    upstream_model: str | None = None,
    priority: int = 100,
    enabled: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        requested_model=requested_model,
        match_type=match_type,
        endpoint="/v1/chat/completions",
        provider=provider,
        upstream_model=upstream_model or requested_model,
        priority=priority,
        enabled=enabled,
    )


def _provider(
    provider: str,
    *,
    enabled: bool = True,
    timeout_seconds: int = 300,
    max_retries: int = 2,
) -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        enabled=enabled,
        base_url=f"https://{provider}.example/v1",
        api_key_env_var=f"{provider.upper()}_API_KEY",
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


@pytest.mark.asyncio
async def test_exact_route_resolves() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    result = await service.resolve_model("gpt-4.1-mini", _make_key())

    assert result.provider == "openai"
    assert result.resolved_model == "gpt-4.1-mini"
    assert result.provider_base_url == "https://openai.example/v1"
    assert result.provider_api_key_env_var == "OPENAI_API_KEY"
    assert result.provider_timeout_seconds == 300
    assert result.provider_max_retries == 2


@pytest.mark.asyncio
async def test_alias_style_route_resolves_to_upstream_model() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository(
            [_route("classroom-cheap", provider="openrouter", upstream_model="openai/gpt-4.1-mini")]
        ),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openrouter")]),
    )

    result = await service.resolve_model("classroom-cheap", _make_key())

    assert result.resolved_model == "openai/gpt-4.1-mini"


@pytest.mark.asyncio
async def test_prefix_route_resolves() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository(
            [_route("openai/", match_type="prefix", provider="openrouter")]
        ),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openrouter")]),
    )

    result = await service.resolve_model("openai/gpt-4.1-mini", _make_key())

    assert result.route_match_type == "prefix"


@pytest.mark.asyncio
async def test_glob_route_resolves() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository(
            [_route("anthropic/*", match_type="glob", provider="openrouter")]
        ),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openrouter")]),
    )

    result = await service.resolve_model("anthropic/claude-3.7-sonnet", _make_key())

    assert result.route_match_type == "glob"


@pytest.mark.asyncio
async def test_disabled_route_rejected() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini", enabled=False)]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    with pytest.raises(ModelRouteDisabledError):
        await service.resolve_model("gpt-4.1-mini", _make_key())


@pytest.mark.asyncio
async def test_disabled_provider_rejected() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai", enabled=False)]),
    )

    with pytest.raises(ProviderDisabledError):
        await service.resolve_model("gpt-4.1-mini", _make_key())


@pytest.mark.asyncio
async def test_route_priority_is_respected() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository(
            [
                _route("gpt-", match_type="prefix", priority=50, provider="openai"),
                _route("gpt-4.1-mini", match_type="exact", priority=100, provider="openrouter"),
            ]
        ),
        provider_configs_repository=FakeProviderConfigsRepository(
            [_provider("openai"), _provider("openrouter")]
        ),
    )

    result = await service.resolve_model("gpt-4.1-mini", _make_key())

    assert result.provider == "openai"
    assert result.priority == 50


@pytest.mark.asyncio
async def test_unknown_model_raises_model_not_found() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    with pytest.raises(ModelNotFoundError):
        await service.resolve_model("missing-model", _make_key())


@pytest.mark.asyncio
async def test_allowed_models_restriction_is_respected() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    with pytest.raises(ModelNotAllowedForKeyError):
        await service.resolve_model(
            "gpt-4.1-mini", _make_key(allow_all_models=False, allowed_models=("gpt-4o-mini",))
        )


@pytest.mark.asyncio
async def test_empty_allowed_models_rejects_all_models() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    with pytest.raises(ModelNotAllowedForKeyError):
        await service.resolve_model(
            "gpt-4.1-mini", _make_key(allow_all_models=False, allowed_models=())
        )


@pytest.mark.asyncio
async def test_allowed_providers_restriction_is_respected() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini", provider="openai")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    with pytest.raises(ProviderNotAllowedForKeyError):
        await service.resolve_model(
            "gpt-4.1-mini",
            _make_key(allowed_providers=("openrouter",)),
        )


@pytest.mark.asyncio
async def test_unsupported_match_type_raises() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository(
            [_route("gpt-4.1-mini", match_type="alias")]
        ),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    with pytest.raises(UnsupportedRouteMatchTypeError):
        await service.resolve_model("gpt-4.1-mini", _make_key())


@pytest.mark.asyncio
async def test_provider_api_key_values_not_exposed() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository([_route("gpt-4.1-mini")]),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openai")]),
    )

    result = await service.resolve_model("gpt-4.1-mini", _make_key())

    assert result.provider_api_key_env_var == "OPENAI_API_KEY"
    assert "sk-" not in (result.provider_api_key_env_var or "")


@pytest.mark.asyncio
async def test_no_hardcoded_broad_o_prefix_rule() -> None:
    service = RouteResolutionService(
        model_routes_repository=FakeModelRoutesRepository(
            [_route("openai/", match_type="prefix", provider="openrouter")]
        ),
        provider_configs_repository=FakeProviderConfigsRepository([_provider("openrouter")]),
    )

    with pytest.raises(ModelNotFoundError):
        await service.resolve_model("o3-mini", _make_key())
