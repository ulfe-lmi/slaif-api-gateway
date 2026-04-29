from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_errors import SmtpSendError
from slaif_gateway.services.email_service import EmailSendResult
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.secrets import generate_secret_key


class _FakeEmailService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent_bodies: list[str] = []

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        self.sent_bodies.append(text_body)
        if self.fail:
            raise SmtpSendError("fake smtp failed password=***")
        return EmailSendResult(
            message_id="<message@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )


class _CommitFailsAfterSmtpFinalization:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1
        if self.commit_count == 2:
            raise RuntimeError("simulated finalization commit failure")
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


def _settings() -> Settings:
    return Settings(
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_FROM="noreply@example.org",
        PUBLIC_BASE_URL="https://api.ulfe.slaif.si/v1",
    )


async def _create_key_delivery(session: AsyncSession, settings: Settings):
    owner = await OwnersRepository(session).create_owner(
        name="Ada",
        surname="Lovelace",
        email=f"ada-{datetime.now(UTC).timestamp()}@example.org",
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
            token_limit_total=1000,
            request_limit_total=20,
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
    return owner, created, delivery


def _service(session: AsyncSession, settings: Settings, email_service: _FakeEmailService):
    return EmailDeliveryService(
        settings=settings,
        one_time_secrets_repository=OneTimeSecretsRepository(session),
        email_deliveries_repository=EmailDeliveriesRepository(session),
        gateway_keys_repository=GatewayKeysRepository(session),
        owners_repository=OwnersRepository(session),
        audit_repository=AuditRepository(session),
        email_service=email_service,
    )


def _service_with_session_control(
    session: AsyncSession,
    settings: Settings,
    email_service: _FakeEmailService,
    session_control: object,
):
    return EmailDeliveryService(
        settings=settings,
        one_time_secrets_repository=OneTimeSecretsRepository(session),
        email_deliveries_repository=EmailDeliveriesRepository(session),
        gateway_keys_repository=GatewayKeysRepository(session),
        owners_repository=OwnersRepository(session),
        audit_repository=AuditRepository(session),
        email_service=email_service,
        session=session_control,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_email_delivery_sends_pending_key_and_does_not_store_plaintext(
    async_test_session: AsyncSession,
) -> None:
    settings = _settings()
    _owner, created, delivery = await _create_key_delivery(async_test_session, settings)
    fake_smtp = _FakeEmailService()

    result = await _service(async_test_session, settings, fake_smtp).send_pending_key_email(
        one_time_secret_id=created.one_time_secret_id,
        email_delivery_id=delivery.id,
    )

    secret = await async_test_session.get(OneTimeSecret, created.one_time_secret_id)
    email_row = await async_test_session.get(EmailDelivery, delivery.id)
    gateway_key = await async_test_session.get(GatewayKey, created.gateway_key_id)
    audits = (
        await async_test_session.execute(select(AuditLog).where(AuditLog.action == "email_key"))
    ).scalars()

    assert result.status == "sent"
    assert secret is not None and secret.status == "consumed"
    assert secret.consumed_at is not None
    assert email_row is not None and email_row.status == "sent"
    assert created.plaintext_key in fake_smtp.sent_bodies[0]
    assert gateway_key is not None and gateway_key.token_hash != created.plaintext_key
    serialized_email = json.dumps(
        {
            "subject": email_row.subject,
            "status": email_row.status,
            "provider_message_id": email_row.provider_message_id,
            "error_message": email_row.error_message,
        },
        default=str,
    )
    serialized_audit = json.dumps([audit.new_values for audit in audits], default=str)
    assert created.plaintext_key not in serialized_email
    assert created.plaintext_key not in serialized_audit
    assert secret.encrypted_payload not in serialized_audit
    assert secret.nonce not in serialized_audit


@pytest.mark.asyncio
async def test_email_delivery_expired_secret_fails(async_test_session: AsyncSession) -> None:
    settings = _settings()
    _owner, created, delivery = await _create_key_delivery(async_test_session, settings)
    secret = await async_test_session.get(OneTimeSecret, created.one_time_secret_id)
    assert secret is not None
    secret.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    result = await _service(async_test_session, settings, _FakeEmailService()).send_pending_key_email(
        one_time_secret_id=created.one_time_secret_id,
        email_delivery_id=delivery.id,
    )

    assert result.status == "failed"
    assert result.error_code == "one_time_secret_expired"
    assert secret.status == "expired"
    assert secret.consumed_at is None


@pytest.mark.asyncio
async def test_email_delivery_consumed_secret_fails(async_test_session: AsyncSession) -> None:
    settings = _settings()
    _owner, created, delivery = await _create_key_delivery(async_test_session, settings)
    secret = await async_test_session.get(OneTimeSecret, created.one_time_secret_id)
    assert secret is not None
    secret.status = "consumed"
    secret.consumed_at = datetime.now(UTC)

    result = await _service(async_test_session, settings, _FakeEmailService()).send_pending_key_email(
        one_time_secret_id=created.one_time_secret_id,
        email_delivery_id=delivery.id,
    )

    assert result.status == "failed"
    assert result.error_code == "one_time_secret_already_consumed"


@pytest.mark.asyncio
async def test_email_delivery_failed_smtp_records_failure_without_consuming(
    async_test_session: AsyncSession,
) -> None:
    settings = _settings()
    _owner, created, delivery = await _create_key_delivery(async_test_session, settings)
    fake_smtp = _FakeEmailService(fail=True)

    result = await _service(async_test_session, settings, fake_smtp).send_pending_key_email(
        one_time_secret_id=created.one_time_secret_id,
        email_delivery_id=delivery.id,
    )

    secret = await async_test_session.get(OneTimeSecret, created.one_time_secret_id)
    email_row = await async_test_session.get(EmailDelivery, delivery.id)
    assert result.status == "failed"
    assert result.error_code == "smtp_send_error"
    assert secret is not None and secret.status == "pending"
    assert secret.consumed_at is None
    assert email_row is not None and email_row.status == "failed"
    assert created.plaintext_key not in (email_row.error_message or "")


@pytest.mark.asyncio
async def test_email_delivery_smtp_success_then_finalization_failure_becomes_ambiguous(
    migrated_postgres_url: str,
) -> None:
    settings = _settings()
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                _owner, created, delivery = await _create_key_delivery(session, settings)

        fake_smtp = _FakeEmailService()
        async with session_factory() as session:
            session_control = _CommitFailsAfterSmtpFinalization(session)
            result = await _service_with_session_control(
                session,
                settings,
                fake_smtp,
                session_control,
            ).send_pending_key_email(
                one_time_secret_id=created.one_time_secret_id,
                email_delivery_id=delivery.id,
            )

        async with session_factory() as session:
            secret = await session.get(OneTimeSecret, created.one_time_secret_id)
            email_row = await session.get(EmailDelivery, delivery.id)
            audits = (
                await session.execute(select(AuditLog).where(AuditLog.action == "email_key_ambiguous"))
            ).scalars().all()

        assert result.status == "ambiguous"
        assert result.error_code == "email_delivery_finalization_failed"
        assert len(fake_smtp.sent_bodies) == 1
        assert created.plaintext_key in fake_smtp.sent_bodies[0]
        assert secret is not None and secret.status == "pending"
        assert secret.consumed_at is None
        assert email_row is not None and email_row.status == "ambiguous"
        assert created.plaintext_key not in (email_row.error_message or "")
        serialized_audit = json.dumps([audit.new_values for audit in audits], default=str)
        assert created.plaintext_key not in serialized_audit

        retry_smtp = _FakeEmailService()
        async with session_factory() as session:
            retry = await _service_with_session_control(
                session,
                settings,
                retry_smtp,
                session,
            ).send_pending_key_email(
                one_time_secret_id=created.one_time_secret_id,
                email_delivery_id=delivery.id,
            )

        assert retry.status == "ambiguous"
        assert retry.error_code == "email_delivery_ambiguous"
        assert retry_smtp.sent_bodies == []
    finally:
        await engine.dispose()
