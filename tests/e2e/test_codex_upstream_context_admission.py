"""Actual SDK/gateway/PostgreSQL proof; provider HTTP is always mocked."""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest
import respx
from openai import APIStatusError, OpenAI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import GatewayKey, ModelRoute
from tests.e2e.test_openai_python_client_chat import (
    _configure_runtime_environment,
    _free_port,
    _load_accounting_side_effect_counts,
    _load_accounting_state,
    _run_uvicorn_server,
    _test_database_url,
)
from tests.e2e.test_openai_python_client_responses import (
    _sse,
    _create_responses_test_data,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head


@pytest.mark.e2e
@pytest.mark.parametrize(
    "mode,stream,token_limit",
    [
        (None, False, 1_000_000),
        ("upstream", False, 1_000_000),
        ("upstream", True, 1_000_000),
        ("upstream", False, 300_000),
    ],
)
def test_context_admission_reserves_full_budget_and_finalizes_actual_usage(
    monkeypatch, mode, stream, token_limit
):
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    model = f"context-admission-{uuid.uuid4().hex}"
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            model=model,
            streaming=True,
            codex_request_envelope=True,
            codex_client_tools=True,
            codex_streaming_tool_events=True,
            codex_encrypted_reasoning_replay=True,
            codex_route_limits={
                "context_window_tokens": 393216,
                "default_max_output_tokens": 64000,
                "max_output_tokens": 128000,
            },
            responses_policy={
                "version": 1,
                "allowed_capabilities": [
                    "codex_request_envelope",
                    "codex_client_tools",
                    "codex_streaming_tool_events",
                    "codex_encrypted_reasoning_replay",
                    "codex_compaction",
                ],
                "allowed_local_tool_types": ["function", "custom"],
            },
        )
    )

    async def configure():
        engine = create_async_engine(database_url)
        try:
            async with async_sessionmaker(engine)() as session:
                await session.execute(
                    update(GatewayKey)
                    .where(GatewayKey.id == created.gateway_key_id)
                    .values(token_limit_total=token_limit)
                )
                route = (
                    await session.execute(
                        select(ModelRoute).where(ModelRoute.requested_model == model)
                    )
                ).scalar_one()
                if mode is not None:
                    route.capabilities = {**route.capabilities, "codex_context_admission": mode}
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(configure())

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    get_settings.cache_clear()
    app = create_app(get_settings())
    port = _free_port()
    observed = []
    completed = {
        "id": "resp_context_budget",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": model,
        "output": [
            {
                "type": "message",
                "id": "stream_message_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "answer", "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 226000,
            "output_tokens": 2,
            "total_tokens": 226002,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }

    def provider(request):
        observed.append(json.loads(request.content))
        # No gateway estimate-based clipping: the actual backend owns that decision.
        assert observed[-1]["max_output_tokens"] == 64000
        if stream:
            return httpx.Response(
                200,
                text=(
                    _sse(
                        {
                            "type": "response.created",
                            "sequence_number": 0,
                            "response": {
                                "id": completed["id"],
                                "object": "response",
                                "created_at": 123,
                                "status": "in_progress",
                                "model": model,
                            },
                        }
                    )
                    + _sse(
                        {
                            "type": "response.output_text.delta",
                            "sequence_number": 1,
                            "item_id": "stream_message_1",
                            "output_index": 0,
                            "content_index": 0,
                            "delta": "answer",
                        }
                    )
                    + _sse(
                        {"type": "response.completed", "sequence_number": 2, "response": completed}
                    )
                ),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=completed)

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        upstream = router.post("https://api.openai.com/v1/responses").mock(side_effect=provider)
        with _run_uvicorn_server(app, port):
            with OpenAI(
                api_key=created.plaintext_key, base_url=f"http://127.0.0.1:{port}/v1", max_retries=0
            ) as client:
                kwargs = {
                    "model": model,
                    "input": [{"role": "user", "content": "x" * 250000} for _ in range(4)],
                    "prompt_cache_key": "synthetic-context-accounting",
                    "stream": stream,
                }
                if mode is None or token_limit == 300_000:
                    with pytest.raises(APIStatusError) as exc:
                        client.responses.create(**kwargs)
                    assert exc.value.code == (
                        "responses_codex_context_window_exceeded"
                        if mode is None
                        else "quota_limit_exceeded"
                    )
                    assert upstream.call_count == 0
                elif stream:
                    events = list(client.responses.create(**kwargs))
                    assert any(e.type == "response.completed" for e in events), [
                        e.model_dump() for e in events if e.type in {"error", "response.failed"}
                    ]
                else:
                    assert client.responses.create(**kwargs).status == "completed"
    if mode is None or token_limit == 300_000:
        counts = asyncio.run(
            _load_accounting_side_effect_counts(database_url, created.gateway_key_id)
        )
        assert counts == (0, 0)
        return
    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert upstream.call_count == 1
    assert state.reservation.reserved_tokens > 393216
    assert state.reservation.status == "finalized"
    assert (
        state.usage_ledger.response_metadata["reserved_tokens"] == state.reservation.reserved_tokens
    )
    assert state.usage_ledger.input_tokens == 226000
    assert state.usage_ledger.output_tokens == 2
    assert state.usage_ledger.total_tokens == 226002
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.tokens_used_total == 226002
