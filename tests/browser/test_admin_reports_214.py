"""214-a GUI grouped reports, pagination and reviewed catalog tools: real-Chromium
browser qualification.

Real browser, real uvicorn app, owned PostgreSQL (the ``owned_pg_url`` fixture is
reused directly - this module is the SOLE PG owner of the run; no ambient
TEST_DATABASE_URL, no proxy-mocked success: every navigation, form, download and
DB oracle goes through the actual HTTP handlers and the real DB).

Cases (file order is significant):

- real login -> the report surfaces reached from the existing Usage list and the
  Operations index;
- all seven grouped summary dimensions render in the real browser;
- complete filter-preserving navigation: a real paged list's SECOND page shows
  offset ordinals, and the shared table sorter renumbers them (offset+1 ..) in
  BOTH directions;
- the safe JSON export: a real form download yields the exact strict-JSON
  attachment (exact raw units, nullable costs, no NaN, no-store/attachment), and
  a valid mutation still succeeds afterwards (the download did not break the
  open session's form flow);
- reviewed matching-model pricing disable through the ACTUAL UI (preview ->
  confirm -> apply -> reload), with an independent DB oracle (only the reviewed
  rows disabled, verbatim per-row audit, unrelated rows unchanged) and an honest
  repeat no-op;
- the legacy route form accepts an older eligible provider BEYOND the 200-row
  choice batch (bounded exact lookup, disabled prep preserved) and refuses an
  unknown provider;
- the NO-JS operator flow: a validation refusal with the no-JS recovery link;
- desktop and narrow captures for visual review.

Safety: synthetic fixture rows only (never forwarded); no real provider/Codex
call, respx mock, or forwarded traffic.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import hashlib
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
from urllib.parse import urlencode

import pytest
import uvicorn
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.api import admin_reports
from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    FxRate,
    GatewayKey,
    ModelRoute,
    PricingRule,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.codex_module_upgrade import (
    CODEX_0149_V4_CLIENT_MODULE,
)
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
)

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif214")
REPORTS = "/admin/reports"

REASON_EXPORT = "214 browser GUI strict-JSON usage export"
REASON_APPLY = "214 browser reviewed pricing disable apply"
REASON_ROUTE = "214 browser older-provider route"

NOW = datetime.now(UTC)


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
    )


# ---------------------------------------------------------------------------
# Seed (fixture data only: synthetic rows, never forwarded)
# ---------------------------------------------------------------------------


def _ledger_row(*, suffix, tag, provider, model, key_id, owner_id, cohort_id, est, act,
                created, owner_name, cohort_name, streaming=False,
                chat_meta=None) -> UsageLedger:
    return UsageLedger(
        request_id=f"req-214b-{tag}-{suffix}",
        gateway_key_id=key_id,
        owner_id=owner_id,
        cohort_id=cohort_id,
        owner_name_snapshot=owner_name,
        owner_surname_snapshot="214",
        owner_email_snapshot=None,
        cohort_name_snapshot=cohort_name,
        endpoint="/v1/chat/completions" if streaming else "/v1/responses",
        provider=provider,
        requested_model=model,
        resolved_model=model,
        streaming=streaming,
        success=True,
        accounting_status="finalized",
        prompt_tokens=1000,
        completion_tokens=500,
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        estimated_cost_eur=est,
        actual_cost_eur=act,
        usage_raw={},
        response_metadata=dict(chat_meta or {}),
        started_at=created,
        finished_at=created,
        created_at=created,
    )


async def _seed_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui214b-{suffix}@example.org",
                    display_name="214 Reports Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner_a = await OwnersRepository(session).create_owner(
                    name="OwnerA", surname=f"214-{suffix}",
                    email=f"gui214b-ownera-{suffix}@example.org",
                )
                owner_b = await OwnersRepository(session).create_owner(
                    name="OwnerB", surname=f"214-{suffix}",
                    email=f"gui214b-ownerb-{suffix}@example.org",
                )
                cohort_a = await CohortsRepository(session).create_cohort(name=f"cohort-a-{suffix}")
                cohort_b = await CohortsRepository(session).create_cohort(name=f"cohort-b-{suffix}")

                keys_repo = GatewayKeysRepository(session)

                async def _key(tag: str, *, owner, cohort) -> GatewayKey:
                    return await keys_repo.create_gateway_key_record(
                        public_key_id=f"214b-{tag}-{suffix}",
                        token_hash=f"214b-{tag}-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        valid_from=NOW - timedelta(days=10),
                        valid_until=NOW + timedelta(days=3650),
                        status="active",
                        created_by_admin_user_id=admin.id,
                        allow_all_models=False,
                        allowed_models=[f"214b-model-{suffix}"],
                        allow_all_endpoints=False,
                        allowed_endpoints=["/v1/responses"],
                        cost_limit_eur=Decimal("42.5"),
                        token_limit_total=1234567,
                        request_limit_total=89,
                    )

                key_a1 = await _key("keya1", owner=owner_a, cohort=cohort_a)
                key_a2 = await _key("keya2", owner=owner_a, cohort=cohort_a)
                key_b1 = await _key("keyb1", owner=owner_b, cohort=cohort_b)
                key_b2 = await _key("keyb2", owner=owner_b, cohort=cohort_b)
                key_b3 = await _key("keyb3", owner=owner_b, cohort=cohort_b)
                # Nonzero used/reserved counters + legal client-module metadata +
                # one real reservation row (the 213 preservation-sentinel pattern).
                key_a1.cost_used_eur = Decimal("7.25")
                key_a1.tokens_used_total = 101
                key_a1.requests_used_total = 7
                key_a1.metadata_json = {
                    "responses_policy": {"client_module": dict(CODEX_0149_V4_CLIENT_MODULE)},
                    "214b_sentinel": {"kept": f"214b-policy-{suffix}"},
                }
                session.add(
                    QuotaReservation(
                        id=uuid.uuid4(),
                        gateway_key_id=key_a1.id,
                        request_id=f"req-214b-resv-{suffix}",
                        endpoint="/v1/responses",
                        requested_model=f"214b-model-{suffix}",
                        provider="prov-a",
                        reserved_cost_eur=Decimal("0.05"),
                        reserved_tokens=13,
                        reserved_requests=2,
                        status="pending",
                        expires_at=NOW + timedelta(days=1),
                    )
                )

                chat_a = {
                    "streaming_live_burn_enabled": True,
                    "streaming_live_burn_triggered": True,
                    "streaming_live_burn_stop_reason": "cost",
                    "estimated_tokens_at_stop": 100,
                    "estimated_cost_eur_at_stop": "1.50",
                    "final_provider_usage_available": True,
                }
                chat_b = {
                    "streaming_live_burn_enabled": True,
                    "streaming_live_burn_triggered": True,
                    "streaming_live_burn_stop_reason": "tokens",
                    "estimated_tokens_at_stop": 200,
                    "estimated_cost_eur_at_stop": "2.00",
                    "final_provider_usage_available": False,
                }

                def _row(tag, provider, model, key, owner, cohort, est, act, created, **kw):
                    return _ledger_row(
                        suffix=suffix, tag=tag, provider=provider, model=model,
                        key_id=key.id, owner_id=owner.id, cohort_id=cohort.id,
                        est=est, act=act, created=created,
                        owner_name=owner.name, cohort_name=cohort.name, **kw,
                    )

                ledger_rows = [
                    _row("a1", "prov-a", "model-a", key_a1, owner_a, cohort_a, Decimal("10"), Decimal("8"), NOW - timedelta(hours=4), streaming=True, chat_meta=chat_a),
                    _row("a2", "prov-a", "model-a", key_a2, owner_a, cohort_a, Decimal("20"), Decimal("18"), NOW - timedelta(hours=5), streaming=True, chat_meta=chat_b),
                    _row("a3", "prov-a", "model-a2", key_a1, owner_a, cohort_a, Decimal("5.5"), Decimal("5.5"), NOW - timedelta(hours=7)),
                    _row("b1", "prov-b", "model-b", key_b1, owner_b, cohort_b, Decimal("30"), Decimal("25"), NOW - timedelta(hours=6)),
                    _row("b2", "prov-b", "model-b2", key_b2, owner_b, cohort_b, Decimal("7"), Decimal("6"), NOW - timedelta(hours=8)),
                    _row("c1", "prov-c", "model-c", key_b2, owner_b, cohort_b, Decimal("1"), Decimal("1"), NOW - timedelta(hours=20)),
                    _row("c2", "prov-c", "model-c", key_b3, owner_b, cohort_b, Decimal("2"), Decimal("2"), NOW - timedelta(hours=20)),
                    _row("d", "prov-d", "model-d", key_b1, owner_b, cohort_b, Decimal("40"), None, NOW - timedelta(days=3)),
                    _row("m", "prov-missing", "model-m", key_a1, owner_a, cohort_a, None, None, NOW - timedelta(hours=2)),
                    _row("z", "prov-zero", "model-z", key_a1, owner_a, cohort_a, Decimal("0"), Decimal("0"), NOW - timedelta(hours=1)),
                    _row("x1", "prov-mixed", "model-x", key_a2, owner_a, cohort_a, Decimal("5"), Decimal("3"), NOW - timedelta(hours=3)),
                    _row("x2", "prov-mixed", "model-x", key_a2, owner_a, cohort_a, None, None, NOW - timedelta(hours=3)),
                    _row("tiea", "prov-tiea", "model-tie", key_a1, owner_a, cohort_a, Decimal("3"), Decimal("3"), NOW - timedelta(hours=9)),
                    _row("tieb", "prov-tieb", "model-tie", key_b1, owner_b, cohort_b, Decimal("4"), Decimal("4"), NOW - timedelta(hours=9)),
                ]
                for row in ledger_rows:
                    session.add(row)

                # Reviewed pricing disable scope: pmain (2 enabled rows) plus one
                # unreviewed rule that must stay enabled.
                pricing_repo = PricingRulesRepository(session)

                async def _pricing(provider, model, *, days_ago: int = 1, enabled: bool = True) -> PricingRule:
                    return await pricing_repo.create_pricing_rule(
                        provider=provider,
                        upstream_model=model,
                        valid_from=NOW - timedelta(days=days_ago),
                        endpoint="/v1/chat/completions",
                        currency="USD",
                        input_price_per_1m=Decimal("1"),
                        output_price_per_1m=Decimal("2"),
                        pricing_metadata={"policy": f"{provider}-{suffix}"},
                        enabled=enabled,
                    )

                pm1 = await _pricing("pmain", "mmain", days_ago=1)
                pm2 = await _pricing("pmain", "mmain", days_ago=2)
                po1 = await _pricing("ppolicy", "mpolicy")

                # One effective FX rate (EUR -> USD) for the present lookup.
                session.add(
                    FxRate(
                        id=uuid.uuid4(),
                        base_currency="EUR",
                        quote_currency="USD",
                        rate=Decimal("1.10"),
                        valid_from=NOW - timedelta(days=1),
                        valid_until=None,
                        source="214b-test-fx",
                    )
                )

                # 201 provider configs: 200 alphabetically-first filler slugs plus
                # one target slug that sorts AFTER all of them, so the target is
                # BEYOND the legacy list_providers(limit=200) choice batch but is a
                # real, exact-lookup-eligible provider.
                provider_repo = ProviderConfigsRepository(session)
                for i in range(200):
                    slug = f"filler{i:03d}"
                    await provider_repo.create_provider_config(
                        provider=slug,
                        display_name=f"Filler {i:03d}",
                        base_url="https://filler.example.invalid/v1",
                        api_key_env_var="FILLER_API_KEY",
                    )
                target_slug = f"z214target-{suffix}"
                await provider_repo.create_provider_config(
                    provider=target_slug,
                    display_name="214b older target provider",
                    base_url="https://target.example.invalid/v1",
                    api_key_env_var="TARGET_API_KEY",
                )

                await session.flush()

                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "key_a1": str(key_a1.id),
                    "keys": [str(k.id) for k in (key_a1, key_a2, key_b1, key_b2, key_b3)],
                    "pricing": {"pmain": [str(pm1.id), str(pm2.id)], "ppolicy": str(po1.id)},
                    "ledger_count": len(ledger_rows),
                    "target_provider": target_slug,
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# DB oracles (Playwright owns the main-thread loop -> run in a worker thread)
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


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _model_digest(rows: list[Any], model: type, exclude: frozenset[str]) -> str:
    columns = [attr.key for attr in sa_inspect(model).column_attrs if attr.key not in exclude]
    records = [
        {c: _jsonable(getattr(row, c)) for c in columns}
        for row in sorted(rows, key=lambda r: str(r.id))
    ]
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot(data: dict[str, Any]) -> dict[str, str]:
    url = data["database_url"]

    async def _run(session):
        keys = (await session.execute(select(GatewayKey))).scalars().all()
        ledger = (await session.execute(select(UsageLedger))).scalars().all()
        quota = (await session.execute(select(QuotaReservation))).scalars().all()
        audit = (await session.execute(select(AuditLog))).scalars().all()
        return {
            "keys": _model_digest(list(keys), GatewayKey, frozenset()),
            "ledger": _model_digest(list(ledger), UsageLedger, frozenset()),
            "quota": _model_digest(list(quota), QuotaReservation, frozenset()),
            "audit": _model_digest(list(audit), AuditLog, frozenset()),
        }

    return _db(url, _run)


def _pricing_enabled_updated(data: dict[str, Any]) -> dict[str, tuple[bool, str]]:
    url = data["database_url"]

    async def _run(session):
        rows = (await session.execute(select(PricingRule))).scalars().all()
        return {str(r.id): (bool(r.enabled), r.updated_at.isoformat()) for r in rows}

    return _db(url, _run)


def _pricing_enabled(data: dict[str, Any], rule_id: str) -> bool:
    url = data["database_url"]

    async def _run(session):
        row = await session.get(PricingRule, uuid.UUID(rule_id))
        assert row is not None, rule_id
        return bool(row.enabled)

    return _db(url, _run)


def _audits(data: dict[str, Any], *, action: str | None = None) -> list[Any]:
    url = data["database_url"]

    async def _run(session):
        stmt = select(AuditLog)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        rows = (await session.execute(stmt)).scalars().all()
        return sorted(rows, key=lambda r: str(r.id))

    return _db(url, _run)


def _routes_by_model(data: dict[str, Any], requested_model: str) -> list[Any]:
    url = data["database_url"]

    async def _run(session):
        rows = (
            (await session.execute(select(ModelRoute).where(ModelRoute.requested_model == requested_model)))
            .scalars().all()
        )
        return list(rows)

    return _db(url, _run)


# ---------------------------------------------------------------------------
# Module environment: owned PG (sole owner) + real uvicorn + Chromium
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reports_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / "browser-214a-lifecycle.json").write_text(
        json.dumps({"container": _PG_STATE.get("pg_container"), "owner": _PG_STATE.get("pg_owner")}, indent=2),
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
def chromium(reports_env) -> Iterator[object]:
    """Depends on ``reports_env`` on purpose: the Playwright sync session runs an
    asyncio loop on the main thread, so PostgreSQL seeding and the uvicorn app
    must complete BEFORE it starts (and the browser closes before DB teardown)."""
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


def _form_csrf(page: object) -> str:
    """The current session CSRF rendered in a page form."""
    return page.locator('input[name="csrf_token"]').first.get_attribute("value")  # type: ignore[union-attr]


def _qurl(base: str, path: str, **params: object) -> str:
    """Build an absolute URL with a query string (Playwright goto has no params)."""
    query = urlencode({k: str(v) for k, v in params.items()})
    return f"{base}{path}?{query}" if query else f"{base}{path}"


def _ordinal_cells(page: object, table_selector: str = "table[data-sortable]") -> list[str]:
    """The displayed logical ordinals (first cell of each data row)."""
    return [
        cell.strip()
        for cell in page.locator(f"{table_selector} tbody tr td.row-ordinal").all_inner_texts()  # type: ignore[union-attr]
    ]


def _summary_group_rows(page: object) -> list[str]:
    """The group labels (row headers) of the rendered summary tbody."""
    return page.locator("table[data-sortable] tbody th[scope='row']").all_inner_texts()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Cases (file order is significant)
# ---------------------------------------------------------------------------


def test_01_login_and_report_navigation(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)

        # From the existing Usage list: the report surface is linked in.
        page.goto(f"{data['base_url']}/admin/usage")  # type: ignore[attr-defined]
        usage_link = page.locator('a[href="/admin/reports/"]')
        assert usage_link.count() >= 1, "Usage list must link to the reports surface"
        usage_link.first.click()
        page.wait_for_url(f"**{REPORTS}/")  # type: ignore[attr-defined]
        assert "Usage summary report" in page.inner_text("body")  # type: ignore[attr-defined]

        # From the Operations index: the reports entry is linked in.
        page.goto(f"{data['base_url']}/admin/operations/")  # type: ignore[attr-defined]
        ops_link = page.locator('a[href="/admin/reports/"]')
        assert ops_link.count() >= 1, "Operations index must link to the reports surface"
        page.locator('a[href="/admin/reports/pricing-disable"]').first.is_visible()
        page.locator('a[href="/admin/reports/fx-lookup"]').first.is_visible()
    finally:
        page.close()  # type: ignore[union-attr]


def test_02_summary_seven_dimensions_render(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        expected = {
            "provider": "prov-a",
            "model": "model-a",
            "provider_model": "prov-a / model-a",
            "owner": "OwnerA 214",
            "cohort": f"cohort-a-{data['suffix']}",
            "key": data["key_a1"],
            "day": (NOW - timedelta(days=3)).date().isoformat(),
        }
        for dim, label in expected.items():
            page.goto(_qurl(data["base_url"], f"{REPORTS}/", group_by=dim, limit=100))  # type: ignore[attr-defined]
            assert page.locator("table[data-sortable]").count() == 1, dim
            labels = _summary_group_rows(page)
            assert label in labels, (dim, label, labels)
            # The scope line reports the accepted bounded source row count.
            assert str(data["ledger_count"]) in page.inner_text("body")  # type: ignore[attr-defined]
    finally:
        page.close()  # type: ignore[attr-defined]


def test_03_usage_list_second_page_sort_offset_ordinals(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        # 14 ledger rows at limit=10 -> a real second page (offset 10, 4 rows).
        page.goto(_qurl(data["base_url"], "/admin/usage", limit=10, offset=10))  # type: ignore[attr-defined]
        page.wait_for_selector("table[data-sortable]")  # type: ignore[attr-defined]
        assert page.locator("table[data-sortable]").get_attribute("data-ordinal-offset") == "10"
        # Initial business order: the page ordinals continue from offset+1.
        assert _ordinal_cells(page) == ["11", "12", "13", "14"]

        # Sort the Request ID column ascending, then descending: the shared
        # sorter renumbers ONLY the positional values from offset+1 in both
        # directions (never 1..N, never touching the data cells).
        sortable_header = page.locator("table[data-sortable] thead th.ts-col a.ts-link").first
        sortable_header.click()
        assert _ordinal_cells(page) == ["11", "12", "13", "14"]
        sortable_header.click()
        assert _ordinal_cells(page) == ["11", "12", "13", "14"]
    finally:
        page.close()  # type: ignore[union-attr]


def test_04_export_download_then_valid_mutation(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        page.goto(f"{data['base_url']}{REPORTS}/export")  # type: ignore[attr-defined]
        csrf = _form_csrf(page)
        page.fill("#export-reason", REASON_EXPORT)  # type: ignore[attr-defined]
        page.check("#export-confirm")  # type: ignore[union-attr]
        with page.expect_download() as download_info:  # type: ignore[attr-defined]
            page.click('form[action="/admin/reports/export"] button[type="submit"]')  # type: ignore[attr-defined]
        download = download_info.value  # type: ignore[union-attr]
        content = Path(download.path()).read_text("utf-8")  # type: ignore[union-attr]
        assert "NaN" not in content
        payload = json.loads(content)
        assert payload["scope"]["row_count"] == data["ledger_count"]
        assert len(payload["rows"]) == data["ledger_count"]
        by_request = {row["request_id"]: row for row in payload["rows"]}
        a1 = by_request[f"req-214b-a1-{data['suffix']}"]
        assert a1["estimated_cost_eur"] == "10.000000000"
        assert a1["actual_cost_eur"] == "8.000000000"
        miss = by_request[f"req-214b-m-{data['suffix']}"]
        assert miss["estimated_cost_eur"] is None

        # A valid mutation AFTER the download: the download is a form-SUBMIT
        # attachment, so the page, its displayed form, and its rendered CSRF
        # are all UNCHANGED. Do NOT re-GET the export page: a full-page
        # render correctly ROTATES the session CSRF.
        assert page.locator('form[action="/admin/reports/export"]').count() == 1
        assert _form_csrf(page) == csrf
        page.fill("#export-reason", REASON_EXPORT + " (second)")  # type: ignore[attr-defined]
        page.check("#export-confirm")  # type: ignore[union-attr]
        with page.expect_download() as download_info2:  # type: ignore[attr-defined]
            page.click('form[action="/admin/reports/export"] button[type="submit"]')  # type: ignore[attr-defined]
        content2 = Path(download_info2.value.path()).read_text("utf-8")  # type: ignore[union-attr]
        assert json.loads(content2)["scope"]["row_count"] == data["ledger_count"]
        # Each export is audited with the session actor + verbatim reason.
        audits = _audits(data, action="admin_usage_export_json")
        assert any((a.note or "") == REASON_EXPORT for a in audits)
        assert any((a.note or "") == REASON_EXPORT + " (second)" for a in audits)
        assert all(str(a.admin_user_id) == data["admin_id"] for a in audits)
    finally:
        page.close()  # type: ignore[union-attr]


def test_05_pricing_preview_apply_reload_repeat(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        pm = data["pricing"]["pmain"]
        unreviewed = data["pricing"]["ppolicy"]
        before = _snapshot(data)
        before_enabled = _pricing_enabled_updated(data)

        page.goto(f"{data['base_url']}{REPORTS}/pricing-disable")  # type: ignore[attr-defined]
        page.fill("#pd-provider-input", "pmain")  # type: ignore[attr-defined]
        page.fill("#pd-model-input", "mmain")  # type: ignore[attr-defined]
        page.fill("#pd-reason", REASON_APPLY)  # type: ignore[attr-defined]
        page.click('form[action="/admin/reports/pricing-disable/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#pd-review-facts-heading")  # type: ignore[attr-defined]
        body = page.inner_text("body")  # type: ignore[attr-defined]
        assert "2 pricing rule(s)" in body
        assert REASON_APPLY in body  # the reviewed reason, verbatim

        # A deliberate preview wrote nothing.
        assert _snapshot(data) == before

        # Save the ORIGINAL displayed review authority BEFORE any further
        # mutation: the session CSRF and the signed review token rendered
        # in the review page's apply form.
        apply_form = 'form[action="/admin/reports/pricing-disable/apply"]'
        review_csrf = page.locator(f"{apply_form} input[name='csrf_token']").get_attribute("value")  # type: ignore[union-attr]
        review_token = page.locator(f"{apply_form} input[name='review_token']").get_attribute("value")  # type: ignore[union-attr]
        assert review_csrf and review_token

        # Actual metadata mutation BETWEEN preview and apply: a private
        # export attachment written with the SAME session CSRF (same
        # browser context) proves the displayed review form stays valid -
        # background attachments never rotate an open form's CSRF.
        export_resp = page.request.post(  # type: ignore[union-attr]
            f"{data['base_url']}{REPORTS}/export",
            form={
                "csrf_token": review_csrf,
                "confirm_export": "1",
                "reason": REASON_EXPORT,
            },
        )
        assert export_resp.status == 200
        assert "attachment" in export_resp.headers.get("content-disposition", "")
        assert _form_csrf(page) == review_csrf  # the displayed form is unchanged
        assert any(  # the export really wrote its audit row
            (a.note or "") == REASON_EXPORT for a in _audits(data, action="admin_usage_export_json")
        )

        # Submit the UNCHANGED visible apply form with the same displayed
        # CSRF.
        page.check("#pd-confirm-apply")  # type: ignore[union-attr]
        page.click(f"{apply_form} button[type='submit']")  # type: ignore[attr-defined]
        page.wait_for_selector("#pd-result-heading")  # type: ignore[attr-defined]
        assert "pricing rule(s) disabled" in page.inner_text("body")  # type: ignore[attr-defined]

        # Only the reviewed rows changed: `enabled` (+ updated_at) on the two
        # reviewed IDs; every other price column and every unreviewed row stable.
        assert _pricing_enabled(data, pm[0]) is False
        assert _pricing_enabled(data, pm[1]) is False
        assert _pricing_enabled(data, unreviewed) is True
        after_enabled = _pricing_enabled_updated(data)
        for rid, (b_en, b_up) in before_enabled.items():
            a_en, a_up = after_enabled[rid]
            if rid in set(pm):
                assert b_en is True and a_en is False
            else:
                assert a_en == b_en and a_up == b_up, rid
        audits = _audits(data, action="pricing_rule_disabled")
        assert {str(a.entity_id) for a in audits} == set(pm)
        assert all(a.note == REASON_APPLY for a in audits)
        assert all(str(a.admin_user_id) == data["admin_id"] for a in audits)

        # The whole flow (export + apply) left accounting untouched.
        after = _snapshot(data)
        for component in ("keys", "ledger", "quota"):
            assert after[component] == before[component], component

        # Honest repeat: REPLAY the ORIGINAL signed token/CSRF in the same
        # browser context. A re-preview of already-disabled rows is refused
        # by law, so the displayed authority is replayed verbatim instead:
        # the result is a no-op (no second disable, no duplicate audit).
        audit_ids_before = {str(a.id) for a in _audits(data)}
        repeat = page.request.post(  # type: ignore[union-attr]
            f"{data['base_url']}{REPORTS}/pricing-disable/apply",
            form={
                "csrf_token": review_csrf,
                "review_token": review_token,
                "confirm_apply": "1",
            },
        )
        assert repeat.status == 200
        assert "Already disabled" in repeat.text()
        assert {str(a.id) for a in _audits(data)} == audit_ids_before
    finally:
        page.close()  # type: ignore[union-attr]


def test_06_older_provider_beyond_200_route_form(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        target = data["target_provider"]
        model = f"214b-route-{data['suffix']}"
        upstream = f"214b-upstream-{data['suffix']}"

        def _fill_route_form(provider: str) -> None:
            page.goto(f"{data['base_url']}/admin/routes/new")  # type: ignore[attr-defined]
            # With JS the managed hidden field is the form authority, so
            # allow_new controls are typed (the input event syncs the hidden
            # value) while allow_new=false controls MUST select a rendered
            # option (typed text alone never submits).  Provider first: the
            # requested-model choice depends on it.
            provider_rc = page.locator('[data-rc][data-input-name="provider"]')  # type: ignore[union-attr]
            provider_rc.locator(".rc-input").fill(provider)
            provider_option = provider_rc.locator("li.rc-option", has_text=provider).first
            provider_option.wait_for()
            provider_option.click()
            page.locator(".rc-input[aria-describedby='route-create-match-model-help']").fill(model)  # type: ignore[union-attr]
            page.keyboard.press("Tab")  # type: ignore[attr-defined]
            page.select_option("select[name='match_type']", "exact")  # type: ignore[union-attr]
            endpoint_rc = page.locator('[data-rc][data-input-name="endpoint"]')  # type: ignore[union-attr]
            endpoint_rc.locator(".rc-input").fill("/v1/chat/completions")
            endpoint_rc.locator("li.rc-option", has_text="/v1/chat/completions").first.click()
            page.locator(".rc-input[aria-describedby='route-create-target-upstream-help']").fill(upstream)  # type: ignore[union-attr]
            page.keyboard.press("Tab")  # type: ignore[attr-defined]
            page.fill("input[name='priority']", "0")  # type: ignore[attr-defined]
            page.fill("input[name='reason']", REASON_ROUTE)  # type: ignore[attr-defined]

        # The target provider is BEYOND the 200-row choice batch but is a real
        # provider: the route form's bounded exact lookup accepts it.
        _fill_route_form(target)
        page.click('form[action="/admin/routes/new"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#route-create-heading, #route-result-heading, .admin-flash")  # type: ignore[attr-defined]
        created = _routes_by_model(data, model)
        assert any(str(r.provider) == target for r in created), "older provider beyond 200 must be saved"

        # An unknown provider is still refused: the JS picker cannot select
        # it, and the server's bounded exact lookup refuses a posted unknown
        # slug (same browser context, the route form's displayed CSRF).
        unknown = f"zzz-not-a-provider-{data['suffix']}"
        unknown_resp = page.request.post(  # type: ignore[union-attr]
            f"{data['base_url']}/admin/routes/new",
            form={
                "csrf_token": _form_csrf(page),
                "requested_model": model,
                "match_type": "exact",
                "endpoint": "/v1/chat/completions",
                "provider": unknown,
                "upstream_model": upstream,
                "priority": "0",
                "creation_intent": "automatic",
                "reason": REASON_ROUTE,
            },
        )
        assert unknown_resp.status == 400
        assert "Select a known provider config." in unknown_resp.text()
        assert not any(str(r.provider) == unknown for r in _routes_by_model(data, model))
    finally:
        page.close()  # type: ignore[union-attr]


def test_07_nojs_validation_recovery(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    context = chromium.new_context(java_script_enabled=False)  # type: ignore[union-attr]
    page = context.new_page()
    try:
        _login(page, data)
        # The live-burn filter's start bound is a native (unvalidated) text
        # field; an invalid value reaches the server refusal, whose no-JS
        # recovery link navigates back to the report (no JS needed).
        page.goto(_qurl(data["base_url"], f"{REPORTS}/live-burn", start_at="not-a-time"))  # type: ignore[attr-defined]
        page.wait_for_selector("#error-heading")  # type: ignore[attr-defined]
        assert "invalid datetime" in page.inner_text("body")  # type: ignore[attr-defined]
        recovery = page.locator('a.button-link', has_text="Back to the report")  # type: ignore[union-attr]
        assert recovery.count() == 1
        recovery.first.click()
        page.wait_for_selector("#live-burn-heading")  # type: ignore[attr-defined]

        # No-JS source-cap recovery: with the (in-process) source bound
        # lowered below the 14-row seed, the UNFILTERED summary is refused
        # - but on the report page itself, with the EXISTING filter form
        # (no JS: the visible inputs carry the form names directly).
        # Entering a narrowing filter through that form reaches an
        # accepted report; no URL editing is needed.
        original_bound = admin_reports.GUI_USAGE_REPORT_SOURCE_MAX_ROWS
        admin_reports.GUI_USAGE_REPORT_SOURCE_MAX_ROWS = 3
        try:
            page.goto(_qurl(data["base_url"], f"{REPORTS}/", group_by="provider"))  # type: ignore[attr-defined]
            body = page.inner_text("body")  # type: ignore[attr-defined]
            assert "bounded source limit of 3" in body
            assert "No groups in the accepted scope" not in body
            assert page.locator('form[action="/admin/reports/"] input[name="provider"]').count() == 1
            # Narrow through the visible form: prov-a carries exactly 3
            # seeded rows, within the bound of 3.
            page.fill('form[action="/admin/reports/"] input[name="provider"]', "prov-a")  # type: ignore[attr-defined]
            page.click('form[action="/admin/reports/"] button[type="submit"]')  # type: ignore[attr-defined]
            page.wait_for_selector("#usage-summary-rows-shown")  # type: ignore[attr-defined]
            assert "prov-a" in _summary_group_rows(page)
            assert "bounded source limit" not in page.inner_text("body")  # type: ignore[attr-defined]
        finally:
            admin_reports.GUI_USAGE_REPORT_SOURCE_MAX_ROWS = original_bound
    finally:
        context.close()  # type: ignore[union-attr]


def test_08_desktop_and_narrow_captures(reports_env: dict[str, Any], chromium: object) -> None:
    data = reports_env
    page = chromium.new_page(viewport={"width": 1440, "height": 900})  # type: ignore[union-attr]
    try:
        _login(page, data)

        # Desktop: the provider-grouped summary and the pricing review page.
        # Use the UNTOUCHED ppolicy/mpolicy scope (one still-enabled row):
        # test_05 already disabled the pmain/mmain rows, and re-previewing
        # an all-disabled scope is refused by law - do NOT re-enable rows
        # just for a screenshot.
        page.goto(_qurl(data["base_url"], f"{REPORTS}/", group_by="provider", limit=100))  # type: ignore[attr-defined]
        page.screenshot(path=str(SCREENSHOT_DIR / "214-summary-desktop.png"), full_page=True)  # type: ignore[attr-defined]
        page.goto(f"{data['base_url']}{REPORTS}/pricing-disable")  # type: ignore[attr-defined]
        page.fill("#pd-provider-input", "ppolicy")  # type: ignore[attr-defined]
        page.fill("#pd-model-input", "mpolicy")  # type: ignore[attr-defined]
        page.fill("#pd-reason", "214 browser final capture preview")  # type: ignore[attr-defined]
        page.click('form[action="/admin/reports/pricing-disable/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#pd-review-facts-heading")  # type: ignore[attr-defined]
        # Real keyboard on the review confirmation checkbox: toggle and back so
        # the capture shows the unconfirmed state (NO apply here).
        page.focus("#pd-confirm-apply")  # type: ignore[attr-defined]
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert page.is_checked("#pd-confirm-apply")  # type: ignore[union-attr]
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert not page.is_checked("#pd-confirm-apply")  # type: ignore[union-attr]
        page.screenshot(path=str(SCREENSHOT_DIR / "214-pricing-review-desktop.png"), full_page=True)  # type: ignore[attr-defined]

        # Narrow: the summary and the pricing form.
        page.set_viewport_size({"width": 390, "height": 844})  # type: ignore[attr-defined]
        page.goto(_qurl(data["base_url"], f"{REPORTS}/", group_by="provider", limit=25))  # type: ignore[attr-defined]
        page.screenshot(path=str(SCREENSHOT_DIR / "214-summary-narrow.png"), full_page=True)  # type: ignore[attr-defined]
        page.goto(f"{data['base_url']}{REPORTS}/pricing-disable")  # type: ignore[attr-defined]
        page.screenshot(path=str(SCREENSHOT_DIR / "214-pricing-narrow.png"), full_page=True)  # type: ignore[attr-defined]
        # Populated pricing REVIEW at narrow width (the untouched
        # ppolicy/mpolicy scope): the reviewed facts table in the
        # established wide/nowrap/scroll styles, review unconfirmed.
        page.fill("#pd-provider-input", "ppolicy")  # type: ignore[attr-defined]
        page.fill("#pd-model-input", "mpolicy")  # type: ignore[attr-defined]
        page.fill("#pd-reason", "214 browser narrow capture preview")  # type: ignore[attr-defined]
        page.click('form[action="/admin/reports/pricing-disable/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#pd-review-facts-heading")  # type: ignore[attr-defined]
        page.screenshot(path=str(SCREENSHOT_DIR / "214-pricing-review-narrow.png"), full_page=True)  # type: ignore[attr-defined]

        for name in (
            "214-summary-desktop.png",
            "214-pricing-review-desktop.png",
            "214-summary-narrow.png",
            "214-pricing-narrow.png",
            "214-pricing-review-narrow.png",
        ):
            assert (SCREENSHOT_DIR / name).stat().st_size > 0
    finally:
        page.close()  # type: ignore[attr-defined]
