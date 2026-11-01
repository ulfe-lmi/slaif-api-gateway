"""213-a GUI Codex replay-reference maintenance: owned PostgreSQL tests.

Real-app, real-PostgreSQL qualification for the 213-a authenticated GUI
inspection and reviewed monotonic extension of retained Codex
replay-reference expiry against the qualified owned, labeled,
loopback-bound, tmpfs-backed PostgreSQL fixture.  This module reuses the
``owned_pg_url`` fixture directly, which ALWAYS creates one NEW owned
container and migrates it - so this module is the SOLE PG owner of the
run (no outer runner container, no ambient TEST_DATABASE_URL reuse).

One explicit ordered scenario (file order is significant); every oracle
is scoped to THIS run's exact seeded IDs:

- index/scope pages render the three explicit scopes (never an implicit
  default) with canonical-UUID bound key/cohort pages;
- the shared-service INSPECTION performs NO domain/audit writes;
- the deliberate PREVIEW performs NO domain/audit writes and shows the
  eligible/excluded counts, configured default lifetime, and the
  before/after expiry ranges;
- the reviewed apply extends ONLY ``expires_at`` of the eligible rows to
  the ORIGINAL stored ``created_at`` plus the selected lifetime (never
  now + lifetime, never shortening the already-later row), writes every
  unrelated reference/ledger/key column unchanged (independent
  full-column before/after digests), and records exactly ONE audit with
  the session-derived actor, the verbatim reviewed reason, the aggregate
  facts, and no raw digests/row UUIDs;
- the exact repeat is a no-op: no duplicate write, no duplicate audit;
- explicit include-expired extends an already-expired eligible row and
  nothing else (truthful updated_references < eligible_references);
- a changed eligibility state (the ledger row de-finalized after review)
  makes the reviewed plan stale and is refused with zero writes;
- a changed scope (an all-active key leaving the active set after
  review) is refused stale with zero writes;
- a late failure injected AFTER the real audit flush rolls back the
  WHOLE caller transaction (expiry update AND audit), renders the fixed
  UNCONFIRMED outcome, and the same reviewed token then applies cleanly
  on retry;
- native auth/CSRF denials (no session -> 303; valid session + wrong
  CSRF -> 400) with zero DB mutation.

The independent before/after oracle digests EVERY column of the seeded
gateway_keys rows (complete metadata included - not the 212
client-module-stripped digest), every seeded usage_ledger row, and every
seeded codex_replay_references row except id/expires_at.  No real
provider/Codex request, respx mock, gateway key usage, or forwarded
traffic is involved; the seeded keys and references are synthetic.
All mutations go through the shared Core replay-maintenance service;
nothing here is a separate write path.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect as sa_inspect, select, update
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
from slaif_gateway.services.codex_replay_maintenance import (
    EXTEND_ACTION,
    EXTEND_ENTITY_TYPE,
)
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,  # noqa: F401  (module-scoped owned-PG fixture reuse)
)

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="review_token" value="([^"]+)"')

ADMIN_PASSWORD = "correct horse battery staple"

BASE = "/admin/operations/replay-maintenance"
REPLAY = __import__("slaif_gateway.api.admin_replay_maintenance", fromlist=["x"])

TTL = 31_536_000  # the configured default (CODEX_REPLAY_REFERENCE_TTL_SECONDS)

REASON_KEY = "213 native key-scope extension apply"
REASON_EXPIRED = "213 native explicit expired inclusion apply"
REASON_ALL = "213 native all-active scope stale-scope proof"
REASON_RB = "213 native late-failure atomic rollback proof"


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET=generate_secret_key(),
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def asyncio_run(coro):
    return asyncio.run(coro)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seed: admin + owner + cohort + route + four keys + ledgers + references,
# in ONE transaction.
# ---------------------------------------------------------------------------


async def _seed(database_url: str) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    created_10d = now - timedelta(days=10)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui213-{suffix}@example.org",
                    display_name="213 Replay GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner = await OwnersRepository(session).create_owner(
                    name="213",
                    surname=f"Replay-{suffix}",
                    email=f"gui213-owner-{suffix}@example.org",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"replay213-{suffix}"
                )
                route = await ModelRoutesRepository(session).create_model_route(
                    requested_model=f"zap-213-{suffix}",
                    provider="mod-a",
                    upstream_model=f"zap-213-{suffix}",
                )
                keys_repo = GatewayKeysRepository(session)

                async def _key(
                    tag: str,
                    *,
                    status: str = "active",
                    valid_from: datetime | None = None,
                    valid_until: datetime | None = None,
                ) -> GatewayKey:
                    row = await keys_repo.create_gateway_key_record(
                        public_key_id=f"213-{tag}-{suffix}",
                        token_hash=f"213-{tag}-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        valid_from=valid_from or (now - timedelta(days=10)),
                        valid_until=valid_until or (now + timedelta(days=3650)),
                        status=status,
                        created_by_admin_user_id=admin.id,
                        allow_all_models=False,
                        allowed_models=[f"213-only-model-{suffix}"],
                        allow_all_endpoints=False,
                        allowed_endpoints=["/v1/responses"],
                        cost_limit_eur=Decimal("42.5"),
                        token_limit_total=1234567,
                        request_limit_total=89,
                    )
                    # Non-zero accounting sentinels preserved by the
                    # reviewed extension (key-row level).
                    row.cost_used_eur = Decimal("7.25")
                    row.tokens_used_total = 101
                    row.requests_used_total = 7
                    row.cost_reserved_eur = Decimal("0.05")
                    row.tokens_reserved_total = 13
                    row.requests_reserved_total = 2
                    return row

                from slaif_gateway.services.codex_module_upgrade import (
                    CODEX_0149_V4_CLIENT_MODULE,
                )

                main_key = await _key("main")
                # A legal existing pinned client-module binding plus an
                # unrelated nested sentinel: the full-key digest must
                # preserve BOTH across the reviewed extension.
                main_key.metadata_json = {
                    "responses_policy": {
                        "client_module": dict(CODEX_0149_V4_CLIENT_MODULE),
                    },
                    "213_sentinel": {"kept": f"replay213-{suffix}"},
                }
                revoked_key = await _key("revoked", status="revoked")
                active2_key = await _key("active2")
                rb_key = await _key("rb")

                def _ledger(key: GatewayKey, tag: str, *, finalized: bool) -> UsageLedger:
                    row = UsageLedger(
                        request_id=f"req-213-{tag}-{suffix}",
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

                reservation = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=main_key.id,
                    request_id=f"req-213-main-{suffix}",
                    endpoint="/v1/responses",
                    requested_model=f"zap-213-{suffix}",
                    provider="mod-a",
                    reserved_cost_eur=Decimal("0.05"),
                    reserved_tokens=13,
                    reserved_requests=2,
                    status="pending",
                    expires_at=now + timedelta(days=1),
                )
                session.add(reservation)
                await session.flush()
                lg_main = _ledger(main_key, "main", finalized=True)
                lg_main.quota_reservation_id = reservation.id
                lg_main_bad = _ledger(main_key, "main-bad", finalized=False)
                lg_revoked = _ledger(revoked_key, "revoked", finalized=True)
                lg_rb = _ledger(rb_key, "rb", finalized=True)
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
                                upstream_model=f"zap-213-{suffix}",
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

                await session.flush()
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "cohort_id": str(cohort.id),
                    "main_key": str(main_key.id),
                    "revoked_key": str(revoked_key.id),
                    "active2_key": str(active2_key.id),
                    "rb_key": str(rb_key.id),
                    "ledger_main": str(lg_main.id),
                    "reservation": str(reservation.id),
                    "created_10d": created_10d,
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, Any]] = {}


def _seed_sync(database_url: str) -> dict[str, Any]:
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio_run(_seed(database_url))
    return _SEED_CACHE[database_url]


# ---------------------------------------------------------------------------
# Independent DB oracles (scoped to THIS run's exact seeded rows)
# ---------------------------------------------------------------------------


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


async def _table_digest(
    database_url: str,
    model: type,
    ids: list[uuid.UUID],
    exclude: frozenset[str],
) -> str:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                (await session.execute(select(model).where(model.id.in_(ids))))
                .scalars()
                .all()
            )
        # Mapper ATTRIBUTE keys (not Column.key): metadata_json maps to
        # the table column "metadata", and Column.key would read the
        # declarative MetaData instead of the complete JSONB value.
        columns = [
            attr.key for attr in sa_inspect(model).column_attrs if attr.key not in exclude
        ]
        records = []
        for row in sorted(rows, key=lambda r: str(r.id)):
            records.append({c: _jsonable(getattr(row, c)) for c in columns})
        canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    finally:
        await engine.dispose()


def _key_ids(data: dict[str, Any]) -> list[uuid.UUID]:
    return [uuid.UUID(data[tag]) for tag in ("main_key", "revoked_key", "active2_key", "rb_key")]


def _ref_ids_by_tag(data: dict[str, Any]) -> dict[str, uuid.UUID]:
    """item_id_hmac == sha256('item-<tag>') is the stable seeded identity."""
    engine = _engine(data["database_url"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tags = ("a", "late", "func", "expired", "ledger-bad", "cross", "version2", "old", "rev", "rb")
    out: dict[str, uuid.UUID] = {}

    async def _run() -> None:
        try:
            async with factory() as session:
                for tag in tags:
                    row = (
                        (
                            await session.execute(
                                select(CodexReplayReference).where(
                                    CodexReplayReference.item_id_hmac
                                    == _digest(f"item-{tag}")
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )
                    assert row is not None, f"seeded reference {tag} missing"
                    out[tag] = row.id
        finally:
            await engine.dispose()

    asyncio_run(_run())
    return out


_REF_IDS: dict[str, uuid.UUID] = {}


def _ref_ids(data: dict[str, Any]) -> dict[str, uuid.UUID]:
    if not _REF_IDS:
        _REF_IDS.update(_ref_ids_by_tag(data))
    return _REF_IDS


async def _ref_expiries(
    database_url: str, ids: dict[str, uuid.UUID]
) -> dict[str, datetime]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    out: dict[str, datetime] = {}
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(CodexReplayReference).where(
                            CodexReplayReference.id.in_(list(ids.values()))
                        )
                    )
                )
                .scalars()
                .all()
            )
        by_id = {row.id: row for row in rows}
        for tag, rid in ids.items():
            out[tag] = by_id[rid].expires_at
    finally:
        await engine.dispose()
    return out


def _expiries(data: dict[str, Any]) -> dict[str, datetime]:
    return asyncio_run(_ref_expiries(data["database_url"], _ref_ids(data)))


async def _audit_rows(database_url: str, admin_id: str) -> list[Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return list(
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.admin_user_id == uuid.UUID(admin_id),
                            AuditLog.action == EXTEND_ACTION,
                        )
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()


def _audits(data: dict[str, Any]) -> list[Any]:
    return asyncio_run(_audit_rows(data["database_url"], data["admin_id"]))


async def _db_audit_total(data_url: str, admin_id: str) -> int:
    engine = _engine(data_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(AuditLog)
                        .where(AuditLog.admin_user_id == uuid.UUID(admin_id))
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


def _audit_total(data: dict[str, Any]) -> int:
    return asyncio_run(_db_audit_total(data["database_url"], data["admin_id"]))


def _snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Independent before/after state: EVERY non-expiry column of the
    seeded keys (complete metadata included), ledgers, and references."""
    refs = _ref_ids(data)
    ledger_ids = [uuid.UUID(data["ledger_main"])]
    engine = _engine(data["database_url"])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _run() -> list[uuid.UUID]:
        try:
            async with factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(UsageLedger.id).where(
                                UsageLedger.gateway_key_id.in_(_key_ids(data))
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                return list(rows)
        finally:
            await engine.dispose()

    ledger_ids = asyncio_run(_run())
    return {
        # Complete key rows INCLUDING updated_at (the reviewed extension
        # must not touch any key column) and the COMPLETE metadata_json.
        "keys": asyncio_run(
            _table_digest(
                data["database_url"],
                GatewayKey,
                _key_ids(data),
                frozenset({"id"}),
            )
        ),
        "ledger": asyncio_run(
            _table_digest(
                data["database_url"],
                UsageLedger,
                ledger_ids,
                frozenset({"id"}),
            )
        ),
        "refs": asyncio_run(
            _table_digest(
                data["database_url"],
                CodexReplayReference,
                list(refs.values()),
                frozenset({"id", "expires_at"}),
            )
        ),
        "reservation": asyncio_run(
            _table_digest(
                data["database_url"],
                QuotaReservation,
                [uuid.UUID(data["reservation"])],
                frozenset({"id"}),
            )
        ),
        "audits_total": _audit_total(data),
    }


def _assert_state_equal(before: dict[str, Any], after: dict[str, Any]) -> None:
    assert before["keys"] == after["keys"], "gateway_keys columns changed"
    assert before["ledger"] == after["ledger"], "usage_ledger rows changed"
    assert before["refs"] == after["refs"], (
        "codex_replay_references non-expiry columns changed"
    )
    assert before["reservation"] == after["reservation"], "quota_reservation changed"
    assert before["audits_total"] == after["audits_total"], "audit rows changed"


def _assert_expiries_equal(
    before: dict[str, datetime], after: dict[str, datetime]
) -> None:
    assert before == after, "reference expiry changed"


async def _set_ledger_status(
    database_url: str, ledger_id: str, status: str
) -> None:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    update(UsageLedger)
                    .where(UsageLedger.id == uuid.UUID(ledger_id))
                    .values(accounting_status=status)
                )
    finally:
        await engine.dispose()


async def _set_key_status(database_url: str, key_id: str, status: str) -> None:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    update(GatewayKey)
                    .where(GatewayKey.id == uuid.UUID(key_id))
                    .values(status=status)
                )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Module fixture: real app + real login on the owned PG
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env(owned_pg_url: str) -> Iterator[dict[str, Any]]:  # noqa: F811 (fixture dependency on the imported fixture name)
    data = _seed_sync(owned_pg_url)
    app = create_app(_settings(owned_pg_url))
    with TestClient(app) as client:
        _login(client, str(data["admin_email"]))
        data["client"] = client
        data["app"] = app
        data["database_url"] = owned_pg_url
        data["audit_total_after_login"] = _audit_total(data)
        yield data


def _login(client: TestClient, admin_email: str) -> None:
    login_page = client.get("/admin/login")
    csrf = CSRF_RE.search(login_page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"email": admin_email, "password": ADMIN_PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.status_code


def _err(html: str) -> str:
    m = re.search(r'<h1 id="error-heading">(.*?)</h1>\s*<p>(.*?)</p>', html, re.S)
    return f"{m.group(1)} / {m.group(2)}" if m else html[:500]


def _csrf(html: str) -> str:
    return CSRF_RE.search(html).group(1)


def _token(html: str) -> str:
    return TOKEN_RE.search(html).group(1)


def _scope_url(kind: str, code: str) -> str:
    if kind == "key":
        return f"{BASE}/key/{code}"
    if kind == "cohort":
        return f"{BASE}/cohort/{code}"
    return f"{BASE}/all-active"


def _scope_page(client: TestClient, kind: str, code: str) -> TestClient:
    page = client.get(_scope_url(kind, code))
    assert page.status_code == 200, (kind, code, page.status_code)
    return page


_FORM_SCOPE = {"key": "key", "cohort": "cohort", "all-active": "all_active"}


def _scope_fields(kind: str, code: str, page: TestClient) -> dict[str, str]:
    fields: dict[str, str] = {
        "csrf_token": _csrf(page.text),
        "scope": _FORM_SCOPE[kind],
        "created_from": "",
        "created_until": "",
    }
    if kind == "key":
        fields["key_id"] = code
    elif kind == "cohort":
        fields["cohort_id"] = code
    return fields


def _inspect(client: TestClient, kind: str, code: str) -> TestClient:
    page = _scope_page(client, kind, code)
    return client.post(f"{BASE}/inspect", data=_scope_fields(kind, code, page))


def _preview(
    client: TestClient, kind: str, code: str, reason: str, **extra: Any
) -> TestClient:
    page = _scope_page(client, kind, code)
    fields = _scope_fields(kind, code, page)
    fields["ttl_seconds"] = ""
    fields["reason"] = reason
    fields.update(extra)
    return client.post(f"{BASE}/preview", data=fields)


def _apply(client: TestClient, csrf: str, token: str, **overrides: Any) -> TestClient:
    data = {"csrf_token": csrf, "review_token": token, "confirm_apply": "1"}
    data.update(overrides)
    return client.post(f"{BASE}/apply", data=data)


# ---------------------------------------------------------------------------
# Ordered scenario
# ---------------------------------------------------------------------------


def test_01_pages_render_three_explicit_scopes(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]

    index = client.get(f"{BASE}/")
    assert index.status_code == 200
    # The global page offers the two record selectors plus the explicit
    # all-active scope (never an implicit default).
    for url in ("/admin/keys", "/admin/cohorts", f"{BASE}/all-active"):
        assert url in index.text, url

    # The bound navigation: key/cohort detail pages carry the exact
    # bound-scope Replay maintenance link.
    key_detail = client.get(f"/admin/keys/{data['main_key']}")
    assert key_detail.status_code == 200
    assert f'{BASE}/key/{data["main_key"]}' in key_detail.text
    cohort_detail = client.get(f"/admin/cohorts/{data['cohort_id']}")
    assert cohort_detail.status_code == 200
    assert f'{BASE}/cohort/{data["cohort_id"]}' in cohort_detail.text

    key_page = _scope_page(client, "key", data["main_key"])
    assert 'name="scope" value="key"' in key_page.text
    assert f'name="key_id" value="{data["main_key"]}"' in key_page.text
    cohort_page = _scope_page(client, "cohort", data["cohort_id"])
    assert 'name="scope" value="cohort"' in cohort_page.text
    all_page = _scope_page(client, "all-active", "")
    assert 'name="scope" value="all_active"' in all_page.text


def test_02_inspect_is_write_free(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    before = _snapshot(data)
    expiries_before = _expiries(data)

    response = _inspect(client, "key", data["main_key"])
    assert response.status_code == 200
    # The key-scope aggregates: 8 seeded references, 7 still unexpired.
    retained = re.search(r"Retained references.*?<dd>([^<]*)</dd>", response.text, re.S).group(1)
    assert retained.strip().startswith("8 (7 active"), retained
    assert "31,536,000" in response.text  # configured default lifetime, formatted
    assert "Usage ledger row not finalized" in response.text
    assert "maintenance metadata" in response.text or "readiness" in response.text

    assert _audits(data) == []
    assert _audit_total(data) == data["audit_total_after_login"]
    _assert_state_equal(before, _snapshot(data))
    _assert_expiries_equal(expiries_before, _expiries(data))


def test_03_preview_is_write_free_with_counts(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    before = _snapshot(data)
    expiries_before = _expiries(data)

    response = _preview(client, "key", data["main_key"], REASON_KEY)
    assert response.status_code == 200
    eligible = re.search(r"Eligible references.*?<dd>([^<]*)</dd>", response.text, re.S).group(1)
    assert eligible.strip() == "3", eligible  # a, late, func
    assert "configured default" in response.text
    assert "Usage ledger row not finalized" in response.text
    assert "Already expired and not explicitly included" in response.text
    token = _token(response.text)
    data["key_token"] = token
    data["key_csrf"] = _csrf(response.text)

    assert _audits(data) == []
    assert _audit_total(data) == data["audit_total_after_login"]
    _assert_state_equal(before, _snapshot(data))
    _assert_expiries_equal(expiries_before, _expiries(data))


def test_04_apply_monotonic_extension_one_audit(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    refs = _ref_ids(data)
    created_10d: datetime = data["created_10d"]
    before = _snapshot(data)
    expiries_before = _expiries(data)

    response = _apply(client, data["key_csrf"], data["key_token"])
    assert response.status_code == 200
    assert "Applied" in response.text
    assert "2" in re.search(r"Applied: ([0-9]+) reference", response.text).group(1)
    data["key_apply_csrf"] = _csrf(response.text)

    # Original-age monotonic target: created_at + TTL, never now + TTL.
    # The ENTIRE expiry map: exactly the two eligible under-target rows
    # moved; every other row (already-later, expired, excluded, other
    # keys) is byte-identical - never shortened, never re-created.
    target = created_10d + timedelta(seconds=TTL)
    expected = dict(expiries_before)
    expected["a"] = target
    expected["func"] = target
    assert _expiries(data) == expected

    # Every non-expiry column of every seeded row is byte-stable,
    # including complete key metadata, the ledger rows, and the
    # unrelated quota-reservation sentinel.
    after = _snapshot(data)
    assert before["keys"] == after["keys"]
    assert before["ledger"] == after["ledger"]
    assert before["refs"] == after["refs"]
    assert before["reservation"] == after["reservation"]

    audits = _audits(data)
    assert len(audits) == 1
    entry = audits[0]
    assert entry.action == EXTEND_ACTION
    assert entry.entity_type == EXTEND_ENTITY_TYPE
    assert entry.entity_id is None
    assert str(entry.admin_user_id) == data["admin_id"]
    assert entry.note == REASON_KEY
    old = entry.old_values
    new = entry.new_values
    assert old["operation"] == "extend"
    assert data["main_key"] in old["scope"]
    assert old["ttl_seconds"] == TTL
    assert old["include_expired"] is False
    assert old["selected_keys"] == 1
    assert old["eligible_references"] == 3
    assert old["extended_references"] == 2
    assert old["exclusion_counts"] == {
        "key_not_active_or_valid": 0,
        "ledger_not_finalized": 2,
        "unsupported_kind": 0,
        "hmac_version_unavailable": 1,
        "outside_lifetime": 1,
        "expired_not_included": 1,
    }
    assert new["new_expiry_range"] == [str(target), str(target)]
    # Privacy: no raw HMAC digests or individual row UUIDs in the audit.
    audit_text = json.dumps({"old": old, "new": new}, default=str)
    for tag in ("a", "late", "func", "expired", "ledger-bad", "cross", "version2", "old", "rev", "rb"):
        assert _digest(f"item-{tag}") not in audit_text
        assert str(refs[tag]) not in audit_text


def test_05_exact_repeat_no_duplicate_write_or_audit(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    before = _snapshot(data)
    expiries_before = _expiries(data)

    response = _apply(client, data["key_apply_csrf"], data["key_token"])
    assert response.status_code == 200
    assert "Already applied" in response.text
    data["key_apply_csrf"] = _csrf(response.text)

    _assert_state_equal(before, _snapshot(data))
    _assert_expiries_equal(expiries_before, _expiries(data))
    assert len(_audits(data)) == 1


def test_06_explicit_expired_inclusion_extends_only_expired(
    env: dict[str, Any],
) -> None:
    data = env
    client = data["client"]
    created_10d: datetime = data["created_10d"]
    before = _snapshot(data)
    expiries_before = _expiries(data)
    expired_expiry_before = expiries_before["expired"]
    assert expired_expiry_before < datetime.now(UTC)

    response = _preview(
        client, "key", data["main_key"], REASON_EXPIRED, include_expired="1"
    )
    assert response.status_code == 200
    eligible = re.search(r"Eligible references.*?<dd>([^<]*)</dd>", response.text, re.S).group(1)
    assert eligible.strip() == "4", eligible  # a, late, func, expired
    token = _token(response.text)
    csrf = _csrf(response.text)

    applied = _apply(client, csrf, token)
    assert applied.status_code == 200
    assert "Applied" in applied.text
    # Truthful: 1 of 4 eligible rows actually changed (the expired one);
    # the already-extended rows are not rewritten.
    assert "1" in re.search(r"Applied: ([0-9]+) reference", applied.text).group(1)
    data["key_apply_csrf"] = _csrf(applied.text)

    # ENTIRE expiry map: only the already-expired row moved; the three
    # already-extended/later rows are untouched (no rewrite).
    target = created_10d + timedelta(seconds=TTL)
    expected = dict(expiries_before)
    expected["expired"] = target
    assert _expiries(data) == expected

    after = _snapshot(data)
    assert before["keys"] == after["keys"]
    assert before["ledger"] == after["ledger"]
    assert before["refs"] == after["refs"]
    assert before["reservation"] == after["reservation"]

    audits = _audits(data)
    assert len(audits) == 2
    entry = audits[1]
    assert entry.action == EXTEND_ACTION
    assert entry.note == REASON_EXPIRED
    assert entry.old_values["include_expired"] is True
    assert entry.old_values["eligible_references"] == 4
    assert entry.old_values["extended_references"] == 1
    assert entry.new_values["new_expiry_range"] == [str(target), str(target)]


def test_07_changed_eligibility_is_stale_refused(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    before = _snapshot(data)
    expiries_before = _expiries(data)

    # After the reviewed plan was captured, the ledger row behind the
    # extended reference de-finalizes: the live classification changed.
    asyncio_run(_set_ledger_status(data["database_url"], data["ledger_main"], "pending"))

    # COMPLETE snapshot AFTER the deliberate eligibility change but
    # BEFORE the refused apply: the stale refusal must not write
    # anything on top of the live (de-finalized) state.
    mid = _snapshot(data)
    response = _apply(client, data["key_apply_csrf"], data["key_token"])
    assert response.status_code == 400
    assert "no longer matches" in response.text, _err(response.text)
    assert "Applied" not in response.text
    # Zero writes from the refused apply - the full snapshot (every
    # key/ledger/ref/reservation column, audit count) is byte-identical
    # to the pre-apply live state.
    _assert_state_equal(mid, _snapshot(data))
    _assert_expiries_equal(expiries_before, _expiries(data))

    # Restore the reviewed state for the later ordered tests; the
    # restored digest must equal the pre-test snapshot exactly.
    asyncio_run(_set_ledger_status(data["database_url"], data["ledger_main"], "finalized"))
    _assert_state_equal(before, _snapshot(data))


def test_08_changed_scope_is_stale_refused(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    expiries_before = _expiries(data)

    response = _preview(client, "all-active", "", REASON_ALL)
    assert response.status_code == 200, _err(response.text)
    token = _token(response.text)
    csrf = _csrf(response.text)

    # While the reviewed plan was captured, an all-active key leaves the
    # active set: the re-validated scope membership must differ.
    asyncio_run(_set_key_status(data["database_url"], data["active2_key"], "revoked"))

    # COMPLETE snapshot AFTER the deliberate scope change but BEFORE
    # the refused apply: the stale refusal must not write anything on
    # top of the live (revoked) state.
    mid = _snapshot(data)
    applied = _apply(client, csrf, token)
    assert applied.status_code == 400
    assert "no longer matches" in applied.text, _err(applied.text)
    assert "Applied" not in applied.text
    # Zero writes from the refused apply - the full snapshot (every
    # key/ledger/ref/reservation column, audit count) is byte-identical
    # to the pre-apply live state.
    _assert_state_equal(mid, _snapshot(data))
    _assert_expiries_equal(expiries_before, _expiries(data))

    # Restore the reviewed active set for later ordered tests.
    asyncio_run(_set_key_status(data["database_url"], data["active2_key"], "active"))


def test_09_late_failure_rolls_back_update_and_audit(
    env: dict[str, Any], monkeypatch
) -> None:
    data = env
    client = data["client"]
    before = _snapshot(data)
    expiries_before = _expiries(data)
    rb_expiry_before = expiries_before["rb"]

    response = _preview(client, "key", data["rb_key"], REASON_RB)
    assert response.status_code == 200
    token = _token(response.text)
    csrf = _csrf(response.text)

    # Failure injected AFTER the real audit flush, before the commit:
    # the updated expiry AND the flushed audit must roll back together.
    real_factory = REPLAY.AuditRepository

    def late_fail_factory(session):
        repo = real_factory(session)
        original = repo.add_audit_log

        async def boom(**kwargs):
            await original(**kwargs)
            raise RuntimeError("213 late-failure-injected")

        repo.add_audit_log = boom
        return repo

    monkeypatch.setattr(REPLAY, "AuditRepository", late_fail_factory)

    applied = _apply(client, csrf, token)
    assert applied.status_code == 400
    assert "UNCONFIRMED" in applied.text
    assert "Applied" not in applied.text

    _assert_state_equal(before, _snapshot(data))
    assert _expiries(data)["rb"] == rb_expiry_before
    data["rb_token"] = token


def test_10_retry_after_unconfirmed_applies(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    created_10d: datetime = data["created_10d"]
    before = _snapshot(data)
    _expiries_before = _expiries(data)

    page = _scope_page(client, "key", data["rb_key"])
    response = _apply(client, _csrf(page.text), data["rb_token"])
    assert response.status_code == 200
    assert "Applied" in response.text
    assert "1" in re.search(r"Applied: ([0-9]+) reference", response.text).group(1)

    # ENTIRE expiry map: only the retry key's reference moved.
    target = created_10d + timedelta(seconds=TTL)
    expected = dict(_expiries_before)
    expected["rb"] = target
    assert _expiries(data) == expected

    after = _snapshot(data)
    assert before["keys"] == after["keys"]
    assert before["ledger"] == after["ledger"]
    assert before["refs"] == after["refs"]
    assert before["reservation"] == after["reservation"]

    audits = _audits(data)
    assert len(audits) == 3
    entry = audits[2]
    assert entry.action == EXTEND_ACTION
    assert entry.note == REASON_RB
    assert entry.old_values["extended_references"] == 1


def test_11_native_auth_csrf_denials_zero_writes(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    before = _snapshot(data)
    expiries_before = _expiries(data)

    # (1) No session at all: every private endpoint refuses at the
    # login boundary.
    with TestClient(data["app"]) as fresh:
        inspect_no_session = fresh.post(
            f"{BASE}/inspect",
            data={
                "csrf_token": "x",
                "scope": "key",
                "key_id": data["main_key"],
                "created_from": "",
                "created_until": "",
            },
            follow_redirects=False,
        )
        assert inspect_no_session.status_code == 303
        assert inspect_no_session.headers["location"] == "/admin/login"
        preview_no_session = fresh.post(
            f"{BASE}/preview",
            data={
                "csrf_token": "x",
                "scope": "key",
                "key_id": data["main_key"],
                "ttl_seconds": "",
                "reason": REASON_KEY,
                "created_from": "",
                "created_until": "",
            },
            follow_redirects=False,
        )
        assert preview_no_session.status_code == 303
        assert preview_no_session.headers["location"] == "/admin/login"
        apply_no_session = fresh.post(
            f"{BASE}/apply",
            data={
                "csrf_token": "x",
                "review_token": data["key_token"],
                "confirm_apply": "1",
            },
            follow_redirects=False,
        )
        assert apply_no_session.status_code == 303
        assert apply_no_session.headers["location"] == "/admin/login"

    # (2) Valid session + wrong CSRF: fixed refusal, nothing executes.
    page = _scope_page(client, "key", data["main_key"])
    fields = _scope_fields("key", data["main_key"], page)
    fields["csrf_token"] = "wrong-csrf"
    response = client.post(f"{BASE}/preview", data=fields)
    assert response.status_code == 400
    assert "CSRF" in response.text

    # Zero DB mutation from any of the denials.
    _assert_state_equal(before, _snapshot(data))
    _assert_expiries_equal(expiries_before, _expiries(data))
    assert _audit_total(data) == before["audits_total"]
