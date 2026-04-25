from __future__ import annotations

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter


def test_factory_returns_openai_adapter() -> None:
    adapter = get_provider_adapter("openai", Settings())

    assert isinstance(adapter, OpenAIProviderAdapter)


def test_factory_returns_openrouter_adapter() -> None:
    adapter = get_provider_adapter("openrouter", Settings())

    assert isinstance(adapter, OpenRouterProviderAdapter)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        get_provider_adapter("unknown", Settings())

    assert exc_info.value.error_code == "unsupported_provider"
