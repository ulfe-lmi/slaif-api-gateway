"""213-a GUI Codex replay-reference maintenance: real-Chromium browser
qualification.

Real browser, real uvicorn app, owned PostgreSQL (the ``owned_pg_url``
fixture is reused directly - this module is the SOLE PG owner of the
run; no outer runner container, no ambient TEST_DATABASE_URL, no
proxy-mocked success: every navigation, form, and DB oracle goes
through the actual HTTP handlers and the real DB).

Cases (file order is significant - one key per scenario family):

- real login -> dashboard Operations -> Replay maintenance index
  (three explicit scopes) and the bound navigation from the existing
  Keys and Cohorts detail pages;
- the shared-service INSPECTION through the actual form is read-only
  (independent before/after DB oracle: every key/ledger/reference/
  reservation column, expiries, and the audit count);
- PREVIEW -> CONFIRM -> APPLY through the ACTUAL UI (typed reason,
  checked confirmation): the exact monotonic extension with an
  independent DB oracle (original-age targets, never-shortened rows,
  complete-row stability digests, ONE session-actor/reason audit);
- the exact repeat of the SAME reviewed token is a no-op (no
  duplicate write or audit);
- the displayed reviewed token remains usable after a real
  background read (a second-tab inspection), applied through a
  browser-context form POST with the current session CSRF;
- the NO-JS operator flow (JavaScript disabled): native form inspect,
  a validation refusal with the no-JS recovery link back to the scope,
  and the full preview -> confirm -> apply flow;
- desktop and narrow captures for visual review.

Safety: synthetic fixture keys and references only (never forwarded);
no real provider/Codex call, respx mock, or ledger accounting.
"""

from __future__ import annotations

import asyncio
import contextlib
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

import pytest
import uvicorn
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    CodexReplayReference,
    GatewayKey,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferenceInsert,
    CodexReplayReferencesRepository,
)
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.codex_module_upgrade import (
    CODEX_0149_V4_CLIENT_MODULE,
)
from slaif_gateway.services.codex_replay_maintenance import EXTEND_ACTION
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
)

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
SCREENSHOT_DIR = Path("/tmp/slaif213")
BASE = "/admin/operations/replay-maintenance"

TTL = 31_536_000

REASON_MAIN = "213 browser main-scope extension apply"
REASON_RB = "213 browser background-read token apply"
REASON_NOJS = "213 browser no-js flow apply"

REF_TAGS = ("a", "late", "func", "expired", "ledger-bad", "cross", "version2", "old", "rev", "rb", "nojs")


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


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seed (fixture data only: synthetic keys/references, never forwarded)
# ---------------------------------------------------------------------------


async def _seed_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    created_10d = now - timedelta(days=10)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui213b-{suffix}@example.org",
                    display_name="213 Replay Browser Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner = await OwnersRepository(session).create_owner(
                    name="213b",
                    surname=f"Replay-{suffix}",
                    email=f"gui213b-owner-{suffix}@example.org",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"replay213b-{suffix}"
                )
                route = await ModelRoutesRepository(session).create_model_route(
                    requested_model=f"zap-213b-{suffix}",
                    provider="mod-a",
                    upstream_model=f"zap-213b-{suffix}",
                )
                keys_repo = GatewayKeysRepository(session)

                async def _key(tag: str, *, status: str = "active") -> GatewayKey:
                    row = await keys_repo.create_gateway_key_record(
                        public_key_id=f"213b-{tag}-{suffix}",
                        token_hash=f"213b-{tag}-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        valid_from=now - timedelta(days=10),
                        valid_until=now + timedelta(days=3650),
                        status=status,
                        created_by_admin_user_id=admin.id,
                        allow_all_models=False,
                        allowed_models=[f"213b-only-model-{suffix}"],
                        allow_all_endpoints=False,
                        allowed_endpoints=["/v1/responses"],
                        cost_limit_eur=Decimal("42.5"),
                        token_limit_total=1234567,
                        request_limit_total=89,
                    )
                    row.cost_used_eur = Decimal("7.25")
                    row.tokens_used_total = 101
                    row.requests_used_total = 7
                    row.cost_reserved_eur = Decimal("0.05")
                    row.tokens_reserved_total = 13
                    row.requests_reserved_total = 2
                    if tag == "main":
                        row.metadata_json = {
                            "responses_policy": {
                                "client_module": dict(CODEX_0149_V4_CLIENT_MODULE),
                            },
                            "213b_sentinel": {"kept": f"replay213b-{suffix}"},
                        }
                    return row

                main_key = await _key("main")
                revoked_key = await _key("revoked", status="revoked")
                rb_key = await _key("rb")
                nojs_key = await _key("nojs")

                reservation = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=main_key.id,
                    request_id=f"req-213b-main-{suffix}",
                    endpoint="/v1/responses",
                    requested_model=f"zap-213b-{suffix}",
                    provider="mod-a",
                    reserved_cost_eur=Decimal("0.05"),
                    reserved_tokens=13,
                    reserved_requests=2,
                    status="pending",
                    expires_at=now + timedelta(days=1),
                )
                session.add(reservation)

                def _ledger(key: GatewayKey, tag: str, *, finalized: bool) -> UsageLedger:
                    row = UsageLedger(
                        request_id=f"req-213b-{tag}-{suffix}",
                        gateway_key_id=key.id,
                        endpoint="/v1/responses",
                        provider="mod-a",
                        success=True if finalized else None,
                        accounting_status="finalized" if finalized else "pending",
                        started_at=created_10d,
                        finished_at=created_10d,
                    )
                    session.add(row)
                    return row

                lg_main = _ledger(main_key, "main", finalized=True)
                lg_main.quota_reservation_id = reservation.id
                lg_main_bad = _ledger(main_key, "main-bad", finalized=False)
                lg_revoked = _ledger(revoked_key, "revoked", finalized=True)
                lg_rb = _ledger(rb_key, "rb", finalized=True)
                lg_nojs = _ledger(nojs_key, "nojs", finalized=True)
                await session.flush()

                async def _ref(
                    *,
                    key: GatewayKey,
                    ledger: UsageLedger,
                    tag: str,
                    created: datetime,
                    expires: datetime,
                    version: int = 1,
                    kind: str = "reasoning",
                    call: bool = False,
                ) -> None:
                    await CodexReplayReferencesRepository(session).upsert_many(
                        [
                            CodexReplayReferenceInsert(
                                id=uuid.uuid4(),
                                gateway_key_id=key.id,
                                usage_ledger_id=ledger.id,
                                source_request_id=ledger.request_id,
                                provider="mod-a",
                                route_id=route.id,
                                upstream_model=f"zap-213b-{suffix}",
                                item_kind=kind,
                                item_id_hmac=_digest(f"item-{tag}"),
                                call_id_hmac=_digest(f"call-{tag}") if call else None,
                                hmac_key_version=version,
                                tool_namespace="functions" if call else None,
                                tool_name="exec" if call else None,
                                created_at=created,
                                expires_at=expires,
                            )
                        ]
                    )

                await _ref(key=main_key, ledger=lg_main, tag="a", created=created_10d, expires=created_10d + timedelta(days=90))
                await _ref(key=main_key, ledger=lg_main, tag="late", created=created_10d, expires=now + timedelta(days=999))
                await _ref(key=main_key, ledger=lg_main, tag="func", created=created_10d, expires=created_10d + timedelta(days=90), kind="function_call", call=True)
                await _ref(key=main_key, ledger=lg_main, tag="expired", created=created_10d, expires=now - timedelta(days=1))
                await _ref(key=main_key, ledger=lg_main_bad, tag="ledger-bad", created=created_10d, expires=created_10d + timedelta(days=90))
                await _ref(key=main_key, ledger=lg_revoked, tag="cross", created=created_10d, expires=created_10d + timedelta(days=90))
                await _ref(key=main_key, ledger=lg_main, tag="version2", created=created_10d, expires=created_10d + timedelta(days=90), version=2)
                await _ref(key=main_key, ledger=lg_main, tag="old", created=now - timedelta(days=400), expires=now + timedelta(days=90))
                await _ref(key=revoked_key, ledger=lg_revoked, tag="rev", created=created_10d, expires=created_10d + timedelta(days=90))
                await _ref(key=rb_key, ledger=lg_rb, tag="rb", created=created_10d, expires=created_10d + timedelta(days=90))
                await _ref(key=nojs_key, ledger=lg_nojs, tag="nojs", created=created_10d, expires=created_10d + timedelta(days=90))

                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "cohort_id": str(cohort.id),
                    "main_key": str(main_key.id),
                    "revoked_key": str(revoked_key.id),
                    "rb_key": str(rb_key.id),
                    "nojs_key": str(nojs_key.id),
                    "reservation": str(reservation.id),
                    "created_10d": created_10d,
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# DB oracles (threaded: the Playwright sync loop owns the main thread)
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
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _model_digest(rows: list[Any], model: type, exclude: frozenset[str]) -> str:
    # Mapper ATTRIBUTE keys (not Column.key): metadata_json maps to the
    # table column "metadata" and must be digested COMPLETELY.
    columns = [
        attr.key for attr in sa_inspect(model).column_attrs if attr.key not in exclude
    ]
    records = [
        {c: _jsonable(getattr(row, c)) for c in columns}
        for row in sorted(rows, key=lambda r: str(r.id))
    ]
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _key_ids(data: dict[str, Any]) -> list[uuid.UUID]:
    return [uuid.UUID(data[tag]) for tag in ("main_key", "revoked_key", "rb_key", "nojs_key")]


def _snapshot(data: dict[str, Any]) -> dict[str, Any]:
    async def _run(session):
        key_rows = (
            (await session.execute(select(GatewayKey).where(GatewayKey.id.in_(_key_ids(data)))))
            .scalars()
            .all()
        )
        ledger_rows = (
            (
                await session.execute(
                    select(UsageLedger).where(UsageLedger.gateway_key_id.in_(_key_ids(data)))
                )
            )
            .scalars()
            .all()
        )
        ref_rows = (
            (
                await session.execute(
                    select(CodexReplayReference).where(
                        CodexReplayReference.gateway_key_id.in_(_key_ids(data))
                    )
                )
            )
            .scalars()
            .all()
        )
        res_rows = (
            (
                await session.execute(
                    select(QuotaReservation).where(
                        QuotaReservation.id == uuid.UUID(data["reservation"])
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "keys": _model_digest(list(key_rows), GatewayKey, frozenset({"id"})),
            "ledger": _model_digest(list(ledger_rows), UsageLedger, frozenset({"id"})),
            "refs": _model_digest(
                list(ref_rows), CodexReplayReference, frozenset({"id", "expires_at"})
            ),
            "reservation": _model_digest(list(res_rows), QuotaReservation, frozenset({"id"})),
        }

    return _db(data["database_url"], _run)


def _expiries(data: dict[str, Any]) -> dict[str, datetime]:
    async def _run(session):
        rows = (
            (
                await session.execute(
                    select(CodexReplayReference).where(
                        CodexReplayReference.item_id_hmac.in_(
                            [_digest(f"item-{tag}") for tag in REF_TAGS]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        out: dict[str, datetime] = {}
        for row in rows:
            for tag in REF_TAGS:
                if row.item_id_hmac == _digest(f"item-{tag}"):
                    out[tag] = row.expires_at
        assert set(out) == set(REF_TAGS), f"missing seeded references: {set(REF_TAGS) - set(out)}"
        return out

    return _db(data["database_url"], _run)


def _audits(data: dict[str, Any]) -> list[Any]:
    async def _run(session):
        return list(
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.admin_user_id == uuid.UUID(data["admin_id"]),
                        AuditLog.action == EXTEND_ACTION,
                    )
                    .order_by(AuditLog.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    return _db(data["database_url"], _run)


# ---------------------------------------------------------------------------
# Module environment: owned PG (sole owner) + real uvicorn + Chromium
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def replay_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / "browser-213a-lifecycle.json").write_text(
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
def chromium(replay_env) -> Iterator[object]:
    """Depends on ``replay_env`` on purpose: the Playwright sync session
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


def _goto_scope(page: object, env: dict[str, Any], kind: str, code: str) -> None:
    url = f"{env['base_url']}{BASE}"
    if kind == "key":
        url += f"/key/{code}"
    elif kind == "cohort":
        url += f"/cohort/{code}"
    else:
        url += "/all-active"
    page.goto(url)  # type: ignore[attr-defined]


def _form_csrf(page: object) -> str:
    """The current session CSRF rendered in the page header form."""
    return page.locator('input[name="csrf_token"]').first.get_attribute("value")  # type: ignore[union-attr]


@pytest.fixture(scope="module")
def main_page(replay_env: dict[str, Any], chromium: object) -> Iterator[object]:
    """ONE authenticated BrowserContext page shared by the preview/
    apply case and its exact repeat: the repeat resubmits the SAME
    session-bound token in the SAME live context (no new login, no
    cookie artifact)."""
    page = chromium.new_page()  # type: ignore[union-attr]
    _login(page, replay_env)
    yield page
    page.close()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Cases (file order is significant)
# ---------------------------------------------------------------------------


def test_01_login_operations_and_bound_navigation(
    replay_env: dict[str, Any], chromium: object
) -> None:
    data = replay_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)

        # Operations index carries the Replay maintenance entry.
        page.goto(f"{data['base_url']}/admin/operations/")  # type: ignore[attr-defined]
        assert page.locator('a[href="/admin/operations/replay-maintenance/"]').count() == 1
        page.locator('a[href="/admin/operations/replay-maintenance/"]').first.click()
        page.wait_for_url(f"**{BASE}/")  # type: ignore[attr-defined]
        index_html = page.content()  # type: ignore[attr-defined]
        # Three explicit scopes: the two record selectors + all-active.
        assert 'href="/admin/keys"' in index_html
        assert 'href="/admin/cohorts"' in index_html
        assert f'href="{BASE}/all-active"' in index_html

        # Bound navigation from the existing key detail page.
        page.goto(f"{data['base_url']}/admin/keys")  # type: ignore[attr-defined]
        assert f"213b-main-{data['suffix']}" in page.content()  # type: ignore[attr-defined]
        page.goto(f"{data['base_url']}/admin/keys/{data['main_key']}")  # type: ignore[attr-defined]
        key_link = page.locator(f'a[href="{BASE}/key/{data["main_key"]}"]')
        assert key_link.count() == 1
        key_link.click()
        page.wait_for_url(f"**{BASE}/key/**")  # type: ignore[attr-defined]
        assert (
            page.locator("#replay-scope-heading").inner_text()  # type: ignore[attr-defined]
            == "One gateway key"
        )

        # Bound navigation from the existing cohort detail page.
        page.goto(f"{data['base_url']}/admin/cohorts")  # type: ignore[attr-defined]
        page.goto(f"{data['base_url']}/admin/cohorts/{data['cohort_id']}")  # type: ignore[attr-defined]
        cohort_link = page.locator(f'a[href="{BASE}/cohort/{data["cohort_id"]}"]')
        assert cohort_link.count() == 1
        cohort_link.click()
        page.wait_for_url(f"**{BASE}/cohort/**")  # type: ignore[attr-defined]
        assert (
            page.locator("#replay-scope-heading").inner_text()  # type: ignore[attr-defined]
            == "One cohort"
        )
    finally:
        page.close()  # type: ignore[attr-defined]


def test_02_inspect_form_is_read_only(
    replay_env: dict[str, Any], chromium: object
) -> None:
    data = replay_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        before = _snapshot(data)
        expiries_before = _expiries(data)
        assert _audits(data) == []

        _goto_scope(page, data, "key", data["main_key"])
        # Real keyboard submission: focus the inspect form's first
        # field and submit with Enter (no scripted button click).
        page.focus("#inspect-created-from")  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        page.wait_for_selector("#replay-inspection-heading")  # type: ignore[attr-defined]

        text = page.inner_text("body")  # type: ignore[attr-defined]
        assert "8 (7 active" in text  # 8 seeded references, 1 expired
        assert "31,536,000" in text  # configured default lifetime
        assert "Usage ledger row not finalized" in text
        assert "readiness" in text  # maintenance-metadata note
        # "Keys in scope" renders the NUMERIC aggregate in the real
        # browser (the dict.keys builtin must never leak).
        keys_text = page.locator(  # type: ignore[union-attr]
            "xpath=//dt[normalize-space()='Keys in scope']"
            "/following-sibling::dd[1]"
        ).inner_text()
        assert keys_text.strip() == "1 (1 active/valid)", keys_text
        assert "builtin method" not in text

        # No domain/audit writes from the inspection.
        assert _snapshot(data) == before
        assert _expiries(data) == expiries_before
        assert _audits(data) == []
    finally:
        page.close()  # type: ignore[attr-defined]


def test_03_preview_confirm_apply_real_ui(
    replay_env: dict[str, Any], main_page: object
) -> None:
    data = replay_env
    page = main_page
    try:
        before = _snapshot(data)
        expiries_before = _expiries(data)
        created_10d: datetime = data["created_10d"]
        target = created_10d + timedelta(seconds=TTL)

        _goto_scope(page, data, "key", data["main_key"])
        page.fill("#preview-reason", REASON_MAIN)  # type: ignore[attr-defined]
        page.click('form[action$="/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-facts-heading")  # type: ignore[attr-defined]

        # The reviewed facts: 3 eligible (a, late, func), the configured
        # default lifetime, the verbatim reason, and the hidden token.
        text = page.inner_text("body")  # type: ignore[attr-defined]
        assert REASON_MAIN in text
        assert "configured default" in text
        eligible_text = page.locator(  # type: ignore[union-attr]
            "xpath=//dt[normalize-space()='Eligible references']/following-sibling::dd[1]"
        ).inner_text()
        assert eligible_text.strip() == "3", eligible_text
        data["main_token"] = page.locator(  # type: ignore[union-attr]
            'input[name="review_token"]'
        ).get_attribute("value")
        assert data["main_token"]

        # The deliberate preview wrote nothing.
        assert _snapshot(data) == before
        assert _expiries(data) == expiries_before
        assert _audits(data) == []

        # Confirm and apply through the actual UI.
        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.click('form[action$="/apply"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-applied-heading")  # type: ignore[attr-defined]
        applied_text = page.inner_text("body")  # type: ignore[attr-defined]
        assert "Applied: 2 references extended" in applied_text
        assert "3 eligible references" in applied_text
        assert "1 selected key." in applied_text

        # ENTIRE expiry map: exactly the two under-target eligible rows
        # moved to the original-age target; nothing else changed.
        expected = dict(expiries_before)
        expected["a"] = target
        expected["func"] = target
        assert _expiries(data) == expected

        # Complete non-expiry state (keys incl. full metadata, ledgers,
        # references, reservation) byte-stable.
        after = _snapshot(data)
        assert after == before, "unrelated rows changed by the apply"

        # Exactly ONE audit: session-derived actor, verbatim reason,
        # aggregate facts, no raw digests or row UUIDs.
        audits = _audits(data)
        assert len(audits) == 1
        entry = audits[0]
        assert entry.action == EXTEND_ACTION
        assert entry.entity_type == "codex_replay_references"
        assert entry.entity_id is None
        assert str(entry.admin_user_id) == data["admin_id"]
        assert entry.note == REASON_MAIN
        assert entry.old_values["extended_references"] == 2
        assert entry.old_values["eligible_references"] == 3
        assert entry.old_values["include_expired"] is False
        audit_text = json.dumps(
            {"old": entry.old_values, "new": entry.new_values}, default=str
        )
        for tag in REF_TAGS:
            assert _digest(f"item-{tag}") not in audit_text
    finally:
        pass  # main_page is closed by its fixture, AFTER test_04


def test_04_exact_repeat_same_token_no_duplicate(
    replay_env: dict[str, Any], main_page: object
) -> None:
    data = replay_env
    page = main_page
    try:
        before = _snapshot(data)
        expiries_before = _expiries(data)
        assert len(_audits(data)) == 1

        # SAME live context as the apply (the session-bound token is
        # verified against this exact actor/session).  The result page
        # no longer renders the apply form, so the SAME reviewed token
        # is resubmitted through a browser-context form POST with the
        # current session CSRF (browser HTTP, not another UI select).
        _goto_scope(page, data, "key", data["main_key"])
        resp = page.request.post(  # type: ignore[union-attr]
            f"{data['base_url']}{BASE}/apply",
            form={
                "csrf_token": _form_csrf(page),
                "review_token": data["main_token"],
                "confirm_apply": "1",
            },
        )
        assert resp.status == 200
        assert "Already applied" in resp.text()

        assert _snapshot(data) == before
        assert _expiries(data) == expiries_before
        assert len(_audits(data)) == 1
    finally:
        pass  # main_page is closed by its fixture


def test_05_token_survives_background_read(
    replay_env: dict[str, Any], chromium: object
) -> None:
    data = replay_env
    page = chromium.new_page()  # type: ignore[union-attr]
    try:
        _login(page, data)
        before = _snapshot(data)
        expiries_before = _expiries(data)
        created_10d: datetime = data["created_10d"]
        target = created_10d + timedelta(seconds=TTL)

        # Preview the rb key scope through the UI and capture the token
        # on the displayed review page.
        _goto_scope(page, data, "key", data["rb_key"])
        page.fill("#preview-reason", REASON_RB)  # type: ignore[attr-defined]
        page.click('form[action$="/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-facts-heading")  # type: ignore[attr-defined]
        token = page.locator('input[name="review_token"]').get_attribute("value")  # type: ignore[union-attr]
        assert token
        displayed_csrf = _form_csrf(page)

        # A REAL background read in the SAME context: a private POST
        # /inspect of ANOTHER scope (read-only, verify-only CSRF, no
        # rotation of the displayed form) with the ORIGINAL displayed
        # CSRF.
        bg_resp = page.request.post(  # type: ignore[union-attr]
            f"{data['base_url']}{BASE}/inspect",
            form={
                "csrf_token": displayed_csrf,
                "scope": "key",
                "key_id": data["main_key"],
                "created_from": "",
                "created_until": "",
            },
        )
        assert bg_resp.status == 200
        assert "8 (7 active" in bg_resp.text()
        assert _snapshot(data) == before
        assert _expiries(data) == expiries_before
        assert len(_audits(data)) == 1

        # The UNCHANGED displayed review page's confirm/apply UI still
        # works with the SAME token (the signed facts survived the
        # background read).
        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.click('form[action$="/apply"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-applied-heading")  # type: ignore[attr-defined]
        assert "Applied: 1 reference extended" in page.inner_text("body")  # type: ignore[attr-defined]

        expected = dict(expiries_before)
        expected["rb"] = target
        assert _expiries(data) == expected
        after = _snapshot(data)
        assert after == before, "unrelated rows changed by the apply"
        audits = _audits(data)
        assert len(audits) == 2
        assert audits[1].note == REASON_RB
        assert audits[1].old_values["extended_references"] == 1
    finally:
        page.close()  # type: ignore[attr-defined]


def test_06_nojs_flow_and_recovery(
    replay_env: dict[str, Any], chromium: object
) -> None:
    data = replay_env
    context = chromium.new_context(java_script_enabled=False)  # type: ignore[union-attr]
    page = context.new_page()
    try:
        _login(page, data)
        before = _snapshot(data)
        expiries_before = _expiries(data)
        created_10d: datetime = data["created_10d"]
        target = created_10d + timedelta(seconds=TTL)
        audit_count_before = len(_audits(data))

        _goto_scope(page, data, "key", data["nojs_key"])

        # No-JS inspection through the native form.
        page.click('form[action$="/inspect"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#replay-inspection-heading")  # type: ignore[attr-defined]
        assert "1" in page.inner_text("body")  # type: ignore[attr-defined]

        # No-JS validation recovery: back to the scope, a text bound
        # field is not natively validated, so the server refusal
        # renders, and its recovery link navigates back to the exact
        # scope (no JS needed).
        _goto_scope(page, data, "key", data["nojs_key"])
        page.fill("#inspect-created-from", "not-a-time")  # type: ignore[attr-defined]
        page.click('form[action$="/inspect"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#error-heading")  # type: ignore[attr-defined]
        assert "ISO 8601 UTC timestamp" in page.inner_text("body")  # type: ignore[attr-defined]
        recovery = page.locator('a.button-link[href$="/key/%s"]' % data["nojs_key"])
        assert recovery.count() == 1
        recovery.click()
        page.wait_for_selector("#replay-scope-heading")  # type: ignore[attr-defined]

        # No-JS preview -> confirm -> apply.
        page.fill("#preview-reason", REASON_NOJS)  # type: ignore[attr-defined]
        page.click('form[action$="/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-facts-heading")  # type: ignore[attr-defined]
        page.check("#confirm-apply")  # type: ignore[attr-defined]
        page.click('form[action$="/apply"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-applied-heading")  # type: ignore[attr-defined]
        assert "Applied: 1 reference extended" in page.inner_text("body")  # type: ignore[attr-defined]

        expected = dict(expiries_before)
        expected["nojs"] = target
        assert _expiries(data) == expected
        after = _snapshot(data)
        assert after == before, "unrelated rows changed by the apply"
        audits = _audits(data)
        assert len(audits) == audit_count_before + 1
        assert audits[-1].note == REASON_NOJS
        assert audits[-1].old_values["extended_references"] == 1
    finally:
        context.close()  # type: ignore[union-attr]


def test_07_desktop_and_narrow_captures(
    replay_env: dict[str, Any], chromium: object
) -> None:
    data = replay_env
    page = chromium.new_page(viewport={"width": 1440, "height": 900})  # type: ignore[union-attr]
    try:
        _login(page, data)

        # Desktop: the (re-)reviewed facts page for the main scope.
        _goto_scope(page, data, "key", data["main_key"])
        page.fill("#preview-reason", "213 browser final capture preview")  # type: ignore[attr-defined]
        page.click('form[action$="/preview"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#review-facts-heading")  # type: ignore[attr-defined]
        # Real keyboard on the review confirmation checkbox: focus it
        # and toggle with Space, then toggle back so the capture shows
        # the unconfirmed state (NO apply in this case).
        page.focus("#confirm-apply")  # type: ignore[attr-defined]
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert page.is_checked("#confirm-apply")  # type: ignore[attr-defined]
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert not page.is_checked("#confirm-apply")  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "213-replay-desktop-review.png"), full_page=True
        )

        _goto_scope(page, data, "key", data["main_key"])
        page.click('form[action$="/inspect"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#replay-inspection-heading")  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "213-replay-desktop-inspection.png"), full_page=True
        )

        # Narrow: index + the bound key scope form.
        page.set_viewport_size({"width": 390, "height": 844})  # type: ignore[attr-defined]
        page.goto(f"{data['base_url']}{BASE}")  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "213-replay-narrow-index.png"), full_page=True
        )
        _goto_scope(page, data, "key", data["main_key"])
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "213-replay-narrow-scope.png"), full_page=True
        )

        # Narrow: the POPULATED inspection page (real per-key,
        # route/model and reason rows; the identity and date cells
        # must stay un-wrapped inside the scroll wrapper).
        page.click('form[action$="/inspect"] button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#replay-inspection-heading")  # type: ignore[attr-defined]
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "213-replay-narrow-inspection.png"), full_page=True
        )

        for name in (
            "213-replay-desktop-review.png",
            "213-replay-desktop-inspection.png",
            "213-replay-narrow-index.png",
            "213-replay-narrow-scope.png",
            "213-replay-narrow-inspection.png",
        ):
            assert (SCREENSHOT_DIR / name).stat().st_size > 0
    finally:
        page.close()  # type: ignore[attr-defined]
