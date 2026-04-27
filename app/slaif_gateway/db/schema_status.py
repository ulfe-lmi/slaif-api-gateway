"""Read-only Alembic schema status helpers for readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


SchemaState = Literal["ok", "missing", "outdated", "unknown"]


class _AsyncExecutable(Protocol):
    async def execute(self, statement): ...


@dataclass(frozen=True, slots=True)
class SchemaStatus:
    """Safe readiness status for the database schema revision."""

    status: SchemaState
    current_revision: str | None
    head_revision: str | None
    message: str

    @property
    def is_current(self) -> bool:
        return self.status == "ok"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    root = _repo_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config


def get_alembic_heads() -> tuple[str, ...]:
    """Return committed Alembic head revisions without touching the database."""
    script = ScriptDirectory.from_config(_alembic_config())
    return tuple(script.get_heads())


def get_alembic_head_revision() -> str:
    """Return the single expected Alembic head revision."""
    heads = get_alembic_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one Alembic head revision, found {len(heads)}.")
    return heads[0]


async def _alembic_version_table_exists(connection: _AsyncExecutable) -> bool:
    result = await connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'alembic_version'
            )
            """
        )
    )
    return bool(result.scalar())


async def get_database_current_revisions(connection: _AsyncExecutable) -> tuple[str, ...]:
    """Read current Alembic revision rows without modifying the database."""
    try:
        if not await _alembic_version_table_exists(connection):
            return ()
        result = await connection.execute(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        raise

    return tuple(str(revision) for revision in result.scalars().all())


async def get_database_current_revision(connection: _AsyncExecutable) -> str | None:
    """Return the database current revision when there is exactly one revision row."""
    revisions = await get_database_current_revisions(connection)
    if len(revisions) != 1:
        return None
    return revisions[0]


async def check_schema_current(connection: _AsyncExecutable) -> SchemaStatus:
    """Compare the database Alembic revision with the committed migration head."""
    try:
        heads = get_alembic_heads()
    except Exception:  # noqa: BLE001
        return SchemaStatus(
            status="unknown",
            current_revision=None,
            head_revision=None,
            message="Alembic head revision could not be determined.",
        )

    head_revision = ",".join(sorted(heads)) if heads else None
    if len(heads) != 1:
        return SchemaStatus(
            status="unknown",
            current_revision=None,
            head_revision=head_revision,
            message="Alembic migration graph does not have exactly one head revision.",
        )

    try:
        current_revisions = await get_database_current_revisions(connection)
    except SQLAlchemyError:
        return SchemaStatus(
            status="unknown",
            current_revision=None,
            head_revision=head_revision,
            message="Database schema revision could not be read.",
        )

    current_revision = ",".join(sorted(current_revisions)) if current_revisions else None
    if not current_revisions:
        return SchemaStatus(
            status="missing",
            current_revision=None,
            head_revision=head_revision,
            message="Alembic version table is missing or empty.",
        )

    if len(current_revisions) != 1:
        return SchemaStatus(
            status="unknown",
            current_revision=current_revision,
            head_revision=head_revision,
            message="Database has multiple Alembic current revisions.",
        )

    if current_revisions[0] != heads[0]:
        return SchemaStatus(
            status="outdated",
            current_revision=current_revisions[0],
            head_revision=heads[0],
            message="Database schema is not at the current Alembic head.",
        )

    return SchemaStatus(
        status="ok",
        current_revision=current_revisions[0],
        head_revision=heads[0],
        message="Database schema is current.",
    )
