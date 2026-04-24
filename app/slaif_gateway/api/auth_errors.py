"""Mapping helpers from auth domain errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.auth_service import GatewayAuthError


def openai_error_from_auth_error(error: GatewayAuthError) -> OpenAICompatibleError:
    """Convert service-layer auth errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
    )
