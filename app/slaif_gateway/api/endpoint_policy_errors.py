"""Mapping helpers from endpoint policy errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.endpoint_policy_errors import EndpointPolicyError


def openai_error_from_endpoint_policy_error(error: EndpointPolicyError) -> OpenAICompatibleError:
    """Convert endpoint policy errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
    )

