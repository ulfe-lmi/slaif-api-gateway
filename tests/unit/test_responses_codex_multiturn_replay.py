from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.services.codex_replay_service import (
    AuthorizedCodexReplayReference,
    CodexReplayAuthorization,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.input_token_estimation import canonical_json_bytes
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    codex_replay_request_candidates,
)


_INTERNAL_CHAT_METADATA_FIELD = "internal_chat_message_metadata_passthrough"
_PRIVATE_METADATA_CANARY = "PRIVATE-REPLAY-METADATA-CANARY"


def _function(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "parameters": {"type": "object", "properties": {}},
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


def _body(input_items: list[object]) -> dict[str, object]:
    return {
        "model": "classroom-codex",
        "input": input_items,
        "stream": True,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "max_output_tokens": 32,
    }


def _reasoning(
    *,
    encrypted: str = "opaque-ciphertext",
    item_id: str = "rs_1",
) -> dict[str, object]:
    return {
        "type": "reasoning",
        "id": item_id,
        "summary": [{"type": "summary_text", "text": "safe summary"}],
        "encrypted_content": encrypted,
    }


def _apply_reasoning(body: dict[str, object]):
    return ResponsesRequestPolicy(Settings()).apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_encrypted_reasoning_replay=True,
    )


def _apply_tools(body: dict[str, object]):
    return ResponsesRequestPolicy(Settings()).apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
        allow_codex_encrypted_reasoning_replay=True,
    )


def _apply_fully_gated(body: dict[str, object]):
    return ResponsesRequestPolicy(Settings()).apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
        allow_codex_encrypted_reasoning_replay=True,
        allow_codex_compaction_replay=True,
    )


def test_encrypted_reasoning_replay_is_canonical_metered_and_id_only_for_lookup() -> None:
    body = _body(
        [
            _reasoning(),
            {"type": "message", "role": "user", "content": "next turn"},
        ]
    )
    original = copy.deepcopy(body)

    result = _apply_reasoning(body)
    candidates = codex_replay_request_candidates(result.effective_body)

    assert result.effective_body == original
    assert result.estimated_input_tokens > len("opaque-ciphertext") // 3
    assert len(candidates) == 1
    assert candidates[0].item_kind == "reasoning"
    assert candidates[0].item_id == "rs_1"
    assert not hasattr(candidates[0], "encrypted_content")
    assert not hasattr(candidates[0], "summary")


def test_dropped_internal_chat_metadata_never_enters_replay_or_hmac_candidates() -> None:
    body = _body(
        [
            {
                **_reasoning(),
                _INTERNAL_CHAT_METADATA_FIELD: {
                    "turn_id": "private-turn",
                    "executed_tool_calls": [
                        {
                            "name": "exec",
                            "arguments": {"private": _PRIVATE_METADATA_CANARY},
                        }
                    ],
                },
            },
            {
                "type": "message",
                "role": "user",
                "content": "next turn",
                _INTERNAL_CHAT_METADATA_FIELD: None,
            },
        ]
    )
    original = copy.deepcopy(body)
    clean_body = copy.deepcopy(body)
    clean_items = clean_body["input"]
    assert isinstance(clean_items, list)
    for item in clean_items:
        assert isinstance(item, dict)
        item.pop(_INTERNAL_CHAT_METADATA_FIELD)

    result = _apply_fully_gated(body)
    clean_result = _apply_fully_gated(clean_body)
    candidates = codex_replay_request_candidates(result.effective_body)
    clean_candidates = codex_replay_request_candidates(clean_result.effective_body)

    assert body == original
    assert result.effective_body == clean_result.effective_body
    assert result.estimated_input_tokens == clean_result.estimated_input_tokens
    assert result.estimated_non_message_input_bytes == clean_result.estimated_non_message_input_bytes
    assert result.estimated_non_message_input_fields == clean_result.estimated_non_message_input_fields
    assert candidates == clean_candidates
    assert len(candidates) == 1
    assert candidates[0].item_id == "rs_1"
    assert not hasattr(candidates[0], _INTERNAL_CHAT_METADATA_FIELD)
    safe_evidence = repr(
        (
            result.estimated_input_tokens,
            result.estimated_non_message_input_bytes,
            result.estimated_non_message_input_fields,
            candidates,
        )
    )
    assert _PRIVATE_METADATA_CANARY not in safe_evidence


def test_pinned_reasoning_replay_accepts_only_exact_null_content() -> None:
    item = _reasoning()
    item["content"] = None
    result = _apply_reasoning(_body([item]))
    assert result.effective_body["input"][0]["content"] is None

    item["content"] = [{"type": "reasoning_text", "text": "private"}]
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_reasoning(_body([item]))
    assert exc_info.value.error_code == "responses_codex_encrypted_reasoning_replay_invalid"
    assert "private" not in exc_info.value.safe_message


def test_encrypted_reasoning_requires_independent_key_gate() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body([_reasoning()]),
            allow_codex_request_envelope=True,
        )
    assert exc_info.value.error_code == "responses_codex_encrypted_reasoning_replay_not_allowed"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda item: item.update(content=[{"type": "reasoning_text", "text": "private"}]),
            "responses_codex_encrypted_reasoning_replay_invalid",
        ),
        (
            lambda item: item.update(status="completed"),
            "responses_codex_encrypted_reasoning_replay_invalid",
        ),
        (
            lambda item: item.update(unknown="authority"),
            "responses_codex_encrypted_reasoning_replay_invalid",
        ),
        (
            lambda item: item.update(encrypted_content=""),
            "responses_codex_encrypted_reasoning_replay_invalid",
        ),
        (
            lambda item: item.update(encrypted_content="x" * 262_145),
            "responses_codex_encrypted_reasoning_replay_too_large",
        ),
        (
            lambda item: item.update(summary=[{"type": "reasoning_text", "text": "private"}]),
            "responses_codex_encrypted_reasoning_replay_invalid",
        ),
    ],
)
def test_reasoning_plaintext_unknown_malformed_and_oversized_shapes_fail_closed(
    mutation,
    code: str,
) -> None:
    item = _reasoning()
    mutation(item)
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_reasoning(_body([item]))
    assert exc_info.value.error_code == code
    assert "private" not in exc_info.value.safe_message
    assert "authority" not in exc_info.value.safe_message


def test_duplicate_reasoning_and_provider_state_combinations_are_rejected() -> None:
    duplicate = _reasoning()
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_reasoning(_body([_reasoning(), duplicate]))
    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_invalid"

    for field in ("previous_response_id", "conversation"):
        body = _body([_reasoning()])
        body[field] = "state_1"
        with pytest.raises(RequestPolicyError) as state_exc:
            _apply_reasoning(body)
        assert state_exc.value.error_code == "responses_codex_replay_provider_state_not_supported"


def test_encrypted_reasoning_request_cumulative_cap_is_exact() -> None:
    policy = ResponsesRequestPolicy(
        Settings(
            RESPONSES_MAX_INPUT_TEXT_BYTES=2_000_000,
            RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES=2_000_000,
            HARD_MAX_INPUT_TOKENS=1_000_000,
        )
    )

    def apply(body: dict[str, object]):
        return policy.apply(
            body,
            allow_codex_request_envelope=True,
            allow_codex_encrypted_reasoning_replay=True,
        )

    at_limit = [
        _reasoning(item_id=f"rs_{index}", encrypted="x" * 262_144)
        for index in range(4)
    ]
    assert len(apply(_body(at_limit)).effective_body["input"]) == 4

    over_limit = [*at_limit, _reasoning(item_id="rs_over", encrypted="x")]
    with pytest.raises(RequestPolicyError) as exc_info:
        apply(_body(over_limit))
    assert exc_info.value.error_code == "responses_codex_encrypted_reasoning_replay_too_large"


def test_tool_replay_requires_exact_adjacent_pair_and_exposes_only_linkage_ids() -> None:
    call = {
        "type": "custom_tool_call",
        "id": "ctc_1",
        "namespace": "functions",
        "name": "exec",
        "call_id": "call_1",
        "input": 'text("SAFE")',
        "status": "completed",
    }
    output = {
        "type": "custom_tool_call_output",
        "call_id": "call_1",
        "output": [{"type": "input_text", "text": "SAFE_RESULT"}],
    }
    body = _body([_additional_tools(), call, output])
    result = _apply_tools(body)
    candidates = codex_replay_request_candidates(result.effective_body)
    assert len(candidates) == 1
    assert candidates[0].item_id == "ctc_1"
    assert candidates[0].call_id == "call_1"
    assert candidates[0].tool_namespace == "functions"
    assert candidates[0].tool_name == "exec"
    assert not hasattr(candidates[0], "input")
    assert not hasattr(candidates[0], "output")

    reordered = _body(
        [
            _additional_tools(),
            call,
            {"type": "message", "role": "user", "content": "gap"},
            {**output, "id": "ctco_reordered"},
        ]
    )
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_tools(reordered)
    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_invalid"


def test_output_item_id_bytes_are_canonical_metered_and_not_hmac_authority() -> None:
    output_id = "ctco_" + "a" * 36
    assert len(output_id) == len(output_id.encode("ascii")) == 41
    call = {
        "type": "custom_tool_call",
        "id": "ctc_1",
        "namespace": "functions",
        "name": "exec",
        "call_id": "call_1",
        "input": "bounded",
    }
    output = {
        "type": "custom_tool_call_output",
        "id": output_id,
        "call_id": "call_1",
        "output": "bounded result",
    }
    with_id_body = _body([_additional_tools(), call, output])
    without_id_body = copy.deepcopy(with_id_body)
    without_id_items = without_id_body["input"]
    assert isinstance(without_id_items, list)
    assert isinstance(without_id_items[2], dict)
    without_id_items[2].pop("id")

    with_id = _apply_tools(with_id_body)
    without_id = _apply_tools(without_id_body)
    with_output = with_id.effective_body["input"][2]
    without_output = without_id.effective_body["input"][2]
    canonical_delta = len(canonical_json_bytes(with_output)) - len(
        canonical_json_bytes(without_output)
    )
    id_field_bytes = len(canonical_json_bytes({"id": output_id}))
    policy = ResponsesRequestPolicy(Settings())
    _, with_material_bytes = policy._validate_input(
        with_id.effective_body["input"],
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
        allow_codex_encrypted_reasoning_replay=True,
    )
    _, without_material_bytes = policy._validate_input(
        without_id.effective_body["input"],
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
        allow_codex_encrypted_reasoning_replay=True,
    )

    assert with_material_bytes - without_material_bytes == canonical_delta
    assert (
        with_id.estimated_non_message_input_bytes
        - without_id.estimated_non_message_input_bytes
        == id_field_bytes
    )
    assert with_id.estimated_input_tokens == max(
        1,
        (
            with_material_bytes
            + with_id.estimated_non_message_input_bytes
            + 2
        )
        // 3,
    )
    assert without_id.estimated_input_tokens == max(
        1,
        (
            without_material_bytes
            + without_id.estimated_non_message_input_bytes
            + 2
        )
        // 3,
    )
    with_candidates = codex_replay_request_candidates(with_id.effective_body)
    without_candidates = codex_replay_request_candidates(without_id.effective_body)
    assert with_candidates == without_candidates
    assert len(with_candidates) == 1
    assert with_candidates[0].item_id == "ctc_1"
    safe_evidence = repr(
        (
            with_id.estimated_input_tokens,
            with_id.estimated_non_message_input_tokens,
            with_id.estimated_non_message_input_bytes,
            with_id.estimated_non_message_input_fields,
            with_candidates,
        )
    )
    assert output_id not in safe_evidence


@pytest.mark.parametrize("collision_kind", ["call", "reasoning", "message"])
def test_output_item_ids_are_unique_across_all_codex_history(collision_kind: str) -> None:
    shared_id = "item_shared"
    items: list[object] = [_additional_tools()]
    if collision_kind == "reasoning":
        items.append(_reasoning(item_id=shared_id))
    elif collision_kind == "message":
        items.append(
            {"type": "message", "id": shared_id, "role": "user", "content": "bounded"}
        )
    call_id = shared_id if collision_kind == "call" else "ctc_unique"
    items.extend(
        [
            {
                "type": "custom_tool_call",
                "id": call_id,
                "namespace": "functions",
                "name": "exec",
                "call_id": "call_1",
                "input": "bounded",
            },
            {
                "type": "custom_tool_call_output",
                "id": shared_id,
                "call_id": "call_1",
                "output": "bounded result",
            },
        ]
    )
    output_index = len(items) - 1

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_tools(_body(items))

    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_invalid"
    assert exc_info.value.param == f"input[{output_index}].id"


def test_duplicate_output_item_ids_are_rejected_request_wide() -> None:
    duplicate_id = "output_shared"
    items = [
        _additional_tools(),
        {
            "type": "custom_tool_call",
            "id": "ctc_1",
            "namespace": "functions",
            "name": "exec",
            "call_id": "call_1",
            "input": "bounded",
        },
        {
            "type": "custom_tool_call_output",
            "id": duplicate_id,
            "call_id": "call_1",
            "output": "bounded result",
        },
        {
            "type": "function_call",
            "id": "fc_1",
            "namespace": "functions",
            "name": "wait",
            "call_id": "call_2",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "id": duplicate_id,
            "call_id": "call_2",
            "output": "bounded result",
        },
    ]

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_tools(_body(items))

    assert exc_info.value.error_code == "responses_codex_tool_roundtrip_invalid"
    assert exc_info.value.param == "input[4].id"


@pytest.mark.parametrize(
    ("output_type", "expected_code"),
    [
        ("function_call_output", "responses_function_call_output_invalid"),
        ("custom_tool_call_output", "responses_custom_tool_call_output_invalid"),
    ],
)
def test_ordinary_non_codex_outputs_continue_to_reject_id(
    output_type: str,
    expected_code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            {
                "model": "classroom",
                "input": [
                    {
                        "type": output_type,
                        "id": "output_ordinary",
                        "call_id": "call_1",
                        "output": "ok",
                    },
                    {"type": "message", "role": "user", "content": "continue"},
                ],
                "stream": False,
                "max_output_tokens": 16,
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == "input[0].id"


def test_ordinary_non_codex_function_output_remains_separate() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        {
            "model": "classroom",
            "input": [
                {"type": "function_call_output", "call_id": "call_1", "output": "ok"},
                {"type": "message", "role": "user", "content": "continue"},
            ],
            "stream": False,
            "max_output_tokens": 16,
        }
    )
    assert result.effective_body["input"][0]["type"] == "function_call_output"
    assert codex_replay_request_candidates(result.effective_body) == ()


def _replay_key() -> SimpleNamespace:
    return SimpleNamespace(
        gateway_key_id=uuid.uuid4(),
        responses_policy={
            "version": 1,
            "allowed_capabilities": [
                "codex_request_envelope",
                "codex_encrypted_reasoning_replay",
            ],
        },
    )


def test_same_key_ownership_denial_precedes_route_and_all_later_side_effects(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    timeline: list[str] = []

    async def deny_ownership(**kwargs):
        timeline.append("ownership")
        raise OpenAICompatibleError(
            "Replay unavailable.",
            status_code=404,
            error_type="invalid_request_error",
            code="responses_codex_replay_reference_not_found",
        )

    async def unexpected_route(**kwargs):
        timeline.append("route")
        raise AssertionError("route must not run")

    monkeypatch.setattr(gateway, "_verify_owned_codex_replay_references", deny_ownership)
    monkeypatch.setattr(gateway, "_resolve_responses_route", unexpected_route)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_body([_reasoning()])),
                authenticated_key=_replay_key(),
                settings=Settings(),
            )
        )
    assert exc_info.value.code == "responses_codex_replay_reference_not_found"
    assert timeline == ["ownership"]


def test_route_mismatch_denial_precedes_redis_pricing_quota_and_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    timeline: list[str] = []
    stored_route_id = uuid.uuid4()
    selected_route_id = uuid.uuid4()

    async def authorize(**kwargs):
        timeline.append("ownership")
        return CodexReplayAuthorization(
            references=(
                AuthorizedCodexReplayReference(
                    item_kind="reasoning",
                    provider="openai",
                    route_id=stored_route_id,
                    upstream_model="gpt-stored",
                    tool_namespace=None,
                    tool_name=None,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
            )
        )

    async def resolve(**kwargs):
        timeline.append("route")
        return SimpleNamespace(
            provider="openai",
            route_id=selected_route_id,
            resolved_model="gpt-selected",
        )

    async def unexpected_redis(**kwargs):
        timeline.append("redis")
        raise AssertionError("Redis must not run")

    monkeypatch.setattr(gateway, "_verify_owned_codex_replay_references", authorize)
    monkeypatch.setattr(gateway, "_resolve_responses_route", resolve)
    monkeypatch.setattr(gateway, "_reserve_redis_rate_limit", unexpected_redis)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_body([_reasoning()])),
                authenticated_key=_replay_key(),
                settings=Settings(),
            )
        )
    assert exc_info.value.code == "responses_codex_replay_route_mismatch"
    assert timeline == ["ownership", "route"]


def _harness_request(items: list[object]):
    from scripts.capture_codex_protocol import ParsedHttpRequest

    return ParsedHttpRequest(
        method="POST",
        target="/v1/responses",
        version="HTTP/1.1",
        headers=(),
        body=json.dumps({"input": items}).encode("utf-8"),
    )


def _harness_tool_pair(*, item_id: str, call_id: str, source: str, marker: str):
    return [
        {
            "type": "custom_tool_call",
            "id": item_id,
            "namespace": "functions",
            "name": "exec",
            "call_id": call_id,
            "input": source,
            "status": "completed",
        },
        {
            "type": "custom_tool_call_output",
            "call_id": call_id,
            "output": [{"type": "input_text", "text": marker}],
        },
    ]


def test_reasoning_replay_manual_harness_fixed_streams_are_pure_and_bounded() -> None:
    from scripts import verify_codex_reasoning_replay as harness

    assert harness.EXPECTED_REQUESTS == 3
    assert harness.SAFE_CODE_MODE_ONE == 'text("SAFE_REPLAY_ONE")'
    assert harness.SAFE_CODE_MODE_TWO == 'text("SAFE_REPLAY_TWO")'
    assert set(harness.REASONING_ITEM) == {
        "type",
        "id",
        "summary",
        "encrypted_content",
    }
    assert harness.REASONING_REPLAY_INPUT_ITEM["content"] is None
    for events in (
        harness.FIRST_RESPONSE_EVENTS,
        harness.SECOND_RESPONSE_EVENTS,
        harness.THIRD_RESPONSE_EVENTS,
    ):
        body = harness._sse_body(events)
        harness.validate_sse_body(body, events=events)
        assert len(body) < 32_000


def test_reasoning_replay_manual_harness_validates_only_exact_in_memory_history() -> None:
    from scripts import verify_codex_reasoning_replay as harness

    first_pair = _harness_tool_pair(
        item_id=harness.FIRST_TOOL_ITEM_ID,
        call_id=harness.FIRST_TOOL_CALL_ID,
        source=harness.SAFE_CODE_MODE_ONE,
        marker="SAFE_REPLAY_ONE",
    )
    second_pair = _harness_tool_pair(
        item_id=harness.SECOND_TOOL_ITEM_ID,
        call_id=harness.SECOND_TOOL_CALL_ID,
        source=harness.SAFE_CODE_MODE_TWO,
        marker="SAFE_REPLAY_TWO",
    )
    harness.validate_second_request(_harness_request(first_pair))
    harness.validate_third_request(
        _harness_request([*first_pair, harness.REASONING_REPLAY_INPUT_ITEM, *second_pair])
    )

    invalid = [*first_pair, dict(harness.REASONING_REPLAY_INPUT_ITEM), *second_pair]
    invalid[2]["content"] = [{"type": "reasoning_text", "text": "private"}]
    with pytest.raises(harness.VerificationError) as exc_info:
        harness.validate_third_request(_harness_request(invalid))
    assert "private" not in str(exc_info.value)
