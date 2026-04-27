"""OpenAI-compatible /v1 API routes."""

import inspect

from fastapi import APIRouter, Depends, Request

from slaif_gateway.api import dependencies as dependencies_module
from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.api.endpoint_policy_errors import openai_error_from_endpoint_policy_error
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest, OpenAIModelList
from slaif_gateway.services.chat_completion_gateway import handle_chat_completion
from slaif_gateway.services.endpoint_policy import CHAT_COMPLETIONS, MODELS_LIST, EndpointPolicyService
from slaif_gateway.services.endpoint_policy_errors import EndpointPolicyError
from slaif_gateway.services.model_catalog import ModelCatalogService

router = APIRouter()
get_db_session_after_auth_header_check = dependencies_module.get_db_session_after_auth_header_check
_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check


@router.get("/v1/models", response_model=OpenAIModelList)
async def list_models(
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
) -> OpenAIModelList:
    _ensure_endpoint_allowed(authenticated_key, MODELS_LIST)
    async for session in _db_session_iterator(request):
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
    _ensure_endpoint_allowed(authenticated_key, CHAT_COMPLETIONS)
    kwargs = {
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_chat_completion).parameters:
        kwargs["request"] = request
    return await handle_chat_completion(
        **kwargs,
    )


def _ensure_endpoint_allowed(authenticated_key: AuthenticatedGatewayKey, endpoint: str) -> None:
    try:
        EndpointPolicyService().ensure_endpoint_allowed(authenticated_key, endpoint)
    except EndpointPolicyError as exc:
        raise openai_error_from_endpoint_policy_error(exc) from exc


def _db_session_iterator(request: Request):
    try:
        return _get_db_session_after_auth_header_check(request)
    except TypeError:
        return _get_db_session_after_auth_header_check()
