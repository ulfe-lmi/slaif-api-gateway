from __future__ import annotations

import asyncio
import os
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import OneTimeSecret
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from tests.integration.db_test_utils import run_alembic_upgrade_head


ADMIN_PASSWORD = "correct horse battery staple"
FAKE_PROVIDER_KEY_VALUE = "sk-browser-provider-secret-must-not-render-123456"
FAKE_OPENROUTER_KEY_VALUE = "sk-or-browser-provider-secret-must-not-render-123456"
FAKE_PLAINTEXT_GATEWAY_KEY = "sk-slaif-browser-plaintext-secret-must-not-render"
PROMPT_TEXT = "browser prompt text that must not render"
COMPLETION_TEXT = "browser completion text that must not render"


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


def _test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for optional Playwright admin smoke tests")
    return database_url


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


async def _create_dashboard_data(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    try:
        async with session_factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"admin-browser-{suffix}@example.org",
                    display_name="Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"Browser Institution {suffix}",
                    country="SI",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"Browser Cohort {suffix}",
                    description="safe browser cohort",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Browser",
                    surname="Owner",
                    email=f"owner-browser-{suffix}@example.org",
                    institution_id=institution.id,
                )
                key = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"browser-{suffix[:16]}",
                    token_hash=f"token_hash_browser_secret_{suffix}",
                    owner_id=owner.id,
                    cohort_id=cohort.id,
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                    key_hint="sk-slaif-browser-hint",
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=1000,
                    request_limit_total=100,
                    allow_all_models=True,
                    allow_all_endpoints=True,
                    created_by_admin_user_id=admin.id,
                )
                provider = await ProviderConfigsRepository(session).create_provider_config(
                    provider=f"browser-openai-{suffix}",
                    display_name="Browser OpenAI",
                    kind="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    enabled=True,
                    timeout_seconds=120,
                    max_retries=1,
                    notes="safe browser provider note",
                )
                route = await ModelRoutesRepository(session).create_model_route(
                    requested_model=f"browser-gpt-{suffix}",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider=provider.provider,
                    upstream_model=f"browser-upstream-{suffix}",
                    priority=10,
                    enabled=True,
                    visible_in_models=True,
                    supports_streaming=True,
                    capabilities={"browser": True},
                    notes="safe browser route note",
                )
                pricing = await PricingRulesRepository(session).create_pricing_rule(
                    provider=provider.provider,
                    upstream_model=route.upstream_model,
                    endpoint=route.endpoint,
                    currency="EUR",
                    input_price_per_1m=Decimal("0.100000000"),
                    cached_input_price_per_1m=Decimal("0.050000000"),
                    output_price_per_1m=Decimal("0.200000000"),
                    reasoning_price_per_1m=None,
                    request_price=None,
                    pricing_metadata={"source": "browser-smoke"},
                    valid_from=now - timedelta(days=1),
                    valid_until=None,
                    enabled=True,
                    source_url="https://pricing.example.org/browser",
                    notes="safe browser pricing note",
                )
                fx = await FxRatesRepository(session).create_fx_rate(
                    base_currency="USD",
                    quote_currency="EUR",
                    rate=Decimal("0.920000000"),
                    valid_from=now - timedelta(days=1),
                    valid_until=None,
                    source=f"browser-smoke-{suffix}",
                )
                usage = await UsageLedgerRepository(session).create_success_record(
                    request_id=f"req_browser_{suffix}",
                    gateway_key_id=key.id,
                    owner_id=owner.id,
                    institution_id=institution.id,
                    cohort_id=cohort.id,
                    owner_email_snapshot=owner.email,
                    owner_name_snapshot=owner.name,
                    owner_surname_snapshot=owner.surname,
                    institution_name_snapshot=institution.name,
                    cohort_name_snapshot=cohort.name,
                    endpoint="/v1/chat/completions",
                    provider=provider.provider,
                    requested_model=route.requested_model,
                    resolved_model=route.upstream_model,
                    upstream_request_id=f"upstream-browser-{suffix}",
                    streaming=False,
                    http_status=200,
                    prompt_tokens=3,
                    completion_tokens=5,
                    total_tokens=8,
                    estimated_cost_eur=Decimal("0.010000000"),
                    actual_cost_eur=Decimal("0.008000000"),
                    native_currency="EUR",
                    usage_raw={"prompt": PROMPT_TEXT, "token_hash": "secret"},
                    response_metadata={
                        "safe": "browser-metadata-ok",
                        "response_body": COMPLETION_TEXT,
                        "authorization": "Authorization: Bearer browser-secret",
                    },
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=100),
                    latency_ms=100,
                )
                audit = await AuditRepository(session).add_audit_log(
                    admin_user_id=admin.id,
                    action="key.created",
                    entity_type="gateway_key",
                    entity_id=key.id,
                    old_values={"token_hash": "secret"},
                    new_values={"safe": "browser-audit-ok", "provider_api_key": FAKE_PROVIDER_KEY_VALUE},
                    ip_address="127.0.0.1",
                    user_agent="playwright",
                    request_id=f"req_audit_browser_{suffix}",
                    note="safe browser audit note",
                )
                secret = OneTimeSecret(
                    purpose="gateway_key_email",
                    owner_id=owner.id,
                    gateway_key_id=key.id,
                    encrypted_payload="encrypted_payload_browser_secret",
                    nonce="nonce_browser_secret",
                    encryption_key_version=1,
                    expires_at=now + timedelta(hours=1),
                    status="pending",
                )
                session.add(secret)
                await session.flush()
                email_delivery = await EmailDeliveriesRepository(session).create_email_delivery(
                    recipient_email=owner.email,
                    subject="Browser gateway key delivery",
                    template_name="gateway_key_email",
                    owner_id=owner.id,
                    gateway_key_id=key.id,
                    one_time_secret_id=secret.id,
                    status="pending",
                )
                return {
                    "admin_email": admin.email,
                    "key_id": key.id,
                    "public_key_id": key.public_key_id,
                    "owner_id": owner.id,
                    "institution_id": institution.id,
                    "cohort_id": cohort.id,
                    "provider_id": provider.id,
                    "route_id": route.id,
                    "pricing_id": pricing.id,
                    "fx_id": fx.id,
                    "usage_id": usage.id,
                    "audit_id": audit.id,
                    "email_id": email_delivery.id,
                }
    finally:
        await engine.dispose()


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY=FAKE_PROVIDER_KEY_VALUE,
        OPENROUTER_API_KEY=FAKE_OPENROUTER_KEY_VALUE,
        ENABLE_EMAIL_DELIVERY=False,
    )


def _assert_no_secret_output(html: str) -> None:
    for forbidden in (
        "token_hash",
        "encrypted_payload",
        "nonce",
        "nonce_browser_secret",
        "password_hash",
        "session_token",
        FAKE_PROVIDER_KEY_VALUE,
        FAKE_OPENROUTER_KEY_VALUE,
        FAKE_PLAINTEXT_GATEWAY_KEY,
        PROMPT_TEXT,
        COMPLETION_TEXT,
        "Authorization: Bearer",
        "provider_api_key",
    ):
        assert forbidden not in html


def _assert_page_ok(page: object, url: str, expected: str) -> str:
    response = page.goto(url)
    assert response is not None
    assert response.status == 200
    html = page.content()
    assert expected in html
    _assert_no_secret_output(html)
    return html


def _assert_csrf_controls(page: object, minimum_count: int = 1) -> None:
    assert page.locator('input[name="csrf_token"]').count() >= minimum_count


@pytest.mark.playwright
def test_admin_dashboard_browser_smoke() -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    data = asyncio.run(_create_dashboard_data(database_url))

    app = create_app(_settings(database_url))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with _run_uvicorn_server(app, port), _chromium_browser() as browser:
        context = browser.new_context(base_url=base_url)
        page = context.new_page()
        try:
            response = page.goto("/admin/login")
            assert response is not None
            assert response.status == 200
            assert "Admin Login" in page.content()
            _assert_csrf_controls(page)

            page.fill('input[name="email"]', str(data["admin_email"]))
            page.fill('input[name="password"]', ADMIN_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_url("**/admin")

            pages = [
                ("/admin", "Admin Dashboard", 1),
                ("/admin/keys", "Gateway Keys", 1),
                (f"/admin/keys/{data['key_id']}", str(data["public_key_id"]), 7),
                ("/admin/keys/create", "Create Gateway Key", 2),
                ("/admin/owners", "Owners", 1),
                (f"/admin/owners/{data['owner_id']}", "Browser Owner", 1),
                ("/admin/institutions", "Institutions", 1),
                (f"/admin/institutions/{data['institution_id']}", "Browser Institution", 1),
                ("/admin/cohorts", "Cohorts", 1),
                (f"/admin/cohorts/{data['cohort_id']}", "Browser Cohort", 1),
                ("/admin/providers", "Provider Configs", 1),
                ("/admin/providers/new", "Create Provider Config", 2),
                (f"/admin/providers/{data['provider_id']}", "Browser OpenAI", 2),
                (f"/admin/providers/{data['provider_id']}/edit", "Edit Provider Config", 2),
                ("/admin/routes", "Model Routes", 1),
                ("/admin/routes/new", "Create Model Route", 2),
                ("/admin/routes/import", "Route Import Preview", 2),
                (f"/admin/routes/{data['route_id']}", "browser-gpt", 2),
                (f"/admin/routes/{data['route_id']}/edit", "Edit Model Route", 2),
                ("/admin/pricing", "Pricing Rules", 1),
                ("/admin/pricing/new", "Create Pricing Rule", 2),
                ("/admin/pricing/import", "Pricing Import Preview", 2),
                (f"/admin/pricing/{data['pricing_id']}", "browser-upstream", 2),
                (f"/admin/pricing/{data['pricing_id']}/edit", "Edit Pricing Rule", 2),
                ("/admin/fx", "FX Rates", 1),
                ("/admin/fx/new", "Create FX rate", 2),
                (f"/admin/fx/{data['fx_id']}", "USD / EUR", 1),
                (f"/admin/fx/{data['fx_id']}/edit", "Edit FX rate", 2),
                ("/admin/usage", "Usage Ledger", 1),
                (f"/admin/usage/{data['usage_id']}", "browser-metadata-ok", 1),
                ("/admin/audit", "Audit Log", 1),
                (f"/admin/audit/{data['audit_id']}", "browser-audit-ok", 1),
                ("/admin/email-deliveries", "Email Deliveries", 1),
                (f"/admin/email-deliveries/{data['email_id']}", "Browser gateway key delivery", 3),
            ]
            for path, expected, csrf_count in pages:
                _assert_page_ok(page, path, expected)
                _assert_csrf_controls(page, minimum_count=csrf_count)

            _assert_page_ok(page, "/admin", "Admin Dashboard")
            page.click('form[action="/admin/logout"] button[type="submit"]')
            page.wait_for_url("**/admin/login")
            assert "Admin Login" in page.content()
        finally:
            context.close()
