"""Tests for organization repository and service."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import Base, Organization
from slaif_gateway.db.repositories.organizations import OrganizationsRepository


@pytest.fixture
async def db_session():
    engine = create_async_engine("postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        yield session
    await engine.dispose()


@pytest.mark.anyio
async def test_create_organization(db_session):
    repo = OrganizationsRepository(db_session)
    org = await repo.create(name="Test Org", slug="test-org")
    assert org.id is not None
    assert org.name == "Test Org"
    assert org.slug == "test-org"


@pytest.mark.anyio
async def test_get_by_slug(db_session):
    repo = OrganizationsRepository(db_session)
    await repo.create(name="Test Org", slug="test-org")
    found = await repo.get_by_slug("test-org")
    assert found is not None
    assert found.slug == "test-org"


@pytest.mark.anyio
async def test_get_by_slug_not_found(db_session):
    repo = OrganizationsRepository(db_session)
    found = await repo.get_by_slug("nonexistent")
    assert found is None
