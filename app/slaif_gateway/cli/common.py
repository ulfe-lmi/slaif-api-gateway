"""Shared helpers for Typer CLI modules."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import typer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.services.reconciliation_errors import ReconciliationError
from slaif_gateway.services.record_errors import RecordServiceError


class CliError(Exception):
    """Safe CLI-facing error."""


class CliDatabaseConfigError(CliError):
    """Raised when CLI database settings are missing or invalid."""


@asynccontextmanager
async def cli_db_session() -> AsyncIterator[tuple[Settings, AsyncSession]]:
    """Yield settings and a transaction-bound async database session."""
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError("DATABASE_URL is not configured. Set DATABASE_URL and try again.")

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            yield settings, session


def run_async(coro: Any) -> Any:
    """Run an async CLI operation."""
    return asyncio.run(coro)


def parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
    """Parse a UUID for a CLI option or argument."""
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{field_name} must be a valid UUID") from exc


def parse_datetime(value: str | None, *, field_name: str) -> datetime | None:
    """Parse an ISO datetime, defaulting naive values to UTC."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{field_name} cannot be empty")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise typer.BadParameter(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_decimal(value: str | None, *, field_name: str) -> Decimal | None:
    """Parse a decimal CLI value without going through float."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{field_name} cannot be empty")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise typer.BadParameter(f"{field_name} must be a decimal value") from exc


def require_positive_limit(limit: int) -> None:
    """Validate common positive limit options."""
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")


def json_default(value: object) -> object:
    """Serialize common database values as JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def emit_json(payload: dict[str, object]) -> None:
    """Emit a JSON object."""
    typer.echo(json.dumps(payload, default=json_default, sort_keys=True))


def echo_kv(payload: dict[str, object]) -> None:
    """Emit a compact key/value block."""
    for key, value in payload.items():
        if isinstance(value, datetime):
            display = value.isoformat()
        elif isinstance(value, Decimal):
            display = str(value)
        elif value is None:
            display = ""
        else:
            display = str(value)
        typer.echo(f"{key}: {display}")


def handle_cli_error(exc: Exception, *, json_output: bool = False) -> None:
    """Render a safe CLI error and exit non-zero."""
    if isinstance(exc, RecordServiceError):
        message = exc.safe_message
        code = exc.error_code
    elif isinstance(exc, ReconciliationError):
        message = exc.safe_message
        code = exc.error_code
    elif isinstance(exc, CliDatabaseConfigError):
        message = str(exc)
        code = "database_not_configured"
    elif isinstance(exc, CliError):
        message = str(exc)
        code = "cli_error"
    elif isinstance(exc, IntegrityError):
        message = "Duplicate or invalid record"
        code = "record_integrity_error"
    elif isinstance(exc, typer.BadParameter):
        message = str(exc)
        code = "invalid_parameter"
    elif isinstance(exc, ValueError):
        message = str(exc) or "Invalid value"
        code = "invalid_value"
    else:
        message = "Command failed"
        code = "command_failed"

    if json_output:
        emit_json({"error": {"code": code, "message": message}})
    else:
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def safe_output_has_no_secrets(output: str, forbidden_terms: tuple[str, ...]) -> bool:
    """Test helper to keep CLI output safety checks readable."""
    lowered = output.lower()
    return not any(term.lower() in lowered for term in forbidden_terms)
