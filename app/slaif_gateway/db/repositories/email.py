"""Repository helpers for email_deliveries table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import EmailDelivery


class EmailDeliveriesRepository:
    """Encapsulates CRUD-style access for EmailDelivery rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_email_delivery(
        self,
        *,
        recipient_email: str,
        subject: str,
        template_name: str,
        owner_id: uuid.UUID | None = None,
        gateway_key_id: uuid.UUID | None = None,
        one_time_secret_id: uuid.UUID | None = None,
        status: str = "pending",
    ) -> EmailDelivery:
        row = EmailDelivery(
            recipient_email=recipient_email,
            subject=subject,
            template_name=template_name,
            owner_id=owner_id,
            gateway_key_id=gateway_key_id,
            one_time_secret_id=one_time_secret_id,
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_email_delivery_status(
        self,
        email_delivery_id: uuid.UUID,
        *,
        status: str,
        provider_message_id: str | None = None,
        error_message: str | None = None,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
    ) -> bool:
        email_delivery = await self.get_email_delivery_by_id(email_delivery_id)
        if email_delivery is None:
            return False

        email_delivery.status = status
        email_delivery.provider_message_id = provider_message_id
        email_delivery.error_message = error_message
        email_delivery.sent_at = sent_at
        email_delivery.failed_at = failed_at
        await self._session.flush()
        return True

    async def get_email_delivery_by_id(self, email_delivery_id: uuid.UUID) -> EmailDelivery | None:
        return await self._session.get(EmailDelivery, email_delivery_id)

    async def list_email_deliveries(
        self,
        *,
        status: str | None = None,
        owner_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EmailDelivery]:
        statement: Select[tuple[EmailDelivery]] = select(EmailDelivery)
        if status is not None:
            statement = statement.where(EmailDelivery.status == status)
        if owner_id is not None:
            statement = statement.where(EmailDelivery.owner_id == owner_id)

        statement = statement.order_by(EmailDelivery.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
