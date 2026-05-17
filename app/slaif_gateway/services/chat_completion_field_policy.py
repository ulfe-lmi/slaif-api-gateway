"""Fail-closed field registry for current Chat Completions requests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
)
from slaif_gateway.services.policy_errors import RequestPolicyError

METADATA_MAX_BYTES = 8192


class ChatCompletionFieldClassification(StrEnum):
    """Registry buckets for top-level Chat Completions request fields."""

    FORWARDED_SUPPORTED = "forwarded_supported"
    GATEWAY_MUTATED = "gateway_mutated"
    LOCAL_TOOL_FEATURE = "local_tool_feature"
    HOSTED_CAPABILITY = "hosted_capability"
    LIFECYCLE_OR_STATE = "lifecycle_or_state"
    UNSUPPORTED_MODALITY = "unsupported_modality"
    EXPLICITLY_REJECTED = "explicitly_rejected"
    TRUSTED_CALIBRATION_ONLY = "trusted_calibration_only"


CHAT_COMPLETION_FIELD_REGISTRY: dict[str, ChatCompletionFieldClassification] = {
    "model": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "messages": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "temperature": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "top_p": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "stop": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "seed": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "user": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "logprobs": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "top_logprobs": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "presence_penalty": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "frequency_penalty": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "stream": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "stream_options": ChatCompletionFieldClassification.GATEWAY_MUTATED,
    "max_tokens": ChatCompletionFieldClassification.GATEWAY_MUTATED,
    "max_completion_tokens": ChatCompletionFieldClassification.GATEWAY_MUTATED,
    "n": ChatCompletionFieldClassification.GATEWAY_MUTATED,
    "tools": ChatCompletionFieldClassification.LOCAL_TOOL_FEATURE,
    "tool_choice": ChatCompletionFieldClassification.LOCAL_TOOL_FEATURE,
    "functions": ChatCompletionFieldClassification.LOCAL_TOOL_FEATURE,
    "function_call": ChatCompletionFieldClassification.LOCAL_TOOL_FEATURE,
    "response_format": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "metadata": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "reasoning_effort": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "parallel_tool_calls": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "modalities": ChatCompletionFieldClassification.UNSUPPORTED_MODALITY,
    "audio": ChatCompletionFieldClassification.UNSUPPORTED_MODALITY,
    "prediction": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "service_tier": ChatCompletionFieldClassification.FORWARDED_SUPPORTED,
    "web_search_options": ChatCompletionFieldClassification.HOSTED_CAPABILITY,
    "external_web_access": ChatCompletionFieldClassification.EXPLICITLY_REJECTED,
    "background": ChatCompletionFieldClassification.LIFECYCLE_OR_STATE,
    "store": ChatCompletionFieldClassification.LIFECYCLE_OR_STATE,
    "previous_response_id": ChatCompletionFieldClassification.LIFECYCLE_OR_STATE,
    "conversation": ChatCompletionFieldClassification.LIFECYCLE_OR_STATE,
    "defer_loading": ChatCompletionFieldClassification.EXPLICITLY_REJECTED,
}

_TEXT_ONLY_MODALITIES = frozenset({"text"})
_UNSUPPORTED_MESSAGE_CONTENT_PART_TYPES = frozenset(
    {
        "audio",
        "file",
        "image",
        "image_url",
        "input_audio",
        "input_file",
        "input_image",
        "video",
    }
)


@dataclass(frozen=True, slots=True)
class ChatCompletionFieldFinding:
    """Safe field-policy finding that never contains request values."""

    rejected_field: str
    classification: ChatCompletionFieldClassification | str
    error_code: str
    safe_message: str


class ChatCompletionFieldPolicyError(RequestPolicyError):
    """Request-policy error for denied Chat Completions request fields."""

    def __init__(self, finding: ChatCompletionFieldFinding) -> None:
        self.error_code = finding.error_code
        self.rejected_field = finding.rejected_field
        self.classification = str(finding.classification)
        super().__init__(finding.safe_message, param=finding.rejected_field)


def classify_chat_completion_request_fields(
    payload: Mapping[str, Any],
    *,
    capability_policy_mode: str = "standard",
) -> dict[str, ChatCompletionFieldClassification | str]:
    """Return the registry classification for each present top-level field."""

    _ = capability_policy_mode
    return {
        str(field): CHAT_COMPLETION_FIELD_REGISTRY.get(
            str(field),
            "unknown",
        )
        for field in payload
    }


def enforce_chat_completion_field_policy(
    payload: Mapping[str, Any],
    *,
    capability_policy_mode: str = "standard",
) -> None:
    """Raise on unknown or unsupported Chat Completions fields before forwarding."""

    trusted_discovery = (
        capability_policy_mode == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    )
    for field in payload:
        field_name = str(field)
        classification = CHAT_COMPLETION_FIELD_REGISTRY.get(field_name)
        if classification is None:
            raise ChatCompletionFieldPolicyError(_unknown_field_finding(field_name))

        finding = _finding_for_known_field(
            field_name,
            payload[field],
            classification=classification,
            trusted_discovery=trusted_discovery,
        )
        if finding is not None:
            raise ChatCompletionFieldPolicyError(finding)

    message_finding = _finding_for_message_content(payload.get("messages"))
    if message_finding is not None:
        raise ChatCompletionFieldPolicyError(message_finding)


def _finding_for_known_field(
    field_name: str,
    value: Any,
    *,
    classification: ChatCompletionFieldClassification,
    trusted_discovery: bool,
) -> ChatCompletionFieldFinding | None:
    if field_name == "web_search_options":
        if trusted_discovery:
            return None
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="web_search_not_allowed",
            safe_message="Chat Completions web search is not enabled by this gateway.",
        )

    if field_name == "external_web_access":
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="web_search_not_allowed",
            safe_message="External web access is not enabled by this gateway.",
        )

    if field_name == "background" and value is True:
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="background_not_allowed",
            safe_message="Background provider execution is not enabled by this gateway.",
        )

    if field_name == "store" and value is True:
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="background_not_allowed",
            safe_message="Provider-side stored state is not enabled by this gateway.",
        )

    if field_name == "previous_response_id":
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="background_not_allowed",
            safe_message="Provider-side response state is not enabled by this gateway.",
        )

    if field_name == "conversation":
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="background_not_allowed",
            safe_message="Provider-side conversation state is not enabled by this gateway.",
        )

    if field_name == "defer_loading":
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="hosted_tool_not_allowed",
            safe_message="Deferred hosted-tool loading is not enabled by this gateway.",
        )

    if field_name == "modalities":
        return _modalities_finding(value, classification=classification)

    if field_name == "audio":
        return ChatCompletionFieldFinding(
            rejected_field=field_name,
            classification=classification,
            error_code="unsupported_chat_completion_modality",
            safe_message=(
                "Chat Completions audio output is not enabled because this gateway "
                "does not yet account for audio pricing."
            ),
        )

    if field_name == "service_tier":
        return _service_tier_finding(value, classification=classification)

    if field_name == "metadata":
        return _metadata_finding(value, classification=classification)

    if field_name == "tools":
        return _tools_finding(value, classification=classification)

    return None


def _modalities_finding(
    value: Any,
    *,
    classification: ChatCompletionFieldClassification,
) -> ChatCompletionFieldFinding | None:
    if isinstance(value, str):
        requested = {value}
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        requested = {str(item) for item in value}
    else:
        requested = {"unsupported"}

    if requested and requested <= _TEXT_ONLY_MODALITIES:
        return None

    return ChatCompletionFieldFinding(
        rejected_field="modalities",
        classification=classification,
        error_code="unsupported_chat_completion_modality",
        safe_message=(
            "Only text Chat Completions modalities are enabled by this gateway."
        ),
    )


def _service_tier_finding(
    value: Any,
    *,
    classification: ChatCompletionFieldClassification,
) -> ChatCompletionFieldFinding | None:
    if value in (None, "auto"):
        return None
    return ChatCompletionFieldFinding(
        rejected_field="service_tier",
        classification=classification,
        error_code="service_tier_not_supported",
        safe_message=(
            "Non-default Chat Completions service tiers are not enabled because "
            "gateway pricing is not service-tier aware."
        ),
    )


def _metadata_finding(
    value: Any,
    *,
    classification: ChatCompletionFieldClassification,
) -> ChatCompletionFieldFinding | None:
    if not isinstance(value, Mapping):
        return ChatCompletionFieldFinding(
            rejected_field="metadata",
            classification=classification,
            error_code="invalid_chat_completion_metadata",
            safe_message="The 'metadata' field must be a JSON object.",
        )
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return ChatCompletionFieldFinding(
            rejected_field="metadata",
            classification=classification,
            error_code="invalid_chat_completion_metadata",
            safe_message="The 'metadata' field must be JSON-serializable.",
        )
    if len(serialized.encode("utf-8")) > METADATA_MAX_BYTES:
        return ChatCompletionFieldFinding(
            rejected_field="metadata",
            classification=classification,
            error_code="chat_completion_metadata_too_large",
            safe_message=(
                "The 'metadata' field exceeds the gateway size limit for "
                "Chat Completions metadata."
            ),
        )
    return None


def _tools_finding(
    value: Any,
    *,
    classification: ChatCompletionFieldClassification,
) -> ChatCompletionFieldFinding | None:
    if not isinstance(value, list):
        return None
    for index, tool in enumerate(value):
        if not isinstance(tool, Mapping):
            continue
        if tool.get("type") == "custom":
            return ChatCompletionFieldFinding(
                rejected_field=f"tools[{index}].type",
                classification=classification,
                error_code="custom_tool_not_supported",
                safe_message=(
                    "Chat Completions custom tools are not enabled by this gateway."
                ),
            )
    return None


def _finding_for_message_content(messages: Any) -> ChatCompletionFieldFinding | None:
    if not isinstance(messages, list):
        return None

    for message_index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part_index, part in enumerate(content):
            if isinstance(part, str):
                continue
            if not isinstance(part, Mapping):
                return _unsupported_message_part_finding(message_index, part_index)
            part_type = part.get("type")
            if part_type == "text":
                continue
            if isinstance(part_type, str) and part_type in _UNSUPPORTED_MESSAGE_CONTENT_PART_TYPES:
                return _unsupported_message_part_finding(message_index, part_index)
            return _unsupported_message_part_finding(message_index, part_index)
    return None


def _unsupported_message_part_finding(
    message_index: int,
    part_index: int,
) -> ChatCompletionFieldFinding:
    return ChatCompletionFieldFinding(
        rejected_field=f"messages[{message_index}].content[{part_index}].type",
        classification=ChatCompletionFieldClassification.UNSUPPORTED_MODALITY,
        error_code="unsupported_chat_completion_modality",
        safe_message=(
            "Only text Chat Completions message content is enabled because this "
            "gateway does not yet account for image, audio, file, or video inputs."
        ),
    )


def _unknown_field_finding(field_name: str) -> ChatCompletionFieldFinding:
    return ChatCompletionFieldFinding(
        rejected_field=field_name,
        classification="unknown",
        error_code="unknown_chat_completion_field",
        safe_message="Unknown Chat Completions request field is not enabled by this gateway.",
    )
