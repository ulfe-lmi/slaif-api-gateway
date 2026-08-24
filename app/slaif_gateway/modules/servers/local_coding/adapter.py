"""Exact-byte OpenAI-compatible Responses transport for Local Coding."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Mapping

import httpx

from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.local_coding.contract import (
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.local_coding.identity import (
    LocalCodingRequestIdentity,
    make_nonce,
    sign_identity,
)
from slaif_gateway.providers.errors import (
    MissingProviderApiKeyError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderTimeoutError,
    UnsupportedProviderEndpointError,
)
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderStreamChunk


class LocalCodingAdapter(OpenAIProviderAdapter):
    """Forward one exact Responses byte sequence to a Local Coding service."""

    def __init__(
        self,
        settings: Settings,
        *,
        route_capabilities: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(settings, **kwargs)
        contract = parse_local_coding_route_contract(route_capabilities)
        if contract is None:
            raise ValueError("Local Coding route contract is unavailable")
        self._local_coding_contract = contract

    def _configured_api_key(self) -> str | None:
        """Use only the provider row's Local Coding service credential."""
        return self._api_key

    def _exact_body(self, request: ProviderRequest, *, stream: bool) -> bytes:
        body = dict(request.body)
        body["model"] = request.upstream_model
        if stream:
            body["stream"] = True
        try:
            encoded = json.dumps(
                body,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc
        if len(encoded) > self._local_coding_contract.max_body_bytes:
            raise ProviderRequestError(provider=self.provider_name)
        return encoded

    def _headers(
        self,
        request: ProviderRequest,
        *,
        body: bytes,
        accept: str,
    ) -> dict[str, str]:
        provider_api_key = self._configured_api_key()
        if not provider_api_key:
            raise MissingProviderApiKeyError(provider=self.provider_name)
        headers = {
            "Authorization": f"Bearer {provider_api_key}",
            "Accept": accept,
            "Content-Type": "application/json",
        }
        if request.request_id:
            headers["X-Request-ID"] = request.request_id
        context = request.server_context or {}
        if context.get("identity_mode") == "signed_identity_v1":
            identity = LocalCodingRequestIdentity(
                principal=str(context.get("principal", "")),
                session=str(context.get("session", "")),
                repository=str(context.get("repository", "")),
                route=str(context.get("route", "")),
                identity_mode="signed_identity_v1",
            )
            timestamp = str(int(time.time()))
            nonce = make_nonce(
                minimum=self._local_coding_contract.nonce_min_length,
                maximum=self._local_coding_contract.nonce_max_length,
            )
            try:
                headers.update(
                    sign_identity(
                        signing_secret=self._settings.local_coding_signing_secret(),
                        identity=identity,
                        body=body,
                        route=self._local_coding_contract,
                        timestamp=timestamp,
                        nonce=nonce,
                    )
                )
            except ValueError as exc:
                raise ProviderConfigurationError(
                    "Local Coding signed identity configuration is unavailable",
                    provider=self.provider_name,
                    error_code="local_coding_identity_configuration_invalid",
                ) from exc
        return headers

    async def forward_response(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in {"/v1/responses", "responses"}:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)
        body = self._exact_body(request, stream=False)
        headers = self._headers(request, body=body, accept="application/json")
        response = await self._post_exact(body=body, headers=headers)
        return self._provider_response(request, response)

    async def stream_response(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[ProviderStreamChunk]:
        if request.endpoint not in {"/v1/responses", "responses"}:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)
        body = self._exact_body(request, stream=True)
        headers = self._headers(request, body=body, accept="text/event-stream")
        async for chunk in self._stream_exact(request=request, body=body, headers=headers):
            yield chunk

    async def _post_exact(self, *, body: bytes, headers: Mapping[str, str]) -> httpx.Response:
        url = f"{self._base_url}/responses"
        try:
            if self._http_client is not None:
                return await self._http_client.post(
                    url,
                    content=body,
                    headers=headers,
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                )
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as client:
                return await client.post(url, content=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc

    async def _stream_exact(
        self,
        *,
        request: ProviderRequest,
        body: bytes,
        headers: Mapping[str, str],
    ) -> AsyncIterator[ProviderStreamChunk]:
        url = f"{self._base_url}/responses"
        try:
            if self._http_client is not None:
                async with self._http_client.stream(
                    "POST",
                    url,
                    content=body,
                    headers=headers,
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    async for event in self._stream_response_events(response):
                        yield self._provider_response_stream_chunk(request, event)
                return
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as client:
                async with client.stream("POST", url, content=body, headers=headers) as response:
                    async for event in self._stream_response_events(response):
                        yield self._provider_response_stream_chunk(request, event)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc
