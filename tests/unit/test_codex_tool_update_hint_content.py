"""Real-client array-form tool metadata must compile like standalone strings."""

import copy

import pytest

from slaif_gateway.modules.clients.codex_0162 import (
    codex_0162_lower_positional_tool_history,
)
from slaif_gateway.modules.codex_tool_history import (
    DEFAULT_INCREMENTAL_TOOLS_HINT,
    codex_positional_hint_positions,
    codex_standalone_text_content,
)
from slaif_gateway.modules.servers.upstream_llm.profiles import (
    bootstrap_upstream_llm_profiles,
)
from slaif_gateway.services.responses_request_policy import (
    _codex_positional_prepared_body,
    apply_codex_positional_prepared_estimate,
)
from tests.unit.test_codex_tool_history_replay_wiring import (
    apply_body,
    base_model,
    call,
    decl,
    fn,
    notice,
    ns,
    out,
    user,
)
from tests.unit.test_local_coding_vllm import CAPS
from tests.unit.test_upstream_llm_adapter import capabilities


def text_part(text):
    return [{"type": "input_text", "text": text}]


@pytest.mark.parametrize("transport", ["vllm", "llama-cpp-qwen-v1"])
def test_real_array_hint_has_same_lowering_and_prepared_estimate_as_string(transport):
    bootstrap_upstream_llm_profiles()
    try:
        route_caps = CAPS if transport == "vllm" else capabilities(transport)
        prepared_bodies = []
        estimates = []
        for encode in (str, text_part):
            body = base_model()
            body["input"] = [
                {"role": "developer", "content": "Leading ordinary instruction"},
                user("open"),
                decl(ns("functions", fn("alpha"))),
                call("alpha", "call-1"),
                out("call-1"),
                {"role": "developer", "content": encode(notice(tools={
                    ("functions", "alpha"),
                })["content"])},
                {"role": "developer", "content": encode(DEFAULT_INCREMENTAL_TOOLS_HINT)},
                decl(ns("clock", fn("omega"))),
                user("continue"),
            ]
            result, _ = apply_body(body)
            original = copy.deepcopy(result.effective_body)
            lowered = codex_0162_lower_positional_tool_history(
                result.effective_body, result.codex_tool_history
            )
            assert [item.get("role") for item in lowered["input"]] == [
                "developer", "user", None, None, "user",
            ]
            assert lowered["input"][0]["content"] == "Leading ordinary instruction"
            assert lowered["input"][-1] == user("continue")
            prepared_bodies.append(_codex_positional_prepared_body(
                lowered, route_caps, result.codex_tool_history.call_bindings
            ))
            adjusted = apply_codex_positional_prepared_estimate(
                result, upstream_body=lowered,
                route_capabilities=route_caps, input_ceiling=1_050_000,
            )
            estimates.append((
                adjusted.estimated_input_tokens, adjusted.unadjusted_input_tokens,
            ))
            assert result.effective_body == original
        assert prepared_bodies[0] == prepared_bodies[1]
        assert estimates[0] == estimates[1]
    finally:
        bootstrap_upstream_llm_profiles()


@pytest.mark.parametrize("encode", [str, text_part])
def test_hint_recognition_requires_exact_literal_developer_role_and_adjacency(encode):
    literal = DEFAULT_INCREMENTAL_TOOLS_HINT
    declaration = decl(ns("functions", fn("alpha")))
    message = {"role": "developer", "content": encode(literal)}
    assert codex_positional_hint_positions([message, declaration]) == {0}
    assert codex_positional_hint_positions([
        {**message, "type": "message"}, declaration,
    ]) == {0}
    for role in ("user", "assistant", "system"):
        assert not codex_positional_hint_positions([
            {**message, "role": role}, declaration,
        ])
    for content in (literal + "\n", " " + literal, "ordinary developer instruction"):
        assert not codex_positional_hint_positions([
            {**message, "content": encode(content)}, declaration,
        ])
    assert not codex_positional_hint_positions([message, user("gap"), declaration])
    assert not codex_positional_hint_positions([declaration, message])


@pytest.mark.parametrize("content", [
    None, 1, {}, [],
    [{"type": "input_text", "text": 1}],
    [{"type": "output_text", "text": DEFAULT_INCREMENTAL_TOOLS_HINT}],
    [{"type": "input_text", "text": DEFAULT_INCREMENTAL_TOOLS_HINT},
     {"type": "input_text", "text": ""}],
])
def test_standalone_decoder_never_concatenates_or_coerces(content):
    assert codex_standalone_text_content(content) is None
    assert not codex_positional_hint_positions([
        {"role": "developer", "content": content},
        decl(ns("functions", fn("alpha"))),
    ])


def test_nonadjacent_array_hint_remains_ordinary_history():
    body = base_model()
    message = {"role": "developer", "content": text_part(DEFAULT_INCREMENTAL_TOOLS_HINT)}
    body["input"] = [
        user("open"), decl(ns("functions", fn("alpha"))),
        message, user("close"),
    ]
    result, _ = apply_body(body)
    lowered = codex_0162_lower_positional_tool_history(
        result.effective_body, result.codex_tool_history
    )
    assert lowered["input"] == [user("open"), message, user("close")]
