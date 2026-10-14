"""184: installed administrator catalog-refresh workflow qualification.

Installed evidence for the objective-184 mandate rows: the ACTUAL
installed commands (wheel console scripts) execute the administrator
catalog-refresh workflow from OUTSIDE the source checkout.

Environment (built once per module run, owned by this test module):

- a fresh ``git clone`` of the exact implementation HEAD (no hardlinks);
- a wheel built from that checkout (``pip wheel``, standard build
  isolation, no extra dependencies);
- a separate owned venv that installs ONLY that wheel (PyPI
  dependencies); no editable install, no source-checkout PYTHONPATH;
- a test-only ``sitecustomize`` shim in that venv. The shim is INERT
  unless ``SLAIF184_FIXTURE_DIR`` is set; when set it MUST succeed at
  interpreter startup (an ImportError or install exception terminates
  the process before any CLI runs - it never falls back to physical
  retrieval). When active it serves checked-in fixture bytes at the
  existing ``sources.fetch_source`` seam for the five fixed official
  URLs, refuses every unmapped URL, and denies any physical httpx send.

No physical network, DNS, or model call occurs in the installed runs:
the fetch seam is replaced in-place and the httpx client the CLI builds
is never used. The substitution is documented here and in
``tests/fixtures/catalog_refresh/installed-workflow/provenance.json``;
this is fixture-qualified workflow evidence, not a live-source claim.

Migrations run from the source checkout's Alembic configuration (the
wheel does not ship ``migrations/``) against one owned testcontainers
PostgreSQL 16 per module (owned loopback/tmpfs container with a unique
slaif184.owner label; identity-checked, removed in finally).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import time
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.integration.db_test_utils import run_alembic_upgrade_head

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "catalog_refresh" / "installed-workflow"
)

# Shared state so later tests in this module can reuse the runs created
# here (file order is the dependency order).
_STATE: dict[str, object] = {}

# --- the test-only fixture seam (written into the owned venv) --------------

SHIM_MODULE = '''\
"""184 test-only source-fixture seam.

Inert unless SLAIF184_FIXTURE_DIR is set. When active it serves
checked-in fixture bytes for the five fixed official URLs at the
existing ``sources.fetch_source`` module-global seam, refuses every
unmapped URL, and denies ANY physical httpx send. When
SLAIF184_MOCK_RESEARCH is set (JSON with result_file/tool_sequence_file),
``collection.collect_bundle`` is wrapped to replace the CLI-created
ResearchConfig with the already-qualified canned mock transport (the
real Codex worker still executes inside the enforced outer boundary).

An active-but-broken shim must terminate the interpreter at startup -
never degrade to physical retrieval.
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
    import httpx

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
    # replacement covers the whole collection pipeline (no DNS, no client).
    sources.fetch_source = fetch_source

    # Belt and braces: ANY physical send attempt is a seam failure. The
    # documented fixture path never sends; deny loudly instead of
    # degrading to real network access.
    def _deny_send(self, request, *args, **kwargs):
        raise RuntimeError("slaif184 fixture seam active: physical HTTP denied")

    httpx.Client.send = _deny_send

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


if os.environ.get("SLAIF184_FIXTURE_DIR"):
    # Module import == activation. Python IGNORES ordinary site-import
    # exceptions, so an active-but-broken seam must terminate EXPLICITLY
    # before any CLI code can run (never degrade to physical retrieval).
    try:
        _install()
    except BaseException as _exc:
        import sys

        print(
            f"slaif184 fixture seam FAILED to activate: {_exc!r} "
            "(terminating before CLI; physical retrieval is never a fallback)",
            file=sys.stderr,
        )
        sys.stderr.flush()
        os._exit(65)
'''

SITECUSTOMIZE = '''\\
import os as _os

# 184 test-only seam bootstrap: active only with SLAIF184_FIXTURE_DIR.
# Python IGNORES ordinary site-import exceptions, so a missing or
# broken shim in active mode must terminate the interpreter EXPLICITLY
# at startup (before any CLI runs) - never degrade to physical retrieval.
if _os.environ.get("SLAIF184_FIXTURE_DIR"):
    try:
        import _slaif184_fixture_shim  # noqa: F401
    except BaseException as _exc:
        import sys as _sys

        _sys.stderr.write(
            "slaif184 fixture seam FAILED to activate: %r "
            "(terminating before CLI; physical retrieval is never a fallback)\\n"
            % (_exc,)
        )
        _sys.stderr.flush()
        _os._exit(65)
'''


# --- installed environment (fresh temp ownership) ---------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)
    return proc


def _build_installed_env(root: Path, head: str) -> dict[str, str]:
    checkout = root / "checkout"
    buildvenv = root / "buildvenv"
    venv = root / "venv"
    dist = root / "dist"
    home = root / "home"
    dist.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)

    # Fresh clone of the exact implementation HEAD (all local refs/objects
    # are present; no branch-name assumption - CI may be detached).
    proc = _run(["git", "clone", "--no-hardlinks", "--quiet", str(REPO_ROOT), str(checkout)])
    assert proc.returncode == 0, f"clone failed: {proc.stderr}"
    proc = _run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", head])
    assert proc.returncode == 0, f"checkout failed: {proc.stderr}"
    assert _git(checkout, "rev-parse", "HEAD") == head, "clone is not at the implementation head"

    # Build environment with pip (the invoking venv may be pip-less).
    proc = _run([sys.executable, "-m", "venv", str(buildvenv)])
    assert proc.returncode == 0, f"buildvenv failed: {proc.stderr}"
    proc = _run(
        [str(buildvenv / "bin" / "pip"), "wheel", str(checkout), "--no-deps",
         "-w", str(dist), "-q"],
        timeout=900,
    )
    assert proc.returncode == 0, (
        f"wheel build failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    )
    wheels = sorted(dist.glob("slaif_api_gateway-*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found: {wheels}"

    # Target environment: installs ONLY the wheel (PyPI dependencies).
    proc = _run([sys.executable, "-m", "venv", str(venv)])
    assert proc.returncode == 0, f"venv failed: {proc.stderr}"
    proc = _run(
        [str(venv / "bin" / "pip"), "install", "--no-cache-dir", "-q", str(wheels[0])],
        timeout=1800,
    )
    assert proc.returncode == 0, (
        f"wheel install failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    )

    # Query the NEW venv for its purelib instead of constructing the path.
    proc = _run([str(venv / "bin" / "python"), "-c",
                 "import sysconfig; print(sysconfig.get_paths()['purelib'])"])
    assert proc.returncode == 0, proc.stderr
    site_packages = Path(proc.stdout.strip())
    (site_packages / "_slaif184_fixture_shim.py").write_text(SHIM_MODULE, encoding="utf-8")
    (site_packages / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")

    return {
        "head": head,
        "checkout": str(checkout),
        "venv_bin": str(venv / "bin"),
        "home": str(home),
        "wheel": str(wheels[0]),
        "wheel_sha256": _sha256_file(wheels[0]),
    }


@pytest.fixture(scope="module")
def installed_env(tmp_path_factory) -> dict[str, str]:
    """Fresh-clone wheel + separate owned venv for the implementation head."""
    head = _git(REPO_ROOT, "rev-parse", "HEAD")
    root = tmp_path_factory.mktemp(f"slaif184-env-{head[:8]}")
    info = _build_installed_env(root, head)
    info["root"] = str(root)
    return info


# --- owned PostgreSQL (module scope) ----------------------------------------


@pytest.fixture(scope="module")
def installed_pg_url() -> Iterator[str]:
    """One owned, loopback-bound, tmpfs-backed PostgreSQL 16 for this module.

    Ownership discipline (same as the 183 research probes): a unique
    ``slaif184.owner`` label, an explicit 127.0.0.1 port binding, and a
    tmpfs data directory (no persistent volume). The exact created
    container ID/label/binding are inspected BEFORE any migration, and
    cleanup re-checks that identity and removes ONLY this container.

    The container is driven directly with the already-installed docker
    SDK (the installed testcontainers version cannot forward
    ``labels``/``tmpfs`` through ``with_kwargs`` - both collide with
    explicit named parameters of its create path). Migrations use the
    approved repository helper (the wheel does not ship
    ``migrations/``; they run from the source checkout)."""
    import docker

    owner = f"slaif184-{secrets.token_hex(8)}"
    client = docker.from_env()
    container = client.containers.run(
        "postgres:16",
        environment={"POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "POSTGRES_DB": "test"},
        ports={5432: ("127.0.0.1", None)},
        labels={"slaif184.owner": owner},
        tmpfs={"/var/lib/postgresql/data": "rw"},
        detach=True,
    )
    try:
        # Inspect the EXACT created identity before any migration.
        attrs = container.attrs
        labels = attrs["Config"].get("Labels") or {}
        assert labels.get("slaif184.owner") == owner, "owned PG label mismatch"
        host_config = attrs["HostConfig"] or {}
        tmpfs = host_config.get("Tmpfs") or {}
        assert "/var/lib/postgresql/data" in tmpfs, "owned PG tmpfs missing"
        bindings = host_config.get("PortBindings") or {}
        bound = bindings.get("5432/tcp") or []
        assert bound and all(b.get("HostIp") == "127.0.0.1" for b in bound), (
            f"owned PG must bind loopback, got: {bound}"
        )
        port = bound[0]["HostPort"]
        assert port, "owned PG port binding missing"

        async def _wait_ready() -> None:
            import asyncpg

            deadline = time.monotonic() + 90
            last: object = None
            while time.monotonic() < deadline:
                try:
                    conn = await asyncpg.connect(
                        "postgresql://test:test@127.0.0.1:%s/test" % port, timeout=3
                    )
                    await conn.close()
                    return
                except Exception as exc:  # noqa: BLE001 - startup retry
                    last = exc
                    await asyncio.sleep(0.5)
            raise AssertionError(f"owned PG did not become ready: {last!r}")

        asyncio.run(_wait_ready())
        url = "postgresql+asyncpg://test:test@127.0.0.1:%s/test" % port
        run_alembic_upgrade_head(url)
        yield url
    finally:
        # Cleanup re-verifies identity and removes ONLY this container.
        try:
            c = client.containers.get(container.id)
            c_labels = c.attrs["Config"].get("Labels") or {}
            assert c_labels.get("slaif184.owner") == owner, (
                "refusing to remove a container whose owner label changed"
            )
            c.stop(timeout=10)
            c.remove(force=True)
        except Exception:
            # Last-resort ownership check via label filter (never by name).
            leftover = client.containers.list(
                all=True, filters={"label": f"slaif184.owner={owner}"}
            )
            for c in leftover:
                c.stop(timeout=10)
                c.remove(force=True)



# --- installed command runner -----------------------------------------------


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


# --- controlled source-set materialization (harness side, recorded) ---------


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


def _sql(url: str, query: str, params: dict | None = None) -> list[tuple]:
    async def _run() -> list[tuple]:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(url, future=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(query), params or {})
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
        "effective_at FROM catalog_refresh_applications "
        "ORDER BY bundle_sha256, plan_sha256",
    )
    audit = _sql(
        url,
        "SELECT action, entity_type, created_at FROM audit_log ORDER BY created_at, action",
    )
    blob = json.dumps(
        {
            "routes": [list(r) for r in rows],
            "pricing": [list(r) for r in pricing],
            "fx": [list(r) for r in fx],
            "apps": [list(r) for r in apps],
            "audit": [list(r) for r in audit],
        },
        default=str,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------


def test_r3r4_installed_bootstrap_verify_apply(
    installed_env: dict[str, str], installed_pg_url: str, tmp_path_factory
) -> None:
    """R3+R4 first case: installed BOTH-provider bootstrap over the
    controlled ECB/source fixtures -> sealed run -> installed verify ->
    SQL-empty baseline -> installed apply (acknowledged exposure warning)
    -> SQL proofs -> status -> idempotent retry."""
    env = installed_env
    db_url = installed_pg_url
    scratch = tmp_path_factory.mktemp("slaif184")
    fx_v1 = _materialize_source_set(scratch / "fx-v1", set_name="v1", rate="1.08")

    # --- R3: the installed entry points resolve INSIDE the wheel venv ------
    origin_proc = _run_installed(
        env,
        [
            "python",
            "-c",
            (
                "import importlib.metadata as md, importlib.resources as r, "
                "slaif_gateway, slaif_gateway.cli.catalog_refresh_admin as adm, json; "
                "print(json.dumps({"
                "'module': slaif_gateway.__file__, "
                "'admin': adm.__file__, "
                "'assets': str(r.files('slaif_gateway.resources.catalog_refresh') "
                "/ 'research-instructions.md'), "
                "'version': md.version('slaif-api-gateway')}, sort_keys=True))"
            ),
        ],
        cwd=scratch,
        timeout=120,
    )
    assert origin_proc.returncode == 0, origin_proc.stderr
    origins = json.loads(origin_proc.stdout.strip().splitlines()[-1])
    venv_lib = Path(env["venv_bin"]).parent / "lib"
    for key in ("module", "admin", "assets"):
        resolved = Path(origins[key]).resolve()
        assert str(resolved).startswith(str(venv_lib)), (
            f"{key} does not resolve inside the installed venv: {resolved}"
        )
    assert origins["version"]
    for entry in ("slaif-catalog-refresh", "slaif-gateway"):
        help_proc = _run_installed(env, [entry, "--help"], cwd=scratch, timeout=120)
        assert help_proc.returncode == 0, help_proc.stderr

    # --- R3: seam activation is verifiable and physical HTTP is denied -----
    seam_proc = _run_installed(
        env,
        [
            "python",
            "-c",
            (
                "import httpx, json, "
                "slaif_gateway.services.catalog_refresh.sources as s; "
                "print(json.dumps({"
                "'fetch_module': s.fetch_source.__module__, "
                "'send_module': httpx.Client.send.__module__}))"
            ),
        ],
        cwd=scratch,
        extra={"SLAIF184_FIXTURE_DIR": str(fx_v1)},
        timeout=120,
    )
    assert seam_proc.returncode == 0, seam_proc.stderr
    seam = json.loads(seam_proc.stdout.strip().splitlines()[-1])
    assert seam["fetch_module"] == "_slaif184_fixture_shim", seam
    assert seam["send_module"] == "_slaif184_fixture_shim", seam
    # And with the env unset the product module is untouched.
    seam_off = _run_installed(
        env,
        [
            "python",
            "-c",
            "import slaif_gateway.services.catalog_refresh.sources as s; "
            "print(s.fetch_source.__module__)",
        ],
        cwd=scratch,
        timeout=120,
    )
    assert seam_off.stdout.strip() == "slaif_gateway.services.catalog_refresh.sources"
    # Executed startup-failure control (print-only payload, no real
    # network): a BROKEN shim shadowing the venv's must terminate the
    # interpreter at startup (exit 65) BEFORE the payload runs.
    broken = scratch / "broken-shim"
    broken.mkdir()
    (broken / "_slaif184_fixture_shim.py").write_text(
        "raise RuntimeError('synthetic shim failure 184')\n", encoding="utf-8"
    )
    broken_proc = subprocess.run(
        [str(Path(env["venv_bin"]) / "python"), "-c", "print('AFTER_STARTUP_EXECUTED')"],
        cwd=str(scratch),
        env=_installed_env_dict(
            env,
            {"SLAIF184_FIXTURE_DIR": str(fx_v1), "PYTHONPATH": str(broken)},
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert broken_proc.returncode == 65, (
        f"broken shim must terminate at startup, got {broken_proc.returncode}\n"
        f"STDOUT:\n{broken_proc.stdout}\nSTDERR:\n{broken_proc.stderr}"
    )
    assert "slaif184 fixture seam FAILED to activate" in broken_proc.stderr
    assert "AFTER_STARTUP_EXECUTED" not in broken_proc.stdout

    _STATE["origins"] = origins

    # --- R4a: installed bootstrap, both providers, controlled ECB fixture --
    run_root = scratch / "runs-boot"
    seal_key = scratch / "seal.key"
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "bootstrap",
            "--run-root",
            str(run_root),
            "--seal-key",
            str(seal_key),
            "--json",
            "--timeout",
            "120",
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
    assert summary["warnings"] == 3 and summary["blockers"] == 0, summary
    run_dir = Path(urlparse(summary["run_dir"]).path)
    assert run_dir.parent == run_root.resolve() or run_dir.parent == run_root
    for artifact in (
        "receipt.json",
        "REVIEW.html",
        "validation.json",
        "catalog-refresh.json",
        "manifest.json",
        "routes-proposal.tsv",
        "pricing-proposal.tsv",
        "fx-proposal.json",
    ):
        assert (run_dir / artifact).is_file(), f"missing {artifact}"
    _STATE["run_root_boot"] = str(run_root)
    _STATE["seal_key"] = str(seal_key)
    _STATE["run_dir_boot"] = str(run_dir)

    # The warning set is exactly the per-model new-exposure findings.
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    codes = [w["code"] for w in validation["warnings"]]
    assert sorted(codes) == ["new_model_exposure"] * 3, codes

    # The sealed HTML carries both providers' models and the FX rate.
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "gpt-3.5-turbo" in html
    assert "syn/orc-a" in html and "syn/orc-b" in html
    assert "0.925925926" in html

    # --- R4b: installed verify (exact sealed identity) ---------------------
    vproc = _run_installed(
        env,
        [
            "slaif-gateway",
            "catalog-refresh",
            "verify",
            "--run-dir",
            str(run_dir),
            "--seal-key",
            str(seal_key),
            "--json",
        ],
        cwd=scratch,
        timeout=120,
    )
    assert vproc.returncode == 0, f"verify rc={vproc.returncode}\n{vproc.stdout}\n{vproc.stderr}"
    vsummary = json.loads([ln for ln in vproc.stdout.splitlines() if ln.strip()][-1])
    assert vsummary.get("valid") is True, vsummary

    # --- R4c: empty-catalog baseline, then installed apply ------------------
    before = _catalog_snapshot(db_url)
    assert _sql(db_url, "SELECT count(*) FROM model_routes")[0][0] == 0
    assert _sql(db_url, "SELECT count(*) FROM pricing_rules")[0][0] == 0
    assert _sql(db_url, "SELECT count(*) FROM fx_rates")[0][0] == 0

    actor = "oap-184-qualification"
    reason = "184-a qualification: installed bootstrap of both providers"
    apply_argv = [
        "slaif-gateway",
        "catalog-refresh",
        "apply",
        "--run-dir",
        str(run_dir),
        "--db-url",
        db_url,
        "--seal-key",
        str(seal_key),
        "--confirm",
        "--reason",
        reason,
        "--actor",
        actor,
        "--ack-warnings",
        "new_model_exposure",
        "--json",
    ]
    aproc = _run_installed(env, apply_argv, cwd=scratch, timeout=180)
    assert aproc.returncode == 0, (
        f"apply rc={aproc.returncode}\n{aproc.stdout}\n{aproc.stderr}"
    )
    asum = json.loads([ln for ln in aproc.stdout.splitlines() if ln.strip()][-1])
    assert asum["status"] == "committed", asum

    # --- R4d: SQL proofs -----------------------------------------------------
    from decimal import Decimal

    routes = _sql(
        db_url,
        "SELECT requested_model, provider, upstream_model, enabled FROM model_routes "
        "ORDER BY requested_model",
    )
    assert [r[0] for r in routes] == ["gpt-3.5-turbo", "syn/orc-a", "syn/orc-b"], routes
    _STATE["route_rows_boot"] = [
        [str(r[0]), r[1], r[2], r[3], bool(r[4]), str(r[5]), str(r[6])]
        for r in _sql(
            db_url,
            "SELECT id, requested_model, provider, upstream_model, enabled, "
            "created_at, updated_at FROM model_routes ORDER BY requested_model",
        )
    ]
    assert {(r[1], r[2]) for r in routes} == {
        ("openai", "gpt-3.5-turbo"),
        ("openrouter", "syn/orc-a"),
        ("openrouter", "syn/orc-b"),
    }
    assert all(r[3] for r in routes)

    def price(provider: str, model: str) -> tuple:
        rows = _sql(
            db_url,
            "SELECT currency, input_price_per_1m, cached_input_price_per_1m, "
            "output_price_per_1m, valid_until FROM pricing_rules "
            "WHERE provider=:provider AND upstream_model=:model "
            "ORDER BY valid_from DESC LIMIT 1",
            {"provider": provider, "model": model},
        )
        assert len(rows) == 1, rows
        return rows[0]

    cur, p_in, p_cached, p_out, p_until = price("openai", "gpt-3.5-turbo")
    assert str(cur) == "USD" and p_in == Decimal("0.5") and p_out == Decimal("1.5")
    assert p_cached is None and p_until is None
    cur, p_in, p_cached, p_out, p_until = price("openrouter", "syn/orc-a")
    # per-token fixture prices stored per-1M: 0.000005 -> 5, 0.000015 -> 15
    assert p_in == Decimal("5") and p_cached == Decimal("0.5") and p_out == Decimal("15")
    assert p_until is None
    cur, p_in, p_cached, p_out, p_until = price("openrouter", "syn/orc-b")
    assert p_in == Decimal("4") and p_cached == Decimal("0.4") and p_out == Decimal("12")

    fx = _sql(
        db_url,
        "SELECT base_currency, quote_currency, rate, valid_until FROM fx_rates",
    )
    assert len(fx) == 1, fx
    # native->EUR stored as the derived reciprocal of the published EUR-USD quote
    assert fx[0][0] == "USD" and fx[0][1] == "EUR"
    assert fx[0][2] == Decimal("0.925925926"), fx[0][2]
    assert fx[0][3] is None

    apps = _sql(
        db_url,
        "SELECT run_id, mode, outcome, operator_actor, reason, effective_at, "
        "bundle_sha256, plan_sha256 FROM catalog_refresh_applications",
    )
    assert len(apps) == 1, apps
    (app_run, app_mode, app_outcome, app_actor, app_reason, app_t, app_bundle, app_plan) = apps[0]
    assert (
        app_mode,
        app_outcome,
        app_actor,
        app_reason,
    ) == ("bootstrap", "committed", actor, reason)
    assert app_run == Path(run_dir).name
    assert app_bundle and app_plan and app_t is not None

    assert _sql(db_url, "SELECT count(*) FROM audit_log")[0][0] >= 1
    assert _catalog_snapshot(db_url) != before

    # --- R4e: installed status + idempotent retry ---------------------------
    sproc = _run_installed(
        env,
        [
            "slaif-gateway",
            "catalog-refresh",
            "status",
            "--run-dir",
            str(run_dir),
            "--db-url",
            db_url,
            "--seal-key",
            str(seal_key),
            "--json",
        ],
        cwd=scratch,
        timeout=120,
    )
    assert sproc.returncode == 0, sproc.stderr
    ssum = json.loads([ln for ln in sproc.stdout.splitlines() if ln.strip()][-1])
    assert ssum["committed"] is True
    assert ssum["bundle_sha256"] == app_bundle

    retry = _run_installed(env, apply_argv, cwd=scratch, timeout=180)
    assert retry.returncode == 0, (
        f"retry apply rc={retry.returncode}\n{retry.stdout}\n{retry.stderr}"
    )
    rsum = json.loads([ln for ln in retry.stdout.splitlines() if ln.strip()][-1])
    assert rsum["status"] == "already_committed", rsum
    apps_after = _sql(
        db_url,
        "SELECT count(*), min(effective_at), max(effective_at) FROM catalog_refresh_applications",
    )
    assert apps_after[0][0] == 1, "idempotent retry must not add a second application row"
    assert apps_after[0][1] == apps_after[0][2] == app_t


def test_r4b_installed_refresh_changed_prices_fx_and_apply(
    installed_env: dict[str, str], installed_pg_url: str, tmp_path_factory
) -> None:
    """R4 (refresh leg): installed refresh against the live DB baseline over
    the v2 controlled sources (changed OpenAI input price, changed OpenRouter
    input price, changed ECB rate) -> READY_WITH_WARNINGS with exactly the
    price/FX movement findings -> report shows old and new values ->
    acknowledged apply supersedes pricing and FX at the one effective T,
    preserves route authority, and records the second application row."""
    env = installed_env
    db_url = installed_pg_url
    scratch = tmp_path_factory.mktemp("slaif184-refresh")
    run_root = Path(_STATE["run_root_boot"])
    seal_key = Path(_STATE["seal_key"])
    fx_v2 = _materialize_source_set(scratch / "fx-v2", set_name="v2", rate="1.12")

    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "refresh",
            "--db-url",
            db_url,
            "--run-root",
            str(run_root),
            "--seal-key",
            str(seal_key),
            "--json",
            "--timeout",
            "120",
        ],
        cwd=scratch,
        extra={"SLAIF184_FIXTURE_DIR": str(fx_v2)},
        timeout=300,
    )
    assert proc.returncode == 10, (
        f"refresh expected READY_WITH_WARNINGS (10), got {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "READY_WITH_WARNINGS"
    run_dir = Path(urlparse(summary["run_dir"]).path)
    for artifact in ("receipt.json", "REVIEW.html", "validation.json", "catalog-refresh.json"):
        assert (run_dir / artifact).is_file(), f"missing {artifact}"
    _STATE["run_dir_refresh"] = str(run_dir)

    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    codes = [w["code"] for w in validation["warnings"]]
    assert sorted(codes) == [
        "fx_moved_review",
        "gate:changes",
        "price_moved_review",
        "price_moved_review",
    ], codes

    # The sealed report carries BOTH old and new values for the movements
    # (FX rendered as the stored native->EUR reciprocals of the quotes).
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "0.5" in html and "0.75" in html
    assert "0.925925926" in html and "0.892857143" in html

    vproc = _run_installed(
        env,
        [
            "slaif-gateway",
            "catalog-refresh",
            "verify",
            "--run-dir",
            str(run_dir),
            "--seal-key",
            str(seal_key),
            "--json",
        ],
        cwd=scratch,
        timeout=120,
    )
    assert vproc.returncode == 0, vproc.stderr
    vsummary = json.loads([ln for ln in vproc.stdout.splitlines() if ln.strip()][-1])
    assert vsummary.get("valid") is True, vsummary

    actor = "oap-184-qualification"
    reason = "184-a qualification: installed refresh of changed prices and FX"
    aproc = _run_installed(
        env,
        [
            "slaif-gateway",
            "catalog-refresh",
            "apply",
            "--run-dir",
            str(run_dir),
            "--db-url",
            db_url,
            "--seal-key",
            str(seal_key),
            "--confirm",
            "--reason",
            reason,
            "--actor",
            actor,
            "--ack-warnings",
            "price_moved_review,fx_moved_review,gate:changes",
            "--json",
        ],
        cwd=scratch,
        timeout=180,
    )
    assert aproc.returncode == 0, (
        f"refresh apply rc={aproc.returncode}\n{aproc.stdout}\n{aproc.stderr}"
    )
    asum = json.loads([ln for ln in aproc.stdout.splitlines() if ln.strip()][-1])
    assert asum["status"] == "committed", asum

    from decimal import Decimal

    # --- pricing supersession at the one effective T ------------------------
    def pricing_rows(provider: str, model: str) -> list:
        return _sql(
            db_url,
            "SELECT input_price_per_1m, output_price_per_1m, cached_input_price_per_1m, "
            "valid_from, valid_until FROM pricing_rules "
            "WHERE provider=:provider AND upstream_model=:model ORDER BY valid_from",
            {"provider": provider, "model": model},
        )

    gpt_rows = pricing_rows("openai", "gpt-3.5-turbo")
    assert len(gpt_rows) == 2, gpt_rows
    old, new = gpt_rows
    assert old[0] == Decimal("0.5") and old[1] == Decimal("1.5") and old[4] is not None
    assert new[0] == Decimal("0.75") and new[1] == Decimal("1.5") and new[4] is None
    assert old[4] == new[3], "old row must close exactly where the new row opens"

    orc_rows = pricing_rows("openrouter", "syn/orc-a")
    assert len(orc_rows) == 2, orc_rows
    old, new = orc_rows
    assert old[0] == Decimal("5") and old[1] == Decimal("15")
    assert new[0] == Decimal("7") and new[1] == Decimal("15") and new[2] == Decimal("0.5")
    assert old[4] == new[3]

    # unchanged model: its single row was not superseded
    orc_b = pricing_rows("openrouter", "syn/orc-b")
    assert len(orc_b) == 1, orc_b
    assert orc_b[0][0] == Decimal("4") and orc_b[0][1] == Decimal("12") and orc_b[0][4] is None

    # --- FX supersession ------------------------------------------------------
    fx_rows = _sql(
        db_url,
        "SELECT rate, valid_from, valid_until FROM fx_rates "
        "WHERE base_currency='USD' AND quote_currency='EUR' ORDER BY valid_from",
    )
    assert len(fx_rows) == 2, fx_rows
    old, new = fx_rows
    assert old[0] == Decimal("0.925925926") and old[2] is not None
    assert new[0] == Decimal("0.892857143") and new[2] is None
    assert old[2] == new[1]
    # the T of the pricing supersessions equals the T of the FX supersession
    assert new[1] == gpt_rows[1][3] == orc_rows[1][3]

    # --- route authority preserved -------------------------------------------
    routes = _sql(
        db_url,
        "SELECT id, requested_model, provider, upstream_model, enabled, "
        "created_at, updated_at FROM model_routes ORDER BY requested_model",
    )
    after_rows = [
        [str(r[0]), r[1], r[2], r[3], bool(r[4]), str(r[5]), str(r[6])] for r in routes
    ]
    assert after_rows == _STATE["route_rows_boot"], (
        "refresh must not create, drop, or modify existing route rows"
    )

    # --- second durable application row ---------------------------------------
    apps = _sql(
        db_url,
        "SELECT run_id, mode, outcome FROM catalog_refresh_applications "
        "ORDER BY effective_at",
    )
    assert len(apps) == 2, apps
    assert apps[0][1] == "bootstrap" and apps[0][2] == "committed"
    assert apps[1][1] == "refresh" and apps[1][2] == "committed"
    assert apps[1][0] == Path(run_dir).name

    sproc = _run_installed(
        env,
        [
            "slaif-gateway",
            "catalog-refresh",
            "status",
            "--run-dir",
            str(run_dir),
            "--db-url",
            db_url,
            "--seal-key",
            str(seal_key),
            "--json",
        ],
        cwd=scratch,
        timeout=120,
    )
    assert sproc.returncode == 0, sproc.stderr
    ssum = json.loads([ln for ln in sproc.stdout.splitlines() if ln.strip()][-1])
    assert ssum["committed"] is True
