"""210-a GUI reviewed route configuration: real Chromium on the owned PostgreSQL.

Actual uvicorn app, real stylesheet, and real admin pages against the
qualified owned, labeled, loopback-bound, tmpfs-backed PostgreSQL
fixture. Exercises the 210-a reviewed route-configuration workflow end
to end, one seeded route PER SCENARIO (no order dependence between
cases):

- the entry link from the route detail page and the form's safe
  progressive-enhancement initial states (real JS);
- the KEYBOARD guided partial plan -> review -> confirm/apply flow with
  independent persisted-DB and audit oracles (tri-state action selects,
  real keyboard for the notes entry, confirm checkbox, and submission);
- (planned in the same order) the complete-replacement document flow,
  the no-JS fallback, the populated capability-source transitions,
  provider notes intents and route-creation intents, and the help
  associations.

Safety: only synthetic fixture values are read; the ENV variable NAME
(GUI210_SVC_KEY) is a literal fixture identifier, never a secret value
(no such environment variable is set). The signed review token is
checked only by BOOLEANS (present / not retained); it is never printed
or screenshotted. Screenshots (synthetic data only) go under
/tmp/slaif210/. No result page is screenshotted.

Run:  python -m pytest tests/browser/test_admin_provider_route_configuration_210.py -m playwright
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, ModelRoute, ProviderConfig
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif210")

KEYBOARD_REASON = "210 browser guided route normalization"
NEW_NOTES = "210 browser updated route notes"
OLD_NOTES = "210 browser route notes"
KEYBOARD_PRIORITY = "150"
KEYBOARD_MAX_OUTPUT = "200000"

CHAT_BLOCK = {"chat_text": True, "chat_streaming": True, "chat_function_tools": False}
CODEX_BLOCK = {
    "context_window_tokens": 1050000,
    "default_max_output_tokens": 32768,
    "max_output_tokens": 128000,
}

FULL_REASON = "210 browser complete capabilities replacement"
NOJS_REASON = "210 browser no-js route normalization"
PROVIDER_REASON = "210 browser provider notes cleared"
CREATE_AUTO_REASON = "210 browser prepared (automatic) route creation"
CREATE_EXP_REASON = "210 browser explicitly enabled route creation"

# Strict version-1 complete-replacement document for the r_full scenario:
# it re-authors the capability state (responses kept, codex_limits added;
# the shared preview normalizes the proposal to its canonical state, so
# the test compares the STORED result to the reviewed canonical proposal
# read from the page, plus explicit leaf expectations).
FULL_DOC_TEXT = (
    '{"schema_version": 1, "capabilities": {"responses": {"text": true}, '
    '"codex_limits": {"context_window_tokens": 200000, '
    '"default_max_output_tokens": 8192, "max_output_tokens": 32000}}}'
)
CREATE_CAPS_TEXT = '{"chat_completions": {"chat_text": true}}'


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


def _settings(database_url: str) -> Settings:
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
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


# ---------------------------------------------------------------------------
# Seed (fixture data only: direct ORM inserts, synthetic material; one
# route per scenario so the cases never depend on each other's writes)
# ---------------------------------------------------------------------------


async def _seed_route_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui210b-{suffix}@example.org",
                    display_name="210 Route GUI Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                providers = ProviderConfigsRepository(session)
                compatible = await providers.create_provider_config(
                    provider=f"210compat-{suffix}",
                    display_name="210 Compat (browser)",
                    kind="openai_compatible",
                    base_url=f"https://svc-210-{suffix}.example/v1",
                    api_key_env_var="GUI210_SVC_KEY",
                    enabled=True,
                    timeout_seconds=300,
                    max_retries=0,
                    notes="210 browser compatible provider notes",
                )
                routes = ModelRoutesRepository(session)

                def _route_args(name: str, capabilities: dict[str, Any], notes: str | None = OLD_NOTES) -> dict[str, Any]:
                    return dict(
                        requested_model=f"210-{name}-{suffix}",
                        match_type="exact",
                        endpoint="/v1/chat/completions",
                        provider=compatible.provider,
                        upstream_model=f"210-{name}-{suffix}",
                        priority=100,
                        enabled=True,
                        visible_in_models=True,
                        supports_streaming=True,
                        capabilities=capabilities,
                        notes=notes,
                    )

                r_keyboard = await routes.create_model_route(
                    **_route_args(
                        "kb",
                        {
                            "chat_completions": dict(CHAT_BLOCK),
                            "codex_limits": dict(CODEX_BLOCK),
                        },
                    )
                )
                r_full = await routes.create_model_route(
                    **_route_args(
                        "full",
                        {
                            "chat_completions": {"chat_text": True},
                            "responses": {"text": True},
                        },
                    )
                )
                r_nojs = await routes.create_model_route(
                    **_route_args(
                        "nojs",
                        {"chat_completions": {"chat_text": True}},
                    )
                )
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "provider_slug": compatible.provider,
                    "provider_id": str(compatible.id),
                    "r_keyboard": str(r_keyboard.id),
                    "r_full": str(r_full.id),
                    "r_nojs": str(r_nojs.id),
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


def _route_snapshot(database_url: str, route_ids: tuple[str, ...]) -> dict[str, Any]:
    """Stable field values (no timestamps) for exact state oracles."""

    async def _get(session):
        rows = (
            (
                await session.execute(
                    select(ModelRoute).where(
                        ModelRoute.id.in_([uuid.UUID(r) for r in route_ids])
                    )
                )
            )
            .scalars()
            .all()
        )
        out: dict[str, Any] = {}
        for row in rows:
            out[str(row.id)] = {
                "requested_model": row.requested_model,
                "match_type": row.match_type,
                "endpoint": row.endpoint,
                "provider": row.provider,
                "upstream_model": row.upstream_model,
                "priority": row.priority,
                "enabled": row.enabled,
                "visible_in_models": row.visible_in_models,
                "supports_streaming": row.supports_streaming,
                "capabilities": json.loads(json.dumps(row.capabilities)),
                "notes": row.notes,
            }
        return out

    return _db(database_url, _get)


def _provider_state(database_url: str, provider_id: str) -> tuple[Any, ...]:
    async def _get(session):
        row = await session.get(ProviderConfig, uuid.UUID(provider_id))
        assert row is not None
        return (
            row.provider,
            row.kind,
            row.base_url,
            row.api_key_env_var,
            row.enabled,
            row.timeout_seconds,
            row.max_retries,
            row.notes,
        )

    return _db(database_url, _get)


def _route_by_model(database_url: str, requested_model: str) -> dict[str, Any]:
    async def _get(session):
        row = (
            (
                await session.execute(
                    select(ModelRoute).where(
                        ModelRoute.requested_model == requested_model
                    )
                )
            )
            .scalars()
            .first()
        )
        assert row is not None, f"created route not found: {requested_model}"
        return {
            "id": str(row.id),
            "enabled": row.enabled,
            "provider": row.provider,
            "priority": row.priority,
            "capabilities": json.loads(json.dumps(row.capabilities)),
            "notes": row.notes,
            "visible_in_models": row.visible_in_models,
            "supports_streaming": row.supports_streaming,
        }

    return _db(database_url, _get)


def _entity_audits(
    database_url: str,
    entity_type: str,
    entity_id: str,
    admin_id: str,
) -> list[dict[str, Any]]:
    """Audit rows scoped to ONE entity of this seed (same shape as the
    210 PG oracles: entity_type + entity_id + actor; ``note`` carries
    the audit reason)."""

    async def _get(session):
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == entity_type,
                        AuditLog.entity_id == uuid.UUID(entity_id),
                        AuditLog.admin_user_id == uuid.UUID(admin_id),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [{"action": r.action, "note": r.note} for r in rows]

    return _db(database_url, _get)


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def route_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_route_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    data["database_url"] = owned_pg_url
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(route_env) -> Iterator[object]:
    """Depends on ``route_env`` on purpose: the Playwright sync session
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
    page.goto("/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f"{LOGIN_FORM} button[type='submit']")  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _screenshot(page: object, name: str, full_page: bool = False) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(  # type: ignore[attr-defined]
        path=str(SCREENSHOT_DIR / name), full_page=full_page
    )


def _screenshot_element(page: object, selector: str, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    locator = page.locator(selector)  # type: ignore[attr-defined]
    locator.first.scroll_into_view_if_needed()  # type: ignore[attr-defined]
    locator.first.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _flat(page: object) -> str:
    return re.sub(r"\s+", " ", page.content())  # type: ignore[attr-defined]


def _plan_form_selector(route_id: str) -> str:
    return f'form[action="/admin/routes/{route_id}/configuration/plan"][data-cfg-root]'


def _form_data(page: object, route_id: str) -> dict[str, str]:
    """The live form serialization - exactly what a submission carries
    (disabled controls are absent)."""
    return page.evaluate(  # type: ignore[attr-defined]
        """() => Object.fromEntries(
             new FormData(document.querySelector(%r))
               .entries())"""
        % _plan_form_selector(route_id)
    )


def _assert_no_token_on_page(page: object, token_value: str) -> None:
    """The signed review state must never be retained on a later page.
    Boolean only - a failure never echoes the value."""
    present = bool(token_value) and token_value in page.content()  # type: ignore[attr-defined]
    assert present is False, "review token retained on page"


def _pick_option(page: object, input_name: str, query: str, option_text: str) -> None:
    """Search a known-only record-choice picker and click one option."""
    rc = page.locator(f'[data-rc][data-input-name="{input_name}"]')  # type: ignore[attr-defined]
    rc.locator(".rc-input").click()
    page.keyboard.type(query)  # type: ignore[attr-defined]
    option = rc.locator(f"li.rc-option:has-text('{option_text}')")
    option.wait_for(state="visible", timeout=15000)
    option.click()


def _type_new(page: object, input_name: str, value: str) -> None:
    """Commit a NEW value in an allow-new single record-choice picker."""
    rc = page.locator(f'[data-rc][data-input-name="{input_name}"]')  # type: ignore[attr-defined]
    rc.locator(".rc-input").click()
    page.keyboard.type(value)  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]


def _rc_value(page: object, input_name: str) -> str:
    return page.input_value(  # type: ignore[attr-defined]
        f'[data-rc][data-input-name="{input_name}"] .rc-value'
    )


# ---------------------------------------------------------------------------
# 1) Entry link from the route detail + form initial state (real JS)
# ---------------------------------------------------------------------------


def test_entry_link_and_form_initial_state(chromium, route_env) -> None:
    env = route_env
    route_id = env["r_keyboard"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)

        # Entry point from the ROUTE DETAIL page.
        page.goto(f"/admin/routes/{route_id}")  # type: ignore[attr-defined]
        link = page.locator(f'a[href="/admin/routes/{route_id}/configuration"]')
        assert link.count() == 1
        assert "Reviewed configuration change" in link.first.inner_text()
        _screenshot_element(
            page,
            'section:has(a[href="%s"])' % f"/admin/routes/{route_id}/configuration",
            "210-entry-detail.png",
        )
        link.first.click()
        page.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]

        flat = _flat(page)
        assert "Reviewed configuration change" in flat
        for heading in (
            "Match",
            "Target",
            "Flags",
            "Notes",
            "Capabilities",
            "Prepare reviewed plan",
        ):
            assert heading in flat, f"form section missing: {heading}"
        # The read-only current-notes projection renders the seeded notes.
        assert page.locator("#route-config-notes-current").inner_text() == OLD_NOTES

        # Real JS progressive enhancement at the DEFAULT (unchanged)
        # source: the guided and full groups are hidden AND disabled, the
        # replacement notes entry is disabled (intent=preserve), and every
        # action-paired value control is disabled while its action says
        # Keep current.
        states = page.evaluate(
            """() => ({
                guided_hidden: document.querySelector('#cfg-guided-group').hidden,
                guided_disabled: document.querySelector('#cfg-guided-group').disabled,
                full_hidden: document.querySelector('#cfg-full-group').hidden,
                full_disabled: document.querySelector('#cfg-full-group').disabled,
                notes_disabled:
                    document.querySelector('textarea[name="notes"]').disabled,
                priority_value_disabled:
                    document.querySelector('#cfg-priority_value').disabled,
                codex_value_disabled:
                    document.querySelector('#cfg-codex_max_output_value').disabled,
            })"""
        )
        assert states["guided_hidden"] is True
        assert states["guided_disabled"] is True
        assert states["full_hidden"] is True
        assert states["full_disabled"] is True
        assert states["notes_disabled"] is True
        assert states["priority_value_disabled"] is True
        assert states["codex_value_disabled"] is True

        _screenshot_element(
            page,
            "section[aria-labelledby='route-config-match-heading']",
            "210-form-match.png",
        )
        _screenshot_element(
            page,
            "section[aria-labelledby='route-config-capabilities-heading']",
            "210-form-capabilities.png",
        )
        # Meaningful desktop view: the WHOLE form in one capture (the
        # element captures above leave the viewport scrolled).
        _screenshot(page, "210-form-desktop.png", full_page=True)

        # Narrow (480px) viewport: the form stays inside the viewport.
        narrow = chromium.new_context(  # type: ignore[attr-defined]
            base_url=env["base_url"], viewport={"width": 480, "height": 900}
        )
        try:
            npage = narrow.new_page()
            _login(npage, env)
            npage.goto(f"/admin/routes/{route_id}/configuration")  # type: ignore[attr-defined]
            npage.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]
            overflow = npage.evaluate(  # type: ignore[attr-defined]
                "() => document.documentElement.scrollWidth"
                " - document.documentElement.clientWidth"
            )
            assert overflow <= 0, "form overflows the 480px viewport"
            _screenshot_element(
                npage,
                "section[aria-labelledby='route-config-capabilities-heading']",
                "210-form-capabilities-narrow.png",
            )
        finally:
            narrow.close()


# ---------------------------------------------------------------------------
# 2) Keyboard guided partial: plan -> review -> confirm/apply -> DB
# ---------------------------------------------------------------------------


def test_keyboard_guided_plan_apply(chromium, route_env) -> None:
    env = route_env
    route_id = env["r_keyboard"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/routes/{route_id}/configuration")  # type: ignore[attr-defined]
        page.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]

        # Guided source: the guided group becomes visible+enabled and the
        # paired value control enables when its action selects Set.
        page.check("input[name='capabilities_source'][value='guided']")  # type: ignore[attr-defined]
        page.select_option("select[name='priority_action']", "set")  # type: ignore[attr-defined]
        assert page.locator("#cfg-priority_value").is_enabled()
        page.fill("#cfg-priority_value", KEYBOARD_PRIORITY)  # type: ignore[attr-defined]

        # Notes: the replacement entry enables for the replace intent,
        # and the text is entered with the real keyboard.
        page.check("input[name='notes_intent'][value='replace']")  # type: ignore[attr-defined]
        notes_area = page.locator("textarea[name='notes']")  # type: ignore[attr-defined]
        notes_area.focus()
        page.keyboard.type(NEW_NOTES)  # type: ignore[attr-defined]

        # Capability leaves: one codex token leaf + one Chat flag flip.
        page.select_option("select[name='codex_max_output_action']", "set")  # type: ignore[attr-defined]
        page.fill("#cfg-codex_max_output_value", KEYBOARD_MAX_OUTPUT)  # type: ignore[attr-defined]
        # The Chat flags live in a native disclosure: an operator opens it
        # with the keyboard before changing a flag (no forced hidden
        # interaction; the progressive disclosure stays intact).
        summary = page.locator("#cfg-chat-flags-summary")  # type: ignore[attr-defined]
        summary.focus()
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        assert page.locator("details:has(#cfg-chat-flags-summary)[open]").count() == 1
        page.select_option("select[name='chat_chat_streaming_action']", "false")  # type: ignore[attr-defined]

        # Submit the READ-ONLY plan.
        page.click(f"{_plan_form_selector(route_id)} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="route_config_review_intent"]', state="attached"
        )

        flat = _flat(page)
        assert "Reviewed route plan" in flat
        assert "Nothing has been written yet" in flat

        # Readable diff table: the changed canonical fields with their
        # before/after values (Priority 100 -> 150, notes replacement).
        diff_text = page.locator("div.table-wrap table tbody").first.inner_text()
        assert "Priority" in diff_text
        assert "100" in diff_text and "150" in diff_text
        assert OLD_NOTES in diff_text and NEW_NOTES in diff_text

        # Capability changes name the ACTUAL changed leaves with the
        # shared M-token + exact-count readout; untouched leaves are not
        # listed.
        cap_list = page.locator(
            "section[aria-labelledby='route-review-capabilities-heading'] ul"
        ).first.inner_text()
        assert "Codex max output" in cap_list
        assert "0.128M (128,000)" in cap_list
        assert "0.2M (200,000)" in cap_list
        assert "Chat capability: chat_streaming" in cap_list
        assert "enabled \u2192 disabled" in cap_list
        assert "Codex context window" not in cap_list
        assert "Codex default max output" not in cap_list

        # Destination provider context: the ENV variable NAME is shown
        # literally; no key value is ever rendered (none is set).
        assert env["provider_slug"] in flat
        assert "GUI210_SVC_KEY" in flat

        _screenshot_element(
            page,
            "section[aria-labelledby='route-review-diff-heading']",
            "210-review-diff.png",
        )

        # Narrow (390px) review: the wrapped diff table must stay inside
        # the viewport and the apply control must remain reachable.
        page.set_viewport_size({"width": 390, "height": 900})  # type: ignore[attr-defined]
        overflow = page.evaluate(  # type: ignore[attr-defined]
            "() => document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        assert overflow <= 0, "review document overflows the 390px viewport"
        _screenshot_element(
            page,
            "section[aria-labelledby='route-review-diff-heading']",
            "210-review-diff-narrow.png",
        )
        apply_button = page.locator(  # type: ignore[attr-defined]
            'form[action$="/configuration/apply"] button[type="submit"]'
        )
        apply_button.scroll_into_view_if_needed()  # type: ignore[attr-defined]
        assert apply_button.is_visible(), "apply control not reachable at 390px"
        page.set_viewport_size({"width": 1440, "height": 900})  # type: ignore[attr-defined]

        # Keyboard-only apply: focus the confirm checkbox, Space to
        # check, type the reason with the real keyboard, Enter to submit
        # (no mouse click on the checkbox or the submit button).
        token_value = page.get_attribute(  # type: ignore[attr-defined]
            'input[name="route_config_review_intent"]', "value"
        )
        assert token_value
        confirm_box = page.locator("input[name='confirm_apply']")  # type: ignore[attr-defined]
        confirm_box.focus()
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert confirm_box.is_checked()
        reason_input = page.locator("input[name='reason']")  # type: ignore[attr-defined]
        reason_input.focus()
        page.keyboard.type(KEYBOARD_REASON)  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        page.wait_for_selector("#route-result-heading")  # type: ignore[attr-defined]

        flat = _flat(page)
        assert "The reviewed plan was applied" in flat
        _assert_no_token_on_page(page, token_value)

        # Independent persisted-DB oracles (separate worker thread).
        db = env["database_url"]
        snap = _route_snapshot(db, (route_id,))
        row = snap[route_id]
        assert row["priority"] == int(KEYBOARD_PRIORITY)
        assert row["notes"] == NEW_NOTES
        caps = row["capabilities"]
        assert caps["codex_limits"]["max_output_tokens"] == int(KEYBOARD_MAX_OUTPUT)
        # Deep siblings preserved by the guided partial patch:
        assert caps["codex_limits"]["context_window_tokens"] == 1050000
        assert caps["codex_limits"]["default_max_output_tokens"] == 32768
        assert caps["chat_completions"]["chat_text"] is True
        assert caps["chat_completions"]["chat_streaming"] is False
        assert caps["chat_completions"]["chat_function_tools"] is False
        # Everything outside the reviewed change is untouched:
        assert row["match_type"] == "exact"
        assert row["endpoint"] == "/v1/chat/completions"
        assert row["provider"] == env["provider_slug"]
        assert row["upstream_model"] == f"210-kb-{env['suffix']}"
        assert row["enabled"] is True
        assert row["visible_in_models"] is True

        # Audit: exactly ONE model_route_updated row scoped to THIS route
        # and admin, with the keyboard-entered reason in ``note``.
        audits = _entity_audits(db, "model_route", route_id, env["admin_id"])
        assert audits == [{"action": "model_route_updated", "note": KEYBOARD_REASON}]
        # Planning itself wrote nothing else: no provider audit rows.
        assert _entity_audits(db, "provider_config", env["provider_id"], env["admin_id"]) == []


# ---------------------------------------------------------------------------
# 3) Populated capability-source transitions (real JS, no submission)
# ---------------------------------------------------------------------------


def test_js_capability_source_transitions(chromium, route_env) -> None:
    env = route_env
    route_id = env["r_keyboard"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/routes/{route_id}/configuration")  # type: ignore[attr-defined]
        page.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]

        # Populate a target edit + a guided leaf while the source is the
        # default (unchanged): the guided group is hidden+disabled, so
        # populate via the enabled target control first.
        page.select_option("select[name='priority_action']", "set")  # type: ignore[attr-defined]
        page.fill("#cfg-priority_value", "175")  # type: ignore[attr-defined]

        # (i) guided: the guided group activates; the typed leaf value is
        # submitted, the replacement document is absent.
        page.check("input[name='capabilities_source'][value='guided']")  # type: ignore[attr-defined]
        states = page.evaluate(  # type: ignore[attr-defined]
            """() => ({
                g_visible: !document.querySelector('#cfg-guided-group').hidden,
                g_enabled: !document.querySelector('#cfg-guided-group').disabled,
                f_hidden: document.querySelector('#cfg-full-group').hidden,
                f_disabled: document.querySelector('#cfg-full-group').disabled,
            })"""
        )
        assert states["g_visible"] is True and states["g_enabled"] is True
        assert states["f_hidden"] is True and states["f_disabled"] is True
        page.select_option("select[name='codex_max_output_action']", "set")  # type: ignore[attr-defined]
        page.fill("#cfg-codex_max_output_value", "300000")  # type: ignore[attr-defined]
        data = _form_data(page, route_id)
        assert data.get("priority") == "175"
        assert data.get("codex_max_output_value") == "300000"
        assert "capabilities_document" not in data

        # (ii) full: the typed complete document is submitted; the guided
        # group (action selects AND value inputs) is fully absent because
        # the disabled fieldset disables every descendant.
        page.check("input[name='capabilities_source'][value='full']")  # type: ignore[attr-defined]
        states = page.evaluate(  # type: ignore[attr-defined]
            """() => ({
                f_visible: !document.querySelector('#cfg-full-group').hidden,
                f_enabled: !document.querySelector('#cfg-full-group').disabled,
                g_hidden: document.querySelector('#cfg-guided-group').hidden,
                g_disabled: document.querySelector('#cfg-guided-group').disabled,
            })"""
        )
        assert states["f_visible"] is True and states["f_enabled"] is True
        assert states["g_hidden"] is True and states["g_disabled"] is True
        doc_area = page.locator("textarea[name='capabilities_document']")  # type: ignore[attr-defined]
        doc_area.focus()
        page.keyboard.type(FULL_DOC_TEXT)  # type: ignore[attr-defined]
        data = _form_data(page, route_id)
        assert data.get("capabilities_document") == FULL_DOC_TEXT
        assert data.get("priority") == "175", "target edits are source-independent"
        for absent in (
            "codex_max_output_value",
            "codex_max_output_action",
            "completion_action",
            "codex_context_value",
        ):
            assert absent not in data, f"stale guided control {absent} submitted"

        # (iii) unchanged: BOTH groups are hidden+disabled; neither the
        # document nor any guided leaf rides along (the target edit still
        # submits - it is not part of the capability source).
        page.check("input[name='capabilities_source'][value='unchanged']")  # type: ignore[attr-defined]
        assert page.locator("#cfg-guided-group").is_hidden()
        assert page.locator("#cfg-full-group").is_hidden()
        data = _form_data(page, route_id)
        assert "capabilities_document" not in data
        assert "codex_max_output_value" not in data
        assert "codex_max_output_action" not in data
        assert data.get("priority") == "175"


# ---------------------------------------------------------------------------
# 4) Complete replacement document: plan -> apply -> exact capabilities
# ---------------------------------------------------------------------------


def test_full_document_replacement_flow(chromium, route_env) -> None:
    env = route_env
    route_id = env["r_full"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/routes/{route_id}/configuration")  # type: ignore[attr-defined]
        page.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]

        page.check("input[name='capabilities_source'][value='full']")  # type: ignore[attr-defined]
        doc_area = page.locator("textarea[name='capabilities_document']")  # type: ignore[attr-defined]
        doc_area.focus()
        page.keyboard.type(FULL_DOC_TEXT)  # type: ignore[attr-defined]
        page.click(f"{_plan_form_selector(route_id)} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="route_config_review_intent"]', state="attached"
        )

        flat = _flat(page)
        assert "Reviewed route plan" in flat
        # The readable diff names the ACTUAL leaf consequences of the
        # complete replacement: the added codex leaves, and the normalized
        # defaults that now appear explicitly (absent -> disabled).
        cap_list = page.locator(
            "section[aria-labelledby='route-review-capabilities-heading'] ul"
        ).first.inner_text()
        assert "Codex context window" in cap_list
        assert "0.2M (200,000)" in cap_list
        assert "Codex default max output" in cap_list
        assert "0.008192M (8,192)" in cap_list
        assert "Codex max output" in cap_list
        assert "0.032M (32,000)" in cap_list
        assert "Chat capability: hosted_web_search" in cap_list
        assert "(absent) \u2192 disabled" in cap_list
        # chat_text stays true under the shared defaults: no change row.
        assert "Chat capability: chat_text" not in cap_list
        # The exact machine plan stays available in the raw disclosure:
        # an operator opens it with the keyboard before reading it (the
        # closed <details> hides the <pre> from inner_text).
        raw_summary = page.locator(
            "section[aria-labelledby='route-review-raw-heading'] summary"
        )
        raw_summary.focus()
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        assert (
            page.locator(
                "section[aria-labelledby='route-review-raw-heading'] details[open]"
            ).count()
            == 1
        )
        raw_pre = page.locator("pre.config-json")
        assert raw_pre.count() == 1
        plan_doc = json.loads(raw_pre.first.inner_text())
        proposed_caps = (
            plan_doc["preview"]["proposed_configuration"]["capabilities"]
        )
        # Explicit leaf expectations on the reviewed canonical proposal.
        assert proposed_caps["codex_limits"] == {
            "context_window_tokens": 200000,
            "default_max_output_tokens": 8192,
            "max_output_tokens": 32000,
        }
        assert proposed_caps["responses"]["text"] is True
        assert proposed_caps.get("chat_completions", {}).get("chat_text") is True

        _screenshot_element(
            page,
            "section[aria-labelledby='route-review-capabilities-heading']",
            "210-review-full-caps.png",
        )

        token_value = page.get_attribute(  # type: ignore[attr-defined]
            'input[name="route_config_review_intent"]', "value"
        )
        assert token_value
        page.check("input[name='confirm_apply']")  # type: ignore[attr-defined]
        page.fill("input[name='reason']", FULL_REASON)  # type: ignore[attr-defined]
        page.click(  # type: ignore[attr-defined]
            'form[action$="/configuration/apply"] button[type="submit"]'
        )
        page.wait_for_selector("#route-result-heading")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "The reviewed plan was applied" in flat
        _assert_no_token_on_page(page, token_value)

        # Independent persisted-DB oracle: the STORED capabilities are
        # EXACTLY the reviewed canonical proposal (shared normalization
        # included), and everything else on the route is preserved.
        db = env["database_url"]
        snap = _route_snapshot(db, (route_id,))
        row = snap[route_id]
        assert row["capabilities"] == proposed_caps
        assert row["capabilities"]["responses"]["text"] is True
        assert row["priority"] == 100
        assert row["notes"] == OLD_NOTES
        assert row["enabled"] is True
        assert row["upstream_model"] == f"210-full-{env['suffix']}"
        audits = _entity_audits(db, "model_route", route_id, env["admin_id"])
        assert audits == [{"action": "model_route_updated", "note": FULL_REASON}]


# ---------------------------------------------------------------------------
# 5) No-JS fallback: the server-rendered form is complete and valid
# ---------------------------------------------------------------------------


def test_nojs_fallback_flow(chromium, route_env) -> None:
    env = route_env
    route_id = env["r_nojs"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], java_script_enabled=False
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/routes/{route_id}/configuration")  # type: ignore[attr-defined]
        page.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]

        # Without JavaScript every group and control is visible and
        # enabled (the progressive enhancement adds hiding/disabling).
        states = page.evaluate(  # type: ignore[attr-defined]
            """() => ({
                guided_visible:
                    !document.querySelector('#cfg-guided-group').hidden
                    && !document.querySelector('#cfg-guided-group').disabled,
                full_visible:
                    !document.querySelector('#cfg-full-group').hidden
                    && !document.querySelector('#cfg-full-group').disabled,
                notes_enabled: !document.querySelector('textarea[name="notes"]').disabled,
                priority_enabled: !document.querySelector('#cfg-priority_value').disabled,
            })"""
        )
        assert states["guided_visible"] is True
        assert states["full_visible"] is True
        assert states["notes_enabled"] is True
        assert states["priority_enabled"] is True

        # Native fields, same server law: priority change + notes clear.
        page.select_option("select[name='priority_action']", "set")  # type: ignore[attr-defined]
        page.fill("#cfg-priority_value", "250")  # type: ignore[attr-defined]
        page.check("input[name='notes_intent'][value='clear']")  # type: ignore[attr-defined]
        page.click(f"{_plan_form_selector(route_id)} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="route_config_review_intent"]', state="attached"
        )

        diff_text = page.locator("div.table-wrap table tbody").first.inner_text()
        assert "Priority" in diff_text
        assert "100" in diff_text and "250" in diff_text
        # A cleared notes value renders the generic null label in the diff
        # table; the DB null below is the authoritative oracle.
        assert OLD_NOTES in diff_text and "(none)" in diff_text

        page.check("input[name='confirm_apply']")  # type: ignore[attr-defined]
        page.fill("input[name='reason']", NOJS_REASON)  # type: ignore[attr-defined]
        page.click(  # type: ignore[attr-defined]
            'form[action$="/configuration/apply"] button[type="submit"]'
        )
        page.wait_for_selector("#route-result-heading")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "The reviewed plan was applied" in flat

        db = env["database_url"]
        snap = _route_snapshot(db, (route_id,))
        row = snap[route_id]
        assert row["priority"] == 250
        assert row["notes"] is None
        assert row["capabilities"] == {"chat_completions": {"chat_text": True}}
        assert row["enabled"] is True
        audits = _entity_audits(db, "model_route", route_id, env["admin_id"])
        assert audits == [{"action": "model_route_updated", "note": NOJS_REASON}]


# ---------------------------------------------------------------------------
# 6) Provider notes clear + route-creation intents
# ---------------------------------------------------------------------------


def test_provider_edit_notes_clear(chromium, route_env) -> None:
    env = route_env
    provider_id = env["provider_id"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/providers/{provider_id}/edit")  # type: ignore[attr-defined]
        edit_form = f'form[action="/admin/providers/{provider_id}/edit"]'
        page.wait_for_selector(edit_form)  # type: ignore[attr-defined]

        # The current notes are shown read-only; the replacement entry is
        # blank and the clear intent needs no replacement text.
        current_dd = page.locator(
            "dl:has(> dt:text-is('Current notes')) dd"
        ).first.inner_text()
        assert current_dd == "210 browser compatible provider notes"
        assert page.input_value(f"{edit_form} textarea[name='notes']") == ""

        page.check(f"{edit_form} input[name='notes_intent'][value='clear']")  # type: ignore[attr-defined]
        page.fill(f"{edit_form} input[name='reason']", PROVIDER_REASON)  # type: ignore[attr-defined]
        page.click(f"{edit_form} button[type='submit']")  # type: ignore[attr-defined]
        # The edit POST 303-redirects to the detail page with a ?message
        # query; match the path prefix, not a bare path glob.
        page.wait_for_url(re.compile(rf"/admin/providers/{provider_id}"))  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "No notes." in flat

        # Independent persisted-DB oracles: the notes are cleared and
        # EVERY other provider field is preserved.
        state = _provider_state(env["database_url"], provider_id)
        (slug, kind, base_url, env_var, enabled, timeout, retries, notes) = state
        assert slug == env["provider_slug"]
        assert kind == "openai_compatible"
        assert base_url == f"https://svc-210-{env['suffix']}.example/v1"
        assert env_var == "GUI210_SVC_KEY"
        assert enabled is True
        assert timeout == 300
        assert retries == 0
        assert notes is None
        audits = _entity_audits(env["database_url"], "provider_config", provider_id, env["admin_id"])
        assert audits == [{"action": "provider_config_updated", "note": PROVIDER_REASON}]


def test_route_creation_intents(chromium, route_env) -> None:
    env = route_env
    auto_model = f"210-newauto-{env['suffix']}"
    exp_model = f"210-newexp-{env['suffix']}"
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)

        def _create(model: str, intent: str, reason: str) -> None:
            page.goto("/admin/routes/new")  # type: ignore[attr-defined]
            page.wait_for_selector('form[action="/admin/routes/new"]')  # type: ignore[attr-defined]
            _pick_option(page, "endpoint", "/v1/chat", "/v1/chat/completions")
            _pick_option(page, "provider", env["provider_slug"], env["provider_slug"])
            assert _rc_value(page, "provider") == env["provider_slug"]
            # requested_model depends on the provider picker: choosing the
            # provider AFTER the model would clear the dependent value, so
            # the model is committed LAST.
            _type_new(page, "requested_model", model)
            assert _rc_value(page, "requested_model") == model
            page.fill('form[action="/admin/routes/new"] input[name=\'priority\']', "10")  # type: ignore[attr-defined]
            page.fill('form[action="/admin/routes/new"] textarea[name=\'capabilities\']', CREATE_CAPS_TEXT)  # type: ignore[attr-defined]
            page.fill('form[action="/admin/routes/new"] input[name=\'reason\']', reason)  # type: ignore[attr-defined]
            page.check(f"input[name='creation_intent'][value='{intent}']")  # type: ignore[attr-defined]
            # Required values exactly as the form will submit them.
            data = page.evaluate(  # type: ignore[attr-defined]
                """() => Object.fromEntries(
                     new FormData(
                         document.querySelector('form[action="/admin/routes/new"]')
                     ).entries())"""
            )
            assert data.get("requested_model") == model
            assert data.get("provider") == env["provider_slug"]
            assert data.get("endpoint") == "/v1/chat/completions"
            assert data.get("priority") == "10"
            assert data.get("capabilities") == CREATE_CAPS_TEXT
            assert data.get("creation_intent") == intent
            with page.expect_response(  # type: ignore[attr-defined]
                lambda r: r.request.method == "POST"
                and r.url.endswith("/admin/routes/new"),
                timeout=15000,
            ) as info:
                page.click('form[action="/admin/routes/new"] button[type=\'submit\']')  # type: ignore[attr-defined]
            response = info.value
            if response.status != 303:
                # A refusal re-renders the form with the shared fixed safe
                # message (it never echoes input): surface it, do not wait.
                flash = page.locator(".admin-flash-error")
                message = flash.first.inner_text() if flash.count() else "(no flash)"
                raise AssertionError(f"route create refused ({response.status}): {message}")
            # 303 -> the NEW route's detail page (UUID path segment).
            page.wait_for_url(  # type: ignore[attr-defined]
                re.compile(r"/admin/routes/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
            )

        # Automatic + a capabilities document: the shared candidate law
        # prepares the route DISABLED (enabling later is the status action).
        _create(auto_model, "automatic", CREATE_AUTO_REASON)
        row = _route_by_model(env["database_url"], auto_model)
        assert row["enabled"] is False, "automatic + caps doc must prepare disabled"
        assert row["provider"] == env["provider_slug"]
        assert row["priority"] == 10
        assert row["capabilities"] == {"chat_completions": {"chat_text": True}}
        assert _entity_audits(env["database_url"], "model_route", row["id"], env["admin_id"]) == [
            {"action": "model_route_created", "note": CREATE_AUTO_REASON}
        ]

        # Enable explicitly: the same form in the explicit intent state.
        _create(exp_model, "explicit_enable", CREATE_EXP_REASON)
        row = _route_by_model(env["database_url"], exp_model)
        assert row["enabled"] is True, "explicit_enable must create enabled"
        assert row["capabilities"] == {"chat_completions": {"chat_text": True}}
        assert _entity_audits(env["database_url"], "model_route", row["id"], env["admin_id"]) == [
            {"action": "model_route_created", "note": CREATE_EXP_REASON}
        ]


# ---------------------------------------------------------------------------
# 7) Meaningful help associations (form + review)
# ---------------------------------------------------------------------------


def test_help_associations_resolve(chromium, route_env) -> None:
    env = route_env
    route_id = env["r_keyboard"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 1440, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/routes/{route_id}/configuration")  # type: ignore[attr-defined]
        page.wait_for_selector(_plan_form_selector(route_id))  # type: ignore[attr-defined]

        # Every picker's OWN help span resolves from the visible field's
        # aria-describedby (five distinct batch-only ids).
        resolved = page.evaluate(  # type: ignore[attr-defined]
            """(names) => {
              const out = {};
              for (const name of names) {
                const input = document.querySelector(
                  `[data-rc][data-input-name="${name}"] .rc-input`
                );
                const desc = input ? input.getAttribute("aria-describedby") : null;
                out[name] = !!desc && desc.split(/\\s+/).every(
                  (id) => document.getElementById(id)
                );
              }
              return out;
            }"""
            ,
            ["requested_model", "endpoint", "provider", "upstream_model", "completion_profile"],
        )
        assert all(resolved[name] for name in resolved), f"unresolved picker help: {resolved}"

        # Plan a small change so the review page renders (read-only).
        page.select_option("select[name='priority_action']", "set")  # type: ignore[attr-defined]
        page.fill("#cfg-priority_value", "160")  # type: ignore[attr-defined]
        page.click(f"{_plan_form_selector(route_id)} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="route_config_review_intent"]', state="attached"
        )

        review_help = page.evaluate(  # type: ignore[attr-defined]
            """() => {
              const inputs = [
                document.querySelector("input[name='confirm_apply']"),
                document.querySelector("input[name='reason']"),
              ];
              const ok = inputs.every(
                (el) => el
                  && el.getAttribute("aria-describedby")
                  && el.getAttribute("aria-describedby").split(/\\s+/).every(
                      (id) => document.getElementById(id)
                    )
              );
              const wrap = document.querySelector("div.table-wrap[tabindex]");
              return {
                review_inputs_linked: ok,
                table_focusable: !!wrap && !!wrap.getAttribute("aria-label"),
                ordinal_header: !!document.querySelector("th[data-ordinal]"),
                empty_state_row: !!document.querySelector("tr[data-no-sort] .empty-state"),
              };
            }"""
        )
        assert review_help["review_inputs_linked"] is True
        assert review_help["table_focusable"] is True
        assert review_help["ordinal_header"] is True
        # This plan HAS changed fields, so the empty-state row must NOT be
        # present (the authored empty row exists only for zero-change plans).
        assert review_help["empty_state_row"] is False
