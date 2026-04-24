"""Repository helpers for quota_reservations table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import QuotaReservation


class QuotaReservationsRepository:
    """Encapsulates CRUD-style access for QuotaReservation rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_reservation(
        self,
        *,
        gateway_key_id: uuid.UUID,
        request_id: str,
        endpoint: str,
        expires_at: datetime,
        requested_model: str | None = None,
        reserved_cost_eur: Decimal = Decimal("0"),
        reserved_tokens: int = 0,
        reserved_requests: int = 1,
        status: str = "pending",
    ) -> QuotaReservation:
        row = QuotaReservation(
            gateway_key_id=gateway_key_id,
            request_id=request_id,
            endpoint=endpoint,
            requested_model=requested_model,
            reserved_cost_eur=reserved_cost_eur,
            reserved_tokens=reserved_tokens,
            reserved_requests=reserved_requests,
            status=status,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_reservation_by_id(self, reservation_id: uuid.UUID) -> QuotaReservation | None:
        return await self._session.get(QuotaReservation, reservation_id)

    async def get_reservation_by_request_id(self, request_id: str) -> QuotaReservation | None:
        result = await self._session.execute(
            select(QuotaReservation).where(QuotaReservation.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def list_reservations_for_key(
        self,
        gateway_key_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[QuotaReservation]:
        statement: Select[tuple[QuotaReservation]] = select(QuotaReservation).where(
            QuotaReservation.gateway_key_id == gateway_key_id
        )
        if status is not None:
            statement = statement.where(QuotaReservation.status == status)

        statement = statement.order_by(QuotaReservation.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def update_reservation_status(
        self,
        reservation_id: uuid.UUID,
        *,
        status: str,
        finalized_at: datetime | None = None,
        released_at: datetime | None = None,
    ) -> bool:
        reservation = await self.get_reservation_by_id(reservation_id)
        if reservation is None:
            return False

        reservation.status = status
        reservation.finalized_at = finalized_at
        reservation.released_at = released_at
        await self._session.flush()
        return True

    async def finalize_reservation(self, reservation_id: uuid.UUID, *, finalized_at: datetime) -> bool:
        statement = (
            update(QuotaReservation)
            .where(QuotaReservation.id == reservation_id)
            .values(status="finalized", finalized_at=finalized_at, released_at=None)
        )
        result = await self._session.execute(statement)
        return result.rowcount > 0

    async def release_reservation(self, reservation_id: uuid.UUID, *, released_at: datetime) -> bool:
        statement = (
            update(QuotaReservation)
            .where(QuotaReservation.id == reservation_id)
            .values(status="released", released_at=released_at)
        )
        result = await self._session.execute(statement)
        return result.rowcount > 0

    async def list_expired_pending_reservations(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[QuotaReservation]:
        statement: Select[tuple[QuotaReservation]] = (
            select(QuotaReservation)
            .where(
                QuotaReservation.status == "pending",
                QuotaReservation.expires_at < now,
            )
            .order_by(QuotaReservation.expires_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
