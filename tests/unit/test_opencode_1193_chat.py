"""Unit tests for the OpenCode 1.19.3 Chat profile, fixtures, and decoder.

Covers:
- the reviewed schema_version 1 packaged profile DATA through the shared
  neutral loader (identity, provenance, dialect bounds, canonical digest);
- the sanitized structural capture fixtures and their digest binding;
- the thin opencode_1193_chat module: static registration, observed-envelope
  acceptance (xhigh, 9 nested declarations, tool-call/result linkage), and
  fail-closed rejections, plus server-side pin resolution behavior.

No provider, no network, no host-default client; stdlib + pytest only.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from slaif_gateway.modules.agent_chat_profile_data import (
    canonical_profile_digest,
    load_agent_chat_profile_file,
)
from slaif_gateway.modules.clients.agent_chat import (
    AGENT_CHAT_ENDPOINT,
    AgentChatModuleSelectionError,
    AgentChatRequestError,
    agent_chat_profile_metadata,
    get_agent_chat_client_module,
    resolve_chat_client_module,
)
from slaif_gateway.modules.clients import opencode_1193_chat as oc

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "opencode" / "1.19.3" / "chat"
PROFILE_PATH = (ROOT / "app" / "slaif_gateway" / "modules" / "clients" / "profiles"
                / "opencode-1.19.3-chat.json")

PINNED_EXECUTABLE_SHA256 = "179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9"
PINNED_SOURCE_TAG = "v1.19.3"
PINNED_SOURCE_COMMIT = "e3c4eb242585dcd77be1a867391b7c25fd47ce52"
BASELINE_VOCABULARY = ["bash", "edit", "glob", "grep", "read", "skill", "task",
                       "todowrite", "write"]

STRUCTURAL_FIXTURES = [
    "structural_text_stream.json",
    "structural_toolloop.json",
    "structural_multicall.json",
    "structural_title_aux.json",
    "structural_compaction.json",
    "structural_reasoning.json",
    "structural_session_identity.json",
]


def _load(name: str):
    return json.loads((FIXTURE_DIR / name).read_text())


def _provenance():
    return _load("provenance.json")


# -- provenance and fixture integrity ---------------------------------------

def test_provenance_fixture_integrity():
    prov = _provenance()
    prof = prov["profile"]
    assert prof["client_module_id"] == "opencode-1.19.3-chat-v1"
    assert prof["client_module_version"] == "1"
    assert prof["client_version"] == "1.19.3"
    assert prof["source_tag"] == PINNED_SOURCE_TAG
    assert prof["source_commit"] == PINNED_SOURCE_COMMIT
    assert prof["executable_sha256"] == PINNED_EXECUTABLE_SHA256
    assert prof["chat_provider_package"] == "@ai-sdk/openai-compatible 2.0.41"
    assert prof["ai_sdk_version"] == "6.0.168"
    assert prof["observed_user_agent"].startswith("opencode/1.19.3 ")
    env = prov["capture_environment"]
    assert env["user_saved_profiles_touched"] is False
    assert env["user_credentials_read"] is False
    assert env["production_provider_key_used"] is False
    labels = {v["label"] for v in env["config_variants"]}
    assert labels == {"task-default", "denied-web-baseline"}
    assert prov["privacy"]["raw_content_retained"] is False
    assert prov["privacy"]["provider_call_performed"] is False
    assert "webfetch" in prof["vocabulary_decision"]


def test_all_structural_fixtures_present_and_private():
    for name in STRUCTURAL_FIXTURES:
        data = _load(name)
        priv = data["privacy"]
        assert priv["raw_content_retained"] is False, name
        assert priv["provider_call_performed"] is False, name
    prov_priv = _provenance()["privacy"]
    assert prov_priv["raw_ids_retained"] is False


def test_structural_fixture_digest_binding():
    prov = _provenance()
    assert prov["structural_fixture_digest_rule"].startswith("sha256 over")
    h = hashlib.sha256()
    for name in sorted(p.name for p in FIXTURE_DIR.glob("structural_*.json")):
        h.update(name.encode() + b"\0" + (FIXTURE_DIR / name).read_bytes())
    assert h.hexdigest() == prov["structural_fixture_sha256"]


# -- structural capture facts -------------------------------------------------

def test_text_stream_envelope_facts():
    data = _load("structural_text_stream.json")
    req = data["request"]
    assert req["top_level_field_count"] == 9
    fields = {f["name"]: f for f in req["top_level_fields"]}
    assert set(fields) == {"model", "max_tokens", "store", "reasoning_effort",
                           "messages", "tools", "tool_choice", "stream", "stream_options"}
    assert fields["reasoning_effort"]["observed"] == "xhigh"
    assert "PROVEN DIFFERENCE" in fields["reasoning_effort"]["note"]
    assert fields["max_tokens"]["observed"] == 32000
    assert fields["store"]["observed"] is False
    assert fields["stream"]["observed"] is True
    assert fields["stream_options"]["observed"] == {"include_usage": True}
    assert fields["tool_choice"]["observed"] == "auto"
    decl = req["tool_declarations"]
    assert decl["form"] == "nested"
    assert decl["counts_by_type"] == {"function": 9}
    assert decl["baseline_vocabulary_9"] == BASELINE_VOCABULARY
    assert decl["strict_key_state"] == "absent"
    assert decl["observed_extension_when_webfetch_not_denied"] == ["webfetch"]
    assert data["client_behavior"]["always_streams_in_run_mode"] is True
    assert data["client_behavior"]["nonstreaming_chat_observed"] is False


def test_toolloop_gate_and_read_wrap_facts():
    data = _load("structural_toolloop.json")
    gate = data["verification_gate"]
    assert gate["exact_result_roundtrip"].startswith("final client text equals")
    assert gate["result"].startswith("verified")
    read = data["read_tool"]
    assert read["declared_argument_keys"] == ["filePath"]
    wrap = read["native_output_wrap"]
    assert wrap["content_is_raw_file_bytes"] is False
    assert wrap["envelope_lines_observed"] == 7
    assert wrap["marker_occurrences_in_output"] == 1
    assert wrap["marker_at_content_start"] is False
    assert wrap["envelope_overhead_bytes_for_46_byte_single_line_file_same_path"] == 138
    assert data["tool_call_issuance"]["finish_reason"] == "tool_calls"


def test_multicall_facts():
    data = _load("structural_multicall.json")
    assert data["issuance"]["calls_in_one_response"] == 2
    assert data["issuance"]["call_ids_distinct"] is True
    assert data["continuation"]["assistant_tool_calls_replayed"] == 2
    assert data["continuation"]["tool_call_ids_match_issued"] is True
    assert data["verification_gate"]["all_calls_verified"] is True
    assert data["verification_gate"]["final_text_source"].startswith("correlated_tool_result")


def test_title_aux_classification_facts():
    data = _load("structural_title_aux.json")
    aux = data["aux_request"]
    assert aux["top_level_field_count"] == 7
    assert aux["fields_absent_vs_main"] == ["tools", "tool_choice"]
    assert data["explicit_title_suppresses"] is True
    assert "must not consume the main turn counter" in data["classification_rule"]


def test_compaction_template_facts():
    data = _load("structural_compaction.json")
    cfg = data["configuration"]
    assert cfg["limit"] == {"context": 4096, "input": 2048, "output": 256}
    assert cfg["compaction"] == {"reserved": 256}
    assert "limit.input - compaction.reserved" in cfg["trigger_arithmetic"]
    usage = cfg["reported_usage_that_triggered"]
    assert usage["total_tokens"] == 2000 and 2000 >= 2048 - 256
    summ = data["summarization_request"]
    assert summ["fields_absent_vs_main"] == ["tools", "tool_choice"]
    tmpl = data["compacted_context_template"]
    assert tmpl["messages"][0] == {"role": "user", "content": "What did we do so far?"}
    assert tmpl["messages"][1] == {"role": "assistant", "content": "<summary from summarization response>"}
    assert tmpl["messages"][2]["content"].startswith("Continue if you have next steps")
    assert tmpl["system"].startswith("unchanged original")
    assert data["persistence"].startswith("compacted context persists")
    assert data["verification_gate"]["result"].startswith("verified")


def test_reasoning_facts():
    data = _load("structural_reasoning.json")
    resp = data["response_side"]
    assert resp["delta_field_observed"].startswith("choices[0].delta.reasoning_content")
    assert resp["accepted_without_error"] is True
    assert resp["surface_default_run"].startswith("no reasoning part")
    assert "one reasoning part" in resp["surface_with_thinking_flag"]


def test_session_identity_predicates():
    data = _load("structural_session_identity.json")
    assert data["experiment"]["A2"].startswith("explicit resume")
    hdr = data["candidate_fields"]["headers"]
    assert hdr["format"] == "ses_[A-Za-z0-9]{26}"
    assert hdr["per_request_three_values_equal"] is True
    pred = data["predicates"]
    assert pred["A1_equals_A2"] is True
    assert pred["A1_distinct_from_B1"] is True
    assert pred["suitable_as_transient_session_hint"] is True
    assert pred["rejected_as_authority"] is True


def test_max_tokens_cap_relation():
    text = _load("structural_text_stream.json")
    observed = text["request"]["top_level_fields"][
        [f["name"] for f in text["request"]["top_level_fields"]].index("max_tokens")
    ]["observed"]
    assert observed == 32000


# -- packaged profile DATA (schema_version 1, shared loader) ------------------

def test_profile_data_schema():
    data = load_agent_chat_profile_file(PROFILE_PATH)
    assert data.schema_version == 1
    assert data.profile_id == "opencode-1.19.3-chat-v1"
    assert data.version == "1"
    c = data.client
    assert c.name == "opencode"
    assert c.distribution_version == "1.19.3"
    assert c.source_tag == PINNED_SOURCE_TAG
    assert c.source_commit == PINNED_SOURCE_COMMIT
    assert c.sdk_name == "@ai-sdk/openai-compatible"
    assert c.sdk_version == "2.0.41"
    assert c.wire_api == "chat_completions"
    assert data.reasoning_efforts == frozenset(
        {"minimal", "low", "medium", "high", "xhigh"}
    )
    assert {f.name for f in data.assistant_message_fields} == {
        "reasoning", "reasoning_content"}
    assert all(f.max_bytes == 65536 for f in data.assistant_message_fields)
    assert data.tools.names == frozenset(BASELINE_VOCABULARY)
    assert data.tools.max_declarations == 32
    assert data.tools.max_description_bytes == 20000
    assert data.tools.max_schema_depth == 8
    assert data.tools.max_schema_properties == 64
    assert data.tools.max_declaration_bytes == 65536
    assert (data.tool_call.id_min_length, data.tool_call.id_max_length) == (1, 128)
    assert data.tool_call.arguments_max_bytes == 65536


def test_profile_digest_binding_and_immutability():
    data = load_agent_chat_profile_file(PROFILE_PATH)
    assert data.fixture_sha256 == canonical_profile_digest(data.document)
    prov = _provenance()
    prof = prov["profile"]
    assert prof["packaged_profile_digest"] == data.fixture_sha256
    assert prof["packaged_profile_digest_rule"].startswith("canonical_profile_digest")
    # deep-frozen document: no mutable surface
    with pytest.raises(TypeError):
        data.document["id"] = "opencode-1.19.3-chat-v1"
    with pytest.raises(AttributeError):
        data.profile_id = "other"


def test_tool_vocabulary_consistency_between_profile_and_fixtures():
    data = load_agent_chat_profile_file(PROFILE_PATH)
    text = _load("structural_text_stream.json")
    decl = text["request"]["tool_declarations"]
    assert set(data.tools.names) == set(decl["baseline_vocabulary_9"])
    assert "webfetch" not in data.tools.names
    assert decl["observed_extension_when_webfetch_not_denied"] == ["webfetch"]


# -- thin module: identity and static registration ----------------------------

def test_module_identity_and_registration():
    mod = oc.OPENCODE_1193_CHAT_CLIENT_MODULE
    assert mod.module_id == "opencode-1.19.3-chat-v1"
    assert mod.module_version == "1"
    assert mod.fixture_sha256 == oc.OPENCODE_1193_CHAT_PROFILE_DATA.fixture_sha256
    assert get_agent_chat_client_module("opencode-1.19.3-chat-v1") is mod
    assert agent_chat_profile_metadata(mod) == {
        "id": "opencode-1.19.3-chat-v1",
        "version": "1",
        "fixture_sha256": mod.fixture_sha256,
    }


def test_observed_envelope_accepted_with_xhigh():
    body = {
        "model": "agent-chat-fake-model",
        "max_tokens": 32000,
        "store": False,
        "reasoning_effort": "xhigh",
        "messages": [
            {"role": "system", "content": "agent instruction prompt"},
            {"role": "user", "content": "hello"},
        ],
        "tools": [
            {"type": "function",
             "function": {"name": name, "description": f"desc {name}",
                          "parameters": {"type": "object",
                                         "properties": {"filePath": {"type": "string"}}}}}
            for name in BASELINE_VOCABULARY
        ],
        "tool_choice": "auto",
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    snapshot = copy.deepcopy(body)
    result = oc.OPENCODE_1193_CHAT_CLIENT_MODULE.normalize(
        AGENT_CHAT_ENDPOINT, body)
    assert body == snapshot  # caller input untouched
    assert result.endpoint == AGENT_CHAT_ENDPOINT
    assert result.body == snapshot  # body preserved exactly
    assert result.module_id == "opencode-1.19.3-chat-v1"
    assert result.module_version == "1"


def test_observed_tool_continuation_accepted():
    call_id = "call_" + "a" * 29  # observed length 34
    body = {
        "model": "m",
        "max_tokens": 32000,
        "store": False,
        "reasoning_effort": "xhigh",
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "read probe.txt"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": call_id, "type": "function",
                 "function": {"name": "read",
                              "arguments": "{\"filePath\":\"probe.txt\"}"}},
            ]},
            {"role": "tool", "tool_call_id": call_id, "content": "wrapped result"},
        ],
        "tools": [
            {"type": "function",
             "function": {"name": "read", "description": "read a file",
                          "parameters": {"type": "object",
                                         "properties": {"filePath": {"type": "string"}}}}},
        ],
        "tool_choice": "auto",
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    oc.OPENCODE_1193_CHAT_CLIENT_MODULE.normalize(AGENT_CHAT_ENDPOINT, body)


def test_assistant_reasoning_fields_and_null_content():
    body = {
        "model": "m",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None,
             "reasoning_content": "thinking", "reasoning": "more",
             "tool_calls": [
                 {"id": "call_x", "type": "function",
                  "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call_x", "content": "ok"},
        ],
    }
    oc.OPENCODE_1193_CHAT_CLIENT_MODULE.normalize(AGENT_CHAT_ENDPOINT, body)
    bad = copy.deepcopy(body)
    bad["messages"][1]["reasoning_content"] = 42
    with pytest.raises(AgentChatRequestError) as exc:
        oc.OPENCODE_1193_CHAT_CLIENT_MODULE.normalize(AGENT_CHAT_ENDPOINT, bad)
    assert exc.value.error_code == "agent_chat_message_field_invalid"


def test_fail_closed_rejections():
    mod = oc.OPENCODE_1193_CHAT_CLIENT_MODULE
    base = {
        "model": "m",
        "reasoning_effort": "xhigh",
        "messages": [{"role": "user", "content": "hi"}],
    }

    def expect(body, code):
        with pytest.raises(AgentChatRequestError) as exc:
            mod.normalize(AGENT_CHAT_ENDPOINT, body)
        assert exc.value.error_code == code

    unknown_top = copy.deepcopy(base)
    unknown_top["include"] = True
    expect(unknown_top, "agent_chat_unknown_field")

    bad_effort = copy.deepcopy(base)
    bad_effort["reasoning_effort"] = "max"
    expect(bad_effort, "agent_chat_reasoning_effort_not_allowed")

    webfetch = copy.deepcopy(base)
    webfetch["tools"] = [
        {"type": "function",
         "function": {"name": "webfetch", "description": "d",
                      "parameters": {"type": "object"}}}]
    expect(webfetch, "agent_chat_tool_name_not_allowed")

    legacy = copy.deepcopy(base)
    legacy["functions"] = []
    expect(legacy, "agent_chat_legacy_functions_not_allowed")

    dangling = copy.deepcopy(base)
    dangling["messages"].append(
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_d", "type": "function",
             "function": {"name": "read", "arguments": "{}"}}]})
    expect(dangling, "agent_chat_tool_call_unresolved")

    unlinked = copy.deepcopy(base)
    unlinked["messages"].append(
        {"role": "tool", "tool_call_id": "call_none", "content": "x"})
    expect(unlinked, "agent_chat_tool_result_not_linked")

    dup_result = copy.deepcopy(base)
    dup_result["messages"].extend([
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_r", "type": "function",
             "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_r", "content": "a"},
        {"role": "tool", "tool_call_id": "call_r", "content": "b"},
    ])
    expect(dup_result, "agent_chat_tool_result_duplicate")

    bad_id = copy.deepcopy(base)
    bad_id["messages"].extend([
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "x" * 129, "type": "function",
             "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "x" * 129, "content": "a"},
    ])
    expect(bad_id, "agent_chat_tool_call_id_invalid")


def test_non_chat_endpoint_fails_closed():
    mod = oc.OPENCODE_1193_CHAT_CLIENT_MODULE
    with pytest.raises(AgentChatModuleSelectionError) as exc:
        mod.normalize("/v1/responses", {"model": "m"})
    assert exc.value.error_code == "unsupported_client_endpoint"


def test_side_effect_free_decoder():
    mod = oc.OPENCODE_1193_CHAT_CLIENT_MODULE
    body = {
        "model": "m", "max_tokens": 32000, "store": False,
        "reasoning_effort": "xhigh",
        "messages": [{"role": "user", "content": "canary-not-a-secret"}],
        "tools": [], "tool_choice": "auto", "stream": True,
        "stream_options": {"include_usage": True},
    }
    snapshot = copy.deepcopy(body)
    for _ in range(3):
        mod.normalize(AGENT_CHAT_ENDPOINT, body)
    assert body == snapshot


# -- server-side pin resolution ------------------------------------------------

def test_pin_resolution():
    good = agent_chat_profile_metadata(oc.OPENCODE_1193_CHAT_CLIENT_MODULE)
    assert resolve_chat_client_module(None) is None
    assert resolve_chat_client_module(dict(good)) is oc.OPENCODE_1193_CHAT_CLIENT_MODULE
    stale = dict(good, version="99")
    with pytest.raises(AgentChatModuleSelectionError) as exc:
        resolve_chat_client_module(stale)
    assert exc.value.error_code == "chat_client_module_fixture_mismatch"
    wrong_digest = dict(good, fixture_sha256="0" * 64)
    with pytest.raises(AgentChatModuleSelectionError) as exc:
        resolve_chat_client_module(wrong_digest)
    assert exc.value.error_code == "chat_client_module_fixture_mismatch"
    extra_key = dict(good, extra=1)
    with pytest.raises(AgentChatModuleSelectionError) as exc:
        resolve_chat_client_module(extra_key)
    assert exc.value.error_code == "chat_client_module_metadata_invalid"
    unknown_id = dict(good, id="not-a-registered-chat-module-v1")
    with pytest.raises(AgentChatModuleSelectionError) as exc:
        resolve_chat_client_module(unknown_id)
    assert exc.value.error_code == "unsupported_client_module"


# -- harness scripts ------------------------------------------------------------

def test_harness_scripts_present_and_compile():
    fake = ROOT / "scripts" / "verify_agent_chat" / "loopback_chat_fake.py"
    verifier = ROOT / "scripts" / "verify_agent_chat" / "verify_opencode_chat_capture.py"
    assert fake.is_file() and verifier.is_file()
    ast.parse(fake.read_text())
    ast.parse(verifier.read_text())
    src = fake.read_text()
    assert "127.0.0.1" in src
    assert "threading.RLock()" in src
    vsrc = verifier.read_text()
    assert PINNED_EXECUTABLE_SHA256 in vsrc
    assert "secrets.token_hex(16)" in vsrc
