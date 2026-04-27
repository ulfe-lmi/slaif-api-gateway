"""Non-streaming OpenAI provider adapter."""

from __future__ import annotations

import asyncio
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
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse

_CHAT_COMPLETIONS_PATH = "/chat/completions"
_UPSTREAM_REQUEST_ID_HEADERS = ("x-request-id", "openai-request-id")


class OpenAIProviderAdapter(ProviderAdapter):
    """Forward non-streaming OpenAI-compatible requests to OpenAI."""

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str = "https://api.openai.com/v1",
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
        return "openai"

    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in {"/v1/chat/completions", "chat.completions"}:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)

        provider_api_key = self._api_key or self._settings.OPENAI_UPSTREAM_API_KEY
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

        return ProviderResponse(
            provider=self.provider_name,
            upstream_model=request.upstream_model,
            status_code=response.status_code,
            json_body=dict(payload),
            headers=safe_response_headers(response.headers),
            upstream_request_id=_upstream_request_id(response.headers, payload),
            usage=self.parse_usage(payload),
        )


def _upstream_request_id(headers: Mapping[str, str], payload: Mapping[str, Any]) -> str | None:
    for header_name in _UPSTREAM_REQUEST_ID_HEADERS:
        request_id = headers.get(header_name)
        if request_id:
            return request_id
    payload_id = payload.get("id")
    return payload_id if isinstance(payload_id, str) else None
