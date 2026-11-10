"""216-a G14 accounting operations: real-Chromium browser qualification.

Real browser, real uvicorn app, owned PostgreSQL (the ``owned_pg_url``
fixture is reused directly - this module is the SOLE PG owner of the run;
no ambient TEST_DATABASE_URL).  Every navigation, form and DB oracle goes
through the actual HTTP handlers and the real database.

Cases (file order is significant):

- real login; the four bounded candidate views render the honest 200-row
  cap, millions-of-tokens (tokm) readouts, masked credential canaries
  (FULL response, including the record-choice initial options), the
  read-only fence view (no release/reset/unblock surface), and hold
  views where unknown partial facts stay "unknown" (never zero);
- the expired dry-run -> signed review -> explicit confirm -> apply flow
  through the ACTUAL UI with a real DB oracle (exactly one settled row,
  exactly one decrement of the linked key counters);
- the beyond-cap path: a canary row genuinely outside the capped 200-row
  candidate view is found through the known-record picker's server
  search, selected into the managed hidden value, previewed, applied -
  and the credential-shaped model never reaches the DOM;
- the NO-JS operator flow: the plain textarea newline fallback, the
  fixed safe missing-reason refusal, the EXACT apply form action
  (real Jinja interpolation, no Python braces), and the keyboard
  confirm/apply;
- real desktop and narrow captures for operator visual review.

Safety: synthetic fixture rows only; no real provider, no email, no
respx mock, no ambient database.
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
from decimal import Decimal
from typing import Any

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import AuditLog, GatewayKey, QuotaReservation
from slaif_gateway.main import create_app
from tests.integration.test_admin_accounting_operations_216_postgres import (
    ADMIN_PASSWORD,
    CREDENTIAL_CANARY,
    _seed_all,
    _settings,
)
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
)

pytestmark = pytest.mark.playwright

LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = __import__("pathlib").Path("/tmp/slaif216")
DESKTOP = {"width": 1440, "height": 900}
NARROW = {"width": 420, "height": 860}

BASE = "/admin/accounting-operations"
VIEW_EXPIRED = f"{BASE}/expired-reservations"
VIEW_FENCES = f"{BASE}/external-tool-fences"
VIEW_HOLDS = f"{BASE}/external-tool-holds"
VIEW_PROVIDER = f"{BASE}/provider-completed-recovery"
APPLY_EXPIRED_ACTION = f"{BASE}/expired-reservations/apply"


# ---------------------------------------------------------------------------
# Real uvicorn (214/215 pattern)
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
# Module environment: owned PG (sole owner) + real uvicorn + Chromium
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def acct_ops_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / "browser-216a-lifecycle.json").write_text(
        json.dumps(
            {
                "container": _PG_STATE.get("pg_container"),
                "owner": _PG_STATE.get("pg_owner"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    settings = _settings(owned_pg_url)
    base = asyncio.run(_seed_all(owned_pg_url, settings))
    base["database_url"] = owned_pg_url
    base["admin_email"] = base["super_admin_email"]
    port = _free_port()
    base["base_url"] = f"http://127.0.0.1:{port}"
    app = create_app(settings)
    with _run_uvicorn_server(app, port):
        yield base


@pytest.fixture(scope="module")
def chromium(acct_ops_env) -> Iterator[object]:
    """Depends on ``acct_ops_env`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PostgreSQL seeding and the
    uvicorn app must complete BEFORE it starts."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


# Re-export the qualified owned-PG fixture under the expected name.
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: E402
    owned_pg_url as _owned_pg_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture


# ---------------------------------------------------------------------------
# Page + DB-oracle helpers
# ---------------------------------------------------------------------------


def _login(page: object, env: dict[str, Any]) -> None:
    base = str(env["base_url"])
    page.goto(f"{base}/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f"{LOGIN_FORM} button[type='submit']")  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _db_worker(database_url: str, coro_factory) -> Any:
    """One-shot DB oracle in a FRESH worker thread (214/215 pattern): the
    Playwright sync session owns an asyncio loop on the main thread, so
    ``asyncio.run`` must never be called from a test body."""

    def _run() -> Any:
        async def _q() -> Any:
            engine = create_async_engine(database_url, future=True)
            try:
                async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                    return await coro_factory(session)
            finally:
                await engine.dispose()

        return asyncio.run(_q())

    box: dict[str, Any] = {}

    def _thread() -> None:
        try:
            box["value"] = _run()
        except BaseException as exc:  # noqa: BLE001 - surface in the test
            box["error"] = exc

    worker = threading.Thread(target=_thread)
    worker.start()
    worker.join(timeout=60)
    assert not worker.is_alive(), "DB oracle worker timed out"
    if "error" in box:
        raise box["error"]
    return box["value"]


def _reservation_status(database_url: str, rid: uuid.UUID) -> str:
    async def _q(session) -> str:
        row = await session.get(QuotaReservation, rid)
        assert row is not None
        return row.status

    return _db_worker(database_url, _q)


def _key_counters(database_url: str, key_id: uuid.UUID) -> tuple[Decimal, int, int]:
    async def _q(session) -> tuple[Decimal, int, int]:
        key = await session.get(GatewayKey, key_id)
        assert key is not None
        return (
            key.cost_reserved_eur,
            key.tokens_reserved_total,
            key.requests_reserved_total,
        )

    return _db_worker(database_url, _q)


def _key_used_counters(database_url: str, key_id: uuid.UUID) -> tuple[Decimal, int, int]:
    async def _q(session) -> tuple[Decimal, int, int]:
        key = await session.get(GatewayKey, key_id)
        assert key is not None
        return (
            key.cost_used_eur,
            key.tokens_used_total,
            key.requests_used_total,
        )

    return _db_worker(database_url, _q)


def _ledger_facts(
    database_url: str, reservation_id: uuid.UUID
) -> tuple[str, Decimal, int]:
    from slaif_gateway.db.models import UsageLedger

    async def _q(session) -> tuple[str, Decimal, int]:
        row = (
            (
                await session.execute(
                    select(UsageLedger).where(UsageLedger.quota_reservation_id == reservation_id)
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        actual = row.actual_cost_eur if row.actual_cost_eur is not None else Decimal("0")
        return (row.accounting_status, actual, row.total_tokens)

    return _db_worker(database_url, _q)


def _audit_blob_has(database_url: str, action: str, entity_id: uuid.UUID, needle: str) -> bool:
    async def _q(session) -> bool:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == action, AuditLog.entity_id == entity_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            blob = json.dumps(
                [row.old_values, row.new_values, row.note, row.request_id], default=str
            )
            if needle in blob:
                return True
        return False

    return _db_worker(database_url, _q)


def _shoot(page: object, name: str, *, full_page: bool = True) -> None:
    page.screenshot(  # type: ignore[union-attr]
        path=str(SCREENSHOT_DIR / name), full_page=full_page
    )


# ---------------------------------------------------------------------------
# Cases (file order is significant)
# ---------------------------------------------------------------------------


def test_01_login_views_bounded_safe_and_masked(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    env = acct_ops_env
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)

        page.goto(f"{env['base_url']}{BASE}/")  # type: ignore[attr-defined]
        assert "Accounting Operations" in page.inner_text("body")  # type: ignore[union-attr]

        # Expired view: the honest 200-row cap (exactly 200 rendered),
        # millions-of-tokens readouts, and NO credential-shaped value in
        # the FULL response.
        page.goto(f"{env['base_url']}{VIEW_EXPIRED}")  # type: ignore[attr-defined]
        assert "Up to 200" in page.inner_text("body")  # type: ignore[union-attr]
        assert page.locator("table[data-sortable] tbody tr").count() == 200  # type: ignore[union-attr]
        assert "0.0001M" in page.inner_text("body")  # type: ignore[union-attr]  # 100-token filler rows
        assert CREDENTIAL_CANARY not in page.content()  # type: ignore[union-attr]
        # The exact known-record picker is a real record-choice control
        # with its associated help.
        assert page.locator("#acct-expired-exact-input").count() == 1  # type: ignore[union-attr]
        assert "at most 200 unique rows" in page.inner_text("#acct-expired-exact-help")  # type: ignore[union-attr]
        # Long 200-row candidate view: viewport capture stays legible for
        # review; the real 200-row DOM/bounds assertions remain the evidence.
        _shoot(page, "216a-desktop-expired-view.png", full_page=False)

        # Fences: read-only view, NO operator release/reset/unblock
        # surface exists on the page.
        page.goto(f"{env['base_url']}{VIEW_FENCES}")  # type: ignore[attr-defined]
        assert "Read-only view." in page.inner_text("body")  # type: ignore[union-attr]
        assert page.locator('form[action^="/admin/accounting-operations"]').count() == 0  # type: ignore[union-attr]
        assert page.locator('input[name="review_token"]').count() == 0  # type: ignore[union-attr]

        # Holds: partial tokens in millions-of-tokens units, and missing
        # partial facts stay "unknown" (never rendered as zero).
        page.goto(f"{env['base_url']}{VIEW_HOLDS}")  # type: ignore[attr-defined]
        holds_body = page.inner_text("body")  # type: ignore[union-attr]
        assert "0.0012M" in holds_body
        assert "unknown" in holds_body

        # Provider-completed view: the credential-shaped requested model
        # is MASKED in the row and WITHHELD from the model picker across
        # the FULL response (no masked-placeholder identity).
        page.goto(f"{env['base_url']}{VIEW_PROVIDER}")  # type: ignore[attr-defined]
        assert "***" in page.inner_text("body")  # type: ignore[union-attr]
        assert "0.0009M" in page.inner_text("body")  # type: ignore[union-attr]  # 900-token row
        assert CREDENTIAL_CANARY not in page.content()  # type: ignore[union-attr]
        _shoot(page, "216a-desktop-provider-view.png")
    finally:
        page.close()  # type: ignore[union-attr]


def test_02_expired_ui_preview_review_apply(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    env = acct_ops_env
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_EXPIRED}")  # type: ignore[attr-defined]

        # Select the first RENDERED row (a filler row beyond every key
        # A/B row) through the ACTUAL checkbox + reason + preview button.
        first_row = page.locator("table[data-sortable] tbody tr").first  # type: ignore[union-attr]
        rid = uuid.UUID(first_row.locator("td:nth-child(3) code").inner_text())  # type: ignore[union-attr]
        first_row.locator('input[name="target_id"]').check()  # type: ignore[union-attr]
        page.fill("#acct-expired-reason", "216 browser UI expired release")  # type: ignore[union-attr]
        page.click("#acct-expired-preview button[type=submit]")  # type: ignore[union-attr]

        # The signed review renders on the preview response (no
        # redirect) with the observed-vs-if-applied columns, the exact
        # reason, and the one-use sealed token.
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "What you are reviewing (current observed facts)" in body
        assert "0.0001M" in body  # observed reserved tokens (millions)
        assert "216 browser UI expired release" in body
        assert page.locator('input[name="review_token"]').count() == 1  # type: ignore[union-attr]
        _shoot(page, "216a-desktop-review.png")

        # Purposeful legibility captures of the SAME reviewed page: the
        # right-scrolled Details column and a narrow review viewport
        # (inside-card scroll preserved; no column redesign implied).
        page.locator(".table-wrap").first.evaluate(  # type: ignore[union-attr]
            "el => { el.scrollLeft = el.scrollWidth; }"
        )
        _shoot(page, "216a-desktop-review-details-scrolled.png", full_page=False)
        page.locator(".table-wrap").first.evaluate(  # type: ignore[union-attr]
            "el => { el.scrollLeft = 0; }"
        )
        page.set_viewport_size(NARROW)  # type: ignore[union-attr]
        _shoot(page, "216a-narrow-review.png", full_page=False)
        page.set_viewport_size(DESKTOP)  # type: ignore[union-attr]

        # The apply form targets the EXACT family (real interpolation).
        apply_form = page.locator(f'form[action="{APPLY_EXPIRED_ACTION}"]')  # type: ignore[union-attr]
        assert apply_form.count() == 1
        apply_form.locator("#acct-confirm-apply").check()  # type: ignore[union-attr]
        apply_form.locator('button[type="submit"]').click()  # type: ignore[union-attr]
        assert "1 row(s) settled" in page.inner_text("body")  # type: ignore[union-attr]

        # DB oracle: exactly one settled row and exactly one decrement
        # of the filler key's reserved counters.
        assert _reservation_status(env["database_url"], rid) == "expired"
        assert _key_counters(env["database_url"], env["key_fill"]) == (
            Decimal("2.04"),
            20_400,
            204,
        )
        _shoot(page, "216a-desktop-result.png")
    finally:
        page.close()  # type: ignore[union-attr]


def test_03_beyond_cap_picker_search_preview_apply(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    env = acct_ops_env
    rid = env["resv_a_canary"]
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_EXPIRED}")  # type: ignore[attr-defined]

        # The canary row is GENUINELY beyond the capped candidate view:
        # it is not among the rendered 200 rows, so no checkbox exists.
        assert str(rid) not in page.inner_text("table[data-sortable]")  # type: ignore[union-attr]

        # The known-record picker: typing the UUID triggers the server
        # search (beyond the latest-100 page), the option is selected
        # with ArrowDown+Enter, and the managed hidden value carries the
        # exact UUID (the form authority).
        page.fill("#acct-expired-exact-input", str(rid))  # type: ignore[union-attr]
        rc = page.locator(".rc-field:has(#acct-expired-exact-input)")  # type: ignore[union-attr]
        rc.locator(".rc-option").first.wait_for(state="visible", timeout=10000)  # type: ignore[union-attr]
        page.keyboard.press("ArrowDown")  # type: ignore[union-attr]
        page.keyboard.press("Enter")  # type: ignore[union-attr]
        chip = rc.locator(".rc-chip")  # type: ignore[union-attr]
        chip.first.wait_for(state="visible", timeout=10000)  # type: ignore[union-attr]
        assert str(rid)[:8] in chip.first.inner_text()  # type: ignore[union-attr]
        hidden = [i.input_value() for i in rc.locator("input.rc-value").all()]  # type: ignore[union-attr]
        assert str(rid) in hidden

        page.fill("#acct-expired-reason", "216 browser beyond-cap canary release")  # type: ignore[union-attr]
        page.click("#acct-expired-preview button[type=submit]")  # type: ignore[union-attr]

        # The credential-shaped model never reaches the DOM on the
        # review page (masked projection + withheld picker).
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "What you are reviewing (current observed facts)" in body
        assert CREDENTIAL_CANARY not in page.content()  # type: ignore[union-attr]

        apply_form = page.locator(f'form[action="{APPLY_EXPIRED_ACTION}"]')  # type: ignore[union-attr]
        apply_form.locator("#acct-confirm-apply").check()  # type: ignore[union-attr]
        apply_form.locator('button[type="submit"]').click()  # type: ignore[union-attr]
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "1 row(s) settled" in body
        assert CREDENTIAL_CANARY not in page.content()  # type: ignore[union-attr]

        # DB oracle: settled once; key A counters decremented exactly
        # once; the audit trail never carries the credential.
        assert _reservation_status(env["database_url"], rid) == "expired"
        assert _key_counters(env["database_url"], env["key_a"]) == (
            Decimal("1.00"),
            10_000,
            100,
        )
        assert (
            _audit_blob_has(
                env["database_url"],
                "quota_reservation_expired",
                rid,
                CREDENTIAL_CANARY,
            )
            is False
        )
        _shoot(page, "216a-desktop-beyond-cap-result.png")
    finally:
        page.close()  # type: ignore[union-attr]


def test_04_no_js_expired_flow_and_exact_apply_action(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    env = acct_ops_env
    browser = chromium  # type: ignore[union-attr]
    context = browser.new_context(viewport=DESKTOP, java_script_enabled=False)
    try:
        page = context.new_page()
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_EXPIRED}")  # type: ignore[attr-defined]

        # NO-JS: the exact field is the plain newline-fallback textarea
        # (the form keeps its exact wire shape).
        assert page.locator("textarea[name='exact_reservation_id']").count() == 1  # type: ignore[union-attr]

        # Missing reason: the fixed safe refusal (400 page), nothing
        # sealed.  The refusal page is an error surface, so return to the
        # view and submit again WITH a reason.
        page.locator('input[name="target_id"]').first.check()  # type: ignore[union-attr]
        page.click("#acct-expired-preview button[type=submit]")  # type: ignore[union-attr]
        assert "A nonblank audit reason is required." in page.inner_text("body")  # type: ignore[union-attr]
        assert page.locator('input[name="review_token"]').count() == 0  # type: ignore[union-attr]

        # WITH a reason: the review seals, and the apply form is plain
        # HTML with the EXACT family action (no Python-like braces).
        page.goto(f"{env['base_url']}{VIEW_EXPIRED}")  # type: ignore[attr-defined]
        page.locator('input[name="target_id"]').first.check()  # type: ignore[attr-defined]
        page.fill("#acct-expired-reason", "216 browser no-js expired release")  # type: ignore[attr-defined]
        page.click("#acct-expired-preview button[type=submit]")  # type: ignore[attr-defined]
        assert "What you are reviewing (current observed facts)" in page.inner_text("body")  # type: ignore[union-attr]
        apply_form = page.locator(f'form[action="{APPLY_EXPIRED_ACTION}"]')  # type: ignore[union-attr]
        assert apply_form.count() == 1

        # Keyboard confirm + apply (the details is open by default).  The
        # keyboard API does NOT carry locator auto-waits, so the checkbox
        # state is asserted explicitly and the form-POST navigation is
        # awaited before reading the result.
        page.focus("#acct-confirm-apply")  # type: ignore[union-attr]
        page.keyboard.press("Space")  # type: ignore[union-attr]
        assert page.locator("#acct-confirm-apply").is_checked()  # type: ignore[union-attr]
        page.focus('form[action="%s"] button[type="submit"]' % APPLY_EXPIRED_ACTION)  # type: ignore[union-attr]
        with page.expect_navigation():  # type: ignore[union-attr]
            page.keyboard.press("Enter")  # type: ignore[union-attr]
        assert page.url.endswith(APPLY_EXPIRED_ACTION)  # type: ignore[union-attr]
        assert "1 row(s) settled" in page.inner_text("body")  # type: ignore[union-attr]
    finally:
        context.close()


def test_04b_hold_finalize_actuals_through_ui(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    """Actual existing hold form: finalize with operator-asserted actuals
    (manual provenance, sealed explicit no-charge choice, truthful result
    and durable terminal ledger facts)."""
    env = acct_ops_env
    rid = env["resv_f"]
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_HOLDS}")  # type: ignore[attr-defined]

        # Select the ACTUAL held row by its rendered reservation id.
        row = page.locator("table[data-sortable] tbody tr", has_text=str(rid)).first  # type: ignore[union-attr]
        row.locator('input[name="reservation_id"]').check()  # type: ignore[union-attr]
        page.select_option("#acct-hold-action", "finalize-actual")  # type: ignore[union-attr]
        page.fill("#acct-hold-cost", "0.42")  # type: ignore[union-attr]
        page.fill("#acct-hold-tokens", "2500")  # type: ignore[union-attr]
        page.check("#acct-hold-outcome-success")  # type: ignore[union-attr]
        page.fill("#acct-hold-reason", "216 browser hold finalize actuals")  # type: ignore[union-attr]
        page.click("#acct-hold-preview button[type=submit]")  # type: ignore[union-attr]

        # Reviewed assertions with honest manual provenance; the explicit
        # no-charge choice is sealed as NOT confirmed for finalize.
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "What you are reviewing (current observed facts)" in body
        assert "operator_asserted" in body
        assert "0.42 EUR" in body
        assert "sealed: not confirmed" in body
        apply_form = page.locator('form[action="/admin/accounting-operations/external-tool-holds/apply"]')  # type: ignore[union-attr]
        assert apply_form.count() == 1
        apply_form.locator("#acct-confirm-apply").check()  # type: ignore[union-attr]
        apply_form.locator('button[type="submit"]').click()  # type: ignore[union-attr]
        assert "1 row(s) settled" in page.inner_text("body")  # type: ignore[union-attr]

        # DB oracle: terminal ledger facts and exactly the operator-
        # asserted amounts booked on the key (no duplicate provider
        # evidence); reserved counters released.
        status, actual, tokens = _ledger_facts(env["database_url"], rid)
        assert status == "finalized"
        assert actual == Decimal("0.42")
        assert tokens == 2500
        assert _key_used_counters(env["database_url"], env["key_f"]) == (
            Decimal("1.52"),
            2525,
            4,
        )
        assert _key_counters(env["database_url"], env["key_f"]) == (
            Decimal("0"),
            0,
            0,
        )
    finally:
        page.close()  # type: ignore[union-attr]


def test_04c_hold_release_no_charge_through_ui(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    """Actual existing hold form: release with no charge requires its
    EXPLICIT confirmation and accepts no actual values; the reserved
    counters are released without any charge."""
    env = acct_ops_env
    rid = env["resv_f3"]
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_HOLDS}")  # type: ignore[attr-defined]

        row = page.locator("table[data-sortable] tbody tr", has_text=str(rid)).first  # type: ignore[union-attr]
        row.locator('input[name="reservation_id"]').check()  # type: ignore[union-attr]
        page.select_option("#acct-hold-action", "release-no-charge")  # type: ignore[union-attr]

        # Without the explicit no-charge confirmation the preview refuses
        # before any seal (fixed safe message, no token).
        page.fill("#acct-hold-reason", "216 browser hold release no charge")  # type: ignore[union-attr]
        page.click("#acct-hold-preview button[type=submit]")  # type: ignore[union-attr]
        assert "no-charge confirmation" in page.inner_text("body")  # type: ignore[union-attr]
        assert page.locator('input[name="review_token"]').count() == 0  # type: ignore[union-attr]

        # WITH the explicit confirmation: the review seals the choice.
        # The refusal above is a fixed 400 error page (the holds form is not
        # re-rendered), so re-enter the real flow and check the box.
        page.goto(f"{env['base_url']}{VIEW_HOLDS}")  # type: ignore[attr-defined]
        row = page.locator("table[data-sortable] tbody tr", has_text=str(rid)).first  # type: ignore[union-attr]
        row.locator('input[name="reservation_id"]').check()  # type: ignore[union-attr]
        page.select_option("#acct-hold-action", "release-no-charge")  # type: ignore[union-attr]
        page.check("#acct-hold-nocharge")  # type: ignore[union-attr]
        page.fill("#acct-hold-reason", "216 browser hold release no charge")  # type: ignore[union-attr]
        page.click("#acct-hold-preview button[type=submit]")  # type: ignore[union-attr]
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "sealed: explicitly confirmed" in body
        apply_form = page.locator('form[action="/admin/accounting-operations/external-tool-holds/apply"]')  # type: ignore[union-attr]
        apply_form.locator("#acct-confirm-apply").check()  # type: ignore[union-attr]
        apply_form.locator('button[type="submit"]').click()  # type: ignore[union-attr]
        assert "1 row(s) settled" in page.inner_text("body")  # type: ignore[union-attr]

        # DB oracle: released at zero (never a provider-verified amount);
        # prior ordinary usage is untouched.
        status, actual, tokens = _ledger_facts(env["database_url"], rid)
        assert status == "failed"
        assert actual == Decimal("0")
        assert tokens == 0
        assert _key_used_counters(env["database_url"], env["key_f3"]) == (
            Decimal("0.75"),
            10,
            1,
        )
        assert _key_counters(env["database_url"], env["key_f3"]) == (
            Decimal("0"),
            0,
            0,
        )
    finally:
        page.close()  # type: ignore[union-attr]


def test_04d_provider_completed_recovery_through_ui(
    acct_ops_env: dict[str, Any], chromium: object
) -> None:
    """Actual existing provider-completed form: recovery uses ONLY the
    stored authoritative evidence (no cost override); the credential-
    shaped model stays masked/withheld across the whole flow."""
    env = acct_ops_env
    lid = env["ledger_p"]
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_PROVIDER}")  # type: ignore[attr-defined]

        # Select the ACTUAL row by its rendered usage-ledger id.
        row = page.locator("table[data-sortable] tbody tr", has_text=str(lid)).first  # type: ignore[union-attr]
        row.locator('input[name="target_id"]').check()  # type: ignore[union-attr]
        page.fill("#acct-pc-reason", "216 browser provider recovery")  # type: ignore[union-attr]
        page.click("#acct-pc-preview button[type=submit]")  # type: ignore[union-attr]

        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "What you are reviewing (current observed facts)" in body
        assert "no cost override" in body
        assert CREDENTIAL_CANARY not in page.content()  # type: ignore[union-attr]
        apply_form = page.locator(
            'form[action="/admin/accounting-operations/provider-completed-recovery/apply"]'
        )  # type: ignore[union-attr]
        assert apply_form.count() == 1
        apply_form.locator("#acct-confirm-apply").check()  # type: ignore[union-attr]
        apply_form.locator('button[type="submit"]').click()  # type: ignore[union-attr]
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "1 row(s) settled" in body
        assert CREDENTIAL_CANARY not in page.content()  # type: ignore[union-attr]

        # DB oracle: stored evidence kept (0.28, never overridden); the
        # recovery marker is resolved; reserved counters released.
        status, actual, tokens = _ledger_facts(env["database_url"], env["resv_p"])
        assert status == "finalized"
        assert actual == Decimal("0.28")
        assert tokens == 900
        assert _key_used_counters(env["database_url"], env["key_p"]) == (
            Decimal("2.28"),
            920,
            5,
        )
        assert _key_counters(env["database_url"], env["key_p"]) == (
            Decimal("0"),
            0,
            0,
        )
    finally:
        page.close()  # type: ignore[union-attr]


def test_05_desktop_and_narrow_captures(acct_ops_env: dict[str, Any], chromium: object) -> None:
    env = acct_ops_env
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{BASE}/")  # type: ignore[attr-defined]
        assert "Accounting Operations" in page.inner_text("body")  # type: ignore[union-attr]
        _shoot(page, "216a-desktop-index.png")
    finally:
        page.close()  # type: ignore[union-attr]

    browser = chromium  # type: ignore[union-attr]
    context = browser.new_context(viewport=NARROW)
    try:
        page = context.new_page()
        _login(page, env)
        page.goto(f"{env['base_url']}{VIEW_EXPIRED}")  # type: ignore[attr-defined]
        assert page.locator("h1").first.is_visible()  # type: ignore[union-attr]
        # The narrow layout stays contained (no horizontal overflow).
        assert page.evaluate("document.documentElement.scrollWidth") <= NARROW["width"]  # type: ignore[union-attr]
        _shoot(page, "216a-narrow-expired-view.png", full_page=False)
    finally:
        context.close()
