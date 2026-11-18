"""A failed first turn must not put unauthorized replay items in client history."""

import asyncio
import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

import slaif_gateway.services.responses_gateway as gateway
from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.services.accounting import AccountingError
from slaif_gateway.services.codex_replay_service import CodexReplayReferenceError
from slaif_gateway.services.responses_replay_delivery import (
    ReplayDeliveryBufferFull, ResponsesReplayDeliveryBuffer,
)
from tests.unit.test_responses_codex_streaming_tools import (
    _added_tool, _done_tool, _estimate, _profile,
)


def _events(*, incomplete=False, limited=False):
    item = dict(item_id="ctc_delivery", call_id="call_delivery", namespace="functions",
                name="exec", custom=True)
    added = _added_tool(**item)
    done = _done_tool(**item, text='text("SAFE")')
    if incomplete:
        done["item"]["status"] = "incomplete"
    return [
        {"type": "response.created", "response": {"id": "resp_delivery"}},
        {"type": "response.output_text.delta", "delta": "Before the tool."},
        added,
        {"type": "response.custom_tool_call_input.delta", "item_id": "ctc_delivery",
         "call_id": "call_delivery", "output_index": 0, "delta": 'text("SAFE")'},
        done,
        {"type": "response.incomplete" if limited else "response.completed", "response": {
            "id": "resp_delivery", "status": "incomplete" if limited else "completed",
            **({"incomplete_details": {"reason": "max_output_tokens"}} if limited else {}),
            "output": [done["item"]],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }},
    ]


def _wire(monkeypatch, events, *, error=None, accounting_error=False,
          persistence_error=False, settings=None, pause=None, profile=None):
    timeline = []
    state = {"timeline": timeline, "finalized": 0, "interrupted": 0, "persisted": 0,
             "released": 0, "provider_closed": False}

    class Adapter:
        async def stream_response(self, request):
            try:
                for event in events:
                    timeline.append("provider:" + event["type"])
                    yield ProviderStreamChunk(
                        provider=request.provider, upstream_model=request.upstream_model,
                        data=json.dumps(event), json_body=event,
                        raw_sse_event="data: " + json.dumps(event) + "\n\n",
                        usage=(ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
                               if event["type"] in {"response.completed", "response.incomplete"}
                               else None),
                    )
                if pause:
                    pause.set()
                    await asyncio.Event().wait()
                if error:
                    raise error
            finally:
                state["provider_closed"] = True

    async def record(**kwargs):
        timeline.append("accounting:record")
        return SimpleNamespace(usage_ledger_id=uuid.uuid4())

    async def finalize(**kwargs):
        timeline.append("accounting:finalize")
        if accounting_error:
            raise AccountingError("Safe test failure")
        state["finalized"] += 1
        return SimpleNamespace(usage_ledger_id=uuid.uuid4(), prompt_tokens=1,
                               completion_tokens=1, total_tokens=2, actual_cost_eur=Decimal(0))

    async def persist(**kwargs):
        timeline.append("replay:commit")
        assert state["finalized"] == 1
        if persistence_error:
            raise CodexReplayReferenceError("Safe test failure",
                                           error_code="responses_codex_replay_persistence_failed")
        state["persisted"] += len(kwargs["candidates"])

    async def interrupt(**kwargs):
        state["interrupted"] += 1
        timeline.append("accounting:interrupted")

    async def noop(**kwargs):
        pass

    async def release(*args, **kwargs):
        state["released"] += 1

    monkeypatch.setattr(gateway, "get_provider_adapter", lambda *args: Adapter())
    monkeypatch.setattr(gateway, "_record_provider_completed_before_finalization", record)
    monkeypatch.setattr(gateway, "_finalize_successful_response", finalize)
    monkeypatch.setattr(gateway, "_mark_provider_completed_finalization_failed", noop)
    monkeypatch.setattr(gateway, "_persist_codex_replay_references", persist)
    monkeypatch.setattr(gateway, "_finalize_responses_stream_interruption_after_output", interrupt)
    monkeypatch.setattr(gateway, "_record_success_metrics", lambda **kwargs: None)
    monkeypatch.setattr(gateway, "record_provider_call_result", lambda **kwargs: None)
    monkeypatch.setattr(gateway, "_release_rate_limit_concurrency", release)
    response = gateway._streaming_responses_response(
        authenticated_key=SimpleNamespace(gateway_key_id=uuid.uuid4()),
        route=SimpleNamespace(provider="openai", resolved_model="synthetic", route_id=uuid.uuid4()),
        policy_result=SimpleNamespace(codex_tool_history=None), cost_estimate=_estimate(),
        reservation=SimpleNamespace(reservation_id=uuid.uuid4()), request_id="req_delivery",
        settings=settings or Settings(), request=None, rate_limit_reservation=None,
        upstream_body={"stream": True}, live_burn_budget=None, stream_validation_profile=profile or _profile(),
    )
    return response, state


def _decode(values):
    return [json.loads(v.split("data: ", 1)[1]) for v in values if v.startswith("data: ")]


async def _collect(response, state):
    values = []
    async for value in response.body_iterator:
        if "ctc_delivery" in value:
            state["timeline"].append("client:tool")
            assert state["finalized"] == 1 and state["persisted"] == 1
        values.append(value)
    return values


@pytest.mark.parametrize("prefix", [3, 4, 5, 6])
def test_fresh_failed_turn_never_delivers_a_replay_item(monkeypatch, prefix):
    # Includes failure AFTER a fully completed item and even after a terminal
    # frame followed by a transport error: neither is a committed response.
    response, state = _wire(monkeypatch, _events()[:prefix], error=ProviderError(
        "Synthetic failure", provider="openai", error_code="vllm_tool_protocol_invalid",
    ))
    values = asyncio.run(_collect(response, state))
    decoded = _decode(values)
    assert [e["type"] for e in decoded] == [
        "response.created", "response.output_text.delta", "response.failed",
    ]
    assert "ctc_delivery" not in "".join(values) and "call_delivery" not in "".join(values)
    assert decoded[-1]["response"]["error"]["code"] == "vllm_tool_protocol_invalid"
    assert state["persisted"] == state["finalized"] == 0
    assert state["interrupted"] == state["released"] == 1
    assert state["provider_closed"]


def test_success_releases_exact_event_order_only_after_durable_commit(monkeypatch):
    events = _events()
    response, state = _wire(monkeypatch, events)
    values = asyncio.run(_collect(response, state))
    assert _decode(values) == events
    assert state["timeline"].index("client:tool") > state["timeline"].index("replay:commit")
    assert state["finalized"] == state["persisted"] == state["released"] == 1
    assert state["interrupted"] == 0


@pytest.mark.parametrize("failure", ["accounting", "persistence", "missing_terminal"])
def test_uncommitted_delivery_is_discarded_for_all_settlement_failures(monkeypatch, failure):
    events = _events()[:-1] if failure == "missing_terminal" else _events()
    response, state = _wire(monkeypatch, events, accounting_error=failure == "accounting",
                            persistence_error=failure == "persistence")
    values = asyncio.run(_collect(response, state))
    assert _decode(values)[-1]["type"] == "response.failed"
    assert "ctc_delivery" not in "".join(values)
    assert state["persisted"] == 0 and state["released"] == 1


@pytest.mark.parametrize("incomplete", [False, True])
def test_output_limit_keeps_complete_tools_replayable_and_incomplete_tools_hidden(monkeypatch, incomplete):
    response, state = _wire(monkeypatch, _events(incomplete=incomplete, limited=True))
    if incomplete:
        async def collect():
            return [v async for v in response.body_iterator]
        values = asyncio.run(collect())
        assert "ctc_delivery" not in "".join(values)
        assert _decode(values)[-1]["response"]["error"]["code"] == "responses_codex_replay_item_incomplete"
        assert state["persisted"] == 0
    else:
        values = asyncio.run(_collect(response, state))
        assert _decode(values) == _events(limited=True)
    assert state["finalized"] == 1 and state["interrupted"] == 0


def test_cancel_before_commit_discards_items_and_releases_slot(monkeypatch):
    async def run():
        pause = asyncio.Event()
        response, state = _wire(monkeypatch, _events()[:-1], pause=pause)
        task = asyncio.create_task(_collect(response, state))
        await pause.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state["finalized"] == state["persisted"] == 0
        assert state["interrupted"] == state["released"] == 1
        assert state["provider_closed"]
    asyncio.run(run())


def test_disconnect_during_committed_tail_does_not_finalize_or_bill_twice(monkeypatch):
    async def run():
        response, state = _wire(monkeypatch, _events())
        iterator = response.body_iterator
        for _ in range(3):
            await anext(iterator)
        assert state["finalized"] == state["persisted"] == 1
        await iterator.aclose()
        assert state["finalized"] == 1 and state["interrupted"] == 0
        assert state["released"] == 1
    asyncio.run(run())


def test_buffer_limit_fails_without_exposing_items(monkeypatch):
    events = _events()
    events[3]["delta"] = "x" * 2048
    response, state = _wire(monkeypatch, events, settings=Settings(CODEX_REPLAY_STREAM_BUFFER_MAX_BYTES=1024))
    values = asyncio.run(_collect(response, state))
    assert _decode(values)[-1]["response"]["error"]["code"] == "responses_codex_replay_delivery_buffer_exceeded"
    assert "ctc_delivery" not in "".join(values)
    assert state["interrupted"] == 1


def test_plain_text_without_replay_items_still_streams_before_settlement(monkeypatch):
    async def run():
        response, state = _wire(monkeypatch, [_events()[0], _events()[1], _events()[-1]])
        iterator = response.body_iterator
        assert "response.created" in await anext(iterator)
        assert "Before the tool." in await anext(iterator)
        assert state["finalized"] == 0
        await anext(iterator)
        assert state["finalized"] == 1
        await iterator.aclose()
    asyncio.run(run())


def test_buffer_is_utf8_bounded_and_never_writes_payload_to_disk():
    buffer = ResponsesReplayDeliveryBuffer(enabled=True, encrypted_reasoning=False, max_bytes=4)
    event = {"type": "response.output_item.added", "item": {"type": "function_call"}}
    assert buffer.hold(event, "žž")
    with pytest.raises(ReplayDeliveryBufferFull):
        buffer.hold({}, "x")
    assert list(buffer.release()) == ["žž"]


def test_disabled_buffer_preserves_ordinary_responses_function_events():
    buffer = ResponsesReplayDeliveryBuffer(enabled=False, encrypted_reasoning=False, max_bytes=1)
    assert not buffer.hold({"type": "response.output_item.done", "item": {"type": "function_call"}}, "original")


@pytest.mark.parametrize("failure", [False, True])
def test_encrypted_reasoning_delivery_obeys_the_same_commit_barrier(monkeypatch, failure):
    from tests.unit.test_responses_codex_streaming_tools import _done_reasoning, _encrypted_profile
    events = [_events()[0], _done_reasoning(item_id="rs_delivery")]
    if not failure:
        events.append(_events()[-1])
    error = ProviderError("Synthetic failure", provider="openai") if failure else None
    response, state = _wire(monkeypatch, events, error=error, profile=_encrypted_profile())

    async def run():
        values = []
        async for value in response.body_iterator:
            if "rs_delivery" in value:
                assert not failure and state["persisted"] == state["finalized"] == 1
            values.append(value)
        return values
    values = asyncio.run(run())
    if failure:
        assert "rs_delivery" not in "".join(values)
        assert _decode(values)[-1]["type"] == "response.failed"
    else:
        assert _decode(values) == events


def test_buffered_tail_preserves_interleaved_text_and_keepalive_has_no_client_state(monkeypatch):
    real_counter = gateway.time.perf_counter
    ticks = iter(range(0, 10000, 20))
    monkeypatch.setattr(gateway, "time", SimpleNamespace(perf_counter=real_counter,
                                                        monotonic=lambda: next(ticks)))
    events = _events()
    events.insert(-1, {"type": "response.output_text.delta", "delta": "After the tool."})
    response, state = _wire(monkeypatch, events)
    values = asyncio.run(_collect(response, state))
    assert _decode(values) == events
    comments = [v for v in values if v.startswith(":")]
    assert comments and all(v == ": keep-alive\n\n" for v in comments)


@pytest.mark.parametrize("overrides", [
    {"CODEX_REPLAY_STREAM_BUFFER_MAX_BYTES": 0},
    {"CODEX_REPLAY_STREAM_BUFFER_MAX_BYTES": 268435457},
    {"CODEX_REPLAY_STREAM_KEEPALIVE_SECONDS": 0},
    {"CODEX_REPLAY_STREAM_KEEPALIVE_SECONDS": 61},
])
def test_invalid_delivery_memory_and_keepalive_budgets_are_rejected(overrides):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(**overrides)
