"""Canonical provider-bound payload builders for OpenAI-compatible endpoints."""

from __future__ import annotations

from typing import Any

import copy

from slaif_gateway.services.upstream_request_contracts import (
    NormalizedChatCompletionUpstreamRequest,
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


def _build_upstream_body(
    normalized_request: NormalizedChatCompletionUpstreamRequest
    | NormalizedResponsesUpstreamRequest
    | NormalizedResponsesInputTokensUpstreamRequest,
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
