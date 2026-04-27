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
                    "x_unknown_json_compatible": {"preserved": True},
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
    assert upstream_body["x_unknown_json_compatible"] == {"preserved": True}
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
