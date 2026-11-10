"""G15 (217-a): admin-GUI custody for the bounded catalog-refresh workflow.

This module is the narrow GUI bridge between the authenticated admin
console and the EXISTING sealed catalog-refresh core. It is deliberately
not a generic job platform: one closed task family, operator-owned file
custody under one existing root, small NEW-ONLY metadata/status records,
and admission bounded by validated settings.

Guarantees (see the 217-a order, "Operator custody"):

- Default off. Missing/unsafe configuration is reported as a useful
  authenticated setup state; it performs NO network, job, or mutation.
- The GUI opens an EXISTING properly-owned root (same-uid trusted
  operator model) and the EXISTING 0600 seal key through the anchored
  no-follow boundary. It only creates private subdirectories INSIDE the
  existing root (through the anchored Core walk); it never creates or
  replaces the seal key, never repairs permissions, and never accepts
  host paths, DB URLs, or keys from the browser or a task payload.
- Canonical browser run UUIDs map to server custody only; all custody
  file access goes through held anchored descriptors (no path
  concatenation as authentication, no symlink/traversal shortcuts).
- Admission (active jobs, retained slots, total bytes) is enforced under
  one cross-process advisory lock so concurrent API requests AND worker
  processes share the same bounds. Every admitted job RESERVES its
  finite byte ceiling and (when it may publish an artifact) its
  retained slot BEFORE any write or publication, so full capacity
  refuses explicitly and custody can never exceed the bounds at rest.
- One status vocabulary: queued / running / ready / warnings / blocked /
  failed / canceled / unavailable / unconfirmed. Broker admission is not
  completion; a canceled queued job can never execute on delayed
  delivery; late or duplicate delivery can never overwrite a published
  sealed artifact or claim another task's outcome.
- Cancellation is read-only and cooperative: a live per-checkpoint flag
  that the shared application composition evaluates at every phase
  checkpoint AND immediately before the NEW-ONLY publication. Until an
  actual terminal fact is known the status is shown as
  cancel-requested/unconfirmed, never as a hard kill claim. Mutating
  apply work is outside the read-only cancellable/timed family.
- Artifact downloads serve the SAME verified captured bytes (Core seal
  authentication, manifest reconciliation, Core per-file caps); every
  held handle is rechecked and closed.
"""

from __future__ import annotations

import fcntl
import json
import itertools
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from slaif_gateway.config import Settings
from slaif_gateway.services.catalog_refresh.baseline import MAX_BASELINE_BYTES
from slaif_gateway.services.catalog_refresh.bundle import MAX_BUNDLE_BYTES
from slaif_gateway.services.catalog_refresh.filesystem import (
    MAX_AUX_BYTES,
    MAX_TOTAL_BYTES as CORE_MAX_RUN_BYTES,
    RECEIPT_MAX_BYTES,
    CatalogRefreshSealError,
    anchored_read_fd,
    load_seal_key_bytes,
    open_anchored_handle,
)
from slaif_gateway.services.catalog_refresh.sealing import (
    CONTENT_FILES,
    load_verified_capture,
)
from slaif_gateway.services.provider_catalog_proposal import OPENROUTER_PACKAGE_ORDER

__all__ = [
    "CATALOG_JOB_FAMILIES",
    "CATALOG_JOB_STATUSES",
    "CATALOG_TERMINAL_STATUSES",
    "CATALOG_RUN_ARTIFACTS",
    "AdminCatalogRefreshError",
    "CustodyCapacityError",
    "CustodyJobError",
    "CustodySetup",
    "begin_job",
    "cancel_check",
    "create_job",
    "finish_job",
    "inspect_custody_setup",
    "job_projection",
    "list_jobs",
    "list_proposal_packages",
    "list_runs",
    "open_proposal_dir",
    "read_job_artifact",
    "read_proposal_artifact",
    "read_proposal_package_artifact",
    "read_run_artifact",
    "remove_proposal_dir",
    "remove_terminal_job",
    "remove_terminal_run",
    "request_cancel",
    "store_upload",
]

# The QUEUED job families are READ-ONLY work (cancellable/timed). Mutating
# apply is deliberately NOT a queued job: the GUI composes the existing
# Core apply directly under fresh HTTP auth (like the CLI apply) and uses
# the Core's own committed-outcome record - no second local mutation-job
# tracker.
CATALOG_JOB_FAMILIES = frozenset(
    {"collect", "review_supplied", "export_baseline", "proposal"}
)
CATALOG_JOB_STATUSES = frozenset(
    {
        "queued",
        "running",
        "ready",
        "warnings",
        "blocked",
        "failed",
        "canceled",
        "unavailable",
        "unconfirmed",
    }
)
CATALOG_TERMINAL_STATUSES = frozenset(
    {"ready", "warnings", "blocked", "failed", "canceled"}
)
# Closed set of sealed CONTENT artifacts the GUI may serve (Core layout).
# manifest/receipt are the authentication itself, never served raw.
CATALOG_RUN_ARTIFACTS = frozenset(CONTENT_FILES)
# The complete published run layout (content + authentication files).
CORE_RUN_FILE_SET = frozenset(set(CONTENT_FILES) | {"manifest.json", "receipt.json"})

_SUBDIRS = ("runs", "jobs", "uploads", "proposals", "locks")
_JOB_NAME_RE = re.compile(r"^[0-9a-f]{32}\.json$")
# Core canonical run leaf names: collect-DATE-TIME-digest, the blocked-*
# leaves, and supplied-bundle run ids - all bounded by the Core bundle
# schema (^[a-z0-9][a-z0-9-]{0,63}$). Custody maps the browser's job id to
# the validated Core run leaf through the job record; it never rewrites a
# run name to fit another shape.
_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_UPLOAD_NAME_RE = re.compile(r"^(bundle|baseline)-[0-9a-f]{32}$")
_JOB_ARTIFACT_NAME_RE = re.compile(r"^(bundle|baseline|baseline-export)-[0-9a-f]{32}$")
_MAX_JOB_FILE_BYTES = 1 * 1024 * 1024

# --- finite custody ceilings (Core-bounded, documented tuning) -------------
# A published run is Core-bounded: the verified-capture aggregate bound
# plus the deterministic receipt/manifest overhead.
_RUN_RESERVATION_BYTES = CORE_MAX_RUN_BYTES + RECEIPT_MAX_BYTES + MAX_AUX_BYTES
# Supplied bundle + exported baseline uploads keep the exact Core bounds.
_UPLOAD_CEILING_BYTES = MAX_BUNDLE_BYTES + MAX_BASELINE_BYTES
# A proposal output set (bounded model caps) with documented headroom.
_PROPOSAL_RESERVATION_BYTES = 32 * 1024 * 1024
# Total job-record count bound (finite metadata growth): admitted only
# below 4x the retained-run bound; terminal records are operator-cleanup.
_JOB_RECORD_MAX_FACTOR = 4

_HELP_DISABLED = (
    "Catalog refresh in the admin console is disabled "
    "(CATALOG_REFRESH_GUI_ENABLED=false).",
    "To enable it, set CATALOG_REFRESH_GUI_ENABLED=true plus "
    "CATALOG_REFRESH_ROOT (an operator-owned directory OUTSIDE the "
    "repository and database, mounted for the API and worker) and "
    "CATALOG_REFRESH_SEAL_KEY (the path of the EXISTING 0600 seal key) "
    "in the deployment environment, then restart the API and worker.",
    "The console never creates or replaces the seal key and never "
    "repairs permissions; it only opens existing operator-owned "
    "custody.",
)


class AdminCatalogRefreshError(ValueError):
    """Safe code+detail error for the catalog-refresh GUI bridge."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class CustodyCapacityError(AdminCatalogRefreshError):
    """Explicit full-capacity refusal (never partial output)."""


class CustodyJobError(AdminCatalogRefreshError):
    """Unknown/invalid job or run custody reference."""


@dataclass(frozen=True)
class CustodySetup:
    """Authenticated setup inspection result (safe to render)."""

    state: str  # "disabled" | "unavailable" | "ready"
    code: str
    help_lines: tuple[str, ...]
    root: Path | None = None
    seal_key: Path | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _strict_json(raw: bytes, cap: int) -> dict[str, Any]:
    def pairs(pairs_list: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs_list:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("invalid json") from None
    if not isinstance(document, dict):
        raise ValueError("json object required")
    return document


def _dir_entries(path: str | Path) -> list[tuple[str, int, int]]:
    """(name, mode, size) for the flat children of one custody directory
    (opened through the anchored walk by the caller); never follows
    links (lstat-style stat on each entry)."""
    entries: list[tuple[str, int, int]] = []
    for entry in os.scandir(str(path)):
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        entries.append((entry.name, st.st_mode, st.st_size))
    return entries


def _known_gateway_roots() -> tuple[Path, ...]:
    """Bounded known gateway source/package/repository roots: the
    resolved package directory, extended to the repository root ONLY
    when a real bounded ``.git`` ancestor is found (a checkout or
    worktree). An INSTALLED package (site-packages, no ``.git``
    ancestor) protects the actual package tree only - never its
    install ancestors and never the filesystem root. A few bounded
    path checks only - no machine inventory or filesystem-attestation
    platform."""
    try:
        import slaif_gateway

        start = Path(slaif_gateway.__file__).resolve().parent
    except Exception:  # noqa: BLE001 - unresolvable package location
        return ()
    repo_root = None
    for ancestor in itertools.islice(start.parents, 12):
        if (ancestor / ".git").exists():
            repo_root = ancestor
            break
    if repo_root is None:
        # Installed (no checkout ancestor): only the actual package.
        return (start,)
    # Real checkout: the package tree through the repository root.
    chain: list[Path] = [start]
    for ancestor in start.parents:
        chain.append(ancestor)
        if ancestor == repo_root:
            break
    return tuple(chain)


def _location_problem(raw: str, what: str) -> str | None:
    """Ordered custody-location gate for ONE configured path (root or
    seal key). Refuses, fail-closed and feature-local, when the path is
    ambiguous (relative - the API and worker processes may have
    different working directories) or RESOLVES INSIDE a known gateway
    source/package/repository root or a recognizable local PostgreSQL
    data directory (bounded ``PG_VERSION`` ancestor check). No layout
    is created before this gate; nothing is repaired or relocated."""
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        return (
            f"The configured {what} path {raw!r} is relative and therefore "
            "ambiguous across the API and worker processes; configure an "
            "absolute path outside the repository and database."
        )
    resolved = Path(os.path.abspath(expanded))
    for root in _known_gateway_roots():
        if resolved == root or root in resolved.parents:
            return (
                f"The configured {what} {raw!r} is inside the gateway "
                "repository/source tree; catalog custody must live outside "
                "the repository and database. The console does not "
                "relocate or repair it."
            )
    for ancestor in resolved.parents:
        if (ancestor / "PG_VERSION").is_file():
            return (
                f"The configured {what} {raw!r} is inside a PostgreSQL "
                "data directory (PGDATA); catalog custody must live outside "
                "the database. The console does not relocate or repair it."
            )
    return None


def inspect_custody_setup(settings: Settings) -> CustodySetup:
    """Inspect the operator custody WITHOUT creating or repairing anything.

    Disabled or missing/unsafe configuration yields a useful setup state
    with ZERO dispatch, network, or mutation. Only when the existing
    root and existing seal key pass every check does it return
    ``state="ready"``; private subdirectories inside the existing root
    are created (0700, through the anchored Core walk) only at that
    point.

    The ordered location gate runs FIRST: configured root/key paths
    must be unambiguous absolute paths outside the gateway
    repository/source tree and outside any recognizable local
    PostgreSQL data directory. A violation is feature-local
    ``unavailable`` - no global startup failure, no repair, no create.
    """
    root_raw = (settings.CATALOG_REFRESH_ROOT or "").strip()
    key_raw = (settings.CATALOG_REFRESH_SEAL_KEY or "").strip()
    if not settings.CATALOG_REFRESH_GUI_ENABLED:
        return CustodySetup("disabled", "catalog_refresh_gui_disabled", _HELP_DISABLED)
    problems: list[str] = []
    if not root_raw:
        problems.append(
            "CATALOG_REFRESH_ROOT is not set; point it at an operator-owned "
            "directory outside the repository and database."
        )
    if not key_raw:
        problems.append(
            "CATALOG_REFRESH_SEAL_KEY is not set; point it at the EXISTING "
            "0600 seal key (created once through the CLI bootstrap flow; "
            "the console never creates it)."
        )
    if problems:
        return CustodySetup(
            "unavailable",
            "catalog_refresh_setup_incomplete",
            tuple(problems) + _HELP_DISABLED[1:],
        )
    root = Path(os.path.abspath(os.path.expanduser(root_raw)))
    seal_key = Path(os.path.abspath(os.path.expanduser(key_raw)))
    # Ordered location gate (BEFORE any existence check or layout
    # creation): outside the repository/source tree, outside any local
    # PGDATA, and unambiguous (absolute).
    root_location = _location_problem(root_raw, "custody root")
    if root_location:
        return CustodySetup("unavailable", "catalog_refresh_location_unsafe", (root_location,))
    key_location = _location_problem(key_raw, "seal key")
    if key_location:
        return CustodySetup("unavailable", "catalog_refresh_location_unsafe", (key_location,))
    try:
        root_st = os.lstat(root)
    except OSError:
        return CustodySetup(
            "unavailable",
            "catalog_refresh_root_missing",
            (
                f"The configured catalog custody root {root} does not exist. "
                "Create it as a real directory owned by the service user "
                "(mode 0700 recommended), outside the repository and "
                "database, mounted for the API and worker. The console "
                "never creates it.",
            ),
        )
    if os.path.islink(str(root)) or not os.path.isdir(str(root)):
        problems.append(
            f"The configured custody root {root} must be a real directory "
            "(not a symlink or special file)."
        )
    else:
        if root_st.st_uid != os.getuid():
            problems.append(
                "The custody root is not owned by the service user running "
                "the API/worker; make it owned by that user (the GUI uses "
                "the existing same-uid trusted-operator model)."
            )
        if root_st.st_mode & 0o022:
            problems.append(
                "The custody root is writable by group or other; remove "
                "those write bits. The console does not repair "
                "permissions."
            )
    if not problems:
        try:
            key_st = os.lstat(seal_key)
        except OSError:
            problems.append(
                f"The configured seal key {seal_key} does not exist. Create "
                "it once with the CLI (e.g. the first catalog-refresh "
                "bootstrap --seal-key) as a regular 0600 file outside the "
                "repository and database; the console never creates or "
                "replaces it."
            )
        else:
            if os.path.islink(str(seal_key)) or not os.path.isfile(str(seal_key)):
                problems.append(
                    f"The configured seal key {seal_key} must be a regular "
                    "file (not a symlink or special file)."
                )
            elif key_st.st_uid != os.getuid():
                problems.append(
                    "The seal key is not owned by the service user running "
                    "the API/worker."
                )
            elif key_st.st_mode & 0o777 != 0o600:
                problems.append(
                    "The seal key must be mode 0600. The console does not "
                    "repair permissions; fix them with chown/chmod as the "
                    "operator."
                )
            else:
                try:
                    load_seal_key_bytes(seal_key)
                except Exception:
                    problems.append(
                        "The configured seal key failed the anchored "
                        "no-follow load check (unreadable or malformed); "
                        "verify it is the existing 0600 key file."
                    )
    if problems:
        return CustodySetup(
            "unavailable", "catalog_refresh_custody_unsafe", tuple(problems)
        )
    # Every check passed: open the EXISTING root through the anchored
    # walk and open-or-create the private subdirectories INSIDE it.
    # FD ownership: the anchored handle owns every retained parent and
    # component descriptor, so it is closed EXACTLY ONCE on every path
    # (ready success, unsafe return, or unexpected raise) - never left
    # to garbage collection.
    try:
        handle = open_anchored_handle(root, create_missing=False)
    except Exception:
        return CustodySetup(
            "unavailable",
            "catalog_refresh_root_unopenable",
            (
                f"The custody root {root} could not be opened through the "
                "anchored no-follow boundary; check ownership and "
                "permissions."
            ),
        )
    try:
        for name in _SUBDIRS:
            try:
                sub = open_anchored_handle(root / name, create_missing=True)
            except Exception:
                return CustodySetup(
                    "unavailable",
                    "catalog_refresh_subdir_unsafe",
                    (
                        f"The private custody subdirectory {name!r} inside "
                        "the root could not be opened or created (0700). "
                        "The console does not repair permissions."
                    ),
                )
            try:
                st = os.fstat(sub.dir_fd)
                if (st.st_mode & 0o777) != 0o700 or st.st_uid != os.getuid():
                    return CustodySetup(
                        "unavailable",
                        "catalog_refresh_subdir_unsafe",
                        (
                            f"The custody subdirectory {name!r} exists with "
                            "unsafe ownership or permissions; make it 0700 "
                            "owned by the service user. The console does not "
                            "repair permissions."
                        ),
                    )
            finally:
                sub.close()
    finally:
        handle.close()
    return CustodySetup(
        "ready",
        "catalog_refresh_ready",
        (),
        root=root,
        seal_key=seal_key,
    )


# --- held-handle custody file access ---------------------------------------


def _open_subdir(root: Path, name: str) -> int:
    """Open one private subdirectory of the existing root through the
    anchored walk and return its held descriptor.

    The anchored walk validates the whole ancestor chain; then only the
    LEAF descriptor is opened relative to the held parent (the same
    O_NOFOLLOW boundary the walk itself applies at the leaf). The walk's
    parent handles are closed EXACTLY ONCE here, and the returned fd is
    standalone: closing it later closes nothing else (no orphaned
    ancestor descriptors)."""
    parent = open_anchored_handle(root, create_missing=False)
    try:
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent.dir_fd
        )
    except BaseException:
        parent.close()
        raise
    parent.close()
    return fd


def _job_name(job_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise CustodyJobError("job_unknown", "unknown job id")
    # Canonical single-component leaf (byte-identical for valid ids;
    # invalid input is rejected above, never normalized into a value).
    return os.path.basename(job_id) + ".json"


def _canonical_job_leaf(job_id: str) -> str:
    """Strict closed-leaf derivation for one job id (32 lowercase hex).

    Every anchored open in this service receives this DERIVED leaf, never
    the raw caller value: anything that is not exactly one 32-hex
    component is refused (same code/message as the job-file helpers), and
    the standard single-component canonical form is byte-identical for
    valid ids, so no valid id changes meaning and no invalid input is
    normalized into an accepted value."""
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise CustodyJobError("job_unknown", "unknown job id")
    return os.path.basename(job_id)


def _read_job_file(jobs_fd: int, name: str) -> dict[str, Any] | None:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=jobs_fd)
    except (FileNotFoundError, OSError):
        return None
    with os.fdopen(fd, "rb") as handle:
        raw = handle.read(_MAX_JOB_FILE_BYTES + 1)
    if len(raw) > _MAX_JOB_FILE_BYTES:
        raise AdminCatalogRefreshError(
            "job_record_too_large", "job metadata record exceeds its bound"
        )
    try:
        return _strict_json(raw, _MAX_JOB_FILE_BYTES)
    except ValueError:
        return None


def _job_payload_bytes(payload: dict[str, Any]) -> int:
    return len((json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def _write_job_file_new_only(jobs_fd: int, name: str, payload: dict[str, Any]) -> None:
    if _job_payload_bytes(payload) > _MAX_JOB_FILE_BYTES:
        raise AdminCatalogRefreshError(
            "job_record_too_large", "job metadata record exceeds its bound"
        )
    raw = (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=jobs_fd,
    )
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _write_job_file_atomic(jobs_fd: int, name: str, payload: dict[str, Any]) -> None:
    if _job_payload_bytes(payload) > _MAX_JOB_FILE_BYTES:
        raise AdminCatalogRefreshError(
            "job_record_too_large", "job metadata record exceeds its bound"
        )
    raw = (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")
    tmp = f".tmp-{uuid.uuid4().hex}-{name}"
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=jobs_fd,
    )
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.rename(tmp, name, src_dir_fd=jobs_fd, dst_dir_fd=jobs_fd)
    except BaseException:
        try:
            os.unlink(tmp, dir_fd=jobs_fd)
        except OSError:
            pass
        raise
    dfd = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=jobs_fd)
    os.fsync(dfd)
    os.close(dfd)


class _admission_lock:
    """Cross-process advisory lock for admission/lifecycle transitions."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._locks_fd: int | None = None
        self._lock_fd: int | None = None

    def __enter__(self) -> "_admission_lock":
        self._locks_fd = _open_subdir(self._root, "locks")
        self._lock_fd = os.open(
            "admission.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o644,
            dir_fd=self._locks_fd,
        )
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            if self._lock_fd is not None:
                try:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(self._lock_fd)
                    self._lock_fd = None
        finally:
            if self._locks_fd is not None:
                os.close(self._locks_fd)
                self._locks_fd = None


# --- bounded custody accounting --------------------------------------------


# Bounded traversal for ACTUAL custody bytes: finite depth/file counts,
# never follows links. Reservations cover FUTURE growth; existing bytes
# are always measured, never estimated.
_TREE_MAX_DEPTH = 8
_TREE_MAX_FILES = 2048


def _dir_tree_bytes(path: str | Path) -> int:
    """ACTUAL total bytes of one custody subtree, including NESTED
    directories (proposal packages) and staging/temp entries."""
    total = 0
    files = 0
    stack: list[tuple[str, int]] = [(str(path), 0)]
    while stack:
        current, depth = stack.pop()
        if depth > _TREE_MAX_DEPTH:
            raise CustodyJobError(
                "custody_tree_too_deep",
                "custody tree exceeds its bounded traversal depth",
            )
        for entry in os.scandir(current):
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            mode = st.st_mode
            if (mode & 0o170000) == 0o040000:
                stack.append((entry.path, depth + 1))
            elif (mode & 0o170000) == 0o100000:
                files += 1
                if files > _TREE_MAX_FILES:
                    raise CustodyJobError(
                        "custody_tree_too_large",
                        "custody tree exceeds its bounded file count",
                    )
                total += st.st_size
    return total


def _runs_usage(runs_path: str | Path) -> int:
    """Published (non-staging) run directory count."""
    return sum(
        1
        for _name, mode, _size in _dir_entries(runs_path)
        if not _name.startswith(".") and (mode & 0o170000) == 0o040000
    )


def _jobs_usage(jobs_fd: int, jobs_path: str | Path) -> tuple[int, int, int, int, int]:
    """(record count, active job count, reserved bytes, reserved
    retained slots, ACTUAL metadata bytes incl. temp records) over the
    jobs directory."""
    records = 0
    active = 0
    reserved = 0
    reserved_slots = 0
    metadata_bytes = 0
    for name, mode, size in _dir_entries(jobs_path):
        if (mode & 0o170000) != 0o100000:
            continue
        if name.startswith(".tmp-"):
            metadata_bytes += size
            continue
        if not _JOB_NAME_RE.fullmatch(name):
            metadata_bytes += size
            continue
        metadata_bytes += size
        record = _read_job_file(jobs_fd, name)
        if record is None:
            continue
        records += 1
        if record.get("status") in ("queued", "running"):
            active += 1
            try:
                reserved += int(record.get("reserved_bytes") or 0)
            except (TypeError, ValueError):
                reserved += _MAX_JOB_FILE_BYTES
            if record.get("reserved_slot"):
                reserved_slots += 1
    return records, active, reserved, reserved_slots, metadata_bytes


def _locks_bytes(locks_path: str | Path) -> int:
    """ACTUAL bytes of the small locks/ metadata (admission lock)."""
    return sum(
        size for _name, mode, size in _dir_entries(locks_path)
        if (mode & 0o170000) == 0o100000
    )


def _custody_usage(root: Path) -> tuple[int, int, int, int, int, int]:
    """(published artifacts, job records, active jobs, total bytes,
    reserved bytes, reserved retained slots) - every custody byte is
    accounted, staging included."""
    runs_fd = _open_subdir(root, "runs")
    try:
        published = _runs_usage(root / "runs")
    finally:
        os.close(runs_fd)
    runs_bytes = _dir_tree_bytes(root / "runs")
    proposals_fd = _open_subdir(root, "proposals")
    try:
        proposal_dirs = [
            name for name, mode, _s in _dir_entries(root / "proposals")
            if not name.startswith(".") and (mode & 0o170000) == 0o040000
        ]
    finally:
        os.close(proposals_fd)
    proposals_bytes = _dir_tree_bytes(root / "proposals")
    uploads_fd = _open_subdir(root, "uploads")
    try:
        pass
    finally:
        os.close(uploads_fd)
    uploads_bytes = _dir_tree_bytes(root / "uploads")
    jobs_fd = _open_subdir(root, "jobs")
    try:
        records, active, reserved, reserved_slots, jobs_bytes = _jobs_usage(
            jobs_fd, root / "jobs"
        )
    finally:
        os.close(jobs_fd)
    locks_fd = _open_subdir(root, "locks")
    try:
        locks_bytes = _locks_bytes(root / "locks")
    finally:
        os.close(locks_fd)
    total_bytes = (
        runs_bytes + proposals_bytes + uploads_bytes + jobs_bytes + locks_bytes
    )
    return (
        published + len(proposal_dirs),
        records,
        active,
        total_bytes,
        reserved,
        reserved_slots,
    )


def _reservation_for(family: str) -> tuple[int, bool]:
    """(reserved bytes, reserved retained slot) per closed family."""
    if family in ("collect", "review_supplied"):
        return (
            _RUN_RESERVATION_BYTES
            + _UPLOAD_CEILING_BYTES
            + _MAX_JOB_FILE_BYTES
        ), True
    if family == "export_baseline":
        return MAX_BASELINE_BYTES + _MAX_JOB_FILE_BYTES, True
    if family == "proposal":
        return _PROPOSAL_RESERVATION_BYTES + _MAX_JOB_FILE_BYTES, True
    raise CustodyJobError("job_family_invalid", "unknown job family")


def create_job(settings: Settings, family: str, params: dict[str, Any]) -> str:
    """Admit and record ONE new job under the custody bounds.

    The admission check and the NEW-ONLY record creation happen under the
    same cross-process lock. The admitted job RESERVES its finite byte
    ceiling and (when it may publish an artifact) its retained slot in
    the same locked step, so concurrent API requests and worker
    processes can never exceed the bounds: full capacity refuses
    explicitly and custody can never exceed the bounds at rest.
    """
    if family not in CATALOG_JOB_FAMILIES:
        raise CustodyJobError("job_family_invalid", "unknown job family")
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    root = setup.root
    reserved_bytes, reserved_slot = _reservation_for(family)
    with _admission_lock(root):
        jobs_fd = _open_subdir(root, "jobs")
        try:
            (
                artifacts,
                records,
                active,
                total_bytes,
                reserved,
                reserved_slots,
            ) = _custody_usage(root)
            if active >= settings.CATALOG_REFRESH_MAX_ACTIVE_JOBS:
                raise CustodyCapacityError(
                    "active_job_capacity",
                    f"the configured maximum of "
                    f"{settings.CATALOG_REFRESH_MAX_ACTIVE_JOBS} active catalog "
                    "refresh job(s) is already in use; wait for the running "
                    "job to finish before queuing another",
                )
            if reserved_slot and (
                artifacts + reserved_slots >= settings.CATALOG_REFRESH_MAX_RETAINED_RUNS
            ):
                raise CustodyCapacityError(
                    "retained_runs_capacity",
                    f"the custody already retains (or reserves) "
                    f"{settings.CATALOG_REFRESH_MAX_RETAINED_RUNS} runs/proposal "
                    "artifacts (the configured maximum); clean up old runs "
                    "or finished job records from the console before "
                    "queuing new work",
                )
            if records >= settings.CATALOG_REFRESH_MAX_RETAINED_RUNS * _JOB_RECORD_MAX_FACTOR:
                raise CustodyCapacityError(
                    "job_record_capacity",
                    "too many catalog refresh job records are retained; "
                    "clean up finished job records from the console before "
                    "queuing new work",
                )
            if total_bytes + reserved + reserved_bytes >= settings.CATALOG_REFRESH_MAX_TOTAL_BYTES:
                raise CustodyCapacityError(
                    "total_bytes_capacity",
                    "the custody already holds the configured maximum total "
                    "bytes (published runs, uploads, staging, and reserved "
                    "capacity); clean up old runs/proposals from the "
                    "console before queuing new work",
                )
            job_id = uuid.uuid4().hex
            record = {
                "schema_version": "1",
                "job_id": job_id,
                "family": family,
                "status": "queued",
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "run_id": None,
                "progress": "queued",
                "dispatch": None,
                "error_code": None,
                "cancel_requested": False,
                "delivered": False,
                "reserved_bytes": reserved_bytes,
                "reserved_slot": bool(reserved_slot),
                "params": params,
            }
            _write_job_file_new_only(jobs_fd, _job_name(job_id), record)
        finally:
            os.close(jobs_fd)
    return job_id


def _read_job_or_none(settings: Settings, job_id: str) -> dict[str, Any] | None:
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    jobs_fd = _open_subdir(setup.root, "jobs")
    try:
        return _read_job_file(jobs_fd, _job_name(job_id))
    finally:
        os.close(jobs_fd)


def begin_job(settings: Settings, job_id: str) -> dict[str, Any] | None:
    """Worker pickup guard: claim one queued job exactly once.

    - Unknown job id -> None (late/duplicate/foreign delivery: do nothing).
    - Cancel-requested queued job -> terminal ``canceled`` WITHOUT
      executing (delayed delivery can never run it).
    - Terminal or already-claimed job -> None (never re-execute, never
      overwrite).
    - Otherwise -> mark ``running`` and return the record.
    """
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return None
    root = setup.root
    with _admission_lock(root):
        jobs_fd = _open_subdir(root, "jobs")
        try:
            record = _read_job_file(jobs_fd, _job_name(job_id))
            if record is None:
                return None
            status = record.get("status")
            if status in CATALOG_TERMINAL_STATUSES:
                return None
            if record.get("cancel_requested") and status == "queued":
                record["status"] = "canceled"
                record["progress"] = "canceled before execution"
                record["updated_at"] = _now_iso()
                record["error_code"] = None
                record["reserved_bytes"] = 0
                record["reserved_slot"] = False
                _write_job_file_atomic(jobs_fd, _job_name(job_id), record)
                return None
            if status == "running":
                # A concurrent (or duplicate) delivery already claimed it.
                return None
            record["status"] = "running"
            record["delivered"] = True
            record["progress"] = "running"
            record["updated_at"] = _now_iso()
            _write_job_file_atomic(jobs_fd, _job_name(job_id), record)
            return record
        finally:
            os.close(jobs_fd)


def finish_job(
    settings: Settings,
    job_id: str,
    status: str,
    *,
    run_id: str | None = None,
    progress: str | None = None,
    error_code: str | None = None,
    artifact_name: str | None = None,
) -> bool:
    """Record a terminal outcome for one job (NEW terminal only) and
    release its reservation.

    ``artifact_name`` is the generated server custody name of one stored
    output artifact (e.g. an exported baseline document); it is recorded
    on the terminal job record and exposed in the safe projection.

    Returns False when the job is unknown or already terminal: late or
    duplicate delivery can never overwrite a published sealed artifact or
    claim another task's outcome.
    """
    if status not in CATALOG_JOB_STATUSES:
        raise CustodyJobError("job_status_invalid", "unknown job status")
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return False
    root = setup.root
    with _admission_lock(root):
        jobs_fd = _open_subdir(root, "jobs")
        try:
            record = _read_job_file(jobs_fd, _job_name(job_id))
            if record is None:
                return False
            if record.get("status") in CATALOG_TERMINAL_STATUSES:
                return False
            record["status"] = status
            if run_id is not None:
                record["run_id"] = run_id
            if progress is not None:
                record["progress"] = progress
            if artifact_name is not None:
                record["artifact_name"] = artifact_name
            record["error_code"] = error_code
            record["updated_at"] = _now_iso()
            record["reserved_bytes"] = 0
            record["reserved_slot"] = False
            _write_job_file_atomic(jobs_fd, _job_name(job_id), record)
            return True
        finally:
            os.close(jobs_fd)


def request_cancel(settings: Settings, job_id: str) -> bool:
    """Cancel one non-terminal job, under the existing admission lock.

    A still-QUEUED/unclaimed job is canceled TERMINALLY here and its
    reservations are released immediately: if the broker dispatch failed
    or the message is lost, no worker can ever acknowledge it, so the
    active slot must not stay occupied and a later retry must be
    admissible. A delayed delivery of such a message then finds the
    terminal state in ``begin_job`` and never executes.

    A claimed/running job keeps the honest cooperative cancel-requested
    flag: its read-only checkpoints resolve the terminal truthfully
    (``canceled`` versus ``failed``)."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    root = setup.root
    with _admission_lock(root):
        jobs_fd = _open_subdir(root, "jobs")
        try:
            record = _read_job_file(jobs_fd, _job_name(job_id))
            if record is None:
                raise CustodyJobError("job_unknown", "unknown job id")
            if record.get("status") in CATALOG_TERMINAL_STATUSES:
                return False
            if (
                record.get("status") == "queued"
                and not record.get("delivered")
            ):
                record["status"] = "canceled"
                record["progress"] = "canceled before execution"
                record["cancel_requested"] = True
                record["error_code"] = None
                record["reserved_bytes"] = 0
                record["reserved_slot"] = False
                record["updated_at"] = _now_iso()
                _write_job_file_atomic(jobs_fd, _job_name(job_id), record)
                return True
            record["cancel_requested"] = True
            record["progress"] = (
                "cancel requested; read-only checkpoints until a terminal "
                "fact is known"
            )
            record["updated_at"] = _now_iso()
            _write_job_file_atomic(jobs_fd, _job_name(job_id), record)
            return True
        finally:
            os.close(jobs_fd)


def note_dispatch(
    settings: Settings, job_id: str, *, dispatched: bool, detail: str
) -> bool:
    """Persist safe broker-dispatch uncertainty on ONE non-terminal job.

    Broker admission is not completion: a failed or lost dispatch is
    recorded on the existing job metadata so the console stays truthful
    across refreshes (the operator can then cancel the job to release
    its slot and re-queue). This is a NON-TERMINAL metadata update - it
    never changes status, claims the job, or releases reservations, and
    it is never a substitute for ``finish_job``. Returns False for
    unknown or terminal jobs (no silent overwrite)."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return False
    root = setup.root
    safe_detail = " ".join(str(detail or "").split())[:200]
    with _admission_lock(root):
        jobs_fd = _open_subdir(root, "jobs")
        try:
            record = _read_job_file(jobs_fd, _job_name(job_id))
            if record is None:
                return False
            if record.get("status") in CATALOG_TERMINAL_STATUSES:
                return False
            record["dispatch"] = "confirmed" if dispatched else "unconfirmed"
            if dispatched:
                record["progress"] = (
                    "queued (broker acknowledged; a running worker is "
                    "not yet proven)"
                )
            else:
                record["progress"] = (
                    "queued, dispatch unconfirmed"
                    + (f" ({safe_detail})" if safe_detail else "")
                    + "; cancel the job to release its slot, then re-queue"
                )
            record["updated_at"] = _now_iso()
            _write_job_file_atomic(jobs_fd, _job_name(job_id), record)
            return True
        finally:
            os.close(jobs_fd)


def cancel_check(settings: Settings, job_id: str) -> Callable[[], bool]:
    """A LIVE cancellation callable for the shared application's
    cooperative checkpoints (pre-baseline, pre-collect, per retrieval
    phase, before staging, and immediately before the NEW-ONLY
    publication).

    It re-reads the custody record on every call, so a flag set after an
    earlier checkpoint is still observed at the final pre-publication
    gate: a canceled task cannot publish ready output after cancellation
    was requested and observed at that gate.
    """

    def _check() -> bool:
        record = _read_job_or_none(settings, job_id)
        if record is None:
            return True  # custody lost: fail closed at the next checkpoint
        if record.get("status") in CATALOG_TERMINAL_STATUSES:
            return True
        return bool(record.get("cancel_requested"))

    return _check


def job_cancel_requested(settings: Settings, job_id: str) -> bool:
    """Truthful live re-read: an operator cancellation was requested for
    this job (regardless of its current status). Lost/unknown custody
    reports False - the caller's fail-closed checkpoint already treats
    that as interrupted."""
    record = _read_job_or_none(settings, job_id)
    return bool(record is not None and record.get("cancel_requested"))


def job_projection(record: dict[str, Any]) -> dict[str, Any]:
    """Safe server projection of one job record (no raw params)."""
    return {
        "job_id": record.get("job_id"),
        "family": record.get("family"),
        "status": record.get("status"),
        "progress": record.get("progress") or "",
        "dispatch": record.get("dispatch"),
        "run_id": record.get("run_id"),
        "artifact_name": record.get("artifact_name"),
        "error_code": record.get("error_code"),
        "cancel_requested": bool(record.get("cancel_requested")),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def list_jobs(settings: Settings, limit: int = 100) -> list[dict[str, Any]]:
    """Newest-first safe projections of recorded jobs (bounded view)."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return []
    root = setup.root
    jobs_fd = _open_subdir(root, "jobs")
    try:
        records: list[dict[str, Any]] = []
        for entry in os.scandir(str(root / "jobs")):
            if not _JOB_NAME_RE.fullmatch(entry.name):
                continue
            record = _read_job_file(jobs_fd, entry.name)
            if record is not None:
                records.append(record)
    finally:
        os.close(jobs_fd)
    records.sort(
        key=lambda r: (r.get("created_at") or "", r.get("job_id") or ""),
        reverse=True,
    )
    return [job_projection(r) for r in records[: max(1, min(limit, 100))]]


def get_job(settings: Settings, job_id: str) -> dict[str, Any] | None:
    """Exact-ID read of ONE recorded job (closed custody lookup).

    The GUI uses this to bind acknowledgements and refresh navigation to
    the EXACT job the server created, so a concurrent same-family job can
    never substitute for it. Unknown or malformed ids return None; no
    listing and no "latest" fallback happen here.
    """
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return None
    try:
        record = _read_job_or_none(settings, job_id)
    except (AdminCatalogRefreshError, CustodyJobError):
        return None
    if record is None:
        return None
    return job_projection(record)


def job_provider_scope(settings: Settings, job_id: str) -> str | None:
    """Bounded accessor for the provider scope of ONE recorded proposal
    job (closed set only). None for unknown ids, other families, or
    values outside the supported scope vocabulary."""
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return None
    try:
        record = _read_job_or_none(settings, job_id)
    except (AdminCatalogRefreshError, CustodyJobError):
        return None
    if record is None or record.get("family") != "proposal":
        return None
    scope = (record.get("params") or {}).get("provider_scope")
    if scope in ("openai", "openrouter", "all"):
        return str(scope)
    return None


def store_upload(
    settings: Settings,
    job_id: str,
    kind: str,
    content: bytes,
    name: str | None = None,
) -> str:
    """Store one bounded uploaded artifact under uploads/<job_id>/ with a
    GENERATED name (the browser filename is untrusted and never used), or
    with a PRE-ALLOCATED closed name when ``name`` is given (it must match
    the exact generated-name shape for the kind; the O_EXCL write keeps
    the operation NEW-ONLY). The size bound is the EXACT Core bound for
    the kind (bundle 8 MiB, baseline 32 MiB) and the write is
    capacity-checked under the same lock as admission. Returns the
    stored file name."""
    if kind == "bundle":
        cap = MAX_BUNDLE_BYTES
    elif kind == "baseline":
        cap = MAX_BASELINE_BYTES
    else:
        raise CustodyJobError("upload_kind_invalid", "unknown upload kind")
    if len(content) > cap:
        raise CustodyJobError("upload_too_large", "uploaded artifact exceeds its bound")
    leaf = _canonical_job_leaf(job_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    root = setup.root
    if name is None:
        name = f"{kind}-{uuid.uuid4().hex}"
    elif not re.fullmatch(rf"{kind}-[0-9a-f]{{32}}", name):
        raise CustodyJobError("upload_name_invalid", "upload name is outside its closed shape")
    with _admission_lock(root):
        # The per-job upload directory is created (0700) through the
        # anchored Core walk inside the existing root, then verified.
        job_handle = open_anchored_handle(root / "uploads" / leaf, create_missing=True)
        uploads_fd = _open_subdir(root, "uploads")
        try:
            st = os.fstat(job_handle.dir_fd)
            if (st.st_mode & 0o777) != 0o700 or st.st_uid != os.getuid():
                raise CustodyJobError("upload_dir_unsafe", "upload directory is unsafe")
            _artifacts, _records, _active, total_bytes, reserved, _slots = _custody_usage(root)
            if total_bytes + reserved + len(content) >= settings.CATALOG_REFRESH_MAX_TOTAL_BYTES:
                raise CustodyCapacityError(
                    "total_bytes_capacity",
                    "the custody already holds the configured maximum total "
                    "bytes; clean up old runs/proposals from the console "
                    "before uploading",
                )
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=job_handle.dir_fd,
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            job_handle.close()
            os.close(uploads_fd)
            raise
        job_handle.close()
        os.close(uploads_fd)
    return name


def upload_exists(settings: Settings, job_id: str, name: str) -> bool:
    """Bounded anchored existence probe for ONE stored upload (closed
    name shape, regular file only). Never reads content."""
    if not isinstance(name, str) or not _UPLOAD_NAME_RE.fullmatch(name):
        raise CustodyJobError("artifact_not_served", "artifact is not served")
    try:
        leaf = _canonical_job_leaf(job_id)
    except CustodyJobError:
        return False
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return False
    uploads_fd = _open_subdir(setup.root, "uploads")
    try:
        try:
            job_fd = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=uploads_fd
            )
        except OSError:
            return False
        try:
            st = os.stat(name, dir_fd=job_fd, follow_symlinks=False)
        except OSError:
            return False
        finally:
            os.close(job_fd)
        return (st.st_mode & 0o170000) == 0o100000
    finally:
        os.close(uploads_fd)


def read_job_artifact(
    settings: Settings, job_id: str, name: str
) -> bytes | None:
    """Read one bounded job artifact through the held anchored handles,
    capped at the EXACT Core bound for the artifact kind."""
    if not isinstance(name, str) or not _JOB_ARTIFACT_NAME_RE.fullmatch(name):
        raise CustodyJobError("artifact_not_served", "artifact is not served")
    # The job id is a caller value: strict closed-leaf derivation BEFORE
    # any open (the name is a closed generated shape; its canonical
    # single-component form is byte-identical).
    leaf = _canonical_job_leaf(job_id)
    name_leaf = os.path.basename(name)
    if name.startswith("bundle"):
        cap = MAX_BUNDLE_BYTES
    else:
        cap = MAX_BASELINE_BYTES
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    uploads_fd = _open_subdir(setup.root, "uploads")
    try:
        job_fd = os.open(
            leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=uploads_fd
        )
    except OSError:
        os.close(uploads_fd)
        return None
    try:
        return anchored_read_fd(job_fd, name_leaf, cap)
    except (OSError, CatalogRefreshSealError):
        return None
    finally:
        os.close(job_fd)
        os.close(uploads_fd)


# Closed generated proposal output names (the provider-catalog proposal
# service's SUPPORTED_OUTPUT_FILES - it is a DISTINCT proposal-only
# service and never produces a catalog-refresh bundle).
_PROPOSAL_ARTIFACT_NAMES = frozenset(
    {
        "source-manifest.json",
        "provider-catalog-normalized.json",
        "routes-proposal.tsv",
        "pricing-proposal.tsv",
        "provider-catalog-report.md",
        "warnings.json",
    }
)


# Closed generated file set inside one packages/<preset>/ directory
# (the provider-catalog proposal service's per-package output).
_PROPOSAL_PACKAGE_FILE_NAMES = frozenset(
    {
        "routes-proposal.tsv",
        "pricing-proposal.tsv",
        "package-report.md",
        "model-review.md",
        "package-manifest.json",
    }
)


def read_proposal_artifact(
    settings: Settings, job_id: str, name: str
) -> bytes | None:
    """Read one bounded GENERATED proposal artifact through the held
    anchored handles (closed name set, capped at the enforced 32 MiB
    proposal output ceiling - the same bound the proposal generator's
    write admission enforces)."""
    if not isinstance(name, str) or name not in _PROPOSAL_ARTIFACT_NAMES:
        raise CustodyJobError("artifact_not_served", "artifact is not served")
    leaf = _canonical_job_leaf(job_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    proposals_fd = _open_subdir(setup.root, "proposals")
    try:
        try:
            job_fd = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=proposals_fd
            )
        except OSError:
            return None
        try:
            return anchored_read_fd(job_fd, name, _PROPOSAL_RESERVATION_BYTES)
        except (OSError, CatalogRefreshSealError):
            return None
        finally:
            os.close(job_fd)
    finally:
        os.close(proposals_fd)


def list_proposal_packages(settings: Settings, job_id: str) -> list[str]:
    """List the GENERATED OpenRouter packages for one proposal job.

    Closed known-preset enumeration: iterate the service's
    OPENROUTER_PACKAGE_ORDER and keep only presets whose directory
    exists, each through a held no-follow component open (no general
    directory scan)."""
    leaf = _canonical_job_leaf(job_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    proposals_fd = _open_subdir(setup.root, "proposals")
    try:
        try:
            job_fd = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=proposals_fd
            )
        except OSError:
            return []
        try:
            try:
                packages_fd = os.open(
                    "packages",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                    dir_fd=job_fd,
                )
            except OSError:
                return []
            try:
                present: list[str] = []
                for preset in OPENROUTER_PACKAGE_ORDER:
                    try:
                        preset_fd = os.open(
                            preset,
                            os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                            dir_fd=packages_fd,
                        )
                    except OSError:
                        continue
                    os.close(preset_fd)
                    present.append(preset)
                return present
            finally:
                os.close(packages_fd)
        finally:
            os.close(job_fd)
    finally:
        os.close(proposals_fd)


def read_proposal_package_artifact(
    settings: Settings, job_id: str, preset: str, name: str
) -> bytes | None:
    """Read one bounded GENERATED package file through the held anchored
    handles (closed preset + closed file set, capped at the enforced
    32 MiB proposal output ceiling)."""
    if not isinstance(preset, str) or preset not in OPENROUTER_PACKAGE_ORDER:
        raise CustodyJobError("artifact_not_served", "artifact is not served")
    if not isinstance(name, str) or name not in _PROPOSAL_PACKAGE_FILE_NAMES:
        raise CustodyJobError("artifact_not_served", "artifact is not served")
    leaf = _canonical_job_leaf(job_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    proposals_fd = _open_subdir(setup.root, "proposals")
    try:
        try:
            job_fd = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=proposals_fd
            )
        except OSError:
            return None
        try:
            return anchored_read_fd(
                job_fd, "packages/" + preset + "/" + name, _PROPOSAL_RESERVATION_BYTES
            )
        except (OSError, CatalogRefreshSealError):
            return None
        finally:
            os.close(job_fd)
    finally:
        os.close(proposals_fd)
def open_proposal_dir(settings: Settings, job_id: str) -> Path:
    """Create/return the private proposals/<job_id>/ output directory for
    one proposal job (0700, server-named). Refuses existing unsafe
    entries; never repairs permissions."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    # Created (0700) through the anchored Core walk inside the existing
    # root, then verified; never a raw O_CREAT on a caller-shaped name.
    job_handle = open_anchored_handle(
        setup.root / "proposals" / job_id, create_missing=True
    )
    proposals_fd = _open_subdir(setup.root, "proposals")
    try:
        st = os.fstat(job_handle.dir_fd)
        if (st.st_mode & 0o777) != 0o700 or st.st_uid != os.getuid():
            raise CustodyJobError("proposal_dir_unsafe", "proposal directory is unsafe")
    finally:
        job_handle.close()
        os.close(proposals_fd)
    return setup.root / "proposals" / job_id


def account_proposal_output(settings: Settings, job_id: str) -> None:
    """Post-generation custody gate for ONE proposal output set.

    Under the admission lock: measure the actual bytes and, if the
    custody would exceed the configured total bound, retract the output
    (identity-checked cleanup) and refuse - never exceeding the bound at
    rest, never leaving a labeled-complete artifact over capacity.
    """
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    leaf = _canonical_job_leaf(job_id)
    root = setup.root
    with _admission_lock(root):
        proposals_fd = _open_subdir(root, "proposals")
        try:
            try:
                _dir_tree_bytes(setup.root / "proposals" / leaf)
            except (OSError, CustodyJobError):
                return  # nothing published: nothing to account
            jobs_fd = _open_subdir(root, "jobs")
            try:
                record = _read_job_file(jobs_fd, _job_name(leaf))
            finally:
                os.close(jobs_fd)
            if record is None:
                return
            (
                _artifacts,
                _records,
                _active,
                total_bytes,
                _reserved_total,
                _slots,
            ) = _custody_usage(root)
            # total_bytes is the AT-REST custody: it already includes the
            # actual proposal output bytes (proposals/job_id) on disk and
            # EXCLUDES the virtual admission reservation (a hold released
            # at finish, changing no disk usage). The old
            # 'total_bytes - reserved + actual' double-counted actual and
            # wrongly subtracted the never-on-disk reservation.
            if total_bytes > settings.CATALOG_REFRESH_MAX_TOTAL_BYTES:
                remove_proposal_dir(settings, leaf)
                raise CustodyCapacityError(
                    "proposal_output_capacity",
                    "the proposal output would exceed the configured "
                    "maximum total custody bytes; it was retracted and no "
                    "complete proposal was published",
                )
        finally:
            os.close(proposals_fd)


def _remove_subtree_anchored(path: Path, dir_fd: int, depth: int, seen: list[int]) -> None:
    """Bounded identity-checked recursive removal of the subtree BELOW a
    held directory descriptor: every entry must be a regular file or
    directory (symlinks and special files refuse), files are unlinked
    through the held dir_fd, subdirectories are opened O_NOFOLLOW through
    the parent descriptor and removed deepest-first. Bounded by the
    custody tree depth/entry limits; any refusal raises and leaves the
    remaining tree untouched (best-effort bounded cleanup)."""
    if depth > _TREE_MAX_DEPTH:
        raise CustodyJobError(
            "proposal_tree_too_deep", "proposal tree exceeds its bounded depth"
        )
    for entry in os.scandir(str(path)):
        seen[0] += 1
        if seen[0] > _TREE_MAX_FILES:
            raise CustodyJobError(
                "proposal_tree_too_large", "proposal tree exceeds its bounded entry count"
            )
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            raise CustodyJobError(
                "proposal_entry_unsafe", "proposal tree entry cannot be inspected"
            )
        mode = st.st_mode
        if (mode & 0o170000) == 0o100000:
            os.unlink(entry.name, dir_fd=dir_fd)
        elif (mode & 0o170000) == 0o040000:
            sub_fd = os.open(
                entry.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=dir_fd,
            )
            try:
                _remove_subtree_anchored(Path(entry.path), sub_fd, depth + 1, seen)
            finally:
                os.close(sub_fd)
            os.rmdir(entry.name, dir_fd=dir_fd)
        else:
            raise CustodyJobError(
                "proposal_entry_unsafe", "proposal tree contains an unsafe entry"
            )


def remove_proposal_dir(settings: Settings, job_id: str) -> None:
    """Identity-checked cleanup of ONE proposal output subtree (files and
    NESTED package directories, bounded): opened O_NOFOLLOW through the
    held proposals descriptor, permission/ownership re-verified, removed
    recursively through the held descriptors, then the empty directory is
    unlinked. Any refusal leaves custody untouched."""
    try:
        leaf = _canonical_job_leaf(job_id)
    except CustodyJobError:
        return  # unknown id: nothing owned to clean (same silent contract)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return
    proposals_fd = _open_subdir(setup.root, "proposals")
    try:
        try:
            fd = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=proposals_fd
            )
        except OSError:
            return
        try:
            st = os.fstat(fd)
            if (st.st_mode & 0o777) != 0o700 or st.st_uid != os.getuid():
                return  # refuse: unsafe directory
            _remove_subtree_anchored(
                setup.root / "proposals" / leaf, fd, 1, [0]
            )
            os.rmdir(leaf, dir_fd=proposals_fd)
        except (OSError, CustodyJobError):
            return  # refuse: leave custody untouched (best-effort bounded)
        finally:
            os.close(fd)
    finally:
        os.close(proposals_fd)


def remove_terminal_job(settings: Settings, job_id: str) -> None:
    """Explicit operator cleanup of ONE TERMINAL job record.

    Bounded owned terminal-artifact cleanup: in addition to the JSON
    record, the job's OWN generated upload artifacts
    (uploads/<job_id>/) and generated proposal output
    (proposals/<job_id>/) are removed through the same identity-checked
    anchored helpers. Absent subtrees are nothing to clean; an existing
    but unsafe/unremovable subtree refuses the whole cleanup (custody
    left untouched). The published RUN this job produced is a separate
    custody object (removed only by remove_terminal_run)."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    leaf = _canonical_job_leaf(job_id)
    root = setup.root
    with _admission_lock(root):
        jobs_fd = _open_subdir(root, "jobs")
        try:
            record = _read_job_file(jobs_fd, _job_name(leaf))
            if record is None:
                raise CustodyJobError("job_unknown", "unknown job id")
            if record.get("status") not in CATALOG_TERMINAL_STATUSES:
                raise CustodyJobError(
                    "job_cleanup_refused", "only finished jobs can be cleaned up"
                )
            # Bounded owned terminal-artifact cleanup (uploads/<job_id>/
            # and proposals/<job_id>/) happens BEFORE the record unlink
            # under the same lock: an unsafe/unremovable subtree refuses
            # the whole cleanup and the record stays in place.
            _remove_job_artifact_subtree(root, "uploads", leaf)
            _remove_job_artifact_subtree(root, "proposals", leaf)
            os.unlink(_job_name(leaf), dir_fd=jobs_fd)
        finally:
            os.close(jobs_fd)


def _remove_job_artifact_subtree(root: Path, subdir: str, job_id: str) -> None:
    """Identity-checked removal of ONE job's owned artifact subtree
    (uploads/<job_id>/ or proposals/<job_id>/): opened O_NOFOLLOW
    through the held parent descriptor, ownership/mode re-verified,
    removed recursively through the held descriptors (bounded), then
    unlinked. Absent subtree -> no-op. Any refusal raises (the caller
    leaves custody untouched and the job record in place)."""
    leaf = _canonical_job_leaf(job_id)
    parent_fd = _open_subdir(root, subdir)
    try:
        try:
            fd = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent_fd
            )
        except FileNotFoundError:
            return
        except OSError:
            raise CustodyJobError(
                "job_artifact_unsafe", "the job artifact entry cannot be opened safely"
            ) from None
        try:
            st = os.fstat(fd)
            if (st.st_mode & 0o777) != 0o700 or st.st_uid != os.getuid():
                raise CustodyJobError(
                    "job_artifact_unsafe", "the job artifact directory is unsafe"
                )
            _remove_subtree_anchored(
                root / subdir / leaf, fd, 1, [0]
            )
            os.rmdir(leaf, dir_fd=parent_fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise CustodyJobError(
            "job_artifact_unsafe", "the job artifact subtree could not be removed safely"
        ) from exc
    finally:
        os.close(parent_fd)


# --- run custody (canonical UUID -> server custody) ------------------------


def _assert_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise CustodyJobError("run_not_found", "unknown run id")
    return run_id.lower()


def open_run_handle(settings: Settings, run_id: str):
    """Map a canonical run UUID to server custody through the anchored
    no-follow walk. Raises CustodyJobError for unknown/unsafe runs. The
    caller OWNS the returned lifecycle handle (close it)."""
    _assert_run_id(run_id)
    leaf = os.path.basename(run_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    try:
        return open_anchored_handle(setup.root / "runs" / leaf, create_missing=False)
    except Exception as exc:
        raise CustodyJobError("run_not_found", "unknown run id") from exc


def load_run_capture(settings: Settings, run_id: str):
    """Authenticate ONE sealed run and return ``(capture, run_handle)``:
    the SAME verified captured bytes plus the held run lifecycle handle
    (descriptor lineage - no path reopen). Only EXISTING custody and
    EXISTING 0600 key material are opened; missing/unsafe setup and
    tampered runs raise. The caller OWNS the returned handle and must
    close it; the handle is already closed on any failure."""
    name = _assert_run_id(run_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None or setup.seal_key is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    run_dir = setup.root / "runs" / name
    key = load_seal_key_bytes(setup.seal_key)
    handle = open_run_handle(settings, name)
    try:
        handle.assert_name_binding(str(run_dir))
        capture = load_verified_capture(run_dir, key, run_handle=handle)
        handle.assert_name_binding(str(run_dir))
        return capture, handle
    except BaseException:
        handle.close()
        raise


def read_run_artifact(settings: Settings, run_id: str, name: str) -> bytes | None:
    """Serve one sealed run artifact: the SAME verified captured bytes.

    The run is authenticated through the existing Core seal boundary
    (anchored no-follow open, held run handle, existing 0600 key, receipt
    HMAC + manifest reconciliation, Core per-file caps). Only sealed
    CONTENT artifacts are served; the authentication files themselves
    (manifest/receipt) are never served raw. Every held handle is
    rechecked and closed.
    """
    if name not in CATALOG_RUN_ARTIFACTS:
        raise CustodyJobError("artifact_not_served", "artifact is not served")
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None or setup.seal_key is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    run_dir = setup.root / "runs" / _assert_run_id(run_id)
    key = load_seal_key_bytes(setup.seal_key)
    run_handle = open_run_handle(settings, run_id)
    try:
        run_handle.assert_name_binding(str(run_dir))
        capture = load_verified_capture(run_dir, key, run_handle=run_handle)
        run_handle.assert_name_binding(str(run_dir))
        return capture.content.get(name)
    finally:
        run_handle.close()


def list_runs(settings: Settings, limit: int = 100) -> list[dict[str, Any]]:
    """Bounded safe projections of published runs (newest first by
    generated_at where readable; unreadable runs stay honest)."""
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        return []
    root = setup.root
    runs_fd = _open_subdir(root, "runs")
    try:
        rows: list[dict[str, Any]] = []
        for entry in os.scandir(str(root / "runs")):
            if entry.name.startswith("."):
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            row: dict[str, Any] = {
                "run_id": entry.name,
                "state": None,
                "generated_at": None,
                "readable": False,
            }
            try:
                fd = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                    dir_fd=runs_fd,
                )
            except OSError:
                rows.append(row)
                continue
            try:
                raw = anchored_read_fd(fd, "validation.json", MAX_AUX_BYTES)
                document = _strict_json(raw, MAX_AUX_BYTES)
                # The sealed ValidationReport document carries the review
                # state at the TOP LEVEL (report.to_dict): read it there.
                state = document.get("state")
                if isinstance(state, str) and state:
                    row["state"] = state
                row["generated_at"] = document.get("generated_at")
                row["readable"] = True
            except (ValueError, OSError, CatalogRefreshSealError):
                pass
            finally:
                os.close(fd)
            rows.append(row)
    finally:
        os.close(runs_fd)
    rows.sort(
        key=lambda r: (r.get("generated_at") or "", r.get("run_id") or ""),
        reverse=True,
    )
    return rows[: max(1, min(limit, 100))]


def remove_terminal_run(settings: Settings, run_id: str) -> None:
    """Identity-checked explicit operator cleanup of ONE published run.

    Only a run whose entries are exactly the sealed Core file set (all
    regular non-symlink files) is removed, file by file through the held
    descriptor, then the empty directory is unlinked. Staging leftovers,
    symlinks, extra entries, or unreadable custody refuse.
    """
    _assert_run_id(run_id)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None:
        raise AdminCatalogRefreshError(
            setup.code, "catalog refresh custody is not usable: " + setup.code
        )
    normalized = _assert_run_id(run_id)
    # Canonical single-component leaf (byte-identical for valid run ids;
    # the grammar already excludes path separators; the configured
    # absolute root is never basenamed).
    leaf = os.path.basename(normalized)
    run_dir = setup.root / "runs" / leaf
    handle = open_run_handle(settings, run_id)
    try:
        entries = _dir_entries(run_dir)
        names = [name for name, _mode, _size in entries]
        # COMPLETE layout (hidden names included) must be EXACTLY the
        # sealed Core file set: no hidden/staging extras, no missing.
        # Refuse BEFORE any unlink so custody is left untouched.
        if sorted(names) != sorted(CORE_RUN_FILE_SET):
            raise CustodyJobError(
                "run_cleanup_refused",
                "run file set does not match the sealed Core layout",
            )
        # Every entry must be a regular non-symlink file (lstat mode);
        # symlinks, directories, and special entries refuse.
        for name, mode, _size in entries:
            if (mode & 0o170000) != 0o100000:
                raise CustodyJobError(
                    "run_cleanup_refused",
                    "run contains a non-regular or unsafe entry",
                )
        # Reassert the held name/lifecycle binding before mutating.
        handle.assert_name_binding(str(run_dir))
        for name in names:
            os.unlink(name, dir_fd=handle.dir_fd)
        handle.assert_name_binding(str(run_dir))
        runs_fd = _open_subdir(setup.root, "runs")
        try:
            os.rmdir(leaf, dir_fd=runs_fd)
        finally:
            os.close(runs_fd)
    finally:
        handle.close()
