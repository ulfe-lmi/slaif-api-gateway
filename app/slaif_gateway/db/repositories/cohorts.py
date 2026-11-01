"""Repository helpers for cohorts table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import Cohort, GatewayKey, Owner
from slaif_gateway.utils.admin_list_filters import as_value_tuple


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

    async def get_cohort_for_update(self, cohort_id: uuid.UUID) -> Cohort | None:
        """Lock one cohort row and repopulate its stored attributes.

        Partial edits call this FIRST in the caller-owned transaction so
        the row lock is held before any provided field is merged with
        the current stored values; the ``populate_existing`` execution
        option refreshes an already-identity-mapped instance with the
        locked row (same pattern as the key-repository locked lookup).
        """
        statement = (
            select(Cohort)
            .where(Cohort.id == cohort_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

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
        name: str | Sequence[str] | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Cohort]:
        """Return cohorts with safe admin-dashboard relationships loaded."""
        names = as_value_tuple(name)
        statement: Select[tuple[Cohort]] = select(Cohort).options(
            selectinload(Cohort.gateway_keys).selectinload(GatewayKey.owner).selectinload(Owner.institution),
        )
        # 195-a: OR WITHIN the name field, predicates before LIMIT/OFFSET.
        if names is not None:
            statement = statement.where(
                or_(
                    *[
                        func.lower(Cohort.name).like(f"%{value.strip().lower()}%")
                        for value in names
                    ]
                )
            )
        if active is not None and now is not None:
            active_filter = and_(
                or_(Cohort.starts_at.is_(None), Cohort.starts_at <= now),
                or_(Cohort.ends_at.is_(None), Cohort.ends_at >= now),
            )
            statement = statement.where(active_filter if active else ~active_filter)

        statement = (
            statement.order_by(
                Cohort.starts_at.desc().nullslast(), Cohort.name.asc(), Cohort.id.asc()
            ).limit(limit).offset(offset)
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
