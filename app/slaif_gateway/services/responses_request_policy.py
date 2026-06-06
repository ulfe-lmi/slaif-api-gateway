"""Request policy for the stateless text-only /v1/responses foundation."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any, NoReturn

from slaif_gateway.config import Settings
from slaif_gateway.schemas.policy import ResponsesPolicyResult
from slaif_gateway.services.input_token_estimation import canonical_json_bytes
from slaif_gateway.services.policy_errors import RequestPolicyError

_SUPPORTED_FIELDS = frozenset(
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
    }
)
TEXT_FORMAT_TEXT = "text"
TEXT_FORMAT_JSON_OBJECT = "json_object"
TEXT_FORMAT_JSON_SCHEMA = "json_schema"
STRUCTURED_TEXT_FORMAT_TYPES = frozenset({TEXT_FORMAT_JSON_OBJECT, TEXT_FORMAT_JSON_SCHEMA})
_TEXT_FORMAT_TYPES = frozenset(
    {
        TEXT_FORMAT_TEXT,
        TEXT_FORMAT_JSON_OBJECT,
        TEXT_FORMAT_JSON_SCHEMA,
    }
)
_TEXT_FORMAT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_SUPPORTED_INPUT_MESSAGE_ROLES = frozenset({"user", "assistant", "system", "developer"})
_SUPPORTED_INPUT_MESSAGE_FIELDS = frozenset({"type", "role", "content"})
_SUPPORTED_INPUT_TEXT_PART_FIELDS = frozenset({"type", "text"})
_SUPPORTED_FUNCTION_CALL_OUTPUT_FIELDS = frozenset({"type", "call_id", "output"})
_SUPPORTED_FUNCTION_TOOL_FIELDS = frozenset(
    {"type", "name", "description", "parameters", "strict"}
)
_SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS = frozenset({"type", "name"})
_FUNCTION_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MULTIMODAL_INPUT_ITEM_TYPES = frozenset(
    {
        "input_image",
        "input_file",
        "input_audio",
        "image",
        "file",
        "audio",
    }
)
_TOOL_INPUT_ITEM_TYPES = frozenset(
    {
        "function_call",
        "custom_tool_call",
        "custom_tool_call_output",
        "web_search_call",
        "file_search_call",
        "code_interpreter_call",
        "computer_call",
        "computer_call_output",
        "mcp_call",
        "mcp_approval_request",
        "mcp_approval_response",
        "tool_search_call",
        "shell_call",
        "local_shell_call",
    }
)
_HOSTED_TOOL_TYPES = frozenset(
    {
        "web_search",
        "web_search_preview",
        "web_search_preview_2025_03_11",
        "web_search_2025_08_26",
        "file_search",
        "code_interpreter",
        "computer",
        "computer_use",
        "computer_use_preview",
        "image_generation",
        "tool_search",
        "mcp",
        "shell",
        "local_shell",
        "apply_patch",
        "namespace",
        "custom",
    }
)


class ResponsesRequestPolicyError(RequestPolicyError):
    """Request-policy error for Responses field validation."""

    def __init__(self, safe_message: str, *, param: str, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(safe_message, param=param)


class ResponsesRequestPolicy:
    """Apply narrow Responses guardrails before route/rate/quota/provider work."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(self, body: Mapping[str, Any]) -> ResponsesPolicyResult:
        effective_body = copy.deepcopy(dict(body))
        self._reject_unknown_fields(effective_body)

        model = effective_body.get("model")
        if not isinstance(model, str) or not model.strip():
            _raise(
                "model",
                "responses_field_invalid_type",
                "The 'model' field must be a non-empty string.",
            )

        canonical_input, input_text_bytes = self._validate_input(effective_body.get("input"))
        effective_body["input"] = canonical_input
        instructions = self._validate_optional_string(
            effective_body.get("instructions"),
            param="instructions",
            max_bytes=self._settings.RESPONSES_MAX_INSTRUCTIONS_BYTES,
        )
        self._validate_stateless_fields(effective_body)
        self._validate_scalar_controls(effective_body)
        self._validate_metadata(effective_body.get("metadata"))
        self._validate_text_config(effective_body.get("text"), stream=effective_body.get("stream"))
        tools_schema_bytes = self._validate_tools(effective_body)
        tool_choice_bytes = self._validate_tool_choice(effective_body)
        function_tools_requested = responses_function_tools_requested(effective_body)
        if effective_body.get("stream") is True and function_tools_requested:
            _raise(
                "tools",
                "responses_function_tool_streaming_not_supported",
                "Streaming Responses function tools are not enabled by this gateway.",
            )
        output_tokens, injected_default = self._resolve_output_token_limit(effective_body)

        estimated_input_tokens = self._estimate_input_tokens(
            input_text_bytes=input_text_bytes,
            instructions=instructions,
            body=effective_body,
            tools_schema_bytes=tools_schema_bytes,
            tool_choice_bytes=tool_choice_bytes,
        )
        if estimated_input_tokens > self._settings.HARD_MAX_INPUT_TOKENS:
            _raise(
                "input",
                "input_token_limit_exceeded",
                "Estimated Responses input size exceeds the configured hard maximum.",
            )

        return ResponsesPolicyResult(
            effective_body=effective_body,
            requested_output_tokens=output_tokens,
            effective_output_tokens=output_tokens,
            estimated_input_tokens=estimated_input_tokens,
            estimated_message_input_tokens=estimated_input_tokens,
            estimated_non_message_input_tokens=0,
            estimated_non_message_input_bytes=0,
            estimated_non_message_input_fields=(),
            injected_default_output_tokens=injected_default,
        )

    def _reject_unknown_fields(self, body: Mapping[str, Any]) -> None:
        for field in body:
            field_name = str(field)
            if field_name not in _SUPPORTED_FIELDS:
                code = _unsupported_code_for_field(field_name)
                _raise(
                    field_name,
                    code,
                    "This Responses request field is not enabled by this gateway.",
                )

    def _validate_input(self, value: Any) -> tuple[str | list[dict[str, Any]], int]:
        if isinstance(value, str):
            if not value:
                _raise(
                    "input",
                    "responses_field_invalid_type",
                    "The 'input' field must be a non-empty text string or text input item array.",
                )
            self._validate_string_bytes(
                value,
                param="input",
                max_bytes=self._settings.RESPONSES_MAX_INPUT_TEXT_BYTES,
            )
            return value, len(value.encode("utf-8"))

        if isinstance(value, list):
            return self._validate_input_item_array(value)

        _raise(
            "input",
            "responses_field_invalid_type",
            "The 'input' field must be a non-empty text string or text input item array.",
        )

    def _validate_input_item_array(self, value: list[Any]) -> tuple[list[dict[str, Any]], int]:
        if not value:
            _raise(
                "input",
                "responses_input_invalid",
                "The Responses input item array must contain at least one item.",
            )
        if len(value) > self._settings.RESPONSES_MAX_INPUT_ITEMS:
            _raise(
                "input",
                "responses_input_item_count_exceeded",
                "The Responses input item array has too many items.",
            )

        canonical_items: list[dict[str, Any]] = []
        total_text_bytes = 0
        for index, item in enumerate(value):
            canonical_item, item_text_bytes = self._validate_input_item(item, index=index)
            total_text_bytes += item_text_bytes
            if total_text_bytes > self._settings.RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES:
                _raise(
                    "input",
                    "responses_input_item_too_large",
                    "The Responses input item text exceeds the gateway size limit.",
                )
            canonical_items.append(canonical_item)
        return canonical_items, total_text_bytes

    def _validate_input_item(self, item: Any, *, index: int) -> tuple[dict[str, Any], int]:
        param = f"input[{index}]"
        if not isinstance(item, Mapping):
            _raise(
                param,
                "responses_input_item_invalid",
                "Each Responses input item must be an object.",
            )

        item_type = item.get("type")
        if item_type == "function_call_output":
            return self._validate_function_call_output_item(item, param=param)
        if item_type is not None and item_type != "message":
            if item_type in _MULTIMODAL_INPUT_ITEM_TYPES:
                code = "responses_input_multimodal_not_supported"
            elif item_type in _TOOL_INPUT_ITEM_TYPES:
                code = "responses_input_tool_item_not_supported"
            else:
                code = "responses_input_item_type_not_supported"
            _raise(
                f"{param}.type",
                code,
                "This Responses input item type is not enabled by this gateway.",
            )

        unknown = set(item) - _SUPPORTED_INPUT_MESSAGE_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_input_item_invalid",
                "This Responses input item field is not enabled by this gateway.",
            )

        role = item.get("role")
        if role not in _SUPPORTED_INPUT_MESSAGE_ROLES:
            _raise(
                f"{param}.role",
                "responses_input_item_role_not_supported",
                "This Responses input message role is not enabled by this gateway.",
            )

        if "content" not in item:
            _raise(
                f"{param}.content",
                "responses_input_item_invalid",
                "Responses input message items require text content.",
            )

        canonical_content, text_bytes = self._validate_input_item_content(
            item["content"],
            param=f"{param}.content",
        )
        canonical_item: dict[str, Any] = {"role": role, "content": canonical_content}
        if item_type == "message":
            canonical_item["type"] = "message"
        return canonical_item, text_bytes

    def _validate_function_call_output_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
    ) -> tuple[dict[str, Any], int]:
        unknown = set(item) - _SUPPORTED_FUNCTION_CALL_OUTPUT_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_function_call_output_invalid",
                "This Responses function call output field is not enabled by this gateway.",
            )
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            _raise(
                f"{param}.call_id",
                "responses_function_call_output_invalid",
                "Responses function call output items require a non-empty call_id.",
            )
        self._validate_string_bytes(
            call_id,
            param=f"{param}.call_id",
            max_bytes=self._settings.RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES,
            code="responses_function_call_output_invalid",
        )
        output = item.get("output")
        if not isinstance(output, str):
            _raise(
                f"{param}.output",
                "responses_function_call_output_invalid",
                "Responses function call output must be a string in this gateway.",
            )
        self._validate_string_bytes(
            output,
            param=f"{param}.output",
            max_bytes=self._settings.RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES,
            code="responses_function_call_output_too_large",
        )
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        }, len(output.encode("utf-8"))

    def _validate_input_item_content(self, content: Any, *, param: str) -> tuple[str | list[dict[str, str]], int]:
        if isinstance(content, str):
            if not content:
                _raise(
                    param,
                    "responses_input_invalid",
                    "Responses input message text content must be non-empty.",
                )
            text_bytes = len(content.encode("utf-8"))
            self._validate_input_item_text_bytes(text_bytes, param=param)
            return content, text_bytes

        if isinstance(content, list):
            if not content:
                _raise(
                    param,
                    "responses_input_invalid",
                    "Responses input message content arrays must contain at least one text part.",
                )
            if len(content) > self._settings.RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM:
                _raise(
                    param,
                    "responses_input_item_count_exceeded",
                    "Responses input message content has too many text parts.",
                )
            canonical_parts: list[dict[str, str]] = []
            total_bytes = 0
            for part_index, part in enumerate(content):
                canonical_part, part_bytes = self._validate_input_text_part(
                    part,
                    param=f"{param}[{part_index}]",
                )
                total_bytes += part_bytes
                canonical_parts.append(canonical_part)
            self._validate_input_item_text_bytes(total_bytes, param=param)
            return canonical_parts, total_bytes

        _raise(
            param,
            "responses_input_invalid",
            "Responses input message content must be text or a text content-part array.",
        )

    def _validate_input_text_part(self, part: Any, *, param: str) -> tuple[dict[str, str], int]:
        if not isinstance(part, Mapping):
            _raise(
                param,
                "responses_input_content_part_not_supported",
                "Responses input content parts must be text objects.",
            )

        part_type = part.get("type")
        if part_type != "input_text":
            code = (
                "responses_input_multimodal_not_supported"
                if part_type in {"input_image", "input_file", "input_audio", "image", "file", "audio"}
                else "responses_input_content_part_not_supported"
            )
            _raise(
                f"{param}.type",
                code,
                "This Responses input content part type is not enabled by this gateway.",
            )

        unknown = set(part) - _SUPPORTED_INPUT_TEXT_PART_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_input_content_part_not_supported",
                "This Responses input content part field is not enabled by this gateway.",
            )

        text = part.get("text")
        if not isinstance(text, str) or not text:
            _raise(
                f"{param}.text",
                "responses_input_invalid",
                "Responses input text parts require non-empty text.",
            )
        text_bytes = len(text.encode("utf-8"))
        self._validate_input_item_text_bytes(text_bytes, param=f"{param}.text")
        return {"type": "input_text", "text": text}, text_bytes

    def _validate_input_item_text_bytes(self, text_bytes: int, *, param: str) -> None:
        if text_bytes > self._settings.RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES:
            _raise(
                param,
                "responses_input_item_too_large",
                "The Responses input item text exceeds the gateway size limit.",
            )

    def _validate_optional_string(self, value: Any, *, param: str, max_bytes: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            _raise(
                param,
                "responses_field_invalid_type",
                f"The '{param}' field must be a string.",
            )
        self._validate_string_bytes(value, param=param, max_bytes=max_bytes)
        return value

    def _validate_stateless_fields(self, body: dict[str, Any]) -> None:
        if "stream" in body and (
            body.get("stream") is not None and not isinstance(body.get("stream"), bool)
        ):
            _raise(
                "stream",
                "responses_field_invalid_type",
                "The 'stream' field must be a boolean when provided.",
            )
        if body.get("store") is True:
            _raise(
                "store",
                "responses_store_not_supported",
                "Provider-side Responses storage is not enabled by this gateway.",
            )
        if "store" in body and body.get("store") is not False and body.get("store") is not None:
            _raise(
                "store",
                "responses_field_invalid_type",
                "The 'store' field must be false when provided.",
            )
        body["store"] = False

        service_tier = body.get("service_tier")
        if service_tier not in (None, "auto"):
            _raise(
                "service_tier",
                "responses_service_tier_not_supported",
                "Non-default Responses service tiers are not enabled by this gateway.",
            )

    def _validate_scalar_controls(self, body: Mapping[str, Any]) -> None:
        self._validate_number_range(body.get("temperature"), param="temperature", minimum=0, maximum=2)
        self._validate_number_range(body.get("top_p"), param="top_p", minimum=0, maximum=1)

    def _validate_number_range(
        self,
        value: Any,
        *,
        param: str,
        minimum: float,
        maximum: float,
    ) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int | float):
            _raise(
                param,
                "responses_field_invalid_type",
                f"The '{param}' field must be a number.",
            )
        if value < minimum or value > maximum:
            _raise(
                param,
                "responses_field_value_out_of_range",
                f"The '{param}' field is outside the supported range.",
            )

    def _validate_metadata(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, Mapping):
            _raise(
                "metadata",
                "responses_field_invalid_type",
                "The 'metadata' field must be an object.",
            )
        if len(value) > self._settings.RESPONSES_MAX_METADATA_KEYS:
            _raise(
                "metadata",
                "responses_field_too_many_items",
                "The 'metadata' field has too many keys.",
            )
        for key in value:
            if not isinstance(key, str):
                _raise(
                    "metadata",
                    "responses_field_invalid_type",
                    "Responses metadata keys must be strings.",
                )
        if len(canonical_json_bytes(value)) > self._settings.RESPONSES_MAX_METADATA_BYTES:
            _raise(
                "metadata",
                "responses_field_too_large",
                "The 'metadata' field exceeds the gateway size limit.",
            )

    def _validate_text_config(self, value: Any, *, stream: Any) -> None:
        if value is None:
            return
        if not isinstance(value, Mapping):
            _raise(
                "text",
                "responses_field_invalid_type",
                "The 'text' field must be an object.",
            )
        unknown = set(value) - {"format"}
        if unknown:
            _raise(
                f"text.{sorted(unknown)[0]}",
                "responses_field_not_supported",
                "This Responses text configuration field is not enabled by this gateway.",
            )
        text_format = value.get("format")
        if text_format is None:
            return
        if not isinstance(text_format, Mapping):
            _raise(
                "text.format",
                "responses_field_invalid_type",
                "The 'text.format' field must be an object.",
            )
        format_type = text_format.get("type")
        if format_type not in _TEXT_FORMAT_TYPES:
            _raise(
                "text.format",
                "responses_text_format_not_supported",
                "This Responses text format type is not enabled by this gateway.",
            )
        if format_type in STRUCTURED_TEXT_FORMAT_TYPES and stream is True:
            _raise(
                "text.format",
                "responses_structured_streaming_not_supported",
                "Structured Responses streaming is not enabled by this gateway.",
            )
        if format_type == TEXT_FORMAT_TEXT:
            self._validate_text_format_text(text_format)
            return
        if format_type == TEXT_FORMAT_JSON_OBJECT:
            self._validate_text_format_json_object(text_format)
            return
        self._validate_text_format_json_schema(text_format)

    def _validate_text_format_text(self, text_format: Mapping[str, Any]) -> None:
        unknown_format = set(text_format) - {"type"}
        if unknown_format:
            _raise(
                f"text.format.{sorted(unknown_format)[0]}",
                "responses_field_not_supported",
                "This Responses text format field is not enabled by this gateway.",
            )
        self._validate_text_format_size(text_format)

    def _validate_text_format_json_object(self, text_format: Mapping[str, Any]) -> None:
        unknown_format = set(text_format) - {"type"}
        if unknown_format:
            _raise(
                f"text.format.{sorted(unknown_format)[0]}",
                "responses_field_not_supported",
                "This Responses JSON object format field is not enabled by this gateway.",
            )
        self._validate_text_format_size(text_format)

    def _validate_text_format_json_schema(self, text_format: Mapping[str, Any]) -> None:
        unknown_format = set(text_format) - {"type", "name", "schema", "description", "strict"}
        if unknown_format:
            _raise(
                f"text.format.{sorted(unknown_format)[0]}",
                "responses_field_not_supported",
                "This Responses JSON schema format field is not enabled by this gateway.",
            )

        name = text_format.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                "text.format.name",
                "responses_text_format_invalid",
                "Responses JSON schema text format requires a non-empty name.",
            )
        if not _TEXT_FORMAT_NAME_PATTERN.fullmatch(name):
            _raise(
                "text.format.name",
                "responses_text_format_invalid",
                "Responses JSON schema text format name uses unsupported characters.",
            )
        self._validate_string_bytes(
            name,
            param="text.format.name",
            max_bytes=self._settings.RESPONSES_MAX_TEXT_FORMAT_NAME_BYTES,
            code="responses_text_format_too_large",
        )

        schema = text_format.get("schema")
        if not isinstance(schema, Mapping):
            _raise(
                "text.format.schema",
                "responses_json_schema_invalid",
                "Responses JSON schema text format requires a schema object.",
            )
        self._validate_json_bytes(
            schema,
            param="text.format.schema",
            max_bytes=self._settings.RESPONSES_MAX_JSON_SCHEMA_BYTES,
            too_large_code="responses_json_schema_too_large",
            invalid_code="responses_json_schema_invalid",
            field_label="Responses JSON schema",
        )

        description = text_format.get("description")
        if description is not None:
            if not isinstance(description, str):
                _raise(
                    "text.format.description",
                    "responses_field_invalid_type",
                    "Responses JSON schema text format description must be a string.",
                )
            self._validate_string_bytes(
                description,
                param="text.format.description",
                max_bytes=self._settings.RESPONSES_MAX_TEXT_FORMAT_DESCRIPTION_BYTES,
                code="responses_text_format_too_large",
            )

        strict = text_format.get("strict")
        if strict is not None and not isinstance(strict, bool):
            _raise(
                "text.format.strict",
                "responses_field_invalid_type",
                "Responses JSON schema text format strict flag must be a boolean.",
            )
        self._validate_text_format_size(text_format)

    def _validate_text_format_size(self, text_format: Mapping[str, Any]) -> None:
        self._validate_json_bytes(
            text_format,
            param="text.format",
            max_bytes=self._settings.RESPONSES_MAX_TEXT_FORMAT_BYTES,
            too_large_code="responses_text_format_too_large",
            invalid_code="responses_text_format_invalid",
            field_label="Responses text format",
        )

    def _validate_tools(self, body: dict[str, Any]) -> int:
        value = body.get("tools")
        if value is None:
            return 0
        if not isinstance(value, list):
            _raise(
                "tools",
                "responses_tool_invalid_shape",
                "The 'tools' field must be a list of Responses function tools.",
            )
        if not value:
            _raise(
                "tools",
                "responses_tool_invalid_shape",
                "The 'tools' field must contain at least one function tool when provided.",
            )
        if len(value) > self._settings.RESPONSES_MAX_TOOLS_PER_REQUEST:
            _raise(
                "tools",
                "responses_tool_count_exceeded",
                "The Responses tools array has too many entries.",
            )
        if len(value) > self._settings.RESPONSES_MAX_FUNCTION_TOOLS_PER_REQUEST:
            _raise(
                "tools",
                "responses_tool_count_exceeded",
                "The Responses function tools array has too many entries.",
            )

        canonical_tools: list[dict[str, Any]] = []
        total_schema_bytes = 0
        seen_names: set[str] = set()
        for index, tool in enumerate(value):
            canonical_tool, schema_bytes = self._validate_function_tool(
                tool,
                param=f"tools[{index}]",
            )
            name = canonical_tool["name"]
            if name in seen_names:
                _raise(
                    f"tools[{index}].name",
                    "responses_tool_invalid_shape",
                    "Responses function tool names must be unique.",
                )
            seen_names.add(name)
            total_schema_bytes += schema_bytes
            if total_schema_bytes > self._settings.RESPONSES_MAX_TOTAL_FUNCTION_TOOL_SCHEMA_BYTES:
                _raise(
                    "tools",
                    "responses_function_tool_schema_too_large",
                    "The total Responses function tool schema size exceeds the gateway limit.",
                )
            canonical_tools.append(canonical_tool)

        body["tools"] = canonical_tools
        return len(canonical_json_bytes({"tools": canonical_tools}))

    def _validate_function_tool(
        self,
        tool: Any,
        *,
        param: str,
    ) -> tuple[dict[str, Any], int]:
        if not isinstance(tool, Mapping):
            _raise(
                param,
                "responses_tool_invalid_shape",
                "Responses tools must be function tool objects.",
            )
        tool_type = tool.get("type")
        if tool_type != "function":
            code = (
                "responses_hosted_tool_not_supported"
                if tool_type in _HOSTED_TOOL_TYPES
                else "responses_tool_type_not_supported"
            )
            if tool_type == "mcp" or _contains_provider_authority_marker(tool):
                code = "responses_mcp_not_supported"
            _raise(
                f"{param}.type",
                code,
                "Only local Responses function tools are enabled by this gateway.",
            )
        if _contains_provider_authority_marker(tool):
            _raise(
                param,
                "responses_mcp_not_supported",
                "Provider-side tool authority markers are not enabled by this gateway.",
            )
        unknown = set(tool) - _SUPPORTED_FUNCTION_TOOL_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_tool_invalid_shape",
                "This Responses function tool field is not enabled by this gateway.",
            )

        name = tool.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                f"{param}.name",
                "responses_tool_invalid_shape",
                "Responses function tools require a non-empty name.",
            )
        if not _FUNCTION_TOOL_NAME_PATTERN.fullmatch(name):
            _raise(
                f"{param}.name",
                "responses_tool_invalid_shape",
                "Responses function tool names use unsupported characters.",
            )
        self._validate_string_bytes(
            name,
            param=f"{param}.name",
            max_bytes=self._settings.RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES,
            code="responses_tool_invalid_shape",
        )

        parameters = tool.get("parameters")
        if not isinstance(parameters, Mapping):
            _raise(
                f"{param}.parameters",
                "responses_tool_invalid_shape",
                "Responses function tools require a parameters schema object.",
            )
        schema_bytes = self._validate_json_bytes(
            parameters,
            param=f"{param}.parameters",
            max_bytes=self._settings.RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES,
            too_large_code="responses_function_tool_schema_too_large",
            invalid_code="responses_tool_invalid_shape",
            field_label="Responses function tool schema",
            return_size=True,
        )

        canonical_tool: dict[str, Any] = {
            "type": "function",
            "name": name,
            "parameters": copy.deepcopy(dict(parameters)),
        }

        description = tool.get("description")
        if description is not None:
            if not isinstance(description, str):
                _raise(
                    f"{param}.description",
                    "responses_tool_invalid_shape",
                    "Responses function tool descriptions must be strings.",
                )
            self._validate_string_bytes(
                description,
                param=f"{param}.description",
                max_bytes=self._settings.RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES,
                code="responses_tool_invalid_shape",
            )
            canonical_tool["description"] = description

        strict = tool.get("strict")
        if strict is not None:
            if not isinstance(strict, bool):
                _raise(
                    f"{param}.strict",
                    "responses_tool_invalid_shape",
                    "Responses function tool strict flags must be booleans.",
                )
            canonical_tool["strict"] = strict
        return canonical_tool, schema_bytes

    def _validate_tool_choice(self, body: dict[str, Any]) -> int:
        if "tool_choice" not in body:
            return 0
        value = body.get("tool_choice")
        tools = body.get("tools")
        if tools is None:
            _raise(
                "tool_choice",
                "responses_tool_choice_invalid",
                "Responses tool_choice requires function tools in this gateway.",
            )
        if isinstance(value, str):
            if value not in {"none", "auto", "required"}:
                _raise(
                    "tool_choice",
                    "responses_tool_choice_invalid",
                    "Responses tool_choice must be none, auto, required, or a function choice.",
                )
            return len(canonical_json_bytes({"tool_choice": value}))
        if not isinstance(value, Mapping):
            _raise(
                "tool_choice",
                "responses_tool_choice_invalid",
                "Responses tool_choice must be none, auto, required, or a function choice.",
            )
        if _contains_provider_authority_marker(value):
            _raise(
                "tool_choice",
                "responses_mcp_not_supported",
                "Provider-side tool choices are not enabled by this gateway.",
            )
        if value.get("type") != "function":
            code = (
                "responses_hosted_tool_not_supported"
                if value.get("type") in _HOSTED_TOOL_TYPES
                else "responses_tool_choice_invalid"
            )
            if value.get("type") == "mcp":
                code = "responses_mcp_not_supported"
            _raise(
                "tool_choice.type",
                code,
                "Only local Responses function tool choices are enabled by this gateway.",
            )
        unknown = set(value) - _SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS
        if unknown:
            _raise(
                f"tool_choice.{sorted(unknown)[0]}",
                "responses_tool_choice_invalid",
                "This Responses tool choice field is not enabled by this gateway.",
            )
        name = value.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                "tool_choice.name",
                "responses_tool_choice_invalid",
                "Responses function tool choices require a non-empty tool name.",
            )
        declared_names = {tool["name"] for tool in tools if isinstance(tool, Mapping)}
        if name not in declared_names:
            _raise(
                "tool_choice.name",
                "responses_tool_choice_invalid",
                "Responses function tool_choice must reference a declared function tool.",
            )
        canonical_choice = {"type": "function", "name": name}
        body["tool_choice"] = canonical_choice
        return len(canonical_json_bytes({"tool_choice": canonical_choice}))

    def _validate_json_bytes(
        self,
        value: Any,
        *,
        param: str,
        max_bytes: int,
        too_large_code: str,
        invalid_code: str,
        field_label: str,
        return_size: bool = False,
    ) -> int | None:
        try:
            field_bytes = canonical_json_bytes(value)
        except ValueError:
            _raise(
                param,
                invalid_code,
                f"{field_label} must be JSON-compatible.",
            )
        if len(field_bytes) > max_bytes:
            _raise(
                param,
                too_large_code,
                f"{field_label} exceeds the gateway size limit.",
            )
        if return_size:
            return len(field_bytes)
        return None

    def _resolve_output_token_limit(self, body: dict[str, Any]) -> tuple[int, bool]:
        value = body.get("max_output_tokens")
        if value is None:
            body["max_output_tokens"] = self._settings.DEFAULT_MAX_OUTPUT_TOKENS
            return self._settings.DEFAULT_MAX_OUTPUT_TOKENS, True
        if isinstance(value, bool) or not isinstance(value, int):
            _raise(
                "max_output_tokens",
                "invalid_output_token_limit",
                "The 'max_output_tokens' field must be a positive integer.",
            )
        if value <= 0:
            _raise(
                "max_output_tokens",
                "invalid_output_token_limit",
                "The 'max_output_tokens' field must be a positive integer.",
            )
        if value > self._settings.HARD_MAX_OUTPUT_TOKENS:
            _raise(
                "max_output_tokens",
                "output_token_limit_exceeded",
                "The 'max_output_tokens' field exceeds the configured hard maximum.",
            )
        return value, False

    def _estimate_input_tokens(
        self,
        *,
        input_text_bytes: int,
        instructions: str | None,
        body: Mapping[str, Any],
        tools_schema_bytes: int = 0,
        tool_choice_bytes: int = 0,
    ) -> int:
        total_bytes = input_text_bytes
        if instructions is not None:
            total_bytes += len(instructions.encode("utf-8"))
        total_bytes += tools_schema_bytes + tool_choice_bytes
        for field in ("text",):
            if field in body and body[field] is not None:
                total_bytes += len(canonical_json_bytes({field: body[field]}))
        return max(1, (total_bytes + 2) // 3)

    def _validate_string_bytes(
        self,
        value: str,
        *,
        param: str,
        max_bytes: int,
        code: str = "responses_field_too_large",
    ) -> None:
        if len(value.encode("utf-8")) > max_bytes:
            _raise(
                param,
                code,
                f"The '{param}' field exceeds the gateway size limit.",
            )


def responses_text_format_type(body: Mapping[str, Any]) -> str | None:
    text = body.get("text")
    if not isinstance(text, Mapping):
        return None
    text_format = text.get("format")
    if not isinstance(text_format, Mapping):
        return None
    format_type = text_format.get("type")
    return format_type if isinstance(format_type, str) else None


def responses_function_tools_requested(body: Mapping[str, Any]) -> bool:
    if body.get("tools") is not None or "tool_choice" in body:
        return True
    return _input_contains_function_call_output(body.get("input"))


def _input_contains_function_call_output(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, Mapping) and item.get("type") == "function_call_output":
            return True
    return False


def _contains_provider_authority_marker(value: Mapping[str, Any]) -> bool:
    forbidden = {
        "server_url",
        "connector_id",
        "authorization",
        "require_approval",
        "approval_request",
        "headers",
        "secrets",
    }
    return any(field in value for field in forbidden)


def _unsupported_code_for_field(field_name: str) -> str:
    if field_name == "parallel_tool_calls":
        return "responses_tools_not_supported"
    if field_name in {"previous_response_id", "conversation"}:
        return "responses_state_not_supported"
    if field_name == "background":
        return "responses_background_not_supported"
    if field_name in {"modalities", "audio", "include"}:
        return "responses_multimodal_not_supported"
    if field_name in {"prompt", "prompt_cache_key", "prompt_cache_retention"}:
        return "responses_state_not_supported"
    return "responses_field_not_supported"


def _raise(param: str, code: str, message: str) -> NoReturn:
    raise ResponsesRequestPolicyError(message, param=param, error_code=code)
