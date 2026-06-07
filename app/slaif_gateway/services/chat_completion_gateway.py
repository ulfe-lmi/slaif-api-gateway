"""Orchestration for OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

import anyio
import structlog
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import StreamingResponse

from slaif_gateway.cache.redis import get_redis_client_from_app
from slaif_gateway.api import dependencies as dependencies_module
from slaif_gateway.api.accounting_errors import openai_error_from_accounting_error
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.api.policy_errors import openai_error_from_request_policy_error
from slaif_gateway.api.pricing_errors import openai_error_from_pricing_error
from slaif_gateway.api.provider_errors import openai_error_from_provider_error
from slaif_gateway.api.quota_errors import openai_error_from_quota_error
from slaif_gateway.api.rate_limit_errors import openai_error_from_rate_limit_error
from slaif_gateway.api.routing_errors import openai_error_from_route_resolution_error
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.repositories.usage_profiles import UsageProfilesRepository
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.errors import ProviderHTTPError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.metrics import (
    add_cost_eur,
    add_tokens,
    increment_accounting_failure,
    increment_provider_diagnostic_generated,
    increment_provider_http_error,
    increment_quota_rejection,
    increment_rate_limit_heartbeat_failure,
    increment_rate_limit_rejection,
    increment_rate_limit_release_failure,
    observe_provider_call,
    record_provider_call_result,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderStreamChunk
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.rate_limits import RateLimitPolicy
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.chat_completion_route_capabilities import (
    enforce_chat_completion_route_capabilities,
)
from slaif_gateway.services.chat_streaming_live_burn import (
    CHAT_STREAMING_LIVE_BURN_ERROR_CODE,
    CHAT_STREAMING_LIVE_BURN_ERROR_MESSAGE,
    ChatStreamingLiveBurnBudget,
    ChatStreamingLiveBurnEstimate,
    ChatStreamingLiveBurnMonitor,
    ChatStreamingLiveBurnPolicy,
    ChatStreamingLiveBurnPolicyError,
    build_chat_streaming_live_burn_budget,
    chat_streaming_live_burn_policy_from_metadata,
    default_chat_streaming_live_burn_policy,
    pre_provider_chat_streaming_live_burn_error,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.rate_limit_errors import RateLimitError
from slaif_gateway.services.rate_limit_errors import RedisRateLimitUnavailableError
from slaif_gateway.services.rate_limit_policy import build_rate_limit_policy
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_request_contracts import normalize_chat_completion_upstream_request
from slaif_gateway.services.upstream_payloads import build_chat_completion_upstream_body
from slaif_gateway.services.usage_profile_service import (
    UsageProfileService,
    build_chat_completion_tool_metadata,
)
from slaif_gateway.providers.streaming import format_openai_error_event

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check
logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class _RateLimitReservation:
    service: RedisRateLimitService
    policy: RateLimitPolicy
    gateway_key_id: uuid.UUID
    request_id: str
    concurrency_reserved: bool


@dataclass(frozen=True, slots=True)
class _ChatCompletionQuotaReservation:
    cost_estimate: ChatCostEstimate
    reservation: QuotaReservationResult
    live_burn_budget: ChatStreamingLiveBurnBudget | None


def _build_safe_chat_completion_upstream_body(
    *,
    policy_result: ChatCompletionPolicyResult,
    upstream_model: str,
) -> dict[str, object]:
    try:
        normalized_request = normalize_chat_completion_upstream_request(
            policy_result.effective_body,
            requested_model=policy_result.effective_body["model"],
            upstream_model=upstream_model,
        )
        return build_chat_completion_upstream_body(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Request contains fields that are not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


async def handle_chat_completion(
    *,
    payload: ChatCompletionRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
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
        policy_result = policy.apply(
            body,
            capability_policy_mode=authenticated_key.capability_policy_mode,
        )
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    route = await _resolve_chat_completion_route(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        policy_result=policy_result,
        request=request,
    )
    upstream_body = _build_safe_chat_completion_upstream_body(
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
        quota = await _reserve_chat_completion_quota(
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            request_id=request_id,
            request=request,
            settings=settings,
        )
        cost_estimate = quota.cost_estimate
        reservation = quota.reservation

        pre_provider_live_burn = pre_provider_chat_streaming_live_burn_error(
            quota.live_burn_budget
        )
        if policy_result.effective_body.get("stream") is True and pre_provider_live_burn is not None:
            try:
                await _record_streaming_live_burn_abort_estimate(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    estimate=pre_provider_live_burn,
                    request=request,
                )
            except AccountingError as accounting_exc:
                increment_accounting_failure(accounting_exc.error_code)
                raise openai_error_from_accounting_error(accounting_exc) from accounting_exc
            except QuotaError as quota_exc:
                increment_quota_rejection(quota_exc.error_code)
                raise openai_error_from_quota_error(quota_exc) from quota_exc
            increment_quota_rejection(CHAT_STREAMING_LIVE_BURN_ERROR_CODE)
            raise OpenAICompatibleError(
                CHAT_STREAMING_LIVE_BURN_ERROR_MESSAGE,
                status_code=429,
                error_type="insufficient_quota",
                code=CHAT_STREAMING_LIVE_BURN_ERROR_CODE,
            )

        if policy_result.effective_body.get("stream") is True:
            try:
                response = _streaming_chat_completion_response(
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    reservation=reservation,
                    request_id=request_id,
                    settings=settings,
                    request=request,
                    rate_limit_reservation=rate_limit_reservation,
                    upstream_body=upstream_body,
                    live_burn_budget=quota.live_burn_budget,
                )
                rate_limit_reservation = None
                return response
            except Exception:
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                raise

        provider_request = ProviderRequest(
            provider=route.provider,
            upstream_model=route.resolved_model,
            endpoint="chat.completions",
            body=upstream_body,
            request_id=request_id,
        )
        try:
            adapter = get_provider_adapter(route, settings)
            provider_response = await observe_provider_call(
                provider=route.provider,
                endpoint="chat.completions",
                call=lambda: adapter.forward_chat_completion(provider_request),
            )
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
                    request=request,
                )
            except AccountingError as accounting_exc:
                increment_accounting_failure(accounting_exc.error_code)
                raise openai_error_from_accounting_error(accounting_exc) from accounting_exc
            except QuotaError as quota_exc:
                increment_quota_rejection(quota_exc.error_code)
                raise openai_error_from_quota_error(quota_exc) from quota_exc
            raise openai_error_from_provider_error(exc) from exc

        try:
            accounting_result = await _finalize_successful_chat_completion(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                policy_result=policy_result,
                cost_estimate=cost_estimate,
                provider_response=provider_response,
                request_id=request_id,
                request=request,
            )
            _record_provider_success_metrics(
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


def _streaming_chat_completion_response(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ChatCompletionPolicyResult,
    cost_estimate: ChatCostEstimate,
    reservation: QuotaReservationResult,
    request_id: str,
    settings: Settings,
    request: Request | None,
    rate_limit_reservation: _RateLimitReservation | None,
    upstream_body: dict[str, object],
    live_burn_budget: ChatStreamingLiveBurnBudget | None,
) -> StreamingResponse:
    adapter = get_provider_adapter(route, settings)
    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint="chat.completions",
        body=upstream_body,
        request_id=request_id,
    )

    async def _events():
        start = time.perf_counter()
        usage_chunk: ProviderStreamChunk | None = None
        upstream_request_id: str | None = None
        done_event: str | None = None
        completed = False
        provider_status = "error"
        live_burn_monitor = (
            ChatStreamingLiveBurnMonitor(live_burn_budget)
            if live_burn_budget is not None
            else None
        )
        heartbeat_stop = asyncio.Event()
        heartbeat_task = _start_rate_limit_heartbeat(
            rate_limit_reservation,
            stop_event=heartbeat_stop,
        )
        try:
            async for chunk in adapter.stream_chat_completion(provider_request):
                if chunk.upstream_request_id:
                    upstream_request_id = chunk.upstream_request_id
                if chunk.usage is not None:
                    usage_chunk = chunk
                if chunk.is_done:
                    completed = True
                    done_event = chunk.raw_sse_event
                    continue
                yield chunk.raw_sse_event
                live_burn_estimate = (
                    live_burn_monitor.observe_chunk(chunk.json_body)
                    if live_burn_monitor is not None
                    else None
                )
                if live_burn_estimate is not None:
                    await _record_streaming_live_burn_abort_estimate(
                        reservation=reservation,
                        authenticated_key=authenticated_key,
                        route=route,
                        cost_estimate=cost_estimate,
                        request_id=request_id,
                        estimate=live_burn_estimate,
                        request=request,
                    )
                    provider_status = "interrupted"
                    yield format_openai_error_event(
                        message=CHAT_STREAMING_LIVE_BURN_ERROR_MESSAGE,
                        error_type="insufficient_quota",
                        code=CHAT_STREAMING_LIVE_BURN_ERROR_CODE,
                        request_id=request_id,
                    )
                    return

            if completed and usage_chunk is not None:
                provider_response = _provider_response_from_stream(
                    route=route,
                    chunk=usage_chunk,
                    upstream_request_id=upstream_request_id,
                )
                provider_completed_record = await _record_provider_completed_before_finalization(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    cost_estimate=cost_estimate,
                    provider_response=provider_response,
                    request_id=request_id,
                    request=request,
                )
                try:
                    accounting_result = await _finalize_successful_chat_completion(
                        reservation=reservation,
                        authenticated_key=authenticated_key,
                        route=route,
                        policy_result=policy_result,
                        cost_estimate=cost_estimate,
                        provider_response=provider_response,
                        request_id=request_id,
                        request=request,
                        streaming=True,
                        provider_completed_usage_ledger_id=(
                            provider_completed_record.usage_ledger_id
                        ),
                    )
                except AccountingError as exc:
                    await _mark_provider_completed_finalization_failed(
                        usage_ledger_id=provider_completed_record.usage_ledger_id,
                        reservation_id=reservation.reservation_id,
                        error=exc,
                        request=request,
                    )
                    raise
                except QuotaError as exc:
                    await _mark_provider_completed_finalization_failed(
                        usage_ledger_id=provider_completed_record.usage_ledger_id,
                        reservation_id=reservation.reservation_id,
                        error=exc,
                        request=request,
                    )
                    raise
                _record_provider_success_metrics(
                    route=route,
                    provider_response=provider_response,
                    accounting_result=accounting_result,
                )
                provider_status = "success"
                if done_event is not None:
                    yield done_event
            else:
                await _record_provider_failure_and_release(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=ProviderError(
                        "Provider stream completed without final usage.",
                        provider=route.provider,
                        upstream_status_code=200 if completed else None,
                        error_code="stream_usage_missing",
                    ),
                    request=request,
                    streaming=True,
                )
                provider_status = "incomplete"
                yield format_openai_error_event(
                    message=(
                        "Provider stream completed without final usage metadata; "
                        "accounting could not finalize successfully."
                    ),
                    error_type="provider_error",
                    code="stream_usage_missing",
                    request_id=request_id,
                )
        except asyncio.CancelledError:
            with anyio.CancelScope(shield=True):
                await _release_streaming_reservation_after_error(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=ProviderError(
                        "Client disconnected during streaming response.",
                        provider=route.provider,
                        error_code="client_disconnected",
                    ),
                    request=request,
                )
            raise
        except ProviderError as exc:
            await _release_streaming_reservation_after_error(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                policy_result=policy_result,
                cost_estimate=cost_estimate,
                request_id=request_id,
                provider_error=exc,
                request=request,
            )
            yield format_openai_error_event(
                message=exc.safe_message,
                error_type=exc.error_type,
                code=exc.error_code,
            )
        except AccountingError as exc:
            increment_accounting_failure(exc.error_code)
            yield format_openai_error_event(
                message=exc.safe_message,
                error_type=exc.error_type,
                code=exc.error_code,
            )
        except QuotaError as exc:
            increment_quota_rejection(exc.error_code)
            yield format_openai_error_event(
                message=exc.safe_message,
                error_type=exc.error_type,
                code=exc.error_code,
            )
        finally:
            with anyio.CancelScope(shield=True):
                heartbeat_stop.set()
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                record_provider_call_result(
                    provider=route.provider,
                    endpoint="chat.completions",
                    status=provider_status,
                    duration_seconds=time.perf_counter() - start,
                )

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _reserve_redis_rate_limit(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    policy_result: ChatCompletionPolicyResult,
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
        exc = OpenAICompatibleError(
            "Rate limit service is unavailable.",
            status_code=503,
            error_type="server_error",
            code="redis_rate_limit_unavailable",
        )
        raise exc

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
    estimated_tokens = policy_result.estimated_input_tokens + policy_result.effective_output_tokens
    try:
        await service.check_and_reserve(
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_tokens=estimated_tokens,
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


def _start_rate_limit_heartbeat(
    reservation: _RateLimitReservation | None,
    *,
    stop_event: asyncio.Event,
) -> asyncio.Task[None] | None:
    if reservation is None or not reservation.concurrency_reserved:
        return None
    interval = reservation.policy.concurrency_heartbeat_seconds or 30
    return asyncio.create_task(
        _heartbeat_rate_limit_concurrency_loop(
            reservation,
            interval_seconds=interval,
            stop_event=stop_event,
        )
    )


async def _heartbeat_rate_limit_concurrency_loop(
    reservation: _RateLimitReservation,
    *,
    interval_seconds: int,
    stop_event: asyncio.Event,
) -> None:
    while True:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            try:
                await reservation.service.heartbeat_concurrency(
                    gateway_key_id=reservation.gateway_key_id,
                    request_id=reservation.request_id,
                    policy=reservation.policy,
                )
            except RateLimitError as exc:
                increment_rate_limit_heartbeat_failure(exc.error_code)


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


async def _reserve_chat_completion_quota(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ChatCompletionPolicyResult,
    request_id: str,
    request: Request | None,
    settings: Settings,
) -> _ChatCompletionQuotaReservation:
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
                endpoint="chat.completions",
            )
        except PricingError as exc:
            raise openai_error_from_pricing_error(exc) from exc

        gateway_keys_repository = GatewayKeysRepository(session)
        quota_service = QuotaService(
            gateway_keys_repository=gateway_keys_repository,
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
            increment_quota_rejection(exc.error_code)
            raise openai_error_from_quota_error(exc) from exc

        gateway_key = None
        try:
            gateway_key = await gateway_keys_repository.get_gateway_key_by_id(
                authenticated_key.gateway_key_id
            )
        except Exception:  # noqa: BLE001
            gateway_key = None
        live_burn_budget = _build_chat_streaming_live_burn_budget(
            authenticated_key=authenticated_key,
            gateway_key=gateway_key,
            reservation=reservation,
            cost_estimate=cost_estimate,
            settings=settings,
        )

        if hasattr(session, "commit"):
            await session.commit()
        return _ChatCompletionQuotaReservation(
            cost_estimate=cost_estimate,
            reservation=reservation,
            live_burn_budget=live_burn_budget,
        )
    finally:
        await session_iterator.aclose()


async def _resolve_chat_completion_route(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    effective_model: str,
    policy_result: ChatCompletionPolicyResult,
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
            )
            enforce_chat_completion_route_capabilities(
                policy_result.effective_body,
                route_capabilities=route.capabilities,
                route_supports_streaming=route.supports_streaming,
                requested_model=route.requested_model,
            )
        except RouteResolutionError as exc:
            raise openai_error_from_route_resolution_error(exc) from exc
        except RequestPolicyError as exc:
            raise openai_error_from_request_policy_error(exc) from exc
        return route
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
    request: Request | None,
    streaming: bool = False,
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
        kwargs = {
            "request_id": request_id,
            "error_type": provider_error.error_code,
            "error_code": provider_error.error_code,
            "status_code": provider_error.upstream_status_code,
        }
        if provider_error.diagnostic is not None:
            kwargs["provider_diagnostic"] = provider_error.diagnostic.to_safe_dict()
        if streaming:
            kwargs["streaming"] = True
        _record_provider_error_metrics(route=route, provider_error=provider_error)
        await accounting_service.record_provider_failure_and_release(
            reservation.reservation_id,
            authenticated_key,
            route,
            policy_result,
            cost_estimate,
            **kwargs,
        )
        if hasattr(session, "commit"):
            await session.commit()
        return
    finally:
        await session_iterator.aclose()


async def _release_streaming_reservation_after_error(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ChatCompletionPolicyResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    provider_error: ProviderError,
    request: Request | None,
) -> None:
    try:
        await _record_provider_failure_and_release(
            reservation=reservation,
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            cost_estimate=cost_estimate,
            request_id=request_id,
            provider_error=provider_error,
            request=request,
            streaming=True,
        )
    except AccountingError as accounting_exc:
        increment_accounting_failure(accounting_exc.error_code)
        raise
    except QuotaError as quota_exc:
        increment_quota_rejection(quota_exc.error_code)
        raise


async def _record_streaming_live_burn_abort_estimate(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    estimate: ChatStreamingLiveBurnEstimate,
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
        result = await accounting_service.record_streaming_live_burn_interrupted_estimate(
            reservation.reservation_id,
            authenticated_key,
            route,
            cost_estimate,
            request_id,
            estimated_input_tokens=cost_estimate.estimated_input_tokens,
            estimated_output_tokens=estimate.estimated_output_tokens,
            estimated_total_tokens=estimate.estimated_request_tokens,
            estimated_cost_eur=estimate.estimated_cost_eur,
            response_metadata=estimate.metadata,
            endpoint="chat.completions",
        )
        if hasattr(session, "commit"):
            await session.commit()
        return result
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
    request: Request | None,
    streaming: bool = False,
    provider_completed_usage_ledger_id: uuid.UUID | None = None,
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
        kwargs = {
            "request_id": request_id,
            "endpoint": "chat.completions",
        }
        if streaming:
            kwargs["streaming"] = True
        if provider_completed_usage_ledger_id is not None:
            kwargs["provider_completed_usage_ledger_id"] = provider_completed_usage_ledger_id
        result = await accounting_service.finalize_successful_response(
            reservation.reservation_id,
            authenticated_key,
            route,
            policy_result,
            cost_estimate,
            provider_response,
            **kwargs,
        )
        if hasattr(session, "commit"):
            await session.commit()
        usage_ledger_id = getattr(result, "usage_ledger_id", None)
        if isinstance(usage_ledger_id, uuid.UUID):
            await _record_usage_profile_after_finalization(
                usage_ledger_id=usage_ledger_id,
                route=route,
                policy_result=policy_result,
                authenticated_key=authenticated_key,
                request=request,
            )
        return result
    finally:
        await session_iterator.aclose()


async def _record_usage_profile_after_finalization(
    *,
    usage_ledger_id: uuid.UUID,
    route: RouteResolutionResult,
    policy_result: ChatCompletionPolicyResult,
    authenticated_key: AuthenticatedGatewayKey,
    request: Request | None,
) -> None:
    """Persist advisory usage profile metadata without affecting responses."""
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration:
        logger.warning(
            "usage_profile.record_skipped",
            reason="database_session_unavailable",
            usage_ledger_id=str(usage_ledger_id),
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "usage_profile.record_failed",
            reason="database_session_error",
            usage_ledger_id=str(usage_ledger_id),
            error=exc.__class__.__name__,
        )
        return

    try:
        service = UsageProfileService(
            usage_ledger_repository=UsageLedgerRepository(session),
            usage_profiles_repository=UsageProfilesRepository(session),
        )
        await service.record_from_usage_ledger(
            usage_ledger_id,
            route=route,
            tool_metadata=build_chat_completion_tool_metadata(policy_result.effective_body),
            profile_metadata=_usage_profile_policy_metadata(
                authenticated_key=authenticated_key,
                effective_body=policy_result.effective_body,
            ),
        )
        if hasattr(session, "commit"):
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "usage_profile.record_failed",
            reason="profile_insert_failed",
            usage_ledger_id=str(usage_ledger_id),
            provider=route.provider,
            requested_model=route.requested_model,
            error=exc.__class__.__name__,
        )
    finally:
        await session_iterator.aclose()


def _usage_profile_policy_metadata(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    effective_body: Mapping[str, object],
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "key_purpose": authenticated_key.key_purpose,
        "capability_policy_mode": authenticated_key.capability_policy_mode,
    }
    if authenticated_key.key_purpose == "trusted_calibration":
        from slaif_gateway.services.hosted_tool_policy import (
            summarize_chat_completion_hosted_capabilities,
        )

        metadata.update(
            summarize_chat_completion_hosted_capabilities(
                effective_body,
                requested_model=str(effective_body.get("model") or ""),
            )
        )
    return metadata


async def _record_provider_completed_before_finalization(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
    request: Request | None,
):
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
        result = await accounting_service.record_provider_completed_before_finalization(
            reservation.reservation_id,
            authenticated_key,
            route,
            cost_estimate,
            provider_response,
            request_id=request_id,
            endpoint="chat.completions",
            streaming=True,
        )
        if hasattr(session, "commit"):
            await session.commit()
        return result
    finally:
        await session_iterator.aclose()


async def _mark_provider_completed_finalization_failed(
    *,
    usage_ledger_id: uuid.UUID,
    reservation_id: uuid.UUID,
    error: Exception,
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
        await accounting_service.mark_provider_completed_finalization_failed(
            usage_ledger_id,
            reservation_id,
            error,
        )
        if hasattr(session, "commit"):
            await session.commit()
    finally:
        await session_iterator.aclose()


def _build_chat_streaming_live_burn_budget(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    gateway_key: object | None,
    reservation: QuotaReservationResult,
    cost_estimate: ChatCostEstimate,
    settings: Settings,
) -> ChatStreamingLiveBurnBudget | None:
    policy = _chat_streaming_live_burn_policy_from_key(
        authenticated_key=authenticated_key,
        gateway_key=gateway_key,
        settings=settings,
    )
    cost_limit = getattr(gateway_key, "cost_limit_eur", authenticated_key.cost_limit_eur)
    token_limit = getattr(gateway_key, "token_limit_total", authenticated_key.token_limit_total)
    cost_used = getattr(gateway_key, "cost_used_eur", authenticated_key.cost_used_eur)
    tokens_used = getattr(gateway_key, "tokens_used_total", authenticated_key.tokens_used_total)
    cost_reserved = getattr(
        gateway_key,
        "cost_reserved_eur",
        authenticated_key.cost_reserved_eur + reservation.reserved_cost_eur,
    )
    tokens_reserved = getattr(
        gateway_key,
        "tokens_reserved_total",
        authenticated_key.tokens_reserved_total + reservation.reserved_tokens,
    )
    return build_chat_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=cost_limit,
        token_limit_total=token_limit,
        cost_used_eur=cost_used,
        tokens_used_total=tokens_used,
        cost_reserved_eur=cost_reserved,
        tokens_reserved_total=tokens_reserved,
        current_reserved_cost_eur=reservation.reserved_cost_eur,
        current_reserved_tokens=reservation.reserved_tokens,
        cost_estimate=cost_estimate,
        estimate_multiplier=settings.CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER,
    )


def _chat_streaming_live_burn_policy_from_key(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    gateway_key: object | None,
    settings: Settings,
) -> ChatStreamingLiveBurnPolicy:
    metadata = getattr(gateway_key, "metadata_json", None)
    if isinstance(metadata, Mapping):
        try:
            return chat_streaming_live_burn_policy_from_metadata(
                metadata,
                max_abs_cost_margin_eur=(
                    settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                ),
                max_abs_token_margin=settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError:
            return default_chat_streaming_live_burn_policy()
    policy = authenticated_key.chat_streaming_live_burn_policy
    if isinstance(policy, Mapping):
        try:
            return chat_streaming_live_burn_policy_from_metadata(
                {"chat_streaming_live_burn": dict(policy)},
                max_abs_cost_margin_eur=(
                    settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                ),
                max_abs_token_margin=settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError:
            return default_chat_streaming_live_burn_policy()
    return default_chat_streaming_live_burn_policy()


def _provider_response_from_stream(
    *,
    route: RouteResolutionResult,
    chunk: ProviderStreamChunk,
    upstream_request_id: str | None,
) -> ProviderResponse:
    return ProviderResponse(
        provider=chunk.provider,
        upstream_model=chunk.upstream_model,
        status_code=200,
        json_body=dict(chunk.json_body or {}),
        upstream_request_id=upstream_request_id or chunk.upstream_request_id,
        usage=chunk.usage,
        raw_cost_native=chunk.raw_cost_native,
        native_currency=chunk.native_currency,
        headers={},
    )


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


def _record_provider_success_metrics(
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
            token_type="completion",
            count=usage.completion_tokens,
        )
        add_tokens(
            provider=route.provider,
            model=route.resolved_model,
            token_type="total",
            count=usage.total_tokens,
        )
    add_cost_eur(
        provider=route.provider,
        model=route.resolved_model,
        cost_eur=getattr(accounting_result, "actual_cost_eur", None),
    )


def _record_provider_error_metrics(
    *,
    route: RouteResolutionResult,
    provider_error: ProviderError,
) -> None:
    if isinstance(provider_error, ProviderHTTPError):
        increment_provider_http_error(
            provider=route.provider,
            endpoint="chat.completions",
            upstream_status_code=provider_error.upstream_status_code,
        )
    if provider_error.diagnostic is not None:
        increment_provider_diagnostic_generated(
            provider=route.provider,
            endpoint="chat.completions",
        )
