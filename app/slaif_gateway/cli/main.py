"""Typer CLI entrypoint for SLAIF API Gateway."""

from __future__ import annotations

import sys
from typing import Annotated

import structlog
import typer

from slaif_gateway import __version__
from slaif_gateway.cli.admin import app as admin_app
from slaif_gateway.cli.bootstrap import app as bootstrap_app
from slaif_gateway.cli.calibration import app as calibration_app
from slaif_gateway.cli.cohorts import app as cohorts_app
from slaif_gateway.cli.db import app as db_app
from slaif_gateway.cli.email import app as email_app
from slaif_gateway.cli.fx import app as fx_app
from slaif_gateway.cli.institutions import app as institutions_app
from slaif_gateway.cli.keys import app as keys_app
from slaif_gateway.cli.openai_assisted import app as openai_assisted_app
from slaif_gateway.cli.owners import app as owners_app
from slaif_gateway.cli.pricing import app as pricing_app
from slaif_gateway.cli.provider_catalog import app as provider_catalog_app
from slaif_gateway.cli.quota import app as quota_app
from slaif_gateway.cli.providers import app as providers_app
from slaif_gateway.cli.routes import app as routes_app
from slaif_gateway.cli.secrets import app as secrets_app
from slaif_gateway.cli.templates import app as templates_app
from slaif_gateway.cli.usage import app as usage_app
from slaif_gateway.config import get_settings
from slaif_gateway.logging import configure_logging

app = typer.Typer(help="SLAIF API Gateway CLI")
app.add_typer(admin_app, name="admin")
app.add_typer(bootstrap_app, name="bootstrap")
app.add_typer(calibration_app, name="calibration")
app.add_typer(institutions_app, name="institutions")
app.add_typer(cohorts_app, name="cohorts")
app.add_typer(owners_app, name="owners")
app.add_typer(db_app, name="db")
app.add_typer(email_app, name="email")
app.add_typer(keys_app, name="keys")
app.add_typer(providers_app, name="providers")
app.add_typer(routes_app, name="routes")
app.add_typer(pricing_app, name="pricing")
app.add_typer(provider_catalog_app, name="provider-catalog")
app.add_typer(fx_app, name="fx")
app.add_typer(usage_app, name="usage")
app.add_typer(quota_app, name="quota")
app.add_typer(secrets_app, name="secrets")
app.add_typer(openai_assisted_app, name="openai-assisted")
app.add_typer(templates_app, name="templates")

_ACCEPTED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
logger = structlog.get_logger(__name__)


def _normalize_cli_log_level(log_level: str) -> str:
    normalized = log_level.strip().upper()
    if normalized not in _ACCEPTED_LOG_LEVELS:
        raise typer.BadParameter(
            "--log-level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
        )
    return normalized


def _resolve_cli_log_level(*, verbose: bool, log_level: str | None) -> str | None:
    if verbose and log_level is not None:
        raise typer.BadParameter("Use either --verbose or --log-level, not both")
    if log_level is not None:
        return _normalize_cli_log_level(log_level)
    if verbose:
        return "DEBUG"
    return None


@app.callback()
def main(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable DEBUG-level CLI diagnostics for this command.",
        ),
    ] = False,
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            help="Set CLI log level for this command: DEBUG, INFO, WARNING, ERROR, or CRITICAL.",
        ),
    ] = None,
) -> None:
    """SLAIF API Gateway CLI root."""
    effective_log_level = _resolve_cli_log_level(verbose=verbose, log_level=log_level)
    settings = get_settings()
    logging_settings = (
        settings.model_copy(update={"LOG_LEVEL": effective_log_level})
        if effective_log_level is not None
        else settings
    )
    configure_logging(logging_settings, output=sys.stderr)
    logger.debug("cli.command.start", command=ctx.invoked_subcommand or "root")


@app.command("version")
def version() -> None:
    """Print package version."""
    typer.echo(f"slaif-api-gateway {__version__}")
