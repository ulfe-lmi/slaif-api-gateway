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
  With ``SLAIF184_APPLY_AGE_SECONDS`` additionally set, the EXISTING
  ``apply.datetime`` seam is test-only substituted with a finite shifted
  wall clock (stale-at-apply refusal; no host clock, no runtime flag).

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
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.integration.db_test_utils import run_alembic_upgrade_head
from tests.integration.test_catalog_refresh_research_codex import (
    requires_boundary,
)

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
unmapped URL, and denies ANY physical httpx send. Optional
SLAIF184_FAIL_URLS (comma-separated official URLs) makes those mapped
fetches raise the safe code-only SourceFetchError, simulating a
source outage for the failed-collect labels. When
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
        fail_urls = os.environ.get("SLAIF184_FAIL_URLS")
        if fail_urls and spec.url in fail_urls.split(","):
            raise sources.SourceFetchError("fixture_forced_failure")
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

    apply_age = os.environ.get("SLAIF184_APPLY_AGE_SECONDS")
    if apply_age:
        # Test-only clock substitution at the EXISTING apply.datetime seam
        # (apply.py calls datetime.now(UTC) for the apply-time freshness
        # re-check): the one wall-clock call shifts by a finite, explicit
        # number of seconds so an otherwise-fresh authenticated run can be
        # proven to refuse on source age at apply. No host clock is touched
        # and no runtime flag or general time framework is added: the
        # product code path is unchanged, and this substitution exists only
        # in this disposable qualification venv under the explicit env var.
        from datetime import timedelta as _timedelta

        import slaif_gateway.services.catalog_refresh.apply as _apply_mod

        _real_datetime = _apply_mod.datetime
        _age_shift = _timedelta(seconds=float(apply_age))

        class _AgedDatetime(_real_datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return _real_datetime.now(tz) + _age_shift

        _apply_mod.datetime = _AgedDatetime


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
    # Explicit qualified daemon (no inherited DOCKER_HOST ambiguity).
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    container = client.containers.run(
        "postgres:16",
        environment={"POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "POSTGRES_DB": "test"},
        ports={5432: ("127.0.0.1", None)},
        labels={"slaif184.owner": owner},
        tmpfs={"/var/lib/postgresql/data": "rw"},
        detach=True,
    )
    try:
        # Inspect the EXACT created identity before any migration. The SDK
        # caches attrs; reload so this is the running state, not the
        # create-time snapshot (port mapping is assigned at start).
        container.reload()
        attrs = container.attrs
        labels = attrs["Config"].get("Labels") or {}
        assert labels.get("slaif184.owner") == owner, "owned PG label mismatch"
        host_config = attrs["HostConfig"] or {}
        tmpfs = host_config.get("Tmpfs") or {}
        assert "/var/lib/postgresql/data" in tmpfs, "owned PG tmpfs missing"
        # Configured binding: loopback IP requested (HostPort empty string
        # == random port in the Docker API).
        bindings = host_config.get("PortBindings") or {}
        configured = bindings.get("5432/tcp") or []
        assert configured and all(
            b.get("HostIp") == "127.0.0.1" for b in configured
        ), f"owned PG must bind loopback, got: {configured}"
        # Actual published mapping (measured after start).
        network_ports = (attrs["NetworkSettings"] or {}).get("Ports") or {}
        bound = network_ports.get("5432/tcp") or []
        assert bound and all(b.get("HostIp") == "127.0.0.1" for b in bound), (
            f"owned PG must publish on loopback, got: {bound}"
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
        # Cleanup re-verifies the EXACT created container ID and its owner
        # label, then removes ONLY that container. A Docker NotFound means
        # it was already removed; every other failure is a real cleanup
        # failure and is re-raised. There is deliberately NO label-scan
        # fallback: an uncreated ID is never removed even if some other
        # container happens to carry the owner label.
        try:
            c = client.containers.get(container.id)
        except docker.errors.NotFound:
            _STATE["pg_cleanup"] = f"already_absent:{container.id[:12]}"
            return
        c.reload()
        c_labels = c.attrs["Config"].get("Labels") or {}
        assert c_labels.get("slaif184.owner") == owner, (
            "refusing to remove a container whose owner label changed"
        )
        c.stop(timeout=10)
        c.remove(force=True)
        _STATE["pg_cleanup"] = f"removed:{container.id[:12]}"



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


def _materialize_source_set(
    target: Path,
    *,
    set_name: str,
    rate: str,
    pricing_set: str | None = None,
    page_set: str | None = None,
    or_set: str | None = None,
) -> Path:
    """Materialize one controlled source set with canonical file names.

    ``pricing_set`` may differ from ``set_name``: the v3 research set reuses
    the v1 pricing rows with the v3 prose-layout model page, and v4 reuses
    the v2 pricing rows with the truncated model page (the provenance
    record documents each exact composition). ``page_set`` overrides the
    per-set model page choice when it differs from ``set_name``.
    ``or_set`` overrides ONLY the OpenRouter models file (v5 reuses the v2
    OpenAI pricing/page with the v5 OpenRouter rows - the provenance
    record documents each exact composition).
    """
    pricing_set = pricing_set or set_name
    or_set = or_set or pricing_set
    target.mkdir(parents=True, exist_ok=True)
    (target / "openrouter-models.json").write_bytes(
        (FIXTURE_DIR / f"openrouter-models-{or_set}.json").read_bytes()
    )
    (target / "openai-pricing.md").write_bytes(
        (FIXTURE_DIR / f"openai-pricing-{pricing_set}.md").read_bytes()
    )
    (target / "openai-models.md").write_bytes(
        (FIXTURE_DIR / "openai-models.md").read_bytes()
    )
    page_names = {
        "v1": "openai-gpt-3.5-turbo-captured-listitem.md",
        "v2": "openai-gpt-3.5-turbo-v2-price-derivative.md",
        "v3": None,  # referenced in place (183-b proven variant)
        "v4": "openai-gpt-3.5-turbo-v2-page-truncated.md",
        "v5": "openai-gpt-3.5-turbo-v2-price-derivative.md",
    }
    page_name = page_names[page_set or set_name]
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


def _sql_exec(url: str, query: str, params: dict | None = None) -> int:
    """Run ONE DML statement in an explicit committed transaction.

    ``_sql`` uses ``engine.connect()`` without a commit (read snapshots
    only; DML there would roll back). Deliberate test-setup edits need a
    real committed write, so they go through this tiny helper, which
    returns the affected row count for the caller to assert.
    """

    async def _run() -> int:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(url, future=True)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(query), params or {})
                return result.rowcount
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _digest_tree(root: Path) -> str:
    """Order-stable digest of every file under ``root`` (content only)."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(root)).encode("utf-8"))
            h.update(path.read_bytes())
    return h.hexdigest()


def _catalog_snapshot(url: str) -> str:
    """Order-stable digest of the catalog tables around a refusal probe."""
    providers = _sql(
        url,
        "SELECT * FROM provider_configs ORDER BY id",
    )
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
            "providers": [list(r) for r in providers],
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
        [
            str(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], bool(r[8]),
            bool(r[9]), bool(r[10]), json.dumps(r[11], sort_keys=True),
            r[12], str(r[13]),
        ]
        for r in _sql(
            db_url,
            "SELECT id, requested_model, match_type, endpoint, provider, "
            "upstream_model, priority, enabled, visible_in_models, "
            "supports_streaming, capabilities, notes, created_at, updated_at "
            "FROM model_routes ORDER BY requested_model",
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
        "SELECT id, requested_model, match_type, endpoint, provider, "
        "upstream_model, priority, enabled, visible_in_models, "
        "supports_streaming, capabilities, notes, created_at, updated_at "
        "FROM model_routes ORDER BY requested_model",
    )
    after_rows = [
        [
            str(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], bool(r[8]),
            bool(r[9]), bool(r[10]), json.dumps(r[11], sort_keys=True),
            r[12], str(r[13]),
        ]
        for r in routes
    ]
    assert after_rows == _STATE["route_rows_boot"], (
        "refresh must not create, drop, or modify ANY column of existing route rows"
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


def test_r5_installed_selection_and_refusals(
    installed_env: dict[str, str], installed_pg_url: str, tmp_path_factory
) -> None:
    """R5 (worksheet rows 13/14/16): installed model selection and
    refusal boundaries, each with actual DB state equality around the
    refusal (not only exit codes).

    (a) single-model scope filter: both-provider sources, one selected
        model, exclusions reconciled explicitly;
    (b) unknown requested model: BLOCKED collect run, empty proposal;
    (c) unsupported preset: child Typer refusal BEFORE any run is created;
    (d) unreachable baseline DB: refresh refused before collection,
        blocked run published, collection-not-started stage.
    """
    env = installed_env
    db_url = installed_pg_url
    scratch = tmp_path_factory.mktemp("slaif184-r5")
    fx_v1 = _materialize_source_set(scratch / "fx-v1", set_name="v1", rate="1.08")
    seal_key = scratch / "seal.key"
    _STATE["seal_key_r5"] = str(seal_key)

    # --- (a) single-model scope: only the selected model, explicit -------
    # reconciled exclusions (bootstrap == first_install baseline, so the
    # result is identical on any DB state; collect never writes the DB).
    run_root_a = scratch / "runs-a"
    snap_before = _catalog_snapshot(db_url)
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "bootstrap",
            "--models",
            "gpt-3.5-turbo",
            "--run-root",
            str(run_root_a),
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
        f"single-model bootstrap expected 10, got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "READY_WITH_WARNINGS"
    assert summary["warnings"] == 1 and summary["blockers"] == 0, summary
    run_dir = Path(urlparse(summary["run_dir"]).path)
    assert run_dir.parent == run_root_a or run_dir.parent == run_root_a.resolve()
    cr = json.loads((run_dir / "catalog-refresh.json").read_text(encoding="utf-8"))
    assert cr["selection"]["model_include"] == ["gpt-3.5-turbo"]
    assert cr["selection"]["providers"] == ["openai", "openrouter"]
    assert [m["model"] for m in cr["models"]] == ["gpt-3.5-turbo"]
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    counts = validation["counts"]
    assert counts["selected"] == 1 and counts["new"] == 1, counts
    # the other-provider models are reconciled EXPLICITLY, not silently
    # dropped from the inventory
    assert "2 reconciled exclusion(s)" in cr["notes"], cr["notes"]
    codes = [w["code"] for w in validation["warnings"]]
    assert codes == ["new_model_exposure"], codes
    assert _catalog_snapshot(db_url) == snap_before, "collect-only run changed the DB"
    _STATE["run_dir_r5a"] = str(run_dir)

    # --- (b) unknown requested model: BLOCKED, empty proposal ------------
    run_root_b = scratch / "runs-b"
    snap_before_b = _catalog_snapshot(db_url)
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "bootstrap",
            "--models",
            "nonexistent-model-x",
            "--run-root",
            str(run_root_b),
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
    assert proc.returncode == 20, (
        f"unknown-model bootstrap expected 20, got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "BLOCKED"
    assert summary["blockers"] == 4, summary
    assert "missing_required_selection" in summary["reason"], summary
    run_dir_b = Path(urlparse(summary["run_dir"]).path)
    assert run_dir_b.parent == run_root_b or run_dir_b.parent == run_root_b.resolve()
    cr_b = json.loads((run_dir_b / "catalog-refresh.json").read_text(encoding="utf-8"))
    assert cr_b["models"] == []
    assert _catalog_snapshot(db_url) == snap_before_b, "blocked run changed the DB"
    _STATE["run_dir_r5b"] = str(run_dir_b)

    # --- (c) unsupported preset: refused before any run is created -------
    run_root_c = scratch / "runs-c"
    snap_before_c = _catalog_snapshot(db_url)
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "bootstrap",
            "--profile",
            "enterprise-v2",
            "--run-root",
            str(run_root_c),
            "--seal-key",
            str(seal_key),
            "--json",
            "--timeout",
            "120",
        ],
        cwd=scratch,
        extra={"SLAIF184_FIXTURE_DIR": str(fx_v1)},
        timeout=120,
    )
    assert proc.returncode == 2, (
        f"unsupported preset expected Typer refusal (2), got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert "only the standard-v1 profile exists in this version" in proc.stderr
    assert not run_root_c.exists() or not any(run_root_c.iterdir()), (
        "preset refusal must not create a run"
    )
    assert _catalog_snapshot(db_url) == snap_before_c

    # --- (d) unreachable baseline DB: refused BEFORE collection ----------
    run_root_d = scratch / "runs-d"
    snap_before_d = _catalog_snapshot(db_url)
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "refresh",
            "--db-url",
            "postgresql+asyncpg://test:test@127.0.0.1:1/nope",
            "--run-root",
            str(run_root_d),
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
    assert proc.returncode == 20, (
        f"unreachable-baseline refresh expected 20, got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "BLOCKED"
    assert summary["stage"].startswith("collection not started"), summary
    assert "baseline_export_failed" in summary["reason"], summary
    run_dir_d = Path(urlparse(summary["run_dir"]).path)
    assert run_dir_d.name.startswith("blocked-baseline_export_failed"), run_dir_d.name
    assert run_dir_d.parent == run_root_d or run_dir_d.parent == run_root_d.resolve()
    assert _catalog_snapshot(db_url) == snap_before_d, "blocked refresh changed the DB"


QUALIFIED_CODX_CLI = (
    Path("/home/janezp/.codex/packages/standalone/releases/")
    / "0.162.1-x86_64-unknown-linux-musl"
    / "bin"
    / "codex"
)
QUALIFIED_CODX_CLI_SHA256 = (
    "628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1"
)
PACKAGED_RESEARCH_TEMPLATE_SHA256 = (
    "5ba7ff44d58fa21f7d020fbb793e5611bfb416b0475e5d92e23d566a45081d18"
)


@pytest.mark.skipif(
    not QUALIFIED_CODX_CLI.is_file(),
    reason="R6 requires the exact qualified Codex CLI 0.162.1 at the recorded path",
)
@requires_boundary
def test_r6_installed_research_fallback(
    installed_env: dict[str, str], tmp_path_factory
) -> None:
    """R6 (worksheet row 9): the useful isolated-Codex fallback through the
    INSTALLED refresh with the packaged template/schema assets and the REAL
    qualified CLI 0.162.1. The mock substitution is transport-only (the
    documented fixture seam): the real Codex worker still executes inside
    the enforced outer boundary; no physical network, no live model.

    Skips only on machines without the qualified CLI/Docker boundary (the
    183 capability marker); on the qualified host this case is REQUIRED and
    must pass (the local run at the final head is the recorded evidence).

    Source set v3 = v1 pricing + prose-layout OpenAI model page whose limit
    lines the deterministic parser cannot resolve -> exactly two eligible
    facts -> canned qualified research result fills both.
    """
    env = installed_env
    scratch = tmp_path_factory.mktemp("slaif184-r6")
    fx_v3 = _materialize_source_set(
        scratch / "fx-v3", set_name="v3", rate="1.08", pricing_set="v1"
    )
    seal_key = scratch / "seal.key"

    assert _sha256_file(QUALIFIED_CODX_CLI) == QUALIFIED_CODX_CLI_SHA256, (
        "qualified Codex CLI bytes changed"
    )

    from tests.integration.test_catalog_refresh_research_codex import _tool_call_sse

    seq_file = scratch / "tool-sequence.sse"
    seq_file.write_text(
        _tool_call_sse("synthetic/research", {"cmd": "cat /workspace/inputs/evidence"}),
        encoding="utf-8",
    )
    result_file = FIXTURE_DIR / "research-canned-result.json"

    run_root = scratch / "runs-research"
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode",
            "bootstrap",
            "--providers",
            "openai",
            "--run-root",
            str(run_root),
            "--seal-key",
            str(seal_key),
            "--json",
            "--timeout",
            "300",
            "--research",
            "--research-cli-bin",
            str(QUALIFIED_CODX_CLI),
            "--research-endpoint",
            "https://synthetic.invalid/v1",
            "--research-model",
            "synthetic/research",
            "--research-auth-env",
            "SLAIF184_SYNTHETIC_KEY",
        ],
        cwd=scratch,
        extra={
            "SLAIF184_FIXTURE_DIR": str(fx_v3),
            "SLAIF184_SYNTHETIC_KEY": "sk-synthetic-184-not-real",
            "SLAIF184_MOCK_RESEARCH": json.dumps(
                {
                    "result_file": str(result_file),
                    "tool_sequence_file": str(seq_file),
                }
            ),
        },
        timeout=600,
    )
    assert proc.returncode == 10, (
        f"research bootstrap expected READY_WITH_WARNINGS (10), "
        f"got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "READY_WITH_WARNINGS"
    assert summary["warnings"] == 2 and summary["blockers"] == 0, summary
    run_dir = Path(urlparse(summary["run_dir"]).path)
    assert run_dir.parent == run_root or run_dir.parent == run_root.resolve()

    cr = json.loads((run_dir / "catalog-refresh.json").read_text(encoding="utf-8"))
    research = cr["research"]
    assert research["status"] == "SUCCEEDED", research
    assert research["mock_model"] is True
    assert research["cli_sha256"] == QUALIFIED_CODX_CLI_SHA256, research
    assert research["codex_version"] != "N/A", research
    # the template is the PACKAGED wheel asset, not a source-checkout path
    assert research["template_sha256"] == PACKAGED_RESEARCH_TEMPLATE_SHA256, research
    assert (
        research["facts_requested"] == 2
        and research["facts_returned"] == 2
        and research["facts_accepted"] == 2
        and research["facts_rejected"] == 0
    ), research
    assert len(cr["research_facts"]) == 2, cr["research_facts"]

    assert [m["model"] for m in cr["models"]] == ["gpt-3.5-turbo"]
    model = cr["models"][0]
    # deterministic pricing + semantically researched limits
    assert model["context_length"] == 16385
    assert model["max_output_tokens"] == 4096
    assert model["provenance"]["extraction"] == "semantic", model["provenance"]

    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    codes = [w["code"] for w in validation["warnings"]]
    # the useful docs-page fallback carries BOTH mandatory REVIEW codes:
    # the new-model exposure and the semantic-method disclosure that the
    # apply-time ACK guard still requires
    assert sorted(codes) == ["new_model_exposure", "research_semantic_method"], codes

    # installed verify over the sealed research run
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
    _STATE["run_dir_research"] = str(run_dir)


def test_r7_installed_apply_negatives(
    installed_env: dict[str, str], installed_pg_url: str, tmp_path_factory
) -> None:
    """R7 (worksheet rows 18/19): installed apply/verify refusals with
    actual DB state equality around each refusal.

    Seal/authentication refusals and the blocked-state refusal happen
    BEFORE database contact; the unacknowledged-findings refusal happens
    after the known-committed lookup inside the locked transaction, so
    that case also proves the live DB is untouched.
    """
    env = installed_env
    db_url = installed_pg_url
    scratch = tmp_path_factory.mktemp("slaif184-r7")
    ready_run = Path(_STATE["run_dir_r5a"])
    blocked_run = Path(_STATE["run_dir_r5b"])
    # an EXISTING run tree the watchdog run must not touch
    boot_root = ready_run.parent
    # the R5 runs were sealed with THEIR OWN key; authenticating them with
    # the bootstrap key would test the wrong-key path, not the state path
    seal_key = Path(_STATE["seal_key_r5"])
    assert ready_run.is_dir() and blocked_run.is_dir() and seal_key.is_file()
    snap0 = _catalog_snapshot(db_url)

    fx_v1 = _materialize_source_set(scratch / "fx-v1", set_name="v1", rate="1.08")

    def verify(run_dir: Path, key: Path) -> subprocess.CompletedProcess:
        return _run_installed(
            env,
            [
                "slaif-gateway", "catalog-refresh", "verify",
                "--run-dir", str(run_dir), "--seal-key", str(key), "--json",
            ],
            cwd=scratch,
            timeout=120,
        )

    def apply_argv(run_dir: Path, key: Path, *extra: str) -> list[str]:
        return [
            "slaif-gateway", "catalog-refresh", "apply",
            "--run-dir", str(run_dir), "--db-url", db_url,
            "--seal-key", str(key), *extra, "--json",
        ]

    def bundle_sha(run_dir: Path) -> str:
        return json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))[
            "semantic_bundle_sha256"
        ]

    def app_rows_for(bundle: str) -> list:
        return _sql(
            db_url,
            "SELECT bundle_sha256, plan_sha256, outcome FROM catalog_refresh_applications "
            "WHERE bundle_sha256 = :b",
            {"b": bundle},
        )

    # --- (r1) BLOCKED run is not applicable: refused before DB contact ----
    proc = _run_installed(
        env,
        apply_argv(blocked_run, seal_key, "--confirm", "--actor", "oap-184-r7",
                   "--reason", "negative: blocked run must not apply"),
        cwd=scratch,
        timeout=120,
    )
    assert proc.returncode == 20, (
        f"blocked-run apply expected 20, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "apply_state_not_applicable" in proc.stderr, proc.stderr
    assert app_rows_for(bundle_sha(blocked_run)) == []
    assert _catalog_snapshot(db_url) == snap0, "r1 changed the DB"

    # --- (r2) unsealed run (receipt removed): verify AND apply refuse -----
    unsealed = scratch / "runs" / "unsealed"
    unsealed.parent.mkdir()

    shutil.copytree(ready_run, unsealed)
    (unsealed / "receipt.json").unlink()
    vproc = verify(unsealed, seal_key)
    assert vproc.returncode == 30, vproc.stderr
    aproc = _run_installed(
        env,
        apply_argv(unsealed, seal_key, "--confirm", "--actor", "oap-184-r7",
                   "--reason", "negative: unsealed run must not apply"),
        cwd=scratch,
        timeout=120,
    )
    assert aproc.returncode == 30, (
        f"unsealed apply expected 30, got {aproc.returncode}\n{aproc.stdout}\n{aproc.stderr}"
    )
    assert _catalog_snapshot(db_url) == snap0, "r2 changed the DB"

    # --- (r3) tampered proposal byte: verify AND apply refuse -------------
    tampered = scratch / "runs" / "tampered"
    shutil.copytree(ready_run, tampered)
    tsv = tampered / "pricing-proposal.tsv"
    data = bytearray(tsv.read_bytes())
    data[-1] = (data[-1] + 1) % 256
    tsv.write_bytes(bytes(data))
    vproc = verify(tampered, seal_key)
    assert vproc.returncode == 30, vproc.stderr
    aproc = _run_installed(
        env,
        apply_argv(tampered, seal_key, "--confirm", "--actor", "oap-184-r7",
                   "--reason", "negative: tampered run must not apply"),
        cwd=scratch,
        timeout=120,
    )
    assert aproc.returncode == 30, (
        f"tampered apply expected 30, got {aproc.returncode}\n{aproc.stdout}\n{aproc.stderr}"
    )
    assert _catalog_snapshot(db_url) == snap0, "r3 changed the DB"

    # --- (r4) wrong seal key: verify AND apply refuse ----------------------
    wrong_key = scratch / "wrong-seal.key"
    # a DIFFERENT but valid key (64 lowercase hex chars, 0600): an invalid
    # format would exit 65 and would not prove the authentication refusal
    wrong_key.write_bytes(os.urandom(32).hex().encode("ascii"))
    wrong_key.chmod(0o600)
    vproc = verify(ready_run, wrong_key)
    assert vproc.returncode == 30, vproc.stderr
    aproc = _run_installed(
        env,
        apply_argv(ready_run, wrong_key, "--confirm", "--actor", "oap-184-r7",
                   "--reason", "negative: wrong key must not apply"),
        cwd=scratch,
        timeout=120,
    )
    assert aproc.returncode == 30, (
        f"wrong-key apply expected 30, got {aproc.returncode}\n{aproc.stdout}\n{aproc.stderr}"
    )
    assert _catalog_snapshot(db_url) == snap0, "r4 changed the DB"

    # --- (r5) missing confirm/actor/reason: refused before DB contact -----
    intent_cases = {
        "confirm": ["--actor", "oap-184-r7", "--reason", "negative: missing confirm"],
        "actor": ["--confirm", "--reason", "negative: missing actor"],
        "reason": ["--confirm", "--actor", "oap-184-r7"],
    }
    for label, extra in intent_cases.items():
        proc = _run_installed(
            env,
            apply_argv(ready_run, seal_key, *extra),
            cwd=scratch,
            timeout=120,
        )
        assert proc.returncode == 65, (
            f"missing-{label} apply expected 65, got {proc.returncode}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    assert _catalog_snapshot(db_url) == snap0, "r5 changed the DB"

    # --- (r6) unacknowledged warning: refused inside the locked ----------
    # transaction after the known-committed lookup; DB untouched.
    snap_before = _catalog_snapshot(db_url)
    ready_bundle = bundle_sha(ready_run)
    assert app_rows_for(ready_bundle) == []
    proc = _run_installed(
        env,
        apply_argv(ready_run, seal_key, "--confirm", "--actor", "oap-184-r7",
                   "--reason", "negative: unacked findings must not apply"),
        cwd=scratch,
        timeout=180,
    )
    assert proc.returncode == 10, (
        f"unacked apply expected 10, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "apply_warnings_unacknowledged" in proc.stderr, proc.stderr
    assert app_rows_for(ready_bundle) == []
    assert _catalog_snapshot(db_url) == snap_before, "unacked refusal changed the DB"

    # --- (r8) wrong baseline source for a bootstrap bundle ---------------
    # (worksheet row 14, installed representative): the bootstrap bundle
    # declares the first-install baseline, so ANY live baseline source is
    # a wrong-baseline invocation and is refused at the wrapper boundary
    # before the child is spawned.
    run_root_r8 = scratch / "runs-r8"
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode", "bootstrap",
            "--db-url", db_url,
            "--run-root", str(run_root_r8),
            "--seal-key", str(seal_key),
            "--json", "--timeout", "120",
        ],
        cwd=scratch,
        extra={"SLAIF184_FIXTURE_DIR": str(fx_v1)},
        timeout=120,
    )
    assert proc.returncode == 65, (
        f"wrong-baseline bootstrap expected 65, got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert (
        "--mode bootstrap cannot be combined with --baseline-file or --db-url"
        in proc.stderr
    ), proc.stderr
    assert not run_root_r8.exists() or not any(run_root_r8.iterdir())
    assert _catalog_snapshot(db_url) == snap0, "r8 changed the DB"

    # --- (r9) forced source outage: honest failed-collect labeling -------
    # (worksheet rows 15/24, installed representative): one official
    # source refuses retrieval (simulated at the documented seam); the
    # run is BLOCKED with the attempted-and-failed stage, no sealed
    # collected review, and no DB contact of any kind.
    run_root_r9 = scratch / "runs-r9"
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode", "bootstrap",
            "--providers", "openai",
            "--run-root", str(run_root_r9),
            "--seal-key", str(seal_key),
            "--json", "--timeout", "120",
        ],
        cwd=scratch,
        extra={
            "SLAIF184_FIXTURE_DIR": str(fx_v1),
            "SLAIF184_FAIL_URLS": "https://developers.openai.com/api/docs/pricing.md",
        },
        timeout=120,
    )
    assert proc.returncode == 20, (
        f"forced-outage bootstrap expected 20, got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "BLOCKED"
    assert summary["stage"].startswith(
        "collection attempted and failed before completion"
    ), summary
    assert "collection failed" in summary["reason"], summary
    run_dir_r9 = Path(urlparse(summary["run_dir"]).path)
    assert run_dir_r9.name.startswith("blocked-fixture_forced_failure"), run_dir_r9.name
    # an incomplete collection never yields a sealed collected review
    assert not (run_dir_r9 / "receipt.json").is_file()
    assert not (run_dir_r9 / "catalog-refresh.json").is_file()
    assert (run_dir_r9 / "REVIEW.html").is_file()
    assert _catalog_snapshot(db_url) == snap0, "r9 changed the DB"

    # --- (r10) research CLI that cannot prove its identity ---------------
    # (worksheet rows 9/24, installed representative): a research CLI
    # binary that hashes but cannot report its version (not executable)
    # refuses the phase BEFORE any invocation (safe UNAVAILABLE code);
    # the unresolved facts then block the review deterministically. No
    # crash, no fabricated measured identity, no DB contact.
    fake_cli = scratch / "fake-codex"
    fake_cli.write_text("not an executable codex binary\n", encoding="utf-8")
    fx_v3 = _materialize_source_set(
        scratch / "fx-v3", set_name="v3", rate="1.08", pricing_set="v1"
    )
    run_root_r10 = scratch / "runs-r10"
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode", "bootstrap",
            "--providers", "openai",
            "--run-root", str(run_root_r10),
            "--seal-key", str(seal_key),
            "--json", "--timeout", "300",
            "--research",
            "--research-cli-bin", str(fake_cli),
            "--research-endpoint", "https://synthetic.invalid/v1",
            "--research-model", "synthetic/research",
            "--research-auth-env", "SLAIF184_SYNTHETIC_KEY",
        ],
        cwd=scratch,
        extra={
            "SLAIF184_FIXTURE_DIR": str(fx_v3),
            "SLAIF184_SYNTHETIC_KEY": "sk-synthetic-184-not-real",
        },
        timeout=600,
    )
    assert proc.returncode == 20, (
        f"unversioned-CLI research bootstrap expected 20, got {proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    summary = _summary(proc)
    assert summary["state"] == "BLOCKED", summary
    assert summary["stage"].startswith("live collection"), summary
    assert "collection_empty_bootstrap" in summary["reason"], summary
    run_dir_r10 = Path(urlparse(summary["run_dir"]).path)
    cr_r10 = json.loads((run_dir_r10 / "catalog-refresh.json").read_text(encoding="utf-8"))
    research_r10 = cr_r10["research"]
    assert research_r10["status"] == "UNAVAILABLE", research_r10
    assert research_r10["failure_code"] == "cli_unversioned", research_r10
    assert research_r10["cli_sha256"] is None, research_r10
    assert research_r10["facts_requested"] == 0 and research_r10["facts_returned"] == 0
    # the model whose required facts stayed unresolved is EXCLUDED from the
    # proposal (never invented), and the exclusion is reconciled explicitly
    assert cr_r10["models"] == []
    assert "Codex research UNAVAILABLE (cli_unversioned)" in cr_r10["notes"], cr_r10["notes"]
    assert "1 reconciled exclusion(s)" in cr_r10["notes"], cr_r10["notes"]
    assert _catalog_snapshot(db_url) == snap0, "r10 changed the DB"

    # --- (r7) watchdog: stalled collect killed, no run published ----------
    stall_root = scratch / "runs-stall"
    boot_digest_before = _digest_tree(boot_root)
    env_extra = {
        "SLAIF184_FIXTURE_DIR": str(fx_v1),
        "SLAIF184_STALL_SECONDS": "60",
    }
    proc = _run_installed(
        env,
        [
            "slaif-catalog-refresh",
            "--mode", "bootstrap",
            "--run-root", str(stall_root),
            "--seal-key", str(seal_key),
            "--json", "--timeout", "10", "--kill-grace", "2",
        ],
        cwd=scratch,
        extra=env_extra,
        timeout=120,
    )
    assert proc.returncode in (124, 137), (
        f"watchdog expected 124/137, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert not stall_root.exists() or not any(stall_root.iterdir()), (
        "watchdog-killed collect must not publish a run"
    )
    assert _digest_tree(boot_root) == boot_digest_before, (
        "watchdog run must not touch existing runs"
    )


def test_r7b_installed_apply_boundary_negatives(
    installed_env: dict[str, str], installed_pg_url: str, tmp_path_factory
) -> None:
    """R7 apply boundary (worksheet rows 14/20/29): two installed
    authenticated-run refusals beyond the sealed-run negatives, each with
    actual DB state equality. Both runs are UNAPPLIED refreshes that carry
    a NON-EMPTY apply plan (changed v1 sources against the current v2
    baseline), so the sealed-document plan check passes and the intended
    execution gate is the one under test.

    (a) stale-at-apply: the apply-time wall clock (the existing
        apply.datetime seam, shifted by an explicit finite test-only
        substitution in the qualification venv) ages every source beyond
        the blocked threshold: exact apply_freshness_blocked with
        source_stale_blocked, no DB mutation, no application record. The
        host clock is never touched; the known-committed-first lookup
        still runs before the current gates (this run has no prior
        application record, so the freshness gate is what refuses).
    (b) baseline drift: a fresh UNAPPLIED reviewed refresh is taken, then
        ONE ordinary catalog row is deliberately changed AFTER review
        (the deliberate test-setup edit, executed separately and
        identified on its own), and the acknowledged installed apply is
        refused with the exact apply_baseline_stale code: the refused
        operation adds no mutation on top of the deliberate edit.
    """
    env = installed_env
    db_url = installed_pg_url
    scratch = tmp_path_factory.mktemp("slaif184-r7b")
    seal_key = Path(_STATE["seal_key"])
    # v1 sources against the post-R4b (v2) baseline: real price/FX
    # movements -> non-empty authenticated apply plan.
    fx_v1 = _materialize_source_set(scratch / "fx-v1", set_name="v1", rate="1.08")

    def ack_codes_for(run_dir: Path) -> str:
        validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
        return ",".join(sorted({w["code"] for w in validation["warnings"]}))

    def ready_refresh_with_changes(tag: str) -> Path:
        root = scratch / f"runs-{tag}"
        proc = _run_installed(
            env,
            [
                "slaif-catalog-refresh",
                "--mode", "refresh",
                "--db-url", db_url,
                "--run-root", str(root),
                "--seal-key", str(seal_key),
                "--json", "--timeout", "120",
            ],
            cwd=scratch,
            extra={"SLAIF184_FIXTURE_DIR": str(fx_v1)},
            timeout=300,
        )
        assert proc.returncode == 10, (
            f"{tag} refresh expected READY_WITH_WARNINGS (10), "
            f"got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        )
        summary = _summary(proc)
        assert summary["state"] == "READY_WITH_WARNINGS", summary
        run_dir = Path(urlparse(summary["run_dir"]).path)
        validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
        assert validation.get("apply_plan", {}).get("operations"), (
            f"{tag}: a non-empty authenticated apply plan is required for this case"
        )
        vproc = _run_installed(
            env,
            [
                "slaif-gateway", "catalog-refresh", "verify",
                "--run-dir", str(run_dir), "--seal-key", str(seal_key), "--json",
            ],
            cwd=scratch,
            timeout=120,
        )
        assert vproc.returncode == 0, vproc.stderr
        return run_dir

    def apply_argv(run_dir: Path, reason: str, *, ack: bool = False) -> list[str]:
        argv = [
            "slaif-gateway", "catalog-refresh", "apply",
            "--run-dir", str(run_dir),
            "--db-url", db_url,
            "--seal-key", str(seal_key),
            "--confirm", "--actor", "oap-184-r7b", "--reason", reason,
        ]
        if ack:
            argv += ["--ack-warnings", ack_codes_for(Path(run_dir))]
        argv.append("--json")
        return argv

    # --- (a) stale at apply: finite test-only clock shift at the seam -----
    stale_run = ready_refresh_with_changes("stale")
    snap_a0 = _catalog_snapshot(db_url)
    aged_extra = {
        "SLAIF184_FIXTURE_DIR": str(fx_v1),
        # 8 days: beyond the 72h source blocked threshold (and the 7d FX
        # blocked threshold) for an otherwise-fresh authenticated run.
        "SLAIF184_APPLY_AGE_SECONDS": str(8 * 24 * 3600),
    }
    aproc = _run_installed(
        env,
        apply_argv(stale_run, "negative: aged apply must be refused on freshness"),
        cwd=scratch,
        extra=aged_extra,
        timeout=180,
    )
    assert aproc.returncode == 20, (
        f"aged apply expected BLOCKED (20), got {aproc.returncode}\n"
        f"{aproc.stdout}\n{aproc.stderr}"
    )
    assert "apply_freshness_blocked" in aproc.stderr, aproc.stderr
    assert "source_stale_blocked" in aproc.stderr, aproc.stderr
    assert _catalog_snapshot(db_url) == snap_a0, "aged refusal changed the DB"
    # deterministic repeat: still refused, still no application record
    aproc2 = _run_installed(
        env,
        apply_argv(stale_run, "negative: aged apply repeat"),
        cwd=scratch,
        extra=aged_extra,
        timeout=180,
    )
    assert aproc2.returncode == 20, (
        f"aged apply repeat expected 20, got {aproc2.returncode}\n"
        f"{aproc2.stdout}\n{aproc2.stderr}"
    )
    assert "apply_freshness_blocked" in aproc2.stderr, aproc2.stderr
    apps = _sql(
        db_url,
        "SELECT count(*) FROM catalog_refresh_applications WHERE run_id = :run",
        {"run": Path(stale_run).name},
    )
    assert apps[0][0] == 0, "aged refusal must not record an application"

    # --- (b) deliberate post-review baseline drift -------------------------
    drift_run = ready_refresh_with_changes("drift")
    snap_b0 = _catalog_snapshot(db_url)
    # Deliberate TEST-SETUP edit, identified separately from the refused
    # operation: one ordinary active pricing row, nudged AFTER the review,
    # committed through an explicit transaction (read-snapshot _sql would
    # roll DML back).
    assert _sql_exec(
        db_url,
        "UPDATE pricing_rules SET input_price_per_1m = input_price_per_1m + 0.000001 "
        "WHERE provider = 'openai' AND upstream_model = 'gpt-3.5-turbo' "
        "AND valid_until IS NULL",
    ) == 1, "deliberate test-setup edit must touch exactly one row"
    snap_b1 = _catalog_snapshot(db_url)
    assert snap_b1 != snap_b0, "deliberate test-setup edit did not take effect"
    bproc = _run_installed(
        env,
        apply_argv(drift_run, "negative: drifted baseline must be refused", ack=True),
        cwd=scratch,
        timeout=180,
    )
    assert bproc.returncode == 65, (
        f"drifted apply expected 65, got {bproc.returncode}\n"
        f"{bproc.stdout}\n{bproc.stderr}"
    )
    assert "apply_baseline_stale" in bproc.stderr, bproc.stderr
    assert "pricing_rules" in bproc.stderr, bproc.stderr
    assert _catalog_snapshot(db_url) == snap_b1, (
        "refused apply changed the DB beyond the deliberate test-setup edit"
    )
    # Deliberate test-setup cleanup: the nudged row is restored to the
    # reviewed value (identified separately; the refusal proofs above are
    # unaffected by this restoration).
    assert _sql_exec(
        db_url,
        "UPDATE pricing_rules SET input_price_per_1m = input_price_per_1m - 0.000001 "
        "WHERE provider = 'openai' AND upstream_model = 'gpt-3.5-turbo' "
        "AND valid_until IS NULL",
    ) == 1, "cleanup of the deliberate edit must touch exactly one row"
    assert _catalog_snapshot(db_url) == snap_b0, (
        "cleanup of the deliberate edit did not restore the pre-edit state"
    )


def test_r7c_installed_refresh_source_failures(
    installed_env: dict[str, str], installed_pg_url: str, tmp_path_factory
) -> None:
    """R7 source-failure closure (worksheet rows 8/12/15): SELECTED
    unsupported billing and a malformed/truncated REFRESH source, each
    through the installed command with an explicit ``--models`` selection,
    with actual DB state equality.

    Both are distinct mechanisms: (a) a billing-representability refusal
    decided from the observed pricing rows (no transport outage, no parser
    failure - the model page is never fetched), and (b) a parser rejection
    of received bytes (not a transport outage: the bytes were delivered
    and the parser refused them).

    Contract pinned here (184 observed-model refusal): a selected
    in-baseline model that is OBSERVED in the collection inventory but
    cannot be safely proposed is BLOCKED (20) with the exact machine
    reason, the observation is retained with its exact inventory entry,
    the model is never reported as absent from the source set, and no DB
    mutation occurs; apply refuses the sealed BLOCKED state before any
    plan use or DB contact (the run is not actionable).

    FX design note: both sets materialize the 1.08 quote against the
    post-R4b stored 1.12-derived rate, i.e. a genuine FX movement, so the
    FX import gate is a clean executable supersession (VERIFIED) and the
    selection blocker is the ONLY refusal under test. A same-rate
    unchanged fixture date is a separate conservative import gate
    (window conflict without a state change) and is out of scope here.
    """
    env = installed_env
    db_url = installed_pg_url
    scratch = tmp_path_factory.mktemp("slaif184-r7c")
    seal_key = Path(_STATE["seal_key"])

    def refresh_collect(tag: str, fx_dir: Path, model: str):
        root = scratch / f"runs-{tag}"
        proc = _run_installed(
            env,
            [
                "slaif-catalog-refresh",
                "--mode", "refresh",
                "--db-url", db_url,
                "--models", model,
                "--run-root", str(root),
                "--seal-key", str(seal_key),
                "--json", "--timeout", "120",
            ],
            cwd=scratch,
            extra={"SLAIF184_FIXTURE_DIR": str(fx_dir)},
            timeout=300,
        )
        summary = _summary(proc)
        run_dir = Path(urlparse(summary["run_dir"]).path)
        return proc, summary, run_dir

    def inventory_entry(cr: dict, provider: str, model: str) -> dict:
        entries = [
            e for e in cr["collection"]["inventory"]
            if e["provider"] == provider and e["model"] == model
        ]
        assert len(entries) == 1, f"inventory for {provider}/{model}: {entries}"
        return entries[0]

    def assert_sealed_blocked_not_actionable(run_dir: Path) -> None:
        """A BLOCKED refresh is not actionable: apply refuses the sealed
        BLOCKED state before any plan use or DB contact (exact code; the
        CLI maps CatalogRefreshBlockedError to exit 20)."""
        aproc = _run_installed(
            env,
            [
                "slaif-gateway", "catalog-refresh", "apply",
                "--run-dir", str(run_dir),
                "--db-url", db_url,
                "--seal-key", str(seal_key),
                "--confirm", "--actor", "oap-184-r7c",
                "--reason", "negative: blocked run must not apply",
                "--json",
            ],
            cwd=scratch,
            timeout=180,
        )
        assert aproc.returncode == 20, (
            f"blocked-run apply expected 20, got {aproc.returncode}\n"
            f"{aproc.stdout}\n{aproc.stderr}"
        )
        assert "apply_state_not_applicable" in aproc.stderr, aproc.stderr

    def assert_selected_refusal(
        tag: str,
        proc,
        summary,
        run_dir: Path,
        *,
        provider: str,
        model: str,
        disposition: str,
        reason_code: str,
        extra_codes: tuple[str, ...] = (),
    ) -> None:
        assert proc.returncode == 20, (
            f"{tag} selected-refresh expected BLOCKED (20), "
            f"got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        )
        assert summary["state"] == "BLOCKED", summary
        cr = json.loads((run_dir / "catalog-refresh.json").read_text(encoding="utf-8"))
        validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
        codes = {w["code"] for w in validation["warnings"]}
        assert "explicitly_selected_not_proposable" in codes, sorted(codes)
        assert "model_disappeared" not in codes, sorted(codes)
        for code in extra_codes:
            assert code in codes, (code, sorted(codes))
        # the observed fact with its exact machine reason
        entry = inventory_entry(cr, provider, model)
        assert entry["disposition"] == disposition, entry
        assert entry["reason_code"] == reason_code, entry
        # nothing is proposed: the observed model is retained locally
        assert cr["models"] == [], cr["models"]
        assert_sealed_blocked_not_actionable(run_dir)

    # --- (a) SELECTED unsupported billing (positive per-request fee) -------
    fx_v5 = _materialize_source_set(
        scratch / "fx-v5", set_name="v5", rate="1.08",
        pricing_set="v2", page_set="v2", or_set="v5",
    )
    snap0 = _catalog_snapshot(db_url)
    proc, summary, run_dir = refresh_collect("billing", fx_v5, "syn/orc-a")
    assert_selected_refusal(
        "selected unsupported-billing", proc, summary, run_dir,
        provider="openrouter", model="syn/orc-a",
        disposition="excluded_subset",
        reason_code="request_charges_unrepresentable",
    )
    # no deletion: the reviewed local rows are retained; no mutation at all
    assert _sql(db_url, "SELECT count(*) FROM model_routes WHERE requested_model = 'syn/orc-a'")[0][0] == 1
    assert _sql(db_url, "SELECT count(*) FROM pricing_rules WHERE provider = 'openrouter' AND upstream_model = 'syn/orc-a' AND valid_until IS NULL")[0][0] == 1
    assert _catalog_snapshot(db_url) == snap0, "unsupported-billing refresh changed the DB"

    # --- (b) SELECTED malformed/truncated REFRESH source (parser) ----------
    fx_v4 = _materialize_source_set(
        scratch / "fx-v4", set_name="v4", rate="1.08",
        pricing_set="v2", page_set="v4",
    )
    proc, summary, run_dir = refresh_collect("truncated", fx_v4, "gpt-3.5-turbo")
    assert_selected_refusal(
        "selected truncated-source", proc, summary, run_dir,
        provider="openai", model="gpt-3.5-turbo",
        disposition="incomplete",
        reason_code="page_parse_failed",
        extra_codes=("source_evidence_parse_failed",),
    )
    # the exact parser code is preserved in the retained observation detail
    entry = next(
        e for e in json.loads((run_dir / "catalog-refresh.json").read_text(encoding="utf-8"))["collection"]["inventory"]
        if e["provider"] == "openai" and e["model"] == "gpt-3.5-turbo"
    )
    assert "openai_model_doc:malformed_price_row" in entry["detail"], entry
    # no deletion: the reviewed local rows are retained; no mutation at all
    assert _sql(db_url, "SELECT count(*) FROM model_routes WHERE requested_model = 'gpt-3.5-turbo'")[0][0] == 1
    assert _sql(db_url, "SELECT count(*) FROM pricing_rules WHERE provider = 'openai' AND upstream_model = 'gpt-3.5-turbo' AND valid_until IS NULL")[0][0] == 1
    assert _catalog_snapshot(db_url) == snap0, "truncated-source refresh changed the DB"


def test_r8_installed_report_browser_gates(tmp_path_factory) -> None:
    """R8 (worksheet rows 2/3/22): the EXACT sealed installed artifacts
    (bootstrap, price+FX refresh, blocked selection) pass the unchanged
    browser decision-surface gates: JS-off, exactly one document request,
    static offline HTML, internal link targets, first-screen 1440x900
    selectors, 1440/1280/375 collapsed+expanded widths, font floors,
    visible decision values, and executed print for the price/FX reports.

    The gate is the UNCHANGED helper of tests/browser (the CI renderer
    gates stay there); this integration case gates the exact installed
    sealed runs. Skips honestly when Chromium is unavailable on the
    machine; the local run at the final head is the recorded evidence.
    """
    bootstrap_run = Path(_STATE["run_dir_boot"])
    refresh_run = Path(_STATE["run_dir_refresh"])
    blocked_run = Path(_STATE["run_dir_r5b"])
    for run_dir in (bootstrap_run, refresh_run, blocked_run):
        assert (run_dir / "REVIEW.html").is_file(), f"missing run: {run_dir}"

    playwright_sync = pytest.importorskip("playwright.sync_api")
    try:
        with playwright_sync.sync_playwright() as probe_pw:
            probe = probe_pw.chromium.launch()
            probe.close()
    except Exception as exc:  # noqa: BLE001 - a missing toolchain is a skip
        pytest.skip(f"playwright chromium unavailable: {exc}")

    from tests.browser.test_catalog_refresh_report import _check_case

    out_dir = tmp_path_factory.mktemp("slaif184-r8")
    cases = {
        "installed-bootstrap-184": (
            bootstrap_run / "REVIEW.html",
            {
                "has_sources": True,
                "pdf": True,
                "visible": (
                    "gpt-3.5-turbo",
                    "syn/orc-a",
                    "syn/orc-b",
                    "0.925925926",
                    "new_model_exposure",
                ),
            },
        ),
        "installed-refresh-184": (
            refresh_run / "REVIEW.html",
            {
                "has_sources": True,
                "pdf": True,
                "visible": (
                    "gpt-3.5-turbo",
                    "syn/orc-a",
                    "0.925925926",
                    "0.892857143",
                    "0.75",
                    "price_moved_review",
                    "fx_moved_review",
                ),
            },
        ),
        "installed-blocked-184": (
            blocked_run / "REVIEW.html",
            {
                "has_sources": True,
                "pdf": False,
                "visible": ("BLOCKED", "missing_required_selection"),
            },
        ),
    }
    metrics: dict = {}
    with playwright_sync.sync_playwright() as pw:
        for case, (html_path, expected) in cases.items():
            _check_case(pw, case, html_path, expected, out_dir, metrics)
    (out_dir / "metrics-final.json").write_text(
        json.dumps(metrics, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
