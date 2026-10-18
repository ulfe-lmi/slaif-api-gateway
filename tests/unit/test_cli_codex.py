from __future__ import annotations

import json
import uuid

import pytest

from typer.testing import CliRunner
from typer.main import get_command

from slaif_gateway.cli import codex as codex_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.codex_qualification import (
    CODEX_COMPACT_ENDPOINT,
    CODEX_MODEL,
    CODEX_RESPONSES_ENDPOINT,
    CodexQualificationResult,
    render_codex_profile,
)

runner = CliRunner()


def _result(*, endpoint: str = CODEX_RESPONSES_ENDPOINT) -> CodexQualificationResult:
    return CodexQualificationResult(
        state="protocol_qualified",
        requested_model=CODEX_MODEL,
        provider="openai",
        endpoint=endpoint,
        route_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        paired_route_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        reason_codes=(),
        profile_version=1,
        cli_version="0.147.0",
        profile="api-key-responses-v1",
        catalog_source="bundled",
        wire_api="responses",
        real_provider_e2e=False,
    )


def test_codex_help_registers_only_read_only_commands_and_no_key_argument() -> None:
    result = runner.invoke(app, ["codex", "--help"])
    profile_help = runner.invoke(app, ["codex", "profile", "--help"])

    assert result.exit_code == 0
    assert "inspect" in result.stdout
    assert "profile" in result.stdout
    assert profile_help.exit_code == 0
    root_command = get_command(app)
    codex_command = root_command.commands["codex"]
    profile_command = codex_command.commands["profile"]
    base_url_parameter = next(
        parameter for parameter in profile_command.params if parameter.name == "base_url"
    )
    assert "--base-url" in base_url_parameter.opts
    assert all(parameter.name not in {"api_key", "secret"} for parameter in profile_command.params)
    assert "api-key" not in profile_help.stdout.lower()
    assert "secret" not in profile_help.stdout.lower()


def test_codex_inspect_json_is_deterministic_and_safe(monkeypatch) -> None:
    async def fake_inspect() -> list[CodexQualificationResult]:
        return [_result(), _result(endpoint=CODEX_COMPACT_ENDPOINT)]

    monkeypatch.setattr(codex_cli, "_inspect_codex", fake_inspect)

    result = runner.invoke(app, ["codex", "inspect", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [row["endpoint"] for row in payload["qualifications"]] == [
        CODEX_RESPONSES_ENDPOINT,
        CODEX_COMPACT_ENDPOINT,
    ]
    assert payload["qualifications"][0]["real_provider_e2e"] is False
    assert "api_key" not in result.stdout.lower()
    assert "pricing_metadata" not in result.stdout


def test_codex_inspect_text_uses_fixed_low_cardinality_fields(monkeypatch) -> None:
    async def fake_inspect() -> list[CodexQualificationResult]:
        return [_result()]

    monkeypatch.setattr(codex_cli, "_inspect_codex", fake_inspect)

    result = runner.invoke(app, ["codex", "inspect"])

    assert result.exit_code == 0
    assert "state: protocol_qualified" in result.stdout
    assert "requested_model: gpt-5.6-sol" in result.stdout
    assert "real_provider_e2e: false" in result.stdout
    assert "raw" not in result.stdout.lower()


def test_codex_profile_text_keeps_artifacts_separate(monkeypatch) -> None:
    async def fake_build(base_url: str):
        assert base_url == "https://gateway.example.org/v1"
        return _result(), render_codex_profile(base_url)

    monkeypatch.setattr(codex_cli, "_build_profile", fake_build)

    result = runner.invoke(
        app,
        ["codex", "profile", "--base-url", "https://gateway.example.org/v1"],
    )

    assert result.exit_code == 0
    assert "Merge this fragment into $CODEX_HOME/config.toml" in result.stdout
    assert "complete content in $CODEX_HOME/slaif.config.toml" in result.stdout
    assert "[profiles" not in result.stdout
    assert "model_catalog_json" not in result.stdout
    assert "codex --profile slaif" in result.stdout


def test_codex_profile_json_has_fixed_targets_and_no_credential(monkeypatch) -> None:
    async def fake_build(base_url: str):
        return _result(), render_codex_profile(base_url)

    monkeypatch.setattr(codex_cli, "_build_profile", fake_build)

    result = runner.invoke(
        app,
        [
            "codex",
            "profile",
            "--base-url",
            "http://127.0.0.1:8123/v1",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["base_config_target"] == "$CODEX_HOME/config.toml"
    assert payload["base_config_mode"] == "merge_fragment"
    assert payload["profile_config_target"] == "$CODEX_HOME/slaif.config.toml"
    assert payload["profile_config_mode"] == "complete_file"
    assert payload["invocation"] == "codex --profile slaif"
    assert payload["qualification"]["state"] == "protocol_qualified"
    assert "sk-" not in result.stdout


def test_codex_profile_requires_exact_ready_result(monkeypatch) -> None:
    async def fake_build(base_url: str):
        raise ValueError("Exactly one ready Codex protocol route pair is required.")

    monkeypatch.setattr(codex_cli, "_build_profile", fake_build)

    result = runner.invoke(
        app,
        ["codex", "profile", "--base-url", "https://gateway.example.org/v1", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "error": {
            "code": "invalid_value",
            "message": "Exactly one ready Codex protocol route pair is required.",
        }
    }


# --- audited client-module upgrade/rollback CLI commands -------------------

from contextlib import asynccontextmanager  # noqa: E402

from slaif_gateway.services.codex_module_upgrade import CodexModuleUpgradeError  # noqa: E402


def _fake_cli_db_session(raise_exc: Exception | None = None):
    @asynccontextmanager
    async def _session():
        if raise_exc is not None:
            raise raise_exc
        yield object(), object()

    return _session


def test_upgrade_key_module_without_configured_db_is_safe_error(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()

    key_id = uuid.uuid4()
    result = runner.invoke(
        app,
        [
            "codex",
            "upgrade-key-module",
            str(key_id),
            "--target",
            "0162-v1",
            "--reason",
            "operator upgrade",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "database_not_configured"
    assert "Traceback" not in result.stdout


def test_upgrade_key_module_unexpected_audit_failure_stays_safe(monkeypatch) -> None:
    canary = "private-audit-canary-token"

    async def _failing_mutation(**_: object) -> object:
        raise RuntimeError(f"audit storage failed: {canary}")

    monkeypatch.setattr(codex_cli, "cli_db_session", _fake_cli_db_session())
    monkeypatch.setattr(codex_cli, "mutate_codex_client_module", _failing_mutation)

    key_id = uuid.uuid4()
    result = runner.invoke(
        app,
        [
            "codex",
            "upgrade-key-module",
            str(key_id),
            "--target",
            "0162-v1",
            "--reason",
            "operator upgrade",
            "--apply",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "command_failed"
    assert canary not in result.stdout
    assert "Traceback" not in result.stdout
    assert "RuntimeError" not in result.stdout


def test_upgrade_key_module_expected_error_preserves_specific_code(monkeypatch) -> None:
    async def _mismatching_mutation(**_: object) -> object:
        raise CodexModuleUpgradeError(
            "The gateway key client-module identity does not match the expected source tuple.",
            code="codex_module_upgrade_identity_mismatch",
        )

    monkeypatch.setattr(codex_cli, "cli_db_session", _fake_cli_db_session())
    monkeypatch.setattr(codex_cli, "mutate_codex_client_module", _mismatching_mutation)

    key_id = uuid.uuid4()
    result = runner.invoke(
        app,
        [
            "codex",
            "rollback-key-module",
            str(key_id),
            "--from-target",
            "0149-v5",
            "--reason",
            "operator rollback",
            "--apply",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "codex_module_upgrade_identity_mismatch"
    assert payload["error"]["message"] == (
        "The gateway key client-module identity does not match the expected source tuple."
    )


def test_unsupported_target_selector_is_not_echoed(monkeypatch) -> None:
    monkeypatch.setattr(codex_cli, "cli_db_session", _fake_cli_db_session())
    bad_selector = "weird-selector-canary"

    for args in (
        [
            "codex",
            "upgrade-key-module",
            str(uuid.uuid4()),
            "--target",
            bad_selector,
            "--reason",
            "operator upgrade",
            "--json",
        ],
        [
            "codex",
            "rollback-key-module",
            str(uuid.uuid4()),
            "--from-target",
            bad_selector,
            "--reason",
            "operator rollback",
            "--json",
        ],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code != 0
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "invalid_parameter"
        assert bad_selector not in result.stdout


@pytest.mark.parametrize(
    ("command", "selector_option", "selector_value"),
    [
        ("upgrade-key-module", "--target", "0162-v1"),
        ("rollback-key-module", "--from-target", "0149-v5"),
    ],
)
@pytest.mark.parametrize("exc_type", [RuntimeError, ValueError])
def test_module_mutation_unexpected_exception_never_echoes_details(
    monkeypatch, command, selector_option, selector_value, exc_type
) -> None:
    canary = "synthetic-private-canary"

    async def _failing_mutation(**_: object) -> object:
        raise exc_type(f"unexpected failure detail: {canary}")

    monkeypatch.setattr(codex_cli, "cli_db_session", _fake_cli_db_session())
    monkeypatch.setattr(codex_cli, "mutate_codex_client_module", _failing_mutation)

    key_id = uuid.uuid4()
    result = runner.invoke(
        app,
        [
            "codex",
            command,
            str(key_id),
            selector_option,
            selector_value,
            "--reason",
            "operator upgrade",
            "--apply",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload == {"error": {"code": "command_failed", "message": "Command failed"}}
    output = result.stdout
    stderr = getattr(result, "stderr", "") or ""
    assert canary not in output
    assert canary not in stderr
    assert "Traceback" not in output
    assert exc_type.__name__ not in output
