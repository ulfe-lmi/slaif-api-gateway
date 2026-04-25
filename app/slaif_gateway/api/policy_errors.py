"""Mapping helpers from request-policy domain errors to OpenAI API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.policy_errors import RequestPolicyError


def openai_error_from_request_policy_error(error: RequestPolicyError) -> OpenAICompatibleError:
    """Convert request policy errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
        param=error.param,
    )
