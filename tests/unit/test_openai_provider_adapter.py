from __future__ import annotations

import inspect
import json

import httpx
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import MissingProviderApiKeyError, ProviderHTTPError
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.schemas.providers import ProviderRequest


def _request(body: dict) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        endpoint="/v1/chat/completions",
        body=body,
        request_id="gw-req",
        extra_headers={
            "Authorization": "Bearer client-key",
            "Cookie": "cookie",
            "Content-Type": "application/json",
        },
    )


@pytest.mark.asyncio
async def test_missing_openai_api_key_raises() -> None:
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY=None))

    with pytest.raises(MissingProviderApiKeyError):
        await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))


@pytest.mark.asyncio
async def test_openai_chat_completion_posts_non_streaming_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_123",
                "object": "chat.completion",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                    "prompt_tokens_details": {"cached_tokens": 2},
                    "completion_tokens_details": {"reasoning_tokens": 1},
                },
            },
            headers={"OpenAI-Request-ID": "req-openai"},
        )
    )
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    adapter = OpenAIProviderAdapter(settings)
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
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_request.headers["accept"] == "application/json"
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["x-request-id"] == "gw-req"
    assert sent_body["model"] == "gpt-4.1-mini"
    assert sent_body["temperature"] == 0.2
    assert sent_body["tools"] == caller_body["tools"]
    assert sent_body["tool_choice"] == "auto"
    assert sent_body["response_format"] == {"type": "json_object"}
    assert sent_body["x_unknown_json_compatible"] == {"preserved": True}
    assert caller_body["model"] == "client-model"
    assert response.provider == "openai"
    assert response.status_code == 200
    assert response.upstream_request_id == "req-openai"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 3
    assert response.usage.total_tokens == 13
    assert response.usage.cached_tokens == 2
    assert response.usage.reasoning_tokens == 1
    assert route.called


@pytest.mark.asyncio
async def test_openai_chat_completion_uses_configured_base_url_and_api_key(respx_mock) -> None:
    secret_value = "custom-openai-upstream-key"
    route = respx_mock.post("https://openai-proxy.example/custom/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"id": "chatcmpl_custom", "object": "chat.completion", "usage": {"total_tokens": 1}},
        )
    )
    adapter = OpenAIProviderAdapter(
        Settings(OPENAI_UPSTREAM_API_KEY=None),
        base_url="https://openai-proxy.example/custom/v1",
        api_key=secret_value,
        timeout_seconds=11,
        max_retries=1,
    )

    response = await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))

    sent_request = route.calls[0].request
    assert sent_request.headers["authorization"] == f"Bearer {secret_value}"
    assert "client-key" not in sent_request.headers["authorization"]
    assert response.json_body["id"] == "chatcmpl_custom"
    assert route.called


@pytest.mark.asyncio
async def test_openai_non_2xx_raises_safe_http_error(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            429,
            json={
                "error": {
                    "message": "raw provider message with sk-proj-secret",
                    "type": "rate_limit_error",
                    "code": "rate_limited",
                    "metadata": {
                        "messages": [{"role": "user", "content": "user prompt body"}],
                        "authorization": "Bearer sk-proj-secret",
                    },
                }
            },
            headers={"openai-request-id": "req-openai-error"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    with pytest.raises(ProviderHTTPError) as exc_info:
        await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))

    assert exc_info.value.provider == "openai"
    assert exc_info.value.upstream_status_code == 429
    assert "raw provider message" not in exc_info.value.safe_message
    assert "openai-upstream-key" not in exc_info.value.safe_message
    assert exc_info.value.diagnostic is not None
    assert exc_info.value.diagnostic.upstream_error_type == "rate_limit_error"
    assert exc_info.value.diagnostic.upstream_error_code == "rate_limited"
    assert exc_info.value.diagnostic.upstream_request_id == "req-openai-error"
    diagnostic_text = str(exc_info.value.diagnostic.to_safe_dict())
    assert "user prompt body" not in diagnostic_text
    assert "sk-proj-secret" not in diagnostic_text
    assert route.called


def test_openai_adapter_safety_boundaries() -> None:
    import slaif_gateway.providers.openai as module

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
