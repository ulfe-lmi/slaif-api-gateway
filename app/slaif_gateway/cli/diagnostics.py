"""Typer commands for the content-free request-failure diagnostics.

All commands go through the shared :class:`RequestDiagnosticsService`
(typed, bounded, read-only for lookups; the explicit ``cleanup`` command is
the only physical operation and touches only the diagnostics table).  No
raw SQL, record editing, secret recovery, or audit-log retention changes.

Output is safe JSON (or a short human line): stored fields are already
content-free, bounded, and secret-free by the service projection, so the
CLI echoes exactly the retained typed fields and nothing else.

Exit codes:
* ``status`` / ``cleanup``: 0 on a completed operation (store-unavailable is
  reported in the payload); 1 on configuration or unexpected failure.
* ``request show``: 0 for found / ambiguous / not_found outcomes (the typed
  outcome is in the payload); 1 for an unavailable store or configuration
  failure.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    CliDatabaseConfigError,
    CliError,
    emit_json,
    handle_cli_error,
    run_async,
)
from slaif_gateway.config import get_settings
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.schemas.request_diagnostics import (
    DiagnosticLookupResult,
    DiagnosticsCleanupResult,
    DiagnosticsNamespace,
    DiagnosticsStatus,
    RequestDiagnosticRecord,
)
from slaif_gateway.services.request_diagnostics import RequestDiagnosticsService

app = typer.Typer(help="Content-free request-failure diagnostics (status/request show/cleanup)")

_NAMESPACE_VALUES = ("any", "gateway", "client")


def _service() -> RequestDiagnosticsService:
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    session_factory = get_sessionmaker(settings)
    return RequestDiagnosticsService(settings=settings, session_factory=session_factory)


def _run_async(operation, *, json_output: bool = False) -> None:  # noqa: ANN001 - typer callback
    try:
        run_async(operation)
    except typer.Exit:
        raise
    except (CliError, CliDatabaseConfigError) as exc:
        handle_cli_error(exc, json_output=json_output)
    except Exception:  # noqa: BLE001 - fixed generic boundary, never echo detail
        if json_output:
            emit_json({"error": {"code": "command_failed", "message": "Command failed"}})
        else:
            typer.secho("Error: Command failed", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def _record_payload(record: RequestDiagnosticRecord) -> dict[str, object]:
    return {
        "gateway_request_id": record.gateway_request_id,
        "client_request_id": record.client_request_id,
        "client_id_unavailable_reason": record.client_id_unavailable_reason,
        "method": record.method,
        "endpoint_template": record.endpoint_template,
        "occurred_at": record.occurred_at.isoformat(),
        "http_status": record.http_status,
        "stream_outcome": record.stream_outcome,
        "source": record.source,
        "reason_code": record.reason_code,
        "error_code": record.error_code,
        "error_param": record.error_param,
        "positions": record.positions,
        "counts": record.counts,
        "limits": record.limits,
        "gateway_key_id": str(record.gateway_key_id) if record.gateway_key_id else None,
        "route_id": str(record.route_id) if record.route_id else None,
        "route_pattern": record.route_pattern,
        "deployment_revision": record.deployment_revision,
        "estimated_input_tokens": record.estimated_input_tokens,
        "output_allowance_tokens": record.output_allowance_tokens,
        "context_window_tokens": record.context_window_tokens,
        "replay_error_code": record.replay_error_code,
        "recorded_at": record.recorded_at.isoformat(),
    }


def _lookup_payload(result: DiagnosticLookupResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "outcome": result.outcome.value,
        "namespace": result.namespace.value,
        "match_count": result.match_count,
        "overflow": result.overflow,
    }
    if result.reason is not None:
        payload["reason"] = result.reason
    if result.record is not None:
        payload["record"] = _record_payload(result.record)
    if result.candidates:
        payload["candidates"] = [
            {
                "gateway_request_id": candidate.gateway_request_id,
                "occurred_at": candidate.occurred_at.isoformat(),
                "matched_namespace": candidate.matched_namespace,
            }
            for candidate in result.candidates
        ]
    return payload


def _status_payload(status: DiagnosticsStatus) -> dict[str, object]:
    return {
        "recording_enabled": status.recording_enabled,
        "store_available": status.store_available,
        "retained_records": status.retained_records,
        "retention_seconds": status.retention_seconds,
        "max_records": status.max_records,
        "write_timeout_ms": status.write_timeout_ms,
        "oldest_occurred_at": (
            status.oldest_occurred_at.isoformat() if status.oldest_occurred_at else None
        ),
        "newest_occurred_at": (
            status.newest_occurred_at.isoformat() if status.newest_occurred_at else None
        ),
    }


@app.command()
def status(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Show recording status and the retained-dataset summary.

    Distinguishes disabled recording, an unavailable store, and an empty
    retained dataset.  Works whether or not recording is enabled.
    """

    async def _op() -> None:
        result = await _service().status()
        payload = _status_payload(result)
        if json_output:
            emit_json(payload)
            return
        if not result.recording_enabled:
            if not result.store_available:
                typer.echo(
                    "recording disabled and store unavailable "
                    "(no new records; retained reads unavailable)"
                )
            else:
                typer.echo(
                    "recording disabled (no new records; retained reads still available)"
                )
        elif not result.store_available:
            typer.echo("store unavailable (check DATABASE_URL and database health)")
        elif result.retained_records == 0:
            typer.echo("recording enabled; retained dataset is empty")
        else:
            typer.echo(
                f"recording enabled; {result.retained_records} retained record(s) "
                f"(max {result.max_records}, retention {result.retention_seconds}s)"
            )

    _run_async(_op(), json_output=json_output)


request_app = typer.Typer(
    help="Resolve one recorded request failure by ID", no_args_is_help=True
)


@request_app.command("show")
def request_show(
    request_id: Annotated[str, typer.Option("--request-id", help="Recorded client or gateway request ID.")],
    namespace: Annotated[
        str,
        typer.Option("--namespace", help="any (default), gateway, or client ID namespace."),
    ] = "any",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Resolve one recorded request failure by ID (typed, bounded lookup).

    A lookup ID never establishes authentication authority.  Ambiguous
    matches are bounded at 100 candidates with an honest count/overflow and
    the gateway diagnostic IDs offered for disambiguation.
    """
    if namespace not in _NAMESPACE_VALUES:
        raise typer.BadParameter(f"--namespace must be one of: {', '.join(_NAMESPACE_VALUES)}")
    namespace_value = DiagnosticsNamespace(namespace)

    async def _op() -> None:
        result = await _service().resolve(request_id, namespace=namespace_value)
        payload = _lookup_payload(result)
        if json_output:
            emit_json(payload)
        elif result.outcome.value == "found" and result.record is not None:
            typer.echo(json.dumps(_record_payload(result.record), indent=2, sort_keys=True))
        else:
            typer.echo(
                f"outcome={result.outcome.value} matches={result.match_count} "
                f"overflow={'yes' if result.overflow else 'no'}"
            )
        if result.outcome.value == "unavailable":
            raise typer.Exit(code=1)

    _run_async(_op(), json_output=json_output)


app.add_typer(request_app, name="request")


@app.command()
def cleanup(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Physically prune ONE bounded batch of expired records (table only).

    There is no background expiry daemon: idle storage needs repeated
    cleanup (or the bounded prune that runs on writes).  Affects only the
    diagnostics table.
    """

    async def _op() -> None:
        result: DiagnosticsCleanupResult = await _service().cleanup()
        if json_output:
            emit_json(
                {
                    "deleted_count": result.deleted_count,
                    "store_available": result.store_available,
                    "reason": result.reason,
                }
            )
        elif result.store_available:
            typer.echo(f"cleaned up {result.deleted_count} expired record(s)")
        else:
            typer.echo("store unavailable (check DATABASE_URL and database health)")
        if not result.store_available:
            raise typer.Exit(code=1)

    _run_async(_op(), json_output=json_output)
