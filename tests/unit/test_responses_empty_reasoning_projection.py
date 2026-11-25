"""228-c functional regressions: create-only empty visible-reasoning projection.

The selected OpenCode module emits the exact id-less empty reasoning
replay placeholder ``{"type": "reasoning", "summary": [],
"encrypted_content": ""}``; openai-compatible upstreams can reject that
canonical item.  For the CREATE request only, the gateway projects
(omits) ONLY that exact item from the forwarded body copy and meters the
projected history.  The input-token-count endpoint keeps denying visible
reasoning input (request-envelope capability not enabled on that path)
and the compact builder meters the full history bytes in both fact
variants.  Validation, resource accounting, ownership, and HMAC
authority always cover the complete history.
"""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_POLICY_SPEC,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_gateway import _project_empty_visible_reasoning
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    canonical_json_bytes,
    is_empty_visible_reasoning_placeholder,
)

PLACEHOLDER = {"type": "reasoning", "summary": [], "encrypted_content": ""}
PLACEHOLDER_BYTES = len(canonical_json_bytes(PLACEHOLDER))
assert PLACEHOLDER_BYTES == 56

TEXT = "x" * 200
TEXT_BYTES = len(TEXT.encode("utf-8"))
USER = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TEXT}]}
CIPHER = {"type": "reasoning", "summary": [], "encrypted_content": "abc123"}
CIPHER_BYTES = len(canonical_json_bytes(CIPHER))

# Native OpenCode pair gates: envelope, client tools, streaming tool
# events, encrypted reasoning replay all enabled for the selected profile.
APPLY_KW = dict(
    allow_codex_request_envelope=True,
    allow_codex_client_tools=True,
    allow_codex_streaming_tool_events=True,
    allow_codex_encrypted_reasoning_replay=True,
)


def _policy(omit_fact: bool) -> ResponsesRequestPolicy:
    spec = replace(
        OPENCODE_1193_RESPONSES_POLICY_SPEC, omit_empty_visible_reasoning=omit_fact
    )
    return ResponsesRequestPolicy(Settings(), client_spec=spec)


def _tokens(total_bytes: int) -> int:
    return max(1, (total_bytes + 2) // 3)


class TestPredicateTruthTable:
    @pytest.mark.parametrize(
        "item",
        [
            {"type": "reasoning", "summary": [], "encrypted_content": "abc"},
            {"type": "reasoning", "summary": [], "encrypted_content": None},
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "x"}],
                "encrypted_content": "",
            },
            {"type": "reasoning", "summary": [], "encrypted_content": "", "id": "rs_1"},
            {"type": "reasoning", "summary": [], "encrypted_content": "", "status": "completed"},
            {"type": "message", "summary": [], "encrypted_content": ""},
            {"type": "reasoning", "summary": [], "content": []},
            {"type": "reasoning", "encrypted_content": ""},
            {},
        ],
    )
    def test_non_placeholder_rejected(self, item):
        assert not is_empty_visible_reasoning_placeholder(item)

    def test_non_mapping_rejected(self):
        assert not is_empty_visible_reasoning_placeholder("nope")
        assert not is_empty_visible_reasoning_placeholder(None)

    def test_exact_placeholder_accepted(self):
        assert is_empty_visible_reasoning_placeholder(PLACEHOLDER)


class TestProjectionHelper:
    def test_removes_only_exact_placeholder(self):
        effective = {"model": "m", "input": [USER, PLACEHOLDER, dict(PLACEHOLDER)]}
        original = copy.deepcopy(effective)
        projected = _project_empty_visible_reasoning(effective)
        assert effective == original
        assert projected is not effective
        assert projected["input"] == [USER]
        assert projected["model"] == "m"

    def test_meaningful_cipher_preserved(self):
        effective = {"model": "m", "input": [USER, PLACEHOLDER, CIPHER]}
        projected = _project_empty_visible_reasoning(effective)
        assert projected["input"] == [USER, CIPHER]

    def test_noop_without_placeholder_same_object(self):
        effective = {"model": "m", "input": [USER, CIPHER]}
        assert _project_empty_visible_reasoning(effective) is effective

    def test_non_list_input_untouched(self):
        effective = {"model": "m", "input": PLACEHOLDER}
        assert _project_empty_visible_reasoning(effective) is effective


class TestCreateMetering:
    def test_fact_on_projects_placeholder_estimate(self):
        policy = _policy(omit_fact=True)
        with_ph = policy.apply({"model": "m", "input": [USER, PLACEHOLDER]}, **APPLY_KW)
        without_ph = policy.apply({"model": "m", "input": [USER]}, **APPLY_KW)
        # Exact pre-rounding deduction of the placeholder canonical bytes:
        # the projected create meters the same history as without it.
        assert with_ph.estimated_input_tokens == _tokens(TEXT_BYTES)
        assert with_ph.estimated_input_tokens == without_ph.estimated_input_tokens

    def test_fact_off_meters_full_history(self):
        policy = _policy(omit_fact=False)
        with_ph = policy.apply({"model": "m", "input": [USER, PLACEHOLDER]}, **APPLY_KW)
        without_ph = policy.apply({"model": "m", "input": [USER]}, **APPLY_KW)
        assert with_ph.estimated_input_tokens == _tokens(TEXT_BYTES + PLACEHOLDER_BYTES)
        assert with_ph.estimated_input_tokens > without_ph.estimated_input_tokens

    def test_fact_on_preserves_meaningful_cipher(self):
        policy = _policy(omit_fact=True)
        both = policy.apply({"model": "m", "input": [USER, PLACEHOLDER, CIPHER]}, **APPLY_KW)
        cipher_only = policy.apply({"model": "m", "input": [USER, CIPHER]}, **APPLY_KW)
        assert both.estimated_input_tokens == _tokens(TEXT_BYTES + CIPHER_BYTES)
        assert both.estimated_input_tokens == cipher_only.estimated_input_tokens

    def test_fact_off_meters_cipher_and_placeholder_full(self):
        policy = _policy(omit_fact=False)
        both = policy.apply({"model": "m", "input": [USER, PLACEHOLDER, CIPHER]}, **APPLY_KW)
        assert both.estimated_input_tokens == _tokens(
            TEXT_BYTES + PLACEHOLDER_BYTES + CIPHER_BYTES
        )


class TestCreateCountEquivalence:
    def test_count_matches_plain_create(self):
        for omit_fact in (True, False):
            policy = _policy(omit_fact=omit_fact)
            create = policy.apply({"model": "m", "input": [USER]}, **APPLY_KW)
            count = policy.apply_input_token_count({"model": "m", "input": [USER]})
            assert count.estimated_input_tokens == create.estimated_input_tokens

    def test_projected_create_equals_count_of_projected_history(self):
        policy = _policy(omit_fact=True)
        create = policy.apply({"model": "m", "input": [USER, PLACEHOLDER]}, **APPLY_KW)
        count = policy.apply_input_token_count({"model": "m", "input": [USER]})
        assert create.estimated_input_tokens == count.estimated_input_tokens


class TestInputCountDenialPreserved:
    def test_count_denies_visible_reasoning_placeholder(self):
        for omit_fact in (True, False):
            policy = _policy(omit_fact=omit_fact)
            with pytest.raises(
                RequestPolicyError, match="request-envelope capability"
            ):
                policy.apply_input_token_count(
                    {"model": "m", "input": [USER, PLACEHOLDER]}
                )

    def test_count_denies_encrypted_reasoning_replay(self):
        policy = _policy(omit_fact=True)
        with pytest.raises(RequestPolicyError, match="request-envelope capability"):
            policy.apply_input_token_count({"model": "m", "input": [USER, CIPHER]})


class TestCompactFullEstimate:
    def test_fact_on_and_fact_off_keep_same_full_estimate(self):
        on = _policy(omit_fact=True).apply_compact(
            {"model": "m", "input": [USER, PLACEHOLDER]}, allow_codex_compaction=True
        )
        off = _policy(omit_fact=False).apply_compact(
            {"model": "m", "input": [USER, PLACEHOLDER]}, allow_codex_compaction=True
        )
        full = _tokens(TEXT_BYTES + PLACEHOLDER_BYTES)
        assert on.estimated_input_tokens == full
        assert off.estimated_input_tokens == full

    def test_compact_matches_plain_create(self):
        policy = _policy(omit_fact=True)
        compact = policy.apply_compact(
            {"model": "m", "input": [USER]}, allow_codex_compaction=True
        )
        create = policy.apply({"model": "m", "input": [USER]}, **APPLY_KW)
        assert compact.estimated_input_tokens == create.estimated_input_tokens


class TestRejectionBeforeProjection:
    @pytest.mark.parametrize(
        "extra",
        [{"bogus": 1}, {"status": "completed"}],
    )
    def test_unknown_extra_field_rejected_before_any_projection(self, extra):
        item = {**PLACEHOLDER, **extra}
        assert not is_empty_visible_reasoning_placeholder(item)
        for omit_fact in (True, False):
            policy = _policy(omit_fact=omit_fact)
            with pytest.raises(RequestPolicyError, match="unsupported field"):
                policy.apply({"model": "m", "input": [item]}, **APPLY_KW)
