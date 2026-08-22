"""Tests for team repository."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import Base, Organization
from slaif_gateway.db.repositories.organizations import OrganizationsRepository
from slaif_gateway.db.repositories.teams import TeamsRepository


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
async def org_id(db_session):
    repo = OrganizationsRepository(db_session)
    org = await repo.create(name="Test Org", slug="test-org")
    return org.id


@pytest.mark.anyio
async def test_create_team(db_session, org_id):
    repo = TeamsRepository(db_session)
    team = await repo.create(organization_id=org_id, name="Engineering", slug="engineering")
    assert team.id is not None
    assert team.organization_id == org_id


@pytest.mark.anyio
async def test_list_by_organization(db_session, org_id):
    repo = TeamsRepository(db_session)
    await repo.create(organization_id=org_id, name="Engineering", slug="engineering")
    await repo.create(organization_id=org_id, name="Product", slug="product")
    teams = await repo.list_by_organization(org_id)
    assert len(teams) == 2
