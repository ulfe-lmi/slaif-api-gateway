"""184: installed administrator catalog-refresh workflow qualification.

Installed evidence for the objective-184 mandate rows: the ACTUAL
installed commands (wheel console scripts) execute the administrator
catalog-refresh workflow from OUTSIDE the source checkout.

Environment (built once per implementation head, module-scoped):

- a fresh ``git clone`` of the implementation head (no hardlinks);
- a wheel built from that checkout (``pip wheel``, standard build
  isolation, no extra dependencies);
- a separate owned venv that installs ONLY that wheel (PyPI
  dependencies); no editable install, no source-checkout PYTHONPATH;
- a test-only ``sitecustomize`` shim in that venv which is INERT unless
  ``SLAIF184_FIXTURE_DIR`` is set; when set, it serves checked-in
  fixture bytes at the existing ``sources.fetch_source`` seam for the
  five fixed official URLs and refuses every unmapped URL.

No physical network, DNS, or model call occurs in the installed runs:
the fetch seam is replaced in-place and the httpx client the CLI builds
is never used. The substitution is documented here and in
``tests/fixtures/catalog_refresh/installed-workflow/provenance.json``;
this is fixture-qualified workflow evidence, not a live-source claim.

Migrations run from the source checkout's Alembic configuration (the
wheel does not ship ``migrations/``); the target database is the
session-owned testcontainers PostgreSQL from the integration conftest.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRANCH = "oap/184-installed-admin-workflow"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "catalog_refresh" / "installed-workflow"
ENV_CACHE_ROOT = Path("/tmp/slaif184-installed-env")

CLI_SHA256_EXPECTED = "628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1"

# Shared state so later tests in this module can reuse the runs created
# here (file order is the dependency order).
_STATE: dict[str, object] = {}

# --- the test-only fixture shim (written into the owned venv) -------------

SHIM_MODULE = '''\
"""184 test-only source-fixture seam (inert without SLAIF184_FIXTURE_DIR).

Serves checked-in fixture bytes for the five fixed official URLs at the
existing ``sources.fetch_source`` module-global seam and refuses every
unmapped URL. When SLAIF184_MOCK_RESEARCH is set (JSON with
result_file/tool_sequence_file), ``collection.collect_bundle`` is
wrapped to replace the CLI-created ResearchConfig with the
already-qualified canned mock transport (the real Codex worker still
executes inside the enforced outer boundary). No other behavior changes.
"""

import dataclasses
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

_URL_FILES = {
    "https://openrouter.ai/api/v1/models": (
        "openrouter-models.json", "application/json"),
    "https://developers.openai.com/api/docs/pricing.md": (
        "openai-pricing.md", "text/markdown"),
    "https://developers.openai.com/api/docs/models.md": (
        "openai-models.md", "text/markdown"),
    "https://developers.openai.com/api/docs/models/gpt-3.5-turbo.md": (
        "openai-model-page.md", "text/markdown"),
    "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml": (
        "ecb-daily.xml", "application/xml"),
}


def _install() -> None:
    import slaif_gateway.services.catalog_refresh.collection as collection
    import slaif_gateway.services.catalog_refresh.sources as sources

    fixture_dir = Path(os.environ["SLAIF184_FIXTURE_DIR"])

    def fetch_source(client, spec, *, context, resolve):
        stall = os.environ.get("SLAIF184_STALL_SECONDS")
        if stall:
            time.sleep(float(stall))
        context.reserve_attempt()
        entry = _URL_FILES.get(spec.url)
        if entry is None:
            raise sources.SourceFetchError("fixture_unmapped_url")
        fname, ctype = entry
        content = (fixture_dir / fname).read_bytes()
        return sources.RetrievalResult(
            spec=spec,
            ok=True,
            final_url=spec.url,
            retrieved_at=datetime.now(UTC),
            status=200,
            content_type=ctype,
            content=content,
            attempts=1,
            redirects=0,
            failure_code=None,
        )

    # fetch_sources() calls the module-global fetch_source by name, so the
    # replacement covers the whole collection pipeline (no DNS, no client use).
    sources.fetch_source = fetch_source

    mock_spec = os.environ.get("SLAIF184_MOCK_RESEARCH")
    if mock_spec:
        real_bundle = collection.collect_bundle
        spec_json = json.loads(mock_spec)

        def collect_bundle(*args, **kwargs):
            cfg = kwargs.get("research")
            if cfg is not None and getattr(cfg, "enabled", False):
                kwargs["research"] = dataclasses.replace(
                    cfg,
                    mock_model=True,
                    mock_result_json=Path(spec_json["result_file"]).read_text(
                        encoding="utf-8"),
                    mock_tool_sequence_sse=Path(
                        spec_json["tool_sequence_file"]).read_text(encoding="utf-8"),
                )
            return real_bundle(*args, **kwargs)

        collection.collect_bundle = collect_bundle


def _activate() -> None:
    if os.environ.get("SLAIF184_FIXTURE_DIR"):
        _install()


try:
    _activate()
except Exception:
    # A broken shim must fail installed runs LOUDLY, never hide silently.
    raise
'''

SITECUSTOMIZE = '''\
try:
    import _slaif184_fixture_shim

    _slaif184_fixture_shim.activate = _slaif184_fixture_shim._activate
    _slaif184_fixture_shim._activate()
except ImportError:
    pass
'''


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _build_installed_env(cache: Path, head: str) -> dict[str, str]:
    checkout = cache / "checkout"
    venv = cache / "venv"
    dist = cache / "dist"
    home = cache / "home"
    for path in (checkout, dist, home):
        path.mkdir(parents=True, exist_ok=True)

    _git(REPO_ROOT, "clone", "--no-hardlinks", "--quiet", str(REPO_ROOT), str(checkout))
    _git(checkout, "fetch", "--quiet", str(REPO_ROOT), BRANCH)
    _git(checkout, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    assert _git(checkout, "rev-parse", "HEAD") == head, "clone is not at the implementation head"

    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(checkout), "--no-deps",
         "-w", str(dist), "-q"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"wheel build failed:\n{proc.stdout}\n{proc.stderr}"
    wheels = sorted(dist.glob("slaif_api_gateway-*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found: {wheels}"

    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True, text=True
    )
    venv_bin = venv / "bin"
    proc = subprocess.run(
        [str(venv_bin / "pip"), "install", "--no-cache-dir", "-q", str(wheels[0])],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, (
        f"wheel install failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    )

    site_packages = venv_bin.parent / (
        f"python{sys.version_info.major}.{sys.version_info.minor}"
    ) / "site-packages"
    (site_packages / "_slaif184_fixture_shim.py").write_text(SHIM_MODULE, encoding="utf-8")
    (site_packages / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")

    return {
        "head": head,
        "checkout": str(checkout),
        "venv_bin": str(venv_bin),
        "home": str(home),
        "wheel": str(wheels[0]),
        "wheel_sha256": _sha256_file(wheels[0]),
    }


@pytest.fixture(scope="module")
def installed_env() -> dict[str, str]:
    """Fresh-clone wheel + separate owned venv for the implementation head."""
    head = _git(REPO_ROOT, "rev-parse", "HEAD")
    cache = ENV_CACHE_ROOT / head[:8]
    ready = cache / "ready.json"
    if not ready.is_file():
        # A previous attempt may have left a partial tree; git clone refuses
        # a non-empty destination, so start clean (no shell rm: shutil only).
        shutil.rmtree(cache, ignore_errors=True)
        cache.mkdir(parents=True, exist_ok=True)
        info = _build_installed_env(cache, head)
        ready.write_text(json.dumps(info, indent=2), encoding="utf-8")
    return json.loads(ready.read_text(encoding="utf-8"))


# --- installed command runner ---------------------------------------------


def _installed_env_dict(env: dict[str, str], extra: dict[str, str] | None = None) -> dict:
    envd = {
        "PATH": (
            env["venv_bin"]
            + os.pathsep
            + "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        ),
        "HOME": env["home"],
        "LANG": "C.UTF-8",
        "TERM": "dumb",
    }
    if extra:
        envd.update(extra)
    return envd


def _run_installed(
    env: dict[str, str],
    argv: list[str],
    *,
    cwd: Path,
    extra: dict[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(Path(env["venv_bin"]) / argv[0]), *argv[1:]],
        cwd=str(cwd),
        env=_installed_env_dict(env, extra),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _summary(proc: subprocess.CompletedProcess) -> dict:
    """Parse the child's compact JSON summary (collect/verify/apply/status)."""
    assert proc.returncode in (0, 10, 20, 30, 65), (
        f"unexpected exit {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return json.loads(lines[-1])


# --- controlled source-set materialization (harness side, recorded) --------


def _materialize_source_set(target: Path, *, set_name: str, rate: str) -> Path:
    """Materialize one controlled source set with canonical file names."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "openrouter-models.json").write_bytes(
        (FIXTURE_DIR / f"openrouter-models-{set_name}.json").read_bytes()
    )
    (target / "openai-pricing.md").write_bytes(
        (FIXTURE_DIR / f"openai-pricing-{set_name}.md").read_bytes()
    )
    (target / "openai-models.md").write_bytes(
        (FIXTURE_DIR / "openai-models.md").read_bytes()
    )
    page_names = {
        "v1": "openai-gpt-3.5-turbo-captured-listitem.md",
        "v2": "openai-gpt-3.5-turbo-v2-price-derivative.md",
        "v3": None,  # referenced in place (183-b proven variant)
    }
    page_name = page_names[set_name]
    page_src = (
        FIXTURE_DIR / page_name
        if page_name
        else REPO_ROOT / "tests" / "fixtures" / "catalog_refresh"
        / "research-openai-page-variant.md"
    )
    (target / "openai-model-page.md").write_bytes(page_src.read_bytes())
    ecb = (FIXTURE_DIR / "ecb-daily-template.xml").read_text(encoding="utf-8")
    ecb = ecb.replace("__DATE__", (datetime.now(UTC) - timedelta(days=1)).date().isoformat())
    ecb = ecb.replace("__RATE__", rate)
    (target / "ecb-daily.xml").write_text(ecb, encoding="utf-8")
    return target


# --- small async SQL helpers (test-process side) ----------------------------


def _sql(url: str, query: str, *params: object) -> list[tuple]:
    async def _run() -> list[tuple]:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(url, future=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(query), params)
                return list(result)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _catalog_snapshot(url: str) -> str:
    """Order-stable digest of the catalog tables around a refusal probe."""
    rows = _sql(
        url,
        "SELECT requested_model, provider, upstream_model, enabled FROM model_routes "
        "ORDER BY requested_model, provider, upstream_model",
    )
    pricing = _sql(
        url,
        "SELECT provider, upstream_model, currency, input_price_per_1m, "
        "output_price_per_1m, valid_from, valid_until, enabled FROM pricing_rules "
        "ORDER BY provider, upstream_model, valid_from",
    )
    fx = _sql(
        url,
        "SELECT base_currency, quote_currency, rate, valid_from, valid_until "
        "FROM fx_rates ORDER BY base_currency, quote_currency, valid_from",
    )
    apps = _sql(
        url,
        "SELECT run_id, bundle_sha256, plan_sha256, mode, operator_actor, reason, "
        "effective_at FROM catalog_refresh_applications ORDER BY bundle_sha256, plan_sha256",
    )
    audit = _sql(url, "SELECT action, entity_type, created_at FROM audit_log "
                      "ORDER BY created_at, action")
    blob = json.dumps(
        {"routes": [list(r) for r in rows], "pricing": [list(r) for r in pricing],
         "fx": [list(r) for r in fx], "apps": [list(r) for r in apps],
         "audit": [list(r) for r in audit]},
        default=str,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------


def test_r3r4_installed_bootstrap_verify_apply(
    installed_env: dict[str, str], migrated_postgres_url: str, tmp_path_factory
) -> None:
    """R3+R4 first case: installed BOTH-provider bootstrap over the controlled
    ECB/source fixtures -> sealed run -> installed verify -> SQL-empty
    baseline -> installed apply -> SQL proof -> status -> idempotent retry."""
    env = installed_env
    db_url = migrated_postgres_url
    scratch = tmp_path_factory.mktemp("slaif184")
    fx_v1 = _materialize_source_set(scratch / "fx-v1", set_name="v1", rate="1.08")

    # --- R3: the installed entry points resolve INSIDE the wheel venv -------
    origin_proc = _run_installed(
        env,
        ["python", "-c", (
            "import importlib.metadata as md, importlib.resources as r, "
            "slaif_gateway, slaif_gateway.cli.catalog_refresh_admin as adm, json; "
            "print(json.dumps({"
            "'module': slaif_gateway.__file__, "
            "'admin': adm.__file__, "
            "'assets': str(r.files('slaif_gateway.resources.catalog_refresh') "
            "/ 'research-instructions.md'), "
            "'version': md.version('slaif-api-gateway')}, sort_keys=True))"
        )],
        cwd=scratch,
        timeout=120,
    )
    assert origin_proc.returncode == 0, origin_proc.stderr
    origins = json.loads(origin_proc.stdout.strip().splitlines()[-1])
    for key in ("module", "admin", "assets"):
        resolved = Path(origins[key]).resolve()
        assert str(resolved).startswith(str(Path(env["venv_bin"]).parent / "lib")), (
            f"{key} does not resolve inside the installed venv: {resolved}"
        )
    assert origins["version"]
    for entry in ("slaif-catalog-refresh", "slaif-gateway"):
        help_proc = _run_installed(env, [entry, "--help"], cwd=scratch, timeout=120)
        assert help_proc.returncode == 0, help_proc.stderr
    _STATE["origins"] = origins

    # --- R4a: installed bootstrap, both providers, controlled ECB fixture ---
    run_root = scratch / "runs-boot"
    seal_key = scratch / "seal.key"
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode", "bootstrap",
            "--run-root", str(run_root),
            "--seal-key", str(seal_key),
            "--json",
            "--timeout", "120",
        ],
        cwd=scratch,
        extra={"SLAIF184_FIXTURE_DIR": str(fx_v1)},
        timeout=300,
    )
    assert proc.returncode == 10, (
        f"bootstrap expected READY_WITH_WARNINGS (10), got {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "READY_WITH_WARNINGS"
    run_dir = Path(urlparse(summary["run_dir"]).path)
    assert run_dir.parent == run_root.resolve() or run_dir.parent == run_root
    for artifact in (
        "receipt.json", "REVIEW.html", "validation.json", "catalog-refresh.json",
        "manifest.json", "routes-proposal.tsv", "pricing-proposal.tsv",
        "fx-proposal.json",
    ):
        assert (run_dir / artifact).is_file(), f"missing {artifact}"
    _STATE["run_root_boot"] = str(run_root)
    _STATE["seal_key"] = str(seal_key)
    _STATE["run_dir_boot"] = str(run_dir)

    # The report names the exposure warning and carries both providers'
    # values plus the ECB rate in the sealed HTML.
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "gpt-3.5-turbo" in html
    assert "syn/orc-a" in html and "syn/orc-b" in html
    assert "1.08" in html

    # --- R4b: installed verify (exact sealed identity) ----------------------
    vproc = _run_installed(
        env,
        ["slaif-gateway", "catalog-refresh", "verify",
         "--run-dir", str(run_dir), "--seal-key", str(seal_key), "--json"],
        cwd=scratch,
        timeout=120,
    )
    assert vproc.returncode == 0, (
        f"verify rc={vproc.returncode}\n{vproc.stdout}\n{vproc.stderr}"
    )
    vsummary = json.loads(
        [ln for ln in vproc.stdout.splitlines() if ln.strip()][-1]
    )
    assert vsummary.get("valid") is True or vsummary.get("state") in ("valid", "READY"), vsummary

    # --- R4c: empty-catalog baseline, then installed apply ------------------
    before = _catalog_snapshot(db_url)
    assert _sql(db_url, "SELECT count(*) FROM model_routes")[0][0] == 0
    assert _sql(db_url, "SELECT count(*) FROM pricing_rules")[0][0] == 0
    assert _sql(db_url, "SELECT count(*) FROM fx_rates")[0][0] == 0

    actor = "oap-184-qualification"
    reason = "184-a qualification: installed bootstrap of both providers"
    aproc = _run_installed(
        env,
        ["slaif-gateway", "catalog-refresh", "apply",
         "--run-dir", str(run_dir),
         "--db-url", db_url,
         "--seal-key", str(seal_key),
         "--confirm",
         "--reason", reason,
         "--actor", actor,
         "--json"],
        cwd=scratch,
        timeout=180,
    )
    assert aproc.returncode == 0, (
        f"apply rc={aproc.returncode}\n{aproc.stdout}\n{aproc.stderr}"
    )
    asum = json.loads([ln for ln in aproc.stdout.splitlines() if ln.strip()][-1])
    assert asum["status"] in ("committed", "already_committed"), asum

    # --- R4d: SQL proofs ------------------------------------------------------
    routes = _sql(
        db_url,
        "SELECT requested_model, provider, upstream_model, enabled FROM model_routes "
        "ORDER BY requested_model",
    )
    assert [r[0] for r in routes] == ["gpt-3.5-turbo", "syn/orc-a", "syn/orc-b"], routes
    assert {(r[1], r[2]) for r in routes} == {
        ("openai", "gpt-3.5-turbo"),
        ("openrouter", "syn/orc-a"),
        ("openrouter", "syn/orc-b"),
    }
    assert all(r[3] for r in routes)

    def price(provider: str, model: str) -> tuple:
        rows = _sql(
            db_url,
            "SELECT currency, input_price_per_1m, output_price_per_1m, valid_until "
            "FROM pricing_rules WHERE provider=%s AND upstream_model=%s "
            "ORDER BY valid_from DESC LIMIT 1",
            provider, model,
        )
        assert len(rows) == 1, rows
        return rows[0]

    from decimal import Decimal

    cur, p_in, p_out, p_until = price("openai", "gpt-3.5-turbo")
    assert str(cur) == "USD" and p_in == Decimal("0.5") and p_out == Decimal("1.5")
    assert p_until is None
    cur, p_in, p_out, p_until = price("openrouter", "syn/orc-a")
    assert p_in == Decimal("0.000005") and p_out == Decimal("0.000015")
    assert p_until is None
    cur, p_in, p_out, p_until = price("openrouter", "syn/orc-b")
    assert p_in == Decimal("0.000004") and p_out == Decimal("0.000012")

    fx = _sql(
        db_url,
        "SELECT base_currency, quote_currency, rate, valid_until FROM fx_rates",
    )
    assert len(fx) == 1, fx
    assert fx[0][0] == "EUR" and fx[0][1] == "USD" and fx[0][2] == Decimal("1.08")
    assert fx[0][3] is None

    apps = _sql(
        db_url,
        "SELECT run_id, mode, outcome, operator_actor, reason, effective_at, "
        "bundle_sha256, plan_sha256 FROM catalog_refresh_applications",
    )
    assert len(apps) == 1, apps
    (app_run, app_mode, app_outcome, app_actor, app_reason, app_t, app_bundle, app_plan) = apps[0]
    assert (app_mode, app_outcome, app_actor, app_reason) == ("bootstrap", "committed", actor, reason)
    assert app_run == Path(run_dir).name
    assert app_bundle and app_plan and app_t is not None

    assert _sql(db_url, "SELECT count(*) FROM audit_log")[0][0] >= 1
    assert _catalog_snapshot(db_url) != before

    # --- R4e: installed status + idempotent retry ---------------------------
    sproc = _run_installed(
        env,
        ["slaif-gateway", "catalog-refresh", "status",
         "--run-dir", str(run_dir), "--db-url", db_url,
         "--seal-key", str(seal_key), "--json"],
        cwd=scratch,
        timeout=120,
    )
    assert sproc.returncode == 0, sproc.stderr
    ssum = json.loads([ln for ln in sproc.stdout.splitlines() if ln.strip()][-1])
    assert ssum["committed"] is True
    assert ssum["bundle_sha256"] == app_bundle

    retry = _run_installed(
        env,
        ["slaif-gateway", "catalog-refresh", "apply",
         "--run-dir", str(run_dir),
         "--db-url", db_url,
         "--seal-key", str(seal_key),
         "--confirm",
         "--reason", reason,
         "--actor", actor,
         "--json"],
        cwd=scratch,
        timeout=180,
    )
    assert retry.returncode == 0, (
        f"retry apply rc={retry.returncode}\n{retry.stdout}\n{retry.stderr}"
    )
    apps_after = _sql(
        db_url,
        "SELECT count(*), min(effective_at), max(effective_at) "
        "FROM catalog_refresh_applications",
    )
    assert apps_after[0][0] == 1, "idempotent retry must not add a second application row"
    assert apps_after[0][1] == apps_after[0][2] == app_t
