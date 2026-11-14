"""Real owned-PostgreSQL-16 evidence for objective 224-a demo control.

Proves, against ONE NEW owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL 16 (the ``owned_pg_url`` fixture - never an ambient
DATABASE_URL fallback):

- migration 0028 creates both demo-control tables in the existing
  ``demo_control`` schema and grants NOTHING (a fresh probe role holds
  no schema/table privileges; the new tables carry no ACL at all);
- the tables are NOT in ``public``: 221's ``pg_dump --schema=public``
  exclusion law is structurally unchanged (accepted 221 evidence for the
  dump itself);
- strict downgrade to 0027 drops exactly the two 0028 tables (schema and
  0027 tables survive) and re-upgrade restores them;
- the reviewed grant matrix (web/worker) is applied and the REAL
  restricted-role service methods execute under it: web creates a
  request (column-limited INSERT; the state column is DB-defaulted,
  never web-written), worker claims/verifies (column-level UPDATE +
  atomic guarded transitions - no FOR UPDATE anywhere), web issues and
  revokes sessions, and the worker's cleanup observes the revocation;
- every forbidden surface is denied with 42501: web cannot write any
  request column (state/worker fields), write fake-admin accounts, or
  read business tables; the worker cannot insert request/session rows,
  cannot SELECT username/password_hash on accounts, and cannot SELECT
  token_hash on sessions;
- the row-locking privilege law is enforced: neither role can FOR SHARE
  account rows (column-SELECT-only grants) and the web role cannot FOR
  SHARE request rows (no UPDATE grant at all), while the worker CAN FOR
  SHARE request rows (column-level UPDATE held); the credential fence
  instead rides STATEMENT-TIME inside the guarded worker CAS, so a
  mid-job reset/disable makes the transition match 0 rows and no stale
  worker result can ever reach verified_unpublished or carry a session;
- concurrent claims are exactly-once (row lock + guarded transition);
- a stale account (disable/reset) mid-job refuses the handoff; a late
  verified result is refused (failed/late_completion);
- session tokens are never stored raw: only the SHA-256 hash exists in
  the table and the raw canary token is absent from every stored value;
- safe errors never echo canaries;
- exact run-owned cleanup removes only the created rows/roles.

No provider HTTP, no Redis, no normal admin auth, no email. Ownership
discipline mirrors the 199/201/218/220 owned fixtures: unique owner
label, loopback-bound, tmpfs-backed PostgreSQL 16, identity inspected
BEFORE readiness/migration, cleanup removes ONLY the exact created
container ID.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import FakeAdminAccount
from slaif_gateway.services.demo_web_control import (
    VERIFIED_COPY_STATE,
    DemoWebControlError,
    DemoWebControlService,
    VerifiedCopyBinding,
    hash_opaque_token,
    web_role_grant_sql,
    worker_role_grant_sql,
)
from slaif_gateway.utils.passwords import hash_admin_password
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif224a"
_WEB_ROLE = "slaif224a_web"
_WORKER_ROLE = "slaif224a_worker"
_PROBE_ROLE = "slaif224a_probe"
_PREVIOUS_HEAD = "0027_demo_admin_accounts"
_CURRENT_HEAD = "0028_demo_web_control"

_STATE: dict[str, Any] = {}
_RUN_IDS: dict[str, Any] = {"requests": [], "sessions": [], "accounts": [], "tokens": []}


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
                        "postgresql://test:test@127.0.0.1:%d/test" % port, timeout=3
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


# --- helpers -----------------------------------------------------------------


def _role_url(owned_pg_url: str, role: str, password: str) -> str:
    return owned_pg_url.replace("test:test", f"{role}:{password}")


def _session_factory(url: str) -> async_sessionmaker:
    return async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)


async def _scalar(url: str, sql: str, params: dict[str, Any] | None = None) -> Any:
    engine = create_async_engine(url, future=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _scalar_many(url: str, sql: str, params: dict[str, Any] | None = None) -> list:
    engine = create_async_engine(url, future=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return list(result.all())
    finally:
        await engine.dispose()


async def _exec(url: str, sql: str) -> None:
    engine = create_async_engine(url, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
    finally:
        await engine.dispose()


def _alembic_config(url: str) -> Config:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _seed_account(url: str, username: str) -> uuid.UUID:
    """Seed one enabled account through the trusted (DB-owner) path."""
    account_id = uuid.uuid4()

    async def run() -> None:
        factory = _session_factory(url)
        async with factory() as session, session.begin():
            session.add(
                FakeAdminAccount(
                    id=account_id,
                    username=username,
                    password_hash=hash_admin_password(f"seed-{uuid.uuid4().hex}"),
                    is_enabled=True,
                    credential_generation=0,
                )
            )

    asyncio.run(run())
    _RUN_IDS["accounts"].append(str(account_id))
    return account_id


async def _set_account_generation(url: str, account_id: uuid.UUID, generation: int) -> None:
    engine = create_async_engine(url, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE demo_control.fake_admin_accounts "
                    "SET credential_generation = :g, is_enabled = :e WHERE id = :id"
                ),
                {"g": generation, "e": True, "id": str(account_id)},
            )
    finally:
        await engine.dispose()


def _canary(tag: str) -> str:
    return f"224a-{tag}-{uuid.uuid4().hex}"


# --- migration shape / no grants / public exclusion ----------------------------


@pytest.mark.asyncio
async def test_migration_0028_shape_no_grants_not_public(owned_pg_url: str) -> None:
    revision = await _scalar(owned_pg_url, "SELECT version_num FROM alembic_version")
    assert revision == _CURRENT_HEAD

    for table in ("demo_snapshot_requests", "demo_web_sessions"):
        exists = await _scalar(
            owned_pg_url,
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'demo_control' AND table_name = :t)",
            {"t": table},
        )
        assert exists is True, table
        # NOT in public: 221's pg_dump --schema=public exclusion is intact.
        in_public = await _scalar(
            owned_pg_url,
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t)",
            {"t": table},
        )
        assert in_public is False, table
        # No explicit ACL at all: the migration grants nothing.
        no_acl = await _scalar(
            owned_pg_url,
            "SELECT relacl IS NULL FROM pg_class c JOIN pg_namespace n "
            "ON n.oid = c.relnamespace WHERE n.nspname = 'demo_control' "
            "AND c.relname = :t",
            {"t": table},
        )
        assert no_acl is True, table

    # A role created AFTER the migration holds no privileges at all.
    probe_exists = await _scalar(
        owned_pg_url,
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)",
        {"r": _PROBE_ROLE},
    )
    if not probe_exists:
        await _exec(owned_pg_url, f"CREATE ROLE {_PROBE_ROLE} NOLOGIN")
    assert (
        await _scalar(
            owned_pg_url,
            f"SELECT has_schema_privilege('{_PROBE_ROLE}', 'demo_control', 'USAGE')",
        )
        is False
    )
    for table in ("demo_snapshot_requests", "demo_web_sessions"):
        assert (
            await _scalar(
                owned_pg_url,
                f"SELECT has_table_privilege('{_PROBE_ROLE}', 'demo_control.{table}', 'SELECT')",
            )
            is False
        )


# --- strict downgrade / re-upgrade ---------------------------------------------


def test_strict_downgrade_reupgrade(owned_pg_url: str) -> None:
    config = _alembic_config(owned_pg_url)
    command.downgrade(config, _PREVIOUS_HEAD)

    async def shape() -> None:
        for table in ("demo_snapshot_requests", "demo_web_sessions"):
            gone = await _scalar(
                owned_pg_url,
                "SELECT NOT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'demo_control' AND table_name = :t)",
                {"t": table},
            )
            assert gone is True, table
        # schema + 0027 tables survive
        schema = await _scalar(
            owned_pg_url,
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'demo_control')",
        )
        assert schema is True
        accounts = await _scalar(
            owned_pg_url,
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'demo_control' AND table_name = 'fake_admin_accounts')",
        )
        assert accounts is True

    asyncio.run(shape())

    command.upgrade(config, "head")

    async def shape2() -> None:
        for table in ("demo_snapshot_requests", "demo_web_sessions"):
            back = await _scalar(
                owned_pg_url,
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'demo_control' AND table_name = :t)",
                {"t": table},
            )
            assert back is True, table
        revision = await _scalar(
            owned_pg_url, "SELECT version_num FROM alembic_version"
        )
        assert revision == _CURRENT_HEAD

    asyncio.run(shape2())


# --- role setup ------------------------------------------------------------------


@pytest.fixture(scope="module")
def role_credentials(owned_pg_url: str) -> dict[str, str]:
    web_pw = _canary("web")
    worker_pw = _canary("worker")

    async def setup() -> None:
        for role, pw in ((_WEB_ROLE, web_pw), (_WORKER_ROLE, worker_pw)):
            exists = await _scalar(
                owned_pg_url, "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)",
                {"r": role},
            )
            if not exists:
                await _exec(owned_pg_url, f"CREATE ROLE {role} LOGIN PASSWORD '{pw}'")
        await _exec(owned_pg_url, f"GRANT CONNECT ON DATABASE test TO {_WEB_ROLE}")
        await _exec(owned_pg_url, f"GRANT CONNECT ON DATABASE test TO {_WORKER_ROLE}")

    asyncio.run(setup())
    return {"web": web_pw, "worker": worker_pw}


@pytest.fixture(scope="module")
def grants_applied(owned_pg_url: str, role_credentials: dict[str, str]) -> None:
    """Apply the reviewed grant matrix exactly once for the module."""
    async def setup() -> None:
        for statement in web_role_grant_sql(_WEB_ROLE):
            await _exec(owned_pg_url, statement)
        for statement in worker_role_grant_sql(_WORKER_ROLE):
            await _exec(owned_pg_url, statement)

    asyncio.run(setup())


def _denied(url: str, sql: str, params: dict[str, Any] | None = None) -> None:
    """Assert the SQL is refused with 42501 (insufficient privilege)."""

    async def run() -> None:
        import asyncpg

        # convert the asyncpg URL form
        raw = url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(raw, timeout=5)
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(sql, *(params or {}).values())
        finally:
            await conn.close()

    asyncio.run(run())


# --- grant matrix denials ----------------------------------------------------------


def test_role_grant_matrix_denials(
    owned_pg_url: str, role_credentials: dict[str, str], grants_applied: None
) -> None:
    web_url = _role_url(owned_pg_url, _WEB_ROLE, role_credentials["web"])
    worker_url = _role_url(owned_pg_url, _WORKER_ROLE, role_credentials["worker"])

    # WEB denials
    _denied(web_url, "UPDATE demo_control.demo_snapshot_requests SET state = 'claimed'")
    _denied(
        web_url,
        "INSERT INTO demo_control.demo_snapshot_requests "
        "(id, account_id, credential_generation, state, created_at, deadline_at, expires_at) "
        "VALUES (gen_random_uuid(), gen_random_uuid(), 0, 'verified_unpublished', "
        "now(), now() + interval '15 minutes', now() + interval '60 minutes')",
    )
    _denied(
        web_url,
        "UPDATE demo_control.demo_snapshot_requests SET worker_job_id = 'snap_"
        + "0" * 32
        + "'",
    )
    _denied(
        web_url,
        "INSERT INTO demo_control.fake_admin_accounts "
        "(id, username, password_hash, is_enabled, credential_generation, "
        "created_at, updated_at) VALUES (gen_random_uuid(), 'deniedweb', 'x', true, 0, "
        "now(), now())",
    )
    _denied(web_url, "UPDATE demo_control.fake_admin_accounts SET is_enabled = false")
    _denied(web_url, "SELECT * FROM public.gateway_keys LIMIT 1")

    # WORKER denials
    _denied(
        worker_url,
        "INSERT INTO demo_control.demo_snapshot_requests "
        "(id, account_id, credential_generation, state, created_at, deadline_at, "
        "expires_at) VALUES (gen_random_uuid(), gen_random_uuid(), 0, 'pending', now(), "
        "now() + interval '15 minutes', now() + interval '60 minutes')",
    )
    _denied(
        worker_url,
        "INSERT INTO demo_control.demo_web_sessions "
        "(id, token_hash, account_id, credential_generation, request_id, created_at, "
        "expires_at) VALUES (gen_random_uuid(), '" + "0" * 64 + "', gen_random_uuid(), 0, "
        "gen_random_uuid(), now(), now())",
    )
    _denied(worker_url, "UPDATE demo_control.demo_web_sessions SET revoked_at = now()")
    _denied(worker_url, "SELECT username FROM demo_control.fake_admin_accounts LIMIT 1")
    _denied(
        worker_url,
        "SELECT password_hash FROM demo_control.fake_admin_accounts LIMIT 1",
    )
    # Row-locking law (PostgreSQL 16 privilege docs): FOR SHARE/FOR UPDATE
    # need UPDATE on at least one column of the locked table. The
    # column-SELECT-only account grant cannot row-lock the account table
    # ...
    _denied(
        worker_url,
        "SELECT id FROM demo_control.fake_admin_accounts "
        "WHERE id = gen_random_uuid() FOR SHARE",
    )
    # ...and the web role holds NO UPDATE on the request table, so it
    # cannot row-lock request rows either (its request reads are plain
    # MVCC SELECTs).
    _denied(
        web_url,
        "SELECT id FROM demo_control.demo_snapshot_requests "
        "WHERE id = gen_random_uuid() FOR SHARE",
    )
    # The worker role DOES hold column-level UPDATE on the request table,
    # so FOR SHARE on request rows is its one legal lock form.
    worker_lockable = asyncio.run(
        _scalar(
            worker_url,
            "SELECT count(*) FROM (SELECT id FROM "
            "demo_control.demo_snapshot_requests "
            "WHERE id = gen_random_uuid() FOR SHARE) AS s",
        )
    )
    assert worker_lockable == 0
    # the worker may read the session FACTS but never the token hash
    allowed = asyncio.run(
        _scalar(
            worker_url,
            "SELECT count(*) FROM (SELECT id, request_id, expires_at, revoked_at "
            "FROM demo_control.demo_web_sessions) AS facts",
        )
    )
    assert allowed == 0  # table exists and is readable (empty at setup)
    _denied(worker_url, "SELECT token_hash FROM demo_control.demo_web_sessions LIMIT 1")
    _denied(worker_url, "SELECT account_id FROM demo_control.demo_web_sessions LIMIT 1")
    _denied(worker_url, "SELECT * FROM public.gateway_keys LIMIT 1")


# --- real restricted-role service execution ---------------------------------------


def test_restricted_role_service_lifecycle(
    owned_pg_url: str, role_credentials: dict[str, str], grants_applied: None
) -> None:
    web_url = _role_url(owned_pg_url, _WEB_ROLE, role_credentials["web"])
    worker_url = _role_url(owned_pg_url, _WORKER_ROLE, role_credentials["worker"])
    account_id = _seed_account(owned_pg_url, f"demo_{uuid.uuid4().hex[:12]}")
    job_id = "snap-" + uuid.uuid4().hex
    target_db = "demo_snap_" + uuid.uuid4().hex[:20]

    async def run() -> None:
        # WEB: create the request (column-limited INSERT under the grant)
        web_factory = _session_factory(web_url)
        async with web_factory() as session, session.begin():
            created = await DemoWebControlService(session).create_request(
                account_id=account_id
            )
        assert created.state == "pending"
        _RUN_IDS["requests"].append(str(created.id))

        # the state came from the DB default, not from any web write
        stored_state = await _scalar(
            owned_pg_url,
            "SELECT state FROM demo_control.demo_snapshot_requests WHERE id = :id",
            {"id": str(created.id)},
        )
        assert stored_state == "pending"

        # WEB: cannot issue a session for an unverified copy
        async with web_factory() as session:
            with pytest.raises(DemoWebControlError) as exc:
                await DemoWebControlService(session).create_session(
                    account_id=account_id, request_id=created.id
                )
            assert exc.value.code == "web_request_not_verified"

        # WORKER: claim + verified handoff under column-level UPDATE grants
        worker_factory = _session_factory(worker_url)
        async with worker_factory() as session, session.begin():
            claimed = await DemoWebControlService(session).claim_request(
                request_id=created.id
            )
        assert claimed.state == "claimed"
        async with worker_factory() as session, session.begin():
            verified = await DemoWebControlService(session).record_verified_handoff(
                request_id=created.id,
                binding=VerifiedCopyBinding(
                    worker_job_id=job_id,
                    worker_target_db=target_db,
                    manifest_state=VERIFIED_COPY_STATE,
                ),
            )
        assert verified.state == "verified_unpublished"
        assert verified.worker_job_id == job_id
        assert verified.worker_target_db == target_db

        # WORKER: facts-only account read works (no username/password_hash)
        # - plain SELECT: row locks on the account table are impossible
        # under the column-SELECT-only grant (proven in the denial
        # matrix above), so the facts read is lock-free by design.
        from slaif_gateway.db.repositories.fake_admin_accounts import (
            FakeAdminAccountsRepository,
        )

        async with worker_factory() as session:
            facts = await FakeAdminAccountsRepository(session).get_account_facts(
                account_id, read_lock=False
            )
        assert facts is not None and facts.is_enabled is True

        # WEB: issue a session (raw token returned once)
        async with web_factory() as session, session.begin():
            issued = await DemoWebControlService(session).create_session(
                account_id=account_id, request_id=created.id
            )
        canary_token = issued.token
        _RUN_IDS["sessions"].append(str(issued.session.id))
        _RUN_IDS["tokens"].append(canary_token)

        # WEB: validate
        async with web_factory() as session:
            ok = await DemoWebControlService(session).validate_session(
                account_id=account_id, token=canary_token
            )
        assert ok.id == issued.session.id

        # WORKER: cleanup refused while the live session binds the copy
        async with worker_factory() as session:
            with pytest.raises(DemoWebControlError) as exc:
                await DemoWebControlService(session).mark_cleanup_pending(
                    request_id=created.id
                )
            assert exc.value.code == "web_cleanup_refused_live_session"

        # WEB: revoke (column-level UPDATE(revoked_at) only)
        async with web_factory() as session, session.begin():
            revoked = await DemoWebControlService(session).revoke_session(
                account_id=account_id, token=canary_token
            )
        assert revoked is not None and revoked.revoked_at is not None

        # WORKER: detects the revocation and cleanup proceeds
        async with worker_factory() as session, session.begin():
            cp = await DemoWebControlService(session).mark_cleanup_pending(
                request_id=created.id
            )
        assert cp.state == "cleanup_pending"
        async with worker_factory() as session, session.begin():
            cleaned = await DemoWebControlService(session).mark_cleaned(
                request_id=created.id
            )
        assert cleaned.state == "cleaned"

        # safe projection never carries the raw token
        safe = issued.session.to_safe_dict()
        assert canary_token not in str(safe)
        assert "token_hash" not in safe

    asyncio.run(run())


@pytest.mark.asyncio
async def test_token_never_stored_raw(owned_pg_url: str) -> None:
    tokens = _RUN_IDS["tokens"]
    assert tokens, "the lifecycle test must have issued at least one token"
    for token in tokens:
        # exactly one stored SHA-256 hash per issued token (64 lowercase hex)
        hash_rows = await _scalar(
            owned_pg_url,
            "SELECT count(*) FROM demo_control.demo_web_sessions "
            "WHERE token_hash = :h AND token_hash ~ '^[0-9a-f]{64}$'",
            {"h": hash_opaque_token(token)},
        )
        assert hash_rows == 1, "exactly one stored hash per issued token"
        # the RAW token must not appear in ANY demo_control row, any column
        leaked = await _scalar(
            owned_pg_url,
            "SELECT (SELECT count(*) FROM demo_control.demo_web_sessions s "
            "WHERE to_jsonb(s)::text LIKE :p) + "
            "(SELECT count(*) FROM demo_control.demo_snapshot_requests r "
            "WHERE to_jsonb(r)::text LIKE :p) + "
            "(SELECT count(*) FROM demo_control.fake_admin_accounts a "
            "WHERE to_jsonb(a)::text LIKE :p)",
            {"p": f"%{token}%"},
        )
        assert leaked == 0, "raw token leaked into a stored value"


def test_concurrent_claims_exactly_once(
    owned_pg_url: str, role_credentials: dict[str, str], grants_applied: None
) -> None:
    web_url = _role_url(owned_pg_url, _WEB_ROLE, role_credentials["web"])
    worker_url = _role_url(owned_pg_url, _WORKER_ROLE, role_credentials["worker"])
    account_id = _seed_account(owned_pg_url, f"demo_{uuid.uuid4().hex[:12]}")

    async def run() -> None:
        web_factory = _session_factory(web_url)
        async with web_factory() as session, session.begin():
            created = await DemoWebControlService(session).create_request(
                account_id=account_id
            )
        request_id = created.id
        _RUN_IDS["requests"].append(str(request_id))

        async def claim_once() -> str:
            factory = _session_factory(worker_url)
            async with factory() as session, session.begin():
                try:
                    result = await DemoWebControlService(session).claim_request(
                        request_id=request_id
                    )
                    return result.state
                except DemoWebControlError as exc:
                    return exc.code

        outcomes = await asyncio.gather(claim_once(), claim_once(), claim_once())
        assert outcomes.count("claimed") == 1, outcomes
        assert all(
            o == "web_request_not_pending" for o in outcomes if o != "claimed"
        ), outcomes
        final = await _scalar(
            owned_pg_url,
            "SELECT state FROM demo_control.demo_snapshot_requests WHERE id = :id",
            {"id": str(request_id)},
        )
        assert final == "claimed"

    asyncio.run(run())


def test_stale_account_mid_job_refuses_handoff(
    owned_pg_url: str, role_credentials: dict[str, str], grants_applied: None
) -> None:
    web_url = _role_url(owned_pg_url, _WEB_ROLE, role_credentials["web"])
    worker_url = _role_url(owned_pg_url, _WORKER_ROLE, role_credentials["worker"])
    account_id = _seed_account(owned_pg_url, f"demo_{uuid.uuid4().hex[:12]}")

    async def run() -> None:
        web_factory = _session_factory(web_url)
        async with web_factory() as session, session.begin():
            created = await DemoWebControlService(session).create_request(
                account_id=account_id
            )
        _RUN_IDS["requests"].append(str(created.id))
        worker_factory = _session_factory(worker_url)
        async with worker_factory() as session, session.begin():
            await DemoWebControlService(session).claim_request(request_id=created.id)
        # generation moves (password reset) mid-job
        await _set_account_generation(owned_pg_url, account_id, 1)
        async with worker_factory() as session, session.begin():
            result = await DemoWebControlService(session).record_verified_handoff(
                request_id=created.id,
                binding=VerifiedCopyBinding(
                    worker_job_id="snap-" + uuid.uuid4().hex,
                    worker_target_db="demo_snap_" + uuid.uuid4().hex[:20],
                    manifest_state=VERIFIED_COPY_STATE,
                ),
            )
        assert result.state == "failed"
        assert result.failure_code == "state_conflict"

        # disable also refuses
        async with web_factory() as session, session.begin():
            created2 = await DemoWebControlService(session).create_request(
                account_id=account_id
            )
        _RUN_IDS["requests"].append(str(created2.id))
        async with worker_factory() as session, session.begin():
            await DemoWebControlService(session).claim_request(request_id=created2.id)
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE demo_control.fake_admin_accounts "
                        "SET is_enabled = false WHERE id = :id"
                    ),
                    {"id": str(account_id)},
                )
        finally:
            await engine.dispose()
        async with worker_factory() as session, session.begin():
            result2 = await DemoWebControlService(session).record_verified_handoff(
                request_id=created2.id,
                binding=VerifiedCopyBinding(
                    worker_job_id="snap-" + uuid.uuid4().hex,
                    worker_target_db="demo_snap_" + uuid.uuid4().hex[:20],
                    manifest_state=VERIFIED_COPY_STATE,
                ),
            )
        assert result2.state == "failed"
        assert result2.failure_code == "state_conflict"

        # a stale worker result can never become browser-authoritative:
        # neither reset request ever reached verified_unpublished, and
        # NO session row may exist for either failed request
        for failed_request in (created.id, created2.id):
            sessions = await _scalar(
                owned_pg_url,
                "SELECT count(*) FROM demo_control.demo_web_sessions "
                "WHERE request_id = :rid",
                {"rid": str(failed_request)},
            )
            assert sessions == 0
            state = await _scalar(
                owned_pg_url,
                "SELECT state FROM demo_control.demo_snapshot_requests "
                "WHERE id = :id",
                {"id": str(failed_request)},
            )
            assert state == "failed"

    asyncio.run(run())


def test_late_verified_result_refused(
    owned_pg_url: str, role_credentials: dict[str, str], grants_applied: None
) -> None:
    web_url = _role_url(owned_pg_url, _WEB_ROLE, role_credentials["web"])
    worker_url = _role_url(owned_pg_url, _WORKER_ROLE, role_credentials["worker"])
    account_id = _seed_account(owned_pg_url, f"demo_{uuid.uuid4().hex[:12]}")

    async def run() -> None:
        web_factory = _session_factory(web_url)
        async with web_factory() as session, session.begin():
            created = await DemoWebControlService(session).create_request(
                account_id=account_id
            )
        _RUN_IDS["requests"].append(str(created.id))
        worker_factory = _session_factory(worker_url)
        async with worker_factory() as session, session.begin():
            await DemoWebControlService(session).claim_request(request_id=created.id)
        # age the copy past its lifetime (owned test database)
        # - all three timestamps move into the past while preserving
        # the CHECK law created_at < deadline_at < expires_at
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE demo_control.demo_snapshot_requests "
                        "SET created_at = now() - interval '2 minutes', "
                        "deadline_at = now() - interval '1 minute', "
                        "expires_at = now() - interval '30 seconds' "
                        "WHERE id = :id"
                    ),
                    {"id": str(created.id)},
                )
        finally:
            await engine.dispose()
        async with worker_factory() as session, session.begin():
            result = await DemoWebControlService(session).record_verified_handoff(
                request_id=created.id,
                binding=VerifiedCopyBinding(
                    worker_job_id="snap-" + uuid.uuid4().hex,
                    worker_target_db="demo_snap_" + uuid.uuid4().hex[:20],
                    manifest_state=VERIFIED_COPY_STATE,
                ),
            )
        assert result.state == "failed"
        assert result.failure_code == "late_completion"

    asyncio.run(run())


def test_safe_errors_no_canary_echo(
    owned_pg_url: str, role_credentials: dict[str, str], grants_applied: None
) -> None:
    worker_url = _role_url(owned_pg_url, _WORKER_ROLE, role_credentials["worker"])
    account_id = _seed_account(owned_pg_url, f"demo_{uuid.uuid4().hex[:12]}")
    canary_job = "snap-" + "c" * 32
    canary_target = "demo_snap_" + "d" * 20

    async def run() -> None:
        # Two claimed requests, seeded directly by the DB owner (the
        # seed path is trusted; the assertions below run under the
        # restricted worker role only).
        request_id = uuid.uuid4()
        second_id = uuid.uuid4()
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                for rid in (request_id, second_id):
                    await conn.execute(
                        text(
                            "INSERT INTO demo_control.demo_snapshot_requests "
                            "(id, account_id, credential_generation, state, "
                            "created_at, deadline_at, expires_at) VALUES "
                            "(:id, :a, 0, 'claimed', now(), "
                            "now() + interval '15 minutes', "
                            "now() + interval '60 minutes')"
                        ),
                        {"id": str(rid), "a": str(account_id)},
                    )
        finally:
            await engine.dispose()
        _RUN_IDS["requests"].extend(str(rid) for rid in (request_id, second_id))
        factory = _session_factory(worker_url)

        # First handoff: the canary copy is legitimately bound to the
        # first request (the canary identities are now STORED).
        async with factory() as session, session.begin():
            first = await DemoWebControlService(session).record_verified_handoff(
                request_id=request_id,
                binding=VerifiedCopyBinding(
                    worker_job_id=canary_job,
                    worker_target_db=canary_target,
                    manifest_state=VERIFIED_COPY_STATE,
                ),
            )
        assert first.state == "verified_unpublished"

        # Second handoff: the SAME canary copy against another claimed
        # request must be refused by the copy-uniqueness invariant -
        # and the safe error must never echo the stored canary
        # identities.
        messages: list[str] = []
        async with factory() as session:
            with pytest.raises(DemoWebControlError) as exc:
                await DemoWebControlService(session).record_verified_handoff(
                    request_id=second_id,
                    binding=VerifiedCopyBinding(
                        worker_job_id=canary_job,
                        worker_target_db=canary_target,
                        manifest_state=VERIFIED_COPY_STATE,
                    ),
                )
            assert exc.value.code == "web_request_copy_reused"
            messages.append(exc.value.safe_message)
            await session.rollback()
        for message in messages:
            assert canary_job not in message
            assert canary_target not in message

    asyncio.run(run())


# --- exact run-owned cleanup --------------------------------------------------------


@pytest.mark.asyncio
async def test_run_owned_exact_cleanup(owned_pg_url: str) -> None:
    """Delete ONLY the exact run-owned rows/roles; verify zero residue."""
    engine = create_async_engine(owned_pg_url, future=True)
    try:
        async with engine.begin() as conn:
            for sid in _RUN_IDS["sessions"]:
                await conn.execute(
                    text(
                        "DELETE FROM demo_control.demo_web_sessions WHERE id = :id"
                    ),
                    {"id": sid},
                )
            for rid in _RUN_IDS["requests"]:
                await conn.execute(
                    text(
                        "DELETE FROM demo_control.demo_snapshot_requests "
                        "WHERE id = :id"
                    ),
                    {"id": rid},
                )
            for aid in _RUN_IDS["accounts"]:
                await conn.execute(
                    text(
                        "DELETE FROM demo_control.fake_admin_account_events "
                        "WHERE account_id = :id"
                    ),
                    {"id": aid},
                )
                await conn.execute(
                    text(
                        "DELETE FROM demo_control.fake_admin_accounts WHERE id = :id"
                    ),
                    {"id": aid},
                )
            # revoke every grant before dropping: a role that still holds
            # table/schema/column privileges cannot be dropped
            for role in (_WEB_ROLE, _WORKER_ROLE, _PROBE_ROLE):
                await conn.execute(text(f"REVOKE ALL ON SCHEMA demo_control FROM {role}"))
                for table in (
                    "fake_admin_accounts",
                    "demo_snapshot_requests",
                    "demo_web_sessions",
                ):
                    await conn.execute(
                        text(f"REVOKE ALL ON demo_control.{table} FROM {role}")
                    )
                await conn.execute(text(f"REVOKE CONNECT ON DATABASE test FROM {role}"))
            for role in (_WEB_ROLE, _WORKER_ROLE, _PROBE_ROLE):
                await conn.execute(text(f"DROP ROLE IF EXISTS {role}"))
    finally:
        await engine.dispose()

    residue = await _scalar(
        owned_pg_url,
        "SELECT (SELECT count(*) FROM demo_control.demo_web_sessions) + "
        "(SELECT count(*) FROM demo_control.demo_snapshot_requests) + "
        "(SELECT count(*) FROM demo_control.fake_admin_accounts)",
    )
    assert residue == 0, f"run-owned residue remains: {residue}"
    for role in (_WEB_ROLE, _WORKER_ROLE, _PROBE_ROLE):
        gone = await _scalar(
            owned_pg_url,
            "SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)",
            {"r": role},
        )
        assert gone is True, role
