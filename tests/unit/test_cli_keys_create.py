from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, CreatedGatewayKey

runner = CliRunner()

OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
COHORT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
ONE_TIME_SECRET_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
PLAINTEXT_KEY = "sk-slaif-public.once-only-secret"


def _created_result() -> CreatedGatewayKey:
    return CreatedGatewayKey(
        gateway_key_id=GATEWAY_KEY_ID,
        owner_id=OWNER_ID,
        public_key_id="public",
        display_prefix="sk-slaif-public",
        plaintext_key=PLAINTEXT_KEY,
        one_time_secret_id=ONE_TIME_SECRET_ID,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
    )


def test_keys_help_registers_commands() -> None:
    result = runner.invoke(app, ["keys", "--help"])

    assert result.exit_code == 0
    for command in (
        "create",
        "list",
        "show",
        "suspend",
        "activate",
        "revoke",
        "extend",
        "set-limits",
        "set-rate-limits",
        "reset-usage",
        "rotate",
    ):
        assert command in result.stdout


def test_keys_create_prints_plaintext_key_once(monkeypatch) -> None:
    seen: dict[str, CreateGatewayKeyInput] = {}

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        seen["payload"] = payload
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--cohort-id",
            str(COHORT_ID),
            "--valid-from",
            "2026-01-01T00:00:00+00:00",
            "--valid-days",
            "31",
            "--cost-limit-eur",
            "12.50",
            "--token-limit-total",
            "1000",
            "--request-limit-total",
            "20",
            "--allowed-model",
            "gpt-test-mini",
            "--allowed-endpoint",
            "chat.completions",
            "--actor-admin-id",
            str(ADMIN_ID),
            "--reason",
            "classroom key",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.count(PLAINTEXT_KEY) == 1
    assert "shown once" in result.stderr
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout

    payload = seen["payload"]
    assert payload.owner_id == OWNER_ID
    assert payload.cohort_id == COHORT_ID
    assert payload.valid_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert payload.valid_until == datetime(2026, 2, 1, tzinfo=UTC)
    assert payload.cost_limit_eur == Decimal("12.50")
    assert payload.token_limit_total == 1000
    assert payload.request_limit_total == 20
    assert payload.allowed_models == ["gpt-test-mini"]
    assert payload.allowed_endpoints == ["chat.completions"]
    assert payload.created_by_admin_id == ADMIN_ID
    assert payload.note == "classroom key"


def test_keys_create_json_requires_explicit_secret_output(monkeypatch) -> None:
    called = False

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        nonlocal called
        called = True
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert called is False
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_parameter"
    assert PLAINTEXT_KEY not in result.stdout


def test_keys_create_json_show_plaintext_includes_key_and_warns(monkeypatch) -> None:
    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--json",
            "--show-plaintext",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["plaintext_key"] == PLAINTEXT_KEY
    assert result.stdout.count(PLAINTEXT_KEY) == 1
    assert "shown once" in result.stderr
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout


def test_keys_create_json_secret_output_file_excludes_stdout_secret(monkeypatch, tmp_path) -> None:
    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)
    secret_path = tmp_path / "gateway-key.txt"

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--json",
            "--secret-output-file",
            str(secret_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "plaintext_key" not in payload
    assert PLAINTEXT_KEY not in result.stdout
    assert secret_path.read_text(encoding="utf-8") == f"{PLAINTEXT_KEY}\n"
    assert secret_path.stat().st_mode & 0o777 == 0o600
    assert "written once" in result.stderr


def test_keys_create_rejects_conflicting_secret_outputs(monkeypatch, tmp_path) -> None:
    called = False

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        nonlocal called
        called = True
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--json",
            "--show-plaintext",
            "--secret-output-file",
            str(tmp_path / "gateway-key.txt"),
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert PLAINTEXT_KEY not in result.stdout


def test_keys_create_rejects_existing_secret_output_file_before_service(monkeypatch, tmp_path) -> None:
    called = False

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        nonlocal called
        called = True
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)
    secret_path = tmp_path / "gateway-key.txt"
    secret_path.write_text("existing\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--json",
            "--secret-output-file",
            str(secret_path),
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert secret_path.read_text(encoding="utf-8") == "existing\n"
    assert PLAINTEXT_KEY not in result.stdout
