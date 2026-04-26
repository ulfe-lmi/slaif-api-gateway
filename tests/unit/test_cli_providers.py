from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import providers as providers_cli
from slaif_gateway.cli.main import app

runner = CliRunner()
PROVIDER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


@dataclass
class FakeProvider:
    id: uuid.UUID = PROVIDER_ID
    provider: str = "openai"
    display_name: str = "OpenAI"
    kind: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key_env_var: str = "OPENAI_UPSTREAM_API_KEY"
    enabled: bool = True
    timeout_seconds: int = 300
    max_retries: int = 2
    notes: str | None = "safe"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)


def test_providers_help_registers_commands() -> None:
    result = runner.invoke(app, ["providers", "--help"])

    assert result.exit_code == 0
    for command in ("add", "list", "show", "enable", "disable"):
        assert command in result.stdout


def test_providers_add_stores_env_var_name_only(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_add_provider(**kwargs: object) -> FakeProvider:
        seen.update(kwargs)
        return FakeProvider()

    monkeypatch.setattr(providers_cli, "_add_provider", fake_add_provider)

    result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--provider",
            "openai",
            "--api-key-env-var",
            "OPENAI_UPSTREAM_API_KEY",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["api_key_env_var"] == "OPENAI_UPSTREAM_API_KEY"
    payload = json.loads(result.stdout)
    assert payload["api_key_env_var"] == "OPENAI_UPSTREAM_API_KEY"
    assert "sk-" not in result.stdout


def test_providers_add_does_not_accept_secret_value_option() -> None:
    result = runner.invoke(
        app,
        ["providers", "add", "--provider", "openai", "--api-key", "sk-real-secret"],
    )

    assert result.exit_code != 0
    assert "sk-real-secret" not in result.stdout


def test_providers_list_show_and_toggle_output_safe(monkeypatch) -> None:
    async def fake_list_providers(*, enabled_only: bool, limit: int) -> list[FakeProvider]:
        assert enabled_only is True
        assert limit == 5
        return [FakeProvider()]

    async def fake_show_provider(provider_or_id: str) -> FakeProvider:
        assert provider_or_id == "openai"
        return FakeProvider()

    async def fake_set_provider_enabled(provider_or_id: str, *, enabled: bool) -> FakeProvider:
        assert provider_or_id == "openai"
        return FakeProvider(enabled=enabled)

    monkeypatch.setattr(providers_cli, "_list_providers", fake_list_providers)
    monkeypatch.setattr(providers_cli, "_show_provider", fake_show_provider)
    monkeypatch.setattr(providers_cli, "_set_provider_enabled", fake_set_provider_enabled)

    list_result = runner.invoke(app, ["providers", "list", "--enabled-only", "--limit", "5", "--json"])
    show_result = runner.invoke(app, ["providers", "show", "openai", "--json"])
    disable_result = runner.invoke(app, ["providers", "disable", "openai", "--json"])
    enable_result = runner.invoke(app, ["providers", "enable", "openai", "--json"])

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert disable_result.exit_code == 0
    assert enable_result.exit_code == 0
    assert json.loads(list_result.stdout)["providers"][0]["provider"] == "openai"
    assert json.loads(show_result.stdout)["provider"] == "openai"
    assert json.loads(disable_result.stdout)["enabled"] is False
    assert json.loads(enable_result.stdout)["enabled"] is True
    for output in (list_result.stdout, show_result.stdout, disable_result.stdout):
        assert "password_hash" not in output
        assert "token_hash" not in output
        assert "sk-real" not in output
