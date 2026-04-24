"""Repository helpers for fx_rates table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import FxRate


class FxRatesRepository:
    """Encapsulates CRUD-style access for FxRate rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_fx_rate(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        rate: Decimal,
        valid_from: datetime,
        valid_until: datetime | None = None,
        source: str | None = None,
    ) -> FxRate:
        row = FxRate(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=rate,
            valid_from=valid_from,
            valid_until=valid_until,
            source=source,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_fx_rate_by_id(self, fx_rate_id: uuid.UUID) -> FxRate | None:
        return await self._session.get(FxRate, fx_rate_id)

    async def list_fx_rates(
        self,
        *,
        base_currency: str | None = None,
        quote_currency: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FxRate]:
        statement: Select[tuple[FxRate]] = select(FxRate)
        if base_currency is not None:
            statement = statement.where(FxRate.base_currency == base_currency)
        if quote_currency is not None:
            statement = statement.where(FxRate.quote_currency == quote_currency)

        statement = statement.order_by(FxRate.valid_from.desc(), FxRate.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def find_latest_rate(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        at_time: datetime | None = None,
    ) -> FxRate | None:
        statement: Select[tuple[FxRate]] = select(FxRate).where(
            FxRate.base_currency == base_currency,
            FxRate.quote_currency == quote_currency,
        )
        if at_time is not None:
            statement = statement.where(
                FxRate.valid_from <= at_time,
                (FxRate.valid_until.is_(None)) | (FxRate.valid_until > at_time),
            )

        statement = statement.order_by(FxRate.valid_from.desc(), FxRate.created_at.desc()).limit(1)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_rates_for_pair(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FxRate]:
        statement: Select[tuple[FxRate]] = (
            select(FxRate)
            .where(
                FxRate.base_currency == base_currency,
                FxRate.quote_currency == quote_currency,
            )
            .order_by(FxRate.valid_from.desc(), FxRate.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
