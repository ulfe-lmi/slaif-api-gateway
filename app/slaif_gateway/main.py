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
from slaif_gateway.api.policy_errors import openai_error_from_request_policy_error
from slaif_gateway.api.routing_errors import openai_error_from_route_resolution_error
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest, OpenAIModelList
from slaif_gateway.services.model_catalog import ModelCatalogService
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError


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

    @app.post("/v1/chat/completions")
    async def validate_chat_completions(
        payload: ChatCompletionRequest,
        authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
    ):
        body = payload.model_dump(mode="python", exclude_none=True)

        if not body.get("model"):
            raise OpenAICompatibleError(
                "The 'model' field is required.",
                status_code=400,
                error_type="invalid_request_error",
                code="missing_model",
                param="model",
            )

        if "messages" not in body:
            raise OpenAICompatibleError(
                "The 'messages' field is required.",
                status_code=400,
                error_type="invalid_request_error",
                code="missing_messages",
                param="messages",
            )

        if not isinstance(body.get("messages"), list):
            raise OpenAICompatibleError(
                "The 'messages' field must be a list.",
                status_code=400,
                error_type="invalid_request_error",
                code="invalid_messages",
                param="messages",
            )

        policy = ChatCompletionRequestPolicy(settings=app_settings)
        try:
            policy_result = policy.apply(body)
        except RequestPolicyError as exc:
            raise openai_error_from_request_policy_error(exc) from exc

        async for session in _get_db_session_after_auth_header_check():
            service = RouteResolutionService(
                model_routes_repository=ModelRoutesRepository(session),
                provider_configs_repository=ProviderConfigsRepository(session),
            )
            try:
                await service.resolve_model(policy_result.effective_body["model"], authenticated_key)
            except RouteResolutionError as exc:
                raise openai_error_from_route_resolution_error(exc) from exc

            raise OpenAICompatibleError(
                "Provider forwarding is not implemented yet.",
                status_code=501,
                error_type="server_error",
                code="provider_forwarding_not_implemented",
            )

        raise OpenAICompatibleError(
            "Provider forwarding is not implemented yet.",
            status_code=501,
            error_type="server_error",
            code="provider_forwarding_not_implemented",
        )

    return app


app = create_app()
