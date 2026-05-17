"""Typer commands for trusted calibration usage previews."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    emit_json,
    handle_cli_error,
    json_default,
    parse_datetime,
    parse_decimal,
    parse_uuid,
    run_async,
)
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.usage_profiles import UsageProfilesRepository
from slaif_gateway.services.calibration_summary_service import (
    CalibrationPreviewResult,
    CalibrationSummaryService,
)

app = typer.Typer(help="Preview trusted calibration usage and participant policy proposals")


async def _summarize(
    *,
    gateway_key_id: str,
    start_at: str | None,
    end_at: str | None,
    multiplier: str,
) -> CalibrationPreviewResult:
    parsed_multiplier = parse_decimal(multiplier, field_name="multiplier")
    if parsed_multiplier is None:
        parsed_multiplier = Decimal("3")
    async with cli_db_session() as (_, session):
        service = CalibrationSummaryService(
            gateway_keys_repository=GatewayKeysRepository(session),
            usage_profiles_repository=UsageProfilesRepository(session),
        )
        return await service.summarize_calibration_key_usage(
            gateway_key_id=parse_uuid(gateway_key_id, field_name="gateway_key_id"),
            start_at=parse_datetime(start_at, field_name="start_at"),
            end_at=parse_datetime(end_at, field_name="end_at"),
            multiplier=parsed_multiplier,
        )


@app.callback()
def calibration() -> None:
    """Preview trusted calibration usage summaries."""


@app.command("summarize")
def summarize(
    gateway_key_id: Annotated[str, typer.Option("--gateway-key-id", help="Trusted calibration gateway key UUID")],
    start_at: Annotated[str | None, typer.Option("--start-at", help="Inclusive ISO created_at lower bound")] = None,
    end_at: Annotated[str | None, typer.Option("--end-at", help="Inclusive ISO created_at upper bound")] = None,
    multiplier: Annotated[str, typer.Option("--multiplier", help="Decimal policy multiplier from 1.0 to 10.0")] = "3",
    json_output: Annotated[bool, typer.Option("--json", help="Output machine-readable safe JSON")] = False,
    output: Annotated[Path | None, typer.Option("--output", help="Write safe JSON preview to this file")] = None,
) -> None:
    """Summarize a trusted calibration key and preview a strict participant policy."""
    try:
        result = run_async(
            _summarize(
                gateway_key_id=gateway_key_id,
                start_at=start_at,
                end_at=end_at,
                multiplier=multiplier,
            )
        )
        payload = _result_dict(result)
        if output is not None:
            _write_json_output(output, payload)
            typer.echo(f"Wrote {output}")
            return
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(payload)
        return
    _emit_human_summary(result)


def _result_dict(result: CalibrationPreviewResult) -> dict[str, object]:
    return asdict(result)


def _write_json_output(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, default=json_default, sort_keys=True, indent=2) + "\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("Output file already exists.") from exc
    except OSError as exc:
        raise ValueError("Could not create output file.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        raise ValueError("Could not write output file.") from exc


def _emit_human_summary(result: CalibrationPreviewResult) -> None:
    summary = result.summary
    proposal = result.proposal
    typer.echo("Trusted calibration usage summary")
    typer.echo(f"gateway_key_id: {summary.gateway_key_id}")
    typer.echo(f"public_key_id: {summary.public_key_id}")
    typer.echo(f"observed_request_count: {summary.observed_request_count}")
    typer.echo(f"observed_endpoints: {', '.join(summary.observed_endpoints) or 'none'}")
    typer.echo(f"observed_models: {', '.join(summary.observed_requested_models) or 'none'}")
    typer.echo(f"observed_providers: {', '.join(summary.observed_providers) or 'none'}")
    typer.echo(f"total_tokens: {summary.total_tokens}")
    typer.echo(f"total_slaif_calculated_cost: {summary.total_slaif_calculated_cost or 'unknown'}")
    typer.echo("")
    typer.echo("Preview-only strict participant policy proposal")
    typer.echo(f"multiplier: {proposal.multiplier}")
    typer.echo(f"proposed_allowed_endpoints: {', '.join(proposal.proposed_allowed_endpoints) or 'none'}")
    typer.echo(f"proposed_allowed_models: {', '.join(proposal.proposed_allowed_models) or 'none'}")
    typer.echo(f"proposed_allowed_providers: {', '.join(proposal.proposed_allowed_providers) or 'none'}")
    typer.echo(f"proposed_request_limit_total: {proposal.proposed_request_limit_total}")
    typer.echo(f"proposed_token_limit_total: {proposal.proposed_token_limit_total}")
    typer.echo(f"proposed_cost_limit_eur: {proposal.proposed_cost_limit_eur or 'unknown'}")
    if result.warnings:
        typer.echo("")
        typer.echo("Warnings")
        for warning in result.warnings:
            typer.echo(f"- {warning}")
    typer.echo("")
    typer.echo("No templates, keys, routes, or pricing rows were changed.")
