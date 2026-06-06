"""Canonical provider-bound payload builders for OpenAI-compatible endpoints."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


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
)


def build_chat_completion_upstream_body(
    effective_body: Mapping[str, Any],
    *,
    upstream_model: str,
) -> dict[str, Any]:
    """Build a fresh Chat Completions provider payload from approved fields only."""

    return _build_upstream_body(
        effective_body,
        upstream_model=upstream_model,
        allowed_fields=CHAT_COMPLETION_UPSTREAM_FIELDS,
        endpoint_label="Chat Completions",
    )


def build_responses_upstream_body(
    effective_body: Mapping[str, Any],
    *,
    upstream_model: str,
) -> dict[str, Any]:
    """Build a fresh Responses provider payload from approved fields only."""

    return _build_upstream_body(
        effective_body,
        upstream_model=upstream_model,
        allowed_fields=RESPONSES_UPSTREAM_FIELDS,
        endpoint_label="Responses",
    )


def _build_upstream_body(
    effective_body: Mapping[str, Any],
    *,
    upstream_model: str,
    allowed_fields: tuple[str, ...],
    endpoint_label: str,
) -> dict[str, Any]:
    unknown_fields = sorted(set(effective_body) - set(allowed_fields))
    if unknown_fields:
        joined = ", ".join(str(field) for field in unknown_fields)
        raise ValueError(f"{endpoint_label} upstream payload contains unapproved fields: {joined}")

    outbound: dict[str, Any] = {}
    for field in allowed_fields:
        if field == "model":
            outbound["model"] = upstream_model
            continue
        if field in effective_body:
            outbound[field] = copy.deepcopy(effective_body[field])
    if "model" not in outbound:
        outbound["model"] = upstream_model
    return outbound
