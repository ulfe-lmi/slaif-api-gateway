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
    classify_route_import_preview,
    detect_route_import_format,
    parse_route_import_csv,
    parse_route_import_json,
    parse_route_import_tsv,
    provider_refs_from_rows,
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
) -> dict[str, object]:
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
        classified = classify_route_import_preview(preview, existing_routes_by_row=existing_by_row)
        return route_import_preview_to_dict(classified)


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
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Preview route imports from a local JSON, CSV, or TSV file."""
    try:
        if not dry_run:
            raise ValueError("Route CLI import is preview-only; pass --dry-run.")
        rows = _load_import_file(file, input_format=input_format)
        payload = run_async(_preview_route_import(rows=rows))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    wrapped = {
        "dry_run": True,
        "total_rows": payload["total_rows"],
        "valid_count": payload["valid_count"],
        "invalid_count": payload["invalid_count"],
        "rows": payload["rows"],
    }
    if json_output:
        emit_json(wrapped)
        return
    echo_kv(
        {
            "dry_run": True,
            "total_rows": payload["total_rows"],
            "valid_count": payload["valid_count"],
            "invalid_count": payload["invalid_count"],
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
