"""Typer commands for model route metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_uuid,
    require_positive_limit,
    run_async,
)
from slaif_gateway.db.models import ModelRoute
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.model_route_service import CHAT_COMPLETIONS_ENDPOINT, ModelRouteService
from slaif_gateway.services.route_import import (
    build_route_import_execution_plan,
    classify_route_import_preview,
    detect_route_import_format,
    execute_route_import_plan,
    parse_route_import_csv,
    parse_route_import_json,
    parse_route_import_tsv,
    provider_refs_from_rows,
    route_import_execution_result_to_dict,
    route_import_preview_to_dict,
    validate_route_import_rows,
)

app = typer.Typer(help="Manage model routes")


def _safe_route_dict(row: ModelRoute) -> dict[str, object]:
    return {
        "id": row.id,
        "requested_model": row.requested_model,
        "match_type": row.match_type,
        "endpoint": row.endpoint,
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "priority": row.priority,
        "enabled": row.enabled,
        "visible_in_models": row.visible_in_models,
        "supports_streaming": row.supports_streaming,
        "capabilities": row.capabilities,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _service(session) -> ModelRouteService:
    return ModelRouteService(
        model_routes_repository=ModelRoutesRepository(session),
        audit_repository=AuditRepository(session),
    )


async def _add_route(
    *,
    requested_model: str,
    match_type: str,
    provider: str,
    upstream_model: str | None,
    priority: int,
    visible_in_models: bool,
    enabled: bool,
    notes: str | None,
    endpoint: str,
) -> ModelRoute:
    async with cli_db_session() as (_, session):
        return await _service(session).create_model_route(
            requested_model=requested_model,
            match_type=match_type,
            provider=provider,
            upstream_model=upstream_model,
            priority=priority,
            visible_in_models=visible_in_models,
            enabled=enabled,
            notes=notes,
            endpoint=endpoint,
        )


async def _list_routes(
    *,
    provider: str | None,
    enabled_only: bool,
    visible_only: bool,
    limit: int,
) -> list[ModelRoute]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_model_routes(
            provider=provider,
            enabled_only=enabled_only,
            visible_only=visible_only,
            limit=limit,
        )


async def _show_route(route_id: str) -> ModelRoute:
    parsed_route_id = parse_uuid(route_id, field_name="route_id")
    async with cli_db_session() as (_, session):
        return await _service(session).get_model_route(parsed_route_id)


async def _set_route_enabled(route_id: str, *, enabled: bool) -> ModelRoute:
    parsed_route_id = parse_uuid(route_id, field_name="route_id")
    async with cli_db_session() as (_, session):
        return await _service(session).set_model_route_enabled(parsed_route_id, enabled=enabled)


async def _preview_route_import(
    *,
    rows: list[dict[str, object]],
) -> object:
    async with cli_db_session() as (_, session):
        providers = await ProviderConfigsRepository(session).list_provider_configs(limit=1000)
        preview = validate_route_import_rows(
            rows,
            provider_configs=provider_refs_from_rows(providers),
            max_rows=max(len(rows), 1),
        )
        valid_rows = [row for row in preview.rows if row.status == "valid"]
        if not valid_rows:
            return route_import_preview_to_dict(preview)

        route_repository = ModelRoutesRepository(session)
        existing_by_row: dict[int, list[object]] = {}
        for row in valid_rows:
            if not row.requested_model or not row.match_type or not row.endpoint:
                continue
            existing_by_row[row.row_number] = await route_repository.list_model_routes(
                endpoint=row.endpoint,
                limit=1000,
            )
        return classify_route_import_preview(preview, existing_routes_by_row=existing_by_row)


async def _execute_route_import(
    *,
    rows: list[dict[str, object]],
    actor_admin_id: str | None,
    reason: str,
) -> dict[str, object]:
    preview = await _preview_route_import(rows=rows)
    plan = build_route_import_execution_plan(preview)
    if not plan.executable:
        raise ValueError(
            "Route import execution is blocked; "
            f"{plan.blocked_count} of {plan.total_rows} rows are not executable. "
            "Run --dry-run to inspect invalid, duplicate, update, or conflict rows."
        )

    parsed_actor_id = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
    async with cli_db_session() as (_, session):
        result = await execute_route_import_plan(
            plan,
            model_route_service=_service(session),
            actor_admin_id=parsed_actor_id,
            reason=reason,
        )
    payload = route_import_execution_result_to_dict(result)
    payload.update(
        {
            "dry_run": False,
            "valid_count": preview.valid_count,
            "invalid_count": preview.invalid_count,
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
def routes() -> None:
    """Manage model routes."""


@app.command("add")
def add(
    requested_model: Annotated[
        str,
        typer.Option("--requested-model", "--pattern", help="Requested model or route pattern"),
    ],
    match_type: Annotated[str, typer.Option("--match-type", help="exact, prefix, or glob")],
    provider: Annotated[str, typer.Option("--provider", help="Provider name")],
    upstream_model: Annotated[str | None, typer.Option("--upstream-model", help="Provider model")] = None,
    priority: Annotated[int, typer.Option("--priority", help="Lower values win")] = 100,
    visible_in_models: Annotated[
        bool,
        typer.Option("--visible/--hidden", help="Expose through /v1/models"),
    ] = True,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled", help="Enable route")] = True,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="Endpoint path or chat.completions alias"),
    ] = CHAT_COMPLETIONS_ENDPOINT,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create a model route."""
    try:
        row = run_async(
            _add_route(
                requested_model=requested_model,
                match_type=match_type,
                provider=provider,
                upstream_model=upstream_model,
                priority=priority,
                visible_in_models=visible_in_models,
                enabled=enabled,
                notes=notes,
                endpoint=endpoint,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_routes(
    provider: Annotated[str | None, typer.Option("--provider", help="Provider filter")] = None,
    enabled_only: Annotated[bool, typer.Option("--enabled-only", help="Only enabled routes")] = False,
    visible_only: Annotated[bool, typer.Option("--visible-only", help="Only /v1/models visible routes")] = False,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List model routes."""
    require_positive_limit(limit)
    try:
        rows = run_async(
            _list_routes(
                provider=provider,
                enabled_only=enabled_only,
                visible_only=visible_only,
                limit=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_route_dict(row) for row in rows]
    if json_output:
        emit_json({"routes": payload})
        return
    if not payload:
        typer.echo("No routes found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one model route."""
    try:
        row = run_async(_show_route(route_id))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("enable")
def enable(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Enable a model route."""
    try:
        row = run_async(_set_route_enabled(route_id, enabled=True))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("disable")
def disable(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Disable a model route."""
    try:
        row = run_async(_set_route_enabled(route_id, enabled=False))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("import")
def import_routes(
    file: Annotated[Path, typer.Option("--file", help="Local JSON, CSV, or TSV route file")],
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
    """Preview or execute route imports from a local JSON, CSV, or TSV file."""
    try:
        mode = _resolve_import_mode(
            dry_run=dry_run,
            execute=execute,
            confirm_import=confirm_import,
            reason=reason,
        )
        rows = _load_import_file(file, input_format=input_format)
        if mode == "dry_run":
            preview = run_async(_preview_route_import(rows=rows))
            payload = route_import_preview_to_dict(preview)
            payload["dry_run"] = True
        else:
            payload = run_async(
                _execute_route_import(
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
            "total_rows": payload["total_rows"],
            "valid_count": payload["valid_count"],
            "invalid_count": payload["invalid_count"],
            "created_count": payload.get("created_count", 0),
            "updated_count": payload.get("updated_count", 0),
            "skipped_count": payload.get("skipped_count", 0),
            "error_count": payload.get("error_count", 0),
        }
    )


def _load_import_file(path: Path, *, input_format: str | None) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        raise ValueError("Route import file does not exist")
    text = path.read_text(encoding="utf-8")
    file_format = detect_route_import_format(
        filename=path.name,
        requested_format=(input_format or "auto"),
        text=text,
    )
    if file_format == "json":
        return parse_route_import_json(text)
    if file_format == "tsv":
        return parse_route_import_tsv(text)
    if file_format == "csv":
        return parse_route_import_csv(text)
    raise ValueError("Route import format must be auto, csv, json, or tsv")
