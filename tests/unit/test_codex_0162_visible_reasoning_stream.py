"""Synthetic regressions matching the observed sparse Local reasoning events."""

import copy
from dataclasses import replace

import pytest

from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE
from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)


def _profile():
    return ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        codex_encrypted_reasoning_replay=True,
        allow_sparse_visible_reasoning=CODEX_0162_CLIENT_MODULE.policy_spec.allow_sparse_visible_reasoning,
    )


def _prefix():
    return [
        {
            "type": "response.created",
            "response": {"id": "resp_test", "status": "in_progress"},
            "sequence_number": 0,
        },
        {
            "type": "response.in_progress",
            "response": {"id": "resp_test", "status": "in_progress"},
            "sequence_number": 1,
        },
        {
            "type": "response.output_item.added",
            "sequence_number": 2,
            "item": {
                "id": "rs_test",
                "summary": [],
                "type": "reasoning",
                "content": [],
                "encrypted_content": "",
                "status": "in_progress",
            },
        },
    ]


def _delta():
    return {
        "type": "response.reasoning_text.delta",
        "item_id": "rs_test",
        "content_index": 0,
        "delta": "synthetic",
        "sequence_number": 3,
    }


def _done():
    return {
        "type": "response.output_item.done",
        "sequence_number": 4,
        "item": {
            "id": "rs_test",
            "type": "reasoning",
            "summary": [],
            "content": [{"type": "reasoning_text", "text": "synthetic"}],
            "encrypted_content": "",
        },
    }


def _started(profile=None):
    validator = ResponsesStreamEventValidator(profile or _profile())
    for event in _prefix():
        assert validator.validate(event)
    return validator


def test_sparse_reasoning_reaches_completion_without_fabricated_state():
    validator = _started()
    delta = _delta()
    original = copy.deepcopy(delta)
    assert validator.validate(delta)
    assert delta == original and "output_index" not in delta
    assert validator.validate(_done())
    assert validator.validate(
        {
            "type": "response.completed",
            "sequence_number": 5,
            "response": {
                "id": "resp_test",
                "status": "completed",
                "output": [_done()["item"]],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
        }
    )
    # Visible reasoning with empty ciphertext cannot create encrypted replay authority.
    assert validator.take_replay_reference_candidates() == ()


@pytest.mark.parametrize("value", [None, True, -1, "0", 1000001])
def test_present_output_index_stays_validated(value):
    event = _delta()
    event["output_index"] = value
    assert not _started().validate(event)


def test_old_profiles_still_require_output_index():
    old = replace(_profile(), allow_sparse_visible_reasoning=False)
    assert not _started(old).validate(_delta())


def test_unknown_or_missing_item_remains_rejected():
    event = _delta()
    event["item_id"] = "rs_unknown"
    assert not _started().validate(event)
    del event["item_id"]
    assert not _started().validate(event)
    assert not ResponsesStreamEventValidator(_profile()).validate(_delta())
    assert not ResponsesStreamEventValidator(_profile()).validate(_done())


def test_missing_content_index_and_oversized_delta_rejected():
    event = _delta()
    del event["content_index"]
    assert not _started().validate(event)
    event = _delta()
    event["delta"] = "x" * 65537
    assert not _started().validate(event)


@pytest.mark.parametrize("mutation", ["ciphertext", "unknown_field", "wrong_content"])
def test_visible_done_does_not_bypass_encrypted_or_shape_checks(mutation):
    validator = _started()
    assert validator.validate(_delta())
    event = _done()
    if mutation == "ciphertext":
        event["item"]["encrypted_content"] = "opaque"
    elif mutation == "unknown_field":
        event["item"]["server_url"] = "https://example.invalid"
    else:
        event["item"]["content"] = [{"type": "image", "text": "synthetic"}]
    assert not validator.validate(event)


def test_empty_ciphertext_visible_continuation_has_no_encrypted_replay_authority():
    from slaif_gateway.config import Settings
    from slaif_gateway.services.responses_request_policy import (
        ResponsesRequestPolicy,
        ResponsesRequestPolicyError,
        codex_replay_request_candidates,
    )

    spec = CODEX_0162_CLIENT_MODULE.policy_spec
    body = {
        "model": "qwen38-27b",
        "input": [
            {
                "type": "reasoning",
                "id": "rs_visible",
                "summary": [],
                "content": [{"type": "reasoning_text", "text": "synthetic context"}],
                "encrypted_content": "",
            },
            {"role": "user", "content": "Synthetic follow-up"},
        ],
    }

    def apply(selected):
        return ResponsesRequestPolicy(Settings(), client_spec=selected).apply(
            body,
            allow_codex_request_envelope=True,
            allow_codex_encrypted_reasoning_replay=True,
        )

    result = apply(spec).effective_body
    assert result["input"][0] == body["input"][0]
    assert codex_replay_request_candidates(result) == ()
    with pytest.raises(ResponsesRequestPolicyError):
        apply(replace(spec, allow_empty_visible_reasoning=False))
    body["input"][0]["content"] = [{"type": "image", "text": "synthetic"}]
    with pytest.raises(ResponsesRequestPolicyError):
        apply(spec)
