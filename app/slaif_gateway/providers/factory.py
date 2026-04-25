"""Provider adapter factory."""

from __future__ import annotations

from slaif_gateway.config import Settings
from slaif_gateway.providers.base import ProviderAdapter
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter


def get_provider_adapter(provider: str, settings: Settings) -> ProviderAdapter:
    """Return an adapter for a configured provider name."""
    normalized = provider.strip().lower()
    if normalized == "openai":
        return OpenAIProviderAdapter(settings)
    if normalized == "openrouter":
        return OpenRouterProviderAdapter(settings)
    raise ProviderConfigurationError(
        "Unsupported provider configured for route",
        provider=provider,
        error_code="unsupported_provider",
    )
