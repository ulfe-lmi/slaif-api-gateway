"""Typer commands for the bounded private demo snapshot worker (objective 221).

Law (mirrors the service module):
- this is the ONLY entry point to the raw-copy custody path; no HTTP route,
  admin template or web role can invoke it;
- output is a fixed safe vocabulary: state, finite failure code, export
  bytes, elapsed milliseconds and the custody copy count. The raw target
  database name, archive path, DSNs, passwords and row content are never
  emitted to stdout/stderr;
- default OFF until the operator configures every field;
- the demo is NOT usable end-to-end until stages 222 (masking), 223
  (file-backed capture) and 224 (login/GUI binding) are complete.
"""

from __future__ import annotations

from typing import Annotated

import typer

from slaif_gateway.cli.common import echo_kv
from slaif_gateway.config import get_settings
from slaif_gateway.services.demo_snapshot import (
    DemoSnapshotError,
    config_from_settings,
    count_raw_copies,
    expire_copies,
    recover_interrupted_jobs,
    run_snapshot_job,
)
from slaif_gateway.services.demo_snapshot_sanitize import (
    sanitize_copies,
)

app = typer.Typer(help="Bounded private demo PostgreSQL snapshot worker (worker-only)")


def _fail(exc: DemoSnapshotError, *, json_output: bool) -> None:
    """Render the safe fixed-vocabulary error and exit non-zero."""
    if json_output:
        from slaif_gateway.cli.common import emit_json

        emit_json({"error": {"code": exc.code, "message": exc.safe_message}})
    else:
        typer.secho(f"Error: {exc.safe_message}", fg=typer.colors.RED, err=True)
        typer.secho(f"code: {exc.code}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command("run")
def run(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Take ONE bounded snapshot job (future per-login invocation point)."""
    try:
        config = config_from_settings(get_settings())
        result = run_snapshot_job(config)
        payload: dict[str, object] = {
            "state": result.state,
            "export_bytes": result.export_bytes,
            "elapsed_ms": result.elapsed_ms,
            "custody_raw_copies": count_raw_copies(config),
        }
        if result.failure_code is not None:
            payload["code"] = result.failure_code
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
        if result.state != "RAW_UNVERIFIED":
            raise typer.Exit(code=1)
    except DemoSnapshotError as exc:  # safe fixed vocabulary only
        _fail(exc, json_output=json_output)


@app.command("expire")
def expire(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Run retention expiry and the finite copy budget."""
    try:
        config = config_from_settings(get_settings())
        removed = expire_copies(config)
        payload: dict[str, object] = {
            "state": "EXPIRED",
            "removed_copies": removed,
            "custody_raw_copies": count_raw_copies(config),
        }
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
    except DemoSnapshotError as exc:
        _fail(exc, json_output=json_output)


@app.command("sanitize")
def sanitize(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Sanitize and verify every RAW_UNVERIFIED private copy (stage 222).

    Idempotent: already-sanitized copies are skipped; a failed copy stays
    RAW_UNVERIFIED with a safe finite code for operator inspection and
    retry.
    """
    try:
        config = config_from_settings(get_settings())
        result = sanitize_copies(config)
        payload: dict[str, object] = {
            "state": result.state,
            "copies_sanitized": result.copies_sanitized,
            "copies_failed": result.copies_failed,
            "elapsed_ms": result.elapsed_ms,
            "custody_raw_copies": count_raw_copies(config),
        }
        if result.failure_code is not None:
            payload["code"] = result.failure_code
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
        if result.state not in ("SANITIZED", "SKIPPED"):
            raise typer.Exit(code=1)
    except DemoSnapshotError as exc:  # safe fixed vocabulary only
        _fail(exc, json_output=json_output)


@app.command("recover")
def recover(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Idempotently clean interrupted jobs left by a dead worker."""
    try:
        config = config_from_settings(get_settings())
        recovered = recover_interrupted_jobs(config)
        payload: dict[str, object] = {
            "state": "RECOVERED",
            "recovered_jobs": recovered,
            "custody_raw_copies": count_raw_copies(config),
        }
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
    except DemoSnapshotError as exc:
        _fail(exc, json_output=json_output)
