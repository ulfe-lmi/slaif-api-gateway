"""Service-layer model route resolution for /v1/chat/completions validation."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

from slaif_gateway.db.models import ModelRoute, ProviderConfig
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.routing_errors import (
    AmbiguousRouteError,
    ModelNotAllowedForKeyError,
    ModelNotFoundError,
    ModelRouteDisabledError,
    ProviderDisabledError,
    ProviderNotAllowedForKeyError,
    UnsupportedRouteMatchTypeError,
)


@dataclass(frozen=True, slots=True)
class _RankedMatch:
    route: ModelRoute
    provider_config: ProviderConfig

    def sort_key(self) -> tuple[int, int, int, str]:
        return (
            self.route.priority,
            _specificity_rank(self.route.match_type),
            -len(self.route.requested_model),
            str(self.route.id),
        )


def _specificity_rank(match_type: str) -> int:
    if match_type == "exact":
        return 0
    if match_type == "prefix":
        return 1
    if match_type == "glob":
        return 2
    return 99


def _matches_route(requested_model: str, route: ModelRoute) -> bool:
    if route.match_type == "exact":
        return requested_model == route.requested_model
    if route.match_type == "prefix":
        return requested_model.startswith(route.requested_model)
    if route.match_type == "glob":
        return fnmatchcase(requested_model, route.requested_model)
    raise UnsupportedRouteMatchTypeError(
        f"Unsupported route match_type '{route.match_type}' for route '{route.id}'"
    )


class RouteResolutionService:
    """Resolve client-facing model names to an enabled provider/upstream model."""

    CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"

    def __init__(
        self,
        *,
        model_routes_repository: ModelRoutesRepository,
        provider_configs_repository: ProviderConfigsRepository,
    ) -> None:
        self._model_routes_repository = model_routes_repository
        self._provider_configs_repository = provider_configs_repository

    async def resolve_model(
        self,
        requested_model: str,
        authenticated_key: AuthenticatedGatewayKey,
    ) -> RouteResolutionResult:
        if not requested_model:
            raise ModelNotFoundError("Model name is required")

        if not authenticated_key.allow_all_models and requested_model not in set(
            authenticated_key.allowed_models
        ):
            raise ModelNotAllowedForKeyError()

        provider_configs = await self._provider_configs_repository.list_provider_configs()
        provider_by_name = {config.provider: config for config in provider_configs}

        routes = await self._model_routes_repository.list_model_routes(
            endpoint=self.CHAT_COMPLETIONS_ENDPOINT,
            limit=1000,
        )

        matching_routes: list[ModelRoute] = []
        matched_disabled_routes = False
        matched_disabled_provider = False

        for route in routes:
            if not _matches_route(requested_model, route):
                continue
            if not route.enabled:
                matched_disabled_routes = True
                continue
            matching_routes.append(route)

        if not matching_routes:
            if matched_disabled_routes:
                raise ModelRouteDisabledError()
            raise ModelNotFoundError()

        ranked_matches: list[_RankedMatch] = []
        for route in matching_routes:
            provider_config = provider_by_name.get(route.provider)
            if provider_config is None or not provider_config.enabled:
                matched_disabled_provider = True
                continue
            ranked_matches.append(_RankedMatch(route=route, provider_config=provider_config))

        if authenticated_key.allowed_providers is not None:
            allowed_providers = set(authenticated_key.allowed_providers)
            ranked_matches = [
                match for match in ranked_matches if match.route.provider in allowed_providers
            ]
            if not ranked_matches:
                raise ProviderNotAllowedForKeyError()

        if not ranked_matches:
            if matched_disabled_provider:
                raise ProviderDisabledError()
            raise ModelNotFoundError()

        ranked_matches.sort(key=lambda match: match.sort_key())
        best = ranked_matches[0]

        if len(ranked_matches) > 1 and ranked_matches[0].sort_key() == ranked_matches[1].sort_key():
            raise AmbiguousRouteError()

        resolved_model = best.route.upstream_model or requested_model

        return RouteResolutionResult(
            requested_model=requested_model,
            resolved_model=resolved_model,
            provider=best.route.provider,
            route_id=best.route.id,
            route_match_type=best.route.match_type,
            route_pattern=best.route.requested_model,
            priority=best.route.priority,
            provider_base_url=best.provider_config.base_url,
            provider_api_key_env_var=best.provider_config.api_key_env_var,
            provider_timeout_seconds=getattr(best.provider_config, "timeout_seconds", None),
            provider_max_retries=getattr(best.provider_config, "max_retries", None),
            visible_model_id=best.route.requested_model,
        )
