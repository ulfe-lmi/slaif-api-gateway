from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import EmailDelivery, OneTimeSecret
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.email_service import EmailSendResult
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.secrets import generate_secret_key
from slaif_gateway.workers import tasks_email


class _FakeEmailService:
    sent_bodies: list[str] = []

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        self.sent_bodies.append(text_body)
        return EmailSendResult(
            message_id="<message@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )


def _settings(database_url: str) -> Settings:
    return Settings(
        DATABASE_URL=database_url,
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_FROM="noreply@example.org",
        PUBLIC_BASE_URL="https://api.ulfe.slaif.si/v1",
    )


@pytest.mark.asyncio
async def test_email_celery_task_sends_with_ids_only(
    migrated_postgres_url: str,
    monkeypatch,
) -> None:
    settings = _settings(migrated_postgres_url)
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            owner = await OwnersRepository(session).create_owner(
                name="Ada",
                surname="Lovelace",
                email=f"task-{datetime.now(UTC).timestamp()}@example.org",
            )
            created = await KeyService(
                settings=settings,
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            ).create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner.id,
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                    valid_until=datetime(2026, 2, 1, tzinfo=UTC),
                )
            )
            delivery = await EmailDeliveriesRepository(session).create_email_delivery(
                recipient_email=owner.email,
                subject="Your SLAIF API Gateway key",
                template_name="gateway_key_email",
                owner_id=owner.id,
                gateway_key_id=created.gateway_key_id,
                one_time_secret_id=created.one_time_secret_id,
                status="pending",
            )

    _FakeEmailService.sent_bodies = []
    monkeypatch.setattr(tasks_email, "EmailService", _FakeEmailService)

    result = await tasks_email._send_pending_key_email(
        settings=settings,
        one_time_secret_id=str(created.one_time_secret_id),
        email_delivery_id=str(delivery.id),
    )

    async with session_factory() as session:
        secret = await session.get(OneTimeSecret, created.one_time_secret_id)
        email_row = await session.get(EmailDelivery, delivery.id)

    await engine.dispose()

    assert result["status"] == "sent"
    assert result["one_time_secret_id"] == str(created.one_time_secret_id)
    assert "recipient_email" not in result
    assert created.plaintext_key not in str(result)
    assert _FakeEmailService.sent_bodies
    assert created.plaintext_key in _FakeEmailService.sent_bodies[0]
    assert secret is not None and secret.status == "consumed"
    assert email_row is not None and email_row.status == "sent"
