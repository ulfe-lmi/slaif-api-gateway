"""Actual-browser key create/detail/update evidence for lazy throttling (V5).

Reuses this objective's already-qualified owned PostgreSQL fixture from the
integration module (owned/label/loopback/tmpfs container, identity verified
before use, exact-ID cleanup) and the existing admin browser pattern
(Playwright Chromium + owned uvicorn app). The app is configured with
explicit synthetic HMAC, one-time-encryption, and admin-session secrets; no
ambient database URL or protected host environment value is trusted.

Coverage:

- positive: non-default wait saved through the real create form, detail
  summary plus prefilled form, authenticated detail update, and return to
  reject; a logged-in web save must be audited under the ACTUAL admin actor;
- no-JS usability (server-rendered wait inputs stay usable) and escaped
  error redisplay;
- CSRF / unauthorized / missing-reason / invalid-bounds negatives that must
  leave the stored policy unchanged.

Safety: only opaque IDs and stored policy JSON are read and asserted. The
one-time plaintext key is never read, logged, or screenshotted; session and
CSRF values are used only transiently to submit forms and are never logged
or screenshotted.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# Reuse the already-qualified owned, labeled, loopback-bound, tmpfs-backed
# PostgreSQL fixture from this objective's integration module (never an
# ambient TEST_DATABASE_URL fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

# Re-export the integration module's qualified fixture under the expected
# fixture name for this module's tests.
owned_pg_url = _owned_pg_url_fixture

ADMIN_PASSWORD = "correct horse battery staple"
WAIT_POLICY = {"mode": "wait", "max_wait_seconds": 45, "max_waiting_requests": 4}
MALICIOUS_REASON = 'x"><script>alert(1)</script>'

# The header carries a /admin/logout Sign-out form BEFORE the page's own
# forms, so every submit/field below is scoped to its exact form action.
CREATE_FORM = 'form[action="/admin/keys/create"]'
LAZY_FORM = 'form[action$="/lazy-throttling"]'
LOGIN_FORM = 'form[action="/admin/login"]'


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
    """Run a DB coroutine on an owned worker loop.

    Playwright's sync API occupies the main thread, so asyncio.run there
    fails with "cannot be called from a running event loop". A fresh thread
    gets a clean loop per call; the result (or the original exception) is
    re-raised verbatim on the calling thread.
    """
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


def _settings(database_url: str) -> Settings:
    # Explicit synthetic key material for this test app only: real key
    # creation requires active HMAC secret + one-time encryption key.
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        GATEWAY_KEY_PREFIX="sk-slaif-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1=generate_secret_key(),
        ADMIN_SESSION_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ENABLE_EMAIL_DELIVERY=False,
    )


async def _create_lazy_browser_data(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    try:
        async with session_factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"lazy-admin-{suffix}@example.org",
                    display_name="Lazy Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"Lazy Browser Institution {suffix}",
                    country="SI",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"lazy-browser-{suffix}",
                    description="safe lazy browser cohort",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Lazy",
                    surname="Browser",
                    email=f"lazy-owner-{suffix}@example.org",
                    institution_id=institution.id,
                )
                key = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"lazy-{suffix[:16]}",
                    token_hash=f"token_hash_lazy_browser_{suffix}",
                    owner_id=owner.id,
                    cohort_id=cohort.id,
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                    key_hint="sk-slaif-lazy-browser-hint",
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=1000,
                    request_limit_total=100,
                    allow_all_models=True,
                    allow_all_endpoints=True,
                    metadata_json={"lazy_throttling_policy": dict(WAIT_POLICY)},
                    created_by_admin_user_id=admin.id,
                )
                return {
                    "admin_id": admin.id,
                    "admin_email": admin.email,
                    "owner_id": owner.id,
                    "cohort_id": cohort.id,
                    "owner_email": owner.email,
                    "cohort_name": cohort.name,
                    "key_id": key.id,
                    "public_key_id": key.public_key_id,
                }
    finally:
        await engine.dispose()


async def _stored_lazy_policy(
    database_url: str, gateway_key_id: uuid.UUID
) -> dict[str, object] | None:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(GatewayKey).where(GatewayKey.id == gateway_key_id)
            )
            row = result.scalar_one()
            return (row.metadata_json or {}).get("lazy_throttling_policy")
    finally:
        await engine.dispose()


async def _stored_public_key_id(database_url: str, gateway_key_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(GatewayKey.public_key_id).where(GatewayKey.id == gateway_key_id)
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _lazy_update_audit_rows(database_url: str, gateway_key_id: uuid.UUID) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_id == gateway_key_id,
                    AuditLog.action == "update_key_lazy_throttling",
                )
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            )
            return list(result.scalars())
    finally:
        await engine.dispose()


def _login(page: object, data: dict[str, object]) -> None:
    response = page.goto("/admin/login")  # type: ignore[attr-defined]
    assert response is not None
    assert response.status == 200
    page.fill(  # type: ignore[attr-defined]
        f'{LOGIN_FORM} input[name="email"]', str(data["admin_email"])
    )
    page.fill(  # type: ignore[attr-defined]
        f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD
    )
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _created_key_ids(page: object) -> tuple[str, uuid.UUID]:
    """Read ONLY the generated public key ID and DB key UUID from the
    create-result labels. The one-time plaintext key is never read."""
    public_key_id = (
        page.locator('dt:has-text("Public key ID") + dd').text_content()  # type: ignore[attr-defined]
        or ""
    ).strip()
    gateway_key_id_raw = (
        page.locator('dt:has-text("Gateway key ID") + dd').text_content()  # type: ignore[attr-defined]
        or ""
    ).strip()
    assert public_key_id, "create result must show the generated public key ID"
    return public_key_id, uuid.UUID(gateway_key_id_raw)


def _fill_minimal_key_form(
    page: object,
    data: dict[str, object],
    *,
    max_wait_seconds: str,
    max_waiting_requests: str,
    reason: str,
    js_enabled: bool = True,
) -> None:
    # 192-a: owner/cohort are record-choice controls (no <select>).
    # With JS the menu selection writes the UUID to the managed hidden
    # field; without JS the visible field is a plain text input that
    # submits the raw UUID (the no-JS value contract).
    if js_enabled:
        owner_rc = page.locator(  # type: ignore[attr-defined]
            f'{CREATE_FORM} .rc:has(input[name="owner_id"])'
        )
        owner_rc.locator(".rc-open").click()
        owner_rc.locator(f'.rc-option:has-text("{data["owner_email"]}")').click()
        cohort_rc = page.locator(  # type: ignore[attr-defined]
            f'{CREATE_FORM} .rc:has(input[name="cohort_id"])'
        )
        cohort_rc.locator(".rc-open").click()
        cohort_rc.locator(f'.rc-option:has-text("{data["cohort_name"]}")').click()
    else:
        page.fill(  # type: ignore[attr-defined]
            f'{CREATE_FORM} input[name="owner_id"]', str(data["owner_id"])
        )
        page.fill(  # type: ignore[attr-defined]
            f'{CREATE_FORM} input[name="cohort_id"]', str(data["cohort_id"])
        )
    assert page.locator(  # type: ignore[attr-defined]
        f'{CREATE_FORM} input[name="owner_id"]'
    ).input_value() == str(data["owner_id"])
    assert page.locator(  # type: ignore[attr-defined]
        f'{CREATE_FORM} input[name="cohort_id"]'
    ).input_value() == str(data["cohort_id"])
    page.fill(f'{CREATE_FORM} input[name="valid_days"]', "30")  # type: ignore[attr-defined]
    page.fill(f'{CREATE_FORM} input[name="cost_limit_eur"]', "10")  # type: ignore[attr-defined]
    page.fill(f'{CREATE_FORM} input[name="token_limit_total"]', "1000")  # type: ignore[attr-defined]
    page.fill(f'{CREATE_FORM} input[name="request_limit_total"]', "100")  # type: ignore[attr-defined]
    page.check(f'{CREATE_FORM} input[name="allow_all_models"]')  # type: ignore[attr-defined]
    page.check(f'{CREATE_FORM} input[name="allow_all_endpoints"]')  # type: ignore[attr-defined]
    page.fill(  # type: ignore[attr-defined]
        f'{CREATE_FORM} input[name="lazy_throttling_max_wait_seconds"]', max_wait_seconds
    )
    page.fill(  # type: ignore[attr-defined]
        f'{CREATE_FORM} input[name="lazy_throttling_max_waiting_requests"]',
        max_waiting_requests,
    )
    page.fill(f'{CREATE_FORM} input[name="reason"]', reason)  # type: ignore[attr-defined]


def _lazy_csrf_token(page: object) -> str:
    token = page.locator(  # type: ignore[attr-defined]
        f'{LAZY_FORM} input[name="csrf_token"]'
    ).input_value()
    assert token, "lazy throttling form must expose a CSRF token"
    return token


def _post_lazy_update(
    context: object,
    key_id: uuid.UUID,
    *,
    csrf_token: str,
    mode: str,
    max_wait_seconds: str,
    max_waiting_requests: str,
    reason: str,
) -> object:
    # max_redirects=0 so redirects (login bounce / success 303) are visible
    # as status codes instead of being followed into another page.
    return context.request.post(  # type: ignore[attr-defined]
        f"/admin/keys/{key_id}/lazy-throttling",
        form={
            "csrf_token": csrf_token,
            "lazy_throttling_mode": mode,
            "lazy_throttling_max_wait_seconds": max_wait_seconds,
            "lazy_throttling_max_waiting_requests": max_waiting_requests,
            "reason": reason,
        },
        max_redirects=0,
    )


@pytest.mark.playwright
def test_admin_lazy_throttling_wait_create_update_and_reject(owned_pg_url: str) -> None:
    """Positive flow: non-default wait saved via create, updated, then rejected."""
    data = asyncio.run(_create_lazy_browser_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url)
        page = context.new_page()
        try:
            _login(page, data)

            # --- create with wait + NON-DEFAULT bounds (JS active) ---
            page.goto("/admin/keys/create")
            create_html = page.content()
            assert "Operator ceilings: 120s maximum wait, 16 waiting per key" in create_html
            assert "Redis rate limiting is currently disabled" in create_html
            assert page.locator(
                f'{CREATE_FORM} input[name="lazy_throttling_mode"][value="reject"]'
            ).is_checked()
            # JS hides the wait bounds until wait is selected.
            group = page.locator(f"{CREATE_FORM} [data-lazy-throttling-field-group]")
            group.wait_for(state="hidden", timeout=10000)
            page.check(f'{CREATE_FORM} input[name="lazy_throttling_mode"][value="wait"]')
            group.wait_for(state="visible", timeout=10000)
            _fill_minimal_key_form(
                page,
                data,
                max_wait_seconds="45",
                max_waiting_requests="4",
                reason="browser lazy create: wait 45s / 4 waiting",
            )
            page.click(f'{CREATE_FORM} button[type="submit"]')
            page.wait_for_selector("#created-key-heading", timeout=20000)
            created_public_key_id, created_key_id = _created_key_ids(page)
            assert (
                _run_in_thread(_stored_public_key_id(owned_pg_url, created_key_id))
                == created_public_key_id
            )
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, created_key_id)) == {
                "mode": "wait",
                "max_wait_seconds": 45,
                "max_waiting_requests": 4,
            }

            # --- detail: summary + prefilled form ---
            page.goto(f"/admin/keys/{created_key_id}")
            assert "Mode: wait; max wait: 45s; max waiting per key: 4" in page.content()
            assert page.locator(
                f'{LAZY_FORM} input[name="lazy_throttling_mode"][value="wait"]'
            ).is_checked()
            assert (
                page.locator(
                    f'{LAZY_FORM} input[name="lazy_throttling_max_wait_seconds"]'
                ).input_value()
                == "45"
            )
            assert (
                page.locator(
                    f'{LAZY_FORM} input[name="lazy_throttling_max_waiting_requests"]'
                ).input_value()
                == "4"
            )

            # --- detail update to another non-default wait (60s / 8) ---
            page.fill(f'{LAZY_FORM} input[name="lazy_throttling_max_wait_seconds"]', "60")
            page.fill(f'{LAZY_FORM} input[name="lazy_throttling_max_waiting_requests"]', "8")
            page.fill(
                f'{LAZY_FORM} input[name="reason"]',
                "browser lazy update: wait 60s / 8 waiting",
            )
            page.click(f'{LAZY_FORM} button[type="submit"]')
            # The success 303 lands on the detail URL with ?message=...
            page.wait_for_url(f"**/admin/keys/{created_key_id}?*")
            assert "Gateway key lazy throttling policy updated." in page.content()
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, created_key_id)) == {
                "mode": "wait",
                "max_wait_seconds": 60,
                "max_waiting_requests": 8,
            }
            # A logged-in web save is audited under the ACTUAL admin actor.
            audit_rows = _run_in_thread(_lazy_update_audit_rows(owned_pg_url, created_key_id))
            assert len(audit_rows) == 1
            assert audit_rows[0].admin_user_id == data["admin_id"]

            # --- return to reject: removes the stored wait policy ---
            page.check(f'{LAZY_FORM} input[name="lazy_throttling_mode"][value="reject"]')
            page.fill(
                f'{LAZY_FORM} input[name="reason"]',
                "browser lazy update: back to reject",
            )
            page.click(f'{LAZY_FORM} button[type="submit"]')
            page.wait_for_url(f"**/admin/keys/{created_key_id}?*")
            assert "Gateway key lazy throttling policy updated." in page.content()
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, created_key_id)) is None
            assert "Mode: reject (immediate 429); no waiting configured" in page.content()
            audit_rows = _run_in_thread(_lazy_update_audit_rows(owned_pg_url, created_key_id))
            assert len(audit_rows) == 2
            assert all(row.admin_user_id == data["admin_id"] for row in audit_rows)

            # The pre-seeded key keeps its original wait policy throughout.
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, data["key_id"])) == WAIT_POLICY
        finally:
            context.close()


@pytest.mark.playwright
def test_admin_lazy_throttling_no_js_create_and_escaped_redisplay(
    owned_pg_url: str,
) -> None:
    """No-JS: wait inputs stay usable; invalid bounds redisplay escaped."""
    data = asyncio.run(_create_lazy_browser_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url, java_script_enabled=False)
        page = context.new_page()
        try:
            _login(page, data)
            page.goto("/admin/keys/create")
            # Without JS the server-rendered wait bounds are usable even
            # while reject is selected (JS may hide/disable only after init).
            group = page.locator(f"{CREATE_FORM} [data-lazy-throttling-field-group]")
            assert group.is_visible()
            wait_input = page.locator(
                f'{CREATE_FORM} input[name="lazy_throttling_max_wait_seconds"]'
            )
            assert wait_input.is_enabled()

            # Select wait, enter NON-DEFAULT bounds, and create without JS.
            page.check(f'{CREATE_FORM} input[name="lazy_throttling_mode"][value="wait"]')
            _fill_minimal_key_form(
                page,
                data,
                max_wait_seconds="40",
                max_waiting_requests="3",
                reason="browser lazy no-js create: wait 40s / 3 waiting",
                js_enabled=False,
            )
            page.click(f'{CREATE_FORM} button[type="submit"]')
            page.wait_for_selector("#created-key-heading", timeout=20000)
            created_public_key_id, created_key_id = _created_key_ids(page)
            assert (
                _run_in_thread(_stored_public_key_id(owned_pg_url, created_key_id))
                == created_public_key_id
            )
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, created_key_id)) == {
                "mode": "wait",
                "max_wait_seconds": 40,
                "max_waiting_requests": 3,
            }
            page.goto(f"/admin/keys/{created_key_id}")
            detail_html = page.content()
            assert "Mode: wait; max wait: 40s; max waiting per key: 3" in detail_html
            assert "Redis rate limiting is currently disabled" in detail_html

            # Invalid bounds (above the operator ceiling) with a malicious
            # reason: the error redisplay must be escaped, policy unchanged.
            csrf = _lazy_csrf_token(page)
            response = _post_lazy_update(
                context,
                created_key_id,
                csrf_token=csrf,
                mode="wait",
                max_wait_seconds="999999",
                max_waiting_requests="3",
                reason=MALICIOUS_REASON,
            )
            assert response.status == 400
            html = response.text()
            assert "<script>alert(1)</script>" not in html
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
            assert "Maximum waiting time" in html
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, created_key_id)) == {
                "mode": "wait",
                "max_wait_seconds": 40,
                "max_waiting_requests": 3,
            }
        finally:
            context.close()


@pytest.mark.playwright
def test_admin_lazy_throttling_negatives_leave_policy_unchanged(
    owned_pg_url: str,
) -> None:
    """CSRF / unauthorized / missing-reason / invalid-bounds negatives."""
    data = asyncio.run(_create_lazy_browser_data(owned_pg_url))
    key_id = data["key_id"]
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        # --- unauthorized: no admin session ---
        anon_context = browser.new_context(base_url=base_url)
        anon_page = anon_context.new_page()
        try:
            anon_page.goto(f"/admin/keys/{key_id}")
            anon_page.wait_for_url("**/admin/login", timeout=10000)
            anon_response = _post_lazy_update(
                anon_context,
                key_id,
                csrf_token="anonymous-cannot-know-this",
                mode="wait",
                max_wait_seconds="45",
                max_waiting_requests="4",
                reason="anonymous attempt",
            )
            assert anon_response.status == 303
            assert "/admin/login" in anon_response.headers.get("location", "")
        finally:
            anon_context.close()
        assert _run_in_thread(_stored_lazy_policy(owned_pg_url, key_id)) == WAIT_POLICY

        # --- authenticated context for the remaining negatives ---
        context = browser.new_context(base_url=base_url)
        page = context.new_page()
        try:
            _login(page, data)

            # --- bad CSRF token: 400, policy unchanged ---
            page.goto(f"/admin/keys/{key_id}")
            csrf = _lazy_csrf_token(page)
            bad_csrf_response = _post_lazy_update(
                context,
                key_id,
                csrf_token="not-the-session-token",
                mode="wait",
                max_wait_seconds="45",
                max_waiting_requests="4",
                reason="bad csrf attempt",
            )
            assert bad_csrf_response.status == 400
            assert "Invalid CSRF token." in bad_csrf_response.text()
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, key_id)) == WAIT_POLICY

            # --- missing reason: redisplayed with the required-reason error ---
            no_reason_response = _post_lazy_update(
                context,
                key_id,
                csrf_token=csrf,
                mode="wait",
                max_wait_seconds="50",
                max_waiting_requests="5",
                reason="   ",
            )
            assert no_reason_response.status == 400
            assert (
                "Enter an audit reason before updating lazy throttling policy."
                in no_reason_response.text()
            )
            assert _run_in_thread(_stored_lazy_policy(owned_pg_url, key_id)) == WAIT_POLICY

            # --- invalid bounds: ceiling and non-positive both refuse ---
            for bad_wait, bad_waiting in (("999999", "4"), ("0", "-1")):
                invalid_response = _post_lazy_update(
                    context,
                    key_id,
                    csrf_token=csrf,
                    mode="wait",
                    max_wait_seconds=bad_wait,
                    max_waiting_requests=bad_waiting,
                    reason="invalid bounds attempt",
                )
                assert invalid_response.status == 400
                assert "Maximum waiting" in invalid_response.text()
                assert _run_in_thread(_stored_lazy_policy(owned_pg_url, key_id)) == WAIT_POLICY
        finally:
            context.close()
