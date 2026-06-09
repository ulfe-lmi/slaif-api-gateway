"""CLI commands for provider catalog proposal generation."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import emit_json, handle_cli_error, run_async
from slaif_gateway.services.provider_catalog_proposal import (
    OPENAI_ASSISTED_ACKNOWLEDGEMENT,
    ProviderCatalogProposalResult,
    generate_provider_catalog_proposal,
)

app = typer.Typer(help="Generate provider catalog proposal files for reviewed import workflows")


class ProviderScopeOption(str, Enum):
    openai = "openai"
    openrouter = "openrouter"
    all = "all"


class SourceMethodOption(str, Enum):
    docs = "docs"
    api = "api"
    assisted = "assisted"


class EndpointScopeOption(str, Enum):
    chat_completions = "chat_completions"
    responses = "responses"


@app.callback()
def provider_catalog() -> None:
    """Proposal-only provider catalog commands."""


@app.command("propose")
def propose_catalog(
    provider: Annotated[ProviderScopeOption, typer.Argument(help="openai, openrouter, or all.")],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory where proposal artifacts will be written."),
    ],
    include_model: Annotated[
        list[str] | None,
        typer.Option("--include-model", help="Include only matching model IDs; repeatable."),
    ] = None,
    exclude_model: Annotated[
        list[str] | None,
        typer.Option("--exclude-model", help="Exclude matching model IDs; repeatable."),
    ] = None,
    endpoint_scope: Annotated[
        list[EndpointScopeOption] | None,
        typer.Option("--endpoint-scope", help="chat_completions or responses; repeatable."),
    ] = None,
    currency: Annotated[str, typer.Option("--currency", help="Currency code for pricing TSV rows.")] = "USD",
    source: Annotated[
        list[SourceMethodOption] | None,
        typer.Option("--source", help="Additional source comparison method; repeatable."),
    ] = None,
    max_models: Annotated[int, typer.Option("--max-models", help="Maximum models to include.")] = 500,
    fetch_details_limit: Annotated[
        int,
        typer.Option("--fetch-details-limit", help="Maximum OpenRouter details endpoints to fetch."),
    ] = 50,
    include_api_models: Annotated[
        bool,
        typer.Option(
            "--include-api-models",
            help="For OpenAI proposals, call GET /v1/models using OPENAI_ADMIN_DISCOVERY_API_KEY.",
        ),
    ] = False,
    max_web_calls: Annotated[
        int,
        typer.Option("--max-web-calls", help="OpenAI assisted cross-check web-call cap."),
    ] = 3,
    save_source_snapshots: Annotated[
        bool,
        typer.Option(
            "--save-source-snapshots/--no-save-source-snapshots",
            help="Save fetched raw source snapshots in the output directory.",
        ),
    ] = False,
    allow_zero_prices: Annotated[
        bool,
        typer.Option(
            "--allow-zero-prices",
            help="Mark zero-price pricing rows as import-ready; they still require operator review.",
        ),
    ] = False,
    acknowledge_assisted_proposal_risk: Annotated[
        bool,
        typer.Option(
            "--acknowledge-assisted-proposal-risk",
            help=OPENAI_ASSISTED_ACKNOWLEDGEMENT,
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output a safe JSON summary.")] = False,
) -> None:
    """Generate provider catalog proposal files without mutating local metadata."""
    try:
        result = run_async(
            generate_provider_catalog_proposal(
                provider_scope=provider.value,
                output_dir=output_dir,
                endpoint_scopes=tuple((endpoint_scope or [EndpointScopeOption.chat_completions])),
                include_models=tuple(include_model or ()),
                exclude_models=tuple(exclude_model or ()),
                currency=currency,
                source_methods=tuple(source or ()),
                max_models=max_models,
                fetch_details_limit=fetch_details_limit,
                include_api_models=include_api_models,
                max_web_calls=max_web_calls,
                save_source_snapshots=save_source_snapshots,
                acknowledge_assisted_proposal_risk=acknowledge_assisted_proposal_risk,
                allow_zero_prices=allow_zero_prices,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    _emit_result(result, json_output=json_output)


def _emit_result(result: ProviderCatalogProposalResult, *, json_output: bool) -> None:
    payload = {
        "output_dir": str(result.output_dir),
        "route_rows_ready": result.route_rows_ready,
        "pricing_rows_ready": result.pricing_rows_ready,
        "warnings": result.warnings_count,
        "high_confidence": result.high_confidence,
        "medium_confidence": result.medium_confidence,
        "low_confidence": result.low_confidence,
        "files": {
            "routes_proposal_tsv": str(result.routes_proposal_path),
            "pricing_proposal_tsv": str(result.pricing_proposal_path),
            "normalized_json": str(result.normalized_path),
            "report_markdown": str(result.report_path),
            "warnings_json": str(result.warnings_path),
            "source_manifest_json": str(result.manifest_path),
        },
        "mutated_metadata": False,
    }
    if json_output:
        emit_json(payload)
        return

    typer.echo("Provider catalog proposal complete")
    typer.echo(f"output_dir={result.output_dir}")
    typer.echo(f"route_rows_ready={result.route_rows_ready}")
    typer.echo(f"pricing_rows_ready={result.pricing_rows_ready}")
    typer.echo(f"warnings={result.warnings_count}")
    typer.echo(f"high_confidence={result.high_confidence}")
    typer.echo(f"medium_confidence={result.medium_confidence}")
    typer.echo(f"low_confidence={result.low_confidence}")
    typer.echo("files:")
    typer.echo(f"- {result.routes_proposal_path}")
    typer.echo(f"- {result.pricing_proposal_path}")
    typer.echo(f"- {result.normalized_path}")
    typer.echo(f"- {result.report_path}")
    typer.echo(f"- {result.warnings_path}")
    typer.echo(f"- {result.manifest_path}")
