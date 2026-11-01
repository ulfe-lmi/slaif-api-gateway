"""209-a GUI reviewed key batch: real Chromium on the owned PostgreSQL.

Actual uvicorn app, real stylesheet, and real admin pages against the
qualified owned, labeled, loopback-bound, tmpfs-backed PostgreSQL
fixture. Exercises the G05 acceptance workflow end to end: the entry
link and the form's safe initial disabled states (real JS, composed
sync), the populated control-transition regressions (allow-list value
never rides along with unrestricted/deny-all; the guided<->advanced
round trip and the keys<->cohort scope change while advanced keep
subordinate controls in the correct state; an inactive chip removed
while its mode is inactive cannot resubmit a stale value), the >100
multi-key selection with older search (no ``selected`` hydration params
on typed queries, the older match stays visible, the FULL selection is
submitted), the keyboard cohort plan/apply happy flow with independent
persisted-DB oracles, and the no-JS fallback flow (native fields, same
server law).

Safety: only synthetic fixture values are read; session and CSRF values
are used transiently and never logged. No batch page ever carries
generated key material, but the synthetic token hashes are still
asserted absent (booleans only) from every rendered page. Screenshots
(synthetic data only) go under /tmp/slaif209/.

Run:  python -m pytest tests/browser/test_admin_key_batch_209.py -m playwright
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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
PLAN_FORM = 'form[action="/admin/key-batch/plan"]'
APPLY_FORM = 'form[action="/admin/key-batch/apply"]'
SCREENSHOT_DIR = Path("/tmp/slaif209")

N_ACTIVE = 105
N_SUSPENDED = 2
N_REVOKED = 1
N_COHORT_KEYS = N_ACTIVE + N_SUSPENDED + N_REVOKED

HAPPY_REASON = "209 browser batch cost cap for the seeded cohort"
NOJS_REASON = "209 no-js batch request cap for the seeded cohort"
HAPPY_COST = "5.00"
NOJS_REQUEST = "999"


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
# Seed (fixture data only: direct ORM inserts, synthetic material)
# ---------------------------------------------------------------------------


async def _seed_batchdata(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui209-{suffix}@example.org",
                    display_name="209 Batch GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"209 GUI Inst {suffix}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"209 GUI Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Batch",
                    surname="Seed",
                    email=f"owner-209-{suffix}@example.org",
                    institution_id=institution.id,
                )
                # Provider slugs are DB-unique: get-or-create so this module
                # coexists with other browser modules on a shared session DB.
                providers = ProviderConfigsRepository(session)
                if await providers.get_provider_config_by_provider("openai") is None:
                    await providers.create_provider_config(
                        provider="openai",
                        display_name="OpenAI (209 GUI)",
                        base_url="https://api.openai.test/v1",
                        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    )
                if (
                    await providers.get_provider_config_by_provider("openrouter")
                    is None
                ):
                    await providers.create_provider_config(
                        provider="openrouter",
                        display_name="OpenRouter (209 GUI)",
                        base_url="https://openrouter.test/v1",
                        api_key_env_var="OPENROUTER_API_KEY",
                    )
                key_ids: list[uuid.UUID] = []
                for index in range(N_COHORT_KEYS):
                    if index < N_ACTIVE:
                        status = "active"
                    elif index < N_ACTIVE + N_SUSPENDED:
                        status = "suspended"
                    else:
                        status = "revoked"
                    key = GatewayKey(
                        public_key_id=f"209gui-{suffix}-{index:03d}",
                        token_hash=f"209gui-hash-{suffix}-{index:03d}",
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        status=status,
                        valid_from=now - timedelta(days=1),
                        valid_until=now + timedelta(days=30),
                        request_limit_total=1000,
                        token_limit_total=5_000_000,
                        created_by_admin_user_id=admin.id,
                        revoked_at=now if status == "revoked" else None,
                    )
                    session.add(key)
                    await session.flush()
                    key_ids.append(key.id)
                return {
                    "admin_email": admin.email,
                    "admin_id": str(admin.id),
                    "cohort_id": str(cohort.id),
                    "owner_id": str(owner.id),
                    "key_ids": [str(k) for k in key_ids],
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


def _key_states(database_url: str, key_ids: list[str]) -> dict[str, tuple[Any, ...]]:

    async def _get(session):
        out: dict[str, tuple[Any, ...]] = {}
        for key_id in key_ids:
            key = await session.get(GatewayKey, uuid.UUID(key_id))
            assert key is not None
            out[key_id] = (
                key.status,
                key.cost_limit_eur,
                key.token_limit_total,
                key.request_limit_total,
                key.token_hash,
                key.public_key_id,
            )
        return out

    return _db(database_url, _get)


def _batch_audit_count(database_url: str, admin_id: str) -> int:

    async def _get(session):
        from sqlalchemy import func

        result = await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "update_key_configuration",
                AuditLog.admin_user_id == uuid.UUID(admin_id),
            )
        )
        return int(result.scalar_one())

    return _db(database_url, _get)


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def batch_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_batchdata(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    data["database_url"] = owned_pg_url
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(batch_env) -> Iterator[object]:
    """Depends on ``batch_env`` on purpose: the Playwright sync session
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


def _screenshot(page: object, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _screenshot_element(page: object, selector: str, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    locator = page.locator(selector)  # type: ignore[attr-defined]
    locator.first.scroll_into_view_if_needed()  # type: ignore[attr-defined]
    locator.first.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _flat(page: object) -> str:
    return re.sub(r"\s+", " ", page.content())  # type: ignore[attr-defined]


def _form_data(page: object) -> dict[str, str]:
    """The live form serialization - exactly what a submission carries
    (disabled controls are absent)."""
    return page.evaluate(  # type: ignore[attr-defined]
        """() => Object.fromEntries(
             new FormData(document.querySelector('form[action="/admin/key-batch/plan"]'))
               .entries())"""
    )


def _rc(page: object, input_name: str) -> object:
    return page.locator(  # type: ignore[attr-defined]
        f'[data-rc][data-input-name="{input_name}"]'
    ).first


def _hidden_value(page: object, input_name: str) -> str:
    return page.input_value(  # type: ignore[attr-defined]
        f'[data-rc][data-input-name="{input_name}"] .rc-value'
    )


def _type_chip(page: object, input_name: str, value: str) -> None:
    """Drive the record-choice multi control like an operator: focus the
    entry field, type the value, commit with Enter."""
    entry = _rc(page, input_name).locator(".rc-input")
    entry.click()
    page.keyboard.type(value)  # type: ignore[attr-defined]
    page.keyboard.press("Enter")  # type: ignore[attr-defined]


def _assert_no_key_material(page: object, env: dict[str, Any]) -> None:
    """Synthetic token hashes must never appear on a rendered page.
    Booleans only - a failure never echoes the value."""
    marker = "209gui-hash"
    present = marker in page.content()  # type: ignore[attr-defined]
    assert present is False, "key material marker present on page"


# ---------------------------------------------------------------------------
# 1) Entry + safe initial disabled states (real JS) + visuals
# ---------------------------------------------------------------------------


def test_entry_and_form_safe_initial_states(chromium, batch_env) -> None:
    env = batch_env
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)

        # Entry point from the key list.
        page.goto("/admin/keys")  # type: ignore[attr-defined]
        link = page.locator('a[href="/admin/key-batch"]').first
        assert link.count() == 1
        _screenshot_element(page, "header:has(a[href='/admin/key-batch'])", "209-entry.png")
        link.click()
        page.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]

        flat = _flat(page)
        assert "Change Existing Keys" in flat
        assert "Selection And Status Scope" in flat
        assert "Input Mode" in flat
        assert "Policy Changes (guided)" in flat

        # Real JS initial composed sync (record-choices adopted the list
        # controls before DOMContentLoaded; key-batch re-derived every
        # state): guided + cohort + all-unchanged defaults.
        states = page.evaluate(  # type: ignore[attr-defined]
            """() => ({
                advanced: document.querySelector('[data-batch-advanced] textarea').disabled,
                cost_value: document.querySelector('input[name="cost_value"]').disabled,
                request_value: document.querySelector('input[name="request_value"]').disabled,
                cohort_enabled: !document.querySelector('[data-batch-cohort-control] .rc-input').disabled,
                keys_disabled: document.querySelector('[data-batch-keys-control] .rc-input').disabled,
                providers_hidden_disabled:
                    Array.from(document.querySelectorAll('[data-rc][data-input-name="providers_value"] .rc-value'))
                        .every((el) => el.disabled),
                providers_entry_disabled:
                    document.querySelector('[data-rc][data-input-name="providers_value"] .rc-input').disabled,
                lazy_disabled:
                    Array.from(document.querySelectorAll('[data-batch-lazy-wait] input'))
                        .every((el) => el.disabled),
                burn_disabled:
                    Array.from(document.querySelectorAll('[data-batch-live-burn] input'))
                        .every((el) => el.disabled),
                status_active: document.querySelector('input[name="status_active"]').checked,
            })"""
        )
        assert states["advanced"] is True, "advanced doc must be inactive in guided mode"
        assert states["cost_value"] is True
        assert states["request_value"] is True
        assert states["cohort_enabled"] is True
        assert states["keys_disabled"] is True
        assert states["providers_hidden_disabled"] is True
        assert states["providers_entry_disabled"] is True
        assert states["lazy_disabled"] is True
        assert states["burn_disabled"] is True
        assert states["status_active"] is True

        _assert_no_key_material(page, env)
        _screenshot_element(
            page, "section[aria-labelledby='batch-selection-heading']", "209-form-selection.png"
        )
        _screenshot_element(
            page, "section[aria-labelledby='batch-policy-heading']", "209-form-policy.png"
        )
        _screenshot(page, "209-form-full.png")

        # Narrow (480px) viewport: the guided policy section stays usable.
        narrow = chromium.new_context(  # type: ignore[attr-defined]
            base_url=env["base_url"], viewport={"width": 480, "height": 900}
        )
        try:
            npage = narrow.new_page()
            _login(npage, env)
            npage.goto("/admin/key-batch")  # type: ignore[attr-defined]
            npage.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]
            _screenshot_element(
                npage, "section[aria-labelledby='batch-policy-heading']", "209-form-policy-narrow.png"
            )
        finally:
            narrow.close()


# ---------------------------------------------------------------------------
# 2) Populated control-transition regressions (real JS, no submission)
# ---------------------------------------------------------------------------


def test_js_transitions_populated_roundtrip(chromium, batch_env) -> None:
    env = batch_env
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/key-batch")  # type: ignore[attr-defined]
        page.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]

        # (i) allow-list value must not ride along with unrestricted.
        page.select_option("select[name='providers_mode']", "allow_list")  # type: ignore[attr-defined]
        _type_chip(page, "providers_value", "openai")
        data = _form_data(page)
        assert data.get("providers_value") == "openai"
        page.select_option("select[name='providers_mode']", "unrestricted")  # type: ignore[attr-defined]
        data = _form_data(page)
        assert data.get("providers_mode") == "unrestricted"
        assert "providers_value" not in data, "stale allow-list value submitted"

        # (ii) value->clear plus the populated guided<->advanced round
        # trip: the round trip must not re-enable a cleared value, and
        # the still-unrestricted providers control stays value-free.
        page.select_option("select[name='request_action']", "set")  # type: ignore[attr-defined]
        page.fill("input[name='request_value']", "500")  # type: ignore[attr-defined]
        page.select_option("select[name='request_action']", "clear")  # type: ignore[attr-defined]
        page.check("input[value='advanced']")  # type: ignore[attr-defined]
        page.check("input[value='guided']")  # type: ignore[attr-defined]
        data = _form_data(page)
        assert data.get("request_action") == "clear"
        assert "request_value" not in data, "cleared value resubmitted after round trip"
        assert data.get("providers_mode") == "unrestricted"
        assert "providers_value" not in data

        # (iii) keys<->cohort scope change while advanced: the selection
        # scope is independent of the policy source and must follow the
        # checked kind even after an advanced excursion.
        page.check("input[value='keys']")  # type: ignore[attr-defined]
        _type_chip(page, "key_ids", env["key_ids"][0])
        data = _form_data(page)
        assert env["key_ids"][0] in (data.get("key_ids") or "")
        page.check("input[value='advanced']")  # type: ignore[attr-defined]
        page.check("input[value='cohort']")  # type: ignore[attr-defined]
        states = page.evaluate(  # type: ignore[attr-defined]
            """() => ({
                cohort_enabled: !document.querySelector('[data-batch-cohort-control] .rc-input').disabled,
                keys_disabled: document.querySelector('[data-batch-keys-control] .rc-input').disabled,
            })"""
        )
        assert states["cohort_enabled"] is True, "cohort control stuck disabled"
        assert states["keys_disabled"] is True, "keys control stuck enabled"
        data = _form_data(page)
        assert data.get("selection_kind") == "cohort"
        assert "key_ids" not in data, "stale key list submitted with cohort scope"

        # (iv) inactive chip removal: record-choices rebuilds its managed
        # hidden field(s) ENABLED on every write; the composed sync must
        # re-disable them so the remaining value cannot resubmit while
        # the mode is unrestricted. Step (iii) left the form in advanced
        # mode (where every guided policy control is correctly disabled):
        # explicitly return to guided first.
        page.check("input[value='guided']")  # type: ignore[attr-defined]
        page.select_option("select[name='providers_mode']", "allow_list")  # type: ignore[attr-defined]
        _type_chip(page, "providers_value", "openrouter")
        data = _form_data(page)
        assert set(data.get("providers_value", "").split("\n")) == {"openai", "openrouter"}
        page.select_option("select[name='providers_mode']", "unrestricted")  # type: ignore[attr-defined]
        page.locator('[data-rc][data-input-name="providers_value"] .rc-chip-remove').first.click()  # type: ignore[attr-defined]
        states = page.evaluate(  # type: ignore[attr-defined]
            """() => Array.from(
                document.querySelectorAll('[data-rc][data-input-name="providers_value"] .rc-value')
            ).every((el) => el.disabled)"""
        )
        assert states is True, "rebuilt hidden field left enabled while inactive"
        data = _form_data(page)
        assert data.get("providers_mode") == "unrestricted"
        assert "providers_value" not in data, (
            "remaining chip resubmitted after inactive removal"
        )


# ---------------------------------------------------------------------------
# 3) >100 multi-key selection with older search (real JS, no apply)
# ---------------------------------------------------------------------------


def test_multikey_over_100_selection_older_search(chromium, batch_env) -> None:
    env = batch_env
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/key-batch")  # type: ignore[attr-defined]
        page.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]

        page.check("input[value='keys']")  # type: ignore[attr-defined]
        initial_raw = page.get_attribute(  # type: ignore[attr-defined]
            '[data-rc][data-input-name="key_ids"]', "data-initial-options"
        )
        initial_ids = {entry["id"] for entry in json.loads(initial_raw)}
        assert len(initial_ids) == 100
        # A seeded key that is NOT in the initial latest-100 batch: the
        # older-search target.
        older = next(k for k in env["key_ids"] if k not in initial_ids)

        lookups: list[str] = []
        page.on(  # type: ignore[attr-defined]
            "request", lambda request: lookups.append(request.url)
            if "/admin/record-choices" in request.url
            else None
        )

        # Select ALL 100 initial-batch options (real menu interactions).
        # The multi control has no rc-open button: focusing the entry
        # field opens the menu. toggleItem keeps the options order
        # stable, so each DISTINCT index is one distinct option -
        # clicking the first option repeatedly would only toggle it.
        rc = _rc(page, "key_ids")
        rc.locator(".rc-input").click()
        rc.locator(".rc-list").wait_for(state="visible")
        for index in range(100):
            rc.locator("li.rc-option").nth(index).click(timeout=5000)
        assert rc.locator(".rc-chip").count() == 100

        # Older search: the typed query must NOT send selected-hydration
        # params (they would consume the result slots and evict the
        # older match), and the older key must be visible/clickable.
        entry = rc.locator(".rc-input")
        entry.click()
        page.keyboard.type(older)  # type: ignore[attr-defined]
        older_option = rc.locator(f"li.rc-option:has-text('{older}')")
        older_option.wait_for(state="visible", timeout=15000)
        older_option.click(timeout=5000)

        typed = [u for u in lookups if "q=" in u and older in u]
        assert typed, "no older-search lookup was issued"
        evicted = [u for u in typed if "selected" in u]
        assert not evicted, "typed query sent selected-hydration params"

        # The FULL selection (100 initial + 1 older) is intact in the
        # managed hidden field and is what the form submits.
        assert rc.locator(".rc-chip").count() == 101
        selected = set((_hidden_value(page, "key_ids")).split("\n"))
        assert selected == initial_ids | {older}, "full selection not preserved"

        # All three statuses so every one of the 101 keys is selected,
        # then submit the plan (read-only preview: nothing is applied).
        page.check("input[name='status_suspended']")  # type: ignore[attr-defined]
        page.check("input[name='status_revoked']")  # type: ignore[attr-defined]
        page.select_option("select[name='cost_action']", "set")  # type: ignore[attr-defined]
        page.fill("input[name='cost_value']", "2.50")  # type: ignore[attr-defined]
        page.click(f"{PLAN_FORM} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="batch_review_intent"]', state="attached"
        )
        flat = _flat(page)
        assert "101 selected" in flat, "full selection was not submitted"
        assert older in flat, "older-selected key truncated from review"
        _assert_no_key_material(page, env)


# ---------------------------------------------------------------------------
# 4) Keyboard happy flow: cohort plan -> review -> apply -> persisted DB
# ---------------------------------------------------------------------------


def test_keyboard_happy_flow_cohort_plan_apply(chromium, batch_env) -> None:
    env = batch_env
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/key-batch")  # type: ignore[attr-defined]
        page.wait_for_selector(PLAN_FORM)  # type: ignore[attr-defined]

        # Pick the one seeded cohort with the COMBOBOX KEYBOARD only (no
        # mouse on an option): focus the entry field, ArrowDown opens the
        # menu (for a known-only picker the focus lands on the menu's
        # search field), the next ArrowDown highlights the first option,
        # Enter selects it.
        cohort_rc = _rc(page, "cohort_id")
        cohort_rc.locator(".rc-input").focus()
        page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
        cohort_rc.locator(".rc-menu").wait_for(state="visible", timeout=15000)
        page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        assert _hidden_value(page, "cohort_id") == env["cohort_id"]

        page.select_option("select[name='cost_action']", "set")  # type: ignore[attr-defined]
        page.fill("input[name='cost_value']", HAPPY_COST)  # type: ignore[attr-defined]
        page.click(f"{PLAN_FORM} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="batch_review_intent"]', state="attached"
        )

        flat = _flat(page)
        assert "105 selected" in flat
        # Field-scoped readable rendering of the per-key change row: raw
        # input 5.00 renders through the common formatter as 5 (the exact
        # DB oracle stays Decimal). Assert the VISIBLE TEXT parts - the
        # serialized page decodes the &rarr; entity to the arrow, so the
        # entity itself must not be matched.
        change_li = page.locator("li:has-text('Cost limit (EUR)')").first  # type: ignore[attr-defined]
        change_text = change_li.inner_text()  # type: ignore[attr-defined]
        assert "Cost limit (EUR)" in change_text
        assert "Unlimited (null)" in change_text
        assert "\u2192" in change_text, "arrow missing from change row"
        assert change_text.rstrip().endswith("\u2192 5"), (
            "formatted 5 missing from the cost change row"
        )
        _assert_no_key_material(page, env)
        _screenshot_element(
            page, "section[aria-labelledby='batch-review-plan-heading']", "209-review.png"
        )

        # Native narrow (390px) review: the wrapped per-key table and the
        # raw plan JSON disclosure must stay INSIDE the viewport (no
        # document overflow), and the apply control must remain reachable.
        page.set_viewport_size({"width": 390, "height": 900})  # type: ignore[attr-defined]
        overflow = page.evaluate(  # type: ignore[attr-defined]
            "() => document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        assert overflow <= 0, "review document overflows the 390px viewport"
        _screenshot_element(
            page,
            "section[aria-labelledby='batch-review-keys-heading']",
            "209-review-narrow.png",
        )
        apply_button = page.locator(f"{APPLY_FORM} button[type='submit']")  # type: ignore[attr-defined]
        apply_button.scroll_into_view_if_needed()  # type: ignore[attr-defined]
        assert apply_button.is_visible(), "apply control not reachable at 390px"
        page.set_viewport_size({"width": 1280, "height": 720})  # type: ignore[attr-defined]

        # Keyboard apply: confirm + reason, then Enter (no mouse click on
        # the submit button).
        token_value = page.get_attribute(  # type: ignore[attr-defined]
            'input[name="batch_review_intent"]', "value"
        )
        assert token_value
        # Keyboard-only confirm + reason + submit (focus/Space/type/Enter;
        # no mouse click on the checkbox or the submit button).
        confirm_box = page.locator("input[name='confirm_apply']")  # type: ignore[attr-defined]
        confirm_box.focus()  # type: ignore[attr-defined]
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        reason_input = page.locator("input[name='reason']")  # type: ignore[attr-defined]
        reason_input.focus()  # type: ignore[attr-defined]
        page.keyboard.type(HAPPY_REASON)  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        page.wait_for_selector("#batch-result-heading")  # type: ignore[attr-defined]


        flat = _flat(page)
        assert "applied" in flat
        assert HAPPY_REASON in flat
        # The signed review state is not retained on the result page.
        retained = token_value in page.content()  # type: ignore[attr-defined]
        assert retained is False, "review token retained on result page"
        _assert_no_key_material(page, env)
        _screenshot(page, "209-result.png")

        # Independent persisted-DB oracles.
        db = env["database_url"]
        states = _key_states(db, env["key_ids"])
        for index, key_id in enumerate(env["key_ids"]):
            status, cost, token, request, token_hash, public_key_id = states[key_id]
            if index < N_ACTIVE:
                assert status == "active"
                assert Decimal(str(cost)) == Decimal(HAPPY_COST), "cost cap not persisted"
                assert token == 5_000_000, "unreviewed token limit moved"
                assert request == 1000, "unreviewed request limit moved"
            else:
                # Excluded by status: untouched.
                assert cost is None, "excluded key mutated"
                assert request == 1000
                assert token == 5_000_000


def test_keyboard_happy_flow_audits(chromium, batch_env) -> None:
    """Audit oracle for test 4 (separate function: the DB worker thread
    must not run while the browser context owns the main loop mid-flow)."""
    env = batch_env
    count = _batch_audit_count(env["database_url"], env["admin_id"])
    assert count == N_ACTIVE, "one update_key_configuration audit per changed key"


# ---------------------------------------------------------------------------
# 5) No-JS fallback: native fields, same server law
# ---------------------------------------------------------------------------


def test_nojs_fallback_flow(chromium, batch_env) -> None:
    env = batch_env
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], java_script_enabled=False
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/key-batch")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action='/admin/key-batch/plan'] textarea[name='key_ids']")  # type: ignore[attr-defined]

        # Without JavaScript the pickers are plain named fields: the
        # cohort picker is a text input, the key picker a textarea.
        assert page.locator("input[name='cohort_id']").count() == 1  # type: ignore[attr-defined]
        assert page.locator("textarea[name='key_ids']").count() == 1  # type: ignore[attr-defined]
        page.fill("input[name='cohort_id']", env["cohort_id"])  # type: ignore[attr-defined]
        page.select_option("select[name='request_action']", "set")  # type: ignore[attr-defined]
        page.fill("input[name='request_value']", NOJS_REQUEST)  # type: ignore[attr-defined]
        page.click(f"{PLAN_FORM} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            'input[name="batch_review_intent"]', state="attached"
        )

        flat = _flat(page)
        assert "105 selected" in flat
        _assert_no_key_material(page, env)

        page.check("input[name='confirm_apply']")  # type: ignore[attr-defined]
        page.fill("input[name='reason']", NOJS_REASON)  # type: ignore[attr-defined]
        page.click(f"{APPLY_FORM} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector("#batch-result-heading")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "applied" in flat
        _assert_no_key_material(page, env)

        # Independent persisted-DB oracles.
        db = env["database_url"]
        states = _key_states(db, env["key_ids"])
        for index, key_id in enumerate(env["key_ids"]):
            status, cost, token, request, token_hash, public_key_id = states[key_id]
            if index < N_ACTIVE:
                assert request == int(NOJS_REQUEST), "request cap not persisted"
                assert Decimal(str(cost)) == Decimal(HAPPY_COST), (
                    "earlier reviewed cost cap must be preserved"
                )
            else:
                assert request == 1000, "excluded key mutated"


def test_nojs_fallback_audits(chromium, batch_env) -> None:
    """Audit oracle for the no-JS flow: 105 (happy) + 105 (no-JS)."""
    env = batch_env
    count = _batch_audit_count(env["database_url"], env["admin_id"])
    assert count == 2 * N_ACTIVE
