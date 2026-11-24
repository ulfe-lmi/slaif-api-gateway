"""Stream-level OpenCode selected-profile lifecycle and flat-function dispatch.

Covers the minimal OpenCode 1.19.3 streaming surface added on top of the
qualified id-less encrypted reasoning path:

- ``response.reasoning_summary_part.done`` is the non-strict summary-part
  closure event; its part text must equal the accumulated
  ``reasoning_summary_text.delta`` bytes, and it is rejected by the strict
  0.149 dialect and by profiles without the OpenCode tool-event surface.
- ``response.output_item.added`` reasoning items carry exactly
  ``{type, id, encrypted_content}`` (bounded id, non-empty bounded cipher)
  under the replay profile; cumulative cipher bytes stay bounded.
- ``_derive_pair_local_codex_top_level_profile`` dispatches the OpenCode
  profile from the validated top-level taxonomy plus ``stream is True``
  alone (no local-server context), while the 0.149 dialect stays
  context-gated.
- The request policy admits streaming top-level function tools only when the
  selected-profile flag is forwarded; custom-tool streaming is deliberately
  NOT relaxed by that flag.

Fake SSE validator-level evidence only; no provider, network, or database
access.
"""

from __future__ import annotations

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
    OPENCODE_1193_RESPONSES_POLICY_SPEC,
)
from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_gateway import (
    _derive_pair_local_codex_top_level_profile,
)
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy

CIPHER = "c" * 64
TAXONOMY = frozenset({("functions", "probe", "function")})

FUNCTION_TOOL = {
    "type": "function",
    "name": "probe",
    "description": "d",
    "parameters": {
        "type": "object",
        "properties": {"canary": {"type": "string"}},
        "required": ["canary"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _profile(**overrides) -> ResponsesStreamValidationProfile:
    base = {
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": True,
        "allow_idless_encrypted_reasoning": True,
        "require_output_indices": True,
    }
    base.update(overrides)
    return ResponsesStreamValidationProfile(**base)


def _validator(**overrides) -> ResponsesStreamEventValidator:
    return ResponsesStreamEventValidator(_profile(**overrides))


def _cipher_added(
    *,
    item_id: str = "rs_1",
    cipher: str | int | None = CIPHER,
    output_index: int = 0,
    seq: int = 0,
) -> dict:
    item: dict = {"type": "reasoning", "id": item_id, "encrypted_content": cipher}
    return {
        "type": "response.output_item.added",
        "output_index": output_index,
        "sequence_number": seq,
        "item": item,
    }


def _part_added(
    *,
    seq: int = 1,
    summary_index: int = 0,
    item_id: str = "rs_1",
    output_index: int = 0,
    text: str = "",
) -> dict:
    return {
        "type": "response.reasoning_summary_part.added",
        "item_id": item_id,
        "output_index": output_index,
        "sequence_number": seq,
        "summary_index": summary_index,
        "part": {"type": "summary_text", "text": text},
    }


def _delta(
    *,
    seq: int = 2,
    summary_index: int = 0,
    item_id: str = "rs_1",
    output_index: int = 0,
    text: str = "part",
) -> dict:
    return {
        "type": "response.reasoning_summary_text.delta",
        "item_id": item_id,
        "output_index": output_index,
        "sequence_number": seq,
        "summary_index": summary_index,
        "delta": text,
    }


def _part_done(
    *,
    seq: int = 3,
    summary_index: int = 0,
    item_id: str = "rs_1",
    output_index: int = 0,
    text: str = "part",
    part_overrides: dict | None = None,
    drop_fields: tuple[str, ...] = (),
) -> dict:
    part: dict = {"type": "summary_text", "text": text}
    if part_overrides is not None:
        part.update(part_overrides)
    payload: dict = {
        "type": "response.reasoning_summary_part.done",
        "item_id": item_id,
        "output_index": output_index,
        "sequence_number": seq,
        "summary_index": summary_index,
        "part": part,
    }
    for field in drop_fields:
        payload.pop(field)
    return payload


def _id_done(
    *,
    seq: int = 4,
    item_id: str = "rs_1",
    output_index: int = 0,
) -> dict:
    return {
        "type": "response.output_item.done",
        "output_index": output_index,
        "sequence_number": seq,
        "item": {
            "type": "reasoning",
            "id": item_id,
            "summary": [{"type": "summary_text", "text": "part"}],
            "encrypted_content": CIPHER,
        },
    }


def _run(validator: ResponsesStreamEventValidator, *events: dict) -> None:
    for event in events:
        assert validator.validate(event) is True, event.get("type")


# --- response.reasoning_summary_part.done (non-strict closure) -------------


def test_part_done_matches_accumulated_deltas_and_captures_candidate() -> None:
    validator = _validator()
    _run(
        validator,
        _cipher_added(),
        _part_added(),
        _delta(),
        _part_done(),
        _id_done(),
    )
    (candidate,) = validator.take_replay_reference_candidates()
    assert candidate.item_kind == "reasoning"
    assert candidate.item_id == "rs_1"
    assert candidate.encrypted_content == CIPHER


def test_part_done_mismatched_text_rejected() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added(), _delta())
    assert validator.validate(_part_done(text="other")) is False


def test_part_done_missing_summary_index_rejected() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added(), _delta())
    assert validator.validate(_part_done(drop_fields=("summary_index",))) is False


def test_part_done_missing_output_index_rejected() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added(), _delta())
    assert validator.validate(_part_done(drop_fields=("output_index",))) is False


def test_part_done_wrong_part_type_rejected() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added(), _delta())
    assert (
        validator.validate(_part_done(part_overrides={"type": "reasoning_text"}))
        is False
    )


def test_part_done_extra_part_field_rejected() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added(), _delta())
    assert validator.validate(_part_done(part_overrides={"annotations": []})) is False


def test_part_done_extra_payload_field_rejected() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added(), _delta())
    payload = _part_done()
    payload["text"] = "part"
    assert validator.validate(payload) is False


def test_part_done_without_active_item_rejected() -> None:
    validator = _validator()
    assert validator.validate(_part_added()) is False


def test_part_done_zero_delta_closure_accepted() -> None:
    validator = _validator()
    _run(validator, _cipher_added(), _part_added())
    assert validator.validate(_part_done(text="")) is True


def test_strict_0149_dialect_rejects_summary_part_done() -> None:
    strict = ResponsesStreamValidationProfile(codex_reasoning_events=True)
    validator = ResponsesStreamEventValidator(strict)
    added = {
        "type": "response.output_item.added",
        "output_index": 0,
        "sequence_number": 0,
        "item": {
            "type": "reasoning",
            "id": "reasoning_1",
            "summary": [],
            "content": None,
            "encrypted_content": None,
            "status": "in_progress",
        },
    }
    assert validator.validate(added) is True
    assert validator.validate(_part_done()) is False


def test_plain_profile_rejects_summary_part_done() -> None:
    validator = ResponsesStreamEventValidator(ResponsesStreamValidationProfile())
    assert validator.validate(_part_added()) is False


# --- id-bearing exact-shape cipher added items -----------------------------


def test_exact_id_bearing_cipher_added_accepted() -> None:
    assert _validator().validate(_cipher_added()) is True


def test_cipher_added_with_summary_rejected() -> None:
    validator = _validator()
    payload = _cipher_added()
    payload["item"]["summary"] = []
    assert validator.validate(payload) is False


def test_cipher_added_with_status_rejected() -> None:
    validator = _validator()
    payload = _cipher_added()
    payload["item"]["status"] = "in_progress"
    assert validator.validate(payload) is False


@pytest.mark.parametrize("item_id", ["rs 1", None])
def test_cipher_added_invalid_identifier_rejected(item_id: object) -> None:
    assert _validator().validate(_cipher_added(item_id=item_id)) is False


@pytest.mark.parametrize("cipher", ["", 123, None])
def test_cipher_added_missing_or_non_string_cipher_rejected(cipher: object) -> None:
    assert _validator().validate(_cipher_added(cipher=cipher)) is False


def test_cipher_added_over_byte_cap_rejected() -> None:
    assert _validator().validate(_cipher_added(cipher="e" * 262_145)) is False


def test_cipher_added_without_allow_idless_rejected() -> None:
    validator = _validator(allow_idless_encrypted_reasoning=False)
    assert validator.validate(_cipher_added()) is False


def test_cipher_added_without_replay_flag_rejected() -> None:
    validator = _validator(codex_encrypted_reasoning_replay=False)
    assert validator.validate(_cipher_added()) is False


def test_cumulative_cipher_byte_cap_enforced() -> None:
    validator = _validator()
    for index in range(4):
        assert (
            validator.validate(
                _cipher_added(
                    item_id=f"rs_{index + 1}",
                    cipher="e" * 262_144,
                    output_index=index,
                )
            )
            is True
        )
    assert (
        validator.validate(
            _cipher_added(item_id="rs_5", cipher="e" * 262_144, output_index=4)
        )
        is False
    )


# --- orphan done rejection under required indexes --------------------------


def _function_item(
    item_type: str,
    *,
    item_id: str = "fc_1",
    call_id: str = "call_1",
) -> dict:
    return {
        "type": "function_call",
        "id": item_id,
        "name": "probe",
        "arguments": "{}",
        "call_id": call_id,
    }


def _function_event(
    event_type: str,
    *,
    seq: int = 0,
    item_id: str = "fc_1",
    call_id: str = "call_1",
    output_index: int = 0,
) -> dict:
    return {
        "type": f"response.output_item.{event_type}",
        "output_index": output_index,
        "sequence_number": seq,
        "item": _function_item(item_id, item_id=item_id, call_id=call_id),
    }


def test_orphan_function_call_done_rejected() -> None:
    """A done without a preceding added is an orphan and fails closed."""
    validator = _validator(declared_client_tools=TAXONOMY)
    assert validator.validate(_function_event("done")) is False
    assert validator.take_replay_reference_candidates() == ()


def test_orphan_encrypted_reasoning_done_rejected() -> None:
    validator = _validator()
    assert validator.validate(_id_done()) is False
    assert validator.take_replay_reference_candidates() == ()


def test_added_done_lifecycle_function_call_accepted() -> None:
    """Normal lifecycle: added registers the index, done reuses it."""
    validator = _validator(declared_client_tools=TAXONOMY)
    _run(validator, _function_event("added", seq=0), _function_event("done", seq=1))
    (candidate,) = validator.take_replay_reference_candidates()
    assert candidate.item_kind == "function_call"
    assert candidate.item_id == "fc_1"
    assert candidate.call_id == "call_1"
    assert candidate.encrypted_content is None
    # A second done for the same item is rejected (seen-ID guard).
    assert validator.validate(_function_event("done", seq=2)) is False


def test_done_reuses_added_index_or_rejected() -> None:
    validator = _validator(declared_client_tools=TAXONOMY)
    _run(validator, _function_event("added", seq=0))
    assert validator.validate(_function_event("done", seq=1, output_index=1)) is False


def test_done_at_index_used_by_other_item_rejected() -> None:
    validator = _validator(declared_client_tools=TAXONOMY)
    _run(validator, _cipher_added(item_id="rs_1", output_index=0))
    assert (
        validator.validate(
            _function_event("done", item_id="fc_1", output_index=0)
        )
        is False
    )
    assert validator.take_replay_reference_candidates() == ()


# --- visible reasoning lifecycle on the selected native profile ------------


def _visible_validator(**overrides) -> ResponsesStreamEventValidator:
    base = {
        "allow_sparse_visible_reasoning": True,
        "allow_empty_visible_reasoning": True,
    }
    base.update(overrides)
    return _validator(**base)


def _visible_event(
    event_type: str,
    *,
    seq: int = 0,
    item_id: str = "vs_1",
    output_index: int = 0,
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
        "output_index": output_index,
        "sequence_number": seq,
        "item": item,
    }


def test_visible_reasoning_lifecycle_selected_profile_no_opaque_authority() -> None:
    validator = _visible_validator()
    _run(
        validator,
        _visible_event("added", seq=0, drop_fields=("summary",)),
        _visible_event("done", seq=1),
    )
    # Empty cipher states on the done closure stay visible.
    assert (
        validator.validate(
            _visible_event(
                "added",
                seq=2,
                item_id="vs_2",
                output_index=1,
                item_overrides={"encrypted_content": ""},
            )
        )
        is True
    )
    assert (
        validator.validate(
            _visible_event(
                "done",
                seq=3,
                item_id="vs_2",
                output_index=1,
                item_overrides={"summary": [], "encrypted_content": ""},
            )
        )
        is True
    )
    # Visible states capture no candidate: zero opaque-cipher authority.
    assert validator.take_replay_reference_candidates() == ()


def test_visible_reasoning_explicit_null_summary_rejected_selected_profile() -> None:
    validator = _visible_validator()
    assert (
        validator.validate(
            _visible_event(
                "added", seq=0, item_overrides={"summary": None}
            )
        )
        is False
    )
    validator = _visible_validator()
    _run(validator, _visible_event("added", seq=0))
    assert (
        validator.validate(
            _visible_event("done", seq=1, item_overrides={"summary": None})
        )
        is False
    )


def test_visible_reasoning_legacy_profile_keeps_content_key() -> None:
    """Legacy sparse-visible (local context) stays byte-identical."""
    legacy = _visible_validator(allow_empty_visible_reasoning=False)
    assert (
        legacy.validate(
            _visible_event("added", seq=0, item_overrides={"content": []})
        )
        is True
    )
    assert (
        legacy.validate(
            _visible_event("done", seq=1, item_overrides={"content": []})
        )
        is True
    )
    legacy = _visible_validator(allow_empty_visible_reasoning=False)
    # Legacy added requires the summary key; omission is not qualified.
    assert (
        legacy.validate(_visible_event("added", seq=0, drop_fields=("summary",)))
        is False
    )
    legacy = _visible_validator(allow_empty_visible_reasoning=False)
    # Legacy done requires the content key even when empty.
    assert legacy.validate(_visible_event("done", seq=1)) is False
# --- pair-local top-level profile dispatch ---------------------------------


def test_derive_opencode_selected_profile() -> None:
    body = {"stream": True, "input": "hi"}
    kwargs = dict(
        client_module_id=OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
        local_coding_server_context=None,
        effective_body=body,
    )
    assert _derive_pair_local_codex_top_level_profile(
        declared_tool_taxonomy=TAXONOMY, **kwargs
    ) == (TAXONOMY, True)
    assert _derive_pair_local_codex_top_level_profile(**kwargs) == (frozenset(), False)
    assert _derive_pair_local_codex_top_level_profile(
        declared_tool_taxonomy=TAXONOMY,
        client_module_id=OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
        local_coding_server_context=None,
        effective_body={"stream": False, "input": "hi"},
    ) == (frozenset(), False)
    assert _derive_pair_local_codex_top_level_profile(
        declared_tool_taxonomy=TAXONOMY,
        client_module_id=OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
        local_coding_server_context={"host": "x"},
        effective_body=body,
    ) == (TAXONOMY, True)


def test_derive_0149_requires_local_server_context() -> None:
    body = {"stream": True, "tools": [{"type": "function", "name": "exec"}]}
    assert _derive_pair_local_codex_top_level_profile(
        client_module_id=CODEX_0149_CLIENT_MODULE_ID,
        local_coding_server_context={"host": "x"},
        effective_body=body,
        declared_tool_taxonomy=TAXONOMY,
    ) == (TAXONOMY, True)
    assert _derive_pair_local_codex_top_level_profile(
        client_module_id=CODEX_0149_CLIENT_MODULE_ID,
        local_coding_server_context=None,
        effective_body=body,
        declared_tool_taxonomy=TAXONOMY,
    ) == (frozenset(), False)


def test_derive_unknown_module_never_selected() -> None:
    body = {"stream": True, "input": "hi"}
    assert _derive_pair_local_codex_top_level_profile(
        client_module_id="other",
        local_coding_server_context={"host": "x"},
        effective_body=body,
        declared_tool_taxonomy=TAXONOMY,
    ) == (frozenset(), False)


# --- request policy flat-function streaming flag ---------------------------


def _policy() -> ResponsesRequestPolicy:
    return ResponsesRequestPolicy(
        Settings(), client_spec=OPENCODE_1193_RESPONSES_POLICY_SPEC
    )


def _wire_body(*, stream: bool, tools: list[dict]) -> dict:
    return {
        "model": "synthetic-opencode-model",
        "input": "hello",
        "stream": stream,
        "store": False,
        "tool_choice": "auto",
        "max_output_tokens": 32_000,
        "tools": tools,
    }


def test_policy_admits_flat_function_streaming_with_selected_profile_flag() -> None:
    policy = _policy()
    result = policy.apply(
        _wire_body(stream=True, tools=[FUNCTION_TOOL]),
        selected_profile_flat_function_streaming=True,
    )
    assert result.effective_body["stream"] is True


def test_policy_denies_flat_function_streaming_without_flag() -> None:
    policy = _policy()
    with pytest.raises(RequestPolicyError) as exc:
        policy.apply(_wire_body(stream=True, tools=[FUNCTION_TOOL]))
    assert exc.value.error_code == "responses_function_tool_streaming_not_supported"
    assert exc.value.param == "tools"


def test_policy_flag_does_not_relax_custom_tool_streaming() -> None:
    policy = _policy()
    with pytest.raises(RequestPolicyError) as exc:
        policy.apply(
            _wire_body(
                stream=True,
                tools=[{"type": "custom", "name": "exec", "description": "e"}],
            ),
            selected_profile_flat_function_streaming=True,
        )
    assert exc.value.error_code == "responses_custom_tool_streaming_not_supported"


def test_policy_non_streaming_function_tools_need_no_flag() -> None:
    policy = _policy()
    result = policy.apply(_wire_body(stream=False, tools=[FUNCTION_TOOL]))
    assert result.effective_body["stream"] is False
