"""Typer commands for demo fake-admin account control (objective 220 foundation).

The ``demo-admin`` group is the ONLY writable path for the ``demo_control``
fake-admin tables. Law:
- passwords come from a hidden confirmation prompt or ``--password-stdin``
  (there is deliberately NO ``--password`` argv option, so credentials
  never appear in argv/process listings);
- bounded, fixed safe errors for every failure class (DB, duplicate,
  invalid parameters); no raw DB URL, password, hash, or user-supplied
  secret is ever emitted to stdout/stderr/JSON;
- each command runs in ONE owned PostgreSQL transaction (account state +
  one safe append-only event commit or roll back together);
- list output reveals only safe username, UUID, enabled state, time, and
  account generation.

No HTTP route exposes this surface; a demo login application is a later
objective.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    CliDatabaseConfigError,
    CliError,
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_int_option,
    run_async,
)
from slaif_gateway.services.fake_admin_accounts import (
    PASSWORD_MAX_LENGTH,
    FakeAdminAccountError,
    FakeAdminAccountService,
)

app = typer.Typer(help="Control demo fake-admin accounts (demo_control schema)")

_LIST_LIMIT_MIN = 1
_LIST_LIMIT_MAX = 100
_LIST_LIMIT_DEFAULT = 50
_LIST_OFFSET_MIN = 0
_LIST_OFFSET_MAX = 1_000_000


def _bounded_limit(value: str, *, field_name: str = "--limit") -> int:
    limit = parse_int_option(value, field_name=field_name)
    if limit is None or not (_LIST_LIMIT_MIN <= limit <= _LIST_LIMIT_MAX):
        raise typer.BadParameter(
            f"{field_name} must be a whole number between {_LIST_LIMIT_MIN} and {_LIST_LIMIT_MAX}"
        )
    return limit


def _bounded_offset(value: str, *, field_name: str = "--offset") -> int:
    offset = parse_int_option(value, field_name=field_name)
    if offset is None or not (_LIST_OFFSET_MIN <= offset <= _LIST_OFFSET_MAX):
        raise typer.BadParameter(
            f"{field_name} must be a whole number between {_LIST_OFFSET_MIN} and {_LIST_OFFSET_MAX}"
        )
    return offset


def _read_password_from_stdin() -> str:
    """Read exactly ONE bounded password line from stdin (never echoed).

    Accepts at most PASSWORD_MAX_LENGTH (128) Unicode characters followed
    by at most one trailing newline. Any extra line, trailing data, or
    lone carriage return that survives the transport is refused with ONE
    fixed no-echo error BEFORE any validation, hashing, or database
    access; consumption stops at the bound instead of reading unbounded
    input.

    Transport note: Python text-mode stdin applies universal-newline
    translation on ordinary transports (pipes, redirected files), so a
    single-line CRLF input normally arrives as one LF-terminated line and
    is accepted like any other single line. A ``\r`` that still reaches
    this reader (untranslated transport) is malformed and refused.
    """
    _STDIN_PASSWORD_REFUSED = (
        f"stdin password must be a single line of at most {PASSWORD_MAX_LENGTH} "
        "characters with no extra data."
    )
    chars: list[str] = []
    newline_seen = False
    while True:
        char = sys.stdin.read(1)
        if char == "":
            break
        if newline_seen:
            # Second line or trailing data after the first newline.
            raise typer.BadParameter(_STDIN_PASSWORD_REFUSED)
        if char == "\n":
            newline_seen = True
            continue
        if char == "\r":
            raise typer.BadParameter(_STDIN_PASSWORD_REFUSED)
        if len(chars) >= PASSWORD_MAX_LENGTH:
            # Oversized first line: the outcome is fixed from here on.
            raise typer.BadParameter(_STDIN_PASSWORD_REFUSED)
        chars.append(char)
    password = "".join(chars)
    if not password:
        raise typer.BadParameter("No password found on stdin.")
    return password


def _prompt_password_pair() -> str:
    """Hidden confirmation prompt pair; fixed safe mismatch message (no echo)."""
    password = typer.prompt("Demo-admin password", hide_input=True)
    confirmation = typer.prompt("Confirm demo-admin password", hide_input=True)
    if password != confirmation:
        raise typer.BadParameter("Password confirmation mismatch.")
    return password


def _obtain_password(*, password_stdin: bool) -> str:
    if password_stdin:
        return _read_password_from_stdin()
    return _prompt_password_pair()


def _service(session) -> FakeAdminAccountService:
    return FakeAdminAccountService(session)


def _run_async(operation, *, json_output: bool = False) -> None:  # noqa: ANN001 - typer callback
    try:
        run_async(operation)
    except typer.Exit:
        raise
    except FakeAdminAccountError as exc:
        if json_output:
            emit_json({"error": {"code": exc.code, "message": exc.safe_message}})
        else:
            typer.secho(f"Error: {exc.safe_message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except (CliError, CliDatabaseConfigError, typer.BadParameter) as exc:
        # typer.BadParameter raised INSIDE the async operation (bounded
        # stdin password reader, hidden-prompt confirmation mismatch)
        # carries the fixed no-echo field-specific message; handle_cli_error
        # renders exactly that message (code: invalid_parameter) and never
        # any user value.
        handle_cli_error(exc, json_output=json_output)
    except Exception:  # noqa: BLE001 - fixed generic boundary, never echo detail
        if json_output:
            emit_json({"error": {"code": "command_failed", "message": "Command failed"}})
        else:
            typer.secho("Error: Command failed", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def _projection_payload(projection, **extra: object) -> dict[str, object]:
    payload = projection.to_safe_dict()
    payload.update(extra)
    return payload


@app.command("create")
def create(
    username: Annotated[str, typer.Argument(help="New demo-admin username (3..64 chars).")],
    reason: Annotated[
        str, typer.Option("--reason", help="Bounded audit reason (1..512 chars).")
    ],
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the password from stdin (one line)."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Create one enabled demo-admin account (credential generation 0)."""

    async def operation() -> None:
        password = _obtain_password(password_stdin=password_stdin)
        async with cli_db_session() as (_, session):
            projection = await _service(session).create_account(
                username=username, password=password, reason=reason
            )
        if json_output:
            emit_json(_projection_payload(projection, created=True))
        else:
            echo_kv(_projection_payload(projection, created=True))

    _run_async(operation(), json_output=json_output)


@app.command("list")
def list_accounts(
    limit: Annotated[str, typer.Option("--limit", help=f"Between {_LIST_LIMIT_MIN} and {_LIST_LIMIT_MAX}.")] = str(
        _LIST_LIMIT_DEFAULT
    ),
    offset: Annotated[
        str, typer.Option("--offset", help="Non-negative paging offset.")
    ] = "0",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """List demo-admin accounts (safe fields only; bounded page)."""

    async def operation() -> None:
        page_limit = _bounded_limit(limit)
        page_offset = _bounded_offset(offset)
        async with cli_db_session() as (_, session):
            result = await _service(session).list_accounts(limit=page_limit, offset=page_offset)
        if json_output:
            emit_json(
                {
                    "items": [item.to_safe_dict() for item in result.items],
                    "limit": result.limit,
                    "offset": result.offset,
                    "active_account_count": result.active_account_count,
                }
            )
        else:
            for item in result.items:
                safe = item.to_safe_dict()
                typer.echo(
                    " ".join(
                        (
                            f"username={safe['username']}",
                            f"id={safe['id']}",
                            f"enabled={'true' if safe['is_enabled'] else 'false'}",
                            f"generation={safe['credential_generation']}",
                            f"created_at={safe['created_at']}",
                            f"updated_at={safe['updated_at']}",
                        )
                    )
                )
            typer.echo(
                " ".join(
                    (
                        f"items={len(result.items)}",
                        f"limit={result.limit}",
                        f"offset={result.offset}",
                        f"active_accounts={result.active_account_count}",
                    )
                )
            )

    _run_async(operation(), json_output=json_output)


@app.command("enable")
def enable(
    username: Annotated[str, typer.Argument(help="Existing demo-admin username.")],
    reason: Annotated[
        str, typer.Option("--reason", help="Bounded audit reason (1..512 chars).")
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Enable one account (idempotent no-op when already enabled)."""

    async def operation() -> None:
        async with cli_db_session() as (_, session):
            result = await _service(session).set_enabled(
                username=username, enabled=True, reason=reason
            )
        payload = _projection_payload(result.projection, state_changed=result.state_changed)
        if json_output:
            emit_json(payload)
        else:
            echo_kv(payload)

    _run_async(operation(), json_output=json_output)


@app.command("disable")
def disable(
    username: Annotated[str, typer.Argument(help="Existing demo-admin username.")],
    reason: Annotated[
        str, typer.Option("--reason", help="Bounded audit reason (1..512 chars).")
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Disable one account (idempotent no-op when already disabled)."""

    async def operation() -> None:
        async with cli_db_session() as (_, session):
            result = await _service(session).set_enabled(
                username=username, enabled=False, reason=reason
            )
        payload = _projection_payload(result.projection, state_changed=result.state_changed)
        if json_output:
            emit_json(payload)
        else:
            echo_kv(payload)

    _run_async(operation(), json_output=json_output)


@app.command("reset-password")
def reset_password(
    username: Annotated[str, typer.Argument(help="Existing demo-admin username.")],
    reason: Annotated[
        str, typer.Option("--reason", help="Bounded audit reason (1..512 chars).")
    ],
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the password from stdin (one line)."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Reset one account's password (never re-enables a disabled account)."""

    async def operation() -> None:
        password = _obtain_password(password_stdin=password_stdin)
        async with cli_db_session() as (_, session):
            projection = await _service(session).reset_password(
                username=username, password=password, reason=reason
            )
        payload = _projection_payload(projection, reset=True)
        if json_output:
            emit_json(payload)
        else:
            echo_kv(payload)

    _run_async(operation(), json_output=json_output)
