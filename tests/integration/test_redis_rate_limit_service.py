from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from redis.exceptions import RedisError

from slaif_gateway.schemas.rate_limits import RateLimitPolicy
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)
from slaif_gateway.services.rate_limit_service import RedisRateLimitService


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest_asyncio.fixture
async def redis_client(tmp_path) -> AsyncIterator[Redis]:
    redis_url = os.getenv("TEST_REDIS_URL")
    process: subprocess.Popen[bytes] | None = None
    if not redis_url:
        redis_server = shutil.which("redis-server")
        if redis_server is None:
            pytest.skip("TEST_REDIS_URL is not set and redis-server is not available")
        port = _free_port()
        redis_url = f"redis://127.0.0.1:{port}/0"
        process = subprocess.Popen(
            [
                redis_server,
                "--save",
                "",
                "--appendonly",
                "no",
                "--port",
                str(port),
                "--dir",
                str(tmp_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    client = Redis.from_url(redis_url, decode_responses=True)
    for _ in range(50):
        try:
            await client.ping()
            break
        except RedisError:
            await asyncio.sleep(0.1)
    else:
        if process is not None:
            process.terminate()
        pytest.skip("Redis did not become ready")

    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()
        if process is not None:
            process.terminate()
            process.wait(timeout=5)


@pytest.mark.asyncio
async def test_redis_rate_limit_service_with_real_redis(redis_client: Redis) -> None:
    service = RedisRateLimitService(redis_client)
    key_id = uuid.uuid4()

    async def reserve_request(index: int):
        try:
            await service.check_and_reserve(
                gateway_key_id=key_id,
                request_id=f"req-{index}",
                estimated_tokens=1,
                policy=RateLimitPolicy(requests_per_minute=5),
            )
            return "allowed"
        except RequestRateLimitExceededError:
            return "limited"

    request_results = await asyncio.gather(*(reserve_request(index) for index in range(10)))
    assert request_results.count("allowed") == 5
    assert request_results.count("limited") == 5

    token_key_id = uuid.uuid4()

    async def reserve_tokens(index: int):
        try:
            await service.check_and_reserve(
                gateway_key_id=token_key_id,
                request_id=f"tok-{index}",
                estimated_tokens=10,
                policy=RateLimitPolicy(tokens_per_minute=50),
            )
            return "allowed"
        except TokenRateLimitExceededError:
            return "limited"

    token_results = await asyncio.gather(*(reserve_tokens(index) for index in range(10)))
    assert token_results.count("allowed") == 5
    assert token_results.count("limited") == 5

    concurrency_key_id = uuid.uuid4()

    async def reserve_concurrency(index: int):
        try:
            await service.check_and_reserve(
                gateway_key_id=concurrency_key_id,
                request_id=f"conc-{index}",
                estimated_tokens=1,
                policy=RateLimitPolicy(concurrent_requests=3),
            )
            return f"conc-{index}"
        except ConcurrencyRateLimitExceededError:
            return "limited"

    concurrency_results = await asyncio.gather(*(reserve_concurrency(index) for index in range(10)))
    active_request_ids = [item for item in concurrency_results if item != "limited"]
    assert len(active_request_ids) == 3
    assert concurrency_results.count("limited") == 7

    await service.release_concurrency(
        gateway_key_id=concurrency_key_id,
        request_id=active_request_ids[0],
    )
    released_result = await service.check_and_reserve(
        gateway_key_id=concurrency_key_id,
        request_id="conc-after-release",
        estimated_tokens=1,
        policy=RateLimitPolicy(concurrent_requests=3),
    )
    assert released_result.allowed is True

    ttl_key_id = uuid.uuid4()
    await service.check_and_reserve(
        gateway_key_id=ttl_key_id,
        request_id="ttl-1",
        estimated_tokens=1,
        policy=RateLimitPolicy(requests_per_minute=1, window_seconds=1),
    )
    with pytest.raises(RequestRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=ttl_key_id,
            request_id="ttl-2",
            estimated_tokens=1,
            policy=RateLimitPolicy(requests_per_minute=1, window_seconds=1),
        )
    await asyncio.sleep(1.2)
    ttl_result = await service.check_and_reserve(
        gateway_key_id=ttl_key_id,
        request_id="ttl-3",
        estimated_tokens=1,
        policy=RateLimitPolicy(requests_per_minute=1, window_seconds=1),
    )
    assert ttl_result.allowed is True

    redis_keys = " ".join(await redis_client.keys("rate:*"))
    assert "sk-slaif-" not in redis_keys
    assert "student@example.com" not in redis_keys


@pytest.mark.asyncio
async def test_real_redis_active_concurrency_uses_separate_ttl(redis_client: Redis) -> None:
    service = RedisRateLimitService(redis_client)
    key_id = uuid.uuid4()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        window_seconds=1,
        concurrency_ttl_seconds=10,
        concurrency_heartbeat_seconds=2,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="active-a",
        estimated_tokens=1,
        policy=policy,
    )
    await asyncio.sleep(1.2)
    with pytest.raises(ConcurrencyRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="active-b",
            estimated_tokens=1,
            policy=policy,
        )

    await service.heartbeat_concurrency(
        gateway_key_id=key_id,
        request_id="active-a",
        policy=policy,
    )
    await asyncio.sleep(1.2)
    with pytest.raises(ConcurrencyRateLimitExceededError):
        await service.check_and_reserve(
            gateway_key_id=key_id,
            request_id="active-b",
            estimated_tokens=1,
            policy=policy,
        )

    await service.release_concurrency(gateway_key_id=key_id, request_id="active-a")
    result = await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="active-b",
        estimated_tokens=1,
        policy=policy,
    )
    assert result.allowed is True


@pytest.mark.asyncio
async def test_real_redis_expired_concurrency_slot_is_cleaned(redis_client: Redis) -> None:
    service = RedisRateLimitService(redis_client)
    key_id = uuid.uuid4()
    policy = RateLimitPolicy(
        concurrent_requests=1,
        concurrency_ttl_seconds=2,
        concurrency_heartbeat_seconds=1,
    )

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="stale-a",
        estimated_tokens=1,
        policy=policy,
    )
    await asyncio.sleep(2.2)
    result = await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="fresh-b",
        estimated_tokens=1,
        policy=policy,
    )
    assert result.allowed is True


@pytest.mark.asyncio
async def test_real_redis_release_is_idempotent(redis_client: Redis) -> None:
    service = RedisRateLimitService(redis_client)
    key_id = uuid.uuid4()
    policy = RateLimitPolicy(concurrent_requests=1)

    await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="release-a",
        estimated_tokens=1,
        policy=policy,
    )
    await service.release_concurrency(gateway_key_id=key_id, request_id="release-a")
    await service.release_concurrency(gateway_key_id=key_id, request_id="release-a")

    result = await service.check_and_reserve(
        gateway_key_id=key_id,
        request_id="release-b",
        estimated_tokens=1,
        policy=policy,
    )
    assert result.allowed is True
