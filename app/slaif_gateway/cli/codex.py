"""Codex protocol qualification, profiles, and audited module upgrades."""

from __future__ import annotations

import uuid
import os
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.codex_replay import app as codex_replay_app
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
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
    bootstrap_codex_compatibility_profile,
)
from slaif_gateway.modules.clients.registry import get_client_module
from slaif_gateway.modules.codex_profile_data import (
    CodexProfileDataError,
    load_codex_profile_file,
    list_codex_presets,
    read_codex_preset,
)
from slaif_gateway.services.codex_module_upgrade import (
    CodexModuleUpgradeError,
    UPGRADE_TARGET_CLIENT_MODULES,
    migrate_codex_0162_key_profile,
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

app.add_typer(codex_replay_app, name="replay")


@app.command("presets")
def presets(
    json_output: Annotated[bool, typer.Option("--json", help="Output safe preset facts")] = False,
) -> None:
    """List shipped client compatibility presets without activating one."""
    try:
        rows = [{"name": name, "path": str(path), **profile.to_facts()}
                for name, path, profile in list_codex_presets()]
    except CodexProfileDataError as exc:
        typer.echo(exc.safe_message)
        raise typer.Exit(code=1) from None
    if json_output:
        emit_json({"presets": rows})
    else:
        for row in rows:
            typer.echo(f"{row['name']}: revision {row['revision']} {row['digest']}")


@app.command("export-preset")
def export_preset(
    name: Annotated[str, typer.Argument(help="Shipped compatibility preset name")],
    output: Annotated[Path, typer.Option("--output", help="New operator-owned JSON file")],
) -> None:
    """Copy a validated preset to a new file; never overwrite or activate it."""
    try:
        document = read_codex_preset(name)
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(document)
    except CodexProfileDataError as exc:
        typer.echo(exc.safe_message)
        raise typer.Exit(code=1) from None
    except OSError:
        typer.echo("The preset output must be a new writable file.")
        raise typer.Exit(code=1) from None
    typer.echo(f"Exported compatibility preset: {output}")


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


class _UnexpectedProfileCommandError(Exception):
    """Unexpected profile-command failure rendered with a fixed generic code."""


_EXPECTED_PROFILE_ERRORS: tuple[type[Exception], ...] = (CodexProfileDataError,)


def _handle_profile_command_error(exc: Exception, *, json_output: bool) -> None:
    """Render a profile read/bootstrap failure without leaking details.

    Expected typed ``CodexProfileDataError`` rejections keep their fixed
    safe code and message; every other exception (including arbitrary
    ``RuntimeError`` or ``ValueError``) is rendered with the fixed generic
    ``command_failed`` message and code so private values never reach CLI
    output.
    """
    if not isinstance(exc, _EXPECTED_PROFILE_ERRORS):
        exc = _UnexpectedProfileCommandError()
    handle_cli_error(exc, json_output=json_output)


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
        typer.Option(
            "--target",
            help="Target selector: 0149-v5, 0162-v1, or 0162-v2",
        ),
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
    """Upgrade one pinned Codex key to an explicit finite target.

    0149-v5 and 0162-v1 upgrade a key on the frozen 0149-v4 tuple. 0162-v2
    upgrades a key on the exact historical 0162-v1 tuple (a 0.149-v4 key
    reaches it only through the documented explicit two-hop sequence while
    quiesced). Default is a dry run; --apply writes the client_module
    compatibility metadata and the audit record in one atomic transaction.
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
            "0162-v1" if target == "0162-v2" else "0149-v4",
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
        typer.Option(
            "--from-target",
            help="Current target selector: 0149-v5, 0162-v1, or 0162-v2",
        ),
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
    """Roll one upgraded Codex key back to its exact frozen predecessor.

    0149-v5 and 0162-v1 roll back to the exact frozen 0.149-v4 tuple;
    0162-v2 rolls back to the exact historical 0162-v1 tuple. Default is a
    dry run; --apply writes the client_module compatibility metadata and the
    audit record in one atomic transaction.
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
            "0162-v1" if from_target == "0162-v2" else "0149-v4",
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


# --- Codex 0.162 file-backed compatibility profile (190-b) ---


@app.command("inspect-profile-file")
def inspect_profile_file(
    file_path: Annotated[
        str, typer.Argument(help="Candidate Codex compatibility profile JSON file")
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Validate a candidate profile file offline and show safe facts.

    The file is read once with the bounded loader; no database, network, or
    provider access.  On any rejection a fixed safe message (and code with
    --json) is shown and the command exits non-zero.
    """
    try:
        profile = load_codex_profile_file(file_path)
        facts = profile.to_facts()
    except CodexProfileDataError as exc:
        if json_output:
            emit_json({"valid": False, "code": exc.code})
        else:
            typer.echo(f"invalid: {exc.safe_message}")
        raise typer.Exit(code=1) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_profile_command_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json({"valid": True, **facts})
        return
    typer.echo("valid: true")
    for label, value in facts.items():
        typer.echo(f"{label}: {value}")


def _require_active_profile(*, json_output: bool = False) -> None:
    """Bind this CLI process to the configured active profile snapshot.

    Called only by commands that read the active profile (show-profile,
    migrate-key-profile).  An operator profile file configured for this
    process is validated once here; an invalid or missing configured file
    fails closed instead of falling back.  Offline commands such as
    inspect-profile-file never trigger this bootstrap.  Every failure —
    expected or unexpected — exits with a fixed safe message.
    """
    try:
        bootstrap_codex_compatibility_profile(get_settings().CODEX_COMPATIBILITY_PROFILE_FILE)
    except CodexProfileDataError as exc:
        typer.echo(exc.safe_message)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # noqa: BLE001
        _handle_profile_command_error(exc, json_output=json_output)


@app.command("show-profile")
def show_profile(
    json_output: Annotated[bool, typer.Option("--json", help="Output stable safe JSON")] = False,
) -> None:
    """Show the active Codex 0.162 profile snapshot of THIS CLI process.

    Reports the profile facts bound to this process's concrete registry
    module.  A running HTTP server keeps the snapshot from its own
    bootstrap until it is restarted, so this output describes this CLI
    process only, not necessarily a live server.
    """
    try:
        _require_active_profile(json_output=json_output)
        module = get_client_module(CODEX_0162_CLIENT_MODULE_ID)
        facts = module.profile.to_facts()
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_profile_command_error(exc, json_output=json_output)
        return
    if json_output:
        emit_json({"client_module_id": module.module_id, **facts})
        return
    typer.echo(
        f"client_module: {module.module_id} v{module.module_version} {module.fixture_sha256}"
    )
    for label, value in facts.items():
        typer.echo(f"{label}: {value}")


def _run_profile_migration(
    key_id: uuid.UUID,
    from_version: str,
    from_digest: str,
    target: str,
    reason: str,
    actor_admin_id: uuid.UUID | None,
    apply: bool,
) -> dict[str, object]:
    async def _mutation() -> dict[str, object]:
        async with cli_db_session() as (_, session):
            result = await migrate_codex_0162_key_profile(
                session=session,
                keys_repository=GatewayKeysRepository(session),
                audit_repository=AuditRepository(session),
                gateway_key_id=key_id,
                from_version=from_version,
                from_digest=from_digest,
                target=target,
                action="codex_key_profile_migrated",
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


_PROFILE_MIGRATION_TARGETS = ("active", "0162-v1", "0162-v2")


@app.command("migrate-key-profile")
def migrate_key_profile(
    key_id: Annotated[uuid.UUID, typer.Argument(help="Exact gateway key UUID to migrate")],
    from_version: Annotated[
        str,
        typer.Option("--from-version", help="Current exact pinned profile revision"),
    ],
    from_digest: Annotated[
        str,
        typer.Option(
            "--from-digest", help="Current exact pinned profile digest (64 lowercase hex)"
        ),
    ],
    reason: Annotated[
        str,
        typer.Option("--reason", help="Bounded operator reason recorded in the audit log"),
    ],
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Target: active (bootstrap data profile), 0162-v1, or 0162-v2",
        ),
    ] = "active",
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
    """Migrate one pinned Codex 0.162 key to an explicit profile target.

    The source must exactly match the key's current (version, digest) pin;
    legacy 1/2 sources require the frozen literal digests.  The target is
    the active validated data profile (default) or one of the two frozen
    legacy tuples for binary rollback.  Default is a dry run; --apply
    writes the client_module metadata and the audit record in one atomic
    transaction.  A repeated exact target is a no-op.
    """
    if target not in _PROFILE_MIGRATION_TARGETS:
        handle_cli_error(
            typer.BadParameter("The target is not an approved profile migration target."),
            json_output=json_output,
        )
        return
    _require_active_profile(json_output=json_output)
    try:
        payload = _run_profile_migration(
            key_id, from_version, from_digest, target, reason, actor_admin_id, apply
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
