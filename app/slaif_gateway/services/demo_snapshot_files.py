"""Objective 223: bounded private demo FILE-BACKED snapshot (worker-only).

Fourth bounded stage of the human-approved fake-admin demonstration
(after 220/221/222):
capture, typed-sanitize and independently verify the admin-visible
FILE-BACKED data for each fresh private snapshot, on top of the 222
verified DB state (``DB_SANITIZED_UNPUBLISHED``). After a complete
capture + typed sanitization + separate read-only verification the
private manifest advances to ``DB_AND_FILES_VERIFIED_UNPUBLISHED``;
browser binding (224) remains absent and no web role reads anything.

Trust boundaries (enforced):
- worker-only: no HTTP route, admin template or web role can invoke it;
  the demo web process of 224 must later read only the verified
  per-copy display copies;
- source files are READ-ONLY: every configured source is read through
  the descriptor-anchored no-follow boundary of the catalog filesystem
  (held directory descriptors, regular-file type/size verified on the
  opened descriptor before any byte is read, bounded reads with EOF
  proof and post-read identity re-check). The only writes are the
  job's own ``files/`` subtree and the narrow private custody manifest
  state (``manifest.json``);
- catalog custody is a closed set: seven sealed run ``CONTENT_FILES``,
  the bounded job upload artifacts, six proposal artifacts, five
  per-package files. Sealed runs are authenticated with the EXISTING
  operator seal key through the real ``load_verified_capture`` path
  before any display copy is derived. The seal key, the original
  manifest/receipt authority and arbitrary upload bytes NEVER enter a
  demo copy;
- the typed sanitizer projects only the reviewed display fields for
  each file kind; names/paths/hosts/credentials/free text/unreviewed
  JSON are replaced with fixed neutral values; an unknown schema,
  field or type fails the job closed;
- packaged invariant data (Codex presets, the packaged Codex startup
  profile, packaged upstream-LLM defaults) is referenced by a pinned
  per-copy digest, never copied;
- the operator ``PUBLIC_BASE_URL`` is recorded as a presence marker
  only; its value is never copied into any artifact;
- display copies live as FLAT 0600 leaves under the job's ``files/``
  directory (0700) inside the operator-owned 0700 demo custody tree;
  the private manifest records capture times, source hashes and leaf
  identities; raw source paths, DSNs and values never render to
  stdout/stderr/logs/reports;
- the copy is promoted ONLY by the independent read-only verifier,
  which re-reads every leaf through the anchored boundary, rechecks
  digests/identities and re-proves the display policy from the stored
  bytes; a worker success flag is never an assertion.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import decimal
import csv
import io
import os
import re
import stat as stat_module
import time
import uuid as _uuid
from datetime import datetime as _dt
from datetime import timezone as _dt_timezone
import hmac as _hmac
from dataclasses import dataclass
from pathlib import Path

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_snapshot_sanitize as dss
from slaif_gateway.services.demo_snapshot_sanitize import (
    demo_profile_id,
    remap_uuid,
)
from slaif_gateway.services.catalog_refresh import filesystem as catfs
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    CatalogRefreshSealError,
)
from slaif_gateway.services.catalog_refresh.sealing import CONTENT_FILES
from slaif_gateway.services.configuration_inspection import (
    CONFIG_INSPECTION_ALLOWLIST,
)

# ---------------------------------------------------------------------------
# Safe finite failure codes (never echo paths/values)
# ---------------------------------------------------------------------------

CODE_FILES_SOURCE_MISSING = "FILES_SOURCE_MISSING"
CODE_FILES_SOURCE_UNSAFE = "FILES_SOURCE_UNSAFE"
CODE_FILES_SOURCE_UNSUPPORTED = "FILES_SOURCE_UNSUPPORTED"
CODE_FILES_SOURCE_TOO_LARGE = "FILES_SOURCE_TOO_LARGE"
CODE_FILES_SOURCE_CHANGED = "FILES_SOURCE_CHANGED"
CODE_FILES_BUDGET_EXCEEDED = "FILES_BUDGET_EXCEEDED"
CODE_FILES_WRITE_FAILED = "FILES_WRITE_FAILED"
CODE_FILES_VERIFY_FAILED = "FILES_VERIFY_FAILED"
CODE_FILES_CLEANUP_FAILED = "FILES_CLEANUP_FAILED"

FILES_STATE_PENDING = "PENDING"
FILES_STATE_FAILED = "FAILED"
FILES_STATE_VERIFIED = "VERIFIED"

FILES_MANIFEST_NAME = "files_manifest.json"
FILES_DIR_NAME = "files"
_FILES_MANIFEST_MAX_BYTES = 1 * 1024 * 1024
_FILES_MAX_LEAVES = 4096
_LEAF_NAME_RE = re.compile(r"^f[0-9]{4}-[0-9a-f]{12}$")
_JOB_LEAF_RE = re.compile(r"^[0-9a-f]{32}$")
_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.ASCII
)

# ---------------------------------------------------------------------------
# Fixed neutral display substitutes (shipped, reviewed; .invalid names)
# ---------------------------------------------------------------------------

DEMO_SCHEMA_VERSION = "demo-display-1"
DEMO_DB_HOST = "demo-postgres.invalid"
DEMO_DB_NAME = "demo-business"
DEMO_DB_PORT = 5432
DEMO_UPSTREAM_BASE_URL = "https://demo-upstream.invalid/v1"
DEMO_ENV_VAR = "DEMO_UPSTREAM_API_KEY"
DEMO_CODE_REVISION = "demo-revision"
DEMO_NOTES = ""
DEMO_PATH = None

NEUTRAL_MARKDOWN = b"# Demo catalog report\n\nNeutral demo display copy.\n"
NEUTRAL_REVIEW_HTML = (
    b"<!doctype html>\n"
    b"<html lang=\"en\">\n"
    b"<head><meta charset=\"utf-8\"><title>SLAIF demo review</title></head>\n"
    b"<body><h1>SLAIF catalog review</h1>"
    b"<p>Neutral demo display copy.</p></body>\n"
    b"</html>\n"
)

# ---------------------------------------------------------------------------
# Display file kinds (closed vocabulary)
# ---------------------------------------------------------------------------

KIND_REFRESH_BUNDLE = "refresh_bundle"
KIND_BASELINE_DOC = "baseline_document"
KIND_ROUTE_TSV = "route_tsv"
KIND_PRICING_TSV = "pricing_tsv"
KIND_FX_JSON = "fx_json"
KIND_VALIDATION_JSON = "validation_json"
KIND_REVIEW_HTML = "review_html"
KIND_NORMALIZED_JSON = "provider_catalog_normalized"
KIND_SOURCE_MANIFEST = "source_manifest"
KIND_WARNINGS_JSON = "warnings_json"
KIND_PACKAGE_MANIFEST = "package_manifest"
KIND_MARKDOWN = "markdown"
KIND_LLM_PROFILES = "upstream_llm_profiles"
KIND_COMPLETION_CHOICES = "completion_choices"
KIND_BRANDING = "branding"
KIND_JOB_RECORD = "job_record"
# 224-t: the ONE finite worker-observed process-configuration
# projection captured at copy time (the reviewed allowlist values +
# configured/default provenance only).
KIND_PROCESS_CONFIG = "process_configuration"

_ALL_KINDS = frozenset(
    {
        KIND_REFRESH_BUNDLE,
        KIND_BASELINE_DOC,
        KIND_ROUTE_TSV,
        KIND_PRICING_TSV,
        KIND_FX_JSON,
        KIND_VALIDATION_JSON,
        KIND_REVIEW_HTML,
        KIND_NORMALIZED_JSON,
        KIND_SOURCE_MANIFEST,
        KIND_WARNINGS_JSON,
        KIND_PACKAGE_MANIFEST,
        KIND_MARKDOWN,
        KIND_LLM_PROFILES,
        KIND_COMPLETION_CHOICES,
        KIND_BRANDING,
        KIND_JOB_RECORD,
        KIND_PROCESS_CONFIG,
    }
)


# ---------------------------------------------------------------------------
# Worker configuration (feature-local; validated on the worker path only,
# so malformed optional demo settings never affect ordinary startup)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileSnapshotConfig:
    """Explicitly configured, worker-only file-stage inputs and bounds."""

    custody_dir: Path
    catalog_root: Path | None
    catalog_seal_key: Path | None
    branding_dir: Path | None
    completion_profile_dir: Path | None
    upstream_llm_profiles_file: Path | None
    public_base_url_configured: bool
    max_file_bytes: int
    max_total_bytes: int
    max_elapsed_seconds: float


def files_config_from_settings(settings: Settings) -> FileSnapshotConfig:
    """Build the file-stage worker config; fail closed on any gap.

    The file stage is part of the demo snapshot worker, so the FULL 221
    worker configuration must already be valid. The three file bounds are
    validated HERE (feature-local) so an ordinary, demo-disabled gateway
    never fails to start because of an optional demo setting.
    """
    base = ds.config_from_settings(settings)
    _MiB = 1024 * 1024
    max_file_bytes = int(settings.DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES)
    max_total_bytes = int(settings.DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES)
    max_elapsed_seconds = float(settings.DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS)
    if not 1 * _MiB <= max_file_bytes <= 128 * _MiB:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "Demo file worker per-file byte cap is outside its finite bound.",
        )
    if not 64 * _MiB <= max_total_bytes <= 4096 * _MiB:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "Demo file worker total byte cap is outside its finite bound.",
        )
    if max_file_bytes > max_total_bytes:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "Demo file worker per-file byte cap exceeds the total byte cap.",
        )
    if not 10 <= max_elapsed_seconds <= 3600:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "Demo file worker elapsed cap is outside its finite bound.",
        )

    def _optional_path(name: str, value: str) -> Path | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        path = Path(normalized)
        if not path.is_absolute():
            raise ds.DemoSnapshotError(
                ds.CODE_MISCONFIGURED,
                f"Demo file worker {name} must be an absolute path.",
            )
        return path

    return FileSnapshotConfig(
        custody_dir=base.custody_dir,
        catalog_root=_optional_path(
            "CATALOG_REFRESH_ROOT", settings.CATALOG_REFRESH_ROOT or ""
        ),
        catalog_seal_key=_optional_path(
            "CATALOG_REFRESH_SEAL_KEY", settings.CATALOG_REFRESH_SEAL_KEY or ""
        ),
        branding_dir=_optional_path(
            "SLAIF_BRANDING_DIR", settings.SLAIF_BRANDING_DIR or ""
        ),
        completion_profile_dir=_optional_path(
            "COMPLETION_SERVICE_PROFILE_DIR",
            settings.COMPLETION_SERVICE_PROFILE_DIR or "",
        ),
        upstream_llm_profiles_file=_optional_path(
            "UPSTREAM_LLM_PROFILES_FILE",
            settings.UPSTREAM_LLM_PROFILES_FILE or "",
        ),
        public_base_url_configured=bool(
            str(settings.PUBLIC_BASE_URL or "").strip()
        ),
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        max_elapsed_seconds=max_elapsed_seconds,
    )


# ---------------------------------------------------------------------------
# Capture model (streaming: raw bytes are sanitized and discarded before
# the next source file is read; only the sanitized display bytes are
# retained, bounded by the aggregate byte budget)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisplayLeaf:
    """One sanitized display leaf ready for the private ``files/`` tree."""

    leaf: str
    logical_name: str
    kind: str
    data: bytes
    sha256: str
    source: str
    source_ref: str
    captured_at: float
    source_sha256: str
    inode_identity: tuple[int, int] | None = None


@dataclass(slots=True)
class _CaptureBudget:
    deadline: float
    raw_bytes: int
    display_bytes: int
    max_file_bytes: int
    max_total_bytes: int
    files_count: int

    def admit_raw(self, raw_size: int) -> None:
        """Aggregate raw admission BEFORE the artifact is parsed."""
        if raw_size > self.max_file_bytes:
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_TOO_LARGE,
                "A demo file source exceeds the per-file byte bound."
            )
        if self.raw_bytes + raw_size > self.max_total_bytes:
            raise ds.DemoSnapshotError(
                CODE_FILES_BUDGET_EXCEEDED,
                "Demo file capture would exceed the total raw byte bound."
            )
        self.raw_bytes += raw_size

    def check_raw(self, raw_size: int) -> None:
        """Aggregate raw PRE-CHECK (non-mutating) before materializing.

        Used for declared sizes learned from a manifest before the real
        bytes are read; ``admit_raw`` is the single mutating admission.
        """
        if raw_size > self.max_file_bytes:
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_TOO_LARGE,
                "A demo file source exceeds the per-file byte bound."
            )
        if self.raw_bytes + raw_size > self.max_total_bytes:
            raise ds.DemoSnapshotError(
                CODE_FILES_BUDGET_EXCEEDED,
                "Demo file capture would exceed the total raw byte bound."
            )

    def admit_display(self, display_size: int) -> None:
        """Aggregate display admission BEFORE the leaf is retained."""
        if display_size > self.max_file_bytes:
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_TOO_LARGE,
                "A demo file display copy exceeds the per-file byte bound."
            )
        if self.display_bytes + display_size > self.max_total_bytes:
            raise ds.DemoSnapshotError(
                CODE_FILES_BUDGET_EXCEEDED,
                "Demo file capture would exceed the total display byte bound."
            )
        self.display_bytes += display_size
        self.files_count += 1


class _Capture:
    """In-memory capture state for ONE copy job (bounded, streaming).

    ``add_display`` is the single seam: it admits the RAW size, runs the
    kind's typed sanitizer, admits the DISPLAY size, and returns the
    sanitized leaf WITHOUT retaining the raw bytes (the caller's raw
    reference is the only one that ever existed). Peak retention is one
    raw file plus all display bytes, each aggregate bounded by
    ``max_total_bytes``.
    """

    def __init__(self, config: FileSnapshotConfig, settings: Settings) -> None:
        self.config = config
        self.settings = settings
        self.budget = _CaptureBudget(
            deadline=time.monotonic() + config.max_elapsed_seconds,
            raw_bytes=0,
            display_bytes=0,
            max_file_bytes=config.max_file_bytes,
            max_total_bytes=config.max_total_bytes,
            files_count=0,
        )
        self.leaves: list[DisplayLeaf] = []
        self.not_configured: list[str] = []
        self.source_records: dict[str, object] = {}
        self.capture_started_at = time.time()
        self.capture_finished_at: float | None = None

    def deadline_check(self) -> None:
        if time.monotonic() > self.budget.deadline:
            raise ds.DemoSnapshotError(
                CODE_FILES_BUDGET_EXCEEDED,
                "Demo file capture exceeded its elapsed bound."
            )

    def _next_leaf(self, digest: str) -> str:
        index = len(self.leaves)
        if index >= _FILES_MAX_LEAVES:
            raise ds.DemoSnapshotError(
                CODE_FILES_BUDGET_EXCEEDED,
                "Demo file capture would exceed the file count bound."
            )
        return f"f{index:04d}-{digest[:12]}"

    def add_display(
        self,
        *,
        kind: str,
        source: str,
        source_ref: str,
        logical_name: str,
        raw: bytes,
        inode_identity: tuple[int, int] | None = None,
        seed: bytes = b"",
        slot: str | None = None,
    ) -> DisplayLeaf:
        """Sanitize one captured raw file and retain only the display leaf."""
        self.deadline_check()
        # Aggregate raw admission happens BEFORE the typed sanitizer
        # parses or materializes anything from the raw bytes.
        self.budget.admit_raw(len(raw))
        data = _sanitize_by_kind(kind, raw, seed=seed, slot=slot)
        # Aggregate display admission happens BEFORE the leaf is stored.
        self.budget.admit_display(len(data))
        digest = hashlib.sha256(data).hexdigest()
        leaf = DisplayLeaf(
            leaf=self._next_leaf(digest),
            logical_name=logical_name,
            kind=kind,
            data=data,
            sha256=digest,
            source=source,
            source_ref=source_ref,
            captured_at=time.time(),
            source_sha256=hashlib.sha256(raw).hexdigest(),
            inode_identity=inode_identity,
        )
        self.leaves.append(leaf)
        return leaf




# ---------------------------------------------------------------------------
# Closed source-name grammars (mirrors the admin custody service's laws)
# ---------------------------------------------------------------------------

_UPLOAD_NAME_RE = re.compile(r"^(bundle|baseline|baseline-export)-[0-9a-f]{32}$")
_PROPOSAL_NAMES = frozenset(
    {
        "source-manifest.json",
        "provider-catalog-normalized.json",
        "routes-proposal.tsv",
        "pricing-proposal.tsv",
        "provider-catalog-report.md",
        "warnings.json",
    }
)
_PACKAGE_FILE_NAMES = frozenset(
    {
        "routes-proposal.tsv",
        "pricing-proposal.tsv",
        "package-report.md",
        "model-review.md",
        "package-manifest.json",
    }
)
_BRANDING_SLOTS = ("style.css", "logo", "logo-compact", "favicon", "hero")
_BRAND_SLOT_MAX_BYTES = 256 * 1024
_LLM_PROFILE_MAX_BYTES = 65536
_COMPLETION_PROFILE_MAX_BYTES = 65536
_COMPLETION_PROFILE_MAX_COUNT = 1000
_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

def _demo_run_id(seed: bytes, run_id: str) -> str:
    """Per-copy deterministic demo run id (slug-safe, link-preserving)."""
    import hashlib as _hashlib
    import hmac as _hmac

    digest = _hmac.new(seed, b"run|" + run_id.encode("utf-8"), _hashlib.sha256).digest()
    return f"demo-run-{digest[:12].hex()}"


def _demo_job_id(seed: bytes, job_id: str) -> str:
    """Per-copy deterministic demo job id (same mapping as the 222 copy DB).

    Returns the 32-lowercase-hex form required by the catalog job
    routes/records (no hyphens).
    """
    return remap_uuid(seed, _uuid.UUID(job_id)).hex


_RUN_FILE_KINDS = {
    "catalog-refresh.json": KIND_REFRESH_BUNDLE,
    "catalog-baseline.json": KIND_BASELINE_DOC,
    "routes-proposal.tsv": KIND_ROUTE_TSV,
    "pricing-proposal.tsv": KIND_PRICING_TSV,
    "fx-proposal.json": KIND_FX_JSON,
    "validation.json": KIND_VALIDATION_JSON,
    "REVIEW.html": KIND_REVIEW_HTML,
}
_UPLOAD_KINDS = {
    "bundle": KIND_REFRESH_BUNDLE,
    "baseline": KIND_BASELINE_DOC,
    "baseline-export": KIND_BASELINE_DOC,
}
_PROPOSAL_KINDS = {
    "source-manifest.json": KIND_SOURCE_MANIFEST,
    "provider-catalog-normalized.json": KIND_NORMALIZED_JSON,
    "routes-proposal.tsv": KIND_ROUTE_TSV,
    "pricing-proposal.tsv": KIND_PRICING_TSV,
    "provider-catalog-report.md": KIND_MARKDOWN,
    "warnings.json": KIND_WARNINGS_JSON,
}
_PACKAGE_KINDS = {
    "routes-proposal.tsv": KIND_ROUTE_TSV,
    "pricing-proposal.tsv": KIND_PRICING_TSV,
    "package-report.md": KIND_MARKDOWN,
    "model-review.md": KIND_MARKDOWN,
    "package-manifest.json": KIND_PACKAGE_MANIFEST,
}


def _held_subdir(parent_fd: int, name: str) -> int | None:
    """Open one subdirectory of a HELD directory fd (no-follow) and keep
    the child fd held for every later child open/read. Absent = None."""
    try:
        return os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent_fd
        )
    except FileNotFoundError:
        return None
    except OSError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "A demo file source directory could not be opened."
        ) from None


def _listdir_held(fd: int) -> list[str]:
    try:
        return sorted(os.listdir(fd))
    except OSError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "A demo file source directory could not be listed."
        ) from None


def _read_catalog_file(
    capture: _Capture,
    parent_fd: int,
    rel: str,
    kind: str,
    seed: bytes,
    cap: int,
    logical_name: str,
) -> None:
    """Read one closed-set catalog file through a HELD parent fd and
    stream it through the typed sanitizer."""
    # Structural invariant: the caller MUST supply the per-copy remapped
    # display identity; the ORIGINAL ``rel`` (source name/job/artifact id)
    # is used only for the held-fd traversal and is never persisted.
    if not isinstance(logical_name, str) or not logical_name:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED,
            "A catalog display leaf has no remapped display identity."
        )
    parts = rel.split("/")
    opened_here: int | None = None
    cur = parent_fd
    try:
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=cur
            )
            if opened_here is not None:
                os.close(opened_here)
            opened_here = child
            cur = child
        try:
            raw = catfs.anchored_read_fd(cur, parts[-1], cap)
        except (OSError, CatalogRefreshSealError):
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_MISSING,
                "A configured demo file source is missing or unreadable."
            ) from None
    except FileNotFoundError:
        return  # optional closed-set member absent: skip
    except ds.DemoSnapshotError:
        raise
    except OSError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "A configured demo file source is not a safe regular file."
        ) from None
    finally:
        if opened_here is not None:
            os.close(opened_here)
    # The private manifest carries ONLY the remapped display identity.
    capture.add_display(
        kind=kind,
        source="catalog",
        source_ref=logical_name,
        logical_name=logical_name,
        raw=raw,
        seed=seed,
    )


def _declared_run_bytes(run_fd: int) -> int:
    """Sum the DECLARED content-file bytes from the run manifest before
    any content is materialized (bounded pre-read budgeting)."""
    try:
        manifest_raw = catfs.anchored_read_fd(
            run_fd, "manifest.json", catfs.MAX_AUX_BYTES
        )
        manifest = catfs.strict_json_bytes(manifest_raw, "manifest.json")
    except (OSError, CatalogRefreshSealError):
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED,
            "A configured catalog run manifest is missing or unreadable."
        ) from None
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "files"}:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED,
            "A configured catalog run manifest has an unknown shape."
        )
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED,
            "A configured catalog run manifest has an unknown shape."
        )
    total = 0
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256", "bytes"}
            or not isinstance(entry.get("path"), str)
            or entry.get("path") not in CONTENT_FILES
            or isinstance(entry.get("bytes"), bool)
            or not isinstance(entry.get("bytes"), int)
            or entry["bytes"] < 0
        ):
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_UNSUPPORTED,
                "A configured catalog run manifest has an unknown shape."
            )
        total += entry["bytes"]
    return total


def _verify_catalog_root(config: FileSnapshotConfig) -> catfs.AnchoredDir:
    """Read-only verification of the configured catalog custody root.

    Returns a HELD anchored handle (every component no-follow). The root
    must be an existing owner-only 0700 directory. Nothing is created or
    repaired: the 223 worker must not mutate catalog source files, so
    the potentially-creating product setup inspector is deliberately NOT
    called here.
    """
    try:
        handle = catfs.open_anchored_handle(config.catalog_root)
    except catfs.CatalogRefreshSealError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "The configured catalog custody root is not usable."
        ) from None
    st = os.fstat(handle.dir_fd)
    # Match the existing catalog source acceptance law: an owner-owned
    # directory that is not group/world WRITABLE (the docs recommend
    # 0700 but the read-only source boundary enforces no group/other
    # write). The demo OUTPUT custody stays strictly 0700.
    if (
        not stat_module.S_ISDIR(st.st_mode)
        or st.st_uid != os.geteuid()
        or (st.st_mode & 0o022) != 0
    ):
        handle.close()
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "The configured catalog custody root is not usable."
        )
    return handle


_JOB_NAME_RE = re.compile(r"^[0-9a-f]{32}\.json$")
_JOB_RECORD_MAX_BYTES = 1 * 1024 * 1024
# The exact product vocabularies (services/admin_catalog_refresh.py).
_JOB_FAMILY_VOCAB = frozenset(
    {"collect", "review_supplied", "export_baseline", "proposal"}
)
_JOB_STATUS_VOCAB = frozenset(
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
_DISPATCH_VOCAB = frozenset({"confirmed", "unconfirmed"})


def _is_iso_timestamp(value: object) -> bool:
    """Bounded ISO-8601 timestamp check (None allowed). Malformed text
    is refused, so a record field can never carry arbitrary secret text
    into a display copy."""
    if value is None:
        return True
    if not isinstance(value, str) or not (10 <= len(value) <= 40):
        return False
    try:
        _dt.fromisoformat(value)
    except ValueError:
        return False
    return True


def _hmac_hex64(seed: bytes, salt: bytes, value: str) -> str:
    return _hmac.new(seed, salt + b"|" + value.encode("utf-8"), hashlib.sha256).hexdigest()


def _remap_upload_name(seed: bytes, name: str) -> str:
    """Per-copy remap of one closed upload name: same prefix, 32-hex
    keyed suffix (same closed grammar; correlation broken). Used for BOTH
    the logical upload display paths and the job-record references so
    every displayed reference links to the same per-copy name."""
    kind, _sep, _suffix = name.partition("-")
    return f"{kind}-{_hmac_hex64(seed, b"artifact", name)[:32]}"


def _sanitize_job_record(raw: bytes, seed: bytes) -> bytes:
    """Typed display projection of one custody job record.

    Projects exactly the admin-visible ``job_projection`` fields against
    the product's finite vocabularies; raw params are never displayed.
    The job id is remapped with the SAME per-copy mapping as the 222 copy
    DB, the referenced run id uses the per-copy demo run id, and free
    text (progress) and error detail (error_code) are neutralized.
    Unknown record shape or type fails closed.
    """
    try:
        record = catfs.strict_json_bytes(raw, "job record")
    except CatalogRefreshSealError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED,
            "A catalog job record is not strict JSON."
        ) from None
    if not isinstance(record, dict):
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED,
            "A catalog job record has an unknown shape."
        )
    job_id = record.get("job_id")
    family = record.get("family")
    status = record.get("status")
    progress = record.get("progress")
    dispatch = record.get("dispatch")
    run_id = record.get("run_id")
    artifact_name = record.get("artifact_name")
    cancel_requested = record.get("cancel_requested")
    created_at = record.get("created_at")
    updated_at = record.get("updated_at")
    if (
        not isinstance(job_id, str)
        or not _JOB_LEAF_RE.fullmatch(job_id)
        or family not in _JOB_FAMILY_VOCAB
        or status not in _JOB_STATUS_VOCAB
        or not isinstance(progress, str)
        or dispatch not in (None, *_DISPATCH_VOCAB)
        or not (
            run_id is None
            or (isinstance(run_id, str) and _RUN_ID_RE.fullmatch(run_id))
        )
        or not (
            artifact_name is None
            or (isinstance(artifact_name, str) and _UPLOAD_NAME_RE.fullmatch(artifact_name))
        )
        or not isinstance(cancel_requested, bool)
        or not _is_iso_timestamp(created_at)
        or not _is_iso_timestamp(updated_at)
    ):
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSUPPORTED, "A catalog job record has an unknown shape."
        )
    artifact_display = (
        _remap_upload_name(seed, artifact_name)
        if artifact_name is not None
        else None
    )
    projection = {
        "schema_version": DEMO_SCHEMA_VERSION,
        "kind": "catalog_job_record",
        "job_id": _demo_job_id(seed, job_id),
        "family": family,
        "status": status,
        # Free text may carry operator/broker detail: neutralized.
        "progress": DEMO_NOTES,
        "dispatch": dispatch,
        "run_id": _demo_run_id(seed, run_id) if run_id is not None else None,
        # The original name suffix is a source content identifier: it is
        # remapped per copy with the same mapping the logical upload
        # display paths use (correlation broken, links stay consistent).
        "artifact_name": artifact_display,
        # Error detail is never displayed.
        "error_code": None,
        "cancel_requested": cancel_requested,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return (json.dumps(projection, sort_keys=True, indent=1) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Typed display sanitizers (one per kind; unknown shape fails closed)
# ---------------------------------------------------------------------------

# The baseline row-count map carries exactly the four closed catalog
# table names (collection.py first_install emits an empty map). Any
# other key is an unreviewed string position and is refused.
_BASELINE_ROW_COUNT_KEYS = frozenset(
    {"providers", "routes", "pricing_rules", "fx_rates"}
)


def _closed_row_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise _unsupported("A demo baseline row-count map has an unexpected shape.")
    result: dict[str, int] = {}
    for key, item in value.items():
        if key not in _BASELINE_ROW_COUNT_KEYS:
            raise _unsupported(
                "A demo baseline row-count map has an unexpected key."
            )
        if type(item) is not int or item < 0:
            raise _unsupported(
                "A demo baseline row-count map has an unexpected value."
            )
        result[key] = item
    return result


def _unsupported(message: str) -> ds.DemoSnapshotError:
    return ds.DemoSnapshotError(CODE_FILES_SOURCE_UNSUPPORTED, message)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate JSON key")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(_token: str) -> object:
    raise ValueError("non-finite JSON value")


def _json_strict(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _unsupported("A demo file source is not valid UTF-8.") from None
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ValueError:
        raise _unsupported("A demo file source carries invalid JSON.") from None


def _str(value: object, field: str, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    return value


def _str_opt(value: object, field: str, max_len: int) -> str | None:
    if value is None:
        return None
    return _str(value, field, max_len)


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    return value


def _int(value: object, field: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    return value


def _iso_dt(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    try:
        parsed = _dt.fromisoformat(value)
    except ValueError:
        raise _unsupported(f"A demo file field has an unexpected shape: {field}") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _unsupported(f"A demo file timestamp is not timezone-aware: {field}")
    return parsed.astimezone(_dt_timezone.utc).isoformat()


def _decimal(value: object, field: str, allow_empty: bool = False) -> str | None:
    if value is None or (allow_empty and value == ""):
        return None if value is None else ""
    if not isinstance(value, str):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    try:
        number = decimal.Decimal(value)
    except (decimal.InvalidOperation, ValueError):
        raise _unsupported(f"A demo file field has an unexpected shape: {field}") from None
    if not number.is_finite() or number < 0:
        raise _unsupported(f"A demo file field has an unexpected value: {field}")
    return value


def _demo_uuid(seed: bytes, value: object, field: str) -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise _unsupported(f"A demo file identity has an unexpected shape: {field}")
    return str(remap_uuid(seed, _uuid.UUID(value)))


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}$")


def _model_id(value: object, field: str) -> str:
    """A bounded provider/model identifier (no free text, no whitespace)."""
    if not isinstance(value, str) or not _MODEL_ID_RE.fullmatch(value):
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    return value


def _model_id_opt(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _model_id(value, field)


def _decimal_opt(
    value: object, field: str, allow_negative: bool = False
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    try:
        number = decimal.Decimal(value)
    except (decimal.InvalidOperation, ValueError):
        raise _unsupported(f"A demo file field has an unexpected shape: {field}") from None
    if not number.is_finite() or (not allow_negative and number < 0):
        raise _unsupported(f"A demo file field has an unexpected value: {field}")
    return value


def _nonneg_int_map_total(value: object, field: str) -> int:
    """Reduce a code->count map to its total (map KEYS are never shown)."""
    total = 0
    for key, item in _dict_keys(value, field).items():
        if not isinstance(key, str) or type(item) is not int or item < 0:
            raise _unsupported(f"A demo file field has an unexpected shape: {field}")
        total += item
    return total


def _provider(value: object, field: str) -> str:
    from slaif_gateway.schemas.catalog_refresh import KNOWN_PROVIDERS

    if not isinstance(value, str) or value not in KNOWN_PROVIDERS:
        raise _unsupported(f"A demo file provider is not recognized: {field}")
    return value


def _provider_opt(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _provider(value, field)


def _source_provider(value: object, field: str) -> str:
    """Source-provenance provider (validation.sources rows): the
    producer's own finite SourceRecord law - the route providers plus
    the ECB FX reference publisher. This is a SOURCE taxonomy and does
    NOT widen the gateway route-provider law used elsewhere."""
    from slaif_gateway.schemas.catalog_refresh import KNOWN_PROVIDERS

    if not isinstance(value, str) or value not in KNOWN_PROVIDERS | {"ecb"}:
        raise _unsupported(
            f"A demo file source provider is not recognized: {field}"
        )
    return value


def _bool_map(value: object, field: str) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    result: dict[str, bool] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 64
            or not isinstance(item, bool)
        ):
            raise _unsupported(f"A demo file field has an unexpected shape: {field}")
        result[key] = item
    return result


def _chat_capabilities_map(value: object, field: str) -> dict[str, bool]:
    """Capabilities must come from the closed chat-capability vocabulary."""
    from slaif_gateway.services.chat_completion_route_capabilities import (
        KNOWN_CHAT_COMPLETION_CAPABILITIES,
    )

    result = _bool_map(value, field)
    for key in result:
        if key not in KNOWN_CHAT_COMPLETION_CAPABILITIES:
            raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    return result

def _catalog_capabilities_map(value: object, field: str) -> dict[str, bool]:
    """Catalog capability keys: the closed CAPABILITY_KEYS law of the
    catalog refresh bundle (text/streaming/...), which is DISTINCT from
    the runtime chat-completion capability vocabulary (DB routes)."""
    from slaif_gateway.schemas.catalog_refresh import CAPABILITY_KEYS

    result = _bool_map(value, field)
    for key in result:
        if key not in CAPABILITY_KEYS:
            raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    return result


def _validated_runtime_capabilities(value: object, field: str) -> dict[str, object]:
    """The sealed route TSV's capabilities cell carries the derived
    RUNTIME capability projection (endpoint-family boolean blocks plus
    the typed codex limits / compaction route-id allowlist /
    external-tools policy), not the flat catalog vocabulary. The
    schema's own strict projection law validates it; unknown blocks or
    fields are refused and nothing is passed through unreviewed."""
    from slaif_gateway.schemas.catalog_refresh import (
        validate_route_capability_projection,
    )

    if not isinstance(value, dict):
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    try:
        validate_route_capability_projection(value)
    except Exception:
        raise _unsupported(
            f"A demo file field has an unexpected shape: {field}"
        ) from None
    return value


def _dump(document: object) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _fx_projection_document(value: object, seed: bytes) -> dict[str, object] | None:
    """The reviewed fx capture projection (fx_rate_id remapped per copy)."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "base_currency",
        "target_currency",
        "fx_rate_id",
        "rate",
        "valid_from",
        "valid_until",
        "captured_at",
    }:
        raise _unsupported("A demo file fx capture has an unexpected shape.")
    fx_rate_id = value["fx_rate_id"]
    if not (
        isinstance(fx_rate_id, str)
        and _UUID_RE.fullmatch(fx_rate_id)
    ):
        raise _unsupported("A demo file fx rate identity has an unexpected shape.")
    return {
        "base_currency": _str(value["base_currency"], "fx.base_currency", 8),
        "target_currency": _str(value["target_currency"], "fx.target_currency", 8),
        "fx_rate_id": _demo_uuid(seed, fx_rate_id, "fx.fx_rate_id"),
        "rate": _decimal(value["rate"], "fx.rate") or "",
        "valid_from": _iso_dt(value["valid_from"], "fx.valid_from"),
        "valid_until": (
            _iso_dt(value["valid_until"], "fx.valid_until")
            if value["valid_until"] is not None
            else None
        ),
        "captured_at": _iso_dt(value["captured_at"], "fx.captured_at"),
    }


def _san_refresh_bundle(raw: bytes, seed: bytes) -> bytes:
    from slaif_gateway.schemas.catalog_refresh import RefreshBundle

    try:
        bundle = RefreshBundle.model_validate(_json_strict(raw))
    except (ds.DemoSnapshotError,):
        raise
    except Exception:
        raise _unsupported("A demo catalog bundle has an unrecognized schema.") from None
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_REFRESH_BUNDLE,
            "run_id": _demo_run_id(seed, bundle.run_id),
            "generated_at": bundle.generated_at.isoformat(),
            "revision": {
                # The source code revision is a source identifier and is
                # never displayed; the finite app versions remain.
                "slaif_revision": DEMO_CODE_REVISION,
                "renderer_version": bundle.revision.renderer_version,
                "policy_version": bundle.revision.policy_version,
            },
            "research": {"status": bundle.research.status},
            "collection": None,
            "policy": {
                "version": bundle.policy.version,
                "price_change_review": bundle.policy.price_change_review,
                "fx_change_review": bundle.policy.fx_change_review,
                "source_stale_review_hours": bundle.policy.source_stale_review_hours,
                "source_stale_blocked_hours": bundle.policy.source_stale_blocked_hours,
                "fx_stale_review_days": bundle.policy.fx_stale_review_days,
                "fx_stale_blocked_days": bundle.policy.fx_stale_blocked_days,
            },
            "profile": {
                "name": bundle.profile.name,
                "endpoint": bundle.profile.endpoint,
                "supports_streaming": bundle.profile.supports_streaming,
                "local_models_visible": bundle.profile.local_models_visible,
                "capability_allowlist": list(bundle.profile.capability_allowlist),
            },
            "selection": {
                "providers": list(bundle.selection.providers),
                "model_include": list(bundle.selection.model_include),
            },
            # Source retrieval records (URLs/times per retrieval) are never
            # displayed; only the finite count remains.
            "sources": {"count": len(bundle.sources)},
            "models": [
                {
                    "provider": m.provider,
                    "model": m.model,
                    "context_length": m.context_length,
                    "max_output_tokens": m.max_output_tokens,
                    "supports_streaming": m.supports_streaming,
                        "capabilities": _catalog_capabilities_map(
                            dict(m.capabilities), "bundle.model.capabilities"
                        ),
                    "deprecated": m.deprecated,
                }
                for m in bundle.models
            ],
            "pricing": [
                {
                    "provider": p.provider,
                    "model": p.model,
                    "endpoint": p.endpoint,
                    "currency": p.currency,
                    "dimensions": [
                        {
                            "name": d.name,
                            "value": d.value,
                            "unit": d.unit,
                            "currency": d.currency,
                        }
                        for d in p.dimensions
                    ],
                    "valid_from": p.valid_from.isoformat(),
                }
                for p in bundle.pricing
            ],
            "routes": [
                {
                    "provider": r.provider,
                    "requested_model": r.requested_model,
                    "upstream_model": r.upstream_model,
                    "match_type": r.match_type,
                    "endpoint": r.endpoint,
                    "priority": r.priority,
                    "enabled": r.enabled,
                    "visible_in_models": r.visible_in_models,
                    "supports_streaming": r.supports_streaming,
                        "capabilities": _catalog_capabilities_map(
                            dict(r.capabilities), "bundle.route.capabilities"
                        ),
                }
                for r in bundle.routes
            ],
            "fx": [
                {
                    "base_currency": f.base_currency,
                    "quote_currency": f.quote_currency,
                    "rate": f.rate,
                    "valid_from": f.valid_from.isoformat(),
                    "valid_until": (
                        f.valid_until.isoformat() if f.valid_until is not None else None
                    ),
                }
                for f in bundle.fx
            ],
            # The baseline TARGET (database/host/port) identifies the
            # source deployment and is never displayed.
            "baseline": {
                "mode": bundle.baseline.mode,
                "postgres_version": bundle.baseline.postgres_version,
                "sql_checked": bundle.baseline.sql_checked,
                "row_counts": _closed_row_counts(bundle.baseline.row_counts),
            },
        }
    )


def _san_baseline_document(raw: bytes, seed: bytes) -> bytes:
    from slaif_gateway.schemas.catalog_refresh import BaselineDocument

    document = _json_strict(raw)
    # Bounded first-install placeholder: a sealed first-install run
    # publishes the canonical empty marker document, NOT a
    # BaselineDocument. The note is fixed product text (never operator
    # content) and is not displayed; only the neutral marker survives.
    if (
        isinstance(document, dict)
        and set(document) == {"schema_version", "note"}
        and document["schema_version"] == "first-install"
        and isinstance(document["note"], str)
        and 0 < len(document["note"]) <= 256
    ):
        return _dump(
            {
                "schema": DEMO_SCHEMA_VERSION,
                "kind": KIND_BASELINE_DOC,
                "first_install": True,
            }
        )
    try:
        doc = BaselineDocument.model_validate(document)
    except ds.DemoSnapshotError:
        raise
    except Exception:
        raise _unsupported(
            "A demo catalog baseline has an unrecognized schema."
        ) from None
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_BASELINE_DOC,
            "exported_at": doc.exported_at.isoformat(),
            "target": {"postgres_version": doc.target.postgres_version},
            "sql_checked": doc.sql_checked,
            "counts": {
                "providers": doc.counts.providers,
                "routes": doc.counts.routes,
                "pricing_rules": doc.counts.pricing_rules,
                "fx_rates": doc.counts.fx_rates,
            },
            "providers": [
                {
                    "id": _demo_uuid(seed, p.id, "provider.id"),
                    "provider": p.provider,
                    "kind": p.kind,
                    "enabled": p.enabled,
                    "timeout_seconds": p.timeout_seconds,
                    "max_retries": p.max_retries,
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in doc.providers
            ],
            "routes": [
                {
                    "id": _demo_uuid(seed, r.id, "route.id"),
                    "requested_model": r.requested_model,
                    "match_type": r.match_type,
                    "endpoint": r.endpoint,
                    "provider": r.provider,
                    "upstream_model": r.upstream_model,
                    "priority": r.priority,
                    "enabled": r.enabled,
                    "visible_in_models": r.visible_in_models,
                    "supports_streaming": r.supports_streaming,
                    "capabilities": r.capabilities,
                    "capabilities_unrepresented": r.capabilities_unrepresented,
                    "capabilities_fingerprint": r.capabilities_fingerprint,
                    "created_at": r.created_at.isoformat(),
                    "updated_at": r.updated_at.isoformat(),
                }
                for r in doc.routes
            ],
            "pricing": [
                {
                    "id": _demo_uuid(seed, p.id, "pricing.id"),
                    "provider": p.provider,
                    "upstream_model": p.upstream_model,
                    "endpoint": p.endpoint,
                    "currency": p.currency,
                    "request_price": p.request_price,
                    "valid_from": p.valid_from.isoformat(),
                    "valid_until": (
                        p.valid_until.isoformat() if p.valid_until is not None else None
                    ),
                    "enabled": p.enabled,
                    "cache_write_input_multiplier": p.cache_write_input_multiplier,
                    "long_context_threshold_tokens": p.long_context_threshold_tokens,
                    "long_context_input_multiplier": p.long_context_input_multiplier,
                    "long_context_output_multiplier": p.long_context_output_multiplier,
                    "external_tool_price_per_call": p.external_tool_price_per_call,
                    "external_tool_source": p.external_tool_source,
                    "pricing_metadata_unrepresented": p.pricing_metadata_unrepresented,
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in doc.pricing
            ],
            "fx": [
                {
                    "id": _demo_uuid(seed, f.id, "fx.id"),
                    "base_currency": f.base_currency,
                    "quote_currency": f.quote_currency,
                    "rate": f.rate,
                    "valid_from": f.valid_from.isoformat(),
                    "valid_until": (
                        f.valid_until.isoformat() if f.valid_until is not None else None
                    ),
                    "created_at": f.created_at.isoformat(),
                }
                for f in doc.fx
            ],
        }
    )


def _tsv_rows_raw(raw: bytes, header: list[str], fail) -> list[list[str]]:
    """Shared tab-TSV reader for producer AND display bytes.

    The sealed-run producer writes csv.DictWriter output (tab delimiter,
    RFC-style quoting of JSON cells, CRLF rows); the display writer
    emits the same dialect with inert unquoted cells. Standard csv
    parsing handles both; EXACT header, EXACT row width, a bounded row
    count and no newline-bearing cell are required, else fail closed.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise fail("is not valid UTF-8.") from None
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
    try:
        rows = list(reader)
    except csv.Error:
        raise fail("has an unexpected shape.") from None
    if not rows or rows[0] != list(header):
        raise fail("has an unexpected header.")
    body = rows[1:]
    if len(body) > _MAX_ROWS:
        raise fail("exceeds its row bound.")
    for cells in body:
        if len(cells) != len(header) or any(
            "\n" in cell or "\r" in cell for cell in cells
        ):
            raise fail("row has an unexpected shape.")
    return body


def _tsv_rows(raw: bytes, header: list[str], field: str) -> list[list[str]]:
    def fail(msg: str) -> ds.DemoSnapshotError:
        return _unsupported(f"A demo {field} {msg}")

    return _tsv_rows_raw(raw, header, fail)


def _tsv_rows_verify(data: bytes, header: list[str]) -> list[list[str]]:
    def fail(msg: str) -> ds.DemoSnapshotError:
        return ds.DemoSnapshotError(CODE_FILES_VERIFY_FAILED, f"A display leaf {msg}")

    return _tsv_rows_raw(data, header, fail)


def _tsv_bool(cell: str, field: str) -> bool:
    if cell == "true":
        return True
    if cell == "false":
        return False
    raise _unsupported(f"A demo {field} has an unexpected value.")


def _tsv_int(cell: str, field: str, lo: int, hi: int) -> int:
    try:
        value = int(cell)
    except ValueError:
        raise _unsupported(f"A demo {field} has an unexpected value.") from None
    if not lo <= value <= hi:
        raise _unsupported(f"A demo {field} has an unexpected value.")
    return value


def _san_route_tsv(raw: bytes, seed: bytes) -> bytes:
    from slaif_gateway.services.catalog_refresh.bundle import ROUTE_TSV_FIELDS

    header = list(ROUTE_TSV_FIELDS)
    rows = _tsv_rows(raw, header, "route proposal")
    out: list[list[str]] = []
    for cells in rows:
        by = dict(zip(header, cells))
        capabilities = _validated_runtime_capabilities(
            _json_strict(by["capabilities"].encode("utf-8")), "route.capabilities"
        )
        row = [
            by["requested_model"],
            by["match_type"],
            by["endpoint"],
            _provider(by["provider"], "route.provider"),
            by["upstream_model"],
            str(_tsv_int(by["priority"], "route.priority", 1, 100000)),
            str(_tsv_bool(by["enabled"], "route.enabled")).lower(),
            str(_tsv_bool(by["visible_in_models"], "route.visible")).lower(),
            str(_tsv_bool(by["supports_streaming"], "route.streaming")).lower(),
            json.dumps(capabilities, sort_keys=True, separators=(",", ":")),
            DEMO_NOTES,
        ]
        out.append(row)
    return ("\n".join(["\t".join(header)] + ["\t".join(r) for r in out]) + "\n").encode("utf-8")


def _san_pricing_tsv(raw: bytes, seed: bytes) -> bytes:
    from slaif_gateway.services.catalog_refresh.bundle import PRICING_TSV_FIELDS

    header = list(PRICING_TSV_FIELDS)
    rows = _tsv_rows(raw, header, "pricing proposal")
    # Arbitrary operator JSONB metadata: parsed to prove shape, then
    # emitted as a neutral fixed empty object (never the source content).
    out: list[list[str]] = []
    for cells in rows:
        by = dict(zip(header, cells))
        _provider(by["provider"], "pricing.provider")
        for price_field in (
            "input_price_per_1m",
            "cached_input_price_per_1m",
            "output_price_per_1m",
            "reasoning_price_per_1m",
            "request_price",
        ):
            _decimal(by[price_field], f"pricing.{price_field}", allow_empty=True)
        _iso_dt(by["valid_from"], "pricing.valid_from")
        if by["source_retrieved_at"]:
            _iso_dt(by["source_retrieved_at"], "pricing.source_retrieved_at")
        # The producer leaves the cell EMPTY when a row carries no
        # metadata; a present cell must be a JSON object (validated,
        # then dropped - the display cell is always the fixed "{}").
        if by["pricing_metadata"]:
            metadata = _json_strict(by["pricing_metadata"].encode("utf-8"))
            if not isinstance(metadata, dict):
                raise _unsupported("A demo pricing metadata has an unexpected shape.")
        row = [
            by["provider"],
            by["model"],
            by["endpoint"],
            by["currency"],
            by["input_price_per_1m"],
            by["cached_input_price_per_1m"],
            by["output_price_per_1m"],
            by["reasoning_price_per_1m"],
            by["request_price"],
            by["valid_from"],
            DEMO_NOTES,  # source_url: never displayed
            by["source_retrieved_at"],
            "{}",
            DEMO_NOTES,
        ]
        out.append(row)
    return ("\n".join(["\t".join(header)] + ["\t".join(r) for r in out]) + "\n").encode("utf-8")


def _san_fx_json(raw: bytes, seed: bytes) -> bytes:
    from slaif_gateway.schemas.catalog_refresh import FxFacts

    value = _json_strict(raw)
    if not isinstance(value, list):
        raise _unsupported("A demo fx proposal has an unexpected shape.")
    facts = []
    for item in value:
        try:
            fact = FxFacts.model_validate(item)
        except Exception:
            raise _unsupported("A demo fx fact has an unrecognized schema.") from None
        facts.append(
            {
                "base_currency": fact.base_currency,
                "quote_currency": fact.quote_currency,
                "rate": fact.rate,
                "valid_from": fact.valid_from.isoformat(),
                "valid_until": (
                    fact.valid_until.isoformat() if fact.valid_until is not None else None
                ),
            }
        )
    return _dump(
        {"schema": DEMO_SCHEMA_VERSION, "kind": KIND_FX_JSON, "fx": facts}
    )


_VALIDATION_TOP_KEYS: frozenset[str] = frozenset(
    {
        "state",
        "state_reason",
        "run_id",
        "generated_at",
        "policy_version",
        "counts",
        "per_provider",
        "dispositions",
        "price_comparisons",
        "warnings",
        "gates",
        "import_gates",
        "baseline",
        "research",
        "artifacts",
        "sql_checks",
        "baseline_metadata",
        "sources",
        "source_evidence",
        "fx_comparisons",
        "execution_context",
        # apply_plan is accepted (and dropped): apply authority is never
        # displayed.
        "apply_plan",
    }
)


def _dict_keys(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    return value


def _str_int_map(value: object, field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, item in _dict_keys(value, field).items():
        if not isinstance(key, str) or type(item) is not int:
            raise _unsupported(f"A demo file field has an unexpected shape: {field}")
        result[key] = item
    return result


def _list_of(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise _unsupported(f"A demo file field has an unexpected type: {field}")
    return value


def _san_validation_json(raw: bytes, seed: bytes) -> bytes:
    doc = _dict_keys(_json_strict(raw), "validation")
    if not set(doc) <= _VALIDATION_TOP_KEYS or not (
        {"state", "state_reason", "run_id", "generated_at", "policy_version"}
        <= set(doc)
    ):
        raise _unsupported("A demo validation document has an unexpected shape.")

    def sub(field: str) -> dict[str, object]:
        return _dict_keys(doc.get(field), f"validation.{field}")

    dispositions = []
    for item in _list_of(doc.get("dispositions", []), "validation.dispositions"):
        row = _dict_keys(item, "validation.disposition")
        dispositions.append(
            {
                "provider": _provider(row.get("provider"), "disposition.provider"),
                "model": _model_id(row.get("model"), "disposition.model"),
                "disposition": _str(row.get("disposition"), "disposition.kind", 32),
            }
        )
    price_comparisons = []
    for item in _list_of(
        doc.get("price_comparisons", []), "validation.price_comparisons"
    ):
        row = _dict_keys(item, "validation.price_comparison")
        price_comparisons.append(
            {
                "provider": _provider(row.get("provider"), "comparison.provider"),
                "model": _model_id(row.get("model"), "comparison.model"),
                "dimension": _str(row.get("dimension"), "comparison.dimension", 64),
                "old": _decimal_opt(row.get("old"), "comparison.old"),
                "new": _decimal_opt(row.get("new"), "comparison.new"),
                # First-install (NEW) comparisons carry no OLD side: the
                # producer's currency_old is nullable; currency_new is
                # always the dimension currency.
                "currency_old": _str_opt(
                    row.get("currency_old"), "comparison.currency_old", 8
                ),
                "currency_new": _str(row.get("currency_new"), "comparison.currency_new", 8),
                "percent_change": _decimal_opt(
                    row.get("percent_change"), "comparison.percent_change",
                    allow_negative=True,
                ),
                "state": _str(row.get("state"), "comparison.state", 32),
            }
        )
    warnings = []
    for item in _list_of(doc.get("warnings", []), "validation.warnings"):
        row = _dict_keys(item, "validation.warning")
        warnings.append(
            {
                "severity": _str(row.get("severity"), "warning.severity", 16),
                "code": _str(row.get("code"), "warning.code", 64),
                # provider is app-generated from the closed vocabulary; the
                # model detail is dropped (free-text position).
                "provider": _provider_opt(row.get("provider"), "warning.provider"),
            }
        )
    gates = [
        {
            "name": _str(
                _dict_keys(item, "validation.gate").get("name"), "gate.name", 64
            )
        }
        for item in _list_of(doc.get("gates", []), "validation.gates")
    ]
    import_gates = []
    for item in _list_of(doc.get("import_gates", []), "validation.import_gates"):
        row = _dict_keys(item, "validation.import_gate")
        import_gates.append(
            {
                "kind": _str(row.get("kind"), "import_gate.kind", 32),
                "schema_valid": _bool(row.get("schema_valid"), "import_gate.schema_valid"),
                "total_rows": _int(row.get("total_rows"), "import_gate.total_rows", 0, 10**9),
                "valid_rows": _int(row.get("valid_rows"), "import_gate.valid_rows", 0, 10**9),
                "invalid_rows": _int(row.get("invalid_rows"), "import_gate.invalid_rows", 0, 10**9),
                "classifications": {
                    "total": _nonneg_int_map_total(
                        row.get("classifications"), "import_gate.classifications"
                    )
                },
                "plan_ready_rows": _int(row.get("plan_ready_rows"), "import_gate.plan_ready_rows", 0, 10**9),
                "plan_blocked_rows": _int(
                    row.get("plan_blocked_rows"), "import_gate.plan_blocked_rows", 0, 10**9
                ),
                # The producer emits a plain non-negative integer
                # aggregate (classifications is the map, not this).
                "excluded_mutations": _int(
                    row.get("excluded_mutations"),
                    "import_gate.excluded_mutations",
                    0,
                    10**9,
                ),
            }
        )
    baseline_metadata = []
    for item in _list_of(
        doc.get("baseline_metadata", []), "validation.baseline_metadata"
    ):
        row = _dict_keys(item, "validation.baseline_metadata_row")
        baseline_metadata.append(
            {
                "provider": _provider(row.get("provider"), "baseline_meta.provider"),
                "model": _model_id(row.get("model"), "baseline_meta.model"),
                "upstream_model": _model_id_opt(
                    row.get("upstream_model"), "baseline_meta.upstream_model"
                ),
                # field names are map positions: only the count remains.
                "fields": {
                    "count": len(
                        _dict_keys(row.get("fields"), "baseline_meta.fields")
                    )
                },
            }
        )
    sources = []
    for item in _list_of(doc.get("sources", []), "validation.sources"):
        row = _dict_keys(item, "validation.source")
        from slaif_gateway.schemas.catalog_refresh import SOURCE_KINDS

        source_kind = row.get("source_kind")
        if not (isinstance(source_kind, str) and source_kind in SOURCE_KINDS):
            raise _unsupported(
                "A demo file field has an unexpected shape: source.kind"
            )
        sources.append(
            {
                "provider": _source_provider(row.get("provider"), "source.provider"),
                "model": _model_id(row.get("model"), "source.model"),
                "source_kind": source_kind,
            }
        )
    context = _dict_keys(doc.get("execution_context"), "validation.execution_context")
    execution_context: dict[str, object] | None = None
    if context:
        from slaif_gateway.schemas.catalog_refresh import ExecutionContext

        try:
            ctx = ExecutionContext.model_validate(context)
        except Exception:
            raise _unsupported(
                "A demo validation document has an unexpected execution context."
            ) from None
        # The context is runner-owned app metadata: the typed law pins
        # the versions to the CURRENT product constants (a sealed run of
        # another version is refused, not displayed). code_revision and
        # the tool identity are source code identifiers, never displayed.
        execution_context = {
            "schema_version": ctx.schema_version,
            "acquisition": ctx.acquisition,
            "generator_versions": {
                "schema_version": ctx.generator_versions.schema_version,
                "renderer_version": ctx.generator_versions.renderer_version,
                "policy_version": ctx.generator_versions.policy_version,
                "extractor_version": ctx.generator_versions.extractor_version,
            },
        }
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_VALIDATION_JSON,
            "state": _str(doc.get("state"), "validation.state", 32),
            # state_reason and every detail/evidence field is free text
            # and is never displayed.
            "state_reason": DEMO_NOTES,
            "run_id": _demo_run_id(seed, _str(doc.get("run_id"), "validation.run_id", 128)),
            "generated_at": _iso_dt(doc.get("generated_at"), "validation.generated_at"),
            "policy_version": _int(doc.get("policy_version"), "validation.policy_version", 1, 1000),
            # count NAMES are map positions: only the entry count remains.
            "counts": {
                "entries": len(
                    _dict_keys(doc.get("counts", {}), "validation.counts")
                )
            },
            # Provider keys are the closed vocabulary; the inner metric
            # names are map positions, reduced to their total.
            "per_provider": {
                _provider(provider, f"validation.per_provider.{provider}"): {
                    "total": _nonneg_int_map_total(
                        values, f"validation.per_provider.{provider}"
                    )
                }
                for provider, values in _dict_keys(
                    doc.get("per_provider", {}), "validation.per_provider"
                ).items()
            },
            "dispositions": dispositions,
            "price_comparisons": price_comparisons,
            "warnings": warnings,
            "gates": gates,
            "import_gates": import_gates,
            # Evidence blobs are reduced to finite counts only.
            "baseline": {"count": len(_dict_keys(doc.get("baseline"), "validation.baseline"))},
            "research": {"count": len(_dict_keys(doc.get("research"), "validation.research"))},
            "artifacts": {"count": len(_dict_keys(doc.get("artifacts"), "validation.artifacts"))},
            "sql_checks": {"count": len(_dict_keys(doc.get("sql_checks"), "validation.sql_checks"))},
            "baseline_metadata": baseline_metadata,
            "sources": sources,
            "source_evidence": {},
            "fx_comparisons": {"count": len(_list_of(doc.get("fx_comparisons", []), "validation.fx_comparisons"))},
            "execution_context": execution_context,
        }
    )


_NORMALIZED_TOP_KEYS: frozenset[str] = frozenset(
    {
        "providers",
        "fx",
        "export_filters",
        "export_row_counts",
        "models",
        "pricing_candidates",
        "route_candidates",
        "comparison_rows",
    }
)


def _san_normalized_json(raw: bytes, seed: bytes) -> bytes:
    doc = _dict_keys(_json_strict(raw), "normalized")
    if set(doc) != _NORMALIZED_TOP_KEYS:
        raise _unsupported(
            "A demo normalized catalog has an unexpected shape."
        )

    providers = [
        _provider(item, f"normalized.providers[{index}]")
        for index, item in enumerate(_list_of(doc["providers"], "normalized.providers"))
    ]
    filters = _dict_keys(doc["export_filters"], "normalized.export_filters")
    row_counts = _dict_keys(doc["export_row_counts"], "normalized.export_row_counts")

    def model_row(item: object, field: str) -> dict[str, object]:
        row = _dict_keys(item, field)
        return {
            "provider": _provider(row.get("provider"), f"{field}.provider"),
            "model_id": _model_id(row.get("model_id"), f"{field}.model_id"),
            "canonical_model_id": _model_id_opt(
                row.get("canonical_model_id"), f"{field}.canonical_model_id"
            ),
            # display_name/description are free text and are never shown.
            "endpoints": [
                _str(ep, f"{field}.endpoints", 64)
                for ep in _list_of(row.get("endpoints", ()), f"{field}.endpoints")
            ],
            "input_modalities": [
                _str(m, f"{field}.input_modalities", 32)
                for m in _list_of(row.get("input_modalities", ()), f"{field}.input_modalities")
            ],
            "output_modalities": [
                _str(m, f"{field}.output_modalities", 32)
                for m in _list_of(row.get("output_modalities", ()), f"{field}.output_modalities")
            ],
            "context_length": _int(row.get("context_length", 0), f"{field}.context_length", 0, 10**9)
            if row.get("context_length") is not None
            else None,
            "max_output_tokens": _int(row.get("max_output_tokens", 0), f"{field}.max_output_tokens", 0, 10**9)
            if row.get("max_output_tokens") is not None
            else None,
            "knowledge_cutoff": _str_opt(
                row.get("knowledge_cutoff"), f"{field}.knowledge_cutoff", 32
            ),
            "supports_streaming": (
                _bool(row.get("supports_streaming"), f"{field}.supports_streaming")
                if row.get("supports_streaming") is not None
                else None
            ),
            "supported_parameters": [
                _str(p, f"{field}.supported_parameters", 64)
                for p in _list_of(row.get("supported_parameters", ()), f"{field}.supported_parameters")
            ],
            "capabilities": _catalog_capabilities_map(
                row.get("capabilities", {}), f"{field}.capabilities"
            ),
            "confidence": _str(row.get("confidence"), f"{field}.confidence", 32),
        }

    def pricing_row(item: object, field: str) -> dict[str, object]:
        row = _dict_keys(item, field)
        return {
            "provider": _provider(row.get("provider"), f"{field}.provider"),
            "model_id": _model_id(row.get("model_id"), f"{field}.model_id"),
            "endpoint": _str(row.get("endpoint"), f"{field}.endpoint", 64),
            "currency": _str(row.get("currency"), f"{field}.currency", 8),
            "input_price_per_1m": _decimal_opt(row.get("input_price_per_1m"), f"{field}.input_price_per_1m"),
            "cached_input_price_per_1m": _decimal_opt(row.get("cached_input_price_per_1m"), f"{field}.cached_input_price_per_1m"),
            "output_price_per_1m": _decimal_opt(row.get("output_price_per_1m"), f"{field}.output_price_per_1m"),
            "reasoning_price_per_1m": _decimal_opt(row.get("reasoning_price_per_1m"), f"{field}.reasoning_price_per_1m"),
            "request_price": _decimal_opt(row.get("request_price"), f"{field}.request_price"),
            # source_url/source_retrieved_at/pricing_metadata/notes are
            # free-text positions and are never shown.
            "ready_for_import": _bool(row.get("ready_for_import"), f"{field}.ready_for_import"),
            "confidence": _str(row.get("confidence"), f"{field}.confidence", 32),
        }

    def route_row(item: object, field: str) -> dict[str, object]:
        row = _dict_keys(item, field)
        return {
            "requested_model": _model_id(row.get("requested_model"), f"{field}.requested_model"),
            "match_type": _str(row.get("match_type"), f"{field}.match_type", 16),
            "endpoint": _str(row.get("endpoint"), f"{field}.endpoint", 64),
            "provider": _provider(row.get("provider"), f"{field}.provider"),
            "upstream_model": _model_id(row.get("upstream_model"), f"{field}.upstream_model"),
            "priority": _int(row.get("priority"), f"{field}.priority", 1, 100000),
            "enabled": _bool(row.get("enabled"), f"{field}.enabled"),
            "visible_in_models": _bool(row.get("visible_in_models"), f"{field}.visible_in_models"),
            "supports_streaming": _bool(row.get("supports_streaming"), f"{field}.supports_streaming"),
            "capabilities": _catalog_capabilities_map(
                row.get("capabilities", {}), f"{field}.capabilities"
            ),
            "ready_for_import": _bool(row.get("ready_for_import"), f"{field}.ready_for_import"),
            "confidence": _str(row.get("confidence"), f"{field}.confidence", 32),
        }

    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_NORMALIZED_JSON,
            "providers": providers,
            "fx": _fx_projection_document(doc["fx"], seed),
            "export_filters": {
                "paired_ready_only": _bool(filters.get("paired_ready_only"), "export_filters.paired_ready_only"),
                "ordinary_chat_only": _bool(filters.get("ordinary_chat_only"), "export_filters.ordinary_chat_only"),
            },
            "export_row_counts": {
                "routes": _int(row_counts.get("routes"), "export_row_counts.routes", 0, 10**9),
                "pricing": _int(row_counts.get("pricing"), "export_row_counts.pricing", 0, 10**9),
            },
            "models": [
                model_row(item, f"normalized.models[{index}]")
                for index, item in enumerate(_list_of(doc["models"], "normalized.models"))
            ],
            "pricing_candidates": [
                pricing_row(item, f"normalized.pricing[{index}]")
                for index, item in enumerate(_list_of(doc["pricing_candidates"], "normalized.pricing_candidates"))
            ],
            "route_candidates": [
                route_row(item, f"normalized.routes[{index}]")
                for index, item in enumerate(_list_of(doc["route_candidates"], "normalized.route_candidates"))
            ],
            # comparison_rows carry free-text status and are reduced to a
            # finite count only.
            "comparison_rows": {
                "count": len(_list_of(doc["comparison_rows"], "normalized.comparison_rows"))
            },
        }
    )


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _hex64(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    return value


def _output_files_list(value: object) -> list[str]:
    from slaif_gateway.services.provider_catalog_proposal import (
        SUPPORTED_OUTPUT_FILES,
    )

    if not isinstance(value, list) or set(value) != set(SUPPORTED_OUTPUT_FILES) or len(
        value
    ) != len(SUPPORTED_OUTPUT_FILES):
        raise _unsupported(
            "A demo source manifest output_files has an unexpected shape."
        )
    return list(value)


_KNOWN_EXTRACTOR_VERSION = "provider_catalog_proposal_v1"


def _extractor_version(value: object) -> str:
    # The finite known law: exactly the app's current extractor version.
    if value != _KNOWN_EXTRACTOR_VERSION:
        raise _unsupported(
            "A demo source manifest carries an unrecognized extractor version."
        )
    return value


def _san_source_manifest(raw: bytes, seed: bytes) -> bytes:
    doc = _dict_keys(_json_strict(raw), "source_manifest")
    if set(doc) != {"sources", "output_files", "fx", "generated_at", "extractor_version"}:
        raise _unsupported("A demo source manifest has an unexpected shape.")
    sources = []
    for index, item in enumerate(_list_of(doc["sources"], "source_manifest.sources")):
        row = _dict_keys(item, f"source_manifest.sources[{index}]")
        # url/content_type/warnings/snapshot_path are free-text positions
        # and are never shown; only the closed identity fields remain.
        sources.append(
            {
                "provider": _provider(row.get("provider"), f"source_manifest.sources[{index}].provider"),
                # source_type has no single closed vocabulary constant:
                # a fixed neutral value is displayed instead.
                "source_type": "known",
                "content_hash": _hex64(
                    row.get("content_hash"), f"source_manifest.sources[{index}].content_hash"
                ),
                "retrieved_at": _iso_dt(row.get("retrieved_at"), f"source_manifest.sources[{index}].retrieved_at"),
            }
        )
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_SOURCE_MANIFEST,
            "sources": sources,
            "output_files": _output_files_list(doc["output_files"]),
            "fx": _fx_projection_document(doc["fx"], seed),
            "generated_at": _iso_dt(doc["generated_at"], "source_manifest.generated_at"),
            "extractor_version": _extractor_version(doc["extractor_version"]),
        }
    )


def _san_warnings_json(raw: bytes, seed: bytes) -> bytes:
    doc = _dict_keys(_json_strict(raw), "warnings")
    if set(doc) != {"warnings"}:
        raise _unsupported("A demo warnings document has an unexpected shape.")
    warnings = []
    for index, item in enumerate(_list_of(doc["warnings"], "warnings.warnings")):
        row = _dict_keys(item, f"warnings.warnings[{index}]")
        warnings.append(
            {
                "code": _str(row.get("code"), f"warnings.warnings[{index}].code", 64),
                "provider": _provider_opt(row.get("provider"), f"warnings.warnings[{index}].provider"),
                "model_id": _model_id_opt(row.get("model_id"), f"warnings.warnings[{index}].model_id"),
                "endpoint": _str_opt(row.get("endpoint"), f"warnings.warnings[{index}].endpoint", 64),
            }
        )
    return _dump({"schema": DEMO_SCHEMA_VERSION, "kind": KIND_WARNINGS_JSON, "warnings": warnings})


_PACKAGE_MANIFEST_KEYS: frozenset[str] = frozenset(
    {
        "package_name",
        "provider",
        "endpoint_family",
        "endpoint",
        "superset_of",
        "includes_packages",
        "mode",
        "ordinary_chat_only",
        "route_rows",
        "pricing_rows",
        "warnings",
        "excluded_counts",
        "generated_at",
        "source_manifest",
        "include_deprecated",
        "include_ambiguous_capabilities",
        "recommendation",
        "safety_mode",
        "audio_input_rows",
        "audio_output_rows",
        "image_input_rows",
        "file_input_rows",
    }
)


def _san_package_manifest(raw: bytes, seed: bytes) -> bytes:
    doc = _dict_keys(_json_strict(raw), "package_manifest")
    if set(doc) != _PACKAGE_MANIFEST_KEYS:
        raise _unsupported("A demo package manifest has an unexpected shape.")
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_PACKAGE_MANIFEST,
            "package_name": _str(doc["package_name"], "package_manifest.package_name", 128),
            "provider": _provider(doc["provider"], "package_manifest.provider"),
            "endpoint_family": _str(doc["endpoint_family"], "package_manifest.endpoint_family", 64),
            "endpoint": _str(doc["endpoint"], "package_manifest.endpoint", 64),
            "superset_of": [
                _str(name, "package_manifest.superset_of", 128)
                for name in _list_of(doc["superset_of"], "package_manifest.superset_of")
            ],
            "includes_packages": [
                _str(name, "package_manifest.includes_packages", 128)
                for name in _list_of(doc["includes_packages"], "package_manifest.includes_packages")
            ],
            "mode": _str(doc["mode"], "package_manifest.mode", 32),
            "ordinary_chat_only": _bool(doc["ordinary_chat_only"], "package_manifest.ordinary_chat_only"),
            "route_rows": _int(doc["route_rows"], "package_manifest.route_rows", 0, 10**9),
            "pricing_rows": _int(doc["pricing_rows"], "package_manifest.pricing_rows", 0, 10**9),
            # warning CODE keys are map positions: totals only.
            "warnings": {"total": _nonneg_int_map_total(doc["warnings"], "package_manifest.warnings")},
            "excluded_counts": {"total": _nonneg_int_map_total(doc["excluded_counts"], "package_manifest.excluded_counts")},
            "generated_at": _iso_dt(doc["generated_at"], "package_manifest.generated_at"),
            # source_manifest is a filesystem path and recommendation is
            # free text: neither is displayed.
            "include_deprecated": _bool(doc["include_deprecated"], "package_manifest.include_deprecated"),
            "include_ambiguous_capabilities": _bool(doc["include_ambiguous_capabilities"], "package_manifest.include_ambiguous_capabilities"),
            "safety_mode": _str(doc["safety_mode"], "package_manifest.safety_mode", 32),
            "audio_input_rows": _int(doc["audio_input_rows"], "package_manifest.audio_input_rows", 0, 10**9),
            "audio_output_rows": _int(doc["audio_output_rows"], "package_manifest.audio_output_rows", 0, 10**9),
            "image_input_rows": _int(doc["image_input_rows"], "package_manifest.image_input_rows", 0, 10**9),
            "file_input_rows": _int(doc["file_input_rows"], "package_manifest.file_input_rows", 0, 10**9),
        }
    )


_LLM_PROFILE_DOC_KEYS: frozenset[str] = frozenset({"schema_version", "profiles"})


def _san_llm_profiles(raw: bytes, seed: bytes) -> bytes:
    from slaif_gateway.modules.servers.upstream_llm.profiles import LLMProfile

    doc = _dict_keys(_json_strict(raw), "llm_profiles")
    if set(doc) != _LLM_PROFILE_DOC_KEYS:
        raise _unsupported("A demo upstream LLM profile document has an unexpected shape.")
    if _int(doc["schema_version"], "llm_profiles.schema_version", 1, 1000) != 1:
        raise _unsupported("A demo upstream LLM profile document has an unexpected shape.")
    profiles = []
    items = _list_of(doc["profiles"], "llm_profiles.profiles")
    for index, item in enumerate(items):
        try:
            profile = LLMProfile.model_validate(item)
        except Exception:
            raise _unsupported(
                "A demo upstream LLM profile has an unrecognized schema."
            ) from None
        # Operator profile IDs are fictionalized per copy; the finite
        # protocol fields and the recomputed digest remain.
        profiles.append(
            {
                "profile_id": f"demo-llm-profile-{index + 1:02d}",
                "revision": profile.revision,
                "instruction_placement": profile.instruction_placement,
                "tool_encoding": profile.tool_encoding,
                "sha256": profile.sha256,
            }
        )
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_LLM_PROFILES,
            "schema_version": 1,
            "profiles": profiles,
        }
    )


_DEMO_PROFILE_ID_RE = re.compile(r"^demo-profile-[0-9a-f]{24}$")


def _san_completion_choices(raw: bytes, seed: bytes) -> bytes:
    doc = _dict_keys(_json_strict(raw), "completion_choices")
    if set(doc) != {"schema_version", "profiles"}:
        raise _unsupported(
            "A demo completion choices document has an unexpected shape."
        )
    if _int(doc["schema_version"], "completion_choices.schema_version", 1, 1000) != 1:
        raise _unsupported(
            "A demo completion choices document has an unexpected shape."
        )
    profiles = _list_of(doc["profiles"], "completion_choices.profiles")
    if len(profiles) > _COMPLETION_PROFILE_MAX_COUNT:
        raise _unsupported(
            "A demo completion choices document exceeds its count bound."
        )
    seen: set[str] = set()
    for item in profiles:
        if not isinstance(item, str) or not _DEMO_PROFILE_ID_RE.fullmatch(item):
            raise _unsupported(
                "A demo completion choices document has an unexpected shape."
            )
        if item in seen:
            raise _unsupported(
                "A demo completion choices document has an unexpected shape."
            )
        seen.add(item)
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_COMPLETION_CHOICES,
            "schema_version": 1,
            "profiles": list(profiles),
        }
    )


def _san_branding(raw: bytes, seed: bytes, slot: str | None) -> bytes:
    """Every branding slot displays the reviewed neutral substitute.

    The operator's own CSS/images are never copied into a demo artifact;
    the selected file is recorded (name/type) in the private manifest
    and replaced with the packaged SLAIF fallback the admin itself
    serves for unconfigured slots.
    """
    from slaif_gateway.web import branding as web_branding

    if slot is None or slot not in web_branding.SLOTS:
        raise _unsupported("A demo branding leaf has an unexpected slot.")
    data, _content_type = web_branding.fallback_asset(slot)
    return data


# ---------------------------------------------------------------------------
# 224-t: the finite worker-observed process-configuration projection
# ---------------------------------------------------------------------------
#
# The worker captures the EXISTING reviewed `CONFIG_INSPECTION_ALLOWLIST`
# projection from THIS worker process's cached Settings at copy time
# (`inspect_process_configuration`, "api" scope): each allowlisted
# numeric/nullable-numeric value plus its configured/default provenance.
# No wildcard model_dump, no environment scan, no file read, no secret,
# no host, no path and no free text can be represented. The worker
# process may hold different cached settings than the live API process;
# the demo page labels the display accordingly (worker-observed
# deployment configuration captured at copy time).
_PROC_CONFIG_LOGICAL_NAME = "configuration/process-configuration.json"
_PROC_CONFIG_INT_MAX = 2**63 - 1  # closed nonnegative integer ceiling
# The three default key-policy rate limits are nullable in Settings
# (None = no default); every other allowlisted setting is a plain int.
_PROC_CONFIG_NULLABLE = frozenset(
    {
        "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
        "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE",
        "DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS",
    }
)
_PROC_CONFIG_SOURCES = frozenset({"configured", "default"})


def _proc_config_entry_closed(row: object, name: str, field: str) -> None:
    """One allowlisted entry: exact keys, closed value/source types."""
    entry = _dict_keys(row, field)
    if set(entry) != {"value", "source"}:
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    value = entry["value"]
    if name in _PROC_CONFIG_NULLABLE:
        if value is not None and (
            type(value) is not int or not 0 <= value <= _PROC_CONFIG_INT_MAX
        ):
            raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    elif type(value) is not int or not 0 <= value <= _PROC_CONFIG_INT_MAX:
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")
    if entry["source"] not in _PROC_CONFIG_SOURCES:
        raise _unsupported(f"A demo file field has an unexpected shape: {field}")


def _san_process_configuration(raw: bytes, seed: bytes) -> bytes:
    """The closed typed law for the process-configuration leaf (224-t).

    The raw document is the worker producer's projection of the finite
    reviewed allowlist; the sanitizer re-proves the EXACT closed shape
    (the same 45 names, no more no less, each a nonnegative integer -
    nullable only for the three default rate limits - plus the closed
    configured/default provenance) and re-dumps the canonical display
    document. Any drift is a finite closed refusal.
    """
    doc = _json_strict(raw)
    entries = _dict_keys(doc, "process_configuration")
    if set(entries) != {"display_version", "settings"}:
        raise _unsupported(
            "A demo process configuration document has an unexpected shape."
        )
    if _int(entries["display_version"], "process_configuration.display_version", 1, 1) != 1:
        raise _unsupported(
            "A demo process configuration document has an unexpected shape."
        )
    settings = _dict_keys(entries["settings"], "process_configuration.settings")
    if set(settings) != set(CONFIG_INSPECTION_ALLOWLIST):
        raise _unsupported(
            "A demo process configuration document has an unexpected shape."
        )
    for name in CONFIG_INSPECTION_ALLOWLIST:
        _proc_config_entry_closed(
            settings[name], name, f"process_configuration.settings.{name}"
        )
    return _dump(
        {
            "schema": DEMO_SCHEMA_VERSION,
            "kind": KIND_PROCESS_CONFIG,
            "schema_version": 1,
            "settings": {
                name: {
                    "source": settings[name]["source"],
                    "value": settings[name]["value"],
                }
                for name in sorted(settings)
            },
        }
    )


_SANITIZERS: dict[str, object] = {
    KIND_REFRESH_BUNDLE: _san_refresh_bundle,
    KIND_BASELINE_DOC: _san_baseline_document,
    KIND_ROUTE_TSV: _san_route_tsv,
    KIND_PRICING_TSV: _san_pricing_tsv,
    KIND_FX_JSON: _san_fx_json,
    KIND_VALIDATION_JSON: _san_validation_json,
    KIND_REVIEW_HTML: lambda raw, seed: NEUTRAL_REVIEW_HTML,
    KIND_MARKDOWN: lambda raw, seed: NEUTRAL_MARKDOWN,
    KIND_NORMALIZED_JSON: _san_normalized_json,
    KIND_SOURCE_MANIFEST: _san_source_manifest,
    KIND_WARNINGS_JSON: _san_warnings_json,
    KIND_PACKAGE_MANIFEST: _san_package_manifest,
    KIND_LLM_PROFILES: _san_llm_profiles,
    KIND_COMPLETION_CHOICES: _san_completion_choices,
    KIND_JOB_RECORD: _sanitize_job_record,
    KIND_PROCESS_CONFIG: _san_process_configuration,
}


def _sanitize_by_kind(kind: str, raw: bytes, *, seed: bytes, slot: str | None = None) -> bytes:
    """Run the closed per-kind display sanitizer (unknown kind fails)."""
    if kind == KIND_BRANDING:
        return _san_branding(raw, seed, slot)
    sanitizer = _SANITIZERS.get(kind)
    if sanitizer is None:
        raise _unsupported("A demo file kind has no display sanitizer.")
    return sanitizer(raw, seed)  # type: ignore[operator]


def capture_catalog(capture: _Capture, seed: bytes) -> None:
    """Capture the closed catalog custody file set (worker-read-only).

    Configured = BOTH CATALOG_REFRESH_ROOT and CATALOG_REFRESH_SEAL_KEY
    set; exactly one set is a misconfiguration (unsafe). A configured
    custody must contain all four admin-addressable subdirectories
    (runs/uploads/proposals/jobs) - the product setup creates them, so a
    missing one is a MISSING configured source and fails closed. The
    source is read exclusively through held anchored descriptors (each
    held subdir fd is closed in a finally, and each run handle's parent
    descriptor is compared to the held enumeration directory) and the
    existing seal-authentication seam; nothing in the catalog custody is
    created or modified. The closed display set: seven sealed run
    CONTENT_FILES, bounded job uploads, six proposal artifacts, five
    per-package files (fixed product preset vocabulary) and the
    admin-visible job records. The seal key, manifest/receipt authority
    and locks are never captured.
    """
    config = capture.config
    if config.catalog_root is None or config.catalog_seal_key is None:
        if config.catalog_root is not None or config.catalog_seal_key is not None:
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_UNSAFE,
                "The configured catalog custody is incomplete."
            )
        capture.not_configured.append("catalog")
        capture.source_records["catalog"] = {"configured": False}
        return
    from slaif_gateway.services.catalog_refresh.sealing import (
        load_verified_capture,
    )
    from slaif_gateway.services.catalog_refresh.bundle import (
        MAX_BUNDLE_BYTES,
    )
    from slaif_gateway.services.provider_catalog_proposal import (
        OPENROUTER_PACKAGE_ORDER,
    )

    root_handle = _verify_catalog_root(config)
    try:
        try:
            key = catfs.load_seal_key_bytes(config.catalog_seal_key)
        except (OSError, CatalogRefreshSealError, ValueError):
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_UNSAFE,
                "The configured catalog seal key is not usable."
            ) from None

        runs_fd = _held_subdir(root_handle.dir_fd, "runs")
        uploads_fd = _held_subdir(root_handle.dir_fd, "uploads")
        proposals_fd = _held_subdir(root_handle.dir_fd, "proposals")
        jobs_fd = _held_subdir(root_handle.dir_fd, "jobs")
        for label, sub in (
            ("runs", runs_fd),
            ("uploads", uploads_fd),
            ("proposals", proposals_fd),
            ("jobs", jobs_fd),
        ):
            if sub is None:
                for held in (runs_fd, uploads_fd, proposals_fd, jobs_fd):
                    if held is not None:
                        os.close(held)
                raise ds.DemoSnapshotError(
                    CODE_FILES_SOURCE_MISSING,
                    f"The configured catalog custody is missing its {label} source."
                )

        runs_record: list[dict[str, object]] = []
        uploads_record: list[dict[str, object]] = []
        proposals_record: list[dict[str, object]] = []
        jobs_record: list[dict[str, object]] = []
        try:
            runs_identity = os.fstat(runs_fd)
            run_names = _listdir_held(runs_fd)
            run_dirs = [
                name
                for name in run_names
                if name and not name.startswith(".") and _RUN_ID_RE.fullmatch(name)
            ]
            for run_id in run_dirs:
                capture.deadline_check()
                run_path = config.catalog_root / "runs" / run_id
                # The enumerated entry must still be a regular directory
                # inside the HELD runs directory (no symlink swap).
                entry_st = os.stat(
                    run_id, dir_fd=runs_fd, follow_symlinks=False
                )
                if not stat_module.S_ISDIR(entry_st.st_mode):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_SOURCE_UNSUPPORTED,
                        "A configured catalog run is not a directory."
                    )
                run_handle = catfs.open_anchored_handle(run_path)
                try:
                    run_handle.assert_name_binding(str(run_path))
                    # The run entry's inode at enumeration time must equal
                    # the identity the handle actually opened: a run
                    # directory swapped within the SAME held runs/ between
                    # os.stat and open would otherwise be silently captured.
                    if (
                        entry_st.st_dev,
                        entry_st.st_ino,
                    ) != run_handle.identity:
                        raise ds.DemoSnapshotError(
                            CODE_FILES_SOURCE_CHANGED,
                            "A configured catalog run changed during capture."
                        )
                    # The run handle's PARENT descriptor must be the same
                    # directory we enumerated (identity compare through
                    # the held fds): a replaced runs/ directory cannot
                    # silently change the enumerated set.
                    parent_st = os.fstat(run_handle.parent_fd)
                    if (
                        parent_st.st_dev,
                        parent_st.st_ino,
                    ) != (runs_identity.st_dev, runs_identity.st_ino):
                        raise ds.DemoSnapshotError(
                            CODE_FILES_SOURCE_CHANGED,
                            "A configured catalog runs directory changed during capture."
                        )
                    # Bounded pre-materialization budget check on the
                    # DECLARED content size (non-mutating, read through
                    # the HELD run handle); each captured file is then
                    # admitted exactly once through the streaming seam.
                    declared = _declared_run_bytes(run_handle.dir_fd)
                    capture.budget.check_raw(declared)
                    try:
                        captured = load_verified_capture(
                            run_path, key, run_handle=run_handle
                        )
                    except (
                        CatalogRefreshSealError,
                        CatalogRefreshBlockedError,
                        OSError,
                        ValueError,
                    ):
                        raise ds.DemoSnapshotError(
                            CODE_FILES_SOURCE_UNSUPPORTED,
                            "A configured catalog run failed seal authentication."
                        ) from None
                    run_handle.assert_name_binding(str(run_path))
                    content = captured.content
                    if set(content) != set(CONTENT_FILES):
                        raise ds.DemoSnapshotError(
                            CODE_FILES_SOURCE_UNSUPPORTED,
                            "A configured catalog run carries an unexpected file set."
                        )
                    # The private manifest carries the per-copy demo run
                    # id only; the original run id is never persisted.
                    demo_run_id = _demo_run_id(seed, run_id)
                    for name in CONTENT_FILES:
                        display_name = f"catalog/runs/{demo_run_id}/{name}"
                        capture.add_display(
                            kind=_RUN_FILE_KINDS[name],
                            source="catalog",
                            source_ref=display_name,
                            logical_name=display_name,
                            raw=content[name],
                            seed=seed,
                        )
                    runs_record.append(
                        {
                            "run_id": demo_run_id,
                            "files": list(CONTENT_FILES),
                        }
                    )
                finally:
                    run_handle.close()

            job_names = _listdir_held(uploads_fd)
            for job in job_names:
                if not _JOB_LEAF_RE.fullmatch(job):
                    continue
                job_fd = os.open(
                    job,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                    dir_fd=uploads_fd,
                )
                try:
                    for name in _listdir_held(job_fd):
                        if not _UPLOAD_NAME_RE.fullmatch(name):
                            continue
                        kind = _UPLOAD_KINDS[name.split("-", 1)[0]]
                        _read_catalog_file(
                            capture,
                            job_fd,
                            name,
                            kind,
                            seed,
                            (
                                MAX_BUNDLE_BYTES
                                if name.startswith("bundle")
                                else catfs.MAX_FILE_BYTES
                            ),
                            logical_name=(
                                f"catalog/uploads/{_demo_job_id(seed, job)}/"
                                f"{_remap_upload_name(seed, name)}"
                            ),
                        )
                        uploads_record.append(
                            {
                                "job": _demo_job_id(seed, job),
                                "artifact": _remap_upload_name(seed, name),
                            }
                        )
                finally:
                    os.close(job_fd)

            job_names = _listdir_held(proposals_fd)
            for job in job_names:
                if not _JOB_LEAF_RE.fullmatch(job):
                    continue
                job_fd = os.open(
                    job,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                    dir_fd=proposals_fd,
                )
                try:
                    for name in _listdir_held(job_fd):
                        if name in _PROPOSAL_NAMES:
                            _read_catalog_file(
                                capture,
                                job_fd,
                                name,
                                _PROPOSAL_KINDS[name],
                                seed,
                                catfs.MAX_FILE_BYTES,
                                logical_name=(
                                    f"catalog/proposals/{_demo_job_id(seed, job)}/{name}"
                                ),
                            )
                            proposals_record.append(
                                {"job": _demo_job_id(seed, job), "artifact": name}
                            )
                    packages_fd = _held_subdir(job_fd, "packages")
                    if packages_fd is None:
                        continue
                    try:
                        for preset in _listdir_held(packages_fd):
                            # Fixed product preset vocabulary only; any
                            # other directory name is not an addressable
                            # package and is refused.
                            if preset not in OPENROUTER_PACKAGE_ORDER:
                                raise ds.DemoSnapshotError(
                                    CODE_FILES_SOURCE_UNSUPPORTED,
                                    "A configured catalog package preset is unknown."
                                )
                            preset_fd = os.open(
                                preset,
                                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                                dir_fd=packages_fd,
                            )
                            try:
                                for name in _listdir_held(preset_fd):
                                    if name in _PACKAGE_FILE_NAMES:
                                        _read_catalog_file(
                                            capture,
                                            preset_fd,
                                            name,
                                            _PACKAGE_KINDS[name],
                                            seed,
                                            catfs.MAX_FILE_BYTES,
                                            logical_name=(
                                                f"catalog/proposals/"
                                                f"{_demo_job_id(seed, job)}"
                                                f"/packages/{preset}/{name}"
                                            ),
                                        )
                                        proposals_record.append(
                                            {
                                                "job": _demo_job_id(seed, job),
                                                "package": preset,
                                                "artifact": name,
                                            }
                                        )
                            finally:
                                os.close(preset_fd)
                    finally:
                        os.close(packages_fd)
                finally:
                    os.close(job_fd)

            for name in _listdir_held(jobs_fd):
                if not _JOB_NAME_RE.fullmatch(name):
                    continue
                job_id = name[:32]
                _read_catalog_file(
                    capture,
                    jobs_fd,
                    name,
                    KIND_JOB_RECORD,
                    seed,
                    _JOB_RECORD_MAX_BYTES,
                    logical_name=f"catalog/jobs/{_demo_job_id(seed, job_id)}.json",
                )
                jobs_record.append(
                    {"record": f"{_demo_job_id(seed, job_id)}.json"}
                )

            capture.source_records["catalog"] = {
                "configured": True,
                "runs": runs_record,
                "uploads": uploads_record,
                "proposals": proposals_record,
                "jobs": jobs_record,
            }
        finally:
            for held in (runs_fd, uploads_fd, proposals_fd, jobs_fd):
                os.close(held)
    finally:
        root_handle.close()


def capture_branding(capture: _Capture, seed: bytes) -> None:
    """Capture the five fixed branding slots (neutralized at sanitize).

    EVERY new copy publishes the COMPLETE finite five-slot display
    set - configured or unconfigured: an unconfigured source still
    gets the five neutral-substitute leaves (the same bytes a
    configured source always shows after sanitization), so the
    session-bound demo read law is one closed shape: EXACTLY five
    ``branding/<slot>`` leaves (zero or a partial set is a damaged
    or pre-upgrade copy and the demo read refuses; older copies from
    before this law were unconfigured-without-leaves and are safely
    refused on re-login). The private source record still
    distinguishes configured from unconfigured (custody only; never
    displayed).

    Slot selection reuses the EXISTING validated resolution law
    (``web.branding.resolve_slot``): an image slot resolves to exactly
    one of its fixed ``<slot>.svg``/``<slot>.png`` files, with the
    anchored no-follow open, bounded read and content validation the
    admin actually serves. A slot that resolves keeps its selected
    bytes/content type (replaced by the neutral substitute at
    sanitize. Candidate presence is inspected through the HELD
    dirfd: only a TRULY ABSENT optional slot gets the neutral
    substitution; a PRESENT candidate that the validated resolution
    law rejects (invalid content, ambiguous dual candidate, swap)
    fails the job closed.
    """
    from slaif_gateway.web import branding as web_branding

    config = capture.config
    if config.branding_dir is None:
        capture.not_configured.append("branding")
        # 224-u: the unconfigured source still publishes the complete
        # finite five-slot neutral display set (the session-bound
        # demo read requires exactly five leaves; the private record
        # keeps the unconfigured provenance).
        slots: dict[str, dict[str, object]] = {}
        for slot in _BRANDING_SLOTS:
            capture.add_display(
                kind=KIND_BRANDING,
                source="branding",
                source_ref=f"branding:{slot}",
                logical_name=f"branding/{slot}",
                raw=b"",
                seed=seed,
                slot=slot,
            )
            slots[slot] = {
                "resolved": False,
                "file_name": None,
                "content_type": None,
                "substituted": True,
            }
        capture.source_records["branding"] = {
            "configured": False,
            "slots": slots,
        }
        return
    try:
        handle = catfs.open_anchored_handle(config.branding_dir)
    except catfs.CatalogRefreshSealError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "The configured branding directory is not usable."
        ) from None
    try:
        handle.assert_name_binding(str(config.branding_dir))
        slots: dict[str, dict[str, object]] = {}
        for slot in _BRANDING_SLOTS:
            # Candidate inspection through the HELD dirfd: an image
            # slot has the fixed names <slot>.svg / <slot>.png, the
            # CSS slot the fixed name style.css.
            candidate_names = (
                (web_branding.STYLE_CSS,)
                if slot == web_branding.STYLE_CSS
                else tuple(slot + ext for ext in web_branding.IMAGE_EXTENSIONS)
            )
            present = 0
            for candidate in candidate_names:
                try:
                    status = os.stat(
                        candidate, dir_fd=handle.dir_fd, follow_symlinks=False
                    )
                except OSError:
                    continue
                # A candidate name that EXISTS but is not a regular file
                # (symlink, special file) is a configured source in an
                # unrecognized shape: fail closed, never a fallback.
                if not stat_module.S_ISREG(status.st_mode):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_SOURCE_UNSUPPORTED,
                        "A configured branding slot candidate is not a regular file."
                    )
                present += 1
            if present == 0:
                capture.add_display(
                    kind=KIND_BRANDING,
                    source="branding",
                    source_ref=f"branding:{slot}",
                    logical_name=f"branding/{slot}",
                    raw=b"",
                    seed=seed,
                    slot=slot,
                )
                slots[slot] = {
                    "resolved": False,
                    "file_name": None,
                    "content_type": None,
                    "substituted": True,
                }
                continue
            resolved = web_branding.resolve_slot(slot, str(config.branding_dir))
            # resolve_slot reopens the configured path independently of
            # the held handle: re-assert the binding before trusting the
            # bytes it read.
            handle.assert_name_binding(str(config.branding_dir))
            if resolved is None:
                # A regular candidate exists in the held directory but
                # the validated resolution law rejected it: a configured
                # source that cannot be recognized fails closed - it is
                # never a neutral fallback.
                raise ds.DemoSnapshotError(
                    CODE_FILES_SOURCE_UNSUPPORTED,
                    "A configured branding slot file could not be validated."
                )
            if (
                resolved.file_name not in candidate_names
                or len(resolved.data) > _BRAND_SLOT_MAX_BYTES
            ):
                raise ds.DemoSnapshotError(
                    CODE_FILES_SOURCE_UNSUPPORTED,
                    "A configured branding slot resolved to an unexpected file."
                )
            capture.add_display(
                kind=KIND_BRANDING,
                source="branding",
                source_ref=f"branding:{slot}",
                logical_name=f"branding/{slot}",
                raw=resolved.data,
                seed=seed,
                slot=slot,
            )
            slots[slot] = {
                "resolved": True,
                "file_name": resolved.file_name,
                "content_type": resolved.content_type,
                "substituted": False,
            }
        capture.source_records["branding"] = {"configured": True, "slots": slots}
    finally:
        handle.close()


def capture_upstream_llm_profiles(capture: _Capture, seed: bytes) -> None:
    """Capture the optional operator upstream-LLM profiles file."""
    config = capture.config
    if config.upstream_llm_profiles_file is None:
        capture.not_configured.append("upstream_llm_profiles")
        capture.source_records["upstream_llm_profiles"] = {
            "configured": False,
            "packaged_defaults": _packaged_llm_defaults(),
        }
        return
    path = config.upstream_llm_profiles_file
    parent = path.parent
    try:
        raw = catfs.anchored_read(parent, path.name, _LLM_PROFILE_MAX_BYTES)
    except (OSError, CatalogRefreshSealError):
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_MISSING,
            "The configured upstream LLM profiles file is missing or unreadable."
        ) from None
    capture.add_display(
        kind=KIND_LLM_PROFILES,
        source="upstream_llm_profiles",
        source_ref="profiles:upstream-llm.json",
        logical_name="profiles/upstream-llm.json",
        raw=raw,
        seed=seed,
    )
    capture.source_records["upstream_llm_profiles"] = {"configured": True}


def _packaged_llm_defaults() -> list[dict[str, object]]:
    """Pinned digest reference for the packaged upstream-LLM defaults."""
    from slaif_gateway.modules.servers.upstream_llm.profiles import load_profiles

    try:
        profiles = load_profiles("")
    except Exception:
        return []
    return [
        {
            "profile_id": profile.profile_id,
            "revision": profile.revision,
            "sha256": profile.sha256,
        }
        for profile in sorted(profiles.values(), key=lambda p: p.profile_id)
    ]


def capture_completion_profiles(capture: _Capture, seed: bytes) -> None:
    """Capture the completion-profile choice projection (stems only).

    Mirrors the admin choices loader law: ``<id>.json`` stems matching
    the shared profile ID law, regular non-symlink files within the
    size bound; the profile BODIES are never read (the admin GET never
    exposes them).
    """
    config = capture.config
    if config.completion_profile_dir is None:
        capture.not_configured.append("completion_profiles")
        capture.source_records["completion_profiles"] = {"configured": False}
        return
    try:
        handle = catfs.open_anchored_handle(config.completion_profile_dir)
    except catfs.CatalogRefreshSealError:
        raise ds.DemoSnapshotError(
            CODE_FILES_SOURCE_UNSAFE,
            "The configured completion profile directory is not usable."
        ) from None
    try:
        handle.assert_name_binding(str(config.completion_profile_dir))
        stems: list[str] = []
        demo_ids: list[str] = []
        private_map: dict[str, str] = {}
        try:
            names = sorted(os.listdir(handle.dir_fd))
        except OSError:
            raise ds.DemoSnapshotError(
                CODE_FILES_SOURCE_UNSAFE,
                "The configured completion profile directory is not listable."
            ) from None
        for name in names:
            if not name.endswith(".json"):
                continue
            stem = name[: -len(".json")]
            if stem == "bindings" or not _PROFILE_ID_RE.fullmatch(stem):
                continue
            # The admin loader law skips non-regular entries (symlinks,
            # special files) - O_NOFOLLOW refuses them at open too.
            try:
                lst = os.lstat(name, dir_fd=handle.dir_fd)
            except OSError:
                continue
            if not stat_module.S_ISREG(lst.st_mode):
                continue
            # Operator directories must not offer group/world-writable
            # profile leaves (the custom-directory loader law).
            if lst.st_mode & (stat_module.S_IWGRP | stat_module.S_IWOTH):
                raise ds.DemoSnapshotError(
                    CODE_FILES_SOURCE_UNSAFE,
                    "A configured completion profile file is group or world writable."
                )
            try:
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=handle.dir_fd,
                )
            except OSError:
                # A REGULAR, non-writable profile file that cannot be
                # opened is a configured source failing closed - never a
                # silently missing choice.
                raise ds.DemoSnapshotError(
                    CODE_FILES_SOURCE_UNSAFE,
                    "A configured completion profile file is unreadable."
                ) from None
            try:
                st = os.fstat(fd)
                if (
                    not stat_module.S_ISREG(st.st_mode)
                    or st.st_size > _COMPLETION_PROFILE_MAX_BYTES
                ):
                    # Refused by the shared size/regular-file law; the
                    # admin loader skips the same file.
                    continue
            finally:
                os.close(fd)
            stems.append(stem)
            if len(stems) > _COMPLETION_PROFILE_MAX_COUNT:
                raise ds.DemoSnapshotError(
                    CODE_FILES_BUDGET_EXCEEDED,
                    "The completion profile directory exceeds its count bound."
                )
        for stem in stems:
            # SHARED 222/223 per-copy derivation (demo_profile_id): a
            # copied route's completion_service.profile uses the exact
            # same function under the same job seed, so the DB value
            # links to exactly this fictional choice.
            demo_id = demo_profile_id(seed, stem)
            demo_ids.append(demo_id)
            private_map[demo_id] = stem
        raw = json.dumps(
            {"schema_version": 1, "profiles": demo_ids},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        capture.add_display(
            kind=KIND_COMPLETION_CHOICES,
            source="completion_profiles",
            source_ref="profiles:completion-choices.json",
            logical_name="profiles/completion-choices.json",
            raw=raw,
            seed=seed,
        )
        capture.source_records["completion_profiles"] = {
            "configured": True,
            "count": len(stems),
            "ids_fictionalized": True,
            "id_map": private_map,
        }
    finally:
        handle.close()


def capture_process_configuration(capture: _Capture) -> None:
    """Capture the ONE finite worker-observed process-configuration
    projection for this copy (224-t).

    The source is the EXISTING reviewed allowlist projection
    (`inspect_process_configuration`, "api" scope) of THIS worker
    process's cached Settings: each allowlisted numeric/nullable-numeric
    value plus its configured/default provenance. There is no wildcard
    model_dump, no environment scan, no file read and no credential,
    host, path or free text in the projection. The capture time is the
    leaf's own capture time (separate from the PostgreSQL snapshot);
    the worker process may hold different cached settings than the live
    API process, and the demo page labels the display as the
    worker-observed deployment configuration captured at copy time.
    A missing, unknown, oversize or corrupt projection fails the copy
    publication closed through the shared add_display law.
    """
    from slaif_gateway.services.configuration_inspection import (
        inspect_process_configuration,
    )

    payload = inspect_process_configuration(capture.settings, process_scope="api")
    entries = payload["config"]["settings"]
    raw = json.dumps(
        {
            "display_version": 1,
            "settings": {
                name: {"value": entries[name]["value"], "source": entries[name]["source"]}
                for name in sorted(CONFIG_INSPECTION_ALLOWLIST)
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    capture.add_display(
        kind=KIND_PROCESS_CONFIG,
        source="process_configuration",
        source_ref="configuration:process-configuration",
        logical_name=_PROC_CONFIG_LOGICAL_NAME,
        raw=raw,
    )


def capture_pinned_references(capture: _Capture) -> None:
    """Record versioned identity references for packaged invariant data.

    Packaged Codex presets, the packaged Codex startup profile and the
    packaged upstream-LLM defaults are shipped application data with no
    operator/customer content: they are referenced by a pinned per-copy
    digest, never copied into a demo artifact. The operator
    PUBLIC_BASE_URL is recorded as a PRESENCE MARKER ONLY - its value is
    never copied into any artifact.
    """
    pinned: dict[str, object] = {}
    try:
        from slaif_gateway.modules.codex_profile_data import (
            list_codex_presets,
            read_codex_preset,
        )

        presets = []
        for name, _path, _profile in list_codex_presets():
            document = read_codex_preset(name)
            presets.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(document).hexdigest(),
                    "bytes": len(document),
                }
            )
        pinned["codex_presets"] = presets
    except Exception:
        pinned["codex_presets"] = []
    try:
        from slaif_gateway.modules.clients.codex_0162 import (
            bootstrap_codex_compatibility_profile,
        )

        profile = bootstrap_codex_compatibility_profile("")
        facts = profile.to_facts()
        pinned["codex_startup_profile"] = {
            "module_id": facts.get("module_id"),
            "revision": facts.get("revision"),
            "digest": facts.get("digest"),
        }
    except Exception:
        pinned["codex_startup_profile"] = None
    capture.source_records["pinned"] = pinned
    capture.source_records["public_base_url"] = {
        "configured": capture.config.public_base_url_configured
    }
    capture.source_records["codex_profile_downloads"] = {
        "base_url_configured": capture.config.public_base_url_configured,
        "note": (
            "Route Codex-profile downloads render from the 222-sanitized "
            "DB route data plus packaged registered profile data; the "
            "display base URL is the demo URL at stage 224."
        ),
    }


def capture_all(config: FileSnapshotConfig, settings: Settings, seed: bytes) -> _Capture:
    """Capture every configured file source for ONE copy job (bounded)."""
    capture = _Capture(config, settings)
    capture_catalog(capture, seed)
    capture_branding(capture, seed)
    capture_process_configuration(capture)
    capture_upstream_llm_profiles(capture, seed)
    capture_completion_profiles(capture, seed)
    capture_pinned_references(capture)
    capture.capture_finished_at = time.time()
    return capture


# ---------------------------------------------------------------------------
# Independent read-only verifier (a worker success flag is never an
# assertion: promotion happens only after this re-proves the tree)
# ---------------------------------------------------------------------------

# Absolute finite ceilings for verification allocations: the untrusted
# manifest byte counts are NEVER trusted to raise (or even set) the read
# caps; the trusted CONFIGURED caps (range-validated by
# files_config_from_settings) are enforced first, and these absolute
# ceilings bound even a misconfigured operator.
VERIFY_ABS_MAX_FILE_BYTES = 128 * 1024 * 1024
VERIFY_ABS_MAX_TOTAL_BYTES = 4096 * 1024 * 1024


def _verify_tsv_policy(kind: str, data: bytes) -> None:
    """Re-prove a stored TSV display leaf (header + neutral sentinels)."""
    from slaif_gateway.services.catalog_refresh.bundle import (
        PRICING_TSV_FIELDS,
        ROUTE_TSV_FIELDS,
    )

    if kind == KIND_ROUTE_TSV:
        header = list(ROUTE_TSV_FIELDS)
        notes_index = ROUTE_TSV_FIELDS.index("notes")
        caps_index = ROUTE_TSV_FIELDS.index("capabilities")
    elif kind == KIND_PRICING_TSV:
        header = list(PRICING_TSV_FIELDS)
        notes_index = PRICING_TSV_FIELDS.index("notes")
        caps_index = None
    else:
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED, "A display leaf has an unexpected kind."
        )
    rows = _tsv_rows_verify(data, header)
    for cells in rows:
        if cells[notes_index] != DEMO_NOTES:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED,
                "A display leaf retains a source note.",
            )
        if kind == KIND_PRICING_TSV:
            # The display TSV must carry the exact neutral sentinels:
            # an empty source_url and the fixed empty metadata object.
            if (
                cells[PRICING_TSV_FIELDS.index("source_url")] != DEMO_NOTES
                or cells[PRICING_TSV_FIELDS.index("pricing_metadata")] != "{}"
            ):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "A display leaf retains a source reference.",
                )
        else:
            # The capabilities cell must re-parse to the reviewed
            # display-form runtime capability projection.
            try:
                value = _json_strict(cells[caps_index].encode("utf-8"))
            except ds.DemoSnapshotError:
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "A display leaf row has an unexpected shape.",
                ) from None
            _v_nested_capabilities()(value)


# --- per-kind display shape specs (the verifier re-proves these) ------------

_MAX_ROWS = 10**6


def _v_unexpected() -> ds.DemoSnapshotError:
    return _unsupported("A display leaf has an unexpected shape.")


def _v_const(expected: object):
    def check(value: object) -> None:
        # Type-strict: JSON true must not satisfy an integer constant
        # (bool is an int subclass).
        if type(value) is not type(expected) or value != expected:
            raise _v_unexpected()

    return check


def _v_str(max_len: int, allow_empty: bool = False):
    def check(value: object) -> None:
        if (
            not isinstance(value, str)
            or len(value) > max_len
            or (not allow_empty and value == "")
        ):
            raise _v_unexpected()

    return check


def _v_opt_str(max_len: int):
    def check(value: object) -> None:
        if value is not None and (
            not isinstance(value, str) or len(value) > max_len
        ):
            raise _v_unexpected()

    return check


def _v_bool():
    def check(value: object) -> None:
        if not isinstance(value, bool):
            raise _v_unexpected()

    return check


def _v_opt_bool():
    def check(value: object) -> None:
        if value is not None and not isinstance(value, bool):
            raise _v_unexpected()

    return check


def _v_int(lo: int, hi: int):
    def check(value: object) -> None:
        if type(value) is not int or not lo <= value <= hi:
            raise _v_unexpected()

    return check


def _v_opt_int(lo: int, hi: int):
    def check(value: object) -> None:
        if value is not None and (
            type(value) is not int or not lo <= value <= hi
        ):
            raise _v_unexpected()

    return check


def _v_decimal(allow_negative: bool = False):
    def check(value: object) -> None:
        if not isinstance(value, str):
            raise _v_unexpected()
        try:
            number = decimal.Decimal(value)
        except (decimal.InvalidOperation, ValueError):
            raise _v_unexpected()
        if not number.is_finite() or (not allow_negative and number < 0):
            raise _v_unexpected()

    return check


def _v_opt_decimal(allow_negative: bool = False):
    base = _v_decimal(allow_negative)

    def check(value: object) -> None:
        if value is None:
            return
        base(value)

    return check


_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _v_iso():
    def check(value: object) -> None:
        if not isinstance(value, str) or not _ISO_RE.fullmatch(value):
            raise _v_unexpected()

    return check


def _v_uuid():
    def check(value: object) -> None:
        if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
            raise _v_unexpected()

    return check


def _v_model_id():
    def check(value: object) -> None:
        if not isinstance(value, str) or not _MODEL_ID_RE.fullmatch(value):
            raise _v_unexpected()

    return check


_DEMO_RUN_ID_RE = re.compile(r"^demo-run-[0-9a-f]{24}$")


def _v_demo_run_id():
    def check(value: object) -> None:
        if not isinstance(value, str) or not _DEMO_RUN_ID_RE.fullmatch(value):
            raise _v_unexpected()

    return check


def _v_str_list(max_len: int, count_max: int, allow_empty: bool = False):
    def check(value: object) -> None:
        if not isinstance(value, list) or len(value) > count_max:
            raise _v_unexpected()
        for item in value:
            if (
                not isinstance(item, str)
                or len(item) > max_len
                or (not allow_empty and item == "")
            ):
                raise _v_unexpected()

    return check


def _v_int_map(key_max: int = 64, value_max: int = 10**9):
    def check(value: object) -> None:
        if not isinstance(value, dict):
            raise _v_unexpected()
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > key_max:
                raise _v_unexpected()
            if type(item) is not int or item < 0 or item > value_max:
                raise _v_unexpected()

    return check


def _v_closed_row_counts():
    def check(value: object) -> None:
        if not isinstance(value, dict):
            raise _v_unexpected()
        for key, item in value.items():
            if key not in _BASELINE_ROW_COUNT_KEYS:
                raise _v_unexpected()
            if type(item) is not int or item < 0 or item > 10**9:
                raise _v_unexpected()

    return check


def _v_capabilities():
    def check(value: object) -> None:
        if not isinstance(value, dict):
            raise _v_unexpected()
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise _v_unexpected()
            if not isinstance(item, bool):
                raise _v_unexpected()
            if key not in _KNOWN_CHAT_CAPS:
                raise _v_unexpected()

    return check


def _v_catalog_caps():
    """Catalog CAPABILITY_KEYS law (text/streaming/...), distinct from
    the runtime chat-completion capability vocabulary used by DB routes."""
    from slaif_gateway.schemas.catalog_refresh import CAPABILITY_KEYS

    def check(value: object) -> None:
        if not isinstance(value, dict):
            raise _v_unexpected()
        for key, item in value.items():
            if type(item) is not bool or key not in CAPABILITY_KEYS:
                raise _v_unexpected()

    return check


def _v_row_spec(row_spec: dict[str, object]):
    def check(value: object) -> None:
        _v_spec(value, row_spec)

    return check


def _v_rows(row_spec: dict[str, object], count_max: int = _MAX_ROWS):
    def check(value: object) -> None:
        if not isinstance(value, list) or len(value) > count_max:
            raise _v_unexpected()
        for row in value:
            _v_row_spec(row_spec)(row)

    return check


def _v_spec(value: object, spec: dict[str, object]) -> None:
    """Exact key set, then each value against its validator."""
    if not isinstance(value, dict) or set(value) != set(spec):
        raise _v_unexpected()
    for key, validator in spec.items():
        validator(value[key])


_KNOWN_CHAT_CAPS = frozenset(
    __import__(
        "slaif_gateway.services.chat_completion_route_capabilities",
        fromlist=["KNOWN_CHAT_COMPLETION_CAPABILITIES"],
    ).KNOWN_CHAT_COMPLETION_CAPABILITIES
)

_RESEARCH_STATUSES = frozenset({"NOT_RUN", "SUCCEEDED", "FAILED", "UNAVAILABLE"})

_MATCH_TYPES = frozenset({"exact", "prefix", "glob"})


def _v_doc_refresh_bundle(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_REFRESH_BUNDLE),
            "run_id": _v_demo_run_id(),
            "generated_at": _v_iso(),
            "revision": _v_row_spec(
                {
                    "slaif_revision": _v_const(DEMO_CODE_REVISION),
                    "renderer_version": _v_str(32),
                    "policy_version": _v_int(1, 1000),
                }
            ),
            "research": _v_row_spec(
                {
                    "status": lambda v: None
                    if isinstance(v, str) and v in _RESEARCH_STATUSES
                    else (_ for _ in ()).throw(_v_unexpected())
                }
            ),
            "collection": _v_const(None),
            "policy": _v_row_spec(
                {
                    "version": _v_int(1, 1000),
                    "price_change_review": _v_decimal(),
                    "fx_change_review": _v_decimal(),
                    "source_stale_review_hours": _v_int(1, 8760),
                    "source_stale_blocked_hours": _v_int(1, 8760),
                    "fx_stale_review_days": _v_int(0, 3660),
                    "fx_stale_blocked_days": _v_int(0, 3660),
                }
            ),
            "profile": _v_row_spec(
                {
                    "name": _v_const("standard-v1"),
                    "endpoint": _v_const("/v1/chat/completions"),
                    "supports_streaming": _v_bool(),
                    "local_models_visible": _v_bool(),
                    "capability_allowlist": _v_str_list(64, 64),
                }
            ),
            "selection": _v_row_spec(
                {
                    "providers": _v_str_list(32, 8),
                    "model_include": _v_str_list(256, _MAX_ROWS),
                }
            ),
            "sources": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
            "models": _v_rows(
                {
                    "provider": lambda v: _provider(v, "bundle.model.provider"),
                    "model": _v_model_id(),
                    "context_length": _v_opt_int(1, 10**9),
                    "max_output_tokens": _v_opt_int(1, 10**9),
                    "supports_streaming": _v_bool(),
                    "capabilities": _v_catalog_caps(),
                    "deprecated": _v_bool(),
                }
            ),
            "pricing": _v_rows(
                {
                    "provider": lambda v: _provider(v, "bundle.pricing.provider"),
                    "model": _v_model_id(),
                    "endpoint": _v_const("/v1/chat/completions"),
                    "currency": _v_str(8),
                    "dimensions": _v_rows(
                        {
                            "name": _v_str(64),
                            "value": _v_opt_str(64),
                            "unit": _v_str(32),
                            "currency": _v_str(8),
                        },
                        count_max=64,
                    ),
                    "valid_from": _v_iso(),
                }
            ),
            "routes": _v_rows(
                {
                    "provider": lambda v: _provider(v, "bundle.route.provider"),
                    "requested_model": _v_model_id(),
                    "upstream_model": _v_model_id(),
                    "match_type": lambda v: None
                    if isinstance(v, str) and v in _MATCH_TYPES
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "endpoint": _v_const("/v1/chat/completions"),
                    "priority": _v_int(1, 100000),
                    "enabled": _v_bool(),
                    "visible_in_models": _v_bool(),
                    "supports_streaming": _v_bool(),
                    "capabilities": _v_catalog_caps(),
                }
            ),
            "fx": _v_rows(
                {
                    "base_currency": _v_str(8),
                    "quote_currency": _v_str(8),
                    "rate": _v_decimal(),
                    "valid_from": _v_iso(),
                    "valid_until": _v_opt_str(64),
                }
            ),
            "baseline": _v_row_spec(
                {
                    "mode": lambda v: None
                    if v in {"first_install", "db_snapshot", "exported_file"}
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "postgres_version": _v_opt_str(32),
                    "sql_checked": _v_bool(),
                    "row_counts": _v_closed_row_counts(),
                }
            ),
        },
    )


def _v_doc_completion_choices(document: dict[str, object]) -> None:
    # "demo-profile-" + 24 hex = 37 chars.
    profiles_validator = _v_str_list(48, _COMPLETION_PROFILE_MAX_COUNT)

    def profiles_check(value: object) -> None:
        profiles_validator(value)
        for item in value:  # type: ignore[union-attr]
            if not _DEMO_PROFILE_ID_RE.fullmatch(item):
                raise _v_unexpected()

    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_COMPLETION_CHOICES),
            "schema_version": _v_const(1),
            "profiles": profiles_check,
        },
    )


def _v_doc_baseline(document: dict[str, object]) -> None:
    # First-install placeholder: exactly the neutral marker, nothing
    # else; any other content falls through to the full document law.
    if (
        isinstance(document, dict)
        and set(document) == {"schema", "kind", "first_install"}
        and document["schema"] == DEMO_SCHEMA_VERSION
        and document["kind"] == KIND_BASELINE_DOC
        and document["first_install"] is True
    ):
        return
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_BASELINE_DOC),
            "exported_at": _v_iso(),
            "target": _v_row_spec({"postgres_version": _v_str(32)}),
            "sql_checked": _v_const(True),
            "counts": _v_row_spec(
                {
                    "providers": _v_int(0, _MAX_ROWS),
                    "routes": _v_int(0, _MAX_ROWS),
                    "pricing_rules": _v_int(0, _MAX_ROWS),
                    "fx_rates": _v_int(0, _MAX_ROWS),
                }
            ),
            "providers": _v_rows(
                {
                    "id": _v_uuid(),
                    "provider": _v_str(32),
                    "kind": _v_str(32),
                    "enabled": _v_bool(),
                    "timeout_seconds": _v_int(1, 10**6),
                    "max_retries": _v_int(0, 10**6),
                    "created_at": _v_iso(),
                    "updated_at": _v_iso(),
                }
            ),
            "routes": _v_rows(
                {
                    "id": _v_uuid(),
                    "requested_model": _v_model_id(),
                    "match_type": lambda v: None
                    if isinstance(v, str) and v in _MATCH_TYPES
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "endpoint": _v_str(64),
                    "provider": _v_str(32),
                    "upstream_model": _v_model_id(),
                    "priority": _v_int(1, 100000),
                    "enabled": _v_bool(),
                    "visible_in_models": _v_bool(),
                    "supports_streaming": _v_bool(),
                    "capabilities": _v_nested_capabilities(),
                    "capabilities_unrepresented": _v_bool(),
                    "capabilities_fingerprint": _v_hex64_check(),
                    "created_at": _v_iso(),
                    "updated_at": _v_iso(),
                }
            ),
            "pricing": _v_rows(
                {
                    "id": _v_uuid(),
                    "provider": _v_str(32),
                    "upstream_model": _v_model_id(),
                    "endpoint": _v_str(64),
                    "currency": _v_str(8),
                    "request_price": _v_opt_decimal(),
                    "valid_from": _v_iso(),
                    "valid_until": _v_opt_str(64),
                    "enabled": _v_bool(),
                    "cache_write_input_multiplier": _v_opt_decimal(),
                    "long_context_threshold_tokens": _v_opt_int(1, 10**9),
                    "long_context_input_multiplier": _v_opt_decimal(),
                    "long_context_output_multiplier": _v_opt_decimal(),
                    "external_tool_price_per_call": _v_opt_decimal(),
                    "external_tool_source": lambda v: None
                    if v is None or v == "openai_published_per_call"
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "pricing_metadata_unrepresented": _v_bool(),
                    "created_at": _v_iso(),
                    "updated_at": _v_iso(),
                }
            ),
            "fx": _v_rows(
                {
                    "id": _v_uuid(),
                    "base_currency": _v_str(8),
                    "quote_currency": _v_str(8),
                    "rate": _v_decimal(),
                    "valid_from": _v_iso(),
                    "valid_until": _v_opt_str(64),
                    "created_at": _v_iso(),
                }
            ),
        },
    )


# The baseline route row carries the baseline export's projected typed
# capability contract (endpoint-family blocks plus the typed codex limits
# block). Its exact structure is verified against the reviewed projection
# law: finite block names, boolean leaves, bounded integer limits.
_CAPABILITY_BOOL_BLOCK_NAMES = frozenset(
    {
        "chat_completions",
        "audio_endpoints",
        "embeddings",
        "realtime",
        "responses",
    }
)


def _v_bool_leaves(value: object) -> None:
    if not isinstance(value, dict):
        raise _v_unexpected()
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 64
            or not isinstance(item, bool)
        ):
            raise _v_unexpected()


def _v_codex_limits(value: object) -> None:
    if not isinstance(value, dict):
        raise _v_unexpected()
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 64
            or type(item) is not int
            or item < 0
            or item > 10**9
        ):
            raise _v_unexpected()


def _v_nested_capabilities() -> None:
    """Validator factory for the baseline typed capability projection."""

    def check(value: object) -> None:
        if not isinstance(value, dict):
            raise _v_unexpected()
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise _v_unexpected()
            if key in _CAPABILITY_BOOL_BLOCK_NAMES:
                _v_bool_leaves(item)
            elif key == "codex_limits":
                _v_codex_limits(item)
            elif key == "codex_compaction_compatible_route_ids":
                if (
                    not isinstance(item, list)
                    or len(item) > 128
                    or not all(
                        isinstance(x, str) and _MODEL_ID_RE.fullmatch(x)
                        for x in item
                    )
                ):
                    raise _v_unexpected()
            elif key == "external_tools":
                _v_bool_leaves(item)
            else:
                raise _v_unexpected()

    return check


def _v_hex64_check() -> None:
    def check(value: object) -> None:
        if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
            raise _v_unexpected()

    return check


_KNOWN_PROVIDERS_SET = frozenset(
    __import__(
        "slaif_gateway.schemas.catalog_refresh",
        fromlist=["KNOWN_PROVIDERS"],
    ).KNOWN_PROVIDERS
)

_SOURCE_KINDS_SET: frozenset[str] = frozenset(
    __import__(
        "slaif_gateway.schemas.catalog_refresh",
        fromlist=["SOURCE_KINDS"],
    ).SOURCE_KINDS
)


def _v_doc_validation(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_VALIDATION_JSON),
            "state": _v_str(32),
            "state_reason": _v_const(DEMO_NOTES),
            "run_id": _v_demo_run_id(),
            "generated_at": _v_iso(),
            "policy_version": _v_int(1, 1000),
            "counts": _v_row_spec({"entries": _v_int(0, _MAX_ROWS)}),
            "per_provider": lambda v: None
            if isinstance(v, dict)
            and all(
                isinstance(p, str)
                and p in _KNOWN_PROVIDERS_SET
                and isinstance(vals, dict)
                and set(vals) == {"total"}
                and isinstance(vals["total"], int)
                and 0 <= vals["total"] <= 10**9
                for p, vals in v.items()
            )
            else (_ for _ in ()).throw(_v_unexpected()),
            "dispositions": _v_rows(
                {
                    "provider": lambda v: _provider(v, "disposition.provider"),
                    "model": _v_model_id(),
                    "disposition": _v_str(32),
                }
            ),
            "price_comparisons": _v_rows(
                {
                    "provider": lambda v: _provider(v, "comparison.provider"),
                    "model": _v_model_id(),
                    "dimension": _v_str(64),
                    "old": _v_opt_decimal(),
                    "new": _v_opt_decimal(),
                    "currency_old": _v_opt_str(8),
                    "currency_new": _v_str(8),
                    "percent_change": _v_opt_decimal(allow_negative=True),
                    "state": _v_str(32),
                }
            ),
            "warnings": _v_rows(
                {
                    "severity": _v_str(16),
                    "code": _v_str(64),
                    "provider": lambda v: None
                    if v is None or (isinstance(v, str) and v in _KNOWN_PROVIDERS_SET)
                    else (_ for _ in ()).throw(_v_unexpected()),
                }
            ),
            "gates": _v_rows({"name": _v_str(64)}, count_max=1024),
            "import_gates": _v_rows(
                {
                    "kind": _v_str(32),
                    "schema_valid": _v_bool(),
                    "total_rows": _v_int(0, 10**9),
                    "valid_rows": _v_int(0, 10**9),
                    "invalid_rows": _v_int(0, 10**9),
                    "classifications": _v_row_spec(
                        {"total": _v_int(0, 10**9)}
                    ),
                    "plan_ready_rows": _v_int(0, 10**9),
                    "plan_blocked_rows": _v_int(0, 10**9),
                    "excluded_mutations": _v_int(0, 10**9),
                }
            ),
            "baseline": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
            "research": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
            "artifacts": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
            "sql_checks": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
            "baseline_metadata": _v_rows(
                {
                    "provider": lambda v: _provider(v, "baseline_meta.provider"),
                    "model": _v_model_id(),
                    "upstream_model": lambda v: None
                    if v is None or (isinstance(v, str) and _MODEL_ID_RE.fullmatch(v))
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "fields": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
                }
            ),
            "sources": _v_rows(
                {
                    "provider": lambda v: _source_provider(v, "source.provider"),
                    "model": _v_model_id(),
                    "source_kind": (
                        lambda v: None
                        if isinstance(v, str) and v in _SOURCE_KINDS_SET
                        else (_ for _ in ()).throw(_v_unexpected())
                    ),
                }
            ),
            "source_evidence": _v_const({}),
            "fx_comparisons": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
            "execution_context": _v_opt_execution_context(),
        },
    )


def _v_opt_execution_context() -> None:
    from slaif_gateway.schemas.catalog_refresh import (
        EXECUTION_CONTEXT_VERSION,
        EXTRACTOR_ID,
        POLICY_VERSION,
        RENDERER_VERSION,
        SCHEMA_VERSION,
    )

    def _choice(*allowed: object):
        def check(value: object) -> None:
            if type(value) is not str or value not in allowed:
                raise _v_unexpected()

        return check

    def check(value: object) -> None:
        if value is None:
            return
        _v_spec(
            value,
            {
                "schema_version": _v_const(EXECUTION_CONTEXT_VERSION),
                "acquisition": _choice("live_collection", "offline_supplied"),
                "generator_versions": _v_row_spec(
                    {
                        "schema_version": _v_const(SCHEMA_VERSION),
                        "renderer_version": _v_const(RENDERER_VERSION),
                        "policy_version": _v_const(POLICY_VERSION),
                        "extractor_version": _v_const(EXTRACTOR_ID),
                    }
                ),
            },
        )

    return check





def _v_fx_capture_spec() -> None:
    def check(value: object) -> None:
        if value is None:
            return
        _v_spec(
            value,
            {
                "base_currency": _v_str(8),
                "target_currency": _v_str(8),
                "fx_rate_id": _v_uuid(),
                "rate": _v_decimal(),
                "valid_from": _v_iso(),
                "valid_until": _v_opt_str(64),
                "captured_at": _v_iso(),
            },
        )

    return check


def _v_doc_normalized(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_NORMALIZED_JSON),
            "providers": (
                lambda v: None
                if isinstance(v, list)
                and len(v) <= 8
                and all(isinstance(p, str) and p in _KNOWN_PROVIDERS_SET for p in v)
                else (_ for _ in ()).throw(_v_unexpected())
            ),
            "fx": _v_fx_capture_spec(),
            "export_filters": _v_row_spec(
                {
                    "paired_ready_only": _v_bool(),
                    "ordinary_chat_only": _v_bool(),
                }
            ),
            "export_row_counts": _v_row_spec(
                {
                    "routes": _v_int(0, _MAX_ROWS),
                    "pricing": _v_int(0, _MAX_ROWS),
                }
            ),
            "models": _v_rows(
                {
                    "provider": lambda v: _provider(v, "normalized.model.provider"),
                    "model_id": _v_model_id(),
                    "canonical_model_id": lambda v: None
                    if v is None or (isinstance(v, str) and _MODEL_ID_RE.fullmatch(v))
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "endpoints": _v_str_list(64, 64),
                    "input_modalities": _v_str_list(32, 64),
                    "output_modalities": _v_str_list(32, 64),
                    "context_length": _v_opt_int(1, 10**9),
                    "max_output_tokens": _v_opt_int(1, 10**9),
                    "knowledge_cutoff": _v_opt_str(32),
                    "supports_streaming": _v_opt_bool(),
                    "supported_parameters": _v_str_list(64, 64),
                    "capabilities": _v_catalog_caps(),
                    "confidence": _v_str(32),
                }
            ),
            "pricing_candidates": _v_rows(
                {
                    "provider": lambda v: _provider(v, "normalized.pricing.provider"),
                    "model_id": _v_model_id(),
                    "endpoint": _v_str(64),
                    "currency": _v_str(8),
                    "input_price_per_1m": _v_opt_decimal(),
                    "cached_input_price_per_1m": _v_opt_decimal(),
                    "output_price_per_1m": _v_opt_decimal(),
                    "reasoning_price_per_1m": _v_opt_decimal(),
                    "request_price": _v_opt_decimal(),
                    "ready_for_import": _v_bool(),
                    "confidence": _v_str(32),
                }
            ),
            "route_candidates": _v_rows(
                {
                    "requested_model": _v_model_id(),
                    "match_type": _v_str(16),
                    "endpoint": _v_str(64),
                    "provider": lambda v: _provider(v, "normalized.route.provider"),
                    "upstream_model": _v_model_id(),
                    "priority": _v_int(1, 100000),
                    "enabled": _v_bool(),
                    "visible_in_models": _v_bool(),
                    "supports_streaming": _v_bool(),
                    "capabilities": _v_catalog_caps(),
                    "ready_for_import": _v_bool(),
                    "confidence": _v_str(32),
                }
            ),
            "comparison_rows": _v_row_spec({"count": _v_int(0, _MAX_ROWS)}),
        },
    )


def _v_doc_source_manifest(document: dict[str, object]) -> None:
    def output_files_check(value: object) -> None:
        from slaif_gateway.services.provider_catalog_proposal import (
            SUPPORTED_OUTPUT_FILES,
        )

        if (
            not isinstance(value, list)
            or set(value) != set(SUPPORTED_OUTPUT_FILES)
            or len(value) != len(SUPPORTED_OUTPUT_FILES)
        ):
            raise _v_unexpected()

    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_SOURCE_MANIFEST),
            "sources": _v_rows(
                {
                    "provider": lambda v: _provider(v, "manifest.source.provider"),
                    "source_type": _v_const("known"),
                    "content_hash": _v_hex64_check(),
                    "retrieved_at": _v_iso(),
                }
            ),
            "output_files": output_files_check,
            "fx": _v_fx_capture_spec(),
            "generated_at": _v_iso(),
            "extractor_version": _v_const(_KNOWN_EXTRACTOR_VERSION),
        },
    )


def _v_doc_warnings(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_WARNINGS_JSON),
            "warnings": _v_rows(
                {
                    "code": _v_str(64),
                    "provider": lambda v: None
                    if v is None or (isinstance(v, str) and v in _KNOWN_PROVIDERS_SET)
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "model_id": lambda v: None
                    if v is None or (isinstance(v, str) and _MODEL_ID_RE.fullmatch(v))
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "endpoint": _v_opt_str(64),
                }
            ),
        },
    )




def _v_doc_package_manifest(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_PACKAGE_MANIFEST),
            "package_name": _v_str(128),
            "provider": lambda v: _provider(v, "package_manifest.provider"),
            "endpoint_family": _v_str(64),
            "endpoint": _v_str(64),
            "superset_of": _v_str_list(128, 64),
            "includes_packages": _v_str_list(128, 64),
            "mode": _v_str(32),
            "ordinary_chat_only": _v_bool(),
            "route_rows": _v_int(0, _MAX_ROWS),
            "pricing_rows": _v_int(0, _MAX_ROWS),
            "warnings": _v_row_spec({"total": _v_int(0, 10**9)}),
            "excluded_counts": _v_row_spec({"total": _v_int(0, 10**9)}),
            "generated_at": _v_iso(),
            "include_deprecated": _v_bool(),
            "include_ambiguous_capabilities": _v_bool(),
            "safety_mode": _v_str(32),
            "audio_input_rows": _v_int(0, _MAX_ROWS),
            "audio_output_rows": _v_int(0, _MAX_ROWS),
            "image_input_rows": _v_int(0, _MAX_ROWS),
            "file_input_rows": _v_int(0, _MAX_ROWS),
        },
    )


_LLM_PLACEMENTS = frozenset({"preserve", "leading_system_developer"})
_LLM_ENCODINGS = frozenset({"preserve", "native_vllm"})


def _v_doc_llm_profiles(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_LLM_PROFILES),
            "schema_version": _v_const(1),
            "profiles": _v_rows(
                {
                    "profile_id": lambda v: None
                    if isinstance(v, str)
                    and re.fullmatch(r"demo-llm-profile-\d{2,4}", v)
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "revision": _v_int(1, 2147483647),
                    "instruction_placement": lambda v: None
                    if v in _LLM_PLACEMENTS
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "tool_encoding": lambda v: None
                    if v in _LLM_ENCODINGS
                    else (_ for _ in ()).throw(_v_unexpected()),
                    "sha256": _v_hex64_check(),
                },
                count_max=1024,
            ),
        },
    )


def _v_doc_job_record(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema_version": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const("catalog_job_record"),
            "job_id": lambda v: None
            if isinstance(v, str) and _JOB_LEAF_RE.fullmatch(v)
            else (_ for _ in ()).throw(_v_unexpected()),
            "family": lambda v: None
            if isinstance(v, str) and v in _JOB_FAMILY_VOCAB
            else (_ for _ in ()).throw(_v_unexpected()),
            "status": lambda v: None
            if isinstance(v, str) and v in _JOB_STATUS_VOCAB
            else (_ for _ in ()).throw(_v_unexpected()),
            "progress": _v_const(DEMO_NOTES),
            "dispatch": lambda v: None
            if v is None or v in _DISPATCH_VOCAB
            else (_ for _ in ()).throw(_v_unexpected()),
            "run_id": lambda v: None
            if v is None or (isinstance(v, str) and _DEMO_RUN_ID_RE.fullmatch(v))
            else (_ for _ in ()).throw(_v_unexpected()),
            "artifact_name": lambda v: None
            if v is None or (isinstance(v, str) and _UPLOAD_NAME_RE.fullmatch(v))
            else (_ for _ in ()).throw(_v_unexpected()),
            "error_code": _v_const(None),
            "cancel_requested": _v_bool(),
            "created_at": _v_iso(),
            "updated_at": _v_iso(),
        },
    )




# 224-t: the closed verifier law for the process-configuration leaf.
# The EXACT reviewed allowlist names (nothing else), each entry a
# nonnegative integer - nullable only for the three default rate
# limits - plus the closed configured provenance vocabulary.
def _proc_config_source_check(value: object) -> None:
    if value not in _PROC_CONFIG_SOURCES:
        raise _v_unexpected()


def _v_doc_process_configuration(document: dict[str, object]) -> None:
    _v_spec(
        document,
        {
            "schema": _v_const(DEMO_SCHEMA_VERSION),
            "kind": _v_const(KIND_PROCESS_CONFIG),
            "schema_version": _v_const(1),
            "settings": _v_row_spec(
                {
                    name: _v_row_spec(
                        {
                            "value": (
                                _v_opt_int(0, _PROC_CONFIG_INT_MAX)
                                if name in _PROC_CONFIG_NULLABLE
                                else _v_int(0, _PROC_CONFIG_INT_MAX)
                            ),
                            "source": _proc_config_source_check,
                        }
                    )
                    for name in CONFIG_INSPECTION_ALLOWLIST
                }
            ),
        },
    )


_JSON_DOC_VALIDATORS: dict[str, object] = {
    KIND_REFRESH_BUNDLE: _v_doc_refresh_bundle,
    KIND_COMPLETION_CHOICES: _v_doc_completion_choices,
    KIND_BASELINE_DOC: _v_doc_baseline,
    KIND_VALIDATION_JSON: _v_doc_validation,
    KIND_NORMALIZED_JSON: _v_doc_normalized,
    KIND_SOURCE_MANIFEST: _v_doc_source_manifest,
    KIND_WARNINGS_JSON: _v_doc_warnings,
    KIND_PACKAGE_MANIFEST: _v_doc_package_manifest,
    KIND_LLM_PROFILES: _v_doc_llm_profiles,
    KIND_JOB_RECORD: _v_doc_job_record,
    KIND_PROCESS_CONFIG: _v_doc_process_configuration,
}


def _verify_json_policy(kind: str, data: bytes) -> None:
    """Re-prove a stored JSON display leaf against its exact shape spec."""
    try:
        document = _json_strict(data)
    except ds.DemoSnapshotError:
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED, "A display leaf is not valid JSON."
        ) from None
    validator = _JSON_DOC_VALIDATORS.get(kind)
    if validator is None:
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED, "A display leaf kind is unverifiable."
        )
    try:
        validator(document)  # type: ignore[operator]
    except ds.DemoSnapshotError:
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED,
            "A display leaf has an unexpected shape.",
        ) from None
    except Exception:
        # Defense in depth: a validator defect (for example a type
        # mismatch against a tampered leaf) must never escape the
        # verifier with a raw traceback; the leaf stays unpublished
        # with a finite code.
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED,
            "A display leaf has an unexpected shape.",
        ) from None




def _verify_leaf_policy(kind: object, data: bytes, slot: str | None) -> None:
    """Re-prove the DISPLAY policy of one stored leaf from its bytes."""
    if not isinstance(kind, str):
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED, "A display leaf has an unexpected kind."
        )
    if kind == KIND_BRANDING:
        from slaif_gateway.web import branding as web_branding

        if slot is None or slot not in web_branding.SLOTS:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED, "A display leaf has an unexpected slot."
            )
        expected, _ct = web_branding.fallback_asset(slot)
        if data != expected:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED, "A display leaf content is unexpected."
            )
        return
    if kind == KIND_REVIEW_HTML:
        if data != NEUTRAL_REVIEW_HTML:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED, "A display leaf content is unexpected."
            )
        return
    if kind == KIND_MARKDOWN:
        if data != NEUTRAL_MARKDOWN:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED, "A display leaf content is unexpected."
            )
        return
    if kind in (KIND_ROUTE_TSV, KIND_PRICING_TSV):
        _verify_tsv_policy(kind, data)
        return
    _verify_json_policy(kind, data)


def verified_leaf_entries(
    job_dir: Path,
    config: FileSnapshotConfig,
    deadline: float,
    expected_job_identity: tuple[int, int] | None = None,
):
    """Shared read-only re-proof of the job's display tree (224-b),
    yielding ONE fully re-proven leaf at a time (224-g).

    The complete identity/inventory law: every leaf re-read through the
    anchored no-follow boundary; the files-directory identity; the
    EXACT leaf set (no foreign entry, no missing leaf, no duplicate or
    invalid name); per-leaf regular type / 0600 mode / byte count /
    inode identity; and the per-leaf digest plus display policy. It
    deliberately has NO already-verified short-circuit: a promoted
    (``FILES_VERIFIED``) tree is re-proven from the held files exactly
    as hard as a fresh one. Per-file and cumulative byte bounds come
    from the TRUSTED configured caps (bounded by the absolute
    verification ceilings); the untrusted manifest counts only ever
    shrink the read. The ABSOLUTE deadline is re-checked before every
    leaf read and before a clean return.

    ``expected_job_identity`` (224-b): when given, the freshly opened
    job-directory handle must have EXACTLY this ``(st_dev, st_ino)`` -
    the identity captured by a PRECEDING held handle on the same job
    directory. A directory swapped between the two handles (the
    per-handle name binding alone cannot detect a swap across two
    unrelated opens) is a refusal.

    Yields ``(entry, data)`` - the exact manifest entry document plus
    the re-proven leaf bytes - for each accepted leaf, one bounded
    leaf at a time (never the aggregate in memory). Any drift is a
    ``FILES_VERIFY_FAILED`` refusal.
    """

    def _deadline_check() -> None:
        if time.monotonic() > deadline:
            raise ds.DemoSnapshotError(
                CODE_FILES_BUDGET_EXCEEDED,
                "File verification exceeded its elapsed bound."
            )

    handle = catfs.open_anchored_handle(job_dir)
    try:
        handle.assert_name_binding(str(job_dir))
        if (
            expected_job_identity is not None
            and handle.identity != tuple(expected_job_identity)
        ):
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED,
                "The job directory identity drifted between reads.",
            )
        try:
            files_fd = os.open(
                FILES_DIR_NAME,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=handle.dir_fd,
            )
        except FileNotFoundError:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED, "The display files tree is missing."
            ) from None
        except OSError:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED, "The display files tree is unusable."
            ) from None
        try:
            dir_st = os.fstat(files_fd)
            if (dir_st.st_mode & 0o777) != 0o700:
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED, "The display files tree is unsafe."
                )
            try:
                manifest_raw = catfs.anchored_read_fd(
                    files_fd, FILES_MANIFEST_NAME, _FILES_MANIFEST_MAX_BYTES
                )
                doc = catfs.strict_json_bytes(manifest_raw, FILES_MANIFEST_NAME)
            except (OSError, catfs.CatalogRefreshSealError):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files manifest is unreadable.",
                ) from None
            if not isinstance(doc, dict) or not isinstance(doc.get("files"), list):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files manifest is malformed.",
                )
            identity = doc.get("files_dir_identity")
            if (
                not isinstance(identity, list)
                or len(identity) != 2
                or (dir_st.st_dev, dir_st.st_ino) != (identity[0], identity[1])
            ):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files tree identity drifted.",
                )
            entries = doc["files"]
            if not all(isinstance(entry, dict) for entry in entries):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files manifest is malformed.",
                )
            names = [entry.get("leaf") for entry in entries]
            if (
                len(set(names)) != len(names)
                or not all(
                    isinstance(n, str) and _LEAF_NAME_RE.fullmatch(n) for n in names
                )
                or len(entries) > _FILES_MAX_LEAVES
            ):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files manifest is malformed.",
                )
            expected_names = set(names) | {FILES_MANIFEST_NAME}
            try:
                actual_names = set(os.listdir(files_fd))
            except OSError:
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files tree is unusable.",
                ) from None
            if actual_names != expected_names:
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The display files tree contains unexpected entries.",
                )
            total_bytes = 0
            for entry in entries:
                _deadline_check()
                name = entry["leaf"]
                size = entry.get("bytes")
                # type() (not isinstance) rejects bool as an integer size.
                if (
                    type(size) is not int
                    or size < 0
                    or size > config.max_file_bytes
                    or size > VERIFY_ABS_MAX_FILE_BYTES
                    or total_bytes + size > config.max_total_bytes
                    or total_bytes + size > VERIFY_ABS_MAX_TOTAL_BYTES
                ):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_VERIFY_FAILED,
                        "The display files manifest is malformed.",
                    )
                try:
                    # The read cap is the trusted configured ceiling, not
                    # the untrusted manifest count: a tampered size
                    # cannot inflate the allocation.
                    data = catfs.anchored_read_fd(
                        files_fd,
                        name,
                        min(size, config.max_file_bytes, VERIFY_ABS_MAX_FILE_BYTES),
                    )
                except (OSError, catfs.CatalogRefreshSealError):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_VERIFY_FAILED,
                        "A display leaf is unreadable.",
                    ) from None
                st = os.stat(name, dir_fd=files_fd, follow_symlinks=False)
                if (
                    not stat_module.S_ISREG(st.st_mode)
                    or (st.st_mode & 0o777) != 0o600
                    or st.st_size != size
                    or len(data) != size
                ):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_VERIFY_FAILED,
                        "A display leaf failed its identity recheck.",
                    )
                recorded = entry.get("inode_identity")
                if (
                    not isinstance(recorded, list)
                    or len(recorded) != 2
                    or (st.st_dev, st.st_ino) != (recorded[0], recorded[1])
                ):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_VERIFY_FAILED,
                        "A display leaf identity drifted.",
                    )
                if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_VERIFY_FAILED,
                        "A display leaf digest drifted.",
                    )
                slot = None
                logical = entry.get("logical_name")
                if isinstance(logical, str) and logical.startswith("branding/"):
                    slot = logical.split("/", 1)[1]
                _verify_leaf_policy(entry.get("kind"), data, slot)
                total_bytes += len(data)
                yield entry, data
        finally:
            os.close(files_fd)
        handle.assert_name_binding(str(job_dir))
    finally:
        handle.close()
    _deadline_check()


def _reprove_files_tree(
    job_dir: Path,
    config: FileSnapshotConfig,
    deadline: float,
    expected_job_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Shared read-only re-proof of the job's display tree (224-b).

    Consumes the single shared re-proof
    (``verified_leaf_entries``) and returns ``(total_bytes,
    leaf_count)``; any drift inside the shared law is a
    ``FILES_VERIFY_FAILED`` refusal.
    """
    total_bytes = 0
    leaf_count = 0
    for _entry, data in verified_leaf_entries(
        job_dir, config, deadline, expected_job_identity
    ):
        total_bytes += len(data)
        leaf_count += 1
    return total_bytes, leaf_count

def verify_files(
    job_dir: Path,
    manifest: ds.SnapshotManifest,
    config: FileSnapshotConfig,
    deadline: float,
) -> None:
    """Independently re-prove the job's display tree (read-only).

    Re-reads every leaf through the anchored boundary and rechecks the
    files-directory identity, the exact leaf set (no foreign entry, no
    missing leaf), per-leaf digest / byte count / 0600 mode / inode
    identity and the per-leaf display policy. Per-file and cumulative
    byte bounds come from the TRUSTED configured caps (bounded by the
    absolute verification ceilings); the untrusted manifest counts only
    ever shrink the read. The caller's ABSOLUTE deadline is re-checked
    before every leaf read and before a clean return, so a large
    verifier re-read can never outlive the copy budget. Any drift is a
    FILES_VERIFY_FAILED refusal;
    only a fully re-proven tree allows the caller to promote the main
    manifest.
    The re-proof itself is the shared ``_reprove_files_tree`` law
    (no short-circuit inside it); this wrapper adds the 223 state
    gates and the idempotent already-verified return, then records
    the proven totals on the manifest.
    """

    if time.monotonic() > deadline:
        raise ds.DemoSnapshotError(
            CODE_FILES_BUDGET_EXCEEDED,
            "File verification exceeded its elapsed bound."
        )
    if manifest.state != ds.STATE_DB_SANITIZED_UNPUBLISHED:
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED,
            "The copy is not in the 222 verified DB state.",
        )
    if manifest.files_state == FILES_STATE_VERIFIED:
        return  # already verified: idempotent
    total_bytes, leaf_count = _reprove_files_tree(job_dir, config, deadline)
    manifest.files_bytes = total_bytes
    manifest.files_count = leaf_count


# ---------------------------------------------------------------------------
# Write phase (owned files/ subtree; the private manifest records it)
# ---------------------------------------------------------------------------

def _write_leaf_bytes(dir_fd: int, name: str, data: bytes) -> tuple[int, int]:
    """Create ONE flat 0600 leaf through a HELD directory fd (O_EXCL)."""
    if not _LEAF_NAME_RE.fullmatch(name) and name != FILES_MANIFEST_NAME:
        raise ds.DemoSnapshotError(
            CODE_FILES_WRITE_FAILED, "A display leaf name is invalid."
        )
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dir_fd
    )
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    except OSError:
        raise ds.DemoSnapshotError(
            CODE_FILES_WRITE_FAILED, "A display leaf could not be written."
        ) from None
    finally:
        os.close(fd)
    st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    if (
        not stat_module.S_ISREG(st.st_mode)
        or st.st_size != len(data)
        or (st.st_mode & 0o777) != 0o600
    ):
        raise ds.DemoSnapshotError(
            CODE_FILES_WRITE_FAILED, "A display leaf failed its identity recheck."
        )
    return st.st_dev, st.st_ino


def _write_files(job_dir: Path, capture: _Capture) -> dict[str, object]:
    """Write the sanitized leaves flat under the job's ``files/`` tree.

    The job directory is held through the anchored no-follow handle; the
    ``files`` directory is created 0700 through the held handle, every
    leaf is a flat 0600 file created O_EXCL through the held files fd,
    and the private files manifest is written LAST (so a torn write can
    never present leaves without their exact-leaf record). Returns the
    manifest document.
    """
    handle = catfs.open_anchored_handle(job_dir)
    try:
        handle.assert_name_binding(str(job_dir))
        try:
            os.mkdir(FILES_DIR_NAME, mode=0o700, dir_fd=handle.dir_fd)
        except FileExistsError:
            raise ds.DemoSnapshotError(
                CODE_FILES_WRITE_FAILED,
                "A display files directory already exists for this job.",
            ) from None
        except OSError:
            raise ds.DemoSnapshotError(
                CODE_FILES_WRITE_FAILED,
                "The display files directory could not be created.",
            ) from None
        try:
            files_fd = os.open(
                FILES_DIR_NAME,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=handle.dir_fd,
            )
        except OSError:
            raise ds.DemoSnapshotError(
                CODE_FILES_WRITE_FAILED,
                "The display files directory could not be reopened.",
            ) from None
        try:
            os.fchmod(files_fd, 0o700)
            dir_st = os.fstat(files_fd)
            files_identity = (dir_st.st_dev, dir_st.st_ino)
            entries: list[dict[str, object]] = []
            for leaf in capture.leaves:
                identity = _write_leaf_bytes(files_fd, leaf.leaf, leaf.data)
                entries.append(
                    {
                        "leaf": leaf.leaf,
                        "logical_name": leaf.logical_name,
                        "kind": leaf.kind,
                        "sha256": leaf.sha256,
                        "bytes": len(leaf.data),
                        "source": leaf.source,
                        "source_ref": leaf.source_ref,
                        "captured_at": leaf.captured_at,
                        "source_sha256": leaf.source_sha256,
                        "inode_identity": [identity[0], identity[1]],
                    }
                )
            manifest: dict[str, object] = {
                "schema_version": 1,
                "state": FILES_STATE_PENDING,
                "files_dir_identity": [files_identity[0], files_identity[1]],
                "files": entries,
                "not_configured": list(capture.not_configured),
                "source_records": dict(capture.source_records),
                "capture_started_at": capture.capture_started_at,
                "capture_finished_at": capture.capture_finished_at,
                "limits": {
                    "max_file_bytes": capture.config.max_file_bytes,
                    "max_total_bytes": capture.config.max_total_bytes,
                    "max_elapsed_seconds": capture.config.max_elapsed_seconds,
                },
            }
            _write_leaf_bytes(
                files_fd,
                FILES_MANIFEST_NAME,
                (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"),
            )
            os.fsync(files_fd)
        finally:
            os.close(files_fd)
        os.fsync(handle.dir_fd)
        handle.assert_name_binding(str(job_dir))
    finally:
        handle.close()
    return manifest


# ---------------------------------------------------------------------------
# Files job (one bounded run over the 222 verified copies)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FilesJobResult:
    """Safe fixed-vocabulary result of one files job run.

    ``failure_code`` is the safe finite code of the FIRST failed copy
    (per-copy codes also live in the private custody manifests).
    """

    state: str
    copies_files_verified: int
    copies_failed: int
    elapsed_ms: int
    failure_code: str | None = None


def _fail_copy(job_dir: Path, manifest: ds.SnapshotManifest, code: str) -> None:
    """Record a failed files attempt on the PRIVATE manifest.

    The main state stays ``DB_SANITIZED_UNPUBLISHED`` (the 222 copy is
    intact and addressable); the files state records the safe finite
    code so the operator can inspect and retry.
    """
    manifest.files_state = FILES_STATE_FAILED
    manifest.files_failure_code = code
    ds.write_manifest(job_dir, manifest)


def _completion_link_violations(
    db_profiles: list[str], choices: frozenset[str] | None
) -> int:
    """Pure link law for the combined DB/files consistency gate.

    ``choices`` is None when the completion-profile source is
    unconfigured (no choice leaf exists to link to). Every copied route
    referencing a completion profile must then link to EXACTLY one
    captured fictional choice; a missing or inconsistent link is a
    violation.
    """
    if not db_profiles:
        return 0
    if choices is None:
        return len(db_profiles)
    return sum(1 for profile in db_profiles if profile not in choices)


def _verified_choice_ids(job_dir: Path) -> frozenset[str] | None:
    """Choices derived from the VERIFIED stored completion-choices leaf.

    Publication must prove the actual displayed bytes: the id set comes
    from the stored leaf under the verified tree (read through the
    anchored boundary), not from the worker's in-memory capture. Returns
    None when the source was unconfigured (no choices leaf exists).
    Any absence, tamper or shape drift is FILES_VERIFY_FAILED.
    """
    handle = catfs.open_anchored_handle(job_dir)
    try:
        handle.assert_name_binding(str(job_dir))
        try:
            files_fd = os.open(
                FILES_DIR_NAME,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                dir_fd=handle.dir_fd,
            )
        except OSError:
            raise ds.DemoSnapshotError(
                CODE_FILES_VERIFY_FAILED,
                "The verified files directory is not addressable."
            ) from None
        try:
            manifest_raw = catfs.anchored_read_fd(
                files_fd, FILES_MANIFEST_NAME, _FILES_MANIFEST_MAX_BYTES
            )
            doc = catfs.strict_json_bytes(manifest_raw, FILES_MANIFEST_NAME)
            if not isinstance(doc, dict) or not isinstance(doc.get("files"), list):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The files manifest shape is inconsistent."
                )
            leaf_name: str | None = None
            for entry in doc["files"]:
                if (
                    isinstance(entry, dict)
                    and entry.get("logical_name") == "profiles/completion-choices.json"
                ):
                    leaf_name = entry.get("leaf")
                    break
            if leaf_name is None:
                return None  # unconfigured source: no choices leaf
            if not isinstance(leaf_name, str):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The completion choices leaf record is inconsistent."
                )
            leaf_raw = catfs.anchored_read_fd(
                files_fd, leaf_name, _COMPLETION_PROFILE_MAX_BYTES
            )
            leaf = catfs.strict_json_bytes(leaf_raw, leaf_name)
            if (
                not isinstance(leaf, dict)
                or set(leaf) != {"schema", "kind", "schema_version", "profiles"}
                or leaf.get("schema_version") != 1
                or not isinstance(leaf.get("profiles"), list)
                or len(leaf["profiles"]) > _COMPLETION_PROFILE_MAX_COUNT
            ):
                raise ds.DemoSnapshotError(
                    CODE_FILES_VERIFY_FAILED,
                    "The completion choices leaf shape is inconsistent."
                )
            for profile in leaf["profiles"]:
                if (
                    not isinstance(profile, str)
                    or not _DEMO_PROFILE_ID_RE.fullmatch(profile)
                ):
                    raise ds.DemoSnapshotError(
                        CODE_FILES_VERIFY_FAILED,
                        "The completion choices leaf carries an unexpected id."
                    )
            return frozenset(str(profile) for profile in leaf["profiles"])
        finally:
            os.close(files_fd)
    finally:
        handle.close()


async def _copy_completion_profile_ids(
    base: ds.DemoSnapshotConfig, target_db: str, timeout: float
) -> list[str]:
    """Read-only fetch of the copied completion-service profile ids.

    Bounded: the session statement timeout AND a wait_for ceiling are
    derived from the caller's remaining copy deadline.
    """
    conn = await dss._connect_copy(
        base,
        target_db,
        readonly=True,
        statement_timeout_ms=int(max(1.0, timeout) * 1000),
    )
    try:
        rows = await asyncio.wait_for(
            conn.fetch(
                "SELECT capabilities->'completion_service'->>'profile' AS p "
                "FROM public.model_routes "
                "WHERE capabilities->'completion_service' IS NOT NULL "
                "AND capabilities->'completion_service'->>'profile' IS NOT NULL"
            ),
            timeout=timeout,
        )
    except Exception:
        await dss._close_quiet(conn)
        raise
    await dss._close_quiet(conn)
    return [str(row["p"]) for row in rows]


def _completion_link_gate(
    job_dir: Path,
    base: ds.DemoSnapshotConfig,
    target_db: str,
    copy_deadline: float,
) -> None:
    """Combined-copy gate BEFORE publication: every completion profile
    referenced by the copied routes must link to exactly one of the
    fictional choices in the VERIFIED stored leaf (same per-copy
    derivation, same job seed). A missing/inconsistent link, an
    unverifiable leaf, or any check failure raises a finite code, so an
    unverifiable copy is never published. Read-only and finite: the DB
    query is bounded by the REMAINING copy deadline and the deadline is
    re-checked after the query, not only before it."""
    if time.monotonic() > copy_deadline:
        raise ds.DemoSnapshotError(
            CODE_FILES_BUDGET_EXCEEDED,
            "The files copy exceeded its elapsed bound."
        )
    choices = _verified_choice_ids(job_dir)
    remaining = copy_deadline - time.monotonic()
    if remaining <= 1.0:
        raise ds.DemoSnapshotError(
            CODE_FILES_BUDGET_EXCEEDED,
            "The files copy exceeded its elapsed bound."
        )
    budget = min(remaining - 1.0, 30.0)
    try:
        db_profiles = asyncio.run(
            _copy_completion_profile_ids(base, target_db, budget)
        )
    except ds.DemoSnapshotError:
        raise
    except Exception:
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED,
            "The completion profile link check could not be completed."
        ) from None
    if time.monotonic() > copy_deadline:
        raise ds.DemoSnapshotError(
            CODE_FILES_BUDGET_EXCEEDED,
            "The files copy exceeded its elapsed bound."
        )
    if _completion_link_violations(db_profiles, choices):
        raise ds.DemoSnapshotError(
            CODE_FILES_VERIFY_FAILED,
            "A copied route references a completion profile that does not "
            "link to the captured demo choices."
        )


def _select_exact_files_job(
    config: FileSnapshotConfig,
    job_id: str,
) -> tuple[list[Path], str | None, bool]:
    """Resolve EXACTLY one custody job for the 224-b worker (no scan).

    Returns ``(job_dirs, error_code, already_verified)``: the single
    addressable job to process, a safe finite error code when the exact
    job is missing, inconsistent or in an unexpected state, or a
    ``already_verified`` flag when the exact job is already
    file-verified (idempotent no-op success). The job is addressed ONLY
    by its closed ``snap-<32 hex>`` name under the validated custody
    root; the manifest's own job id must agree. Unrelated pre-existing
    copies are never touched or promoted.
    """
    if not isinstance(job_id, str) or not re.fullmatch(r"snap-[0-9a-f]{32}", job_id):
        return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False
    job_dir = config.custody_dir / job_id
    manifest = ds.read_manifest(job_dir)
    if manifest is None or manifest.job_id != job_id:
        return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False
    if manifest.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED:
        if manifest.files_state == FILES_STATE_VERIFIED:
            return [], None, True
        return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False
    if manifest.state == ds.STATE_DB_SANITIZED_UNPUBLISHED:
        return [job_dir], None, False
    return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False


def run_files_job(
    config: FileSnapshotConfig,
    settings: Settings,
    *,
    job_id: str | None = None,
) -> FilesJobResult:
    """Run the bounded files stage over every 222 verified copy.

    Idempotent: already file-verified copies are skipped. Each copy gets
    capture -> write -> independent verification -> promotion under the
    custody fence, bounded by ONE absolute elapsed deadline. A failed
    copy keeps its 222 state with a safe finite files failure code and
    its partial display tree is cleaned (exact leaves only); a cleanup
    failure is reported as FILES_CLEANUP_FAILED and the artifacts are
    retained for operator inspection.

    ``job_id`` (224-b exact worker): run the files stage for EXACTLY
    that one custody job (addressed by its closed ``snap-<32 hex>``
    name, never by directory order, timestamps or target database). A
    missing, inconsistent or unexpected-state exact job is a safe
    finite failure (``EXACT_COPY_UNAVAILABLE``); an already
    file-verified exact job is an idempotent no-op success. Unrelated
    pre-existing copies are never touched or promoted.
    """
    ds.validate_custody_dir(config.custody_dir)
    # The combined DB/files link gate addresses the exact copied
    # database, so the 221 worker target configuration must already be
    # valid (it is: files_config_from_settings requires it). Validate it
    # BEFORE taking the custody fence so a config-validation failure
    # cannot leak the fence.
    base = ds.config_from_settings(settings)
    fence_fd = ds.acquire_fence(config.custody_dir)
    started = time.monotonic()
    verified = 0
    failed = 0
    first_failure_code: str | None = None
    try:
        targets: list[Path] = []
        if job_id is not None:
            targets, exact_error, already_verified = _select_exact_files_job(
                config, job_id
            )
            if exact_error is not None:
                return FilesJobResult(
                    "FAILED", 0, 1,
                    int((time.monotonic() - started) * 1000),
                    exact_error,
                )
            if already_verified:
                return FilesJobResult(
                    "FILES_VERIFIED", 0, 0,
                    int((time.monotonic() - started) * 1000),
                    None,
                )
        else:
            for job_dir in ds.list_job_dirs(config.custody_dir):
                manifest = ds.read_manifest(job_dir)
                if (
                    manifest is not None
                    and manifest.state == ds.STATE_DB_SANITIZED_UNPUBLISHED
                ):
                    targets.append(job_dir)
        for job_dir in targets:
            manifest = ds.read_manifest(job_dir)
            if manifest is None or manifest.state != ds.STATE_DB_SANITIZED_UNPUBLISHED:
                continue
            if manifest.files_state == FILES_STATE_VERIFIED:
                verified += 1
                continue
            # A previous interrupted attempt: clean the exact prior
            # display leaves before starting again.
            if manifest.files_state in (FILES_STATE_PENDING, FILES_STATE_FAILED):
                if not ds._clean_job_files(job_dir):
                    failed += 1
                    if first_failure_code is None:
                        first_failure_code = CODE_FILES_CLEANUP_FAILED
                    _fail_copy(job_dir, manifest, CODE_FILES_CLEANUP_FAILED)
                    continue
            seed = manifest.job_id.encode("utf-8")
            # ONE absolute deadline for the whole copy: capture, write
            # and verification share the same bounded budget.
            copy_deadline = time.monotonic() + config.max_elapsed_seconds

            def _copy_deadline_check() -> None:
                if time.monotonic() > copy_deadline:
                    raise ds.DemoSnapshotError(
                        CODE_FILES_BUDGET_EXCEEDED,
                        "The files copy exceeded its elapsed bound."
                    )

            try:
                capture = capture_all(config, settings, seed)
                _copy_deadline_check()
                _write_files(job_dir, capture)
                _copy_deadline_check()
                verify_files(job_dir, manifest, config, copy_deadline)
                _completion_link_gate(
                    job_dir, base, manifest.target_db, copy_deadline
                )
            except ds.DemoSnapshotError as exc:
                failed += 1
                cleanup_ok = ds._clean_job_files(job_dir)
                final_code = exc.code if cleanup_ok else CODE_FILES_CLEANUP_FAILED
                if first_failure_code is None:
                    first_failure_code = final_code
                _fail_copy(job_dir, manifest, final_code)
                continue
            # Final deadline gate immediately BEFORE the promotion write:
            # an over-budget copy is never published as verified.
            if time.monotonic() > copy_deadline:
                failed += 1
                cleanup_ok = ds._clean_job_files(job_dir)
                final_code = (
                    CODE_FILES_BUDGET_EXCEEDED
                    if cleanup_ok
                    else CODE_FILES_CLEANUP_FAILED
                )
                if first_failure_code is None:
                    first_failure_code = final_code
                _fail_copy(job_dir, manifest, final_code)
                continue
            manifest.files_state = FILES_STATE_VERIFIED
            manifest.files_failure_code = None
            manifest.files_verified_at = time.time()
            manifest.state = ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
            ds.write_manifest(job_dir, manifest)
            verified += 1
    finally:
        ds.release_fence(fence_fd)
    return FilesJobResult(
        state="FILES_VERIFIED" if failed == 0 else "FAILED",
        copies_files_verified=verified,
        copies_failed=failed,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        failure_code=first_failure_code if failed else None,
    )
