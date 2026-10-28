"""Typer commands for model route metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    parse_uuid,
    require_positive_limit,
    run_async,
)
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import ModelRoute
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.model_route_service import CHAT_COMPLETIONS_ENDPOINT, ModelRouteService
from slaif_gateway.services.external_tool_policy_contract import (
    parse_route_external_tool_policy,
    strict_route_policy,
)
from slaif_gateway.cli.provider_route_files import (
    read_capabilities_file,
    read_route_plan_file,
    write_route_plan_file,
)
from slaif_gateway.schemas.provider_route_configuration import (
    CapabilityPatch,
)
from slaif_gateway.services.provider_route_configuration import (
    contains_known_secret_shape,
    execute_route_update_plan,
    preview_route_update_for_route,
    validate_route_creation_candidate,
)
from slaif_gateway.services.route_import import (
    build_route_import_execution_plan,
    classify_route_import_preview,
    detect_route_import_format,
    execute_route_import_plan,
    parse_route_import_csv,
    parse_route_import_json,
    parse_route_import_tsv,
    provider_refs_from_rows,
    route_import_execution_result_to_dict,
    route_import_preview_to_dict,
    validate_route_import_rows,
)
from slaif_gateway.utils.redaction import redact_text

app = typer.Typer(help="Manage model routes")


def _safe_route_dict(row: ModelRoute) -> dict[str, object]:
    capabilities = dict(row.capabilities or {})
    parsed_external = parse_route_external_tool_policy(
        capabilities.get("external_tools"),
        ceilings=get_settings().get_external_tool_operator_ceilings(),
    )
    external_policy = (
        parsed_external.policy
        if parsed_external.valid and parsed_external.policy is not None
        else strict_route_policy()
    )
    if "external_tools" in capabilities:
        capabilities["external_tools"] = external_policy.to_metadata()
    return {
        "id": row.id,
        "requested_model": row.requested_model,
        "match_type": row.match_type,
        "endpoint": row.endpoint,
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "priority": row.priority,
        "enabled": row.enabled,
        "visible_in_models": row.visible_in_models,
        "supports_streaming": row.supports_streaming,
        "capabilities": capabilities,
        "external_tool_policy": external_policy.to_metadata(),
        "external_tool_runtime_status": "openai_web_search_fenced_only; other_hosted_families_denied",
        "notes": redact_text(row.notes) if row.notes else row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _service(session) -> ModelRouteService:
    return ModelRouteService(
        model_routes_repository=ModelRoutesRepository(session),
        audit_repository=AuditRepository(session),
        external_tool_ceilings=get_settings().get_external_tool_operator_ceilings(),
    )


async def _add_route(
    *,
    requested_model: str,
    match_type: str,
    provider: str,
    upstream_model: str | None,
    priority: int,
    visible_in_models: bool,
    enabled: bool,
    notes: str | None,
    endpoint: str,
    supports_streaming: bool,
    capabilities: dict[str, object] | None,
    reason: str | None,
    actor_admin_id,
) -> ModelRoute:
    async with cli_db_session() as (settings, session):
        # 199-b R4: complete pure configuration validation BEFORE the new
        # route is stored (provider must exist; canonical merged candidate
        # validated against the provider's actual kind/configuration with
        # the ACTUAL installation ceilings and configured profile dir).
        await validate_route_creation_candidate(
            session,
            requested_model=requested_model,
            match_type=match_type,
            provider=provider,
            upstream_model=upstream_model,
            priority=priority,
            visible_in_models=visible_in_models,
            enabled=enabled,
            supports_streaming=supports_streaming,
            notes=notes,
            endpoint=endpoint,
            capabilities=capabilities,
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        return await _service(session).create_model_route(
            requested_model=requested_model,
            match_type=match_type,
            provider=provider,
            upstream_model=upstream_model,
            priority=priority,
            visible_in_models=visible_in_models,
            enabled=enabled,
            notes=notes,
            endpoint=endpoint,
            supports_streaming=supports_streaming,
            capabilities=capabilities,
            reason=reason,
            actor_admin_id=actor_admin_id,
        )


async def _list_routes(
    *,
    provider: str | None,
    enabled_only: bool,
    visible_only: bool,
    limit: int,
) -> list[ModelRoute]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_model_routes(
            provider=provider,
            enabled_only=enabled_only,
            visible_only=visible_only,
            limit=limit,
        )


async def _show_route(route_id: str) -> ModelRoute:
    parsed_route_id = parse_uuid(route_id, field_name="route_id")
    async with cli_db_session() as (_, session):
        return await _service(session).get_model_route(parsed_route_id)


async def _set_route_enabled(route_id: str, *, enabled: bool) -> ModelRoute:
    parsed_route_id = parse_uuid(route_id, field_name="route_id")
    async with cli_db_session() as (_, session):
        return await _service(session).set_model_route_enabled(parsed_route_id, enabled=enabled)


async def _preview_route_update_plan(route_id: str, **edits: object):
    async with cli_db_session() as (settings, session):
        return await preview_route_update_for_route(
            session,
            route_id,
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
            **edits,
        )


async def _execute_route_update_plan(
    route_id: str, plan, *, reason: str, actor_admin_id: object
) -> ModelRoute:
    async with cli_db_session() as (settings, session):
        return await execute_route_update_plan(
            session,
            plan,
            reason=reason,
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
            actor_admin_id=actor_admin_id,
        )


def _parse_bool_capability_flags(
    entries: list[str] | None, *, flag: str
) -> dict[str, bool] | None:
    """Parse repeatable NAME=true|false capability flags (fixed errors)."""
    if not entries:
        return None
    parsed: dict[str, bool] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if not sep or not name.strip() or value not in {"true", "false"}:
            raise typer.BadParameter(f"{flag} must be NAME=true or NAME=false.")
        parsed[name.strip()] = value == "true"
    return parsed


async def _preview_route_import(
    *,
    rows: list[dict[str, object]],
) -> object:
    async with cli_db_session() as (_, session):
        providers = await ProviderConfigsRepository(session).list_provider_configs(limit=1000)
        preview = validate_route_import_rows(
            rows,
            provider_configs=provider_refs_from_rows(providers),
            max_rows=max(len(rows), 1),
            external_tool_ceilings=get_settings().get_external_tool_operator_ceilings(),
        )
        valid_rows = [row for row in preview.rows if row.status == "valid"]
        if not valid_rows:
            return route_import_preview_to_dict(preview)

        route_repository = ModelRoutesRepository(session)
        existing_by_row: dict[int, list[object]] = {}
        for row in valid_rows:
            if not row.requested_model or not row.match_type or not row.endpoint:
                continue
            existing_by_row[row.row_number] = await route_repository.list_model_routes(
                endpoint=row.endpoint,
                limit=1000,
            )
        return classify_route_import_preview(preview, existing_routes_by_row=existing_by_row)


async def _execute_route_import(
    *,
    rows: list[dict[str, object]],
    actor_admin_id: str | None,
    reason: str,
) -> dict[str, object]:
    preview = await _preview_route_import(rows=rows)
    plan = build_route_import_execution_plan(preview)
    if not plan.executable:
        raise ValueError(
            "Route import execution is blocked; "
            f"{plan.blocked_count} of {plan.total_rows} rows are not executable. "
            "Run --dry-run to inspect invalid, duplicate, update, or conflict rows."
        )

    parsed_actor_id = (
        parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
    )
    async with cli_db_session() as (_, session):
        result = await execute_route_import_plan(
            plan,
            model_route_service=_service(session),
            actor_admin_id=parsed_actor_id,
            reason=reason,
        )
    payload = route_import_execution_result_to_dict(result)
    payload.update(
        {
            "dry_run": False,
            "valid_count": preview.valid_count,
            "invalid_count": preview.invalid_count,
        }
    )
    return payload


def _resolve_import_mode(
    *,
    dry_run: bool,
    execute: bool,
    confirm_import: bool,
    reason: str | None,
) -> str:
    if dry_run and execute:
        raise ValueError("Pass either --dry-run or --execute, not both.")
    if confirm_import and not execute:
        raise ValueError("--confirm-import requires --execute.")
    if execute and not confirm_import:
        raise ValueError("--execute requires --confirm-import.")
    if execute and not (reason or "").strip():
        raise ValueError("--reason is required with --execute.")
    if not dry_run and not execute:
        raise ValueError(
            "Pass --dry-run for preview or --execute --confirm-import --reason to write rows."
        )
    return "execute" if execute else "dry_run"


@app.callback()
def routes() -> None:
    """Manage model routes."""


@app.command("add")
def add(
    requested_model: Annotated[
        str,
        typer.Option("--requested-model", "--pattern", help="Requested model or route pattern"),
    ],
    match_type: Annotated[str, typer.Option("--match-type", help="exact, prefix, or glob")],
    provider: Annotated[str, typer.Option("--provider", help="Provider name")],
    upstream_model: Annotated[
        str | None, typer.Option("--upstream-model", help="Provider model")
    ] = None,
    priority: Annotated[int, typer.Option("--priority", help="Lower values win")] = 100,
    visible_in_models: Annotated[
        bool,
        typer.Option("--visible/--hidden", help="Expose through /v1/models"),
    ] = True,
    enabled: Annotated[
        bool | None,
        typer.Option(
            "--enabled/--disabled",
            help="Explicitly enable the route; omitted with --capabilities-file stays DISABLED",
        ),
    ] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="Endpoint path or chat.completions alias"),
    ] = CHAT_COMPLETIONS_ENDPOINT,
    supports_streaming: Annotated[
        bool,
        typer.Option("--streaming/--no-streaming", help="Allow streaming for this route"),
    ] = True,
    capabilities_file: Annotated[
        Path | None,
        typer.Option(
            "--capabilities-file",
            help="Strict JSON file with a COMPLETE capabilities document",
        ),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Admin actor UUID for audit"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create a model route (capabilities-file preparation defaults DISABLED)."""
    if contains_known_secret_shape(notes):
        raise typer.BadParameter(
            "--notes: value must not contain recognized credential patterns."
        )
    settings = get_settings()
    capabilities = (
        read_capabilities_file(
            capabilities_file,
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        if capabilities_file is not None
        else None
    )
    actor = (
        parse_uuid(actor_admin_id, field_name="actor-admin-id")
        if actor_admin_id is not None
        else None
    )
    # Deliberate 199 default: a capabilities-file preparation stays DISABLED
    # unless the operator explicitly chooses --enabled; flag-free route-add
    # keeps the historical enabled default.
    effective_enabled = enabled if enabled is not None else (
        False if capabilities_file is not None else True
    )
    try:
        row = run_async(
            _add_route(
                requested_model=requested_model,
                match_type=match_type,
                provider=provider,
                upstream_model=upstream_model,
                priority=priority,
                visible_in_models=visible_in_models,
                enabled=effective_enabled,
                notes=notes,
                endpoint=endpoint,
                supports_streaming=supports_streaming,
                capabilities=capabilities,
                reason=reason,
                actor_admin_id=actor,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_routes(
    provider: Annotated[str | None, typer.Option("--provider", help="Provider filter")] = None,
    enabled_only: Annotated[
        bool, typer.Option("--enabled-only", help="Only enabled routes")
    ] = False,
    visible_only: Annotated[
        bool, typer.Option("--visible-only", help="Only /v1/models visible routes")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List model routes."""
    require_positive_limit(limit)
    try:
        rows = run_async(
            _list_routes(
                provider=provider,
                enabled_only=enabled_only,
                visible_only=visible_only,
                limit=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_route_dict(row) for row in rows]
    if json_output:
        emit_json({"routes": payload})
        return
    if not payload:
        typer.echo("No routes found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one model route."""
    try:
        row = run_async(_show_route(route_id))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("update")
def update(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    reason: Annotated[
        str | None, typer.Option("--reason", help="Required audit reason for --execute")
    ] = None,
    dry_run: Annotated[
        Path | None,
        typer.Option(
            "--dry-run",
            help="READ-ONLY: write the reviewed plan to this NEW file",
        ),
    ] = None,
    execute: Annotated[
        Path | None,
        typer.Option("--execute", help="Apply the reviewed plan file in one transaction"),
    ] = None,
    # Typed partial capability leaves (dry-run only).
    codex_context_window_tokens: Annotated[
        int | None, typer.Option("--codex-context-window-tokens")
    ] = None,
    codex_default_max_output_tokens: Annotated[
        int | None, typer.Option("--codex-default-max-output-tokens")
    ] = None,
    codex_max_output_tokens: Annotated[
        int | None, typer.Option("--codex-max-output-tokens")
    ] = None,
    media_image_tokens: Annotated[int | None, typer.Option("--media-image-tokens")] = None,
    media_video_tokens: Annotated[int | None, typer.Option("--media-video-tokens")] = None,
    media_video_frames: Annotated[int | None, typer.Option("--media-video-frames")] = None,
    chat_capability: Annotated[
        list[str] | None,
        typer.Option("--chat-capability", help="NAME=true|false; repeatable"),
    ] = None,
    responses_capability: Annotated[
        list[str] | None,
        typer.Option("--responses-capability", help="NAME=true|false; repeatable"),
    ] = None,
    completion_service_profile: Annotated[
        str | None,
        typer.Option("--completion-service-profile", help="Available data profile ID"),
    ] = None,
    clear_completion_service: Annotated[
        bool,
        typer.Option("--clear-completion-service", help="Remove the profile selector"),
    ] = False,
    # Typed route fields (dry-run only). Omitted fields are preserved.
    requested_model: Annotated[
        str | None, typer.Option("--requested-model", help="New requested model")
    ] = None,
    match_type: Annotated[
        str | None, typer.Option("--match-type", help="New match type: exact, prefix, or glob")
    ] = None,
    endpoint: Annotated[
        str | None, typer.Option("--endpoint", help="New endpoint path or chat.completions alias")
    ] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="New provider slug")
    ] = None,
    upstream_model: Annotated[
        str | None, typer.Option("--upstream-model", help="New upstream model")
    ] = None,
    priority: Annotated[int | None, typer.Option("--priority", help="New priority (lower wins)")] = None,
    visible_in_models: Annotated[
        bool | None, typer.Option("--visible/--hidden", help="New /v1/models visibility")
    ] = None,
    supports_streaming: Annotated[
        bool | None, typer.Option("--streaming/--no-streaming", help="New streaming flag")
    ] = None,
    notes: Annotated[
        str | None, typer.Option("--notes", help="Replace administrative notes")
    ] = None,
    clear_notes: Annotated[
        bool, typer.Option("--clear-notes", help="Clear administrative notes to empty")
    ] = False,
    capabilities_file: Annotated[
        Path | None,
        typer.Option(
            "--capabilities-file",
            help="Strict JSON file with a COMPLETE replacement capabilities document",
        ),
    ] = None,
    actor_admin_id: Annotated[
        str | None, typer.Option("--actor-admin-id", help="Admin actor UUID for audit")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Update one route through a reviewed two-step plan (dry-run then execute)."""
    if dry_run is None and execute is None:
        raise typer.BadParameter("Choose --dry-run PATH or --execute PATH.")
    if dry_run is not None and execute is not None:
        raise typer.BadParameter("Choose either --dry-run or --execute, not both.")
    actor = (
        parse_uuid(actor_admin_id, field_name="actor-admin-id")
        if actor_admin_id is not None
        else None
    )

    codex_patch: dict[str, int] = {}
    if codex_context_window_tokens is not None:
        codex_patch["context_window_tokens"] = codex_context_window_tokens
    if codex_default_max_output_tokens is not None:
        codex_patch["default_max_output_tokens"] = codex_default_max_output_tokens
    if codex_max_output_tokens is not None:
        codex_patch["max_output_tokens"] = codex_max_output_tokens
    media_patch: dict[str, int] = {}
    if media_image_tokens is not None:
        media_patch["image_tokens"] = media_image_tokens
    if media_video_tokens is not None:
        media_patch["video_tokens"] = media_video_tokens
    if media_video_frames is not None:
        media_patch["video_frames"] = media_video_frames
    chat_patch = _parse_bool_capability_flags(chat_capability, flag="--chat-capability")
    responses_patch = _parse_bool_capability_flags(
        responses_capability, flag="--responses-capability"
    )
    patch_flags_used = bool(
        codex_patch
        or media_patch
        or chat_patch
        or responses_patch
        or completion_service_profile is not None
        or clear_completion_service
    )

    if execute is not None:
        # Mixed mode is refused: a plan is applied exactly as reviewed.
        if (
            patch_flags_used
            or capabilities_file is not None
            or requested_model is not None
            or match_type is not None
            or endpoint is not None
            or provider is not None
            or upstream_model is not None
            or priority is not None
            or visible_in_models is not None
            or supports_streaming is not None
            or notes is not None
            or clear_notes
        ):
            raise typer.BadParameter(
                "Edit flags are --dry-run only; review the plan, then --execute it unchanged."
            )
        if reason is None:
            raise typer.BadParameter("--reason is required with --execute.")
        if not (reason or "").strip():
            raise typer.BadParameter("--reason must be a nonblank audit reason.")
        if contains_known_secret_shape(reason):
            raise typer.BadParameter(
                "--reason: value must not contain recognized credential patterns."
            )
        execute_settings = get_settings()
        plan = read_route_plan_file(
            execute,
            external_tool_ceilings=execute_settings.get_external_tool_operator_ceilings(),
            profile_dir=execute_settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        # The CLI route argument BINDS to the reviewed plan (199-b): a plan
        # can never be applied to a different route than the one reviewed.
        if str(parse_uuid(route_id, field_name="route_id")) != plan.route_id:
            raise typer.BadParameter(
                "The route argument must match the reviewed plan."
            )
        try:
            row = run_async(
                _execute_route_update_plan(
                    route_id, plan, reason=reason, actor_admin_id=actor
                )
            )
        except Exception as exc:  # noqa: BLE001
            handle_cli_error(exc, json_output=json_output)
            return
        payload = _safe_route_dict(row)
        if json_output:
            emit_json(payload)
            return
        echo_kv(payload)
        return

    if capabilities_file is not None and patch_flags_used:
        raise typer.BadParameter(
            "Choose either --capabilities-file (complete replacement) or "
            "capability edit flags (partial patch), not both."
        )
    if notes is not None and clear_notes:
        raise typer.BadParameter("Choose either --notes or --clear-notes, not both.")
    if completion_service_profile is not None and clear_completion_service:
        raise typer.BadParameter(
            "Choose either --completion-service-profile or --clear-completion-service."
        )

    if completion_service_profile is not None:
        completion_service: object = {
            "version": 1,
            "profile": completion_service_profile,
        }
    elif clear_completion_service:
        completion_service = None
    else:
        completion_service = CapabilityPatch().completion_service  # omitted
    patch = CapabilityPatch(
        codex_limits=codex_patch or None,
        media_input_estimation=media_patch or None,
        chat_completions=chat_patch,
        responses=responses_patch,
        completion_service=completion_service,
    )
    has_patch = not patch.is_empty()

    preview_settings = get_settings()
    capabilities = (
        read_capabilities_file(
            capabilities_file,
            external_tool_ceilings=preview_settings.get_external_tool_operator_ceilings(),
            profile_dir=preview_settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        if capabilities_file is not None
        else None
    )
    try:
        plan = run_async(
            _preview_route_update_plan(
                route_id,
                requested_model=requested_model,
                match_type=match_type,
                endpoint=endpoint,
                provider=provider,
                upstream_model=upstream_model,
                priority=priority,
                visible_in_models=visible_in_models,
                supports_streaming=supports_streaming,
                notes=notes,
                clear_notes=clear_notes,
                capabilities_document=capabilities,
                capability_patch=patch if has_patch else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    # The round-trip gate must revalidate under the SAME configured
    # installation ceilings and profile directory the preview used.
    write_route_plan_file(
        dry_run,
        plan,
        external_tool_ceilings=preview_settings.get_external_tool_operator_ceilings(),
        profile_dir=preview_settings.COMPLETION_SERVICE_PROFILE_DIR,
    )
    preview = plan.preview or {}
    payload = {
        "route_id": plan.route_id,
        "capabilities_mode": plan.capabilities_mode,
        "changed_fields": list(preview.get("changed_fields") or []),
        "expected_configuration_fingerprint": plan.expected_configuration_fingerprint,
        "plan_written": True,
    }
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("enable")
def enable(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Enable a model route."""
    try:
        row = run_async(_set_route_enabled(route_id, enabled=True))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("disable")
def disable(
    route_id: Annotated[str, typer.Argument(help="Route UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Disable a model route."""
    try:
        row = run_async(_set_route_enabled(route_id, enabled=False))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_route_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("import")
def import_routes(
    file: Annotated[Path, typer.Option("--file", help="Local JSON, CSV, or TSV route file")],
    input_format: Annotated[
        str | None,
        typer.Option(
            "--format", help="json, csv, or tsv; auto-detected from file extension if omitted"
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate without writing rows")
    ] = False,
    execute: Annotated[bool, typer.Option("--execute", help="Write validated rows")] = False,
    confirm_import: Annotated[
        bool,
        typer.Option("--confirm-import", help="Acknowledge that confirmed import will write rows"),
    ] = False,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Audit reason for confirmed import")
    ] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Admin actor UUID for audit"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Preview or execute route imports from a local JSON, CSV, or TSV file."""
    try:
        mode = _resolve_import_mode(
            dry_run=dry_run,
            execute=execute,
            confirm_import=confirm_import,
            reason=reason,
        )
        rows = _load_import_file(file, input_format=input_format)
        if mode == "dry_run":
            preview = run_async(_preview_route_import(rows=rows))
            payload = route_import_preview_to_dict(preview)
            payload["dry_run"] = True
        else:
            payload = run_async(
                _execute_route_import(
                    rows=rows,
                    actor_admin_id=actor_admin_id,
                    reason=reason or "",
                )
            )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(payload)
        return
    echo_kv(
        {
            "dry_run": payload["dry_run"],
            "total_rows": payload["total_rows"],
            "valid_count": payload["valid_count"],
            "invalid_count": payload["invalid_count"],
            "created_count": payload.get("created_count", 0),
            "updated_count": payload.get("updated_count", 0),
            "skipped_count": payload.get("skipped_count", 0),
            "error_count": payload.get("error_count", 0),
        }
    )


def _load_import_file(path: Path, *, input_format: str | None) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        raise ValueError("Route import file does not exist")
    text = path.read_text(encoding="utf-8")
    file_format = detect_route_import_format(
        filename=path.name,
        requested_format=(input_format or "auto"),
        text=text,
    )
    if file_format == "json":
        return parse_route_import_json(text)
    if file_format == "tsv":
        return parse_route_import_tsv(text)
    if file_format == "csv":
        return parse_route_import_csv(text)
    raise ValueError("Route import format must be auto, csv, json, or tsv")
