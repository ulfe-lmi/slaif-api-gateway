"""Typer commands for provider configuration metadata."""

from __future__ import annotations

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
from slaif_gateway.db.models import ProviderConfig
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.provider_route_configuration import (
    contains_known_secret_shape,
    partial_update_provider_config,
)
from slaif_gateway.services.openai_compatible_discovery import (
    OpenAICompatibleDiscoveryService,
)
from slaif_gateway.services.openai_compatible_setup import (
    EXPLICIT_PRICING,
    LOCAL_ZERO_PRICING,
    OpenAICompatibleSetupService,
    SetupError,
    SetupRequest,
    parse_public_model_mapping_entries,
)
from slaif_gateway.services.provider_config_service import ProviderConfigService
from slaif_gateway.utils.redaction import redact_text

app = typer.Typer(help="Manage provider metadata")


def _safe_text(value: str | None) -> str | None:
    """Known-shape redaction for free-form read values (199-b).

    Legitimate env-reference NAMES (``api_key_env_var``) and structured
    fields are never masked; only recognized credential shapes inside
    free-form text are redacted before output.
    """
    return redact_text(value) if value else value


def _safe_provider_dict(row: ProviderConfig) -> dict[str, object]:
    return {
        "id": row.id,
        "provider": row.provider,
        "display_name": _safe_text(row.display_name),
        "kind": row.kind,
        "base_url": _safe_text(row.base_url),
        "api_key_env_var": row.api_key_env_var,
        "enabled": row.enabled,
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "notes": _safe_text(row.notes),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _service(session) -> ProviderConfigService:
    return ProviderConfigService(
        provider_configs_repository=ProviderConfigsRepository(session),
        audit_repository=AuditRepository(session),
    )


def _refuse_known_secret_shapes(
    *,
    display_name: str | None,
    base_url: str | None,
    notes: str | None,
    reason: str | None,
) -> None:
    """Refuse known credential shapes in creation free-form fields.

    One bounded check shared by the Typer ``add`` command and the async
    ``_add_provider`` entry point (199-c/199-d), invoked BEFORE any
    database access so a direct helper call cannot bypass it. Fixed safe
    vocabulary only: the flag is named, the value is never echoed.
    Known-shape protection, not a sanitizer framework.
    """
    for value, flag in (
        (display_name, "--display-name"),
        (base_url, "--base-url"),
        (notes, "--notes"),
        (reason, "--reason"),
    ):
        if contains_known_secret_shape(value):
            raise typer.BadParameter(
                f"{flag}: value must not contain recognized credential patterns."
            )


async def _add_provider(
    *,
    provider: str,
    display_name: str | None,
    base_url: str | None,
    api_key_env_var: str,
    enabled: bool,
    notes: str | None,
    kind: str,
    reason: str | None,
    confirm_insecure_http: bool,
    timeout_seconds: int,
    max_retries: int,
    actor_admin_id,
) -> ProviderConfig:
    _refuse_known_secret_shapes(
        display_name=display_name,
        base_url=base_url,
        notes=notes,
        reason=reason,
    )
    async with cli_db_session() as (_, session):
        return await _service(session).create_provider_config(
            provider=provider,
            display_name=display_name,
            base_url=base_url,
            api_key_env_var=api_key_env_var,
            enabled=enabled,
            notes=notes,
            kind=kind,
            reason=reason,
            confirm_insecure_http=confirm_insecure_http,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            actor_admin_id=actor_admin_id,
        )


async def _list_providers(*, enabled_only: bool, limit: int) -> list[ProviderConfig]:
    async with cli_db_session() as (_, session):
        return await _service(session).list_provider_configs(
            enabled_only=enabled_only,
            limit=limit,
        )


async def _show_provider(provider_or_id: str) -> ProviderConfig:
    async with cli_db_session() as (_, session):
        return await _service(session).get_provider_config(provider_or_id)


async def _update_provider(
    provider_or_id: str,
    *,
    display_name: str | None,
    base_url: str | None,
    kind: str | None,
    api_key_env_var: str | None,
    timeout_seconds: int | None,
    max_retries: int | None,
    notes: str | None,
    clear_notes: bool,
    confirm_insecure_http: bool,
    reason: str,
    actor_admin_id,
) -> ProviderConfig:
    async with cli_db_session() as (_, session):
        return await partial_update_provider_config(
            session,
            provider_or_id,
            display_name=display_name,
            base_url=base_url,
            kind=kind,
            api_key_env_var=api_key_env_var,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            notes=notes,
            clear_notes=clear_notes,
            confirm_insecure_http=confirm_insecure_http,
            reason=reason,
            actor_admin_id=actor_admin_id,
        )


async def _set_provider_enabled(provider_or_id: str, *, enabled: bool) -> ProviderConfig:
    async with cli_db_session() as (_, session):
        return await _service(session).set_provider_enabled(provider_or_id, enabled=enabled)


async def _discover_models(provider_or_id: str) -> dict[str, object]:
    async with cli_db_session() as (_, session):
        result = await OpenAICompatibleDiscoveryService(
            provider_configs_repository=ProviderConfigsRepository(session),
        ).discover(provider_or_id)
    return {"provider": result.provider, "models": list(result.models)}


async def _setup_models(
    *,
    provider_or_id: str,
    selected_models: list[str],
    public_model_entries: list[str],
    preset: str,
    priority: int,
    visible_in_models: bool,
    streaming: bool,
    local_function_tools: bool,
    confirm_enable_unqualified: bool,
    pricing_mode: str,
    confirm_local_zero: bool,
    input_price_per_1m: str | None,
    output_price_per_1m: str | None,
    reason: str,
) -> dict[str, object]:
    async with cli_db_session() as (_, session):
        providers = ProviderConfigsRepository(session)
        provider = await _service(session).get_provider_config(provider_or_id)
        mappings = parse_public_model_mapping_entries(selected_models, public_model_entries)
        result = await OpenAICompatibleSetupService(
            session=session,
            provider_configs_repository=providers,
            model_routes_repository=ModelRoutesRepository(session),
            pricing_rules_repository=PricingRulesRepository(session),
            audit_repository=AuditRepository(session),
            discovery_service=OpenAICompatibleDiscoveryService(
                provider_configs_repository=providers,
            ),
        ).execute(
            SetupRequest(
                provider=provider.provider,
                selected_models=tuple(selected_models),
                public_model_ids=mappings,
                preset=preset,
                priority=priority,
                visible_in_models=visible_in_models,
                streaming=streaming,
                local_function_tools=local_function_tools,
                confirm_enable_unqualified=confirm_enable_unqualified,
                pricing_mode=pricing_mode,
                confirm_local_zero=confirm_local_zero,
                input_price_per_1m=input_price_per_1m,
                output_price_per_1m=output_price_per_1m,
                reason=reason,
            )
        )
    return {
        "provider": result.provider,
        "models": list(result.models),
        "route_ids": [row.id for row in result.routes],
        "pricing_rule_ids": [row.id for row in result.pricing_rules],
        "route_count": len(result.routes),
        "pricing_rule_count": len(result.pricing_rules),
        "preset": result.preset,
        "enabled": result.enabled,
        "pricing_mode": result.pricing_mode,
    }


@app.callback()
def providers() -> None:
    """Manage provider metadata."""


@app.command("add")
def add(
    provider: Annotated[str, typer.Option("--provider", help="Provider name, e.g. openai")],
    api_key_env_var: Annotated[
        str,
        typer.Option("--api-key-env-var", help="Environment variable name containing the provider key"),
    ],
    display_name: Annotated[str | None, typer.Option("--display-name", help="Display name")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="OpenAI-compatible base URL")] = None,
    enabled: Annotated[
        bool | None,
        typer.Option(
            "--enabled/--disabled",
            help="Explicitly enable the provider; omitted creation stays DISABLED",
        ),
    ] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    kind: Annotated[
        str,
        typer.Option("--kind", help="Provider kind: openai_compatible or module"),
    ] = "openai_compatible",
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout-seconds", help="Positive upstream timeout in seconds"),
    ] = 300,
    max_retries: Annotated[
        int,
        typer.Option("--max-retries", help="Non-negative upstream retry count (0 valid)"),
    ] = 2,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Admin actor UUID for audit"),
    ] = None,
    confirm_insecure_http: Annotated[
        bool,
        typer.Option("--confirm-insecure-http", help="Allow an HTTP LAN backend after reviewing the warning"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create provider metadata without storing provider secrets."""
    actor = (
        parse_uuid(actor_admin_id, field_name="actor-admin-id")
        if actor_admin_id is not None
        else None
    )
    # 199-c/199-d: the SAME known-shape input guards as update apply to
    # creation free-form fields BEFORE any database access (the optional
    # creation reason law is preserved - only shapes are refused). The
    # shared check also runs inside _add_provider, so the public refusal
    # stays correct even when tests replace the async helper.
    _refuse_known_secret_shapes(
        display_name=display_name,
        base_url=base_url,
        notes=notes,
        reason=reason,
    )
    try:
        row = run_async(
            _add_provider(
                provider=provider,
                display_name=display_name,
                base_url=base_url,
                api_key_env_var=api_key_env_var,
                # Deliberate 199 default change: omitted creation stays
                # DISABLED; only explicit --enabled activates the provider.
                enabled=False if enabled is None else enabled,
                notes=notes,
                kind=kind,
                reason=reason,
                confirm_insecure_http=confirm_insecure_http,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                actor_admin_id=actor,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_provider_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("list")
def list_providers(
    enabled_only: Annotated[bool, typer.Option("--enabled-only", help="Only enabled providers")] = False,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List provider metadata."""
    require_positive_limit(limit)
    try:
        rows = run_async(_list_providers(enabled_only=enabled_only, limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_safe_provider_dict(row) for row in rows]
    if json_output:
        emit_json({"providers": payload})
        return
    if not payload:
        typer.echo("No providers found.")
        return
    for index, row in enumerate(payload):
        if index:
            typer.echo("")
        echo_kv(row)


@app.command("show")
def show(
    provider_or_id: Annotated[str, typer.Argument(help="Provider name or UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show one provider configuration."""
    try:
        row = run_async(_show_provider(provider_or_id))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = _safe_provider_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("update")
def update(
    provider_or_id: Annotated[str, typer.Argument(help="Provider name or UUID")],
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason")],
    display_name: Annotated[
        str | None, typer.Option("--display-name", help="New display name")
    ] = None,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="New OpenAI-compatible base URL")
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="New provider kind: openai_compatible or module"),
    ] = None,
    api_key_env_var: Annotated[
        str | None,
        typer.Option(
            "--api-key-env-var",
            help="New environment variable NAME containing the provider key",
        ),
    ] = None,
    timeout_seconds: Annotated[
        int | None,
        typer.Option("--timeout-seconds", help="New positive upstream timeout in seconds"),
    ] = None,
    max_retries: Annotated[
        int | None,
        typer.Option("--max-retries", help="New non-negative upstream retry count (0 valid)"),
    ] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Replace administrative notes")] = None,
    clear_notes: Annotated[
        bool,
        typer.Option("--clear-notes", help="Clear administrative notes to empty"),
    ] = False,
    confirm_insecure_http: Annotated[
        bool,
        typer.Option("--confirm-insecure-http", help="Allow an HTTP LAN backend after reviewing the warning"),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Admin actor UUID for audit"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Partially update one provider; omitted fields preserve current values."""
    if notes is not None and clear_notes:
        raise typer.BadParameter("Choose either --notes or --clear-notes, not both.")
    if not (reason or "").strip():
        raise typer.BadParameter("--reason must be a nonblank audit reason.")
    for value, flag in (
        (display_name, "--display-name"),
        (base_url, "--base-url"),
        (notes, "--notes"),
        (reason, "--reason"),
    ):
        if contains_known_secret_shape(value):
            raise typer.BadParameter(
                f"{flag}: value must not contain recognized credential patterns."
            )
    actor = (
        parse_uuid(actor_admin_id, field_name="actor-admin-id")
        if actor_admin_id is not None
        else None
    )
    try:
        row = run_async(
            _update_provider(
                provider_or_id,
                display_name=display_name,
                base_url=base_url,
                kind=kind,
                api_key_env_var=api_key_env_var,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                notes=notes,
                clear_notes=clear_notes,
                confirm_insecure_http=confirm_insecure_http,
                reason=reason,
                actor_admin_id=actor,
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_provider_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("discover-models")
def discover_models(
    provider_or_id: Annotated[str, typer.Argument(help="Generic provider name or UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")]=False,
) -> None:
    """Preview a bounded upstream /models response without mutating catalog state."""
    try:
        payload = run_async(_discover_models(provider_or_id))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json(payload)
        return
    typer.echo(f"provider: {payload['provider']}")
    typer.echo("models:")
    for model in payload["models"]:
        typer.echo(f"- {model}")


@app.command("setup-models")
def setup_models(
    provider_or_id: Annotated[str, typer.Argument(help="Generic provider name or UUID")],
    selected_models: Annotated[
        list[str], typer.Option("--model", help="Upstream model to select; repeat for multiple models")
    ],
    preset: Annotated[
        str,
        typer.Option(
            "--preset",
            help=(
                "chat_text_v1, responses_text_v1, chat_and_responses_text_v1, "
                "or chat_and_responses_vision_inline_v1"
            ),
        ),
    ],
    pricing_mode: Annotated[
        str,
        typer.Option("--pricing-mode", help="local_zero or explicit"),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason")],
    public_model_entries: Annotated[
        list[str] | None, typer.Option("--public-model-id", help="Repeated upstream=public mapping")
    ] = None,
    priority: Annotated[int, typer.Option("--priority")] = 100,
    visible_in_models: Annotated[bool, typer.Option("--visible/--hidden")] = True,
    streaming: Annotated[bool, typer.Option("--streaming/--no-streaming")] = False,
    local_function_tools: Annotated[bool, typer.Option("--local-function-tools/--no-local-function-tools")] = False,
    confirm_enable_unqualified: Annotated[
        bool, typer.Option("--confirm-enable-unqualified", help="Enable before qualification review")
    ] = False,
    confirm_local_zero: Annotated[
        bool, typer.Option("--confirm-local-zero", help="Confirm operator-local zero pricing")
    ] = False,
    input_price_per_1m: Annotated[str | None, typer.Option("--input-price-per-1m")] = None,
    output_price_per_1m: Annotated[str | None, typer.Option("--output-price-per-1m")] = None,
    confirm_execute: Annotated[
        bool, typer.Option("--confirm-execute", help="Confirm re-probe and atomic setup")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output safe JSON")] = False,
) -> None:
    """Re-probe and atomically create reviewed generic provider setup rows."""
    if not confirm_execute:
        raise typer.BadParameter("--confirm-execute is required")
    if pricing_mode not in {LOCAL_ZERO_PRICING, EXPLICIT_PRICING}:
        raise typer.BadParameter("--pricing-mode must be local_zero or explicit")
    try:
        payload = run_async(
            _setup_models(
                provider_or_id=provider_or_id,
                selected_models=selected_models,
                public_model_entries=public_model_entries or [],
                preset=preset,
                priority=priority,
                visible_in_models=visible_in_models,
                streaming=streaming,
                local_function_tools=local_function_tools,
                confirm_enable_unqualified=confirm_enable_unqualified,
                pricing_mode=pricing_mode,
                confirm_local_zero=confirm_local_zero,
                input_price_per_1m=input_price_per_1m,
                output_price_per_1m=output_price_per_1m,
                reason=reason,
            )
        )
    except (SetupError, ValueError) as exc:
        handle_cli_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("enable")
def enable(
    provider_or_id: Annotated[str, typer.Argument(help="Provider name or UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Enable a provider configuration."""
    try:
        row = run_async(_set_provider_enabled(provider_or_id, enabled=True))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_provider_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)


@app.command("disable")
def disable(
    provider_or_id: Annotated[str, typer.Argument(help="Provider name or UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Disable a provider configuration."""
    try:
        row = run_async(_set_provider_enabled(provider_or_id, enabled=False))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = _safe_provider_dict(row)
    if json_output:
        emit_json(payload)
        return
    echo_kv(payload)
