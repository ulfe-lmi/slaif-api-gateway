from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import fx as fx_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.fx_rate_service import FxRateService
from slaif_gateway.services.record_errors import RecordNotFoundError

runner = CliRunner()
FX_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


@dataclass
class FakeFxRate:
    id: uuid.UUID = FX_ID
    base_currency: str = "USD"
    quote_currency: str = "EUR"
    rate: Decimal = Decimal("0.920000000")
    valid_from: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    valid_until: datetime | None = None
    source: str | None = "manual"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


def test_fx_help_registers_commands() -> None:
    result = runner.invoke(app, ["fx", "--help"])

    assert result.exit_code == 0
    for command in ("add", "list", "latest"):
        assert command in result.stdout


def test_fx_add_parses_decimal_rate(monkeypatch) -> None:
    seen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_session():
        yield None, object()

    class FakeService:
        async def create_fx_rate(self, **kwargs: object) -> FakeFxRate:
            seen.update(kwargs)
            return FakeFxRate(rate=kwargs["rate"])

    monkeypatch.setattr(fx_cli, "cli_db_session", fake_session)
    monkeypatch.setattr(fx_cli, "_service", lambda session: FakeService())

    row = fx_cli.run_async(
        fx_cli._add_fx_rate(
            base_currency="USD",
            quote_currency="EUR",
            rate="0.920000000",
            valid_from="2026-01-01T00:00:00Z",
            valid_until=None,
            source="manual",
        )
    )

    assert row.rate == Decimal("0.920000000")
    assert seen["rate"] == Decimal("0.920000000")


@pytest.mark.parametrize("rate", [Decimal("0"), Decimal("-0.1")])
def test_fx_add_zero_or_negative_rate_fails(rate: Decimal) -> None:
    service = FxRateService(fx_rates_repository=object(), audit_repository=object())

    async def run_invalid() -> None:
        await service.create_fx_rate(
            base_currency="USD",
            quote_currency="EUR",
            rate=rate,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=None,
            source=None,
        )

    with pytest.raises(ValueError, match="positive"):
        fx_cli.run_async(run_invalid())


def test_fx_list_latest_and_decimal_json(monkeypatch) -> None:
    async def fake_list_fx_rates(
        *,
        base_currency: str | None,
        quote_currency: str | None,
        limit: int,
    ) -> list[FakeFxRate]:
        assert base_currency == "USD"
        assert quote_currency == "EUR"
        assert limit == 5
        return [FakeFxRate()]

    async def fake_latest_fx_rate(*, base_currency: str, quote_currency: str) -> FakeFxRate:
        assert base_currency == "USD"
        assert quote_currency == "EUR"
        return FakeFxRate()

    monkeypatch.setattr(fx_cli, "_list_fx_rates", fake_list_fx_rates)
    monkeypatch.setattr(fx_cli, "_latest_fx_rate", fake_latest_fx_rate)

    list_result = runner.invoke(
        app,
        ["fx", "list", "--base-currency", "USD", "--quote-currency", "EUR", "--limit", "5", "--json"],
    )
    latest_result = runner.invoke(
        app,
        ["fx", "latest", "--base-currency", "USD", "--quote-currency", "EUR", "--json"],
    )

    assert list_result.exit_code == 0
    assert latest_result.exit_code == 0
    assert json.loads(list_result.stdout)["fx_rates"][0]["rate"] == "0.920000000"
    assert json.loads(latest_result.stdout)["rate"] == "0.920000000"


def test_fx_latest_fails_cleanly_when_missing(monkeypatch) -> None:
    async def fake_latest_fx_rate(*, base_currency: str, quote_currency: str) -> FakeFxRate:
        raise RecordNotFoundError("FX rate")

    monkeypatch.setattr(fx_cli, "_latest_fx_rate", fake_latest_fx_rate)

    result = runner.invoke(app, ["fx", "latest", "--base-currency", "USD"])

    assert result.exit_code != 0
    assert "FX rate not found" in result.stderr
    assert "Traceback" not in result.output
