"""ASGI app entrypoint for the SLAIF API Gateway."""

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
from slaif_gateway.lifespan import build_lifespan
from slaif_gateway.logging import configure_logging
from slaif_gateway.startup_warnings import emit_startup_configuration_warnings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_settings = settings or get_settings()
    configure_logging(app_settings)
    emit_startup_configuration_warnings(app_settings)
    app = FastAPI(title="SLAIF API Gateway", lifespan=build_lifespan(app_settings))
    app.state.settings = app_settings
    app.state.db_engine = None
    app.state.db_sessionmaker = None
    app.state.redis_client = None

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
