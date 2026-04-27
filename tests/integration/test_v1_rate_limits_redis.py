from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from contextlib import closing
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import RedisError

from slaif_gateway.schemas.rate_limits import RateLimitPolicy
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    FAKE_OPENAI_UPSTREAM_KEY,
    PROMPT_TEXT,
    TEST_MODEL,
    _configure_runtime_environment,
    _create_test_data,
    _load_accounting_state,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_redis(redis_url: str) -> None:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        for _ in range(50):
            try:
                await client.ping()
                await client.flushdb()
                return
            except RedisError:
                await asyncio.sleep(0.1)
        pytest.skip("Redis did not become ready")
    finally:
        await client.aclose()


async def _redis_keys(redis_url: str) -> list[str]:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        return list(await client.keys("rate:*"))
    finally:
        await client.aclose()


@pytest.fixture
def redis_test_url(tmp_path) -> Iterator[str]:
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

    asyncio.run(_wait_for_redis(redis_url))
    try:
        yield redis_url
    finally:
        asyncio.run(_flush_redis(redis_url))
        if process is not None:
            process.terminate()
            process.wait(timeout=5)


async def _flush_redis(redis_url: str) -> None:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        await client.flushdb()
    finally:
        await client.aclose()


def _configure_rate_limit_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_url: str,
    redis_url: str,
    requests_per_minute: int | None = None,
    tokens_per_minute: int | None = None,
    concurrent_requests: int | None = None,
) -> None:
    _configure_runtime_environment(monkeypatch, database_url)
    monkeypatch.setenv("ENABLE_REDIS_RATE_LIMITS", "true")
    monkeypatch.setenv("REDIS_URL", redis_url)
    if requests_per_minute is not None:
        monkeypatch.setenv("DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE", str(requests_per_minute))
    if tokens_per_minute is not None:
        monkeypatch.setenv("DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE", str(tokens_per_minute))
    if concurrent_requests is not None:
        monkeypatch.setenv("DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS", str(concurrent_requests))

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()


def _chat_body(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": PROMPT_TEXT}],
        "max_tokens": 20,
    }
    body.update(overrides)
    return body


def _upstream_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-rate-limit-integration",
            "object": "chat.completion",
            "model": TEST_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": COMPLETION_TEXT},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
        },
        headers={"x-request-id": "upstream-rate-limit-integration"},
    )


def _streaming_sse() -> str:
    return (
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[{{"index":0,"delta":{{"content":"{COMPLETION_TEXT}"}},'
        '"finish_reason":"stop"}]}\n\n'
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[],"usage":'
        '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
        "data: [DONE]\n\n"
    )


def test_v1_chat_request_rate_limit_rejects_before_provider(
    migrated_postgres_url: str,
    redis_test_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_rate_limit_environment(
        monkeypatch,
        database_url=migrated_postgres_url,
        redis_url=redis_test_url,
        requests_per_minute=1,
    )
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=_upstream_response()
        )
        with TestClient(app) as client:
            first = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )
            second = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "request_rate_limit_exceeded"
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"


def test_v1_chat_token_rate_limit_rejects_before_quota_and_provider(
    migrated_postgres_url: str,
    redis_test_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_rate_limit_environment(
        monkeypatch,
        database_url=migrated_postgres_url,
        redis_url=redis_test_url,
        tokens_per_minute=1,
    )
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=_upstream_response()
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "token_rate_limit_exceeded"
    assert len(upstream_route.calls) == 0


def test_v1_chat_concurrency_released_after_success(
    migrated_postgres_url: str,
    redis_test_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_rate_limit_environment(
        monkeypatch,
        database_url=migrated_postgres_url,
        redis_url=redis_test_url,
        concurrent_requests=1,
    )
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=_upstream_response()
        )
        with TestClient(app) as client:
            first = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )
            second = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(upstream_route.calls) == 2
    state = asyncio.run(_load_accounting_state(migrated_postgres_url, created.gateway_key_id))
    assert state.gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_reserved_total == 0
    assert state.gateway_key.requests_used_total == 2

    redis_keys = " ".join(asyncio.run(_redis_keys(redis_test_url)))
    assert created.plaintext_gateway_key not in redis_keys
    assert "@" not in redis_keys


def test_v1_chat_concurrency_limit_rejects_active_slot(
    migrated_postgres_url: str,
    redis_test_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_rate_limit_environment(
        monkeypatch,
        database_url=migrated_postgres_url,
        redis_url=redis_test_url,
        concurrent_requests=1,
    )
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    async def _reserve_active_slot() -> None:
        client = Redis.from_url(redis_test_url, decode_responses=True)
        try:
            service = RedisRateLimitService(client)
            await service.check_and_reserve(
                gateway_key_id=created.gateway_key_id,
                request_id="already-active",
                estimated_tokens=1,
                policy=RateLimitPolicy(concurrent_requests=1),
            )
        finally:
            await client.aclose()

    asyncio.run(_reserve_active_slot())

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=_upstream_response()
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "concurrency_rate_limit_exceeded"
    assert len(upstream_route.calls) == 0


def test_v1_streaming_concurrency_released_after_success(
    migrated_postgres_url: str,
    redis_test_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_rate_limit_environment(
        monkeypatch,
        database_url=migrated_postgres_url,
        redis_url=redis_test_url,
        concurrent_requests=1,
    )
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, content=_streaming_sse().encode())
        )
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json=_chat_body(stream=True),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            ) as first:
                first_body = "".join(first.iter_text())
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json=_chat_body(stream=True),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            ) as second:
                second_body = "".join(second.iter_text())

    assert first.status_code == 200
    assert second.status_code == 200
    assert "data: [DONE]" in first_body
    assert "data: [DONE]" in second_body
    assert len(upstream_route.calls) == 2
    state = asyncio.run(_load_accounting_state(migrated_postgres_url, created.gateway_key_id))
    assert state.gateway_key.requests_used_total == 2
    assert state.gateway_key.cost_reserved_eur == Decimal("0E-9")

    redis_keys = " ".join(asyncio.run(_redis_keys(redis_test_url)))
    assert created.plaintext_gateway_key not in redis_keys
    assert PROMPT_TEXT not in redis_keys
    assert COMPLETION_TEXT not in redis_keys
    assert json.dumps(state.usage_ledger.usage_raw, sort_keys=True).find(PROMPT_TEXT) == -1
