"""ASGI app entrypoint for the SLAIF API Gateway."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from slaif_gateway.api.errors import (
    OpenAICompatibleError,
    http_exception_handler,
    openai_compatible_error_handler,
    request_validation_exception_handler,
)
from slaif_gateway.api.health import router as health_router
from slaif_gateway.api.metrics import router as metrics_router
from slaif_gateway.api.middleware import MetricsMiddleware, RequestIdMiddleware
from slaif_gateway.api.openai_compat import router as openai_compat_router
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db import session as db_session_module
from slaif_gateway.logging import configure_logging


def _build_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db_engine = None
        app.state.db_sessionmaker = None

        if settings.DATABASE_URL:
            engine = db_session_module.create_engine_from_settings(settings)
            app.state.db_engine = engine
            app.state.db_sessionmaker = db_session_module.create_sessionmaker_from_engine(engine)

        try:
            yield
        finally:
            engine = getattr(app.state, "db_engine", None)
            if engine is not None:
                await engine.dispose()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_settings = settings or get_settings()
    configure_logging(app_settings)
    app = FastAPI(title="SLAIF API Gateway", lifespan=_build_lifespan(app_settings))
    app.state.settings = app_settings
    app.state.db_engine = None
    app.state.db_sessionmaker = None

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware, settings=app_settings)

    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(openai_compat_router)

    return app


app = create_app()
