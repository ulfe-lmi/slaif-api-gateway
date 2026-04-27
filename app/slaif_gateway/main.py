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
from slaif_gateway.api.openai_compat import router as openai_compat_router
from slaif_gateway.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_settings = settings or get_settings()
    app = FastAPI(title="SLAIF API Gateway")
    app.state.settings = app_settings

    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

    app.include_router(health_router)
    app.include_router(openai_compat_router)

    return app


app = create_app()
