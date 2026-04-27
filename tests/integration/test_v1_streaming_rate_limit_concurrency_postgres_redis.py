from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.schemas.providers import ProviderResponse, ProviderStreamChunk, ProviderUsage
from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
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


async def _flush_redis(redis_url: str) -> None:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        await client.flushdb()
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


def _configure_rate_limit_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_url: str,
    redis_url: str,
) -> None:
    _configure_runtime_environment(monkeypatch, database_url)
    monkeypatch.setenv("ENABLE_REDIS_RATE_LIMITS", "true")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_TTL_SECONDS", "4")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS", "1")

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()


def _chat_body(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": PROMPT_TEXT}],
        "max_tokens": 20,
        "stream": True,
    }
    body.update(overrides)
    return body


async def _set_key_rate_limit_window(database_url: str, gateway_key_id, window_seconds: int) -> None:
    engine = create_async_engine(database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            assert gateway_key is not None
            metadata = dict(gateway_key.metadata_json or {})
            metadata["rate_limit_policy"] = {"window_seconds": window_seconds}
            gateway_key.metadata_json = metadata
            await session.commit()
    finally:
        await engine.dispose()


def test_streaming_concurrency_tracks_active_stream_beyond_window(
    migrated_postgres_url: str,
    redis_test_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_rate_limit_environment(
        monkeypatch,
        database_url=migrated_postgres_url,
        redis_url=redis_test_url,
    )
    created = asyncio.run(_create_test_data(migrated_postgres_url))
    asyncio.run(_set_key_rate_limit_window(migrated_postgres_url, created.gateway_key_id, 1))

    stream_started = threading.Event()
    finish_stream = threading.Event()

    class _SlowStreamingAdapter:
        async def forward_chat_completion(self, request):
            _ = request
            return ProviderResponse(
                provider="openai",
                upstream_model=TEST_MODEL,
                status_code=200,
                json_body={
                    "id": "chatcmpl-after-stream",
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
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )

        async def stream_chat_completion(self, request):
            _ = request
            stream_started.set()
            yield ProviderStreamChunk(
                provider="openai",
                upstream_model=TEST_MODEL,
                data='{"id":"chunk","choices":[{"delta":{"content":"hi"}}]}',
                raw_sse_event='data: {"id":"chunk","choices":[{"delta":{"content":"hi"}}]}\n\n',
            )
            while not finish_stream.is_set():
                await asyncio.sleep(0.05)
            yield ProviderStreamChunk(
                provider="openai",
                upstream_model=TEST_MODEL,
                data=(
                    '{"id":"usage","choices":[],"usage":'
                    '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}'
                ),
                raw_sse_event=(
                    'data: {"id":"usage","choices":[],"usage":'
                    '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
                ),
                json_body={
                    "id": "usage",
                    "choices": [],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )
            yield ProviderStreamChunk(
                provider="openai",
                upstream_model=TEST_MODEL,
                data="[DONE]",
                raw_sse_event="data: [DONE]\n\n",
                is_done=True,
            )

    import slaif_gateway.services.chat_completion_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda route, settings: _SlowStreamingAdapter())

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    first_body: list[str] = []
    first_status: list[int] = []

    with TestClient(app) as client:

        def _consume_first_stream() -> None:
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            ) as response:
                first_status.append(response.status_code)
                first_body.extend(response.iter_text())

        thread = threading.Thread(target=_consume_first_stream)
        thread.start()
        assert stream_started.wait(timeout=5)
        time.sleep(1.4)

        second = client.post(
            "/v1/chat/completions",
            json=_chat_body(stream=False),
            headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
        )
        finish_stream.set()
        thread.join(timeout=10)
        assert not thread.is_alive()

        third = client.post(
            "/v1/chat/completions",
            json=_chat_body(stream=False),
            headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
        )

    assert first_status == [200]
    assert "data: [DONE]" in "".join(first_body)
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "concurrency_rate_limit_exceeded"
    assert third.status_code == 200

    state = asyncio.run(_load_accounting_state(migrated_postgres_url, created.gateway_key_id))
    assert state.gateway_key.requests_used_total == 2
    usage_payload = str(state.usage_ledger.usage_raw)
    metadata_payload = str(state.usage_ledger.response_metadata)
    assert PROMPT_TEXT not in usage_payload
    assert COMPLETION_TEXT not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert COMPLETION_TEXT not in metadata_payload
