"""Stream-level validation for the selected-profile encrypted reasoning wire.

Observed provider output items carry real IDs on both added and done; the
pinned OpenCode SDK drops IDs only on the request-side replay it sends back
in the next turn, which input eligibility covers separately.  Provider
output without an ID therefore fails closed on every encrypted-replay
profile, including the selected one.

The ``allow_idless_encrypted_reasoning`` profile flag (default False) scopes
the qualified OpenCode 1.19.3 additions: the exact observed id-bearing
``{type, id, encrypted_content}`` added shape, and the capture of the
ciphertext on replay candidates so the post-accounting v3 ciphertext alias
can bind the ciphertext itself instead of a fabricated protocol ID.  Legacy
profiles keep their single ID reference: their candidates carry
``encrypted_content=None``.
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


def _visible_idless_reasoning_done(seq: int = 1) -> dict:
    item: dict = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "visible"}],
    }
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


def test_idless_encrypted_reasoning_done_rejected_even_when_flag_on() -> None:
    """Provider output requires real IDs; the SDK drops them request-side only."""
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_idless_reasoning_done()) is False
    assert validator.take_replay_reference_candidates() == ()


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


def test_idbearing_reasoning_candidate_carries_cipher() -> None:
    """An ID-bearing validated done keeps the ciphertext for the v3 alias."""
    validator = ResponsesStreamEventValidator(_profile())
    payload = _idless_reasoning_done()
    payload["item"] = copy.deepcopy(payload["item"])
    payload["item"]["id"] = "rs_1"
    assert validator.validate(payload) is True
    (candidate,) = validator.take_replay_reference_candidates()
    assert candidate.item_kind == "reasoning"
    assert candidate.item_id == "rs_1"
    assert candidate.encrypted_content == CIPHER


def test_distinct_idless_ciphers_are_rejected_without_ids() -> None:
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_idless_reasoning_done(seq=1)) is False
    assert (
        validator.validate(
            _idless_reasoning_done(seq=2, item_overrides={"encrypted_content": CIPHER_B})
        )
        is False
    )
    assert validator.take_replay_reference_candidates() == ()


def test_idbearing_reasoning_candidate_cipher_gated_by_profile_flag() -> None:
    """Legacy encrypted-replay profiles keep cipher-free single references."""
    validator = ResponsesStreamEventValidator(
        _profile(allow_idless_encrypted_reasoning=False)
    )
    payload = _idless_reasoning_done()
    payload["item"]["id"] = "rs_1"
    assert validator.validate(payload) is True
    (candidate,) = validator.take_replay_reference_candidates()
    assert candidate.item_kind == "reasoning"
    assert candidate.item_id == "rs_1"
    assert candidate.encrypted_content is None


def _visible_reasoning_item(
    event_type: str,
    item_id: str,
    seq: int,
    *,
    item_overrides: dict | None = None,
    drop_fields: tuple[str, ...] = (),
) -> dict:
    item: dict = {
        "type": "reasoning",
        "id": item_id,
        "summary": [{"type": "summary_text", "text": "visible"}],
    }
    if item_overrides is not None:
        item.update(item_overrides)
    for field in drop_fields:
        item.pop(field)
    return {
        "type": f"response.output_item.{event_type}",
        "output_index": 0,
        "sequence_number": seq,
        "item": item,
    }


def _visible_profile(**overrides) -> ResponsesStreamValidationProfile:
    base = {
        "allow_sparse_visible_reasoning": True,
        "allow_empty_visible_reasoning": True,
    }
    base.update(overrides)
    return _profile(**base)


def test_selected_profile_visible_reasoning_lifecycle_omits_content_key() -> None:
    """Captured native lifecycle: added without summary, done with summary."""
    validator = ResponsesStreamEventValidator(_visible_profile())
    assert (
        validator.validate(
            _visible_reasoning_item("added", "vs_1", seq=0, drop_fields=("summary",))
        )
        is True
    )
    assert validator.validate(_visible_reasoning_item("done", "vs_1", seq=1)) is True
    # A second item may carry the content key; both shapes stay bounded.
    assert (
        validator.validate(
            _visible_reasoning_item(
                "added", "vs_2", seq=2, item_overrides={"content": []}
            )
        )
        is True
    )
    assert (
        validator.validate(
            _visible_reasoning_item(
                "done",
                "vs_2",
                seq=3,
                item_overrides={
                    "content": [{"type": "reasoning_text", "text": "visible"}]
                },
            )
        )
        is True
    )
    # Visible states grant zero opaque authority: no candidates are captured.
    assert validator.take_replay_reference_candidates() == ()


def test_selected_profile_visible_reasoning_empty_cipher_states() -> None:
    """Absent/null/empty cipher on added and done stays a visible item."""
    for cipher_value in (None, ""):
        validator = ResponsesStreamEventValidator(_visible_profile())
        assert (
            validator.validate(
                _visible_reasoning_item(
                    "added",
                    "vs_e",
                    seq=0,
                    item_overrides={"encrypted_content": cipher_value},
                )
            )
            is True
        )
    # Done closure with an explicit empty cipher and empty summary.
    validator = ResponsesStreamEventValidator(_visible_profile())
    assert (
        validator.validate(_visible_reasoning_item("added", "vs_e", seq=0))
        is True
    )
    assert (
        validator.validate(
            _visible_reasoning_item(
                "done",
                "vs_e",
                seq=1,
                item_overrides={"summary": [], "encrypted_content": ""},
            )
        )
        is True
    )
    assert validator.take_replay_reference_candidates() == ()


def test_selected_profile_visible_reasoning_explicit_null_summary_rejected() -> None:
    validator = ResponsesStreamEventValidator(_visible_profile())
    assert (
        validator.validate(
            _visible_reasoning_item(
                "added", "vs_n", seq=0, item_overrides={"summary": None}
            )
        )
        is False
    )
    # Explicit null on the done of an active item is malformed, not an
    # omission: it stays denied while the item itself was addable.
    validator = ResponsesStreamEventValidator(_visible_profile())
    assert (
        validator.validate(_visible_reasoning_item("added", "vs_n1", seq=0))
        is True
    )
    assert (
        validator.validate(
            _visible_reasoning_item(
                "done", "vs_n1", seq=1, item_overrides={"summary": None}
            )
        )
        is False
    )
    assert validator.take_replay_reference_candidates() == ()


def test_legacy_visible_reasoning_keeps_content_key_required() -> None:
    """Legacy sparse-visible profiles stay byte-identical (content required)."""
    validator = ResponsesStreamEventValidator(
        _visible_profile(allow_empty_visible_reasoning=False)
    )
    assert (
        validator.validate(
            _visible_reasoning_item(
                "added", "vs_l", seq=0, item_overrides={"content": []}
            )
        )
        is True
    )
    # Legacy done requires the content key even when empty.
    assert (
        validator.validate(
            _visible_reasoning_item(
                "done", "vs_l", seq=1, item_overrides={"content": []}
            )
        )
        is True
    )
    validator = ResponsesStreamEventValidator(
        _visible_profile(allow_empty_visible_reasoning=False)
    )
    assert (
        validator.validate(
            _visible_reasoning_item(
                "added", "vs_l2", seq=0, drop_fields=("summary",)
            )
        )
        is False
    )
    validator = ResponsesStreamEventValidator(
        _visible_profile(allow_empty_visible_reasoning=False)
    )
    assert (
        validator.validate(
            _visible_reasoning_item("done", "vs_l2", seq=1, drop_fields=("summary",))
        )
        is False
    )


def test_visible_idless_reasoning_done_preserves_legacy_behavior() -> None:
    # Replay OFF: the visible idless {type, summary} shape was always legal;
    # it must still validate and capture no candidate.
    validator = ResponsesStreamEventValidator(
        _profile(codex_encrypted_reasoning_replay=False)
    )
    assert validator.validate(_visible_idless_reasoning_done()) is True
    assert validator.take_replay_reference_candidates() == ()

    # Replay ON: the strict encrypted-replay shape set does not include the
    # visible idless form, so it now fails closed.
    validator = ResponsesStreamEventValidator(_profile())
    assert validator.validate(_visible_idless_reasoning_done()) is False
    assert validator.take_replay_reference_candidates() == ()
