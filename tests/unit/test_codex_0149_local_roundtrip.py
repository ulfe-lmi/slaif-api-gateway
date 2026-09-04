from __future__ import annotations

import asyncio
import http.client
import json
import sys
from types import SimpleNamespace

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


def test_obligation_evaluator_reports_exact_empty_missing_list() -> None:
    assert verifier.evaluate_obligations() == []
    assert f"missing={verifier.evaluate_obligations()}" == "missing=[]"


def test_doctrine_link_mutations_report_the_exact_missing_location() -> None:
    documents = {
        "AGENTS.md": "AGENTIC_CLIENT_INTEGRATION.md",
        "docs/module-architecture.md": "../AGENTIC_CLIENT_INTEGRATION.md",
        "docs/responses-compatibility.md": "../AGENTIC_CLIENT_INTEGRATION.md",
        "docs/compatibility-matrix.md": "../AGENTIC_CLIENT_INTEGRATION.md",
    }
    assert verifier.missing_doctrine_links(documents) == []
    for path, expected in (
        ("AGENTS.md", "doctrine_link:AGENTS.md"),
        ("docs/module-architecture.md", "doctrine_link:docs/module-architecture.md"),
        ("docs/responses-compatibility.md", "doctrine_link:docs/responses-compatibility.md"),
        ("docs/compatibility-matrix.md", "doctrine_link:docs/compatibility-matrix.md"),
    ):
        mutated = dict(documents)
        mutated[path] = ""
        assert verifier.missing_doctrine_links(mutated) == [expected]


def test_gateway_failure_projection_is_finite_and_value_free() -> None:
    observation = SimpleNamespace(
        request_count=1,
        response_statuses=[400],
        error_codes=["responses_tool_invalid_shape"],
        error_shapes=["error_invalid_request_tools_description"],
        request_shapes=["stream_true_tools_function[name,type]_input_message"],
    )
    code = verifier._safe_gateway_failure_code(observation, "AttributeError")
    assert code == (
        "gateway_requests_one_status_4xx_error_responses_tool_invalid_shape_"
        "shape_error_invalid_request_tools_description_exception_AttributeError_"
        "profile_stream_true_function_input_message"
    )
    assert len(code) <= 512
    assert all(char.isalnum() or char in "_+.-" for char in code)
    unknown = SimpleNamespace(
        request_count=9,
        response_statuses=[0],
        error_codes=["private-value"],
        error_shapes=["bad value"],
        request_shapes=["private value"],
    )
    unknown_code = verifier._safe_gateway_failure_code(unknown, "UnexpectedError")
    assert unknown_code == (
        "gateway_requests_other_status_other_error_other_shape_other_exception_other_"
        "profile_stream_other"
    )


def test_gateway_observer_owns_request_projection() -> None:
    assert "_record_request_shape" in verifier._GatewayObservation.__dict__
    assert "_record_request_shape" not in verifier._GatewayExceptionObservation.__dict__

    sent: list[dict[str, object]] = []

    async def app(scope, receive, send) -> None:
        assert scope["path"] == "/v1/responses"
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    body = json.dumps(
        {
            "stream": True,
            "tools": [{"type": "function", "name": "safe", "description": "x"}],
            "input": [{"type": "message"}],
        }
    ).encode()
    messages = iter(
        (
            {"type": "http.request", "body": body, "more_body": False},
        )
    )

    async def receive() -> dict[str, object]:
        return next(messages)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    observer = verifier._GatewayObservation(app)
    asyncio.run(
        observer(
            {"type": "http", "method": "POST", "path": "/v1/responses"},
            receive,
            send,
        )
    )
    assert observer.request_count == 1
    assert observer.request_shapes == [
        "stream_true_tools_function[description,name,type]_format_none_description_string_bounded_input_message"
    ]
    assert sent[-1]["type"] == "http.response.body"


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
