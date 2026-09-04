from __future__ import annotations

import http.client
import json
import sys

import pytest

from scripts import verify_codex_0149_local_roundtrip as verifier


def test_codex_command_uses_task_local_zero_retry_responses_profile(tmp_path) -> None:
    command = verifier._codex_command(
        tmp_path / "codex",
        workdir=tmp_path,
        port=43123,
        catalog=tmp_path / "catalog.json",
        output=tmp_path / "output.json",
    )

    assert command[0].endswith("codex")
    assert any('wire_api="responses"' in item for item in command)
    assert "model_providers.slaif-roundtrip.request_max_retries=0" in command
    assert "model_providers.slaif-roundtrip.stream_max_retries=0" in command
    assert "--ignore-user-config" in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--resume" not in command


def test_obligation_manifest_is_complete_and_bounded() -> None:
    assert set(verifier.OBLIGATION_MANIFEST) == {
        "app/codex_replay_repository",
        "app/codex_0149_client",
        "app/contracts",
        "app/codex_replay_service",
        "app/responses_gateway",
        "app/responses_request_policy",
        "fixture/reasoning",
        "fixture/session",
        "fixture/structural",
        "fixture/local_filter",
        "fixture/signed_identity",
        "replay/no_downgrade_rotation",
        "identity/stream/accounting/privacy",
        "fake_codex_two_turn",
        "historical_155_machinery",
    }
    assert all(isinstance(value, str) and value for value in verifier.OBLIGATION_MANIFEST.values())


def test_fake_streams_are_two_bounded_ordered_lifecycles() -> None:
    function_events = verifier._function_stream("{}", "shell_command")
    message_events = verifier._message_stream()

    assert [event["sequence_number"] for event in function_events] == list(range(7))
    assert [event["sequence_number"] for event in message_events] == list(range(9))
    assert [event["type"] for event in function_events].count("response.completed") == 1
    assert [event["type"] for event in message_events].count("response.completed") == 1
    assert function_events[2]["item"]["id"] == "function1"
    assert "id" not in {"type": "function_call_output"}


def test_known_local_tool_selection_fails_closed() -> None:
    with pytest.raises(verifier.VerificationError, match="known_local_tool_missing"):
        verifier._tool_name({"tools": [{"type": "function", "name": "unknown"}]})

    assert verifier._tool_name(
        {"tools": [{"type": "function", "name": "exec_command"}]}
    ) == "exec_command"


def test_fake_local_requires_signed_headers_and_idless_adjacent_output() -> None:
    state = verifier._FakeLocalState(
        service_token=verifier.LOCAL_SERVICE_TOKEN,
        signing_secret=verifier.LOCAL_SIGNING_SECRET.encode(),
    )
    headers = http.client.HTTPMessage()
    headers["authorization"] = f"Bearer {verifier.LOCAL_SERVICE_TOKEN}"
    for name in (
        "x-slaif-identity-version",
        "x-slaif-principal",
        "x-slaif-session",
        "x-slaif-repository",
        "x-slaif-route",
        "x-slaif-timestamp",
        "x-slaif-nonce",
        "x-slaif-signature",
    ):
        headers[name] = "invalid"
    body = json.dumps(
        {
            "input": [
                {"type": "function_call", "call_id": "call_roundtrip"},
                {"type": "function_call_output", "call_id": "call_roundtrip", "output": "ok"},
            ]
        }
    ).encode()

    with pytest.raises(verifier.VerificationError, match="signed_body_mismatch"):
        state.observe(body, headers, "/v1/responses")


def test_main_emits_only_fixed_failure_line(monkeypatch, capsys) -> None:
    monkeypatch.setattr(verifier, "run_roundtrip", lambda: (_ for _ in ()).throw(verifier.VerificationError("accounting_predicate_failed")))
    monkeypatch.setattr(sys, "argv", ["verify_codex_0149_local_roundtrip.py"])

    assert verifier.main() == 1
    assert capsys.readouterr().out == (
        "VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_FAILED code=accounting_predicate_failed\n"
    )
