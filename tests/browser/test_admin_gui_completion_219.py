"""219-a: focused real-Chromium qualification of the changed GUI seams.

Real browser, real uvicorn app, and ONE NEW owned labeled loopback tmpfs
PostgreSQL 16 (the qualified ``owned_pg_url`` fixture - never an ambient
database). No Redis/Celery, no upstream network, no real credentials.

Focused scope (whole-field inventory stays in the unit module; the full
G01-G18 matrix stays in the final installed workflow):

- create key page: the Policy Source section precedes the guided
  request-policy selector in the REAL DOM, the new owner/cohort record
  choices resolve their linked help in the real DOM, and the page stays
  inside a 420px viewport (captures);
- trusted-calibration key detail: every rendered ``key-*-help`` element
  resolves through real aria-describedby links (including the
  record-choice destination-ID rc-help span), and a KEYBOARD-ONLY flow
  performs a real external-tool policy update with a persisted audit;
- reviewed batch: the complete reviewed membership is a keyboard/no-JS
  ``<details>`` disclosure with the exact UUID count, and the Apply
  section is ordered ABOVE the per-key before/after table (real DOM
  order);
- calibration: KEYBOARD-ONLY preview, the safe JSON attachment downloads
  in the real browser, and the SAME displayed form token still creates
  the template (real-browser non-rotating CSRF proof); the no-JS
  operator performs the SAME end-to-end flow with native controls only.

Synthetic screenshots are stored under /tmp/slaif219 for operator/root
inspection.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    GatewayKey,
    KeyTemplate,
    UsageLedger,
    UsageProfile,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

pytestmark = pytest.mark.playwright

owned_pg_url = _owned_pg_url_fixture

SCREENSHOT_DIR = Path("/tmp/slaif219")
DESKTOP = {"width": 1440, "height": 900}
NARROW = {"width": 420, "height": 860}

ADMIN_PASSWORD = "219-browser-admin-pw-xK7"
EXT_TOOL_REASON = "219 keyboard external-tool strict reset"
NOJS_TEMPLATE_NAME = "219 nojs calibration template"
NOJS_TEMPLATE_REASON = "219 nojs calibration template creation"
JS_TEMPLATE_NAME = "219 keyboard calibration template"
JS_TEMPLATE_REASON = "219 keyboard calibration template creation"

PLAN_FORM = 'form[action="/admin/key-batch/plan"]'


# ---------------------------------------------------------------------------
# Real uvicorn (214/215/216/217/218 pattern)
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


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET=generate_secret_key(),
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


# ---------------------------------------------------------------------------
# Seed: fixture data only (direct ORM inserts, synthetic material)
# ---------------------------------------------------------------------------


def _key_kwargs(
    index: int, suffix: str, now: datetime, owner_id: uuid.UUID,
    cohort_id: uuid.UUID | None, admin_id: uuid.UUID,
) -> dict[str, Any]:
    return dict(
        public_key_id=f"219pg-{suffix}-{index:03d}",
        token_hash=f"219pg-hash-{suffix}-{index:03d}",
        owner_id=owner_id,
        cohort_id=cohort_id,
        status="active",
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        request_limit_total=1000,
        token_limit_total=5_000_000,
        cost_used_eur=Decimal(f"0.{100 + index}"),
        tokens_used_total=1000 + index * 7,
        requests_used_total=50 + index * 3,
        allow_all_models=True,
        allow_all_endpoints=True,
        created_by_admin_user_id=admin_id,
    )


async def _seed(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui219-{suffix}@example.org",
                    display_name="219 GUI Completion Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"219 Institute {suffix}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"219 Completion Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Completion",
                    surname="Seed",
                    email=f"owner-219-{suffix}@example.org",
                    institution_id=institution.id,
                )
                cohort_key_ids: list[uuid.UUID] = []
                for index in range(3):
                    key = GatewayKey(
                        **_key_kwargs(index, suffix, now, owner.id, cohort.id, admin.id)
                    )
                    session.add(key)
                    await session.flush()
                    cohort_key_ids.append(key.id)
                # Trusted calibration key (request limit required by the
                # product constraint) for the calibration + detail flows.
                trusted = GatewayKey(
                    **{
                        **_key_kwargs(3, suffix, now, owner.id, None, admin.id),
                        "key_purpose": "trusted_calibration",
                        "capability_policy_mode": "trusted_calibration_discovery",
                    }
                )
                session.add(trusted)
                await session.flush()
                # Real observed usage for the calibration key (fixture
                # rows; the calibration service reads profile rows only).
                for index in range(2):
                    ledger = UsageLedger(
                        request_id=f"219pg-req-{suffix}-{index}",
                        gateway_key_id=trusted.id,
                        owner_id=owner.id,
                        endpoint="/v1/chat/completions",
                        provider="openai",
                        requested_model="gpt-4.1-mini",
                        resolved_model="gpt-4.1-mini",
                        success=True,
                        accounting_status="finalized",
                        started_at=now,
                        finished_at=now,
                        input_tokens=100 + 20 * index,
                        output_tokens=50 + 10 * index,
                        total_tokens=150 + 30 * index,
                    )
                    session.add(ledger)
                    await session.flush()
                    session.add(
                        UsageProfile(
                            usage_ledger_id=ledger.id,
                            gateway_key_id=trusted.id,
                            owner_id=owner.id,
                            endpoint_path="/v1/chat/completions",
                            provider="openai",
                            requested_model="gpt-4.1-mini",
                            resolved_upstream_model="gpt-4.1-mini",
                            provider_host="api.openai.com",
                            provider_endpoint_path="/v1/chat/completions",
                            input_tokens=100 + 20 * index,
                            output_tokens=50 + 10 * index,
                            total_tokens=150 + 30 * index,
                        )
                    )
                await session.flush()
                # Standard control key: never part of any 219 flow.
                control = GatewayKey(
                    **_key_kwargs(4, suffix, now, owner.id, None, admin.id)
                )
                session.add(control)
                await session.flush()
                return {
                    "admin_email": admin.email,
                    "admin_id": str(admin.id),
                    "cohort_id": str(cohort.id),
                    "cohort_key_ids": [str(k) for k in cohort_key_ids],
                    "trusted_key_id": str(trusted.id),
                    "control_key_id": str(control.id),
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, Any]] = {}


def _seed_sync(database_url: str) -> dict[str, Any]:
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio.run(_seed(database_url))
    return _SEED_CACHE[database_url]


# ---------------------------------------------------------------------------
# Module environment: owned PG + real uvicorn
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env219_browser(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    database_url = owned_pg_url
    settings = _settings(database_url)
    seed = _seed_sync(database_url)
    app = create_app(settings)
    port = _free_port()
    base: dict[str, Any] = {
        "seed": seed,
        "base_url": f"http://127.0.0.1:{port}",
        "database_url": database_url,
    }
    with _run_uvicorn_server(app, port):
        yield base


@pytest.fixture(scope="module")
def chromium(env219_browser) -> Iterator[object]:
    """Depends on ``env219_browser`` on purpose: the Playwright sync
    session runs an asyncio loop on the main thread, so the app must be
    up BEFORE it starts."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_context(chromium: object, viewport: dict | None = None, *, no_js: bool = False):
    return chromium.new_context(  # type: ignore[attr-defined]
        viewport=viewport or DESKTOP,
        java_script_enabled=not no_js,
    )


def _login(page: object, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    page.fill('form[action="/admin/login"] input[name="email"]', email)  # type: ignore[attr-defined]
    page.fill('form[action="/admin/login"] input[name="password"]', password)  # type: ignore[attr-defined]
    page.click('form[action="/admin/login"] button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url(f"{base_url}/admin")  # type: ignore[attr-defined]


def _assert_help_links(page: object, help_ids: tuple[str, ...]) -> None:
    """Every named help element EXISTS, is non-empty, and is REFERENCED
    by at least one ACTUAL visible entry control's aria-describedby
    (real DOM check; 219-b: the referencing element must itself be an
    entry control — input/textarea/select — not any arbitrary element,
    and hidden inputs never count)."""
    for help_id in help_ids:
        ok = page.evaluate(  # type: ignore[attr-defined]
            """(id) => {
                const help = document.getElementById(id);
                if (!help || !help.textContent.trim()) return false;
                const refs = document.querySelectorAll('[aria-describedby~="help_id"]'.replace("help_id", id));
                for (const ref of refs) {
                    const tag = ref.tagName.toLowerCase();
                    if (tag === "input" || tag === "textarea" || tag === "select") {
                        if (tag === "input" && ref.type === "hidden") continue;
                        return true;
                    }
                }
                return false;
            }""",
            help_id,
        )
        assert ok, f"help not resolved by an actual entry control: {help_id}"


def _assert_enhanced_picker_search_help(page: object, help_id: str) -> None:
    """219-b: the enhanced picker's ACTUAL visible entry controls — the
    main input AND the unnamed menu-search box rendered by the shared
    macro — both reference the control's help id, which resolves to
    non-empty text in the real DOM."""
    result = page.evaluate(  # type: ignore[attr-defined]
        """(helpId) => {
            const help = document.getElementById(helpId);
            if (!help) return { found: false };
            const rc = help.closest("label") ? help.closest("label").querySelector("[data-rc]") : null;
            if (!rc) return { found: false };
            const firstRef = (el) =>
                (el.getAttribute("aria-describedby") || "").trim().split(/\\s+/)[0] || null;
            const main = rc.querySelector(".rc-input");
            const mainId = main ? firstRef(main) : null;
            const mainOk = !!(mainId && mainId === helpId && help.textContent.trim());
            const search = rc.querySelector(".rc-search");
            const searchId = search ? firstRef(search) : null;
            const searchOk = search
                ? !!(searchId && searchId === helpId && help.textContent.trim())
                : null;
            return { found: true, main: mainOk, search: searchOk };
        }""",
        help_id,
    )
    assert result["found"], f"enhanced picker for help {help_id} not found"
    assert result["main"], f"main picker input not associated with {help_id}"
    if result["search"] is not None:
        assert result["search"], (
            f"unnamed menu-search box not associated with {help_id}"
        )


def _open_all_details(page: object) -> None:
    """219-b: match the native rendered probe's population: all existing
    <details> disclosures open before the whole-field sweep."""
    page.evaluate(  # type: ignore[attr-defined]
        "document.querySelectorAll('details').forEach((d) => { d.open = true; })"
    )


def _assert_all_visible_entry_controls_described(page: object) -> int:
    """219-b: EVERY visible editable/choice control on the real page --
    unnamed JS-driven inputs, dynamically named inputs, and
    disabled-but-displayed lists included; hidden (computed CSS), readonly,
    and submit-type controls excluded -- carries a RESOLVING description:
    its own aria-describedby, or for checkbox/radio the innermost fieldset's,
    pointing at a defined, non-empty element. Real DOM + computed CSS;
    returns the audited control count."""
    result = page.evaluate(  # type: ignore[attr-defined]
        """() => {
            const problems = [];
            let count = 0;
            const isVisible = (el) => {
                let cur = el;
                while (cur && cur.nodeType === 1) {
                    const style = getComputedStyle(cur);
                    if (style.display === "none" || style.visibility === "hidden") {
                        return false;
                    }
                    cur = cur.parentElement;
                }
                return true;
            };
            const els = document.querySelectorAll("input, select, textarea");
            for (const el of els) {
                if (el.tagName === "INPUT") {
                    const t = (el.type || "text").toLowerCase();
                    if (["hidden", "submit", "button", "image", "reset"].includes(t)) {
                        continue;
                    }
                }
                if (el.hasAttribute("readonly")) continue;
                if (!isVisible(el)) continue;
                count++;
                const where = el.tagName.toLowerCase()
                    + (el.name ? "[name=" + el.name + "]" : " [unnamed]")
                    + (el.id ? "#" + el.id : "");
                let tokens = (el.getAttribute("aria-describedby") || "")
                    .trim().split(/\\s+/).filter(Boolean);
                if (!tokens.length && el.tagName === "INPUT"
                        && ["checkbox", "radio"].includes(el.type)) {
                    let cur = el.parentElement;
                    while (cur && cur.tagName !== "FIELDSET") cur = cur.parentElement;
                    if (cur) {
                        tokens = (cur.getAttribute("aria-describedby") || "")
                            .trim().split(/\\s+/).filter(Boolean);
                    }
                }
                if (!tokens.length) {
                    problems.push(where + ": no aria-describedby");
                    continue;
                }
                for (const id of tokens) {
                    const target = document.getElementById(id);
                    if (!target) {
                        problems.push(where + ": undefined help id " + id);
                    } else if (!target.textContent.trim()) {
                        problems.push(where + ": empty help id " + id);
                    }
                }
            }
            return { count: count, problems: problems };
        }"""
    )
    assert result["problems"] == [], (
        "unresolved visible-control descriptions: " + "; ".join(result["problems"])
    )
    return result["count"]


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


def _assert_no_key_material(page: object) -> None:
    body = page.content()  # type: ignore[attr-defined]
    assert "sk-provider-secret-placeholder" not in body
    assert "sk-or-provider-secret-placeholder" not in body
    assert "argon2" not in body


# ---------------------------------------------------------------------------
# 1) Create key page: visual order, linked help, narrow viewport
# ---------------------------------------------------------------------------


def test_create_page_visual_order_linked_help_and_narrow(
    env219_browser: dict[str, Any], chromium: object
) -> None:
    env = env219_browser
    base_url: str = env["base_url"]
    seed: dict[str, Any] = env["seed"]

    context = _new_context(chromium)
    page = context.new_page()
    _login(page, base_url, seed["admin_email"], ADMIN_PASSWORD)

    page.goto(f"{base_url}/admin/keys/create")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/create"]')  # type: ignore[attr-defined]

    # REAL DOM order: the short Policy Source section precedes the long
    # guided Request Policy selector.
    order = page.evaluate(  # type: ignore[attr-defined]
        """() => {
            const source = document.getElementById('create-policy-source-heading');
            const guided = document.getElementById('create-policy-heading');
            if (!source || !guided) return null;
            return !!(source.compareDocumentPosition(guided) & Node.DOCUMENT_POSITION_FOLLOWING);
        }"""
    )
    assert order is True, "Policy Source must precede the guided selector"

    # The new record-choice help resolves in the real DOM.
    _assert_help_links(page, ("create-owner-help", "create-cohort-help"))
    # 219-b: the ACTUAL visible enhanced controls (main input + the
    # unnamed menu-search box) carry the association, not just SOME
    # element somewhere on the page.
    _assert_enhanced_picker_search_help(page, "create-owner-help")
    _assert_enhanced_picker_search_help(page, "create-cohort-help")
    # 219-b: whole-field native audit -- EVERY visible editable/choice
    # control (unnamed search inputs, dynamically named fields, and
    # disabled-but-displayed policy lists included) resolves a real
    # description element in the real DOM, in BOTH policy-source states.
    _open_all_details(page)
    guided_count = _assert_all_visible_entry_controls_described(page)
    assert guided_count >= 50, (
        f"guided create sweep population implausible: {guided_count}"
    )
    page.select_option('select[name="policy_source"]', "configuration")
    page.wait_for_selector(  # type: ignore[attr-defined]
        "[data-create-configuration-document-group]", state="visible"
    )
    document_count = _assert_all_visible_entry_controls_described(page)
    assert document_count < guided_count, (
        "document mode did not hide the guided policy bodies"
    )
    assert document_count >= 5, (
        f"document create sweep population implausible: {document_count}"
    )
    _assert_no_key_material(page)
    page.screenshot(
        path=str(SCREENSHOT_DIR / "219-create-policy-source-desktop.png"),
        full_page=False,
    )
    page.locator("section[aria-labelledby='create-policy-source-heading']")  # type: ignore[attr-defined]
    context.close()

    # Narrow (420px): no horizontal document overflow.
    narrow = _new_context(chromium, viewport=NARROW)
    npage = narrow.new_page()
    _login(npage, base_url, seed["admin_email"], ADMIN_PASSWORD)
    npage.goto(f"{base_url}/admin/keys/create")  # type: ignore[attr-defined]
    npage.wait_for_selector('form[action="/admin/keys/create"]')  # type: ignore[attr-defined]
    overflow = npage.evaluate(  # type: ignore[attr-defined]
        "() => document.documentElement.scrollWidth"
        " - document.documentElement.clientWidth"
    )
    assert overflow <= 0, "create document overflows the 420px viewport"
    npage.screenshot(
        path=str(SCREENSHOT_DIR / "219-create-policy-source-narrow.png"),
        full_page=False,
    )
    narrow.close()


# ---------------------------------------------------------------------------
# 2) Trusted-calibration key detail: linked help + keyboard external-tool
# ---------------------------------------------------------------------------


def test_key_detail_linked_help_and_keyboard_ext_tool_update(
    env219_browser: dict[str, Any], chromium: object
) -> None:
    env = env219_browser
    base_url: str = env["base_url"]
    seed: dict[str, Any] = env["seed"]
    trusted_id: str = seed["trusted_key_id"]

    context = _new_context(chromium)
    page = context.new_page()
    _login(page, base_url, seed["admin_email"], ADMIN_PASSWORD)

    page.goto(f"{base_url}/admin/keys/{trusted_id}")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/external-tool-policy"]')  # type: ignore[attr-defined]

    # The rendered help elements resolve through real aria-describedby
    # links, including the record-choice destination-ID rc-help span.
    _assert_help_links(
        page,
        (
            "key-policy-reason-help",
            "key-rate-limits-help",
            "key-explain-route-help",
            "key-explain-model-help",
            "key-lazy-help",
            "key-ext-tool-help",
            "key-ext-tool-dest-help",
            "key-validity-help",
            "key-limits-help",
        ),
    )
    # 219-b: the explain-model picker is the shared searchable known-model
    # picker: its main input AND the unnamed menu-search box reference the
    # control's own help in the real DOM.
    _assert_enhanced_picker_search_help(page, "key-explain-model-help")
    rc_help = page.locator('span.rc-help#key-ext-tool-dest-help')  # type: ignore[attr-defined]
    assert rc_help.count() == 1
    assert rc_help.inner_text().strip()
    # Conditional group: strict bounded is the selected default, and the
    # reviewed-destination record choice (JS-enhanced, no-JS native
    # fallback) is part of the same visible group.
    assert page.eval_on_selector(  # type: ignore[attr-defined]
        'select[name="external_tool_mode"]',
        "el => el.value",
    ) == "strict_bounded"
    # 219-b: whole-field native audit -- the trusted detail page (all
    # existing disclosures open) AND a standard detail page must each
    # resolve every visible control's description in the real DOM.
    _open_all_details(page)
    assert _assert_all_visible_entry_controls_described(page) >= 50, (
        "trusted detail sweep population implausible"
    )
    standard_id: str = seed["control_key_id"]
    page.goto(f"{base_url}/admin/keys/{standard_id}")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + standard_id + '/policy"]')  # type: ignore[attr-defined]
    _open_all_details(page)
    assert _assert_all_visible_entry_controls_described(page) >= 50, (
        "standard detail sweep population implausible"
    )
    # Return to the trusted key for the keyboard-only operation below.
    page.goto(f"{base_url}/admin/keys/{trusted_id}")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/external-tool-policy"]')  # type: ignore[attr-defined]
    _assert_no_key_material(page)
    page.screenshot(
        path=str(SCREENSHOT_DIR / "219-key-detail-ext-tool-desktop.png"),
        full_page=False,
    )

    # KEYBOARD-ONLY real operation: focus the audit reason, type it, and
    # Enter submits the external-tool policy form (strict bounded kept).
    reason_input = page.locator(
        'form[action="/admin/keys/' + trusted_id + '/external-tool-policy"]'
        ' input[name="reason"]'
    )  # type: ignore[attr-defined]
    reason_input.focus()
    page.keyboard.type(EXT_TOOL_REASON)  # type: ignore[attr-defined]
    # Enter submits the form; wait on the ACTUAL target POST response (the
    # 207 _submit_form expect_response pattern), not on a URL the page
    # already has, which can resolve before the submission completes.
    with page.expect_response(  # type: ignore[attr-defined]
        lambda r: r.request.method == "POST"
        and r.url.endswith(f"/admin/keys/{trusted_id}/external-tool-policy")
    ) as post_info:
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
    assert int(post_info.value.status) == 303, "external-tool POST did not succeed"
    # Resulting navigation: the 303 lands back on the key detail with the
    # success message, and the flash is only rendered after that GET.
    page.wait_for_url(  # type: ignore[attr-defined]
        f"{base_url}/admin/keys/{trusted_id}?message=key_external_tool_policy_updated"
    )
    page.wait_for_selector(".admin-flash", state="visible", timeout=15000)  # type: ignore[attr-defined]
    flash_count = page.locator(".admin-flash").count()  # type: ignore[attr-defined]
    flash_text = (
        page.locator(".admin-flash").first.inner_text()  # type: ignore[attr-defined]
        if flash_count
        else "<no flash>"
    )
    error_count = page.locator(".admin-flash-error").count()  # type: ignore[attr-defined]
    assert (
        "External-tool policy updated"
        in page.inner_text("body")  # type: ignore[attr-defined]
    ), f"flash_count={flash_count} flash={flash_text!r} errors={error_count}"

    context.close()

    # Independent persisted-DB oracle (after the context is closed).
    rows = _db(
        env["database_url"],
        lambda session: session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == "update_external_tool_policy",
                AuditLog.admin_user_id == uuid.UUID(seed["admin_id"]),
                AuditLog.note == EXT_TOOL_REASON,
            )
            .order_by(AuditLog.created_at)
        ),
    )
    audits = rows.scalars().all()
    assert len(audits) == 1, "exactly one persisted external-tool audit expected"


# ---------------------------------------------------------------------------
# 3) Reviewed batch: membership disclosure + apply ordering (JS)
# ---------------------------------------------------------------------------


def _plan_cohort_cost_change(page: object, env: dict[str, Any], cohort_id: str) -> None:
    """Drive the batch plan form to a reviewed cohort plan: the cohort
    record choice plus one guided cost change."""
    # Combo box keyboard only (209 pattern): focus the entry field,
    # ArrowDown opens the menu, the next ArrowDown highlights the single
    # seeded option, Enter selects it (no mouse on an option).
    cohort_rc = page.locator(  # type: ignore[attr-defined]
        '[data-batch-cohort-control] .rc-input'
    )
    cohort_rc.focus()
    page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
    page.locator('[data-batch-cohort-control] .rc-menu').wait_for(  # type: ignore[attr-defined]
        state="visible", timeout=15000
    )
    page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]
    hidden = page.get_attribute('input[name="cohort_id"]', "value")  # type: ignore[attr-defined]
    assert hidden == cohort_id, "cohort selection not registered"

    page.select_option("select[name='cost_action']", "set")  # type: ignore[attr-defined]
    page.fill("input[name='cost_value']", "12.50")  # type: ignore[attr-defined]
    page.click(f"{PLAN_FORM} button[type='submit']")  # type: ignore[attr-defined]
    page.wait_for_selector(  # type: ignore[attr-defined]
        'input[name="batch_review_intent"]', state="attached"
    )


def test_batch_review_membership_disclosure_and_apply_order(
    env219_browser: dict[str, Any], chromium: object
) -> None:
    env = env219_browser
    base_url: str = env["base_url"]
    seed: dict[str, Any] = env["seed"]
    cohort_id: str = seed["cohort_id"]

    context = _new_context(chromium)
    page = context.new_page()
    _login(page, base_url, seed["admin_email"], ADMIN_PASSWORD)

    page.goto(f"{base_url}/admin/key-batch")  # type: ignore[attr-defined]
    page.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]
    _plan_cohort_cost_change(page, env, cohort_id)

    # The complete reviewed membership is a keyboard/no-JS disclosure,
    # collapsed by default, with the exact UUID count in the summary.
    details = page.locator(  # type: ignore[attr-defined]
        "section[aria-labelledby='batch-review-plan-heading'] details:has(summary:has-text('Full reviewed membership'))"
    )
    assert details.count() == 1
    summary_text = details.locator("summary").inner_text()  # type: ignore[attr-defined]
    assert "3 exact key UUIDs" in summary_text
    assert details.evaluate("el => el.open") is False, (  # type: ignore[attr-defined]
        "membership disclosure must start collapsed"
    )

    # DOM order: Apply section BEFORE the per-key before/after table.
    order = page.evaluate(  # type: ignore[attr-defined]
        """() => {
            const apply = document.getElementById('batch-review-apply-heading');
            const table = document.getElementById('batch-review-keys-heading');
            if (!apply || !table) return null;
            return !!(apply.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING);
        }"""
    )
    assert order is True, "Apply section must precede the per-key table"

    # Keyboard disclosure: focus the summary and press Enter.
    details.locator("summary").focus()  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]
    assert details.evaluate("el => el.open") is True  # type: ignore[attr-defined]
    visible_uuids = [
        code.inner_text().strip()  # type: ignore[attr-defined]
        for code in details.locator("ul.uuid-list code").all()
    ]
    assert sorted(visible_uuids) == sorted(seed["cohort_key_ids"])

    _assert_no_key_material(page)
    page.screenshot(
        path=str(SCREENSHOT_DIR / "219-batch-review-disclosure-open.png"),
        full_page=False,
    )
    context.close()


# ---------------------------------------------------------------------------
# 4) No-JS operator: batch disclosure + full calibration flow (real writes)
# ---------------------------------------------------------------------------


def test_nojs_batch_disclosure_and_calibration_flow(
    env219_browser: dict[str, Any], chromium: object
) -> None:
    env = env219_browser
    base_url: str = env["base_url"]
    seed: dict[str, Any] = env["seed"]
    trusted_id: str = seed["trusted_key_id"]

    context = _new_context(chromium, no_js=True)
    page = context.new_page()
    _login(page, base_url, seed["admin_email"], ADMIN_PASSWORD)

    # No-JS batch: native select fallback for the cohort record choice.
    page.goto(f"{base_url}/admin/key-batch")  # type: ignore[attr-defined]
    page.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]
    # Without JavaScript the cohort picker is the plain named text field.
    assert page.locator("input[name='cohort_id']").count() == 1  # type: ignore[attr-defined]
    page.fill("input[name='cohort_id']", seed["cohort_id"])  # type: ignore[attr-defined]
    page.select_option("select[name='cost_action']", "set")  # type: ignore[attr-defined]
    page.fill("input[name='cost_value']", "12.50")  # type: ignore[attr-defined]
    page.click(f"{PLAN_FORM} button[type='submit']")  # type: ignore[attr-defined]
    page.wait_for_selector(  # type: ignore[attr-defined]
        'input[name="batch_review_intent"]', state="attached"
    )

    details = page.locator(  # type: ignore[attr-defined]
        "section[aria-labelledby='batch-review-plan-heading'] details:has(summary:has-text('Full reviewed membership'))"
    )
    assert details.count() == 1
    assert "3 exact key UUIDs" in details.locator("summary").inner_text()  # type: ignore[attr-defined]
    # Native <details> works without JS: open it and check the UUID list.
    details.locator("summary").click()  # type: ignore[attr-defined]
    visible_uuids = [
        code.inner_text().strip()  # type: ignore[attr-defined]
        for code in details.locator("ul.uuid-list code").all()
    ]
    assert sorted(visible_uuids) == sorted(seed["cohort_key_ids"])
    # The apply form (with its linked help) is still present above the
    # per-key table, and the associations survive with JS disabled.
    _assert_help_links(page, ("batch-apply-help",))
    page.screenshot(
        path=str(SCREENSHOT_DIR / "219-batch-review-nojs.png"),
        full_page=False,
    )

    # No-JS calibration: native form preview, safe JSON attachment, and
    # the SAME-page template creation (no JS to rotate anything).
    page.goto(f"{base_url}/admin/keys/{trusted_id}/calibration")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/calibration/preview"]')  # type: ignore[attr-defined]
    page.fill('input[name="multiplier"]', "2")  # type: ignore[attr-defined]
    page.click(  # type: ignore[attr-defined]
        'form[action="/admin/keys/' + trusted_id + '/calibration/preview"] button[type="submit"]'
    )
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/calibration/create-template"]')  # type: ignore[attr-defined]
    flat = page.inner_text("body")  # type: ignore[attr-defined]
    assert "bulk participant key creation remains future work" in flat
    assert "Templates and recommendation execution are future work" not in flat
    assert "not a frozen copy of this rendered preview" in flat

    # Safe JSON attachment in the no-JS browser.
    with page.expect_download() as download_info:  # type: ignore[attr-defined]
        page.click("a:has-text(\"Download this preview's JSON\")")  # type: ignore[attr-defined]
    download = download_info.value  # type: ignore[attr-defined]
    assert download.suggested_filename == (  # type: ignore[attr-defined]
        f"slaif-calibration-summary-{trusted_id}.json"
    )
    payload_path = SCREENSHOT_DIR / "219-nojs-calibration-summary.json"
    download.save_as(str(payload_path))  # type: ignore[attr-defined]
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "proposal", "is_empty", "warnings"}

    # Same-page template creation with the STILL-DISPLAYED form token.
    page.goto(f"{base_url}/admin/keys/{trusted_id}/calibration")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/calibration/preview"]')  # type: ignore[attr-defined]
    page.fill('input[name="multiplier"]', "2")  # type: ignore[attr-defined]
    page.click(  # type: ignore[attr-defined]
        'form[action="/admin/keys/' + trusted_id + '/calibration/preview"] button[type="submit"]'
    )
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/calibration/create-template"]')  # type: ignore[attr-defined]
    create_form = 'form[action="/admin/keys/' + trusted_id + '/calibration/create-template"]'
    page.fill(f'{create_form} input[name="template_name"]', NOJS_TEMPLATE_NAME)  # type: ignore[attr-defined]
    page.check(f'{create_form} input[name="confirm_create_template"]')  # type: ignore[attr-defined]
    page.fill(f'{create_form} input[name="reason"]', NOJS_TEMPLATE_REASON)  # type: ignore[attr-defined]
    page.click(f'{create_form} button[type="submit"]')  # type: ignore[attr-defined]
    # DOM-poll the rendered template name: a same-tab download can leave
    # Playwright's navigation-lifecycle wait desynced even though the
    # document fully loaded (document.readyState == complete), so the
    # element wait is the reliable gate here.
    page.get_by_text(NOJS_TEMPLATE_NAME, exact=True).first.wait_for(  # type: ignore[attr-defined]
        state="visible", timeout=20000
    )
    assert "template_created" in page.url  # type: ignore[attr-defined]
    assert "Key template" in page.inner_text("body")  # type: ignore[attr-defined]

    context.close()

    # Independent persisted-DB oracles (after the context is closed).
    rows = _db(
        env["database_url"],
        lambda session: session.execute(
            select(KeyTemplate)
            .where(KeyTemplate.name == NOJS_TEMPLATE_NAME)
            .where(KeyTemplate.created_by_admin_id == uuid.UUID(seed["admin_id"]))
        ),
    )
    templates = rows.scalars().all()
    assert len(templates) == 1, "no-JS template not persisted exactly once"
    assert templates[0].current_revision_id is not None

    audits = _db(
        env["database_url"],
        lambda session: session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == "key_template.created",
                AuditLog.admin_user_id == uuid.UUID(seed["admin_id"]),
                AuditLog.note == NOJS_TEMPLATE_REASON,
            )
        ),
    )
    assert len(audits.scalars().all()) == 1, "no-JS template audit missing"


# ---------------------------------------------------------------------------
# 5) Keyboard calibration: preview, real download, same-token template create
# ---------------------------------------------------------------------------


def test_keyboard_calibration_download_then_same_token_create(
    env219_browser: dict[str, Any], chromium: object
) -> None:
    env = env219_browser
    base_url: str = env["base_url"]
    seed: dict[str, Any] = env["seed"]
    trusted_id: str = seed["trusted_key_id"]

    context = _new_context(chromium)
    page = context.new_page()
    _login(page, base_url, seed["admin_email"], ADMIN_PASSWORD)

    page.goto(f"{base_url}/admin/keys/{trusted_id}/calibration")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/calibration/preview"]')  # type: ignore[attr-defined]

    # KEYBOARD-ONLY preview submission: focus the multiplier and type.
    multiplier = page.locator('input[name="multiplier"]')  # type: ignore[attr-defined]
    multiplier.focus()
    page.keyboard.press("ControlOrMeta+a")  # type: ignore[attr-defined]
    page.keyboard.type("2")  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/keys/' + trusted_id + '/calibration/create-template"]')  # type: ignore[attr-defined]
    flat = page.inner_text("body")  # type: ignore[attr-defined]
    assert "bulk participant key creation remains future work" in flat
    assert "not a frozen copy of this rendered preview" in flat

    # Real browser download of the safe JSON attachment.
    with page.expect_download() as download_info:  # type: ignore[attr-defined]
        page.click("a:has-text(\"Download this preview's JSON\")")  # type: ignore[attr-defined]
    download = download_info.value  # type: ignore[attr-defined]
    assert download.suggested_filename == (  # type: ignore[attr-defined]
        f"slaif-calibration-summary-{trusted_id}.json"
    )
    payload_path = SCREENSHOT_DIR / "219-keyboard-calibration-summary.json"
    download.save_as(str(payload_path))  # type: ignore[attr-defined]
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "proposal", "is_empty", "warnings"}
    assert "sk-provider-secret-placeholder" not in payload_path.read_text(encoding="utf-8")

    # The SAME still-displayed form token must create the template
    # (real-browser non-rotating CSRF proof), keyboard only.
    create_form = 'form[action="/admin/keys/' + trusted_id + '/calibration/create-template"]'
    name_input = page.locator(f'{create_form} input[name="template_name"]')  # type: ignore[attr-defined]
    name_input.focus()
    page.keyboard.type(JS_TEMPLATE_NAME)  # type: ignore[attr-defined]
    confirm = page.locator(f'{create_form} input[name="confirm_create_template"]')  # type: ignore[attr-defined]
    confirm.focus()
    page.keyboard.press("Space")  # type: ignore[attr-defined]
    reason_input = page.locator(f'{create_form} input[name="reason"]')  # type: ignore[attr-defined]
    reason_input.focus()
    page.keyboard.type(JS_TEMPLATE_REASON)  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]
    # Same-tab download desync note: DOM-poll the rendered name.
    page.get_by_text(JS_TEMPLATE_NAME, exact=True).first.wait_for(  # type: ignore[attr-defined]
        state="visible", timeout=20000
    )
    assert "template_created" in page.url  # type: ignore[attr-defined]
    assert "Key template" in page.inner_text("body")  # type: ignore[attr-defined]
    page.screenshot(
        path=str(SCREENSHOT_DIR / "219-calibration-template-created.png"),
        full_page=False,
    )

    context.close()

    # Independent persisted-DB oracles (after the context is closed).
    rows = _db(
        env["database_url"],
        lambda session: session.execute(
            select(KeyTemplate)
            .where(KeyTemplate.name == JS_TEMPLATE_NAME)
            .where(KeyTemplate.created_by_admin_id == uuid.UUID(seed["admin_id"]))
        ),
    )
    templates = rows.scalars().all()
    assert len(templates) == 1, "keyboard template not persisted exactly once"

    audits = _db(
        env["database_url"],
        lambda session: session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == "key_template.created",
                AuditLog.admin_user_id == uuid.UUID(seed["admin_id"]),
                AuditLog.note == JS_TEMPLATE_REASON,
            )
        ),
    )
    assert len(audits.scalars().all()) == 1, "keyboard template audit missing"
