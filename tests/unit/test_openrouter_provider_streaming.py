from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx

from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import ProviderHTTPError
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter
from slaif_gateway.schemas.providers import ProviderRequest


def test_openrouter_streaming_uses_provider_key_and_parses_cost() -> None:
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    body = {
        "model": "client-model",
        "stream": True,
        "messages": [],
        "stream_options": {"include_usage": False},
    }
    request = ProviderRequest(
        provider="openrouter",
        upstream_model="anthropic/claude-test",
        endpoint="chat.completions",
        body=body,
        request_id="gw-123",
        extra_headers={"Authorization": "Bearer gateway-key"},
    )
    sse = (
        'data: {"id":"chunk-1","choices":[],"usage":{"prompt_tokens":3,'
        '"completion_tokens":4,"total_tokens":7,"cost_usd":"0.0012"}}\n\n'
        "data: [DONE]\n\n"
    )

    async def _collect():
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            upstream = router.post("https://openrouter.ai/api/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={"x-openrouter-request-id": "upstream-openrouter"},
                )
            )
            chunks = [chunk async for chunk in adapter.stream_chat_completion(request)]
            return upstream, chunks

    upstream, chunks = asyncio.run(_collect())

    assert chunks[0].usage is not None
    assert chunks[0].usage.total_tokens == 7
    assert chunks[0].raw_cost_native == Decimal("0.0012")
    assert chunks[0].native_currency == "USD"
    assert chunks[0].upstream_request_id == "upstream-openrouter"

    sent = upstream.calls[0].request
    assert sent.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert sent.headers["authorization"] != "Bearer gateway-key"
    assert sent.headers["accept"] == "text/event-stream"
    sent_body = json.loads(sent.content)
    assert sent_body["stream"] is True
    assert sent_body["stream_options"] == {"include_usage": True}
    assert sent_body["model"] == "anthropic/claude-test"
    assert body["model"] == "client-model"
    assert body["stream_options"]["include_usage"] is False


def test_openrouter_streaming_injects_usage_options_when_client_omits_them() -> None:
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    body = {
        "model": "client-model",
        "stream": True,
        "messages": [],
        "temperature": 0.2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
    }
    request = ProviderRequest(
        provider="openrouter",
        upstream_model="anthropic/claude-test",
        endpoint="chat.completions",
        body=body,
        request_id="gw-123",
        extra_headers={"Authorization": "Bearer gateway-key"},
    )

    async def _collect_request_body():
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            upstream = router.post("https://openrouter.ai/api/v1/chat/completions").mock(
                return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
            )
            _ = [chunk async for chunk in adapter.stream_chat_completion(request)]
            return json.loads(upstream.calls[0].request.content)

    sent_body = asyncio.run(_collect_request_body())

    assert sent_body["stream"] is True
    assert sent_body["stream_options"] == {"include_usage": True}
    assert sent_body["temperature"] == 0.2
    assert sent_body["tools"] == body["tools"]
    assert sent_body["tool_choice"] == "auto"
    assert sent_body["response_format"] == {"type": "json_object"}
    assert "stream_options" not in body


def test_openrouter_streaming_error_event_raises_safe_diagnostic() -> None:
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    request = ProviderRequest(
        provider="openrouter",
        upstream_model="anthropic/claude-test",
        endpoint="chat.completions",
        body={"model": "client-model", "stream": True, "messages": []},
        request_id="gw-123",
        extra_headers={"Authorization": "Bearer gateway-key"},
    )
    sse = (
        'data: {"error":{"message":"provider rejected sk-or-secret",'
        '"code":"bad_request","metadata":{"prompt":"user prompt body",'
        '"response_body":"assistant completion body"}}}\n\n'
    )

    async def _collect():
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.post("https://openrouter.ai/api/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={"x-openrouter-request-id": "or-stream-error"},
                )
            )
            return [chunk async for chunk in adapter.stream_chat_completion(request)]

    with pytest.raises(ProviderHTTPError) as exc_info:
        asyncio.run(_collect())

    assert exc_info.value.diagnostic is not None
    assert exc_info.value.diagnostic.upstream_error_code == "bad_request"
    assert exc_info.value.diagnostic.upstream_request_id == "or-stream-error"
    diagnostic_text = str(exc_info.value.diagnostic.to_safe_dict())
    assert "user prompt body" not in diagnostic_text
    assert "assistant completion body" not in diagnostic_text
    assert "sk-or-secret" not in diagnostic_text
