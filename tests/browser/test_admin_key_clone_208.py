"""208-a GUI reviewed key cloning: real Chromium on the owned PostgreSQL.

Actual uvicorn app, real stylesheet, and real HTTP admin pages against
the already-qualified owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL fixture. Exercises the G04 acceptance workflow end to end:
key-detail clone entry, the guided form (source identity, core
eligibility, target owner/cohort record pickers, three validity modes),
the review page (readable canonical policy, signed intent, no key
material), keyboard apply with confirmation and reason, the one-time
plaintext result (asserted from HTML only - the result page is NEVER
screenshotted), persisted target fidelity via direct-DB oracles, the
exact-repeat already-applied outcome, and read-only outcome recovery.
No-JS fallback and a narrow viewport round out the GUI checks.

Safety: only synthetic fixture values are read; session and CSRF values
are used transiently and never logged or screenshotted. The generated
plaintext key is asserted as booleans over page HTML only. Screenshots
(synthetic data only, no key/session/secret cells) go under
/tmp/slaif208/.

Run:  python -m pytest tests/browser/test_admin_key_clone_208.py -m playwright
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
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
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
SCREENSHOT_DIR = Path("/tmp/slaif208")

TOKEN_RE = re.compile(r'name="clone_review_intent" value="([^"]+)"')
OPERATION_RE = re.compile(
    r"clone/receipts\?operation=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"-[0-9a-f]{4}-[0-9a-f]{12})"
)
SECRET_DISPLAY_RE = re.compile(
    r'class="secret-display".*?<code>([^<]+)</code>', re.DOTALL
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


async def _seed_clonedata(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui208-{suffix}@example.org",
                    display_name="208 GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"208 GUI Inst {suffix}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"208 GUI Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                source_owner = await OwnersRepository(session).create_owner(
                    name="Browser",
                    surname="Source",
                    email=f"owner-208-src-{suffix}@example.org",
                    institution_id=institution.id,
                )
                target_owner = await OwnersRepository(session).create_owner(
                    name="Browser",
                    surname="Target",
                    email=f"owner-208-tgt-{suffix}@example.org",
                    institution_id=institution.id,
                )
                # Provider slugs are DB-unique: get-or-create so this module
                # coexists with other browser modules on a shared session DB.
                providers = ProviderConfigsRepository(session)
                if await providers.get_provider_config_by_provider("openai") is None:
                    await providers.create_provider_config(
                        provider="openai",
                        display_name="OpenAI (208 GUI)",
                        base_url="https://api.openai.test/v1",
                        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    )
                if (
                    await providers.get_provider_config_by_provider("openrouter")
                    is None
                ):
                    await providers.create_provider_config(
                        provider="openrouter",
                        display_name="OpenRouter (208 GUI)",
                        base_url="https://openrouter.test/v1",
                        api_key_env_var="OPENROUTER_API_KEY",
                    )
                routes = ModelRoutesRepository(session)
                existing = {
                    r.requested_model
                    for r in await routes.list_model_routes(provider="openai")
                }
                if "gpt-test" not in existing:
                    await routes.create_model_route(
                        requested_model="gpt-test",
                        provider="openai",
                        upstream_model="gpt-test",
                        endpoint="/v1/chat/completions",
                    )
                source = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"208gui-src-{suffix}",
                    token_hash=f"token_hash_208gui_src_{suffix}",
                    owner_id=source_owner.id,
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                    key_hint=f"sk-slaif-208s{suffix[:4]}",
                    rate_limit_requests_per_minute=30,
                    rate_limit_tokens_per_minute=10000,
                    max_concurrent_requests=2,
                    allow_all_models=True,
                    allow_all_endpoints=True,
                    created_by_admin_user_id=admin.id,
                    metadata_json={
                        "allowed_providers": ["openai"],
                        "rate_limit_policy": {"window_seconds": 10},
                        "lazy_throttling_policy": {
                            "mode": "wait",
                            "max_wait_seconds": 30,
                            "max_waiting_requests": 2,
                        },
                    },
                )
                await session.flush()
                return {
                    "admin_email": admin.email,
                    "suffix": suffix,
                    "source_owner_id": str(source_owner.id),
                    "target_owner_id": str(target_owner.id),
                    "cohort_id": str(cohort.id),
                    "key_source": str(source.id),
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Direct-DB read helpers (persistence oracles, run outside the browser)
# ---------------------------------------------------------------------------


def _db(database_url: str, coro_factory):
    """Run one async DB oracle in a worker thread (the Playwright sync API
    owns the main-thread asyncio loop)."""
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


def _key_state(database_url: str, key_id: str) -> dict[str, Any] | None:
    key_uuid = uuid.UUID(key_id)

    async def _get(session):
        key = await session.get(GatewayKey, key_uuid)
        if key is None:
            return None
        metadata = key.metadata_json if isinstance(key.metadata_json, dict) else {}
        return {
            "status": key.status,
            "owner_id": str(key.owner_id),
            "cohort_id": (str(key.cohort_id) if key.cohort_id else None),
            "providers": metadata.get("allowed_providers"),
            "models": (bool(key.allow_all_models), list(key.allowed_models or [])),
            "endpoints": (
                bool(key.allow_all_endpoints),
                list(key.allowed_endpoints or []),
            ),
            "rate_requests": key.rate_limit_requests_per_minute,
            "rate_tokens": key.rate_limit_tokens_per_minute,
            "concurrency": key.max_concurrent_requests,
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
            "token_hash": key.token_hash,
            "public_key_id": key.public_key_id,
            "valid_from": key.valid_from,
            "valid_until": key.valid_until,
            "receipt": metadata.get("clone_receipt"),
        }

    return _db(database_url, _get)


def _keys_for_owner(database_url: str, owner_id: str) -> list[str]:
    owner_uuid = uuid.UUID(owner_id)

    async def _get(session):
        result = await session.execute(
            select(GatewayKey)
            .where(GatewayKey.owner_id == owner_uuid)
            .order_by(GatewayKey.created_at.asc(), GatewayKey.id.asc())
        )
        return [str(k.id) for k in result.scalars().all()]

    return _db(database_url, _get)


def _clone_audit_count(database_url: str) -> int:
    async def _get(session):
        result = await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "gateway_key_cloned")
        )
        return int(result.scalar_one())

    return _db(database_url, _get)


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def clone_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_clonedata(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    data["database_url"] = owned_pg_url
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(clone_env) -> Iterator[object]:
    """Depends on ``clone_env`` on purpose: the Playwright sync session
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
    """Focused element capture of the NEW controls only."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    locator = page.locator(selector)  # type: ignore[attr-defined]
    locator.first.scroll_into_view_if_needed()  # type: ignore[attr-defined]
    locator.first.screenshot(path=str(SCREENSHOT_DIR / name))  # type: ignore[attr-defined]


def _flat(page: object) -> str:
    """Whitespace-normalized page source for multi-line template asserts."""
    return re.sub(r"\s+", " ", page.content())  # type: ignore[attr-defined]


def _error_snippet(html: str) -> str:
    """Fixed-label error extraction: only the flash message text is kept."""
    match = re.search(
        r'<div class="admin-flash admin-flash-error"[^>]*>\s*<p>([^<]*)</p>', html
    )
    return match.group(1) if match else "(no admin-flash-error found)"


def _select_record(page: object, label_text: str, record_id: str) -> None:
    """Drive the existing record-choice combobox for one field."""
    field = page.locator("label.rc-field", has_text=label_text)  # type: ignore[attr-defined]
    field.first.locator("button.rc-open").click()  # type: ignore[attr-defined]
    option = field.first.locator(".rc-list li").first  # type: ignore[attr-defined]
    option.wait_for(state="visible", timeout=15000)  # type: ignore[attr-defined]
    option.click()  # type: ignore[attr-defined]
    input_name = "target_owner_id" if "owner" in label_text.lower() else "target_cohort_id"
    if record_id:
        assert page.locator(f'input[name="{input_name}"]').input_value() == record_id  # type: ignore[attr-defined]
    else:
        assert (
            page.locator(f'input[name="{input_name}"]').input_value() == ""  # type: ignore[attr-defined]
        )


def _goto_clone_form(page: object, env: dict[str, Any]) -> None:
    page.goto(f"/admin/keys/{env['key_source']}")  # type: ignore[attr-defined]
    page.wait_for_selector("#key-clone-heading")  # type: ignore[attr-defined]
    page.click('a[href$="/clone"]')  # type: ignore[attr-defined]
    page.wait_for_selector("form[action$='/clone/review']")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 1) Detail entry + guided form + review (focused screenshots)
# ---------------------------------------------------------------------------


def test_clone_detail_entry_guided_form_and_review(chromium, clone_env) -> None:
    env = clone_env
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)

        # Key detail: the new clone entry plus the preserved ordinary panel.
        page.goto(f"/admin/keys/{env['key_source']}")  # type: ignore[attr-defined]
        page.wait_for_selector("#key-clone-heading")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "Clone this key" in flat
        assert "Check a clone outcome" in flat
        assert "Update Request Policy" in flat, "ordinary detail actions preserved"
        _screenshot_element(
            page, "section[aria-labelledby='key-clone-heading']", "208-detail-clone-entry.png"
        )
        _screenshot(page, "208-key-detail.png")

        # Guided form: source identity, eligibility, pickers, validity modes.
        page.click('a[href$="/clone"]')  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/clone/review']")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "Clone Gateway Key" in flat
        assert "not eligible for cloning" not in flat
        assert "Eligibility: " in flat
        assert "copy-source-expiry" in flat
        assert "duration-from-now" in flat
        assert "absolute" in flat
        assert "No cohort" in flat
        _screenshot_element(page, "[data-clone-validity]", "208-form-validity.png")
        _screenshot_element(
            page, "section[aria-labelledby='clone-target-heading']", "208-form-target.png"
        )

        # Drive the NEW target pickers through the existing combobox.
        _select_record(page, "Target owner", env["target_owner_id"])
        _select_record(page, "Target cohort (optional)", env["cohort_id"])
        # Non-minute exact duration: 3601 seconds.
        page.check("input[value='duration-from-now']")  # type: ignore[attr-defined]
        page.fill("input[name='duration_value']", "3601")  # type: ignore[attr-defined]
        page.select_option("select[name='duration_unit']", "seconds")  # type: ignore[attr-defined]

        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: r.request.method == "POST" and r.url.endswith("/clone/review")
        ) as review_info:
            page.locator("form[action$='/clone/review']").locator(
                "button[type='submit']"
            ).click()  # type: ignore[attr-defined]
        assert int(review_info.value.status) == 200  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/clone/apply']")  # type: ignore[attr-defined]

        flat = _flat(page)
        assert "Reviewed Clone Plan" in flat or "review" in flat.lower()
        assert "Allow-list: openai" in flat
        assert "Wait for capacity: max wait 30s" in flat
        # Null responses_policy: neutral readout, no blanket "disabled" claim.
        assert (
            "No explicit Responses policy: optional key capability grants are absent"
            in flat
        )
        assert "Responses disabled" not in flat
        # 10s window source: counts are per configured window, not per minute.
        assert "30 requests, 0.01M tokens per 10s window" in flat
        html = page.content()  # type: ignore[attr-defined]
        token = TOKEN_RE.search(html)
        assert token is not None, "review page must carry the signed intent"
        assert "sk-slaif-" not in html, "review page must not show a key"
        no_per_minute = "req/min" not in html and "tokens/min" not in html
        assert no_per_minute, "10s window must not be labeled per minute"
        _screenshot_element(
            page,
            "section[aria-labelledby='review-policy-heading']",
            "208-review-policy.png",
        )
        _screenshot(page, "208-review.png")

        # 2) Narrow viewport: the review controls stay usable.
        page.set_viewport_size({"width": 768, "height": 900})  # type: ignore[attr-defined]
        _screenshot_element(page, "form[action$='/clone/apply']", "208-review-narrow.png")


# ---------------------------------------------------------------------------
# 2) Keyboard apply -> one-time result -> persisted target -> repeat -> recovery
# ---------------------------------------------------------------------------


def test_clone_apply_repeat_and_recovery(chromium, clone_env) -> None:
    env = clone_env
    source_id = env["key_source"]
    database_url = env["database_url"]
    target_owner_id = env["target_owner_id"]
    source_state_before = _key_state(database_url, source_id)
    target_keys_before = _keys_for_owner(database_url, target_owner_id)
    audits_before = _clone_audit_count(database_url)

    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        _goto_clone_form(page, env)
        _select_record(page, "Target owner", env["target_owner_id"])
        _select_record(page, "Target cohort (optional)", env["cohort_id"])
        page.check("input[value='duration-from-now']")  # type: ignore[attr-defined]
        page.fill("input[name='duration_value']", "3601")  # type: ignore[attr-defined]
        page.select_option("select[name='duration_unit']", "seconds")  # type: ignore[attr-defined]
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: r.request.method == "POST" and r.url.endswith("/clone/review")
        ) as review_info:
            page.locator("form[action$='/clone/review']").locator(
                "button[type='submit']"
            ).click()  # type: ignore[attr-defined]
        assert int(review_info.value.status) == 200  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/clone/apply']")  # type: ignore[attr-defined]
        html = page.content()  # type: ignore[attr-defined]
        token = TOKEN_RE.search(html).group(1)
        operation = OPERATION_RE.search(html).group(1)

        # Keyboard apply: real focus/Space/Enter - no mouse clicks here.
        confirm = page.locator("input[name='confirm_apply']")  # type: ignore[attr-defined]
        confirm.focus()
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert confirm.is_checked(), "Space must toggle the confirmation"
        reason = page.locator("input[name='reason']")  # type: ignore[attr-defined]
        reason.focus()
        page.keyboard.type("208 browser clone")  # type: ignore[attr-defined]
        assert reason.input_value() == "208 browser clone"
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: r.request.method == "POST" and r.url.endswith("/clone/apply")
        ) as apply_info:
            page.keyboard.press("Enter")  # type: ignore[attr-defined]
        apply_response = apply_info.value  # type: ignore[attr-defined]
        assert int(apply_response.status) == 200
        no_store_headers = [
            v for k, v in apply_response.headers.items() if k.lower() == "cache-control"
        ]
        assert any("no-store" in v for v in no_store_headers)
        page.wait_for_selector("#clone-result-heading")  # type: ignore[attr-defined]

        # One-time plaintext result: HTML assertions only (never screenshotted).
        result_html = page.content()  # type: ignore[attr-defined]
        secret_match = SECRET_DISPLAY_RE.search(result_html)
        assert secret_match is not None, "plaintext key not displayed exactly once"
        displayed = secret_match.group(1)
        prefix_ok = displayed.startswith("sk-slaif-")
        count_ok = result_html.count(displayed) == 1
        assert prefix_ok and count_ok, "displayed key shape/count wrong"
        assert "New Key" in _flat(page)

        # Persisted target: faithful policy, independent identity, zero usage.
        target_keys = _keys_for_owner(database_url, target_owner_id)
        assert len(target_keys) == len(target_keys_before) + 1
        target_id = next(k for k in target_keys if k not in target_keys_before)
        source_state = _key_state(database_url, source_id)
        target_state = _key_state(database_url, target_id)
        assert target_state is not None
        for field in (
            "status",
            "cohort_id",
            "providers",
            "models",
            "endpoints",
            "rate_requests",
            "rate_tokens",
            "concurrency",
            "lazy",
        ):
            expected = source_state_before[field]
            if field == "cohort_id":
                expected = env["cohort_id"]
            assert target_state[field] == expected, field
        assert target_state["owner_id"] == target_owner_id
        zero_usage = all(int(v) == 0 for v in target_state["usage"])
        zero_reservations = all(int(v) == 0 for v in target_state["reservations"])
        assert zero_usage and zero_reservations, "target must start unused"
        independent = (
            target_state["token_hash"] != source_state["token_hash"]
            and target_state["public_key_id"] != source_state_before["public_key_id"]
        )
        assert independent, "target must have independent material and identity"
        window = target_state["valid_until"] - target_state["valid_from"]
        assert window == timedelta(seconds=3601), "3601s window not persisted exactly"
        receipt = target_state["receipt"]
        assert isinstance(receipt, dict) and receipt.get("status") == "created"
        assert receipt.get("operation_uuid") == operation
        assert receipt.get("source_gateway_key_id") == source_id
        assert receipt.get("target_gateway_key_id") == target_id
        assert _clone_audit_count(database_url) == audits_before + 1
        # Source unchanged by the clone.
        assert _key_state(database_url, source_id) == source_state_before

        # Exact-repeat: the SAME operation returns already-applied, no new key.
        detail_html = page.request.get(f"/admin/keys/{source_id}").text()  # type: ignore[attr-defined]
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', detail_html).group(1)
        repeat_response = page.request.post(  # type: ignore[attr-defined]
            f"/admin/keys/{source_id}/clone/apply",
            form={
                "csrf_token": csrf,
                "clone_review_intent": token,
                "confirm_apply": "true",
                "reason": "208 exact repeat",
            },
        )
        assert int(repeat_response.status) == 200, (
            int(repeat_response.status), _error_snippet(repeat_response.text())
        )
        repeat_html = repeat_response.text()
        assert "Already Applied" in repeat_html
        repeat_no_redisplay = SECRET_DISPLAY_RE.search(repeat_html) is None
        assert repeat_no_redisplay, "already-applied must not redisplay plaintext"
        assert target_id in repeat_html, "already-applied returns the recorded target"
        assert _keys_for_owner(database_url, target_owner_id) == (
            target_keys
        )
        assert _clone_audit_count(database_url) == audits_before + 1

        # Read-only recovery by operation, plus the not-found view.
        page.goto(f"/admin/keys/{source_id}/clone/receipts?operation={operation}")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "completed and created exactly one target key" in flat
        assert target_id in flat
        _screenshot(page, "208-recovery-created.png")
        page.goto(
            f"/admin/keys/{source_id}/clone/receipts?operation={uuid.uuid4()}"
        )  # type: ignore[attr-defined]
        assert "No clone receipt matches" in _flat(page)
        assert "NOTHING is assumed" in _flat(page)
        _screenshot(page, "208-recovery-notfound.png")


# ---------------------------------------------------------------------------
# 3) No-JS fallback: plain inputs, radio, typed UUIDs
# ---------------------------------------------------------------------------


def test_clone_no_js_fallback(chromium, clone_env) -> None:
    env = clone_env
    database_url = env["database_url"]
    source_id = env["key_source"]
    target_owner_id = env["target_owner_id"]
    source_state_before = _key_state(database_url, source_id)
    target_keys_before = _keys_for_owner(database_url, target_owner_id)
    audits_before = _clone_audit_count(database_url)
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], java_script_enabled=False
    ) as context:
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/keys/{source_id}/clone")  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/clone/review']")  # type: ignore[attr-defined]
        flat = _flat(page)
        assert "not eligible for cloning" not in flat
        # No-JS: type the target UUIDs as plain text (no combobox needed).
        # Cohort is deliberately left blank: the no-cohort path.
        page.fill("input[name='target_owner_id']", env["target_owner_id"])  # type: ignore[attr-defined]
        page.check("input[value='duration-from-now']")  # type: ignore[attr-defined]
        page.fill("input[name='duration_value']", "3601")  # type: ignore[attr-defined]
        page.select_option("select[name='duration_unit']", "seconds")  # type: ignore[attr-defined]
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: r.request.method == "POST" and r.url.endswith("/clone/review")
        ) as review_info:
            page.locator("form[action$='/clone/review']").locator(
                "button[type='submit']"
            ).click()  # type: ignore[attr-defined]
        assert int(review_info.value.status) == 200  # type: ignore[attr-defined]
        page.wait_for_selector("form[action$='/clone/apply']")  # type: ignore[attr-defined]
        html = page.content()  # type: ignore[attr-defined]
        assert TOKEN_RE.search(html) is not None
        assert "sk-slaif-" not in html
        operation = OPERATION_RE.search(html).group(1)

        # Native (no-JS) confirm/reason/apply and the one-time result.
        page.check("input[name='confirm_apply']")  # type: ignore[attr-defined]
        page.fill("input[name='reason']", "208 no-js clone")  # type: ignore[attr-defined]
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: r.request.method == "POST" and r.url.endswith("/clone/apply")
        ) as apply_info:
            page.locator("form[action$='/clone/apply']").locator(
                "button[type='submit']"
            ).click()  # type: ignore[attr-defined]
        assert int(apply_info.value.status) == 200  # type: ignore[attr-defined]
        page.wait_for_selector("#clone-result-heading")  # type: ignore[attr-defined]
        result_html = page.content()  # type: ignore[attr-defined]
        secret_match = SECRET_DISPLAY_RE.search(result_html)
        assert secret_match is not None, "no-JS result must show the one-time key"
        displayed = secret_match.group(1)
        prefix_ok = displayed.startswith("sk-slaif-")
        count_ok = result_html.count(displayed) == 1
        assert prefix_ok and count_ok, "displayed key shape/count wrong"

        # Persisted target for the no-cohort path.
        target_keys = _keys_for_owner(database_url, target_owner_id)
        assert len(target_keys) == len(target_keys_before) + 1
        target_id = next(k for k in target_keys if k not in target_keys_before)
        target_state = _key_state(database_url, target_id)
        assert target_state is not None
        assert target_state["owner_id"] == target_owner_id
        assert target_state["cohort_id"] is None, "blank cohort means no cohort"
        for field in (
            "status",
            "providers",
            "models",
            "endpoints",
            "rate_requests",
            "rate_tokens",
            "concurrency",
            "lazy",
        ):
            assert target_state[field] == source_state_before[field], field
        zero_usage = all(int(v) == 0 for v in target_state["usage"])
        assert zero_usage, "no-JS target must start unused"
        receipt = target_state["receipt"]
        assert isinstance(receipt, dict) and receipt.get("status") == "created"
        assert receipt.get("operation_uuid") == operation
        assert _clone_audit_count(database_url) == audits_before + 1
