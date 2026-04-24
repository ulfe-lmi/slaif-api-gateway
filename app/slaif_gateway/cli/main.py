"""Typer CLI entrypoint for SLAIF API Gateway."""

import typer

from slaif_gateway import __version__
from slaif_gateway.cli.db import app as db_app

app = typer.Typer(help="SLAIF API Gateway CLI")
app.add_typer(db_app, name="db")


@app.callback()
def main() -> None:
    """SLAIF API Gateway CLI root."""


@app.command("version")
def version() -> None:
    """Print package version."""
    typer.echo(f"slaif-api-gateway {__version__}")
