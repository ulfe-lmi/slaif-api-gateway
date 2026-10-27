"""Read-only upstream compatibility profile inspection; no database required."""

from pathlib import Path

import typer

from slaif_gateway.cli.common import emit_json
from slaif_gateway.config import get_settings
from slaif_gateway.modules.servers.upstream_llm.profiles import load_profiles
from slaif_gateway.providers.errors import ProviderConfigurationError

app = typer.Typer(help="Inspect configured upstream LLM adapter profiles.")


@app.command("profiles")
def profiles(profile_file: Path | None = typer.Option(None, "--file")) -> None:
    """Print profile data and exact route selectors, without inference or mutation."""
    filename = str(profile_file) if profile_file else get_settings().UPSTREAM_LLM_PROFILES_FILE
    try:
        snapshot = load_profiles(filename)
    except ProviderConfigurationError as exc:
        typer.echo("Invalid upstream LLM profile file.", err=True)
        raise typer.Exit(code=1) from exc
    emit_json({"profiles": [
        {"data": profile.model_dump(), "route_selector": {
            "version": 1, "profile": profile.profile_id,
            "revision": profile.revision, "sha256": profile.sha256,
        }}
        for profile in snapshot.values()
    ]})
