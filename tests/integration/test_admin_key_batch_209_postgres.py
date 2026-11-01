"""209-a GUI reviewed key batch: owned PostgreSQL integration tests.

Real-app, real-PostgreSQL qualification for the G05 batch workflow
against the qualified owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL fixture (supplied as TEST_DATABASE_URL by the runner, exactly
like the 207/208 modules): exact cohort-vs-keys scope on a seeded 108-key
cohort (105 active / 2 suspended / 1 revoked) plus one active
OUT-OF-SCOPE control key (no cohort, never selected), the read-only
preview (zero writes, zero audits, no first-page truncation), the atomic
apply (persisted per-key fidelity, one ``update_key_configuration`` audit
per changed key with actor + reason, full material/identity/usage/
reservation/other-metadata preservation while only the requested quotas
- and the legitimate ``updated_at`` - move), the SAME-original-reviewed-
plan repeat (the original signed token re-applied), the stale refusals
(direct-DB drift; direct status change) with zero writes and zero new
audits, and the late per-key write-failure rollback proof (the injected
failure after earlier provisional updates rolls back ALL key state and
ALL provisional audits of the whole operation).

The seed is quota-only (no provider/route/model configuration is
touched by the reviewed change), so this module inserts NO provider
configs or model routes: it coexists with every other integration module
on one session database without shared unique slugs.
Owners/institutions/cohorts/owners use run-unique names, and every
oracle is scoped to THIS seed's owner so foreign rows on the shared
session database can never pollute a snapshot.

Fixture data only: the keys are direct ORM inserts (synthetic material,
deterministic usage/reservation values) - they are not the product's
key-creation flow and are not reused elsewhere.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="batch_review_intent" value="([^"]+)"')
ERROR_MESSAGE_RE = re.compile(
    r'class="error-page".*?<p>([^<]+)</p>', re.DOTALL
)

ADMIN_PASSWORD = "correct horse battery staple"
APPLY_REASON = "209 batch quota normalization for the seeded cohort"

N_ACTIVE = 105
N_SUSPENDED = 2
N_REVOKED = 1
N_COHORT_KEYS = N_ACTIVE + N_SUSPENDED + N_REVOKED
N_CONTROL_KEYS = 1  # active, no cohort, never selected
N_SEEDED_KEYS = N_COHORT_KEYS + N_CONTROL_KEYS

BASELINE_REQUEST_LIMIT = 1000
BASELINE_TOKEN_LIMIT = 5_000_000
TARGET_TOKEN_LIMIT = 2_000_000
TARGET_REQUEST_SET = 555
LATE_FAILURE_REQUEST_SET = 777

# Snapshot tuple indices (see _snapshot):
IDX_STATUS = 0
IDX_TOKEN_LIMIT = 2
IDX_REQUEST_LIMIT = 3
IDX_UPDATED_AT = 30


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


def asyncio_run(coro):
    return asyncio.run(coro)


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def _key_kwargs(index: int, status: str, suffix: str, now: datetime,
                owner_id: uuid.UUID, cohort_id: uuid.UUID | None,
                admin_id: uuid.UUID) -> dict[str, Any]:
    return dict(
        public_key_id=f"209pg-{suffix}-{index:03d}",
        token_hash=f"209pg-hash-{suffix}-{index:03d}",
        owner_id=owner_id,
        cohort_id=cohort_id,
        status=status,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        request_limit_total=BASELINE_REQUEST_LIMIT,
        token_limit_total=BASELINE_TOKEN_LIMIT,
        cost_used_eur=Decimal(f"0.{100 + index}"),
        tokens_used_total=1000 + index * 7,
        requests_used_total=50 + index * 3,
        cost_reserved_eur=Decimal(f"0.{index + 1:09d}"),
        tokens_reserved_total=17 + index,
        requests_reserved_total=5 + index,
        allow_all_models=True,
        allow_all_endpoints=True,
        created_by_admin_user_id=admin_id,
        revoked_at=now if status == "revoked" else None,
    )


async def _seed(database_url: str) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui209-{suffix}@example.org",
                    display_name="209 Batch GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"209 Institute {suffix}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"209 Batch Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Batch",
                    surname="Seed",
                    email=f"owner-209-{suffix}@example.org",
                    institution_id=institution.id,
                )
                key_ids: list[uuid.UUID] = []
                for index in range(N_COHORT_KEYS):
                    if index < N_ACTIVE:
                        status = "active"
                    elif index < N_ACTIVE + N_SUSPENDED:
                        status = "suspended"
                    else:
                        status = "revoked"
                    key = GatewayKey(
                        **_key_kwargs(
                            index, status, suffix, now, owner.id, cohort.id, admin.id
                        )
                    )
                    session.add(key)
                    await session.flush()
                    key_ids.append(key.id)
                # Active OUT-OF-SCOPE control: same owner, NO cohort, and
                # never part of an explicit selection - a scope bug that
                # applied to the whole cohort/owner would move it.
                control = GatewayKey(
                    **_key_kwargs(
                        N_COHORT_KEYS, "active", suffix, now, owner.id, None, admin.id
                    )
                )
                session.add(control)
                await session.flush()
                return {
                    "admin_email": admin.email,
                    "admin_id": str(admin.id),
                    "cohort_id": str(cohort.id),
                    "owner_id": str(owner.id),
                    "key_ids": [str(k) for k in key_ids],
                    "control_key_id": str(control.id),
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, Any]] = {}


def _seed_sync(database_url: str) -> dict[str, Any]:
    """One shared seed per database (single TestClient login keeps the
    module deterministic; this module owns no DB-unique slugs)."""
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio_run(_seed(database_url))
    return _SEED_CACHE[database_url]


# ---------------------------------------------------------------------------
# Login / form helpers (real HTTP, real CSRF)
# ---------------------------------------------------------------------------


def _csrf_from_html(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match is not None
    return match.group(1)


def _login(client: TestClient, admin_email: str) -> None:
    login_page = client.get("/admin/login")
    csrf = _csrf_from_html(login_page.text)
    response = client.post(
        "/admin/login",
        data={
            "email": admin_email,
            "password": ADMIN_PASSWORD,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _form_csrf(client: TestClient) -> str:
    page = client.get("/admin/key-batch")
    assert page.status_code == 200
    return _csrf_from_html(page.text)


def _plan_fields(
    csrf: str,
    seed: dict[str, Any],
    *,
    selection_kind: str = "cohort",
    statuses: tuple[str, ...] = ("active",),
    token_action: str = "set",
    token_value: str = str(TARGET_TOKEN_LIMIT),
    request_action: str = "clear",
    request_value: str = "",
) -> dict[str, str]:
    key_ids = seed["key_ids"]
    fields: dict[str, str] = {
        "csrf_token": csrf,
        "input_mode": "guided",
        "selection_kind": selection_kind,
        "cohort_id": seed["cohort_id"] if selection_kind == "cohort" else "",
        "key_ids": (
            "\n".join(key_ids) if selection_kind == "keys" else ""
        ),
        "cost_action": "unchanged",
        "cost_value": "",
        "token_action": token_action,
        "token_value": token_value,
        "request_action": request_action,
        "request_value": request_value,
        "rate_action_requests": "unchanged",
        "rate_value_requests": "",
        "rate_action_tokens": "unchanged",
        "rate_value_tokens": "",
        "rate_action_concurrency": "unchanged",
        "rate_value_concurrency": "",
        "rate_action_window": "unchanged",
        "rate_value_window": "",
        "providers_mode": "unchanged",
        "providers_value": "",
        "models_mode": "unchanged",
        "models_value": "",
        "endpoints_mode": "unchanged",
        "endpoints_value": "",
        "lazy_mode": "unchanged",
        "lazy_wait_seconds": "",
        "lazy_waiting": "",
        "live_burn_mode": "unchanged",
        "live_burn_cost_margin": "",
        "live_burn_token_margin": "",
        "configuration_json": "",
    }
    # Real browser behavior: unchecked status boxes submit nothing.
    for name in ("status_active", "status_suspended", "status_revoked"):
        if name.replace("status_", "") in statuses:
            fields[name] = "true"
    return fields


def _apply(
    client: TestClient, csrf: str, token: str, reason: str = APPLY_REASON
) -> Any:
    return client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": csrf,
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": reason,
        },
        follow_redirects=False,
    )


def _error_message(html: str) -> str:
    """The shared branded error page's message (scoped: the base shell
    around it must not satisfy or break message assertions)."""
    match = ERROR_MESSAGE_RE.search(html)
    assert match is not None, "no error-page message found"
    return match.group(1)


# ---------------------------------------------------------------------------
# Direct-DB oracles (fresh sessions per call; canonical value snapshots,
# never ORM object identity; scoped to THIS seed's owner so foreign rows
# on the shared session database can never pollute a comparison)
# ---------------------------------------------------------------------------


async def _session_run(factory, coro_factory):
    async with factory() as session:
        return await coro_factory(session)


def _snapshot(database_url: str, owner_id: str) -> dict[str, tuple[Any, ...]]:
    """Every key of the seeded owner -> canonical value tuple.

    Includes ``updated_at`` so any write (even one that leaves the
    compared policy fields looking identical) is detected on rows that
    must NOT be touched.
    """

    async def _run(session):
        result = await session.execute(
            select(GatewayKey)
            .where(GatewayKey.owner_id == uuid.UUID(owner_id))
            .order_by(GatewayKey.created_at.asc(), GatewayKey.id.asc())
        )
        out: dict[str, tuple[Any, ...]] = {}
        for key in result.scalars().all():
            out[str(key.id)] = (
                key.status,
                str(key.cost_limit_eur),
                key.token_limit_total,
                key.request_limit_total,
                str(key.cost_used_eur),
                key.tokens_used_total,
                key.requests_used_total,
                str(key.cost_reserved_eur),
                key.tokens_reserved_total,
                key.requests_reserved_total,
                key.rate_limit_requests_per_minute,
                key.rate_limit_tokens_per_minute,
                key.max_concurrent_requests,
                key.allow_all_models,
                tuple(key.allowed_models or ()),
                key.allow_all_endpoints,
                tuple(key.allowed_endpoints or ()),
                key.token_hash,
                key.public_key_id,
                key.key_prefix,
                key.valid_from,
                key.valid_until,
                str(key.owner_id),
                str(key.cohort_id),
                key.key_purpose,
                key.capability_policy_mode,
                key.external_tool_fence_state,
                json.dumps(key.metadata_json, sort_keys=True),
                json.dumps(key.calibration_metadata, sort_keys=True),
                key.created_at,
                key.updated_at,
            )
        return out

    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return asyncio_run(_session_run(factory, _run))
    finally:
        asyncio_run(engine.dispose())


def _batch_audits(database_url: str, admin_id: str) -> list[dict[str, Any]]:
    """``update_key_configuration`` rows written by THIS admin (scoped:
    other modules on the shared session DB write their own audits)."""

    async def _run(session):
        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.action == "update_key_configuration",
                AuditLog.admin_user_id == uuid.UUID(admin_id),
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        return [
            {
                "entity_id": str(row.entity_id),
                "admin_user_id": str(row.admin_user_id),
                "note": row.note,
                "old_values": json.dumps(row.old_values or {}, sort_keys=True),
                "new_values": json.dumps(row.new_values or {}, sort_keys=True),
            }
            for row in result.scalars().all()
        ]

    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return asyncio_run(_session_run(factory, _run))
    finally:
        asyncio_run(engine.dispose())


def _set_request_limit(database_url: str, key_id: str, value: int) -> None:

    async def _run(session):
        async with session.begin():
            key = await session.get(GatewayKey, uuid.UUID(key_id))
            assert key is not None
            key.request_limit_total = value

    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        asyncio_run(_session_run(factory, _run))
    finally:
        asyncio_run(engine.dispose())


def _set_status(database_url: str, key_id: str, status: str) -> None:

    async def _run(session):
        async with session.begin():
            key = await session.get(GatewayKey, uuid.UUID(key_id))
            assert key is not None
            key.status = status

    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        asyncio_run(_session_run(factory, _run))
    finally:
        asyncio_run(engine.dispose())


def _snapshot_changed_key(
    before: tuple[Any, ...], after: tuple[Any, ...], key_id: str
) -> None:
    """A reviewed first-apply key: ONLY the requested quotas may differ,
    plus the legitimate ``updated_at`` from the actual write. Every other
    field - status, cost, all usage/reservation counters, rate members,
    material (token_hash/public_key_id/key_prefix), identity, validity,
    purpose/mode/fence, metadata - is preserved exactly."""
    assert after[IDX_TOKEN_LIMIT] == TARGET_TOKEN_LIMIT, "token limit not persisted"
    assert after[IDX_REQUEST_LIMIT] is None, "request limit not cleared"
    for index in range(len(before)):
        if index in (IDX_TOKEN_LIMIT, IDX_REQUEST_LIMIT, IDX_UPDATED_AT):
            continue
        assert after[index] == before[index], (
            f"{key_id[:8]} field {index} changed outside the reviewed quotas"
        )


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def batch_env(migrated_postgres_url: str) -> Iterator[dict[str, Any]]:
    data = _seed_sync(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    # The TestClient context keeps the app lifespan open (DB sessionmaker
    # bound at startup) for the WHOLE module: the SAME login session and
    # secrets make a signed review token issued by an earlier test valid
    # in a later one (the same-operation repeat law).
    with TestClient(app) as client:
        _login(client, str(data["admin_email"]))
        data["client"] = client
        data["csrf"] = _form_csrf(client)
        data["database_url"] = migrated_postgres_url
        yield data


def _snap(data: dict[str, Any]) -> dict[str, tuple[Any, ...]]:
    return _snapshot(data["database_url"], data["owner_id"])


def _audits(data: dict[str, Any]) -> list[dict[str, Any]]:
    return _batch_audits(data["database_url"], data["admin_id"])


# ---------------------------------------------------------------------------
# (a) Cohort scope: read-only preview, exact DB-filtered membership
# ---------------------------------------------------------------------------


def test_cohort_plan_is_read_only_full_scope(batch_env) -> None:
    data = batch_env
    client: TestClient = data["client"]
    key_ids = data["key_ids"]
    active_ids = set(key_ids[:N_ACTIVE])
    suspended_ids = set(key_ids[N_ACTIVE : N_ACTIVE + N_SUSPENDED])
    revoked_ids = set(key_ids[N_ACTIVE + N_SUSPENDED :])

    before = _snap(data)
    audits_before = _audits(data)
    assert len(before) == N_SEEDED_KEYS
    assert len(audits_before) == 0

    response = client.post(
        "/admin/key-batch/plan",
        data=_plan_fields(
            data["csrf"], data, statuses=("active", "suspended")
        ),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "no-store" in response.headers.get("cache-control", "")

    # Exact DB-filtered membership: 105 active + 2 suspended = 107, ALL
    # changed, no first-page truncation (every UUID actually rendered).
    assert "107 selected" in text
    assert "107 changed" in text
    assert "0 unchanged" in text
    for key_id in active_ids | suspended_ids:
        assert key_id in text, f"selected {key_id[:8]} not enumerated"
    # Cohort scope: status-excluded members are NOT enumerated, and the
    # out-of-cohort control key is not in the cohort at all.
    for key_id in revoked_ids:
        assert key_id not in text, "status-excluded member enumerated"
    assert data["control_key_id"] not in text
    # Honest cohort wording (filtered in DB, not client-side truncation).
    assert "filtered in the database by the selected persisted statuses" in text
    assert "NOT enumerated for cohort scope" in text

    after = _snap(data)
    assert after == before, "plan preview wrote key state"
    audits_after = _audits(data)
    assert audits_after == audits_before, "plan preview wrote audits"


# ---------------------------------------------------------------------------
# (b) Explicit keys scope: exact exclusions, atomic apply, preservation
# ---------------------------------------------------------------------------


def test_keys_plan_apply_persists_and_preserves(batch_env) -> None:
    data = batch_env
    client: TestClient = data["client"]
    key_ids = data["key_ids"]
    active_ids = set(key_ids[:N_ACTIVE])
    suspended_ids = set(key_ids[N_ACTIVE : N_ACTIVE + N_SUSPENDED])
    revoked_ids = set(key_ids[N_ACTIVE + N_SUSPENDED :])

    before = _snap(data)
    audits_before = _audits(data)
    assert len(audits_before) == 0

    # Review: 105 selected, 3 excluded with exact UUID + status; the
    # active control key is neither selected nor excluded.
    response = client.post(
        "/admin/key-batch/plan",
        data=_plan_fields(data["csrf"], data, selection_kind="keys"),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "105 selected" in text
    assert "105 changed" in text
    assert "0 unchanged" in text
    assert "3 excluded by status" in text
    for key_id in suspended_ids | revoked_ids:
        assert key_id in text, f"excluded {key_id[:8]} missing from review"
    assert "suspended" in text
    assert "revoked" in text
    # No literal dict-key rendering of the exclusion entries.
    assert "<code>key_id</code>" not in text
    assert "<code>status</code>" not in text

    token = TOKEN_RE.search(text)
    assert token is not None
    # The SAME original token is re-applied by the repeat test (c): the
    # same-operation repeat law, not a fresh zero-diff plan.
    data["original_token"] = token.group(1)

    # Apply: one atomic operation, 105 persisted changes, 105 audits.
    result = _apply(client, data["csrf"], token.group(1))
    assert result.status_code == 200, result.text[:500]
    assert "applied" in result.text
    # The signed review state is not retained on the result page.
    retained = token.group(1) in result.text
    assert retained is False, "review token retained on result page"

    after = _snap(data)
    audits = _audits(data)
    assert len(audits) == N_ACTIVE, "one audit per changed key"

    for key_id in key_ids:
        before_row = before[key_id]
        after_row = after[key_id]
        if key_id in active_ids:
            _snapshot_changed_key(before_row, after_row, key_id)
            audit = next(a for a in audits if a["entity_id"] == key_id)
            assert audit["admin_user_id"] == data["admin_id"]
            assert audit["note"] == APPLY_REASON
            recorded_change = (
                '"request_limit_total"' in audit["old_values"]
                and '"token_limit_total"' in audit["new_values"]
            )
            assert recorded_change, "audit did not record the reviewed change"
        else:
            # Excluded members are byte-identical (no partial writes).
            assert after_row == before_row, f"excluded {key_id[:8]} mutated"
    # The active out-of-scope control key is untouched (full tuple,
    # including updated_at: never written).
    assert after[data["control_key_id"]] == before[data["control_key_id"]]
    # No audit for excluded members or the control key.
    audited = {a["entity_id"] for a in audits}
    assert audited == active_ids


# ---------------------------------------------------------------------------
# (c) The SAME original reviewed plan, re-applied: already-at-target no-op
# ---------------------------------------------------------------------------


def test_repeat_original_plan_apply_already_at_target(batch_env) -> None:
    data = batch_env
    client: TestClient = data["client"]

    before = _snap(data)
    audits_before = _audits(data)
    assert len(audits_before) == N_ACTIVE

    # A FRESH re-plan of the same scope is itself a read-only zero-diff
    # preview (the selected keys currently equal the target).
    response = client.post(
        "/admin/key-batch/plan",
        data=_plan_fields(data["csrf"], data, selection_kind="keys"),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "105 selected" in text
    assert "0 changed" in text
    assert "105 unchanged" in text

    # The SAME ORIGINAL signed token from the first apply (c) is the
    # repeat: not a fresh plan, a repeated reviewed operation.
    original_token = data["original_token"]
    result = _apply(client, data["csrf"], original_token)
    assert result.status_code == 200, result.text[:500]
    assert "already_at_target" in result.text

    after = _snap(data)
    assert after == before, "repeat apply wrote state"
    audits_after = _audits(data)
    assert audits_after == audits_before, "repeat apply wrote audits"


# ---------------------------------------------------------------------------
# (d) Direct-DB drift after the plan: stale refusal, zero writes
# ---------------------------------------------------------------------------


def test_drift_after_plan_is_stale_zero_writes(batch_env) -> None:
    data = batch_env
    client: TestClient = data["client"]
    key_ids = data["key_ids"]
    drift_key = key_ids[0]

    response = client.post(
        "/admin/key-batch/plan",
        data=_plan_fields(data["csrf"], data, selection_kind="keys"),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:500]
    token = TOKEN_RE.search(response.text)
    assert token is not None

    # Operator-visible drift outside the reviewed flow (e.g. another
    # admin's single-key edit) between review and apply.
    _set_request_limit(data["database_url"], drift_key, 999)
    after_drift = _snap(data)

    result = _apply(client, data["csrf"], token.group(1))
    assert result.status_code == 400, result.text[:500]
    message = _error_message(result.text)
    assert "drifted after the review" in message
    assert "refused" in message
    # The fixed safe refusal carries no plan/credential material: the
    # drift value is not redisplayed in the message.
    drift_echoed = "999" in message
    assert drift_echoed is False, "drift value redisplayed in refusal"

    after = _snap(data)
    # Zero batch writes: the post-drift state (direct DB) is untouched.
    assert after == after_drift, "stale refusal wrote key state"
    audits_after = _audits(data)
    assert len(audits_after) == N_ACTIVE, "stale refusal wrote audits"


# ---------------------------------------------------------------------------
# (e) Direct status change after the plan: refused, whole set untouched
# ---------------------------------------------------------------------------


def test_status_change_after_plan_is_refused_no_writes(batch_env) -> None:
    data = batch_env
    client: TestClient = data["client"]
    key_ids = data["key_ids"]
    revoke_key = key_ids[0]  # the key left drifted (999) by (d)

    # A NEW reviewed plan whose target differs for EVERY selected key
    # (request set to 555): all 105 active are first-apply candidates.
    response = client.post(
        "/admin/key-batch/plan",
        data=_plan_fields(
            data["csrf"],
            data,
            selection_kind="keys",
            request_action="set",
            request_value=str(TARGET_REQUEST_SET),
        ),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "105 selected" in text
    assert "105 changed" in text
    token = TOKEN_RE.search(text)
    assert token is not None

    # A selected key leaves the reviewed status scope between review and
    # apply (direct DB, e.g. a concurrent single-key revoke).
    _set_status(data["database_url"], revoke_key, "revoked")
    after_revoke = _snap(data)

    result = _apply(client, data["csrf"], token.group(1))
    assert result.status_code == 400, result.text[:500]
    message = _error_message(result.text)
    assert "status or existence changed after the review" in message
    assert "refused" in message

    after = _snap(data)
    assert after == after_revoke, "refused apply wrote key state"
    audits_after = _audits(data)
    assert len(audits_after) == N_ACTIVE, "refused apply wrote audits"
    # No key received the reviewed target: the whole set is untouched.
    for key_id in key_ids:
        assert after[key_id][IDX_REQUEST_LIMIT] != TARGET_REQUEST_SET, (
            "reviewed target written"
        )


# ---------------------------------------------------------------------------
# (f) Late per-key write failure: the WHOLE operation rolls back
# ---------------------------------------------------------------------------


def test_late_write_failure_rolls_back_whole_operation(batch_env, monkeypatch) -> None:
    data = batch_env
    client: TestClient = data["client"]

    # A NEW reviewed plan that changes EVERY remaining active key
    # (request set to 777; after (e) exactly 104 keys are active): all
    # are first-apply candidates, so the write loop reaches the injected
    # late failure only AFTER earlier provisional updates/audits.
    response = client.post(
        "/admin/key-batch/plan",
        data=_plan_fields(
            data["csrf"],
            data,
            selection_kind="keys",
            request_action="set",
            request_value=str(LATE_FAILURE_REQUEST_SET),
        ),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "104 selected" in text
    assert "104 changed" in text
    token = TOKEN_RE.search(text)
    assert token is not None

    before = _snap(data)
    audits_before = _audits(data)
    assert len(audits_before) == N_ACTIVE

    # Known Core seam: the per-key configuration update, patched on the
    # shared KeyService class (the runtime scope builds a fresh instance
    # per request). The 3rd actual per-key write fails; keys 1-2 are
    # provisionally updated (and provisionally audited) first.
    original_update = KeyService.update_gateway_key_configuration
    applied_key_ids: list[str] = []

    async def late_failure(self, payload):
        applied_key_ids.append(str(payload.gateway_key_id))
        if len(applied_key_ids) == 3:
            raise RuntimeError("injected late per-key write failure")
        return await original_update(self, payload)

    monkeypatch.setattr(
        KeyService, "update_gateway_key_configuration", late_failure
    )

    with pytest.raises(RuntimeError, match="injected late per-key write failure"):
        _apply(client, data["csrf"], token.group(1))

    # The failure was reached only after EARLIER provisional updates:
    # two per-key updates actually executed before the 3rd one failed.
    assert len(applied_key_ids) == 3, "injected failure did not hit the write loop"

    after = _snap(data)
    # WHOLE-operation rollback: every key row (including the two
    # provisionally updated ones) and the legitimate updated_at of all
    # rows are exactly the pre-apply state.
    assert after == before, "late failure did not roll back all key state"
    audits_after = _audits(data)
    # ALL provisional audits of the whole operation rolled back.
    assert audits_after == audits_before, "late failure left provisional audits"
