"""Operator-controlled request-capture facility: shared file store and control.

This module owns the bounded, default-OFF capture state that is shared across
the shipped worker processes through the ordinary local filesystem:

* a **manifest** file describing active capture sessions (armings),
* **atomic count-claim and storage-reservation** across processes using
  ``fcntl.flock`` (no per-worker counters, no distributed coordination),
* a **trusted directory store** with ``0700`` directory / ``0600`` artifact and
  control files, safe no-follow regular-file checks for control/artifact paths,
  and atomic publication so partial files are never labeled complete,
* **operator** arm/status/stop/cleanup logic usable from the CLI without
  constructing the HTTP app or a database,
* a **local-only** rejection diagnostic contextvar so the request policy can
  attach a precise structured reason to the capture without any public error,
  log, or content change.

Design constraints (objective 191, R1/R4/R7):

* Reading configuration alone never creates a capture window; a window exists
  only for an armed, not-yet-expired session.
* Exhaustion and expiration survive worker restarts and never re-arm.
* Count claims are consumed even if the later artifact write fails, so a
  failure cannot create an endless capture.
* Storage is accounted twice: a positive per-claim **reservation** at claim
  time, and the **actual** combined capture/record/temp footprint re-checked
  under the same lock at publication (both the per-capture budget and the
  global total), so real writes cannot exceed either budget.
* Artifacts may only be published against a claim that was actually issued for
  that session, and duplicate or stale-after-cleanup writes are rejected.
* Control and artifact paths are verified as regular files we own (no symlink /
  FIFO / non-regular targets); the manifest is opened no-follow, non-blocking
  and re-verified by fstat on the opened handle before any read, so a
  regular->FIFO swap is refused without blocking.
* Lock acquisition is bounded and non-blocking with a short retry and a safe
  error, so a stuck lock makes the caller skip (never block the request).
* ``cleanup`` removes only recognized owned artifact/partial names and
  preserves anything else in a session directory; history pruning drops only
  fileless, unreserved finished sessions so artifacts are never orphaned.
* On storage-full / write / permission / lock / masking failure the caller
  skips or marks the capture safely; this module never raises into auth,
  validation, admission, accounting, or forwarding.
* No raw request content is ever written here; the caller passes already
  masked bytes. No raw tempfiles, spools, or intermediate artifacts.
* No new persistent database schema, admin UI, remote export, or dependency.
* The trust model is an operator-owned local directory, not a hostile
  same-UID filesystem jail.
"""

from __future__ import annotations

import contextvars
import fcntl
import json
import logging
import math
import os
import re
import stat
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

__all__ = [
    "build_capture_facility",
    "CAPTURES_DIR_NAME",
    "LOCK_NAME",
    "MANIFEST_NAME",
    "CaptureFacilityConfig",
    "CaptureSession",
    "CaptureStore",
    "CaptureStoreError",
    "CAPTURE_REJECTION_STATE_KEY",
    "clear_capture_rejection",
    "get_capture_rejection",
    "get_scope_capture_rejection",
    "record_capture_rejection",
    "record_scope_capture_rejection",
    "reset_capture_rejection",
    "CAPTURE_PROVENANCE_STATE_KEY",
    "get_scope_capture_provenance",
    "record_scope_capture_provenance",
]


class CaptureStoreError(ValueError):
    """Safe, low-detail error for the capture facility.

    The message is a fixed reason code; it never contains request content.
    """

    def __init__(self, reason: str = "capture_store_error") -> None:
        super().__init__(reason)
        self.reason = reason


MANIFEST_NAME = "capture.manifest.json"
LOCK_NAME = ".capture.lock"
CAPTURES_DIR_NAME = "captures"

_SCHEMA_VERSION = 1
# Hard safety caps for reading/parsing a manifest (independent of the
# operator-configured session cap) so a tampered manifest cannot force an
# unbounded parse or allocation.
_MAX_MANIFEST_BYTES = 1 * 1024 * 1024
_MAX_SESSIONS_HARD = 4096
_MAX_COUNT_HARD = 1_000_000
# Bounded, non-blocking lock acquisition: retry for a short total window then
# fail safely. Kept well under one request so a stuck lock cannot block the
# capture observer (which skips on the safe error).
_LOCK_WAIT_SECONDS = 0.5
_LOCK_RETRY_SECONDS = 0.02
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SESSION_ID_PATTERN = re.compile(r"^cap-[0-9a-f]{32}$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
# Overhead added to the base64-expanded body budget to cover metadata, the
# concise record sidecar, and temporary files in the per-capture reservation.
_METADATA_OVERHEAD_BYTES = 256 * 1024
# Recognized owned artifact/partial names that cleanup may remove; anything
# else inside a session directory is preserved.
_OWNED_CAPTURE = re.compile(r"^[A-Za-z0-9._-]{1,64}\.capture\.json$")
_OWNED_RECORD = re.compile(r"^[A-Za-z0-9._-]{1,64}\.record\.json$")
_OWNED_PARTIAL = re.compile(r"^\.partial-[A-Za-z0-9._-]*\.tmp$")


@dataclass(frozen=True, slots=True)
class CaptureFacilityConfig:
    """Immutable operator configuration for the capture facility."""

    enabled: bool
    root: Path
    body_budget_bytes: int
    total_storage_bytes: int
    max_count: int
    max_ttl_seconds: int
    deployed_revision: str
    revision_provenance: str
    app_version: str
    default_count: int = 1
    default_ttl_seconds: int = 300
    # Bounded history: total sessions retained in the manifest (active plus
    # most-recent finished). Keeps the control file from growing unbounded.
    max_sessions: int = 128


@dataclass(frozen=True, slots=True)
class CaptureSession:
    """One armed capture session (a finite, expiring capture window)."""

    session_id: str
    endpoint: str
    key_uuid: str | None
    count: int
    claimed: int
    created_at: float
    expires_at: float
    stopped: bool
    bytes_reserved: int
    published: int = 0
    claim_reserve: int = 0

    def status(self, now: float) -> str:
        if self.stopped:
            return "stopped"
        if now >= self.expires_at:
            return "expired"
        if self.claimed >= self.count:
            return "exhausted"
        return "active"

    @property
    def remaining(self) -> int:
        return max(0, self.count - self.claimed)


def _session_to_dict(session: CaptureSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "endpoint": session.endpoint,
        "key_uuid": session.key_uuid,
        "count": session.count,
        "claimed": session.claimed,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "stopped": session.stopped,
        "bytes_reserved": session.bytes_reserved,
        "published": session.published,
        "claim_reserve": session.claim_reserve,
    }


def _require_int(data: dict[str, Any], key: str, *, minimum: int, default: int = 0) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CaptureStoreError("capture_manifest_unreadable")
    return value


def _require_nonneg_finite_number(data: dict[str, Any], key: str) -> float:
    value = data.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CaptureStoreError("capture_manifest_unreadable")
    if not math.isfinite(value) or value < 0:
        raise CaptureStoreError("capture_manifest_unreadable")
    return float(value)


def _session_from_dict(data: dict[str, Any]) -> CaptureSession:
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise CaptureStoreError("capture_manifest_unreadable")
    endpoint = data.get("endpoint")
    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("/")
        or len(endpoint) > 2048
    ):
        raise CaptureStoreError("capture_manifest_unreadable")
    key_uuid = data.get("key_uuid")
    if key_uuid is not None and (
        not isinstance(key_uuid, str) or not _UUID_PATTERN.fullmatch(key_uuid)
    ):
        raise CaptureStoreError("capture_manifest_unreadable")
    count = _require_int(data, "count", minimum=1, default=0)
    if count > _MAX_COUNT_HARD:
        raise CaptureStoreError("capture_manifest_unreadable")
    claimed = _require_int(data, "claimed", minimum=0)
    created_at = _require_nonneg_finite_number(data, "created_at")
    expires_at = _require_nonneg_finite_number(data, "expires_at")
    stopped = data.get("stopped", False)
    if not isinstance(stopped, bool):
        raise CaptureStoreError("capture_manifest_unreadable")
    bytes_reserved = _require_int(data, "bytes_reserved", minimum=0)
    published = _require_int(data, "published", minimum=0)
    claim_reserve = _require_int(data, "claim_reserve", minimum=0)
    return CaptureSession(
        session_id=session_id,
        endpoint=endpoint,
        key_uuid=key_uuid,
        count=count,
        claimed=claimed,
        created_at=created_at,
        expires_at=expires_at,
        stopped=stopped,
        bytes_reserved=bytes_reserved,
        published=published,
        claim_reserve=claim_reserve,
    )


def _session_status(data: dict[str, Any], now: float) -> str:
    if data.get("stopped"):
        return "stopped"
    expires_at = _require_nonneg_finite_number(data, "expires_at")
    if now >= expires_at:
        return "expired"
    if int(data.get("claimed", 0)) >= int(data.get("count", 0)):
        return "exhausted"
    return "active"


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


class CaptureStore:
    """Bounded, cross-process capture store rooted at one trusted directory."""

    def __init__(self, config: CaptureFacilityConfig) -> None:
        self._config = config
        self._root = self._validate_root(config.root)
        self._lock_path = self._root / LOCK_NAME
        self._manifest_path = self._root / MANIFEST_NAME
        self._captures_dir = self._root / CAPTURES_DIR_NAME
        self._init_layout()

    @property
    def config(self) -> CaptureFacilityConfig:
        return self._config

    @property
    def root(self) -> Path:
        return self._root

    # -- layout / validation -------------------------------------------------

    def _forbidden_roots(self) -> tuple[Path, ...]:
        here = Path(__file__).resolve()
        package_root = here.parents[1]  # .../app/slaif_gateway
        repo_root = here.parents[3]  # .../slaif-api-gateway
        return (package_root, repo_root)

    def _validate_root(self, root: Path) -> Path:
        if not isinstance(root, Path) or not root.is_absolute():
            raise CaptureStoreError("capture_root_invalid")
        if root.is_symlink():
            raise CaptureStoreError("capture_root_symlink")
        resolved = root.resolve()
        if resolved == Path("/"):
            raise CaptureStoreError("capture_root_forbidden")
        for forbidden in self._forbidden_roots():
            if _is_within(resolved, forbidden):
                raise CaptureStoreError("capture_root_forbidden")
        return resolved

    def _check_owned(self, st: os.stat_result) -> None:
        if os.geteuid() is not None and st.st_uid != os.geteuid():
            raise CaptureStoreError("capture_root_ownership")

    def _init_layout(self) -> None:
        if self._root.is_symlink():
            raise CaptureStoreError("capture_root_symlink")
        if self._root.exists():
            if not self._root.is_dir():
                raise CaptureStoreError("capture_root_invalid")
        else:
            try:
                self._root.mkdir(mode=0o700)
            except OSError:
                raise CaptureStoreError("capture_root_unavailable") from None
        try:
            os.chmod(self._root, 0o700)
            self._check_owned(self._root.stat())
        except OSError:
            raise CaptureStoreError("capture_root_unavailable") from None
        if self._captures_dir.is_symlink():
            raise CaptureStoreError("capture_root_symlink")
        if not self._captures_dir.is_dir():
            try:
                self._captures_dir.mkdir(mode=0o700, exist_ok=True)
            except OSError:
                raise CaptureStoreError("capture_root_unavailable") from None
        try:
            os.chmod(self._captures_dir, 0o700)
            self._check_owned(self._captures_dir.stat())
        except OSError:
            raise CaptureStoreError("capture_root_unavailable") from None
        self._ensure_control_file(self._lock_path)
        with self._lock(exclusive=True):
            self._ensure_manifest()

    def _ensure_control_file(self, path: Path) -> None:
        """Ensure ``path`` is a regular file we own (0600), refusing symlinks.

        Uses no-follow opens so a symlinked control target is refused rather
        than followed or overwritten.
        """
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            try:
                fd = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600
                )
            except FileExistsError:
                st = os.lstat(path)
            except OSError:
                raise CaptureStoreError("capture_control_unavailable") from None
            else:
                os.close(fd)
                st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            raise CaptureStoreError("capture_control_unsafe")
        self._check_owned(st)
        try:
            os.chmod(path, 0o600)
        except OSError:
            raise CaptureStoreError("capture_control_unavailable") from None

    def _ensure_manifest(self) -> None:
        try:
            st = os.lstat(self._manifest_path)
        except FileNotFoundError:
            self._write_manifest(self._empty_manifest())
            return
        if not stat.S_ISREG(st.st_mode):
            # Never overwrite a non-regular manifest (e.g. a FIFO); reads
            # reject it explicitly instead of blocking or clobbering it.
            return

    # -- locking -------------------------------------------------------------

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        fd = self._open_lock_fd()
        flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        deadline = time.monotonic() + _LOCK_WAIT_SECONDS
        acquired = False
        try:
            while True:
                try:
                    fcntl.flock(fd, flags | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    try:
                        time.sleep(_LOCK_RETRY_SECONDS)
                    except OSError:
                        pass
            if not acquired:
                raise CaptureStoreError("capture_lock_unavailable")
            yield
        finally:
            if acquired:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(fd)

    def _open_lock_fd(self) -> int:
        try:
            st = os.lstat(self._lock_path)
        except FileNotFoundError:
            try:
                return os.open(
                    self._lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                    0o600,
                )
            except OSError:
                raise CaptureStoreError("capture_control_unavailable") from None
        if not stat.S_ISREG(st.st_mode):
            raise CaptureStoreError("capture_control_unsafe")
        try:
            return os.open(self._lock_path, os.O_RDWR | os.O_NOFOLLOW)
        except OSError:
            raise CaptureStoreError("capture_control_unavailable") from None

    # -- manifest ------------------------------------------------------------

    def _empty_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "storage_bytes_reserved": 0,
            "sessions": [],
        }

    def _read_manifest(self) -> dict[str, Any]:
        # Open no-follow and non-blocking, then verify the ACTUAL opened handle
        # (regular, owned, bounded) and read from that same fd. This closes the
        # lstat->open->read TOCTOU gap: a regular->FIFO swap between an earlier
        # path check and the read is caught by fstat on the opened fd and can
        # never block (O_NONBLOCK) the caller.
        try:
            fd = os.open(
                self._manifest_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )
        except FileNotFoundError:
            return self._empty_manifest()
        except OSError:
            raise CaptureStoreError("capture_manifest_unavailable") from None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise CaptureStoreError("capture_manifest_unsafe")
            if os.geteuid() is not None and st.st_uid != os.geteuid():
                raise CaptureStoreError("capture_manifest_unsafe")
            if st.st_size > _MAX_MANIFEST_BYTES:
                raise CaptureStoreError("capture_manifest_unreadable")
            chunks: list[bytes] = []
            total = 0
            while total <= _MAX_MANIFEST_BYTES:
                chunk = os.read(fd, min(65536, _MAX_MANIFEST_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(fd)
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise CaptureStoreError("capture_manifest_unreadable")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise CaptureStoreError("capture_manifest_unreadable") from None
        if not isinstance(data, dict) or data.get("schema_version") != _SCHEMA_VERSION:
            raise CaptureStoreError("capture_manifest_unreadable")
        storage = data.get("storage_bytes_reserved", 0)
        if isinstance(storage, bool) or not isinstance(storage, int) or storage < 0:
            raise CaptureStoreError("capture_manifest_unreadable")
        sessions = data.get("sessions")
        if not isinstance(sessions, list) or len(sessions) > _MAX_SESSIONS_HARD:
            raise CaptureStoreError("capture_manifest_unreadable")
        for session in sessions:
            if not isinstance(session, dict):
                raise CaptureStoreError("capture_manifest_unreadable")
            _session_from_dict(session)
        return data

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        data = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        self._atomic_write(self._manifest_path, data)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        # No-follow: refuse to publish through a symlinked/non-regular target.
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            st = None
        if st is not None and (stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode)):
            raise CaptureStoreError("capture_artifact_unavailable")
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(path.parent), prefix=".partial-", suffix=".tmp"
            )
        except OSError:
            raise CaptureStoreError("capture_io_unavailable") from None
        try:
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise CaptureStoreError("capture_io_unavailable") from None
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- operator API --------------------------------------------------------

    def arm(
        self,
        *,
        endpoint: str,
        key_uuid: str | None = None,
        count: int | None = None,
        ttl_seconds: int | float | None = None,
        now: float | None = None,
    ) -> CaptureSession:
        """Arm one finite capture session; returns the created session."""
        config = self._config
        if (
            not isinstance(endpoint, str)
            or not endpoint.startswith("/")
            or "?" in endpoint
            or "#" in endpoint
            or len(endpoint) > 2048
        ):
            raise CaptureStoreError("capture_endpoint_invalid")
        if key_uuid is not None:
            if not isinstance(key_uuid, str) or not _UUID_PATTERN.fullmatch(key_uuid):
                raise CaptureStoreError("capture_key_uuid_invalid")
            key_uuid = key_uuid.lower()
        if count is None:
            count = config.default_count
        if isinstance(count, bool) or not isinstance(count, int) or not (
            1 <= count <= config.max_count
        ):
            raise CaptureStoreError("capture_count_invalid")
        if ttl_seconds is None:
            ttl_seconds = config.default_ttl_seconds
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or not (0 < ttl_seconds <= config.max_ttl_seconds)
        ):
            raise CaptureStoreError("capture_ttl_invalid")
        now_ts = float(now if now is not None else time.time())
        session = CaptureSession(
            session_id=f"cap-{uuid.uuid4().hex}",
            endpoint=endpoint,
            key_uuid=key_uuid,
            count=count,
            claimed=0,
            created_at=now_ts,
            expires_at=now_ts + float(ttl_seconds),
            stopped=False,
            bytes_reserved=0,
            published=0,
            claim_reserve=0,
        )
        with self._lock(exclusive=True):
            manifest = self._read_manifest()
            sessions = manifest["sessions"]
            self._prune_finished(sessions, now_ts)
            if len(sessions) >= config.max_sessions:
                raise CaptureStoreError("capture_sessions_full")
            sessions.append(_session_to_dict(session))
            self._write_manifest(manifest)
        return session

    def _prune_finished(self, sessions: list[dict[str, Any]], now: float) -> None:
        """Bound the manifest by dropping only fileless, unreserved finished
        sessions. A finished session that still has reserved bytes or published
        artifacts is never pruned (its files must survive for operator cleanup);
        in that case arming is refused until the operator cleans up.
        """
        cap = self._config.max_sessions
        while len(sessions) >= cap:
            finished = [
                s
                for s in sessions
                if _session_status(s, now) != "active"
                and int(s.get("published", 0)) == 0
                and int(s.get("bytes_reserved", 0)) == 0
            ]
            if not finished:
                break
            oldest = min(
                finished,
                key=lambda s: (
                    float(s.get("created_at", 0.0)),
                    str(s.get("session_id", "")),
                ),
            )
            sessions.remove(oldest)

    def status(self, *, now: float | None = None) -> list[CaptureSession]:
        """Return all sessions; call ``session.status(now)`` for state."""
        _ = float(now if now is not None else time.time())
        with self._lock(exclusive=False):
            manifest = self._read_manifest()
        return [_session_from_dict(s) for s in manifest["sessions"]]

    def storage_reserved(self) -> int:
        """Return the total bytes currently reserved across all sessions."""
        with self._lock(exclusive=False):
            manifest = self._read_manifest()
        return int(manifest.get("storage_bytes_reserved", 0))

    def stop(self, *, session_id: str | None = None) -> int:
        """Stop one session (or all); returns the number of sessions stopped."""
        with self._lock(exclusive=True):
            manifest = self._read_manifest()
            changed = 0
            for session in manifest["sessions"]:
                if session_id is not None and session.get("session_id") != session_id:
                    continue
                if not session.get("stopped"):
                    session["stopped"] = True
                    changed += 1
            if changed:
                self._write_manifest(manifest)
        return changed

    def cleanup(self, *, session_id: str | None = None) -> int:
        """Remove exactly-owned artifacts for a session (or all) and release quota.

        Returns the number of artifact files removed. Never deletes arbitrary
        directory contents; only recognized owned capture/record/partial names
        inside a session's own directory are removed.
        """
        removed = 0
        with self._lock(exclusive=True):
            manifest = self._read_manifest()
            kept: list[dict[str, Any]] = []
            for session in manifest["sessions"]:
                if session_id is not None and session.get("session_id") != session_id:
                    kept.append(session)
                    continue
                session_dir = self._captures_dir / str(session.get("session_id", ""))
                removed += self._remove_session_dir(session_dir)
                manifest["storage_bytes_reserved"] = max(
                    0,
                    int(manifest.get("storage_bytes_reserved", 0))
                    - int(session.get("bytes_reserved", 0)),
                )
            manifest["sessions"] = kept
            self._write_manifest(manifest)
        return removed

    def _remove_session_dir(self, session_dir: Path) -> int:
        removed = 0
        if not session_dir.is_dir() or session_dir.is_symlink():
            return removed
        try:
            entries = list(session_dir.iterdir())
        except OSError:
            return removed
        for entry in entries:
            name = entry.name
            if not (
                _OWNED_CAPTURE.fullmatch(name)
                or _OWNED_RECORD.fullmatch(name)
                or _OWNED_PARTIAL.fullmatch(name)
            ):
                continue  # preserve anything not a recognized owned artifact
            try:
                st = os.lstat(entry)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            try:
                entry.unlink()
                removed += 1
            except OSError:
                continue
        try:
            session_dir.rmdir()  # only succeeds once empty
        except OSError:
            pass
        return removed

    # -- runtime peek (ASGI observer) ----------------------------------------

    def peek(self, *, endpoint: str, now: float | None = None) -> dict[str, Any] | None:
        """Return a summary of the first active session matching ``endpoint``.

        Non-consuming (shared lock). Used by the ASGI observer as a cheap gate
        before doing any body buffering or read-only auth probe. Returns ``None``
        when no active session matches. ``key_uuid`` is ``None`` for an
        endpoint-only session or the verified UUID filter otherwise.
        """
        now_ts = float(now if now is not None else time.time())
        with self._lock(exclusive=False):
            manifest = self._read_manifest()
        for session in manifest["sessions"]:
            if _session_status(session, now_ts) != "active":
                continue
            if str(session.get("endpoint")) != endpoint:
                continue
            return {
                "session_id": session.get("session_id"),
                "key_uuid": session.get("key_uuid"),
            }
        return None

    # -- runtime claim (ASGI observer) ---------------------------------------

    def reservation_bytes(self) -> int:
        """Per-claim/per-capture storage budget (base64 body + metadata)."""
        budget = max(0, self._config.body_budget_bytes)
        return int(budget * 4 / 3) + _METADATA_OVERHEAD_BYTES

    def claim(
        self,
        *,
        endpoint: str,
        key_uuid: str | None = None,
        now: float | None = None,
        reserve_bytes: int | None = None,
    ) -> CaptureSession | None:
        """Atomically claim one capture slot for a matching active session.

        Returns the claimed session, or ``None`` when no session matches, is
        exhausted/expired/stopped, or storage is full. The claim is consumed
        even if the later artifact write fails. ``reserve_bytes`` defaults to
        the store's positive per-claim reservation (never zero/no-quota).
        """
        now_ts = float(now if now is not None else time.time())
        reserve = self.reservation_bytes() if reserve_bytes is None else reserve_bytes
        # A claim must always reserve a positive amount (never zero/no-quota);
        # an explicit zero is rejected so publication cannot under-account.
        if isinstance(reserve, bool) or not isinstance(reserve, int) or reserve <= 0:
            raise CaptureStoreError("capture_reserve_invalid")
        with self._lock(exclusive=True):
            manifest = self._read_manifest()
            total = int(manifest.get("storage_bytes_reserved", 0))
            for session in manifest["sessions"]:
                if _session_status(session, now_ts) != "active":
                    continue
                if str(session.get("endpoint")) != endpoint:
                    continue
                candidate_key = session.get("key_uuid")
                if candidate_key is not None and candidate_key != key_uuid:
                    continue
                if reserve > 0 and total + reserve > self._config.total_storage_bytes:
                    continue
                session["claimed"] = int(session.get("claimed", 0)) + 1
                session["claim_reserve"] = reserve
                session["bytes_reserved"] = int(session.get("bytes_reserved", 0)) + reserve
                total += reserve
                manifest["storage_bytes_reserved"] = total
                self._write_manifest(manifest)
                return _session_from_dict(session)
        return None

    # -- artifact publication ------------------------------------------------

    def write_artifact(
        self,
        *,
        session_id: str,
        request_id: str,
        capture: bytes,
        record: bytes,
    ) -> None:
        """Atomically publish one masked capture artifact + concise record.

        Publication is bounded by the actual combined capture/record/temp
        footprint re-checked under the same lock at publish time, against both
        the per-capture budget and the global total, and is only permitted
        against a claim that was actually issued for this session (duplicate
        and stale-after-cleanup writes are rejected).
        """
        if not _REQUEST_ID_PATTERN.fullmatch(request_id):
            raise CaptureStoreError("capture_request_id_invalid")
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise CaptureStoreError("capture_session_id_invalid")
        capture = bytes(capture)
        record = bytes(record)
        with self._lock(exclusive=True):
            manifest = self._read_manifest()
            total = int(manifest.get("storage_bytes_reserved", 0))
            target = None
            for session in manifest["sessions"]:
                if session.get("session_id") == session_id:
                    target = session
                    break
            if target is None:
                raise CaptureStoreError("capture_session_missing")
            claimed = int(target.get("claimed", 0))
            published = int(target.get("published", 0))
            if published >= claimed:
                raise CaptureStoreError(
                    "capture_unclaimed" if claimed == 0 else "capture_exhausted"
                )
            session_dir = self._captures_dir / session_id
            capture_path = session_dir / f"{request_id}.capture.json"
            record_path = session_dir / f"{request_id}.record.json"
            if self._path_regular(capture_path) or self._path_regular(record_path):
                raise CaptureStoreError("capture_duplicate")
            reserve = int(target.get("claim_reserve", 0)) or self.reservation_bytes()
            combined = len(capture) + len(record)
            if combined > self.reservation_bytes():
                raise CaptureStoreError("capture_storage_full")
            actual = combined + _METADATA_OVERHEAD_BYTES
            proposed_total = max(0, total - reserve + actual)
            if proposed_total > self._config.total_storage_bytes:
                raise CaptureStoreError("capture_storage_full")
            self._ensure_session_dir(session_dir)
            try:
                self._atomic_write(capture_path, capture)
                self._atomic_write(record_path, record)
                target["published"] = published + 1
                target["bytes_reserved"] = int(target.get("bytes_reserved", 0)) + (
                    actual - reserve
                )
                manifest["storage_bytes_reserved"] = proposed_total
                self._write_manifest(manifest)
            except BaseException:
                for path in (capture_path, record_path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                raise
        return None

    def _path_regular(self, path: Path) -> bool:
        try:
            st = os.lstat(path)
        except OSError:
            return False
        return stat.S_ISREG(st.st_mode)

    def _ensure_session_dir(self, session_dir: Path) -> None:
        if session_dir.is_symlink():
            raise CaptureStoreError("capture_artifact_unavailable")
        if not session_dir.is_dir():
            try:
                session_dir.mkdir(mode=0o700, exist_ok=True)
            except OSError:
                raise CaptureStoreError("capture_artifact_unavailable") from None
        try:
            os.chmod(session_dir, 0o700)
            self._check_owned(session_dir.stat())
        except OSError:
            raise CaptureStoreError("capture_artifact_unavailable") from None


# -- facility construction (shared by the ASGI observer and the CLI) -----------

if TYPE_CHECKING:  # pragma: no cover - annotation only
    from slaif_gateway.config import Settings

_logger = logging.getLogger("slaif_gateway.request_capture")
_MAX_BODY_BUDGET = 64 * 1024 * 1024


def _resolve_app_version(override: str) -> str:
    if override and override.strip():
        return override.strip()
    try:
        from importlib.metadata import version

        return version("slaif-api-gateway")
    except Exception:  # noqa: BLE001 - version is non-essential; fail safe
        return "unknown"


def build_capture_facility(settings: "Settings") -> CaptureStore | None:
    """Build the shared capture store from settings, or ``None`` if disabled.

    A disabled or invalid capture configuration never affects startup: the
    facility stays off (safe, low-detail log), matching the default-OFF opt-in
    design. Used by both the ASGI observer (``install_request_capture``) and
    the operator CLI so they share one construction/validation path.
    """
    if not getattr(settings, "REQUEST_CAPTURE_ENABLED", False):
        return None
    root_raw = (getattr(settings, "REQUEST_CAPTURE_DIR", "") or "").strip()
    if not root_raw:
        _logger.warning("request capture enabled but REQUEST_CAPTURE_DIR empty; facility off")
        return None
    body_budget = max(0, int(getattr(settings, "REQUEST_CAPTURE_BODY_BUDGET_BYTES", 10485760)))
    if body_budget > _MAX_BODY_BUDGET:
        body_budget = _MAX_BODY_BUDGET
    config = CaptureFacilityConfig(
        enabled=True,
        root=Path(root_raw),
        body_budget_bytes=body_budget,
        total_storage_bytes=max(
            0, int(getattr(settings, "REQUEST_CAPTURE_TOTAL_STORAGE_BYTES", 20971520))
        ),
        max_count=max(1, int(getattr(settings, "REQUEST_CAPTURE_MAX_COUNT", 100))),
        max_ttl_seconds=max(1, int(getattr(settings, "REQUEST_CAPTURE_MAX_TTL_SECONDS", 3600))),
        deployed_revision=(
            (getattr(settings, "REQUEST_CAPTURE_DEPLOYED_REVISION", "") or "").strip()
            or "unknown"
        ),
        revision_provenance=(
            (getattr(settings, "REQUEST_CAPTURE_REVISION_PROVENANCE", "") or "").strip()
            or "operator-unspecified"
        ),
        app_version=_resolve_app_version(getattr(settings, "REQUEST_CAPTURE_APP_VERSION", "") or ""),
    )
    try:
        return CaptureStore(config)
    except CaptureStoreError as exc:
        _logger.warning("request capture facility unavailable (%s); facility off", exc.reason)
        return None


# -- local-only rejection diagnostic context --------------------------------

_capture_rejection: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "slaif_request_capture_rejection", default=None
)


def record_capture_rejection(context: dict[str, Any]) -> contextvars.Token:
    """Record a local-only structured rejection reason for the capture observer."""
    return _capture_rejection.set(context)


def get_capture_rejection() -> dict[str, Any] | None:
    """Return the local-only rejection reason recorded for this request, if any."""
    return _capture_rejection.get()


def reset_capture_rejection(token: contextvars.Token) -> None:
    """Reset the rejection context to its prior value."""
    _capture_rejection.reset(token)


def clear_capture_rejection() -> None:
    """Clear any recorded rejection reason for the current context."""
    _capture_rejection.set(None)


# -- per-request scope-state rejection channel ------------------------------
# BaseHTTPMiddleware (RequestId/Metrics) run the inner app in a child task, so a
# contextvar set deep in the policy does not reliably reach an outer ASGI
# observer. The shared per-request ``scope`` dict object is the reliable
# channel: the policy records a bounded, content-free structured reason here and
# the ASGI observer reads it after the app completes.
CAPTURE_REJECTION_STATE_KEY = "slaif_capture_rejection"


def record_scope_capture_rejection(scope: dict[str, Any], context: dict[str, Any]) -> None:
    """Record a local-only structured rejection reason on the request scope.

    ``context`` must be a bounded, content-free structured reason (reason code,
    position, counts, limits); it never carries raw request content.
    """
    state = scope.setdefault("state", {})
    if isinstance(state, dict):
        state[CAPTURE_REJECTION_STATE_KEY] = context


def get_scope_capture_rejection(scope: dict[str, Any]) -> dict[str, Any] | None:
    """Return the local-only rejection reason recorded on the request scope."""
    state = scope.get("state")
    if not isinstance(state, dict):
        return None
    value = state.get(CAPTURE_REJECTION_STATE_KEY)
    return value if isinstance(value, dict) else None

# -- per-request scope-state provenance channel -----------------------------
# A bounded, mergeable record of request-provenance facts (verified key UUID,
# whether verification came from normal auth or the read-only capture probe, and
# the selected client-module identity). Written incrementally by the auth
# dependency and the route; read once by the ASGI observer for the record
# sidecar.  Purely observational: it never carries raw request content and never
# affects auth, admission, or accounting.
CAPTURE_PROVENANCE_STATE_KEY = "slaif_capture_provenance"


def record_scope_capture_provenance(scope: dict[str, Any], **fields: object) -> None:
    """Merge bounded provenance facts onto the per-request scope state.

    ``None`` values are ignored so multiple callers (auth dependency, route)
    can contribute disjoint fields to the same record.  Content-free only.
    """
    state = scope.setdefault("state", {})
    if not isinstance(state, dict):
        return
    current = state.get(CAPTURE_PROVENANCE_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    for key, value in fields.items():
        if value is None:
            continue
        current[key] = value
    state[CAPTURE_PROVENANCE_STATE_KEY] = current


def get_scope_capture_provenance(scope: dict[str, Any]) -> dict[str, Any] | None:
    """Return the per-request provenance record, if any was recorded."""
    state = scope.get("state")
    if not isinstance(state, dict):
        return None
    value = state.get(CAPTURE_PROVENANCE_STATE_KEY)
    return value if isinstance(value, dict) else None
