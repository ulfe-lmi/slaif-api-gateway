"""OpenAI-compatible /v1 API routes."""

import inspect

from fastapi import APIRouter, Body, Depends, Request

from slaif_gateway.api import dependencies as dependencies_module
from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.api.endpoint_policy_errors import openai_error_from_endpoint_policy_error
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest, OpenAIModelList, ResponsesCreateRequest
from slaif_gateway.services.audio_gateway import (
    handle_audio_speech,
    handle_audio_transcription,
    handle_audio_translation,
)
from slaif_gateway.services.chat_completion_gateway import handle_chat_completion
from slaif_gateway.services.embeddings_gateway import handle_embeddings_create
from slaif_gateway.services.endpoint_policy import (
    AUDIO_SPEECH,
    AUDIO_TRANSCRIPTIONS,
    AUDIO_TRANSLATIONS,
    CHAT_COMPLETIONS,
    EMBEDDINGS,
    CONVERSATION_ITEMS_CREATE,
    CONVERSATION_ITEMS_DELETE,
    CONVERSATION_ITEMS_LIST,
    CONVERSATION_ITEMS_RETRIEVE,
    CONVERSATIONS_CREATE,
    CONVERSATIONS_UPDATE,
    CONVERSATIONS_DELETE,
    CONVERSATIONS_RETRIEVE,
    MODELS_LIST,
    REALTIME_CLIENT_SECRETS,
    RESPONSES,
    RESPONSES_COMPACT,
    RESPONSES_DELETE,
    RESPONSES_INPUT_ITEMS,
    RESPONSES_INPUT_TOKENS,
    RESPONSES_RETRIEVE,
    EndpointPolicyService,
)
from slaif_gateway.services.endpoint_policy_errors import EndpointPolicyError
from slaif_gateway.services.model_catalog import ModelCatalogService
from slaif_gateway.services.realtime_gateway import handle_realtime_client_secret_create
from slaif_gateway.services.responses_gateway import (
    handle_conversation_item_create,
    handle_conversation_item_delete,
    handle_conversation_item_retrieve,
    handle_conversation_items_list,
    handle_conversation_create,
    handle_conversation_update,
    handle_conversation_delete,
    handle_conversation_retrieve,
    handle_response_compact,
    handle_response_create,
    handle_response_delete,
    handle_response_input_tokens_count,
    handle_response_input_items_list,
    handle_response_retrieve,
)

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


@router.post("/v1/audio/speech")
async def create_audio_speech(
    request: Request,
    payload: dict[str, object],
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, AUDIO_SPEECH)
    return await handle_audio_speech(
        payload=payload,
        authenticated_key=authenticated_key,
        settings=request.app.state.settings,
        request=request,
    )


@router.post("/v1/audio/transcriptions")
async def create_audio_transcription(
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, AUDIO_TRANSCRIPTIONS)
    return await handle_audio_transcription(
        authenticated_key=authenticated_key,
        settings=request.app.state.settings,
        request=request,
    )


@router.post("/v1/audio/translations")
async def create_audio_translation(
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, AUDIO_TRANSLATIONS)
    return await handle_audio_translation(
        authenticated_key=authenticated_key,
        settings=request.app.state.settings,
        request=request,
    )


@router.post("/v1/embeddings")
async def create_embeddings(
    request: Request,
    payload: dict[str, object],
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, EMBEDDINGS)
    return await handle_embeddings_create(
        payload=payload,
        authenticated_key=authenticated_key,
        settings=request.app.state.settings,
        request=request,
    )


@router.post("/v1/realtime/client_secrets")
async def create_realtime_client_secret(
    request: Request,
    payload: dict[str, object],
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, REALTIME_CLIENT_SECRETS)
    return await handle_realtime_client_secret_create(
        payload=payload,
        authenticated_key=authenticated_key,
        settings=request.app.state.settings,
        request=request,
    )


@router.post("/v1/responses")
async def create_response(
    request: Request,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, RESPONSES)
    kwargs = {
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_response_create).parameters:
        kwargs["request"] = request
    return await handle_response_create(**kwargs)


@router.post("/v1/responses/input_tokens")
async def count_response_input_tokens(
    request: Request,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, RESPONSES_INPUT_TOKENS)
    kwargs = {
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_response_input_tokens_count).parameters:
        kwargs["request"] = request
    return await handle_response_input_tokens_count(**kwargs)


@router.post("/v1/responses/compact")
async def compact_response(
    request: Request,
    payload: ResponsesCreateRequest,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, RESPONSES_COMPACT)
    kwargs = {
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_response_compact).parameters:
        kwargs["request"] = request
    return await handle_response_compact(**kwargs)


@router.get("/v1/responses/{response_id}")
async def retrieve_response(
    response_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, RESPONSES_RETRIEVE)
    kwargs = {
        "response_id": response_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_response_retrieve).parameters:
        kwargs["request"] = request
    return await handle_response_retrieve(**kwargs)


@router.get("/v1/responses/{response_id}/input_items")
async def list_response_input_items(
    response_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, RESPONSES_INPUT_ITEMS)
    kwargs = {
        "response_id": response_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_response_input_items_list).parameters:
        kwargs["request"] = request
    return await handle_response_input_items_list(**kwargs)


@router.delete("/v1/responses/{response_id}")
async def delete_response(
    response_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, RESPONSES_DELETE)
    kwargs = {
        "response_id": response_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_response_delete).parameters:
        kwargs["request"] = request
    return await handle_response_delete(**kwargs)


@router.post("/v1/conversations")
async def create_conversation(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATIONS_CREATE)
    kwargs = {
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_create).parameters:
        kwargs["request"] = request
    return await handle_conversation_create(**kwargs)


@router.post("/v1/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATIONS_UPDATE)
    kwargs = {
        "conversation_id": conversation_id,
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_update).parameters:
        kwargs["request"] = request
    return await handle_conversation_update(**kwargs)


@router.post("/v1/conversations/{conversation_id}/items")
async def create_conversation_items(
    conversation_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATION_ITEMS_CREATE)
    kwargs = {
        "conversation_id": conversation_id,
        "payload": payload,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_item_create).parameters:
        kwargs["request"] = request
    return await handle_conversation_item_create(**kwargs)


@router.get("/v1/conversations/{conversation_id}/items")
async def list_conversation_items(
    conversation_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATION_ITEMS_LIST)
    kwargs = {
        "conversation_id": conversation_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_items_list).parameters:
        kwargs["request"] = request
    return await handle_conversation_items_list(**kwargs)


@router.get("/v1/conversations/{conversation_id}/items/{item_id}")
async def retrieve_conversation_item(
    conversation_id: str,
    item_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATION_ITEMS_RETRIEVE)
    kwargs = {
        "conversation_id": conversation_id,
        "item_id": item_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_item_retrieve).parameters:
        kwargs["request"] = request
    return await handle_conversation_item_retrieve(**kwargs)


@router.delete("/v1/conversations/{conversation_id}/items/{item_id}")
async def delete_conversation_item(
    conversation_id: str,
    item_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATION_ITEMS_DELETE)
    kwargs = {
        "conversation_id": conversation_id,
        "item_id": item_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_item_delete).parameters:
        kwargs["request"] = request
    return await handle_conversation_item_delete(**kwargs)


@router.get("/v1/conversations/{conversation_id}")
async def retrieve_conversation(
    conversation_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATIONS_RETRIEVE)
    kwargs = {
        "conversation_id": conversation_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_retrieve).parameters:
        kwargs["request"] = request
    return await handle_conversation_retrieve(**kwargs)


@router.delete("/v1/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    authenticated_key: AuthenticatedGatewayKey = Depends(get_authenticated_gateway_key),
):
    _ensure_endpoint_allowed(authenticated_key, CONVERSATIONS_DELETE)
    kwargs = {
        "conversation_id": conversation_id,
        "authenticated_key": authenticated_key,
        "settings": request.app.state.settings,
    }
    if "request" in inspect.signature(handle_conversation_delete).parameters:
        kwargs["request"] = request
    return await handle_conversation_delete(**kwargs)


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
