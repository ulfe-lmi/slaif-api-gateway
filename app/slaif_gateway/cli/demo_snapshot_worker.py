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
from slaif_gateway.services import demo_web_worker as dww
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
from slaif_gateway.services.demo_snapshot_files import (
    files_config_from_settings,
    run_files_job,
)

app = typer.Typer(help="Bounded private demo PostgreSQL snapshot worker (worker-only)")


def _fail(
    exc: DemoSnapshotError | dww.DemoWebWorkerError, *, json_output: bool
) -> None:
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


@app.command("files")
def files(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Capture, sanitize and verify every 222 copy's display files (223).

    Idempotent: already file-verified copies are skipped; a failed copy
    keeps its 222 state with a safe finite files failure code for
    operator inspection and retry.
    """
    try:
        config = files_config_from_settings(get_settings())
        result = run_files_job(config, get_settings())
        payload: dict[str, object] = {
            "state": result.state,
            "copies_files_verified": result.copies_files_verified,
            "copies_failed": result.copies_failed,
            "elapsed_ms": result.elapsed_ms,
        }
        if result.failure_code is not None:
            payload["code"] = result.failure_code
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
        if result.state != "FILES_VERIFIED":
            raise typer.Exit(code=1)
    except DemoSnapshotError as exc:  # safe fixed vocabulary only
        _fail(exc, json_output=json_output)


@app.command("process-request")
def process_request(
    request_id: Annotated[
        str, typer.Argument(help="The exact demo snapshot request UUID to process.")
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Process ONE specific request: claim, ONE fresh 221 copy, 222 + 223
    for THAT copy, worker-held proof, verified handoff (224-b, worker-only).

    Requires the explicit worker-control credential configuration
    (separate from the owner DATABASE_URL). Output is the safe fixed
    vocabulary: state, finite failure code, elapsed milliseconds. The
    job id and target database name are NEVER emitted.
    """
    import asyncio
    import uuid as _uuid

    from slaif_gateway.services.demo_web_worker import DemoWebWorkerError

    try:
        rid = _uuid.UUID(request_id)
    except ValueError:
        typer.secho(
            "Error: The request id is not a valid UUID.", fg=typer.colors.RED, err=True
        )
        typer.secho("code: WEB_WORKER_MISCONFIGURED", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        settings = get_settings()
        config = dww.web_worker_config_from_settings(settings)
        result = asyncio.run(
            dww.process_request(config, settings, request_id=rid)
        )
        payload: dict[str, object] = result.to_safe_dict()
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
        if result.state != "verified_unpublished":
            raise typer.Exit(code=1)
    except (DemoSnapshotError, DemoWebWorkerError) as exc:
        _fail(exc, json_output=json_output)


@app.command("cleanup")
def cleanup(
    limit: Annotated[
        int,
        typer.Option("--limit", help="Bounded candidate scan size (1..100)."),
    ] = 100,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the safe result as a JSON object."),
    ] = False,
) -> None:
    """Bounded recovery/cleanup (224-b, worker-only, schedulable).

    Reaps stuck pending/claimed rows, marks failed and session-released
    verified rows cleanup_pending, then drops ONLY each bound target
    database and removes ONLY its owned custody leaves before claiming
    cleaned. Output is the safe fixed-vocabulary counts; retained rows
    stay inspectable for retry.
    """
    import asyncio

    from slaif_gateway.services.demo_web_worker import DemoWebWorkerError

    try:
        settings = get_settings()
        config = dww.web_worker_config_from_settings(settings)
        result = asyncio.run(dww.recover_and_cleanup(config, limit=limit))
        payload: dict[str, object] = {"state": "CLEANUP_RAN"}
        payload.update(result.to_safe_dict())
        if json_output:
            from slaif_gateway.cli.common import emit_json

            emit_json(payload)
        else:
            echo_kv(payload)
    except (DemoSnapshotError, DemoWebWorkerError) as exc:
        _fail(exc, json_output=json_output)
