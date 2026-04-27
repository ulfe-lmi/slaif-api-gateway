from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import MissingProviderApiKeyError, ProviderConfigurationError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter
from slaif_gateway.schemas.routing import RouteResolutionResult


def test_factory_returns_openai_adapter() -> None:
    adapter = get_provider_adapter("openai", Settings(OPENAI_UPSTREAM_API_KEY="openai-key"))

    assert isinstance(adapter, OpenAIProviderAdapter)
    assert adapter._base_url == "https://api.openai.com/v1"


def test_factory_returns_openrouter_adapter() -> None:
    adapter = get_provider_adapter("openrouter", Settings(OPENROUTER_API_KEY="openrouter-key"))

    assert isinstance(adapter, OpenRouterProviderAdapter)
    assert adapter._base_url == "https://openrouter.ai/api/v1"


def test_factory_builds_openai_adapter_from_route_metadata(monkeypatch) -> None:
    monkeypatch.setenv("CLASSROOM_OPENAI_KEY", "configured-openai-key")
    route = RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-test-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_base_url="https://gateway-openai.example/v1/",
        provider_api_key_env_var="CLASSROOM_OPENAI_KEY",
        provider_timeout_seconds=17,
        provider_max_retries=3,
    )

    adapter = get_provider_adapter(route, Settings(OPENAI_UPSTREAM_API_KEY=None))

    assert isinstance(adapter, OpenAIProviderAdapter)
    assert adapter._base_url == "https://gateway-openai.example/v1"
    assert adapter._api_key == "configured-openai-key"
    assert adapter._timeout_seconds == 17
    assert adapter._max_retries == 3


def test_factory_builds_openrouter_adapter_from_provider_config_metadata(monkeypatch) -> None:
    monkeypatch.setenv("CLASSROOM_OPENROUTER_KEY", "configured-openrouter-key")
    provider_config = SimpleNamespace(
        provider="openrouter",
        base_url="https://gateway-openrouter.example/api/v1",
        api_key_env_var="CLASSROOM_OPENROUTER_KEY",
        timeout_seconds=23,
        max_retries=1,
    )

    adapter = get_provider_adapter(provider_config, Settings(OPENROUTER_API_KEY=None))

    assert isinstance(adapter, OpenRouterProviderAdapter)
    assert adapter._base_url == "https://gateway-openrouter.example/api/v1"
    assert adapter._api_key == "configured-openrouter-key"
    assert adapter._timeout_seconds == 23
    assert adapter._max_retries == 1


def test_factory_missing_configured_api_key_env_var_raises_safe_error(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_PROVIDER_KEY", raising=False)
    route = SimpleNamespace(provider="openai", api_key_env_var="MISSING_PROVIDER_KEY")

    with pytest.raises(MissingProviderApiKeyError) as exc_info:
        get_provider_adapter(route, Settings(OPENAI_UPSTREAM_API_KEY="fallback-must-not-be-used"))

    assert exc_info.value.provider == "openai"
    assert "fallback-must-not-be-used" not in exc_info.value.safe_message
    assert "MISSING_PROVIDER_KEY" not in exc_info.value.safe_message


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        get_provider_adapter("unknown", Settings())

    assert exc_info.value.error_code == "unsupported_provider"
