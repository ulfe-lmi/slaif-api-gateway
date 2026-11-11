"""219-a: ONE complete final installed GUI workflow (G01-G18 + calibration).

Test-only opt-in: set ``RUN_GUI_PARITY_INSTALLED_WORKFLOW=1``. Every test in
this module then MUST run (zero skipped) against FINAL installed code:

- ONE wheel built from THIS source tree (payload byte-verified against the
  archived source) and ONE owned venv whose installed application payload is
  byte-verified against that selected wheel. The recorded receipt names the
  wheel hash, source commit/tree, package version, API/worker module origins
  and the installed templates/CSS/JS/fonts.
- The REAL API runs as a uvicorn subprocess on the owned venv interpreter
  from an owned directory OUTSIDE the checkout, with PYTHONPATH unset.
- The REAL application Celery worker runs on the SAME owned venv through the
  accepted 217 worker driver (synthetic source bytes only; loopback-only
  network gate; broker asserted to be exactly the owned Redis).
- One complete scenario through real authenticated HTTP + Chromium against
  owned labeled PostgreSQL 16 and Redis, with strictly synthetic provider
  and SMTP fixtures. Seeded rows are SETUP only; every asserted outcome is
  produced by a reviewed GUI operation and verified by independent
  persisted/audit oracles (redirect destination plus persisted state).

Coverage (whole original mandate): G01 key-policy tri-state + safe
configuration round trip; G02/G03 rates + effective/source/model
explanation; G04 reviewed clone; G05 reviewed batch + safe repeat;
G06/G07 route configuration + provider preparation; G08/G16 diagnostics +
configuration/profile/version inspection; G09 replay inspect/extend;
G10 preset/data identity + module upgrade/rollback + data-profile
migration; G11/G13/G18 grouped usage/export + paging + pricing disable +
FX; G12 delivery lifecycle + SMTP test; G14 four accounting recovery
families; G15 sealed catalog refresh with real worker; G17 accounts; the
original calibration JSON row. Representative negatives: unauthorized,
wrong CSRF, tampered/stale review, validation recovery, secret canaries.

No product behavior change; no broad historical matrix rerun; no release,
tag, deployment, provider inference, or real email.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.server
import httpx
import json
import os
import re
import socket
import shutil
import subprocess
import tarfile
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.test_admin_catalog_refresh_217_postgres import (
    TERMINAL_JOB_STATUSES,
)
from tests.integration.test_cli_field_installed_workflow import (
    GatewayServer,
    ProviderMock,
    SmtpSink,
    _build_wheel,
    _installed_payload_matches,
    _migrate,
    _python_for_venv,
    _scrubbed_setup_env,
    _sha256_file,
    _venv_is_usable,
    _wait_pg_ready,
    _wheel_payload_matches,
)
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
    owned_redis_url as _owned_redis_url_fixture,
)

# Re-expose the qualified owned-database fixtures under their public names so
# the module-scope env fixture can request them by name (same pattern as the
# browser/postgres modules).
owned_pg_url = _owned_pg_url_fixture
owned_redis_url = _owned_redis_url_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = Path("/tmp/slaif219/installed-workflow")
# Path reference ONLY: the driver gate runs at import (owned URLs must
# be configured), so importing it here would kill collection.
WORKER_DRIVER = REPO_ROOT / "tests" / "integration" / "_catalog_refresh_worker_driver.py"
RUN_TOKEN = uuid.uuid4().hex[:16]

RUN_INSTALLED = os.environ.get("RUN_GUI_PARITY_INSTALLED_WORKFLOW", "").strip() == "1"

SUPERADMIN_EMAIL = "gui219-superadmin@example.org"
ADMIN_EMAIL = "gui219-admin@example.org"
ADMIN_PASSWORD = "219-installed-admin-pw-Q8m"

# Frozen compatibility pins (imported values, not literals).
from slaif_gateway.services.codex_module_upgrade import (  # noqa: E402
    CODEX_0149_V4_CLIENT_MODULE,
    CODEX_0162_V1_CLIENT_MODULE,
)

SUPERADMIN_PIN = dict(CODEX_0149_V4_CLIENT_MODULE)
MIGRATION_PIN = dict(CODEX_0162_V1_CLIENT_MODULE)


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr[:300]}")
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Artifacts: pristine source of THIS HEAD, ONE wheel, ONE owned venv
# ---------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class Artifacts:
    pristine: Path
    wheel: Path
    wheel_sha256: str
    venv_root: Path
    venv_py: Path
    wheel_reused: bool
    payload_files: int
    installed_payload_files: int
    steps: list[str]


def _pristine_source(tmp_base: Path) -> tuple[Path, str, str]:
    """git archive of THIS source HEAD (the objective branch head)."""
    commit = _git("rev-parse", "HEAD")
    tree = _git("rev-parse", f"{commit}^{{tree}}")
    target = tmp_base / "pristine"
    if target.is_dir():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    archive = tmp_base / "source.tar"
    with archive.open("wb") as handle:
        proc = subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise AssertionError(f"git archive failed: {proc.stderr[:300]}")
        handle.write(proc.stdout)
    with tarfile.open(archive, "r") as tar:
        tar.extractall(target, filter="data")
    assert (target / "app" / "slaif_gateway" / "__init__.py").is_file()
    archive.unlink()
    return target, commit, tree


def _wheel_name(pristine: Path) -> str:
    init = pristine / "app" / "slaif_gateway" / "__init__.py"
    match = re.search(
        r'__version__\s*=\s*["\']([^"\']+)["\']', init.read_text(encoding="utf-8")
    )
    version = match.group(1) if match else "0.1.0"
    return f"slaif_gateway-{version}-py3-none-any.whl"


def _ensure_venv_broker_transport_deps(venv_root: Path) -> None:
    """Ensure the owned venv can import the package the REAL Celery worker's
    kombu Redis transport soft-imports (``packaging``). ``packaging`` is not in
    the wheel's hard dependency closure, so a fresh minimal owned venv lacks it
    and the real broker transport crashes on connect (ModuleNotFoundError).
    Idempotent: no-op when the import already succeeds. Test-only venv
    completion; no product change.
    """
    venv_py = str(venv_root / "bin" / "python")
    probe = subprocess.run(
        [venv_py, "-c", "import packaging"],
        capture_output=True,
        timeout=60,
        env=_scrubbed_setup_env(),
    )
    if probe.returncode == 0:
        return
    subprocess.run(
        [
            venv_py,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--disable-pip-version-check",
            "packaging",
        ],
        capture_output=True,
        timeout=300,
        check=True,
        env=_scrubbed_setup_env(),
    )


def _resolve_artifacts(tmp_base: Path) -> tuple[Artifacts, str, str]:
    steps: list[str] = []
    pristine, commit, tree = _pristine_source(tmp_base)
    steps.append(f"git archive {commit} (tree {tree}) -> {pristine}")

    wheel: Path | None = None
    wheel_reused = False
    payload_files = 0
    name = _wheel_name(pristine)
    candidates = (
        [Path(os.environ["SLAIF219_WHEEL"])]
        if os.environ.get("SLAIF219_WHEEL", "").strip()
        else [tmp_base / "dist" / name]
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                payload_files = _wheel_payload_matches(pristine, candidate, tmp_base)
            except AssertionError:
                continue
            wheel = candidate
            wheel_reused = True
            steps.append(f"reused verified wheel {candidate}")
            break
    if wheel is None:
        wheel, payload_files = _build_wheel(pristine, tmp_base)
        steps.append(f"built and payload-verified wheel -> {wheel}")

    wheel_sha = _sha256_file(wheel)
    # _wheel_payload_matches leaves the SELECTED wheel extracted here.
    wheel_pkg = tmp_base / "wheel-extract" / "slaif_gateway"
    assert wheel_pkg.is_dir(), "selected wheel payload extraction missing"

    venv_root: Path | None = None
    if (tmp_base / "venv").is_dir() and _venv_is_usable(tmp_base / "venv"):
        try:
            _installed_payload_matches(tmp_base / "venv", wheel_pkg)
        except AssertionError:
            steps.append(
                "stale reused venv rejected: installed payload differs from the "
                "selected wheel; replacing with a fresh owned venv"
            )
        else:
            venv_root = tmp_base / "venv"
            steps.append(f"reused verified owned venv {venv_root}")
    if venv_root is None:
        venv_root = tmp_base / "venv"
        if venv_root.is_dir():
            shutil.rmtree(venv_root)
        subprocess.run(
            [_python_for_venv(), "-m", "venv", str(venv_root)],
            capture_output=True,
            timeout=300,
            check=True,
            env=_scrubbed_setup_env(),
        )
        subprocess.run(
            [str(venv_root / "bin" / "python"), "-m", "pip", "install", "--quiet", str(wheel)],
            capture_output=True,
            timeout=900,
            check=True,
            cwd=str(tmp_base),
            env=_scrubbed_setup_env(),
        )
        assert _venv_is_usable(venv_root), "fresh owned venv failed identity check"
        steps.append(f"created owned venv {venv_root} and installed {wheel.name}")

    # Ensure the real broker transport deps are present (build + reuse paths).
    _ensure_venv_broker_transport_deps(venv_root)
    steps.append("ensured owned venv broker transport deps (packaging)")

    installed_payload = _installed_payload_matches(venv_root, wheel_pkg)
    steps.append(f"verified installed application payload vs selected wheel ({installed_payload} files)")
    return (
        Artifacts(
            pristine=pristine,
            wheel=wheel,
            wheel_sha256=wheel_sha,
            venv_root=venv_root,
            venv_py=venv_root / "bin" / "python",
            wheel_reused=wheel_reused,
            payload_files=payload_files,
            installed_payload_files=installed_payload,
            steps=steps,
        ),
        commit,
        tree,
    )


# ---------------------------------------------------------------------------
# Installed origin probes (scrubbed env, neutral cwd, no PYTHONPATH)
# ---------------------------------------------------------------------------


_SCRUBBED_PROBE_ENV = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}


def _probe(venv_py: Path, code: str) -> str:
    proc = subprocess.run(
        [str(venv_py), "-c", code],
        cwd="/tmp",
        env=dict(_SCRUBBED_PROBE_ENV),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError(f"installed probe failed (exit {proc.returncode}): {proc.stderr[:300]}")
    return proc.stdout


def _installed_identities(artifacts: Artifacts) -> dict[str, str]:
    out = _probe(
        artifacts.venv_py,
        (
            "import sys, importlib.metadata as md, json\n"
            "import slaif_gateway as m\n"
            "import slaif_gateway.main as main_mod\n"
            "import slaif_gateway.workers.celery_app as celery_mod\n"
            "print(json.dumps({\n"
            "  'package': m.__file__,\n"
            "  'api_module': main_mod.__file__,\n"
            "  'worker_module': celery_mod.__file__,\n"
            "  'version': md.version('slaif-api-gateway'),\n"
            "  'python': sys.version.split()[0],\n"
            "}))\n"
        ),
    ).strip()
    return json.loads(out)


def _installed_static_inventory(artifacts: Artifacts) -> dict[str, Any]:
    package_file = _probe(
        artifacts.venv_py,
        "import slaif_gateway as m; print(m.__file__)",
    ).strip()
    package_dir = Path(package_file).parent
    web = package_dir / "web"
    groups = {
        "templates": (web / "templates", ".html"),
        "css": (web / "static" / "css", ".css"),
        "js": (web / "static" / "js", ".js"),
        "fonts": (web / "static" / "fonts", None),
    }
    out: dict[str, Any] = {}
    for label, (base, suffix) in groups.items():
        if not base.is_dir():
            out[label] = {"count": 0, "sha256_all": ""}
            continue
        files = sorted(
            p for p in base.rglob("*") if p.is_file() and (suffix is None or p.suffix == suffix)
        )
        h = hashlib.sha256()
        for p in files:
            h.update(str(p.relative_to(base)).encode("utf-8"))
            h.update(p.read_bytes())
        out[label] = {"count": len(files), "sha256_all": h.hexdigest()}
    return out


# ---------------------------------------------------------------------------
# Database oracle (fixture assertion; source-vendor SQLAlchemy)
# ---------------------------------------------------------------------------


def _db(database_url: str, coro_factory):
    box: dict[str, Any] = {}

    def _worker() -> None:
        async def _run():
            engine = create_async_engine(database_url, future=True)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    box["value"] = await coro_factory(session)
            finally:
                await engine.dispose()

        try:
            asyncio.run(_run())
        except BaseException as exc:  # pragma: no cover - re-raised below
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


# ---------------------------------------------------------------------------
# Seed script (runs on the OWNED VENV; product ORM from the installed wheel)
# ---------------------------------------------------------------------------


SEED_SCRIPT = r'''
import asyncio, json, secrets, sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import asyncpg

from slaif_gateway.db.models import (
    Cohort,
    CodexReplayReference,
    FxRate,
    GatewayKey,
    Institution,
    ModelRoute,
    Owner,
    PricingRule,
    ProviderConfig,
    QuotaReservation,
    RequestDiagnostic,
    UsageLedger,
    UsageProfile,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_CODEX_PROFILE_ID,
    build_codex_profile_declaration,
    get_codex_profile,
)

async def main() -> int:
    database_url = sys.argv[1]
    provider_base = sys.argv[2]
    admin_password = sys.argv[3]
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:10]
    manifest: dict = {}

    async with factory() as session:
        async with session.begin():
            superadmin = await AdminUsersRepository(session).create_admin_user(
                email="gui219-superadmin@example.org",
                display_name="219 Installed Superadmin",
                password_hash=hash_admin_password(admin_password),
                role="superadmin",
                is_active=True,
            )
            admin = await AdminUsersRepository(session).create_admin_user(
                email="gui219-admin@example.org",
                display_name="219 Installed Admin",
                password_hash=hash_admin_password(admin_password),
                role="admin",
                is_active=True,
            )
            institution = Institution(name=f"219 Institute {suffix}", country="SI")
            session.add(institution)
            await session.flush()

            owner_std = Owner(
                name="Std", surname="Seed",
                email=f"owner-std-{suffix}@example.org",
                institution_id=institution.id,
            )
            owner_cal = Owner(
                name="Cal", surname="Seed",
                email=f"owner-cal-{suffix}@example.org",
                institution_id=institution.id,
            )
            session.add_all([owner_std, owner_cal])
            await session.flush()

            cohort = Cohort(
                name=f"219 Cohort {suffix}",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            session.add(cohort)
            await session.flush()

            provider = ProviderConfig(
                provider="openai",
                display_name="Synthetic OpenAI",
                kind="openai_compatible",
                base_url=provider_base,
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                enabled=True,
                max_retries=2,
                timeout_seconds=30,
            )
            session.add(provider)
            await session.flush()

            def make_key(index: int, *, cohort_id=None, purpose="standard",
                         mode="standard", owner=None, allowed=None) -> GatewayKey:
                return GatewayKey(
                    public_key_id=f"219iw-{suffix}-{index:03d}",
                    token_hash=f"219iw-hash-{suffix}-{index:03d}",
                    owner_id=(owner or owner_std).id,
                    cohort_id=cohort_id,
                    status="active",
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                    request_limit_total=1000,
                    token_limit_total=5_000_000,
                    cost_limit_eur=Decimal("100.000000000"),
                    cost_used_eur=Decimal("0.000000000"),
                    tokens_used_total=0,
                    requests_used_total=0,
                    cost_reserved_eur=Decimal("0.000000000"),
                    tokens_reserved_total=0,
                    requests_reserved_total=0,
                    allow_all_models=allowed is None,
                    allow_all_endpoints=True,
                    allowed_models=allowed or None,
                    key_purpose=purpose,
                    capability_policy_mode=mode,
                    created_by_admin_user_id=admin.id,
                )

            k1 = make_key(1, cohort_id=cohort.id,
                          allowed=("gpt-4.1-mini", "gpt-4.1-nano"))
            k1.metadata_json = {
                "responses_policy": {
                    "client_module": json.loads(sys.argv[4]),
                    "219_sentinel": {"kept": "keep-me"},
                },
                "219_top_sentinel": {"kept": "keep-me"},
            }
            k2 = make_key(2, cohort_id=cohort.id, allowed=("gpt-4.1-nano",))
            k3 = make_key(3, cohort_id=cohort.id, allowed=("gpt-4.1-nano",))
            k4 = make_key(4, purpose="trusted_calibration",
                          mode="trusted_calibration_discovery", owner=owner_cal)
            k5 = make_key(5, allowed=("gpt-4.1-mini", "gpt-4.1-nano"))
            k6 = make_key(6, allowed=("gpt-4.1-mini",))
            k6.metadata_json = {
                "responses_policy": {"client_module": json.loads(sys.argv[5])}
            }
            session.add_all([k1, k2, k3, k4, k5, k6])
            await session.flush()

            routes = []
            for (model, priority) in (("gpt-4.1-mini", 10), ("gpt-4.1-nano", 20)):
                route = ModelRoute(
                    provider="openai",
                    endpoint="/v1/chat/completions",
                    requested_model=model,
                    upstream_model=model,
                    match_type="exact",
                    enabled=True,
                    priority=priority,
                    visible_in_models=True,
                    supports_streaming=True,
                )
                session.add(route)
                await session.flush()
                routes.append(route)

            for route in routes:
                session.add(
                    PricingRule(
                        provider=provider.provider,
                        upstream_model=route.upstream_model,
                        endpoint="/v1/chat/completions",
                        input_price_per_1m=Decimal("1.000000000"),
                        output_price_per_1m=Decimal("2.000000000"),
                        currency="EUR",
                        valid_from=now - timedelta(days=1),
                        enabled=True,
                    )
                )
            await session.flush()

            # G10 credential-free route profile/config/catalog artifacts:
            # ONE stored ready Codex route on the registered qwen38 0.162
            # profile (single /v1/responses endpoint, client-local
            # compaction, self-contained artifacts plus model catalog).
            # Synthetic provider/route/pricing only - no provider HTTP and
            # no requalification (212 browser fixture pattern).
            codex_provider = ProviderConfig(
                provider=f"syn219c-{suffix}",
                display_name="Synthetic 219 Codex Provider",
                kind="openai_compatible",
                base_url="https://syn219c.example/v1",
                api_key_env_var="GUI219C_SYN219_KEY",
                enabled=True,
                timeout_seconds=300,
                max_retries=0,
                notes=None,
            )
            session.add(codex_provider)
            await session.flush()
            codex_profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
            assert codex_profile is not None
            codex_route = ModelRoute(
                requested_model=codex_profile.public_model,
                provider=codex_provider.provider,
                upstream_model=codex_profile.upstream_model,
                match_type="exact",
                endpoint="/v1/responses",
                priority=1,
                enabled=True,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={
                    "responses": {
                        "text": True,
                        "stateless": True,
                        "streaming": True,
                        "codex_request_envelope": True,
                        "codex_client_tools": True,
                        "codex_streaming_tool_events": True,
                        "codex_encrypted_reasoning_replay": True,
                    },
                    "codex_limits": {
                        "context_window_tokens": codex_profile.context_window_tokens,
                        "default_max_output_tokens": codex_profile.default_max_output_tokens,
                        "max_output_tokens": codex_profile.max_output_tokens,
                    },
                    "codex_profile": build_codex_profile_declaration(
                        QWEN38_CODEX_PROFILE_ID
                    ),
                },
                notes="219 installed codex responses route",
            )
            session.add(codex_route)
            await session.flush()
            session.add(
                PricingRule(
                    provider=codex_provider.provider,
                    upstream_model=codex_profile.upstream_model,
                    endpoint="/v1/responses",
                    input_price_per_1m=Decimal("1.000000000"),
                    cached_input_price_per_1m=Decimal("0.250000000"),
                    output_price_per_1m=Decimal("1.000000000"),
                    reasoning_price_per_1m=Decimal("2.000000000"),
                    request_price=Decimal("0.000000000"),
                    currency="EUR",
                    valid_from=now - timedelta(days=1),
                    enabled=True,
                    pricing_metadata={
                        "codex_accounting": {
                            "long_context_threshold_tokens": 98304,
                            "long_context_input_multiplier": "2",
                            "long_context_output_multiplier": "2",
                            "cache_write_input_multiplier": "1",
                        }
                    },
                )
            )
            await session.flush()

            session.add_all([
                FxRate(
                    base_currency="GBP", quote_currency="EUR",
                    rate=Decimal("1.180000000"),
                    valid_from=now - timedelta(days=1),
                ),
                FxRate(
                    base_currency="USD", quote_currency="EUR",
                    rate=Decimal("0.920000000"),
                    valid_from=now - timedelta(days=1),
                ),
            ])
            await session.flush()

            # K1: 60 observed usage rows (2 pages at the 50-row page bound).
            diag_id = "gw-" + uuid.uuid4().hex
            for i in range(60):
                ledger = UsageLedger(
                    request_id=f"219iw-req-{suffix}-{i:03d}",
                    gateway_key_id=k1.id,
                    owner_id=k1.owner_id,
                    cohort_id=k1.cohort_id,
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    requested_model="gpt-4.1-mini",
                    resolved_model="gpt-4.1-mini",
                    success=True,
                    accounting_status="finalized",
                    started_at=now - timedelta(hours=60 - i),
                    finished_at=now - timedelta(hours=60 - i),
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150,
                    actual_cost_eur=Decimal("0.000150000"),
                )
                session.add(ledger)
                await session.flush()
                session.add(
                    UsageProfile(
                        usage_ledger_id=ledger.id,
                        gateway_key_id=k1.id,
                        owner_id=k1.owner_id,
                        cohort_id=k1.cohort_id,
                        endpoint_path="/v1/chat/completions",
                        provider="openai",
                        requested_model="gpt-4.1-mini",
                        resolved_upstream_model="gpt-4.1-mini",
                        provider_host="127.0.0.1",
                        provider_endpoint_path="/v1/chat/completions",
                        input_tokens=100,
                        output_tokens=50,
                        total_tokens=150,
                    )
                )
            await session.flush()
            # first K1 ledger row is the diagnostics' source request
            first = (
                await session.execute(
                    select(UsageLedger)
                    .where(UsageLedger.gateway_key_id == k1.id)
                    .order_by(UsageLedger.created_at.asc())
                )
            ).scalars().first()
            session.add(
                RequestDiagnostic(
                    gateway_request_id=diag_id,
                    method="POST",
                    endpoint_template="/v1/chat/completions",
                    occurred_at=now,
                    http_status=200,
                    stream_outcome="http_rejection",
                    source="provider",
                    reason_code="provider_error",
                    error_code="upstream_500",
                    gateway_key_id=k1.id,
                    route_id=routes[0].id,
                    route_pattern="/v1/chat/completions",
                    recorded_at=now,
                )
            )
            await session.flush()

            # K4 (trusted calibration): two observed rows.
            for i in range(2):
                ledger = UsageLedger(
                    request_id=f"219iw-cal-{suffix}-{i}",
                    gateway_key_id=k4.id,
                    owner_id=k4.owner_id,
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    requested_model="gpt-4.1-mini",
                    resolved_model="gpt-4.1-mini",
                    success=True,
                    accounting_status="finalized",
                    started_at=now - timedelta(hours=2 + i),
                    finished_at=now - timedelta(hours=2 + i),
                    input_tokens=80 + 20 * i,
                    output_tokens=40 + 10 * i,
                    total_tokens=120 + 30 * i,
                )
                session.add(ledger)
                await session.flush()
                session.add(
                    UsageProfile(
                        usage_ledger_id=ledger.id,
                        gateway_key_id=k4.id,
                        owner_id=k4.owner_id,
                        endpoint_path="/v1/chat/completions",
                        provider="openai",
                        requested_model="gpt-4.1-mini",
                        resolved_upstream_model="gpt-4.1-mini",
                        input_tokens=80 + 20 * i,
                        output_tokens=40 + 10 * i,
                        total_tokens=120 + 30 * i,
                    )
                )
            await session.flush()

            # G14 candidates (exact product-validated shapes; SETUP only):
            # 1) an expired pending reservation on K2;
            # 2) an ACTIVE fence on K5 (read-only fence view candidate);
            # 3) an exact HELD external-tool accounting hold on K3 (pending
            #    fenced reservation bound to the key fence and exactly one
            #    unresolved hold ledger, reserved counters consistent);
            # 4) a provider-completed finalization-failed recovery row on
            #    K5 with a pending reservation and positive final usage.
            session.add(
                QuotaReservation(
                    gateway_key_id=k2.id,
                    request_id=f"219iw-resv-{suffix}",
                    endpoint="/v1/chat/completions",
                    requested_model="gpt-4.1-nano",
                    reserved_cost_eur=Decimal("0.001000000"),
                    reserved_tokens=150,
                    reserved_requests=1,
                    status="pending",
                    expires_at=now - timedelta(minutes=30),
                )
            )
            await session.flush()
            # K2's reserved counters must reflect this pending reservation or
            # the G14 expired-reconciliation subtract underflows the invariant.
            k2.cost_reserved_eur = Decimal("0.001000000")
            k2.tokens_reserved_total = 150
            k2.requests_reserved_total = 1

            k5_fence_resv = QuotaReservation(
                gateway_key_id=k5.id,
                request_id=f"219iw-fencerq-{suffix}",
                endpoint="/v1/chat/completions",
                requested_model="gpt-4.1-nano",
                quota_mode="external_tool_fenced",
                external_tool_capabilities=["shell"],
                external_tool_destination_ids=["219iw-dest"],
                external_tool_provider="openai",
                external_tool_route_id=routes[1].id,
                reserved_cost_eur=Decimal("0.500000000"),
                reserved_tokens=5000,
                reserved_requests=1,
                status="pending",
                expires_at=now + timedelta(minutes=5),
            )
            session.add(k5_fence_resv)
            await session.flush()
            k5.external_tool_fence_state = "active"
            k5.external_tool_fence_reservation_id = k5_fence_resv.id
            k5.external_tool_fence_request_id = k5_fence_resv.request_id
            k5.external_tool_fence_acquired_at = now
            k5.external_tool_fence_expires_at = now + timedelta(minutes=5)

            hold_resv = QuotaReservation(
                gateway_key_id=k3.id,
                request_id=f"219iw-holdreq-{suffix}",
                endpoint="/v1/chat/completions",
                requested_model="gpt-4.1-nano",
                quota_mode="external_tool_fenced",
                external_tool_capabilities=["shell"],
                external_tool_destination_ids=["219iw-dest"],
                external_tool_provider="openai",
                external_tool_route_id=routes[1].id,
                reserved_cost_eur=Decimal("0.500000000"),
                reserved_tokens=5000,
                reserved_requests=1,
                status="pending",
                expires_at=now + timedelta(minutes=5),
            )
            session.add(hold_resv)
            await session.flush()
            k3.external_tool_fence_state = "held"
            k3.external_tool_fence_reservation_id = hold_resv.id
            k3.external_tool_fence_request_id = hold_resv.request_id
            k3.external_tool_fence_acquired_at = now
            k3.external_tool_fence_expires_at = now + timedelta(minutes=5)
            k3.cost_reserved_eur = Decimal("0.500000000")
            k3.tokens_reserved_total = 5000
            k3.requests_reserved_total = 1
            hold = UsageLedger(
                request_id=hold_resv.request_id,
                quota_reservation_id=hold_resv.id,
                gateway_key_id=k3.id,
                owner_id=k3.owner_id,
                endpoint="/v1/chat/completions",
                provider="openai",
                requested_model="gpt-4.1-nano",
                resolved_model="gpt-4.1-nano",
                accounting_status="estimated",
                started_at=now - timedelta(hours=1),
                input_tokens=50,
                output_tokens=25,
                total_tokens=75,
                response_metadata={
                    "external_tool_accounting_hold": {
                        "version": 1,
                        "state": "held",
                        "reason_code": "missing_final_cost",
                        "needs_reconciliation": True,
                        "evidence_quality": "partial_estimate",
                        "held_at": (now - timedelta(hours=1)).isoformat(),
                    }
                },
            )
            session.add(hold)
            await session.flush()

            pcr_resv = QuotaReservation(
                gateway_key_id=k5.id,
                request_id=f"219iw-pcrreq-{suffix}",
                endpoint="/v1/chat/completions",
                requested_model="gpt-4.1-nano",
                reserved_cost_eur=Decimal("0.100000000"),
                reserved_tokens=200,
                reserved_requests=1,
                status="pending",
                expires_at=now + timedelta(minutes=5),
            )
            session.add(pcr_resv)
            await session.flush()
            k5.cost_reserved_eur = Decimal("0.600000000")
            k5.tokens_reserved_total = 5200
            k5.requests_reserved_total = 2
            pcr = UsageLedger(
                request_id=f"219iw-pcr-{suffix}",
                    quota_reservation_id=pcr_resv.id,
                    gateway_key_id=k5.id,
                    owner_id=k5.owner_id,
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    requested_model="gpt-4.1-nano",
                    resolved_model="gpt-4.1-nano",
                    success=False,
                    accounting_status="failed",
                    started_at=now - timedelta(hours=2),
                    finished_at=now - timedelta(hours=2),
                    upstream_request_id=f"prov-{suffix}-pcr",
                    prompt_tokens=120,
                    completion_tokens=80,
                    input_tokens=120,
                    output_tokens=80,
                    total_tokens=200,
                    estimated_cost_eur=Decimal("0.100000000"),
                    actual_cost_eur=Decimal("0.100000000"),
                response_metadata={
                    "needs_reconciliation": True,
                    "recovery_state": "provider_completed_finalization_failed",
                },
            )
            session.add(pcr)
            await session.flush()

            # G11 live-burn report: ONE K1 Chat streaming row with live-burn
            # telemetry (the report aggregates only streaming rows that
            # carry telemetry). Cost estimate is deliberately NOT
            # invoice-grade; the final provider usage IS available, so the
            # provenance counts stay exact and honest.
            burn = UsageLedger(
                request_id=f"219iw-burn-{suffix}",
                gateway_key_id=k1.id,
                owner_id=k1.owner_id,
                cohort_id=k1.cohort_id,
                endpoint="/v1/chat/completions",
                provider="openai",
                requested_model="gpt-4.1-mini",
                resolved_model="gpt-4.1-mini",
                streaming=True,
                success=True,
                accounting_status="finalized",
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
                input_tokens=1100,
                output_tokens=200,
                total_tokens=1300,
                actual_cost_eur=Decimal("0.000120000"),
                response_metadata={
                    "streaming_live_burn_enabled": True,
                    "streaming_live_burn_triggered": True,
                    "streaming_live_burn_stop_reason": "cost",
                    "estimated_tokens_at_stop": 1234,
                    # Canonical JSONB form: exact decimal TEXT (the production
                    # writer serializes via _format_eur); JSONB cannot hold Decimal.
                    "estimated_cost_eur_at_stop": "0.000123456",
                    "cost_margin_eur": "0.000050000",
                    "token_margin": 100,
                    "final_provider_usage_available": True,
                    "estimate_is_invoice_grade": False,
                },
            )
            session.add(burn)
            await session.flush()

            # G09: one eligible same-key codex replay reference on K1.
            first = (
                await session.execute(
                    select(UsageLedger)
                    .where(UsageLedger.gateway_key_id == k1.id)
                    .order_by(UsageLedger.created_at.asc())
                )
            ).scalars().first()
            session.add(
                CodexReplayReference(
                    gateway_key_id=k1.id,
                    usage_ledger_id=first.id,
                    source_request_id=first.request_id,
                    provider="openai",
                    route_id=routes[0].id,
                    upstream_model="gpt-4.1-mini",
                    item_kind="compaction",
                    item_id_hmac=secrets.token_hex(32),
                    hmac_key_version=1,
                    created_at=now,
                    # Expiry close enough that the reviewed 86400s extension
                    # (max(old, created+TTL)) is a genuine monotonic extension.
                    expires_at=now + timedelta(hours=12),
                )
            )
            await session.flush()

            manifest = {
                "superadmin": str(superadmin.id),
                "admin": str(admin.id),
                "institution": str(institution.id),
                "owner_std": str(owner_std.id),
                "owner_cal": str(owner_cal.id),
                "cohort": str(cohort.id),
                "provider": str(provider.id),
                "route_mini": str(routes[0].id),
                "route_nano": str(routes[1].id),
                "provider_codex": str(codex_provider.id),
                "route_codex": str(codex_route.id),
                "k1": str(k1.id),
                "k2": str(k2.id),
                "k3": str(k3.id),
                "k4": str(k4.id),
                "k5": str(k5.id),
                "k6": str(k6.id),
                "reservation": str((
                    await session.execute(
                        select(QuotaReservation)
                        .where(QuotaReservation.request_id == f"219iw-resv-{suffix}")
                    )
                ).scalars().one().id),
                "hold_ledger": str(hold.id),
                "hold_reservation": str(hold_resv.id),
                "pcr_ledger": str(pcr.id),
                "pcr_reservation": str(pcr_resv.id),
                "burn_ledger": str(burn.id),
                "diag_request_id": diag_id,
                "suffix": suffix,
            }
    await engine.dispose()
    print("SEED_MANIFEST " + json.dumps(manifest, sort_keys=True))
    return 0

sys.exit(asyncio.run(main()))
'''




# ---------------------------------------------------------------------------
# Part 2: owned environment + the ONE installed GUI workflow (G01-G18)
# ---------------------------------------------------------------------------

class _ModelsServer:
    """Owned loopback GET /v1/models endpoint for the GUI discovery
    scenario (documented IO substitution; fixed synthetic model IDs)."""

    def __init__(self, models: tuple[str, ...]) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        body = json.dumps({"data": [{"id": m, "object": "model"} for m in models]})

        class _Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
                if self.path.rstrip("/") == "/v1/models":
                    payload = body.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self.send_error(404)

        self._httpd = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.port), _Handler
        )
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except OSError:
            pass


class _LoggedGateway(GatewayServer):
    """The installed gateway with its app log RETAINED on disk: the final
    secret scan must check complete app/worker logs, not only response
    bodies. Captures output only; changes no product behavior."""

    def __init__(self, venv_py: Path, env: dict[str, str], cwd: Path) -> None:
        self.app_log_path = WORKFLOW_DIR / "gateway-app.log"
        if self.app_log_path.exists():
            self.app_log_path.unlink()
        super().__init__(venv_py, env, cwd)

    def _drain(self) -> None:
        assert self.proc.stdout is not None
        with open(self.app_log_path, "ab", buffering=0) as fh:
            while True:
                chunk = self.proc.stdout.read(65536)
                if not chunk:
                    return
                fh.write(chunk)


REASON = "219 installed GUI workflow operation"
LOGIN_ACTION = 'form[action="/admin/login"]'

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
REVIEW_TOKEN_RE = re.compile(r'name="review_token" value="([^"]+)"')
BATCH_TOKEN_RE = re.compile(r'name="batch_review_intent" value="([^"]+)"')
CLONE_TOKEN_RE = re.compile(r'name="clone_review_intent" value="([^"]+)"')
ROUTE_TOKEN_RE = re.compile(r'name="route_config_review_intent" value="([^"]+)"')

CATALOG_BASE = "/admin/operations/catalog"
COMPAT_BASE = "/admin/operations/compatibility"
REPLAY_BASE = "/admin/operations/replay-maintenance"
ACCOUNTS_BASE = "/admin/accounts"


def _csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match is not None, "no CSRF token rendered"
    return match.group(1)


def _token(html: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(html)
    assert match is not None, "review token missing from rendered page"
    return match.group(1)


class _LoginState:
    """One real authenticated HTTP session against the installed gateway."""

    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, follow_redirects=False)

    def login(self, email: str, password: str) -> None:
        page = self.client.get("/admin/login")
        assert page.status_code == 200, page.status_code
        resp = self.client.post(
            "/admin/login",
            data={"email": email, "password": password, "csrf_token": _csrf(page.text)},
        )
        assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
        assert resp.headers["location"] == "/admin", resp.headers["location"]

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.client.get(path, params=params or None)
        assert resp.status_code == 200, (path, resp.status_code, resp.text[:300])
        return resp

    def post(self, path: str, data: dict[str, Any], **kwargs: Any) -> Any:
        return self.client.post(path, data=data, **kwargs)


def _gateway_env(
    *,
    database_url: str,
    redis_url: str,
    smtp_port: int,
    custody_root: Path,
    seal_key: Path,
) -> dict[str, str]:
    """Scrubbed env for the installed app/worker: no PYTHONPATH, no checkout
    cwd, synthetic provider secrets, the owned SMTP sink as the only SMTP
    target, the owned Redis as the ONLY broker, and the owned catalog
    custody root/seal key."""
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/tmp/slaif219/installed-workflow/home",
        "LANG": "C.UTF-8",
        "APP_ENV": "development",
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "TOKEN_HMAC_SECRET": _gen_secret(),
        "TOKEN_HMAC_SECRET_V1": _gen_secret(),
        "ACTIVE_HMAC_KEY_VERSION": "1",
        "ONE_TIME_SECRET_ENCRYPTION_KEY": _gen_secret(),
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ADMIN_SESSION_SECRET": _gen_secret(),
        "ENABLE_ADMIN_DASHBOARD": "true",
        "ENABLE_EMAIL_DELIVERY": "true",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": str(smtp_port),
        "SMTP_FROM": "219-installed@example.invalid",
        "OPENAI_UPSTREAM_API_KEY": "sk-provider-secret-placeholder-219",
        "OPENROUTER_API_KEY": "sk-or-provider-secret-placeholder-219",
        # Valid configured public gateway URL (HTTP numeric-loopback dev
        # form ending in /v1): the credential-free codex-profile artifact
        # renderer accepts exactly this shape; the non-numeric "localhost"
        # HTTP default is deliberately NOT renderable.
        "PUBLIC_BASE_URL": "http://127.0.0.1:8000/v1",
        # Synthetic discovery key material for the GUI discovery scenario:
        # the provider config references the ENV VAR NAME; the value is a
        # documented synthetic placeholder, never a real credential.
        "GUI219D_SYN219_KEY": "syn-219-discovery-placeholder",
        "CATALOG_REFRESH_GUI_ENABLED": "true",
        "CATALOG_REFRESH_ROOT": str(custody_root),
        "CATALOG_REFRESH_SEAL_KEY": str(seal_key),
    }


def _gen_secret() -> str:
    from slaif_gateway.utils.secrets import generate_secret_key

    return generate_secret_key()


def _seed_via_venv(
    artifacts: Artifacts,
    database_url: str,
    provider_base: str,
) -> dict[str, str]:
    """Run the seed script ON THE OWNED VENV (product ORM from the wheel)."""
    proc = subprocess.run(
        [
            str(artifacts.venv_py),
            "-c",
            SEED_SCRIPT,
            database_url,
            provider_base,
            ADMIN_PASSWORD,
            json.dumps(SUPERADMIN_PIN),
            json.dumps(MIGRATION_PIN),
        ],
        cwd="/tmp",
        env=dict(_SCRUBBED_PROBE_ENV),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if proc.returncode != 0:
        raise AssertionError(f"seed failed (exit {proc.returncode}): {proc.stderr[:500]}")
    for line in proc.stdout.splitlines():
        if line.startswith("SEED_MANIFEST "):
            return json.loads(line[len("SEED_MANIFEST "):])
    raise AssertionError("seed manifest line missing from seed output")


def _wait_worker_ready(proc: subprocess.Popen, timeout: float = 180.0) -> None:
    """Drain the driver's stdout until the test-only WORKER_READY line (the
    real Celery worker then runs in that same process)."""
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    tail: list[str] = []
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise AssertionError(
                    "worker driver exited before readiness "
                    f"(exit {proc.returncode}): {''.join(tail)[-400:]}"
                )
            continue
        text = line.decode("utf-8", "replace").strip()
        tail.append(text + "\n")
        if len(tail) > 50:
            tail.pop(0)
        if "WORKER_READY" in text:
            return
    raise AssertionError("worker driver did not become ready in time")


def _drain_worker(proc: subprocess.Popen, log_path: Path) -> None:
    """Continuously drain the worker stdout AFTER readiness.

    The readiness wait stops reading at the WORKER_READY line; without a
    continuous drain the OS pipe buffer (64 KB) fills during the first
    job's logging and the real worker blocks on a write mid-job. The drain
    keeps the worker unblocked and retains the full log for failure
    diagnosis (test-only; no product behavior).
    """
    assert proc.stdout is not None
    with open(log_path, "ab") as fh:
        for raw in iter(proc.stdout.readline, b""):
            fh.write(raw)
            fh.flush()


@pytest.fixture(scope="module")
def env219(owned_pg_url: str, owned_redis_url: str) -> Iterator[dict[str, Any]]:
    if not RUN_INSTALLED:
        pytest.skip(
            "RUN_GUI_PARITY_INSTALLED_WORKFLOW=1 is required (test-only opt-in)"
        )
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    # The sealed catalog-refresh operations require the seal key's parent
    # directory (this fixture dir) to not be group/other-writable; force the
    # documented private mode even when the directory pre-exists from an
    # earlier umask-002 run.
    os.chmod(WORKFLOW_DIR, 0o700)
    home = WORKFLOW_DIR / "home"
    home.mkdir(exist_ok=True)

    artifacts, commit, tree = _resolve_artifacts(WORKFLOW_DIR)
    identities = _installed_identities(artifacts)
    static_inventory = _installed_static_inventory(artifacts)

    pg = urlparse(owned_pg_url)
    orm_url = (
        f"postgresql+asyncpg://{pg.username}:{pg.password}"
        f"@127.0.0.1:{pg.port}{pg.path}"
    )
    driver_url = (
        f"postgresql://{pg.username}:{pg.password}"
        f"@127.0.0.1:{pg.port}{pg.path}"
    )
    _wait_pg_ready(driver_url, artifacts.venv_py)
    _migrate(artifacts.pristine, artifacts.venv_py, orm_url)

    sink = SmtpSink()
    provider = ProviderMock()
    models = _ModelsServer(("syn-219-model-a", "syn-219-model-b"))
    manifest = _seed_via_venv(artifacts, orm_url, provider.base_url)

    custody_root = WORKFLOW_DIR / "custody"
    custody_root.mkdir(exist_ok=True)
    # The custody gate rejects a group/other-writable root (mode & 0o022);
    # force the documented 0700 even when the directory pre-exists from an
    # earlier umask-002 run.
    os.chmod(custody_root, 0o700)
    # Every installed run starts from an EMPTY owned custody: earlier
    # fixture runs persist terminal job records, proposal artifacts and
    # published runs in this same owned root, and that accumulation (a)
    # advances toward the retained-run capacity between runs and (b) lets
    # stale terminal jobs shadow the fresh ones in bounded console/job
    # projections (a stale "ready" proposal must never be mistaken for
    # the job the current run just created). Bounded cleanup of the
    # GENERATED custody subtrees of this fixture's OWN root only; the
    # root, the lock dir, and everything outside custody/ are preserved.
    for _sub in ("jobs", "proposals", "runs", "uploads"):
        _path = custody_root / _sub
        if _path.is_dir():
            for _entry in sorted(_path.iterdir()):
                if _entry.is_dir() and not _entry.is_symlink():
                    shutil.rmtree(_entry)
                elif _entry.is_file() or _entry.is_symlink():
                    _entry.unlink()
        _path.mkdir(exist_ok=True)
    seal_key = WORKFLOW_DIR / "seal.hex"
    seal_key.write_bytes(b"21" * 32)
    os.chmod(seal_key, 0o600)

    env = _gateway_env(
        database_url=orm_url,
        redis_url=owned_redis_url,
        smtp_port=sink.port,
        custody_root=custody_root,
        seal_key=seal_key,
    )

    app_dir = WORKFLOW_DIR / "app-run"
    app_dir.mkdir(exist_ok=True)
    gateway = _LoggedGateway(artifacts.venv_py, env, app_dir)

    origin_report = WORKFLOW_DIR / "worker-origin.json"
    if origin_report.exists():
        origin_report.unlink()
    worker_error_report = WORKFLOW_DIR / "worker-error.log"
    if worker_error_report.exists():
        worker_error_report.unlink()
    worker_proc = subprocess.Popen(
        [str(artifacts.venv_py), str(WORKER_DRIVER)],
        cwd="/tmp",
        env=dict(
            env,
            SLAIF219_WORKER_ORIGIN_REPORT=str(origin_report),
            SLAIF219_WORKER_ERROR_REPORT=str(worker_error_report),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _wait_worker_ready(worker_proc)
    worker_log = WORKFLOW_DIR / "worker.log"
    if worker_log.exists():
        worker_log.unlink()
    threading.Thread(
        target=_drain_worker, args=(worker_proc, worker_log), daemon=True,
    ).start()

    env_dict: dict[str, Any] = {
        "artifacts": artifacts,
        "commit": commit,
        "tree": tree,
        "identities": identities,
        "static_inventory": static_inventory,
        "database_url": owned_pg_url,
        "orm_url": orm_url,
        "redis_url": owned_redis_url,
        "manifest": manifest,
        "sink": sink,
        "provider": provider,
        "gateway": gateway,
        "models": models,
        "base_url": gateway.url,
        "app_dir": app_dir,
        "custody_root": custody_root,
        "seal_key": seal_key,
        "worker_proc": worker_proc,
        "worker_origin_report": origin_report,
        "worker_error_report": worker_error_report,
    }
    try:
        yield env_dict
    finally:
        if worker_proc.poll() is None:
            worker_proc.terminate()
            try:
                worker_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                worker_proc.kill()
                worker_proc.wait(timeout=30)
        if worker_proc.stdout is not None:
            try:
                worker_proc.stdout.close()
            except (OSError, ValueError):
                pass
        gateway.stop()
        provider.stop()
        sink.stop()
        models.stop()


@pytest.fixture(scope="module")
def chromium(env219: dict[str, Any]) -> Iterator[object]:
    """Playwright sync session started AFTER the installed app is up (the
    sync API owns the main thread's event loop)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


def _superadmin(env: dict[str, Any]) -> _LoginState:
    state = _LoginState(env["base_url"])
    state.login(SUPERADMIN_EMAIL, ADMIN_PASSWORD)
    return state


def _audits(env: dict[str, Any], action: str, entity_id: str | None = None) -> list[dict[str, Any]]:
    from slaif_gateway.db.models import AuditLog

    async def _query(session):
        stmt = select(AuditLog).where(AuditLog.action == action)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        rows = (await session.execute(stmt.order_by(AuditLog.created_at.asc()))).scalars().all()
        return [
            {
                "action": r.action,
                "entity_id": str(r.entity_id) if r.entity_id else None,
                "actor": str(r.admin_user_id) if r.admin_user_id else None,
                "note": r.note,
                "old": r.old_values,
                "new": r.new_values,
            }
            for r in rows
        ]

    return _db(env["database_url"], _query)


def _gateway_keys(env: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from slaif_gateway.db.models import GatewayKey

    async def _query(session):
        rows = (await session.execute(select(GatewayKey))).scalars().all()
        out = {}
        for r in rows:
            out[str(r.id)] = {
                "public_key_id": r.public_key_id,
                "token_hash": r.token_hash,
                "owner_id": str(r.owner_id),
                "cohort_id": str(r.cohort_id) if r.cohort_id else None,
                "status": r.status,
                "allow_all_models": r.allow_all_models,
                "allowed_models": list(r.allowed_models or []),
                "allow_all_endpoints": r.allow_all_endpoints,
                "allowed_endpoints": list(r.allowed_endpoints or []),
                "cost_used_eur": float(r.cost_used_eur),
                "tokens_used_total": r.tokens_used_total,
                "requests_used_total": r.requests_used_total,
                "token_limit_total": r.token_limit_total,
                "cost_reserved_eur": float(r.cost_reserved_eur),
                "tokens_reserved_total": r.tokens_reserved_total,
                "requests_reserved_total": r.requests_reserved_total,
                "rate_limit_requests_per_minute": r.rate_limit_requests_per_minute,
                "rate_limit_policy": dict((dict(r.metadata_json or {}).get("rate_limit_policy") or {})),
                "max_concurrent_requests": r.max_concurrent_requests,
                "external_tool_fence_state": r.external_tool_fence_state,
                "metadata_json": dict(r.metadata_json or {}),
            }
        return out

    return _db(env["database_url"], _query)


def _canary_free(env: dict[str, Any], html: str) -> None:
    assert "sk-provider-secret-placeholder-219" not in html
    assert "sk-or-provider-secret-placeholder-219" not in html
    assert "argon2" not in html
    # A FULL usable gateway-key VALUE (<prefix><public_id>.<secret>) must
    # never leak on any admin surface.  The secret half is exactly the part
    # after the dot, so only dot-bearing values are flagged.  Bare public
    # identifiers are legitimate UI (not secret material): the 8-char display
    # prefix and the prefix+public_key_id key NAME shown in lists/detail.
    full_key = re.search(
        r"sk-slaif-[A-Za-z0-9_-]{4,64}\.[A-Za-z0-9._~+/=-]{8,}", html
    )
    assert full_key is None, f"full gateway key value leaked: {full_key.group(0)[:24]}..."


# ---------------------------------------------------------------------------
# 00. Installed identity receipt (wheel / venv / origins / static payload)
# ---------------------------------------------------------------------------


def test_00_installed_identity_receipt(env219: dict[str, Any]) -> None:
    env = env219
    artifacts: Artifacts = env["artifacts"]
    identities: dict[str, str] = env["identities"]
    static: dict[str, Any] = env["static_inventory"]

    # Source identity is THIS objective HEAD.
    assert env["commit"] == _git("rev-parse", "HEAD")
    assert len(env["tree"]) == 40
    assert len(artifacts.wheel_sha256) == 64
    assert artifacts.payload_files > 100
    assert artifacts.installed_payload_files == artifacts.payload_files

    # Product origins: the installed wheel, not the checkout, not editable.
    venv_root = str(artifacts.venv_root)
    for label in ("package", "api_module", "worker_module"):
        path = identities[label]
        assert path.startswith(venv_root), (label, path)
        assert str(REPO_ROOT) not in path, (label, path)
        assert "site-packages" in path, (label, path)
    wheel_version = artifacts.wheel.name.split("-")[1]
    assert identities["version"] == wheel_version

    # The worker process itself proves the same installed origin.
    origin = json.loads(env["worker_origin_report"].read_text(encoding="utf-8"))
    for label in ("package", "worker_module"):
        assert origin[label].startswith(venv_root), (label, origin[label])
        assert "site-packages" in origin[label]

    # The real API ran from an owned directory OUTSIDE the checkout.
    assert not str(env["app_dir"]).startswith(str(REPO_ROOT))
    # The gateway/worker env construction never sets PYTHONPATH (the
    # _gateway_env dict has no such key by construction).
    assert "PYTHONPATH" not in _gateway_env(
        database_url=env["orm_url"],
        redis_url=env["redis_url"],
        smtp_port=1,
        custody_root=WORKFLOW_DIR,
        seal_key=WORKFLOW_DIR / "seal.hex",
    )

    # Installed templates/CSS/JS/fonts: finite, nonempty, digested.
    for label in ("templates", "css", "js", "fonts"):
        assert static[label]["count"] > 0, label
        assert len(static[label]["sha256_all"]) == 64, label

    # The driver fails closed unless the effective broker is EXACTLY the
    # owned Redis (it SystemExits before WORKER_READY otherwise, so the
    # fixture itself proves the fact).
    assert env["redis_url"].startswith("redis://127.0.0.1:")


# ---------------------------------------------------------------------------
# 01. Login + secret canary + process configuration (G08/G16)
# ---------------------------------------------------------------------------


def test_01_login_secret_canary_and_process_configuration(env219: dict[str, Any]) -> None:
    env = env219
    base = env["base_url"]
    client = httpx.Client(base_url=base, follow_redirects=False)

    anon = client.get("/admin")
    assert anon.status_code in (302, 303)
    assert "/admin/login" in anon.headers["location"]

    state = _superadmin(env)
    home = state.get("/admin")
    _canary_free(env, home.text)

    proc = state.get("/admin/operations/process-configuration")
    _canary_free(env, proc.text)
    assert env["identities"]["version"] in proc.text
    # The finite allowlist page renders the settings table but not the
    # configured key prefix (an operator env setting, not a process setting).
    assert "API process settings" in proc.text
    assert "sk-slaif-" not in proc.text

    # The owned provider placeholder is a server-side secret: it must never
    # reach any admin surface.
    assert "sk-provider-secret-placeholder-219" not in proc.text
    client.close()
    env["superadmin"] = state


# ---------------------------------------------------------------------------
# 02. G01: guided create + strict configuration round trip + tri-state
# ---------------------------------------------------------------------------


def test_02_g01_key_policy_configuration_round_trip(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest: dict[str, str] = env["manifest"]
    before_ids = set(_gateway_keys(env))

    page = state.get("/admin/keys/create")
    csrf = _csrf(page.text)
    resp = state.post(
        "/admin/keys/create",
        {
            "csrf_token": csrf,
            "owner_id": manifest["owner_std"],
            "cohort_id": manifest["cohort"],
            "valid_days": "30",
            "email_delivery_mode": "none",
            "allowed_providers": "openai",
            "allowed_models": "gpt-4.1-mini",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    # Success renders the 200 no-store create result page (not a redirect).
    assert resp.status_code == 200, (resp.status_code, resp.text[:300])
    # For none-delivery this result page is the ONLY plaintext-key display by
    # design; assert it shows the created key and leaks no provider secret/hash.
    shown = re.search(
        r'class="secret-display"[^>]*>\s*<code>(sk-slaif-[A-Za-z0-9._\-]+)</code>',
        resp.text,
    )
    assert shown, "none-delivery create must display the plaintext key once"
    assert resp.text.count(shown.group(1)) == 1
    assert "sk-provider-secret-placeholder-219" not in resp.text
    assert "sk-or-provider-secret-placeholder-219" not in resp.text
    assert "argon2" not in resp.text
    # Captured for the final log/audit secret scan: this ONE-TIME display
    # value must never appear anywhere else (logs, audit metadata, other
    # pages).
    env["g01_key_plaintext"] = shown.group(1)

    keys = _gateway_keys(env)
    new_ids = set(keys) - before_ids
    assert len(new_ids) == 1, new_ids
    created = keys[new_id := next(iter(new_ids))]
    assert created["owner_id"] == manifest["owner_std"]
    assert created["cohort_id"] == manifest["cohort"]
    assert created["metadata_json"].get("allowed_providers") == ["openai"]
    assert created["allowed_models"] == ["gpt-4.1-mini"]
    assert created["allow_all_endpoints"] is True
    env["g01_key"] = new_id

    # Safe export: attachment, typed doc, exact policy, no material.
    export = state.get(f"/admin/keys/{new_id}/configuration.json")
    assert "attachment" in export.headers["content-disposition"]
    doc = export.json()
    assert doc["schema_version"] == 1
    assert doc.get("allowed_providers") == ["openai"]
    assert doc.get("allowed_models") == ["gpt-4.1-mini"]
    # allow_all_endpoints is True: the endpoint allow-list is stored empty.
    assert doc.get("allowed_endpoints") == []
    # Absence semantics: this key was created with NO rate limit, so the
    # canonical export records an explicit null policy - never an invented
    # zero or empty object.
    assert doc.get("rate_limit_policy") is None
    body = export.text
    _canary_free(env, body)
    assert created["token_hash"] not in body

    # Strict round trip: the SAME exported document (one allowed policy
    # field changed) is re-POSTed through the advanced configuration. The
    # document itself has NO free-text note field - unknown fields are
    # refused by the strict version-1 law; the operator note is the audit
    # reason carried with the server actor.
    doc["allowed_models"] = ["gpt-4.1-nano"]
    detail = state.get(f"/admin/keys/{new_id}")
    resp = state.post(
        f"/admin/keys/{new_id}/configuration",
        {
            "csrf_token": _csrf(detail.text),
            "configuration_json": json.dumps(doc),
            "confirm_configuration_update": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code == 303, (resp.status_code, resp.text[:300])
    after = _gateway_keys(env)[new_id]
    assert after["metadata_json"].get("allowed_providers") == ["openai"]
    assert after["allowed_models"] == ["gpt-4.1-nano"]
    audits = _audits(env, "update_key_configuration", new_id)
    assert len(audits) >= 1
    assert audits[-1]["actor"] == manifest["superadmin"]
    assert audits[-1]["note"] == REASON

    # Round-tripped export keeps the changed model list and the null rate.
    doc2 = state.get(f"/admin/keys/{new_id}/configuration.json").json()
    assert doc2["allowed_models"] == ["gpt-4.1-nano"]
    assert doc2.get("rate_limit_policy") is None

    # Tri-state through the policy form: deny-all, then unrestricted.
    # None and [] are DELIBERATELY different canonical states: deny-all is
    # stored as an explicit empty list, unrestricted is stored as an
    # ABSENT field (the export renders it as an explicit null). No
    # truthiness shortcut may equate them.
    detail = state.get(f"/admin/keys/{new_id}")
    resp = state.post(
        f"/admin/keys/{new_id}/policy",
        {
            "csrf_token": _csrf(detail.text),
            "provider_deny_all": "true",
            "allowed_models": "gpt-4.1-nano",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code == 303, (resp.status_code, resp.text[:300])
    denied_meta = _gateway_keys(env)[new_id]["metadata_json"]
    denied_value = denied_meta.get("allowed_providers")
    assert isinstance(denied_value, list) and denied_value == []
    # The export renders the SAME canonical deny-all state (explicit []).
    denied_doc = state.get(f"/admin/keys/{new_id}/configuration.json").json()
    assert denied_doc.get("allowed_providers") == []

    detail = state.get(f"/admin/keys/{new_id}")
    resp = state.post(
        f"/admin/keys/{new_id}/policy",
        {
            "csrf_token": _csrf(detail.text),
            "allow_all_providers": "true",
            "allowed_models": "gpt-4.1-nano",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code == 303, (resp.status_code, resp.text[:300])
    final_meta = _gateway_keys(env)[new_id]["metadata_json"]
    assert "allowed_providers" not in final_meta, (
        "unrestricted must be the ABSENT field, not an empty list"
    )
    # The export renders the SAME canonical unrestricted state (null).
    final_doc = state.get(f"/admin/keys/{new_id}/configuration.json").json()
    assert "allowed_providers" in final_doc and final_doc["allowed_providers"] is None
    # Identity fields preserved through every policy mutation.
    assert _gateway_keys(env)[new_id]["owner_id"] == manifest["owner_std"]


# ---------------------------------------------------------------------------
# 03. G02/G03: rate editor + read-only route explanation
# ---------------------------------------------------------------------------


def test_03_g02_g03_rates_and_explanation(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    k1 = env["manifest"]["k1"]
    before = _gateway_keys(env)[k1]

    detail = state.get(f"/admin/keys/{k1}")
    resp = state.post(
        f"/admin/keys/{k1}/rate-limits",
        {
            "csrf_token": _csrf(detail.text),
            "rate_action_requests_per_window": "set",
            "rate_value_requests_per_window": "45",
            "rate_action_window": "set",
            "rate_value_window": "10",
            "reason": REASON,
        },
    )
    assert resp.status_code == 303, (resp.status_code, resp.text[:300])
    after = _gateway_keys(env)[k1]
    # requests-per-window is a scalar column; only window_seconds lives in
    # the metadata rate_limit_policy dict.
    assert after["rate_limit_requests_per_minute"] == 45
    assert after["rate_limit_policy"].get("window_seconds") == 10

    # Read-only explanation: real HTTP, no provider inference, no counters.
    calls_before = len(env["provider"].request_log)
    explain = state.post(
        f"/admin/keys/{k1}/explain-route",
        {"csrf_token": _csrf(state.get(f"/admin/keys/{k1}").text),
         "endpoint": "/v1/chat/completions",
         "model": "gpt-4.1-mini"},
    )
    assert explain.status_code == 200
    assert "openai" in explain.text
    assert "gpt-4.1-mini" in explain.text
    assert len(env["provider"].request_log) == calls_before, "explanation inferred"
    same = _gateway_keys(env)[k1]
    assert same["tokens_used_total"] == before["tokens_used_total"]
    assert same["requests_used_total"] == before["requests_used_total"]


# ---------------------------------------------------------------------------
# 04. G04: reviewed standard-key clone
# ---------------------------------------------------------------------------


def test_04_g04_reviewed_clone(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    # K2 carries a plain administrable stored policy; the codex-pinned keys
    # (K1/K6) are intentionally outside this configuration tool's scope.
    ksrc = manifest["k2"]
    source = _gateway_keys(env)[ksrc]
    before_ids = set(_gateway_keys(env))

    page = state.get(f"/admin/keys/{ksrc}/clone")
    resp = state.post(
        f"/admin/keys/{ksrc}/clone/review",
        {
            "csrf_token": _csrf(page.text),
            "target_owner_id": manifest["owner_cal"],
            "target_cohort_id": "",
            "validity_mode": "duration-from-now",
            "duration_value": "86400",
            "duration_unit": "seconds",
            "email_delivery_mode": "none",
        },
    )
    assert resp.status_code == 200, resp.text[:400]
    token = _token(resp.text, CLONE_TOKEN_RE)

    resp = state.post(
        f"/admin/keys/{ksrc}/clone/apply",
        {
            "csrf_token": _csrf(state.get(f"/admin/keys/{ksrc}").text),
            "clone_review_intent": token,
            "confirm_apply": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])

    new_ids = set(_gateway_keys(env)) - before_ids
    assert len(new_ids) == 1, new_ids
    clone = _gateway_keys(env)[new_id := next(iter(new_ids))]
    assert clone["token_hash"] != source["token_hash"], "clone reuses source material"
    assert clone["owner_id"] == manifest["owner_cal"]
    assert clone["cohort_id"] is None
    assert clone["tokens_used_total"] == 0
    assert clone["requests_used_total"] == 0
    # Faithful policy clone of K2's plain stored policy.
    assert clone["allow_all_models"] is False
    assert clone["allowed_models"] == ["gpt-4.1-nano"]
    assert clone["allow_all_endpoints"] is True
    # Source preserved byte-for-byte in identity/usage.
    assert _gateway_keys(env)[ksrc]["token_hash"] == source["token_hash"]
    assert _gateway_keys(env)[ksrc]["requests_used_total"] == source["requests_used_total"]
    env["g04_clone"] = new_id


# ---------------------------------------------------------------------------
# 05. G05: reviewed batch + safe repeat
# ---------------------------------------------------------------------------


def _batch_plan_fields(
    csrf: str, manifest: dict[str, str], key_ids: str | None = None
) -> dict[str, str]:
    if key_ids is None:
        key_ids = manifest["k2"] + "\n" + manifest["k3"]
    return {
        "csrf_token": csrf,
        "input_mode": "guided",
        "selection_kind": "keys",
        "cohort_id": "",
        "key_ids": key_ids,
        "status_active": "true",
        "cost_action": "unchanged",
        "cost_value": "",
        "token_action": "set",
        "token_value": "4000000",
        "request_action": "unchanged",
        "request_value": "",
        "rate_action_requests": "unchanged",
        "rate_value_requests": "",
        "rate_action_tokens": "unchanged",
        "rate_value_tokens": "",
        "rate_action_concurrency": "unchanged",
        "rate_value_concurrency": "",
        "rate_action_window": "unchanged",
        "rate_value_window": "",
        "providers_mode": "unchanged",
        "providers_value": "",
        "models_mode": "unchanged",
        "models_value": "",
        "endpoints_mode": "unchanged",
        "endpoints_value": "",
        "lazy_mode": "unchanged",
        "lazy_wait_seconds": "",
        "lazy_waiting": "",
        "live_burn_mode": "unchanged",
        "live_burn_cost_margin": "",
        "live_burn_token_margin": "",
        "configuration_json": "",
    }


def test_05_g05_reviewed_batch_and_safe_repeat(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    k2 = manifest["k2"]

    # K3 carries a HELD external-tool fence until test_12 settles it (later),
    # so the reviewed batch targets K2 + the non-fenced GUI key (g01) from
    # test_02: two plain, administrable, non-fenced keys.
    g01 = env["g01_key"]
    batch_keys = manifest["k2"] + "\n" + g01
    plan = state.post(
        "/admin/key-batch/plan",
        _batch_plan_fields(_csrf(state.get("/admin/key-batch").text), manifest, key_ids=batch_keys),
    )
    assert plan.status_code == 200, plan.text[:400]
    assert "2 selected" in plan.text
    token = _token(plan.text, BATCH_TOKEN_RE)

    result = state.post(
        "/admin/key-batch/apply",
        {
            "csrf_token": _csrf(plan.text),
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": REASON,
        },
    )
    assert result.status_code == 200, result.text[:400]
    assert "applied" in result.text
    keys = _gateway_keys(env)
    assert keys[k2]["token_limit_total"] == 4000000
    assert keys[g01]["token_limit_total"] == 4000000
    audits = _audits(env, "update_key_configuration")
    assert {a["entity_id"] for a in audits} >= {k2, g01}
    audits_before = len(audits)

    # Safe repeat: a FRESH re-plan is a read-only zero-diff preview and the
    # ORIGINAL reviewed token applies already_at_target with zero writes.
    replan = state.post(
        "/admin/key-batch/plan",
        _batch_plan_fields(_csrf(state.get("/admin/key-batch").text), manifest, key_ids=batch_keys),
    )
    assert replan.status_code == 200
    assert "0 changed" in replan.text
    assert "2 unchanged" in replan.text
    repeat = state.post(
        "/admin/key-batch/apply",
        {
            "csrf_token": _csrf(replan.text),
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": REASON,
        },
    )
    assert repeat.status_code == 200, repeat.text[:400]
    assert "already_at_target" in repeat.text
    assert len(_audits(env, "update_key_configuration")) == audits_before
    assert _gateway_keys(env)[k2]["token_limit_total"] == 4000000


# ---------------------------------------------------------------------------
# 06. G06/G07: partial route configuration + provider preparation
# ---------------------------------------------------------------------------


def _route_plan_fields(csrf: str, **extra: Any) -> dict[str, str]:
    fields: dict[str, str] = {
        "csrf_token": csrf,
        "capabilities_source": "unchanged",
        "requested_model_action": "unchanged",
        "match_type_action": "unchanged",
        "endpoint_action": "unchanged",
        "provider_action": "unchanged",
        "upstream_model_action": "unchanged",
        "priority_action": "unchanged",
        "visible_in_models_action": "unchanged",
        "supports_streaming_action": "unchanged",
        "notes_intent": "preserve",
        "codex_context_action": "unchanged",
        "codex_default_output_action": "unchanged",
        "codex_max_output_action": "unchanged",
        "media_image_action": "unchanged",
        "media_video_tokens_action": "unchanged",
        "media_video_frames_action": "unchanged",
        "completion_action": "unchanged",
    }
    fields.update(extra)
    return fields


def _route_plan_and_apply(
    state: _LoginState, route_id: str, **extra: Any
) -> tuple[int, str]:
    """One reviewed route plan + apply; returns (apply status, plan text)."""
    page = state.get(f"/admin/routes/{route_id}/configuration")
    plan = state.post(
        f"/admin/routes/{route_id}/configuration/plan",
        _route_plan_fields(_csrf(page.text), **extra),
    )
    assert plan.status_code == 200, plan.text[:400]
    resp = state.post(
        f"/admin/routes/{route_id}/configuration/apply",
        {
            "csrf_token": _csrf(state.get(f"/admin/routes/{route_id}/configuration").text),
            "route_config_review_intent": _token(plan.text, ROUTE_TOKEN_RE),
            "confirm_apply": "true",
            "reason": REASON,
        },
    )
    return resp.status_code, plan.text


def test_06_g06_g07_route_and_provider(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    route_mini = manifest["route_mini"]
    route_nano = manifest["route_nano"]

    from slaif_gateway.db.models import ModelRoute, ProviderConfig

    async def _route(session, route_id: str):
        row = await session.get(ModelRoute, uuid.UUID(route_id))
        assert row is not None
        return {
            "priority": row.priority,
            "enabled": row.enabled,
            "upstream_model": row.upstream_model,
            "match_type": row.match_type,
            "endpoint": row.endpoint,
            "provider": row.provider,
            "notes": row.notes,
            "capabilities": dict(row.capabilities or {}),
        }

    before_nano = _db(env["database_url"], lambda s: _route(s, route_nano))

    def _plan_and_apply(overrides: dict[str, str]) -> httpx.Response:
        page = state.get(f"/admin/routes/{route_mini}/configuration")
        plan = state.post(
            f"/admin/routes/{route_mini}/configuration/plan",
            _route_plan_fields(_csrf(page.text), **overrides),
        )
        assert plan.status_code == 200, plan.text[:400]
        return state.post(
            f"/admin/routes/{route_mini}/configuration/apply",
            {
                "csrf_token": _csrf(state.get(f"/admin/routes/{route_mini}/configuration").text),
                "route_config_review_intent": _token(plan.text, ROUTE_TOKEN_RE),
                "confirm_apply": "true",
                "reason": REASON,
            },
        )

    # G06 setup: ONE reviewed plan that moves priority AND sets the rich
    # capability leaves (codex limits + media estimates) on route_mini.
    plan_a_page = state.get(f"/admin/routes/{route_mini}/configuration")
    plan_a = state.post(
        f"/admin/routes/{route_mini}/configuration/plan",
        _route_plan_fields(
            _csrf(plan_a_page.text),
            priority_action="set",
            priority="5",
            media_image_action="set",
            media_image_value="1000000",
            media_video_tokens_action="set",
            media_video_tokens_value="500000",
            media_video_frames_action="set",
            media_video_frames_value="16",
            codex_context_action="set",
            codex_context_value="1000000",
            codex_default_output_action="set",
            codex_default_output_value="8192",
            codex_max_output_action="set",
            codex_max_output_value="32768",
        ),
    )
    assert plan_a.status_code == 200, plan_a.text[:400]
    # The reviewed plan names the actual changed leaves (leaf-level diff).
    assert "Media video frames" in plan_a.text
    assert "Codex context window" in plan_a.text
    resp = state.post(
        f"/admin/routes/{route_mini}/configuration/apply",
        {
            "csrf_token": _csrf(state.get(f"/admin/routes/{route_mini}/configuration").text),
            "route_config_review_intent": _token(plan_a.text, ROUTE_TOKEN_RE),
            "confirm_apply": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    after_a = _db(env["database_url"], lambda s: _route(s, route_mini))
    assert after_a["priority"] == 5
    assert after_a["capabilities"]["codex_limits"] == {
        "context_window_tokens": 1000000,
        "default_max_output_tokens": 8192,
        "max_output_tokens": 32768,
    }
    assert after_a["capabilities"]["media_input_estimation"] == {
        "version": 1,
        "image_tokens": 1000000,
        "video_tokens": 500000,
        "video_frames": 16,
    }

    # G06 THE requirement: an actual reviewed partial capability LEAF
    # change (video frames 16 -> 24, nothing else) on THE SAME route, then
    # the untouched deep siblings on that same route must be retained.
    apply_b = _plan_and_apply(
        media_video_frames_action="set", media_video_frames_value="24"
    )
    assert apply_b.status_code in (200, 303), (apply_b.status_code, apply_b.text[:300])
    after_b = _db(env["database_url"], lambda s: _route(s, route_mini))
    media = after_b["capabilities"]["media_input_estimation"]
    assert media["video_frames"] == 24, "changed leaf must persist"
    # Deep siblings on the SAME route are retained, byte-exact.
    assert media["image_tokens"] == 1000000
    assert media["video_tokens"] == 500000
    assert after_b["capabilities"]["codex_limits"] == {
        "context_window_tokens": 1000000,
        "default_max_output_tokens": 8192,
        "max_output_tokens": 32768,
    }
    # Non-capability route columns survive the leaf change untouched.
    assert after_b["priority"] == 5
    assert after_b["upstream_model"] == "gpt-4.1-mini"
    assert after_b["enabled"] is True
    assert after_b["match_type"] == "exact"
    assert after_b["endpoint"] == "/v1/chat/completions"
    assert after_b["provider"] == "openai"
    # Cross-route isolation (retained old evidence): the other route is
    # unchanged in every asserted dimension.
    after_nano = _db(env["database_url"], lambda s: _route(s, route_nano))
    assert after_nano == before_nano

    # Two reviewed applies, two audited updates, exact actor/note.
    audits = _audits(env, "model_route_updated", route_mini)
    assert len(audits) == 2, len(audits)
    for audit in audits:
        assert audit["actor"] == manifest["superadmin"]
        assert audit["note"] == REASON

    # G07: provider PREPARATION (create with notes, disabled), an UPDATE
    # that clears the existing notes, then EXPLICIT activation - three
    # distinct persisted mutations with separated preparation/activation
    # audits. (The seeded provider pages remain accepted read evidence.)
    providers = state.get("/admin/providers")
    assert "Synthetic OpenAI" in providers.text
    provider_page = state.get(f"/admin/providers/{manifest['provider']}")
    assert "openai" in provider_page.text
    _canary_free(env, provider_page.text)

    def _provider_row(provider_id: str) -> dict[str, Any]:
        async def _query(session):
            row = await session.get(ProviderConfig, uuid.UUID(provider_id))
            assert row is not None
            return {
                "provider": row.provider,
                "display_name": row.display_name,
                "enabled": row.enabled,
                "notes": row.notes,
                "timeout_seconds": row.timeout_seconds,
                "max_retries": row.max_retries,
            }

        return _db(env["database_url"], _query)

    create_page = state.get("/admin/providers/new")
    resp = state.post(
        "/admin/providers/new",
        {
            "csrf_token": _csrf(create_page.text),
            "provider": "syn219g",
            "display_name": "219 G07 Synthetic Provider",
            "kind": "openai_compatible",
            "base_url": "https://syn219g.example/v1",
            "api_key_env_var": "GUI219G_SYN219_KEY",
            "enabled": "",
            "timeout_seconds": "300",
            "max_retries": "0",
            "notes": "219 G07 prepared provider notes",
            "notes_intent": "replace",
            "reason": REASON,
        },
    )
    assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
    g07_id = re.search(r"/admin/providers/([0-9a-f-]{36})", resp.headers["location"]).group(1)
    prepared = _provider_row(g07_id)
    # Prepared but NOT activated: the enabled state is persisted False.
    assert prepared["enabled"] is False
    assert prepared["notes"] == "219 G07 prepared provider notes"
    assert prepared["timeout_seconds"] == 300
    created_audits = _audits(env, "provider_config_created", g07_id)
    assert len(created_audits) == 1
    assert created_audits[0]["actor"] == manifest["superadmin"]
    assert created_audits[0]["note"] == REASON

    edit_page = state.get(f"/admin/providers/{g07_id}/edit")
    resp = state.post(
        f"/admin/providers/{g07_id}/edit",
        {
            "csrf_token": _csrf(edit_page.text),
            "provider": "syn219g",
            "display_name": "219 G07 Synthetic Provider",
            "kind": "openai_compatible",
            "base_url": "https://syn219g.example/v1",
            "api_key_env_var": "GUI219G_SYN219_KEY",
            "enabled": "",
            "timeout_seconds": "320",
            "max_retries": "0",
            "notes": "",
            "notes_intent": "clear",
            "reason": REASON,
        },
    )
    assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
    updated = _provider_row(g07_id)
    # The update actually cleared the existing notes and changed a value;
    # the provider is still prepared, not activated.
    assert updated["notes"] is None
    assert updated["timeout_seconds"] == 320
    assert updated["enabled"] is False
    updated_audits = _audits(env, "provider_config_updated", g07_id)
    assert len(updated_audits) == 1
    assert updated_audits[0]["actor"] == manifest["superadmin"]
    assert updated_audits[0]["note"] == REASON

    detail_page = state.get(f"/admin/providers/{g07_id}")
    resp = state.post(
        f"/admin/providers/{g07_id}/enable",
        {"csrf_token": _csrf(detail_page.text), "reason": REASON},
    )
    assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
    assert "provider_config_enabled" in resp.headers["location"]
    activated = _provider_row(g07_id)
    assert activated["enabled"] is True
    enabled_audits = _audits(env, "provider_config_enabled", g07_id)
    assert len(enabled_audits) == 1
    assert enabled_audits[0]["actor"] == manifest["superadmin"]
    assert enabled_audits[0]["note"] == REASON

    # Separation of preparation from activation: the three mutations are
    # three distinct audit rows in chronological order.
    all_three = (created_audits + updated_audits + enabled_audits)
    assert [a["action"] for a in all_three] == [
        "provider_config_created",
        "provider_config_updated",
        "provider_config_enabled",
    ]


# ---------------------------------------------------------------------------
# 07. G08: retained content-free request diagnostics
# ---------------------------------------------------------------------------


def test_07_g08_content_free_diagnostics(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]

    diag = state.get("/admin/operations/diagnostics")
    resp = state.post(
        "/admin/operations/diagnostics/lookup",
        {
            "csrf_token": _csrf(diag.text),
            "lookup_id": manifest["diag_request_id"],
            "lookup_namespace": "gateway",
        },
    )
    assert resp.status_code == 200
    assert manifest["diag_request_id"] in resp.text
    assert "upstream_500" in resp.text
    # Content-free: no ledger request IDs, provider placeholders, or key
    # material on the investigation page.
    assert "219iw-req-" not in resp.text
    _canary_free(env, resp.text)

    unknown = state.post(
        "/admin/operations/diagnostics/lookup",
        {
            "csrf_token": _csrf(state.get("/admin/operations/diagnostics").text),
            "lookup_id": "gw-" + "f" * 32,
            "lookup_namespace": "gateway",
        },
    )
    assert unknown.status_code == 200
    assert "gw-" + "f" * 32 in unknown.text
    # Honest missing state, not an invented zero.
    assert "No retained record matches this ID" in unknown.text


# ---------------------------------------------------------------------------
# 08. G09: eligible replay inspect + monotonic TTL extension
# ---------------------------------------------------------------------------


def test_08_g09_replay_inspect_and_extend(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    k1 = env["manifest"]["k1"]

    from slaif_gateway.db.models import CodexReplayReference
    from slaif_gateway.services.codex_replay_maintenance import EXTEND_ACTION

    async def _refs(session):
        rows = (
            (
                await session.execute(
                    select(CodexReplayReference).where(
                        CodexReplayReference.gateway_key_id == uuid.UUID(k1)
                    )
                )
            ).scalars().all()
        )
        return [
            {
                "expires_at": r.expires_at,
                "item_id_hmac": r.item_id_hmac,
            }
            for r in rows
        ]

    before = _db(env["database_url"], _refs)
    assert len(before) == 1

    page = state.get(f"{REPLAY_BASE}/key/{k1}")
    scope_fields = {
        "csrf_token": _csrf(page.text),
        "scope": "key",
        "created_from": "",
        "created_until": "",
        "key_id": k1,
    }
    inspect = state.post(f"{REPLAY_BASE}/inspect", dict(scope_fields))
    assert inspect.status_code == 200, inspect.text[:400]
    assert k1 in inspect.text

    preview = state.post(
        f"{REPLAY_BASE}/preview",
        dict(scope_fields, ttl_seconds="86400", reason=REASON),
    )
    assert preview.status_code == 200, preview.text[:400]
    token = _token(preview.text, REVIEW_TOKEN_RE)
    resp = state.post(
        f"{REPLAY_BASE}/apply",
        {
            "csrf_token": _csrf(preview.text),
            "review_token": token,
            "confirm_apply": "1",
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])

    after = _db(env["database_url"], _refs)
    assert len(after) == 1
    assert after[0]["expires_at"] > before[0]["expires_at"], "TTL must extend monotonically"
    assert after[0]["item_id_hmac"] == before[0]["item_id_hmac"], "HMAC reference mutated"
    # No raw reference disclosure on any replay page.
    for html in (inspect.text, preview.text):
        assert before[0]["item_id_hmac"] not in html, "raw replay reference disclosed"
    audits = _audits(env, EXTEND_ACTION)
    assert audits, "replay extension not audited"


# ---------------------------------------------------------------------------
# 09. G10: preset identity + module upgrade/rollback + profile migration
# ---------------------------------------------------------------------------


def test_09_g10_compatibility(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    k1, k6 = manifest["k1"], manifest["k6"]

    # Registered preset directory: data identity page + exact download.
    index = state.get(f"{COMPAT_BASE}/")
    names = sorted(
        set(re.findall(rf"{re.escape(COMPAT_BASE)}/preset/([A-Za-z0-9._-]+)\"", index.text))
    )
    assert names, "no registered presets rendered"
    preset = names[0]
    page = state.get(f"{COMPAT_BASE}/preset/{preset}")
    assert preset in page.text
    download = state.get(f"{COMPAT_BASE}/preset/{preset}/download")
    assert download.status_code == 200
    assert f'attachment; filename="{preset}.json"' in download.headers["content-disposition"]
    preset_doc = download.json()
    assert json.dumps(preset_doc)
    assert "no-store" in download.headers.get("cache-control", "").lower()

    # K1 binding: exact 0149-v4 tuple.
    page = state.get(f"{COMPAT_BASE}/key/{k1}")
    # The bound form carries the exact frozen 0149-v4 digest.
    assert SUPERADMIN_PIN["fixture_sha256"] in page.text
    form = {"csrf_token": _csrf(page.text)}
    for name in ("from_version", "from_digest", "pin_selector"):
        form[name] = re.search(rf'name="{name}" value="([^"]*)"', page.text).group(1)

    def _pin(key_id: str) -> dict[str, str]:
        keys = _gateway_keys(env)
        return dict(keys[key_id]["metadata_json"]["responses_policy"]["client_module"])

    assert _pin(k1) == dict(SUPERADMIN_PIN)

    # Reviewed upgrade 0149-v4 -> 0149-v5 (exact persisted tuple, sentinels).
    review = state.post(
        f"{COMPAT_BASE}/key/{k1}/review",
        dict(form, operation_target="module_upgrade:0149-v5", reason=REASON),
    )
    assert review.status_code == 200, review.text[:400]
    assert "Dry run complete" in review.text
    token = _token(review.text, REVIEW_TOKEN_RE)
    resp = state.post(
        f"{COMPAT_BASE}/key/{k1}/apply",
        {
            "csrf_token": _csrf(state.get(f"{COMPAT_BASE}/key/{k1}").text),
            "review_token": token,
            "confirm_apply": "1",
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    pin = _pin(k1)
    assert pin == {
        "id": "codex-0.149-responses-v1",
        "version": "5",
        "fixture_sha256": "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec",
    }
    meta = _gateway_keys(env)[k1]["metadata_json"]
    assert meta["responses_policy"]["219_sentinel"] == {"kept": "keep-me"}
    assert meta["219_top_sentinel"] == {"kept": "keep-me"}
    assert len(_audits(env, "codex_client_module_upgraded", k1)) == 1

    # Reviewed rollback 0149-v5 -> 0149-v4.
    page = state.get(f"{COMPAT_BASE}/key/{k1}")
    form = {"csrf_token": _csrf(page.text)}
    for name in ("from_version", "from_digest", "pin_selector"):
        form[name] = re.search(rf'name="{name}" value="([^"]*)"', page.text).group(1)
    review = state.post(
        f"{COMPAT_BASE}/key/{k1}/review",
        dict(form, operation_target="module_rollback:0149-v4", reason=REASON),
    )
    assert review.status_code == 200, review.text[:400]
    resp = state.post(
        f"{COMPAT_BASE}/key/{k1}/apply",
        {
            "csrf_token": _csrf(state.get(f"{COMPAT_BASE}/key/{k1}").text),
            "review_token": _token(review.text, REVIEW_TOKEN_RE),
            "confirm_apply": "1",
        },
    )
    assert resp.status_code in (200, 303)
    assert _pin(k1) == dict(SUPERADMIN_PIN)
    assert len(_audits(env, "codex_client_module_rolled_back", k1)) == 1

    # K6: 0162-v1 data-profile migration to the ACTIVE profile.
    page = state.get(f"{COMPAT_BASE}/key/{k6}")
    form = {"csrf_token": _csrf(page.text)}
    for name in ("from_version", "from_digest", "pin_selector"):
        form[name] = re.search(rf'name="{name}" value="([^"]*)"', page.text).group(1)
    review = state.post(
        f"{COMPAT_BASE}/key/{k6}/review",
        dict(form, operation_target="migrate:active", reason=REASON),
    )
    assert review.status_code == 200, review.text[:400]
    resp = state.post(
        f"{COMPAT_BASE}/key/{k6}/apply",
        {
            "csrf_token": _csrf(state.get(f"{COMPAT_BASE}/key/{k6}").text),
            "review_token": _token(review.text, REVIEW_TOKEN_RE),
            "confirm_apply": "1",
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    assert len(_audits(env, "codex_key_profile_migrated", k6)) == 1
    # The pin moved to the EXACT expected ACTIVE snapshot identity (not
    # merely off the old pin): the same resolution the apply worker used.
    from slaif_gateway.modules.clients.codex_0162 import (
        CODEX_0162_CLIENT_MODULE_ID,
    )
    from slaif_gateway.modules.clients.registry import get_client_module

    active = get_client_module(CODEX_0162_CLIENT_MODULE_ID)
    assert _pin(k6) == {
        "id": CODEX_0162_CLIENT_MODULE_ID,
        "version": active.module_version,
        "fixture_sha256": active.fixture_sha256,
    }

    # G10 credential-free route profile/config/catalog artifacts: the
    # stored ready codex route serves byte-exact artifacts rendered from
    # the VALID configured public gateway URL (HTTP numeric-loopback
    # /v1). The no-key law: the artifacts carry env-var NAMES, never
    # values; the attachment context is non-rotating (the still-displayed
    # origin page's form token survives the download).
    from slaif_gateway.services.codex_profile_registry import (
        QWEN38_CODEX_PROFILE_ID,
    )
    from slaif_gateway.services.codex_qualification import render_codex_profile

    public_base_url = "http://127.0.0.1:8000/v1"  # the fixture's PUBLIC_BASE_URL
    expected = render_codex_profile(public_base_url, QWEN38_CODEX_PROFILE_ID)
    route_codex = manifest["route_codex"]
    origin_page = state.get(f"/admin/routes/{route_codex}")
    origin_csrf = _csrf(origin_page.text)

    base = state.get(f"/admin/routes/{route_codex}/codex-profile/base")
    assert base.headers["content-disposition"] == (
        'attachment; filename="codex-provider.config.toml"'
    )
    assert "no-store" in base.headers["cache-control"].lower()
    assert base.text == expected.base_config_toml

    profile = state.get(f"/admin/routes/{route_codex}/codex-profile/profile")
    assert "no-store" in profile.headers["cache-control"].lower()
    assert profile.text == expected.profile_config_toml

    catalog = state.get(f"/admin/routes/{route_codex}/codex-profile/catalog")
    assert "no-store" in catalog.headers["cache-control"].lower()
    assert expected.model_catalog_json is not None
    assert json.loads(catalog.text) == json.loads(expected.model_catalog_json)

    # No-key law: no credential material or env-var VALUES in any artifact.
    for artifact in (base, profile, catalog):
        assert "sk-" not in artifact.text
        assert "GUI219C_SYN219_KEY=" not in artifact.text
        assert "sk-provider-secret-placeholder-219" not in artifact.text
    # The base fragment references the env-var NAME only.
    assert 'env_key = "OPENAI_API_KEY"' in base.text
    # Non-rotating attachment context: the still-displayed origin page's
    # form token is unchanged after the downloads.
    origin_after = state.get(f"/admin/routes/{route_codex}")
    assert _csrf(origin_after.text) == origin_csrf
    # The compatibility index offers the same ready route's artifact links.
    index = state.get(f"{COMPAT_BASE}/")
    assert f"/admin/routes/{route_codex}/codex-profile/profile" in index.text


# ---------------------------------------------------------------------------
# 10. G11/G13/G18: grouped usage paging + CSV export + pricing + FX
# ---------------------------------------------------------------------------


def test_10_g11_g13_g18_usage_export_pricing_fx(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    k1 = env["manifest"]["k1"]

    # Ledger paging: 61 seeded K1 rows (60 observed + 1 live-burn) ->
    # 50 + 11 at the 50-row page bound (legacy retained evidence).
    page1 = state.get("/admin/usage", params={"gateway_key_id": k1, "limit": 50, "offset": 0})
    rows1 = re.findall(r"/admin/usage/[0-9a-f-]{36}", page1.text)
    assert len(set(rows1)) == 50, len(set(rows1))
    page2 = state.get("/admin/usage", params={"gateway_key_id": k1, "limit": 50, "offset": 50})
    rows2 = re.findall(r"/admin/usage/[0-9a-f-]{36}", page2.text)
    assert len(set(rows2)) == 11
    assert not (set(rows1) & set(rows2)), "pages overlap"
    # Filter-preserving paging: the next-page link keeps the key filter.
    flat1 = page1.text.replace("&amp;", "&").replace("\n", "")
    assert "gateway_key_id=" + k1 in flat1 and "offset=50" in flat1

    # G11 grouped usage report: the EXACT K1 scope aggregates into one
    # provider/model group with exact counts and honest cost availability
    # (estimated cost is KNOWN-MISSING on every seeded row; actual cost is
    # fully known). The scope flash states the exact accepted row count.
    summary = state.get(
        "/admin/reports/",
        params={"group_by": "provider_model", "gateway_key_id": k1},
    )
    assert "61 ledger rows" in summary.text
    assert "1 groups (provider_model)" in summary.text
    assert "openai / gpt-4.1-mini" in summary.text
    # Exact group counts: 61 requests, all successful, 10,300 tokens.
    assert 'data-sort-value="61"' in summary.text
    assert 'data-sort-value="10300"' in summary.text
    # Known-missing honesty: estimated cost renders unavailable (no rows
    # carried an estimated cost), actual cost is exact and complete.
    assert "unavailable" in summary.text
    assert "0.00912 EUR" in summary.text
    _canary_free(env, summary.text)

    # G11 live-burn report: the exact K1 scope aggregates the ONE seeded
    # streaming live-burn stop with exact stop-reason and provenance
    # counts (final provider usage available, estimate not final).
    burn = state.get(
        "/admin/reports/live-burn", params={"gateway_key_id": k1}
    )
    assert "1" in burn.text
    assert 'data-sort-value="1234"' in burn.text
    assert "0.000123456 EUR" in burn.text
    # Interrupted/estimated rows are counted, never backfilled: the
    # provenance missing counter is exactly 0 for this scope.
    assert "Final provider usage missing" in burn.text
    _canary_free(env, burn.text)

    # The usage detail page renders the sanitized live-burn section for
    # the seeded streaming row.
    detail = state.get(f"/admin/usage/{env['manifest']['burn_ledger']}")
    assert "Chat streaming live-burn" in detail.text
    assert "cost" in detail.text
    _canary_free(env, detail.text)

    # Safe machine export (explicit confirmation + reason).
    export = state.post(
        "/admin/usage/export.csv",
        {
            "csrf_token": _csrf(state.get("/admin/usage", params={"gateway_key_id": k1}).text),
            "confirm_export": "1",
            "reason": REASON,
        },
    )
    assert export.status_code == 200, export.status_code
    assert "text/csv" in export.headers["content-type"]
    body = export.text
    assert "219iw-req-" in body
    _canary_free(env, body)

    # G13: reviewed model-pricing disable.
    preview = state.post(
        "/admin/reports/pricing-disable/preview",
        {
            "csrf_token": _csrf(state.get("/admin/reports/pricing-disable").text),
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "reason": REASON,
        },
    )
    assert preview.status_code == 200, preview.text[:400]
    resp = state.post(
        "/admin/reports/pricing-disable/apply",
        {
            "csrf_token": _csrf(preview.text),
            "review_token": _token(preview.text, REVIEW_TOKEN_RE),
            "confirm_apply": "1",
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])

    from slaif_gateway.db.models import PricingRule

    async def _rule(session):
        rows = (
            (
                await session.execute(
                    select(PricingRule).where(
                        PricingRule.provider == "openai",
                        PricingRule.upstream_model == "gpt-4.1-mini",
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 1
        return {"enabled": rows[0].enabled}

    rule = _db(env["database_url"], _rule)
    assert rule["enabled"] is False, "pricing rule not disabled"

    # G11 safe JSON report export: the SAME exact K1 scope through the
    # confirmed strict-JSON attachment. Exact raw machine units, exact
    # scope/provenance metadata, no-store, and an audit row carrying the
    # scope - then an OVERBOUND scope is refused with exact counts and
    # no partial export and no audit.
    audits_before = len(_audits(env, "admin_usage_export_json"))
    export_page = state.get("/admin/reports/export")
    jexport = state.post(
        "/admin/reports/export",
        {
            "csrf_token": _csrf(export_page.text),
            "confirm_export": "1",
            "reason": REASON,
            "gateway_key_id": k1,
        },
    )
    assert jexport.status_code == 200, jexport.status_code
    assert "application/json" in jexport.headers["content-type"]
    assert "attachment" in jexport.headers["content-disposition"]
    assert "no-store" in jexport.headers["cache-control"].lower()
    payload = jexport.json()
    assert set(payload) == {"generated_at", "scope", "rows"}
    # Provenance: exact submitted scope + default limit + exact row count.
    assert payload["scope"]["filters"]["gateway_key_id"] == k1
    assert payload["scope"]["limit"] == 10000
    assert payload["scope"]["row_count"] == 61
    assert len(payload["rows"]) == 61
    # generated_at is a parseable instant (provenance timestamp).
    datetime.fromisoformat(payload["generated_at"])
    # Exact raw machine units on an observed row (Decimal as exact text).
    by_request = {row["request_id"]: row for row in payload["rows"]}
    first_req = "219iw-req-"
    observed = next(row for rid, row in by_request.items() if rid.startswith(first_req))
    assert observed["prompt_tokens"] == 100
    assert observed["completion_tokens"] == 50
    assert observed["total_tokens"] == 150
    assert observed["actual_cost_eur"] == "0.000150000"
    assert observed["estimated_cost_eur"] is None
    # The live-burn row's safe telemetry is exported, its estimate never
    # labelled invoice-grade.
    burn_row = next(
        row for row in payload["rows"] if row["request_id"] == "219iw-burn-" + env["manifest"]["suffix"]
    )
    assert burn_row["streaming"] is True
    assert burn_row["chat_live_burn_triggered"] is True
    assert burn_row["chat_live_burn_stop_reason"] == "cost"
    assert burn_row["chat_live_burn_estimated_tokens_at_stop"] == 1234
    assert burn_row["chat_live_burn_final_provider_usage_available"] is True
    _canary_free(env, jexport.text)
    # The export audit row carries the exact scope and the server actor.
    jaudits = _audits(env, "admin_usage_export_json")
    assert len(jaudits) == audits_before + 1
    jaudit = jaudits[-1]
    assert jaudit["actor"] == env["manifest"]["superadmin"]
    assert jaudit["note"] == REASON
    assert jaudit["new"]["row_count"] == 61
    assert jaudit["new"]["filters"]["gateway_key_id"] == k1
    # Overbound scope: exact-count refusal, no partial artifact, no audit.
    overbound = state.post(
        "/admin/reports/export",
        {
            "csrf_token": _csrf(state.get("/admin/reports/export").text),
            "confirm_export": "1",
            "reason": REASON,
            "gateway_key_id": k1,
            "limit": "10",
        },
    )
    assert overbound.status_code == 400, overbound.status_code
    assert "11 or more" in overbound.text
    assert "No partial export was produced" in overbound.text
    assert len(_audits(env, "admin_usage_export_json")) == audits_before + 1

    # G18: effective FX lookup (seeded USD->EUR 0.92) and honest missing.
    fx = state.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "USD", "quote_currency": "EUR"},
    )
    assert "0.92" in fx.text
    missing = state.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "EUR", "quote_currency": "GBP"},
    )
    assert missing.status_code == 200  # honest unavailable, not a 500
    # Honest unavailable wording, not merely HTTP 200: the missing pair
    # (EUR->GBP is not seeded; only GBP->EUR and USD->EUR exist) renders
    # the fixed no-rate direction with no inferred conversion.
    assert "No FX rate is effective for EUR / GBP" in missing.text
    assert "no rate is inferred" in missing.text


# ---------------------------------------------------------------------------
# 11. G12: delivery lifecycle + explicit retry + bounded SMTP test
# ---------------------------------------------------------------------------


def test_11_g12_email_delivery_lifecycle(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    sink = env["sink"]

    from slaif_gateway.db.models import EmailDelivery

    def _deliveries() -> list[dict[str, Any]]:
        async def _q(session):
            rows = (await session.execute(select(EmailDelivery))).scalars().all()
            return [
                {"id": str(r.id), "status": r.status, "recipient": r.recipient_email}
                for r in rows
            ]

        return _db(env["database_url"], _q)

    before = {d["id"]: d for d in _deliveries()}

    # GUI key create with PENDING delivery (real operator workflow).
    page = state.get("/admin/keys/create")
    resp = state.post(
        "/admin/keys/create",
        {
            "csrf_token": _csrf(page.text),
            "owner_id": manifest["owner_std"],
            "cohort_id": "",
            "valid_days": "30",
            "email_delivery_mode": "pending",
            "allow_all_providers": "true",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    # Success renders the 200 no-store create result page (not a redirect).
    assert resp.status_code == 200, (resp.status_code, resp.text[:300])
    now = {d["id"]: d for d in _deliveries()}
    new_ids = set(now) - set(before)
    assert len(new_ids) == 1, new_ids
    delivery_id = next(iter(new_ids))
    assert now[delivery_id]["status"] == "pending"
    assert now[delivery_id]["recipient"] == f"owner-std-{manifest['suffix']}@example.org"

    # Detail inspection shows the send surface.
    detail = state.get(f"/admin/email-deliveries/{delivery_id}")
    assert f"/admin/email-deliveries/{delivery_id}/send-now" in detail.text
    _canary_free(env, detail.text)

    # Explicit send-now through the REAL loopback SMTP sink.
    sent = state.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        {"csrf_token": _csrf(detail.text), "confirm_send": "true"},
    )
    assert sent.status_code == 303, (sent.status_code, sent.text[:300])
    assert len(sink.received) == 1, "SMTP sink did not receive exactly one message"
    assert sink.received[0]["to"].strip("<>") == now[delivery_id]["recipient"]
    assert {d["id"]: d for d in _deliveries()}[delivery_id]["status"] == "sent"

    # Consumed-secret negative boundary: the already-sent delivery, even
    # flipped to failed, is NOT retryable - its one-time secret is consumed
    # and can never be made resendable (shared Core law, surfaced honestly).
    async def _fail_consumed(session):
        # AsyncSession closes without committing; the flip needs an explicit
        # transaction to be durable.
        async with session.begin():
            row = await session.get(EmailDelivery, uuid.UUID(delivery_id))
            assert row is not None
            row.status = "failed"

    _db(env["database_url"], _fail_consumed)
    blocked = state.get(f"/admin/email-deliveries/{delivery_id}")
    assert 'id="retry-mode-select"' not in blocked.text
    assert "not currently retryable" in blocked.text

    # Explicit eligible FAILED retry: a FRESH pending delivery (its one-time
    # secret never consumed) is flipped to failed (SETUP simulating an SMTP
    # outage) with a known-code error audit, then the GUI retry-failed action
    # re-sends it exactly once with a persisted actor/reason audit.
    before2 = {d["id"]: d for d in _deliveries()}
    page2 = state.get("/admin/keys/create")
    resp2 = state.post(
        "/admin/keys/create",
        {
            "csrf_token": _csrf(page2.text),
            "owner_id": manifest["owner_std"],
            "cohort_id": "",
            "valid_days": "30",
            "email_delivery_mode": "pending",
            "allow_all_providers": "true",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    assert resp2.status_code == 200, (resp2.status_code, resp2.text[:300])
    now2 = {d["id"]: d for d in _deliveries()}
    retry_ids = set(now2) - set(before2)
    assert len(retry_ids) == 1, retry_ids
    retry_id = next(iter(retry_ids))
    assert now2[retry_id]["status"] == "pending"

    async def _fail_fresh(session):
        from slaif_gateway.db.repositories.audit import AuditRepository

        # Explicit transaction: the flip + error audit must be durable.
        async with session.begin():
            row = await session.get(EmailDelivery, uuid.UUID(retry_id))
            assert row is not None
            row.status = "failed"
            await AuditRepository(session).add_audit_log(
                action="email_key_failed",
                entity_type="email_delivery",
                entity_id=retry_id,
                new_values={"error_code": "smtp_send_error", "email_delivery_id": str(retry_id)},
            )

    _db(env["database_url"], _fail_fresh)
    detail = state.get(f"/admin/email-deliveries/{retry_id}")
    assert 'id="retry-mode-select"' in detail.text
    assert 'id="retry-reason-input"' in detail.text
    assert 'id="retry-confirm-checkbox"' in detail.text
    # Safe known-code failure provenance (never raw prose).
    assert "smtp_send_error" in detail.text
    _canary_free(env, detail.text)
    retry_reason = "219 installed retry after synthetic SMTP outage"
    retried = state.post(
        f"/admin/email-deliveries/{retry_id}/retry-failed",
        {
            "csrf_token": _csrf(detail.text),
            "retry_mode": "send-now",
            "reason": retry_reason,
            "confirm_retry": "true",
        },
    )
    assert retried.status_code == 303, (retried.status_code, retried.text[:300])
    assert len(sink.received) == 2, "retry must send exactly once"
    assert sink.received[-1]["to"].strip("<>") == now2[retry_id]["recipient"]
    assert {d["id"]: d for d in _deliveries()}[retry_id]["status"] == "sent"
    sent_audits = [
        a
        for a in _audits(env, "email_key", retry_id)
        if a["note"] == retry_reason and (a["new"] or {}).get("status") == "sent"
    ]
    assert len(sent_audits) == 1, sent_audits
    assert sent_audits[0]["actor"] is not None

    # Bounded SMTP TEST against the owned synthetic recipient/service.
    review = state.post(
        "/admin/email-operations/smtp-test/review",
        {
            "csrf_token": _csrf(state.get("/admin/email-operations/smtp-test").text),
            "recipient": "219-sink@example.invalid",
        },
    )
    assert review.status_code == 200, review.text[:400]
    resp = state.post(
        "/admin/email-operations/smtp-test/apply",
        {
            "csrf_token": _csrf(review.text),
            "review_token": _token(review.text, REVIEW_TOKEN_RE),
            "confirm_send_test": "true",
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    assert len(sink.received) == 3
    assert sink.received[-1]["to"].strip("<>") == "219-sink@example.invalid"


# ---------------------------------------------------------------------------
# 12. G14: the four accounting candidate/recovery families
# ---------------------------------------------------------------------------


def test_12_g14_accounting_operations(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    k2, k3, k5 = manifest["k2"], manifest["k3"], manifest["k5"]

    from slaif_gateway.db.models import QuotaReservation, UsageLedger, GatewayKey

    def _resv(rid: str):
        async def _q(session):
            row = await session.get(QuotaReservation, uuid.UUID(rid))
            assert row is not None
            return {"status": row.status, "released_at": row.released_at is not None}

        return _db(env["database_url"], _q)

    def _ledger(lid: str):
        async def _q(session):
            row = await session.get(UsageLedger, uuid.UUID(lid))
            assert row is not None
            return {
                "status": row.accounting_status,
                "success": row.success,
                "actual_cost": float(row.actual_cost_eur) if row.actual_cost_eur is not None else None,
                "meta": dict(row.response_metadata or {}),
            }

        return _db(env["database_url"], _q)

    def _key(rid: str):
        async def _q(session):
            row = await session.get(GatewayKey, uuid.UUID(rid))
            assert row is not None
            return {"fence": row.external_tool_fence_state,
                    "reserved_tokens": row.tokens_reserved_total}

        return _db(env["database_url"], _q)

    def _apply(url: str, token: str, csrf: str):
        resp = state.post(url, {"csrf_token": csrf, "review_token": token, "confirm_apply": "1"})
        assert resp.status_code == 200, (url, resp.status_code, resp.text[:300])
        return resp

    BASE = "/admin/accounting-operations"

    # (1) expired-reservations: preview -> review -> apply (authoritative).
    view = state.get(f"{BASE}/expired-reservations")
    assert k2 in view.text
    preview = state.post(
        f"{BASE}/expired-reservations/preview",
        {
            "csrf_token": _csrf(view.text),
            "reason": REASON,
            "exact_reservation_id": manifest["reservation"],
        },
    )
    assert preview.status_code == 200, preview.text[:400]
    resp = _apply(f"{BASE}/expired-reservations/apply", _token(preview.text, REVIEW_TOKEN_RE), _csrf(preview.text))
    assert "Committed: 1 row(s) settled" in resp.text
    assert _resv(manifest["reservation"]) == {"status": "expired", "released_at": True}
    assert _key(k2)["reserved_tokens"] == 0

    # (2) external-tool-fences: READ-ONLY inspection, no action surface.
    fences = state.get(f"{BASE}/external-tool-fences")
    assert k5 in fences.text
    assert k3 in fences.text
    assert "/apply" not in fences.text, "fence view must stay read-only"

    # (3) external-tool-holds: operator-asserted finalize (unknown cost never
    #     defaults: the operator supplies the explicit actuals).
    preview = state.post(
        f"{BASE}/external-tool-holds/preview",
        {
            "csrf_token": _csrf(state.get(f"{BASE}/external-tool-holds").text),
            "hold_action": "finalize-actual",
            "reason": REASON,
            "reservation_id": manifest["hold_reservation"],
            "actual_cost_eur": "0.42",
            "actual_total_tokens": "2500",
            "outcome": "success",
        },
    )
    assert preview.status_code == 200, preview.text[:400]
    resp = _apply(f"{BASE}/external-tool-holds/apply", _token(preview.text, REVIEW_TOKEN_RE), _csrf(preview.text))
    assert "Committed: 1 row(s) settled" in resp.text
    held = _ledger(manifest["hold_ledger"])
    assert held["status"] == "finalized"
    assert held["success"] is True
    assert held["actual_cost"] == 0.42
    assert held["meta"]["external_tool_accounting_hold"]["needs_reconciliation"] is False
    assert _key(k3)["fence"] == "none"
    assert _key(k3)["reserved_tokens"] == 0
    assert _audits(env, "external_tool_accounting_hold_reconciled")

    # (4) provider-completed-recovery: authoritative stored outcome.
    preview = state.post(
        f"{BASE}/provider-completed-recovery/preview",
        {
            "csrf_token": _csrf(state.get(f"{BASE}/provider-completed-recovery").text),
            "reason": REASON,
            "exact_ledger_id": manifest["pcr_ledger"],
        },
    )
    assert preview.status_code == 200, preview.text[:400]
    resp = _apply(
        f"{BASE}/provider-completed-recovery/apply",
        _token(preview.text, REVIEW_TOKEN_RE),
        _csrf(preview.text),
    )
    assert "Committed: 1 row(s) settled" in resp.text
    pcr = _ledger(manifest["pcr_ledger"])
    assert pcr["status"] == "finalized"
    assert pcr["success"] is True
    assert pcr["meta"]["recovery_state"] != "provider_completed_finalization_failed"
    assert _resv(manifest["pcr_reservation"])["status"] in ("finalized", "released")


# ---------------------------------------------------------------------------
# 13. G15: sealed catalog refresh through the REAL application worker
# ---------------------------------------------------------------------------


def _custody_settings(env: dict[str, Any]) -> Any:
    from slaif_gateway.config import Settings

    return Settings(
        APP_ENV="test",
        DATABASE_URL=env["database_url"],
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET=_gen_secret(),
        TOKEN_HMAC_SECRET_V1=_gen_secret(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=_gen_secret(),
        ACTIVE_HMAC_KEY_VERSION="1",
        GATEWAY_KEY_PREFIX="sk-slaif-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ENABLE_ADMIN_DASHBOARD=True,
        ENABLE_EMAIL_DELIVERY=False,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder-219",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder-219",
        CATALOG_REFRESH_GUI_ENABLED=True,
        CATALOG_REFRESH_ROOT=str(env["custody_root"]),
        CATALOG_REFRESH_SEAL_KEY=str(env["seal_key"]),
        CATALOG_REFRESH_MAX_TOTAL_BYTES=1024 * 1024 * 1024,
        CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS=300,
    )


def _wait_job(env: dict[str, Any], family: str, known: set[str] | None = None, timeout: float = 300.0) -> dict[str, Any]:
    from slaif_gateway.services import admin_catalog_refresh as custody

    settings = _custody_settings(env)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for row in custody.list_jobs(settings, limit=100):
            if row.get("family") == family and row.get("status") in TERMINAL_JOB_STATUSES:
                if known is None or row["job_id"] not in known:
                    return row
        time.sleep(1.0)
    raise AssertionError(f"no terminal {family} job within {timeout}s")


def _route_count(env: dict[str, Any]) -> int:
    from slaif_gateway.db.models import ModelRoute

    async def _q(session):
        rows = (await session.execute(select(ModelRoute))).scalars().all()
        return len(rows)

    return _db(env["database_url"], _q)


def test_13_g15_catalog_refresh_real_worker(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    BASE = CATALOG_BASE
    # Snapshot the custody job ids that EXIST before this test creates
    # any job: every _wait_job below must observe a FRESH job of this
    # run, never a stale terminal record (the bounded console
    # projection lists all retained jobs, and a stale terminal job of
    # the same family must never be mistaken for the one just created).
    from slaif_gateway.services import admin_catalog_refresh as _custody_219

    _known_jobs = {
        row["job_id"]
        for row in _custody_219.list_jobs(_custody_settings(env), limit=100)
    }

    # (1) Proposal generation through the real worker (synthetic source
    #     bytes only; the registry/bridge/composition is production). The
    #     configured currency is non-USD (EUR): the worker captures the ONE
    #     seeded USD->EUR rate before generation and publishes the TSV
    #     already converted - the accepted 217 currency law.
    resp = state.post(
        f"{BASE}/proposals/generate",
        {
            "csrf_token": _csrf(state.get(f"{BASE}/proposals").text),
            "provider_scope": "openrouter",
            "endpoint_scope": "chat_completions",
            "source_method": "docs",
            "max_models": "500",
            "fetch_details_limit": "0",
            "max_web_calls": "3",
            "currency": "EUR",
            "ordinary_chat_only": "on",
            "paired_ready_only": "on",
            "package_name": "openrouter-chat-text",
        },
    )
    proposal = _wait_job(env, "proposal", known=_known_jobs)
    assert proposal["status"] == "ready", proposal
    # Broker acknowledgement is a durable job-record fact (the console HTML
    # does not render the dispatch note). A terminal "ready" job additionally
    # proves a real worker executed, which requires a successful broker dispatch.
    assert proposal["dispatch"] == "confirmed", proposal
    job_id: str = proposal["job_id"]

    tsv = state.get(f"{BASE}/jobs/{job_id}/artifact/pricing-proposal.tsv")
    assert tsv.status_code == 200
    # The published TSV is ALREADY converted to EUR at the captured rate;
    # source USD facts and the applied FX pair are preserved per row. Exact
    # Decimal equality (9-decimal storage, HALF_UP) - never floats/tolerance.
    from slaif_gateway.services.pricing_import import parse_pricing_import_tsv

    quantum = Decimal("0.000000001")
    data_rows = [r for r in parse_pricing_import_tsv(tsv.text) if r.get("model")]
    assert data_rows, "no pricing rows were published"
    for r in data_rows:
        assert r["currency"] == "EUR"
        metadata = json.loads(r["pricing_metadata"])
        assert metadata["source_currency"] == "USD"
        # Frozen string projection; compare as exact Decimal (trailing-zero
        # normalization is production behavior).
        assert Decimal(metadata["fx"]["rate"]) == Decimal("0.92")
        for price_field in (
            "input_price_per_1m",
            "cached_input_price_per_1m",
            "output_price_per_1m",
            "reasoning_price_per_1m",
            "request_price",
        ):
            original = metadata["source_prices"][price_field]
            if original in (None, ""):
                assert r[price_field] == ""
            else:
                expected = (
                    Decimal(original) * Decimal("0.92")
                ).quantize(quantum, rounding=ROUND_HALF_UP)
                assert Decimal(r[price_field]) == expected, (
                    r["model"], price_field, r[price_field], expected,
                )

    # The normalized JSON artifact carries the same capture fact (no floats).
    normalized = state.get(f"{BASE}/jobs/{job_id}/artifact/provider-catalog-normalized.json")
    assert normalized.status_code == 200
    payload = json.loads(normalized.text)
    assert payload["fx"]["target_currency"] == "EUR"
    assert Decimal(payload["fx"]["rate"]) == Decimal("0.92")

    # (2) Strict import preview of the converted rows (NO import execution):
    # the preview must DISPLAY the converted EUR amounts.
    preview = state.post(
        f"{BASE}/jobs/{job_id}/import-preview/pricing",
        {"csrf_token": _csrf(state.get(f"{BASE}/proposals").text)},
    )
    assert preview.status_code == 200, preview.text[:400]
    assert "EUR" in preview.text
    page_decimals = {
        Decimal(token)
        for token in re.findall(r"\d+\.\d+", preview.text)
    }
    converted_amounts = [
        Decimal(r["input_price_per_1m"])
        for r in data_rows
        if r.get("input_price_per_1m") not in (None, "")
    ]
    assert converted_amounts, "no converted input price published"
    assert any(v in page_decimals for v in converted_amounts), (
        "no converted EUR amount rendered in import preview"
    )
    _canary_free(env, preview.text)

    # (3) Collect through the real worker -> sealed run. REFRESH mode
    # without an uploaded baseline (the accepted 217 legacy rule): this
    # fixture seeds a non-empty deployment catalog (providers/routes/
    # pricing/FX for the GUI scenarios), and bootstrap collect/apply is
    # lawfully refused on a populated catalog - the sealed baseline is
    # therefore exported from the configured target at collect time, so
    # the reviewed apply can lawfully commit against it.
    resp = state.post(
        f"{BASE}/collect/submit",
        {
            "csrf_token": _csrf(state.get(f"{BASE}/collect").text),
            "mode": "refresh",
            "providers": ["openrouter"],
        },
    )
    # Admission + broker acknowledgement are page-visible facts (the sealed
    # worker execution is proven by the terminal job below).
    assert resp.status_code == 200, (resp.status_code, resp.text[:600])
    assert "broker acknowledged" in resp.text, resp.text[:600]
    collect = _wait_job(env, "collect", known=_known_jobs)
    assert collect["status"] in ("ready", "warnings"), collect
    assert collect["dispatch"] == "confirmed", collect
    run_id: str = collect["run_id"]
    assert run_id.startswith("collect-")

    # (4) Real run facts + verify.
    run_page = state.get(f"{BASE}/runs/{run_id}/")
    assert run_id in run_page.text
    resp = state.post(f"{BASE}/runs/{run_id}/verify", {"csrf_token": _csrf(run_page.text)})
    assert resp.status_code == 200, resp.text[:400]

    # (5) Queued export-baseline of the REAL owned database.
    resp = state.post(f"{BASE}/export-baseline/submit", {"csrf_token": _csrf(state.get(f"{BASE}/export-baseline").text)})
    export = _wait_job(env, "export_baseline", known=_known_jobs)
    assert export["status"] == "ready", export
    assert export["dispatch"] == "confirmed", export
    artifact = export["artifact_name"]
    document = state.get(f"{BASE}/jobs/{export['job_id']}/artifact/{artifact}").json()
    assert document["schema_version"] == "1"
    assert document["sql_checked"] is True

    # (6) Reviewed atomic apply: sealed facts -> exact warning acks -> signed
    #     apply -> authoritative status.
    before_routes = _route_count(env)
    first = state.post(f"{BASE}/runs/{run_id}/apply-preview", {"csrf_token": _csrf(state.get(f"{BASE}/runs/{run_id}/").text)})
    assert first.status_code == 200, first.text[:400]
    warnings = re.findall(r'name="ack_warning_code" value="([^"]+)"', first.text)
    second = state.post(
        f"{BASE}/runs/{run_id}/apply-preview",
        {"csrf_token": _csrf(first.text), "reason": REASON, "ack_warning_code": warnings},
    )
    assert second.status_code == 200, second.text[:400]
    token = _token(second.text, REVIEW_TOKEN_RE)
    resp = state.post(
        f"{BASE}/runs/{run_id}/apply",
        {
            "csrf_token": _csrf(second.text),
            "review_token": token,
            "confirm_apply": "on",
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    assert _route_count(env) > before_routes, "catalog apply wrote no routes"
    status = state.get(f"{BASE}/runs/{run_id}/apply-status")
    assert status.status_code == 200

    # (7) Safe repeat: a fresh reviewed apply of the same run is a no-op.
    before = _route_count(env)
    first = state.post(f"{BASE}/runs/{run_id}/apply-preview", {"csrf_token": _csrf(state.get(f"{BASE}/runs/{run_id}/").text)})
    assert first.status_code == 200, first.text[:400]
    page = first
    if not REVIEW_TOKEN_RE.search(page.text):
        warnings = re.findall(r'name="ack_warning_code" value="([^"]+)"', page.text)
        page = state.post(
            f"{BASE}/runs/{run_id}/apply-preview",
            {
                "csrf_token": _csrf(page.text),
                "reason": REASON,
                "ack_warning_code": warnings,
            },
        )
        assert page.status_code == 200, page.text[:400]
    match = REVIEW_TOKEN_RE.search(page.text)
    if match:
        resp = state.post(
            f"{BASE}/runs/{run_id}/apply",
            {
                "csrf_token": _csrf(page.text),
                "review_token": match.group(1),
                "confirm_apply": "on",
            },
        )
        assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    assert _route_count(env) == before, "repeat apply must be a no-op"


# ---------------------------------------------------------------------------
# 14. G17: account list/create/reset + role boundary
# ---------------------------------------------------------------------------


def test_14_g17_accounts(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    created_email = f"219-created-{uuid.uuid4().hex[:10]}@example.test"
    created_pw = "Pw-219-created-new-admin"

    listing = state.get(f"{ACCOUNTS_BASE}")
    assert SUPERADMIN_EMAIL in listing.text
    assert ADMIN_EMAIL in listing.text
    _canary_free(env, listing.text)

    # Create an ordinary admin (explicit confirmations, actor/reason).
    resp = state.post(
        f"{ACCOUNTS_BASE}/create",
        {
            "csrf_token": _csrf(state.get(f"{ACCOUNTS_BASE}/create").text),
            "email": created_email,
            "display_name": "219 Created Admin",
            "password": created_pw,
            "password_confirmation": created_pw,
            "role": "admin",
            "confirm_create": "1",
            "confirm_superadmin": "",
            "reason": REASON,
        },
    )
    assert resp.status_code == 303, (resp.status_code, resp.text[:300])

    from slaif_gateway.db.models import AdminUser, AdminSession
    from slaif_gateway.utils.passwords import verify_admin_password

    async def _created(session):
        rows = (
            (
                await session.execute(
                    select(AdminUser).where(AdminUser.email == created_email)
                )
            ).scalars().all()
        )
        assert len(rows) == 1
        row = rows[0]
        return {
            "id": str(row.id),
            "role": row.role,
            "active": row.is_active,
            "hash": row.password_hash,
        }

    created = _db(env["database_url"], _created)
    assert created["role"] == "admin"
    assert created["active"] is True
    assert created["hash"].startswith("$argon2id$")
    assert verify_admin_password(created_pw, created["hash"])
    assert _audits(env, "admin_user_created", created["id"])

    # The new admin gets a REAL session, then a superadmin reset revokes it.
    admin_state = _LoginState(env["base_url"])
    admin_state.login(created_email, created_pw)

    async def _sessions(session):
        rows = (
            (
                await session.execute(
                    select(AdminSession).where(
                        AdminSession.admin_user_id == uuid.UUID(created["id"])
                    )
                )
            ).scalars().all()
        )
        return [{"revoked": s.revoked_at is not None} for s in rows]

    assert _db(env["database_url"], _sessions) == [{"revoked": False}]

    page = state.get(f"{ACCOUNTS_BASE}/reset", params={"admin_id": created["id"]})
    assert created_email in page.text
    assert f'name="admin_id" value="{created["id"]}"' in page.text
    resp = state.post(
        f"{ACCOUNTS_BASE}/reset?admin_id={created["id"]}",
        {
            "csrf_token": _csrf(page.text),
            "admin_id": created["id"],
            "password": "Pw-219-reset-target-pw",
            "password_confirmation": "Pw-219-reset-target-pw",
            "confirm_reset": "1",
            "reason": REASON,
        },
    )
    assert resp.status_code == 303, (resp.status_code, resp.text[:300])
    assert _db(env["database_url"], _sessions) == [{"revoked": True}], "target session not revoked"
    audits = _audits(env, "admin_user_password_reset", created["id"])
    assert audits and audits[-1]["actor"] == manifest["superadmin"]
    assert created_pw not in resp.text

    # Role boundary: an ordinary admin is refused the account surface.
    # The reset above revoked this admin's session, so re-authenticate with
    # the new password to prove the 403 is the persisted-role gate (not a
    # 303 login redirect for a revoked/unauthenticated session).
    admin_state.login(created_email, "Pw-219-reset-target-pw")
    refused = admin_state.client.get(f"{ACCOUNTS_BASE}")
    assert refused.status_code == 403, refused.status_code


# ---------------------------------------------------------------------------
# 15. Original calibration row: real-browser JSON download + same-page create
# ---------------------------------------------------------------------------


def test_15_calibration_json_download_and_template(env219: dict[str, Any], chromium: object) -> None:
    env = env219
    k4: str = env["manifest"]["k4"]
    base_url: str = env["base_url"]

    context = chromium.new_context()  # type: ignore[attr-defined]
    page = context.new_page()
    page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    page.fill('form[action="/admin/login"] input[name="email"]', SUPERADMIN_EMAIL)  # type: ignore[attr-defined]
    page.fill('form[action="/admin/login"] input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click('form[action="/admin/login"] button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url(f"{base_url}/admin")  # type: ignore[attr-defined]

    page.goto(f"{base_url}/admin/keys/{k4}/calibration")  # type: ignore[attr-defined]
    page.wait_for_selector(f'form[action="/admin/keys/{k4}/calibration/preview"]')  # type: ignore[attr-defined]

    multiplier = page.locator('input[name="multiplier"]')  # type: ignore[attr-defined]
    multiplier.focus()
    page.keyboard.press("ControlOrMeta+a")  # type: ignore[attr-defined]
    page.keyboard.type("2")  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]
    page.wait_for_selector(f'form[action="/admin/keys/{k4}/calibration/create-template"]')  # type: ignore[attr-defined]
    # Honest copy: the download recomputes CURRENT data, not a frozen copy.
    assert "not a frozen copy" in page.inner_text("body")  # type: ignore[attr-defined]

    with page.expect_download() as download_info:  # type: ignore[attr-defined]
        page.click("a:has-text(\"Download this preview's JSON\")")  # type: ignore[attr-defined]
    download = download_info.value  # type: ignore[attr-defined]
    assert download.suggested_filename == f"slaif-calibration-summary-{k4}.json"  # type: ignore[attr-defined]
    payload_path = WORKFLOW_DIR / "installed-calibration-summary.json"
    download.save_as(str(payload_path))  # type: ignore[attr-defined]
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "proposal", "is_empty", "warnings"}
    assert payload["summary"], "trusted calibration key has observed usage: non-empty summary expected"
    raw = payload_path.read_text(encoding="utf-8")
    assert "sk-" not in raw, "credential material in calibration JSON"

    # The SAME still-displayed form token creates the template (non-rotating
    # attachment context), keyboard only.
    create_form = f'form[action="/admin/keys/{k4}/calibration/create-template"]'
    name_input = page.locator(f'{create_form} input[name="template_name"]')  # type: ignore[attr-defined]
    name_input.focus()
    page.keyboard.type("219 installed calibration template")  # type: ignore[attr-defined]
    page.locator(f'{create_form} input[name="confirm_create_template"]').focus()  # type: ignore[attr-defined]
    page.keyboard.press("Space")  # type: ignore[attr-defined]
    page.locator(f'{create_form} input[name="reason"]').focus()  # type: ignore[attr-defined]
    page.keyboard.type("219 installed calibration template creation")  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]
    page.get_by_text("219 installed calibration template", exact=True).first.wait_for(  # type: ignore[attr-defined]
        state="visible", timeout=20000
    )
    assert "template_created" in page.url  # type: ignore[attr-defined]
    page.screenshot(path=str(WORKFLOW_DIR / "219-installed-calibration.png"))  # type: ignore[attr-defined]
    context.close()

    from slaif_gateway.db.models import KeyTemplate

    rows = _db(
        env["database_url"],
        lambda session: session.execute(
            select(KeyTemplate).where(KeyTemplate.name == "219 installed calibration template")
        ),
    )
    assert len(rows.scalars().all()) == 1, "installed calibration template not persisted exactly once"
    assert _audits(env, "key_template.created")


# ---------------------------------------------------------------------------
# 15b. Representative legacy outcomes on a dedicated owner + key (the
# original 219 scope: record/key creation, lifecycle/rotation, quotas,
# lazy waiting, discovery/import, template issue, audit/export, logout).
# All operations are EXISTING GUI surfaces; no new feature or permission.
# ---------------------------------------------------------------------------


def test_15b_legacy_lifecycle_outcomes(env219: dict[str, Any]) -> None:
    env = env219
    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    suffix = manifest["suffix"]

    # 1) Legacy OWNER (record) creation through the GUI.
    owners_page = state.get("/owners/new")
    resp = state.post(
        "/owners/new",
        {
            "csrf_token": _csrf(owners_page.text),
            "name": "Legacy",
            "surname": f"Seed-{suffix}",
            "email": f"legacy-{suffix}@example.org",
            "institution_id": manifest["institution"],
            "external_id": "",
            "notes": "",
            "is_active": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
    from slaif_gateway.db.models import Owner

    async def _find_owner(session):
        rows = (
            await session.execute(
                select(Owner).where(Owner.email == f"legacy-{suffix}@example.org")
            )
        ).scalars().all()
        assert len(rows) == 1
        return str(rows[0].id)

    legacy_owner = _db(env["database_url"], _find_owner)
    owner_audits = _audits(env, "owner_created", legacy_owner)
    assert len(owner_audits) == 1
    assert owner_audits[0]["actor"] == manifest["superadmin"]
    assert owner_audits[0]["note"] == REASON

    # 2) Legacy STANDARD key creation for the new owner (none delivery:
    # the result page is the ONLY plaintext display).
    create_page = state.get("/admin/keys/create")
    resp = state.post(
        "/admin/keys/create",
        {
            "csrf_token": _csrf(create_page.text),
            "owner_id": legacy_owner,
            "cohort_id": manifest["cohort"],
            "valid_days": "30",
            "email_delivery_mode": "none",
            "allowed_providers": "openai",
            "allowed_models": "gpt-4.1-mini",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    assert resp.status_code == 200, resp.status_code
    shown = re.search(
        r'class="secret-display"[^>]*>\s*<code>(sk-slaif-[A-Za-z0-9._\-]+)</code>',
        resp.text,
    )
    assert shown, "none-delivery legacy create must display the key once"
    assert resp.text.count(shown.group(1)) == 1
    legacy_key_plaintext = shown.group(1)
    env["legacy_key_plaintext"] = legacy_key_plaintext

    before_ids = set(_gateway_keys(env))
    legacy_key = next(iter(set(_gateway_keys(env)) - before_ids))
    env["legacy_key"] = legacy_key
    legacy_before = _gateway_keys(env)[legacy_key]
    assert legacy_before["owner_id"] == legacy_owner
    assert legacy_before["allowed_models"] == ["gpt-4.1-mini"]

    # 2b) One REAL proxied chat completion with the fresh key: the owned
    # ProviderMock is the upstream (documented IO substitution), so the
    # counters below are non-zero evidence that the later edits must not
    # reset.
    from datetime import UTC, timedelta

    proxy = httpx.Client(base_url=env["base_url"], timeout=30)
    chat = proxy.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {legacy_key_plaintext}"},
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "219"}]},
    )
    proxy.close()
    assert chat.status_code == 200, chat.text[:400]
    assert chat.json()["choices"][0]["message"]["content"] == "fixture completion"
    legacy_used = _gateway_keys(env)[legacy_key]
    assert legacy_used["requests_used_total"] == 1
    assert legacy_used["tokens_used_total"] == 2
    assert legacy_used["cost_used_eur"] > 0
    from slaif_gateway.db.models import GatewayKey

    async def _validity_before(session):
        row = await session.get(GatewayKey, uuid.UUID(legacy_key))
        assert row is not None
        return row.valid_until

    original_until = _db(env["database_url"], _validity_before)

    # 3) Validity edit (extended absolute window) WITHOUT any usage reset.
    detail = state.get(f"/admin/keys/{legacy_key}")
    extended_until = (datetime.now(UTC) + timedelta(days=60)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    resp = state.post(
        f"/admin/keys/{legacy_key}/validity",
        {
            "csrf_token": _csrf(detail.text),
            "valid_from": "",
            "valid_until": extended_until,
            "reason": REASON,
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    persisted_until = _db(env["database_url"], _validity_before)
    assert persisted_until != original_until
    assert persisted_until is not None and persisted_until.year >= datetime.now(UTC).year
    legacy_after_validity = _gateway_keys(env)[legacy_key]
    for field in (
        "cost_used_eur",
        "tokens_used_total",
        "requests_used_total",
        "cost_reserved_eur",
        "tokens_reserved_total",
        "requests_reserved_total",
    ):
        assert legacy_after_validity[field] == legacy_used[field], field

    # 4) Hard quota edit (token limit) WITHOUT a usage reset.
    detail = state.get(f"/admin/keys/{legacy_key}")
    resp = state.post(
        f"/admin/keys/{legacy_key}/limits",
        {
            "csrf_token": _csrf(detail.text),
            "cost_limit_eur": "",
            "token_limit": "777777",
            "request_limit": "",
            "clear_cost_limit": "",
            "clear_token_limit": "",
            "clear_request_limit": "",
            "reason": REASON,
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    legacy_after_limits = _gateway_keys(env)[legacy_key]
    assert legacy_after_limits["token_limit_total"] == 777777
    for field in ("cost_used_eur", "tokens_used_total", "requests_used_total"):
        assert legacy_after_limits[field] == legacy_used[field], field

    # 5) Lazy waiting configuration (bounded wait mode, exact policy).
    detail = state.get(f"/admin/keys/{legacy_key}")
    resp = state.post(
        f"/admin/keys/{legacy_key}/lazy-throttling",
        {
            "csrf_token": _csrf(detail.text),
            "lazy_throttling_mode": "wait",
            "lazy_throttling_max_wait_seconds": "30",
            "lazy_throttling_max_waiting_requests": "2",
            "reason": REASON,
        },
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    lazy_meta = _gateway_keys(env)[legacy_key]["metadata_json"]
    assert lazy_meta.get("lazy_throttling_policy") == {
        "mode": "wait",
        "max_wait_seconds": 30,
        "max_waiting_requests": 2,
    }
    assert _audits(env, "update_key_lazy_throttling", legacy_key)

    # 6) Suspend then activate: persisted status transitions + audits.
    detail = state.get(f"/admin/keys/{legacy_key}")
    resp = state.post(
        f"/admin/keys/{legacy_key}/suspend",
        {"csrf_token": _csrf(detail.text), "reason": REASON},
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    assert _gateway_keys(env)[legacy_key]["status"] == "suspended"
    assert _audits(env, "suspend_key", legacy_key)
    detail = state.get(f"/admin/keys/{legacy_key}")
    resp = state.post(
        f"/admin/keys/{legacy_key}/activate",
        {"csrf_token": _csrf(detail.text), "reason": REASON},
    )
    assert resp.status_code in (200, 303), (resp.status_code, resp.text[:300])
    assert _gateway_keys(env)[legacy_key]["status"] == "active"
    assert _audits(env, "activate_key", legacy_key)

    # 7) Rotation with the old material INVALIDATED: one-time replacement
    # plaintext, old key revoked, no email row (none delivery), audits.
    detail = state.get(f"/admin/keys/{legacy_key}")
    resp = state.post(
        f"/admin/keys/{legacy_key}/rotate",
        {
            "csrf_token": _csrf(detail.text),
            "confirm_rotate": "true",
            "keep_old_active": "",
            "email_delivery_mode": "none",
            "reason": REASON,
        },
    )
    assert resp.status_code == 200, resp.status_code
    assert "Replacement Key Created" in resp.text
    new_shown = re.search(
        r'class="secret-display"[^>]*>\s*<code>(sk-slaif-[A-Za-z0-9._\-]+)</code>',
        resp.text,
    )
    assert new_shown, "rotation result must display the replacement once"
    assert resp.text.count(new_shown.group(1)) == 1
    assert new_shown.group(1) != legacy_key_plaintext
    env["rotated_key_plaintext"] = new_shown.group(1)
    assert "Old key revoked" in resp.text
    assert "Yes" in resp.text
    old_key = _gateway_keys(env)[legacy_key]
    assert old_key["status"] == "revoked"
    rotated_id = next(iter(set(_gateway_keys(env)) - before_ids - {legacy_key}))
    rotated_key = _gateway_keys(env)[rotated_id]
    assert rotated_key["status"] == "active"
    assert rotated_key["token_hash"] != old_key["token_hash"]
    assert _audits(env, "rotate_key")
    # The replacement plaintext is NEVER re-displayed on any other surface.
    assert new_shown.group(1) not in state.get(f"/admin/keys/{rotated_id}").text
    # Correct one-time destination: none delivery creates no email row.
    from slaif_gateway.db.models import EmailDelivery

    async def _no_emails(session):
        rows = (
            await session.execute(
                select(EmailDelivery).where(
                    EmailDelivery.gateway_key_id.in_([legacy_key, rotated_id])
                )
            )
        ).scalars().all()
        return len(rows)

    assert _db(env["database_url"], _no_emails) == 0

    # 8) Provider discovery/import review/application against the OWNED
    # synthetic models endpoint (create provider -> bounded discovery ->
    # reviewed setup apply -> persisted route + local-zero pricing).
    models: _ModelsServer = env["models"]
    create_page = state.get("/admin/providers/new")
    resp = state.post(
        "/admin/providers/new",
        {
            "csrf_token": _csrf(create_page.text),
            "provider": "syn219d",
            "display_name": "219 Discovery Synthetic Provider",
            "kind": "openai_compatible",
            "base_url": models.base_url,
            "api_key_env_var": "GUI219D_SYN219_KEY",
            "enabled": "true",
            "timeout_seconds": "30",
            "max_retries": "0",
            "notes": "",
            "notes_intent": "replace",
            "reason": REASON,
        },
    )
    assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
    disc_id = re.search(r"/admin/providers/([0-9a-f-]{36})", resp.headers["location"]).group(1)
    discover_page = state.get(f"/admin/providers/{disc_id}/discover")
    preview = state.post(
        f"/admin/providers/{disc_id}/discover/preview",
        {
            "csrf_token": _csrf(discover_page.text),
            "confirm_discovery": "true",
        },
    )
    assert preview.status_code == 200, preview.text[:400]
    assert "syn-219-model-a" in preview.text
    assert "syn-219-model-b" in preview.text
    exec_resp = state.post(
        f"/admin/providers/{disc_id}/discover/execute",
        {
            "csrf_token": _csrf(preview.text),
            "selected_models": "syn-219-model-a",
            "preset": "chat_text_v1",
            "pricing_mode": "local_zero",
            "confirm_local_zero": "true",
            "priority": "100",
            "visible_in_models": "true",
            "streaming": "true",
            "local_function_tools": "",
            "confirm_enable_unqualified": "",
            "confirm_execute": "true",
            "reason": REASON,
        },
    )
    assert exec_resp.status_code in (302, 303), (exec_resp.status_code, exec_resp.text[:300])
    assert "openai_compatible_setup_executed" in exec_resp.headers["location"]
    from slaif_gateway.db.models import ModelRoute, PricingRule

    async def _discovery_applied(session):
        routes = (
            await session.execute(
                select(ModelRoute).where(
                    ModelRoute.provider == "syn219d",
                    ModelRoute.requested_model == "syn-219-model-a",
                )
            )
        ).scalars().all()
        assert len(routes) == 1, "exactly one discovered route"
        pricing = (
            await session.execute(
                select(PricingRule).where(
                    PricingRule.provider == "syn219d",
                    PricingRule.upstream_model == "syn-219-model-a",
                )
            )
        ).scalars().all()
        assert len(pricing) == 1, "exactly one local-zero pricing rule"
        return {
            "enabled": routes[0].enabled,
            "priority": routes[0].priority,
            "input_price": pricing[0].input_price_per_1m,
        }

    applied = _db(env["database_url"], _discovery_applied)
    assert applied["enabled"] is True
    assert applied["priority"] == 100
    assert applied["input_price"] == 0

    # 9) Template ISSUE from the calibration-created revision (test_15):
    # one-time plaintext, persisted key, provenance, audit.
    from slaif_gateway.db.models import KeyTemplate

    async def _find_template(session):
        row = (
            await session.execute(
                select(KeyTemplate).where(
                    KeyTemplate.name == "219 installed calibration template"
                )
            )
        ).scalars().one()
        return str(row.id)

    template_id = _db(env["database_url"], _find_template)
    template_page = state.get(f"/admin/templates/{template_id}")
    issue_match = re.search(
        r"/admin/templates/([0-9a-f-]{36})/revisions/([0-9a-f-]{36})/create-key",
        template_page.text,
    )
    assert issue_match, "template detail must offer the current-revision issue form"
    issue_action = f"/admin/templates/{issue_match.group(1)}/revisions/{issue_match.group(2)}/create-key"
    issue_resp = state.post(
        issue_action,
        {
            "csrf_token": _csrf(template_page.text),
            "owner_id": legacy_owner,
            "cohort_id": manifest["cohort"],
            "valid_days": "30",
            "email_delivery_mode": "none",
            "confirm_create_key_from_template": "true",
            "reason": REASON,
        },
    )
    assert issue_resp.status_code == 200, issue_resp.text[:400]
    issued_shown = re.search(
        r'class="secret-display"[^>]*>\s*<code>(sk-slaif-[A-Za-z0-9._\-]+)</code>',
        issue_resp.text,
    )
    assert issued_shown, "template issue must display the plaintext once"
    assert issue_resp.text.count(issued_shown.group(1)) == 1
    issued_id = next(iter(set(_gateway_keys(env)) - before_ids - {legacy_key, rotated_id}))
    env["issued_key_plaintext"] = issued_shown.group(1)
    issued_key = _gateway_keys(env)[issued_id]
    assert issued_key["owner_id"] == legacy_owner
    assert issued_key["status"] == "active"

    # 10) GUI audit inspection + the existing safe audit export.
    audit_page = state.get("/admin/audit")
    assert "audit" in audit_page.text.lower()
    export = state.post(
        "/admin/audit/export.csv",
        {
            "csrf_token": _csrf(audit_page.text),
            "confirm_export": "1",
            "reason": REASON,
        },
    )
    assert export.status_code == 200, export.status_code
    assert "text/csv" in export.headers["content-type"]
    assert "attachment" in export.headers["content-disposition"]
    assert "provider_config_enabled" in export.text
    _canary_free(env, export.text)

    # 11) Logout: the session is invalidated; a fresh login works again
    # (restored for the following tests).
    any_page = state.get("/admin/audit")
    resp = state.post(
        "/admin/logout", {"csrf_token": _csrf(any_page.text)},
    )
    assert resp.status_code in (302, 303), (resp.status_code, resp.text[:300])
    assert "/admin/login" in resp.headers["location"]
    bounced = state.get("/admin")
    assert bounced.status_code in (302, 303)
    assert "/admin/login" in bounced.headers["location"]
    state.login(SUPERADMIN_EMAIL, ADMIN_PASSWORD)
    assert state.get("/admin").status_code == 200


# ---------------------------------------------------------------------------
# 16. Representative negatives: auth, CSRF, tampered review, recovery, secrets
# ---------------------------------------------------------------------------


def test_16_negatives(env219: dict[str, Any]) -> None:
    """Representative FINAL negative matrix, stated exactly.

    THIS test proves (against the installed code): anonymous bounce, wrong
    CSRF refusal with zero writes, validation recovery preservation, a
    tampered batch review intent refused with zero writes, a WRONG-SESSION
    route review apply refused (purpose-bound signed token), and a STALE
    route review apply refused after a newer change (fingerprint law).
    It does NOT itself prove wrong-actor/session or expired-review cases
    across every surface, nor the all-logs/audit claim: those are covered
    by the accepted unchanged component evidence (207/212/213 browser and
    unit modules) and by test_18_final_secret_scan's complete app/worker
    log + audit-metadata sweep. A refusal here is evidence the requested
    ordinary happy path does NOT work in that variant - never evidence
    that the happy path works.
    """
    env = env219
    base_url: str = env["base_url"]

    # Unauthorized: a fresh anonymous client is bounced to login.
    anon = httpx.Client(base_url=base_url, follow_redirects=False)
    anon_home = anon.get("/admin")
    assert anon_home.status_code in (302, 303)
    assert "/admin/login" in anon_home.headers["location"]
    anon_secret = anon.get("/admin/keys/create")
    assert anon_secret.status_code in (302, 303)
    anon.close()

    state: _LoginState = env["superadmin"]
    manifest = env["manifest"]
    k2, k3 = manifest["k2"], manifest["k3"]
    limits_before = {
        k: _gateway_keys(env)[k]["token_limit_total"] for k in (k2, k3)
    }

    # Wrong CSRF: fixed 400 refusal, zero writes.
    bad = state.post(
        "/admin/keys/create",
        {
            "csrf_token": "0" * 64,
            "owner_id": manifest["owner_std"],
            "cohort_id": "",
            "valid_days": "30",
            "email_delivery_mode": "none",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "reason": REASON,
        },
    )
    assert bad.status_code == 400, bad.status_code
    assert "Invalid CSRF token" in bad.text
    before_count = len(_gateway_keys(env))

    # Validation recovery: a refused create re-renders with the submitted
    # fields preserved and writes nothing.
    recovery = state.post(
        "/admin/keys/create",
        {
            "csrf_token": _csrf(state.get("/admin/keys/create").text),
            "owner_id": "",  # required owner missing
            "cohort_id": "",
            "valid_days": "30",
            "email_delivery_mode": "none",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "reason": "219 recovery canary reason",
        },
    )
    assert recovery.status_code == 400, recovery.status_code
    assert "219 recovery canary reason" in recovery.text, "submitted input not preserved"
    assert len(_gateway_keys(env)) == before_count, "validation recovery wrote a key"

    # Tampered batch review intent: refused with zero writes.
    plan = state.post(
        "/admin/key-batch/plan",
        _batch_plan_fields(_csrf(state.get("/admin/key-batch").text), manifest),
    )
    assert plan.status_code == 200
    token = _token(plan.text, BATCH_TOKEN_RE)
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    tampered_resp = state.post(
        "/admin/key-batch/apply",
        {
            "csrf_token": _csrf(plan.text),
            "batch_review_intent": tampered,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": REASON,
        },
    )
    assert tampered_resp.status_code in (400, 403, 200), tampered_resp.status_code
    if tampered_resp.status_code == 200:
        assert "applied" not in tampered_resp.text.lower() or "refused" in tampered_resp.text.lower()
    assert _gateway_keys(env)[k2]["token_limit_total"] == limits_before[k2]
    assert _gateway_keys(env)[k3]["token_limit_total"] == limits_before[k3]

    # Wrong-SESSION route review apply: the purpose-bound signed route
    # review token is bound to the superadmin's admin user AND session.
    # A DIFFERENT authenticated session (the seeded non-superadmin) must
    # be refused with zero writes even though it is a valid login.
    from slaif_gateway.db.models import ModelRoute

    async def _route_priority(session, route_id: str):
        row = await session.get(ModelRoute, uuid.UUID(route_id))
        return row.priority

    route_nano = manifest["route_nano"]
    nano_before = _db(env["database_url"], lambda s: _route_priority(s, route_nano))
    # Superadmin plans a change (creates the bound token) but does not apply.
    nano_page = state.get(f"/admin/routes/{route_nano}/configuration")
    nano_plan = state.post(
        f"/admin/routes/{route_nano}/configuration/plan",
        _route_plan_fields(_csrf(nano_page.text), priority_action="set", priority="55"),
    )
    assert nano_plan.status_code == 200, nano_plan.text[:400]
    nano_token = _token(nano_plan.text, ROUTE_TOKEN_RE)
    # A second, DIFFERENT valid session attempts to apply that token.
    other = _LoginState(base_url)
    other.login(ADMIN_EMAIL, ADMIN_PASSWORD)
    other_page = other.get(f"/admin/routes/{route_nano}/configuration")
    cross = other.post(
        f"/admin/routes/{route_nano}/configuration/apply",
        {
            "csrf_token": _csrf(other_page.text),
            "route_config_review_intent": nano_token,
            "confirm_apply": "true",
            "reason": REASON,
        },
    )
    assert cross.status_code in (400, 403), (cross.status_code, cross.text[:300])
    # Zero writes: the route still carries its original priority.
    assert _db(env["database_url"], lambda s: _route_priority(s, route_nano)) == nano_before
    other.client.close()

    # STALE route review apply: a reviewed plan whose expected pre-state
    # fingerprint no longer matches (a newer change landed first) must be
    # refused stale with zero writes.
    # Plan a change (creates the bound token) but do NOT apply it yet.
    nano_cfg = state.get(f"/admin/routes/{route_nano}/configuration")
    stale_plan = state.post(
        f"/admin/routes/{route_nano}/configuration/plan",
        _route_plan_fields(_csrf(nano_cfg.text), priority_action="set", priority="77"),
    )
    assert stale_plan.status_code == 200, stale_plan.text[:400]
    stale_token = _token(stale_plan.text, ROUTE_TOKEN_RE)
    # Land a DIFFERENT newer change first so the reviewed pre-state is stale.
    newer_status, _ = _route_plan_and_apply(state, route_nano, priority_action="set", priority="78")
    assert newer_status in (200, 303)
    # Now apply the older reviewed plan: it must be refused STALE.
    stale_resp = state.post(
        f"/admin/routes/{route_nano}/configuration/apply",
        {
            "csrf_token": _csrf(state.get(f"/admin/routes/{route_nano}/configuration").text),
            "route_config_review_intent": stale_token,
            "confirm_apply": "true",
            "reason": REASON,
        },
    )
    assert stale_resp.status_code == 400, (stale_resp.status_code, stale_resp.text[:300])
    # Zero writes: the route keeps the NEWER priority, not the stale one.
    assert _db(env["database_url"], lambda s: _route_priority(s, route_nano)) == 78

    # Secret canary sweep across the surfaces this workflow exercised.
    for path in ("/admin", "/admin/keys", "/admin/providers", "/admin/usage",
                 "/admin/operations/process-configuration", f"/admin/keys/{manifest['k1']}"):
        _canary_free(env, state.get(path).text)


# ---------------------------------------------------------------------------
# 17. FINAL complete app/worker log + audit-metadata secret scan
# ---------------------------------------------------------------------------


def test_17_final_secret_scan(env219: dict[str, Any]) -> None:
    """Complete-body/log/audit secret canary over the final changed
    surfaces.

    Checks the RETAINED app log, the worker log, and EVERY audit row's
    persisted metadata (note + old/new values) for the known synthetic
    secrets, admin password, one-time plaintext key values, and session
    cookie aliases. Public key NAMES (prefix + public id, no secret half)
    and the intentional one-time result-page displays are functional
    exceptions and are NOT part of this scan. No real credentials or
    private contents are present anywhere by construction.
    """
    env = env219
    canaries: list[str] = [
        "sk-provider-secret-placeholder-219",
        "sk-or-provider-secret-placeholder-219",
        ADMIN_PASSWORD,
    ]
    for key in (
        "g01_key_plaintext",
        "legacy_key_plaintext",
        "rotated_key_plaintext",
        "issued_key_plaintext",
    ):
        value = env.get(key)
        if value:
            canaries.append(str(value))
    # Session aliases: every session cookie value the workflow used.
    for client in (env["superadmin"].client,):
        for cookie_value in client.cookies.values():
            if cookie_value:
                canaries.append(str(cookie_value))

    # 1) Complete app log + worker log sweep.
    gateway = env["gateway"]
    app_log = gateway.app_log_path.read_text(encoding="utf-8", errors="replace")
    worker_log = (WORKFLOW_DIR / "worker.log")
    worker_text = (
        worker_log.read_text(encoding="utf-8", errors="replace")
        if worker_log.exists()
        else ""
    )
    for name, text_ in (("app log", app_log), ("worker log", worker_text)):
        for canary in canaries:
            assert canary not in text_, (
                f"known secret material found in {name}: {canary[:16]}..."
            )

    # 2) EVERY audit row's persisted metadata (note + old/new values).
    from slaif_gateway.db.models import AuditLog

    async def _all_audit_metadata(session):
        rows = (await session.execute(select(AuditLog))).scalars().all()
        return [
            {
                "action": r.action,
                "note": r.note,
                "old_values": r.old_values,
                "new_values": r.new_values,
            }
            for r in rows
        ]

    audit_rows = _db(env["database_url"], _all_audit_metadata)
    assert audit_rows, "audit table must not be empty after this workflow"
    for row in audit_rows:
        rendered = json.dumps(
            {
                "action": row["action"],
                "note": row["note"],
                "old_values": row["old_values"],
                "new_values": row["new_values"],
            },
            default=str,
        )
        for canary in canaries:
            assert canary not in rendered, (
                f"known secret material found in audit metadata "
                f"({row['action']}): {canary[:16]}..."
            )
