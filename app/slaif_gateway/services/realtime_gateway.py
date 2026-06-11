"""Orchestration for the narrow Realtime client-secret RC2 foundation."""

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
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.realtime import RealtimePolicyResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.realtime_request_policy import RealtimeRequestPolicy
from slaif_gateway.services.realtime_route_capabilities import (
    enforce_realtime_route_capabilities,
)
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_payloads import (
    build_realtime_client_secret_upstream_body,
)
from slaif_gateway.services.upstream_request_contracts import (
    normalize_realtime_client_secret_upstream_request,
)

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check

REALTIME_CLIENT_SECRETS_ENDPOINT = "/v1/realtime/client_secrets"
REALTIME_CLIENT_SECRETS_PROVIDER_ENDPOINT = "realtime.client_secrets"


async def handle_realtime_client_secret_create(
    *,
    payload: dict[str, Any],
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = dict(payload)
    policy_service = RealtimeRequestPolicy(settings)
    try:
        policy_result = policy_service.apply_client_secret_create(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    session_body = dict(policy_result.effective_body["session"])
    route = await _resolve_realtime_route(
        authenticated_key=authenticated_key,
        requested_model=str(session_body["model"]),
        request=request,
    )
    upstream_body = _build_safe_realtime_upstream_body(
        policy_result.effective_body,
        resolved_model=route.resolved_model,
    )

    try:
        direct_provider_exposure_required = _requires_direct_provider_exposure_acceptance(
            authenticated_key
        )
        enforce_realtime_route_capabilities(
            route_capabilities=route.capabilities,
            transcription_requested=session_body["type"] == "transcription",
            direct_provider_exposure_required=direct_provider_exposure_required,
        )
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    reservation, cost_estimate = await _reserve_realtime_quota(
        authenticated_key=authenticated_key,
        route=route,
        policy_result=policy_result,
        request_id=request_id,
        request=request,
        admission_pricing_only=direct_provider_exposure_required,
    )

    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint=REALTIME_CLIENT_SECRETS_PROVIDER_ENDPOINT,
        body=upstream_body,
        request_id=request_id,
    )
    adapter = get_provider_adapter(route, settings)
    try:
        provider_response = await observe_provider_call(
            provider=route.provider,
            endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
            call=lambda: adapter.create_realtime_client_secret(provider_request),
        )
    except ProviderError as exc:
        await _record_realtime_provider_failure(
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

    accounting_result = await _finalize_realtime_success(
        reservation=reservation,
        authenticated_key=authenticated_key,
        route=route,
        policy_result=policy_result,
        cost_estimate=cost_estimate,
        provider_response=provider_response,
        request_id=request_id,
        request=request,
        admission_pricing_only=direct_provider_exposure_required,
    )
    _record_realtime_success_metrics(route=route, accounting_result=accounting_result)
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
        headers=dict(provider_response.headers),
    )


async def _resolve_realtime_route(
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
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
            )
        except RouteResolutionError as exc:
            raise openai_error_from_route_resolution_error(exc) from exc
    raise _database_session_unavailable_error()


async def _reserve_realtime_quota(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: RealtimePolicyResult,
    request_id: str,
    request: Request | None,
    admission_pricing_only: bool,
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
            cost_estimate = await pricing.estimate_realtime_client_secret_cost(
                route=route,
                policy=policy_result,
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
                admission_pricing_only=admission_pricing_only,
            )
            reservation = await quota.reserve_for_chat_completion(
                authenticated_key=authenticated_key,
                route=route,
                policy=policy_result,
                cost_estimate=cost_estimate,
                request_id=request_id,
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
            )
            await session.commit()
            return reservation, cost_estimate
        except PricingError as exc:
            raise openai_error_from_pricing_error(exc) from exc
        except QuotaError as exc:
            raise openai_error_from_quota_error(exc) from exc
    raise _database_session_unavailable_error()


async def _record_realtime_provider_failure(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: RealtimePolicyResult,
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
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
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


async def _finalize_realtime_success(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: RealtimePolicyResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
    request: Request | None,
    admission_pricing_only: bool,
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
                    endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
                )
                await session.commit()
                return result

            usage = ActualUsage(
                prompt_tokens=policy_result.estimated_input_tokens,
                completion_tokens=policy_result.effective_output_tokens,
                total_tokens=policy_result.estimated_input_tokens + policy_result.effective_output_tokens,
                other_usage={},
            )
            session_body = dict(policy_result.effective_body["session"])
            audio_body = session_body.get("audio", {})
            input_body = audio_body.get("input", {}) if isinstance(audio_body, dict) else {}
            output_body = audio_body.get("output", {}) if isinstance(audio_body, dict) else {}

            result = await service.finalize_successful_custom_response(
                reservation.reservation_id,
                authenticated_key,
                route,
                cost_estimate,
                provider_response,
                request_id,
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
                usage=usage,
                actual_cost_eur=cost_estimate.estimated_total_cost_eur,
                actual_cost_native=cost_estimate.estimated_total_cost_native,
                native_currency=cost_estimate.native_currency,
                cost_source="slaif_realtime_session_admission",
                cost_confidence="estimated_realtime_session_admission",
                component_costs_native={"admission": cost_estimate.estimated_total_cost_native},
                component_token_counts={
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                },
                response_metadata_extra={
                    "provider_usage_available": False,
                    "estimate_is_invoice_grade": False,
                    "realtime_estimate_reason": "realtime_client_secret_issued",
                    "realtime_direct_provider_exposure_admission": admission_pricing_only,
                    "session_type": session_body.get("type"),
                    "output_modalities": list(session_body.get("output_modalities", [])),
                    "audio_input_format": input_body.get("format", {}).get("type")
                    if isinstance(input_body, dict)
                    else None,
                    "audio_output_format": output_body.get("format", {}).get("type")
                    if isinstance(output_body, dict)
                    else None,
                    "audio_output_voice": output_body.get("voice")
                    if isinstance(output_body, dict)
                    else None,
                    "expires_after_seconds": policy_result.effective_body["expires_after"]["seconds"],
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


def _build_safe_realtime_upstream_body(
    effective_body: dict[str, Any],
    *,
    resolved_model: str,
) -> dict[str, Any]:
    session = effective_body.get("session")
    if not isinstance(session, dict):
        raise OpenAICompatibleError(
            "Realtime client-secret request is missing session configuration.",
            status_code=500,
            error_type="server_error",
            code="realtime_request_contract_invalid",
        )
    normalized_request = normalize_realtime_client_secret_upstream_request(
        effective_body,
        requested_model=str(session["model"]),
        upstream_model=resolved_model,
    )
    return build_realtime_client_secret_upstream_body(normalized_request)


def _record_realtime_success_metrics(
    *,
    route: RouteResolutionResult,
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


def _request_id_from_request(request: Request | None) -> str:
    if request is None:
        return uuid.uuid4().hex
    header_name = request.app.state.settings.REQUEST_ID_HEADER
    header_value = request.headers.get(header_name)
    if header_value and header_value.strip():
        return header_value.strip()
    return uuid.uuid4().hex


def _requires_direct_provider_exposure_acceptance(
    authenticated_key: AuthenticatedGatewayKey,
) -> bool:
    return any(
        limit is not None
        for limit in (
            authenticated_key.cost_limit_eur,
            authenticated_key.token_limit_total,
            authenticated_key.request_limit_total,
        )
    )


async def _db_session_iterator(request: Request | None):
    dependency = (
        get_db_session_after_auth_header_check
        if request is None
        else _get_db_session_after_auth_header_check
    )
    if request is None:
        async for session in dependency():
            yield session
        return
    async for session in dependency(request):
        yield session


def _database_session_unavailable_error() -> OpenAICompatibleError:
    return OpenAICompatibleError(
        "Database session dependency is unavailable.",
        status_code=500,
        error_type="server_error",
        code="database_session_unavailable",
    )
