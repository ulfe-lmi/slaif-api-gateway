from __future__ import annotations

import inspect
import json
from decimal import Decimal

import httpx
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import MissingProviderApiKeyError, ProviderHTTPError
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter
from slaif_gateway.schemas.providers import ProviderRequest


def _request(body: dict) -> ProviderRequest:
    return ProviderRequest(
        provider="openrouter",
        upstream_model="openai/gpt-4.1-mini",
        endpoint="/v1/chat/completions",
        body=body,
        request_id="gw-req",
        extra_headers={
            "Authorization": "Bearer client-key",
            "X-CSRF-Token": "csrf",
            "Accept": "application/json",
        },
    )


@pytest.mark.asyncio
async def test_missing_openrouter_api_key_raises() -> None:
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY=None))

    with pytest.raises(MissingProviderApiKeyError):
        await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))


@pytest.mark.asyncio
async def test_openrouter_chat_completion_posts_non_streaming_request(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen_123",
                "object": "chat.completion",
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "total_tokens": 15,
                    "cost_usd": "0.00042",
                },
            },
            headers={"X-OpenRouter-Request-ID": "req-openrouter"},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    caller_body = {
        "model": "client-model",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
        "x_unknown_json_compatible": {"preserved": True},
    }

    response = await adapter.forward_chat_completion(_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_request.headers["accept"] == "application/json"
    assert "x-csrf-token" not in sent_request.headers
    assert sent_request.headers["x-request-id"] == "gw-req"
    assert sent_body["model"] == "openai/gpt-4.1-mini"
    assert sent_body["temperature"] == 0.2
    assert sent_body["tools"] == caller_body["tools"]
    assert sent_body["tool_choice"] == "auto"
    assert sent_body["response_format"] == {"type": "json_object"}
    assert sent_body["x_unknown_json_compatible"] == {"preserved": True}
    assert caller_body["model"] == "client-model"
    assert response.provider == "openrouter"
    assert response.status_code == 200
    assert response.upstream_request_id == "req-openrouter"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 4
    assert response.usage.total_tokens == 15
    assert response.raw_cost_native == Decimal("0.00042")
    assert response.native_currency == "USD"
    assert route.called


@pytest.mark.asyncio
async def test_openrouter_chat_completion_uses_configured_base_url_and_api_key(respx_mock) -> None:
    secret_value = "custom-openrouter-upstream-key"
    route = respx_mock.post("https://openrouter-proxy.example/custom/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen_custom",
                "object": "chat.completion",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
        )
    )
    adapter = OpenRouterProviderAdapter(
        Settings(OPENROUTER_API_KEY=None),
        base_url="https://openrouter-proxy.example/custom/v1",
        api_key=secret_value,
        timeout_seconds=13,
        max_retries=1,
    )

    response = await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))

    sent_request = route.calls[0].request
    assert sent_request.headers["authorization"] == f"Bearer {secret_value}"
    assert "client-key" not in sent_request.headers["authorization"]
    assert response.json_body["id"] == "gen_custom"
    assert route.called


@pytest.mark.asyncio
async def test_openrouter_non_2xx_raises_safe_http_error(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            401,
            json={"error": {"message": "raw provider message with possible sensitive content"}},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))

    with pytest.raises(ProviderHTTPError) as exc_info:
        await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))

    assert exc_info.value.provider == "openrouter"
    assert exc_info.value.upstream_status_code == 401
    assert "raw provider message" not in exc_info.value.safe_message
    assert "openrouter-upstream-key" not in exc_info.value.safe_message
    assert route.called


def test_openrouter_adapter_safety_boundaries() -> None:
    import slaif_gateway.providers.openrouter as module

    source = inspect.getsource(module)
    forbidden_terms = (
        "FastAPI",
        "QuotaService",
        "usage_ledger",
        "Celery",
        "aiosmtplib",
        "jinja2",
        ".commit(",
    )

    for term in forbidden_terms:
        assert term not in source
