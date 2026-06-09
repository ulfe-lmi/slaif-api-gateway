"""Orchestration for stateless text-output OpenAI-compatible Responses."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import anyio
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import StreamingResponse

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
from slaif_gateway.db.models import ConversationReference, ResponseReference
from slaif_gateway.db.repositories.conversation_references import ConversationReferencesRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.response_references import ResponseReferencesRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.metrics import (
    add_cost_eur,
    add_tokens,
    increment_accounting_failure,
    increment_provider_http_error,
    increment_quota_rejection,
    increment_rate_limit_heartbeat_failure,
    increment_rate_limit_rejection,
    increment_rate_limit_release_failure,
    observe_provider_call,
    record_provider_call_result,
)
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.providers.streaming import format_responses_error_event
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.schemas.policy import ResponsesPolicyResult
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
from slaif_gateway.services.rate_limit_errors import RateLimitError, RedisRateLimitUnavailableError
from slaif_gateway.services.rate_limit_policy import build_rate_limit_policy
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy
from slaif_gateway.services.responses_request_policy import (
    TEXT_FORMAT_JSON_OBJECT,
    TEXT_FORMAT_JSON_SCHEMA,
    conversation_requested,
    previous_response_id_requested,
    responses_custom_tools_requested,
    responses_file_input_requested,
    responses_function_tools_requested,
    responses_image_input_requested,
    responses_text_format_type,
    validate_conversation_items_create_body,
    validate_conversation_update_body,
)
from slaif_gateway.services.responses_route_capabilities import (
    enforce_responses_route_capabilities,
)
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_request_contracts import (
    normalize_conversation_update_upstream_request,
    normalize_conversation_items_create_upstream_request,
    normalize_conversation_items_query_request,
    normalize_responses_compact_upstream_request,
    normalize_responses_input_tokens_upstream_request,
    normalize_responses_upstream_request,
)
from slaif_gateway.services.upstream_payloads import (
    build_conversation_update_upstream_body,
    build_conversation_items_create_upstream_body,
    build_conversation_items_query_params,
    build_responses_compact_upstream_body,
    build_responses_input_items_query_params,
    build_responses_input_tokens_upstream_body,
    build_responses_upstream_body,
)

RESPONSES_ENDPOINT = "/v1/responses"
RESPONSES_PROVIDER_ENDPOINT = "responses"
RESPONSES_INPUT_TOKENS_ENDPOINT = "/v1/responses/input_tokens"
RESPONSES_INPUT_TOKENS_PROVIDER_ENDPOINT = "responses.input_tokens"
RESPONSES_COMPACT_ENDPOINT = "/v1/responses/compact"
RESPONSES_COMPACT_PROVIDER_ENDPOINT = "responses.compact"
RESPONSES_RETRIEVE_ENDPOINT = "GET /v1/responses/{response_id}"
RESPONSES_DELETE_ENDPOINT = "DELETE /v1/responses/{response_id}"
RESPONSES_INPUT_ITEMS_ENDPOINT = "GET /v1/responses/{response_id}/input_items"
RESPONSES_RETRIEVE_PROVIDER_ENDPOINT = "responses.retrieve"
RESPONSES_DELETE_PROVIDER_ENDPOINT = "responses.delete"
RESPONSES_INPUT_ITEMS_PROVIDER_ENDPOINT = "responses.input_items"
CONVERSATIONS_CREATE_ENDPOINT = "/v1/conversations"
CONVERSATIONS_UPDATE_ENDPOINT = "POST /v1/conversations/{conversation_id}"
CONVERSATIONS_RETRIEVE_ENDPOINT = "GET /v1/conversations/{conversation_id}"
CONVERSATIONS_DELETE_ENDPOINT = "DELETE /v1/conversations/{conversation_id}"
CONVERSATIONS_CREATE_PROVIDER_ENDPOINT = "conversations.create"
CONVERSATIONS_UPDATE_PROVIDER_ENDPOINT = "conversations.update"
CONVERSATIONS_RETRIEVE_PROVIDER_ENDPOINT = "conversations.retrieve"
CONVERSATIONS_DELETE_PROVIDER_ENDPOINT = "conversations.delete"
CONVERSATION_ITEMS_CREATE_ENDPOINT = "POST /v1/conversations/{conversation_id}/items"
CONVERSATION_ITEMS_LIST_ENDPOINT = "GET /v1/conversations/{conversation_id}/items"
CONVERSATION_ITEMS_RETRIEVE_ENDPOINT = "GET /v1/conversations/{conversation_id}/items/{item_id}"
CONVERSATION_ITEMS_DELETE_ENDPOINT = "DELETE /v1/conversations/{conversation_id}/items/{item_id}"
CONVERSATION_ITEMS_CREATE_PROVIDER_ENDPOINT = "conversations.items.create"
CONVERSATION_ITEMS_LIST_PROVIDER_ENDPOINT = "conversations.items.list"
CONVERSATION_ITEMS_RETRIEVE_PROVIDER_ENDPOINT = "conversations.items.retrieve"
CONVERSATION_ITEMS_DELETE_PROVIDER_ENDPOINT = "conversations.items.delete"
_RESPONSES_INPUT_ITEMS_ALLOWED_QUERY_KEYS = frozenset({"after", "include", "include[]", "limit", "order"})
_RESPONSES_INPUT_ITEMS_ALLOWED_INCLUDE_VALUES = frozenset({"message.input_image.image_url"})
_CONVERSATION_ITEMS_ALLOWED_QUERY_KEYS = frozenset(
    {"after", "before", "include", "include[]", "limit", "order"}
)
_CONVERSATION_ITEMS_ALLOWED_INCLUDE_VALUES = frozenset({"message.input_image.image_url"})

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


def _build_safe_responses_input_tokens_upstream_body(
    *,
    policy_result: ResponsesPolicyResult,
    upstream_model: str,
) -> dict[str, object]:
    try:
        normalized_request = normalize_responses_input_tokens_upstream_request(
            policy_result.effective_body,
            requested_model=policy_result.effective_body["model"],
            upstream_model=upstream_model,
        )
        return build_responses_input_tokens_upstream_body(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Request contains fields that are not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


def _build_safe_responses_compact_upstream_body(
    *,
    policy_result: ResponsesPolicyResult,
    upstream_model: str,
) -> dict[str, object]:
    try:
        normalized_request = normalize_responses_compact_upstream_request(
            policy_result.effective_body,
            requested_model=policy_result.effective_body["model"],
            upstream_model=upstream_model,
        )
        return build_responses_compact_upstream_body(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Request contains fields that are not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


def _build_safe_conversation_items_create_upstream_body(
    effective_body: dict[str, object],
) -> dict[str, object]:
    try:
        normalized_request = normalize_conversation_items_create_upstream_request(effective_body)
        return build_conversation_items_create_upstream_body(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Conversation item create payload is not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


def _build_safe_conversation_update_upstream_body(
    effective_body: dict[str, object],
) -> dict[str, object]:
    try:
        normalized_request = normalize_conversation_update_upstream_request(effective_body)
        return build_conversation_update_upstream_body(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Conversation update payload is not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


def _build_safe_conversation_items_query_params(
    query_params: dict[str, object],
) -> dict[str, object]:
    try:
        normalized_request = normalize_conversation_items_query_request(query_params)
        return build_conversation_items_query_params(normalized_request)
    except (TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "Conversation items query is not approved for upstream forwarding.",
            status_code=400,
            error_type="invalid_request_error",
            code="upstream_payload_not_approved",
        ) from exc


def _validate_input_token_count_response(provider_response: ProviderResponse) -> None:
    payload = provider_response.json_body
    if payload.get("object") != "response.input_tokens":
        raise OpenAICompatibleError(
            "Provider returned an invalid Responses input-token count response.",
            status_code=502,
            error_type="server_error",
            code="provider_response_invalid",
        )
    input_tokens = payload.get("input_tokens")
    if isinstance(input_tokens, bool) or not isinstance(input_tokens, int) or input_tokens < 0:
        raise OpenAICompatibleError(
            "Provider returned an invalid Responses input-token count response.",
            status_code=502,
            error_type="server_error",
            code="provider_response_invalid",
        )


def _validate_compact_response(provider_response: ProviderResponse) -> None:
    payload = provider_response.json_body
    if payload.get("object") != "response.compaction":
        raise ProviderError(
            "Provider returned an invalid Responses compact response.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="provider_response_invalid",
        )
    if provider_response.usage is None:
        raise ProviderError(
            "Provider Responses compact response did not include usage metadata.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="responses_compact_usage_missing",
        )


async def handle_response_input_tokens_count(
    *,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = payload.model_dump(mode="python", exclude_none=True, exclude_unset=True)
    policy = ResponsesRequestPolicy(settings=settings)
    try:
        policy_result = policy.apply_input_token_count(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    route = await _resolve_responses_route(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        endpoint=RESPONSES_INPUT_TOKENS_ENDPOINT,
        streaming_requested=False,
        text_format_type=responses_text_format_type(policy_result.effective_body),
        function_tools_requested=responses_function_tools_requested(policy_result.effective_body),
        custom_tools_requested=responses_custom_tools_requested(policy_result.effective_body),
        image_input_requested=responses_image_input_requested(policy_result.effective_body),
        file_input_requested=responses_file_input_requested(policy_result.effective_body),
        input_token_count_requested=True,
        stored_responses_requested=False,
        previous_response_id_requested=False,
        compact_requested=False,
        conversations_requested=False,
        request=request,
    )
    upstream_body = _build_safe_responses_input_tokens_upstream_body(
        policy_result=policy_result,
        upstream_model=route.resolved_model,
    )
    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint=RESPONSES_INPUT_TOKENS_PROVIDER_ENDPOINT,
        body=upstream_body,
        request_id=request_id,
    )
    try:
        adapter = get_provider_adapter(route, settings)
        provider_response = await observe_provider_call(
            provider=route.provider,
            endpoint=RESPONSES_INPUT_TOKENS_PROVIDER_ENDPOINT,
            call=lambda: adapter.forward_response_input_tokens(provider_request),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    _validate_input_token_count_response(provider_response)
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_response_compact(
    *,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = payload.model_dump(mode="python", exclude_none=True, exclude_unset=True)
    policy = ResponsesRequestPolicy(settings=settings)
    try:
        policy_result = policy.apply_compact(body)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    route = await _resolve_responses_route(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        endpoint=RESPONSES_COMPACT_ENDPOINT,
        streaming_requested=False,
        text_format_type=None,
        function_tools_requested=False,
        custom_tools_requested=False,
        image_input_requested=False,
        file_input_requested=False,
        input_token_count_requested=False,
        stored_responses_requested=False,
        previous_response_id_requested=False,
        compact_requested=True,
        conversations_requested=False,
        request=request,
    )
    upstream_body = _build_safe_responses_compact_upstream_body(
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
            endpoint=RESPONSES_COMPACT_ENDPOINT,
        )
        provider_request = ProviderRequest(
            provider=route.provider,
            upstream_model=route.resolved_model,
            endpoint=RESPONSES_COMPACT_PROVIDER_ENDPOINT,
            body=upstream_body,
            request_id=request_id,
        )
        try:
            adapter = get_provider_adapter(route, settings)
            provider_response = await observe_provider_call(
                provider=route.provider,
                endpoint=RESPONSES_COMPACT_PROVIDER_ENDPOINT,
                call=lambda: adapter.compact_response(provider_request),
            )
            _validate_compact_response(provider_response)
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
                provider_endpoint=RESPONSES_COMPACT_PROVIDER_ENDPOINT,
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
                provider_endpoint=RESPONSES_COMPACT_PROVIDER_ENDPOINT,
            )
            _record_success_metrics(
                route=route,
                provider_response=provider_response,
                accounting_result=accounting_result,
                provider_endpoint=RESPONSES_COMPACT_PROVIDER_ENDPOINT,
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
        if rate_limit_reservation is not None:
            await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
        raise

    await _release_rate_limit_concurrency(rate_limit_reservation, suppress=False)
    return response


async def handle_response_create(
    *,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    body = payload.model_dump(mode="python", exclude_none=True, exclude_unset=True)
    policy = ResponsesRequestPolicy(settings=settings)
    try:
        policy_result = policy.apply(body, allow_store=True)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    request_id = _request_id_from_request(request)
    route = await _resolve_responses_route(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        endpoint=RESPONSES_ENDPOINT,
        streaming_requested=policy_result.effective_body.get("stream") is True,
        text_format_type=responses_text_format_type(policy_result.effective_body),
        function_tools_requested=responses_function_tools_requested(policy_result.effective_body),
        custom_tools_requested=responses_custom_tools_requested(policy_result.effective_body),
        image_input_requested=responses_image_input_requested(policy_result.effective_body),
        file_input_requested=responses_file_input_requested(policy_result.effective_body),
        input_token_count_requested=False,
        stored_responses_requested=policy_result.effective_body.get("store") is True,
        previous_response_id_requested=previous_response_id_requested(policy_result.effective_body),
        compact_requested=False,
        conversations_requested=conversation_requested(policy_result.effective_body),
        request=request,
    )
    if previous_response_id_requested(policy_result.effective_body):
        await _verify_previous_response_reference(
            previous_response_id=str(policy_result.effective_body["previous_response_id"]),
            authenticated_key=authenticated_key,
            route=route,
            request=request,
        )
    if conversation_requested(policy_result.effective_body):
        await _verify_conversation_reference(
            conversation_id=str(policy_result.effective_body["conversation"]),
            authenticated_key=authenticated_key,
            route=route,
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

        if policy_result.effective_body.get("stream") is True:
            try:
                response = _streaming_responses_response(
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
                )
                return response
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
                    streaming=True,
                )
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                rate_limit_reservation = None
                raise openai_error_from_provider_error(exc) from exc
            except Exception:
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                raise

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
            if policy_result.effective_body.get("store") is True:
                await _persist_stored_response_reference(
                    authenticated_key=authenticated_key,
                    route=route,
                    provider_response=provider_response,
                    request=request,
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
        if rate_limit_reservation is not None:
            await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
        raise

    await _release_rate_limit_concurrency(rate_limit_reservation, suppress=False)
    return response


async def handle_response_retrieve(
    *,
    response_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    safe_response_id = _validate_response_id(response_id)
    reference = await _get_owned_active_response_reference(
        response_id=safe_response_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _response_not_found_error()

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model=reference.upstream_model or "",
            endpoint=RESPONSES_RETRIEVE_PROVIDER_ENDPOINT,
            body={},
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=RESPONSES_RETRIEVE_PROVIDER_ENDPOINT,
            call=lambda: adapter.retrieve_response(
                provider_request,
                response_id=safe_response_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_response_delete(
    *,
    response_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    safe_response_id = _validate_response_id(response_id)
    reference = await _get_owned_active_response_reference(
        response_id=safe_response_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _response_not_found_error()

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model=reference.upstream_model or "",
            endpoint=RESPONSES_DELETE_PROVIDER_ENDPOINT,
            body={},
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=RESPONSES_DELETE_PROVIDER_ENDPOINT,
            call=lambda: adapter.delete_response(
                provider_request,
                response_id=safe_response_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    await _mark_response_reference_deleted(reference_id=reference.id, request=request)
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_response_input_items_list(
    *,
    response_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    safe_response_id = _validate_response_id(response_id)
    query_params = _validate_response_input_items_query(request)
    reference = await _get_owned_active_response_reference(
        response_id=safe_response_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _response_not_found_error()

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_reference(
            reference,
            request=request,
            list_input_items_requested=True,
        )
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model=reference.upstream_model or "",
            endpoint=RESPONSES_INPUT_ITEMS_PROVIDER_ENDPOINT,
            body=build_responses_input_items_query_params(query_params),
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=RESPONSES_INPUT_ITEMS_PROVIDER_ENDPOINT,
            call=lambda: adapter.list_response_input_items(
                provider_request,
                response_id=safe_response_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_create(
    *,
    payload: dict[str, object] | None,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    _validate_conversation_create_body(payload)
    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_new_conversation(
            authenticated_key=authenticated_key,
            request=request,
        )
        provider_request = ProviderRequest(
            provider=route_like.provider,
            upstream_model="",
            endpoint=CONVERSATIONS_CREATE_PROVIDER_ENDPOINT,
            body={},
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=route_like.provider,
            endpoint=CONVERSATIONS_CREATE_PROVIDER_ENDPOINT,
            call=lambda: adapter.create_conversation(provider_request),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    await _persist_conversation_reference(
        authenticated_key=authenticated_key,
        provider=route_like.provider,
        provider_response=provider_response,
        request=request,
    )
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_update(
    *,
    conversation_id: str,
    payload: dict[str, object] | None,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    reference = await _owned_conversation_reference_or_404(
        conversation_id=conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    try:
        effective_body = validate_conversation_update_body(payload)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc
    upstream_body = _build_safe_conversation_update_upstream_body(effective_body)

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATIONS_UPDATE_PROVIDER_ENDPOINT,
            body=upstream_body,
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATIONS_UPDATE_PROVIDER_ENDPOINT,
            call=lambda: adapter.update_conversation(
                provider_request,
                conversation_id=reference.provider_conversation_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_retrieve(
    *,
    conversation_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    safe_conversation_id = _validate_conversation_id(conversation_id)
    reference = await _get_owned_active_conversation_reference(
        conversation_id=safe_conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _conversation_not_found_error()

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATIONS_RETRIEVE_PROVIDER_ENDPOINT,
            body={},
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATIONS_RETRIEVE_PROVIDER_ENDPOINT,
            call=lambda: adapter.retrieve_conversation(
                provider_request,
                conversation_id=safe_conversation_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_delete(
    *,
    conversation_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    safe_conversation_id = _validate_conversation_id(conversation_id)
    reference = await _get_owned_active_conversation_reference(
        conversation_id=safe_conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _conversation_not_found_error()

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATIONS_DELETE_PROVIDER_ENDPOINT,
            body={},
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATIONS_DELETE_PROVIDER_ENDPOINT,
            call=lambda: adapter.delete_conversation(
                provider_request,
                conversation_id=safe_conversation_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    await _mark_conversation_reference_deleted(reference_id=reference.id, request=request)
    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_item_create(
    *,
    conversation_id: str,
    payload: dict[str, object] | None,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    reference = await _owned_conversation_reference_or_404(
        conversation_id=conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    try:
        effective_body = validate_conversation_items_create_body(payload, settings=settings)
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc
    upstream_body = _build_safe_conversation_items_create_upstream_body(effective_body)

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATION_ITEMS_CREATE_PROVIDER_ENDPOINT,
            body=upstream_body,
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATION_ITEMS_CREATE_PROVIDER_ENDPOINT,
            call=lambda: adapter.create_conversation_items(
                provider_request,
                conversation_id=reference.provider_conversation_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_items_list(
    *,
    conversation_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    reference = await _owned_conversation_reference_or_404(
        conversation_id=conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    query_params = _validate_conversation_items_query(request, allow_pagination=True)
    upstream_query = _build_safe_conversation_items_query_params(query_params)

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATION_ITEMS_LIST_PROVIDER_ENDPOINT,
            body=upstream_query,
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATION_ITEMS_LIST_PROVIDER_ENDPOINT,
            call=lambda: adapter.list_conversation_items(
                provider_request,
                conversation_id=reference.provider_conversation_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_item_retrieve(
    *,
    conversation_id: str,
    item_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    reference = await _owned_conversation_reference_or_404(
        conversation_id=conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    safe_item_id = _validate_conversation_item_id(item_id)
    query_params = _validate_conversation_items_query(request, allow_pagination=False)
    upstream_query = _build_safe_conversation_items_query_params(query_params)

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATION_ITEMS_RETRIEVE_PROVIDER_ENDPOINT,
            body=upstream_query,
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATION_ITEMS_RETRIEVE_PROVIDER_ENDPOINT,
            call=lambda: adapter.retrieve_conversation_item(
                provider_request,
                conversation_id=reference.provider_conversation_id,
                item_id=safe_item_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def handle_conversation_item_delete(
    *,
    conversation_id: str,
    item_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    reference = await _owned_conversation_reference_or_404(
        conversation_id=conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    safe_item_id = _validate_conversation_item_id(item_id)

    request_id = _request_id_from_request(request)
    try:
        route_like = await _provider_route_for_conversation_reference(reference, request=request)
        provider_request = ProviderRequest(
            provider=reference.provider,
            upstream_model="",
            endpoint=CONVERSATION_ITEMS_DELETE_PROVIDER_ENDPOINT,
            body={},
            request_id=request_id,
        )
        adapter = get_provider_adapter(route_like, settings)
        provider_response = await observe_provider_call(
            provider=reference.provider,
            endpoint=CONVERSATION_ITEMS_DELETE_PROVIDER_ENDPOINT,
            call=lambda: adapter.delete_conversation_item(
                provider_request,
                conversation_id=reference.provider_conversation_id,
                item_id=safe_item_id,
            ),
        )
    except ProviderError as exc:
        raise openai_error_from_provider_error(exc) from exc

    return JSONResponse(
        status_code=provider_response.status_code,
        content=dict(provider_response.json_body),
    )


async def _resolve_responses_route(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    effective_model: str,
    endpoint: str,
    streaming_requested: bool,
    text_format_type: str | None,
    function_tools_requested: bool,
    custom_tools_requested: bool,
    image_input_requested: bool,
    file_input_requested: bool,
    input_token_count_requested: bool,
    stored_responses_requested: bool,
    previous_response_id_requested: bool,
    compact_requested: bool,
    conversations_requested: bool,
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
                endpoint=endpoint,
            )
            enforce_responses_route_capabilities(
                route_capabilities=route.capabilities,
                streaming_requested=streaming_requested,
                route_supports_streaming=route.supports_streaming,
                json_mode_requested=text_format_type == TEXT_FORMAT_JSON_OBJECT,
                structured_output_requested=text_format_type == TEXT_FORMAT_JSON_SCHEMA,
                function_tools_requested=function_tools_requested,
                custom_tools_requested=custom_tools_requested,
                image_input_requested=image_input_requested,
                file_input_requested=file_input_requested,
                input_token_count_requested=input_token_count_requested,
                stored_responses_requested=stored_responses_requested,
                previous_response_id_requested=previous_response_id_requested,
                compact_requested=compact_requested,
                conversations_requested=conversations_requested,
            )
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
    endpoint: str = RESPONSES_ENDPOINT,
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
                endpoint=endpoint,
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
                endpoint=endpoint,
            )
        except QuotaError as exc:
            increment_quota_rejection(quota_exc_code(exc))
            raise openai_error_from_quota_error(exc) from exc

        if hasattr(session, "commit"):
            await session.commit()
        return cost_estimate, reservation
    finally:
        await session_iterator.aclose()


def _streaming_responses_response(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    cost_estimate: ChatCostEstimate,
    reservation: QuotaReservationResult,
    request_id: str,
    settings: Settings,
    request: Request | None,
    rate_limit_reservation: _RateLimitReservation | None,
    upstream_body: dict[str, object],
) -> StreamingResponse:
    adapter = get_provider_adapter(route, settings)
    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint=RESPONSES_PROVIDER_ENDPOINT,
        body=upstream_body,
        request_id=request_id,
    )

    async def _events():
        start = time.perf_counter()
        completed_chunk: ProviderStreamChunk | None = None
        upstream_request_id: str | None = None
        completed_event: str | None = None
        terminal_done_event: str | None = None
        completed = False
        provider_status = "error"
        heartbeat_stop = asyncio.Event()
        heartbeat_task = _start_rate_limit_heartbeat(
            rate_limit_reservation,
            stop_event=heartbeat_stop,
        )
        try:
            async for chunk in adapter.stream_response(provider_request):
                if chunk.upstream_request_id:
                    upstream_request_id = chunk.upstream_request_id
                if _is_responses_completed_chunk(chunk):
                    completed = True
                    completed_event = chunk.raw_sse_event
                    completed_chunk = chunk
                    continue
                if chunk.is_done:
                    terminal_done_event = chunk.raw_sse_event
                    continue
                yield chunk.raw_sse_event

            if completed and completed_chunk is not None and completed_chunk.usage is not None:
                provider_response = _provider_response_from_response_stream(
                    chunk=completed_chunk,
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
                    accounting_result = await _finalize_successful_response(
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
                _record_success_metrics(
                    route=route,
                    provider_response=provider_response,
                    accounting_result=accounting_result,
                )
                provider_status = "success"
                if completed_event is not None:
                    yield completed_event
                if terminal_done_event is not None:
                    yield terminal_done_event
            else:
                await _record_provider_failure_and_release(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=ProviderError(
                        "Provider Responses stream completed without final usage.",
                        provider=route.provider,
                        upstream_status_code=200 if completed else None,
                        error_code="responses_stream_usage_missing",
                    ),
                    request=request,
                    streaming=True,
                )
                provider_status = "incomplete"
                yield format_responses_error_event(
                    message=(
                        "Provider Responses stream completed without final usage metadata; "
                        "accounting could not finalize successfully."
                    ),
                    code="responses_stream_usage_missing",
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
                        "Client disconnected during streaming Responses request.",
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
            yield format_responses_error_event(
                message=exc.safe_message,
                code=exc.error_code,
            )
        except AccountingError as exc:
            increment_accounting_failure(exc.error_code)
            yield format_responses_error_event(
                message=exc.safe_message,
                code=exc.error_code,
            )
        except QuotaError as exc:
            increment_quota_rejection(exc.error_code)
            yield format_responses_error_event(
                message=exc.safe_message,
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
                        # Expected after explicitly cancelling the heartbeat task during stream cleanup.
                        pass
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                record_provider_call_result(
                    provider=route.provider,
                    endpoint=RESPONSES_PROVIDER_ENDPOINT,
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
    streaming: bool = False,
    provider_endpoint: str = RESPONSES_PROVIDER_ENDPOINT,
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
            "endpoint": provider_endpoint,
            "error_type": provider_error.error_code,
            "error_code": provider_error.error_code,
            "status_code": provider_error.upstream_status_code,
        }
        if provider_error.diagnostic is not None:
            kwargs["provider_diagnostic"] = provider_error.diagnostic.to_safe_dict()
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
    except AccountingError as exc:
        increment_accounting_failure(exc.error_code)
        raise openai_error_from_accounting_error(exc) from exc
    except QuotaError as exc:
        increment_quota_rejection(exc.error_code)
        raise openai_error_from_quota_error(exc) from exc
    finally:
        await session_iterator.aclose()


async def _release_streaming_reservation_after_error(
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
    streaming: bool = False,
    provider_completed_usage_ledger_id: uuid.UUID | None = None,
    provider_endpoint: str = RESPONSES_PROVIDER_ENDPOINT,
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
            "endpoint": provider_endpoint,
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
        return result
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
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
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


async def _persist_stored_response_reference(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    provider_response: ProviderResponse,
    request: Request | None,
) -> None:
    provider_response_id = _provider_response_id(provider_response)
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        repository = ResponseReferencesRepository(session)
        await repository.create_response_reference(
            provider_response_id=provider_response_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            owner_id=authenticated_key.owner_id,
            cohort_id=authenticated_key.cohort_id,
            provider=route.provider,
            requested_model=route.requested_model,
            upstream_model=route.resolved_model,
            endpoint=RESPONSES_ENDPOINT,
            route_id=route.route_id,
            provider_request_id=provider_response.upstream_request_id,
            metadata={},
        )
        if hasattr(session, "commit"):
            await session.commit()
    finally:
        await session_iterator.aclose()


async def _persist_conversation_reference(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    provider: str,
    provider_response: ProviderResponse,
    request: Request | None,
) -> None:
    provider_conversation_id = _provider_conversation_id(provider_response)
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        repository = ConversationReferencesRepository(session)
        await repository.create_conversation_reference(
            provider_conversation_id=provider_conversation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            owner_id=authenticated_key.owner_id,
            cohort_id=authenticated_key.cohort_id,
            provider=provider,
            endpoint=CONVERSATIONS_CREATE_ENDPOINT,
            provider_request_id=provider_response.upstream_request_id,
            metadata={},
        )
        if hasattr(session, "commit"):
            await session.commit()
    finally:
        await session_iterator.aclose()


async def _get_owned_active_conversation_reference(
    *,
    conversation_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    request: Request | None,
) -> ConversationReference | None:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        repository = ConversationReferencesRepository(session)
        return await repository.get_active_reference_for_key(
            provider_conversation_id=conversation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
        )
    finally:
        await session_iterator.aclose()


async def _owned_conversation_reference_or_404(
    *,
    conversation_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    request: Request | None,
) -> ConversationReference:
    safe_conversation_id = _validate_conversation_id(conversation_id)
    reference = await _get_owned_active_conversation_reference(
        conversation_id=safe_conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _conversation_not_found_error()
    return reference


async def _verify_conversation_reference(
    *,
    conversation_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    request: Request | None,
) -> ConversationReference:
    reference = await _get_owned_active_conversation_reference(
        conversation_id=conversation_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _conversation_not_found_error()
    if not _conversation_reference_matches_route(reference, route):
        raise _conversation_not_found_error()
    return reference


async def _get_owned_active_response_reference(
    *,
    response_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    request: Request | None,
):
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        repository = ResponseReferencesRepository(session)
        return await repository.get_active_reference_for_key(
            provider_response_id=response_id,
            gateway_key_id=authenticated_key.gateway_key_id,
        )
    finally:
        await session_iterator.aclose()


async def _verify_previous_response_reference(
    *,
    previous_response_id: str,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    request: Request | None,
) -> ResponseReference:
    reference = await _get_owned_active_response_reference(
        response_id=previous_response_id,
        authenticated_key=authenticated_key,
        request=request,
    )
    if reference is None:
        raise _response_not_found_error()
    if not _response_reference_matches_route(reference, route):
        raise _response_not_found_error()
    return reference


def _response_reference_matches_route(
    reference: ResponseReference,
    route: RouteResolutionResult,
) -> bool:
    if reference.provider != route.provider:
        return False
    if reference.upstream_model and reference.upstream_model != route.resolved_model:
        return False
    if reference.route_id is not None and reference.route_id != route.route_id:
        return False
    return True


def _conversation_reference_matches_route(
    reference: ConversationReference,
    route: RouteResolutionResult,
) -> bool:
    if reference.provider != route.provider:
        return False
    if reference.route_id is not None and reference.route_id != route.route_id:
        return False
    return True


async def _provider_route_for_reference(
    reference,
    *,
    request: Request | None,
    list_input_items_requested: bool = False,
):
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        if list_input_items_requested:
            if reference.route_id is None:
                raise _response_not_found_error()
            model_route = await ModelRoutesRepository(session).get_model_route_by_id(reference.route_id)
            if (
                model_route is None
                or model_route.enabled is not True
                or model_route.provider != reference.provider
                or model_route.upstream_model != reference.upstream_model
                or model_route.endpoint != RESPONSES_ENDPOINT
            ):
                raise _response_not_found_error()
            try:
                enforce_responses_route_capabilities(
                    route_capabilities=model_route.capabilities,
                    list_input_items_requested=True,
                )
            except RequestPolicyError as exc:
                raise openai_error_from_request_policy_error(exc) from exc

        provider_config = await ProviderConfigsRepository(session).get_provider_config_by_provider(
            reference.provider
        )
        if provider_config is None or provider_config.enabled is not True:
            raise ProviderConfigurationError(
                "Provider is not configured for this stored Response.",
                provider=reference.provider,
                error_code="provider_configuration_error",
            )
        return SimpleNamespace(
            provider=provider_config.provider,
            provider_base_url=provider_config.base_url,
            provider_api_key_env_var=provider_config.api_key_env_var,
            provider_timeout_seconds=provider_config.timeout_seconds,
            provider_max_retries=provider_config.max_retries,
        )
    finally:
        await session_iterator.aclose()


async def _provider_route_for_new_conversation(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    request: Request | None,
):
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        providers = await ProviderConfigsRepository(session).list_provider_configs(enabled=True)
        provider_config = _select_conversation_provider_config(
            providers,
            authenticated_key=authenticated_key,
        )
        if provider_config is None:
            raise ProviderConfigurationError(
                "Provider is not configured for Conversations.",
                provider="openai",
                error_code="provider_configuration_error",
            )
        return _route_like_for_provider_config(provider_config)
    finally:
        await session_iterator.aclose()


async def _provider_route_for_conversation_reference(
    reference: ConversationReference,
    *,
    request: Request | None,
):
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        provider_config = await ProviderConfigsRepository(session).get_provider_config_by_provider(
            reference.provider
        )
        if provider_config is None or provider_config.enabled is not True:
            raise ProviderConfigurationError(
                "Provider is not configured for this Conversation.",
                provider=reference.provider,
                error_code="provider_configuration_error",
            )
        return _route_like_for_provider_config(provider_config)
    finally:
        await session_iterator.aclose()


def _select_conversation_provider_config(
    provider_configs,
    *,
    authenticated_key: AuthenticatedGatewayKey,
):
    enabled_by_name = {config.provider: config for config in provider_configs if config.enabled}
    if authenticated_key.allowed_providers is not None:
        allowed = [provider for provider in authenticated_key.allowed_providers if provider in enabled_by_name]
        if not allowed:
            return None
        if len(allowed) == 1:
            return enabled_by_name[allowed[0]]
        if "openai" in allowed:
            return enabled_by_name["openai"]
        return enabled_by_name[sorted(allowed)[0]]
    return enabled_by_name.get("openai") or next(iter(sorted(enabled_by_name.values(), key=lambda item: item.provider)), None)


def _route_like_for_provider_config(provider_config):
    return SimpleNamespace(
        provider=provider_config.provider,
        provider_base_url=provider_config.base_url,
        provider_api_key_env_var=provider_config.api_key_env_var,
        provider_timeout_seconds=provider_config.timeout_seconds,
        provider_max_retries=provider_config.max_retries,
    )


def _validate_response_input_items_query(request: Request | None) -> dict[str, object]:
    if request is None:
        return {}
    params = request.query_params
    unknown_keys = set(params.keys()) - _RESPONSES_INPUT_ITEMS_ALLOWED_QUERY_KEYS
    if unknown_keys:
        raise _input_items_query_error("Unsupported input-items query parameter.", param="query")

    query: dict[str, object] = {}
    after = params.get("after")
    if after is not None:
        if not after or len(after.encode("utf-8")) > 256 or any(ord(char) < 32 for char in after):
            raise _input_items_query_error("Invalid input-items cursor.", param="after")
        query["after"] = after

    limit = params.get("limit")
    if limit is not None:
        try:
            limit_value = int(limit)
        except ValueError as exc:
            raise _input_items_query_error("Invalid input-items limit.", param="limit") from exc
        if str(limit_value) != limit or limit_value < 1 or limit_value > 100:
            raise _input_items_query_error("Invalid input-items limit.", param="limit")
        query["limit"] = limit_value

    order = params.get("order")
    if order is not None:
        if order not in {"asc", "desc"}:
            raise _input_items_query_error("Invalid input-items order.", param="order")
        query["order"] = order

    include_values = [*params.getlist("include"), *params.getlist("include[]")]
    if include_values:
        cleaned_include: list[str] = []
        for include in include_values:
            if include not in _RESPONSES_INPUT_ITEMS_ALLOWED_INCLUDE_VALUES:
                raise _input_items_query_error(
                    "Unsupported input-items include value.",
                    param="include",
                )
            cleaned_include.append(include)
        query["include"] = cleaned_include
    return query


def _validate_conversation_items_query(
    request: Request | None,
    *,
    allow_pagination: bool,
) -> dict[str, object]:
    if request is None:
        return {}
    params = request.query_params
    allowed_keys = (
        _CONVERSATION_ITEMS_ALLOWED_QUERY_KEYS
        if allow_pagination
        else frozenset({"include", "include[]"})
    )
    unknown_keys = set(params.keys()) - allowed_keys
    if unknown_keys:
        raise _conversation_items_query_error(
            "Unsupported Conversation items query parameter.",
            param="query",
        )

    query: dict[str, object] = {}
    if allow_pagination:
        after = params.get("after")
        if after is not None:
            query["after"] = _validate_items_cursor(after, param="after")

        before = params.get("before")
        if before is not None:
            query["before"] = _validate_items_cursor(before, param="before")

        limit = params.get("limit")
        if limit is not None:
            try:
                limit_value = int(limit)
            except ValueError as exc:
                raise _conversation_items_query_error(
                    "Invalid Conversation items limit.",
                    param="limit",
                ) from exc
            if str(limit_value) != limit or limit_value < 1 or limit_value > 100:
                raise _conversation_items_query_error(
                    "Invalid Conversation items limit.",
                    param="limit",
                )
            query["limit"] = limit_value

        order = params.get("order")
        if order is not None:
            if order not in {"asc", "desc"}:
                raise _conversation_items_query_error(
                    "Invalid Conversation items order.",
                    param="order",
                )
            query["order"] = order

    include_values = [*params.getlist("include"), *params.getlist("include[]")]
    if include_values:
        cleaned_include: list[str] = []
        for include in include_values:
            if include not in _CONVERSATION_ITEMS_ALLOWED_INCLUDE_VALUES:
                raise _conversation_items_query_error(
                    "Unsupported Conversation items include value.",
                    param="include",
                )
            cleaned_include.append(include)
        query["include"] = cleaned_include
    return query


def _validate_items_cursor(value: str, *, param: str) -> str:
    if not value or len(value.encode("utf-8")) > 256 or any(ord(char) < 32 for char in value):
        raise _conversation_items_query_error(
            "Invalid Conversation items cursor.",
            param=param,
        )
    return value


def _input_items_query_error(message: str, *, param: str) -> OpenAICompatibleError:
    return OpenAICompatibleError(
        message,
        status_code=400,
        error_type="invalid_request_error",
        code="invalid_response_input_items_query",
        param=param,
    )


def _conversation_items_query_error(message: str, *, param: str) -> OpenAICompatibleError:
    return OpenAICompatibleError(
        message,
        status_code=400,
        error_type="invalid_request_error",
        code="invalid_conversation_items_query",
        param=param,
    )


async def _mark_response_reference_deleted(
    *,
    reference_id: uuid.UUID,
    request: Request | None,
) -> None:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        reference = await session.get(ResponseReference, reference_id)
        if reference is None or reference.status != "active":
            raise OpenAICompatibleError(
                "Stored Response delete could not update local reference metadata.",
                status_code=500,
                error_type="server_error",
                code="response_reference_update_failed",
            )
        await ResponseReferencesRepository(session).mark_deleted(
            reference,
            deleted_at=datetime.now(UTC),
        )
        if hasattr(session, "commit"):
            await session.commit()
    finally:
        await session_iterator.aclose()


async def _mark_conversation_reference_deleted(
    *,
    reference_id: uuid.UUID,
    request: Request | None,
) -> None:
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc

    try:
        reference = await session.get(ConversationReference, reference_id)
        if reference is None or reference.status != "active":
            raise OpenAICompatibleError(
                "Conversation delete could not update local reference metadata.",
                status_code=500,
                error_type="server_error",
                code="conversation_reference_update_failed",
            )
        await ConversationReferencesRepository(session).mark_deleted(
            reference,
            deleted_at=datetime.now(UTC),
        )
        if hasattr(session, "commit"):
            await session.commit()
    finally:
        await session_iterator.aclose()


def _provider_response_id(provider_response: ProviderResponse) -> str:
    response_id = provider_response.json_body.get("id")
    if isinstance(response_id, str) and response_id:
        return response_id
    raise OpenAICompatibleError(
        "Provider did not return a retrievable stored Response ID.",
        status_code=502,
        error_type="server_error",
        code="provider_response_invalid",
    )


def _provider_conversation_id(provider_response: ProviderResponse) -> str:
    conversation_id = provider_response.json_body.get("id")
    if isinstance(conversation_id, str) and conversation_id:
        return conversation_id
    raise OpenAICompatibleError(
        "Provider did not return a Conversation ID.",
        status_code=502,
        error_type="server_error",
        code="provider_response_invalid",
    )


def _validate_conversation_create_body(payload: dict[str, object] | None) -> dict[str, object]:
    if payload in (None, {}):
        return {}
    if not isinstance(payload, dict):
        raise OpenAICompatibleError(
            "Conversation create request body must be an object.",
            status_code=400,
            error_type="invalid_request_error",
            code="conversation_create_body_invalid",
        )
    raise OpenAICompatibleError(
        "Conversation create with initial items or metadata is not enabled by this gateway.",
        status_code=400,
        error_type="invalid_request_error",
        code="conversation_create_fields_not_supported",
        param=sorted(payload)[0] if payload else None,
    )


def _validate_response_id(response_id: str) -> str:
    if not response_id or len(response_id.encode("utf-8")) > 512 or any(
        ord(char) < 32 for char in response_id
    ):
        raise OpenAICompatibleError(
            "Response not found.",
            status_code=404,
            error_type="invalid_request_error",
            code="response_not_found",
        )
    return response_id


def _validate_conversation_id(conversation_id: str) -> str:
    if not conversation_id or len(conversation_id.encode("utf-8")) > 512 or any(
        ord(char) < 32 for char in conversation_id
    ):
        raise _conversation_not_found_error()
    return conversation_id


def _validate_conversation_item_id(item_id: str) -> str:
    if not item_id or len(item_id.encode("utf-8")) > 512 or any(ord(char) < 32 for char in item_id):
        raise OpenAICompatibleError(
            "Conversation item not found.",
            status_code=404,
            error_type="invalid_request_error",
            code="conversation_item_not_found",
        )
    return item_id


def _response_not_found_error() -> OpenAICompatibleError:
    return OpenAICompatibleError(
        "Response not found.",
        status_code=404,
        error_type="invalid_request_error",
        code="response_not_found",
    )


def _conversation_not_found_error() -> OpenAICompatibleError:
    return OpenAICompatibleError(
        "Conversation not found.",
        status_code=404,
        error_type="invalid_request_error",
        code="conversation_not_found",
    )


def _record_success_metrics(
    *,
    route: RouteResolutionResult,
    provider_response: ProviderResponse,
    accounting_result: FinalizedAccountingResult,
    provider_endpoint: str = RESPONSES_PROVIDER_ENDPOINT,
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
            endpoint=provider_endpoint,
            upstream_status_code=provider_response.status_code,
        )


def _provider_response_from_response_stream(
    *,
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


def _is_responses_completed_chunk(chunk: ProviderStreamChunk) -> bool:
    payload = chunk.json_body
    return isinstance(payload, dict) and payload.get("type") == "response.completed"


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
