"""Typer commands for institution records."""

from __future__ import annotations

from typing import Annotated

import typer

from slaif_gateway.cli.common import cli_db_session, echo_kv, emit_json, handle_cli_error, run_async
from slaif_gateway.db.models import Institution
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.services.institution_service import InstitutionService

app = typer.Typer(help="Manage institutions")


def _safe_institution_dict(institution: Institution) -> dict[str, object]:
    return {
        "id": institution.id,
        "name": institution.name,
        "country": institution.country,
        "notes": institution.notes,
        "created_at": institution.created_at,
        "updated_at": institution.updated_at,
    }


async def _create_institution(
    *,
    name: str,
    country: str | None,
    notes: str | None,
) -> Institution:
    async with cli_db_session() as (_, session):
        service = InstitutionService(
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.create_institution(name=name, country=country, notes=notes)


async def _list_institutions(*, limit: int) -> list[Institution]:
    async with cli_db_session() as (_, session):
        service = InstitutionService(
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.list_institutions(limit=limit)


async def _show_institution(institution_id_or_name: str) -> Institution:
    async with cli_db_session() as (_, session):
        service = InstitutionService(
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.get_institution(institution_id_or_name)


@app.callback()
def institutions() -> None:
    """Manage institutions."""


@app.command("create")
def create(
    name: Annotated[str, typer.Option("--name", help="Institution name")],
    country: Annotated[str | None, typer.Option("--country", help="Country code or name")] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create an institution."""
    try:
        institution = run_async(_create_institution(name=name, country=country, notes=notes))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_institution_dict(institution)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_institutions(
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List institutions."""
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")
    try:
        rows = run_async(_list_institutions(limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_institution_dict(row) for row in rows]
    if json_output:
        emit_json({"institutions": payload})
        return
    if not payload:
        typer.echo("No institutions found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    institution_id_or_name: Annotated[str, typer.Argument(help="Institution UUID or name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one institution."""
    try:
        institution = run_async(_show_institution(institution_id_or_name))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_institution_dict(institution)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)
