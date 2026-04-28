from __future__ import annotations

import json
import uuid

from typer.testing import CliRunner

from slaif_gateway.cli import email as email_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult
from slaif_gateway.services.email_service import EmailSendResult

runner = CliRunner()


def test_email_help_registers_commands() -> None:
    result = runner.invoke(app, ["email", "--help"])

    assert result.exit_code == 0
    assert "test" in result.stdout
    assert "send-pending-key" in result.stdout


def test_email_test_uses_safe_service(monkeypatch) -> None:
    async def fake_send_test_email(*, to: str, subject: str, body: str | None):
        assert to == "ada@example.org"
        assert subject == "Subject"
        assert body == "Hello"
        return EmailSendResult(
            message_id="<message@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )

    monkeypatch.setattr(email_cli, "_send_test_email", fake_send_test_email)

    result = runner.invoke(
        app,
        ["email", "test", "--to", "ada@example.org", "--subject", "Subject", "--body", "Hello", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "sent"
    assert "sk-slaif-" not in result.stdout


def test_send_pending_key_send_now_calls_service(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    seen: dict[str, object] = {}

    async def fake_send_pending_key_now(**kwargs):
        seen.update(kwargs)
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id,
            one_time_secret_id=secret_id,
            gateway_key_id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            recipient_email="ada@example.org",
            status="sent",
            provider_message_id="<message@example.org>",
        )

    monkeypatch.setattr(email_cli, "_send_pending_key_now", fake_send_pending_key_now)

    result = runner.invoke(
        app,
        ["email", "send-pending-key", "--one-time-secret-id", str(secret_id), "--send-now", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "sent"
    assert payload["one_time_secret_id"] == str(secret_id)
    assert seen["one_time_secret_id"] == secret_id
    assert "ada@example.org" not in result.stdout
    assert "sk-slaif-" not in result.stdout


def test_send_pending_key_enqueue_payload_ids_only(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    seen: dict[str, object] = {}

    class FakeTask:
        @staticmethod
        def delay(*args):
            seen["args"] = args

            class AsyncResult:
                id = "celery-task-id"

            return AsyncResult()

    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)

    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--enqueue",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "queued"
    assert seen["args"] == (str(secret_id), str(delivery_id), None)
    assert "sk-slaif-" not in result.stdout
    assert "plaintext" not in result.stdout.lower()
