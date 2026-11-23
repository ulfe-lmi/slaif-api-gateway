"""Stream-level validation for the qualified id-less encrypted reasoning path.

The OpenCode Responses wire replays provider-encrypted reasoning as
``response.output_item.done`` items carrying exactly
``{type, summary, encrypted_content}`` -- no item ID, no status.  The
``allow_idless_encrypted_reasoning`` profile flag (default False) is the only
way such an item becomes valid; the captured reference then binds the
ciphertext itself instead of a fabricated protocol ID.  Legacy ID-bearing
streams stay byte-identical: their candidates carry ``encrypted_content=None``.
"""

from __future__ import annotations

import copy

from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)

CIPHER = "c" * 64
CIPHER_B = "d" * 64


def _profile(**overrides) -> ResponsesStreamValidationProfile:
    # The OpenCode wire carries its tool loop through the strict typed-SSE
    # validator, so output_item events route through _validate_codex_event.
    base = {
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": True,
        "allow_idless_encrypted_reasoning": True,
    }
    base.update(overrides)
    return ResponsesStreamValidationProfile(**base)


def _idless_reasoning_done(
    *, seq: int = 1, item_overrides: dict | None = None
) -> dict:
    item: dict = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "opaque"}],
        "encrypted_content": CIPHER,
    }
    if item_overrides is not None:
        item.update(item_overrides)
    return {
        "type": "response.output_item.done",
        "output_index": 0,
        "sequence_number": seq,
        "item": item,
    }


def test_idless_encrypted_reasoning_done_rejected_when_flag_off() -> None:
    validator = ResponsesStreamEventValidator(
        _profile(allow_idless_encrypted_reasoning=False)
    )
    assert validator.validate(_idless_reasoning_done()) is False
    assert validator.take_replay_reference_candidates() == ()


def test_idless_encrypted_reasoning_done_rejected_without_replay_flag() -> None:
    validator = ResponsesStreamEventValidator(
        _profile(codex_encrypted_reasoning_replay=False)
    )
    assert validator.validate(_idless_reasoning_done()) is False
    assert validator.take_replay_reference_candidates() == ()


def test_idless_encrypted_reasoning_done_accepted_when_flag_on() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_idless_reasoning_done()) is True
    (candidate,) = validator.take_replay_reference_candidates()
    assert candidate.item_kind == "reasoning"
    assert candidate.item_id is None
    assert candidate.encrypted_content == CIPHER
    assert candidate.call_id is None
    assert candidate.tool_namespace is None
    assert candidate.tool_name is None


def test_idless_encrypted_reasoning_added_rejected_even_when_flag_on() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    payload = _idless_reasoning_done()
    payload["type"] = "response.output_item.added"
    assert validator.validate(payload) is False


def test_idless_encrypted_reasoning_done_extra_status_rejected() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert (
        validator.validate(
            _idless_reasoning_done(item_overrides={"status": "completed"})
        )
        is False
    )


def test_present_null_id_rejected_even_when_flag_on() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert (
        validator.validate(
            _idless_reasoning_done(item_overrides={"id": None})
        )
        is False
    )
    assert validator.take_replay_reference_candidates() == ()


def test_present_malformed_id_rejected_even_when_flag_on() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert (
        validator.validate(
            _idless_reasoning_done(item_overrides={"id": "not an id!"})
        )
        is False
    )


def test_idless_encrypted_reasoning_done_empty_cipher_rejected() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert (
        validator.validate(
            _idless_reasoning_done(item_overrides={"encrypted_content": ""})
        )
        is False
    )
    assert validator.take_replay_reference_candidates() == ()


def test_idless_function_call_done_still_requires_str_id() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    payload = {
        "type": "response.output_item.done",
        "output_index": 0,
        "sequence_number": 1,
        "item": {
            "type": "function_call",
            "namespace": None,
            "name": "wait",
            "arguments": "{}",
            "call_id": "call_1",
        },
    }
    assert validator.validate(payload) is False
    assert validator.take_replay_reference_candidates() == ()


def test_idbearing_reasoning_candidate_stays_cipherless() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    payload = _idless_reasoning_done()
    payload["item"] = copy.deepcopy(payload["item"])
    payload["item"]["id"] = "rs_1"
    assert validator.validate(payload) is True
    (candidate,) = validator.take_replay_reference_candidates()
    assert candidate.item_kind == "reasoning"
    assert candidate.item_id == "rs_1"
    assert candidate.encrypted_content is None


def test_distinct_idless_ciphers_produce_distinct_candidates() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_idless_reasoning_done(seq=1)) is True
    assert (
        validator.validate(
            _idless_reasoning_done(seq=2, item_overrides={"encrypted_content": CIPHER_B})
        )
        is True
    )
    candidates = validator.take_replay_reference_candidates()
    assert [c.encrypted_content for c in candidates] == [CIPHER, CIPHER_B]
    assert all(c.item_id is None for c in candidates)
