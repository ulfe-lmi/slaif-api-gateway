"""CLI commands for the bounded catalog refresh collection and review workflow.

Scope in this version: collect (bounded live official-source collection
followed by review of the collected bundle), review (offline review of a
supplied bundle), verify, and read-only export-baseline. Live collection is
limited to the registered official catalog, pricing, and FX endpoints over
HTTPS with bounded retries, redirects, and byte budgets; there is no refresh
or apply command in this version, and supersession/apply must never be
claimed to work.

Exit codes:
- 0  review state READY
- 10 review state READY_WITH_WARNINGS
- 20 review state BLOCKED (safe blocked run published when possible)
- 30 verify: run directory failed verification
- 65 data error: unreadable/unparseable input, bad baseline file, missing
   database configuration, seal key problem, or output conflict
- 2  usage error (typer standard, e.g. contradictory options)
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from slaif_gateway.cli.common import CliError, emit_json, run_async
from slaif_gateway.schemas.catalog_refresh import BaselineDocument, RefreshBundle
from slaif_gateway.services.catalog_refresh import collection as catalog_collection
from slaif_gateway.services.catalog_refresh import sources as catalog_sources
from slaif_gateway.services.catalog_refresh.sources import SourceFetchError
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
    load_seal_key_bytes,
    mkdir_private_child,
    open_anchored_handle,
    publish_new_only_directory,
    publish_new_only_file,
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
    ensure_seal_key,
    first_install_baseline_bytes,
    seal_run,
    verify_run,
)
from slaif_gateway.services.catalog_refresh.validation import (
    SQL_CAPTURE_DOCUMENT,
    SQL_CAPTURE_FIRST_INSTALL,
    SQL_CAPTURE_LIVE_EXPORT,
    validate_against_baseline_document,
    validation_json_bytes,
)

app = typer.Typer(help="Bounded catalog refresh: collect, review, verify, export-baseline (no refresh or apply command exists in this version)")

EXIT_READY = 0
EXIT_READY_WITH_WARNINGS = 10
EXIT_BLOCKED = 20
EXIT_VERIFY_INVALID = 30
EXIT_DATA_ERROR = 65

STAGE_LINE = (
    "offline review: review/export/verify only; no refresh or apply command exists "
    "in this version"
)
STAGE_LINE_COLLECT = (
    "live collection: bounded official-source retrieval performed by this command, "
    "then review of the collected bundle; no refresh or apply command exists in this "
    "version"
)

DEFAULT_SEAL_KEY = Path("~/.local/state/slaif/catalog-refresh/seal.key")


def _baseline_document_bytes(baseline: BaselineDocument) -> bytes:
    """Canonical JSON bytes for an exported baseline document."""
    payload = baseline.model_dump(mode="json")
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _settings_database_url_configured() -> bool:
    from slaif_gateway.config import get_settings

    return bool(get_settings().DATABASE_URL)


def _settings_database_url() -> str:
    from slaif_gateway.config import get_settings

    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliError("DATABASE_URL is not configured; pass --db-url")
    return settings.DATABASE_URL


def _read_existing_seal_key(path: Path) -> bytes:
    """Read a runner-owned seal key; verify never creates keys.

    The key is loaded through the shared anchored boundary: no-follow at
    every component, regular file / 0600 / current-runner ownership / 64
    lowercase hex bytes validated on the OPENED descriptor.
    """
    try:
        return load_seal_key_bytes(Path(path).expanduser())
    except CatalogRefreshSealError as exc:
        raise CliError(str(exc)) from exc


def _minimal_blocked_html(*, run_id: str, code: str, detail: str, generated_at: str) -> bytes:
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
        "<footer>Offline scope: review/export/verify only — live source retrieval is unavailable in this version and no refresh or apply command exists in this version.</footer>",
        "</main>",
        "</body>",
        "</html>",
    ]
    return ("\n".join(parts) + "\n").encode("utf-8")


def _minimal_blocked_validation_json(*, run_id: str, code: str, detail: str, generated_at: str) -> bytes:
    payload = {
        "state": "BLOCKED",
        "state_reason": f"{code}: {detail}",
        "code": code,
        "run_id": run_id,
        "generated_at": generated_at,
        "note": "minimal blocked run; no comparison performed; not sealed",
    }
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _publish_blocked_run(
    *,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    run_name: str,
    code: str,
    detail: str,
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
        "REVIEW.html": _minimal_blocked_html(run_id=run_name, code=code, detail=detail, generated_at=generated_at),
        "validation.json": _minimal_blocked_validation_json(run_id=run_name, code=code, detail=detail, generated_at=generated_at),
    }
    if bundle_canonical is not None:
        files["catalog-refresh.json"] = bundle_canonical
    owns_handle = False
    if run_root_handle is None:
        run_root_handle = open_anchored_handle(run_root, create_missing=True)
        run_root_handle.assert_mutation_namespace("run root directory")
        owns_handle = True
    try:
        _assert_review_bindings(run_root, seal_key_path, run_root_handle, key_handle)
    except CatalogRefreshSealError as exc:
        raise CliError(f"checked path binding changed; refusing to publish: {exc}") from exc
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
                    raise CliError(
                        f"run directory already exists; refusing to overwrite: {run_root / run_name}"
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


def _emit_review_summary(
    *,
    state: str,
    reason: str,
    run_id: str,
    report_path: Path,
    run_dir: Path,
    changed: int,
    warnings: int,
    blockers: int,
    json_output: bool,
    stage: str = STAGE_LINE,
) -> None:
    summary: dict[str, Any] = {
        "state": state,
        "reason": reason,
        "run_id": run_id,
        "report": report_path.absolute().as_uri(),
        "run_dir": run_dir.absolute().as_uri(),
        "changed": changed,
        "warnings": warnings,
        "blockers": blockers,
        "stage": stage,
    }
    if json_output:
        emit_json(summary)
        return
    for key in ("state", "reason", "run_id", "report", "run_dir", "changed", "warnings", "blockers", "stage"):
        typer.echo(f"{key}: {summary[key]}")


@app.command("review")
def review_bundle(
    bundle_path: Annotated[
        Path,
        typer.Argument(help="Path to the canonical catalog-refresh.json proposal bundle."),
    ],
    baseline_file: Annotated[
        Path | None,
        typer.Option(
            "--baseline-file",
            help="Explicit exported baseline document (bundle baseline mode exported_file).",
        ),
    ] = None,
    first_install: Annotated[
        bool,
        typer.Option(
            "--first-install",
            help="Explicit first-install marker; the bundle baseline mode must be first_install.",
        ),
    ] = False,
    db_url: Annotated[
        str | None,
        typer.Option(
            "--db-url",
            help="PostgreSQL URL for a live read-only baseline export (bundle baseline mode db_snapshot). Defaults to DATABASE_URL.",
        ),
    ] = None,
    run_root: Annotated[
        Path,
        typer.Option("--run-root", help="Root directory for sealed run output."),
    ] = Path("catalog-refresh-runs"),
    seal_key: Annotated[
        Path,
        typer.Option(
            "--seal-key",
            help="Runner-owned seal key file (created 0600 if missing). Must be outside the run directory.",
        ),
    ] = DEFAULT_SEAL_KEY,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a compact JSON summary instead of text."),
    ] = False,
) -> None:
    """Review one proposal bundle against a baseline and publish a sealed run.

    Exit codes: 0 READY, 10 READY_WITH_WARNINGS, 20 BLOCKED, 65 data error.
    """
    try:
        raise typer.Exit(_review_impl(
            bundle_path=bundle_path,
            baseline_file=baseline_file,
            first_install=first_install,
            db_url=db_url,
            run_root=run_root,
            seal_key=seal_key,
            json_output=json_output,
        ))
    except typer.Exit:
        raise
    except CliError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshSealError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshBlockedError as exc:
        typer.secho(f"Error: {exc.code}: {exc.detail}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc


def _open_optional_anchored_handle(path: Path) -> AnchoredDir | None:
    try:
        return open_anchored_handle(path)
    except CatalogRefreshSealError:
        return None


def _check_key_containment(
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
            raise typer.BadParameter("--seal-key must be outside the run directory tree")
    elif seal_key_path.is_relative_to(run_root):
        raise typer.BadParameter("--seal-key must be outside the run directory tree")
    if run_root_handle is not None:
        run_root_handle.assert_mutation_namespace("run root directory")
    if key_handle is not None:
        key_handle.assert_mutation_namespace("seal key parent directory")


def _assert_review_bindings(
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


def _review_impl(
    *,
    bundle_path: Path,
    baseline_file: Path | None,
    first_install: bool,
    db_url: str | None,
    run_root: Path,
    seal_key: Path,
    json_output: bool,
) -> int:
    run_root = run_root.expanduser().absolute()
    seal_key_path = Path(seal_key).expanduser().absolute()
    if first_install and (baseline_file is not None or db_url is not None):
        raise typer.BadParameter("--first-install cannot be combined with --baseline-file or --db-url")
    if baseline_file is not None and db_url is not None:
        raise typer.BadParameter("use either --baseline-file or --db-url, not both")

    # 180-g (G2): both paths are opened (never created) with the anchored
    # walk and the HELD handles are retained for the ENTIRE review
    # lifecycle (containment, key load, publication, error-report paths);
    # later gates re-assert the checked bindings before key load and
    # before every publication.
    run_root_handle = _open_optional_anchored_handle(run_root)
    key_handle = _open_optional_anchored_handle(seal_key_path.parent)
    try:
        _check_key_containment(run_root, seal_key_path, run_root_handle, key_handle)
        return _review_pipeline(
            bundle_path=bundle_path,
            baseline_file=baseline_file,
            first_install=first_install,
            db_url=db_url,
            run_root=run_root,
            seal_key_path=seal_key_path,
            json_output=json_output,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
        )
    except typer.BadParameter:
        raise
    except CatalogRefreshSealError as exc:
        raise CliError(f"refusing unsafe directory configuration: {exc}") from exc
    finally:
        if run_root_handle is not None:
            run_root_handle.close()
        if key_handle is not None:
            key_handle.close()


def _review_pipeline(
    *,
    bundle_path: Path,
    baseline_file: Path | None,
    first_install: bool,
    db_url: str | None,
    run_root: Path,
    seal_key_path: Path,
    json_output: bool,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
) -> int:
    # 1) Load the canonical bundle through the anchored bounded reader;
    #    the 8 MiB cap is enforced from the open descriptor BEFORE any
    #    content is allocated. Unparseable input gets a minimal blocked run.
    try:
        raw = read_user_file(Path(bundle_path), MAX_BUNDLE_BYTES)
    except CatalogRefreshSealError as exc:
        raise CliError(f"bundle file is not readable: {bundle_path}") from exc
    try:
        bundle = load_bundle(raw)
    except CatalogRefreshBlockedError as exc:
        run_name = f"blocked-invalid-{hashlib.sha256(raw).hexdigest()[:16]}"
        run_dir = _publish_blocked_run(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            run_name=run_name,
            code=exc.code,
            detail=exc.detail,
            generated_at=datetime.now(UTC).isoformat(),
            bundle_canonical=None,
        )
        _emit_review_summary(
            state="BLOCKED",
            reason=f"bundle invalid: {exc.code}",
            run_id=run_name,
            report_path=run_dir / "REVIEW.html",
            run_dir=run_dir,
            changed=0,
            warnings=0,
            blockers=1,
            json_output=json_output,
        )
        return EXIT_DATA_ERROR

    # 2) Resolve the baseline according to the bundle's declared mode.
    # 180-e (E5): the SQL capture is the ACTUAL path this review command took,
    # recorded as it is taken. It is checked for consistency with the bundle's
    # declared mode inside validate_bundle; a label cannot claim SQL evidence
    # this path did not produce.
    sql_capture: str
    mode = bundle.baseline.mode
    if mode == "first_install":
        if baseline_file is not None or db_url is not None:
            raise typer.BadParameter("bundle baseline mode is first_install; do not supply a baseline source")
        baseline_doc: BaselineDocument | None = None
        sql_capture = SQL_CAPTURE_FIRST_INSTALL
    elif mode == "db_snapshot":
        if baseline_file is not None:
            raise typer.BadParameter("bundle baseline mode is db_snapshot; use --db-url (or DATABASE_URL), not --baseline-file")
        url = db_url or _settings_database_url()
        try:
            baseline_doc = run_async(export_baseline(url, now=datetime.now(UTC)))
            sql_capture = SQL_CAPTURE_LIVE_EXPORT
        except CatalogRefreshBlockedError as exc:
            run_dir = _publish_blocked_run(
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
            _emit_review_summary(
                state="BLOCKED",
                reason=f"{exc.code}: {exc.detail}",
                run_id=run_dir.name,
                report_path=run_dir / "REVIEW.html",
                run_dir=run_dir,
                changed=0,
                warnings=0,
                blockers=1,
                json_output=json_output,
            )
            return EXIT_BLOCKED
    else:  # exported_file
        if db_url is not None:
            raise typer.BadParameter("bundle baseline mode is exported_file; use --baseline-file, not --db-url")
        if baseline_file is None:
            raise CliError("refresh bundle requires an explicit exported baseline; pass --baseline-file")
        try:
            baseline_raw = read_user_file(Path(baseline_file), MAX_BASELINE_BYTES)
        except CatalogRefreshSealError as exc:
            raise CliError(f"baseline file is not readable: {baseline_file}") from exc
        try:
            baseline_doc = load_baseline(baseline_raw)
            sql_capture = SQL_CAPTURE_DOCUMENT
        except CatalogRefreshBlockedError as exc:
            raise CliError(f"baseline file invalid: {exc.code}") from exc

    # 3-6) Shared review tail: baseline identity checks, deterministic
    # recomputation, seal-key lifecycle, staged publish, summary.
    return _finalize_review_pipeline(
        bundle=bundle,
        baseline_doc=baseline_doc,
        sql_capture=sql_capture,
        run_root=run_root,
        seal_key_path=seal_key_path,
        json_output=json_output,
        run_root_handle=run_root_handle,
        key_handle=key_handle,
    )


def _finalize_review_pipeline(
    *,
    bundle: RefreshBundle,
    baseline_doc: BaselineDocument | None,
    sql_capture: str,
    run_root: Path,
    seal_key_path: Path,
    json_output: bool,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    stage: str = STAGE_LINE,
) -> int:
    """Shared tail of review and collect.

    The run-root and key-parent anchored handles are held for the whole
    tail and their checked bindings are re-asserted before the seal-key
    load and before publication (180-g lifecycle gates unchanged).
    """
    # 1) Baseline identity checks (declared identity must match the resolved document).
    if baseline_doc is not None:
        declared = bundle.baseline
        if declared.content_sha256 is not None and declared.content_sha256 != baseline_doc.content_sha256:
            _blocked_identity(
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                bundle=bundle, code="baseline_identity_mismatch",
                detail="baseline content digest does not match the bundle's declared baseline identity",
                json_output=json_output,
            )
        if declared.target_database is not None and declared.target_database != baseline_doc.target.database:
            _blocked_identity(
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                bundle=bundle, code="baseline_target_mismatch",
                detail=f"baseline target {baseline_doc.target.database!r} does not match declared {declared.target_database!r}",
                json_output=json_output,
            )

    # 2) Deterministic recomputation.
    policy = policy_from_document(bundle.policy)
    try:
        report, artifacts = validate_against_baseline_document(bundle, baseline_doc, policy, sql_capture=sql_capture)
    except CatalogRefreshBlockedError as exc:
        _blocked_identity(
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            bundle=bundle, code=exc.code, detail=exc.detail, json_output=json_output,
        )

    # 3) Seal key: lifecycle gate (checked bindings must still hold) then
    #    load through the HELD key-parent descriptor (descriptor lineage).
    try:
        _assert_review_bindings(run_root, seal_key_path, run_root_handle, key_handle)
        key_bytes = ensure_seal_key(
            seal_key_path,
            key_parent_fd=key_handle.dir_fd if key_handle is not None else None,
        )
    except CatalogRefreshSealError as exc:
        raise CliError(f"checked path binding changed or seal key cannot be safely loaded: {exc}") from exc

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
            first_install_baseline_bytes() if baseline_doc is None else _baseline_document_bytes(baseline_doc)
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
            raise CliError(f"run root cannot be safely opened: {exc}") from exc
        owns_run_handle = True
    run_dir = run_root / bundle.run_id
    try:
        try:
            _assert_review_bindings(run_root, seal_key_path, run_root_handle, key_handle)
        except CatalogRefreshSealError as exc:
            raise CliError(f"checked path binding changed; refusing to publish: {exc}") from exc
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
                try:
                    publish_new_only_directory(
                        run_root_handle.dir_fd, staging_name, bundle.run_id, staging_identity
                    )
                except PublicationConflictError as exc:
                    raise CliError(
                        f"run directory already exists; refusing to overwrite completed output: {run_dir}"
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
    _emit_review_summary(
        state=report.state,
        reason=report.state_reason,
        run_id=bundle.run_id,
        report_path=run_dir / "REVIEW.html",
        run_dir=run_dir,
        changed=report.counts.get("changed", 0),
        warnings=len(report.warnings),
        blockers=blockers,
        json_output=json_output,
        stage=stage,
    )
    if report.state == "READY":
        return EXIT_READY
    if report.state == "READY_WITH_WARNINGS":
        return EXIT_READY_WITH_WARNINGS
    return EXIT_BLOCKED


@app.command("collect")
def collect_command(
    bootstrap: Annotated[
        bool,
        typer.Option(
            "--bootstrap",
            help="First-install collection: explicitly empty baseline; no baseline source is read.",
        ),
    ] = False,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Refresh collection against an existing baseline (requires --baseline-file or --db-url).",
        ),
    ] = False,
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="Collection profile (only standard-v1 exists in this version).",
        ),
    ] = "standard-v1",
    providers: Annotated[
        str,
        typer.Option(
            "--providers",
            help="Comma-separated provider list, a non-empty subset of openai,openrouter (default both).",
        ),
    ] = "openai,openrouter",
    models: Annotated[
        str | None,
        typer.Option(
            "--models",
            help="Comma-separated explicit model selection (default: all eligible models).",
        ),
    ] = None,
    baseline_file: Annotated[
        Path | None,
        typer.Option(
            "--baseline-file",
            help="Explicit exported baseline document (refresh only).",
        ),
    ] = None,
    db_url: Annotated[
        str | None,
        typer.Option(
            "--db-url",
            help="PostgreSQL URL for a live read-only baseline export (refresh only). Defaults to DATABASE_URL.",
        ),
    ] = None,
    run_root: Annotated[
        Path,
        typer.Option("--run-root", help="Root directory for sealed run output."),
    ] = Path("catalog-refresh-runs"),
    seal_key: Annotated[
        Path,
        typer.Option(
            "--seal-key",
            help="Runner-owned seal key file (created 0600 if missing). Must be outside the run directory.",
        ),
    ] = DEFAULT_SEAL_KEY,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a compact JSON summary instead of text."),
    ] = False,
) -> None:
    """Collect authoritative provider catalogs now, then review the collected bundle.

    Bounded official retrieval only: the registered OpenRouter/OpenAI
    catalog, pricing, and model-page endpoints plus the ECB reference XML,
    over HTTPS with bounded retries, redirects, and byte budgets. Every
    retrieval outcome (including failures) is recorded in the bundle's
    collection identity and re-verified by validation. Codex research is
    NOT_RUN in this version; no import/apply is performed.

    Exit codes: 0 READY, 10 READY_WITH_WARNINGS, 20 BLOCKED, 65 data error.
    """
    try:
        raise typer.Exit(_collect_impl(
            bootstrap=bootstrap,
            refresh=refresh,
            profile=profile,
            providers=providers,
            models=models,
            baseline_file=baseline_file,
            db_url=db_url,
            run_root=run_root,
            seal_key=seal_key,
            json_output=json_output,
        ))
    except typer.Exit:
        raise
    except CliError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshSealError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc


def _collect_impl(
    *,
    bootstrap: bool,
    refresh: bool,
    profile: str,
    providers: str,
    models: str | None,
    baseline_file: Path | None,
    db_url: str | None,
    run_root: Path,
    seal_key: Path,
    json_output: bool,
) -> int:
    if bootstrap == refresh:
        raise typer.BadParameter("exactly one of --bootstrap or --refresh is required")
    if profile != "standard-v1":
        raise typer.BadParameter("only the standard-v1 profile exists in this version")
    provider_tuple = tuple(sorted({p.strip() for p in providers.split(",") if p.strip()}))
    if not provider_tuple or any(p not in ("openai", "openrouter") for p in provider_tuple):
        raise typer.BadParameter("providers must be a non-empty subset of openai,openrouter")
    model_include = (
        tuple(sorted({m.strip() for m in models.split(",") if m.strip()})) if models else ()
    )
    if bootstrap and (baseline_file is not None or db_url is not None):
        raise typer.BadParameter("--bootstrap cannot be combined with --baseline-file or --db-url")
    if baseline_file is not None and db_url is not None:
        raise typer.BadParameter("use either --baseline-file or --db-url, not both")
    if refresh and baseline_file is None and db_url is None and not _settings_database_url_configured():
        raise typer.BadParameter("--refresh requires --baseline-file or --db-url (or DATABASE_URL)")

    run_root = run_root.expanduser().absolute()
    seal_key_path = Path(seal_key).expanduser().absolute()
    run_root_handle = _open_optional_anchored_handle(run_root)
    key_handle = _open_optional_anchored_handle(seal_key_path.parent)
    try:
        _check_key_containment(run_root, seal_key_path, run_root_handle, key_handle)

        # 1) Resolve the baseline BEFORE collection: the collector needs the
        #    document for refresh preservation, and the SQL capture label is
        #    the ACTUAL path this command took.
        if bootstrap:
            baseline_mode = "first_install"
            baseline_doc: BaselineDocument | None = None
            sql_capture = SQL_CAPTURE_FIRST_INSTALL
        elif baseline_file is not None:
            baseline_mode = "exported_file"
            try:
                baseline_raw = read_user_file(baseline_file, MAX_BASELINE_BYTES)
            except CatalogRefreshSealError as exc:
                raise CliError(f"baseline file is not readable: {baseline_file}") from exc
            try:
                baseline_doc = load_baseline(baseline_raw)
            except CatalogRefreshBlockedError as exc:
                raise CliError(f"baseline file invalid: {exc.code}") from exc
            sql_capture = SQL_CAPTURE_DOCUMENT
        else:
            baseline_mode = "db_snapshot"
            url = db_url or _settings_database_url()
            try:
                baseline_doc = run_async(export_baseline(url, now=datetime.now(UTC)))
            except CatalogRefreshBlockedError as exc:
                digest = hashlib.sha256(f"db-export:{exc.code}".encode("utf-8")).hexdigest()[:16]
                run_dir = _publish_blocked_run(
                    run_root=run_root,
                    seal_key_path=seal_key_path,
                    run_root_handle=run_root_handle,
                    key_handle=key_handle,
                    run_name=f"blocked-{exc.code}-{digest}",
                    code=exc.code,
                    detail=exc.detail,
                    generated_at=datetime.now(UTC).isoformat(),
                    bundle_canonical=None,
                )
                _emit_review_summary(
                    state="BLOCKED",
                    reason=f"{exc.code}: {exc.detail}",
                    run_id=run_dir.name,
                    report_path=run_dir / "REVIEW.html",
                    run_dir=run_dir,
                    changed=0,
                    warnings=0,
                    blockers=1,
                    json_output=json_output,
                    stage=STAGE_LINE_COLLECT,
                )
                return EXIT_BLOCKED
            sql_capture = SQL_CAPTURE_LIVE_EXPORT

        # 2) Collection: bounded official retrieval + deterministic parsing.
        # The collector measures its own start/finish window (passing a
        # pre-fetch ``now`` would date the run BEFORE the retrievals it
        # records and trip the future-timestamp gate).
        now = datetime.now(UTC)
        client = catalog_sources.new_client()
        try:
            bundle = catalog_collection.collect_bundle(
                providers=provider_tuple,
                model_include=model_include,
                baseline_mode=baseline_mode,
                baseline=baseline_doc,
                client=client,
            )
        except (CatalogRefreshBlockedError, SourceFetchError) as exc:
            code = getattr(exc, "code", None) or "collection_failed"
            detail = getattr(exc, "detail", None) or str(exc)
            digest = hashlib.sha256(f"{code}:{detail}".encode("utf-8")).hexdigest()[:16]
            run_dir = _publish_blocked_run(
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                run_name=f"blocked-{code}-{digest}",
                code=code,
                detail=detail,
                generated_at=now.isoformat(),
                bundle_canonical=None,
            )
            _emit_review_summary(
                state="BLOCKED",
                reason=f"collection failed: {code}: {detail}",
                run_id=run_dir.name,
                report_path=run_dir / "REVIEW.html",
                run_dir=run_dir,
                changed=0,
                warnings=0,
                blockers=1,
                json_output=json_output,
                stage=STAGE_LINE_COLLECT,
            )
            return EXIT_DATA_ERROR
        finally:
            client.close()

        # 3-6) Shared review tail: identity checks, deterministic
        # recomputation, seal-key lifecycle, staged publish, summary.
        return _finalize_review_pipeline(
            bundle=bundle,
            baseline_doc=baseline_doc,
            sql_capture=sql_capture,
            run_root=run_root,
            seal_key_path=seal_key_path,
            json_output=json_output,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            stage=STAGE_LINE_COLLECT,
        )
    finally:
        if run_root_handle is not None:
            run_root_handle.close()
        if key_handle is not None:
            key_handle.close()


def _blocked_identity(
    *,
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    bundle: Any,
    code: str,
    detail: str,
    json_output: bool,
) -> None:
    canonical = canonical_bundle_bytes(bundle)
    run_dir = _publish_blocked_run(
        run_root=run_root,
        seal_key_path=seal_key_path,
        run_root_handle=run_root_handle,
        key_handle=key_handle,
        run_name=f"blocked-{code}-{hashlib.sha256(canonical).hexdigest()[:16]}",
        code=code,
        detail=detail,
        generated_at=bundle.generated_at.isoformat(),
        bundle_canonical=canonical,
    )
    _emit_review_summary(
        state="BLOCKED",
        reason=f"{code}: {detail}",
        run_id=run_dir.name,
        report_path=run_dir / "REVIEW.html",
        run_dir=run_dir,
        changed=0,
        warnings=0,
        blockers=1,
        json_output=json_output,
    )
    raise typer.Exit(EXIT_BLOCKED)


@app.command("verify")
def verify_run_command(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Run directory produced by the review command."),
    ],
    seal_key: Annotated[
        Path,
        typer.Option(
            "--seal-key",
            help="Runner-owned seal key file; must already exist (verify never creates keys).",
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a compact JSON summary instead of text."),
    ] = False,
) -> None:
    """Verify a sealed run directory against the runner-owned key.

    Exit codes: 0 valid, 30 invalid, 65 data error.
    """
    try:
        key = _read_existing_seal_key(seal_key)
        result = verify_run(Path(run_dir).expanduser(), key)
    except CliError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except (OSError, CatalogRefreshError) as exc:  # noqa: BLE001 - safe boundary
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc

    if json_output:
        emit_json({"valid": result.valid, "state": result.state, "checks": result.checks, "run_dir": str(Path(run_dir).expanduser())})
        raise typer.Exit(EXIT_VERIFY_INVALID if not result.valid else 0)
    typer.echo(f"run_dir: {Path(run_dir).expanduser()}")
    typer.echo(f"valid: {'yes' if result.valid else 'no'}")
    if result.state is not None:
        typer.echo(f"state: {result.state}")
    for name, value in sorted(result.checks.items()):
        typer.echo(f"{name}: {value}")
    raise typer.Exit(EXIT_VERIFY_INVALID if not result.valid else 0)


@app.command("export-baseline")
def export_baseline_command(
    out: Annotated[
        Path,
        typer.Option("--out", help="Output path for the baseline document; must not already exist."),
    ],
    db_url: Annotated[
        str | None,
        typer.Option("--db-url", help="PostgreSQL URL for the read-only export. Defaults to DATABASE_URL."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a compact JSON summary instead of text."),
    ] = False,
) -> None:
    """Export a read-only consistent baseline document (no writes to the DB).

    Exit codes: 0 success, 65 data error (never produces an empty bootstrap).
    """
    try:
        url = db_url or _settings_database_url()
        out_path = Path(out).expanduser()
        doc = run_async(export_baseline(url, now=datetime.now(UTC)))
    except (CliError, CatalogRefreshBlockedError) as exc:
        message = getattr(exc, "detail", None) or str(exc)
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc

    # 180-g (G3): new-only output enforced atomically at the actual write
    # (renameat2 RENAME_NOREPLACE); a pre-existing target of any type —
    # including a directory created concurrently — is left untouched.
    try:
        publish_new_only_file(out_path.parent, out_path.name, _baseline_document_bytes(doc), 0o644)
    except PublicationConflictError:
        typer.secho(f"Error: refusing to overwrite existing output: {out_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR)
    except CatalogRefreshSealError as exc:
        typer.secho(f"Error: output cannot be safely published: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    summary: dict[str, Any] = {
        "target": f"{doc.target.server_host}:{doc.target.server_port}/{doc.target.database}",
        "postgres_version": doc.target.postgres_version,
        "exported_at": doc.exported_at.isoformat(),
        "sql_checked": True,
        "counts": {
            "providers": doc.counts.providers,
            "routes": doc.counts.routes,
            "pricing_rules": doc.counts.pricing_rules,
            "fx_rates": doc.counts.fx_rates,
        },
        "content_sha256": doc.content_sha256,
        "out": out_path.absolute().as_uri(),
    }
    if json_output:
        emit_json(summary)
        raise typer.Exit(EXIT_READY)
    for key, value in summary.items():
        if key == "counts":
            typer.echo("counts: " + " ".join(f"{k}={v}" for k, v in value.items()))
        else:
            typer.echo(f"{key}: {value}")
    raise typer.Exit(EXIT_READY)
