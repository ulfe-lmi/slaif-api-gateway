from __future__ import annotations

from slaif_gateway.api.provider_errors import openai_error_from_provider_error
from slaif_gateway.providers.errors import (
    MissingProviderApiKeyError,
    ProviderHTTPError,
    ProviderResponseParseError,
    ProviderTimeoutError,
    UnsupportedProviderEndpointError,
)


def test_missing_provider_key_maps_to_server_error() -> None:
    mapped = openai_error_from_provider_error(MissingProviderApiKeyError(provider="openai"))

    assert mapped.status_code == 500
    assert mapped.error_type == "server_error"
    assert mapped.code == "missing_provider_api_key"


def test_provider_http_error_uses_safe_upstream_status() -> None:
    mapped = openai_error_from_provider_error(
        ProviderHTTPError(provider="openai", upstream_status_code=429)
    )

    assert mapped.status_code == 429
    assert mapped.error_type == "server_error"
    assert mapped.code == "provider_http_error"


def test_timeout_maps_to_gateway_timeout() -> None:
    mapped = openai_error_from_provider_error(ProviderTimeoutError(provider="openrouter"))

    assert mapped.status_code == 504
    assert mapped.code == "provider_timeout"


def test_parse_error_maps_to_bad_gateway() -> None:
    mapped = openai_error_from_provider_error(ProviderResponseParseError(provider="openai"))

    assert mapped.status_code == 502
    assert mapped.code == "provider_response_parse_error"


def test_unsupported_endpoint_has_safe_metadata_only() -> None:
    error = UnsupportedProviderEndpointError(provider="openai")

    assert error.provider == "openai"
    assert error.status_code == 500
    assert error.error_code == "unsupported_provider_endpoint"
    assert "sk-" not in error.safe_message
    assert "Bearer" not in error.safe_message
