"""CLI commands for the bounded catalog refresh collection and review workflow.

Scope in this version: collect (bounded live official-source collection
followed by review of the collected bundle), review (offline review of a
supplied bundle), verify, read-only export-baseline, and the explicit
atomic apply of a reviewed sealed run (plus read-only apply status). Live
collection is limited to the registered official catalog, pricing, and FX
endpoints over HTTPS with bounded retries, redirects, and byte budgets. When
enabled, the isolated Codex semantic research fallback (real CLI in an
enforced outer boundary, parent re-grounding; deterministic parsing stays
first) may transcribe eligible unresolved facts from the captured bytes.

217-a (G15): the collect/review/publication pipeline bodies now delegate to
the shared application composition in
:mod:`slaif_gateway.services.catalog_refresh.application` (the same
composition the admin-GUI worker tasks compose); this module keeps the CLI
entrypoints, option parsing, output, and exit semantics unchanged and adds
no second pipeline.

Exit codes:
- 0  review state READY
- 10 review state READY_WITH_WARNINGS
- 20 review state BLOCKED (safe blocked run published when possible)
- 30 verify: run directory failed verification
- 30 apply: seal/authentication failure (wrong key, tampered, unsupported)
- 65 data error: unreadable/unparseable input, bad baseline file, missing
   database configuration, seal key problem, or output conflict
- 2  usage error (typer standard, e.g. contradictory options)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from slaif_gateway.cli.common import CliError, emit_json, run_async
from slaif_gateway.schemas.catalog_refresh import BaselineDocument
from slaif_gateway.services.catalog_refresh import application as catalog_application
from slaif_gateway.services.catalog_refresh import research as catalog_research
from slaif_gateway.services.catalog_refresh.apply import (
    apply_reviewed_run,
    apply_status,
)
from slaif_gateway.services.catalog_refresh.baseline import (
    export_baseline,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    CatalogRefreshError,
    CatalogRefreshSealError,
)
from slaif_gateway.services.catalog_refresh.filesystem import (
    AnchoredDir,
    PublicationConflictError,
    load_seal_key_bytes,
    open_anchored_handle,
    publish_new_only_file,
)
from slaif_gateway.services.catalog_refresh.sealing import (
    verify_run,
)

app = typer.Typer(help="Bounded catalog refresh: collect, review, verify, export-baseline, apply, status")

EXIT_READY = 0
EXIT_READY_WITH_WARNINGS = 10
EXIT_BLOCKED = 20
EXIT_VERIFY_INVALID = 30
EXIT_DATA_ERROR = 65

# Stage lines live in the shared composition (217-a); they are re-exported
# unchanged for the CLI surface and existing consumers.
STAGE_LINE = catalog_application.STAGE_LINE
STAGE_LINE_COLLECT = catalog_application.STAGE_LINE_COLLECT
STAGE_LINE_COLLECT_NOT_STARTED = catalog_application.STAGE_LINE_COLLECT_NOT_STARTED
STAGE_LINE_COLLECT_INCOMPLETE = catalog_application.STAGE_LINE_COLLECT_INCOMPLETE

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


def _settings_database_url_or_none() -> str | None:
    from slaif_gateway.config import get_settings

    return get_settings().DATABASE_URL or None


def _check_key_containment(
    run_root: Path,
    seal_key_path: Path,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
) -> None:
    """CLI mapping of the shared containment check (usage error text and
    exit semantics unchanged)."""
    try:
        catalog_application.check_key_containment(
            run_root, seal_key_path, run_root_handle, key_handle
        )
    except catalog_application.ApplicationUsageError as exc:
        raise typer.BadParameter(exc.detail) from exc


_assert_review_bindings = catalog_application.assert_review_bindings


def _read_existing_seal_key(path: Path, handle: AnchoredDir | None = None) -> bytes:
    """Read a runner-owned seal key; verify never creates keys.

    The key is loaded through the shared anchored boundary: no-follow at
    every component, regular file / 0600 / current-runner ownership / 64
    lowercase hex bytes validated on the OPENED descriptor. When the
    caller passes its checked key-parent handle, the key is read through
    that held descriptor (binding re-asserted inside the loader, no path
    reopen) instead of re-anchoring the parent.
    """
    try:
        return load_seal_key_bytes(Path(path).expanduser(), parent_handle=handle)
    except CatalogRefreshSealError as exc:
        raise CliError(str(exc)) from exc


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


def _outcome_exit_code(outcome: "catalog_application.ReviewOutcome") -> int:
    if outcome.exit_class == "ready":
        return EXIT_READY
    if outcome.exit_class == "ready_with_warnings":
        return EXIT_READY_WITH_WARNINGS
    if outcome.exit_class == "blocked_data_error":
        return EXIT_DATA_ERROR
    return EXIT_BLOCKED


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


def _open_optional_anchored_handle(path: Path) -> AnchoredDir | None:
    try:
        return open_anchored_handle(path)
    except CatalogRefreshSealError:
        return None


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
        # 217-a (G15): lazy resolution seam - the configured DATABASE_URL
        # getter is passed as a callable, never pre-read. The shared
        # pipeline parses the bundle once, selects its VALIDATED
        # baseline.mode, and evaluates the getter ONLY for a db_snapshot
        # bundle lacking an explicit --db-url (the legacy resolution
        # point); offline and explicit-URL reviews never consult
        # settings.
        try:
            outcome = catalog_application.run_review(
                bundle_path=bundle_path,
                baseline_file=baseline_file,
                first_install=first_install,
                db_url=db_url,
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                settings_database_url=_settings_database_url_or_none,
            )
        except catalog_application.ApplicationUsageError as exc:
            raise typer.BadParameter(exc.detail) from exc
        except catalog_application.ApplicationDataError as exc:
            raise CliError(exc.message) from exc
        _emit_review_summary(
            state=outcome.state,
            reason=outcome.reason,
            run_id=outcome.run_id,
            report_path=outcome.report_path,
            run_dir=outcome.run_dir,
            changed=outcome.changed,
            warnings=outcome.warnings,
            blockers=outcome.blockers,
            json_output=json_output,
            stage=outcome.stage,
        )
        return _outcome_exit_code(outcome)
    except typer.BadParameter:
        raise
    except CatalogRefreshSealError as exc:
        raise CliError(f"refusing unsafe directory configuration: {exc}") from exc
    finally:
        if run_root_handle is not None:
            run_root_handle.close()
        if key_handle is not None:
            key_handle.close()


def _finalize_review_pipeline(
    *,
    bundle: Any,
    baseline_doc: BaselineDocument | None,
    sql_capture: str,
    run_root: Path,
    seal_key_path: Path,
    json_output: bool,
    run_root_handle: AnchoredDir | None,
    key_handle: AnchoredDir | None,
    stage: str = STAGE_LINE,
    acquisition: str = "offline_supplied",
) -> int:
    """CLI compatibility wrapper over the shared finalize tail (217-a).

    The pipeline itself lives in
    :func:`slaif_gateway.services.catalog_refresh.application.
    finalize_review_pipeline`; this wrapper keeps the historical signature
    (and the compact summary emission + exit-code contract) for the CLI and
    existing consumers.
    """
    try:
        outcome = catalog_application.finalize_review_pipeline(
            bundle=bundle,
            baseline_doc=baseline_doc,
            sql_capture=sql_capture,
            run_root=run_root,
            seal_key_path=seal_key_path,
            run_root_handle=run_root_handle,
            key_handle=key_handle,
            stage=stage,
            acquisition=acquisition,
        )
    except catalog_application.ApplicationDataError as exc:
        raise CliError(exc.message) from exc
    _emit_review_summary(
        state=outcome.state,
        reason=outcome.reason,
        run_id=outcome.run_id,
        report_path=outcome.report_path,
        run_dir=outcome.run_dir,
        changed=outcome.changed,
        warnings=outcome.warnings,
        blockers=outcome.blockers,
        json_output=json_output,
        stage=outcome.stage,
    )
    return _outcome_exit_code(outcome)


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
    research: Annotated[
        bool,
        typer.Option(
            "--research/--no-research",
            help="Enable the isolated Codex semantic research fallback for eligible "
                 "unresolved facts (default off; deterministic parsing stays first).",
        ),
    ] = False,
    research_cli_bin: Annotated[
        Path | None,
        typer.Option("--research-cli-bin", help="Verified codex CLI binary (required with --research)."),
    ] = None,
    research_endpoint: Annotated[
        str | None,
        typer.Option("--research-endpoint", help="HTTPS research inference endpoint (required with --research)."),
    ] = None,
    research_model: Annotated[
        str | None,
        typer.Option("--research-model", help="Model name for the research endpoint (required with --research)."),
    ] = None,
    research_auth_env: Annotated[
        str | None,
        typer.Option("--research-auth-env", help="Environment variable NAME holding the research operator key (value never printed)."),
    ] = None,
    research_timeout: Annotated[
        int,
        typer.Option("--research-timeout", help="Per-task research child timeout in seconds (10-600, default 120)."),
    ] = 120,
) -> None:
    """Collect authoritative provider catalogs now, then review the collected bundle.

    Bounded official retrieval only: the registered OpenRouter/OpenAI
    catalog, pricing, and model-page endpoints plus the ECB reference XML,
    over HTTPS with bounded retries, redirects, and byte budgets. Every
    retrieval outcome (including failures) is recorded in the bundle's
    collection identity and re-verified by validation. By default Codex
    research is NOT_RUN; with --research, eligible unresolved facts may be
    transcribed by the isolated Codex semantic fallback (real CLI in an
    enforced outer boundary; the parent re-grounds every fact). No
    import/apply is performed.

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
            research=research,
            research_cli_bin=research_cli_bin,
            research_endpoint=research_endpoint,
            research_model=research_model,
            research_auth_env=research_auth_env,
            research_timeout=research_timeout,
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
    research: bool,
    research_cli_bin: Path | None,
    research_endpoint: str | None,
    research_model: str | None,
    research_auth_env: str | None,
    research_timeout: int,
) -> int:
    if bootstrap == refresh:
        raise typer.BadParameter("exactly one of --bootstrap or --refresh is required")
    if profile != "standard-v1":
        raise typer.BadParameter("only the standard-v1 profile exists in this version")
    research_config: catalog_research.ResearchConfig | None = None
    if research:
        missing = [
            name
            for name, value in (
                ("--research-cli-bin", research_cli_bin),
                ("--research-endpoint", research_endpoint),
                ("--research-model", research_model),
                ("--research-auth-env", research_auth_env),
            )
            if not value
        ]
        if missing:
            raise typer.BadParameter("--research requires " + ", ".join(missing))
        endpoint = str(research_endpoint)
        if not endpoint.lower().startswith("https://"):
            raise typer.BadParameter("--research-endpoint must be an HTTPS endpoint")
        if not 10 <= research_timeout <= 600:
            raise typer.BadParameter("--research-timeout must be between 10 and 600")
        if not str(research_auth_env) or not os.environ.get(str(research_auth_env)):
            raise typer.BadParameter(f"--research-auth-env {research_auth_env} is not set to a non-empty value")
        cli_bin_path = Path(research_cli_bin).expanduser().absolute()
        if not cli_bin_path.is_file():
            raise typer.BadParameter(f"--research-cli-bin is not a readable file: {cli_bin_path}")
        research_config = catalog_research.ResearchConfig(
            enabled=True,
            cli_bin=str(cli_bin_path),
            model_endpoint=endpoint,
            model_name=str(research_model),
            model_auth_env=str(research_auth_env),
            timeout_seconds=research_timeout,
        )
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
        # 217-a (G15): legacy LAZY resolution point - the configured
        # DATABASE_URL is consulted ONLY on the refresh-without-exported-
        # file path (no --db-url, no --baseline-file); bootstrap and
        # exported-file modes never touch settings at all.
        settings_database_url = None
        if not bootstrap and baseline_file is None and db_url is None:
            settings_database_url = _settings_database_url_or_none()
        try:
            outcome = catalog_application.run_collect(
                bootstrap=bootstrap,
                refresh=refresh,
                profile=profile,
                providers=provider_tuple,
                model_include=model_include,
                baseline_file=baseline_file,
                db_url=db_url,
                run_root=run_root,
                seal_key_path=seal_key_path,
                run_root_handle=run_root_handle,
                key_handle=key_handle,
                research=research_config,
                settings_database_url=settings_database_url,
            )
        except catalog_application.ApplicationUsageError as exc:
            raise typer.BadParameter(exc.detail) from exc
        except catalog_application.ApplicationDataError as exc:
            raise CliError(exc.message) from exc
        _emit_review_summary(
            state=outcome.state,
            reason=outcome.reason,
            run_id=outcome.run_id,
            report_path=outcome.report_path,
            run_dir=outcome.run_dir,
            changed=outcome.changed,
            warnings=outcome.warnings,
            blockers=outcome.blockers,
            json_output=json_output,
            stage=outcome.stage,
        )
        return _outcome_exit_code(outcome)
    except typer.BadParameter:
        raise
    except CatalogRefreshSealError as exc:
        raise CliError(f"refusing unsafe directory configuration: {exc}") from exc
    finally:
        if run_root_handle is not None:
            run_root_handle.close()
        if key_handle is not None:
            key_handle.close()


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

    181-i (I2): after authenticating the run, the original RUNNER-SELECTED
    execution context bound in the authenticated validation.json is
    replayed (never re-measured); the original generator identity and the
    current verifier's measured identity are reported separately. Sealed
    runs predating the execution-context contract are refused explicitly.

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
        payload = result.to_dict()
        payload["run_dir"] = str(Path(run_dir).expanduser())
        emit_json(payload)
        raise typer.Exit(EXIT_VERIFY_INVALID if not result.valid else 0)
    typer.echo(f"run_dir: {Path(run_dir).expanduser()}")
    typer.echo(f"valid: {'yes' if result.valid else 'no'}")
    if result.state is not None:
        typer.echo(f"state: {result.state}")
    for name, value in sorted(result.checks.items()):
        typer.echo(f"{name}: {value}")
    if result.original_generator is not None:
        typer.echo(
            f"original generator: tool {result.original_generator['tool']} · code_revision "
            f"{result.original_generator['code_revision']} (authenticated in the sealed validation.json)"
        )
    if result.current_generator is not None:
        typer.echo(
            f"current generator: tool {result.current_generator['tool']} · code_revision "
            f"{result.current_generator['code_revision']} (measured at verification time)"
        )
    raise typer.Exit(EXIT_VERIFY_INVALID if not result.valid else 0)


@app.command("export-baseline")
def export_baseline_command(
    out: Annotated[
        Path,
        typer.Option("--out", help="Output path for the baseline document; must not already exist."),
    ],
    db_url: Annotated[
        str | None,
        typer.Option(
            "--db-url",
            help="PostgreSQL URL for the read-only export. Defaults to DATABASE_URL.",
        ),
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
        raise typer.Exit(EXIT_DATA_ERROR) from None
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


@app.command("apply")
def apply_run(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Sealed run directory whose reviewed plan will be applied."),
    ],
    db_url: Annotated[
        str,
        typer.Option(
            "--db-url",
            help="PostgreSQL URL of the target database (explicit operator configuration; never defaulted).",
        ),
    ],
    seal_key: Annotated[
        Path,
        typer.Option(
            "--seal-key",
            help="Runner-owned seal key file. Must be outside the run directory.",
        ),
    ] = DEFAULT_SEAL_KEY,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Explicit operator confirmation that this run is to be applied."),
    ] = False,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Operator reason recorded with the durable application record."),
    ] = "",
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            help="Operator assertion of who is applying (recorded as supplied; not a verified RBAC identity).",
        ),
    ] = "",
    admin_id: Annotated[
        str | None,
        typer.Option(
            "--admin-id",
            help="Existing admin user ID recorded as the acting admin (verified to exist in the target database).",
        ),
    ] = None,
    ack_warnings: Annotated[
        str | None,
        typer.Option(
            "--ack-warnings",
            help="Comma-separated review finding codes acknowledged at apply time.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a compact JSON summary instead of text."),
    ] = False,
) -> None:
    """Apply the reviewed plan of one sealed run atomically to PostgreSQL.

    Exit codes: 0 committed (or already committed), 10 unacknowledged
    apply-time findings, 20 plan not applicable (blocked, absent, or
    mismatched), 30 seal/authentication failure, 65 data error (target
    mismatch, stale baseline, non-empty bootstrap, unknown admin,
    close-guard drift, database failure).
    """
    try:
        admin_uuid: uuid.UUID | None = None
        if admin_id is not None:
            try:
                admin_uuid = uuid.UUID(admin_id)
            except ValueError:
                raise CliError("--admin-id must be a UUID") from None
        if not confirm:
            raise CliError("apply requires explicit --confirm")
        if not reason.strip():
            raise CliError("apply requires a non-empty --reason")
        if not actor.strip():
            raise CliError("apply requires a non-empty --actor")

        run_dir_path = Path(run_dir).expanduser().absolute()
        seal_key_path = Path(seal_key).expanduser().absolute()
        run_dir_handle = _open_optional_anchored_handle(run_dir_path)
        key_handle = _open_optional_anchored_handle(seal_key_path.parent)
        try:
            _check_key_containment(run_dir_path, seal_key_path, run_dir_handle, key_handle)
            _assert_review_bindings(run_dir_path, seal_key_path, run_dir_handle, key_handle)
            key = _read_existing_seal_key(seal_key_path, key_handle)
            try:
                result = run_async(
                    apply_reviewed_run(
                        run_dir=run_dir_path,
                        seal_key=key,
                        database_url=db_url,
                        reason=reason.strip(),
                        actor=actor.strip(),
                        admin_id=admin_uuid,
                        ack_warnings=tuple(
                            code.strip() for code in (ack_warnings or "").split(",") if code.strip()
                        ),
                        run_handle=run_dir_handle,
                    )
                )
            except CatalogRefreshSealError as exc:
                typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(EXIT_VERIFY_INVALID) from exc
            except CatalogRefreshBlockedError as exc:
                typer.secho(f"Error: {exc.code}: {exc.detail}", fg=typer.colors.RED, err=True)
                if exc.code == "apply_warnings_unacknowledged":
                    raise typer.Exit(EXIT_READY_WITH_WARNINGS) from exc
                if exc.code in (
                    "apply_state_not_applicable",
                    "apply_freshness_blocked",
                    "apply_no_plan",
                    "apply_plan_unsupported",
                    "apply_plan_mismatch",
                ):
                    raise typer.Exit(EXIT_BLOCKED) from exc
                raise typer.Exit(EXIT_DATA_ERROR) from exc
        finally:
            if run_dir_handle is not None:
                run_dir_handle.close()
            if key_handle is not None:
                key_handle.close()

        summary: dict[str, Any] = {
            "status": result.status,
            "run_id": result.run_id,
            "bundle_sha256": result.bundle_sha256,
            "plan_sha256": result.plan_sha256,
            "effective_at": result.effective_at,
            "counts": dict(sorted(result.counts.items())),
        }
        if result.record is not None:
            summary["record"] = dict(sorted(result.record.items()))
        if json_output:
            emit_json(summary)
            raise typer.Exit(EXIT_READY)
        for key, value in summary.items():
            if key == "counts":
                typer.echo("counts: " + " ".join(f"{k}={v}" for k, v in value.items()))
            elif key == "record":
                typer.echo("record: " + json.dumps(value, sort_keys=True))
            else:
                typer.echo(f"{key}: {value}")
        raise typer.Exit(EXIT_READY)
    except typer.Exit:
        raise
    except CliError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshSealError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc


@app.command("status")
def apply_status_command(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Sealed run directory to look up."),
    ],
    db_url: Annotated[
        str,
        typer.Option(
            "--db-url",
            help="PostgreSQL URL to query (read-only; never mutates, never takes catalog locks).",
        ),
    ],
    seal_key: Annotated[
        Path,
        typer.Option(
            "--seal-key",
            help="Runner-owned seal key file. Must be outside the run directory.",
        ),
    ] = DEFAULT_SEAL_KEY,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a compact JSON summary instead of text."),
    ] = False,
) -> None:
    """Read-only visibility of the committed apply outcome for one sealed run.

    Exit codes: 0 (committed or not yet committed — the fact is reported),
    30 seal/authentication failure, 65 data error.
    """
    try:
        run_dir_path = Path(run_dir).expanduser().absolute()
        seal_key_path = Path(seal_key).expanduser().absolute()
        run_dir_handle = _open_optional_anchored_handle(run_dir_path)
        key_handle = _open_optional_anchored_handle(seal_key_path.parent)
        try:
            _check_key_containment(run_dir_path, seal_key_path, run_dir_handle, key_handle)
            _assert_review_bindings(run_dir_path, seal_key_path, run_dir_handle, key_handle)
            key = _read_existing_seal_key(seal_key_path, key_handle)
            try:
                status = run_async(
                    apply_status(
                        run_dir=run_dir_path,
                        seal_key=key,
                        database_url=db_url,
                        run_handle=run_dir_handle,
                    )
                )
            except CatalogRefreshSealError as exc:
                typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(EXIT_VERIFY_INVALID) from exc
        finally:
            if run_dir_handle is not None:
                run_dir_handle.close()
            if key_handle is not None:
                key_handle.close()

        summary: dict[str, Any] = {
            "run_id": status.run_id,
            "bundle_sha256": status.bundle_sha256,
            "committed": status.committed,
            "records": list(status.records),
        }
        if json_output:
            emit_json(summary)
            raise typer.Exit(EXIT_READY)
        typer.echo(f"run_id: {status.run_id}")
        typer.echo(f"bundle_sha256: {status.bundle_sha256}")
        typer.echo(f"committed: {str(status.committed).lower()}")
        for record in status.records:
            typer.echo("record: " + json.dumps(record, sort_keys=True))
        raise typer.Exit(EXIT_READY)
    except typer.Exit:
        raise
    except CliError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshSealError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    except CatalogRefreshBlockedError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
