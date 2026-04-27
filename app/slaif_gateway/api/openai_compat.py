"""OpenAI-compatible /v1 API routes."""

from fastapi import APIRouter, Depends, Request

from slaif_gateway.api import dependencies as dependencies_module
from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest, OpenAIModelList
from slaif_gateway.services.chat_completion_gateway import handle_chat_completion
from slaif_gateway.services.model_catalog import ModelCatalogService

router = APIRouter()
_get_db_session_after_auth_header_check = dependencies_module._get_db_session_after_auth_header_check


@router.get("/v1/models", response_model=OpenAIModelList)
async def list_models(
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
) -> OpenAIModelList:
    async for session in _get_db_session_after_auth_header_check():
        service = ModelCatalogService(
            model_routes_repository=ModelRoutesRepository(session),
            provider_configs_repository=ProviderConfigsRepository(session),
        )
        models = await service.list_visible_models(authenticated_key)
        return OpenAIModelList(data=models)

    return OpenAIModelList(data=[])


@router.post("/v1/chat/completions")
async def validate_chat_completions(
    request: Request,
    payload: ChatCompletionRequest,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    return await handle_chat_completion(
        payload=payload,
        authenticated_key=authenticated_key,
        settings=request.app.state.settings,
    )
