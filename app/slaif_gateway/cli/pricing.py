"""Typer commands for pricing rule metadata."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_datetime,
    parse_decimal,
    parse_uuid,
    require_positive_limit,
    run_async,
)
from slaif_gateway.db.models import PricingRule
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.services.pricing_rule_service import PricingImportResult, PricingRuleService

app = typer.Typer(help="Manage pricing rules")


def _safe_pricing_dict(row: PricingRule | dict[str, object]) -> dict[str, object]:
    if isinstance(row, dict):
        return dict(row)
    return {
        "id": row.id,
        "provider": row.provider,
        "model": row.upstream_model,
        "endpoint": row.endpoint,
        "currency": row.currency,
        "input_price_per_1m": row.input_price_per_1m,
        "cached_input_price_per_1m": row.cached_input_price_per_1m,
        "output_price_per_1m": row.output_price_per_1m,
        "reasoning_price_per_1m": row.reasoning_price_per_1m,
        "request_price": row.request_price,
        "pricing_metadata": row.pricing_metadata,
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "enabled": row.enabled,
        "source_url": row.source_url,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _service(session) -> PricingRuleService:
    return PricingRuleService(
        pricing_rules_repository=PricingRulesRepository(session),
        audit_repository=AuditRepository(session),
    )


async def _add_pricing_rule(
    *,
    provider: str,
    model: str,
    endpoint: str,
    currency: str,
    input_price_per_1m: str,
    output_price_per_1m: str,
    cached_input_price_per_1m: str | None,
    reasoning_price_per_1m: str | None,
    valid_from: str | None,
    valid_until: str | None,
    source_url: str | None,
    notes: str | None,
    enabled: bool,
) -> PricingRule:
    parsed_valid_from = parse_datetime(valid_from, field_name="valid_from") or datetime.now(UTC)
    parsed_valid_until = parse_datetime(valid_until, field_name="valid_until")
    input_price = parse_decimal(input_price_per_1m, field_name="input_price_per_1m")
    output_price = parse_decimal(output_price_per_1m, field_name="output_price_per_1m")
    cached_input_price = parse_decimal(
        cached_input_price_per_1m,
        field_name="cached_input_price_per_1m",
    )
    reasoning_price = parse_decimal(reasoning_price_per_1m, field_name="reasoning_price_per_1m")
    if input_price is None or output_price is None:
        raise typer.BadParameter("input and output prices are required")

    async with cli_db_session() as (_, session):
        return await _service(session).create_pricing_rule(
            provider=provider,
            model=model,
            endpoint=endpoint,
            currency=currency,
            input_price_per_1m=input_price,
            output_price_per_1m=output_price,
            cached_input_price_per_1m=cached_input_price,
            reasoning_price_per_1m=reasoning_price,
            valid_from=parsed_valid_from,
            valid_until=parsed_valid_until,
            source_url=source_url,
            notes=notes,
            enabled=enabled,
        )


async def _list_pricing_rules(
    *,
    provider: str | None,
    model: str | None,
    endpoint: str | None,
    enabled_only: bool,
    limit: int,
) -> list[PricingRule]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_pricing_rules(
            provider=provider,
            model=model,
            endpoint=endpoint,
            enabled_only=enabled_only,
            limit=limit,
        )


async def _show_pricing_rule(pricing_rule_id: str) -> PricingRule:
    parsed_id = parse_uuid(pricing_rule_id, field_name="pricing_rule_id")
    async with cli_db_session() as (_, session):
        return await _service(session).get_pricing_rule(parsed_id)


async def _disable_model(
    *,
    provider: str,
    model: str,
    endpoint: str | None,
) -> list[PricingRule]:
    async with cli_db_session() as (_, session):
        return await _service(session).disable_model(
            provider=provider,
            model=model,
            endpoint=endpoint,
        )


async def _import_pricing_rules(
    *,
    rows: list[dict[str, object]],
    dry_run: bool,
) -> PricingImportResult:
    if dry_run:
        service = PricingRuleService(
            pricing_rules_repository=object(),
            audit_repository=object(),
        )
        return await service.import_pricing_rules(rows, dry_run=True)
    async with cli_db_session() as (_, session):
        return await _service(session).import_pricing_rules(rows, dry_run=dry_run)


@app.callback()
def pricing() -> None:
    """Manage pricing rules."""


@app.command("add")
def add(
    provider: Annotated[str, typer.Option("--provider", help="Provider name")],
    model: Annotated[str, typer.Option("--model", help="Upstream model name")],
    input_price_per_1m: Annotated[
        str,
        typer.Option("--input-price-per-1m", help="Input-token price per 1M tokens"),
    ],
    output_price_per_1m: Annotated[
        str,
        typer.Option("--output-price-per-1m", help="Output-token price per 1M tokens"),
    ],
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="Endpoint path or chat.completions alias"),
    ] = "chat.completions",
    currency: Annotated[str, typer.Option("--currency", help="3-letter currency code")] = "EUR",
    cached_input_price_per_1m: Annotated[
        str | None,
        typer.Option("--cached-input-price-per-1m", help="Cached-input price per 1M tokens"),
    ] = None,
    reasoning_price_per_1m: Annotated[
        str | None,
        typer.Option("--reasoning-price-per-1m", help="Reasoning-token price per 1M tokens"),
    ] = None,
    valid_from: Annotated[str | None, typer.Option("--valid-from", help="ISO datetime")] = None,
    valid_until: Annotated[str | None, typer.Option("--valid-until", help="ISO datetime")] = None,
    source_url: Annotated[str | None, typer.Option("--source-url", help="Pricing source URL")] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled", help="Enable pricing rule")] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create a pricing rule."""
    try:
        row = run_async(
            _add_pricing_rule(
                provider=provider,
                model=model,
                endpoint=endpoint,
                currency=currency,
                input_price_per_1m=input_price_per_1m,
                output_price_per_1m=output_price_per_1m,
                cached_input_price_per_1m=cached_input_price_per_1m,
                reasoning_price_per_1m=reasoning_price_per_1m,
                valid_from=valid_from,
                valid_until=valid_until,
                source_url=source_url,
                notes=notes,
                enabled=enabled,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_pricing_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_pricing(
    provider: Annotated[str | None, typer.Option("--provider", help="Provider filter")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model filter")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Endpoint filter")] = None,
    enabled_only: Annotated[bool, typer.Option("--enabled-only", help="Only enabled rules")] = False,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List pricing rules."""
    require_positive_limit(limit)
    try:
        rows = run_async(
            _list_pricing_rules(
                provider=provider,
                model=model,
                endpoint=endpoint,
                enabled_only=enabled_only,
                limit=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_pricing_dict(row) for row in rows]
    if json_output:
        emit_json({"pricing_rules": payload})
        return
    if not payload:
        typer.echo("No pricing rules found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    pricing_rule_id: Annotated[str, typer.Argument(help="Pricing rule UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one pricing rule."""
    try:
        row = run_async(_show_pricing_rule(pricing_rule_id))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_pricing_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("disable-model")
def disable_model(
    provider: Annotated[str, typer.Option("--provider", help="Provider name")],
    model: Annotated[str, typer.Option("--model", help="Model name")],
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Endpoint filter")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Disable enabled pricing rules for one provider/model."""
    try:
        rows = run_async(_disable_model(provider=provider, model=model, endpoint=endpoint))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = {
        "disabled_count": len(rows),
        "pricing_rules": [_safe_pricing_dict(row) for row in rows],
    }
    if json_output:
        emit_json(payload)
        return
    echo_kv({"disabled_count": len(rows)})
    for row in payload["pricing_rules"]:
        typer.echo("")
        echo_kv(row)


@app.command("import")
def import_pricing(
    file: Annotated[Path, typer.Option("--file", help="Local JSON or CSV pricing file")],
    input_format: Annotated[
        str | None,
        typer.Option("--format", help="json or csv; auto-detected from file extension if omitted"),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate without writing rows")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Import pricing rules from a local JSON or CSV file."""
    try:
        rows = _load_import_file(file, input_format=input_format)
        result = run_async(_import_pricing_rules(rows=rows, dry_run=dry_run))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = {
        "dry_run": result.dry_run,
        "imported_count": result.imported_count,
        "validated_count": len(result.rows),
        "pricing_rules": [_safe_pricing_dict(row) for row in result.rows],
    }
    if json_output:
        emit_json(payload)
        return
    echo_kv(
        {
            "dry_run": result.dry_run,
            "imported_count": result.imported_count,
            "validated_count": len(result.rows),
        }
    )


def _load_import_file(path: Path, *, input_format: str | None) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        raise ValueError("Pricing import file does not exist")
    file_format = _detect_format(path, input_format)
    if file_format == "json":
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Pricing import file is not valid JSON") from exc
        if not isinstance(loaded, list):
            raise ValueError("Pricing JSON import must be a list of objects")
        if not all(isinstance(item, dict) for item in loaded):
            raise ValueError("Pricing JSON import must contain only objects")
        return loaded
    if file_format == "csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError("--format must be json or csv")


def _detect_format(path: Path, input_format: str | None) -> str:
    if input_format:
        normalized = input_format.strip().lower()
    else:
        normalized = path.suffix.lower().removeprefix(".")
    if normalized not in {"json", "csv"}:
        raise ValueError("--format must be json or csv")
    return normalized
