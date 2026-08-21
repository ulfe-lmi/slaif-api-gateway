"""Generic operator-defined OpenAI-compatible provider adapter."""

from __future__ import annotations

from slaif_gateway.providers.openai import OpenAIProviderAdapter


class OpenAICompatibleProviderAdapter(OpenAIProviderAdapter):
    """Reuse the OpenAI wire adapter while retaining the configured provider slug."""

    pass
