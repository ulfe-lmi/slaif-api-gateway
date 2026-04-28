"""Typer commands for SMTP email delivery operations."""

from __future__ import annotations

import uuid
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_uuid,
    run_async,
)
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.email_delivery_service import EmailDeliveryService, PendingKeyEmailResult
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.workers.tasks_email import send_pending_key_email_task

app = typer.Typer(help="Test and send configured email deliveries")


@app.command("test")
def send_test_email(
    to: Annotated[str, typer.Option("--to", help="Recipient email address")],
    subject: Annotated[
        str,
        typer.Option("--subject", help="Test email subject"),
    ] = "SLAIF API Gateway test email",
    body: Annotated[str | None, typer.Option("--body", help="Optional plain-text body")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output")] = False,
) -> None:
    """Send a safe SMTP test email with no gateway key material."""
    try:
        result = run_async(_send_test_email(to=to, subject=subject, body=body))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)

    payload: dict[str, object] = {
        "status": "sent",
        "message_id": result.message_id,
        "accepted_recipients": list(result.accepted_recipients),
    }
    emit_json(payload) if json_output else echo_kv(payload)


@app.command("send-pending-key")
def send_pending_key(
    one_time_secret_id: Annotated[str, typer.Option("--one-time-secret-id", help="One-time secret UUID")],
    email_delivery_id: Annotated[str | None, typer.Option("--email-delivery-id", help="Email delivery UUID")] = None,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Actor admin UUID")] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit note")] = None,
    enqueue: Annotated[bool, typer.Option("--enqueue", help="Enqueue a Celery task")] = False,
    send_now: Annotated[bool, typer.Option("--send-now", help="Send synchronously now")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output")] = False,
) -> None:
    """Send or enqueue delivery of a pending gateway-key one-time secret."""
    try:
        secret_uuid = parse_uuid(one_time_secret_id, field_name="one_time_secret_id")
        delivery_uuid = parse_uuid(email_delivery_id, field_name="email_delivery_id") if email_delivery_id else None
        admin_uuid = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
        if enqueue and send_now:
            raise typer.BadParameter("Use either --enqueue or --send-now, not both")
        if enqueue:
            async_result = send_pending_key_email_task.delay(
                str(secret_uuid),
                str(delivery_uuid) if delivery_uuid else None,
                str(admin_uuid) if admin_uuid else None,
            )
            payload: dict[str, object] = {
                "status": "queued",
                "celery_task_id": async_result.id,
                "one_time_secret_id": str(secret_uuid),
                "email_delivery_id": str(delivery_uuid) if delivery_uuid else None,
            }
        else:
            result = run_async(
                _send_pending_key_now(
                    one_time_secret_id=secret_uuid,
                    email_delivery_id=delivery_uuid,
                    actor_admin_id=admin_uuid,
                    reason=reason,
                )
            )
            payload = _result_payload(result)
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    emit_json(payload) if json_output else echo_kv(payload)
    if payload.get("status") == "failed":
        raise typer.Exit(code=1)


async def _send_test_email(*, to: str, subject: str, body: str | None):
    settings = get_settings()
    return await EmailService(settings).send_email(
        to=to,
        subject=subject,
        text_body=body or "SLAIF API Gateway SMTP test email.",
    )


async def _send_pending_key_now(
    *,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID | None,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> PendingKeyEmailResult:
    async with cli_db_session() as (settings, session):
        service = EmailDeliveryService(
            settings=settings,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            email_deliveries_repository=EmailDeliveriesRepository(session),
            gateway_keys_repository=GatewayKeysRepository(session),
            owners_repository=OwnersRepository(session),
            audit_repository=AuditRepository(session),
            email_service=EmailService(settings),
        )
        return await service.send_pending_key_email(
            one_time_secret_id=one_time_secret_id,
            email_delivery_id=email_delivery_id,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


def _result_payload(result: PendingKeyEmailResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "email_delivery_id": str(result.email_delivery_id),
        "one_time_secret_id": str(result.one_time_secret_id),
    }
    if result.gateway_key_id is not None:
        payload["gateway_key_id"] = str(result.gateway_key_id)
    if result.owner_id is not None:
        payload["owner_id"] = str(result.owner_id)
    if result.provider_message_id is not None:
        payload["provider_message_id"] = result.provider_message_id
    if result.error_code is not None:
        payload["error_code"] = result.error_code
    if result.error_message is not None:
        payload["error_message"] = result.error_message
    return payload
