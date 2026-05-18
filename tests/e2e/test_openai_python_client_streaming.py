from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx

from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    FAKE_OPENAI_UPSTREAM_KEY,
    PROMPT_TEXT,
    TEST_MODEL,
    _configure_runtime_environment,
    _create_test_data,
    _free_port,
    _load_accounting_state,
    _run_uvicorn_server,
    _test_database_url,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


@pytest.mark.e2e
def test_openai_python_client_chat_completions_streaming_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    sse = (
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[{{"index":0,"delta":{{"content":"Hello "}},'
        '"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[{{"index":0,"delta":{{"content":"from mocked upstream"}},'
        '"finish_reason":"stop"}]}\n\n'
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[],"usage":'
        '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
        "data: [DONE]\n\n"
    )

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={"x-request-id": "upstream-openai-stream-e2e"},
                )
            )

            client = OpenAI()
            chunks = client.chat.completions.create(
                model=TEST_MODEL,
                messages=[{"role": "user", "content": PROMPT_TEXT}],
                stream=True,
                temperature=0.2,
                top_p=0.9,
                stop=["STOP"],
                user="student-1",
                seed=123,
                tools=[{"type": "function", "function": {"name": "lookup"}}],
                tool_choice="auto",
                response_format={"type": "json_object"},
                extra_body={
                    "metadata": {"course": "week-1"},
                },
            )
            streamed_text = "".join(chunk.choices[0].delta.content or "" for chunk in chunks if chunk.choices)

    assert streamed_text == COMPLETION_TEXT
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["stream"] is True
    assert upstream_body["model"] == TEST_MODEL
    assert upstream_body["stream_options"] == {"include_usage": True}
    assert upstream_body["temperature"] == 0.2
    assert upstream_body["top_p"] == 0.9
    assert upstream_body["stop"] == ["STOP"]
    assert upstream_body["user"] == "student-1"
    assert upstream_body["seed"] == 123
    assert upstream_body["tools"][0]["function"]["name"] == "lookup"
    assert upstream_body["tool_choice"] == "auto"
    assert upstream_body["response_format"] == {"type": "json_object"}
    assert upstream_body["metadata"] == {"course": "week-1"}
    assert PROMPT_TEXT in json.dumps(upstream_body)

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))

    assert state.reservation.status == "finalized"
    assert state.gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_reserved_total == 0
    assert state.gateway_key.tokens_used_total == 11
    assert state.gateway_key.requests_used_total == 1

    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.accounting_status == "finalized"
    assert state.usage_ledger.prompt_tokens == 5
    assert state.usage_ledger.completion_tokens == 6
    assert state.usage_ledger.total_tokens == 11

    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    assert PROMPT_TEXT not in usage_payload
    assert COMPLETION_TEXT not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert COMPLETION_TEXT not in metadata_payload


@pytest.mark.e2e
def test_openai_python_client_chat_completions_streaming_multiple_choices_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url, owner_label="OpenAI Multi Stream", multiple_choices=True))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    first_delta = {
        "id": "chatcmpl-multi-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [
            {"index": 0, "delta": {"content": "first"}, "finish_reason": None},
            {"index": 1, "delta": {"content": "second"}, "finish_reason": None},
        ],
    }
    second_delta = {
        "id": "chatcmpl-multi-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [
            {"index": 1, "delta": {"content": " done"}, "finish_reason": "stop"},
            {"index": 0, "delta": {"content": " done"}, "finish_reason": "length"},
        ],
    }
    usage_delta = {
        "id": "chatcmpl-multi-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [],
        "usage": {"prompt_tokens": 5, "completion_tokens": 12, "total_tokens": 17},
    }
    sse = _sse(first_delta) + _sse(second_delta) + _sse(usage_delta) + "data: [DONE]\n\n"

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={"x-request-id": "upstream-openai-multi-stream-e2e"},
                )
            )

            client = OpenAI()
            chunks = list(
                client.chat.completions.create(
                    model=TEST_MODEL,
                    messages=[{"role": "user", "content": PROMPT_TEXT}],
                    stream=True,
                    max_completion_tokens=8,
                    n=2,
                )
            )

    choice_indexes = [choice.index for chunk in chunks for choice in chunk.choices]
    finish_reasons = [choice.finish_reason for chunk in chunks for choice in chunk.choices]
    assert choice_indexes == [0, 1, 1, 0]
    assert "stop" in finish_reasons
    assert "length" in finish_reasons
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.completion_tokens == 12

    upstream_body = json.loads(upstream_route.calls[0].request.content)
    assert upstream_body["stream"] is True
    assert upstream_body["stream_options"] == {"include_usage": True}
    assert upstream_body["n"] == 2
    assert upstream_body["max_completion_tokens"] == 8
    assert upstream_route.calls[0].request.headers["authorization"] == (
        f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    )
    assert upstream_route.calls[0].request.headers["authorization"] != (
        f"Bearer {created.plaintext_gateway_key}"
    )

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.prompt_tokens == 5
    assert state.usage_ledger.completion_tokens == 12
    assert state.usage_ledger.total_tokens == 17


@pytest.mark.e2e
def test_openai_python_client_chat_completions_streaming_image_input_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url, owner_label="OpenAI Image Stream", image_inputs=True))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    image_url = "https://example.test/stream-image.png?token=stream-secret"
    first_delta = {
        "id": "chatcmpl-image-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [{"index": 0, "delta": {"content": "image "}, "finish_reason": None}],
    }
    second_delta = {
        "id": "chatcmpl-image-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [{"index": 0, "delta": {"content": "answer"}, "finish_reason": "stop"}],
    }
    usage_delta = {
        "id": "chatcmpl-image-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [],
        "usage": {"prompt_tokens": 21, "completion_tokens": 4, "total_tokens": 25},
    }
    sse = _sse(first_delta) + _sse(second_delta) + _sse(usage_delta) + "data: [DONE]\n\n"

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={"x-request-id": "upstream-openai-image-stream-e2e"},
                )
            )

            client = OpenAI()
            chunks = list(
                client.chat.completions.create(
                    model=TEST_MODEL,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": PROMPT_TEXT},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url, "detail": "low"},
                                },
                            ],
                        }
                    ],
                    stream=True,
                )
            )

    streamed_text = "".join(chunk.choices[0].delta.content or "" for chunk in chunks if chunk.choices)
    assert streamed_text == "image answer"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total_tokens == 25

    upstream_body = json.loads(upstream_route.calls[0].request.content)
    assert upstream_body["stream"] is True
    assert upstream_body["stream_options"] == {"include_usage": True}
    assert upstream_body["messages"][0]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": image_url, "detail": "low"},
    }
    assert upstream_route.calls[0].request.headers["authorization"] == (
        f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    )
    assert upstream_route.calls[0].request.headers["authorization"] != (
        f"Bearer {created.plaintext_gateway_key}"
    )

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.prompt_tokens == 21
    assert state.usage_ledger.completion_tokens == 4
    assert state.usage_ledger.total_tokens == 25

    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    for forbidden in (PROMPT_TEXT, image_url, created.plaintext_gateway_key, FAKE_OPENAI_UPSTREAM_KEY):
        assert forbidden not in usage_payload
        assert forbidden not in metadata_payload


@pytest.mark.e2e
def test_openai_python_client_chat_completions_streaming_tool_calls_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url, owner_label="OpenAI Tool Stream"))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    tool_argument_marker = "unique-tool-argument-e2e"
    first_tool_delta = {
        "id": "chatcmpl-tool-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_lookup",
                            "type": "function",
                            "function": {"name": "lookup"},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ],
    }
    second_tool_delta = {
        "id": "chatcmpl-tool-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": f'{{"query":"{tool_argument_marker}"}}'},
                        }
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    usage_delta = {
        "id": "chatcmpl-tool-stream-e2e",
        "object": "chat.completion.chunk",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [],
        "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
    }
    sse = _sse(first_tool_delta) + _sse(second_tool_delta) + _sse(usage_delta) + "data: [DONE]\n\n"

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={"x-request-id": "upstream-openai-tool-stream-e2e"},
                )
            )

            client = OpenAI()
            chunks = list(
                client.chat.completions.create(
                    model=TEST_MODEL,
                    messages=[{"role": "user", "content": PROMPT_TEXT}],
                    stream=True,
                    tools=[{"type": "function", "function": {"name": "lookup"}}],
                    tool_choice="auto",
                )
            )

    tool_call_chunks = [
        tool_call
        for chunk in chunks
        for choice in chunk.choices
        for tool_call in (choice.delta.tool_calls or [])
    ]
    finish_reasons = [choice.finish_reason for chunk in chunks for choice in chunk.choices]

    assert tool_call_chunks[0].index == 0
    assert tool_call_chunks[0].id == "call_lookup"
    assert tool_call_chunks[0].type == "function"
    assert tool_call_chunks[0].function is not None
    assert tool_call_chunks[0].function.name == "lookup"
    assert tool_call_chunks[1].function is not None
    assert tool_call_chunks[1].function.arguments == f'{{"query":"{tool_argument_marker}"}}'
    assert "tool_calls" in finish_reasons
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["stream"] is True
    assert upstream_body["stream_options"] == {"include_usage": True}
    assert upstream_body["tools"][0]["function"]["name"] == "lookup"
    assert upstream_body["tool_choice"] == "auto"

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.prompt_tokens == 9
    assert state.usage_ledger.completion_tokens == 3
    assert state.usage_ledger.total_tokens == 12
    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    assert PROMPT_TEXT not in usage_payload
    assert tool_argument_marker not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert tool_argument_marker not in metadata_payload
