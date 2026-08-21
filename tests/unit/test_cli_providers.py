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
    for command in ("add", "list", "show", "enable", "disable", "discover-models", "setup-models"):
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


def test_providers_add_generic_http_requires_explicit_safe_ack(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_add_provider(**kwargs: object) -> FakeProvider:
        seen.update(kwargs)
        return FakeProvider(provider="lan-qwen-text", base_url="http://qwen.lan/v1")

    monkeypatch.setattr(providers_cli, "_add_provider", fake_add_provider)

    result = runner.invoke(
        app,
        [
            "providers", "add", "--provider", "lan-qwen-text",
            "--base-url", "http://qwen.lan/v1",
            "--api-key-env-var", "LAN_QWEN_KEY",
            "--reason", "operator-owned LAN reverse proxy",
            "--confirm-insecure-http", "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["confirm_insecure_http"] is True
    assert seen["reason"] == "operator-owned LAN reverse proxy"
    assert "sk-" not in result.stdout


def test_providers_add_does_not_accept_secret_value_option() -> None:
    result = runner.invoke(
        app,
        ["providers", "add", "--provider", "openai", "--api-key", "sk-real-secret"],
    )

    assert result.exit_code != 0
    assert "sk-real-secret" not in result.stdout


def test_providers_discover_models_json_is_safe_preview(monkeypatch) -> None:
    async def fake_discover(provider_or_id: str) -> dict[str, object]:
        assert provider_or_id == "lan-qwen"
        return {"provider": "lan-qwen", "models": ["qwen/a"]}

    monkeypatch.setattr(providers_cli, "_discover_models", fake_discover)
    result = runner.invoke(app, ["providers", "discover-models", "lan-qwen", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"provider": "lan-qwen", "models": ["qwen/a"]}


def test_providers_setup_models_uses_explicit_confirmation_and_safe_json(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_setup(**kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {
            "provider": "lan-qwen",
            "models": ["qwen/a"],
            "route_ids": ["route-id"],
            "pricing_rule_ids": ["pricing-id"],
            "route_count": 1,
            "pricing_rule_count": 1,
            "preset": "chat_text_v1",
            "enabled": False,
            "pricing_mode": "local_zero",
        }

    monkeypatch.setattr(providers_cli, "_setup_models", fake_setup)
    result = runner.invoke(
        app,
        [
            "providers", "setup-models", "lan-qwen", "--model", "qwen/a",
            "--public-model-id", "qwen/a=public-a", "--preset", "chat_text_v1",
            "--pricing-mode", "local_zero", "--confirm-local-zero",
            "--confirm-execute", "--reason", "operator confirmed", "--json",
        ],
    )
    assert result.exit_code == 0
    assert seen["public_model_entries"] == ["qwen/a=public-a"]
    assert seen["confirm_local_zero"] is True
    payload = json.loads(result.stdout)
    assert set(payload) == {
        "provider", "models", "route_ids", "pricing_rule_ids", "route_count",
        "pricing_rule_count", "preset", "enabled", "pricing_mode",
    }
    assert "operator confirmed" not in result.stdout


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
