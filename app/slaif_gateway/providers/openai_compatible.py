"""Generic operator-defined OpenAI-compatible provider adapter."""

from __future__ import annotations

from slaif_gateway.providers.openai import OpenAIProviderAdapter


class OpenAICompatibleProviderAdapter(OpenAIProviderAdapter):
    """Reuse the OpenAI wire adapter while retaining the configured provider slug."""

    def _configured_api_key(self) -> str | None:
        """Require the exact operator-configured key; never use OpenAI fallback state."""
        return self._api_key
