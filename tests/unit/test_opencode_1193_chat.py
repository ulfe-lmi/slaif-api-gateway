"""Unit tests for the OpenCode 1.19.3 Chat profile data and structural fixtures.

These tests are independent of the primary neutral Chat engine checkpoint:
they pin the reviewed DATA (profile file + structural fixtures) that the
thin decoder will later consume. The guarded decoder tests at the bottom
activate only once modules/clients/opencode_1193_chat.py is implemented.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "opencode" / "1.19.3" / "chat"
PROFILE_PATH = (ROOT / "app" / "slaif_gateway" / "modules" / "clients" / "profiles"
                / "opencode-1.19.3-chat.json")

PINNED_EXECUTABLE_SHA256 = "179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9"
BASELINE_VOCABULARY = ["bash", "edit", "glob", "grep", "read", "skill", "task", "todowrite", "write"]

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


def _profile():
    return json.loads(PROFILE_PATH.read_text())


def test_provenance_fixture_integrity():
    prov = _load("provenance.json")
    prof = prov["profile"]
    assert prof["client_module_id"] == "opencode-1.19.3-chat-v1"
    assert prof["client_module_version"] == "1"
    assert prof["client_version"] == "1.19.3"
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


def test_all_structural_fixtures_present_and_private():
    for name in STRUCTURAL_FIXTURES:
        data = _load(name)
        priv = data["privacy"]
        assert priv["raw_content_retained"] is False, name
        assert priv["provider_call_performed"] is False, name
    prov_priv = _load("provenance.json")["privacy"]
    assert prov_priv["raw_content_retained"] is False
    assert prov_priv["raw_ids_retained"] is False


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


def test_profile_data_schema():
    prof = _profile()
    assert prof["schema_version"] == 2
    assert prof["profile_kind"] == "agent_chat"
    assert prof["module_id"] == "opencode-1.19.3-chat-v1"
    assert prof["module_version"] == "1"
    assert prof["endpoint"] == "/v1/chat/completions"
    assert prof["provenance"]["executable_sha256"] == PINNED_EXECUTABLE_SHA256
    env = prof["envelope"]["top_level_fields"]
    assert env["reasoning_effort"]["allowed"] == ["minimal", "low", "medium", "high", "xhigh"]
    assert prof["envelope"]["unknown_top_level_fields"] == "fail_closed"
    assert prof["tools"]["baseline_vocabulary"] == BASELINE_VOCABULARY
    assert prof["tools"]["vocabulary_is_configuration_dependent"] is True
    assert prof["known_tool_arguments"]["read"]["filePath"]["type"] == "string"
    assert prof["session_hints"]["headers"]["x-opencode-session-id"]["equals"] == "x-session-id"
    assert prof["session_hints"]["predicates"]["rejected_as_authority"] is True


def test_tool_vocabulary_consistency_between_profile_and_fixtures():
    prof = _profile()
    text = _load("structural_text_stream.json")
    decl = text["request"]["tool_declarations"]
    assert prof["tools"]["baseline_vocabulary"] == decl["baseline_vocabulary_9"]
    ext = prof["tools"]["observed_configuration_extensions"]
    assert list(ext) == decl["observed_extension_when_webfetch_not_denied"]


def test_fixture_digest_binding():
    prof = _profile()
    h = hashlib.sha256()
    for name in sorted(p.name for p in FIXTURE_DIR.glob("structural_*.json")):
        data = (FIXTURE_DIR / name).read_bytes()
        h.update(name.encode() + b"\0" + data)
    assert h.hexdigest() == prof["fixture_sha256"]
    assert prof["fixture_digest_rule"].startswith("sha256 over")


def test_max_tokens_cap_relation():
    prof = _profile()
    text = _load("structural_text_stream.json")
    observed = text["request"]["top_level_fields"][
        [f["name"] for f in text["request"]["top_level_fields"]].index("max_tokens")
    ]["observed"]
    assert observed == prof["limits"]["max_tokens_observed"] == 32000
    configured = prof["limits"]["configured_output_limit_reference"]
    assert observed < configured  # runtime cap below configured limit.output


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


# -- guarded decoder tests (activate once the module exists) ---------------

def _try_decoder():
    try:
        return importlib.import_module("slaif_gateway.modules.clients.opencode_1193_chat")
    except Exception:
        return None


def test_decoder_protocol_conformance():
    mod = _try_decoder()
    if mod is None:
        pytest.skip("decoder module not yet implemented (pending primary neutral checkpoint)")
    cls = mod.OpenCode1193ChatClientModule if hasattr(mod, "OpenCode1193ChatClientModule") else None
    if cls is None:
        pytest.skip("decoder module exists but no client module class found")
    inst = cls()
    assert inst.module_id == "opencode-1.19.3-chat-v1"
    assert inst.module_version == "1"
    assert inst.fixture_sha256 == _profile()["fixture_sha256"]


def test_decoder_side_effect_free_and_canary():
    mod = _try_decoder()
    if mod is None:
        pytest.skip("decoder module not yet implemented (pending primary neutral checkpoint)")
    cls = getattr(mod, "OpenCode1193ChatClientModule", None)
    if cls is None:
        pytest.skip("decoder module exists but no client module class found")
    inst = cls()
    body = {
        "model": "m", "max_tokens": 32000, "store": False,
        "reasoning_effort": "xhigh",
        "messages": [{"role": "user", "content": "canary-not-a-secret"}],
        "tools": [], "tool_choice": "auto", "stream": True,
        "stream_options": {"include_usage": True},
    }
    snapshot = json.loads(json.dumps(body))
    inst.normalize("/v1/chat/completions", body)
    assert body == snapshot  # no mutation of caller input
