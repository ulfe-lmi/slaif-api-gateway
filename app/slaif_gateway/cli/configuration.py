"""Typer commands for finite process-configuration inspection (204).

The ``config show`` command reports the CURRENT CLI process's cached
Settings snapshot through a finite reviewed allowlist. It never exposes
credential values, and an invalid Settings environment maps to a fixed
safe unavailable payload (no ValidationError value/traceback echo).
"""

from __future__ import annotations

from typing import Annotated

import typer

from slaif_gateway.cli.common import emit_json
from slaif_gateway.config import get_settings
from slaif_gateway.services.configuration_inspection import (
    inspect_process_configuration,
    render_process_configuration_text,
)

app = typer.Typer(help="Show the current CLI process configuration")

_UNAVAILABLE_CODE = "configuration_unavailable"
_UNAVAILABLE_MESSAGE = (
    "Process configuration could not be loaded. Check the deployment "
    "environment and try again."
)


@app.command("show")
def show(
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show the finite allowlisted Settings snapshot for this process."""
    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001 - fixed safe boundary, no value echo
        if json_output:
            emit_json(
                {"error": {"code": _UNAVAILABLE_CODE, "message": _UNAVAILABLE_MESSAGE}}
            )
        else:
            typer.secho(
                f"Error: {_UNAVAILABLE_MESSAGE}", fg=typer.colors.RED, err=True
            )
        raise typer.Exit(code=1)

    payload = inspect_process_configuration(settings)
    if json_output:
        emit_json(payload)
        return
    typer.echo(render_process_configuration_text(payload))
