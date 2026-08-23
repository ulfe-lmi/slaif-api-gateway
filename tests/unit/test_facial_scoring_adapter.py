from __future__ import annotations

import httpx
import pytest

from slaif_gateway.modules.facial_scoring import FacialScoringAdapter
from slaif_gateway.providers.errors import (
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderRequestError,
    ProviderResponseParseError,
    ProviderTimeoutError,
)
from slaif_gateway.schemas.providers import ProviderRequest


MODEL = "facial-manipulation-scoring"


def _request(url: str = "data:image/png;base64,AAAA", **body_fields: object) -> ProviderRequest:
    body: dict[str, object] = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "private text that must not leave the gateway"},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
        "max_completion_tokens": 4096,
    }
    body.update(body_fields)
    return ProviderRequest(
        provider="facial_scoring",
        upstream_model=MODEL,
        endpoint="chat.completions",
        body=body,
        request_id="request-id",
    )


def _adapter(handler) -> tuple[FacialScoringAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        FacialScoringAdapter(
            provider_name="facial_scoring",
            base_url="https://native.example",
            api_key="native-secret",
            timeout_seconds=7,
            max_retries=0,
            http_client=client,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_success_uses_exact_multipart_contract_and_returns_zero_usage() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = await request.aread()
        return httpx.Response(200, json={"status": "scored", "score": 0.8234}, request=request)

    adapter, client = _adapter(handler)
    try:
        response = await adapter.forward_chat_completion(_request())
    finally:
        await client.aclose()

    assert seen["url"] == "https://native.example/v1/score"
    headers = seen["headers"]
    assert headers["x-api-key"] == "native-secret"
    assert "authorization" not in headers
    multipart = seen["body"]
    assert b'name="image"' in multipart
    assert b'filename="image.png"' in multipart
    assert b"Content-Type: image/png" in multipart
    assert b"private text that must not leave the gateway" not in multipart
    assert response.json_body["model"] == MODEL
    assert response.json_body["choices"][0]["message"]["content"] == (
        "Score: 0.8234 (type: uncalibrated_model_score)"
    )
    assert response.json_body["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    assert response.usage is not None
    assert response.usage.total_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("media_type", "filename"),
    [("jpeg", "image.jpg"), ("webp", "image.webp"), ("gif", "image.gif")],
)
async def test_supported_media_gets_fixed_filename_and_type(media_type: str, filename: str) -> None:
    seen: dict[str, bytes] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = await request.aread()
        return httpx.Response(200, json={"status": "unscorable", "reason": "not enough evidence"})

    adapter, client = _adapter(handler)
    try:
        url = f"data:image/{media_type};base64,AAAA"
        response = await adapter.forward_chat_completion(_request(url))
    finally:
        await client.aclose()

    assert f'filename="{filename}"'.encode() in seen["body"]
    assert f"Content-Type: image/{media_type}".encode() in seen["body"]
    assert response.json_body["choices"][0]["message"]["content"] == (
        "Result: unscorable (not enough evidence)"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://operator.example/image.png",
        "file:///tmp/image.png",
        "data:image/svg+xml;base64,AAAA",
        "data:image/png;base64,not-base64!",
        "data:image/png;base64,",
    ],
)
async def test_only_nonempty_supported_base64_data_urls_are_admitted(url: str) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "scored", "score": 0.1})

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(ProviderRequestError) as exc_info:
            await adapter.forward_chat_completion(_request(url))
    finally:
        await client.aclose()

    assert exc_info.value.status_code == 400
    assert "operator.example" not in str(exc_info.value)
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body_fields",
    [
        {"stream": True},
        {"n": 2},
        {"tools": []},
        {"temperature": 0.2},
        {"messages": [{"role": "user", "content": "text only"}]},
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    ],
                }
            ]
        },
    ],
)
async def test_unsupported_shapes_are_rejected_before_native_call(body_fields: dict[str, object]) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "scored", "score": 0.1})

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(ProviderRequestError):
            await adapter.forward_chat_completion(_request(**body_fields))
    finally:
        await client.aclose()
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"status": "scored", "score": 2}, {"status": "unknown"}, {}])
async def test_malformed_score_result_is_safe_parse_error(payload: dict[str, object]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(ProviderResponseParseError) as exc_info:
            await adapter.forward_chat_completion(_request())
    finally:
        await client.aclose()
    assert "unknown" not in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_native_http_failure_does_not_expose_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": {"message": "private native body"}}, request=request)

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(ProviderHTTPError) as exc_info:
            await adapter.forward_chat_completion(_request())
    finally:
        await client.aclose()
    assert exc_info.value.upstream_status_code == 502
    assert "private native body" not in str(exc_info.value)
    assert exc_info.value.diagnostic is not None


@pytest.mark.asyncio
async def test_timeout_is_mapped_without_retry() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("native timeout", request=request)

    adapter, client = _adapter(handler)
    try:
        with pytest.raises(ProviderTimeoutError):
            await adapter.forward_chat_completion(_request())
    finally:
        await client.aclose()
    assert calls == 1


def test_constructor_rejects_retries() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        FacialScoringAdapter(
            provider_name="facial_scoring",
            base_url="https://native.example",
            api_key="native-secret",
            timeout_seconds=7,
            max_retries=1,
        )
    assert exc_info.value.error_code == "invalid_provider_configuration"
