"""Typer commands for quota reservation repair operations."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    CliError,
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_uuid,
    require_positive_limit,
    run_async,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.reconciliation import (
    ProviderCompletedReconciliationCandidate,
    ProviderCompletedReconciliationResult,
    ProviderCompletedReconciliationSummary,
    ReservationReconciliationResult,
    ReservationReconciliationSummary,
    StaleReservationCandidate,
)
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService

app = typer.Typer(help="Inspect and repair quota reservations")


def _service(session) -> ReservationReconciliationService:
    return ReservationReconciliationService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
        usage_ledger_repository=UsageLedgerRepository(session),
        audit_repository=AuditRepository(session),
    )


async def _list_expired_reservations(*, limit: int) -> list[StaleReservationCandidate]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_expired_pending_reservations(limit=limit)


async def _list_provider_completed_recovery(
    *,
    limit: int,
    provider: str | None,
    model: str | None,
    gateway_key_id: uuid.UUID | None,
) -> list[ProviderCompletedReconciliationCandidate]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_provider_completed_recovery_rows(
            limit=limit,
            provider=provider,
            model=model,
            gateway_key_id=gateway_key_id,
        )


async def _reconcile_expired_reservations(
    *,
    limit: int,
    dry_run: bool,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> ReservationReconciliationSummary:
    async with cli_db_session() as (_, session):
        return await _service(session).reconcile_expired_pending_reservations(
            limit=limit,
            dry_run=dry_run,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


async def _reconcile_reservation(
    *,
    reservation_id: uuid.UUID,
    dry_run: bool,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> ReservationReconciliationResult:
    async with cli_db_session() as (_, session):
        return await _service(session).reconcile_expired_pending_reservation(
            reservation_id,
            dry_run=dry_run,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


async def _reconcile_provider_completed(
    *,
    usage_ledger_id: uuid.UUID | None,
    reservation_id: uuid.UUID | None,
    limit: int,
    dry_run: bool,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> ProviderCompletedReconciliationResult | ProviderCompletedReconciliationSummary:
    async with cli_db_session() as (_, session):
        service = _service(session)
        if usage_ledger_id is not None or reservation_id is not None:
            return await service.reconcile_provider_completed_recovery(
                usage_ledger_id=usage_ledger_id,
                reservation_id=reservation_id,
                dry_run=dry_run,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
        return await service.reconcile_provider_completed_recovery_rows(
            limit=limit,
            dry_run=dry_run,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


@app.callback()
def quota() -> None:
    """Inspect and repair quota reservations."""


@app.command("list-expired-reservations")
def list_expired_reservations(
    limit: Annotated[int, typer.Option("--limit", help="Maximum expired pending reservations to list")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List expired pending reservations without mutating state."""
    try:
        require_positive_limit(limit)
        rows = run_async(_list_expired_reservations(limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_row_dict(row) for row in rows]
    if json_output:
        emit_json({"expired_reservations": payload})
        return
    if not rows:
        typer.echo("No expired pending reservations found.")
        return
    _emit_candidates(rows)


@app.command("list-provider-completed-recovery")
def list_provider_completed_recovery(
    limit: Annotated[int, typer.Option("--limit", help="Maximum recovery rows to list")] = 100,
    provider: Annotated[str | None, typer.Option("--provider", help="Filter by provider")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Filter by requested or resolved model")] = None,
    key_id: Annotated[str | None, typer.Option("--key-id", help="Filter by gateway key UUID")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List provider-completed finalization-failed rows without mutating state."""
    try:
        require_positive_limit(limit)
        parsed_key_id = parse_uuid(key_id, field_name="key_id") if key_id else None
        rows = run_async(
            _list_provider_completed_recovery(
                limit=limit,
                provider=provider,
                model=model,
                gateway_key_id=parsed_key_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_row_dict(row) for row in rows]
    if json_output:
        emit_json({"provider_completed_recovery": payload})
        return
    if not rows:
        typer.echo("No provider-completed recovery rows found.")
        return
    _emit_provider_completed_candidates(rows)


@app.command("reconcile-expired-reservations")
def reconcile_expired_reservations(
    limit: Annotated[int, typer.Option("--limit", help="Maximum expired pending reservations to reconcile")] = 100,
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute", help="Preview or execute reconciliation")] = True,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Admin actor UUID for audit")] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit note")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Reconcile expired pending reservations. Defaults to dry-run."""
    try:
        require_positive_limit(limit)
        actor_id = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
        summary = run_async(
            _reconcile_expired_reservations(
                limit=limit,
                dry_run=dry_run,
                actor_admin_id=actor_id,
                reason=reason,
            )
        )
        if summary.candidate_count == 0:
            raise CliError("No expired pending reservations found.")
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _summary_dict(summary)
    if json_output:
        emit_json(payload)
        return
    _emit_summary(summary)


@app.command("reconcile-reservation")
def reconcile_reservation(
    reservation_id: Annotated[str, typer.Argument(help="Quota reservation UUID")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute", help="Preview or execute reconciliation")] = True,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Admin actor UUID for audit")] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit note")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Reconcile one expired pending reservation. Defaults to dry-run."""
    try:
        parsed_reservation_id = parse_uuid(reservation_id, field_name="reservation_id")
        actor_id = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
        result = run_async(
            _reconcile_reservation(
                reservation_id=parsed_reservation_id,
                dry_run=dry_run,
                actor_admin_id=actor_id,
                reason=reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _row_dict(result)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("reconcile-provider-completed")
def reconcile_provider_completed(
    usage_ledger_id: Annotated[str | None, typer.Option("--usage-ledger-id", help="Usage ledger UUID")] = None,
    reservation_id: Annotated[str | None, typer.Option("--reservation-id", help="Quota reservation UUID")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum recovery rows for batch mode")] = 100,
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute", help="Preview or execute reconciliation")] = True,
    actor_admin_id: Annotated[str | None, typer.Option("--actor-admin-id", help="Admin actor UUID for audit")] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit note")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Reconcile provider-completed finalization-failed rows. Defaults to dry-run."""
    try:
        require_positive_limit(limit)
        parsed_usage_ledger_id = (
            parse_uuid(usage_ledger_id, field_name="usage_ledger_id") if usage_ledger_id else None
        )
        parsed_reservation_id = (
            parse_uuid(reservation_id, field_name="reservation_id") if reservation_id else None
        )
        if parsed_usage_ledger_id is not None and parsed_reservation_id is not None:
            raise CliError("Provide only one of --usage-ledger-id or --reservation-id")
        actor_id = parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
        if not dry_run:
            typer.secho(
                "Executing provider-completed recovery reconciliation using stored usage/cost metadata.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        result = run_async(
            _reconcile_provider_completed(
                usage_ledger_id=parsed_usage_ledger_id,
                reservation_id=parsed_reservation_id,
                limit=limit,
                dry_run=dry_run,
                actor_admin_id=actor_id,
                reason=reason,
            )
        )
        if isinstance(result, ProviderCompletedReconciliationSummary) and result.candidate_count == 0:
            raise CliError("No provider-completed recovery rows found.")
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _provider_completed_payload(result)
    if json_output:
        emit_json(payload)
        return
    if isinstance(result, ProviderCompletedReconciliationSummary):
        _emit_provider_completed_summary(result)
    else:
        echo_kv(payload)


def _row_dict(
    row: (
        StaleReservationCandidate
        | ReservationReconciliationResult
        | ProviderCompletedReconciliationCandidate
        | ProviderCompletedReconciliationResult
    ),
) -> dict[str, object]:
    return asdict(row)


def _summary_dict(summary: ReservationReconciliationSummary) -> dict[str, object]:
    payload = asdict(summary)
    payload["results"] = [_row_dict(row) for row in summary.results]
    return payload


def _provider_completed_payload(
    result: ProviderCompletedReconciliationResult | ProviderCompletedReconciliationSummary,
) -> dict[str, object]:
    if isinstance(result, ProviderCompletedReconciliationSummary):
        payload = asdict(result)
        payload["results"] = [_row_dict(row) for row in result.results]
        return payload
    return _row_dict(result)


def _emit_candidates(rows: list[StaleReservationCandidate]) -> None:
    typer.echo(
        "reservation_id\tgateway_key_id\trequest_id\tstatus\treserved_cost_eur\t"
        "reserved_tokens\treserved_requests\texpires_at"
    )
    for row in rows:
        typer.echo(
            "\t".join(
                (
                    str(row.reservation_id),
                    str(row.gateway_key_id),
                    row.request_id,
                    row.status,
                    str(row.reserved_cost_eur),
                    str(row.reserved_tokens),
                    str(row.reserved_requests),
                    row.expires_at.isoformat(),
                )
            )
        )


def _emit_provider_completed_candidates(rows: list[ProviderCompletedReconciliationCandidate]) -> None:
    typer.echo(
        "usage_ledger_id\treservation_id\tgateway_key_id\trequest_id\tprovider\t"
        "requested_model\tresolved_model\tendpoint\ttotal_tokens\tactual_cost_eur\trecovery_state"
    )
    for row in rows:
        typer.echo(
            "\t".join(
                (
                    str(row.usage_ledger_id),
                    str(row.reservation_id),
                    str(row.gateway_key_id),
                    row.request_id,
                    row.provider,
                    row.requested_model or "",
                    row.resolved_model or "",
                    row.endpoint,
                    str(row.total_tokens),
                    str(row.actual_cost_eur),
                    row.recovery_state,
                )
            )
        )


def _emit_summary(summary: ReservationReconciliationSummary) -> None:
    echo_kv(
        {
            "checked_count": summary.checked_count,
            "candidate_count": summary.candidate_count,
            "reconciled_count": summary.reconciled_count,
            "skipped_count": summary.skipped_count,
            "dry_run": summary.dry_run,
        }
    )
    if not summary.results:
        typer.echo("No expired pending reservations found.")
        return
    typer.echo("")
    for index, row in enumerate(summary.results):
        if index:
            typer.echo("")
        echo_kv(_row_dict(row))


def _emit_provider_completed_summary(summary: ProviderCompletedReconciliationSummary) -> None:
    echo_kv(
        {
            "checked_count": summary.checked_count,
            "candidate_count": summary.candidate_count,
            "reconciled_count": summary.reconciled_count,
            "skipped_count": summary.skipped_count,
            "dry_run": summary.dry_run,
        }
    )
    if not summary.results:
        typer.echo("No provider-completed recovery rows found.")
        return
    typer.echo("")
    for index, row in enumerate(summary.results):
        if index:
            typer.echo("")
        echo_kv(_row_dict(row))
