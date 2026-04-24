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
from slaif_gateway.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_settings = settings or get_settings()
    app = FastAPI(title="SLAIF API Gateway")
    app.state.settings = app_settings

    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {
            "status": "ok",
            "database": "not_configured",
            "redis": "not_configured",
        }

    @app.get("/v1/models")
    def list_models() -> dict[str, object]:
        return {"object": "list", "data": []}

    return app


app = create_app()
