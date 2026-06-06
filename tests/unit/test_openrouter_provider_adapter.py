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


def _responses_request(body: dict) -> ProviderRequest:
    return ProviderRequest(
        provider="openrouter",
        upstream_model="openai/gpt-5.2",
        endpoint="/v1/responses",
        body=body,
        request_id="gw-resp-req",
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
        "n": 1,
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
    assert sent_body["n"] == 1
    assert set(sent_body) == {
        "model",
        "messages",
        "temperature",
        "tools",
        "tool_choice",
        "response_format",
        "n",
    }
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
async def test_openrouter_response_posts_non_streaming_request(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_or_123",
                "object": "response",
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "total_tokens": 15,
                    "cost_usd": "0.00042",
                },
            },
            headers={"X-OpenRouter-Request-ID": "req-openrouter-response"},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "x-csrf-token" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert sent_body == {
        "model": "openai/gpt-5.2",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
    }
    assert caller_body["model"] == "client-model"
    assert response.provider == "openrouter"
    assert response.status_code == 200
    assert response.upstream_request_id == "req-openrouter-response"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 4
    assert response.usage.total_tokens == 15
    assert response.raw_cost_native == Decimal("0.00042")
    assert response.native_currency == "USD"
    assert route.called


@pytest.mark.asyncio
async def test_openrouter_response_posts_function_tool_request(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_or_tool_123",
                "object": "response",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_123",
                        "name": "lookup",
                        "arguments": '{"query":"safe"}',
                    }
                ],
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "total_tokens": 15,
                    "cost_usd": "0.00042",
                },
            },
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "openai/gpt-5.2",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }
    assert response.json_body["output"][0]["type"] == "function_call"
    assert response.usage is not None
    assert response.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_openrouter_response_posts_custom_tool_request(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_or_custom_tool_123",
                "object": "response",
                "output": [
                    {
                        "type": "custom_tool_call",
                        "call_id": "call_123",
                        "name": "emit_regex",
                        "input": "safe",
                    }
                ],
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "total_tokens": 15,
                    "cost_usd": "0.00042",
                },
            },
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "tools": [
            {
                "type": "custom",
                "name": "emit_regex",
                "description": "Local custom intent.",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": "[a-z]+",
                },
            }
        ],
        "tool_choice": {"type": "custom", "name": "emit_regex"},
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "openai/gpt-5.2",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "tools": [
            {
                "type": "custom",
                "name": "emit_regex",
                "description": "Local custom intent.",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": "[a-z]+",
                },
            }
        ],
        "tool_choice": {"type": "custom", "name": "emit_regex"},
    }
    assert response.json_body["output"][0]["type"] == "custom_tool_call"
    assert response.usage is not None
    assert response.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_openrouter_response_posts_structured_text_format_request(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_or_schema",
                "object": "response",
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 7,
                    "total_tokens": 12,
                    "cost_usd": "0.00042",
                },
            },
            headers={"X-OpenRouter-Request-ID": "req-openrouter-response-schema"},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    caller_body = {
        "model": "client-model",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": schema,
                "strict": True,
            }
        },
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "openai/gpt-5.2",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": schema,
                "strict": True,
            }
        },
    }
    assert response.usage is not None
    assert response.usage.total_tokens == 12
    assert response.raw_cost_native == Decimal("0.00042")
    assert route.called


@pytest.mark.asyncio
async def test_openrouter_response_posts_input_item_array_request(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_or_items",
                "object": "response",
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 4,
                    "total_tokens": 12,
                    "cost_usd": "0.00042",
                },
            },
            headers={"X-OpenRouter-Request-ID": "req-openrouter-response-items"},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": [
            {"role": "developer", "content": "developer text"},
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        ],
        "store": False,
        "max_output_tokens": 20,
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "openai/gpt-5.2",
        "input": [
            {"role": "developer", "content": "developer text"},
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        ],
        "store": False,
        "max_output_tokens": 20,
    }
    assert response.usage is not None
    assert response.usage.total_tokens == 12
    assert response.raw_cost_native == Decimal("0.00042")
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
            json={
                "error": {
                    "message": "raw provider message with sk-or-secret",
                    "code": "rate_limited",
                    "metadata": {
                        "request_body": "user prompt body",
                        "response_body": "assistant completion body",
                        "apiKey": "sk-or-secret",
                    },
                }
            },
            headers={"x-openrouter-request-id": "or-error-req"},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))

    with pytest.raises(ProviderHTTPError) as exc_info:
        await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))

    assert exc_info.value.provider == "openrouter"
    assert exc_info.value.upstream_status_code == 401
    assert "raw provider message" not in exc_info.value.safe_message
    assert "openrouter-upstream-key" not in exc_info.value.safe_message
    assert exc_info.value.diagnostic is not None
    assert exc_info.value.diagnostic.upstream_error_code == "rate_limited"
    assert exc_info.value.diagnostic.upstream_request_id == "or-error-req"
    diagnostic_text = str(exc_info.value.diagnostic.to_safe_dict())
    assert "user prompt body" not in diagnostic_text
    assert "assistant completion body" not in diagnostic_text
    assert "sk-or-secret" not in diagnostic_text
    assert route.called


@pytest.mark.asyncio
async def test_openrouter_non_2xx_text_body_does_not_store_raw_preview(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            503,
            text="temporary outage with sk-or-secret and user prompt body",
            headers={"x-openrouter-request-id": "or-text-req"},
        )
    )
    adapter = OpenRouterProviderAdapter(Settings(OPENROUTER_API_KEY="openrouter-upstream-key"))

    with pytest.raises(ProviderHTTPError) as exc_info:
        await adapter.forward_chat_completion(_request({"model": "client-model", "messages": []}))

    assert exc_info.value.diagnostic is not None
    assert exc_info.value.diagnostic.upstream_request_id == "or-text-req"
    assert exc_info.value.diagnostic.sanitized_body_preview is None
    assert "temporary outage" not in str(exc_info.value.diagnostic.to_safe_dict())
    assert "sk-or-secret" not in str(exc_info.value.diagnostic.to_safe_dict())
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
