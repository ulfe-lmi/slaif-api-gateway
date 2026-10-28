"""Typer commands for Codex replay reference inspection and maintenance."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    emit_json,
    handle_cli_error,
    run_async,
)
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.codex_replay import CodexReplayReferencesRepository
from slaif_gateway.schemas.codex_replay_maintenance import (
    REPLAY_PLAN_MAX_BYTES,
    ReplayMaintenanceError,
    parse_replay_extend_plan_file,
    parse_replay_scope,
    parse_utc_datetime,
    validate_utc_bounds,
    write_replay_extend_plan_file,
)
from slaif_gateway.services.codex_replay_maintenance import (
    CodexReplayMaintenanceService,
    MAX_REFERENCE_TTL_SECONDS,
    MIN_REFERENCE_TTL_SECONDS,
    ReplayInspectionSummary,
)

app = typer.Typer(help="Inspect retained Codex replay references and apply reviewed expiry extensions")


def _service(session: object) -> CodexReplayMaintenanceService:
    return CodexReplayMaintenanceService(
        repository=CodexReplayReferencesRepository(session),
        audit_repository=AuditRepository(session),
        settings=get_settings(),
    )


ScopeKeyOption = Annotated[
    uuid.UUID | None,
    typer.Option("--key-id", help="Exactly one scope: one gateway key UUID"),
]
ScopeCohortOption = Annotated[
    uuid.UUID | None,
    typer.Option("--cohort-id", help="Exactly one scope: one cohort UUID"),
]
ScopeAllOption = Annotated[
    bool,
    typer.Option("--all-active", help="Exactly one scope: every active key"),
]
CreatedFromOption = Annotated[
    str | None,
    typer.Option("--created-from", help="ISO 8601 UTC lower creation bound (inclusive)"),
]
CreatedUntilOption = Annotated[
    str | None,
    typer.Option("--created-until", help="ISO 8601 UTC upper creation bound (exclusive)"),
]


def _parse_bounds(created_from: str | None, created_until: str | None):
    bounds = (parse_utc_datetime(created_from, field="--created-from"),
              parse_utc_datetime(created_until, field="--created-until"))
    validate_utc_bounds(bounds[0], bounds[1])
    return bounds[0], bounds[1]


def _validate_scope(key_id, cohort_id, all_active):
    return parse_replay_scope(
        key_id=str(key_id) if key_id is not None else None,
        cohort_id=str(cohort_id) if cohort_id is not None else None,
        all_active=all_active,
    )


def _iso(value) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _inspection_payload(summary: ReplayInspectionSummary) -> dict[str, object]:
    return {
        "scope": summary.scope_text,
        "now": _iso(summary.now),
        "configured_ttl_seconds": summary.configured_ttl_seconds,
        "keys": summary.keys,
        "keys_active_or_valid": summary.keys_active_or_valid,
        "references": summary.references,
        "active_references": summary.active_references,
        "expired_references": summary.expired_references,
        "created_min": _iso(summary.created_min),
        "created_max": _iso(summary.created_max),
        "expiry_min": _iso(summary.expiry_min),
        "expiry_max": _iso(summary.expiry_max),
        "per_key": [
            {
                "key_id": str(item.key_id),
                "key_status": item.key_status,
                "references": item.references,
                "active_references": item.active_references,
                "expired_references": item.expired_references,
                "created_min": _iso(item.created_min),
                "created_max": _iso(item.created_max),
                "expiry_min": _iso(item.expiry_min),
                "expiry_max": _iso(item.expiry_max),
            }
            for item in summary.per_key
        ],
        "route_model_groups": [
            {
                "route_id": str(item.route_id),
                "requested_model": item.requested_model,
                "references": item.references,
            }
            for item in summary.route_model_groups
        ],
        "route_model_groups_total": summary.route_model_groups_total,
        "route_model_groups_truncated": summary.route_model_groups_truncated,
        "exclusion_reasons": summary.reasons.as_counts(),
        "note": summary.note,
    }


@app.command("inspect")
def inspect(
    key_id: ScopeKeyOption = None,
    cohort_id: ScopeCohortOption = None,
    all_active: ScopeAllOption = False,
    created_from: CreatedFromOption = None,
    created_until: CreatedUntilOption = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Read-only safe inspection of retained replay references (no writes, no audit)."""
    try:
        scope = _validate_scope(key_id, cohort_id, all_active)
        from_bound, until_bound = _parse_bounds(created_from, created_until)
    except (ReplayMaintenanceError, typer.BadParameter) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    try:
        async def _go():
            async with cli_db_session() as (_, session):
                return await _service(session).inspect_replay_references(
                    scope=scope,
                    created_from=from_bound,
                    created_until=until_bound,
                )

        summary = run_async(_go())
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json(_inspection_payload(summary))
        return
    typer.echo(f"Scope: {summary.scope_text}")
    typer.echo(f"Keys: {summary.keys} ({summary.keys_active_or_valid} active/valid)")
    typer.echo(
        f"References: {summary.references} "
        f"({summary.active_references} active, {summary.expired_references} expired)"
    )
    if summary.references:
        typer.echo(
            f"Created range: {_iso(summary.created_min)} .. {_iso(summary.created_max)}"
        )
        typer.echo(
            f"Expiry range: {_iso(summary.expiry_min)} .. {_iso(summary.expiry_max)}"
        )
        for group in summary.route_model_groups:
            typer.echo(
                f"Route {group.route_id} model={group.requested_model or '-'}: "
                f"{group.references} references"
            )
        if summary.route_model_groups_truncated:
            typer.echo(
                f"(route/model groups truncated at the bounded output limit; "
                f"total distinct routes: {summary.route_model_groups_total})"
            )
    reasons = summary.reasons.as_counts()
    typer.echo(
        "Exclusion/reuse-limit reasons: "
        + ", ".join(f"{name}={count}" for name, count in reasons.items())
    )
    typer.echo(summary.note)


@app.command("extend")
def extend(
    key_id: ScopeKeyOption = None,
    cohort_id: ScopeCohortOption = None,
    all_active: ScopeAllOption = False,
    ttl_seconds: Annotated[
        int | None,
        typer.Option(
            "--ttl-seconds",
            help="Positive lifetime in seconds (1..31536000); omitted uses the configured TTL",
        ),
    ] = None,
    include_expired: Annotated[
        bool,
        typer.Option("--include-expired", help="Explicitly restore explicitly-expired references"),
    ] = False,
    created_from: CreatedFromOption = None,
    created_until: CreatedUntilOption = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Dry-run: write the reviewed plan to a NEW 0600 file"),
    ] = None,
    execute: Annotated[
        Path | None,
        typer.Option("--execute", help="Apply this previously reviewed plan file"),
    ] = None,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Nonblank safe audit reason (required with --execute)"),
    ] = None,
    actor_admin_id: Annotated[
        uuid.UUID | None,
        typer.Option("--actor-admin-id", help="Admin actor UUID for the audit"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Preview or apply a reviewed monotonic expiry extension (created + TTL)."""
    if (output is None) == (execute is None):
        typer.secho(
            "Choose exactly one of --output (dry-run) or --execute <plan>.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        if ttl_seconds is not None and (
            ttl_seconds < MIN_REFERENCE_TTL_SECONDS
            or ttl_seconds > MAX_REFERENCE_TTL_SECONDS
        ):
            raise typer.BadParameter(
                "--ttl-seconds must be within 1..31536000 seconds."
            )
        if execute is not None and not (reason or "").strip():
            raise typer.BadParameter(
                "--reason is required for --execute (nonblank audit reason)."
            )
    except typer.BadParameter as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    if execute is not None:
        try:
            plan = parse_replay_extend_plan_file(execute)
        except ReplayMaintenanceError as exc:
            typer.secho(exc.safe_message, fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc
        payload = {
            "mode": "execute",
            "scope": plan.scope.scope_text,
            "ttl_seconds": plan.ttl_seconds,
            "configured_ttl_seconds": plan.configured_ttl_seconds,
            "ttl_is_configured_default": plan.ttl_seconds
            == plan.configured_ttl_seconds,
            "include_expired": plan.include_expired,
            "selected_keys": plan.selected_keys,
            "eligible_references": plan.eligible_references,
            "exclusion_counts": plan.exclusion_counts,
            "old_expiry_range": [_iso(plan.old_expiry_min), _iso(plan.old_expiry_max)],
            "new_expiry_range": [_iso(plan.new_expiry_min), _iso(plan.new_expiry_max)],
        }
        try:
            async def _apply():
                async with cli_db_session() as (_, session):
                    return await _service(session).apply_replay_extend(
                        plan=plan,
                        reason=reason,
                        actor_admin_id=actor_admin_id,
                    )

            result = run_async(_apply())
        except Exception as exc:  # noqa: BLE001
            handle_cli_error(exc, json_output=json_output)
            return
        payload.update(
            {
                "applied": result.applied,
                "already_applied": result.already_applied,
                "updated_references": result.updated_references,
            }
        )
        if json_output:
            emit_json(payload)
            return
        if result.already_applied:
            typer.echo("Already applied: the reviewed extension is in place (no writes, no audit).")
        elif result.applied:
            typer.echo(
                f"Applied: {result.updated_references} references extended "
                f"(monotonic; original creation times preserved)."
            )
        else:
            typer.echo("No eligible change under the reviewed plan (no writes, no audit).")
        return

    # Dry-run path: resolve exact bounded membership, render the plan, write 0600.
    try:
        scope = _validate_scope(key_id, cohort_id, all_active)
        from_bound, until_bound = _parse_bounds(created_from, created_until)
    except (ReplayMaintenanceError, typer.BadParameter) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    try:
        async def _preview():
            async with cli_db_session() as (_, session):
                service = _service(session)
                return await service.preview_replay_extend(
                    scope=scope,
                    ttl_seconds=ttl_seconds,
                    include_expired=include_expired,
                    created_from=from_bound,
                    created_until=until_bound,
                )

        plan = run_async(_preview())
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    try:
        write_replay_extend_plan_file(output, plan)
    except ReplayMaintenanceError as exc:
        typer.secho(exc.safe_message, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    selected_ttl = plan.ttl_seconds
    payload = {
        "mode": "dry-run",
        "plan_file": str(output),
        "scope": plan.scope.scope_text,
        "ttl_seconds": selected_ttl,
        "configured_ttl_seconds": plan.configured_ttl_seconds,
        "ttl_is_configured_default": selected_ttl == plan.configured_ttl_seconds,
        "include_expired": plan.include_expired,
        "selected_keys": plan.selected_keys,
        "eligible_references": plan.eligible_references,
        "exclusion_counts": plan.exclusion_counts,
        "old_expiry_range": [_iso(plan.old_expiry_min), _iso(plan.old_expiry_max)],
        "new_expiry_range": [_iso(plan.new_expiry_min), _iso(plan.new_expiry_max)],
    }
    if json_output:
        emit_json(payload)
        return
    typer.echo(f"Dry-run plan written: {output} (0600, {REPLAY_PLAN_MAX_BYTES} byte cap)")
    typer.echo(f"Scope: {plan.scope.scope_text}")
    typer.echo(
        f"Selected lifetime: {selected_ttl} s "
        f"(configured default: {plan.configured_ttl_seconds} s)"
    )
    typer.echo(f"Selected keys: {plan.selected_keys}")
    typer.echo(
        f"Eligible references: {plan.eligible_references} "
        f"(include-expired: {str(plan.include_expired).lower()})"
    )
    if plan.eligible_references:
        typer.echo(
            f"Expiry change: {_iso(plan.old_expiry_min)}..{_iso(plan.old_expiry_max)} -> "
            f"{_iso(plan.new_expiry_min)}..{_iso(plan.new_expiry_max)} "
            "(original creation time + selected lifetime, monotonic)"
        )
    typer.echo(
        "Apply with: slaif-gateway codex replay extend --execute <plan> "
        "--reason '<reviewed reason>'"
    )
