"""Repository helpers for institutions table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import Institution


class InstitutionsRepository:
    """Encapsulates CRUD-style access for Institution rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_institution(
        self,
        *,
        name: str,
        country: str | None = None,
        notes: str | None = None,
    ) -> Institution:
        institution = Institution(name=name, country=country, notes=notes)
        self._session.add(institution)
        await self._session.flush()
        return institution

    async def get_institution_by_id(self, institution_id: uuid.UUID) -> Institution | None:
        return await self._session.get(Institution, institution_id)

    async def get_institution_by_name(self, name: str) -> Institution | None:
        statement = select(Institution).where(func.lower(Institution.name) == name.lower())
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_institutions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Institution]:
        statement: Select[tuple[Institution]] = (
            select(Institution).order_by(Institution.name.asc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
