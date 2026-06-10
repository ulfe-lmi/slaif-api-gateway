"""Service-layer endpoint allow-list checks for authenticated gateway keys."""

from __future__ import annotations

from typing import Final

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.endpoint_policy_errors import EndpointNotAllowedError
from slaif_gateway.services.key_modes import is_trusted_calibration_key

MODELS_LIST: Final[str] = "models.list"
CHAT_COMPLETIONS: Final[str] = "chat.completions"
AUDIO_SPEECH: Final[str] = "audio.speech"
AUDIO_TRANSCRIPTIONS: Final[str] = "audio.transcriptions"
AUDIO_TRANSLATIONS: Final[str] = "audio.translations"
RESPONSES: Final[str] = "responses"
RESPONSES_INPUT_TOKENS: Final[str] = "responses.input_tokens"
RESPONSES_RETRIEVE: Final[str] = "responses.retrieve"
RESPONSES_DELETE: Final[str] = "responses.delete"
RESPONSES_INPUT_ITEMS: Final[str] = "responses.input_items"
RESPONSES_COMPACT: Final[str] = "responses.compact"
CONVERSATIONS_CREATE: Final[str] = "conversations.create"
CONVERSATIONS_UPDATE: Final[str] = "conversations.update"
CONVERSATIONS_RETRIEVE: Final[str] = "conversations.retrieve"
CONVERSATIONS_DELETE: Final[str] = "conversations.delete"
CONVERSATION_ITEMS_CREATE: Final[str] = "conversations.items.create"
CONVERSATION_ITEMS_LIST: Final[str] = "conversations.items.list"
CONVERSATION_ITEMS_RETRIEVE: Final[str] = "conversations.items.retrieve"
CONVERSATION_ITEMS_DELETE: Final[str] = "conversations.items.delete"

_ENDPOINT_ALIASES: Final[dict[str, frozenset[str]]] = {
    MODELS_LIST: frozenset(
        {
            "models.list",
            "get /v1/models",
            "/v1/models",
        }
    ),
    CHAT_COMPLETIONS: frozenset(
        {
            "chat.completions",
            "post /v1/chat/completions",
            "/v1/chat/completions",
        }
    ),
    AUDIO_SPEECH: frozenset(
        {
            "audio.speech",
            "post /v1/audio/speech",
            "/v1/audio/speech",
        }
    ),
    AUDIO_TRANSCRIPTIONS: frozenset(
        {
            "audio.transcriptions",
            "post /v1/audio/transcriptions",
            "/v1/audio/transcriptions",
        }
    ),
    AUDIO_TRANSLATIONS: frozenset(
        {
            "audio.translations",
            "post /v1/audio/translations",
            "/v1/audio/translations",
        }
    ),
    RESPONSES: frozenset(
        {
            "responses",
            "post /v1/responses",
            "/v1/responses",
        }
    ),
    RESPONSES_INPUT_TOKENS: frozenset(
        {
            "responses.input_tokens",
            "post /v1/responses/input_tokens",
            "/v1/responses/input_tokens",
        }
    ),
    RESPONSES_RETRIEVE: frozenset(
        {
            "responses.retrieve",
            "get /v1/responses/{response_id}",
        }
    ),
    RESPONSES_DELETE: frozenset(
        {
            "responses.delete",
            "delete /v1/responses/{response_id}",
        }
    ),
    RESPONSES_INPUT_ITEMS: frozenset(
        {
            "responses.input_items",
            "get /v1/responses/{response_id}/input_items",
        }
    ),
    RESPONSES_COMPACT: frozenset(
        {
            "responses.compact",
            "post /v1/responses/compact",
            "/v1/responses/compact",
        }
    ),
    CONVERSATIONS_CREATE: frozenset(
        {
            "conversations.create",
            "post /v1/conversations",
            "/v1/conversations",
        }
    ),
    CONVERSATIONS_UPDATE: frozenset(
        {
            "conversations.update",
            "post /v1/conversations/{conversation_id}",
        }
    ),
    CONVERSATIONS_RETRIEVE: frozenset(
        {
            "conversations.retrieve",
            "get /v1/conversations/{conversation_id}",
        }
    ),
    CONVERSATIONS_DELETE: frozenset(
        {
            "conversations.delete",
            "delete /v1/conversations/{conversation_id}",
        }
    ),
    CONVERSATION_ITEMS_CREATE: frozenset(
        {
            "conversations.items.create",
            "post /v1/conversations/{conversation_id}/items",
        }
    ),
    CONVERSATION_ITEMS_LIST: frozenset(
        {
            "conversations.items.list",
            "get /v1/conversations/{conversation_id}/items",
        }
    ),
    CONVERSATION_ITEMS_RETRIEVE: frozenset(
        {
            "conversations.items.retrieve",
            "get /v1/conversations/{conversation_id}/items/{item_id}",
        }
    ),
    CONVERSATION_ITEMS_DELETE: frozenset(
        {
            "conversations.items.delete",
            "delete /v1/conversations/{conversation_id}/items/{item_id}",
        }
    ),
}


class EndpointPolicyService:
    """Checks whether an authenticated key may call a stable endpoint identifier."""

    def ensure_endpoint_allowed(
        self,
        authenticated_key: AuthenticatedGatewayKey,
        endpoint: str,
    ) -> None:
        if authenticated_key.allow_all_endpoints or is_trusted_calibration_key(
            key_purpose=authenticated_key.key_purpose,
            capability_policy_mode=authenticated_key.capability_policy_mode,
        ):
            return

        allowed = {_normalize_endpoint_entry(item) for item in authenticated_key.allowed_endpoints}
        if not allowed:
            raise EndpointNotAllowedError()

        requested_aliases = _ENDPOINT_ALIASES.get(endpoint, frozenset({_normalize_endpoint_entry(endpoint)}))
        if allowed.isdisjoint(requested_aliases):
            raise EndpointNotAllowedError()


def _normalize_endpoint_entry(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    parts = normalized.split(maxsplit=1)
    if len(parts) == 2 and parts[0].isalpha() and parts[1].startswith("/"):
        return f"{parts[0].lower()} {parts[1].lower()}"
    if normalized.startswith("/"):
        return normalized.lower()
    return normalized.lower()
