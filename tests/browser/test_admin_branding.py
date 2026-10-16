"""Actual-browser operator-branding evidence for 187-a (V2).

Reuses the already-qualified owned PostgreSQL fixture from the lazy-
throttling integration module (owned/label/loopback/tmpfs container,
identity verified before use, exact-ID cleanup) and the existing admin
browser pattern (Playwright Chromium + owned uvicorn app). The app is
configured with explicit synthetic HMAC, one-time-encryption, and
admin-session secrets; no ambient database URL or protected host
environment value is trusted.

Coverage:

- disabled (unset) defaults on desktop and at the 375px mobile
  breakpoint, where the packaged logo must stay visible;
- enabled custom fixture: all five slots render, operator CSS is loaded
  after and applied over the packaged styles (computed change), and the
  wide/compact selection switches at the 480px breakpoint by computed
  visibility;
- live refresh without restart, including a same-size/same-mtime
  replacement, and per-slot fallback on removal/invalidity;
- public asset routes are total, set no cookies, and expose no
  protected pages;
- CSRF-protected login, session, and the authenticated dashboard still
  function with branding active.

Safety: only asset bytes, opaque IDs, and computed styles are asserted.
Session and CSRF values are used only transiently to submit the login
form and are never logged or screenshotted.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import Owner
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# Reuse the already-qualified owned, labeled, loopback-bound, tmpfs-backed
# PostgreSQL fixture (never an ambient TEST_DATABASE_URL fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

# Re-export the integration module's qualified fixture under the expected
# fixture name for this module's tests.
owned_pg_url = _owned_pg_url_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]
CUSTOM = REPO_ROOT / "tests" / "fixtures" / "branding" / "custom"
PACKAGED_LOGO = REPO_ROOT / "app" / "slaif_gateway" / "web" / "static" / "img" / "slaif-logo.svg"
PACKAGED_LOGO_URL = "/admin/static/img/slaif-logo.svg"
PACKAGED_CSS_URL = "/admin/static/css/admin.css"

ADMIN_PASSWORD = "correct horse battery staple"
DEFAULT_BODY_BG = "rgb(247, 248, 250)"
CUSTOM_BODY_BG = "rgb(31, 45, 61)"
CUSTOM_H1_COLOR = "rgb(215, 242, 110)"
LOGIN_FORM = 'form[action="/admin/login"]'
OWNER_FORM = 'form[action="/admin/owners/new"]'


@contextmanager
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
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("Uvicorn server thread exited before startup")
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for Uvicorn server startup")
            time.sleep(0.05)
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_in_thread(coro):
    """Run a DB coroutine on an owned worker loop (Playwright owns the
    main-thread loop), re-raising the original exception verbatim."""
    result: dict[str, object] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised verbatim
            result["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=60)
    assert not thread.is_alive(), "DB helper thread did not finish"
    if "error" in result:
        raise result["error"]
    return result["value"]


@contextmanager
def _chromium_browser() -> Iterator[object]:
    playwright_sync = pytest.importorskip("playwright.sync_api")
    manager = playwright_sync.sync_playwright()
    playwright = manager.start()
    try:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")
        try:
            yield browser
        finally:
            browser.close()
    finally:
        playwright.stop()


def _settings(database_url: str, branding_dir: Path | None = None) -> Settings:
    # Explicit synthetic key material for this test app only.
    values: dict[str, object] = {
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ACTIVE_HMAC_KEY_VERSION": "1",
        "TOKEN_HMAC_SECRET_V1": generate_secret_key(),
        "ADMIN_SESSION_SECRET": generate_secret_key(),
        "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
        "ENABLE_EMAIL_DELIVERY": False,
    }
    if branding_dir is not None:
        values["SLAIF_BRANDING_DIR"] = str(branding_dir)
    return Settings(**values)


async def _seed_admin(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    try:
        async with session_factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"branding-admin-{suffix}@example.org",
                    display_name="Branding Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                return {"admin_email": admin.email}
    finally:
        await engine.dispose()


async def _owner_rows(database_url: str, email: str) -> list[Owner]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(Owner).where(Owner.email == email))
            return list(result.scalars())
    finally:
        await engine.dispose()


def _copy_custom_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "branding"
    shutil.copytree(CUSTOM, target)
    return target


def _login(page: object, data: dict[str, object]) -> None:
    response = page.goto("/admin/login")  # type: ignore[attr-defined]
    assert response is not None
    assert response.status == 200
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(data["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _computed(page: object, selector: str, property_name: str) -> str:
    return page.locator(selector).evaluate(  # type: ignore[attr-defined]
        f"(el) => getComputedStyle(el).{property_name}"
    )


def _assert_asset_response(page: object, slot: str, content_type: str, body: bytes) -> None:
    response = page.request.get(f"/admin/branding/{slot}")  # type: ignore[attr-defined]
    assert response.status == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in response.headers
    assert response.body() == body
    assert b"<html" not in response.body().lower()


@pytest.mark.playwright
def test_admin_branding_disabled_defaults_and_public_assets(owned_pg_url: str) -> None:
    """Disabled/unset: packaged defaults on desktop and 375px mobile,
    total fallback asset routes, and working CSRF login."""
    data = _run_in_thread(_seed_admin(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        try:
            page.goto("/admin/login")
            assert page.locator("img.auth-logo").count() == 1
            assert page.locator("img.auth-logo").get_attribute("src") == PACKAGED_LOGO_URL
            assert page.locator("img.brand-logo-compact").count() == 0
            assert page.locator("img.auth-hero").count() == 0
            assert page.locator('link[href="/admin/branding/style.css"]').count() == 0
            assert page.locator('link[rel="icon"]').get_attribute("href") == PACKAGED_LOGO_URL
            assert "branding-active" not in page.content()
            assert _computed(page, "body", "backgroundColor") == DEFAULT_BODY_BG
            assert page.locator("img.auth-logo").is_visible()

            # Public asset routes are total when disabled: fallback bytes,
            # correct MIME, no cookies, no protected content.
            packaged = PACKAGED_LOGO.read_bytes()
            _assert_asset_response(page, "style.css", "text/css", b"")
            for slot in ("logo", "logo-compact", "favicon", "hero"):
                _assert_asset_response(page, slot, "image/svg+xml", packaged)
            assert page.request.get("/admin/branding/other.css").status == 404

            # Mobile breakpoint: the packaged logo must stay visible.
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            assert _computed(page, "img.auth-logo", "display") != "none"
            assert page.locator("img.auth-logo").is_visible()

            # CSRF-protected login and the authenticated dashboard still work.
            _login(page, data)
            assert page.locator("img.brand-logo").first.get_attribute("src") == PACKAGED_LOGO_URL
        finally:
            page.close()
            context.close()


@pytest.mark.playwright
def test_admin_branding_enabled_all_slots_desktop_and_mobile(
    owned_pg_url: str, tmp_path: Path
) -> None:
    """Enabled custom fixture: all five slots, CSS applied after packaged
    styles, and the 480px wide/compact switch by computed visibility."""
    branding = _copy_custom_fixture(tmp_path)
    data = _run_in_thread(_seed_admin(owned_pg_url))
    app = create_app(_settings(owned_pg_url, branding_dir=branding))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        requested: list[str] = []
        context.on("request", lambda req: requested.append(req.url))  # type: ignore[arg-type]
        page = context.new_page()
        try:
            page.goto("/admin/login")
            # Operator CSS is loaded after the packaged stylesheet and wins.
            links = page.eval_on_selector_all(  # type: ignore[attr-defined]
                "head link", "els => els.map(e => e.getAttribute('href'))"
            )
            assert links.index(PACKAGED_CSS_URL) < links.index("/admin/branding/style.css")
            assert _computed(page, "body", "backgroundColor") == CUSTOM_BODY_BG
            assert _computed(page, ".auth-panel h1", "color") == CUSTOM_H1_COLOR

            # Wide visible / compact hidden on desktop, each at its slot.
            assert page.locator("img.auth-logo").get_attribute("src") == "/admin/branding/logo"
            assert page.locator("img.auth-logo").is_visible()
            compact = "img.brand-logo-compact"
            assert page.locator(compact).get_attribute("src") == "/admin/branding/logo-compact"
            assert _computed(page, compact, "display") == "none"

            # Hero + favicon overrides.
            assert page.locator("img.auth-hero").get_attribute("src") == "/admin/branding/hero"
            assert page.locator("img.auth-hero").is_visible()
            assert page.locator('link[rel="icon"]').get_attribute("href") == "/admin/branding/favicon"

            # Served asset bytes are exactly the operator fixture bytes.
            _assert_asset_response(page, "style.css", "text/css", (CUSTOM / "style.css").read_bytes())
            for slot, fixture, mime in (
                ("logo", "logo.svg", "image/svg+xml"),
                ("logo-compact", "logo-compact.png", "image/png"),
                ("favicon", "favicon.png", "image/png"),
                ("hero", "hero.svg", "image/svg+xml"),
            ):
                _assert_asset_response(page, slot, mime, (CUSTOM / fixture).read_bytes())
            for path in (
                "/admin/branding/style.css",
                "/admin/branding/logo",
                "/admin/branding/logo-compact",
                "/admin/branding/hero",
            ):
                assert any(path in url for url in requested), path
            # Headless engines may not issue the tab-icon request; the DOM
            # link href/type plus the explicit MIME/bytes checks above
            # qualify the favicon integration. Poll briefly and record the
            # observation rather than force the automatic fetch.
            favicon_requested = False
            deadline = time.monotonic() + 3
            while not favicon_requested:
                if time.monotonic() > deadline:
                    break
                favicon_requested = any(
                    "/admin/branding/favicon" in url for url in requested
                )
                if not favicon_requested:
                    time.sleep(0.1)
            print(f"FAVICON_AUTOMATIC_FETCH={str(favicon_requested).lower()}")

            # Mobile breakpoint: compact shown, wide hidden, CSS still applied.
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            assert _computed(page, "img.auth-logo", "display") == "none"
            assert _computed(page, compact, "display") != "none"
            assert page.locator(compact).is_visible()
            assert _computed(page, "body", "backgroundColor") == CUSTOM_BODY_BG

            # Login and the authenticated dashboard still work with branding.
            _login(page, data)
            assert page.locator("img.brand-logo").first.get_attribute("src") == "/admin/branding/logo"

            # Actual authenticated admin form mutation: create an owner.
            owner_email = f"owner-{uuid.uuid4().hex[:12]}@example.org"
            assert _run_in_thread(_owner_rows(owned_pg_url, owner_email)) == []
            page.goto("/admin/owners/new")
            # This page carries branding in <head> (favicon + CSS), not a logo lockup.
            assert 'href="/admin/branding/style.css"' in page.content()
            assert 'href="/admin/branding/favicon"' in page.content()
            page.fill(f'{OWNER_FORM} input[name="name"]', "Branding")
            page.fill(f'{OWNER_FORM} input[name="surname"]', "Owner")
            page.fill(f'{OWNER_FORM} input[name="email"]', owner_email)
            page.fill(f'{OWNER_FORM} textarea[name="reason"]', "branding browser: owner create")
            page.click(f'{OWNER_FORM} button[type="submit"]')
            page.wait_for_url("**/admin/owners/*")
            rows = _run_in_thread(_owner_rows(owned_pg_url, owner_email))
            assert len(rows) == 1
            assert rows[0].name == "Branding"
            assert rows[0].surname == "Owner"

            # A bad CSRF attempt is refused and leaves state unchanged.
            rejected_email = f"owner-{uuid.uuid4().hex[:12]}@example.org"
            bad = page.request.post(  # type: ignore[attr-defined]
                "/admin/owners/new",
                form={
                    "csrf_token": "invalid",
                    "name": "Bad",
                    "surname": "Csrf",
                    "email": rejected_email,
                    "reason": "branding browser: bad csrf",
                },
                max_redirects=0,
            )
            assert bad.status == 400
            assert _run_in_thread(_owner_rows(owned_pg_url, rejected_email)) == []
        finally:
            page.close()
            context.close()


@pytest.mark.playwright
def test_admin_branding_live_refresh_and_fallback(owned_pg_url: str, tmp_path: Path) -> None:
    """No-restart refresh, same-size/same-mtime pickup, and per-slot
    fallback on removal or invalid content."""
    branding = _copy_custom_fixture(tmp_path)
    app = create_app(_settings(owned_pg_url, branding_dir=branding))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        try:
            page.goto("/admin/login")
            assert _computed(page, "body", "backgroundColor") == CUSTOM_BODY_BG

            # A changed file is picked up on reload without restart.
            first = "body { background-color: #223344; }\n"
            (branding / "style.css").write_text(first)
            page.reload()
            assert _computed(page, "body", "backgroundColor") == "rgb(34, 51, 68)"

            # A same-size/same-mtime replacement is picked up as well.
            before = (branding / "style.css").stat()
            second = "body { background-color: #556677; }\n"
            assert len(second.encode()) == before.st_size
            (branding / "style.css").write_text(second)
            os.utime(branding / "style.css", ns=(before.st_atime_ns, before.st_mtime_ns))
            page.reload()
            assert _computed(page, "body", "backgroundColor") == "rgb(85, 102, 119)"

            # Removing the stylesheet restores the packaged default.
            (branding / "style.css").unlink()
            page.reload()
            assert _computed(page, "body", "backgroundColor") == DEFAULT_BODY_BG

            # An invalid logo falls back per slot; the valid compact PNG
            # override is unaffected.
            (branding / "logo.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
            )
            page.reload()
            assert page.locator("img.auth-logo").get_attribute("src") == PACKAGED_LOGO_URL
            assert page.locator("img.brand-logo-compact").get_attribute("src") == (
                "/admin/branding/logo-compact"
            )
            assert page.request.get("/admin/branding/logo").body() == PACKAGED_LOGO.read_bytes()
        finally:
            page.close()
            context.close()
