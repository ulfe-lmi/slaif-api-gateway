"""Repository helpers for cohorts table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import Cohort


class CohortsRepository:
    """Encapsulates CRUD-style access for Cohort rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_cohort(
        self,
        *,
        name: str,
        description: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> Cohort:
        cohort = Cohort(
            name=name,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        self._session.add(cohort)
        await self._session.flush()
        return cohort

    async def get_cohort_by_id(self, cohort_id: uuid.UUID) -> Cohort | None:
        return await self._session.get(Cohort, cohort_id)

    async def list_cohorts(self, *, limit: int = 100, offset: int = 0) -> list[Cohort]:
        statement: Select[tuple[Cohort]] = (
            select(Cohort)
            .order_by(Cohort.starts_at.desc().nullslast(), Cohort.name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
