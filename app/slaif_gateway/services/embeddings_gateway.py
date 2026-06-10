"""Orchestration for standalone OpenAI-compatible Embeddings API endpoint."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.responses import JSONResponse
from starlette.requests import Request

from slaif_gateway.api import dependencies as dependencies_module
from slaif_gateway.api.accounting_errors import openai_error_from_accounting_error
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.api.policy_errors import openai_error_from_request_policy_error
from slaif_gateway.api.pricing_errors import openai_error_from_pricing_error
from slaif_gateway.api.provider_errors import openai_error_from_provider_error
from slaif_gateway.api.quota_errors import openai_error_from_quota_error
from slaif_gateway.api.routing_errors import openai_error_from_route_resolution_error
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.metrics import add_cost_eur, add_tokens, observe_provider_call
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.accounting import ActualUsage, FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.embeddings import EmbeddingsPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.embeddings_request_policy import EmbeddingsRequestPolicy
from slaif_gateway.services.embeddings_route_capabilities import (
    enforce_embeddings_route_capabilities,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_payloads import build_embeddings_upstream_body
from slaif_gateway.services.upstream_request_contracts import (
    normalize_embeddings_upstream_request,
)

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check

EMBEDDINGS_ENDPOINT = "/v1/embeddings"


async def handle_embeddings_create(
    *,
    payload: dict[str, Any],
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = dict(payload)
    policy_service = EmbeddingsRequestPolicy(settings)
    try:
        policy_result = policy_service.apply(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    route = await _resolve_embeddings_route(
        authenticated_key=authenticated_key,
        requested_model=str(policy_result.effective_body["model"]),
        request=request,
    )
    upstream_body = _build_safe_embeddings_upstream_body(
        policy_result.effective_body,
        resolved_model=route.resolved_model,
    )

    try:
        enforce_embeddings_route_capabilities(
            route_capabilities=route.capabilities,
            dimensions_requested="dimensions" in policy_result.effective_body,
        )
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    reservation, cost_estimate = await _reserve_embeddings_quota(
        authenticated_key=authenticated_key,
        route=route,
        policy_result=policy_result,
        request_id=request_id,
        request=request,
    )

    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint="embeddings",
        body=upstream_body,
        request_id=request_id,
    )
    adapter = get_provider_adapter(route, settings)
    try:
        provider_response = await observe_provider_call(
            provider=route.provider,
            endpoint=EMBEDDINGS_ENDPOINT,
            call=lambda: adapter.create_embedding(provider_request),
        )
    except ProviderError as exc:
        await _record_embeddings_provider_failure(
            reservation=reservation,
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            cost_estimate=cost_estimate,
            request_id=request_id,
            request=request,
            provider_error=exc,
        )
        raise openai_error_from_provider_error(exc) from exc

    accounting_result = await _finalize_embeddings_success(
        reservation=reservation,
        authenticated_key=authenticated_key,
        route=route,
        policy_result=policy_result,
        cost_estimate=cost_estimate,
        provider_response=provider_response,
        request_id=request_id,
        request=request,
    )
    _record_embeddings_success_metrics(
        route=route,
        provider_response=provider_response,
        accounting_result=accounting_result,
    )
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
        headers=dict(provider_response.headers),
    )


async def _resolve_embeddings_route(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    requested_model: str,
    request: Request | None,
) -> RouteResolutionResult:
    async for session in _db_session_iterator(request):
        service = RouteResolutionService(
            model_routes_repository=ModelRoutesRepository(session),
            provider_configs_repository=ProviderConfigsRepository(session),
        )
        try:
            return await service.resolve_model(
                requested_model,
                authenticated_key,
                endpoint=EMBEDDINGS_ENDPOINT,
            )
        except RouteResolutionError as exc:
            raise openai_error_from_route_resolution_error(exc) from exc
    raise _database_session_unavailable_error()


async def _reserve_embeddings_quota(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: EmbeddingsPolicyResult,
    request_id: str,
    request: Request | None,
) -> tuple[QuotaReservationResult, ChatCostEstimate]:
    async for session in _db_session_iterator(request):
        pricing = PricingService(
            pricing_rules_repository=PricingRulesRepository(session),
            fx_rates_repository=FxRatesRepository(session),
        )
        quota = QuotaService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
        )
        try:
            cost_estimate = await pricing.estimate_embeddings_cost(
                route=route,
                policy=policy_result,
                endpoint=EMBEDDINGS_ENDPOINT,
            )
            reservation = await quota.reserve_for_chat_completion(
                authenticated_key=authenticated_key,
                route=route,
                policy=policy_result,  # type: ignore[arg-type]
                cost_estimate=cost_estimate,
                request_id=request_id,
                endpoint=EMBEDDINGS_ENDPOINT,
            )
            await session.commit()
            return reservation, cost_estimate
        except PricingError as exc:
            raise openai_error_from_pricing_error(exc) from exc
        except QuotaError as exc:
            raise openai_error_from_quota_error(exc) from exc
    raise _database_session_unavailable_error()


async def _record_embeddings_provider_failure(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: EmbeddingsPolicyResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    request: Request | None,
    provider_error: ProviderError,
) -> None:
    async for session in _db_session_iterator(request):
        service = AccountingService(session)
        try:
            await service.record_provider_failure_and_release(
                reservation.reservation_id,
                authenticated_key,
                route,
                policy_result,  # type: ignore[arg-type]
                cost_estimate,
                request_id,
                error_type=provider_error.error_type,
                endpoint=EMBEDDINGS_ENDPOINT,
                error_code=provider_error.error_code,
                status_code=provider_error.upstream_status_code or provider_error.status_code,
                provider_diagnostic=provider_error.diagnostic.to_safe_dict()
                if provider_error.diagnostic is not None
                else None,
                streaming=False,
            )
            await session.commit()
            return
        except AccountingError as exc:
            raise openai_error_from_accounting_error(exc) from exc
        except QuotaError as exc:
            raise openai_error_from_quota_error(exc) from exc
    raise _database_session_unavailable_error()


async def _finalize_embeddings_success(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: EmbeddingsPolicyResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
    request: Request | None,
) -> FinalizedAccountingResult:
    async for session in _db_session_iterator(request):
        service = AccountingService(session)
        try:
            if provider_response.usage is not None:
                result = await service.finalize_successful_response(
                    reservation.reservation_id,
                    authenticated_key,
                    route,
                    policy_result,  # type: ignore[arg-type]
                    cost_estimate,
                    provider_response,
                    request_id,
                    endpoint=EMBEDDINGS_ENDPOINT,
                )
                await session.commit()
                return result

            usage = ActualUsage(
                prompt_tokens=policy_result.estimated_input_tokens,
                completion_tokens=0,
                total_tokens=policy_result.estimated_input_tokens,
                other_usage={},
            )
            result = await service.finalize_successful_custom_response(
                reservation.reservation_id,
                authenticated_key,
                route,
                cost_estimate,
                provider_response,
                request_id,
                endpoint=EMBEDDINGS_ENDPOINT,
                usage=usage,
                actual_cost_eur=cost_estimate.estimated_total_cost_eur,
                actual_cost_native=cost_estimate.estimated_total_cost_native,
                native_currency=cost_estimate.native_currency,
                cost_source="slaif_estimated_input_pricing",
                cost_confidence="estimated_from_embeddings_input",
                component_costs_native={"input": cost_estimate.estimated_total_cost_native},
                component_token_counts={"prompt_tokens": usage.prompt_tokens, "completion_tokens": 0},
                response_metadata_extra={
                    "provider_usage_available": False,
                    "embeddings_estimate_reason": "usage_missing_estimated",
                    "encoding_format": policy_result.effective_body.get("encoding_format", "float"),
                    "dimensions": policy_result.effective_body.get("dimensions"),
                },
                streaming=False,
            )
            await session.commit()
            return result
        except AccountingError as exc:
            raise openai_error_from_accounting_error(exc) from exc
        except QuotaError as exc:
            raise openai_error_from_quota_error(exc) from exc
    raise _database_session_unavailable_error()


def _build_safe_embeddings_upstream_body(
    effective_body: dict[str, Any],
    *,
    resolved_model: str,
) -> dict[str, Any]:
    normalized_request = normalize_embeddings_upstream_request(
        effective_body,
        requested_model=str(effective_body["model"]),
        upstream_model=resolved_model,
    )
    return build_embeddings_upstream_body(normalized_request)


def _db_session_iterator(request: Request | None):
    try:
        if request is None:
            return _get_db_session_after_auth_header_check()
        return _get_db_session_after_auth_header_check(request)
    except TypeError:
        return _get_db_session_after_auth_header_check()


def _database_session_unavailable_error() -> OpenAICompatibleError:
    return OpenAICompatibleError(
        "Database session could not be created.",
        status_code=500,
        error_type="server_error",
        code="database_session_unavailable",
    )


def _request_id_from_request(request: Request | None) -> str:
    request_id = getattr(getattr(request, "state", None), "gateway_request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return f"gw-{uuid.uuid4()}"


def _record_embeddings_success_metrics(
    *,
    route: RouteResolutionResult,
    provider_response: ProviderResponse,
    accounting_result: FinalizedAccountingResult,
) -> None:
    usage = provider_response.usage
    if usage is not None:
        add_tokens(
            provider=route.provider,
            model=route.resolved_model,
            token_type="prompt",
            count=usage.prompt_tokens,
        )
        add_tokens(
            provider=route.provider,
            model=route.resolved_model,
            token_type="total",
            count=usage.total_tokens,
        )
    else:
        add_tokens(
            provider=route.provider,
            model=route.resolved_model,
            token_type="prompt",
            count=accounting_result.prompt_tokens,
        )
        add_tokens(
            provider=route.provider,
            model=route.resolved_model,
            token_type="total",
            count=accounting_result.total_tokens,
        )
    add_cost_eur(
        provider=route.provider,
        model=route.resolved_model,
        cost_eur=accounting_result.actual_cost_eur,
    )
