"""Repository helpers for cohorts table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import Cohort, GatewayKey, Owner


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

    async def get_cohort_by_name(self, name: str) -> Cohort | None:
        statement = select(Cohort).where(Cohort.name == name)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_cohorts(self, *, limit: int = 100, offset: int = 0) -> list[Cohort]:
        statement: Select[tuple[Cohort]] = (
            select(Cohort)
            .order_by(Cohort.starts_at.desc().nullslast(), Cohort.name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_cohorts_for_admin(
        self,
        *,
        name: str | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Cohort]:
        """Return cohorts with safe admin-dashboard relationships loaded."""
        statement: Select[tuple[Cohort]] = select(Cohort).options(
            selectinload(Cohort.gateway_keys).selectinload(GatewayKey.owner).selectinload(Owner.institution),
        )
        if name is not None:
            normalized_name = name.strip().lower()
            statement = statement.where(func.lower(Cohort.name).like(f"%{normalized_name}%"))
        if active is not None and now is not None:
            active_filter = and_(
                or_(Cohort.starts_at.is_(None), Cohort.starts_at <= now),
                or_(Cohort.ends_at.is_(None), Cohort.ends_at >= now),
            )
            statement = statement.where(active_filter if active else ~active_filter)

        statement = (
            statement.order_by(Cohort.starts_at.desc().nullslast(), Cohort.name.asc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_cohort_for_admin_detail(self, cohort_id: uuid.UUID) -> Cohort | None:
        """Return one cohort with safe admin-dashboard relationships loaded."""
        statement = (
            select(Cohort)
            .options(
                selectinload(Cohort.gateway_keys).selectinload(GatewayKey.owner).selectinload(Owner.institution),
            )
            .where(Cohort.id == cohort_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update_cohort_metadata(
        self,
        cohort_id: uuid.UUID,
        *,
        name: str,
        description: str | None,
        starts_at: datetime | None,
        ends_at: datetime | None,
    ) -> Cohort | None:
        cohort = await self.get_cohort_by_id(cohort_id)
        if cohort is None:
            return None

        cohort.name = name
        cohort.description = description
        cohort.starts_at = starts_at
        cohort.ends_at = ends_at
        await self._session.flush()
        return cohort
