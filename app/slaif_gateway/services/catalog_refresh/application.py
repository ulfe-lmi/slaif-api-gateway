"""Shared catalog-refresh application composition (217-a: G15).

The typed collect/review/publication composition that BOTH the CLI
entrypoints and the admin-GUI worker tasks compose. Extraction of the
previously CLI-private pipeline internals; no behavior change:

- collection resolves the baseline BEFORE retrieval and runs under ONE
  collection-owned :class:`~slaif_gateway.services.catalog_refresh.sources.
  AcquisitionContext` (finite attempt/byte budgets, cooperative deadline,
  cross-phase outcome cache);
- review and collect share one deterministic finalize tail (baseline
  identity checks, recomputation, seal-key lifecycle, staged NEW-ONLY
  publication of one sealed run);
- HTTP/worker code composes these functions and never re-implements
  validation, sealing, or publication, never spawns the CLI, and never
  runs a second pipeline.

Operator-custody mode: ``existing_key_only=True`` loads the EXISTING 0600
seal key through the held key-parent descriptor (never creates, repairs,
or chmods); the default CLI mode keeps ``ensure_seal_key`` semantics.

Cancellation is cooperative and read-only: a ``cancel`` predicate is
checked at phase checkpoints (before baseline resolution, before
collection, at every retrieval phase through the existing fetch seam, and
before publication). An in-flight library operation may finish before
cancellation is observed; publication is gated so a canceled invocation
can never publish a complete-looking run.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from slaif_gateway.schemas.catalog_refresh import BaselineDocument, RefreshBundle
from slaif_gateway.services.catalog_refresh import collection as _collection
from slaif_gateway.services.catalog_refresh import sources as _sources
from slaif_gateway.services.catalog_refresh.baseline import (
    MAX_BASELINE_BYTES,
    export_baseline,
    load_baseline,
)
from slaif_gateway.services.catalog_refresh.bundle import (
    MAX_BUNDLE_BYTES,
    canonical_bundle_bytes,
    load_bundle,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    CatalogRefreshError,
    CatalogRefreshSealError,
)
from slaif_gateway.services.catalog_refresh.filesystem import (
    AnchoredDir,
    PublicationConflictError,
    cleanup_staged_directory,
    ensure_seal_key,
    load_seal_key_bytes,
    mkdir_private_child,
    open_anchored_handle,
    publish_new_only_directory,
    read_user_file,
    write_staged_file,
)
from slaif_gateway.services.catalog_refresh.policy import policy_from_document
from slaif_gateway.services.catalog_refresh.rendering import (
    build_manifest,
    esc,
    render_report,
)
from slaif_gateway.services.catalog_refresh.sealing import (
    MANIFEST_NAME,
    first_install_baseline_bytes,
    seal_run,
    verify_run,
)
from slaif_gateway.services.catalog_refresh.validation import (
    ACQUISITION_LIVE,
    ACQUISITION_OFFLINE,
    SQL_CAPTURE_DOCUMENT,
    SQL_CAPTURE_FIRST_INSTALL,
    SQL_CAPTURE_LIVE_EXPORT,
    validate_against_baseline_document,
    validation_json_bytes,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from slaif_gateway.services.catalog_refresh.research import ResearchConfig
    from slaif_gateway.services.catalog_refresh.sealing import VerifyResult
    from slaif_gateway.services.catalog_refresh.sources import AcquisitionContext

__all__ = [
    "STAGE_LINE",
    "STAGE_LINE_COLLECT",
    "STAGE_LINE_COLLECT_NOT_STARTED",
    "STAGE_LINE_COLLECT_INCOMPLETE",
    "PROFILE_STANDARD_V1",
    "SUPPORTED_PROVIDERS",
    "CANCEL_FETCH_CODE",
    "ApplicationUsageError",
    "ApplicationDataError",
    "CollectionCanceled",
    "ReviewOutcome",
    "BundleLoad",
    "assert_review_bindings",
    "check_key_containment",
    "publish_blocked_run",
    "load_bundle_bounded",
    "resolve_review_baseline",
    "resolve_collect_baseline",
    "finalize_review_pipeline",
    "run_review",
    "run_collect",
    "export_baseline_document",
    "verify_run_dir",
]

# Stage lines are RUNNER-SELECTED acquisition labels (181-i I1): they name
# the path THIS invocation actually took. A label can never claim a
# retrieval that was not performed.
STAGE_LINE = (
    "offline review: this invocation reviewed supplied bytes and performed no "
    "live retrieval; export/verify available; any sealed research facts are "
    "re-verified against the captured source bytes; apply is a separate "
    "explicit command"
)
STAGE_LINE_COLLECT = (
    "live collection: bounded official-source retrieval performed by this command, "
    "then review of the collected bundle; the isolated Codex semantic research "
    "fallback (when enabled) is part of the live collection path and its sealed "
    "facts are re-verified in this review; apply is a separate explicit command"
)
STAGE_LINE_COLLECT_NOT_STARTED = (
    "collection not started: baseline resolution failed before any retrieval; "
    "no live collection (and no research) was performed by this command; apply "
    "is a separate explicit command"
)
STAGE_LINE_COLLECT_INCOMPLETE = (
    "collection attempted and failed before completion: bounded official-source "
    "retrieval was attempted, but no complete collection was produced and no "
    "sealed collected review exists; apply is a separate explicit command"
)

PROFILE_STANDARD_V1 = "standard-v1"
SUPPORTED_PROVIDERS = ("openai", "openrouter")

# The fetch-seam code raised when the operator requested cancellation
# between retrieval phases (read-only work only; the existing seam is the
# only checkpoint mechanism - no budget reset, no transport rewrite).
CANCEL_FETCH_CODE = "collection_canceled"


class ApplicationUsageError(CatalogRefreshError):
    """Operator input conflict for the shared composition (usage error).

    Carries a stable safe ``code`` and the exact safe ``detail``; the CLI
    maps codes to its historical message text and exit semantics, the GUI
    maps them to its own guidance. Never echoes raw input.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class ApplicationDataError(CatalogRefreshError):
    """Data error for the shared composition (CLI exit-65 class).

    Unreadable/unparseable input, missing database configuration,
    seal-key problems, or output conflicts. Carries a stable safe ``code``
    and a safe ``message``; never echoes raw input.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message


class CollectionCanceled(CatalogRefreshError):
    """Cooperative cancellation observed at a phase checkpoint.

    No complete collection exists and nothing was published; the caller
    records the terminal (or, if the worker was interrupted, unconfirmed)
    canceled state. This is never a blocked run: cancellation is not a
    validation finding.
    """


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """Structured outcome of one review/collect invocation."""

    state: str  # READY | READY_WITH_WARNINGS | BLOCKED
    reason: str
    run_id: str
    run_dir: Path
    report_path: Path
    changed: int
    warnings: int
    blockers: int
    stage: str
    # Exit classification for the composing caller:
    # "ready" | "ready_with_warnings" | "blocked" | "blocked_data_error"
    exit_class: str


@dataclass(frozen=True, slots=True)
class BundleLoad:
    """Result of one bounded canonical-bundle read."""

    bundle: RefreshBundle | None
    raw: bytes | None
    blocked_code: str | None = None
    blocked_detail: str | None = None


def check_key_containment(
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
) -> None:
    """180-g (G2): the seal key must stay outside the run tree. When BOTH
    paths exist, containment is verified on the anchored (st_dev, st_ino)
    chains of the held directory descriptors — a lexical check alone could
    be raced. When either path does not exist yet, a static absolute-path
    containment check applies (the run tree is only created, anchored, at
    publication). The mutation namespaces (run root, key parent) must be
    operator-owned and not peer-writable; unsafe supplied parents fail
    closed (they are never chmod'ed). Nothing is created here."""
    if run_root_handle is not None and key_handle is not None:
        if run_root_handle.identity in key_handle.chain:
            raise ApplicationUsageError(
                "seal_key_inside_run_tree",
                "--seal-key must be outside the run directory tree",
            )
    elif seal_key_path.is_relative_to(run_root):
        raise ApplicationUsageError(
            "seal_key_inside_run_tree",
            "--seal-key must be outside the run directory tree",
        )
    if run_root_handle is not None:
        run_root_handle.assert_mutation_namespace("run root directory")
    if key_handle is not None:
        key_handle.assert_mutation_namespace("seal key parent directory")


def assert_review_bindings(
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
) -> None:
    """Lifecycle gate: the checked run-root and seal-key-parent bindings
    must still hold (hop by hop, through the held descriptors). A
    directory swapped in at ANY level — cross-phase rename included —
    voids the review: no publication, no success announcement."""
    if run_root_handle is not None:
        run_root_handle.assert_name_binding(str(run_root))
    if key_handle is not None:
        key_handle.assert_name_binding(str(seal_key_path.parent))


def _baseline_document_bytes(baseline: BaselineDocument) -> bytes:
    """Canonical JSON bytes for an exported baseline document."""
    payload = baseline.model_dump(mode="json")
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _minimal_blocked_html(
    *, run_id: str, code: str, detail: str, generated_at: str, stage: str = STAGE_LINE
) -> bytes:
    css = (
        "body{font-family:system-ui,-apple-system,sans-serif;margin:24px;color:#1a202c;"
        "line-height:1.45}.state{font-weight:600;padding:10px 14px;border:1px solid #c53030;"
        "background:#fff5f5;color:#742a2a;border-radius:6px}dl{display:grid;"
        "grid-template-columns:max-content 1fr;gap:2px 14px;font-size:.9rem;margin:12px 0}"
        "dt{font-weight:600}dd{margin:0;word-break:break-all}.muted{color:#718096}"
        "footer{margin-top:24px;color:#718096;font-size:.8rem;border-top:1px solid #e2e8f0;"
        "padding-top:8px}"
    )
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
        f"<title>SLAIF catalog refresh review — BLOCKED — {esc(run_id)}</title>",
        f"<style>{css}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>SLAIF catalog refresh review</h1>",
        f"<p class='state'><strong>BLOCKED</strong> — {esc(code)}</p>",
        "<p>No baseline comparison was performed and no import plan was produced for this run.</p>",
        "<dl>",
        f"<dt>Run ID</dt><dd>{esc(run_id)}</dd>",
        f"<dt>Blocking code</dt><dd>{esc(code)}</dd>",
        f"<dt>Detail</dt><dd>{esc(detail)}</dd>",
        f"<dt>Generated at</dt><dd>{esc(generated_at)}</dd>",
        "</dl>",
        "<p class='muted'>This minimal blocked run is not sealed: sealing requires the complete canonical input set, which was unavailable for this run.</p>",
        f"<footer>Scope: {esc(stage)}.</footer>",
        "</main>",
        "</body>",
        "</html>",
    ]
    return ("\n".join(parts) + "\n").encode("utf-8")


def _minimal_blocked_validation_json(
    *, run_id: str, code: str, detail: str, generated_at: str
) -> bytes:
    payload = {
        "state": "BLOCKED",
        "state_reason": f"{code}: {detail}",
        "code": code,
        "run_id": run_id,
        "generated_at": generated_at,
        "note": "minimal blocked run; no comparison performed; not sealed",
    }
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def publish_blocked_run(
    *,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    run_name: str,
    code: str,
    detail: str,
    stage: str = STAGE_LINE,
    generated_at: str,
    bundle_canonical: bytes | None,
) -> Path:
    """Publish a safe, unsealed BLOCKED run directory (new only, atomic).

    The small run is assembled in a private staging directory and
    published with one atomic NEW-ONLY directory rename through the
    HELD run-root handle; a failure leaves nothing at the final path.
    The checked lifecycle bindings (run root, seal-key parent) must
    still hold or the publication is refused.
    """
    files: dict[str, bytes] = {
        "REVIEW.html": _minimal_blocked_html(
            run_id=run_name, code=code, detail=detail, generated_at=generated_at, stage=stage
        ),
        "validation.json": _minimal_blocked_validation_json(
            run_id=run_name, code=code, detail=detail, generated_at=generated_at
        ),
    }
    if bundle_canonical is not None:
        files["catalog-refresh.json"] = bundle_canonical
    owns_handle = False
    if run_root_handle is None:
        run_root_handle = open_anchored_handle(run_root, create_missing=True)
        run_root_handle.assert_mutation_namespace("run root directory")
        owns_handle = True
    try:
        assert_review_bindings(run_root, seal_key_path, run_root_handle, key_handle)
    except CatalogRefreshSealError as exc:
        raise ApplicationDataError(
            "binding_changed", f"checked path binding changed; refusing to publish: {exc}"
        ) from exc
    try:
        staging_name, staging_fd, staging_identity = mkdir_private_child(
            run_root_handle.dir_fd, f".staging-{run_name}-"
        )
        created: list[str] = []
        try:
            try:
                for name in sorted(files):
                    write_staged_file(staging_fd, name, files[name], 0o644)
                    created.append(name)
                os.fchmod(staging_fd, 0o755)
                try:
                    publish_new_only_directory(
                        run_root_handle.dir_fd, staging_name, run_name, staging_identity
                    )
                except PublicationConflictError as exc:
                    raise ApplicationDataError(
                        "run_conflict",
                        f"run directory already exists; refusing to overwrite: {run_root / run_name}",
                    ) from exc
            finally:
                os.close(staging_fd)
        except BaseException:
            cleanup_staged_directory(
                run_root_handle.dir_fd, staging_name, staging_identity, created
            )
            raise
    finally:
        if owns_handle:
            run_root_handle.close()
    return run_root / run_name


def load_bundle_bounded(bundle_path: Path) -> BundleLoad:
    """Bounded canonical-bundle read through the anchored reader.

    The 8 MiB cap is enforced from the open descriptor BEFORE any content
    is allocated. Unreadable input raises :class:`ApplicationDataError`;
    unparseable input is a blocked finding (the caller publishes a minimal
    blocked run).
    """
    try:
        raw = read_user_file(Path(bundle_path), MAX_BUNDLE_BYTES)
    except CatalogRefreshSealError as exc:
        raise ApplicationDataError(
            "bundle_unreadable", f"bundle file is not readable: {bundle_path}"
        ) from exc
    try:
        return BundleLoad(bundle=load_bundle(raw), raw=raw)
    except CatalogRefreshBlockedError as exc:
        return BundleLoad(bundle=None, raw=raw, blocked_code=exc.code, blocked_detail=exc.detail)


def resolve_review_baseline(
    *,
    bundle: RefreshBundle,
    baseline_file: Path | None,
    first_install: bool,
    db_url: str | None,
    settings_database_url: "Callable[[], str | None] | None" = None,
) -> tuple[BaselineDocument | None, str]:
    """Resolve the review baseline according to the bundle's declared mode.

    ``db_url`` is the caller's EXPLICIT source (flag/form);
    ``settings_database_url`` is a LAZY getter for the
    deployment-configured DATABASE_URL. The bundle is parsed once by the
    caller and its VALIDATED ``baseline.mode`` selects the path; the
    getter is evaluated ONLY in db_snapshot mode lacking an explicit
    URL - exactly the legacy resolution point. Offline modes
    (first_install, exported_file) and explicit-URL reviews never
    evaluate it, so no settings/database configuration is consulted for
    them. Returns ``(baseline_doc, sql_capture)`` where ``sql_capture``
    is the ACTUAL path this invocation took (checked against the
    declared mode inside validation). Raises
    :class:`ApplicationUsageError` for mode/source conflicts and
    :class:`ApplicationDataError` for data failures. A failed live export
    raises :class:`CatalogRefreshBlockedError` (the caller publishes a
    blocked run).
    """
    mode = bundle.baseline.mode
    if mode == "first_install":
        if first_install and (baseline_file is not None or db_url is not None):
            raise ApplicationUsageError(
                "first_install_conflict",
                "--first-install cannot be combined with --baseline-file or --db-url",
            )
        if baseline_file is not None or db_url is not None:
            raise ApplicationUsageError(
                "baseline_source_conflict",
                "bundle baseline mode is first_install; do not supply a baseline source",
            )
        return None, SQL_CAPTURE_FIRST_INSTALL
    if mode == "db_snapshot":
        if baseline_file is not None:
            raise ApplicationUsageError(
                "baseline_source_conflict",
                "bundle baseline mode is db_snapshot; use --db-url (or DATABASE_URL), not --baseline-file",
            )
        url = db_url
        if url is None and settings_database_url is not None:
            # Legacy LAZY fallback: the configured DATABASE_URL is
            # evaluated here, only in db_snapshot mode lacking an
            # explicit URL - never in offline modes, never before the
            # bundle's validated mode is known.
            url = settings_database_url()
        if not url:
            raise ApplicationDataError(
                "database_url_missing", "DATABASE_URL is not configured; pass --db-url"
            )
        doc = _run_async(export_baseline(url, now=datetime.now(UTC)))
        return doc, SQL_CAPTURE_LIVE_EXPORT
    # exported_file
    if db_url is not None:
        raise ApplicationUsageError(
            "baseline_source_conflict",
            "bundle baseline mode is exported_file; use --baseline-file, not --db-url",
        )
    if baseline_file is None:
        raise ApplicationDataError(
            "baseline_missing",
            "refresh bundle requires an explicit exported baseline; pass --baseline-file",
        )
    try:
        baseline_raw = read_user_file(Path(baseline_file), MAX_BASELINE_BYTES)
    except CatalogRefreshSealError as exc:
        raise ApplicationDataError(
            "baseline_unreadable", f"baseline file is not readable: {baseline_file}"
        ) from exc
    try:
        doc = load_baseline(baseline_raw)
    except CatalogRefreshBlockedError as exc:
        raise ApplicationDataError("baseline_invalid", f"baseline file invalid: {exc.code}") from exc
    return doc, SQL_CAPTURE_DOCUMENT


def resolve_collect_baseline(
    *,
    bootstrap: bool,
    baseline_file: Path | None,
    db_url: str | None,
    settings_database_url: str | None = None,
) -> tuple[str, BaselineDocument | None, str]:
    """Resolve the collect baseline BEFORE any retrieval.

    The deployment-configured ``settings_database_url`` is consulted ONLY
    on the refresh-without-exported-file path (the legacy resolution
    point); it never conflicts with bootstrap or exported-file modes.
    Returns ``(baseline_mode, baseline_doc, sql_capture)``. A failed
    live export raises :class:`CatalogRefreshBlockedError` (the caller
    publishes a blocked run with the not-started stage label).
    """
    if bootstrap:
        return "first_install", None, SQL_CAPTURE_FIRST_INSTALL
    if baseline_file is not None:
        try:
            baseline_raw = read_user_file(Path(baseline_file), MAX_BASELINE_BYTES)
        except CatalogRefreshSealError as exc:
            raise ApplicationDataError(
                "baseline_unreadable", f"baseline file is not readable: {baseline_file}"
            ) from exc
        try:
            doc = load_baseline(baseline_raw)
        except CatalogRefreshBlockedError as exc:
            raise ApplicationDataError("baseline_invalid", f"baseline file invalid: {exc.code}") from exc
        return "exported_file", doc, SQL_CAPTURE_DOCUMENT
    url = db_url or settings_database_url
    if not url:
        raise ApplicationDataError(
            "database_url_missing", "DATABASE_URL is not configured; pass --db-url"
        )
    doc = _run_async(export_baseline(url, now=datetime.now(UTC)))
    return "db_snapshot", doc, SQL_CAPTURE_LIVE_EXPORT


def _run_async(coro: Any) -> Any:
    """Run one async Core call from a synchronous composition context."""
    import asyncio

    return asyncio.run(coro)


def _check_cancel(cancel: Callable[[], bool] | None) -> None:
    if cancel is not None and cancel():
        raise CollectionCanceled("cancellation requested at a phase checkpoint")


def _cancellation_fetch(
    cancel: Callable[[], bool], fetch: Callable[..., list] | None
) -> Callable[..., list]:
    """Wrap the collection fetch seam with the phase-checkpoint gate.

    ``collect_bundle`` invokes the fetch seam once per retrieval phase;
    checking before each call is a phase-boundary cancellation checkpoint
    that uses ONLY the existing seam (no budget reset, no transport
    change, no library-internal hook).
    """
    base = fetch if fetch is not None else _sources.fetch_sources

    def wrapped(specs, *, client, context, resolve):
        _check_cancel(cancel)
        return base(specs, client=client, context=context, resolve=resolve)

    return wrapped


def finalize_review_pipeline(
    *,
    bundle: RefreshBundle,
    baseline_doc: BaselineDocument | None,
    sql_capture: str,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    stage: str = STAGE_LINE,
    acquisition: str = ACQUISITION_OFFLINE,
    existing_key_only: bool = False,
    cancel: Callable[[], bool] | None = None,
) -> ReviewOutcome:
    """Shared tail of review and collect.

    The run-root and key-parent anchored handles are held for the whole
    tail and their checked bindings are re-asserted before the seal-key
    load and before publication (180-g lifecycle gates unchanged).
    ``existing_key_only`` loads the EXISTING 0600 key through the held
    key-parent descriptor (operator-custody mode, never creates); the
    default keeps the runner-owned ``ensure_seal_key`` semantics.
    """
    # 1) Baseline identity checks (declared identity must match the resolved document).
    # 181-b (B2): the database name is compared as before, and when the
    # bundle declares explicit host/port identity fields they must match
    # too. The full target identity remains bound inside the content
    # digest (a substituted document is rejected above), so nothing is
    # weakened; the comparison is now consistent with the collector's
    # declared representation.
    if baseline_doc is not None:
        declared = bundle.baseline
        if declared.content_sha256 is not None and declared.content_sha256 != baseline_doc.content_sha256:
            return _blocked_identity(
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                bundle=bundle,
                code="baseline_identity_mismatch",
                detail="baseline content digest does not match the bundle's declared baseline identity",
                stage=stage,
            )
        if declared.target_database is not None and declared.target_database != baseline_doc.target.database:
            return _blocked_identity(
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                bundle=bundle,
                code="baseline_target_mismatch",
                detail=f"baseline target {baseline_doc.target.database!r} does not match declared {declared.target_database!r}",
                stage=stage,
            )
        if declared.target_host is not None and (
            declared.target_host != baseline_doc.target.server_host
            or declared.target_port != baseline_doc.target.server_port
        ):
            return _blocked_identity(
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                bundle=bundle,
                code="baseline_target_mismatch",
                detail=(
                    f"baseline target host:port {baseline_doc.target.server_host}:{baseline_doc.target.server_port} "
                    f"does not match declared {declared.target_host}:{declared.target_port}"
                ),
                stage=stage,
            )

    # 2) Deterministic recomputation. 181-i (I1): the acquisition scope is
    # the RUNNER-SELECTED path of THIS invocation (review = offline;
    # collect = live), never inferred from the bundle's collection field.
    policy = policy_from_document(bundle.policy)
    try:
        report, artifacts = validate_against_baseline_document(
            bundle,
            baseline_doc,
            policy,
            sql_capture=sql_capture,
            acquisition=acquisition,
        )
    except CatalogRefreshBlockedError as exc:
        return _blocked_identity(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            bundle=bundle,
            code=exc.code,
            detail=exc.detail,
            stage=stage,
        )

    # 3) Seal key: lifecycle gate (checked bindings must still hold) then
    #    load through the HELD key-parent descriptor (descriptor lineage).
    try:
        assert_review_bindings(run_root, seal_key_path, run_root_handle, key_handle)
        if existing_key_only:
            key_bytes = load_seal_key_bytes(seal_key_path, parent_handle=key_handle)
        else:
            key_bytes = ensure_seal_key(
                seal_key_path,
                key_parent_fd=key_handle.dir_fd if key_handle is not None else None,
            )
    except CatalogRefreshSealError as exc:
        raise ApplicationDataError(
            "seal_key_unsafe",
            f"checked path binding changed or seal key cannot be safely loaded: {exc}",
        ) from exc

    # 4) Build the complete run in a private staged directory, then publish
    #    it with one atomic NEW-ONLY directory operation. The run is sealed
    #    last, so a failure at any point removes the staging tree and never
    #    leaves a publicly complete-looking unsealed review at the final
    #    path. The run-root handle is held across the entire
    #    create/write/seal/publish/cleanup lifecycle; sealing consumes the
    #    SAME held staging descriptor (descriptor lineage, capture-once);
    #    failure cleanup is identity-checked through the held parent, and
    #    the mutation namespace is enforced to be operator-owned and not
    #    peer-writable, so a replaced staging entry is never published or
    #    removed.
    content: dict[str, bytes] = {
        "catalog-refresh.json": canonical_bundle_bytes(bundle),
        "catalog-baseline.json": (
            first_install_baseline_bytes()
            if baseline_doc is None
            else _baseline_document_bytes(baseline_doc)
        ),
        "routes-proposal.tsv": artifacts["routes-proposal.tsv"],
        "pricing-proposal.tsv": artifacts["pricing-proposal.tsv"],
        "fx-proposal.json": artifacts["fx-proposal.json"],
        "validation.json": validation_json_bytes(report),
        "REVIEW.html": render_report(bundle, report.to_dict()),
    }
    owns_run_handle = False
    if run_root_handle is None:
        try:
            run_root_handle = open_anchored_handle(run_root, create_missing=True)
            run_root_handle.assert_mutation_namespace("run root directory")
        except CatalogRefreshSealError as exc:
            raise ApplicationDataError(
                "run_root_unsafe", f"run root cannot be safely opened: {exc}"
            ) from exc
        owns_run_handle = True
    run_dir = run_root / bundle.run_id
    try:
        try:
            # Publication gate: a cancellation observed after validation
            # but before the atomic publish refuses publication (a
            # canceled invocation must never publish a complete run).
            _check_cancel(cancel)
            assert_review_bindings(run_root, seal_key_path, run_root_handle, key_handle)
        except CatalogRefreshSealError as exc:
            raise ApplicationDataError(
                "binding_changed",
                f"checked path binding changed; refusing to publish: {exc}",
            ) from exc
        staging_name, staging_fd, staging_identity = mkdir_private_child(
            run_root_handle.dir_fd, f".staging-{bundle.run_id}-"
        )
        created: list[str] = [*sorted(content), MANIFEST_NAME, "receipt.json"]
        try:
            try:
                for name in sorted(content):
                    write_staged_file(staging_fd, name, content[name], 0o644)
                write_staged_file(staging_fd, MANIFEST_NAME, build_manifest(content), 0o644)
                seal_run(staging_fd, key_bytes)  # receipt.json is the final file
                os.fchmod(staging_fd, 0o755)  # standard run directory mode at publication
                # FINAL publication gate: the cancel/state check is
                # synchronized with the NEW-ONLY publication itself (same
                # held staging descriptor, immediately before the atomic
                # publish) - the pre-staging checkpoint alone is not a
                # publication guarantee.
                _check_cancel(cancel)
                try:
                    publish_new_only_directory(
                        run_root_handle.dir_fd, staging_name, bundle.run_id, staging_identity
                    )
                except PublicationConflictError as exc:
                    raise ApplicationDataError(
                        "run_conflict",
                        f"run directory already exists; refusing to overwrite completed output: {run_dir}",
                    ) from exc
            finally:
                os.close(staging_fd)
        except BaseException:
            # Never leave a partial, unsealed run behind; the original
            # error is re-raised to the caller after the identity-checked
            # staging cleanup.
            cleanup_staged_directory(
                run_root_handle.dir_fd, staging_name, staging_identity, created
            )
            raise
    finally:
        if owns_run_handle:
            run_root_handle.close()

    blockers = sum(1 for warning in report.warnings if warning.severity == "BLOCKER")
    if report.state == "READY":
        exit_class = "ready"
    elif report.state == "READY_WITH_WARNINGS":
        exit_class = "ready_with_warnings"
    else:
        exit_class = "blocked"
    return ReviewOutcome(
        state=report.state,
        reason=report.state_reason,
        run_id=bundle.run_id,
        run_dir=run_dir,
        report_path=run_dir / "REVIEW.html",
        changed=report.counts.get("changed", 0),
        warnings=len(report.warnings),
        blockers=blockers,
        stage=stage,
        exit_class=exit_class,
    )


def _blocked_identity(
    *,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    bundle: RefreshBundle,
    code: str,
    detail: str,
    stage: str,
) -> ReviewOutcome:
    canonical = canonical_bundle_bytes(bundle)
    run_dir = publish_blocked_run(
        run_root=run_root,
        seal_key_path=seal_key_path,
        run_root_handle=run_root_handle,
        key_handle=key_handle,
        run_name=f"blocked-{code}-{hashlib.sha256(canonical).hexdigest()[:16]}",
        code=code,
        detail=detail,
        stage=stage,
        generated_at=bundle.generated_at.isoformat(),
        bundle_canonical=canonical,
    )
    return ReviewOutcome(
        state="BLOCKED",
        reason=f"{code}: {detail}",
        run_id=run_dir.name,
        run_dir=run_dir,
        report_path=run_dir / "REVIEW.html",
        changed=0,
        warnings=0,
        blockers=1,
        stage=stage,
        exit_class="blocked",
    )


def run_review(
    *,
    bundle_path: Path,
    baseline_file: Path | None,
    first_install: bool,
    db_url: str | None,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    existing_key_only: bool = False,
    cancel: Callable[[], bool] | None = None,
    settings_database_url: "Callable[[], str | None] | None" = None,
) -> ReviewOutcome:
    """Offline review of one supplied bundle (the ``review`` pipeline).

    ``settings_database_url`` is a LAZY getter (never a pre-read value):
    the bundle is parsed once, its validated ``baseline.mode`` selects
    the baseline path, and only a db_snapshot bundle lacking an explicit
    ``db_url`` evaluates the getter. Offline reviews (first_install,
    exported_file) and explicit-URL reviews never consult settings.

    Returns a :class:`ReviewOutcome`; an invalid bundle publishes a
    minimal blocked run with ``exit_class="blocked_data_error"`` (CLI
    exit 65). Usage conflicts raise :class:`ApplicationUsageError`, data
    errors raise :class:`ApplicationDataError`, and a failed live export
    publishes a blocked run with ``exit_class="blocked"`` (CLI exit 20).
    """
    _check_cancel(cancel)
    loaded = load_bundle_bounded(bundle_path)
    if loaded.bundle is None:
        assert loaded.raw is not None
        run_name = f"blocked-invalid-{hashlib.sha256(loaded.raw).hexdigest()[:16]}"
        run_dir = publish_blocked_run(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            run_name=run_name,
            code=loaded.blocked_code or "bundle_invalid",
            detail=loaded.blocked_detail or "",
            generated_at=datetime.now(UTC).isoformat(),
            bundle_canonical=None,
        )
        return ReviewOutcome(
            state="BLOCKED",
            reason=f"bundle invalid: {loaded.blocked_code or 'bundle_invalid'}",
            run_id=run_name,
            run_dir=run_dir,
            report_path=run_dir / "REVIEW.html",
            changed=0,
            warnings=0,
            blockers=1,
            stage=STAGE_LINE,
            exit_class="blocked_data_error",
        )
    bundle = loaded.bundle
    try:
        baseline_doc, sql_capture = resolve_review_baseline(
            bundle=bundle,
            baseline_file=baseline_file,
            first_install=first_install,
            db_url=db_url,
            settings_database_url=settings_database_url,
        )
    except CatalogRefreshBlockedError as exc:
        run_dir = publish_blocked_run(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            run_name=f"blocked-{exc.code}-{hashlib.sha256(canonical_bundle_bytes(bundle)).hexdigest()[:16]}",
            code=exc.code,
            detail=exc.detail,
            generated_at=bundle.generated_at.isoformat(),
            bundle_canonical=canonical_bundle_bytes(bundle),
        )
        return ReviewOutcome(
            state="BLOCKED",
            reason=f"{exc.code}: {exc.detail}",
            run_id=run_dir.name,
            run_dir=run_dir,
            report_path=run_dir / "REVIEW.html",
            changed=0,
            warnings=0,
            blockers=1,
            stage=STAGE_LINE,
            exit_class="blocked",
        )
    _check_cancel(cancel)
    return finalize_review_pipeline(
        bundle=bundle,
        baseline_doc=baseline_doc,
        sql_capture=sql_capture,
        run_root=run_root,
        seal_key_path=seal_key_path,
        run_root_handle=run_root_handle,
        key_handle=key_handle,
        stage=STAGE_LINE,
        acquisition=ACQUISITION_OFFLINE,
        existing_key_only=existing_key_only,
        cancel=cancel,
    )


def run_collect(
    *,
    bootstrap: bool,
    refresh: bool,
    profile: str,
    providers: tuple[str, ...],
    model_include: tuple[str, ...],
    baseline_file: Path | None,
    db_url: str | None,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    research: "ResearchConfig | None" = None,
    existing_key_only: bool = False,
    cancel: Callable[[], bool] | None = None,
    client: Any | None = None,
    fetch: Callable[..., list] | None = None,
    resolve: Callable[..., list] | None = None,
    acquisition: "AcquisitionContext | None" = None,
    settings_database_url: str | None = None,
) -> ReviewOutcome:
    """Bounded live collect + review of the collected bundle.

    The baseline is resolved BEFORE any retrieval; the whole collection
    runs under ONE collection-owned AcquisitionContext (created inside
    ``collect_bundle`` before acquisition starts unless the caller
    supplies one programmatically). Cancellation is cooperative at phase
    checkpoints (before baseline resolution, before collection, at every
    retrieval phase through the fetch seam, and before publication).

    Collection-level failures publish a minimal blocked run with the
    exact stage label of the path reached. ``client``/``fetch``/``resolve``
    /``acquisition`` are the existing programmatic injection seams used by
    qualification (synthetic official-source bytes); production callers
    omit them and get the vetted official transport.
    """
    if bootstrap == refresh:
        raise ApplicationUsageError(
            "mode_conflict", "exactly one of --bootstrap or --refresh is required"
        )
    if profile != PROFILE_STANDARD_V1:
        raise ApplicationUsageError(
            "profile_unsupported", "only the standard-v1 profile exists in this version"
        )
    provider_tuple = tuple(sorted({p.strip() for p in providers if p and p.strip()}))
    if not provider_tuple or any(p not in SUPPORTED_PROVIDERS for p in provider_tuple):
        raise ApplicationUsageError(
            "providers_invalid", "providers must be a non-empty subset of openai,openrouter"
        )
    model_include = tuple(sorted({m.strip() for m in model_include if m and m.strip()}))
    if bootstrap and (baseline_file is not None or db_url is not None):
        raise ApplicationUsageError(
            "bootstrap_baseline_conflict",
            "--bootstrap cannot be combined with --baseline-file or --db-url",
        )
    if baseline_file is not None and db_url is not None:
        raise ApplicationUsageError(
            "baseline_source_conflict", "use either --baseline-file or --db-url, not both"
        )
    if refresh and baseline_file is None and not db_url and not settings_database_url:
        raise ApplicationUsageError(
            "refresh_requires_baseline",
            "--refresh requires --baseline-file or --db-url (or DATABASE_URL)",
        )

    _check_cancel(cancel)

    # 1) Resolve the baseline BEFORE collection: the collector needs the
    #    document for refresh preservation, and the SQL capture label is
    #    the ACTUAL path this command took.
    try:
        baseline_mode, baseline_doc, sql_capture = resolve_collect_baseline(
            bootstrap=bootstrap,
            baseline_file=baseline_file,
            db_url=db_url,
            settings_database_url=settings_database_url,
        )
    except CatalogRefreshBlockedError as exc:
        digest = hashlib.sha256(f"db-export:{exc.code}".encode("utf-8")).hexdigest()[:16]
        run_dir = publish_blocked_run(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            run_name=f"blocked-{exc.code}-{digest}",
            code=exc.code,
            detail=exc.detail,
            stage=STAGE_LINE_COLLECT_NOT_STARTED,
            generated_at=datetime.now(UTC).isoformat(),
            bundle_canonical=None,
        )
        return ReviewOutcome(
            state="BLOCKED",
            reason=f"{exc.code}: {exc.detail}",
            run_id=run_dir.name,
            run_dir=run_dir,
            report_path=run_dir / "REVIEW.html",
            changed=0,
            warnings=0,
            blockers=1,
            stage=STAGE_LINE_COLLECT_NOT_STARTED,
            exit_class="blocked",
        )

    # 2) Collection: bounded official retrieval + deterministic parsing.
    # The collector measures its own start/finish window (passing a
    # pre-fetch ``now`` would date the run BEFORE the retrievals it
    # records and trip the future-timestamp gate).
    owns_client = client is None
    if owns_client:
        client = _sources.new_client()
    _fetch = _cancellation_fetch(cancel, fetch) if cancel is not None else fetch
    collection_error: tuple[str, str] | None = None
    bundle: RefreshBundle | None = None
    # Optional seams: only OVERRIDE the registered Core defaults when the
    # caller actually supplied one (or the cancellation wrapper). Passing
    # None explicitly would replace the production vetted fetch/resolver
    # defaults with None.
    collect_kwargs: dict[str, Any] = {
        "providers": provider_tuple,
        "model_include": model_include,
        "baseline_mode": baseline_mode,
        "baseline": baseline_doc,
        "client": client,
        "research": research,
    }
    if _fetch is not None:
        collect_kwargs["fetch"] = _fetch
    if resolve is not None:
        collect_kwargs["resolve"] = resolve
    if acquisition is not None:
        collect_kwargs["acquisition"] = acquisition
    try:
        try:
            bundle = _collection.collect_bundle(**collect_kwargs)
        except CatalogRefreshBlockedError as exc:
            collection_error = (exc.code, exc.detail)
        except _sources.SourceFetchError as exc:
            if exc.code == CANCEL_FETCH_CODE:
                raise CollectionCanceled(
                    "cancellation requested before a retrieval phase started"
                ) from None
            collection_error = (
                exc.code or "collection_failed",
                getattr(exc, "detail", None) or str(exc),
            )
    finally:
        if owns_client:
            client.close()
    if collection_error is not None:
        code, detail = collection_error
        # 181-b (B4): the run was published as state BLOCKED; the
        # composing caller maps exit_class to its exit semantics (the CLI
        # exits 20 - 65 is reserved for data errors where no blocked run
        # is published).
        digest = hashlib.sha256(f"{code}:{detail}".encode("utf-8")).hexdigest()[:16]
        run_dir = publish_blocked_run(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            run_name=f"blocked-{code}-{digest}",
            code=code,
            detail=detail,
            stage=STAGE_LINE_COLLECT_INCOMPLETE,
            generated_at=datetime.now(UTC).isoformat(),
            bundle_canonical=None,
        )
        return ReviewOutcome(
            state="BLOCKED",
            reason=f"collection failed: {code}: {detail}",
            run_id=run_dir.name,
            run_dir=run_dir,
            report_path=run_dir / "REVIEW.html",
            changed=0,
            warnings=0,
            blockers=1,
            stage=STAGE_LINE_COLLECT_INCOMPLETE,
            exit_class="blocked",
        )
    assert bundle is not None

    # 3-6) Shared review tail: identity checks, deterministic
    # recomputation, seal-key lifecycle, staged publish, summary.
    return finalize_review_pipeline(
        bundle=bundle,
        baseline_doc=baseline_doc,
        sql_capture=sql_capture,
        run_root=run_root,
        seal_key_path=seal_key_path,
        run_root_handle=run_root_handle,
        key_handle=key_handle,
        stage=STAGE_LINE_COLLECT,
        # 181-i (I1): only the collect path selects the acquired (live)
        # context — this invocation executed the collection path.
        acquisition=ACQUISITION_LIVE,
        existing_key_only=existing_key_only,
        cancel=cancel,
    )


def export_baseline_document(
    *, db_url: str, now: datetime | None = None
) -> BaselineDocument:
    """Read-only consistent allowlisted baseline export (no DB writes,
    never an empty bootstrap after a failed contact)."""
    if not db_url:
        raise ApplicationDataError("database_url_missing", "DATABASE_URL is not configured")
    return _run_async(export_baseline(db_url, now=now or datetime.now(UTC)))


def verify_run_dir(
    *,
    run_dir: Path,
    seal_key_path: Path,
    key_handle: "AnchoredDir | None" = None,
    run_handle: "AnchoredDir | None" = None,
) -> "VerifyResult":
    """Read-only verification of one sealed run.

    The EXISTING 0600 seal key is loaded through the held key-parent
    descriptor (never created); when the caller retains a checked
    run-directory lifecycle handle it is passed through (descriptor
    lineage - no path reopen). Never re-signs, never rewrites, never
    executes SQL.
    """
    key = load_seal_key_bytes(Path(seal_key_path).expanduser(), parent_handle=key_handle)
    return verify_run(
        Path(run_dir).expanduser(), key, run_handle=run_handle
    )
