"""Pure tests for the opt-in actual-Codex gateway verifier."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from scripts import verify_codex_gateway_e2e as verifier


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "postgresql+asyncpg://slaif@localhost/slaif_gateway_test",
        "postgresql+asyncpg://slaif@127.0.0.2/slaif_gateway_test",
        "postgresql+asyncpg://slaif@127.0.0.1/slaif_gateway",
        "postgresql+asyncpg://slaif@127.0.0.1/production",
        "postgresql+asyncpg://slaif@127.0.0.1/slaif_gateway_test?sslmode=require",
        "postgresql+asyncpg://slaif@127.0.0.1/slaif_gateway_test#fragment",
        "sqlite:///slaif_gateway_test.db",
    ],
)
def test_test_database_url_refuses_unsafe_targets(value: str | None) -> None:
    with pytest.raises(verifier.VerificationError) as exc_info:
        verifier.validate_test_database_url(value)

    assert exc_info.value.code == verifier.SAFE_DATABASE_ERROR


def test_test_database_url_accepts_only_numeric_loopback_test_name() -> None:
    target = verifier.validate_test_database_url(
        "postgresql+asyncpg://slaif:secret@127.0.0.1:5432/slaif_gateway_oap011_test_ab12"
    )

    assert target.database_name == "slaif_gateway_oap011_test_ab12"
    assert "secret" not in repr(target)


def test_argument_parser_has_no_mutating_or_secret_interface() -> None:
    verifier.parse_arguments([])
    for arguments in (["--help"], ["--database-url", "secret"], ["--api-key", "secret"]):
        with pytest.raises(verifier.VerificationError) as exc_info:
            verifier.parse_arguments(arguments)
        assert exc_info.value.code == verifier.SAFE_ARGUMENT_ERROR


def test_fixed_failure_output_never_reflects_unknown_value() -> None:
    output = verifier.fixed_error_output("private operator value")

    assert output == ("RESULT=FAIL\nERROR_CODE=verification_failed\nREAL_PROVIDER_CALLED=false\n")
    assert "private operator value" not in output


def test_fixed_success_output_is_exact_and_low_cardinality() -> None:
    facts = verifier.VerificationFacts(
        cli_version_matched=True,
        fixture_digest_matched=True,
        scenario_count=5,
        text_completion_seen=True,
        local_exec_seen=True,
        local_edit_seen=True,
        workspace_marker_matched=True,
        multi_round_replay_seen=True,
        encrypted_reasoning_replay_seen=True,
        cache_read_usage_seen=True,
        cache_write_usage_seen=True,
        long_context_tiers_seen=True,
        v1_compact_seen=True,
        post_compact_continuation_seen=True,
        quota_rejection_seen=True,
        quota_rejected_before_upstream=True,
        stream_interruption_seen=True,
        provider_error_seen=True,
        accounting_matched=True,
        outstanding_reservations=0,
        provider_auth_replaced=True,
        outbound_headers_sanitized=True,
        loopback_only=True,
        raw_payloads_persisted=False,
        redis_private_ephemeral=True,
        workspaces_removed=True,
        real_provider_called=False,
    )

    output = verifier.fixed_success_output(facts)
    lines = output.splitlines()

    assert [line.split("=", 1)[0] for line in lines] == list(verifier.OUTPUT_KEYS)
    assert lines[0] == "RESULT=OK"
    assert "SCENARIO_COUNT=5" in lines
    assert "OUTSTANDING_RESERVATIONS=0" in lines
    assert "REAL_PROVIDER_CALLED=false" in lines
    assert all("http" not in line and "sk-slaif" not in line for line in lines)


def test_codex_command_uses_named_profile_without_selection_overrides(tmp_path: Path) -> None:
    command = verifier.build_codex_command(
        workdir=tmp_path,
        prompt="bounded prompt",
        sandbox="workspace-write",
    )

    assert command[:6] == [
        "/usr/bin/codex",
        "--ask-for-approval",
        "never",
        "--profile",
        "slaif",
        "exec",
    ]
    assert "--ephemeral" in command
    assert "workspace-write" in command
    assert "model=" not in "\n".join(command)
    assert "model_provider=" not in "\n".join(command)
    assert "request_max_retries=0" in "\n".join(command)
    assert "stream_max_retries=0" in "\n".join(command)


def test_profile_environment_is_private_and_proxy_fail_closed(tmp_path: Path) -> None:
    environment = verifier._profile_environment(tmp_path, "private-gateway-key")

    assert environment["CODEX_HOME"] == str(tmp_path)
    assert environment["HOME"] == str(tmp_path)
    assert environment["OPENAI_API_KEY"] == "private-gateway-key"
    assert environment["NO_PROXY"] == "127.0.0.1"
    assert environment["HTTP_PROXY"] == "http://127.0.0.1:9"
    assert "OPENAI_UPSTREAM_API_KEY" not in environment


def test_tool_scenario_has_exact_three_round_state_machine(tmp_path: Path) -> None:
    actions = verifier.build_tool_scenario_actions(
        workspace=tmp_path,
        marker_content="unique marker",
        encrypted_content="opaque encrypted value",
        final_text="unique final",
    )

    assert [action.path for action in actions] == ["/v1/responses"] * 3
    assert [action.kind for action in actions] == ["sse"] * 3
    encoded = json.dumps([action.payload for action in actions])
    assert "tools.exec_command" in encoded
    assert "tools.apply_patch" in encoded
    assert "opaque encrypted value" in encoded
    assert "unique final" in encoded


def test_context_scenario_has_responses_compact_continuation() -> None:
    actions = verifier.build_context_scenario_actions(
        marker="unique context marker",
        encrypted_content="unique opaque compaction",
    )

    assert [action.path for action in actions] == [
        "/v1/responses",
        "/v1/responses/compact",
        "/v1/responses",
    ]
    assert [action.kind for action in actions] == ["sse", "json", "sse"]
    assert "unique opaque compaction" in json.dumps(actions[1].payload)


def test_upstream_request_reducer_requires_server_key_and_sanitizes_headers() -> None:
    server = verifier.ScriptedOpenAIMock()
    request = verifier.capture.ParsedHttpRequest(
        method="POST",
        target="/v1/responses",
        version="HTTP/1.1",
        headers=(
            ("authorization", f"Bearer {verifier.DUMMY_UPSTREAM_KEY}"),
            ("content-type", "application/json"),
        ),
        body=json.dumps({"model": verifier.CODEX_MODEL, "input": []}).encode(),
    )

    facts = server._reduce_request(request, expected_path="/v1/responses")

    assert facts.authorization_replaced is True
    assert facts.headers_sanitized is True
    assert facts.content_encoding_absent is True
    assert facts.model_matched is True


@pytest.mark.parametrize(
    "headers",
    [
        (("authorization", "Bearer client-key"),),
        (
            ("authorization", f"Bearer {verifier.DUMMY_UPSTREAM_KEY}"),
            ("cookie", "private-cookie"),
        ),
    ],
)
def test_upstream_request_reducer_rejects_client_auth_or_private_headers(
    headers: tuple[tuple[str, str], ...],
) -> None:
    server = verifier.ScriptedOpenAIMock()
    request = verifier.capture.ParsedHttpRequest(
        method="POST",
        target="/v1/responses",
        version="HTTP/1.1",
        headers=headers,
        body=json.dumps({"model": verifier.CODEX_MODEL, "input": []}).encode(),
    )

    with pytest.raises(verifier.VerificationError):
        server._reduce_request(request, expected_path="/v1/responses")


def test_accounting_reducer_requires_exact_success_failure_and_zero_pending() -> None:
    success = verifier.KeyAccountingFacts(
        requests_used=3,
        tokens_used=6,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("finalized", "finalized", "finalized"),
        ledger_statuses=("finalized", "finalized", "finalized"),
        ledger_successes=(True, True, True),
        ledger_error_types=(None, None, None),
        usage=((1, 0, 1, 0, 2),) * 3,
        component_metadata=({}, {}, {}),
    )
    context = verifier.KeyAccountingFacts(
        requests_used=3,
        tokens_used=872_024,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("finalized", "finalized", "finalized"),
        ledger_statuses=("finalized", "finalized", "finalized"),
        ledger_successes=(True, True, True),
        ledger_error_types=(None, None, None),
        usage=(
            (600_000, 200_000, 10, 4, 600_010),
            (272_000, 100_000, 2, 1, 272_002),
            (10, 5, 2, 1, 12),
        ),
        component_metadata=(
            {
                "actual_cached_tokens": 200_000,
                "component_token_counts": {
                    "input_uncached_tokens": 300_000,
                    "long_context_tier_applied": 1,
                },
                "component_costs_native": {"input_cache_write": "0.25"},
            },
            {
                "actual_cached_tokens": 100_000,
                "component_token_counts": {
                    "input_uncached_tokens": 122_000,
                    "long_context_tier_applied": 0,
                },
                "component_costs_native": {"input_cache_write": "0.0625"},
            },
            {
                "actual_cached_tokens": 5,
                "component_token_counts": {
                    "input_uncached_tokens": 4,
                    "long_context_tier_applied": 0,
                },
                "component_costs_native": {"input_cache_write": "0.00000125"},
            },
        ),
    )
    quota = verifier.KeyAccountingFacts(
        requests_used=1,
        tokens_used=2,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("finalized",),
        ledger_statuses=("finalized",),
        ledger_successes=(True,),
        ledger_error_types=(None,),
        usage=((1, 0, 1, 0, 2),),
        component_metadata=({},),
    )
    failure = verifier.KeyAccountingFacts(
        requests_used=0,
        tokens_used=0,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("released",),
        ledger_statuses=("failed",),
        ledger_successes=(False,),
        ledger_error_types=("provider_http_error",),
        usage=((0, 0, 0, 0, 0),),
        component_metadata=({},),
    )

    assert verifier._validate_accounting(
        tool=success,
        context=context,
        quota=quota,
        interruption=failure,
        provider_error=failure,
    ) == (True, True, True, True)


def test_import_and_pytest_collection_do_not_invoke_manual_verifier(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(verifier, "verify", lambda target: calls.append(target))

    imported = importlib.reload(verifier)

    assert imported.__name__ == "scripts.verify_codex_gateway_e2e"
    assert calls == []


def test_main_refuses_real_provider_environment_without_running(monkeypatch, capsys) -> None:
    calls: list[object] = []
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://slaif@127.0.0.1/slaif_gateway_test",
    )
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", "must-not-be-read")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(verifier, "verify", lambda target: calls.append(target))

    result = verifier.main([])

    assert result == 1
    assert calls == []
    assert capsys.readouterr().out == (
        "RESULT=FAIL\nERROR_CODE=verification_failed\nREAL_PROVIDER_CALLED=false\n"
    )


def test_real_pilot_runbook_is_human_gated_and_unexecuted() -> None:
    content = Path("docs/runbooks/codex-openai-pilot.md").read_text(encoding="utf-8")

    for required in (
        "PREPARED, NOT EXECUTED",
        "separately and explicitly authorized",
        "non-production",
        "codex-cli 0.147.0",
        "gpt-5.6-sol",
        "OPENAI_UPSTREAM_API_KEY",
        "read -rsp",
        "at most four",
        "revoke the pilot key",
        "zero outstanding reservations",
        "real_provider_e2e=false",
    ):
        assert required in content
    assert "export OPENAI_UPSTREAM_API_KEY=" not in content


def test_documented_support_boundary_is_exact() -> None:
    content = Path("docs/codex-compatibility.md").read_text(encoding="utf-8")

    assert "local_gateway_e2e_qualified=true" in content
    assert "bounded_real_openai_pilot_prepared=true" in content
    assert "real_provider_e2e=false" in content
    assert "full compatibility is not claimed" in content


def test_manual_verifier_is_not_wired_into_ci_or_application() -> None:
    needle = "verify_codex_gateway_e2e"
    searched = [Path("pyproject.toml"), *Path(".github/workflows").glob("*.yml")]

    assert all(needle not in path.read_text(encoding="utf-8") for path in searched)
    source = Path("scripts/verify_codex_gateway_e2e.py").read_text(encoding="utf-8")
    assert "api.openai.com" not in source
