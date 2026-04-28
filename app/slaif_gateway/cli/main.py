"""Typer CLI entrypoint for SLAIF API Gateway."""

import typer

from slaif_gateway import __version__
from slaif_gateway.cli.admin import app as admin_app
from slaif_gateway.cli.cohorts import app as cohorts_app
from slaif_gateway.cli.db import app as db_app
from slaif_gateway.cli.email import app as email_app
from slaif_gateway.cli.fx import app as fx_app
from slaif_gateway.cli.institutions import app as institutions_app
from slaif_gateway.cli.keys import app as keys_app
from slaif_gateway.cli.owners import app as owners_app
from slaif_gateway.cli.pricing import app as pricing_app
from slaif_gateway.cli.quota import app as quota_app
from slaif_gateway.cli.providers import app as providers_app
from slaif_gateway.cli.routes import app as routes_app
from slaif_gateway.cli.usage import app as usage_app

app = typer.Typer(help="SLAIF API Gateway CLI")
app.add_typer(admin_app, name="admin")
app.add_typer(institutions_app, name="institutions")
app.add_typer(cohorts_app, name="cohorts")
app.add_typer(owners_app, name="owners")
app.add_typer(db_app, name="db")
app.add_typer(email_app, name="email")
app.add_typer(keys_app, name="keys")
app.add_typer(providers_app, name="providers")
app.add_typer(routes_app, name="routes")
app.add_typer(pricing_app, name="pricing")
app.add_typer(fx_app, name="fx")
app.add_typer(usage_app, name="usage")
app.add_typer(quota_app, name="quota")


@app.callback()
def main() -> None:
    """SLAIF API Gateway CLI root."""


@app.command("version")
def version() -> None:
    """Print package version."""
    typer.echo(f"slaif-api-gateway {__version__}")
