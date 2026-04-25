"""Mapping helpers from key-management domain errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.key_errors import KeyManagementError


def openai_error_from_key_management_error(error: KeyManagementError) -> OpenAICompatibleError:
    """Convert service-layer key-management errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
        param=error.param,
    )
