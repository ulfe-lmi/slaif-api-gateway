"""Read-only Codex protocol qualification and profile-v2 commands."""

from __future__ import annotations

from typing import Annotated

import typer

from slaif_gateway.cli.common import cli_db_session, emit_json, handle_cli_error, run_async
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.codex_qualification import (
    CodexProfileArtifacts,
    CodexQualificationResult,
    CodexQualificationService,
    render_codex_profile,
    render_codex_profile_text,
)

app = typer.Typer(help="Inspect Codex protocol qualification and render a safe user profile")


def _service(session: object) -> CodexQualificationService:
    return CodexQualificationService(
        provider_configs_repository=ProviderConfigsRepository(session),
        model_routes_repository=ModelRoutesRepository(session),
        pricing_rules_repository=PricingRulesRepository(session),
        fx_rates_repository=FxRatesRepository(session),
    )


async def _inspect_codex() -> list[CodexQualificationResult]:
    async with cli_db_session() as (_, session):
        return await _service(session).inspect()


async def _build_profile(base_url: str) -> tuple[CodexQualificationResult, CodexProfileArtifacts]:
    async with cli_db_session() as (_, session):
        qualification = await _service(session).ready_responses_profile()
    return qualification, render_codex_profile(base_url)


@app.callback()
def codex() -> None:
    """Inspect exact local Codex protocol qualification."""


@app.command("inspect")
def inspect(
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """List deterministic local Codex qualification/readiness results."""

    try:
        results = run_async(_inspect_codex())
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = [result.to_safe_dict() for result in results]
    if json_output:
        emit_json({"qualifications": payload})
        return
    if not payload:
        typer.echo("No model routes found.")
        return
    for index, result in enumerate(payload):
        if index:
            typer.echo("")
        typer.echo(f"state: {result['state']}")
        typer.echo(f"requested_model: {result['requested_model']}")
        typer.echo(f"provider: {result['provider']}")
        typer.echo(f"endpoint: {result['endpoint']}")
        typer.echo(f"route_id: {result['route_id']}")
        typer.echo(f"paired_route_id: {result['paired_route_id'] or ''}")
        typer.echo(f"reason_codes: {','.join(result['reason_codes'])}")
        typer.echo(f"real_provider_e2e: {str(result['real_provider_e2e']).lower()}")


@app.command("profile")
def profile(
    base_url: Annotated[
        str,
        typer.Option(
            "--base-url",
            help="Credential-free SLAIF gateway base URL ending exactly /v1",
        ),
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Print, but never write, the ready two-file Codex profile-v2 layout."""

    try:
        qualification, artifacts = run_async(_build_profile(base_url))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    if json_output:
        payload = artifacts.to_safe_dict()
        payload["qualification"] = qualification.to_safe_dict()
        emit_json(payload)
        return
    typer.echo(render_codex_profile_text(artifacts), nl=False)
