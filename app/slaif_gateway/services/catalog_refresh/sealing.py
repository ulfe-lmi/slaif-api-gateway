"""Local HMAC-SHA256 sealing and verification for run directories.

Trust scope: this seal proves internal consistency of a run (bundle,
baseline, artifacts, validation, report, identities) against a
runner-owned key. It is local trust, not protection from the administrator
who controls the key; the key is never stored in the bundle, research
directory, report, logs, or exceptions, and future researchers must never
receive it.

Filesystem trust rules (180-g): every path this module touches goes through
the shared descriptor-anchored boundary in ``filesystem`` — held directory
descriptors with no-follow opens at every component (ancestors included),
regular-file type/size verified on the opened descriptor BEFORE reading,
bounded reads with EOF proof and post-read identity re-check, O_NONBLOCK
leaves, and atomic NEW-ONLY publication. A parent or ancestor replaced by
a symlink after verification cannot redirect a later operation.

Capture-once: each run content file is read exactly once per
seal/verification pass; the SAME captured bytes feed the manifest/receipt
digests, the canonical bundle identity, the run identity, semantic
recomputation and the artifact/report correspondence. Nothing is reopened
by path after checking; verification holds ONE anchored descriptor for the
run directory across every file it reads, executes no SQL, and re-signs
nothing.

Signing as well as verification is bounds-checked BEFORE content is read:
the manifest's declared set, counts and sizes are reconciled against the
exact expected content-file set, the per-file bound (8 MiB for the bundle
itself, 32 MiB for other content files) and the aggregate bound including
manifest/receipt overhead; the per-file read cap is the DECLARED size with
the remaining aggregate budget, so an entry that claims 1 byte never
allocates 32 MiB, and the bundle's 8 MiB cap applies at its file read.

Manifest/receipt contracts: strict JSON (duplicate keys, non-finite values,
malformed and deeply nested input fail closed without tracebacks or raw
input leakage), the EXACT expected content-file set, and per-file digest
reconciliation against captured bytes before the signer will sign. The
first-install baseline must be the exact canonical empty marker bytes,
not merely any object carrying the expected schema_version value.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slaif_gateway.services.catalog_refresh import filesystem as fs
from slaif_gateway.services.catalog_refresh.bundle import (
    MAX_BUNDLE_BYTES,
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
from slaif_gateway.services.catalog_refresh.validation import (
    sql_capture_for_mode,
    validate_bundle,
    validation_json_bytes,
)

# Re-exported for existing importers (canonical definitions live in
# filesystem).
KEY_BYTES = fs.KEY_BYTES
MAX_FILE_BYTES = fs.MAX_FILE_BYTES
MAX_TOTAL_BYTES = fs.MAX_TOTAL_BYTES
MAX_FILES = fs.MAX_FILES
MAX_DEPTH = fs.MAX_DEPTH
ensure_seal_key = fs.ensure_seal_key

RECEIPT_NAME = "receipt.json"
MANIFEST_NAME = "manifest.json"
BUNDLE_NAME = "catalog-refresh.json"
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
_EXPECTED_CONTENT = frozenset(CONTENT_FILES)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    valid: bool
    checks: dict[str, str]
    state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "checks": dict(sorted(self.checks.items())), "state": self.state}


def _parse_manifest(raw: bytes) -> list[dict[str, Any]]:
    manifest = fs.strict_json_bytes(raw, "manifest.json")
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
        if not isinstance(digest_value, str) or not fs._HEX64.fullmatch(digest_value):
            raise CatalogRefreshSealError("manifest.json sha256 must be 64 lowercase hex")
        if isinstance(size_value, bool) or not isinstance(size_value, int) or size_value < 0:
            raise CatalogRefreshSealError("manifest.json bytes must be a non-negative integer")
        if path_value in seen_paths:
            raise CatalogRefreshSealError("manifest.json duplicate path")
        seen_paths.add(path_value)
    return entries


def _parse_receipt(raw: bytes) -> dict[str, Any]:
    receipt = fs.strict_json_bytes(raw, "receipt.json")
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_KEYS:
        raise CatalogRefreshSealError("receipt.json has an unexpected shape")
    if receipt.get("schema_version") != "1":
        raise CatalogRefreshSealError("receipt.json schema_version must be '1'")
    files = receipt.get("files")
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and fs._HEX64.fullmatch(v) for k, v in files.items()
    ):
        raise CatalogRefreshSealError("receipt.json files must map names to 64-hex digests")
    for field_name in ("manifest_sha256", "semantic_bundle_sha256", "hmac_sha256"):
        value = receipt.get(field_name)
        if not isinstance(value, str) or not fs._HEX64.fullmatch(value):
            raise CatalogRefreshSealError(f"receipt.json {field_name} must be 64 lowercase hex")
    return receipt


def _file_cap(name: str, declared_bytes: int, remaining: int) -> int:
    """Per-file read cap: the DECLARED size (never more than the file
    claims), bounded by the file-specific acceptance cap (the bundle's own
    8 MiB applies at its file read) and the remaining aggregate budget.
    """
    per_file = MAX_BUNDLE_BYTES if name == BUNDLE_NAME else MAX_FILE_BYTES
    return max(0, min(declared_bytes, per_file, remaining))


def _validate_declared_entries(
    entries: list[dict[str, Any]], manifest_len: int, receipt_len_or_bound: int
) -> None:
    """Reconcile the DECLARED manifest against the exact expected content
    set and all bounds BEFORE any content is read (signing and
    verification both enforce this)."""
    paths = [entry["path"] for entry in entries]
    if set(paths) != _EXPECTED_CONTENT or len(paths) != len(_EXPECTED_CONTENT):
        raise CatalogRefreshSealError(
            "manifest.json file set must be exactly the expected content files"
        )
    if len(entries) > MAX_FILES:
        raise CatalogRefreshSealError("manifest.json declares too many files")
    for entry in entries:
        per_file = MAX_BUNDLE_BYTES if entry["path"] == BUNDLE_NAME else MAX_FILE_BYTES
        if entry["bytes"] > per_file:
            # Constant message: the (untrusted) manifest path is never echoed.
            raise CatalogRefreshSealError("manifest.json declares a file beyond the size bound")
    declared_total = sum(entry["bytes"] for entry in entries)
    if manifest_len + receipt_len_or_bound + declared_total > MAX_TOTAL_BYTES:
        raise CatalogRefreshSealError(
            "manifest declares bounds beyond the aggregate acceptance limit"
        )


def seal_run(run_dir_fd: int, key: bytes) -> bytes:
    """Compute digests, authenticate, and write the receipt.

    The caller HOLDS the private staged run-directory descriptor for the
    whole operation (descriptor lineage: no path reopen between staging
    and seal). Capture-once: each content file and the manifest are read
    exactly once through the anchored boundary; the captured bytes are the
    single input to the content digests, the manifest digest, the
    canonical bundle identity and the HMAC payload.

    Before any content is read, the DECLARED manifest is reconciled
    (exact content set, per-file and aggregate bounds including
    manifest/receipt overhead). During capture, the per-file read cap is
    the declared size with the remaining aggregate budget (the bundle's
    8 MiB cap included), and after capture every declared digest and size
    is reconciled against the captured bytes: the signer never signs an
    inconsistent manifest/content. The receipt is the final file and is
    written into the (private, pre-publication) run directory via the
    same held descriptor.
    """
    manifest_raw = fs.anchored_read_fd(run_dir_fd, MANIFEST_NAME, fs.MAX_AUX_BYTES)
    entries = _parse_manifest(manifest_raw)
    # Strict pre-read reconciliation (G4): fail closed BEFORE capturing
    # any content if the declared manifest is inconsistent or over-bounds.
    _validate_declared_entries(entries, len(manifest_raw), fs.RECEIPT_MAX_BYTES)
    captured: dict[str, bytes] = {}
    remaining = MAX_TOTAL_BYTES - len(manifest_raw) - fs.RECEIPT_MAX_BYTES
    for entry in sorted(entries, key=lambda e: e["path"]):
        name = entry["path"]
        data = fs.anchored_read_fd(run_dir_fd, name, _file_cap(name, entry["bytes"], remaining))
        if len(data) != entry["bytes"]:
            raise CatalogRefreshSealError(f"manifest size mismatch: {name}")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise CatalogRefreshSealError(f"manifest digest mismatch: {name}")
        remaining -= len(data)
        captured[name] = data
    bundle_raw = captured[BUNDLE_NAME]
    bundle = load_bundle(bundle_raw)  # strict schema check of the captured bytes
    semantic = hashlib.sha256(canonical_bundle_bytes(bundle)).hexdigest()
    run_id, generated_at = _bundle_identity_fields(bundle_raw)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    payload = _hmac_payload(run_id, generated_at, manifest_sha256, content_hashes(captured), semantic)
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    receipt = {
        "schema_version": "1",
        "files": dict(sorted(content_hashes(captured).items())),
        "manifest_sha256": manifest_sha256,
        "semantic_bundle_sha256": semantic,
        "hmac_sha256": digest,
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8")
    fs.write_staged_file(run_dir_fd, RECEIPT_NAME, receipt_bytes, 0o644)
    os.fsync(run_dir_fd)
    return receipt_bytes


def _bundle_identity_fields(bundle_raw: bytes) -> tuple[str, str]:
    """run_id / generated_at from the CAPTURED bundle bytes (one strict
    parse; the same bytes already passed load_bundle in this pass)."""
    identity = fs.strict_json_bytes(bundle_raw, "bundle")
    if not isinstance(identity, dict):
        raise CatalogRefreshSealError("bundle must be a JSON object")
    return str(identity["run_id"]), str(identity["generated_at"])


def _hmac_payload(run_id: str, generated_at: str, manifest_sha256: str, files: dict[str, str], semantic: str) -> bytes:
    entries = "|".join(f"{name}:{digest}" for name, digest in sorted(files.items()))
    return (
        f"slaif-catalog-refresh-seal/v1|run={run_id}|generated_at={generated_at}"
        f"|manifest={manifest_sha256}|files={entries}|semantic={semantic}"
    ).encode("utf-8")


def verify_run(run_dir: Path, key: bytes) -> VerifyResult:
    """Verify seal, digests, and semantic/renderer correspondence.

    Read-only: never initializes a key, never writes, never re-signs, and
    executes no SQL. The run directory is anchored ONCE and the held
    descriptor serves every read (receipt, manifest, all content files);
    the manifest's declared set, counts and sizes are checked BEFORE
    content is read; each per-file read cap is the declared size with the
    file-specific acceptance cap; the same captured bytes feed digests,
    HMAC, semantic recomputation and artifact/report correspondence. Any
    manipulation of proposal+report+manifest together fails without the
    external key.
    """
    run_dir = Path(run_dir)
    try:
        run_fd, _chain = fs._open_anchored(run_dir)
    except CatalogRefreshSealError:
        return VerifyResult(False, {"run_dir": "missing"})
    try:
        return _verify_run_fd(run_fd, key)
    finally:
        os.close(run_fd)


def _verify_run_fd(run_fd: int, key: bytes) -> VerifyResult:
    try:
        receipt_raw = fs.anchored_read_fd(run_fd, RECEIPT_NAME, fs.MAX_AUX_BYTES)
        manifest_raw = fs.anchored_read_fd(run_fd, MANIFEST_NAME, fs.MAX_AUX_BYTES)
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

    # Exact expected content set, checked against the DECLARED entries
    # before any content file is read.
    if set(receipt["files"]) != _EXPECTED_CONTENT:
        return VerifyResult(False, {"receipt": "file set must be exactly the expected content files"})
    try:
        _validate_declared_entries(entries, len(manifest_raw), len(receipt_raw))
    except CatalogRefreshSealError:
        return VerifyResult(False, {"bounds": "manifest declares bounds beyond the acceptance limits"})

    content: dict[str, bytes] = {}
    remaining = MAX_TOTAL_BYTES - len(manifest_raw) - len(receipt_raw)
    for entry in sorted(entries, key=lambda e: e["path"]):
        name = entry["path"]
        cap = _file_cap(name, entry["bytes"], remaining)
        try:
            data = fs.anchored_read_fd(run_fd, name, cap)
        except CatalogRefreshSealError as exc:
            return VerifyResult(False, {"safe_paths": str(exc)})
        remaining -= len(data)
        if len(data) != entry["bytes"]:
            return VerifyResult(False, {"size": f"manifest bytes mismatch {name}"})
        content[name] = data

    # 1) per-file digests
    for name, data in content.items():
        digest = hashlib.sha256(data).hexdigest()
        manifest_digest = next((e["sha256"] for e in entries if e["path"] == name), None)
        receipt_digest = receipt["files"].get(name)
        if digest != manifest_digest or digest != receipt_digest:
            checks = {"digest": f"mismatch {name}"}
            return VerifyResult(False, checks)
    checks: dict[str, str] = {"digests": "ok"}

    # 2) HMAC (requires the external key)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha256 != receipt["manifest_sha256"]:
        return VerifyResult(False, {"manifest": "digest mismatch"})
    bundle_raw = content[BUNDLE_NAME]
    try:
        bundle = load_bundle(bundle_raw)
        semantic = hashlib.sha256(canonical_bundle_bytes(bundle)).hexdigest()
        run_id, generated_at = _bundle_identity_fields(bundle_raw)
    except CatalogRefreshBlockedError as exc:
        # Safe code-only surface (no raw input echo).
        return VerifyResult(False, {"bundle": exc.code})
    except (CatalogRefreshSealError, KeyError, TypeError) as exc:
        return VerifyResult(False, {"bundle": str(exc)[:200]})
    if semantic != receipt["semantic_bundle_sha256"]:
        return VerifyResult(False, {"semantic_bundle": "canonical bytes differ"})
    payload = _hmac_payload(run_id, generated_at, manifest_sha256, content_hashes(content), semantic)
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
        # The replay recomputes with the ORIGINAL run's captured bytes (the
        # sealed baseline bytes are what that run captured); this
        # verification itself executes no SQL and says so in its checks.
        policy = policy_from_document(bundle.policy)
        report, artifacts = validate_bundle(
            bundle, baseline, policy, sql_capture=sql_capture_for_mode(bundle.baseline.mode)
        )
    except (CatalogRefreshBlockedError, CatalogRefreshSealError, ValueError) as exc:
        return VerifyResult(False, {"recompute": str(exc)[:200]})
    checks["sql_evidence"] = "replayed from sealed bytes (no SQL executed during verification)"

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
        # The first-install baseline must be the EXACT canonical empty
        # marker document (bytes), not merely any object carrying the
        # expected schema_version value.
        if content["catalog-baseline.json"] != first_install_baseline_bytes():
            checks["first_install"] = "first-install baseline must be the exact canonical empty marker document"
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
    """Atomically publish the explicitly empty first-install baseline
    document as a NEW file (no-replace; a pre-existing target is untouched)."""
    data = first_install_baseline_bytes()
    out_path = Path(out_path)
    fs.publish_new_only_file(out_path.parent, out_path.name, data, 0o644)
    return data
