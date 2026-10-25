"""Captured 0.164 declaration vocabulary and generic native custom transport."""

import copy
import json
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import (
    Codex0162ResponsesClientModule,
    classify_additional_tools,
)
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file, parse_codex_profile_data
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
)
from slaif_gateway.providers.errors import ProviderResponseParseError
from tests.unit.test_local_coding_vllm import native_events

ROOT = Path("app/slaif_gateway/modules/clients/profiles")
FIXTURE = json.loads(Path("tests/fixtures/codex/0.164.0/declarations.json").read_text())
WORKTREES = json.loads(Path("tests/fixtures/codex/0.164.0/worktree-declarations.json").read_text())


def module(version):
    return Codex0162ResponsesClientModule(load_codex_profile_file(ROOT / f"codex-{version}.json"))


def body():
    namespaces = []
    for group in FIXTURE["namespaces"]:
        tools = []
        for observed in group["tools"]:
            tool = {k: observed[k] for k in ("type", "name")}
            if tool["type"] == "custom":
                tool["format"] = {"type": "grammar", "syntax": "lark", "definition": "start: /.+/"}
            else:
                tool["parameters"] = {"type": "object", "properties": {}}
            tools.append(tool)
        namespaces.append({"type": "namespace", "name": group["name"], "tools": tools})
    return {
        "model": "synthetic",
        "stream": True,
        "max_output_tokens": 64,
        "input": [
            {"type": "additional_tools", "role": "developer", "tools": namespaces},
            {"role": "user", "content": "Synthetic fixture"},
        ],
    }


def apply(value, version="0.164.0", **gates):
    m = module(version)
    options = {
        "allow_codex_request_envelope": True,
        "allow_codex_client_tools": True,
        "allow_codex_streaming_tool_events": True,
    }
    options.update(gates)
    return ResponsesRequestPolicy(Settings(), client_spec=m.policy_spec).apply(
        m.normalize_responses(value).body, **options
    )


def test_real_captured_vocabulary_reproduces_old_rejection_and_new_acceptance():
    assert FIXTURE["cli_version"] == "0.164.0"
    assert FIXTURE["request_count"] == 1 and FIXTURE["cli_exit_code"] == 0
    assert {g["name"] for g in FIXTURE["namespaces"]} == {"functions", "clock", "collaboration"}
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply(body(), "0.163.0")
    assert error.value.error_code == "responses_codex_client_tools_invalid"
    assert error.value.param == "input[0].tools"
    assert apply(body()).effective_body["input"][0]["tools"] == body()["input"][0]["tools"]


@pytest.mark.parametrize(
    "namespace", ["functions", "multi_agent_v1", "clock", "collaboration", "mcp__codex_worktrees"]
)
def test_previous_and_new_builtin_names_remain_bounded(namespace):
    assert module("0.164.0").profile.classify_namespace_name(namespace) == "builtin"
    assert module("0.164.0").profile.classify_namespace_name(namespace + "_unknown") is None


def test_worktree_declarations_reproduce_revision_13_rejection_and_revision_14_acceptance():
    value = body()
    value["input"][0]["tools"].append(copy.deepcopy(WORKTREES["namespace"]))
    current = module("0.164.0").profile
    assert current.revision == "14"
    previous_data = json.loads((ROOT / "codex-0.164.0.json").read_text())
    previous_data["revision"] = "13"
    previous_data["namespace_rules"]["builtin_names"].remove("mcp__codex_worktrees")
    previous = parse_codex_profile_data(json.dumps(previous_data))
    assert previous.digest == "c78dea4283a1f493f553491c0b02fdc13f119e65ea43eb186ed95707938ecb88"
    rejection = classify_additional_tools(value["input"][0]["tools"], previous)
    assert rejection.reason_code == "namespace_name_unapproved"
    assert rejection.namespace_index == 3
    accepted = apply(value)
    assert accepted.effective_body["input"][0]["tools"] == value["input"][0]["tools"]

    from slaif_gateway.modules.clients.codex_0162 import codex_0162_lower_initial_additional_tools

    codec = VLLMToolCodec(codex_0162_lower_initial_additional_tools(accepted.effective_body))
    assert {t["name"] for t in codec.body["tools"] if t["name"].startswith("mcp__codex_worktrees.")} == {
        "mcp__codex_worktrees." + t["name"] for t in WORKTREES["namespace"]["tools"]
    }
    assert current.connector_prefixes == previous.connector_prefixes
    value["input"][0]["tools"][-1]["name"] = "mcp__unreviewed"
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply(value)
    assert error.value.error_code == "responses_codex_client_tools_invalid"


@pytest.mark.parametrize(
    "change", ["unknown_namespace", "unapproved_custom", "hosted_type", "capability_off"]
)
def test_new_vocabulary_does_not_grant_unknown_tools_or_core_authority(change):
    value = body()
    if change == "unknown_namespace":
        value["input"][0]["tools"][1]["name"] = "unreviewed"
    if change == "unapproved_custom":
        value["input"][0]["tools"][0]["tools"][0]["name"] = "unreviewed"
    if change == "hosted_type":
        value["input"][0]["tools"][1]["tools"][0]["type"] = "web_search"
    with pytest.raises(ResponsesRequestPolicyError):
        apply(value, **({"allow_codex_client_tools": False} if change == "capability_off" else {}))


def test_declared_custom_exec_roundtrips_native_stream_response_and_history():
    raw = body()
    accepted = apply(raw)
    from slaif_gateway.modules.clients.codex_0162 import codex_0162_lower_initial_additional_tools

    lowered = codex_0162_lower_initial_additional_tools(accepted.effective_body)
    snapshot = copy.deepcopy(lowered)
    codec = VLLMToolCodec(lowered)
    assert lowered == snapshot
    native = next(t for t in codec.body["tools"] if t["name"] == "functions.exec")
    assert native["type"] == "function"
    assert native["parameters"] == {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
        "additionalProperties": False,
    }
    source = 'text("SYNTHETIC")'
    wrapped = json.dumps({"input": source})
    events = native_events(wrapped)
    for event in events:
        if "item" in event:
            event["item"]["name"] = "functions.exec"
        if "name" in event:
            event["name"] = "functions.exec"
    output = [out for event in events for out in codec.events(event)]
    call = output[-1]["item"]
    assert (
        call["type"] == "custom_tool_call"
        and call["name"] == "exec"
        and call["namespace"] == "functions"
    )
    assert call["input"] == source and call["call_id"] == "call_synthetic"
    replay = copy.deepcopy(lowered)
    replay["input"] += [
        call,
        {
            "type": "custom_tool_call_output",
            "call_id": "call_synthetic",
            "output": "synthetic output",
        },
    ]
    rebuilt = VLLMToolCodec(replay)
    assert json.loads(rebuilt.body["input"][-2]["arguments"]) == {"input": source}
    assert rebuilt.body["input"][-1]["type"] == "function_call_output"
    with pytest.raises(ProviderResponseParseError):
        rebuilt.item(dict(events[-1]["item"], name="functions.undeclared"))
