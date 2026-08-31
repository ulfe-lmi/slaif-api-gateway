from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import uuid
from types import SimpleNamespace
from decimal import Decimal
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0147 import CODEX_0147_POLICY_SPEC
from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_CLIENT_MODULE_ID
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.streaming import (
    RESPONSES_CODEX_STREAM_EVENT_TYPES,
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.codex_replay_service import CodexReplayReferenceError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    codex_client_tool_declarations,
    responses_codex_streaming_tool_events_allowed,
)
from slaif_gateway.services.responses_gateway import _codex_reasoning_events_enabled
from slaif_gateway.services.responses_gateway import (
    _derive_pair_local_codex_top_level_profile,
)
from slaif_gateway.services.responses_request_policy import (
    responses_codex_client_tools_requested,
    responses_codex_streaming_tool_events_requested,
)
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
    enforce_responses_route_capabilities,
)
from slaif_gateway.services.responses_streaming_live_burn import (
    ResponsesStreamingLiveBurnMonitor,
    build_responses_streaming_live_burn_budget,
    normalize_responses_streaming_live_burn_policy,
)
from scripts import capture_codex_protocol as capture
from scripts import verify_codex_tool_roundtrip as verifier


PRIVATE_CANARY = "private-tool-stream-canary"
DECLARATIONS = frozenset(
    {
        ("functions", "exec", "custom"),
        ("functions", "wait", "function"),
        ("functions", "request_user_input", "function"),
        ("collaboration", "followup_task", "function"),
        ("collaboration", "interrupt_agent", "function"),
        ("collaboration", "list_agents", "function"),
        ("collaboration", "send_message", "function"),
        ("collaboration", "spawn_agent", "function"),
        ("collaboration", "wait_agent", "function"),
    }
)


def _policy(settings: Settings) -> ResponsesRequestPolicy:
    return ResponsesRequestPolicy(settings, client_spec=CODEX_0147_POLICY_SPEC)
def _function(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "description": f"bounded-{name}",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "additionalProperties": False,
        },
    }


def _additional_tools() -> dict[str, object]:
    return {
        "type": "additional_tools",
        "role": "developer",
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "tools": [
                    {
                        "type": "custom",
                        "name": "exec",
                        "format": {
                            "type": "grammar",
                            "syntax": "lark",
                            "definition": "start: WORD\nWORD: /[A-Za-z]+/",
                        },
                    },
                    _function("wait"),
                    _function("request_user_input"),
                ],
            },
            {
                "type": "namespace",
                "name": "collaboration",
                "tools": [
                    _function("followup_task"),
                    _function("interrupt_agent"),
                    _function("list_agents"),
                    _function("send_message"),
                    _function("spawn_agent"),
                    _function("wait_agent"),
                ],
            },
        ],
    }


def _body(*, stream: bool = True, input_items: list[object] | None = None) -> dict[str, object]:
    return {
        "model": "classroom-codex",
        "input": input_items
        or [
            _additional_tools(),
            {"type": "message", "role": "user", "content": "hello"},
        ],
        "tool_choice": "auto",
        "stream": stream,
        "store": False,
        "max_output_tokens": 20,
    }


def _apply(body: dict[str, object]):
    return _policy(Settings()).apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )


def _profile() -> ResponsesStreamValidationProfile:
    return ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        declared_client_tools=DECLARATIONS,
    )


def _encrypted_profile() -> ResponsesStreamValidationProfile:
    return ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        codex_encrypted_reasoning_replay=True,
        declared_client_tools=DECLARATIONS,
    )


def _reasoning_added_event() -> dict[str, object]:
    return {
        "type": "response.output_item.added",
        "output_index": 0,
        "sequence_number": 1,
        "item": {
            "type": "reasoning",
            "id": "reasoning_1",
            "summary": [],
            "content": None,
            "encrypted_content": None,
            "status": "in_progress",
        },
    }


def _reasoning_part_event(event_type: str, sequence_number: int, text: str = "") -> dict[str, object]:
    return {
        "type": event_type,
        "item_id": "reasoning_1",
        "output_index": 0,
        "content_index": 0,
        "sequence_number": sequence_number,
        "part": {"type": "reasoning_text", "text": text},
    }


def _reasoning_text_event(
    event_type: str, sequence_number: int, *, delta: str | None = None, text: str | None = None
) -> dict[str, object]:
    event: dict[str, object] = {
        "type": event_type,
        "item_id": "reasoning_1",
        "output_index": 0,
        "content_index": 0,
        "sequence_number": sequence_number,
    }
    if delta is not None:
        event["delta"] = delta
    if text is not None:
        event["text"] = text
    return event


def _reasoning_done_event(sequence_number: int, *, text: str = "bounded") -> dict[str, object]:
    event = _reasoning_added_event()
    event["type"] = "response.output_item.done"
    event["sequence_number"] = sequence_number
    event["item"] = {
        "type": "reasoning",
        "id": "reasoning_1",
        "summary": [],
        "content": [{"type": "reasoning_text", "text": text}],
        "encrypted_content": None,
        "status": "completed",
    }
    return event


def _strict_reasoning_validator() -> ResponsesStreamEventValidator:
    return ResponsesStreamEventValidator(
        ResponsesStreamValidationProfile(codex_reasoning_events=True)
    )


def test_codex_0149_reasoning_stream_is_contained_to_the_local_server_pair() -> None:
    local_context = {"identity_mode": "static"}
    assert _codex_reasoning_events_enabled(
        client_module_id="codex-0.149-responses-v1", server_context=local_context
    )
    assert not _codex_reasoning_events_enabled(
        client_module_id="codex-0.149-responses-v1",
        server_context=None,
    )
    assert not _codex_reasoning_events_enabled(
        client_module_id="openai-default", server_context=local_context
    )


def test_codex_0149_top_level_tools_activate_only_after_exact_local_resolution() -> None:
    body = {
        "model": "classroom-codex",
        "input": "hello",
        "stream": True,
        "tools": [
            _function("wait"),
            {
                "type": "custom",
                "name": "exec",
                "description": "bounded-exec",
                "format": {"type": "grammar", "syntax": "lark"},
            },
        ],
    }

    # These are the unchanged pre-policy additional_tools facts; top-level
    # declarations are not treated as that namespace.
    assert responses_codex_client_tools_requested(body) is False
    assert responses_codex_streaming_tool_events_requested(body) is False

    local_declarations, local_streaming = _derive_pair_local_codex_top_level_profile(
        client_module_id=CODEX_0149_CLIENT_MODULE_ID,
        local_coding_server_context={"identity_mode": "static"},
        effective_body=body,
    )
    assert local_declarations == frozenset(
        {
            ("functions", "wait", "function"),
            ("functions", "exec", "custom"),
        }
    )
    assert local_streaming is True

    non_local_declarations, non_local_streaming = _derive_pair_local_codex_top_level_profile(
        client_module_id=CODEX_0149_CLIENT_MODULE_ID,
        local_coding_server_context=None,
        effective_body=body,
    )
    assert non_local_declarations == frozenset()
    assert non_local_streaming is False


def test_exact_pair_tool_branch_is_rejected_until_live_shape_evidence_exists() -> None:
    profile = ResponsesStreamValidationProfile(
        codex_reasoning_events=True,
        codex_streaming_tool_events=True,
        declared_client_tools=frozenset({("functions", "exec", "custom")}),
    )
    validator = ResponsesStreamEventValidator(profile)
    tool_added = {
        "type": "response.output_item.added",
        "output_index": 0,
        "sequence_number": 1,
        "item": {
            "type": "custom_tool_call",
            "id": "tool-item-1",
            "status": "in_progress",
            "namespace": "functions",
            "name": "exec",
            "call_id": "tool-call-1",
            "input": "",
        },
    }
    tool_delta = {
        "type": "response.custom_tool_call_input.delta",
        "item_id": "tool-item-1",
        "call_id": "tool-call-1",
        "output_index": 0,
        "sequence_number": 2,
        "delta": "bounded",
    }
    assert validator.validate(tool_added) is False
    assert validator.validate(tool_delta) is False
    ordinary_validator = ResponsesStreamEventValidator(
        ResponsesStreamValidationProfile(codex_reasoning_events=True)
    )
    assert all(ordinary_validator.validate(event) for event in _strict_message_prefix_events())


def _message_added_event() -> dict[str, object]:
    return {
        "type": "response.output_item.added",
        "output_index": 1,
        "sequence_number": 2,
        "item": {
            "type": "message",
            "id": "message_1",
            "status": "in_progress",
            "role": "assistant",
            "content": [],
            "phase": None,
        },
    }


def _message_content_part(event_type: str, sequence_number: int, text: str = "") -> dict[str, object]:
    return {
        "type": event_type,
        "item_id": "message_1",
        "output_index": 1,
        "content_index": 0,
        "sequence_number": sequence_number,
        "part": {
            "type": "output_text",
            "text": text,
            "annotations": [],
            "logprobs": [] if event_type == "response.content_part.added" else None,
        },
    }


def _message_text_event(event_type: str, sequence_number: int, value: str) -> dict[str, object]:
    event: dict[str, object] = {
        "type": event_type,
        "item_id": "message_1",
        "output_index": 1,
        "content_index": 0,
        "sequence_number": sequence_number,
        "logprobs": [],
    }
    event["delta" if event_type == "response.output_text.delta" else "text"] = value
    return event


def _message_done_event(sequence_number: int, text: str = "answer") -> dict[str, object]:
    return {
        "type": "response.output_item.done",
        "output_index": 1,
        "sequence_number": sequence_number,
        "item": {
            "type": "message",
            "id": "message_1",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": text,
                    "annotations": [],
                    "logprobs": None,
                }
            ],
            "phase": None,
            "summary": [],
        },
    }


def _strict_response_event(event_type: str, sequence_number: int) -> dict[str, object]:
    response = {"id": "response_1", "status": "in_progress"}
    if event_type == "response.completed":
        response.update(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "reasoning",
                        "id": "parser_reasoning_1",
                        "status": None,
                        "summary": [],
                        "content": [{"type": "reasoning_text", "text": "bounded"}],
                        "encrypted_content": None,
                    },
                    {
                        "type": "message",
                        "id": "parser_message_1",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "answer",
                                "annotations": [],
                                "logprobs": None,
                            }
                        ],
                        "phase": None,
                    }
                ],
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": {
                        "cached_tokens": 0,
                        "input_tokens_per_turn": [1],
                        "cached_tokens_per_turn": [0],
                    },
                    "output_tokens": 1,
                    "output_tokens_details": {
                        "reasoning_tokens": 0,
                        "tool_output_tokens": 0,
                        "output_tokens_per_turn": [1],
                        "tool_output_tokens_per_turn": [0],
                    },
                    "total_tokens": 2,
                },
            }
        )
    return {"type": event_type, "sequence_number": sequence_number, "response": response}


def _strict_message_prefix_events() -> list[dict[str, object]]:
    return [
        _strict_response_event("response.created", 0),
        _strict_response_event("response.in_progress", 1),
        _message_added_event(),
        _message_content_part("response.content_part.added", 3),
        _message_text_event("response.output_text.delta", 4, "ans"),
        _message_text_event("response.output_text.delta", 5, "wer"),
        _message_text_event("response.output_text.done", 6, "answer"),
        _message_content_part("response.content_part.done", 7, "answer"),
        _message_done_event(8),
    ]


def test_codex_0149_message_text_lifecycle_is_exactly_scoped() -> None:
    validator = _strict_reasoning_validator()
    events = _strict_message_prefix_events() + [_strict_response_event("response.completed", 9)]
    assert all(validator.validate(event) for event in events)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["item"].pop("phase"),
        lambda event: event["item"].update(phase="final_answer"),
        lambda event: event["item"].update(content=[{"type": "output_text", "text": "x"}]),
        lambda event: event["item"].update(type="function_call"),
    ],
)
def test_codex_0149_message_added_rejects_non_exact_shapes(mutation) -> None:
    event = _message_added_event()
    mutation(event)
    assert not _strict_reasoning_validator().validate(event)


def test_codex_0149_message_lifecycle_rejects_reordering_and_wrong_terminal_shapes() -> None:
    validator = _strict_reasoning_validator()
    assert validator.validate(_strict_response_event("response.created", 0))
    assert validator.validate(_strict_response_event("response.in_progress", 1))
    assert validator.validate(_message_added_event())
    assert not validator.validate(_message_content_part("response.content_part.done", 3))

    validator = _strict_reasoning_validator()
    assert validator.validate(_message_added_event())
    assert validator.validate(_message_content_part("response.content_part.added", 3))
    assert validator.validate(_message_text_event("response.output_text.delta", 4, "answer"))
    assert not validator.validate(_message_text_event("response.output_text.done", 5, "wrong"))

    validator = _strict_reasoning_validator()
    assert validator.validate(_message_added_event())
    assert validator.validate(_message_content_part("response.content_part.added", 3))
    assert validator.validate(_message_text_event("response.output_text.delta", 4, "answer"))
    assert validator.validate(_message_text_event("response.output_text.done", 5, "answer"))
    assert not validator.validate(_message_content_part("response.content_part.done", 6))


def test_codex_0149_message_lifecycle_enforces_event_specific_logprobs() -> None:
    validator = _strict_reasoning_validator()
    added = _message_content_part("response.content_part.added", 3)
    added["part"]["logprobs"] = None
    assert validator.validate(_message_added_event())
    assert not validator.validate(added)

    validator = _strict_reasoning_validator()
    assert validator.validate(_message_added_event())
    assert validator.validate(_message_content_part("response.content_part.added", 3))
    assert validator.validate(_message_text_event("response.output_text.delta", 4, "answer"))
    assert validator.validate(_message_text_event("response.output_text.done", 5, "answer"))
    done_part = _message_content_part("response.content_part.done", 6, "answer")
    done_part["part"]["logprobs"] = []
    assert not validator.validate(done_part)

    validator = _strict_reasoning_validator()
    assert validator.validate(_message_added_event())
    assert validator.validate(_message_content_part("response.content_part.added", 3))
    assert validator.validate(_message_text_event("response.output_text.delta", 4, "answer"))
    assert validator.validate(_message_text_event("response.output_text.done", 5, "answer"))
    assert validator.validate(_message_content_part("response.content_part.done", 6, "answer"))
    terminal = _message_done_event(7)
    terminal["item"]["content"][0]["logprobs"] = []
    assert not validator.validate(terminal)


def test_codex_0149_completed_requires_usage_and_no_active_output() -> None:
    validator = _strict_reasoning_validator()
    assert validator.validate(_strict_response_event("response.created", 0))
    assert not validator.validate(_strict_response_event("response.completed", 1))

    validator = _strict_reasoning_validator()
    assert validator.validate(_strict_response_event("response.created", 0))
    assert validator.validate(_message_added_event())
    missing_usage = _strict_response_event("response.completed", 3)
    missing_usage["response"].pop("usage")
    assert not validator.validate(missing_usage)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda response: response.update(output="not-a-list"),
        lambda response: response.update(output=[]),
        lambda response: response["output"].__setitem__(0, {"type": "function_call"}),
        lambda response: response["output"].__setitem__(0, {**response["output"][0], "status": "completed"}),
        lambda response: response["usage"]["input_tokens_details"].update(cached_tokens=-1),
        lambda response: response["usage"]["output_tokens_details"].update(reasoning_tokens=-1),
        lambda response: response["usage"]["output_tokens_details"].update(tool_output_tokens="0"),
        lambda response: response["usage"]["input_tokens_details"].update(
            input_tokens_per_turn=[0] * 65
        ),
        lambda response: response["usage"]["output_tokens_details"].update(
            tool_output_tokens_per_turn=[0, 1]
        ),
        lambda response: response["usage"].update(total_tokens=3),
    ],
)
def test_codex_0149_completed_output_and_usage_reject_malformed_facts(mutation) -> None:
    validator = _strict_reasoning_validator()
    assert all(validator.validate(event) for event in _strict_message_prefix_events())
    completed = _strict_response_event("response.completed", 9)
    mutation(completed["response"])
    assert not validator.validate(completed)


def test_codex_0149_reasoning_item_lifecycle_is_exactly_scoped() -> None:
    added = _reasoning_added_event()
    assert not ResponsesStreamEventValidator(ResponsesStreamValidationProfile()).validate(added)
    validator = _strict_reasoning_validator()
    assert validator.validate(added)
    assert validator.validate(_reasoning_part_event("response.reasoning_part.added", 2))
    assert validator.validate(
        _reasoning_text_event("response.reasoning_text.delta", 3, delta="bound")
    )
    assert validator.validate(
        _reasoning_text_event("response.reasoning_text.delta", 4, delta="ed")
    )
    assert validator.validate(
        _reasoning_text_event("response.reasoning_text.done", 5, text="bounded")
    )
    assert validator.validate(
        _reasoning_part_event("response.reasoning_part.done", 6, text="bounded")
    )
    assert validator.validate(_reasoning_done_event(7))


def test_codex_0149_reasoning_lifecycle_tracks_nonzero_output_index() -> None:
    validator = _strict_reasoning_validator()
    events = [
        _reasoning_added_event(),
        _reasoning_part_event("response.reasoning_part.added", 2),
        _reasoning_text_event("response.reasoning_text.delta", 3, delta="bounded"),
        _reasoning_text_event("response.reasoning_text.done", 4, text="bounded"),
        _reasoning_part_event("response.reasoning_part.done", 5, text="bounded"),
        _reasoning_done_event(6),
    ]
    for event in events:
        event["output_index"] = 4
    assert all(validator.validate(event) for event in events)

    mismatch = _strict_reasoning_validator()
    assert mismatch.validate(_reasoning_added_event())
    bad_delta = _reasoning_text_event("response.reasoning_text.delta", 2, delta="wrong-index")
    bad_delta["output_index"] = 1
    assert not mismatch.validate(bad_delta)


def test_non_strict_reasoning_text_done_keeps_no_prior_delta_behavior() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_reasoning_added_event())
    event = _reasoning_text_event("response.reasoning_text.done", 2, text="")
    event.pop("sequence_number")
    assert validator.validate(event)


@pytest.mark.parametrize(
    "events",
    [
        [_reasoning_part_event("response.reasoning_part.added", 1)],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_part_event("response.reasoning_part.added", 3),
        ],
        [
            _reasoning_added_event(),
            _reasoning_text_event("response.reasoning_text.delta", 2, delta="orphan"),
        ],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_text_event("response.reasoning_text.done", 3, text=""),
        ],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_text_event("response.reasoning_text.delta", 3, delta="bounded"),
            _reasoning_text_event("response.reasoning_text.done", 4, text="wrong"),
        ],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_text_event("response.reasoning_text.delta", 3, delta="bounded"),
            _reasoning_part_event("response.reasoning_part.done", 4, text="bounded"),
        ],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_text_event("response.reasoning_text.delta", 3, delta="bounded"),
            _reasoning_text_event("response.reasoning_text.done", 4, text="bounded"),
            _reasoning_part_event("response.reasoning_part.done", 5, text="wrong"),
        ],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_text_event("response.reasoning_text.delta", 3, delta="bounded"),
            _reasoning_text_event("response.reasoning_text.done", 4, text="bounded"),
            _reasoning_part_event("response.reasoning_part.done", 5, text="bounded"),
            _reasoning_part_event("response.reasoning_part.done", 6, text="bounded"),
        ],
        [_reasoning_added_event(), _reasoning_done_event(2)],
        [
            _reasoning_added_event(),
            _reasoning_part_event("response.reasoning_part.added", 2),
            _reasoning_text_event("response.reasoning_text.delta", 3, delta="bounded"),
            _reasoning_text_event("response.reasoning_text.done", 4, text="bounded"),
            _reasoning_part_event("response.reasoning_part.done", 5, text="bounded"),
            _reasoning_done_event(6, text="different"),
        ],
    ],
)
def test_codex_0149_reasoning_lifecycle_rejects_orphans_duplicates_and_reordering(
    events: list[dict[str, object]],
) -> None:
    validator = _strict_reasoning_validator()
    results = [validator.validate(event) for event in events]
    assert results[-1] is False


def test_codex_0149_reasoning_lifecycle_rejects_message_and_tool_smuggling() -> None:
    validator = _strict_reasoning_validator()
    assert not validator.validate(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "sequence_number": 1,
            "item": {"type": "message", "id": "message_1", "content": []},
        }
    )
    assert not validator.validate(
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "function_1",
            "output_index": 0,
            "sequence_number": 2,
            "delta": "{}",
        }
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["item"].update(type="function_call"),
        lambda event: event["item"].update(extra="authority"),
        lambda event: event.update(output_index="0"),
    ],
)
def test_codex_0149_reasoning_item_rejects_non_exact_shapes(mutation) -> None:
    event = _reasoning_added_event()
    mutation(event)
    assert not ResponsesStreamEventValidator(
        ResponsesStreamValidationProfile(codex_reasoning_events=True)
    ).validate(event)


def _done_reasoning(
    *,
    item_id: str = "rs_1",
    encrypted_content: str = "opaque-ciphertext",
) -> dict[str, object]:
    return {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "reasoning",
            "id": item_id,
            "summary": [{"type": "summary_text", "text": "safe summary"}],
            "encrypted_content": encrypted_content,
        },
    }


def test_encrypted_reasoning_done_event_is_exact_opaque_and_candidate_only() -> None:
    validator = ResponsesStreamEventValidator(_encrypted_profile())
    payload = _done_reasoning(encrypted_content=PRIVATE_CANARY)
    original = copy.deepcopy(payload)

    assert validator.validate(payload)
    assert payload == original
    candidates = validator.take_replay_reference_candidates()
    assert len(candidates) == 1
    assert candidates[0].item_kind == "reasoning"
    assert candidates[0].item_id == "rs_1"
    assert not hasattr(candidates[0], "encrypted_content")
    assert not hasattr(candidates[0], "summary")
    assert PRIVATE_CANARY not in repr(validator.__dict__)
    assert PRIVATE_CANARY not in json.dumps(validator.safe_evidence())
    assert validator.take_replay_reference_candidates() == ()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["item"].update(content=[]),
        lambda event: event["item"].update(status="completed"),
        lambda event: event["item"].update(unknown="authority"),
        lambda event: event["item"].update(encrypted_content=""),
        lambda event: event["item"].update(encrypted_content="x" * 262_145),
        lambda event: event["item"].update(summary=[{"type": "reasoning_text", "text": "private"}]),
    ],
)
def test_encrypted_reasoning_done_event_rejects_plaintext_unknown_and_size(mutation) -> None:
    validator = ResponsesStreamEventValidator(_encrypted_profile())
    event = _done_reasoning()
    mutation(event)
    assert not validator.validate(event)
    assert validator.take_replay_reference_candidates() == ()


def test_encrypted_reasoning_requires_gate_done_event_and_cumulative_cap() -> None:
    assert not ResponsesStreamEventValidator(_profile()).validate(_done_reasoning())
    added = _done_reasoning()
    added["type"] = "response.output_item.added"
    assert not ResponsesStreamEventValidator(_encrypted_profile()).validate(added)

    validator = ResponsesStreamEventValidator(_encrypted_profile())
    for index in range(4):
        assert validator.validate(
            _done_reasoning(
                item_id=f"rs_{index}",
                encrypted_content="x" * 262_144,
            )
        )
    assert not validator.validate(
        _done_reasoning(item_id="rs_over", encrypted_content="x")
    )
    assert len(validator.take_replay_reference_candidates()) == 4


def _added_tool(
    *,
    item_id: str,
    call_id: str,
    namespace: str,
    name: str,
    custom: bool,
) -> dict[str, object]:
    field = "input" if custom else "arguments"
    return {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "type": "custom_tool_call" if custom else "function_call",
            "id": item_id,
            "status": "in_progress",
            "namespace": namespace,
            "name": name,
            "call_id": call_id,
            field: "",
        },
    }


def _done_tool(
    *,
    item_id: str,
    call_id: str,
    namespace: str,
    name: str,
    custom: bool,
    text: str,
) -> dict[str, object]:
    field = "input" if custom else "arguments"
    return {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "custom_tool_call" if custom else "function_call",
            "id": item_id,
            "status": "completed",
            "namespace": namespace,
            "name": name,
            "call_id": call_id,
            field: text,
        },
    }


@pytest.mark.parametrize(
    ("envelope", "client_tools", "stream_events", "allowed"),
    [
        (False, False, False, False),
        (True, False, False, False),
        (True, True, False, False),
        (True, False, True, False),
        (False, True, True, False),
        (True, True, True, True),
    ],
)
def test_streaming_client_tools_require_three_independent_key_gates(
    envelope: bool,
    client_tools: bool,
    stream_events: bool,
    allowed: bool,
) -> None:
    capabilities = ["text", "stateless"]
    if envelope:
        capabilities.append("codex_request_envelope")
    if client_tools:
        capabilities.append("codex_client_tools")
    if stream_events:
        capabilities.append("codex_streaming_tool_events")
    policy = {"version": 1, "allowed_capabilities": capabilities}

    assert responses_codex_streaming_tool_events_allowed(policy) is allowed

    kwargs = {
        "allow_codex_request_envelope": envelope,
        "allow_codex_client_tools": client_tools,
        "allow_codex_streaming_tool_events": stream_events,
    }
    if allowed:
        assert _policy(Settings()).apply(_body(), **kwargs).effective_body[
            "stream"
        ] is True
    else:
        with pytest.raises(RequestPolicyError):
            _policy(Settings()).apply(_body(), **kwargs)


@pytest.mark.parametrize(
    ("envelope", "client_tools", "stream_events", "allowed"),
    [
        (False, False, False, False),
        (True, True, False, False),
        (True, False, True, False),
        (False, True, True, False),
        (True, True, True, True),
    ],
)
def test_streaming_client_tools_require_three_independent_route_gates(
    envelope: bool,
    client_tools: bool,
    stream_events: bool,
    allowed: bool,
) -> None:
    capabilities = default_responses_capabilities()
    capabilities.update(
        {
            "streaming": True,
            "codex_request_envelope": envelope,
            "codex_client_tools": client_tools,
            "codex_streaming_tool_events": stream_events,
        }
    )
    kwargs = {
        "route_capabilities": {"responses": capabilities},
        "route_supports_streaming": True,
        "streaming_requested": True,
        "codex_client_tools_requested": True,
        "codex_streaming_tool_events_requested": True,
    }
    if allowed:
        enforce_responses_route_capabilities(**kwargs)
    else:
        with pytest.raises(RequestPolicyError):
            enforce_responses_route_capabilities(**kwargs)


def test_validated_declarations_build_identifier_free_stream_profile() -> None:
    result = _apply(_body())

    assert codex_client_tool_declarations(result.effective_body) == DECLARATIONS


def test_function_and_custom_stream_sequences_are_validated_incrementally() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    events = [
        {"type": "response.created", "response": {"id": "resp_1"}},
        {
            "type": "response.in_progress",
            "response": {"id": "resp_1", "status": "in_progress"},
        },
        _added_tool(
            item_id="fc_1",
            call_id="call_1",
            namespace="functions",
            name="wait",
            custom=False,
        ),
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1",
            "output_index": 0,
            "delta": '{"value":',
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1",
            "output_index": 0,
            "delta": '"ok"}',
        },
        _done_tool(
            item_id="fc_1",
            call_id="call_1",
            namespace="functions",
            name="wait",
            custom=False,
            text='{"value":"ok"}',
        ),
        _added_tool(
            item_id="ctc_1",
            call_id="call_2",
            namespace="functions",
            name="exec",
            custom=True,
        ),
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": "ctc_1",
            "call_id": "call_2",
            "output_index": 1,
            "delta": 'text("SAFE")',
        },
        _done_tool(
            item_id="ctc_1",
            call_id="call_2",
            namespace="functions",
            name="exec",
            custom=True,
            text='text("SAFE")',
        ),
    ]

    assert all(validator.validate(event) for event in events)
    evidence = validator.safe_evidence()
    assert evidence["event_counts"]["response.output_item.added"] == 2
    assert PRIVATE_CANARY not in repr(evidence)
    assert "call_1" not in repr(evidence)


def test_reasoning_message_and_terminal_event_table_is_bounded() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "reasoning", "id": "rs_1", "summary": []},
        },
        {
            "type": "response.reasoning_summary_part.added",
            "item_id": "rs_1",
            "output_index": 0,
            "summary_index": 0,
            "part": {"type": "summary_text", "text": ""},
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "rs_1",
            "output_index": 0,
            "summary_index": 0,
            "delta": "bounded summary",
        },
        {
            "type": "response.reasoning_summary_text.done",
            "item_id": "rs_1",
            "output_index": 0,
            "summary_index": 0,
            "text": "bounded summary",
        },
        {
            "type": "response.reasoning_text.delta",
            "item_id": "rs_1",
            "output_index": 0,
            "content_index": 0,
            "delta": "bounded reasoning",
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [{"type": "summary_text", "text": "bounded summary"}],
                "content": [{"type": "reasoning_text", "text": "bounded reasoning"}],
            },
        },
        {
            "type": "response.output_text.delta",
            "item_id": "msg_1",
            "output_index": 1,
            "content_index": 0,
            "delta": "final",
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "final"}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp_1",
                "status": "completed",
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": None,
                    "output_tokens": 5,
                    "output_tokens_details": {"reasoning_tokens": 2},
                    "total_tokens": 15,
                },
            },
        },
    ]

    assert set(event["type"] for event in events).issubset(
        RESPONSES_CODEX_STREAM_EVENT_TYPES
    )
    assert all(validator.validate(event) for event in events)


@pytest.mark.parametrize(
    "event",
    [
        {"type": "response.web_search_call.in_progress", "item_id": "ws_1"},
        {
            "type": "response.output_item.done",
            "item": {"type": "web_search_call", "id": "ws_1", "status": "completed"},
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "custom_tool_call",
                "call_id": "call_1",
                "name": "shell",
                "namespace": "functions",
                "input": PRIVATE_CANARY,
            },
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "wait",
                "namespace": "functions",
                "arguments": "{}",
                "server_url": f"https://{PRIVATE_CANARY}.invalid",
            },
        },
        {"type": "response.failed", "response": {"error": PRIVATE_CANARY}},
        {"type": "response.incomplete", "response": {"reason": PRIVATE_CANARY}},
        {"type": "error", "message": PRIVATE_CANARY},
    ],
)
def test_hosted_authority_unknown_and_provider_failure_events_fail_closed(
    event: dict[str, object],
) -> None:
    validator = ResponsesStreamEventValidator(_profile())

    assert validator.validate(event) is False
    assert PRIVATE_CANARY not in repr(validator.safe_evidence())


@pytest.mark.parametrize(
    "action",
    [
        {"type": "search", "query": PRIVATE_CANARY},
        {"type": "open_page", "url": f"https://{PRIVATE_CANARY}.invalid"},
        {
            "type": "find_in_page",
            "url": f"https://{PRIVATE_CANARY}.invalid",
            "pattern": PRIVATE_CANARY,
        },
    ],
)
def test_web_search_stream_validates_all_official_actions_content_free(action) -> None:
    validator = ResponsesStreamEventValidator(
        ResponsesStreamValidationProfile(web_search=True, web_search_max_tool_calls=1)
    )
    event = {
        "type": "response.output_item.done",
        "output_index": 0,
        "sequence_number": 1,
        "item": {
            "type": "web_search_call",
            "id": "ws_action_1",
            "status": "completed",
            "action": action,
        },
    }
    assert validator.validate(event)
    evidence = validator.take_web_search_evidence()
    assert evidence == (
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "sequence_number": 1,
            "item": {
                "type": "web_search_call",
                "id": "ws_action_1",
                "status": "completed",
                "output_index": 0,
                "sequence_number": 1,
                "action": {"type": action["type"]},
            },
        },
    )
    assert PRIVATE_CANARY not in repr(validator.__dict__)


@pytest.mark.parametrize(
    "field_overrides",
    [
        {"sequence_number": -1},
        {"output_index": -1},
        {"item": {"type": "web_search_call", "status": "completed"}},
        {
            "item": {
                "type": "web_search_call",
                "id": "ws_bad_action",
                "status": "completed",
                "action": {"type": "unsupported", "query": PRIVATE_CANARY},
            }
        },
    ],
)
def test_web_search_stream_rejects_bounds_and_malformed_actions_without_canaries(
    field_overrides,
) -> None:
    validator = ResponsesStreamEventValidator(
        ResponsesStreamValidationProfile(web_search=True, web_search_max_tool_calls=1)
    )
    event = {
        "type": "response.output_item.done",
        "output_index": 0,
        "sequence_number": 1,
        "item": {
            "type": "web_search_call",
            "id": "ws_valid",
            "status": "completed",
            "action": {"type": "search", "query": "safe"},
        },
    }
    event.update(field_overrides)
    assert not validator.validate(event)
    assert PRIVATE_CANARY not in repr(validator.safe_evidence())

    valid = {
        "type": "response.output_item.done",
        "output_index": 0,
        "sequence_number": 2,
        "item": {
            "type": "web_search_call",
            "id": "ws_first",
            "status": "completed",
            "action": {"type": "search", "query": "safe"},
        },
    }
    assert validator.validate(valid)
    for sequence in range(3, 17):
        assert validator.validate({**valid, "sequence_number": sequence})
    overflow = {**valid, "sequence_number": 17}
    assert not validator.validate(overflow)
    assert PRIVATE_CANARY not in repr(validator.safe_evidence())


def test_orphan_delta_duplicate_ids_and_mismatched_done_fail_closed() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    added = _added_tool(
        item_id="fc_1",
        call_id="call_1",
        namespace="functions",
        name="wait",
        custom=False,
    )
    assert validator.validate(added)
    assert not validator.validate(copy.deepcopy(added))

    other = ResponsesStreamEventValidator(_profile())
    assert not other.validate(
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_orphan",
            "output_index": 0,
            "delta": PRIVATE_CANARY,
        }
    )
    assert validator.validate(
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1",
            "output_index": 0,
            "delta": "{}",
        }
    )
    assert not validator.validate(
        _done_tool(
            item_id="fc_1",
            call_id="call_1",
            namespace="functions",
            name="wait",
            custom=False,
            text='{"mismatch":true}',
        )
    )


def test_event_and_replay_size_caps_fail_closed_without_echoing_content() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(
        _added_tool(
            item_id="ctc_1",
            call_id="call_1",
            namespace="functions",
            name="exec",
            custom=True,
        )
    )
    assert not validator.validate(
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": "ctc_1",
            "output_index": 0,
            "delta": PRIVATE_CANARY * 10_000,
        }
    )

    items = [
        _additional_tools(),
        {
            "type": "custom_tool_call",
            "id": "ctc_1",
            "name": "exec",
            "call_id": "call_1",
            "input": PRIVATE_CANARY,
        },
        {"type": "custom_tool_call_output", "call_id": "call_1", "output": "x"},
    ]
    with pytest.raises(RequestPolicyError) as exc_info:
        _policy(
            Settings(RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES=4)
        ).apply(
            _body(input_items=items),
            allow_codex_request_envelope=True,
            allow_codex_client_tools=True,
            allow_codex_streaming_tool_events=True,
        )
    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_too_large"
    assert PRIVATE_CANARY not in exc_info.value.safe_message


def test_codex_outputs_without_all_gates_are_rejected_before_replay() -> None:
    body = _body(
        input_items=[
            _additional_tools(),
            {"type": "custom_tool_call_output", "call_id": "call_1", "output": "x"},
        ]
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        _policy(Settings()).apply(
            body,
            allow_codex_request_envelope=True,
            allow_codex_client_tools=True,
            allow_codex_streaming_tool_events=False,
        )

    assert exc_info.value.error_code == "responses_codex_streaming_tool_events_not_allowed"


@pytest.mark.parametrize("custom", [False, True])
def test_roundtrip_replay_is_deep_copied_metered_and_exact(custom: bool) -> None:
    call_type = "custom_tool_call" if custom else "function_call"
    output_type = "custom_tool_call_output" if custom else "function_call_output"
    text_field = "input" if custom else "arguments"
    name = "exec" if custom else "wait"
    call = {
        "type": call_type,
        "id": "ctc_1" if custom else "fc_1",
        "status": "completed",
        "namespace": "functions",
        "name": name,
        "call_id": "call_1",
        text_field: 'text("SAFE")' if custom else '{"value":"ok"}',
    }
    output_value: object = (
        [
            {"type": "input_text", "text": "tool status"},
            {"type": "input_text", "text": "SAFE_TOOL_RESULT"},
        ]
        if custom
        else "SAFE_TOOL_RESULT"
    )
    output = {"type": output_type, "call_id": "call_1", "output": output_value}
    body = _body(input_items=[_additional_tools(), call, output])
    original = copy.deepcopy(body)

    result = _apply(body)

    assert result.effective_body["input"][1] == call
    assert result.effective_body["input"][2] == output
    assert result.estimated_input_tokens > 0
    result.effective_body["input"][1][text_field] = "mutated"
    assert body == original


@pytest.mark.parametrize(
    ("custom", "output_id"),
    [
        (False, "fco_1"),
        (True, "ctco_" + "a" * 36),
    ],
)
def test_optional_bounded_codex_output_item_id_is_canonical(custom: bool, output_id: str) -> None:
    if custom:
        assert len(output_id) == len(output_id.encode("ascii")) == 41
    call_type = "custom_tool_call" if custom else "function_call"
    output_type = "custom_tool_call_output" if custom else "function_call_output"
    text_field = "input" if custom else "arguments"
    name = "exec" if custom else "wait"
    call = {
        "type": call_type,
        "id": "ctc_1" if custom else "fc_1",
        "namespace": "functions",
        "name": name,
        "call_id": "call_1",
        text_field: "bounded",
    }
    output = {
        "type": output_type,
        "id": output_id,
        "call_id": "call_1",
        "output": "bounded result",
    }

    result = _apply(_body(input_items=[_additional_tools(), call, output]))

    assert result.effective_body["input"][2] == output


@pytest.mark.parametrize(
    "invalid_id",
    [
        7,
        "",
        "bad/output-id",
        "x" * 129,
    ],
)
def test_malformed_codex_output_item_ids_fail_safely(invalid_id: object) -> None:
    items = [
        _additional_tools(),
        {
            "type": "custom_tool_call",
            "id": "ctc_1",
            "namespace": "functions",
            "name": "exec",
            "call_id": "call_1",
            "input": "bounded",
        },
        {
            "type": "custom_tool_call_output",
            "id": invalid_id,
            "call_id": "call_1",
            "output": PRIVATE_CANARY,
        },
    ]

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(input_items=items))

    assert exc_info.value.error_code == "responses_codex_envelope_invalid"
    assert exc_info.value.param == "input[2].id"
    assert PRIVATE_CANARY not in exc_info.value.safe_message
    assert PRIVATE_CANARY not in str(exc_info.value)


@pytest.mark.parametrize("unknown_field", ["name", "status", "metadata"])
def test_unknown_codex_output_item_fields_remain_denied(unknown_field: str) -> None:
    output = {
        "type": "custom_tool_call_output",
        "id": "ctco_1",
        "call_id": "call_1",
        "output": PRIVATE_CANARY,
        unknown_field: PRIVATE_CANARY,
    }
    items = [
        _additional_tools(),
        {
            "type": "custom_tool_call",
            "id": "ctc_1",
            "namespace": "functions",
            "name": "exec",
            "call_id": "call_1",
            "input": "bounded",
        },
        output,
    ]

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(input_items=items))

    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_invalid"
    assert exc_info.value.param == f"input[2].{unknown_field}"
    assert PRIVATE_CANARY not in exc_info.value.safe_message
    assert PRIVATE_CANARY not in str(exc_info.value)


@pytest.mark.parametrize(
    "items",
    [
        [
            _additional_tools(),
            {
                "type": "function_call_output",
                "id": "fco_orphan",
                "call_id": "call_1",
                "output": "orphan",
            },
        ],
        [
            _additional_tools(),
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "name": "unknown",
                "call_id": "call_1",
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "id": "fco_unknown",
                "call_id": "call_1",
                "output": "x",
            },
        ],
        [
            _additional_tools(),
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "name": "wait",
                "call_id": "call_1",
                "arguments": "{}",
            },
            {
                "type": "custom_tool_call_output",
                "id": "ctco_cross_type",
                "call_id": "call_1",
                "output": "x",
            },
        ],
        [
            _additional_tools(),
                {
                    "type": "custom_tool_call",
                    "id": "ctc_1",
                    "namespace": "collaboration",
                "name": "send_message",
                "call_id": "call_1",
                "input": PRIVATE_CANARY,
            },
            {
                "type": "custom_tool_call_output",
                "id": "ctco_unapproved",
                "call_id": "call_1",
                "output": "x",
            },
        ],
    ],
)
def test_orphan_unknown_mismatched_and_unapproved_replay_is_rejected(
    items: list[object],
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(input_items=items))

    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_invalid"
    assert PRIVATE_CANARY not in exc_info.value.safe_message


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom",
        resolved_model="gpt-test",
        native_currency="EUR",
        estimated_input_tokens=10,
        estimated_output_tokens=100,
        estimated_input_cost_native=Decimal("0.000010000"),
        estimated_output_cost_native=Decimal("0.000100000"),
        estimated_total_cost_native=Decimal("0.000110000"),
        estimated_total_cost_eur=Decimal("0.000110000"),
        pricing_rule_id=None,
        fx_rate_id=None,
        input_price_per_1m=Decimal("1.000000000"),
        output_price_per_1m=Decimal("1.000000000"),
        fx_rate=Decimal("1"),
    )


def _monitor() -> ResponsesStreamingLiveBurnMonitor:
    policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 0},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1_000_000,
    )
    budget = build_responses_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=None,
        token_limit_total=1_000_000,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    assert budget is not None
    return ResponsesStreamingLiveBurnMonitor(budget)


@pytest.mark.parametrize(
    "event_type",
    [
        "response.output_text.delta",
        "response.function_call_arguments.delta",
        "response.custom_tool_call_input.delta",
        "response.reasoning_summary_text.delta",
        "response.reasoning_text.delta",
    ],
)
def test_live_burn_counts_every_forwarded_generated_delta(event_type: str) -> None:
    monitor = _monitor()
    event: dict[str, object] = {
        "type": event_type,
        "item_id": "item_1",
        "delta": PRIVATE_CANARY,
    }
    if "summary" in event_type:
        event["summary_index"] = 0
    elif "reasoning_text" in event_type or "output_text" in event_type:
        event["content_index"] = 0

    monitor.observe_chunk(event)

    assert monitor.estimated_output_tokens > 0


def test_live_burn_counts_direct_done_but_not_delta_plus_done_twice() -> None:
    direct = _monitor()
    direct.observe_chunk(
        _done_tool(
            item_id="ctc_1",
            call_id="call_1",
            namespace="functions",
            name="exec",
            custom=True,
            text=PRIVATE_CANARY,
        )
    )
    assert direct.estimated_output_tokens > 0

    streamed = _monitor()
    streamed.observe_chunk(
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": "ctc_1",
            "output_index": 0,
            "delta": PRIVATE_CANARY,
        }
    )
    after_delta = streamed.estimated_output_tokens
    streamed.observe_chunk(
        _done_tool(
            item_id="ctc_1",
            call_id="call_1",
            namespace="functions",
            name="exec",
            custom=True,
            text=PRIVATE_CANARY,
        )
    )

    assert streamed.estimated_output_tokens == after_delta


def test_threshold_crossing_tool_delta_is_counted_before_stop() -> None:
    policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 0},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    budget = build_responses_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=None,
        token_limit_total=11,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    assert budget is not None
    monitor = ResponsesStreamingLiveBurnMonitor(budget)

    result = monitor.observe_chunk(
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": "ctc_1",
            "output_index": 0,
            "delta": PRIVATE_CANARY,
        }
    )

    assert result is not None
    assert result.estimated_output_tokens > 0
    assert PRIVATE_CANARY not in repr(result.metadata)


def _parsed_request(body: dict[str, object]) -> capture.ParsedHttpRequest:
    raw = json.dumps(body, separators=(",", ":")).encode()
    return capture.ParsedHttpRequest(
        method="POST",
        target="/v1/responses",
        version="HTTP/1.1",
        headers=(
            ("content-type", "application/json"),
            ("content-length", str(len(raw))),
            ("authorization", "Bearer fixed-dummy"),
        ),
        body=raw,
    )


def test_manual_verifier_validates_pair_without_returning_payloads() -> None:
    request = _parsed_request(
        {
            "input": [
                {
                    "type": "custom_tool_call",
                    "namespace": "functions",
                    "name": "exec",
                    "call_id": verifier.TOOL_CALL_ID,
                    "input": verifier.SAFE_CODE_MODE_INPUT,
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": verifier.TOOL_CALL_ID,
                    "output": "SAFE_TOOL_RESULT",
                },
            ]
        }
    )

    assert verifier.validate_second_request(request) is None


def test_manual_verifier_rejects_authority_and_malformed_sse_safely() -> None:
    request = _parsed_request(
        {
            "input": [
                {
                    "type": "custom_tool_call",
                    "namespace": "functions",
                    "name": "shell",
                    "call_id": verifier.TOOL_CALL_ID,
                    "input": PRIVATE_CANARY,
                },
                {
                    "type": "custom_tool_call_output",
                    "call_id": verifier.TOOL_CALL_ID,
                    "output": PRIVATE_CANARY,
                },
            ]
        }
    )
    with pytest.raises(verifier.VerificationError) as exc_info:
        verifier.validate_second_request(request)
    assert PRIVATE_CANARY not in str(exc_info.value)

    malformed = verifier._sse_body(verifier.FIRST_RESPONSE_EVENTS).replace(
        b"response.created", PRIVATE_CANARY.encode(), 1
    )
    with pytest.raises(verifier.VerificationError) as sse_exc:
        verifier.validate_sse_body(malformed, events=verifier.FIRST_RESPONSE_EVENTS)
    assert PRIVATE_CANARY not in str(sse_exc.value)


def test_manual_verifier_mocks_subprocess_and_preserves_capture_isolation(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, b'{"type":"turn.completed"}\n', b"")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    environment = capture._isolated_environment(Path("/tmp/fixed-codex-home"))

    result = verifier._run_codex(
        Path("/usr/bin/codex"),
        workdir=Path("/tmp/fixed-codex-work"),
        port=12345,
        environment=environment,
    )

    command = seen["command"]
    assert result.returncode == 0
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "read-only" in command
    assert seen["kwargs"]["env"] == environment
    assert set(environment).isdisjoint(
        {"OPENAI_API_KEY", "OPENAI_UPSTREAM_API_KEY", "OPENROUTER_API_KEY"}
    )


def test_manual_verifier_mocks_socket_and_binds_only_numeric_loopback(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeSocket:
        def setsockopt(self, *args):
            calls.append(("setsockopt", args))

        def bind(self, address):
            calls.append(("bind", address))

        def listen(self, count):
            calls.append(("listen", count))

        def settimeout(self, value):
            calls.append(("settimeout", value))

        def getsockname(self):
            return ("127.0.0.1", 43210)

        def close(self):
            calls.append(("close", None))

    class FakeThread:
        def __init__(self, **kwargs):
            calls.append(("thread", kwargs["name"]))

        def start(self):
            calls.append(("thread_start", None))

        def join(self, timeout):
            calls.append(("thread_join", timeout))

    monkeypatch.setattr(verifier.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(verifier.threading, "Thread", FakeThread)
    server = verifier.RoundtripLoopbackServer()

    server.start()
    server.stop()

    assert ("bind", ("127.0.0.1", 0)) in calls
    assert ("listen", 2) in calls
    assert server.port == 43210


def test_manual_verifier_fixture_pin_and_pytest_purity() -> None:
    fixture = Path("tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json")
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == (
        "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
    )
    source = Path("scripts/verify_codex_tool_roundtrip.py").read_text()
    assert "if __name__ == \"__main__\"" in source
    assert "verify_roundtrip(" not in source.split('if __name__ == "__main__"')[1]


def test_gateway_forwards_frames_in_order_and_holds_completed_until_accounting(
    monkeypatch,
) -> None:
    import asyncio

    import slaif_gateway.services.responses_gateway as gateway

    timeline: list[str] = []
    event_payloads = [
        {"type": "response.created", "response": {"id": "resp_1"}},
        _added_tool(
            item_id="ctc_1",
            call_id="call_1",
            namespace="functions",
            name="exec",
            custom=True,
        ),
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": "ctc_1",
            "call_id": "call_1",
            "output_index": 0,
            "delta": 'text("SAFE")',
        },
        _done_tool(
            item_id="ctc_1",
            call_id="call_1",
            namespace="functions",
            name="exec",
            custom=True,
            text='text("SAFE")',
        ),
        {
            "type": "response.completed",
            "response": {
                "id": "resp_1",
                "status": "completed",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 2,
                },
            },
        },
    ]
    raw_events = [f"data: {json.dumps(payload, separators=(',', ':'))}\n\n" for payload in event_payloads]

    class FakeAdapter:
        async def stream_response(self, request):
            for index, (payload, raw_event) in enumerate(
                zip(event_payloads, raw_events, strict=True)
            ):
                timeline.append(f"provider:{index}")
                yield ProviderStreamChunk(
                    provider=request.provider,
                    upstream_model=request.upstream_model,
                    data=json.dumps(payload),
                    raw_sse_event=raw_event,
                    json_body=payload,
                    usage=(
                        ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
                        if payload["type"] == "response.completed"
                        else None
                    ),
                )

    async def fake_record_completed(**kwargs):
        timeline.append("accounting:record")
        return SimpleNamespace(usage_ledger_id=uuid.uuid4())

    async def fake_finalize(**kwargs):
        timeline.append("accounting:finalize")
        return SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            actual_cost_eur=Decimal("0"),
        )

    async def fake_persist_replay(**kwargs):
        timeline.append("replay:persist")
        return 1

    monkeypatch.setattr(gateway, "get_provider_adapter", lambda route, settings: FakeAdapter())
    monkeypatch.setattr(
        gateway,
        "_record_provider_completed_before_finalization",
        fake_record_completed,
    )
    monkeypatch.setattr(gateway, "_finalize_successful_response", fake_finalize)
    monkeypatch.setattr(gateway, "_persist_codex_replay_references", fake_persist_replay)
    monkeypatch.setattr(gateway, "_record_success_metrics", lambda **kwargs: None)
    monkeypatch.setattr(gateway, "record_provider_call_result", lambda **kwargs: None)

    response = gateway._streaming_responses_response(
        authenticated_key=SimpleNamespace(gateway_key_id=uuid.uuid4()),
        route=SimpleNamespace(
            provider="openai",
            resolved_model="gpt-test",
            route_id=uuid.uuid4(),
        ),
        policy_result=SimpleNamespace(),
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
        iterator = response.body_iterator.__aiter__()
        first = await anext(iterator)
        assert first == raw_events[0]
        assert timeline == ["provider:0"]
        values = [first]
        async for value in iterator:
            values.append(value)
            if value == raw_events[-1]:
                timeline.append("client:completed")
        return values

    forwarded = asyncio.run(collect())

    assert forwarded == raw_events
    assert timeline[-4:] == [
        "accounting:record",
        "accounting:finalize",
        "replay:persist",
        "client:completed",
    ]


def test_replay_persistence_failure_after_accounting_suppresses_completed(monkeypatch) -> None:
    import asyncio

    import slaif_gateway.services.responses_gateway as gateway

    timeline: list[str] = []
    tool_done = _done_tool(
        item_id="ctc_1",
        call_id="call_1",
        namespace="functions",
        name="exec",
        custom=True,
        text='text("SAFE")',
    )
    completed = {
        "type": "response.completed",
        "response": {
            "id": "resp_1",
            "status": "completed",
            "usage": {
                "input_tokens": 1,
                "input_tokens_details": None,
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 2,
            },
        },
    }
    payloads = [tool_done, completed]
    raw_events = [f"data: {json.dumps(payload, separators=(',', ':'))}\n\n" for payload in payloads]

    class FakeAdapter:
        async def stream_response(self, request):
            for payload, raw_event in zip(payloads, raw_events, strict=True):
                yield ProviderStreamChunk(
                    provider=request.provider,
                    upstream_model=request.upstream_model,
                    data=json.dumps(payload),
                    raw_sse_event=raw_event,
                    json_body=payload,
                    usage=(
                        ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
                        if payload["type"] == "response.completed"
                        else None
                    ),
                )

    async def fake_record_completed(**kwargs):
        timeline.append("accounting:record")
        return SimpleNamespace(usage_ledger_id=uuid.uuid4())

    async def fake_finalize(**kwargs):
        timeline.append("accounting:finalize")
        return SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            actual_cost_eur=Decimal("0"),
        )

    async def fail_persist(**kwargs):
        timeline.append("replay:persist-failed")
        raise CodexReplayReferenceError(
            "Codex replay references could not be persisted safely.",
            error_code="responses_codex_replay_persistence_failed",
        )

    monkeypatch.setattr(gateway, "get_provider_adapter", lambda route, settings: FakeAdapter())
    monkeypatch.setattr(
        gateway,
        "_record_provider_completed_before_finalization",
        fake_record_completed,
    )
    monkeypatch.setattr(gateway, "_finalize_successful_response", fake_finalize)
    monkeypatch.setattr(gateway, "_persist_codex_replay_references", fail_persist)
    monkeypatch.setattr(gateway, "_record_success_metrics", lambda **kwargs: None)
    monkeypatch.setattr(gateway, "record_provider_call_result", lambda **kwargs: None)

    response = gateway._streaming_responses_response(
        authenticated_key=SimpleNamespace(gateway_key_id=uuid.uuid4()),
        route=SimpleNamespace(
            provider="openai",
            resolved_model="gpt-test",
            route_id=uuid.uuid4(),
        ),
        policy_result=SimpleNamespace(),
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
        return [value async for value in response.body_iterator]

    forwarded = asyncio.run(collect())
    assert forwarded[0] == raw_events[0]
    assert raw_events[1] not in forwarded
    assert "responses_codex_replay_persistence_failed" in forwarded[-1]
    assert timeline == [
        "accounting:record",
        "accounting:finalize",
        "replay:persist-failed",
    ]


@pytest.mark.parametrize(
    "estimate_reason",
    [
        "responses_streaming_usage_missing_estimated",
        "responses_streaming_provider_error_estimated",
        "responses_streaming_client_disconnected_estimated",
    ],
)
def test_tool_output_interruption_paths_record_estimated_usage(
    monkeypatch,
    estimate_reason: str,
) -> None:
    import asyncio

    import slaif_gateway.services.responses_gateway as gateway

    monitor = _monitor()
    monitor.observe_chunk(
        {
            "type": "response.custom_tool_call_input.delta",
            "item_id": "ctc_1",
            "output_index": 0,
            "delta": PRIVATE_CANARY,
        }
    )
    calls: list[dict[str, object]] = []

    async def fake_estimate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(accounting_status="estimated")

    async def unexpected_release(**kwargs):
        raise AssertionError("a token-bearing tool stream must not fully release")

    async def unexpected_replay_persistence(**kwargs):
        raise AssertionError("interrupted streams must not persist replay references")

    monkeypatch.setattr(
        gateway,
        "_record_responses_streaming_interrupted_estimate",
        fake_estimate,
    )
    monkeypatch.setattr(gateway, "_record_provider_failure_and_release", unexpected_release)
    monkeypatch.setattr(
        gateway,
        "_persist_codex_replay_references",
        unexpected_replay_persistence,
    )

    asyncio.run(
        gateway._finalize_responses_stream_interruption_after_output(
            reservation=SimpleNamespace(reservation_id=uuid.uuid4()),
            authenticated_key=SimpleNamespace(gateway_key_id=uuid.uuid4()),
            route=SimpleNamespace(provider="openai", resolved_model="gpt-test"),
            policy_result=SimpleNamespace(),
            cost_estimate=_estimate(),
            request_id="req_1",
            provider_error=ProviderError(
                "safe failure",
                provider="openai",
                error_code="safe_failure",
            ),
            request=None,
            estimate_reason=estimate_reason,
            stream_estimate_monitor=monitor,
        )
    )

    assert len(calls) == 1
    assert calls[0]["estimate_reason"] == estimate_reason
    assert calls[0]["estimated_output_tokens"] > 0
    assert PRIVATE_CANARY not in repr(calls[0]["response_metadata"])
