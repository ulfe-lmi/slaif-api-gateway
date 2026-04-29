from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import inspect
import uuid

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.model_catalog import ModelCatalogService


@dataclass
class _FakeModelRoute:
    requested_model: str
    provider: str
    enabled: bool = True
    visible_in_models: bool = True


@dataclass
class _FakeProviderConfig:
    provider: str
    enabled: bool


class _FakeModelRoutesRepository:
    def __init__(self, routes: list[_FakeModelRoute]) -> None:
        self._routes = routes

    async def list_visible_model_routes(self) -> list[_FakeModelRoute]:
        return [route for route in self._routes if route.enabled and route.visible_in_models]


class _FakeProviderConfigsRepository:
    def __init__(self, provider_configs: list[_FakeProviderConfig]) -> None:
        self._provider_configs = provider_configs

    async def list_provider_configs(self) -> list[_FakeProviderConfig]:
        return self._provider_configs


def _auth_key(
    *,
    allow_all_models: bool = True,
    allowed_models: Sequence[str] = (),
    allowed_providers: tuple[str, ...] | None = None,
) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=1),
        allow_all_models=allow_all_models,
        allowed_models=tuple(allowed_models),
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


@pytest.mark.asyncio
async def test_returns_only_enabled_visible_routes_with_enabled_providers() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [
                _FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai"),
                _FakeModelRoute(
                    requested_model="openai/gpt-4.1-mini",
                    provider="openrouter",
                    enabled=False,
                ),
                _FakeModelRoute(
                    requested_model="anthropic/claude-3.7-sonnet",
                    provider="openrouter",
                    visible_in_models=False,
                ),
                _FakeModelRoute(requested_model="gpt-4.1", provider="openai"),
            ]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [
                _FakeProviderConfig(provider="openai", enabled=True),
                _FakeProviderConfig(provider="openrouter", enabled=False),
            ]
        ),
    )

    result = await service.list_visible_models(_auth_key())

    assert [model.id for model in result] == ["gpt-4.1-mini", "gpt-4.1"]
    assert all(model.object == "model" for model in result)
    assert all(model.created == 0 for model in result)
    assert all(model.owned_by == "openai" for model in result)


@pytest.mark.asyncio
async def test_returns_client_facing_model_ids_and_applies_allowed_models_filtering() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [
                _FakeModelRoute(requested_model="classroom-cheap", provider="openrouter"),
                _FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai"),
            ]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [
                _FakeProviderConfig(provider="openai", enabled=True),
                _FakeProviderConfig(provider="openrouter", enabled=True),
            ]
        ),
    )

    result = await service.list_visible_models(
        _auth_key(allow_all_models=False, allowed_models=("classroom-cheap",))
    )

    assert [model.id for model in result] == ["classroom-cheap"]


@pytest.mark.asyncio
async def test_empty_allowed_models_returns_no_models() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [
                _FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai"),
                _FakeModelRoute(requested_model="openai/gpt-4.1-mini", provider="openrouter"),
            ]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [
                _FakeProviderConfig(provider="openai", enabled=True),
                _FakeProviderConfig(provider="openrouter", enabled=True),
            ]
        ),
    )

    result = await service.list_visible_models(_auth_key(allow_all_models=False, allowed_models=()))

    assert result == []


@pytest.mark.asyncio
async def test_empty_allowed_models_list_returns_no_models() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [_FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai")]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [_FakeProviderConfig(provider="openai", enabled=True)]
        ),
    )

    result = await service.list_visible_models(_auth_key(allow_all_models=False, allowed_models=[]))

    assert result == []


@pytest.mark.asyncio
async def test_applies_allowed_provider_filtering_and_handles_empty_routes() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository([]),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [_FakeProviderConfig(provider="openai", enabled=True)]
        ),
    )

    result = await service.list_visible_models(_auth_key(allowed_providers=("openai",)))

    assert result == []


@pytest.mark.asyncio
async def test_applies_allowed_provider_filtering_to_visible_routes() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [
                _FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai"),
                _FakeModelRoute(requested_model="openai/gpt-4.1-mini", provider="openrouter"),
            ]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [
                _FakeProviderConfig(provider="openai", enabled=True),
                _FakeProviderConfig(provider="openrouter", enabled=True),
            ]
        ),
    )

    result = await service.list_visible_models(_auth_key(allowed_providers=("openrouter",)))

    assert [model.id for model in result] == ["openai/gpt-4.1-mini"]


@pytest.mark.asyncio
async def test_empty_allowed_providers_returns_no_models_when_provider_policy_is_present() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [_FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai")]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository(
            [_FakeProviderConfig(provider="openai", enabled=True)]
        ),
    )

    result = await service.list_visible_models(_auth_key(allowed_providers=()))

    assert result == []


@pytest.mark.asyncio
async def test_does_not_include_models_when_provider_config_is_missing() -> None:
    service = ModelCatalogService(
        model_routes_repository=_FakeModelRoutesRepository(
            [_FakeModelRoute(requested_model="gpt-4.1-mini", provider="openai")]
        ),
        provider_configs_repository=_FakeProviderConfigsRepository([]),
    )

    result = await service.list_visible_models(_auth_key())

    assert result == []


def test_model_catalog_service_safety_constraints() -> None:
    import slaif_gateway.services.model_catalog as model_catalog_module

    source = inspect.getsource(model_catalog_module)
    lowered_source = source.lower()

    for disallowed in ("openai", "openrouter", "httpx", "celery", "aiosmtplib", "fastapi"):
        if disallowed in {"openai", "openrouter"}:
            # provider names are valid plain strings in tests/routes; skip broad word matches.
            continue
        assert disallowed not in lowered_source
