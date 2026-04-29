"""Database-related CLI commands."""

from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config
import typer

from slaif_gateway.config import get_settings
from slaif_gateway.utils.redaction import redact_database_url

app = typer.Typer(help="Database configuration helpers")


def _alembic_config() -> Config:
    """Return the project Alembic config for explicit operator commands."""
    return Config(str(Path.cwd() / "alembic.ini"))


@app.command("check-config")
def check_config() -> None:
    """Check whether DATABASE_URL is configured without connecting to the DB."""
    settings = get_settings()
    if settings.DATABASE_URL:
        typer.echo("DATABASE_URL configured: yes")
        typer.echo(f"DATABASE_URL (redacted): {redact_database_url(settings.DATABASE_URL)}")
        return

    typer.echo("DATABASE_URL configured: no")


@app.command("show-url")
def show_url() -> None:
    """Print the redacted DATABASE_URL value."""
    settings = get_settings()
    typer.echo(f"DATABASE_URL: {redact_database_url(settings.DATABASE_URL)}")


@app.command("upgrade")
def upgrade(
    revision: str = typer.Argument("head", help="Alembic revision target, usually 'head'."),
) -> None:
    """Run Alembic migrations explicitly."""
    alembic_command.upgrade(_alembic_config(), revision)


@app.command("current")
def current(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose Alembic output."),
) -> None:
    """Show the current Alembic revision."""
    alembic_command.current(_alembic_config(), verbose=verbose)
