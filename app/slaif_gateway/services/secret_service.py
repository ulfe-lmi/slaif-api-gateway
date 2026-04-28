"""One-time secret consumption for key delivery workflows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from slaif_gateway.config import Settings
from slaif_gateway.db.models import OneTimeSecret
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.services.email_errors import (
    OneTimeSecretAlreadyConsumedError,
    OneTimeSecretExpiredError,
    OneTimeSecretNotFoundError,
    OneTimeSecretPurposeError,
    SmtpConfigurationError,
)
from slaif_gateway.utils.secrets import EncryptedSecret, decrypt_secret


@dataclass(frozen=True, slots=True)
class DecryptedOneTimeSecret:
    """Decrypted one-time secret payload kept in process memory only."""

    row: OneTimeSecret
    plaintext: str


class SecretService:
    """Decrypts and consumes one-time secrets without logging plaintext."""

    def __init__(
        self,
        *,
        settings: Settings,
        one_time_secrets_repository: OneTimeSecretsRepository,
    ) -> None:
        self._settings = settings
        self._one_time_secrets_repository = one_time_secrets_repository

    async def decrypt_pending_one_time_secret_for_update(
        self,
        secret_id: uuid.UUID,
        *,
        purpose: str,
        now: datetime | None = None,
    ) -> DecryptedOneTimeSecret:
        """Lock, validate, and decrypt a pending one-time secret."""
        if not self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY:
            raise SmtpConfigurationError("ONE_TIME_SECRET_ENCRYPTION_KEY is required")

        checked_at = now or datetime.now(UTC)
        row = await self._one_time_secrets_repository.get_one_time_secret_for_update(secret_id)
        if row is None:
            raise OneTimeSecretNotFoundError("One-time secret was not found")
        if row.purpose != purpose:
            raise OneTimeSecretPurposeError("One-time secret purpose does not match requested delivery")
        if row.status == "consumed" or row.consumed_at is not None:
            raise OneTimeSecretAlreadyConsumedError("One-time secret was already consumed")
        if row.status != "pending":
            raise OneTimeSecretAlreadyConsumedError("One-time secret is no longer pending")
        if row.expires_at <= checked_at:
            await self._one_time_secrets_repository.mark_one_time_secret_revoked_or_expired(
                secret_id,
                status="expired",
            )
            raise OneTimeSecretExpiredError("One-time secret has expired")

        plaintext = decrypt_secret(
            EncryptedSecret(ciphertext=row.encrypted_payload, nonce=row.nonce),
            self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
        ).decode("utf-8")
        return DecryptedOneTimeSecret(row=row, plaintext=plaintext)

    async def mark_consumed(self, secret_id: uuid.UUID, *, consumed_at: datetime) -> bool:
        """Mark a one-time secret consumed exactly once."""
        return await self._one_time_secrets_repository.mark_one_time_secret_consumed(
            secret_id,
            consumed_at=consumed_at,
        )

    async def consume_one_time_secret(
        self,
        secret_id: uuid.UUID,
        *,
        purpose: str,
        now: datetime | None = None,
    ) -> str:
        """Validate, decrypt, and mark a one-time secret consumed."""
        checked_at = now or datetime.now(UTC)
        decrypted = await self.decrypt_pending_one_time_secret_for_update(
            secret_id,
            purpose=purpose,
            now=checked_at,
        )
        consumed = await self.mark_consumed(secret_id, consumed_at=checked_at)
        if not consumed:
            raise OneTimeSecretAlreadyConsumedError("One-time secret was already consumed")
        return decrypted.plaintext
