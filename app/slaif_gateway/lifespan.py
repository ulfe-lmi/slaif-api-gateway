"""FastAPI lifespan wiring for external clients."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from slaif_gateway.cache import redis as redis_module
from slaif_gateway.config import Settings
from slaif_gateway.db import session as db_session_module


def build_lifespan(settings: Settings):
    """Build the application lifespan context manager."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db_engine = None
        app.state.db_sessionmaker = None
        app.state.redis_client = None

        if settings.DATABASE_URL:
            engine = db_session_module.create_engine_from_settings(settings)
            app.state.db_engine = engine
            app.state.db_sessionmaker = db_session_module.create_sessionmaker_from_engine(engine)

        if settings.ENABLE_REDIS_RATE_LIMITS:
            app.state.redis_client = redis_module.create_redis_client_from_settings(settings)

        try:
            yield
        finally:
            redis_client = getattr(app.state, "redis_client", None)
            if redis_client is not None:
                await redis_module.close_redis_client(redis_client)

            engine = getattr(app.state, "db_engine", None)
            if engine is not None:
                await engine.dispose()

    return lifespan
