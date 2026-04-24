"""Database-related CLI commands."""

import typer

from slaif_gateway.config import get_settings
from slaif_gateway.utils.redaction import redact_database_url

app = typer.Typer(help="Database configuration helpers")


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
