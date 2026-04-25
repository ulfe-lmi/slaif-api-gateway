"""Optional foundational repository smoke checks on migrated PostgreSQL."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.institutions import InstitutionsRepository


@pytest.mark.asyncio
async def test_foundation_repository_smoke_integration(async_test_session: AsyncSession) -> None:
    repository = InstitutionsRepository(async_test_session)
    rows = await repository.list_institutions(limit=1)
    assert isinstance(rows, list)
