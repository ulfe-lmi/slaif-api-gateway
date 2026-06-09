"""Route/model capability policy for text-output Responses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slaif_gateway.services.policy_errors import RequestPolicyError

RESPONSES_CAPABILITIES_KEY = "responses"
RESPONSES_CAPABILITY_TEXT = "text"
RESPONSES_CAPABILITY_STATELESS = "stateless"
RESPONSES_CAPABILITY_STREAMING = "streaming"
RESPONSES_CAPABILITY_TOOLS = "tools"
RESPONSES_CAPABILITY_FUNCTION_TOOLS = "function_tools"
RESPONSES_CAPABILITY_CUSTOM_TOOLS = "custom_tools"
RESPONSES_CAPABILITY_IMAGE_INPUT = "image_input"
RESPONSES_CAPABILITY_FILE_INPUT = "file_input"
RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT = "input_token_count"
RESPONSES_CAPABILITY_STORED_RESPONSES = "stored_responses"
RESPONSES_CAPABILITY_PREVIOUS_RESPONSE_ID = "previous_response_id"
RESPONSES_CAPABILITY_LIST_INPUT_ITEMS = "list_input_items"
RESPONSES_CAPABILITY_COMPACT = "compact"
RESPONSES_CAPABILITY_CONVERSATIONS = "conversations"
RESPONSES_CAPABILITY_MULTIMODAL = "multimodal"
RESPONSES_CAPABILITY_STORAGE = "storage"
RESPONSES_CAPABILITY_BACKGROUND = "background"
RESPONSES_CAPABILITY_JSON_MODE = "json_mode"
RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS = "structured_outputs"

KNOWN_RESPONSES_CAPABILITIES = frozenset(
    {
        RESPONSES_CAPABILITY_TEXT,
        RESPONSES_CAPABILITY_STATELESS,
        RESPONSES_CAPABILITY_STREAMING,
        RESPONSES_CAPABILITY_TOOLS,
        RESPONSES_CAPABILITY_FUNCTION_TOOLS,
        RESPONSES_CAPABILITY_CUSTOM_TOOLS,
        RESPONSES_CAPABILITY_IMAGE_INPUT,
        RESPONSES_CAPABILITY_FILE_INPUT,
        RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT,
        RESPONSES_CAPABILITY_STORED_RESPONSES,
        RESPONSES_CAPABILITY_PREVIOUS_RESPONSE_ID,
        RESPONSES_CAPABILITY_LIST_INPUT_ITEMS,
        RESPONSES_CAPABILITY_COMPACT,
        RESPONSES_CAPABILITY_CONVERSATIONS,
        RESPONSES_CAPABILITY_MULTIMODAL,
        RESPONSES_CAPABILITY_STORAGE,
        RESPONSES_CAPABILITY_BACKGROUND,
        RESPONSES_CAPABILITY_JSON_MODE,
        RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS,
    }
)


def default_responses_capabilities() -> dict[str, bool]:
    """Return conservative metadata for this first Responses slice."""

    return {
        RESPONSES_CAPABILITY_TEXT: True,
        RESPONSES_CAPABILITY_STATELESS: True,
        RESPONSES_CAPABILITY_STREAMING: False,
        RESPONSES_CAPABILITY_TOOLS: False,
        RESPONSES_CAPABILITY_FUNCTION_TOOLS: False,
        RESPONSES_CAPABILITY_CUSTOM_TOOLS: False,
        RESPONSES_CAPABILITY_IMAGE_INPUT: False,
        RESPONSES_CAPABILITY_FILE_INPUT: False,
        RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT: False,
        RESPONSES_CAPABILITY_STORED_RESPONSES: False,
        RESPONSES_CAPABILITY_PREVIOUS_RESPONSE_ID: False,
        RESPONSES_CAPABILITY_LIST_INPUT_ITEMS: False,
        RESPONSES_CAPABILITY_COMPACT: False,
        RESPONSES_CAPABILITY_CONVERSATIONS: False,
        RESPONSES_CAPABILITY_MULTIMODAL: False,
        RESPONSES_CAPABILITY_STORAGE: False,
        RESPONSES_CAPABILITY_BACKGROUND: False,
        RESPONSES_CAPABILITY_JSON_MODE: False,
        RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS: False,
    }


def ensure_default_responses_capabilities(
    capabilities: Mapping[str, object] | None,
    *,
    endpoint: str,
) -> dict[str, object]:
    """Add explicit Responses metadata only when creating Responses routes."""

    normalized = dict(capabilities or {})
    if endpoint in {"/v1/responses", "/v1/responses/input_tokens", "/v1/responses/compact"} and (
        RESPONSES_CAPABILITIES_KEY not in normalized
    ):
        normalized[RESPONSES_CAPABILITIES_KEY] = default_responses_capabilities()
    return normalized


@dataclass(frozen=True, slots=True)
class ResponsesRouteCapabilityFinding:
    capability: str
    field: str
    error_code: str
    safe_message: str


class ResponsesRouteCapabilityError(RequestPolicyError):
    """Request-policy error for Responses route capability mismatches."""

    def __init__(self, finding: ResponsesRouteCapabilityFinding) -> None:
        self.error_code = finding.error_code
        super().__init__(finding.safe_message, param=finding.field)


def enforce_responses_route_capabilities(
    *,
    route_capabilities: Mapping[str, object] | None,
    streaming_requested: bool = False,
    route_supports_streaming: bool = False,
    json_mode_requested: bool = False,
    structured_output_requested: bool = False,
    function_tools_requested: bool = False,
    custom_tools_requested: bool = False,
    image_input_requested: bool = False,
    file_input_requested: bool = False,
    input_token_count_requested: bool = False,
    stored_responses_requested: bool = False,
    previous_response_id_requested: bool = False,
    list_input_items_requested: bool = False,
    compact_requested: bool = False,
    conversations_requested: bool = False,
) -> None:
    """Require explicit Responses metadata and fail closed."""

    capabilities = _parse_route_capabilities(route_capabilities)
    required = (
        ResponsesRouteCapabilityFinding(
            capability=RESPONSES_CAPABILITY_TEXT,
            field="model",
            error_code="responses_route_capability_not_supported",
            safe_message="This model route does not support text Responses.",
        ),
    )
    for finding in required:
        if capabilities.get(finding.capability) is not True:
            raise ResponsesRouteCapabilityError(finding)

    if previous_response_id_requested:
        if capabilities.get(RESPONSES_CAPABILITY_PREVIOUS_RESPONSE_ID) is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_PREVIOUS_RESPONSE_ID,
                    field="previous_response_id",
                    error_code="responses_previous_response_capability_not_supported",
                    safe_message=(
                        "This model route does not support Responses previous_response_id."
                    ),
                )
            )

    if list_input_items_requested:
        if capabilities.get(RESPONSES_CAPABILITY_LIST_INPUT_ITEMS) is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_LIST_INPUT_ITEMS,
                    field="response_id",
                    error_code="responses_list_input_items_capability_not_supported",
                    safe_message=(
                        "This model route does not support Responses input-item listing."
                    ),
                )
            )

    if compact_requested:
        if capabilities.get(RESPONSES_CAPABILITY_COMPACT) is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_COMPACT,
                    field="model",
                    error_code="responses_compact_capability_not_supported",
                    safe_message="This model route does not support Responses compaction.",
                )
            )

    if conversations_requested:
        if capabilities.get(RESPONSES_CAPABILITY_CONVERSATIONS) is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_CONVERSATIONS,
                    field="conversation",
                    error_code="responses_conversation_capability_not_supported",
                    safe_message="This model route does not support Responses conversations.",
                )
            )

    if stored_responses_requested:
        if capabilities.get(RESPONSES_CAPABILITY_STORED_RESPONSES) is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_STORED_RESPONSES,
                    field="store",
                    error_code="responses_stored_response_capability_not_supported",
                    safe_message="This model route does not support stored Responses.",
                )
            )
    elif (
        not previous_response_id_requested
        and not list_input_items_requested
        and not compact_requested
        and not conversations_requested
        and capabilities.get(RESPONSES_CAPABILITY_STATELESS) is not True
    ):
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_STATELESS,
                field="model",
                error_code="responses_route_capability_not_supported",
                safe_message="This model route does not support stateless Responses.",
            )
        )

    if streaming_requested:
        if capabilities.get(RESPONSES_CAPABILITY_STREAMING) is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_STREAMING,
                    field="stream",
                    error_code="responses_route_capability_not_supported",
                    safe_message="This model route does not support streaming Responses.",
                )
            )
        if route_supports_streaming is not True:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=RESPONSES_CAPABILITY_STREAMING,
                    field="stream",
                    error_code="responses_route_capability_not_supported",
                    safe_message="This provider route does not support streaming Responses.",
                )
            )
    if json_mode_requested and capabilities.get(RESPONSES_CAPABILITY_JSON_MODE) is not True:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_JSON_MODE,
                field="text.format",
                error_code="responses_json_mode_not_supported",
                safe_message="This model route does not support Responses JSON mode.",
            )
        )
    if (
        structured_output_requested
        and capabilities.get(RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS) is not True
    ):
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS,
                field="text.format",
                error_code="responses_structured_output_not_supported",
                safe_message="This model route does not support Responses structured output.",
            )
        )
    if function_tools_requested and capabilities.get(RESPONSES_CAPABILITY_FUNCTION_TOOLS) is not True:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_FUNCTION_TOOLS,
                field="tools",
                error_code="responses_function_tool_capability_not_supported",
                safe_message="This model route does not support Responses function tools.",
            )
        )
    if custom_tools_requested and capabilities.get(RESPONSES_CAPABILITY_CUSTOM_TOOLS) is not True:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_CUSTOM_TOOLS,
                field="tools",
                error_code="responses_custom_tool_capability_not_supported",
                safe_message="This model route does not support Responses custom tools.",
            )
        )
    if image_input_requested and capabilities.get(RESPONSES_CAPABILITY_IMAGE_INPUT) is not True:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_IMAGE_INPUT,
                field="input",
                error_code="responses_image_input_capability_not_supported",
                safe_message="This model route does not support Responses image input.",
            )
        )
    if file_input_requested and capabilities.get(RESPONSES_CAPABILITY_FILE_INPUT) is not True:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_FILE_INPUT,
                field="input",
                error_code="responses_file_input_capability_not_supported",
                safe_message="This model route does not support Responses file input.",
            )
        )
    if (
        input_token_count_requested
        and capabilities.get(RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT) is not True
    ):
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT,
                field="model",
                error_code="responses_input_token_count_capability_not_supported",
                safe_message="This model route does not support Responses input-token counting.",
            )
        )


def _parse_route_capabilities(route_capabilities: Mapping[str, object] | None) -> dict[str, bool]:
    if not route_capabilities or RESPONSES_CAPABILITIES_KEY not in route_capabilities:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITIES_KEY,
                field="model",
                error_code="responses_route_capability_missing",
                safe_message="Responses route capability metadata is missing.",
            )
        )

    raw = route_capabilities.get(RESPONSES_CAPABILITIES_KEY)
    if not isinstance(raw, Mapping):
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITIES_KEY,
                field="model",
                error_code="responses_route_capability_invalid",
                safe_message="Responses route capability metadata is invalid.",
            )
        )

    parsed: dict[str, bool] = {}
    for key, value in raw.items():
        capability = str(key)
        if capability not in KNOWN_RESPONSES_CAPABILITIES:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=capability,
                    field="model",
                    error_code="responses_route_capability_invalid",
                    safe_message="Responses route capability metadata contains an unknown flag.",
                )
            )
        if not isinstance(value, bool):
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=capability,
                    field="model",
                    error_code="responses_route_capability_invalid",
                    safe_message="Responses route capability metadata must use boolean flags.",
                )
            )
        parsed[capability] = value
    return parsed
