"""Repository for project records."""

from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import Project


class ProjectsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        return await self._session.get(Project, project_id)

    async def get_by_slug(self, team_id: uuid.UUID, slug: str) -> Project | None:
        stmt = select(Project).where(Project.team_id == team_id, Project.slug == slug)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_team(self, team_id: uuid.UUID) -> list[Project]:
        stmt = select(Project).where(Project.team_id == team_id).order_by(Project.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(
        self,
        *,
        team_id: uuid.UUID,
        name: str,
        slug: str,
        description: str | None = None,
        starts_at=None,
        ends_at=None,
    ) -> Project:
        project = Project(team_id=team_id, name=name, slug=slug, description=description, starts_at=starts_at, ends_at=ends_at)
        self._session.add(project)
        await self._session.flush()
        return project
