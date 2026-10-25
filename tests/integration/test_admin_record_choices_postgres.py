"""Owned-PostgreSQL qualification for admin record-choice controls (192-a).

Covers the exact acceptance conditions found during review:

- latest-100 exact ordering (created_at DESC, id ASC tie-breaker) with ties;
- search reaching OLDER records beyond the initial batch;
- selected-outside-100 hydration across UUID, provider-slug, email, public
  key id and plain model kinds (including multi-selection where one
  selected value sits at the batch tail);
- anonymized-owner eligibility (batch AND selected hydration);
- id search (UUID / public id / entity id) for owner, key, audit target and
  one-time secret;
- model kind includes upstream tokens, pricing tokens and usage history;
- audit targets grouped BEFORE the LIMIT and scoped by target_type;
- request-id kind unions usage-ledger and audit-log request ids;
- DB-bounded queries and canonical vocabularies;
- HTTP: unauthenticated 303, unknown kind 400, and the read-only lookup
  guarantee (no CSRF rotation, no session touch, original-form CSRF POST
  still succeeds).

PostgreSQL is a fresh owned container (labeled, loopback-bound, tmpfs);
never an ambient TEST_DATABASE_URL.
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

import httpx
import pytest
import uvicorn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AdminSession,
    AdminUser,
    AuditLog,
    Cohort,
    FxRate,
    GatewayKey,
    Institution,
    ModelRoute,
    OneTimeSecret,
    Owner,
    PricingRule,
    ProviderConfig,
    UsageLedger,
)
from slaif_gateway.main import create_app
from slaif_gateway.services import admin_record_choices as svc
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# Reuse the qualified owned PostgreSQL fixture (never an ambient fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture

ADMIN_EMAIL = "choices-admin@example.org"
ADMIN_PASSWORD = "correct horse battery staple"
BASE_TIME = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
SEED_SUFFIX = uuid.uuid4().hex[:10]


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------


def _seed_all(database_url: str) -> dict[str, object]:
    """Create deterministic bounded seed rows; returns the ids we assert on."""

    async def _run() -> dict[str, object]:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    now = datetime.now(UTC)
                    admin = AdminUser(
                        id=uuid.uuid4(),
                        email=ADMIN_EMAIL,
                        display_name="Choices Admin",
                        password_hash=hash_admin_password(ADMIN_PASSWORD),
                        role="admin",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(admin)

                    # 105 owners, staggered created_at; owners 103 and 104
                    # share created_at (tie broken by id ASC).
                    owners = []
                    for i in range(105):
                        created = BASE_TIME + timedelta(seconds=i)
                        if i == 104:
                            created = owners[103].created_at
                        owner = Owner(
                            id=uuid.uuid4(),
                            name="Choice",
                            surname=f"Owner {i:03d}",
                            email=f"choice-owner-{i:03d}-{SEED_SUFFIX}@example.org",
                            created_at=created,
                            anonymized_at=None,
                        )
                        session.add(owner)
                        owners.append(owner)
                    # A recently created ANONYMIZED owner: would sit inside
                    # the latest-100 batch if eligibility were bypassed.
                    anonymized = Owner(
                        id=uuid.uuid4(),
                        name="Choice",
                        surname="Anonymized",
                        email=f"choice-anon-{SEED_SUFFIX}@example.org",
                        created_at=BASE_TIME + timedelta(seconds=106),
                        anonymized_at=now,
                    )
                    session.add(anonymized)

                    institutions = []
                    for i in range(10):
                        institution = Institution(
                            id=uuid.uuid4(),
                            name=f"Choice Institution {i:02d}",
                            country="SI" if i % 2 == 0 else "AT",
                            created_at=BASE_TIME + timedelta(minutes=i),
                        )
                        session.add(institution)
                        institutions.append(institution)

                    cohorts = []
                    for i in range(5):
                        cohort = Cohort(
                            id=uuid.uuid4(),
                            name=f"choice-cohort-{i}-{SEED_SUFFIX}",
                            description="record choice seed cohort",
                            starts_at=BASE_TIME,
                            ends_at=BASE_TIME + timedelta(days=30),
                            created_at=BASE_TIME + timedelta(hours=i),
                        )
                        session.add(cohort)
                        cohorts.append(cohort)

                    key = GatewayKey(
                        id=uuid.uuid4(),
                        public_key_id=f"choice-{SEED_SUFFIX}",
                        key_prefix="sk-slaif-",
                        key_hint=f"choice-{SEED_SUFFIX}",
                        token_hash=f"token_hash_choice_{SEED_SUFFIX}_{uuid.uuid4().hex}",
                        owner_id=owners[0].id,
                        status="active",
                        valid_from=BASE_TIME,
                        valid_until=BASE_TIME + timedelta(days=30),
                        created_at=BASE_TIME + timedelta(days=1),
                    )
                    session.add(key)

                    # 105 providers, staggered like owners (005 ends the
                    # latest-100 batch; 000-004 are older).
                    providers = []
                    for i in range(105):
                        provider = ProviderConfig(
                            id=uuid.uuid4(),
                            provider=f"root-provider-{i:03d}",
                            display_name=f"Root Provider {i:03d}",
                            kind="openai_compatible",
                            base_url=f"https://provider-{i:03d}.example.org/v1",
                            api_key_env_var=f"CHOICE_PROVIDER_{i:03d}_API_KEY",
                            enabled=True,
                            created_at=BASE_TIME + timedelta(seconds=i),
                        )
                        session.add(provider)
                        providers.append(provider)

                    # Routes: requested + upstream tokens (both must appear
                    # as first-class model values).
                    for j, (req, up) in enumerate(
                        (("route-req-a", "route-up-a"), ("route-req-b", "route-up-b"))
                    ):
                        route = ModelRoute(
                            id=uuid.uuid4(),
                            requested_model=req,
                            match_type="exact",
                            endpoint="/v1/chat/completions",
                            provider="root-provider-001",
                            upstream_model=up,
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            created_at=BASE_TIME + timedelta(days=2, minutes=j),
                        )
                        session.add(route)
                    # A second provider owns its own model tokens, so the
                    # provider scope is exercised against real exclusions
                    # (a prefix-only assertion cannot catch a removed
                    # provider filter when every row shares one provider).
                    session.add(
                        ModelRoute(
                            id=uuid.uuid4(),
                            requested_model="route-req-z",
                            match_type="exact",
                            endpoint="/v1/chat/completions",
                            provider="root-provider-002",
                            upstream_model="route-up-z",
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            created_at=BASE_TIME + timedelta(days=2, minutes=2),
                        )
                    )

                    pricing = PricingRule(
                        id=uuid.uuid4(),
                        provider="root-provider-001",
                        upstream_model="pricing-up-a",
                        endpoint="/v1/chat/completions",
                        currency="CHF",
                        input_price_per_1m=Decimal("1"),
                        output_price_per_1m=Decimal("2"),
                        valid_from=BASE_TIME,
                        enabled=True,
                        created_at=BASE_TIME + timedelta(days=2, minutes=5),
                    )
                    session.add(pricing)

                    # Usage history: 105 distinct requested models
                    # (usage-model-000..104, staggered; 000-004 older than
                    # the latest-100 distinct batch) + one shared request id.
                    usage_rows = []
                    for i in range(105):
                        row = UsageLedger(
                            id=uuid.uuid4(),
                            request_id=f"usage-req-{i:03d}-{SEED_SUFFIX}",
                            gateway_key_id=key.id,
                            endpoint="/v1/chat/completions",
                            provider="root-provider-001",
                            requested_model=f"usage-model-{i:03d}",
                            success=True,
                            accounting_status="finalized",
                            http_status=200,
                            started_at=BASE_TIME + timedelta(hours=3, seconds=i),
                            finished_at=BASE_TIME + timedelta(hours=3, seconds=i) + timedelta(milliseconds=25),
                            created_at=BASE_TIME + timedelta(hours=3, seconds=i),
                        )
                        session.add(row)
                        usage_rows.append(row)
                    shared = UsageLedger(
                        id=uuid.uuid4(),
                        request_id=f"shared-req-{SEED_SUFFIX}",
                        gateway_key_id=key.id,
                        endpoint="/v1/responses",
                        provider="root-provider-001",
                        requested_model="usage-model-104",
                        success=True,
                        accounting_status="finalized",
                        http_status=200,
                        started_at=BASE_TIME + timedelta(hours=3, minutes=10),
                        finished_at=BASE_TIME + timedelta(hours=3, minutes=10) + timedelta(milliseconds=25),
                        created_at=BASE_TIME + timedelta(hours=3, minutes=10),
                    )
                    session.add(shared)
                    usage_rows.append(shared)

                    # FX + pricing currency: EUR/USD/GBP, CHF; two sources.
                    for base, quote, source, extra in (
                        ("EUR", "USD", "ecb", 0),
                        ("USD", "EUR", "manual", 1),
                        ("GBP", "USD", "ecb", 2),
                    ):
                        rate = FxRate(
                            id=uuid.uuid4(),
                            base_currency=base,
                            quote_currency=quote,
                            rate=Decimal("1.100000000"),
                            valid_from=BASE_TIME,
                            source=source,
                            created_at=BASE_TIME + timedelta(days=3, hours=extra),
                        )
                        session.add(rate)

                    # Audit history: one hot entity (150 recent events) and
                    # 15 other entities (one event each, older). Grouping
                    # before the LIMIT must keep all 15 others visible.
                    hot_entity = uuid.uuid4()
                    for i in range(150):
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                action="admin_key_create",
                                entity_type="owner",
                                entity_id=hot_entity,
                                request_id=f"audit-req-{i:03d}-{SEED_SUFFIX}",
                                created_at=BASE_TIME + timedelta(days=4, minutes=i),
                            )
                        )
                    other_entities = []
                    for j in range(15):
                        entity_id = uuid.uuid4()
                        other_entities.append(entity_id)
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                action="admin_owner_create",
                                entity_type="owner",
                                entity_id=entity_id,
                                created_at=BASE_TIME + timedelta(days=4, hours=2, minutes=j),
                            )
                        )
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            action="admin_key_revoke",
                            entity_type="gateway_key",
                            entity_id=key.id,
                            created_at=BASE_TIME + timedelta(days=4, hours=3),
                        )
                    )
                    # Shared request id between usage and audit.
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            action="admin_export",
                            entity_type="usage_ledger",
                            entity_id=shared.id,
                            request_id=f"shared-req-{SEED_SUFFIX}",
                            created_at=BASE_TIME + timedelta(days=4, hours=4),
                        )
                    )

                    secrets = []
                    for i in range(2):
                        secret = OneTimeSecret(
                            id=uuid.uuid4(),
                            purpose="gateway_key_email",
                            encrypted_payload=f"cipher-{SEED_SUFFIX}-{i}",
                            nonce=f"nonce-{SEED_SUFFIX}-{i}",
                            encryption_key_version=1,
                            expires_at=now + timedelta(days=1),
                            status="pending",
                            created_at=now + timedelta(seconds=i),
                        )
                        session.add(secret)
                        secrets.append(secret)

                    return {
                        "admin_id": admin.id,
                        "owners": [o.id for o in owners],
                        "owner_names": {str(o.id): f"Choice Owner {i:03d}" for i, o in enumerate(owners)},
                        "anonymized_owner_id": anonymized.id,
                        "institutions": [i.id for i in institutions],
                        "cohorts": [c.id for c in cohorts],
                        "key_id": key.id,
                        "key_public_id": key.public_key_id,
                        "providers": [p.provider for p in providers],
                        "usage_request_ids": [r.request_id for r in usage_rows[:-1]],
                        "shared_request_id": shared.request_id,
                        "hot_audit_entity": hot_entity,
                        "other_audit_entities": other_entities,
                        "secret_ids": [s.id for s in secrets],
                    }
        finally:
            await engine.dispose()

    return asyncio.run(_run())


@pytest.fixture(scope="module")
def seeded_env(owned_pg_url: str) -> dict[str, object]:
    return _seed_all(owned_pg_url)


# ---------------------------------------------------------------------------
# Service-level helpers
# ---------------------------------------------------------------------------


def _load(database_url: str, kind: str, **kwargs: object) -> list[svc.RecordChoice]:
    async def _run() -> list[svc.RecordChoice]:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    return await svc.load_choices(session, kind, **kwargs)  # type: ignore[arg-type]
        finally:
            await engine.dispose()

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Latest-100 ordering, older search, selected hydration
# ---------------------------------------------------------------------------


def test_owner_latest_100_exact_order_with_ties(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    choices = _load(owned_pg_url, "owner")
    assert len(choices) == svc.CHOICE_LIMIT
    # 103 and 104 share created_at: the tie is broken by id ASC (uuid
    # binary order == canonical string order).
    uid_103 = str(seeded_env["owners"][103])  # type: ignore[index]
    uid_104 = str(seeded_env["owners"][104])  # type: ignore[index]
    tie_order = sorted([uid_103, uid_104])
    tie_labels = {uid_103: "Choice Owner 103", uid_104: "Choice Owner 104"}
    expected = [tie_labels[tie_order[0]], tie_labels[tie_order[1]]] + [
        f"Choice Owner {i:03d}" for i in range(102, 4, -1)
    ]  # 100 rows: the batch ends at owner 005
    assert [c.label for c in choices] == expected
    # Anonymized owner must not appear despite the recent created_at.
    assert str(seeded_env["anonymized_owner_id"]) not in [c.id for c in choices]


def test_owner_older_search_reaches_beyond_batch(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    choices = _load(owned_pg_url, "owner", q="Owner 000")
    ids = [c.id for c in choices]
    assert str(seeded_env["owners"][0]) in ids  # type: ignore[index]
    # Search results stay bounded.
    assert len(choices) <= svc.CHOICE_LIMIT


def test_selected_outside_100_hydrated_across_kinds(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    owners: list[str] = [str(o) for o in seeded_env["owners"]]  # type: ignore[union-attr]
    # owner: canonical, uppercase and unhyphenated spellings of owner 000
    raw = owners[0]
    for spelling in (raw, str(raw).upper(), str(uuid.UUID(raw)).replace("-", "")):
        choices = _load(owned_pg_url, "owner", selected=[spelling])
        hit = next((c for c in choices if c.id == str(uuid.UUID(raw))), None)
        assert hit is not None, f"owner {spelling} not hydrated"
        assert hit.label == "Choice Owner 000"
        assert len(choices) <= svc.CHOICE_LIMIT
    # institution UUID selected (small batch: still present)
    institution_raw = str(seeded_env["institutions"][0])
    choices = _load(owned_pg_url, "institution", selected=[institution_raw])
    assert institution_raw in [c.id for c in choices]
    # cohort UUID
    cohort_raw = str(seeded_env["cohorts"][0])
    choices = _load(owned_pg_url, "cohort", selected=[cohort_raw])
    assert cohort_raw in [c.id for c in choices]
    # gateway key UUID
    key_raw = str(seeded_env["key_id"])
    choices = _load(owned_pg_url, "key", selected=[key_raw])
    assert key_raw in [c.id for c in choices]
    # provider slug outside the batch
    choices = _load(owned_pg_url, "provider", selected=["root-provider-000"])
    hit = next((c for c in choices if c.id == "root-provider-000"), None)
    assert hit is not None and hit.label == "root-provider-000"
    assert len(choices) <= svc.CHOICE_LIMIT
    # owner email outside the batch
    choices = _load(
        owned_pg_url,
        "owner_email",
        selected=[f"choice-owner-000-{SEED_SUFFIX}@example.org"],
    )
    assert f"choice-owner-000-{SEED_SUFFIX}@example.org" in [c.id for c in choices]
    # public key id
    choices = _load(owned_pg_url, "key_public_id", selected=[seeded_env["key_public_id"]])  # type: ignore[arg-type]
    assert str(seeded_env["key_public_id"]) in [c.id for c in choices]
    # plain model token outside the distinct batch
    choices = _load(owned_pg_url, "model", selected=["usage-model-000"])
    assert "usage-model-000" in [c.id for c in choices]
    assert len(choices) <= svc.CHOICE_LIMIT


def test_institution_and_cohort_name_kinds_latest_order_search_and_selection(
    owned_pg_url: str, seeded_env: dict[str, object]
) -> None:
    """Name-based list filters submit the NAME (never a UUID): latest
    distinct names, older-name server search, per-record metadata in the
    sub line, and selected-name hydration."""
    institutions = seeded_env["institutions"]
    # Latest-first: institution 09 (newest) leads, 00 last; id == name.
    choices = _load(owned_pg_url, "institution_name")
    assert [c.id for c in choices] == [
        f"Choice Institution {i:02d}" for i in range(9, -1, -1)
    ]
    newest = next(c for c in choices if c.id == "Choice Institution 09")
    assert newest.label == "Choice Institution 09"
    assert str(institutions[9]) in newest.sub

    # Server search reaches an OLDER name outside the top of the batch.
    older = _load(owned_pg_url, "institution_name", q="Choice Institution 03")
    assert [c.id for c in older] == ["Choice Institution 03"]

    # Institution names are unique in the DB (uq_institutions_name_lower),
    # so each name resolves to exactly ONE record: the GROUP-BY/meta
    # pairing must carry that record's own metadata (country · id) into
    # the sub line.
    one = _load(owned_pg_url, "institution_name", q="Choice Institution 01")
    assert [c.id for c in one] == ["Choice Institution 01"]
    assert one[0].sub.startswith("AT · "), f"sub must carry the record country: {one[0].sub}"
    assert str(institutions[1]) in one[0].sub

    # Selected names: the in-batch one is kept with its label, and a
    # free-typed/older name outside the batch remains visible (plain).
    selected = _load(
        owned_pg_url,
        "institution_name",
        selected=["Choice Institution 02", f"older-free-typed-{SEED_SUFFIX}"],
    )
    selected_ids = [c.id for c in selected]
    assert "Choice Institution 02" in selected_ids
    assert f"older-free-typed-{SEED_SUFFIX}" in selected_ids

    # Cohort names: id is the name; sub carries the window + record id.
    cohorts = seeded_env["cohorts"]
    cohort_choices = _load(owned_pg_url, "cohort_name")
    assert [c.id for c in cohort_choices] == [
        f"choice-cohort-{i}-{SEED_SUFFIX}" for i in range(4, -1, -1)
    ]
    first = cohort_choices[0]
    assert first.id == f"choice-cohort-4-{SEED_SUFFIX}"
    assert str(cohorts[4]) in first.sub
    assert BASE_TIME.isoformat() in first.sub


def test_multi_selection_keeps_in_batch_and_outside(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    # Root scenario: 105 providers, latest-100 batch ends at 005; selecting
    # 005 (in batch, at the tail) plus 000 (outside) keeps BOTH.
    choices = _load(owned_pg_url, "provider", selected=["root-provider-005", "root-provider-000"])
    ids = [c.id for c in choices]
    assert "root-provider-005" in ids, "in-batch selected provider was evicted"
    assert "root-provider-000" in ids, "outside-batch selected provider missing"
    assert len(choices) <= svc.CHOICE_LIMIT
    # Same for the plain model kind (usage-model-104 is in the batch tail
    # region; usage-model-000 is outside).
    choices = _load(owned_pg_url, "model", selected=["usage-model-005", "usage-model-000"])
    ids = [c.id for c in choices]
    assert "usage-model-005" in ids and "usage-model-000" in ids
    assert len(choices) <= svc.CHOICE_LIMIT


def test_anonymized_owner_excluded_from_selected_hydration(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    anonymized = str(seeded_env["anonymized_owner_id"])
    # q with no match isolates eligibility: the selected anonymized owner
    # must not be hydrated even with an empty batch.
    choices = _load(owned_pg_url, "owner", q="zz-no-such-owner-zz", selected=[anonymized])
    assert anonymized not in [c.id for c in choices]
    # And a normal (eligible) selected owner still hydrates under the same q.
    eligible = str(seeded_env["owners"][0])  # type: ignore[index]
    choices = _load(owned_pg_url, "owner", q="zz-no-such-owner-zz", selected=[eligible])
    assert eligible in [c.id for c in choices]


# ---------------------------------------------------------------------------
# Id search and distinct-before-LIMIT audit targets
# ---------------------------------------------------------------------------


def test_id_search_matches_uuid_and_public_id(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    # owner by UUID substring and by full UUID
    owner_raw = str(seeded_env["owners"][7])  # type: ignore[index]
    assert owner_raw in [c.id for c in _load(owned_pg_url, "owner", q=owner_raw)]
    assert owner_raw in [c.id for c in _load(owned_pg_url, "owner", q=owner_raw[:8])]
    # key by internal UUID
    key_raw = str(seeded_env["key_id"])
    assert key_raw in [c.id for c in _load(owned_pg_url, "key", q=key_raw)]
    # audit target by entity UUID (UUID column cast)
    hot = str(seeded_env["hot_audit_entity"])
    assert hot in [c.id for c in _load(owned_pg_url, "audit_target", q=hot)]
    # one-time secret by UUID
    secret_raw = str(seeded_env["secret_ids"][0])
    assert secret_raw in [c.id for c in _load(owned_pg_url, "one_time_secret", q=secret_raw)]


def test_audit_target_grouped_before_limit_and_scoped(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    other_entities = [str(e) for e in seeded_env["other_audit_entities"]]  # type: ignore[union-attr]
    hot = str(seeded_env["hot_audit_entity"])
    choices = _load(owned_pg_url, "audit_target")
    ids = [c.id for c in choices]
    # The hot entity's 150 recent events must not crowd out the others.
    assert hot in ids
    for entity in other_entities:
        assert entity in ids, f"entity {entity} crowded out of initial batch"
    assert len(choices) <= svc.CHOICE_LIMIT
    # Scope to one entity type: gateway_key targets only.
    choices = _load(owned_pg_url, "audit_target", target_type="gateway_key")
    assert all("gateway_key" in c.label for c in choices)
    assert str(seeded_env["key_id"]) in [c.id for c in choices]
    assert hot not in [c.id for c in choices]


def test_request_id_includes_usage_and_audit_request_ids(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    choices = _load(owned_pg_url, "request_id")
    ids = [c.id for c in choices]
    # Latest audit request ids (150 hot-entity events) appear...
    assert any(i.startswith("audit-req-") for i in ids)
    # ...and the shared request id is de-duplicated to one option.
    shared = str(seeded_env["shared_request_id"])
    assert ids.count(shared) == 1
    assert len(choices) <= svc.CHOICE_LIMIT
    # Bounded search.
    choices = _load(owned_pg_url, "request_id", q="audit-req-000")
    assert any(i == f"audit-req-000-{SEED_SUFFIX}" for i in [c.id for c in choices])


# ---------------------------------------------------------------------------
# Model / currency / vocabulary kinds
# ---------------------------------------------------------------------------


def test_model_kind_includes_upstream_pricing_and_usage(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    choices = _load(owned_pg_url, "model")
    ids = [c.id for c in choices]
    # upstream tokens are first-class (not dropped by coalesce)
    assert "route-up-a" in ids
    assert "route-req-a" in ids
    # pricing token
    assert "pricing-up-a" in ids
    # usage history tokens
    assert any(i.startswith("usage-model-") for i in ids)
    # The OTHER provider's tokens join the unscoped union...
    assert "route-req-z" in ids and "route-up-z" in ids
    # ...and provider scope narrows to that provider's rows EXACTLY:
    # provider-001's route/pricing tokens plus its newest 95 usage models
    # (the 5 distinct route/pricing tokens push the 5 oldest usage models
    # out of the merged 100-cap), with provider-002's models absent.
    expected = {
        "route-req-a",
        "route-up-a",
        "route-req-b",
        "route-up-b",
        "pricing-up-a",
    } | {f"usage-model-{i:03d}" for i in range(10, 105)}
    scoped = [c.id for c in _load(owned_pg_url, "model", provider="root-provider-001")]
    assert len(scoped) == 100
    assert set(scoped) == expected
    assert "route-req-z" not in scoped and "route-up-z" not in scoped


def test_policy_model_kind_latest_100_older_search_and_provider_scope(
    owned_pg_url: str, seeded_env: dict[str, object]
) -> None:
    """The key-policy model search offers only REQUESTED tokens of ENABLED
    routes on ENABLED providers over IMPLEMENTED endpoints (the base
    catalog eligibility, applied even when the UI filters are "All"):
    latest-100 per provider, older tokens via server search, provider
    scoping, disabled routes/providers and unimplemented endpoints
    excluded, upstream tokens never returned."""

    async def _add_policy_routes() -> None:
        engine = create_async_engine(owned_pg_url, future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    # A DISABLED provider whose newest route must never be
                    # offered, even in the unscoped ("All") batch.
                    session.add(
                        ProviderConfig(
                            id=uuid.uuid4(),
                            provider="root-provider-policy-disabled",
                            display_name="Root Provider Policy Disabled",
                            kind="openai_compatible",
                            base_url="https://provider-policy-disabled.example.org/v1",
                            api_key_env_var="CHOICE_PROVIDER_POLICY_DISABLED_API_KEY",
                            enabled=False,
                            created_at=datetime.now(UTC),
                        )
                    )
                    for i in range(105):
                        session.add(
                            ModelRoute(
                                id=uuid.uuid4(),
                                requested_model=f"policy-model-{i:03d}",
                                match_type="exact",
                                endpoint="/v1/chat/completions",
                                provider="root-provider-001",
                                upstream_model=f"policy-up-{i:03d}",
                                enabled=True,
                                visible_in_models=True,
                                supports_streaming=True,
                                created_at=BASE_TIME + timedelta(days=3, minutes=i),
                            )
                        )
                    # Newer than the whole batch, on the disabled provider:
                    # recency must not resurrect an ineligible route.
                    session.add(
                        ModelRoute(
                            id=uuid.uuid4(),
                            requested_model="policy-model-deadprov",
                            match_type="exact",
                            endpoint="/v1/chat/completions",
                            provider="root-provider-policy-disabled",
                            upstream_model="policy-up-deadprov",
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            created_at=datetime.now(UTC),
                        )
                    )
                    # Same enabled provider, but an UNIMPLEMENTED endpoint:
                    # never a key-policy model choice either.
                    session.add(
                        ModelRoute(
                            id=uuid.uuid4(),
                            requested_model="policy-model-badendpoint",
                            match_type="exact",
                            endpoint="/v1/files",
                            provider="root-provider-001",
                            upstream_model="policy-up-badendpoint",
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            created_at=BASE_TIME + timedelta(days=2),
                        )
                    )
                    # An implemented path that only exists through a
                    # method-prefixed canonical token
                    # ("GET /v1/responses/{response_id}"); proves the
                    # lookup normalizes canonical endpoint scopes to the
                    # plain path form the route column stores.
                    session.add(
                        ModelRoute(
                            id=uuid.uuid4(),
                            requested_model="policy-model-resp",
                            match_type="exact",
                            endpoint="/v1/responses/{response_id}",
                            provider="root-provider-001",
                            upstream_model="policy-up-resp",
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            created_at=BASE_TIME + timedelta(days=2, minutes=1),
                        )
                    )
                    session.add(
                        ModelRoute(
                            id=uuid.uuid4(),
                            requested_model="policy-model-disabled",
                            match_type="exact",
                            endpoint="/v1/chat/completions",
                            provider="root-provider-001",
                            upstream_model="policy-up-disabled",
                            enabled=False,
                            visible_in_models=False,
                            supports_streaming=True,
                            created_at=datetime.now(UTC),
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_add_policy_routes())

    batch = [c.id for c in _load(owned_pg_url, "policy_model", provider="root-provider-001")]
    assert len(batch) == 100
    # Latest first: the 100 newest enabled tokens; the 5 oldest policy
    # tokens and the two seeded provider-001 routes sit outside the batch.
    assert batch[0] == "policy-model-104"
    assert "policy-model-003" not in batch
    assert "route-req-a" not in batch
    assert "policy-model-disabled" not in batch
    # Upstream tokens are never policy-model options.
    assert not any(i.startswith("policy-up-") for i in batch)

    # Base eligibility with the UI filters at "All" (no scopes at all):
    # the disabled provider's newest route and the unimplemented-endpoint
    # route must not ride the recency order into the unscoped batch, and
    # a direct search must not surface them either.
    unscoped = [c.id for c in _load(owned_pg_url, "policy_model")]
    assert "policy-model-104" in unscoped
    assert "policy-model-deadprov" not in unscoped
    assert "policy-model-badendpoint" not in unscoped
    assert [c.id for c in _load(owned_pg_url, "policy_model", q="policy-model-deadprov")] == []
    assert [c.id for c in _load(owned_pg_url, "policy_model", q="policy-model-badendpoint")] == []
    # A scope naming only the disabled provider yields no choices.
    assert [c.id for c in _load(owned_pg_url, "policy_model", provider="root-provider-policy-disabled")] == []
    # Endpoint scopes: plain implemented path still matches; a
    # method-prefixed canonical token is reduced to its path form; an
    # unimplemented path matches nothing.
    resp_scoped = [
        c.id
        for c in _load(
            owned_pg_url,
            "policy_model",
            provider="root-provider-001",
            endpoints=["GET /v1/responses/{response_id}"],
        )
    ]
    assert resp_scoped == ["policy-model-resp"]
    # An explicit plain implemented-path scope behaves like the provider
    # batch and keeps the other-endpoint token out.
    chat_scoped = [
        c.id
        for c in _load(
            owned_pg_url,
            "policy_model",
            provider="root-provider-001",
            endpoints=["/v1/chat/completions"],
        )
    ]
    assert chat_scoped == batch
    assert "policy-model-resp" not in chat_scoped
    assert (
        [c.id for c in _load(owned_pg_url, "policy_model", endpoints=["/v1/files"])] == []
    )

    # Older search reaches a token outside the batch.
    older = [
        c.id
        for c in _load(
            owned_pg_url, "policy_model", provider="root-provider-001", q="policy-model-003"
        )
    ]
    assert older == ["policy-model-003"]

    # Disabled routes never surface, even in search.
    disabled = _load(owned_pg_url, "policy_model", q="policy-model-disabled")
    assert [c.id for c in disabled] == []

    # Provider scope: provider-002 has only its seeded token.
    scoped = [c.id for c in _load(owned_pg_url, "policy_model", provider="root-provider-002")]
    assert scoped == ["route-req-z"]


def test_currency_fx_source_db_derived_latest_first(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    codes = [c.id for c in _load(owned_pg_url, "currency")]
    # Latest observed created_at first: GBP (fx +3d+2h) > USD (+3d+1h)
    # > EUR (+3d) > CHF (pricing +2d); no invented codes.
    assert codes == ["GBP", "USD", "EUR", "CHF"]
    sources = [c.id for c in _load(owned_pg_url, "fx_source")]
    # ecb observed at BASE+3h+2 > manual at BASE+3h+1
    assert sources == ["ecb", "manual"]
    actions = [c.id for c in _load(owned_pg_url, "audit_action")]
    assert set(actions) == {"admin_key_create", "admin_owner_create", "admin_key_revoke", "admin_export"}
    types = [c.id for c in _load(owned_pg_url, "audit_target_type")]
    assert set(types) == {"owner", "gateway_key", "usage_ledger"}


def test_endpoint_and_email_status_canonical_vocabularies(owned_pg_url: str) -> None:
    endpoints = [c.id for c in _load(owned_pg_url, "endpoint")]
    assert "/v1/chat/completions" in endpoints
    assert "/v1/responses" in endpoints
    assert not any(" " in e for e in endpoints)
    statuses = [c.id for c in _load(owned_pg_url, "email_delivery_status")]
    assert statuses == list(svc.KNOWN_EMAIL_DELIVERY_STATUSES)
    assert "sending" in statuses and "ambiguous" in statuses
    assert "consumed" not in statuses and "expired" not in statuses


def test_bounded_query_truncation_and_selected_cap(owned_pg_url: str, seeded_env: dict[str, object]) -> None:
    long_query = "Owner " + "x" * 500
    choices = _load(owned_pg_url, "owner", q=long_query)
    assert len(choices) <= svc.CHOICE_LIMIT
    # selected list is bounded server-side (API passes max 8); the service
    # de-duplicates and caps the result regardless.
    owners: list[str] = seeded_env["owners"]  # type: ignore[assignment]
    many_selected = [owners[i] for i in range(0, 104, 10)] + ["root-provider-000"]  # type: ignore[index]
    choices = _load(owned_pg_url, "owner", selected=many_selected)
    assert len(choices) <= svc.CHOICE_LIMIT


# ---------------------------------------------------------------------------
# HTTP: auth law, unknown kind, and read-only lookup guarantee
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
        deadline = time.monotonic() + 15
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
def admin_client(owned_pg_url: str, seeded_env: dict[str, object]) -> Iterator[httpx.Client]:
    app = create_app(_settings_for(owned_pg_url))
    with _run_server(app, _free_port()) as base_url:
        client = httpx.Client(base_url=base_url, follow_redirects=False, timeout=30)
        # Login: GET the form (login CSRF cookie + token), then POST.
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


def test_lookup_unauthenticated_redirects(admin_client: httpx.Client) -> None:
    anonymous = httpx.Client(
        base_url=str(admin_client.base_url), follow_redirects=False, timeout=30
    )
    try:
        response = anonymous.get("/admin/record-choices", params={"kind": "owner"})
        assert response.status_code == 303
        assert "/admin/login" in response.headers.get("location", "")
    finally:
        anonymous.close()


def test_lookup_unknown_kind_returns_400(admin_client: httpx.Client) -> None:
    response = admin_client.get(
        "/admin/record-choices", params={"kind": "gateway_keys", "q": "x"}
    )
    assert response.status_code == 400
    assert "record_choices_bad_request" in response.text


def test_lookup_is_readonly_and_original_csrf_post_succeeds(
    owned_pg_url: str,
    seeded_env: dict[str, object],
    admin_client: httpx.Client,
) -> None:
    # 1) Render the owner-create form (form CSRF token A).
    form_page = admin_client.get("/admin/owners/new")
    assert form_page.status_code == 200
    form_match = re.search(r'<input type="hidden" name="csrf_token" value="([^"]+)"', form_page.text)
    assert form_match, "owner form CSRF token not rendered"
    form_csrf = form_match.group(1)

    # 2) Snapshot session rows and audit counts.
    async def _snapshot() -> dict[str, object]:
        engine = create_async_engine(owned_pg_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(
                                AdminSession.csrf_token_hash,
                                AdminSession.last_seen_at,
                                AdminSession.revoked_at,
                                AdminSession.expires_at,
                            )
                        )
                    )
                    .all()
                )
                audit_count = (
                    await session.execute(select(func.count(AuditLog.id)))
                ).scalar_one()
                owner_count = (await session.execute(select(func.count(Owner.id)))).scalar_one()
                return {
                    "sessions": [tuple(r) for r in rows],
                    "audit_count": audit_count,
                    "owner_count": owner_count,
                }
        finally:
            await engine.dispose()

    before = asyncio.run(_snapshot())

    # 3) Two dropdown lookups (search + selected hydration).
    for _ in range(2):
        response = admin_client.get(
            "/admin/record-choices",
            params={
                "kind": "owner",
                "q": "Owner 100",
                "selected": str(seeded_env["owners"][0]),  # type: ignore[index]
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "owner"
        assert len(payload["choices"]) <= svc.CHOICE_LIMIT
        assert "no-store" in response.headers.get("cache-control", "").lower()

    # 4) Lookups must not have mutated sessions, audit, or owners.
    after = asyncio.run(_snapshot())
    assert after["sessions"] == before["sessions"], "lookup mutated session rows"
    assert after["audit_count"] == before["audit_count"], "lookup wrote audit rows"
    assert after["owner_count"] == before["owner_count"], "lookup wrote owner rows"

    # 5) The ORIGINAL form CSRF still works after the lookups.
    new_email = f"choice-post-{uuid.uuid4().hex[:10]}@example.org"
    institution_raw = str(seeded_env["institutions"][0])  # type: ignore[index]
    post = admin_client.post(
        "/admin/owners/new",
        data={
            "csrf_token": form_csrf,
            "name": "Choice",
            "surname": "Posted",
            "email": new_email,
            "institution_id": institution_raw,
            "is_active": "true",
            "reason": "record choices integration qualification",
        },
    )
    assert post.status_code in (302, 303), post.text[:500]
    assert post.headers.get("location", "").startswith("/admin/owners/")

    # 6) Session rows: the login/GET touches may have updated last_seen on
    # the page GET, but NO csrf hash rotation occurred from the lookups.
    final = asyncio.run(_snapshot())
    assert final["sessions"][0][0] == before["sessions"][0][0], (
        "CSRF token hash changed by lookups"
    )

