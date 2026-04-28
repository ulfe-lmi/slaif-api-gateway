"""SMTP email service built on aiosmtplib."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib

from slaif_gateway.config import Settings
from slaif_gateway.services.email_errors import (
    EmailDeliveryDisabledError,
    SmtpConfigurationError,
    SmtpSendError,
)
from slaif_gateway.utils.redaction import redact_text


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    """Safe SMTP send metadata."""

    message_id: str | None
    accepted_recipients: tuple[str, ...]
    provider_status: str


class EmailService:
    """Sends email without logging message bodies or SMTP secrets."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailSendResult:
        """Send one message through configured SMTP."""
        self._validate_enabled_and_configured()

        message = EmailMessage()
        message_id = make_msgid(domain="slaif-api-gateway.local")
        message["Message-ID"] = message_id
        message["From"] = self._settings.SMTP_FROM or ""
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body is not None:
            message.add_alternative(html_body, subtype="html")

        try:
            response = await aiosmtplib.send(
                message,
                hostname=self._settings.SMTP_HOST,
                port=self._settings.SMTP_PORT,
                username=self._settings.SMTP_USERNAME,
                password=self._settings.SMTP_PASSWORD,
                use_tls=self._settings.SMTP_USE_TLS,
                start_tls=self._settings.SMTP_STARTTLS,
                timeout=self._settings.SMTP_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            raise SmtpSendError(redact_text(str(exc)) or "SMTP send failed") from exc

        provider_status = _safe_provider_status(response)
        return EmailSendResult(
            message_id=message_id,
            accepted_recipients=(to,),
            provider_status=provider_status,
        )

    def _validate_enabled_and_configured(self) -> None:
        if not self._settings.ENABLE_EMAIL_DELIVERY:
            raise EmailDeliveryDisabledError("Email delivery is disabled")
        if not self._settings.SMTP_HOST or not self._settings.SMTP_FROM:
            raise SmtpConfigurationError(
                "SMTP_HOST and SMTP_FROM are required when email delivery is enabled"
            )


def _safe_provider_status(response: object) -> str:
    if isinstance(response, tuple) and len(response) >= 2:
        return redact_text(str(response[1]))
    return redact_text(str(response))
