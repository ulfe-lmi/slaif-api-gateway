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
    created_at: datetime | None = None
    provider_message_id: str | None = None
    error_message: str | None = None
    sent_at: datetime | None = None
    failed_at: datetime | None = None


class _OneTimeRepo:
    def __init__(self, row: _OneTimeSecret) -> None:
        self.row = row

    async def get_one_time_secret_by_id(self, one_time_secret_id: uuid.UUID):
        return self.row if one_time_secret_id == self.row.id else None

    async def get_one_time_secret_for_update(self, one_time_secret_id: uuid.UUID):
        return self.row if one_time_secret_id == self.row.id else None

    async def get_one_time_secret_for_update_fresh(self, one_time_secret_id: uuid.UUID):
        # 202-a: same selection; fake state is always current.
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

    async def get_email_delivery_for_update(self, email_delivery_id: uuid.UUID):
        return self.rows.get(email_delivery_id)

    async def get_email_delivery_for_update_fresh(self, email_delivery_id: uuid.UUID):
        # 202-a: same selection as get_email_delivery_for_update; the fake
        # rows are always current (no stale identity-map in unit doubles).
        return self.rows.get(email_delivery_id)

    async def has_blocking_email_delivery_attempt(
        self,
        one_time_secret_id: uuid.UUID,
        *,
        statuses: tuple[str, ...] = ("sending", "sent", "ambiguous"),
    ):
        # 202-a: whole same-secret set (fake has no tail beyond the dict).
        return any(
            row.one_time_secret_id == one_time_secret_id and row.status in statuses
            for row in self.rows.values()
        )

    async def has_email_delivery_attempt(self, one_time_secret_id: uuid.UUID):
        return any(
            row.one_time_secret_id == one_time_secret_id for row in self.rows.values()
        )

    async def mark_sending(self, email_delivery_id: uuid.UUID, *, started_at: datetime):
        row = self.rows[email_delivery_id]
        row.status = "sending"
        row.failed_at = started_at
        row.error_message = None
        return True

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

    async def mark_ambiguous(
        self,
        email_delivery_id: uuid.UUID,
        *,
        failed_at: datetime,
        error_message: str,
        provider_message_id: str | None = None,
    ):
        row = self.rows[email_delivery_id]
        row.status = "ambiguous"
        row.failed_at = failed_at
        row.error_message = error_message
        row.provider_message_id = provider_message_id
        return True


class _FinalizationFailingEmailRepo(_EmailRepo):
    async def mark_sent(self, email_delivery_id: uuid.UUID, *, sent_at: datetime, provider_message_id: str | None):
        raise RuntimeError("database finalization failed")


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


def _service_with_email_repo(*, email_repo: _EmailRepo, email_service: _EmailService | None = None):
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
    assert "sk-slaif-" not in (email_repo.rows[existing.id].error_message or "")


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


@pytest.mark.asyncio
async def test_email_delivery_service_creates_pending_delivery_without_plaintext() -> None:
    service, secret, email_repo, audit_repo, _sender, plaintext_key = _service()

    result = await service.create_pending_key_email_delivery(
        gateway_key_id=secret.gateway_key_id,
        one_time_secret_id=secret.id,
        owner_id=secret.owner_id,
    )

    assert result.status == "pending"
    assert result.email_delivery_id in email_repo.rows
    assert email_repo.rows[result.email_delivery_id].one_time_secret_id == secret.id
    assert secret.status == "pending"
    assert secret.consumed_at is None
    serialized = json.dumps(
        {
            "delivery": email_repo.rows[result.email_delivery_id].__dict__,
            "audit": audit_repo.calls,
        },
        default=str,
    )
    assert plaintext_key not in serialized
    assert secret.encrypted_payload not in serialized
    assert secret.nonce not in serialized


@pytest.mark.asyncio
async def test_email_delivery_sendability_requires_pending_unconsumed_secret() -> None:
    service, secret, email_repo, _audit_repo, _sender, _plaintext_key = _service()
    delivery = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret.owner_id,
        gateway_key_id=secret.gateway_key_id,
        one_time_secret_id=secret.id,
        status="pending",
    )

    sendability = await service.get_key_email_delivery_sendability(delivery.id)
    assert sendability.can_send is True
    assert sendability.one_time_secret_status == "present"

    secret.status = "consumed"
    secret.consumed_at = datetime.now(UTC)
    blocked = await service.get_key_email_delivery_sendability(delivery.id)
    assert blocked.can_send is False
    assert blocked.one_time_secret_status == "consumed"
    assert "rotated" in (blocked.blocking_reason or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_status", ["sent", "sending", "ambiguous"])
async def test_email_delivery_service_blocks_terminal_or_in_progress_statuses(delivery_status: str) -> None:
    service, secret, email_repo, _audit_repo, sender, _plaintext_key = _service()
    delivery = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret.owner_id,
        gateway_key_id=secret.gateway_key_id,
        one_time_secret_id=secret.id,
        status=delivery_status,
    )

    result = await service.send_pending_key_email(
        one_time_secret_id=secret.id,
        email_delivery_id=delivery.id,
    )

    assert result.status in {"failed", "ambiguous"}
    assert sender.sent_bodies == []
    assert email_repo.rows[delivery.id].status == delivery_status


@pytest.mark.asyncio
async def test_email_delivery_service_marks_ambiguous_after_finalization_failure() -> None:
    email_repo = _FinalizationFailingEmailRepo()
    service, secret, email_repo, audit_repo, sender, plaintext_key = _service_with_email_repo(email_repo=email_repo)
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

    assert result.status == "ambiguous"
    assert result.error_code == "email_delivery_finalization_failed"
    assert plaintext_key in sender.sent_bodies[0]
    assert email_repo.rows[existing.id].status == "ambiguous"
    assert plaintext_key not in (email_repo.rows[existing.id].error_message or "")
    serialized_audit = json.dumps(audit_repo.calls, default=str)
    assert plaintext_key not in serialized_audit

    retry = await service.send_pending_key_email(
        one_time_secret_id=secret.id,
        email_delivery_id=existing.id,
    )

    assert retry.status == "ambiguous"
    assert len(sender.sent_bodies) == 1


# --- 202-a send-boundary guards (focused, fake-repository evidence) ----------


class _MultiSecretRepo:
    def __init__(self, rows: list[_OneTimeSecret]) -> None:
        self.rows = {row.id: row for row in rows}

    async def get_one_time_secret_by_id(self, one_time_secret_id: uuid.UUID):
        return self.rows.get(one_time_secret_id)

    async def get_one_time_secret_for_update(self, one_time_secret_id: uuid.UUID):
        return self.rows.get(one_time_secret_id)

    async def get_one_time_secret_for_update_fresh(self, one_time_secret_id: uuid.UUID):
        # 202-a: same selection; fake state is always current.
        return self.rows.get(one_time_secret_id)

    async def mark_one_time_secret_consumed(self, one_time_secret_id: uuid.UUID, *, consumed_at: datetime) -> bool:
        row = self.rows.get(one_time_secret_id)
        if row is None or row.consumed_at is not None:
            return False
        row.status = "consumed"
        row.consumed_at = consumed_at
        return True

    async def mark_one_time_secret_revoked_or_expired(self, one_time_secret_id: uuid.UUID, *, status: str) -> bool:
        row = self.rows.get(one_time_secret_id)
        if row is None:
            return False
        row.status = status
        return True


def _two_secret_setup(*, email_repo: _EmailRepo | None = None):
    """Owner/key with TWO pending gateway-key secrets (same owner/key)."""
    encryption_key = generate_secret_key()
    owner = _Owner(id=uuid.uuid4())
    gateway_key = _GatewayKey(
        id=uuid.uuid4(),
        owner_id=owner.id,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
    )

    def _secret() -> _OneTimeSecret:
        encrypted = encrypt_secret(
            json.dumps(
                {
                    "plaintext_key": "sk-slaif-public.once-only-secret",
                    "gateway_key_id": str(gateway_key.id),
                    "owner_id": str(owner.id),
                    "purpose": "gateway_key_email",
                }
            ),
            encryption_key,
        )
        return _OneTimeSecret(
            id=uuid.uuid4(),
            purpose="gateway_key_email",
            owner_id=owner.id,
            gateway_key_id=gateway_key.id,
            encrypted_payload=encrypted.ciphertext,
            nonce=encrypted.nonce,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    secret_a = _secret()
    secret_b = _secret()
    sender = _EmailService()
    service = EmailDeliveryService(
        settings=Settings(
            ENABLE_EMAIL_DELIVERY=True,
            SMTP_HOST="localhost",
            SMTP_FROM="noreply@example.org",
            ONE_TIME_SECRET_ENCRYPTION_KEY=encryption_key,
            PUBLIC_BASE_URL="https://api.ulfe.slaif.si/v1",
        ),
        one_time_secrets_repository=_MultiSecretRepo([secret_a, secret_b]),
        email_deliveries_repository=email_repo or _EmailRepo(),
        gateway_keys_repository=_KeyRepo(gateway_key),
        owners_repository=_OwnerRepo(owner),
        audit_repository=_AuditRepo(),
        email_service=sender,
    )
    return service, secret_a, secret_b, sender


@pytest.mark.asyncio
async def test_send_refuses_mismatched_secret_same_owner_key() -> None:
    # 202-a root probe: a DIFFERENT secret UUID with matching owner/key must
    # be refused at the shared locked send boundary (exact binding).
    service, secret_a, secret_b, sender = _two_secret_setup()
    delivery_repo = service._email_deliveries_repository
    delivery = await delivery_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="pending",
    )

    result = await service.send_pending_key_email(
        one_time_secret_id=secret_b.id,
        email_delivery_id=delivery.id,
    )

    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert sender.sent_bodies == []
    assert secret_a.consumed_at is None
    assert secret_b.consumed_at is None
    assert delivery.status == "pending"


@pytest.mark.asyncio
async def test_selected_foreign_owner_binding_refused_before_decryption(monkeypatch) -> None:
    # 202-a root probe: a selected delivery whose bound secret belongs to a
    # DIFFERENT owner/key must be refused before the real crypto runs.
    service, secret, email_repo, _audit_repo, sender, _plaintext_key = _service()
    foreign_owner = _Owner(id=uuid.uuid4())
    foreign_key = _GatewayKey(
        id=uuid.uuid4(),
        owner_id=foreign_owner.id,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
    )
    foreign_secret = _OneTimeSecret(
        id=uuid.uuid4(),
        purpose="gateway_key_email",
        owner_id=foreign_owner.id,
        gateway_key_id=foreign_key.id,
        encrypted_payload="foreign-ciphertext-never-decrypted",
        nonce="foreign-nonce",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    service._one_time_secrets_repository = _OneTimeRepo(foreign_secret)
    delivery = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret.owner_id,
        gateway_key_id=secret.gateway_key_id,
        one_time_secret_id=foreign_secret.id,
        status="pending",
    )

    decrypt_calls = 0

    def no_decrypt(*args, **kwargs):
        nonlocal decrypt_calls
        decrypt_calls += 1
        raise AssertionError("real crypto must not run for a foreign binding")

    monkeypatch.setattr("slaif_gateway.services.secret_service.decrypt_secret", no_decrypt)

    result = await service.send_pending_key_email(
        one_time_secret_id=foreign_secret.id,
        email_delivery_id=delivery.id,
    )

    assert result.status == "failed"
    assert result.error_code == "email_delivery_not_sendable"
    assert "does not match" in result.error_message
    assert decrypt_calls == 0
    assert sender.sent_bodies == []
    assert foreign_secret.consumed_at is None


@pytest.mark.asyncio
async def test_selected_revoked_secret_refused_before_decryption(monkeypatch) -> None:
    # 202-a: revoked selected material keeps the existing pre-crypto
    # classification and never invokes the real crypto.
    service, secret, email_repo, _audit_repo, sender, _plaintext_key = _service()
    secret.status = "revoked"
    delivery = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret.owner_id,
        gateway_key_id=secret.gateway_key_id,
        one_time_secret_id=secret.id,
        status="pending",
    )

    decrypt_calls = 0

    def no_decrypt(*args, **kwargs):
        nonlocal decrypt_calls
        decrypt_calls += 1
        raise AssertionError("real crypto must not run for revoked material")

    monkeypatch.setattr("slaif_gateway.services.secret_service.decrypt_secret", no_decrypt)

    result = await service.send_pending_key_email(
        one_time_secret_id=secret.id,
        email_delivery_id=delivery.id,
    )

    assert result.status == "failed"
    assert result.error_code == "one_time_secret_already_consumed"
    assert decrypt_calls == 0
    assert sender.sent_bodies == []
    assert secret.consumed_at is None


@pytest.mark.asyncio
async def test_sendability_agrees_with_sender_for_blocked_same_secret_row() -> None:
    # 202-a shared-sendability consistency: a selected PENDING row whose
    # same secret has another AMBIGUOUS attempt must report can_send=False
    # (read-only result agrees with the sender; no decryption).
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, _sender = _two_secret_setup(email_repo=email_repo)
    selected = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="pending",
    )
    await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="ambiguous",
    )

    sendability = await service.get_key_email_delivery_sendability(selected.id)

    assert sendability.can_send is False
    assert "sending, sent, or ambiguous" in (sendability.blocking_reason or "")

    clean = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="pending",
    )
    # the ambiguous row still blocks this clean pending sibling too
    clean_sendability = await service.get_key_email_delivery_sendability(clean.id)
    assert clean_sendability.can_send is False


@pytest.mark.asyncio
async def test_send_refuses_unknown_selected_delivery_without_implicit_creation() -> None:
    # 202-a root probe: a supplied missing delivery UUID is a missing/unsafe
    # selected target, NEVER implicit creation of another delivery.
    service, secret_a, _secret_b, sender = _two_secret_setup()
    delivery_repo = service._email_deliveries_repository

    result = await service.send_pending_key_email(
        one_time_secret_id=secret_a.id,
        email_delivery_id=uuid.uuid4(),
    )

    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert delivery_repo.rows == {}
    assert sender.sent_bodies == []
    assert secret_a.consumed_at is None


@pytest.mark.asyncio
async def test_omitted_selector_blocked_by_prior_ambiguous_attempt() -> None:
    # 202-a root probe: omitting the selector for the same secret must NOT
    # create a fresh attempt around a prior ambiguous row.
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    prior = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="ambiguous",
    )

    result = await service.send_pending_key_email(one_time_secret_id=secret_a.id)

    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert list(email_repo.rows) == [prior.id]
    assert prior.status == "ambiguous"
    assert sender.sent_bodies == []
    assert secret_a.consumed_at is None


@pytest.mark.asyncio
async def test_selected_retryable_row_blocked_by_prior_sending_attempt() -> None:
    # A different retryable row selected while another same-secret row is
    # `sending` must be refused (no convenient-row bypass).
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    in_flight = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="sending",
    )
    retryable = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="failed",
    )

    result = await service.send_pending_key_email(
        one_time_secret_id=secret_a.id,
        email_delivery_id=retryable.id,
    )

    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert in_flight.status == "sending"
    assert retryable.status == "failed"
    assert sender.sent_bodies == []
    assert secret_a.consumed_at is None


@pytest.mark.asyncio
async def test_no_id_refused_when_prior_failed_history_exists() -> None:
    # 202-a: no-ID is a genuine initial creation only. Retained failed
    # history must be retried via selected-ID / explicit retry, never by
    # silently creating a fresh row.
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    failed = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="failed",
    )

    result = await service.send_pending_key_email(one_time_secret_id=secret_a.id)

    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert list(email_repo.rows) == [failed.id]
    assert failed.status == "failed"
    assert sender.sent_bodies == []
    assert secret_a.consumed_at is None


@pytest.mark.asyncio
async def test_no_id_refused_when_prior_cancelled_history_exists() -> None:
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    cancelled = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="cancelled",
    )

    result = await service.send_pending_key_email(one_time_secret_id=secret_a.id)

    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert list(email_repo.rows) == [cancelled.id]
    assert sender.sent_bodies == []
    assert secret_a.consumed_at is None


@pytest.mark.asyncio
async def test_selected_failed_retry_still_works_with_clean_history() -> None:
    # The legitimate path: select the FAILED row explicitly (the service
    # shared layer permits failed retries; the CLI adds flag/reason).
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    failed = await email_repo.create_email_delivery(
        recipient_email="ada@example.org",
        subject="Subject",
        template_name="gateway_key_email",
        owner_id=secret_a.owner_id,
        gateway_key_id=secret_a.gateway_key_id,
        one_time_secret_id=secret_a.id,
        status="failed",
    )

    result = await service.send_pending_key_email(
        one_time_secret_id=secret_a.id,
        email_delivery_id=failed.id,
    )

    assert result.status == "sent"
    assert failed.status == "sent"
    assert secret_a.consumed_at is not None
    assert len(sender.sent_bodies) == 1
    assert len(email_repo.rows) == 1


@pytest.mark.asyncio
async def test_expired_after_lock_wait_is_not_decrypted() -> None:
    # 202-a: the fresh instant chosen AFTER owning the secret lock rejects
    # expired material BEFORE decryption (no stale pre-wait clock use).
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    secret_a.expires_at = datetime.now(UTC) + timedelta(seconds=1)
    # the fresh (post-lock) instant is already past expiry
    service._now_factory = lambda: datetime.now(UTC) + timedelta(seconds=60)

    result = await service.send_pending_key_email(one_time_secret_id=secret_a.id)

    assert result.status == "failed"
    assert result.error_code == "one_time_secret_expired"
    assert sender.sent_bodies == []
    assert secret_a.status == "expired"


@pytest.mark.asyncio
async def test_consumed_after_lock_wait_is_not_decrypted() -> None:
    email_repo = _EmailRepo()
    service, secret_a, _secret_b, sender = _two_secret_setup(email_repo=email_repo)
    secret_a.status = "consumed"
    consumed_at = datetime.now(UTC)
    secret_a.consumed_at = consumed_at

    result = await service.send_pending_key_email(one_time_secret_id=secret_a.id)

    assert result.status == "failed"
    assert result.error_code == "one_time_secret_already_consumed"
    assert sender.sent_bodies == []
