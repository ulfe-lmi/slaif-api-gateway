"""Repository for organization records."""

from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import Organization


class OrganizationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        return await self._session.get(Organization, org_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[Organization]:
        stmt = select(Organization).order_by(Organization.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(self, *, name: str, slug: str, notes: str | None = None) -> Organization:
        org = Organization(name=name, slug=slug, notes=notes)
        self._session.add(org)
        await self._session.flush()
        return org
