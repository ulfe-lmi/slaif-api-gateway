from __future__ import annotations

import json
import uuid

from typer.testing import CliRunner

from slaif_gateway.cli import email as email_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.email_delivery_service import KeyEmailDeliverySendability, PendingKeyEmailResult
from slaif_gateway.services.email_service import EmailSendResult

runner = CliRunner()


def test_email_help_registers_commands() -> None:
    result = runner.invoke(app, ["email", "--help"])

    assert result.exit_code == 0
    assert "test" in result.stdout
    assert "send-pending-key" in result.stdout
    assert "list" in result.stdout
    assert "show" in result.stdout


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

    async def fake_enqueue_audit(**kwargs):
        seen["audit"] = kwargs

    async def fake_binding(delivery_uuid):
        return "pending", secret_id

    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)
    monkeypatch.setattr(
        email_cli,
        "_get_key_email_sendability",
        lambda email_delivery_id: _sendable(email_delivery_id, secret_id),
    )
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", fake_enqueue_audit)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

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
    # broker payload stays EXACTLY the existing three UUIDs
    assert seen["args"] == (str(secret_id), str(delivery_id), None)
    # 202-a: the safe enqueue-REQUEST intent audit is recorded before dispatch
    assert seen["audit"]["one_time_secret_id"] == secret_id
    assert seen["audit"]["email_delivery_id"] == delivery_id
    assert seen["audit"]["retry_failed"] is False
    assert "sk-slaif-" not in result.stdout
    assert "plaintext" not in result.stdout.lower()


def test_send_pending_key_enqueue_refuses_ambiguous_delivery(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    class FakeTask:
        @staticmethod
        def delay(*args):
            raise AssertionError("Celery should not be called")

    async def fake_blocked(email_delivery_id: uuid.UUID) -> KeyEmailDeliverySendability:
        return KeyEmailDeliverySendability(
            email_delivery_id=email_delivery_id,
            one_time_secret_id=secret_id,
            email_delivery_status="ambiguous",
            one_time_secret_status="present",
            can_send=False,
            blocking_reason="SMTP may have accepted this email; rotate the key.",
        )

    def audit_must_not_run(**kwargs):
        raise AssertionError("enqueue-REQUEST audit must not be recorded on refusal")

    async def fake_binding(delivery_uuid):
        return "ambiguous", secret_id

    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)
    monkeypatch.setattr(email_cli, "_get_key_email_sendability", fake_blocked)
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", audit_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

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

    assert result.exit_code == 1
    assert "rotate the key" in result.stdout
    assert "sk-slaif-" not in result.stdout
    assert "plaintext" not in result.stdout.lower()


async def _sendable(email_delivery_id: uuid.UUID, secret_id: uuid.UUID) -> KeyEmailDeliverySendability:
    return KeyEmailDeliverySendability(
        email_delivery_id=email_delivery_id,
        one_time_secret_id=secret_id,
        email_delivery_status="pending",
        one_time_secret_status="present",
        can_send=True,
        blocking_reason=None,
    )


# --- 202-a focused CLI cases -------------------------------------------------


def test_send_now_refuses_failed_delivery_without_retry_flag(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    def sender_must_not_run(**kwargs):
        raise AssertionError("sender must not run for a FAILED row without --retry-failed")

    async def fake_binding(delivery_uuid):
        return "failed", secret_id

    monkeypatch.setattr(email_cli, "_send_pending_key_now", sender_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "retry-failed" in result.stdout


def test_enqueue_refuses_mismatched_supplied_secret_before_dispatch(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    other_secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    class FakeTask:
        @staticmethod
        def delay(*args):
            raise AssertionError("Celery must not be called for a mismatched secret")

    def audit_must_not_run(**kwargs):
        raise AssertionError("enqueue-REQUEST audit must not be recorded on refusal")

    async def fake_binding(delivery_uuid):
        return "pending", other_secret_id

    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", audit_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

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

    assert result.exit_code == 1
    assert "does not match" in result.stdout


def test_retry_failed_requires_nonblank_reason(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    def sender_must_not_run(**kwargs):
        raise AssertionError("sender must not run with a blank retry reason")

    async def fake_binding(delivery_uuid):
        return "failed", secret_id

    monkeypatch.setattr(email_cli, "_send_pending_key_now", sender_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--retry-failed",
            "--reason",
            "   ",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "nonblank" in result.stdout


def test_retry_flag_on_pending_delivery_is_refused(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    def sender_must_not_run(**kwargs):
        raise AssertionError("sender must not run: --retry-failed needs a FAILED row")

    async def fake_binding(delivery_uuid):
        return "pending", secret_id

    monkeypatch.setattr(email_cli, "_send_pending_key_now", sender_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--retry-failed",
            "--reason",
            "retry",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "FAILED" in result.stdout


def test_retry_failed_with_flag_and_reason_passes_preflight(monkeypatch) -> None:
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

    async def fake_binding(delivery_uuid):
        return "failed", secret_id

    monkeypatch.setattr(email_cli, "_send_pending_key_now", fake_send_pending_key_now)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--retry-failed",
            "--reason",
            "retry after smtp failure",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "sent"
    assert seen["reason"] == "retry after smtp failure"


def test_enqueue_reason_with_known_secret_shape_refused_without_echo(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    canary = "sk-slaif-canary202a00"

    class FakeTask:
        @staticmethod
        def delay(*args):
            raise AssertionError("Celery must not be called with a credential-bearing reason")

    def audit_must_not_run(**kwargs):
        raise AssertionError("enqueue-REQUEST audit must not be recorded on refusal")

    async def fake_binding(delivery_uuid):
        return "pending", secret_id

    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", audit_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

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
            "--reason",
            f"use key {canary} now",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "credential" in result.stdout
    assert canary not in result.stdout


def test_list_rejects_naive_created_from(monkeypatch) -> None:
    def list_must_not_run(**kwargs):
        raise AssertionError("service must not run for a naive time bound")

    monkeypatch.setattr(email_cli, "_list_inspection", list_must_not_run)

    result = runner.invoke(
        app,
        ["email", "list", "--created-from", "2026-01-01T00:00:00", "--json"],
    )

    assert result.exit_code == 1
    assert "aware UTC" in result.stdout


def test_list_rejects_reversed_time_window(monkeypatch) -> None:
    def list_must_not_run(**kwargs):
        raise AssertionError("service must not run for a reversed window")

    monkeypatch.setattr(email_cli, "_list_inspection", list_must_not_run)

    result = runner.invoke(
        app,
        [
            "email",
            "list",
            "--created-from",
            "2026-02-01T00:00:00+00:00",
            "--created-until",
            "2026-01-01T00:00:00+00:00",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "later" in result.stdout


def test_list_rejects_queued_status(monkeypatch) -> None:
    def list_must_not_run(**kwargs):
        raise AssertionError("service must not run for a non-persisted status")

    monkeypatch.setattr(email_cli, "_list_inspection", list_must_not_run)

    result = runner.invoke(app, ["email", "list", "--status", "queued", "--json"])

    assert result.exit_code == 1
    assert "pending" in result.stdout and "cancelled" in result.stdout
    assert "queued" not in result.stdout.split("must be one of")[1].split(",")[0]


def test_list_rejects_non_integer_page_bounds_without_echo(monkeypatch) -> None:
    def list_must_not_run(**kwargs):
        raise AssertionError("service must not run for non-integer page bounds")

    monkeypatch.setattr(email_cli, "_list_inspection", list_must_not_run)
    canary = "sk-slaif-canary202a00"

    for flag in ("--limit", "--offset"):
        result = runner.invoke(app, ["email", "list", flag, canary, "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "invalid_parameter"
        assert "integer" in payload["error"]["message"]
        assert canary not in result.stdout
        assert canary not in (result.stderr or "")

    result = runner.invoke(app, ["email", "list", "--limit", "abc", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_parameter"


def test_list_page_bounds_defaults_and_explicit_integers(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_list(**kwargs):
        seen.update(kwargs)
        from slaif_gateway.schemas.email_inspection import EmailDeliveryListPage

        return EmailDeliveryListPage(items=(), limit=kwargs["limit"], offset=kwargs["offset"])

    monkeypatch.setattr(email_cli, "_list_inspection", fake_list)

    result = runner.invoke(app, ["email", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["limit"] == 50 and payload["offset"] == 0
    assert seen["limit"] == 50 and seen["offset"] == 0

    result = runner.invoke(app, ["email", "list", "--limit", "2", "--offset", "3", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["limit"] == 2 and payload["offset"] == 3
    assert seen["limit"] == 2 and seen["offset"] == 3


def test_list_rejects_out_of_range_page_bounds_without_echo(monkeypatch) -> None:
    def list_must_not_run(**kwargs):
        raise AssertionError("service must not run for out-of-range page bounds")

    monkeypatch.setattr(email_cli, "_list_inspection", list_must_not_run)

    result = runner.invoke(app, ["email", "list", "--limit", "101", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_parameter"
    assert "101" not in payload["error"]["message"]

    result = runner.invoke(app, ["email", "list", "--offset", "-1", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_parameter"


def test_show_not_found_is_distinct_from_store_unavailable(monkeypatch) -> None:
    from sqlalchemy.exc import OperationalError

    delivery_id = uuid.uuid4()

    async def fake_show_none(delivery_uuid):
        return None

    monkeypatch.setattr(email_cli, "_show_inspection", fake_show_none)
    result = runner.invoke(app, ["email", "show", str(delivery_id), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "delivery_not_found"

    async def fake_show_unavailable(delivery_uuid):
        raise OperationalError("SELECT 1", {}, RuntimeError("connection refused"))

    monkeypatch.setattr(email_cli, "_show_inspection", fake_show_unavailable)
    result = runner.invoke(app, ["email", "show", str(delivery_id), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "store_unavailable"
    assert "connection refused" not in result.stdout


# --- 202-a four-mode dispatch combinations (truthful hooks) -----------------


def _four_mode_hooks(monkeypatch, *, with_delivery: bool):
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    seen: dict[str, object] = {}

    async def fake_send_pending_key_now(**kwargs):
        seen["sync"] = kwargs
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id,
            one_time_secret_id=secret_id,
            gateway_key_id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            recipient_email="ada@example.org",
            status="sent",
            provider_message_id="<message@example.org>",
        )

    async def fake_audit(**kwargs):
        seen["audit"] = kwargs

    async def fake_binding(delivery_uuid):
        return "pending", secret_id

    class FakeTask:
        @staticmethod
        def delay(*args):
            seen["delay"] = args

            class AsyncResult:
                id = "celery-task-id"

            return AsyncResult()

    monkeypatch.setattr(email_cli, "_send_pending_key_now", fake_send_pending_key_now)
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", fake_audit)
    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)
    if with_delivery:
        monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)
        monkeypatch.setattr(
            email_cli,
            "_get_key_email_sendability",
            lambda email_delivery_id: _sendable(email_delivery_id, secret_id),
        )
    return secret_id, delivery_id, seen


def test_dispatch_mode_no_id_send_now_sends_synchronously(monkeypatch) -> None:
    secret_id, _delivery_id, seen = _four_mode_hooks(monkeypatch, with_delivery=False)

    result = runner.invoke(
        app,
        ["email", "send-pending-key", "--one-time-secret-id", str(secret_id), "--send-now", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "sent"
    assert "sync" in seen
    assert "audit" not in seen
    assert "delay" not in seen


def test_dispatch_mode_no_id_enqueue_queues_only(monkeypatch) -> None:
    secret_id, _delivery_id, seen = _four_mode_hooks(monkeypatch, with_delivery=False)

    async def fresh_preflight(one_time_secret_id):
        return None

    monkeypatch.setattr(email_cli, "_preflight_no_id_secret", fresh_preflight)

    result = runner.invoke(
        app,
        ["email", "send-pending-key", "--one-time-secret-id", str(secret_id), "--enqueue", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "queued"
    assert "delay" in seen
    assert seen["delay"] == (str(secret_id), None, None)
    assert "audit" in seen
    assert "sync" not in seen


def test_dispatch_mode_selected_send_now_sends_synchronously(monkeypatch) -> None:
    secret_id, delivery_id, seen = _four_mode_hooks(monkeypatch, with_delivery=True)

    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "sent"
    assert "sync" in seen
    assert "audit" not in seen
    assert "delay" not in seen


def test_dispatch_mode_selected_enqueue_queues_only(monkeypatch) -> None:
    secret_id, delivery_id, seen = _four_mode_hooks(monkeypatch, with_delivery=True)

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
    assert json.loads(result.stdout)["status"] == "queued"
    assert "delay" in seen
    assert seen["delay"] == (str(secret_id), str(delivery_id), None)
    assert "audit" in seen
    assert "sync" not in seen


def test_retry_reason_over_length_bound_is_refused(monkeypatch) -> None:
    secret_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    def sender_must_not_run(**kwargs):
        raise AssertionError("sender must not run for an overlong reason")

    async def fake_binding(delivery_uuid):
        return "failed", secret_id

    monkeypatch.setattr(email_cli, "_send_pending_key_now", sender_must_not_run)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

    overlong = "x" * 1025
    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--retry-failed",
            "--reason",
            overlong,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "too long" in result.stdout
    assert overlong not in result.stdout


def test_retry_reason_at_length_bound_passes_preflight(monkeypatch) -> None:
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

    async def fake_binding(delivery_uuid):
        return "failed", secret_id

    monkeypatch.setattr(email_cli, "_send_pending_key_now", fake_send_pending_key_now)
    monkeypatch.setattr(email_cli, "_get_selected_delivery_binding", fake_binding)

    at_bound = "x" * 1024
    result = runner.invoke(
        app,
        [
            "email",
            "send-pending-key",
            "--one-time-secret-id",
            str(secret_id),
            "--email-delivery-id",
            str(delivery_id),
            "--send-now",
            "--retry-failed",
            "--reason",
            at_bound,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["reason"] == at_bound


# --- 202-a no-ID enqueue preflight (item 12) ---------------------------------


def _no_id_enqueue_hooks(monkeypatch) -> tuple[uuid.UUID, dict[str, object]]:
    secret_id = uuid.uuid4()
    seen: dict[str, object] = {}

    def audit_must_not_run(**kwargs):
        raise AssertionError("intent audit must not be recorded on refusal")

    class FakeTask:
        @staticmethod
        def delay(*args):
            raise AssertionError("Celery must not be dispatched on refusal")

    monkeypatch.setattr(email_cli, "send_pending_key_email_task", FakeTask)
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", audit_must_not_run)
    return secret_id, seen


def test_no_id_enqueue_refuses_retained_failed_history(monkeypatch) -> None:
    secret_id, _seen = _no_id_enqueue_hooks(monkeypatch)

    async def preflight(one_time_secret_id):
        assert one_time_secret_id == secret_id
        return "This one-time secret already has delivery history; select an existing delivery UUID explicitly"

    monkeypatch.setattr(email_cli, "_preflight_no_id_secret", preflight)

    result = runner.invoke(
        app,
        ["email", "send-pending-key", "--one-time-secret-id", str(secret_id), "--enqueue", "--json"],
    )

    assert result.exit_code == 1
    assert "delivery history" in result.stdout


def test_no_id_enqueue_refuses_blocked_same_secret_state(monkeypatch) -> None:
    secret_id, _seen = _no_id_enqueue_hooks(monkeypatch)

    async def preflight(one_time_secret_id):
        return (
            "A prior delivery attempt for this one-time secret is sending, sent, or ambiguous; enqueue is not safe"
        )

    monkeypatch.setattr(email_cli, "_preflight_no_id_secret", preflight)

    result = runner.invoke(
        app,
        ["email", "send-pending-key", "--one-time-secret-id", str(secret_id), "--enqueue", "--json"],
    )

    assert result.exit_code == 1
    assert "sending, sent, or ambiguous" in result.stdout


def test_no_id_enqueue_preserves_fresh_initial_creation(monkeypatch) -> None:
    secret_id, _delivery_id, seen = _four_mode_hooks(monkeypatch, with_delivery=False)

    async def fresh_preflight(one_time_secret_id):
        assert one_time_secret_id == secret_id
        return None

    monkeypatch.setattr(email_cli, "_preflight_no_id_secret", fresh_preflight)

    result = runner.invoke(
        app,
        ["email", "send-pending-key", "--one-time-secret-id", str(secret_id), "--enqueue", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "queued"
    assert seen["delay"] == (str(secret_id), None, None)
    assert "audit" in seen
    assert "sync" not in seen
