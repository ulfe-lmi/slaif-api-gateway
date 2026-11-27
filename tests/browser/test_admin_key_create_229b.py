"""229-b GUI key creation: client presets, readiness, and safe errors.

Real Chromium on the owned, loopback-bound PostgreSQL fixture with an
actual uvicorn app. Exercises the 229-b completion scope end to end:

1. the guided main flow stays visible while every advanced category is
   collapsed by default, with a plain-language access summary;
2. client-use preset endpoint ownership: checking a client preselects
   the endpoints that client needs, unchecking it removes ONLY
   preset-owned endpoints while operator-added endpoints survive, and
   repeated toggling is stable (no duplicates);
3. a genuinely missing required endpoint warns before submit and is
   still refused by the server with the exact operator text;
4. document mode makes client-use choices VISIBLY INACTIVE (disabled,
   never hidden, never submitted) with a visible note, and returning
   to guided re-enables them and re-syncs presets;
5. an ACTUAL no-JavaScript Hermes create: the server applies the client
   preset add-only (keeps the operator's explicit endpoint, adds the
   chat endpoint, persists the active Hermes pin) — no browser script
   supplies required endpoints;
6. safe structured errors: field anchors, aria-invalid, focus on the
   failed submit, and the affected collapsed group opened.

Safety: only synthetic fixture values are read; session/CSRF values are
used transiently for login and never logged or screenshotted.
Screenshots (synthetic data only, no key/session/secret cells) go under
/home/janezp/codex-work/slaif-229-task/ (the existing owned task dir).

Run:  python -m pytest tests/browser/test_admin_key_create_229b.py -m playwright
"""

from __future__ import annotations

import asyncio
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    EmailDelivery,
    GatewayKey,
    ModelRoute,
    PricingRule,
    ProviderConfig,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.modules.clients.agent_chat import (
    bootstrap_agent_chat_client_modules,
)
from slaif_gateway.modules.clients.hermes_0225_chat import (
    HERMES_0225_CHAT_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.registry import active_client_module_facts
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_CODEX_PROFILE_ID,
    build_codex_profile_declaration,
    get_codex_profile,
)
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
SCREENSHOT_DIR = Path("/home/janezp/codex-work/slaif-229-task")

OPENCODE_RESPONSES_GATES = (
    "codex_request_envelope",
    "codex_client_tools",
    "codex_streaming_tool_events",
    "codex_encrypted_reasoning_replay",
)

_CHAT_ENDPOINT = "/v1/chat/completions"
_CODEX_ENDPOINTS = ("/v1/models", "/v1/responses")

ADVANCED_DETAIL_HEADING_IDS = (
    "create-adv-external-tools-heading",
    "create-adv-rate-limit-heading",
    "create-adv-live-burn-heading",
    "create-adv-calibration-heading",
)


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


def _key_rows(database_url: str, owner_id: uuid.UUID) -> list[GatewayKey]:
    async def _get(session):
        result = await session.execute(
            select(GatewayKey).where(GatewayKey.owner_id == owner_id)
        )
        return list(result.scalars().all())

    return _db(database_url, _get)


def _count(database_url: str, model) -> int:
    async def _get(session):
        result = await session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())

    return _db(database_url, _get)


def _created_audit_count(database_url: str) -> int:
    async def _get(session):
        result = await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.entity_type == "gateway_key",
                AuditLog.action == "gateway_key_created",
            )
        )
        return int(result.scalar_one())

    return _db(database_url, _get)


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
# Seed: one enabled Chat provider (gpt-test) + one enabled Codex/Responses
# provider (qualified qwen route with the four OpenCode gates), both with
# active EUR pricing, plus admin/owner/cohort identity records.
# ---------------------------------------------------------------------------


async def _seed_create229b_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui229b-{suffix}@example.org",
                    display_name="229-b GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"229b GUI Inst {suffix}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"229b GUI Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Browser",
                    surname="Twentytwenty",
                    email=f"owner-229b-{suffix}@example.org",
                    institution_id=institution.id,
                )
                chat_provider = f"chat229b-{suffix}"
                session.add(
                    ProviderConfig(
                        provider=chat_provider,
                        display_name="Chat 229b Provider",
                        kind="openai_compatible",
                        base_url=f"https://chat229b-{suffix}.example/v1",
                        api_key_env_var=f"GUI229B_CHAT_{suffix.upper()}_KEY",
                        enabled=True,
                    )
                )
                await session.flush()
                session.add(
                    ModelRoute(
                        requested_model="gpt-test",
                        provider=chat_provider,
                        upstream_model="gpt-test",
                        endpoint=_CHAT_ENDPOINT,
                        enabled=True,
                    )
                )
                session.add(
                    PricingRule(
                        provider=chat_provider,
                        upstream_model="gpt-test",
                        endpoint=_CHAT_ENDPOINT,
                        input_price_per_1m=Decimal("1.000000000"),
                        cached_input_price_per_1m=Decimal("0.250000000"),
                        output_price_per_1m=Decimal("1.000000000"),
                        reasoning_price_per_1m=Decimal("2.000000000"),
                        request_price=Decimal("0.000000000"),
                        currency="EUR",
                        valid_from=now - timedelta(days=1),
                        enabled=True,
                    )
                )
                codex_provider = f"syn229b-{suffix}"
                session.add(
                    ProviderConfig(
                        provider=codex_provider,
                        display_name="Syn 229b Provider",
                        kind="openai_compatible",
                        base_url=f"https://syn229b-{suffix}.example/v1",
                        api_key_env_var=f"GUI229B_SYN_{suffix.upper()}_KEY",
                        enabled=True,
                    )
                )
                await session.flush()
                session.add(
                    ModelRoute(
                        requested_model=profile.public_model,
                        provider=codex_provider,
                        upstream_model=profile.upstream_model,
                        match_type="exact",
                        endpoint="/v1/responses",
                        priority=1,
                        enabled=True,
                        visible_in_models=True,
                        supports_streaming=True,
                        capabilities={
                            "responses": {
                                "text": True,
                                "stateless": True,
                                "streaming": True,
                                **{gate: True for gate in OPENCODE_RESPONSES_GATES},
                            },
                            "codex_limits": {
                                "context_window_tokens": profile.context_window_tokens,
                                "default_max_output_tokens": profile.default_max_output_tokens,
                                "max_output_tokens": profile.max_output_tokens,
                            },
                            "codex_profile": build_codex_profile_declaration(
                                QWEN38_CODEX_PROFILE_ID
                            ),
                        },
                    )
                )
                session.add(
                    PricingRule(
                        provider=codex_provider,
                        upstream_model=profile.upstream_model,
                        endpoint="/v1/responses",
                        input_price_per_1m=Decimal("1.000000000"),
                        cached_input_price_per_1m=Decimal("0.250000000"),
                        output_price_per_1m=Decimal("1.000000000"),
                        reasoning_price_per_1m=Decimal("2.000000000"),
                        request_price=Decimal("0.000000000"),
                        currency="EUR",
                        valid_from=now - timedelta(days=1),
                        enabled=True,
                        pricing_metadata={
                            "codex_accounting": {
                                "long_context_threshold_tokens": 98304,
                                "long_context_input_multiplier": "2",
                                "long_context_output_multiplier": "2",
                                "cache_write_input_multiplier": "1",
                            }
                        },
                    )
                )
                await session.flush()
                return {
                    "admin_email": admin.email,
                    "owner_id": owner.id,
                    "cohort_id": cohort.id,
                    "chat_provider": chat_provider,
                    "qwen_model": profile.public_model,
                }
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def env229b(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_create229b_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    data["database_url"] = owned_pg_url
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(env229b) -> Iterator[object]:
    """Depends on ``env229b`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PostgreSQL readiness,
    seeding, and the uvicorn app must complete BEFORE it starts (and the
    browser closes before DB teardown)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(page: object, env: dict[str, Any]) -> None:
    page.goto("/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _screenshot(page: object, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _flat(page: object) -> str:
    """Whitespace-normalized page source for multi-line template asserts."""
    return re.sub(r"\s+", " ", page.content())  # type: ignore[attr-defined]


def _open_manual_details(page: object) -> None:
    """Open the collapsed 'Advanced manual policy strings (fallback)'
    group so the manual endpoint textarea is operable by a real user."""
    details = page.locator("details.policy-manual-details")  # type: ignore[attr-defined]
    if details.get_attribute("open") is None:
        details.locator("summary").click()


def _manual_endpoints(page: object) -> list[str]:
    value = page.evaluate(  # type: ignore[attr-defined]
        "() => document.querySelector('[data-policy-manual=\"endpoints\"]').value"
    )
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _set_manual_endpoints(page: object, lines: list[str]) -> None:
    """Set the manual endpoint textarea the way an operator typing would
    (value + input event, so the preset-ownership listener sees it)."""
    page.evaluate(  # type: ignore[attr-defined]
        """(lines) => {
            const manual = document.querySelector('[data-policy-manual="endpoints"]');
            manual.value = lines.join("\\n");
            manual.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        lines,
    )


def _client_box(page: object, name: str) -> object:
    return page.locator(f'input[name="{name}"]')  # type: ignore[attr-defined]


def _submit_create(page: object) -> int:
    """POST the create form; return the HTTP status of the POST response."""
    with page.expect_response(  # type: ignore[attr-defined]
        lambda r: r.request.method == "POST" and r.url.endswith("/admin/keys/create")
    ) as info:
        page.get_by_role("button", name="Create key").click()  # type: ignore[attr-defined]
    return int(info.value.status)


def _flash_error(page: object) -> str:
    match = re.search(
        r'<div class="admin-flash admin-flash-error"[^>]*>(.*?)</div>',
        page.content(),  # type: ignore[attr-defined]
        re.S,
    )
    assert match is not None, "no error flash on the create page"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip()


def _fill_identity(page: object, env: dict[str, Any], *, js_mode: bool) -> None:
    """Owner/cohort/validity/delivery/reason, JS-mode rc widget or plain
    no-JS inputs."""
    if js_mode:
        owner_field = page.locator("label.rc-field", has_text="Owner")  # type: ignore[attr-defined]
        owner_field.first.locator("button.rc-open").click()
        option = owner_field.first.locator(".rc-list li").first
        option.wait_for(state="visible", timeout=15000)  # type: ignore[attr-defined]
        option.click()
        assert (  # type: ignore[attr-defined]
            page.locator('input[name="owner_id"]').input_value() == str(env["owner_id"])
        )
    else:
        page.fill(  # type: ignore[attr-defined]
            'input[name="owner_id"]', str(env["owner_id"])
        )
    page.fill('input[name="reason"]', "229-b browser regression key")  # type: ignore[attr-defined]
    # A concrete validity window (the guided form starts blank).
    page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]


def _select_explicit_provider(page: object, provider: str) -> None:
    """Narrow from the default allow-all to ONE explicit provider the way
    an operator does: type the slug, then uncheck allow-all providers."""
    page.fill('textarea[name="allowed_providers"]', provider)  # type: ignore[attr-defined]
    page.locator('input[name="allow_all_providers"]').uncheck()  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# 1) Main flow visible, advanced collapsed, access summary, layouts
# ---------------------------------------------------------------------------


def test_main_flow_visible_advanced_collapsed_summary(chromium, env229b) -> None:
    env = env229b
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]

        # Main-flow headings are plain language and visible.
        for heading in (
            "Who will use this key?",
            "Chosen provider and models",
            "Request Policy",
            "Validity",
            "What this key will be able to do",
            "Create Key",
        ):
            assert page.get_by_role("heading", name=heading).first.is_visible()  # type: ignore[attr-defined]

        # Every advanced category is collapsed by default.
        for heading_id in ADVANCED_DETAIL_HEADING_IDS:
            details = page.locator(  # type: ignore[attr-defined]
                f'details[aria-labelledby="{heading_id}"]'
            )
            assert details.count() == 1
            assert details.get_attribute("open") is None

        # Jargon removed from the primary advanced labels.
        assert (
            page.get_by_role("heading", name="Redis Operational Rate Limits").count()
            == 0
        )
        assert "Request speed controls" in _flat(page)
        assert "Provider-run tools and their cost risk" in _flat(page)
        assert "Stopping long responses early" in _flat(page)

        # Plain-language access summary (guided mode) with the rows the
        # operator actually sees before creating.
        summary = page.locator("dl.access-summary")  # type: ignore[attr-defined]
        assert summary.is_visible()
        text = _flat(page)
        for label in (
            "Client setup",
            "Models",
            "Providers",
            "Endpoints",
            "Lifetime limits",
            "After creation",
        ):
            assert label in text
        assert "None - plain API key only" in text
        assert "unlimited" in text  # blank lifetime limits = unlimited, stated

        _screenshot(page, "229b-create-ordinary-desktop.png")

    # Narrow desktop viewport: the busy guided form still fits.
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], viewport={"width": 480, "height": 900}
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        overflow = page.evaluate(  # type: ignore[attr-defined]
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0
        _screenshot(page, "229b-create-ordinary-narrow.png")


# ---------------------------------------------------------------------------
# 2) Preset switching: endpoint ownership, explicit selections survive,
#    repeated toggling is stable
# ---------------------------------------------------------------------------


def test_preset_switching_endpoint_ownership(chromium, env229b) -> None:
    env = env229b
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _open_manual_details(page)

        # Hermes checked: its preset-owned chat endpoint is preselected.
        _client_box(page, "client_use_hermes").check()
        assert _manual_endpoints(page) == [_CHAT_ENDPOINT]

        # Operator explicitly adds /v1/models (a real typing gesture).
        _set_manual_endpoints(page, [_CHAT_ENDPOINT, "/v1/models"])
        assert page.locator(  # type: ignore[attr-defined]
            '[data-client-use-summary]'
        ).is_visible()

        # Uncheck Hermes: preset-owned endpoint removed, explicit kept.
        _client_box(page, "client_use_hermes").uncheck()
        assert _manual_endpoints(page) == ["/v1/models"]

        # Codex checked: its two preset endpoints preselected; the
        # operator's /v1/models stays (added once, not duplicated).
        _client_box(page, "client_use_codex").check()
        assert sorted(_manual_endpoints(page)) == sorted(
            ["/v1/models", "/v1/responses"]
        )

        # Repeated Hermes toggling is stable and duplicate-free.
        for _ in range(3):
            _client_box(page, "client_use_hermes").check()
            _client_box(page, "client_use_hermes").uncheck()
        assert sorted(_manual_endpoints(page)) == sorted(
            ["/v1/models", "/v1/responses"]
        )
        _client_box(page, "client_use_hermes").check()
        assert sorted(_manual_endpoints(page)) == sorted(
            ["/v1/models", "/v1/responses", _CHAT_ENDPOINT]
        )

        # Unchecking Codex removes only its preset-owned /v1/responses.
        _client_box(page, "client_use_codex").uncheck()
        assert sorted(_manual_endpoints(page)) == sorted(
            ["/v1/models", _CHAT_ENDPOINT]
        )

        # The selected-endpoints control mirrors the manual list (the
        # server reads the manual textarea; this proves the visible
        # operator view agrees with what is submitted).
        # The selected pane mirrors the manual list (all child options,
        # per policy-selector.js; not necessarily DOM-selected).
        selected = page.evaluate(  # type: ignore[attr-defined]
            """() => Array.from(
                document.querySelector('[data-policy-selected="endpoints"]').options
            ).map((option) => option.value)"""
        )
        assert sorted(selected) == sorted(
            ["/v1/models", _CHAT_ENDPOINT]
        )

        # No checked client -> the preset summary line hides again.
        _client_box(page, "client_use_hermes").uncheck()
        assert not page.locator(  # type: ignore[attr-defined]
            '[data-client-use-summary]'
        ).is_visible()
        assert _manual_endpoints(page) == ["/v1/models"]

        _screenshot(page, "229b-create-client-presets.png")


# ---------------------------------------------------------------------------
# 3) Missing preset endpoint: truthful pre-submit warning + server
#    add-only application; a genuine refusal leaves no side effects
# ---------------------------------------------------------------------------


def test_missing_preset_endpoint_warns_then_server_applies_add_only(
    chromium, env229b
) -> None:
    """Operator trims the preset-owned chat endpoint out of an explicit
    list. The pre-submit warning tells the truth: the server applies the
    client preset add-only (it does not refuse). The create succeeds, the
    confirmation page shows the final endpoint list, and the stored grant
    is exactly the operator's explicit entries plus the added endpoint."""
    env = env229b
    before_ids = {str(r.id) for r in _key_rows(env["database_url"], env["owner_id"])}
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _fill_identity(page, env, js_mode=True)
        _open_manual_details(page)
        _client_box(page, "client_use_hermes").check()
        _select_explicit_provider(page, str(env["chat_provider"]))
        page.fill('textarea[name="allowed_models"]', "gpt-test")  # type: ignore[attr-defined]

        # Operator trims the list to /v1/models only, removing the
        # preset-owned chat endpoint. Non-empty, so the generic "select at
        # least one endpoint" core check is not what would fire.
        _set_manual_endpoints(page, ["/v1/models"])

        # Pre-submit warning, without navigating away. It must describe the
        # real add-only server behavior, not a false refusal.
        page.evaluate(  # type: ignore[attr-defined]
            "() => document.querySelector('form.create-form')"
            ".dispatchEvent(new Event('submit'))"
        )
        summary_text = page.locator(  # type: ignore[attr-defined]
            '[data-client-use-summary]'
        ).inner_text()
        assert "Warning: a checked client needs" in summary_text
        assert _CHAT_ENDPOINT in summary_text
        assert "refuse" not in summary_text

        # The server applies the preset add-only: success, not refusal.
        status = _submit_create(page)
        assert status == 200
        result_text = _flat(page)
        assert "Gateway Key Created" in result_text
        # The final endpoint list is shown on the confirmation page.
        assert "/v1/models, /v1/chat/completions" in result_text

    # The stored grant is the operator's explicit entry plus exactly the
    # one added required endpoint; no allow-all, nothing else granted.
    new_keys = [
        r
        for r in _key_rows(env["database_url"], env["owner_id"])
        if str(r.id) not in before_ids
    ]
    assert len(new_keys) == 1
    key = new_keys[0]
    assert set(key.allowed_endpoints) == {"/v1/models", _CHAT_ENDPOINT}
    assert key.allow_all_endpoints is False


def test_refused_create_leaves_no_side_effects(chromium, env229b) -> None:
    """A genuine validation refusal (invalid quota value) must create
    nothing: no key, no email row, no create audit row for the seeded
    owner, and the safe error identifies the affected control."""
    env = env229b
    keys_before = _key_rows(env["database_url"], env["owner_id"])
    emails_before = _count(env["database_url"], EmailDelivery)
    audits_before = _created_audit_count(env["database_url"])
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _fill_identity(page, env, js_mode=True)
        _client_box(page, "client_use_hermes").check()
        _open_manual_details(page)
        _select_explicit_provider(page, str(env["chat_provider"]))
        page.fill('textarea[name="allowed_models"]', "gpt-test")  # type: ignore[attr-defined]
        page.fill('input[name="cost_limit_eur"]', "abc")  # type: ignore[attr-defined]

        status = _submit_create(page)
        assert status == 400
        error = _flash_error(page)
        assert "Enter valid positive quota and rate-limit values." in error
        assert "Cost limit EUR" in error  # structured anchor names the control
    # Database side: nothing was created.
    assert (
        {str(r.id) for r in _key_rows(env["database_url"], env["owner_id"])}
        == {str(r.id) for r in keys_before}
    )
    assert _count(env["database_url"], EmailDelivery) == emails_before
    assert _created_audit_count(env["database_url"]) == audits_before


# 4) Document mode: client choices visibly inactive, never submitted,
#    guided return re-enables and re-syncs
# ---------------------------------------------------------------------------


def test_document_mode_disables_client_choices(chromium, env229b) -> None:
    env = env229b
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _client_box(page, "client_use_hermes").check()

        page.select_option('select[name="policy_source"]', "configuration")  # type: ignore[attr-defined]

        # All four client checkboxes are VISIBLY INACTIVE: still rendered
        # and visible, but disabled (and therefore never submitted).
        for name in (
            "client_use_codex",
            "client_use_opencode_chat",
            "client_use_opencode_responses",
            "client_use_hermes",
        ):
            box = _client_box(page, name)
            assert box.is_visible()
            assert box.is_disabled()
        assert page.locator('[data-doc-mode-client-note]').is_visible()  # type: ignore[attr-defined]

        # Disabled controls are not part of the submission.
        submitted = page.evaluate(  # type: ignore[attr-defined]
            "() => new FormData(document.querySelector('form.create-form'))"
            '.get("client_use_hermes")'
        )
        assert submitted is None

        # The guided policy body is compacted; the document group is shown.
        assert page.locator('[data-guided-policy-body]').first.is_hidden()  # type: ignore[attr-defined]
        assert page.locator(  # type: ignore[attr-defined]
            '[data-create-configuration-document-group]'
        ).is_visible()
        _screenshot(page, "229b-create-doc-mode.png")

        # Deliberate return to guided: re-enabled, preset re-synced.
        page.select_option('select[name="policy_source"]', "guided")  # type: ignore[attr-defined]
        assert _client_box(page, "client_use_hermes").is_enabled()
        assert not page.locator('[data-doc-mode-client-note]').is_visible()  # type: ignore[attr-defined]
        assert page.locator('[data-guided-policy-body]').first.is_visible()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 5) ACTUAL no-JS client create: server-applied preset, active pin kept
# ---------------------------------------------------------------------------


def test_nojs_hermes_create_server_applied_preset(chromium, env229b) -> None:
    env = env229b
    owner_id = env["owner_id"]
    emails_before = _count(env["database_url"], EmailDelivery)
    audits_before = _created_audit_count(env["database_url"])
    with chromium.new_context(
        base_url=env["base_url"], java_script_enabled=False
    ) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]

        before_ids = {str(r.id) for r in _key_rows(env["database_url"], owner_id)}
        # No-JS: plain inputs, real operator typing. The manual endpoint
        # group is the documented no-JS fallback; the operator enters ONE
        # explicit endpoint and checks the client — the SERVER must apply
        # the preset add-only.
        _fill_identity(page, env, js_mode=False)
        _open_manual_details(page)
        _select_explicit_provider(page, str(env["chat_provider"]))
        page.fill('textarea[name="allowed_models"]', "gpt-test")  # type: ignore[attr-defined]
        page.fill('textarea[name="allowed_endpoints"]', "/v1/models")  # type: ignore[attr-defined]
        _client_box(page, "client_use_hermes").check()
        _screenshot(page, "229b-create-nojs-client-form.png")

        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: r.request.method == "POST"
            and r.url.endswith("/admin/keys/create")
        ) as info:
            page.get_by_role("button", name="Create key").click()  # type: ignore[attr-defined]
        # No-JS success path: the plain form POST renders the plaintext
        # create-result page directly (where the operator copies the key);
        # no JS redirect is involved, so this is a 200, not a 303.
        assert info.value.status == 200
        result_text = info.value.text()
        assert "Gateway Key Created" in result_text
        assert "Plaintext Gateway Key" in result_text

    # Server applied the preset: the operator's explicit endpoint is kept
    # and the chat endpoint the client requires was added.
    rows = _key_rows(env["database_url"], owner_id)
    new_keys = [r for r in rows if str(r.id) not in before_ids]
    assert len(new_keys) == 1
    key = new_keys[0]
    assert set(key.allowed_endpoints) == {"/v1/models", _CHAT_ENDPOINT}

    # The ACTIVE installed Hermes pin is persisted (identity from the
    # registry, not a frozen constant).
    bootstrap_agent_chat_client_modules()
    metadata = key.metadata_json or {}
    chat_pin = metadata.get("chat_client_module")
    facts = active_client_module_facts(HERMES_0225_CHAT_CLIENT_MODULE_ID)
    assert isinstance(chat_pin, dict)
    assert chat_pin == {
        "id": facts.module_id,
        "version": facts.module_version,
        "fixture_sha256": facts.fixture_sha256,
    }

    assert _count(env["database_url"], EmailDelivery) == emails_before
    assert _created_audit_count(env["database_url"]) == audits_before + 1


# ---------------------------------------------------------------------------
# 6) Safe structured errors: anchors, aria-invalid, focus, group opened
# ---------------------------------------------------------------------------


def test_error_state_anchors_focus_and_open_details(chromium, env229b) -> None:
    env = env229b
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        _fill_identity(page, env, js_mode=True)
        _client_box(page, "client_use_hermes").check()
        _open_manual_details(page)
        _set_manual_endpoints(page, [_CHAT_ENDPOINT])
        _select_explicit_provider(page, str(env["chat_provider"]))
        page.fill('textarea[name="allowed_models"]', "gpt-test")  # type: ignore[attr-defined]

        # One invalid advanced value inside a collapsed group.
        rate_details = page.locator(  # type: ignore[attr-defined]
            'details[aria-labelledby="create-adv-rate-limit-heading"]'
        )
        assert rate_details.get_attribute("open") is None
        # Set the invalid value while the group stays COLLAPSED: the
        # error-focus script (not the operator) must open it after the
        # refused submit.
        page.evaluate(  # type: ignore[attr-defined]
            """() => {
                const input = document.querySelector(
                    'input[name="rate_limit_requests_per_minute"]'
                );
                input.value = "abc";
            }"""
        )

        status = _submit_create(page)
        assert status == 400

        # Structured summary with a clickable anchor for the flagged field.
        summary = page.locator("#create-error-summary")  # type: ignore[attr-defined]
        assert summary.is_visible()
        error_text = summary.inner_text()
        assert "Enter valid positive quota and rate-limit values." in error_text
        assert "Traceback" not in error_text
        assert "Reference ID:" in error_text
        anchor = summary.locator(  # type: ignore[attr-defined]
            'a.create-error-link[href="#create-field-rate_limit_requests_per_minute"]'
        )
        assert anchor.count() >= 1

        # The flagged control is marked and focused; the collapsed group
        # that contains it was opened by the page script.
        flagged = page.locator(  # type: ignore[attr-defined]
            "#create-field-rate_limit_requests_per_minute"
        )
        assert flagged.count() == 1
        assert flagged.get_attribute("aria-invalid") == "true"
        assert "create-error-field" in (flagged.get_attribute("class") or "")
        assert rate_details.get_attribute("open") is not None
        active_id = page.evaluate("() => document.activeElement.id")  # type: ignore[attr-defined]
        assert active_id == "create-field-rate_limit_requests_per_minute"

        # All four rate fields of the failing control group are flagged.
        for name in (
            "rate_limit_requests_per_minute",
            "rate_limit_tokens_per_minute",
            "rate_limit_concurrent_requests",
            "rate_limit_window_seconds",
        ):
            assert page.locator(f"#create-field-{name}").count() == 1  # type: ignore[attr-defined]

        # The entered (nonsecret) value is preserved for correction.
        assert (
            page.locator('input[name="rate_limit_requests_per_minute"]').input_value()  # type: ignore[attr-defined]
            == "abc"
        )
        _screenshot(page, "229b-create-error-state.png")


# ---------------------------------------------------------------------------
# Advanced explanation actually open (desktop) for root inspection
# ---------------------------------------------------------------------------


def test_advanced_explanations_open_screenshot(chromium, env229b) -> None:
    env = env229b
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")
        page.wait_for_selector("form[action='/admin/keys/create']")  # type: ignore[attr-defined]
        rate_details = page.locator(  # type: ignore[attr-defined]
            'details[aria-labelledby="create-adv-rate-limit-heading"]'
        )
        page.locator("#create-adv-rate-limit-heading").click()
        assert rate_details.get_attribute("open") is not None
        # Per-field help is adjacent and plain-language.
        assert "requests per minute" in rate_details.inner_text().lower()  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "229b-create-advanced-open.png"), full_page=True
        )
