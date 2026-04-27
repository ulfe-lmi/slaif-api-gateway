from __future__ import annotations

from slaif_gateway.providers.diagnostics import build_provider_error_diagnostic
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
    diagnostic = build_provider_error_diagnostic(
        provider="openai",
        upstream_status_code=429,
        body={
            "error": {
                "message": "rate limited sk-proj-secret",
                "type": "rate_limit_error",
                "code": "rate_limited",
                "metadata": {
                    "request_body": "user prompt body",
                    "authorization": "Bearer sk-secret",
                },
            }
        },
        headers={"x-request-id": "req-safe", "authorization": "Bearer sk-secret"},
    )
    mapped = openai_error_from_provider_error(
        ProviderHTTPError(provider="openai", upstream_status_code=429, diagnostic=diagnostic)
    )

    assert mapped.status_code == 429
    assert mapped.error_type == "server_error"
    assert mapped.code == "provider_http_error"
    assert "rate limited" not in mapped.message
    assert "sk-proj-secret" not in mapped.message
    assert diagnostic.upstream_error_type == "rate_limit_error"
    assert diagnostic.upstream_error_code == "rate_limited"
    metadata = diagnostic.to_safe_dict()
    metadata_text = str(metadata)
    assert "req-safe" in metadata_text
    assert "user prompt body" not in metadata_text
    assert "Bearer sk-secret" not in metadata_text
    assert "sk-proj-secret" not in metadata_text


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


def test_plain_text_provider_body_is_not_persisted_as_preview() -> None:
    diagnostic = build_provider_error_diagnostic(
        provider="openrouter",
        upstream_status_code=500,
        body="plain text containing user prompt body and sk-or-secret",
        headers={"x-openrouter-request-id": "or-req"},
    )

    assert diagnostic.upstream_request_id == "or-req"
    assert diagnostic.sanitized_body_preview is None
    assert "user prompt body" not in str(diagnostic.to_safe_dict())
    assert "sk-or-secret" not in str(diagnostic.to_safe_dict())
