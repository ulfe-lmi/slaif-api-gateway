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


def _responses_input_tokens_request(body: dict) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="gpt-5.2",
        endpoint="/v1/responses/input_tokens",
        body=body,
        request_id="gw-count-req",
        extra_headers={
            "Authorization": "Bearer client-key",
            "Cookie": "cookie",
            "Content-Type": "application/json",
        },
    )


def _responses_compact_request(body: dict) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="gpt-5.2",
        endpoint="/v1/responses/compact",
        body=body,
        request_id="gw-compact-req",
        extra_headers={
            "Authorization": "Bearer client-key",
            "Cookie": "cookie",
            "Content-Type": "application/json",
        },
    )


def _responses_lifecycle_request(endpoint: str) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="gpt-5.2",
        endpoint=endpoint,
        body={},
        request_id="gw-response-lifecycle-req",
        extra_headers={
            "Authorization": "Bearer client-key",
            "Cookie": "cookie",
            "Content-Type": "application/json",
        },
    )


def _conversation_request(endpoint: str, body: dict | None = None) -> ProviderRequest:
    return ProviderRequest(
        provider="openai",
        upstream_model="",
        endpoint=endpoint,
        body=body or {},
        request_id="gw-conversation-req",
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
async def test_openai_response_compact_posts_native_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses/compact").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpct_123",
                "object": "response.compaction",
                "created_at": 1,
                "output": [],
                "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            },
            headers={"OpenAI-Request-ID": "req-openai-compact"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": [{"role": "user", "content": "compact this"}],
    }

    response = await adapter.compact_response(_responses_compact_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert sent_request.headers["x-request-id"] == "gw-compact-req"
    assert sent_body == {
        "model": "gpt-5.2",
        "input": [{"role": "user", "content": "compact this"}],
    }
    assert response.status_code == 200
    assert response.upstream_request_id == "req-openai-compact"
    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 3
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_posts_previous_response_id_body(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_next",
                "object": "response",
                "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            },
            headers={"OpenAI-Request-ID": "req-openai-response-previous"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": "continue",
        "store": False,
        "max_output_tokens": 20,
        "previous_response_id": "resp_previous",
    }

    response = await adapter.forward_response(_responses_request(caller_body))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert sent_body == {
        "model": "gpt-5.2",
        "input": "continue",
        "store": False,
        "max_output_tokens": 20,
        "previous_response_id": "resp_previous",
    }
    assert response.upstream_request_id == "req-openai-response-previous"


@pytest.mark.asyncio
async def test_openai_response_input_tokens_posts_count_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses/input_tokens").mock(
        return_value=httpx.Response(
            200,
            json={"object": "response.input_tokens", "input_tokens": 123},
            headers={"OpenAI-Request-ID": "req-openai-count"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": "hello",
        "tools": [{"type": "custom", "name": "emit_text"}],
    }

    response = await adapter.forward_response_input_tokens(
        _responses_input_tokens_request(caller_body)
    )

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert sent_body == {
        "model": "gpt-5.2",
        "input": "hello",
        "tools": [{"type": "custom", "name": "emit_text"}],
    }
    assert caller_body["model"] == "client-model"
    assert response.json_body == {"object": "response.input_tokens", "input_tokens": 123}
    assert response.upstream_request_id == "req-openai-count"
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_retrieve_uses_provider_auth_and_exact_path(respx_mock) -> None:
    route = respx_mock.get("https://api.openai.com/v1/responses/resp_123").mock(
        return_value=httpx.Response(
            200,
            json={"id": "resp_123", "object": "response", "status": "completed"},
            headers={"OpenAI-Request-ID": "req-openai-retrieve"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    response = await adapter.retrieve_response(
        _responses_lifecycle_request("responses.retrieve"),
        response_id="resp_123",
    )

    sent_request = route.calls[0].request
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert response.json_body == {"id": "resp_123", "object": "response", "status": "completed"}
    assert response.upstream_request_id == "req-openai-retrieve"
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_delete_uses_provider_auth_and_exact_path(respx_mock) -> None:
    route = respx_mock.delete("https://api.openai.com/v1/responses/resp_123").mock(
        return_value=httpx.Response(
            200,
            json={"id": "resp_123", "object": "response.deleted", "deleted": True},
            headers={"OpenAI-Request-ID": "req-openai-delete"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    response = await adapter.delete_response(
        _responses_lifecycle_request("responses.delete"),
        response_id="resp_123",
    )

    sent_request = route.calls[0].request
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert response.json_body == {"id": "resp_123", "object": "response.deleted", "deleted": True}
    assert response.upstream_request_id == "req-openai-delete"
    assert route.called


@pytest.mark.asyncio
async def test_openai_response_input_items_uses_provider_auth_exact_path_and_query(respx_mock) -> None:
    route = respx_mock.get(
        "https://api.openai.com/v1/responses/resp_123/input_items",
        params={
            "after": "item_1",
            "include": "message.input_image.image_url",
            "limit": "25",
            "order": "asc",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [],
                "first_id": None,
                "last_id": None,
                "has_more": False,
            },
            headers={"OpenAI-Request-ID": "req-openai-input-items"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    response = await adapter.list_response_input_items(
        ProviderRequest(
            provider="openai",
            upstream_model="gpt-5.2",
            endpoint="responses.input_items",
            body={
                "after": "item_1",
                "include": ["message.input_image.image_url"],
                "limit": 25,
                "order": "asc",
            },
            request_id="gw-input-items-req",
            extra_headers={
                "Authorization": "Bearer client-key",
                "Cookie": "cookie",
                "Content-Type": "application/json",
            },
        ),
        response_id="resp_123",
    )

    sent_request = route.calls[0].request
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert response.json_body == {
        "object": "list",
        "data": [],
        "first_id": None,
        "last_id": None,
        "has_more": False,
    }
    assert response.upstream_request_id == "req-openai-input-items"
    assert route.called


@pytest.mark.asyncio
async def test_openai_conversation_create_uses_provider_auth_and_empty_body(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/conversations").mock(
        return_value=httpx.Response(
            200,
            json={"id": "conv_123", "object": "conversation"},
            headers={"OpenAI-Request-ID": "req-openai-conversation-create"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    response = await adapter.create_conversation(_conversation_request("conversations.create"))

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in sent_request.headers["authorization"]
    assert "cookie" not in sent_request.headers
    assert sent_request.headers["accept"] == "application/json"
    assert sent_request.headers["x-request-id"] == "gw-conversation-req"
    assert sent_body == {}
    assert response.json_body == {"id": "conv_123", "object": "conversation"}
    assert response.upstream_request_id == "req-openai-conversation-create"


@pytest.mark.asyncio
async def test_openai_conversation_retrieve_delete_use_provider_auth_and_exact_path(respx_mock) -> None:
    retrieve_route = respx_mock.get("https://api.openai.com/v1/conversations/conv_123").mock(
        return_value=httpx.Response(
            200,
            json={"id": "conv_123", "object": "conversation"},
            headers={"OpenAI-Request-ID": "req-openai-conversation-retrieve"},
        )
    )
    delete_route = respx_mock.delete("https://api.openai.com/v1/conversations/conv_123").mock(
        return_value=httpx.Response(
            200,
            json={"id": "conv_123", "object": "conversation.deleted", "deleted": True},
            headers={"OpenAI-Request-ID": "req-openai-conversation-delete"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))

    retrieved = await adapter.retrieve_conversation(
        _conversation_request("conversations.retrieve"),
        conversation_id="conv_123",
    )
    deleted = await adapter.delete_conversation(
        _conversation_request("conversations.delete"),
        conversation_id="conv_123",
    )

    assert retrieve_route.calls[0].request.headers["authorization"] == "Bearer openai-upstream-key"
    assert delete_route.calls[0].request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-key" not in retrieve_route.calls[0].request.headers["authorization"]
    assert "client-key" not in delete_route.calls[0].request.headers["authorization"]
    assert retrieved.upstream_request_id == "req-openai-conversation-retrieve"
    assert deleted.upstream_request_id == "req-openai-conversation-delete"
    assert retrieved.json_body["object"] == "conversation"
    assert deleted.json_body["object"] == "conversation.deleted"


@pytest.mark.asyncio
async def test_openai_conversation_items_use_provider_auth_exact_paths_body_and_query(respx_mock) -> None:
    create_route = respx_mock.post("https://api.openai.com/v1/conversations/conv_123/items").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "msg_1", "type": "message"}]},
            headers={"OpenAI-Request-ID": "req-openai-conversation-items-create"},
        )
    )
    list_route = respx_mock.get(
        "https://api.openai.com/v1/conversations/conv_123/items",
        params={
            "after": "msg_0",
            "before": "msg_9",
            "include": "message.input_image.image_url",
            "limit": "10",
            "order": "asc",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [], "first_id": None, "last_id": None, "has_more": False},
            headers={"OpenAI-Request-ID": "req-openai-conversation-items-list"},
        )
    )
    retrieve_route = respx_mock.get(
        "https://api.openai.com/v1/conversations/conv_123/items/msg_1",
        params={"include": "message.input_image.image_url"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={"id": "msg_1", "type": "message", "role": "user"},
            headers={"OpenAI-Request-ID": "req-openai-conversation-item-retrieve"},
        )
    )
    delete_route = respx_mock.delete(
        "https://api.openai.com/v1/conversations/conv_123/items/msg_1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"id": "conv_123", "object": "conversation"},
            headers={"OpenAI-Request-ID": "req-openai-conversation-item-delete"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    create_body = {"items": [{"role": "user", "content": "hello"}]}

    created = await adapter.create_conversation_items(
        _conversation_request("conversations.items.create", create_body),
        conversation_id="conv_123",
    )
    listed = await adapter.list_conversation_items(
        _conversation_request(
            "conversations.items.list",
            {
                "after": "msg_0",
                "before": "msg_9",
                "include": ["message.input_image.image_url"],
                "limit": 10,
                "order": "asc",
            },
        ),
        conversation_id="conv_123",
    )
    retrieved = await adapter.retrieve_conversation_item(
        _conversation_request(
            "conversations.items.retrieve",
            {"include": ["message.input_image.image_url"]},
        ),
        conversation_id="conv_123",
        item_id="msg_1",
    )
    deleted = await adapter.delete_conversation_item(
        _conversation_request("conversations.items.delete"),
        conversation_id="conv_123",
        item_id="msg_1",
    )

    assert json.loads(create_route.calls[0].request.content) == create_body
    for route in (create_route, list_route, retrieve_route, delete_route):
        sent_request = route.calls[0].request
        assert sent_request.headers["authorization"] == "Bearer openai-upstream-key"
        assert "client-key" not in sent_request.headers["authorization"]
        assert "cookie" not in sent_request.headers
        assert sent_request.headers["accept"] == "application/json"
    assert created.upstream_request_id == "req-openai-conversation-items-create"
    assert listed.upstream_request_id == "req-openai-conversation-items-list"
    assert retrieved.upstream_request_id == "req-openai-conversation-item-retrieve"
    assert deleted.upstream_request_id == "req-openai-conversation-item-delete"


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
async def test_openai_response_posts_file_input_request(respx_mock) -> None:
    route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_file",
                "object": "response",
                "usage": {"input_tokens": 16, "output_tokens": 4, "total_tokens": 20},
            },
            headers={"OpenAI-Request-ID": "req-openai-response-file"},
        )
    )
    adapter = OpenAIProviderAdapter(Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key"))
    caller_body = {
        "model": "client-model",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "summarize this"},
                    {
                        "type": "input_file",
                        "file_url": "https://example.test/document.pdf",
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
                    {"type": "input_text", "text": "summarize this"},
                    {
                        "type": "input_file",
                        "file_url": "https://example.test/document.pdf",
                    },
                ],
            }
        ],
        "store": False,
        "max_output_tokens": 20,
    }
    assert response.usage is not None
    assert response.usage.total_tokens == 20
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
