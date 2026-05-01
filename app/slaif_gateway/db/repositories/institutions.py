"""Repository helpers for institutions table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import Institution, Owner


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

    async def list_institutions_for_admin(
        self,
        *,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Institution]:
        """Return institutions with safe admin-dashboard relationships loaded."""
        statement: Select[tuple[Institution]] = select(Institution).options(
            selectinload(Institution.owners).selectinload(Owner.gateway_keys),
        )
        if name is not None:
            normalized_name = name.strip().lower()
            statement = statement.where(func.lower(Institution.name).like(f"%{normalized_name}%"))

        statement = statement.order_by(Institution.name.asc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_institution_for_admin_detail(self, institution_id: uuid.UUID) -> Institution | None:
        """Return one institution with safe admin-dashboard relationships loaded."""
        statement = (
            select(Institution)
            .options(selectinload(Institution.owners).selectinload(Owner.gateway_keys))
            .where(Institution.id == institution_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update_institution_metadata(
        self,
        institution_id: uuid.UUID,
        *,
        name: str,
        country: str | None,
        notes: str | None,
    ) -> Institution | None:
        institution = await self.get_institution_by_id(institution_id)
        if institution is None:
            return None

        institution.name = name
        institution.country = country
        institution.notes = notes
        await self._session.flush()
        return institution
