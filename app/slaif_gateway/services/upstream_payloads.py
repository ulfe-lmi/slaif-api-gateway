"""Canonical provider-bound payload builders for OpenAI-compatible endpoints."""

from __future__ import annotations

from typing import Any

import copy

from slaif_gateway.services.upstream_request_contracts import (
    NormalizedAudioSpeechUpstreamRequest,
    NormalizedAudioTranscriptionUpstreamRequest,
    NormalizedAudioTranslationUpstreamRequest,
    NormalizedEmbeddingsUpstreamRequest,
    NormalizedConversationItemsCreateUpstreamRequest,
    NormalizedConversationItemsQueryRequest,
    NormalizedConversationUpdateUpstreamRequest,
    NormalizedChatCompletionUpstreamRequest,
    NormalizedResponsesCompactUpstreamRequest,
    NormalizedResponsesInputTokensUpstreamRequest,
    NormalizedResponsesUpstreamRequest,
)


CHAT_COMPLETION_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "messages",
    "temperature",
    "top_p",
    "stop",
    "seed",
    "user",
    "logit_bias",
    "logprobs",
    "top_logprobs",
    "presence_penalty",
    "frequency_penalty",
    "stream",
    "stream_options",
    "max_tokens",
    "max_completion_tokens",
    "n",
    "tools",
    "tool_choice",
    "functions",
    "function_call",
    "response_format",
    "metadata",
    "reasoning_effort",
    "parallel_tool_calls",
    "modalities",
    "audio",
    "prediction",
    "service_tier",
    "web_search_options",
    "store",
)

RESPONSES_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "input",
    "instructions",
    "max_output_tokens",
    "temperature",
    "top_p",
    "metadata",
    "stream",
    "store",
    "text",
    "service_tier",
    "tools",
    "tool_choice",
    "previous_response_id",
    "conversation",
)

RESPONSES_INPUT_TOKENS_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "input",
    "instructions",
    "text",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "truncation",
)

RESPONSES_INPUT_ITEMS_QUERY_FIELDS: tuple[str, ...] = (
    "after",
    "include",
    "limit",
    "order",
)

RESPONSES_COMPACT_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "input",
    "instructions",
)
SPEECH_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "input",
    "voice",
    "response_format",
    "speed",
    "instructions",
)
TRANSCRIPTION_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "language",
    "prompt",
    "response_format",
    "temperature",
    "timestamp_granularities",
    "include",
)
TRANSLATION_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "prompt",
    "response_format",
    "temperature",
)
EMBEDDINGS_UPSTREAM_FIELDS: tuple[str, ...] = (
    "model",
    "input",
    "encoding_format",
    "dimensions",
    "user",
)
CONVERSATION_ITEMS_CREATE_UPSTREAM_FIELDS: tuple[str, ...] = ("items",)
CONVERSATION_UPDATE_UPSTREAM_FIELDS: tuple[str, ...] = ("metadata",)
CONVERSATION_ITEMS_QUERY_FIELDS: tuple[str, ...] = (
    "after",
    "before",
    "include",
    "limit",
    "order",
)


def build_chat_completion_upstream_body(
    normalized_request: NormalizedChatCompletionUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Chat Completions provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(CHAT_COMPLETION_UPSTREAM_FIELDS),
        endpoint_label="Chat Completions",
    )


def build_responses_upstream_body(
    normalized_request: NormalizedResponsesUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Responses provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(RESPONSES_UPSTREAM_FIELDS),
        endpoint_label="Responses",
    )


def build_responses_input_tokens_upstream_body(
    normalized_request: NormalizedResponsesInputTokensUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Responses input-token count provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(RESPONSES_INPUT_TOKENS_UPSTREAM_FIELDS),
        endpoint_label="Responses input-token count",
    )


def build_responses_compact_upstream_body(
    normalized_request: NormalizedResponsesCompactUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Responses compact provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(RESPONSES_COMPACT_UPSTREAM_FIELDS),
        endpoint_label="Responses compact",
    )


def build_audio_speech_upstream_body(
    normalized_request: NormalizedAudioSpeechUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Audio speech provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(SPEECH_UPSTREAM_FIELDS),
        endpoint_label="Audio speech",
    )


def build_audio_transcription_upstream_body(
    normalized_request: NormalizedAudioTranscriptionUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Audio transcription provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(TRANSCRIPTION_UPSTREAM_FIELDS),
        endpoint_label="Audio transcription",
    )


def build_audio_translation_upstream_body(
    normalized_request: NormalizedAudioTranslationUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Audio translation provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(TRANSLATION_UPSTREAM_FIELDS),
        endpoint_label="Audio translation",
    )


def build_embeddings_upstream_body(
    normalized_request: NormalizedEmbeddingsUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Embeddings provider payload from approved fields only."""

    return _build_upstream_body(
        normalized_request,
        allowed_fields=frozenset(EMBEDDINGS_UPSTREAM_FIELDS),
        endpoint_label="Embeddings",
    )


def build_responses_input_items_query_params(
    query_params: dict[str, object],
) -> dict[str, object]:
    """Build fresh Responses input-items provider query params from approved fields only."""

    approved = frozenset(RESPONSES_INPUT_ITEMS_QUERY_FIELDS)
    unknown_fields = set(query_params) - approved
    if unknown_fields:
        raise ValueError("Responses input-items query contains unsupported fields.")
    return {field: copy.deepcopy(query_params[field]) for field in RESPONSES_INPUT_ITEMS_QUERY_FIELDS if field in query_params}


def build_conversation_items_create_upstream_body(
    normalized_request: NormalizedConversationItemsCreateUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Conversation items provider payload from approved fields only."""

    if not isinstance(normalized_request, NormalizedConversationItemsCreateUpstreamRequest):
        raise TypeError(
            "Conversation items create upstream payload must be built from a normalized request contract."
        )
    fields = normalized_request.as_upstream_fields()
    unknown_fields = set(fields) - set(CONVERSATION_ITEMS_CREATE_UPSTREAM_FIELDS)
    if unknown_fields:
        raise ValueError("Conversation items create payload contains unsupported fields.")
    return {
        field: copy.deepcopy(fields[field])
        for field in CONVERSATION_ITEMS_CREATE_UPSTREAM_FIELDS
        if field in fields
    }


def build_conversation_items_query_params(
    normalized_request: NormalizedConversationItemsQueryRequest,
) -> dict[str, object]:
    """Build fresh Conversation items provider query params from approved fields only."""

    if not isinstance(normalized_request, NormalizedConversationItemsQueryRequest):
        raise TypeError(
            "Conversation items query params must be built from a normalized request contract."
        )
    fields = normalized_request.as_upstream_fields()
    unknown_fields = set(fields) - set(CONVERSATION_ITEMS_QUERY_FIELDS)
    if unknown_fields:
        raise ValueError("Conversation items query contains unsupported fields.")
    return {
        field: copy.deepcopy(fields[field])
        for field in CONVERSATION_ITEMS_QUERY_FIELDS
        if field in fields
    }


def build_conversation_update_upstream_body(
    normalized_request: NormalizedConversationUpdateUpstreamRequest,
) -> dict[str, Any]:
    """Build a fresh Conversation update payload from approved fields only."""

    if not isinstance(normalized_request, NormalizedConversationUpdateUpstreamRequest):
        raise TypeError(
            "Conversation update upstream payload must be built from a normalized request contract."
        )
    fields = normalized_request.as_upstream_fields()
    unknown_fields = set(fields) - set(CONVERSATION_UPDATE_UPSTREAM_FIELDS)
    if unknown_fields:
        raise ValueError("Conversation update payload contains unsupported fields.")
    return {
        field: copy.deepcopy(fields[field])
        for field in CONVERSATION_UPDATE_UPSTREAM_FIELDS
        if field in fields
    }


def _build_upstream_body(
    normalized_request: NormalizedChatCompletionUpstreamRequest
    | NormalizedResponsesUpstreamRequest
    | NormalizedResponsesInputTokensUpstreamRequest
    | NormalizedResponsesCompactUpstreamRequest
    | NormalizedAudioSpeechUpstreamRequest
    | NormalizedAudioTranscriptionUpstreamRequest
    | NormalizedAudioTranslationUpstreamRequest
    | NormalizedEmbeddingsUpstreamRequest,
    *,
    allowed_fields: frozenset[str],
    endpoint_label: str,
) -> dict[str, Any]:
    if not isinstance(
        normalized_request,
        (
            NormalizedChatCompletionUpstreamRequest,
            NormalizedResponsesUpstreamRequest,
            NormalizedResponsesInputTokensUpstreamRequest,
                NormalizedResponsesCompactUpstreamRequest,
                NormalizedAudioSpeechUpstreamRequest,
                NormalizedAudioTranscriptionUpstreamRequest,
                NormalizedAudioTranslationUpstreamRequest,
                NormalizedEmbeddingsUpstreamRequest,
            ),
        ):
        raise TypeError(
            f"{endpoint_label} upstream payload must be built from a normalized request contract."
        )

    outbound: dict[str, Any] = {"model": normalized_request.upstream_model}
    fields = normalized_request.as_upstream_fields()
    unknown_fields = sorted(set(fields) - (set(allowed_fields) - {"model"}))
    if unknown_fields:
        joined = ", ".join(str(field) for field in unknown_fields)
        raise ValueError(f"{endpoint_label} upstream payload contains unapproved fields: {joined}")

    for field in allowed_fields:
        if field == "model":
            continue
        if field in fields:
            outbound[field] = copy.deepcopy(fields[field])
    return outbound
