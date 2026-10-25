"""Owned-PostgreSQL qualification for 195-a multi-value list filters.

Real PG16 (fresh owned container — never an ambient URL) proofs for the
multi-filter behavior that unit fakes cannot establish:

- OR-within / AND-across semantics on the keys page: two selected
  cohorts return the UNION, the third cohort is excluded, and a status
  filter narrows that union;
- duplicate-free owner membership when one owner has keys in two
  selected cohorts (GatewayKey ANY/EXISTS, not a JOIN fan-out);
- the multi predicate runs in SQL BEFORE LIMIT/OFFSET (a page beyond
  the first still returns only matching rows);
- the usage provider family keeps its case-insensitive LIKE semantics
  for multi values;
- audit target_type parents OR-scope the ``audit_target`` choices in
  SQL BEFORE the 100-choice limit, including a >200-character parent
  value preserved in full;
- usage/audit CSV exports follow the same validated multi scope and
  persist JSON-safe effective-filter metadata (UUID tuples -> lists);
- HTTP (real uvicorn + authenticated session): the no-JS
  repeated-parameter AND newline-fallback serializations match the
  same rows as the JS chip submission, legacy one-value links keep
  working, an invalid member is a 400 without echoing the value, the
  no-selected lookup does not crash, and the lookup's explicit
  100-value / 1024-char bounds answer 400.

All data is synthetic and fictional (no real people, providers, or
secrets); the module never points at ``DATABASE_URL``.
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

import httpx
import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    Cohort,
    GatewayKey,
    Institution,
    Owner,
    UsageLedger,
    AdminUser,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_export_service import AdminCsvExportService
from slaif_gateway.services.admin_record_choices import load_choices
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# Reuse the qualified owned PostgreSQL fixture (never an ambient fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture

ADMIN_EMAIL = "multiselect-admin@example.org"
ADMIN_PASSWORD = "correct horse battery staple"
SUFFIX = uuid.uuid4().hex[:10]
BASE_TIME = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
LONG_PARENT = "probe_entity_type_" + "e" * 232  # 252 chars (>200, <=1024)

PROV_ALPHA = f"prov-alpha-{SUFFIX}"
PROV_BETA = f"prov-beta-{SUFFIX}"
PROV_GAMMA = f"prov-gamma-{SUFFIX}"

BULK_PER_COHORT = 30
BULK_GAMMA = 20


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def _seed(database_url: str) -> dict[str, object]:
    """Create the deterministic fictional multi-filter dataset."""

    async def _run() -> dict[str, object]:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        ids: dict[str, object] = {}
        try:
            async with session_factory() as session:
                async with session.begin():
                    now = datetime.now(UTC)
                    admin = AdminUser(
                        id=uuid.uuid4(),
                        email=ADMIN_EMAIL,
                        display_name="MultiSelect Admin",
                        password_hash=hash_admin_password(ADMIN_PASSWORD),
                        role="admin",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(admin)

                    institution = Institution(
                        id=uuid.uuid4(),
                        name=f"SLAIF University {SUFFIX}",
                        country="SI",
                        created_at=BASE_TIME,
                    )
                    session.add(institution)
                    ids["institution_id"] = institution.id

                    cohorts = {}
                    for tag in ("alpha", "beta", "gamma"):
                        cohort = Cohort(
                            id=uuid.uuid4(),
                            name=f"Cohort{tag.capitalize()}-{SUFFIX}",
                            starts_at=BASE_TIME,
                            ends_at=BASE_TIME + timedelta(days=30),
                            created_at=BASE_TIME + timedelta(minutes=1),
                        )
                        session.add(cohort)
                        cohorts[tag] = cohort.id
                    ids["cohort_alpha"] = cohorts["alpha"]
                    ids["cohort_beta"] = cohorts["beta"]
                    ids["cohort_gamma"] = cohorts["gamma"]

                    owners = {}
                    for tag in ("a", "b", "c", "d"):
                        owner = Owner(
                            id=uuid.uuid4(),
                            name="Multi",
                            surname=f"Owner {tag}",
                            email=f"multi-owner-{tag}-{SUFFIX}@example.org",
                            institution_id=institution.id,
                            created_at=BASE_TIME + timedelta(minutes=2),
                        )
                        session.add(owner)
                        owners[tag] = owner.id
                    ids["owner_a"] = owners["a"]
                    ids["owner_b"] = owners["b"]
                    ids["owner_c"] = owners["c"]
                    ids["owner_d"] = owners["d"]

                    key_fields = dict(
                        # Neutral hint: never bake the gateway key prefix
                        # into synthetic test data (AGENTS).
                        key_hint=f"synthetic-hint-{SUFFIX}",
                        valid_from=BASE_TIME,
                        valid_until=BASE_TIME + timedelta(days=30),
                        allowed_models=["synthetic-model"],
                        allowed_endpoints=["/v1/chat/completions"],
                        created_by_admin_user_id=admin.id,
                    )

                    def add_key(cohort_id, owner_id, *, status, i) -> GatewayKey:
                        key = GatewayKey(
                            id=uuid.uuid4(),
                            public_key_id=f"public-ms-{status}-{i:03d}-{SUFFIX}",
                            token_hash="synthetic_token_hash_" + uuid.uuid4().hex,
                            owner_id=owner_id,
                            cohort_id=cohort_id,
                            status=status,
                            created_at=BASE_TIME + timedelta(minutes=3, seconds=i),
                            **key_fields,
                        )
                        session.add(key)
                        return key

                    # Named keys (asserted individually).
                    ids["key_alpha_a"] = add_key(
                        cohorts["alpha"], owners["a"], status="active", i=100
                    ).id
                    ids["key_beta_a"] = add_key(
                        cohorts["beta"], owners["a"], status="active", i=101
                    ).id
                    ids["key_alpha_b"] = add_key(
                        cohorts["alpha"], owners["b"], status="active", i=102
                    ).id
                    ids["key_beta_c_suspended"] = add_key(
                        cohorts["beta"], owners["c"], status="suspended", i=103
                    ).id
                    ids["key_gamma_d"] = add_key(
                        cohorts["gamma"], owners["d"], status="active", i=104
                    ).id

                    # Bulk keys: union size is large enough to prove the
                    # predicate runs BEFORE LIMIT/OFFSET (60 matching rows
                    # vs 20 gamma rows that must never bleed in).
                    # alpha/beta bulk keys stay with owners b/c so the
                    # duplicate-free owner assertion for owner d (gamma
                    # only) holds; gamma bulk keys go to owner d.
                    bulk_owners_by_tag = {
                        "alpha": [owners["b"], owners["c"]],
                        "beta": [owners["b"], owners["c"]],
                        "gamma": [owners["d"]],
                    }
                    i = 0
                    for tag, count in (
                        ("alpha", BULK_PER_COHORT),
                        ("beta", BULK_PER_COHORT),
                        ("gamma", BULK_GAMMA),
                    ):
                        tag_owners = bulk_owners_by_tag[tag]
                        for n in range(count):
                            add_key(
                                cohorts[tag],
                                tag_owners[(i + n) % len(tag_owners)],
                                status="active",
                                i=i + n,
                            )
                        i += count

                    # Usage rows: two per provider (CSV export scope).
                    # The usage key sits in the GAMMA cohort so the
                    # alpha/beta union counts stay exact.
                    usage_key = GatewayKey(
                        id=uuid.uuid4(),
                        public_key_id=f"public-ms-usage-{SUFFIX}",
                        token_hash="synthetic_token_hash_" + uuid.uuid4().hex,
                        owner_id=owners["a"],
                        cohort_id=cohorts["gamma"],
                        status="active",
                        created_at=BASE_TIME + timedelta(minutes=4),
                        **key_fields,
                    )
                    session.add(usage_key)
                    for j, provider in enumerate(
                        [PROV_ALPHA, PROV_ALPHA, PROV_BETA, PROV_BETA, PROV_GAMMA, PROV_GAMMA]
                    ):
                        session.add(
                            UsageLedger(
                                id=uuid.uuid4(),
                                request_id=f"ms-usage-req-{j}-{SUFFIX}",
                                gateway_key_id=usage_key.id,
                                endpoint="/v1/chat/completions",
                                provider=provider,
                                requested_model=f"ms-model-{SUFFIX}",
                                success=True,
                                accounting_status="finalized",
                                http_status=200,
                                started_at=BASE_TIME + timedelta(hours=1, seconds=j),
                                finished_at=BASE_TIME + timedelta(hours=1, seconds=j)
                                + timedelta(milliseconds=5),
                                created_at=BASE_TIME + timedelta(hours=1, seconds=j),
                            )
                        )

                    # Audit rows: 60 gateway_key + 60 owner entities
                    # (staggered, oldest first) + 5 latest usage_ledger
                    # entities + ONE >200-char entity_type (full-value
                    # multi-parent proof).
                    for j in range(60):
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                admin_user_id=admin.id,
                                action="ms_probe",
                                entity_type="gateway_key",
                                entity_id=uuid.uuid4(),
                                created_at=BASE_TIME + timedelta(hours=2, seconds=j),
                            )
                        )
                    for j in range(60):
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                admin_user_id=admin.id,
                                action="ms_probe",
                                entity_type="owner",
                                entity_id=uuid.uuid4(),
                                created_at=BASE_TIME + timedelta(hours=3, seconds=j),
                            )
                        )
                    for j in range(5):
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                admin_user_id=admin.id,
                                action="ms_probe",
                                entity_type="usage_ledger",
                                entity_id=uuid.uuid4(),
                                created_at=BASE_TIME + timedelta(hours=9, seconds=j),
                            )
                        )
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            admin_user_id=admin.id,
                            action="ms_probe",
                            entity_type=LONG_PARENT,
                            entity_id=uuid.uuid4(),
                            created_at=BASE_TIME + timedelta(hours=4),
                        )
                        )
        finally:
            await engine.dispose()
        return ids

    return asyncio.run(_run())


@pytest.fixture(scope="module")
def ms_env(owned_pg_url: str) -> dict[str, object]:
    return _seed(owned_pg_url)


# ---------------------------------------------------------------------------
# Service-level real-PG proofs
# ---------------------------------------------------------------------------


def _run_on_pg(database_url: str, coro):
    return asyncio.run(coro)


def test_keys_two_cohort_union_third_excluded_and_status_and(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _query() -> list[object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    repo = GatewayKeysRepository(session)
                    rows = await repo.list_keys_for_admin(
                        cohort_id=(
                            uuid.UUID(str(ms_env["cohort_alpha"])),
                            uuid.UUID(str(ms_env["cohort_beta"])),
                        ),
                        limit=200,
                        offset=0,
                    )
                    return rows
        finally:
            await engine.dispose()

    rows = _run_on_pg(owned_pg_url, _query())
    cohort_ids = {str(r.cohort_id) for r in rows}
    # UNION of the two cohorts, exactly (the third cohort never bleeds in).
    assert cohort_ids == {
        str(ms_env["cohort_alpha"]),
        str(ms_env["cohort_beta"]),
    }
    ids = {str(r.id) for r in rows}
    assert str(ms_env["key_alpha_a"]) in ids
    assert str(ms_env["key_beta_a"]) in ids
    assert str(ms_env["key_gamma_d"]) not in ids
    # 2 named + 2 named + 30 + 30 bulk = 64.
    assert len(rows) == 2 + 2 + BULK_PER_COHORT + BULK_PER_COHORT


def test_keys_union_narrowed_by_status_and(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _query() -> list[object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    repo = GatewayKeysRepository(session)
                    return await repo.list_keys_for_admin(
                        cohort_id=(
                            uuid.UUID(str(ms_env["cohort_alpha"])),
                            uuid.UUID(str(ms_env["cohort_beta"])),
                        ),
                        status="suspended",
                        limit=200,
                        offset=0,
                    )
        finally:
            await engine.dispose()

    rows = _run_on_pg(owned_pg_url, _query())
    # AND across fields: only the single suspended beta key survives.
    assert [str(r.id) for r in rows] == [str(ms_env["key_beta_c_suspended"])]


def test_owner_membership_is_duplicate_free_across_two_cohorts(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _query() -> list[object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    repo = OwnersRepository(session)
                    return await repo.list_owners_for_admin(
                        cohort_id=(
                            uuid.UUID(str(ms_env["cohort_alpha"])),
                            uuid.UUID(str(ms_env["cohort_beta"])),
                        ),
                        limit=200,
                        offset=0,
                    )
        finally:
            await engine.dispose()

    rows = _run_on_pg(owned_pg_url, _query())
    owner_ids = [str(r.id) for r in rows]
    # Owner A holds keys in BOTH selected cohorts and appears exactly ONCE
    # (ANY/EXISTS, no JOIN fan-out); owner D (gamma only) is excluded.
    assert owner_ids.count(str(ms_env["owner_a"])) == 1
    assert str(ms_env["owner_a"]) in owner_ids
    assert str(ms_env["owner_b"]) in owner_ids
    assert str(ms_env["owner_c"]) in owner_ids
    assert str(ms_env["owner_d"]) not in owner_ids


def test_multi_predicate_runs_in_sql_before_limit_offset(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _query() -> list[object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    repo = GatewayKeysRepository(session)
                    cohort_ids = (
                        uuid.UUID(str(ms_env["cohort_alpha"])),
                        uuid.UUID(str(ms_env["cohort_beta"])),
                    )
                    page = await repo.list_keys_for_admin(
                        cohort_id=cohort_ids, limit=10, offset=45
                    )
                    tail = await repo.list_keys_for_admin(
                        cohort_id=cohort_ids, limit=10, offset=60
                    )
                    end = await repo.list_keys_for_admin(
                        cohort_id=cohort_ids, limit=10, offset=64
                    )
                    return page, tail, end
        finally:
            await engine.dispose()

    page, tail, end = _run_on_pg(owned_pg_url, _query())
    # 64 matching rows (4 named + 60 bulk): offset 45 still returns a
    # FULL page of ONLY matching cohorts (never gamma). If the predicate
    # post-filtered fetched rows, offset 45 would leak unfiltered rows
    # 46..86 and the page would be 40 rows instead of exactly 10.
    assert len(page) == 10
    assert {str(r.cohort_id) for r in page} <= {
        str(ms_env["cohort_alpha"]),
        str(ms_env["cohort_beta"]),
    }
    # The final partial page of the MATCHING set is exact (64 - 60), and
    # offset past its end is empty — post-filter semantics would still
    # return matching rows fetched beyond the offset.
    assert len(tail) == 4
    assert {str(r.cohort_id) for r in tail} <= {
        str(ms_env["cohort_alpha"]),
        str(ms_env["cohort_beta"]),
    }
    assert end == []


def test_usage_provider_like_semantics_multi(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _query() -> list[object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    repo = UsageLedgerRepository(session)
                    return await repo.list_usage_for_admin(
                        provider=(PROV_ALPHA, PROV_BETA),
                        limit=200,
                        offset=0,
                    )
        finally:
            await engine.dispose()

    rows = _run_on_pg(owned_pg_url, _query())
    providers = {r.provider for r in rows}
    assert providers == {PROV_ALPHA, PROV_BETA}
    assert len(rows) == 4
    assert PROV_GAMMA not in providers


def test_audit_target_multi_parent_scope_before_limit_and_full_value(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _query() -> dict[str, object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    unscoped = await load_choices(session, "audit_target")
                    two_type = await load_choices(
                        session, "audit_target", target_type=("gateway_key", "owner")
                    )
                    single_long = await load_choices(
                        session, "audit_target", target_type=(LONG_PARENT,)
                    )
                    mixed_long = await load_choices(
                        session, "audit_target", target_type=("usage_ledger", LONG_PARENT)
                    )
                    return {
                        "unscoped": unscoped,
                        "two_type": two_type,
                        "single_long": single_long,
                        "mixed_long": mixed_long,
                    }
        finally:
            await engine.dispose()

    result = _run_on_pg(owned_pg_url, _query())
    unscoped = result["unscoped"]
    two_type = result["two_type"]
    single_long = result["single_long"]
    mixed_long = result["mixed_long"]

    # Unscoped latest-100 batch: the 5 newest usage_ledger entities plus
    # 95 of the 120 gateway_key/owner entities -> some of the OLDER
    # gateway_key/owner entities are missing.
    unscoped_types = {c.label.split(":")[0] for c in unscoped}
    assert "usage_ledger" in unscoped_types
    assert len(unscoped) == 100

    # Two-parent OR scope BEFORE the LIMIT: exactly the 100 newest of the
    # 120 gateway_key/owner entities; the 5 usage_ledger entities are
    # excluded even though they are the globally newest; and at least one
    # entity that the UNSCOPED batch dropped is present here (proof the
    # scope narrows the candidate set before the 100-cap applies).
    assert {c.label.split(":")[0] for c in two_type} == {"gateway_key", "owner"}
    assert len(two_type) == 100
    unscoped_ids = {c.id for c in unscoped}
    two_type_ids = {c.id for c in two_type}
    assert two_type_ids.isdisjoint(
        {c.id for c in unscoped if c.label.startswith("usage_ledger")}
    )
    assert (two_type_ids - unscoped_ids), (
        "the scoped batch must include candidates the unscoped batch cut"
    )

    # A >200-character parent (within the explicit 1024 bound) reaches the
    # SQL scope in FULL and matches exactly its own entity.
    assert [c.label for c in single_long] == [f"{LONG_PARENT}: {single_long[0].id}"]
    assert mixed_long and {c.label.split(":")[0] for c in mixed_long} == {
        "usage_ledger",
        LONG_PARENT,
    }


def test_audit_selected_hydration_respects_parent_scope(
    owned_pg_url: str,
    ms_env: dict[str, object],
) -> None:
    """A selected target OUTSIDE the chosen parent type is a display
    request, not eligibility: it must not become an eligible choice,
    while an in-scope selected target keeps its authoritative label.
    (Permanent regression for the root-reproduced R5 scope defect.)"""
    target = uuid.uuid4()
    # A DEDICATED probe type: the probe row must not perturb the seeded
    # gateway_key/owner/usage_ledger audit populations that sibling
    # tests count.
    probe_type = f"scope_probe_type_{SUFFIX}"

    async def _run() -> dict[str, object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            action=f"synthetic_scope_probe-{SUFFIX}",
                            entity_type=probe_type,
                            entity_id=target,
                            created_at=BASE_TIME + timedelta(hours=12),
                        )
                    )
            async with factory() as session:
                scoped_out = await load_choices(
                    session, "audit_target", selected=(str(target),), target_type=("owner",)
                )
                scoped_in = await load_choices(
                    session, "audit_target", selected=(str(target),), target_type=(probe_type,)
                )
                return {
                    "scoped_out": scoped_out,
                    "scoped_in": scoped_in,
                }
        finally:
            await engine.dispose()

    result = _run_on_pg(owned_pg_url, _run())
    scoped_out = result["scoped_out"]
    scoped_in = result["scoped_in"]
    # The owner-scoped result is exactly owner entities: the selected
    # out-of-scope id never becomes an eligible choice.
    assert scoped_out, "owner-scoped batch expected from seeded owner entities"
    assert all(c.label.split(":")[0] == "owner" for c in scoped_out)
    assert all(c.id != str(target) for c in scoped_out)
    # The SAME selected id hydrates with its authoritative label when the
    # parent scope covers its type.
    assert any(
        c.id == str(target) and c.label == f"{probe_type}: {target}" for c in scoped_in
    )


def test_audit_selected_hydration_deduplicates_before_limit(
    owned_pg_url: str,
) -> None:
    """6 selected ids x 20 eligible parent types = 120 (id, type) groups:
    the per-id reduction must happen IN SQL BEFORE the 100-limit, or the
    first ids starve later eligible selected ids of their label.
    (Permanent regression for the root-reproduced R5 limit defect.)"""
    targets = [uuid.uuid4() for _ in range(6)]
    parents = tuple(f"scope_probe_type_{i}_{SUFFIX}" for i in range(20))
    now = datetime.now(UTC)
    async def _run() -> list[object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    session.add_all(
                        AuditLog(
                            id=uuid.uuid4(),
                            action=f"synthetic_crowding_probe-{SUFFIX}",
                            entity_type=parent,
                            entity_id=target,
                            created_at=now - timedelta(minutes=i * 10, seconds=j),
                        )
                        for i, target in enumerate(targets)
                        for j, parent in enumerate(parents)
                    )
            async with factory() as session:
                return await load_choices(
                    session,
                    "audit_target",
                    selected=tuple(str(v) for v in targets),
                    target_type=parents,
                )
        finally:
            await engine.dispose()

    choices = _run_on_pg(owned_pg_url, _run())
    returned = {c.id for c in choices}
    assert {str(v) for v in targets} <= returned, (
        "100 grouped type rows starved an eligible selected ID before "
        "unique-id reduction"
    )
    # One label per selected id, each from an eligible parent type.
    for target in targets:
        matches = [c for c in choices if c.id == str(target)]
        assert len(matches) == 1
        assert matches[0].label.split(":")[0] in parents
def test_usage_csv_export_multi_scope_and_json_safe_metadata(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _run() -> dict[str, object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    admin_id = (
                        await session.execute(
                            select(AdminUser.id).where(AdminUser.email == ADMIN_EMAIL)
                        )
                    ).scalar_one()
                    service = AdminCsvExportService(
                        usage_ledger_repository=UsageLedgerRepository(session),
                        audit_repository=AuditRepository(session),
                    )
                    result = await service.export_usage_csv(
                        actor_admin_id=admin_id,
                        reason="integration multi export",
                        limit=50,
                        provider=(PROV_ALPHA, PROV_BETA),
                    )
                    audit_row = (
                        await session.execute(
                            select(AuditLog).where(AuditLog.id == result.audit_log_id)
                        )
                    ).scalar_one()
                    return {
                        "row_count": result.row_count,
                        "content": result.content,
                        "new_values": audit_row.new_values,
                    }
        finally:
            await engine.dispose()

    out = _run_on_pg(owned_pg_url, _run())
    assert out["row_count"] == 4
    body = out["content"].splitlines()
    assert body[0].startswith("created_at,"), body[0]
    joined = "\n".join(body)
    assert joined.count(f",{PROV_ALPHA},") >= 2 or joined.count(PROV_ALPHA) >= 2
    assert joined.count(PROV_BETA) >= 2
    assert PROV_GAMMA not in joined
    # Effective-filter metadata is JSON-safe: UUID/text tuples -> lists,
    # no raw tuple reprs.
    filters = out["new_values"]["filters"]
    json.dumps(out["new_values"])  # must not raise
    assert filters["provider"] == [PROV_ALPHA, PROV_BETA]


def test_audit_csv_export_multi_target_type_scope(
    owned_pg_url: str, ms_env: dict[str, object]
) -> None:
    async def _run() -> dict[str, object]:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    admin_id = (
                        await session.execute(
                            select(AdminUser.id).where(AdminUser.email == ADMIN_EMAIL)
                        )
                    ).scalar_one()
                    service = AdminCsvExportService(
                        usage_ledger_repository=UsageLedgerRepository(session),
                        audit_repository=AuditRepository(session),
                    )
                    result = await service.export_audit_csv(
                        actor_admin_id=admin_id,
                        reason="integration audit multi export",
                        limit=200,
                        target_type=("gateway_key", "owner"),
                    )
                    audit_row = (
                        await session.execute(
                            select(AuditLog).where(AuditLog.id == result.audit_log_id)
                        )
                    ).scalar_one()
                    return {
                        "row_count": result.row_count,
                        "new_values": audit_row.new_values,
                    }
        finally:
            await engine.dispose()

    out = _run_on_pg(owned_pg_url, _run())
    # 60 + 60 seeded entities, none from the other types.
    assert out["row_count"] == 120
    json.dumps(out["new_values"])  # must not raise
    assert out["new_values"]["filters"]["target_type"] == ["gateway_key", "owner"]


# ---------------------------------------------------------------------------
# HTTP: real uvicorn + authenticated session
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _settings_for(database_url: str) -> Settings:
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
    )


@contextmanager
def _run_server(app: object, port: int) -> Iterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("uvicorn thread exited before startup")
            if time.monotonic() > deadline:
                raise TimeoutError("uvicorn startup timeout")
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def ms_client(owned_pg_url: str, ms_env: dict[str, object]) -> Iterator[httpx.Client]:
    app = create_app(_settings_for(owned_pg_url))
    with _run_server(app, _free_port()) as base_url:
        client = httpx.Client(base_url=base_url, follow_redirects=False, timeout=60)
        login_page = client.get("/admin/login")
        assert login_page.status_code == 200
        match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
        assert match, "login CSRF token not rendered"
        response = client.post(
            "/admin/login",
            data={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "csrf_token": match.group(1),
            },
        )
        assert response.status_code in (302, 303), response.text[:300]
        yield client
        client.close()


def _data_rows(html: str) -> int:
    """Count the table's data rows (one row-ordinal cell per row)."""
    return html.count('class="row-ordinal"')


def _cohort_row_count(html: str, cohort_name: str) -> int:
    """Count DATA ROWS of one cohort (scoped to the table's cohort cell).

    Cohort UUIDs may also appear in the choice options of the filter
    controls, so a whole-page substring check would not prove the row
    scope; the ``col-cohort`` cell occurs only in table data rows.
    """
    return html.count(f'<td class="col-cohort">{cohort_name}</td>')


def test_http_repeated_param_union_and_newline_fallback(
    ms_client: httpx.Client, ms_env: dict[str, object]
) -> None:
    alpha = str(ms_env["cohort_alpha"])
    beta = str(ms_env["cohort_beta"])
    alpha_name = f"CohortAlpha-{SUFFIX}"
    beta_name = f"CohortBeta-{SUFFIX}"
    gamma_name = f"CohortGamma-{SUFFIX}"
    alpha_rows = 2 + BULK_PER_COHORT
    beta_rows = 2 + BULK_PER_COHORT

    union_rows = 2 + 2 + BULK_PER_COHORT + BULK_PER_COHORT

    # Repeated parameters (the JS chip submission / no-JS repeated form).
    response = ms_client.get(
        "/admin/keys", params={"limit": "200", "cohort_id": [alpha, beta]}
    )
    assert response.status_code == 200
    assert _data_rows(response.text) == union_rows
    # Both accepted values round-trip into the multi control.
    assert alpha in response.text and beta in response.text
    # Scoped DATA-ROW identity: the rows come from BOTH selected cohorts
    # and NO gamma row bleeds in (the negative evidence the dropped
    # whole-page check provided; options may legitimately list gamma).
    assert _cohort_row_count(response.text, alpha_name) == alpha_rows
    assert _cohort_row_count(response.text, beta_name) == beta_rows
    assert _cohort_row_count(response.text, gamma_name) == 0

    # Newline fallback (the no-JS textarea serialization).
    response = ms_client.get(
        "/admin/keys", params={"limit": "200", "cohort_id": f"{alpha}\n{beta}"}
    )
    assert response.status_code == 200
    assert _data_rows(response.text) == union_rows
    assert _cohort_row_count(response.text, alpha_name) == alpha_rows
    assert _cohort_row_count(response.text, beta_name) == beta_rows
    assert _cohort_row_count(response.text, gamma_name) == 0

    # Legacy one-value link keeps working.
    response = ms_client.get("/admin/keys", params={"limit": "200", "cohort_id": alpha})
    assert response.status_code == 200
    assert _data_rows(response.text) == 2 + BULK_PER_COHORT
    assert _cohort_row_count(response.text, alpha_name) == alpha_rows
    assert _cohort_row_count(response.text, beta_name) == 0
    assert _cohort_row_count(response.text, gamma_name) == 0

    # No parameter = unfiltered.
    response = ms_client.get("/admin/keys", params={"limit": "200"})
    assert _data_rows(response.text) == (
        # 5 named + 60 bulk alpha/beta + 20 bulk gamma + 1 usage key
        5 + 2 * BULK_PER_COHORT + BULK_GAMMA + 1
    )
    # Full row identity: alpha/beta as above, gamma = 1 named + 20 bulk
    # + 1 usage key = 22; 32 + 32 + 22 = 86 total.
    assert _cohort_row_count(response.text, alpha_name) == alpha_rows
    assert _cohort_row_count(response.text, beta_name) == beta_rows
    assert _cohort_row_count(response.text, gamma_name) == 1 + BULK_GAMMA + 1

    # An invalid member is a 400 page that never echoes the value.
    bad = "nope-not-a-uuid"
    response = ms_client.get("/admin/keys", params={"cohort_id": bad})
    assert response.status_code == 400
    assert "valid UUID" in response.text
    assert bad not in response.text


def test_http_lookup_no_selected_and_explicit_bounds(
    ms_client: httpx.Client, ms_env: dict[str, object]
) -> None:
    # No selected values: the empty-sequence boundary works end to end
    # (real session + real PG), and the seeded cohorts hydrate.
    response = ms_client.get("/admin/record-choices", params={"kind": "cohort"})
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    payload = response.json()
    labels = {c["label"] for c in payload["choices"]}
    assert f"CohortAlpha-{SUFFIX}" in labels
    assert f"CohortBeta-{SUFFIX}" in labels
    assert f"CohortGamma-{SUFFIX}" in labels

    # Explicit bounds: 101 selected values -> 400 fixed message (no echo);
    # a 1025-char value -> 400; exactly 100 -> accepted.
    values = [f"sel-{i}-{SUFFIX}" for i in range(101)]
    response = ms_client.get(
        "/admin/record-choices", params={"kind": "owner", "selected": values}
    )
    assert response.status_code == 400
    assert "At most 100 values of at most 1024 characters" in response.text
    assert values[-1] not in response.text

    response = ms_client.get(
        "/admin/record-choices",
        params={"kind": "owner", "selected": ["s" * 1025]},
    )
    assert response.status_code == 400
    assert "s" * 100 not in response.text

    response = ms_client.get(
        "/admin/record-choices",
        params={"kind": "owner", "selected": [f"sel-{i}" for i in range(100)]},
    )
    assert response.status_code == 200


def test_http_lookup_unauthenticated_and_multi_target_type(
    ms_client: httpx.Client, ms_env: dict[str, object]
) -> None:
    anonymous = httpx.Client(
        base_url=str(ms_client.base_url), follow_redirects=False, timeout=30
    )
    try:
        response = anonymous.get(
            "/admin/record-choices", params={"kind": "cohort"}
        )
        assert response.status_code == 303
        assert "/admin/login" in response.headers.get("location", "")
    finally:
        anonymous.close()

    # A >200-character target_type parent is accepted (within the explicit
    # 1024 bound) and scoped in full — the seeded long-parent entity is
    # the only match.
    response = ms_client.get(
        "/admin/record-choices",
        params={"kind": "audit_target", "target_type": LONG_PARENT},
    )
    assert response.status_code == 200
    choices = response.json()["choices"]
    assert len(choices) == 1
    assert choices[0]["label"].startswith(f"{LONG_PARENT}: ")
