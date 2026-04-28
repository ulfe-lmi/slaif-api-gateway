"""Repository helpers for one_time_secrets table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import OneTimeSecret


class OneTimeSecretsRepository:
    """Encapsulates CRUD-style access for OneTimeSecret rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_one_time_secret(
        self,
        *,
        purpose: str,
        encrypted_payload: str,
        nonce: str,
        expires_at: datetime,
        owner_id: uuid.UUID | None = None,
        gateway_key_id: uuid.UUID | None = None,
        encryption_key_version: int = 1,
        status: str = "pending",
    ) -> OneTimeSecret:
        row = OneTimeSecret(
            purpose=purpose,
            encrypted_payload=encrypted_payload,
            nonce=nonce,
            expires_at=expires_at,
            owner_id=owner_id,
            gateway_key_id=gateway_key_id,
            encryption_key_version=encryption_key_version,
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_one_time_secret_by_id(self, one_time_secret_id: uuid.UUID) -> OneTimeSecret | None:
        return await self._session.get(OneTimeSecret, one_time_secret_id)

    async def get_one_time_secret_for_update(self, one_time_secret_id: uuid.UUID) -> OneTimeSecret | None:
        statement = select(OneTimeSecret).where(OneTimeSecret.id == one_time_secret_id).with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def mark_one_time_secret_consumed(
        self,
        one_time_secret_id: uuid.UUID,
        *,
        consumed_at: datetime,
    ) -> bool:
        statement = (
            update(OneTimeSecret)
            .where(
                OneTimeSecret.id == one_time_secret_id,
                OneTimeSecret.consumed_at.is_(None),
            )
            .values(status="consumed", consumed_at=consumed_at)
        )
        result = await self._session.execute(statement)
        return result.rowcount > 0

    async def mark_one_time_secret_revoked_or_expired(
        self,
        one_time_secret_id: uuid.UUID,
        *,
        status: str,
    ) -> bool:
        statement = (
            update(OneTimeSecret)
            .where(OneTimeSecret.id == one_time_secret_id)
            .values(status=status)
        )
        result = await self._session.execute(statement)
        return result.rowcount > 0
