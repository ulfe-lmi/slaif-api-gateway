"""Output exhaustion is an accounted terminal, with partial output kept intact."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator, ResponsesStreamValidationProfile,
)
from slaif_gateway.schemas.providers import ProviderUsage
from slaif_gateway.services.accounting import AccountingError
from tests.unit.test_v1_responses_quota import (
    _response_stream_chunk, _responses_request, _wire_auth_and_db,
    _wire_streaming_gateway, _wire_streaming_route, _wire_successful_route_pricing_quota,
)


def terminal(event_type="response.incomplete"):
    return {
        "type": event_type, "sequence_number": 2,
        "response": {
            "id": "resp_limited", "object": "response", "status": "incomplete",
            "error": None, "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{
                "type": "message", "id": "msg_limited", "role": "assistant",
                "status": "incomplete",
                "content": [{"type": "output_text", "text": "partial answer", "annotations": []}],
            }],
            "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        },
    }


@pytest.mark.parametrize("event_type", ["response.incomplete", "response.completed"])
def test_both_output_limit_representations_are_valid_without_mutating_status(event_type):
    event = terminal(event_type)
    original = copy.deepcopy(event)
    validator = ResponsesStreamEventValidator(ResponsesStreamValidationProfile())
    assert validator.validate(event)
    assert event == original
    assert validator.take_replay_reference_candidates() == ()
    assert not validator.validate(event)  # a terminal cannot be followed by another


@pytest.mark.parametrize("mutate", [
    lambda e: e["response"].update(status="completed"),
    lambda e: e["response"].update(incomplete_details={"reason": "unknown"}),
    lambda e: e["response"].update(incomplete_details={"reason": "content_filter"}),
    lambda e: e["response"].update(error={"message": "private"}),
    lambda e: e["response"].pop("usage"),
    lambda e: e["response"]["usage"].update(output_tokens=True),
    lambda e: e["response"]["usage"].update(total_tokens=999),
    lambda e: e["response"]["output"].append({"type": "web_search_call", "id": "hosted"}),
    lambda e: e["response"]["output"][0].update(server_url="https://private.invalid"),
    lambda e: e.update(sequence_number=-1),
])
def test_malformed_missing_usage_and_hosted_authority_remain_refused(mutate):
    event = terminal()
    mutate(event)
    validator = ResponsesStreamEventValidator(ResponsesStreamValidationProfile())
    assert not validator.validate(event)
    assert validator.take_replay_reference_candidates() == ()


def test_output_limit_terminal_matches_progress_identity_and_sequence():
    for mutation in ("id", "sequence"):
        validator = ResponsesStreamEventValidator(ResponsesStreamValidationProfile())
        assert validator.validate({
            "type": "response.created", "sequence_number": 2,
            "response": {"id": "resp_limited"},
        })
        event = terminal()
        event["sequence_number"] = 3
        if mutation == "id":
            event["response"]["id"] = "resp_foreign"
        else:
            event["sequence_number"] = 2
        assert not validator.validate(event)


def test_hosted_web_search_keeps_its_independent_settlement_boundary():
    validator = ResponsesStreamEventValidator(ResponsesStreamValidationProfile(web_search=True))
    assert not validator.validate(terminal())


@pytest.mark.parametrize("event_type", ["response.incomplete", "response.completed"])
@pytest.mark.parametrize("partial_item", [False, True])
def test_strict_legacy_message_lifecycle_keeps_output_limit_status(event_type, partial_item):
    from tests.unit.test_responses_codex_streaming_tools import (
        _strict_message_prefix_events, _strict_reasoning_validator, _strict_response_event,
    )

    validator = _strict_reasoning_validator()
    prefix = _strict_message_prefix_events()
    if partial_item:
        prefix[-1]["item"]["status"] = "incomplete"
    assert all(validator.validate(event) for event in prefix)
    event = _strict_response_event("response.completed", 9)
    event["type"] = event_type
    event["response"].update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    if partial_item:
        event["response"]["output"][-1]["status"] = "incomplete"
    original = copy.deepcopy(event)
    assert validator.validate(event)
    assert event == original


@pytest.mark.parametrize("status", ["completed", "incomplete"])
def test_partial_tools_never_gain_replay_and_terminal_arguments_must_match(status):
    profile = ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True, codex_encrypted_reasoning_replay=True,
        declared_client_tools=frozenset({("functions", "lookup", "function")}),
    )
    for tamper in (False, True):
        validator = ResponsesStreamEventValidator(profile)
        item = {
            "type": "function_call", "id": "fc_1", "call_id": "call_1",
            "namespace": "functions", "name": "lookup", "arguments": "",
            "status": "in_progress",
        }
        assert validator.validate({
            "type": "response.output_item.added", "output_index": 0,
            "sequence_number": 0, "item": item,
        })
        assert validator.validate({
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1", "output_index": 0, "sequence_number": 1, "delta": "{}",
        })
        done = {**item, "arguments": "{}", "status": status}
        assert validator.validate({
            "type": "response.output_item.done", "output_index": 0,
            "sequence_number": 2, "item": done,
        })
        event = terminal()
        event["sequence_number"] = 3
        event["response"]["output"] = [{**done, "arguments": '{"changed":1}' if tamper else "{}"}]
        assert validator.validate(event) is not tamper
        candidates = validator.take_replay_reference_candidates()
        assert len(candidates) == (1 if status == "completed" else 0)


@pytest.mark.parametrize("adapter_module", [
    "slaif_gateway.providers.openai",
    "slaif_gateway.providers.openrouter",
    "slaif_gateway.modules.servers.local_coding.adapter",
])
def test_provider_extractors_use_nested_authoritative_incomplete_usage(adapter_module):
    from importlib import import_module

    event = terminal()
    extracted = import_module(adapter_module)._responses_event_response_payload(event)
    assert extracted is event["response"]
    assert extracted["usage"] == {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}


def setup_stream(monkeypatch, event, *, finalize_error=None):
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({
            "type": "response.created", "sequence_number": 0,
            "response": {"id": "resp_limited"},
        }),
        _response_stream_chunk({
            "type": "response.output_text.delta", "sequence_number": 1,
            "delta": "partial answer",
        }),
        _response_stream_chunk(event, usage=ProviderUsage(
            prompt_tokens=3, completion_tokens=2, total_tokens=5,
        )),
    ]
    state, _, reservation = _wire_streaming_gateway(
        monkeypatch, chunks=chunks, finalize_error=finalize_error,
    )
    return app, state, reservation


@pytest.mark.parametrize("event_type", ["response.incomplete", "response.completed"])
def test_partial_text_and_exact_terminal_forward_only_after_usage_finalization(monkeypatch, event_type):
    event = terminal(event_type)
    app, state, reservation = setup_stream(monkeypatch, event)
    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "stream": True})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert response.status_code == 200
    assert events[1]["delta"] == "partial answer"
    assert events[-1] == event
    assert len(state["provider_completed_calls"]) == len(state["finalize_calls"]) == 1
    assert state["provider_completed_calls"][0]["usage"].total_tokens == 5
    assert not state["streaming_estimate_calls"] and not state["failure_calls"]
    assert state["rate_release_calls"] == [(reservation, True)]


def test_accounting_failure_suppresses_output_limited_terminal(monkeypatch):
    app, state, _ = setup_stream(monkeypatch, terminal(), finalize_error=AccountingError("safe"))
    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "stream": True})
    assert "partial answer" in response.text
    assert "event: response.incomplete" not in response.text
    assert '"status":"failed"' in response.text.replace(" ", "")
    assert len(state["recovery_failure_calls"]) == 1
