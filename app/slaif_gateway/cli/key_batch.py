"""Typer commands for reviewed key-configuration batches (203-a).

``keys batch plan`` previews (READ ONLY) and ``keys batch apply`` applies
the EXISTING supported key-policy/rate changes to the EXACT selected
existing keys (one cohort or an explicit UUID list), atomically with the
existing per-key audits. The CLI parses and formats only: the shared
``KeyBatchService`` owns selection, preview, consistency, and
transaction orchestration; no raw ORM mutations and no duplicated policy
validators live here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import typer

from slaif_gateway.cli import keys as _keys_cli
from slaif_gateway.cli.key_policy_files import read_policy_file
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.schemas.key_configuration import key_configuration_export
from slaif_gateway.schemas.key_batch import (
    KEY_BATCH_MAX_KEYS,
    KEY_BATCH_STATUSES,
    KeyBatchError,
    parse_key_batch_plan_file,
    render_key_batch_plan,
    write_key_batch_plan_file,
)
from slaif_gateway.services.key_batch_service import (
    KeyBatchApplyResult,
    KeyBatchService,
)
from slaif_gateway.services.key_service import KeyService

# Finite recognized credential shapes reused from the existing redaction
# contract (known-shape protection for the plan artifact pathname, not a
# general sanitizer).
from slaif_gateway.utils.redaction import (  # noqa: E402
    _BEARER_PATTERN,
    _GATEWAY_KEY_TEXT_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

_PLAN_PATH_SECRET_SHAPE_PATTERNS = (
    _GATEWAY_KEY_TEXT_PATTERN,
    _BEARER_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

app = typer.Typer(help="Review and apply key-configuration batches")


@asynccontextmanager
async def _batch_runtime() -> AsyncIterator[tuple[KeyService, KeyBatchService]]:
    """Same caller-owned key runtime plus the shared batch service.

    Both operations run inside the ONE caller transaction
    (``session.begin()``): a successful plan exits that read-only
    transaction normally (a no-write transaction may still COMMIT),
    releases its locks, and writes ZERO key/config/audit/material
    state; apply commits only after the whole batch is validated and
    applied, and a failed atomic apply propagates and rolls back all
    changes.
    """
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise _keys_cli.CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    _keys_cli._bootstrap_codex_profile(settings)

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise _keys_cli.CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            keys_repository = GatewayKeysRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
                model_routes_repository=ModelRoutesRepository(session),
            )
            batch_service = KeyBatchService(
                gateway_keys_repository=keys_repository,
                cohorts_repository=CohortsRepository(session),
                key_service=key_service,
            )
            yield key_service, batch_service


def _handle_batch_cli_error(exc: Exception, *, json_output: bool) -> None:
    if isinstance(exc, KeyBatchError):
        message = exc.safe_message
        code = exc.error_code
        if json_output:
            _keys_cli._emit_json({"error": {"code": code, "message": message}})
        else:
            typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    _keys_cli._handle_cli_error(exc, json_output=json_output)


def _parse_selection(
    *,
    cohort_id: str | None,
    key_id: list[str] | None,
    status: list[str] | None,
) -> dict[str, object]:
    """Typed, no-echo selection parsing (safe fixed errors)."""
    key_id_list = list(key_id or [])
    if (cohort_id is None) == (not key_id_list):
        raise typer.BadParameter(
            "Use exactly one selection source: --cohort-id or --key-id."
        )
    statuses: list[str] = []
    for value in status or ():
        if value not in KEY_BATCH_STATUSES:
            raise typer.BadParameter(
                "Each --status must be one of: active, suspended, revoked."
            )
        if value not in statuses:
            statuses.append(value)
    if not statuses:
        statuses = ["active"]
    if cohort_id is not None:
        return {
            "cohort_id": _keys_cli._parse_uuid(cohort_id, field_name="cohort_id"),
            "key_ids": (),
            "statuses": tuple(statuses),
        }
    unique: list[str] = []
    for value in key_id_list:
        text_id = value.strip()
        if text_id in unique:
            raise typer.BadParameter("The key list contains duplicate key IDs.")
        unique.append(text_id)
    if len(unique) > KEY_BATCH_MAX_KEYS:
        raise typer.BadParameter(
            f"The key list may carry at most {KEY_BATCH_MAX_KEYS} key IDs."
        )
    return {
        "cohort_id": None,
        "key_ids": tuple(
            _keys_cli._parse_uuid(value, field_name="key_id") for value in unique
        ),
        "statuses": tuple(statuses),
    }


def _echo_plan_summary(plan_file: Path, plan: Any) -> None:
    document = render_key_batch_plan(plan)
    if plan.selection_kind == "cohort":
        typer.echo(f"selection: cohort {plan.cohort_id}")
    else:
        typer.echo(f"selection: keys {len(plan.key_ids)}")
    typer.echo(f"statuses: {', '.join(plan.statuses)}")
    typer.echo(f"selected: {plan.selected_count}")
    typer.echo(f"changed: {plan.changed_count}")
    typer.echo(f"unchanged: {plan.unchanged_count}")
    typer.echo(f"excluded_by_status: {len(plan.excluded_by_status)}")
    typer.echo(f"planned_at: {plan.planned_at}")
    for entry in document["excluded_by_status"]:
        typer.echo(f"excluded: {entry['key_id']} ({entry['status']})")
    for key in plan.keys:
        if key.changes:
            typer.echo(f"key {key.key_id}: {len(key.changes)} changed field(s)")
            for change in key.changes:
                typer.echo(
                    f"  - {change['field']}: {change['before']} -> {change['after']}"
                )
        else:
            typer.echo(f"key {key.key_id}: unchanged")
    typer.echo(f"plan_file: {plan_file}")


def _echo_apply_summary(result: KeyBatchApplyResult) -> None:
    typer.echo(f"status: {result.status}")
    typer.echo(f"selected: {result.selected_count}")
    typer.echo(f"changed: {result.changed_count}")
    typer.echo(f"unchanged: {result.unchanged_count}")
    for key_id in result.key_ids:
        typer.echo(f"key: {key_id}")


def _refuse_credential_shape_path(path: Path) -> None:
    """Finite known-shape guard on the plan artifact PATHNAME.

    The plan file name becomes a persisted artifact and is echoed in the
    command output; a recognized credential shape in the path is refused
    with a fixed safe error BEFORE any write or output (known-shape
    protection, not a general sanitizer; normal paths are unchanged).
    """
    if any(pattern.search(str(path)) for pattern in _PLAN_PATH_SECRET_SHAPE_PATTERNS):
        raise typer.BadParameter(
            "The plan file path contains a recognized credential shape."
        )


def _refuse_credential_shape_policy(configuration: Any) -> None:
    """Finite known-shape guard on the PARSED policy document.

    A recognized credential shape anywhere in the policy content (values
    or field names) is refused with a fixed safe error BEFORE projection
    or validation (whose shared messages may reference requested values)
    and before any plan artifact write (known-shape protection, not a
    general sanitizer; normal policy values are unchanged).
    """
    document = key_configuration_export(configuration)

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            if any(
                pattern.search(value) for pattern in _PLAN_PATH_SECRET_SHAPE_PATTERNS
            ):
                raise typer.BadParameter(
                    "The policy file contains a recognized credential shape."
                )
        elif isinstance(value, dict):
            for key, item in value.items():
                _walk(key)
                _walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    _walk(document)


@app.command("plan")
def plan(
    cohort_id: Annotated[
        str | None, typer.Option("--cohort-id", help="Cohort UUID to select")
    ] = None,
    key_id: Annotated[
        list[str] | None,
        typer.Option("--key-id", help="Exact gateway key UUID (repeatable)"),
    ] = None,
    status: Annotated[
        list[str] | None,
        typer.Option(
            "--status", help="Persisted status filter (repeatable; default: active)"
        ),
    ] = None,
    policy_file: Annotated[
        Path | None,
        typer.Option("--policy-file", help="Version-1 key-configuration policy file"),
    ] = None,
    plan_file: Annotated[
        Path | None,
        typer.Option("--plan-file", help="NEW plan output file (never overwritten)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Preview (READ ONLY) and save a reviewed key-configuration batch plan."""
    try:
        selection = _parse_selection(
            cohort_id=cohort_id, key_id=key_id, status=status
        )
        if policy_file is None:
            raise typer.BadParameter("The --policy-file option is required.")
        if plan_file is None:
            raise typer.BadParameter("The --plan-file option is required.")
        _refuse_credential_shape_path(plan_file)
        configuration = read_policy_file(policy_file)
        _refuse_credential_shape_policy(configuration)
    except Exception as exc:  # noqa: BLE001
        _handle_batch_cli_error(exc, json_output=json_output)
        return

    try:
        plan_result = _keys_cli._run_async(_batch_plan(selection, configuration))
        write_key_batch_plan_file(plan_file, plan_result)
    except Exception as exc:  # noqa: BLE001
        _handle_batch_cli_error(exc, json_output=json_output)
        return

    if json_output:
        _keys_cli._emit_json(
            {"plan_file": str(plan_file), "plan": render_key_batch_plan(plan_result)}
        )
        return
    _echo_plan_summary(plan_file, plan_result)


async def _batch_plan(
    selection: dict[str, object], configuration: Any
) -> Any:
    async with _batch_runtime() as (_, batch_service):
        return await batch_service.plan(
            cohort_id=selection["cohort_id"],
            key_ids=selection["key_ids"],
            statuses=selection["statuses"],
            policy=configuration,
        )


@app.command("apply")
def apply(
    plan_file: Annotated[
        Path | None,
        typer.Option("--plan-file", help="Reviewed batch plan file"),
    ] = None,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Required bounded audit reason")
    ] = None,
    actor_admin_id: Annotated[
        str | None, typer.Option("--actor-admin-id", help="Acting admin UUID")
    ] = None,
    confirm_external_tool_fenced: Annotated[
        bool,
        typer.Option(
            "--confirm-external-tool-fenced",
            help=(
                "Fresh confirmation required to apply a fenced external-tool "
                "target (a saved plan never carries confirmation authority)"
            ),
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Apply a reviewed batch plan atomically (fresh reason/confirmation).

    The saved plan grants no authority: the fresh bounded reason and
    the fresh fenced confirmation are the operator's apply-time controls.
    """
    try:
        actor = (
            _keys_cli._parse_uuid(actor_admin_id, field_name="actor_admin_id")
            if actor_admin_id
            else None
        )
        if plan_file is None:
            raise typer.BadParameter("The --plan-file option is required.")
        if reason is None:
            raise typer.BadParameter("The --reason option is required.")
        plan = parse_key_batch_plan_file(plan_file)
    except Exception as exc:  # noqa: BLE001
        _handle_batch_cli_error(exc, json_output=json_output)
        return

    try:
        result = _keys_cli._run_async(
            _batch_apply(
                plan,
                reason=reason,
                actor_admin_id=actor,
                confirm_external_tool_fenced=confirm_external_tool_fenced,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_batch_cli_error(exc, json_output=json_output)
        return

    if json_output:
        _keys_cli._emit_json(
            {
                "status": result.status,
                "selected_count": result.selected_count,
                "changed_count": result.changed_count,
                "unchanged_count": result.unchanged_count,
                "key_ids": list(result.key_ids),
            }
        )
        return
    _echo_apply_summary(result)


async def _batch_apply(
    plan: Any,
    *,
    reason: str,
    actor_admin_id: Any,
    confirm_external_tool_fenced: bool,
) -> KeyBatchApplyResult:
    async with _batch_runtime() as (_, batch_service):
        return await batch_service.apply(
            plan=plan,
            reason=reason,
            actor_admin_id=actor_admin_id,
            confirm_external_tool_fenced=confirm_external_tool_fenced,
        )
