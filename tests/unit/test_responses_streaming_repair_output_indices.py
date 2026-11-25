"""228-c focused validation: bounded output_index repair for the qualified native wire.

Covers the demonstrated LAN transport defect (first rejected producer
event = ``response.output_item.added`` with ``output_index`` ABSENT) and
the ruling's repair law:

- Missing ``added`` positions are assigned only from unambiguous
  contiguous added ordering; missing ``done`` positions reuse the
  already validated same item ID's index.  Supplied indexes are never
  overwritten; ambiguous positions fail closed.
- The repaired wire payload preserves the ORIGINAL provider item status
  (an incomplete done keeps ``status: incomplete`` on the wire; the
  completed normalization stays validation-only).
- A rejected candidate never leaves a repaired payload behind; no stale
  payload across alternating repaired/unrepaired events.
- Terminal order consistency: once any index was derived, BOTH terminal
  representations (``response.completed`` and the
  ``response.incomplete`` output-limit terminal) must agree with the
  registered ID -> index ordering/coverage; contradictions are rejected,
  never reordered, and no pending item is completed.
- The terminal-order guard compares registered item IDs to output
  positions only; terminal item shape/arguments remain outside it.
- With the repair flag off, required-index denial is unchanged.

Fake SSE validator-level evidence only; no provider, network, or
database access.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

from slaif_gateway.config import Settings
from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage

CIPHER = "c" * 64
TAXONOMY = frozenset({("functions", "read", "function")})
USAGE = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}


def _profile(**overrides) -> ResponsesStreamValidationProfile:
    base = {
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": True,
        "allow_idless_encrypted_reasoning": True,
        "allow_sparse_visible_reasoning": True,
        "allow_empty_visible_reasoning": True,
        "allow_reasoning_summary_part_done": True,
        "require_output_indices": True,
        "repair_missing_output_indices": True,
        "declared_client_tools": TAXONOMY,
    }
    base.update(overrides)
    return ResponsesStreamValidationProfile(**base)


def _validator(**overrides) -> ResponsesStreamEventValidator:
    return ResponsesStreamEventValidator(_profile(**overrides))


def _function_item(
    item_id: str = "fc_1", call_id: str = "call_1", status: str | None = None
) -> dict:
    item: dict = {
        "type": "function_call",
        "id": item_id,
        "name": "read",
        "call_id": call_id,
        "arguments": "{}",
    }
    if status is not None:
        item["status"] = status
    return item


def _cipher_item(item_id: str = "rs_1") -> dict:
    return {"type": "reasoning", "id": item_id, "encrypted_content": CIPHER}


def _cipher_done_item(item_id: str = "rs_1") -> dict:
    return {
        "type": "reasoning",
        "id": item_id,
        "summary": [{"type": "summary_text", "text": "part"}],
        "encrypted_content": CIPHER,
    }


def _message_item(item_id: str = "msg_1") -> dict:
    return {
        "type": "message",
        "id": item_id,
        "role": "assistant",
        "content": [{"type": "output_text", "text": "ok"}],
    }


def _item_event(
    event_type: str, item: dict, *, seq: int, output_index: int | None = None
) -> dict:
    payload: dict = {
        "type": f"response.output_item.{event_type}",
        "sequence_number": seq,
        "item": item,
    }
    if output_index is not None:
        payload["output_index"] = output_index
    return payload


def _completed(seq: int, *, output: list[dict]) -> dict:
    """Terminal event carrying the faithful done item shapes.

    Callers pass the actual done items; the terminal-order guard only
    compares their registered IDs against output positions.
    """
    return {
        "type": "response.completed",
        "sequence_number": seq,
        "response": {"id": "resp_1", "status": "completed", "output": output},
    }


def _done_function_item(item_id: str, call_id: str = "call_1") -> dict:
    return {
        "type": "function_call",
        "id": item_id,
        "name": "read",
        "call_id": call_id,
        "arguments": "{}",
        "status": "completed",
    }


def _incomplete_terminal(seq: int, *, output: list) -> dict:
    return {
        "type": "response.incomplete",
        "sequence_number": seq,
        "response": {
            "id": "resp_1",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": output,
            "usage": dict(USAGE),
        },
    }


def _two_item_stream(v: ResponsesStreamEventValidator) -> None:
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    assert v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=2)) is True
    assert v.validate(_item_event("done", _function_item("fc_2", call_id="call_2"), seq=3)) is True


# --- derivation -------------------------------------------------------------


def test_added_missing_index_assigned_contiguously() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    assert v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=2)) is True
    assert v.validate(_item_event("done", _function_item("fc_2", call_id="call_2"), seq=3)) is True
    assert v.repaired_output_indices is True
    (c1, c2) = v.take_replay_reference_candidates()
    assert (c1.item_id, c1.item_kind) == ("fc_1", "function_call")
    assert (c2.item_id, c2.item_kind) == ("fc_2", "function_call")


def test_added_done_repair_payload_exact_and_input_unmutated() -> None:
    v = _validator()
    original = _item_event("added", _cipher_item("rs_1"), seq=0)
    assert v.validate(original) is True
    assert "output_index" not in original
    repaired = v.take_repaired_payload()
    assert repaired == {**original, "output_index": 0}
    assert repaired["item"]["encrypted_content"] == CIPHER
    assert v.take_repaired_payload() is None


def test_done_missing_index_reuses_added_index() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    assert v.take_repaired_payload() is not None
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=1)) is True
    repaired = v.take_repaired_payload()
    assert repaired is not None
    assert repaired["output_index"] == 0
    assert repaired["item"]["id"] == "fc_1"


def test_done_missing_index_reuses_supplied_added_index() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0, output_index=3)) is True
    assert v.take_repaired_payload() is None
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=1)) is True
    repaired = v.take_repaired_payload()
    assert repaired is not None
    assert repaired["output_index"] == 3


def test_mixed_supplied_and_derived() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0, output_index=0)) is True
    assert v.take_repaired_payload() is None  # supplied: never repaired
    assert v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1)) is True
    assert v.take_repaired_payload()["output_index"] == 1
    assert v.validate(_item_event("done", _function_item("fc_2", call_id="call_2"), seq=2)) is True
    assert v.take_repaired_payload()["output_index"] == 1


def test_multi_item_kinds_all_derived_and_terminal_agrees() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _cipher_item("rs_1"), seq=0)) is True
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=1)) is True
    assert v.validate(_item_event("added", _message_item("msg_1"), seq=2)) is True
    assert v.validate(_item_event("done", _cipher_done_item("rs_1"), seq=3)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=4)) is True
    assert v.validate(_item_event("done", _message_item("msg_1"), seq=5)) is True
    assert (
        v.validate(
            _completed(
                6,
                output=[
                    _cipher_done_item("rs_1"),
                    _function_item("fc_1"),
                    _message_item("msg_1"),
                ],
            )
        )
        is True
    )
    assert v.repaired_output_indices is True


def test_incomplete_done_wire_status_preserved_and_terminal_safety() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1", status="in_progress"), seq=0)) is True
    assert v.take_repaired_payload() is not None
    assert v.validate(_item_event("done", _function_item("fc_1", status="incomplete"), seq=1)) is True
    repaired = v.take_repaired_payload()
    assert repaired is not None
    assert repaired["item"]["status"] == "incomplete"  # wire keeps provider status
    assert repaired["output_index"] == 0
    # Original incomplete safety: the terminal is rejected although the
    # output order matches; the pending item is not completed.
    assert v.validate(_completed(2, output=[_function_item("fc_1")])) is False
    assert v.take_repaired_payload() is None


# --- fail-closed negatives ---------------------------------------------------


def test_orphan_done_missing_index_rejected() -> None:
    v = _validator()
    assert v.validate(_item_event("done", _function_item("fc_ghost"), seq=0)) is False
    assert v.take_repaired_payload() is None
    assert v.repaired_output_indices is False


def test_duplicate_added_missing_index_rejected() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=1)) is False
    assert v.take_repaired_payload() is None


def test_second_done_missing_index_rejected() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=1)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=2)) is False
    assert v.take_repaired_payload() is None


def test_gap_ambiguity_denied_and_state_unchanged() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True  # 0
    assert (
        v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1, output_index=2))
        is True
    )
    # {0, 2} is non-contiguous: the next position is ambiguous.
    assert v.validate(_item_event("added", _function_item("fc_3", call_id="call_3"), seq=2)) is False
    assert v.take_repaired_payload() is None
    assert v.validate(_item_event("added", _function_item("fc_3", call_id="call_3"), seq=3)) is False


def test_missing_item_id_rejected() -> None:
    v = _validator()
    item = _function_item("fc_1")
    del item["id"]
    assert v.validate(_item_event("added", item, seq=0)) is False
    assert v.take_repaired_payload() is None


def test_nonstring_item_id_rejected() -> None:
    v = _validator()
    item = _function_item("fc_1")
    item["id"] = 42
    assert v.validate(_item_event("added", item, seq=0)) is False
    assert v.take_repaired_payload() is None


def test_repair_flag_off_keeps_strict_denial() -> None:
    v = _validator(repair_missing_output_indices=False)
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is False
    assert v.take_repaired_payload() is None
    assert v.repaired_output_indices is False


def test_failed_shape_validation_cache_empty_and_no_pollution() -> None:
    v = _validator(declared_client_tools=frozenset())
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is False
    assert v.take_repaired_payload() is None
    # The rejected candidate consumed no index.
    assert v.validate(_item_event("added", _cipher_item("rs_1"), seq=1)) is True
    assert v.take_repaired_payload()["output_index"] == 0


def test_supplied_index_conflict_still_rejected() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0, output_index=0)) is True
    assert v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1)) is True
    # Derived 1 for fc_2; a supplied conflicting index for fc_1 (stored 0)
    # stays rejected.
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=2, output_index=1)) is False
    assert v.take_repaired_payload() is None


# --- terminal order consistency (both representations) ------------------------


def test_terminal_output_order_agreement_accepted() -> None:
    v = _validator()
    _two_item_stream(v)
    assert (
        v.validate(
            _completed(
                4, output=[_function_item("fc_1"), _function_item("fc_2", call_id="call_2")]
            )
        )
        is True
    )


def test_terminal_output_reversed_rejected() -> None:
    v = _validator()
    _two_item_stream(v)
    assert (
        v.validate(
            _completed(
                4, output=[_function_item("fc_2", call_id="call_2"), _function_item("fc_1")]
            )
        )
        is False
    )
    assert v.take_repaired_payload() is None


def test_terminal_output_missing_item_rejected() -> None:
    v = _validator()
    _two_item_stream(v)
    assert v.validate(_completed(4, output=[_function_item("fc_1")])) is False


def test_terminal_output_extra_item_rejected() -> None:
    v = _validator()
    _two_item_stream(v)
    assert (
        v.validate(
            _completed(
                4,
                output=[
                    _function_item("fc_1"),
                    _function_item("fc_2", call_id="call_2"),
                    _function_item("fc_ghost", call_id="call_3"),
                ],
            )
        )
        is False
    )


def test_terminal_output_duplicate_id_rejected() -> None:
    v = _validator()
    _two_item_stream(v)
    assert v.validate(_completed(4, output=[_function_item("fc_1"), _function_item("fc_1")])) is False


def test_terminal_guard_inactive_without_derived_indexes() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0, output_index=1)) is True
    assert v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1, output_index=0)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=2, output_index=1)) is True
    assert v.validate(_item_event("done", _function_item("fc_2", call_id="call_2"), seq=3, output_index=0)) is True
    # Indexed-only stream: nothing was derived, so the terminal-order
    # guard stays inactive and the legacy completed behavior applies.
    # The terminal below is the VALID supplied order (fc_2 at 0, fc_1 at
    # 1), matching the registered supplied indexes.
    assert (
        v.validate(
            _completed(
                4, output=[_function_item("fc_2", call_id="call_2"), _function_item("fc_1")]
            )
        )
        is True
    )
    assert v.repaired_output_indices is False


def test_output_limit_terminal_order_agreement_accepted() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=1)) is True
    assert v.validate(_incomplete_terminal(2, output=[_done_function_item("fc_1")])) is True


def test_output_limit_terminal_reversed_rejected() -> None:
    v = _validator()
    _two_item_stream(v)
    assert (
        v.validate(
            _incomplete_terminal(
                4,
                output=[_done_function_item("fc_2", call_id="call_2"), _done_function_item("fc_1")],
            )
        )
        is False
    )
    assert v.take_repaired_payload() is None


def test_output_limit_terminal_missing_item_rejected() -> None:
    v = _validator()
    _two_item_stream(v)
    assert v.validate(_incomplete_terminal(4, output=[_done_function_item("fc_1")])) is False


# --- alternation / staleness ---------------------------------------------------


def test_no_stale_payload_alternation() -> None:
    v = _validator()
    assert v.validate(_item_event("added", _function_item("fc_1"), seq=0)) is True
    first = v.take_repaired_payload()
    assert first is not None and first["output_index"] == 0
    assert (
        v.validate(_item_event("added", _function_item("fc_2", call_id="call_2"), seq=1, output_index=1))
        is True
    )
    assert v.take_repaired_payload() is None  # supplied: no stale first payload
    assert v.validate(_item_event("done", _function_item("fc_2", call_id="call_2"), seq=2)) is True
    third = v.take_repaired_payload()
    assert third is not None and third["output_index"] == 1 and third["item"]["id"] == "fc_2"
    assert v.validate(_item_event("done", _function_item("fc_1"), seq=3)) is True
    fourth = v.take_repaired_payload()
    assert fourth is not None and fourth["output_index"] == 0
    assert v.take_repaired_payload() is None


# --- core gateway SSE wire / held tail ----------------------------------------


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="gpt-test",
        resolved_model="gpt-test",
        native_currency="EUR",
        estimated_input_tokens=5,
        estimated_output_tokens=2,
        estimated_input_cost_native=Decimal("0.000010000"),
        estimated_output_cost_native=Decimal("0.000008000"),
        estimated_total_cost_native=Decimal("0.000018000"),
        estimated_total_cost_eur=Decimal("0.000018000"),
        pricing_rule_id=None,
        fx_rate_id=None,
        input_price_per_1m=Decimal("2.000000000"),
        output_price_per_1m=Decimal("8.000000000"),
        fx_rate=Decimal("1"),
    )


def _wire_gateway(
    monkeypatch,
    event_payloads: list[dict],
    *,
    marker_labels: dict[str, str] | None = None,
):
    """Drive the real ``_streaming_responses_response`` core with a fake adapter.

    Only the provider adapter and the settlement side effects are faked;
    validation, repair re-encoding, the replay delivery buffer, and frame
    ordering under test are the real gateway code path.  The profile is
    synthetic (supplied directly as the gateway would construct it for
    this pair); the client/server pair gate, authentication, and
    PostgreSQL settlement are covered by the real-factory/respx PG cases,
    whose database session and route resolver are mocked fixtures while
    the provider factory, adapter, and loopback HTTP transport are real.
    Native HTTP (LAN) evidence is separate.  ``marker_labels`` maps an
    expected client frame to a timeline label so arrival order against
    the accounting/replay steps can be asserted.
    """
    import slaif_gateway.services.responses_gateway as gateway

    timeline: list[str] = []
    raw_events = [
        f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
        for payload in event_payloads
    ]
    usage = (5, 2, 7)

    class FakeAdapter:
        async def stream_response(self, request):
            for payload, raw_event in zip(event_payloads, raw_events, strict=True):
                yield ProviderStreamChunk(
                    provider=request.provider,
                    upstream_model=request.upstream_model,
                    data=json.dumps(payload),
                    raw_sse_event=raw_event,
                    json_body=payload,
                    usage=(
                        ProviderUsage(
                            prompt_tokens=usage[0],
                            completion_tokens=usage[1],
                            total_tokens=usage[2],
                        )
                        if payload["type"] == "response.completed"
                        else None
                    ),
                )

    recorded: list[dict] = []

    async def fake_record_completed(**kwargs):
        timeline.append("accounting:record")
        recorded.append(kwargs)
        return SimpleNamespace(usage_ledger_id=uuid.uuid4())

    async def fake_finalize(**kwargs):
        timeline.append("accounting:finalize")
        return SimpleNamespace(
            prompt_tokens=usage[0],
            completion_tokens=usage[1],
            total_tokens=usage[2],
            actual_cost_eur=Decimal("0"),
        )

    async def fake_persist_replay(**kwargs):
        timeline.append("replay:persist")
        return 1

    async def fake_interruption(**kwargs):
        timeline.append("stream:interruption")
        return None

    monkeypatch.setattr(
        gateway, "get_provider_adapter", lambda route, settings: FakeAdapter()
    )
    monkeypatch.setattr(
        gateway, "_record_provider_completed_before_finalization", fake_record_completed
    )
    monkeypatch.setattr(gateway, "_finalize_successful_response", fake_finalize)
    monkeypatch.setattr(gateway, "_persist_codex_replay_references", fake_persist_replay)
    monkeypatch.setattr(gateway, "_record_success_metrics", lambda **kwargs: None)
    monkeypatch.setattr(gateway, "record_provider_call_result", lambda **kwargs: None)
    monkeypatch.setattr(
        gateway,
        "_finalize_responses_stream_interruption_after_output",
        fake_interruption,
    )

    response = gateway._streaming_responses_response(
        authenticated_key=SimpleNamespace(gateway_key_id=uuid.uuid4()),
        route=SimpleNamespace(
            provider="openai",
            resolved_model="gpt-test",
            route_id=uuid.uuid4(),
        ),
        policy_result=SimpleNamespace(codex_tool_history=None),
        cost_estimate=_estimate(),
        reservation=SimpleNamespace(reservation_id=uuid.uuid4()),
        request_id="req_1",
        settings=Settings(),
        request=None,
        rate_limit_reservation=None,
        upstream_body={"model": "gpt-test", "stream": True},
        live_burn_budget=None,
        stream_validation_profile=_profile(),
    )

    async def collect() -> list[str]:
        values: list[str] = []
        async for value in response.body_iterator:
            values.append(value)
            label = marker_labels.get(value) if marker_labels else None
            if label is None and value == raw_events[-1]:
                label = "client:completed"
            if label is not None:
                timeline.append(label)
        return values

    return raw_events, timeline, recorded, asyncio.run(collect())


def _wire_completed() -> dict:
    return {
        "type": "response.completed",
        "sequence_number": 2,
        "response": {
            "id": "resp_1",
            "status": "completed",
            "output": [_function_item("fc_1")],
            "usage": dict(USAGE),
        },
    }


def _compact_frame(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def test_gateway_reencodes_repaired_events_into_wire_and_held_tail(monkeypatch) -> None:
    added = _item_event("added", _function_item("fc_1"), seq=0)  # no output_index
    done = _item_event("done", _function_item("fc_1"), seq=1)  # no output_index
    repaired_added = _compact_frame({**added, "output_index": 0})
    repaired_done = _compact_frame({**done, "output_index": 0})
    raw_events, timeline, recorded, forwarded = _wire_gateway(
        monkeypatch,
        [
            {"type": "response.created", "response": {"id": "resp_1"}},
            added,
            done,
            _wire_completed(),
        ],
        marker_labels={
            repaired_added: "client:repaired_added",
            repaired_done: "client:repaired_done",
        },
    )
    # Exact client-visible order: created live, then the HELD tail of
    # compact re-encoded repaired frames, then the raw completed frame.
    assert forwarded == [
        raw_events[0],
        repaired_added,
        repaired_done,
        raw_events[3],
    ]
    # The unmodified missing-index producer frames never reach the client.
    assert raw_events[1] not in forwarded
    assert raw_events[2] not in forwarded
    # Usage is available to settlement (carried on the terminal chunk);
    # the repaired item chunks themselves carry no usage.
    assert recorded
    assert recorded[0]["provider_response"].usage is not None
    # Held-tail proof: BOTH repaired tool frames are released only after
    # accounting and replay-reference persistence; completed is last.  A
    # premature live yield of a repaired frame would break this order.
    assert timeline[-6:] == [
        "accounting:record",
        "accounting:finalize",
        "replay:persist",
        "client:repaired_added",
        "client:repaired_done",
        "client:completed",
    ]


def test_gateway_no_derivation_forwards_raw_bytes_unchanged(monkeypatch) -> None:
    added = _item_event("added", _function_item("fc_1"), seq=0, output_index=0)
    done = _item_event("done", _function_item("fc_1"), seq=1, output_index=0)
    raw_events, timeline, recorded, forwarded = _wire_gateway(
        monkeypatch,
        [
            {"type": "response.created", "response": {"id": "resp_1"}},
            added,
            done,
            _wire_completed(),
        ],
        marker_labels={
            _compact_frame(added): "client:added",
            _compact_frame(done): "client:done",
        },
    )
    # Every index supplied: no repair occurs and every frame is forwarded
    # byte-identical, still held and released after accounting in order.
    assert forwarded == raw_events
    assert recorded
    assert timeline[-6:] == [
        "accounting:record",
        "accounting:finalize",
        "replay:persist",
        "client:added",
        "client:done",
        "client:completed",
    ]


def test_gateway_orphan_missing_index_fails_closed(monkeypatch) -> None:
    orphan = _item_event("done", _function_item("fc_ghost", call_id="call_ghost"), seq=1)
    raw_events, timeline, recorded, forwarded = _wire_gateway(
        monkeypatch,
        [
            {"type": "response.created", "response": {"id": "resp_1"}},
            orphan,
        ],
    )
    joined = "".join(forwarded)
    assert forwarded[0] == raw_events[0]
    assert "response.failed" in joined
    assert "responses_stream_event_not_supported" in joined
    # The failed stream is interrupted, never settled, and persists no
    # replay references.
    assert "stream:interruption" in timeline
    assert "accounting:record" not in timeline
    assert "accounting:finalize" not in timeline
    assert "replay:persist" not in timeline
    assert recorded == []
