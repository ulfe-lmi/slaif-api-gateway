"""Real owned-PostgreSQL-16 evidence for objective 200 replay maintenance.

Proves, against a real disposable database: exact read-only inspection
(counts, ranges, route/model groups, fixed exclusion reasons, zero
writes/audits); dry-run plan file (0600, zero writes); the reviewed apply
(original stored creation + selected TTL target, monotonic no-shorten,
created_at and every unrelated column unchanged, ONE safe audit with no
digests/row UUIDs); safe idempotent repeat (no duplicate audit); stale
refusal on an unrelated change and on a crossed eligibility boundary;
explicit --include-expired restoration; explicit TTL distinct from the
configured default; a forced LATE audit failure with the updated row
visible in the SAME transaction and full rollback; and the encountered
scale (20,451 references across 26 eligible keys, including 91 expired
needing explicit consent) supported in ONE reviewed operation.

No provider HTTP, no Redis, no real upstream contact, no real SMTP.
Ownership discipline mirrors the 199 owned fixture: unique owner label,
loopback-bound, tmpfs-backed PostgreSQL 16, identity inspected BEFORE
readiness/migration, cleanup removes ONLY the exact created container ID.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import (
    AuditLog,
    CodexReplayReference,
    GatewayKey,
    ModelRoute,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferenceInsert,
    CodexReplayReferencesRepository,
)
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.codex_replay_maintenance import (
    parse_replay_extend_plan_file,
)
from slaif_gateway.services.codex_replay_maintenance import (
    CodexReplayMaintenanceService,
    ReplayMaintenanceStaleError,
)
from slaif_gateway.schemas.codex_replay_maintenance import ReplayScope
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif200a"

_STATE: dict[str, Any] = {}

_CLI_ENV_VARS = (
    "DATABASE_URL",
    "APP_ENV",
    "GATEWAY_KEY_PREFIX",
    "GATEWAY_KEY_ACCEPTED_PREFIXES",
    "ACTIVE_HMAC_KEY_VERSION",
    "TOKEN_HMAC_SECRET_V1",
    "TOKEN_HMAC_SECRET_V2",
    "ADMIN_SESSION_SECRET",
    "ONE_TIME_SECRET_ENCRYPTION_KEY",
    "OPENAI_UPSTREAM_API_KEY",
    "OPENROUTER_API_KEY",
    "ENABLE_EMAIL_DELIVERY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_FROM",
    "CODEX_REPLAY_REFERENCE_TTL_SECONDS",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-codex-replay-12345"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-codex-replay-12345"

RUNNER = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_TERM_VARS = ("COLUMNS", "NO_COLOR")


def _plain(text: str) -> str:
    return " ".join(_ANSI_RE.sub("", text).split())


def _cli(*args: str) -> Any:
    return RUNNER.invoke(app, list(args))


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- owned PostgreSQL 16 fixture ---------------------------------------------


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
    saved = {name: os.environ.get(name) for name in _CLI_ENV_VARS}
    os.environ["DATABASE_URL"] = owned_pg_url
    os.environ["APP_ENV"] = "test"
    os.environ["GATEWAY_KEY_PREFIX"] = "sk-slaif-"
    os.environ["GATEWAY_KEY_ACCEPTED_PREFIXES"] = "sk-slaif-"
    os.environ["ACTIVE_HMAC_KEY_VERSION"] = "1"
    os.environ["TOKEN_HMAC_SECRET_V1"] = TEST_HMAC_SECRET
    os.environ.pop("TOKEN_HMAC_SECRET_V2", None)  # version 2 intentionally unavailable
    os.environ["ADMIN_SESSION_SECRET"] = TEST_ADMIN_SECRET
    from slaif_gateway.utils.secrets import generate_secret_key

    os.environ["ONE_TIME_SECRET_ENCRYPTION_KEY"] = generate_secret_key()
    os.environ["OPENAI_UPSTREAM_API_KEY"] = "fake-openai-upstream-key"
    os.environ["OPENROUTER_API_KEY"] = "fake-openrouter-upstream-key"
    os.environ.pop("ENABLE_EMAIL_DELIVERY", None)
    os.environ.pop("SMTP_HOST", None)
    os.environ.pop("SMTP_PORT", None)
    os.environ.pop("SMTP_FROM", None)
    os.environ.pop("CODEX_REPLAY_REFERENCE_TTL_SECONDS", None)  # configured default
    get_settings.cache_clear()
    saved_term = {name: os.environ.get(name) for name in _TERM_VARS}
    os.environ["COLUMNS"] = "220"
    os.environ["NO_COLOR"] = "1"
    try:
        yield owned_pg_url
    finally:
        for name, value in saved_term.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def _session_factory(url: str):
    return async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)


# --- world --------------------------------------------------------------------

TTL_365 = 31_536_000
WORLD_NOW = datetime.now(UTC)


async def _make_key(
    session,
    *,
    owner_id: uuid.UUID,
    cohort_id: uuid.UUID,
    tag: str,
    status: str = "active",
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> GatewayKey:
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"pk-{tag}-{uuid.uuid4().hex[:12]}",
        token_hash=f"hash-{tag}-{uuid.uuid4().hex}",
        owner_id=owner_id,
        cohort_id=cohort_id,
        valid_from=valid_from or (WORLD_NOW - timedelta(days=10)),
        valid_until=valid_until or (WORLD_NOW + timedelta(days=3650)),
        status=status,
    )


async def _make_ledger(
    session,
    *,
    key: GatewayKey,
    tag: str,
    finalized: bool = True,
) -> UsageLedger:
    row = UsageLedger(
        request_id=f"req-{tag}-{uuid.uuid4().hex}",
        gateway_key_id=key.id,
        endpoint="/v1/responses",
        provider="mod-a",
        success=True if finalized else None,
        accounting_status="finalized" if finalized else "pending",
        started_at=WORLD_NOW - timedelta(days=10),
        finished_at=WORLD_NOW - timedelta(days=10),
    )
    session.add(row)
    await session.flush()
    return row


async def _make_reference(
    session,
    *,
    key: GatewayKey,
    ledger: UsageLedger,
    route: ModelRoute,
    tag: str,
    created: datetime,
    expires: datetime,
    version: int = 1,
    kind: str = "reasoning",
) -> CodexReplayReference:
    return await CodexReplayReferencesRepository(session).upsert_many(
        [
            CodexReplayReferenceInsert(
                id=uuid.uuid4(),
                gateway_key_id=key.id,
                usage_ledger_id=ledger.id,
                source_request_id=ledger.request_id,
                provider="mod-a",
                route_id=route.id,
                upstream_model="zap-it-1",
                item_kind=kind,
                item_id_hmac=_digest(f"item-{tag}"),
                call_id_hmac=None,
                hmac_key_version=version,
                tool_namespace=None,
                tool_name=None,
                created_at=created,
                expires_at=expires,
            )
        ]
    ) or None


async def _world(url: str) -> dict[str, Any]:
    factory = _session_factory(url)
    state: dict[str, Any] = {"url": url}
    async with factory() as session:
        owner = await OwnersRepository(session).create_owner(
            name="Replay", surname="Maint", email=f"replay-{uuid.uuid4().hex[:8]}@example.test"
        )
        cohort = await CohortsRepository(session).create_cohort(name="replay-maint")
        cohort_bulk = await CohortsRepository(session).create_cohort(name="replay-bulk")
        route = await ModelRoutesRepository(session).create_model_route(
            requested_model="zap-it-1",
            provider="mod-a",
            upstream_model="zap-it-1",
        )
        keys = {
            "active": await _make_key(session, owner_id=owner.id, cohort_id=cohort.id, tag="active"),
            "revoked": await _make_key(
                session, owner_id=owner.id, cohort_id=cohort.id, tag="revoked", status="revoked"
            ),
            "suspended": await _make_key(
                session, owner_id=owner.id, cohort_id=cohort.id, tag="suspended", status="suspended"
            ),
            "future": await _make_key(
                session,
                owner_id=owner.id,
                cohort_id=cohort.id,
                tag="future",
                valid_from=WORLD_NOW + timedelta(days=1),
            ),
            "past": await _make_key(
                session,
                owner_id=owner.id,
                cohort_id=cohort.id,
                tag="past",
                valid_until=WORLD_NOW - timedelta(days=1),
            ),
            "expired": await _make_key(session, owner_id=owner.id, cohort_id=cohort.id, tag="expired"),
            "ttl": await _make_key(session, owner_id=owner.id, cohort_id=cohort.id, tag="ttl"),
            "rollback": await _make_key(session, owner_id=owner.id, cohort_id=cohort.id, tag="rollback"),
        }
        ledgers = {tag: await _make_ledger(session, key=keys[tag], tag=tag) for tag in keys}
        bad_ledger = await _make_ledger(session, key=keys["active"], tag="active-bad", finalized=False)

        created_10d = WORLD_NOW - timedelta(days=10)
        refs: dict[str, list[Any]] = {}

        def _rec(tag: str, key: GatewayKey, ledger: UsageLedger, created: datetime, expires: datetime, **kw: Any) -> None:
            refs.setdefault(tag, []).append(
                (key, ledger, created, expires, kw)
            )

        _rec("r_active", keys["active"], ledgers["active"], created_10d, created_10d + timedelta(days=90))
        _rec("r_late", keys["active"], ledgers["active"], created_10d, WORLD_NOW + timedelta(days=999))
        _rec("r_boundary", keys["active"], ledgers["active"], created_10d, created_10d + timedelta(days=90))
        _rec("r_expired", keys["active"], ledgers["active"], created_10d, WORLD_NOW - timedelta(days=1))
        _rec("r_ledger_bad", keys["active"], bad_ledger, created_10d, created_10d + timedelta(days=90))
        _rec("r_version2", keys["active"], ledgers["active"], created_10d, created_10d + timedelta(days=90), version=2)
        _rec("r_old", keys["active"], ledgers["active"], WORLD_NOW - timedelta(days=400), WORLD_NOW + timedelta(days=90))
        _rec("r_revoked", keys["revoked"], ledgers["revoked"], created_10d, created_10d + timedelta(days=90))
        _rec("r_suspended", keys["suspended"], ledgers["suspended"], created_10d, created_10d + timedelta(days=90))
        _rec("r_future", keys["future"], ledgers["future"], created_10d, created_10d + timedelta(days=90))
        _rec("r_past", keys["past"], ledgers["past"], created_10d, created_10d + timedelta(days=90))
        _rec("r_exp_a", keys["expired"], ledgers["expired"], created_10d, WORLD_NOW - timedelta(days=1))
        _rec("r_exp_b", keys["expired"], ledgers["expired"], created_10d, WORLD_NOW - timedelta(days=2))
        _rec("r_exp_c", keys["expired"], ledgers["expired"], created_10d, WORLD_NOW - timedelta(days=3))
        _rec("r_exp_ok", keys["expired"], ledgers["expired"], created_10d, created_10d + timedelta(days=90))
        _rec("r_ttl", keys["ttl"], ledgers["ttl"], created_10d, created_10d + timedelta(days=90))
        _rec("r_rb_a", keys["rollback"], ledgers["rollback"], created_10d, created_10d + timedelta(days=90))
        _rec("r_rb_b", keys["rollback"], ledgers["rollback"], created_10d, created_10d + timedelta(days=90))

        for tag, entries in refs.items():
            for key, ledger, created, expires, kw in entries:
                await _make_reference(
                    session,
                    key=key,
                    ledger=ledger,
                    route=route,
                    tag=tag,
                    created=created,
                    expires=expires,
                    **kw,
                )

        # Bulk world: 20,451 references across 26 eligible keys (91 expired).
        bulk_keys = []
        for i in range(26):
            bulk_keys.append(
                await _make_key(
                    session, owner_id=owner.id, cohort_id=cohort_bulk.id, tag=f"bulk{i:02d}"
                )
            )
        bulk_ledgers = [await _make_ledger(session, key=k, tag=f"bulk{i:02d}") for i, k in enumerate(bulk_keys)]
        per_key = [20451 // 26] * 26
        for i in range(20451 % 26):
            per_key[i] += 1
        inserts: list[CodexReplayReferenceInsert] = []
        expired_slots = 91
        for i, key in enumerate(bulk_keys):
            for j in range(per_key[i]):
                is_expired = expired_slots > 0
                if is_expired:
                    expired_slots -= 1
                created = WORLD_NOW - timedelta(days=10 + (j % 5))
                expires = (
                    WORLD_NOW - timedelta(hours=1 + (j % 24))
                    if is_expired
                    else created + timedelta(days=90)
                )
                inserts.append(
                    CodexReplayReferenceInsert(
                        id=uuid.uuid4(),
                        gateway_key_id=key.id,
                        usage_ledger_id=bulk_ledgers[i].id,
                        source_request_id=bulk_ledgers[i].request_id,
                        provider="mod-a",
                        route_id=route.id,
                        upstream_model="zap-it-1",
                        item_kind="reasoning",
                        item_id_hmac=_digest(f"bulk-{i}-{j}"),
                        call_id_hmac=None,
                        hmac_key_version=1,
                        tool_namespace=None,
                        tool_name=None,
                        created_at=created,
                        expires_at=expires,
                    )
                )
        assert expired_slots == 0
        # Chunked: a single 20,451-row statement would exceed the
        # PostgreSQL 65,535 protocol parameter limit.
        for start in range(0, len(inserts), 1_000):
            await CodexReplayReferencesRepository(session).upsert_many(
                inserts[start : start + 1_000]
            )
        state["owner"] = owner
        state["cohort"] = cohort
        state["cohort_bulk"] = cohort_bulk
        state["route"] = route
        state["keys"] = keys
        state["bulk_keys"] = bulk_keys
        await session.commit()
    return state


@pytest.fixture(scope="module")
def world(cli_env: str) -> dict[str, Any]:
    return asyncio.run(_world(cli_env))


# --- helpers ------------------------------------------------------------------


def _service_for(url: str, session: Any) -> CodexReplayMaintenanceService:
    return CodexReplayMaintenanceService(
        repository=CodexReplayReferencesRepository(session),
        audit_repository=AuditRepository(session),
        settings=get_settings(),
    )


def _key_state_row(state: dict[str, Any], tag: str) -> uuid.UUID:
    return state["keys"][tag].id


def _snapshot_rows(url: str, key_id: uuid.UUID) -> dict[uuid.UUID, tuple]:
    async def _go() -> dict[uuid.UUID, tuple]:
        factory = _session_factory(url)
        async with factory() as session:
            result = await session.execute(
                select(CodexReplayReference).where(
                    CodexReplayReference.gateway_key_id == key_id
                )
            )
            out: dict[uuid.UUID, tuple] = {}
            for row in result.scalars().all():
                out[row.id] = (
                    row.gateway_key_id,
                    row.usage_ledger_id,
                    row.source_request_id,
                    row.provider,
                    row.route_id,
                    row.upstream_model,
                    row.item_kind,
                    row.item_id_hmac,
                    row.call_id_hmac,
                    row.hmac_key_version,
                    row.tool_namespace,
                    row.tool_name,
                    row.created_at,
                    row.expires_at,
                )
            return out

    return asyncio.run(_go())


def _audits_for_action(url: str) -> list[Any]:
    async def _go() -> list[Any]:
        factory = _session_factory(url)
        async with factory() as session:
            result = await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "codex_replay_references_extended"
                )
            )
            return list(result.scalars().all())

    return asyncio.run(_go())


def _row_expiries(url: str, key_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    async def _go() -> dict[uuid.UUID, datetime]:
        factory = _session_factory(url)
        async with factory() as session:
            result = await session.execute(
                select(CodexReplayReference.id, CodexReplayReference.expires_at).where(
                    CodexReplayReference.gateway_key_id == key_id
                )
            )
            return {row[0]: row[1] for row in result.all()}

    return asyncio.run(_go())


# --- additional helpers -------------------------------------------------------


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _ref_count(url: str) -> int:
    async def _go() -> int:
        factory = _session_factory(url)
        async with factory() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(CodexReplayReference.id))
                    )
                ).scalar_one()
            )

    return asyncio.run(_go())


def _audits_count(url: str) -> int:
    return len(_audits_for_action(url))


def _row_id_for_digest(url: str, key_id: uuid.UUID, digest: str) -> uuid.UUID:
    async def _go() -> uuid.UUID:
        factory = _session_factory(url)
        async with factory() as session:
            return (
                await session.execute(
                    select(CodexReplayReference.id).where(
                        CodexReplayReference.gateway_key_id == key_id,
                        CodexReplayReference.item_id_hmac == digest,
                    )
                )
            ).scalar_one()

    return asyncio.run(_go())


def _raw_update_expiry(url: str, row_id: uuid.UUID, new_expiry: datetime) -> None:
    async def _go() -> None:
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    update(CodexReplayReference)
                    .where(CodexReplayReference.id == row_id)
                    .values(expires_at=new_expiry)
                )

    asyncio.run(_go())


def _cohort_key_count(url: str, cohort_id: uuid.UUID) -> int:
    async def _go() -> int:
        factory = _session_factory(url)
        async with factory() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(GatewayKey.id)).where(
                            GatewayKey.cohort_id == cohort_id
                        )
                    )
                ).scalar_one()
            )

    return asyncio.run(_go())


def _new_cohort(url: str, name: str) -> uuid.UUID:
    async def _go() -> uuid.UUID:
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                cohort = await CohortsRepository(session).create_cohort(name=name)
                return cohort.id

    return asyncio.run(_go())


def _new_key(url: str, cohort_id: uuid.UUID, tag: str) -> uuid.UUID:
    async def _go() -> uuid.UUID:
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                owner_id = (
                    await session.execute(select(GatewayKey.owner_id).limit(1))
                ).scalar_one()
                key = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"pk-{tag}-{uuid.uuid4().hex[:12]}",
                    token_hash=f"hash-{tag}-{uuid.uuid4().hex}",
                    owner_id=owner_id,
                    cohort_id=cohort_id,
                    valid_from=WORLD_NOW - timedelta(days=10),
                    valid_until=WORLD_NOW + timedelta(days=3650),
                    status="active",
                )
                return key.id

    return asyncio.run(_go())


def _key_cohort(url: str, key_id: uuid.UUID) -> uuid.UUID:
    async def _go() -> uuid.UUID:
        factory = _session_factory(url)
        async with factory() as session:
            return (
                await session.execute(
                    select(GatewayKey.cohort_id).where(GatewayKey.id == key_id)
                )
            ).scalar_one()

    return asyncio.run(_go())


def _new_key_with_reference(
    url: str,
    cohort_name: str,
    tag: str,
    created_offset: timedelta = timedelta(days=10),
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, datetime]:
    async def _go() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, datetime]:
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                owner_id = (
                    await session.execute(select(GatewayKey.owner_id).limit(1))
                ).scalar_one()
                cohort = await CohortsRepository(session).create_cohort(name=cohort_name)
                key = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"pk-{tag}-{uuid.uuid4().hex[:12]}",
                    token_hash=f"hash-{tag}-{uuid.uuid4().hex}",
                    owner_id=owner_id,
                    cohort_id=cohort.id,
                    valid_from=WORLD_NOW - timedelta(days=10),
                    valid_until=WORLD_NOW + timedelta(days=3650),
                    status="active",
                )
                ledger = UsageLedger(
                    request_id=f"req-{tag}-{uuid.uuid4().hex}",
                    gateway_key_id=key.id,
                    endpoint="/v1/responses",
                    provider="mod-a",
                    success=True,
                    accounting_status="finalized",
                    started_at=WORLD_NOW - timedelta(days=10),
                    finished_at=WORLD_NOW - timedelta(days=10),
                )
                session.add(ledger)
                await session.flush()
                route_id = (
                    await session.execute(select(ModelRoute.id).limit(1))
                ).scalar_one()
                created = WORLD_NOW - created_offset
                await CodexReplayReferencesRepository(session).upsert_many(
                    [
                        CodexReplayReferenceInsert(
                            id=uuid.uuid4(),
                            gateway_key_id=key.id,
                            usage_ledger_id=ledger.id,
                            source_request_id=ledger.request_id,
                            provider="mod-a",
                            route_id=route_id,
                            upstream_model="zap-it-1",
                            item_kind="reasoning",
                            item_id_hmac=_digest(f"item-{tag}"),
                            call_id_hmac=None,
                            hmac_key_version=1,
                            tool_namespace=None,
                            tool_name=None,
                            created_at=created,
                            expires_at=created + timedelta(days=90),
                        )
                    ]
                )
                row_id = (
                    await session.execute(
                        select(CodexReplayReference.id).where(
                            CodexReplayReference.gateway_key_id == key.id
                        )
                    )
                ).scalar_one()
                return cohort.id, key.id, row_id, created

    return asyncio.run(_go())


def _created_digest(url: str, cohort_id: uuid.UUID) -> tuple[str, int]:
    async def _go() -> tuple[str, int]:
        factory = _session_factory(url)
        async with factory() as session:
            values = (
                await session.execute(
                    select(CodexReplayReference.created_at)
                    .join(GatewayKey, GatewayKey.id == CodexReplayReference.gateway_key_id)
                    .where(GatewayKey.cohort_id == cohort_id)
                    .order_by(CodexReplayReference.id)
                )
            ).scalars().all()
        return (
            hashlib.sha256(
                b",".join(value.isoformat().encode("utf-8") for value in values)
            ).hexdigest(),
            len(values),
        )

    return asyncio.run(_go())


def _exact_target_count(url: str, cohort_id: uuid.UUID) -> int:
    async def _go() -> int:
        factory = _session_factory(url)
        async with factory() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(CodexReplayReference.id))
                        .join(GatewayKey, GatewayKey.id == CodexReplayReference.gateway_key_id)
                        .where(
                            GatewayKey.cohort_id == cohort_id,
                            CodexReplayReference.expires_at
                            == CodexReplayReference.created_at
                            + text("interval '31536000 seconds'"),
                        )
                    )
                ).scalar_one()
            )

    return asyncio.run(_go())


def _expired_count(url: str, cohort_id: uuid.UUID) -> int:
    async def _go() -> int:
        factory = _session_factory(url)
        async with factory() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(CodexReplayReference.id))
                        .join(GatewayKey, GatewayKey.id == CodexReplayReference.gateway_key_id)
                        .where(
                            GatewayKey.cohort_id == cohort_id,
                            CodexReplayReference.expires_at <= datetime.now(UTC),
                        )
                    )
                ).scalar_one()
            )

    return asyncio.run(_go())


@pytest.fixture(scope="module")
def plan_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("slaif200a-plans")


# --- tests (definition order matters: one shared module database) -------------


def test_inspection_is_exact_read_only(world: dict[str, Any], cli_env: str) -> None:
    url = cli_env
    cohort = world["cohort"]
    keys = world["keys"]
    before_refs = _ref_count(url)
    before_audits = _audits_count(url)
    result = _cli("codex", "replay", "inspect", "--cohort-id", str(cohort.id), "--json")
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["scope"] == f"cohort:{cohort.id}"
    assert payload["configured_ttl_seconds"] == TTL_365
    assert payload["keys"] == 8
    assert payload["keys_active_or_valid"] == 4
    assert payload["references"] == 18
    assert payload["active_references"] == 14
    assert payload["expired_references"] == 4
    assert payload["created_min"] == _iso_z(WORLD_NOW - timedelta(days=400))
    assert payload["created_max"] == _iso_z(WORLD_NOW - timedelta(days=10))
    assert payload["expiry_min"] == _iso_z(WORLD_NOW - timedelta(days=3))
    assert payload["expiry_max"] == _iso_z(WORLD_NOW + timedelta(days=999))
    assert payload["exclusion_reasons"] == {
        "key_not_active_or_valid": 4,
        "ledger_not_finalized": 1,
        "unsupported_kind": 0,
        "hmac_version_unavailable": 1,
        "outside_lifetime": 1,
        "expired_not_included": 4,
    }
    groups = payload["route_model_groups"]
    assert len(groups) == 1
    assert groups[0]["requested_model"] == "zap-it-1"
    assert groups[0]["references"] == 18
    assert payload["route_model_groups_total"] == 1
    assert payload["route_model_groups_truncated"] is False
    per_key = {item["key_id"]: item for item in payload["per_key"]}
    assert len(per_key) == 8
    assert per_key[str(keys["active"].id)]["references"] == 7
    assert per_key[str(keys["active"].id)]["expired_references"] == 1
    assert per_key[str(keys["expired"].id)]["expired_references"] == 3
    assert "readiness" in payload["note"]
    # Read-only: zero writes, zero audits.
    assert _ref_count(url) == before_refs
    assert _audits_count(url) == before_audits


def test_dry_run_writes_0600_plan_zero_writes(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    cohort = world["cohort"]
    before_refs = _ref_count(url)
    before_audits = _audits_count(url)
    expiries_before = {
        tag: _row_expiries(url, key.id) for tag, key in world["keys"].items()
    }
    plan_path = plan_dir / "dry.json"
    result = _cli(
        "codex", "replay", "extend", "--cohort-id", str(cohort.id),
        "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    assert stat.S_IMODE(plan_path.stat().st_mode) == 0o600
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["selected_keys"] == 8
    assert payload["eligible_references"] == 7
    assert payload["ttl_is_configured_default"] is True
    assert payload["exclusion_counts"]["expired_not_included"] == 4
    plan = parse_replay_extend_plan_file(plan_path)
    assert plan.selected_keys == 8
    assert plan.eligible_references == 7
    text = plan_path.read_text(encoding="utf-8")
    assert plan.expected_source_fingerprint in text
    assert plan.expected_source_state_fingerprint in text
    assert plan.expected_post_state_fingerprint in text
    # No individual row UUIDs or digests in the reviewed plan file.
    for key_id in world["keys"].values():
        for row_id in _row_expiries(url, key_id.id):
            assert str(row_id) not in text
    for tag in (
        "r_active", "r_late", "r_boundary", "r_expired", "r_ledger_bad",
        "r_version2", "r_old", "r_ttl", "r_rb_a", "r_rb_b",
    ):
        assert _digest(f"item-{tag}") not in text
    # Zero writes: nothing changed at all.
    assert _ref_count(url) == before_refs
    assert _audits_count(url) == before_audits
    for tag, key in world["keys"].items():
        assert _row_expiries(url, key.id) == expiries_before[tag]
    # Reusing the same output path is refused (new file only).
    again = _cli(
        "codex", "replay", "extend", "--cohort-id", str(cohort.id),
        "--output", str(plan_path),
    )
    assert again.exit_code == 1
    assert "new writable file" in _plain(again.stderr)


def test_execute_extends_eligible_monotonically_one_safe_audit(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    k = world["keys"]["active"]
    plan_path = plan_dir / "active-plan.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_keys"] == 1
    assert payload["eligible_references"] == 3
    assert payload["ttl_is_configured_default"] is True
    snapshot = _snapshot_rows(url, k.id)
    expiries_before = _row_expiries(url, k.id)
    audits_before = _audits_count(url)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_path),
        "--reason", "restore long-running conversation", "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["already_applied"] is False
    assert payload["updated_references"] == 2
    target = (WORLD_NOW - timedelta(days=10)) + timedelta(seconds=TTL_365)
    ids = {
        tag: _row_id_for_digest(url, k.id, _digest(f"item-{tag}"))
        for tag in (
            "r_active", "r_late", "r_boundary", "r_expired",
            "r_ledger_bad", "r_version2", "r_old",
        )
    }
    assert expiries_before[ids["r_active"]] == (WORLD_NOW - timedelta(days=10)) + timedelta(days=90)
    expiries = _row_expiries(url, k.id)
    assert expiries[ids["r_active"]] == target
    assert expiries[ids["r_boundary"]] == target
    # Monotonic no-shorten and untouched exclusions.
    assert expiries[ids["r_late"]] == WORLD_NOW + timedelta(days=999)
    assert expiries[ids["r_expired"]] == WORLD_NOW - timedelta(days=1)
    assert expiries[ids["r_ledger_bad"]] == (WORLD_NOW - timedelta(days=10)) + timedelta(days=90)
    assert expiries[ids["r_version2"]] == (WORLD_NOW - timedelta(days=10)) + timedelta(days=90)
    assert expiries[ids["r_old"]] == WORLD_NOW + timedelta(days=90)
    # Every column unchanged except expires_at of the two extended rows.
    after = _snapshot_rows(url, k.id)
    assert set(after) == set(snapshot)
    updated_ids = {ids["r_active"], ids["r_boundary"]}
    for row_id, before in snapshot.items():
        assert after[row_id] == (before[:13] + (target,)) if row_id in updated_ids else before
    # Exactly one safe audit, free of digests and row UUIDs.
    audits = _audits_for_action(url)
    assert len(audits) == audits_before + 1
    entry = audits[-1]
    assert entry.action == "codex_replay_references_extended"
    assert entry.entity_type == "codex_replay_references"
    assert entry.entity_id is None
    assert entry.note == "restore long-running conversation"
    old = entry.old_values
    assert old["operation"] == "extend"
    assert old["scope"] == f"key:{k.id}"
    assert old["ttl_seconds"] == TTL_365
    assert old["selected_keys"] == 1
    assert old["eligible_references"] == 3
    assert old["extended_references"] == 2
    payload_text = json.dumps(
        {"old": old, "new": entry.new_values, "note": entry.note}, default=str
    )
    for tag in ids:
        assert _digest(f"item-{tag}") not in payload_text
    for row_id in snapshot:
        assert str(row_id) not in payload_text


def test_repeat_execute_is_already_applied_no_duplicate_audit(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    k = world["keys"]["active"]
    expiries = _row_expiries(url, k.id)
    audits_before = _audits_count(url)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_dir / "active-plan.json"),
        "--reason", "idempotent repeat", "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is False
    assert payload["already_applied"] is True
    assert payload["updated_references"] == 0
    assert _row_expiries(url, k.id) == expiries
    assert _audits_count(url) == audits_before  # still exactly one audit


def test_unrelated_change_just_short_of_target_fails_stale(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    k = world["keys"]["rollback"]
    plan_path = plan_dir / "rollback-short.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["eligible_references"] == 2
    target = (WORLD_NOW - timedelta(days=10)) + timedelta(seconds=TTL_365)
    rb_a = _row_id_for_digest(url, k.id, _digest("item-r_rb_a"))
    rb_b = _row_id_for_digest(url, k.id, _digest("item-r_rb_b"))
    # An unrelated operator edit stops just SHORT of the reviewed target.
    _raw_update_expiry(url, rb_a, target - timedelta(days=1))
    audits_before = _audits_count(url)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_path),
        "--reason", "should be stale", "--json",
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stdout)
    assert error_payload["error"]["code"] == "invalid_value"
    assert "pre-state no longer matches" in error_payload["error"]["message"]
    assert _audits_count(url) == audits_before
    expiries = _row_expiries(url, k.id)
    assert expiries[rb_a] == target - timedelta(days=1)  # failed op wrote nothing
    assert expiries[rb_b] == (WORLD_NOW - timedelta(days=10)) + timedelta(days=90)


def test_eligibility_boundary_crossed_fails_stale(
    world: dict[str, Any], cli_env: str
) -> None:
    url = cli_env
    k = world["keys"]["ttl"]
    created = WORLD_NOW - timedelta(days=10)
    audits_before = _audits_count(url)
    expiries_before = _row_expiries(url, k.id)

    async def _go() -> None:
        factory = _session_factory(url)
        async with factory() as session:
            service = _service_for(url, session)
            plan = await service.preview_replay_extend(
                scope=ReplayScope(key_id=k.id), now=WORLD_NOW
            )
            assert plan.eligible_references == 1
            # The original-age target is crossed while the plan waits.
            later = created + timedelta(seconds=TTL_365 + 1)
            with pytest.raises(ReplayMaintenanceStaleError):
                await service.apply_replay_extend(
                    plan=plan, reason="crossed original-age target", now=later
                )

    asyncio.run(_go())
    assert _row_expiries(url, k.id) == expiries_before
    assert _audits_count(url) == audits_before


def test_include_expired_restores_explicitly_included(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    k = world["keys"]["expired"]
    default_path = plan_dir / "exp-default.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--output", str(default_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["eligible_references"] == 1
    assert payload["exclusion_counts"]["expired_not_included"] == 3
    incl_path = plan_dir / "exp-include.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--include-expired", "--output", str(incl_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["eligible_references"] == 4
    assert payload["exclusion_counts"]["expired_not_included"] == 0
    audits_before = _audits_count(url)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(incl_path),
        "--reason", "restore explicitly reviewed expired references", "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["updated_references"] == 4
    target = (WORLD_NOW - timedelta(days=10)) + timedelta(seconds=TTL_365)
    expiries = _row_expiries(url, k.id)
    for tag in ("r_exp_a", "r_exp_b", "r_exp_c", "r_exp_ok"):
        assert expiries[_row_id_for_digest(url, k.id, _digest(f"item-{tag}"))] == target
    assert _audits_count(url) == audits_before + 1
    # Now the default scope sees no expired exclusions for this key.
    again = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--output", str(plan_dir / "exp-default2.json"), "--json",
    )
    assert again.exit_code == 0, again.stderr
    payload = json.loads(again.stdout)
    assert payload["eligible_references"] == 4
    assert payload["exclusion_counts"]["expired_not_included"] == 0


def test_explicit_ttl_target_distinct_from_configured(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    # A 1-day reviewed lifetime can only extend a reference created inside
    # the last day; use a dedicated cohort so the main cohort membership
    # (and the later stale proofs) is untouched.
    _cohort_id, k_id, ttl_row, created = _new_key_with_reference(
        url, "replay-ttl", "ttl1d", created_offset=timedelta(hours=2)
    )
    # External edit below the reviewed 1-day target (the review happens after).
    _raw_update_expiry(url, ttl_row, created + timedelta(hours=12))
    plan_path = plan_dir / "ttl86400.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k_id),
        "--ttl-seconds", "86400", "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ttl_seconds"] == 86_400
    assert payload["configured_ttl_seconds"] == TTL_365
    assert payload["ttl_is_configured_default"] is False
    assert payload["eligible_references"] == 1
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_path),
        "--reason", "short reviewed lifetime", "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["updated_references"] == 1
    assert _row_expiries(url, k_id)[ttl_row] == created + timedelta(seconds=86_400)


def test_zero_reference_key_added_between_preview_and_execute_fails_stale(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    cohort = world["cohort"]
    plan_path = plan_dir / "cohort-zero-key.json"
    result = _cli(
        "codex", "replay", "extend", "--cohort-id", str(cohort.id),
        "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_keys"] == 8
    # A zero-reference key joins the reviewed cohort after the review.
    _new_key(url, cohort.id, tag="zerokey")
    audits_before = _audits_count(url)
    expiries_before = _row_expiries(url, world["keys"]["rollback"].id)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_path),
        "--reason", "stale scope growth", "--json",
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stdout)
    assert error_payload["error"]["code"] == "invalid_value"
    assert "pre-state no longer matches" in error_payload["error"]["message"]
    assert _audits_count(url) == audits_before
    assert _row_expiries(url, world["keys"]["rollback"].id) == expiries_before


def test_unrelated_extension_beyond_target_fails_stale(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    k = world["keys"]["rollback"]
    plan_path = plan_dir / "rollback-beyond.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["eligible_references"] == 2
    target = (WORLD_NOW - timedelta(days=10)) + timedelta(seconds=TTL_365)
    rb_a = _row_id_for_digest(url, k.id, _digest("item-r_rb_a"))
    rb_b = _row_id_for_digest(url, k.id, _digest("item-r_rb_b"))
    # An unrelated extension landing BEYOND the reviewed target.
    _raw_update_expiry(url, rb_a, target + timedelta(days=1))
    audits_before = _audits_count(url)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_path),
        "--reason", "stale beyond target", "--json",
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stdout)
    assert error_payload["error"]["code"] == "invalid_value"
    assert "pre-state no longer matches" in error_payload["error"]["message"]
    assert _audits_count(url) == audits_before
    expiries = _row_expiries(url, k.id)
    assert expiries[rb_a] == target + timedelta(days=1)
    assert expiries[rb_b] == (WORLD_NOW - timedelta(days=10)) + timedelta(days=90)


def test_concurrent_cohort_move_during_key_lock_fails_stale(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    import asyncpg
    import threading

    url = cli_env
    plain_url = url.replace("postgresql+asyncpg://", "postgresql://")
    rb = world["keys"]["rollback"]
    plan_path = plan_dir / "cohort-moved.json"
    result = _cli(
        "codex", "replay", "extend", "--cohort-id", str(world["cohort"].id),
        "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    member_count_before = _cohort_key_count(url, world["cohort"].id)
    assert payload["selected_keys"] == member_count_before
    expiries_before = _row_expiries(url, rb.id)
    audits_before = _audits_count(url)
    new_cohort_id = _new_cohort(url, "replay-moved")

    update_done = threading.Event()
    move_error: dict[str, Any] = {"value": None}

    def _move_session() -> None:
        async def _go() -> None:
            conn = await asyncpg.connect(plain_url, timeout=10)
            try:
                await conn.execute("BEGIN")
                await conn.execute(
                    "UPDATE gateway_keys SET cohort_id = $1 WHERE id = $2",
                    new_cohort_id,
                    rb.id,
                )
                update_done.set()
                # Wait until the execute connection blocks on this row lock,
                # then commit the move so ONLY the post-lock revalidation
                # can observe it.
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    # pg_stat_activity serves a CACHED stats snapshot inside
                    # a transaction: clear it before every poll, otherwise a
                    # lock holder inside an open transaction sees 0 waiters.
                    await conn.execute("SELECT pg_stat_clear_snapshot()")
                    waiting = await conn.fetchval(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                    )
                    if waiting:
                        break
                    await asyncio.sleep(0.05)
                else:
                    move_error["value"] = "execute never blocked on the held key row lock"
                    await conn.execute("ROLLBACK")
                    return
                await conn.execute("COMMIT")
            finally:
                await conn.close()

        asyncio.run(_go())

    move_thread = threading.Thread(target=_move_session)
    move_thread.start()
    assert update_done.wait(timeout=60), "cohort move UPDATE did not land uncommitted"
    holder: dict[str, Any] = {}

    def _execute() -> None:
        holder["result"] = _cli(
            "codex", "replay", "extend", "--execute", str(plan_path),
            "--reason", "stale cohort move", "--json",
        )

    execute_thread = threading.Thread(target=_execute)
    execute_thread.start()
    move_thread.join(timeout=180)
    assert not move_thread.is_alive()
    execute_thread.join(timeout=180)
    assert not execute_thread.is_alive()
    result = holder["result"]
    assert move_error["value"] is None, move_error["value"]
    assert result.exit_code == 1
    error_payload = json.loads(result.stdout)
    assert error_payload["error"]["code"] == "invalid_value"
    assert "pre-state no longer matches" in error_payload["error"]["message"]
    # The failed operation wrote nothing; the move itself stands.
    assert _row_expiries(url, rb.id) == expiries_before
    assert _audits_count(url) == audits_before
    assert _key_cohort(url, rb.id) == new_cohort_id
    assert _cohort_key_count(url, world["cohort"].id) == member_count_before - 1


def test_edited_plan_counts_refused_with_real_file(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    k = world["keys"]["ttl"]
    good_path = plan_dir / "ttl-edited-source.json"
    result = _cli(
        "codex", "replay", "extend", "--key-id", str(k.id),
        "--output", str(good_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_keys"] == 1
    assert payload["eligible_references"] == 1
    expiries_before = _row_expiries(url, k.id)
    audits_before = _audits_count(url)
    # Edit ONLY the counts in the reviewed plan file (the strict round-trip
    # gate proves document self-consistency, not count fidelity).
    document = json.loads(good_path.read_text(encoding="utf-8"))
    document["selected_keys"] = 2
    document["eligible_references"] = 2
    forged_path = plan_dir / "ttl-edited-forged.json"
    forged_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(forged_path, 0o600)
    result = _cli(
        "codex", "replay", "extend", "--execute", str(forged_path),
        "--reason", "forged counts", "--json",
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stdout)
    assert error_payload["error"]["code"] == "invalid_value"
    assert "pre-state no longer matches" in error_payload["error"]["message"]
    assert _row_expiries(url, k.id) == expiries_before
    assert _audits_count(url) == audits_before
    # The unedited reviewed plan still applies cleanly; the audit reports
    # the derived fresh counts, never the (here honest) preview metadata.
    result = _cli(
        "codex", "replay", "extend", "--execute", str(good_path),
        "--reason", "honest apply", "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["updated_references"] == 1
    audits = _audits_for_action(url)
    assert audits[-1].old_values["selected_keys"] == 1
    assert audits[-1].old_values["eligible_references"] == 1
    assert audits[-1].old_values["extended_references"] == 1


def test_late_audit_failure_rolls_back_atomically(world: dict[str, Any], cli_env: str) -> None:
    url = cli_env
    audits_before = _audits_count(url)
    _cohort_id, key_id, row_id, created = _new_key_with_reference(url, "replay-late", "late")
    expiries_before = _row_expiries(url, key_id)
    target = created + timedelta(seconds=TTL_365)

    class _LateAuditRepository:
        def __init__(self, session: Any, row_id: uuid.UUID, target: datetime) -> None:
            self._session = session
            self._row_id = row_id
            self._target = target
            self.checked = False

        async def add_audit_log(self, **kwargs: Any) -> None:
            # SAME transaction: the updated row must already be visible.
            result = await self._session.execute(
                select(CodexReplayReference.expires_at).where(
                    CodexReplayReference.id == self._row_id
                )
            )
            visible = result.scalar_one()
            assert visible == self._target, "updated row not visible in same transaction"
            self.checked = True
            raise RuntimeError("forced late audit failure")

    async def _go() -> None:
        factory = _session_factory(url)
        async with factory() as session:
            late = _LateAuditRepository(session, row_id, target)
            service = CodexReplayMaintenanceService(
                repository=CodexReplayReferencesRepository(session),
                audit_repository=late,  # type: ignore[arg-type]
                settings=get_settings(),
            )
            plan = await service.preview_replay_extend(
                scope=ReplayScope(key_id=key_id), now=datetime.now(UTC)
            )
            assert plan.eligible_references == 1
            message = ""
            try:
                await service.apply_replay_extend(
                    plan=plan, reason="late audit failure", actor_admin_id=None
                )
            except RuntimeError as exc:
                message = str(exc)
            assert message == "forced late audit failure"
            assert late.checked
        # Context exit: the uncommitted transaction rolls back here.

    asyncio.run(_go())
    # A fresh session sees the original state; no audit row was committed.
    assert _row_expiries(url, key_id) == expiries_before
    assert _audits_count(url) == audits_before


def test_scale_single_reviewed_operation_bulk(
    world: dict[str, Any], cli_env: str, plan_dir: Path
) -> None:
    url = cli_env
    cohort = world["cohort_bulk"]
    audits_before = _audits_count(url)
    result = _cli(
        "codex", "replay", "inspect", "--cohort-id", str(cohort.id), "--json"
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["keys"] == 26
    assert payload["keys_active_or_valid"] == 26
    assert payload["references"] == 20_451
    assert payload["active_references"] == 20_360
    assert payload["expired_references"] == 91
    assert payload["created_min"] == _iso_z(WORLD_NOW - timedelta(days=14))
    assert payload["created_max"] == _iso_z(WORLD_NOW - timedelta(days=10))
    assert payload["expiry_min"] == _iso_z(WORLD_NOW - timedelta(hours=24))
    assert payload["expiry_max"] == _iso_z(WORLD_NOW - timedelta(days=10) + timedelta(days=90))
    assert payload["exclusion_reasons"]["expired_not_included"] == 91
    assert payload["exclusion_reasons"]["key_not_active_or_valid"] == 0
    groups = payload["route_model_groups"]
    assert len(groups) == 1
    assert groups[0]["references"] == 20_451
    created_before, created_count = _created_digest(url, cohort.id)
    assert created_count == 20_451
    plan_path = plan_dir / "bulk-plan.json"
    result = _cli(
        "codex", "replay", "extend", "--cohort-id", str(cohort.id),
        "--include-expired", "--output", str(plan_path), "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_keys"] == 26
    assert payload["eligible_references"] == 20_451
    # ONE reviewed operation carries the whole scale (chunked UPDATEs).
    result = _cli(
        "codex", "replay", "extend", "--execute", str(plan_path),
        "--reason", "restore reviewed bulk references", "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["already_applied"] is False
    assert payload["updated_references"] == 20_451
    # Every row now carries exactly original creation + 365d (created_at
    # intact) and the 91 previously-expired references are restored.
    assert _exact_target_count(url, cohort.id) == 20_451
    assert _expired_count(url, cohort.id) == 0
    created_after, created_count_after = _created_digest(url, cohort.id)
    assert created_after == created_before
    assert created_count_after == 20_451
    assert _audits_count(url) == audits_before + 1
