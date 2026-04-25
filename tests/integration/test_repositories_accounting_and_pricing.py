"""Optional accounting/provider-pricing repository smoke checks on migrated PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.fx_rates import FxRatesRepository


@pytest.mark.asyncio
async def test_fx_repository_smoke_on_existing_migrated_database(async_test_session: AsyncSession) -> None:
    repo = FxRatesRepository(async_test_session)
    rows = await repo.list_rates_for_pair(base_currency="USD", quote_currency="EUR", limit=1)

    if not rows:
        test_rate = await repo.create_fx_rate(
            base_currency="USD",
            quote_currency="EUR",
            rate=Decimal("0.900000000"),
            valid_from=datetime.now(UTC),
            source="integration-test",
        )
        await async_test_session.rollback()
        assert test_rate.rate == Decimal("0.900000000")
    else:
        assert rows[0].base_currency == "USD"
