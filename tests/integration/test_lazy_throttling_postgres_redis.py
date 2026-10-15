"""Real owned Redis + PostgreSQL evidence for bounded per-key lazy throttling.

V2 scope here (first increment): two separate service instances sharing one
real Redis server prove the waiting-lease caps, cross-instance visibility,
admit-once semantics, and that waiting never increments request/token state.
A second increment adds the actual-HTTP Chat wait->admit case with real PG
accounting snapshots.

Ownership discipline mirrors the 184 installed-workflow fixture: unique
owner label, explicit 127.0.0.1 port binding, tmpfs PG / no-persistence
Redis, identity inspected BEFORE use, cleanup removes ONLY the exact
created container ID (a Docker NotFound means already removed).
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import QuotaReservation, UsageLedger
from slaif_gateway.schemas.rate_limits import (
    LazyThrottlingPolicy,
    RateLimitPolicy,
)
from slaif_gateway.services.lazy_throttling import (
    LazyAdmissionContext,
    LazyThrottlingAdmission,
    global_waiting_key,
    per_key_waiting_key,
    wait_for_rate_limit_admission,
)
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    LazyThrottlingDeadlineExceededError,
    LazyThrottlingWaitingCapacityFullError,
)
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from tests.e2e.test_openai_python_client_chat import (
    CHAT_COMPLETIONS_ENDPOINT,
    COMPLETION_TEXT,
    PROMPT_TEXT,
    _configure_runtime_environment,
    _free_port,
    _run_uvicorn_server,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif185a"

_STATE: dict[str, str] = {}


# --- owned service fixtures -------------------------------------------------


def _inspect_owned(container, owner: str, container_port: int, *, expect_tmpfs: bool) -> int:
    """Reload and verify the EXACT created identity; return the bound port."""
    container.reload()
    attrs = container.attrs
    labels = attrs["Config"].get("Labels") or {}
    assert labels.get(f"{_OWNER_PREFIX}.owner") == owner, "owned container label mismatch"
    host_config = attrs["HostConfig"] or {}
    if expect_tmpfs:
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
    """Remove ONLY the exact created ID with its matching owner label.

    Only docker NotFound is treated as already removed; any other error is a
    real cleanup failure and propagates (reported honestly, never masked).
    """
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
    """One NEW owned, labeled, loopback-bound, tmpfs-backed PostgreSQL 16.

    Always a fresh synthetic container (no ambient/shared URL reuse):
    explicit POSTGRES_USER/PASSWORD/DB and tmpfs at CREATE time, identity
    (label/tmpfs/loopback) verified BEFORE readiness and migration, and
    cleanup of the exact created ID even when setup itself fails.
    """
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
        _STATE["pg_container"] = container.id  # type: ignore[attr-defined]
        _STATE["pg_owner"] = owner
        port = _inspect_owned(container, owner, 5432, expect_tmpfs=True)

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
def owned_redis_url() -> Iterator[str]:
    """One NEW owned, labeled, loopback-bound, no-persistence Redis 7.

    Always a fresh synthetic container (no ambient/shared URL reuse, no
    FLUSHDB on anything that was not created here); cleanup of the exact
    created ID even when setup itself fails.
    """
    import docker

    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    container = None
    owner = f"{_OWNER_PREFIX}-{uuid.uuid4().hex}"
    try:
        container = client.containers.run(
            "redis:7-alpine",
            command=["redis-server", "--save", "", "--appendonly", "no"],
            ports={6379: ("127.0.0.1", None)},
            labels={f"{_OWNER_PREFIX}.owner": owner},
            detach=True,
        )
        _STATE["redis_container"] = container.id  # type: ignore[attr-defined]
        _STATE["redis_owner"] = owner
        port = _inspect_owned(container, owner, 6379, expect_tmpfs=False)

        probe = Redis.from_url(f"redis://127.0.0.1:{port}/0", decode_responses=True)

        async def _wait_ready() -> None:
            deadline = time.monotonic() + 30
            last: object = None
            try:
                while time.monotonic() < deadline:
                    try:
                        await probe.ping()
                        return
                    except RedisError as exc:
                        last = exc
                        await asyncio.sleep(0.2)
                raise AssertionError(f"owned Redis did not become ready: {last!r}")
            finally:
                # Close in the SAME loop the connection was created in.
                await probe.aclose()

        asyncio.run(_wait_ready())
        _STATE["redis_source"] = "owned"
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        if container is not None:
            _STATE["redis_cleanup"] = _remove_owned(client, container, owner)


# --- shared helpers ----------------------------------------------------------


def _configure_lazy_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_url: str,
    redis_url: str,
) -> None:
    """Runtime environment for the real app: PG + enabled Redis limiter."""
    _configure_runtime_environment(monkeypatch, database_url)
    monkeypatch.setenv("ENABLE_REDIS_RATE_LIMITS", "true")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_TTL_SECONDS", "30")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS", "5")

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()


@dataclass(frozen=True)
class _SeededKey:
    plaintext_gateway_key: str
    gateway_key_id: uuid.UUID
    public_key_id: str


async def _seed_chat_key(
    database_url: str,
    *,
    model: str,
    rate_limit_policy: dict[str, int | None] | None = None,
    lazy_throttling_policy: dict[str, object] | None = None,
    request_limit_total: int = 100,
) -> _SeededKey:
    """Seed institution/owner/cohort/provider/route/pricing/key for one model."""
    from slaif_gateway.config import Settings
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique = uuid.uuid4().hex
    now = datetime.now(UTC)

    async with session_factory() as session:
        institution = await InstitutionsRepository(session).create_institution(
            name=f"SLAIF lazy {unique}", country="SI", notes="lazy throttling integration"
        )
        owner = await OwnersRepository(session).create_owner(
            name="Lazy",
            surname="Client",
            email=f"lazy-client-{unique}@example.org",
            institution_id=institution.id,
            notes="lazy throttling integration owner",
        )
        cohort = await CohortsRepository(session).create_cohort(
            name=f"lazy-{unique}",
            description="lazy throttling integration cohort",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        providers = ProviderConfigsRepository(session)
        provider_config = await providers.get_provider_config_by_provider("openai")
        if provider_config is None:
            await providers.create_provider_config(
                provider="openai",
                display_name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                notes="lazy throttling integration provider",
            )
        else:
            await providers.update_provider_metadata(
                provider_config.id,
                display_name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                notes="lazy throttling integration provider",
            )
            await providers.set_provider_enabled(provider_config.id, enabled=True)

        routes = ModelRoutesRepository(session)
        await routes.create_model_route(
            requested_model=model,
            provider="openai",
            upstream_model=model,
            match_type="exact",
            endpoint=CHAT_COMPLETIONS_ENDPOINT,
            priority=1,
            visible_in_models=True,
            supports_streaming=True,
            capabilities={
                "chat_completions": {
                    "chat_text": True,
                    "chat_streaming": True,
                    "chat_function_tools": False,
                    "chat_custom_tools": False,
                    "chat_legacy_functions": True,
                    "chat_structured_outputs": True,
                    "chat_json_mode": True,
                    "chat_logprobs": False,
                    "chat_reasoning_usage": False,
                    "chat_cached_input_usage": False,
                    "hosted_web_search": False,
                    "hosted_file_search": False,
                    "hosted_code_interpreter": False,
                    "hosted_computer_use": False,
                    "hosted_image_generation": False,
                    "hosted_tool_search": False,
                    "external_mcp_connectors": False,
                    "chat_image_inputs": False,
                    "chat_multimodal": False,
                    "chat_audio": False,
                    "chat_file_inputs": False,
                    "chat_audio_inputs": False,
                    "chat_audio_outputs": False,
                    "chat_service_tier_non_default": False,
                    "chat_multiple_choices": False,
                }
            },
            notes="lazy throttling integration route",
        )
        await PricingRulesRepository(session).create_pricing_rule(
            provider="openai",
            upstream_model=model,
            endpoint=CHAT_COMPLETIONS_ENDPOINT,
            valid_from=now - timedelta(days=1),
            currency="EUR",
            input_price_per_1m=Decimal("1.000000000"),
            output_price_per_1m=Decimal("1.000000000"),
            request_price=Decimal("0.000000000"),
            pricing_metadata={},
            notes="lazy throttling integration pricing",
        )

        key_service = KeyService(
            settings=Settings(),
            gateway_keys_repository=GatewayKeysRepository(session),
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            audit_repository=AuditRepository(session),
        )
        created = await key_service.create_gateway_key(
            CreateGatewayKeyInput(
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(minutes=5),
                valid_until=now + timedelta(hours=1),
                cost_limit_eur=Decimal("10.000000000"),
                token_limit_total=100_000,
                request_limit_total=request_limit_total,
                allowed_models=[model],
                allowed_endpoints=[CHAT_COMPLETIONS_ENDPOINT],
                rate_limit_policy=rate_limit_policy,
                lazy_throttling_policy=lazy_throttling_policy,
                note="lazy throttling integration key",
            )
        )
        await session.commit()
        result = _SeededKey(
            plaintext_gateway_key=created.plaintext_key,
            gateway_key_id=created.gateway_key_id,
            public_key_id=created.public_key_id,
        )
    await engine.dispose()
    return result


async def _side_effect_counts(
    database_url: str, gateway_key_id: uuid.UUID
) -> tuple[int, int]:
    """(quota_reservations, usage_ledger) row counts for one key."""
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            reservations = await session.execute(
                select(func.count())
                .select_from(QuotaReservation)
                .where(QuotaReservation.gateway_key_id == gateway_key_id)
            )
            ledger = await session.execute(
                select(func.count())
                .select_from(UsageLedger)
                .where(UsageLedger.gateway_key_id == gateway_key_id)
            )
            return int(reservations.scalar_one()), int(ledger.scalar_one())
    finally:
        await engine.dispose()


async def _ledger_rows(database_url: str, gateway_key_id: uuid.UUID) -> list[dict[str, object]]:
    """Actual finalization rows for one key (token + cost amounts)."""
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(UsageLedger)
                .where(UsageLedger.gateway_key_id == gateway_key_id)
                .order_by(UsageLedger.created_at)
            )
            return [
                {
                    "request_id": row.request_id,
                    "total_tokens": row.total_tokens,
                    "actual_cost_eur": row.actual_cost_eur,
                }
                for row in result.scalars()
            ]
    finally:
        await engine.dispose()



async def _assert_no_checked_out_pool_connections(app, samples: int = 3) -> None:
    """The waiting request must not hold an app DB session/connection.

    Sample the app engine's pool a few times across the settled wait/sleep
    phase: any checked-out connection would be a held session (a plain fast
    UPDATE cannot distinguish that, so observe the pool directly).
    """
    for _ in range(samples):
        checked_out = app.state.db_engine.pool.checkedout()
        assert checked_out == 0, f"app pool has {checked_out} checked-out connection(s) while waiting"
        await asyncio.sleep(0.15)


async def _wait_zcard(client: Redis, key: str, expected: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if int(await client.zcard(key) or 0) == expected:
            return
        await asyncio.sleep(0.05)
    actual = await client.zcard(key)
    raise AssertionError(f"ZSET {key!r} expected {expected} members, got {actual}")


# --- V2: two separate service instances sharing one real Redis ---------------


@pytest.mark.asyncio
async def test_two_instances_waiting_caps_and_admit_once(owned_redis_url: str) -> None:
    """Per-key waiting cap, cross-instance visibility, admit exactly once.

    Instance A (client A) holds the single concurrency slot; instance B
    (client B, same server) runs the bounded wait helper. Waiting must not
    increment request/token state, the per-key cap must refuse a second
    waiter while the helper waits, and release from A must admit B's waiter
    exactly once, leaving no waiting lease behind.
    """
    client_a = Redis.from_url(owned_redis_url, decode_responses=True)
    client_b = Redis.from_url(owned_redis_url, decode_responses=True)
    try:
        service_a = RedisRateLimitService(client_a, fail_closed=True)
        service_b = RedisRateLimitService(client_b, fail_closed=True)
        admission = LazyThrottlingAdmission(client_b, fail_closed=True)

        key_id = uuid.uuid4()
        policy = RateLimitPolicy(
            concurrent_requests=1,
            requests_per_minute=5,
            tokens_per_minute=20,
            window_seconds=300,
            concurrency_ttl_seconds=30,
            concurrency_heartbeat_seconds=5,
        )
        lazy = LazyThrottlingPolicy(mode="wait", max_wait_seconds=30, max_waiting_requests=1)
        lease_deadline = datetime.fromtimestamp(time.time() + 300, tz=UTC)

        async def _counter_sum(client: Redis, counter: str) -> int:
            total = 0
            async for key in client.scan_iter(match=f"rate:{key_id}:{counter}:*"):
                total += int(await client.get(key) or 0)
            return total

        # Blocker (instance A) takes the only concurrency slot.
        blocker = await service_a.check_and_reserve(
            gateway_key_id=key_id, request_id="blocker", estimated_tokens=5, policy=policy
        )
        assert blocker.allowed is True

        context = LazyAdmissionContext(
            gateway_key_id=key_id,
            authenticated_key=object(),
            limiter_policy=policy,
            policy_result=None,
            route=None,
            estimated_tokens=5,
        )

        async def _check_and_reserve(**kwargs):
            return await service_b.check_and_reserve(**kwargs)

        async def _release_slot() -> None:
            await service_b.release_concurrency(gateway_key_id=key_id, request_id="waiter-1")

        task = asyncio.create_task(
            wait_for_rate_limit_admission(
                check_and_reserve=_check_and_reserve,
                admission=admission,
                initial_context=context,
                estimated_tokens=5,
                lazy_policy=lazy,
                request_id="waiter-1",
                release_admission_slot=_release_slot,
                max_waiting_total=256,
                lease_ttl_seconds=300,
            )
        )

        # The helper's waiting lease is visible from the OTHER instance.
        await _wait_zcard(client_a, per_key_waiting_key(key_id), 1, timeout=5)
        await _wait_zcard(client_a, global_waiting_key(), 1, timeout=5)

        # Per-key waiting cap = 1: a second waiter for the same key is
        # refused while the helper waits.
        second_lease = await admission.acquire_waiting_lease(
            gateway_key_id=key_id,
            request_id="waiter-2",
            lease_deadline=lease_deadline,
            max_waiting_per_key=lazy.max_waiting_requests,
            max_waiting_total=256,
            lease_ttl_seconds=300,
        )
        assert second_lease is False
        await admission.release_waiting_lease(gateway_key_id=key_id, request_id="waiter-2")

        # While waiting, the waiter incremented nothing.
        assert await _counter_sum(client_a, "requests") == 1
        assert await _counter_sum(client_a, "tokens") == 5

        # Release from instance A -> instance B's waiter is admitted.
        await service_a.release_concurrency(gateway_key_id=key_id, request_id="blocker")
        outcome = await asyncio.wait_for(task, timeout=15)
        assert outcome.result.allowed is True

        # Every exit releases the waiting lease; nothing lingers.
        assert int(await client_a.zcard(per_key_waiting_key(key_id)) or 0) == 0
        assert int(await client_a.zcard(global_waiting_key()) or 0) == 0

        # The waiter now holds the single slot: a late reservation is denied.
        with pytest.raises(ConcurrencyRateLimitExceededError):
            await service_a.check_and_reserve(
                gateway_key_id=key_id, request_id="late", estimated_tokens=1, policy=policy
            )
        # The waiter admitted exactly once: counters show blocker + waiter only.
        assert await _counter_sum(client_a, "requests") == 2
        assert await _counter_sum(client_a, "tokens") == 10
        await service_b.release_concurrency(gateway_key_id=key_id, request_id="waiter-1")
    finally:
        await client_a.aclose()
        await client_b.aclose()


@pytest.mark.asyncio
async def test_global_waiting_cap_across_keys(owned_redis_url: str) -> None:
    """Deployment-wide waiting cap: a third key cannot join a full queue.

    Two keys' waiters fill the global cap of 2 (from instance B); a third
    key's bounded wait must refuse with the waiting-capacity-full error
    BEFORE holding any lease, and releasing the blockers admits the two
    queued waiters exactly once each.
    """
    client_a = Redis.from_url(owned_redis_url, decode_responses=True)
    client_b = Redis.from_url(owned_redis_url, decode_responses=True)
    try:
        service_a = RedisRateLimitService(client_a, fail_closed=True)
        service_b = RedisRateLimitService(client_b, fail_closed=True)
        admission = LazyThrottlingAdmission(client_b, fail_closed=True)

        keys = [uuid.uuid4() for _ in range(3)]
        policy = RateLimitPolicy(
            concurrent_requests=1,
            requests_per_minute=5,
            tokens_per_minute=20,
            window_seconds=300,
            concurrency_ttl_seconds=30,
            concurrency_heartbeat_seconds=5,
        )
        lazy = LazyThrottlingPolicy(mode="wait", max_wait_seconds=30, max_waiting_requests=10)

        for index, key_id in enumerate(keys[:2]):
            result = await service_a.check_and_reserve(
                gateway_key_id=key_id,
                request_id=f"blocker-{index}",
                estimated_tokens=5,
                policy=policy,
            )
            assert result.allowed is True

        async def _waiter(key_id: uuid.UUID, request_id: str) -> object:
            context = LazyAdmissionContext(
                gateway_key_id=key_id,
                authenticated_key=object(),
                limiter_policy=policy,
                policy_result=None,
                route=None,
                estimated_tokens=5,
            )

            async def _check_and_reserve(**kwargs):
                return await service_b.check_and_reserve(**kwargs)

            async def _release_slot() -> None:
                await service_b.release_concurrency(gateway_key_id=key_id, request_id=request_id)

            return await wait_for_rate_limit_admission(
                check_and_reserve=_check_and_reserve,
                admission=admission,
                initial_context=context,
                estimated_tokens=5,
                lazy_policy=lazy,
                request_id=request_id,
                release_admission_slot=_release_slot,
                max_waiting_total=2,
                lease_ttl_seconds=300,
            )

        task_a = asyncio.create_task(_waiter(keys[0], "waiter-a"))
        await _wait_zcard(client_a, global_waiting_key(), 1, timeout=5)
        task_b = asyncio.create_task(_waiter(keys[1], "waiter-b"))
        await _wait_zcard(client_a, global_waiting_key(), 2, timeout=5)

        # Third key: the deployment-wide cap is full; refused before any
        # waiting lease is held.
        with pytest.raises(LazyThrottlingWaitingCapacityFullError):
            await _waiter(keys[2], "waiter-c")
        assert int(await client_a.zcard(global_waiting_key()) or 0) == 2
        assert int(await client_a.zcard(per_key_waiting_key(keys[2])) or 0) == 0

        # Releasing both blockers admits the two queued waiters once each.
        await service_a.release_concurrency(gateway_key_id=keys[0], request_id="blocker-0")
        await service_a.release_concurrency(gateway_key_id=keys[1], request_id="blocker-1")
        outcome_a = await asyncio.wait_for(task_a, timeout=15)
        outcome_b = await asyncio.wait_for(task_b, timeout=15)
        assert outcome_a.result.allowed is True
        assert outcome_b.result.allowed is True
        assert int(await client_a.zcard(global_waiting_key()) or 0) == 0
        for key_id, request_id in ((keys[0], "waiter-a"), (keys[1], "waiter-b")):
            await service_b.release_concurrency(gateway_key_id=key_id, request_id=request_id)
    finally:
        await client_a.aclose()
        await client_b.aclose()


async def _stored_request_ids(database_url: str, gateway_key_id: uuid.UUID) -> set[str]:
    """Request IDs already persisted for one key (reservations + ledger)."""
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            reservations = await session.execute(
                select(QuotaReservation.request_id).where(
                    QuotaReservation.gateway_key_id == gateway_key_id
                )
            )
            ledger = await session.execute(
                select(UsageLedger.request_id).where(
                    UsageLedger.gateway_key_id == gateway_key_id
                )
            )
            return set(reservations.scalars()) | set(ledger.scalars())
    finally:
        await engine.dispose()



async def probe_zcard_check(redis_url: str, key_id: uuid.UUID) -> int:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        return int(await client.zcard(per_key_waiting_key(key_id)) or 0)
    finally:
        await client.aclose()


# --- shared test-only state helpers ------------------------------------------


async def _set_gateway_key_status(
    database_url: str, gateway_key_id: uuid.UUID, status: str
) -> int:
    """Direct SQL lifecycle change (test-only): returns affected rowcount."""
    from sqlalchemy import text

    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("UPDATE gateway_keys SET status = :status WHERE id = :id"),
                {"status": status, "id": gateway_key_id},
            )
            return result.rowcount
    finally:
        await engine.dispose()


async def _set_owner_inactive(database_url: str, owner_id: uuid.UUID) -> int:
    """Direct SQL owner deactivation (test-only): returns affected rowcount."""
    from sqlalchemy import text

    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("UPDATE owners SET is_active = false WHERE id = :id"),
                {"id": owner_id},
            )
            return result.rowcount
    finally:
        await engine.dispose()


def _responses_body(model: str) -> dict[str, object]:
    return {"model": model, "input": PROMPT_TEXT, "store": False}


async def _seed_responses_key(
    database_url: str,
    *,
    model: str,
    rate_limit_policy: dict[str, int | None] | None = None,
    lazy_throttling_policy: dict[str, object] | None = None,
) -> _SeededKey:
    """Seed institution/owner/cohort/provider/route/pricing/key for /v1/responses."""
    from slaif_gateway.config import Settings
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService
    from slaif_gateway.services.responses_route_capabilities import (
        default_responses_capabilities,
    )

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique = uuid.uuid4().hex
    now = datetime.now(UTC)
    responses_endpoint = "/v1/responses"

    async with session_factory() as session:
        institution = await InstitutionsRepository(session).create_institution(
            name=f"SLAIF lazy {unique}", country="SI", notes="lazy throttling integration"
        )
        owner = await OwnersRepository(session).create_owner(
            name="Lazy",
            surname="Client",
            email=f"lazy-client-{unique}@example.org",
            institution_id=institution.id,
            notes="lazy throttling integration owner",
        )
        cohort = await CohortsRepository(session).create_cohort(
            name=f"lazy-{unique}",
            description="lazy throttling integration cohort",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        providers = ProviderConfigsRepository(session)
        provider_config = await providers.get_provider_config_by_provider("openai")
        if provider_config is None:
            await providers.create_provider_config(
                provider="openai",
                display_name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                notes="lazy throttling integration provider",
            )
        else:
            await providers.update_provider_metadata(
                provider_config.id,
                display_name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                notes="lazy throttling integration provider",
            )
            await providers.set_provider_enabled(provider_config.id, enabled=True)

        routes = ModelRoutesRepository(session)
        await routes.create_model_route(
            requested_model=model,
            provider="openai",
            upstream_model=model,
            match_type="exact",
            endpoint=responses_endpoint,
            priority=1,
            visible_in_models=True,
            supports_streaming=False,
            capabilities={"responses": default_responses_capabilities()},
            notes="lazy throttling integration responses route",
        )
        await PricingRulesRepository(session).create_pricing_rule(
            provider="openai",
            upstream_model=model,
            endpoint=responses_endpoint,
            valid_from=now - timedelta(days=1),
            currency="EUR",
            input_price_per_1m=Decimal("1.000000000"),
            output_price_per_1m=Decimal("1.000000000"),
            request_price=Decimal("0.000000000"),
            pricing_metadata={},
            notes="lazy throttling integration responses pricing",
        )

        key_service = KeyService(
            settings=Settings(),
            gateway_keys_repository=GatewayKeysRepository(session),
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            audit_repository=AuditRepository(session),
        )
        created = await key_service.create_gateway_key(
            CreateGatewayKeyInput(
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(minutes=5),
                valid_until=now + timedelta(hours=1),
                cost_limit_eur=Decimal("10.000000000"),
                token_limit_total=100_000,
                request_limit_total=100,
                allowed_models=[model],
                allowed_endpoints=[responses_endpoint],
                rate_limit_policy=rate_limit_policy,
                lazy_throttling_policy=lazy_throttling_policy,
                note="lazy throttling integration responses key",
            )
        )
        await session.commit()
        result = _SeededKey(
            plaintext_gateway_key=created.plaintext_key,
            gateway_key_id=created.gateway_key_id,
            public_key_id=created.public_key_id,
        )
    await engine.dispose()
    return result


def _make_holding_responses_adapter(model, calls, first_entered, first_release):
    """Mocked provider: the first /v1/responses call holds the concurrency slot."""
    from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage

    class _HoldingResponsesAdapter:
        def __init__(self) -> None:
            self._first_held = False

        async def forward_response(self, request):
            calls.append(request.request_id)
            if not self._first_held:
                self._first_held = True
                first_entered.set()
                while not first_release.is_set():
                    await asyncio.sleep(0.05)
            return ProviderResponse(
                provider="openai",
                upstream_model=model,
                status_code=200,
                json_body={
                    "id": "resp-lazy-wait",
                    "object": "response",
                    "model": model,
                    "status": "completed",
                    "output": [],
                    "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
                    "store": False,
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )

    return _HoldingResponsesAdapter()


async def _stored_gateway_key_row(
    database_url: str, gateway_key_id: uuid.UUID
) -> object:
    """Fetch the stored gateway_keys row (test-only read)."""
    from sqlalchemy import select

    from slaif_gateway.db.models import GatewayKey

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(GatewayKey).where(GatewayKey.id == gateway_key_id)
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _audit_rows_for_key(
    database_url: str, gateway_key_id: uuid.UUID
) -> list[object]:
    """Audit rows for one key, oldest first."""
    from sqlalchemy import select

    from slaif_gateway.db.models import AuditLog

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(AuditLog)
                .where(AuditLog.entity_id == gateway_key_id)
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            )
            return list(result.scalars())
    finally:
        await engine.dispose()


# --- V3/V4: actual HTTP Chat wait -> admit, real PG accounting ---------------


def _chat_body(
    model: str, *, stream: bool = False, max_tokens: int = 20
) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT_TEXT}],
        "max_tokens": max_tokens,
        "stream": stream,
    }


async def _ledger_rows(database_url: str, gateway_key_id: uuid.UUID) -> list[dict[str, object]]:
    """Actual finalization rows for one key (token + cost amounts)."""
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(UsageLedger)
                .where(UsageLedger.gateway_key_id == gateway_key_id)
                .order_by(UsageLedger.created_at)
            )
            return [
                {
                    "request_id": row.request_id,
                    "total_tokens": row.total_tokens,
                    "actual_cost_eur": row.actual_cost_eur,
                }
                for row in result.scalars()
            ]
    finally:
        await engine.dispose()



async def _assert_no_checked_out_pool_connections(app, samples: int = 3) -> None:
    """The waiting request must not hold an app DB session/connection.

    Sample the app engine pool a few times across the settled wait/sleep
    phase: any checked-out connection would be a held session/transaction
    on the waiting request path.
    """
    for _ in range(samples):
        checked_out = app.state.db_engine.pool.checkedout()
        assert checked_out == 0, (
            f"app pool has {checked_out} checked-out connection(s) while waiting"
        )
        await asyncio.sleep(0.15)


def test_http_chat_waits_for_capacity_then_admits_once(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real uvicorn app: a wait-mode request waits while capacity is held.

    One key with a single concurrency slot and wait mode. Request 1 holds
    the slot in a slow (mocked) provider call; request 2 is denied by the
    limiter, WAITS (bounded lazy admission), and is admitted exactly once
    after request 1 finishes. While request 2 waits: zero new
    quota-reservation/ledger rows for the key and zero checked-out app DB
    connections. After admission: exactly one normal
    reservation/finalization pair and exactly one provider invocation per
    request.
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()

    from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage

    class _CountingAdapter:
        def __init__(self) -> None:
            self._first_held = False

        async def forward_chat_completion(self, request):
            calls.append(request.request_id)
            if not self._first_held:
                self._first_held = True
                first_entered.set()
                # Hold the only concurrency slot (the real request path keeps
                # it reserved until finalization).
                while not first_release.is_set():
                    await asyncio.sleep(0.05)
            return ProviderResponse(
                provider="openai",
                upstream_model=model,
                status_code=200,
                json_body={
                    "id": "chatcmpl-lazy-wait",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": COMPLETION_TEXT},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: _CountingAdapter()
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    base = f"http://127.0.0.1:{port}"
    responses: list[httpx.Response] = []

    def _post() -> None:
        with httpx.Client(timeout=60.0) as client:
            responses.append(
                client.post(
                    f"{base}/v1/chat/completions",
                    json=_chat_body(model),
                    headers=headers,
                )
            )

    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    async def _observe_waiting() -> None:
        # Request 2 must be observable WAITING (bounded lease, per-key ZSET)
        # while request 1 still holds the slot.
        try:
            await _wait_zcard(probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=20)
        finally:
            await probe.aclose()

    thread1 = threading.Thread(target=_post)
    thread2 = threading.Thread(target=_post)
    with _run_uvicorn_server(app, port):
        thread1.start()
        try:
            assert first_entered.wait(timeout=20), "first provider call did not start"

            baseline = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))

            thread2.start()

            # Observe request 2 actually waiting.
            asyncio.run(_observe_waiting())

            # While request 2 waits: no new reservation/ledger rows, and no
            # app DB session/connection is held by the waiting request path.
            mid = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
            assert mid == baseline, (
                f"waiting must not mutate accounting: baseline={baseline} mid={mid}"
            )
            asyncio.run(_assert_no_checked_out_pool_connections(app))
        finally:
            # Release the slot and drain both requests even when an
            # assertion above fails (harness cleanup, not a product path).
            first_release.set()
            thread1.join(timeout=30)
            thread2.join(timeout=30)
            assert not thread1.is_alive()
            assert not thread2.is_alive()

    assert [r.status_code for r in responses] == [200, 200], [
        (r.status_code, r.text[:300]) for r in responses
    ]
    assert len(calls) == 2, "each request must invoke the provider exactly once"
    assert COMPLETION_TEXT in responses[1].text

    final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
    assert final[0] == baseline[0] + 1, (
        f"the waited request reserved exactly once: baseline={baseline} final={final}"
    )
    # One normal finalization per completed request (request 1 and the waited
    # request 2): exactly two ledger rows, each attributed to its own gateway
    # request ID (matching the two provider calls) with the exact per-request
    # amounts (no double charge, redistribution, or extra charge, nothing
    # from the waiting phase).
    ledger = asyncio.run(_ledger_rows(owned_pg_url, seeded.gateway_key_id))
    assert len(ledger) == 2, f"expected exactly two finalizations, got {ledger}"
    assert {row["request_id"] for row in ledger} == set(calls), (
        f"ledger rows must be attributed to the two provider calls: "
        f"{ledger} vs {calls}"
    )
    for row in ledger:
        assert row["total_tokens"] == 11, row
        assert row["actual_cost_eur"] == Decimal("0.000011"), row
    assert sum(row["total_tokens"] for row in ledger) == 22, ledger
    expected_cost = Decimal("0.000011") * 2
    assert sum(
        (row["actual_cost_eur"] for row in ledger), Decimal("0")
    ) == expected_cost, ledger
    # Waiting left no waiting-lease behind.
    leftovers = asyncio.run(probe_zcard_check(owned_redis_url, seeded.gateway_key_id))
    assert leftovers == 0


# --- V3/V4: HTTP negatives (Chat) -------------------------------------------


def _start_holding_request(
    *,
    base: str,
    model: str,
    headers: dict[str, str],
) -> threading.Thread:
    """POST one non-streaming chat request (its provider call may hold a slot)."""
    def _post() -> None:
        with httpx.Client(timeout=90.0) as client:
            client.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
            )

    return threading.Thread(target=_post)


def test_http_chat_default_mode_denies_immediately(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject mode (the default) keeps immediate 429 under the same contention.

    No waiting lease may ever be acquired; the provider is invoked exactly
    once (the holding request only).
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy=None,  # missing policy -> reject default
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    async def _observe_no_wait() -> None:
        try:
            # Give the second request time to arrive, be denied, and (if
            # buggy) acquire a waiting lease; it must never wait.
            await asyncio.sleep(1.0)
            assert int(await probe.zcard(per_key_waiting_key(seeded.gateway_key_id)) or 0) == 0
            assert int(await probe.zcard(global_waiting_key()) or 0) == 0
        finally:
            await probe.aclose()

    holder = _start_holding_request(base=base, model=model, headers=headers)
    with _run_uvicorn_server(app, port):
        holder.start()
        try:
            assert first_entered.wait(timeout=20)
            denied = httpx.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
                timeout=30.0,
            )
            assert denied.status_code == 429
            assert denied.json()["error"]["code"] == "concurrency_rate_limit_exceeded"
            asyncio.run(_observe_no_wait())
        finally:
            first_release.set()
            holder.join(timeout=30)
            assert not holder.is_alive()

    assert len(calls) == 1, "default reject mode must not forward the denied request"


def test_http_chat_wait_mode_deadline_429(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wait-mode request that cannot fit before max_wait fails at 429.

    max_wait_seconds=1 while the slot is held for ~4s: the honest deadline
    error is returned, no provider call occurs for the waiter, and the
    waiting lease is cleaned up.
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 1, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    async def _observe_deadline_cleanup() -> None:
        try:
            # The 429 above already proves the wait ended; the lease must be
            # gone (cleanup on the deadline path), not merely expired later.
            await asyncio.sleep(0.3)
            assert int(await probe.zcard(per_key_waiting_key(seeded.gateway_key_id)) or 0) == 0
            assert int(await probe.zcard(global_waiting_key()) or 0) == 0
        finally:
            await probe.aclose()

    holder = _start_holding_request(base=base, model=model, headers=headers)
    with _run_uvicorn_server(app, port):
        holder.start()
        try:
            assert first_entered.wait(timeout=20)
            started = time.monotonic()
            denied = httpx.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
                timeout=30.0,
            )
            elapsed = time.monotonic() - started
            assert denied.status_code == 429
            assert denied.json()["error"]["code"] == "lazy_throttling_deadline_exceeded"
            assert elapsed < 3.0, f"deadline 429 came too late: {elapsed:.2f}s"
            asyncio.run(_observe_deadline_cleanup())
        finally:
            first_release.set()
            holder.join(timeout=30)
            assert not holder.is_alive()

    assert len(calls) == 1, "the deadline waiter must never reach the provider"


def test_http_chat_waiting_capacity_full_429(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With max_waiting_requests=1, a third request cannot join the queue."""
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 1},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    waited: list[httpx.Response] = []

    holder = _start_holding_request(base=base, model=model, headers=headers)
    waiter_thread = threading.Thread(
        target=lambda: waited.append(
            httpx.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
                timeout=60.0,
            )
        )
    )
    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    async def _observe_waiter_holds_slot() -> None:
        try:
            await _wait_zcard(
                probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=15
            )
        finally:
            await probe.aclose()

    with _run_uvicorn_server(app, port):
        holder.start()
        waiter_thread.start()
        try:
            assert first_entered.wait(timeout=20)
            # The waiter occupies the single waiting slot.
            asyncio.run(_observe_waiter_holds_slot())
            full = httpx.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
                timeout=30.0,
            )
            assert full.status_code == 429
            assert full.json()["error"]["code"] == "lazy_throttling_waiting_capacity_full"
        finally:
            first_release.set()
            waiter_thread.join(timeout=30)
            holder.join(timeout=30)
            assert not waiter_thread.is_alive()
            assert not holder.is_alive()
    assert len(waited) == 1
    assert waited[0].status_code == 200, waited[0].text[:300]

    assert len(calls) == 2, "the cap-full request must never reach the provider"


def _make_holding_chat_adapter(model, calls, first_entered, first_release):
    """Mocked provider: the first call holds the concurrency slot."""
    from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage

    class _HoldingAdapter:
        def __init__(self) -> None:
            self._first_held = False

        async def forward_chat_completion(self, request):
            calls.append(request.request_id)
            if not self._first_held:
                self._first_held = True
                first_entered.set()
                while not first_release.is_set():
                    await asyncio.sleep(0.05)
            return ProviderResponse(
                provider="openai",
                upstream_model=model,
                status_code=200,
                json_body={
                    "id": "chatcmpl-lazy-neg",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": COMPLETION_TEXT},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )

    return _HoldingAdapter()


# --- V2: deadline / cancellation / crash-expiry lease cleanup ---------------


@pytest.mark.asyncio
async def test_deadline_cancel_and_crash_expiry_release_leases(
    owned_redis_url: str,
) -> None:
    """Every non-admission exit path releases the waiting lease promptly.

    (a) deadline exhaustion, (b) external task cancellation, and (c) crashed
    worker leases (pre-seeded expired members) all leave the per-key and
    global waiting ZSETs empty; the expired-member sweep happens on the next
    acquisition.
    """
    client = Redis.from_url(owned_redis_url, decode_responses=True)
    try:
        service = RedisRateLimitService(client, fail_closed=True)
        admission = LazyThrottlingAdmission(client, fail_closed=True)
        policy = RateLimitPolicy(
            concurrent_requests=1,
            window_seconds=300,
            concurrency_ttl_seconds=30,
            concurrency_heartbeat_seconds=5,
        )
        lease_deadline = datetime.fromtimestamp(time.time() + 300, tz=UTC)

        def _context(key_id: uuid.UUID) -> LazyAdmissionContext:
            return LazyAdmissionContext(
                gateway_key_id=key_id,
                authenticated_key=object(),
                limiter_policy=policy,
                policy_result=None,
                route=None,
                estimated_tokens=5,
            )

        # (a) deadline: slot held longer than max_wait -> 429 deadline error,
        # lease released on the deadline path.
        key_a = uuid.uuid4()
        await service.check_and_reserve(
            gateway_key_id=key_a, request_id="blocker-a", estimated_tokens=5, policy=policy
        )
        with pytest.raises(LazyThrottlingDeadlineExceededError):
            await wait_for_rate_limit_admission(
                check_and_reserve=lambda **kw: service.check_and_reserve(**kw),
                admission=admission,
                initial_context=_context(key_a),
                estimated_tokens=5,
                lazy_policy=LazyThrottlingPolicy(mode="wait", max_wait_seconds=1, max_waiting_requests=2),
                request_id="waiter-a",
                max_waiting_total=256,
                lease_ttl_seconds=300,
            )
        assert int(await client.zcard(per_key_waiting_key(key_a)) or 0) == 0
        assert int(await client.zcard(global_waiting_key()) or 0) == 0
        await service.release_concurrency(gateway_key_id=key_a, request_id="blocker-a")

        # (b) cancellation: an external task cancel during the wait releases
        # the lease (idempotent finally path) and propagates CancelledError.
        key_b = uuid.uuid4()
        await service.check_and_reserve(
            gateway_key_id=key_b, request_id="blocker-b", estimated_tokens=5, policy=policy
        )
        task = asyncio.create_task(
            wait_for_rate_limit_admission(
                check_and_reserve=lambda **kw: service.check_and_reserve(**kw),
                admission=admission,
                initial_context=_context(key_b),
                estimated_tokens=5,
                lazy_policy=LazyThrottlingPolicy(mode="wait", max_wait_seconds=30, max_waiting_requests=2),
                request_id="waiter-b",
                max_waiting_total=256,
                lease_ttl_seconds=300,
            )
        )
        await _wait_zcard(client, per_key_waiting_key(key_b), 1, timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert int(await client.zcard(per_key_waiting_key(key_b)) or 0) == 0
        assert int(await client.zcard(global_waiting_key()) or 0) == 0
        await service.release_concurrency(gateway_key_id=key_b, request_id="blocker-b")

        # (c) crash expiry: a crashed waiter's expired lease is swept by the
        # next acquisition and does not count against the cap.
        key_c = uuid.uuid4()
        expired_ms = int((time.time() - 120) * 1000)
        member = f"{key_c}:crashed-waiter"
        await client.zadd(per_key_waiting_key(key_c), {member: expired_ms})
        await client.zadd(global_waiting_key(), {member: expired_ms})
        acquired = await admission.acquire_waiting_lease(
            gateway_key_id=key_c,
            request_id="waiter-c",
            lease_deadline=lease_deadline,
            max_waiting_per_key=1,
            max_waiting_total=256,
            lease_ttl_seconds=300,
        )
        assert acquired is True
        # The crashed member is gone; only the live waiter remains.
        assert await client.zscore(per_key_waiting_key(key_c), member) is None
        assert await client.zscore(global_waiting_key(), member) is None
        assert int(await client.zcard(per_key_waiting_key(key_c)) or 0) == 1
        await admission.release_waiting_lease(gateway_key_id=key_c, request_id="waiter-c")
        assert int(await client.zcard(per_key_waiting_key(key_c)) or 0) == 0
        assert int(await client.zcard(global_waiting_key()) or 0) == 0
    finally:
        await client.aclose()


# --- V3: streaming wait -> admit --------------------------------------------


def test_http_chat_streaming_waits_for_capacity_then_admits(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A streaming wait-mode request waits, then streams its normal result."""
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()

    from slaif_gateway.schemas.providers import (
        ProviderResponse,
        ProviderStreamChunk,
        ProviderUsage,
    )

    class _HoldingStreamingAdapter:
        def __init__(self) -> None:
            self._first_held = False

        async def forward_chat_completion(self, request):
            calls.append(request.request_id)
            if not self._first_held:
                self._first_held = True
                first_entered.set()
                while not first_release.is_set():
                    await asyncio.sleep(0.05)
            return ProviderResponse(
                provider="openai",
                upstream_model=model,
                status_code=200,
                json_body={
                    "id": "chatcmpl-lazy-stream-holder",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": COMPLETION_TEXT},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )

        async def stream_chat_completion(self, request):
            calls.append(request.request_id)
            yield ProviderStreamChunk(
                provider="openai",
                upstream_model=model,
                data='{"id":"lazy-stream","choices":[{"delta":{"content":"ok"}}]}',
                raw_sse_event='data: {"id":"lazy-stream","choices":[{"delta":{"content":"ok"}}]}\n\n',
            )
            yield ProviderStreamChunk(
                provider="openai",
                upstream_model=model,
                data=(
                    '{"id":"lazy-stream-usage","choices":[],"usage":'
                    '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}'
                ),
                raw_sse_event=(
                    'data: {"id":"lazy-stream-usage","choices":[],"usage":'
                    '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
                ),
                json_body={
                    "id": "lazy-stream-usage",
                    "choices": [],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )
            yield ProviderStreamChunk(
                provider="openai",
                upstream_model=model,
                data="[DONE]",
                raw_sse_event="data: [DONE]\n\n",
                is_done=True,
            )

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: _HoldingStreamingAdapter()
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    stream_body: list[str] = []
    stream_status: list[int] = []

    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    async def _observe_waiting() -> None:
        try:
            await _wait_zcard(probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=20)
        finally:
            await probe.aclose()

    def _stream_post() -> None:
        with httpx.Client(timeout=60.0) as client:
            with client.stream(
                "POST",
                f"{base}/v1/chat/completions",
                json=_chat_body(model, stream=True),
                headers=headers,
            ) as response:
                stream_status.append(response.status_code)
                stream_body.extend(response.iter_text())

    holder = _start_holding_request(base=base, model=model, headers=headers)
    waiter = threading.Thread(target=_stream_post)
    with _run_uvicorn_server(app, port):
        holder.start()
        try:
            assert first_entered.wait(timeout=20)
            baseline = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
            waiter.start()
            asyncio.run(_observe_waiting())
            mid = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
            assert mid == baseline, (
                f"streaming wait must not mutate accounting: baseline={baseline} mid={mid}"
            )
        finally:
            first_release.set()
            holder.join(timeout=30)
            waiter.join(timeout=30)
            assert not holder.is_alive()
            assert not waiter.is_alive()

    assert stream_status == [200]
    body = "".join(stream_body)
    assert "data: [DONE]" in body
    assert len(calls) == 2, "each request must invoke the provider exactly once"
    final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
    assert final == (baseline[0] + 1, baseline[1] + 2), (
        f"one reservation + one finalization per completed request: "
        f"baseline={baseline} final={final}"
    )


# --- V3: actual client socket disconnect before admission -------------------


def _send_raw_chat_request(port: int, *, model: str, key: str) -> socket.socket:
    """Open a raw TCP socket and send one complete chat request."""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT_TEXT}],
            "max_tokens": 20,
            "stream": False,
        }
    ).encode("utf-8")
    request = (
        f"POST /v1/chat/completions HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Authorization: Bearer {key}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("utf-8") + body
    sock = socket.create_connection(("127.0.0.1", port), timeout=30.0)
    sock.sendall(request)
    return sock


def test_http_chat_real_socket_disconnect_before_admission(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed client socket aborts the wait BEFORE provider work.

    The waiter's TCP connection is actually closed while it holds a waiting
    lease. The server must detect the disconnect through the transport
    (not synthetic task cancellation): no provider call, no accounting rows,
    no waiting lease, and the server stays healthy for the next request.
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )


    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    sock: socket.socket | None = None
    waiter_request_ids: list[str] = []

    async def _wait_close_and_observe_cleanup() -> None:
        # One coroutine, one connection, one loop: observe the waiter's
        # lease (capturing its opaque request ID), close its actual TCP
        # socket, then observe the lease cleanup.
        try:
            await _wait_zcard(probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=20)
            members = await probe.zrange(per_key_waiting_key(seeded.gateway_key_id), 0, -1)
            assert len(members) == 1, members
            member = str(members[0])
            key_prefix = f"{seeded.gateway_key_id}:"
            assert member.startswith(key_prefix), member
            waiter_request_ids.append(member[len(key_prefix):])
            assert sock is not None
            sock.close()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if int(await probe.zcard(per_key_waiting_key(seeded.gateway_key_id)) or 0) == 0:
                    break
                await asyncio.sleep(0.1)
            assert int(await probe.zcard(per_key_waiting_key(seeded.gateway_key_id)) or 0) == 0
            assert int(await probe.zcard(global_waiting_key()) or 0) == 0
        finally:
            await probe.aclose()

    holder = _start_holding_request(base=base, model=model, headers=headers)
    with _run_uvicorn_server(app, port):
        holder.start()
        try:
            assert first_entered.wait(timeout=20)
            baseline = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
            sock = _send_raw_chat_request(port, model=model, key=seeded.plaintext_gateway_key)
            asyncio.run(_wait_close_and_observe_cleanup())
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            first_release.set()
            holder.join(timeout=30)
            assert not holder.is_alive()

        # The disconnected waiter never reached the provider and never
        # reserved: its opaque request ID (captured from the waiting lease)
        # is absent from provider calls and from all persisted accounting.
        # (Checked while the server is still up, before the healthy check.)
        assert len(waiter_request_ids) == 1
        canceled_request_id = waiter_request_ids[0]
        assert canceled_request_id not in calls, (
            f"a disconnected waiter must never reach the provider: {calls}"
        )
        assert len(calls) == 1, "only the holder may have reached the provider"
        stored = asyncio.run(_stored_request_ids(owned_pg_url, seeded.gateway_key_id))
        assert canceled_request_id not in stored, stored
        mid = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
        assert mid == (baseline[0], baseline[1] + 1), (
            f"only the holder may have finalized so far: baseline={baseline} mid={mid}"
        )

        # The server must still be healthy after the abrupt disconnect: a
        # normal request now succeeds (itself a billable model call).
        healthy = httpx.post(
            f"{base}/v1/chat/completions",
            json=_chat_body(model),
            headers=headers,
            timeout=30.0,
        )
        assert healthy.status_code == 200, healthy.text[:300]
        assert len(calls) == 2, "holder + healthy: exactly two provider calls"
        final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
        assert final == (baseline[0] + 1, baseline[1] + 2), (
            f"holder + healthy requests finalize normally after the cancel: "
            f"baseline={baseline} final={final}"
        )
        final_stored = asyncio.run(_stored_request_ids(owned_pg_url, seeded.gateway_key_id))
        assert canceled_request_id not in final_stored, final_stored


# --- V4: hard quota refusal is immediate, never a waiting candidate (R5) -----


def test_http_chat_hard_quota_refuses_immediately_without_waiting(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request that cannot fit its hard quota fails immediately.

    request_limit_total=1 with the holder already reserving the single
    permitted request. The waiter is denied by the Redis concurrency limiter,
    enters the wait branch, and the non-mutating hard-quota preflight refuses
    it with 429 quota_limit_exceeded BEFORE any waiting lease is acquired: no
    queue slot, no provider call, no new reservation/ledger row.
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
            request_limit_total=1,
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}

    # Continuously sample the per-key waiting ZSET for the whole waiter
    # flight: entering the wait branch holds its lease at least across the
    # initial sleep, so any waiting would be observed.
    max_waiting_observed = 0
    sampler_stop = threading.Event()
    sampled = {"done": False}

    def _sample_waiting_lease() -> None:
        nonlocal max_waiting_observed
        import redis as redis_sync

        client = redis_sync.Redis.from_url(owned_redis_url, decode_responses=True)
        try:
            while not sampler_stop.is_set():
                count = int(
                    client.zcard(per_key_waiting_key(seeded.gateway_key_id)) or 0
                )
                if count > max_waiting_observed:
                    max_waiting_observed = count
                time.sleep(0.02)
        finally:
            client.close()
            sampled["done"] = True

    sampler = threading.Thread(target=_sample_waiting_lease)
    holder = _start_holding_request(base=base, model=model, headers=headers)
    waiter_responses: list[httpx.Response] = []

    def _waiter() -> None:
        with httpx.Client(timeout=30.0) as client:
            waiter_responses.append(
                client.post(
                    f"{base}/v1/chat/completions",
                    json=_chat_body(model, max_tokens=40),
                    headers=headers,
                )
            )

    waiter = threading.Thread(target=_waiter)
    with _run_uvicorn_server(app, port):
        sampler.start()
        holder.start()
        try:
            assert first_entered.wait(timeout=20), "first provider call did not start"
            baseline = asyncio.run(
                _side_effect_counts(owned_pg_url, seeded.gateway_key_id)
            )
            waiter.start()
            waiter.join(timeout=30)
            assert not waiter.is_alive(), "hard-quota waiter did not return"
            # The holder still owns the slot: the waiter is already refused.
            assert asyncio.run(
                probe_zcard_check(owned_redis_url, seeded.gateway_key_id)
            ) == 0
        finally:
            sampler_stop.set()
            first_release.set()
            holder.join(timeout=30)
            assert not holder.is_alive()
            if waiter.is_alive():
                waiter.join(timeout=10)
            sampler.join(timeout=10)
            assert not sampler.is_alive()

    assert max_waiting_observed == 0, (
        "a hard-quota refusal must never hold a waiting lease"
    )
    assert len(waiter_responses) == 1
    assert waiter_responses[0].status_code == 429, waiter_responses[0].text[:300]
    assert waiter_responses[0].json()["error"]["code"] == "quota_limit_exceeded"
    # Only the holder reached the provider; only the holder finalized.
    assert len(calls) == 1, calls
    final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
    # The holder's in-flight reservation is already in the baseline; the
    # hard-quota waiter must add NO reservation and NO finalization, while the
    # holder's own reservation finalizes to exactly one ledger row.
    assert final == (baseline[0], baseline[1] + 1), (
        f"the hard-quota waiter must leave no reservation/ledger: "
        f"baseline={baseline} final={final}"
    )


# --- V4: revocation while waiting prevents old-policy forwarding -------------


def test_http_chat_revoked_while_waiting_refuses_403(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key revoked while a request waits is refused at revalidation.

    The waiter is observed holding its waiting lease (per-key ZSET member
    {key_id}:{request_id}); the key is then revoked directly in PostgreSQL.
    The waiter's revalidation after the wait must refuse with 403
    gateway_key_revoked instead of forwarding under its stale pre-wait
    authorization: no provider call and no persisted accounting under the
    waiter's opaque request ID. The already-admitted holder finalizes
    normally (revalidation gates requests still waiting, not in-flight work).
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    probe = Redis.from_url(owned_redis_url, decode_responses=True)
    waiter_request_ids: list[str] = []

    async def _observe_waiter_then_revoke() -> None:
        try:
            await _wait_zcard(
                probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=20
            )
            members = await probe.zrange(
                per_key_waiting_key(seeded.gateway_key_id), 0, -1
            )
            assert len(members) == 1, members
            member = str(members[0])
            prefix = f"{seeded.gateway_key_id}:"
            assert member.startswith(prefix), member
            waiter_request_ids.append(member[len(prefix):])
            # Revoke while the waiter still holds its waiting lease.
            assert await _set_gateway_key_status(
                owned_pg_url, seeded.gateway_key_id, "revoked"
            ) == 1
        finally:
            await probe.aclose()

    holder = _start_holding_request(base=base, model=model, headers=headers)
    waiter_responses: list[httpx.Response] = []
    waiter = threading.Thread(
        target=lambda: waiter_responses.append(
            httpx.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
                timeout=60.0,
            )
        )
    )
    with _run_uvicorn_server(app, port):
        holder.start()
        try:
            assert first_entered.wait(timeout=20), "first provider call did not start"
            baseline = asyncio.run(
                _side_effect_counts(owned_pg_url, seeded.gateway_key_id)
            )
            waiter.start()
            asyncio.run(_observe_waiter_then_revoke())
            waiter.join(timeout=30)
            assert not waiter.is_alive(), "revoked waiter did not return"
        finally:
            first_release.set()
            holder.join(timeout=30)
            assert not holder.is_alive()
            if waiter.is_alive():
                waiter.join(timeout=10)

    assert len(waiter_request_ids) == 1
    canceled_request_id = waiter_request_ids[0]
    assert len(waiter_responses) == 1
    assert waiter_responses[0].status_code == 403, waiter_responses[0].text[:300]
    assert waiter_responses[0].json()["error"]["code"] == "gateway_key_revoked"
    # The revoked waiter never reached the provider and never reserved.
    assert len(calls) == 1, calls
    assert canceled_request_id not in calls, calls
    stored = asyncio.run(_stored_request_ids(owned_pg_url, seeded.gateway_key_id))
    assert canceled_request_id not in stored, stored
    # The already-admitted holder finalizes normally.
    final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
    # The holder's in-flight reservation is already in the baseline; the
    # revoked waiter adds nothing, and the holder finalizes exactly once.
    assert final == (baseline[0], baseline[1] + 1), (
        f"the admitted holder finalizes once: baseline={baseline} final={final}"
    )
    # No waiting lease left behind by the refused waiter.
    assert asyncio.run(probe_zcard_check(owned_redis_url, seeded.gateway_key_id)) == 0


def test_http_chat_owner_inactive_while_waiting_refuses_403(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An owner deactivated while a request waits is refused at revalidation.

    The waiter is observed holding its waiting lease (per-key ZSET member
    {key_id}:{request_id}); the owner is then deactivated directly in
    PostgreSQL. The waiter's revalidation after the wait must refuse with 403
    owner_not_active instead of forwarding under its stale pre-wait
    authorization: no provider call and no persisted accounting under the
    waiter's opaque request ID. The already-admitted holder finalizes
    normally (revalidation gates requests still waiting, not in-flight work).
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-http-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_chat_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_chat_adapter(model, calls, first_entered, first_release)

    import slaif_gateway.services.chat_completion_gateway as chat_gateway

    monkeypatch.setattr(
        chat_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    probe = Redis.from_url(owned_redis_url, decode_responses=True)
    waiter_request_ids: list[str] = []

    async def _observe_waiter_then_deactivate_owner() -> None:
        try:
            await _wait_zcard(
                probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=20
            )
            members = await probe.zrange(
                per_key_waiting_key(seeded.gateway_key_id), 0, -1
            )
            assert len(members) == 1, members
            member = str(members[0])
            prefix = f"{seeded.gateway_key_id}:"
            assert member.startswith(prefix), member
            waiter_request_ids.append(member[len(prefix):])
            # Deactivate the owner while the waiter still holds its lease.
            key_row = await _stored_gateway_key_row(
                owned_pg_url, seeded.gateway_key_id
            )
            assert await _set_owner_inactive(owned_pg_url, key_row.owner_id) == 1
        finally:
            await probe.aclose()

    holder = _start_holding_request(base=base, model=model, headers=headers)
    waiter_responses: list[httpx.Response] = []
    waiter = threading.Thread(
        target=lambda: waiter_responses.append(
            httpx.post(
                f"{base}/v1/chat/completions",
                json=_chat_body(model),
                headers=headers,
                timeout=60.0,
            )
        )
    )
    with _run_uvicorn_server(app, port):
        holder.start()
        try:
            assert first_entered.wait(timeout=20), "first provider call did not start"
            baseline = asyncio.run(
                _side_effect_counts(owned_pg_url, seeded.gateway_key_id)
            )
            waiter.start()
            asyncio.run(_observe_waiter_then_deactivate_owner())
            waiter.join(timeout=30)
            assert not waiter.is_alive(), "inactive-owner waiter did not return"
        finally:
            first_release.set()
            holder.join(timeout=30)
            assert not holder.is_alive()
            if waiter.is_alive():
                waiter.join(timeout=10)

    assert len(waiter_request_ids) == 1
    canceled_request_id = waiter_request_ids[0]
    assert len(waiter_responses) == 1
    assert waiter_responses[0].status_code == 403, waiter_responses[0].text[:300]
    assert waiter_responses[0].json()["error"]["code"] == "owner_not_active"
    # The refused waiter never reached the provider and never reserved.
    assert len(calls) == 1, calls
    assert canceled_request_id not in calls, calls
    stored = asyncio.run(_stored_request_ids(owned_pg_url, seeded.gateway_key_id))
    assert canceled_request_id not in stored, stored
    # The already-admitted holder finalizes normally.
    final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
    # The holder's in-flight reservation is already in the baseline; the
    # refused waiter adds nothing, and the holder finalizes exactly once.
    assert final == (baseline[0], baseline[1] + 1), (
        f"the admitted holder finalizes once: baseline={baseline} final={final}"
    )
    # No waiting lease left behind by the refused waiter.
    assert asyncio.run(probe_zcard_check(owned_redis_url, seeded.gateway_key_id)) == 0


# --- V3/V4: actual HTTP Responses wait -> admit --------------------------------


def test_http_responses_waits_for_capacity_then_admits(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The /v1/responses seam waits before upstream and admits once.

    One key with a single concurrency slot and wait mode. Request 1 holds the
    slot in a slow (mocked) provider call; request 2 is denied by the limiter,
    WAITS, and is admitted exactly once after request 1 finishes. While
    request 2 waits: zero new reservation/ledger rows and zero checked-out
    app DB connections. After admission: one normal reservation/finalization
    per request and one provider invocation per request.
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-resp-{uuid.uuid4().hex[:12]}"
    seeded = asyncio.run(
        _seed_responses_key(
            owned_pg_url,
            model=model,
            rate_limit_policy={"max_concurrent_requests": 1, "window_seconds": 60},
            lazy_throttling_policy={"mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 2},
        )
    )

    calls: list[str] = []
    first_entered = threading.Event()
    first_release = threading.Event()
    adapter = _make_holding_responses_adapter(
        model, calls, first_entered, first_release
    )

    import slaif_gateway.services.responses_gateway as responses_gateway

    monkeypatch.setattr(
        responses_gateway, "get_provider_adapter", lambda route, settings: adapter
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {seeded.plaintext_gateway_key}"}
    responses_out: list[httpx.Response] = []

    def _post() -> None:
        with httpx.Client(timeout=60.0) as client:
            responses_out.append(
                client.post(
                    f"{base}/v1/responses",
                    json=_responses_body(model),
                    headers=headers,
                )
            )

    # Test-only observation of the wait loop: the helper's sleep seam is
    # wrapped so the waiting request is observed while it is actually asleep
    # (no checked-out app DB connection), BEFORE the holder is released.
    # (A random post-facto sample can catch a brief revalidation query.)
    entered_wait = threading.Event()
    sleep_counts: list[int] = []
    real_wait = responses_gateway.wait_for_rate_limit_admission

    async def _observing_sleep(seconds: float) -> None:
        sleep_counts.append(app.state.db_engine.pool.checkedout())
        entered_wait.set()
        await asyncio.sleep(seconds)

    def _wait_with_observation(**kwargs: object) -> object:
        kwargs["sleep"] = _observing_sleep
        return real_wait(**kwargs)

    monkeypatch.setattr(
        responses_gateway, "wait_for_rate_limit_admission", _wait_with_observation
    )

    probe = Redis.from_url(owned_redis_url, decode_responses=True)

    async def _observe_waiting() -> None:
        try:
            await _wait_zcard(
                probe, per_key_waiting_key(seeded.gateway_key_id), 1, timeout=20
            )
        finally:
            await probe.aclose()

    thread1 = threading.Thread(target=_post)
    thread2 = threading.Thread(target=_post)
    with _run_uvicorn_server(app, port):
        thread1.start()
        try:
            assert first_entered.wait(timeout=20), "first provider call did not start"
            baseline = asyncio.run(
                _side_effect_counts(owned_pg_url, seeded.gateway_key_id)
            )
            thread2.start()
            asyncio.run(_observe_waiting())
            assert entered_wait.wait(timeout=20), (
                "the waiter never entered the bounded wait loop"
            )
            # Observe at least two settled wait-loop iterations while the
            # holder still owns the slot: at each sleep boundary the waiting
            # request must hold no DB connection (the counts are recorded
            # inside the sleep callback, always before first_release).
            deadline = time.monotonic() + 15
            while len(sleep_counts) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(sleep_counts) >= 2, (
                f"expected at least two observed wait-loop sleeps, got {sleep_counts}"
            )
            assert all(count == 0 for count in sleep_counts), (
                f"the waiting request must not hold a DB connection at the "
                f"sleep boundary: {sleep_counts}"
            )
            # No accounting mutation while waiting.
            mid = asyncio.run(
                _side_effect_counts(owned_pg_url, seeded.gateway_key_id)
            )
            assert mid == baseline, (
                f"waiting must not mutate accounting: baseline={baseline} mid={mid}"
            )
        finally:
            first_release.set()
            thread1.join(timeout=30)
            thread2.join(timeout=30)
            assert not thread1.is_alive()
            assert not thread2.is_alive()

    assert [r.status_code for r in responses_out] == [200, 200], [
        (r.status_code, r.text[:300]) for r in responses_out
    ]
    assert len(calls) == 2, "each request must invoke the provider exactly once"
    assert "response" in responses_out[1].text
    final = asyncio.run(_side_effect_counts(owned_pg_url, seeded.gateway_key_id))
    # The holder's in-flight reservation is already in the baseline: the
    # waited request adds exactly ONE reservation, and both completed
    # requests finalize exactly once.
    assert final == (baseline[0] + 1, baseline[1] + 2), (
        f"one normal reservation/finalization per request: "
        f"baseline={baseline} final={final}"
    )
    ledger = asyncio.run(_ledger_rows(owned_pg_url, seeded.gateway_key_id))
    assert len(ledger) == 2, ledger
    assert {row["request_id"] for row in ledger} == set(calls), (
        f"ledger rows must be attributed to the two provider calls: "
        f"{ledger} vs {calls}"
    )
    for row in ledger:
        assert row["total_tokens"] == 11, row
        assert row["actual_cost_eur"] == Decimal("0.000011"), row
    leftovers = asyncio.run(probe_zcard_check(owned_redis_url, seeded.gateway_key_id))
    assert leftovers == 0


# --- V4: admin durable lazy-throttling policy with safe audit -----------------


@pytest.mark.asyncio
async def test_admin_lazy_throttling_policy_durable_and_audited(
    owned_pg_url: str,
    owned_redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-default wait policy is durable, audited, and safely projected.

    Create with an explicit wait policy (stored in key metadata, audit new
    values carry no plaintext key); an ordinary rate-limit update PRESERVES
    the lazy policy (R1); an explicit update flips to reject and removes the
    stored policy; a reject-mode round-trip stores nothing; and malformed
    stored metadata (written directly, bypassing service validation) never
    surfaces as a wait policy.
    """
    _configure_lazy_environment(
        monkeypatch, database_url=owned_pg_url, redis_url=owned_redis_url
    )
    model = f"lazy-audit-{uuid.uuid4().hex[:12]}"
    wait_policy = {"mode": "wait", "max_wait_seconds": 45, "max_waiting_requests": 4}
    seeded = await _seed_chat_key(
        owned_pg_url,
        model=model,
        rate_limit_policy={"max_concurrent_requests": 2, "window_seconds": 60},
        lazy_throttling_policy=dict(wait_policy),
    )
    key_id = seeded.gateway_key_id

    from slaif_gateway.config import Settings
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.schemas.keys import (
        UpdateGatewayKeyLazyThrottlingInput,
        UpdateGatewayKeyRateLimitsInput,
    )
    from slaif_gateway.services.key_service import KeyService

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _service_session() -> object:
        engine = create_async_engine(owned_pg_url, future=True)
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                yield session
        finally:
            await engine.dispose()


    # (1) Creation: the wait policy is durably stored in key metadata and the
    # creation audit carries safe values (no plaintext key, ever).
    row = await _stored_gateway_key_row(owned_pg_url, key_id)
    assert (row.metadata_json or {}).get("lazy_throttling_policy") == wait_policy
    created_audit = next(
        a for a in await _audit_rows_for_key(owned_pg_url, key_id)
        if a.action == "gateway_key_created"
    )
    assert created_audit.new_values["lazy_throttling_policy"] == wait_policy
    created_blob = str(created_audit.new_values)
    assert seeded.plaintext_gateway_key not in created_blob
    assert seeded.plaintext_gateway_key not in str(
        (row.metadata_json or {}).get("lazy_throttling_policy")
    )

    # (2) Ordinary rate-limit update preserves the lazy policy (R1).
    async with _service_session() as session:
            service = KeyService(
                settings=Settings(),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.update_gateway_key_rate_limits(
                UpdateGatewayKeyRateLimitsInput(
                    gateway_key_id=key_id,
                    rate_limit_policy={"max_concurrent_requests": 3, "window_seconds": 30},
                    actor_admin_id=None,
                    reason="focused integration: ordinary rate limit change",
                )
            )
            await session.commit()
    row = await _stored_gateway_key_row(owned_pg_url, key_id)
    assert (row.metadata_json or {}).get("lazy_throttling_policy") == wait_policy
    assert row.max_concurrent_requests == 3

    # (3) Explicit lazy update to reject: policy removed, audit old/new safe.
    async with _service_session() as session:
            service = KeyService(
                settings=Settings(),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.update_gateway_key_lazy_throttling(
                UpdateGatewayKeyLazyThrottlingInput(
                    gateway_key_id=key_id,
                    lazy_throttling_policy={"mode": "reject"},
                    actor_admin_id=None,
                    reason="focused integration: return to immediate rejection",
                )
            )
            await session.commit()
    row = await _stored_gateway_key_row(owned_pg_url, key_id)
    assert "lazy_throttling_policy" not in (row.metadata_json or {})
    lazy_audit = [
        a
        for a in await _audit_rows_for_key(owned_pg_url, key_id)
        if a.action == "update_key_lazy_throttling"
    ]
    assert len(lazy_audit) == 1
    assert lazy_audit[0].old_values["lazy_throttling_policy"] == wait_policy
    assert lazy_audit[0].new_values["lazy_throttling_policy"] is None
    assert lazy_audit[0].note == "focused integration: return to immediate rejection"

    # (4) Reject-mode round-trip: storing reject leaves nothing to project.
    async with _service_session() as session:
            service = KeyService(
                settings=Settings(),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )
            assert service._lazy_throttling_policy_from_key(row) is None
            await service.update_gateway_key_lazy_throttling(
                UpdateGatewayKeyLazyThrottlingInput(
                    gateway_key_id=key_id,
                    lazy_throttling_policy={"mode": "wait",
                                           "max_wait_seconds": 30,
                                           "max_waiting_requests": 2},
                    actor_admin_id=None,
                    reason="focused integration: re-enable defaults",
                )
            )
            await session.commit()
    row = await _stored_gateway_key_row(owned_pg_url, key_id)
    assert (row.metadata_json or {}).get("lazy_throttling_policy") == {
        "mode": "wait",
        "max_wait_seconds": 30,
        "max_waiting_requests": 2,
    }

    # (5) Malformed stored metadata never grants wait: an unknown field
    # written directly (bypassing service validation) parses to None.
    malformed = dict(
        (row.metadata_json or {}).get("lazy_throttling_policy") or {}
    )
    malformed["unexpected_field"] = 1
    bad_metadata = dict(row.metadata_json or {})
    bad_metadata["lazy_throttling_policy"] = malformed
    async with _service_session() as session:
            repo = GatewayKeysRepository(session)
            updated = await repo.update_gateway_key_metadata(
                key_id, metadata_json=bad_metadata
            )
            assert updated
            await session.commit()
    from slaif_gateway.config import get_settings
    from slaif_gateway.schemas.rate_limits import parse_lazy_throttling_policy_metadata

    settings = get_settings()
    row = await _stored_gateway_key_row(owned_pg_url, key_id)
    parsed = parse_lazy_throttling_policy_metadata(
        (row.metadata_json or {}).get("lazy_throttling_policy"),
        max_wait_seconds_ceiling=settings.LAZY_THROTTLING_MAX_WAIT_SECONDS,
        max_waiting_per_key_ceiling=settings.LAZY_THROTTLING_MAX_WAITING_PER_KEY,
    )
    assert parsed is None, "malformed stored policy must never grant waiting"

    async with _service_session() as session:
        service = KeyService(
            settings=Settings(),
            gateway_keys_repository=GatewayKeysRepository(session),
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            audit_repository=AuditRepository(session),
        )
        refreshed = await service._get_gateway_key(key_id)
        assert service._lazy_throttling_policy_from_key(refreshed) is None

    # (6) Injected audit-write failure: the metadata change and the audit
    # write share one transaction, so the whole update rolls back and no
    # audit row remains (same-transaction audit guarantee, R2).
    policy_before_failure = (row.metadata_json or {}).get("lazy_throttling_policy")
    audits_before_failure = len(
        [
            a
            for a in await _audit_rows_for_key(owned_pg_url, key_id)
            if a.action == "update_key_lazy_throttling"
        ]
    )

    async def _raise_audit_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected audit write failure")

    monkeypatch.setattr(AuditRepository, "add_audit_log", _raise_audit_failure)
    async with _service_session() as session:
        service = KeyService(
            settings=Settings(),
            gateway_keys_repository=GatewayKeysRepository(session),
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            audit_repository=AuditRepository(session),
        )
        with pytest.raises(RuntimeError, match="injected audit write failure"):
            await service.update_gateway_key_lazy_throttling(
                UpdateGatewayKeyLazyThrottlingInput(
                    gateway_key_id=key_id,
                    lazy_throttling_policy={"mode": "reject"},
                    actor_admin_id=None,
                    reason="focused integration: audit failure rollback",
                )
            )
    row = await _stored_gateway_key_row(owned_pg_url, key_id)
    assert (row.metadata_json or {}).get("lazy_throttling_policy") == policy_before_failure
    lazy_audit_after_failure = [
        a
        for a in await _audit_rows_for_key(owned_pg_url, key_id)
        if a.action == "update_key_lazy_throttling"
    ]
    assert len(lazy_audit_after_failure) == audits_before_failure

