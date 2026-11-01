"""211-a GUI operations (request diagnostics): real Chromium on owned PostgreSQL.

Actual uvicorn app, real stylesheet, and real admin pages against the
qualified owned, labeled, loopback-bound, tmpfs-backed PostgreSQL
fixture (``owned_pg_url`` reused directly - this module is the sole
container owner for the run; no unused outer PG).  One explicit ordered
scenario; file order is significant only in that the cleanup case
consumes the seeded expired rows:

- real login -> dashboard -> Operations -> Request diagnostics
  navigation, the status panel, the KEYBOARD picker lookup of the
  retained HTTP-200 stream-failure record (visible failure facts),
  the client-ID collision ambiguity table and the per-candidate
  gateway resolve;
- bounded expired cleanup through the real form with INDEPENDENT
  persisted-DB oracles (deleted/retained counts and the ONE
  actor/reason/count audit row).

Safety: only synthetic fixture values are read; no real provider or
Codex request is involved (records are projected by the SHARED
producer projection ``build_diagnostic_record`` and stored through the
shared repository).  Screenshots (synthetic data only) go under
/tmp/slaif211/.

Run:  python -m pytest tests/browser/test_admin_operations_211.py -m playwright
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    GatewayKey,
    Owner,
    RequestDiagnostic,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.request_diagnostics import (
    RequestDiagnosticsRepository,
)
from slaif_gateway.main import create_app
from slaif_gateway.services.request_diagnostics import build_diagnostic_record
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
)

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif211")

CLEANUP_REASON = "211 browser expired diagnostics cleanup"

# Retention for THIS run: 1 hour, so "expired" rows are 2 hours old and
# retained rows are inside the window (same settings as the 211 PG
# module: write timeout raised to the 1000ms maximum for cold
# first-connection statement preparation).
RETENTION_SECONDS = 3600
EXPIRED_AGE = timedelta(seconds=2 * RETENTION_SECONDS)
N_EXPIRED_SEEDED = 3

# The shared picker JS removes name= from the VISIBLE .rc-input (the
# managed hidden field carries the submitted value), so select the
# visible combobox through its diagnostic-kind container.
LOOKUP_PICKER = 'span.rc[data-kind="diagnostic_request_id"] .rc-input'


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


def _settings(database_url: str, profile_file: str = "") -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ACTIVE_HMAC_KEY_VERSION": "1",
        "TOKEN_HMAC_SECRET_V1": generate_secret_key(),
        "ADMIN_SESSION_SECRET": generate_secret_key(),
        "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
        "ENABLE_EMAIL_DELIVERY": False,
        "OPENAI_UPSTREAM_API_KEY": "sk-provider-secret-placeholder",
        "OPENROUTER_API_KEY": "sk-or-provider-secret-placeholder",
        "REQUEST_DIAGNOSTICS_ENABLED": True,
        "REQUEST_DIAGNOSTICS_RETENTION_SECONDS": RETENTION_SECONDS,
        "REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS": 1000,
    }
    if profile_file:
        values["UPSTREAM_LLM_PROFILES_FILE"] = profile_file
    return Settings(**values)


# ---------------------------------------------------------------------------
# Seed (fixture data only: shared producer projection + direct ORM
# inserts, synthetic material; cleanup consumes the expired rows LAST)
# ---------------------------------------------------------------------------


def _build(settings: Settings, gateway_id: str, *, occurred_at: datetime,
           **extra: Any):
    """One synthetic record through the SHARED producer projection."""
    base: dict[str, Any] = dict(
        gateway_request_id=gateway_id,
        method="GET",
        endpoint_template="/v1/chat/completions",
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        http_status=401,
        stream_outcome="http_rejection",
        source="preauth",
        reason_code="local_rejection",
        error_code="authentication_failed",
    )
    base.update(extra)
    return build_diagnostic_record(base, settings=settings)


async def _seed_data(database_url: str) -> dict[str, Any]:
    settings = _settings(database_url)
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui211b-{suffix}@example.org",
                    display_name="211 Ops Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                repository = RequestDiagnosticsRepository(session)
                records = [
                    _build(settings, f"211b-preauth-{suffix}", occurred_at=now),
                    _build(
                        settings,
                        f"211b-streamfail-{suffix}",
                        occurred_at=now,
                        method="POST",
                        http_status=200,
                        stream_outcome="stream_failure",
                        source="classifier",
                        reason_code="http_error",
                        error_code="responses_stream_provider_failure",
                        positions={"line": 3, "namespace_index": 2},
                        counts={"count": 5, "max_output_tokens": 1_500_000},
                        limits={
                            "max_input_tokens": 900_000,
                            "absolute_max_output_tokens": 2_000_000,
                        },
                        estimated_input_tokens=12,
                        output_allowance_tokens=1_500_000,
                        context_window_tokens=1_050_000,
                    ),
                    _build(
                        settings,
                        f"211b-dupa-{suffix}",
                        occurred_at=now,
                        client_request_id=f"211b-dupclient-{suffix}",
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    ),
                    _build(
                        settings,
                        f"211b-dupb-{suffix}",
                        occurred_at=now,
                        client_request_id=f"211b-dupclient-{suffix}",
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    ),
                    # Retained record whose CLIENT id is the seeded usage
                    # row's request_id: the usage-detail entry link must
                    # resolve it in the client namespace.
                    _build(
                        settings,
                        f"211b-usage-diag-{suffix}",
                        occurred_at=now,
                        client_request_id=f"211b-usage-{suffix}",
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    ),
                ]
                for i in range(N_EXPIRED_SEEDED):
                    records.append(
                        _build(
                            settings,
                            f"211b-exp-{suffix}-{i}",
                            occurred_at=now - EXPIRED_AGE,
                        )
                    )
                for record in records:
                    await repository.insert_row(record)

                # Usage-detail entry-link scenario: one owner, one
                # gateway key, and one ledger row whose request_id is a
                # SAFE diagnostic client ID (client_request_id
                # deliberately None: normal writes do not populate it).
                owner = Owner(
                    id=uuid.uuid4(),
                    name="211 Browser",
                    surname=f"Owner {suffix}",
                    email=f"gui211b-owner-{suffix}@example.org",
                    created_at=now,
                )
                session.add(owner)
                key = GatewayKey(
                    id=uuid.uuid4(),
                    public_key_id=f"211b-{suffix}",
                    key_prefix="sk-slaif-",
                    key_hint=f"211b-{suffix}",
                    token_hash=f"token_hash_211b_{suffix}_{uuid.uuid4().hex}",
                    owner_id=owner.id,
                    status="active",
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                    created_at=now,
                )
                session.add(key)
                ledger = UsageLedger(
                    id=uuid.uuid4(),
                    request_id=f"211b-usage-{suffix}",
                    gateway_key_id=key.id,
                    owner_id=owner.id,
                    endpoint="/v1/chat/completions",
                    provider="211b-synthetic",
                    requested_model="211b-model",
                    resolved_model="211b-model",
                    success=True,
                    accounting_status="finalized",
                    http_status=200,
                    prompt_tokens=3,
                    completion_tokens=5,
                    input_tokens=3,
                    output_tokens=5,
                    total_tokens=8,
                    started_at=now - timedelta(minutes=5),
                    finished_at=now - timedelta(minutes=5) + timedelta(milliseconds=25),
                    latency_ms=25,
                    created_at=now - timedelta(minutes=5),
                )
                session.add(ledger)
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "preauth": f"211b-preauth-{suffix}",
                    "streamfail": f"211b-streamfail-{suffix}",
                    "dupa": f"211b-dupa-{suffix}",
                    "dupb": f"211b-dupb-{suffix}",
                    "dupclient": f"211b-dupclient-{suffix}",
                    "usage_request_id": f"211b-usage-{suffix}",
                    "usage_ledger_id": str(ledger.id),
                    "retained_ids": (
                        f"211b-preauth-{suffix}",
                        f"211b-streamfail-{suffix}",
                        f"211b-dupa-{suffix}",
                        f"211b-dupb-{suffix}",
                        f"211b-usage-diag-{suffix}",
                    ),
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Direct-DB read helpers (persistence oracles, run in a worker thread:
# the Playwright sync API owns the main-thread asyncio loop)
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


def _scoped_counts(data: dict[str, Any]) -> dict[str, int]:
    suffix = data["suffix"]

    async def _get(session):
        retained = (
            await session.execute(
                select(func.count(RequestDiagnostic.id)).where(
                    RequestDiagnostic.gateway_request_id.in_(data["retained_ids"])
                )
            )
        ).scalar_one()
        expired = (
            await session.execute(
                select(func.count(RequestDiagnostic.id)).where(
                    RequestDiagnostic.gateway_request_id.like(
                        f"211b-exp-{suffix}-%"
                    )
                )
            )
        ).scalar_one()
        return {"retained": int(retained), "expired": int(expired)}

    return _db(data["database_url"], _get)


def _cleanup_audits(data: dict[str, Any]) -> list[dict[str, Any]]:
    async def _get(session):
        rows = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.action == "diagnostics_expired_cleanup",
                        AuditLog.admin_user_id == uuid.UUID(data["admin_id"]),
                    )
                    .order_by(AuditLog.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [{"new": r.new_values, "note": r.note} for r in rows]

    return _db(data["database_url"], _get)


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ops_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / "browser-211a-lifecycle.json").write_text(
        json.dumps(
            {
                "container": _PG_STATE.get("pg_container"),
                "owner": _PG_STATE.get("pg_owner"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    profile_file = SCREENSHOT_DIR / f"profiles-211b-{uuid.uuid4().hex[:8]}.json"
    profile_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "browser-profile",
                        "revision": 7,
                        "instruction_placement": "preserve",
                        "tool_encoding": "preserve",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(profile_file, 0o644)

    data = asyncio.run(_seed_data(owned_pg_url))
    data["profile_file"] = str(profile_file)
    data["base_url"] = f"http://127.0.0.1:{_free_port()}"
    data["database_url"] = owned_pg_url
    port = int(data["base_url"].rsplit(":", 1)[1])
    app = create_app(_settings(owned_pg_url, profile_file=str(profile_file)))
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(ops_env) -> Iterator[object]:
    """Depends on ``ops_env`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PostgreSQL readiness,
    seeding, and the uvicorn app must complete BEFORE it starts (and the
    browser closes before DB teardown)."""
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


def _pick_lookup_id(page: object, value: str) -> None:
    """Keyboard picker entry: type the ID, ArrowDown/Enter select the
    rendered retained option (the managed hidden field carries it)."""
    page.fill(LOOKUP_PICKER, value)  # type: ignore[attr-defined]
    page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]


def _multipart_field(raw: str, name: str) -> str:
    """One ASCII field value from the picker's FormData (multipart) body."""
    match = re.search(
        r'Content-Disposition: form-data; name="%s"\r?\n\r?\n([^\r\n]*)\r?\n--'
        % re.escape(name),
        raw,
    )
    assert match is not None, f"multipart field {name!r} not found"
    return match.group(1)


# ---------------------------------------------------------------------------
# Cases (file order is significant: cleanup consumes the expired rows)
# ---------------------------------------------------------------------------


def test_login_operations_lookup_disambiguation_cleanup(
    ops_env: dict[str, Any], chromium: object
) -> None:
    """Real login -> dashboard -> Operations -> Diagnostics -> keyboard
    lookup of the HTTP-200 stream failure, client-ID ambiguity +
    gateway resolve, then bounded cleanup with independent DB oracles."""
    data = ops_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        assert page.url.endswith("/admin")  # type: ignore[attr-defined]

        # dashboard -> Operations (Usage and operations group)
        page.click(
            '.dash-group:has-text("Usage and operations") a[href="/admin/operations"]'  # type: ignore[attr-defined]
        )
        page.wait_for_url("**/operations/")  # type: ignore[attr-defined]
        assert (
            page.locator("#operations-heading").inner_text()  # type: ignore[attr-defined]
            == "Operations"
        )
        page.click('a[href="/admin/operations/diagnostics"]')  # type: ignore[attr-defined]
        page.wait_for_url("**/operations/diagnostics")  # type: ignore[attr-defined]

        # status panel: enabled recording + this run's retention
        html = page.content()  # type: ignore[attr-defined]
        assert "Enabled" in html
        assert "3,600 seconds" in html
        assert "Available" in html

        # (1) KEYBOARD lookup of the retained HTTP-200 stream failure:
        # visible failure facts, formatted token facts, no attribution
        # (preauth/source classifier, no gateway key stored)
        _pick_lookup_id(page, data["streamfail"])
        page.click('button:has-text("Look up")')  # type: ignore[attr-defined]
        page.wait_for_selector("text=Stream outcome")  # type: ignore[attr-defined]
        visible = page.locator(  # type: ignore[attr-defined]
            'section[aria-labelledby="diagnostics-result-heading"]'
        ).inner_text()
        assert (
            "stream_failure — the response started with HTTP 200 but the "
            "stream FAILED: this is a failure, not a success" in visible
        )
        assert "http_error / responses_stream_provider_failure" in visible
        assert "max_output_tokens: 1.5M tokens (1,500,000)" in visible
        assert "max_input_tokens: 0.9M tokens (900,000)" in visible
        assert "absolute_max_output_tokens: 2M tokens (2,000,000)" in visible
        assert "line: 3 · namespace_index: 2" in visible
        # token-fact row: M tokens as visible text, exact raw detail in title
        assert "output allowance 1.5M" in visible
        html = page.content()  # type: ignore[attr-defined]
        assert 'title="1,500,000 tokens"' in html
        # no authenticated-key attribution on this retained failure
        assert "<dt>Gateway key / route</dt><dd>— / —</dd>" in html
        # the explicit historical-module-identity row
        assert "Client module identity" in visible
        assert "Not recorded" in visible

        # (2) client-ID collision: two retained rows, one per gateway
        # record; resolve ONE candidate in the gateway namespace
        _pick_lookup_id(page, data["dupclient"])
        page.click('button:has-text("Look up")')  # type: ignore[attr-defined]
        page.wait_for_selector("text=retained row(s) match this ID")  # type: ignore[attr-defined]
        visible = page.locator(  # type: ignore[attr-defined]
            'section[aria-labelledby="diagnostics-result-heading"]'
        ).inner_text()
        assert "2 retained row(s) match this ID" in visible
        html = page.content()  # type: ignore[attr-defined]
        assert html.count('value="%s"' % data["dupa"]) >= 1
        assert html.count('value="%s"' % data["dupb"]) >= 1
        # resolve the INTENDED candidate row (the one carrying dupa's
        # gateway ID), not whichever button happens to be first
        page.click(
            'tr:has(code:text("%s")) button:has-text("Resolve in gateway")'
            % data["dupa"]
        )  # type: ignore[attr-defined]
        page.wait_for_selector("text=Stream outcome")  # type: ignore[attr-defined]
        html = page.content()  # type: ignore[attr-defined]
        visible = page.locator(  # type: ignore[attr-defined]
            'section[aria-labelledby="diagnostics-result-heading"]'
        ).inner_text()
        assert "local_rejection / rate_limited" in visible
        assert "<code>%s</code>" % data["dupa"] in html

        # (3) bounded expired cleanup through the real form (inside the
        # labelled disclosure), with INDEPENDENT persisted-DB oracles
        # (counts + the one audit row)
        assert _scoped_counts(data)["expired"] == N_EXPIRED_SEEDED
        # the disclosure starts closed: open it with the keyboard
        # (fill auto-waits for the form to be actionable/visible)
        page.focus("#diagnostics-cleanup-summary")  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        page.fill("#cleanup-reason", CLEANUP_REASON)  # type: ignore[attr-defined]
        page.check("#cleanup-confirm")  # type: ignore[attr-defined]
        page.click('button:has-text("Run cleanup")')  # type: ignore[attr-defined]
        page.wait_for_selector("text=Cleanup complete")  # type: ignore[attr-defined]
        assert (
            "Cleanup complete: deleted 3 expired record(s) (bounded batch: "
            "1,000)." in page.content()  # type: ignore[attr-defined]
        )
        assert "The batch limit was reached" not in page.content()  # type: ignore[attr-defined]

        counts = _scoped_counts(data)
        assert counts["expired"] == 0
        assert counts["retained"] == 5  # retained rows preserved
        audits = _cleanup_audits(data)
        assert len(audits) == 1
        assert audits[0]["new"]["deleted_count"] == 3
        assert audits[0]["note"] == CLEANUP_REASON
    finally:
        page.close()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Picker privacy: a pasted credential never reaches any URL, the error
# response, or the rendered page (the POST body refusal is the only
# path it may take)
# ---------------------------------------------------------------------------

CANARY = "sk-slaif-211browsercanary00"
DIAGNOSTIC_RC = 'span.rc[data-kind="diagnostic_request_id"]'


def test_picker_pasted_credential_never_reaches_url_or_response(
    ops_env: dict[str, Any], chromium: object
) -> None:
    data = ops_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}/admin/operations/diagnostics")  # type: ignore[attr-defined]

        seen_urls: list[str] = []
        page.on("request", lambda r: seen_urls.append(r.url))  # type: ignore[attr-defined]
        # Capture the choices responses at the NETWORK layer: the request
        # still EXECUTES the real HTTP handler (route.fetch()), and
        # route.fulfill() delivers the UNMODIFIED backend response to the
        # page; only the body is additionally buffered by Playwright,
        # because a page-bound Response.text() stalled on an evicted body
        # in a prior run.
        captured: list[tuple[str, int, str]] = []

        def _capture_choices(route: object) -> None:
            # a handler fault must never poison the browser connection
            # (e.g. a route still settling when the page closes)
            try:
                response = route.fetch()
                captured.append(
                    (route.request.method, response.status, response.text())
                )
                route.fulfill(response=response)
            except Exception:  # noqa: BLE001 - test-capture best effort
                try:
                    route.abort()
                except Exception:  # noqa: BLE001
                    pass

        page.route(  # type: ignore[attr-defined]
            "**/admin/operations/diagnostics/choices", _capture_choices
        )

        # open the menu (opening may fetch the initial empty-q list, a
        # 200) and paste the synthetic credential into the search field
        page.click(f'{DIAGNOSTIC_RC} .rc-input')  # type: ignore[attr-defined]
        search = f'{DIAGNOSTIC_RC} .rc-search'
        page.fill(search, CANARY)  # type: ignore[attr-defined]

        # wait for the EXACT failure announcement (the transient
        # "Searching…" state must not satisfy the wait)
        page.get_by_text(  # type: ignore[attr-defined]
            "Search unavailable — retry or type a known value.", exact=True
        ).wait_for(timeout=15000)
        refusals = [
            (method, body) for method, status, body in captured if status == 400
        ]
        assert len(refusals) == 1
        refusal_method, refusal_body = refusals[0]
        assert refusal_method == "POST"
        # the fixed safe refusal carries no input
        assert json.loads(refusal_body) == {"detail": "Search value withheld."}
        assert CANARY not in refusal_body
        # the picker POSTs the body; the value never reaches ANY URL
        assert any("/admin/operations/diagnostics/choices" in u for u in seen_urls)
        for url in seen_urls:
            assert CANARY not in url
            assert "211browsercanary00" not in url

        # clear the search and wait for a 200 re-fetch that comes AFTER
        # the 400 (an earlier initial-list 200 cannot satisfy recovery)
        refusal_index = max(
            i for i, (_m, s, _b) in enumerate(captured) if s == 400
        )
        page.fill(search, "")  # type: ignore[attr-defined]
        deadline = 100
        while not any(
            i > refusal_index and status == 200
            for i, (_m, status, _b) in enumerate(captured)
        ):
            if deadline <= 0:
                raise AssertionError("no post-refusal 200 re-fetch")
            page.wait_for_timeout(100)  # type: ignore[attr-defined]
            deadline -= 1
        assert CANARY not in page.content()  # type: ignore[attr-defined]
        page.unroute("**/admin/operations/diagnostics/choices")  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Existing record-choice kinds keep their normal GET lookup transport
# ---------------------------------------------------------------------------


def test_existing_kinds_still_use_get_lookup(
    ops_env: dict[str, Any], chromium: object
) -> None:
    data = ops_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}/admin/usage")  # type: ignore[attr-defined]

        seen: list[tuple[str, str]] = []
        page.on(  # type: ignore[attr-defined]
            "request",
            lambda r: seen.append((r.method, r.url)),
        )
        # the usage-list provider picker is an EXISTING kind: typing must
        # issue the shared GET record-choices lookup, never the 211 POST
        provider_rc = 'span.rc[data-kind="provider"]'
        page.click(f"{provider_rc} .rc-input")  # type: ignore[attr-defined]
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url
        ) as info:
            page.fill(f"{provider_rc} .rc-input", "211b")  # type: ignore[attr-defined]
        url = info.value.url
        assert info.value.request.method == "GET"
        assert "/admin/record-choices?" in url
        assert "kind=provider" in url
        for method, seen_url in seen:
            assert "/admin/operations/diagnostics/choices" not in seen_url
    finally:
        page.close()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Usage-detail entry link: guarded CLIENT-namespace prefill resolves the
# retained record whose client ID is the usage row's request_id
# ---------------------------------------------------------------------------


def test_usage_detail_entry_link_client_namespace(
    ops_env: dict[str, Any], chromium: object
) -> None:
    data = ops_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}/admin/usage/{data['usage_ledger_id']}")  # type: ignore[attr-defined]
        expected = f"/admin/operations/diagnostics?lookup={data['usage_request_id']}&namespace=client"
        link = page.locator(f'a[href="{expected}"]')  # type: ignore[attr-defined]
        assert link.count() == 1
        assert "Look up in request diagnostics (client namespace)" in link.inner_text()
        link.click()
        page.wait_for_url(
            lambda url: "/admin/operations/diagnostics?lookup=" in url
        )  # type: ignore[attr-defined]
        # the picker is prefilled with the SAFE request_id: the accepted
        # 193 picker design blanks the visible single input and preserves
        # the chosen ID as chip + managed hidden field (so assert those,
        # not the visible input value)
        assert (
            page.locator(f"{DIAGNOSTIC_RC} .rc-value").input_value()  # type: ignore[attr-defined]
            == data["usage_request_id"]
        )
        assert data["usage_request_id"] in page.locator(  # type: ignore[attr-defined]
            f"{DIAGNOSTIC_RC} .rc-selected"
        ).inner_text()
        assert (
            page.locator("#lookup-namespace-select").input_value()  # type: ignore[attr-defined]
            == "client"
        )

        # namespace change is read LIVE by the private POST lookup:
        # switching to gateway makes the next picker fetch carry it;
        # wait for the COMPLETED 200 response (the page's own CSRF token
        # is still accepted - no rotation between same-page renders)
        csrf_field = (
            'form[action="/admin/operations/diagnostics/lookup"] '
            'input[name="csrf_token"]'
        )
        csrf = page.locator(csrf_field).input_value()  # type: ignore[attr-defined]
        choices_pred = lambda r: "/admin/operations/diagnostics/choices" in r.url  # noqa: E731
        ok_pred = lambda r: choices_pred(r) and r.status == 200  # noqa: E731

        page.select_option("#lookup-namespace-select", "gateway")  # type: ignore[attr-defined]
        with page.expect_request(choices_pred) as req_info, page.expect_response(  # type: ignore[attr-defined]
            ok_pred
        ) as resp_info:
            page.click(f"{DIAGNOSTIC_RC} .rc-input")  # type: ignore[attr-defined]
        gateway_request = req_info.value
        assert gateway_request.method == "POST"
        body = gateway_request.post_data or ""
        assert _multipart_field(body, "namespace") == "gateway"
        assert _multipart_field(body, "kind") == "diagnostic_request_id"
        assert _multipart_field(body, "csrf_token") == csrf
        assert resp_info.value.status == 200

        # close the menu, switch back, and complete the CLIENT-namespace
        # refresh too (same live-namespace + same-CSRF proof)
        page.keyboard.press("Escape")  # type: ignore[attr-defined]
        page.select_option("#lookup-namespace-select", "client")  # type: ignore[attr-defined]
        with page.expect_request(choices_pred) as req2, page.expect_response(  # type: ignore[attr-defined]
            ok_pred
        ) as resp2:
            page.click(f"{DIAGNOSTIC_RC} .rc-input")  # type: ignore[attr-defined]
        client_body = req2.value.post_data or ""
        assert _multipart_field(client_body, "namespace") == "client"
        assert _multipart_field(client_body, "csrf_token") == csrf
        assert resp2.value.status == 200

        # the same-page submit is a POST to the same-page action and the
        # lookup token from the same form is still valid
        with page.expect_request(  # type: ignore[attr-defined]
            lambda r: r.url.endswith("/admin/operations/diagnostics/lookup")
        ) as lookup_info:
            page.click('button:has-text("Look up")')  # type: ignore[attr-defined]
        assert lookup_info.value.method == "POST"
        page.wait_for_selector("text=Stream outcome")  # type: ignore[attr-defined]
        html = page.content()  # type: ignore[attr-defined]
        visible = page.locator(  # type: ignore[attr-defined]
            'section[aria-labelledby="diagnostics-result-heading"]'
        ).inner_text()
        assert "local_rejection / rate_limited" in visible
        assert "<code>%s</code>" % data["usage_request_id"] in html
        assert "<code>%s</code>" % f"211b-usage-diag-{data['suffix']}" in html
    finally:
        page.close()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# No-JS fallback: the server-rendered form works without JavaScript and
# same-page validation recovery stays CSRF-protected (no redirect)
# ---------------------------------------------------------------------------


def test_nojs_lookup_and_validation_recovery(
    ops_env: dict[str, Any], chromium: object
) -> None:
    data = ops_env
    context = chromium.new_context(java_script_enabled=False)  # type: ignore[union-attr]
    page = context.new_page()
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}/admin/operations/diagnostics")  # type: ignore[attr-defined]

        # empty submit: same-page error flash at the form ACTION url
        # (a same-page POST render, not a redirect or a new state URL)
        page.click('button:has-text("Look up")')  # type: ignore[attr-defined]
        assert page.url.endswith("/admin/operations/diagnostics/lookup")  # type: ignore[attr-defined]
        visible = page.locator(".admin-flash-error").inner_text()  # type: ignore[attr-defined]
        assert visible == "Enter a diagnostic request ID."

        # the no-JS form field (name retained without JS) + submit
        page.fill('input[name="lookup_id"]', data["preauth"])  # type: ignore[attr-defined]
        page.click('button:has-text("Look up")')  # type: ignore[attr-defined]
        page.wait_for_selector("text=Stream outcome")  # type: ignore[attr-defined]
        visible = page.locator(  # type: ignore[attr-defined]
            'section[aria-labelledby="diagnostics-result-heading"]'
        ).inner_text()
        assert "local_rejection / authentication_failed" in visible
        assert "preauth" in visible
    finally:
        context.close()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Process configuration inspection + existing workflows still render
# ---------------------------------------------------------------------------


def test_process_configuration_and_existing_workflows(
    ops_env: dict[str, Any], chromium: object
) -> None:
    data = ops_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)

        # operations index: both entries
        page.goto(f"{data['base_url']}/admin/operations/")  # type: ignore[attr-defined]
        assert (
            page.locator("#operations-heading").inner_text()  # type: ignore[attr-defined]
            == "Operations"
        )
        assert page.locator('a[href="/admin/operations/diagnostics"]').count() == 1
        assert page.locator('a[href="/admin/operations/process-configuration"]').count() == 1

        # process configuration: finite allowlist + startup profile snapshot
        page.goto(f"{data['base_url']}/admin/operations/process-configuration")  # type: ignore[attr-defined]
        assert (
            "API process settings (45 finite allowlist)" in page.content()  # type: ignore[attr-defined]
        )
        assert (
            page.locator(  # type: ignore[attr-defined]
                'section[aria-labelledby="proc-config-settings-heading"] tbody tr'
            ).count()
            == 45
        )
        html = page.content()  # type: ignore[attr-defined]
        # the startup-validated profile snapshot with the exact selector
        # JSON object (version/profile/revision/sha256)
        assert "<td><code>browser-profile</code></td>" in html
        assert '"profile": "browser-profile"' in html
        assert '"version": 1' in html and '"revision": 7' in html
        assert "Limitations" in html
        # values are process-scope, not per-key policy or reverse-proxy limits
        assert "Values are not per-key policy" in html

        # existing workflows still render with the seeded data
        page.goto(f"{data['base_url']}/admin/usage")  # type: ignore[attr-defined]
        assert data["usage_request_id"] in page.content()  # type: ignore[attr-defined]
        page.goto(f"{data['base_url']}/admin/keys")  # type: ignore[attr-defined]
        assert f"211b-{data['suffix']}" in page.content()  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Actual rendered styles: narrow (no horizontal overflow) + desktop
# captures for root visual review (synthetic data only)
# ---------------------------------------------------------------------------


def test_narrow_and_desktop_captures(
    ops_env: dict[str, Any], chromium: object
) -> None:
    data = ops_env
    page = chromium.new_page(viewport={"width": 390, "height": 844})  # type: ignore[union-attr]
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}/admin/operations/diagnostics")  # type: ignore[attr-defined]
        # no horizontal overflow at the narrow width (scrollbar-aware)
        overflow = page.evaluate(  # type: ignore[attr-defined]
            "document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        assert int(overflow) <= 0
        page.screenshot(path=str(SCREENSHOT_DIR / "211-browser-narrow.png"), full_page=True)  # type: ignore[attr-defined]

        # desktop capture of the same page (top + full)
        page.set_viewport_size({"width": 1280, "height": 900})  # type: ignore[attr-defined]
        page.wait_for_timeout(150)  # type: ignore[attr-defined]
        page.screenshot(path=str(SCREENSHOT_DIR / "211-browser-desktop.png"), full_page=True)  # type: ignore[attr-defined]
        # the status panel facts remain visible at both widths
        assert "3,600 seconds" in page.content()  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]
