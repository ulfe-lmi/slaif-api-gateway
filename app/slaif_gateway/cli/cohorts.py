"""Typer commands for cohort records."""

from __future__ import annotations

import uuid
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_datetime,
    parse_uuid,
    run_async,
)
from slaif_gateway.db.models import Cohort
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.schemas.record_edits import (
    CohortUpdatePatch,
    parse_cohort_update_patch,
)
from slaif_gateway.services.cohort_service import CohortService

app = typer.Typer(help="Manage cohorts")


def _safe_cohort_dict(cohort: Cohort) -> dict[str, object]:
    return {
        "id": cohort.id,
        "name": cohort.name,
        "description": cohort.description,
        "starts_at": cohort.starts_at,
        "ends_at": cohort.ends_at,
        "created_at": cohort.created_at,
        "updated_at": cohort.updated_at,
    }


async def _create_cohort(
    *,
    name: str,
    institution_id: str | None,
    description: str | None,
    starts_at: str | None,
    ends_at: str | None,
) -> Cohort:
    parsed_starts_at = parse_datetime(starts_at, field_name="starts_at")
    parsed_ends_at = parse_datetime(ends_at, field_name="ends_at")
    if parsed_starts_at is not None and parsed_ends_at is not None and parsed_ends_at <= parsed_starts_at:
        raise ValueError("ends_at must be after starts_at")
    parsed_institution_id = (
        parse_uuid(institution_id, field_name="institution_id") if institution_id else None
    )
    async with cli_db_session() as (_, session):
        service = CohortService(
            cohorts_repository=CohortsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.create_cohort(
            name=name,
            institution_id=parsed_institution_id,
            description=description,
            starts_at=parsed_starts_at,
            ends_at=parsed_ends_at,
        )


async def _list_cohorts(*, institution_id: str | None, limit: int) -> list[Cohort]:
    parsed_institution_id = (
        parse_uuid(institution_id, field_name="institution_id") if institution_id else None
    )
    async with cli_db_session() as (_, session):
        service = CohortService(
            cohorts_repository=CohortsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.list_cohorts(institution_id=parsed_institution_id, limit=limit)


async def _show_cohort(cohort_id: str) -> Cohort:
    async with cli_db_session() as (_, session):
        service = CohortService(
            cohorts_repository=CohortsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.get_cohort(parse_uuid(cohort_id, field_name="cohort_id"))


async def _update_cohort(
    *,
    cohort_id: str,
    patch: CohortUpdatePatch,
    actor_admin_id: uuid.UUID | None,
    reason: str,
) -> Cohort:
    async with cli_db_session() as (_, session):
        service = CohortService(
            cohorts_repository=CohortsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.update_cohort_partial(
            cohort_id,
            patch=patch,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


@app.callback()
def cohorts() -> None:
    """Manage cohorts."""


@app.command("create")
def create(
    name: Annotated[str, typer.Option("--name", help="Cohort name")],
    institution_id: Annotated[
        str | None,
        typer.Option("--institution-id", help="Unsupported until cohorts link to institutions"),
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Cohort description")] = None,
    starts_at: Annotated[str | None, typer.Option("--starts-at", help="ISO start datetime")] = None,
    ends_at: Annotated[str | None, typer.Option("--ends-at", help="ISO end datetime")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create a cohort."""
    try:
        cohort = run_async(
            _create_cohort(
                name=name,
                institution_id=institution_id,
                description=description,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_cohort_dict(cohort)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("update")
def update(
    cohort_id: Annotated[str, typer.Argument(help="Cohort UUID")],
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason for this edit")],
    name: Annotated[str | None, typer.Option("--name", help="Replace the cohort name")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Replace the cohort description")] = None,
    clear_description: Annotated[bool, typer.Option("--clear-description", help="Clear the cohort description")] = False,
    starts_at: Annotated[str | None, typer.Option("--starts-at", help="Replace the ISO start datetime")] = None,
    clear_starts_at: Annotated[bool, typer.Option("--clear-starts-at", help="Clear the start datetime")] = False,
    ends_at: Annotated[str | None, typer.Option("--ends-at", help="Replace the ISO end datetime")] = None,
    clear_ends_at: Annotated[bool, typer.Option("--clear-ends-at", help="Clear the end datetime")] = False,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Recording admin UUID")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Update one cohort (omitted fields are preserved)."""
    try:
        patch, actor, cleaned_reason = parse_cohort_update_patch(
            name=name,
            description=description,
            clear_description=clear_description,
            starts_at=starts_at,
            clear_starts_at=clear_starts_at,
            ends_at=ends_at,
            clear_ends_at=clear_ends_at,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
        cohort = run_async(
            _update_cohort(
                cohort_id=cohort_id,
                patch=patch,
                actor_admin_id=actor,
                reason=cleaned_reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_cohort_dict(cohort)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_cohorts(
    institution_id: Annotated[
        str | None,
        typer.Option("--institution-id", help="Unsupported until cohorts link to institutions"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List cohorts."""
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")
    try:
        rows = run_async(_list_cohorts(institution_id=institution_id, limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_cohort_dict(row) for row in rows]
    if json_output:
        emit_json({"cohorts": payload})
        return
    if not payload:
        typer.echo("No cohorts found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    cohort_id: Annotated[str, typer.Argument(help="Cohort UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one cohort."""
    try:
        cohort = run_async(_show_cohort(cohort_id))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_cohort_dict(cohort)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)
