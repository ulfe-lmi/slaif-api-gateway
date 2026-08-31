"""Orchestration for stateless text-output OpenAI-compatible Responses."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.codex_replay import CodexReplayReferencesRepository
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
from slaif_gateway.modules.clients.registry import (
    normalize_default_client_request,
    resolve_responses_client_module,
)
from slaif_gateway.modules.contracts import DEFAULT_CLIENT_MODULE_ID, ModuleSelectionError
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.local_coding.identity import derive_request_identity
from slaif_gateway.modules.servers.registry import (
    ensure_client_module_has_server_pair,
    ensure_client_server_pair,
    resolve_server_module,
)
from slaif_gateway.providers.errors import ProviderConfigurationError, ProviderError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.providers.streaming import (
    RESPONSES_PROVIDER_FAILURE_EVENT_TYPES,
    RESPONSES_TEXT_STREAM_EVENT_TYPES,
    CodexReplayStreamCandidate,
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
    format_responses_error_event,
)
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceResolveInput,
    ExternalToolFenceRouteFacts,
)
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldInput,
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReasonCode,
)
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.schemas.policy import ResponsesPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate, FxConversionResult, PricingLookupResult
from slaif_gateway.schemas.providers import (
    ProviderRequest,
    ProviderResponse,
    ProviderStreamChunk,
    ProviderUsage,
)
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.rate_limits import RateLimitPolicy
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import AccountingError
from slaif_gateway.services.codex_replay_service import (
    CodexReplayAuthorization,
    CodexReplayReferenceError,
    CodexReplayService,
)
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceError,
    ExternalToolFenceService,
)
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService
from slaif_gateway.services.openai_compatible_request_boundary import (
    OpenAICompatibleRequestBoundaryError,
    enforce_openai_compatible_request_boundary,
)
from slaif_gateway.services.openai_web_search_contract import (
    EXTERNAL_TOOL_FENCED,
    parse_key_external_tool_policy,
    parse_web_search_output,
    parse_web_search_stream,
)
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import PricingError
from slaif_gateway.services.quota_errors import QuotaError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.rate_limit_errors import RateLimitError, RedisRateLimitUnavailableError
from slaif_gateway.services.rate_limit_policy import build_rate_limit_policy
from slaif_gateway.services.rate_limit_service import RedisRateLimitService
from slaif_gateway.services.responses_external_tool_runtime import (
    ExternalToolRuntimeError,
    admit_web_search_request,
    with_pricing,
)
from slaif_gateway.services.responses_request_policy import (
    TEXT_FORMAT_JSON_OBJECT,
    TEXT_FORMAT_JSON_SCHEMA,
    CodexCompactionReplayCandidate,
    CodexReplayRequestCandidate,
    ResponsesRequestPolicy,
    apply_codex_route_limits,
    codex_client_tool_declarations,
    codex_client_tool_taxonomy_id,
    codex_replay_request_candidates,
    conversation_requested,
    previous_response_id_requested,
    responses_codex_client_tools_allowed,
    responses_codex_client_tools_requested,
    responses_codex_compaction_allowed,
    responses_codex_compaction_replay_requested,
    responses_codex_compaction_requested,
    responses_codex_encrypted_reasoning_replay_allowed,
    responses_codex_encrypted_reasoning_replay_requested,
    responses_codex_extended_limits_allowed,
    responses_codex_request_envelope_allowed,
    responses_codex_request_envelope_requested,
    responses_codex_streaming_tool_events_allowed,
    responses_codex_streaming_tool_events_requested,
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
    parse_codex_compaction_compatible_route_ids,
)
from slaif_gateway.services.responses_streaming_live_burn import (
    RESPONSES_STREAMING_LIVE_BURN_ERROR_CODE,
    RESPONSES_STREAMING_LIVE_BURN_ERROR_MESSAGE,
    ResponsesStreamingLiveBurnBudget,
    ResponsesStreamingLiveBurnEstimate,
    ResponsesStreamingLiveBurnMonitor,
    ResponsesStreamingLiveBurnPolicy,
    ResponsesStreamingLiveBurnPolicyError,
    build_responses_streaming_estimate_monitor,
    build_responses_streaming_live_burn_budget,
    default_responses_streaming_live_burn_policy,
    pre_provider_responses_streaming_live_burn_error,
    responses_streaming_live_burn_policy_from_metadata,
    safe_responses_streaming_interrupted_estimate_metadata,
)


from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import RouteResolutionError
from slaif_gateway.services.upstream_payloads import (
    build_conversation_items_create_upstream_body,
    build_conversation_items_query_params,
    build_conversation_update_upstream_body,
    build_responses_compact_upstream_body,
    build_responses_input_items_query_params,
    build_responses_input_tokens_upstream_body,
    build_responses_upstream_body,
)
from slaif_gateway.services.upstream_request_contracts import (
    normalize_conversation_items_create_upstream_request,
    normalize_conversation_items_query_request,
    normalize_conversation_update_upstream_request,
    normalize_responses_compact_upstream_request,
    normalize_responses_input_tokens_upstream_request,
    normalize_responses_upstream_request,
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
_RESPONSES_INPUT_ITEMS_ALLOWED_QUERY_KEYS = frozenset(
    {"after", "include", "include[]", "limit", "order"}
)
_RESPONSES_INPUT_ITEMS_ALLOWED_INCLUDE_VALUES = frozenset({"message.input_image.image_url"})
_CONVERSATION_ITEMS_ALLOWED_QUERY_KEYS = frozenset(
    {"after", "before", "include", "include[]", "limit", "order"}
)
_CONVERSATION_ITEMS_ALLOWED_INCLUDE_VALUES = frozenset({"message.input_image.image_url"})
_ALLOWED_RESPONSES_STREAM_EVENT_TYPES = RESPONSES_TEXT_STREAM_EVENT_TYPES


def _key_allows_external_web_search(authenticated_key: AuthenticatedGatewayKey) -> bool:
    """Permit candidate parsing only for a canonical fenced key policy."""
    parsed = parse_key_external_tool_policy(authenticated_key.external_tool_policy)
    return bool(parsed.valid and parsed.policy is not None and parsed.policy.mode == EXTERNAL_TOOL_FENCED)

get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check


@dataclass(frozen=True, slots=True)
class _ResponsesQuotaReservation:
    cost_estimate: ChatCostEstimate
    reservation: QuotaReservationResult
    live_burn_budget: ResponsesStreamingLiveBurnBudget | None
    external_tool_pricing: object | None = None


@dataclass(frozen=True, slots=True)
class _ExternalToolPricingFacts:
    lookup: PricingLookupResult
    fx: FxConversionResult


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


def _build_local_coding_server_context(
    *,
    client_request,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    settings: Settings,
) -> dict[str, object] | None:
    try:
        descriptor = resolve_server_module(
            route.provider,
            getattr(route, "provider_kind", None),
            getattr(route, "capabilities", None),
        )
        if descriptor.module_id != LOCAL_CODING_SERVER_MODULE_ID:
            return None
        contract = parse_local_coding_route_contract(route.capabilities)
        if contract is None:
            raise ValueError("Local Coding route contract is unavailable")
        policy = authenticated_key.responses_policy
        repository_scope = policy.get("local_coding_repository_scope") if isinstance(policy, Mapping) else None
        identity = derive_request_identity(
            owner_id=authenticated_key.owner_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            identity_hints=getattr(client_request, "identity_hints", {}),
            repository_scope=repository_scope if isinstance(repository_scope, str) else None,
            route=contract,
            derivation_secret=(
                settings.local_coding_identity_derivation_secret()
                if contract.identity_mode == "signed_identity_v1"
                else None
            ),
        )
    except (ProviderConfigurationError, TypeError, ValueError) as exc:
        raise OpenAICompatibleError(
            "The Local Coding identity contract is unavailable for this request.",
            status_code=503,
            error_type="server_error",
            code="local_coding_identity_unavailable",
        ) from exc
    if identity is None:
        return {"identity_mode": "static", "route": contract.route_name}
    return {
        "identity_mode": identity.identity_mode,
        "principal": identity.principal,
        "session": identity.session,
        "repository": identity.repository,
        "route": identity.route,
    }


def _codex_reasoning_events_enabled(
    *, client_module_id: str, server_context: Mapping[str, object] | None
) -> bool:
    return (
        client_module_id == "codex-0.149-responses-v1"
        and server_context is not None
    )


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


def _validate_compact_response(
    provider_response: ProviderResponse,
    *,
    codex_compaction: bool = False,
) -> CodexCompactionReplayCandidate | None:
    payload = provider_response.json_body
    if not codex_compaction and payload.get("object") != "response.compaction":
        raise ProviderError(
            "Provider returned an invalid Responses compact response.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="provider_response_invalid",
        )
    raw_usage = payload.get("usage")
    if provider_response.usage is None or not isinstance(raw_usage, Mapping):
        raise ProviderError(
            "Provider Responses compact response did not include usage metadata.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="responses_compact_usage_missing",
        )
    if not codex_compaction:
        return None
    if (
        set(payload) - {"output", "usage", "id", "object", "created_at"}
        or "output" not in payload
        or "usage" not in payload
        or ("object" in payload and payload["object"] != "response.compaction")
        or ("id" in payload and not _valid_codex_compact_response_id(payload["id"]))
        or (
            "created_at" in payload
            and not _valid_codex_compact_created_at(payload["created_at"])
        )
        or not _valid_codex_compact_usage(raw_usage, provider_response.usage)
    ):
        raise ProviderError(
            "Provider returned an invalid Codex compact response.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="responses_codex_compaction_response_invalid",
        )
    output = payload.get("output")
    if not isinstance(output, list) or len(output) != 1:
        raise ProviderError(
            "Provider returned an invalid Codex compact response.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="responses_codex_compaction_response_invalid",
        )
    item = output[0]
    if not isinstance(item, Mapping) or set(item) != {"type", "id", "encrypted_content"}:
        raise ProviderError(
            "Provider returned an invalid Codex compact response.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="responses_codex_compaction_response_invalid",
        )
    item_id = item.get("id")
    encrypted_content = item.get("encrypted_content")
    if (
        item.get("type") != "compaction"
        or not isinstance(item_id, str)
        or not item_id
        or len(item_id) > 128
        or not item_id.isascii()
        or not all(character.isalnum() or character in "._:-" for character in item_id)
        or not item_id[0].isalnum()
        or not isinstance(encrypted_content, str)
        or not encrypted_content
        or len(encrypted_content.encode("utf-8")) > 1_048_576
    ):
        raise ProviderError(
            "Provider returned an invalid Codex compact response.",
            provider=provider_response.provider,
            upstream_status_code=provider_response.status_code,
            error_code="responses_codex_compaction_response_invalid",
        )
    return CodexCompactionReplayCandidate(
        item_kind="compaction",
        item_id=item_id,
        call_id=None,
        tool_namespace=None,
        tool_name=None,
        encrypted_content=encrypted_content,
    )


def _valid_codex_compact_response_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value.encode("utf-8")) <= 512
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
    )


def _valid_codex_compact_created_at(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= 2**63 - 1


def _valid_codex_compact_usage(raw: Mapping[str, object], usage: ProviderUsage) -> bool:
    allowed = {
        "input_tokens",
        "input_tokens_details",
        "output_tokens",
        "output_tokens_details",
        "total_tokens",
    }
    if set(raw) - allowed:
        return False

    def _count(value: object) -> bool:
        return not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= 2**63 - 1

    input_tokens = raw.get("input_tokens")
    output_tokens = raw.get("output_tokens")
    total_tokens = raw.get("total_tokens")
    if not all(_count(value) for value in (input_tokens, output_tokens, total_tokens)):
        return False
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert isinstance(total_tokens, int)
    if total_tokens != input_tokens + output_tokens:
        return False
    if (
        usage.prompt_tokens != input_tokens
        or usage.completion_tokens != output_tokens
        or usage.total_tokens != total_tokens
    ):
        return False

    input_details = raw.get("input_tokens_details")
    if input_details is not None:
        if not isinstance(input_details, Mapping) or set(input_details) - {
            "cached_tokens",
            "cache_write_tokens",
        }:
            return False
        cached_tokens = input_details.get("cached_tokens", 0)
        cache_write_tokens = input_details.get("cache_write_tokens", 0)
        if not _count(cached_tokens) or not _count(cache_write_tokens):
            return False
        assert isinstance(cached_tokens, int)
        assert isinstance(cache_write_tokens, int)
        if cached_tokens + cache_write_tokens > input_tokens:
            return False
        if (
            usage.cached_tokens != input_details.get("cached_tokens")
            or usage.cache_write_tokens != input_details.get("cache_write_tokens")
        ):
            return False
    elif usage.cached_tokens is not None or usage.cache_write_tokens is not None:
        return False

    output_details = raw.get("output_tokens_details")
    if output_details is not None:
        if not isinstance(output_details, Mapping) or set(output_details) - {"reasoning_tokens"}:
            return False
        reasoning_tokens = output_details.get("reasoning_tokens", 0)
        if not _count(reasoning_tokens):
            return False
        assert isinstance(reasoning_tokens, int)
        if reasoning_tokens > output_tokens:
            return False
        if usage.reasoning_tokens != output_details.get("reasoning_tokens"):
            return False
    elif usage.reasoning_tokens is not None:
        return False
    return True


async def handle_response_input_tokens_count(
    *,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None = None,
):
    client_module = _resolve_responses_client_module(authenticated_key)
    _ensure_client_module_pair_exists(client_module.module_id)
    body = payload.model_dump(mode="python", exclude_none=True, exclude_unset=True)
    policy = ResponsesRequestPolicy(
        settings=settings,
        client_spec=client_module.policy_spec,
    )
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
    client_module = _resolve_responses_client_module(authenticated_key)
    try:
        raw_body = payload.model_dump(mode="python", exclude_none=True, exclude_unset=True)
        body = (
            raw_body
            if client_module.module_id == DEFAULT_CLIENT_MODULE_ID
            else client_module.normalize(RESPONSES_COMPACT_ENDPOINT, raw_body).body
        )
    except ModuleSelectionError as exc:
        raise _openai_error_from_client_module_error(exc) from exc
    for field in ("parallel_tool_calls", "reasoning", "prompt_cache_key", "text"):
        if field in payload.model_fields_set and field not in body:
            body[field] = None
    codex_compaction_requested = responses_codex_compaction_requested(body)
    allow_codex_compaction = responses_codex_compaction_allowed(authenticated_key.responses_policy)
    policy = ResponsesRequestPolicy(
        settings=settings,
        client_spec=client_module.policy_spec,
    )
    try:
        policy_result = policy.apply_compact(
            body,
            allow_codex_compaction=allow_codex_compaction,
        )
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    replay_candidates = codex_replay_request_candidates(policy_result.effective_body)
    replay_authorization = await _verify_owned_codex_replay_references(
        candidates=replay_candidates,
        authenticated_key=authenticated_key,
        settings=settings,
        request=request,
    )
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
        codex_request_envelope_requested=codex_compaction_requested,
        codex_client_tools_requested=codex_compaction_requested,
        codex_streaming_tool_events_requested=codex_compaction_requested,
        codex_encrypted_reasoning_replay_requested=codex_compaction_requested,
        codex_extended_limits_requested=codex_compaction_requested,
        codex_compaction_requested=codex_compaction_requested,
        request=request,
    )
    _ensure_client_server_pair(client_module.module_id, route)
    _reject_local_coding_auxiliary_endpoint(route)
    if codex_compaction_requested:
        try:
            policy_result = apply_codex_route_limits(
                policy_result,
                route_capabilities=route.capabilities,
                settings=settings,
                include_output_field=False,
                reserve_route_max_output=True,
            )
        except RequestPolicyError as exc:
            raise openai_error_from_request_policy_error(exc) from exc
    _verify_codex_replay_route(
        authorization=replay_authorization,
        route=route,
        compact_endpoint=codex_compaction_requested,
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
        quota = await _reserve_responses_quota(
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            request_id=request_id,
            settings=settings,
            request=request,
            endpoint=RESPONSES_COMPACT_ENDPOINT,
        )
        cost_estimate = quota.cost_estimate
        reservation = quota.reservation
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
            compact_candidate = _validate_compact_response(
                provider_response,
                codex_compaction=codex_compaction_requested,
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
            if compact_candidate is not None:
                await _persist_codex_replay_references(
                    candidates=(compact_candidate,),
                    authenticated_key=authenticated_key,
                    usage_ledger_id=accounting_result.usage_ledger_id,
                    request_id=request_id,
                    route=route,
                    settings=settings,
                    request=request,
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
        except CodexReplayReferenceError as exc:
            raise _openai_error_from_codex_replay_error(exc) from exc

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
    client_module = _resolve_responses_client_module(authenticated_key)
    try:
        raw_body = payload.model_dump(mode="python", exclude_none=True, exclude_unset=True)
        normalized_client_request = (
            normalize_default_client_request("/v1/responses", raw_body)
            if client_module.module_id == DEFAULT_CLIENT_MODULE_ID
            else client_module.normalize_responses(raw_body)
        )
    except ModuleSelectionError as exc:
        raise _openai_error_from_client_module_error(exc) from exc
    body = normalized_client_request.body
    _ensure_client_module_pair_exists(client_module.module_id)
    adapter_managed_candidates = frozenset(
        normalized_client_request.adapter_managed_declaration_candidates
    )
    for field in (
        "client_metadata",
        "include",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
    ):
        if field in payload.model_fields_set and field not in body:
            body[field] = None
    external_web_search_requested = any(
        isinstance(tool, Mapping) and tool.get("type") == "web_search"
        for tool in body.get("tools", [])
    ) if isinstance(body.get("tools", []), list) and "web_search" not in adapter_managed_candidates else False
    allow_external_tool_request = _key_allows_external_web_search(
        authenticated_key
    ) if external_web_search_requested else False
    codex_client_tools_requested = responses_codex_client_tools_requested(body)
    codex_request_envelope_requested = (
        responses_codex_request_envelope_requested(body) or codex_client_tools_requested
    )
    allow_codex_request_envelope = responses_codex_request_envelope_allowed(
        authenticated_key.responses_policy
    )
    allow_codex_client_tools = responses_codex_client_tools_allowed(
        authenticated_key.responses_policy
    )
    codex_client_tool_taxonomy = codex_client_tool_taxonomy_id(
        authenticated_key.responses_policy
    )
    codex_streaming_tool_events_requested = responses_codex_streaming_tool_events_requested(body)
    allow_codex_streaming_tool_events = responses_codex_streaming_tool_events_allowed(
        authenticated_key.responses_policy
    )
    codex_encrypted_reasoning_replay_requested = (
        responses_codex_encrypted_reasoning_replay_requested(body)
    )
    allow_codex_encrypted_reasoning_replay = responses_codex_encrypted_reasoning_replay_allowed(
        authenticated_key.responses_policy
    )
    allow_codex_extended_limits = responses_codex_extended_limits_allowed(
        authenticated_key.responses_policy
    )
    allow_codex_compaction = responses_codex_compaction_allowed(authenticated_key.responses_policy)
    codex_compaction_replay_requested = responses_codex_compaction_replay_requested(body)
    codex_extended_limits_requested = (
        codex_request_envelope_requested and allow_codex_extended_limits
    )
    codex_encrypted_reasoning_event_requested = codex_encrypted_reasoning_replay_requested or (
        allow_codex_encrypted_reasoning_replay
        and client_module.encrypted_reasoning_output_requested(body)
    )
    policy = ResponsesRequestPolicy(
        settings=settings,
        client_spec=client_module.policy_spec,
    )
    try:
        policy_result = policy.apply(
            body,
            allow_store=True,
            allow_codex_request_envelope=allow_codex_request_envelope,
            allow_codex_client_tools=allow_codex_client_tools,
            allow_codex_streaming_tool_events=allow_codex_streaming_tool_events,
            allow_codex_encrypted_reasoning_replay=(allow_codex_encrypted_reasoning_replay),
            allow_codex_extended_limits=codex_extended_limits_requested,
            allow_codex_compaction_replay=allow_codex_compaction,
            codex_client_tool_taxonomy=codex_client_tool_taxonomy,
            allow_external_tool_request=allow_external_tool_request,
            adapter_managed_declaration_candidates=frozenset(
                normalized_client_request.adapter_managed_declaration_candidates
            ),
            adapter_managed_declaration_shapes=(
                normalized_client_request.adapter_managed_declaration_shapes
            ),
        )
    except RequestPolicyError as exc:
        raise openai_error_from_request_policy_error(exc) from exc

    replay_candidates = codex_replay_request_candidates(policy_result.effective_body)
    replay_authorization = await _verify_owned_codex_replay_references(
        candidates=replay_candidates,
        authenticated_key=authenticated_key,
        settings=settings,
        request=request,
    )
    request_id = _request_id_from_request(request)
    route = await _resolve_responses_route(
        authenticated_key=authenticated_key,
        effective_model=policy_result.effective_body["model"],
        endpoint=RESPONSES_ENDPOINT,
        streaming_requested=policy_result.effective_body.get("stream") is True,
        text_format_type=responses_text_format_type(policy_result.effective_body),
        function_tools_requested=(
            responses_function_tools_requested(policy_result.effective_body)
            and not codex_client_tools_requested
        ),
        custom_tools_requested=(
            responses_custom_tools_requested(policy_result.effective_body)
            and not codex_client_tools_requested
        ),
        image_input_requested=responses_image_input_requested(policy_result.effective_body),
        file_input_requested=responses_file_input_requested(policy_result.effective_body),
        input_token_count_requested=False,
        stored_responses_requested=policy_result.effective_body.get("store") is True,
        previous_response_id_requested=previous_response_id_requested(policy_result.effective_body),
        compact_requested=False,
        conversations_requested=conversation_requested(policy_result.effective_body),
        codex_request_envelope_requested=codex_request_envelope_requested,
        codex_client_tools_requested=codex_client_tools_requested,
        codex_streaming_tool_events_requested=codex_streaming_tool_events_requested,
        codex_encrypted_reasoning_replay_requested=(codex_encrypted_reasoning_event_requested),
        codex_extended_limits_requested=codex_extended_limits_requested,
        codex_compaction_requested=codex_compaction_replay_requested,
        request=request,
    )
    _ensure_client_server_pair(client_module.module_id, route)
    local_coding_server_context = _build_local_coding_server_context(
        client_request=normalized_client_request,
        authenticated_key=authenticated_key,
        route=route,
        settings=settings,
    )
    try:
        enforce_openai_compatible_request_boundary(
            policy_result.effective_body,
            route=route,
            endpoint="responses",
        )
    except OpenAICompatibleRequestBoundaryError as exc:
        raise OpenAICompatibleError(
            "Remote image URLs are not enabled for generic OpenAI-compatible providers.",
            status_code=400,
            error_type="invalid_request_error",
            code="openai_compatible_remote_image_not_allowed",
            param=exc.param,
        ) from exc
    if codex_extended_limits_requested:
        try:
            policy_result = apply_codex_route_limits(
                policy_result,
                route_capabilities=route.capabilities,
                settings=settings,
            )
        except RequestPolicyError as exc:
            raise openai_error_from_request_policy_error(exc) from exc
    _verify_codex_replay_route(
        authorization=replay_authorization,
        route=route,
    )
    external_web_search_admission = None
    if external_web_search_requested:
        try:
            external_web_search_admission = admit_web_search_request(
                policy_result.effective_body,
                authenticated_key=authenticated_key,
                route_provider=route.provider,
                route_capabilities=route.capabilities,
            )
        except ExternalToolRuntimeError as exc:
            raise OpenAICompatibleError(
                "The requested hosted web-search contract is not enabled for this key and route.",
                status_code=400,
                error_type="invalid_request_error",
                code="responses_external_tool_not_allowed",
            ) from exc
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
    external_pricing_lookup = None
    if external_web_search_admission is not None:
        external_pricing_lookup = await _validate_external_tool_pricing(
            route=route,
            endpoint=RESPONSES_ENDPOINT,
            request=request,
        )
    rate_limit_reservation = await _reserve_redis_rate_limit(
        authenticated_key=authenticated_key,
        policy_result=policy_result,
        request_id=request_id,
        settings=settings,
        request=request,
    )
    try:
        quota = await _reserve_responses_quota(
            authenticated_key=authenticated_key,
            route=route,
            policy_result=policy_result,
            request_id=request_id,
            settings=settings,
            request=request,
            external_tool_admission=external_web_search_admission,
            external_pricing_facts=external_pricing_lookup,
        )
        cost_estimate = quota.cost_estimate
        reservation = quota.reservation
        if external_web_search_admission is not None:
            if quota.external_tool_pricing is None:
                raise OpenAICompatibleError(
                    "External-tool pricing is not configured for the resolved model.",
                    status_code=500,
                    error_type="server_error",
                    code="external_tool_pricing_missing",
                )
            external_web_search_admission = with_pricing(
                external_web_search_admission,
                pricing=quota.external_tool_pricing,
            )

        pre_provider_live_burn = pre_provider_responses_streaming_live_burn_error(
            quota.live_burn_budget
        )
        if (
            policy_result.effective_body.get("stream") is True
            and pre_provider_live_burn is not None
        ):
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
            increment_quota_rejection(RESPONSES_STREAMING_LIVE_BURN_ERROR_CODE)
            raise OpenAICompatibleError(
                RESPONSES_STREAMING_LIVE_BURN_ERROR_MESSAGE,
                status_code=429,
                error_type="insufficient_quota",
                code=RESPONSES_STREAMING_LIVE_BURN_ERROR_CODE,
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
                    live_burn_budget=quota.live_burn_budget,
                    stream_validation_profile=ResponsesStreamValidationProfile(
                        codex_streaming_tool_events=codex_streaming_tool_events_requested,
                        codex_reasoning_events=_codex_reasoning_events_enabled(
                            client_module_id=client_module.module_id,
                            server_context=local_coding_server_context,
                        ),

                        codex_encrypted_reasoning_replay=(
                            codex_encrypted_reasoning_event_requested
                        ),
                            declared_client_tools=codex_client_tool_declarations(
                                policy_result.effective_body
                            ),
                            web_search=external_web_search_admission is not None,
                            web_search_max_tool_calls=(
                                external_web_search_admission.request.effective_tool_call_cap
                                if external_web_search_admission is not None
                                else None
                            ),
                    ),
                    external_web_search_admission=external_web_search_admission,
                    external_tool_pricing=quota.external_tool_pricing,
                    server_context=local_coding_server_context,
                )
                return response
            except ProviderError as exc:
                client_provider_error = (
                    _safe_external_provider_error(exc)
                    if external_web_search_admission is not None
                    else exc
                )
                await _record_provider_failure_and_release(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=client_provider_error,
                    request=request,
                    streaming=True,
                    external_tool=external_web_search_admission is not None,
                )
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                rate_limit_reservation = None
                raise openai_error_from_provider_error(client_provider_error) from exc
            except Exception as exc:
                if external_web_search_admission is not None:
                    safe_error = ProviderError(
                        "The upstream provider could not be constructed.",
                        provider=route.provider,
                        error_code="provider_configuration_error",
                    )
                    await _record_provider_failure_and_release(
                        reservation=reservation,
                        authenticated_key=authenticated_key,
                        route=route,
                        policy_result=policy_result,
                        cost_estimate=cost_estimate,
                        request_id=request_id,
                        provider_error=safe_error,
                        request=request,
                        streaming=True,
                        external_tool=True,
                    )
                    raise openai_error_from_provider_error(safe_error) from exc
                await _release_rate_limit_concurrency(rate_limit_reservation, suppress=True)
                raise

        provider_request = ProviderRequest(
            provider=route.provider,
            upstream_model=route.resolved_model,
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
            body=upstream_body,
            request_id=request_id,
            server_context=local_coding_server_context,
        )
        provider_started = False
        try:
            adapter = get_provider_adapter(route, settings)
            provider_started = True
            provider_response = await observe_provider_call(
                provider=route.provider,
                endpoint=RESPONSES_PROVIDER_ENDPOINT,
                call=lambda: adapter.forward_response(provider_request),
            )
        except ProviderError as exc:
            if external_web_search_admission is not None and provider_started:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    reason_code=ExternalToolHoldReasonCode.PROVIDER_ERROR_UNKNOWN_CHARGE,
                    evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    estimated_cost_eur=(
                        cost_estimate.estimated_total_cost_eur
                        + _external_tool_max_fee_eur(external_web_search_admission, cost_estimate)
                    ),
                )
            else:
                await _record_provider_failure_and_release(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=exc,
                    request=request,
                    external_tool=(
                        external_web_search_admission is not None and not provider_started
                    ),
                )
            client_provider_error = (
                _safe_external_provider_error(exc)
                if external_web_search_admission is not None
                else exc
            )
            raise openai_error_from_provider_error(client_provider_error) from exc
        except Exception as exc:  # noqa: BLE001
            safe_provider_error = ProviderError(
                "The upstream provider call failed.",
                provider=route.provider,
                error_code="provider_request_error",
            )
            if external_web_search_admission is not None and provider_started:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    reason_code=ExternalToolHoldReasonCode.PROVIDER_ERROR_UNKNOWN_CHARGE,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    estimated_cost_eur=(
                        cost_estimate.estimated_total_cost_eur
                        + _external_tool_max_fee_eur(external_web_search_admission, cost_estimate)
                    ),
                )
            else:
                await _record_provider_failure_and_release(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=safe_provider_error,
                    request=request,
                    external_tool=(
                        external_web_search_admission is not None and not provider_started
                    ),
                )
            raise openai_error_from_provider_error(safe_provider_error) from exc

        try:
            if external_web_search_admission is not None:
                accounting_result = await _finalize_external_web_search_response(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    provider_response=provider_response,
                    request_id=request_id,
                    request=request,
                    admission=external_web_search_admission,
                )
            else:
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
            if external_web_search_admission is not None:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    estimated_cost_eur=(
                        cost_estimate.estimated_total_cost_eur
                        + _external_tool_max_fee_eur(external_web_search_admission, cost_estimate)
                    ),
                )
            increment_accounting_failure(exc.error_code)
            raise openai_error_from_accounting_error(exc) from exc
        except QuotaError as exc:
            increment_quota_rejection(exc.error_code)
            raise openai_error_from_quota_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            if external_web_search_admission is not None:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    estimated_cost_eur=(
                        cost_estimate.estimated_total_cost_eur
                        + _external_tool_max_fee_eur(external_web_search_admission, cost_estimate)
                    ),
                )
                raise OpenAICompatibleError(
                    "External-tool accounting could not be finalized safely.",
                    status_code=500,
                    error_type="server_error",
                    code="external_tool_accounting_uncertain",
                ) from exc
            raise

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
    _validate_response_retrieve_query(request)
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


async def _verify_owned_codex_replay_references(
    *,
    candidates: tuple[CodexReplayRequestCandidate | CodexCompactionReplayCandidate, ...],
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
    request: Request | None,
) -> CodexReplayAuthorization:
    if not candidates:
        return CodexReplayAuthorization(references=())
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc
    try:
        service = CodexReplayService(
            repository=CodexReplayReferencesRepository(session),
            settings=settings,
        )
        try:
            return await service.verify_owned_replay(
                candidates=candidates,
                gateway_key_id=authenticated_key.gateway_key_id,
            )
        except CodexReplayReferenceError as exc:
            raise _openai_error_from_codex_replay_error(exc) from exc
    finally:
        await session_iterator.aclose()


def _resolve_responses_client_module(
    authenticated_key: AuthenticatedGatewayKey,
):
    try:
        return resolve_responses_client_module(getattr(authenticated_key, "responses_policy", None))
    except ModuleSelectionError as exc:
        raise _openai_error_from_client_module_error(exc) from exc


def _openai_error_from_client_module_error(exc: ModuleSelectionError) -> OpenAICompatibleError:
    return OpenAICompatibleError(
        "The selected client module is unavailable for this request.",
        status_code=400,
        error_type="invalid_request_error",
        code=exc.error_code,
    )


def _ensure_client_server_pair(client_module_id: str, route: RouteResolutionResult) -> None:
    try:
        descriptor = resolve_server_module(
            route.provider,
            getattr(route, "provider_kind", None),
            getattr(route, "capabilities", None),
        )
        ensure_client_server_pair(client_module_id, descriptor.module_id)
    except ProviderConfigurationError as exc:
        raise OpenAICompatibleError(
            "The selected client and server modules are not compatible.",
            status_code=400,
            error_type="invalid_request_error",
            code="incompatible_client_server_pair",
        ) from exc


def _ensure_client_module_pair_exists(client_module_id: str) -> None:
    try:
        ensure_client_module_has_server_pair(client_module_id)
    except ProviderConfigurationError as exc:
        raise OpenAICompatibleError(
            "The selected client and server modules are not compatible.",
            status_code=400,
            error_type="invalid_request_error",
            code="incompatible_client_server_pair",
        ) from exc


def _reject_local_coding_auxiliary_endpoint(route: RouteResolutionResult) -> None:
    try:
        descriptor = resolve_server_module(
            route.provider,
            getattr(route, "provider_kind", None),
            getattr(route, "capabilities", None),
        )
    except ProviderConfigurationError as exc:
        raise OpenAICompatibleError(
            "The selected server module is unavailable for this endpoint.",
            status_code=400,
            error_type="invalid_request_error",
            code="local_coding_endpoint_not_supported",
        ) from exc
    if descriptor.module_id == LOCAL_CODING_SERVER_MODULE_ID:
        raise OpenAICompatibleError(
            "The Local Coding server module supports Responses create only.",
            status_code=400,
            error_type="invalid_request_error",
            code="local_coding_endpoint_not_supported",
        )


def _verify_codex_replay_route(
    *,
    authorization: CodexReplayAuthorization,
    route: RouteResolutionResult,
    compact_endpoint: bool = False,
) -> None:
    try:
        compatible_route_ids = (
            parse_codex_compaction_compatible_route_ids(route.capabilities)
            if compact_endpoint
            or any(reference.item_kind == "compaction" for reference in authorization.references)
            else frozenset()
        )
        CodexReplayService.verify_route_compatibility(
            authorization,
            provider=route.provider,
            route_id=route.route_id,
            upstream_model=route.resolved_model,
            compatible_route_ids=compatible_route_ids,
            allow_compact_endpoint_route_compatibility=compact_endpoint,
        )
    except CodexReplayReferenceError as exc:
        raise _openai_error_from_codex_replay_error(exc) from exc


def _openai_error_from_codex_replay_error(
    error: CodexReplayReferenceError,
) -> OpenAICompatibleError:
    unavailable = error.error_code == "responses_codex_replay_hmac_unavailable"
    persistence = error.error_code == "responses_codex_replay_persistence_failed"
    return OpenAICompatibleError(
        error.safe_message,
        status_code=503 if unavailable else 500 if persistence else 404,
        error_type="server_error" if unavailable or persistence else "invalid_request_error",
        code=error.error_code,
    )


async def _persist_codex_replay_references(
    *,
    candidates: tuple[
        CodexReplayStreamCandidate | CodexReplayRequestCandidate | CodexCompactionReplayCandidate,
        ...,
    ],
    authenticated_key: AuthenticatedGatewayKey,
    usage_ledger_id: uuid.UUID,
    request_id: str,
    route: RouteResolutionResult,
    settings: Settings,
    request: Request | None,
) -> int:
    if not candidates:
        return 0
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise CodexReplayReferenceError(
            "Codex replay references could not be persisted safely.",
            error_code="responses_codex_replay_persistence_failed",
        ) from exc
    try:
        service = CodexReplayService(
            repository=CodexReplayReferencesRepository(session),
            settings=settings,
        )
        try:
            count = await service.persist_validated_references(
                candidates=candidates,
                gateway_key_id=authenticated_key.gateway_key_id,
                usage_ledger_id=usage_ledger_id,
                source_request_id=request_id,
                provider=route.provider,
                route_id=route.route_id,
                upstream_model=route.resolved_model,
            )
            await session.commit()
            return count
        except CodexReplayReferenceError:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise CodexReplayReferenceError(
                "Codex replay references could not be persisted safely.",
                error_code="responses_codex_replay_persistence_failed",
            ) from None
    finally:
        await session_iterator.aclose()


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
    codex_request_envelope_requested: bool = False,
    codex_client_tools_requested: bool = False,
    codex_streaming_tool_events_requested: bool = False,
    codex_encrypted_reasoning_replay_requested: bool = False,
    codex_extended_limits_requested: bool = False,
    codex_compaction_requested: bool = False,
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
                codex_request_envelope_requested=codex_request_envelope_requested,
                codex_client_tools_requested=codex_client_tools_requested,
                codex_streaming_tool_events_requested=(codex_streaming_tool_events_requested),
                codex_encrypted_reasoning_replay_requested=(
                    codex_encrypted_reasoning_replay_requested
                ),
                codex_extended_limits_requested=codex_extended_limits_requested,
                codex_compaction_requested=codex_compaction_requested,
            )
        except RouteResolutionError as exc:
            raise openai_error_from_route_resolution_error(exc) from exc
        except RequestPolicyError as exc:
            raise openai_error_from_request_policy_error(exc) from exc
        return route
    finally:
        await session_iterator.aclose()


async def _validate_external_tool_pricing(
    *,
    route: RouteResolutionResult,
    endpoint: str,
    request: Request | None,
):
    """Validate immutable hosted-tool pricing before any Redis or fence mutation."""
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
            pricing_row = await pricing_service.find_active_pricing_rule(
                provider=route.provider,
                model=route.resolved_model,
                endpoint=endpoint,
            )
        except PricingError as exc:
            raise openai_error_from_pricing_error(exc) from exc
        if pricing_row.external_tool_pricing is None:
            raise openai_error_from_pricing_error(
                PricingError(
                    "External-tool pricing is not configured for the resolved model.",
                    param="model",
                )
            )
        pricing_currency = getattr(
            pricing_row,
            "currency",
            pricing_row.external_tool_pricing.currency,
        )
        _, fx = await pricing_service.convert_to_eur(Decimal("0"), pricing_currency)
        return _ExternalToolPricingFacts(lookup=pricing_row, fx=fx)
    finally:
        await session_iterator.aclose()


async def _reserve_responses_quota(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    request_id: str,
    settings: Settings,
    request: Request | None,
    endpoint: str = RESPONSES_ENDPOINT,
    external_tool_admission=None,
    external_pricing_facts: _ExternalToolPricingFacts | None = None,
) -> _ResponsesQuotaReservation:
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
            estimate_kwargs = {
                "route": route,
                "policy": policy_result,
                "endpoint": endpoint,
            }
            if external_pricing_facts is not None:
                estimate_kwargs["pricing"] = external_pricing_facts.lookup
                estimate_kwargs["fx"] = external_pricing_facts.fx
            cost_estimate = await pricing_service.estimate_chat_completion_cost(**estimate_kwargs)
        except PricingError as exc:
            raise openai_error_from_pricing_error(exc) from exc

        external_tool_pricing = (
            external_pricing_facts.lookup.external_tool_pricing
            if external_pricing_facts is not None
            else None
        )
        if external_tool_admission is not None:
            if external_tool_pricing is None:
                raise openai_error_from_pricing_error(
                    PricingError(
                        "External-tool pricing is not configured for the resolved model.",
                        param="model",
                    )
                )

            fence_service = ExternalToolFenceService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            fence_route_id = route.route_id
            try:
                fence_route_id = uuid.UUID(str(fence_route_id))
            except (TypeError, ValueError, AttributeError) as exc:
                raise OpenAICompatibleError(
                    "The resolved route has no durable route identifier for external-tool accounting.",
                    status_code=500,
                    error_type="server_error",
                    code="external_tool_route_id_missing",
                ) from exc
            if fence_route_id is None:
                raise OpenAICompatibleError(
                    "The resolved route has no durable route identifier for external-tool accounting.",
                    status_code=500,
                    error_type="server_error",
                    code="external_tool_route_id_missing",
                )
            try:
                fence_result = await fence_service.acquire(
                    ExternalToolFenceAcquireInput(
                        gateway_key_id=authenticated_key.gateway_key_id,
                        request_id=request_id,
                        route=ExternalToolFenceRouteFacts(
                            endpoint=endpoint,
                            requested_model=route.requested_model,
                            provider=route.provider,
                            route_id=fence_route_id,
                        ),
                        capabilities=(external_tool_admission.request.capability,),
                        destination_ids=(),
                        decision=external_tool_admission.decision,
                        now=datetime.now(UTC),
                    )
                )
            except ExternalToolFenceError as exc:
                raise OpenAICompatibleError(
                    exc.safe_message,
                    status_code=exc.status_code,
                    error_type=exc.error_type,
                    code=exc.error_code,
                ) from exc
            reservation = QuotaReservationResult(
                reservation_id=fence_result.reservation_id,
                gateway_key_id=fence_result.gateway_key_id,
                request_id=fence_result.request_id,
                reserved_cost_eur=fence_result.reserved_cost_eur,
                reserved_tokens=fence_result.reserved_tokens,
                status="pending",
                expires_at=fence_result.expires_at,
            )
            live_burn_budget = None
            if hasattr(session, "commit"):
                await session.commit()
            return _ResponsesQuotaReservation(
                cost_estimate=cost_estimate,
                reservation=reservation,
                live_burn_budget=live_burn_budget,
                external_tool_pricing=external_tool_pricing,
            )

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
                endpoint=endpoint,
            )
        except QuotaError as exc:
            increment_quota_rejection(quota_exc_code(exc))
            raise openai_error_from_quota_error(exc) from exc

        gateway_key = None
        try:
            gateway_key = await gateway_keys_repository.get_gateway_key_by_id(
                authenticated_key.gateway_key_id
            )
        except Exception:  # noqa: BLE001
            gateway_key = None
        live_burn_budget = _build_responses_streaming_live_burn_budget(
            authenticated_key=authenticated_key,
            gateway_key=gateway_key,
            reservation=reservation,
            cost_estimate=cost_estimate,
            settings=settings,
        )

        if hasattr(session, "commit"):
            await session.commit()
        return _ResponsesQuotaReservation(
            cost_estimate=cost_estimate,
            reservation=reservation,
            live_burn_budget=live_burn_budget,
            external_tool_pricing=external_tool_pricing,
        )
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
    live_burn_budget: ResponsesStreamingLiveBurnBudget | None,
    stream_validation_profile: ResponsesStreamValidationProfile | None = None,
    external_web_search_admission=None,
    external_tool_pricing=None,
    server_context: Mapping[str, object] | None = None,
) -> StreamingResponse:
    adapter = get_provider_adapter(route, settings)
    provider_request = ProviderRequest(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint=RESPONSES_PROVIDER_ENDPOINT,
        body=upstream_body,
        request_id=request_id,
        server_context=server_context,
    )

    async def _events():
        start = time.perf_counter()
        completed_chunk: ProviderStreamChunk | None = None
        upstream_request_id: str | None = None
        completed_event: str | None = None
        terminal_done_event: str | None = None
        completed = False
        provider_status = "error"
        stream_estimate_monitor = build_responses_streaming_estimate_monitor(
            cost_estimate=cost_estimate,
            estimate_multiplier=settings.RESPONSES_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER,
            budget=live_burn_budget,
        )
        stream_event_validator = ResponsesStreamEventValidator(
            stream_validation_profile or ResponsesStreamValidationProfile()
        )
        external_tool_hold_fee_eur = Decimal("0")
        if external_web_search_admission is not None and external_tool_pricing is not None:
            if external_tool_pricing.currency == cost_estimate.native_currency:
                hold_fx_rate = cost_estimate.fx_rate
            elif external_tool_pricing.currency == "EUR":
                hold_fx_rate = Decimal("1")
            else:
                hold_fx_rate = None
            if hold_fx_rate is not None:
                external_tool_hold_fee_eur = (
                    external_web_search_admission.maximum_fee_native * hold_fx_rate
                )
        heartbeat_stop = asyncio.Event()
        heartbeat_task = _start_rate_limit_heartbeat(
            rate_limit_reservation,
            stop_event=heartbeat_stop,
        )
        try:
            async for chunk in adapter.stream_response(provider_request):
                if chunk.upstream_request_id:
                    upstream_request_id = chunk.upstream_request_id
                if chunk.is_done:
                    terminal_done_event = chunk.raw_sse_event
                    continue
                if not stream_event_validator.validate(chunk.json_body):
                    event_type = (
                        chunk.json_body.get("type") if isinstance(chunk.json_body, dict) else None
                    )
                    provider_failure = event_type in RESPONSES_PROVIDER_FAILURE_EVENT_TYPES
                    error_code = (
                        "responses_stream_provider_failure"
                        if provider_failure
                        else "responses_stream_event_not_supported"
                    )
                    safe_message = (
                        "Provider reported a failure during Responses streaming."
                        if provider_failure
                        else (
                            "Provider emitted a Responses streaming event that is not supported "
                            "by this gateway."
                        )
                    )
                    if external_web_search_admission is not None:
                        await _place_external_web_search_hold(
                            reservation=reservation,
                            authenticated_key=authenticated_key,
                            request_id=request_id,
                            request=request,
                            streaming=True,
                            reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
                            evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                        )
                    else:
                        await _finalize_responses_stream_interruption_after_output(
                            reservation=reservation,
                            authenticated_key=authenticated_key,
                            route=route,
                            policy_result=policy_result,
                            cost_estimate=cost_estimate,
                            request_id=request_id,
                            provider_error=ProviderError(
                                safe_message,
                                provider=route.provider,
                                upstream_status_code=200,
                                error_code=error_code,
                            ),
                            request=request,
                            estimate_reason="responses_streaming_provider_error_estimated",
                            stream_estimate_monitor=stream_estimate_monitor,
                        )
                    provider_status = "incomplete"
                    yield format_responses_error_event(
                        message=safe_message,
                        code=error_code,
                        request_id=request_id,
                    )
                    return
                if _is_responses_completed_chunk(chunk):
                    completed = True
                    completed_event = chunk.raw_sse_event
                    completed_chunk = chunk
                    continue
                live_burn_estimate = stream_estimate_monitor.observe_chunk(chunk.json_body)
                if live_burn_estimate is not None:
                    if external_web_search_admission is not None:
                        await _place_external_web_search_hold(
                            reservation=reservation,
                            authenticated_key=authenticated_key,
                            request_id=request_id,
                            request=request,
                            streaming=True,
                            reason_code=ExternalToolHoldReasonCode.AMBIGUOUS_FINAL_COST,
                            evidence_quality=ExternalToolHoldEvidenceQuality.PARTIAL_ESTIMATE,
                            partial_total_tokens=live_burn_estimate.estimated_total_tokens,
                            estimated_cost_eur=(
                                live_burn_estimate.estimated_cost_eur + external_tool_hold_fee_eur
                            ),
                        )
                    else:
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
                    yield format_responses_error_event(
                        message=RESPONSES_STREAMING_LIVE_BURN_ERROR_MESSAGE,
                        code=RESPONSES_STREAMING_LIVE_BURN_ERROR_CODE,
                        request_id=request_id,
                    )
                    return
                yield chunk.raw_sse_event

            if completed and completed_chunk is not None and completed_chunk.usage is not None:
                provider_response = _provider_response_from_response_stream(
                    chunk=completed_chunk,
                    upstream_request_id=upstream_request_id,
                )
                provider_completed_record = None
                streaming_evidence = None
                if external_web_search_admission is not None:
                    streaming_evidence = parse_web_search_stream(
                        stream_event_validator.take_web_search_evidence(),
                        admitted_call_cap=external_web_search_admission.request.effective_tool_call_cap,
                        pricing=external_tool_pricing,
                        provider=route.provider,
                        tool_choice=policy_result.effective_body.get("tool_choice"),
                    )
                    if not streaming_evidence.authoritative:
                        raise AccountingError("Authoritative web-search stream evidence is required")
                else:
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
                    if external_web_search_admission is not None:
                        accounting_result = await _finalize_external_web_search_response(
                            reservation=reservation,
                            authenticated_key=authenticated_key,
                            route=route,
                            policy_result=policy_result,
                            cost_estimate=cost_estimate,
                            provider_response=provider_response,
                            request_id=request_id,
                            request=request,
                            admission=external_web_search_admission,
                            streaming=True,
                            streaming_evidence=streaming_evidence,
                        )
                    else:
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
                    if provider_completed_record is not None:
                        await _mark_provider_completed_finalization_failed(
                            usage_ledger_id=provider_completed_record.usage_ledger_id,
                            reservation_id=reservation.reservation_id,
                            error=exc,
                            request=request,
                        )
                    raise
                except QuotaError as exc:
                    if provider_completed_record is not None:
                        await _mark_provider_completed_finalization_failed(
                            usage_ledger_id=provider_completed_record.usage_ledger_id,
                            reservation_id=reservation.reservation_id,
                            error=exc,
                            request=request,
                        )
                    raise
                replay_reference_candidates = (
                    stream_event_validator.take_replay_reference_candidates()
                )
                if replay_reference_candidates:
                    try:
                        await _persist_codex_replay_references(
                            candidates=replay_reference_candidates,
                            authenticated_key=authenticated_key,
                            usage_ledger_id=(
                                provider_completed_record.usage_ledger_id
                                if provider_completed_record is not None
                                else accounting_result.usage_ledger_id
                            ),
                            request_id=request_id,
                            route=route,
                            settings=settings,
                            request=request,
                        )
                    except CodexReplayReferenceError as exc:
                        provider_status = "incomplete"
                        yield format_responses_error_event(
                            message=exc.safe_message,
                            code=exc.error_code,
                            request_id=request_id,
                        )
                        return
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
                if external_web_search_admission is not None:
                    await _place_external_web_search_hold(
                        reservation=reservation,
                        authenticated_key=authenticated_key,
                        request_id=request_id,
                        request=request,
                        streaming=True,
                        reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
                        evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    )
                else:
                    await _finalize_responses_stream_interruption_after_output(
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
                        estimate_reason="responses_streaming_usage_missing_estimated",
                        stream_estimate_monitor=stream_estimate_monitor,
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
                if external_web_search_admission is not None:
                    await _place_external_web_search_hold(
                        reservation=reservation,
                        authenticated_key=authenticated_key,
                        request_id=request_id,
                        request=request,
                        streaming=True,
                        reason_code=ExternalToolHoldReasonCode.INTERRUPTION_DISCONNECT,
                        evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    )
                else:
                    await _finalize_responses_stream_interruption_after_output(
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
                        estimate_reason="responses_streaming_client_disconnected_estimated",
                        stream_estimate_monitor=stream_estimate_monitor,
                    )
            raise
        except ProviderError as exc:
            if external_web_search_admission is not None:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    streaming=True,
                    reason_code=ExternalToolHoldReasonCode.PROVIDER_ERROR_UNKNOWN_CHARGE,
                    evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    estimated_cost_eur=(
                        cost_estimate.estimated_total_cost_eur + external_tool_hold_fee_eur
                    ),
                )
            else:
                await _finalize_responses_stream_interruption_after_output(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    route=route,
                    policy_result=policy_result,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    provider_error=exc,
                    request=request,
                    estimate_reason="responses_streaming_provider_error_estimated",
                    stream_estimate_monitor=stream_estimate_monitor,
                )
            wire_error = (
                _safe_external_provider_error(exc)
                if external_web_search_admission is not None
                else exc
            )
            yield format_responses_error_event(
                message=wire_error.safe_message,
                code=wire_error.error_code,
            )
        except AccountingError as exc:
            if external_web_search_admission is not None:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    streaming=True,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                )
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
        except Exception:  # noqa: BLE001
            if external_web_search_admission is not None:
                await _place_external_web_search_hold(
                    reservation=reservation,
                    authenticated_key=authenticated_key,
                    request_id=request_id,
                    request=request,
                    streaming=True,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    estimated_cost_eur=(
                        cost_estimate.estimated_total_cost_eur + external_tool_hold_fee_eur
                    ),
                )
                yield format_responses_error_event(
                    message="External-tool streaming accounting could not be finalized safely.",
                    code="external_tool_accounting_uncertain",
                    request_id=request_id,
                )
            else:
                raise
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
    external_tool: bool = False,
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
        if external_tool:
            fence_service = ExternalToolFenceService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            await fence_service.resolve(
                ExternalToolFenceResolveInput(
                    gateway_key_id=authenticated_key.gateway_key_id,
                    request_id=request_id,
                )
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


def _safe_external_provider_error(error: ProviderError) -> ProviderError:
    """Strip provider diagnostic text before exposing hosted-tool errors."""
    return ProviderError(
        "The upstream provider call failed.",
        provider=error.provider,
        upstream_status_code=error.upstream_status_code,
        error_type=error.error_type,
        error_code=error.error_code,
    )


async def _finalize_responses_stream_interruption_after_output(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    provider_error: ProviderError,
    request: Request | None,
    estimate_reason: str,
    stream_estimate_monitor: ResponsesStreamingLiveBurnMonitor,
) -> None:
    try:
        if stream_estimate_monitor.estimated_output_tokens > 0:
            await _record_responses_streaming_interrupted_estimate(
                reservation=reservation,
                authenticated_key=authenticated_key,
                route=route,
                cost_estimate=cost_estimate,
                request_id=request_id,
                response_metadata=safe_responses_streaming_interrupted_estimate_metadata(
                    estimated_input_tokens=cost_estimate.estimated_input_tokens,
                    estimated_output_tokens=stream_estimate_monitor.estimated_output_tokens,
                    estimated_total_tokens=stream_estimate_monitor.estimated_request_tokens,
                    estimated_cost_eur=stream_estimate_monitor.estimated_cost_eur,
                    interruption_reason=estimate_reason,
                    final_provider_usage_available=False,
                ),
                estimated_output_tokens=stream_estimate_monitor.estimated_output_tokens,
                estimated_total_tokens=stream_estimate_monitor.estimated_request_tokens,
                estimated_cost_eur=stream_estimate_monitor.estimated_cost_eur,
                endpoint=RESPONSES_PROVIDER_ENDPOINT,
                error_type=provider_error.error_code or "responses_stream_interrupted",
                error_message=provider_error.error_code or "responses_stream_interrupted",
                status_code=provider_error.upstream_status_code,
                estimate_reason=estimate_reason,
                request=request,
            )
        else:
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


async def _record_responses_streaming_interrupted_estimate(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    response_metadata: dict[str, object],
    estimated_output_tokens: int,
    estimated_total_tokens: int,
    estimated_cost_eur: Decimal,
    endpoint: str,
    error_type: str,
    error_message: str,
    status_code: int | None,
    estimate_reason: str,
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
        result = await accounting_service.record_streaming_interrupted_estimate(
            reservation.reservation_id,
            authenticated_key,
            route,
            cost_estimate,
            request_id,
            estimated_input_tokens=cost_estimate.estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_total_tokens=estimated_total_tokens,
            estimated_cost_eur=estimated_cost_eur,
            response_metadata=response_metadata,
            endpoint=endpoint,
            estimate_reason=estimate_reason,
            error_type=error_type,
            error_message=error_message,
            status_code=status_code,
        )
        if hasattr(session, "commit"):
            await session.commit()
        return result
    finally:
        await session_iterator.aclose()


async def _record_streaming_live_burn_abort_estimate(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    cost_estimate: ChatCostEstimate,
    request_id: str,
    estimate: ResponsesStreamingLiveBurnEstimate,
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
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
            estimate_reason="responses_streaming_live_burn_interrupted",
        )
        if hasattr(session, "commit"):
            await session.commit()
        return result
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


async def _finalize_external_web_search_response(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    route: RouteResolutionResult,
    policy_result: ResponsesPolicyResult,
    cost_estimate: ChatCostEstimate,
    provider_response: ProviderResponse,
    request_id: str,
    request: Request | None,
    admission,
    streaming: bool = False,
    streaming_evidence=None,
) -> FinalizedAccountingResult:
    """Finalize model usage plus authoritative content-free web-search evidence."""
    evidence = streaming_evidence or parse_web_search_output(
        provider_response.json_body,
        admitted_call_cap=admission.request.effective_tool_call_cap,
        pricing=admission.pricing if hasattr(admission, "pricing") else None,
        provider=route.provider,
        tool_choice=policy_result.effective_body.get("tool_choice"),
    )
    if not evidence.authoritative:
        raise AccountingError(
            f"Authoritative web-search accounting evidence is required ({evidence.reason_code})"
        )

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
        usage = accounting_service.extract_usage(provider_response)
        model_cost = accounting_service.compute_actual_cost(
            provider_response,
            route,
            usage,
            cost_estimate,
        )
        pricing = admission.pricing
        if pricing.currency == cost_estimate.native_currency:
            fx_rate = cost_estimate.fx_rate
        elif pricing.currency == "EUR":
            fx_rate = Decimal("1")
        else:
            fx_rate = None
        # EUR-native test doubles may omit the explicit 1:1 fact; production
        # reservations retain the pricing conversion rate before mutation.
        if fx_rate is None and cost_estimate.native_currency == "EUR":
            fx_rate = Decimal("1")
        if fx_rate is None:
            raise AccountingError("The reservation did not retain exact external-tool FX facts.")
        tool_fee_eur = (evidence.total_tool_fee_native or Decimal("0")) * fx_rate
        actual_eur = model_cost.actual_cost_eur + tool_fee_eur
        final = await accounting_service.finalize_successful_custom_response(
            reservation.reservation_id,
            authenticated_key,
            route,
            cost_estimate,
            provider_response,
            request_id,
            endpoint=RESPONSES_PROVIDER_ENDPOINT,
            usage=usage,
            actual_cost_eur=actual_eur,
            actual_cost_native=actual_eur,
            native_currency="EUR",
            cost_source="slaif_calculated",
            cost_confidence="slaif_calculated_external_tool_authoritative",
            component_costs_native={
                "model": model_cost.actual_cost_eur,
                "external_tool": tool_fee_eur,
            },
            component_token_counts={
                "model_total": usage.total_tokens,
                "external_tool_calls": evidence.completed_call_count,
            },
            response_metadata_extra={
                "external_tool_contract_version": 1,
                "external_tool_capability": evidence.capability,
                "external_tool_admitted_call_cap": evidence.admitted_call_cap,
                "external_tool_completed_call_count": evidence.completed_call_count,
                "external_tool_pricing_source": evidence.pricing_source,
                "external_tool_unit_fee_native": str(evidence.unit_tool_fee_native),
                "external_tool_total_fee_native": str(evidence.total_tool_fee_native),
                "external_tool_cost_source": "openai_published_per_call",
                "external_tool_cost_confidence": "authoritative",
            },
            streaming=streaming,
        )
        fence_service = ExternalToolFenceService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
            usage_ledger_repository=UsageLedgerRepository(session),
            audit_repository=AuditRepository(session),
        )
        await fence_service.resolve(
            ExternalToolFenceResolveInput(
                gateway_key_id=authenticated_key.gateway_key_id,
                request_id=request_id,
            )
        )
        if hasattr(session, "commit"):
            await session.commit()
        return final
    finally:
        await session_iterator.aclose()


def _external_tool_max_fee_eur(admission, cost_estimate: ChatCostEstimate) -> Decimal:
    pricing = getattr(admission, "pricing", None)
    if pricing is None:
        return Decimal("0")
    if pricing.currency == "EUR":
        fx_rate = Decimal("1")
    elif pricing.currency == cost_estimate.native_currency:
        fx_rate = cost_estimate.fx_rate
    else:
        fx_rate = None
    if fx_rate is None and cost_estimate.native_currency == "EUR":
        fx_rate = Decimal("1")
    if fx_rate is None:
        raise AccountingError("The reservation did not retain exact external-tool FX facts.")
    return admission.maximum_fee_native * fx_rate


async def _place_external_web_search_hold(
    *,
    reservation: QuotaReservationResult,
    authenticated_key: AuthenticatedGatewayKey,
    request_id: str,
    request: Request | None,
    reason_code: ExternalToolHoldReasonCode,
    evidence_quality: ExternalToolHoldEvidenceQuality,
    partial_total_tokens: int | None = None,
    estimated_cost_eur: Decimal | None = None,
    streaming: bool = False,
) -> None:
    """Keep the full fenced reservation when terminal evidence is uncertain."""
    session_iterator = _db_session_iterator(request)
    try:
        session = await anext(session_iterator)
    except StopAsyncIteration as exc:
        raise _database_session_unavailable_error() from exc
    try:
        hold_service = ExternalToolAccountingHoldService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
            usage_ledger_repository=UsageLedgerRepository(session),
            audit_repository=AuditRepository(session),
        )
        await hold_service.place(
            ExternalToolAccountingHoldInput(
                gateway_key_id=authenticated_key.gateway_key_id,
                reservation_id=reservation.reservation_id,
                request_id=request_id,
                reason_code=reason_code,
                evidence_quality=evidence_quality,
                streaming=streaming,
                now=datetime.now(UTC),
                partial_total_tokens=partial_total_tokens,
                estimated_cost_eur=estimated_cost_eur,
            )
        )
        if hasattr(session, "commit"):
            await session.commit()
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


def _build_responses_streaming_live_burn_budget(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    gateway_key: object | None,
    reservation: QuotaReservationResult,
    cost_estimate: ChatCostEstimate,
    settings: Settings,
) -> ResponsesStreamingLiveBurnBudget | None:
    policy = _responses_streaming_live_burn_policy_from_key(
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
    return build_responses_streaming_live_burn_budget(
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
        estimate_multiplier=settings.RESPONSES_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER,
    )


def _responses_streaming_live_burn_policy_from_key(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    gateway_key: object | None,
    settings: Settings,
) -> ResponsesStreamingLiveBurnPolicy:
    metadata = getattr(gateway_key, "metadata_json", None)
    if isinstance(metadata, dict):
        try:
            return responses_streaming_live_burn_policy_from_metadata(
                metadata,
                max_abs_cost_margin_eur=(
                    settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                ),
                max_abs_token_margin=settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ResponsesStreamingLiveBurnPolicyError:
            return default_responses_streaming_live_burn_policy()
    policy = authenticated_key.responses_streaming_live_burn_policy
    if isinstance(policy, dict):
        try:
            return responses_streaming_live_burn_policy_from_metadata(
                {"responses_streaming_live_burn": dict(policy)},
                max_abs_cost_margin_eur=(
                    settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                ),
                max_abs_token_margin=settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ResponsesStreamingLiveBurnPolicyError:
            return default_responses_streaming_live_burn_policy()
    return default_responses_streaming_live_burn_policy()


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
            model_route = await ModelRoutesRepository(session).get_model_route_by_id(
                reference.route_id
            )
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
        allowed = [
            provider
            for provider in authenticated_key.allowed_providers
            if provider in enabled_by_name
        ]
        if not allowed:
            return None
        if len(allowed) == 1:
            return enabled_by_name[allowed[0]]
        if "openai" in allowed:
            return enabled_by_name["openai"]
        return enabled_by_name[sorted(allowed)[0]]
    return enabled_by_name.get("openai") or next(
        iter(sorted(enabled_by_name.values(), key=lambda item: item.provider)), None
    )


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


def _validate_response_retrieve_query(request: Request | None) -> None:
    if request is None:
        return
    if request.query_params:
        raise OpenAICompatibleError(
            "Responses retrieve query parameters are not supported by this gateway.",
            status_code=400,
            error_type="invalid_request_error",
            code="invalid_response_retrieve_query",
            param="query",
        )


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
    if (
        not response_id
        or len(response_id.encode("utf-8")) > 512
        or any(ord(char) < 32 for char in response_id)
    ):
        raise OpenAICompatibleError(
            "Response not found.",
            status_code=404,
            error_type="invalid_request_error",
            code="response_not_found",
        )
    return response_id


def _validate_conversation_id(conversation_id: str) -> str:
    if (
        not conversation_id
        or len(conversation_id.encode("utf-8")) > 512
        or any(ord(char) < 32 for char in conversation_id)
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
