from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.email_errors import (
    OneTimeSecretAlreadyConsumedError,
    OneTimeSecretExpiredError,
    OneTimeSecretPurposeError,
)
from slaif_gateway.services.secret_service import SecretService
from slaif_gateway.utils.secrets import encrypt_secret, generate_secret_key


@dataclass
class _SecretRow:
    id: uuid.UUID
    purpose: str
    encrypted_payload: str
    nonce: str
    expires_at: datetime
    status: str = "pending"
    consumed_at: datetime | None = None


class _Repo:
    def __init__(self, row: _SecretRow) -> None:
        self.row = row

    async def get_one_time_secret_for_update(self, one_time_secret_id: uuid.UUID):
        return self.row if one_time_secret_id == self.row.id else None

    async def mark_one_time_secret_consumed(self, one_time_secret_id: uuid.UUID, *, consumed_at: datetime) -> bool:
        if self.row.consumed_at is not None:
            return False
        self.row.consumed_at = consumed_at
        self.row.status = "consumed"
        return True

    async def mark_one_time_secret_revoked_or_expired(self, one_time_secret_id: uuid.UUID, *, status: str) -> bool:
        self.row.status = status
        return True


def _service(row: _SecretRow, key: str) -> SecretService:
    return SecretService(
        settings=Settings(ONE_TIME_SECRET_ENCRYPTION_KEY=key),
        one_time_secrets_repository=_Repo(row),
    )


def _row(*, key: str, plaintext: str = "secret") -> _SecretRow:
    encrypted = encrypt_secret(plaintext, key)
    return _SecretRow(
        id=uuid.uuid4(),
        purpose="gateway_key_email",
        encrypted_payload=encrypted.ciphertext,
        nonce=encrypted.nonce,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_secret_service_decrypts_and_consumes_valid_secret() -> None:
    key = generate_secret_key()
    row = _row(key=key, plaintext="sk-slaif-public.once-only-secret")

    plaintext = await _service(row, key).consume_one_time_secret(row.id, purpose="gateway_key_email")

    assert plaintext == "sk-slaif-public.once-only-secret"
    assert row.status == "consumed"
    assert row.consumed_at is not None


@pytest.mark.asyncio
async def test_secret_service_rejects_expired_secret() -> None:
    key = generate_secret_key()
    row = _row(key=key)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(OneTimeSecretExpiredError):
        await _service(row, key).consume_one_time_secret(row.id, purpose="gateway_key_email")

    assert row.status == "expired"
    assert row.consumed_at is None


@pytest.mark.asyncio
async def test_secret_service_rejects_consumed_secret() -> None:
    key = generate_secret_key()
    row = _row(key=key)
    row.status = "consumed"
    row.consumed_at = datetime.now(UTC)

    with pytest.raises(OneTimeSecretAlreadyConsumedError):
        await _service(row, key).consume_one_time_secret(row.id, purpose="gateway_key_email")


@pytest.mark.asyncio
async def test_secret_service_rejects_wrong_purpose() -> None:
    key = generate_secret_key()
    row = _row(key=key)

    with pytest.raises(OneTimeSecretPurposeError):
        await _service(row, key).consume_one_time_secret(row.id, purpose="gateway_key_rotation_email")
