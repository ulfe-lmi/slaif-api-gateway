"""Shared request-policy validation for gateway keys."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from slaif_gateway.db.models import ModelRoute
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.model_route_service import CHAT_COMPLETIONS_ENDPOINT
from slaif_gateway.services.route_resolution import matches_model_route

MODELS_ENDPOINT = "/v1/models"
SPEECH_ENDPOINT = "/v1/audio/speech"
TRANSCRIPTIONS_ENDPOINT = "/v1/audio/transcriptions"
TRANSLATIONS_ENDPOINT = "/v1/audio/translations"
EMBEDDINGS_ENDPOINT = "/v1/embeddings"
RESPONSES_ENDPOINT = "/v1/responses"
RESPONSES_INPUT_TOKENS_ENDPOINT = "/v1/responses/input_tokens"
RESPONSES_RETRIEVE_ENDPOINT = "GET /v1/responses/{response_id}"
RESPONSES_DELETE_ENDPOINT = "DELETE /v1/responses/{response_id}"
RESPONSES_INPUT_ITEMS_ENDPOINT = "GET /v1/responses/{response_id}/input_items"
RESPONSES_COMPACT_ENDPOINT = "/v1/responses/compact"
CONVERSATIONS_CREATE_ENDPOINT = "/v1/conversations"
CONVERSATIONS_CREATE_METHOD_ENDPOINT = "POST /v1/conversations"
CONVERSATIONS_UPDATE_ENDPOINT = "POST /v1/conversations/{conversation_id}"
CONVERSATIONS_RETRIEVE_ENDPOINT = "GET /v1/conversations/{conversation_id}"
CONVERSATIONS_DELETE_ENDPOINT = "DELETE /v1/conversations/{conversation_id}"
CONVERSATION_ITEMS_CREATE_ENDPOINT = "POST /v1/conversations/{conversation_id}/items"
CONVERSATION_ITEMS_LIST_ENDPOINT = "GET /v1/conversations/{conversation_id}/items"
CONVERSATION_ITEMS_RETRIEVE_ENDPOINT = "GET /v1/conversations/{conversation_id}/items/{item_id}"
CONVERSATION_ITEMS_DELETE_ENDPOINT = "DELETE /v1/conversations/{conversation_id}/items/{item_id}"
IMPLEMENTED_CLIENT_ENDPOINTS = frozenset(
    {
        MODELS_ENDPOINT,
        CHAT_COMPLETIONS_ENDPOINT,
        SPEECH_ENDPOINT,
        TRANSCRIPTIONS_ENDPOINT,
        TRANSLATIONS_ENDPOINT,
        EMBEDDINGS_ENDPOINT,
        RESPONSES_ENDPOINT,
        RESPONSES_INPUT_TOKENS_ENDPOINT,
        RESPONSES_RETRIEVE_ENDPOINT,
        RESPONSES_DELETE_ENDPOINT,
        RESPONSES_INPUT_ITEMS_ENDPOINT,
        RESPONSES_COMPACT_ENDPOINT,
        CONVERSATIONS_CREATE_ENDPOINT,
        CONVERSATIONS_CREATE_METHOD_ENDPOINT,
        CONVERSATIONS_UPDATE_ENDPOINT,
        CONVERSATIONS_RETRIEVE_ENDPOINT,
        CONVERSATIONS_DELETE_ENDPOINT,
        CONVERSATION_ITEMS_CREATE_ENDPOINT,
        CONVERSATION_ITEMS_LIST_ENDPOINT,
        CONVERSATION_ITEMS_RETRIEVE_ENDPOINT,
        CONVERSATION_ITEMS_DELETE_ENDPOINT,
    }
)


class _ModelRoutesRepository(Protocol):
    async def list_enabled_model_routes(
        self, *, endpoint: str | None = None
    ) -> list[ModelRoute]:
        pass


@dataclass(frozen=True, slots=True)
class GatewayKeyPolicy:
    """Normalized gateway-key request policy."""

    allowed_models: list[str] = field(default_factory=list)
    allowed_endpoints: list[str] = field(default_factory=list)
    allow_all_models: bool = False
    allow_all_endpoints: bool = False


async def validate_gateway_key_policy(
    policy: GatewayKeyPolicy,
    *,
    model_routes_repository: _ModelRoutesRepository | None,
) -> GatewayKeyPolicy:
    """Validate and normalize key endpoint/model allow-list policy.

    Route-aware model validation runs when a model-route repository is provided.
    Unit tests and narrow service fakes may omit the repository, but production
    admin and CLI paths provide it.
    """
    normalized = validate_gateway_key_policy_values(policy)

    effective_endpoints = (
        set(IMPLEMENTED_CLIENT_ENDPOINTS)
        if normalized.allow_all_endpoints
        else set(normalized.allowed_endpoints)
    )
    model_backed_endpoints = effective_endpoints & {
        CHAT_COMPLETIONS_ENDPOINT,
        SPEECH_ENDPOINT,
        TRANSCRIPTIONS_ENDPOINT,
        TRANSLATIONS_ENDPOINT,
        EMBEDDINGS_ENDPOINT,
        RESPONSES_ENDPOINT,
        RESPONSES_INPUT_TOKENS_ENDPOINT,
        RESPONSES_COMPACT_ENDPOINT,
    }
    if not normalized.allow_all_models and model_backed_endpoints:
        if not normalized.allowed_models:
            raise InvalidGatewayKeyPolicyError(
                "Select at least one allowed model or allow all models for model-backed endpoints.",
                param="allowed_models",
            )

    if model_routes_repository is not None and normalized.allowed_models:
        await _validate_models_have_routes(
            normalized.allowed_models,
            endpoints=effective_endpoints,
            model_routes_repository=model_routes_repository,
        )
    return normalized


def validate_gateway_key_policy_values(policy: GatewayKeyPolicy) -> GatewayKeyPolicy:
    """Validate policy fields that do not require database-backed route metadata."""
    normalized = GatewayKeyPolicy(
        allowed_models=_dedupe(policy.allowed_models),
        allowed_endpoints=_dedupe(policy.allowed_endpoints),
        allow_all_models=bool(policy.allow_all_models),
        allow_all_endpoints=bool(policy.allow_all_endpoints),
    )
    _validate_endpoints(normalized)
    _validate_model_value_shapes(normalized.allowed_models)
    return normalized


def _validate_endpoints(policy: GatewayKeyPolicy) -> None:
    if not policy.allow_all_endpoints and not policy.allowed_endpoints:
        raise InvalidGatewayKeyPolicyError(
            "Select at least one allowed endpoint or allow all endpoints.",
            param="allowed_endpoints",
        )

    for endpoint in policy.allowed_endpoints:
        normalized_endpoint = _normalize_endpoint_value(endpoint)
        if not normalized_endpoint.startswith("/v1/"):
            raise InvalidGatewayKeyPolicyError(
                "Allowed endpoints must be API paths such as /v1/models or method paths such as "
                "GET /v1/responses/{response_id}.",
                param="allowed_endpoints",
            )
        if endpoint not in IMPLEMENTED_CLIENT_ENDPOINTS:
            raise InvalidGatewayKeyPolicyError(
                f"Endpoint {endpoint} is not implemented for gateway keys.",
                param="allowed_endpoints",
            )


def _validate_model_value_shapes(allowed_models: list[str]) -> None:
    for model in allowed_models:
        if model.startswith("/v1/"):
            raise InvalidGatewayKeyPolicyError(
                "Allowed models must be model IDs such as gpt-5.2; endpoint paths belong in Allowed endpoints.",
                param="allowed_models",
            )


def _normalize_endpoint_value(endpoint: str) -> str:
    parts = endpoint.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0].isalpha():
        return parts[1]
    return endpoint.strip()


async def _validate_models_have_routes(
    allowed_models: list[str],
    *,
    endpoints: set[str],
    model_routes_repository: _ModelRoutesRepository,
) -> None:
    require_visible = endpoints == {MODELS_ENDPOINT}
    endpoints_to_check = (
        CHAT_COMPLETIONS_ENDPOINT,
        SPEECH_ENDPOINT,
        TRANSCRIPTIONS_ENDPOINT,
        TRANSLATIONS_ENDPOINT,
        RESPONSES_ENDPOINT,
        RESPONSES_INPUT_TOKENS_ENDPOINT,
        RESPONSES_COMPACT_ENDPOINT,
    )
    if endpoints and not require_visible:
        endpoints_to_check = tuple(endpoint for endpoint in endpoints_to_check if endpoint in endpoints)

    for model in allowed_models:
        candidates = []
        for endpoint in endpoints_to_check:
            routes = await model_routes_repository.list_enabled_model_routes(endpoint=endpoint)
            candidates.extend(route for route in routes if matches_model_route(model, route))
        if require_visible:
            candidates = [route for route in candidates if route.visible_in_models]
        if candidates:
            continue
        raise InvalidGatewayKeyPolicyError(
            f"No enabled route exists for model {model}. "
            "Run the OpenAI Completions catalog bootstrap or create a route first.",
            param="allowed_models",
        )


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized
