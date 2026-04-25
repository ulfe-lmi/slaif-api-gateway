"""ASGI app entrypoint for the SLAIF API Gateway."""

import uuid

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from slaif_gateway.api.accounting_errors import openai_error_from_accounting_error
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
from slaif_gateway.api.pricing_errors import openai_error_from_pricing_error
from slaif_gateway.api.provider_errors import openai_error_from_provider_error
from slaif_gateway.api.quota_errors import openai_error_from_quota_error
from slaif_gateway.api.routing_errors import openai_error_from_route_resolution_error
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest, OpenAIModelList
from slaif_gateway.schemas.providers import ProviderRequest
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.model_catalog import ModelCatalogService
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
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

        if policy_result.effective_body.get("stream") is True:
            raise OpenAICompatibleError(
                "Streaming chat completions are not implemented yet.",
                status_code=501,
                error_type="server_error",
                code="streaming_not_implemented",
                param="stream",
            )

        request_id = f"gw-{uuid.uuid4()}"
        async for session in _get_db_session_after_auth_header_check():
            service = RouteResolutionService(
                model_routes_repository=ModelRoutesRepository(session),
                provider_configs_repository=ProviderConfigsRepository(session),
            )
            try:
                route = await service.resolve_model(
                    policy_result.effective_body["model"],
                    authenticated_key,
                )
            except RouteResolutionError as exc:
                raise openai_error_from_route_resolution_error(exc) from exc

            pricing_service = PricingService(
                pricing_rules_repository=PricingRulesRepository(session),
                fx_rates_repository=FxRatesRepository(session),
            )
            try:
                cost_estimate = await pricing_service.estimate_chat_completion_cost(
                    route=route,
                    policy=policy_result,
                    endpoint="chat.completions",
                )
            except PricingError as exc:
                raise openai_error_from_pricing_error(exc) from exc

            quota_service = QuotaService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
            )
            reservation = None
            try:
                reservation = await quota_service.reserve_for_chat_completion(
                    authenticated_key=authenticated_key,
                    route=route,
                    policy=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                )
            except QuotaError as exc:
                raise openai_error_from_quota_error(exc) from exc

            provider_request = ProviderRequest(
                provider=route.provider,
                upstream_model=route.resolved_model,
                endpoint="chat.completions",
                body=dict(policy_result.effective_body),
                request_id=request_id,
            )
            accounting_service = AccountingService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
            )
            try:
                adapter = get_provider_adapter(route.provider, app_settings)
                provider_response = await adapter.forward_chat_completion(provider_request)
            except ProviderError as exc:
                if reservation is not None:
                    try:
                        await accounting_service.record_provider_failure_and_release(
                            reservation.reservation_id,
                            authenticated_key,
                            route,
                            policy_result,
                            cost_estimate,
                            request_id=request_id,
                            error_type=exc.error_code,
                            error_code=exc.error_code,
                            status_code=exc.upstream_status_code,
                        )
                        if hasattr(session, "commit"):
                            await session.commit()
                    except AccountingError as accounting_exc:
                        raise openai_error_from_accounting_error(accounting_exc) from accounting_exc
                raise openai_error_from_provider_error(exc) from exc

            try:
                await accounting_service.finalize_successful_response(
                    reservation.reservation_id,
                    authenticated_key,
                    route,
                    policy_result,
                    cost_estimate,
                    provider_response,
                    request_id=request_id,
                    endpoint="chat.completions",
                )
                if hasattr(session, "commit"):
                    await session.commit()
            except AccountingError as exc:
                raise openai_error_from_accounting_error(exc) from exc

            return JSONResponse(
                status_code=provider_response.status_code,
                content=dict(provider_response.json_body),
            )

        raise OpenAICompatibleError(
            "Provider forwarding is not implemented yet.",
            status_code=501,
            error_type="server_error",
            code="provider_forwarding_not_implemented",
        )

    return app


app = create_app()
