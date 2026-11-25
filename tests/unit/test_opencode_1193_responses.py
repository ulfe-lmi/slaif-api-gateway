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
    "structural_assistant_tool.json",
    "structural_defaulttitle.json",
    "structural_reasoning_visible.json",
    "structural_compaction.json",
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
    assert env["captured_utc_date"] == "2026-11-24"
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
    # presence only: the capture verifier never recorded the strict value
    assert decl["strict_key_state"] == "present_value_not_recorded"
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
    assert resp["event_envelope_keys"] == ["type", "sequence_number", "<per-event fields>"]
    assert "response_id" not in resp["event_envelope_keys"]
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["final_text_exact_match"] is True
    assert beh["nonstreaming_responses_observed"] is False
    assert beh["elapsed_s"] == 5.828


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
    assert data["session"]["session_value_sha256_8"] == "9c20a369"
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["elapsed_s"] == 5.578


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
    assert ri["encrypted_sha256_8"] == "d1c28cd0"
    assert ri["full_byte_equals_issued"] is True
    assert added["function_call"]["name"] == "read"
    assert added["function_call"]["id_state"] == "absent"
    assert added["function_call_output"]["id_state"] == "absent"
    assert cont["issued_call_id_correlated"] is True
    assert data["session"]["stable_across_two_requests"] is True
    assert data["session"]["session_value_sha256_8"] == "080846e0"
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["final_text_exact"] is True
    assert beh["elapsed_s"] == 5.581


def test_session_identity_predicates():
    data = _load("structural_session_identity.json")
    cf = data["candidate_fields"]
    assert cf["names"] == ["x-opencode-session-id", "x-session-affinity",
                           "x-session-id"]
    assert cf["three_values_equal_per_request"] is True
    assert cf["value_retention"].startswith("sha256_8 only")
    exp = data["experiments"]
    assert exp["A"]["requests"]["A1"] == exp["A"]["requests"]["A2"]
    assert exp["A"]["requests"]["A1"]["session_value_sha256_8"] == "9c20a369"
    assert exp["B"]["requests"]["B1"]["session_value_sha256_8"] == "080846e0"
    assert exp["C"]["requests"]["C1"]["session_value_sha256_8"] == "b728f8db"
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


def test_assistant_tool_continuation_facts():
    data = _load("structural_assistant_tool.json")
    _assert_contract(data["request_turn_1"])
    issue = data["tool_call_issuance"]
    assert issue["output_slot_assignment"] == {"assistant_text_message": 0,
                                               "function_call": 1}
    assert issue["done_item_status"] == "completed"
    assert issue["call_id_correlated_to_result"] is True
    cont = data["request_turn_2_continuation"]
    assert cont["input_item_count"] == 5
    assert cont["input_item_types"] == [None, None, None,
                                        "function_call", "function_call_output"]
    obs = data["assistant_message_observation"]
    assert obs["assistant_message_count"] == 1
    item = obs["assistant_message_items"][0]
    assert item["type"] is None
    assert item["keys_sorted"] == ["content", "role"]
    assert item["role"] == "assistant"
    assert item["content_form"] == "list"
    assert item["content_part_types"] == ["output_text"]
    assert obs["lead_text_replayed_in_input"] is True
    wrap = data["read_tool"]["native_output_wrap"]
    assert wrap["content_is_raw_file_bytes"] is False
    assert wrap["marker_present"] is True
    assert wrap["marker_occurrences_in_output"] == 1
    assert wrap["content_byte_length"] == 192
    assert wrap["marker_byte_length"] == 38
    assert wrap["content_equals_marker"] is False
    gate = data["verification_gate"]
    assert gate["result"] == "verified"
    assert gate["final_text_source"] == "correlated_tool_result"
    assert gate["final_text_length"] == 38
    assert data["session"]["session_value_sha256_8"] == "01d4076c"
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["elapsed_s"] == 5.728


def test_default_title_aux_request_facts():
    data = _load("structural_defaulttitle.json")
    assert data["title_flag_supplied"] is False
    order = data["request_order"]
    assert order["tools_count_per_request"] == [0, 9]
    assert order["main_request_index"] == 1
    aux = data["aux_request"]
    assert aux["aux_requests"] == 1
    assert aux["top_level_field_count"] == 7
    assert aux["top_level_fields"] == [
        "include", "input", "max_output_tokens", "model", "reasoning",
        "store", "stream"]
    assert aux["tool_choice_present"] is False
    assert aux["include_present"] is True
    assert aux["reasoning_present"] is True
    assert aux["input_form"] == "list"
    assert aux["input_item_count"] == 3
    cf = aux["contract_facts"]
    assert cf["model"]["observed"] == "agent-responses-fake-model"
    assert cf["stream"]["observed"] is True
    assert cf["store"]["observed"] is False
    assert cf["max_output_tokens_present"] is True
    assert cf["include"]["observed"] == ["reasoning.encrypted_content"]
    assert cf["reasoning"]["observed"] == {"effort": "xhigh"}
    main = data["main_request"]
    assert main["input_item_count"] == 2
    _assert_contract(main)
    assert data["session"]["stable_across_two_requests"] is True
    assert data["session"]["session_value_sha256_8"] == "221d1bea"
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["final_text_exact"] is True
    assert beh["elapsed_s"] == 5.678


def test_reasoning_visible_states_facts():
    data = _load("structural_reasoning_visible.json")
    assert data["observation_only"] is True
    assert data["not_encrypted_ownership"] is True
    assert "NOT encrypted-ownership passes" in data["authority_note"]
    _assert_contract(data["request_turn_1"])
    sc = data["scenarios"]
    assert set(sc) == {"absent", "null", "empty"}
    for name, s in sc.items():
        assert s["verification_gate"]["result"] == "verified", name
        assert s["verification_gate"]["final_text_source"] == "correlated_tool_result", name
        assert s["session"]["stable_across_two_requests"] is True, name
        assert s["client_behavior"]["exit_code"] == 0, name
        assert s["sdk_replay_behavior"]["issued_call_id_correlated"] is True, name
    assert sc["absent"]["reasoning_item_issued_state"] == "absent"
    a = sc["absent"]["sdk_replay_behavior"]
    assert a["input_item_count"] == 4
    assert a["input_item_types"] == [None, None, "function_call",
                                     "function_call_output"]
    assert a["reasoning_replayed_state"] == "null"
    assert a["replayed_matches_issued"] is False
    assert sc["null"]["reasoning_item_issued_state"] == "null"
    n = sc["null"]["sdk_replay_behavior"]
    assert n["input_item_count"] == 4
    assert n["input_item_types"] == [None, None, "function_call",
                                     "function_call_output"]
    assert n["reasoning_replayed_state"] == "null"
    assert n["replayed_matches_issued"] is False
    assert sc["empty"]["reasoning_item_issued_state"] == "empty_string"
    e = sc["empty"]["sdk_replay_behavior"]
    assert e["input_item_count"] == 5
    assert e["input_item_types"] == [None, None, "reasoning", "function_call",
                                     "function_call_output"]
    kept = e["appended_items"][0]
    assert kept["type"] == "reasoning"
    assert kept["keys_sorted"] == ["encrypted_content", "summary", "type"]
    assert kept["id_state"] == "absent" and kept["status_state"] == "absent"
    assert kept["encrypted_content_state"] == "empty_string"
    assert kept["summary_present"] is True
    assert kept["derived_sha256_8_of_empty_string"] == "e3b0c442"
    assert kept["derived_byte_length_of_empty_string"] == 0
    assert "DERIVED" in kept["derived_note"]
    assert kept["replayed_state"] == "empty_string"
    assert kept["replayed_matches_issued"] is True
    assert sc["absent"]["session"]["session_value_sha256_8"] == "b0f486a3"
    assert sc["absent"]["client_behavior"]["elapsed_s"] == 5.831
    assert sc["null"]["session"]["session_value_sha256_8"] == "425f751c"
    assert sc["null"]["client_behavior"]["elapsed_s"] == 5.48
    assert sc["empty"]["session"]["session_value_sha256_8"] == "3c472fa9"
    assert sc["empty"]["client_behavior"]["elapsed_s"] == 5.528
    gate = data["shared_marker_gate"]
    assert gate["result"] == "verified"
    assert gate["final_text_length"] == 38
    assert gate["marker_length"] == 38


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


def test_compaction_client_side_facts():
    data = _load("structural_compaction.json")
    assert data["endpoint"] == "POST /v1/responses"
    assert data["fake_only_synthetic_trigger"] is True
    assert data["not_gateway_provider_pass"] is True
    assert "loopback fake" in data["authority_note"]
    # no compaction endpoint participation claimed; empty trace is
    # non-observation evidence only
    trace = data["compaction_trace"]
    assert trace["post_paths_other_than_responses_seen"] == []
    assert trace["responses_compact_endpoint_observed"] is False
    # turn 1: baseline contract + synthetic overflow trigger, tool not answered
    t1 = data["request_turn_1"]
    _assert_contract(t1)
    assert t1["input_item_count"] == 2
    assert t1["tools_count"] == 9
    assert t1["tool_declaration_strict_present_count"] == 9
    assert t1["issued_function_call"]["name"] == "read"
    assert t1["issued_function_call"]["tool_executed"] is False
    assert t1["issued_function_call"]["function_call_outputs_issued"] == 0
    trig = t1["usage_emitted_by_fake"]
    assert trig["usage_is_synthetic_trigger"] is True
    assert trig["input_tokens"] == 225000
    assert trig["output_tokens"] == 2000
    # summary request: observed 7-field shape with recorded deviations
    s = data["compaction_summary_request"]
    assert s["top_level_field_count"] == 7
    assert s["top_level_fields"] == sorted([
        "include", "input", "max_output_tokens", "model", "reasoning",
        "store", "stream"])
    assert s["tools_form"] == "absent"
    assert s["system_form"] == "absent"
    assert s["tool_choice_present"] is False
    assert s["max_output_tokens"] == 32000
    assert s["input_item_count"] == 2
    assert s["input_item_types"] == [None, None]
    assert s["input_item_roles"] == ["developer", "user"]
    assert "compaction.ts:161" in s["input_item_note"]
    assert "OMITS the tools key" in s["observed_deviations_from_source_prediction"]["tools"]
    assert "4096" in s["observed_deviations_from_source_prediction"]["max_output_tokens"]
    # continuation: 4 typeless items, source-derived order, full replacement
    c = data["continuation_request"]
    assert c["input_item_count"] == 4
    assert c["input_item_types"] == [None, None, None, None]
    assert c["input_item_roles"] == ["developer", "user", "assistant", "user"]
    assert c["compaction_user_item_index"] == 1
    assert c["summary_item_index_byte_exact"] == 2
    assert c["continue_user_item_index"] == 3
    assert c["order_compaction_user_before_summary"] is True
    assert c["order_summary_before_continue"] is True
    assert c["fc_outputs_total"] == 0
    assert c["first_user_text_equals_original_prompt"] is False
    assert "fully replaced" in c["observed_deviation_from_source_prediction"]
    assert c["tools_count"] == 9
    assert c["tool_choice"] == "auto"
    assert any("message-v2.ts:241" in r for r in data["source_refs"])
    assert any("compaction.ts:531" in r for r in data["source_refs"])
    # gate and session
    gate = data["verification_gate"]
    assert gate["result"] == "verified"
    assert gate["compaction_request_seen"] is True
    assert gate["summary_byte_exact_replay"] is True
    assert gate["final_text_exact"] is True
    assert gate["final_text_source"] == "static_sentinel"
    assert gate["sentinel_length"] == 24
    ses = data["session"]
    assert ses["request_count"] == 3
    assert ses["stable_across_requests"] is True
    assert ses["session_value_sha256_8"] == "6145d992"
    assert ses["session_header_names_present"] == [
        "x-opencode-session-id", "x-session-affinity", "x-session-id"]
    beh = data["client_behavior"]
    assert beh["exit_code"] == 0
    assert beh["elapsed_s"] == 5.528
    assert data["privacy"]["raw_content_retained"] is False
    assert data["privacy"]["provider_call_performed"] is False
