"""OpenRouter provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import httpx

from slaif_gateway.config import Settings
from slaif_gateway.providers.base import ProviderAdapter
from slaif_gateway.providers.errors import (
    MissingProviderApiKeyError,
    ProviderHTTPError,
    ProviderRequestError,
    ProviderResponseParseError,
    ProviderTimeoutError,
    UnsupportedProviderEndpointError,
)
from slaif_gateway.providers.headers import build_provider_headers, safe_response_headers
from slaif_gateway.providers.streaming import parse_sse_lines
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderStreamChunk

_CHAT_COMPLETIONS_PATH = "/chat/completions"
_UPSTREAM_REQUEST_ID_HEADERS = ("x-request-id", "x-openrouter-request-id")


class OpenRouterProviderAdapter(ProviderAdapter):
    """Forward OpenAI-compatible requests to OpenRouter."""

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._http_client = http_client

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in {"/v1/chat/completions", "chat.completions"}:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)

        provider_api_key = self._api_key or self._settings.OPENROUTER_API_KEY
        if not provider_api_key:
            raise MissingProviderApiKeyError(provider=self.provider_name)

        body = dict(request.body)
        body["model"] = request.upstream_model
        headers = build_provider_headers(
            provider_api_key,
            provider=self.provider_name,
            request_id=request.request_id,
            extra_headers=request.extra_headers,
        )
        response = await self._post_json(_CHAT_COMPLETIONS_PATH, json=body, headers=headers)
        return self._provider_response(request, response)

    async def stream_chat_completion(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[ProviderStreamChunk]:
        if request.endpoint not in {"/v1/chat/completions", "chat.completions"}:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)

        provider_api_key = self._api_key or self._settings.OPENROUTER_API_KEY
        if not provider_api_key:
            raise MissingProviderApiKeyError(provider=self.provider_name)

        body = dict(request.body)
        body["model"] = request.upstream_model
        body["stream"] = True
        headers = build_provider_headers(
            provider_api_key,
            provider=self.provider_name,
            request_id=request.request_id,
            extra_headers=request.extra_headers,
        )

        async for chunk in self._stream_sse(_CHAT_COMPLETIONS_PATH, json=body, headers=headers):
            yield self._provider_stream_chunk(request, chunk)

    async def _post_json(
        self,
        path: str,
        *,
        json: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        timeout = self._timeout_seconds
        for attempt in range(self._max_retries + 1):
            try:
                if self._http_client is not None:
                    return await self._http_client.post(url, json=json, headers=headers, timeout=timeout)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    return await client.post(url, json=json, headers=headers)
            except httpx.TimeoutException as exc:
                if attempt >= self._max_retries:
                    raise ProviderTimeoutError(provider=self.provider_name) from exc
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise ProviderRequestError(provider=self.provider_name) from exc
            await asyncio.sleep(0)

        raise ProviderRequestError(provider=self.provider_name)

    async def _stream_sse(
        self,
        path: str,
        *,
        json: Mapping[str, Any],
        headers: Mapping[str, str],
    ):
        url = f"{self._base_url}{path}"
        timeout = self._timeout_seconds
        try:
            if self._http_client is not None:
                async with self._http_client.stream(
                    "POST",
                    url,
                    json=json,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    async for event in self._stream_response_events(response):
                        yield event
                return

            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=json, headers=headers) as response:
                    async for event in self._stream_response_events(response):
                        yield event
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc

    async def _stream_response_events(self, response: httpx.Response):
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderHTTPError(
                provider=self.provider_name,
                upstream_status_code=response.status_code,
            )

        pending_lines: list[str] = []
        async for line in response.aiter_lines():
            pending_lines.append(line)
            if line == "":
                for event in parse_sse_lines(pending_lines):
                    yield response, event
                pending_lines = []

        if pending_lines:
            for event in parse_sse_lines(pending_lines):
                yield response, event

    def _provider_response(
        self,
        request: ProviderRequest,
        response: httpx.Response,
    ) -> ProviderResponse:
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderHTTPError(
                provider=self.provider_name,
                upstream_status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseParseError(provider=self.provider_name) from exc

        if not isinstance(payload, Mapping):
            raise ProviderResponseParseError(provider=self.provider_name)

        raw_cost_native, native_currency = _extract_openrouter_cost(payload)
        return ProviderResponse(
            provider=self.provider_name,
            upstream_model=request.upstream_model,
            status_code=response.status_code,
            json_body=dict(payload),
            headers=safe_response_headers(response.headers),
            upstream_request_id=_upstream_request_id(response.headers, payload),
            usage=self.parse_usage(payload),
            raw_cost_native=raw_cost_native,
            native_currency=native_currency,
        )

    def _provider_stream_chunk(self, request: ProviderRequest, chunk) -> ProviderStreamChunk:
        response, event = chunk
        payload = event.json_body
        raw_cost_native, native_currency = _extract_openrouter_cost(payload or {})
        return ProviderStreamChunk(
            provider=self.provider_name,
            upstream_model=request.upstream_model,
            data=event.data,
            raw_sse_event=event.raw_event,
            json_body=payload,
            is_done=event.is_done,
            usage=self.parse_usage(payload) if payload is not None else None,
            upstream_request_id=_upstream_request_id(response.headers, payload or {}),
            raw_cost_native=raw_cost_native,
            native_currency=native_currency,
        )


def _upstream_request_id(headers: Mapping[str, str], payload: Mapping[str, Any]) -> str | None:
    for header_name in _UPSTREAM_REQUEST_ID_HEADERS:
        request_id = headers.get(header_name)
        if request_id:
            return request_id
    payload_id = payload.get("id")
    return payload_id if isinstance(payload_id, str) else None


def _extract_openrouter_cost(payload: Mapping[str, Any]) -> tuple[Decimal | None, str | None]:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return None, None

    raw_cost = usage.get("cost")
    if raw_cost is None:
        raw_cost = usage.get("cost_usd")
    if raw_cost is None:
        return None, None

    try:
        cost = Decimal(str(raw_cost))
    except (InvalidOperation, ValueError):
        return None, None

    currency = usage.get("currency")
    if not isinstance(currency, str) or not currency:
        currency = "USD" if "cost_usd" in usage or "cost" in usage else None
    return cost, currency
