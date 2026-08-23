"""Typer commands for provider configuration metadata."""

from __future__ import annotations

from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    echo_kv,
    emit_json,
    handle_cli_error,
    require_positive_limit,
    run_async,
)
from slaif_gateway.db.models import ProviderConfig
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
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

app = typer.Typer(help="Manage provider metadata")


def _safe_provider_dict(row: ProviderConfig) -> dict[str, object]:
    return {
        "id": row.id,
        "provider": row.provider,
        "display_name": row.display_name,
        "kind": row.kind,
        "base_url": row.base_url,
        "api_key_env_var": row.api_key_env_var,
        "enabled": row.enabled,
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _service(session) -> ProviderConfigService:
    return ProviderConfigService(
        provider_configs_repository=ProviderConfigsRepository(session),
        audit_repository=AuditRepository(session),
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
) -> ProviderConfig:
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
    enabled: Annotated[bool, typer.Option("--enabled/--disabled", help="Enable provider")] = True,
    notes: Annotated[str | None, typer.Option("--notes", help="Administrative notes")] = None,
    kind: Annotated[
        str,
        typer.Option("--kind", help="Provider kind: openai_compatible or module"),
    ] = "openai_compatible",
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    confirm_insecure_http: Annotated[
        bool,
        typer.Option("--confirm-insecure-http", help="Allow an HTTP LAN backend after reviewing the warning"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Create provider metadata without storing provider secrets."""
    try:
        row = run_async(
            _add_provider(
                provider=provider,
                display_name=display_name,
                base_url=base_url,
                api_key_env_var=api_key_env_var,
                enabled=enabled,
                notes=notes,
                kind=kind,
                reason=reason,
                confirm_insecure_http=confirm_insecure_http,
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
