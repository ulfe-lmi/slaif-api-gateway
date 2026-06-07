"""Normalized upstream request contracts for provider payload reconstruction."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from collections.abc import Mapping


_UNSET = object()

CHAT_UPSTREAM_ALLOWED_FIELDS = frozenset(
    {
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
    }
)

RESPONSES_UPSTREAM_ALLOWED_FIELDS = frozenset(
    {
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
    }
)

RESPONSES_INPUT_TOKENS_UPSTREAM_ALLOWED_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "text",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "truncation",
    }
)

RESPONSES_COMPACT_UPSTREAM_ALLOWED_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
    }
)


def _is_set(value: object) -> bool:
    """Return true when a contract field carries a real value."""

    return value is not _UNSET


def _deepcopy_or_unset(value: object) -> object:
    """Deep-copy policy-approved values so upstream bodies do not alias inputs."""

    if value is _UNSET:
        return value
    return copy.deepcopy(value)


def _ensure_required_text_model(requested_model: str, upstream_model: str, *, endpoint: str) -> None:
    if not requested_model.strip():
        raise ValueError(f"{endpoint} request is missing a requested model.")
    if not upstream_model.strip():
        raise ValueError(f"{endpoint} request is missing an upstream model.")


def _ensure_no_unknown_fields(body: Mapping[str, Any], *, allowed_fields: frozenset[str]) -> None:
    unknown_fields = sorted(set(body) - set(allowed_fields))
    if unknown_fields:
        joined = ", ".join(str(field) for field in unknown_fields)
        raise ValueError(f"Request contains unapproved top-level fields: {joined}")


def _as_messages(messages: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(copy.deepcopy(message) for message in messages)


def _select_field(value: object) -> object:
    if value is _UNSET:
        return _UNSET
    return copy.deepcopy(value)


@dataclass(frozen=True, slots=True)
class NormalizedChatCompletionUpstreamRequest:
    requested_model: str
    upstream_model: str
    messages: tuple[Mapping[str, Any], ...]

    temperature: object = _UNSET
    top_p: object = _UNSET
    stop: object = _UNSET
    seed: object = _UNSET
    user: object = _UNSET
    logit_bias: object = _UNSET
    logprobs: object = _UNSET
    top_logprobs: object = _UNSET
    presence_penalty: object = _UNSET
    frequency_penalty: object = _UNSET
    stream: object = _UNSET
    stream_options: object = _UNSET
    max_tokens: object = _UNSET
    max_completion_tokens: object = _UNSET
    n: object = _UNSET
    tools: object = _UNSET
    tool_choice: object = _UNSET
    functions: object = _UNSET
    function_call: object = _UNSET
    response_format: object = _UNSET
    metadata: object = _UNSET
    reasoning_effort: object = _UNSET
    parallel_tool_calls: object = _UNSET
    modalities: object = _UNSET
    audio: object = _UNSET
    prediction: object = _UNSET
    service_tier: object = _UNSET
    web_search_options: object = _UNSET
    store: object = _UNSET

    def as_upstream_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            if name in {"requested_model", "upstream_model"}:
                continue
            value = getattr(self, name)
            if not _is_set(value):
                continue
            if name == "messages":
                fields[name] = [copy.deepcopy(message) for message in self.messages]
                continue
            fields[name] = _select_field(value)
        return fields


@dataclass(frozen=True, slots=True)
class NormalizedResponsesUpstreamRequest:
    requested_model: str
    upstream_model: str
    input: str | tuple[Mapping[str, Any], ...]

    instructions: object = _UNSET
    max_output_tokens: object = _UNSET
    temperature: object = _UNSET
    top_p: object = _UNSET
    metadata: object = _UNSET
    stream: object = _UNSET
    store: object = _UNSET
    text: object = _UNSET
    service_tier: object = _UNSET
    tools: object = _UNSET
    tool_choice: object = _UNSET
    previous_response_id: object = _UNSET

    def as_upstream_fields(self) -> dict[str, Any]:
        input_value: Any
        if isinstance(self.input, tuple):
            input_value = [copy.deepcopy(item) for item in self.input]
        else:
            input_value = self.input
        fields: dict[str, Any] = {"input": input_value}
        for name in self.__dataclass_fields__:
            if name in {"requested_model", "upstream_model", "input"}:
                continue
            value = getattr(self, name)
            if not _is_set(value):
                continue
            fields[name] = _select_field(value)
        return fields


@dataclass(frozen=True, slots=True)
class NormalizedResponsesInputTokensUpstreamRequest:
    requested_model: str
    upstream_model: str
    input: str | tuple[Mapping[str, Any], ...]

    instructions: object = _UNSET
    text: object = _UNSET
    tools: object = _UNSET
    tool_choice: object = _UNSET
    parallel_tool_calls: object = _UNSET
    truncation: object = _UNSET

    def as_upstream_fields(self) -> dict[str, Any]:
        input_value: Any
        if isinstance(self.input, tuple):
            input_value = [copy.deepcopy(item) for item in self.input]
        else:
            input_value = self.input
        fields: dict[str, Any] = {"input": input_value}
        for name in self.__dataclass_fields__:
            if name in {"requested_model", "upstream_model", "input"}:
                continue
            value = getattr(self, name)
            if not _is_set(value):
                continue
            fields[name] = _select_field(value)
        return fields


@dataclass(frozen=True, slots=True)
class NormalizedResponsesCompactUpstreamRequest:
    requested_model: str
    upstream_model: str
    input: str | tuple[Mapping[str, Any], ...]

    instructions: object = _UNSET

    def as_upstream_fields(self) -> dict[str, Any]:
        input_value: Any
        if isinstance(self.input, tuple):
            input_value = [copy.deepcopy(item) for item in self.input]
        else:
            input_value = self.input
        fields: dict[str, Any] = {"input": input_value}
        if _is_set(self.instructions):
            fields["instructions"] = _select_field(self.instructions)
        return fields


def normalize_chat_completion_upstream_request(
    effective_body: Mapping[str, Any],
    *,
    requested_model: str,
    upstream_model: str,
) -> NormalizedChatCompletionUpstreamRequest:
    """Build a normalized Chat Completions contract from a policy-approved body."""

    _ensure_required_text_model(
        requested_model=requested_model,
        upstream_model=upstream_model,
        endpoint="Chat Completions",
    )
    body = dict(effective_body)
    if body.get("model") != requested_model:
        raise ValueError("Requested model must match policy-effective model.")
    allowed_fields = CHAT_UPSTREAM_ALLOWED_FIELDS
    _ensure_no_unknown_fields(body, allowed_fields=allowed_fields)
    messages = _as_messages(body["messages"])
    return NormalizedChatCompletionUpstreamRequest(
        requested_model=requested_model,
        upstream_model=upstream_model,
        messages=messages,
        temperature=_select_field(body.get("temperature", _UNSET)),
        top_p=_select_field(body.get("top_p", _UNSET)),
        stop=_select_field(body.get("stop", _UNSET)),
        seed=_select_field(body.get("seed", _UNSET)),
        user=_select_field(body.get("user", _UNSET)),
        logit_bias=_select_field(body.get("logit_bias", _UNSET)),
        logprobs=_select_field(body.get("logprobs", _UNSET)),
        top_logprobs=_select_field(body.get("top_logprobs", _UNSET)),
        presence_penalty=_select_field(body.get("presence_penalty", _UNSET)),
        frequency_penalty=_select_field(body.get("frequency_penalty", _UNSET)),
        stream=_select_field(body.get("stream", _UNSET)),
        stream_options=_select_field(body.get("stream_options", _UNSET)),
        max_tokens=_select_field(body.get("max_tokens", _UNSET)),
        max_completion_tokens=_select_field(body.get("max_completion_tokens", _UNSET)),
        n=_select_field(body.get("n", _UNSET)),
        tools=_select_field(body.get("tools", _UNSET)),
        tool_choice=_select_field(body.get("tool_choice", _UNSET)),
        functions=_select_field(body.get("functions", _UNSET)),
        function_call=_select_field(body.get("function_call", _UNSET)),
        response_format=_select_field(body.get("response_format", _UNSET)),
        metadata=_select_field(body.get("metadata", _UNSET)),
        reasoning_effort=_select_field(body.get("reasoning_effort", _UNSET)),
        parallel_tool_calls=_select_field(body.get("parallel_tool_calls", _UNSET)),
        modalities=_select_field(body.get("modalities", _UNSET)),
        audio=_select_field(body.get("audio", _UNSET)),
        prediction=_select_field(body.get("prediction", _UNSET)),
        service_tier=_select_field(body.get("service_tier", _UNSET)),
        web_search_options=_select_field(body.get("web_search_options", _UNSET)),
        store=_select_field(body.get("store", _UNSET)),
    )


def normalize_responses_upstream_request(
    effective_body: Mapping[str, Any],
    *,
    requested_model: str,
    upstream_model: str,
) -> NormalizedResponsesUpstreamRequest:
    """Build a normalized Responses contract from a policy-approved body."""

    _ensure_required_text_model(
        requested_model=requested_model,
        upstream_model=upstream_model,
        endpoint="Responses",
    )
    body = dict(effective_body)
    if body.get("model") != requested_model:
        raise ValueError("Requested model must match policy-effective model.")
    allowed_fields = RESPONSES_UPSTREAM_ALLOWED_FIELDS
    _ensure_no_unknown_fields(body, allowed_fields=allowed_fields)

    return NormalizedResponsesUpstreamRequest(
        requested_model=requested_model,
        upstream_model=upstream_model,
        input=(
            tuple(copy.deepcopy(item) for item in body["input"])
            if isinstance(body["input"], list)
            else copy.deepcopy(body["input"])
        ),
        instructions=_select_field(body.get("instructions", _UNSET)),
        max_output_tokens=_select_field(body.get("max_output_tokens", _UNSET)),
        temperature=_select_field(body.get("temperature", _UNSET)),
        top_p=_select_field(body.get("top_p", _UNSET)),
        metadata=_select_field(body.get("metadata", _UNSET)),
        stream=_select_field(body.get("stream", _UNSET)),
        store=_select_field(body.get("store", _UNSET)),
        text=_select_field(body.get("text", _UNSET)),
        service_tier=_select_field(body.get("service_tier", _UNSET)),
        tools=_select_field(body.get("tools", _UNSET)),
        tool_choice=_select_field(body.get("tool_choice", _UNSET)),
        previous_response_id=_select_field(body.get("previous_response_id", _UNSET)),
    )


def normalize_responses_input_tokens_upstream_request(
    effective_body: Mapping[str, Any],
    *,
    requested_model: str,
    upstream_model: str,
) -> NormalizedResponsesInputTokensUpstreamRequest:
    """Build a normalized Responses input-token count contract from a policy-approved body."""

    _ensure_required_text_model(
        requested_model=requested_model,
        upstream_model=upstream_model,
        endpoint="Responses input-token count",
    )
    body = dict(effective_body)
    if body.get("model") != requested_model:
        raise ValueError("Requested model must match policy-effective model.")
    _ensure_no_unknown_fields(
        body,
        allowed_fields=RESPONSES_INPUT_TOKENS_UPSTREAM_ALLOWED_FIELDS,
    )

    return NormalizedResponsesInputTokensUpstreamRequest(
        requested_model=requested_model,
        upstream_model=upstream_model,
        input=(
            tuple(copy.deepcopy(item) for item in body["input"])
            if isinstance(body["input"], list)
            else copy.deepcopy(body["input"])
        ),
        instructions=_select_field(body.get("instructions", _UNSET)),
        text=_select_field(body.get("text", _UNSET)),
        tools=_select_field(body.get("tools", _UNSET)),
        tool_choice=_select_field(body.get("tool_choice", _UNSET)),
        parallel_tool_calls=_select_field(body.get("parallel_tool_calls", _UNSET)),
        truncation=_select_field(body.get("truncation", _UNSET)),
    )


def normalize_responses_compact_upstream_request(
    effective_body: Mapping[str, Any],
    *,
    requested_model: str,
    upstream_model: str,
) -> NormalizedResponsesCompactUpstreamRequest:
    """Build a normalized Responses compact contract from a policy-approved body."""

    _ensure_required_text_model(
        requested_model=requested_model,
        upstream_model=upstream_model,
        endpoint="Responses compact",
    )
    body = dict(effective_body)
    if body.get("model") != requested_model:
        raise ValueError("Requested model must match policy-effective model.")
    _ensure_no_unknown_fields(
        body,
        allowed_fields=RESPONSES_COMPACT_UPSTREAM_ALLOWED_FIELDS,
    )

    return NormalizedResponsesCompactUpstreamRequest(
        requested_model=requested_model,
        upstream_model=upstream_model,
        input=(
            tuple(copy.deepcopy(item) for item in body["input"])
            if isinstance(body["input"], list)
            else copy.deepcopy(body["input"])
        ),
        instructions=_select_field(body.get("instructions", _UNSET)),
    )
