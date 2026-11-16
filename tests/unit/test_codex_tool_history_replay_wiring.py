"""226-b integration regressions: declaration-history lifecycle wiring.

Covers the b-round acceptance categories at the policy/gateway/adapter
seams.  The pure helper lifecycle law (pinned grammar, transitions,
reason codes) is owned by tests/unit/test_codex_tool_history.py from
226-a and is not duplicated here.
"""

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import (
    Codex0162ResponsesClientModule,
    codex_0162_lower_positional_tool_history,
)
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file
from slaif_gateway.modules.codex_tool_history import (
    DEFAULT_INCREMENTAL_TOOLS_HINT,
    DEFAULT_REMOVED_NAMESPACES_HEADER,
    DEFAULT_REMOVED_TOOLS_HEADER,
)
from slaif_gateway.modules.servers.local_coding_vllm.adapter import prepare_vllm_body
from slaif_gateway.modules.servers.upstream_llm.adapter import prepare_upstream_llm_body
from slaif_gateway.providers.errors import (
    ProviderRequestError,
    ProviderResponseParseError,
)
from slaif_gateway.schemas.providers import (
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from slaif_gateway.services import responses_gateway as gateway
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
    _codex_positional_prepared_estimate_bytes,
    apply_codex_positional_prepared_estimate,
    codex_replay_request_candidates,
)
from tests.unit.test_local_coding_vllm import CAPS
from tests.unit.test_upstream_llm_adapter import capabilities

ROOT = Path("app/slaif_gateway/modules/clients/profiles")
CANARY = "canary-secret-value-226b"

# --- builders ----------------------------------------------------------------


def module():
    return Codex0162ResponsesClientModule(
        load_codex_profile_file(ROOT / "codex-0.167.1.json")
    )


def _options(**gates):
    options = {
        "allow_codex_request_envelope": True,
        "allow_codex_client_tools": True,
        "allow_codex_streaming_tool_events": True,
    }
    options.update(gates)
    return options


def apply_body(body, *, settings=None, **gates):
    m = module()
    policy = ResponsesRequestPolicy(settings or Settings(), client_spec=m.policy_spec)
    return policy.apply(m.normalize_responses(body).body, **_options(**gates)), policy


def fn(name, properties=None):
    return {
        "type": "function",
        "name": name,
        "parameters": {"type": "object", "properties": properties or {}},
    }


def custom(name):
    return {
        "type": "custom",
        "name": name,
        "format": {"type": "grammar", "syntax": "lark", "definition": "start: /x/"},
    }


def ns(name, *tools):
    return {"type": "namespace", "name": name, "tools": list(tools)}


def decl(*groups, item_id=None):
    item = {"type": "additional_tools", "role": "developer", "tools": list(groups)}
    if item_id is not None:
        item["id"] = item_id
    return item


def call(name, call_id, *, id_=None, namespace=None, arguments="{}"):
    item = {"type": "function_call", "call_id": call_id, "name": name, "arguments": arguments}
    if id_ is not None:
        item["id"] = id_
    if namespace is not None:
        item["namespace"] = namespace
    return item


def custom_call(name, call_id, *, id_=None, namespace=None, text="raw text"):
    item = {"type": "custom_tool_call", "call_id": call_id, "name": name, "input": text}
    if id_ is not None:
        item["id"] = id_
    if namespace is not None:
        item["namespace"] = namespace
    return item


def out(call_id, output="ok"):
    return {"type": "function_call_output", "call_id": call_id, "output": output}


def custom_out(call_id, output="ok"):
    return {"type": "custom_tool_call_output", "call_id": call_id, "output": output}


def notice(namespaces=(), tools=()):
    sections = []
    if namespaces:
        sections.append(
            DEFAULT_REMOVED_NAMESPACES_HEADER
            + "".join("\n- " + name for name in sorted(namespaces))
        )
    if tools:
        sections.append(
            DEFAULT_REMOVED_TOOLS_HEADER
            + "".join("\n- " + f"{n}.{t}" for n, t in sorted(tools))
        )
    return {"role": "developer", "content": "\n\n".join(sections)}


def hint():
    return {"role": "developer", "content": DEFAULT_INCREMENTAL_TOOLS_HINT}


def user(text="say bounded"):
    return {"role": "user", "content": text}


def base_model():
    return {"model": "synthetic", "max_output_tokens": 64}


# --- A. extractor ownership law (pure) ---------------------------------------


def test_positional_candidate_bound_to_earlier_identity_with_later_same_name():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-1", id_="fc-1"),
            decl(ns("clock", fn("alpha")), item_id="d2"),
            out("call-1"),
        ]
    }
    bindings = {"call-1": ("functions", "alpha", "function")}
    candidates = codex_replay_request_candidates(body, codex_tool_call_bindings=bindings)
    call_candidates = [
        c for c in candidates if c.item_kind in ("function_call", "custom_tool_call")
    ]
    assert len(call_candidates) == 1
    candidate = call_candidates[0]
    assert (candidate.tool_namespace, candidate.tool_name, candidate.call_id) == (
        "functions",
        "alpha",
        "call-1",
    )
    assert candidate.item_id == "fc-1"
    # The legacy union drops the same call (the demonstrated bypass); the
    # positional identity is the only admissible source in new mode.
    legacy = codex_replay_request_candidates(body)
    assert not [c for c in legacy if c.call_id == "call-1"]


def test_positional_extraction_does_not_mutate_input():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-1", id_="fc-1"),
            out("call-1"),
        ]
    }
    original = copy.deepcopy(body)
    codex_replay_request_candidates(
        body, codex_tool_call_bindings={"call-1": ("functions", "alpha", "function")}
    )
    assert body == original


def test_positional_explicit_namespace_contradiction_denies():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-1", id_="fc-1", namespace="clock"),
            out("call-1"),
        ]
    }
    with pytest.raises(ValueError, match="codex_replay_candidate_extraction_failed"):
        codex_replay_request_candidates(
            body, codex_tool_call_bindings={"call-1": ("functions", "alpha", "function")}
        )


def test_positional_unbound_and_duplicate_calls_deny():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-1", id_="fc-1"),
            out("call-1"),
            call("alpha", "call-1", id_="fc-2"),
            out("call-1"),
        ]
    }
    with pytest.raises(ValueError, match="codex_replay_candidate_extraction_failed"):
        codex_replay_request_candidates(
            body, codex_tool_call_bindings={"call-1": ("functions", "alpha", "function")}
        )
    body_unbound = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-9", id_="fc-9"),
            out("call-9"),
        ]
    }
    with pytest.raises(ValueError, match="codex_replay_candidate_extraction_failed"):
        codex_replay_request_candidates(body_unbound, codex_tool_call_bindings={})


def test_positional_idless_qualified_and_unqualified():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-1"),
            out("call-1"),
        ]
    }
    bindings = {"call-1": ("functions", "alpha", "function")}
    candidates = codex_replay_request_candidates(
        body, codex_tool_call_bindings=bindings, allow_idless_tool_call_replay=True
    )
    assert len(candidates) == 1 and candidates[0].item_id is None
    with pytest.raises(ValueError, match="codex_replay_reference_form_unavailable"):
        codex_replay_request_candidates(body, codex_tool_call_bindings=bindings)


def test_positional_completeness_missing_bound_call_denies():
    body = {"input": [decl(ns("functions", fn("alpha")), item_id="d1"), user()]}
    with pytest.raises(ValueError, match="codex_replay_candidate_extraction_failed"):
        codex_replay_request_candidates(
            body,
            codex_tool_call_bindings={"call-missing": ("functions", "alpha", "function")},
        )


def test_positional_reasoning_and_compaction_candidates_coexist():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            {"type": "reasoning", "id": "rs-1", "encrypted_content": "opaque"},
            call("alpha", "call-1", id_="fc-1"),
            out("call-1"),
        ]
    }
    candidates = codex_replay_request_candidates(
        body, codex_tool_call_bindings={"call-1": ("functions", "alpha", "function")}
    )
    kinds = {c.item_kind: c for c in candidates}
    assert set(kinds) == {"reasoning", "function_call"}
    assert kinds["reasoning"].item_id == "rs-1"
    assert kinds["function_call"].call_id == "call-1"


def test_legacy_zero_and_ambiguous_match_completeness_denies():
    zero = {"input": [call("nope", "call-1", id_="fc-1")]}
    with pytest.raises(ValueError, match="codex_replay_candidate_extraction_failed"):
        codex_replay_request_candidates(zero, require_call_completeness=True)
    assert codex_replay_request_candidates(zero) == ()

    ambiguous = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            decl(ns("clock", fn("alpha")), item_id="d2"),
            call("alpha", "call-1", id_="fc-1"),
        ]
    }
    with pytest.raises(ValueError, match="codex_replay_candidate_extraction_failed"):
        codex_replay_request_candidates(ambiguous, require_call_completeness=True)
    assert codex_replay_request_candidates(ambiguous) == ()


def test_legacy_validated_idless_completeness_denies_without_flag():
    body = {
        "input": [
            decl(ns("functions", fn("alpha")), item_id="d1"),
            call("alpha", "call-1"),
        ]
    }
    assert codex_replay_request_candidates(body) == ()
    with pytest.raises(ValueError, match="codex_replay_reference_form_unavailable"):
        codex_replay_request_candidates(body, require_call_completeness=True)
    candidates = codex_replay_request_candidates(
        body, allow_idless_tool_call_replay=True, require_call_completeness=True
    )
    assert len(candidates) == 1 and candidates[0].item_id is None


# --- B. policy level (0.167.1) ------------------------------------------------


def test_multiple_updates_second_declaration_at_index_265_under_explicit_512_limit():
    settings = Settings(RESPONSES_MAX_INPUT_ITEMS=512)
    filler = [user(f"filler {i}") for i in range(264)]
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        *filler,
        decl(ns("functions", fn("beta"), fn("alpha")), item_id="d2"),
        user("final"),
    ]
    assert body["input"][265]["id"] == "d2"
    result, _ = apply_body(body, settings=settings)
    facts = result.codex_tool_history
    assert facts is not None
    assert set(facts.active_definitions) == {
        ("functions", "alpha"),
        ("functions", "beta"),
    }
    assert 265 in [step.position for step in facts.steps]


def test_identical_repeated_declarations_same_different_omitted_inert_ids():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="same-id"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        # identical re-declaration, SAME inert ID
        decl(ns("functions", fn("alpha")), item_id="same-id"),
        # equivalent re-declaration, DIFFERENT inert ID
        decl(ns("functions", fn("alpha")), item_id="other-id"),
        call("alpha", "call-2", id_="fc-2"),
        out("call-2"),
        # OMMITTED inert ID
        decl(ns("functions", fn("alpha"))),
    ]
    result, _ = apply_body(body)
    facts = result.codex_tool_history
    assert set(facts.active_definitions) == {("functions", "alpha")}
    assert set(facts.call_bindings) == {"call-1", "call-2"}


def test_exec_kind_transitions_both_directions_with_completed_calls():
    # custom -> function: historical custom call keeps its original
    # binding; the final current catalog holds the function definition.
    to_function = base_model()
    to_function["input"] = [
        decl(ns("functions", custom("exec")), item_id="d1"),
        custom_call("exec", "call-1", id_="fc-1"),
        custom_out("call-1"),
        hint(),
        decl(ns("functions", fn("exec", {"cmd": {"type": "string"}})), item_id="d2"),
        call("exec", "call-2", id_="fc-2"),
        out("call-2"),
    ]
    result, _ = apply_body(to_function)
    facts = result.codex_tool_history
    assert facts.call_bindings["call-1"] == ("functions", "exec", "custom")
    assert facts.call_bindings["call-2"] == ("functions", "exec", "function")
    assert facts.active_definitions[("functions", "exec")]["type"] == "function"
    assert facts.active_definitions[("functions", "exec")]["parameters"]["properties"] == {
        "cmd": {"type": "string"}
    }

    # function -> custom: mirrored direction.
    to_custom = base_model()
    to_custom["input"] = [
        decl(ns("functions", fn("exec")), item_id="d1"),
        call("exec", "call-1", id_="fc-1"),
        out("call-1"),
        hint(),
        decl(ns("functions", custom("exec")), item_id="d2"),
        custom_call("exec", "call-2", id_="fc-2"),
        custom_out("call-2"),
    ]
    result2, _ = apply_body(to_custom)
    facts2 = result2.codex_tool_history
    assert facts2.call_bindings["call-1"] == ("functions", "exec", "function")
    assert facts2.call_bindings["call-2"] == ("functions", "exec", "custom")
    assert facts2.active_definitions[("functions", "exec")]["type"] == "custom"


def test_same_name_schema_redefinition_final_definition_wins():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        hint(),
        decl(ns("functions", fn("alpha", {"k": {"type": "string"}})), item_id="d2"),
        call("alpha", "call-2", id_="fc-2"),
        out("call-2"),
    ]
    result, _ = apply_body(body)
    definition = result.codex_tool_history.active_definitions[("functions", "alpha")]
    assert definition["parameters"]["properties"] == {"k": {"type": "string"}}


@pytest.mark.parametrize("gate", ["allow_codex_client_tools", "allow_codex_request_envelope"])
def test_missing_permission_denies_before_any_provider_work(gate):
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    with pytest.raises(ResponsesRequestPolicyError):
        apply_body(body, **{gate: False})


def test_provider_state_mixing_denied_for_positional_history():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    body["previous_response_id"] = "resp_previous"
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(body)
    assert exc.value.error_code == "responses_codex_replay_provider_state_not_supported"


def test_provider_state_mixing_denied_when_legacy_union_would_drop_call():
    # The root-confirmed regression: earlier namespace-less call, later
    # same-name namespace.  The legacy union sees zero candidates here;
    # the positional bindings must still trigger the mixing denial.
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        decl(ns("clock", fn("alpha")), item_id="d2"),
        out("call-1"),
    ]
    body["previous_response_id"] = "resp_previous"
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(body)
    assert exc.value.error_code == "responses_codex_replay_provider_state_not_supported"


def test_positional_accepted_without_provider_state():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    result, _ = apply_body(body)
    assert result.codex_tool_history is not None


def test_predeclaration_call_denied_with_position():
    body = base_model()
    body["input"] = [
        user("first"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        decl(ns("functions", fn("alpha")), item_id="d1"),
    ]
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(body)
    assert exc.value.error_code == "responses_codex_tool_history_invalid"
    assert exc.value.param.startswith("input[1]")
    assert CANARY not in str(exc.value)


def test_removed_tool_new_call_denied():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        notice(tools={("functions", "alpha")}),
        call("alpha", "call-2", id_="fc-2"),
        out("call-2"),
    ]
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(body)
    assert exc.value.error_code == "responses_codex_tool_history_invalid"


@pytest.mark.parametrize("position", ["first", "middle", "last"])
def test_invalid_declaration_at_every_position(position):
    invalid = decl(ns("functions", fn("alpha"), fn("bad name!")))
    valid = decl(ns("functions", fn("alpha")))
    if position == "first":
        items, expected = [invalid, user(), valid], "input[0]"
    elif position == "middle":
        items, expected = [valid, user(), invalid], "input[2]"
    else:
        items, expected = [valid, user(), invalid, user()], "input[2]"
    body = base_model()
    body["input"] = items
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(body)
    assert exc.value.error_code == "responses_codex_client_tools_invalid"
    assert exc.value.param.startswith(expected)


def test_duplicate_call_output_and_unfinished_guards():
    duplicate_calls = base_model()
    duplicate_calls["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        call("alpha", "call-1", id_="fc-2"),
        out("call-1"),
        out("call-1"),
    ]
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(duplicate_calls)
    assert exc.value.error_code == "responses_codex_tool_history_invalid"

    duplicate_outputs = base_model()
    duplicate_outputs["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        out("call-1"),
    ]
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(duplicate_outputs)
    assert exc.value.error_code == "responses_codex_tool_history_invalid"

    unfinished = base_model()
    unfinished["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
    ]
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(unfinished)
    assert exc.value.error_code == "responses_codex_tool_history_invalid"


def test_add_remove_reintroduce_final_catalog():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        notice(tools={("functions", "alpha")}),
        hint(),
        decl(ns("functions", fn("alpha")), item_id="d2"),
        call("alpha", "call-2", id_="fc-2"),
        out("call-2"),
    ]
    result, _ = apply_body(body)
    facts = result.codex_tool_history
    assert set(facts.active_definitions) == {("functions", "alpha")}
    lowered = codex_0162_lower_positional_tool_history(result.effective_body, facts)
    tools = lowered["tools"]
    assert [g["name"] for g in tools] == ["functions"]
    assert {t["name"] for t in tools[0]["tools"]} == {"alpha"}
    assert not [
        i for i in lowered["input"]
        if i.get("type") == "additional_tools"
        or i.get("content") == DEFAULT_INCREMENTAL_TOOLS_HINT
    ]


def test_schema_type_transition_error_is_content_free():
    # function -> custom is allowed only for preset-approved custom names;
    # "alpha" is not approved, so the denial must stay content-free.
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        hint(),
        decl(ns("functions", custom("alpha")), item_id="d2"),
    ]
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_body(body)
    assert exc.value.error_code in {
        "responses_codex_client_tools_invalid",
        "responses_codex_tool_history_invalid",
    }
    assert "CANARY" not in str(exc.value)


def test_reused_policy_instance_carries_no_stale_facts():
    policy = ResponsesRequestPolicy(Settings(), client_spec=module().policy_spec)
    m = module()
    first = base_model()
    first["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    result1 = policy.apply(m.normalize_responses(first).body, **_options())
    assert set(result1.codex_tool_history.call_bindings) == {"call-1"}

    second = base_model()
    second["input"] = [user("plain follow-up")]
    result2 = policy.apply(m.normalize_responses(second).body, **_options())
    assert result2.codex_tool_history is not None
    assert len(result2.codex_tool_history.active_definitions) == 0
    assert len(result2.codex_tool_history.call_bindings) == 0

    # Minimal valid non-Codex compact payload (model + input only);
    # base_model() carries max_output_tokens, unsupported by compact.
    compact_body = {"model": "synthetic", "input": [user("compact history")]}
    result3 = policy.apply_compact(m.normalize_responses(compact_body).body)
    assert result3.codex_tool_history is None


def test_string_input_materializes_empty_facts_direct_policy():
    # Defensive direct policy check: the frozen client module does not
    # normalize string input; the policy itself must materialize empty
    # active facts for a positional-mode string request.
    policy = ResponsesRequestPolicy(Settings(), client_spec=module().policy_spec)
    result = policy.apply({"model": "synthetic", "input": "hello bounded"})
    facts = result.codex_tool_history
    assert facts is not None
    assert len(facts.active_definitions) == 0
    assert len(facts.call_bindings) == 0
    assert "codex_tool_history" not in result.model_dump()
    assert CANARY not in repr(result)


def test_declaration_free_list_pipeline_has_empty_facts():
    body = base_model()
    body["input"] = [user("declaration-free history")]
    result, _ = apply_body(body)
    facts = result.codex_tool_history
    assert facts is not None
    assert len(facts.active_definitions) == 0
    assert len(facts.call_bindings) == 0


# --- C. lowering / both backends / no mutation --------------------------------


def test_lowering_preserves_entire_ordinary_history_and_mutates_nothing():
    body = base_model()
    body["input"] = [
        user("open"),
        decl(ns("functions", fn("alpha")), item_id="d1"),
        hint(),  # after d1, before the call: ordinary history
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        notice(tools={("functions", "alpha")}),
        hint(),  # immediately before d2: declaration metadata
        decl(ns("clock", fn("omega")), item_id="d2"),
        user("close"),
    ]
    result, _ = apply_body(body)
    facts = result.codex_tool_history
    original_body = copy.deepcopy(result.effective_body)
    original_definitions = {
        key: copy.deepcopy(value) for key, value in facts.active_definitions.items()
    }
    lowered = codex_0162_lower_positional_tool_history(result.effective_body, facts)
    assert result.effective_body == original_body
    for key, value in facts.active_definitions.items():
        assert value == original_definitions[key]
    remaining = lowered["input"]
    assert len(remaining) == 5
    # Full canonical ordinary items at explicit known indices: roles,
    # contents, IDs, and relative order intact.
    assert remaining[0] == {"role": "user", "content": "open"}
    assert remaining[1] == {
        "role": "developer",
        "content": DEFAULT_INCREMENTAL_TOOLS_HINT,
    }
    assert remaining[2] == {
        "type": "function_call",
        "call_id": "call-1",
        "name": "alpha",
        "id": "fc-1",
        "arguments": "{}",
    }
    assert remaining[3] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "ok",
    }
    assert remaining[4] == {"role": "user", "content": "close"}
    tools = lowered["tools"]
    assert [g["name"] for g in tools] == ["clock"]
    assert {t["name"] for t in tools[0]["tools"]} == {"omega"}


def test_prepared_bodies_for_both_backends():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    result, _ = apply_body(body)
    facts = result.codex_tool_history
    lowered = codex_0162_lower_positional_tool_history(result.effective_body, facts)

    local_body, local_codec = prepare_vllm_body(
        lowered, tool_call_bindings=facts.call_bindings
    )
    assert {t["name"] for t in local_body["tools"]} == {"functions.alpha"}

    profile = load_profiles_snapshot()["responses-functions-v1"]
    portable_body, portable_codec = prepare_upstream_llm_body(
        lowered, profile, tool_call_bindings=facts.call_bindings
    )
    portable_names = {t["name"] for t in portable_body["tools"]}
    assert len(portable_names) == 1
    portable_name = next(iter(portable_names))
    assert portable_name.startswith("tool_functions_alpha_")
    assert portable_name != "functions.alpha"
    assert local_codec is not None and portable_codec is not None


def test_pure_preview_and_transport_share_placement_refusal():
    # Late ordinary developer text after history: an order-changing
    # profile must refuse identically in the pure pre-admission preview
    # and in the production transport (same fixed safe code).
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        user("close"),
        {"role": "developer", "content": "late ordinary instruction"},
    ]
    result, _ = apply_body(body)
    lowered = codex_0162_lower_positional_tool_history(
        result.effective_body, result.codex_tool_history
    )
    profile = load_profiles_snapshot()["llama-cpp-qwen-v1"]
    assert profile.instruction_placement == "leading_system_developer"
    with pytest.raises(ProviderRequestError) as exc:
        prepare_upstream_llm_body(
            dict(lowered), profile, tool_call_bindings=result.codex_tool_history.call_bindings
        )
    assert exc.value.error_code == "upstream_llm_bindings_placement_conflict"
    assert exc.value.status_code == 400
    assert "late ordinary instruction" not in str(exc.value)

    # Prefix-only instructions remain representable on the same profile.
    prefix_body = base_model()
    prefix_body["input"] = [
        {"role": "developer", "content": "leading instruction"},
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        user("close"),
    ]
    prefix_result, _ = apply_body(prefix_body)
    prefix_lowered = codex_0162_lower_positional_tool_history(
        prefix_result.effective_body, prefix_result.codex_tool_history
    )
    prepared, _ = prepare_upstream_llm_body(
        dict(prefix_lowered),
        profile,
        tool_call_bindings=prefix_result.codex_tool_history.call_bindings,
    )
    assert prepared["input"][0] == {"role": "developer", "content": "leading instruction"}

    # Legacy bindings=None keeps the existing reordering behavior.
    legacy_prepared, _ = prepare_upstream_llm_body(
        dict(lowered), profile, tool_call_bindings=None
    )
    assert legacy_prepared["input"][0] == {
        "role": "developer",
        "content": "late ordinary instruction",
    }


def test_preflight_estimate_refuses_before_admission():
    from slaif_gateway.modules.servers.upstream_llm.profiles import (
        bootstrap_upstream_llm_profiles,
    )

    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        user("close"),
        {"role": "developer", "content": "late ordinary instruction"},
    ]
    result, _ = apply_body(body)
    lowered = codex_0162_lower_positional_tool_history(
        result.effective_body, result.codex_tool_history
    )
    bootstrap_upstream_llm_profiles()
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        apply_codex_positional_prepared_estimate(
            result,
            upstream_body=lowered,
            route_capabilities=capabilities(),
            input_ceiling=1050000,
        )
    assert exc.value.error_code == "responses_codex_tool_wire_invalid"
    assert "late ordinary instruction" not in str(exc.value)


def load_profiles_snapshot():
    from slaif_gateway.modules.servers.upstream_llm.profiles import load_profiles

    return load_profiles()


def test_prepared_estimate_counts_forwarded_fields_only():
    # The estimator measures the PREPARED (forwarded) body: a
    # prompt_cache_key present there MUST count.
    with_cache = {
        "input": "x" * 300,
        "instructions": "i" * 50,
        "tools": [{"type": "function", "name": "a", "parameters": {"type": "object"}}],
        "prompt_cache_key": "forwarded-cache",
    }
    without_cache = {k: v for k, v in with_cache.items() if k != "prompt_cache_key"}
    total_with, non_message_with, fields_with = (
        _codex_positional_prepared_estimate_bytes(with_cache)
    )
    total_without, non_message_without, fields_without = (
        _codex_positional_prepared_estimate_bytes(without_cache)
    )
    assert total_with > total_without
    assert non_message_with > non_message_without
    assert "prompt_cache_key" in fields_with
    assert "prompt_cache_key" not in fields_without
    # string input and instructions are message material, not non-message.
    assert non_message_with < total_with
    assert total_with >= 300 + 50


def test_local_pipeline_strips_prompt_cache_key_before_the_estimator():
    body = base_model()
    body["prompt_cache_key"] = "local-cache-key"
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    result, _ = apply_body(body)
    facts = result.codex_tool_history
    lowered = codex_0162_lower_positional_tool_history(result.effective_body, facts)
    assert "prompt_cache_key" in lowered
    safe_body = gateway._build_safe_responses_upstream_body(
        policy_result=result,
        upstream_model="synthetic",
        omit_prompt_cache_key=True,
        lower_codex_0162_positional_history=True,
        lower_codex_0162_initial_declaration=False,
    )
    assert "prompt_cache_key" not in safe_body
    total, non_message, fields = _codex_positional_prepared_estimate_bytes(safe_body)
    assert "prompt_cache_key" not in fields
    assert total > 0


def test_prepared_estimate_reanchoring_is_idempotent():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    result, _ = apply_body(body)
    lowered = codex_0162_lower_positional_tool_history(
        result.effective_body, result.codex_tool_history
    )
    once = apply_codex_positional_prepared_estimate(
        result,
        upstream_body=lowered,
        route_capabilities=None,
        input_ceiling=1_000_000,
    )
    twice = apply_codex_positional_prepared_estimate(
        once,
        upstream_body=lowered,
        route_capabilities=None,
        input_ceiling=1_000_000,
    )
    assert once.unadjusted_input_tokens == twice.unadjusted_input_tokens
    assert once.estimated_input_tokens == twice.estimated_input_tokens


# --- D. output guard + codec refusal settlement seam --------------------------


def _provider_response(output_items, usage):
    return ProviderResponse(
        provider="local-coding-vLLM",
        upstream_model="synthetic",
        status_code=200,
        json_body={"output": output_items},
        usage=usage,
    )


def test_empty_catalog_output_guard_denies_generated_call():
    policy = ResponsesRequestPolicy(Settings(), client_spec=module().policy_spec)
    result = policy.apply({"model": "synthetic", "input": "hello bounded"})
    active = gateway._codex_positional_active_tool_identities(result)
    assert active is not None and len(active) == 0

    usage = ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    response = _provider_response(
        [{"type": "function_call", "name": "alpha", "arguments": "{}"}], usage
    )
    with pytest.raises(OpenAICompatibleError) as exc:
        gateway._enforce_codex_positional_output_policy(
            provider_response=response, policy_result=result
        )
    assert exc.value.status_code == 502
    assert exc.value.code == "responses_codex_tool_history_obsolete_call"

    malformed = _provider_response(
        [{"type": "function_call", "name": None, "arguments": "{}"}], usage
    )
    with pytest.raises(OpenAICompatibleError):
        gateway._enforce_codex_positional_output_policy(
            provider_response=malformed, policy_result=result
        )

    text_only = _provider_response(
        [{"type": "message", "role": "assistant", "content": []}], usage
    )
    gateway._enforce_codex_positional_output_policy(
        provider_response=text_only, policy_result=result
    )

    legacy_result = SimpleNamespace(codex_tool_history=None)
    gateway._enforce_codex_positional_output_policy(
        provider_response=response, policy_result=legacy_result
    )


def test_output_guard_enforces_final_set_after_removal():
    body = base_model()
    body["input"] = [
        decl(ns("functions", fn("alpha")), item_id="d1"),
        call("alpha", "call-1", id_="fc-1"),
        out("call-1"),
        notice(tools={("functions", "alpha")}),
    ]
    result, _ = apply_body(body)
    usage = ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    historical_call = _provider_response(
        [{"type": "function_call", "name": "alpha", "arguments": "{}"}], usage
    )
    with pytest.raises(OpenAICompatibleError):
        gateway._enforce_codex_positional_output_policy(
            provider_response=historical_call, policy_result=result
        )


def _lifecycle_request(bindings):
    return ProviderRequest(
        provider="local-coding-vLLM",
        upstream_model="synthetic",
        endpoint="responses",
        body={
            "input": [{"role": "user", "content": "bounded"}],
            "tools": [
                {
                    "type": "namespace",
                    "name": "functions",
                    "tools": [
                        {
                            "type": "function",
                            "name": "kept",
                            "parameters": {"type": "object", "properties": {}},
                        }
                    ],
                }
            ],
        },
        codex_tool_call_bindings=bindings,
    )


def test_vllm_lifecycle_refusal_retains_settlement_metadata(monkeypatch):
    from dataclasses import replace

    import asyncio

    from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
    from slaif_gateway.modules.servers.local_coding_vllm.adapter import (
        LocalCodingVLLMAdapter,
    )

    adapter = LocalCodingVLLMAdapter(Settings(), route_capabilities=CAPS)

    async def fake_base_forward(self, request):
        return _provider_response(
            [{"type": "function_call", "name": "functions.removed", "arguments": "{}"}],
            ProviderUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
        )

    monkeypatch.setattr(LocalCodingAdapter, "forward_response", fake_base_forward)
    result = asyncio.run(adapter.forward_response(_lifecycle_request({})))
    assert result.json_body == {}
    assert result.text_body is None
    assert result.binary_body is None
    assert result.safe_rejection_code == "vllm_tool_protocol_invalid"
    assert result.usage.prompt_tokens == 7
    assert result.usage.completion_tokens == 3
    assert result.usage.total_tokens == 10
    assert "functions.removed" not in repr(result)

    with pytest.raises(ProviderResponseParseError):
        asyncio.run(
            adapter.forward_response(replace(_lifecycle_request({}), codex_tool_call_bindings=None))
        )


def test_upstream_llm_lifecycle_refusal_retains_settlement_metadata(monkeypatch):
    from dataclasses import replace

    import asyncio

    from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
    from slaif_gateway.modules.servers.upstream_llm.adapter import (
        ConfiguredUpstreamLLMAdapter,
    )

    adapter = ConfiguredUpstreamLLMAdapter(
        Settings(), route_capabilities=capabilities("native-vllm-v1")
    )

    async def fake_base_forward(self, request):
        return _provider_response(
            [{"type": "function_call", "name": "functions.removed", "arguments": "{}"}],
            ProviderUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7),
        )

    monkeypatch.setattr(LocalCodingAdapter, "forward_response", fake_base_forward)
    result = asyncio.run(adapter.forward_response(_lifecycle_request({})))
    assert result.json_body == {}
    assert result.text_body is None
    assert result.binary_body is None
    assert result.safe_rejection_code == "vllm_tool_protocol_invalid"
    assert result.usage.prompt_tokens == 5
    assert result.usage.completion_tokens == 2
    assert result.usage.total_tokens == 7
    assert "functions.removed" not in repr(result)

    with pytest.raises(ProviderResponseParseError):
        asyncio.run(
            adapter.forward_response(
                replace(_lifecycle_request({}), codex_tool_call_bindings=None)
            )
        )


def test_core_marker_check_refuses_fixed_502():
    from dataclasses import replace

    marked = _provider_response(
        [], ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    )
    marked = replace(marked, safe_rejection_code="vllm_tool_protocol_invalid")
    with pytest.raises(OpenAICompatibleError) as excinfo:
        gateway._reject_settled_codec_rejection(marked)
    error = excinfo.value
    assert error.status_code == 502
    assert error.code == "vllm_tool_protocol_invalid"
    assert "vllm_tool_protocol_invalid" not in repr(marked)

    unmarked = _provider_response(
        [{"type": "message", "role": "assistant", "content": []}],
        ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    assert unmarked.safe_rejection_code is None
    gateway._reject_settled_codec_rejection(unmarked)
