"""215-a G12 email operations: real-Chromium browser qualification.

Real browser, real uvicorn app, owned PostgreSQL (the ``owned_pg_url``
fixture is reused directly - this module is the SOLE PG owner of the run;
no ambient TEST_DATABASE_URL) plus a small STANDARD-LIBRARY loopback-only
synthetic SMTP sink (LOCAL MOCK SMTP, not an inbox/provider/TLS
qualification; every transport field is explicit: 127.0.0.1 sink port,
no real auth, no TLS).  Every navigation, form and DB oracle goes
through the actual HTTP handlers and the real database.

Cases (file order is significant):

- real login; the email-deliveries list renders the canonical status
  dropdown (six persisted statuses, no secret-lifecycle labels) and the
  inclusive UTC date controls with associated help;
- real UI filtering: the status filter and the exact owner-email filter
  change the rendered TBODY; a past date window renders no rows;
- detail: the shared finite latest-failure provenance (known code, and
  ``unavailable`` for an unknown recorded code with no raw provider
  prose), the same-secret history blocker, and the retry-failed form
  with its actual control IDs and help;
- the explicit retry-failed send-now flow through the ACTUAL UI with a
  REAL loopback sink message-count proof (exactly one message, to the
  prepared destination, row finalized to sent);
- the NO-JS operator flow: send-now without the confirm checkbox shows
  the confirmation requirement, and WITH it the ordinary pending send
  reaches the sink exactly once;
- the SMTP test surface: prepare -> reviewed facts -> retriable
  missing-confirm error keeps the one-use form -> confirm -> accepted
  (real sink message) -> reload;
- no-JS keyboard pagination: filter-preserving Next/Previous links and
  continuing row ordinals, navigated by keyboard Enter on the links;
- real desktop and narrow captures for operator visual review.

The ordinary pending ENQUEUE UI path is qualified with a recording stub
at the existing enqueue seam (exact three-UUID payload, truthful queued /
requested-but-unconfirmed feedback) - NO real broker contact; the broker
URL in settings stays inert for every other case.

Safety: synthetic fixture rows only; no real recipient, no real SMTP
account, no provider/Codex call, no respx mock.
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
from typing import Any
from urllib.parse import urlencode

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import EmailDelivery
from slaif_gateway.main import create_app
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
)
from tests.integration.test_admin_email_operations_215_postgres import (
    ADMIN_PASSWORD,
    LocalMockSmtpSink,
    RAW_PROSE,
    _create_pending_delivery,
    _seed_data,
    _seed_error_audit,
    _seed_sentinel_key,
    _seed_sibling_delivery,
    _settings,
    _set_delivery_status,
)

pytestmark = pytest.mark.playwright

LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = __import__("pathlib").Path("/tmp/slaif215")
DESKTOP = {"width": 1440, "height": 900}
NARROW = {"width": 420, "height": 860}
CANONICAL_STATUSES = ["pending", "sending", "sent", "failed", "ambiguous", "cancelled"]


# ---------------------------------------------------------------------------
# Real uvicorn (214 pattern)
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
# Module environment: owned PG (sole owner) + real uvicorn + sink + Chromium
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def email_ops_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / "browser-215a-lifecycle.json").write_text(
        json.dumps({"container": _PG_STATE.get("pg_container"), "owner": _PG_STATE.get("pg_owner")}, indent=2),
        encoding="utf-8",
    )
    sink = LocalMockSmtpSink().start()
    try:
        settings = _settings(owned_pg_url, smtp_port=int(sink.port))
        base = asyncio.run(_seed_data(owned_pg_url, settings))
        owner_a = base.pop("owner_a")
        owner_b = base.pop("owner_b")
        owner_c = base.pop("owner_c")
        # State matrix (file order is significant):
        #  - pending (owner A): ordinary send surface (NO-JS flow)
        #  - failed (owner A): retry-failed UI surface + known-code audit
        #  - 9 filler pending (owner A): pagination depth
        #  - sending + same-secret failed (owner B): history blocker
        #  - failed+raw prose (owner C): raw prose must never reach the DOM
        pending = _create_pending_delivery(owned_pg_url, settings, owner=owner_a, label="b-pending")
        failed = _create_pending_delivery(owned_pg_url, settings, owner=owner_a, label="b-failed")
        filler_enqueue = _create_pending_delivery(owned_pg_url, settings, owner=owner_a, label="b-fill-01")
        for n in range(2, 10):
            _create_pending_delivery(owned_pg_url, settings, owner=owner_a, label=f"b-fill-{n:02d}")
        hist_a = _create_pending_delivery(owned_pg_url, settings, owner=owner_b, label="b-hist-send")
        _set_delivery_status(owned_pg_url, hist_a["email_delivery_id"], "sending")
        hist_b = _seed_sibling_delivery(
            owned_pg_url,
            one_time_secret_id=hist_a["one_time_secret_id"],
            gateway_key_id=hist_a["gateway_key_id"],
            owner_id=owner_b.id,
            status="failed",
            recipient_email="histb-sibling-215b@example.org",
            label="b-hist-failed",
        )
        failed_prose = _create_pending_delivery(owned_pg_url, settings, owner=owner_c, label="b-failed-prose")
        _set_delivery_status(owned_pg_url, failed["email_delivery_id"], "failed")
        _set_delivery_status(owned_pg_url, failed_prose["email_delivery_id"], "failed", error_message=RAW_PROSE)
        _seed_error_audit(owned_pg_url, failed["email_delivery_id"], error_code="smtp_send_error")
        _seed_error_audit(owned_pg_url, failed_prose["email_delivery_id"], error_code="totally-unknown-code")
        _seed_sentinel_key(owned_pg_url, owner_a)

        base.update(
            pending=pending,
            failed=failed,
            failed_prose=failed_prose,
            hist_a=hist_a,
            hist_b=hist_b,
            filler_enqueue=filler_enqueue,
            owner_a_email=owner_a.email,
            owner_b_id=owner_b.id,
            sink=sink,
            database_url=owned_pg_url,
        )
        port = _free_port()
        base["base_url"] = f"http://127.0.0.1:{port}"
        app = create_app(settings)
        with _run_uvicorn_server(app, port):
            yield base
    finally:
        sink.stop()


@pytest.fixture(scope="module")
def chromium(email_ops_env) -> Iterator[object]:
    """Depends on ``email_ops_env`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PostgreSQL seeding and the
    uvicorn app must complete BEFORE it starts (and the browser closes
    before the sink teardown)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


# Re-export the qualified owned-PG fixture under the expected name.
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: E402
    owned_pg_url as _owned_pg_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------


def _login(page: object, env: dict[str, Any]) -> None:
    base = str(env["base_url"])
    page.goto(f"{base}/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f"{LOGIN_FORM} button[type='submit']")  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _qurl(base: str, path: str, **params: object) -> str:
    """Build an absolute URL with a query string (Playwright goto has no params)."""
    query = urlencode({k: str(v) for k, v in params.items()})
    return f"{base}{path}?{query}" if query else f"{base}{path}"


def _row_link(delivery_id: uuid.UUID) -> str:
    return f"/admin/email-deliveries/{delivery_id}"


def _tbody_links(page: object) -> list[str]:
    """Detail hrefs of the ACTUAL rendered result rows (TBODY only)."""
    links: list[str] = []
    for anchor in page.locator("table[data-sortable] tbody tr td a").all():  # type: ignore[union-attr]
        href = anchor.get_attribute("href")  # type: ignore[union-attr]
        if href is not None:
            links.append(href)
    return links


def _ordinal_cells(page: object) -> list[str]:
    return [
        cell.strip()
        for cell in page.locator("table[data-sortable] tbody tr td.row-ordinal").all_inner_texts()  # type: ignore[union-attr]
    ]


def _db_worker(database_url: str, delivery_id: uuid.UUID) -> str:
    """One-shot DB oracle in a FRESH worker thread (214/215 pattern): the
    Playwright sync session owns an asyncio loop on the main thread, so
    ``asyncio.run`` must never be called from a test body."""

    def _run() -> str:
        async def _query() -> str:
            engine = create_async_engine(database_url, future=True)
            try:
                async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                    row = (
                        await session.execute(select(EmailDelivery).where(EmailDelivery.id == delivery_id))
                    ).scalar_one()
                    return row.status
            finally:
                await engine.dispose()

        return asyncio.run(_query())

    box: dict[str, Any] = {}

    def _thread() -> None:
        try:
            box["value"] = _run()
        except BaseException as exc:  # noqa: BLE001 - surface in the test
            box["error"] = exc

    worker = threading.Thread(target=_thread)
    worker.start()
    worker.join(timeout=30)
    assert not worker.is_alive(), "DB oracle worker timed out"
    if "error" in box:
        raise box["error"]
    return box["value"]


def _shoot(page: object, name: str, **viewport: int) -> None:
    if viewport:
        page.set_viewport_size(viewport)  # type: ignore[union-attr]
    page.screenshot(path=str(SCREENSHOT_DIR / name), full_page=True)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Cases (file order is significant)
# ---------------------------------------------------------------------------


def test_01_login_list_canonical_statuses_and_date_controls(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)

        page.goto(f"{env['base_url']}/admin/email-deliveries")  # type: ignore[attr-defined]
        # Real login landed on a real page with the list table.
        assert "Email Deliveries" in page.inner_text("body")  # type: ignore[union-attr]

        # Canonical persisted statuses ONLY: six options + "Any"; the
        # secret-lifecycle labels (consumed/expired) are NOT delivery
        # statuses and must not be offered as a query meaning.
        options = page.locator("#email-status-select option").all_inner_texts()  # type: ignore[union-attr]
        assert options == ["Any", *CANONICAL_STATUSES]
        assert "consumed" not in options and "expired" not in options
        assert page.locator("#email-status-help").count() == 1  # type: ignore[union-attr]

        # Inclusive UTC date controls with associated (visible) help.
        assert page.locator("#email-start-at-input").is_visible()  # type: ignore[union-attr]
        assert page.locator("#email-end-at-input").is_visible()  # type: ignore[union-attr]
        help_text = page.inner_text("#email-dates-help")  # type: ignore[union-attr]
        assert "UTC" in help_text and "inclusive" in help_text.lower()

        # All seeded rows render (14 deliveries across owners).
        body_links = _tbody_links(page)
        assert _row_link(env["pending"]["email_delivery_id"]) in body_links
        assert _row_link(env["failed"]["email_delivery_id"]) in body_links
        assert len(body_links) == 14

        _shoot(page, "215a-desktop-list.png")
    finally:
        page.close()  # type: ignore[union-attr]


def test_02_real_ui_status_and_exact_filters_change_tbody(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}/admin/email-deliveries")  # type: ignore[attr-defined]

        # Status filter through the ACTUAL select + submit button. The
        # FULL form is submitted, including the BLANK date controls:
        # that must normalize to unbounded (a real form submit, not a
        # hand-built date query) and return the filtered table.
        assert page.input_value("#email-start-at-input") == ""  # type: ignore[union-attr]
        assert page.input_value("#email-end-at-input") == ""  # type: ignore[union-attr]
        page.select_option("#email-status-select", "failed")  # type: ignore[union-attr]
        page.click('#email-deliveries-filter button[type="submit"]')  # type: ignore[union-attr]
        page.wait_for_url("**/admin/email-deliveries?status=failed*")  # type: ignore[attr-defined]
        links = _tbody_links(page)
        assert _row_link(env["failed"]["email_delivery_id"]) in links
        assert _row_link(env["failed_prose"]["email_delivery_id"]) in links
        assert _row_link(env["hist_b"]["email_delivery_id"]) in links
        assert _row_link(env["pending"]["email_delivery_id"]) not in links

        # Exact delivery UUID (advanced section) through the ACTUAL
        # picker semantics: the shared record-choices control moves form
        # authority to a managed hidden selected value, so typing alone
        # is a search, not a selection - filter the rendered options,
        # highlight the match, Enter selects it (visible chip), and the
        # submitted value is the exact UUID.
        page.goto(f"{env['base_url']}/admin/email-deliveries")  # type: ignore[attr-defined]
        page.click("#email-advanced-summary")  # type: ignore[union-attr]
        page.fill("#email-delivery-id-input", str(env["failed"]["email_delivery_id"]))  # type: ignore[union-attr]
        delivery_rc = page.locator(".rc-field:has(#email-delivery-id-input)")  # type: ignore[union-attr]
        delivery_rc.locator(".rc-option").first.wait_for(state="visible", timeout=10000)  # type: ignore[union-attr]
        page.keyboard.press("ArrowDown")  # type: ignore[union-attr]
        page.keyboard.press("Enter")  # type: ignore[union-attr]
        chip = delivery_rc.locator(".rc-chip")  # type: ignore[union-attr]
        chip.first.wait_for(state="visible", timeout=10000)  # type: ignore[union-attr]
        # The chip shows the option label; the FORM AUTHORITY is the
        # managed hidden selected value - it must carry the exact UUID.
        assert str(env["failed"]["email_delivery_id"])[:8] in chip.first.inner_text()  # type: ignore[union-attr]
        assert delivery_rc.locator("input.rc-value").first.input_value() == str(  # type: ignore[union-attr]
            env["failed"]["email_delivery_id"]
        )
        page.click('#email-deliveries-filter button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_url("**delivery_id=*")  # type: ignore[attr-defined]
        links = _tbody_links(page)
        assert links == [_row_link(env["failed"]["email_delivery_id"])]

        # A past date window renders the empty state (inclusive bounds,
        # naive input treated as UTC - usable, not an error).
        page.goto(
            _qurl(
                str(env["base_url"]),
                "/admin/email-deliveries",
                start_at="1999-01-01T00:00:00",
                end_at="1999-01-02T00:00:00",
            )
        )  # type: ignore[union-attr]
        assert "No email deliveries found." in page.inner_text("body")  # type: ignore[union-attr]
        assert _tbody_links(page) == []
    finally:
        page.close()  # type: ignore[union-attr]


def test_03_detail_provenance_and_retry_form_controls(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)

        # Known finite code: the shared projection renders code/action.
        page.goto(f"{env['base_url']}{_row_link(env['failed']['email_delivery_id'])}")  # type: ignore[union-attr]
        assert "Last recorded failure" in page.inner_text("body")  # type: ignore[union-attr]
        assert "smtp_send_error" in page.inner_text("body")  # type: ignore[union-attr]
        assert "email_key_failed" in page.inner_text("body")  # type: ignore[union-attr]
        # The explicit retry-failed form with actual control IDs + help.
        assert page.locator('#retry-mode-select option[value="send-now"]').count() == 1  # type: ignore[union-attr]
        assert page.locator("#retry-reason-input").is_visible()  # type: ignore[union-attr]
        assert page.locator("#retry-confirm-checkbox").count() == 1  # type: ignore[union-attr]
        assert "1024 UTF-8 bytes" in page.inner_text("#retry-reason-help")  # type: ignore[union-attr]
        _shoot(page, "215a-desktop-detail-failed.png")

        # Unknown recorded code: the finite `unavailable` label, never
        # the raw provider prose (it must not reach the DOM).
        page.goto(f"{env['base_url']}{_row_link(env['failed_prose']['email_delivery_id'])}")  # type: ignore[union-attr]
        assert "unavailable" in page.inner_text("body")  # type: ignore[union-attr]
        assert RAW_PROSE not in page.inner_text("body")  # type: ignore[union-attr]

        # Same-secret history: the FAILED row is blocked by its sending
        # sibling (shared Core truth), no retry form.
        page.goto(f"{env['base_url']}{_row_link(env['hist_b']['email_delivery_id'])}")  # type: ignore[union-attr]
        assert "A prior delivery attempt for this one-time secret is sending" in page.inner_text("body")  # type: ignore[union-attr]
        assert page.locator("#retry-mode-select").count() == 0  # type: ignore[union-attr]

        # Pending row: the ordinary send/enqueue forms, no retry form.
        page.goto(f"{env['base_url']}{_row_link(env['pending']['email_delivery_id'])}")  # type: ignore[union-attr]
        assert page.locator('form[action$="/send-now"]').count() == 1  # type: ignore[union-attr]
        assert page.locator('form[action$="/enqueue"]').count() == 1  # type: ignore[union-attr]
        assert page.locator("#retry-mode-select").count() == 0  # type: ignore[union-attr]
    finally:
        page.close()  # type: ignore[union-attr]


def test_04_retry_failed_send_now_through_ui_reaches_sink_once(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    sink: LocalMockSmtpSink = env["sink"]
    before = len(sink.messages)
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)
        page.goto(f"{env['base_url']}{_row_link(env['failed']['email_delivery_id'])}")  # type: ignore[union-attr]

        # The explicit retry-failed flow through the ACTUAL UI.
        page.select_option("#retry-mode-select", "send-now")  # type: ignore[union-attr]
        page.fill("#retry-reason-input", "215 browser UI retry after SMTP outage")  # type: ignore[union-attr]
        page.check("#retry-confirm-checkbox")  # type: ignore[union-attr]
        page.click('form[action$="/retry-failed"] button[type="submit"]')  # type: ignore[union-attr]
        page.wait_for_url(f"**{_row_link(env['failed']['email_delivery_id'])}?message=*")  # type: ignore[attr-defined]
        assert "Key email delivery sent." in page.inner_text("body")  # type: ignore[union-attr]

        # Exactly ONE real message reached the loopback sink, to the
        # prepared destination (current owner, refreshed at execution).
        assert len(sink.messages) == before + 1
        envelope = sink.messages[-1]
        assert envelope["mail_from"] == "noreply-215@example.org"
        assert envelope["rcpt_to"] == [env["owner_a_email"]]
        assert "Your SLAIF API Gateway key" in envelope["data"]

        # The row finalized to sent (independent DB oracle).
        assert _db_worker(env["database_url"], env["failed"]["email_delivery_id"]) == "sent"

        # Repeat through the UI: the consumed secret is never made
        # resendable - the truthful not-failed refusal, no 2nd message.
        page.goto(f"{env['base_url']}{_row_link(env['failed']['email_delivery_id'])}")  # type: ignore[union-attr]
        assert page.locator("#retry-mode-select").count() == 0  # type: ignore[union-attr]
        _shoot(page, "215a-desktop-detail-after-retry.png")
    finally:
        page.close()  # type: ignore[union-attr]


def test_05_no_js_send_now_missing_confirm_then_confirm(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    sink: LocalMockSmtpSink = env["sink"]
    before = len(sink.messages)
    browser = chromium  # type: ignore[union-attr]
    context = browser.new_context(viewport=DESKTOP, java_script_enabled=False)
    try:
        page = context.new_page()
        _login(page, env)
        page.goto(f"{env['base_url']}{_row_link(env['pending']['email_delivery_id'])}")  # type: ignore[union-attr]

        # NO-JS: submit the send form WITHOUT ticking the confirm
        # checkbox -> the fixed confirmation requirement, no SMTP.
        page.fill('form[action$="/send-now"] textarea[name="reason"]', "215 browser no-js send")  # type: ignore[union-attr]
        page.click('form[action$="/send-now"] button[type="submit"]')  # type: ignore[union-attr]
        page.wait_for_url(f"**{_row_link(env['pending']['email_delivery_id'])}?message=*")  # type: ignore[attr-defined]
        assert "Confirm email delivery before sending." in page.inner_text("body")  # type: ignore[union-attr]
        assert len(sink.messages) == before

        # Same NO-JS page WITH the confirm checkbox -> the ordinary
        # pending send reaches the sink exactly once.
        page.check('form[action$="/send-now"] input[name="confirm_send"]')  # type: ignore[union-attr]
        page.click('form[action$="/send-now"] button[type="submit"]')  # type: ignore[union-attr]
        page.wait_for_url(f"**{_row_link(env['pending']['email_delivery_id'])}?message=*")  # type: ignore[attr-defined]
        assert "Key email delivery sent." in page.inner_text("body")  # type: ignore[union-attr]
        assert len(sink.messages) == before + 1
        assert _db_worker(env["database_url"], env["pending"]["email_delivery_id"]) == "sent"
    finally:
        context.close()


def test_06_smtp_test_prepare_review_confirm_accepted(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    sink: LocalMockSmtpSink = env["sink"]
    before = len(sink.messages)
    page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
    try:
        _login(page, env)

        # From the Operations index: the SMTP test surface is linked.
        page.goto(f"{env['base_url']}/admin/operations/")  # type: ignore[union-attr]
        assert page.locator('a[href="/admin/email-operations/smtp-test"]').count() >= 1  # type: ignore[union-attr]
        page.click('a[href="/admin/email-operations/smtp-test"]')  # type: ignore[union-attr]
        page.wait_for_url("**/admin/email-operations/smtp-test")  # type: ignore[attr-defined]

        recipient = f"215-browser-ops-{uuid.uuid4().hex[:8]}@example.invalid"
        page.fill("#smtp-test-recipient", recipient)  # type: ignore[union-attr]
        page.fill("#smtp-test-subject", "215 browser SMTP review subject")  # type: ignore[union-attr]
        page.fill("#smtp-test-body", "215 browser reviewed test body line 1\nline 2")  # type: ignore[union-attr]
        page.click('form[action$="/smtp-test/review"] button[type="submit"]')  # type: ignore[union-attr]
        page.wait_for_url("**/admin/email-operations/smtp-test/review")  # type: ignore[attr-defined]

        # The reviewed facts render verbatim, with the retryable one-use
        # form (now with its actual control ID + associated help).
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert recipient in body
        assert "215 browser SMTP review subject" in body
        assert "215 browser reviewed test body line 1" in body
        assert page.locator("#smtp-test-confirm-checkbox").count() == 1  # type: ignore[union-attr]
        assert "One-time confirmation" in page.inner_text("#smtp-test-confirm-help")  # type: ignore[union-attr]
        _shoot(page, "215a-desktop-smtp-review.png")

        # Narrow (420px) capture of the reviewed form for visual review;
        # the page width must stay contained (the reviewed body preview
        # scrolls inside its existing scroll-box class).  Restore the
        # desktop viewport afterwards.
        page.set_viewport_size(NARROW)  # type: ignore[union-attr]
        _shoot(page, "215a-narrow-smtp-review.png")
        assert page.evaluate("document.documentElement.scrollWidth") <= NARROW["width"]  # type: ignore[union-attr]
        page.set_viewport_size(DESKTOP)  # type: ignore[union-attr]

        # Apply WITHOUT the confirm checkbox: the missing-confirm error
        # is RETRIABLE - the valid one-use form stays (no restart).
        page.click('form[action$="/smtp-test/apply"] button[type="submit"]')  # type: ignore[union-attr]
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "confirm" in body.lower()
        assert page.locator("#smtp-test-confirm-checkbox").count() == 1  # type: ignore[union-attr]
        assert len(sink.messages) == before  # no claim, no send

        # WITH the confirm checkbox: the reviewed test is accepted by
        # the configured (loopback) SMTP service - exactly one message.
        page.check("#smtp-test-confirm-checkbox")  # type: ignore[union-attr]
        page.click('form[action$="/smtp-test/apply"] button[type="submit"]')  # type: ignore[union-attr]
        assert "accepted by the configured SMTP service" in page.inner_text("body")  # type: ignore[union-attr]
        assert len(sink.messages) == before + 1
        assert sink.messages[-1]["rcpt_to"] == [recipient]

        # TRUTHFUL reload: observe the ACTUAL method/path. A reload of a
        # POST-loaded page may resubmit the last POST: the durable
        # one-use claim must then refuse the repeated token truthfully
        # (already used), with no second send and no live token.
        reload_before = len(sink.messages)
        with page.expect_response(lambda response: "smtp-test/apply" in response.url) as reload_info:  # type: ignore[union-attr]
            page.reload()  # type: ignore[union-attr]
        reload_response = reload_info.value
        reload_request = reload_response.request  # type: ignore[union-attr]
        assert reload_response.status == 200
        assert reload_request.method in ("GET", "POST")  # type: ignore[attr-defined]
        body = page.inner_text("body")  # type: ignore[union-attr]
        if reload_request.method == "POST":  # type: ignore[attr-defined]
            # Honest: the browser resubmitted the consumed intent and
            # the one-use claim refused it (no second send).
            assert "already used" in body
        else:
            # Honest: the direct-GET recovery surface.
            assert "This page only accepts the reviewed test submission" in body
        assert page.locator('input[name="review_token"]').count() == 0  # type: ignore[union-attr]
        assert len(sink.messages) == reload_before  # unchanged sink count

        # Direct GET of the apply URL: the safe NO-SEND recovery surface
        # (status 200, fixed notice, recovery link, no live token) and
        # it must not send or re-claim.
        get_response = page.goto(f"{env['base_url']}/admin/email-operations/smtp-test/apply")  # type: ignore[union-attr]
        assert get_response is not None and get_response.status == 200
        body = page.inner_text("body")  # type: ignore[union-attr]
        assert "This page only accepts the reviewed test submission" in body
        assert "does not send or resend" in body
        assert page.locator('a[href="/admin/email-operations/smtp-test"]').count() >= 1  # type: ignore[union-attr]
        assert page.locator('input[name="review_token"]').count() == 0  # type: ignore[union-attr]
        assert len(sink.messages) == reload_before

        # The surface is usable for a NEW test: the prepare page shows a
        # fresh form with no live reviewed token (the one-use intent is
        # consumed; a repeat submit is refused natively as "already
        # used" - proven in the native PG qualification).
        page.goto(f"{env['base_url']}/admin/email-operations/smtp-test")  # type: ignore[union-attr]
        assert "SMTP Test" in page.inner_text("body")  # type: ignore[union-attr]
        assert page.locator("#smtp-test-recipient").is_visible()  # type: ignore[union-attr]
        assert page.locator('input[name="review_token"]').count() == 0  # type: ignore[union-attr]
    finally:
        page.close()  # type: ignore[union-attr]


def test_07_enqueue_ui_records_exact_payload_no_real_broker(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    delivery = env["filler_enqueue"]
    from slaif_gateway.api import admin as admin_module

    original = admin_module._enqueue_admin_pending_key_email
    calls: list[tuple[str, str, str]] = []

    def _recording_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        calls.append((str(one_time_secret_id), str(email_delivery_id), str(actor_admin_id)))
        return "fake-215-browser-task-id"

    admin_module._enqueue_admin_pending_key_email = _recording_enqueue
    try:
        # The ACTUAL UI ordinary pending enqueue: the committed intent
        # audit precedes the (stubbed) dispatch; feedback is truthful.
        page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
        try:
            _login(page, env)
            page.goto(f"{env['base_url']}{_row_link(delivery['email_delivery_id'])}")  # type: ignore[union-attr]
            page.fill('form[action$="/enqueue"] textarea[name="reason"]', "215 browser UI enqueue")  # type: ignore[union-attr]
            page.check('form[action$="/enqueue"] input[name="confirm_enqueue"]')  # type: ignore[union-attr]
            page.click('form[action$="/enqueue"] button[type="submit"]')  # type: ignore[union-attr]
            page.wait_for_url(f"**{_row_link(delivery['email_delivery_id'])}?message=*")  # type: ignore[attr-defined]
            assert "Key email delivery queued." in page.inner_text("body")  # type: ignore[union-attr]
            assert len(calls) == 1
            # The payload stays EXACTLY the existing three UUID args
            # (no extra fields, no plaintext, no raw prose).
            uuid.UUID(calls[0][0])
            uuid.UUID(calls[0][1])
            uuid.UUID(calls[0][2])
            assert calls[0][0] == str(delivery["one_time_secret_id"])
            assert calls[0][1] == str(delivery["email_delivery_id"])
        finally:
            page.close()  # type: ignore[union-attr]
    finally:
        admin_module._enqueue_admin_pending_key_email = original

    # Truthful unconfirmed: the recording commits, the (broken) broker
    # stub fails -> requested-but-unconfirmed feedback, never queued/sent
    # success and never raw fault prose.
    def _broken_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        raise RuntimeError("broker down (browser fixture)")

    admin_module._enqueue_admin_pending_key_email = _broken_enqueue
    try:
        page = chromium.new_page(viewport=DESKTOP)  # type: ignore[union-attr]
        try:
            _login(page, env)
            page.goto(f"{env['base_url']}{_row_link(delivery['email_delivery_id'])}")  # type: ignore[union-attr]
            page.check('form[action$="/enqueue"] input[name="confirm_enqueue"]')  # type: ignore[union-attr]
            page.click('form[action$="/enqueue"] button[type="submit"]')  # type: ignore[union-attr]
            page.wait_for_url(f"**{_row_link(delivery['email_delivery_id'])}?message=*")  # type: ignore[attr-defined]
            body = page.inner_text("body")  # type: ignore[union-attr]
            assert "Enqueue requested but unconfirmed" in body
            assert "Key email delivery queued." not in body
            assert "broker down" not in body  # no raw fault prose
        finally:
            page.close()  # type: ignore[union-attr]
    finally:
        admin_module._enqueue_admin_pending_key_email = original


def test_08_no_js_keyboard_pagination_filter_preserving(
    email_ops_env: dict[str, Any], chromium: object
) -> None:
    env = email_ops_env
    browser = chromium  # type: ignore[union-attr]
    context = browser.new_context(viewport=NARROW, java_script_enabled=False)
    try:
        page = context.new_page()
        _login(page, env)

        # Owner A has exactly 11 deliveries (pending+failed+9 fillers):
        # with limit=3 the list pages and the EXACT owner filter is
        # carried through the allowlisted navigation URLs.
        page.goto(
            _qurl(
                str(env["base_url"]),
                "/admin/email-deliveries",
                limit=3,
                owner_email_exact=env["owner_a_email"],
            )
        )  # type: ignore[union-attr]
        assert _ordinal_cells(page) == ["1", "2", "3"]
        assert page.locator('a[rel="next"]').is_visible()  # type: ignore[union-attr]

        # Keyboard-only: focus the Next link and press Enter.
        page.focus('a[rel="next"]')  # type: ignore[union-attr]
        page.keyboard.press("Enter")  # type: ignore[union-attr]
        page.wait_for_url("**offset=3*")  # type: ignore[attr-defined]
        assert "owner_email_exact=" in page.url  # type: ignore[attr-defined]
        assert "limit=3" in page.url  # type: ignore[attr-defined]
        assert _ordinal_cells(page) == ["4", "5", "6"]

        # Previous is keyboard-reachable and preserves the filters too
        # (deterministic: wait for the navigation the Enter initiates).
        page.focus('a[rel="prev"]')  # type: ignore[union-attr]
        with page.expect_navigation():  # type: ignore[union-attr]
            page.keyboard.press("Enter")  # type: ignore[union-attr]
        assert _ordinal_cells(page) == ["1", "2", "3"]
        assert "owner_email_exact=" in page.url  # type: ignore[attr-defined]
        _shoot(page, "215a-narrow-list-paged.png")
    finally:
        context.close()


def test_09_narrow_detail_capture(email_ops_env: dict[str, Any], chromium: object) -> None:
    env = email_ops_env
    browser = chromium  # type: ignore[union-attr]
    context = browser.new_context(viewport=NARROW)
    try:
        page = context.new_page()
        _login(page, env)
        page.goto(f"{env['base_url']}/admin/email-deliveries")  # type: ignore[union-attr]
        assert "Email Deliveries" in page.inner_text("body")  # type: ignore[union-attr]
        _shoot(page, "215a-narrow-list.png")
        page.goto(f"{env['base_url']}{_row_link(env['hist_a']['email_delivery_id'])}")  # type: ignore[union-attr]
        assert page.locator("h1").first.is_visible()  # type: ignore[union-attr]
        _shoot(page, "215a-narrow-detail.png")
    finally:
        context.close()
