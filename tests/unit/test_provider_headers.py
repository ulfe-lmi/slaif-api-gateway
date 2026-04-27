from __future__ import annotations

from slaif_gateway.providers.headers import build_provider_headers, safe_response_headers


def test_provider_headers_inject_provider_authorization_and_safe_headers() -> None:
    headers = build_provider_headers(
        "upstream-secret",
        provider="openai",
        request_id="gw-123",
        extra_headers={
            "Authorization": "Bearer client-key",
            "Cookie": "session=value",
            "X-CSRF-Token": "csrf",
            "X-Admin-Session": "admin",
            "X-Token-Budget": "secret",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-ID": "client-request-id",
        },
    )

    assert headers["Authorization"] == "Bearer upstream-secret"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"
    assert headers["X-Request-ID"] == "gw-123"
    assert "Cookie" not in headers
    assert "X-CSRF-Token" not in headers
    assert "X-Admin-Session" not in headers
    assert "X-Token-Budget" not in headers
    assert "Bearer client-key" not in headers.values()


def test_secret_like_headers_are_not_forwarded_even_when_not_exact_matches() -> None:
    headers = build_provider_headers(
        "upstream-secret",
        provider="openrouter",
        extra_headers={
            "X-Api-Key": "api-key",
            "X-Provider-Secret": "secret",
            "X-Session-Id": "session",
            "X-Gateway-Key": "gateway",
            "User-Agent": "not-allowlisted",
        },
    )

    assert headers == {
        "Authorization": "Bearer upstream-secret",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def test_provider_headers_use_explicit_accept_over_client_header() -> None:
    headers = build_provider_headers(
        "upstream-secret",
        provider="openai",
        accept="text/event-stream",
        extra_headers={"Accept": "application/json"},
    )

    assert headers["Accept"] == "text/event-stream"


def test_safe_response_headers_drop_sensitive_values() -> None:
    headers = safe_response_headers(
        {
            "Content-Type": "application/json",
            "X-Request-ID": "upstream-request",
            "OpenAI-Request-ID": "openai-request",
            "Set-Cookie": "secret",
            "Authorization": "Bearer secret",
            "X-Secret": "secret",
        }
    )

    assert headers["Content-Type"] == "application/json"
    assert headers["X-Request-ID"] == "upstream-request"
    assert headers["OpenAI-Request-ID"] == "openai-request"
    assert "Set-Cookie" not in headers
    assert "Authorization" not in headers
    assert "X-Secret" not in headers
