"""Orchestration for non-streaming OpenAI-compatible chat completions."""

from __future__ import annotations

import uuid

from fastapi.responses import JSONResponse

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
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError

_get_db_session_after_auth_header_check = dependencies_module._get_db_session_after_auth_header_check


async def handle_chat_completion(
    *,
    payload: ChatCompletionRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
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

    policy = ChatCompletionRequestPolicy(settings=settings)
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
    route, cost_estimate, reservation = await _reserve_chat_completion_quota(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        policy_result=policy_result,
        request_id=request_id,
    )

    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint="chat.completions",
        body=dict(policy_result.effective_body),
        request_id=request_id,
    )
    try:
        adapter = get_provider_adapter(route, settings)
        provider_response = await adapter.forward_chat_completion(provider_request)
    except ProviderError as exc:
        try:
            await _record_provider_failure_and_release(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                policy_result=policy_result,
                cost_estimate=cost_estimate,
                request_id=request_id,
                provider_error=exc,
            )
        except AccountingError as accounting_exc:
            raise openai_error_from_accounting_error(accounting_exc) from accounting_exc
        raise openai_error_from_provider_error(exc) from exc

    try:
        await _finalize_successful_chat_completion(
            reservation=reservation,
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            cost_estimate=cost_estimate,
            provider_response=provider_response,
            request_id=request_id,
        )
    except AccountingError as exc:
        raise openai_error_from_accounting_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def _reserve_chat_completion_quota(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    effective_model: str,
    policy_result: ChatCompletionPolicyResult,
    request_id: str,
) -> tuple[RouteResolutionResult, ChatCostEstimate, QuotaReservationResult]:
    session_iterator = _get_db_session_after_auth_header_check()
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise OpenAICompatibleError(
            "Provider forwarding is not implemented yet.",
            status_code=501,
            error_type="server_error",
            code="provider_forwarding_not_implemented",
        ) from exc

    try:
        service = RouteResolutionService(
            model_routes_repository=ModelRoutesRepository(session),
            provider_configs_repository=ProviderConfigsRepository(session),
        )
        try:
            route = await service.resolve_model(
                effective_model,
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

        if hasattr(session, "commit"):
            await session.commit()
        return route, cost_estimate, reservation
    finally:
        await session_iterator.aclose()


async def _record_provider_failure_and_release(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ChatCompletionPolicyResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    provider_error: ProviderError,
) -> None:
    session_iterator = _get_db_session_after_auth_header_check()
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise OpenAICompatibleError(
            "Provider forwarding is not implemented yet.",
            status_code=501,
            error_type="server_error",
            code="provider_forwarding_not_implemented",
        ) from exc

    try:
        accounting_service = AccountingService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
            usage_ledger_repository=UsageLedgerRepository(session),
        )
        await accounting_service.record_provider_failure_and_release(
            reservation.reservation_id,
            authenticated_key,
            route,
            policy_result,
            cost_estimate,
            request_id=request_id,
            error_type=provider_error.error_code,
            error_code=provider_error.error_code,
            status_code=provider_error.upstream_status_code,
        )
        if hasattr(session, "commit"):
            await session.commit()
        return
    finally:
        await session_iterator.aclose()


async def _finalize_successful_chat_completion(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ChatCompletionPolicyResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
) -> None:
    session_iterator = _get_db_session_after_auth_header_check()
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise OpenAICompatibleError(
            "Provider forwarding is not implemented yet.",
            status_code=501,
            error_type="server_error",
            code="provider_forwarding_not_implemented",
        ) from exc

    try:
        accounting_service = AccountingService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
            usage_ledger_repository=UsageLedgerRepository(session),
        )
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
        return
    finally:
        await session_iterator.aclose()
