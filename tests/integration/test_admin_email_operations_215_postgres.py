"""215-a G12 email operations: owned-PG HTTP qualification + local mock SMTP.

Real-app, real-PostgreSQL qualification for the 215-a authenticated GUI:
the additive exact list filters (against the unchanged substring
semantics), the shared latest-failure provenance, the shared Core
sendability bridge on the detail view, the explicit retry-failed action
(send-now through a REAL loopback SMTP sink; enqueue through a stubbed
broker with the exact three-UUID payload), the ordinary pending enqueue
requested-intent audit, and the bounded SMTP test (one-use claim,
per-actor budget, duplicate/concurrent submits, controlled fault seams).

This module reuses the ``owned_pg_url`` fixture directly (one NEW owned
container, migrated) and is the SOLE PG owner of the run.  The SMTP sink
is a small STANDARD-LIBRARY loopback-only synthetic SMTP fixture - a
LOCAL MOCK SMTP, not an inbox/provider/TLS qualification.  No ambient
DB, no real recipient, no real SMTP account, no provider or Codex call;
all rows are synthetic.

Proof seams (214 patterns): the recording broker stubs prove
durable-before-broker from INSIDE the dispatch using a SEPARATE fresh
PG session in a worker thread (no asyncio.run on the live ASGI loop);
the fixture DEFAULT-DENIES live dispatch on both module bindings (every
enqueue case installs its own explicit stub); the review CSRF is
captured ONCE (original) and reused for apply/repeat/concurrent
submits; the one-use claim race is proven both as a controlled
two-session HTTP seam and as a deterministic row-lock contention probe
(FOR UPDATE blocking observed); the commit-fault seam has a PRE-COMMIT
mode and a REAL-COMMIT-THEN-RAISE ACK-LOSS mode (durable claim, no
duplicate, never an assumed rollback); and a small legal unrelated
NONZERO key/usage/reservation sentinel plus full mapped-field row
digests bound the preservation proof (allowed changes are exactly the
selected delivery/secret rows plus append-only audit/admin rows).
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AdminUser,
    AuditLog,
    EmailDelivery,
    GatewayKey,
    OneTimeSecret,
    Owner,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.email_admin_operations import (
    SMTP_TEST_CLAIM_ACTION,
    SMTP_TEST_ENTITY_TYPE,
    SMTP_TEST_RESULT_ACTION,
    SmtpTestIntentAlreadyClaimedError,
    claim_smtp_test_attempt,
)
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.key_service import KeyService
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
RAW_PROSE = "raw-smtp-prose-MUST-NOT-LEAK-215"


def _row_link(email_delivery_id: uuid.UUID) -> str:
    """A list TABLE row's detail link."""
    return f"/admin/email-deliveries/{email_delivery_id}"


_TBodies_RE = re.compile(r"<tbody>(.*?)</tbody>", re.DOTALL)


def _table_body(response_text: str) -> str:
    """The actual rendered result rows (TBODY only).

    The page also carries the known-record picker's latest-100 choice
    metadata, which may mention record UUIDs WITHOUT rendering their
    rows; result-coverage assertions target the table body, and the
    picker choices are NOT shrunk to satisfy negatives.
    """
    bodies = _TBodies_RE.findall(response_text)
    assert bodies, "no table body rendered"
    return "\n".join(bodies)


# ---------------------------------------------------------------------------
# Local mock SMTP sink (stdlib asyncio, loopback-only, records envelopes)
# ---------------------------------------------------------------------------


class LocalMockSmtpSink:
    """Loopback-only synthetic SMTP sink (LOCAL MOCK SMTP, stdlib asyncio).

    Speaks the minimum SMTP dialogue aiosmtplib drives (greeting,
    EHLO/HELO, MAIL FROM, RCPT TO, DATA, QUIT) and records each accepted
    envelope.  No auth, no TLS, no relay, no delivery: a test fixture,
    never an inbox/provider qualification.
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.port: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Any = None
        self._thread: threading.Thread | None = None

    async def _on_connect(self, reader: Any, writer: Any) -> None:
        try:
            writer.write(b"220 slaif-local-mock-smtp ESMTP ready\r\n")
            await writer.drain()
            in_data = False
            data: list[str] = []
            envelope: dict[str, Any] = {"mail_from": None, "rcpt_to": [], "data": ""}
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if in_data:
                    if text == ".":
                        in_data = False
                        envelope["data"] = "\r\n".join(data)
                        self.messages.append(envelope)
                        writer.write(b"250 2.0.0 Ok: queued\r\n")
                    else:
                        data.append(text[1:] if text.startswith("..") else text)
                    await writer.drain()
                    continue
                upper = text.upper()
                if upper.startswith("EHLO") or upper.startswith("HELO"):
                    writer.write(b"250-slaif-local-mock-smtp\r\n250 OK\r\n")
                elif upper.startswith("MAIL FROM"):
                    match = re.search(r"<([^>]*)>", text)
                    envelope["mail_from"] = match.group(1) if match else None
                    writer.write(b"250 2.1.0 Ok\r\n")
                elif upper.startswith("RCPT TO"):
                    match = re.search(r"<([^>]*)>", text)
                    envelope["rcpt_to"].append(match.group(1) if match else None)
                    writer.write(b"250 2.1.5 Ok\r\n")
                elif upper.startswith("DATA"):
                    in_data = True
                    data = []
                    writer.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                elif upper.startswith("QUIT"):
                    writer.write(b"221 2.0.0 Bye\r\n")
                    await writer.drain()
                    break
                else:
                    writer.write(b"250 2.0.0 Ok\r\n")
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                writer.close()
            except (ConnectionError, OSError):
                pass

    def start(self) -> "LocalMockSmtpSink":
        self._loop = asyncio.new_event_loop()
        ready = threading.Event()

        def runner() -> None:
            asyncio.set_event_loop(self._loop)  # type: ignore[arg-type]

            async def boot() -> None:
                server = await asyncio.start_server(self._on_connect, "127.0.0.1", 0)
                self._server = server
                self.port = server.sockets[0].getsockname()[1]
                ready.set()

            self._loop.run_until_complete(boot())
            self._loop.run_forever()

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        assert ready.wait(15), "mock SMTP sink did not start"
        assert self.port is not None and 0 < self.port < 65536
        return self

    def stop(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Settings / app / DB helpers
# ---------------------------------------------------------------------------


def _settings(database_url: str, *, smtp_port: int) -> Settings:
    # Every SMTP transport field is explicit: loopback sink, no real
    # auth, no TLS.
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
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=smtp_port,
        SMTP_FROM="noreply-215@example.org",
        SMTP_USERNAME=None,
        SMTP_PASSWORD=None,
        SMTP_USE_TLS=False,
        SMTP_STARTTLS=False,
        SMTP_TIMEOUT_SECONDS=15,
        CELERY_BROKER_URL="redis://localhost:6379/15",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


class _FakeEmailService:
    """Only used where a real SMTP send must NOT happen (sendability probes)."""

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        raise AssertionError("no real send expected in this seam")


def _create_pending_delivery(
    database_url: str,
    settings: Settings,
    *,
    owner,
    label: str,
) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        engine = _engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    created = await KeyService(
                        settings=settings,
                        gateway_keys_repository=GatewayKeysRepository(session),
                        one_time_secrets_repository=OneTimeSecretsRepository(session),
                        audit_repository=AuditRepository(session),
                    ).create_gateway_key(
                        CreateGatewayKeyInput(
                            owner_id=owner.id,
                            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                            valid_until=datetime(2027, 1, 1, tzinfo=UTC),
                            allow_all_models=True,
                            allow_all_endpoints=True,
                            note=f"215 create {label}",
                        )
                    )
                    pending = await EmailDeliveryService(
                        settings=settings,
                        one_time_secrets_repository=OneTimeSecretsRepository(session),
                        email_deliveries_repository=EmailDeliveriesRepository(session),
                        gateway_keys_repository=GatewayKeysRepository(session),
                        owners_repository=OwnersRepository(session),
                        audit_repository=AuditRepository(session),
                        email_service=_FakeEmailService(),
                    ).create_pending_key_email_delivery(
                        gateway_key_id=created.gateway_key_id,
                        one_time_secret_id=created.one_time_secret_id,
                        owner_id=owner.id,
                        reason=f"215 pending {label}",
                    )
                    return {
                        "gateway_key_id": created.gateway_key_id,
                        "one_time_secret_id": created.one_time_secret_id,
                        "email_delivery_id": pending.email_delivery_id,
                        "owner_id": owner.id,
                    }
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _set_delivery_status(database_url: str, email_delivery_id: uuid.UUID, status: str, *, error_message: str | None = None) -> None:
    async def _run() -> None:
        engine = _engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    delivery = await session.get(EmailDelivery, email_delivery_id)
                    assert delivery is not None
                    delivery.status = status
                    if error_message is not None:
                        delivery.error_message = error_message
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _set_secret_state(database_url: str, one_time_secret_id: uuid.UUID, *, status: str | None = None, consumed: bool = False, expired: bool = False) -> None:
    async def _run() -> None:
        engine = _engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    secret = await session.get(OneTimeSecret, one_time_secret_id)
                    assert secret is not None
                    if status is not None:
                        secret.status = status
                    if consumed:
                        secret.status = "consumed"
                        secret.consumed_at = datetime.now(UTC)
                    if expired:
                        secret.status = "expired"
                        secret.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _seed_error_audit(database_url: str, delivery_id: uuid.UUID, *, error_code: str, action: str = "email_key_failed") -> None:
    async def _run() -> None:
        engine = _engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    await AuditRepository(session).add_audit_log(
                        action=action,
                        entity_type="email_delivery",
                        entity_id=delivery_id,
                        new_values={"error_code": error_code, "email_delivery_id": str(delivery_id)},
                    )
        finally:
            await engine.dispose()

    asyncio.run(_run())


async def _seed_data(database_url: str, settings: Settings) -> dict[str, Any]:
    engine = _engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    try:
        async with session_factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui215-{suffix}@example.org",
                    display_name="215 Email Ops Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner_a = await OwnersRepository(session).create_owner(
                    name="Alice", surname=f"215-{suffix}",
                    email=f"alice-{suffix}@example.org",
                )
                owner_b = await OwnersRepository(session).create_owner(
                    name="Alice", surname=f"Sub-{suffix}",
                    email=f"alice-{suffix}-sub@example.org",
                )
                owner_c = await OwnersRepository(session).create_owner(
                    name="Cleo", surname=f"215-{suffix}",
                    email=f"cleo-{suffix}@example.org",
                )
                return {
                    "admin_email": admin.email,
                    "admin_id": admin.id,
                    "owner_a": owner_a,
                    "owner_b": owner_b,
                    "owner_c": owner_c,
                    "suffix": suffix,
                }
    finally:
        await engine.dispose()


def _seed_sibling_delivery(
    database_url: str,
    *,
    one_time_secret_id: uuid.UUID,
    gateway_key_id: uuid.UUID,
    owner_id: uuid.UUID,
    status: str,
    recipient_email: str,
    label: str,
) -> dict[str, Any]:
    """One synthetic same-secret delivery row (fixture-only history state)."""

    async def _run() -> dict[str, Any]:
        engine = _engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                async with session.begin():
                    row = EmailDelivery(
                        id=uuid.uuid4(),
                        owner_id=owner_id,
                        gateway_key_id=gateway_key_id,
                        one_time_secret_id=one_time_secret_id,
                        recipient_email=recipient_email,
                        subject=f"215 sibling {label}",
                        template_name="gateway_key_email",
                        status=status,
                        failed_at=datetime.now(UTC) if status == "failed" else None,
                        created_at=datetime.now(UTC),
                    )
                    session.add(row)
                    return {"email_delivery_id": row.id, "one_time_secret_id": one_time_secret_id}
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _login(client: TestClient, env: dict[str, Any]) -> None:
    response = client.get("/admin/login")
    assert response.status_code == 200
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        "/admin/login",
        data={"csrf_token": csrf, "email": env["admin_email"], "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _page_csrf(client: TestClient, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200
    return CSRF_RE.search(response.text).group(1)


# ---------------------------------------------------------------------------
# Threaded DB worker + preservation digests (214 pattern)
# ---------------------------------------------------------------------------


def _db_worker(database_url: str, coro_factory) -> Any:
    """Run a DB coroutine in a WORKER THREAD (the 214 threaded-DB pattern).

    The recording broker stubs execute inside the TestClient's live ASGI
    loop thread, where ``asyncio.run`` would raise ("cannot be called
    from a running event loop"); a fresh worker thread has no running
    loop, so the SEPARATE fresh PG connection used to prove
    durable-before-broker is safe there.
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


def _row_digest(model: type, row: Any, exclude: frozenset[str] = frozenset()) -> str:
    """Full mapped-field digest of one row (every column attribute)."""
    columns = [attr.key for attr in sa_inspect(model).column_attrs if attr.key not in exclude]
    canonical = json.dumps(
        {c: _jsonable(getattr(row, c)) for c in columns},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Login bookkeeping legitimately touches ONLY these auth-tracking
# columns; every other admin identity field is invariant.
_ADMIN_USER_AUTH_TRACKING = frozenset({"last_login_at", "updated_at"})


def _preservation_snapshot(database_url: str) -> dict[str, dict[str, str]]:
    """Per-row mapped-field digests for every table the email ops touch."""

    async def _run(session) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for name, model in (
            ("gateway_keys", GatewayKey),
            ("usage_ledger", UsageLedger),
            ("quota_reservations", QuotaReservation),
            ("one_time_secrets", OneTimeSecret),
            ("email_deliveries", EmailDelivery),
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


def _seed_sentinel_key(database_url: str, owner) -> dict[str, Any]:
    """One small LEGAL unrelated nonzero key/usage/reservation sentinel.

    The 213/214 preservation-sentinel pattern: an all-zero ledger state
    alone cannot prove preservation, so a real nonzero usage ledger row,
    a real reservation row, and nonzero key counters must survive every
    215 email operation byte-identical (full mapped-field digests).
    """

    async def _run() -> dict[str, Any]:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid.uuid4().hex[:10]
        try:
            async with factory() as session:
                async with session.begin():
                    key = await GatewayKeysRepository(session).create_gateway_key_record(
                        public_key_id=f"215sent-{suffix}",
                        token_hash=f"215sent-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        valid_until=datetime(2027, 1, 1, tzinfo=UTC),
                        status="active",
                        allow_all_models=False,
                        allowed_models=[f"215sent-model-{suffix}"],
                        allow_all_endpoints=False,
                        allowed_endpoints=["/v1/chat/completions"],
                        cost_limit_eur=Decimal("42.5"),
                        token_limit_total=1234567,
                        request_limit_total=89,
                    )
                    key.cost_used_eur = Decimal("7.25")
                    key.tokens_used_total = 101
                    key.requests_used_total = 7
                    reservation = QuotaReservation(
                        id=uuid.uuid4(),
                        gateway_key_id=key.id,
                        request_id=f"req-215sent-resv-{suffix}",
                        endpoint="/v1/chat/completions",
                        requested_model=f"215sent-model-{suffix}",
                        provider="prov-215sent",
                        reserved_cost_eur=Decimal("0.05"),
                        reserved_tokens=13,
                        reserved_requests=2,
                        status="pending",
                        expires_at=datetime.now(UTC) + timedelta(days=1),
                    )
                    session.add(reservation)
                    ledger = UsageLedger(
                        request_id=f"req-215sent-ledger-{suffix}",
                        gateway_key_id=key.id,
                        owner_id=owner.id,
                        quota_reservation_id=reservation.id,
                        owner_name_snapshot=owner.name,
                        owner_surname_snapshot=owner.surname,
                        endpoint="/v1/chat/completions",
                        provider="prov-215sent",
                        requested_model=f"215sent-model-{suffix}",
                        resolved_model=f"215sent-model-{suffix}",
                        streaming=False,
                        success=True,
                        http_status=200,
                        prompt_tokens=41,
                        completion_tokens=17,
                        input_tokens=41,
                        output_tokens=17,
                        total_tokens=58,
                        estimated_cost_eur=Decimal("0.05"),
                        actual_cost_eur=Decimal("0.048"),
                        usage_raw={"sentinel": "215a"},
                        response_metadata={},
                        started_at=datetime(2026, 9, 1, tzinfo=UTC),
                        finished_at=datetime(2026, 9, 1, tzinfo=UTC),
                        latency_ms=120,
                    )
                    session.add(ledger)
                    return {
                        "gateway_key_id": key.id,
                        "reservation_id": reservation.id,
                        "ledger_request_id": ledger.request_id,
                    }
        finally:
            await engine.dispose()

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Module environment: owned PG (sole owner) + local mock SMTP + real app
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env215(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    sink = LocalMockSmtpSink().start()
    try:
        settings = _settings(owned_pg_url, smtp_port=int(sink.port))
        base = asyncio.run(_seed_data(owned_pg_url, settings))
        owner_a, owner_b = base.pop("owner_a"), base.pop("owner_b")
        base["owner_c"] = base.pop("owner_c")
        # State matrix (file order is significant):
        #  - pending (owner A): ordinary send/enqueue surface
        #  - failed (owner A): retry-failed surface + known-code error audit
        #  - failed+raw prose (owner C): raw prose must never reach the DOM
        #  - same-secret history (owner B): one sending + one failed row
        #  - consumed-secret / expired-secret failures
        pending = _create_pending_delivery(owned_pg_url, settings, owner=owner_a, label="pending")
        failed = _create_pending_delivery(owned_pg_url, settings, owner=owner_a, label="failed")
        failed_prose = _create_pending_delivery(owned_pg_url, settings, owner=base["owner_c"], label="failedprose")
        failed3 = _create_pending_delivery(owned_pg_url, settings, owner=base["owner_c"], label="failed3")
        hist_a = _create_pending_delivery(owned_pg_url, settings, owner=owner_b, label="hist-sending")
        _set_delivery_status(owned_pg_url, hist_a["email_delivery_id"], "sending")
        # hist_b shares hist_a's one-time secret: the same-secret history
        # truth (a sending sibling) must block the failed row.
        hist_b = _seed_sibling_delivery(
            owned_pg_url,
            one_time_secret_id=hist_a["one_time_secret_id"],
            gateway_key_id=hist_a["gateway_key_id"],
            owner_id=owner_b.id,
            status="failed",
            recipient_email="histb-sibling-215@example.org",
            label="hist-failed",
        )
        consumed = _create_pending_delivery(owned_pg_url, settings, owner=owner_b, label="consumed")
        expired = _create_pending_delivery(owned_pg_url, settings, owner=base["owner_c"], label="expired")

        _set_delivery_status(owned_pg_url, failed["email_delivery_id"], "failed")
        _set_delivery_status(owned_pg_url, failed_prose["email_delivery_id"], "failed", error_message=RAW_PROSE)
        _set_delivery_status(owned_pg_url, failed3["email_delivery_id"], "failed")
        _set_delivery_status(owned_pg_url, consumed["email_delivery_id"], "failed")
        _set_delivery_status(owned_pg_url, expired["email_delivery_id"], "failed")
        _set_secret_state(owned_pg_url, consumed["one_time_secret_id"], consumed=True)
        _set_secret_state(owned_pg_url, expired["one_time_secret_id"], expired=True)
        _seed_error_audit(owned_pg_url, failed["email_delivery_id"], error_code="smtp_send_error")
        _seed_error_audit(owned_pg_url, failed_prose["email_delivery_id"], error_code="totally-unknown-code")

        base["owner_a_id"] = owner_a.id
        base["owner_b_id"] = owner_b.id
        base["owner_c_id"] = base["owner_c"].id
        base.update(
            pending=pending,
            failed=failed,
            failed_prose=failed_prose,
            failed3=failed3,
            hist_a=hist_a,
            hist_b=hist_b,
            consumed=consumed,
            expired=expired,
            settings=settings,
            sink=sink,
            database_url=owned_pg_url,
        )
        # Preservation sentinel (213/214 pattern): one small LEGAL
        # unrelated nonzero key/usage/reservation that must survive
        # every operation byte-identical (full mapped-field digests).
        base["sentinel"] = _seed_sentinel_key(owned_pg_url, owner_a)
        seeded = (pending, failed, failed_prose, failed3, hist_a, consumed, expired)
        base["allowed_secret_ids"] = {d["one_time_secret_id"] for d in seeded}
        base["allowed_delivery_ids"] = {d["email_delivery_id"] for d in seeded} | {
            hist_b["email_delivery_id"]
        }
        # BEFORE baseline: captured after all seeding, before any test
        # operation mutates anything.
        base["preservation_before"] = _preservation_snapshot(owned_pg_url)

        # DEFAULT-DENY live dispatch: both module bindings fail loudly
        # unless a test installs its own explicit recording stub - the
        # fixture must never allow contact with the unowned localhost
        # broker (redis://localhost:6379/15 in settings is inert).
        from slaif_gateway.api import admin as _admin_module
        from slaif_gateway.api import admin_email_operations as _ops_module

        def _default_deny_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
            raise AssertionError(
                "live broker dispatch attempted without an explicit stub "
                "(215 default-deny fixture binding)"
            )

        _admin_orig = _admin_module._enqueue_admin_pending_key_email
        _ops_orig = _ops_module._enqueue_admin_pending_key_email
        _admin_module._enqueue_admin_pending_key_email = _default_deny_enqueue
        _ops_module._enqueue_admin_pending_key_email = _default_deny_enqueue

        app = create_app(settings)
        # Lifespan-managed client (214 pattern): create_app leaves
        # app.state.db_sessionmaker = None; the app LIFESPAN initializes
        # it, and a bare TestClient(app) never starts it.  The
        # module-scoped context keeps it alive for every secondary
        # cookie client on the SAME app (they must not re-initialize or
        # discard the parent lifespan).
        with TestClient(app) as client:
            _login(client, base)
            base["client"] = client
            base["app"] = app
            yield base
    finally:
        _admin_module._enqueue_admin_pending_key_email = _admin_orig
        _ops_module._enqueue_admin_pending_key_email = _ops_orig
        sink.stop()


# ---- list: additive exact filters vs unchanged substring -------------------


def test_list_exact_filters_and_unchanged_substring(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    pending, failed, failed_prose, hist_b = (env215[k] for k in ("pending", "failed", "failed_prose", "hist_b"))
    suffix = env215["suffix"]

    # Exact delivery UUID: exactly one rendered row (TBODY-scoped).
    response = client.get(f"/admin/email-deliveries?delivery_id={failed['email_delivery_id']}")
    assert response.status_code == 200
    body = _table_body(response.text)
    assert _row_link(failed["email_delivery_id"]) in body
    assert _row_link(pending["email_delivery_id"]) not in body

    # Repeatable OR-within: two delivery ids -> two rendered rows.
    response = client.get(
        f"/admin/email-deliveries?delivery_id={failed['email_delivery_id']}&delivery_id={pending['email_delivery_id']}"
    )
    assert response.status_code == 200
    body = _table_body(response.text)
    assert _row_link(failed["email_delivery_id"]) in body
    assert _row_link(pending["email_delivery_id"]) in body
    assert _row_link(failed_prose["email_delivery_id"]) not in body

    # Exact owner email (shared CLI normalization: strip/lower) matches
    # ONLY owner A, while the legacy substring owner_email matches A and
    # the -sub owner B.
    response = client.get(f"/admin/email-deliveries?owner_email_exact=ALICE-{suffix}@example.org")
    assert response.status_code == 200
    # Case/trim normalization: the submitted value differs in case from
    # the stored one and still matches exactly.
    body = _table_body(response.text)
    assert _row_link(pending["email_delivery_id"]) in body
    assert _row_link(hist_b["email_delivery_id"]) not in body

    response = client.get(f"/admin/email-deliveries?owner_email=alice-{suffix}")
    assert response.status_code == 200
    body = _table_body(response.text)
    assert _row_link(pending["email_delivery_id"]) in body
    assert _row_link(hist_b["email_delivery_id"]) in body

    # AND across: exact owner email + exact owner id.
    response = client.get(
        f"/admin/email-deliveries?owner_email_exact=alice-{suffix}@example.org&owner_id={env215['owner_b_id']}"
    )
    assert response.status_code == 200
    assert _row_link(pending["email_delivery_id"]) not in _table_body(response.text)  # owner A rows excluded

    # Exact owner id only: owner B rows.
    response = client.get(f"/admin/email-deliveries?owner_id={env215['owner_b_id']}")
    assert response.status_code == 200
    body = _table_body(response.text)
    assert _row_link(hist_b["email_delivery_id"]) in body
    assert _row_link(pending["email_delivery_id"]) not in body


def test_list_date_bounds_naive_utc_and_end_before_start(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    pending = env215["pending"]
    # Naive (no timezone) input is treated as UTC and usable: everything
    # created now is inside a wide window.
    response = client.get("/admin/email-deliveries?start_at=2000-01-01T00:00:00&end_at=2999-01-01T00:00:00")
    assert response.status_code == 200
    assert _row_link(pending["email_delivery_id"]) in _table_body(response.text)
    # A window entirely in the past matches nothing.
    response = client.get("/admin/email-deliveries?start_at=1999-01-01T00:00:00&end_at=1999-01-02T00:00:00")
    assert response.status_code == 200
    assert _row_link(pending["email_delivery_id"]) not in _table_body(response.text)
    # End before start is refused safely (fixed message, no echo).
    response = client.get("/admin/email-deliveries?start_at=2026-01-02T00:00:00&end_at=2026-01-01T00:00:00")
    assert response.status_code == 400
    assert "Invalid filter." in response.text
    # The HTML filter form submits BLANK date controls: blank + a valid
    # status filter is a normal 200 (unbounded), never a framework 422.
    response = client.get("/admin/email-deliveries?status=failed&start_at=&end_at=")
    assert response.status_code == 200
    assert _row_link(env215["failed"]["email_delivery_id"]) in _table_body(response.text)
    assert _row_link(env215["pending"]["email_delivery_id"]) not in _table_body(response.text)
    # A nonblank non-ISO value is a fixed invalid-filter refusal (no
    # echo of the submitted value).
    response = client.get("/admin/email-deliveries?start_at=not-a-datetime")
    assert response.status_code == 400
    assert "Invalid filter." in response.text
    assert "not-a-datetime" not in response.text


def test_list_cap_plus_one_has_more_and_filter_carry_through(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    # There are at least 5 seeded deliveries; page size 3 must report
    # has_more with a Next link that carries the filters through.
    response = client.get("/admin/email-deliveries?limit=3&owner_email=alice")
    assert response.status_code == 200
    assert 'class="pagination' in response.text or "Next" in response.text
    next_link = re.search(r'href="([^"]*?/admin/email-deliveries\?[^"]*offset=3[^"]*)"', response.text)
    assert next_link is not None, "no Next page link with carried filters"
    assert "owner_email=alice" in next_link.group(1)
    assert "limit=3" in next_link.group(1)


def test_list_status_filter_uses_canonical_statuses(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    # Canonical persisted statuses only (no non-persisted consumed/expired
    # delivery statuses); a failed-only filter returns exactly the failed
    # matrix rows.
    response = client.get("/admin/email-deliveries?status=failed")
    assert response.status_code == 200
    body = _table_body(response.text)
    for key in ("failed", "failed_prose", "hist_b", "consumed", "expired"):
        assert _row_link(env215[key]["email_delivery_id"]) in body
    assert _row_link(env215["pending"]["email_delivery_id"]) not in body
    # Other canonical persisted statuses still work.
    response = client.get("/admin/email-deliveries?status=pending")
    assert response.status_code == 200
    body = _table_body(response.text)
    assert _row_link(env215["pending"]["email_delivery_id"]) in body
    assert _row_link(env215["failed"]["email_delivery_id"]) not in body
    # Consumed/expired are NOT delivery statuses: filtering by them is a
    # fixed invalid-filter refusal (they are secret lifecycle states).
    for label in ("consumed", "expired"):
        response = client.get(f"/admin/email-deliveries?status={label}")
        assert response.status_code == 400
        assert "Invalid filter." in response.text


# ---- detail: provenance + shared Core sendability bridge -------------------


def test_detail_shows_finite_failure_provenance_not_raw_prose(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    failed, failed_prose, pending = env215["failed"], env215["failed_prose"], env215["pending"]

    # Known finite code: the shared projection renders code/action/time.
    response = client.get(f"/admin/email-deliveries/{failed['email_delivery_id']}")
    assert response.status_code == 200
    assert "smtp_send_error" in response.text
    assert "email_key_failed" in response.text
    assert "Last recorded failure" in response.text

    # Unknown recorded code: the finite `unavailable` label, never prose.
    response = client.get(f"/admin/email-deliveries/{failed_prose['email_delivery_id']}")
    assert response.status_code == 200
    assert "unavailable" in response.text
    assert "totally-unknown-code" not in response.text
    # Raw legacy error_message/SMTP prose must not reach the DOM.
    assert RAW_PROSE not in response.text

    # No matching error audit: useful unavailable explanation.
    response = client.get(f"/admin/email-deliveries/{pending['email_delivery_id']}")
    assert response.status_code == 200
    assert "No safe failure code is recorded for this delivery" in response.text


def test_detail_bridges_shared_core_sendability(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    # Same-secret history: the FAILED row is blocked by its same-secret
    # SENDING sibling (the Core truth the CLI sees), not by the legacy
    # single-row projection.
    hist_b = env215["hist_b"]
    response = client.get(f"/admin/email-deliveries/{hist_b['email_delivery_id']}")
    assert response.status_code == 200
    assert "A prior delivery attempt for this one-time secret is sending" in response.text
    assert 'id="retry-mode-select"' not in response.text  # retry form hidden

    # Consumed-secret failed row: secret lifecycle blocker, no retry form.
    consumed = env215["consumed"]
    response = client.get(f"/admin/email-deliveries/{consumed['email_delivery_id']}")
    assert response.status_code == 200
    assert "already consumed" in response.text
    assert 'id="retry-mode-select"' not in response.text

    # Pending sendable row: ordinary send/enqueue forms visible, no raw
    # provider prose anywhere.
    pending = env215["pending"]
    response = client.get(f"/admin/email-deliveries/{pending['email_delivery_id']}")
    assert response.status_code == 200
    assert f"/admin/email-deliveries/{pending['email_delivery_id']}/send-now" in response.text
    assert f"/admin/email-deliveries/{pending['email_delivery_id']}/enqueue" in response.text

    # Failed sendable row: the explicit retry-failed form with actual
    # control IDs + associated help.
    failed = env215["failed"]
    response = client.get(f"/admin/email-deliveries/{failed['email_delivery_id']}")
    assert response.status_code == 200
    assert 'id="retry-mode-select"' in response.text
    assert 'id="retry-reason-input"' in response.text
    assert 'id="retry-confirm-checkbox"' in response.text
    assert 'id="retry-mode-help"' in response.text
    assert 'id="retry-confirm-help"' in response.text
    assert "1024 UTF-8 bytes" in response.text


def test_detail_and_list_redact_credential_shaped_addresses(env215: dict[str, Any]) -> None:
    # A legacy/corrupted row carrying a credential-shaped recipient or
    # owner address must be redacted in the GUI projection (same safe
    # projection as the CLI), in BOTH list and detail.
    async def _corrupt() -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(env215["database_url"], future=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    delivery = await session.get(EmailDelivery, env215["expired"]["email_delivery_id"])
                    assert delivery is not None
                    delivery.recipient_email = "sk-slaif-abcdef0123456789abcdef0123456789abcdef01@example.org"
        finally:
            await engine.dispose()

    asyncio.run(_corrupt())
    client: TestClient = env215["client"]
    expired_id = env215["expired"]["email_delivery_id"]
    list_response = client.get(f"/admin/email-deliveries?delivery_id={expired_id}")
    assert list_response.status_code == 200
    assert "sk-slaif-abcdef0123456789abcdef0123456789abcdef01@example.org" not in list_response.text
    detail_response = client.get(f"/admin/email-deliveries/{expired_id}")
    assert detail_response.status_code == 200
    assert "sk-slaif-abcdef0123456789abcdef0123456789abcdef01@example.org" not in detail_response.text


# ---- retry-failed: real send-now through the local mock SMTP --------------


def test_retry_failed_send_now_sends_exactly_once_and_consumes(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    failed = env215["failed"]
    delivery_id = failed["email_delivery_id"]
    before = len(sink.messages)

    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": csrf,
            "retry_mode": "send-now",
            "reason": "215 native retry after SMTP outage",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_sent")

    # Exactly ONE real message reached the loopback sink...
    assert len(sink.messages) == before + 1
    envelope = sink.messages[-1]
    assert envelope["mail_from"] == "noreply-215@example.org"
    # ...to the PREPARED destination (current owner, refreshed at
    # execution time), with the gateway key in the body (the whole point
    # of key email) and no raw provider prose.
    delivery = _get_delivery(env215["database_url"], delivery_id)
    assert envelope["rcpt_to"] == [delivery.recipient_email]
    # Stable line from the rendered key-email body (the plaintext key
    # itself is asserted on separately where shown once).
    assert "Your SLAIF API Gateway key" in envelope["data"]

    # The row finalized to sent, the one-time secret consumed.
    assert delivery.status == "sent"
    assert delivery.sent_at is not None
    secret = _get_secret(env215["database_url"], delivery.one_time_secret_id)
    assert secret.status == "consumed"
    assert secret.consumed_at is not None

    # Repeat: the consumed secret is NEVER made resendable by a checkbox.
    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": csrf,
            "retry_mode": "send-now",
            "reason": "215 native repeat retry must refuse",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    # The row is now SENT (not failed): the truthful not-failed copy,
    # never the FAILED-only retry-required or a secret-lifecycle claim.
    assert response.headers["location"].endswith("message=email_delivery_retry_not_applicable")
    assert len(sink.messages) == before + 1  # no second message


def test_retry_failed_enqueue_records_intent_before_stubbed_broker(monkeypatch, env215: dict[str, Any]) -> None:
    from slaif_gateway.api import admin_email_operations as ops_router

    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    failed3 = env215["failed3"]
    delivery_id = failed3["email_delivery_id"]
    before = len(sink.messages)

    calls: list[tuple[object, ...]] = []

    def _fake_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        calls.append((str(one_time_secret_id), str(email_delivery_id), str(actor_admin_id)))
        # PROVE durable-before-broker: INSIDE the dispatch stub, a
        # SEPARATE fresh PG session (214 threaded worker - never
        # asyncio.run on the live ASGI loop) must ALREADY see the exact
        # intent committed - not merely after the HTTP response.
        async def _probe(session) -> list[AuditLog]:
            rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "email_key_enqueue_requested",
                        AuditLog.entity_id == email_delivery_id,
                        AuditLog.admin_user_id == actor_admin_id,
                    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                )
            ).scalars().all()
            return list(rows)

        rows = _db_worker(env215["database_url"], _probe)
        assert len(rows) == 1
        row = rows[0]
        assert row.new_values["retry_failed"] is True
        assert row.new_values["intent"] == "enqueue_requested"
        assert row.note == "215 native enqueue retry"
        assert row.admin_user_id == env215["admin_id"]
        return "fake-215-task-id"

    monkeypatch.setattr(ops_router, "_enqueue_admin_pending_key_email", _fake_enqueue)

    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": csrf,
            "retry_mode": "enqueue",
            "reason": "215 native enqueue retry",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_queued")

    # No SMTP happened on the API path...
    assert len(sink.messages) == before
    # ...the payload stays EXACTLY the existing three UUID args...
    assert len(calls) == 1
    uuid.UUID(calls[0][0])
    uuid.UUID(calls[0][1])
    uuid.UUID(calls[0][2])
    assert calls[0][1] == str(delivery_id)
    # ...and the explicit retry intent is durable with the server actor.
    rows = _audit_rows(env215["database_url"], action="email_key_enqueue_requested", entity_id=delivery_id)
    assert len(rows) == 1
    assert rows[0].new_values["retry_failed"] is True
    assert rows[0].new_values["intent"] == "enqueue_requested"
    assert rows[0].note == "215 native enqueue retry"
    assert rows[0].admin_user_id == env215["admin_id"]
    assert rows[0].new_values["one_time_reference_id"] == str(failed3["one_time_secret_id"])


def test_retry_failed_now_pending_row_refuses_via_http(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    pending = env215["pending"]
    delivery_id = pending["email_delivery_id"]
    before = len(sink.messages)

    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": csrf,
            "retry_mode": "send-now",
            "reason": "215 native failed-only on pending row",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Truthful not-failed copy: the row is pending, so the FAILED-only
    # message must not claim it is failed (that one stays reserved for
    # genuine failed-row redirects).
    assert response.headers["location"].endswith("message=email_delivery_retry_not_applicable")
    assert len(sink.messages) == before


def test_normal_send_on_now_failed_row_refuses_via_http(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    failed_prose = env215["failed_prose"]
    delivery_id = failed_prose["email_delivery_id"]
    before = len(sink.messages)

    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={"csrf_token": csrf, "confirm_send": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_retry_required")
    assert len(sink.messages) == before


def test_retry_failed_broker_failure_is_requested_but_unconfirmed(monkeypatch, env215: dict[str, Any]) -> None:
    from slaif_gateway.api import admin_email_operations as ops_router

    client: TestClient = env215["client"]
    failed_prose = env215["failed_prose"]
    delivery_id = failed_prose["email_delivery_id"]

    def _broken_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        raise RuntimeError("broker down (fixture)")

    monkeypatch.setattr(ops_router, "_enqueue_admin_pending_key_email", _broken_enqueue)

    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": csrf,
            "retry_mode": "enqueue",
            "reason": "215 native broker failure",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_enqueue_unconfirmed")
    # The requested intent IS durable (requested, not queued/sent)...
    rows = _audit_rows(env215["database_url"], action="email_key_enqueue_requested", entity_id=delivery_id)
    assert len(rows) == 1
    # ...and no queued/sent success or raw fault prose is fabricated.
    assert "broker down" not in response.text
    assert "email_delivery_queued" not in response.headers["location"]
    assert "email_delivery_sent" not in response.headers["location"]


def test_retry_failed_recording_failure_prevents_broker(monkeypatch, env215: dict[str, Any]) -> None:
    from slaif_gateway.api import admin_email_operations as ops_router

    client: TestClient = env215["client"]
    failed3 = env215["failed3"]
    delivery_id = failed3["email_delivery_id"]
    calls: list[tuple[object, ...]] = []

    async def _audit_raises(**kwargs: Any) -> None:
        raise RuntimeError("commit fault (fixture)")

    def _fake_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        calls.append((str(one_time_secret_id), str(email_delivery_id), str(actor_admin_id)))
        return "fake-215-task-id"

    monkeypatch.setattr(ops_router, "record_enqueue_request_audit", _audit_raises)
    monkeypatch.setattr(ops_router, "_enqueue_admin_pending_key_email", _fake_enqueue)

    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": csrf,
            "retry_mode": "enqueue",
            "reason": "215 native recording failure",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_enqueue_recording_unconfirmed")
    assert calls == []  # recording failure prevents broker dispatch entirely


# ---- ordinary pending enqueue: committed requested-intent audit -----------


def test_ordinary_pending_enqueue_records_intent_before_broker(monkeypatch, env215: dict[str, Any]) -> None:
    from slaif_gateway.api import admin as admin_module

    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    pending = env215["pending"]
    delivery_id = pending["email_delivery_id"]
    before = len(sink.messages)

    calls: list[tuple[object, ...]] = []

    def _fake_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        calls.append((str(one_time_secret_id), str(email_delivery_id), str(actor_admin_id)))
        # PROVE durable-before-broker: INSIDE the dispatch stub, a
        # SEPARATE fresh PG session (214 threaded worker - never
        # asyncio.run on the live ASGI loop) must ALREADY see the exact
        # intent committed - not merely after the HTTP response.
        async def _probe(session) -> list[AuditLog]:
            rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "email_key_enqueue_requested",
                        AuditLog.entity_id == email_delivery_id,
                        AuditLog.admin_user_id == actor_admin_id,
                    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                )
            ).scalars().all()
            return list(rows)

        rows = _db_worker(env215["database_url"], _probe)
        assert len(rows) == 1
        row = rows[0]
        assert row.new_values["retry_failed"] is False
        assert row.new_values["intent"] == "enqueue_requested"
        assert row.note == "215 native pending enqueue"
        assert row.admin_user_id == env215["admin_id"]
        return "fake-215-task-id"

    monkeypatch.setattr(admin_module, "_enqueue_admin_pending_key_email", _fake_enqueue)

    # Optional reason preserved (nonblank): recorded with the server
    # actor and retry_failed=False.
    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={"csrf_token": csrf, "confirm_enqueue": "true", "reason": "215 native pending enqueue"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_queued")
    assert len(sink.messages) == before  # the API never sends on enqueue
    assert len(calls) == 1
    uuid.UUID(calls[0][0])
    uuid.UUID(calls[0][1])
    uuid.UUID(calls[0][2])
    rows = _audit_rows(env215["database_url"], action="email_key_enqueue_requested", entity_id=delivery_id)
    assert len(rows) == 1
    assert rows[0].new_values["retry_failed"] is False
    assert rows[0].note == "215 native pending enqueue"
    assert rows[0].admin_user_id == env215["admin_id"]

    # 215-a canary: a PROVIDED reason matching an ACTUAL incoming opaque
    # cookie is withheld BEFORE any audit/broker - no new durable
    # intent, no second dispatch, fixed safe feedback (valid auth/CSRF/
    # eligible pending target throughout).
    intent_ids_before = {row.id for row in rows}
    client.cookies.set("slaif_opaque_token", "opaque-cookie-secret-215")
    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={
            "csrf_token": csrf,
            "confirm_enqueue": "true",
            "reason": "opaque-cookie-secret-215",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_reason_withheld")
    assert len(calls) == 1  # no second broker dispatch
    rows_after = _audit_rows(env215["database_url"], action="email_key_enqueue_requested", entity_id=delivery_id)
    assert {row.id for row in rows_after} == intent_ids_before  # no new intent


def test_ordinary_pending_enqueue_blank_reason_stays_none(monkeypatch, env215: dict[str, Any]) -> None:
    from slaif_gateway.api import admin as admin_module

    client: TestClient = env215["client"]
    pending = env215["pending"]
    delivery_id = pending["email_delivery_id"]
    # This delivery already carries the prior nonblank-reason intent
    # from the previous test (UUID audit ids are random, so the NEW
    # event is selected by ID delta, never by row position).
    existing_ids = {row.id for row in _audit_rows(env215["database_url"], action="email_key_enqueue_requested", entity_id=delivery_id)}
    assert len(existing_ids) == 1
    calls: list[tuple[object, ...]] = []

    def _fake_enqueue(*, one_time_secret_id, email_delivery_id, actor_admin_id):
        calls.append((str(one_time_secret_id), str(email_delivery_id), str(actor_admin_id)))
        # PROVE durable-before-broker: INSIDE the dispatch stub, a
        # SEPARATE fresh PG session (214 threaded worker - never
        # asyncio.run on the live ASGI loop) must ALREADY see the exact
        # intent committed - not merely after the HTTP response.
        async def _probe(session) -> list[AuditLog]:
            rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "email_key_enqueue_requested",
                        AuditLog.entity_id == email_delivery_id,
                        AuditLog.admin_user_id == actor_admin_id,
                    )
                )
            ).scalars().all()
            return list(rows)

        rows = _db_worker(env215["database_url"], _probe)
        # Exactly the prior row plus THIS new one; select by ID delta.
        new_rows = [r for r in rows if r.id not in existing_ids]
        prior_rows = [r for r in rows if r.id in existing_ids]
        assert len(rows) == 2
        assert len(new_rows) == 1
        assert len(prior_rows) == 1
        # Prior history is preserved untouched (correct reason handling).
        assert prior_rows[0].note == "215 native pending enqueue"
        row = new_rows[0]
        assert row.new_values["retry_failed"] is False
        assert row.new_values["intent"] == "enqueue_requested"
        assert row.note is None
        assert row.admin_user_id == env215["admin_id"]
        return "fake-215-task-id"

    monkeypatch.setattr(admin_module, "_enqueue_admin_pending_key_email", _fake_enqueue)

    # Blank/missing pending reason is still accepted (the failed-only
    # nonblank rule does NOT apply); the audit note stays None.
    csrf = _page_csrf(client, f"/admin/email-deliveries/{delivery_id}")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={"csrf_token": csrf, "confirm_enqueue": "true", "reason": "   "},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_queued")
    assert len(calls) == 1
    rows = _audit_rows(env215["database_url"], action="email_key_enqueue_requested", entity_id=delivery_id)
    assert len(rows) == 2
    new_row = [r for r in rows if r.id not in existing_ids]
    assert len(new_row) == 1
    assert new_row[0].note is None
    assert new_row[0].new_values["retry_failed"] is False
    prior_row = [r for r in rows if r.id in existing_ids][0]
    assert prior_row.note == "215 native pending enqueue"


# ---------------------------------------------------------------------------
# Bounded DB oracles
# ---------------------------------------------------------------------------


def _get_delivery(database_url: str, delivery_id: uuid.UUID) -> EmailDelivery:
    async def _run() -> EmailDelivery:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                delivery = await session.get(EmailDelivery, delivery_id)
                assert delivery is not None
                return delivery
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _get_secret(database_url: str, secret_id: uuid.UUID) -> OneTimeSecret:
    async def _run() -> OneTimeSecret:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                secret = await session.get(OneTimeSecret, secret_id)
                assert secret is not None
                return secret
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _audit_rows(database_url: str, *, action: str, entity_id: uuid.UUID | None = None) -> list[AuditLog]:
    async def _run() -> list[AuditLog]:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                statement = select(AuditLog).where(AuditLog.action == action)
                if entity_id is not None:
                    statement = statement.where(AuditLog.entity_id == entity_id)
                statement = statement.order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
                return list((await session.execute(statement)).scalars().all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _decode_review_nonce(token: str) -> str:
    import base64

    body = token.rpartition(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")).decode("utf-8"))
    return str(payload["review"]["nonce"])


def _new_review_token(
    client: TestClient,
    env: dict[str, Any],
    *,
    recipient: str = "ops-215-sink@example.invalid",
) -> tuple[str, str, str]:
    csrf = _page_csrf(client, "/admin/email-operations/smtp-test")
    response = client.post(
        "/admin/email-operations/smtp-test/review",
        data={
            "csrf_token": csrf,
            "recipient": recipient,
            "subject": "215 native SMTP test",
            "body": "215 native SMTP test body.\nLine two.",
        },
    )
    assert response.status_code == 200
    token = REVIEW_TOKEN_RE.search(response.text).group(1)
    # ORIGINAL review CSRF: every apply / repeat / concurrent submit of
    # THIS token reuses this exact value.  A fresh GET per apply would
    # ROTATE the session CSRF and race parallel submissions (each page
    # GET rotates once; the POST apply itself never rotates).
    review_csrf = CSRF_RE.search(response.text).group(1)
    return token, _decode_review_nonce(token), review_csrf


def _apply_token(client: TestClient, token: str, csrf: str, *, confirm: bool = True) -> Any:
    data: dict[str, str] = {"csrf_token": csrf, "review_token": token}
    if confirm:
        data["confirm_send_test"] = "true"
    response = client.post("/admin/email-operations/smtp-test/apply", data=data, follow_redirects=False)
    # The INTENDED guard must be reached - never an auth rejection
    # (303 -> /admin/login) or a CSRF rejection (400 "Invalid CSRF").
    assert response.status_code == 200, (
        f"apply must reach the guard page, got HTTP {response.status_code}"
    )
    assert "/admin/login" not in response.headers.get("location", "")
    return response


# ---- SMTP test: real sink acceptance + sanitized durable audit -------------


def test_smtp_test_real_sink_acceptance_and_sanitized_audit(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    before = len(sink.messages)

    response = client.get("/admin/email-operations/smtp-test")
    assert response.status_code == 200
    assert "Cooldown: at most 3 test attempts per 60 seconds" in response.text

    token, nonce, review_csrf = _new_review_token(client, env215)
    response = _apply_token(client, token, review_csrf)
    assert "accepted by the configured SMTP service" in response.text
    assert 'name="review_token"' not in response.text  # one-use: token consumed

    # Exactly ONE message reached the loopback sink, to the reviewed
    # recipient, through the server-configured transport (no real auth).
    assert len(sink.messages) == before + 1
    envelope = sink.messages[-1]
    assert envelope["rcpt_to"] == ["ops-215-sink@example.invalid"]
    assert envelope["mail_from"] == "noreply-215@example.org"
    assert "215 native SMTP test" in envelope["data"]

    # Durable sanitized audit: the ONE-USE identity is the bound
    # entity_id column (UUID(hex=nonce)) - the nonce string itself never
    # reaches metadata (a nonce-named key would be masked to ***).
    claims = _audit_rows(env215["database_url"], action=SMTP_TEST_CLAIM_ACTION)
    results = _audit_rows(env215["database_url"], action=SMTP_TEST_RESULT_ACTION)
    expected_entity = uuid.UUID(hex=nonce)
    assert [row.entity_id for row in claims] == [expected_entity]
    assert [row.entity_id for row in results] == [expected_entity]
    for row in claims + results:
        assert row.entity_type == SMTP_TEST_ENTITY_TYPE
        assert row.admin_user_id == env215["admin_id"]
        assert "intent_nonce" not in row.new_values
        # old_values is legitimately NULL for these append-only events.
        assert "intent_nonce" not in (row.old_values or {})
    assert claims[0].new_values == {"result": "claimed"}
    assert results[0].new_values == {"result": "accepted"}

    # The durable claim lookup by the ORIGINAL nonce identity matches
    # (the sanitizer cannot break this identity: it is a bound column).
    async def _lookup() -> bool:
        engine = _engine(env215["database_url"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                row = await AuditRepository(session).get_smtp_test_claim(
                    admin_user_id=env215["admin_id"], intent_nonce=nonce
                )
                return row is not None and row.entity_id == expected_entity
        finally:
            await engine.dispose()

    assert asyncio.run(_lookup()) is True


def test_smtp_test_duplicate_same_intent_never_resends(env215: dict[str, Any]) -> None:
    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    before = len(sink.messages)

    token, _nonce, review_csrf = _new_review_token(client, env215)
    first = _apply_token(client, token, review_csrf)
    assert "accepted by the configured SMTP service" in first.text
    assert len(sink.messages) == before + 1

    # Same reviewed intent, second submit: one-use refusal, no message
    # (same ORIGINAL review CSRF - no re-GET between submits).
    second = _apply_token(client, token, review_csrf)
    assert "already used" in second.text
    assert len(sink.messages) == before + 1
    # The claim/budget stay consumed; the token is not re-rendered.
    assert 'name="review_token"' not in second.text


def _claim_lock_contention_probe(database_url: str) -> None:
    """Deterministic REAL actor-lock contention at the claim seam.

    Session A holds the admin-user row FOR UPDATE (the exact lock the
    one-use claim takes for the whole check-insert-commit).  A real
    ``claim_smtp_test_attempt`` in a second session must ACTUALLY block
    on it (observed by elapsed time), then serialize behind A and be
    refused by the committed duplicate check - proving the one-use
    guard is a real row-lock race, not a timing coincidence.  A fresh
    admin + fresh nonce keep this isolated from the per-actor budget
    oracle the later tests rely on.
    """
    holder = _create_extra_admin(database_url)
    admin_id = holder["id"]
    nonce = uuid.uuid4().hex[:32]
    entity = uuid.UUID(hex=nonce)
    acquired = threading.Event()
    release = threading.Event()

    def _holder() -> None:
        async def _run() -> None:
            engine = _engine(database_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    async with session.begin():
                        await session.execute(
                            text("SELECT id FROM admin_users WHERE id = :id FOR UPDATE"),
                            {"id": admin_id},
                        )
                        acquired.set()
                        assert release.wait(timeout=60), "holder release timed out"
                        # The winner's committed claim becomes visible
                        # when this commit releases the row lock.
                        await AuditRepository(session).add_audit_log(
                            action=SMTP_TEST_CLAIM_ACTION,
                            entity_type=SMTP_TEST_ENTITY_TYPE,
                            entity_id=entity,
                            admin_user_id=admin_id,
                            new_values={"result": "claimed"},
                        )
            finally:
                await engine.dispose()

        asyncio.run(_run())

    claim_box: dict[str, Any] = {}

    def _claiming() -> None:
        async def _run() -> None:
            engine = _engine(database_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            start = time.monotonic()
            try:
                try:
                    async with factory() as session:
                        await claim_smtp_test_attempt(
                            session=session,
                            admin_users_repository=AdminUsersRepository(session),
                            audit_repository=AuditRepository(session),
                            actor_admin_id=admin_id,
                            intent_nonce=nonce,
                        )
                    claim_box["outcome"] = "no-error"
                except BaseException as exc:  # recorded, asserted below
                    claim_box["outcome"] = type(exc).__name__
                    claim_box["elapsed"] = time.monotonic() - start
            finally:
                await engine.dispose()

        asyncio.run(_run())

    holder_thread = threading.Thread(target=_holder, daemon=True)
    holder_thread.start()
    assert acquired.wait(timeout=60), "holder never acquired the actor row lock"

    claim_thread = threading.Thread(target=_claiming, daemon=True)
    claim_thread.start()
    time.sleep(0.6)
    assert claim_thread.is_alive(), (
        "claim did not block on the held actor row lock (no real contention)"
    )

    release.set()
    holder_thread.join(timeout=60)
    claim_thread.join(timeout=60)
    assert not holder_thread.is_alive() and not claim_thread.is_alive()
    assert claim_box.get("outcome") == SmtpTestIntentAlreadyClaimedError.__name__, claim_box
    # It genuinely waited on the lock before serializing behind the
    # winner (an unblocked duplicate refusal would finish in <0.4s).
    assert claim_box.get("elapsed", 0.0) >= 0.4, claim_box

    # Exactly ONE durable claim (the holder's); the serialized loser
    # added nothing.
    claims = _audit_rows(database_url, action=SMTP_TEST_CLAIM_ACTION, entity_id=entity)
    assert [str(row.admin_user_id) for row in claims] == [str(admin_id)]


def test_smtp_test_concurrent_same_intent_at_most_one_message(env215: dict[str, Any]) -> None:
    from concurrent.futures import ThreadPoolExecutor

    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    before = len(sink.messages)

    token, nonce, review_csrf = _new_review_token(client, env215)

    # Controlled two-session claim seam: both sessions submit the SAME
    # ORIGINAL review CSRF and the same one-use token; the actor-row
    # lock + committed claim serialize them - exactly one claim
    # survives.  The deterministic row-lock contention proof follows.
    def _apply() -> str:
        return _apply_token(client, token, review_csrf).text

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(pool.map(lambda _i: _apply(), range(2)))

    # Exactly ONE attempted message and ONE durable claim row.
    assert len(sink.messages) == before + 1
    accepted = sum(1 for page in pages if "accepted by the configured SMTP service" in page)
    refused = sum(1 for page in pages if "already used" in page)
    assert accepted + refused == 2
    assert accepted == 1
    claims = _audit_rows(env215["database_url"], action=SMTP_TEST_CLAIM_ACTION)
    assert sum(1 for row in claims if row.entity_id == uuid.UUID(hex=nonce)) == 1

    _claim_lock_contention_probe(env215["database_url"])


def test_smtp_test_budget_cooldown_after_three_attempts(env215: dict[str, Any]) -> None:
    # Attempted so far (file order): 1 + 2 (duplicate test) + 1
    # (concurrent test) = 4 committed claims in this 60s window - the
    # per-actor 3/60s budget must now refuse with the fixed cooldown.
    client: TestClient = env215["client"]
    sink: LocalMockSmtpSink = env215["sink"]
    before = len(sink.messages)

    token, _nonce, review_csrf = _new_review_token(client, env215)
    response = _apply_token(client, token, review_csrf)
    assert "cooldown" in response.text.lower()
    assert len(sink.messages) == before
    assert 'name="review_token"' not in response.text


# ---- SMTP test: controlled fault seams (native sessionmaker) ---------------


class _CommitFailingSessionmaker:
    """Fails the app's real sessionmaker at a NAMED commit phase.

    Phase identification (pure REAL SQLAlchemy behavior, probed):
    ``AuditRepository.add_audit_log`` FLUSHES before returning, so the
    claim/result audit row does not sit in ``session.new`` at commit
    time (and ``AsyncSession`` does not even proxy the sync
    ``pending`` collection), and ``AsyncSession.begin().__aexit__``
    does not call the public ``AsyncSession.commit`` override.  The
    seam therefore wraps the real ``session.add`` (test-only, in
    fixture sessions only) and records the added audit row's action in
    a stable ``session.info`` phase marker; the commit wrapper reads
    that marker - never a blind commit count - and identifies exactly
    one of the two public commits a native apply request issues: the
    one-use CLAIM commit or the RESULT commit.

    test="pre-commit": RAISES BEFORE the real commit - the write rolls
    back and durability is unconfirmed (the page must say
    "could not be confirmed", never "was not durable").
    test="ack-loss": the real commit COMPLETES (the write is durable)
    and THEN the seam raises - a lost-ack simulation: the client saw a
    failure although the commit landed.
    """

    def __init__(self, inner: Any, *, fail_phase: str, test: str = "pre-commit") -> None:
        assert fail_phase in {"claim", "result"}
        self.inner = inner
        self.fail_phase = fail_phase
        self.test = test
        self.hit = False
        self.ack_loss_committed = False

    def __call__(self) -> Any:
        session = self.inner()
        inner_commit = session.commit
        inner_add = session.add

        def add(obj: Any) -> None:
            # Test-only phase marker: which named audit action is this
            # session about to commit? (The flushed row is gone from
            # pending/new by commit time, so the marker is read at
            # commit time from session.info, which survives the flush.)
            action = getattr(obj, "action", None)
            if action == SMTP_TEST_CLAIM_ACTION:
                session.info["215_fault_phase"] = "claim"
            elif action == SMTP_TEST_RESULT_ACTION:
                session.info["215_fault_phase"] = "result"
            inner_add(obj)

        async def commit() -> None:
            phase = session.info.get("215_fault_phase", "other")
            if phase == self.fail_phase:
                self.hit = True
                if self.test == "ack-loss":
                    await inner_commit()
                    self.ack_loss_committed = True
                    raise RuntimeError("ack-loss fault seam (fixture)")
                raise RuntimeError("pre-commit fault seam (fixture)")
            return await inner_commit()

        session.add = add
        session.commit = commit
        return session


def test_smtp_test_claim_fault_dispatches_nothing(env215: dict[str, Any]) -> None:
    sink: LocalMockSmtpSink = env215["sink"]
    before = len(sink.messages)
    app = env215["app"]

    # (a) PRE-COMMIT fault: the CLAIM-phase commit RAISES BEFORE the
    # real commit, so nothing is durable.  The handler must never
    # dispatch and must phrase durability as UNCONFIRMED (never "was
    # not durable").  A FRESH admin keeps the seam proof isolated from
    # the per-actor budget oracle (the main admin already has 4
    # in-window claims).
    admin2 = _create_extra_admin(env215["database_url"])
    client: TestClient = env215["client"]
    # One TestClient portal per app: the app's async engine is bound to
    # the context-managed client's loop, so a SECOND bare TestClient
    # would hit "attached to a different loop" (the login handler's
    # RuntimeError -> 503).  Switch the SAME client to the fresh admin
    # via a cookie-jar swap (the main admin's tests are complete).
    client.cookies.clear()
    _login(client, {"admin_email": admin2["email"]})

    token, nonce, review_csrf = _new_review_token(client, env215, recipient="ops-215-claim-fault@example.invalid")
    original = app.state.db_sessionmaker
    seam = _CommitFailingSessionmaker(original, fail_phase="claim")
    try:
        app.state.db_sessionmaker = seam
        response = _apply_token(client, token, review_csrf)
    finally:
        app.state.db_sessionmaker = original
    assert seam.hit  # the claim-phase commit was really intercepted
    assert "recording could not be confirmed before sending" in response.text
    # No SMTP call, no claim row (the pre-commit fault rolled back),
    # no result row, no raw fault prose.
    assert len(sink.messages) == before
    claims = _audit_rows(env215["database_url"], action=SMTP_TEST_CLAIM_ACTION)
    assert not any(row.entity_id == uuid.UUID(hex=nonce) for row in claims)
    results = _audit_rows(env215["database_url"], action=SMTP_TEST_RESULT_ACTION)
    assert not any(row.entity_id == uuid.UUID(hex=nonce) for row in results)
    assert "fault seam" not in response.text
    assert 'name="review_token"' not in response.text

    # (b) ACK-LOSS mode: the claim commit REALLY COMPLETES (durable)
    # and only then does the seam raise - a lost ack.  Even so: no
    # dispatch (no SMTP call), the page stays unconfirmed, the durable
    # claim SURVIVES, and a repeat of the same token is refused by it
    # (no duplicate) - not an assumed rollback.
    admin4 = _create_extra_admin(env215["database_url"])
    client.cookies.clear()
    _login(client, {"admin_email": admin4["email"]})

    token2, nonce2, review_csrf2 = _new_review_token(client, env215, recipient="ops-215-ack-loss@example.invalid")
    entity2 = uuid.UUID(hex=nonce2)
    seam2 = _CommitFailingSessionmaker(original, fail_phase="claim", test="ack-loss")
    try:
        app.state.db_sessionmaker = seam2
        response = _apply_token(client, token2, review_csrf2)
    finally:
        app.state.db_sessionmaker = original
    assert seam2.hit and seam2.ack_loss_committed, "the ack-loss commit must have really executed"
    assert "recording could not be confirmed before sending" in response.text
    assert "fault seam" not in response.text
    assert len(sink.messages) == before  # still NO SMTP call
    # The claim is DURABLE despite the lost ack.
    claims = _audit_rows(env215["database_url"], action=SMTP_TEST_CLAIM_ACTION)
    assert sum(1 for row in claims if row.entity_id == entity2) == 1
    results = _audit_rows(env215["database_url"], action=SMTP_TEST_RESULT_ACTION)
    assert not any(row.entity_id == entity2 for row in results)
    # Repeat the SAME token: the durable claim refuses it - no second
    # message (a lost ack is never permission to send again).
    repeat = _apply_token(client, token2, review_csrf2)
    assert "already used" in repeat.text
    assert len(sink.messages) == before
    assert 'name="review_token"' not in repeat.text


def test_smtp_test_result_fault_keeps_truthful_acceptance_and_claim(env215: dict[str, Any]) -> None:
    sink: LocalMockSmtpSink = env215["sink"]
    before = len(sink.messages)
    app = env215["app"]

    admin3 = _create_extra_admin(env215["database_url"])
    client: TestClient = env215["client"]
    client.cookies.clear()
    _login(client, {"admin_email": admin3["email"]})

    token, nonce, review_csrf = _new_review_token(client, env215, recipient="ops-215-result-fault@example.invalid")
    original = app.state.db_sessionmaker
    seam = _CommitFailingSessionmaker(original, fail_phase="result")
    try:
        # The CLAIM-phase commit succeeds; the RESULT-phase commit
        # fails PRE-commit (the result rolls back).
        app.state.db_sessionmaker = seam
        response = _apply_token(client, token, review_csrf)
    finally:
        app.state.db_sessionmaker = original
    assert seam.hit  # the result-phase commit was really intercepted
    # The acceptance stays truthfully shown...
    assert "accepted by the configured SMTP service" in response.text
    # ...with the record-unconfirmed note (never a rollback/no-message
    # promise), and exactly ONE message was attempted.
    assert "Result recording UNCONFIRMED" in response.text
    assert len(sink.messages) == before + 1
    assert "fault seam" not in response.text

    # The claim is Durable (claim/budget stay consumed); the result row
    # is absent.
    claims = _audit_rows(env215["database_url"], action=SMTP_TEST_CLAIM_ACTION)
    assert sum(1 for row in claims if row.entity_id == uuid.UUID(hex=nonce)) == 1
    results = _audit_rows(env215["database_url"], action=SMTP_TEST_RESULT_ACTION)
    assert not any(row.entity_id == uuid.UUID(hex=nonce) for row in results)

    # Repeat the SAME intent: the durable claim refuses it - no second
    # message (a lost result is never permission to send again).
    before2 = len(sink.messages)
    repeat = _apply_token(client, token, review_csrf)
    assert "already used" in repeat.text
    assert len(sink.messages) == before2


def _create_extra_admin(database_url: str) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    admin = await AdminUsersRepository(session).create_admin_user(
                        email=f"gui215-extra-{uuid.uuid4()}@example.org",
                        display_name="215 Fault Seam Admin",
                        password_hash=hash_admin_password(ADMIN_PASSWORD),
                        role="admin",
                        is_active=True,
                    )
                    return {"email": admin.email, "id": admin.id}
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_smtp_test_disabled_readiness_refuses(env215: dict[str, Any]) -> None:
    # A second app over the SAME owned PG with delivery disabled: the
    # form shows the unavailable state and review is refused (400).
    settings = _settings(env215["database_url"], smtp_port=int(env215["sink"].port))
    settings = Settings(**{**settings.model_dump(), "ENABLE_EMAIL_DELIVERY": False})
    app = create_app(settings)
    # Separate app over the SAME owned PG: its OWN lifespan-managed
    # client (independent of the main app's sessionmaker lifecycle).
    with TestClient(app) as client:
        _login(client, {"admin_email": env215["admin_email"]})

        response = client.get("/admin/email-operations/smtp-test")
        assert response.status_code == 200
        assert "Email delivery is disabled" in response.text

        csrf = CSRF_RE.search(response.text).group(1)
        response = client.post(
            "/admin/email-operations/smtp-test/review",
            data={"csrf_token": csrf, "recipient": "ops-215@example.invalid"},
        )
        assert response.status_code == 400


# ---- preservation: policy/key/ledger state untouched by email ops ---------


def test_email_operations_preserve_policy_key_ledger_state(env215: dict[str, Any]) -> None:
    before = env215["preservation_before"]
    after = _preservation_snapshot(env215["database_url"])
    sentinel = env215["sentinel"]

    # One small LEGAL unrelated NONZERO sentinel (213/214 pattern): an
    # all-zero ledger/reservation state alone cannot prove
    # preservation - the nonzero sentinel key, reservation, and usage
    # ledger rows must survive byte-identical (full mapped-field
    # digests).
    assert (
        after["gateway_keys"][str(sentinel["gateway_key_id"])]
        == before["gateway_keys"][str(sentinel["gateway_key_id"])]
    )
    assert (
        after["quota_reservations"][str(sentinel["reservation_id"])]
        == before["quota_reservations"][str(sentinel["reservation_id"])]
    )
    assert before["usage_ledger"] == after["usage_ledger"]

    # Unrelated tables: identical ID sets and every pre-existing row
    # byte-identical (no key/policy/usage/reservation/owner changes
    # from any email operation).
    for table in ("gateway_keys", "quota_reservations", "owners"):
        assert set(after[table]) == set(before[table]), table
        for row_id, digest in before[table].items():
            assert after[table][row_id] == digest, f"{table}:{row_id} changed"

    # admin_users / audit_log: every pre-existing row invariant on ALL
    # mapped fields except the admin auth-tracking columns
    # (last_login_at/updated_at, legitimately touched by logins);
    # new rows allowed only for fixture-created actors and operation
    # audits.
    for row_id, digest in before["admin_users"].items():
        assert after["admin_users"].get(row_id) == digest, f"admin_users:{row_id} mutated"
    for row_id, digest in before["audit_log"].items():
        assert after["audit_log"].get(row_id) == digest, f"audit_log:{row_id} mutated"

    # Seeded delivery/secret families: NO new rows; only the
    # intentional selected rows may change (the send-now retry
    # advanced its own delivery row and consumed its own secret).
    allowed_secrets = {str(v) for v in env215["allowed_secret_ids"]}
    allowed_deliveries = {str(v) for v in env215["allowed_delivery_ids"]}
    for table, allowed in (
        ("one_time_secrets", allowed_secrets),
        ("email_deliveries", allowed_deliveries),
    ):
        assert set(after[table]) == set(before[table]), table
        for row_id, digest in before[table].items():
            if row_id in allowed:
                continue
            assert after[table][row_id] == digest, f"{table}:{row_id} changed"

    # The intended changes really happened (not a vacuous compare):
    # the retried failed delivery advanced and its secret was consumed.
    failed = env215["failed"]
    assert (
        after["email_deliveries"][str(failed["email_delivery_id"])]
        != before["email_deliveries"][str(failed["email_delivery_id"])]
    )
    assert (
        after["one_time_secrets"][str(failed["one_time_secret_id"])]
        != before["one_time_secrets"][str(failed["one_time_secret_id"])]
    )

