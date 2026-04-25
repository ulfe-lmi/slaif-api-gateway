"""ASGI app entrypoint for the SLAIF API Gateway."""

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from slaif_gateway.api.dependencies import (
    _get_db_session_after_auth_header_check,
    get_authenticated_gateway_key,
)
from slaif_gateway.api.errors import (
    OpenAICompatibleError,
    http_exception_handler,
    openai_compatible_error_handler,
    request_validation_exception_handler,
)
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import OpenAIModelList
from slaif_gateway.services.model_catalog import ModelCatalogService


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

    @app.get("/v1/models", response_model=OpenAIModelList)
    async def list_models(
        authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
    ) -> OpenAIModelList:
        async for session in _get_db_session_after_auth_header_check():
            service = ModelCatalogService(
                model_routes_repository=ModelRoutesRepository(session),
                provider_configs_repository=ProviderConfigsRepository(session),
            )
            models = await service.list_visible_models(authenticated_key)
            return OpenAIModelList(data=models)

        return OpenAIModelList(data=[])

    return app


app = create_app()
