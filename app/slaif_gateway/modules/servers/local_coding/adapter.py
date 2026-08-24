"""Exact-byte Responses-only transport for Local Coding."""

from __future__ import annotations

import hmac
import json
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx

from slaif_gateway.config import Settings, validate_local_coding_secret
from slaif_gateway.modules.servers.local_coding.contract import (
    LocalCodingRouteContract,
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.local_coding.identity import (
    LocalCodingRequestIdentity,
    make_nonce,
    sign_identity,
)
from slaif_gateway.providers.base import ProviderAdapter
from slaif_gateway.providers.diagnostics import (
    build_provider_error_diagnostic,
    build_provider_error_diagnostic_from_response,
)
from slaif_gateway.providers.errors import (
    MissingProviderApiKeyError,
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderRequestError,
    ProviderResponseParseError,
    ProviderTimeoutError,
    UnsupportedProviderEndpointError,
)
from slaif_gateway.providers.headers import safe_response_headers
from slaif_gateway.providers.streaming import parse_sse_lines
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderStreamChunk

_UPSTREAM_REQUEST_ID_HEADERS = ("x-request-id", "openai-request-id")


class LocalCodingAdapter(ProviderAdapter):
    """Forward only exact Responses create/stream operations to Local Coding."""

    def __init__(
        self,
        settings: Settings,
        *,
        route_capabilities: Mapping[str, object] | None = None,
        base_url: str = "https://local-coding.invalid/v1",
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 0,
        http_client: httpx.AsyncClient | None = None,
        provider_name: str = "local-coding",
    ) -> None:
        self._settings = settings
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._http_client = http_client
        self._provider_name = provider_name
        try:
            contract = parse_local_coding_route_contract(route_capabilities)
        except (TypeError, ValueError) as exc:
            raise ProviderConfigurationError(
                "Local Coding route contract is invalid",
                provider=provider_name,
                error_code="local_coding_route_contract_invalid",
            ) from exc
        if contract is None:
            raise ProviderConfigurationError(
                "Local Coding route contract is unavailable",
                provider=provider_name,
                error_code="local_coding_route_contract_invalid",
            )
        self._local_coding_contract = contract
        self._validate_secret_roles(contract)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        """Local Coding has no Chat Completions transport."""
        _ = request
        raise UnsupportedProviderEndpointError(provider=self.provider_name)

    def _validate_secret_roles(self, contract: LocalCodingRouteContract) -> None:
        if self._api_key is None:
            return
        try:
            service_secret = validate_local_coding_secret(self._api_key, "service credential")
        except (TypeError, ValueError) as exc:
            raise ProviderConfigurationError(
                "Local Coding service credential is invalid",
                provider=self.provider_name,
                error_code="local_coding_service_credential_invalid",
            ) from exc

        configured_secrets: list[bytes] = []
        if contract.identity_mode == "signed_identity_v1":
            try:
                configured_secrets.extend(
                    (
                        self._settings.local_coding_signing_secret(),
                        self._settings.local_coding_identity_derivation_secret(),
                    )
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise ProviderConfigurationError(
                    "Local Coding signed identity configuration is unavailable",
                    provider=self.provider_name,
                    error_code="local_coding_identity_configuration_invalid",
                ) from exc
        else:
            for value, label in (
                (self._settings.LOCAL_CODING_SIGNING_SECRET_V1, "signing"),
                (self._settings.LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1, "identity derivation"),
            ):
                if value:
                    try:
                        configured_secrets.append(validate_local_coding_secret(value, label))
                    except (TypeError, ValueError) as exc:
                        raise ProviderConfigurationError(
                            "Local Coding identity secret configuration is invalid",
                            provider=self.provider_name,
                            error_code="local_coding_identity_configuration_invalid",
                        ) from exc

        if len(configured_secrets) >= 2 and hmac.compare_digest(
            configured_secrets[0], configured_secrets[1]
        ):
            raise ProviderConfigurationError(
                "Local Coding secret roles are not separate",
                provider=self.provider_name,
                error_code="local_coding_secret_roles_not_separate",
            )
        if any(hmac.compare_digest(service_secret, secret) for secret in configured_secrets):
            raise ProviderConfigurationError(
                "Local Coding secret roles are not separate",
                provider=self.provider_name,
                error_code="local_coding_secret_roles_not_separate",
            )

        for value in (
            self._settings.TOKEN_HMAC_SECRET_V1,
            self._settings.TOKEN_HMAC_SECRET,
            self._settings.ADMIN_SESSION_SECRET,
            self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
            self._settings.OPENAI_UPSTREAM_API_KEY,
            self._settings.OPENROUTER_API_KEY,
            self._settings.OPENAI_ADMIN_DISCOVERY_API_KEY,
        ):
            if isinstance(value, str) and value and hmac.compare_digest(
                service_secret, value.encode("utf-8")
            ):
                raise ProviderConfigurationError(
                    "Local Coding secret roles are not separate",
                    provider=self.provider_name,
                    error_code="local_coding_secret_roles_not_separate",
                )

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
            except (AttributeError, TypeError, ValueError) as exc:
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
            ) as client, client.stream(
                "POST",
                url,
                content=body,
                headers=headers,
            ) as response:
                async for event in self._stream_response_events(response):
                    yield self._provider_response_stream_chunk(request, event)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc

    async def _stream_response_events(self, response: httpx.Response):
        if response.status_code < 200 or response.status_code >= 300:
            diagnostic = await build_provider_error_diagnostic_from_response(
                provider=self.provider_name,
                response=response,
            )
            raise ProviderHTTPError(
                provider=self.provider_name,
                upstream_status_code=response.status_code,
                diagnostic=diagnostic,
            )

        pending_lines: list[str] = []
        async for line in response.aiter_lines():
            pending_lines.append(line)
            if line == "":
                for event in parse_sse_lines(pending_lines):
                    self._raise_for_stream_error_event(response, event.json_body)
                    yield response, event
                pending_lines = []

        if pending_lines:
            for event in parse_sse_lines(pending_lines):
                self._raise_for_stream_error_event(response, event.json_body)
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
                diagnostic=build_provider_error_diagnostic(
                    provider=self.provider_name,
                    upstream_status_code=response.status_code,
                    body=_json_or_none(response),
                    headers=response.headers,
                ),
            )

        content_type = response.headers.get("content-type", "")
        payload: Mapping[str, Any] | None = None
        text_body: str | None = None
        if "json" in content_type:
            try:
                raw_payload = response.json()
            except ValueError as exc:
                raise ProviderResponseParseError(provider=self.provider_name) from exc
            if not isinstance(raw_payload, Mapping):
                raise ProviderResponseParseError(provider=self.provider_name)
            payload = dict(raw_payload)
        else:
            text_body = response.text

        return ProviderResponse(
            provider=self.provider_name,
            upstream_model=request.upstream_model,
            status_code=response.status_code,
            json_body=dict(payload or {}),
            text_body=text_body,
            content_type=content_type or None,
            headers=safe_response_headers(response.headers),
            upstream_request_id=_upstream_request_id(response.headers, payload or {}),
            usage=self.parse_usage(payload or {}),
        )

    def _raise_for_stream_error_event(
        self,
        response: httpx.Response,
        payload: Mapping[str, Any] | None,
    ) -> None:
        if not isinstance(payload, Mapping):
            return
        if "error" not in payload and payload.get("type") != "error":
            return
        raise ProviderHTTPError(
            provider=self.provider_name,
            upstream_status_code=response.status_code,
            diagnostic=build_provider_error_diagnostic(
                provider=self.provider_name,
                upstream_status_code=response.status_code,
                body=payload,
                headers=response.headers,
            ),
        )

    def _provider_response_stream_chunk(
        self,
        request: ProviderRequest,
        chunk,
    ) -> ProviderStreamChunk:
        response, event = chunk
        payload = event.json_body
        response_payload = _responses_event_response_payload(payload)
        usage_payload = response_payload if response_payload is not None else payload
        return ProviderStreamChunk(
            provider=self.provider_name,
            upstream_model=request.upstream_model,
            data=event.data,
            raw_sse_event=event.raw_event,
            json_body=payload,
            is_done=event.is_done,
            usage=self.parse_usage(usage_payload) if usage_payload is not None else None,
            upstream_request_id=_upstream_request_id(
                response.headers,
                response_payload or payload or {},
            ),
        )


def _upstream_request_id(headers: Mapping[str, str], payload: Mapping[str, Any]) -> str | None:
    for header_name in _UPSTREAM_REQUEST_ID_HEADERS:
        request_id = headers.get(header_name)
        if request_id:
            return request_id
    payload_id = payload.get("id")
    return payload_id if isinstance(payload_id, str) else None


def _json_or_none(response: httpx.Response) -> object | None:
    try:
        return response.json()
    except ValueError:
        return None


def _responses_event_response_payload(
    payload: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not isinstance(payload, Mapping) or payload.get("type") != "response.completed":
        return None
    response_payload = payload.get("response")
    return response_payload if isinstance(response_payload, Mapping) else None
