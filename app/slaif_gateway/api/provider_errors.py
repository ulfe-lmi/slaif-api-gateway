"""Mapping helpers from provider domain errors to OpenAI-compatible API errors."""

from __future__ import annotations

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.providers.errors import ProviderError, ProviderHTTPError


def openai_error_from_provider_error(error: ProviderError) -> OpenAICompatibleError:
    """Convert provider adapter errors to OpenAI-compatible API exceptions."""
    status_code = error.status_code
    if isinstance(error, ProviderHTTPError) and error.upstream_status_code is not None:
        status_code = _safe_upstream_status(error.upstream_status_code)

    return OpenAICompatibleError(
        error.safe_message,
        status_code=status_code,
        error_type=error.error_type,
        code=error.error_code,
    )


def _safe_upstream_status(status_code: int) -> int:
    if 400 <= status_code <= 599:
        return status_code
    return 502
