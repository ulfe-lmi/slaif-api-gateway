"""217-a G15 GUI catalog refresh: owned PG/Redis real-app HTTP qualification.

Real-app (FastAPI TestClient, real routes, real CSRF/session auth), real
owned PostgreSQL (module-owned Docker container, sole PG owner), real
owned Redis broker - the full GUI workflow:

- setup READY state and ordinary app usability;
- QUEUED collect: API -> owned Redis broker -> disposable application
  Celery worker (the root-authorized real-worker proof) -> sealed run in
  operator custody, then run detail / verify / artifact through HTTP, with
  CANONICAL rendering asserted (run state, first-install baseline honesty,
  configured-not-SQL-observed target);
- QUEUED supplied-bundle review from a DELIBERATELY CONSTRUCTED independent
  RefreshBundle input (its own explicit test run_id; a fresh semantic
  digest, no reuse of the collect seal); same-ID re-review of the collect
  bundle is refused NEW-ONLY (run_conflict), original bytes/inode unchanged;
- the two-step reviewed superadmin apply of the COLLECT run (normal
  collect -> inspect -> verify -> reviewed apply flow): sealed intent ->
  signed choices -> explicit confirm mutating the REAL owned database,
  proving the final apply uses the SIGNED reason (an unsigned form reason
  override is ignored) and a committed repeat returns already_committed with
  no duplicate audit row;
- the reviewed-apply gate matrix over REAL sessions/CSRF: missing confirm,
  tampered token, wrong actor, expired token, run-binding mismatch, and
  download/status -> same-page apply (non-rotating read context);
- the superadmin role boundary (ordinary admin refused before effects);
- QUEUED export-baseline exporting the REAL owned catalog;
- QUEUED provider-catalog proposal through the DEFAULT registry/bridge seam
  (only the proposal transport is a synthetic MockTransport) -> generated
  TSV -> existing import-preview bridge (no import execution);
- secret-persistence canaries: request-owned authentication values embedded
  in collect/review/proposal inputs are refused before any job/custody write;
- dashboard-off and feature-off fail-closed guards with a valid
  authenticated session.

Labeled seams (the ONLY synthetic parts, identical to the focused unit
suite): the disposable worker's collect client is a synthetic
OFFICIAL-source ``World()`` MockTransport client with a synthetic public
resolver answer, and every live DNS/socket seam in that worker is a hard
failure. The broker round-trip, task pickup, custody lifecycle, Core
composition, sealing, publication, and every database interaction are
real. No physical upstream network, no ambient PG/Redis, no mocked
broker, no eager execution.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from pathlib import Path
from typing import Any
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    AdminSession,
    AdminUser,
    CatalogRefreshApplication,
    ModelRoute,
)
from slaif_gateway.main import create_app
import slaif_gateway.api.admin_catalog_refresh as router_mod
from slaif_gateway.services import admin_catalog_refresh as custody
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
# Reuse the qualified owned PostgreSQL/Redis fixtures (never ambient).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
    owned_redis_url as _owned_redis_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture
owned_redis_url = _owned_redis_url_fixture

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_DRIVER = _REPO_ROOT / "tests" / "integration" / "_catalog_refresh_worker_driver.py"

ADMIN_PASSWORD = "correct horse battery staple"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
REVIEW_TOKEN_RE = re.compile(r'name="review_token" value="([^"]+)"')
BASE = "/admin/operations/catalog"
TERMINAL_JOB_STATUSES = frozenset(
    {"ready", "warnings", "blocked", "failed", "canceled", "unavailable", "unconfirmed"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(database_url: str, custody_root: Path, seal_key: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "ADMIN_SESSION_SECRET": "s" * 40,
        "TOKEN_HMAC_SECRET": generate_secret_key(),
        "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
        "TOKEN_HMAC_SECRET_V1": generate_secret_key(),
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ACTIVE_HMAC_KEY_VERSION": "1",
        "ENABLE_ADMIN_DASHBOARD": True,
        "ENABLE_EMAIL_DELIVERY": False,
        "OPENAI_UPSTREAM_API_KEY": "sk-provider-secret-placeholder",
        "OPENROUTER_API_KEY": "sk-or-provider-secret-placeholder",
        "CATALOG_REFRESH_GUI_ENABLED": True,
        "CATALOG_REFRESH_ROOT": str(custody_root),
        "CATALOG_REFRESH_SEAL_KEY": str(seal_key),
        "CATALOG_REFRESH_MAX_TOTAL_BYTES": 1024 * 1024 * 1024,
        "CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS": 300,
    }
    values.update(overrides)
    return Settings(**values)


def _db_worker(database_url: str, coro_factory) -> Any:
    """Run a DB coroutine in a WORKER THREAD (216 pattern): the primary
    TestClient owns a live ASGI loop thread where ``asyncio.run`` would
    raise; a fresh worker thread has no running loop."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    box: dict[str, Any] = {}

    def _worker() -> None:
        async def _run() -> None:
            engine = create_async_engine(database_url, future=True)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    box["value"] = await coro_factory(session)
            finally:
                await engine.dispose()

        try:
            asyncio.run(_run())
        except BaseException as exc:  # re-raised in the main thread
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


async def _seed_admins(database_url: str) -> dict[str, str]:
    from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    out: dict[str, str] = {}
    try:
        async with factory() as session:
            async with session.begin():
                for key, role in (("superadmin", "superadmin"), ("admin", "admin")):
                    email = f"217-{role}-{suffix}@example.test"
                    out[key] = email
                    await AdminUsersRepository(session).create_admin_user(
                        email=email,
                        display_name=f"217 {role} admin",
                        password_hash=hash_admin_password(ADMIN_PASSWORD),
                        role=role,
                        is_active=True,
                    )
    finally:
        await engine.dispose()
    return out


def _login(client: TestClient, *, email: str) -> None:
    response = client.get("/admin/login")
    assert response.status_code == 200
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        "/admin/login",
        data={"csrf_token": csrf, "email": email, "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _page_csrf(client: TestClient, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200
    match = CSRF_RE.search(response.text)
    assert match, f"no CSRF token on {path}"
    return match.group(1)


def _latest_job(settings: Settings, family: str) -> dict[str, Any] | None:
    for row in custody.list_jobs(settings, limit=100):
        if row.get("family") == family:
            return row
    return None


def _wait_job(settings: Settings, family: str, *, timeout: float = 240.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        row = _latest_job(settings, family)
        if row is not None:
            last = row
            if row["status"] in TERMINAL_JOB_STATUSES:
                return row
        time.sleep(1.0)
    raise AssertionError(f"job family {family!r} did not reach a terminal state: {last!r}")


def _wait_new_job(
    settings: Settings,
    family: str,
    known_ids: set[str],
    *,
    timeout: float = 240.0,
) -> dict[str, Any]:
    """Wait for a NEW job (job_id not in ``known_ids``) of ``family`` to reach
    a terminal state. Robust to created_at timestamp ties between same-family
    jobs, where newest-first ordering alone is ambiguous."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        for row in custody.list_jobs(settings, limit=100):
            if row.get("family") != family or row.get("job_id") in known_ids:
                continue
            last = row
            if row["status"] in TERMINAL_JOB_STATUSES:
                return row
        time.sleep(1.0)
    raise AssertionError(
        f"new job family {family!r} did not reach a terminal state: {last!r}"
    )


def _count_apps(database_url: str, run_id: str) -> int:
    """Number of committed catalog-refresh application rows for one run."""

    async def _run(session) -> int:
        return await session.scalar(
            select(func.count(CatalogRefreshApplication.id)).where(
                CatalogRefreshApplication.run_id == run_id
            )
        )

    return _db_worker(database_url, _run)


def _route_count(database_url: str) -> int:
    """Committed route rows for the synthetic official-source catalog."""

    async def _run(session) -> int:
        return await session.scalar(
            select(func.count(ModelRoute.id)).where(
                ModelRoute.requested_model.in_(("gpt-syn-2", "synth/alpha", "synth/beta"))
            )
        )

    return _db_worker(database_url, _run)


def _apply_audit_rows(database_url: str, run_id: str) -> list[tuple[str | None, dict[str, Any]]]:
    """The actual Core ``audit_log`` rows written for committed applies of ONE
    run: [(admin_user_id, new_values)]. A committed repeat writes NO new row."""

    async def _run(session) -> list[tuple[str | None, dict[str, Any]]]:
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "catalog_refresh_applied",
                    AuditLog.entity_type == "catalog_refresh_application",
                )
            )
        ).scalars().all()
        return [
            (None if r.admin_user_id is None else str(r.admin_user_id), dict(r.new_values or {}))
            for r in rows
            if (r.new_values or {}).get("run_id") == run_id
        ]

    return _db_worker(database_url, _run)


def _admin_ids(database_url: str, email: str) -> tuple[str, str]:
    """(admin_user_id, latest non-revoked session id) for a seeded admin."""

    async def _run(session) -> tuple[str, str]:
        user = (
            await session.execute(select(AdminUser).where(AdminUser.email == email))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(AdminSession)
                    .where(
                        AdminSession.admin_user_id == user.id,
                        AdminSession.revoked_at.is_(None),
                    )
                    .order_by(AdminSession.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        assert rows, f"no live session for {email}"
        return str(user.id), str(rows[0].id)

    return _db_worker(database_url, _run)


def _signed_token(
    client: TestClient, run_id: str, warnings: list[str], reason: str
) -> str:
    """Walk the two-step apply-preview over HTTP and return the signed
    (actor/session-bound) review token for one run."""
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    data: dict[str, Any] = {"csrf_token": csrf, "reason": reason}
    for code in warnings:
        data.setdefault("ack_warning_code", []).append(code)
    response = client.post(f"{BASE}/runs/{run_id}/apply-preview", data=data)
    assert response.status_code == 200, response.text
    match = REVIEW_TOKEN_RE.search(response.text)
    assert match, "apply-preview produced no signed review token"
    return match.group(1)


def _spawn_worker(
    *,
    pg_url: str,
    redis_url: str,
    custody_root: Path,
    seal_key: Path,
    log_path: Path,
) -> subprocess.Popen:
    """The disposable application Celery worker (root-authorized for this
    bounded test): a REAL worker process consuming the owned Redis
    broker, with the labeled synthetic official-source collect seams."""
    env = dict(os.environ)
    for var in (
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "CATALOG_REFRESH_ROOT",
        "CATALOG_REFRESH_SEAL_KEY",
        "CATALOG_REFRESH_GUI_ENABLED",
        "CATALOG_REFRESH_MAX_TOTAL_BYTES",
        "CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS",
    ):
        env.pop(var, None)
    env.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": pg_url,
            "REDIS_URL": redis_url,
            "ENABLE_EMAIL_DELIVERY": "false",
            "CATALOG_REFRESH_GUI_ENABLED": "true",
            "CATALOG_REFRESH_ROOT": str(custody_root),
            "CATALOG_REFRESH_SEAL_KEY": str(seal_key),
            "CATALOG_REFRESH_MAX_TOTAL_BYTES": str(1024 * 1024 * 1024),
            "CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS": "300",
            "ADMIN_SESSION_SECRET": "s" * 40,
        }
    )
    log_file = open(log_path, "ab")
    return subprocess.Popen(
        [sys.executable, str(_WORKER_DRIVER)],
        cwd=str(_REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _kill_worker(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env217(owned_pg_url: str, owned_redis_url: str, tmp_path_factory) -> Iterator[dict[str, Any]]:
    monkey = pytest.MonkeyPatch()
    # API-process environment: the LAZY worker import at dispatch time
    # creates the module-level celery app from get_settings(), so the
    # broker must resolve to the owned Redis in THIS process.
    monkey.setenv("APP_ENV", "test")
    monkey.setenv("DATABASE_URL", owned_pg_url)
    monkey.setenv("REDIS_URL", owned_redis_url)
    monkey.setenv("ENABLE_EMAIL_DELIVERY", "false")
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    # The test module's top-level ``create_app`` import already created
    # the module-level celery app (broker resolved from the AMBIENT env
    # at import time). Re-point the SAME singleton's broker to the owned
    # Redis: the router's lazy dispatch import finds this exact app. The
    # effective broker must be EXACTLY the owned Redis before any
    # dispatch, and the result backend must stay unset (optional).
    from slaif_gateway.workers import celery_app as _celery_module

    # Save the parent-process module-level singleton state we are about to
    # override, so teardown restores it (see below): no subsequent
    # integration module may inherit a broker pointing at this fixture's
    # owned (soon removed) Redis container.
    _app = _celery_module.celery_app
    _orig_broker = _app.conf.broker_url
    _orig_backend = _app.conf.result_backend
    # Save the ORIGINAL pool cache slots (never accessed or created just
    # to close them): the app-level ``_pool`` and the AMQP-level
    # ``_producer_pool`` each cache a pool bound to the broker URL that
    # was active when the slot was populated, so restoring
    # ``conf.broker_url`` ALONE would leave them - and any later
    # reconnect through them - pointing at this fixture's owned (soon
    # removed) Redis.
    _orig_pool = _app._pool
    _orig_amqp = _app.__dict__.get("amqp")  # cached_property slot; NOT created
    _orig_producer_pool = (
        _orig_amqp._producer_pool if _orig_amqp is not None else None
    )
    # Isolate this fixture: clear the cache slots so dispatch creates
    # FRESH pools bound to the owned broker below.
    _app._pool = None
    if _orig_amqp is not None:
        _orig_amqp._producer_pool = None
    _app.conf.broker_url = owned_redis_url
    assert _app.conf.broker_url == owned_redis_url
    assert not _app.conf.result_backend

    workdir = tmp_path_factory.mktemp("catalog217")
    custody_root = workdir / "custody"
    custody_root.mkdir(mode=0o700)
    seal_key = workdir / "seal.hex"
    seal_key.write_bytes(b"ef" * 32)
    os.chmod(seal_key, stat.S_IRUSR | stat.S_IWUSR)

    settings = _settings(owned_pg_url, custody_root, seal_key)
    emails = asyncio.run(_seed_admins(owned_pg_url))
    app = create_app(settings)
    worker_proc: subprocess.Popen | None = None
    base: dict[str, Any] = {}
    with TestClient(app) as client:
        _login(client, email=emails["superadmin"])
        worker_proc = _spawn_worker(
            pg_url=owned_pg_url,
            redis_url=owned_redis_url,
            custody_root=custody_root,
            seal_key=seal_key,
            log_path=workdir / "worker.log",
        )
        base.update(
            {
                "client": client,
                "app": app,
                "settings": settings,
                "emails": emails,
                "database_url": owned_pg_url,
                "redis_url": owned_redis_url,
                "custody_root": custody_root,
                "workdir": workdir,
            }
        )
        try:
            yield base
        finally:
            _kill_worker(worker_proc)
            # REQUIRED isolation: close ONLY the pools this fixture created
            # (the CURRENT cache slots - never the original ones), clear
            # the slots, then restore the ORIGINAL cache objects and the
            # singleton config. monkey.undo() restores ENV only, not this
            # singleton - so the restore below must hold, never be
            # swallowed.
            _fixture_pool = _app._pool
            _fixture_amqp = _app.__dict__.get("amqp")
            _fixture_producer_pool = (
                _fixture_amqp._producer_pool if _fixture_amqp is not None else None
            )
            for _pool in (_fixture_pool, _fixture_producer_pool):
                if _pool is not None:
                    try:
                        _pool.force_close_all()
                    except Exception:  # noqa: BLE001 - best-effort owned cleanup
                        pass
            if _orig_amqp is not None:
                _app.__dict__["amqp"] = _orig_amqp
                _orig_amqp._producer_pool = _orig_producer_pool
            else:
                # an AMQP instance created during this fixture is owned
                # by it: discard it (its pools were closed above).
                _app.__dict__.pop("amqp", None)
            _app._pool = _orig_pool
            _app.conf.broker_url = _orig_broker
            _app.conf.result_backend = _orig_backend
            # Assert restoration WITHOUT printing URLs: no owned-broker
            # pool may remain in the singleton cache slots.
            assert _app._pool is _orig_pool
            assert _app.conf.broker_url == _orig_broker
            _amqp_now = _app.__dict__.get("amqp")
            if _orig_amqp is not None:
                assert _amqp_now is _orig_amqp
                assert _amqp_now._producer_pool is _orig_producer_pool
            else:
                assert _amqp_now is None
            get_settings.cache_clear()
            monkey.undo()


# ---------------------------------------------------------------------------
# 1. setup READY + ordinary app usability
# ---------------------------------------------------------------------------


def test_setup_ready_and_ordinary_app_usable(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    response = client.get("/admin/")
    assert response.status_code == 200
    response = client.get(f"{BASE}/")
    assert response.status_code == 200
    assert "ready" in response.text.lower()


# ---------------------------------------------------------------------------
# 2. QUEUED collect: API -> owned Redis -> real application worker
# ---------------------------------------------------------------------------


def test_queued_collect_smoke_real_worker(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    assert _latest_job(settings, "collect") is None
    csrf = _page_csrf(client, f"{BASE}/collect")
    response = client.post(
        f"{BASE}/collect/submit",
            data={
                "csrf_token": csrf,
                "mode": "bootstrap",
                "providers": ["openai", "openrouter"],
            },
    )
    assert response.status_code == 200
    # honest dispatch confirmation: the broker acknowledged; a running
    # worker is proven separately by the sealed run below.
    assert "broker acknowledged" in response.text
    row = _wait_job(settings, "collect")
    assert row["status"] in ("ready", "warnings"), row
    run_id = row["run_id"]
    assert run_id and run_id.startswith("collect-")
    env217["collect_run_id"] = run_id

    # the sealed run is real custody: authenticated capture, exact file set
    capture, handle = custody.load_run_capture(settings, run_id)
    try:
        assert capture.result.valid is True
        assert capture.baseline is None  # bootstrap: no SQL observation
        # ALL sealed warning codes (the exact acknowledgement vocabulary the
        # reviewed apply must select); captured once for the apply test.
        env217["collect_warnings"] = sorted(
            {w.code for w in capture.report.warnings if w.code}
        )
        names = set(capture.content)
        # capture.content is the CONTENT file set; manifest/receipt are
        # authentication files and are never part of the capture content
        assert names == set(custody.CORE_RUN_FILE_SET - {"manifest.json", "receipt.json"})
        bundle_bytes = capture.content["catalog-refresh.json"]
        assert bundle_bytes
    finally:
        handle.close()
    env217["collect_bundle_bytes"] = bundle_bytes

    # Canonical rendering: the sealed run is readable through the SAME
    # authenticated projection (asserted content, not merely HTTP 200) -
    # real state, honest first-install baseline, configured-not-SQL-observed.
    run_rows = {r["run_id"]: r for r in custody.list_runs(settings)}
    assert run_rows[run_id]["state"] in ("READY", "READY_WITH_WARNINGS"), run_rows[run_id]
    detail = client.get(f"{BASE}/runs/{run_id}/")
    assert detail.status_code == 200
    assert "READY" in detail.text
    assert "first_install" in detail.text
    assert "no — no SQL observation (bootstrap/first-install)" in detail.text
    assert "configured (NOT SQL-observed)" in detail.text

    # HTTP surfaces: verify + artifact (same verified bytes)
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    response = client.post(f"{BASE}/runs/{run_id}/verify", data={"csrf_token": csrf})
    assert response.status_code == 200
    response = client.get(f"{BASE}/runs/{run_id}/artifact/catalog-refresh.json")
    assert response.status_code == 200
    assert response.content == bundle_bytes


# ---------------------------------------------------------------------------
# 3. QUEUED supplied-bundle review from the sealed collect bundle
# ---------------------------------------------------------------------------


def test_queued_review_smoke(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    # The standalone review pipeline takes a SUPPLIED RefreshBundle and
    # publishes under THAT bundle's own input run_id (NEW-ONLY). We
    # deliberately construct an independent input fixture from the sealed
    # collect bundle: a fresh explicit test run_id (a NEW semantic digest -
    # no reuse of the collect seal, no production ID rewrite).
    collect_bundle = json.loads(env217["collect_bundle_bytes"])
    independent_run_id = "indep-review-" + uuid.uuid4().hex[:24]
    collect_bundle["run_id"] = independent_run_id
    independent_bytes = (
        json.dumps(collect_bundle, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    known = {
        r["job_id"]
        for r in custody.list_jobs(settings, limit=100)
        if r.get("family") == "review_supplied"
    }
    csrf = _page_csrf(client, f"{BASE}/review")
    response = client.post(
        f"{BASE}/review/submit",
        data={"csrf_token": csrf},
        files={"bundle": ("bundle.json", independent_bytes, "application/json")},
    )
    assert response.status_code == 200
    assert "broker acknowledged" in response.text
    row = _wait_new_job(settings, "review_supplied", known)
    assert row["status"] in ("ready", "warnings"), row
    # the review publishes under the SUPPLIED bundle's own input run_id
    assert row["run_id"] == independent_run_id
    env217["review_run_id"] = independent_run_id
    response = client.get(f"{BASE}/runs/{independent_run_id}/")
    assert response.status_code == 200
    capture, handle = custody.load_run_capture(settings, independent_run_id)
    try:
        assert capture.result.valid is True
        assert capture.bundle.run_id == independent_run_id
    finally:
        handle.close()


def test_review_same_id_refused(env217: dict[str, Any]) -> None:
    """Same-ID re-review of the collect bundle is refused NEW-ONLY: the run
    directory already exists, so the job fails run_conflict and the original
    sealed bytes are left untouched (no re-publication, no overwrite)."""
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    bundle_bytes: bytes = env217["collect_bundle_bytes"]
    original_run_id: str = env217["collect_run_id"]
    # the original run is intact before the refused re-review
    before = custody.read_run_artifact(settings, original_run_id, "catalog-refresh.json")
    assert before == bundle_bytes
    known = {
        r["job_id"]
        for r in custody.list_jobs(settings, limit=100)
        if r.get("family") == "review_supplied"
    }
    csrf = _page_csrf(client, f"{BASE}/review")
    response = client.post(
        f"{BASE}/review/submit",
        data={"csrf_token": csrf},
        files={"bundle": ("bundle.json", bundle_bytes, "application/json")},
    )
    assert response.status_code == 200
    row = _wait_new_job(settings, "review_supplied", known)
    assert row["status"] == "failed", row
    assert row["error_code"] == "run_conflict", row
    # the original sealed run is byte-for-byte unchanged
    after = custody.read_run_artifact(settings, original_run_id, "catalog-refresh.json")
    assert after == bundle_bytes


# ---------------------------------------------------------------------------
# 4. two-step reviewed superadmin apply -> real owned DB
# ---------------------------------------------------------------------------


def test_apply_two_step_superadmin_commits(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    # The NORMAL flow applies the COLLECT run (collect -> inspect -> verify
    # -> reviewed apply), not a re-published review.
    run_id: str = env217["collect_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    SIGNED_REASON = (
        "217-a queued qualification: apply the synthetic official-source catalog"
    )
    UNSIGNED_OVERRIDE = "TAMPERED-UNSIGNED-REASON"

    def _route_count() -> int:
        async def _run(session) -> int:
            return await session.scalar(
                select(func.count(ModelRoute.id)).where(
                    ModelRoute.requested_model.in_(("gpt-syn-2", "synth/alpha", "synth/beta"))
                )
            )

        return _db_worker(env217["database_url"], _run)

    def _application_count() -> int:
        async def _run(session) -> int:
            return await session.scalar(
                select(func.count(CatalogRefreshApplication.id)).where(
                    CatalogRefreshApplication.run_id == run_id
                )
            )

        return _db_worker(env217["database_url"], _run)

    def _committed_reason() -> str | None:
        async def _run(session) -> str | None:
            return await session.scalar(
                select(CatalogRefreshApplication.reason).where(
                    CatalogRefreshApplication.run_id == run_id
                )
            )

        return _db_worker(env217["database_url"], _run)

    def _created_counts() -> dict[str, int] | None:
        # The DURABLE created/superseded counts of the committed application
        # record (the exact values the status page must render, not guesses).
        async def _run(session) -> dict[str, int] | None:
            row = (
                await session.execute(
                    select(CatalogRefreshApplication).where(
                        CatalogRefreshApplication.run_id == run_id
                    )
                )
            ).scalars().first()
            if row is None:
                return None
            return {
                "providers": int(row.created_providers),
                "routes": int(row.created_routes),
                "pricing": int(row.created_pricing),
                "fx": int(row.created_fx),
            }

        return _db_worker(env217["database_url"], _run)

    before = _route_count()
    assert _application_count() == 0
    # Step 1: sealed facts + the exact sealed acknowledgement vocabulary
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    response = client.post(
        f"{BASE}/runs/{run_id}/apply-preview",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 200
    # Step 2: the operator's reason + the EXACT sealed warning codes
    data: dict[str, Any] = {
        "csrf_token": csrf,
        "reason": SIGNED_REASON,
    }
    for code in warnings:
        data.setdefault("ack_warning_code", []).append(code)
    response = client.post(f"{BASE}/runs/{run_id}/apply-preview", data=data)
    assert response.status_code == 200
    token_match = REVIEW_TOKEN_RE.search(response.text)
    assert token_match, "final review page carries no signed review token"
    review_token = token_match.group(1)
    # Final apply: ONLY the signed document + explicit confirmation. An
    # unsigned ``reason`` form field is ALSO submitted and must be IGNORED -
    # the committed audit reason is the SIGNED value, not the override.
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        f"{BASE}/runs/{run_id}/apply",
        data={
            "csrf_token": csrf,
            "review_token": review_token,
            "confirm_apply": "on",
            "reason": UNSIGNED_OVERRIDE,
        },
    )
    assert response.status_code == 200
    after = _route_count()
    assert after == before + 3, f"apply committed {after - before} route rows, expected 3"
    # exactly one audit row, carrying the SIGNED reason (unsigned ignored)
    assert _application_count() == 1
    committed = _committed_reason()
    assert committed == SIGNED_REASON
    assert UNSIGNED_OVERRIDE not in (committed or "")
    # the ACTUAL Core audit_log row: exactly one, bound to the superadmin
    # actor, carrying this run (the operator reason lives on the durable
    # application record asserted above).
    superadmin_id, _ = _admin_ids(env217["database_url"], env217["emails"]["superadmin"])
    audit_rows = _apply_audit_rows(env217["database_url"], run_id)
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == superadmin_id
    assert audit_rows[0][1].get("run_id") == run_id
    # the truthful result is servable through the non-rotating read context
    response = client.get(f"{BASE}/runs/{run_id}/apply-status")
    assert response.status_code == 200
    # the status page renders the ACTUAL authoritative application record
    # (durable outcome facts + nonempty counts), not just the run id
    assert "Authoritative record" in response.text
    assert "committed (authoritative application record found)" in response.text
    # the rendered counts EXACTLY match the durable application record
    rec_counts = _created_counts()
    assert rec_counts is not None and rec_counts["routes"] >= 3, rec_counts
    assert f"routes: {rec_counts['routes']}" in response.text
    assert f"pricing: {rec_counts['pricing']}" in response.text
    assert f"providers: {rec_counts['providers']}" in response.text
    assert f"fx: {rec_counts['fx']}" in response.text
    assert SIGNED_REASON in response.text
    assert "n/a (UTC)" not in response.text
    assert "UNCONFIRMED until" not in response.text

    # --- committed repeat: idempotent, no second audit row --------------
    # A fresh review on the SAME now-committed run returns already_committed:
    # it commits nothing new and adds NO duplicate application row.
    routes_after_commit = _route_count()
    apps_after_commit = _application_count()
    audit_after_commit = len(_apply_audit_rows(env217["database_url"], run_id))
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    response = client.post(
        f"{BASE}/runs/{run_id}/apply-preview", data={"csrf_token": csrf}
    )
    assert response.status_code == 200
    repeat_data: dict[str, Any] = {
        "csrf_token": csrf,
        "reason": "217-a committed repeat: the same reviewed plan is re-applied",
    }
    for code in warnings:
        repeat_data.setdefault("ack_warning_code", []).append(code)
    response = client.post(f"{BASE}/runs/{run_id}/apply-preview", data=repeat_data)
    assert response.status_code == 200
    repeat_match = REVIEW_TOKEN_RE.search(response.text)
    assert repeat_match, "repeat review page carries no signed review token"
    repeat_token = repeat_match.group(1)
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        f"{BASE}/runs/{run_id}/apply",
        data={"csrf_token": csrf, "review_token": repeat_token, "confirm_apply": "on"},
    )
    assert response.status_code == 200
    assert "already_committed" in response.text
    # nothing new committed; the original audit row remains the ONLY one
    assert _route_count() == routes_after_commit
    assert _application_count() == apps_after_commit == 1
    # and the ACTUAL Core audit_log is unchanged (a committed repeat re-applies
    # nothing and writes no second apply-audit row)
    assert len(_apply_audit_rows(env217["database_url"], run_id)) == audit_after_commit == 1


# ---------------------------------------------------------------------------
# Reviewed-apply gate matrix (REAL sessions/CSRF, over the committed run)
# ---------------------------------------------------------------------------


def test_apply_gate_missing_confirm(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    run_id: str = env217["collect_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    before = _count_apps(env217["database_url"], run_id)
    token = _signed_token(client, run_id, warnings, "gate: explicit confirmation required")
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    # a valid token but NO explicit confirmation checkbox
    response = client.post(
        f"{BASE}/runs/{run_id}/apply",
        data={"csrf_token": csrf, "review_token": token},
    )
    assert response.status_code == 400
    assert "confirm" in response.text.lower()
    assert _count_apps(env217["database_url"], run_id) == before


def test_apply_gate_tampered_token(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    run_id: str = env217["collect_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    before = _count_apps(env217["database_url"], run_id)
    token = _signed_token(client, run_id, warnings, "gate: token integrity")
    body, dot, digest = token.rpartition(".")
    # flip ONE hex char in the HMAC digest: format stays valid, digest fails
    flipped = "1" if digest[-1] != "1" else "0"
    tampered = body + dot + digest[:-1] + flipped
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    response = client.post(
        f"{BASE}/runs/{run_id}/apply",
        data={"csrf_token": csrf, "review_token": tampered, "confirm_apply": "on"},
    )
    assert response.status_code == 400
    assert _count_apps(env217["database_url"], run_id) == before


def test_apply_gate_wrong_session(env217: dict[str, Any]) -> None:
    # The review token is bound to a specific admin session: a token minted
    # in session S1 must NOT be accepted by a different session S2 (re-login
    # of the same superadmin), even though the role still passes.
    main_client: TestClient = env217["client"]
    run_id: str = env217["collect_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    before = _count_apps(env217["database_url"], run_id)
    token = _signed_token(main_client, run_id, warnings, "gate: session binding")
    with TestClient(env217["app"]) as other:
        _login(other, email=env217["emails"]["superadmin"])
        csrf = _page_csrf(other, f"{BASE}/runs/{run_id}/")
        response = other.post(
            f"{BASE}/runs/{run_id}/apply",
            data={"csrf_token": csrf, "review_token": token, "confirm_apply": "on"},
        )
        assert response.status_code == 400
    assert _count_apps(env217["database_url"], run_id) == before


def test_apply_gate_expired_token(env217: dict[str, Any]) -> None:
    settings: Settings = env217["settings"]
    client: TestClient = env217["client"]
    run_id: str = env217["collect_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    before = _count_apps(env217["database_url"], run_id)
    user_id, session_id = _admin_ids(
        env217["database_url"], env217["emails"]["superadmin"]
    )
    built, refusal = router_mod._apply_review_document(
        settings, run_id, reason="gate: token expiry", ack_codes=list(warnings)
    )
    assert built is not None, refusal
    document, _ = built
    token = router_mod.build_catalog_refresh_review_token(
        admin_session_secret=settings.ADMIN_SESSION_SECRET,
        admin_user_id=uuid.UUID(user_id),
        admin_session_id=uuid.UUID(session_id),
        review_document=document,
        ttl_seconds=1,
    )
    time.sleep(1.2)  # let the 1s TTL lapse
    csrf = _page_csrf(client, f"{BASE}/runs/{run_id}/")
    response = client.post(
        f"{BASE}/runs/{run_id}/apply",
        data={"csrf_token": csrf, "review_token": token, "confirm_apply": "on"},
    )
    assert response.status_code == 400
    assert _count_apps(env217["database_url"], run_id) == before


def test_apply_gate_run_binding(env217: dict[str, Any]) -> None:
    # A token bound to the COLLECT run cannot be applied to the (different)
    # independent REVIEW run id.
    client: TestClient = env217["client"]
    collect_run_id: str = env217["collect_run_id"]
    review_run_id: str = env217["review_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    token = _signed_token(client, collect_run_id, warnings, "gate: run binding")
    csrf = _page_csrf(client, f"{BASE}/runs/{review_run_id}/")
    response = client.post(
        f"{BASE}/runs/{review_run_id}/apply",
        data={"csrf_token": csrf, "review_token": token, "confirm_apply": "on"},
    )
    assert response.status_code == 400
    assert "bind" in response.text.lower()


def test_apply_download_then_same_page_apply(env217: dict[str, Any]) -> None:
    # NON-ROTATING read context + committed-repeat through the real signed
    # form: authenticated read-only GETs (artifact download, apply-status) must
    # not consume the stored form token, so the SAME page's token (csrf1) still
    # drives a signed final apply; that apply is a committed repeat (the collect
    # run is already committed) and leaves the authoritative DB outcome unchanged.
    client: TestClient = env217["client"]
    run_id: str = env217["collect_run_id"]
    warnings: list[str] = env217["collect_warnings"]
    page = client.get(f"{BASE}/runs/{run_id}/")
    assert page.status_code == 200
    csrf1 = CSRF_RE.search(page.text).group(1)
    # read-only authenticated downloads/status (non-rotating)
    artifact = client.get(f"{BASE}/runs/{run_id}/artifact/catalog-refresh.json")
    assert artifact.status_code == 200
    status = client.get(f"{BASE}/runs/{run_id}/apply-status")
    assert status.status_code == 200

    # the ORIGINAL page's token (csrf1) is still valid after the read-only GETs:
    # walk the two-step signed form to mint a final review token.
    data: dict[str, Any] = {
        "csrf_token": csrf1,
        "reason": "217-a same-page signed final apply after read-only downloads",
    }
    for code in warnings:
        data.setdefault("ack_warning_code", []).append(code)
    response = client.post(f"{BASE}/runs/{run_id}/apply-preview", data=data)
    assert response.status_code == 200
    token_match = REVIEW_TOKEN_RE.search(response.text)
    assert token_match, "same-page signed final form produced no review token"
    review_token = token_match.group(1)

    # the authoritative committed outcome BEFORE the committed-repeat apply
    routes_before = _route_count(env217["database_url"])
    apps_before = _count_apps(env217["database_url"], run_id)
    audit_before = len(_apply_audit_rows(env217["database_url"], run_id))

    # final apply (signed token + explicit confirm) - a committed repeat
    csrf_final = CSRF_RE.search(response.text).group(1)
    response = client.post(
        f"{BASE}/runs/{run_id}/apply",
        data={"csrf_token": csrf_final, "review_token": review_token, "confirm_apply": "on"},
    )
    assert response.status_code == 200
    assert "already_committed" in response.text
    # authoritative DB outcome is UNCHANGED: no new routes, application row,
    # or apply-audit row
    assert _route_count(env217["database_url"]) == routes_before
    assert _count_apps(env217["database_url"], run_id) == apps_before
    assert len(_apply_audit_rows(env217["database_url"], run_id)) == audit_before
# ---------------------------------------------------------------------------
# 5. role boundary: ordinary admin is refused BEFORE any effect
# ---------------------------------------------------------------------------


def test_apply_preview_refuses_ordinary_admin(env217: dict[str, Any]) -> None:
    app = env217["app"]
    with TestClient(app) as other:
        _login(other, email=env217["emails"]["admin"])
        run_id: str = env217["review_run_id"]
        response = other.get(f"{BASE}/runs/{run_id}/")
        assert response.status_code == 200  # inspection remains available
        csrf = CSRF_RE.search(response.text).group(1)
        response = other.post(f"{BASE}/runs/{run_id}/apply-preview", data={"csrf_token": csrf})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# 6. QUEUED export-baseline: real owned-PG export
# ---------------------------------------------------------------------------


def test_queued_export_baseline_smoke(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    csrf = _page_csrf(client, f"{BASE}/export-baseline")
    response = client.post(
        f"{BASE}/export-baseline/submit", data={"csrf_token": csrf}
    )
    assert response.status_code == 200
    assert "broker acknowledged" in response.text
    row = _wait_job(settings, "export_baseline")
    assert row["status"] == "ready", row
    artifact = row["artifact_name"]
    assert artifact and artifact.startswith("baseline-")
    response = client.get(f"{BASE}/jobs/{row['job_id']}/artifact/{artifact}")
    assert response.status_code == 200
    document = json.loads(response.content)
    assert document["schema_version"] == "1"
    assert document["sql_checked"] is True
    assert document["target"]["database"] == "test"  # the owned database
    # the apply step committed real rows before this export
    assert document["counts"]["routes"] >= 3


# ---------------------------------------------------------------------------
# Job-result binding: acknowledgements and ?job= refresh navigation bind to
# the EXACT server-created job id; an explicit unknown/foreign id is refused
# and NEVER substituted by the newest job of the family.
# ---------------------------------------------------------------------------


def test_job_result_binding_exact_id(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]

    def _post_export() -> str:
        csrf = _page_csrf(client, f"{BASE}/export-baseline")
        response = client.post(
            f"{BASE}/export-baseline/submit", data={"csrf_token": csrf}
        )
        assert response.status_code == 200
        return _latest_job(settings, "export_baseline")["job_id"]

    job_a = _post_export()
    row_a = _wait_job(settings, "export_baseline")
    assert row_a["job_id"] == job_a
    assert row_a["status"] == "ready", row_a
    job_b = _post_export()
    assert job_b != job_a
    row_b = _wait_job(settings, "export_baseline")
    assert row_b["job_id"] == job_b and row_b["status"] == "ready", row_b

    # 1. the EXACT bound id renders that job (and only that job) even though
    #    another same-family job exists and is newer
    response = client.get(f"{BASE}/export-baseline", params={"job": job_a})
    assert response.status_code == 200
    assert f"<code>{job_a}</code>" in response.text
    assert job_b not in response.text
    # 2. the absent param keeps the explicitly latest-global view (newest)
    response = client.get(f"{BASE}/export-baseline")
    assert response.status_code == 200
    assert f"<code>{job_b}</code>" in response.text
    assert job_a not in response.text
    # 3. an EXPLICIT unknown id is refused: no job block, never the newest
    response = client.get(
        f"{BASE}/export-baseline", params={"job": "f" * 32}
    )
    assert response.status_code == 200
    assert "Job status unavailable" in response.text
    assert job_a not in response.text and job_b not in response.text
    # 4. malformed ids are refused the same way
    response = client.get(f"{BASE}/export-baseline", params={"job": job_a[:16]})
    assert "Job status unavailable" in response.text
    assert job_a not in response.text
    # 5. foreign-family id (a collect/review job id shape cannot exist here,
    #    so use the exact-id service guard for a proposal-family id instead)
    assert custody.get_job(settings, job_a) is not None
    bound = router_mod._bound_job(settings, job_a, "proposal")
    assert bound is None  # exact id, wrong family: refused, not substituted
    last, refusal = router_mod._resolve_bound_view(
        SimpleNamespace(query_params={"job": job_a}), settings, "proposal", []
    )
    assert last is None and refusal


# ---------------------------------------------------------------------------
# Secret-persistence canaries: the request's OWN session value embedded in
# collect/review/proposal inputs is refused BEFORE any job/custody write.
# ---------------------------------------------------------------------------


def test_secret_canaries_refused(
    env217: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    canary = client.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    assert canary, "authenticated session cookie not present"
    canary_bytes = canary.encode("utf-8")
    worker_log = env217["workdir"] / "worker.log"
    responses: list[str] = []

    def _custody_has_canary() -> bool:
        for path in env217["custody_root"].rglob("*"):
            if path.is_file() and canary_bytes in path.read_bytes():
                return True
        return False

    jobs_before = len(custody.list_jobs(settings, limit=100))

    # 1. collect: the canary in the real models field (which IS captured into
    #    job params/output) - refusal proves it is never persisted.
    csrf = _page_csrf(client, f"{BASE}/collect")
    response = client.post(
        f"{BASE}/collect/submit",
        data={"csrf_token": csrf, "mode": "bootstrap", "providers": "openai", "models": canary},
    )
    assert response.status_code == 200
    assert "known incoming authentication value" in response.text
    responses.append(response.text)
    assert len(custody.list_jobs(settings, limit=100)) == jobs_before

    # 2. review: the canary embedded in the uploaded bundle bytes
    collect_bundle = json.loads(env217["collect_bundle_bytes"])
    collect_bundle["notes"] = canary
    canary_bundle_bytes = (
        json.dumps(collect_bundle, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    csrf = _page_csrf(client, f"{BASE}/review")
    response = client.post(
        f"{BASE}/review/submit",
        data={"csrf_token": csrf},
        files={"bundle": ("bundle.json", canary_bundle_bytes, "application/json")},
    )
    assert response.status_code == 200
    assert "known incoming authentication value" in response.text
    responses.append(response.text)
    assert len(custody.list_jobs(settings, limit=100)) == jobs_before

    # 3. proposals: the canary in an explicit include-model selection
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/proposals/generate",
        data={
            "csrf_token": csrf,
            "provider_scope": "openrouter",
            "endpoint_scope": "chat_completions",
            "source_method": "docs",
            "include_models": canary,
        },
    )
    assert response.status_code == 200
    assert "known incoming authentication value" in response.text
    responses.append(response.text)
    assert len(custody.list_jobs(settings, limit=100)) == jobs_before

    # the canary leaked NOWHERE: not the refused pages, not the parent-process
    # logs, not the worker log (dispatch never happened), not custody.
    for body in responses:
        assert canary not in body
    assert canary not in caplog.text
    assert canary_bytes not in (worker_log.read_bytes() if worker_log.exists() else b"")
    assert not _custody_has_canary()


# ---------------------------------------------------------------------------
# QUEUED proposal through the DEFAULT registry/bridge seam (only the proposal
# transport is a synthetic MockTransport) -> generated TSV -> import preview.
# ---------------------------------------------------------------------------


def test_proposal_queued_default_bridge_to_import_preview(env217: dict[str, Any]) -> None:
    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/proposals/generate",
        data={
            "csrf_token": csrf,
            "provider_scope": "openrouter",
            "endpoint_scope": "chat_completions",
            "source_method": "docs",
            "max_models": "500",
            "fetch_details_limit": "0",
            "max_web_calls": "3",
            "currency": "USD",
            "ordinary_chat_only": "on",
            "paired_ready_only": "on",
            "package_name": "openrouter-chat-text",
        },
    )
    assert response.status_code == 200
    assert "broker acknowledged" in response.text
    row = _wait_job(settings, "proposal")
    assert row["status"] == "ready", row
    job_id = row["job_id"]
    # the generated TSV is a verified custody artifact (real worker output)
    tsv = client.get(f"{BASE}/jobs/{job_id}/artifact/routes-proposal.tsv")
    assert tsv.status_code == 200
    text = tsv.content.decode("utf-8")
    assert "requested_model" in text
    assert "synth/alpha" in text
    # --- generated package usability (closed known preset) -----------------
    # the proposals page lists the closed preset directory that was generated
    response = client.get(f"{BASE}/proposals")
    assert response.status_code == 200
    assert "Generated packages" in response.text
    assert "openrouter-chat-text" in response.text
    # ONE closed preset file download through the held anchored custody read
    pkg = client.get(
        f"{BASE}/jobs/{job_id}/package/openrouter-chat-text/routes-proposal.tsv"
    )
    assert pkg.status_code == 200
    pkg_text = pkg.content.decode("utf-8")
    assert "requested_model" in pkg_text
    assert "synth/alpha" in pkg_text
    # the package TSV bridges to the EXISTING import preview (no import run)
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/jobs/{job_id}/package/openrouter-chat-text/import-preview/routes",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 200
    assert "synth/alpha" in response.text
    # unknown package file names are refused (closed set), not served
    refused = client.get(f"{BASE}/jobs/{job_id}/package/openrouter-chat-text/rogue.txt")
    assert refused.status_code == 404
    # bridge the TSV to the EXISTING import preview (routes) - NO import run
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/jobs/{job_id}/import-preview/routes", data={"csrf_token": csrf}
    )
    assert response.status_code == 200
    assert "synth/alpha" in response.text
    # and the pricing preview
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/jobs/{job_id}/import-preview/pricing", data={"csrf_token": csrf}
    )
    assert response.status_code == 200


def _seed_fx_rate(database_url: str, *, rate: Decimal, valid_from: datetime) -> str:
    """Seed ONE configured direct FX row in the REAL owned PG; returns
    the row id (the capture must reference exactly this row)."""
    from slaif_gateway.db.repositories.fx_rates import FxRatesRepository

    def _coro(session):
        async def _run() -> str:
            row = await FxRatesRepository(session).create_fx_rate(
                base_currency="USD",
                quote_currency="EUR",
                rate=rate,
                valid_from=valid_from,
                source="217-fx-queue-test",
            )
            await session.commit()
            return str(row.id)

        return _run()

    return _db_worker(database_url, _coro)


def test_proposal_queued_non_usd_fx_conversion_real_pg(env217: dict[str, Any]) -> None:
    """QUEUED non-USD proposal with the REAL owned PG: ONE configured
    direct USD->EUR row (seeded here) is captured exactly once by the
    real worker BEFORE generation (source transport stays synthetic),
    and the published pricing TSV is converted with that rate - source
    USD facts and the applied FX pair preserved, same fact in the
    normalized JSON, and the converted rows still bridge to the
    EXISTING import preview (no import execution)."""
    from slaif_gateway.services.pricing_import import parse_pricing_import_tsv

    client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    database_url: str = env217["database_url"]

    rate = Decimal("1.08")
    # valid_from = NOW: the earlier reviewed-apply commit in this module
    # already created a USD->EUR row with an EARLIER valid_from, and
    # find_latest_rate orders valid_from desc - so this deliberately
    # seeded row is the ONE row the capture must pick.
    seed_time = datetime.now(UTC)
    fx_rate_id = _seed_fx_rate(
        database_url,
        rate=rate,
        valid_from=seed_time,
    )

    known = {
        row["job_id"]
        for row in custody.list_jobs(settings, limit=100)
        if row.get("family") == "proposal"
    }
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/proposals/generate",
        data={
            "csrf_token": csrf,
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
    assert response.status_code == 200
    assert "broker acknowledged" in response.text
    row = _wait_new_job(settings, "proposal", known)
    assert row["status"] == "ready", row
    job_id = row["job_id"]
    # the ready progress states the one applied conversion truthfully
    assert "FX USD→EUR" in row["progress"]
    assert "rate=1.08" in row["progress"]

    # the published pricing TSV is converted with the captured rate
    tsv = client.get(f"{BASE}/jobs/{job_id}/artifact/pricing-proposal.tsv")
    assert tsv.status_code == 200
    rows = parse_pricing_import_tsv(tsv.content.decode("utf-8"))
    data_rows = [r for r in rows if r.get("model")]
    assert data_rows, "no pricing rows were published"
    quantum = Decimal("0.000000001")

    for r in data_rows:
        assert r["currency"] == "EUR"
        metadata = json.loads(r["pricing_metadata"])
        assert metadata["source_currency"] == "USD"
        assert metadata["fx"]["fx_rate_id"] == fx_rate_id
        assert metadata["fx"]["rate"] == "1.08"
        source_prices = metadata["source_prices"]
        for field in (
            "input_price_per_1m",
            "cached_input_price_per_1m",
            "output_price_per_1m",
            "reasoning_price_per_1m",
            "request_price",
        ):
            original = source_prices[field]
            if original in (None, ""):
                assert r[field] == ""
            else:
                # exact Decimal equality against the ONE captured rate
                # (production strips trailing zeros; never floats/tolerance)
                expected = (Decimal(original) * rate).quantize(
                    quantum, rounding=ROUND_HALF_UP
                )
                # an originally-zero price is legitimate and stays zero;
                # a POSITIVE price that became zero would be a refusal
                if Decimal(original) > 0:
                    assert expected != 0
                assert Decimal(r[field]) == expected
    # the normalized JSON artifact carries the same capture fact
    normalized = client.get(
        f"{BASE}/jobs/{job_id}/artifact/provider-catalog-normalized.json"
    )
    assert normalized.status_code == 200
    payload = json.loads(normalized.content.decode("utf-8"))
    assert payload["fx"]["fx_rate_id"] == fx_rate_id
    assert payload["fx"]["target_currency"] == "EUR"

    # the converted output bridges to the EXISTING pricing import preview
    csrf = _page_csrf(client, f"{BASE}/proposals")
    response = client.post(
        f"{BASE}/jobs/{job_id}/import-preview/pricing", data={"csrf_token": csrf}
    )
    assert response.status_code == 200
    # the preview DISPLAYS the converted rows: exact valid/invalid counts
    # and the EUR currency on the rows (not merely an HTTP 200)
    preview_text = response.text
    valid_match = re.search(
        r"Valid rows</span>\s*<strong>(\d+)</strong>", preview_text
    )
    invalid_match = re.search(
        r"Invalid rows</span>\s*<strong>(\d+)</strong>", preview_text
    )
    assert valid_match and int(valid_match.group(1)) == len(data_rows)
    assert invalid_match and int(invalid_match.group(1)) == 0
    assert "EUR" in preview_text
    assert "synth/alpha" in preview_text


# ---------------------------------------------------------------------------
# 7. dashboard-off guard: every new route fails closed, authenticated
# ---------------------------------------------------------------------------


def test_dashboard_off_guard_authed_session(env217: dict[str, Any]) -> None:
    main_client: TestClient = env217["client"]
    settings: Settings = env217["settings"]
    jobs_before = len(custody.list_jobs(settings, limit=100))
    off_settings = _settings(
        env217["database_url"],
        env217["custody_root"],
        Path(env217["settings"].CATALOG_REFRESH_SEAL_KEY),
        ENABLE_ADMIN_DASHBOARD=False,
    )
    with TestClient(create_app(off_settings)) as off:
        # carry the VALID authenticated session cookie from the main app
        off.cookies.update(main_client.cookies)
        run_id = env217["review_run_id"]
        job_id = "0" * 32
        routes = [
            ("GET", f"{BASE}/"),
            ("GET", f"{BASE}/proposals"),
            ("POST", f"{BASE}/proposals/generate"),
            ("GET", f"{BASE}/collect"),
            ("POST", f"{BASE}/collect/submit"),
            ("GET", f"{BASE}/review"),
            ("POST", f"{BASE}/review/submit"),
            ("GET", f"{BASE}/export-baseline"),
            ("POST", f"{BASE}/export-baseline/submit"),
            ("GET", f"{BASE}/runs/{run_id}/"),
            ("POST", f"{BASE}/runs/{run_id}/verify"),
            ("GET", f"{BASE}/runs/{run_id}/artifact/validation.json"),
            ("GET", f"{BASE}/jobs/{job_id}/artifact/baseline-{job_id}"),
            ("POST", f"{BASE}/jobs/{job_id}/cancel"),
            ("POST", f"{BASE}/jobs/{job_id}/remove"),
            ("POST", f"{BASE}/runs/{run_id}/remove"),
            ("POST", f"{BASE}/runs/{run_id}/apply-preview"),
            ("POST", f"{BASE}/runs/{run_id}/apply"),
            ("GET", f"{BASE}/runs/{run_id}/apply-status"),
            ("POST", f"{BASE}/jobs/{job_id}/import-preview/routes"),
        ]
        for method, path in routes:
            if method == "GET":
                response = off.get(path)
            else:
                response = off.post(path, data={"csrf_token": "off"})
            assert response.status_code == 404, (method, path, response.status_code)
    # no effect at all: no new jobs, no dispatch
    assert len(custody.list_jobs(settings, limit=100)) == jobs_before


# ---------------------------------------------------------------------------
# 8. feature-off (GUI disabled): useful refusal, fail closed, no dispatch
# ---------------------------------------------------------------------------


def test_feature_off_fail_closed(env217: dict[str, Any]) -> None:
    settings: Settings = env217["settings"]
    jobs_before = len(custody.list_jobs(settings, limit=100))
    off_settings = _settings(
        env217["database_url"],
        env217["custody_root"],
        Path(settings.CATALOG_REFRESH_SEAL_KEY),
        CATALOG_REFRESH_GUI_ENABLED=False,
    )
    with TestClient(create_app(off_settings)) as off:
        _login(off, email=env217["emails"]["superadmin"])
        # ordinary app routes stay usable
        assert off.get("/admin/").status_code == 200
        # the catalog index renders the useful disabled setup state
        response = off.get(f"{BASE}/")
        assert response.status_code == 200
        assert "disabled" in response.text.lower()
        # actions fail closed: refused, no job, no dispatch
        csrf = CSRF_RE.search(response.text).group(1)
        response = off.post(
            f"{BASE}/collect/submit",
            data={"csrf_token": csrf, "mode": "bootstrap", "providers": "openai"},
        )
        assert response.status_code == 200
        assert "broker acknowledged" not in response.text
    assert len(custody.list_jobs(settings, limit=100)) == jobs_before
