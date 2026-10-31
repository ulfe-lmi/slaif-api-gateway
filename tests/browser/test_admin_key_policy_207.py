"""207-a GUI key policy: real Chromium on the owned PostgreSQL.

Actual uvicorn app, real stylesheet, and real HTTP admin pages against
the already-qualified owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL fixture. Exercises the G01-G03 acceptance workflow end to
end: guided create with the provider tri-state (allow-all / selected /
deny-all, JS mutual exclusion included), strict document-mode create
persisting the canonical version-1 policy, existing-key policy edits with
empty-selection fail-closed and disabled-provider preservation, the
per-member rate editor (set 1/10s + concurrency 1, zero and no-op
refusals, clear-to-inherit with sibling preservation), the versioned
configuration download (allowlisted, private no-store attachment) and
partial update (plus unknown-field, confirmation, and reason refusals
with a synthetic credential-shaped canary that is never echoed), the
configuration-only explain-model-access report (resolved / blocked /
unknown-model, read-only), and the no-JS server form fallback (owner
typed as plain text, provider list typed in the manual textarea,
fail-closed policy submit, legacy lazy-throttling controls still
usable) on a narrow desktop viewport.

Safety: only synthetic fixture values are read; session and CSRF values
are used transiently for login and never logged or screenshotted.
Screenshots (synthetic data only, no key/session/secret cells) go under
/tmp/slaif207/.

Run:  python -m pytest tests/browser/test_admin_key_policy_207.py -m playwright
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
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey, OneTimeSecret, ProviderConfig
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# Reuse the already-qualified owned, labeled, loopback-bound, tmpfs-backed
# PostgreSQL fixture (never an ambient TEST_DATABASE_URL fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

# Re-export the qualified fixture under the expected fixture name.
owned_pg_url = _owned_pg_url_fixture

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif207")

# A synthetic credential-shaped canary used ONLY as submitted input that a
# rejected document may contain; assertions are booleans over rendered
# output (the value itself is synthetic, not a live secret).
CONFIG_CANARY = "sk-slaif-canary-" + "7" * 40


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
# Seed
# ---------------------------------------------------------------------------


def _seed_key(
    session,
    *,
    admin_id: uuid.UUID,
    owner_id: uuid.UUID,
    public_key_id: str,
    token_hash: str,
    key_hint: str,
    providers: list[str],
    now: datetime,
    rate_requests: int | None = None,
) -> GatewayKey:
    key = GatewayKeysRepository(session)
    created = key.create_gateway_key_record(
        public_key_id=public_key_id,
        token_hash=token_hash,
        owner_id=owner_id,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        key_hint=key_hint,
        rate_limit_requests_per_minute=rate_requests,
        allow_all_models=True,
        allow_all_endpoints=True,
        created_by_admin_user_id=admin_id,
        metadata_json={"allowed_providers": providers},
    )
    return created


async def _seed_keypolicy_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui207-{suffix}@example.org",
                    display_name="207 GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"207 GUI Inst {suffix}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"207 GUI Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Browser",
                    surname="Twenty",
                    email=f"owner-207-{suffix}@example.org",
                    institution_id=institution.id,
                )
                providers = ProviderConfigsRepository(session)
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI (207 GUI)",
                    base_url="https://api.openai.test/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                )
                await providers.create_provider_config(
                    provider="openrouter",
                    display_name="OpenRouter (207 GUI)",
                    base_url="https://openrouter.test/v1",
                    api_key_env_var="OPENROUTER_API_KEY",
                )
                routes = ModelRoutesRepository(session)
                await routes.create_model_route(
                    requested_model="gpt-test",
                    provider="openai",
                    upstream_model="gpt-test",
                    endpoint="/v1/chat/completions",
                )
                await routes.create_model_route(
                    requested_model="gpt-other",
                    provider="openrouter",
                    upstream_model="gpt-other",
                    endpoint="/v1/chat/completions",
                )

                def _one_time_secret(key: GatewayKey) -> None:
                    session.add(
                        OneTimeSecret(
                            purpose="gateway_key_email",
                            owner_id=owner.id,
                            gateway_key_id=key.id,
                            encrypted_payload="c2VlZC1vbmx5LXBsYWNlaG9sZGVy",
                            nonce="bm9uY2UtcGxhY2Vob2xkZXI",
                            encryption_key_version=1,
                            expires_at=now + timedelta(days=1),
                            status="pending",
                        )
                    )

                # Existing key for the edit workflows: an allow-list with a
                # DISABLED-provider preservation angle and a stored rate.
                legacy = await _seed_key(
                    session,
                    admin_id=admin.id,
                    owner_id=owner.id,
                    public_key_id=f"207gui-legacy-{suffix}",
                    token_hash=f"token_hash_207gui_legacy_{suffix}",
                    key_hint=f"sk-slaif-207l{suffix[:4]}",
                    providers=["openrouter"],
                    now=now,
                    rate_requests=500,
                )
                # Existing key with an openai allow-list for explain.
                explain = await _seed_key(
                    session,
                    admin_id=admin.id,
                    owner_id=owner.id,
                    public_key_id=f"207gui-explain-{suffix}",
                    token_hash=f"token_hash_207gui_explain_{suffix}",
                    key_hint=f"sk-slaif-207e{suffix[:4]}",
                    providers=["openai"],
                    now=now,
                )
                _one_time_secret(legacy)
                _one_time_secret(explain)
                await session.flush()
                return {
                    "admin_email": admin.email,
                    "suffix": suffix,
                    "owner_id": str(owner.id),
                    "cohort_id": str(cohort.id),
                    "key_legacy": str(legacy.id),
                    "key_explain": str(explain.id),
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Direct-DB read helpers (persistence oracles, run outside the browser)
# ---------------------------------------------------------------------------


def _db(database_url: str, coro_factory):
    """Run one async DB oracle in a worker thread.

    The Playwright sync API owns an asyncio loop on the main thread, so
    ``asyncio.run`` must execute elsewhere; a dedicated thread with its
    own loop and engine keeps the oracles independent of the browser.
    """
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


def _fetch_key_state(database_url: str, key_id: str) -> dict[str, Any]:
    key_uuid = uuid.UUID(key_id)

    async def _get(session):
        key = await session.get(GatewayKey, key_uuid)
        assert key is not None
        metadata = key.metadata_json if isinstance(key.metadata_json, dict) else {}
        rate_policy = metadata.get("rate_limit_policy")
        rate_policy = rate_policy if isinstance(rate_policy, dict) else {}
        return {
            "providers": metadata.get("allowed_providers"),
            "models": (bool(key.allow_all_models), list(key.allowed_models or [])),
            "endpoints": (bool(key.allow_all_endpoints), list(key.allowed_endpoints or [])),
            "cost_limit": (
                str(key.cost_limit_eur) if key.cost_limit_eur is not None else None
            ),
            "rate_requests": key.rate_limit_requests_per_minute,
            "rate_tokens": key.rate_limit_tokens_per_minute,
            "concurrency": key.max_concurrent_requests,
            "window": rate_policy.get("window_seconds"),
            "lazy": metadata.get("lazy_throttling_policy"),
            "usage": (
                key.requests_used_total,
                key.tokens_used_total,
                key.cost_used_eur,
            ),
            "reservations": (
                key.cost_reserved_eur,
                key.tokens_reserved_total,
                key.requests_reserved_total,
            ),
            "owner_id": str(key.owner_id),
            "token_hash": key.token_hash,
            "valid_until": key.valid_until,
        }

    return _db(database_url, _get)


def _latest_key_id(database_url: str, owner_id: str) -> str:
    owner_uuid = uuid.UUID(owner_id)

    async def _get(session):
        result = await session.execute(
            select(GatewayKey)
            .where(GatewayKey.owner_id == owner_uuid)
            .order_by(GatewayKey.created_at.desc(), GatewayKey.id.desc())
            .limit(1)
        )
        key = result.scalar_one()
        return str(key.id)

    return _db(database_url, _get)


def _audit_count(database_url: str) -> int:
    async def _get(session):
        result = await session.execute(select(func.count()).select_from(AuditLog))
        return int(result.scalar_one())

    return _db(database_url, _get)


def _last_audit_note(database_url: str, action: str) -> str | None:
    async def _get(session):
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row.note if row is not None else None

    return _db(database_url, _get)


def _set_provider_enabled(database_url: str, provider: str, enabled: bool) -> None:
    async def _set(session):
        async with session.begin():
            result = await session.execute(
                select(ProviderConfig).where(ProviderConfig.provider == provider)
            )
            config = result.scalar_one()
            config.enabled = enabled

    _db(database_url, _set)


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def keypolicy_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_keypolicy_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    data["database_url"] = owned_pg_url
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(keypolicy_env) -> Iterator[object]:
    """Depends on ``keypolicy_env`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PostgreSQL readiness,
    seeding, and the uvicorn app must complete BEFORE it starts (and the
    browser closes before DB teardown)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


def _login(page: object, env: dict[str, Any]) -> None:
    page.goto("/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _screenshot(page: object, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _screenshot_element(page: object, selector: str, name: str) -> None:
    """Focused element capture: whole-page screenshots of these busy
    pages showed only the page-top identity instead of the new controls."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    locator = page.locator(selector)  # type: ignore[attr-defined]
    locator.first.scroll_into_view_if_needed()  # type: ignore[attr-defined]
    locator.first.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _error_snippet(html: str) -> str:
    """Fixed-label error extraction: only the flash message text is kept."""
    match = re.search(
        r'<div class="admin-flash admin-flash-error"[^>]*>\s*<p>([^<]*)</p>', html
    )
    return match.group(1) if match else "(no admin-flash-error found)"


def _flat(page: object) -> str:
    """Whitespace-normalized page source for multi-line template asserts."""
    return re.sub(r"\s+", " ", page.content())  # type: ignore[attr-defined]


def _select_owner_js(page: object, owner_id: str) -> None:
    """Drive the existing record-choice combobox (latest-100 dropdown)."""
    owner_field = page.locator("label.rc-field", has_text="Owner")  # type: ignore[attr-defined]
    owner_field.first.locator("button.rc-open").click()
    option = owner_field.first.locator(".rc-list li").first
    option.wait_for(state="visible", timeout=15000)  # type: ignore[attr-defined]
    option.click()
    assert page.locator('input[name="owner_id"]').input_value() == owner_id  # type: ignore[attr-defined]


def _submit_form(page: object, form_locator: object, suffix: str) -> int:
    """POST one admin form; return the HTTP status of the POST response."""
    with page.expect_response(  # type: ignore[attr-defined]
        lambda r: r.request.method == "POST" and r.url.endswith(suffix)
    ) as info:
        form_locator.locator("button[type='submit']").click()  # type: ignore[attr-defined]
    return int(info.value.status)


# ---------------------------------------------------------------------------
# 1) Create: field help, tri-state JS, three provider modes persisted
# ---------------------------------------------------------------------------


def test_create_form_help_and_provider_tri_state(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    suffix = env["suffix"]
    owner_id = env["owner_id"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]

        # --- req 5: field-specific help wired through aria-describedby
        for help_id in (
            "create-validity-help",
            "create-limits-help",
            "create-policy-source-help",
            "create-reason-help",
            "create-rate-limit-help",
            "create-policy-provider-mode-help",
        ):
            help_el = page.locator(f"#{help_id}")
            assert help_el.count() == 1, help_id
            assert help_el.first.inner_text().strip() != "", help_id
        assert (
            page.locator('input[name="valid_from"]').get_attribute("aria-describedby")
            == "create-validity-help"
        )
        assert (
            page.locator('input[name="cost_limit_eur"]').get_attribute("aria-describedby")
            == "create-limits-help"
        )
        assert (
            page.locator('input[name="rate_limit_requests_per_minute"]')
            .get_attribute("aria-describedby")
            == "create-rate-limit-help"
        )
        assert (
            page.locator('input[name="reason"]').get_attribute("aria-describedby")
            == "create-reason-help"
        )
        for mode in ("allow_all_providers", "provider_deny_all"):
            assert (
                page.locator(f'input[name="{mode}"]').get_attribute("aria-describedby")
                == "create-policy-provider-mode-help"
            )
        # Editable controls are wrapped in (or labelled by) a <label>, so
        # keyboard focus announces the field name.
        assert (
            page.locator("label:has(input[name='rate_limit_requests_per_minute'])").count()
            == 1
        )

        # --- policy source: guided keeps its explicit allow-all default;
        #     document mode resets the guided policy controls (JS law)
        assert page.locator('input[name="allow_all_providers"]').is_checked()
        assert page.locator('select[name="policy_source"]').input_value() == "guided"
        page.select_option('select[name="policy_source"]', "configuration")  # type: ignore[attr-defined]
        assert not page.locator('input[name="allow_all_providers"]').is_checked()
        assert page.locator('[data-create-configuration-document]').is_visible()
        page.select_option('select[name="policy_source"]', "guided")  # type: ignore[attr-defined]
        assert page.locator('[data-create-configuration-document]').is_hidden()

        # --- tri-state mutual exclusion (JS behaviour)
        allow_all = page.locator('input[name="allow_all_providers"]')
        deny_all = page.locator('input[name="provider_deny_all"]')
        group = page.locator('[data-policy-selector-group="providers"]')
        allow_all.check()
        assert "policy-selector-disabled" in (group.get_attribute("class") or "")
        deny_all.check()  # JS unchecks the other mode
        assert deny_all.is_checked()
        assert not allow_all.is_checked()
        allow_all.check()  # and back
        assert allow_all.is_checked()
        assert not deny_all.is_checked()
        allow_all.uncheck()

        # --- key A: unrestricted (allow all)
        _select_owner_js(page, owner_id)
        page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]
        page.check('input[name="allow_all_providers"]')  # type: ignore[attr-defined]
        page.check('input[name="allow_all_models"]')  # type: ignore[attr-defined]
        page.check('input[name="allow_all_endpoints"]')  # type: ignore[attr-defined]
        page.fill('input[name="reason"]', f"207 browser unrestricted {suffix}")  # type: ignore[attr-defined]
        # Focused capture of the NEW create controls (policy source +
        # provider selector), not the page-top identity.
        _screenshot_element(
            page,
            'section.action-panel[aria-labelledby="create-policy-source-heading"]',
            "key-create-policy-source.png",
        )
        _screenshot_element(
            page,
            'section.action-panel[aria-labelledby="create-policy-heading"]',
            "key-create-provider-controls.png",
        )
        status = _submit_form(page, page.locator("form[action='/admin/keys/create']"), "/admin/keys/create")
        assert status == 200  # email mode "none" renders the result page
        page.wait_for_url("**/admin/keys/create")  # type: ignore[attr-defined]
        env["key_unrestricted"] = _latest_key_id(env["database_url"], owner_id)
        page.goto(f"/admin/keys/{env['key_unrestricted']}")  # type: ignore[attr-defined]
        page.wait_for_selector("#key-effective-policy-heading")  # type: ignore[attr-defined]
        assert "Unrestricted (all enabled providers)" in page.content()
        assert page.locator('input[name="allow_all_providers"]').is_checked()
        assert not page.locator('input[name="provider_deny_all"]').is_checked()

        # --- key B: explicit openai allow-list via the selector buttons
        page.goto("/admin/keys/create")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _select_owner_js(page, owner_id)
        # The guided default is "allow all"; an allow-list key explicitly
        # leaves that mode off (the grid unlocks via the selector JS).
        page.uncheck('input[name="allow_all_providers"]')  # type: ignore[attr-defined]
        page.select_option("#create-policy-providers-available", "openai")  # type: ignore[attr-defined]
        page.click('button[data-policy-add="providers"]')  # type: ignore[attr-defined]
        assert (
            page.locator('textarea[name="allowed_providers"]').input_value() == "openai"
        )  # type: ignore[attr-defined]
        assert not page.locator('input[name="allow_all_providers"]').is_checked()
        assert not page.locator('input[name="provider_deny_all"]').is_checked()
        page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]
        page.check('input[name="allow_all_models"]')  # type: ignore[attr-defined]
        page.check('input[name="allow_all_endpoints"]')  # type: ignore[attr-defined]
        page.fill('input[name="reason"]', f"207 browser allow-list {suffix}")  # type: ignore[attr-defined]
        status = _submit_form(page, page.locator("form[action='/admin/keys/create']"), "/admin/keys/create")
        assert status == 200
        page.wait_for_url("**/admin/keys/create")  # type: ignore[attr-defined]
        env["key_openai"] = _latest_key_id(env["database_url"], owner_id)
        page.goto(f"/admin/keys/{env['key_openai']}")  # type: ignore[attr-defined]
        page.wait_for_selector("#key-effective-policy-heading")  # type: ignore[attr-defined]
        assert "Allow-list: openai" in page.content()
        _screenshot_element(
            page,
            'section.detail-section[aria-labelledby="key-effective-policy-heading"]',
            "key-detail-effective-policy.png",
        )

        # --- key C: deny-all (explicit, labelled)
        page.goto("/admin/keys/create")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _select_owner_js(page, owner_id)
        page.uncheck('input[name="allow_all_providers"]')  # type: ignore[attr-defined]
        page.check('input[name="provider_deny_all"]')  # type: ignore[attr-defined]
        page.check('input[name="allow_all_models"]')  # type: ignore[attr-defined]
        page.check('input[name="allow_all_endpoints"]')  # type: ignore[attr-defined]
        page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]
        page.fill('input[name="reason"]', f"207 browser deny-all {suffix}")  # type: ignore[attr-defined]
        status = _submit_form(page, page.locator("form[action='/admin/keys/create']"), "/admin/keys/create")
        assert status == 200
        page.wait_for_url("**/admin/keys/create")  # type: ignore[attr-defined]
        env["key_denyall"] = _latest_key_id(env["database_url"], owner_id)
        page.goto(f"/admin/keys/{env['key_denyall']}")  # type: ignore[attr-defined]
        page.wait_for_selector("#key-effective-policy-heading")  # type: ignore[attr-defined]
        assert "Deny all providers" in page.content()
        assert page.locator('input[name="provider_deny_all"]').is_checked()


# ---------------------------------------------------------------------------
# 1b) Document-mode create: strict version-1 document persists canonically
# ---------------------------------------------------------------------------


def test_create_document_mode_persists_canonical_policy(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    suffix = env["suffix"]
    owner_id = env["owner_id"]
    document = {
        "schema_version": 1,
        "allowed_models": ["gpt-test"],
        "allowed_endpoints": ["/v1/chat/completions"],
        "allowed_providers": ["openai"],
        "cost_limit_eur": "5.000000000",
        "rate_limit_policy": {"requests_per_minute": 3, "window_seconds": 15},
    }
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _select_owner_js(page, owner_id)
        page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]
        # Document mode: the guided policy checkboxes reset to "off" (JS
        # law) and the strict version-1 document becomes the SINGLE policy
        # source; identity fields stay guided.
        page.select_option('select[name="policy_source"]', "configuration")  # type: ignore[attr-defined]
        assert not page.locator('input[name="allow_all_providers"]').is_checked()
        assert not page.locator('input[name="allow_all_models"]').is_checked()
        assert not page.locator('input[name="allow_all_endpoints"]').is_checked()
        assert page.locator('[data-create-configuration-document]').is_visible()
        page.fill(  # type: ignore[attr-defined]
            'textarea[name="configuration_json"]', json.dumps(document)
        )
        page.fill('input[name="reason"]', f"207 browser document-mode {suffix}")  # type: ignore[attr-defined]
        _screenshot_element(
            page,
            'section.action-panel[aria-labelledby="create-policy-source-heading"]',
            "key-create-document-mode.png",
        )
        status = _submit_form(page, page.locator("form[action='/admin/keys/create']"), "/admin/keys/create")
        assert status == 200, "document-mode create failed: " + _error_snippet(page.content())
        page.wait_for_url("**/admin/keys/create")  # type: ignore[attr-defined]
        # The intentional one-time plaintext result is functional: the key
        # renders exactly once in the dedicated result panel. Booleans
        # only, so a regression cannot print the generated value.
        code = page.locator("section[aria-labelledby='created-plaintext-heading'] code")
        assert code.count() == 1
        key_text = code.first.inner_text().strip()  # type: ignore[attr-defined]
        # Opaque boolean first: a failed assertion must never print the
        # generated one-time value (fixed message only).
        one_time_result_ok = (
            key_text.startswith("sk-slaif-") and len(key_text) > len("sk-slaif-")
        )
        assert one_time_result_ok, (
            "one-time plaintext result panel did not render a gateway key"
        )
        key_id = _latest_key_id(env["database_url"], owner_id)
        env["key_document"] = key_id
        # Navigate away from the one-time result BEFORE any capture.
        page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
        page.wait_for_selector("#key-effective-policy-heading")  # type: ignore[attr-defined]
        assert "Allow-list: openai" in _flat(page)
        # Persisted canonical state (direct DB oracle).
        state = _fetch_key_state(env["database_url"], key_id)
        assert state["providers"] == ["openai"]
        assert state["models"] == (False, ["gpt-test"])
        assert state["endpoints"] == (False, ["/v1/chat/completions"])
        assert state["cost_limit"] == "5.000000000"
        assert state["rate_requests"] == 3
        assert state["window"] == 15
        assert state["concurrency"] is None
        assert state["rate_tokens"] is None
        # The canonical export reproduces the same document values.
        response = context.request.get(f"/admin/keys/{key_id}/configuration.json")  # type: ignore[attr-defined]
        assert response.ok
        exported = response.json()
        assert exported["allowed_models"] == ["gpt-test"]
        assert exported["allow_all_models"] is False
        assert exported["allowed_endpoints"] == ["/v1/chat/completions"]
        assert exported["allow_all_endpoints"] is False
        assert exported["allowed_providers"] == ["openai"]
        assert exported["cost_limit_eur"] == "5.000000000"
        assert exported["rate_limit_policy"] == {
            "requests_per_minute": 3,
            "window_seconds": 15,
        }
        # The provider tri-state remains intact after the document-mode
        # flow: selector mutual exclusion still works on the create form.
        page.goto("/admin/keys/create")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        allow_all = page.locator('input[name="allow_all_providers"]')
        deny_all = page.locator('input[name="provider_deny_all"]')
        allow_all.check()
        assert allow_all.is_checked()
        deny_all.check()
        assert deny_all.is_checked()
        assert not allow_all.is_checked()
        allow_all.check()
        assert allow_all.is_checked()
        assert not deny_all.is_checked()


# ---------------------------------------------------------------------------
# 2) Existing-key policy edit: fail-closed, preservation, positive edit
# ---------------------------------------------------------------------------


def test_policy_edit_fail_closed_and_preservation(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    key_id = env["key_legacy"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/policy']")  # type: ignore[attr-defined]

        assert "Allow-list: openrouter" in page.content()
        assert not page.locator('input[name="allow_all_providers"]').is_checked()
        assert not page.locator('input[name="provider_deny_all"]').is_checked()
        assert (
            page.locator('textarea[name="allowed_providers"]').input_value() == "openrouter"
        )  # type: ignore[attr-defined]

        # --- empty selection with no mode is refused (never broadens)
        page.locator("#detail-policy-providers-selected option").first.click()  # type: ignore[attr-defined]
        page.click('button[data-policy-remove="providers"]')  # type: ignore[attr-defined]
        assert page.locator('textarea[name="allowed_providers"]').input_value() == ""  # type: ignore[attr-defined]
        policy_form = page.locator("form[action$='/policy']")
        policy_form.locator('input[name="reason"]').fill("207 empty selection")  # type: ignore[attr-defined]
        status = _submit_form(page, policy_form, f"/admin/keys/{key_id}/policy")
        assert status == 400
        assert "an empty selection never grants unrestricted access" in page.content()
        # Stored state is untouched: the Effective Policy section still
        # projects the saved allow-list and the DB row is unchanged.
        assert "Allow-list: openrouter" in _flat(page)
        assert _fetch_key_state(env["database_url"], key_id)["providers"] == ["openrouter"]

        # --- a provider disabled AFTER the key stored it stays listed
        _set_provider_enabled(env["database_url"], "openrouter", False)
        try:
            # The 400 left the page at the POST URL; return to the detail.
            page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
            page.wait_for_selector("form[action$='/policy']")  # type: ignore[attr-defined]
            assert "openrouter | manual entry" in page.content()
            # Saving with the disabled provider stored round-trips it.
            policy_form = page.locator("form[action$='/policy']")
            policy_form.locator('input[name="reason"]').fill("207 round-trip disabled provider")  # type: ignore[attr-defined]
            status = _submit_form(page, policy_form, f"/admin/keys/{key_id}/policy")
            assert status == 303
            state = _fetch_key_state(env["database_url"], key_id)
            assert state["providers"] == ["openrouter"]
        finally:
            _set_provider_enabled(env["database_url"], "openrouter", True)

        # --- positive edit: add openai to the stored list
        page.reload()  # type: ignore[attr-defined]
        page.select_option("#detail-policy-providers-available", "openai")  # type: ignore[attr-defined]
        page.click('button[data-policy-add="providers"]')  # type: ignore[attr-defined]
        submitted = (
            page.locator('textarea[name="allowed_providers"]').input_value()  # type: ignore[attr-defined]
        )
        assert set(submitted.split("\n")) == {"openai", "openrouter"}
        policy_form = page.locator("form[action$='/policy']")
        policy_form.locator('input[name="reason"]').fill("207 add openai")  # type: ignore[attr-defined]
        status = _submit_form(page, policy_form, f"/admin/keys/{key_id}/policy")
        assert status == 303
        page.wait_for_url(f"**/admin/keys/{key_id}?message=*")  # type: ignore[attr-defined]
        assert "Allow-list: openai, openrouter" in page.content() or (
            "openai" in page.content() and "openrouter" in page.content()
        )
        state = _fetch_key_state(env["database_url"], key_id)
        assert set(state["providers"] or []) == {"openai", "openrouter"}


# ---------------------------------------------------------------------------
# 3) Rate editor: prefill, no-op/zero refusal, set 1/10s + concurrency 1,
#    clear-to-inherit with sibling preservation
# ---------------------------------------------------------------------------


def test_rate_editor_workflow(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    key_id = env["key_legacy"]
    before = _fetch_key_state(env["database_url"], key_id)
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/rate-limits']")  # type: ignore[attr-defined]

        form = page.locator("form[action$='/rate-limits']")
        # Prefill: the stored member shows its current configured value,
        # every action defaults to "unchanged".
        assert (
            form.locator('select[name="rate_action_requests_per_window"]').input_value()
            == "unchanged"
        )
        assert form.locator('input[name="rate_value_requests_per_window"]').input_value() == "500"
        for member in ("tokens_per_window", "concurrency", "window"):
            assert (
                form.locator(f'select[name="rate_action_{member}"]').input_value()
                == "unchanged"
            )
        # The help line is wired to every editor control.
        assert (
            form.locator('select[name="rate_action_window"]')
            .get_attribute("aria-describedby")
            == "key-rate-limits-help"
        )
        assert page.locator("#key-rate-limits-help").count() == 1
        assert page.locator("#key-rate-limits-help").inner_text().strip() != ""

        # --- no-op submit is refused
        form.locator('input[name="reason"]').fill("207 no change")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/rate-limits")
        assert status == 400
        assert "No rate-limit change requested. Set or clear at least one member." in page.content()

        # --- zero is never a value (fixed message, state unchanged)
        form = page.locator("form[action$='/rate-limits']")
        form.locator('select[name="rate_action_requests_per_window"]').select_option("set")  # type: ignore[attr-defined]
        form.locator('input[name="rate_value_requests_per_window"]').fill("0")  # type: ignore[attr-defined]
        form.locator('input[name="reason"]').fill("207 try zero")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/rate-limits")
        assert status == 400
        assert "Requests per window must be a positive whole number." in page.content()
        assert _fetch_key_state(env["database_url"], key_id)["rate_requests"] == 500

        # --- one request per 10 seconds + concurrency 1
        form = page.locator("form[action$='/rate-limits']")
        form.locator('select[name="rate_action_requests_per_window"]').select_option("set")  # type: ignore[attr-defined]
        form.locator('input[name="rate_value_requests_per_window"]').fill("1")  # type: ignore[attr-defined]
        form.locator('select[name="rate_action_window"]').select_option("set")  # type: ignore[attr-defined]
        form.locator('input[name="rate_value_window"]').fill("10")  # type: ignore[attr-defined]
        form.locator('select[name="rate_action_concurrency"]').select_option("set")  # type: ignore[attr-defined]
        form.locator('input[name="rate_value_concurrency"]').fill("1")  # type: ignore[attr-defined]
        form.locator('input[name="reason"]').fill("207 one per ten seconds")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/rate-limits")
        assert status == 303
        page.wait_for_url(f"**/admin/keys/{key_id}?message=*")  # type: ignore[attr-defined]
        assert "Gateway key operational rate limits updated." in page.content()

        body = _flat(page)
        assert "requests_per_window: configured 1 (source: key)" in body
        assert "concurrency: configured 1 (source: key)" in body
        assert "window_seconds: configured 10 (source: key)" in body
        assert "tokens_per_window: not limited by this member" in body
        assert "requests 1 / tokens inherited / concurrency 1 / window 10" in body
        _screenshot_element(
            page,
            'section.action-panel[aria-labelledby="key-rate-limits-heading"]',
            "key-detail-rate-editor.png",
        )

        after = _fetch_key_state(env["database_url"], key_id)
        assert after["rate_requests"] == 1
        assert after["concurrency"] == 1
        assert after["window"] == 10
        assert after["rate_tokens"] is None
        # Usage, reservations, identities, validity, and material untouched.
        assert after["usage"] == before["usage"]
        assert after["reservations"] == before["reservations"]
        assert after["owner_id"] == before["owner_id"]
        assert after["token_hash"] == before["token_hash"]
        assert after["valid_until"] == before["valid_until"]
        note = _last_audit_note(env["database_url"], "update_key_rate_limits")
        assert note is not None and "207 one per ten seconds" in note

        # --- clear requests: inherit the deployment; siblings preserved
        form = page.locator("form[action$='/rate-limits']")
        form.locator('select[name="rate_action_requests_per_window"]').select_option("clear")  # type: ignore[attr-defined]
        form.locator('input[name="reason"]').fill("207 clear requests")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/rate-limits")
        assert status == 303
        page.wait_for_url(f"**/admin/keys/{key_id}?message=*")  # type: ignore[attr-defined]
        body = _flat(page)
        assert "requests_per_window: not limited by this member" in body
        assert "concurrency: configured 1 (source: key)" in body
        assert "window_seconds: configured 10 (source: key)" in body
        after = _fetch_key_state(env["database_url"], key_id)
        assert after["rate_requests"] is None
        assert after["concurrency"] == 1
        assert after["window"] == 10


# ---------------------------------------------------------------------------
# 4) Advanced configuration: allowlisted private download + partial update
# ---------------------------------------------------------------------------


def test_configuration_export_and_update(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    key_id = env["key_legacy"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        # --- SAME-PAGE download (order 207-b requirement 2): the detail
        #     page loads FIRST; the read-only attachment authenticates
        #     WITHOUT rotating the stored CSRF token, so the still-
        #     displayed form keeps its own token.
        page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/configuration']")  # type: ignore[attr-defined]
        response = context.request.get(  # type: ignore[attr-defined]
            f"/admin/keys/{key_id}/configuration.json"
        )
        assert response.ok
        disposition = response.headers.get("content-disposition", "")
        assert disposition.startswith('attachment; filename="slaif-key-configuration-')
        assert "no-store" in response.headers.get("cache-control", "")
        document = response.json()
        assert document["schema_version"] == 1
        assert set(document["allowed_providers"]) == {"openai", "openrouter"}
        for forbidden in ("api_key", "token_hash", "owner", "cohort", "secret"):
            assert forbidden not in document, forbidden

        # --- partial update through the SAME still-displayed form (no
        #     reload/goto/token swap): the attachment GET above left the
        #     form's own CSRF token valid.
        form = page.locator("form[action$='/configuration']")
        document_text = json.dumps(
            {"schema_version": 1, "rate_limit_policy": {"requests_per_minute": 7}}
        )
        form.locator('textarea[name="configuration_json"]').fill(document_text)  # type: ignore[attr-defined]
        form.locator('input[name="confirm_configuration_update"]').check()  # type: ignore[attr-defined]
        form.locator('input[name="reason"]').fill("207 config partial update")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/configuration")
        assert status == 303, (
            "partial config update refused: " + _error_snippet(page.content())
        )
        page.wait_for_url(f"**/admin/keys/{key_id}?message=*")  # type: ignore[attr-defined]
        assert "Gateway key advanced configuration updated." in page.content()
        # Readout members render as separate text nodes (name: then value);
        # compare whitespace-normalized text, as the rate-editor case does.
        body = _flat(page)
        assert "requests_per_window: configured 7 (source: key)" in body
        # Sibling members and the allow-list are preserved.
        state = _fetch_key_state(env["database_url"], key_id)
        assert state["rate_requests"] == 7
        assert state["window"] == 10
        assert set(state["providers"] or []) == {"openai", "openrouter"}

        # --- unknown field carrying a credential-shaped canary: fixed safe
        #     refusal, the canary is never echoed, the doc is not retained.
        bad = json.dumps({"schema_version": 1, "not_a_field": CONFIG_CANARY})
        form = page.locator("form[action$='/configuration']")
        form.locator('textarea[name="configuration_json"]').fill(bad)  # type: ignore[attr-defined]
        form.locator('input[name="confirm_configuration_update"]').check()  # type: ignore[attr-defined]
        form.locator('input[name="reason"]').fill("207 unknown field")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/configuration")
        assert status == 400
        assert "Document contains unsupported fields." in page.content()
        rendered = page.content()
        assert CONFIG_CANARY not in rendered
        assert (
            page.locator('textarea[name="configuration_json"]').input_value() == ""
        )  # type: ignore[attr-defined]

        # --- missing confirmation is refused
        form = page.locator("form[action$='/configuration']")
        form.locator('textarea[name="configuration_json"]').fill(document_text)  # type: ignore[attr-defined]
        confirm = form.locator('input[name="confirm_configuration_update"]')
        if confirm.is_checked():
            confirm.uncheck()
        form.locator('input[name="reason"]').fill("207 missing confirmation")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/configuration")
        assert status == 400
        assert "Confirm the advanced key configuration update before continuing." in page.content()

        # --- missing reason is refused
        form = page.locator("form[action$='/configuration']")
        form.locator('textarea[name="configuration_json"]').fill(document_text)  # type: ignore[attr-defined]
        confirm = form.locator('input[name="confirm_configuration_update"]')
        if not confirm.is_checked():
            confirm.check()
        # The input is `required` client-side; lift that one attribute so
        # the browser can actually submit an empty reason and the SERVER's
        # fixed refusal (not native validation) is what is proven.
        form.locator('input[name="reason"]').evaluate(
            "el => el.removeAttribute('required')"
        )  # type: ignore[attr-defined]
        form.locator('input[name="reason"]').fill("")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/configuration")
        assert status == 400
        assert "Enter an audit reason before updating the advanced key configuration." in page.content()


# ---------------------------------------------------------------------------
# 5) Explain model access: shared configuration-only report, read-only
# ---------------------------------------------------------------------------


def test_explain_route_read_only(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    key_id = env["key_explain"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/explain-route']")  # type: ignore[attr-defined]
        # The login itself audits (admin_login_succeeded); snapshot only
        # after it so the read-only invariant covers the explain POSTs.
        audit_before = _audit_count(env["database_url"])

        form = page.locator("form[action$='/explain-route']")
        assert (
            form.locator('select[name="endpoint"] option').count() > 1
        )
        form.locator('select[name="endpoint"]').select_option("/v1/chat/completions")  # type: ignore[attr-defined]
        form.locator('input[name="model"]').fill("gpt-test")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/explain-route")
        assert status == 200  # read-only re-render
        report = page.locator("div[data-explain-report]")
        assert report.count() == 1
        assert report.locator(".status-pill").first.text_content().strip() == "resolved"
        resolution = report.locator("dt:has-text('Resolution') + dd").inner_text()  # type: ignore[attr-defined]
        assert "openai" in resolution and "gpt-test" in resolution
        assert report.locator("dt:has-text('Bounds')").count() == 1
        assert report.locator("dt:has-text('Not evaluated here')").count() == 1
        assert "configuration only" in page.content()
        _screenshot_element(
            page,
            'section.action-panel[aria-labelledby="key-explain-route-heading"]',
            "key-explain-report.png",
        )

        # --- unknown model: reportable blocked result
        form = page.locator("form[action$='/explain-route']")
        form.locator('select[name="endpoint"]').select_option("/v1/chat/completions")  # type: ignore[attr-defined]
        form.locator('input[name="model"]').fill("gpt-no-such-model")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/explain-route")
        assert status == 200
        report = page.locator("div[data-explain-report]")
        assert report.locator(".status-pill").first.text_content().strip() == "blocked"
        assert report.locator("dt:has-text('Blocker')").count() == 1

        # --- model outside the key's provider allow-list
        form = page.locator("form[action$='/explain-route']")
        form.locator('select[name="endpoint"]').select_option("/v1/chat/completions")  # type: ignore[attr-defined]
        form.locator('input[name="model"]').fill("gpt-other")  # type: ignore[attr-defined]
        status = _submit_form(page, form, f"/admin/keys/{key_id}/explain-route")
        assert status == 200
        report = page.locator("div[data-explain-report]")
        assert report.locator(".status-pill").first.text_content().strip() == "blocked"

        # Inspections never write: the audit trail is unchanged.
        assert _audit_count(env["database_url"]) == audit_before


# ---------------------------------------------------------------------------
# 6) No-JS server form fallback + legacy lazy controls + narrow layout
# ---------------------------------------------------------------------------


def test_nojs_fallback_legacy_lazy_and_narrow_layout(chromium, keypolicy_env) -> None:
    env = keypolicy_env
    suffix = env["suffix"]
    owner_id = env["owner_id"]

    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], java_script_enabled=False
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]

        # No-JS: the owner control is a plain text field (pre-192 law) and
        # the provider list is the manual textarea inside the collapsed
        # "Advanced manual policy strings (fallback)" disclosure.
        assert page.locator('input[name="owner_id"]').is_visible()
        page.fill('input[name="owner_id"]', owner_id)  # type: ignore[attr-defined]
        # The server default is "allow all enabled providers" (checked);
        # an allow-list key explicitly leaves that mode off.
        page.uncheck('input[name="allow_all_providers"]')  # type: ignore[attr-defined]
        page.click("details.policy-manual-details summary")  # type: ignore[attr-defined]
        page.fill('textarea[name="allowed_providers"]', "openai")  # type: ignore[attr-defined]
        page.check('input[name="allow_all_models"]')  # type: ignore[attr-defined]
        page.check('input[name="allow_all_endpoints"]')  # type: ignore[attr-defined]
        page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]
        page.fill('input[name="reason"]', f"207 no-JS key {suffix}")  # type: ignore[attr-defined]
        status = _submit_form(page, page.locator("form[action='/admin/keys/create']"), "/admin/keys/create")
        assert status == 200
        page.wait_for_url("**/admin/keys/create")  # type: ignore[attr-defined]
        # A failed create re-renders the form at 200 with a flash error;
        # the success result page has no error flash. The snippet helper
        # keeps only the fixed flash message text, never form values.
        assert "admin-flash-error" not in page.content(), (
            "no-JS create failed: " + _error_snippet(page.content())
        )
        key_id = _latest_key_id(env["database_url"], owner_id)
        env["key_nojs"] = key_id
        assert _fetch_key_state(env["database_url"], key_id)["providers"] == ["openai"]
        page.goto(f"/admin/keys/{key_id}")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/policy']")  # type: ignore[attr-defined]
        assert "Allow-list: openai" in page.content()

        # No-JS empty-selection policy submit is also refused server-side.
        page.click("details.policy-manual-details summary")  # type: ignore[attr-defined]
        page.fill('textarea[name="allowed_providers"]', "")  # type: ignore[attr-defined]
        policy_form = page.locator("form[action$='/policy']")
        policy_form.locator('input[name="reason"]').fill("207 no-JS empty")  # type: ignore[attr-defined]
        status = _submit_form(page, policy_form, f"/admin/keys/{key_id}/policy")
        assert status == 400
        assert "an empty selection never grants unrestricted access" in page.content()

        # Legacy lazy-throttling controls remain present and usable.
        lazy_form = page.locator("form[action$='/lazy-throttling']")
        assert lazy_form.count() == 1
        lazy_form.locator('input[name="lazy_throttling_mode"][value="wait"]').check()  # type: ignore[attr-defined]
        lazy_form.locator('input[name="lazy_throttling_max_wait_seconds"]').fill("30")  # type: ignore[attr-defined]
        lazy_form.locator('input[name="lazy_throttling_max_waiting_requests"]').fill("5")  # type: ignore[attr-defined]
        lazy_form.locator('input[name="reason"]').fill("207 no-JS lazy wait")  # type: ignore[attr-defined]
        status = _submit_form(page, lazy_form, f"/admin/keys/{key_id}/lazy-throttling")
        assert status == 303
        page.wait_for_url(f"**/admin/keys/{key_id}?message=*")  # type: ignore[attr-defined]
        assert "stored wait (max wait 30s, 5 waiting; source: key)" in _flat(page)
        state = _fetch_key_state(env["database_url"], key_id)
        assert (state["lazy"] or {}).get("mode") == "wait"
        assert (state["lazy"] or {}).get("max_wait_seconds") == 30

    # Narrow desktop viewport: no horizontal overflow on the busy detail page.
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 480, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/keys/{env['key_legacy']}")  # type: ignore[attr-defined]
        page.wait_for_selector("#key-effective-policy-heading")  # type: ignore[attr-defined]
        scroll_width = page.evaluate("() => document.documentElement.scrollWidth")  # type: ignore[attr-defined]
        assert int(scroll_width) <= 480
        _screenshot(page, "key-detail-narrow.png")
        # The busy policy/rate region fits the narrow viewport as well.
        page.evaluate(  # type: ignore[attr-defined]
            "() => document.getElementById('key-effective-policy-heading').scrollIntoView()"
        )
        _screenshot(page, "key-detail-narrow-policy.png")
        # Focused capture of the NEW editable rate controls at 480px.
        _screenshot_element(
            page,
            'section.action-panel[aria-labelledby="key-rate-limits-heading"]',
            "key-detail-narrow-rate-editor.png",
        )
