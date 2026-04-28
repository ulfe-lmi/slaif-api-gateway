from __future__ import annotations

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.email_errors import (
    EmailDeliveryDisabledError,
    SmtpConfigurationError,
    SmtpSendError,
)
from slaif_gateway.services.email_service import EmailService


@pytest.mark.asyncio
async def test_email_service_sends_with_aiosmtplib(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_send(message, **kwargs):
        seen["message"] = message
        seen["kwargs"] = kwargs
        return ({}, "250 queued")

    monkeypatch.setattr("slaif_gateway.services.email_service.aiosmtplib.send", fake_send)
    settings = Settings(
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_PORT=1025,
        SMTP_USERNAME="user",
        SMTP_PASSWORD="smtp-secret",
        SMTP_FROM="noreply@example.org",
    )

    result = await EmailService(settings).send_email(
        to="ada@example.org",
        subject="Subject",
        text_body="Plain body",
    )

    assert result.accepted_recipients == ("ada@example.org",)
    assert result.message_id
    assert seen["kwargs"]["hostname"] == "localhost"
    assert seen["kwargs"]["password"] == "smtp-secret"
    assert seen["message"]["To"] == "ada@example.org"
    assert "Plain body" in seen["message"].get_content()


@pytest.mark.asyncio
async def test_email_service_rejects_disabled_delivery() -> None:
    settings = Settings(ENABLE_EMAIL_DELIVERY=False)

    with pytest.raises(EmailDeliveryDisabledError):
        await EmailService(settings).send_email(
            to="ada@example.org",
            subject="Subject",
            text_body="Plain body",
        )


@pytest.mark.asyncio
async def test_email_service_configuration_errors_are_safe() -> None:
    settings = Settings(ENABLE_EMAIL_DELIVERY=False)
    settings.ENABLE_EMAIL_DELIVERY = True

    with pytest.raises(SmtpConfigurationError) as exc:
        await EmailService(settings).send_email(
            to="ada@example.org",
            subject="Subject",
            text_body="Plain body",
        )

    assert "SMTP_HOST" in str(exc.value)


@pytest.mark.asyncio
async def test_email_service_redacts_smtp_failure(monkeypatch) -> None:
    async def fake_send(message, **kwargs):
        raise RuntimeError("authentication failed password=smtp-secret")

    monkeypatch.setattr("slaif_gateway.services.email_service.aiosmtplib.send", fake_send)
    settings = Settings(
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_FROM="noreply@example.org",
        SMTP_PASSWORD="smtp-secret",
    )

    with pytest.raises(SmtpSendError) as exc:
        await EmailService(settings).send_email(
            to="ada@example.org",
            subject="Subject",
            text_body="Plain body",
        )

    assert "smtp-secret" not in str(exc.value)
    assert "password=***" in str(exc.value)
