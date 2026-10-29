"""Real CLI + real service + real owned-PostgreSQL-16 evidence for 202-a.

Drives the ACTUAL CLI entrypoint (Typer app, real repositories/SQL) and
the ACTUAL EmailDeliveryService against a real disposable PostgreSQL 16
database.  SMTP and the Celery broker are FAKE (no real mail, no
Redis): the fake EmailService records rendered bodies, the fake task
records exact broker arguments, and an actual crypto hook counts real
``decrypt_secret`` invocations.

Proves: exact AND-combined list filters (owner email exact match, never
substring identity) applied in SQL before deterministic
``(created_at DESC, id DESC)`` paging of a 110-row batch with TIED
creation times (correct last page, honest has_more/next_offset); exact
show lifecycle/sendability projection and the safe historical audit
error code (exact target/type/action/time, id tie-breaker, unknown
latest code -> unavailable) with ZERO decrypt/render/send/queue and
byte/row-identical scoped state; actual sender actions (initial pending
send/queue, explicit failed retry with flag+reason, sent-repeat denied,
expired/consumed/sending/ambiguous/missing/foreign/secret-UUID-mismatch
denied without wrong-target mutation, omitted-selector and
alternative-retryable-row bypass denied, legitimate fresh no-ID,
SMTP-accepted-then-finalization-failure -> ambiguous that cannot be
resent); and a controlled blocking/current-state concurrency case using
real row locks with deterministic lock-wait observation (stale preflight
cannot authorize after the state changes while waiting).  Enqueue intent
audit semantics are proven too: intent committed BEFORE dispatch, audit
failure prevents dispatch, dispatch failure leaves only honest intent,
payload exactly the existing three UUIDs, ``queued`` distinct from the
persisted list status.

Ownership discipline mirrors the 198/199/200 owned fixtures: unique
owner label, loopback-bound, tmpfs-backed PostgreSQL 16, identity
inspected BEFORE readiness/migration, cleanup removes ONLY the exact
created container ID.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli import email as email_cli
from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import (
    AuditLog,
    EmailDelivery,
    GatewayKey,
    OneTimeSecret,
    Owner,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_errors import SmtpSendError
from slaif_gateway.services.email_service import EmailSendResult
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif202a"

_STATE: dict[str, str] = {}

_ENV_VARS = (
    "DATABASE_URL",
    "APP_ENV",
    "GATEWAY_KEY_PREFIX",
    "GATEWAY_KEY_ACCEPTED_PREFIXES",
    "ACTIVE_HMAC_KEY_VERSION",
    "TOKEN_HMAC_SECRET_V1",
    "ADMIN_SESSION_SECRET",
    "ONE_TIME_SECRET_ENCRYPTION_KEY",
    "ENABLE_EMAIL_DELIVERY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_FROM",
    "CELERY_BROKER_URL",
    "OPENAI_UPSTREAM_API_KEY",
    "OPENROUTER_API_KEY",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-email-inspection-202a"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-email-inspection-202a"

TIED_CREATED_AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
SYNTHETIC_STATUSES = ("pending", "sending", "sent", "failed", "ambiguous", "cancelled")

CANARY = "sk-slaif-canary202a00"

_runner = CliRunner()


# --- owned PostgreSQL 16 fixture (198/199/200 ownership discipline) ---------


def _inspect_owned(container, owner: str, container_port: int) -> int:
    container.reload()
    attrs = container.attrs
    labels = attrs["Config"].get("Labels") or {}
    assert labels.get(f"{_OWNER_PREFIX}.owner") == owner, "owned container label mismatch"
    host_config = attrs["HostConfig"] or {}
    tmpfs = host_config.get("Tmpfs") or {}
    assert "/var/lib/postgresql/data" in tmpfs, "owned PG tmpfs missing"
    configured = (host_config.get("PortBindings") or {}).get(f"{container_port}/tcp") or []
    assert configured and all(b.get("HostIp") == "127.0.0.1" for b in configured), (
        f"owned container must bind loopback, got: {configured}"
    )
    network_ports = (attrs["NetworkSettings"] or {}).get("Ports") or {}
    bound = network_ports.get(f"{container_port}/tcp") or []
    assert bound and all(b.get("HostIp") == "127.0.0.1" for b in bound), (
        f"owned container must publish on loopback, got: {bound}"
    )
    port = bound[0]["HostPort"]
    assert port, "owned container port binding missing"
    return int(port)


def _remove_owned(client, container, owner: str) -> str:
    import docker

    try:
        c = client.containers.get(container.id)
    except docker.errors.NotFound:
        return f"already_absent:{container.id[:12]}"
    c.reload()
    c_labels = c.attrs["Config"].get("Labels") or {}
    assert c_labels.get(f"{_OWNER_PREFIX}.owner") == owner, (
        "refusing to remove a container whose owner label changed"
    )
    c.stop(timeout=10)
    c.remove(force=True)
    return f"removed:{container.id[:12]}"


@pytest.fixture(scope="module")
def owned_pg_url() -> Iterator[str]:
    """One NEW owned, labeled, loopback-bound, tmpfs-backed PostgreSQL 16."""
    import docker

    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    container = None
    owner = f"{_OWNER_PREFIX}-{uuid.uuid4().hex}"
    try:
        container = client.containers.run(
            "postgres:16",
            environment={
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "POSTGRES_DB": "test",
            },
            ports={5432: ("127.0.0.1", None)},
            labels={f"{_OWNER_PREFIX}.owner": owner},
            tmpfs={"/var/lib/postgresql/data": "rw"},
            detach=True,
        )
        _STATE["pg_container"] = container.id
        _STATE["pg_owner"] = owner
        port = _inspect_owned(container, owner, 5432)

        async def _wait_ready() -> None:
            import asyncpg

            deadline = time.monotonic() + 90
            last: object = None
            while time.monotonic() < deadline:
                try:
                    conn = await asyncpg.connect(
                        f"postgresql://test:test@127.0.0.1:{port}/test", timeout=3
                    )
                    await conn.close()
                    return
                except Exception as exc:  # noqa: BLE001 - startup retry
                    last = exc
                    await asyncio.sleep(0.5)
            raise AssertionError(f"owned PG did not become ready: {last!r}")

        asyncio.run(_wait_ready())
        url = f"postgresql+asyncpg://test:test@127.0.0.1:{port}/test"
        run_alembic_upgrade_head(url)
        _STATE["pg_source"] = "owned"
        yield url
    finally:
        if container is not None:
            _STATE["pg_cleanup"] = _remove_owned(client, container, owner)


@pytest.fixture(scope="module")
def cli_env(owned_pg_url: str) -> str:
    """DATABASE_URL is ONLY the exact owned fictional database."""
    saved = {name: os.environ.get(name) for name in _ENV_VARS}
    os.environ["DATABASE_URL"] = owned_pg_url
    os.environ["APP_ENV"] = "test"
    os.environ["GATEWAY_KEY_PREFIX"] = "sk-slaif-"
    os.environ["GATEWAY_KEY_ACCEPTED_PREFIXES"] = "sk-slaif-"
    os.environ["ACTIVE_HMAC_KEY_VERSION"] = "1"
    os.environ["TOKEN_HMAC_SECRET_V1"] = TEST_HMAC_SECRET
    os.environ["ADMIN_SESSION_SECRET"] = TEST_ADMIN_SECRET
    os.environ["ONE_TIME_SECRET_ENCRYPTION_KEY"] = generate_secret_key()
    os.environ["ENABLE_EMAIL_DELIVERY"] = "true"
    os.environ["SMTP_HOST"] = "localhost"
    os.environ["SMTP_FROM"] = "noreply@example.org"
    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/15"
    os.environ["OPENAI_UPSTREAM_API_KEY"] = "fake-openai-upstream-key"
    os.environ["OPENROUTER_API_KEY"] = "fake-openrouter-upstream-key"
    get_settings.cache_clear()
    try:
        yield owned_pg_url
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeEmailService.sent.clear()
    _FakeEmailService.failure = None
    _FakeEmailService.send_url = None
    _FakeEmailService.on_send = None
    monkeypatch.setattr(email_cli, "EmailService", _FakeEmailService)


# --- fakes (SMTP / Celery only) ---------------------------------------------


class _FakeEmailService:
    sent: list[dict[str, object]] = []
    failure: Exception | None = None
    # 202-b: optional DURING-ATTEMPT observation hook — a coroutine
    # callable ``(url, to)`` invoked at the START of every attempt, before
    # a recorded failure raises and before a successful send is recorded,
    # so a test can read the already-committed sending state from a FRESH
    # session for successful AND failed attempts alike. ``send_url``
    # carries the owned database URL into the hook.
    send_url: str | None = None
    on_send: object | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        if _FakeEmailService.on_send is not None:
            await _FakeEmailService.on_send(_FakeEmailService.send_url, to)  # type: ignore[misc]
        if _FakeEmailService.failure is not None:
            raise _FakeEmailService.failure
        _FakeEmailService.sent.append({"to": to, "subject": subject, "text_body": text_body})
        return EmailSendResult(
            message_id=f"<fake-{uuid.uuid4().hex[:8]}@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.raising = False
        self.intent_visible_before_dispatch: bool | None = None
        self.url: str | None = None
        self.expected: dict[str, object] | None = None

    def delay(self, *args):
        self.calls.append(args)
        if self.raising:
            raise ConnectionError("broker down 202a")
        if self.url is not None and self.expected is not None:
            self.intent_visible_before_dispatch = _run(
                _enqueue_intent_visible(
                    self.url,
                    one_time_secret_id=self.expected["one_time_secret_id"],
                    email_delivery_id=self.expected["email_delivery_id"],
                )
            )

        class _AsyncResult:
            id = "fake-task-202a"

        return _AsyncResult()


# --- session helpers ----------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _session_factory(url: str):
    return async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)


async def _create_owner(url: str, *, email: str | None = None) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            owner = await OwnersRepository(session).create_owner(
                name="Inspect",
                surname="Owner",
                email=email or f"inspect-{uuid.uuid4().hex}@example.org",
            )
            return owner.id


async def _create_admin(url: str) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-{uuid.uuid4().hex}@example.org",
                display_name="202a Admin",
                password_hash="argon2id-mock-hash-202a",
                role="admin",
            )
            return admin.id


def _create_key(url: str, owner_id: uuid.UUID, *, email_delivery: str | None = None, show_plaintext: bool = False) -> dict[str, object]:
    args = [
        "keys",
        "create",
        "--owner-id",
        str(owner_id),
        "--valid-from",
        "2026-06-01T00:00:00+00:00",
        "--valid-until",
        "2027-06-01T00:00:00+00:00",
        "--reason",
        "202a integration",
        "--allow-all-models",
        "--allow-all-endpoints",
        "--json",
    ]
    if email_delivery is not None:
        args += ["--email-delivery", email_delivery]
    # `keys create --json` requires an explicit key channel; pending/none
    # modes allow --show-plaintext (send-now/enqueue do not, and are not
    # used by this file).
    if show_plaintext or email_delivery in (None, "pending"):
        args.append("--show-plaintext")
    result = _runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


async def _set_fields(url: str, model, row_id: uuid.UUID, **fields) -> None:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            await session.execute(update(model).where(model.id == row_id).values(**fields))


async def _set_delivery(url: str, delivery_id: uuid.UUID, **fields) -> None:
    await _set_fields(url, EmailDelivery, delivery_id, **fields)


async def _set_secret(url: str, secret_id: uuid.UUID, **fields) -> None:
    await _set_fields(url, OneTimeSecret, secret_id, **fields)


async def _insert_delivery(
    url: str,
    *,
    row_id: uuid.UUID,
    owner_id: uuid.UUID,
    gateway_key_id: uuid.UUID,
    one_time_secret_id: uuid.UUID,
    recipient_email: str,
    status: str,
    created_at: datetime,
    subject: str = "Subject 202a",
) -> None:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            session.add(
                EmailDelivery(
                    id=row_id,
                    owner_id=owner_id,
                    gateway_key_id=gateway_key_id,
                    one_time_secret_id=one_time_secret_id,
                    recipient_email=recipient_email,
                    subject=subject,
                    template_name="gateway_key_email",
                    status=status,
                    created_at=created_at,
                    sent_at=created_at if status == "sent" else None,
                    failed_at=created_at if status in {"failed", "ambiguous"} else None,
                )
            )


async def _insert_audit(
    url: str,
    *,
    action: str,
    entity_id: uuid.UUID,
    new_values: dict[str, object],
    created_at: datetime | None = None,
    note: str | None = None,
    entity_type: str = "email_delivery",
    row_id: uuid.UUID | None = None,
) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            row = AuditLog(
                id=row_id or uuid.uuid4(),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                new_values=new_values,
                note=note,
                created_at=created_at or datetime.now(UTC),
            )
            session.add(row)
            await session.flush()
            return row.id


async def _audits(url: str, *, action: str | None = None, entity_id: uuid.UUID | None = None) -> list[AuditLog]:
    factory = _session_factory(url)
    async with factory() as session:
        stmt = select(AuditLog)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        stmt = stmt.order_by(AuditLog.created_at, AuditLog.id)
        rows = (await session.execute(stmt)).scalars().all()
        return list(rows)


async def _enqueue_intent_visible(
    url: str, *, one_time_secret_id: uuid.UUID, email_delivery_id: uuid.UUID | None
) -> bool:
    # Correlate the EXACT scoped intent row: persisted action + exact
    # entity id + the safe reference field ``one_time_reference_id``
    # (secret-bearing key names are dropped by the global durable
    # sanitizer; this event documents the safe reference instead).
    factory = _session_factory(url)
    async with factory() as session:
        row = (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.action == "email_key_enqueue_requested")
                .where(AuditLog.entity_id == email_delivery_id)
                .where(AuditLog.new_values["one_time_reference_id"].astext == str(one_time_secret_id))
            )
        ).scalar_one_or_none()
        return row is not None


async def _scoped_table_hashes(url: str) -> dict[str, str]:
    factory = _session_factory(url)
    tables: dict[str, str] = {}
    async with factory() as session:
        for model in (EmailDelivery, OneTimeSecret, GatewayKey, Owner, AuditLog, UsageLedger):
            rows = (await session.execute(select(model))).scalars().all()
            payload = json.dumps(
                [
                    {c.name: getattr(row, c.name) for c in model.__table__.columns}
                    for row in rows
                ],
                default=str,
                sort_keys=True,
            )
            tables[model.__tablename__] = hashlib.sha256(payload.encode()).hexdigest()
    return tables


async def _delivery_rows(url: str, *, gateway_key_id: uuid.UUID | None = None) -> list[EmailDelivery]:
    factory = _session_factory(url)
    async with factory() as session:
        stmt = select(EmailDelivery)
        if gateway_key_id is not None:
            stmt = stmt.where(EmailDelivery.gateway_key_id == gateway_key_id)
        return list((await session.execute(stmt)).scalars().all())


async def _get_secret(url: str, secret_id: uuid.UUID) -> OneTimeSecret:
    factory = _session_factory(url)
    async with factory() as session:
        row = await session.get(OneTimeSecret, secret_id)
        assert row is not None
        return row


async def _send_via_service(
    url: str,
    *,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID | None = None,
    actor_admin_id: uuid.UUID | None = None,
    reason: str | None = None,
    decrypt_guard: dict[str, int] | None = None,
):
    """Run the ACTUAL EmailDeliveryService (fake SMTP) on the owned PG."""
    import slaif_gateway.services.secret_service as secret_service_module

    original = secret_service_module.decrypt_secret

    def counting_decrypt(*args, **kwargs):
        if decrypt_guard is not None:
            decrypt_guard["calls"] += 1
        return original(*args, **kwargs)

    secret_service_module.decrypt_secret = counting_decrypt
    factory = _session_factory(url)
    try:
        async with factory() as session:
            service = EmailDeliveryService(
                settings=get_settings(),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                email_deliveries_repository=EmailDeliveriesRepository(session),
                gateway_keys_repository=GatewayKeysRepository(session),
                owners_repository=OwnersRepository(session),
                audit_repository=AuditRepository(session),
                email_service=_FakeEmailService(),
                session=session,
            )
            return await service.send_pending_key_email(
                one_time_secret_id=one_time_secret_id,
                email_delivery_id=email_delivery_id,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
    finally:
        secret_service_module.decrypt_secret = original


def _invoke_email(args: list[str]):
    return _runner.invoke(app, ["email", *args])



# --- A: exact filters + deterministic paging over a 110-row tied batch ------
#
# Batch composition (known IDs, explained exactly): 4 hero deliveries
# created by the ACTUAL CLI `keys create --email-delivery pending` (two for
# owner o1, one for o2, one for o3) plus 106 directly inserted synthetic
# rows bound to the real o3 key/secret UUIDs. Every row carries the SAME
# created_at (TIED_CREATED_AT), so the deterministic (created_at DESC, id
# DESC) order reduces to UUID DESC and paging is exact.


def _list_page(*args: str) -> dict[str, object]:
    result = _invoke_email(["list", "--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_list_exact_filters_and_tied_paging(cli_env: str) -> None:
    url = cli_env
    # Mixed owners with OVERLAPPING email substrings: filtering by
    # "b@example.org" must never match owner "a.b@example.org".
    o1 = _run(_create_owner(url, email="a.b@example.org"))
    o2 = _run(_create_owner(url, email="b@example.org"))
    o3 = _run(_create_owner(url, email="ada@example.org"))

    k1a = _create_key(url, o1, email_delivery="pending")
    k1b = _create_key(url, o1, email_delivery="pending")
    k2 = _create_key(url, o2, email_delivery="pending")
    k3 = _create_key(url, o3, email_delivery="pending")
    d1a = uuid.UUID(k1a["email_delivery_id"])
    d1b = uuid.UUID(k1b["email_delivery_id"])
    d2 = uuid.UUID(k2["email_delivery_id"])
    d3 = uuid.UUID(k3["email_delivery_id"])
    _run(_set_delivery(url, d1a, created_at=TIED_CREATED_AT))
    _run(_set_delivery(url, d1b, created_at=TIED_CREATED_AT))
    _run(_set_delivery(url, d2, created_at=TIED_CREATED_AT))
    _run(_set_delivery(url, d3, status="sent", sent_at=TIED_CREATED_AT, created_at=TIED_CREATED_AT))

    # 106 synthetic rows (known pre-generated IDs) on the real o3 key/secret.
    synth_ids = [uuid.uuid4() for _ in range(106)]
    synth_status = {sid: SYNTHETIC_STATUSES[i % 6] for i, sid in enumerate(synth_ids)}
    for sid in synth_ids:
        _run(
            _insert_delivery(
                url,
                row_id=sid,
                owner_id=o3,
                gateway_key_id=uuid.UUID(k3["gateway_key_id"]),
                one_time_secret_id=uuid.UUID(k3["one_time_secret_id"]),
                recipient_email="ada@example.org",
                status=synth_status[sid],
                created_at=TIED_CREATED_AT,
            )
        )

    all_ids = {d1a, d1b, d2, d3} | set(synth_ids)
    assert len(all_ids) == 110

    p1 = _list_page("--limit", "50")
    p2 = _list_page("--limit", "50", "--offset", "50")
    p3 = _list_page("--limit", "50", "--offset", "100")
    assert p1["has_more"] is True and p1["next_offset"] == 50
    assert p2["has_more"] is True and p2["next_offset"] == 100
    assert p3["has_more"] is False and p3["next_offset"] is None
    assert p1["limit"] == 50 and p1["offset"] == 0
    assert p3["offset"] == 100 and len(p3["items"]) == 10
    # Tied created_at => UUID DESC ordering; exact known-ID pages.
    assert [i["delivery_id"] for i in p1["items"]] == [str(x) for x in sorted(all_ids, reverse=True)[:50]]
    assert [i["delivery_id"] for i in p3["items"]] == [str(x) for x in sorted(all_ids, reverse=True)[100:]]
    got = [i["delivery_id"] for i in p1["items"] + p2["items"] + p3["items"]]
    assert len(got) == 110 and set(got) == {str(x) for x in all_ids}

    # Exact normalized owner email: NEVER a substring identity guess.
    for spelling in ("b@example.org", "B@example.ORG", "  b@example.org  "):
        f = _list_page("--owner-email", spelling)
        assert [i["delivery_id"] for i in f["items"]] == [str(d2)]

    f = _list_page("--owner-id", str(o1))
    assert {i["delivery_id"] for i in f["items"]} == {str(d1a), str(d1b)}

    # o3: 107 rows => 100 + 7 across pages (SQL filter BEFORE paging).
    f = _list_page("--owner-id", str(o3), "--limit", "100")
    assert len(f["items"]) == 100 and f["has_more"] is True and f["next_offset"] == 100
    f2 = _list_page("--owner-id", str(o3), "--limit", "100", "--offset", "100")
    assert len(f2["items"]) == 7 and f2["has_more"] is False

    f = _list_page("--key-id", str(k1b["gateway_key_id"]))
    assert [i["delivery_id"] for i in f["items"]] == [str(d1b)]

    # AND combination: exact owner + exact status.
    f = _list_page("--owner-id", str(o3), "--status", "failed")
    assert {i["delivery_id"] for i in f["items"]} == {
        str(sid) for sid in synth_ids if synth_status[sid] == "failed"
    }

    # Every persisted status filters to exactly its known rows.
    hero_by_status = {"pending": {d1a, d1b, d2}, "sent": {d3}}
    for status in ("pending", "sending", "sent", "failed", "ambiguous", "cancelled"):
        f = _list_page("--status", status, "--limit", "100")
        want = {str(sid) for sid in synth_ids if synth_status[sid] == status} | {
            str(x) for x in hero_by_status.get(status, set())
        }
        assert {i["delivery_id"] for i in f["items"]} == want, status
        assert f["has_more"] is False

    # Inclusive aware-UTC window: the tied batch is inside; +1s is outside.
    f = _list_page("--created-from", TIED_CREATED_AT.isoformat(), "--created-until", TIED_CREATED_AT.isoformat(), "--limit", "100")
    assert len(f["items"]) == 100 and f["has_more"] is True
    f = _list_page(
        "--created-from", (TIED_CREATED_AT + timedelta(seconds=1)).isoformat(), "--limit", "100"
    )
    assert f["items"] == [] and f["has_more"] is False

    # Readable text mode.
    t = _invoke_email(["list", "--limit", "3"])
    assert t.exit_code == 0
    first = t.stdout.splitlines()[0].split()
    assert first[0] in {str(x) for x in all_ids}
    assert "has_more: true" in t.stdout


def test_list_invalid_inputs_and_canaries_no_echo(cli_env: str) -> None:
    url = cli_env
    owner_id = _run(_create_owner(url))
    key = _create_key(url, owner_id, email_delivery="pending")
    key_delivery = uuid.UUID(key["email_delivery_id"])

    def neg(*args: str) -> tuple[int, str, dict[str, object]]:
        result = _invoke_email(["list", "--json", *args])
        assert result.exit_code == 1, (result.exit_code, result.output)
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "invalid_parameter", payload
        return result.exit_code, result.stdout, payload

    neg("--delivery-id", "not-a-uuid")
    neg("--status", "queued")
    neg("--status", "")
    neg("--created-from", "2026-01-01T00:00:00")  # naive: not an explicit aware UTC instant
    neg(
        "--created-from",
        "2026-02-01T00:00:00+00:00",
        "--created-until",
        "2026-01-01T00:00:00+00:00",
    )
    neg("--limit", "0")
    neg("--offset", "-1")
    neg("--limit", "101")
    neg("--limit", CANARY)
    neg("--offset", CANARY)
    neg("--owner-email", CANARY)
    neg("--delivery-id", CANARY)

    # A recognized credential canary never echoes on ANY page/filter input.
    for flag in ("--limit", "--offset", "--owner-email", "--delivery-id", "--status", "--created-from"):
        result = _invoke_email(["list", "--json", flag, CANARY])
        assert result.exit_code == 1
        assert CANARY not in result.stdout
        assert CANARY not in (result.stderr or "")

    # Missing (empty result) is distinct from invalid: exit 0, zero items.
    # (The store is NOT empty: this key's delivery is present.)
    f = _list_page("--key-id", str(key["gateway_key_id"]))
    assert [i["delivery_id"] for i in f["items"]] == [str(key_delivery)]
    f = _list_page("--delivery-id", str(uuid.uuid4()))
    assert f["items"] == [] and f["has_more"] is False
    f = _list_page("--owner-email", "nobody@nowhere.example")
    assert f["items"] == []
    # Credential-like input in the (valid-shaped) owner email filter returns
    # zero rows without echoing the value.
    result = _invoke_email(["list", "--json", "--owner-email", "sk-slaif-c0ffee@x.example"])
    assert result.exit_code == 0
    assert "sk-slaif-c0ffee" not in result.stdout
    assert json.loads(result.stdout)["items"] == []


# --- B: lifecycle, sendability, and historical audit projection -------------


def test_show_lifecycle_sendability_and_historical_audit(cli_env: str) -> None:
    url = cli_env
    now = datetime.now(UTC)
    owner_a = _run(_create_owner(url))
    owner_b = _run(_create_owner(url))

    k_present = _create_key(url, owner_a, email_delivery="pending")
    k_consumed = _create_key(url, owner_a, email_delivery="pending")
    k_expired = _create_key(url, owner_a, email_delivery="pending")
    k_unavailable = _create_key(url, owner_a, email_delivery="pending")
    k_mismatched = _create_key(url, owner_a, email_delivery="pending")
    k_other = _create_key(url, owner_b, email_delivery="pending")  # foreign valid secret
    k_sent_hist = _create_key(url, owner_a, email_delivery="pending")
    k_unknown = _create_key(url, owner_a, email_delivery="pending")
    k_ambiguous = _create_key(url, owner_a, email_delivery="pending")
    k_distractor = _create_key(url, owner_b, email_delivery="pending")

    _run(
        _set_secret(
            url,
            uuid.UUID(k_consumed["one_time_secret_id"]),
            status="consumed",
            consumed_at=now,
        )
    )
    _run(
        _set_secret(
            url,
            uuid.UUID(k_expired["one_time_secret_id"]),
            expires_at=now - timedelta(hours=1),
        )
    )
    _run(_set_delivery(url, uuid.UUID(k_unavailable["email_delivery_id"]), one_time_secret_id=None))
    _run(
        _set_delivery(
            url,
            uuid.UUID(k_mismatched["email_delivery_id"]),
            one_time_secret_id=uuid.UUID(k_other["one_time_secret_id"]),
        )
    )

    # sent + historical failure: two tied email_key_failed rows (id tie-break),
    # plus distractors that exact matching MUST exclude (foreign delivery,
    # non-failed action, wrong entity type, and a LATER row on another
    # delivery).
    sent_d = uuid.UUID(k_sent_hist["email_delivery_id"])
    _run(_set_delivery(url, sent_d, status="sent", sent_at=now))
    old_audit_id = uuid.uuid4()
    new_audit_id = old_audit_id
    while new_audit_id <= old_audit_id:
        new_audit_id = uuid.uuid4()
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=sent_d,
            new_values={"error_code": "smtp_send_error", "status": "failed"},
            created_at=now,
            row_id=old_audit_id,
        )
    )
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=sent_d,
            new_values={"error_code": "email_delivery_finalization_failed", "status": "failed"},
            created_at=now,
            row_id=new_audit_id,
        )
    )
    other_d = uuid.UUID(k_unknown["email_delivery_id"])
    distractor_d = uuid.UUID(k_distractor["email_delivery_id"])
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=distractor_d,
            new_values={"error_code": "smtp_configuration_error"},
            created_at=now,
        )
    )
    _run(
        _insert_audit(
            url,
            action="email_key",
            entity_id=sent_d,
            new_values={"error_code": "smtp_send_error", "status": "sent"},
            created_at=now,
        )
    )
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=sent_d,
            entity_type="gateway_key",
            new_values={"error_code": "smtp_send_error"},
            created_at=now,
        )
    )
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=distractor_d,
            new_values={"error_code": "smtp_send_error"},
            created_at=now + timedelta(seconds=5),  # ahead in time, other target
        )
    )

    # unknown latest code => unavailable (not guessed, not an older entry).
    _run(_set_delivery(url, other_d, status="failed", failed_at=now))
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=other_d,
            new_values={"error_code": "totally_unknown_code_202a"},
            created_at=now,
        )
    )
    amb_d = uuid.UUID(k_ambiguous["email_delivery_id"])
    _run(_set_delivery(url, amb_d, status="ambiguous", failed_at=now))
    _run(
        _insert_audit(
            url,
            action="email_key_ambiguous",
            entity_id=amb_d,
            new_values={"error_code": "email_delivery_finalization_failed", "status": "ambiguous"},
            created_at=now,
        )
    )

    def show(delivery_id: str) -> dict[str, object]:
        result = _invoke_email(["show", delivery_id, "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert "subject" not in payload
        assert "body" not in payload
        assert "error_message" not in payload
        return payload

    p = show(k_present["email_delivery_id"])
    assert p["status"] == "pending"
    assert p["one_time_secret"] == {"status": "present", "can_send": True, "blocking_reason": None}
    assert "last_recorded_failure" not in p

    p = show(k_consumed["email_delivery_id"])
    assert p["one_time_secret"]["status"] == "consumed"
    assert p["one_time_secret"]["can_send"] is False
    assert p["one_time_secret"]["blocking_reason"]

    p = show(k_expired["email_delivery_id"])
    assert p["one_time_secret"]["status"] == "expired"
    assert p["one_time_secret"]["can_send"] is False

    p = show(k_unavailable["email_delivery_id"])
    assert p["one_time_secret"]["status"] == "unavailable"
    assert p["one_time_secret"]["can_send"] is False

    p = show(k_mismatched["email_delivery_id"])
    assert p["one_time_secret"]["can_send"] is False
    assert "does not match" in (p["one_time_secret"]["blocking_reason"] or "")

    p = show(k_sent_hist["email_delivery_id"])
    assert p["status"] == "sent"
    assert p["one_time_secret"]["status"] == "present"
    assert p["one_time_secret"]["can_send"] is False
    # Historical (labeled by provenance), exact tied id tie-breaker wins.
    failure = p["last_recorded_failure"]
    assert failure["error_code"] == "email_delivery_finalization_failed"
    assert failure["action"] == "email_key_failed"
    assert failure["provenance"] == "last recorded audit error"
    assert datetime.fromisoformat(str(failure["recorded_at"])) == now

    p = show(k_unknown["email_delivery_id"])
    assert p["status"] == "failed"
    assert p["last_recorded_failure"]["error_code"] == "unavailable"
    assert p["last_recorded_failure"]["action"] == "email_key_failed"
    assert p["last_recorded_failure"]["provenance"] == "last recorded audit error"

    p = show(k_ambiguous["email_delivery_id"])
    assert p["status"] == "ambiguous"
    failure = p["last_recorded_failure"]
    assert failure["error_code"] == "email_delivery_finalization_failed"
    assert failure["action"] == "email_key_ambiguous"
    assert failure["provenance"] == "last recorded audit error"
    assert datetime.fromisoformat(str(failure["recorded_at"])) == now

    # Exact missing UUID is distinct from store unavailable.
    missing = _invoke_email(["show", str(uuid.uuid4()), "--json"])
    assert missing.exit_code == 1
    assert json.loads(missing.stdout)["error"]["code"] == "delivery_not_found"


# --- B: read-only inspection causes zero side effects ------------------------


def test_show_list_read_only_zero_side_effects(cli_env: str) -> None:
    url = cli_env
    owner_id = _run(_create_owner(url))
    key = _create_key(url, owner_id, email_delivery="pending", show_plaintext=True)
    delivery_id = uuid.UUID(key["email_delivery_id"])
    secret_id = uuid.UUID(key["one_time_secret_id"])
    secret = _run(_get_secret(url, secret_id))

    # Plant canaries that inspection output must never display.
    _run(
        _set_delivery(
            url,
            delivery_id,
            subject="SubjectCanary202a",
            error_message=f"ErrorProseCanary202a key={CANARY}",
        )
    )
    _run(
        _insert_audit(
            url,
            action="email_key_failed",
            entity_id=delivery_id,
            new_values={"error_code": "smtp_send_error", "leak": "AuditProseCanary202a"},
        )
    )

    before = _run(_scoped_table_hashes(url))
    assert _FakeEmailService.sent == []

    outputs: list[str] = []
    for args in (
        ["list", "--json"],
        ["list", "--status", "pending", "--limit", "100", "--json"],
        ["list", "--owner-email", "inspect-x@example.org", "--json"],
        ["show", str(delivery_id), "--json"],
        ["show", str(uuid.uuid4()), "--json"],
        ["list"],
    ):
        result = _invoke_email(args)
        outputs.append(result.stdout)
        outputs.append(result.stderr or "")

    after = _run(_scoped_table_hashes(url))
    assert before == after, "read-only inspection must leave all scoped rows byte/row-identical"
    assert _FakeEmailService.sent == []

    for out in outputs:
        for canary in (
            "SubjectCanary202a",
            "ErrorProseCanary202a",
            "AuditProseCanary202a",
            CANARY,
            key["plaintext_key"],  # type: ignore[index]
            secret.encrypted_payload,
            secret.nonce,
        ):
            assert canary not in out, canary[:18]


# --- C: actual sender actions against owned PG (fake SMTP/broker) ------------


def test_actions_send_retry_and_refusals(cli_env: str) -> None:
    url = cli_env
    admin_id = _run(_create_admin(url))
    owner_a = _run(_create_owner(url))
    owner_b = _run(_create_owner(url))
    now = datetime.now(UTC)

    # 1. Initial pending send-now: fake SMTP records the body, key consumed once.
    k1 = _create_key(url, owner_a, email_delivery="pending", show_plaintext=True)
    d1 = uuid.UUID(k1["email_delivery_id"])
    s1 = uuid.UUID(k1["one_time_secret_id"])
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s1),
            "--email-delivery-id", str(d1),
            "--actor-admin-id", str(admin_id),
            "--reason", "initial 202a",
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "sent"
    assert k1["plaintext_key"] in _FakeEmailService.sent[0]["text_body"]  # type: ignore[operator]
    assert k1["plaintext_key"] not in result.stdout  # type: ignore[operator]
    assert _run(_get_secret(url, s1)).status == "consumed"
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k1["gateway_key_id"])))[0].status == "sent"
    sent_count = len(_FakeEmailService.sent)

    # 2. Repeated already-sent request: refused, no second send/consumption.
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s1),
            "--email-delivery-id", str(d1),
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"
    assert len(_FakeEmailService.sent) == sent_count

    # 3. Failed retry: force an SMTP failure, then the explicit flag+reason path.
    _FakeEmailService.failure = SmtpSendError("smtp down 202a")
    k2 = _create_key(url, owner_a, email_delivery="pending")
    d2 = uuid.UUID(k2["email_delivery_id"])
    s2 = uuid.UUID(k2["one_time_secret_id"])
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s2),
            "--email-delivery-id", str(d2),
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"
    assert json.loads(result.stdout)["error_code"] == "smtp_send_error"
    _FakeEmailService.failure = None
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k2["gateway_key_id"])))[0].status == "failed"

    # Missing flag / blank reason / retry-on-pending are all refused first.
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s2), "--email-delivery-id", str(d2), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert "FAILED" in result.stdout
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s2),
            "--email-delivery-id", str(d2),
            "--retry-failed",
            "--reason", "   ",
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert "nonblank" in result.stdout
    k2b = _create_key(url, owner_a, email_delivery="pending")
    d2b = uuid.UUID(k2b["email_delivery_id"])
    s2b = uuid.UUID(k2b["one_time_secret_id"])
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s2b),
            "--email-delivery-id", str(d2b),
            "--retry-failed",
            "--reason", "x",
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert "Only an existing FAILED delivery" in result.stdout

    # The legitimate explicit retry succeeds and the reason is audited.
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s2),
            "--email-delivery-id", str(d2),
            "--actor-admin-id", str(admin_id),
            "--retry-failed",
            "--reason", "operator retry 202a",
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "sent"
    audits = _run(_audits(url, action="email_key", entity_id=d2))
    assert any(a.note == "operator retry 202a" for a in audits)

    # 4. Expired secret: refused, secret marked expired, no send, no decrypt of usable material.
    k3 = _create_key(url, owner_a, email_delivery="pending")
    d3 = uuid.UUID(k3["email_delivery_id"])
    s3 = uuid.UUID(k3["one_time_secret_id"])
    _run(_set_secret(url, s3, expires_at=now - timedelta(minutes=1)))
    sent_count = len(_FakeEmailService.sent)
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s3), "--email-delivery-id", str(d3), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error_code"] == "one_time_secret_expired"
    assert _run(_get_secret(url, s3)).status == "expired"
    assert len(_FakeEmailService.sent) == sent_count

    # 5. Selected sending / ambiguous are blocked.
    k4 = _create_key(url, owner_a, email_delivery="pending")
    d4 = uuid.UUID(k4["email_delivery_id"])
    s4 = uuid.UUID(k4["one_time_secret_id"])
    _run(_set_delivery(url, d4, status="sending"))
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s4), "--email-delivery-id", str(d4), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error_code"] == "email_delivery_in_progress"

    k5 = _create_key(url, owner_a, email_delivery="pending")
    d5 = uuid.UUID(k5["email_delivery_id"])
    s5 = uuid.UUID(k5["one_time_secret_id"])
    _run(_set_delivery(url, d5, status="ambiguous", failed_at=now))
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s5), "--email-delivery-id", str(d5), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error_code"] == "email_delivery_ambiguous"

    # 6. Missing selected delivery UUID: clean refusal, no implicit creation.
    k6 = _create_key(url, owner_a, email_delivery="pending")
    s6 = uuid.UUID(k6["one_time_secret_id"])
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s6), "--email-delivery-id", str(uuid.uuid4()), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)  # fixed safe JSON error
    assert len(_run(_delivery_rows(url, gateway_key_id=uuid.UUID(k6["gateway_key_id"])))) == 1

    # 7. Secret UUID mismatch: refused, both targets untouched.
    k7 = _create_key(url, owner_a, email_delivery="pending")
    d7 = uuid.UUID(k7["email_delivery_id"])
    s7 = uuid.UUID(k7["one_time_secret_id"])
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s1), "--email-delivery-id", str(d7), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert "match" in result.stdout
    assert _run(_get_secret(url, s7)).status == "pending"
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k7["gateway_key_id"])))[0].status == "pending"

    # 8. Foreign selected owner/key binding: refused WITHOUT decryption or
    # SMTP (pre-decryption binding law), foreign targets untouched.
    k8 = _create_key(url, owner_a, email_delivery="pending")
    k9 = _create_key(url, owner_b, email_delivery="pending")
    d8 = uuid.UUID(k8["email_delivery_id"])
    s9 = uuid.UUID(k9["one_time_secret_id"])
    _run(_set_delivery(url, d8, one_time_secret_id=s9))
    recipient_before8 = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k8["gateway_key_id"])))[0].recipient_email
    sent_count = len(_FakeEmailService.sent)
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s9), "--email-delivery-id", str(d8), "--send-now", "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"
    assert json.loads(result.stdout)["error_code"] == "email_delivery_not_sendable"
    assert len(_FakeEmailService.sent) == sent_count
    assert _run(_get_secret(url, s9)).status == "pending"
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k9["gateway_key_id"])))[0].status == "pending"
    # 202-b: the invalid-identity refusal leaves the selected recipient
    # untouched (zero decrypt/SMTP already asserted above).
    d8_after = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k8["gateway_key_id"])))[0]
    assert d8_after.status == "pending"
    assert d8_after.recipient_email == recipient_before8


def test_actions_no_id_bypass_refusals_and_pre_decrypt_guard(cli_env: str) -> None:
    url = cli_env
    owner_a = _run(_create_owner(url))
    owner_b = _run(_create_owner(url))
    now = datetime.now(UTC)

    # Omitted selector cannot bypass a retained same-secret SENDING state.
    k1 = _create_key(url, owner_a, email_delivery="pending")
    d1 = uuid.UUID(k1["email_delivery_id"])
    s1 = uuid.UUID(k1["one_time_secret_id"])
    _run(_set_delivery(url, d1, status="sending"))
    guard = {"calls": 0}
    result = _run(_send_via_service(url, one_time_secret_id=s1, decrypt_guard=guard))
    assert result.status == "failed"
    assert guard["calls"] == 0
    assert _FakeEmailService.sent == []
    rows = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k1["gateway_key_id"])))
    assert len(rows) == 1 and rows[0].status == "sending", "no substitute row, no state rewrite"

    # An alternative retryable (failed) row cannot bypass a same-secret SENT sibling.
    k2 = _create_key(url, owner_a, email_delivery="pending")
    d2 = uuid.UUID(k2["email_delivery_id"])
    s2 = uuid.UUID(k2["one_time_secret_id"])
    _run(_set_delivery(url, d2, status="sent", sent_at=now))
    d2_alt = uuid.uuid4()
    _run(
        _insert_delivery(
            url,
            row_id=d2_alt,
            owner_id=owner_a,
            gateway_key_id=uuid.UUID(k2["gateway_key_id"]),
            one_time_secret_id=s2,
            recipient_email="inspect-alternate@example.org",
            status="failed",
            created_at=now - timedelta(minutes=5),
        )
    )
    result = _run(_send_via_service(url, one_time_secret_id=s2, email_delivery_id=d2_alt, reason="retry"))
    assert result.status == "failed"
    alt_rows = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k2["gateway_key_id"])))
    assert {r.status for r in alt_rows} == {"sent", "failed"}, "retryable row untouched"

    # Retained FAILED history refuses a no-ID send; the explicit retry works.
    k3 = _create_key(url, owner_a, email_delivery="pending")
    d3 = uuid.UUID(k3["email_delivery_id"])
    s3 = uuid.UUID(k3["one_time_secret_id"])
    _run(_set_delivery(url, d3, status="failed", failed_at=now))
    result = _run(_send_via_service(url, one_time_secret_id=s3))
    assert result.status == "failed"
    assert len(_run(_delivery_rows(url, gateway_key_id=uuid.UUID(k3["gateway_key_id"])))) == 1
    guard = {"calls": 0}
    result = _run(_send_via_service(url, one_time_secret_id=s3, email_delivery_id=d3, reason="explicit retry", decrypt_guard=guard))
    assert result.status == "sent"
    assert guard["calls"] == 1

    # Legitimate fresh no-ID initial creation still works (real crypto once).
    k4 = _create_key(url, owner_a)  # no --email-delivery: secret, no delivery row
    s4 = uuid.UUID(k4["one_time_secret_id"])
    guard = {"calls": 0}
    result = _run(_send_via_service(url, one_time_secret_id=s4, decrypt_guard=guard))
    assert result.status == "sent"
    assert guard["calls"] == 1
    rows = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k4["gateway_key_id"])))
    assert len(rows) == 1 and rows[0].status == "sent"

    # Foreign owner/key binding refused BEFORE the real crypto (item 14).
    k5 = _create_key(url, owner_a, email_delivery="pending")
    k6 = _create_key(url, owner_b, email_delivery="pending")
    d5 = uuid.UUID(k5["email_delivery_id"])
    s6 = uuid.UUID(k6["one_time_secret_id"])
    _run(_set_delivery(url, d5, one_time_secret_id=s6))
    sent_count = len(_FakeEmailService.sent)
    guard = {"calls": 0}
    result = _run(_send_via_service(url, one_time_secret_id=s6, email_delivery_id=d5, decrypt_guard=guard))
    assert result.status == "failed"
    assert result.error_code == "email_delivery_not_sendable"
    assert guard["calls"] == 0
    assert len(_FakeEmailService.sent) == sent_count
    assert _run(_get_secret(url, s6)).status == "pending"
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k6["gateway_key_id"])))[0].status == "pending"
    # Not-sendable refusals do NOT rewrite the selected row (existing law):
    # the foreign-bound delivery stays pending, only the result refuses.
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k5["gateway_key_id"])))[0].status == "pending"


def test_actions_ambiguous_after_finalization_failure(cli_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    url = cli_env
    owner_id = _run(_create_owner(url))
    k = _create_key(url, owner_id, email_delivery="pending")
    d = uuid.UUID(k["email_delivery_id"])
    s = uuid.UUID(k["one_time_secret_id"])

    async def _boom(self, secret_id, *, consumed_at):
        raise RuntimeError("finalization boom 202a")

    monkeypatch.setattr("slaif_gateway.services.email_delivery_service.SecretService.mark_consumed", _boom)

    # SMTP accepted, finalization failed => ambiguous (not sent, not failed).
    result = _run(_send_via_service(url, one_time_secret_id=s, email_delivery_id=d))
    assert result.status == "ambiguous"
    assert result.error_code == "email_delivery_finalization_failed"
    assert "finalization boom 202a" not in (result.error_message or "")
    row = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k["gateway_key_id"])))[0]
    assert row.status == "ambiguous"
    assert _run(_get_secret(url, s)).status == "pending"  # not consumed
    audits = _run(_audits(url, action="email_key_ambiguous", entity_id=d))
    assert audits and audits[-1].new_values["error_code"] == "email_delivery_finalization_failed"
    assert "finalization boom 202a" not in json.dumps([a.new_values for a in audits])

    # Cannot be resent via explicit retry OR selector omission.
    sent_count = len(_FakeEmailService.sent)
    result = _run(_send_via_service(url, one_time_secret_id=s, email_delivery_id=d, reason="retry"))
    # Explicit retry of an ambiguous row refuses with the ambiguous
    # classification (existing law) — no second send.
    assert result.status == "ambiguous"
    assert result.error_code == "email_delivery_ambiguous"
    result = _run(_send_via_service(url, one_time_secret_id=s))
    assert result.status == "failed"
    assert result.error_code == "email_delivery_selection_required"
    assert len(_FakeEmailService.sent) == sent_count


# --- 202-b: prepared-recipient metadata on the existing sending commit -------
#
# The owner address is edited AFTER the pending delivery rows exist (they
# still carry the fictional creation-time address). The existing sending
# commit must record exactly the prepared SMTP target (current Owner.email)
# so read-only inspection reports the recipient prepared for THIS actual
# attempt. This never infers or rewrites historical destinations and proves
# nothing about SMTP acceptance or inbox arrival; outcomes follow the
# existing sent/failed/ambiguous law.


def test_prepared_recipient_refreshes_to_current_owner_email(
    cli_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = cli_env
    admin_id = _run(_create_admin(url))
    old_address = "ada-old-202b@example.org"
    current_address = "ada-current-202b@example.org"
    owner_id = _run(_create_owner(url, email=old_address))
    k1 = _create_key(url, owner_id, email_delivery="pending", show_plaintext=True)
    k2 = _create_key(url, owner_id, email_delivery="pending")
    k3 = _create_key(url, owner_id, email_delivery="pending")
    d1 = uuid.UUID(k1["email_delivery_id"])
    s1 = uuid.UUID(k1["one_time_secret_id"])
    d2 = uuid.UUID(k2["email_delivery_id"])
    s2 = uuid.UUID(k2["one_time_secret_id"])
    d3 = uuid.UUID(k3["email_delivery_id"])
    s3 = uuid.UUID(k3["one_time_secret_id"])
    # The owner address is edited AFTER the rows were created.
    _run(_set_fields(url, Owner, owner_id, email=current_address))
    for k in (k1, k2, k3):
        assert (
            _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k["gateway_key_id"])))[0].recipient_email
            == old_address
        )

    attempts: list[dict[str, object]] = []
    current_delivery: dict[str, uuid.UUID | None] = {"id": None}

    # DURING every attempt (successful or failed), a FRESH separate session
    # reads the row for the scenario's delivery UUID: the existing sending
    # commit must already carry the prepared recipient equal to the exact
    # fake `to`.
    async def _observe_attempt(during_url: str, to: str) -> None:
        entry: dict[str, object] = {"to": to}
        if current_delivery["id"] is not None:
            factory = _session_factory(during_url)
            async with factory() as fresh:
                row = await fresh.get(EmailDelivery, current_delivery["id"])
                entry["during_status"] = row.status
                entry["during_recipient"] = row.recipient_email
        attempts.append(entry)

    _FakeEmailService.send_url = url
    _FakeEmailService.on_send = _observe_attempt

    # A. SUCCESS via the ACTUAL CLI: after success the fresh row and the
    #    actual CLI list/show reflect the prepared address, not the
    #    obsolete one.
    current_delivery["id"] = d1
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s1),
            "--email-delivery-id", str(d1),
            "--actor-admin-id", str(admin_id),
            "--reason", "prepared recipient 202b",
            "--send-now",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "sent"
    assert len(attempts) == 1
    assert attempts[0]["to"] == current_address
    assert attempts[0]["during_status"] == "sending"
    assert attempts[0]["during_recipient"] == current_address
    row1 = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k1["gateway_key_id"])))[0]
    assert row1.status == "sent"
    assert row1.recipient_email == current_address
    assert _FakeEmailService.sent[-1]["to"] == current_address
    listed = _list_page("--delivery-id", str(d1))
    assert listed["items"][0]["recipient_email"] == current_address
    shown = _invoke_email(["show", str(d1), "--json"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["recipient_email"] == current_address

    # B. SMTP FAILURE via the ACTUAL shared sender: the ATTEMPT (observed
    #    before the fake failure) targets the prepared address with the
    #    committed sending state carrying it; existing failed law with the
    #    prepared recipient retained; the secret is untouched.
    current_delivery["id"] = d2
    _FakeEmailService.failure = SmtpSendError("smtp down 202b")
    result2 = _run(
        _send_via_service(url, one_time_secret_id=s2, email_delivery_id=d2, reason="smtp failure 202b")
    )
    _FakeEmailService.failure = None
    assert result2.status == "failed"
    assert len(attempts) == 2
    assert attempts[1]["to"] == current_address
    assert attempts[1]["during_status"] == "sending"
    assert attempts[1]["during_recipient"] == current_address
    row2 = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k2["gateway_key_id"])))[0]
    assert row2.status == "failed"
    assert row2.recipient_email == current_address
    assert _run(_get_secret(url, s2)).status == "pending"

    # C. SMTP accepted, DB finalization failure => existing ambiguous law,
    #    prepared recipient retained, secret not consumed, no resend.
    current_delivery["id"] = d3

    async def _boom(self, secret_id, *, consumed_at):
        raise RuntimeError("finalization boom 202b")

    monkeypatch.setattr("slaif_gateway.services.email_delivery_service.SecretService.mark_consumed", _boom)
    result3 = _run(
        _send_via_service(url, one_time_secret_id=s3, email_delivery_id=d3, reason="finalization failure 202b")
    )
    assert result3.status == "ambiguous"
    assert len(attempts) == 3
    assert attempts[2]["to"] == current_address
    assert attempts[2]["during_status"] == "sending"
    assert attempts[2]["during_recipient"] == current_address
    assert _FakeEmailService.sent[-1]["to"] == current_address
    row3 = _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k3["gateway_key_id"])))[0]
    assert row3.status == "ambiguous"
    assert row3.recipient_email == current_address
    assert _run(_get_secret(url, s3)).status == "pending"
    result4 = _run(_send_via_service(url, one_time_secret_id=s3, email_delivery_id=d3, reason="retry"))
    assert result4.status == "ambiguous"
    assert result4.error_code == "email_delivery_ambiguous"
    assert len(attempts) == 3, "the ambiguous retry adds no SMTP attempt"
    _FakeEmailService.on_send = None


# --- C: controlled blocking concurrency on real row locks --------------------
#
# Deterministic coordination: the holder acquires the exact FOR UPDATE row
# lock, the sender PREFETCHES the delivery/secret/sendability in its own
# session (so stale identity-map values are actually present), the sender
# then blocks, and the observer proves the CAUSAL relation with the exact
# query `holder = ANY(pg_blocking_pids(sender_pid))` (with the cached
# pg_stat snapshot cleared before each poll). Only then does the holder
# mutate the secret and commit. No fragile sleeps.


async def _concurrency_refusal_scenario(
    url: str,
    *,
    delivery_id: uuid.UUID,
    secret_id: uuid.UUID,
    holder_row: str,
    secret_mutation: dict[str, object] | None = None,
    late_expiry: dict[str, object] | None = None,
):
    """Holder locks one row; sender (prefetched, then blocked) must refuse."""
    factory = _session_factory(url)
    shared: dict[str, object] = {"holder_pid": None, "sender_pid": None, "result": None}
    locked = asyncio.Event()
    prefetched = asyncio.Event()
    blocked_observed = asyncio.Event()

    async def holder() -> None:
        # Session A holds the FOR UPDATE lock, waits until the observer has
        # PROVEN the sender is blocked by it, then mutates the secret.
        # It never acquires the other row (no inverse lock ordering).
        async with factory() as session_a:
            async with session_a.begin():
                model = EmailDelivery if holder_row == "delivery" else OneTimeSecret
                row_id = delivery_id if holder_row == "delivery" else secret_id
                row = (
                    await session_a.execute(
                        select(model).where(model.id == row_id).with_for_update()
                    )
                ).scalar_one()
                assert row.id == row_id
                shared["holder_pid"] = (
                    await session_a.execute(text("SELECT pg_backend_pid()"))
                ).scalar_one()
                locked.set()
                await blocked_observed.wait()
                if late_expiry is not None:
                    # Fresh-clock expiry proof: t1 is advanced ONLY after the
                    # causal lock wait is observed, and the new expiry sits
                    # strictly between the stale t0 and the fresh t1 — so a
                    # stale pre-wait clock would have passed the expiry
                    # check (and decrypted), while only the fresh clock
                    # refuses.
                    t0 = late_expiry["t0"]
                    t1 = max(datetime.now(UTC), t0 + timedelta(microseconds=1))
                    late_expiry["t1"] = t1
                    late_expiry["expiry"] = t0 + (t1 - t0) / 2
                    late_expiry["clock"]["current"] = t1
                    mutation = {"expires_at": late_expiry["expiry"]}
                else:
                    mutation = dict(secret_mutation)
                await session_a.execute(
                    update(OneTimeSecret)
                    .where(OneTimeSecret.id == secret_id)
                    .values(**mutation)
                )
            # commit releases the row lock

    async def sender() -> None:
        async with factory() as session_b:
            delivery_repo = EmailDeliveriesRepository(session_b)
            secret_repo = OneTimeSecretsRepository(session_b)
            # PREFETCH the relevant rows and the read-only sendability in
            # the SAME sender session BEFORE the wait: the identity map now
            # holds stale values the fresh-for-update lookups must replace.
            stale_delivery = await delivery_repo.get_email_delivery_by_id(delivery_id)
            stale_secret = await secret_repo.get_one_time_secret_by_id(secret_id)
            assert stale_delivery is not None and stale_delivery.status == "pending"
            assert stale_secret is not None and stale_secret.status == "pending"
            service = EmailDeliveryService(
                settings=get_settings(),
                one_time_secrets_repository=secret_repo,
                email_deliveries_repository=delivery_repo,
                gateway_keys_repository=GatewayKeysRepository(session_b),
                owners_repository=OwnersRepository(session_b),
                audit_repository=AuditRepository(session_b),
                email_service=_FakeEmailService(),
                session=session_b,
                now_factory=(
                    (lambda: late_expiry["clock"]["current"]) if late_expiry is not None else None
                ),
            )
            await service.get_key_email_delivery_sendability(delivery_id)
            shared["sender_pid"] = (
                await session_b.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
            prefetched.set()
            shared["result"] = await service.send_pending_key_email(
                one_time_secret_id=secret_id,
                email_delivery_id=delivery_id,
            )

    async def observer() -> None:
        # Exact causal relation: THIS sender backend waits on a lock and
        # THIS holder backend blocks it.
        async with factory() as obs:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                await obs.execute(text("SELECT pg_stat_clear_snapshot()"))
                waiting = (
                    await obs.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE pid = :sender AND wait_event_type = 'Lock' "
                            "AND :holder = ANY(pg_blocking_pids(pid))"
                        ),
                        {"sender": shared["sender_pid"], "holder": shared["holder_pid"]},
                    )
                ).scalar_one()
                if waiting >= 1:
                    blocked_observed.set()
                    return
                await asyncio.sleep(0.25)
        raise AssertionError("sender was never observed blocked BY the holder")

    a_task = asyncio.create_task(holder())
    await asyncio.wait_for(locked.wait(), timeout=30)
    b_task = asyncio.create_task(sender())
    await asyncio.wait_for(prefetched.wait(), timeout=30)
    o_task = asyncio.create_task(observer())
    await asyncio.wait_for(blocked_observed.wait(), timeout=30)
    await o_task
    await asyncio.wait_for(a_task, timeout=30)
    await asyncio.wait_for(b_task, timeout=60)
    return shared["result"]


def _run_concurrency_with_crypto_guard(url: str, scenario_kwargs: dict[str, object]):
    """Run one scenario with the ACTUAL decrypt_secret hook counting calls."""
    import slaif_gateway.services.secret_service as secret_service_module

    original = secret_service_module.decrypt_secret
    guard = {"calls": 0}

    def counting_decrypt(*args, **kwargs):
        guard["calls"] += 1
        return original(*args, **kwargs)

    secret_service_module.decrypt_secret = counting_decrypt
    try:
        result = _run(_concurrency_refusal_scenario(url, **scenario_kwargs))
    finally:
        secret_service_module.decrypt_secret = original
    return result, guard


def _fresh_pending_pair(url: str, owner_id: uuid.UUID):
    k = _create_key(url, owner_id, email_delivery="pending")
    return (
        uuid.UUID(k["email_delivery_id"]),
        uuid.UUID(k["one_time_secret_id"]),
        uuid.UUID(k["gateway_key_id"]),
    )


def test_concurrency_delivery_lock_wait_consumed_refusal(cli_env: str) -> None:
    url = cli_env
    owner_id = _run(_create_owner(url))
    delivery_id, secret_id, key_id = _fresh_pending_pair(url, owner_id)
    now = datetime.now(UTC)

    result, guard = _run_concurrency_with_crypto_guard(
        url,
        {
            "delivery_id": delivery_id,
            "secret_id": secret_id,
            "holder_row": "delivery",
            "secret_mutation": {"status": "consumed", "consumed_at": now},
        },
    )

    # The stale preflight (pending/present, prefetched before the wait)
    # cannot authorize once the secret is consumed while blocked.
    assert result.status == "failed"
    assert result.error_code == "one_time_secret_already_consumed"
    assert guard["calls"] == 0
    assert _FakeEmailService.sent == []
    secret = _run(_get_secret(url, secret_id))
    assert secret.status == "consumed" and secret.consumed_at is not None
    rows = _run(_delivery_rows(url, gateway_key_id=key_id))
    assert len(rows) == 1
    assert rows[0].status == "failed"  # existing failure law for the attempt
    audits = _run(_audits(url, action="email_key_failed", entity_id=delivery_id))
    assert audits and audits[-1].new_values["error_code"] == "one_time_secret_already_consumed"


def test_concurrency_secret_lock_wait_consumed_refusal(cli_env: str) -> None:
    url = cli_env
    owner_id = _run(_create_owner(url))
    delivery_id, secret_id, key_id = _fresh_pending_pair(url, owner_id)
    now = datetime.now(UTC)

    # The sender holds the delivery lock and waits on the SECRET row lock;
    # the holder (secret row only) consumes it. The fresh-for-update secret
    # refresh must override the prefetched stale pending value.
    result, guard = _run_concurrency_with_crypto_guard(
        url,
        {
            "delivery_id": delivery_id,
            "secret_id": secret_id,
            "holder_row": "secret",
            "secret_mutation": {"status": "consumed", "consumed_at": now},
        },
    )

    assert result.status == "failed"
    assert result.error_code == "one_time_secret_already_consumed"
    assert guard["calls"] == 0
    assert _FakeEmailService.sent == []
    assert _run(_get_secret(url, secret_id)).status == "consumed"
    rows = _run(_delivery_rows(url, gateway_key_id=key_id))
    assert len(rows) == 1 and rows[0].status == "failed"


def test_concurrency_secret_lock_wait_expiry_after_wait_fresh_clock(cli_env: str) -> None:
    url = cli_env
    owner_id = _run(_create_owner(url))
    delivery_id, secret_id, key_id = _fresh_pending_pair(url, owner_id)
    # Stale clock t0 (the sender's pre-wait instant, injected via
    # now_factory); the holder moves the expiry to t0 < expiry < t1 where
    # t1 is advanced only after the causal lock wait is observed.
    t0 = datetime.now(UTC)
    late = {"t0": t0, "clock": {"current": t0}, "t1": None, "expiry": None}

    result, guard = _run_concurrency_with_crypto_guard(
        url,
        {
            "delivery_id": delivery_id,
            "secret_id": secret_id,
            "holder_row": "secret",
            "late_expiry": late,
        },
    )

    # The boundary itself: a stale t0 would NOT have seen this expiry.
    assert t0 < late["expiry"] < late["t1"]
    assert result.status == "failed"
    assert result.error_code == "one_time_secret_expired"
    assert guard["calls"] == 0
    assert _FakeEmailService.sent == []
    secret = _run(_get_secret(url, secret_id))
    assert secret.status == "expired", "fresh-clock expiry law must mark it"
    assert secret.consumed_at is None
    rows = _run(_delivery_rows(url, gateway_key_id=key_id))
    assert len(rows) == 1 and rows[0].status == "failed"
    audits = _run(_audits(url, action="email_key_failed", entity_id=delivery_id))
    assert audits and audits[-1].new_values["error_code"] == "one_time_secret_expired"


# --- D: enqueue intent audit, payload, and failure boundaries ----------------


def test_enqueue_intent_audit_payload_and_queued_distinct(
    cli_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = cli_env
    admin_id = _run(_create_admin(url))
    owner_id = _run(_create_owner(url))
    k = _create_key(url, owner_id, email_delivery="pending")
    d = uuid.UUID(k["email_delivery_id"])
    s = uuid.UUID(k["one_time_secret_id"])
    reason = "enqueue intent 202a"

    task = _FakeTask()
    task.url = url
    task.expected = {"one_time_secret_id": s, "email_delivery_id": d}
    monkeypatch.setattr(email_cli, "send_pending_key_email_task", task)

    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s),
            "--email-delivery-id", str(d),
            "--actor-admin-id", str(admin_id),
            "--reason", reason,
            "--enqueue",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "queued"
    assert payload["celery_task_id"] == "fake-task-202a"
    # Broker payload: EXACTLY the existing three UUIDs — no reason/body/key/crypto.
    assert task.calls == [(str(s), str(d), str(admin_id))]
    blob = repr(task.calls)
    assert reason not in blob and "sk-slaif-" not in blob
    # Intent was committed BEFORE dispatch (verified from inside delay()).
    assert task.intent_visible_before_dispatch is True
    # Reason is no longer silently ignored on enqueue.
    audits = _run(_audits(url, action="email_key_enqueue_requested", entity_id=d))
    assert len(audits) == 1
    assert audits[0].note == reason
    assert audits[0].admin_user_id == admin_id
    assert audits[0].new_values["intent"] == "enqueue_requested"
    # The selected delivery id is the persisted safe selected ID; the
    # one-time secret is attributed through the documented SAFE reference
    # field only — the secret-bearing key name is dropped by the global
    # durable sanitizer (existing boundary, not relaxed here).
    assert audits[0].new_values["email_delivery_id"] == str(d)
    assert audits[0].new_values["one_time_reference_id"] == str(s)
    assert "one_time_secret_id" not in audits[0].new_values
    # `queued` is the CLI broker-submission result, NOT a persisted status.
    f = _list_page("--delivery-id", str(d))
    assert f["items"][0]["status"] == "pending"
    assert _run(_get_secret(url, s)).status == "pending"


def test_enqueue_no_id_preflight_and_failure_boundaries(
    cli_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = cli_env
    owner_a = _run(_create_owner(url))
    owner_b = _run(_create_owner(url))
    now = datetime.now(UTC)

    def install_task() -> _FakeTask:
        task = _FakeTask()
        monkeypatch.setattr(email_cli, "send_pending_key_email_task", task)
        return task

    # Fresh no-ID initial enqueue is preserved (secret, no delivery row yet).
    k_fresh = _create_key(url, owner_a)
    s_fresh = uuid.UUID(k_fresh["one_time_secret_id"])
    task = install_task()
    result = _invoke_email(
        ["send-pending-key", "--one-time-secret-id", str(s_fresh), "--enqueue", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "queued"
    assert task.calls == [(str(s_fresh), None, None)]
    assert task.intent_visible_before_dispatch is None  # selected-only probe not armed

    # Retained FAILED same-secret history: refused BEFORE audit/dispatch.
    k1 = _create_key(url, owner_a, email_delivery="pending")
    d1 = uuid.UUID(k1["email_delivery_id"])
    s1 = uuid.UUID(k1["one_time_secret_id"])
    _run(_set_delivery(url, d1, status="failed", failed_at=now))
    before = len(_run(_audits(url, action="email_key_enqueue_requested")))
    task = install_task()
    result = _invoke_email(["send-pending-key", "--one-time-secret-id", str(s1), "--enqueue", "--json"])
    assert result.exit_code == 1
    assert "history" in result.stdout
    assert task.calls == []
    assert len(_run(_audits(url, action="email_key_enqueue_requested"))) == before

    # A same-secret SENDING sibling blocks no-ID enqueue too.
    k2 = _create_key(url, owner_b, email_delivery="pending")
    d2 = uuid.UUID(k2["email_delivery_id"])
    s2 = uuid.UUID(k2["one_time_secret_id"])
    _run(_set_delivery(url, d2, status="sending"))
    before = len(_run(_audits(url, action="email_key_enqueue_requested")))
    task = install_task()
    result = _invoke_email(["send-pending-key", "--one-time-secret-id", str(s2), "--enqueue", "--json"])
    assert result.exit_code == 1
    assert "not safe" in result.stdout
    assert task.calls == []
    assert len(_run(_audits(url, action="email_key_enqueue_requested"))) == before

    # Shared sendability AGREEMENT: a selected pending row with a blocked
    # same-secret sibling (sent) reports can_send=false in `show` AND
    # refuses the enqueue — one shared validator, no second divergence.
    k4 = _create_key(url, owner_b, email_delivery="pending")
    s4 = uuid.UUID(k4["one_time_secret_id"])
    d4 = uuid.UUID(k4["email_delivery_id"])
    _run(_set_delivery(url, d4, status="sent", sent_at=now))
    d3 = uuid.uuid4()
    _run(
        _insert_delivery(
            url,
            row_id=d3,
            owner_id=owner_b,
            gateway_key_id=uuid.UUID(k4["gateway_key_id"]),
            one_time_secret_id=s4,
            recipient_email="inspect-sibling@example.org",
            status="pending",
            created_at=now - timedelta(minutes=5),
        )
    )
    show = _invoke_email(["show", str(d3), "--json"])
    assert show.exit_code == 0
    show_payload = json.loads(show.stdout)
    assert show_payload["one_time_secret"]["can_send"] is False
    assert "sending, sent, or ambiguous" in (show_payload["one_time_secret"]["blocking_reason"] or "")
    task = install_task()
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s4),
            "--email-delivery-id", str(d3),
            "--enqueue",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert task.calls == []

    # Audit failure prevents dispatch (safe JSON, no detail, no state change).
    k5 = _create_key(url, owner_a, email_delivery="pending")
    d5 = uuid.UUID(k5["email_delivery_id"])
    s5 = uuid.UUID(k5["one_time_secret_id"])
    original_audit = email_cli._record_enqueue_request_audit

    async def _audit_boom(**kwargs):
        raise RuntimeError("audit store down 202a")

    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", _audit_boom)
    task = install_task()
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s5),
            "--email-delivery-id", str(d5),
            "--enqueue",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "command_failed"
    assert "audit store down 202a" not in result.stdout
    assert task.calls == []
    # Restore the real audit path: the dispatch-failure case needs the
    # honest committed intent.
    monkeypatch.setattr(email_cli, "_record_enqueue_request_audit", original_audit)

    # Dispatch failure leaves ONLY the honest committed intent.
    k6 = _create_key(url, owner_a, email_delivery="pending")
    d6 = uuid.UUID(k6["email_delivery_id"])
    s6 = uuid.UUID(k6["one_time_secret_id"])
    before = len(_run(_audits(url, action="email_key_enqueue_requested", entity_id=d6)))
    task = install_task()
    task.raising = True
    result = _invoke_email(
        [
            "send-pending-key",
            "--one-time-secret-id", str(s6),
            "--email-delivery-id", str(d6),
            "--enqueue",
            "--json",
        ]
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "command_failed"
    assert "broker down 202a" not in result.stdout
    assert task.calls == [(str(s6), str(d6), None)]  # dispatch was attempted
    after = _run(_audits(url, action="email_key_enqueue_requested", entity_id=d6))
    assert len(after) == before + 1  # honest intent remains
    assert after[-1].new_values["intent"] == "enqueue_requested"
    assert _run(_delivery_rows(url, gateway_key_id=uuid.UUID(k6["gateway_key_id"])))[0].status == "pending"
    assert _run(_get_secret(url, s6)).status == "pending"
