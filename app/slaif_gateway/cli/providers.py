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
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
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
) -> ProviderConfig:
    async with cli_db_session() as (_, session):
        return await _service(session).create_provider_config(
            provider=provider,
            display_name=display_name,
            base_url=base_url,
            api_key_env_var=api_key_env_var,
            enabled=enabled,
            notes=notes,
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
