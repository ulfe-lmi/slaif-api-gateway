"""216-a G14 accounting operations: owned-PG HTTP qualification.

Real-app, real-PostgreSQL qualification for the 216-a authenticated GUI:
four bounded read-only candidate views (with the honest 200-row cap and
no completeness claim), the four reviewed recovery action families
(dry-run -> signed review -> explicit confirm -> truthful result) on the
shared Core services, the whole-batch refusal law (ANY changed included
row refuses the WHOLE selection; terminal unchanged rows are safe
already-resolved no-ops), the exact 200-selection ceiling (20/21/200
accepted, 201 refuses), the sealed explicit no-charge intent contract,
the manual-vs-stored provenance boundary, unknown-cost holds, fenced
ordinary release refusal, repeat/unchanged recovery without duplicate
counters or audits, committed/rejected/unconfirmed outcomes at the REAL
transaction seam (commit-ack-loss is durable, never a rollback promise),
late audit rollback of the whole selected transaction, cached/waited
key freshness, reversed cross-key caller selection without deadlock
(ascending key UUID lock order), beyond-cap exact selection through the
known-record picker, and a nonzero unrelated sentinel preserved by full
mapped-field digests.

This module reuses the ``owned_pg_url`` fixture directly (one NEW owned
container, migrated) and is the SOLE PG owner of the run. No ambient DB,
no real provider, no email, no CLI; all rows are synthetic.

Proof seams: the commit-fault seam wraps the app's REAL sessionmaker at
a NAMED mutation phase (audit-action marker, never a blind commit count)
and raises from the REAL session's own named lifecycle events (before_commit
for the PRE-COMMIT mode, after_commit for the REAL-COMMIT-THEN-RAISE
ACK-LOSS mode); the late
audit fault seam raises inside Core's audit step (test-only, labelled);
the concurrency probes use SEPARATE fresh PG sessions in worker threads
(no asyncio.run on the live ASGI loop); the preservation proof uses full
mapped-field row digests with an explicit allowed-change set (allowed
changes are exactly the reviewed target rows plus their key counters,
fence fields, new expired-ledger rows, and append-only audit rows).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AdminUser,
    AuditLog,
    GatewayKey,
    ModelRoute,
    Owner,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReasonCode,
    safe_hold_metadata,
)
from slaif_gateway.services.admin_accounting_operations import (
    AdminAccountingOperationsService,
    AccountingReviewTarget,
    fingerprint_expired_reservation,
)
from slaif_gateway.services.reconciliation_errors import ReconciliationError
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
# Reuse the qualified owned PostgreSQL fixture (never an ambient fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture

ADMIN_PASSWORD = "correct horse battery staple"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
REVIEW_TOKEN_RE = re.compile(r'name="review_token" value="([^"]+)"')

# Credential-shaped canary: a full accepted-prefix gateway-key value seeded
# into a free-text candidate fact. It must be MASKED in every rendered
# surface (view + review) and can never round-trip as a manual assertion
# (the existing pure alias guard refuses it pre-seal).
CREDENTIAL_CANARY = "sk-slaif-" + "ab" * 16

BASE = "/admin/accounting-operations"
VIEW_EXPIRED = f"{BASE}/expired-reservations"
VIEW_FENCES = f"{BASE}/external-tool-fences"
VIEW_HOLDS = f"{BASE}/external-tool-holds"
VIEW_PROVIDER = f"{BASE}/provider-completed-recovery"
PREVIEW_EXPIRED = f"{BASE}/expired-reservations/preview"
APPLY_EXPIRED = f"{BASE}/expired-reservations/apply"
PREVIEW_PROVIDER = f"{BASE}/provider-completed-recovery/preview"
APPLY_PROVIDER = f"{BASE}/provider-completed-recovery/apply"
PREVIEW_HOLDS = f"{BASE}/external-tool-holds/preview"
APPLY_HOLDS = f"{BASE}/external-tool-holds/apply"

# Audit actions the 216 mutation transactions write (the commit-fault seam
# identifies the mutation commit by these, never by a blind commit count).
_MUTATION_AUDIT_ACTIONS = frozenset(
    {
        "quota_reservation_expired",
        "provider_completed_reconciliation",
        "external_tool_accounting_hold_reconciled",
    }
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        GATEWAY_KEY_PREFIX="sk-slaif-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1=generate_secret_key(),
        ENABLE_ADMIN_DASHBOARD=True,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return str(value)


def _row_digest(model: type, row: Any, exclude: frozenset[str] = frozenset()) -> str:
    """Full mapped-field digest of one row (every column attribute)."""
    columns = [attr.key for attr in sa_inspect(model).column_attrs if attr.key not in exclude]
    canonical = json.dumps(
        {c: _jsonable(getattr(row, c)) for c in columns},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Login bookkeeping legitimately touches ONLY these auth-tracking columns;
# every other admin identity field is invariant.
_ADMIN_USER_AUTH_TRACKING = frozenset({"last_login_at", "updated_at"})


def _preservation_snapshot(database_url: str) -> dict[str, dict[str, str]]:
    """Per-row mapped-field digests for every table the accounting ops touch."""

    async def _run(session) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for name, model in (
            ("gateway_keys", GatewayKey),
            ("usage_ledger", UsageLedger),
            ("quota_reservations", QuotaReservation),
            ("audit_log", AuditLog),
            ("owners", Owner),
        ):
            rows = list((await session.execute(select(model))).scalars().all())
            out[name] = {str(r.id): _row_digest(model, r) for r in rows}
        admin_rows = list((await session.execute(select(AdminUser))).scalars().all())
        out["admin_users"] = {
            str(r.id): _row_digest(AdminUser, r, exclude=_ADMIN_USER_AUTH_TRACKING)
            for r in admin_rows
        }
        return out

    return _db_worker(database_url, _run)


def _db_worker(database_url: str, coro_factory) -> Any:
    """Run a DB coroutine in a WORKER THREAD (the 214/215 threaded pattern).

    The primary TestClient owns a live ASGI loop thread where
    ``asyncio.run`` would raise; a fresh worker thread has no running loop,
    so the SEPARATE fresh PG connection used by the concurrency/fault
    probes is safe there.
    """
    box: dict[str, Any] = {}

    def _worker() -> None:
        async def _run() -> None:
            engine = create_async_engine(database_url, future=True)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    box["value"] = await coro_factory(session)
            finally:
                await engine.dispose()

        try:
            asyncio.run(_run())
        except BaseException as exc:  # re-raised below
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def _login(client: TestClient, *, email: str) -> None:
    response = client.get("/admin/login")
    assert response.status_code == 200
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        "/admin/login",
        data={"csrf_token": csrf, "email": email, "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _page_csrf(client: TestClient, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200
    return CSRF_RE.search(response.text).group(1)


def _review_token_from(response) -> str:
    match = REVIEW_TOKEN_RE.search(response.text)
    assert match, "review page did not seal a review token"
    return match.group(1)


def _get_reservation(database_url: str, reservation_id: uuid.UUID) -> QuotaReservation:
    async def _run(session) -> QuotaReservation:
        row = await session.get(QuotaReservation, reservation_id)
        assert row is not None
        return row

    return _db_worker(database_url, _run)


def _get_ledger_by_request(database_url: str, request_id: str) -> UsageLedger | None:
    async def _run(session) -> UsageLedger | None:
        rows = (
            (await session.execute(select(UsageLedger).where(UsageLedger.request_id == request_id)))
            .scalars()
            .all()
        )
        return rows[0] if rows else None

    return _db_worker(database_url, _run)


def _get_key(database_url: str, key_id: uuid.UUID) -> GatewayKey:
    async def _run(session) -> GatewayKey:
        row = await session.get(GatewayKey, key_id)
        assert row is not None
        return row

    return _db_worker(database_url, _run)


def _audit_rows(database_url: str, *, action: str, entity_id: uuid.UUID | None = None) -> list[AuditLog]:
    async def _run(session) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.action == action)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        return list((await session.execute(stmt)).scalars().all())

    return _db_worker(database_url, _run)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _hold_ledger_metadata(reason_code: str, evidence_quality: str, held_at: datetime) -> dict[str, Any]:
    return safe_hold_metadata(
        reason_code=ExternalToolHoldReasonCode(reason_code),  # type: ignore[arg-type]
        evidence_quality=ExternalToolHoldEvidenceQuality(evidence_quality),  # type: ignore[arg-type]
        held_at=held_at,
    )


async def _seed_all(database_url: str, settings: Settings) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                super_admin = await _create_admin(session, f"gui216-super-{suffix}@example.org", "superadmin")
                plain_admin = await _create_admin(session, f"gui216-admin-{suffix}@example.org", "admin")
                owner_a = await OwnersRepository(session).create_owner(
                    name="Ivo", surname=f"216-{suffix}", email=f"ivo-{suffix}@example.org"
                )
                owner_b = await OwnersRepository(session).create_owner(
                    name="Mara", surname=f"216-{suffix}", email=f"mara-{suffix}@example.org"
                )
                keys_repo = GatewayKeysRepository(session)

                # Bound routes for the fenced reservations' route facts
                # (external_tool_route_id is a real FK to model_routes).
                hold_routes: dict[str, uuid.UUID] = {}
                for provider in ("prov-hold-216", "prov-hold3-216", "prov-f2-216"):
                    route = ModelRoute(
                        id=uuid.uuid4(),
                        requested_model=f"route-{provider}",
                        match_type="exact",
                        endpoint="/v1/responses",
                        provider=provider,
                        upstream_model=f"route-{provider}",
                        priority=100,
                        enabled=True,
                        capabilities={},
                    )
                    session.add(route)
                    hold_routes[provider] = route.id

                # ---- Key A: 101 ordinary EXPIRED pending reservations ----
                key_a = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216a-{suffix}",
                    token_hash=f"216a-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_a.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=True,
                    allowed_models=[],
                    allow_all_endpoints=True,
                    allowed_endpoints=[],
                    cost_limit_eur=Decimal("500"),
                    token_limit_total=5_000_000,
                    request_limit_total=500,
                )
                key_a.cost_used_eur = Decimal("7.25")
                key_a.tokens_used_total = 101
                key_a.requests_used_total = 7
                resv_a: list[QuotaReservation] = []
                for i in range(1, 102):
                    model = CREDENTIAL_CANARY if i == 101 else f"model-216a-{i:03d}"
                    resv = QuotaReservation(
                        id=uuid.uuid4(),
                        gateway_key_id=key_a.id,
                        request_id=f"req-216a-{suffix}-{i:03d}",
                        endpoint="/v1/chat/completions",
                        requested_model=model,
                        provider="prov-216a",
                        reserved_cost_eur=Decimal("0.01"),
                        reserved_tokens=100,
                        reserved_requests=1,
                        status="pending",
                        expires_at=now - timedelta(hours=i),
                        # The canary row is OLDER than the picker's
                        # latest-100 page, so the known-record search is
                        # the only user-reachable exact path to it.
                        **({"created_at": now - timedelta(days=2)} if i == 101 else {}),
                    )
                    session.add(resv)
                    resv_a.append(resv)
                key_a.cost_reserved_eur = Decimal("1.01")
                key_a.tokens_reserved_total = 10_100
                key_a.requests_reserved_total = 101

                # ---- Key B: 11 ordinary EXPIRED pending reservations ----
                key_b = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216b-{suffix}",
                    token_hash=f"216b-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_b.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=True,
                    allowed_models=[],
                    allow_all_endpoints=True,
                    allowed_endpoints=[],
                    cost_limit_eur=Decimal("100"),
                    token_limit_total=1_000_000,
                    request_limit_total=100,
                )
                key_b.cost_used_eur = Decimal("0.5")
                key_b.tokens_used_total = 50
                key_b.requests_used_total = 2
                resv_b: list[QuotaReservation] = []
                for i in range(1, 12):
                    resv = QuotaReservation(
                        id=uuid.uuid4(),
                        gateway_key_id=key_b.id,
                        request_id=f"req-216b-{suffix}-{i:02d}",
                        endpoint="/v1/chat/completions",
                        requested_model=f"model-216b-{i:02d}",
                        provider="prov-216b",
                        reserved_cost_eur=Decimal("0.02"),
                        reserved_tokens=200,
                        reserved_requests=1,
                        status="pending",
                        expires_at=now - timedelta(hours=100 + i),
                    )
                    session.add(resv)
                    resv_b.append(resv)
                key_b.cost_reserved_eur = Decimal("0.22")
                key_b.tokens_reserved_total = 2_200
                key_b.requests_reserved_total = 11

                # ---- Key FILL: 205 ordinary EXPIRED pending filler rows,
                # each OLDER than every key A/B row (now-150h..now-354h).
                # The capped 200-row candidate view therefore shows ONLY
                # filler rows: the canary and ALL key A/B rows sit
                # genuinely beyond the view cap, so the known-record
                # exact-selection path is the real user-reachable route
                # to them.  Counters are the static sum of its rows
                # (never settled in this module).
                key_fill = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216fill-{suffix}",
                    token_hash=f"216fill-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_b.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=True,
                    allowed_models=[],
                    allow_all_endpoints=True,
                    allowed_endpoints=[],
                    cost_limit_eur=Decimal("1000"),
                    token_limit_total=5_000_000,
                    request_limit_total=500,
                )
                resv_fill: list[QuotaReservation] = []
                for i in range(205):
                    resv = QuotaReservation(
                        id=uuid.uuid4(),
                        gateway_key_id=key_fill.id,
                        request_id=f"req-216fill-{suffix}-{i:03d}",
                        endpoint="/v1/chat/completions",
                        requested_model=f"filler-216-{i:03d}",
                        provider="prov-216fill",
                        reserved_cost_eur=Decimal("0.01"),
                        reserved_tokens=100,
                        reserved_requests=1,
                        status="pending",
                        expires_at=now - timedelta(hours=150 + i),
                    )
                    session.add(resv)
                    resv_fill.append(resv)
                key_fill.cost_reserved_eur = Decimal("2.05")
                key_fill.tokens_reserved_total = 20_500
                key_fill.requests_reserved_total = 205

                # ---- Key F: held external-tool fence + held row (partial
                # facts: unknown FINAL cost stays held) ----
                key_f = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216f-{suffix}",
                    token_hash=f"216f-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_a.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=False,
                    allowed_models=["model-hold-216"],
                    allow_all_endpoints=False,
                    allowed_endpoints=["/v1/responses"],
                    cost_limit_eur=Decimal("100"),
                    token_limit_total=1_000_000,
                    request_limit_total=100,
                )
                key_f.cost_used_eur = Decimal("1.10")
                key_f.tokens_used_total = 25
                key_f.requests_used_total = 3
                resv_f = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=key_f.id,
                    request_id=f"req-216f-{suffix}",
                    endpoint="/v1/responses",
                    requested_model="model-hold-216",
                    provider="prov-hold-216",
                    quota_mode="external_tool_fenced",
                    external_tool_provider="prov-hold-216",
                    external_tool_route_id=hold_routes["prov-hold-216"],
                    external_tool_capabilities=["functions"],
                    external_tool_destination_ids=[],
                    reserved_cost_eur=Decimal("0.50"),
                    reserved_tokens=5000,
                    reserved_requests=1,
                    status="pending",
                    expires_at=now + timedelta(hours=1),
                )
                session.add(resv_f)
                # The gateway_keys fence back-reference is a bare FK
                # (no ORM relationship orders the inserts): the
                # reservation row must EXIST before the key row updates
                # flush.
                await session.flush()
                key_f.cost_reserved_eur = Decimal("0.50")
                key_f.tokens_reserved_total = 5000
                key_f.requests_reserved_total = 1
                key_f.external_tool_fence_state = "held"
                key_f.external_tool_fence_reservation_id = resv_f.id
                key_f.external_tool_fence_request_id = resv_f.request_id
                key_f.external_tool_fence_acquired_at = now - timedelta(hours=2)
                key_f.external_tool_fence_expires_at = now + timedelta(hours=1)
                ledger_f = UsageLedger(
                    id=uuid.uuid4(),
                    request_id=resv_f.request_id,
                    gateway_key_id=key_f.id,
                    owner_id=owner_a.id,
                    quota_reservation_id=resv_f.id,
                    owner_name_snapshot=owner_a.name,
                    owner_surname_snapshot=owner_a.surname,
                    endpoint="/v1/responses",
                    provider="prov-hold-216",
                    requested_model="model-hold-216",
                    streaming=False,
                    success=None,
                    accounting_status="estimated",
                    # place() stores partial facts in total_tokens /
                    # estimated_cost_eur only; usage_raw stays EMPTY (a
                    # hold ledger with raw usage evidence is not a valid
                    # reconciliation candidate).
                    prompt_tokens=0,
                    completion_tokens=0,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=1200,
                    estimated_cost_eur=Decimal("0.05"),
                    actual_cost_eur=None,
                    usage_raw={},
                    response_metadata=_hold_ledger_metadata(
                        "missing_final_cost", "partial_estimate", now - timedelta(hours=1)
                    ),
                    started_at=now - timedelta(hours=2),
                )
                session.add(ledger_f)

                # ---- Key F3: held fence + held row (NO partial facts at all)
                key_f3 = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216f3-{suffix}",
                    token_hash=f"216f3-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_b.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=False,
                    allowed_models=["model-hold3-216"],
                    allow_all_endpoints=False,
                    allowed_endpoints=["/v1/responses"],
                    cost_limit_eur=Decimal("100"),
                    token_limit_total=1_000_000,
                    request_limit_total=100,
                )
                key_f3.cost_used_eur = Decimal("0.75")
                key_f3.tokens_used_total = 10
                key_f3.requests_used_total = 1
                resv_f3 = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=key_f3.id,
                    request_id=f"req-216f3-{suffix}",
                    endpoint="/v1/responses",
                    requested_model="model-hold3-216",
                    provider="prov-hold3-216",
                    quota_mode="external_tool_fenced",
                    external_tool_provider="prov-hold3-216",
                    external_tool_route_id=hold_routes["prov-hold3-216"],
                    external_tool_capabilities=["functions"],
                    external_tool_destination_ids=[],
                    reserved_cost_eur=Decimal("0.25"),
                    reserved_tokens=2500,
                    reserved_requests=1,
                    status="pending",
                    expires_at=now + timedelta(hours=1),
                )
                session.add(resv_f3)
                await session.flush()  # same fence-FK ordering as key F
                key_f3.cost_reserved_eur = Decimal("0.25")
                key_f3.tokens_reserved_total = 2500
                key_f3.requests_reserved_total = 1
                key_f3.external_tool_fence_state = "held"
                key_f3.external_tool_fence_reservation_id = resv_f3.id
                key_f3.external_tool_fence_request_id = resv_f3.request_id
                key_f3.external_tool_fence_acquired_at = now - timedelta(hours=3)
                key_f3.external_tool_fence_expires_at = now + timedelta(hours=1)
                ledger_f3 = UsageLedger(
                    id=uuid.uuid4(),
                    request_id=resv_f3.request_id,
                    gateway_key_id=key_f3.id,
                    owner_id=owner_b.id,
                    quota_reservation_id=resv_f3.id,
                    owner_name_snapshot=owner_b.name,
                    owner_surname_snapshot=owner_b.surname,
                    endpoint="/v1/responses",
                    provider="prov-hold3-216",
                    requested_model="model-hold3-216",
                    streaming=False,
                    success=None,
                    accounting_status="interrupted",
                    prompt_tokens=0,
                    completion_tokens=0,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    estimated_cost_eur=None,
                    actual_cost_eur=None,
                    usage_raw={},
                    response_metadata=_hold_ledger_metadata(
                        "missing_final_usage", "missing", now - timedelta(hours=2)
                    ),
                    started_at=now - timedelta(hours=3),
                )
                session.add(ledger_f3)

                # ---- Key F2: fenced reservation that is ALSO expired (the
                # ordinary release path must refuse it, never forgive at 0)
                key_f2 = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216f2-{suffix}",
                    token_hash=f"216f2-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_a.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=False,
                    allowed_models=["model-f2-216"],
                    allow_all_endpoints=False,
                    allowed_endpoints=["/v1/responses"],
                    cost_limit_eur=Decimal("100"),
                    token_limit_total=1_000_000,
                    request_limit_total=100,
                )
                key_f2.cost_used_eur = Decimal("0.10")
                key_f2.tokens_used_total = 5
                key_f2.requests_used_total = 1
                resv_f2 = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=key_f2.id,
                    request_id=f"req-216f2-{suffix}",
                    endpoint="/v1/responses",
                    requested_model="model-f2-216",
                    provider="prov-f2-216",
                    quota_mode="external_tool_fenced",
                    external_tool_provider="prov-f2-216",
                    external_tool_route_id=hold_routes["prov-f2-216"],
                    external_tool_capabilities=["functions"],
                    external_tool_destination_ids=[],
                    reserved_cost_eur=Decimal("0.10"),
                    reserved_tokens=1000,
                    reserved_requests=1,
                    status="pending",
                    expires_at=now - timedelta(hours=2),
                )
                session.add(resv_f2)
                key_f2.cost_reserved_eur = Decimal("0.10")
                key_f2.tokens_reserved_total = 1000
                key_f2.requests_reserved_total = 1

                # ---- Key P: provider-completed finalization failure ----
                key_p = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216p-{suffix}",
                    token_hash=f"216p-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_b.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=True,
                    allowed_models=[],
                    allow_all_endpoints=True,
                    allowed_endpoints=[],
                    cost_limit_eur=Decimal("100"),
                    token_limit_total=1_000_000,
                    request_limit_total=100,
                )
                key_p.cost_used_eur = Decimal("2.00")
                key_p.tokens_used_total = 20
                key_p.requests_used_total = 4
                resv_p = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=key_p.id,
                    request_id=f"req-216p-{suffix}",
                    endpoint="/v1/chat/completions",
                    # Credential-shaped free-text fact: the provider view
                    # must MASK it in the rendered row, keep the raw
                    # machine fact, and never carry it into the audit.
                    requested_model=CREDENTIAL_CANARY,
                    provider="prov-pc-216",
                    reserved_cost_eur=Decimal("0.30"),
                    reserved_tokens=3000,
                    reserved_requests=1,
                    status="pending",
                    expires_at=now + timedelta(hours=1),
                )
                session.add(resv_p)
                key_p.cost_reserved_eur = Decimal("0.30")
                key_p.tokens_reserved_total = 3000
                key_p.requests_reserved_total = 1
                ledger_p = UsageLedger(
                    id=uuid.uuid4(),
                    request_id=resv_p.request_id,
                    gateway_key_id=key_p.id,
                    owner_id=owner_b.id,
                    quota_reservation_id=resv_p.id,
                    owner_name_snapshot=owner_b.name,
                    owner_surname_snapshot=owner_b.surname,
                    endpoint="/v1/chat/completions",
                    provider="prov-pc-216",
                    requested_model=CREDENTIAL_CANARY,
                    resolved_model=CREDENTIAL_CANARY,
                    streaming=False,
                    success=True,
                    http_status=200,
                    accounting_status="failed",
                    prompt_tokens=600,
                    completion_tokens=300,
                    input_tokens=600,
                    output_tokens=300,
                    total_tokens=900,
                    estimated_cost_eur=Decimal("0.30"),
                    actual_cost_eur=Decimal("0.28"),
                    usage_raw={"pc": "216p"},
                    response_metadata={
                        "needs_reconciliation": True,
                        "recovery_state": "provider_completed_finalization_failed",
                    },
                    started_at=now - timedelta(hours=1),
                    finished_at=now - timedelta(minutes=50),
                    latency_ms=900,
                )
                session.add(ledger_p)

                # ---- Key S: small LEGAL unrelated nonzero sentinel ----
                key_s = await keys_repo.create_gateway_key_record(
                    public_key_id=f"216s-{suffix}",
                    token_hash=f"216s-{suffix}-hash-{uuid.uuid4().hex}",
                    owner_id=owner_a.id,
                    valid_from=now - timedelta(days=10),
                    valid_until=now + timedelta(days=200),
                    status="active",
                    allow_all_models=False,
                    allowed_models=[f"sent-216-{suffix}"],
                    allow_all_endpoints=False,
                    allowed_endpoints=["/v1/chat/completions"],
                    cost_limit_eur=Decimal("42.5"),
                    token_limit_total=1_234_567,
                    request_limit_total=89,
                )
                key_s.cost_used_eur = Decimal("9.99")
                key_s.tokens_used_total = 999
                key_s.requests_used_total = 9
                resv_s = QuotaReservation(
                    id=uuid.uuid4(),
                    gateway_key_id=key_s.id,
                    request_id=f"req-216s-{suffix}",
                    endpoint="/v1/chat/completions",
                    requested_model=f"sent-216-{suffix}",
                    provider="prov-216s",
                    reserved_cost_eur=Decimal("0.05"),
                    reserved_tokens=50,
                    reserved_requests=1,
                    status="pending",
                    expires_at=now + timedelta(days=30),
                )
                session.add(resv_s)
                key_s.cost_reserved_eur = Decimal("0.05")
                key_s.tokens_reserved_total = 50
                key_s.requests_reserved_total = 1
                ledger_s = UsageLedger(
                    id=uuid.uuid4(),
                    request_id=f"req-216s-led-{suffix}",
                    gateway_key_id=key_s.id,
                    owner_id=owner_a.id,
                    quota_reservation_id=resv_s.id,
                    owner_name_snapshot=owner_a.name,
                    owner_surname_snapshot=owner_a.surname,
                    endpoint="/v1/chat/completions",
                    provider="prov-216s",
                    requested_model=f"sent-216-{suffix}",
                    resolved_model=f"sent-216-{suffix}",
                    streaming=False,
                    success=True,
                    http_status=200,
                    accounting_status="finalized",
                    prompt_tokens=70,
                    completion_tokens=30,
                    input_tokens=70,
                    output_tokens=30,
                    total_tokens=100,
                    estimated_cost_eur=Decimal("0.10"),
                    actual_cost_eur=Decimal("0.10"),
                    usage_raw={"sentinel": "216a"},
                    response_metadata={},
                    started_at=now - timedelta(days=3),
                    finished_at=now - timedelta(days=3),
                    latency_ms=120,
                )
                session.add(ledger_s)

                return {
                    "super_admin_email": super_admin.email,
                    "super_admin_id": super_admin.id,
                    "plain_admin_email": plain_admin.email,
                    "plain_admin_id": plain_admin.id,
                    "owner_a_id": owner_a.id,
                    "owner_b_id": owner_b.id,
                    "key_a": key_a.id,
                    "key_b": key_b.id,
                    "key_fill": key_fill.id,
                    "resv_fill": [r.id for r in resv_fill],
                    "key_f": key_f.id,
                    "key_f2": key_f2.id,
                    "key_f3": key_f3.id,
                    "key_p": key_p.id,
                    "key_s": key_s.id,
                    "resv_a": [r.id for r in resv_a],
                    "resv_b": [r.id for r in resv_b],
                    "resv_a_canary": resv_a[100].id,
                    "resv_f": resv_f.id,
                    "resv_f2": resv_f2.id,
                    "resv_f3": resv_f3.id,
                    "resv_p": resv_p.id,
                    "resv_s": resv_s.id,
                    "ledger_f": ledger_f.id,
                    "ledger_f3": ledger_f3.id,
                    "ledger_p": ledger_p.id,
                    "ledger_s": ledger_s.id,
                    "request_f": resv_f.request_id,
                    "request_p": resv_p.request_id,
                }
    finally:
        await engine.dispose()


async def _create_admin(session, email: str, role: str) -> AdminUser:
    from slaif_gateway.db.repositories.admin_users import AdminUsersRepository

    return await AdminUsersRepository(session).create_admin_user(
        email=email,
        display_name=f"216 {role} admin",
        password_hash=hash_admin_password(ADMIN_PASSWORD),
        role=role,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Commit-fault seam (215 pattern): REAL session, NAMED mutation phase
# ---------------------------------------------------------------------------


class _216CommitFaultSessionmaker:
    """Fails the app's real sessionmaker at the 216 MUTATION commit.

    Phase identification (pure REAL SQLAlchemy behavior): the mutation
    transaction is the one whose session ADDS an audit row whose action is
    one of the 216 mutation actions (the read scopes add none).  The seam
    wraps the real ``session.add`` (test-only, in fixture sessions only)
    and records the marker in ``session.info``; the named session-local
    lifecycle events read that same dict - never a blind commit count.

    The fault itself is raised from the REAL SQLAlchemy session events on
    the fixture session (per-instance listeners only):

    test="pre-commit": raised in ``before_commit`` - the real COMMIT is
    never issued, the transaction rolls back, and durability is
    unconfirmed.
    test="ack-loss": raised in ``after_commit`` - the real commit has
    already COMPLETED (the write is durable) and then the seam raises:
    a lost-ack simulation where the client saw a failure although the
    commit landed.
    """

    def __init__(self, inner: Any, *, test: str = "pre-commit") -> None:
        assert test in {"pre-commit", "ack-loss"}
        self.inner = inner
        self.test = test
        self.hit = False
        self.ack_loss_committed = False

    def __call__(self) -> Any:
        session = self.inner()
        inner_add = session.add

        def add(obj: Any) -> None:
            action = getattr(obj, "action", None)
            if action in _MUTATION_AUDIT_ACTIONS:
                session.info["216_fault_phase"] = "mutation"
            inner_add(obj)

        def _mutation_phase(sync_session: Any) -> bool:
            return sync_session.info.get("216_fault_phase") == "mutation"

        def _before_commit(sync_session: Any) -> None:
            if not _mutation_phase(sync_session):
                return
            self.hit = True
            if self.test == "pre-commit":
                # The real COMMIT is never issued: SQLAlchemy rolls the
                # transaction back and the fault propagates through the
                # app's ``async with session.begin()`` exit unchanged.
                raise RuntimeError("pre-commit fault seam (fixture)")

        def _after_commit(sync_session: Any) -> None:
            if not _mutation_phase(sync_session):
                return
            self.hit = True
            if self.test == "ack-loss":
                # The real commit has ALREADY completed (the write is
                # durable); raising here is the lost-ack simulation.
                self.ack_loss_committed = True
                raise RuntimeError("ack-loss fault seam (fixture)")

        # Session-LOCAL lifecycle events on the REAL session (no custom
        # transaction/context proxies, no production seam): AsyncSession
        # proxies ``info`` to the same dict these events observe.
        event.listen(session.sync_session, "before_commit", _before_commit)
        event.listen(session.sync_session, "after_commit", _after_commit)
        session.add = add
        return session


# ---------------------------------------------------------------------------
# Module environment: owned PG (sole owner) + real app
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env216(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    settings = _settings(owned_pg_url)
    base = asyncio.run(_seed_all(owned_pg_url, settings))
    base["settings"] = settings
    base["database_url"] = owned_pg_url
    # Preservation-proof bookkeeping: the ONLY rows that may differ between
    # the BEFORE and AFTER digests are the reviewed targets plus their
    # linked keys/ledgers (tests add their own ids as they run); every
    # other row must survive byte-identical.
    base["allowed_reservation_ids"]: set[str] = set()
    base["allowed_ledger_ids"]: set[str] = set()
    base["allowed_key_ids"]: set[str] = set()
    base["preservation_before"] = _preservation_snapshot(owned_pg_url)

    app = create_app(settings)
    # Lifespan-managed client: create_app leaves db_sessionmaker unset; the
    # app LIFESPAN initializes it. One client = one portal; the secondary
    # logins switch the SAME client via a cookie-jar swap (215 pattern).
    with TestClient(app) as client:
        _login(client, email=base["super_admin_email"])
        base["client"] = client
        base["app"] = app
        yield base


# ---------------------------------------------------------------------------
# HTTP form helpers
# ---------------------------------------------------------------------------

_TBodies_RE = re.compile(r"<tbody>(.*?)</tbody>", re.DOTALL)


def _table_bodies(text: str) -> str:
    """The actual rendered table rows (TBODY-scoped, 215 pattern)."""
    bodies = _TBodies_RE.findall(text)
    assert bodies, "no table body rendered"
    return "\n".join(bodies)


def _review_submit(response: Any) -> tuple[str, str]:
    """(review_token, csrf_token) from a sealed review page."""
    token = _review_token_from(response)
    csrf = CSRF_RE.search(response.text)
    assert csrf, "review page carries no CSRF token"
    return token, csrf.group(1)


def _apply_post(client: TestClient, url: str, token: str, csrf: str) -> Any:
    return client.post(
        url,
        data={"csrf_token": csrf, "review_token": token, "confirm_apply": "1"},
    )


def _form(data: Sequence[tuple[str, str]]) -> dict[str, list[str]]:
    # Form pairs -> mapping-of-lists so httpx serializes a proper
    # application/x-www-form-urlencoded body with REPEATED keys (this
    # httpx build does not url-encode a bare list of pairs).
    form: dict[str, list[str]] = {}
    for key, value in data:
        form.setdefault(key, []).append(value)
    return form


def _preview_expired(
    client: TestClient,
    *,
    target_ids: Sequence[uuid.UUID] = (),
    exact_ids: Sequence[uuid.UUID] = (),
    reason: str = "expired preview",
) -> Any:
    data: list[tuple[str, str]] = [
        ("csrf_token", _page_csrf(client, VIEW_EXPIRED)),
        ("reason", reason),
    ]
    for rid in target_ids:
        data.append(("target_id", str(rid)))
    for rid in exact_ids:
        data.append(("exact_reservation_id", str(rid)))
    return client.post(PREVIEW_EXPIRED, data=_form(data))


def _preview_provider(
    client: TestClient,
    *,
    target_ids: Sequence[uuid.UUID] = (),
    exact_ids: Sequence[uuid.UUID] = (),
    reason: str = "provider preview",
) -> Any:
    data: list[tuple[str, str]] = [
        ("csrf_token", _page_csrf(client, VIEW_PROVIDER)),
        ("reason", reason),
    ]
    for lid in target_ids:
        data.append(("target_id", str(lid)))
    for lid in exact_ids:
        data.append(("exact_ledger_id", str(lid)))
    return client.post(PREVIEW_PROVIDER, data=_form(data))


def _preview_hold(
    client: TestClient,
    *,
    reservation_id: uuid.UUID | None = None,
    exact_id: uuid.UUID | None = None,
    action: str = "finalize-actual",
    reason: str = "hold preview",
    confirm_no_charge: bool = False,
    actual_cost_eur: str = "",
    actual_total_tokens: str = "",
    outcome: str = "",
) -> Any:
    data: list[tuple[str, str]] = [
        ("csrf_token", _page_csrf(client, VIEW_HOLDS)),
        ("hold_action", action),
        ("reason", reason),
    ]
    if reservation_id is not None:
        data.append(("reservation_id", str(reservation_id)))
    if exact_id is not None:
        data.append(("exact_reservation_id", str(exact_id)))
    if confirm_no_charge:
        data.append(("confirm_no_charge", "1"))
    if actual_cost_eur:
        data.append(("actual_cost_eur", actual_cost_eur))
    if actual_total_tokens:
        data.append(("actual_total_tokens", actual_total_tokens))
    if outcome:
        data.append(("outcome", outcome))
    return client.post(PREVIEW_HOLDS, data=_form(data))


# ---------------------------------------------------------------------------
# Direct-service worker probes (separate fresh PG sessions, worker threads)
# ---------------------------------------------------------------------------


def _service_worker(database_url: str, coro_factory) -> Any:
    """Like _db_worker, but the coroutine also gets the reviewed-ops service."""
    from slaif_gateway.api.admin_accounting_operations import _build_service

    def _inner(session) -> Any:
        return coro_factory(session, _build_service(session))

    return _db_worker(database_url, _inner)


def _get_ledger_by_id(database_url: str, ledger_id: uuid.UUID) -> UsageLedger:
    async def _run(session) -> UsageLedger:
        row = await session.get(UsageLedger, ledger_id)
        assert row is not None
        return row

    return _db_worker(database_url, _run)


def _get_ledger_by_reservation(database_url: str, reservation_id: uuid.UUID) -> UsageLedger | None:
    async def _run(session) -> UsageLedger | None:
        rows = (
            (
                await session.execute(
                    select(UsageLedger).where(UsageLedger.quota_reservation_id == reservation_id)
                )
            )
            .scalars()
            .all()
        )
        return rows[0] if rows else None

    return _db_worker(database_url, _run)


def _key_counters(database_url: str, key_id: uuid.UUID) -> tuple[Decimal, int, int]:
    async def _run(session) -> tuple[Decimal, int, int]:
        key = await session.get(GatewayKey, key_id)
        assert key is not None
        return key.cost_reserved_eur, key.tokens_reserved_total, key.requests_reserved_total

    return _db_worker(database_url, _run)


def _same_row_lock_contention_probe(
    database_url: str, reservation_id: uuid.UUID, actor_admin_id: uuid.UUID
) -> None:
    """Two REAL service sessions: one holds the row lock, the other WAITS.

    The waiting apply must observe the changed (settled) row AFTER the wait
    and refuse safely - it must never double-settle the same reservation.
    """
    locked = threading.Event()
    waiter_at_gate = threading.Event()
    proceed = threading.Event()
    holder_box: dict[str, Any] = {}
    waiter_box: dict[str, Any] = {}

    async def _holder_run(session, service) -> Any:
        async with session.begin():
            rows = await service._quota.get_reservations_by_ids_for_update([reservation_id])
            fingerprint = fingerprint_expired_reservation(rows[0])
            locked.set()
            assert proceed.wait(timeout=90), "holder proceed timed out"
            return await service.apply_expired(
                targets=[AccountingReviewTarget(reservation_id, fingerprint)],
                actor_admin_id=actor_admin_id,
                reason="contention holder",
            )

    async def _waiter_run(session, service) -> Any:
        async with session.begin():
            pre = await service._quota.get_reservation_by_id(reservation_id)
        assert pre is not None
        fingerprint = fingerprint_expired_reservation(pre)
        # Signal BEFORE the apply transaction issues its FOR UPDATE, so the
        # observed wait is on the real held PG row lock (not thread startup).
        waiter_at_gate.set()
        start = time.monotonic()
        try:
            async with session.begin():
                await service.apply_expired(
                    targets=[AccountingReviewTarget(reservation_id, fingerprint)],
                    actor_admin_id=actor_admin_id,
                    reason="contention waiter",
                )
            waiter_box["outcome"] = "no-error"
        except BaseException as exc:  # recorded, asserted below
            waiter_box["outcome"] = type(exc).__name__
        waiter_box["elapsed"] = time.monotonic() - start
        return None

    def _holder_thread() -> None:
        try:
            holder_box["result"] = _service_worker(database_url, _holder_run)
        except BaseException as exc:  # propagated below
            holder_box["error"] = exc

    def _waiter_thread() -> None:
        try:
            _service_worker(database_url, _waiter_run)
        except BaseException as exc:  # propagated below
            waiter_box["error"] = exc

    holder = threading.Thread(
        target=_holder_thread, daemon=True
    )
    holder.start()
    # The holder MUST hold the row lock before the waiter even starts, so
    # the waiter's apply can only make progress after the holder commits.
    if not locked.wait(timeout=60):
        if "error" in holder_box:
            raise holder_box["error"]
        raise AssertionError("holder never locked the row")
    if "error" in holder_box:
        raise holder_box["error"]
    waiter = threading.Thread(target=_waiter_thread, daemon=True)
    waiter.start()
    assert waiter_at_gate.wait(timeout=60), "waiter never reached the row-lock request"
    time.sleep(1.2)
    assert waiter.is_alive(), "waiter did not wait on the held PG row lock"
    proceed.set()
    holder.join(timeout=120)
    waiter.join(timeout=120)
    assert not holder.is_alive() and not waiter.is_alive()
    assert holder_box.get("error") is None, holder_box
    assert "error" not in waiter_box, waiter_box
    assert holder_box["result"].settled_count == 1
    # The waiter genuinely waited, then saw the changed row and refused.
    assert waiter_box["outcome"] == "AccountingSourceChangedError", waiter_box
    assert waiter_box["elapsed"] >= 0.4, waiter_box


# ---------------------------------------------------------------------------
# 1. Read-only candidate views (bounded, honest, fenced = no action surface)
# ---------------------------------------------------------------------------


def test_views_render_bounded_and_fence_is_read_only(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]

    index = client.get("/admin/accounting-operations/")
    assert index.status_code == 200

    expired = client.get(VIEW_EXPIRED)
    assert expired.status_code == 200
    assert "Up to 200" in expired.text
    body = _table_bodies(expired.text)
    # The capped view shows EXACTLY the 200 oldest expired rows.  The 205
    # filler rows (now-150h..now-354h) are all older than every key A/B
    # row, so the view is entirely filler and NO key A/B row is rendered
    # - the honest cap behavior (no completeness claim).
    assert len(re.findall(r"<tr", body)) == 200
    for rid in env216["resv_b"]:
        assert str(rid) not in body
    for rid in env216["resv_a"]:
        assert str(rid) not in body
    assert str(env216["resv_f2"]) not in body
    # The 200 SHOWN rows are the oldest filler rows (index 5..204); the
    # five newest filler rows are beyond the cap as well.
    for rid in env216["resv_fill"][5:15]:
        assert str(rid) in body
    for rid in env216["resv_fill"][:5]:
        assert str(rid) not in body
    # The credential-shaped canary model never renders in this view.
    assert CREDENTIAL_CANARY not in expired.text

    fences = client.get(VIEW_FENCES)
    assert fences.status_code == 200
    assert "Read-only view." in fences.text
    fbody = _table_bodies(fences.text)
    assert str(env216["key_f"]) in fbody
    assert str(env216["key_f3"]) in fbody
    assert str(env216["key_f2"]) not in fences.text  # fence already "none"
    # No operator release/reset/unblock surface exists in the fence view.
    assert '/action="/admin/accounting-operations' not in fences.text
    assert 'name="reservation_id"' not in fences.text
    assert 'name="review_token"' not in fences.text

    holds = client.get(VIEW_HOLDS)
    assert holds.status_code == 200
    hbody = _table_bodies(holds.text)
    assert str(env216["resv_f"]) in hbody
    assert str(env216["resv_f3"]) in hbody
    # Not a valid held shape: absent from the held-rows TABLE (the
    # exact picker's initial options legitimately list recent ids).
    assert str(env216["resv_f2"]) not in hbody
    assert "0.0012M" in hbody  # rF partial tokens (1200)
    assert "unknown" in hbody  # rF3 has NO partial facts (never zero)

    provider = client.get(VIEW_PROVIDER)
    assert provider.status_code == 200
    pbody = _table_bodies(provider.text)
    assert str(env216["ledger_p"]) in pbody
    assert str(env216["resv_p"]) in pbody
    # The credential-shaped requested model is MASKED in the rendered row.
    assert CREDENTIAL_CANARY not in pbody
    assert "***" in pbody
    assert "0.0009M" in pbody  # rP final tokens (900)
    # ...and WITHHELD from the model picker across the FULL response
    # (including the data-initial-options payload): a masked placeholder
    # never becomes a selectable identity, and a direct token search
    # returns no option for it - while ordinary model tokens stay
    # selectable (the guard is not a blanket mask).
    assert CREDENTIAL_CANARY not in provider.text
    pc = client.get("/admin/record-choices", params={"kind": "model"})
    assert pc.status_code == 200
    model_labels = [c["label"] for c in pc.json()["choices"]]
    assert CREDENTIAL_CANARY not in model_labels
    assert "model-hold-216" in model_labels
    pc = client.get(
        "/admin/record-choices", params={"kind": "model", "q": CREDENTIAL_CANARY}
    )
    assert pc.status_code == 200
    assert pc.json()["choices"] == []


# ---------------------------------------------------------------------------
# 2. Expired dry-run: writes nothing; review display law (observed vs applied)
# ---------------------------------------------------------------------------


def test_expired_dry_run_preserves_state_and_review_display(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    before = _preservation_snapshot(db)

    r1 = env216["resv_b"][0]
    page = _preview_expired(client, target_ids=[r1], reason="dry run inspection")
    assert page.status_code == 200
    text = page.text
    assert "What you are reviewing (current observed facts)" in text
    # Separately sortable observed / if-applied columns with raw sort keys.
    for header in (
        "Tokens (observed)",
        "Requests (observed)",
        "Cost (EUR, observed)",
        "Tokens (if applied)",
        "Requests (if applied)",
        "Cost (EUR, if applied)",
    ):
        assert header in text
    assert 'data-sort-value="200"' in text
    assert "0.0002M" in text
    assert 'data-sort-value="0.02"' in text
    assert "Release the reserved cost, tokens and requests" in text
    assert "Audit reason: <strong>dry run inspection</strong>" in text
    assert re.search(r"bound to your signed-in\s+session for 15 minutes", text)
    # The dry-run status is a CURRENT fact shown as observed detail, never a
    # proposed post-apply state.
    assert ">Status:</span> pending" in text
    _review_submit(page)

    after = _preservation_snapshot(db)
    assert after == before, "the preview must not mutate anything"
    env216["settle_r1"] = (
        _review_token_from(page),
        CSRF_RE.search(page.text).group(1),
        r1,
    )


# ---------------------------------------------------------------------------
# 3. Single settlement commits with exact counters, ledger, and audit
# ---------------------------------------------------------------------------


def test_expired_single_settlement_commits(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    token, csrf, rid = env216["settle_r1"]
    resp = _apply_post(client, APPLY_EXPIRED, token, csrf)
    assert resp.status_code == 200
    assert "Committed: 1 row(s) settled" in resp.text

    key_b = _get_key(db, env216["key_b"])
    assert key_b.cost_reserved_eur == Decimal("0.20")
    assert key_b.tokens_reserved_total == 2000
    assert key_b.requests_reserved_total == 10
    row = _get_reservation(db, rid)
    assert row.status == "expired"
    assert row.released_at is not None
    env216["r1_released_at"] = row.released_at

    ledger = _get_ledger_by_reservation(db, rid)
    assert ledger is not None
    assert ledger.accounting_status == "failed"
    assert ledger.actual_cost_eur == Decimal("0")
    assert ledger.error_type == "stale_quota_reservation"

    audits = _audit_rows(db, action="quota_reservation_expired", entity_id=rid)
    assert len(audits) == 1
    assert audits[0].admin_user_id == env216["super_admin_id"]
    assert audits[0].note == "dry run inspection"

    env216["allowed_key_ids"].add(str(env216["key_b"]))
    env216["allowed_reservation_ids"].add(str(rid))


# ---------------------------------------------------------------------------
# 4. ANY changed included row refuses the WHOLE selected batch (no mix)
# ---------------------------------------------------------------------------


def test_expired_changed_row_refuses_whole_batch(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    r2, r3 = env216["resv_b"][1], env216["resv_b"][2]
    page = _preview_expired(client, target_ids=[r2, r3], reason="batch refusal")
    assert page.status_code == 200
    token, csrf = _review_submit(page)

    def _mutate(session) -> Any:
        async def _t() -> None:
            async with session.begin():
                row = (
                    await session.execute(
                        select(QuotaReservation).where(QuotaReservation.id == r3)
                    )
                ).scalar_one()
                row.reserved_tokens += 7

        return _t()

    _db_worker(db, _mutate)

    resp = _apply_post(client, APPLY_EXPIRED, token, csrf)
    assert resp.status_code == 200
    assert "changed after the preview" in resp.text
    assert "WHOLE operation was refused" in resp.text

    # BOTH rows untouched: no settled/already mix, no counters, ledger, audit.
    assert _get_reservation(db, r2).status == "pending"
    assert _get_reservation(db, r3).status == "pending"
    assert _key_counters(db, env216["key_b"]) == (Decimal("0.20"), 2000, 10)
    assert _get_ledger_by_reservation(db, r2) is None
    assert _get_ledger_by_reservation(db, r3) is None
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=r2)
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=r3)
    env216["allowed_reservation_ids"].add(str(r3))  # out-of-band mutation only


# ---------------------------------------------------------------------------
# 5. A newly matching row is NEVER added to a reviewed selection
# ---------------------------------------------------------------------------


def test_expired_newly_matching_row_never_added(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    r4, r5 = env216["resv_b"][3], env216["resv_b"][4]
    page = _preview_expired(client, target_ids=[r4, r5], reason="new match probe")
    assert page.status_code == 200
    token, csrf = _review_submit(page)

    def _seed_new(session) -> Any:
        async def _t() -> uuid.UUID:
            async with session.begin():
                key_b = await session.get(GatewayKey, env216["key_b"])
                assert key_b is not None
                resv = QuotaReservation(
                    gateway_key_id=key_b.id,
                    request_id=f"req-216b-new-{uuid.uuid4().hex[:8]}",
                    endpoint="/v1/chat/completions",
                    requested_model="model-216b-new",
                    provider="prov-216b",
                    reserved_cost_eur=Decimal("0.02"),
                    reserved_tokens=200,
                    reserved_requests=1,
                    status="pending",
                    expires_at=datetime.now(UTC) - timedelta(hours=5),
                )
                session.add(resv)
                await session.flush()
                key_b.cost_reserved_eur += Decimal("0.02")
                key_b.tokens_reserved_total += 200
                key_b.requests_reserved_total += 1
                return resv.id

        return _t()

    new_id = _db_worker(db, _seed_new)

    resp = _apply_post(client, APPLY_EXPIRED, token, csrf)
    assert resp.status_code == 200
    assert "Committed: 2 row(s) settled" in resp.text

    # Exactly the two reviewed rows settled; the new candidate stays pending.
    assert _get_reservation(db, r4).status == "expired"
    assert _get_reservation(db, r5).status == "expired"
    assert _get_reservation(db, new_id).status == "pending"
    assert _key_counters(db, env216["key_b"]) == (Decimal("0.18"), 1800, 9)

    env216["allowed_reservation_ids"].update({str(r4), str(r5)})


# ---------------------------------------------------------------------------
# 6. Repeat of an already-resolved row: safe no-op, no duplicate effect
# ---------------------------------------------------------------------------


def test_expired_repeat_already_resolved_no_duplicate(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_b"][0]  # settled by test 3
    audits_before = len(_audit_rows(db, action="quota_reservation_expired", entity_id=rid))
    counters_before = _key_counters(db, env216["key_b"])

    page = _preview_expired(client, target_ids=[rid], reason="repeat probe")
    assert page.status_code == 200
    assert "Already resolved" in page.text  # human Proposal label (no raw enum)
    token, csrf = _review_submit(page)

    resp = _apply_post(client, APPLY_EXPIRED, token, csrf)
    assert resp.status_code == 200
    assert "every reviewed row was already resolved" in resp.text
    assert "no duplicate effect" in resp.text

    assert _key_counters(db, env216["key_b"]) == counters_before
    assert len(_audit_rows(db, action="quota_reservation_expired", entity_id=rid)) == audits_before
    assert _get_reservation(db, rid).released_at == env216["r1_released_at"]


# ---------------------------------------------------------------------------
# 7. Exact selection bounds: 20 / 21 accepted, 200 bounded, 201 refuses
# ---------------------------------------------------------------------------


def test_expired_selection_bounds_20_21_200_201(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    resv_a = env216["resv_a"]

    # 20 real rows: accepted and sealed.
    page = _preview_expired(client, target_ids=resv_a[:20], reason="bound 20")
    assert page.status_code == 200
    _review_submit(page)

    # 21 real rows: accepted (the global list-filter cap of 20 must NOT apply
    # to the reviewed accounting selection).
    page = _preview_expired(client, target_ids=resv_a[:21], reason="bound 21")
    assert page.status_code == 200
    _review_submit(page)

    # 200 rows (100 real + 100 missing): the ceiling is reached, and the
    # missing rows refuse the whole review seal.
    ids = list(resv_a[:100]) + [uuid.uuid4() for _ in range(100)]
    page = _preview_expired(client, target_ids=ids, reason="bound 200")
    assert page.status_code == 200
    assert 'name="review_token"' not in page.text

    # 201 rows: predictably refused (fixed safe message, never a 500).
    ids201 = list(resv_a[:20]) + [uuid.uuid4() for _ in range(181)]
    page = _preview_expired(client, target_ids=ids201, reason="bound 201")
    assert page.status_code == 400
    assert "at most 200" in page.text


# ---------------------------------------------------------------------------
# 8. Hold intent negatives: explicit mutually-exclusive law, pre-seal
# ---------------------------------------------------------------------------


def test_hold_intent_negatives_refuse_before_seal(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    r3 = env216["resv_f3"]

    # Release without the explicit no-charge confirmation.
    resp = _preview_hold(client, reservation_id=r3, action="release-no-charge", reason="neg 1")
    assert resp.status_code == 400
    assert "no-charge confirmation" in resp.text

    # Release WITH a cost value (conflict).
    resp = _preview_hold(
        client,
        reservation_id=r3,
        action="release-no-charge",
        reason="neg 2",
        confirm_no_charge=True,
        actual_cost_eur="0.10",
    )
    assert resp.status_code == 400
    assert "conflict" in resp.text

    # Release WITH token values (conflict).
    resp = _preview_hold(
        client,
        reservation_id=r3,
        action="release-no-charge",
        reason="neg 3",
        confirm_no_charge=True,
        actual_total_tokens="5",
    )
    assert resp.status_code == 400
    assert "conflict" in resp.text

    # Finalize without an explicit outcome.
    resp = _preview_hold(
        client,
        reservation_id=r3,
        action="finalize-actual",
        reason="neg 4",
        actual_cost_eur="0.10",
        actual_total_tokens="5",
    )
    assert resp.status_code == 400
    assert "One of the reviewed values is invalid" in resp.text

    # Finalize with a posted no-charge confirmation (conflict).
    resp = _preview_hold(
        client,
        reservation_id=r3,
        action="finalize-actual",
        reason="neg 5",
        confirm_no_charge=True,
        actual_cost_eur="0.10",
        actual_total_tokens="5",
        outcome="success",
    )
    assert resp.status_code == 400
    assert "conflict" in resp.text

    # Radio picker AND exact field at once.
    resp = _preview_hold(
        client,
        reservation_id=r3,
        exact_id=r3,
        action="release-no-charge",
        reason="neg 6",
        confirm_no_charge=True,
    )
    assert resp.status_code == 400
    assert "one way only" in resp.text


# ---------------------------------------------------------------------------
# 9. Hold finalize with operator actuals (operator_asserted provenance)
# ---------------------------------------------------------------------------


def test_hold_finalize_actual_commits_operator_asserted(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_f"]
    page = _preview_hold(
        client,
        reservation_id=rid,
        action="finalize-actual",
        reason="finalize actuals",
        actual_cost_eur="0.42",
        actual_total_tokens="2500",
        outcome="success",
    )
    assert page.status_code == 200
    text = page.text
    # Observed (reserved) vs proposed (operator-asserted) in raw machine units.
    assert 'data-sort-value="5000"' in text
    assert 'data-sort-value="2500"' in text
    assert "0.005M" in text
    assert "0.0025M" in text
    assert 'data-sort-value="0.5"' in text
    assert 'data-sort-value="0.42"' in text
    assert ">Fence state:</span> held" in text
    assert ">Accounting status:</span> estimated" in text
    assert ">Provider outcome:</span> success" in text
    assert "sealed: not confirmed" in text
    assert "0.42 EUR" in text
    token, csrf = _review_submit(page)

    resp = _apply_post(client, APPLY_HOLDS, token, csrf)
    assert resp.status_code == 200
    assert "Committed: 1 row(s) settled" in resp.text

    ledger = _get_ledger_by_reservation(db, rid)
    assert ledger.accounting_status == "finalized"
    assert ledger.success is True
    assert ledger.actual_cost_eur == Decimal("0.42")
    assert ledger.total_tokens == 2500
    meta = ledger.response_metadata
    recon = meta["external_tool_accounting_reconciliation"]
    assert recon["cost_source"] == "operator_reconciliation"
    assert recon["confidence"] == "operator_asserted"
    assert recon["confirmed_no_charge"] is False
    assert meta["external_tool_accounting_hold"]["needs_reconciliation"] is False

    assert _get_reservation(db, rid).status == "finalized"
    key_f = _get_key(db, env216["key_f"])
    assert key_f.cost_reserved_eur == Decimal("0")
    assert key_f.tokens_reserved_total == 0
    assert key_f.requests_reserved_total == 0
    assert key_f.cost_used_eur == Decimal("1.52")
    assert key_f.tokens_used_total == 2525
    assert key_f.requests_used_total == 4
    assert key_f.last_used_at is not None
    assert key_f.external_tool_fence_state == "none"

    audits = _audit_rows(db, action="external_tool_accounting_hold_reconciled", entity_id=env216["key_f"])
    assert len(audits) == 1
    assert audits[0].admin_user_id == env216["super_admin_id"]

    env216["allowed_reservation_ids"].add(str(rid))
    env216["allowed_ledger_ids"].add(str(env216["ledger_f"]))
    env216["allowed_key_ids"].add(str(env216["key_f"]))


# ---------------------------------------------------------------------------
# 10. Hold release with explicit no charge (unknown cost never defaults to 0)
# ---------------------------------------------------------------------------


def test_hold_release_no_charge_commits(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_f3"]
    page = _preview_hold(
        client,
        reservation_id=rid,
        action="release-no-charge",
        reason="release no charge",
        confirm_no_charge=True,
    )
    assert page.status_code == 200
    text = page.text
    assert "sealed: explicitly confirmed" in text
    # Proposed release = the reserved amounts; NO actuals asserted.
    assert 'data-sort-value="2500"' in text
    assert 'data-sort-value="0.25"' in text
    assert ">Accounting status:</span> interrupted" in text
    token, csrf = _review_submit(page)

    resp = _apply_post(client, APPLY_HOLDS, token, csrf)
    assert resp.status_code == 200
    assert "Committed: 1 row(s) settled" in resp.text

    ledger = _get_ledger_by_reservation(db, rid)
    assert ledger.accounting_status == "failed"
    assert ledger.success is False
    assert ledger.actual_cost_eur == Decimal("0")
    assert ledger.total_tokens == 0
    recon = ledger.response_metadata["external_tool_accounting_reconciliation"]
    assert recon["confirmed_no_charge"] is True
    assert recon["confidence"] == "operator_asserted"

    assert _get_reservation(db, rid).status == "released"
    key = _get_key(db, env216["key_f3"])
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    # Used counters are UNCHANGED: release with no charge never charges.
    assert key.cost_used_eur == Decimal("0.75")
    assert key.tokens_used_total == 10
    assert key.requests_used_total == 1
    assert key.external_tool_fence_state == "none"

    audits = _audit_rows(db, action="external_tool_accounting_hold_reconciled", entity_id=env216["key_f3"])
    assert len(audits) == 1
    assert audits[0].admin_user_id == env216["super_admin_id"]

    env216["allowed_reservation_ids"].add(str(rid))
    env216["allowed_ledger_ids"].add(str(env216["ledger_f3"]))
    env216["allowed_key_ids"].add(str(env216["key_f3"]))


# ---------------------------------------------------------------------------
# 11. Provider-completed recovery: stored evidence only, no GUI override
# ---------------------------------------------------------------------------


def test_provider_completed_recovery_keeps_stored_evidence(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    lid = env216["ledger_p"]
    page = _preview_provider(client, target_ids=[lid], reason="provider recovery")
    assert page.status_code == 200
    text = page.text
    assert 'data-sort-value="900"' in text
    assert 'data-sort-value="0.28"' in text
    assert ">Accounting status:</span> failed" in text
    assert ">Provider:</span> prov-pc-216" in text
    assert "no cost override" in text
    token, csrf = _review_submit(page)

    resp = _apply_post(client, APPLY_PROVIDER, token, csrf)
    assert resp.status_code == 200
    assert "Committed: 1 row(s) settled" in resp.text

    ledger = _get_ledger_by_id(db, lid)
    assert ledger.accounting_status == "finalized"
    assert ledger.success is True
    # The stored authoritative cost is kept EXACTLY (no GUI override).
    assert ledger.actual_cost_eur == Decimal("0.28")
    assert ledger.response_metadata["needs_reconciliation"] is False
    assert ledger.response_metadata["recovery_state"] == "provider_completed_reconciled"

    assert _get_reservation(db, env216["resv_p"]).status == "finalized"
    key_p = _get_key(db, env216["key_p"])
    assert key_p.cost_reserved_eur == Decimal("0")
    assert key_p.tokens_reserved_total == 0
    assert key_p.requests_reserved_total == 0
    assert key_p.cost_used_eur == Decimal("2.28")
    assert key_p.tokens_used_total == 920
    assert key_p.requests_used_total == 5
    assert key_p.last_used_at is not None

    audits = _audit_rows(db, action="provider_completed_reconciliation", entity_id=lid)
    assert len(audits) == 1
    assert audits[0].admin_user_id == env216["super_admin_id"]

    env216["allowed_reservation_ids"].add(str(env216["resv_p"]))
    env216["allowed_ledger_ids"].add(str(lid))
    env216["allowed_key_ids"].add(str(env216["key_p"]))


# ---------------------------------------------------------------------------
# 12. Fenced reservation: ordinary release refused; NO generic unblock route
# ---------------------------------------------------------------------------


def test_fenced_ordinary_release_refused_no_generic_unblock(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_f2"]

    page = _preview_expired(client, target_ids=[rid], reason="fenced refusal")
    assert page.status_code == 200
    assert "external_tool_fenced" in page.text
    assert "One or more selected rows cannot be reviewed right now" in page.text
    assert 'name="review_token"' not in page.text

    # There is no generic fence release/reset/unblock endpoint at all.
    resp = client.post(
        f"{VIEW_FENCES}/apply",
        data={"csrf_token": "x", "review_token": "y", "confirm_apply": "1"},
    )
    assert resp.status_code == 404

    row = _get_reservation(db, rid)
    assert row.status == "pending"
    assert _key_counters(db, env216["key_f2"]) == (Decimal("0.10"), 1000, 1)
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=rid)


# ---------------------------------------------------------------------------
# 13. Execution privilege: existing superadmin role (server-side)
# ---------------------------------------------------------------------------


def test_apply_requires_superadmin_role(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_a"][89]  # rA-90: untouched pending row

    # Switch the SAME client to the plain (non-super) admin.
    client.cookies.clear()
    _login(client, email=env216["plain_admin_email"])

    # Inspection and even sealing are available to all signed-in admins...
    view = client.get(VIEW_EXPIRED)
    assert view.status_code == 200
    page = _preview_expired(client, target_ids=[rid], reason="privilege probe")
    assert page.status_code == 200
    token, csrf = _review_submit(page)

    # ...but applying requires the existing superadmin role.
    resp = _apply_post(client, APPLY_EXPIRED, token, csrf)
    assert resp.status_code == 403
    assert "superadmin" in resp.text

    assert _get_reservation(db, rid).status == "pending"
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=rid)

    # Back to the superadmin for the remaining tests.
    client.cookies.clear()
    _login(client, email=env216["super_admin_email"])


# ---------------------------------------------------------------------------
# 14. Concurrent same-row: exactly one settlement, one safe refusal
# ---------------------------------------------------------------------------


def test_concurrent_same_row_settles_exactly_once(env216: dict[str, Any]) -> None:
    from concurrent.futures import ThreadPoolExecutor

    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_a"][49]  # rA-50
    # Two independent seals for the SAME row (two reviewers, same facts).
    t1, c1 = _review_submit(_preview_expired(client, target_ids=[rid], reason="concurrent 1"))
    t2, c2 = _review_submit(_preview_expired(client, target_ids=[rid], reason="concurrent 2"))

    def _post(token: str) -> Any:
        # Each _preview_expired GET above refreshed the session CSRF
        # token, so c1 is STALE: both workers submit the CURRENT token
        # (c2) with their DISTINCT session-bound seals, and no
        # intervening GET may occur.  An auth/CSRF denial must not be
        # mistaken for the concurrency proof: both responses are
        # asserted HTTP 200.
        return client.post(
            APPLY_EXPIRED,
            data={"csrf_token": c2, "review_token": token, "confirm_apply": "1"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(_post, (t1, t2)))
    pages = [r.text for r in responses]
    assert all(r.status_code == 200 for r in responses)

    settled = sum(1 for p in pages if "1 row(s) settled" in p)
    refused = sum(1 for p in pages if "changed after the preview" in p)
    assert settled == 1
    assert refused == 1

    assert _get_reservation(db, rid).status == "expired"
    assert len(_audit_rows(db, action="quota_reservation_expired", entity_id=rid)) == 1
    # Exactly ONE decrement of the row's reserved amounts.
    assert _key_counters(db, env216["key_a"]) == (Decimal("1.00"), 10_000, 100)

    env216["allowed_reservation_ids"].add(str(rid))
    env216["allowed_key_ids"].add(str(env216["key_a"]))

    # Deterministic REAL row-lock contention proof on the next row: the
    # waiting apply must block on the held FOR UPDATE, then refuse the
    # changed row (never a double settlement).
    rid51 = env216["resv_a"][50]
    _same_row_lock_contention_probe(db, rid51, env216["super_admin_id"])
    assert _get_reservation(db, rid51).status == "expired"
    assert len(_audit_rows(db, action="quota_reservation_expired", entity_id=rid51)) == 1
    assert _key_counters(db, env216["key_a"]) == (Decimal("0.99"), 9_900, 99)
    env216["allowed_reservation_ids"].add(str(rid51))


# ---------------------------------------------------------------------------
# 15a. Waited lock: a change landing WHILE the apply waits is detected
# ---------------------------------------------------------------------------


def test_waited_lock_detects_changed_row_after_preview(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_a"][59]  # rA-60
    page = _preview_expired(client, target_ids=[rid], reason="waited freshness")
    assert page.status_code == 200
    token, csrf = _review_submit(page)

    locked = threading.Event()
    proceed = threading.Event()

    def _mutate(session) -> Any:
        async def _t() -> None:
            async with session.begin():
                row = (
                    await session.execute(
                        select(QuotaReservation)
                        .where(QuotaReservation.id == rid)
                        .with_for_update()
                    )
                ).scalars().first()
                assert row is not None, "waited-lock row vanished"
                locked.set()
                assert proceed.wait(timeout=90), "mutator proceed timed out"
                row.reserved_tokens += 5

        return _t()

    holder_box: dict[str, Any] = {}

    def _holder() -> None:
        try:
            _db_worker(db, _mutate)
        except BaseException as exc:  # propagated below
            holder_box["error"] = exc

    holder = threading.Thread(target=_holder, daemon=True)
    holder.start()
    assert locked.wait(timeout=60), f"mutator never locked the row: {holder_box}"
    assert holder_box.get("error") is None

    apply_box: dict[str, Any] = {}

    def _http() -> None:
        apply_box["resp"] = client.post(
            APPLY_EXPIRED,
            data={"csrf_token": csrf, "review_token": token, "confirm_apply": "1"},
        )

    # The holder ALREADY holds the row lock: only now start the HTTP
    # applier, so "still alive" below proves a real PG lock wait.
    applier = threading.Thread(target=_http, daemon=True)
    applier.start()
    time.sleep(1.2)
    assert applier.is_alive(), "apply did not wait on the held row lock"
    proceed.set()
    holder.join(timeout=120)
    applier.join(timeout=120)
    assert not holder.is_alive() and not applier.is_alive()
    assert holder_box.get("error") is None, holder_box

    resp = apply_box["resp"]
    assert resp.status_code == 200
    assert "changed after the preview" in resp.text

    # The row keeps ONLY the out-of-band change; nothing was settled.
    row = _get_reservation(db, rid)
    assert row.status == "pending"
    assert row.reserved_tokens == 105
    assert _key_counters(db, env216["key_a"]) == (Decimal("0.99"), 9_900, 99)
    assert _get_ledger_by_reservation(db, rid) is None
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=rid)
    env216["allowed_reservation_ids"].add(str(rid))


# ---------------------------------------------------------------------------
# 15b. Reversed cross-key caller selections: ascending key-UUID lock order,
#     no deadlock, both batches commit
# ---------------------------------------------------------------------------


def test_reversed_cross_key_selection_no_deadlock(env216: dict[str, Any]) -> None:
    db = env216["database_url"]
    resv_a, resv_b = env216["resv_a"], env216["resv_b"]
    r_a1, r_a2 = resv_a[69], resv_a[70]  # rA-70, rA-71 (key A)
    r_b1, r_b2 = resv_b[9], resv_b[10]  # rB-10, rB-11 (key B)
    barrier = threading.Barrier(2)
    boxes: list[dict[str, Any]] = [{}, {}]

    def _worker(i: int, targets: list[tuple[uuid.UUID, str]]) -> None:
        async def _run(session, service) -> Any:
            barrier.wait(timeout=30)
            async with session.begin():
                return await service.apply_expired(
                    targets=[AccountingReviewTarget(t, fp) for t, fp in targets],
                    actor_admin_id=env216["super_admin_id"],
                    reason="cross-key probe",
                )

        try:
            # _service_worker injects the reviewed-ops service itself.
            boxes[i]["result"] = _service_worker(db, _run)
        except BaseException as exc:  # propagated below
            boxes[i]["error"] = exc

    # Fingerprint each row's CURRENT facts before the probe starts.
    targets_1 = [
        (r_a1, fingerprint_expired_reservation(_get_reservation(db, r_a1))),
        (r_b1, fingerprint_expired_reservation(_get_reservation(db, r_b1))),
    ]
    targets_2 = [
        (r_b2, fingerprint_expired_reservation(_get_reservation(db, r_b2))),
        (r_a2, fingerprint_expired_reservation(_get_reservation(db, r_a2))),
    ]
    t1 = threading.Thread(target=lambda: _worker(0, targets_1), daemon=True)
    t2 = threading.Thread(target=lambda: _worker(1, targets_2), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=120)
    t2.join(timeout=120)
    assert not t1.is_alive() and not t2.is_alive(), "cross-key lock order deadlocked"
    assert boxes[0].get("error") is None and boxes[1].get("error") is None, boxes

    # OPPOSITE caller orders over the SAME two keys: both commit.
    assert boxes[0]["result"].settled_count == 2
    assert boxes[1]["result"].settled_count == 2
    for rid_ in (r_a1, r_a2, r_b1, r_b2):
        assert _get_reservation(db, rid_).status == "expired"
    assert _key_counters(db, env216["key_a"]) == (Decimal("0.97"), 9_700, 97)
    assert _key_counters(db, env216["key_b"]) == (Decimal("0.14"), 1_400, 7)

    env216["allowed_reservation_ids"].update({str(x) for x in (r_a1, r_a2, r_b1, r_b2)})
    env216["allowed_key_ids"].update({str(env216["key_a"]), str(env216["key_b"])})


def _build_probe_service(session) -> "AdminAccountingOperationsService":
    from slaif_gateway.api.admin_accounting_operations import _build_service

    return _build_service(session)


# ---------------------------------------------------------------------------
# 16. Commit-ack loss at the REAL seam: durable, unconfirmed, never rollback
# ---------------------------------------------------------------------------


def test_commit_ack_loss_is_durable_not_rollback(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    app = env216["app"]
    rid = env216["resv_a"][79]  # rA-80
    page = _preview_expired(client, target_ids=[rid], reason="ack loss probe")
    assert page.status_code == 200
    token, csrf = _review_submit(page)

    original = app.state.db_sessionmaker
    seam = _216CommitFaultSessionmaker(original, test="ack-loss")
    try:
        app.state.db_sessionmaker = seam
        resp = client.post(
            APPLY_EXPIRED,
            data={"csrf_token": csrf, "review_token": token, "confirm_apply": "1"},
        )
    finally:
        app.state.db_sessionmaker = original
    assert seam.hit and seam.ack_loss_committed
    assert resp.status_code == 200
    assert "commit acknowledgement" in resp.text
    assert "NOT a rollback" in resp.text
    assert "fault seam" not in resp.text

    # The write is DURABLE despite the lost acknowledgement.
    assert _get_reservation(db, rid).status == "expired"
    assert _key_counters(db, env216["key_a"]) == (Decimal("0.96"), 9_600, 96)
    assert _get_ledger_by_reservation(db, rid) is not None
    assert len(_audit_rows(db, action="quota_reservation_expired", entity_id=rid)) == 1

    env216["allowed_reservation_ids"].add(str(rid))
    env216["allowed_key_ids"].add(str(env216["key_a"]))


# ---------------------------------------------------------------------------
# 17. Late audit fault: the WHOLE selected transaction rolls back safely
# ---------------------------------------------------------------------------


class _LateAuditFault(ReconciliationError):
    """Test-only SAFE accounting error raised at the audit step (seam)."""

    error_code = "reconciliation_invariant_error"
    message = "late audit fault seam (fixture)"


def test_late_audit_fault_rolls_back_whole_batch(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    r1, r2 = env216["resv_a"][80], env216["resv_a"][81]  # rA-81, rA-82
    page = _preview_expired(client, target_ids=[r1, r2], reason="late audit probe")
    assert page.status_code == 200
    token, csrf = _review_submit(page)
    counters_before = _key_counters(db, env216["key_a"])

    original_add = AuditRepository.add_audit_log

    async def _failing_add(self, **kwargs) -> Any:
        if kwargs.get("action") in _MUTATION_AUDIT_ACTIONS:
            raise _LateAuditFault()
        return await original_add(self, **kwargs)

    AuditRepository.add_audit_log = _failing_add
    try:
        resp = client.post(
            APPLY_EXPIRED,
            data={"csrf_token": csrf, "review_token": token, "confirm_apply": "1"},
        )
    finally:
        AuditRepository.add_audit_log = original_add

    assert resp.status_code == 200
    assert "invariants" in resp.text
    # WHOLE batch rolled back: both rows pending, counters and ledgers intact.
    assert _get_reservation(db, r1).status == "pending"
    assert _get_reservation(db, r2).status == "pending"
    assert _key_counters(db, env216["key_a"]) == counters_before
    assert _get_ledger_by_reservation(db, r1) is None
    assert _get_ledger_by_reservation(db, r2) is None
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=r1)
    assert not _audit_rows(db, action="quota_reservation_expired", entity_id=r2)


# ---------------------------------------------------------------------------
# 18. Beyond-cap exact selection via the known-record picker (+ canary)
# ---------------------------------------------------------------------------


def test_beyond_cap_exact_selection_picker_and_canary(env216: dict[str, Any]) -> None:
    client: TestClient = env216["client"]
    db = env216["database_url"]
    rid = env216["resv_a_canary"]
    resv_fill = env216["resv_fill"]

    # The canary row is GENUINELY beyond the capped candidate view: the
    # initial page renders only the 200 oldest (filler) rows, and the
    # canary (now-101h) is not among them - so no checkbox path exists.
    page = client.get(VIEW_EXPIRED)
    assert page.status_code == 200
    assert str(rid) not in _table_bodies(page.text)

    # ...and it is beyond the picker's latest-100 page too...
    page = client.get("/admin/record-choices", params={"kind": "quota_reservation"})
    assert page.status_code == 200
    assert str(rid) not in [c["id"] for c in page.json()["choices"]]
    # ...but the bounded UUID search finds it (real user-reachable path).
    page = client.get(
        "/admin/record-choices",
        params={"kind": "quota_reservation", "q": str(rid)},
    )
    assert page.status_code == 200
    assert str(rid) in [c["id"] for c in page.json()["choices"]]

    # 200 REAL eligible ids seal successfully - the valid-200 acceptance
    # (distinct from the 200-with-missing-ids refusal in the bounds test).
    page = _preview_expired(client, target_ids=resv_fill[:200], reason="valid 200")
    assert page.status_code == 200
    _review_submit(page)

    # Preview through the exact known-record field (no checkbox path exists
    # for this row: it is outside the capped candidate view).
    page = _preview_expired(client, exact_ids=[rid], reason="beyond cap selection")
    assert page.status_code == 200
    assert CREDENTIAL_CANARY not in page.text
    token, csrf = _review_submit(page)

    resp = _apply_post(client, APPLY_EXPIRED, token, csrf)
    assert resp.status_code == 200
    assert "Committed: 1 row(s) settled" in resp.text
    assert CREDENTIAL_CANARY not in resp.text

    assert _get_reservation(db, rid).status == "expired"
    assert _key_counters(db, env216["key_a"]) == (Decimal("0.95"), 9_500, 95)
    ledger = _get_ledger_by_reservation(db, rid)
    assert ledger is not None
    # The machine row keeps the RAW fact (Core/freshness contract); the
    # AUDIT trail must never carry the credential-shaped value.
    assert ledger.requested_model == CREDENTIAL_CANARY
    for audit in _audit_rows(db, action="quota_reservation_expired", entity_id=rid):
        blob = json.dumps(
            [audit.old_values, audit.new_values, audit.note, audit.request_id], default=str
        )
        assert CREDENTIAL_CANARY not in blob

    env216["allowed_reservation_ids"].add(str(rid))
    env216["allowed_key_ids"].add(str(env216["key_a"]))


# ---------------------------------------------------------------------------
# 19. Preservation: only reviewed targets + linked keys/ledgers changed
# ---------------------------------------------------------------------------


def test_preservation_digests_allow_only_reviewed_changes(env216: dict[str, Any]) -> None:
    db = env216["database_url"]
    before = env216["preservation_before"]
    after = _preservation_snapshot(db)

    for table in before:
        assert set(before[table]) <= set(after[table]), f"{table}: rows disappeared"

    allowed = {
        "quota_reservations": env216["allowed_reservation_ids"],
        "usage_ledger": env216["allowed_ledger_ids"],
        "gateway_keys": env216["allowed_key_ids"],
        "owners": set(),
        "admin_users": set(),
    }
    for table, allowed_ids in allowed.items():
        for row_id, digest in before[table].items():
            if row_id in allowed_ids:
                continue
            assert after[table][row_id] == digest, (
                f"{table} row {row_id} changed outside its reviewed allow set"
            )

    # The audit log is append-only: every pre-existing row is byte-identical.
    for row_id, digest in before["audit_log"].items():
        assert after["audit_log"][row_id] == digest, f"audit row {row_id} was modified"

    # The unrelated nonzero sentinel survives every operation byte-identical.
    assert after["gateway_keys"][str(env216["key_s"])] == before["gateway_keys"][str(env216["key_s"])]
    assert (
        after["quota_reservations"][str(env216["resv_s"])]
        == before["quota_reservations"][str(env216["resv_s"])]
    )
    assert after["usage_ledger"][str(env216["ledger_s"])] == before["usage_ledger"][str(env216["ledger_s"])]

    # No credential-shaped canary anywhere in the whole audit trail.
    def _scan(session) -> Any:
        async def _t() -> int:
            rows = list((await session.execute(select(AuditLog))).scalars().all())
            bad = 0
            for row in rows:
                blob = json.dumps(
                    [row.old_values, row.new_values, row.note, row.request_id], default=str
                )
                if CREDENTIAL_CANARY in blob:
                    bad += 1
            return bad

        return _t()

    assert _db_worker(db, _scan) == 0

    # Every settled expired row produced exactly one failure ledger.
    settled_expired = [
        env216["resv_b"][0],
        env216["resv_b"][3],
        env216["resv_b"][4],
        env216["resv_a"][49],
        env216["resv_a"][50],
        env216["resv_a"][69],
        env216["resv_a"][70],
        env216["resv_b"][9],
        env216["resv_b"][10],
        env216["resv_a"][79],
        env216["resv_a_canary"],
    ]
    for rid_ in settled_expired:
        assert _get_ledger_by_reservation(db, rid_) is not None
