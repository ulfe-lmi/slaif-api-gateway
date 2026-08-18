from __future__ import annotations

import json
import uuid

from typer.testing import CliRunner

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
    assert "--base-url" in profile_help.stdout
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
