"""Typer commands for key owner records."""

from __future__ import annotations

import uuid
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_uuid,
    run_async,
)
from slaif_gateway.db.models import Owner
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.schemas.record_edits import (
    OwnerUpdatePatch,
    parse_owner_update_patch,
)
from slaif_gateway.services.owner_service import OwnerService

app = typer.Typer(help="Manage key owners")


def _safe_owner_dict(owner: Owner) -> dict[str, object]:
    return {
        "id": owner.id,
        "name": owner.name,
        "surname": owner.surname,
        "email": owner.email,
        "institution_id": owner.institution_id,
        "notes": owner.notes,
        "is_active": owner.is_active,
        "created_at": owner.created_at,
        "updated_at": owner.updated_at,
    }


async def _create_owner(
    *,
    name: str,
    surname: str,
    email: str,
    institution_id: str | None,
    notes: str | None,
) -> Owner:
    parsed_institution_id = (
        parse_uuid(institution_id, field_name="institution_id") if institution_id else None
    )
    async with cli_db_session() as (_, session):
        service = OwnerService(
            owners_repository=OwnersRepository(session),
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.create_owner(
            name=name,
            surname=surname,
            email=email,
            institution_id=parsed_institution_id,
            notes=notes,
        )


async def _list_owners(
    *,
    institution_id: str | None,
    email: str | None,
    limit: int,
) -> list[Owner]:
    parsed_institution_id = (
        parse_uuid(institution_id, field_name="institution_id") if institution_id else None
    )
    async with cli_db_session() as (_, session):
        service = OwnerService(
            owners_repository=OwnersRepository(session),
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.list_owners(
            institution_id=parsed_institution_id,
            email=email,
            limit=limit,
        )


async def _show_owner(owner_id_or_email: str) -> Owner:
    async with cli_db_session() as (_, session):
        service = OwnerService(
            owners_repository=OwnersRepository(session),
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.get_owner(owner_id_or_email)


async def _update_owner(
    *,
    owner_id: str,
    patch: OwnerUpdatePatch,
    actor_admin_id: uuid.UUID | None,
    reason: str,
) -> Owner:
    async with cli_db_session() as (_, session):
        service = OwnerService(
            owners_repository=OwnersRepository(session),
            institutions_repository=InstitutionsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.update_owner_partial(
            owner_id,
            patch=patch,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


@app.callback()
def owners() -> None:
    """Manage key owners."""


@app.command("create")
def create(
    name: Annotated[str, typer.Option("--name", help="Owner first name")],
    surname: Annotated[str, typer.Option("--surname", help="Owner surname")],
    email: Annotated[str, typer.Option("--email", help="Owner email")],
    institution_id: Annotated[str | None, typer.Option("--institution-id", help="Institution UUID")] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create a key owner."""
    try:
        owner = run_async(
            _create_owner(
                name=name,
                surname=surname,
                email=email,
                institution_id=institution_id,
                notes=notes,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_owner_dict(owner)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("update")
def update(
    owner_id: Annotated[str, typer.Argument(help="Owner UUID")],
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason for this edit")],
    name: Annotated[str | None, typer.Option("--name", help="Replace the owner first name")] = None,
    surname: Annotated[str | None, typer.Option("--surname", help="Replace the owner surname")] = None,
    email: Annotated[str | None, typer.Option("--email", help="Replace the owner email")] = None,
    institution_id: Annotated[str | None, typer.Option("--institution-id", help="Replace the institution UUID")] = None,
    clear_institution: Annotated[bool, typer.Option("--clear-institution", help="Clear the institution link")] = False,
    external_id: Annotated[str | None, typer.Option("--external-id", help="Replace the external ID")] = None,
    clear_external_id: Annotated[bool, typer.Option("--clear-external-id", help="Clear the external ID")] = False,
    notes: Annotated[str | None, typer.Option("--notes", help="Replace the administrative notes")] = None,
    clear_notes: Annotated[bool, typer.Option("--clear-notes", help="Clear the administrative notes")] = False,
    active: Annotated[bool, typer.Option("--active", help="Set active (omit to preserve current state)")] = False,
    inactive: Annotated[bool, typer.Option("--inactive", help="Set inactive (omit to preserve current state)")] = False,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Recording admin UUID")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Update one key owner (omitted fields are preserved)."""
    try:
        patch, actor, cleaned_reason = parse_owner_update_patch(
            name=name,
            surname=surname,
            email=email,
            institution_id=institution_id,
            clear_institution=clear_institution,
            external_id=external_id,
            clear_external_id=clear_external_id,
            notes=notes,
            clear_notes=clear_notes,
            active=active,
            inactive=inactive,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
        owner = run_async(
            _update_owner(
                owner_id=owner_id,
                patch=patch,
                actor_admin_id=actor,
                reason=cleaned_reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_owner_dict(owner)
    payload["external_id"] = owner.external_id
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_owners(
    institution_id: Annotated[str | None, typer.Option("--institution-id", help="Institution UUID")] = None,
    email: Annotated[str | None, typer.Option("--email", help="Owner email")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List key owners."""
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")
    try:
        rows = run_async(_list_owners(institution_id=institution_id, email=email, limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_owner_dict(row) for row in rows]
    if json_output:
        emit_json({"owners": payload})
        return
    if not payload:
        typer.echo("No owners found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    owner_id_or_email: Annotated[str, typer.Argument(help="Owner UUID or email")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one key owner."""
    try:
        owner = run_async(_show_owner(owner_id_or_email))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_owner_dict(owner)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)
