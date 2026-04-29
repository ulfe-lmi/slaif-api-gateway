"""Celery tasks for safe key email delivery."""

from __future__ import annotations

import asyncio
import uuid

from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.session import create_engine_from_settings, create_sessionmaker_from_engine
from slaif_gateway.services.email_delivery_service import EmailDeliveryService, PendingKeyEmailResult
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.workers.celery_app import celery_app


@celery_app.task(name="slaif_gateway.email.send_pending_key_email")
def send_pending_key_email_task(
    one_time_secret_id: str,
    email_delivery_id: str | None = None,
    actor_admin_id: str | None = None,
) -> dict[str, object]:
    """Send a pending key email; task payloads contain IDs only."""
    return asyncio.run(
        _send_pending_key_email(
            settings=get_settings(),
            one_time_secret_id=one_time_secret_id,
            email_delivery_id=email_delivery_id,
            actor_admin_id=actor_admin_id,
        )
    )


async def _send_pending_key_email(
    *,
    settings: Settings,
    one_time_secret_id: str,
    email_delivery_id: str | None = None,
    actor_admin_id: str | None = None,
) -> dict[str, object]:
    engine = create_engine_from_settings(settings)
    try:
        session_factory = create_sessionmaker_from_engine(engine)
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
            result = await service.send_pending_key_email(
                one_time_secret_id=uuid.UUID(one_time_secret_id),
                email_delivery_id=uuid.UUID(email_delivery_id) if email_delivery_id else None,
                actor_admin_id=uuid.UUID(actor_admin_id) if actor_admin_id else None,
            )
            return _safe_task_result(result)
    finally:
        await engine.dispose()


def _safe_task_result(result: PendingKeyEmailResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "email_delivery_id": str(result.email_delivery_id),
        "one_time_secret_id": str(result.one_time_secret_id),
        "status": result.status,
    }
    if result.gateway_key_id is not None:
        payload["gateway_key_id"] = str(result.gateway_key_id)
    if result.owner_id is not None:
        payload["owner_id"] = str(result.owner_id)
    if result.provider_message_id is not None:
        payload["provider_message_id"] = result.provider_message_id
    if result.error_code is not None:
        payload["error_code"] = result.error_code
    return payload
