from __future__ import annotations

import asyncio
import json
import threading

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.schemas.providers import ProviderStreamChunk
from slaif_gateway.schemas.rate_limits import RateLimitResult
from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    FAKE_OPENAI_UPSTREAM_KEY,
    PROMPT_TEXT,
    _configure_runtime_environment,
    _create_test_data,
    _free_port,
    _load_accounting_state,
    _run_uvicorn_server,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head


async def _enable_concurrency_rate_limit(database_url: str, gateway_key_id) -> None:
    from slaif_gateway.db.models import GatewayKey

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            assert gateway_key is not None
            gateway_key.max_concurrent_requests = 1
            metadata = dict(gateway_key.metadata_json or {})
            metadata["rate_limit_policy"] = {"max_concurrent_requests": 1}
            gateway_key.metadata_json = metadata
            await session.commit()
    finally:
        await engine.dispose()


def test_streaming_client_disconnect_releases_reservation_and_redis_slot(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    monkeypatch.setenv("ENABLE_REDIS_RATE_LIMITS", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    created = asyncio.run(_create_test_data(migrated_postgres_url))
    asyncio.run(_enable_concurrency_rate_limit(migrated_postgres_url, created.gateway_key_id))

    stream_started = threading.Event()
    adapter_closed = threading.Event()
    redis_released = threading.Event()
    rate_state: dict[str, list[tuple[object, str]]] = {
        "reserve_calls": [],
        "release_calls": [],
    }

    class _FakeRedis:
        async def aclose(self) -> None:
            return None

    class _FakeRedisRateLimitService:
        def __init__(self, redis_client, *, fail_closed=True):
            _ = (redis_client, fail_closed)

        async def check_and_reserve(self, *, gateway_key_id, request_id, estimated_tokens, policy):
            _ = (estimated_tokens, policy)
            rate_state["reserve_calls"].append((gateway_key_id, request_id))
            return RateLimitResult(allowed=True)

        async def release_concurrency(self, *, gateway_key_id, request_id):
            rate_state["release_calls"].append((gateway_key_id, request_id))
            redis_released.set()

        async def heartbeat_concurrency(self, *, gateway_key_id, request_id, policy):
            _ = (gateway_key_id, request_id, policy)
            return RateLimitResult(allowed=True)

    class _SlowStreamingAdapter:
        async def stream_chat_completion(self, request):
            _ = request
            stream_started.set()
            try:
                yield ProviderStreamChunk(
                    provider="openai",
                    upstream_model="gpt-test-mini",
                    data='{"id":"chunk","choices":[{"delta":{"content":"partial"}}]}',
                    raw_sse_event='data: {"id":"chunk","choices":[{"delta":{"content":"partial"}}]}\n\n',
                )
                while True:
                    await asyncio.sleep(0.05)
            finally:
                adapter_closed.set()

    from slaif_gateway.cache import redis as redis_module
    import slaif_gateway.services.chat_completion_gateway as gateway_module
    from slaif_gateway.main import create_app

    monkeypatch.setattr(redis_module, "create_redis_client_from_settings", lambda settings: _FakeRedis())
    monkeypatch.setattr(gateway_module, "RedisRateLimitService", _FakeRedisRateLimitService)
    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda route, settings: _SlowStreamingAdapter())

    app = create_app(get_settings())
    port = _free_port()
    first_chunk = ""

    with _run_uvicorn_server(app, port):
        with httpx.Client(timeout=httpx.Timeout(10.0, read=10.0)) as client:
            with client.stream(
                "POST",
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json={
                    "model": "gpt-test-mini",
                    "messages": [{"role": "user", "content": PROMPT_TEXT}],
                    "stream": True,
                },
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            ) as response:
                assert response.status_code == 200
                assert stream_started.wait(timeout=5)
                for text in response.iter_text():
                    first_chunk += text
                    if "partial" in first_chunk:
                        break

        assert adapter_closed.wait(timeout=5)
        assert redis_released.wait(timeout=5)

    assert "partial" in first_chunk
    assert "data: [DONE]" not in first_chunk
    assert rate_state["reserve_calls"]
    assert rate_state["release_calls"] == [
        (created.gateway_key_id, rate_state["reserve_calls"][0][1])
    ]

    state = asyncio.run(_load_accounting_state(migrated_postgres_url, created.gateway_key_id))
    assert state.reservation.status == "released"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_reserved_total == 0
    assert state.gateway_key.tokens_used_total == 0
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.accounting_status == "failed"
    assert state.usage_ledger.error_type == "client_disconnected"

    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    assert PROMPT_TEXT not in usage_payload
    assert COMPLETION_TEXT not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert COMPLETION_TEXT not in metadata_payload
    assert created.plaintext_gateway_key not in metadata_payload
    assert FAKE_OPENAI_UPSTREAM_KEY not in metadata_payload
