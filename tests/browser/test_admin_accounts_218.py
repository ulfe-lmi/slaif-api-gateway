"""218-a G17: real-Chromium browser qualification of the admin accounts GUI.

Real browser, real uvicorn app, and ONE NEW owned labeled loopback tmpfs
PostgreSQL 16 (the qualified ``owned_pg_url`` fixture - never an ambient
database). No Redis/Celery, no upstream network, no real credentials.

Cases (file order is significant; the module environment is shared):

- real login, then the accounts list renders the safe metadata table
  (server-derived identity, UUID reset links, honest pagination) with NO
  hash/token/secret in the rendered page (desktop capture);
- the create form: every visible control carries a RESOLVED
  aria-describedby link to a non-empty help element (real DOM check),
  the explicit-confirmation refusal (400, password never redisplayed),
  the full create flow (303 -> flash -> the persisted row in the list),
  and the duplicate refusal (409, no raw SQL text);
- the reset flow entered from the list row link: the server-derived
  identity and the URL-bound target, the explained session-revocation
  consequence BEFORE confirmation, the full reset flow, and the
  persisted consequence (new password signs in, old password refused);
- the self-reset flow: the own-account warning, the secret-free
  safe-login flash, the revoked session, new-password sign-in,
  old-password refusal;
- the SERVER-side ordinary-admin denial (403 on every account view and
  action - hiding the link is not the gate);
- narrow (420px) layout without horizontal overflow (capture),
  keyboard-only flow that performs a REAL create, and a no-JS operator
  flow that performs a REAL reset (not just GET/render).

Synthetic screenshots are stored under /tmp/slaif218 for operator/root
inspection (accepted visuals are frozen).
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from slaif_gateway.main import create_app
from tests.integration.test_admin_accounts_218_postgres import (
    BASE as ACCOUNTS_BASE,
    ROOT2_PASSWORD,
    ROOT_PASSWORD,
    _seed_admins,
    _settings,
)
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

BASE = ACCOUNTS_BASE

pytestmark = pytest.mark.playwright

owned_pg_url = _owned_pg_url_fixture

LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif218")
DESKTOP = {"width": 1440, "height": 900}
NARROW = {"width": 420, "height": 860}

# Distinctive canary secrets for the browser flows.
CREATE_PASSWORD = "218-browser-create-pw-xQ9"
RESET_PASSWORD = "218-browser-reset-pw-mK4"
SELF_RESET_PASSWORD = "218-browser-self-pw-zT7"


# ---------------------------------------------------------------------------
# Real uvicorn (214/215/216/217 pattern)
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
# Module environment: owned PG + real uvicorn
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env218_browser(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    settings = _settings(owned_pg_url)
    accounts = asyncio.run(_seed_admins(owned_pg_url))
    app = create_app(settings)
    port = _free_port()
    base: dict[str, Any] = {
        "accounts": accounts,
        "base_url": f"http://127.0.0.1:{port}",
        "database_url": owned_pg_url,
    }
    with _run_uvicorn_server(app, port):
        yield base


@pytest.fixture(scope="module")
def chromium(env218_browser) -> Iterator[object]:
    """Depends on ``env218_browser`` on purpose: the Playwright sync
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


def _login_page(page: object, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', email)  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', password)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url(f"{base_url}/admin")  # type: ignore[attr-defined]


def _assert_help_links(page: object, help_ids: tuple[str, ...]) -> None:
    """Every named help element EXISTS, is non-empty, and is REFERENCED
    by at least one real control's aria-describedby (real DOM check)."""
    for help_id in help_ids:
        ok = page.evaluate(  # type: ignore[attr-defined]
            """(id) => {
                const help = document.getElementById(id);
                if (!help || !help.textContent.trim()) return false;
                return !!document.querySelector('[aria-describedby~="help_id"]'.replace("help_id", id));
            }""",
            help_id,
        )
        assert ok, f"help link not resolved: {help_id}"


def _row_for_email(page: object, email: str):
    # Text-engine match (no CSS escaping issues with "@" in emails).
    return page.locator(  # type: ignore[attr-defined]
        "table[data-sortable] tbody tr",
        has=page.get_by_text(email, exact=True),  # type: ignore[attr-defined]
    )


def _list_rows(page: object) -> int:
    return page.locator("table[data-sortable] tbody tr").count()  # type: ignore[attr-defined]


def _submit_form(page: object, form_selector: str) -> None:
    page.click(f"{form_selector} button[type='submit']")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 1. Login + list rendering (desktop capture)
# ---------------------------------------------------------------------------


def test_login_and_accounts_list_safe_rendering(
    env218_browser: dict[str, Any], chromium: object
) -> None:
    base_url: str = env218_browser["base_url"]
    accounts = env218_browser["accounts"]
    root = accounts["superadmin"]

    context = _new_context(chromium)
    page = context.new_page()
    _login_page(page, base_url, root["email"], ROOT_PASSWORD)

    page.goto(f"{base_url}{BASE}")  # type: ignore[attr-defined]
    page.wait_for_selector("table[data-sortable]")  # type: ignore[attr-defined]

    # Every seeded identity is listed with its SERVER-DERIVED UUID link.
    for key in ("superadmin", "root2", "target", "bystander"):
        email = accounts[key]["email"]
        row = _row_for_email(page, email)
        assert row.count() == 1, email
        assert row.locator('a[href^="/admin/accounts/reset?admin_id="]').count() == 1

    body = page.content()
    assert "argon2" not in body
    assert "provider-secret-placeholder-218" not in body
    # Accessible scroll wrapper + shared sort/ordinal contract.
    assert page.locator('[role="region"][aria-label="Administrator accounts"]').count() == 1
    assert page.locator("th[data-sort-type]").count() >= 2
    assert page.locator("td.row-ordinal").first.inner_text() == "1"
    # The operations index navigation carries the bounded account group.
    page.goto(f"{base_url}/admin/operations/")  # type: ignore[attr-defined]
    body = page.content()
    assert 'href="/admin/accounts"' in body
    assert "Administrator accounts" in body

    page.screenshot(path=str(SCREENSHOT_DIR / "218-accounts-list-desktop.png"))
    context.close()


# ---------------------------------------------------------------------------
# 2. Create form: linked help, confirm refusal, full flow, duplicate 409
# ---------------------------------------------------------------------------


def test_create_flow_linked_help_and_persisted_outcome(
    env218_browser: dict[str, Any], chromium: object
) -> None:
    base_url: str = env218_browser["base_url"]
    accounts = env218_browser["accounts"]
    root = accounts["superadmin"]

    context = _new_context(chromium)
    page = context.new_page()
    _login_page(page, base_url, root["email"], ROOT_PASSWORD)

    page.goto(f"{base_url}{BASE}/create")  # type: ignore[attr-defined]
    page.wait_for_selector('form[action="/admin/accounts/create"]')  # type: ignore[attr-defined]

    # EVERY visible control has a resolved, non-empty, linked field help.
    _assert_help_links(
        page,
        (
            "create-email-help",
            "create-display-name-help",
            "create-password-help",
            "create-password-confirmation-help",
            "create-role-help",
            "create-confirm-help",
            "create-superadmin-confirm-help",
            "create-reason-help",
        ),
    )
    assert page.locator('select[name="role"] option').count() == 2  # native choices
    page.screenshot(path=str(SCREENSHOT_DIR / "218-create-desktop.png"))

    # Explicit confirmation is REQUIRED even for an ordinary admin: the
    # form's native required validation blocks the submit before any
    # request (the SAME server-side 400 refusal law is proven natively
    # in the unit/native modules); safe fields are preserved and the
    # password values are never redisplayed.
    email = f"218-browser-created-{uuid.uuid4().hex[:10]}@example.test"
    form = 'form[action="/admin/accounts/create"]'
    page.fill(f'{form} input[name="email"]', email)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="display_name"]', "218 Browser Created")  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password"]', CREATE_PASSWORD)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password_confirmation"]', CREATE_PASSWORD)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="reason"]', "218 browser create")  # type: ignore[attr-defined]
    _submit_form(page, form)
    # Native constraint validation refused the submit: no navigation,
    # the missing control is invalid, and the page state is preserved.
    assert page.url.endswith("/admin/accounts/create")
    assert page.evaluate(  # type: ignore[attr-defined]
        'document.querySelector('
        '\'form[action="/admin/accounts/create"] input[name="confirm_create"]\''
        ").checkValidity() === false"
    )
    body = page.content()
    assert CREATE_PASSWORD not in body  # password never redisplayed by the server
    assert f'value="{CREATE_PASSWORD}"' not in body  # no source-level redisplay either
    assert page.locator(f'{form} input[name="email"]').input_value() == email  # type: ignore[attr-defined]
    # The browser DOM keeps the user-typed password after a natively blocked
    # submit; the server-redisplay law above is the binding check.

    # The full flow: explicit confirmation -> 303 -> flash -> persisted.
    page.check(f'{form} input[name="confirm_create"]')  # type: ignore[attr-defined]
    _submit_form(page, form)
    page.wait_for_url(f"{base_url}{BASE}?message=admin_account_created")  # type: ignore[attr-defined]
    assert page.locator(".admin-flash-success").inner_text() == (  # type: ignore[attr-defined]
        "Administrator account created."
    )
    assert CREATE_PASSWORD not in page.content()

    # The persisted outcome is visible in the list (safe metadata only).
    assert _row_for_email(page, email).count() == 1
    assert CREATE_PASSWORD not in page.content()
    assert "argon2" not in page.content()

    # Duplicate submission: the KNOWN condition answers fixed 409.
    page.goto(f"{base_url}{BASE}/create")  # type: ignore[attr-defined]
    page.wait_for_selector(f'{form} input[name="email"]')  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="email"]', email)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="display_name"]', "218 Browser Dup")  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password"]', "218-browser-dup-pw-Qq2")  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password_confirmation"]', "218-browser-dup-pw-Qq2")  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="reason"]', "218 browser duplicate")  # type: ignore[attr-defined]
    page.check(f'{form} input[name="confirm_create"]')  # type: ignore[attr-defined]
    _submit_form(page, form)
    # The shared branded error surface (fixed 409 outcome, no raw text).
    page.wait_for_selector("#error-heading")  # type: ignore[attr-defined]
    assert page.locator("#error-heading").inner_text() == "Error"  # type: ignore[attr-defined]
    body = page.content()
    assert "HTTP 409" in body
    assert (
        "An administrator account with this email already exists. The "
        "submission was rejected without changes." in body
    )
    for fragment in ("duplicate key", "IntegrityError", "psycopg", "asyncpg", "argon2"):
        assert fragment not in body

    context.close()


# ---------------------------------------------------------------------------
# 3. Reset flow: bound target, explained consequence, persisted outcome
# ---------------------------------------------------------------------------


def test_reset_flow_from_list_link_and_persisted_consequences(
    env218_browser: dict[str, Any], chromium: object
) -> None:
    base_url: str = env218_browser["base_url"]
    accounts = env218_browser["accounts"]
    root = accounts["superadmin"]
    target = accounts["target"]

    context = _new_context(chromium)
    page = context.new_page()
    _login_page(page, base_url, root["email"], ROOT_PASSWORD)

    # Enter through the LIST ROW link (server-derived fixed UUID target).
    page.goto(f"{base_url}{BASE}")  # type: ignore[attr-defined]
    _row_for_email(page, target["email"]).locator(
        'a[href^="/admin/accounts/reset?admin_id="]'
    ).click()
    page.wait_for_url(f"{base_url}{BASE}/reset?admin_id=*")  # type: ignore[attr-defined]

    # Server-derived identity + URL-bound form + explained consequence
    # BEFORE the confirmation control.
    body = page.content()
    assert target["email"] in body
    assert f'action="/admin/accounts/reset?admin_id={target["id"]}"' in body
    assert f'name="admin_id" value="{target["id"]}"' in body
    assert "signs out ALL of its existing console sessions" in body
    _assert_help_links(
        page,
        (
            "reset-password-help",
            "reset-password-confirmation-help",
            "reset-confirm-help",
            "reset-reason-help",
        ),
    )
    page.screenshot(path=str(SCREENSHOT_DIR / "218-reset-desktop.png"))

    form = 'form[action^="/admin/accounts/reset?admin_id="]'
    # Mismatched confirmation: refused, and the complete secret values are
    # never redisplayed.
    page.fill(f'{form} input[name="password"]', RESET_PASSWORD)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password_confirmation"]', RESET_PASSWORD + "x")  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="reason"]', "218 browser reset")  # type: ignore[attr-defined]
    page.check(f'{form} input[name="confirm_reset"]')  # type: ignore[attr-defined]
    _submit_form(page, form)
    page.wait_for_selector(".admin-flash-error")  # type: ignore[attr-defined]
    body = page.content()
    assert "do not match exactly" in body
    assert RESET_PASSWORD not in body
    assert RESET_PASSWORD + "x" not in body
    # The server-refetched target identity is still displayed on the
    # validation-recovery re-render.
    assert target["email"] in body

    # The full reset flow. The validation-recovery re-render never
    # redisplayed the secrets and does not preserve the confirmation
    # checkbox state (the reason field IS preserved), so BOTH password
    # entries and the explicit confirmation are re-entered.
    page.fill(f'{form} input[name="password"]', RESET_PASSWORD)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password_confirmation"]', RESET_PASSWORD)  # type: ignore[attr-defined]
    page.check(f'{form} input[name="confirm_reset"]')  # type: ignore[attr-defined]
    _submit_form(page, form)
    page.wait_for_url(f"{base_url}{BASE}?message=admin_password_reset")  # type: ignore[attr-defined]
    assert page.locator(".admin-flash-success").inner_text() == (  # type: ignore[attr-defined]
        "Administrator password reset completed; the account's previous "
        "sessions were signed out."
    )
    assert RESET_PASSWORD not in page.content()

    # Persisted consequence: the new password signs in, the old password
    # is refused - in a FRESH browser (real login against real PG).
    fresh = _new_context(chromium)
    fresh_page = fresh.new_page()
    fresh_page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    fresh_page.fill(f'{LOGIN_FORM} input[name="email"]', target["email"])  # type: ignore[attr-defined]
    fresh_page.fill(f'{LOGIN_FORM} input[name="password"]', RESET_PASSWORD)  # type: ignore[attr-defined]
    fresh_page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    fresh_page.wait_for_url(f"{base_url}/admin")  # type: ignore[attr-defined]

    refused = _new_context(chromium)
    refused_page = refused.new_page()
    refused_page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    refused_page.fill(f'{LOGIN_FORM} input[name="email"]', target["email"])  # type: ignore[attr-defined]
    refused_page.fill(f'{LOGIN_FORM} input[name="password"]', target["password"])  # type: ignore[attr-defined]
    refused_page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    refused_page.wait_for_selector(".form-error")  # type: ignore[attr-defined]
    assert refused_page.locator(".form-error").inner_text() == (  # type: ignore[attr-defined]
        "Invalid email or password."
    )

    fresh.close()
    refused.close()
    context.close()


# ---------------------------------------------------------------------------
# 4. Self-reset: own-account warning, secret-free flash, revoked session
# ---------------------------------------------------------------------------


def test_self_reset_logout_and_safe_login_flash(
    env218_browser: dict[str, Any], chromium: object
) -> None:
    base_url: str = env218_browser["base_url"]
    accounts = env218_browser["accounts"]
    root2 = accounts["root2"]

    context = _new_context(chromium)
    page = context.new_page()
    _login_page(page, base_url, root2["email"], ROOT2_PASSWORD)

    page.goto(f"{base_url}{BASE}")  # type: ignore[attr-defined]
    _row_for_email(page, root2["email"]).locator(
        'a[href^="/admin/accounts/reset?admin_id="]'
    ).click()
    page.wait_for_url(f"{base_url}{BASE}/reset?admin_id=*")  # type: ignore[attr-defined]
    # The own-account consequence is explained explicitly.
    assert "your own account" in page.content()

    form = 'form[action^="/admin/accounts/reset?admin_id="]'
    page.fill(f'{form} input[name="password"]', SELF_RESET_PASSWORD)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="password_confirmation"]', SELF_RESET_PASSWORD)  # type: ignore[attr-defined]
    page.fill(f'{form} input[name="reason"]', "218 browser self reset")  # type: ignore[attr-defined]
    page.check(f'{form} input[name="confirm_reset"]')  # type: ignore[attr-defined]
    _submit_form(page, form)
    page.wait_for_url(f"{base_url}/admin/login?message=admin_password_reset_self")  # type: ignore[attr-defined]

    # The secret-free safe-login flash; the session is gone (the login
    # page rendered, not the dashboard).
    assert page.locator(".admin-flash-success").inner_text() == (  # type: ignore[attr-defined]
        "Your password was reset. All of your admin sessions were signed "
        "out; sign in again with the new password."
    )
    assert SELF_RESET_PASSWORD not in page.content()
    page.screenshot(path=str(SCREENSHOT_DIR / "218-self-reset-flash.png"))

    # The SAME context (whose cookie the server revoked) is bounced to
    # the login page, then the new password signs in and the old one is
    # refused.
    page.goto(f"{base_url}/admin")  # type: ignore[attr-defined]
    page.wait_for_url(f"{base_url}/admin/login")  # type: ignore[attr-defined]

    page.fill(f'{LOGIN_FORM} input[name="email"]', root2["email"])  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', SELF_RESET_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url(f"{base_url}/admin")  # type: ignore[attr-defined]

    # Sign out through the dashboard's real POST form (logout is
    # POST-only with CSRF).
    page.click('form[action="/admin/logout"] button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', root2["email"])  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ROOT2_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_selector(".form-error")  # type: ignore[attr-defined]
    assert page.locator(".form-error").inner_text() == (  # type: ignore[attr-defined]
        "Invalid email or password."
    )

    context.close()


# ---------------------------------------------------------------------------
# 5. Server-side ordinary-admin denial (hiding links is not the gate)
# ---------------------------------------------------------------------------


def test_ordinary_admin_denied_on_every_account_surface(
    env218_browser: dict[str, Any], chromium: object
) -> None:
    base_url: str = env218_browser["base_url"]
    accounts = env218_browser["accounts"]
    target = accounts["target"]

    context = _new_context(chromium)
    page = context.new_page()
    # The account was reset by an earlier test: sign in with the NEW
    # password (real PG state).
    _login_page(page, base_url, target["email"], RESET_PASSWORD)

    for path in (
        f"{BASE}",
        f"{BASE}/create",
        f"{BASE}/reset?admin_id={target['id']}",
    ):
        page.goto(f"{base_url}{path}")  # type: ignore[attr-defined]
        page.wait_for_selector("#error-heading")  # type: ignore[attr-defined]
        assert page.locator("#error-heading").inner_text() == "Forbidden"  # type: ignore[attr-defined]
        body = page.content()
        assert (
            "Administrator account management requires the existing "
            "superadmin role. Sign in as a superadmin to manage accounts." in body
        )
        assert "Reset password" not in body  # no account rows leaked
        assert "argon2" not in body

    context.close()


# ---------------------------------------------------------------------------
# 6. Narrow + keyboard + no-JS (real operations, not just rendering)
# ---------------------------------------------------------------------------


def test_narrow_keyboard_and_no_js_real_flows(
    env218_browser: dict[str, Any], chromium: object
) -> None:
    base_url: str = env218_browser["base_url"]
    accounts = env218_browser["accounts"]
    root = accounts["superadmin"]
    target = accounts["bystander"]

    # --- Narrow (420px): no horizontal overflow, form usable (capture) ---
    narrow = _new_context(chromium, viewport=NARROW)
    narrow_page = narrow.new_page()
    _login_page(narrow_page, base_url, root["email"], ROOT_PASSWORD)
    narrow_page.goto(f"{base_url}{BASE}/create")  # type: ignore[attr-defined]
    narrow_page.wait_for_selector('form[action="/admin/accounts/create"]')  # type: ignore[attr-defined]
    assert narrow_page.evaluate(  # type: ignore[attr-defined]
        "document.documentElement.scrollWidth <= 420"
    )
    narrow_page.screenshot(
        path=str(SCREENSHOT_DIR / "218-create-narrow.png"), full_page=True
    )
    narrow.close()

    # --- Keyboard-only: a REAL create without any pointer events ---
    keys = _new_context(chromium)
    keys_page = keys.new_page()
    _login_page(keys_page, base_url, root["email"], ROOT_PASSWORD)
    keys_page.goto(f"{base_url}{BASE}/create")  # type: ignore[attr-defined]
    keys_page.wait_for_selector('form[action="/admin/accounts/create"]')  # type: ignore[attr-defined]
    keyboard_email = f"218-browser-keyboard-{uuid.uuid4().hex[:10]}@example.test"
    # Keyboard focus into the FIRST control, then Tab through the form.
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]
    for _ in range(20):  # reach the email field deterministically
        if keys_page.evaluate(  # type: ignore[attr-defined]
            'document.activeElement && document.activeElement.name === "email"'
        ):
            break
        keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]
    keys_page.keyboard.type(keyboard_email)  # type: ignore[attr-defined]
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]
    keys_page.keyboard.type("218 Browser Keyboard")  # type: ignore[attr-defined]
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]
    keys_page.keyboard.type("218-browser-keyboard-pw-Hh5")  # type: ignore[attr-defined]
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]
    keys_page.keyboard.type("218-browser-keyboard-pw-Hh5")  # type: ignore[attr-defined]
    # Tab over the role select: it keeps its default (ordinary admin) -
    # no pointer, no dropdown interaction.
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]  # -> role (skip)
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]  # -> confirm_create
    keys_page.keyboard.press("Space")  # type: ignore[attr-defined]  # check confirm_create
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]  # -> confirm_superadmin (skip)
    keys_page.keyboard.press("Tab")  # type: ignore[attr-defined]  # -> reason
    keys_page.keyboard.type("218 browser keyboard create")  # type: ignore[attr-defined]
    keys_page.keyboard.press("Enter")  # type: ignore[attr-defined]  # submit
    keys_page.wait_for_url(f"{base_url}{BASE}?message=admin_account_created")  # type: ignore[attr-defined]
    assert keys_page.locator(".admin-flash-success").count() == 1  # type: ignore[attr-defined]
    assert _row_for_email(keys_page, keyboard_email).count() == 1
    keys.close()

    # --- No-JS: a REAL reset through the plain form POST ---
    nojs = _new_context(chromium, no_js=True)
    nojs_page = nojs.new_page()
    nojs_page.goto(f"{base_url}/admin/login")  # type: ignore[attr-defined]
    nojs_page.fill(f'{LOGIN_FORM} input[name="email"]', root["email"])  # type: ignore[attr-defined]
    nojs_page.fill(f'{LOGIN_FORM} input[name="password"]', ROOT_PASSWORD)  # type: ignore[attr-defined]
    nojs_page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    nojs_page.wait_for_url(f"{base_url}/admin")  # type: ignore[attr-defined]

    nojs_page.goto(f"{base_url}{BASE}")  # type: ignore[attr-defined]
    nojs_page.wait_for_selector("table[data-sortable]")  # type: ignore[attr-defined]
    _row_for_email(nojs_page, target["email"]).locator(
        'a[href^="/admin/accounts/reset?admin_id="]'
    ).click()
    nojs_page.wait_for_url(f"{base_url}{BASE}/reset?admin_id=*")  # type: ignore[attr-defined]
    nojs_form = 'form[action^="/admin/accounts/reset?admin_id="]'
    nojs_page.fill(f'{nojs_form} input[name="password"]', "218-browser-nojs-pw-Jj8")  # type: ignore[attr-defined]
    nojs_page.fill(f'{nojs_form} input[name="password_confirmation"]', "218-browser-nojs-pw-Jj8")  # type: ignore[attr-defined]
    nojs_page.fill(f'{nojs_form} input[name="reason"]', "218 browser no-js reset")  # type: ignore[attr-defined]
    nojs_page.check(f'{nojs_form} input[name="confirm_reset"]')  # type: ignore[attr-defined]
    nojs_page.click(f'{nojs_form} button[type="submit"]')  # type: ignore[attr-defined]
    nojs_page.wait_for_url(f"{base_url}{BASE}?message=admin_password_reset")  # type: ignore[attr-defined]
    assert nojs_page.locator(".admin-flash-success").count() == 1  # type: ignore[attr-defined]
    assert "218-browser-nojs-pw-Jj8" not in nojs_page.content()
    nojs.close()
