"""Real owned-PostgreSQL-16 evidence for objective 220 demo-admin control.

Proves, against ONE NEW owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL 16 (the qualified ``owned_pg_url`` fixture — never an ambient
DATABASE_URL fallback):

- migration 0027 creates the ``demo_control`` schema with both tables and
  grants NOTHING to any role (a fresh role created after the migration
  has no schema/table privileges);
- the account lifecycle (create/list/enable/disable/reset) writes one
  safe append-only event per real state change with a monotonically
  increasing credential generation, uses salted Argon2id hashes, and
  never persists plaintext;
- duplicate creation (case variant) is the fixed duplicate error;
- disabling the last active account makes the database-side active count
  zero immediately (same transaction) and in the committed state;
- a reset never re-enables a disabled account;
- a failed late event/write rolls back the account change in the same
  transaction (nothing committed);
- an explicitly granted restricted role (SELECT on fake accounts only)
  is refused every INSERT/UPDATE/DELETE on account or event rows and
  every SELECT/DML on business tables;
- the real CLI against this database emits only the safe allowlist and
  never a canary password, hash, or DSN.

No provider HTTP, no Redis, no normal admin auth, no real upstream
contact, no email. Ownership discipline mirrors the 199/201/218 owned
fixtures: unique owner label, loopback-bound, tmpfs-backed PostgreSQL 16,
identity inspected BEFORE readiness/migration, cleanup removes ONLY the
exact created container ID.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import get_settings
from slaif_gateway.db.models import (
    FakeAdminAccount,
    FakeAdminAccountEvent,
)
from slaif_gateway.services.fake_admin_accounts import (
    FakeAdminAccountError,
    FakeAdminAccountService,
)
from slaif_gateway.utils.passwords import verify_admin_password
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif220a"

_PROBE_ROLE = "slaif220a_probe"
_WEB_ROLE = "slaif220a_web"

_STATE: dict[str, Any] = {}


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


def _unique_username(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _password(tag: str) -> str:
    # Synthetic canary password: strong, bounded, unique per test run.
    return f"demo-{tag}-{uuid.uuid4().hex}"


def _session_factory(url: str) -> async_sessionmaker:
    return async_sessionmaker(
        create_async_engine(url, future=True), expire_on_commit=False
    )


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


# --- migration shape / no grants ---------------------------------------------


@pytest.mark.asyncio
async def test_migration_created_demo_control_schema_tables_and_no_grants(
    owned_pg_url: str,
) -> None:
    revision = await _scalar(
        owned_pg_url, "SELECT version_num FROM alembic_version"
    )
    assert revision == "0027_demo_admin_accounts"

    schema_exists = await _scalar(
        owned_pg_url,
        "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'demo_control')",
    )
    assert schema_exists is True

    for table in ("fake_admin_accounts", "fake_admin_account_events"):
        exists = await _scalar(
            owned_pg_url,
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'demo_control' AND table_name = :t)",
            {"t": table},
        )
        assert exists is True, table

    # A role created AFTER the migration must hold no privileges at all:
    # the migration creates no roles and grants nothing.
    # _PROBE_ROLE is a fixed synthetic test identifier (owned fresh
    # container); existence is checked with a bound parameter so no SQL
    # interpolation is needed for the identifier lookup.
    probe_exists = await _scalar(
        owned_pg_url,
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)",
        {"r": _PROBE_ROLE},
    )
    if not probe_exists:
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"CREATE ROLE {_PROBE_ROLE} NOLOGIN"))
        finally:
            await engine.dispose()

    assert (
        await _scalar(
            owned_pg_url,
            f"SELECT has_schema_privilege('{_PROBE_ROLE}', 'demo_control', 'USAGE')",
        )
        is False
    )
    for table in ("fake_admin_accounts", "fake_admin_account_events"):
        assert (
            await _scalar(
                owned_pg_url,
                f"SELECT has_table_privilege('{_PROBE_ROLE}', 'demo_control.{table}', 'SELECT')",
            )
            is False
        )
        # No explicit ACL at all on either table.
        assert (
            await _scalar(
                owned_pg_url,
                "SELECT relacl IS NULL FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = 'demo_control' "
                "AND c.relname = :t",
                {"t": table},
            )
            is True
        )


# --- account lifecycle --------------------------------------------------------


@pytest.mark.asyncio
async def test_account_lifecycle_events_generation_and_hashing(owned_pg_url: str) -> None:
    factory = _session_factory(owned_pg_url)
    username = _unique_username("demo")
    password = _password("lifecycle")
    try:
        async with factory() as session, session.begin():
            service = FakeAdminAccountService(session)
            projection = await service.create_account(
                username=username, password=password, reason="test setup"
            )
        assert projection.is_enabled is True
        assert projection.credential_generation == 0

        events = await _scalar_many(
            owned_pg_url,
            "SELECT action, credential_generation, reason FROM demo_control.fake_admin_account_events "
            "WHERE account_id = :id ORDER BY created_at, id",
            {"id": str(projection.id)},
        )
        assert [(e.action, e.credential_generation, e.reason) for e in events] == [
            ("created", 0, "test setup")
        ]

        # Salted Argon2id hash persisted; plaintext never stored; verify works.
        stored_hash = await _scalar(
            owned_pg_url,
            "SELECT password_hash FROM demo_control.fake_admin_accounts WHERE id = :id",
            {"id": str(projection.id)},
        )
        assert stored_hash.startswith("$argon2id$")
        assert verify_admin_password(password, stored_hash) is True
        assert verify_admin_password(password + "x", stored_hash) is False

        # disable (gen 1), repeat disable (idempotent no-op, still gen 1)
        async with factory() as session, session.begin():
            result = await FakeAdminAccountService(session).set_enabled(
                username=username, enabled=False, reason="off"
            )
            assert result.state_changed is True
            assert result.projection.credential_generation == 1
        async with factory() as session, session.begin():
            result = await FakeAdminAccountService(session).set_enabled(
                username=username, enabled=False, reason="already off"
            )
            assert result.state_changed is False
            assert result.projection.credential_generation == 1

        event_count = await _scalar(
            owned_pg_url,
            "SELECT count(*) FROM demo_control.fake_admin_account_events WHERE account_id = :id",
            {"id": str(projection.id)},
        )
        assert event_count == 2  # created + one disable; no fake success audit

        # enable (gen 2), reset (gen 3, still enabled)
        async with factory() as session, session.begin():
            result = await FakeAdminAccountService(session).set_enabled(
                username=username, enabled=True, reason="on"
            )
            assert result.projection.credential_generation == 2
        new_password = _password("lifecycle2")
        async with factory() as session, session.begin():
            projection = await FakeAdminAccountService(session).reset_password(
                username=username, password=new_password, reason="rotation"
            )
        assert projection.credential_generation == 3
        assert projection.is_enabled is True

        stored_hash = await _scalar(
            owned_pg_url,
            "SELECT password_hash FROM demo_control.fake_admin_accounts WHERE id = :id",
            {"id": str(projection.id)},
        )
        assert verify_admin_password(new_password, stored_hash) is True
        assert verify_admin_password(password, stored_hash) is False

        events = await _scalar_many(
            owned_pg_url,
            "SELECT action FROM demo_control.fake_admin_account_events "
            "WHERE account_id = :id ORDER BY created_at, id",
            {"id": str(projection.id)},
        )
        assert [e.action for e in events] == [
            "created",
            "disabled",
            "enabled",
            "password_reset",
        ]

        # list: safe fields + active count
        async with factory() as session:
            listing = await FakeAdminAccountService(session).list_accounts(
                limit=10, offset=0
            )
        names = [item.username for item in listing.items]
        assert username in names
    finally:
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                # Test-owned row cleanup (owned disposable database).
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_account_events WHERE account_id = :id"),
                    {"id": str(projection.id)},
                )
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_accounts WHERE id = :id"),
                    {"id": str(projection.id)},
                )
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_create_is_fixed_error(owned_pg_url: str) -> None:
    factory = _session_factory(owned_pg_url)
    username = _unique_username("dup")
    try:
        async with factory() as session, session.begin():
            await FakeAdminAccountService(session).create_account(
                username=username, password=_password("dup1"), reason="first"
            )
        # Case-variant duplicate: the CITEXT unique constraint is the law.
        with pytest.raises(FakeAdminAccountError) as excinfo:
            async with factory() as session, session.begin():
                await FakeAdminAccountService(session).create_account(
                    username=username.upper(), password=_password("dup2"), reason="second"
                )
        assert excinfo.value.code == "demo_admin_account_exists"
    finally:
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_account_events "
                         "WHERE account_id IN (SELECT id FROM demo_control.fake_admin_accounts WHERE username = :u)"),
                    {"u": username},
                )
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_accounts WHERE username = :u"),
                    {"u": username},
                )
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_last_disable_makes_active_count_zero_immediately(owned_pg_url: str) -> None:
    factory = _session_factory(owned_pg_url)
    user_a = _unique_username("lasta")
    user_b = _unique_username("lastb")
    ids: list[str] = []
    try:
        async with factory() as session, session.begin():
            service = FakeAdminAccountService(session)
            pa = await service.create_account(
                username=user_a, password=_password("lasta"), reason="a"
            )
            pb = await service.create_account(
                username=user_b, password=_password("lastb"), reason="b"
            )
            ids = [str(pa.id), str(pb.id)]
        before = await _scalar(
            owned_pg_url,
            "SELECT count(*) FROM demo_control.fake_admin_accounts WHERE username IN (:a, :b)",
            {"a": user_a, "b": user_b},
        )
        assert before == 2

        # Disable both; after the LAST disable commits, the global active
        # count for these rows is zero (same-transaction visibility too).
        async with factory() as session, session.begin():
            await FakeAdminAccountService(session).set_enabled(
                username=user_a, enabled=False, reason="off-a"
            )
        async with factory() as session, session.begin():
            await FakeAdminAccountService(session).set_enabled(
                username=user_b, enabled=False, reason="off-b"
            )
        # In-transaction immediacy: disable a fresh account and count
        # within the SAME transaction before commit.
        user_c = _unique_username("lastc")
        from sqlalchemy import func, select

        async with factory() as session, session.begin():
            pc = await FakeAdminAccountService(session).create_account(
                username=user_c, password=_password("lastc"), reason="c"
            )
            ids.append(str(pc.id))
            # The fresh account is enabled inside this transaction...
            result = await session.execute(
                select(func.count(FakeAdminAccount.id)).where(
                    FakeAdminAccount.id == pc.id, FakeAdminAccount.is_enabled.is_(True)
                )
            )
            assert int(result.scalar_one()) == 1
            await FakeAdminAccountService(session).set_enabled(
                username=user_c, enabled=False, reason="off-c"
            )
            # ...and disabling it makes the active count zero in the SAME
            # transaction, before any commit.
            result = await session.execute(
                select(func.count(FakeAdminAccount.id)).where(
                    FakeAdminAccount.id == pc.id, FakeAdminAccount.is_enabled.is_(True)
                )
            )
            assert int(result.scalar_one()) == 0
        # Committed state: none of the three accounts are active.
        active_total = await _scalar(
            owned_pg_url,
            "SELECT count(*) FROM demo_control.fake_admin_accounts "
            "WHERE username IN (:a, :b, :c) AND is_enabled = true",
            {"a": user_a, "b": user_b, "c": user_c},
        )
        assert active_total == 0
    finally:
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_account_events "
                         "WHERE account_id = ANY(:ids)"),
                    {"ids": ids},
                )
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_accounts WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_reset_never_reenables_disabled_account(owned_pg_url: str) -> None:
    factory = _session_factory(owned_pg_url)
    username = _unique_username("reen")
    try:
        async with factory() as session, session.begin():
            projection = await FakeAdminAccountService(session).create_account(
                username=username, password=_password("reen1"), reason="a"
            )
        async with factory() as session, session.begin():
            await FakeAdminAccountService(session).set_enabled(
                username=username, enabled=False, reason="off"
            )
        gen_after_disable: int | None = None
        async with factory() as session, session.begin():
            result = await FakeAdminAccountService(session).reset_password(
                username=username, password=_password("reen2"), reason="rotation"
            )
            gen_after_disable = result.credential_generation
            assert result.is_enabled is False  # reset never re-enables
        rows = await _scalar_many(
            owned_pg_url,
            "SELECT is_enabled, credential_generation FROM demo_control.fake_admin_accounts WHERE id = :id",
            {"id": str(projection.id)},
        )
        stored = rows[0]
        assert stored.is_enabled is False
        assert stored.credential_generation == gen_after_disable
    finally:
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_account_events "
                         "WHERE account_id IN (SELECT id FROM demo_control.fake_admin_accounts WHERE username = :u)"),
                    {"u": username},
                )
                await conn.execute(
                    text("DELETE FROM demo_control.fake_admin_accounts WHERE username = :u"),
                    {"u": username},
                )
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_late_write_failure_rolls_back_account_change(owned_pg_url: str) -> None:
    """A failed late event/write must roll back the account change."""
    from sqlalchemy import insert

    from sqlalchemy.exc import IntegrityError

    factory = _session_factory(owned_pg_url)
    username = _unique_username("rollback")
    # The late event-write fault must surface as an IntegrityError to the
    # caller, and the whole owned transaction (account row included)
    # rolls back with it.
    with pytest.raises(IntegrityError):
        async with factory() as session, session.begin():
            service = FakeAdminAccountService(session)
            projection = await service.create_account(
                username=username, password=_password("rb1"), reason="a"
            )
            # Late-write fault in the SAME transaction: an event row
            # violating the action CHECK after the account row was flushed.
            await session.execute(
                insert(FakeAdminAccountEvent).values(
                    account_id=projection.id,
                    action="not_a_real_action",
                    reason="late fault",
                    credential_generation=0,
                )
            )

    # Nothing committed: no account row, no event rows for this username.
    accounts = await _scalar(
        owned_pg_url,
        "SELECT count(*) FROM demo_control.fake_admin_accounts WHERE username = :u",
        {"u": username},
    )
    events = await _scalar(
        owned_pg_url,
        "SELECT count(*) FROM demo_control.fake_admin_account_events e "
        "JOIN demo_control.fake_admin_accounts a ON a.id = e.account_id "
        "WHERE a.username = :u",
        {"u": username},
    )
    assert accounts == 0
    assert events == 0


# --- restricted role boundary --------------------------------------------------


@pytest.mark.asyncio
async def test_restricted_role_select_only_and_business_denied(owned_pg_url: str) -> None:
    import asyncpg

    password = uuid.uuid4().hex + uuid.uuid4().hex  # random, never printed
    host_port = owned_pg_url.rsplit("@", 1)[1].split("/", 1)[0]
    # Derive the real synthetic owned-PG DSN (container credentials);
    # it is used only in-memory and never printed.
    owner_dsn = f"postgresql://test:test@{host_port}/test"
    web_role_dsn = f"postgresql://{_WEB_ROLE}:{password}@{host_port}/test"

    # _WEB_ROLE is a fixed synthetic test identifier (owned fresh
    # container). Role existence is checked with a native asyncpg
    # parameter; the DDL itself uses only the fixed identifier plus the
    # random hex password (no user-supplied text).
    conn = await asyncpg.connect(owner_dsn, timeout=10)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", _WEB_ROLE)
        if not exists:
            await conn.execute(f"CREATE ROLE {_WEB_ROLE} LOGIN PASSWORD '{password}'")
        await conn.execute(f"GRANT USAGE ON SCHEMA demo_control TO {_WEB_ROLE}")
        # Exactly the documented future grant: SELECT on fake accounts
        # only. NO grant on the event table, NO business-table grant.
        await conn.execute(
            f"GRANT SELECT ON demo_control.fake_admin_accounts TO {_WEB_ROLE}"
        )
    finally:
        await conn.close()

    # asyncpg.connect() is awaitable (not an async context manager):
    # await it, then close in a finally block.
    try:
        # As the web role: SELECT on the accounts table works.
        conn = await asyncpg.connect(web_role_dsn, timeout=10)
        try:
            rows = await conn.fetch(
                "SELECT id, username, is_enabled, credential_generation "
                "FROM demo_control.fake_admin_accounts"
            )
            assert isinstance(rows, list)
        finally:
            await conn.close()

        async def _expect_refused(sql: str, params: tuple = ()) -> None:
            conn = await asyncpg.connect(web_role_dsn, timeout=10)
            try:
                with pytest.raises(asyncpg.PostgresError) as excinfo:
                    if sql.lstrip().upper().startswith("SELECT"):
                        await conn.fetch(sql, *params)
                    else:
                        await conn.execute(sql, *params)
                assert excinfo.value.sqlstate == "42501", sql  # insufficient_privilege
            finally:
                await conn.close()

        await _expect_refused(
            "INSERT INTO demo_control.fake_admin_accounts "
            "(id, username, password_hash, is_enabled, credential_generation, "
            "created_at, updated_at) VALUES (gen_random_uuid(), 'zzhack' || "
            "substr(md5(random()::text), 1, 12), 'x', true, 0, now(), now())"
        )
        await _expect_refused(
            "UPDATE demo_control.fake_admin_accounts SET is_enabled = false"
        )
        await _expect_refused("DELETE FROM demo_control.fake_admin_accounts WHERE false")
        await _expect_refused(
            "INSERT INTO demo_control.fake_admin_account_events "
            "(id, account_id, action, reason, credential_generation, created_at) "
            "VALUES (gen_random_uuid(), gen_random_uuid(), 'created', 'x', 0, now())"
        )
        await _expect_refused("SELECT count(*) FROM demo_control.fake_admin_account_events")
        await _expect_refused("SELECT count(*) FROM gateway_keys")
        await _expect_refused("SELECT count(*) FROM usage_ledger")
        await _expect_refused("SELECT count(*) FROM admin_users")
        await _expect_refused(
            "INSERT INTO audit_log (id, action, note, entity_type, entity_id, "
            "created_at) VALUES (gen_random_uuid(), 'x', 'x', 'x', gen_random_uuid(), now())"
        )
    finally:
        # REVOKE the exact test role's grants before DROP ROLE (PostgreSQL
        # refuses to drop a role that still holds privileges).
        conn = await asyncpg.connect(owner_dsn, timeout=10)
        try:
            await conn.execute(
                f"REVOKE SELECT ON demo_control.fake_admin_accounts FROM {_WEB_ROLE}"
            )
            await conn.execute(f"REVOKE USAGE ON SCHEMA demo_control FROM {_WEB_ROLE}")
            await conn.execute(f"DROP ROLE IF EXISTS {_WEB_ROLE}")
        finally:
            await conn.close()
    _STATE["web_role_dropped"] = True  # role removed; no DSN persisted


# --- real CLI safe output ------------------------------------------------------


def test_cli_safe_output_against_owned_pg(owned_pg_url: str, monkeypatch) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app as root_app

    runner = CliRunner()
    canary_password = _password("cli-canary")
    username = _unique_username("clidemo")
    saved_env = {k: os.environ.get(k) for k in ("DATABASE_URL",)}
    try:
        monkeypatch.setenv("DATABASE_URL", owned_pg_url)
        get_settings.cache_clear()

        create = runner.invoke(
            root_app,
            ["demo-admin", "create", username, "--reason", "cli test",
             "--password-stdin", "--json"],
            input=f"{canary_password}\n",
        )
        assert create.exit_code == 0, create.output
        payload = _json_output(create.output)
        _assert_safe_payload(payload)
        account_id = payload["id"]

        listing = runner.invoke(root_app, ["demo-admin", "list", "--json"])
        assert listing.exit_code == 0, listing.output
        lpayload = _json_output(listing.output)
        assert any(item["id"] == account_id for item in lpayload["items"])
        for item in lpayload["items"]:
            _assert_safe_payload(item)

        disable = runner.invoke(
            root_app, ["demo-admin", "disable", username, "--reason", "cli off", "--json"]
        )
        assert disable.exit_code == 0, disable.output
        dpayload = _json_output(disable.output)
        assert dpayload["is_enabled"] is False
        assert dpayload["state_changed"] is True
        assert dpayload["credential_generation"] == 1

        reset = runner.invoke(
            root_app,
            ["demo-admin", "reset-password", username, "--reason", "cli rotation",
             "--password-stdin", "--json"],
            input=f"{_password('cli-canary2')}\n",
        )
        assert reset.exit_code == 0, reset.output
        rpayload = _json_output(reset.output)
        # reset never re-enables
        assert rpayload["is_enabled"] is False
        assert rpayload["credential_generation"] == 2

        for result in (create, listing, disable, reset):
            assert canary_password not in result.output
            assert owned_pg_url not in result.output
            assert "$argon2id$" not in result.output

        # not-found is a fixed safe error
        missing = runner.invoke(
            root_app,
            ["demo-admin", "disable", _unique_username("nope"), "--reason", "x", "--json"],
        )
        assert missing.exit_code == 1
        mpayload = _json_output(missing.output)
        assert mpayload["error"]["code"] == "demo_admin_account_not_found"
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        # Test-owned row cleanup in the owned disposable database.
        asyncio.run(_cleanup_rows(owned_pg_url, [account_id]))


def _assert_safe_payload(payload: dict[str, Any]) -> None:
    allowed = {
        "id",
        "username",
        "is_enabled",
        "credential_generation",
        "created_at",
        "updated_at",
        "created",
        "reset",
        "state_changed",
        "items",
        "limit",
        "offset",
        "active_account_count",
        "error",
    }
    assert set(payload) <= allowed, sorted(set(payload) - allowed)


def _json_output(output: str) -> dict[str, Any]:
    import json

    for line in reversed([ln for ln in output.splitlines() if ln.strip()]):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise AssertionError(f"no JSON payload in output: {output!r}")


async def _cleanup_rows(url: str, ids: list[str]) -> None:
    engine = create_async_engine(url, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM demo_control.fake_admin_account_events "
                     "WHERE account_id = ANY(:ids)"),
                {"ids": ids},
            )
            await conn.execute(
                text("DELETE FROM demo_control.fake_admin_accounts WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
    finally:
        await engine.dispose()
