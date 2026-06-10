"""Typer commands for pricing rule metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    CliDatabaseConfigError,
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
from slaif_gateway.services.pricing_import import (
    build_pricing_import_execution_plan,
    classify_pricing_import_preview,
    detect_pricing_import_format,
    execute_pricing_import_plan,
    parse_pricing_import_csv,
    parse_pricing_import_json,
    parse_pricing_import_tsv,
    pricing_import_execution_result_to_dict,
    pricing_import_preview_to_dict,
    validate_pricing_import_rows,
)
from slaif_gateway.services.pricing_rule_service import PricingRuleService

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


async def _classify_pricing_import(
    *,
    rows: list[dict[str, object]],
) -> object:
    preview = validate_pricing_import_rows(rows, max_rows=max(len(rows), 1))
    if preview.valid_count == 0:
        return preview

    try:
        async with cli_db_session() as (_, session):
            repository = PricingRulesRepository(session)
            existing_by_row: dict[int, list[object]] = {}
            for row in preview.rows:
                if row.status != "valid" or not row.provider or not row.model or not row.endpoint:
                    continue
                existing_by_row[row.row_number] = await repository.list_pricing_rules_for_provider_model(
                    provider=row.provider,
                    upstream_model=row.model,
                    endpoint=row.endpoint,
                )
    except CliDatabaseConfigError:
        return preview

    return classify_pricing_import_preview(preview, existing_rules_by_row=existing_by_row)


async def _preview_pricing_import(
    *,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    preview = await _classify_pricing_import(rows=rows)
    return pricing_import_preview_to_dict(preview)


async def _execute_pricing_import(
    *,
    rows: list[dict[str, object]],
    actor_admin_id: str | None,
    reason: str,
) -> dict[str, object]:
    preview = await _classify_pricing_import(rows=rows)
    plan = build_pricing_import_execution_plan(preview)
    if not plan.executable:
        raise ValueError(
            "Pricing import execution is blocked; "
            f"{plan.blocked_count} of {plan.total_rows} rows are not executable. "
            "Run --dry-run to inspect invalid, duplicate, or overlapping rows."
        )

    parsed_actor_id = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
    async with cli_db_session() as (_, session):
        result = await execute_pricing_import_plan(
            plan,
            pricing_rule_service=_service(session),
            actor_admin_id=parsed_actor_id,
            reason=reason,
        )
    payload = pricing_import_execution_result_to_dict(result)
    payload.update(
        {
            "dry_run": False,
            "validated_count": preview.valid_count,
            "invalid_count": preview.invalid_count,
            "imported_count": result.created_count + result.updated_count,
        }
    )
    return payload


def _resolve_import_mode(
    *,
    dry_run: bool,
    execute: bool,
    confirm_import: bool,
    reason: str | None,
) -> str:
    if dry_run and execute:
        raise ValueError("Pass either --dry-run or --execute, not both.")
    if confirm_import and not execute:
        raise ValueError("--confirm-import requires --execute.")
    if execute and not confirm_import:
        raise ValueError("--execute requires --confirm-import.")
    if execute and not (reason or "").strip():
        raise ValueError("--reason is required with --execute.")
    if not dry_run and not execute:
        raise ValueError(
            "Pass --dry-run for preview or --execute --confirm-import --reason to write rows."
        )
    return "execute" if execute else "dry_run"


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
    file: Annotated[Path, typer.Option("--file", help="Local JSON, CSV, or TSV pricing file")],
    input_format: Annotated[
        str | None,
        typer.Option("--format", help="json, csv, or tsv; auto-detected from file extension if omitted"),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate without writing rows")] = False,
    execute: Annotated[bool, typer.Option("--execute", help="Write validated rows")] = False,
    confirm_import: Annotated[
        bool,
        typer.Option("--confirm-import", help="Acknowledge that confirmed import will write rows"),
    ] = False,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason for confirmed import")] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Admin actor UUID for audit"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Preview or execute pricing imports from a local JSON, CSV, or TSV file."""
    try:
        mode = _resolve_import_mode(
            dry_run=dry_run,
            execute=execute,
            confirm_import=confirm_import,
            reason=reason,
        )
        rows = _load_import_file(file, input_format=input_format)
        if mode == "dry_run":
            payload = run_async(_preview_pricing_import(rows=rows))
            payload.update(
                {
                    "dry_run": True,
                    "imported_count": 0,
                    "created_count": 0,
                    "updated_count": 0,
                    "skipped_count": 0,
                    "error_count": 0,
                    "validated_count": payload.get("valid_count", 0),
                }
            )
        else:
            payload = run_async(
                _execute_pricing_import(
                    rows=rows,
                    actor_admin_id=actor_admin_id,
                    reason=reason or "",
                )
            )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(payload)
        return
    echo_kv(
        {
            "dry_run": payload["dry_run"],
            "validated_count": payload.get("validated_count", 0),
            "invalid_count": payload.get("invalid_count", 0),
            "imported_count": payload.get("imported_count", 0),
            "created_count": payload.get("created_count", 0),
            "updated_count": payload.get("updated_count", 0),
            "skipped_count": payload.get("skipped_count", 0),
            "error_count": payload.get("error_count", 0),
        }
    )


def _load_import_file(path: Path, *, input_format: str | None) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        raise ValueError("Pricing import file does not exist")
    text = path.read_text(encoding="utf-8")
    file_format = detect_pricing_import_format(
        filename=path.name,
        requested_format=(input_format or "auto"),
        text=text,
    )
    if file_format == "json":
        return parse_pricing_import_json(text)
    if file_format == "csv":
        return parse_pricing_import_csv(text)
    if file_format == "tsv":
        return parse_pricing_import_tsv(text)
    raise ValueError("Pricing import format must be auto, csv, json, or tsv")
