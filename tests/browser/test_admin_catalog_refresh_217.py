"""217-a G15 GUI catalog refresh: real-Chromium browser qualification.

Real browser, real uvicorn app, owned PostgreSQL, owned Redis broker, and
the disposable REAL Celery application worker (root-authorized for this
bounded test). Scope labels: broker/PG/auth/CSRF surfaces are REAL (this
process dispatches; the worker process consumes and seals); only the
official-source bytes are synthetic (the labeled worker seams). No
upstream network, no ambient database/Redis.

Cases (file order is significant; the module environment is shared):

- real login; the workspace index renders the honest setup-READY state
  (desktop, no horizontal overflow);
- queued bootstrap COLLECT from the real form: sealed run, and the run
  page renders REAL non-empty facts (READY state, the configured
  NOT-SQL-observed target with the owned PG database/host/port, unknown
  version, non-zero disposition counts, apply-plan identity) - asserted
  content, not merely HTTP 200;
- the reviewed-apply workflow for the COLLECT run: prepare -> signed
  operator intent (exact sealed warning vocabulary) -> explicit confirm
  -> committed, with persisted routes/application/audit oracles and the
  honest apply-status page; a committed repeat returns already_committed
  and changes nothing (the gate matrix stays in the native module - not
  duplicated here);
- authenticated sealed artifact download, then the SAME page's verify
  form (original token) still works (non-rotating read context);
- queued proposal with the closed openrouter-chat-text PACKAGE: the page
  lists the generated package, a real package file download, and the
  package route/pricing import previews with non-empty rows (per-M USD);
- a deliberately constructed independent supplied bundle (fresh explicit
  test run_id assigned in TEST SETUP, never rewritten in production) is
  published under its SUPPLIED id (NEW-ONLY);
- keyboard-only submit (export baseline), narrow (420px) layout without
  horizontal overflow, and a no-JS operator flow that performs a REAL
  read-only operation (export baseline form POST), not just GET/render;
- desktop + narrow captures for operator visual review.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import socket
import stat
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import uvicorn

from sqlalchemy import select

from slaif_gateway.config import Settings
from slaif_gateway.db.models import CatalogRefreshApplication
from slaif_gateway.main import create_app
from slaif_gateway.services import admin_catalog_refresh as custody
from tests.integration.test_admin_catalog_refresh_217_postgres import (
    ADMIN_PASSWORD,
    BASE,
    TERMINAL_JOB_STATUSES,
    _admin_ids,
    _apply_audit_rows,
    _count_apps,
    _db_worker,
    _kill_worker,
    _route_count,
    _seed_admins,
    _settings,
    _spawn_worker,
)
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_redis_url as _owned_redis_url_fixture,
)

pytestmark = pytest.mark.playwright

LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif217")
DESKTOP = {"width": 1440, "height": 900}
NARROW = {"width": 420, "height": 860}

# Re-export the qualified owned-PG/Redis fixtures under the expected names.
owned_pg_url = _owned_pg_url_fixture
owned_redis_url = _owned_redis_url_fixture


# ---------------------------------------------------------------------------
# Real uvicorn (214/215/216 pattern)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _run_uvicorn_server(app, port: int) -> Iterator[None]:
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        lifespan="on",
        timeout_keep_alive=1,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("Uvicorn server thread exited before startup")
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for Uvicorn server startup")
            time.sleep(0.05)
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ---------------------------------------------------------------------------
# Module environment: owned PG + owned Redis + real worker + real uvicorn
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env217_browser(
    owned_pg_url: str, owned_redis_url: str, tmp_path_factory
) -> Iterator[dict[str, Any]]:
    monkey = pytest.MonkeyPatch()
    monkey.setenv("APP_ENV", "test")
    monkey.setenv("DATABASE_URL", owned_pg_url)
    monkey.setenv("REDIS_URL", owned_redis_url)
    monkey.setenv("ENABLE_EMAIL_DELIVERY", "false")
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    from slaif_gateway.workers import celery_app as _celery_module

    # Same singleton isolation as the native module: save the ORIGINAL
    # pool cache slots (never accessed/created just to close them), clear
    # the slots, and restore originals plus config in teardown.
    _app = _celery_module.celery_app
    _orig_broker = _app.conf.broker_url
    _orig_backend = _app.conf.result_backend
    _orig_pool = _app._pool
    _orig_amqp = _app.__dict__.get("amqp")
    _orig_producer_pool = (
        _orig_amqp._producer_pool if _orig_amqp is not None else None
    )
    _app._pool = None
    if _orig_amqp is not None:
        _orig_amqp._producer_pool = None
    _app.conf.broker_url = owned_redis_url
    assert _app.conf.broker_url == owned_redis_url
    assert not _app.conf.result_backend

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    workdir = tmp_path_factory.mktemp("catalog217-browser")
    custody_root = workdir / "custody"
    custody_root.mkdir(mode=0o700)
    seal_key = workdir / "seal.hex"
    seal_key.write_bytes(b"dd" * 32)
    os.chmod(seal_key, stat.S_IRUSR | stat.S_IWUSR)

    settings = _settings(owned_pg_url, custody_root, seal_key)
    emails = asyncio.run(_seed_admins(owned_pg_url))
    app = create_app(settings)
    worker_proc = _spawn_worker(
        pg_url=owned_pg_url,
        redis_url=owned_redis_url,
        custody_root=custody_root,
        seal_key=seal_key,
        log_path=workdir / "worker.log",
    )
    port = _free_port()
    base: dict[str, Any] = {
        "settings": settings,
        "admin_email": emails["superadmin"],
        "base_url": f"http://127.0.0.1:{port}",
        "database_url": owned_pg_url,
        "custody_root": custody_root,
        "workdir": workdir,
    }
    try:
        with _run_uvicorn_server(app, port):
            yield base
    finally:
        _kill_worker(worker_proc)
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
            _app.__dict__.pop("amqp", None)
        _app._pool = _orig_pool
        _app.conf.broker_url = _orig_broker
        _app.conf.result_backend = _orig_backend
        # REQUIRED isolation assertions (no URL printing):
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


@pytest.fixture(scope="module")
def chromium(env217_browser) -> Iterator[object]:
    """Depends on ``env217_browser`` on purpose: the Playwright sync
    session runs an asyncio loop on the main thread, so app/worker
    startup must complete BEFORE it starts."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(page: object, base_url: str, email: str) -> None:
    page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', email)  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f"{LOGIN_FORM} button[type='submit']")  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _latest_job(settings: Settings, family: str) -> dict[str, Any] | None:
    for row in custody.list_jobs(settings, limit=100):
        if row.get("family") == family:
            return row
    return None


def _wait_job(settings: Settings, family: str, *, timeout: float = 180.0) -> dict[str, Any]:
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


def _widest_overflow(page: object) -> dict[str, Any]:
    """Diagnostic for a width assertion failure: the rightmost rendered
    element past the viewport (tag/id/class/right) - the overflow cause
    is diagnosed from the DOM, never hidden by a wider tolerance."""
    return page.evaluate(  # type: ignore[attr-defined]
        "() => {"
        "  const v = document.documentElement.clientWidth;"
        "  let worst = null;"
        "  for (const el of document.querySelectorAll('*')) {"
        "    const r = el.getBoundingClientRect();"
        "    if (r.right > v + 1 && (!worst || r.right > worst.right))"
        "      worst = {tag: el.tagName, id: el.id,"
        "               cls: String(el.className).slice(0, 96),"
        "               right: Math.round(r.right)};"
        "  }"
        "  return {scrollWidth: document.documentElement.scrollWidth,"
        "          clientWidth: v, worst};"
        "}"
    )


# ---------------------------------------------------------------------------
# 1. login + index setup-READY (desktop)
# ---------------------------------------------------------------------------


def test_index_setup_ready_after_real_login(env217_browser: dict[str, Any], chromium: object) -> None:
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        base = str(env217_browser["base_url"])
        _login(page, base, str(env217_browser["admin_email"]))
        page.goto(f"{base}{BASE}/")
        html = page.content()
        assert "Catalog refresh" in html
        assert "Operator storage is" in html and "<strong>ready</strong>" in html
        width = page.evaluate("document.documentElement.scrollWidth")  # type: ignore[attr-defined]
        assert width <= DESKTOP["width"] + 10, width
        page.screenshot(path=str(SCREENSHOT_DIR / "217a-index-desktop.png"))  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# 2. queued bootstrap collect: sealed run with REAL non-empty rendering
# ---------------------------------------------------------------------------


def test_collect_bootstrap_sealed_run_rendering(env217_browser: dict[str, Any], chromium: object) -> None:
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        base = str(env217_browser["base_url"])
        settings: Settings = env217_browser["settings"]
        _login(page, base, str(env217_browser["admin_email"]))
        page.goto(f"{base}{BASE}/collect")
        # the mode radios are intentionally required with NO default:
        # select bootstrap explicitly (production stays auto-default-free)
        page.check("#collect-mode-bootstrap")  # type: ignore[attr-defined]
        page.select_option(  # type: ignore[attr-defined]
            "#collect-providers", ["openai", "openrouter"]
        )
        page.get_by_role("button", name="Start collect").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        assert "broker acknowledged" in page.content()
        row = _wait_job(settings, "collect")
        assert row["status"] in ("ready", "warnings"), row
        run_id = str(row["run_id"])
        assert run_id.startswith("collect-")
        env217_browser["collect_run_id"] = run_id
        # ALL sealed warning codes (the exact acknowledgement vocabulary
        # the reviewed apply must select); captured once for the apply test
        capture, handle = custody.load_run_capture(settings, run_id)
        try:
            env217_browser["collect_warnings"] = sorted(
                {w.code for w in capture.report.warnings if w.code}
            )
        finally:
            handle.close()

        # the run page renders REAL non-empty facts (asserted content,
        # not merely HTTP 200)
        page.goto(f"{base}{BASE}/runs/{run_id}/")
        html = page.content()
        assert "<dt>State</dt><dd>READY" in html or "READY_WITH_WARNINGS" in html
        parsed = urlparse(str(env217_browser["database_url"]))
        assert "<dt>Baseline mode</dt><dd>first_install</dd>" in html
        assert f"<dd>{parsed.path.lstrip('/')} @ {parsed.hostname}:{parsed.port}" in html
        assert "configured (NOT SQL-observed)" in html
        assert "unknown (not SQL-observed)" in html
        assert "no — no SQL observation (bootstrap/first-install)" in html
        new_match = re.search(r"<dt>new</dt><dd>(\d+)</dd>", html)
        assert new_match and int(new_match.group(1)) >= 3, "non-empty disposition counts"
        assert "Apply plan and identity" in html
        assert "Identity match</dt><dd>yes" in html
        # canonical rendering: a bounded safe projection of the SAME sealed
        # apply plan, and price comparisons with explicit missing-price
        # rendering (bootstrap has NO prior prices; never a literal None)
        assert "Plan operations" in html
        assert "create_route" in html
        assert "Price comparisons" in html
        assert "— (no prior price)" in html
        assert "None%" not in html and "None None" not in html
        page.screenshot(path=str(SCREENSHOT_DIR / "217a-run-desktop.png"), full_page=True)  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# 3. reviewed apply (COLLECT run): signed intent -> confirm -> committed
# ---------------------------------------------------------------------------


def test_reviewed_apply_commits_and_status(env217_browser: dict[str, Any], chromium: object) -> None:
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        base = str(env217_browser["base_url"])
        database_url = str(env217_browser["database_url"])
        _login(page, base, str(env217_browser["admin_email"]))
        run_id = str(env217_browser["collect_run_id"])
        warnings = list(env217_browser["collect_warnings"])
        signed_reason = (
            "217-a browser qualification: apply the synthetic official-source catalog"
        )
        before = _route_count(database_url)
        assert _count_apps(database_url, run_id) == 0

        def _created_counts() -> dict[str, int] | None:
            # The DURABLE created/superseded counts of the committed
            # application record (the exact values the status page renders).
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

            return _db_worker(database_url, _run)
        # step 1: sealed facts page
        page.goto(f"{base}{BASE}/runs/{run_id}/")
        assert page.url.rstrip("/").endswith(f"/runs/{run_id}"), page.url
        page.get_by_role("button", name="Prepare reviewed apply\u2026").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        # step 2: operator intent - the EXACT sealed warning vocabulary +
        # the reason that will be SEALED into the review state
        for code in warnings:
            page.check(f'input[name="ack_warning_code"][value="{code}"]')  # type: ignore[attr-defined]
        page.fill("#apply-reason", signed_reason)  # type: ignore[attr-defined]
        page.get_by_role("button", name="Sign the sealed review").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        # final confirmation: explicit checkbox + the signed token only
        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.get_by_role("button", name="Apply the reviewed run").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        html = page.content()
        assert "committed" in html
        assert "already_committed" not in html
        # persisted outcome oracles: routes, application record, Core audit
        after = _route_count(database_url)
        assert after == before + 3, f"apply committed {after - before} route rows, expected 3"
        assert _count_apps(database_url, run_id) == 1
        superadmin_id, _ = _admin_ids(database_url, str(env217_browser["admin_email"]))
        audit_rows = _apply_audit_rows(database_url, run_id)
        assert len(audit_rows) == 1
        assert audit_rows[0][0] == superadmin_id
        assert audit_rows[0][1].get("run_id") == run_id
        # the honest status page (non-rotating read context)
        page.goto(f"{base}{BASE}/runs/{run_id}/apply-status")
        status_html = page.content()
        # the status page renders the ACTUAL authoritative record (durable
        # outcome facts + nonempty counts), not just the run id
        assert "Authoritative record" in status_html
        assert "committed (authoritative application record found)" in status_html
        rec_counts = _created_counts()
        assert rec_counts is not None and rec_counts["routes"] >= 3, rec_counts
        assert f"routes: {rec_counts['routes']}" in status_html
        assert f"pricing: {rec_counts['pricing']}" in status_html
        assert signed_reason in status_html
        assert "UNCONFIRMED until" not in status_html
        page.screenshot(path=str(SCREENSHOT_DIR / "217a-apply-committed.png"), full_page=True)  # type: ignore[attr-defined]
        # committed repeat: re-review the SAME run -> already_committed,
        # nothing new committed, the original audit row stays the only one
        page.goto(f"{base}{BASE}/runs/{run_id}/")
        page.get_by_role("button", name="Prepare reviewed apply\u2026").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        for code in warnings:
            page.check(f'input[name="ack_warning_code"][value="{code}"]')  # type: ignore[attr-defined]
        page.fill(  # type: ignore[attr-defined]
            "#apply-reason", "217-a browser committed repeat: the same reviewed plan is re-applied"
        )
        page.get_by_role("button", name="Sign the sealed review").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.get_by_role("button", name="Apply the reviewed run").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        assert "already_committed" in page.content()
        assert _route_count(database_url) == after
        assert _count_apps(database_url, run_id) == 1
        assert len(_apply_audit_rows(database_url, run_id)) == 1
    finally:
        page.close()


# ---------------------------------------------------------------------------
# 4. artifact download, then SAME-page verify (non-rotating read context)
# ---------------------------------------------------------------------------


def test_artifact_download_then_same_page_verify(env217_browser: dict[str, Any], chromium: object) -> None:
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        base = str(env217_browser["base_url"])
        _login(page, base, str(env217_browser["admin_email"]))
        run_id = str(env217_browser["collect_run_id"])
        page.goto(f"{base}{BASE}/runs/{run_id}/")
        with page.expect_download() as download_info:  # type: ignore[attr-defined]
            page.click(  # type: ignore[attr-defined]
                f'a[href="/admin/operations/catalog/runs/{run_id}/artifact/catalog-refresh.json"]'
            )
        download = download_info.value
        assert download.suggested_filename == "catalog-refresh.json"
        body = Path(download.path()).read_bytes()  # type: ignore[attr-defined]
        assert json.loads(body)["run_id"] == run_id
        # the SAME page's verify form (original token) still works after
        # the authenticated download: non-rotating read context
        page.click(  # type: ignore[attr-defined]
            f'form[action="/admin/operations/catalog/runs/{run_id}/verify"] button[type="submit"]'
        )
        page.wait_for_load_state("networkidle")
        html = page.content()
        assert "Explicit verification:" in html
        assert "NOT verify cleanly" not in html
    finally:
        page.close()


# ---------------------------------------------------------------------------
# 5. queued proposal: closed package listing/download/import previews
# ---------------------------------------------------------------------------


def test_proposal_package_and_import_previews(env217_browser: dict[str, Any], chromium: object) -> None:
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        base = str(env217_browser["base_url"])
        settings: Settings = env217_browser["settings"]
        _login(page, base, str(env217_browser["admin_email"]))
        page.goto(f"{base}{BASE}/proposals")
        page.select_option("#prop-provider-scope", "openrouter")  # type: ignore[attr-defined]
        page.check('input[name="endpoint_scope"][value="chat_completions"]')  # type: ignore[attr-defined]
        page.check('input[name="source_method"][value="docs"]')  # type: ignore[attr-defined]
        page.fill("#prop-fetch-details", "0")  # type: ignore[attr-defined]
        page.check('input[name="package_name"][value="openrouter-chat-text"]')  # type: ignore[attr-defined]
        page.get_by_role("button", name="Generate proposal").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        assert "broker acknowledged" in page.content()
        row = _wait_job(settings, "proposal")
        assert row["status"] in ("ready", "warnings"), row

        page.goto(f"{base}{BASE}/proposals")
        html = page.content()
        assert "Generated packages" in html
        assert "openrouter-chat-text" in html
        # the package section renders in a collapsed <details>: expand it
        # like an operator would, then act on the real links
        page.click('summary:has-text("openrouter-chat-text")')  # type: ignore[attr-defined]
        # real package file download through the closed preset selector
        with page.expect_download() as dl:  # type: ignore[attr-defined]
            page.click('a[href$="/package/openrouter-chat-text/routes-proposal.tsv"]')  # type: ignore[attr-defined]
        pkg = Path(dl.value.path()).read_bytes().decode("utf-8")  # type: ignore[attr-defined]
        assert "requested_model" in pkg and "synth/alpha" in pkg
        # the package TSV bridges to the EXISTING import previews (no
        # automatic import)
        page.click(  # type: ignore[attr-defined]
            'form[action$="/package/openrouter-chat-text/import-preview/routes"] button[type="submit"]'
        )
        page.wait_for_load_state("networkidle")
        assert "synth/alpha" in page.content()
        page.goto(f"{base}{BASE}/proposals")
        # the fresh proposals page renders the package in a COLLAPSED
        # <details> again: re-expand it like an operator would before
        # acting on the pricing preview link
        page.click('summary:has-text("openrouter-chat-text")')  # type: ignore[attr-defined]
        page.click(  # type: ignore[attr-defined]
            'form[action$="/package/openrouter-chat-text/import-preview/pricing"] button[type="submit"]'
        )
        page.wait_for_load_state("networkidle")
        pricing_html = page.content()
        assert "synth/alpha" in pricing_html
        assert "USD" in pricing_html  # non-empty per-M pricing rows
        page.goto(f"{base}{BASE}/proposals")
        page.screenshot(path=str(SCREENSHOT_DIR / "217a-proposals-desktop.png"), full_page=True)  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# 5. independent supplied bundle: published under its SUPPLIED run id
# ---------------------------------------------------------------------------


def test_supplied_bundle_review_published_under_supplied_id(
    env217_browser: dict[str, Any], chromium: object, tmp_path: Path
) -> None:
    settings: Settings = env217_browser["settings"]
    run_id = str(env217_browser["collect_run_id"])
    capture, handle = custody.load_run_capture(settings, run_id)
    try:
        bundle_bytes = capture.content["catalog-refresh.json"]
    finally:
        handle.close()
    # TEST SETUP constructs a deliberately independent input fixture: a
    # fresh explicit test run_id assigned BEFORE upload. Production
    # preserves whatever input id it receives (NEW-ONLY publication).
    bundle = json.loads(bundle_bytes)
    supplied_run_id = "browser-review-" + uuid.uuid4().hex[:24]
    bundle["run_id"] = supplied_run_id
    supplied = (
        json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    bundle_file = tmp_path / "supplied-bundle.json"
    bundle_file.write_bytes(supplied)
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        base = str(env217_browser["base_url"])
        _login(page, base, str(env217_browser["admin_email"]))
        page.goto(f"{base}{BASE}/review")
        page.set_input_files("#review-bundle", str(bundle_file))  # type: ignore[attr-defined]
        page.get_by_role("button", name="Seal and review").click()  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        assert "broker acknowledged" in page.content()
        row = _wait_job(settings, "review_supplied")
        assert row["status"] in ("ready", "warnings"), row
        # published under the SUPPLIED id (independent of the collect run)
        runs = {r["run_id"] for r in custody.list_runs(settings)}
        assert supplied_run_id in runs
        page.goto(f"{base}{BASE}/runs/{supplied_run_id}/")
        html = page.content()
        assert supplied_run_id in html
        assert "READY" in html
        page.screenshot(path=str(SCREENSHOT_DIR / "217a-review-run-desktop.png"), full_page=True)  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# 6. keyboard-only submit, narrow layout, no-JS operator flow
# ---------------------------------------------------------------------------


def test_narrow_keyboard_and_no_js(env217_browser: dict[str, Any], chromium: object) -> None:
    base = str(env217_browser["base_url"])
    settings: Settings = env217_browser["settings"]
    # keyboard-only submit of the export-baseline form (a real, bounded,
    # read-only queued job): Tab until the submit button is focused, then
    # Enter - no mouse anywhere
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, base, str(env217_browser["admin_email"]))
        page.goto(f"{base}{BASE}/export-baseline")
        focused: dict[str, str] = {}
        for _ in range(80):
            page.keyboard.press("Tab")  # type: ignore[attr-defined]
            focused = page.evaluate(  # type: ignore[attr-defined]
                "() => ({tag: document.activeElement.tagName,"
                " text: (document.activeElement.textContent || '').trim()})"
            )
            if focused.get("tag") == "BUTTON" and focused.get("text") == "Export baseline":
                break
        assert focused.get("text") == "Export baseline", focused
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        assert "broker acknowledged" in page.content()
        row = _wait_job(settings, "export_baseline")
        assert row["status"] == "ready", row
        # narrow layout on the SAME (still logged-in) page
        run_id = str(env217_browser["collect_run_id"])
        for path in (
            "/",
            "/collect",
            "/proposals",
            f"/runs/{run_id}/",
            f"/runs/{run_id}/apply-status",
        ):
            page.goto(f"{base}{BASE}{path}")  # type: ignore[attr-defined]
            page.set_viewport_size(NARROW)  # type: ignore[attr-defined]
            width = page.evaluate("document.documentElement.scrollWidth")  # type: ignore[attr-defined]
            assert width <= NARROW["width"] + 10, (path, _widest_overflow(page))
        page.goto(f"{base}{BASE}/collect")
        page.screenshot(path=str(SCREENSHOT_DIR / "217a-collect-narrow.png"))  # type: ignore[attr-defined]
    finally:
        page.close()
    # no-JS operator flow: server-rendered login/index remain usable AND a
    # REAL read-only operation (the export-baseline form POST - a plain
    # HTML form, no JavaScript) dispatches and completes
    context = chromium.new_context(viewport=DESKTOP, java_script_enabled=False)  # type: ignore[union-attr]
    try:
        jsless = context.new_page()
        jsless.goto(f"{base}/admin/login")
        jsless.fill(f'{LOGIN_FORM} input[name="email"]', str(env217_browser["admin_email"]))
        jsless.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)
        jsless.click(f"{LOGIN_FORM} button[type='submit']")
        jsless.wait_for_url("**/admin")
        jsless.goto(f"{base}{BASE}/")
        assert "Catalog refresh" in jsless.content()
        jsless.goto(f"{base}{BASE}/collect")
        assert 'id="catalog-collect-form"' in jsless.content()
        jsless.goto(f"{base}{BASE}/export-baseline")
        # the header carries a logout form with its own submit button;
        # target the export form's submit specifically (no-JS submit)
        jsless.click('form[action$="/export-baseline/submit"] button[type="submit"]')
        jsless.wait_for_load_state("networkidle")
        assert "broker acknowledged" in jsless.content()
        row = _wait_job(settings, "export_baseline")
        assert row["status"] == "ready", row
    finally:
        context.close()
