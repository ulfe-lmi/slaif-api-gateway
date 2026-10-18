"""Codex protocol qualification, profiles, and audited module upgrades."""

from __future__ import annotations

import uuid
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    CliDatabaseConfigError,
    cli_db_session,
    emit_json,
    handle_cli_error,
    run_async,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.services.codex_module_upgrade import (
    CodexModuleUpgradeError,
    UPGRADE_TARGET_CLIENT_MODULES,
    mutate_codex_client_module,
)
from slaif_gateway.services.codex_qualification import (
    CodexProfileArtifacts,
    CodexQualificationResult,
    CodexQualificationService,
    render_codex_profile,
    render_codex_profile_text,
)

app = typer.Typer(help="Inspect Codex protocol qualification and render a safe user profile")


def _service(session: object) -> CodexQualificationService:
    return CodexQualificationService(
        provider_configs_repository=ProviderConfigsRepository(session),
        model_routes_repository=ModelRoutesRepository(session),
        pricing_rules_repository=PricingRulesRepository(session),
        fx_rates_repository=FxRatesRepository(session),
    )


async def _inspect_codex() -> list[CodexQualificationResult]:
    async with cli_db_session() as (_, session):
        return await _service(session).inspect()


async def _build_profile(
    base_url: str,
    qualification_profile: str | None = None,
) -> tuple[CodexQualificationResult, CodexProfileArtifacts]:
    async with cli_db_session() as (_, session):
        qualification = await _service(session).ready_responses_profile(
            qualification_profile=qualification_profile
        )
    return qualification, render_codex_profile(base_url, qualification_profile)


@app.callback()
def codex() -> None:
    """Inspect exact local Codex protocol qualification."""


@app.command("inspect")
def inspect(
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """List deterministic local Codex qualification/readiness results."""

    try:
        results = run_async(_inspect_codex())
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    payload = [result.to_safe_dict() for result in results]
    if json_output:
        emit_json({"qualifications": payload})
        return
    if not payload:
        typer.echo("No model routes found.")
        return
    for index, result in enumerate(payload):
        if index:
            typer.echo("")
        typer.echo(f"state: {result['state']}")
        typer.echo(f"requested_model: {result['requested_model']}")
        typer.echo(f"provider: {result['provider']}")
        typer.echo(f"endpoint: {result['endpoint']}")
        typer.echo(f"route_id: {result['route_id']}")
        typer.echo(f"paired_route_id: {result['paired_route_id'] or ''}")
        typer.echo(f"reason_codes: {','.join(result['reason_codes'])}")
        typer.echo(f"profile_id: {result['profile_id'] or ''}")
        typer.echo(f"metadata_version: {result['metadata_version'] or ''}")
        typer.echo(f"real_provider_e2e: {str(result['real_provider_e2e']).lower()}")


@app.command("profile")
def profile(
    base_url: Annotated[
        str,
        typer.Option(
            "--base-url",
            help="Credential-free SLAIF gateway base URL ending exactly /v1",
        ),
    ],
    qualification_profile: Annotated[
        str | None,
        typer.Option(
            "--qualification-profile",
            help="Select a registered ready qualification profile; default is the legacy profile.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Print, but never write, the ready two-file Codex profile-v2 layout."""

    try:
        if qualification_profile is None:
            qualification, artifacts = run_async(_build_profile(base_url))
        else:
            qualification, artifacts = run_async(_build_profile(base_url, qualification_profile))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return
    if json_output:
        payload = artifacts.to_safe_dict()
        payload["qualification"] = qualification.to_safe_dict()
        emit_json(payload)
        return
    typer.echo(render_codex_profile_text(artifacts), nl=False)


def _run_module_mutation(
    key_id: uuid.UUID,
    expected_source: str,
    target: str,
    action: str,
    actor_admin_id: uuid.UUID | None,
    reason: str,
    apply: bool,
) -> dict[str, object]:
    async def _mutation() -> dict[str, object]:
        async with cli_db_session() as (_, session):
            result = await mutate_codex_client_module(
                session=session,
                keys_repository=GatewayKeysRepository(session),
                audit_repository=AuditRepository(session),
                gateway_key_id=key_id,
                expected_source=expected_source,
                target=target,
                action=action,
                actor_admin_id=actor_admin_id,
                reason=reason,
                apply=apply,
            )
        return {
            "gateway_key_id": str(result.gateway_key_id),
            "status": result.status,
            "action": result.action,
            "changed": result.changed,
            "source_module": dict(result.source_module),
            "target_module": dict(result.target_module),
        }

    return run_async(_mutation())


class _UnexpectedModuleMutationError(Exception):
    """Unexpected module-mutation failure rendered with a fixed generic code."""


_EXPECTED_MODULE_MUTATION_ERRORS: tuple[type[Exception], ...] = (
    CodexModuleUpgradeError,
    CliDatabaseConfigError,
)


def _handle_module_mutation_error(exc: Exception, *, json_output: bool) -> None:
    """Render a module-mutation failure without leaking unexpected details.

    Expected typed failures keep their specific safe codes; every other
    exception (including arbitrary ``ValueError`` or Pydantic validation
    errors) is rendered with the fixed generic ``command_failed`` message
    and code so private values never reach CLI output.
    """
    if not isinstance(exc, _EXPECTED_MODULE_MUTATION_ERRORS):
        exc = _UnexpectedModuleMutationError()
    handle_cli_error(exc, json_output=json_output)


@app.command("upgrade-key-module")
def upgrade_key_module(
    key_id: Annotated[uuid.UUID, typer.Argument(help="Exact gateway key UUID to upgrade")],
    target: Annotated[
        str,
        typer.Option("--target", help="Target selector: 0149-v5 or 0162-v1"),
    ],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Bounded operator reason recorded in the audit log"),
    ],
    actor_admin_id: Annotated[
        uuid.UUID | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID recorded in the audit log"),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Actually mutate the key; the default is a dry run"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Upgrade one pinned 0.149-v4 Codex key to an explicit finite target.

    Default is a dry run; --apply writes the client_module compatibility
    metadata and the audit record in one atomic transaction.
    """

    if target not in UPGRADE_TARGET_CLIENT_MODULES:
        handle_cli_error(
            typer.BadParameter("The target selector is not an approved selector."),
            json_output=json_output,
        )
        return
    try:
        payload = _run_module_mutation(
            key_id,
            "0149-v4",
            target,
            "codex_client_module_upgraded",
            actor_admin_id,
            reason,
            apply,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_module_mutation_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json(payload)
        return
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"key: {payload['gateway_key_id']}")
    typer.echo(f"changed: {str(payload['changed']).lower()}")
    for label, module in (
        ("source", payload["source_module"]),
        ("target", payload["target_module"]),
    ):
        typer.echo(f"{label}: {module['id']} v{module['version']} {module['fixture_sha256']}")


@app.command("rollback-key-module")
def rollback_key_module(
    key_id: Annotated[uuid.UUID, typer.Argument(help="Exact gateway key UUID to roll back")],
    from_target: Annotated[
        str,
        typer.Option("--from-target", help="Current target selector: 0149-v5 or 0162-v1"),
    ],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Bounded operator reason recorded in the audit log"),
    ],
    actor_admin_id: Annotated[
        uuid.UUID | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID recorded in the audit log"),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Actually mutate the key; the default is a dry run"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Roll one upgraded Codex key back to the exact frozen 0.149-v4 tuple.

    Default is a dry run; --apply writes the client_module compatibility
    metadata and the audit record in one atomic transaction.
    """

    if from_target not in UPGRADE_TARGET_CLIENT_MODULES:
        handle_cli_error(
            typer.BadParameter("The target selector is not an approved selector."),
            json_output=json_output,
        )
        return
    try:
        payload = _run_module_mutation(
            key_id,
            from_target,
            "0149-v4",
            "codex_client_module_rolled_back",
            actor_admin_id,
            reason,
            apply,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_module_mutation_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json(payload)
        return
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"key: {payload['gateway_key_id']}")
    typer.echo(f"changed: {str(payload['changed']).lower()}")
    for label, module in (
        ("source", payload["source_module"]),
        ("target", payload["target_module"]),
    ):
        typer.echo(f"{label}: {module['id']} v{module['version']} {module['fixture_sha256']}")
