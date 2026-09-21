"""Local HMAC-SHA256 sealing and verification for run directories.

Trust scope: this seal proves internal consistency of a run (bundle,
baseline, artifacts, validation, report, identities) against a
runner-owned key. It is local trust, not protection from the administrator
who controls the key; the key is never stored in the bundle, research
directory, report, logs, or exceptions, and future researchers must never
receive it.
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
MAX_FILE_BYTES = 16 * 1024 * 1024
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


@dataclass(frozen=True, slots=True)
class VerifyResult:
    valid: bool
    checks: dict[str, str]
    state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "checks": dict(sorted(self.checks.items())), "state": self.state}


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
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


def ensure_seal_key(path: Path) -> bytes:
    """Create (0600, atomic) or load the runner-owned seal key.

    Never overwrites an existing key silently; existing keys must be 0600.
    """
    path = Path(path)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise CatalogRefreshSealError("seal key path must be a regular file")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise CatalogRefreshSealError("existing seal key must be mode 0600")
        key = path.read_bytes()
        if len(key) != KEY_BYTES * 2:
            raise CatalogRefreshSealError("seal key has the wrong length")
        return bytes.fromhex(key.decode("ascii"))
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(KEY_BYTES)
    _atomic_write(path, key.hex().encode("ascii"), 0o600)
    return key


def _hmac_payload(run_id: str, generated_at: str, manifest_sha256: str, files: dict[str, str], semantic: str) -> bytes:
    entries = "|".join(f"{name}:{digest}" for name, digest in sorted(files.items()))
    return (
        f"slaif-catalog-refresh-seal/v1|run={run_id}|generated_at={generated_at}"
        f"|manifest={manifest_sha256}|files={entries}|semantic={semantic}"
    ).encode("utf-8")


def seal_run(run_dir: Path, key: bytes) -> bytes:
    """Compute digests, authenticate, and write the receipt atomically."""
    run_dir = Path(run_dir)
    files: dict[str, str] = {}
    for name in CONTENT_FILES:
        target = run_dir / name
        if not target.is_file():
            raise CatalogRefreshSealError(f"missing content file {name}")
        files[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path = run_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise CatalogRefreshSealError("missing manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    bundle_raw = (run_dir / "catalog-refresh.json").read_bytes()
    semantic = hashlib.sha256(canonical_bundle_bytes(load_bundle(bundle_raw))).hexdigest()
    payload = _hmac_payload(
        _run_id_from(bundle_raw),
        _generated_at_from(bundle_raw),
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


def _safe_file(run_dir: Path, name: str) -> Path:
    """Strict path rules: relative, regular, no symlinks, bounded size/depth."""
    if not name or name.startswith("/") or ".." in name.split("/"):
        raise CatalogRefreshSealError(f"unsafe manifest path {name!r}")
    target = (run_dir / name).resolve()
    if not target.is_relative_to(run_dir.resolve()):
        raise CatalogRefreshSealError(f"path escapes run directory: {name}")
    if target.is_symlink():
        raise CatalogRefreshSealError(f"refusing symlink: {name}")
    if not target.is_file():
        raise CatalogRefreshSealError(f"not a regular file: {name}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise CatalogRefreshSealError(f"file exceeds size bound: {name}")
    depth = len(target.relative_to(run_dir.resolve()).parts)
    if depth > MAX_DEPTH:
        raise CatalogRefreshSealError(f"path depth exceeds bound: {name}")
    return target


def verify_run(run_dir: Path, key: bytes) -> VerifyResult:
    """Verify seal, digests, and semantic/renderer correspondence.

    Reads each file once; never writes; never re-signs. Any manipulation of
    proposal+report+manifest together fails without the external key.
    """
    run_dir = Path(run_dir)
    checks: dict[str, str] = {}
    if not run_dir.is_dir():
        return VerifyResult(False, {"run_dir": "missing"})
    try:
        receipt_target = _safe_file(run_dir, RECEIPT_NAME)
        manifest_target = _safe_file(run_dir, MANIFEST_NAME)
    except CatalogRefreshSealError as exc:
        return VerifyResult(False, {"safe_paths": str(exc)})
    receipt_raw = receipt_target.read_bytes()
    manifest_raw = manifest_target.read_bytes()
    try:
        receipt = json.loads(receipt_raw.decode("utf-8"))
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return VerifyResult(False, {"parse": "receipt or manifest is not valid JSON"})
    expected_receipt_raw = (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8")
    if receipt_raw != expected_receipt_raw:
        return VerifyResult(False, {"receipt": "non-canonical receipt encoding"})

    content: dict[str, bytes] = {}
    total = 0
    for entry in manifest.get("files", []):
        name = entry.get("path", "")
        try:
            target = _safe_file(run_dir, name)
        except CatalogRefreshSealError as exc:
            return VerifyResult(False, {"safe_paths": str(exc)}, )
        data = target.read_bytes()
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
        manifest_digest = next((e.get("sha256") for e in manifest.get("files", []) if e.get("path") == name), None)
        receipt_digest = receipt.get("files", {}).get(name)
        if digest != manifest_digest or digest != receipt_digest:
            checks["digest"] = f"mismatch {name}"
            return VerifyResult(False, checks)
    checks["digests"] = "ok"

    # 2) HMAC (requires the external key)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha256 != receipt.get("manifest_sha256"):
        return VerifyResult(False, {"manifest": "digest mismatch"})
    bundle_raw = content["catalog-refresh.json"]
    try:
        bundle = load_bundle(bundle_raw)
        semantic = hashlib.sha256(canonical_bundle_bytes(bundle)).hexdigest()
    except CatalogRefreshBlockedError as exc:
        return VerifyResult(False, {"bundle": exc.code})
    if semantic != receipt.get("semantic_bundle_sha256"):
        return VerifyResult(False, {"semantic_bundle": "canonical bytes differ"})
    payload = _hmac_payload(_run_id_from(bundle_raw), _generated_at_from(bundle_raw), manifest_sha256, content_hashes(content), semantic)
    expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(receipt.get("hmac_sha256", ""))):
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
