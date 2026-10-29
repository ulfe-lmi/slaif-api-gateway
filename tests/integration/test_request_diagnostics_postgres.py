"""Real owned-PostgreSQL-16 evidence for objective 201 request diagnostics.

Proves, against a real disposable database (schema 0026 head): a normal
record with absent positions persists SQL NULL (never JSON null); a repeated
stable gateway diagnostic ID is idempotent (one row, STORED); a primary-key
collision with a DIFFERENT gateway ID is a bounded drop, never labelled
STORED; the positions shape/size and 8KiB facts CHECKs actually fire on
PostgreSQL 16; the configured maximum is a true cap under eviction (including
the lowered-by-more-than-one-eviction-bound drain) and under concurrent
writers; expired rows are pruned; and lookups are namespace-honest with an
exact same-snapshot match count and the 100-candidate bound.

A repeated retained gateway diagnostic ID at FULL capacity is a true
idempotent no-op: the original row ID, metadata, and timestamps are
preserved (the root-reproduced defect was that the repeat evicted and
replaced the original row, returning STORED_AFTER_EVICTION).

No provider HTTP, no Redis, no normal auth, no real upstream contact.
Ownership discipline mirrors the 199/200 owned fixtures: unique owner label,
loopback-bound, tmpfs-backed PostgreSQL 16, identity inspected BEFORE
readiness/migration, cleanup removes ONLY the exact created container ID.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.schemas.request_diagnostics import (
    DiagnosticLookupOutcome,
    DiagnosticsNamespace,
    DiagnosticsWriteOutcome,
)
from slaif_gateway.services import request_diagnostics as rd
from slaif_gateway.services.request_diagnostics import RequestDiagnosticsService
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif201a"

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


# --- helpers -------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "_env_file": None,
        "APP_ENV": "test",
        "DATABASE_URL": None,
        "REQUEST_DIAGNOSTICS_ENABLED": True,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _service(url: str, **settings_overrides: Any) -> RequestDiagnosticsService:
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)
    # The 100ms production default is deliberately tight; the maximum allowed
    # 1000ms keeps cold first-connection statement preparation inside the
    # write budget in this suite (the production default stays 100ms).
    settings_overrides.setdefault("REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS", 1000)
    return RequestDiagnosticsService(settings=_settings(**settings_overrides), session_factory=factory)


def _facts(gateway_request_id: str, **overrides: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "gateway_request_id": gateway_request_id,
        "method": "POST",
        "endpoint_template": "/v1/responses",
        "occurred_at": datetime.now(UTC),
        "stream_outcome": "http_rejection",
        "http_status": 400,
    }
    facts.update(overrides)
    return facts


async def _row_count(url: str) -> int:
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)
    async with factory() as session:
        return (await session.execute(text("SELECT count(*) FROM request_diagnostics"))).scalar_one()


async def _raw(url: str, sql: str, *params: Any) -> Any:
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(text(sql), *params)
        await session.commit()
        return result


# --- tests -----------------------------------------------------------------------


def test_normal_record_absent_positions_stored_as_sql_null(owned_pg_url: str) -> None:
    async def _go() -> None:
        svc = _service(owned_pg_url)
        gid = f"gw-{uuid.uuid4()}"
        outcome = await svc.record_failure(
            _facts(gid, client_request_id="req-diag-null", counts={"count": 2, "limit": 8})
        )
        assert outcome is DiagnosticsWriteOutcome.STORED
        assert await _row_count(owned_pg_url) == 1
        result = await _raw(
            owned_pg_url,
            "SELECT positions IS NULL, counts IS NULL, limits IS NULL, counts->>'count' "
            "FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gid},
        )
        positions_null, counts_null, limits_null, count_value = result.first()
        assert positions_null is True  # SQL NULL, not JSON null
        assert counts_null is False
        assert limits_null is True
        assert count_value == "2"

    asyncio.run(_go())

def test_gateway_id_repeat_is_idempotent_single_row(owned_pg_url: str) -> None:
    async def _go() -> None:
        svc = _service(owned_pg_url)
        gid = f"gw-{uuid.uuid4()}"
        first = await svc.record_failure(_facts(gid))
        second = await svc.record_failure(_facts(gid))
        assert first is DiagnosticsWriteOutcome.STORED
        assert second is DiagnosticsWriteOutcome.STORED  # repeat, not a second row
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gid},
        )
        assert result.scalar_one() == 1

    asyncio.run(_go())


def test_overlong_known_param_path_stores_row_with_param_unavailable(
    owned_pg_url: str,
) -> None:
    """A 71-char all-known-component error_param must not drop the row.

    The root-owned PG16 probe (postgres-param-bound-probe.json) reproduced
    the pre-fix defect: the value passed projection, VARCHAR(64) rejected
    the INSERT, and the whole diagnostic was dropped (unavailable).  The
    service now projects the overlong optional path to unavailable and
    preserves the remaining failure facts in the row.
    """

    async def _go() -> None:
        svc = _service(owned_pg_url)
        gid = f"gw-{uuid.uuid4()}"
        overlong = (
            "max_output_tokens.max_output_tokens.max_output_tokens.max_output_tokens"
        )
        assert len(overlong) == 71
        outcome = await svc.record_failure(
            _facts(
                gid,
                client_request_id="req-diag-param-bound",
                source="responses_route_limits",
                error_code="responses_codex_context_window_exceeded",
                error_param=overlong,
            )
        )
        assert outcome is DiagnosticsWriteOutcome.STORED
        result = await _raw(
            owned_pg_url,
            "SELECT error_param IS NULL, source, error_code "
            "FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gid},
        )
        param_null, source, error_code = result.first()
        assert param_null is True
        assert source == "responses_route_limits"
        assert error_code == "responses_codex_context_window_exceeded"

    asyncio.run(_go())

def test_pk_collision_with_different_gateway_id_is_unavailable(
    owned_pg_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A primary-key collision (23505 on the PK, not the gateway-ID unique)
    must be a bounded drop, never labelled STORED."""

    async def _go() -> None:
        fixed_id = uuid.uuid4()
        pre_gid = f"gw-{uuid.uuid4()}"
        await _raw(
            owned_pg_url,
            "INSERT INTO request_diagnostics "
            "(id, gateway_request_id, method, occurred_at, stream_outcome, recorded_at) "
            "VALUES (:id, :gid, 'POST', now() AT TIME ZONE 'UTC', 'http_rejection', "
            "now() AT TIME ZONE 'UTC')",
            {"id": fixed_id, "gid": pre_gid},
        )

        real_build = rd.build_diagnostic_record

        def _forced_id(facts: Any, **kwargs: Any) -> Any:
            record = real_build(facts, **kwargs)
            return dataclasses.replace(record, id=fixed_id)

        monkeypatch.setattr(rd, "build_diagnostic_record", _forced_id)
        svc = _service(owned_pg_url)
        new_gid = f"gw-{uuid.uuid4()}"
        outcome = await svc.record_failure(_facts(new_gid))
        assert outcome is DiagnosticsWriteOutcome.DROPPED_UNAVAILABLE
        result = await _raw(
            owned_pg_url,
            "SELECT gateway_request_id FROM request_diagnostics WHERE id = :id",
            {"id": fixed_id},
        )
        # the pre-existing row is untouched; no new row exists
        assert result.scalar_one() == pre_gid

    asyncio.run(_go())


def test_positions_check_and_8kib_check_fire_on_postgres16(owned_pg_url: str) -> None:
    async def _go() -> None:
        """Raw-SQL proofs that the PG16-safe CHECKs actually exist and fire."""
        from sqlalchemy.exc import IntegrityError

        # positions over the 512-byte bound
        with pytest.raises(IntegrityError) as positions_exc:
            await _raw(
                owned_pg_url,
                "INSERT INTO request_diagnostics "
                "(id, gateway_request_id, method, occurred_at, stream_outcome, positions, "
                "recorded_at) VALUES (gen_random_uuid(), 'gw-diag-pos-check', 'POST', "
                "now() AT TIME ZONE 'UTC', 'http_rejection', to_jsonb("
                "(SELECT jsonb_object_agg(k::text, 1) FROM generate_series(1, 400) k)), "
                "now() AT TIME ZONE 'UTC')",
            )
        assert "request_diagnostics_positions_bounded" in str(positions_exc.value)

        # facts payload over the 8KiB bound
        with pytest.raises(IntegrityError) as payload_exc:
            await _raw(
                owned_pg_url,
                "INSERT INTO request_diagnostics "
                "(id, gateway_request_id, method, occurred_at, stream_outcome, counts, "
                "recorded_at) VALUES (gen_random_uuid(), 'gw-diag-8kib-check', 'POST', "
                "now() AT TIME ZONE 'UTC', 'http_rejection', to_jsonb("
                "(SELECT jsonb_object_agg('k' || lpad(k::text, 6, '0'), 1) "
                "FROM generate_series(1, 900) k)), "
                "now() AT TIME ZONE 'UTC')",
            )
        assert "request_diagnostics_facts_payload_8kib" in str(payload_exc.value)

        # a service-level record can still be stored afterwards (transaction clean)
        svc = _service(owned_pg_url)
        outcome = await svc.record_failure(_facts(f"gw-{uuid.uuid4()}"))
        assert outcome is DiagnosticsWriteOutcome.STORED

    asyncio.run(_go())

def test_capacity_eviction_keeps_configured_max(owned_pg_url: str) -> None:
    async def _go() -> None:
        base = await _row_count(owned_pg_url)
        svc = _service(owned_pg_url, REQUEST_DIAGNOSTICS_MAX_RECORDS=base + 10)
        outcomes = set()
        # the table already holds rows from earlier tests: capture the exact
        # two OLDEST rows, which eviction must remove first
        result = await _raw(
            owned_pg_url,
            "SELECT gateway_request_id FROM request_diagnostics "
            "ORDER BY occurred_at ASC, id ASC LIMIT 2",
        )
        oldest_before = {row[0] for row in result.all()}
        assert len(oldest_before) == 2
        gids = [f"gw-{uuid.uuid4()}" for _ in range(12)]
        for gid in gids:
            outcomes.add(await svc.record_failure(_facts(gid)))
        assert await _row_count(owned_pg_url) == base + 10
        assert DiagnosticsWriteOutcome.STORED in outcomes
        assert DiagnosticsWriteOutcome.STORED_AFTER_EVICTION in outcomes
        # exactly the two oldest rows (from before this test) were evicted
        for evicted_gid in oldest_before:
            result = await _raw(
                owned_pg_url,
                "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
                {"gid": evicted_gid},
            )
            assert result.scalar_one() == 0
        # the newest of this test's 12 is retained
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gids[-1]},
        )
        assert result.scalar_one() == 1

    asyncio.run(_go())

def test_repeat_at_capacity_is_noop_original_unchanged(owned_pg_url: str) -> None:
    """A repeat of a retained gateway ID at full capacity must NOT evict the
    original row it duplicates (root-reproduced, real PG16)."""

    async def _go() -> None:
        base = await _row_count(owned_pg_url)
        svc = _service(
            owned_pg_url,
            # 30-day retention keeps the deliberately aged row prunable-free.
            REQUEST_DIAGNOSTICS_RETENTION_SECONDS=2_592_000,
            REQUEST_DIAGNOSTICS_MAX_RECORDS=base + 5,
        )
        gid = f"gw-{uuid.uuid4()}"
        # Aged by one hour: strictly the table's OLDEST row (every other row
        # in this suite is minutes old or newer) yet far inside BOTH this
        # service's 30-day retention and the suite's default 7-day retention,
        # so expiry pruning can never remove it.  Without the pre-eviction
        # check, a repeat write would evict and replace it first.
        aged = datetime.now(UTC) - timedelta(hours=1)
        outcome = await svc.record_failure(
            _facts(
                gid,
                occurred_at=aged,
                error_code="responses_function_tool_capability_not_supported",
                counts={"count": 7},
            )
        )
        assert outcome is DiagnosticsWriteOutcome.STORED
        result = await _raw(
            owned_pg_url,
            "SELECT * FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gid},
        )
        original = result.fetchall()
        assert len(original) == 1

        # Fill the table to exactly the configured maximum.
        for _ in range(4):
            assert await _row_count(owned_pg_url) <= base + 5
            assert (
                await svc.record_failure(_facts(f"gw-{uuid.uuid4()}"))
                is DiagnosticsWriteOutcome.STORED
            )
        assert await _row_count(owned_pg_url) == base + 5

        # REPEAT the retained gateway ID with DIFFERENT safe facts: it must be
        # a true no-op, preserving the original row byte-for-byte.
        repeat_outcome = await svc.record_failure(
            _facts(
                gid,
                http_status=403,
                error_code="responses_stream_event_not_supported",
                counts={"count": 9},
            )
        )
        assert repeat_outcome is DiagnosticsWriteOutcome.STORED
        assert await _row_count(owned_pg_url) == base + 5
        result = await _raw(
            owned_pg_url,
            "SELECT * FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gid},
        )
        assert result.fetchall() == original

    asyncio.run(_go())

def test_lowered_max_by_more_than_eviction_bound_is_true_cap_then_drains(
    owned_pg_url: str,
) -> None:
    async def _go() -> None:
        # bulk-seed 1200 rows directly (distinct, ordered occurred_at)
        await _raw(
            owned_pg_url,
            "INSERT INTO request_diagnostics "
            "(id, gateway_request_id, method, occurred_at, stream_outcome, recorded_at) "
            "SELECT gen_random_uuid(), 'gw-diag-bulk-' || g, 'POST', "
            "now() AT TIME ZONE 'UTC' - make_interval(secs => (1200 - g) * 1.0), "
            "'http_rejection', now() AT TIME ZONE 'UTC' FROM generate_series(1, 1200) g",
        )
        before = await _row_count(owned_pg_url)
        assert before >= 1200

        svc = _service(owned_pg_url, REQUEST_DIAGNOSTICS_MAX_RECORDS=100)
        # one bounded eviction bound (<=1000) cannot make room: the prune is
        # committed and the new record is dropped (true cap, no insert).
        outcome = await svc.record_failure(_facts(f"gw-{uuid.uuid4()}"))
        assert outcome is DiagnosticsWriteOutcome.DROPPED_CAPACITY
        assert await _row_count(owned_pg_url) == before - 1000

        # the next non-repeat write drains the remainder through ONE bounded
        # eviction (leaving exactly max-1 rows) and then inserts: the cap holds
        gid = f"gw-{uuid.uuid4()}"
        outcome = await svc.record_failure(_facts(gid))
        assert outcome is DiagnosticsWriteOutcome.STORED_AFTER_EVICTION
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics",
        )
        assert result.scalar_one() == 100  # exactly the configured maximum
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": gid},
        )
        assert result.scalar_one() == 1

    asyncio.run(_go())

def test_expiry_pruned_on_write_and_by_cleanup(owned_pg_url: str) -> None:
    async def _go() -> None:
        svc = _service(owned_pg_url, REQUEST_DIAGNOSTICS_RETENTION_SECONDS=60)
        keep_gid = f"gw-{uuid.uuid4()}"
        age_gid = f"gw-{uuid.uuid4()}"
        # (each write may also prune older rows from preceding tests that are
        # outside the 60s window, so either stored outcome is legitimate)
        assert await svc.record_failure(_facts(keep_gid)) in (
            DiagnosticsWriteOutcome.STORED,
            DiagnosticsWriteOutcome.STORED_AFTER_EVICTION,
        )
        assert await svc.record_failure(_facts(age_gid)) in (
            DiagnosticsWriteOutcome.STORED,
            DiagnosticsWriteOutcome.STORED_AFTER_EVICTION,
        )
        # age one row beyond the retention window
        await _raw(
            owned_pg_url,
            "UPDATE request_diagnostics SET occurred_at = now() AT TIME ZONE 'UTC' - "
            "interval '10 days', recorded_at = now() AT TIME ZONE 'UTC' - interval '10 days' "
            "WHERE gateway_request_id = :gid",
            {"gid": age_gid},
        )
        # the next write prunes expired rows first (including any older rows
        # from preceding tests in this module, which are outside the 60s
        # retention window); the write itself is not an eviction failure
        assert await svc.record_failure(_facts(f"gw-{uuid.uuid4()}")) in (
            DiagnosticsWriteOutcome.STORED,
            DiagnosticsWriteOutcome.STORED_AFTER_EVICTION,
        )
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": age_gid},
        )
        assert result.scalar_one() == 0
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": keep_gid},
        )
        assert result.scalar_one() == 1
        # explicit cleanup positively proven: store the fresh row FIRST, then
        # seed the explicit expired target, then run cleanup with NO
        # intervening write (a write would prune expired rows itself)
        fresh_gid = f"gw-{uuid.uuid4()}"
        assert await svc.record_failure(_facts(fresh_gid)) in (
            DiagnosticsWriteOutcome.STORED,
            DiagnosticsWriteOutcome.STORED_AFTER_EVICTION,
        )
        target_gid = f"gw-{uuid.uuid4()}"
        await _raw(
            owned_pg_url,
            "INSERT INTO request_diagnostics "
            "(id, gateway_request_id, method, occurred_at, stream_outcome, recorded_at) "
            "VALUES (gen_random_uuid(), :tgid, 'POST', "
            "now() AT TIME ZONE 'UTC' - interval '2 days', 'http_rejection', "
            "now() AT TIME ZONE 'UTC' - interval '2 days')",
            {"tgid": target_gid},
        )
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE occurred_at < "
            "now() AT TIME ZONE 'UTC' - interval '60 seconds'",
        )
        expired_before = result.scalar_one()
        assert expired_before >= 1
        status = await svc.cleanup()
        assert status.store_available is True
        # one bounded batch deleted exactly the expired rows (far below the
        # batch bound, so nothing else is pending)
        assert status.deleted_count == expired_before
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": target_gid},
        )
        assert result.scalar_one() == 0  # the explicit expired target deleted
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE gateway_request_id = :gid",
            {"gid": fresh_gid},
        )
        assert result.scalar_one() == 1  # the fresh row is retained
        result = await _raw(
            owned_pg_url,
            "SELECT count(*) FROM request_diagnostics WHERE occurred_at < "
            "now() AT TIME ZONE 'UTC' - interval '60 seconds'",
        )
        assert result.scalar_one() == 0

    asyncio.run(_go())

def test_lookup_namespaces_cross_namespace_and_overflow(owned_pg_url: str) -> None:
    async def _go() -> None:
        svc = _service(owned_pg_url)
        # the shared string is safe in both id charsets (letters, digits, '-')
        shared = f"req-{uuid.uuid4().hex[:16]}"
        gw_a = f"gw-{uuid.uuid4()}"
        # row A: the shared string is its CLIENT id; row B: its GATEWAY id
        assert await svc.record_failure(_facts(gw_a, client_request_id=shared)) is (
            DiagnosticsWriteOutcome.STORED
        )
        assert await svc.record_failure(_facts(shared)) is DiagnosticsWriteOutcome.STORED

        # client namespace: exactly one client row matches (row A)
        found = await svc.resolve(shared, namespace=DiagnosticsNamespace.CLIENT)
        assert found.outcome is DiagnosticLookupOutcome.FOUND
        assert found.record is not None
        assert found.record.gateway_request_id == gw_a
        # gateway namespace: exactly one gateway row matches (row B)
        gateway_match = await svc.resolve(shared, namespace=DiagnosticsNamespace.GATEWAY)
        assert gateway_match.outcome is DiagnosticLookupOutcome.FOUND
        assert gateway_match.record is not None
        assert gateway_match.record.gateway_request_id == shared
        # any namespace: cross-namespace collision is honestly ambiguous
        ambiguous = await svc.resolve(shared, namespace=DiagnosticsNamespace.ANY)
        assert ambiguous.outcome is DiagnosticLookupOutcome.AMBIGUOUS
        assert ambiguous.match_count == 2
        assert {c.matched_namespace for c in ambiguous.candidates} == {"client", "gateway"}
        # an id stored in neither namespace is not found
        absent = f"req-{uuid.uuid4().hex[:16]}"
        assert (
            await svc.resolve(absent, namespace=DiagnosticsNamespace.ANY)
        ).outcome is DiagnosticLookupOutcome.NOT_FOUND

        # 101 retained rows sharing one client id: exact count + overflow bound
        bulk_id = f"req-{uuid.uuid4().hex[:16]}"
        for i in range(101):
            assert await svc.record_failure(
                _facts(f"gw-{uuid.uuid4()}", client_request_id=bulk_id)
            ) in (DiagnosticsWriteOutcome.STORED, DiagnosticsWriteOutcome.STORED_AFTER_EVICTION)
        overflow = await svc.resolve(bulk_id, namespace=DiagnosticsNamespace.CLIENT)
        assert overflow.outcome is DiagnosticLookupOutcome.AMBIGUOUS
        assert overflow.match_count == 101
        assert overflow.overflow is True
        assert len(overflow.candidates) == 100

    asyncio.run(_go())

def test_concurrent_writers_never_exceed_cap(owned_pg_url: str) -> None:
    async def _go() -> None:
        base = await _row_count(owned_pg_url)
        cap = base + 25
        svc = _service(owned_pg_url, REQUEST_DIAGNOSTICS_MAX_RECORDS=cap)
        batch = [f"gw-{uuid.uuid4()}" for _ in range(40)]

        async def _writer(index: int) -> None:
            for i in range(5):
                await svc.record_failure(_facts(batch[index * 5 + i]))

        await asyncio.gather(*(_writer(i) for i in range(8)))
        assert await _row_count(owned_pg_url) <= cap

    asyncio.run(_go())
