"""Redis client helpers for optional temporary operational state."""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from starlette.requests import Request

from slaif_gateway.config import Settings


def create_redis_client_from_settings(settings: Settings) -> Redis:
    """Create a Redis client from explicit settings."""
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is not configured.")

    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )


def get_redis_client_from_app(request: Request) -> Any:
    """Return the FastAPI lifespan-managed Redis client."""
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        raise RuntimeError("Redis client is not available on application state.")
    return redis_client


async def close_redis_client(redis_client: Any) -> None:
    """Close a Redis client created during application lifespan."""
    close = getattr(redis_client, "aclose", None)
    if close is not None:
        await close()
        return

    legacy_close = getattr(redis_client, "close", None)
    if legacy_close is not None:
        maybe_awaitable = legacy_close()
        if hasattr(maybe_awaitable, "__await__"):
            await maybe_awaitable
