"""Safe schemas for provider adapter requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
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
