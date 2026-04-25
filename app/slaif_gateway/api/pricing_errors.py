"""Mapping helpers from pricing domain errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.pricing_errors import PricingError


def openai_error_from_pricing_error(error: PricingError) -> OpenAICompatibleError:
    """Convert pricing and FX errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
        param=error.param,
    )
