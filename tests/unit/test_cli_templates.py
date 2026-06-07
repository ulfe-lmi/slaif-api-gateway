from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from typer.testing import CliRunner

from slaif_gateway.cli import templates as templates_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.key_template_service import KeyTemplateError

runner = CliRunner()
KEY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SECRET_VALUE = "sk-live-secret-must-not-render"
PROMPT_TEXT = "prompt text must not render"
COMPLETION_TEXT = "completion text must not render"


def test_templates_help_registers_create_from_calibration() -> None:
    result = runner.invoke(app, ["templates", "--help"])

    assert result.exit_code == 0
    assert "create-from-calibration" in result.stdout


def test_create_from_calibration_outputs_safe_text(monkeypatch) -> None:
    async def fake_create(**kwargs):
        assert kwargs["gateway_key_id"] == str(KEY_ID)
        assert kwargs["confirm_create_template"] is True
        return _created_result()

    monkeypatch.setattr(templates_cli, "_create_from_calibration", fake_create)

    result = runner.invoke(
        app,
        [
            "templates",
            "create-from-calibration",
            "--gateway-key-id",
            str(KEY_ID),
            "--name",
            "Participants",
            "--confirm-create-template",
            "--reason",
            "Reviewed",
        ],
    )

    assert result.exit_code == 0
    assert "Key template created" in result.stdout
    assert "No participant keys were created" in result.stdout
    assert "gpt-4.1-mini" in result.stdout
    assert "Chat live-burn: on" in result.stdout
    assert SECRET_VALUE not in result.stdout
    assert PROMPT_TEXT not in result.stdout
    assert COMPLETION_TEXT not in result.stdout


def test_create_from_calibration_json_is_valid_and_safe(monkeypatch) -> None:
    async def fake_create(**kwargs):
        return _created_result()

    monkeypatch.setattr(templates_cli, "_create_from_calibration", fake_create)

    result = runner.invoke(
        app,
        [
            "templates",
            "create-from-calibration",
            "--gateway-key-id",
            str(KEY_ID),
            "--name",
            "Participants",
            "--confirm-create-template",
            "--reason",
            "Reviewed",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["template"]["name"] == "Participants"
    assert payload["revision"]["revision_number"] == 1
    assert payload["revision"]["chat_streaming_live_burn_policy"] == {
        "version": 1,
        "enabled": True,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert SECRET_VALUE not in serialized
    assert PROMPT_TEXT not in serialized
    assert COMPLETION_TEXT not in serialized


def test_create_from_calibration_rejects_missing_confirmation(monkeypatch) -> None:
    async def fake_create(**kwargs):
        raise KeyTemplateError("Confirm template creation before continuing.")

    monkeypatch.setattr(templates_cli, "_create_from_calibration", fake_create)

    result = runner.invoke(
        app,
        ["templates", "create-from-calibration", "--gateway-key-id", str(KEY_ID), "--name", "Participants"],
    )

    assert result.exit_code == 1
    assert "Confirm template creation" in result.stderr


def test_create_from_calibration_rejects_missing_reason(monkeypatch) -> None:
    async def fake_create(**kwargs):
        raise KeyTemplateError("Audit reason is required.")

    monkeypatch.setattr(templates_cli, "_create_from_calibration", fake_create)

    result = runner.invoke(
        app,
        [
            "templates",
            "create-from-calibration",
            "--gateway-key-id",
            str(KEY_ID),
            "--name",
            "Participants",
            "--confirm-create-template",
        ],
    )

    assert result.exit_code == 1
    assert "Audit reason" in result.stderr


def test_create_from_calibration_rejects_standard_key(monkeypatch) -> None:
    async def fake_create(**kwargs):
        raise KeyTemplateError("Calibration summaries are available only for trusted calibration keys.")

    monkeypatch.setattr(templates_cli, "_create_from_calibration", fake_create)

    result = runner.invoke(
        app,
        [
            "templates",
            "create-from-calibration",
            "--gateway-key-id",
            str(KEY_ID),
            "--name",
            "Participants",
            "--confirm-create-template",
            "--reason",
            "Reviewed",
        ],
    )

    assert result.exit_code == 1
    assert "trusted calibration keys" in result.stderr


def _created_result():
    template_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    revision_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    audit_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    template = SimpleNamespace(
        id=template_id,
        name="Participants",
        status="active",
        current_revision_id=revision_id,
    )
    revision = SimpleNamespace(
        id=revision_id,
        revision_number=1,
        source_type="calibration_proposal",
        source_calibration_gateway_key_id=KEY_ID,
        source_time_window_start=now,
        source_time_window_end=now,
        source_multiplier=Decimal("3"),
        allowed_endpoints=["/v1/chat/completions"],
        allowed_models=["gpt-4.1-mini"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=["web_search_options"],
        request_limit_total=6,
        token_limit_total=90,
        cost_limit_eur=Decimal("0.030000000"),
        template_snapshot={"warnings": ["review hosted capabilities"]},
    )
    audit = SimpleNamespace(id=audit_id)
    return SimpleNamespace(template=template, revision=revision, audit_log=audit)
