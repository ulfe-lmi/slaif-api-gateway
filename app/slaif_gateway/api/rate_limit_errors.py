"""OpenAI-compatible mapping for Redis rate-limit domain errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.rate_limit_errors import RateLimitError


def openai_error_from_rate_limit_error(exc: RateLimitError) -> OpenAICompatibleError:
    """Return an OpenAI-shaped API error for Redis rate-limit failures."""
    return OpenAICompatibleError(
        exc.safe_message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        code=exc.error_code,
        param=exc.param,
    )
