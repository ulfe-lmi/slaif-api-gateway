"""Optional result identities are corroboration, never tool/replay authority."""

import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import codex_0162_lower_positional_tool_history
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.providers.errors import ProviderRequestError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
)
from tests.unit.test_codex_0164_preset import apply
from tests.unit.test_codex_tool_history_replay_wiring import (
    apply_body, base_model, call, custom, custom_call, custom_out, decl, fn,
    notice, ns, out, user,
)


def history(custom_kind=False, **identity):
    definition = custom("exec") if custom_kind else fn("read")
    name = definition["name"]
    invoke = custom_call if custom_kind else call
    result = custom_out if custom_kind else out
    return {**base_model(), "input": [
        decl(ns("functions", definition, fn("kept"))),
        invoke(name, "call_original", namespace="functions"),
        # Removal and a same-name declaration elsewhere must not rebind the call.
        notice(tools={("functions", name)}),
        decl(ns("functions", fn("kept")), ns("mcp__codex_tui", fn(name))),
        {**result("call_original"), **identity},
        user(),
    ]}


@pytest.mark.parametrize("custom_kind", [False, True])
@pytest.mark.parametrize("identity_kind", ["absent", "null", "matching"])
def test_result_identity_matches_historical_call_after_catalog_change(custom_kind, identity_kind):
    name = "exec" if custom_kind else "read"
    identity = {} if identity_kind == "absent" else {
        "name": name if identity_kind == "matching" else None,
    }
    if not custom_kind and identity_kind != "absent":
        identity["namespace"] = "functions" if identity_kind == "matching" else None
    value = history(custom_kind, **identity)
    accepted, _ = apply_body(value)
    assert accepted.effective_body["input"][-2] == value["input"][-2]


@pytest.mark.parametrize("custom_kind", [False, True])
@pytest.mark.parametrize("name", ["kept", "", 1, {}, ["exec"], "é" * 300])
def test_invalid_result_name_cannot_select_another_tool(custom_kind, name):
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply_body(history(custom_kind, name=name))
    assert error.value.error_code == "responses_codex_tool_roundtrip_invalid"
    assert error.value.param == "input[4].name"


@pytest.mark.parametrize("namespace", ["mcp__codex_tui", "", 1, {}, "é" * 300])
def test_result_namespace_must_match_original_call(namespace):
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply_body(history(namespace=namespace))
    assert error.value.param == "input[4].namespace"
    assert error.value.error_code == "responses_codex_tool_roundtrip_invalid"


def test_custom_result_namespace_is_not_in_pinned_source_contract():
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply_body(history(True, name="exec", namespace="functions"))
    assert error.value.param == "input[4].namespace"


@pytest.mark.parametrize("version", ["0.162.1", "0.164.0", "0.167.0"])
def test_frozen_profiles_do_not_gain_result_identity_fields(version):
    value = history(name="read")
    value["input"] = [value["input"][0], value["input"][1], value["input"][-2]]
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply(value, version)
    assert error.value.param == "input[2].name"


def test_ordinary_responses_remains_strict():
    with pytest.raises(ResponsesRequestPolicyError):
        ResponsesRequestPolicy(Settings()).apply({
            **base_model(), "input": [{**out("call_original"), "name": "read"}],
        })


@pytest.mark.parametrize("custom_kind", [False, True])
@pytest.mark.parametrize("portable", [False, True])
def test_codec_translates_result_identity_using_original_call(custom_kind, portable):
    identity = {"name": "exec" if custom_kind else "read"}
    if not custom_kind:
        identity["namespace"] = "functions"
    value = history(custom_kind, **identity)
    accepted, _ = apply_body(value)
    facts = accepted.codex_tool_history
    lowered = codex_0162_lower_positional_tool_history(accepted.effective_body, facts)
    snapshot = copy.deepcopy(lowered)
    codec = VLLMToolCodec(
        lowered, portable_names=portable, tool_call_bindings=facts.call_bindings,
    )
    calls = [i for i in codec.body["input"] if i.get("type") == "function_call"]
    output = next(i for i in codec.body["input"] if i.get("type") == "function_call_output")
    assert output["name"] == calls[0]["name"]
    assert "namespace" not in output
    assert lowered == snapshot


def test_result_identity_is_included_in_input_metering():
    plain, _ = apply_body(history())
    named, _ = apply_body(history(name="read", namespace="functions"))
    assert named.estimated_input_tokens > plain.estimated_input_tokens


@pytest.mark.parametrize("identity", [
    {"name": "kept"}, {"namespace": "mcp__codex_tui"}, {"name": ["read"]},
])
def test_codec_defends_against_result_identity_contradicting_preceding_call(identity):
    # Transport defense also covers a caller that bypasses core preparation.
    value = {
        "tools": [ns("functions", fn("read"), fn("kept"))],
        "input": [
            call("read", "call_original", namespace="functions"),
            {**out("call_original"), **identity},
        ],
    }
    with pytest.raises(ProviderRequestError):
        VLLMToolCodec(value)


def test_codec_namespace_only_result_and_null_name_need_no_fabricated_name():
    accepted, _ = apply_body(history(name=None, namespace="functions"))
    facts = accepted.codex_tool_history
    lowered = codex_0162_lower_positional_tool_history(accepted.effective_body, facts)
    codec = VLLMToolCodec(lowered, tool_call_bindings=facts.call_bindings)
    result = next(i for i in codec.body["input"] if i.get("type") == "function_call_output")
    assert result["name"] is None
    assert "namespace" not in result


@pytest.mark.parametrize("change", ["orphan", "duplicate", "kind", "missing"])
def test_matching_result_name_does_not_relax_linkage(change):
    value = history(name="read", namespace="functions")
    if change == "orphan":
        value["input"][4]["call_id"] = "call_unknown"
    elif change == "duplicate":
        value["input"].insert(5, copy.deepcopy(value["input"][4]))
    elif change == "kind":
        value["input"][4]["type"] = "custom_tool_call_output"
        value["input"][4].pop("namespace")
    else:
        value["input"].pop(4)
    with pytest.raises(ResponsesRequestPolicyError):
        apply_body(value)
