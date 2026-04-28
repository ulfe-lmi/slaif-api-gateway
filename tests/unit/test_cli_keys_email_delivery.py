from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import CreatedGatewayKey, RotatedGatewayKeyResult
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult

runner = CliRunner()

OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
OLD_GATEWAY_KEY_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")
ONE_TIME_SECRET_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
EMAIL_DELIVERY_ID = uuid.UUID("99999999-9999-4999-8999-999999999999")
PLAINTEXT_KEY = "sk-slaif-public.once-only-secret"
ROTATED_PLAINTEXT_KEY = "sk-slaif-new-public.once-only-rotation-secret"


def _created_key() -> CreatedGatewayKey:
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


def _rotated_key() -> RotatedGatewayKeyResult:
    return RotatedGatewayKeyResult(
        old_gateway_key_id=OLD_GATEWAY_KEY_ID,
        new_gateway_key_id=GATEWAY_KEY_ID,
        new_plaintext_key=ROTATED_PLAINTEXT_KEY,
        new_public_key_id="new-public",
        one_time_secret_id=ONE_TIME_SECRET_ID,
        old_status="revoked",
        new_status="active",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        owner_id=OWNER_ID,
    )


def _delivery(status: str = "pending") -> PendingKeyEmailResult:
    return PendingKeyEmailResult(
        email_delivery_id=EMAIL_DELIVERY_ID,
        one_time_secret_id=ONE_TIME_SECRET_ID,
        gateway_key_id=GATEWAY_KEY_ID,
        owner_id=OWNER_ID,
        recipient_email="ada@example.org",
        status=status,
        provider_message_id="<message@example.org>" if status == "sent" else None,
    )


def test_keys_create_email_delivery_pending_keeps_existing_plaintext_policy(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_create_with_email_delivery(payload, *, email_delivery_mode):
        seen["mode"] = email_delivery_mode
        return keys_cli.KeyEmailDeliveryCliResult(
            key_result=_created_key(),
            delivery_result=_delivery("pending"),
        )

    monkeypatch.setattr(
        keys_cli,
        "_create_gateway_key_with_email_delivery",
        fake_create_with_email_delivery,
    )

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--email-delivery",
            "pending",
        ],
    )

    assert result.exit_code == 0
    assert seen["mode"] == keys_cli.EmailDeliveryMode.pending
    assert result.stdout.count(PLAINTEXT_KEY) == 1
    assert "email_delivery_id" in result.stdout
    assert "pending" in result.stderr


def test_keys_create_email_delivery_send_now_suppresses_plaintext(monkeypatch) -> None:
    async def fake_create_with_email_delivery(payload, *, email_delivery_mode):
        assert email_delivery_mode == keys_cli.EmailDeliveryMode.send_now
        return keys_cli.KeyEmailDeliveryCliResult(
            key_result=_created_key(),
            delivery_result=_delivery("sent"),
        )

    monkeypatch.setattr(
        keys_cli,
        "_create_gateway_key_with_email_delivery",
        fake_create_with_email_delivery,
    )

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--email-delivery",
            "send-now",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "plaintext_key" not in payload
    assert PLAINTEXT_KEY not in result.stdout
    assert payload["email_delivery"]["status"] == "sent"
    assert "not printed" in result.stderr


def test_keys_create_email_delivery_enqueue_suppresses_plaintext_and_reports_task(monkeypatch) -> None:
    async def fake_create_with_email_delivery(payload, *, email_delivery_mode):
        assert email_delivery_mode == keys_cli.EmailDeliveryMode.enqueue
        return keys_cli.KeyEmailDeliveryCliResult(
            key_result=_created_key(),
            delivery_result=_delivery("queued"),
            celery_task_id="task-123",
        )

    monkeypatch.setattr(
        keys_cli,
        "_create_gateway_key_with_email_delivery",
        fake_create_with_email_delivery,
    )

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--email-delivery",
            "enqueue",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "plaintext_key" not in payload
    assert payload["email_delivery"]["status"] == "queued"
    assert payload["celery_task_id"] == "task-123"
    assert PLAINTEXT_KEY not in result.stdout


def test_keys_create_rejects_multiple_secret_destinations(monkeypatch, tmp_path) -> None:
    called = False

    async def fake_create_with_email_delivery(payload, *, email_delivery_mode):
        nonlocal called
        called = True
        return keys_cli.KeyEmailDeliveryCliResult(
            key_result=_created_key(),
            delivery_result=_delivery("sent"),
        )

    monkeypatch.setattr(
        keys_cli,
        "_create_gateway_key_with_email_delivery",
        fake_create_with_email_delivery,
    )

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--email-delivery",
            "send-now",
            "--show-plaintext",
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert PLAINTEXT_KEY not in result.stdout

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--email-delivery",
            "enqueue",
            "--secret-output-file",
            str(tmp_path / "secret.txt"),
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert PLAINTEXT_KEY not in result.stdout


def test_keys_rotate_email_delivery_send_now_uses_replacement_only(monkeypatch) -> None:
    async def fake_rotate_with_email_delivery(payload, *, email_delivery_mode):
        assert payload.gateway_key_id == OLD_GATEWAY_KEY_ID
        assert email_delivery_mode == keys_cli.EmailDeliveryMode.send_now
        return keys_cli.KeyEmailDeliveryCliResult(
            key_result=_rotated_key(),
            delivery_result=_delivery("sent"),
        )

    monkeypatch.setattr(
        keys_cli,
        "_rotate_gateway_key_with_email_delivery",
        fake_rotate_with_email_delivery,
    )

    result = runner.invoke(
        app,
        [
            "keys",
            "rotate",
            str(OLD_GATEWAY_KEY_ID),
            "--email-delivery",
            "send-now",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "new_plaintext_key" not in payload
    assert ROTATED_PLAINTEXT_KEY not in result.stdout
    assert payload["email_delivery"]["gateway_key_id"] == str(GATEWAY_KEY_ID)
    assert payload["old_gateway_key_id"] == str(OLD_GATEWAY_KEY_ID)


def test_enqueue_pending_key_email_payload_contains_ids_only(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeAsyncResult:
        id = "task-123"

    class FakeTask:
        def delay(self, *args):
            seen["args"] = args
            return FakeAsyncResult()

    monkeypatch.setattr(keys_cli, "send_pending_key_email_task", FakeTask())

    task_id = keys_cli._enqueue_pending_key_email(
        one_time_secret_id=ONE_TIME_SECRET_ID,
        email_delivery_id=EMAIL_DELIVERY_ID,
        actor_admin_id=ADMIN_ID,
    )

    assert task_id == "task-123"
    assert seen["args"] == (str(ONE_TIME_SECRET_ID), str(EMAIL_DELIVERY_ID), str(ADMIN_ID))
    assert PLAINTEXT_KEY not in repr(seen["args"])
