"""Visible reasoning stays visible across provider serialization differences."""

import copy

import pytest

from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator, ResponsesStreamValidationProfile, _MAX_STREAM_ITEM_TEXT_BYTES,
)
from slaif_gateway.services.responses_request_policy import responses_codex_encrypted_reasoning_replay_requested
from tests.unit.test_codex_0164_preset import module


def _item(form, *, done=False, item_id="rs_switch"):
    item = {
        "type": "reasoning", "id": item_id, "summary": [],
        "content": [{"type": "reasoning_text", "text": "synthetic reasoning"}] if done else [],
        "status": "completed" if done else "in_progress",
    }
    if form != "absent":
        item["encrypted_content"] = None if form == "null" else ""
    return item


def _events(form, *, response_id="resp_switch", item_id="rs_switch"):
    added = _item(form, item_id=item_id)
    done = _item(form, done=True, item_id=item_id)
    common = {"item_id": item_id, "output_index": 0, "content_index": 0}
    return [
        {"type": "response.created", "response": {"id": response_id, "status": "in_progress"}},
        {"type": "response.in_progress", "response": {"id": response_id, "status": "in_progress"}},
        {"type": "response.output_item.added", "output_index": 0, "item": added},
        {"type": "response.content_part.added", **common, "part": {"type": "reasoning_text", "text": ""}},
        {"type": "response.reasoning_text.delta", **common, "delta": "synthetic reasoning"},
        {"type": "response.reasoning_text.done", **common, "text": "synthetic reasoning"},
        {"type": "response.content_part.done", **common, "part": {"type": "reasoning_text", "text": "synthetic reasoning"}},
        {"type": "response.output_item.done", "output_index": 0, "item": done},
    ]


def _profile(encrypted=True, qualified=True):
    return ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        codex_encrypted_reasoning_replay=encrypted,
        allow_sparse_visible_reasoning=qualified,
    )


@pytest.mark.parametrize("form", ["absent", "null", "empty"])
def test_visible_history_does_not_request_encrypted_replay(form):
    assert not responses_codex_encrypted_reasoning_replay_requested({"input": [_item(form, done=True)]})


@pytest.mark.parametrize("value", ["opaque", 42, False, [], {}])
def test_opaque_or_malformed_ciphertext_retains_independent_gate(value):
    item = _item("empty", done=True)
    item["encrypted_content"] = value
    assert responses_codex_encrypted_reasoning_replay_requested({"input": [item]})


@pytest.mark.parametrize("form", ["absent", "null", "empty"])
@pytest.mark.parametrize("encrypted", [False, True])
def test_completed_visible_reasoning_accepts_all_empty_representations(form, encrypted):
    validator = ResponsesStreamEventValidator(_profile(encrypted))
    for sequence, event in enumerate(_events(form)):
        event["sequence_number"] = sequence
        original = copy.deepcopy(event)
        assert validator.validate(event), event["type"]
        assert event == original
    assert validator.take_replay_reference_candidates() == ()


@pytest.mark.parametrize("form", ["absent", "null", "empty"])
def test_unqualified_encrypted_profile_is_not_widened(form):
    validator = ResponsesStreamEventValidator(_profile(qualified=False))
    assert validator.validate(_events(form)[2])
    assert not validator.validate(_events(form)[-1])


@pytest.mark.parametrize("value", ["opaque", 42, False, [], {}])
@pytest.mark.parametrize("encrypted", [False, True])
def test_malformed_or_opaque_payload_cannot_use_visible_completion(value, encrypted):
    validator = ResponsesStreamEventValidator(_profile(encrypted))
    events = _events("null")
    for e in events[:-1]:
        assert validator.validate(e)
    events[-1]["item"]["encrypted_content"] = value
    assert not validator.validate(events[-1])


@pytest.mark.parametrize("change", ["unknown_field", "oversize", "wrong_content", "unknown_id"])
def test_null_ciphertext_does_not_relax_content_or_lifecycle_bounds(change):
    validator = ResponsesStreamEventValidator(_profile())
    events = _events("null")
    for e in events[:-1]:
        assert validator.validate(e)
    item = events[-1]["item"]
    if change == "unknown_field":
        item["server_url"] = "https://example.invalid"
    elif change == "oversize":
        item["content"][0]["text"] = "x" * (_MAX_STREAM_ITEM_TEXT_BYTES + 1)
    elif change == "wrong_content":
        item["content"][0]["type"] = "input_image"
    else:
        item["id"] = "rs_unknown"
    assert not validator.validate(events[-1])


def test_real_encrypted_output_still_creates_only_its_authenticated_candidate():
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_events("null")[2])
    item = {"type": "reasoning", "id": "rs_switch", "summary": [], "encrypted_content": "opaque"}
    assert validator.validate({"type": "response.output_item.done", "output_index": 0, "item": item})
    refs = validator.take_replay_reference_candidates()
    assert len(refs) == 1 and refs[0].item_kind == "reasoning"


def test_shipped_profile_digest_and_qualification_switch_are_unchanged():
    spec = module("0.167.1")
    assert spec.fixture_sha256 == "cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed"
    assert spec.policy_spec.allow_sparse_visible_reasoning
