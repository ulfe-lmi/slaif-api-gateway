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
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.streaming import (
    RESPONSES_CODEX_STREAM_EVENT_TYPES,
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    codex_client_tool_declarations,
    responses_codex_streaming_tool_events_allowed,
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
    return ResponsesRequestPolicy(Settings()).apply(
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
        assert ResponsesRequestPolicy(Settings()).apply(_body(), **kwargs).effective_body[
            "stream"
        ] is True
    else:
        with pytest.raises(RequestPolicyError):
            ResponsesRequestPolicy(Settings()).apply(_body(), **kwargs)


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
            "name": "exec",
            "call_id": "call_1",
            "input": PRIVATE_CANARY,
        },
        {"type": "custom_tool_call_output", "call_id": "call_1", "output": "x"},
    ]
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(
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
        ResponsesRequestPolicy(Settings()).apply(
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
    "items",
    [
        [
            _additional_tools(),
            {"type": "function_call_output", "call_id": "call_1", "output": "orphan"},
        ],
        [
            _additional_tools(),
            {
                "type": "function_call",
                "name": "unknown",
                "call_id": "call_1",
                "arguments": "{}",
            },
            {"type": "function_call_output", "call_id": "call_1", "output": "x"},
        ],
        [
            _additional_tools(),
            {
                "type": "function_call",
                "name": "wait",
                "call_id": "call_1",
                "arguments": "{}",
            },
            {"type": "custom_tool_call_output", "call_id": "call_1", "output": "x"},
        ],
        [
            _additional_tools(),
            {
                "type": "custom_tool_call",
                "namespace": "collaboration",
                "name": "send_message",
                "call_id": "call_1",
                "input": PRIVATE_CANARY,
            },
            {"type": "custom_tool_call_output", "call_id": "call_1", "output": "x"},
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

    monkeypatch.setattr(gateway, "get_provider_adapter", lambda route, settings: FakeAdapter())
    monkeypatch.setattr(
        gateway,
        "_record_provider_completed_before_finalization",
        fake_record_completed,
    )
    monkeypatch.setattr(gateway, "_finalize_successful_response", fake_finalize)
    monkeypatch.setattr(gateway, "_record_success_metrics", lambda **kwargs: None)
    monkeypatch.setattr(gateway, "record_provider_call_result", lambda **kwargs: None)

    response = gateway._streaming_responses_response(
        authenticated_key=SimpleNamespace(gateway_key_id=uuid.uuid4()),
        route=SimpleNamespace(provider="openai", resolved_model="gpt-test"),
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
    assert timeline[-3:] == [
        "accounting:record",
        "accounting:finalize",
        "client:completed",
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

    monkeypatch.setattr(
        gateway,
        "_record_responses_streaming_interrupted_estimate",
        fake_estimate,
    )
    monkeypatch.setattr(gateway, "_record_provider_failure_and_release", unexpected_release)

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
