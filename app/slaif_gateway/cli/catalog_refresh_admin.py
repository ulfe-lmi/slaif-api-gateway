"""Installed administrator refresh entry point (184 R1).

One documented refresh command: a THIN composition of the existing
``slaif-gateway catalog-refresh collect`` pipeline (collect + review in
one sealed run) under the standard Linux ``timeout(1)`` watchdog.

- Bootstrap/refresh choice is explicit (``--mode bootstrap|refresh``).
- Defaults: both providers, all eligible models, standard-v1 profile.
- The watchdog ONLY ever wraps the read-only collect invocation; apply,
  review, export-baseline, verify and status keep their own commands and
  semantics and are never placed under the watchdog.
- The child's exact exit code is preserved (including the timeout
  watchdog's own 124/128+N conventions on cancellation).
- No automatic apply, retry, browser server or Gateway startup.
- The child prints its compact readiness/run/report identity (state,
  reason, run_id, report, run_dir, changed/warnings/blockers, stage);
  this wrapper adds no file-review checklist.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.catalog_refresh import DEFAULT_SEAL_KEY, EXIT_DATA_ERROR
from slaif_gateway.cli.common import CliError

app = typer.Typer(
    invoke_without_command=True,
    help=(
        "One read-only catalog refresh: the existing collect/review "
        "pipeline under the standard Linux timeout watchdog. Read-only: "
        "no apply, retry, browser server or Gateway startup."
    ),
)

MODES = ("bootstrap", "refresh")
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_KILL_GRACE_SECONDS = 5


def _refresh_impl(
    mode: str,
    timeout: int,
    kill_grace: int,
    cli_bin: Path | None,
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
    mode = mode.lower()
    if mode not in MODES:
        raise CliError(f"--mode must be one of: {', '.join(MODES)}")
    if timeout < 1:
        raise CliError("--timeout must be a positive finite number of seconds")
    # -k 0 is NOT "KILL immediately": GNU timeout duration 0 DISABLES the
    # KILL escalation, leaving a TERM-ignoring child uncancellable.
    if kill_grace < 1:
        raise CliError(
            "--kill-grace must be a positive number of seconds "
            "(zero would disable the KILL escalation)"
        )
    if mode == "bootstrap" and (baseline_file is not None or db_url is not None):
        raise CliError("--mode bootstrap cannot be combined with --baseline-file or --db-url")

    timeout_bin = shutil.which("timeout")
    if timeout_bin is None:
        raise CliError(
            "standard Linux 'timeout' watchdog not found on PATH; "
            "the read-only refresh wrapper requires it"
        )
    gateway_cli = str(cli_bin) if cli_bin is not None else shutil.which("slaif-gateway")
    if gateway_cli is None:
        raise CliError(
            "installed 'slaif-gateway' CLI not found on PATH; "
            "install the slaif-api-gateway package or pass --cli-bin"
        )

    child_argv = [
        gateway_cli,
        "catalog-refresh",
        "collect",
        f"--{mode}",
        "--profile",
        profile,
        "--providers",
        providers,
        "--run-root",
        str(run_root),
        "--seal-key",
        str(seal_key),
    ]
    if models:
        child_argv += ["--models", models]
    if baseline_file is not None:
        child_argv += ["--baseline-file", str(baseline_file)]
    if db_url is not None:
        child_argv += ["--db-url", db_url]
    if json_output:
        child_argv += ["--json"]
    if research:
        child_argv += ["--research"]
        if research_cli_bin is not None:
            child_argv += ["--research-cli-bin", str(research_cli_bin)]
        if research_endpoint is not None:
            child_argv += ["--research-endpoint", str(research_endpoint)]
        if research_model is not None:
            child_argv += ["--research-model", str(research_model)]
        if research_auth_env is not None:
            child_argv += ["--research-auth-env", str(research_auth_env)]
        if research_timeout != 120:
            child_argv += ["--research-timeout", str(research_timeout)]

    watchdog_argv = [timeout_bin, "-k", str(kill_grace), str(timeout), *child_argv]
    # Inherited stdio: the child's compact readiness/run/report identity
    # (and any blocked-run detail) flows straight to the operator. The
    # exact child exit code is preserved, including the watchdog's own
    # exit conventions (124 timed out, 128+N killed by signal N).
    proc = subprocess.run(watchdog_argv, check=False)
    return proc.returncode


@app.callback()
def refresh(
    ctx: typer.Context,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Explicit collection mode: 'bootstrap' (first install, empty baseline) "
                 "or 'refresh' (against an existing baseline).",
            case_sensitive=False,
        ),
    ],
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            help=f"Read-only collect watchdog timeout in seconds (positive; default {DEFAULT_TIMEOUT_SECONDS}).",
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
    kill_grace: Annotated[
        int,
        typer.Option(
            "--kill-grace",
            help=f"Seconds the watchdog allows the child to exit before SIGKILL (positive; default {DEFAULT_KILL_GRACE_SECONDS}).",
        ),
    ] = DEFAULT_KILL_GRACE_SECONDS,
    cli_bin: Annotated[
        Path | None,
        typer.Option(
            "--cli-bin",
            help="Gateway CLI executable (default: 'slaif-gateway' resolved from PATH).",
        ),
    ] = None,
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
            help="Enable the isolated Codex semantic research fallback (default off).",
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
        typer.Option("--research-auth-env", help="Environment variable NAME holding the research operator key."),
    ] = None,
    research_timeout: Annotated[
        int,
        typer.Option("--research-timeout", help="Per-task research child timeout in seconds (10-600, default 120)."),
    ] = 120,
) -> None:
    """Run ONE read-only catalog refresh (collect + review, one sealed report).

    This is a thin wrapper: it invokes the installed
    ``slaif-gateway catalog-refresh collect`` command through the standard
    Linux ``timeout(1)`` watchdog and preserves the child's exact exit
    code. It never applies, never retries, and never starts a browser
    server or the Gateway.

    Exit codes (preserved from the child): 0 READY, 10
    READY_WITH_WARNINGS, 20 BLOCKED, 30 verify invalid (not produced by
    collect), 65 data error; 124/137 when the watchdog cancels a stalled
    read-only collection.
    """
    try:
        rc = _refresh_impl(
            mode=mode,
            timeout=timeout,
            kill_grace=kill_grace,
            cli_bin=cli_bin,
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
        )
    except CliError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_DATA_ERROR) from exc
    raise typer.Exit(rc)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
