from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_errors import SmtpSendError
from slaif_gateway.services.email_service import EmailSendResult
from slaif_gateway.utils.secrets import encrypt_secret, generate_secret_key


@dataclass
class _Owner:
    id: uuid.UUID
    name: str = "Ada"
    surname: str = "Lovelace"
    email: str = "ada@example.org"


@dataclass
class _GatewayKey:
    id: uuid.UUID
    owner_id: uuid.UUID
    valid_from: datetime
    valid_until: datetime
    cost_limit_eur: Decimal | None = Decimal("10")
    token_limit_total: int | None = 1000
    request_limit_total: int | None = 20


@dataclass
class _OneTimeSecret:
    id: uuid.UUID
    purpose: str
    owner_id: uuid.UUID
    gateway_key_id: uuid.UUID
    encrypted_payload: str
    nonce: str
    expires_at: datetime
    status: str = "pending"
    consumed_at: datetime | None = None


@dataclass
class _EmailDelivery:
    id: uuid.UUID
    recipient_email: str
    subject: str
    template_name: str
    owner_id: uuid.UUID | None
    gateway_key_id: uuid.UUID | None
    one_time_secret_id: uuid.UUID | None
    status: str = "pending"
    provider_message_id: str | None = None
    error_message: str | None = None
    sent_at: datetime | None = None
    failed_at: datetime | None = None


class _OneTimeRepo:
    def __init__(self, row: _OneTimeSecret) -> None:
        self.row = row

    async def get_one_time_secret_for_update(self, one_time_secret_id: uuid.UUID):
        return self.row if one_time_secret_id == self.row.id else None

    async def mark_one_time_secret_consumed(self, one_time_secret_id: uuid.UUID, *, consumed_at: datetime) -> bool:
        if self.row.consumed_at is not None:
            return False
        self.row.status = "consumed"
        self.row.consumed_at = consumed_at
        return True

    async def mark_one_time_secret_revoked_or_expired(self, one_time_secret_id: uuid.UUID, *, status: str) -> bool:
        self.row.status = status
        return True


class _EmailRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, _EmailDelivery] = {}

    async def create_email_delivery(self, **kwargs):
        row = _EmailDelivery(id=uuid.uuid4(), **kwargs)
        self.rows[row.id] = row
        return row

    async def get_email_delivery_by_id(self, email_delivery_id: uuid.UUID):
        return self.rows.get(email_delivery_id)

    async def mark_sent(self, email_delivery_id: uuid.UUID, *, sent_at: datetime, provider_message_id: str | None):
        row = self.rows[email_delivery_id]
        row.status = "sent"
        row.sent_at = sent_at
        row.provider_message_id = provider_message_id
        return True

    async def mark_failed(self, email_delivery_id: uuid.UUID, *, failed_at: datetime, error_message: str):
        row = self.rows[email_delivery_id]
        row.status = "failed"
        row.failed_at = failed_at
        row.error_message = error_message
        return True


class _KeyRepo:
    def __init__(self, row: _GatewayKey) -> None:
        self.row = row

    async def get_gateway_key_by_id(self, gateway_key_id: uuid.UUID):
        return self.row if gateway_key_id == self.row.id else None


class _OwnerRepo:
    def __init__(self, row: _Owner) -> None:
        self.row = row

    async def get_owner_by_id(self, owner_id: uuid.UUID):
        return self.row if owner_id == self.row.id else None


class _AuditRepo:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.calls.append(kwargs)


class _EmailService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent_bodies: list[str] = []

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        self.sent_bodies.append(text_body)
        if self.fail:
            raise SmtpSendError("smtp failed password=***")
        return EmailSendResult(
            message_id="<message@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )


def _service(*, email_service: _EmailService | None = None):
    encryption_key = generate_secret_key()
    owner = _Owner(id=uuid.uuid4())
    gateway_key = _GatewayKey(
        id=uuid.uuid4(),
        owner_id=owner.id,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
    )
    plaintext_key = "sk-slaif-public.once-only-secret"
    encrypted = encrypt_secret(
        json.dumps(
            {
                "plaintext_key": plaintext_key,
                "gateway_key_id": str(gateway_key.id),
                "owner_id": str(owner.id),
                "purpose": "gateway_key_email",
            }
        ),
        encryption_key,
    )
    secret = _OneTimeSecret(
        id=uuid.uuid4(),
        purpose="gateway_key_email",
        owner_id=owner.id,
        gateway_key_id=gateway_key.id,
        encrypted_payload=encrypted.ciphertext,
        nonce=encrypted.nonce,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    email_repo = _EmailRepo()
    audit_repo = _AuditRepo()
    sender = email_service or _EmailService()
    service = EmailDeliveryService(
        settings=Settings(
            ENABLE_EMAIL_DELIVERY=True,
            SMTP_HOST="localhost",
            SMTP_FROM="noreply@example.org",
            ONE_TIME_SECRET_ENCRYPTION_KEY=encryption_key,
            PUBLIC_BASE_URL="https://api.ulfe.slaif.si/v1",
        ),
        one_time_secrets_repository=_OneTimeRepo(secret),
        email_deliveries_repository=email_repo,
        gateway_keys_repository=_KeyRepo(gateway_key),
        owners_repository=_OwnerRepo(owner),
        audit_repository=audit_repo,
        email_service=sender,
    )
    return service, secret, email_repo, audit_repo, sender, plaintext_key


@pytest.mark.asyncio
async def test_email_delivery_service_sends_and_consumes_secret() -> None:
    service, secret, email_repo, audit_repo, sender, plaintext_key = _service()

    result = await service.send_pending_key_email(one_time_secret_id=secret.id)

    assert result.status == "sent"
    assert secret.status == "consumed"
    assert secret.consumed_at is not None
    assert email_repo.rows[result.email_delivery_id].status == "sent"
    assert plaintext_key in sender.sent_bodies[0]
    assert "token_hash" not in sender.sent_bodies[0]
    serialized_audit = json.dumps(audit_repo.calls, default=str)
    assert plaintext_key not in serialized_audit
    assert secret.encrypted_payload not in serialized_audit
    assert secret.nonce not in serialized_audit


@pytest.mark.asyncio
async def test_email_delivery_service_records_failure_without_consuming_secret() -> None:
    service, secret, email_repo, _audit_repo, _sender, _plaintext_key = _service(
        email_service=_EmailService(fail=True)
    )
    existing = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret.owner_id,
        gateway_key_id=secret.gateway_key_id,
        one_time_secret_id=secret.id,
        status="pending",
    )

    result = await service.send_pending_key_email(
        one_time_secret_id=secret.id,
        email_delivery_id=existing.id,
    )

    assert result.status == "failed"
    assert secret.status == "pending"
    assert secret.consumed_at is None
    assert email_repo.rows[existing.id].status == "failed"
    assert "smtp-secret" not in (email_repo.rows[existing.id].error_message or "")


@pytest.mark.asyncio
async def test_email_delivery_service_marks_created_delivery_failed_on_smtp_error() -> None:
    service, secret, email_repo, _audit_repo, _sender, _plaintext_key = _service(
        email_service=_EmailService(fail=True)
    )

    result = await service.send_pending_key_email(one_time_secret_id=secret.id)

    assert result.status == "failed"
    assert result.email_delivery_id in email_repo.rows
    assert email_repo.rows[result.email_delivery_id].status == "failed"
    assert secret.status == "pending"
