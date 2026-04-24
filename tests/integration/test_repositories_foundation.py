"""Optional integration scaffolding for foundational repositories."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.repositories.institutions import InstitutionsRepository


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not configured; skipping optional integration repository checks",
)


@pytest.mark.asyncio
async def test_foundation_repository_smoke_integration() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            repository = InstitutionsRepository(session)
            rows = await repository.list_institutions(limit=1)
            assert isinstance(rows, list)
    finally:
        await engine.dispose()
