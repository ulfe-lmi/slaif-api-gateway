"""Native-browser SLAIF visual design evidence for 188-a (V2/V3/V4).

Reuses the already-qualified owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL fixture (never an ambient URL) and the existing uvicorn +
Playwright Chromium pattern. The app is configured with explicit synthetic
HMAC, one-time-encryption, and admin-session secrets; no ambient database
URL or protected host environment value is trusted.

Coverage:

- default theme: shared shell (header brand lockup, section navigation,
  footer, skip link), packaged local font faces actually loaded with
  pinned HTTP bytes, and the exact cream/teal/blue computed palette;
- keyboard compact menu (expanded state, Escape, focus return) at 375px
  and usable no-JS navigation at 375px;
- labeled, keyboard-focusable table regions and no horizontal page
  overflow at 375px;
- alternate operator theme: coordinated readable foreground/background
  pairs on primary/secondary controls and selects (computed contrast
  >= 4.5:1) plus the wide/compact 480px selection;
- branded standalone 400/404 error surfaces preserving status/message,
  unauthenticated redirect, owner-create form flow with validation and
  bad-CSRF refusal (state unchanged), and the unchanged JSON /v1 error
  contract.

Safety: only synthetic data, opaque IDs, asset bytes, and computed styles
are asserted. Session and CSRF values are used only transiently to submit
forms and are never logged or screenshotted; no one-time-key result
screen is captured; no real provider calls occur.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey, Owner
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
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
PACKAGED_LOGO_URL = "/admin/static/img/slaif-logo.svg"
PACKAGED_CSS_URL = "/admin/static/css/admin.css"

ADMIN_PASSWORD = "correct horse battery staple"

DEFAULT_BODY_BG = "rgb(251, 251, 249)"
DEFAULT_HEADING_COLOR = "rgb(22, 48, 46)"
DEFAULT_ACCENT = "rgb(8, 108, 134)"

ALT_BODY_BG = "rgb(16, 28, 44)"
ALT_H1_COLOR = "rgb(244, 211, 94)"
ALT_PRIMARY_BG = "rgb(232, 185, 59)"
ALT_PRIMARY_FG = "rgb(16, 28, 44)"
ALT_SECONDARY_BG = "rgb(24, 44, 68)"
ALT_SECONDARY_FG = "rgb(232, 185, 59)"
ALT_CONTROL_BG = "rgb(24, 44, 68)"
ALT_CONTROL_FG = "rgb(232, 238, 245)"

FONT_SHA256 = {
    "Roboto.ttf": "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134",
    "RobotoCondensed.ttf": "dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0",
}


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


async def _seed_design_data(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    try:
        async with session_factory() as session:
            async with session.begin():
                # A long local part keeps the 375px dashboard identity line
                # a genuine overflow regression (R3).
                long_local = f"{suffix}{uuid.uuid4().hex}"
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"design-admin-{long_local}@example.org",
                    display_name="Design Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"Design Institution {suffix}",
                    country="SI",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"Design Cohort {suffix}",
                    description="safe design cohort",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Design",
                    surname="Owner",
                    email=f"design-owner-{suffix}@example.org",
                    institution_id=institution.id,
                )
                key = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"design-{suffix[:16]}",
                    token_hash=f"token_hash_design_secret_{suffix}",
                    owner_id=owner.id,
                    cohort_id=cohort.id,
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                    key_hint="sk-slaif-design-hint",
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=1000,
                    request_limit_total=100,
                    allow_all_models=True,
                    allow_all_endpoints=True,
                    created_by_admin_user_id=admin.id,
                )
                return {
                    "admin_email": admin.email,
                    "key_public_id": key.public_key_id,
                }
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


async def _gateway_key_rows(database_url: str) -> list[GatewayKey]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(GatewayKey))
            return list(result.scalars())
    finally:
        await engine.dispose()


def _login(page: object, data: dict[str, object]) -> None:
    response = page.goto("/admin/login")  # type: ignore[attr-defined]
    assert response is not None
    assert response.status == 200
    page.fill('form[action="/admin/login"] input[name="email"]', str(data["admin_email"]))  # type: ignore[attr-defined]
    page.fill('form[action="/admin/login"] input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click('form[action="/admin/login"] button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")


def _computed(page: object, selector: str, property_name: str) -> str:
    return page.locator(selector).evaluate(  # type: ignore[attr-defined]
        f"(el) => getComputedStyle(el).{property_name}"
    )


def _rgb_parts(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"rgb\((\d+), (\d+), (\d+)\)", value.strip())
    assert match, value
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _contrast_ratio(color_a: str, color_b: str) -> float:
    def lin(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def luminance(color: tuple[int, int, int]) -> float:
        r, g, b = color
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    a, b = luminance(_rgb_parts(color_a)), luminance(_rgb_parts(color_b))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _assert_no_horizontal_overflow(page: object, width: int) -> None:
    scroll_width = page.evaluate("document.documentElement.scrollWidth")  # type: ignore[attr-defined]
    assert scroll_width <= width, (scroll_width, width)


def _shot(page: object, outdir: Path, name: str) -> Path:
    """Wait for font/paint readiness, then capture into the per-test dir."""
    outdir.mkdir(parents=True, exist_ok=True)
    page.evaluate("document.fonts.ready.then(() => true)")  # type: ignore[attr-defined]
    path = outdir / name
    page.screenshot(path=str(path))  # type: ignore[attr-defined]
    return path


@pytest.mark.playwright
def test_design_default_theme_shell_fonts_navigation_and_tables(owned_pg_url: str, tmp_path: Path) -> None:
    """Default theme: shell, local fonts (bytes + load), palette, readable
    control pairs, section navigation, named focusable table region
    (incl. 768 tablet), keyboard menu, and mobile login/table surfaces."""
    data = _run_in_thread(_seed_design_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        try:
            page.goto("/admin/login")
            page.evaluate("document.fonts.ready.then(() => true)")

            # Exact default palette on the login surface.
            assert _computed(page, "body", "backgroundColor") == DEFAULT_BODY_BG
            assert _computed(page, "h1", "color") == DEFAULT_HEADING_COLOR
            submit_selector = "form[action='/admin/login'] button[type='submit']"
            assert _computed(page, submit_selector, "backgroundColor") == DEFAULT_ACCENT
            assert _contrast_ratio(
                _computed(page, submit_selector, "color"),
                _computed(page, submit_selector, "backgroundColor"),
            ) >= 4.5

            # Local packaged fonts are declared, loaded, and byte-exact.
            assert page.evaluate("document.fonts.check('16px Roboto')") is True
            assert page.evaluate(r"document.fonts.check('16px \"Roboto Condensed\"')") is True
            for name, expected in FONT_SHA256.items():
                response = page.request.get(f"/admin/static/fonts/{name}")
                assert response.status == 200
                assert hashlib.sha256(response.body()).hexdigest() == expected, name

            # Shared shell: brand lockup, footer, skip link, no nav pre-auth.
            assert page.locator("img.admin-header-logo").is_visible()
            assert page.locator("img.admin-header-logo").get_attribute("src") == PACKAGED_LOGO_URL
            assert page.locator(".admin-footer").count() == 1
            assert page.locator(".skip-link").count() == 1
            assert page.locator("#admin-nav").count() == 0
            _assert_no_horizontal_overflow(page, 1440)
            _shot(page, tmp_path, "design-default-login-1440.png")

            # 375 login (still anonymous): the real mobile login surface.
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            page.evaluate("document.fonts.ready.then(() => true)")
            _assert_no_horizontal_overflow(page, 375)
            _shot(page, tmp_path, "design-default-login-375.png")

            # Authenticated at 1440: section navigation with the current section.
            page.set_viewport_size({"width": 1440, "height": 900})
            _login(page, data)
            nav = page.locator("#admin-nav a")
            assert nav.count() == 14
            assert page.locator('#admin-nav a[aria-current="page"]').inner_text() == "Dashboard"
            _shot(page, tmp_path, "design-default-dashboard-1440.png")

            # 375 dashboard: the long identity line wraps, no overflow (R3).
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            _assert_no_horizontal_overflow(page, 375)
            _shot(page, tmp_path, "design-default-dashboard-375.png")
            page.set_viewport_size({"width": 1440, "height": 900})
            page.reload()

            # Keys table: labeled, focusable NAMED region with the row.
            page.goto(f"/admin/keys?public_key_id={data['key_public_id']}")
            assert page.locator('#admin-nav a[aria-current="page"]').inner_text() == "Keys"
            wrap = page.locator(".table-wrap")
            assert wrap.count() == 1
            assert wrap.get_attribute("role") == "region"
            assert wrap.get_attribute("tabindex") == "0"
            assert wrap.get_attribute("aria-label") == "Gateway keys"
            assert page.locator(".table-wrap a[href^='/admin/keys/']").count() == 1

            # Default-theme control pairs stay readable (>= 4.5:1).
            primary_selector = 'a.button-link[href="/admin/keys/create"]'
            secondary_selector = 'a.button-link.secondary[href="/admin/keys/bulk-import"]'
            select_selector = 'form.filter-bar[action="/admin/keys"] select[name="status"]'
            assert _computed(page, primary_selector, "backgroundColor") == DEFAULT_ACCENT
            for selector in (primary_selector, secondary_selector, select_selector):
                assert _contrast_ratio(
                    _computed(page, selector, "color"),
                    _computed(page, selector, "backgroundColor"),
                ) >= 4.5, selector
            _assert_no_horizontal_overflow(page, 1440)
            _shot(page, tmp_path, "design-default-keys-1440.png")

            # Key detail: safe metadata surface, no plaintext material.
            detail_href = page.locator(".table-wrap a[href^='/admin/keys/']").get_attribute("href")
            page.goto(detail_href)
            assert str(data["key_public_id"]) in page.locator("#key-heading").inner_text()
            _shot(page, tmp_path, "design-default-key-detail-1440.png")

            # Provider list review surface.
            page.goto("/admin/providers")
            assert page.locator("#providers-heading").inner_text() == "Provider Configs"
            _shot(page, tmp_path, "design-default-providers-1440.png")

            # 768 tablet: inline nav (no toggle) and the named region is
            # focusable; it scrolls when the table overflows.
            page.goto(f"/admin/keys?public_key_id={data['key_public_id']}")
            page.set_viewport_size({"width": 768, "height": 1024})
            page.reload()
            page.evaluate("document.fonts.ready.then(() => true)")
            assert page.locator(".nav-toggle").is_hidden()
            assert page.locator("#admin-nav").is_visible()
            _assert_no_horizontal_overflow(page, 768)
            wrap.focus()
            assert page.evaluate(
                "document.activeElement === document.querySelector('.table-wrap')"
            ) is True
            if wrap.evaluate("el => el.scrollWidth > el.clientWidth"):
                # Real keyboard scroll on the focused named region; no
                # programmatic scroll substitution.
                page.keyboard.press("ArrowRight")
                left = 0
                for _ in range(20):  # bounded wait, up to ~2s
                    left = wrap.evaluate("el => el.scrollLeft")
                    if left > 0:
                        break
                    page.wait_for_timeout(100)  # type: ignore[attr-defined]
                assert left > 0
            _shot(page, tmp_path, "design-default-keys-768.png")

            # 375 keys: compact keyboard menu (expanded state, Escape,
            # focus return) and no page overflow.
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            _assert_no_horizontal_overflow(page, 375)
            toggle = page.locator(".nav-toggle")
            assert toggle.is_visible()
            assert page.locator("#admin-nav").is_hidden()
            toggle.press("Enter")
            assert page.locator("#admin-nav").is_visible()
            assert toggle.get_attribute("aria-expanded") == "true"
            page.keyboard.press("Escape")
            assert page.locator("#admin-nav").is_hidden()
            assert toggle.get_attribute("aria-expanded") == "false"
            assert page.evaluate(
                "document.activeElement === document.querySelector('.nav-toggle')"
            ) is True
            _shot(page, tmp_path, "design-default-keys-375.png")

            # 375 key create: panels and controls stay inside the card.
            # Page-level no-overflow alone cannot catch card overflow.
            page.goto("/admin/keys/create")
            shell_box = page.locator(".dashboard-shell.wide").bounding_box()
            form_box = page.locator("form.create-form").bounding_box()
            assert form_box["x"] >= shell_box["x"] - 1
            assert form_box["x"] + form_box["width"] <= shell_box["x"] + shell_box["width"] + 1
            for panel in page.locator("form.create-form .action-panel").all():
                box = panel.bounding_box()
                assert box["x"] >= form_box["x"] - 1, "panel left outside form"
                assert box["x"] + box["width"] <= form_box["x"] + form_box["width"] + 1, (
                    "panel right outside form"
                )
            for control in page.locator(
                "form.create-form select, form.create-form input, form.create-form textarea, form.create-form button"
            ).all():
                cbox = control.bounding_box()
                if cbox is None:
                    continue
                assert cbox["x"] + cbox["width"] <= form_box["x"] + form_box["width"] + 1, (
                    "control right outside form"
                )
            _shot(page, tmp_path, "design-default-key-create-375.png")
        finally:
            page.close()
            context.close()


@pytest.mark.playwright
def test_design_no_javascript_navigation_usable(owned_pg_url: str) -> None:
    """Without JavaScript the wrapping nav remains visible and usable at
    375px (no .nav-ready collapse, no toggle), and forms still work."""
    data = _run_in_thread(_seed_design_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(
            base_url=base_url,
            viewport={"width": 375, "height": 812},
            java_script_enabled=False,
        )
        page = context.new_page()
        try:
            page.goto("/admin/login")
            assert "nav-ready" not in page.content()
            assert page.locator(".nav-toggle").count() == 0
            _assert_no_horizontal_overflow(page, 375)

            # No-JS login through the plain form.
            page.fill('form[action="/admin/login"] input[name="email"]', str(data["admin_email"]))  # type: ignore[attr-defined]
            page.fill('form[action="/admin/login"] input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
            page.click('form[action="/admin/login"] button[type="submit"]')  # type: ignore[attr-defined]
            page.wait_for_url("**/admin")

            # The section nav is a plain visible list on the dashboard.
            assert "nav-ready" not in page.content()
            assert page.locator("#admin-nav").is_visible()
            assert page.locator("#admin-nav a").count() == 14
            # Without JavaScript the signed-in toggle button stays hidden.
            assert page.locator(".nav-toggle").is_hidden()
            page.click("#admin-nav a[href='/admin/owners']")
            page.wait_for_url("**/admin/owners")
            assert page.locator("#admin-nav a[aria-current='page']").inner_text() == "Owners"
            _assert_no_horizontal_overflow(page, 375)

            # 768 tablet: the wrapping nav is visible inline, no toggle.
            page.set_viewport_size({"width": 768, "height": 1024})
            page.reload()
            assert "nav-ready" not in page.content()
            assert page.locator(".nav-toggle").is_hidden()
            assert page.locator("#admin-nav").is_visible()
            assert page.locator("#admin-nav a").count() == 14
            _assert_no_horizontal_overflow(page, 768)
        finally:
            page.close()
            context.close()


@pytest.mark.playwright
def test_design_alternate_theme_contrast_and_compact_selection(
    owned_pg_url: str, tmp_path: Path
) -> None:
    """Alternate operator theme: coordinated readable pairs (computed
    contrast >= 4.5:1) scoped to the real controls, mobile login, 768
    tablet, and the 480px wide/compact logo selection."""
    branding = tmp_path / "branding"
    shutil.copytree(CUSTOM, branding)
    data = _run_in_thread(_seed_design_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url, branding_dir=branding))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        try:
            page.goto("/admin/login")
            page.evaluate("document.fonts.ready.then(() => true)")

            # Operator CSS is loaded after the packaged stylesheet and wins.
            links = page.eval_on_selector_all(  # type: ignore[attr-defined]
                "head link", "els => els.map(e => e.getAttribute('href'))"
            )
            assert links.index(PACKAGED_CSS_URL) < links.index("/admin/branding/style.css")
            assert _computed(page, "body", "backgroundColor") == ALT_BODY_BG
            assert _computed(page, "h1", "color") == ALT_H1_COLOR
            assert page.locator("img.admin-header-logo").get_attribute("src") == "/admin/branding/logo"
            _assert_no_horizontal_overflow(page, 1440)
            _shot(page, tmp_path, "design-alt-login-1440.png")

            # 375 login: the real mobile login surface under the operator theme.
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            page.evaluate("document.fonts.ready.then(() => true)")
            _assert_no_horizontal_overflow(page, 375)
            _shot(page, tmp_path, "design-alt-login-375.png")

            page.set_viewport_size({"width": 1440, "height": 900})
            _login(page, data)
            page.goto(f"/admin/keys?public_key_id={data['key_public_id']}")

            # Coordinated readable pairs, scoped to the actual controls.
            primary_selector = 'a.button-link[href="/admin/keys/create"]'
            secondary_selector = 'a.button-link.secondary[href="/admin/keys/bulk-import"]'
            select_selector = 'form.filter-bar[action="/admin/keys"] select[name="status"]'
            primary_bg = _computed(page, primary_selector, "backgroundColor")
            primary_fg = _computed(page, primary_selector, "color")
            assert primary_bg == ALT_PRIMARY_BG
            assert primary_fg == ALT_PRIMARY_FG
            assert _contrast_ratio(primary_fg, primary_bg) >= 4.5

            secondary_bg = _computed(page, secondary_selector, "backgroundColor")
            secondary_fg = _computed(page, secondary_selector, "color")
            assert secondary_bg == ALT_SECONDARY_BG
            assert secondary_fg == ALT_SECONDARY_FG
            assert _contrast_ratio(secondary_fg, secondary_bg) >= 4.5

            control_bg = _computed(page, select_selector, "backgroundColor")
            control_fg = _computed(page, select_selector, "color")
            assert control_bg == ALT_CONTROL_BG
            assert control_fg == ALT_CONTROL_FG
            assert _contrast_ratio(control_fg, control_bg) >= 4.5

            # Body text against the navy page surface stays readable.
            assert _contrast_ratio(_computed(page, "body", "color"), ALT_BODY_BG) >= 4.5
            _assert_no_horizontal_overflow(page, 1440)

            # 768 tablet: inline nav, no toggle, no overflow.
            page.set_viewport_size({"width": 768, "height": 1024})
            page.reload()
            assert page.locator(".nav-toggle").is_hidden()
            assert page.locator("#admin-nav").is_visible()
            _assert_no_horizontal_overflow(page, 768)
            _shot(page, tmp_path, "design-alt-keys-768.png")

            # 375 keys: the compact logo replaces the wide one.
            page.set_viewport_size({"width": 375, "height": 812})
            page.reload()
            assert _computed(page, "img.admin-header-logo", "display") == "none"
            compact = page.locator("img.brand-logo-compact")
            assert compact.get_attribute("src") == "/admin/branding/logo-compact"
            assert _computed(page, "img.brand-logo-compact", "display") != "none"
            assert compact.is_visible()
            _assert_no_horizontal_overflow(page, 375)
            _shot(page, tmp_path, "design-alt-keys-375.png")
        finally:
            page.close()
            context.close()


@pytest.mark.playwright
def test_design_error_surfaces_owner_form_flow_and_v1_contract(owned_pg_url: str, tmp_path: Path) -> None:
    """Branded 400/404 error surfaces preserve status/message; the
    owner-create form flow works with existing reason/CSRF rules; the
    JSON /v1 error contract is unchanged.

    The 404/400 assertions run in an authenticated context because
    protected admin routes redirect anonymous visitors to login; the
    anonymous redirect is proven separately in a fresh browser context
    so no session cookie can leak into that assertion.
    """
    data = _run_in_thread(_seed_design_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        anon_context: object | None = None
        try:
            # Login first: protected error surfaces need a session.
            _login(page, data)

            # Branded 404: exact status and message on the shared surface.
            response = page.goto(f"/admin/keys/{uuid.uuid4()}")  # type: ignore[attr-defined]
            assert response.status == 404
            assert page.locator(".error-page").count() == 1
            assert "HTTP 404" in page.content()
            assert "Gateway key not found." in page.content()
            assert page.locator(".admin-header img.admin-header-logo").count() == 1
            assert page.locator(".admin-footer").count() == 1
            _shot(page, tmp_path, "design-error-404-1440.png")

            # Branded 400 with the exact pre-188 message.
            response = page.goto("/admin/keys?institution_id=not-a-uuid")  # type: ignore[attr-defined]
            assert response.status == 400
            assert page.locator(".error-page").count() == 1
            assert "HTTP 400" in page.content()
            assert "Invalid filter." in page.content()

            # Unauthenticated access redirects (no HTML error page).
            anon_context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
            anon = anon_context.new_page()
            response = anon.goto("/admin/keys")  # type: ignore[attr-defined]
            assert response.status == 200
            assert anon.url.endswith("/admin/login")  # type: ignore[attr-defined]
            anon.close()  # type: ignore[attr-defined]

            # Owner-create: a genuine server-side validation refusal
            # first. "no-at-sign.example" satisfies the native required
            # check but the gateway parser rejects it, so the server
            # (not the browser) produces the 400 and flash error.
            rejected_email = "no-at-sign.example"
            page.goto("/admin/owners/new")  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] input[name="name"]', "Design")  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] input[name="surname"]', "Rejected")  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] input[name="email"]', rejected_email)  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] textarea[name="reason"]', "design: validation case")  # type: ignore[attr-defined]
            with page.expect_response(  # type: ignore[attr-defined]
                lambda r: r.url == f"{base_url}/admin/owners/new"
                and r.request.method == "POST"
            ) as info:
                page.click('form[action="/admin/owners/new"] button[type="submit"]')  # type: ignore[attr-defined]
            response = info.value
            assert response.status == 400
            assert page.url.endswith("/admin/owners/new")
            flash = page.locator(".admin-flash-error")
            assert flash.count() == 1
            assert "Owner email must be valid" in flash.inner_text()
            assert _run_in_thread(_owner_rows(owned_pg_url, rejected_email)) == []
            _shot(page, tmp_path, "design-owner-validation-error-1440.png")

            # A valid create with the existing reason/CSRF rules.
            created_email = f"design-created-{uuid.uuid4().hex[:12]}@example.org"
            page.fill('form[action="/admin/owners/new"] input[name="name"]', "Design")  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] input[name="surname"]', "Created")  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] input[name="email"]', created_email)  # type: ignore[attr-defined]
            page.fill('form[action="/admin/owners/new"] textarea[name="reason"]', "design: valid create")  # type: ignore[attr-defined]
            page.click('form[action="/admin/owners/new"] button[type="submit"]')  # type: ignore[attr-defined]
            page.wait_for_url("**/admin/owners/*")  # type: ignore[attr-defined]
            rows = _run_in_thread(_owner_rows(owned_pg_url, created_email))
            assert len(rows) == 1
            assert rows[0].name == "Design"

            # Bad CSRF: refusal with the exact message, no row created.
            csrf_rejected_email = f"design-csrf-{uuid.uuid4().hex[:12]}@example.org"
            bad = page.request.post(  # type: ignore[attr-defined]
                "/admin/owners/new",
                form={
                    "csrf_token": "invalid",
                    "name": "Design",
                    "surname": "Csrf",
                    "email": csrf_rejected_email,
                    "reason": "design: bad csrf",
                },
                max_redirects=0,
            )
            assert bad.status == 400
            assert "Invalid CSRF token." in bad.text()
            assert _run_in_thread(_owner_rows(owned_pg_url, csrf_rejected_email)) == []

            # The /v1 JSON error contract is untouched by the HTML surface.
            response = page.request.post(  # type: ignore[attr-defined]
                "/v1/chat/completions",
                data=json.dumps(
                    {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]}
                ),
                headers={"Content-Type": "application/json"},
            )
            assert response.status == 401
            assert response.headers["content-type"].startswith("application/json")
            body = response.text()
            assert "<!doctype" not in body.lower()
            assert '"error"' in body
        finally:
            page.close()
            context.close()
            if anon_context is not None:
                anon_context.close()  # type: ignore[attr-defined]
