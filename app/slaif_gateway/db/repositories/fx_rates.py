"""Repository helpers for fx_rates table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import FxRate
from slaif_gateway.utils.admin_list_filters import as_value_tuple, or_equals


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

    async def list_fx_rates_for_admin(
        self,
        *,
        base_currency: str | Sequence[str] | None = None,
        quote_currency: str | Sequence[str] | None = None,
        source: str | Sequence[str] | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FxRate]:
        bases = as_value_tuple(base_currency)
        quotes = as_value_tuple(quote_currency)
        sources = as_value_tuple(source)
        # 195-a: OR WITHIN a field; pre-195 per-member normalization
        # preserved (exact currency equality, case-insensitive source
        # substring).
        statement: Select[tuple[FxRate]] = select(FxRate)
        if bases is not None:
            statement = statement.where(or_equals(FxRate.base_currency, bases))
        if quotes is not None:
            statement = statement.where(or_equals(FxRate.quote_currency, quotes))
        if sources is not None:
            statement = statement.where(
                or_(
                    *[FxRate.source.ilike(f"%{value}%") for value in sources]
                )
            )
        if active is not None and now is not None:
            active_condition = (
                (FxRate.valid_from <= now)
                & ((FxRate.valid_until.is_(None)) | (FxRate.valid_until >= now))
            )
            statement = statement.where(active_condition if active else ~active_condition)

        statement = statement.order_by(FxRate.valid_from.desc(), FxRate.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_fx_rate_for_admin_detail(self, fx_rate_id: uuid.UUID) -> FxRate | None:
        return await self._session.get(FxRate, fx_rate_id)

    async def update_fx_rate_metadata(
        self,
        fx_rate_id: uuid.UUID,
        *,
        base_currency: str,
        quote_currency: str,
        rate: Decimal,
        valid_from: datetime,
        valid_until: datetime | None,
        source: str | None,
    ) -> FxRate | None:
        row = await self.get_fx_rate_by_id(fx_rate_id)
        if row is None:
            return None

        row.base_currency = base_currency
        row.quote_currency = quote_currency
        row.rate = rate
        row.valid_from = valid_from
        row.valid_until = valid_until
        row.source = source
        await self._session.flush()
        return row

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

    # ------------------------------------------------------------------
    # 182: atomic apply supersession helper (A3). Additive: all
    # existing public methods above are preserved unchanged.
    # ------------------------------------------------------------------
    async def close_active_fx_rate(
        self,
        *,
        fx_rate_id: uuid.UUID,
        base_currency: str,
        quote_currency: str,
        rate: Decimal,
        valid_from: datetime,
        expected_valid_until: datetime | None,
        effective_at: datetime,
    ) -> bool:
        """Supersession close: end the active validity window of EXACTLY the
        FX row the reviewed plan identified, at the one effective T.

        Guarded on the baseline facts recorded in the plan (row identity,
        pair, exact rate, opening instant, the REVIEWED closing instant,
        still active at T). The reviewed closing instant is compared with
        exact NULL-safe equality (IS NOT DISTINCT FROM): a reviewed NULL
        end must still be NULL at apply time (a NULL -> finite drift is
        rejected, never wildcarded), and a reviewed finite future end —
        ordinary refresh state — must still be exactly that end and still
        in the future at T. Any drift or expiry means the row is not the
        reviewed active row and NOTHING is mutated. The window is then
        safely ended at the one effective T while the rate value and row
        identity stay untouched; the new rate is inserted as a new row at
        the same instant by the caller.
        """
        result = await self._session.execute(
            text(
                "UPDATE fx_rates SET valid_until = :effective_at "
                "WHERE id = :id "
                "AND base_currency = :base_currency "
                "AND quote_currency = :quote_currency "
                "AND rate = :rate "
                "AND valid_from = :valid_from "
                "AND valid_until IS NOT DISTINCT FROM :expected_valid_until "
                "AND (valid_until IS NULL OR valid_until > :effective_at)"
            ),
            {
                "id": fx_rate_id,
                "base_currency": base_currency,
                "quote_currency": quote_currency,
                "rate": rate,
                "valid_from": valid_from,
                "expected_valid_until": expected_valid_until,
                "effective_at": effective_at,
            },
        )
        return result.rowcount == 1
