"""Admin-only OpenAI-assisted proposal CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import emit_json, handle_cli_error, run_async
from slaif_gateway.config import get_settings
from slaif_gateway.services.openai_assisted_catalog import (
    DEFAULT_OPENAI_ASSISTED_MODEL,
    DEFAULT_OPENAI_MODELS_SOURCE_URL,
    DEFAULT_OPENAI_PRICING_SOURCE_URL,
    OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
    PROPOSAL_WARNING,
    OpenAIAssistedProposalResult,
    generate_openai_pricing_proposal,
    generate_openai_route_proposal,
)

app = typer.Typer(help="Generate reviewed OpenAI-assisted catalog proposal files")


@app.callback()
def openai_assisted() -> None:
    """Generate proposal files that must be imported through reviewed workflows."""


@app.command("pricing-proposal")
def pricing_proposal(
    output: Annotated[Path, typer.Option("--output", help="Proposal TSV output path.")],
    source_url: Annotated[
        str,
        typer.Option("--source-url", help="Official OpenAI pricing docs URL."),
    ] = DEFAULT_OPENAI_PRICING_SOURCE_URL,
    models_source_url: Annotated[
        str,
        typer.Option("--models-source-url", help="Official OpenAI model comparison docs URL."),
    ] = DEFAULT_OPENAI_MODELS_SOURCE_URL,
    api_key_env_var: Annotated[
        str,
        typer.Option(
            "--api-key-env-var",
            help="Environment variable containing the admin discovery OpenAI API key.",
        ),
    ] = OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="OpenAI model for the proposal; defaults to OPENAI_ASSISTED_CATALOG_MODEL.",
        ),
    ] = None,
    currency: Annotated[str, typer.Option("--currency", help="Proposal currency.")] = "USD",
    include_model: Annotated[
        list[str] | None,
        typer.Option("--include-model", help="Include only matching model names; repeatable."),
    ] = None,
    exclude_model: Annotated[
        list[str] | None,
        typer.Option("--exclude-model", help="Exclude matching model names; repeatable."),
    ] = None,
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="Endpoint alias/path for pricing rows."),
    ] = "chat.completions",
    max_web_calls: Annotated[
        int,
        typer.Option("--max-web-calls", help="Instruction-level cap for web search calls."),
    ] = 3,
    acknowledge_llm_proposal_risk: Annotated[
        bool,
        typer.Option(
            "--acknowledge-llm-proposal-risk",
            help="Required acknowledgement that generated rows are reviewed proposals only.",
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON summary.")] = False,
) -> None:
    """Generate an OpenAI pricing TSV proposal for later reviewed import."""
    if not acknowledge_llm_proposal_risk:
        handle_cli_error(
            ValueError("--acknowledge-llm-proposal-risk is required"),
            json_output=json_output,
        )
        return
    try:
        result = run_async(
            generate_openai_pricing_proposal(
                output_path=output,
                source_url=source_url,
                models_source_url=models_source_url,
                api_key_env_var=api_key_env_var,
                proposal_model=_effective_model(model),
                currency=currency,
                endpoint=endpoint,
                include_models=tuple(include_model or ()),
                exclude_models=tuple(exclude_model or ()),
                max_web_calls=max_web_calls,
                overwrite=overwrite,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    _emit_result(result, json_output=json_output)


@app.command("route-proposal")
def route_proposal(
    output: Annotated[Path, typer.Option("--output", help="Proposal TSV output path.")],
    source_url: Annotated[
        str,
        typer.Option("--source-url", help="Official OpenAI model comparison docs URL."),
    ] = DEFAULT_OPENAI_MODELS_SOURCE_URL,
    api_key_env_var: Annotated[
        str,
        typer.Option(
            "--api-key-env-var",
            help="Environment variable containing the admin discovery OpenAI API key.",
        ),
    ] = OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="OpenAI model for the proposal; defaults to OPENAI_ASSISTED_CATALOG_MODEL.",
        ),
    ] = None,
    include_model: Annotated[
        list[str] | None,
        typer.Option("--include-model", help="Include only matching model names; repeatable."),
    ] = None,
    exclude_model: Annotated[
        list[str] | None,
        typer.Option("--exclude-model", help="Exclude matching model names; repeatable."),
    ] = None,
    implemented_endpoints_only: Annotated[
        bool,
        typer.Option(
            "--implemented-endpoints-only/--include-unsupported-endpoints",
            help="Only emit currently implemented gateway endpoints.",
        ),
    ] = True,
    acknowledge_llm_proposal_risk: Annotated[
        bool,
        typer.Option(
            "--acknowledge-llm-proposal-risk",
            help="Required acknowledgement that generated rows are reviewed proposals only.",
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace an existing output file."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON summary.")] = False,
) -> None:
    """Generate an OpenAI Chat Completions route TSV proposal for reviewed import."""
    if not acknowledge_llm_proposal_risk:
        handle_cli_error(
            ValueError("--acknowledge-llm-proposal-risk is required"),
            json_output=json_output,
        )
        return
    try:
        result = run_async(
            generate_openai_route_proposal(
                output_path=output,
                source_url=source_url,
                api_key_env_var=api_key_env_var,
                proposal_model=_effective_model(model),
                include_models=tuple(include_model or ()),
                exclude_models=tuple(exclude_model or ()),
                implemented_endpoints_only=implemented_endpoints_only,
                overwrite=overwrite,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    _emit_result(result, json_output=json_output)


def _effective_model(model: str | None) -> str:
    if model is not None and model.strip():
        return model.strip()
    configured = get_settings().OPENAI_ASSISTED_CATALOG_MODEL.strip()
    return configured or DEFAULT_OPENAI_ASSISTED_MODEL


def _emit_result(result: OpenAIAssistedProposalResult, *, json_output: bool) -> None:
    payload = {
        "warning": PROPOSAL_WARNING,
        "proposal_type": result.proposal_type,
        "output_path": str(result.output_path),
        "row_count": result.row_count,
        "warnings": list(result.warnings),
        "source_urls": list(result.source_urls),
        "next_steps": list(result.next_steps),
        "mutated_metadata": False,
    }
    if json_output:
        emit_json(payload)
        return
    typer.secho(PROPOSAL_WARNING, fg=typer.colors.YELLOW, bold=True)
    typer.echo(f"proposal_type: {result.proposal_type}")
    typer.echo(f"output_path: {result.output_path}")
    typer.echo(f"row_count: {result.row_count}")
    if result.warnings:
        typer.echo("warnings:")
        for warning in result.warnings:
            typer.echo(f"- {warning}")
    typer.echo("next steps:")
    typer.echo("- inspect TSV")
    typer.echo("- run pricing/routes import preview")
    typer.echo("- execute import only with confirmation and audit reason")
