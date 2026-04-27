"""Orchestration for OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

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
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.metrics import (
    add_tokens,
    increment_accounting_failure,
    increment_quota_rejection,
    increment_rate_limit_heartbeat_failure,
    increment_rate_limit_rejection,
    increment_rate_limit_release_failure,
    observe_provider_call,
    record_provider_call_result,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderStreamChunk
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
from slaif_gateway.services.rate_limit_errors import RateLimitError
from slaif_gateway.services.rate_limit_errors import RedisRateLimitUnavailableError
from slaif_gateway.services.rate_limit_policy import build_rate_limit_policy
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.providers.streaming import format_openai_error_event

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check


@dataclass(slots=True)
class _RateLimitReservation:
    service: RedisRateLimitService
    policy: RateLimitPolicy
    gateway_key_id: uuid.UUID
    request_id: str
    concurrency_reserved: bool


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
        policy_result = policy.apply(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    rate_limit_reservation = await _reserve_redis_rate_limit(
        authenticated_key=authenticated_key,
        policy_result=policy_result,
        request_id=request_id,
        settings=settings,
        request=request,
    )
    try:
        route, cost_estimate, reservation = await _reserve_chat_completion_quota(
            authenticated_key=authenticated_key,
            effective_model=policy_result.effective_body["model"],
            policy_result=policy_result,
            request_id=request_id,
            request=request,
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
            body=dict(policy_result.effective_body),
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
            await _finalize_successful_chat_completion(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                policy_result=policy_result,
                cost_estimate=cost_estimate,
                provider_response=provider_response,
                request_id=request_id,
                request=request,
            )
            _record_provider_usage_metrics(route=route, provider_response=provider_response)
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
) -> StreamingResponse:
    adapter = get_provider_adapter(route, settings)
    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint="chat.completions",
        body=dict(policy_result.effective_body),
        request_id=request_id,
    )

    async def _events():
        start = time.perf_counter()
        usage_chunk: ProviderStreamChunk | None = None
        upstream_request_id: str | None = None
        done_event: str | None = None
        completed = False
        provider_status = "error"
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
                    await _finalize_successful_chat_completion(
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
                _record_provider_usage_metrics(route=route, provider_response=provider_response)
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
                if done_event is not None:
                    yield done_event
        except asyncio.CancelledError:
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
    effective_model: str,
    policy_result: ChatCompletionPolicyResult,
    request_id: str,
    request: Request | None,
) -> tuple[RouteResolutionResult, ChatCostEstimate, QuotaReservationResult]:
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
            increment_quota_rejection(exc.error_code)
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
        if streaming:
            kwargs["streaming"] = True
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
            "endpoint": "chat.completions",
        }
        if streaming:
            kwargs["streaming"] = True
        if provider_completed_usage_ledger_id is not None:
            kwargs["provider_completed_usage_ledger_id"] = provider_completed_usage_ledger_id
        await accounting_service.finalize_successful_response(
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
        return
    finally:
        await session_iterator.aclose()


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


def _record_provider_usage_metrics(
    *,
    route: RouteResolutionResult,
    provider_response: ProviderResponse,
) -> None:
    usage = provider_response.usage
    if usage is None:
        return
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
