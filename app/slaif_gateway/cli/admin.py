"""Typer commands for admin user bootstrap."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from slaif_gateway.cli.common import cli_db_session, echo_kv, emit_json, handle_cli_error, run_async
from slaif_gateway.db.models import AdminUser
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.services.admin_service import AdminService
from slaif_gateway.utils.passwords import hash_admin_password

app = typer.Typer(help="Manage admin users")


def _safe_admin_dict(admin_user: AdminUser) -> dict[str, object]:
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "display_name": admin_user.display_name,
        "is_active": admin_user.is_active,
        "is_superadmin": admin_user.role == "superadmin",
        "role": admin_user.role,
        "created_at": admin_user.created_at,
        "last_login_at": admin_user.last_login_at,
    }


async def _create_admin(
    *,
    email: str,
    display_name: str,
    password_hash: str,
    is_superadmin: bool,
) -> AdminUser:
    async with cli_db_session() as (_, session):
        service = AdminService(
            admin_users_repository=AdminUsersRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.create_admin_user(
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            is_superadmin=is_superadmin,
        )


async def _reset_password(admin_user_id_or_email: str, password_hash: str) -> AdminUser:
    async with cli_db_session() as (_, session):
        service = AdminService(
            admin_users_repository=AdminUsersRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.reset_admin_password(
            admin_user_id_or_email=admin_user_id_or_email,
            password_hash=password_hash,
        )


async def _list_admins(*, limit: int) -> list[AdminUser]:
    async with cli_db_session() as (_, session):
        service = AdminService(
            admin_users_repository=AdminUsersRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await service.list_admin_users(limit=limit)


def _read_password(*, password: str | None, password_stdin: bool) -> str:
    if password is not None and password_stdin:
        raise typer.BadParameter("Use either --password or --password-stdin, not both")
    if password_stdin:
        return sys.stdin.read().rstrip("\n")
    if password is not None:
        return password
    return typer.prompt("Password", hide_input=True, confirmation_prompt=True)


@app.callback()
def admin() -> None:
    """Manage admin users."""


@app.command("create")
def create(
    email: Annotated[str, typer.Option("--email", help="Admin email")],
    display_name: Annotated[str, typer.Option("--display-name", help="Admin display name")],
    password: Annotated[
        str | None,
        typer.Option("--password", help="Admin password; prefer prompt or --password-stdin"),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read password from stdin"),
    ] = False,
    superadmin: Annotated[
        bool,
        typer.Option("--superadmin/--no-superadmin", help="Create as superadmin"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create an admin user."""
    try:
        hashed_password = hash_admin_password(
            _read_password(password=password, password_stdin=password_stdin)
        )
        admin_user = run_async(
            _create_admin(
                email=email,
                display_name=display_name,
                password_hash=hashed_password,
                is_superadmin=superadmin,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_admin_dict(admin_user)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("reset-password")
def reset_password(
    admin_user_id_or_email: Annotated[str, typer.Argument(help="Admin user UUID or email")],
    password: Annotated[
        str | None,
        typer.Option("--password", help="New admin password; prefer prompt or --password-stdin"),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read password from stdin"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Reset an admin user's password."""
    try:
        hashed_password = hash_admin_password(
            _read_password(password=password, password_stdin=password_stdin)
        )
        admin_user = run_async(_reset_password(admin_user_id_or_email, hashed_password))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = {
        "id": admin_user.id,
        "email": admin_user.email,
        "password_changed": True,
        "updated_at": admin_user.updated_at,
    }
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_admins(
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List admin users using safe metadata only."""
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")
    try:
        rows = run_async(_list_admins(limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_admin_dict(row) for row in rows]
    if json_output:
        emit_json({"admin_users": payload})
        return
    if not payload:
        typer.echo("No admin users found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)
