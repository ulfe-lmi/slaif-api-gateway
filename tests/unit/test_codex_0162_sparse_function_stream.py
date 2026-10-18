"""Synthetic regressions for observed Local sparse function argument events."""

from dataclasses import replace

import pytest

from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)


def _started(sparse=True):
    validator = ResponsesStreamEventValidator(
        ResponsesStreamValidationProfile(
            codex_streaming_tool_events=True,
            allow_sparse_function_events=sparse,
            declared_client_tools=frozenset({("functions", "exec_command", "function")}),
        )
    )
    assert validator.validate(
        {
            "type": "response.output_item.added",
            "sequence_number": 0,
            "output_index": 0,
            "item": {
                "type": "function_call",
                "id": "fc_test",
                "call_id": "call_test",
                "namespace": "functions",
                "name": "exec_command",
                "arguments": "",
                "status": "in_progress",
            },
        }
    )
    return validator


def _delta():
    return {
        "type": "response.function_call_arguments.delta",
        "item_id": "fc_test",
        "delta": "{}",
        "sequence_number": 1,
    }


def _done():
    return {
        "type": "response.function_call_arguments.done",
        "item_id": "fc_test",
        "name": "exec_command",
        "arguments": "{}",
        "sequence_number": 2,
    }


def test_sparse_arguments_roundtrip_requires_matching_final_item():
    validator = _started()
    assert validator.validate(_delta())
    assert validator.validate(_done())
    assert validator.validate(
        {
            "type": "response.output_item.done",
            "sequence_number": 3,
            "item": {
                "type": "function_call",
                "id": "fc_test",
                "call_id": "call_test",
                "namespace": "functions",
                "name": "exec_command",
                "arguments": "{}",
                "status": "completed",
            },
        }
    )
    assert len(validator.take_replay_reference_candidates()) == 1
    assert not validator.validate(_done())


def test_older_profiles_still_reject_sparse_delta_and_done():
    validator = _started(False)
    assert not validator.validate(_delta())
    assert not validator.validate(_done())


@pytest.mark.parametrize("value", [None, True, -1, "0", 1, 1000001])
def test_present_output_index_remains_bounded_and_matches_active_item(value):
    event = _delta()
    event["output_index"] = value
    assert not _started().validate(event)
    validator = _started()
    assert validator.validate(_delta())
    event = _done()
    event["output_index"] = value
    assert not validator.validate(event)


@pytest.mark.parametrize(
    "mutation", ["unknown_item", "wrong_name", "wrong_arguments", "extra", "oversize"]
)
def test_done_rejects_unmatched_or_unsafe_shape(mutation):
    validator = _started()
    assert validator.validate(_delta())
    event = _done()
    if mutation == "unknown_item":
        event["item_id"] = "fc_other"
    elif mutation == "wrong_name":
        event["name"] = "other"
    elif mutation == "wrong_arguments":
        event["arguments"] = "different"
    elif mutation == "extra":
        event["server_url"] = "https://example.invalid"
    else:
        event["arguments"] = "x" * 1048577
    assert not validator.validate(event)


def test_duplicate_done_and_late_delta_rejected():
    validator = _started()
    assert validator.validate(_delta())
    assert validator.validate(_done())
    assert not validator.validate(_done())
    assert not validator.validate(_delta())
    assert not ResponsesStreamEventValidator(
        replace(
            ResponsesStreamValidationProfile(),
            allow_sparse_function_events=True,
        )
    ).validate(_done())
