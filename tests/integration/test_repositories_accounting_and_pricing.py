"""Optional integration smoke checks for accounting/provider-pricing repositories."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.repositories.fx_rates import FxRatesRepository


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is not set; skipping optional integration repository checks.",
)


@pytest.mark.asyncio
async def test_fx_repository_smoke_on_existing_migrated_database() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = FxRatesRepository(session)
        rows = await repo.list_rates_for_pair(base_currency="USD", quote_currency="EUR", limit=1)

        if not rows:
            test_rate = await repo.create_fx_rate(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.900000000"),
                valid_from=datetime.now(UTC),
                source="integration-test",
            )
            await session.rollback()
            assert test_rate.rate == Decimal("0.900000000")
        else:
            assert rows[0].base_currency == "USD"

    await engine.dispose()
