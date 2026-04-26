"""Typer commands for FX rate metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_datetime,
    parse_decimal,
    require_positive_limit,
    run_async,
)
from slaif_gateway.db.models import FxRate
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.services.fx_rate_service import FxRateService

app = typer.Typer(help="Manage FX rates")


def _safe_fx_dict(row: FxRate) -> dict[str, object]:
    return {
        "id": row.id,
        "base_currency": row.base_currency,
        "quote_currency": row.quote_currency,
        "rate": row.rate,
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "source": row.source,
        "created_at": row.created_at,
    }


def _service(session) -> FxRateService:
    return FxRateService(
        fx_rates_repository=FxRatesRepository(session),
        audit_repository=AuditRepository(session),
    )


async def _add_fx_rate(
    *,
    base_currency: str,
    quote_currency: str,
    rate: str,
    valid_from: str | None,
    valid_until: str | None,
    source: str | None,
) -> FxRate:
    parsed_rate = parse_decimal(rate, field_name="rate")
    if parsed_rate is None:
        raise typer.BadParameter("rate is required")
    parsed_valid_from = parse_datetime(valid_from, field_name="valid_from") or datetime.now(UTC)
    parsed_valid_until = parse_datetime(valid_until, field_name="valid_until")
    async with cli_db_session() as (_, session):
        return await _service(session).create_fx_rate(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=parsed_rate,
            valid_from=parsed_valid_from,
            valid_until=parsed_valid_until,
            source=source,
        )


async def _list_fx_rates(
    *,
    base_currency: str | None,
    quote_currency: str | None,
    limit: int,
) -> list[FxRate]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_fx_rates(
            base_currency=base_currency,
            quote_currency=quote_currency,
            limit=limit,
        )


async def _latest_fx_rate(*, base_currency: str, quote_currency: str) -> FxRate:
    async with cli_db_session() as (_, session):
        return await _service(session).latest_fx_rate(
            base_currency=base_currency,
            quote_currency=quote_currency,
        )


@app.callback()
def fx() -> None:
    """Manage FX rates."""


@app.command("add")
def add(
    base_currency: Annotated[str, typer.Option("--base-currency", help="Base currency, e.g. USD")],
    rate: Annotated[str, typer.Option("--rate", help="Conversion rate as a decimal string")],
    quote_currency: Annotated[str, typer.Option("--quote-currency", help="Quote currency")] = "EUR",
    source: Annotated[str | None, typer.Option("--source", help="Manual source note")] = None,
    valid_from: Annotated[str | None, typer.Option("--valid-from", help="ISO datetime")] = None,
    valid_until: Annotated[str | None, typer.Option("--valid-until", help="ISO datetime")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create an FX rate row."""
    try:
        row = run_async(
            _add_fx_rate(
                base_currency=base_currency,
                quote_currency=quote_currency,
                rate=rate,
                valid_from=valid_from,
                valid_until=valid_until,
                source=source,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_fx_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_fx(
    base_currency: Annotated[str | None, typer.Option("--base-currency", help="Base currency filter")] = None,
    quote_currency: Annotated[str | None, typer.Option("--quote-currency", help="Quote currency filter")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List FX rates."""
    require_positive_limit(limit)
    try:
        rows = run_async(
            _list_fx_rates(
                base_currency=base_currency,
                quote_currency=quote_currency,
                limit=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = [_safe_fx_dict(row) for row in rows]
    if json_output:
        emit_json({"fx_rates": payload})
        return
    if not payload:
        typer.echo("No FX rates found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("latest")
def latest(
    base_currency: Annotated[str, typer.Option("--base-currency", help="Base currency")],
    quote_currency: Annotated[str, typer.Option("--quote-currency", help="Quote currency")] = "EUR",
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show the latest active FX rate for a pair."""
    try:
        row = run_async(_latest_fx_rate(base_currency=base_currency, quote_currency=quote_currency))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_fx_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)
