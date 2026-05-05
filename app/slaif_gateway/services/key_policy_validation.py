"""Shared request-policy validation for gateway keys."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from slaif_gateway.db.models import ModelRoute
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.model_route_service import CHAT_COMPLETIONS_ENDPOINT
from slaif_gateway.services.route_resolution import matches_model_route

MODELS_ENDPOINT = "/v1/models"
IMPLEMENTED_CLIENT_ENDPOINTS = frozenset({MODELS_ENDPOINT, CHAT_COMPLETIONS_ENDPOINT})


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
    if not normalized.allow_all_models and CHAT_COMPLETIONS_ENDPOINT in effective_endpoints:
        if not normalized.allowed_models:
            raise InvalidGatewayKeyPolicyError(
                "Select at least one allowed model or allow all models for /v1/chat/completions.",
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
        if not endpoint.startswith("/v1/"):
            raise InvalidGatewayKeyPolicyError(
                "Allowed endpoints must be API paths such as /v1/models or /v1/chat/completions.",
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


async def _validate_models_have_routes(
    allowed_models: list[str],
    *,
    endpoints: set[str],
    model_routes_repository: _ModelRoutesRepository,
) -> None:
    chat_routes = await model_routes_repository.list_enabled_model_routes(
        endpoint=CHAT_COMPLETIONS_ENDPOINT
    )
    require_visible = endpoints == {MODELS_ENDPOINT}

    for model in allowed_models:
        candidates = [route for route in chat_routes if matches_model_route(model, route)]
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
