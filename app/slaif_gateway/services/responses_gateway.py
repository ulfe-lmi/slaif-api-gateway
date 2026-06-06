"""Orchestration for stateless text-only OpenAI-compatible Responses."""

from __future__ import annotations

import uuid

from fastapi.responses import JSONResponse
from starlette.requests import Request

from slaif_gateway.api import dependencies as dependencies_module
from slaif_gateway.api.accounting_errors import openai_error_from_accounting_error
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.api.policy_errors import openai_error_from_request_policy_error
from slaif_gateway.api.pricing_errors import openai_error_from_pricing_error
from slaif_gateway.api.provider_errors import openai_error_from_provider_error
from slaif_gateway.api.quota_errors import openai_error_from_quota_error
from slaif_gateway.api.rate_limit_errors import openai_error_from_rate_limit_error
from slaif_gateway.api.routing_errors import openai_error_from_route_resolution_error
from slaif_gateway.cache.redis import get_redis_client_from_app
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.metrics import (
    add_cost_eur,
    add_tokens,
    increment_accounting_failure,
    increment_provider_http_error,
    increment_quota_rejection,
    increment_rate_limit_rejection,
    increment_rate_limit_release_failure,
    observe_provider_call,
)
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.schemas.policy import ResponsesPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.rate_limits import RateLimitPolicy
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.rate_limit_errors import RateLimitError, RedisRateLimitUnavailableError
from slaif_gateway.services.rate_limit_policy import build_rate_limit_policy
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy
from slaif_gateway.services.responses_route_capabilities import (
    enforce_responses_route_capabilities,
)
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_request_contracts import normalize_responses_upstream_request
from slaif_gateway.services.upstream_payloads import build_responses_upstream_body

RESPONSES_ENDPOINT = "/v1/responses"
RESPONSES_PROVIDER_ENDPOINT = "responses"

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check


def _build_safe_responses_upstream_body(
    *,
    policy_result: ResponsesPolicyResult,
    upstream_model: str,
) -> dict[str, object]:
    try:
        normalized_request = normalize_responses_upstream_request(
            policy_result.effective_body,
            requested_model=policy_result.effective_body["model"],
            upstream_model=upstream_model,
        )
        return build_responses_upstream_body(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Request contains fields that are not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


async def handle_response_create(
    *,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = payload.model_dump(mode="python", exclude_none=True)
    policy = ResponsesRequestPolicy(settings=settings)
    try:
        policy_result = policy.apply(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    route = await _resolve_responses_route(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        request=request,
    )
    upstream_body = _build_safe_responses_upstream_body(
        policy_result=policy_result,
        upstream_model=route.resolved_model,
    )
    rate_limit_reservation = await _reserve_redis_rate_limit(
        authenticated_key=authenticated_key,
        policy_result=policy_result,
        request_id=request_id,
        settings=settings,
        request=request,
    )
    try:
        cost_estimate, reservation = await _reserve_responses_quota(
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            request_id=request_id,
            request=request,
        )
        provider_request = ProviderRequest(
            provider=route.provider,
            upstream_model=route.resolved_model,
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
            body=upstream_body,
            request_id=request_id,
        )
        try:
            adapter = get_provider_adapter(route, settings)
            provider_response = await observe_provider_call(
                provider=route.provider,
                endpoint=RESPONSES_PROVIDER_ENDPOINT,
                call=lambda: adapter.forward_response(provider_request),
            )
        except ProviderError as exc:
            await _record_provider_failure_and_release(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                policy_result=policy_result,
                cost_estimate=cost_estimate,
                request_id=request_id,
                provider_error=exc,
                request=request,
            )
            raise openai_error_from_provider_error(exc) from exc

        try:
            accounting_result = await _finalize_successful_response(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                policy_result=policy_result,
                cost_estimate=cost_estimate,
                provider_response=provider_response,
                request_id=request_id,
                request=request,
            )
            _record_success_metrics(
                route=route,
                provider_response=provider_response,
                accounting_result=accounting_result,
            )
        except AccountingError as exc:
            increment_accounting_failure(exc.error_code)
            raise openai_error_from_accounting_error(exc) from exc
        except QuotaError as exc:
            increment_quota_rejection(exc.error_code)
            raise openai_error_from_quota_error(exc) from exc

        response = JSONResponse(
            status_code=provider_response.status_code,
            content=dict(provider_response.json_body),
        )
    except Exception:
        await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
        raise

    await _release_rate_limit_concurrency(rate_limit_reservation, suppress=False)
    return response


async def _resolve_responses_route(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    effective_model: str,
    request: Request | None,
) -> RouteResolutionResult:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        service = RouteResolutionService(
            model_routes_repository=ModelRoutesRepository(session),
            provider_configs_repository=ProviderConfigsRepository(session),
        )
        try:
            route = await service.resolve_model(
                effective_model,
                authenticated_key,
                endpoint=RESPONSES_ENDPOINT,
            )
            enforce_responses_route_capabilities(route_capabilities=route.capabilities)
        except RouteResolutionError as exc:
            raise openai_error_from_route_resolution_error(exc) from exc
        except RequestPolicyError as exc:
            raise openai_error_from_request_policy_error(exc) from exc
        return route
    finally:
        await session_iterator.aclose()


async def _reserve_responses_quota(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    request_id: str,
    request: Request | None,
) -> tuple[ChatCostEstimate, QuotaReservationResult]:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        pricing_service = PricingService(
            pricing_rules_repository=PricingRulesRepository(session),
            fx_rates_repository=FxRatesRepository(session),
        )
        try:
            cost_estimate = await pricing_service.estimate_chat_completion_cost(
                route=route,
                policy=policy_result,
                endpoint=RESPONSES_ENDPOINT,
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
                endpoint=RESPONSES_ENDPOINT,
            )
        except QuotaError as exc:
            increment_quota_rejection(quota_exc_code(exc))
            raise openai_error_from_quota_error(exc) from exc

        if hasattr(session, "commit"):
            await session.commit()
        return cost_estimate, reservation
    finally:
        await session_iterator.aclose()


async def _reserve_redis_rate_limit(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    policy_result: ResponsesPolicyResult,
    request_id: str,
    settings: Settings,
    request: Request | None,
) -> _RateLimitReservation | None:
    if not settings.ENABLE_REDIS_RATE_LIMITS:
        return None

    policy = build_rate_limit_policy(authenticated_key=authenticated_key, settings=settings)
    if not policy.has_limits():
        return None
    if request is None:
        raise OpenAICompatibleError(
            "Rate limit service is unavailable.",
            status_code=503,
            error_type="server_error",
            code="redis_rate_limit_unavailable",
        )
    try:
        redis_client = get_redis_client_from_app(request)
    except RuntimeError as exc:
        rate_limit_exc = RedisRateLimitUnavailableError()
        increment_rate_limit_rejection(rate_limit_exc.error_code)
        raise openai_error_from_rate_limit_error(rate_limit_exc) from exc
    service = RedisRateLimitService(
        redis_client,
        fail_closed=settings.rate_limit_fail_closed(),
    )
    try:
        await service.check_and_reserve(
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_tokens=policy_result.estimated_input_tokens
            + policy_result.effective_output_tokens,
            policy=policy,
        )
    except RateLimitError as exc:
        increment_rate_limit_rejection(exc.error_code)
        raise openai_error_from_rate_limit_error(exc) from exc
    return _RateLimitReservation(
        service=service,
        policy=policy,
        gateway_key_id=authenticated_key.gateway_key_id,
        request_id=request_id,
        concurrency_reserved=policy.concurrent_requests is not None,
    )


async def _record_provider_failure_and_release(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    provider_error: ProviderError,
    request: Request | None,
) -> None:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

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
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
            error_type=provider_error.error_code,
            error_code=provider_error.error_code,
            status_code=provider_error.upstream_status_code,
            provider_diagnostic=provider_error.diagnostic.to_safe_dict()
            if provider_error.diagnostic is not None
            else None,
        )
        if hasattr(session, "commit"):
            await session.commit()
    except AccountingError as exc:
        increment_accounting_failure(exc.error_code)
        raise openai_error_from_accounting_error(exc) from exc
    except QuotaError as exc:
        increment_quota_rejection(exc.error_code)
        raise openai_error_from_quota_error(exc) from exc
    finally:
        await session_iterator.aclose()


async def _finalize_successful_response(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
    request: Request | None,
) -> FinalizedAccountingResult:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        accounting_service = AccountingService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
            usage_ledger_repository=UsageLedgerRepository(session),
        )
        result = await accounting_service.finalize_successful_response(
            reservation.reservation_id,
            authenticated_key,
            route,
            policy_result,
            cost_estimate,
            provider_response,
            request_id=request_id,
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
        )
        if hasattr(session, "commit"):
            await session.commit()
        return result
    finally:
        await session_iterator.aclose()


def _record_success_metrics(
    *,
    route: RouteResolutionResult,
    provider_response: ProviderResponse,
    accounting_result: FinalizedAccountingResult,
) -> None:
    add_tokens(
        provider=route.provider,
        model=route.resolved_model,
        token_type="prompt",
        count=accounting_result.prompt_tokens,
    )
    add_tokens(
        provider=route.provider,
        model=route.resolved_model,
        token_type="completion",
        count=accounting_result.completion_tokens,
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
    if provider_response.status_code >= 400:
        increment_provider_http_error(
            provider=route.provider,
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
            upstream_status_code=provider_response.status_code,
        )


class _RateLimitReservation:
    def __init__(
        self,
        *,
        service: RedisRateLimitService,
        policy: RateLimitPolicy,
        gateway_key_id: uuid.UUID,
        request_id: str,
        concurrency_reserved: bool,
    ) -> None:
        self.service = service
        self.policy = policy
        self.gateway_key_id = gateway_key_id
        self.request_id = request_id
        self.concurrency_reserved = concurrency_reserved


async def _release_rate_limit_concurrency(
    reservation: _RateLimitReservation | None,
    *,
    suppress: bool,
) -> None:
    if reservation is None or not reservation.concurrency_reserved:
        return
    try:
        await reservation.service.release_concurrency(
            gateway_key_id=reservation.gateway_key_id,
            request_id=reservation.request_id,
        )
    except RateLimitError as exc:
        increment_rate_limit_release_failure(exc.error_code)
        if not suppress:
            raise openai_error_from_rate_limit_error(exc) from exc


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


def quota_exc_code(exc: QuotaError) -> str:
    return getattr(exc, "error_code", "quota_error")
