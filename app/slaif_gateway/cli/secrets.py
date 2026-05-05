"""CLI helpers for generating and validating runtime secrets."""

from __future__ import annotations

import base64
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import CliError, handle_cli_error
from slaif_gateway.config import is_placeholder_secret
from slaif_gateway.utils.secrets import generate_secret_key

app = typer.Typer(help="Generate and validate server runtime secrets")
generate_app = typer.Typer(help="Generate one runtime secret")
app.add_typer(generate_app, name="generate")

_ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=")
_ONE_TIME_SECRET_BYTES = 32


def _hmac_env_var(version: int) -> str:
    if version <= 0:
        raise typer.BadParameter("--version must be a positive integer")
    return f"TOKEN_HMAC_SECRET_V{version}"


def _generate_text_secret() -> str:
    return secrets.token_urlsafe(48)


def _env_line_key(line: str) -> str | None:
    match = _ENV_LINE_RE.match(line)
    if match is None:
        return None
    return match.group("key")


def _strip_inline_newline(line: str) -> str:
    return line[:-1] if line.endswith("\n") else line


def _parse_env_assignment_value(line: str) -> str:
    body = _strip_inline_newline(line)
    _, _, raw_value = body.partition("=")
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_env_values(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliError(f"Env file not found: {path}. Run cp .env.example .env first.") from exc
    except OSError as exc:
        raise CliError(f"Could not read env file: {path}") from exc

    values: dict[str, str] = {}
    for line in text.splitlines():
        key = _env_line_key(line)
        if key is None:
            continue
        values[key] = _parse_env_assignment_value(line)
    return values


def _warn_if_env_file_is_broadly_readable(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return
    if mode & 0o077:
        typer.secho(
            f"Warning: {path} is readable by other users; consider chmod 600 {path}",
            fg=typer.colors.YELLOW,
            err=True,
        )


def _replacement_warning(env_var: str) -> str:
    if env_var.startswith("TOKEN_HMAC_SECRET_V"):
        return (
            f"Warning: replacing {env_var} invalidates existing gateway keys signed "
            "with that version unless the old secret remains configured."
        )
    if env_var == "ADMIN_SESSION_SECRET":
        return "Warning: replacing ADMIN_SESSION_SECRET invalidates active admin sessions."
    if env_var == "ONE_TIME_SECRET_ENCRYPTION_KEY":
        return (
            "Warning: replacing ONE_TIME_SECRET_ENCRYPTION_KEY can make existing encrypted "
            "one-time secrets undecryptable."
        )
    return f"Warning: replacing {env_var} changes runtime secret material."


def _write_env_value(path: Path, env_var: str, value: str, *, force: bool) -> None:
    if path.name == ".env.example":
        raise CliError("Refusing to modify .env.example; copy it to .env first.")

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliError(f"Env file not found: {path}. Run cp .env.example .env first.") from exc
    except OSError as exc:
        raise CliError(f"Could not read env file: {path}") from exc

    _warn_if_env_file_is_broadly_readable(path)

    lines = text.splitlines(keepends=True)
    updated = False
    for index, line in enumerate(lines):
        if _env_line_key(line) != env_var:
            continue
        current_value = _parse_env_assignment_value(line)
        if current_value and not is_placeholder_secret(current_value) and not force:
            raise CliError(
                f"{env_var} already has a non-placeholder value in {path}; use --force "
                "only if you intend to replace it."
            )
        if current_value and not is_placeholder_secret(current_value) and force:
            typer.secho(_replacement_warning(env_var), fg=typer.colors.YELLOW, err=True)
        lines[index] = f"{env_var}={value}\n"
        updated = True
        break

    if not updated:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = f"{lines[-1]}\n"
        lines.append(f"{env_var}={value}\n")

    try:
        path.write_text("".join(lines), encoding="utf-8")
    except OSError as exc:
        raise CliError(f"Could not update env file: {path}") from exc


def _emit_or_write_secret(
    *,
    env_var: str,
    value: str,
    env_file: Path,
    write: bool,
    force: bool,
) -> None:
    if not write:
        typer.echo(value)
        return

    _write_env_value(env_file, env_var, value, force=force)
    typer.echo(f"Updated {env_var} in {env_file}")


def _decode_one_time_secret(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as exc:  # noqa: BLE001
        raise CliError("ONE_TIME_SECRET_ENCRYPTION_KEY must be base64url-encoded") from exc


def _validate_one_time_secret(value: str) -> None:
    decoded = _decode_one_time_secret(value)
    if len(decoded) != _ONE_TIME_SECRET_BYTES:
        raise CliError("ONE_TIME_SECRET_ENCRYPTION_KEY must decode to exactly 32 bytes")


@app.callback()
def secrets_root() -> None:
    """Generate and validate server runtime secrets."""


@generate_app.callback()
def generate_root() -> None:
    """Generate one server runtime secret."""


@generate_app.command("hmac")
def generate_hmac(
    version: Annotated[int, typer.Option("--version", help="HMAC secret version")],
    env_file: Annotated[Path, typer.Option("--env-file", help="Env file to update")] = Path(
        ".env"
    ),
    write: Annotated[bool, typer.Option("--write", help="Write the value to --env-file")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing non-placeholder value"),
    ] = False,
) -> None:
    """Generate a TOKEN_HMAC_SECRET_V<version> value."""
    try:
        _emit_or_write_secret(
            env_var=_hmac_env_var(version),
            value=_generate_text_secret(),
            env_file=env_file,
            write=write,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc)


@generate_app.command("admin-session")
def generate_admin_session(
    env_file: Annotated[Path, typer.Option("--env-file", help="Env file to update")] = Path(
        ".env"
    ),
    write: Annotated[bool, typer.Option("--write", help="Write the value to --env-file")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing non-placeholder value"),
    ] = False,
) -> None:
    """Generate an ADMIN_SESSION_SECRET value."""
    try:
        _emit_or_write_secret(
            env_var="ADMIN_SESSION_SECRET",
            value=_generate_text_secret(),
            env_file=env_file,
            write=write,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc)


@generate_app.command("one-time")
def generate_one_time(
    env_file: Annotated[Path, typer.Option("--env-file", help="Env file to update")] = Path(
        ".env"
    ),
    write: Annotated[bool, typer.Option("--write", help="Write the value to --env-file")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing non-placeholder value"),
    ] = False,
) -> None:
    """Generate a ONE_TIME_SECRET_ENCRYPTION_KEY value."""
    try:
        _emit_or_write_secret(
            env_var="ONE_TIME_SECRET_ENCRYPTION_KEY",
            value=generate_secret_key(),
            env_file=env_file,
            write=write,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc)


@app.command("validate-env")
def validate_env(
    env_file: Annotated[Path, typer.Option("--env-file", help="Env file to validate")] = Path(
        ".env"
    ),
) -> None:
    """Validate required runtime secrets in an env file without printing values."""
    try:
        values = _load_env_values(env_file)
        app_env = values.get("APP_ENV", "development").strip().lower()
        active_version = values.get("ACTIVE_HMAC_KEY_VERSION", "1").strip() or "1"
        try:
            version_int = int(active_version)
        except ValueError as exc:
            raise CliError("ACTIVE_HMAC_KEY_VERSION must be a positive integer") from exc
        if version_int <= 0:
            raise CliError("ACTIVE_HMAC_KEY_VERSION must be a positive integer")
        hmac_env_var = _hmac_env_var(version_int)

        hmac_secret = values.get(hmac_env_var)
        if hmac_secret is None or is_placeholder_secret(hmac_secret):
            raise CliError(f"{hmac_env_var} must be configured with a non-placeholder value")
        typer.echo(f"OK: {hmac_env_var} configured")

        admin_session_secret = values.get("ADMIN_SESSION_SECRET")
        if admin_session_secret is None or is_placeholder_secret(admin_session_secret):
            raise CliError("ADMIN_SESSION_SECRET must be configured with a non-placeholder value")
        typer.echo("OK: ADMIN_SESSION_SECRET configured")

        one_time_secret = values.get("ONE_TIME_SECRET_ENCRYPTION_KEY", "").strip()
        if one_time_secret:
            _validate_one_time_secret(one_time_secret)
            typer.echo("OK: ONE_TIME_SECRET_ENCRYPTION_KEY decodes to 32 bytes")
        elif app_env == "production":
            raise CliError("ONE_TIME_SECRET_ENCRYPTION_KEY is required when APP_ENV=production")
        else:
            typer.echo("OK: ONE_TIME_SECRET_ENCRYPTION_KEY blank for development")
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc)
