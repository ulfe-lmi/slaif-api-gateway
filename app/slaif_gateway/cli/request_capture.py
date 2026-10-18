"""Typer commands for the operator-controlled request-capture facility.

These act on the shared local capture store using settings only: they never
construct the HTTP app or open a database. Enable / directory / revision are
process-restart settings; ``arm`` / ``status`` / ``stop`` / ``cleanup`` operate
on the shared manifest and need no restart. Output is safe JSON; captured
request content is never printed by ``status``/``stop``/``cleanup`` (only
``inspect`` decodes a specific, operator-selected artifact).

Error boundary: known facility/config errors (``CliError`` /
``CaptureStoreError``) keep their fixed, content-free reasons; any *unexpected*
exception is swallowed into a single fixed generic ``command_failed`` result
that never echoes the exception message (so a fault carrying request content
cannot leak). ``typer.Exit`` is never re-caught.
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import CliError, emit_json, handle_cli_error
from slaif_gateway.config import get_settings
from slaif_gateway.services.request_capture import (
    CAPTURES_DIR_NAME,
    CaptureSession,
    CaptureStore,
    CaptureStoreError,
    build_capture_facility,
)

app = typer.Typer(help="Operator request-capture facility (arm/status/stop/cleanup/inspect)")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SAFE_SESSION_ID = re.compile(r"^cap-[0-9a-f]{32}$")
# Safety margin over the base64-expanded body budget for artifact reads.
_ARTIFACT_MARGIN_BYTES = 1024 * 1024
_MIN_ARTIFACT_BYTES = 1 * 1024 * 1024


def _store() -> CaptureStore:
    settings = get_settings()
    store = build_capture_facility(settings)
    if store is None:
        if not getattr(settings, "REQUEST_CAPTURE_ENABLED", False):
            raise CliError(
                "request capture is not enabled; set REQUEST_CAPTURE_ENABLED and "
                "REQUEST_CAPTURE_DIR (and restart workers), then retry"
            )
        raise CliError("request capture facility is unavailable; check REQUEST_CAPTURE_DIR")
    return store


def _safe_unexpected_failure() -> None:
    """Fixed, content-free failure for unexpected exceptions (never echo it)."""
    emit_json({"error": {"code": "command_failed", "message": "Command failed"}})
    raise typer.Exit(code=1)


def _run(operation: Callable[[], None]) -> None:
    """Run one command body behind the safe, fixed CLI error boundary."""
    try:
        operation()
    except typer.Exit:
        raise
    except (CliError, CaptureStoreError) as exc:
        handle_cli_error(exc, json_output=True)
    except Exception:  # noqa: BLE001 - fixed generic boundary, no detail
        _safe_unexpected_failure()


def _session_payload(session: CaptureSession, now: float) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "endpoint": session.endpoint,
        "key_uuid": session.key_uuid,
        "count": session.count,
        "claimed": session.claimed,
        "remaining": session.remaining,
        "status": session.status(now),
        "expires_at": session.expires_at,
    }


@app.command("arm")
def arm(
    endpoint: Annotated[str, typer.Option("--endpoint", help="Exact request path, e.g. /v1/responses.")],
    key_uuid: Annotated[str | None, typer.Option("--key-uuid", help="Verified gateway key UUID filter (optional).")] = None,
    count: Annotated[int | None, typer.Option("--count", help="Finite number of requests to capture.")] = None,
    ttl_seconds: Annotated[float | None, typer.Option("--ttl-seconds", help="Finite absolute expiry in seconds.")] = None,
) -> None:
    """Arm a finite, expiring capture window for the next matching request(s)."""

    def _op() -> None:
        store = _store()
        config = store.config
        count_value = count if count is not None else config.default_count
        ttl_value = ttl_seconds if ttl_seconds is not None else config.default_ttl_seconds
        session = store.arm(
            endpoint=endpoint,
            key_uuid=key_uuid,
            count=count_value,
            ttl_seconds=ttl_value,
        )
        emit_json(_session_payload(session, session.created_at))

    _run(_op)


@app.command("status")
def status() -> None:
    """List capture sessions with their current state and remaining count."""

    def _op() -> None:
        store = _store()
        now = time.time()
        sessions = [_session_payload(s, now) for s in store.status(now=now)]
        emit_json({"sessions": sessions, "storage_bytes_reserved": store.storage_reserved()})

    _run(_op)


@app.command("stop")
def stop(
    session_id: Annotated[str | None, typer.Option("--session-id", help="Stop one session; omit to stop all.")] = None,
) -> None:
    """Stop a session (or all), ending collection without deleting artifacts."""

    def _op() -> None:
        store = _store()
        if session_id is not None and not _SAFE_SESSION_ID.fullmatch(session_id):
            raise CliError("session_id has an invalid form")
        stopped = store.stop(session_id=session_id)
        emit_json({"stopped": stopped})

    _run(_op)


@app.command("cleanup")
def cleanup(
    session_id: Annotated[str | None, typer.Option("--session-id", help="Cleanup one session; omit for all.")] = None,
) -> None:
    """Delete a session's owned artifacts and release its storage quota."""

    def _op() -> None:
        store = _store()
        if session_id is not None and not _SAFE_SESSION_ID.fullmatch(session_id):
            raise CliError("session_id has an invalid form")
        removed = store.cleanup(session_id=session_id)
        emit_json({"artifacts_removed": removed})

    _run(_op)


@app.command("inspect")
def inspect(
    request_id: Annotated[str, typer.Option("--request-id", help="The gw-... X-SLAIF-Diagnostic-ID to inspect.")],
    decode: Annotated[bool, typer.Option("--decode", help="Decode base64 body/headers for reading.")] = False,
) -> None:
    """Locate and (optionally) decode one specific capture artifact by request ID."""

    def _op() -> None:
        if not _SAFE_REQUEST_ID.fullmatch(request_id):
            raise CliError("request_id has an invalid form")
        store = _store()
        capture_raw, record_raw = _find_artifacts(store, request_id)
        if capture_raw is None:
            raise CliError("no capture artifact found for that request_id")
        capture = _parse_json(capture_raw)
        record = _parse_json(record_raw) if record_raw is not None else None
        if decode:
            capture = _decode_capture(capture)
        emit_json({"capture": capture, "record": record})

    _run(_op)


# -- bounded artifact read -------------------------------------------------


def _artifact_budget_bytes(store: CaptureStore) -> int:
    budget = max(_MIN_ARTIFACT_BYTES, int(store.config.body_budget_bytes))
    return int(budget * 4 / 3) + _ARTIFACT_MARGIN_BYTES


def _bounded_read_regular(path: Path, max_bytes: int) -> bytes | None:
    """Read an owned, regular, non-symlink artifact via a no-follow fd.

    Returns ``None`` when the path is absent or not a regular file we own;
    raises ``CliError`` for a size overflow (a fixed, content-free reason).
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        if os.geteuid() is not None and st.st_uid != os.geteuid():
            raise CliError("capture artifact is not owned by the current user")
        if st.st_size > max_bytes:
            raise CliError("capture artifact exceeds the safe read limit")
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            chunks.append(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if len(raw) > max_bytes:
        raise CliError("capture artifact exceeds the safe read limit")
    return raw


def _find_artifacts(
    store: CaptureStore, request_id: str
) -> tuple[bytes | None, bytes | None]:
    """Locate a session's capture/record artifacts for a request ID, safely."""
    captures_dir = store.root / CAPTURES_DIR_NAME
    if captures_dir.is_symlink() or not captures_dir.is_dir():
        return None, None
    max_bytes = _artifact_budget_bytes(store)
    for session_dir in captures_dir.iterdir():
        if session_dir.is_symlink() or not session_dir.is_dir():
            continue
        if not _SAFE_SESSION_ID.fullmatch(session_dir.name):
            continue
        capture_path = session_dir / f"{request_id}.capture.json"
        record_path = session_dir / f"{request_id}.record.json"
        if capture_path.is_symlink():
            continue
        capture_raw = _bounded_read_regular(capture_path, max_bytes)
        if capture_raw is None:
            continue
        record_raw = (
            _bounded_read_regular(record_path, max_bytes)
            if not record_path.is_symlink()
            else None
        )
        return capture_raw, record_raw
    return None, None


def _parse_json(raw: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise CliError("capture artifact is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise CliError("capture artifact is not valid JSON")
    return parsed


# -- decode (retain original base64, label any lossy view) -----------------


def _decode_field(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, TypeError):
        return {"base64": value, "note": "not_base64"}
    try:
        return {"base64": value, "text": raw.decode("utf-8")}
    except UnicodeDecodeError:
        return {
            "base64": value,
            "text": raw.decode("utf-8", "replace"),
            "note": "non_utf8_lossy_view",
        }


def _decode_capture(capture: dict[str, object]) -> dict[str, object]:
    decoded = dict(capture)
    for key in ("path", "query", "body"):
        if key in decoded:
            decoded[key] = _decode_field(decoded[key])
    headers = decoded.get("headers")
    if isinstance(headers, list):
        decoded["headers"] = [[name, _decode_field(value)] for name, value in headers]
    return decoded
