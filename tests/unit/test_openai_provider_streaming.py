from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import MissingProviderApiKeyError
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.schemas.providers import ProviderRequest


def _request(body: dict[str, object] | None = None) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="gpt-test-mini",
        endpoint="chat.completions",
        body=body or {"model": "client-model", "stream": True, "messages": []},
        request_id="gw-123",
        extra_headers={"Authorization": "Bearer gateway-key", "X-Request-ID": "client-request"},
    )


def test_openai_streaming_sends_stream_true_and_parses_usage() -> None:
    original_body = {
        "model": "client-model",
        "stream": True,
        "messages": [],
        "stream_options": {"include_usage": False, "other": "preserved"},
    }
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    sse = (
        'data: {"id":"chunk-1","object":"chat.completion.chunk","choices":[]}\n\n'
        'data: {"id":"chunk-2","object":"chat.completion.chunk","choices":[],"usage":'
        '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
        "data: [DONE]\n\n"
    )

    async def _collect():
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            upstream = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, content=sse.encode(), headers={"x-request-id": "upstream"})
            )
            chunks = [chunk async for chunk in adapter.stream_chat_completion(_request(original_body))]
            return upstream, chunks

    upstream, chunks = asyncio.run(_collect())

    assert [chunk.data for chunk in chunks] == [
        '{"id":"chunk-1","object":"chat.completion.chunk","choices":[]}',
        '{"id":"chunk-2","object":"chat.completion.chunk","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}',
        "[DONE]",
    ]
    assert chunks[1].usage is not None
    assert chunks[1].usage.total_tokens == 11
    assert chunks[-1].is_done is True

    sent = upstream.calls[0].request
    assert sent.headers["authorization"] == "Bearer openai-upstream-key"
    assert sent.headers["authorization"] != "Bearer gateway-key"
    assert sent.headers["accept"] == "text/event-stream"
    sent_body = json.loads(sent.content)
    assert sent_body["stream"] is True
    assert sent_body["stream_options"] == {"include_usage": True, "other": "preserved"}
    assert sent_body["model"] == "gpt-test-mini"
    assert original_body["model"] == "client-model"
    assert original_body["stream_options"]["include_usage"] is False


def test_openai_streaming_missing_key_is_safe() -> None:
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY=None))

    async def _collect():
        return [chunk async for chunk in adapter.stream_chat_completion(_request())]

    with pytest.raises(MissingProviderApiKeyError) as exc_info:
        asyncio.run(_collect())

    assert "openai-upstream-key" not in str(exc_info.value)


def test_openai_streaming_injects_usage_options_when_client_omits_them() -> None:
    original_body = {
        "model": "client-model",
        "stream": True,
        "messages": [],
        "temperature": 0.2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
    }
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    async def _collect_request_body():
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            upstream = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
            )
            _ = [chunk async for chunk in adapter.stream_chat_completion(_request(original_body))]
            return json.loads(upstream.calls[0].request.content)

    sent_body = asyncio.run(_collect_request_body())

    assert sent_body["stream"] is True
    assert sent_body["stream_options"] == {"include_usage": True}
    assert sent_body["temperature"] == 0.2
    assert sent_body["tools"] == original_body["tools"]
    assert sent_body["tool_choice"] == "auto"
    assert sent_body["response_format"] == {"type": "json_object"}
    assert "stream_options" not in original_body
