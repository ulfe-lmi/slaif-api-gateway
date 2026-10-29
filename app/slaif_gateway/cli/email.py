"""Typer commands for SMTP email delivery operations and read-only inspection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from slaif_gateway.cli.common import (
    CliDatabaseConfigError,
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
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.schemas.email_inspection import (
    EmailDeliveryListItem,
    EmailInspectionValidationError,
    LIST_LIMIT_DEFAULT,
    normalize_owner_email,
    validate_creation_window,
    validate_delivery_status,
    validate_page,
)
from slaif_gateway.services.email_delivery_service import (
    KEY_EMAIL_PURPOSES,
    EmailDeliveryService,
    PendingKeyEmailResult,
)
from slaif_gateway.services.email_inspection import EmailInspectionService
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.provider_route_configuration import contains_known_secret_shape
from slaif_gateway.workers.tasks_email import send_pending_key_email_task

# Consistent with the existing operator audit-reason bound
# (services/openai_compatible_setup.py: 1024 UTF-8 bytes).
_RETRY_REASON_MAX_BYTES = 1024


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


@app.command("list")
def list_email_deliveries(
    delivery_id: Annotated[str | None, typer.Option("--delivery-id", help="Exact delivery UUID")] = None,
    key_id: Annotated[str | None, typer.Option("--key-id", help="Exact gateway key UUID")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner-id", help="Exact owner UUID")] = None,
    owner_email: Annotated[str | None, typer.Option("--owner-email", help="Exact (normalized) owner email")] = None,
    status: Annotated[str | None, typer.Option("--status", help="Persisted delivery status")] = None,
    created_from: Annotated[
        str | None,
        typer.Option("--created-from", help="Inclusive aware UTC lower bound (ISO datetime)"),
    ] = None,
    created_until: Annotated[
        str | None,
        typer.Option("--created-until", help="Inclusive aware UTC upper bound (ISO datetime)"),
    ] = None,
    limit: Annotated[str, typer.Option("--limit", help="Page size, 1..100 (default 50)")] = str(LIST_LIMIT_DEFAULT),
    offset: Annotated[str, typer.Option("--offset", help="Page offset, 0..1000000")] = "0",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output")] = False,
) -> None:
    """List persisted key email deliveries by exact allowlisted filters (read-only)."""
    try:
        parsed_delivery_id = parse_uuid(delivery_id, field_name="delivery_id") if delivery_id else None
        parsed_key_id = parse_uuid(key_id, field_name="key_id") if key_id else None
        parsed_owner_id = parse_uuid(owner_id, field_name="owner_id") if owner_id else None
        normalized_owner_email = normalize_owner_email(owner_email) if owner_email else None
        parsed_status = validate_delivery_status(status) if status is not None else None
        parsed_from = _parse_aware_utc_datetime(created_from, field_name="created_from")
        parsed_until = _parse_aware_utc_datetime(created_until, field_name="created_until")
        validate_creation_window(parsed_from, parsed_until)
        page_limit, page_offset = validate_page(
            _parse_page_value(limit, field_name="limit"),
            _parse_page_value(offset, field_name="offset"),
        )
        page = run_async(
            _list_inspection(
                delivery_id=parsed_delivery_id,
                gateway_key_id=parsed_key_id,
                owner_id=parsed_owner_id,
                owner_email_normalized=normalized_owner_email,
                status=parsed_status,
                created_from=parsed_from,
                created_until=parsed_until,
                limit=page_limit,
                offset=page_offset,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_inspection_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(
            {
                "items": [_item_payload(item) for item in page.items],
                "limit": page.limit,
                "offset": page.offset,
                "has_more": page.has_more,
                "next_offset": page.next_offset,
            }
        )
        return
    for item in page.items:
        typer.echo(
            " ".join(
                (
                    str(item.delivery_id),
                    item.status,
                    item.recipient_email,
                    f"created_at={item.created_at.isoformat()}",
                )
            )
        )
    typer.echo(f"has_more: {str(page.has_more).lower()}")
    if page.next_offset is not None:
        typer.echo(f"next_offset: {page.next_offset}")


@app.command("show")
def show_email_delivery(
    delivery_uuid: Annotated[str, typer.Argument(help="Exact delivery UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output")] = False,
) -> None:
    """Show allowlisted metadata for ONE exact delivery UUID (read-only)."""
    try:
        parsed_delivery_id = parse_uuid(delivery_uuid, field_name="delivery_uuid")
        detail = run_async(_show_inspection(parsed_delivery_id))
    except Exception as exc:  # noqa: BLE001
        _handle_inspection_error(exc, json_output=json_output)
        return

    if detail is None:
        _emit_inspection_error(
            "delivery_not_found",
            "Email delivery was not found",
            json_output=json_output,
            extra={"delivery_id": str(parsed_delivery_id)},
        )
        return

    payload = _item_payload(detail.item)
    if detail.secret_lifecycle is not None:
        payload["one_time_secret"] = {
            "status": detail.secret_lifecycle.status,
            "can_send": detail.secret_lifecycle.can_send,
            "blocking_reason": detail.secret_lifecycle.blocking_reason,
        }
    if detail.last_recorded_failure is not None:
        payload["last_recorded_failure"] = {
            "error_code": detail.last_recorded_failure.error_code,
            "action": detail.last_recorded_failure.action,
            "recorded_at": detail.last_recorded_failure.recorded_at,
            "provenance": detail.last_recorded_failure.provenance,
        }
    if json_output:
        emit_json(payload)
    else:
        echo_kv(payload)


@app.command("send-pending-key")
def send_pending_key(
    one_time_secret_id: Annotated[str, typer.Option("--one-time-secret-id", help="One-time secret UUID")],
    email_delivery_id: Annotated[str | None, typer.Option("--email-delivery-id", help="Email delivery UUID")] = None,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Actor admin UUID")] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit note")] = None,
    enqueue: Annotated[bool, typer.Option("--enqueue", help="Enqueue a Celery task")] = False,
    send_now: Annotated[bool, typer.Option("--send-now", help="Send synchronously now")] = False,
    retry_failed: Annotated[
        bool,
        typer.Option("--retry-failed", help="Explicitly retry an existing FAILED delivery"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output")] = False,
) -> None:
    """Send or enqueue delivery of a pending gateway-key one-time secret."""
    try:
        secret_uuid = parse_uuid(one_time_secret_id, field_name="one_time_secret_id")
        delivery_uuid = parse_uuid(email_delivery_id, field_name="email_delivery_id") if email_delivery_id else None
        admin_uuid = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
        if enqueue and send_now:
            raise typer.BadParameter("Use either --enqueue or --send-now, not both")
        if retry_failed and delivery_uuid is None:
            raise typer.BadParameter("--retry-failed requires --email-delivery-id")
        if (reason is not None and (retry_failed or enqueue)) and contains_known_secret_shape(reason):
            # 202-a: new action reason protection applies consistently to
            # every reason this command newly persists (retry in either
            # mode, enqueue intent), not only when retry_failed=true.
            raise typer.BadParameter("--reason must not contain recognized credential patterns")
        if delivery_uuid is not None:
            # 202-a read-only preflight BEFORE send/queue in BOTH
            # synchronous and enqueue modes: the selected target must
            # exist, be backed by the EXACT supplied secret, and a FAILED
            # row may only be sent with explicit --retry-failed plus a
            # nonblank bounded reason.
            row_status, row_secret_id = run_async(_get_selected_delivery_binding(delivery_uuid))
            if row_status is None:
                raise typer.BadParameter("The selected email delivery UUID was not found")
            if row_secret_id != secret_uuid:
                raise typer.BadParameter("The one-time secret does not match the selected email delivery")
            if row_status == "failed":
                if not retry_failed:
                    raise typer.BadParameter(
                        "The selected delivery is FAILED; use --retry-failed with a nonblank --reason to retry it"
                    )
                if reason is None or not reason.strip():
                    raise typer.BadParameter("--retry-failed requires a nonblank --reason")
                if len(reason.encode("utf-8")) > _RETRY_REASON_MAX_BYTES:
                    raise typer.BadParameter("Audit reason is too long")
            elif retry_failed:
                raise typer.BadParameter("Only an existing FAILED delivery can be explicitly retried")
            if enqueue:
                sendability = run_async(_get_key_email_sendability(delivery_uuid))
                if not sendability.can_send:
                    raise typer.BadParameter(
                        sendability.blocking_reason
                        or "This key email delivery cannot be safely queued; rotate the key if needed."
                    )
        if enqueue:
            if delivery_uuid is None:
                # 202-a: a no-ID enqueue must not skip the lifecycle /
                # history preflight. Reject unsafe or retained-failed
                # same-secret states BEFORE the intent audit/dispatch
                # (metadata-only shared guards, no decryption, no worker
                # argument changes); a valid fresh no-ID initial enqueue
                # is preserved.
                preflight_error = run_async(_preflight_no_id_secret(secret_uuid))
                if preflight_error is not None:
                    raise typer.BadParameter(preflight_error)
            # 202-a: bounded safe operator enqueue-REQUEST audit via the
            # existing audit repository BEFORE dispatch. The commit must
            # succeed first; an audit failure prevents dispatch. It
            # records only safe selected IDs/actor/reason and explicit
            # intent — NOT successful SMTP or a persisted queued status.
            run_async(
                _record_enqueue_request_audit(
                    one_time_secret_id=secret_uuid,
                    email_delivery_id=delivery_uuid,
                    actor_admin_id=admin_uuid,
                    reason=reason,
                    retry_failed=retry_failed,
                )
            )
            # The Celery task payload stays EXACTLY the existing three
            # UUIDs (no reason/body/secret/boolean/policy/context).
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
    if payload.get("status") in {"failed", "ambiguous"}:
        raise typer.Exit(code=1)


def _item_payload(item: EmailDeliveryListItem) -> dict[str, object]:
    """Allowlisted metadata only: no subject/body/error prose/provider IDs."""
    return {
        "delivery_id": str(item.delivery_id),
        "owner_id": str(item.owner_id) if item.owner_id else None,
        "gateway_key_id": str(item.gateway_key_id) if item.gateway_key_id else None,
        "one_time_secret_id": str(item.one_time_secret_id) if item.one_time_secret_id else None,
        "recipient_email": item.recipient_email,
        "status": item.status,
        "created_at": item.created_at,
        "sent_at": item.sent_at,
        "failed_at": item.failed_at,
    }


def _parse_page_value(value: str, *, field_name: str) -> int:
    """Parse a page bound without ever echoing the supplied value."""
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{field_name} cannot be empty")
    candidate = normalized[1:] if normalized[0] in "+-" else normalized
    if not candidate.isascii() or not candidate.isdigit():
        raise typer.BadParameter(f"{field_name} must be an integer")
    return int(normalized)


def _parse_aware_utc_datetime(value: str | None, *, field_name: str) -> datetime | None:
    """Inspection time bounds must be EXPLICIT aware UTC instants."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{field_name} cannot be empty")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise typer.BadParameter(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise typer.BadParameter(f"{field_name} must be an explicit aware UTC datetime")
    return parsed


def _emit_inspection_error(
    code: str, message: str, *, json_output: bool, extra: dict[str, object] | None = None
) -> None:
    """Fixed safe inspection error outcome (nonzero)."""
    if json_output:
        payload = {"error": {"code": code, "message": message}}
        if extra:
            payload.update(extra)
        emit_json(payload)
    else:
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _handle_inspection_error(exc: Exception, *, json_output: bool) -> None:
    if isinstance(exc, EmailInspectionValidationError):
        _emit_inspection_error("invalid_parameter", exc.safe_message, json_output=json_output)
    elif isinstance(exc, typer.BadParameter):
        _emit_inspection_error("invalid_parameter", str(exc), json_output=json_output)
    elif isinstance(exc, CliDatabaseConfigError):
        _emit_inspection_error("database_not_configured", str(exc), json_output=json_output)
    elif isinstance(exc, SQLAlchemyError):
        # Store unavailable is distinct from an empty/missing result and
        # never echoes driver/SQL detail.
        _emit_inspection_error("store_unavailable", "The email delivery store is unavailable", json_output=json_output)
    else:
        handle_cli_error(exc, json_output=json_output)


async def _open_inspection_session():
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError("DATABASE_URL is not configured. Set DATABASE_URL and try again.")
    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc
    return session_factory


async def _build_inspection_service(session_factory, session):
    settings = get_settings()
    sender_service = EmailDeliveryService(
        settings=settings,
        one_time_secrets_repository=OneTimeSecretsRepository(session),
        email_deliveries_repository=EmailDeliveriesRepository(session),
        gateway_keys_repository=GatewayKeysRepository(session),
        owners_repository=OwnersRepository(session),
        audit_repository=AuditRepository(session),
        email_service=EmailService(settings),
        session=session,
    )
    return EmailInspectionService(
        email_deliveries_repository=EmailDeliveriesRepository(session),
        audit_repository=AuditRepository(session),
        sendability_provider=sender_service.get_key_email_delivery_sendability,
    )


async def _list_inspection(
    *,
    delivery_id: uuid.UUID | None,
    gateway_key_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    owner_email_normalized: str | None,
    status: str | None,
    created_from: datetime | None,
    created_until: datetime | None,
    limit: int,
    offset: int,
):
    session_factory = await _open_inspection_session()
    async with session_factory() as session:
        service = await _build_inspection_service(session_factory, session)
        return await service.list_deliveries(
            delivery_id=delivery_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            owner_email_normalized=owner_email_normalized,
            status=status,
            created_from=created_from,
            created_until=created_until,
            limit=limit,
            offset=offset,
        )


async def _show_inspection(delivery_id: uuid.UUID):
    session_factory = await _open_inspection_session()
    async with session_factory() as session:
        service = await _build_inspection_service(session_factory, session)
        return await service.show_delivery(delivery_id)


async def _preflight_no_id_secret(one_time_secret_id: uuid.UUID):
    """202-a read-only metadata-only guard for a no-ID enqueue.

    Reuses the same bounded predicates as the shared send boundary
    (exact-secret lifecycle + whole-set history EXISTS). Returns a fixed
    safe message when the enqueue is not safe, or None when a genuine
    fresh no-ID initial enqueue may proceed. No decryption.
    """
    session_factory = await _open_inspection_session()
    async with session_factory() as session:
        secret = await OneTimeSecretsRepository(session).get_one_time_secret_by_id(one_time_secret_id)
        if secret is None:
            return "The one-time secret UUID was not found"
        if secret.status == "consumed" or secret.consumed_at is not None:
            return "The one-time secret was already consumed; rotate the key"
        checked_at = datetime.now(UTC)
        if secret.status == "expired" or secret.expires_at <= checked_at:
            return "The one-time secret is expired; rotate the key"
        if secret.status != "pending":
            return "The one-time secret is not pending; rotate the key"
        if secret.purpose not in KEY_EMAIL_PURPOSES:
            return "The one-time secret is not valid for key email delivery"
        delivery_repo = EmailDeliveriesRepository(session)
        if await delivery_repo.has_blocking_email_delivery_attempt(one_time_secret_id):
            return (
                "A prior delivery attempt for this one-time secret is sending, sent, or ambiguous; enqueue is not safe"
            )
        if await delivery_repo.has_email_delivery_attempt(one_time_secret_id):
            return "This one-time secret already has delivery history; select an existing delivery UUID explicitly"
    return None


async def _get_selected_delivery_binding(delivery_uuid: uuid.UUID):
    """Read-only preflight metadata for a selected delivery (status + secret)."""
    session_factory = await _open_inspection_session()
    async with session_factory() as session:
        delivery = await EmailDeliveriesRepository(session).get_email_delivery_by_id(delivery_uuid)
    if delivery is None:
        return None, None
    return delivery.status, delivery.one_time_secret_id


async def _record_enqueue_request_audit(
    *,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID | None,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
    retry_failed: bool,
) -> None:
    """Bounded safe operator enqueue-REQUEST intent audit; commit BEFORE dispatch.

    The one-time secret is referenced under the SAFE field name
    ``one_time_reference_id`` (strictly the already-parsed UUID string):
    the durable metadata sanitizer intentionally drops secret-bearing key
    names such as ``one_time_secret_id`` from every audit record, and this
    event must not relax that global boundary. The reference keeps the
    intent attributable for no-ID enqueues (where entity_id is NULL).
    """
    session_factory = await _open_inspection_session()
    async with session_factory() as session:
        await AuditRepository(session).add_audit_log(
            action="email_key_enqueue_requested",
            entity_type="email_delivery",
            entity_id=email_delivery_id,
            admin_user_id=actor_admin_id,
            note=reason,
            new_values={
                "one_time_reference_id": str(one_time_secret_id),
                "email_delivery_id": str(email_delivery_id) if email_delivery_id else None,
                "actor_admin_id": str(actor_admin_id) if actor_admin_id else None,
                "intent": "enqueue_requested",
                "retry_failed": retry_failed,
            },
        )
        await session.commit()


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
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError("DATABASE_URL is not configured. Set DATABASE_URL and try again.")
    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc
    async with session_factory() as session:
        service = EmailDeliveryService(
            settings=settings,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            email_deliveries_repository=EmailDeliveriesRepository(session),
            gateway_keys_repository=GatewayKeysRepository(session),
            owners_repository=OwnersRepository(session),
            audit_repository=AuditRepository(session),
            email_service=EmailService(settings),
            session=session,
        )
        return await service.send_pending_key_email(
            one_time_secret_id=one_time_secret_id,
            email_delivery_id=email_delivery_id,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


async def _get_key_email_sendability(email_delivery_id: uuid.UUID):
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError("DATABASE_URL is not configured. Set DATABASE_URL and try again.")
    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        service = EmailDeliveryService(
            settings=settings,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            email_deliveries_repository=EmailDeliveriesRepository(session),
            gateway_keys_repository=GatewayKeysRepository(session),
            owners_repository=OwnersRepository(session),
            audit_repository=AuditRepository(session),
            email_service=EmailService(settings),
            session=session,
        )
        return await service.get_key_email_delivery_sendability(email_delivery_id)


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
