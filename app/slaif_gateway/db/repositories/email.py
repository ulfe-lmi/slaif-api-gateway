"""Repository helpers for email_deliveries table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import EmailDelivery, Owner
from slaif_gateway.utils.admin_list_filters import (
    as_uuid_tuple,
    as_value_tuple,
    or_equals,
)


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
        owner_email: str | Sequence[str] | None = None,
        gateway_key_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        one_time_secret_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        delivery_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        owner_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        owner_email_exact: str | Sequence[str] | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmailDelivery]:
        """Return email delivery rows with safe dashboard relationships loaded."""
        emails = as_value_tuple(owner_email)
        key_ids = as_uuid_tuple(gateway_key_id)
        secret_ids = as_uuid_tuple(one_time_secret_id)
        delivery_ids = as_uuid_tuple(delivery_id)
        owner_ids = as_uuid_tuple(owner_id)
        exact_emails = as_value_tuple(owner_email_exact)
        # 195-a: OR WITHIN a field, AND ACROSS fields; predicates apply in
        # SQL BEFORE LIMIT/OFFSET. Pre-195 per-member normalization
        # preserved (case-insensitive substring for owner email, exact
        # equality for the UUID ids and status).
        # 215-a: additive EXACT filters (delivery UUID, owner UUID,
        # normalized exact owner email) on the SAME query; the exact email
        # values arrive pre-normalized (strip/lower) by the caller, never
        # re-derived here.
        statement = _email_delivery_admin_statement()
        if status is not None:
            statement = statement.where(EmailDelivery.status == status)
        if emails is not None or exact_emails is not None:
            statement = statement.join(EmailDelivery.owner)
        if emails is not None:
            statement = statement.where(
                or_(
                    *[func.lower(Owner.email).like(f"%{value.lower()}%") for value in emails]
                )
            )
        if exact_emails is not None:
            statement = statement.where(
                or_(
                    *[func.lower(Owner.email) == value for value in exact_emails]
                )
            )
        if key_ids is not None:
            statement = statement.where(or_equals(EmailDelivery.gateway_key_id, key_ids))
        if secret_ids is not None:
            statement = statement.where(or_equals(EmailDelivery.one_time_secret_id, secret_ids))
        if delivery_ids is not None:
            statement = statement.where(or_equals(EmailDelivery.id, delivery_ids))
        if owner_ids is not None:
            statement = statement.where(or_equals(EmailDelivery.owner_id, owner_ids))
        if start_at is not None:
            statement = statement.where(EmailDelivery.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(EmailDelivery.created_at <= end_at)

        statement = statement.order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.asc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_email_delivery_for_admin_detail(self, email_delivery_id: uuid.UUID) -> EmailDelivery | None:
        statement = _email_delivery_admin_statement().where(EmailDelivery.id == email_delivery_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_email_deliveries_for_inspection(
        self,
        *,
        delivery_id: uuid.UUID | None = None,
        gateway_key_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        owner_email_normalized: str | None = None,
        status: str | None = None,
        created_from: datetime | None = None,
        created_until: datetime | None = None,
        limit: int,
        offset: int,
    ) -> list[EmailDelivery]:
        """Exact, AND-combined inspection filters applied in SQL BEFORE paging.

        202-a: deterministic `(created_at DESC, id DESC)` ordering; the
        caller passes `limit + 1` to derive an honest `has_more`. Owner
        email is an EXACT normalized match (never a GUI substring guess);
        creation bounds are inclusive.
        """
        statement: Select[tuple[EmailDelivery]] = select(EmailDelivery)
        if delivery_id is not None:
            statement = statement.where(EmailDelivery.id == delivery_id)
        if gateway_key_id is not None:
            statement = statement.where(EmailDelivery.gateway_key_id == gateway_key_id)
        if owner_id is not None:
            statement = statement.where(EmailDelivery.owner_id == owner_id)
        if owner_email_normalized is not None:
            statement = statement.join(EmailDelivery.owner).where(
                func.lower(Owner.email) == owner_email_normalized
            )
        if status is not None:
            statement = statement.where(EmailDelivery.status == status)
        if created_from is not None:
            statement = statement.where(EmailDelivery.created_at >= created_from)
        if created_until is not None:
            statement = statement.where(EmailDelivery.created_at <= created_until)

        statement = statement.order_by(
            EmailDelivery.created_at.desc(), EmailDelivery.id.desc()
        ).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def has_blocking_email_delivery_attempt(
        self,
        one_time_secret_id: uuid.UUID,
        *,
        statuses: tuple[str, ...] = ("sending", "sent", "ambiguous"),
    ) -> bool:
        """202-a: bounded EXISTS over the WHOLE same-secret set (indexed).

        `limit(1)` on the `one_time_secret_id` index: no page/tail can miss
        a blocking attempt, and no history rows are materialized.
        """
        statement = (
            select(EmailDelivery.id)
            .where(
                EmailDelivery.one_time_secret_id == one_time_secret_id,
                EmailDelivery.status.in_(statuses),
            )
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.first() is not None

    async def has_email_delivery_attempt(
        self,
        one_time_secret_id: uuid.UUID,
    ) -> bool:
        """202-a: bounded EXISTS of ANY prior delivery row for this exact secret.

        The no-ID path may only create the FIRST delivery for a secret;
        existing history (any status) requires an explicit selected-ID
        retry, never a silent new-row bypass.
        """
        statement = (
            select(EmailDelivery.id)
            .where(EmailDelivery.one_time_secret_id == one_time_secret_id)
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.first() is not None

    async def get_email_delivery_for_update_fresh(
        self, email_delivery_id: uuid.UUID
    ) -> EmailDelivery | None:
        """202-a: FOR UPDATE lock PLUS current-state refresh.

        `populate_existing` re-reads the row's columns so a row loaded
        before a blocking lock wait is not served from the stale ORM
        identity map. Selection semantics match
        `get_email_delivery_for_update`.
        """
        statement = (
            select(EmailDelivery)
            .where(EmailDelivery.id == email_delivery_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


def _email_delivery_admin_statement() -> Select[tuple[EmailDelivery]]:
    return select(EmailDelivery).options(
        selectinload(EmailDelivery.owner),
        selectinload(EmailDelivery.gateway_key),
        selectinload(EmailDelivery.one_time_secret),
    )
