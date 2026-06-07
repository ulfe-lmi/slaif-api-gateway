from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from redis.exceptions import RedisError

from slaif_gateway.schemas.rate_limits import RateLimitPolicy
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    InvalidRateLimitPolicyError,
    RateLimitReleaseError,
    RedisRateLimitUnavailableError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)
from slaif_gateway.services.rate_limit_service import RedisRateLimitService


class _FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.values: dict[str, int] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.eval_calls: list[tuple[object, ...]] = []
        self.zrem_calls: list[tuple[str, str]] = []

    async def eval(self, script, numkeys, *values):
        if self.fail:
            raise RedisError("redis unavailable")
        self.eval_calls.append((script, numkeys, *values))
        keys = values[:numkeys]
        args = values[numkeys:]
        if numkeys == 1:
            concurrency_key = keys[0]
            if len(args) == 2:
                now_ms = int(args[0])
                zset = self.zsets.setdefault(str(concurrency_key), {})
                removed = 0
                for member, score in list(zset.items()):
                    if score <= now_ms:
                        removed += 1
                        del zset[member]
                return removed
            now_ms = int(args[0])
            request_id = str(args[1])
            ttl_seconds = int(args[2])
            zset = self.zsets.setdefault(str(concurrency_key), {})
            for member, score in list(zset.items()):
                if score <= now_ms:
                    del zset[member]
            if request_id not in zset:
                return [0, "missing", 0]
            expires = now_ms + (ttl_seconds * 1000)
            zset[request_id] = expires
            return [1, "refreshed", expires]
        request_key, token_key, concurrency_key = keys
        now_ms = int(args[0])
        window_seconds = int(args[1])
        request_limit = int(args[2])
        token_limit = int(args[3])
        concurrency_limit = int(args[4])
        estimated_tokens = int(args[5])
        request_id = str(args[6])
        concurrency_ttl_seconds = int(args[7])
        reset_ms = now_ms + (window_seconds * 1000)
        slot_expires_ms = now_ms + (concurrency_ttl_seconds * 1000)

        zset = self.zsets.setdefault(str(concurrency_key), {})
        for member, score in list(zset.items()):
            if score <= now_ms:
                del zset[member]

        if concurrency_limit > 0 and request_id not in zset and len(zset) >= concurrency_limit:
            earliest_expiry = min(zset.values())
            retry_after = max(((earliest_expiry - now_ms) + 999) // 1000, 1)
            return [0, "concurrency", 0, 0, len(zset), earliest_expiry, retry_after, 0]

        current_requests = self.values.get(str(request_key), 0)
        if request_limit > 0 and current_requests + 1 > request_limit:
            return [
                0,
                "requests",
                max(request_limit - current_requests, 0),
                0,
                0,
                reset_ms,
                window_seconds,
                0,
            ]

        current_tokens = self.values.get(str(token_key), 0)
        if token_limit > 0 and current_tokens + estimated_tokens > token_limit:
            return [
                0,
                "tokens",
                0,
                max(token_limit - current_tokens, 0),
                0,
                reset_ms,
                window_seconds,
                0,
            ]

        if request_limit > 0:
            current_requests += 1
            self.values[str(request_key)] = current_requests
        if token_limit > 0:
            current_tokens += estimated_tokens
            self.values[str(token_key)] = current_tokens
        if concurrency_limit > 0:
            zset[request_id] = slot_expires_ms

        return [
            1,
            "allowed",
            max(request_limit - current_requests, 0) if request_limit > 0 else 0,
            max(token_limit - current_tokens, 0) if token_limit > 0 else 0,
            len(zset) if concurrency_limit > 0 else 0,
            reset_ms,
            0,
            slot_expires_ms if concurrency_limit > 0 else 0,
        ]

    async def zrem(self, key, member):
        if self.fail:
            raise RedisError("redis unavailable")
        self.zrem_calls.append((str(key), str(member)))
        self.zsets.setdefault(str(key), {}).pop(str(member), None)
        return 1

    async def zremrangebyscore(self, key, _min, max_score):
        zset = self.zsets.setdefault(str(key), {})
        removed = 0
        for member, score in list(zset.items()):
            if score <= int(max_score):
                removed += 1
                del zset[member]
        return removed


def _key_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.mark.asyncio
async def test_no_policy_allows_without_redis_write() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)

    result = await service.check_and_reserve(
        gateway_key_id=_key_id(),
        request_id="req-1",
        estimated_tokens=10,
        policy=RateLimitPolicy(),
    )

    assert result.allowed is True
    assert redis.eval_calls == []


@pytest.mark.asyncio
async def test_allows_requests_under_limit_with_one_atomic_eval() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)

    result = await service.check_and_reserve(
        gateway_key_id=_key_id(),
        request_id="req-1",
        estimated_tokens=10,
        policy=RateLimitPolicy(requests_per_minute=2),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.allowed is True
    assert result.remaining_requests == 1
    assert len(redis.eval_calls) == 1


@pytest.mark.asyncio
async def test_rejects_over_request_limit() -> None:
    service = RedisRateLimitService(_FakeRedis())
    policy = RateLimitPolicy(requests_per_minute=1)
    key_id = _key_id()

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-1",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(RequestRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="req-2",
            estimated_tokens=1,
            policy=policy,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_rejects_over_token_limit() -> None:
    service = RedisRateLimitService(_FakeRedis())

    with pytest.raises(TokenRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=_key_id(),
            request_id="req-1",
            estimated_tokens=11,
            policy=RateLimitPolicy(tokens_per_minute=10),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_rejects_and_releases_concurrency_limit() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)
    key_id = _key_id()
    policy = RateLimitPolicy(concurrent_requests=1)

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-1",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ConcurrencyRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="req-2",
            estimated_tokens=1,
            policy=policy,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

    await service.release_concurrency(gateway_key_id=key_id, request_id="req-1")
    await service.release_concurrency(gateway_key_id=key_id, request_id="req-1")

    result = await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-2",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.allowed is True
    assert len(redis.zrem_calls) == 2


@pytest.mark.asyncio
async def test_concurrency_slot_uses_active_ttl_not_request_window() -> None:
    service = RedisRateLimitService(_FakeRedis())
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        window_seconds=1,
        concurrency_ttl_seconds=10,
        concurrency_heartbeat_seconds=2,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-active",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ConcurrencyRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="req-blocked",
            estimated_tokens=1,
            policy=policy,
            now=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_heartbeat_refreshes_existing_concurrency_slot() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        window_seconds=1,
        concurrency_ttl_seconds=5,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-heartbeat",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = await service.heartbeat_concurrency(
        gateway_key_id=key_id,
        request_id="req-heartbeat",
        policy=policy,
        now=datetime(2026, 1, 1, 0, 0, 4, tzinfo=UTC),
    )

    assert result.concurrency_slot_expires_at == datetime(2026, 1, 1, 0, 0, 9, tzinfo=UTC)
    with pytest.raises(ConcurrencyRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="req-blocked",
            estimated_tokens=1,
            policy=policy,
            now=datetime(2026, 1, 1, 0, 0, 6, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_expired_concurrency_slot_is_cleaned_after_ttl() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=2,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-stale",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-fresh",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
    )

    assert result.allowed is True
    concurrency_key = RedisRateLimitService._concurrency_key(key_id)
    assert "req-stale" not in redis.zsets[concurrency_key]
    assert "req-fresh" in redis.zsets[concurrency_key]


@pytest.mark.asyncio
async def test_real_time_concurrency_operations_request_redis_server_time() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=5,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-server-time",
        estimated_tokens=1,
        policy=policy,
    )
    await service.heartbeat_concurrency(
        gateway_key_id=key_id,
        request_id="req-server-time",
        policy=policy,
    )
    await service.cleanup_expired_concurrency(gateway_key_id=key_id)

    assert redis.eval_calls[0][-1] == 1
    assert redis.eval_calls[1][-1] == 1
    assert redis.eval_calls[2][-1] == 1


@pytest.mark.asyncio
async def test_injected_time_keeps_concurrency_operations_deterministic() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=5,
        concurrency_heartbeat_seconds=1,
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-injected-time",
        estimated_tokens=1,
        policy=policy,
        now=now,
    )
    await service.heartbeat_concurrency(
        gateway_key_id=key_id,
        request_id="req-injected-time",
        policy=policy,
        now=now,
    )
    await service.cleanup_expired_concurrency(gateway_key_id=key_id, now=now)

    assert redis.eval_calls[0][-1] == 0
    assert redis.eval_calls[1][-1] == 0
    assert redis.eval_calls[2][-1] == 0


@pytest.mark.asyncio
async def test_cleanup_removes_expired_concurrency_before_cardinality_check() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=2,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-stale",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-fresh",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )

    assert result.allowed is True
    assert result.concurrent_in_use == 1


@pytest.mark.asyncio
async def test_concurrency_limit_retry_after_and_reset_are_bounded() -> None:
    service = RedisRateLimitService(_FakeRedis())
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=5,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-active",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ConcurrencyRateLimitExceededError) as exc_info:
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="req-blocked",
            estimated_tokens=1,
            policy=policy,
            now=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        )

    assert 1 <= (exc_info.value.retry_after_seconds or 0) <= 2


@pytest.mark.asyncio
async def test_heartbeat_missing_slot_raises_release_error() -> None:
    service = RedisRateLimitService(_FakeRedis())

    with pytest.raises(RateLimitReleaseError):
        await service.heartbeat_concurrency(
            gateway_key_id=_key_id(),
            request_id="missing",
            policy=RateLimitPolicy(
                concurrent_requests=1,
                concurrency_ttl_seconds=5,
                concurrency_heartbeat_seconds=1,
            ),
        )


@pytest.mark.asyncio
async def test_heartbeat_does_not_resurrect_expired_concurrency_slot() -> None:
    service = RedisRateLimitService(_FakeRedis())
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=2,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-expiring",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(RateLimitReleaseError):
        await service.heartbeat_concurrency(
            gateway_key_id=key_id,
            request_id="req-expiring",
            policy=policy,
            now=datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_cleanup_expired_concurrency_uses_same_expiry_semantics() -> None:
    service = RedisRateLimitService(_FakeRedis())
    key_id = _key_id()
    policy = RateLimitPolicy(
        concurrent_requests=2,
        concurrency_ttl_seconds=2,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-expired",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="req-live",
        estimated_tokens=1,
        policy=policy,
        now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
    )

    removed = await service.cleanup_expired_concurrency(
        gateway_key_id=key_id,
        now=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )

    assert removed == 1


@pytest.mark.asyncio
async def test_redis_unavailable_fails_closed_or_open() -> None:
    fail_closed = RedisRateLimitService(_FakeRedis(fail=True), fail_closed=True)
    with pytest.raises(RedisRateLimitUnavailableError):
        await fail_closed.check_and_reserve(
            gateway_key_id=_key_id(),
            request_id="req",
            estimated_tokens=1,
            policy=RateLimitPolicy(requests_per_minute=1),
        )

    fail_open = RedisRateLimitService(_FakeRedis(fail=True), fail_closed=False)
    result = await fail_open.check_and_reserve(
        gateway_key_id=_key_id(),
        request_id="req",
        estimated_tokens=1,
        policy=RateLimitPolicy(requests_per_minute=1),
    )
    assert result.allowed is True
    assert result.degraded is True


@pytest.mark.asyncio
async def test_invalid_estimated_tokens_fail() -> None:
    service = RedisRateLimitService(_FakeRedis())

    with pytest.raises(InvalidRateLimitPolicyError):
        await service.check_and_reserve(
            gateway_key_id=_key_id(),
            request_id="req",
            estimated_tokens=-1,
            policy=RateLimitPolicy(requests_per_minute=1),
        )


def test_invalid_policy_values_fail() -> None:
    with pytest.raises(ValidationError):
        RateLimitPolicy(requests_per_minute=0)


@pytest.mark.asyncio
async def test_redis_keys_do_not_include_plaintext_gateway_key_or_email() -> None:
    redis = _FakeRedis()
    service = RedisRateLimitService(redis)

    await service.check_and_reserve(
        gateway_key_id=_key_id(),
        request_id="req-safe",
        estimated_tokens=5,
        policy=RateLimitPolicy(requests_per_minute=1, tokens_per_minute=10, concurrent_requests=1),
    )

    recorded = " ".join(str(item) for call in redis.eval_calls for item in call)
    assert "sk-slaif-" not in recorded
    assert "student@example.com" not in recorded
    assert str(_key_id()) in recorded
