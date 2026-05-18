"""Explicit caps and scalar validation for Chat Completions requests."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.services.input_token_estimation import canonical_json_bytes
from slaif_gateway.services.policy_errors import MULTI_CHOICE_UNSUPPORTED_MESSAGE, RequestPolicyError

_REASONING_EFFORT_VALUES = frozenset({"minimal", "low", "medium", "high"})
_RESPONSE_FORMAT_TYPES = frozenset({"text", "json_object", "json_schema"})


class ChatCompletionRequestCapsError(RequestPolicyError):
    """Request-policy error for bounded Chat Completions field validation."""

    def __init__(self, safe_message: str, *, param: str, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(safe_message, param=param)


def enforce_chat_completion_request_caps(
    payload: Mapping[str, Any],
    *,
    settings: Settings,
) -> None:
    """Validate currently supported Chat Completions fields before forwarding.

    Error messages intentionally name only fields and limits. They never include
    raw messages, schemas, metadata values, tool arguments, or request bodies.
    """

    _validate_model(payload.get("model"))
    _validate_messages(payload.get("messages"), settings=settings)
    _validate_scalar_controls(payload)
    _validate_stop(payload.get("stop"), settings=settings)
    _validate_user(payload.get("user"), settings=settings)
    _validate_logit_bias(payload.get("logit_bias"), settings=settings)
    _validate_tools(payload.get("tools"), settings=settings)
    _validate_legacy_functions(payload.get("functions"), settings=settings)
    _validate_function_choice(payload.get("tool_choice"), param="tool_choice", settings=settings)
    _validate_function_choice(
        payload.get("function_call"),
        param="function_call",
        settings=settings,
    )
    _validate_response_format(payload.get("response_format"), settings=settings)
    _validate_metadata(payload.get("metadata"), settings=settings)
    _validate_prediction(payload.get("prediction"), settings=settings)
    _validate_stream_options(payload.get("stream_options"), settings=settings)


def _validate_model(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        _raise(
            "model",
            "chat_field_invalid_type",
            "The 'model' field must be a non-empty string.",
        )


def _validate_messages(value: Any, *, settings: Settings) -> None:
    if not isinstance(value, list):
        _raise(
            "messages",
            "invalid_messages",
            "The 'messages' field must be a non-empty list.",
        )
    if not value:
        _raise(
            "messages",
            "invalid_messages",
            "The 'messages' field must be a non-empty list.",
        )
    if len(value) > settings.CHAT_MAX_MESSAGES_PER_REQUEST:
        _raise(
            "messages",
            "chat_message_limit_exceeded",
            "The request includes too many Chat Completions messages.",
        )

    for message_index, message in enumerate(value):
        if not isinstance(message, Mapping):
            _raise(
                "messages",
                "invalid_messages",
                "Each Chat Completions message must be an object.",
            )
        role = message.get("role")
        if not isinstance(role, str) or not role.strip():
            _raise(
                "messages",
                "invalid_messages",
                "Each Chat Completions message must include a non-empty string role.",
            )
        _validate_message_content(
            message.get("content"),
            message_index=message_index,
            settings=settings,
        )


def _validate_message_content(
    content: Any,
    *,
    message_index: int,
    settings: Settings,
) -> None:
    if content is None:
        return

    if isinstance(content, str):
        _validate_string_bytes(
            content,
            param=f"messages[{message_index}].content",
            max_bytes=settings.CHAT_MAX_MESSAGE_CONTENT_BYTES,
            error_code="chat_field_too_large",
            safe_message="A Chat Completions message content field exceeds the gateway size limit.",
        )
        return

    if not isinstance(content, list):
        _raise(
            f"messages[{message_index}].content",
            "chat_field_invalid_type",
            "Chat Completions message content must be a string, null, or a list of text parts.",
        )

    text_parts = 0
    total_text_bytes = 0
    for part_index, part in enumerate(content):
        if isinstance(part, str):
            text_parts += 1
            total_text_bytes += len(part.encode("utf-8"))
            continue
        if not isinstance(part, Mapping):
            _raise(
                f"messages[{message_index}].content[{part_index}]",
                "chat_field_invalid_type",
                "Chat Completions message content parts must be text strings or text objects.",
            )
        if part.get("type") != "text":
            continue
        text = part.get("text")
        if not isinstance(text, str):
            _raise(
                f"messages[{message_index}].content[{part_index}].text",
                "chat_field_invalid_type",
                "Chat Completions text content parts must include string text.",
            )
        text_parts += 1
        total_text_bytes += len(text.encode("utf-8"))

    if text_parts > settings.CHAT_MAX_TEXT_PARTS_PER_MESSAGE:
        _raise(
            f"messages[{message_index}].content",
            "chat_field_too_many_items",
            "A Chat Completions message includes too many text content parts.",
        )
    if total_text_bytes > settings.CHAT_MAX_MESSAGE_CONTENT_BYTES:
        _raise(
            f"messages[{message_index}].content",
            "chat_field_too_large",
            "A Chat Completions message content field exceeds the gateway size limit.",
        )


def _validate_scalar_controls(payload: Mapping[str, Any]) -> None:
    _validate_number_range(
        payload.get("temperature"),
        param="temperature",
        minimum=0,
        maximum=2,
    )
    _validate_number_range(payload.get("top_p"), param="top_p", minimum=0, maximum=1)
    _validate_number_range(
        payload.get("presence_penalty"),
        param="presence_penalty",
        minimum=-2,
        maximum=2,
    )
    _validate_number_range(
        payload.get("frequency_penalty"),
        param="frequency_penalty",
        minimum=-2,
        maximum=2,
    )
    _validate_bool(payload.get("stream"), param="stream")
    _validate_bool(payload.get("logprobs"), param="logprobs")
    _validate_bool(payload.get("parallel_tool_calls"), param="parallel_tool_calls")

    seed = payload.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        _raise("seed", "chat_field_invalid_type", "The 'seed' field must be an integer.")

    top_logprobs = payload.get("top_logprobs")
    if top_logprobs is not None:
        if isinstance(top_logprobs, bool) or not isinstance(top_logprobs, int):
            _raise(
                "top_logprobs",
                "chat_field_invalid_type",
                "The 'top_logprobs' field must be an integer.",
            )
        if top_logprobs < 0 or top_logprobs > 20:
            _raise(
                "top_logprobs",
                "chat_field_value_out_of_range",
                "The 'top_logprobs' field must be between 0 and 20.",
            )
        if payload.get("logprobs") is not True:
            _raise(
                "top_logprobs",
                "chat_field_value_out_of_range",
                "The 'top_logprobs' field requires 'logprobs' to be true.",
            )

    n = payload.get("n")
    if n is not None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            _raise(
                "n",
                "invalid_choice_count",
                "The 'n' field must be the integer 1.",
            )
        if n > 1:
            _raise(
                "n",
                "invalid_choice_count",
                MULTI_CHOICE_UNSUPPORTED_MESSAGE,
            )

    reasoning_effort = payload.get("reasoning_effort")
    if reasoning_effort is not None:
        if not isinstance(reasoning_effort, str) or reasoning_effort not in _REASONING_EFFORT_VALUES:
            _raise(
                "reasoning_effort",
                "chat_field_value_out_of_range",
                "The 'reasoning_effort' field must be one of: minimal, low, medium, high.",
            )


def _validate_number_range(
    value: Any,
    *,
    param: str,
    minimum: float,
    maximum: float,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a number.")
    if not math.isfinite(float(value)) or value < minimum or value > maximum:
        _raise(
            param,
            "chat_field_value_out_of_range",
            f"The '{param}' field is outside the supported range.",
        )


def _validate_bool(value: Any, *, param: str) -> None:
    if value is not None and not isinstance(value, bool):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a boolean.")


def _validate_logit_bias(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "logit_bias",
            "chat_field_invalid_type",
            "The 'logit_bias' field must be a JSON object.",
        )
    if _json_size(value, param="logit_bias") > settings.CHAT_MAX_LOGIT_BIAS_BYTES:
        _raise(
            "logit_bias",
            "chat_field_too_large",
            "The 'logit_bias' field exceeds the gateway size limit.",
        )
    for key, bias in value.items():
        if not isinstance(key, str):
            _raise(
                "logit_bias",
                "chat_field_invalid_type",
                "The 'logit_bias' field must use string token IDs as keys.",
            )
        if isinstance(bias, bool) or not isinstance(bias, int | float):
            _raise(
                "logit_bias",
                "chat_field_invalid_type",
                "The 'logit_bias' field values must be numbers.",
            )
        if not math.isfinite(float(bias)) or bias < -100 or bias > 100:
            _raise(
                "logit_bias",
                "chat_field_value_out_of_range",
                "The 'logit_bias' field values must be between -100 and 100.",
            )


def _validate_stop(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    sequences: list[str]
    if isinstance(value, str):
        sequences = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        sequences = value
    else:
        _raise(
            "stop",
            "chat_field_invalid_type",
            "The 'stop' field must be a string or a list of strings.",
        )

    if len(sequences) > settings.CHAT_MAX_STOP_SEQUENCES:
        _raise(
            "stop",
            "chat_stop_sequence_limit_exceeded",
            "The 'stop' field includes too many stop sequences.",
        )
    for sequence in sequences:
        _validate_string_bytes(
            sequence,
            param="stop",
            max_bytes=settings.CHAT_MAX_STOP_SEQUENCE_BYTES,
            error_code="chat_field_too_large",
            safe_message="A stop sequence exceeds the gateway size limit.",
        )


def _validate_user(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        _raise("user", "chat_field_invalid_type", "The 'user' field must be a string.")
    _validate_string_bytes(
        value,
        param="user",
        max_bytes=settings.CHAT_MAX_USER_FIELD_BYTES,
        error_code="chat_field_too_large",
        safe_message="The 'user' field exceeds the gateway size limit.",
    )


def _validate_tools(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _raise("tools", "chat_field_invalid_type", "The 'tools' field must be a list.")
    if len(value) > settings.CHAT_MAX_TOOLS_PER_REQUEST:
        _raise(
            "tools",
            "chat_tool_count_exceeded",
            "The request includes too many Chat Completions tools.",
        )
    total_schema_bytes = 0
    for index, tool in enumerate(value):
        if not isinstance(tool, Mapping):
            _raise(f"tools[{index}]", "chat_field_invalid_type", "Each tool must be an object.")
        if tool.get("type") != "function":
            continue
        function = tool.get("function")
        total_schema_bytes += _validate_function_definition(
            function,
            param_prefix=f"tools[{index}].function",
            settings=settings,
        )
    if total_schema_bytes > settings.CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES:
        _raise(
            "tools",
            "chat_tool_schema_too_large",
            "The total function-tool schema size exceeds the gateway size limit.",
        )


def _validate_legacy_functions(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _raise(
            "functions",
            "chat_field_invalid_type",
            "The 'functions' field must be a list.",
        )
    if len(value) > settings.CHAT_MAX_FUNCTIONS_PER_REQUEST:
        _raise(
            "functions",
            "chat_tool_count_exceeded",
            "The request includes too many legacy Chat Completions functions.",
        )
    total_schema_bytes = 0
    for index, function in enumerate(value):
        total_schema_bytes += _validate_function_definition(
            function,
            param_prefix=f"functions[{index}]",
            settings=settings,
        )
    if total_schema_bytes > settings.CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES:
        _raise(
            "functions",
            "chat_tool_schema_too_large",
            "The total legacy function schema size exceeds the gateway size limit.",
        )


def _validate_function_definition(
    value: Any,
    *,
    param_prefix: str,
    settings: Settings,
) -> int:
    if not isinstance(value, Mapping):
        _raise(
            param_prefix,
            "chat_field_invalid_type",
            "Function tools must include a function object.",
        )
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        _raise(
            f"{param_prefix}.name",
            "chat_field_invalid_type",
            "Function tool names must be non-empty strings.",
        )
    _validate_string_bytes(
        name,
        param=f"{param_prefix}.name",
        max_bytes=settings.CHAT_MAX_TOOL_NAME_BYTES,
        error_code="chat_field_too_large",
        safe_message="A function tool name exceeds the gateway size limit.",
    )
    description = value.get("description")
    if description is not None:
        if not isinstance(description, str):
            _raise(
                f"{param_prefix}.description",
                "chat_field_invalid_type",
                "Function tool descriptions must be strings.",
            )
        _validate_string_bytes(
            description,
            param=f"{param_prefix}.description",
            max_bytes=settings.CHAT_MAX_TOOL_DESCRIPTION_BYTES,
            error_code="chat_field_too_large",
            safe_message="A function tool description exceeds the gateway size limit.",
        )
    parameters = value.get("parameters")
    if parameters is None:
        return 0
    if not isinstance(parameters, Mapping):
        _raise(
            f"{param_prefix}.parameters",
            "chat_field_invalid_type",
            "Function tool parameters must be a JSON object.",
        )
    size = _json_size(parameters, param=f"{param_prefix}.parameters")
    if size > settings.CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES:
        _raise(
            f"{param_prefix}.parameters",
            "chat_tool_schema_too_large",
            "A function tool schema exceeds the gateway size limit.",
        )
    return size


def _validate_function_choice(
    value: Any,
    *,
    param: str,
    settings: Settings,
) -> None:
    if value is None:
        return
    if isinstance(value, str):
        return
    if not isinstance(value, Mapping):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a string or object.")
    if _json_size(value, param=param) > settings.CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES:
        _raise(
            param,
            "chat_tool_schema_too_large",
            f"The '{param}' field exceeds the gateway size limit.",
        )
    function = value.get("function")
    if function is not None:
        if not isinstance(function, Mapping):
            _raise(
                f"{param}.function",
                "chat_field_invalid_type",
                f"The '{param}.function' field must be an object.",
            )
        name = function.get("name")
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                _raise(
                    f"{param}.function.name",
                    "chat_field_invalid_type",
                    "Function choice names must be non-empty strings.",
                )
            _validate_string_bytes(
                name,
                param=f"{param}.function.name",
                max_bytes=settings.CHAT_MAX_TOOL_NAME_BYTES,
                error_code="chat_field_too_large",
                safe_message="A function choice name exceeds the gateway size limit.",
            )
    name = value.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            _raise(
                f"{param}.name",
                "chat_field_invalid_type",
                "Function choice names must be non-empty strings.",
            )
        _validate_string_bytes(
            name,
            param=f"{param}.name",
            max_bytes=settings.CHAT_MAX_TOOL_NAME_BYTES,
            error_code="chat_field_too_large",
            safe_message="A function choice name exceeds the gateway size limit.",
        )


def _validate_response_format(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "response_format",
            "chat_field_invalid_type",
            "The 'response_format' field must be a JSON object.",
        )
    response_type = value.get("type")
    if response_type not in _RESPONSE_FORMAT_TYPES:
        _raise(
            "response_format.type",
            "chat_field_value_out_of_range",
            "The 'response_format.type' field must be text, json_object, or json_schema.",
        )
    if response_type == "json_schema":
        json_schema = value.get("json_schema")
        if not isinstance(json_schema, Mapping):
            _raise(
                "response_format.json_schema",
                "chat_field_invalid_type",
                "The 'response_format.json_schema' field must be a JSON object.",
            )
        if _json_size(json_schema, param="response_format.json_schema") > settings.CHAT_MAX_RESPONSE_FORMAT_SCHEMA_BYTES:
            _raise(
                "response_format.json_schema",
                "chat_response_format_schema_too_large",
                "The response format JSON schema exceeds the gateway size limit.",
            )


def _validate_metadata(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "metadata",
            "chat_field_invalid_type",
            "The 'metadata' field must be a JSON object.",
        )
    if len(value) > settings.CHAT_MAX_METADATA_KEYS:
        _raise(
            "metadata",
            "chat_field_too_many_items",
            "The 'metadata' field includes too many keys.",
        )
    for key in value:
        if not isinstance(key, str):
            _raise(
                "metadata",
                "chat_field_invalid_type",
                "The 'metadata' field must use string keys.",
            )
        _validate_string_bytes(
            key,
            param="metadata",
            max_bytes=settings.CHAT_MAX_METADATA_KEY_BYTES,
            error_code="chat_field_too_large",
            safe_message="A metadata key exceeds the gateway size limit.",
        )
    if _json_size(value, param="metadata") > settings.CHAT_MAX_METADATA_BYTES:
        _raise(
            "metadata",
            "chat_metadata_too_large",
            "The 'metadata' field exceeds the gateway size limit.",
        )


def _validate_prediction(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "prediction",
            "chat_field_invalid_type",
            "The 'prediction' field must be a JSON object.",
        )
    if _json_size(value, param="prediction") > settings.CHAT_MAX_PREDICTION_BYTES:
        _raise(
            "prediction",
            "chat_field_too_large",
            "The 'prediction' field exceeds the gateway size limit.",
        )


def _validate_stream_options(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "stream_options",
            "invalid_stream_options",
            "The 'stream_options' field must be a JSON object.",
        )
    if _json_size(value, param="stream_options") > settings.CHAT_MAX_STREAM_OPTIONS_BYTES:
        _raise(
            "stream_options",
            "chat_field_too_large",
            "The 'stream_options' field exceeds the gateway size limit.",
        )


def _json_size(value: Any, *, param: str) -> int:
    try:
        return len(canonical_json_bytes(value))
    except ValueError as exc:
        raise ChatCompletionRequestCapsError(
            f"The '{param}' field must be JSON-serializable.",
            param=param,
            error_code="chat_field_invalid_type",
        ) from exc


def _validate_string_bytes(
    value: str,
    *,
    param: str,
    max_bytes: int,
    error_code: str,
    safe_message: str,
) -> None:
    if len(value.encode("utf-8")) > max_bytes:
        _raise(param, error_code, safe_message)


def _raise(param: str, error_code: str, safe_message: str) -> None:
    raise ChatCompletionRequestCapsError(
        safe_message,
        param=param,
        error_code=error_code,
    )
