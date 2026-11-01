"""214-a GUI grouped reports, pagination, and reviewed catalog tools: owned-PG HTTP proof.

Real-app, real-PostgreSQL qualification for the 214-a authenticated GUI:
grouped usage/live-burn reporting, safe strict-JSON export, complete
filter-preserving list navigation, reviewed matching-model pricing disable,
and effective FX lookup.  This module reuses the ``owned_pg_url`` fixture
directly (one NEW owned container, migrated), so it is the SOLE PG owner of
the run.  Every oracle is scoped to THIS run's exact seeded IDs.

One explicit ordered scenario (file order is significant); the normal HTTP
flow uses real auth/session/CSRF through the shared services and
repositories.  The late-audit rollback and the new pricing-lock boundary
are proven at the shared-service level on the SAME owned PG with controlled
fault / cached-lock instrumentation, honestly distinguished from the
unpatched normal flow.  No real provider/Codex request, respx mock, gateway
key usage, or forwarded traffic is involved; all rows are synthetic.
"""

from __future__ import annotations

import asyncio
import hashlib
import html as html_mod
import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.api import admin_reports
from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    FxRate,
    GatewayKey,
    PricingRule,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.main import create_app
from slaif_gateway.schemas.usage import UsageExportRow
from slaif_gateway.services.pricing_rule_service import (
    PricingDisableStaleError,
    PricingRuleService,
)
from slaif_gateway.services.codex_module_upgrade import CODEX_0149_V4_CLIENT_MODULE
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,  # noqa: F401  (module-scoped owned-PG fixture reuse)
)

REPORTS = "/admin/reports"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="review_token" value="([^"]+)"')
ADMIN_PASSWORD = "correct horse battery staple"

# Fixed reasons (214 native).
REASON_EXPORT = "214 native GUI strict-JSON usage export"
REASON_APPLY = "214 native reviewed pricing disable apply"

NOW = datetime.now(UTC)
TIED_TS = NOW - timedelta(hours=20)
TIE_TS = NOW - timedelta(hours=9)


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


# ---------------------------------------------------------------------------
# Seed: admin + 2 owners + 2 cohorts + 5 keys + 12 ledger rows + pricing + FX,
# in ONE transaction.
# ---------------------------------------------------------------------------


def _ledger_row(
    *,
    tag: str,
    suffix: str,
    provider: str,
    model: str,
    key_id: uuid.UUID,
    owner_id: uuid.UUID,
    cohort_id: uuid.UUID,
    est: Decimal | None,
    act: Decimal | None,
    created: datetime,
    owner_name: str,
    cohort_name: str,
    streaming: bool = False,
    chat_meta: dict[str, object] | None = None,
    tokens: int = 1000,
) -> UsageLedger:
    return UsageLedger(
        request_id=f"req-214-{tag}-{suffix}",
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
        prompt_tokens=tokens,
        completion_tokens=tokens // 2,
        input_tokens=tokens,
        output_tokens=tokens // 2,
        total_tokens=tokens * 3 // 2,
        estimated_cost_eur=est,
        actual_cost_eur=act,
        usage_raw={},
        response_metadata=dict(chat_meta or {}),
        started_at=created,
        finished_at=created,
        created_at=created,
    )


async def _seed(database_url: str) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui214-{suffix}@example.org",
                    display_name="214 Reports GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner_a = await OwnersRepository(session).create_owner(
                    name="OwnerA", surname=f"214-{suffix}",
                    email=f"gui214-ownera-{suffix}@example.org",
                )
                owner_b = await OwnersRepository(session).create_owner(
                    name="OwnerB", surname=f"214-{suffix}",
                    email=f"gui214-ownerb-{suffix}@example.org",
                )
                cohort_a = await CohortsRepository(session).create_cohort(name=f"cohort-a-{suffix}")
                cohort_b = await CohortsRepository(session).create_cohort(name=f"cohort-b-{suffix}")

                keys_repo = GatewayKeysRepository(session)

                async def _key(tag: str, *, owner, cohort) -> GatewayKey:
                    return await keys_repo.create_gateway_key_record(
                        public_key_id=f"214-{tag}-{suffix}",
                        token_hash=f"214-{tag}-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        valid_from=NOW - timedelta(days=10),
                        valid_until=NOW + timedelta(days=3650),
                        status="active",
                        created_by_admin_user_id=admin.id,
                        allow_all_models=False,
                        allowed_models=[f"214-model-{suffix}"],
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
                # 214-a preservation sentinels (reuse the 213 pattern): one
                # nonzero used/reserved key, nonempty legal client-pin/policy
                # metadata, and one real owned reservation row, so the quota
                # digest is non-empty before the preservation snapshots.
                key_a1.cost_used_eur = Decimal("7.25")
                key_a1.tokens_used_total = 101
                key_a1.requests_used_total = 7
                key_a1.cost_reserved_eur = Decimal("0.05")
                key_a1.tokens_reserved_total = 13
                key_a1.requests_reserved_total = 2
                key_a1.metadata_json = {
                    "responses_policy": {"client_module": dict(CODEX_0149_V4_CLIENT_MODULE)},
                    "214_sentinel": {"kept": f"214-policy-{suffix}"},
                }
                session.add(
                    QuotaReservation(
                        id=uuid.uuid4(),
                        gateway_key_id=key_a1.id,
                        request_id=f"req-214-resv-{suffix}",
                        endpoint="/v1/responses",
                        requested_model=f"214-model-{suffix}",
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
                        tag=tag, suffix=suffix, provider=provider, model=model,
                        key_id=key.id, owner_id=owner.id, cohort_id=cohort.id,
                        est=est, act=act, created=created,
                        owner_name=owner.name, cohort_name=cohort.name, **kw,
                    )

                ledger_rows = [
                    _row("zero", "prov-zero", "model-z", key_a1, owner_a, cohort_a, Decimal("0"), Decimal("0"), NOW - timedelta(hours=1)),
                    _row("miss", "prov-missing", "model-m", key_a1, owner_a, cohort_a, None, None, NOW - timedelta(hours=2)),
                    _row("mixk", "prov-mixed", "model-x", key_a2, owner_a, cohort_a, Decimal("5"), Decimal("3"), NOW - timedelta(hours=3)),
                    _row("mixm", "prov-mixed", "model-x", key_a2, owner_a, cohort_a, None, None, NOW - timedelta(hours=3)),
                    _row("a1", "prov-a", "model-a", key_a1, owner_a, cohort_a, Decimal("10"), Decimal("8"), NOW - timedelta(hours=4), streaming=True, chat_meta=chat_a),
                    _row("a2", "prov-a", "model-a", key_a2, owner_a, cohort_a, Decimal("20"), Decimal("18"), NOW - timedelta(hours=5), streaming=True, chat_meta=chat_b),
                    _row("a3", "prov-a", "model-a2", key_a1, owner_a, cohort_a, Decimal("5.5"), Decimal("5.5"), NOW - timedelta(hours=7)),
                    _row("b1", "prov-b", "model-b", key_b1, owner_b, cohort_b, Decimal("30"), Decimal("25"), NOW - timedelta(hours=6)),
                    _row("b2", "prov-b", "model-b2", key_b2, owner_b, cohort_b, Decimal("7"), Decimal("6"), NOW - timedelta(hours=8)),
                    _row("dold", "prov-d", "model-d", key_b1, owner_b, cohort_b, Decimal("40"), None, NOW - timedelta(days=3)),
                    _row("t1", "prov-c", "model-c", key_b2, owner_b, cohort_b, Decimal("1"), Decimal("1"), TIED_TS),
                    _row("t2", "prov-c", "model-c", key_b3, owner_b, cohort_b, Decimal("2"), Decimal("2"), TIED_TS),
                    # Two single-row provider groups that tie on
                    # (request_count, last_seen_at) to exercise the
                    # stable grouping_key FINAL tie-break for the report.
                    _row("tiea", "prov-tiea", "model-tie", key_a1, owner_a, cohort_a, Decimal("3"), Decimal("3"), TIE_TS),
                    _row("tieb", "prov-tieb", "model-tie", key_b1, owner_b, cohort_b, Decimal("4"), Decimal("4"), TIE_TS),
                ]
                for row in ledger_rows:
                    session.add(row)

                # Reviewed pricing disable scopes (all enabled, endpoint chat).
                pricing_repo = PricingRulesRepository(session)

                async def _pricing(
                    provider, model, tag, *, policy: str, enabled: bool = True, days_ago: int = 1
                ) -> PricingRule:
                    return await pricing_repo.create_pricing_rule(
                        provider=provider,
                        upstream_model=model,
                        valid_from=NOW - timedelta(days=days_ago),
                        endpoint="/v1/chat/completions",
                        currency="USD",
                        input_price_per_1m=Decimal("1"),
                        output_price_per_1m=Decimal("2"),
                        pricing_metadata={"policy": f"{policy}-{suffix}"},
                        enabled=enabled,
                    )

                # Co-located rules in one scope need a distinct valid_from
                # (the identity unique key is provider/model/endpoint/valid_from).
                pm1 = await _pricing("pmain", "mmain", "pm1", policy="pmain", days_ago=1)
                pm2 = await _pricing("pmain", "mmain", "pm2", policy="pmain", days_ago=2)
                po1 = await _pricing("ppolicy", "mpolicy", "po1", policy="ppolicy")
                pp1 = await _pricing("pprice", "mprice", "pp1", policy="pprice")
                pmem1 = await _pricing("pmember", "mmember", "pmem1", policy="pmember")
                px1 = await _pricing("pmixed", "mmixed", "px1", policy="pmixed", days_ago=1)
                px2 = await _pricing("pmixed", "mmixed", "px2", policy="pmixed", days_ago=2)
                prb1 = await _pricing("prb", "mrb", "prb1", policy="prb")
                prb2 = await _pricing("prb2", "mrb2", "prb2", policy="prb2")

                # One effective FX rate (EUR -> USD) for the present lookup.
                session.add(
                    FxRate(
                        id=uuid.uuid4(),
                        base_currency="EUR",
                        quote_currency="USD",
                        rate=Decimal("1.10"),
                        valid_from=NOW - timedelta(days=1),
                        valid_until=None,
                        source="214-test-fx",
                    )
                )
                await session.flush()

                # Independent seed facts for the report oracle: the test
                # re-derives each dimension's (label -> request_count) itself
                # from exactly the rows it seeded, rather than calling the
                # service aggregation helper.
                ledger_groups = [
                    {
                        "provider": r.provider,
                        "model": r.resolved_model or r.requested_model,
                        "owner_label": f"{r.owner_name_snapshot} {r.owner_surname_snapshot}".strip(),
                        "cohort_label": r.cohort_name_snapshot or "",
                        "key_id": str(r.gateway_key_id),
                        "created": r.created_at,
                    }
                    for r in ledger_rows
                ]

                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "owner_a": str(owner_a.id),
                    "owner_b": str(owner_b.id),
                    "cohort_a": str(cohort_a.id),
                    "cohort_b": str(cohort_b.id),
                    "key_a1": str(key_a1.id),
                    "key_b1": str(key_b1.id),
                    "keys": [str(k.id) for k in (key_a1, key_a2, key_b1, key_b2, key_b3)],
                    "tied1": "t1",
                    "tied2": "t2",
                    "pricing": {
                        "pmain": [str(pm1.id), str(pm2.id)],
                        "ppolicy": str(po1.id),
                        "pprice": str(pp1.id),
                        "pmember": str(pmem1.id),
                        "pmixed": [str(px1.id), str(px2.id)],
                        "prb": str(prb1.id),
                        "prb2": str(prb2.id),
                    },
                    "ledger_count": len(ledger_rows),
                    "ledger_groups": ledger_groups,
                }
    finally:
        await engine.dispose()


def _seed_sync(database_url: str) -> dict[str, Any]:
    return asyncio.run(_seed(database_url))


# ---------------------------------------------------------------------------
# Module fixture: real app + real login on the owned PG
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env(owned_pg_url: str) -> Iterator[dict[str, Any]]:  # noqa: F811 (imported fixture name)
    data = _seed_sync(owned_pg_url)
    app = create_app(_settings(owned_pg_url))
    with TestClient(app) as client:
        _login(client, str(data["admin_email"]))
        data["client"] = client
        data["app"] = app
        data["database_url"] = owned_pg_url
        yield data


# The two cases that legitimately WRITE an audit row (a valid JSON export,
# and the successful reviewed pricing apply).  Every other case is read-only
# (or a refused honest no-op) and must leave the audit log untouched.
_AUDIT_WRITING_CASES = frozenset(
    {
        "test_07_export_exact_json_unchanged_accounting",
        "test_11_pricing_preview_apply_actor_reason_scope",
    }
)


@pytest.fixture(autouse=True)
def _accounting_preservation(
    env: dict[str, Any], request: pytest.FixtureRequest
) -> Iterator[None]:
    """Per-test accounting oracle: gateway keys, the usage ledger, and quota
    reservations are IMMUTABLE across every GUI read/report/preview flow, and
    the audit log too for every read-only case.  Normal session/CSRF tracking
    (admin sessions, rotating CSRF tokens) is deliberately NOT part of these
    digests.  Reuses the existing full-table digests - no new fixture data or
    framework.
    """
    before = _unrelated_digests(env)
    yield
    after = _unrelated_digests(env)
    assert after["keys"] == before["keys"], "gateway keys changed by a read/report flow"
    assert after["ledger"] == before["ledger"], "usage ledger changed by a read/report flow"
    assert after["quota"] == before["quota"], "quota reservations changed by a read/report flow"
    if request.node.name not in _AUDIT_WRITING_CASES:
        assert after["audit"] == before["audit"], "audit log changed by a read-only case"


def _login(client: TestClient, admin_email: str) -> None:
    login_page = client.get("/admin/login")
    csrf = CSRF_RE.search(login_page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"email": admin_email, "password": ADMIN_PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.status_code


# ---------------------------------------------------------------------------
# Shared assertion helpers
# ---------------------------------------------------------------------------


def _csrf(page_html: str) -> str:
    return CSRF_RE.search(page_html).group(1)


def _nav_url(page_html: str, rel: str) -> str | None:
    m = re.search(rf'href="([^"]+)" rel="{rel}"', page_html)
    return html_mod.unescape(m.group(1)) if m else None


def _table_rows(page_html: str) -> list[str]:
    return re.findall(r"<tr[^>]*>.*?</tr>", page_html, re.S)


def _row_for(page_html: str, marker: str) -> str | None:
    for row in _table_rows(page_html):
        if marker in row:
            return row
    return None


def _summary_group_map(page_html: str) -> dict[str, int]:
    """Parse (group label -> request_count) from the rendered summary tbody.

    Reads the ACTUAL rendered row: the ``<th scope="row">`` label and the
    first ``data-sort-value`` cell (the raw integer request count), not the
    comma-formatted display text.
    """
    result: dict[str, int] = {}
    for row in _table_rows(page_html):
        label_m = re.search(r'<th scope="row">(.*?)</th>', row, re.S)
        count_m = re.search(r'<td [^>]*data-sort-value="(\d+)"', row)
        if label_m is not None and count_m is not None:
            result[html_mod.unescape(label_m.group(1))] = int(count_m.group(1))
    return result


def _audit_rows(database_url: str, *, action: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
    async def _run() -> list[dict[str, Any]]:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                stmt = select(AuditLog)
                if action is not None:
                    stmt = stmt.where(AuditLog.action == action)
                if entity_id is not None:
                    stmt = stmt.where(AuditLog.entity_id == uuid.UUID(entity_id))
                rows = (await session.execute(stmt)).scalars().all()
                return [
                    {
                        "id": str(r.id),
                        "action": r.action,
                        "entity_id": str(r.entity_id) if r.entity_id else None,
                        "admin_user_id": str(r.admin_user_id) if r.admin_user_id else None,
                        "note": r.note,
                    }
                    for r in rows
                ]
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _full_table_digest(database_url: str, model: type, exclude: frozenset[str] = frozenset()) -> str:
    columns = [a.key for a in sa_inspect(model).column_attrs if a.key not in exclude]
    async def _fetch() -> list[dict[str, Any]]:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        records: list[dict[str, Any]] = []
        try:
            async with factory() as session:
                rows = (await session.execute(select(model))).scalars().all()
                for row in sorted(rows, key=lambda r: str(r.id)):
                    records.append({c: _jsonable(getattr(row, c)) for c in columns})
        finally:
            await engine.dispose()
        return records

    records = asyncio.run(_fetch())
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _unrelated_digests(data: dict[str, Any]) -> dict[str, str]:
    url = data["database_url"]
    return {
        "keys": _full_table_digest(url, GatewayKey),
        "ledger": _full_table_digest(url, UsageLedger),
        "quota": _full_table_digest(url, QuotaReservation),
        "audit": _full_table_digest(url, AuditLog),
    }


# ---------------------------------------------------------------------------
# Slice 1: grouped summary, filters/time, cost availability, tie-break, cap+1
# ---------------------------------------------------------------------------


def test_01_summary_renders_seven_dimensions(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    groups = data["ledger_groups"]
    suffix = data["suffix"]
    key_a1 = data["key_a1"]
    # expected distinct-group cardinality per dimension, from the seeded rows
    # themselves (a plain distinct-key count, NOT the service grouping law).
    cardinality = {
        "provider": len({g["provider"] for g in groups}),
        "model": len({g["model"] for g in groups}),
        "provider_model": len({(g["provider"], g["model"]) for g in groups}),
        "owner": len({g["owner_label"] for g in groups}),
        "cohort": len({g["cohort_label"] for g in groups}),
        "key": len({g["key_id"] for g in groups}),
        "day": len({g["created"].date() for g in groups}),
    }
    # a few representative expected labels/IDs + their seeded request counts,
    # to anchor each dimension's rendered rows against the independent seed.
    representative = {
        "provider": [("prov-a", 3), ("prov-mixed", 2), ("prov-tiea", 1)],
        "model": [("model-a", 2), ("model-tie", 2)],
        "provider_model": [("prov-a / model-a", 2), ("prov-c / model-c", 2)],
        # the ledger rows snapshot the surname as the fixed "214" tag, so the
        # owner group label is "<Name> 214" (see _ledger_row), not the owner's
        # full suffixed surname.
        "owner": [("OwnerA 214", 8), ("OwnerB 214", 6)],
        "cohort": [(f"cohort-a-{suffix}", 8), (f"cohort-b-{suffix}", 6)],
        "key": [(key_a1, 5)],
        "day": [((NOW - timedelta(days=3)).date().isoformat(), 1)],
    }
    total_rows = len(groups)
    for dim in ("provider", "model", "provider_model", "owner", "cohort", "key", "day"):
        page = client.get(f"{REPORTS}/", params={"group_by": dim, "limit": 100})
        assert page.status_code == 200, (dim, page.status_code)
        rendered = _summary_group_map(page.text)
        # actual tbody cardinality == the seed's distinct group count for the dim
        assert len(rendered) == cardinality[dim], (dim, rendered)
        # summed rendered request counts cover the whole seeded scope exactly once
        assert sum(rendered.values()) == total_rows, (dim, sum(rendered.values()))
        # representative expected labels/IDs carry their seeded request counts
        for label, count in representative[dim]:
            assert rendered.get(label) == count, (dim, label, rendered.get(label), rendered)


def test_02_filters_and_time_bounds(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    # provider filter narrows to that provider only
    page = client.get(f"{REPORTS}/", params={"group_by": "provider", "provider": "prov-a", "limit": 100})
    assert page.status_code == 200
    assert "prov-a" in page.text and "prov-b" not in page.text
    # owner filter (owner_b owns prov-b/c/d rows; not prov-zero)
    page = client.get(f"{REPORTS}/", params={"group_by": "provider", "owner_id": data["owner_b"], "limit": 100})
    assert page.status_code == 200
    assert "prov-b" in page.text and "prov-zero" not in page.text
    # cohort filter (cohort_a has prov-missing; not prov-d which is cohort_b)
    page = client.get(f"{REPORTS}/", params={"group_by": "provider", "cohort_id": data["cohort_a"], "limit": 100})
    assert page.status_code == 200
    assert "prov-missing" in page.text and "prov-d" not in page.text
    # inclusive aware-UTC window: only the 1h-ago prov-zero row falls inside
    start = (NOW - timedelta(hours=1.5)).isoformat()
    end = (NOW - timedelta(hours=0.5)).isoformat()
    page = client.get(f"{REPORTS}/", params={"group_by": "provider", "start_at": start, "end_at": end, "limit": 100})
    assert page.status_code == 200
    assert "prov-zero" in page.text and "prov-b" not in page.text
    # end < start is a 400 with a report recovery link
    bad = client.get(f"{REPORTS}/", params={"group_by": "provider", "start_at": end, "end_at": start, "limit": 100})
    assert bad.status_code == 400
    assert "/admin/reports/" in bad.text


def test_03_cost_availability_zero_missing_mixed(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    page = client.get(f"{REPORTS}/", params={"group_by": "provider", "limit": 100})
    assert page.status_code == 200
    zero_row = _row_for(page.text, "prov-zero")
    assert zero_row is not None and zero_row.count("0 EUR") == 2
    assert "unavailable" not in zero_row  # a genuine known zero stays zero
    # Provider-reported compact count + exact status evidence in the title.
    assert "0/1 known" in zero_row
    assert "No cost data (0 of 1 rows known)" in zero_row
    missing_row = _row_for(page.text, "prov-missing")
    assert missing_row is not None and "unavailable" in missing_row
    mixed_row = _row_for(page.text, "prov-mixed")
    assert mixed_row is not None
    # BOTH the estimated and the actual fields are partial for prov-mixed,
    # so the "incomplete" label appears for each and neither is unavailable.
    assert mixed_row.count("incomplete (partial; missing rows excluded)") == 2
    assert "unavailable" not in mixed_row


def test_04_grouping_key_final_tie_break(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    page = client.get(f"{REPORTS}/", params={"group_by": "provider", "limit": 100})
    assert page.status_code == 200
    # Both tie groups have request_count=1 and the same last_seen_at; the
    # stable grouping_key FINAL tie-break orders the higher key first.
    pos_a = page.text.find("<th scope=\"row\">prov-tiea</th>")
    pos_b = page.text.find("<th scope=\"row\">prov-tieb</th>")
    assert pos_a != -1 and pos_b != -1, (pos_a, pos_b)
    assert pos_b < pos_a


def test_05_summary_source_cap_plus_one_refusal(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = env
    client = data["client"]
    assert data["ledger_count"] > 3
    monkeypatch.setattr(admin_reports, "GUI_USAGE_REPORT_SOURCE_MAX_ROWS", 3)
    refused = client.get(f"{REPORTS}/", params={"group_by": "provider", "limit": 100})
    assert refused.status_code == 400
    assert "bounded source limit of 3" in refused.text
    # The refusal is recoverable WITHIN the page: the existing report/filter
    # form is rendered (submitted scope prefilled) with the bound error -
    # no result rows, no empty "no groups" state, no completeness claim.
    assert 'action="/admin/reports/"' in refused.text
    assert 'name="provider"' in refused.text
    assert "No groups in the accepted scope" not in refused.text
    # Entering a narrowing filter through the form reaches an accepted report.
    narrowed = client.get(
        f"{REPORTS}/", params={"group_by": "provider", "provider": "prov-a", "limit": 100}
    )
    assert narrowed.status_code == 200
    rendered = _summary_group_map(narrowed.text)
    assert rendered == {"prov-a": 3}


def test_06_live_burn_provenance_and_cap(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = env
    client = data["client"]
    page = client.get(f"{REPORTS}/live-burn")
    assert page.status_code == 200
    # Chat-only aggregates: exactly the two seeded triggered chat rows.
    def _dd(label: str) -> str:
        m = re.search(rf"<dt>{re.escape(label)}</dt>\s*<dd[^>]*>\s*([^<\s]+)", page.text)
        assert m is not None, label
        return m.group(1).strip()

    assert _dd("Triggered total") == "2"
    assert _dd("Stop reason: tokens") == "1"
    assert _dd("Stop reason: cost") == "1"
    assert _dd("Stop reason: both") == "0"
    assert _dd("Final provider usage available") == "1"
    assert _dd("Final provider usage missing") == "1"
    assert "interrupted/estimated rows; never backfilled" in page.text
    # The cap counts ALL matched ledger rows, not only the chat rows:
    # with a bound of 3 the 14-row unfiltered scope is refused even though
    # only 2 rows carry live-burn metadata.
    monkeypatch.setattr(admin_reports, "GUI_USAGE_REPORT_SOURCE_MAX_ROWS", 3)
    refused = client.get(f"{REPORTS}/live-burn")
    assert refused.status_code == 400
    assert "bounded source limit of 3" in refused.text
    # The refusal is recoverable WITHIN the page: the existing report/filter
    # form is rendered with the bound error - no aggregates, no count claims.
    assert 'action="/admin/reports/live-burn"' in refused.text
    assert 'name="provider"' in refused.text
    assert "Triggered total" not in refused.text
    # Narrowing to the provider that carries the live-burn rows (3 rows,
    # within the bound of 3) reaches an accepted report again.
    narrowed = client.get(f"{REPORTS}/live-burn", params={"provider": "prov-a"})
    assert narrowed.status_code == 200
    dd = re.search(r"<dt>Triggered total</dt>\s*<dd[^>]*>\s*([^<\s]+)", narrowed.text)
    assert dd is not None and dd.group(1).strip() == "2"


# ---------------------------------------------------------------------------
# Slice 2: safe strict-JSON export
# ---------------------------------------------------------------------------


def test_07_export_exact_json_unchanged_accounting(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    form = client.get(f"{REPORTS}/export")
    assert form.status_code == 200
    csrf = _csrf(form.text)
    before = _unrelated_digests(data)
    resp = client.post(
        f"{REPORTS}/export",
        data={
            "csrf_token": csrf,
            "confirm_export": "1",
            "reason": REASON_EXPORT,
            "limit": str(data["ledger_count"]),
        },
    )
    assert resp.status_code == 200, resp.text[:400]
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert resp.headers.get("Cache-Control") == "no-store"
    assert "application/json" in resp.headers.get("Content-Type", "")
    content = resp.text
    assert "NaN" not in content
    payload = json.loads(content)
    assert payload["scope"]["row_count"] == data["ledger_count"]
    assert payload["scope"]["limit"] == data["ledger_count"]
    assert len(payload["rows"]) == data["ledger_count"]
    export_fields = {f.name for f in dataclass_fields(UsageExportRow)}
    for row in payload["rows"]:
        assert set(row.keys()) == export_fields
    by_request = {row["request_id"]: row for row in payload["rows"]}
    a1 = by_request[f"req-214-a1-{data['suffix']}"]
    # exact raw machine unit: the Numeric(18,9) DB value as its exact string
    # (never a float), matching the stored 9-decimal representation.
    assert a1["estimated_cost_eur"] == "10.000000000"
    assert a1["actual_cost_eur"] == "8.000000000"
    assert a1["gateway_key_id"] == data["key_a1"]  # canonical UUID string
    assert "T" in a1["created_at"]  # ISO-8601 datetime
    miss = by_request[f"req-214-miss-{data['suffix']}"]
    assert miss["estimated_cost_eur"] is None  # missing cost stays null, never zero
    assert miss["actual_cost_eur"] is None
    audits = _audit_rows(data["database_url"], action="admin_usage_export_json")
    assert any(REASON_EXPORT in (a["note"] or "") for a in audits)
    after = _unrelated_digests(data)
    assert after["keys"] == before["keys"]
    assert after["ledger"] == before["ledger"]
    assert after["quota"] == before["quota"]


def test_08_export_overbound_and_validation(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    form = client.get(f"{REPORTS}/export")
    csrf = _csrf(form.text)
    # overbound: cap+1 with limit=5 refuses the 14-row scope, no partial
    resp = client.post(
        f"{REPORTS}/export",
        data={"csrf_token": csrf, "confirm_export": "1", "reason": REASON_EXPORT, "limit": "5"},
    )
    assert resp.status_code == 400
    assert "configured export ceiling is 5" in resp.text
    assert "No partial export was produced" in resp.text
    # missing confirm is a 400
    resp = client.post(
        f"{REPORTS}/export", data={"csrf_token": csrf, "reason": REASON_EXPORT, "limit": "5"}
    )
    assert resp.status_code == 400
    assert "Confirm the JSON export" in resp.text
    # missing reason is a 400
    resp = client.post(
        f"{REPORTS}/export", data={"csrf_token": csrf, "confirm_export": "1", "limit": "5"}
    )
    assert resp.status_code == 400
    assert "Enter an audit reason" in resp.text


# ---------------------------------------------------------------------------
# Slice 3: complete filter-preserving navigation on a real paged list
# ---------------------------------------------------------------------------


def test_09_keys_list_unfiltered_first_page(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    # unfiltered first page: the None-guard must not 500, honest page state
    page = client.get("/admin/keys")
    assert page.status_code == 200
    assert f"{len(data['keys'])} rows shown" in page.text
    assert "No more rows" in page.text
    assert "Beginning" in page.text
    assert _nav_url(page.text, "next") is None


def test_10_keys_list_two_cohort_repeated_filter_navigation(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    ca, cb = data["cohort_a"], data["cohort_b"]
    p1 = client.get("/admin/keys", params={"cohort_id": [ca, cb], "limit": 2})
    assert p1.status_code == 200
    assert _nav_url(p1.text, "next") == f"/admin/keys?cohort_id={ca}&cohort_id={cb}&limit=2&offset=2"
    assert _nav_url(p1.text, "prev") is None
    p2 = client.get("/admin/keys", params={"cohort_id": [ca, cb], "limit": 2, "offset": 2})
    assert p2.status_code == 200
    assert _nav_url(p2.text, "next") == f"/admin/keys?cohort_id={ca}&cohort_id={cb}&limit=2&offset=4"
    assert _nav_url(p2.text, "prev") == f"/admin/keys?cohort_id={ca}&cohort_id={cb}&limit=2&offset=0"
    p3 = client.get("/admin/keys", params={"cohort_id": [ca, cb], "limit": 2, "offset": 4})
    assert p3.status_code == 200
    assert "No more rows" in p3.text
    assert _nav_url(p3.text, "prev") == f"/admin/keys?cohort_id={ca}&cohort_id={cb}&limit=2&offset=2"


# ---------------------------------------------------------------------------
# Pass-2 helpers: pricing review flow, native service-level fault / lock cases
# ---------------------------------------------------------------------------


def _pricing_form_csrf(client: TestClient) -> str:
    page = client.get(f"{REPORTS}/pricing-disable")
    assert page.status_code == 200
    return _csrf(page.text)


def _preview_pricing(client: TestClient, provider: str, model: str, reason: str) -> TestClient:
    csrf = _pricing_form_csrf(client)
    return client.post(
        f"{REPORTS}/pricing-disable/preview",
        data={"csrf_token": csrf, "provider": provider, "model": model, "reason": reason},
    )


def _extract_token(page_html: str) -> str:
    return TOKEN_RE.search(page_html).group(1)


def _apply_pricing(client: TestClient, csrf: str, token: str) -> TestClient:
    return client.post(
        f"{REPORTS}/pricing-disable/apply",
        data={"csrf_token": csrf, "review_token": token, "confirm_apply": "1"},
    )


async def _pricing_state(database_url: str, rule_id: str) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await session.get(PricingRule, uuid.UUID(rule_id))
            assert row is not None, rule_id
            return {
                "enabled": bool(row.enabled),
                "pricing_metadata": dict(row.pricing_metadata or {}),
                "input_price_per_1m": row.input_price_per_1m,
            }
    finally:
        await engine.dispose()


def _pricing_enabled(database_url: str, rule_id: str) -> bool:
    return asyncio.run(_pricing_state(database_url, rule_id))["enabled"]


async def _pricing_enabled_updated(database_url: str) -> dict[str, tuple[bool, str]]:
    """``{id: (enabled, updated_at_iso)}`` for EVERY pricing row (oracle)."""
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (await session.execute(select(PricingRule))).scalars().all()
            return {str(r.id): (bool(r.enabled), r.updated_at.isoformat()) for r in rows}
    finally:
        await engine.dispose()


def _pricing_enabled_updated_sync(database_url: str) -> dict[str, tuple[bool, str]]:
    return asyncio.run(_pricing_enabled_updated(database_url))


def _edit_pricing_field(database_url: str, rule_id: str, field: str, value: Any) -> None:
    async def _run() -> None:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    row = await session.get(PricingRule, uuid.UUID(rule_id))
                    assert row is not None
                    setattr(row, field, value)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _create_pricing_rule(database_url: str, provider: str, model: str, *, days_ago: int) -> str:
    async def _run() -> str:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    row = await PricingRulesRepository(session).create_pricing_rule(
                        provider=provider,
                        upstream_model=model,
                        valid_from=NOW - timedelta(days=days_ago),
                        endpoint="/v1/chat/completions",
                        currency="USD",
                        input_price_per_1m=Decimal("1"),
                        output_price_per_1m=Decimal("2"),
                        pricing_metadata={"policy": "late-member"},
                        enabled=True,
                    )
                    return str(row.id)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


async def _late_rollback(database_url: str, rule_id: str, actor_id: str) -> None:
    """Native late-audit fault: the real disable + audit flush run, then the
    transaction is forced to fail so the WHOLE caller transaction rolls back."""
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as s:
            async with s.begin():
                plan = await PricingRuleService(
                    pricing_rules_repository=PricingRulesRepository(s),
                    audit_repository=AuditRepository(s),
                ).preview_disable_model(provider="prb", model="mrb")
        assert plan.row_count == 1
        raised = False
        async with factory() as s:
            real_audit = AuditRepository(s)

            class _LateFail:
                async def add_audit_log(self, **kwargs: Any) -> None:
                    await real_audit.add_audit_log(**kwargs)
                    await s.flush()  # the real audit write is flushed first
                    raise RuntimeError("214 late-audit-injected")

            try:
                async with s.begin():
                    await PricingRuleService(
                        pricing_rules_repository=PricingRulesRepository(s),
                        audit_repository=_LateFail(),
                    ).apply_disable_model_reviewed(
                        plan, actor_admin_id=uuid.UUID(actor_id), reason=REASON_APPLY
                    )
            except RuntimeError:
                raised = True
        assert raised
    finally:
        await engine.dispose()


async def _blocked_lock(database_url: str, rule_id: str, actor_id: str) -> dict[str, Any]:
    """Native blocked-lock / cached-ORM interleaving on one owned PG:
    B holds a FOR UPDATE lock and edits the policy; A (with the row preloaded
    in its identity map) applies and waits on B's lock; after B commits, A's
    populate_existing refresh sees the fresh policy and goes stale.

    B polls ``pg_blocking_pids(a_pid)`` -- A's backend, captured from A before
    it blocks -- to OBSERVE that A is waiting on B's lock.  B is the blocker,
    so the query must target A's pid, not B's own.  ``_a_apply`` returns its
    outcome and the stale error is caught OUTSIDE ``A.begin`` so the caller
    transaction rolls back, matching the GUI controller.
    """
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    out: dict[str, Any] = {}
    try:
        async with factory() as s:
            async with s.begin():
                plan = await PricingRuleService(
                    pricing_rules_repository=PricingRulesRepository(s),
                    audit_repository=AuditRepository(s),
                ).preview_disable_model(provider="prb2", model="mrb2")
        assert plan.row_count == 1

        async with factory() as B:
            async with B.begin():
                locked_b = await PricingRulesRepository(B).lock_pricing_rules_for_review((uuid.UUID(rule_id),))
                assert len(locked_b) == 1
                out["b_pid"] = (await B.execute(text("select pg_backend_pid()"))).scalar()

                async def _a_apply() -> str:
                    async with factory() as A:
                        try:
                            async with A.begin():
                                cached = await A.get(PricingRule, uuid.UUID(rule_id))
                                assert cached is not None  # strong reference in A's identity map
                                out["a_pid"] = (await A.execute(text("select pg_backend_pid()"))).scalar()
                                await PricingRuleService(
                                    pricing_rules_repository=PricingRulesRepository(A),
                                    audit_repository=AuditRepository(A),
                                ).apply_disable_model_reviewed(
                                    plan, actor_admin_id=uuid.UUID(actor_id), reason=REASON_APPLY
                                )
                            return "applied"
                        except PricingDisableStaleError:
                            return "stale"

                a_task = asyncio.create_task(_a_apply())
                blocking: list[Any] = []
                for _ in range(50):
                    await asyncio.sleep(0.2)
                    a_pid = out.get("a_pid")
                    if not a_pid:
                        continue
                    blocking = (
                        (await B.execute(text("select pg_blocking_pids(:a_pid)"), {"a_pid": a_pid}))
                        .scalars()
                        .first()
                        or []
                    )
                    if blocking:
                        break
                out["blocking"] = list(blocking)
                # B edits the policy and commits, releasing the lock.
                locked_b[0].pricing_metadata = {"policy": "changed-after-preview"}
            # B committed here; A can now acquire the lock.
            out["a"] = await a_task
    finally:
        await engine.dispose()
    return out


async def _list_usage_for_admin(database_url: str) -> list[dict[str, Any]]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = await UsageLedgerRepository(session).list_usage_for_admin(limit=100, offset=0)
            return [{"id": str(r.id), "request_id": r.request_id} for r in rows]
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Slice 4: reviewed matching-model pricing disable (HTTP, real auth/CSRF)
# ---------------------------------------------------------------------------


def test_11_pricing_preview_apply_actor_reason_scope(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    url = data["database_url"]
    pm = data["pricing"]["pmain"]
    reviewed_ids = set(pm)
    # Full price state (every column) and the body (every column except the
    # two a successful apply legitimately touches: enabled + updated_at).
    before_price_full = _full_table_digest(url, PricingRule)
    before_price_body = _full_table_digest(url, PricingRule, exclude=frozenset({"enabled", "updated_at"}))
    before_enabled_updated = _pricing_enabled_updated_sync(url)
    before_all_audit = {a["id"] for a in _audit_rows(url)}
    resp = _preview_pricing(client, "pmain", "mmain", REASON_APPLY)
    assert resp.status_code == 200, resp.text[:400]
    assert "pmain / mmain" in resp.text
    assert "2 pricing rule(s) to disable" in resp.text
    assert REASON_APPLY in resp.text  # the reviewed reason, verbatim
    assert pm[0] in resp.text and pm[1] in resp.text  # every reviewed row accessible
    # A preview only locks and reads: the FULL price state (every column,
    # including enabled and updated_at) is preserved byte-for-byte.
    assert _full_table_digest(url, PricingRule) == before_price_full
    # ...and it writes no audit of any kind (read-only preview).
    assert {a["id"] for a in _audit_rows(url)} == before_all_audit
    csrf = _csrf(resp.text)
    token = _extract_token(resp.text)
    data["pmain_token"] = token
    before = {a["id"] for a in _audit_rows(url, action="pricing_rule_disabled")}
    apply_resp = _apply_pricing(client, csrf, token)
    assert apply_resp.status_code == 200, apply_resp.text[:400]
    # the disabled count is rendered inside <strong>, so assert the phrase
    # without the count (the exact count is proven by the two audits below).
    assert "Applied:" in apply_resp.text and "pricing rule(s) disabled" in apply_resp.text
    # Successful apply: EVERY other price column (all rows) and every
    # unreviewed row is byte-for-byte unchanged - the only columns that may
    # change are `enabled` and `updated_at`, and only on the reviewed IDs.
    assert _full_table_digest(url, PricingRule, exclude=frozenset({"enabled", "updated_at"})) == before_price_body
    after_enabled_updated = _pricing_enabled_updated_sync(url)
    assert set(after_enabled_updated) == set(before_enabled_updated)  # no rows added/dropped
    for rid, (b_en, b_updated) in before_enabled_updated.items():
        a_en, a_updated = after_enabled_updated[rid]
        if rid in reviewed_ids:
            assert b_en is True and a_en is False  # the reviewed rows get disabled
        else:
            assert a_en == b_en, rid  # unreviewed enabled state unchanged
            assert a_updated == b_updated, rid  # unreviewed row was never touched
    new = [a for a in _audit_rows(url, action="pricing_rule_disabled") if a["id"] not in before]
    assert len(new) == 2
    assert {a["entity_id"] for a in new} == reviewed_ids  # exact reviewed scope, nothing else
    assert all(a["note"] == REASON_APPLY for a in new)  # verbatim reason per row
    assert all(a["admin_user_id"] == data["admin_id"] for a in new)  # session-derived actor
    assert _pricing_enabled(url, pm[0]) is False
    assert _pricing_enabled(url, pm[1]) is False


def test_12_pricing_exact_repeat_noop(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    pm = data["pricing"]["pmain"]
    token = data["pmain_token"]
    before = {a["id"] for a in _audit_rows(data["database_url"], action="pricing_rule_disabled")}
    apply_resp = _apply_pricing(client, _pricing_form_csrf(client), token)
    assert apply_resp.status_code == 200
    assert "Already disabled" in apply_resp.text
    new = [a for a in _audit_rows(data["database_url"], action="pricing_rule_disabled") if a["id"] not in before]
    assert new == []  # honest no-op: no second disable, no duplicate audit
    assert _pricing_enabled(data["database_url"], pm[0]) is False


def test_13_pricing_policy_edit_is_stale(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    po = data["pricing"]["ppolicy"]
    resp = _preview_pricing(client, "ppolicy", "mpolicy", REASON_APPLY)
    assert resp.status_code == 200
    token, csrf = _extract_token(resp.text), _csrf(resp.text)
    _edit_pricing_field(data["database_url"], po, "pricing_metadata", {"policy": "changed-after-preview"})
    apply_resp = _apply_pricing(client, csrf, token)
    assert apply_resp.status_code == 400
    assert "Preview the scope again" in apply_resp.text
    assert _pricing_enabled(data["database_url"], po) is True
    assert _audit_rows(data["database_url"], action="pricing_rule_disabled", entity_id=po) == []


def test_14_pricing_price_edit_is_stale(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    pp = data["pricing"]["pprice"]
    resp = _preview_pricing(client, "pprice", "mprice", REASON_APPLY)
    assert resp.status_code == 200
    token, csrf = _extract_token(resp.text), _csrf(resp.text)
    _edit_pricing_field(data["database_url"], pp, "input_price_per_1m", Decimal("99"))
    apply_resp = _apply_pricing(client, csrf, token)
    assert apply_resp.status_code == 400
    assert "Preview the scope again" in apply_resp.text
    assert _pricing_enabled(data["database_url"], pp) is True
    assert _audit_rows(data["database_url"], action="pricing_rule_disabled", entity_id=pp) == []


def test_15_pricing_new_member_is_stale(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    pmem = data["pricing"]["pmember"]
    resp = _preview_pricing(client, "pmember", "mmember", REASON_APPLY)
    assert resp.status_code == 200
    token, csrf = _extract_token(resp.text), _csrf(resp.text)
    # a newly matching enabled row appears after the preview
    new_id = _create_pricing_rule(data["database_url"], "pmember", "mmember", days_ago=3)
    apply_resp = _apply_pricing(client, csrf, token)
    assert apply_resp.status_code == 400
    assert "Preview the scope again" in apply_resp.text
    # neither the reviewed row nor the unreviewed new row is disabled
    assert _pricing_enabled(data["database_url"], pmem) is True
    assert _pricing_enabled(data["database_url"], new_id) is True
    assert _audit_rows(data["database_url"], action="pricing_rule_disabled", entity_id=pmem) == []


def test_16_pricing_mixed_flags_is_stale(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    px = data["pricing"]["pmixed"]
    before_audit = {a["id"] for a in _audit_rows(data["database_url"], action="pricing_rule_disabled")}
    resp = _preview_pricing(client, "pmixed", "mmixed", REASON_APPLY)
    assert resp.status_code == 200
    token, csrf = _extract_token(resp.text), _csrf(resp.text)
    # part of the scope is disabled after the preview (visible mixed drift)
    _edit_pricing_field(data["database_url"], px[1], "enabled", False)
    apply_resp = _apply_pricing(client, csrf, token)
    assert apply_resp.status_code == 400
    assert "Preview the scope again" in apply_resp.text
    assert _pricing_enabled(data["database_url"], px[0]) is True
    assert _pricing_enabled(data["database_url"], px[1]) is False
    # the mixed refusal created NO new audit (earlier scopes' audits are unaffected)
    after_audit = {a["id"] for a in _audit_rows(data["database_url"], action="pricing_rule_disabled")}
    assert after_audit == before_audit


# ---------------------------------------------------------------------------
# Slice 5: native preservation / rollback / new-lock proofs on the owned PG
# ---------------------------------------------------------------------------


def test_17_pricing_late_audit_rolls_back_whole_transaction(env: dict[str, Any]) -> None:
    data = env
    url = data["database_url"]
    prb = data["pricing"]["prb"]
    before = _unrelated_digests(data)
    before_price = _full_table_digest(url, PricingRule)  # FULL pricing table, every column
    before_audit = [a["id"] for a in _audit_rows(url, action="pricing_rule_disabled")]
    asyncio.run(_late_rollback(url, prb, data["admin_id"]))
    after = _unrelated_digests(data)
    after_price = _full_table_digest(url, PricingRule)
    # the whole caller transaction rolled back: the FULL pricing table (every
    # column, including enabled and updated_at) plus key, ledger, quota and
    # audit are all byte-for-byte unchanged - including the audit that was
    # flushed before the fault and the in-flight disable.
    assert after_price == before_price
    assert after["keys"] == before["keys"]
    assert after["ledger"] == before["ledger"]
    assert after["quota"] == before["quota"]
    assert after["audit"] == before["audit"]
    assert [a["id"] for a in _audit_rows(url, action="pricing_rule_disabled")] == before_audit
    assert _pricing_enabled(url, prb) is True


def test_18_pricing_lock_waits_and_rechecks_fresh_policy(env: dict[str, Any]) -> None:
    data = env
    url = data["database_url"]
    prb2 = data["pricing"]["prb2"]
    out = asyncio.run(_blocked_lock(url, prb2, data["admin_id"]))
    # A actually waited on B's row lock: pg_blocking_pids(a_pid), polled
    # through B, lists B's own backend PID as the blocker of A.
    assert out["blocking"], "A was not observed waiting on B's lock"
    assert out["b_pid"] in out["blocking"], "B was not observed as the blocker of A"
    # After B committed the policy edit, A's populate_existing refresh saw the
    # fresh facts and went stale: no disable, no audit.
    assert out["a"] == "stale"
    state = asyncio.run(_pricing_state(url, prb2))
    assert state["enabled"] is True
    assert state["pricing_metadata"] == {"policy": "changed-after-preview"}
    assert _audit_rows(url, action="pricing_rule_disabled", entity_id=prb2) == []


def test_19_usage_list_tied_primary_order_is_deterministic(env: dict[str, Any]) -> None:
    data = env
    rows = asyncio.run(_list_usage_for_admin(data["database_url"]))
    by_id = {r["request_id"]: r["id"] for r in rows}
    order = {r["request_id"]: i for i, r in enumerate(rows)}
    t1 = f"req-214-t1-{data['suffix']}"
    t2 = f"req-214-t2-{data['suffix']}"
    assert t1 in order and t2 in order
    # same created_at -> adjacent in the list
    assert abs(order[t1] - order[t2]) == 1
    # the deterministic id tie-break (id.asc) fixes their relative order
    if by_id[t1] < by_id[t2]:
        assert order[t1] < order[t2]
    else:
        assert order[t2] < order[t1]


# ---------------------------------------------------------------------------
# Slice 6: effective FX lookup
# ---------------------------------------------------------------------------


def test_20_fx_lookup_present_and_missing(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    present = client.get(f"{REPORTS}/fx-lookup", params={"base_currency": "EUR", "quote_currency": "USD"})
    assert present.status_code == 200
    assert "Effective rate" in present.text
    assert "1.1" in present.text  # rate 1.10
    assert "214-test-fx" in present.text  # source
    assert "USD per 1 EUR" in present.text
    missing = client.get(f"{REPORTS}/fx-lookup", params={"base_currency": "EUR", "quote_currency": "GBP"})
    assert missing.status_code == 200
    assert "No FX rate is effective for" in missing.text
    assert "EUR / GBP" in missing.text
    assert "honest missing state" in missing.text

