"""Pure tests for the opt-in actual-Codex gateway verifier."""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import stat
import subprocess
from dataclasses import replace
from decimal import Decimal
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
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test?host=/var/run/postgresql",
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test?port=6543",
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test?options=-c%20search_path=private",
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test?",
        "postgresql+asyncpg://slaif@127.0.0.1/slaif_gateway_test#fragment",
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test#",
        "postgresql://slaif@127.0.0.1:5432/slaif_gateway_test",
        "postgresql+asyncpg://slaif@127.0.0.1/slaif_gateway_test",
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif gateway_test",
        "\x00postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test",
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


def test_codex_binary_override_requires_absolute_owner_only_non_symlink(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    binary.write_bytes(b"synthetic")
    binary.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    assert verifier._resolve_codex_binary(str(binary)) == binary
    with pytest.raises(verifier.VerificationError) as relative:
        verifier._resolve_codex_binary("relative/codex")
    assert relative.value.code == "unsafe_codex_binary"

    symlink = tmp_path / "codex-link"
    symlink.symlink_to(binary)
    with pytest.raises(verifier.VerificationError) as linked:
        verifier._resolve_codex_binary(str(symlink))
    assert linked.value.code == "unsafe_codex_binary"


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
        exec_sentinel="unique exec success",
        encrypted_content="opaque encrypted value",
        final_text="unique final",
    )

    assert [action.path for action in actions] == ["/v1/responses"] * 3
    assert [action.kind for action in actions] == ["sse"] * 3
    encoded = json.dumps([action.payload for action in actions])
    assert "tools.exec_command" in encoded
    assert "r.exit_code !== 0" in encoded
    assert "unique exec success" in encoded
    assert "tools.apply_patch" in encoded
    assert "opaque encrypted value" in encoded
    assert "unique final" in encoded


def test_linked_exec_output_and_final_marker_require_exact_structured_evidence() -> None:
    request_facts = verifier.UpstreamRequestFacts(
        path="/v1/responses",
        authorization_replaced=True,
        headers_sanitized=True,
        content_encoding_absent=True,
        model_matched=True,
        input_items=(
            {
                "type": "custom_tool_call_output",
                "call_id": "call_oap011_exec",
                "output": {"content": [{"text": "prefix unique-exec-sentinel suffix"}]},
            },
        ),
    )
    completed = subprocess.CompletedProcess(
        ["codex"],
        0,
        (
            b'{"type":"item.completed","item":{"type":"agent_message",'
            b'"text":"unique-final-marker"}}\n'
            b'{"type":"turn.completed"}\n'
        ),
        b"",
    )

    assert verifier._linked_custom_tool_output_contains(
        request_facts,
        call_id="call_oap011_exec",
        sentinel="unique-exec-sentinel",
    )
    assert verifier._codex_final_marker_seen(completed, marker="unique-final-marker")
    assert not verifier._codex_final_marker_seen(completed, marker="different-final")
    assert not verifier._linked_custom_tool_output_contains(
        request_facts,
        call_id="different-call",
        sentinel="unique-exec-sentinel",
    )


def test_failure_actions_carry_unique_body_sentinels_without_changing_topology() -> None:
    interrupted = verifier.build_failure_action(
        interrupted=True,
        sentinel="unique-interruption-body",
    )
    provider_error = verifier.build_failure_action(
        interrupted=False,
        sentinel="unique-provider-error-body",
    )

    assert interrupted.kind == "interrupted"
    assert interrupted.status_code == 200
    assert "unique-interruption-body" in json.dumps(interrupted.payload)
    assert provider_error.kind == "error"
    assert provider_error.status_code == 429
    assert "unique-provider-error-body" in json.dumps(provider_error.payload)
    assert provider_error.payload["error"]["message"] == "bounded loopback provider error"
    assert provider_error.payload["error"]["content"] == "unique-provider-error-body"


def test_private_workspace_modes_contents_and_portable_cleanup(tmp_path: Path) -> None:
    assert (
        "gateway_key" not in inspect.signature(verifier.prepare_private_codex_workspace).parameters
    )
    prepared = verifier.prepare_private_codex_workspace(gateway_port=8123)
    forbidden_credential = "sk-slaif-private-gateway-secret"
    try:
        assert stat.S_IMODE(prepared.root.stat().st_mode) == 0o700
        assert stat.S_IMODE(prepared.codex_home.stat().st_mode) == 0o700
        assert stat.S_IMODE(prepared.workspace.stat().st_mode) == 0o700
        for profile_file in prepared.profile_files:
            assert stat.S_IMODE(profile_file.stat().st_mode) == 0o600
            content = profile_file.read_text(encoding="utf-8")
            assert forbidden_credential not in content
            assert verifier.DUMMY_UPSTREAM_KEY not in content
    finally:
        verifier._remove_private_root(prepared.root)

    assert not prepared.root.exists()
    outside = tmp_path / "slaif-oap011-codex-outside"
    outside.mkdir()
    with pytest.raises(verifier.VerificationError):
        verifier._remove_private_root(outside)
    assert outside.is_dir()


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
    ordinary_metadata = {
        "component_token_counts": {
            "input_uncached_tokens": 1,
            "input_cached_tokens": 0,
            "output_non_reasoning_tokens": 1,
            "output_reasoning_tokens": 0,
            "long_context_tier_applied": 0,
            "total_tokens": 2,
        },
        "component_costs_native": {
            "input_uncached": "0.000001",
            "input_cached": "0",
            "input_cache_write": "0",
            "output_non_reasoning": "0.000002",
            "output_reasoning": "0",
            "output_audio": "0",
        },
    }
    success = verifier.KeyAccountingFacts(
        cost_used_eur=Decimal("0.000009000"),
        cost_reserved_eur=Decimal("0.000000000"),
        requests_used=3,
        tokens_used=6,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("finalized", "finalized", "finalized"),
        ledger_statuses=("finalized", "finalized", "finalized"),
        ledger_successes=(True, True, True),
        ledger_error_types=(None, None, None),
        ledger_http_statuses=(200, 200, 200),
        ledger_actual_costs_eur=(Decimal("0.000003000"),) * 3,
        ledger_actual_costs_native=(Decimal("0.000003000"),) * 3,
        ledger_native_currencies=("EUR", "EUR", "EUR"),
        usage=((1, 0, 1, 0, 2),) * 3,
        component_metadata=(ordinary_metadata, ordinary_metadata, ordinary_metadata),
    )
    context = verifier.KeyAccountingFacts(
        cost_used_eur=Decimal("1.284545750"),
        cost_reserved_eur=Decimal("0.000000000"),
        requests_used=3,
        tokens_used=872_024,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("finalized", "finalized", "finalized"),
        ledger_statuses=("finalized", "finalized", "finalized"),
        ledger_successes=(True, True, True),
        ledger_error_types=(None, None, None),
        ledger_http_statuses=(200, 200, 200),
        ledger_actual_costs_eur=(
            Decimal("1.050030000"),
            Decimal("0.234504000"),
            Decimal("0.000011750"),
        ),
        ledger_actual_costs_native=(
            Decimal("1.050030000"),
            Decimal("0.234504000"),
            Decimal("0.000011750"),
        ),
        ledger_native_currencies=("EUR", "EUR", "EUR"),
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
                    "input_cached_tokens": 200_000,
                    "output_non_reasoning_tokens": 6,
                    "output_reasoning_tokens": 4,
                    "long_context_tier_applied": 1,
                    "total_tokens": 600_010,
                },
                "component_costs_native": {
                    "input_uncached": "0.6",
                    "input_cached": "0.2",
                    "input_cache_write": "0.25",
                    "output_non_reasoning": "0.000018",
                    "output_reasoning": "0.000012",
                    "output_audio": "0",
                },
            },
            {
                "actual_cached_tokens": 100_000,
                "component_token_counts": {
                    "input_uncached_tokens": 122_000,
                    "input_cached_tokens": 100_000,
                    "output_non_reasoning_tokens": 1,
                    "output_reasoning_tokens": 1,
                    "long_context_tier_applied": 0,
                    "total_tokens": 272_002,
                },
                "component_costs_native": {
                    "input_uncached": "0.122",
                    "input_cached": "0.05",
                    "input_cache_write": "0.0625",
                    "output_non_reasoning": "0.000002",
                    "output_reasoning": "0.000002",
                    "output_audio": "0",
                },
            },
            {
                "actual_cached_tokens": 5,
                "component_token_counts": {
                    "input_uncached_tokens": 4,
                    "input_cached_tokens": 5,
                    "output_non_reasoning_tokens": 1,
                    "output_reasoning_tokens": 1,
                    "long_context_tier_applied": 0,
                    "total_tokens": 12,
                },
                "component_costs_native": {
                    "input_uncached": "0.000004",
                    "input_cached": "0.0000025",
                    "input_cache_write": "0.00000125",
                    "output_non_reasoning": "0.000002",
                    "output_reasoning": "0.000002",
                    "output_audio": "0",
                },
            },
        ),
    )
    quota = verifier.KeyAccountingFacts(
        cost_used_eur=Decimal("0.000003000"),
        cost_reserved_eur=Decimal("0.000000000"),
        requests_used=1,
        tokens_used=2,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("finalized",),
        ledger_statuses=("finalized",),
        ledger_successes=(True,),
        ledger_error_types=(None,),
        ledger_http_statuses=(200,),
        ledger_actual_costs_eur=(Decimal("0.000003000"),),
        ledger_actual_costs_native=(Decimal("0.000003000"),),
        ledger_native_currencies=("EUR",),
        usage=((1, 0, 1, 0, 2),),
        component_metadata=(ordinary_metadata,),
    )
    failure = verifier.KeyAccountingFacts(
        cost_used_eur=Decimal("0.000000000"),
        cost_reserved_eur=Decimal("0.000000000"),
        requests_used=0,
        tokens_used=0,
        requests_reserved=0,
        tokens_reserved=0,
        pending_reservations=0,
        reservation_statuses=("released",),
        ledger_statuses=("failed",),
        ledger_successes=(False,),
        ledger_error_types=("provider_request_error",),
        ledger_http_statuses=(None,),
        ledger_actual_costs_eur=(Decimal("0.000000000"),),
        ledger_actual_costs_native=(Decimal("0.000000000"),),
        ledger_native_currencies=("EUR",),
        usage=((0, 0, 0, 0, 0),),
        component_metadata=({},),
    )
    provider_failure = replace(
        failure,
        ledger_error_types=("provider_http_error",),
        ledger_http_statuses=(429,),
    )

    assert verifier._validate_accounting(
        tool=success,
        context=context,
        quota=quota,
        interruption=failure,
        provider_error=provider_failure,
    ) == (True, True, True, True)

    wrong_total = replace(success, cost_used_eur=Decimal("0.000010000"))
    assert (
        verifier._validate_accounting(
            tool=wrong_total,
            context=context,
            quota=quota,
            interruption=failure,
            provider_error=provider_failure,
        )[0]
        is False
    )

    unscaled_total = replace(success, cost_used_eur=Decimal("0.000009"))
    assert (
        verifier._validate_accounting(
            tool=unscaled_total,
            context=context,
            quota=quota,
            interruption=failure,
            provider_error=provider_failure,
        )[0]
        is False
    )

    wrong_components = list(copy.deepcopy(context.component_metadata))
    wrong_components[1]["component_costs_native"]["input_cache_write"] = "0.062500001"
    assert (
        verifier._validate_accounting(
            tool=success,
            context=replace(context, component_metadata=tuple(wrong_components)),
            quota=quota,
            interruption=failure,
            provider_error=provider_failure,
        )[0]
        is False
    )


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
        "postgresql+asyncpg://slaif@127.0.0.1:5432/slaif_gateway_test",
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
        "/usr/bin/codex",
        "--ask-for-approval never",
        "--profile slaif",
        "--ephemeral",
        "--sandbox workspace-write",
        "model_providers.slaif.request_max_retries=0",
        "model_providers.slaif.stream_max_retries=0",
        "PILOT_WORKSPACE",
        "SLAIF_CODEX_BOUNDED_PILOT",
        "PILOT_OK",
        "does not enable search",
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
