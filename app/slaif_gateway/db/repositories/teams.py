"""Repository for team records."""

from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import Team, TeamMember


class TeamsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, team_id: uuid.UUID) -> Team | None:
        return await self._session.get(Team, team_id)

    async def get_by_slug(self, org_id: uuid.UUID, slug: str) -> Team | None:
        stmt = select(Team).where(Team.organization_id == org_id, Team.slug == slug)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_organization(self, org_id: uuid.UUID) -> list[Team]:
        stmt = select(Team).where(Team.organization_id == org_id).order_by(Team.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(self, *, organization_id: uuid.UUID, name: str, slug: str, notes: str | None = None) -> Team:
        team = Team(organization_id=organization_id, name=name, slug=slug, notes=notes)
        self._session.add(team)
        await self._session.flush()
        return team

    async def add_member(self, *, team_id: uuid.UUID, owner_id: uuid.UUID, role: str = "member") -> TeamMember:
        member = TeamMember(team_id=team_id, owner_id=owner_id, role=role)
        self._session.add(member)
        await self._session.flush()
        return member

    async def get_member(self, team_id: uuid.UUID, owner_id: uuid.UUID) -> TeamMember | None:
        stmt = select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.owner_id == owner_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
