"""Local HMAC-SHA256 sealing and verification for run directories.

Trust scope: this seal proves internal consistency of a run (bundle,
baseline, artifacts, validation, report, identities) against a
runner-owned key. It is local trust, not protection from the administrator
who controls the key; the key is never stored in the bundle, research
directory, report, logs, or exceptions, and future researchers must never
receive it.

Filesystem trust rules (180-b):
- Key creation is race-safe: the winner completes a private temp file and
  publishes it with an atomic ``os.link``, so the final path only ever holds
  a complete key; a concurrent initializer either reuses that verified key
  or fails. A final key is never silently replaced.
- Every path component is checked for symlinks *before* resolution; leaf,
  parent, and dangling symlinks are all refused.
- Content is read through an ``O_NOFOLLOW`` descriptor whose size is bounded
  by an ``fstat`` taken on the open descriptor — there is no lexical check
  followed by an unchecked ``read_bytes``.
- Manifests and receipts are parsed with duplicate-key rejection and exact
  shape checks; malformed shapes fail closed without tracebacks or raw
  input leaks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slaif_gateway.services.catalog_refresh.bundle import (
    canonical_bundle_bytes,
    load_bundle,
)
from slaif_gateway.services.catalog_refresh.baseline import (
    canonical_baseline_content,
    load_baseline,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    CatalogRefreshSealError,
)
from slaif_gateway.services.catalog_refresh.policy import policy_from_document
from slaif_gateway.services.catalog_refresh.rendering import render_report
from slaif_gateway.services.catalog_refresh.validation import validate_bundle, validation_json_bytes

KEY_BYTES = 32
# Aligned with the baseline export bound (MAX_BASELINE_BYTES): a sealed run
# may legitimately carry a 32 MiB catalog-baseline.json, so the per-file
# acceptance bound must not be smaller than that.
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_FILES = 64
MAX_DEPTH = 4
RECEIPT_NAME = "receipt.json"
MANIFEST_NAME = "manifest.json"
CONTENT_FILES = (
    "catalog-refresh.json",
    "catalog-baseline.json",
    "routes-proposal.tsv",
    "pricing-proposal.tsv",
    "fx-proposal.json",
    "validation.json",
    "REVIEW.html",
)

_RECEIPT_KEYS = frozenset({"schema_version", "files", "manifest_sha256", "semantic_bundle_sha256", "hmac_sha256"})
_MANIFEST_ENTRY_KEYS = frozenset({"path", "sha256", "bytes"})
_HEX64 = __import__("re").compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class VerifyResult:
    valid: bool
    checks: dict[str, str]
    state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "checks": dict(sorted(self.checks.items())), "state": self.state}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(token: str) -> Any:
    raise ValueError(f"non-finite JSON value {token!r}")


def _strict_json(raw: bytes, what: str) -> Any:
    """Parse JSON failing closed on duplicate keys, non-finite values, or bad UTF-8."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogRefreshSealError(f"{what} is not valid UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_non_finite)
    except ValueError as exc:
        raise CatalogRefreshSealError(f"{what} is not strictly valid JSON") from exc


def _assert_no_symlink_components(path: Path) -> None:
    """Refuse if any component of the absolute path (incl. an existing leaf) is a symlink."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[len(absolute.anchor):]:
        current = current / part
        if os.path.islink(current):
            raise CatalogRefreshSealError(f"refusing symlink path component: {part}")


def _read_seal_key_bytes(path: Path) -> bytes:
    """Read and validate an existing seal key through an O_NOFOLLOW descriptor."""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise CatalogRefreshSealError("seal key must not be a symlink")
    if not stat.S_ISREG(st.st_mode):
        raise CatalogRefreshSealError("seal key path must be a regular file")
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o077:
        raise CatalogRefreshSealError("existing seal key must be mode 0600")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        data = os.read(fd, KEY_BYTES * 2 + 1)
    finally:
        os.close(fd)
    if len(data) != KEY_BYTES * 2:
        raise CatalogRefreshSealError("seal key has the wrong length")
    try:
        hex_text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CatalogRefreshSealError("seal key is not ASCII hex") from exc
    if not _HEX64.fullmatch(hex_text):
        raise CatalogRefreshSealError("seal key is not 64 lowercase hex characters")
    return bytes.fromhex(hex_text)


def ensure_seal_key(path: Path) -> bytes:
    """Create (0600, race-safe) or load the runner-owned seal key.

    Race-safe publication: the winner writes the complete key to a private
    temp file in the same directory (0600, fsync) and then publishes it with
    an atomic ``os.link``. The final path therefore only ever holds a
    complete key — a concurrent initializer that observes it (via the
    ``FileExistsError`` from the link or a direct read) can never see a
    half-written file. Exactly one initializer wins; every other initializer
    validates the published key (regular file, 0600, 64 lowercase hex, no
    symlinks) and reuses its bytes. An invalid existing key is never
    replaced silently.
    """
    path = Path(path).expanduser().absolute()
    _assert_no_symlink_components(path)
    if os.path.lexists(path):
        return _read_seal_key_bytes(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(KEY_BYTES)
    hex_text = key.hex()
    fd, tmp_name = tempfile.mkstemp(prefix=".seal-key.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(hex_text.encode("ascii"))
            handle.flush()
            os.fchmod(handle.fileno(), 0o600)  # exact mode regardless of umask
            os.fsync(handle.fileno())
        try:
            os.link(tmp_name, path)  # atomic publish; EEXIST iff a peer won
        except FileExistsError:
            # A concurrent initializer published first; reuse its verified
            # key (the publish is atomic, so the bytes are complete).
            return _read_seal_key_bytes(path)
        os.unlink(tmp_name)  # our private temp copy; the key lives at `path`
    except BaseException:
        # Best-effort removal of our own temp file; the original exception is
        # what the caller sees.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return key


def _safe_read(run_dir: Path, name: str, cap: int) -> bytes:
    """Strict bounded read of ``run_dir/name``.

    Rejects absolute/duplicate/traversal names, any symlink component (leaf
    or parent, checked before resolution), special files, and files above
    the size cap. The bytes are read from an ``O_NOFOLLOW`` descriptor whose
    size was fixed by ``fstat`` on that same descriptor.
    """
    if not name or name.startswith("/") or "\\" in name:
        raise CatalogRefreshSealError(f"unsafe run path {name!r}")
    parts = name.split("/")
    if any(part in ("", "..") for part in parts):
        raise CatalogRefreshSealError(f"unsafe run path {name!r}")
    if len(parts) > MAX_DEPTH:
        raise CatalogRefreshSealError(f"path depth exceeds bound: {name}")
    if os.path.islink(run_dir):
        raise CatalogRefreshSealError("run directory must not be a symlink")
    current = run_dir
    for part in parts:
        current = current / part
        if os.path.islink(current):
            raise CatalogRefreshSealError(f"refusing symlink component: {name}")
    target = run_dir / name
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise CatalogRefreshSealError(f"cannot safely open run file: {name}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise CatalogRefreshSealError(f"not a regular file: {name}")
        if st.st_size > cap:
            raise CatalogRefreshSealError(f"file exceeds size bound: {name}")
        chunks: list[bytes] = []
        remaining = st.st_size
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                raise CatalogRefreshSealError(f"short read on run file: {name}")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    except CatalogRefreshSealError:
        raise
    except OSError as exc:
        raise CatalogRefreshSealError(f"cannot safely read run file: {name}") from exc
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Best-effort cleanup of our own temp file; a missing temp file is
        # fine (already renamed/unlinked), any other error is masked by the
        # original exception that is re-raised below.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _hmac_payload(run_id: str, generated_at: str, manifest_sha256: str, files: dict[str, str], semantic: str) -> bytes:
    entries = "|".join(f"{name}:{digest}" for name, digest in sorted(files.items()))
    return (
        f"slaif-catalog-refresh-seal/v1|run={run_id}|generated_at={generated_at}"
        f"|manifest={manifest_sha256}|files={entries}|semantic={semantic}"
    ).encode("utf-8")


def _parse_manifest(raw: bytes) -> list[dict[str, Any]]:
    manifest = _strict_json(raw, "manifest.json")
    if not isinstance(manifest, dict):
        raise CatalogRefreshSealError("manifest.json must be a JSON object")
    if set(manifest) != {"schema_version", "files"}:
        raise CatalogRefreshSealError("manifest.json has an unexpected shape")
    if manifest.get("schema_version") != "1":
        raise CatalogRefreshSealError("manifest.json schema_version must be '1'")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise CatalogRefreshSealError("manifest.json files must be a list")
    seen_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _MANIFEST_ENTRY_KEYS:
            raise CatalogRefreshSealError("manifest.json entry has an unexpected shape")
        path_value = entry.get("path")
        digest_value = entry.get("sha256")
        size_value = entry.get("bytes")
        if not isinstance(path_value, str) or not path_value:
            raise CatalogRefreshSealError("manifest.json path must be a non-empty string")
        if not isinstance(digest_value, str) or not _HEX64.fullmatch(digest_value):
            raise CatalogRefreshSealError("manifest.json sha256 must be 64 lowercase hex")
        if isinstance(size_value, bool) or not isinstance(size_value, int) or size_value < 0:
            raise CatalogRefreshSealError("manifest.json bytes must be a non-negative integer")
        if path_value in seen_paths:
            raise CatalogRefreshSealError(f"manifest.json duplicate path {path_value!r}")
        seen_paths.add(path_value)
    return entries


def _parse_receipt(raw: bytes) -> dict[str, Any]:
    receipt = _strict_json(raw, "receipt.json")
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_KEYS:
        raise CatalogRefreshSealError("receipt.json has an unexpected shape")
    if receipt.get("schema_version") != "1":
        raise CatalogRefreshSealError("receipt.json schema_version must be '1'")
    files = receipt.get("files")
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and _HEX64.fullmatch(v) for k, v in files.items()
    ):
        raise CatalogRefreshSealError("receipt.json files must map names to 64-hex digests")
    for field_name in ("manifest_sha256", "semantic_bundle_sha256", "hmac_sha256"):
        value = receipt.get(field_name)
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            raise CatalogRefreshSealError(f"receipt.json {field_name} must be 64 lowercase hex")
    return receipt


def seal_run(run_dir: Path, key: bytes) -> bytes:
    """Compute digests, authenticate, and write the receipt atomically."""
    run_dir = Path(run_dir)
    files: dict[str, str] = {}
    for name in CONTENT_FILES:
        data = _safe_read(run_dir, name, MAX_FILE_BYTES)
        files[name] = hashlib.sha256(data).hexdigest()
    manifest_bytes = _safe_read(run_dir, MANIFEST_NAME, MAX_FILE_BYTES)
    _parse_manifest(manifest_bytes)  # fail closed before signing
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    bundle_data = _safe_read(run_dir, "catalog-refresh.json", MAX_FILE_BYTES)
    semantic = hashlib.sha256(canonical_bundle_bytes(load_bundle(bundle_data))).hexdigest()
    payload = _hmac_payload(
        _run_id_from(bundle_data),
        _generated_at_from(bundle_data),
        manifest_sha256,
        files,
        semantic,
    )
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    receipt = {
        "schema_version": "1",
        "files": dict(sorted(files.items())),
        "manifest_sha256": manifest_sha256,
        "semantic_bundle_sha256": semantic,
        "hmac_sha256": digest,
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8")
    _atomic_write(run_dir / RECEIPT_NAME, receipt_bytes, 0o644)
    return receipt_bytes


def _run_id_from(bundle_raw: bytes) -> str:
    return str(json.loads(bundle_raw)["run_id"])


def _generated_at_from(bundle_raw: bytes) -> str:
    return str(json.loads(bundle_raw)["generated_at"])


def verify_run(run_dir: Path, key: bytes) -> VerifyResult:
    """Verify seal, digests, and semantic/renderer correspondence.

    Reads each file once through the safe bounded reader; never writes; never
    initializes a key; never re-signs. Any manipulation of proposal+report+
    manifest together fails without the external key.
    """
    run_dir = Path(run_dir)
    checks: dict[str, str] = {}
    if os.path.islink(run_dir) or not run_dir.is_dir():
        return VerifyResult(False, {"run_dir": "missing"})
    try:
        receipt_raw = _safe_read(run_dir, RECEIPT_NAME, MAX_FILE_BYTES)
        manifest_raw = _safe_read(run_dir, MANIFEST_NAME, MAX_FILE_BYTES)
    except CatalogRefreshSealError as exc:
        return VerifyResult(False, {"safe_paths": str(exc)})
    try:
        receipt = _parse_receipt(receipt_raw)
        entries = _parse_manifest(manifest_raw)
    except CatalogRefreshSealError as exc:
        return VerifyResult(False, {"parse": str(exc)})
    expected_receipt_raw = (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8")
    if receipt_raw != expected_receipt_raw:
        return VerifyResult(False, {"receipt": "non-canonical receipt encoding"})

    content: dict[str, bytes] = {}
    total = 0
    for entry in entries:
        name = entry["path"]
        try:
            data = _safe_read(run_dir, name, MAX_FILE_BYTES)
        except CatalogRefreshSealError as exc:
            return VerifyResult(False, {"safe_paths": str(exc)})
        if len(data) != entry["bytes"]:
            return VerifyResult(False, {"size": f"manifest bytes mismatch {name}"})
        total += len(data)
        content[name] = data
    if len(content) > MAX_FILES or total > MAX_TOTAL_BYTES:
        return VerifyResult(False, {"bounds": "run exceeds file/size bounds"})
    for name in CONTENT_FILES:
        if name not in content:
            return VerifyResult(False, {"content": f"missing {name}"})

    # 1) per-file digests
    for name, data in content.items():
        digest = hashlib.sha256(data).hexdigest()
        manifest_digest = next((e["sha256"] for e in entries if e["path"] == name), None)
        receipt_digest = receipt["files"].get(name)
        if digest != manifest_digest or digest != receipt_digest:
            checks["digest"] = f"mismatch {name}"
            return VerifyResult(False, checks)
    checks["digests"] = "ok"

    # 2) HMAC (requires the external key)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha256 != receipt["manifest_sha256"]:
        return VerifyResult(False, {"manifest": "digest mismatch"})
    bundle_raw = content["catalog-refresh.json"]
    try:
        bundle = load_bundle(bundle_raw)
        semantic = hashlib.sha256(canonical_bundle_bytes(bundle)).hexdigest()
    except CatalogRefreshBlockedError as exc:
        return VerifyResult(False, {"bundle": exc.code})
    if semantic != receipt["semantic_bundle_sha256"]:
        return VerifyResult(False, {"semantic_bundle": "canonical bytes differ"})
    payload = _hmac_payload(_run_id_from(bundle_raw), _generated_at_from(bundle_raw), manifest_sha256, content_hashes(content), semantic)
    expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt["hmac_sha256"]):
        checks["hmac"] = "authentication failed"
        return VerifyResult(False, checks)
    checks["hmac"] = "ok"

    # 3) semantic/renderer correspondence: recompute validation + report
    try:
        baseline = None
        baseline_raw = content["catalog-baseline.json"]
        if bundle.baseline.mode != "first_install":
            baseline = load_baseline(baseline_raw)
            if baseline.content_sha256 != hashlib.sha256(canonical_baseline_content(baseline)).hexdigest():
                return VerifyResult(False, {"baseline_digest": "mismatch"})
            expected_bundle_digest = bundle.baseline.content_sha256
            if expected_bundle_digest is not None and expected_bundle_digest != baseline.content_sha256:
                return VerifyResult(False, {"baseline_identity": "bundle baseline identity differs from baseline document"})
        policy = policy_from_document(bundle.policy)
        report, artifacts = validate_bundle(bundle, baseline, policy)
    except (CatalogRefreshBlockedError, ValueError) as exc:
        return VerifyResult(False, {"recompute": str(exc)[:200]})

    for name, data in artifacts.items():
        if content.get(name) != data:
            return VerifyResult(False, {"artifacts": f"derived artifact differs: {name}"})
    checks["artifacts"] = "ok"

    expected_validation = validation_json_bytes(report)
    if content.get("validation.json") != expected_validation:
        return VerifyResult(False, {"validation": "validation.json does not match recomputed result"})
    checks["validation"] = "ok"

    expected_report = render_report(bundle, report.to_dict())
    if content.get("REVIEW.html") != expected_report:
        return VerifyResult(False, {"report": "REVIEW.html does not match recomputed render"})
    checks["report"] = "ok"

    state = report.state
    if bundle.baseline.mode == "first_install":
        if json.loads(content["catalog-baseline.json"].decode("utf-8")).get("schema_version") != "first-install":
            checks["first_install"] = "first-install baseline must be the explicit empty marker document"
            return VerifyResult(False, checks, state)
    checks["correspondence"] = "ok"
    return VerifyResult(True, checks, state)


def content_hashes(content: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(content.items())}


def first_install_baseline_bytes() -> bytes:
    """The explicitly empty first-install baseline document (canonical bytes)."""
    payload = {
        "schema_version": "first-install",
        "note": "FIRST INSTALL — NO LOCAL BASELINE. Explicitly empty; no before/after values are invented and no database was read.",
    }
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def write_first_install_baseline(out_path: Path) -> bytes:
    """Atomically write the explicitly empty first-install baseline document."""
    data = first_install_baseline_bytes()
    _atomic_write(out_path, data, 0o644)
    return data
