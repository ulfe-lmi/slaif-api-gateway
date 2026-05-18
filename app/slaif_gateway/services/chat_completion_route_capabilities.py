"""Route/model capability policy for current Chat Completions requests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from slaif_gateway.services.hosted_tool_policy import is_search_specific_chat_completion_model
from slaif_gateway.services.policy_errors import RequestPolicyError

CHAT_COMPLETIONS_CAPABILITIES_KEY = "chat_completions"

CHAT_CAPABILITY_TEXT = "chat_text"
CHAT_CAPABILITY_STREAMING = "chat_streaming"
CHAT_CAPABILITY_FUNCTION_TOOLS = "chat_function_tools"
CHAT_CAPABILITY_CUSTOM_TOOLS = "chat_custom_tools"
CHAT_CAPABILITY_LEGACY_FUNCTIONS = "chat_legacy_functions"
CHAT_CAPABILITY_STRUCTURED_OUTPUTS = "chat_structured_outputs"
CHAT_CAPABILITY_JSON_MODE = "chat_json_mode"
CHAT_CAPABILITY_LOGPROBS = "chat_logprobs"
CHAT_CAPABILITY_REASONING_USAGE = "chat_reasoning_usage"
CHAT_CAPABILITY_CACHED_INPUT_USAGE = "chat_cached_input_usage"
CHAT_CAPABILITY_HOSTED_WEB_SEARCH = "hosted_web_search"
CHAT_CAPABILITY_HOSTED_FILE_SEARCH = "hosted_file_search"
CHAT_CAPABILITY_HOSTED_CODE_INTERPRETER = "hosted_code_interpreter"
CHAT_CAPABILITY_HOSTED_COMPUTER_USE = "hosted_computer_use"
CHAT_CAPABILITY_HOSTED_IMAGE_GENERATION = "hosted_image_generation"
CHAT_CAPABILITY_HOSTED_TOOL_SEARCH = "hosted_tool_search"
CHAT_CAPABILITY_EXTERNAL_MCP_CONNECTORS = "external_mcp_connectors"
CHAT_CAPABILITY_IMAGE_INPUTS = "chat_image_inputs"
CHAT_CAPABILITY_MULTIMODAL = "chat_multimodal"
CHAT_CAPABILITY_AUDIO = "chat_audio"
CHAT_CAPABILITY_FILE_INPUTS = "chat_file_inputs"
CHAT_CAPABILITY_AUDIO_INPUTS = "chat_audio_inputs"
CHAT_CAPABILITY_SERVICE_TIER_NON_DEFAULT = "chat_service_tier_non_default"
CHAT_CAPABILITY_MULTIPLE_CHOICES = "chat_multiple_choices"

KNOWN_CHAT_COMPLETION_CAPABILITIES = frozenset(
    {
        CHAT_CAPABILITY_TEXT,
        CHAT_CAPABILITY_STREAMING,
        CHAT_CAPABILITY_FUNCTION_TOOLS,
        CHAT_CAPABILITY_CUSTOM_TOOLS,
        CHAT_CAPABILITY_LEGACY_FUNCTIONS,
        CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
        CHAT_CAPABILITY_JSON_MODE,
        CHAT_CAPABILITY_LOGPROBS,
        CHAT_CAPABILITY_REASONING_USAGE,
        CHAT_CAPABILITY_CACHED_INPUT_USAGE,
        CHAT_CAPABILITY_HOSTED_WEB_SEARCH,
        CHAT_CAPABILITY_HOSTED_FILE_SEARCH,
        CHAT_CAPABILITY_HOSTED_CODE_INTERPRETER,
        CHAT_CAPABILITY_HOSTED_COMPUTER_USE,
        CHAT_CAPABILITY_HOSTED_IMAGE_GENERATION,
        CHAT_CAPABILITY_HOSTED_TOOL_SEARCH,
        CHAT_CAPABILITY_EXTERNAL_MCP_CONNECTORS,
        CHAT_CAPABILITY_IMAGE_INPUTS,
        CHAT_CAPABILITY_MULTIMODAL,
        CHAT_CAPABILITY_AUDIO,
        CHAT_CAPABILITY_FILE_INPUTS,
        CHAT_CAPABILITY_AUDIO_INPUTS,
        CHAT_CAPABILITY_SERVICE_TIER_NON_DEFAULT,
        CHAT_CAPABILITY_MULTIPLE_CHOICES,
    }
)

_HOSTED_TOOL_CAPABILITY_BY_TYPE = {
    "web_search": CHAT_CAPABILITY_HOSTED_WEB_SEARCH,
    "web_search_preview": CHAT_CAPABILITY_HOSTED_WEB_SEARCH,
    "file_search": CHAT_CAPABILITY_HOSTED_FILE_SEARCH,
    "code_interpreter": CHAT_CAPABILITY_HOSTED_CODE_INTERPRETER,
    "computer": CHAT_CAPABILITY_HOSTED_COMPUTER_USE,
    "computer_use": CHAT_CAPABILITY_HOSTED_COMPUTER_USE,
    "image_generation": CHAT_CAPABILITY_HOSTED_IMAGE_GENERATION,
    "tool_search": CHAT_CAPABILITY_HOSTED_TOOL_SEARCH,
}


def default_chat_completion_capabilities(*, supports_streaming: bool = True) -> dict[str, bool]:
    """Return conservative metadata for currently supported Chat Completions routes."""

    return {
        CHAT_CAPABILITY_TEXT: True,
        CHAT_CAPABILITY_STREAMING: bool(supports_streaming),
        CHAT_CAPABILITY_FUNCTION_TOOLS: True,
        CHAT_CAPABILITY_CUSTOM_TOOLS: False,
        CHAT_CAPABILITY_LEGACY_FUNCTIONS: True,
        CHAT_CAPABILITY_STRUCTURED_OUTPUTS: True,
        CHAT_CAPABILITY_JSON_MODE: True,
        CHAT_CAPABILITY_LOGPROBS: True,
        CHAT_CAPABILITY_REASONING_USAGE: True,
        CHAT_CAPABILITY_CACHED_INPUT_USAGE: True,
        CHAT_CAPABILITY_HOSTED_WEB_SEARCH: False,
        CHAT_CAPABILITY_HOSTED_FILE_SEARCH: False,
        CHAT_CAPABILITY_HOSTED_CODE_INTERPRETER: False,
        CHAT_CAPABILITY_HOSTED_COMPUTER_USE: False,
        CHAT_CAPABILITY_HOSTED_IMAGE_GENERATION: False,
        CHAT_CAPABILITY_HOSTED_TOOL_SEARCH: False,
        CHAT_CAPABILITY_EXTERNAL_MCP_CONNECTORS: False,
        CHAT_CAPABILITY_IMAGE_INPUTS: False,
        CHAT_CAPABILITY_MULTIMODAL: False,
        CHAT_CAPABILITY_AUDIO: False,
        CHAT_CAPABILITY_FILE_INPUTS: False,
        CHAT_CAPABILITY_AUDIO_INPUTS: False,
        CHAT_CAPABILITY_SERVICE_TIER_NON_DEFAULT: False,
        CHAT_CAPABILITY_MULTIPLE_CHOICES: False,
    }


def ensure_default_chat_completion_capabilities(
    capabilities: Mapping[str, object] | None,
    *,
    supports_streaming: bool = True,
    endpoint: str = "/v1/chat/completions",
) -> dict[str, object]:
    """Add explicit Chat Completions capability metadata for new chat routes.

    Existing non-chat metadata is preserved. If the caller already supplied a
    chat_completions block, it is left untouched so admins can intentionally
    narrow a route's capability surface.
    """

    normalized = dict(capabilities or {})
    if endpoint == "/v1/chat/completions" and CHAT_COMPLETIONS_CAPABILITIES_KEY not in normalized:
        normalized[CHAT_COMPLETIONS_CAPABILITIES_KEY] = default_chat_completion_capabilities(
            supports_streaming=supports_streaming
        )
    return normalized


@dataclass(frozen=True, slots=True)
class ChatCompletionRouteCapabilityFinding:
    """Safe route/model capability finding that excludes request values."""

    capability: str
    field: str
    error_code: str
    safe_message: str


class ChatCompletionRouteCapabilityError(RequestPolicyError):
    """Request-policy error for route/model capability mismatches."""

    def __init__(self, finding: ChatCompletionRouteCapabilityFinding) -> None:
        self.error_code = finding.error_code
        self.capability = finding.capability
        super().__init__(finding.safe_message, param=finding.field)


def enforce_chat_completion_route_capabilities(
    payload: Mapping[str, Any],
    *,
    route_capabilities: Mapping[str, object] | None,
    route_supports_streaming: bool,
    requested_model: str,
) -> None:
    """Raise when a request shape exceeds route/model Chat Completions metadata."""

    capabilities = _parse_route_capabilities(
        route_capabilities,
        route_supports_streaming=route_supports_streaming,
    )
    findings = classify_chat_completion_route_capability_requirements(
        payload,
        requested_model=requested_model,
    )
    for finding in findings:
        if not capabilities.get(finding.capability, False):
            raise ChatCompletionRouteCapabilityError(finding)


def classify_chat_completion_route_capability_requirements(
    payload: Mapping[str, Any],
    *,
    requested_model: str,
) -> tuple[ChatCompletionRouteCapabilityFinding, ...]:
    """Return safe capability requirements implied by the accepted request shape."""

    findings = [
        ChatCompletionRouteCapabilityFinding(
            capability=CHAT_CAPABILITY_TEXT,
            field="model",
            error_code="chat_capability_not_supported",
            safe_message="This model route does not support text Chat Completions.",
        )
    ]

    if payload.get("stream") is True:
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_STREAMING,
                field="stream",
                error_code="chat_capability_not_supported",
                safe_message="This model route does not support Chat Completions streaming.",
            )
        )

    if _effective_choice_count(payload) > 1:
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_MULTIPLE_CHOICES,
                field="n",
                error_code="chat_multiple_choices_capability_not_supported",
                safe_message="This model route does not support multiple Chat Completions choices.",
            )
        )

    if _uses_function_tools(payload):
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_FUNCTION_TOOLS,
                field="tools",
                error_code="chat_capability_not_supported",
                safe_message="This model route does not support local Chat Completions function tools.",
            )
        )

    if _uses_custom_tools(payload):
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_CUSTOM_TOOLS,
                field="tools",
                error_code="chat_custom_tool_capability_not_supported",
                safe_message=(
                    "This model route does not support local Chat Completions custom tools."
                ),
            )
        )

    if _uses_image_inputs(payload):
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_IMAGE_INPUTS,
                field="messages",
                error_code="chat_image_input_capability_not_supported",
                safe_message="This model route does not support Chat Completions image input.",
            )
        )

    if _uses_file_inputs(payload):
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_FILE_INPUTS,
                field="messages",
                error_code="chat_file_input_capability_not_supported",
                safe_message="This model route does not support Chat Completions file input.",
            )
        )

    if _uses_audio_inputs(payload):
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_AUDIO_INPUTS,
                field="messages",
                error_code="chat_audio_input_capability_not_supported",
                safe_message="This model route does not support Chat Completions audio input.",
            )
        )

    if "functions" in payload or "function_call" in payload:
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_LEGACY_FUNCTIONS,
                field="functions" if "functions" in payload else "function_call",
                error_code="chat_capability_not_supported",
                safe_message="This model route does not support legacy Chat Completions functions.",
            )
        )

    response_format = payload.get("response_format")
    if isinstance(response_format, Mapping):
        response_format_type = response_format.get("type")
        if response_format_type == "json_object":
            findings.append(
                ChatCompletionRouteCapabilityFinding(
                    capability=CHAT_CAPABILITY_JSON_MODE,
                    field="response_format",
                    error_code="chat_capability_not_supported",
                    safe_message="This model route does not support Chat Completions JSON mode.",
                )
            )
        elif response_format_type == "json_schema":
            findings.append(
                ChatCompletionRouteCapabilityFinding(
                    capability=CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
                    field="response_format",
                    error_code="chat_capability_not_supported",
                    safe_message=(
                        "This model route does not support Chat Completions structured outputs."
                    ),
                )
            )

    if payload.get("logprobs") is True or "top_logprobs" in payload:
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_LOGPROBS,
                field="logprobs" if payload.get("logprobs") is True else "top_logprobs",
                error_code="chat_capability_not_supported",
                safe_message="This model route does not support Chat Completions logprobs.",
            )
        )

    if "reasoning_effort" in payload:
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_REASONING_USAGE,
                field="reasoning_effort",
                error_code="chat_capability_not_supported",
                safe_message="This model route does not support Chat Completions reasoning controls.",
            )
        )

    if is_search_specific_chat_completion_model(requested_model) or "web_search_options" in payload:
        findings.append(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_CAPABILITY_HOSTED_WEB_SEARCH,
                field="model" if is_search_specific_chat_completion_model(requested_model) else "web_search_options",
                error_code="chat_hosted_tool_not_allowed",
                safe_message=(
                    "This model route does not enable hosted Chat Completions web search."
                ),
            )
        )

    findings.extend(_hosted_tool_findings(payload))

    return tuple(findings)


def _parse_route_capabilities(
    route_capabilities: Mapping[str, object] | None,
    *,
    route_supports_streaming: bool,
) -> dict[str, bool]:
    if not route_capabilities or CHAT_COMPLETIONS_CAPABILITIES_KEY not in route_capabilities:
        return default_chat_completion_capabilities(supports_streaming=route_supports_streaming)

    raw = route_capabilities.get(CHAT_COMPLETIONS_CAPABILITIES_KEY)
    if not isinstance(raw, Mapping):
        raise ChatCompletionRouteCapabilityError(
            ChatCompletionRouteCapabilityFinding(
                capability=CHAT_COMPLETIONS_CAPABILITIES_KEY,
                field="model",
                error_code="chat_route_capability_invalid",
                safe_message="Chat Completions route capability metadata is invalid.",
            )
        )

    parsed: dict[str, bool] = {}
    for key, value in raw.items():
        capability = str(key)
        if capability not in KNOWN_CHAT_COMPLETION_CAPABILITIES:
            raise ChatCompletionRouteCapabilityError(
                ChatCompletionRouteCapabilityFinding(
                    capability=capability,
                    field="model",
                    error_code="chat_route_capability_invalid",
                    safe_message="Chat Completions route capability metadata contains an unknown flag.",
                )
            )
        if not isinstance(value, bool):
            raise ChatCompletionRouteCapabilityError(
                ChatCompletionRouteCapabilityFinding(
                    capability=capability,
                    field="model",
                    error_code="chat_route_capability_invalid",
                    safe_message="Chat Completions route capability metadata must use boolean flags.",
                )
            )
        parsed[capability] = value

    return parsed


def _uses_function_tools(payload: Mapping[str, Any]) -> bool:
    tools = payload.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, Mapping) and tool.get("type") == "function":
                return True

    tool_choice = payload.get("tool_choice")
    return isinstance(tool_choice, Mapping) and tool_choice.get("type") == "function"


def _effective_choice_count(payload: Mapping[str, Any]) -> int:
    value = payload.get("n")
    if isinstance(value, bool) or not isinstance(value, int):
        return 1
    return value


def _uses_custom_tools(payload: Mapping[str, Any]) -> bool:
    tools = payload.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, Mapping) and tool.get("type") == "custom":
                return True

    tool_choice = payload.get("tool_choice")
    return isinstance(tool_choice, Mapping) and tool_choice.get("type") == "custom"


def _uses_image_inputs(payload: Mapping[str, Any]) -> bool:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "image_url":
                return True
    return False


def _uses_file_inputs(payload: Mapping[str, Any]) -> bool:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "file":
                return True
    return False


def _uses_audio_inputs(payload: Mapping[str, Any]) -> bool:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "input_audio":
                return True
    return False


def _hosted_tool_findings(payload: Mapping[str, Any]) -> list[ChatCompletionRouteCapabilityFinding]:
    findings: list[ChatCompletionRouteCapabilityFinding] = []
    tools = payload.get("tools")
    if isinstance(tools, list):
        for index, tool in enumerate(tools):
            if not isinstance(tool, Mapping):
                continue
            tool_type = tool.get("type")
            if not isinstance(tool_type, str):
                continue
            capability = _HOSTED_TOOL_CAPABILITY_BY_TYPE.get(tool_type)
            if capability is None:
                continue
            findings.append(
                ChatCompletionRouteCapabilityFinding(
                    capability=capability,
                    field=f"tools[{index}].type",
                    error_code="chat_hosted_tool_not_allowed",
                    safe_message="This model route does not enable that hosted Chat Completions tool.",
                )
            )

    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, Mapping):
        choice_type = tool_choice.get("type")
        if isinstance(choice_type, str):
            capability = _HOSTED_TOOL_CAPABILITY_BY_TYPE.get(choice_type)
            if capability is not None:
                findings.append(
                    ChatCompletionRouteCapabilityFinding(
                        capability=capability,
                        field="tool_choice.type",
                        error_code="chat_hosted_tool_not_allowed",
                        safe_message=(
                            "This model route does not enable that hosted Chat Completions tool."
                        ),
                    )
                )
    return findings
