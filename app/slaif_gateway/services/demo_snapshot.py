"""Objective 221: bounded private demo PostgreSQL snapshots (worker-only).

This module implements the SECOND bounded stage of the human-approved
fake-admin demonstration: one consistent snapshot of the live business
PostgreSQL, exported with ``pg_dump`` as a SELECT-only source role and
restored as a NEW UNIQUE database in a separate demo PostgreSQL service.

Trust boundaries (enforced, not just documented):

- Worker-only: no API route, no admin template, no web role, no public URL
  references the raw copy. The demo PostgreSQL target revokes ``CONNECT``
  from ``PUBLIC`` on every raw database it creates, so a synthetic web role
  cannot connect to or read it.
- Source is read-only: the source role holds SELECT/USAGE on the business
  schema only; it cannot DML, cannot read ``demo_control``, and never
  receives provider credentials (the PG client tools run with a minimal
  explicit environment that contains no provider or application
  variables). The dump is limited to the business ``public`` schema by a
  positive allowlist plus the two fixed approved extensions required by
  migration 0001, so ``demo_control`` can never enter the archive.
- No ``CREATE DATABASE ... TEMPLATE`` against the live source; the raw copy
  is a fresh database on the separate demo service. No new PostgreSQL
  server process per demo account.
- Custody: job state lives in an operator-owned ``0700`` directory OUTSIDE
  the repository and the databases; every artifact is ``0600``. Symlink
  traversal is refused. The custody manifest is the durable handoff record
  that later stages (222/223/224) address; it is deliberately NOT a
  PostgreSQL table: the SELECT-only source role must never be able to read
  or influence bookkeeping, and a file manifest keeps the schema surface at
  zero.
- Limits: an explicit per-job export byte cap (streamed and counted, the
  dump is killed before a complete claim can exceed it), an elapsed-time
  cap, single-worker concurrency via a race-safe kernel ``flock`` fence
  (the kernel releases the lock automatically when the worker dies),
  retention/expiry and a finite copy budget. Default OFF until the
  optional worker is configured.
- Privacy: passwords come from a restrictive ``PGPASSFILE`` (never argv or
  logs); the raw target database name, archive path, DSNs and any captured
  tool stderr are redacted from every rendered output, log line and report.
  An incomplete dump is NEVER marked complete.

A completed copy is recorded in the explicit ``RAW_UNVERIFIED`` state: no
future web reader can mistake it for published. Stages 222 (masking),
223 (file-backed capture) and 224 (login/GUI binding) are required before
any use; this stage proves custody and limits only.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import signal
import select
import subprocess
import stat as stat_module
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from slaif_gateway.config import Settings
from slaif_gateway.services.catalog_refresh import filesystem as catfs

# ---------------------------------------------------------------------------
# States and safe finite failure codes
# ---------------------------------------------------------------------------

#: A complete private copy. Explicitly NOT published: stages 222/223/224
#: must verify/project before any web-readable use.
STATE_RAW_UNVERIFIED = "RAW_UNVERIFIED"
#: The 222 sanitizer transaction committed AND the independent read-only
#: verifier passed. Still NOT published: file-backed verification (223)
#: and browser binding (224) are absent, and no web role may read it.
STATE_DB_SANITIZED_UNPUBLISHED = "DB_SANITIZED_UNPUBLISHED"
#: The 222 DB state AND the 223 file-backed capture, typed
#: sanitization and independent read-only verification all passed.
#: Still NOT published: browser binding (224) is absent and no web
#: role may read the copy or its display files.
STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED = "DB_AND_FILES_VERIFIED_UNPUBLISHED"
#: The worker is mid-job on this copy.
STATE_RUNNING = "RUNNING"
#: The job failed and its partial artifacts were cleaned.
STATE_FAILED = "FAILED"
#: The job failed AND cleanup could not finish; inspectable operator-only
#: state that a later ``recover`` retries idempotently.
STATE_CLEANUP_FAILED = "CLEANUP_FAILED"
#: Partial/interrupted artifacts were cleaned; no copy exists.
STATE_CLEANED = "CLEANED"

CODE_DISABLED = "SNAPSHOT_DISABLED"
CODE_MISCONFIGURED = "SNAPSHOT_MISCONFIGURED"
CODE_CUSTODY_UNSAFE = "CUSTODY_UNSAFE"
CODE_FENCE_HELD = "FENCE_HELD"
CODE_SOURCE_DUMP_FAILED = "SOURCE_DUMP_FAILED"
CODE_SOURCE_DUMP_CAP_BYTES = "SOURCE_DUMP_CAP_BYTES"
CODE_SOURCE_DUMP_CAP_ELAPSED = "SOURCE_DUMP_CAP_ELAPSED"
CODE_SOURCE_DUMP_CANCELLED = "SOURCE_DUMP_CANCELLED"
CODE_TARGET_CREATE_FAILED = "TARGET_CREATE_FAILED"
CODE_TARGET_RESTORE_FAILED = "TARGET_RESTORE_FAILED"
CODE_TARGET_RESTORE_CAP_ELAPSED = "TARGET_RESTORE_CAP_ELAPSED"
CODE_TARGET_NOT_SEPARATE = "TARGET_NOT_SEPARATE"
CODE_CLEANUP_FAILED = "CLEANUP_FAILED"
CODE_UNEXPECTED = "UNEXPECTED"
#: The restored copy's catalog differs from the reviewed field policy
#: (unknown table/column/type/extension/constraint): fail closed before
#: any modification.
CODE_SANITIZE_SCHEMA_UNKNOWN = "SANITIZE_SCHEMA_UNKNOWN"
#: The sanitizer transaction failed or was not committed; the copy stays
#: RAW_UNVERIFIED and no promotion occurred.
CODE_SANITIZE_FAILED = "SANITIZE_FAILED"
#: The transaction committed but the independent verifier failed; the
#: copy is NOT promoted (stays RAW_UNVERIFIED, inspectable).
CODE_SANITIZE_VERIFY_FAILED = "SANITIZE_VERIFY_FAILED"

_MANIFEST_NAME = "manifest.json"
_MANIFEST_SCHEMA_VERSION = 1
_FENCE_NAME = ".fence"
_TARGET_DB_PREFIX = "demo_snap_"
_DUMP_NAME = "demo.dump"
_FILES_MANIFEST_NAME = "files_manifest.json"
#: Bounded acceptance cap for the private files manifest on cleanup.
_FILES_MANIFEST_MAX_BYTES = 1 * 1024 * 1024
#: Finite maximum number of flat display leaves per job.
_FILES_MAX_LEAVES = 4096
#: Generated flat display-leaf filename grammar (single component;
#: no slash, dot or dotdot can ever match).
_FILES_LEAF_NAME_RE = re.compile(r"^f[0-9]{4}-[0-9a-f]{12}$")
_STDERR_TAIL_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 1024 * 1024
_POLL_SECONDS = 0.1
_PG_CONNECT_TIMEOUT = 10
# Conservative SQL identifier vocabulary for any operator-configured name
# that is interpolated into SQL (the generated target database name and the
# target user). Nothing else may reach these statements.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class DemoSnapshotError(Exception):
    """Safe fixed-vocabulary error for the demo snapshot worker.

    ``code`` is one of the finite codes above; the rendered message never
    contains a DSN, password, raw database name, archive path or row
    content.
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DemoSnapshotConfig:
    """Explicitly configured, worker-only snapshot limits and endpoints."""

    source_host: str
    source_port: int
    source_database: str
    source_user: str
    target_host: str
    target_port: int
    target_user: str
    target_database_prefix: str
    pgpassfile: Path
    custody_dir: Path
    max_export_bytes: int
    max_elapsed_seconds: float
    retention_seconds: int
    max_copies: int


def config_from_settings(settings: Settings) -> DemoSnapshotConfig:
    """Build the worker config from explicit Settings; fail closed.

    Default OFF: an enabled snapshot worker requires every field to be
    explicitly configured; any gap is a safe misconfiguration, never a
    fallback to an ambient endpoint.
    """
    if not settings.DEMO_SNAPSHOT_ENABLED:
        raise DemoSnapshotError(
            CODE_DISABLED,
            "Demo snapshot worker is disabled (DEMO_SNAPSHOT_ENABLED is not true).",
        )

    def _required(name: str, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise DemoSnapshotError(
                CODE_MISCONFIGURED,
                f"Demo snapshot worker is missing the {name} configuration.",
            )
        return normalized

    source_host = _required("DEMO_SNAPSHOT_SOURCE_HOST", settings.DEMO_SNAPSHOT_SOURCE_HOST)
    target_host = _required("DEMO_SNAPSHOT_TARGET_HOST", settings.DEMO_SNAPSHOT_TARGET_HOST)
    source_database = _required(
        "DEMO_SNAPSHOT_SOURCE_DATABASE", settings.DEMO_SNAPSHOT_SOURCE_DATABASE
    )
    if not _IDENT_RE.fullmatch(source_database):
        raise DemoSnapshotError(
            CODE_MISCONFIGURED,
            "DEMO_SNAPSHOT_SOURCE_DATABASE is not a valid PostgreSQL identifier.",
        )
    source_user = _required("DEMO_SNAPSHOT_SOURCE_USER", settings.DEMO_SNAPSHOT_SOURCE_USER)
    target_user = _required("DEMO_SNAPSHOT_TARGET_USER", settings.DEMO_SNAPSHOT_TARGET_USER)
    if not _IDENT_RE.fullmatch(target_user):
        raise DemoSnapshotError(
            CODE_MISCONFIGURED,
            "DEMO_SNAPSHOT_TARGET_USER is not a valid PostgreSQL identifier.",
        )

    custody_raw = _required("DEMO_SNAPSHOT_CUSTODY_DIR", settings.DEMO_SNAPSHOT_CUSTODY_DIR)
    passfile_raw = _required("DEMO_SNAPSHOT_PGPASSFILE", settings.DEMO_SNAPSHOT_PGPASSFILE)
    custody_dir = Path(custody_raw)
    pgpassfile = Path(passfile_raw)
    if not custody_dir.is_absolute():
        raise DemoSnapshotError(
            CODE_MISCONFIGURED, "DEMO_SNAPSHOT_CUSTODY_DIR must be an absolute path."
        )
    if not pgpassfile.is_absolute():
        raise DemoSnapshotError(
            CODE_MISCONFIGURED, "DEMO_SNAPSHOT_PGPASSFILE must be an absolute path."
        )

    if settings.DEMO_SNAPSHOT_MAX_EXPORT_BYTES <= 0:
        raise DemoSnapshotError(
            CODE_MISCONFIGURED, "DEMO_SNAPSHOT_MAX_EXPORT_BYTES must be positive."
        )
    if settings.DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS <= 0:
        raise DemoSnapshotError(
            CODE_MISCONFIGURED, "DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS must be positive."
        )
    if settings.DEMO_SNAPSHOT_RETENTION_SECONDS <= 0:
        raise DemoSnapshotError(
            CODE_MISCONFIGURED, "DEMO_SNAPSHOT_RETENTION_SECONDS must be positive."
        )
    if settings.DEMO_SNAPSHOT_MAX_COPIES <= 0:
        raise DemoSnapshotError(
            CODE_MISCONFIGURED, "DEMO_SNAPSHOT_MAX_COPIES must be positive."
        )

    return DemoSnapshotConfig(
        source_host=source_host,
        source_port=int(settings.DEMO_SNAPSHOT_SOURCE_PORT),
        source_database=source_database,
        source_user=source_user,
        target_host=target_host,
        target_port=int(settings.DEMO_SNAPSHOT_TARGET_PORT),
        target_user=target_user,
        target_database_prefix="demo_snap",
        pgpassfile=pgpassfile,
        custody_dir=custody_dir,
        max_export_bytes=int(settings.DEMO_SNAPSHOT_MAX_EXPORT_BYTES),
        max_elapsed_seconds=float(settings.DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS),
        retention_seconds=int(settings.DEMO_SNAPSHOT_RETENTION_SECONDS),
        max_copies=int(settings.DEMO_SNAPSHOT_MAX_COPIES),
    )


# ---------------------------------------------------------------------------
# Custody directory and manifest
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SnapshotManifest:
    """Private (0600) durable job state; the handoff record for 222/223/224.

    ``target_db`` is retained so later stages can address the exact copy;
    it must never be rendered to stdout/stderr/logs/public output.
    """

    job_id: str
    state: str
    created_at: float
    target_db: str
    capture_started_at: float | None = None
    capture_finished_at: float | None = None
    restore_finished_at: float | None = None
    export_bytes: int = 0
    failure_code: str | None = None
    schema_version: int = _MANIFEST_SCHEMA_VERSION
    # Objective 223 file stage (absent until the files job records it).
    files_state: str | None = None
    files_failure_code: str | None = None
    files_verified_at: float | None = None
    files_bytes: int = 0
    files_count: int = 0

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "state": self.state,
            "created_at": self.created_at,
            "target_db": self.target_db,
            "capture_started_at": self.capture_started_at,
            "capture_finished_at": self.capture_finished_at,
            "restore_finished_at": self.restore_finished_at,
            "export_bytes": self.export_bytes,
            "failure_code": self.failure_code,
            "files_state": self.files_state,
            "files_failure_code": self.files_failure_code,
            "files_verified_at": self.files_verified_at,
            "files_bytes": self.files_bytes,
            "files_count": self.files_count,
        }


def _validate_custody_dir(custody_dir: Path) -> None:
    """Refuse symlinked (any component), missing or group/world-accessible custody roots."""
    # No symlink traversal anywhere in the explicitly configured path:
    # a symlinked parent would silently move the custody tree (and its
    # 0700 boundary) to an operator-unreviewed location.
    current = custody_dir
    while True:
        try:
            st = current.lstat()
        except FileNotFoundError as exc:
            raise DemoSnapshotError(
                CODE_CUSTODY_UNSAFE, "Demo snapshot custody directory does not exist."
            ) from exc
        except OSError:
            # PermissionDenied / NotADirectory / any other stat failure
            # on ANY component: fail closed with the fixed safe code and
            # message — never a raw exception that could expose the
            # private custody path in a traceback.
            raise DemoSnapshotError(
                CODE_CUSTODY_UNSAFE,
                "Demo snapshot custody path could not be verified.",
            ) from None
        if stat_module.S_ISLNK(st.st_mode):
            raise DemoSnapshotError(
                CODE_CUSTODY_UNSAFE,
                "Demo snapshot custody path must not contain symlinks.",
            )
        parent = current.parent
        if parent == current:
            break
        current = parent
    st = custody_dir.lstat()
    if not stat_module.S_ISDIR(st.st_mode):
        raise DemoSnapshotError(
            CODE_CUSTODY_UNSAFE, "Demo snapshot custody path is not a real directory."
        )
    if st.st_mode & (stat_module.S_IRWXG | stat_module.S_IRWXO):
        raise DemoSnapshotError(
            CODE_CUSTODY_UNSAFE,
            "Demo snapshot custody directory must be mode 0700 (owner-only).",
        )


def validate_custody_dir(custody_dir: Path) -> None:
    """Public worker-internal alias of the private custody check.

    Exposed for the 222/223 worker siblings so every demo worker command
    enforces the identical custody boundary (no symlinks, owner-only
    0700) with the identical safe error vocabulary.
    """
    _validate_custody_dir(custody_dir)


def list_job_dirs(custody_dir: Path) -> list[Path]:
    """Public worker-internal alias (closed job-name law, no symlinks)."""
    return _list_job_dirs(custody_dir)


def read_manifest(job_dir: Path) -> SnapshotManifest | None:
    """Public worker-internal alias of the private manifest reader."""
    return _read_manifest(job_dir)


def write_manifest(job_dir: Path, manifest: SnapshotManifest) -> None:
    """Public worker-internal alias of the private manifest writer."""
    _write_manifest(job_dir, manifest)


def acquire_fence(custody_dir: Path) -> int:
    """Public worker-internal alias of the single-worker flock fence."""
    return _acquire_fence(custody_dir)


def release_fence(fd: int) -> None:
    """Public worker-internal alias of the fence release."""
    _release_fence(fd)


def _atomic_write_private(path: Path, data: bytes) -> None:
    """Write a 0600 file atomically without following symlinks."""
    tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)


def _write_manifest(job_dir: Path, manifest: SnapshotManifest) -> None:
    _atomic_write_private(job_dir / _MANIFEST_NAME, (json.dumps(manifest.to_json(), sort_keys=True) + "\n").encode("utf-8"))


def _read_manifest(job_dir: Path) -> SnapshotManifest | None:
    try:
        raw = (job_dir / _MANIFEST_NAME).read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
        return None
    try:
        return SnapshotManifest(
            job_id=str(payload["job_id"]),
            state=str(payload["state"]),
            created_at=float(payload["created_at"]),
            target_db=str(payload["target_db"]),
            capture_started_at=(
                float(payload["capture_started_at"])
                if payload.get("capture_started_at") is not None
                else None
            ),
            capture_finished_at=(
                float(payload["capture_finished_at"])
                if payload.get("capture_finished_at") is not None
                else None
            ),
            restore_finished_at=(
                float(payload["restore_finished_at"])
                if payload.get("restore_finished_at") is not None
                else None
            ),
            export_bytes=int(payload.get("export_bytes") or 0),
            failure_code=(str(payload["failure_code"]) if payload.get("failure_code") else None),
            files_state=(str(payload["files_state"]) if payload.get("files_state") else None),
            files_failure_code=(
                str(payload["files_failure_code"])
                if payload.get("files_failure_code")
                else None
            ),
            files_verified_at=(
                float(payload["files_verified_at"])
                if payload.get("files_verified_at") is not None
                else None
            ),
            files_bytes=int(payload.get("files_bytes") or 0),
            files_count=int(payload.get("files_count") or 0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _list_job_dirs(custody_dir: Path) -> list[Path]:
    try:
        entries = sorted(custody_dir.iterdir())
    except OSError:
        return []
    result: list[Path] = []
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_dir():
                continue
            if not re.fullmatch(r"snap-[0-9a-f]{32}", entry.name):
                continue
        except OSError:
            continue
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Single-worker cross-process fence (race-safe kernel flock)
# ---------------------------------------------------------------------------


def _acquire_fence(custody_dir: Path) -> int:
    """Take the single-worker fence; returns the held lock fd.

    The lock is a kernel ``flock`` on the custody directory's fence file:
    acquisition and holder death are serialized by the kernel itself, so
    there is no stale-PID detection, no O_EXCL unlink/retry race and no
    PID-reuse ambiguity. A live holder cannot be dislodged; a dead holder
    (crash, SIGKILL) releases the lock automatically.
    """
    fence_path = custody_dir / _FENCE_NAME
    try:
        # O_NOFOLLOW: a planted symlink fence must not redirect the lock
        # to an arbitrary file; it fails closed as "could not be acquired".
        fd = os.open(fence_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        raise DemoSnapshotError(
            CODE_FENCE_HELD, "Demo snapshot worker fence could not be acquired."
        ) from None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise DemoSnapshotError(
            CODE_FENCE_HELD, "Another demo snapshot worker is already running."
        ) from None
    return fd


def _release_fence(fd: int) -> None:
    """Release and close a held fence fd (idempotent, never raises)."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Secret handling and redaction
# ---------------------------------------------------------------------------


def _read_passfile_passwords(pgpassfile: Path, config: DemoSnapshotConfig) -> list[str]:
    """Read the exact passwords this worker uses (never rendered).

    Matches the worker's hosts and users, including ``*`` wildcard fields,
    so every credential the tools could present is in the redaction set.
    """
    passwords: list[str] = []
    try:
        raw = pgpassfile.read_text(encoding="utf-8")
    except OSError:
        return passwords
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.count(":") < 4:
            continue
        host, port, database, user, password = line.split(":", 4)
        if host in ("*", config.source_host, config.target_host) and user in (
            "*",
            config.source_user,
            config.target_user,
        ):
            passwords.append(password)
    return passwords


def _redact(message: str, secrets: Sequence[str]) -> str:
    redacted = str(message)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


# ---------------------------------------------------------------------------
# PostgreSQL client tooling (worker image only)
# ---------------------------------------------------------------------------


def _pg_env(pgpassfile: Path) -> dict[str, str]:
    """Minimal explicit environment for the PG client tools.

    Only the variables the tools need are present. The ambient worker
    environment is never inherited, in particular not provider
    credentials or application DSNs, so the source tools can never
    obtain provider substitution capability.
    """
    return {
        "PATH": os.environ.get(
            "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        ),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "PGPASSFILE": str(pgpassfile),
        "PGCONNECT_TIMEOUT": str(_PG_CONNECT_TIMEOUT),
    }


def _require_pg_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DemoSnapshotError(
            CODE_MISCONFIGURED,
            "PostgreSQL 16 client tooling is not installed in this worker image.",
        )
    return path


def _tail_error(stderr_file: Path, secrets: Sequence[str]) -> str:
    try:
        raw = stderr_file.read_bytes()[-_STDERR_TAIL_BYTES:]
    except OSError:
        return ""
    return _redact(raw.decode("utf-8", errors="replace"), secrets).strip()


@dataclass(frozen=True, slots=True)
class _CappedRunResult:
    """Bounded outcome of one PG client tool invocation."""

    returncode: int
    stderr_tail: str
    stdout_tail: str = ""


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _kill_group_quiet(proc: subprocess.Popen[bytes]) -> None:
    """SIGKILL the whole process group (the child and any descendants)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _pump_stdout(
    proc: subprocess.Popen[bytes],
    *,
    deadline: float,
    cancel_event: threading.Event | None,
    on_chunk: Callable[[bytes], None],
    elapsed_code: str,
    stream_code: str = CODE_SOURCE_DUMP_FAILED,
) -> None:
    """Stream the tool's stdout through ``on_chunk`` until EOF.

    Deadline and cancellation are checked on every poll, so a silent
    child cannot defeat the caps. A byte-cap error raised by
    ``on_chunk`` propagates to the caller, which kills the process group.
    A failed select or read is a STREAM failure, never EOF: it fails
    closed with a safe code so the caller can kill the process group;
    a broken pipe must not look like a clean completion.
    """
    stdout = proc.stdout
    if stdout is None:
        return
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise DemoSnapshotError(
                    CODE_SOURCE_DUMP_CANCELLED, "Demo snapshot job was cancelled."
                )
            if time.monotonic() > deadline:
                raise DemoSnapshotError(
                    elapsed_code,
                    "Demo snapshot stopped by its configured time limit.",
                )
            try:
                readable, _, _ = select.select([stdout], [], [], _POLL_SECONDS)
            except (OSError, ValueError) as exc:
                raise DemoSnapshotError(
                    stream_code, "Demo snapshot tool output stream failed."
                ) from exc
            if not readable:
                continue
            try:
                chunk = os.read(stdout.fileno(), _READ_CHUNK_BYTES)
            except OSError as exc:
                raise DemoSnapshotError(
                    stream_code, "Demo snapshot tool output stream failed."
                ) from exc
            if not chunk:
                break
            on_chunk(chunk)
    finally:
        try:
            stdout.close()
        except OSError:
            pass


def _wait_enforced(
    proc: subprocess.Popen[bytes],
    *,
    deadline: float,
    cancel_event: threading.Event | None,
    elapsed_code: str,
) -> None:
    """Keep enforcing the caps until the child exits.

    Covers the case where the child closes stdout and then hangs: pipe
    EOF alone never means the job finished, so the caps keep applying
    until the process group is gone.
    """
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            raise DemoSnapshotError(
                CODE_SOURCE_DUMP_CANCELLED, "Demo snapshot job was cancelled."
            )
        if time.monotonic() > deadline:
            raise DemoSnapshotError(
                elapsed_code,
                "Demo snapshot stopped by its configured time limit.",
            )
        time.sleep(_POLL_SECONDS)


def _run_tool(
    cmd: Sequence[str],
    *,
    env: dict[str, str],
    workdir: Path,
    deadline: float,
    cancel_event: threading.Event | None,
    secrets: Sequence[str],
    on_chunk: Callable[[bytes], None] | None = None,
    stdout_tail_bytes: int | None = None,
    elapsed_code: str = CODE_SOURCE_DUMP_CAP_ELAPSED,
    stream_code: str = CODE_SOURCE_DUMP_FAILED,
) -> _CappedRunResult:
    """Run a bounded PG client tool with enforced deadline/cancel/byte cap.

    The tool runs in its own session (process group); any cap breach or
    cancellation SIGKILLs the entire group before a complete claim can
    stand. ``on_chunk`` receives each stdout chunk (the dump archive is
    streamed and counted there; with no ``on_chunk`` stdout is
    discarded unless ``stdout_tail_bytes`` requests a bounded tail, which
    is redacted and returned). stderr goes to a private 0600 file, is
    redacted to a bounded tail and removed.
    """
    tail_state: dict[str, bytes] = {"tail": b""}

    def _tail_chunk(chunk: bytes) -> None:
        limit = int(stdout_tail_bytes)
        tail_state["tail"] = (tail_state["tail"] + chunk)[-limit:]

    stderr_file = workdir / f"stderr-{uuid.uuid4().hex[:8]}"
    try:
        stderr_fd = os.open(
            stderr_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
    except OSError:
        raise DemoSnapshotError(
            CODE_SOURCE_DUMP_FAILED, "Demo snapshot export could not be started."
        ) from None
    stderr_handle = os.fdopen(stderr_fd, "wb")
    try:
        proc = subprocess.Popen(
            list(cmd),
            stdout=subprocess.PIPE
            if (on_chunk is not None or stdout_tail_bytes is not None)
            else subprocess.DEVNULL,
            stderr=stderr_handle,
            env=env,
            cwd=str(workdir),
            start_new_session=True,
        )
    except Exception:
        stderr_handle.close()
        _unlink_quiet(stderr_file)
        raise DemoSnapshotError(
            CODE_SOURCE_DUMP_FAILED, "Demo snapshot export could not be started."
        ) from None
    try:
        try:
            if on_chunk is not None:
                _pump_stdout(
                    proc,
                    deadline=deadline,
                    cancel_event=cancel_event,
                    on_chunk=on_chunk,
                    elapsed_code=elapsed_code,
                    stream_code=stream_code,
                )
            elif stdout_tail_bytes is not None:
                _pump_stdout(
                    proc,
                    deadline=deadline,
                    cancel_event=cancel_event,
                    on_chunk=_tail_chunk,
                    elapsed_code=elapsed_code,
                    stream_code=stream_code,
                )
            _wait_enforced(
                proc,
                deadline=deadline,
                cancel_event=cancel_event,
                elapsed_code=elapsed_code,
            )
            returncode = proc.wait(timeout=10)
        except DemoSnapshotError:
            _kill_group_quiet(proc)
            raise
        except Exception:
            # Fail closed on ANY unexpected error: kill and reap the
            # whole process group before the exception can escape, so
            # no live child or descendant survives a tool failure.
            _kill_group_quiet(proc)
            raise
    finally:
        stderr_tail = _tail_error(stderr_file, secrets)
        stderr_handle.close()
        _unlink_quiet(stderr_file)
    stdout_tail = _redact(
        tail_state["tail"].decode("utf-8", errors="replace"), secrets
    ).strip()
    return _CappedRunResult(
        returncode=returncode, stderr_tail=stderr_tail, stdout_tail=stdout_tail
    )


# ---------------------------------------------------------------------------
# Target-service operations
# ---------------------------------------------------------------------------


def _psql_target_admin(
    config: DemoSnapshotConfig,
    database: str,
    sql: str,
    *,
    env: dict[str, str],
    workdir: Path,
    deadline: float,
    secrets: Sequence[str],
    elapsed_code: str,
    capture_output: bool = False,
) -> _CappedRunResult:
    psql = _require_pg_tool("psql")
    cmd = [
        psql,
        "-h", config.target_host,
        "-p", str(config.target_port),
        "-U", config.target_user,
        "-d", database,
        "-v", "ON_ERROR_STOP=1",
        "-w",  # never prompt; PGPASSFILE only
        "-tA",  # tuples only, no headers: safe for the bounded checks
        "-qc", sql,
    ]
    return _run_tool(
        cmd,
        env=env,
        workdir=workdir,
        deadline=deadline,
        cancel_event=None,
        secrets=secrets,
        stdout_tail_bytes=64 * 1024 if capture_output else None,
        elapsed_code=elapsed_code,
        # A stream failure during a bounded check fails under the same
        # context code the check already reports.
        stream_code=elapsed_code,
    )


def _target_ops(
    config: DemoSnapshotConfig,
    *,
    workdir: Path,
    secrets: Sequence[str],
):
    env = _pg_env(config.pgpassfile)

    def create_database(target_db: str, deadline: float) -> None:
        # Defense in depth: the config layer already validated the target
        # user; refuse before any interpolation regardless.
        if not _IDENT_RE.fullmatch(config.target_user):
            raise DemoSnapshotError(CODE_UNEXPECTED, "Demo snapshot target user is invalid.")
        if not _IDENT_RE.fullmatch(target_db):
            raise DemoSnapshotError(CODE_UNEXPECTED, "Demo snapshot target name is invalid.")
        # Separate-service contract guard, BEFORE any create: the target
        # service must never be the source cluster. Quick same-endpoint
        # check first, then the authoritative bounded target-catalog check
        # (covers host aliases); fail closed if separation cannot be
        # proven. No database is created before this guard passes.
        if (
            str(config.source_host).strip() == str(config.target_host).strip()
            and int(config.source_port) == int(config.target_port)
        ):
            raise DemoSnapshotError(
                CODE_TARGET_NOT_SEPARATE,
                "Demo snapshot target is configured as the source cluster.",
            )
        separate = _psql_target_admin(
            config,
            "postgres",
            # Identifier validated in config_from_settings, so this
            # literal cannot break out of the statement.
            "SELECT EXISTS(SELECT 1 FROM pg_database "
            f"WHERE datname = '{config.source_database}')",
            env=env,
            workdir=workdir,
            deadline=deadline,
            secrets=secrets,
            elapsed_code=CODE_TARGET_NOT_SEPARATE,
            capture_output=True,
        )
        if separate.returncode != 0:
            raise DemoSnapshotError(
                CODE_TARGET_NOT_SEPARATE,
                "Demo snapshot target separation could not be verified.",
            )
        # Fail closed on the catalog proof: only an EXACT boolean "f"
        # (source database absent from the target catalog) allows a
        # CREATE. "t", empty and every malformed output reject.
        separate_out = separate.stdout_tail.strip()
        if separate_out == "t":
            raise DemoSnapshotError(
                CODE_TARGET_NOT_SEPARATE,
                "Demo snapshot target service is not separate from the source.",
            )
        if separate_out != "f":
            raise DemoSnapshotError(
                CODE_TARGET_NOT_SEPARATE,
                "Demo snapshot target separation could not be verified.",
            )
        # One absolute job deadline (passed in) covers ALL of the create
        # steps plus the later dump and restore: a slow create cannot
        # consume a second full budget.
        # 1) Create the raw copy CLOSED: while ALLOW_CONNECTIONS is false
        # no role at all can connect, so the ACL restriction below has no
        # raw-access window.
        result = _psql_target_admin(
            config,
            "postgres",
            f'CREATE DATABASE "{target_db}" WITH ALLOW_CONNECTIONS = false',
            env=env,
            workdir=workdir,
            deadline=deadline,
            secrets=secrets,
            elapsed_code=CODE_TARGET_CREATE_FAILED,
        )
        if result.returncode != 0:
            raise DemoSnapshotError(
                CODE_TARGET_CREATE_FAILED,
                "Demo snapshot target database could not be created.",
            )
        # 2) Restrict while still closed: PUBLIC loses CONNECT, only the
        # configured target user receives it.
        revoke = _psql_target_admin(
            config,
            "postgres",
            f'REVOKE CONNECT ON DATABASE "{target_db}" FROM PUBLIC; '
            f'GRANT CONNECT ON DATABASE "{target_db}" TO "{config.target_user}"',
            env=env,
            workdir=workdir,
            deadline=deadline,
            secrets=secrets,
            elapsed_code=CODE_TARGET_CREATE_FAILED,
        )
        if revoke.returncode != 0:
            raise DemoSnapshotError(
                CODE_TARGET_CREATE_FAILED,
                "Demo snapshot target database isolation could not be applied.",
            )
        # 3) Open only after the restriction is in place. The fresh
        # database stays empty: the trusted extensions required by the
        # business migration chain (0001: pgcrypto, citext) travel inside
        # the dump archive itself (explicit -e selection, proven safe with
        # -n public on PostgreSQL 16), so nothing is pre-bootstrapped and
        # the restore's --clean --if-exists has nothing to conflict with.
        result = _psql_target_admin(
            config,
            "postgres",
            f'ALTER DATABASE "{target_db}" WITH ALLOW_CONNECTIONS = true',
            env=env,
            workdir=workdir,
            deadline=deadline,
            secrets=secrets,
            elapsed_code=CODE_TARGET_CREATE_FAILED,
        )
        if result.returncode != 0:
            raise DemoSnapshotError(
                CODE_TARGET_CREATE_FAILED,
                "Demo snapshot target database could not be opened.",
            )

    def drop_database(target_db: str) -> bool:
        if not _IDENT_RE.fullmatch(target_db):
            return False
        deadline = time.monotonic() + 60
        result = _psql_target_admin(
            config,
            "postgres",
            f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)',
            env=env,
            workdir=workdir,
            deadline=deadline,
            secrets=secrets,
            elapsed_code=CODE_CLEANUP_FAILED,
        )
        return result.returncode == 0

    def database_exists(target_db: str) -> bool | None:
        """Authoritative bounded existence check; ``None`` = cannot verify.

        Lets cleanup distinguish a create that was denied before any
        database was made (nothing to clean) from a database that may be
        present (which an unprivileged role might not be able to drop).
        """
        if not _IDENT_RE.fullmatch(target_db):
            return None
        deadline = time.monotonic() + 60
        result = _psql_target_admin(
            config,
            "postgres",
            # Identifier is validated to the conservative character set
            # above, so this literal cannot break out of the statement.
            f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = '{target_db}')",
            env=env,
            workdir=workdir,
            deadline=deadline,
            secrets=secrets,
            elapsed_code=CODE_CLEANUP_FAILED,
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        # Exact boolean only: anything else (empty, "tf", "true", ...)
        # is "cannot verify" and must never be guessed.
        out = result.stdout_tail.strip()
        if out == "t":
            return True
        if out == "f":
            return False
        return None

    def restore(archive_path: Path, target_db: str, deadline: float) -> None:
        pg_restore = _require_pg_tool("pg_restore")
        # The target database is always a FRESH UNIQUE empty database
        # created by this job. --clean --if-exists is safe here: nothing
        # was pre-bootstrapped (the required trusted extensions travel in
        # the archive and are restored before the tables), so the schema
        # clean has no dependent objects to conflict with.
        cmd = [
            pg_restore,
            "-h", config.target_host,
            "-p", str(config.target_port),
            "-U", config.target_user,
            "-d", target_db,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            str(archive_path),
        ]
        result = _run_tool(
            cmd,
            env=env,
            workdir=workdir,
            deadline=deadline,
            cancel_event=None,
            secrets=secrets,
            elapsed_code=CODE_TARGET_RESTORE_CAP_ELAPSED,
        )
        if result.returncode != 0:
            raise DemoSnapshotError(
                CODE_TARGET_RESTORE_FAILED,
                "Demo snapshot restore failed.",
            )

    return _TargetOpsBundle(
        create_database=create_database,
        drop_database=drop_database,
        restore=restore,
        database_exists=database_exists,
    )


@dataclass(frozen=True, slots=True)
class _TargetOpsBundle:
    create_database: Callable[[str, float], None]
    drop_database: Callable[[str], bool]
    restore: Callable[[Path, str, float], None]
    database_exists: Callable[[str], bool | None]


TargetOps = _TargetOpsBundle


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DemoSnapshotJobResult:
    """Safe, renderable outcome. ``target_db`` is internal-only."""

    state: str
    failure_code: str | None
    export_bytes: int
    elapsed_ms: int
    target_db: str = field(repr=False, default="")


def _clean_job_files(job_dir: Path) -> bool:
    """Exact-leaf, dirfd-anchored cleanup of the 223 ``files/`` subtree.

    Everything is opened through held descriptors: the anchored job-dir
    handle (every ancestor no-follow), then ``files`` through that held
    handle, and the private manifest through a bounded anchored read on
    the held ``files`` fd. No pathname is re-opened after verification.
    The ``files/`` directory identity measured on the held fd must
    equal the manifest-recorded identity BEFORE the fd is closed.
    Cleanup runs only when that manifest records the exact flat leaves
    the files worker created, and every leaf name must match the
    generated flat filename grammar before it is handed to the anchored
    removal helper. Cleanup delegates exact-leaf removal to the catalog
    filesystem boundary and then PROVES the directory is gone through
    the same held handle. A missing, unreadable or inconsistent
    manifest, a tampered identity, a grammar-violating leaf name, or a
    surviving directory is a cleanup FAILURE: artifacts are retained
    for operator inspection.
    """
    try:
        job_handle = catfs.open_anchored_handle(job_dir)
    except catfs.CatalogRefreshSealError:
        return False
    try:
        job_handle.assert_name_binding(str(job_dir))
        try:
            files_fd = os.open(
                "files",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=job_handle.dir_fd,
            )
        except FileNotFoundError:
            return True  # absent: nothing owned to clean
        except OSError:
            return False
        try:
            try:
                manifest_raw = catfs.anchored_read_fd(
                    files_fd, _FILES_MANIFEST_NAME, _FILES_MANIFEST_MAX_BYTES
                )
                manifest = catfs.strict_json_bytes(
                    manifest_raw, _FILES_MANIFEST_NAME
                )
            except (OSError, catfs.CatalogRefreshSealError):
                return False
            if not isinstance(manifest, dict):
                return False
            identity = manifest.get("files_dir_identity")
            leaves = manifest.get("files")
            if not isinstance(identity, list) or len(identity) != 2:
                return False
            if (
                not isinstance(leaves, list)
                or len(leaves) > _FILES_MAX_LEAVES
                or not all(
                    isinstance(entry, dict) and isinstance(entry.get("leaf"), str)
                    for entry in leaves
                )
            ):
                return False
            try:
                expected_identity = (int(identity[0]), int(identity[1]))
            except (TypeError, ValueError):
                return False
            # The directory identity is measured on the HELD fd and must
            # match the manifest BEFORE anything is closed or removed.
            dir_st = os.fstat(files_fd)
            if (dir_st.st_dev, dir_st.st_ino) != expected_identity:
                return False
            created_names = [str(entry["leaf"]) for entry in leaves]
            if (
                len(set(created_names)) != len(created_names)
                or not all(_FILES_LEAF_NAME_RE.fullmatch(name) for name in created_names)
            ):
                return False
        finally:
            os.close(files_fd)
        created_names = created_names + [_FILES_MANIFEST_NAME]
        catfs.cleanup_staged_directory(
            job_handle.dir_fd, "files", expected_identity, created_names
        )
        # Prove absence through the SAME held handle; the helper is
        # best-effort and a surviving directory is a failed cleanup.
        try:
            probe = os.open(
                "files",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=job_handle.dir_fd,
            )
        except FileNotFoundError:
            probe = None
        except OSError:
            return False
        if probe is not None:
            os.close(probe)
            return False
        job_handle.assert_name_binding(str(job_dir))
        return True
    except catfs.CatalogRefreshSealError:
        return False
    finally:
        job_handle.close()


def _cleanup_artifacts(
    ops: TargetOps,
    job_dir: Path,
    target_db: str,
) -> bool:
    """Remove partial dump and target DB; then the 223 display files.

    Ordering is load-bearing: the 223 display files are removed only
    AFTER the exact target database removal succeeds, so a failed DB
    drop keeps the files (and manifest) available for retry.
    ``True`` only when every step completed.
    """
    clean = True
    try:
        (job_dir / _DUMP_NAME).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        clean = False
    # Authoritative bounded existence check before dropping. A create that
    # was denied before making anything (e.g. NOCREATEDB) leaves no
    # database to clean and must not be reported as a failed cleanup; a
    # database that is present, or whose existence cannot be verified, is
    # dropped, and a failed drop of possibly-present data stays
    # CLEANUP_FAILED (never labeled clean).
    exists = ops.database_exists(target_db)
    if exists is not False and not ops.drop_database(target_db):
        clean = False
    if clean and not _clean_job_files(job_dir):
        clean = False
    return clean


def _recover_interrupted_jobs(
    config: DemoSnapshotConfig,
    ops: TargetOps,
) -> int:
    """Clean stale RUNNING/CLEANUP_FAILED jobs from a dead worker.

    Idempotent: only manifests in interrupted states are touched, and every
    step tolerates already-gone artifacts. Runs UNDER the fence, so a
    RUNNING manifest here always belongs to a dead process.
    """
    recovered = 0
    for job_dir in _list_job_dirs(config.custody_dir):
        manifest = _read_manifest(job_dir)
        if manifest is None or manifest.state not in (STATE_RUNNING, STATE_CLEANUP_FAILED):
            continue
        clean = _cleanup_artifacts(ops, job_dir, manifest.target_db)
        final_state = STATE_CLEANED if clean else STATE_CLEANUP_FAILED
        manifest.state = final_state
        if clean:
            manifest.failure_code = None
        _write_manifest(job_dir, manifest)
        recovered += 1
    return recovered


def _expire_copies(
    config: DemoSnapshotConfig,
    ops: TargetOps,
    now: float | None = None,
) -> int:
    """Expire retained copies past retention and enforce the budget.

    Every unpublished copy state (RAW_UNVERIFIED, DB_SANITIZED_UNPUBLISHED
    and DB_AND_FILES_VERIFIED_UNPUBLISHED) counts against retention and
    the finite copy budget: a sanitized-but-unpublished copy is still a
    private copy holding copy-derived data, and 224 is the only path
    that ever consumes it.
    """
    now = time.time() if now is None else now
    copies = []
    for job_dir in _list_job_dirs(config.custody_dir):
        manifest = _read_manifest(job_dir)
        if manifest is not None and manifest.state in (
            STATE_RAW_UNVERIFIED,
            STATE_DB_SANITIZED_UNPUBLISHED,
            STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
        ):
            copies.append((manifest.created_at, job_dir, manifest))
    copies.sort(key=lambda item: item[0])

    expired = [
        item for item in copies
        if (now - item[0]) > config.retention_seconds
    ]
    kept = [item for item in copies if item not in expired]
    overflow = kept[: max(0, len(kept) - config.max_copies)]

    removed = 0
    for _created, job_dir, manifest in expired + overflow:
        clean = _cleanup_artifacts(ops, job_dir, manifest.target_db)
        manifest.state = STATE_CLEANED
        if clean:
            manifest.failure_code = None
        else:
            manifest.state = STATE_CLEANUP_FAILED
            manifest.failure_code = CODE_CLEANUP_FAILED
        _write_manifest(job_dir, manifest)
        removed += 1
    return removed


def run_snapshot_job(
    config: DemoSnapshotConfig,
    *,
    cancel_event: threading.Event | None = None,
    ops: TargetOps | None = None,
) -> DemoSnapshotJobResult:
    """Run ONE bounded snapshot job. The complete custody+export+restore path.

    Raises ``DemoSnapshotError`` only for pre-job configuration/custody
    failures; every mid-job failure returns a safe result with a finite
    code and leaves no browser-readable artifact.
    """
    _validate_custody_dir(config.custody_dir)
    fence_fd = _acquire_fence(config.custody_dir)
    started = time.monotonic()
    try:
        workdir = config.custody_dir
        secrets = [
            * _read_passfile_passwords(config.pgpassfile, config),
        ]
        if ops is None:
            ops = _target_ops(config, workdir=workdir, secrets=secrets)

        _recover_interrupted_jobs(config, ops)
        _expire_copies(config, ops)

        job_id = f"snap-{uuid.uuid4().hex}"
        target_db = f"{config.target_database_prefix}_{uuid.uuid4().hex[:20]}"
        job_dir = config.custody_dir / job_id
        job_dir.mkdir(mode=0o700)

        manifest = SnapshotManifest(
            job_id=job_id,
            state=STATE_RUNNING,
            created_at=time.time(),
            target_db=target_db,
        )
        _write_manifest(job_dir, manifest)

        # ONE absolute deadline for the whole job: create + dump + restore
        # share it, so no phase can spend a second full budget.
        deadline = time.monotonic() + config.max_elapsed_seconds
        archive_path = job_dir / _DUMP_NAME
        try:
            # 1) Fresh unique target database on the separate demo service.
            ops.create_database(target_db, deadline)
            secrets = [*secrets, target_db, str(archive_path)]

            # 2) Consistent pg_dump as the SELECT-only source role.
            manifest.capture_started_at = time.time()
            env = _pg_env(config.pgpassfile)
            pg_dump = _require_pg_tool("pg_dump")
            dump_cmd = [
                pg_dump,
                "-h", config.source_host,
                "-p", str(config.source_port),
                "-U", config.source_user,
                "-d", config.source_database,
                # File-based custom format without -f writes to stdout
                # (official PostgreSQL 16 behavior), which is streamed and
                # counted by _account_chunk below.
                "--format=custom",
                # Positive allowlist: only the business public schema is
                # dumped; demo_control can never enter the archive.
                "--schema=public",
                # Fixed approved extension set required by migration 0001;
                # explicit -e selection is additive with -n public on
                # PostgreSQL 16, so the fresh copy restores them in the
                # same archive (nothing broader is ever included).
                "-e", "citext",
                "-e", "pgcrypto",
                "--no-owner",
                "--no-privileges",
            ]

            byte_count = 0

            def _account_chunk(chunk: bytes) -> None:
                nonlocal byte_count
                byte_count += len(chunk)
                if byte_count > config.max_export_bytes:
                    raise DemoSnapshotError(
                        CODE_SOURCE_DUMP_CAP_BYTES,
                        "Demo snapshot export exceeded its configured byte cap.",
                    )
                fd = os.open(
                    archive_path,
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    os.write(fd, chunk)
                finally:
                    os.close(fd)

            result = _run_tool(
                dump_cmd,
                env=env,
                workdir=workdir,
                deadline=deadline,
                cancel_event=cancel_event,
                secrets=secrets,
                on_chunk=_account_chunk,
            )
            manifest.capture_finished_at = time.time()
            manifest.export_bytes = byte_count
            if result.returncode != 0:
                raise DemoSnapshotError(
                    CODE_SOURCE_DUMP_FAILED,
                    "Demo snapshot export failed.",
                )
            if byte_count <= 0:
                raise DemoSnapshotError(
                    CODE_SOURCE_DUMP_FAILED,
                    "Demo snapshot export produced no data.",
                )

            # 3) Restore into the raw private copy.
            ops.restore(archive_path, target_db, deadline)
            manifest.restore_finished_at = time.time()

            # 4) Complete: explicit unverified/raw state, nothing published.
            manifest.state = STATE_RAW_UNVERIFIED
            _write_manifest(job_dir, manifest)
            return DemoSnapshotJobResult(
                state=STATE_RAW_UNVERIFIED,
                failure_code=None,
                export_bytes=byte_count,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                target_db=target_db,
            )
        except DemoSnapshotError as exc:
            clean = True
            try:
                clean = _cleanup_artifacts(ops, job_dir, target_db)
            except Exception:
                clean = False
            if clean:
                manifest.state = STATE_FAILED
                manifest.failure_code = exc.code
            else:
                manifest.state = STATE_CLEANUP_FAILED
                manifest.failure_code = CODE_CLEANUP_FAILED
            try:
                _write_manifest(job_dir, manifest)
            except OSError:
                pass
            return DemoSnapshotJobResult(
                state=manifest.state,
                failure_code=manifest.failure_code,
                export_bytes=0,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                target_db=target_db,
            )
        except Exception:
            clean = True
            try:
                clean = _cleanup_artifacts(ops, job_dir, target_db)
            except Exception:
                clean = False
            if clean:
                manifest.state = STATE_FAILED
                manifest.failure_code = CODE_UNEXPECTED
            else:
                manifest.state = STATE_CLEANUP_FAILED
                manifest.failure_code = CODE_CLEANUP_FAILED
            try:
                _write_manifest(job_dir, manifest)
            except OSError:
                pass
            return DemoSnapshotJobResult(
                state=manifest.state,
                failure_code=manifest.failure_code,
                export_bytes=0,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                target_db=target_db,
            )
    finally:
        _release_fence(fence_fd)


def recover_interrupted_jobs(config: DemoSnapshotConfig, *, ops: TargetOps | None = None) -> int:
    """Fenced recovery entry point (CLI ``recover``)."""
    _validate_custody_dir(config.custody_dir)
    fence_fd = _acquire_fence(config.custody_dir)
    try:
        workdir = config.custody_dir
        secrets = list(_read_passfile_passwords(config.pgpassfile, config))
        if ops is None:
            ops = _target_ops(config, workdir=workdir, secrets=secrets)
        return _recover_interrupted_jobs(config, ops)
    finally:
        _release_fence(fence_fd)


def expire_copies(config: DemoSnapshotConfig, *, ops: TargetOps | None = None) -> int:
    """Fenced expiry entry point (CLI ``expire``)."""
    _validate_custody_dir(config.custody_dir)
    fence_fd = _acquire_fence(config.custody_dir)
    try:
        workdir = config.custody_dir
        secrets = list(_read_passfile_passwords(config.pgpassfile, config))
        if ops is None:
            ops = _target_ops(config, workdir=workdir, secrets=secrets)
        return _expire_copies(config, ops)
    finally:
        _release_fence(fence_fd)


def count_raw_copies(config: DemoSnapshotConfig) -> int:
    """How many RAW_UNVERIFIED custody entries exist (safe to render)."""
    try:
        _validate_custody_dir(config.custody_dir)
    except DemoSnapshotError:
        return 0
    count = 0
    for job_dir in _list_job_dirs(config.custody_dir):
        manifest = _read_manifest(job_dir)
        if manifest is not None and manifest.state == STATE_RAW_UNVERIFIED:
            count += 1
    return count
