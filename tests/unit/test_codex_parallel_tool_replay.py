"""Pair tool results by invocation identity, including natural parallel batches."""

import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
)
from tests.unit.test_compatibility_presets import _module


def _body():
    calls = [
        dict(
            type="function_call",
            id=f"fc_synthetic_{n}",
            call_id=f"call_synthetic_{n}",
            namespace="functions",
            name="exec_command",
            arguments="{}",
            status="completed",
        )
        for n in (1, 2)
    ]
    outputs = [
        dict(type="function_call_output", call_id=c["call_id"], output="synthetic") for c in calls
    ]
    declaration = {
        "type": "additional_tools",
        "role": "developer",
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            }
        ],
    }
    return {
        "model": "synthetic",
        "stream": True,
        "parallel_tool_calls": False,
        "input": [declaration, *calls, *outputs],
    }


def _apply(body, **gates):
    module = _module()
    options = dict(
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )
    options.update(gates)
    return ResponsesRequestPolicy(Settings(), client_spec=module.policy_spec).apply(
        module.normalize_responses(body).body, **options
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("parallel", [False, True])
def test_parallel_history_is_preserved_regardless_of_current_generation_preference(
    reverse, parallel
):
    body = _body()
    body["parallel_tool_calls"] = parallel
    if reverse:
        body["input"][-2:] = reversed(body["input"][-2:])
    original = copy.deepcopy(body)
    result = _apply(body)
    assert body == original
    assert result.effective_body["input"][1:] == original["input"][1:]


@pytest.mark.parametrize(
    "mutation",
    [
        "before_call",
        "missing",
        "duplicate_output",
        "duplicate_call",
        "wrong_call",
        "wrong_kind",
        "user_boundary",
        "undeclared",
    ],
)
def test_invalid_call_output_graphs_still_fail_closed(mutation):
    body = _body()
    items = body["input"]
    if mutation == "before_call":
        items[1], items[3] = items[3], items[1]
    elif mutation == "missing":
        items.pop()
    elif mutation == "duplicate_output":
        items.append(copy.deepcopy(items[-1]))
    elif mutation == "duplicate_call":
        items[2] = copy.deepcopy(items[1])
    elif mutation == "wrong_call":
        items[-1]["call_id"] = "call_unknown"
    elif mutation == "wrong_kind":
        items[-1]["type"] = "custom_tool_call_output"
    elif mutation == "user_boundary":
        items.insert(
            3,
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "new turn"}],
            },
        )
    elif mutation == "undeclared":
        items[2]["name"] = "unknown"
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body)


@pytest.mark.parametrize(
    "gate",
    [
        "allow_codex_request_envelope",
        "allow_codex_client_tools",
        "allow_codex_streaming_tool_events",
    ],
)
def test_parallel_history_keeps_independent_capability_gates(gate):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(_body(), **{gate: False})


def test_parallel_function_and_custom_outputs_keep_kind_and_identity():
    body = _body()
    body["input"][0]["tools"][0]["tools"].append(
        {
            "type": "custom",
            "name": "apply_patch",
            "format": {"type": "grammar", "syntax": "lark", "definition": "start: /.+/"},
        }
    )
    call = body["input"][2]
    call.update(type="custom_tool_call", name="apply_patch", input="synthetic patch")
    del call["arguments"]
    body["input"][-1]["type"] = "custom_tool_call_output"
    assert _apply(body).effective_body["input"][1:] == body["input"][1:]


@pytest.mark.parametrize(
    "intermediate",
    [
        {
            "type": "reasoning",
            "summary": [],
            "content": [{"type": "reasoning_text", "text": "synthetic"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "synthetic"}],
        },
    ],
)
def test_validated_assistant_context_is_preserved_between_call_and_result(intermediate):
    body = _body()
    body["input"].insert(3, intermediate)
    assert _apply(body).effective_body["input"][1:] == body["input"][1:]
