"""Typer commands for durable key templates."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    emit_json,
    handle_cli_error,
    parse_datetime,
    parse_decimal,
    parse_uuid,
    run_async,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.key_templates import KeyTemplatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.usage_profiles import UsageProfilesRepository
from slaif_gateway.services.calibration_summary_service import CalibrationSummaryService
from slaif_gateway.services.key_template_service import KeyTemplateCreationResult, KeyTemplateService

app = typer.Typer(help="Create and inspect durable key templates")


@app.callback()
def templates() -> None:
    """Manage versioned key template policy snapshots."""


async def _create_from_calibration(
    *,
    gateway_key_id: str,
    name: str,
    description: str | None,
    start_at: str | None,
    end_at: str | None,
    multiplier: str,
    validity_days_default: int | None,
    email_delivery_mode_default: str | None,
    confirm_create_template: bool,
    reason: str,
) -> KeyTemplateCreationResult:
    parsed_multiplier = parse_decimal(multiplier, field_name="multiplier")
    if parsed_multiplier is None:
        parsed_multiplier = Decimal("3")
    async with cli_db_session() as (_, session):
        calibration_service = CalibrationSummaryService(
            gateway_keys_repository=GatewayKeysRepository(session),
            usage_profiles_repository=UsageProfilesRepository(session),
        )
        preview = await calibration_service.summarize_calibration_key_usage(
            gateway_key_id=parse_uuid(gateway_key_id, field_name="gateway_key_id"),
            start_at=parse_datetime(start_at, field_name="start_at"),
            end_at=parse_datetime(end_at, field_name="end_at"),
            multiplier=parsed_multiplier,
        )
        template_service = KeyTemplateService(
            key_templates_repository=KeyTemplatesRepository(session),
            audit_repository=AuditRepository(session),
        )
        return await template_service.create_from_calibration_proposal(
            preview=preview,
            name=name,
            description=description,
            reason=reason,
            confirm_create_template=confirm_create_template,
            validity_days_default=validity_days_default,
            email_delivery_mode_default=email_delivery_mode_default,
        )


@app.command("create-from-calibration")
def create_from_calibration(
    gateway_key_id: Annotated[str, typer.Option("--gateway-key-id", help="Trusted calibration gateway key UUID")],
    name: Annotated[str, typer.Option("--name", help="Template name")],
    description: Annotated[str | None, typer.Option("--description", help="Template description")] = None,
    start_at: Annotated[str | None, typer.Option("--start-at", help="Inclusive ISO created_at lower bound")] = None,
    end_at: Annotated[str | None, typer.Option("--end-at", help="Inclusive ISO created_at upper bound")] = None,
    multiplier: Annotated[str, typer.Option("--multiplier", help="Decimal policy multiplier from 1.0 to 10.0")] = "3",
    validity_days_default: Annotated[
        int | None,
        typer.Option("--validity-days-default", help="Optional default validity window for future keys"),
    ] = None,
    email_delivery_mode_default: Annotated[
        str | None,
        typer.Option("--email-delivery-mode-default", help="Optional default email mode: none or pending"),
    ] = None,
    confirm_create_template: Annotated[
        bool,
        typer.Option("--confirm-create-template", help="Confirm durable template creation"),
    ] = False,
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason")] = "",
    json_output: Annotated[bool, typer.Option("--json", help="Output machine-readable safe JSON")] = False,
) -> None:
    """Create a versioned key template from a reviewed calibration proposal."""
    try:
        result = run_async(
            _create_from_calibration(
                gateway_key_id=gateway_key_id,
                name=name,
                description=description,
                start_at=start_at,
                end_at=end_at,
                multiplier=multiplier,
                validity_days_default=validity_days_default,
                email_delivery_mode_default=email_delivery_mode_default,
                confirm_create_template=confirm_create_template,
                reason=reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _result_dict(result)
    if json_output:
        emit_json(payload)
        return
    _emit_human_result(result)


def _result_dict(result: KeyTemplateCreationResult) -> dict[str, object]:
    revision = result.revision
    return {
        "template": {
            "id": result.template.id,
            "name": result.template.name,
            "status": result.template.status,
            "current_revision_id": result.template.current_revision_id,
        },
        "revision": {
            "id": revision.id,
            "revision_number": revision.revision_number,
            "source_type": revision.source_type,
            "source_calibration_gateway_key_id": revision.source_calibration_gateway_key_id,
            "source_time_window_start": revision.source_time_window_start,
            "source_time_window_end": revision.source_time_window_end,
            "source_multiplier": revision.source_multiplier,
            "allowed_endpoints": revision.allowed_endpoints,
            "allowed_models": revision.allowed_models,
            "allowed_providers": revision.allowed_providers,
            "allowed_hosted_capabilities": revision.allowed_hosted_capabilities,
            "hosted_capabilities_requiring_review": revision.hosted_capabilities_requiring_review,
            "request_limit_total": revision.request_limit_total,
            "token_limit_total": revision.token_limit_total,
            "cost_limit_eur": revision.cost_limit_eur,
            "warnings": _snapshot_warnings(revision.template_snapshot),
        },
        "audit_log_id": result.audit_log.id,
        "message": "Template created. No participant keys were created.",
    }


def _snapshot_warnings(snapshot: dict[str, object]) -> list[object]:
    warnings = snapshot.get("warnings") if isinstance(snapshot, dict) else None
    return list(warnings) if isinstance(warnings, list) else []


def _emit_human_result(result: KeyTemplateCreationResult) -> None:
    revision = result.revision
    typer.echo("Key template created from reviewed calibration proposal")
    typer.echo(f"template_id: {result.template.id}")
    typer.echo(f"template_name: {result.template.name}")
    typer.echo(f"revision_id: {revision.id}")
    typer.echo(f"revision_number: {revision.revision_number}")
    typer.echo(f"source_calibration_gateway_key_id: {revision.source_calibration_gateway_key_id}")
    typer.echo(f"allowed_endpoints: {', '.join(revision.allowed_endpoints) or 'none'}")
    typer.echo(f"allowed_models: {', '.join(revision.allowed_models) or 'none'}")
    typer.echo(f"allowed_providers: {', '.join(revision.allowed_providers) or 'none'}")
    typer.echo(f"request_limit_total: {revision.request_limit_total}")
    typer.echo(f"token_limit_total: {revision.token_limit_total}")
    typer.echo(f"cost_limit_eur: {revision.cost_limit_eur or 'unknown'}")
    if revision.hosted_capabilities_requiring_review:
        typer.echo(
            "hosted_capabilities_requiring_review: "
            + ", ".join(revision.hosted_capabilities_requiring_review)
        )
    warnings = _snapshot_warnings(revision.template_snapshot)
    if warnings:
        typer.echo("")
        typer.echo("Warnings")
        for warning in warnings:
            typer.echo(f"- {warning}")
    typer.echo("")
    typer.echo("No participant keys were created, and no existing gateway keys were changed.")
