"""Repository helpers for owners table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import Owner


class OwnersRepository:
    """Encapsulates CRUD-style access for Owner rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_owner(
        self,
        *,
        name: str,
        surname: str,
        email: str,
        institution_id: uuid.UUID | None = None,
        external_id: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
    ) -> Owner:
        owner = Owner(
            name=name,
            surname=surname,
            email=email,
            institution_id=institution_id,
            external_id=external_id,
            notes=notes,
            is_active=is_active,
        )
        self._session.add(owner)
        await self._session.flush()
        return owner

    async def get_owner_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        return await self._session.get(Owner, owner_id)

    async def get_owner_by_email(self, email: str) -> Owner | None:
        statement = select(Owner).where(Owner.email == email)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_owners(self, *, limit: int = 100, offset: int = 0) -> list[Owner]:
        statement: Select[tuple[Owner]] = (
            select(Owner).order_by(Owner.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def update_owner_basic_fields(
        self,
        owner_id: uuid.UUID,
        *,
        name: str | None = None,
        surname: str | None = None,
        institution_id: uuid.UUID | None = None,
        external_id: str | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
    ) -> Owner | None:
        owner = await self.get_owner_by_id(owner_id)
        if owner is None:
            return None

        if name is not None:
            owner.name = name
        if surname is not None:
            owner.surname = surname
        if institution_id is not None:
            owner.institution_id = institution_id
        if external_id is not None:
            owner.external_id = external_id
        if notes is not None:
            owner.notes = notes
        if is_active is not None:
            owner.is_active = is_active

        await self._session.flush()
        return owner
