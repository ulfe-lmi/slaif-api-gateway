"""Service-layer model catalog visibility for authenticated /v1/models responses."""

from __future__ import annotations

from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import OpenAIModel


class ModelCatalogService:
    """Build OpenAI-compatible model visibility from configured routes/providers."""

    def __init__(
        self,
        *,
        model_routes_repository: ModelRoutesRepository,
        provider_configs_repository: ProviderConfigsRepository,
    ) -> None:
        self._model_routes_repository = model_routes_repository
        self._provider_configs_repository = provider_configs_repository

    async def list_visible_models(self, authenticated_key: AuthenticatedGatewayKey) -> list[OpenAIModel]:
        if not authenticated_key.allow_all_models and not authenticated_key.allowed_models:
            return []

        routes = await self._model_routes_repository.list_visible_model_routes()
        provider_configs = await self._provider_configs_repository.list_provider_configs()
        enabled_provider_names = {
            provider_config.provider for provider_config in provider_configs if provider_config.enabled
        }

        restrict_models = not authenticated_key.allow_all_models
        allowed_models = set(authenticated_key.allowed_models)

        restrict_providers = authenticated_key.allowed_providers is not None
        allowed_providers = set(authenticated_key.allowed_providers or ())

        models: list[OpenAIModel] = []
        seen_ids: set[str] = set()

        for route in routes:
            if route.provider not in enabled_provider_names:
                continue
            if restrict_providers and route.provider not in allowed_providers:
                continue
            if restrict_models and route.requested_model not in allowed_models:
                continue
            if route.requested_model in seen_ids:
                continue

            models.append(
                OpenAIModel(
                    id=route.requested_model,
                    object="model",
                    created=0,
                    owned_by=route.provider,
                )
            )
            seen_ids.add(route.requested_model)

        return models
