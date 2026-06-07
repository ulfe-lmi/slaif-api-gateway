from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, CreatedGatewayKey
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)

runner = CliRunner()

OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
COHORT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
ONE_TIME_SECRET_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
PLAINTEXT_KEY = "sk-slaif-public.once-only-secret"


TEMPLATE_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")
TEMPLATE_REVISION_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")


def _created_result(
    *,
    template_id: uuid.UUID | None = None,
    template_revision_id: uuid.UUID | None = None,
) -> CreatedGatewayKey:
    return CreatedGatewayKey(
        gateway_key_id=GATEWAY_KEY_ID,
        owner_id=OWNER_ID,
        public_key_id="public",
        display_prefix="sk-slaif-public",
        plaintext_key=PLAINTEXT_KEY,
        one_time_secret_id=ONE_TIME_SECRET_ID,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        template_id=template_id,
        template_revision_id=template_revision_id,
    )


def test_keys_help_registers_commands() -> None:
    result = runner.invoke(app, ["keys", "--help"])

    assert result.exit_code == 0
    for command in (
        "create",
        "create-from-template",
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
            "/v1/chat/completions",
            "--allow-all-models",
            "--allow-all-endpoints",
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
    assert payload.allowed_endpoints == ["/v1/chat/completions"]
    assert payload.allow_all_models is True
    assert payload.allow_all_endpoints is True
    assert payload.created_by_admin_id == ADMIN_ID
    assert payload.note == "classroom key"
    assert payload.chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": True,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }


def test_keys_create_parses_chat_streaming_live_burn_flags(monkeypatch) -> None:
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
            "--valid-days",
            "31",
            "--no-chat-streaming-live-burn",
            "--chat-streaming-live-burn-cost-margin-eur",
            "-0.25",
            "--chat-streaming-live-burn-token-margin",
            "-250",
            "--reason",
            "classroom key",
        ],
    )

    assert result.exit_code == 0
    assert seen["payload"].chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": False,
        "cost_margin_eur": "-0.250000000",
        "token_margin": -250,
    }


def test_keys_create_from_template_outputs_safe_standard_key(monkeypatch) -> None:
    async def fake_create(**kwargs):
        assert kwargs["template_revision_id"] == TEMPLATE_REVISION_ID
        assert kwargs["owner_id"] == OWNER_ID
        assert kwargs["cohort_id"] == COHORT_ID
        assert kwargs["reason"] == "reviewed template"
        assert kwargs["confirm_create_key_from_template"] is True
        return (
            SimpleNamespace(
                created_key=_created_result(
                    template_id=TEMPLATE_ID,
                    template_revision_id=TEMPLATE_REVISION_ID,
                ),
                template=SimpleNamespace(id=TEMPLATE_ID, name="Participants"),
                revision=SimpleNamespace(id=TEMPLATE_REVISION_ID, revision_number=1),
                audit_log=SimpleNamespace(id=uuid.uuid4()),
            ),
            None,
            None,
        )

    monkeypatch.setattr(keys_cli, "_create_key_from_template", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create-from-template",
            "--template-revision-id",
            str(TEMPLATE_REVISION_ID),
            "--owner-id",
            str(OWNER_ID),
            "--cohort-id",
            str(COHORT_ID),
            "--valid-days",
            "14",
            "--reason",
            "reviewed template",
            "--confirm-create-key-from-template",
        ],
    )

    assert result.exit_code == 0
    assert PLAINTEXT_KEY in result.stdout
    assert "standard" in result.stdout
    assert str(TEMPLATE_ID) in result.stdout
    assert str(TEMPLATE_REVISION_ID) in result.stdout
    assert "No templates, revisions, or existing keys were changed" in result.stdout
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout


def test_keys_create_from_template_rejects_missing_confirmation(monkeypatch) -> None:
    called = False

    async def fake_create(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(keys_cli, "_create_key_from_template", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create-from-template",
            "--template-revision-id",
            str(TEMPLATE_REVISION_ID),
            "--owner-id",
            str(OWNER_ID),
            "--valid-days",
            "14",
            "--reason",
            "reviewed template",
        ],
    )

    assert result.exit_code == 1
    assert called is False
    assert "Confirm key creation from template" in result.stderr


def test_keys_create_from_template_json_is_secret_safe(monkeypatch) -> None:
    async def fake_create(**kwargs):
        return (
            SimpleNamespace(
                created_key=_created_result(
                    template_id=TEMPLATE_ID,
                    template_revision_id=TEMPLATE_REVISION_ID,
                ),
                template=SimpleNamespace(id=TEMPLATE_ID, name="Participants"),
                revision=SimpleNamespace(id=TEMPLATE_REVISION_ID, revision_number=1),
                audit_log=SimpleNamespace(id=uuid.uuid4()),
            ),
            None,
            None,
        )

    monkeypatch.setattr(keys_cli, "_create_key_from_template", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create-from-template",
            "--template-revision-id",
            str(TEMPLATE_REVISION_ID),
            "--owner-id",
            str(OWNER_ID),
            "--valid-days",
            "14",
            "--reason",
            "reviewed template",
            "--confirm-create-key-from-template",
            "--json",
            "--show-plaintext",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["template_id"] == str(TEMPLATE_ID)
    assert payload["template_revision_id"] == str(TEMPLATE_REVISION_ID)
    assert payload["plaintext_key"] == PLAINTEXT_KEY
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout


def test_keys_create_from_template_rejects_missing_reason(monkeypatch) -> None:
    called = False

    async def fake_create(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(keys_cli, "_create_key_from_template", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create-from-template",
            "--template-revision-id",
            str(TEMPLATE_REVISION_ID),
            "--owner-id",
            str(OWNER_ID),
            "--valid-days",
            "14",
            "--confirm-create-key-from-template",
        ],
    )

    assert result.exit_code == 1
    assert called is False
    assert "--reason is required" in result.stderr


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


def test_keys_create_trusted_calibration_requires_confirmation(monkeypatch) -> None:
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
            "--valid-days",
            "2",
            "--request-limit-total",
            "5",
            "--trusted-calibration",
            "--reason",
            "trusted organizer discovery",
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert "trusted calibration" in result.stderr.lower() or "trusted calibration" in result.stdout.lower()


def test_keys_create_trusted_calibration_builds_payload_and_warns(monkeypatch) -> None:
    seen: dict[str, CreateGatewayKeyInput] = {}

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        seen["payload"] = payload
        return CreatedGatewayKey(
            gateway_key_id=GATEWAY_KEY_ID,
            owner_id=OWNER_ID,
            public_key_id="public",
            display_prefix="sk-slaif-public",
            plaintext_key=PLAINTEXT_KEY,
            one_time_secret_id=ONE_TIME_SECRET_ID,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=datetime(2026, 2, 1, tzinfo=UTC),
            key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        )

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-days",
            "2",
            "--request-limit-total",
            "5",
            "--trusted-calibration",
            "--confirm-trusted-calibration",
            "--reason",
            "trusted organizer discovery",
        ],
    )

    assert result.exit_code == 0
    assert "Trusted calibration key" in result.stderr
    assert result.stdout.count(PLAINTEXT_KEY) == 1
    payload = seen["payload"]
    assert payload.key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION
    assert payload.capability_policy_mode == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    assert payload.confirm_trusted_calibration is True
    assert payload.request_limit_total == 5
    assert payload.calibration_metadata == {"creation_channel": "cli"}


def test_keys_create_trusted_calibration_rejects_send_now_email(monkeypatch) -> None:
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
            "--valid-days",
            "2",
            "--request-limit-total",
            "5",
            "--trusted-calibration",
            "--confirm-trusted-calibration",
            "--email-delivery",
            "send-now",
            "--reason",
            "trusted organizer discovery",
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert "email-delivery none or pending" in result.stderr


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
