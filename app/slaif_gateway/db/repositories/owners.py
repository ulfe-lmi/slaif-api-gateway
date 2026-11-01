"""Repository helpers for owners table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import GatewayKey, Owner
from slaif_gateway.utils.admin_list_filters import (
    as_uuid_tuple,
    as_value_tuple,
    or_equals,
)


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

    async def get_owner_for_update(self, owner_id: uuid.UUID) -> Owner | None:
        """Lock one owner row and repopulate its stored attributes.

        Partial edits call this FIRST in the caller-owned transaction so
        the row lock is held before any provided field is merged with
        the current stored values; the ``populate_existing`` execution
        option refreshes an already-identity-mapped instance with the
        locked row (same pattern as the key-repository locked lookup).
        """
        statement = (
            select(Owner)
            .where(Owner.id == owner_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_owner_by_email(self, email: str) -> Owner | None:
        statement = select(Owner).where(Owner.email == email)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_owners(
        self,
        *,
        institution_id: uuid.UUID | None = None,
        email: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Owner]:
        statement: Select[tuple[Owner]] = select(Owner)
        if institution_id is not None:
            statement = statement.where(Owner.institution_id == institution_id)
        if email is not None:
            statement = statement.where(Owner.email == email)

        statement = statement.order_by(Owner.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_owners_for_admin(
        self,
        *,
        email: str | Sequence[str] | None = None,
        institution_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        cohort_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Owner]:
        """Return owners with safe admin-dashboard relationships loaded."""
        emails = as_value_tuple(email)
        institution_ids = as_uuid_tuple(institution_id)
        cohort_ids = as_uuid_tuple(cohort_id)
        statement: Select[tuple[Owner]] = select(Owner).options(
            selectinload(Owner.institution),
            selectinload(Owner.gateway_keys).selectinload(GatewayKey.cohort),
        )
        # 195-a: OR WITHIN a filter field, AND ACROSS fields; predicates
        # apply in SQL BEFORE LIMIT/OFFSET (never post-fetch filtering).
        # Cohort membership stays an ANY/EXISTS over the GatewayKey
        # relationship, so an owner with several matching keys is returned
        # exactly once.
        if emails is not None:
            statement = statement.where(
                or_(
                    *[
                        func.lower(Owner.email).like(f"%{value.strip().lower()}%")
                        for value in emails
                    ]
                )
            )
        if institution_ids is not None:
            statement = statement.where(or_equals(Owner.institution_id, institution_ids))
        if cohort_ids is not None:
            statement = statement.where(
                Owner.gateway_keys.any(
                    or_equals(GatewayKey.cohort_id, cohort_ids)
                )
            )

        statement = statement.order_by(Owner.created_at.desc(), Owner.id.asc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_owner_for_admin_detail(self, owner_id: uuid.UUID) -> Owner | None:
        """Return one owner with safe admin-dashboard relationships loaded."""
        statement = (
            select(Owner)
            .options(
                selectinload(Owner.institution),
                selectinload(Owner.gateway_keys).selectinload(GatewayKey.cohort),
            )
            .where(Owner.id == owner_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

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

    async def update_owner_metadata(
        self,
        owner_id: uuid.UUID,
        *,
        name: str,
        surname: str,
        email: str,
        institution_id: uuid.UUID | None,
        external_id: str | None,
        notes: str | None,
        is_active: bool,
    ) -> Owner | None:
        owner = await self.get_owner_by_id(owner_id)
        if owner is None:
            return None

        owner.name = name
        owner.surname = surname
        owner.email = email
        owner.institution_id = institution_id
        owner.external_id = external_id
        owner.notes = notes
        owner.is_active = is_active
        await self._session.flush()
        return owner
