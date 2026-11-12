"""Exact 0.167 TUI namespace without broader tool or policy authority."""

import copy
import json
from pathlib import Path

import pytest

from slaif_gateway.modules.clients.codex_0162 import (
    classify_additional_tools,
    codex_0162_lower_initial_additional_tools,
)
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicyError
from tests.unit.test_codex_0164_preset import apply, body, module
from tests.unit.test_local_coding_vllm import native_events

ROOT = Path("app/slaif_gateway/modules/clients/profiles")
FIXTURE = json.loads(Path("tests/fixtures/codex/0.167.0/worktree-declarations.json").read_text())
CAPTURE = json.loads(Path("tests/fixtures/codex/0.167.0/declarations.json").read_text())


def tui_body():
    value = body()
    value["input"][0]["tools"].append(copy.deepcopy(FIXTURE["namespace"]))
    return value


def test_exact_client_captured_catalog_plus_source_derived_tui_declarations():
    value = body()
    value["input"][0]["tools"] = [
        {"type": "namespace", **copy.deepcopy(group)} for group in CAPTURE["namespaces"]
    ]
    value["input"][0]["tools"].append(copy.deepcopy(FIXTURE["namespace"]))
    assert CAPTURE["cli_version"] == "0.167.0"
    assert CAPTURE["request_count"] == 1
    assert CAPTURE["declaration_positions"] == [0]
    # Custom grammar was deliberately omitted from the public structural capture.
    value["input"][0]["tools"][0]["tools"][0]["format"] = {
        "type": "grammar", "syntax": "lark", "definition": "start: /.+/",
    }
    assert apply(value, "0.167.0").effective_body["input"] == value["input"]


def test_revision_15_changes_only_provenance_revision_and_exact_namespace():
    old = json.loads((ROOT / "codex-0.164.0.json").read_text())
    new = json.loads((ROOT / "codex-0.167.0.json").read_text())
    assert new.pop("revision") == "15"
    assert old.pop("revision") == "14"
    assert new.pop("provenance") == {
        "cli_version": "0.167.0",
        "source_tag": "rust-v0.167.0",
        "source_commit": "086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a",
    }
    old.pop("provenance")
    new["namespace_rules"]["builtin_names"].remove("mcp__codex_tui")
    assert new == old
    assert module("0.167.0").fixture_sha256 != module("0.164.0").fixture_sha256


def test_exact_namespace_reproduces_old_rejection_and_new_acceptance():
    value = tui_body()
    rejected = classify_additional_tools(value["input"][0]["tools"], module("0.164.0").profile)
    assert rejected.reason_code == "namespace_name_unapproved"
    assert rejected.namespace_index == 3
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply(value)
    assert error.value.error_code == "responses_codex_client_tools_invalid"
    assert error.value.param == "input[0].tools"
    assert apply(value, "0.167.0").effective_body["input"] == value["input"]


@pytest.mark.parametrize("name", [
    "functions", "multi_agent_v1", "clock", "collaboration", "mcp__codex_worktrees",
    "mcp__codex_tui",
])
def test_exact_builtin_names_remain_bounded(name):
    profile = module("0.167.0").profile
    assert profile.classify_namespace_name(name) == "builtin"
    assert profile.classify_namespace_name(name + "_unknown") is None


@pytest.mark.parametrize("change", ["namespace", "hosted", "custom", "gate"])
def test_new_namespace_does_not_bypass_existing_boundaries(change):
    value = tui_body()
    group = value["input"][0]["tools"][-1]
    if change == "namespace":
        group["name"] = "mcp__unreviewed"
    elif change == "hosted":
        group["tools"][0]["type"] = "web_search"
    elif change == "custom":
        group["tools"][0] = {
            "type": "custom", "name": "exec", "format": {"type": "text"},
        }
    gates = {"allow_codex_client_tools": False} if change == "gate" else {}
    with pytest.raises(ResponsesRequestPolicyError):
        apply(value, "0.167.0", **gates)


def test_tui_function_declaration_stream_and_continuation_roundtrip():
    accepted = apply(tui_body(), "0.167.0")
    lowered = codex_0162_lower_initial_additional_tools(accepted.effective_body)
    codec = VLLMToolCodec(lowered)
    wire = next(t for t in codec.body["tools"] if t["name"] == "mcp__codex_tui.list_worktrees")
    assert wire["parameters"] == FIXTURE["namespace"]["tools"][2]["parameters"]
    events = native_events("{}")
    for event in events:
        if "item" in event:
            event["item"]["name"] = wire["name"]
        if "name" in event:
            event["name"] = wire["name"]
    output = [out for event in events for out in codec.events(event)]
    call = output[-1]["item"]
    assert call["type"] == "function_call"
    assert call["namespace"] == "mcp__codex_tui"
    assert call["name"] == "list_worktrees"
    assert call["arguments"] == "{}"
    replay = copy.deepcopy(lowered)
    replay["input"] += [call, {
        "type": "function_call_output", "call_id": call["call_id"], "output": "[]",
    }]
    rebuilt = VLLMToolCodec(replay)
    assert rebuilt.body["input"][-2]["name"] == wire["name"]
    assert rebuilt.body["input"][-1]["output"] == "[]"
