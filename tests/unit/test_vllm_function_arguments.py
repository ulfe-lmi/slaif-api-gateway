"""Completed native-vLLM function calls must contain complete JSON objects."""

import copy

import pytest

from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.providers.errors import ProviderRequestError, ProviderResponseParseError
from tests.unit.test_local_coding_vllm import body, native_events

INVALID = [
    '{"cmd": "unterminated',
    '{"cmd":',
    "[]",
    "null",
    '"text"',
    '{"cmd":1,"cmd":2}',
    '{"x":NaN}',
    '{"x":Infinity}',
]


@pytest.mark.parametrize("arguments", INVALID)
def test_invalid_function_arguments_are_not_marked_done(arguments):
    codec = VLLMToolCodec(body())
    events = native_events(arguments)
    for event in events:
        if isinstance(event.get("item"), dict):
            event["item"]["name"] = "functions.exec_command"
        if "name" in event:
            event["name"] = "functions.exec_command"
    emitted = []
    with pytest.raises(ProviderResponseParseError) as exc:
        for event in events:
            emitted.extend(codec.events(event))
    assert exc.value.error_code == "vllm_function_arguments_invalid"
    assert not any(
        e["type"] in ("response.function_call_arguments.done", "response.output_item.done")
        for e in emitted
    )
    assert not codec.calls["fc_synthetic"].done


@pytest.mark.parametrize("arguments", INVALID)
def test_invalid_replay_is_rejected_before_provider_work_without_repairing_history(arguments):
    original = body()
    original["input"].append(
        {
            "type": "function_call",
            "id": "fc_synthetic",
            "call_id": "call_synthetic",
            "namespace": "functions",
            "name": "exec_command",
            "arguments": arguments,
        }
    )
    before = copy.deepcopy(original)
    with pytest.raises(ProviderRequestError) as exc:
        VLLMToolCodec(original)
    assert exc.value.status_code == 400
    assert exc.value.error_code == "vllm_replay_arguments_invalid"
    assert "Start a new conversation" in exc.value.safe_message
    assert arguments not in exc.value.safe_message
    assert original == before


@pytest.mark.parametrize(
    "arguments", ["{}", '{"cmd":"printf ok"}', '{"x":{"nested":[1,true,null]}}']
)
def test_valid_function_replay_is_preserved(arguments):
    original = body()
    original["input"].append(
        {
            "type": "function_call",
            "id": "fc_synthetic",
            "call_id": "call_synthetic",
            "namespace": "functions",
            "name": "exec_command",
            "arguments": arguments,
        }
    )
    assert VLLMToolCodec(original).body["input"][-1]["arguments"] == arguments
