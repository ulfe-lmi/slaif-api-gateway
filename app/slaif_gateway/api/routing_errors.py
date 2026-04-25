"""Mapping helpers from routing domain errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.services.routing_errors import RouteResolutionError


def openai_error_from_route_resolution_error(
    error: RouteResolutionError,
) -> OpenAICompatibleError:
    """Convert route resolution domain errors to OpenAI-compatible API exceptions."""
    return OpenAICompatibleError(
        error.safe_message,
        status_code=error.status_code,
        error_type=error.error_type,
        code=error.error_code,
    )
