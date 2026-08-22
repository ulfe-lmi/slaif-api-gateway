"""Tests for project repository."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import Base, Organization
from slaif_gateway.db.repositories.organizations import OrganizationsRepository
from slaif_gateway.db.repositories.teams import TeamsRepository
from slaif_gateway.db.repositories.projects import ProjectsRepository


@pytest.fixture
async def db_session():
    engine = create_async_engine("postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def team_id(db_session):
    org_repo = OrganizationsRepository(db_session)
    org = await org_repo.create(name="Test Org", slug="test-org")
    team_repo = TeamsRepository(db_session)
    team = await team_repo.create(organization_id=org.id, name="Eng", slug="eng")
    return team.id


@pytest.mark.anyio
async def test_create_project(db_session, team_id):
    repo = ProjectsRepository(db_session)
    project = await repo.create(team_id=team_id, name="Gateway", slug="gateway")
    assert project.id is not None
    assert project.team_id == team_id


@pytest.mark.anyio
async def test_list_by_team(db_session, team_id):
    repo = ProjectsRepository(db_session)
    await repo.create(team_id=team_id, name="Gateway", slug="gateway")
    await repo.create(team_id=team_id, name="Portal", slug="portal")
    projects = await repo.list_by_team(team_id)
    assert len(projects) == 2
