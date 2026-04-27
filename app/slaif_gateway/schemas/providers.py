"""Safe schemas for provider adapter requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Basic token usage returned by an upstream provider."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    other_usage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Safe provider request envelope.

    This object intentionally excludes gateway keys, client Authorization
    headers, provider API keys, token hashes, and persistence details.
    """

    provider: str
    upstream_model: str
    endpoint: str
    body: Mapping[str, Any]
    request_id: str | None = None
    extra_headers: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Safe provider response envelope returned by adapters."""

    provider: str
    upstream_model: str
    status_code: int
    json_body: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)
    upstream_request_id: str | None = None
    usage: ProviderUsage | None = None
    raw_cost_native: Decimal | None = None
    native_currency: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderErrorDiagnostic:
    """Bounded, sanitized provider error details for operators.

    This structure is safe for logs and usage ledger metadata. It intentionally
    excludes provider keys, gateway keys, token hashes, request bodies, response
    bodies, prompts, completions, messages, choices, and tool payloads.
    """

    provider: str
    upstream_status_code: int | None = None
    upstream_error_type: str | None = None
    upstream_error_code: str | None = None
    upstream_request_id: str | None = None
    sanitized_message: str | None = None
    sanitized_body_preview: str | None = None
    response_headers: Mapping[str, str] = field(default_factory=dict)
    truncated: bool = False
    created_at: datetime | None = None

    def to_safe_dict(self) -> dict[str, object]:
        """Return JSON-safe diagnostic metadata."""
        payload: dict[str, object] = {
            "provider": self.provider,
            "truncated": self.truncated,
        }
        if self.upstream_status_code is not None:
            payload["upstream_status_code"] = self.upstream_status_code
        if self.upstream_error_type is not None:
            payload["upstream_error_type"] = self.upstream_error_type
        if self.upstream_error_code is not None:
            payload["upstream_error_code"] = self.upstream_error_code
        if self.upstream_request_id is not None:
            payload["upstream_request_id"] = self.upstream_request_id
        if self.sanitized_message is not None:
            payload["sanitized_message"] = self.sanitized_message
        if self.sanitized_body_preview is not None:
            payload["sanitized_body_preview"] = self.sanitized_body_preview
        if self.response_headers:
            payload["response_headers"] = dict(self.response_headers)
        if self.created_at is not None:
            payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class ProviderStreamChunk:
    """Safe provider streaming chunk envelope.

    The raw event/data values are provider response data only. This schema
    intentionally excludes gateway keys, provider keys, token hashes, and
    request/response persistence details.
    """

    provider: str
    upstream_model: str
    data: str
    raw_sse_event: str
    json_body: Mapping[str, Any] | None = None
    is_done: bool = False
    usage: ProviderUsage | None = None
    upstream_request_id: str | None = None
    raw_cost_native: Decimal | None = None
    native_currency: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderStreamSummary:
    """Safe summary of an upstream streaming response for accounting."""

    provider: str
    upstream_model: str
    upstream_request_id: str | None = None
    usage: ProviderUsage | None = None
    completed: bool = False
    interrupted: bool = False
    raw_cost_native: Decimal | None = None
    native_currency: str | None = None
