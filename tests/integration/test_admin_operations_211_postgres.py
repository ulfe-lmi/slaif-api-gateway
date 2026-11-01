"""211-a GUI operations (diagnostics): owned PostgreSQL tests.

Real-app, real-PostgreSQL qualification for the 211-a operations GUI
consumer.  This module reuses the qualified ``owned_pg_url`` fixture
directly, which ALWAYS creates one NEW owned, labeled, loopback-bound,
tmpfs-backed PostgreSQL 16 container and migrates it - so this module
is the ONLY writer to the request_diagnostics table in its run, which
is exactly what makes the physically-global expired cleanup safely
scope-provable here.  No coexistence claim with other objective
modules is made, and no ambient/shared TEST_DATABASE_URL is reused.

One explicit ordered scenario (file order is significant: the cleanup
tests consume the seeded expired rows):

- retained pre-admission (HTTP 401) and HTTP-200 stream-failure
  records rendered correctly through authenticated HTTP;
- collision (same client ID on two gateway rows) ambiguity plus
  namespace disambiguation and the per-candidate gateway resolve;
- expiry (an expired row is NOT a retained match) and
  recording-disabled reads (status Disabled, retained lookups still
  served);
- picker choices on >100 retained IDs: the 100 cap, cross-namespace
  de-duplication (an ID retained in BOTH namespaces appears exactly
  once), retention exclusion of expired IDs, and hydration of a
  selected OLDER ID that is outside the newest-100 batch;
- native picker auth/CSRF denials (no session -> 303; valid session +
  wrong CSRF -> fixed 400 JSON) with zero DB mutation;
- expired cleanup bounded at 1000 with the retained rows preserved and
  ONE real actor/reason/count audit;
- atomic rollback on an injected failure AFTER the real audit flush
  (the whole transaction - delete AND audit - rolls back; the
  unconfirmed outcome is NOT rendered as a success);
- a zero-delete cleanup audited once with the actual count 0.

Synthetic producer insertion (labeled): every record is projected by
the SHARED producer projection ``build_diagnostic_record`` and stored
through the shared repository ``insert_row`` - NO real provider/Codex
request, respx mock, gateway key, or ledger row is involved.  The 201
producer conformance is NOT re-proved here.

All oracles are scoped to THIS run's exact seeded IDs (the run-unique
``211-`` gateway-ID prefix family); nothing outside that seed is read
or asserted.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlencode
import re
import uuid
import json
from pathlib import Path
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, RequestDiagnostic
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.request_diagnostics import (
    RequestDiagnosticsRepository,
)
from slaif_gateway.main import create_app
from slaif_gateway.schemas.request_diagnostics import DIAGNOSTIC_LOOKUP_BOUND
from slaif_gateway.services.request_diagnostics import build_diagnostic_record
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_lazy_throttling_postgres_redis import (
    _STATE as _PG_STATE,
    owned_pg_url,  # noqa: F401  (module-scoped owned-PG fixture reuse)
)

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
CHOICES_PATH = "/admin/operations/diagnostics/choices"
CHOICES_KIND = "diagnostic_request_id"

ADMIN_PASSWORD = "correct horse battery staple"
CLEANUP_REASON = "211 expired diagnostics cleanup"
ZERO_REASON = "211 zero-delete cleanup"

# Retention for THIS run: 1 hour, so "expired" rows are 2 hours old and
# retained rows are within the window.  The write timeout is raised to
# the maximum allowed 1000ms so cold first-connection statement
# preparation stays inside the write budget (production default 100ms).
RETENTION_SECONDS = 3600
EXPIRED_AGE = timedelta(seconds=2 * RETENTION_SECONDS)
# The hydrated "older" choice: inside retention but the OLDEST written
# row, so the newest-100 batch cannot contain it.
OLD_CHOICE_AGE = timedelta(seconds=RETENTION_SECONDS - 100)

N_CHOICE_RECENT = 119  # -> with the 5 retained rows the cap is binding
N_CHOICE_COLLIDING = 60  # rows whose client ID == gateway ID
N_EXPIRED_SEEDED = 1001


def _settings(database_url: str, *, enabled: bool = True) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET=generate_secret_key(),
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
        REQUEST_DIAGNOSTICS_ENABLED=enabled,
        REQUEST_DIAGNOSTICS_RETENTION_SECONDS=RETENTION_SECONDS,
        REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=1000,
    )


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def asyncio_run(coro):
    return asyncio.run(coro)


def _record_facts(gateway_id: str, *, occurred_at: datetime, **extra: Any) -> dict:
    base: dict[str, Any] = dict(
        gateway_request_id=gateway_id,
        method="GET",
        endpoint_template="/v1/chat/completions",
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        http_status=401,
        stream_outcome="http_rejection",
        source="preauth",
        reason_code="local_rejection",
        error_code="authentication_failed",
    )
    base.update(extra)
    return base


def _build(settings: Settings, gateway_id: str, *, occurred_at: datetime,
           **extra: Any):
    """One synthetic record through the SHARED producer projection."""
    return build_diagnostic_record(
        _record_facts(gateway_id, occurred_at=occurred_at, **extra),
        settings=settings,
    )


async def _seed(database_url: str) -> dict[str, Any]:
    """Seed admin + the exact scenario rows in ONE transaction."""
    settings = _settings(database_url)
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui211-{suffix}@example.org",
                    display_name="211 Ops GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                repository = RequestDiagnosticsRepository(session)
                records = [
                    _build(
                        settings, f"211-preauth-{suffix}", occurred_at=now
                    ),
                    _build(
                        settings,
                        f"211-streamfail-{suffix}",
                        occurred_at=now,
                        method="POST",
                        http_status=200,
                        stream_outcome="stream_failure",
                        source="classifier",
                        reason_code="http_error",
                        error_code="responses_stream_provider_failure",
                        positions={"line": 3, "namespace_index": 2},
                        counts={"count": 5, "max_output_tokens": 1_500_000},
                        limits={
                            "max_input_tokens": 900_000,
                            "absolute_max_output_tokens": 2_000_000,
                        },
                        estimated_input_tokens=12,
                        output_allowance_tokens=1_500_000,
                        context_window_tokens=1_050_000,
                    ),
                    _build(
                        settings,
                        f"211-dupa-{suffix}",
                        occurred_at=now,
                        client_request_id=f"211-dupclient-{suffix}",
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    ),
                    _build(
                        settings,
                        f"211-dupb-{suffix}",
                        occurred_at=now,
                        client_request_id=f"211-dupclient-{suffix}",
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    ),
                    _build(
                        settings,
                        f"211-unrelated-{suffix}",
                        occurred_at=now,
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    ),
                ]
                # Picker-choice scenario rows: all retained.  The first
                # N_CHOICE_COLLIDING rows keep client ID == gateway ID
                # (cross-namespace collision); the rest use distinct
                # client IDs.  recorded_at decreases with i, so row 0 is
                # the newest choice.
                for i in range(N_CHOICE_RECENT):
                    gid = f"211-ch-{suffix}-{i:03d}"
                    records.append(
                        _build(
                            settings,
                            gid,
                            occurred_at=now,
                            recorded_at=now - timedelta(seconds=i),
                            client_request_id=(
                                gid if i < N_CHOICE_COLLIDING
                                else f"211-chc-{suffix}-{i:03d}"
                            ),
                            http_status=429,
                            reason_code="local_rejection",
                            error_code="rate_limited",
                        )
                    )
                # The OLDER retained choice (oldest write time in the
                # table; inside retention, outside the newest-100 batch).
                records.append(
                    _build(
                        settings,
                        f"211-chold-{suffix}",
                        occurred_at=now - OLD_CHOICE_AGE,
                        recorded_at=now - OLD_CHOICE_AGE,
                        client_request_id=f"211-choldc-{suffix}",
                        http_status=429,
                        reason_code="local_rejection",
                        error_code="rate_limited",
                    )
                )
                for i in range(N_EXPIRED_SEEDED):
                    records.append(
                        _build(
                            settings,
                            f"211-exp-{suffix}-{i:04d}",
                            occurred_at=now - EXPIRED_AGE,
                        )
                    )
                # Synthetic producer insertion through the shared
                # repository (no real request).  Direct insert_row: the
                # capacity-lock / prune write path is 201 producer
                # conformance, not this GUI consumer qualification.
                for record in records:
                    await repository.insert_row(record)
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "preauth": f"211-preauth-{suffix}",
                    "streamfail": f"211-streamfail-{suffix}",
                    "dupa": f"211-dupa-{suffix}",
                    "dupb": f"211-dupb-{suffix}",
                    "dupclient": f"211-dupclient-{suffix}",
                    "unrelated": f"211-unrelated-{suffix}",
                    "expired_first": f"211-exp-{suffix}-0000",
                    "choice_newest": f"211-ch-{suffix}-000",
                    "choice_older": f"211-chold-{suffix}",
                    "retained_ids": (
                        f"211-preauth-{suffix}",
                        f"211-streamfail-{suffix}",
                        f"211-dupa-{suffix}",
                        f"211-dupb-{suffix}",
                        f"211-unrelated-{suffix}",
                    ),
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, Any]] = {}


def _seed_sync(database_url: str) -> dict[str, Any]:
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio_run(_seed(database_url))
    return _SEED_CACHE[database_url]


# ---------------------------------------------------------------------------
# DB oracles (scoped to THIS run's exact seeded IDs only)
# ---------------------------------------------------------------------------


async def _scoped_counts(
    database_url: str, suffix: str, retained_ids: tuple[str, ...]
) -> dict[str, int]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            retained = (
                await session.execute(
                    select(func.count(RequestDiagnostic.id)).where(
                        RequestDiagnostic.gateway_request_id.in_(retained_ids)
                    )
                )
            ).scalar_one()
            expired = (
                await session.execute(
                    select(func.count(RequestDiagnostic.id)).where(
                        RequestDiagnostic.gateway_request_id.like(
                            f"211-exp-{suffix}-%"
                        )
                        | RequestDiagnostic.gateway_request_id.like(
                            f"211-late-{suffix}-%"
                        )
                    )
                )
            ).scalar_one()
            choices = (
                await session.execute(
                    select(func.count(RequestDiagnostic.id)).where(
                        RequestDiagnostic.gateway_request_id.like(
                            f"211-ch%{suffix}%"
                        )
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    return {
        "retained": int(retained),
        "expired": int(expired),
        "choices": int(choices),
    }


def _counts(data: dict[str, Any]) -> dict[str, int]:
    return asyncio_run(
        _scoped_counts(data["database_url"], data["suffix"], data["retained_ids"])
    )


async def _cleanup_audits(database_url: str, admin_id: str) -> list[dict[str, Any]]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLog)
                        .where(
                            AuditLog.action == "diagnostics_expired_cleanup",
                            AuditLog.admin_user_id == uuid.UUID(admin_id),
                        )
                        .order_by(AuditLog.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "new": r.new_values,
                "note": r.note,
            }
            for r in rows
        ]
    finally:
        await engine.dispose()


def _audits(data: dict[str, Any]) -> list[dict[str, Any]]:
    return asyncio_run(_cleanup_audits(data["database_url"], data["admin_id"]))


async def _insert_expired(database_url: str, suffix: str, count: int) -> None:
    settings = _settings(database_url)
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                repository = RequestDiagnosticsRepository(session)
                for i in range(count):
                    await repository.insert_row(
                        _build(
                            settings,
                            f"211-late-{suffix}-{i:04d}",
                            occurred_at=now - EXPIRED_AGE,
                        )
                    )
    finally:
        await engine.dispose()


async def _delete_all_expired(database_url: str, suffix: str) -> None:
    """Fixture helper: physically drop THIS run's remaining expired rows."""
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    delete(RequestDiagnostic).where(
                        RequestDiagnostic.gateway_request_id.like(
                            f"211-exp-{suffix}-%"
                        )
                        | RequestDiagnostic.gateway_request_id.like(
                            f"211-late-{suffix}-%"
                        )
                    )
                )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Module fixture: real app + real login on the owned PG
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def route_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:  # noqa: F811 (fixture dependency on the imported fixture name)
    data = _seed_sync(owned_pg_url)
    app = create_app(_settings(owned_pg_url))
    with TestClient(app) as client:
        _login(client, str(data["admin_email"]))
        data["client"] = client
        data["database_url"] = owned_pg_url
        # Lifecycle proof sidecar: the exact created container ID and
        # owner label (the owned_pg_url fixture removes the exact ID in
        # its teardown; the managed terminal verifies none remain).
        sidecar = Path("/tmp/slaif211/pg-211a-lifecycle.json")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            json.dumps(
                {
                    "container": _PG_STATE.get("pg_container", ""),
                    "owner": _PG_STATE.get("pg_owner", ""),
                }
            ),
            encoding="utf-8",
        )
        yield data


def _login(client: TestClient, admin_email: str) -> None:
    login_page = client.get("/admin/login")
    csrf = CSRF_RE.search(login_page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"email": admin_email, "password": ADMIN_PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _csrf(client: TestClient, page: str) -> str:
    html = client.get(page)
    assert html.status_code == 200, html.text[:400]
    return CSRF_RE.search(html.text).group(1)


def _lookup(data: dict[str, Any], lookup_id: str, namespace: str = "any") -> str:
    page = "/admin/operations/diagnostics"
    csrf = _csrf(data["client"], page)
    response = data["client"].post(
        f"{page}/lookup",
        data={
            "csrf_token": csrf,
            "lookup_id": lookup_id,
            "lookup_namespace": namespace,
        },
    )
    assert response.status_code == 200
    return response.text


def _choices(
    data: dict[str, Any],
    *,
    csrf: str | None = None,
    namespace: str = "any",
    query: str | None = None,
    selected: tuple[str, ...] = (),
    session_client: TestClient | None = None,
):
    """POST the kind-specific picker lookup; returns the response.

    The body is built with an explicit urlencoded payload (repeated
    ``selected`` values preserved) so the encoding does not depend on
    the HTTP client's form handling.
    """
    client = session_client or data["client"]
    if csrf is None:
        csrf = _csrf(client, "/admin/operations/diagnostics")
    fields: list[tuple[str, str]] = [
        ("csrf_token", csrf),
        ("kind", CHOICES_KIND),
        ("namespace", namespace),
    ]
    if query is not None:
        fields.append(("q", query))
    for value in selected:
        fields.append(("selected", value))
    return client.post(
        CHOICES_PATH,
        content=urlencode(fields),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


def _cleanup(data: dict[str, Any], reason: str) -> str:
    page = "/admin/operations/diagnostics"
    csrf = _csrf(data["client"], page)
    response = data["client"].post(
        f"{page}/cleanup",
        data={"csrf_token": csrf, "reason": reason, "confirm": "1"},
    )
    assert response.status_code == 200
    return response.text


# ---------------------------------------------------------------------------
# Cases (file order is significant: cleanup tests consume expired rows)
# ---------------------------------------------------------------------------


def test_page_status_and_found_rendering(route_env: dict[str, Any]) -> None:
    data = route_env
    before = _counts(data)
    html = data["client"].get("/admin/operations/diagnostics").text
    assert "Enabled" in html
    assert "3,600 seconds" in html

    # retained pre-admission 401 renders with its safe facts
    html = _lookup(data, data["preauth"])
    # found-result-only facts (the prefilled lookup field also carries
    # the ID, so the ID alone is not a found oracle): the rendered
    # reason/error line plus NO authenticated-key attribution
    assert "local_rejection / authentication_failed" in html
    assert "<dt>Gateway key / route</dt><dd>— / —</dd>" in html
    assert data["preauth"] in html
    assert "stream FAILED" not in html

    # HTTP-200 stream failure is VISIBLY a failure, with readable
    # labelled numeric facts (no dict reprs, visible M tokens)
    html = _lookup(data, data["streamfail"])
    assert "stream FAILED" in html
    assert "this is a failure, not a success" in html
    assert "line: 3 · namespace_index: 2" in html
    assert "max_output_tokens: 1.5M tokens (1,500,000)" in html
    assert "max_input_tokens: 0.9M tokens (900,000)" in html
    assert "absolute_max_output_tokens: 2M tokens (2,000,000)" in html
    assert 'title="1,050,000 tokens"' in html

    # reads are non-mutating: exact seed intact, no cleanup audits
    assert _counts(data) == before
    assert _audits(data) == []


def test_ambiguity_and_namespace_disambiguation(route_env: dict[str, Any]) -> None:
    data = route_env
    before = _counts(data)
    # same client ID on two gateway rows -> ambiguous across namespaces
    html = _lookup(data, data["dupclient"], "any")
    assert "2 retained row(s) match this ID" in html
    assert data["dupa"] in html and data["dupb"] in html
    assert 'name="lookup_id" value="%s"' % data["dupa"] in html
    # the GATEWAY namespace does not match the client ID at all
    html = _lookup(data, data["dupclient"], "gateway")
    assert "No retained record matches" in html
    # the per-candidate server form resolves one gateway record
    html = _lookup(data, data["dupa"], "gateway")
    # found-result-only fact for the resolved record
    assert "local_rejection / rate_limited" in html
    assert data["dupa"] in html
    assert "stream FAILED" not in html
    assert _counts(data) == before
    assert _audits(data) == []


def test_expired_not_returned_and_disabled_reads(route_env: dict[str, Any]) -> None:
    data = route_env
    # an expired row is NOT a retained match
    html = _lookup(data, data["expired_first"])
    assert "No retained record matches" in html

    # recording-disabled app on the SAME dedicated database: status
    # Disabled, retained lookups still served
    app = create_app(_settings(data["database_url"], enabled=False))
    with TestClient(app) as client:
        _login(client, data["admin_email"])
        html = client.get("/admin/operations/diagnostics").text
        assert "Disabled" in html
        csrf = CSRF_RE.search(html).group(1)
        response = client.post(
            "/admin/operations/diagnostics/lookup",
            data={
                "csrf_token": csrf,
                "lookup_id": data["preauth"],
                "lookup_namespace": "any",
            },
        )
        assert response.status_code == 200
        # found-result-only fact on the disabled-reads lookup too
        assert "local_rejection / authentication_failed" in response.text
        assert data["preauth"] in response.text


def test_choices_cap_dedup_and_older_hydration(route_env: dict[str, Any]) -> None:
    data = route_env
    assert _counts(data)["choices"] == N_CHOICE_RECENT + 1

    # >100 retained distinct IDs -> exactly the 100 cap, all unique,
    # the cross-namespace collision appears exactly ONCE, expired IDs
    # excluded by retention, and the older row is outside the batch.
    response = _choices(data)
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    payload = response.json()
    assert payload["kind"] == CHOICES_KIND
    assert payload["limit"] == DIAGNOSTIC_LOOKUP_BOUND
    assert payload["store_available"] is True
    ids = [c["id"] for c in payload["choices"]]
    assert len(ids) == DIAGNOSTIC_LOOKUP_BOUND
    assert len(set(ids)) == DIAGNOSTIC_LOOKUP_BOUND
    assert ids.count(data["choice_newest"]) == 1  # deduped, not twice
    assert data["choice_older"] not in ids
    assert not any(cid.startswith(f"211-exp-{data['suffix']}") for cid in ids)

    # a selected OLDER ID reserves its slot: hydrated even though it is
    # outside the newest-100 batch
    response = _choices(data, selected=(data["choice_older"],))
    assert response.status_code == 200
    payload = response.json()
    hydrated = [c for c in payload["choices"] if c["id"] == data["choice_older"]]
    assert len(hydrated) == 1
    assert "gateway" in hydrated[0]["sub"]
    assert len(payload["choices"]) == DIAGNOSTIC_LOOKUP_BOUND


def test_choices_native_auth_and_csrf_denials(route_env: dict[str, Any]) -> None:
    data = route_env
    before = _counts(data)
    # (1) NO session cookie: 303 to login, never a JSON success
    app = create_app(_settings(data["database_url"]))
    with TestClient(app) as anon:
        anon_response = anon.post(
            CHOICES_PATH,
            content=urlencode(
                [
                    ("csrf_token", "any"),
                    ("kind", CHOICES_KIND),
                    ("namespace", "any"),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
    response = anon_response
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert response.headers.get("content-type") is None or (
        "json" not in response.headers.get("content-type", "")
    )
    # a VALID token first: the picker works before any denial is credited
    ok = _choices(data)
    assert ok.status_code == 200
    assert ok.json()["store_available"] is True
    # (2) valid session + WRONG csrf: fixed 400 JSON refusal
    response = _choices(data, csrf="wrong-csrf-token")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid CSRF token."}
    # zero mutation from either denial
    assert _counts(data) == before
    assert _audits(data) == []


def test_cleanup_bounded_1000_with_single_audit(route_env: dict[str, Any]) -> None:
    data = route_env
    assert _counts(data)["expired"] == N_EXPIRED_SEEDED
    html = _cleanup(data, CLEANUP_REASON)
    assert "Cleanup complete: deleted 1,000 expired record(s)" in html
    # the flash-specific limit-reached sentence (the static confirmation
    # help always mentions the bounded batch)
    assert "The batch limit was reached; another run may be needed" in html

    counts = _counts(data)
    assert counts["expired"] == 1  # bounded batch: exactly one left
    assert counts["retained"] == 5  # retained rows preserved
    assert counts["choices"] == N_CHOICE_RECENT + 1
    audits = _audits(data)
    assert len(audits) == 1
    assert audits[0]["new"]["deleted_count"] == 1000
    assert audits[0]["note"] == CLEANUP_REASON


def test_cleanup_late_audit_failure_rolls_back_atomically(
    route_env: dict[str, Any],
) -> None:
    data = route_env
    asyncio_run(_insert_expired(data["database_url"], data["suffix"], 3))
    before = _counts(data)
    assert before["expired"] == 4

    real_add_audit_log = AuditRepository.add_audit_log

    async def _failing_audit(self, *args: Any, **kwargs: Any) -> Any:
        # Real audit flush FIRST (the audit row joins the transaction),
        # THEN the injected late commit failure rolls everything back.
        await real_add_audit_log(self, *args, **kwargs)
        raise RuntimeError("injected late commit failure")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AuditRepository, "add_audit_log", _failing_audit)
        html = _cleanup(data, CLEANUP_REASON)

    # the unconfirmed outcome is NOT rendered as a success
    assert "Cleanup outcome unconfirmed" in html
    assert "Cleanup complete" not in html
    # full atomic rollback: every expired row retained, NO committed
    # audit for the failed attempt
    assert _counts(data) == before
    assert len(_audits(data)) == 1


def test_cleanup_zero_delete_audited_once(route_env: dict[str, Any]) -> None:
    data = route_env
    # fixture: physically drop THIS run's remaining expired rows
    asyncio_run(_delete_all_expired(data["database_url"], data["suffix"]))
    assert _counts(data)["expired"] == 0

    html = _cleanup(data, ZERO_REASON)
    assert "Cleanup complete: deleted 0 expired record(s)" in html
    assert "The batch limit was reached" not in html

    counts = _counts(data)
    assert counts["expired"] == 0
    assert counts["retained"] == 5  # retained rows still preserved
    audits = _audits(data)
    assert len(audits) == 2
    assert audits[1]["new"]["deleted_count"] == 0
    assert audits[1]["note"] == ZERO_REASON
