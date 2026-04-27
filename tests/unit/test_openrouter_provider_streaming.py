from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import respx

from slaif_gateway.config import Settings
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter
from slaif_gateway.schemas.providers import ProviderRequest


def test_openrouter_streaming_uses_provider_key_and_parses_cost() -> None:
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    body = {"model": "client-model", "stream": True, "messages": []}
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
    sent_body = json.loads(sent.content)
    assert sent_body["stream"] is True
    assert sent_body["model"] == "anthropic/claude-test"
    assert body["model"] == "client-model"
