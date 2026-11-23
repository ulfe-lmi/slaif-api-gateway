"""Unit tests for the OpenCode 1.19.3 Responses capture fixtures.

Fixtures/structure only:
- the sanitized structural capture fixtures, their privacy invariants, and
  their digest binding against provenance.json;
- per-fixture wire facts (contract fields, SSE sequences, tool-loop and
  encrypted-reasoning replay shapes, session-hint predicates);
- presence/compile sanity of the loopback fake and verifier scripts.

No provider, no network, no native binary invocation. The Responses profile
module and packaged DATA do not exist yet (primary owns packaging), so this
test imports no slaif_gateway module: stdlib + pytest only.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "opencode" / "1.19.3" / "responses"

PINNED_EXECUTABLE_SHA256 = "179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9"
PINNED_SOURCE_TAG = "v1.19.3"
PINNED_SOURCE_COMMIT = "e3c4eb242585dcd77be1a867391b7c25fd47ce52"
BASELINE_VOCABULARY = ["bash", "edit", "glob", "grep", "read", "skill", "task",
                       "todowrite", "write"]
STRUCTURAL_FIXTURES = [
    "structural_text_stream.json",
    "structural_toolloop.json",
    "structural_reasoning_replay.json",
    "structural_session_identity.json",
]
NINE_FIELDS = ["include", "input", "max_output_tokens", "model", "reasoning",
               "store", "stream", "tool_choice", "tools"]


def _load(name: str):
    return json.loads((FIXTURE_DIR / name).read_text())


def _provenance():
    return _load("provenance.json")


# -- provenance and fixture integrity ---------------------------------------

def test_provenance_fixture_integrity():
    prov = _provenance()
    prof = prov["profile"]
    assert prof["client_module_id"] == "opencode-1.19.3-responses-v1"
    assert prof["client_module_version"] == "1"
    assert prof["client_version"] == "1.19.3"
    assert prof["source_tag"] == PINNED_SOURCE_TAG
    assert prof["source_commit"] == PINNED_SOURCE_COMMIT
    assert prof["executable_sha256"] == PINNED_EXECUTABLE_SHA256
    assert prof["responses_provider_package"].startswith("@ai-sdk/openai ")
    assert "3.0.88" in prof["responses_provider_package"]
    assert "3.0.84" in prof["responses_provider_package"]
    assert "no runtime npm install" in prof["responses_provider_package"]
    assert prof["ai_sdk_version"] == "6.0.168"
    assert prof["wire_api"] == "responses"
    assert prof["observed_user_agent"].startswith("opencode/1.19.3")
    assert prof["packaged_profile_digest"] is None
    assert "pending" in prof["packaged_profile_digest_state"]
    env = prov["capture_environment"]
    assert env["captured_utc_date"] == "2026-11-23"
    assert env["user_saved_profiles_touched"] is False
    assert env["user_credentials_read"] is False
    assert env["production_provider_key_used"] is False
    labels = {v["label"] for v in env["config_variants"]}
    assert labels == {"denied-web-baseline"}
    for key in ("raw_content_retained", "provider_call_performed",
                "raw_ids_retained", "credentials_retained",
                "home_workspace_paths_retained"):
        assert prov["privacy"][key] is False
    assert "webfetch" in prof["vocabulary_decision"]


def test_all_structural_fixtures_present_and_private():
    names = sorted(p.name for p in FIXTURE_DIR.glob("structural_*.json"))
    assert names == sorted(STRUCTURAL_FIXTURES)
    for name in STRUCTURAL_FIXTURES:
        data = _load(name)
        priv = data["privacy"]
        assert priv["raw_content_retained"] is False, name
        assert priv["provider_call_performed"] is False, name
    blob = b"".join((FIXTURE_DIR / n).read_bytes() for n in names)
    blob += (FIXTURE_DIR / "provenance.json").read_bytes()
    assert b"Bearer sk" not in blob


def test_structural_fixture_digest_binding():
    prov = _provenance()
    assert prov["structural_fixture_digest_rule"].startswith("sha256 over")
    h = hashlib.sha256()
    for name in sorted(p.name for p in FIXTURE_DIR.glob("structural_*.json")):
        h.update(name.encode() + b"\0" + (FIXTURE_DIR / name).read_bytes())
    assert h.hexdigest() == prov["structural_fixture_sha256"]


# -- structural capture facts -------------------------------------------------

def _assert_contract(req):
    cf = req["contract_facts"]
    assert cf["max_output_tokens"]["observed"] == 32000
    assert cf["store"]["observed"] is False
    assert cf["stream"]["observed"] is True
    assert cf["tool_choice"]["observed"] == "auto"
    assert cf["include"]["observed"] == ["reasoning.encrypted_content"]
    assert cf["reasoning"]["observed"] == {"effort": "xhigh"}
    assert req["tools_count"] == 9


def test_text_stream_envelope_facts():
    data = _load("structural_text_stream.json")
    assert data["endpoint"] == "POST /v1/responses"
    fields = [f["name"] for f in data["request"]["top_level_fields"]]
    assert fields == sorted(NINE_FIELDS)
    assert data["request"]["top_level_field_count"] == 9
    _assert_contract(data["request"])
    decl = data["request"]["tool_declarations"]
    assert decl["form"] == "flat"
    assert decl["strict_key_state"] == "present_true_on_all_9"
    assert decl["counts_by_type"] == {"function": 9}
    assert decl["baseline_vocabulary_9"] == BASELINE_VOCABULARY
    items = data["request"]["input_items"]
    assert [i["role"] for i in items] == ["developer", "user"]
    assert all(i["type_key_state"] == "absent" and i["id_state"] == "absent"
               and i["status_state"] == "absent" for i in items)
    resp = data["response"]
    assert resp["event_sequence_observed"] == [
        "response.created",
        "response.output_item.added",
        "response.output_text.delta",
        "response.output_item.done",
        "response.completed",
    ]
    assert resp["usage_fields"] == ["input_tokens", "output_tokens", "total_tokens"]
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["final_text_exact_match"] is True
    assert beh["nonstreaming_responses_observed"] is False
    assert beh["elapsed_s"] == 5.978


def test_toolloop_wire_facts():
    data = _load("structural_toolloop.json")
    _assert_contract(data["request_turn_1"])
    cont = data["request_turn_2_continuation"]
    assert cont["input_item_count"] == 4
    added = {i["type"]: i for i in cont["appended_items"]}
    assert set(added) == {"function_call", "function_call_output"}
    assert added["function_call"]["keys_sorted"] == [
        "arguments", "call_id", "name", "type"]
    assert added["function_call"]["id_state"] == "absent"
    assert added["function_call"]["status_state"] == "absent"
    assert added["function_call_output"]["keys_sorted"] == [
        "call_id", "output", "type"]
    assert added["function_call_output"]["id_state"] == "absent"
    assert cont["call_id_replayed"] is True
    wrap = data["read_tool"]["native_output_wrap"]
    assert wrap["marker_present"] is True
    assert wrap["marker_occurrences_in_output"] == 1
    assert wrap["content_byte_length"] == 192
    assert wrap["marker_byte_length"] == 38
    assert wrap["content_equals_marker"] is False
    gate = data["verification_gate"]
    assert gate["result"] == "verified"
    assert gate["final_text_source"] == "correlated_tool_result"
    assert gate["final_text_length"] == 38
    assert data["session"]["stable_across_two_requests"] is True
    assert data["session"]["session_value_sha256_8"] == "2ee98e47"
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["elapsed_s"] == 5.53


def test_reasoning_replay_wire_facts():
    data = _load("structural_reasoning_replay.json")
    _assert_contract(data["request_turn_1"])
    seq = data["response_turn_1"]["event_sequence_observed"]
    assert seq == [
        "response.created",
        "response.output_item.added",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_part.done",
        "response.output_item.done",
        "response.output_item.added",
        "response.output_item.done",
        "response.completed",
    ]
    cont = data["request_turn_2_continuation"]
    assert cont["input_item_count"] == 5
    assert cont["input_item_types"] == [
        None, None, "reasoning", "function_call", "function_call_output"]
    added = {i["type"]: i for i in cont["appended_items"]}
    ri = added["reasoning"]
    assert ri["keys_sorted"] == ["encrypted_content", "summary", "type"]
    assert ri["id_state"] == "absent"
    assert ri["status_state"] == "absent"
    assert ri["encrypted_byte_length"] == 64
    assert ri["encrypted_sha256_8"] == "f2719d31"
    assert ri["full_byte_equals_issued"] is True
    assert added["function_call"]["name"] == "read"
    assert added["function_call"]["id_state"] == "absent"
    assert added["function_call_output"]["id_state"] == "absent"
    assert cont["issued_call_id_correlated"] is True
    assert data["session"]["stable_across_two_requests"] is True
    assert data["session"]["session_value_sha256_8"] == "760705ef"
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["final_text_exact"] is True
    assert beh["elapsed_s"] == 5.578


def test_session_identity_predicates():
    data = _load("structural_session_identity.json")
    cf = data["candidate_fields"]
    assert cf["names"] == ["x-opencode-session-id", "x-session-affinity",
                           "x-session-id"]
    assert cf["three_values_equal_per_request"] is True
    assert cf["value_retention"].startswith("sha256_8 only")
    exp = data["experiments"]
    assert exp["A"]["requests"]["A1"] == exp["A"]["requests"]["A2"]
    assert exp["A"]["requests"]["A1"]["session_value_sha256_8"] == "2ee98e47"
    assert exp["B"]["requests"]["B1"]["session_value_sha256_8"] == "760705ef"
    assert exp["C"]["requests"]["C1"]["session_value_sha256_8"] == "74551a8e"
    pred = data["predicates"]
    assert pred["A1_equals_A2"] is True
    assert pred["A1_distinct_from_B1"] is True
    assert pred["distinct_across_all_probes"] is True
    assert pred["suitable_as_transient_session_hint"] is True
    assert pred["rejected_as_authority"] is True


# -- harness scripts ------------------------------------------------------------

def test_harness_scripts_present_and_compile():
    fake = ROOT / "scripts" / "verify_agent_chat" / "loopback_responses_fake.py"
    verifier = ROOT / "scripts" / "verify_agent_chat" / "verify_opencode_responses_capture.py"
    assert fake.is_file() and verifier.is_file()
    ast.parse(fake.read_text())
    ast.parse(verifier.read_text())
    src = fake.read_text()
    assert "127.0.0.1" in src
    assert "uuid.uuid4().hex" in src
    vsrc = verifier.read_text()
    assert PINNED_EXECUTABLE_SHA256 in vsrc
    assert "@ai-sdk/openai" in vsrc


# -- pure encrypted-replay gate (verify_reasoning_replay) -------------------

_ISSUED_ENC = "a1b2c3d4e5" * 8  # 64 synthetic chars, never a real cipher


def _load_verifier_module():
    p = (ROOT / "scripts" / "verify_agent_chat"
         / "verify_opencode_responses_capture.py")
    spec = importlib.util.spec_from_file_location(
        "verify_opencode_responses_capture", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _issued(call_id="call_synthetic_1", tool_name="read",
            encrypted=_ISSUED_ENC):
    return {"call_id": call_id, "tool_name": tool_name,
            "encrypted_sha256_8": "deadbeef",
            "encrypted_byte_length": len(encrypted),
            "encrypted_content_issued": encrypted}


def _items(encrypted=_ISSUED_ENC, call_id="call_synthetic_1",
           fc_name="read", out_call_id="call_synthetic_1"):
    items = [{"role": "developer", "content": "x"},
             {"role": "user", "content": [{"type": "input_text", "text": "x"}]}]
    if encrypted is not None:
        items.append({"type": "reasoning", "encrypted_content": encrypted})
    items.append({"type": "function_call", "call_id": call_id,
                  "name": fc_name, "arguments": "{}"})
    items.append({"type": "function_call_output", "call_id": out_call_id,
                  "output": "x"})
    return items


def test_replay_gate_positive():
    mod = _load_verifier_module()
    r = mod.verify_reasoning_replay(_issued(), _items())
    assert r["pass"] is True
    assert r["encrypted_replay_verified"] is True
    assert r["call_linkage_exact"] is True
    assert r["reasoning_item_count"] == 1
    assert r["reasoning_items"][0]["full_equals_issued"] is True
    assert r["issued_call_id_present"] is True
    assert r["issued_encrypted_content_present"] is True
    assert _ISSUED_ENC not in json.dumps(r)  # raw bytes never emitted


def test_replay_gate_missing_cipher_fails():
    mod = _load_verifier_module()
    r = mod.verify_reasoning_replay(_issued(), _items(encrypted=None))
    assert r["encrypted_replay_verified"] is False
    assert r["pass"] is False


def test_replay_gate_changed_cipher_fails():
    mod = _load_verifier_module()
    enc = _ISSUED_ENC[:-1] + ("0" if _ISSUED_ENC[-1] != "0" else "1")
    r = mod.verify_reasoning_replay(_issued(), _items(encrypted=enc))
    assert r["reasoning_items"][0]["full_equals_issued"] is False
    assert r["pass"] is False
    assert "equals_issued" not in r["reasoning_items"][0]


def test_replay_gate_wrong_linkage_fails():
    mod = _load_verifier_module()
    r = mod.verify_reasoning_replay(_issued(), _items(out_call_id="call_other"))
    assert r["call_linkage_exact"] is False
    assert r["encrypted_replay_verified"] is True
    assert r["pass"] is False
    r2 = mod.verify_reasoning_replay(_issued(), _items(fc_name="write"))
    assert r2["call_linkage_exact"] is False
    assert r2["pass"] is False


def test_replay_gate_empty_issued_fails_closed():
    mod = _load_verifier_module()
    r = mod.verify_reasoning_replay({}, _items())
    assert r["issued_call_id_present"] is False
    assert r["issued_encrypted_content_present"] is False
    assert r["encrypted_replay_verified"] is False
    assert r["call_linkage_exact"] is False
    assert r["pass"] is False
