"""Outbound provider header construction and filtering."""

from __future__ import annotations

from collections.abc import Mapping

_SAFE_EXTRA_HEADERS = {
    "accept": "Accept",
    "content-type": "Content-Type",
    "x-request-id": "X-Request-ID",
}

_FORBIDDEN_HEADER_FRAGMENTS = (
    "authorization",
    "cookie",
    "csrf",
    "session",
    "password",
    "token",
    "secret",
    "admin",
    "gateway",
    "api-key",
    "apikey",
    "set-cookie",
)


def build_provider_headers(
    provider_api_key: str,
    provider: str,
    request_id: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
    accept: str = "application/json",
) -> dict[str, str]:
    """Build safe outbound headers for an upstream provider request."""
    _ = provider
    headers: dict[str, str] = {
        "Authorization": f"Bearer {provider_api_key}",
        "Content-Type": "application/json",
        "Accept": accept,
    }

    if extra_headers:
        for raw_name, value in extra_headers.items():
            normalized_name = raw_name.strip().lower()
            if not normalized_name or _is_forbidden_header(normalized_name):
                continue
            canonical_name = _SAFE_EXTRA_HEADERS.get(normalized_name)
            if canonical_name is None:
                continue
            headers[canonical_name] = value

    headers["Accept"] = accept

    if request_id:
        headers["X-Request-ID"] = request_id

    return headers


def safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return non-sensitive response headers useful to downstream callers."""
    safe: dict[str, str] = {}
    for raw_name, value in headers.items():
        normalized_name = raw_name.strip().lower()
        if _is_forbidden_header(normalized_name):
            continue
        canonical_name = _SAFE_EXTRA_HEADERS.get(normalized_name)
        if canonical_name is not None:
            safe[canonical_name] = value
            continue
        if normalized_name in {"x-request-id", "openai-request-id", "x-openrouter-request-id"}:
            safe[raw_name] = value
    return safe


def _is_forbidden_header(normalized_name: str) -> bool:
    return any(fragment in normalized_name for fragment in _FORBIDDEN_HEADER_FRAGMENTS)
