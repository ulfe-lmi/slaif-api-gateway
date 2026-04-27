"""Safe provider error diagnostics for operator-facing metadata."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from slaif_gateway.providers.headers import safe_response_headers
from slaif_gateway.schemas.providers import ProviderErrorDiagnostic
from slaif_gateway.utils.redaction import is_sensitive_key, redact_mapping, redact_text
from slaif_gateway.utils.sanitization import is_content_key, sanitize_metadata_mapping

_MAX_PREVIEW_CHARS = 1000
_BROAD_SK_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9._~+/=-]{4,}\b")
_UPSTREAM_REQUEST_ID_HEADERS = (
    "x-request-id",
    "openai-request-id",
    "x-openrouter-request-id",
    "cf-ray",
)


def build_provider_error_diagnostic(
    *,
    provider: str,
    upstream_status_code: int | None,
    body: object | None,
    headers: Mapping[str, str] | None = None,
) -> ProviderErrorDiagnostic:
    """Build bounded, sanitized provider diagnostics from a response body."""
    response_headers = _safe_diagnostic_headers(headers or {})
    error_payload = _error_payload(body)
    sanitized_message = _safe_message(error_payload.get("message"))
    sanitized_body_preview, truncated = sanitize_provider_error_body(body)

    return ProviderErrorDiagnostic(
        provider=provider,
        upstream_status_code=upstream_status_code,
        upstream_error_type=_safe_short_value(error_payload.get("type")),
        upstream_error_code=_safe_short_value(error_payload.get("code")),
        upstream_request_id=extract_upstream_request_id(headers or {}, body),
        sanitized_message=sanitized_message,
        sanitized_body_preview=sanitized_body_preview,
        response_headers=response_headers,
        truncated=truncated,
        created_at=datetime.now(UTC),
    )


async def build_provider_error_diagnostic_from_response(
    *,
    provider: str,
    response: httpx.Response,
) -> ProviderErrorDiagnostic:
    """Read an upstream error response and return safe diagnostics."""
    content = await response.aread()
    body = _body_from_response(response, content)
    return build_provider_error_diagnostic(
        provider=provider,
        upstream_status_code=response.status_code,
        body=body,
        headers=response.headers,
    )


def sanitize_provider_error_body(body: object | None) -> tuple[str | None, bool]:
    """Return a safe, bounded body preview.

    JSON bodies are recursively sanitized and content-bearing fields are dropped.
    Plain text provider bodies are deliberately not persisted because they can
    contain echoed prompts or completions without machine-readable field names.
    """
    if body is None:
        return None, False
    if isinstance(body, Mapping):
        sanitized = sanitize_metadata_mapping(_drop_diagnostic_fields(body), drop_content_keys=True)
        preview = _redact_provider_diagnostic_text(
            json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
        )
        return _truncate_preview(preview)
    if isinstance(body, list | tuple):
        sanitized = sanitize_metadata_mapping(
            {"body": _drop_diagnostic_fields(list(body))},
            drop_content_keys=True,
        )
        preview = _redact_provider_diagnostic_text(
            json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
        )
        return _truncate_preview(preview)
    return None, False


def extract_upstream_request_id(
    headers: Mapping[str, str],
    body: object | None = None,
) -> str | None:
    """Extract a safe upstream request ID from known headers or JSON fields."""
    lowered = {key.lower(): value for key, value in headers.items()}
    for header_name in _UPSTREAM_REQUEST_ID_HEADERS:
        value = lowered.get(header_name)
        if value:
            return _redact_provider_diagnostic_text(str(value))[:128]

    if isinstance(body, Mapping):
        for key in ("request_id", "id"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return _redact_provider_diagnostic_text(value)[:128]
    return None


def _body_from_response(response: httpx.Response, content: bytes) -> object | None:
    if not content:
        return None
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            parsed = json.loads(content.decode(response.encoding or "utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return parsed
    try:
        text = content.decode(response.encoding or "utf-8", errors="replace")
    except LookupError:
        text = content.decode("utf-8", errors="replace")
    return text


def _error_payload(body: object | None) -> Mapping[str, Any]:
    if not isinstance(body, Mapping):
        return {}
    error = body.get("error")
    if isinstance(error, Mapping):
        return error
    return body


def _safe_message(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return _truncate_preview(_redact_provider_diagnostic_text(value.strip()))[0]


def _safe_short_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
    else:
        cleaned = str(value).strip()
    if not cleaned:
        return None
    return _redact_provider_diagnostic_text(cleaned)[:128]


def _safe_diagnostic_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in redact_mapping(safe_response_headers(headers)).items()
        if isinstance(key, str)
    }


def _drop_diagnostic_fields(value: object) -> object:
    if isinstance(value, Mapping):
        safe: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if is_sensitive_key(key) or is_content_key(key):
                continue
            safe[key] = _drop_diagnostic_fields(item)
        return safe
    if isinstance(value, list | tuple):
        return [_drop_diagnostic_fields(item) for item in value]
    return value


def _truncate_preview(value: str) -> tuple[str, bool]:
    if len(value) <= _MAX_PREVIEW_CHARS:
        return value, False
    return value[:_MAX_PREVIEW_CHARS], True


def _redact_provider_diagnostic_text(value: str) -> str:
    return _BROAD_SK_TOKEN_PATTERN.sub("***", redact_text(value))
