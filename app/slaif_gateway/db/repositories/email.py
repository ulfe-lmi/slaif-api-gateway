"""Repository helpers for email_deliveries table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import EmailDelivery, Owner


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

    async def get_email_delivery_for_update(self, email_delivery_id: uuid.UUID) -> EmailDelivery | None:
        statement = select(EmailDelivery).where(EmailDelivery.id == email_delivery_id).with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def mark_sending(
        self,
        email_delivery_id: uuid.UUID,
        *,
        started_at: datetime,
    ) -> bool:
        return await self.update_email_delivery_status(
            email_delivery_id,
            status="sending",
            provider_message_id=None,
            error_message=None,
            sent_at=None,
            failed_at=started_at,
        )

    async def mark_sent(
        self,
        email_delivery_id: uuid.UUID,
        *,
        sent_at: datetime,
        provider_message_id: str | None = None,
    ) -> bool:
        return await self.update_email_delivery_status(
            email_delivery_id,
            status="sent",
            provider_message_id=provider_message_id,
            error_message=None,
            sent_at=sent_at,
            failed_at=None,
        )

    async def mark_ambiguous(
        self,
        email_delivery_id: uuid.UUID,
        *,
        failed_at: datetime,
        error_message: str,
        provider_message_id: str | None = None,
    ) -> bool:
        return await self.update_email_delivery_status(
            email_delivery_id,
            status="ambiguous",
            provider_message_id=provider_message_id,
            error_message=error_message,
            sent_at=None,
            failed_at=failed_at,
        )

    async def mark_failed(
        self,
        email_delivery_id: uuid.UUID,
        *,
        failed_at: datetime,
        error_message: str,
    ) -> bool:
        return await self.update_email_delivery_status(
            email_delivery_id,
            status="failed",
            provider_message_id=None,
            error_message=error_message,
            sent_at=None,
            failed_at=failed_at,
        )

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

    async def list_email_deliveries_for_admin(
        self,
        *,
        status: str | None = None,
        owner_email: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
        one_time_secret_id: uuid.UUID | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmailDelivery]:
        """Return email delivery rows with safe dashboard relationships loaded."""
        statement = _email_delivery_admin_statement()
        if status is not None:
            statement = statement.where(EmailDelivery.status == status)
        if owner_email is not None:
            statement = statement.join(EmailDelivery.owner).where(
                func.lower(Owner.email).like(f"%{owner_email.lower()}%")
            )
        if gateway_key_id is not None:
            statement = statement.where(EmailDelivery.gateway_key_id == gateway_key_id)
        if one_time_secret_id is not None:
            statement = statement.where(EmailDelivery.one_time_secret_id == one_time_secret_id)
        if start_at is not None:
            statement = statement.where(EmailDelivery.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(EmailDelivery.created_at <= end_at)

        statement = statement.order_by(EmailDelivery.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_email_delivery_for_admin_detail(self, email_delivery_id: uuid.UUID) -> EmailDelivery | None:
        statement = _email_delivery_admin_statement().where(EmailDelivery.id == email_delivery_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


def _email_delivery_admin_statement() -> Select[tuple[EmailDelivery]]:
    return select(EmailDelivery).options(
        selectinload(EmailDelivery.owner),
        selectinload(EmailDelivery.gateway_key),
        selectinload(EmailDelivery.one_time_secret),
    )
