"""Typer commands for first-time metadata bootstrap workflows."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import cli_db_session, emit_json, handle_cli_error, run_async
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.openai_completions_catalog import (
    PLACEHOLDER_PRICING_NOTE,
    BootstrapRowStatus,
    OpenAICompletionsBootstrapResult,
    bootstrap_openai_completions_catalog,
    load_pricing_file,
)

app = typer.Typer(help="Bootstrap common local metadata catalogs")


class PricingModeOption(str, Enum):
    """CLI pricing modes for catalog bootstrap."""

    require_file = "require-file"
    placeholder = "placeholder"


@app.callback()
def bootstrap() -> None:
    """Bootstrap local metadata required by OpenAI-compatible workflows."""


async def _bootstrap_openai_completions_catalog(
    *,
    api_key_env_var: str,
    currency: str,
    pricing_mode: PricingModeOption,
    pricing_file: Path | None,
    confirm_placeholder_pricing: bool,
    include_legacy_completions: bool,
    include_legacy_models: bool,
    dry_run: bool,
) -> OpenAICompletionsBootstrapResult:
    if include_legacy_completions:
        raise ValueError("/v1/completions legacy endpoint is not implemented")
    if pricing_mode == PricingModeOption.require_file:
        if pricing_file is None:
            raise ValueError("--pricing-file is required when --pricing-mode=require-file")
        pricing_file_rows = load_pricing_file(pricing_file, currency=currency)
    else:
        if pricing_file is not None:
            raise ValueError("--pricing-file cannot be used when --pricing-mode=placeholder")
        if not confirm_placeholder_pricing:
            raise ValueError(
                "--confirm-placeholder-pricing is required when --pricing-mode=placeholder"
            )
        pricing_file_rows = {}

    async with cli_db_session() as (_, session):
        return await bootstrap_openai_completions_catalog(
            provider_configs_repository=ProviderConfigsRepository(session),
            model_routes_repository=ModelRoutesRepository(session),
            pricing_rules_repository=PricingRulesRepository(session),
            audit_repository=AuditRepository(session),
            api_key_env_var=api_key_env_var,
            currency=currency,
            pricing_mode=pricing_mode.value,  # type: ignore[arg-type]
            pricing_file_rows=pricing_file_rows,
            include_legacy_completions=include_legacy_completions,
            include_legacy_models=include_legacy_models,
            dry_run=dry_run,
        )


@app.command("openai-completions-catalog")
def openai_completions_catalog(
    api_key_env_var: Annotated[
        str,
        typer.Option(
            "--api-key-env-var",
            help="Environment variable name holding the server-side OpenAI provider key.",
        ),
    ] = "OPENAI_UPSTREAM_API_KEY",
    currency: Annotated[
        str,
        typer.Option("--currency", help="Currency code for pricing rows."),
    ] = "EUR",
    pricing_mode: Annotated[
        PricingModeOption,
        typer.Option("--pricing-mode", help="require-file or placeholder."),
    ] = PricingModeOption.require_file,
    pricing_file: Annotated[
        Path | None,
        typer.Option("--pricing-file", help="Operator-controlled pricing CSV."),
    ] = None,
    confirm_placeholder_pricing: Annotated[
        bool,
        typer.Option(
            "--confirm-placeholder-pricing",
            help="Confirm placeholder pricing is for smoke tests only.",
        ),
    ] = False,
    include_legacy_completions: Annotated[
        bool,
        typer.Option(
            "--include-legacy-completions/--no-include-legacy-completions",
            help="Include /v1/completions routes if implemented.",
        ),
    ] = False,
    include_legacy_models: Annotated[
        bool,
        typer.Option(
            "--include-legacy-models/--no-include-legacy-models",
            help="Include older chat models from the curated catalog.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Preview without writing, or apply changes."),
    ] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Seed local OpenAI Chat Completions provider, routes, and pricing metadata."""
    try:
        result = run_async(
            _bootstrap_openai_completions_catalog(
                api_key_env_var=api_key_env_var,
                currency=currency,
                pricing_mode=pricing_mode,
                pricing_file=pricing_file,
                confirm_placeholder_pricing=confirm_placeholder_pricing,
                include_legacy_completions=include_legacy_completions,
                include_legacy_models=include_legacy_models,
                dry_run=dry_run,
            )
        )
        if result.has_blockers:
            _emit_result(result, json_output=json_output)
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    _emit_result(result, json_output=json_output)


def _emit_result(result: OpenAICompletionsBootstrapResult, *, json_output: bool) -> None:
    if json_output:
        emit_json(_result_to_dict(result))
        return

    mode = "dry-run" if result.dry_run else "applied"
    typer.echo(f"mode: {mode}")
    typer.echo(f"provider: {result.provider.status}")
    _echo_counts("chat.completions routes", result.chat_routes)
    if result.completions_routes:
        if all(row.status == "not_implemented" for row in result.completions_routes):
            typer.echo("completions routes: not implemented")
        else:
            _echo_counts("completions routes", result.completions_routes)
    _echo_counts("pricing", result.pricing)
    if result.placeholder_pricing:
        typer.secho(
            f"warning: {PLACEHOLDER_PRICING_NOTE}",
            fg=typer.colors.YELLOW,
        )
    if result.has_blockers:
        typer.echo("blocked: resolve missing/conflicting rows and rerun the command")
    typer.echo("next steps:")
    typer.echo("- create or edit a gateway key")
    typer.echo("- allow endpoints /v1/models and /v1/chat/completions")
    typer.echo("- allow all catalog models or list the desired model IDs")
    typer.echo("- test /v1/models")


def _echo_counts(label: str, rows: tuple[BootstrapRowStatus, ...]) -> None:
    counts = _counts(rows)
    if label == "pricing":
        typer.echo(
            f"{label}: {counts['created']} created, {counts['exists']} exists, "
            f"{counts['missing']} missing, {counts['conflict']} conflicts"
        )
        return
    typer.echo(
        f"{label}: {counts['created']} created, {counts['exists']} exists, "
        f"{counts['conflict']} conflicts"
    )


def _counts(rows: tuple[BootstrapRowStatus, ...]) -> Counter[str]:
    counts: Counter[str] = Counter(row.status for row in rows)
    for key in ("created", "exists", "missing", "conflict", "not_implemented"):
        counts.setdefault(key, 0)
    return counts


def _result_to_dict(result: OpenAICompletionsBootstrapResult) -> dict[str, object]:
    return {
        "dry_run": result.dry_run,
        "provider": _row_to_dict(result.provider),
        "chat_completions_routes": [_row_to_dict(row) for row in result.chat_routes],
        "completions_routes": [_row_to_dict(row) for row in result.completions_routes],
        "pricing": [_row_to_dict(row) for row in result.pricing],
        "selected_models": list(result.selected_models),
        "placeholder_pricing": result.placeholder_pricing,
        "has_blockers": result.has_blockers,
    }


def _row_to_dict(row: BootstrapRowStatus) -> dict[str, object]:
    return {
        "status": row.status,
        "model_id": row.model_id,
        "endpoint": row.endpoint,
        "message": row.message,
    }
