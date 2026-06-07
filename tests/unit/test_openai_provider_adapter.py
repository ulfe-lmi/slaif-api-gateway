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


def _responses_request(body: dict) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="gpt-5.2",
        endpoint="/v1/responses",
        body=body,
        request_id="gw-resp-req",
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
        "n": 1,
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
async def test_openai_response_posts_non_streaming_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_123",
                "object": "response",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 3,
                    "total_tokens": 13,
                    "input_tokens_details": {"cached_tokens": 2},
                    "output_tokens_details": {"reasoning_tokens": 1},
                },
            },
            headers={"OpenAI-Request-ID": "req-openai-response"},
        )
    )
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    adapter = OpenAIProviderAdapter(settings)
    caller_body = {
        "model": "client-model",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert sent_body == {
        "model": "gpt-5.2",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
    }
    assert caller_body["model"] == "client-model"
    assert response.provider == "openai"
    assert response.status_code == 200
    assert response.upstream_request_id == "req-openai-response"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 3
    assert response.usage.total_tokens == 13
    assert response.usage.cached_tokens == 2
    assert response.usage.reasoning_tokens == 1
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_posts_function_tool_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_tool_123",
                "object": "response",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_123",
                        "name": "lookup",
                        "arguments": '{"query":"safe"}',
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            },
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
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
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "gpt-5.2",
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
    assert response.usage.total_tokens == 13


@pytest.mark.asyncio
async def test_openai_response_posts_custom_tool_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_custom_tool_123",
                "object": "response",
                "output": [
                    {
                        "type": "custom_tool_call",
                        "call_id": "call_123",
                        "name": "emit_regex",
                        "input": "safe",
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            },
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
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
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "gpt-5.2",
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
    assert response.usage.total_tokens == 13


@pytest.mark.asyncio
async def test_openai_response_posts_structured_text_format_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_schema",
                "object": "response",
                "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
            },
            headers={"OpenAI-Request-ID": "req-openai-response-schema"},
        )
    )
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    adapter = OpenAIProviderAdapter(settings)
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
                "description": "Answer object.",
                "schema": schema,
                "strict": True,
            }
        },
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "gpt-5.2",
        "input": "hello",
        "store": False,
        "max_output_tokens": 20,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "description": "Answer object.",
                "schema": schema,
                "strict": True,
            }
        },
    }
    assert response.usage is not None
    assert response.usage.total_tokens == 12
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_posts_input_item_array_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_items",
                "object": "response",
                "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
            },
            headers={"OpenAI-Request-ID": "req-openai-response-items"},
        )
    )
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    adapter = OpenAIProviderAdapter(settings)
    caller_body = {
        "model": "client-model",
        "input": [
            {"role": "system", "content": "system text"},
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
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "gpt-5.2",
        "input": [
            {"role": "system", "content": "system text"},
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
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_posts_image_input_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_image",
                "object": "response",
                "usage": {"input_tokens": 14, "output_tokens": 4, "total_tokens": 18},
            },
            headers={"OpenAI-Request-ID": "req-openai-response-image"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {
                        "type": "input_image",
                        "image_url": "https://example.test/image.png",
                        "detail": "low",
                    },
                ],
            }
        ],
        "store": False,
        "max_output_tokens": 20,
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {
                        "type": "input_image",
                        "image_url": "https://example.test/image.png",
                        "detail": "low",
                    },
                ],
            }
        ],
        "store": False,
        "max_output_tokens": 20,
    }
    assert response.usage is not None
    assert response.usage.total_tokens == 18
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
