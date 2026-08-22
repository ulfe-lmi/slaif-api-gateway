"""Tests for cross-team authorization rules."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import Base, Organization, Owner
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
async def setup(db_session):
    org_repo = OrganizationsRepository(db_session)
    org = await org_repo.create(name="Test Org", slug="test-org")
    team_repo = TeamsRepository(db_session)
    team_a = await team_repo.create(organization_id=org.id, name="Team A", slug="team-a")
    team_b = await team_repo.create(organization_id=org.id, name="Team B", slug="team-b")
    owner = Owner(name="Test", surname="User", email="test@example.org", is_active=True)
    db_session.add(owner)
    await db_session.flush()
    return team_a, team_b, owner


@pytest.mark.anyio
async def test_member_of_one_team_not_auto_member_of_another(db_session, setup):
    team_a, team_b, owner = setup
    team_repo = TeamsRepository(db_session)
    await team_repo.add_member(team_id=team_a.id, owner_id=owner.id)
    member_b = await team_repo.get_member(team_id=team_b.id, owner_id=owner.id)
    assert member_b is None


@pytest.mark.anyio
async def test_add_member_to_team(db_session, setup):
    team_a, _, owner = setup
    team_repo = TeamsRepository(db_session)
    member = await team_repo.add_member(team_id=team_a.id, owner_id=owner.id, role="lead")
    assert member.role == "lead"
