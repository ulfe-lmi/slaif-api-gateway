"""212-a GUI Codex compatibility: real-Chromium browser qualification.

Real browser, real uvicorn app, owned PostgreSQL (the ``owned_pg_url``
fixture is reused directly - this module is the SOLE PG owner of the
run; no outer runner container, no ambient TEST_DATABASE_URL, no
proxy-mocked success: every navigation, form, download, and DB oracle
goes through the actual HTTP handlers and the real DB).

Cases (file order is significant - one key per scenario family):

- real login -> dashboard Operations -> Compatibility index (entry
  link, preset table with exact identity strings, startup identity);
- keys list -> key detail -> Compatibility entry -> the key page
  (pin facts, finite options);
- the seeded READY Codex route: index qualification row (ready
  badge, canonical artifact links) and the route-detail
  Compatibility entry + Credential-free Codex artifacts section,
  with a real authenticated artifact download (credential-free
  TOML, no-store);
- module upgrade through the ACTUAL keyboard flow (select/reason/
  submit/check), review facts, confirm + apply, reload the persisted
  binding, and the exact repeat as a no-op - with an independent DB
  oracle (exact tuple, ONE session-actor/reason audit, full-row
  stability digest);
- preset inspect + credential-free authenticated JSON download
  (exact document, no-store, no credential shapes or CLI paths);
- 0.162 data-profile migration to the real bootstrap ACTIVE profile
  (one audited update, persisted identity);
- the no-JS rollback flow (JS disabled: the same native forms work
  end to end);
- narrow (no horizontal overflow) + desktop captures.

Safety: synthetic fixture keys only (never forwarded); no real
provider/Codex call, respx mock, or ledger row.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import socket
import threading
import time
import uuid
from collections.abc import Iterator
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
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import (
    ProviderConfigsRepository,
)
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_CODEX_PROFILE_ID,
    build_codex_profile_declaration,
    get_codex_profile,
)
from slaif_gateway.main import create_app
from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE_ID
from slaif_gateway.modules.codex_profile_data import (
    list_codex_presets,
    read_codex_preset,
)
from slaif_gateway.services.codex_module_upgrade import (
    CODEX_0149_V4_CLIENT_MODULE,
    UPGRADE_TARGET_CLIENT_MODULES,
    get_client_module,
)
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
)

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif212")
BASE = "/admin/operations/compatibility"

PIN_0149_V4 = dict(CODEX_0149_V4_CLIENT_MODULE)
PIN_0149_V5 = dict(UPGRADE_TARGET_CLIENT_MODULES["0149-v5"])
PIN_0162_V1 = dict(UPGRADE_TARGET_CLIENT_MODULES["0162-v1"])

REASON_UPGRADE = "212 browser module upgrade apply"
REASON_MIGRATE = "212 browser profile migrate active"
REASON_NOJS_ROLLBACK = "212 browser nojs rollback apply"

COMPAT_ACTIONS = (
    "codex_client_module_upgraded",
    "codex_client_module_rolled_back",
    "codex_key_profile_migrated",
)


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
        # Numeric loopback: the credential-free artifact renderer
        # refuses non-numeric "localhost" HTTP base URLs, and a
        # ready row must offer its artifact links.
        PUBLIC_BASE_URL="http://127.0.0.1:8000/v1",
    )


# ---------------------------------------------------------------------------
# Seed (fixture data only: synthetic keys, never forwarded)
# ---------------------------------------------------------------------------


async def _seed_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    quota = dict(
        cost_limit_eur=Decimal("42.5"),
        token_limit_total=1234567,
        request_limit_total=89,
    )
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui212b-{suffix}@example.org",
                    display_name="212 Compat Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner = await OwnersRepository(session).create_owner(
                    name="212b",
                    surname=f"Compat-{suffix}",
                    email=f"gui212b-owner-{suffix}@example.org",
                )
                keys = GatewayKeysRepository(session)

                async def _key(name: str, pin: dict[str, str]):
                    return await keys.create_gateway_key_record(
                        public_key_id=f"212b-{name}-{suffix}",
                        token_hash=f"212b-{name}-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        valid_from=now - timedelta(days=1),
                        valid_until=now + timedelta(days=365),
                        status="active",
                        created_by_admin_user_id=admin.id,
                        metadata_json={
                            "responses_policy": {
                                "client_module": dict(pin),
                                "212b_sentinel": {"kept": name},
                            }
                        },
                        **quota,
                    )

                module_key = await _key("mod", PIN_0149_V4)
                profile_key = await _key("prof", PIN_0162_V1)

                # ONE stored ready Codex route: the registered
                # qwen38-27b 0.162 profile (provider_kind
                # openai_compatible is DB-valid, no provider-slug pin,
                # a single /v1/responses endpoint, client-local
                # compaction, self-contained artifacts plus model
                # catalog).  Synthetic provider/route/pricing only -
                # no provider HTTP and no requalification.
                providers = ProviderConfigsRepository(session)
                codex_provider = f"syn212b-{suffix}"
                await providers.create_provider_config(
                    provider=codex_provider,
                    display_name="Synthetic 212b Codex Provider",
                    kind="openai_compatible",
                    base_url="https://syn212b.example/v1",
                    api_key_env_var="GUI212B_SYN212_KEY",
                    enabled=True,
                    timeout_seconds=300,
                    max_retries=0,
                    notes=None,
                )
                codex_profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
                assert codex_profile is not None
                codex_model = codex_profile.public_model
                routes = ModelRoutesRepository(session)
                pricing = PricingRulesRepository(session)
                codex_route = await routes.create_model_route(
                    requested_model=codex_profile.public_model,
                    provider=codex_provider,
                    upstream_model=codex_profile.upstream_model,
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
                            "codex_request_envelope": True,
                            "codex_client_tools": True,
                            "codex_streaming_tool_events": True,
                            "codex_encrypted_reasoning_replay": True,
                        },
                        "codex_limits": {
                            "context_window_tokens": codex_profile.context_window_tokens,
                            "default_max_output_tokens": codex_profile.default_max_output_tokens,
                            "max_output_tokens": codex_profile.max_output_tokens,
                        },
                        "codex_profile": build_codex_profile_declaration(
                            QWEN38_CODEX_PROFILE_ID
                        ),
                    },
                    notes="212b browser codex responses route",
                )
                await pricing.create_pricing_rule(
                    provider=codex_provider,
                    upstream_model=codex_profile.upstream_model,
                    endpoint="/v1/responses",
                    valid_from=now - timedelta(days=1),
                    currency="EUR",
                    input_price_per_1m=Decimal("1.000000000"),
                    cached_input_price_per_1m=Decimal("0.250000000"),
                    output_price_per_1m=Decimal("1.000000000"),
                    reasoning_price_per_1m=Decimal("2.000000000"),
                    request_price=Decimal("0.000000000"),
                    pricing_metadata={
                        "codex_accounting": {
                            "long_context_threshold_tokens": 98_304,
                            "long_context_input_multiplier": "2",
                            "long_context_output_multiplier": "2",
                            "cache_write_input_multiplier": "1",
                        }
                    },
                    notes="212b browser codex pricing",
                )
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "module_key": str(module_key.id),
                    "profile_key": str(profile_key.id),
                    "codex_route_id": str(codex_route.id),
                    "codex_model": codex_model,
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# DB oracles (scoped to THIS run's exact seeded key IDs)
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


def _key_state(data: dict[str, Any], key_id: str) -> dict[str, Any]:
    async def _get(session):
        row = (
            (
                await session.execute(
                    select(GatewayKey).where(GatewayKey.id == uuid.UUID(key_id))
                )
            )
            .scalars()
            .first()
        )
        audits = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.entity_type == "gateway_key",
                        AuditLog.entity_id == uuid.UUID(key_id),
                        AuditLog.admin_user_id == uuid.UUID(data["admin_id"]),
                        AuditLog.action.in_(COMPAT_ACTIONS),
                    )
                    .order_by(AuditLog.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "client_module": copy.deepcopy(
                (row.metadata_json or {}).get("responses_policy", {}).get(
                    "client_module"
                )
            ),
            "audits": [
                {"action": r.action, "old": r.old_values, "new": r.new_values,
                 "note": r.note}
                for r in audits
            ],
            "digest": _row_digest_sync(row),
        }

    return _db(data["database_url"], _get)


def _row_digest_sync(row) -> tuple[str, str]:
    """Full-row stability digest from an already-loaded ORM row: every
    gateway_keys column except id/updated_at, plus all metadata except
    the audited responses_policy.client_module path (same excluded set
    as the accepted shared-Core proof)."""
    import hashlib

    from sqlalchemy import inspect as sa_inspect

    excluded = frozenset({"id", "updated_at", "metadata_json"})
    columns = [column.key for column in sa_inspect(GatewayKey).columns]
    raw_columns = {
        key: getattr(row, key) for key in columns if key not in excluded
    }
    metadata = dict(row.metadata_json or {})
    policy = metadata.get("responses_policy")
    if isinstance(policy, dict) and "client_module" in policy:
        metadata["responses_policy"] = {
            k: v for k, v in policy.items() if k != "client_module"
        }
    def _d(values: object) -> str:
        return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()

    return _d(tuple(sorted(raw_columns.items()))), _d(metadata)


def _active_tuple() -> dict[str, str]:
    active = get_client_module(CODEX_0162_CLIENT_MODULE_ID)
    assert active.module_id == CODEX_0162_CLIENT_MODULE_ID
    return {
        "id": CODEX_0162_CLIENT_MODULE_ID,
        "version": str(active.module_version),
        "fixture_sha256": str(active.fixture_sha256),
    }


# ---------------------------------------------------------------------------
# Module environment: owned PG (sole owner) + real uvicorn + Chromium
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compat_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / "browser-212a-lifecycle.json").write_text(
        json.dumps(
            {
                "container": _PG_STATE.get("pg_container"),
                "owner": _PG_STATE.get("pg_owner"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    data = asyncio.run(_seed_data(owned_pg_url))
    data["database_url"] = owned_pg_url
    data["base_url"] = f"http://127.0.0.1:{_free_port()}"
    port = int(data["base_url"].rsplit(":", 1)[1])
    app = create_app(_settings(owned_pg_url))
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(compat_env) -> Iterator[object]:
    """Depends on ``compat_env`` on purpose: the Playwright sync session
    runs an asyncio loop on the main thread, so PostgreSQL seeding and
    the uvicorn app must complete BEFORE it starts (and the browser
    closes before DB teardown)."""
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


def _keyboard_select(page: object, select_id: str, value: str) -> None:
    """Drive a native select to the exact option with the keyboard."""
    select = page.locator(f"#{select_id}")  # type: ignore[union-attr]
    page.focus(f"#{select_id}")  # type: ignore[attr-defined]
    for _ in range(10):
        if select.input_value() == value:
            return
        page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
    raise AssertionError(f"keyboard select did not reach {value!r}")


# ---------------------------------------------------------------------------
# Cases (file order is significant)
# ---------------------------------------------------------------------------


def test_login_operations_compatibility_index(
    compat_env: dict[str, Any], chromium: object
) -> None:
    data = compat_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)

        # Operations index carries the new Compatibility entry.
        page.goto(f"{data['base_url']}/admin/operations/")  # type: ignore[attr-defined]
        assert (
            page.locator('a[href="/admin/operations/compatibility/"]').count() == 1
        )

        page.goto(f"{data['base_url']}{BASE}")  # type: ignore[attr-defined]
        assert "Codex Compatibility" in page.locator(  # type: ignore[attr-defined]
            "#compatibility-heading"
        ).inner_text()
        # Choose-a-key entry (the existing key workflow owns selection).
        assert page.locator('a[href="/admin/keys"]').count() >= 1
        # Preset table: the real bundled presets with exact identity
        # strings (revision is an identity, not a formatted quantity).
        names = [
            "codex-0.162.1",
            "codex-0.163.0",
            "codex-0.164.0",
        ]
        for name in names:
            assert f"<code>{name}</code>" in page.content()  # type: ignore[attr-defined]
        for revision in ("10", "12", "14"):
            assert f"<code>{revision}</code>" in page.content()  # type: ignore[attr-defined]
        assert f"{BASE}/preset/codex-0.163.0/download" in page.content()  # type: ignore[attr-defined]
        # Startup data identity section is explicit (validated snapshot).
        assert "API startup data identity" in page.content()  # type: ignore[attr-defined]
        assert "snapshot unavailable" not in page.content()  # type: ignore[attr-defined]
        # No filesystem paths leak to the browser.
        assert "app/slaif_gateway" not in page.content()  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]


def test_keys_detail_compatibility_entry(
    compat_env: dict[str, Any], chromium: object
) -> None:
    data = compat_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)

        # The seeded key is reachable from the existing keys list.
        page.goto(f"{data['base_url']}/admin/keys")  # type: ignore[attr-defined]
        assert f"212b-mod-{data['suffix']}" in page.content()  # type: ignore[attr-defined]

        page.goto(f"{data['base_url']}/admin/keys/{data['module_key']}")  # type: ignore[attr-defined]
        compat_link = page.locator(
            f'a[href="{BASE}/key/{data["module_key"]}"]'
        )
        assert compat_link.count() == 1
        compat_link.click()
        page.wait_for_url(f"**{BASE}/key/**")  # type: ignore[attr-defined]

        # Pin facts render the exact current tuple.
        assert PIN_0149_V4["id"] in page.content()  # type: ignore[attr-defined]
        assert PIN_0149_V4["fixture_sha256"] in page.content()  # type: ignore[attr-defined]
        # Finite options for the exact 0149-v4 pin (two legal upgrades).
        select = page.locator("#operation-target-select")  # type: ignore[union-attr]
        assert select.count() == 1
        options = [
            o.get_attribute("value")
            for o in select.locator("option").element_handles()  # type: ignore[union-attr]
        ]
        assert len(options) == 2
        assert set(options) == {"module_upgrade:0149-v5", "module_upgrade:0162-v1"}
    finally:
        page.close()  # type: ignore[attr-defined]


def test_route_detail_compatibility_and_ready_artifacts(
    compat_env: dict[str, Any], chromium: object
) -> None:
    """One stored READY Codex route exercises the index qualification
    row, the route-detail Compatibility entry, and a real
    authenticated credential-free artifact download."""
    data = compat_env
    route_id = str(data["codex_route_id"])
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)

        # Index: the seeded route is a ready declared Codex row with
        # its canonical artifact links (the registered profile is
        # self-contained - no base fragment - and ships a model
        # catalog).
        page.goto(f"{data['base_url']}{BASE}")  # type: ignore[attr-defined]
        index_html = page.content()  # type: ignore[attr-defined]
        assert "Protocol-qualified" in index_html
        assert "No declared Codex routes." not in index_html
        assert "qualification projection is unavailable" not in index_html
        assert f"/admin/routes/{route_id}/codex-profile/profile" in index_html
        assert f"/admin/routes/{route_id}/codex-profile/catalog" in index_html
        assert f"/admin/routes/{route_id}/codex-profile/base" not in index_html

        # Route detail: Compatibility entry + artifact section, and
        # the metadata-v2 locally-qualified copy for the registered
        # profile.
        page.goto(f"{data['base_url']}/admin/routes/{route_id}")  # type: ignore[attr-defined]
        detail_html = page.content()  # type: ignore[attr-defined]
        assert "Codex compatibility" in detail_html
        assert (
            page.locator('a[href="/admin/operations/compatibility/"]').count()
            >= 1
        )
        assert "Credential-free Codex artifacts" in detail_html
        assert (
            f"Exact registered profile {QWEN38_CODEX_PROFILE_ID}"
            " (metadata v2) is locally qualified"
        ) in detail_html
        assert "Download Codex config" in detail_html
        assert "Download model catalog" in detail_html
        assert "Download base fragment" not in detail_html

        # Real authenticated downloads through the canonical route
        # artifact handlers (shared session cookies): no-store and
        # credential-free TOML and catalog JSON.
        profile_url = f"{data['base_url']}/admin/routes/{route_id}/codex-profile/profile"
        profile_resp = page.request.get(profile_url)  # type: ignore[union-attr]
        assert profile_resp.status == 200
        assert "no-store" in profile_resp.headers.get("cache-control", "")
        profile_toml = profile_resp.text()
        assert f'model = "{data["codex_model"]}"' in profile_toml
        assert "[features]" in profile_toml
        assert "sk-" not in profile_toml
        assert "Bearer" not in profile_toml

        catalog_url = f"{data['base_url']}/admin/routes/{route_id}/codex-profile/catalog"
        catalog_resp = page.request.get(catalog_url)  # type: ignore[union-attr]
        assert catalog_resp.status == 200
        assert "no-store" in catalog_resp.headers.get("cache-control", "")
        catalog_body = catalog_resp.text()
        assert '"models"' in catalog_body
        assert data["codex_model"] in catalog_body
        assert "sk-" not in catalog_body
        assert "Bearer" not in catalog_body
    finally:
        page.close()  # type: ignore[attr-defined]


def test_module_upgrade_download_then_review_apply_repeat(
    compat_env: dict[str, Any], chromium: object
) -> None:
    """Canonical preset download while the key form stays displayed,
    then the ACTUAL keyboard form flow, persisted reload, and the exact
    repeat as a browser-context HTTP POST of the ORIGINAL token."""
    # The ready route's canonical profile/catalog artifacts are
    # downloaded alongside the preset in the same phase (read-only
    # attachments: no-store, and the still-displayed key form's CSRF
    # survives both).
    data = compat_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        key_url = f"{data['base_url']}{BASE}/key/{data['module_key']}"
        page.goto(key_url)  # type: ignore[attr-defined]
        before = _key_state(data, data["module_key"])
        assert before["client_module"] == PIN_0149_V4
        assert before["audits"] == []

        # --- canonical attachment download, key form still displayed ---
        name = list(list_codex_presets())[0][0]
        download_url = f"{data['base_url']}{BASE}/preset/{name}/download"
        csrf_before = (
            page.locator('input[name="csrf_token"]').first.get_attribute("value")
        )  # type: ignore[union-attr]
        resp = page.request.get(download_url)  # type: ignore[union-attr]
        assert resp.status == 200
        assert "no-store" in resp.headers.get("cache-control", "")
        # Exact canonical bytes, byte-identical to the strict loader.
        assert resp.body() == read_codex_preset(name).encode("utf-8")
        # The read did NOT rotate the still-visible form CSRF.
        csrf_after = (
            page.locator('input[name="csrf_token"]').first.get_attribute("value")
        )  # type: ignore[union-attr]
        assert csrf_after == csrf_before
        assert csrf_after
        # The key form is still the displayed page (no navigation).
        assert page.url == key_url

        # --- ready-route artifacts, same displayed key form ---
        route_id = str(data["codex_route_id"])
        for artifact_name in ("profile", "catalog"):
            artifact_resp = page.request.get(  # type: ignore[union-attr]
                f"{data['base_url']}/admin/routes/{route_id}"
                f"/codex-profile/{artifact_name}"
            )
            assert artifact_resp.status == 200
            assert "no-store" in artifact_resp.headers.get("cache-control", "")
        # The artifact reads did not rotate the form CSRF either.
        csrf_after_artifacts = (
            page.locator('input[name="csrf_token"]').first.get_attribute("value")
        )  # type: ignore[union-attr]
        assert csrf_after_artifacts == csrf_before
        assert page.url == key_url

        # --- ACTUAL keyboard form flow ---
        _keyboard_select(page, "operation-target-select", "module_upgrade:0149-v5")
        page.focus("#migration-reason")  # type: ignore[attr-defined]
        page.keyboard.type(REASON_UPGRADE)  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        page.wait_for_selector('text=Dry run complete')  # type: ignore[attr-defined]

        # Reviewed facts: exact source/target identity, verbatim reason.
        review_html = page.content()  # type: ignore[attr-defined]
        assert "Reviewed migration" in review_html
        assert PIN_0149_V4["fixture_sha256"] in review_html
        assert PIN_0149_V5["fixture_sha256"] in review_html
        assert REASON_UPGRADE in review_html
        # No visible empty-state text after the real tuple rows.
        assert "No reviewed tuples." not in review_html

        # Capture the ORIGINAL signed token before applying.
        original_token = page.locator(  # type: ignore[union-attr]
            'input[name="review_token"]'
        ).get_attribute("value")
        assert original_token

        # Reviewed source/target + confirmation page, captured before
        # anything is applied (for visual review).
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "212-compat-review-confirmation.png"),
            full_page=True,
        )

        # Keyboard confirm + apply.
        page.focus("#confirm-apply")  # type: ignore[attr-defined]
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        page.click('button:has-text("Apply migration")')  # type: ignore[attr-defined]
        page.wait_for_selector('text=Applied')  # type: ignore[attr-defined]

        # Independent DB oracle: exact tuple + ONE real audit + full-row
        # stability.
        after = _key_state(data, data["module_key"])
        assert after["client_module"] == PIN_0149_V5
        assert len(after["audits"]) == 1
        entry = after["audits"][0]
        assert entry["action"] == "codex_client_module_upgraded"
        assert entry["note"] == REASON_UPGRADE
        assert entry["old"] == {"client_module": PIN_0149_V4}
        assert entry["new"] == {"client_module": PIN_0149_V5}
        assert after["digest"] == before["digest"]

        # Reload the key page: the persisted binding is displayed.
        page.goto(key_url)  # type: ignore[attr-defined]
        assert PIN_0149_V5["fixture_sha256"] in page.content()  # type: ignore[attr-defined]

        # The exact repeat is a browser-context HTTP POST of the
        # ORIGINAL token with the current valid CSRF (the finite UI
        # correctly no longer offers the applied upgrade from the v5
        # pin, so the repeat is not another UI selection).
        current_csrf = (
            page.locator('input[name="csrf_token"]').first.get_attribute("value")
        )  # type: ignore[union-attr]
        repeat = page.request.post(  # type: ignore[union-attr]
            f"{data['base_url']}{BASE}/key/{data['module_key']}/apply",
            form={
                "csrf_token": current_csrf,
                "review_token": original_token,
                "confirm_apply": "1",
            },
        )
        assert repeat.status == 200
        assert "Already at target" in repeat.text()
        repeat_state = _key_state(data, data["module_key"])
        assert repeat_state["client_module"] == PIN_0149_V5
        assert len(repeat_state["audits"]) == 1
    finally:
        page.close()  # type: ignore[attr-defined]


def test_preset_inspect_exact_document(
    compat_env: dict[str, Any], chromium: object
) -> None:
    data = compat_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}{BASE}")  # type: ignore[attr-defined]
        name, _path, profile = list(list_codex_presets())[0]
        page.click(f'a[href="{BASE}/preset/{name}"]')  # type: ignore[attr-defined]
        page.wait_for_url(f"**{BASE}/preset/{name}")  # type: ignore[attr-defined]

        # The displayed document is the EXACT strict-loader bytes
        # (schema-agnostic: whatever the current shipped preset
        # schema is, the bytes are unmodified).
        document_text = (
            page.locator('pre.config-json code').first.inner_text()
        )  # type: ignore[union-attr]
        assert document_text == read_codex_preset(name)
        # Credential-free and free of CLI filesystem paths.
        assert "sk-" not in document_text
        assert "Bearer" not in document_text
        assert "app/slaif_gateway" not in document_text
        assert "/tmp/" not in document_text
        # Current loader facts render in the safe-facts list (revision
        # and digest as exact identity strings).
        facts = profile.to_facts()
        assert str(facts["revision"]) in page.content()  # type: ignore[attr-defined]
        assert str(facts["digest"]) in page.content()  # type: ignore[attr-defined]
        # The index revision cell shows the exact string, not a
        # formatted quantity (re-verify on the index page).
        page.goto(f"{data['base_url']}{BASE}")  # type: ignore[attr-defined]
        assert f"<code>{facts['revision']}</code>" in page.content()  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]


def test_profile_migration_active_apply(
    compat_env: dict[str, Any], chromium: object
) -> None:
    data = compat_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        key_url = f"{data['base_url']}{BASE}/key/{data['profile_key']}"
        page.goto(key_url)  # type: ignore[attr-defined]
        before = _key_state(data, data["profile_key"])
        assert before["client_module"] == PIN_0162_V1
        active = _active_tuple()

        page.select_option("#operation-target-select", "migrate:active")  # type: ignore[attr-defined]
        page.fill("#migration-reason", REASON_MIGRATE)  # type: ignore[attr-defined]
        page.click('button:has-text("Dry-run and review")')  # type: ignore[attr-defined]
        page.wait_for_selector('text=Dry run complete')  # type: ignore[attr-defined]
        # The review binds the REAL bootstrap active tuple.
        assert active["fixture_sha256"] in page.content()  # type: ignore[attr-defined]

        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.click('button:has-text("Apply migration")')  # type: ignore[attr-defined]
        page.wait_for_selector('text=Applied')  # type: ignore[attr-defined]

        after = _key_state(data, data["profile_key"])
        assert after["client_module"] == active
        assert len(after["audits"]) == 1
        assert (
            after["audits"][0]["action"] == "codex_key_profile_migrated"
        )
        assert after["audits"][0]["note"] == REASON_MIGRATE
        assert after["audits"][0]["old"] == {"client_module": PIN_0162_V1}
        assert after["audits"][0]["new"] == {"client_module": active}
        assert after["digest"] == before["digest"]

        # Reload: the persisted active identity is displayed.
        page.goto(key_url)  # type: ignore[attr-defined]
        assert active["fixture_sha256"] in page.content()  # type: ignore[attr-defined]
        assert f"<code>{active['version']}</code>" in page.content()  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]


def test_nojs_module_rollback_flow(
    compat_env: dict[str, Any], chromium: object
) -> None:
    data = compat_env
    context = chromium.new_context(java_script_enabled=False)  # type: ignore[union-attr]
    page = context.new_page()
    try:
        _login(page, data)
        key_url = f"{data['base_url']}{BASE}/key/{data['module_key']}"
        page.goto(key_url)  # type: ignore[attr-defined]
        before = _key_state(data, data["module_key"])
        assert before["client_module"] == PIN_0149_V5

        # The native form is fully usable without JS.
        select = page.locator("#operation-target-select")  # type: ignore[union-attr]
        assert select.is_enabled()
        select.select_option("module_rollback:0149-v4")  # type: ignore[union-attr]
        page.fill("#migration-reason", REASON_NOJS_ROLLBACK)  # type: ignore[attr-defined]
        page.click('button:has-text("Dry-run and review")')  # type: ignore[attr-defined]
        page.wait_for_selector('text=Dry run complete')  # type: ignore[attr-defined]

        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.click('button:has-text("Apply migration")')  # type: ignore[attr-defined]
        page.wait_for_selector('text=Applied')  # type: ignore[attr-defined]

        after = _key_state(data, data["module_key"])
        assert after["client_module"] == PIN_0149_V4
        # The no-JS rollback adds exactly ONE more real audit.
        assert len(after["audits"]) == len(before["audits"]) + 1
        entry = after["audits"][-1]
        assert entry["action"] == "codex_client_module_rolled_back"
        assert entry["note"] == REASON_NOJS_ROLLBACK
        assert entry["old"] == {"client_module": PIN_0149_V5}
        assert entry["new"] == {"client_module": PIN_0149_V4}
        assert after["digest"] == before["digest"]
    finally:
        context.close()  # type: ignore[union-attr]


def test_narrow_and_desktop_captures(
    compat_env: dict[str, Any], chromium: object
) -> None:
    data = compat_env
    page = chromium.new_page(viewport={"width": 390, "height": 844})  # type: ignore[union-attr]
    try:
        _login(page, data)
        key_url = f"{data['base_url']}{BASE}/key/{data['module_key']}"
        page.goto(key_url)  # type: ignore[attr-defined]
        # No horizontal overflow at the narrow width (scrollbar-aware).
        overflow = page.evaluate(  # type: ignore[attr-defined]
            "document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        assert int(overflow) <= 0
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "212-compat-key-narrow.png"),
            full_page=True,
        )

        # Desktop top + full captures of the same page.
        page.set_viewport_size({"width": 1280, "height": 900})  # type: ignore[attr-defined]
        page.wait_for_timeout(150)  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "212-compat-key-desktop.png"),
            full_page=True,
        )
        # The pin facts remain visible at both widths.
        assert PIN_0149_V4["id"] in page.content()  # type: ignore[attr-defined]

        # Desktop capture of the index (presets + startup identity).
        page.goto(f"{data['base_url']}{BASE}")  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "212-compat-index-desktop.png"),
            full_page=True,
        )

        # Narrow index WITH the populated qualification table.
        page.set_viewport_size({"width": 390, "height": 844})  # type: ignore[union-attr]
        page.wait_for_timeout(150)  # type: ignore[attr-defined]
        assert "Protocol-qualified" in page.content()  # type: ignore[attr-defined]
        narrow_overflow = page.evaluate(  # type: ignore[attr-defined]
            "document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        assert int(narrow_overflow) <= 0
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "212-compat-index-narrow.png"),
            full_page=True,
        )
    finally:
        page.close()  # type: ignore[attr-defined]
