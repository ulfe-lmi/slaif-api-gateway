"""CLI commands for the bounded offline catalog refresh review workflow.

Objective 180 scope: review, verify, and read-only export-baseline only.
There is no refresh command and no apply command; supersession/apply is
NOT_SUPPORTED until objective 182 and must never be claimed to work.

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
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from slaif_gateway.cli.common import CliError, emit_json, run_async
from slaif_gateway.schemas.catalog_refresh import BaselineDocument
from slaif_gateway.services.catalog_refresh.baseline import (
    export_baseline,
    load_baseline,
)
from slaif_gateway.services.catalog_refresh.bundle import (
    canonical_bundle_bytes,
    load_bundle,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    CatalogRefreshError,
    CatalogRefreshSealError,
)
from slaif_gateway.services.catalog_refresh.policy import policy_from_document
from slaif_gateway.services.catalog_refresh.rendering import (
    build_manifest,
    esc,
    render_report,
)
from slaif_gateway.services.catalog_refresh.sealing import (
    KEY_BYTES,
    ensure_seal_key,
    first_install_baseline_bytes,
    seal_run,
    verify_run,
)
from slaif_gateway.services.catalog_refresh.validation import (
    validate_against_baseline_document,
    validation_json_bytes,
)

app = typer.Typer(help="Bounded offline catalog refresh review (no apply exists yet)")

EXIT_READY = 0
EXIT_READY_WITH_WARNINGS = 10
EXIT_BLOCKED = 20
EXIT_VERIFY_INVALID = 30
EXIT_DATA_ERROR = 65

STAGE_LINE = (
    "offline review (objective 180): review/export/verify only; no apply command "
    "exists; supersession/apply NOT_SUPPORTED until 182"
)

DEFAULT_SEAL_KEY = Path("~/.local/state/slaif/catalog-refresh/seal.key")


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    """Atomic write: temp file in same directory, fsync, rename, fsync dir."""
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


def _baseline_document_bytes(baseline: BaselineDocument) -> bytes:
    """Canonical JSON bytes for an exported baseline document."""
    payload = baseline.model_dump(mode="json")
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _settings_database_url() -> str:
    from slaif_gateway.config import get_settings

    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliError("DATABASE_URL is not configured; pass --db-url")
    return settings.DATABASE_URL


def _read_existing_seal_key(path: Path) -> bytes:
    """Read a runner-owned seal key; verify never creates keys."""
    expanded = Path(path).expanduser()
    if not expanded.is_file():
        raise CliError(f"seal key file does not exist: {expanded} (verify never creates keys)")
    try:
        raw = expanded.read_bytes()
        key = bytes.fromhex(raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CliError("seal key file must contain 64 ASCII hex characters") from exc
    if len(key) != KEY_BYTES:
        raise CliError("seal key has the wrong length")
    return key


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
        "<footer>Offline scope: review/export/verify only — no refresh or apply command exists yet; supersession apply is NOT_SUPPORTED until objective 182.</footer>",
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
    run_name: str,
    code: str,
    detail: str,
    generated_at: str,
    bundle_canonical: bytes | None,
) -> Path:
    """Publish a safe, unsealed BLOCKED run directory (new only, atomic)."""
    run_dir = run_root / run_name
    run_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise CliError(f"run directory already exists; refusing to overwrite: {run_dir}") from exc
    _atomic_write(run_dir / "REVIEW.html", _minimal_blocked_html(run_id=run_name, code=code, detail=detail, generated_at=generated_at), 0o644)
    _atomic_write(run_dir / "validation.json", _minimal_blocked_validation_json(run_id=run_name, code=code, detail=detail, generated_at=generated_at), 0o644)
    if bundle_canonical is not None:
        _atomic_write(run_dir / "catalog-refresh.json", bundle_canonical, 0o644)
    return run_dir


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
        "stage": STAGE_LINE,
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
    seal_key_path = Path(seal_key).expanduser()
    if seal_key_path.resolve().is_relative_to(run_root.resolve()):
        raise typer.BadParameter("--seal-key must be outside the run directory tree")
    if first_install and (baseline_file is not None or db_url is not None):
        raise typer.BadParameter("--first-install cannot be combined with --baseline-file or --db-url")
    if baseline_file is not None and db_url is not None:
        raise typer.BadParameter("use either --baseline-file or --db-url, not both")

    # 1) Load the canonical bundle; unparseable input gets a minimal blocked run.
    try:
        raw = Path(bundle_path).read_bytes()
    except OSError as exc:
        raise CliError(f"bundle file is not readable: {bundle_path}") from exc
    try:
        bundle = load_bundle(raw)
    except CatalogRefreshBlockedError as exc:
        run_name = f"blocked-invalid-{hashlib.sha256(raw).hexdigest()[:16]}"
        run_dir = _publish_blocked_run(
            run_root=run_root,
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
    mode = bundle.baseline.mode
    if mode == "first_install":
        if baseline_file is not None or db_url is not None:
            raise typer.BadParameter("bundle baseline mode is first_install; do not supply a baseline source")
        baseline_doc: BaselineDocument | None = None
    elif mode == "db_snapshot":
        if baseline_file is not None:
            raise typer.BadParameter("bundle baseline mode is db_snapshot; use --db-url (or DATABASE_URL), not --baseline-file")
        url = db_url or _settings_database_url()
        try:
            baseline_doc = run_async(export_baseline(url, now=datetime.now(UTC)))
        except CatalogRefreshBlockedError as exc:
            run_dir = _publish_blocked_run(
                run_root=run_root,
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
            baseline_raw = Path(baseline_file).read_bytes()
        except OSError as exc:
            raise CliError(f"baseline file is not readable: {baseline_file}") from exc
        try:
            baseline_doc = load_baseline(baseline_raw)
        except CatalogRefreshBlockedError as exc:
            raise CliError(f"baseline file invalid: {exc.code}") from exc

    # 3) Baseline identity checks (declared identity must match the resolved document).
    if baseline_doc is not None:
        declared = bundle.baseline
        if declared.content_sha256 is not None and declared.content_sha256 != baseline_doc.content_sha256:
            _blocked_identity(
                run_root=run_root, bundle=bundle, code="baseline_identity_mismatch",
                detail="baseline content digest does not match the bundle's declared baseline identity",
                json_output=json_output,
            )
        if declared.target_database is not None and declared.target_database != baseline_doc.target.database:
            _blocked_identity(
                run_root=run_root, bundle=bundle, code="baseline_target_mismatch",
                detail=f"baseline target {baseline_doc.target.database!r} does not match declared {declared.target_database!r}",
                json_output=json_output,
            )

    # 4) Deterministic recomputation.
    policy = policy_from_document(bundle.policy)
    try:
        report, artifacts = validate_against_baseline_document(bundle, baseline_doc, policy)
    except CatalogRefreshBlockedError as exc:
        _blocked_identity(
            run_root=run_root, bundle=bundle, code=exc.code, detail=exc.detail, json_output=json_output,
        )

    # 5) Publish the sealed run (new directory only, atomic, sealed last).
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
    key_bytes = ensure_seal_key(seal_key_path)
    run_dir = run_root / bundle.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise CliError(f"run directory already exists; refusing to overwrite completed output: {run_dir}") from exc
    for name in sorted(content):
        _atomic_write(run_dir / name, content[name], 0o644)
    _atomic_write(run_dir / "manifest.json", build_manifest(content), 0o644)
    seal_run(run_dir, key_bytes)

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
    )
    if report.state == "READY":
        return EXIT_READY
    if report.state == "READY_WITH_WARNINGS":
        return EXIT_READY_WITH_WARNINGS
    return EXIT_BLOCKED


def _blocked_identity(
    *,
    run_root: Path,
    bundle: Any,
    code: str,
    detail: str,
    json_output: bool,
) -> None:
    canonical = canonical_bundle_bytes(bundle)
    run_dir = _publish_blocked_run(
        run_root=run_root,
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
        if out_path.exists():
            raise CliError(f"refusing to overwrite existing output: {out_path}")
        doc = run_async(export_baseline(url, now=datetime.now(UTC)))
    except (CliError, CatalogRefreshBlockedError) as exc:
        message = getattr(exc, "detail", None) or str(exc)
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc

    _atomic_write(out_path, _baseline_document_bytes(doc), 0o644)
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
