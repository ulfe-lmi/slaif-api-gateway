"""Mapping helpers from quota domain errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.quota_errors import QuotaError


def openai_error_from_quota_error(error: QuotaError) -> OpenAICompatibleError:
    """Convert quota reservation errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
        param=error.param,
    )

