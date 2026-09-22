"""Bounded, descriptor-anchored filesystem boundary for catalog refresh.

180-g (G1/G2/G3): the security boundary for ALL catalog-refresh input,
seal-key, run-content, manifest/receipt and output paths is a walk of held
directory descriptors with no-follow opens — never a lexical lstat/islink
check followed by a full-path open. Every component (including ancestors)
is opened O_NOFOLLOW while the previous component's descriptor is held, and
leaves are opened relative to the verified parent descriptor. A component
replaced by a symlink after verification therefore cannot redirect a later
operation: the later open happens against the held descriptor, not the
path.

Native stdlib interfaces are used for every operation that has one:
``os.open(name, flags, dir_fd=fd)``, ``os.mkdir(name, mode, dir_fd=fd)``
(mkdir(2) is atomic no-replace), ``os.unlink(name, dir_fd=fd)`` and
``os.rmdir(name, dir_fd=fd)``. The only ctypes wrapper is the narrow
``renameat2(RENAME_NOREPLACE)`` publication primitive, which stdlib does not
expose; it fails closed when unavailable and never falls back to
check-then-replace.

Descriptor ownership is explicit: a function never closes a descriptor it
did not open. Callers hold the run/staging/key-parent descriptors for the
entire create/write/seal/publish/cleanup lifecycle and pass them down; the
inode identity ``(st_dev, st_ino)`` captured at creation is re-checked
through the held parent before any failure cleanup, so a replaced (even
regular-directory) staging entry is never cleaned up or published.

Reads are regular-file reads on the opened descriptor: the type and size
are verified with ``fstat`` on that same descriptor BEFORE any byte is
read, size caps are enforced before allocation, leaves are opened
O_NONBLOCK so a FIFO can never block the caller, and the bounded reader
reads exactly the snapshotted size, then proves EOF (a file that grows
after the snapshot is refused), then re-checks the descriptor identity and
size after the read. Sockets, devices, and directories are refused with
safe typed errors; no device content is ever read. All validation and
authentication consumes the single captured byte snapshot returned here;
callers never reopen by path after checking. A same-size in-place mutation
racing the read is not detectable at the byte level; the captured bytes are
the only input to digests/HMAC/semantic checks, so any divergence is
detected by those authentications at verification time.

Publication of final names (sealed runs, minimal BLOCKED runs, exported
baselines) is atomic NEW-ONLY via ``renameat2(RENAME_NOREPLACE)`` anchored
to the verified parent descriptor. Existing empty/nonempty directories,
files, symlinks and concurrently created destinations stay untouched.

Manifest/receipt contracts are enforced BEFORE content is read (exact
expected content-file set, per-file bounds, aggregate bound including
manifest/receipt overhead) and the incremental remaining budget is applied
to every per-file read, so an entry that claims 1 byte never allocates
32 MiB.

Lifecycle binding: ``open_anchored_handle`` returns an ``AnchoredDir`` that
holds the descriptor of EVERY walked component for the whole operation.
``assert_name_binding`` re-verifies, hop by hop, that each component NAME
still resolves (no-follow, through the held parent descriptor) to the
identity captured at check time; a directory swapped in at ANY level of
the hierarchy (a cross-phase rename) voids the binding. The review CLI
keeps the run-root and seal-key-parent handles across the ENTIRE
lifecycle (containment check, key load, publication, error-report paths)
and refuses to publish or announce success if any checked binding
changed, so a stale display pathname can never announce a run for a
different root.

Mutation-namespace protection: names are only created/replaced/removed
through held descriptors inside directories that are verified to be
owned by the current user and NOT writable by group or other (checked
with fstat on the held descriptor). An unsafe supplied mutation parent
fails closed; existing directories are never chmod'ed. This enforces the
real unprivileged-peer boundary around the check-then-mutate seams: a
peer that cannot write the namespace cannot replace a name between the
identity check and the mutation. The threat scope explicitly excludes
root and hostile code holding the runner's full identity/authority (and
the key-controlling administrator).

Strict JSON (``strict_json_bytes``) rejects duplicate keys, non-finite
values, malformed and deeply nested input; its errors are constant strings
and never echo input bytes.

Platform assumptions (documented honestly): Linux; kernel >= 3.13 and glibc
>= 2.28 for ``renameat2``. The threat scope is local integrity against an
unprivileged local peer, not protection from an administrator who controls
the key or arbitrary privileged interference.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshSealError

# --- documented bounds -------------------------------------------------------

# Per run-content-file acceptance bound. Aligned with the baseline export
# bound (MAX_BASELINE_BYTES): a sealed run may legitimately carry a 32 MiB
# catalog-baseline.json, so the per-file bound must not be smaller.
MAX_FILE_BYTES = 32 * 1024 * 1024
# Small bound for the manifest/receipt (they hold 64 short entries at most).
MAX_AUX_BYTES = 1 * 1024 * 1024
# Aggregate bound for one run, INCLUDING manifest/receipt overhead.
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_FILES = 64
MAX_DEPTH = 4
# Documented pre-read overhead bound for the (deterministic-length) receipt
# used by the SIGNING path, which checks the aggregate bound before the
# receipt exists. The actual receipt is far smaller than this.
RECEIPT_MAX_BYTES = 8 * 1024

# Seal key file: 32 random bytes, persisted as 64 lowercase ASCII hex chars.
KEY_BYTES = 32
KEY_FILE_BYTES = KEY_BYTES * 2

_READ_CHUNK = 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# --- ctypes: renameat2(RENAME_NOREPLACE) only --------------------------------

_RENAME_NOREPLACE = 1  # include/linux/fcntl.h

_libc: ctypes.CDLL | None = None
_renameat2 = None


def _load_libc() -> ctypes.CDLL | None:
    global _libc
    if _libc is None:
        try:
            _libc = ctypes.CDLL("libc.so.6", use_errno=True)
        except OSError:
            _libc = None
    return _libc


class PublicationConflictError(CatalogRefreshSealError):
    """The final destination already exists; the atomic no-replace refused."""


def _renameat2_noreplace(src_dirfd: int, src_name: str, dst_dirfd: int, dst_name: str) -> None:
    """Atomic NEW-ONLY rename, anchored to the given parent descriptors.

    Raises PublicationConflictError on EEXIST and a safe typed error when
    the primitive is unavailable or fails for any other reason. Never falls
    back to check-then-replace.
    """
    global _renameat2
    libc = _load_libc()
    if libc is None or not hasattr(libc, "renameat2"):
        raise CatalogRefreshSealError(
            "atomic no-replace publication is not supported on this platform"
        )
    if _renameat2 is None:
        _renameat2 = libc.renameat2
        _renameat2.restype = ctypes.c_int
        _renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
    rc = _renameat2(
        src_dirfd,
        src_name.encode("utf-8"),
        dst_dirfd,
        dst_name.encode("utf-8"),
        _RENAME_NOREPLACE,
    )
    if rc == 0:
        return
    if ctypes.get_errno() == errno.EEXIST:
        raise PublicationConflictError(
            "destination already exists; refusing to overwrite"
        )
    raise CatalogRefreshSealError("atomic publication failed")


# --- strict JSON (shared by bundle, baseline, manifest, receipt, marker) -----


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            # Constant message: the (untrusted) key name is never echoed.
            raise ValueError("duplicate JSON key")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(_token: str) -> Any:
    raise ValueError("non-finite JSON constant")


def strict_json_bytes(raw: bytes, what: str) -> Any:
    """Parse JSON failing closed on duplicate keys, non-finite values,
    malformed or deeply nested input. The error never echoes input bytes."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogRefreshSealError(f"{what} is not valid UTF-8") from exc
    try:
        return json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_non_finite
        )
    except (json.JSONDecodeError, ValueError, RecursionError):
        raise CatalogRefreshSealError(f"{what} is not strictly valid JSON") from None


# --- descriptor-anchored path walks ------------------------------------------


def _validate_relative_name(name: str) -> None:
    if not name or name.startswith("/") or "\\" in name:
        raise CatalogRefreshSealError("unsafe run path")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise CatalogRefreshSealError("unsafe run path")
    if len(parts) > MAX_DEPTH:
        raise CatalogRefreshSealError("path depth exceeds bound")


def _validate_flat_name(name: str) -> None:
    if (
        not name
        or name in (".", "..")
        or name.startswith("/")
        or "/" in name
        or "\\" in name
    ):
        raise CatalogRefreshSealError("unsafe file name")


def _anchor_error(exc: OSError) -> CatalogRefreshSealError:
    if exc.errno in (errno.ENOENT, errno.ENOTDIR):
        return CatalogRefreshSealError("directory not found")
    if exc.errno == errno.ELOOP:
        return CatalogRefreshSealError("refusing symlink path component")
    return CatalogRefreshSealError("path cannot be safely opened")


def _open_component(
    dir_fd: int, name: str, flags: int, mode: int = 0, create_missing: bool = False
) -> int:
    """Open (and, when ``create_missing``, atomically create) one component
    relative to a HELD parent descriptor, no-follow.

    This is the barrier every component (including nested parents) passes
    through; tests exercise races at this exact seam. ``os.mkdir`` via
    ``dir_fd`` is mkdir(2): atomic, never replaces an existing entry.
    """
    try:
        if create_missing:
            try:
                os.mkdir(name, 0o700, dir_fd=dir_fd)
            except FileExistsError:
                pass
            except OSError as exc:
                raise _anchor_error(exc) from exc
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise _anchor_error(exc) from exc


def open_anchored_directory(
    path: Path, create_missing: bool = False
) -> tuple[int, list[tuple[int, int]]]:
    """Open ``path`` as a directory, walking every component with a held
    descriptor and O_NOFOLLOW (a symlinked component at ANY level fails).

    With ``create_missing=True``, absent components are created privately
    (mode 0700) atomically (mkdir(2), no-replace) through the same anchored
    walk — no unanchored mkdir happens anywhere.

    Returns ``(fd, chain)`` where ``chain`` is the ``(st_dev, st_ino)`` of
    each component from the first component below the filesystem root to
    the final directory (final last), fstat'ed on the held descriptors. The
    caller owns and must close ``fd``.
    """
    handle = open_anchored_handle(path, create_missing=create_missing)
    # The caller owns ONLY the returned directory descriptor; every other
    # owned descriptor (intermediate components, the direct parent, the
    # root) is closed exactly once here (intermediate descriptors appear
    # in both tuples).
    closed: set[int] = set()
    for fd in (*handle.component_fds, *handle.parent_fds):
        if fd != handle.dir_fd and fd not in closed:
            os.close(fd)
            closed.add(fd)
    return handle.dir_fd, list(handle.chain)


def _open_anchored(path: Path) -> tuple[int, list[tuple[int, int]]]:
    """Test seam for the anchored directory open (delegates directly)."""
    return open_anchored_directory(path)


def _assert_mutation_namespace(fd: int, what: str) -> None:
    """Verify (on the OPENED descriptor) that a directory whose entries we
    are about to create/rename/remove is operator-owned and not writable
    by group or other. Fails closed; never chmods."""
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode):
        raise CatalogRefreshSealError(f"{what} is not a directory")
    if st.st_uid != os.geteuid():
        raise CatalogRefreshSealError(f"{what} must be owned by the current user")
    if st.st_mode & 0o022:
        raise CatalogRefreshSealError(f"{what} must not be writable by group or other")


def _close_owned_fd(fd: int, expected_identity: tuple[int, int] | None) -> None:
    """Close an owned descriptor, refusing to close a number that no
    longer refers to the object we opened.

    Ownership is consumed exactly once per unique fd. If the number was
    freed earlier and has been reused for a DIFFERENT object (fstat
    identity mismatch), it is never closed — closing it would kill an
    unrelated descriptor. If it is already closed (EBADF), the number may
    likewise have been reused elsewhere and is left alone.
    """
    if expected_identity is None:
        return
    try:
        st = os.fstat(fd)
    except OSError:
        return  # already closed; the number may be reused elsewhere
    if (st.st_dev, st.st_ino) != expected_identity:
        return  # reused for a different object — never close
    try:
        os.close(fd)
    except OSError:
        pass


@dataclass(frozen=True, slots=True)
class AnchoredDir:
    """A directory held open with verified identity for a whole lifecycle.

    Holds the descriptor of every walked component (plus the root), the
    per-component names, and the ``(st_dev, st_ino)`` captured on the held
    descriptors at open time. Callers keep the handle across
    create/write/seal/publish/cleanup; nothing reopens a checked path by
    name between the containment check and the mutation.
    """

    parent_fds: tuple[int, ...]
    names: tuple[str, ...]
    component_fds: tuple[int, ...]
    chain: tuple[tuple[int, int], ...]
    fd_identities: dict[int, tuple[int, int]]

    @property
    def parent_fd(self) -> int:
        return self.parent_fds[-1]

    @property
    def name(self) -> str:
        return self.names[-1]

    @property
    def dir_fd(self) -> int:
        return self.component_fds[-1]

    @property
    def identity(self) -> tuple[int, int]:
        return self.chain[-1]

    def assert_name_binding(self, display: str = "") -> None:
        """Re-verify, hop by hop, that every component NAME still resolves
        (no-follow, through its HELD parent descriptor) to the identity
        captured at check time. A directory swapped in at ANY level of the
        hierarchy — rename or symlink, with or without inode reuse —
        breaks the binding and raises."""
        suffix = f": {display}" if display else ""
        for parent, name, expected in zip(self.parent_fds, self.names, self.chain):
            try:
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent
                )
            except OSError as exc:
                raise CatalogRefreshSealError(
                    f"checked directory binding changed{suffix}"
                ) from exc
            try:
                st = os.fstat(fd)
            finally:
                os.close(fd)
            if (st.st_dev, st.st_ino) != expected:
                raise CatalogRefreshSealError(
                    f"checked directory binding changed{suffix}"
                )

    def assert_mutation_namespace(self, what: str) -> None:
        """The directory we mutate entries in must be operator-owned and
        not writable by group or other (fstat on the held descriptor)."""
        _assert_mutation_namespace(self.dir_fd, what)

    def close(self) -> None:
        """Close every owned descriptor exactly once (ownership consumed).

        Intermediate component descriptors appear in BOTH tuples, so they
        are deduplicated. Each close is identity-checked against the
        object captured at open time: a freed fd number that has been
        reused for an unrelated object is never closed, so close() can
        never kill a concurrently reused foreign descriptor.
        """
        closed: set[int] = set()
        for fd in (*self.component_fds, *self.parent_fds):
            if fd in closed:
                continue
            closed.add(fd)
            _close_owned_fd(fd, self.fd_identities.get(fd))


def open_anchored_handle(path: Path, create_missing: bool = False) -> AnchoredDir:
    """Open ``path`` as a directory via the anchored walk and RETAIN the
    descriptors of every component (lifecycle handle).

    With ``create_missing=True``, absent components are created privately
    (mode 0700) atomically through the same walk. The returned handle is
    the unit of lifecycle binding: keep it open across the whole
    operation and call :meth:`AnchoredDir.assert_name_binding` before
    trusting the display pathname again. The caller owns all descriptors.
    """
    absolute = os.path.abspath(os.path.expanduser(str(path)))
    parts = [part for part in absolute.split(os.sep) if part not in ("", ".")]
    if not parts:
        raise CatalogRefreshSealError("path must be below the filesystem root")
    if any(part == ".." for part in parts):
        raise CatalogRefreshSealError("path traversal is not allowed")
    try:
        root_fd = os.open(os.sep, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
    except OSError as exc:
        raise CatalogRefreshSealError("cannot open the filesystem root") from exc
    parent_fds: list[int] = [root_fd]
    names: list[str] = []
    component_fds: list[int] = []
    chain: list[tuple[int, int]] = []
    fd_identities: dict[int, tuple[int, int]] = {}
    root_st = os.fstat(root_fd)
    fd_identities[root_fd] = (root_st.st_dev, root_st.st_ino)
    try:
        for part in parts:
            child = _open_component(
                parent_fds[-1],
                part,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                create_missing=create_missing,
            )
            st = os.fstat(child)
            names.append(part)
            component_fds.append(child)
            chain.append((st.st_dev, st.st_ino))
            fd_identities[child] = (st.st_dev, st.st_ino)
            parent_fds.append(child)
    except BaseException:
        closed: set[int] = set()
        for fd in (*component_fds, *parent_fds):
            if fd not in closed:
                closed.add(fd)
                _close_owned_fd(fd, fd_identities.get(fd))
        raise
    return AnchoredDir(
        parent_fds=tuple(parent_fds[:-1]),
        names=tuple(names),
        component_fds=tuple(component_fds),
        chain=tuple(chain),
        fd_identities=fd_identities,
    )


# --- bounded regular-file reads ----------------------------------------------

os_read = os.read  # test seam for short/growing-read injection


def _bounded_read_regular(fd: int, cap: int, display: str) -> bytes:
    """Read the complete regular file on an OPENED descriptor, bounded.

    Order of operations on the same fd:
      1. fstat: regular type, size <= cap (before any allocation);
      2. read exactly the snapshotted size (chunked, no oversize buffer);
      3. EOF probe: a byte past the snapshotted size means the file grew
         after the snapshot -> refuse;
      4. post-read fstat: the descriptor identity (st_dev, st_ino) and the
         size must be unchanged, proving a stable, complete file.
    A file that shrinks mid-read yields a short read -> refuse. Returns the
    single captured byte snapshot; the caller keeps the fd open/closed per
    its ownership rules.
    """
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        raise CatalogRefreshSealError(f"not a regular file: {display}")
    if st.st_size > cap:
        raise CatalogRefreshSealError(f"file exceeds the size bound: {display}")
    identity = (st.st_dev, st.st_ino)
    size = st.st_size
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = os_read(fd, min(remaining, _READ_CHUNK))
        if not chunk:
            raise CatalogRefreshSealError(f"short or growing read: {display}")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os_read(fd, 1):
        raise CatalogRefreshSealError(f"file grew after the size snapshot: {display}")
    st_after = os.fstat(fd)
    if (st_after.st_dev, st_after.st_ino) != identity or st_after.st_size != size:
        raise CatalogRefreshSealError(f"file changed during read: {display}")
    return b"".join(chunks)


def _read_leaf(dir_fd: int, leaf: str, cap: int, display: str) -> bytes:
    """Open the leaf relative to the HELD parent and read it with bounds.

    O_NONBLOCK guarantees a FIFO leaf cannot block the caller; type and
    size are verified with fstat on the opened descriptor BEFORE any read;
    the cap is enforced before allocation. The caller's ``dir_fd`` is NOT
    closed here.
    """
    _validate_flat_name(leaf)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except OSError as exc:
        raise _anchor_error(exc) from exc
    try:
        try:
            return _bounded_read_regular(fd, cap, display)
        except OSError as exc:
            raise CatalogRefreshSealError(f"cannot safely read: {display}") from exc
    finally:
        os.close(fd)


def anchored_read_fd(dir_fd: int, name: str, cap: int) -> bytes:
    """Read ``name`` (run-relative) from a HELD run-directory descriptor.

    Intermediate components are opened no-follow via the held descriptors
    and closed again; the caller's ``dir_fd`` is NEVER closed by this
    function (explicit ownership), so a held run descriptor remains usable
    for every subsequent file. Test seam for capture-once accounting.
    """
    _validate_relative_name(name)
    parts = name.split("/")
    cur = dir_fd
    opened_here: int | None = None
    try:
        for part in parts[:-1]:
            child = _open_component(
                cur, part, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
            )
            if opened_here is not None:
                os.close(opened_here)
            opened_here = child
            cur = child
        return _read_leaf(cur, parts[-1], cap, display=name)
    finally:
        if opened_here is not None:
            os.close(opened_here)


def anchored_read(parent: Path, name: str, cap: int) -> bytes:
    """Anchored bounded read of ``parent/name`` (run-relative name).

    Opens (and owns) the parent descriptor itself; closes it on exit.
    """
    _validate_relative_name(name)
    fd, _chain = _open_anchored(parent)
    try:
        return anchored_read_fd(fd, name, cap)
    finally:
        os.close(fd)


def read_user_file(path: Path, cap: int) -> bytes:
    """Anchored bounded read of a user-supplied input path (bundle/baseline).

    The size cap is enforced from fstat on the opened descriptor BEFORE any
    content is allocated or read, so an oversize sparse file is refused
    without a single byte being read. Symlinked leaves/ancestors are
    refused; a FIFO leaf is refused as non-regular without blocking.
    """
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    leaf = absolute.name
    if not leaf or leaf in (".", ".."):
        raise CatalogRefreshSealError("unsafe input path")
    fd, _chain = _open_anchored(absolute.parent)
    try:
        return _read_leaf(fd, leaf, cap, display=str(path))
    finally:
        os.close(fd)


# --- seal key: one secure loader, anchored creation --------------------------


def _load_seal_key_fd(parent_fd: int, leaf: str, display: Path) -> bytes:
    """Validate and read an EXISTING seal key through a HELD parent
    descriptor (descriptor lineage: no path reopen).

    Validates on the OPENED descriptor: regular file, EXACT mode 0600
    (0400/0700/0644 are all refused), current-runner ownership, exactly 64
    lowercase ASCII hex bytes, complete file (EOF probed, post-read
    identity re-checked). Never creates, repairs, chmods, rotates, or
    re-signs anything. No key bytes or raw input ever appear in the error.
    """
    try:
        key_fd = os.open(
            leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
        )
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise CatalogRefreshSealError(
                f"seal key file does not exist: {display} (verify never creates keys)"
            ) from exc
        raise CatalogRefreshSealError("seal key cannot be safely opened") from exc
    try:
        st = os.fstat(key_fd)
        if not stat.S_ISREG(st.st_mode):
            raise CatalogRefreshSealError("seal key must be a regular file")
        if stat.S_IMODE(st.st_mode) != 0o600:
            raise CatalogRefreshSealError("seal key must be mode 0600")
        if st.st_uid != os.geteuid():
            raise CatalogRefreshSealError("seal key must be owned by the current user")
        if st.st_size != KEY_FILE_BYTES:
            raise CatalogRefreshSealError("seal key has the wrong length")
        try:
            data = _bounded_read_regular(key_fd, KEY_FILE_BYTES, "seal key")
        except OSError as exc:
            raise CatalogRefreshSealError("seal key cannot be safely read") from exc
    finally:
        os.close(key_fd)
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CatalogRefreshSealError("seal key is not ASCII hex") from exc
    if not _HEX64.fullmatch(text):
        raise CatalogRefreshSealError("seal key is not 64 lowercase hex characters")
    return bytes.fromhex(text)


def load_seal_key_bytes(path: Path) -> bytes:
    """Load an EXISTING seal key through the anchored no-follow boundary.

    The parent directory is opened once with a descriptor-anchored walk;
    the key is then validated on the opened descriptor. Verify-style use:
    never creates anything; a missing key stays missing.
    """
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    leaf = absolute.name
    if not leaf or leaf in (".", ".."):
        raise CatalogRefreshSealError("seal key path is unsafe")
    try:
        parent_fd, _chain = _open_anchored(absolute.parent)
    except CatalogRefreshSealError as exc:
        raise CatalogRefreshSealError("seal key path is not safely accessible") from exc
    try:
        return _load_seal_key_fd(parent_fd, leaf, Path(path).expanduser())
    finally:
        os.close(parent_fd)


def ensure_seal_key(path: Path, key_parent_fd: int | None = None) -> bytes:
    """Create (0600, race-safe, anchored) or load the runner-owned seal key.

    The parent chain is created/verified by the SAME anchored walk (absent
    components are mkdir(2)'d privately 0700 through held descriptors — no
    unanchored mkdir). The held parent descriptor is kept for the entire
    operation: probe, private temp, publish, winner load and cleanup all
    happen relative to it, so a swapped path cannot redirect any of them.

    When the caller passes a ``key_parent_fd`` it retains from an earlier
    checked lifecycle handle (descriptor lineage — no path reopen), the
    function operates through that held descriptor and does NOT close it.
    When it is omitted, the parent is opened (and created if missing)
    here and closed on exit. The mutation namespace (the key parent) is
    verified operator-owned and not peer-writable in both cases.

    The winner completes a private 0600 temp entry (fsync) in the verified
    parent and publishes it with an atomic NEW-ONLY rename; a concurrent
    initializer that loses the race validates and reuses the complete
    winner (descriptor lineage — no path reopen) or fails. An invalid
    existing key is never silently replaced.
    """
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    leaf = absolute.name
    if not leaf or leaf in (".", ".."):
        raise CatalogRefreshSealError("seal key path is unsafe")
    display = Path(path).expanduser()
    if key_parent_fd is None:
        parent_fd, _chain = open_anchored_directory(absolute.parent, create_missing=True)
        try:
            _assert_mutation_namespace(parent_fd, "seal key parent directory")
        except BaseException:
            os.close(parent_fd)
            raise
    else:
        parent_fd = key_parent_fd
        _assert_mutation_namespace(parent_fd, "seal key parent directory")
    try:
        try:
            probe = os.open(
                leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
            )
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise CatalogRefreshSealError("seal key cannot be safely opened") from exc
        else:
            os.close(probe)
            return _load_seal_key_fd(parent_fd, leaf, display)
        key = os.urandom(KEY_BYTES)
        hex_bytes = key.hex().encode("ascii")
        tmp_name = f".seal-key-{os.getpid()}-{secrets.token_hex(8)}"
        try:
            tmp_fd = os.open(
                tmp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise CatalogRefreshSealError("seal key cannot be created") from exc
        try:
            view = memoryview(hex_bytes)
            while view:
                written = os.write(tmp_fd, view)
                view = view[written:]
            os.fchmod(tmp_fd, 0o600)  # exact mode regardless of umask
            os.fsync(tmp_fd)
            try:
                _renameat2_noreplace(parent_fd, tmp_name, parent_fd, leaf)
            except PublicationConflictError:
                # A peer published first; the publish is atomic, so the
                # winner's bytes are complete. Validate and reuse them
                # through the SAME held parent descriptor.
                os.unlink(tmp_name, dir_fd=parent_fd)
                return _load_seal_key_fd(parent_fd, leaf, display)
            os.fsync(parent_fd)
            return key
        except BaseException:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
        finally:
            os.close(tmp_fd)
    finally:
        if key_parent_fd is None:
            os.close(parent_fd)


# --- private staging and atomic NEW-ONLY publication --------------------------


def mkdir_private_child(parent_fd: int, prefix: str) -> tuple[str, int, tuple[int, int]]:
    """Create a private 0700 child directory inside a HELD parent.

    ``os.mkdir`` via ``dir_fd`` is mkdir(2): atomic and never replaces an
    existing entry. Returns ``(name, dir_fd, (st_dev, st_ino))``; the
    caller owns ``dir_fd`` and must hold it for the staging lifetime. The
    identity is the anchor for later identity-checked cleanup.
    """
    _assert_mutation_namespace(parent_fd, "private staging parent directory")
    name = f"{prefix}{os.getpid()}-{secrets.token_hex(8)}"
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except OSError as exc:
        raise CatalogRefreshSealError("cannot create private staging directory") from exc
    try:
        dir_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent_fd)
    except OSError as exc:
        try:
            os.rmdir(name, dir_fd=parent_fd)
        except OSError:
            pass
        raise CatalogRefreshSealError("cannot open private staging directory") from exc
    st = os.fstat(dir_fd)
    return name, dir_fd, (st.st_dev, st.st_ino)


def write_staged_file(dir_fd: int, name: str, data: bytes, mode: int) -> None:
    """Write one file inside a PRIVATE staged directory via the held
    descriptor (complete write + fchmod + fsync). Replacement is
    acceptable here only because the directory is private (0700,
    mkdir(2)-created by us in a verified parent); final published names
    use the NEW-ONLY publication primitives instead."""
    _validate_flat_name(name)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode, dir_fd=dir_fd)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fchmod(fd, mode)  # exact mode regardless of umask
        os.fsync(fd)
    finally:
        os.close(fd)


def cleanup_staged_directory(
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int],
    created_names: Sequence[str],
) -> None:
    """Best-effort removal of OUR private staging directory, anchored.

    The name is re-opened through the HELD parent descriptor (no-follow);
    if the entry no longer resolves to the exact ``(st_dev, st_ino)``
    captured at creation — i.e. it was replaced by ANY other object,
    symlink or regular directory alike — cleanup is refused and the
    foreign entry is left untouched. The parent namespace must also still
    be operator-owned and not peer-writable, or cleanup is refused
    (silently — this is the failure path and must not mask the original
    error). Otherwise only the tracked entries we created are unlinked
    (via the identity-checked descriptor), then the directory itself is
    rmdir'ed through the held parent.
    """
    parent_st = os.fstat(parent_fd)
    if parent_st.st_uid != os.geteuid() or parent_st.st_mode & 0o022:
        # Unsafe (peer-writable or foreign-owned) mutation namespace:
        # refuse cleanup silently rather than risk touching foreign entries.
        return
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent_fd)
    except OSError:
        return
    try:
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != expected_identity:
            return  # foreign entry at our staging name: refuse cleanup
        for child_name in created_names:
            try:
                os.unlink(child_name, dir_fd=fd)
            except OSError:
                pass
    finally:
        os.close(fd)
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        pass


def publish_new_only_directory(
    parent_fd: int,
    staging_name: str,
    destination_name: str,
    staging_identity: tuple[int, int],
) -> None:
    """Atomically publish a private staged directory as a NEW destination,
    anchored to the HELD parent descriptor (the same one that created the
    staging entry — no path reopen between create and publish).

    Before the atomic rename, the staging NAME is re-opened through the
    held parent and its ``(st_dev, st_ino)`` is compared with the identity
    captured at creation: a directory that was swapped in at the staging
    name (rename-based replacement or symlink) is never published.
    Existing empty/nonempty directories, files, and symlinks at the
    destination are left byte/inode-identical; a concurrently created
    destination cannot be clobbered. Raises PublicationConflictError when
    the destination already exists.

    Residual (documented): the check and the rename are not a single
    syscall; a same-uid peer that deletes AND recreates the staging name
    within that window with a reused inode could still be published. The
    captured-bytes authentication of the sealed content is the final
    authority: verification re-authenticates exact bytes and would not
    accept foreign content as a valid run.
    """
    _validate_flat_name(staging_name)
    _validate_flat_name(destination_name)
    _assert_mutation_namespace(parent_fd, "publication parent directory")
    try:
        check_fd = os.open(
            staging_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent_fd
        )
    except OSError as exc:
        raise CatalogRefreshSealError("staging directory cannot be safely opened") from exc
    try:
        st = os.fstat(check_fd)
        if (st.st_dev, st.st_ino) != staging_identity:
            raise CatalogRefreshSealError(
                "staging directory was replaced; refusing to publish"
            )
    finally:
        os.close(check_fd)
    _renameat2_noreplace(parent_fd, staging_name, parent_fd, destination_name)
    os.fsync(parent_fd)


def publish_new_only_file(
    parent: Path, destination_name: str, data: bytes, mode: int
) -> None:
    """Atomically publish a file as a NEW destination (one-shot).

    The parent is verified once by the anchored walk; the temp is created
    O_EXCL inside that verified parent, completed and fsynced, then
    published with renameat2(RENAME_NOREPLACE) through the same descriptor.
    Pre-existing targets of any type remain untouched; a conflict removes
    our own temp and raises PublicationConflictError.
    """
    _validate_flat_name(destination_name)
    parent_fd, _chain = _open_anchored(parent)
    tmp_name = f".{destination_name}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    try:
        _assert_mutation_namespace(parent_fd, "output parent directory")
        tmp_fd = os.open(
            tmp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=parent_fd,
        )
        try:
            view = memoryview(data)
            while view:
                written = os.write(tmp_fd, view)
                view = view[written:]
            os.fchmod(tmp_fd, mode)
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)
        try:
            _renameat2_noreplace(parent_fd, tmp_name, parent_fd, destination_name)
        except PublicationConflictError:
            os.unlink(tmp_name, dir_fd=parent_fd)
            raise
        os.fsync(parent_fd)
    except BaseException:
        try:
            os.unlink(tmp_name, dir_fd=parent_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(parent_fd)
