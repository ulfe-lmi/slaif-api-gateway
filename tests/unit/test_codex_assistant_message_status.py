"""Completed assistant history remains an explicit, version-owned dialect fact."""

from dataclasses import replace
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_POLICY_SPEC
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE,
    Codex0162ResponsesClientModule,
)
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
)


def _candidate():
    path = Path(__file__).parents[2] / (
        "app/slaif_gateway/modules/clients/profiles/codex_0162_assistant_history.json"
    )
    return Codex0162ResponsesClientModule(load_codex_profile_file(str(path)))


def _message(**changes):
    return {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "Synthetic pre-tool commentary."}],
        **changes,
    }


def _apply(message, *, spec=None, **gates):
    options = dict(
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )
    options.update(gates)
    return ResponsesRequestPolicy(
        Settings(), client_spec=spec or _candidate().policy_spec
    ).apply(
        {"model": "synthetic", "input": [message], "max_output_tokens": 20},
        **options,
    )


def test_candidate_preserves_completed_assistant_status_and_meters_content():
    message = _message()
    result = _apply(message)
    assert result.effective_body["input"] == [message]
    assert result.estimated_message_input_tokens > 0
    without_status = dict(message)
    without_status.pop("status")
    assert result.estimated_message_input_tokens == _apply(
        without_status
    ).estimated_message_input_tokens


@pytest.mark.parametrize("status", [None, True, 0, [], {}, "in_progress", "incomplete", ""])
def test_candidate_rejects_every_unapproved_status(status):
    with pytest.raises(ResponsesRequestPolicyError) as error:
        _apply(_message(status=status))
    assert error.value.param == "input[0].status"


@pytest.mark.parametrize("role", ["user", "developer", "system"])
def test_completed_status_is_assistant_only(role):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(_message(role=role))


@pytest.mark.parametrize(
    "gate",
    ["allow_codex_request_envelope", "allow_codex_client_tools", "allow_codex_streaming_tool_events"],
)
def test_completed_status_requires_every_independent_gate(gate):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(_message(), **{gate: False})


@pytest.mark.parametrize(
    "spec",
    [
        CODEX_0149_POLICY_SPEC,
        CODEX_0162_CLIENT_MODULE.policy_spec,
        replace(_candidate().policy_spec, allow_completed_assistant_message_status=False),
    ],
)
def test_historical_and_disabled_specs_still_reject_status(spec):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(_message(), spec=spec)


def test_candidate_does_not_allow_other_message_fields():
    with pytest.raises(ResponsesRequestPolicyError) as error:
        _apply(_message(unapproved=True))
    assert error.value.param == "input[0].unapproved"


def test_completed_commentary_survives_a_tool_result_continuation():
    declaration = {
        "type": "additional_tools", "role": "developer",
        "tools": [{
            "type": "namespace", "name": "functions",
            "tools": [{
                "type": "function", "name": "exec_command",
                "parameters": {"type": "object", "properties": {}},
            }],
        }],
    }
    history = [
        declaration,
        {"type": "message", "role": "user", "content": "Synthetic task."},
        _message(),
        {
            "type": "function_call", "id": "fc_synthetic", "call_id": "call_synthetic",
            "namespace": "functions", "name": "exec_command", "arguments": "{}",
            "status": "completed",
        },
        {"type": "function_call_output", "call_id": "call_synthetic", "output": "Synthetic result."},
    ]
    module = _candidate()
    body = {"model": "synthetic", "input": history, "stream": True, "max_output_tokens": 20}
    result = ResponsesRequestPolicy(Settings(), client_spec=module.policy_spec).apply(
        module.normalize_responses(body).body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )
    assert result.effective_body["input"][2] == history[2]
    assert result.effective_body["input"][3:] == history[3:]


def test_ordinary_responses_does_not_accept_completed_status():
    with pytest.raises(ResponsesRequestPolicyError):
        ResponsesRequestPolicy(Settings()).apply(
            {"model": "synthetic", "input": [_message()], "max_output_tokens": 20}
        )


def test_revision9_is_opt_in_and_has_a_distinct_policy_identity():
    candidate = _candidate()
    assert candidate.module_version == "9"
    assert CODEX_0162_CLIENT_MODULE.module_version == "8"
    assert candidate.fixture_sha256 != CODEX_0162_CLIENT_MODULE.fixture_sha256
