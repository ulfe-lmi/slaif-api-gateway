"""Bounded, operator-triggered discovery for generic OpenAI-compatible backends."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from slaif_gateway.db.models import ProviderConfig
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.providers.headers import build_provider_headers

MAX_DISCOVERY_RESPONSE_BYTES = 1_048_576
MAX_DISCOVERY_MODELS = 500
MAX_DISCOVERY_DEPTH = 8
MAX_DISCOVERY_FIELDS = 4_096
MAX_MODEL_ID_BYTES = 255

_BUILT_IN_PROVIDERS = frozenset({"openai", "openrouter"})
_SECRET_LIKE = re.compile(
    r"(?:^|[^a-z0-9])(?:bearer|basic|api[_-]?key|access[_-]?token|secret|password|cookie|authorization)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


class DiscoveryError(ValueError):
    """Safe operator-facing discovery failure with no upstream content."""


@dataclass(frozen=True, slots=True)
class DiscoveredModels:
    """Safe discovery result; upstream metadata is intentionally discarded."""

    provider: str
    models: tuple[str, ...]


class _HttpClient(Protocol):
    def stream(self, method: str, url: str, **kwargs: Any) -> Any: ...


def _safe_error(message: str) -> DiscoveryError:
    return DiscoveryError(message)


async def discover_openai_compatible_models(
    provider: ProviderConfig,
    *,
    http_client: _HttpClient | None = None,
    secret_lookup: Callable[[str], str | None] = os.getenv,
) -> DiscoveredModels:
    """Perform one bounded authenticated ``GET <base_url>/models`` call.

    The caller owns provider selection and any database transaction. This
    function only performs a read-only network preview and never persists the
    response or its metadata.
    """

    _validate_provider(provider)
    secret = secret_lookup(provider.api_key_env_var)
    if not secret or not secret.strip():
        raise _safe_error("Configured provider secret is unavailable")

    base_url = _validated_base_url(provider.base_url)
    url = f"{base_url}/models"
    headers = build_provider_headers(
        secret,
        provider.provider,
        accept="application/json",
        content_type=None,
    )
    timeout = httpx.Timeout(float(provider.timeout_seconds))
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    )
    if owns_client:
        # HTTPX supplies general-purpose defaults (User-Agent, cookies, and
        # connection negotiation headers). Discovery deliberately sends only
        # the provider authorization and JSON Accept headers.
        client.headers.clear()
        client.headers.update(headers)
    try:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if 300 <= response.status_code < 400:
                    raise _safe_error("Provider discovery redirects are not allowed")
                if not 200 <= response.status_code < 300:
                    raise _safe_error("Provider discovery returned an unsuccessful response")
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().split(";", 1)[0].strip() == "application/json":
                    raise _safe_error("Provider discovery response must be JSON")
                raw = await _bounded_response_bytes(response)
        except DiscoveryError:
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            raise _safe_error("Provider discovery request failed") from exc
    finally:
        if owns_client:
            await client.aclose()

    return _parse_discovery_response(provider.provider, raw)


class OpenAICompatibleDiscoveryService:
    """Repository-backed operator discovery service."""

    def __init__(
        self,
        *,
        provider_configs_repository: ProviderConfigsRepository,
        http_client: _HttpClient | None = None,
        secret_lookup: Callable[[str], str | None] = os.getenv,
    ) -> None:
        self._providers = provider_configs_repository
        self._http_client = http_client
        self._secret_lookup = secret_lookup

    async def discover(self, provider_or_id: str) -> DiscoveredModels:
        """Reload and discover one configured provider by slug or UUID."""

        provider = await self._get_provider(provider_or_id)
        if provider is None:
            raise _safe_error("Configured provider was not found")
        return await discover_openai_compatible_models(
            provider,
            http_client=self._http_client,
            secret_lookup=self._secret_lookup,
        )

    async def _get_provider(self, provider_or_id: str) -> ProviderConfig | None:
        value = provider_or_id.strip()
        try:
            import uuid

            return await self._providers.get_provider_config_by_id(uuid.UUID(value))
        except (ValueError, AttributeError):
            return await self._providers.get_provider_config_by_provider(value)


async def _bounded_response_bytes(response: Any) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError as exc:
            raise _safe_error("Provider discovery response length is invalid") from exc
        if parsed_length > MAX_DISCOVERY_RESPONSE_BYTES:
            raise _safe_error("Provider discovery response is too large")

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        if not isinstance(chunk, bytes):
            raise _safe_error("Provider discovery response is invalid")
        total += len(chunk)
        if total > MAX_DISCOVERY_RESPONSE_BYTES:
            raise _safe_error("Provider discovery response is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_provider(provider: ProviderConfig) -> None:
    if not provider.enabled:
        raise _safe_error("Configured provider is disabled")
    if provider.kind != "openai_compatible" or provider.provider in _BUILT_IN_PROVIDERS:
        raise _safe_error("Provider discovery is limited to generic OpenAI-compatible providers")
    if not provider.provider or not provider.api_key_env_var:
        raise _safe_error("Configured provider metadata is incomplete")


def _validated_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise _safe_error("Configured provider URL is invalid")
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/v1"
        or any(char.isspace() or ord(char) < 32 for char in normalized)
    ):
        raise _safe_error("Configured provider URL is invalid")
    return normalized


def _parse_discovery_response(provider: str, raw: bytes) -> DiscoveredModels:
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _safe_error("Provider discovery response is invalid JSON") from exc
    if _shape_size(decoded, depth=0) > MAX_DISCOVERY_FIELDS:
        raise _safe_error("Provider discovery response is too complex")
    if not isinstance(decoded, Mapping) or "data" not in decoded:
        raise _safe_error("Provider discovery response must contain a data list")
    rows = decoded.get("data")
    if not isinstance(rows, list) or len(rows) > MAX_DISCOVERY_MODELS:
        raise _safe_error("Provider discovery returned too many models")

    model_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or "id" not in row:
            raise _safe_error("Provider discovery model shape is invalid")
        model_id = row["id"]
        if not isinstance(model_id, str) or not model_id.strip():
            raise _safe_error("Provider discovery model identifier is invalid")
        if len(model_id.encode("utf-8")) > MAX_MODEL_ID_BYTES:
            raise _safe_error("Provider discovery model identifier is too long")
        if any(ord(char) < 32 or ord(char) == 127 for char in model_id):
            raise _safe_error("Provider discovery model identifier is invalid")
        if _looks_secret_or_url(model_id):
            raise _safe_error("Provider discovery model identifier is unsafe")
        if model_id in seen:
            raise _safe_error("Provider discovery returned duplicate models")
        seen.add(model_id)
        model_ids.append(model_id)
    return DiscoveredModels(provider=provider, models=tuple(model_ids))


def _shape_size(value: object, *, depth: int) -> int:
    if depth > MAX_DISCOVERY_DEPTH:
        raise _safe_error("Provider discovery response is too deeply nested")
    if isinstance(value, Mapping):
        return 1 + sum(1 + _shape_size(item, depth=depth + 1) for item in value.values())
    if isinstance(value, list):
        return 1 + sum(_shape_size(item, depth=depth + 1) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return 1
    raise _safe_error("Provider discovery response shape is invalid")


def _looks_secret_or_url(value: str) -> bool:
    lowered = value.lower()
    if "@" in value or "://" in value or lowered.startswith(("http:", "https:")):
        return True
    if _SECRET_LIKE.search(value):
        return True
    return lowered.startswith(("sk-", "sk_", "sk-or-"))
