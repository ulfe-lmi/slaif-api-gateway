"""Orchestration for standalone OpenAI-compatible Audio API endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.responses import JSONResponse, Response
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
from slaif_gateway.schemas.audio import AudioPolicyResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError, UsageMissingError
from slaif_gateway.services.audio_request_policy import AudioRequestPolicy
from slaif_gateway.services.audio_route_capabilities import enforce_audio_route_capabilities
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_payloads import (
    build_audio_speech_upstream_body,
    build_audio_transcription_upstream_body,
    build_audio_translation_upstream_body,
)
from slaif_gateway.services.upstream_request_contracts import (
    normalize_audio_speech_upstream_request,
    normalize_audio_transcription_upstream_request,
    normalize_audio_translation_upstream_request,
)

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check

AUDIO_SPEECH_ENDPOINT = "/v1/audio/speech"
AUDIO_TRANSCRIPTIONS_ENDPOINT = "/v1/audio/transcriptions"
AUDIO_TRANSLATIONS_ENDPOINT = "/v1/audio/translations"


async def handle_audio_speech(
    *,
    payload: dict[str, Any],
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = dict(payload)
    policy_service = AudioRequestPolicy(settings)
    try:
        policy_result = policy_service.apply_speech(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc
    route = await _resolve_audio_route(
        endpoint=AUDIO_SPEECH_ENDPOINT,
        authenticated_key=authenticated_key,
        requested_model=str(policy_result.effective_body["model"]),
        request=request,
    )
    upstream_body = _build_safe_audio_speech_upstream_body(
        policy_result.effective_body,
        resolved_model=route.resolved_model,
    )
    return await _handle_audio_operation(
        endpoint=AUDIO_SPEECH_ENDPOINT,
        provider_endpoint="audio.speech",
        authenticated_key=authenticated_key,
        route=route,
        settings=settings,
        request=request,
        policy_result=policy_result,
        provider_request_body=upstream_body,
        upload_files=None,
    )


async def handle_audio_transcription(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None,
):
    if request is None:
        raise OpenAICompatibleError(
            "Multipart request context is required.",
            status_code=500,
            error_type="server_error",
            code="request_context_missing",
        )
    form = await request.form()
    policy_service = AudioRequestPolicy(settings)
    try:
        policy_result, upload = await policy_service.apply_transcription(form)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc
    route = await _resolve_audio_route(
        endpoint=AUDIO_TRANSCRIPTIONS_ENDPOINT,
        authenticated_key=authenticated_key,
        requested_model=str(policy_result.effective_body["model"]),
        request=request,
    )
    upstream_body = _build_safe_audio_transcription_upstream_body(
        policy_result.effective_body,
        resolved_model=route.resolved_model,
    )
    return await _handle_audio_operation(
        endpoint=AUDIO_TRANSCRIPTIONS_ENDPOINT,
        provider_endpoint="audio.transcriptions",
        authenticated_key=authenticated_key,
        route=route,
        settings=settings,
        request=request,
        policy_result=policy_result,
        provider_request_body=upstream_body,
        upload_files={"file": upload},
    )


async def handle_audio_translation(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None,
):
    if request is None:
        raise OpenAICompatibleError(
            "Multipart request context is required.",
            status_code=500,
            error_type="server_error",
            code="request_context_missing",
        )
    form = await request.form()
    policy_service = AudioRequestPolicy(settings)
    try:
        policy_result, upload = await policy_service.apply_translation(form)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc
    route = await _resolve_audio_route(
        endpoint=AUDIO_TRANSLATIONS_ENDPOINT,
        authenticated_key=authenticated_key,
        requested_model=str(policy_result.effective_body["model"]),
        request=request,
    )
    upstream_body = _build_safe_audio_translation_upstream_body(
        policy_result.effective_body,
        resolved_model=route.resolved_model,
    )
    return await _handle_audio_operation(
        endpoint=AUDIO_TRANSLATIONS_ENDPOINT,
        provider_endpoint="audio.translations",
        authenticated_key=authenticated_key,
        route=route,
        settings=settings,
        request=request,
        policy_result=policy_result,
        provider_request_body=upstream_body,
        upload_files={"file": upload},
    )


async def _handle_audio_operation(
    *,
    endpoint: str,
    provider_endpoint: str,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    settings: Settings,
    request: Request | None,
    policy_result: AudioPolicyResult,
    provider_request_body: dict[str, Any],
    upload_files,
):
    request_id = _request_id_from_request(request)

    try:
        enforce_audio_route_capabilities(endpoint=endpoint, route_capabilities=route.capabilities)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc
    _ensure_resolved_audio_model_allowed(endpoint=endpoint, resolved_model=route.resolved_model, settings=settings)

    reservation, cost_estimate = await _reserve_audio_quota(
        endpoint=endpoint,
        authenticated_key=authenticated_key,
        route=route,
        policy_result=policy_result,
        request_id=request_id,
        request=request,
    )

    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint=provider_endpoint,
        body=provider_request_body,
        files={
            name: _provider_upload(upload)
            for name, upload in (upload_files or {}).items()
        }
        or None,
        request_id=request_id,
    )
    adapter = get_provider_adapter(route, settings)
    try:
        provider_response = await observe_provider_call(
            provider=route.provider,
            endpoint=endpoint,
            call=lambda: _call_audio_provider(
                adapter=adapter,
                provider_endpoint=provider_endpoint,
                provider_request=provider_request,
            ),
        )
    except ProviderError as exc:
        await _record_audio_provider_failure(
            endpoint=endpoint,
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

    accounting_result = await _finalize_audio_success(
        endpoint=endpoint,
        reservation=reservation,
        authenticated_key=authenticated_key,
        route=route,
        policy_result=policy_result,
        cost_estimate=cost_estimate,
        provider_response=provider_response,
        request_id=request_id,
        request=request,
    )
    _record_audio_success_metrics(route=route, provider_response=provider_response, accounting_result=accounting_result)
    return _audio_response(provider_response, default_content_type=policy_result.content_type)


async def _call_audio_provider(*, adapter, provider_endpoint: str, provider_request: ProviderRequest):
    if provider_endpoint == "audio.speech":
        return await adapter.create_speech(provider_request)
    if provider_endpoint == "audio.transcriptions":
        return await adapter.create_transcription(provider_request)
    if provider_endpoint == "audio.translations":
        return await adapter.create_translation(provider_request)
    raise OpenAICompatibleError(
        "Standalone Audio API provider endpoint is not configured.",
        status_code=500,
        error_type="server_error",
        code="audio_provider_endpoint_invalid",
    )


async def _resolve_audio_route(
    *,
    endpoint: str,
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
                endpoint=endpoint,
            )
        except RouteResolutionError as exc:
            raise openai_error_from_route_resolution_error(exc) from exc
    raise _database_session_unavailable_error()


async def _reserve_audio_quota(
    *,
    endpoint: str,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: AudioPolicyResult,
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
            cost_estimate = await pricing.estimate_audio_operation_cost(
                route=route,
                policy=policy_result,
                endpoint=endpoint,
            )
            reservation = await quota.reserve_for_chat_completion(
                authenticated_key=authenticated_key,
                route=route,
                policy=policy_result,
                cost_estimate=cost_estimate,
                request_id=request_id,
                endpoint=endpoint,
            )
            await session.commit()
            return reservation, cost_estimate
        except PricingError as exc:
            raise openai_error_from_pricing_error(exc) from exc
        except QuotaError as exc:
            raise openai_error_from_quota_error(exc) from exc
    raise _database_session_unavailable_error()


async def _record_audio_provider_failure(
    *,
    endpoint: str,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: AudioPolicyResult,
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
                policy_result,
                cost_estimate,
                request_id,
                error_type=provider_error.error_type,
                endpoint=endpoint,
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


async def _finalize_audio_success(
    *,
    endpoint: str,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: AudioPolicyResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
    request: Request | None,
) -> FinalizedAccountingResult:
    async for session in _db_session_iterator(request):
        service = AccountingService(session)
        try:
            if provider_response.usage is not None and cost_estimate.request_price is None:
                result = await service.finalize_successful_response(
                    reservation.reservation_id,
                    authenticated_key,
                    route,
                    policy_result,  # type: ignore[arg-type]
                    cost_estimate,
                    provider_response,
                    request_id,
                    endpoint=endpoint,
                )
                await session.commit()
                return result

            usage = (
                service.extract_usage(provider_response)
                if provider_response.usage is not None
                else ActualUsage(
                    prompt_tokens=policy_result.estimated_input_tokens,
                    completion_tokens=0,
                    total_tokens=policy_result.estimated_input_tokens,
                    other_usage={},
                )
            )
            if cost_estimate.request_price is not None:
                actual_cost_native = cost_estimate.request_price
                actual_cost_eur = cost_estimate.estimated_total_cost_eur
                cost_source = "request_price"
                cost_confidence = "configured_request_price"
                metadata = {
                    "provider_usage_available": provider_response.usage is not None,
                    "audio_request_priced": True,
                }
            elif endpoint == AUDIO_SPEECH_ENDPOINT:
                actual_cost_native = cost_estimate.estimated_total_cost_native
                actual_cost_eur = cost_estimate.estimated_total_cost_eur
                cost_source = "slaif_estimated_input_pricing"
                cost_confidence = "estimated_from_speech_input"
                metadata = {
                    "provider_usage_available": False,
                    "audio_estimate_reason": "speech_usage_missing_estimated",
                }
            else:
                raise UsageMissingError()

            result = await service.finalize_successful_custom_response(
                reservation.reservation_id,
                authenticated_key,
                route,
                cost_estimate,
                provider_response,
                request_id,
                endpoint=endpoint,
                usage=usage,
                actual_cost_eur=actual_cost_eur,
                actual_cost_native=actual_cost_native,
                native_currency=cost_estimate.native_currency,
                cost_source=cost_source,
                cost_confidence=cost_confidence,
                component_costs_native={"request": actual_cost_native},
                component_token_counts={
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                },
                response_metadata_extra=metadata,
                streaming=False,
            )
            await session.commit()
            return result
        except AccountingError as exc:
            raise openai_error_from_accounting_error(exc) from exc
        except QuotaError as exc:
            raise openai_error_from_quota_error(exc) from exc
    raise _database_session_unavailable_error()


def _audio_response(provider_response: ProviderResponse, *, default_content_type: str | None):
    headers = dict(provider_response.headers)
    content_type = provider_response.content_type or default_content_type
    if provider_response.binary_body is not None:
        return Response(
            content=provider_response.binary_body,
            status_code=provider_response.status_code,
            media_type=content_type,
            headers=headers,
        )
    if provider_response.text_body is not None:
        return Response(
            content=provider_response.text_body,
            status_code=provider_response.status_code,
            media_type=content_type,
            headers=headers,
        )
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
        headers=headers,
    )


def _provider_upload(upload):
    from slaif_gateway.schemas.providers import ProviderFileUpload

    return ProviderFileUpload(
        filename=upload.filename,
        content_type=upload.content_type,
        data=upload.data,
    )


def _build_safe_audio_speech_upstream_body(
    effective_body: dict[str, Any],
    *,
    resolved_model: str,
) -> dict[str, Any]:
    normalized_request = normalize_audio_speech_upstream_request(
        effective_body,
        requested_model=str(effective_body["model"]),
        upstream_model=resolved_model,
    )
    return build_audio_speech_upstream_body(normalized_request)


def _build_safe_audio_transcription_upstream_body(
    effective_body: dict[str, Any],
    *,
    resolved_model: str,
) -> dict[str, Any]:
    normalized_request = normalize_audio_transcription_upstream_request(
        effective_body,
        requested_model=str(effective_body["model"]),
        upstream_model=resolved_model,
    )
    return build_audio_transcription_upstream_body(normalized_request)


def _build_safe_audio_translation_upstream_body(
    effective_body: dict[str, Any],
    *,
    resolved_model: str,
) -> dict[str, Any]:
    normalized_request = normalize_audio_translation_upstream_request(
        effective_body,
        requested_model=str(effective_body["model"]),
        upstream_model=resolved_model,
    )
    return build_audio_translation_upstream_body(normalized_request)


def _ensure_resolved_audio_model_allowed(
    *,
    endpoint: str,
    resolved_model: str,
    settings: Settings,
) -> None:
    if endpoint == AUDIO_SPEECH_ENDPOINT:
        allowed_models = _csv_set(settings.AUDIO_SPEECH_ALLOWED_MODELS)
    elif endpoint == AUDIO_TRANSCRIPTIONS_ENDPOINT:
        allowed_models = _csv_set(settings.AUDIO_TRANSCRIPTION_ALLOWED_MODELS)
    elif endpoint == AUDIO_TRANSLATIONS_ENDPOINT:
        allowed_models = _csv_set(settings.AUDIO_TRANSLATION_ALLOWED_MODELS)
    else:
        raise OpenAICompatibleError(
            "Standalone Audio API endpoint is not configured.",
            status_code=500,
            error_type="server_error",
            code="audio_endpoint_not_configured",
        )
    if resolved_model not in allowed_models:
        raise OpenAICompatibleError(
            "The resolved standalone Audio API model is not allowed by the configured policy.",
            status_code=400,
            error_type="invalid_request_error",
            code="audio_model_not_supported",
            param="model",
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


def _csv_set(raw_value: str) -> set[str]:
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def _record_audio_success_metrics(
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
    else:
        add_tokens(
            provider=route.provider,
            model=route.resolved_model,
            token_type="prompt",
            count=accounting_result.prompt_tokens,
        )
    add_cost_eur(
        provider=route.provider,
        model=route.resolved_model,
        cost_eur=accounting_result.actual_cost_eur,
    )
