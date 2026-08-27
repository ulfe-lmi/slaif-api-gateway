"""Request policy for the stateless text-output /v1/responses foundation."""

from __future__ import annotations

import base64
import binascii
import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib.parse import urlsplit

from slaif_gateway.modules.clients.responses_support import (
    TEXT_FORMAT_TEXT,
    TEXT_FORMAT_JSON_OBJECT,
    TEXT_FORMAT_JSON_SCHEMA as _TEXT_FORMAT_JSON_SCHEMA,
    STRUCTURED_TEXT_FORMAT_TYPES,
    _TEXT_FORMAT_NAME_PATTERN,
    _TEXT_FORMAT_TYPES,
    _SUPPORTED_INPUT_MESSAGE_ROLES,
    _SUPPORTED_INPUT_MESSAGE_FIELDS,
    _SUPPORTED_INPUT_TEXT_PART_FIELDS,
    _SUPPORTED_COMPACT_MESSAGE_FIELDS,
    _SUPPORTED_COMPACT_TEXT_PART_FIELDS,
    _SUPPORTED_COMPACT_PART_TYPES,
    _SUPPORTED_COMPACT_MESSAGE_STATUSES,
    _SUPPORTED_INPUT_IMAGE_PART_FIELDS,
    _SUPPORTED_INPUT_FILE_PART_FIELDS,
    _SUPPORTED_FUNCTION_CALL_OUTPUT_FIELDS,
    _SUPPORTED_CUSTOM_TOOL_CALL_OUTPUT_FIELDS,
    _SUPPORTED_FUNCTION_TOOL_FIELDS,
    _SUPPORTED_CUSTOM_TOOL_FIELDS,
    _SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS,
    _SUPPORTED_CUSTOM_TOOL_CHOICE_FIELDS,
    _SUPPORTED_CUSTOM_TOOL_TEXT_FORMAT_FIELDS,
    _SUPPORTED_CUSTOM_TOOL_GRAMMAR_FORMAT_FIELDS,
    _SUPPORTED_CONVERSATION_ITEM_CREATE_FIELDS,
    _SUPPORTED_CONVERSATION_UPDATE_FIELDS,
    _CONVERSATION_UPDATE_MAX_METADATA_KEYS,
    _CONVERSATION_UPDATE_MAX_METADATA_KEY_CHARS,
    _CONVERSATION_UPDATE_MAX_METADATA_VALUE_CHARS,
    _FUNCTION_TOOL_NAME_PATTERN,
    _CUSTOM_TOOL_NAME_PATTERN,
    _MULTIMODAL_INPUT_ITEM_TYPES,
    _TOOL_INPUT_ITEM_TYPES,
    _HOSTED_TOOL_TYPES,
    _CUSTOM_TOOL_FORMAT_TYPES,
    _CUSTOM_TOOL_GRAMMAR_SYNTAXES,
    _IMAGE_DETAIL_VALUES,
    _IMAGE_DATA_URL_PREFIX,
    _IMAGE_DATA_URL_BASE64_SUFFIX,
    _FILE_DATA_URL_PREFIX,
    _FILE_DATA_URL_BASE64_SUFFIX,
    _BASE64_CHARS_RE,
)
from slaif_gateway.modules.contracts import ResponsesClientPolicySpec
from slaif_gateway.config import Settings
from slaif_gateway.schemas.policy import ResponsesPolicyResult
from slaif_gateway.services.input_token_estimation import canonical_json_bytes
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_route_capabilities import (
    KNOWN_RESPONSES_CAPABILITIES,
    RESPONSES_CAPABILITY_CODEX_CLIENT_TOOLS,
    RESPONSES_CAPABILITY_CODEX_COMPACTION,
    RESPONSES_CAPABILITY_CODEX_ENCRYPTED_REASONING_REPLAY,
    RESPONSES_CAPABILITY_CODEX_REQUEST_ENVELOPE,
    RESPONSES_CAPABILITY_CODEX_STREAMING_TOOL_EVENTS,
    parse_codex_route_limits,
)

_SUPPORTED_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "max_output_tokens",
        "max_tool_calls",
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
        "client_metadata",
        "include",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
    }
)
_SUPPORTED_INPUT_TOKEN_COUNT_FIELDS = frozenset(
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
_SUPPORTED_COMPACT_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
    }
)

TEXT_FORMAT_JSON_SCHEMA = _TEXT_FORMAT_JSON_SCHEMA
_ADAPTER_MANAGED_TOOL_TOKEN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ADAPTER_MANAGED_UNSAFE_VALUE_MARKERS = (
    "bearer",
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "password",
    "token",
)


def _contains_unsafe_adapter_value(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_unsafe_adapter_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_unsafe_adapter_value(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "://" in value or any(
            marker in lowered for marker in _ADAPTER_MANAGED_UNSAFE_VALUE_MARKERS
        )
    return False


def codex_client_tool_taxonomy_id(policy: object) -> str | None:
    """Compatibility export for the pure client-taxonomy helper."""
    if isinstance(policy, Mapping) and isinstance(policy.get("codex_client_tool_taxonomy"), str):
        return policy["codex_client_tool_taxonomy"]
    return None


class ResponsesRequestPolicyError(RequestPolicyError):
    """Request-policy error for Responses field validation."""

    def __init__(self, safe_message: str, *, param: str, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(safe_message, param=param)


@dataclass(frozen=True, slots=True, repr=False)
class CodexReplayRequestCandidate:
    """Transient validated replay identifiers for the immediate HMAC lookup."""

    item_kind: str
    item_id: str
    call_id: str | None
    tool_namespace: str | None
    tool_name: str | None


@dataclass(frozen=True, slots=True, repr=False)
class CodexCompactionReplayCandidate:
    """Transient composite opaque values used only by the immediate HMAC step."""

    item_kind: str
    item_id: str
    call_id: str | None
    tool_namespace: str | None
    tool_name: str | None
    encrypted_content: str


class ResponsesRequestPolicy:
    """Apply narrow Responses guardrails before route/rate/quota/provider work."""

    def __init__(
        self,
        settings: Settings,
        *,
        client_spec: ResponsesClientPolicySpec | None = None,
    ) -> None:
        self._settings = settings
        self._codex_spec = client_spec

    def apply(
        self,
        body: Mapping[str, Any],
        *,
        allow_store: bool = False,
        allow_codex_request_envelope: bool = False,
        allow_codex_client_tools: bool = False,
        allow_codex_streaming_tool_events: bool = False,
        allow_codex_encrypted_reasoning_replay: bool = False,
        allow_codex_extended_limits: bool = False,
        allow_codex_compaction_replay: bool = False,
        codex_client_tool_taxonomy: str | None = None,
        allow_external_tool_request: bool = False,
        adapter_managed_declaration_candidates: frozenset[str] = frozenset(),
        adapter_managed_declaration_shapes: Mapping[str, frozenset[str]] | None = None,
    ) -> ResponsesPolicyResult:
        effective_body = copy.deepcopy(dict(body))
        codex_client_tools_requested = responses_codex_client_tools_requested(effective_body)
        if codex_client_tools_requested and not (
            allow_codex_request_envelope and allow_codex_client_tools
        ):
            _raise(
                _first_codex_client_tools_param(effective_body),
                "responses_codex_client_tools_not_allowed",
                "Codex client tool namespaces are not enabled for this gateway key.",
            )
        codex_streaming_tool_events_requested = responses_codex_streaming_tool_events_requested(
            effective_body
        )
        if codex_streaming_tool_events_requested and not (
            allow_codex_request_envelope
            and allow_codex_client_tools
            and allow_codex_streaming_tool_events
        ):
            _raise(
                "stream",
                "responses_codex_streaming_tool_events_not_allowed",
                "Codex streaming tool events are not enabled for this gateway key.",
            )
        codex_envelope_requested = responses_codex_request_envelope_requested(effective_body)
        if codex_envelope_requested and not allow_codex_request_envelope:
            _raise(
                _first_codex_envelope_param(effective_body),
                "responses_codex_envelope_not_allowed",
                "The Codex request envelope is not enabled for this gateway key.",
            )
        codex_encrypted_reasoning_replay_requested = (
            responses_codex_encrypted_reasoning_replay_requested(effective_body)
        )
        if codex_encrypted_reasoning_replay_requested and not (
            allow_codex_request_envelope and allow_codex_encrypted_reasoning_replay
        ):
            _raise(
                _first_codex_encrypted_reasoning_param(effective_body),
                "responses_codex_encrypted_reasoning_replay_not_allowed",
                "Codex encrypted reasoning replay is not enabled for this gateway key.",
            )
        self._reject_unknown_fields(effective_body)

        model = effective_body.get("model")
        if not isinstance(model, str) or not model.strip():
            _raise(
                "model",
                "responses_field_invalid_type",
                "The 'model' field must be a non-empty string.",
            )

        canonical_input, input_material_bytes = self._validate_input(
            effective_body.get("input"),
            allow_codex_request_envelope=allow_codex_request_envelope,
            allow_codex_client_tools=allow_codex_client_tools,
            allow_codex_streaming_tool_events=allow_codex_streaming_tool_events,
            allow_codex_encrypted_reasoning_replay=allow_codex_encrypted_reasoning_replay,
            allow_codex_compaction_replay=allow_codex_compaction_replay,
            codex_client_tool_taxonomy=codex_client_tool_taxonomy,
        )
        effective_body["input"] = canonical_input
        instructions = self._validate_optional_string(
            effective_body.get("instructions"),
            param="instructions",
            max_bytes=self._settings.RESPONSES_MAX_INSTRUCTIONS_BYTES,
        )
        self._validate_storage_fields(effective_body, allow_store=allow_store)
        self._validate_previous_response_id(effective_body)
        self._validate_conversation(effective_body)
        if "conversation" in effective_body and "previous_response_id" in effective_body:
            _raise(
                "conversation",
                "responses_conversation_previous_response_not_supported",
                "Responses conversation and previous_response_id cannot be combined in this gateway.",
            )
        if codex_replay_request_candidates(effective_body) and (
            "conversation" in effective_body or "previous_response_id" in effective_body
        ):
            _raise(
                "input",
                "responses_codex_replay_provider_state_not_supported",
                "Codex client-managed replay cannot be combined with provider-managed state.",
            )
        self._validate_scalar_controls(effective_body)
        self._validate_metadata(effective_body.get("metadata"))
        self._validate_text_config(
            effective_body.get("text"),
            stream=effective_body.get("stream"),
            allow_codex_request_envelope=allow_codex_request_envelope,
        )
        self._validate_codex_request_envelope(
            effective_body,
            allow_codex_request_envelope=allow_codex_request_envelope,
        )
        self._validate_codex_client_tool_controls(effective_body)
        tools_schema_bytes = self._validate_tools(
            effective_body,
            allow_external_tool_request=allow_external_tool_request,
            allow_codex_client_tools=allow_codex_client_tools,
            adapter_managed_declaration_candidates=adapter_managed_declaration_candidates,
            adapter_managed_declaration_shapes=adapter_managed_declaration_shapes,
        )
        if "max_tool_calls" in effective_body and not any(
            isinstance(tool, Mapping) and tool.get("type") == "web_search"
            for tool in effective_body.get("tools", [])
        ):
            _raise(
                "max_tool_calls",
                "responses_external_tool_invalid",
                "The hosted tool call limit requires an admitted web-search declaration.",
            )
        tool_choice_bytes = self._validate_tool_choice(effective_body)
        function_tools_requested = responses_function_tools_requested(effective_body)
        custom_tools_requested = responses_custom_tools_requested(effective_body)
        adapter_managed_streaming_allowed = (
            bool(adapter_managed_declaration_candidates)
            and allow_codex_request_envelope
            and allow_codex_client_tools
            and allow_codex_streaming_tool_events
        )
        if (
            effective_body.get("stream") is True
            and function_tools_requested
            and not (codex_streaming_tool_events_requested or adapter_managed_streaming_allowed)
        ):
            _raise(
                "tools",
                "responses_function_tool_streaming_not_supported",
                "Streaming Responses function tools are not enabled by this gateway.",
            )
        if (
            effective_body.get("stream") is True
            and custom_tools_requested
            and not (codex_streaming_tool_events_requested or adapter_managed_streaming_allowed)
        ):
            _raise(
                "tools",
                "responses_custom_tool_streaming_not_supported",
                "Streaming Responses custom tools are not enabled by this gateway.",
            )
        if effective_body.get("stream") is True and previous_response_id_requested(effective_body):
            _raise(
                "previous_response_id",
                "responses_previous_response_streaming_not_supported",
                "Streaming Responses with previous_response_id is not enabled by this gateway.",
            )
        if effective_body.get("stream") is True and conversation_requested(effective_body):
            _raise(
                "conversation",
                "responses_conversation_streaming_not_supported",
                "Streaming Responses with conversation is not enabled by this gateway.",
            )
        output_tokens, injected_default = self._resolve_output_token_limit(
            effective_body,
            hard_max=(
                self._settings.CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS
                if allow_codex_extended_limits
                else self._settings.HARD_MAX_OUTPUT_TOKENS
            ),
        )

        (
            estimated_input_tokens,
            estimated_non_message_input_tokens,
            estimated_non_message_input_bytes,
            estimated_non_message_input_fields,
        ) = self._estimate_input_tokens(
            input_material_bytes=input_material_bytes,
            instructions=instructions,
            body=effective_body,
            tools_schema_bytes=tools_schema_bytes,
            tool_choice_bytes=tool_choice_bytes,
            codex_client_tool_declaration_bytes=(
                _codex_client_tool_declaration_estimation_bytes(effective_body.get("input"))
            ),
        )
        input_ceiling = (
            self._settings.CODEX_ABSOLUTE_MAX_INPUT_TOKENS
            if allow_codex_extended_limits
            else self._settings.HARD_MAX_INPUT_TOKENS
        )
        if estimated_input_tokens > input_ceiling:
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
            estimated_message_input_tokens=max(
                0, estimated_input_tokens - estimated_non_message_input_tokens
            ),
            estimated_non_message_input_tokens=estimated_non_message_input_tokens,
            estimated_non_message_input_bytes=estimated_non_message_input_bytes,
            estimated_non_message_input_fields=estimated_non_message_input_fields,
            injected_default_output_tokens=injected_default,
        )

    def apply_input_token_count(self, body: Mapping[str, Any]) -> ResponsesPolicyResult:
        """Validate a Responses input-token count request without create-only fields."""

        effective_body = copy.deepcopy(dict(body))
        self._reject_unknown_fields(
            effective_body,
            allowed_fields=_SUPPORTED_INPUT_TOKEN_COUNT_FIELDS,
        )

        model = effective_body.get("model")
        if not isinstance(model, str) or not model.strip():
            _raise(
                "model",
                "responses_field_invalid_type",
                "The 'model' field must be a non-empty string.",
            )

        canonical_input, input_material_bytes = self._validate_input(effective_body.get("input"))
        effective_body["input"] = canonical_input
        instructions = self._validate_optional_string(
            effective_body.get("instructions"),
            param="instructions",
            max_bytes=self._settings.RESPONSES_MAX_INSTRUCTIONS_BYTES,
        )
        self._validate_text_config(effective_body.get("text"), stream=False)
        tools_schema_bytes = self._validate_tools(effective_body)
        tool_choice_bytes = self._validate_tool_choice(effective_body)
        self._validate_input_token_count_controls(effective_body)

        estimated_input_tokens, _, _, _ = self._estimate_input_tokens(
            input_material_bytes=input_material_bytes,
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
            requested_output_tokens=0,
            effective_output_tokens=0,
            estimated_input_tokens=estimated_input_tokens,
            estimated_message_input_tokens=estimated_input_tokens,
            estimated_non_message_input_tokens=0,
            estimated_non_message_input_bytes=0,
            estimated_non_message_input_fields=(),
            injected_default_output_tokens=False,
        )

    def apply_compact(
        self,
        body: Mapping[str, Any],
        *,
        allow_codex_compaction: bool = False,
    ) -> ResponsesPolicyResult:
        """Validate a bounded text-focused Responses compaction request."""

        effective_body = copy.deepcopy(dict(body))
        codex_requested = responses_codex_compaction_requested(effective_body)
        if codex_requested and not allow_codex_compaction:
            _raise(
                _first_codex_compaction_param(effective_body),
                "responses_codex_compaction_not_allowed",
                "Codex V1 compaction is not enabled for this gateway key.",
            )
        self._reject_unknown_fields(
            effective_body,
            allowed_fields=(
                self._codex_spec.compact_fields if codex_requested else _SUPPORTED_COMPACT_FIELDS
            ),
        )

        model = effective_body.get("model")
        if not isinstance(model, str) or not model.strip():
            _raise(
                "model",
                "responses_field_invalid_type",
                "The 'model' field must be a non-empty string.",
            )

        if "input" not in effective_body:
            _raise(
                "input",
                "responses_compact_input_required",
                "Responses compaction requires an explicit input field in this gateway.",
            )
        if codex_requested:
            canonical_input, input_material_bytes = self._validate_input(
                effective_body.get("input"),
                allow_codex_request_envelope=True,
                allow_codex_client_tools=True,
                allow_codex_streaming_tool_events=True,
                allow_codex_encrypted_reasoning_replay=True,
                allow_codex_compaction_replay=True,
            )
        else:
            canonical_input, input_material_bytes = self._validate_compact_input(
                effective_body.get("input")
            )
        effective_body["input"] = canonical_input
        instructions = self._validate_optional_string(
            effective_body.get("instructions"),
            param="instructions",
            max_bytes=self._settings.RESPONSES_MAX_INSTRUCTIONS_BYTES,
        )
        tools_schema_bytes = 0
        if codex_requested:
            self._validate_scalar_controls(effective_body)
            self._validate_text_config(
                effective_body.get("text"),
                stream=False,
                allow_codex_request_envelope=True,
            )
            self._validate_codex_request_envelope(
                effective_body,
                allow_codex_request_envelope=True,
            )
            self._validate_codex_client_tool_controls(effective_body)
            tools_schema_bytes = self._validate_tools(effective_body)
        (
            estimated_input_tokens,
            estimated_non_message_tokens,
            estimated_non_message_bytes,
            estimated_non_message_fields,
        ) = self._estimate_input_tokens(
            input_material_bytes=input_material_bytes,
            instructions=instructions,
            body=effective_body,
            tools_schema_bytes=tools_schema_bytes,
            codex_client_tool_declaration_bytes=(
                _codex_client_tool_declaration_estimation_bytes(effective_body.get("input"))
                if codex_requested
                else 0
            ),
        )
        input_ceiling = (
            self._settings.CODEX_ABSOLUTE_MAX_INPUT_TOKENS
            if codex_requested
            else self._settings.HARD_MAX_INPUT_TOKENS
        )
        if estimated_input_tokens > input_ceiling:
            _raise(
                "input",
                "input_token_limit_exceeded",
                "Estimated Responses compact input size exceeds the configured hard maximum.",
            )
        output_tokens = self._settings.RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS
        compact_output_ceiling = (
            self._settings.CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS
            if codex_requested
            else self._settings.RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS
        )
        if output_tokens > compact_output_ceiling:
            _raise(
                "max_output_tokens",
                "output_token_limit_exceeded",
                "Responses compact output reservation exceeds the configured hard maximum.",
            )

        return ResponsesPolicyResult(
            effective_body=effective_body,
            requested_output_tokens=output_tokens,
            effective_output_tokens=output_tokens,
            estimated_input_tokens=estimated_input_tokens,
            estimated_message_input_tokens=max(
                0, estimated_input_tokens - estimated_non_message_tokens
            ),
            estimated_non_message_input_tokens=estimated_non_message_tokens,
            estimated_non_message_input_bytes=estimated_non_message_bytes,
            estimated_non_message_input_fields=estimated_non_message_fields,
            injected_default_output_tokens=True,
        )

    def _reject_unknown_fields(
        self,
        body: Mapping[str, Any],
        *,
        allowed_fields: frozenset[str] = _SUPPORTED_FIELDS,
    ) -> None:
        for field in body:
            field_name = str(field)
            if field_name not in allowed_fields:
                code = _unsupported_code_for_field(field_name)
                _raise(
                    field_name,
                    code,
                    "This Responses request field is not enabled by this gateway.",
                )

    def _validate_input(
        self,
        value: Any,
        *,
        allow_codex_request_envelope: bool = False,
        allow_codex_client_tools: bool = False,
        allow_codex_streaming_tool_events: bool = False,
        allow_codex_encrypted_reasoning_replay: bool = False,
        allow_codex_compaction_replay: bool = False,
        codex_client_tool_taxonomy: str | None = None,
    ) -> tuple[str | list[dict[str, Any]], int]:
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
            return self._validate_input_item_array(
                value,
                allow_codex_request_envelope=allow_codex_request_envelope,
                allow_codex_client_tools=allow_codex_client_tools,
                allow_codex_streaming_tool_events=allow_codex_streaming_tool_events,
                allow_codex_encrypted_reasoning_replay=(allow_codex_encrypted_reasoning_replay),
                allow_codex_compaction_replay=allow_codex_compaction_replay,
                codex_client_tool_taxonomy=codex_client_tool_taxonomy,
            )

        _raise(
            "input",
            "responses_field_invalid_type",
            "The 'input' field must be a non-empty text string or text input item array.",
        )

    def _validate_compact_input(self, value: Any) -> tuple[str | list[dict[str, Any]], int]:
        if isinstance(value, str):
            if not value:
                _raise(
                    "input",
                    "responses_compact_input_invalid",
                    "Responses compaction input must be a non-empty string or message item array.",
                )
            self._validate_string_bytes(
                value,
                param="input",
                max_bytes=self._settings.RESPONSES_MAX_INPUT_TEXT_BYTES,
            )
            return value, len(value.encode("utf-8"))

        if isinstance(value, list):
            return self._validate_compact_input_item_array(value)

        _raise(
            "input",
            "responses_compact_input_invalid",
            "Responses compaction input must be a non-empty string or message item array.",
        )
        raise AssertionError("unreachable")

    def _validate_compact_input_item_array(
        self, value: list[Any]
    ) -> tuple[list[dict[str, Any]], int]:
        if not value:
            _raise(
                "input",
                "responses_compact_input_invalid",
                "Responses compaction input item arrays must contain at least one item.",
            )
        if len(value) > self._settings.RESPONSES_MAX_INPUT_ITEMS:
            _raise(
                "input",
                "responses_input_item_count_exceeded",
                "The Responses compact input item array has too many items.",
            )

        canonical_items: list[dict[str, Any]] = []
        total_text_bytes = 0
        for index, item in enumerate(value):
            canonical_item, item_text_bytes = self._validate_compact_input_item(
                item,
                index=index,
            )
            total_text_bytes += item_text_bytes
            if total_text_bytes > self._settings.RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES:
                _raise(
                    "input",
                    "responses_input_item_too_large",
                    "The Responses compact input text exceeds the gateway size limit.",
                )
            canonical_items.append(canonical_item)
        return canonical_items, total_text_bytes

    def _validate_compact_input_item(self, item: Any, *, index: int) -> tuple[dict[str, Any], int]:
        param = f"input[{index}]"
        if not isinstance(item, Mapping):
            _raise(
                param,
                "responses_compact_input_invalid",
                "Each Responses compact input item must be an object.",
            )
        unknown = set(item) - _SUPPORTED_COMPACT_MESSAGE_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_compact_input_invalid",
                "This Responses compact input item field is not enabled by this gateway.",
            )
        item_type = item.get("type")
        if item_type is not None and item_type != "message":
            _raise(
                f"{param}.type",
                "responses_compact_input_item_type_not_supported",
                "Only Responses message items are enabled for compaction by this gateway.",
            )
        role = item.get("role")
        if role not in _SUPPORTED_INPUT_MESSAGE_ROLES:
            _raise(
                f"{param}.role",
                "responses_input_item_role_not_supported",
                "This Responses compact input message role is not enabled by this gateway.",
            )
        if "content" not in item:
            _raise(
                f"{param}.content",
                "responses_compact_input_invalid",
                "Responses compact input message items require text content.",
            )
        canonical_content, text_bytes = self._validate_compact_input_item_content(
            item["content"],
            param=f"{param}.content",
        )
        canonical_item: dict[str, Any] = {"role": role, "content": canonical_content}
        if item_type == "message":
            canonical_item["type"] = "message"
        item_id = item.get("id")
        if item_id is not None:
            if not isinstance(item_id, str) or not item_id:
                _raise(
                    f"{param}.id",
                    "responses_compact_input_invalid",
                    "Responses compact input item IDs must be non-empty strings.",
                )
            self._validate_string_bytes(
                item_id,
                param=f"{param}.id",
                max_bytes=self._settings.RESPONSES_MAX_PREVIOUS_RESPONSE_ID_BYTES,
                code="responses_compact_input_invalid",
            )
            canonical_item["id"] = item_id
        status = item.get("status")
        if status is not None:
            if status not in _SUPPORTED_COMPACT_MESSAGE_STATUSES:
                _raise(
                    f"{param}.status",
                    "responses_compact_input_invalid",
                    "Responses compact input item status is not supported.",
                )
            canonical_item["status"] = status
        return canonical_item, text_bytes

    def _validate_compact_input_item_content(
        self,
        content: Any,
        *,
        param: str,
    ) -> tuple[str | list[dict[str, str]], int]:
        if isinstance(content, str):
            if not content:
                _raise(
                    param,
                    "responses_compact_input_invalid",
                    "Responses compact input message text content must be non-empty.",
                )
            text_bytes = len(content.encode("utf-8"))
            self._validate_input_item_text_bytes(text_bytes, param=param)
            return content, text_bytes

        if isinstance(content, list):
            if not content:
                _raise(
                    param,
                    "responses_compact_input_invalid",
                    "Responses compact input content arrays must contain at least one text part.",
                )
            canonical_parts: list[dict[str, str]] = []
            total_text_bytes = 0
            for part_index, part in enumerate(content):
                canonical_part, part_bytes = self._validate_compact_text_part(
                    part,
                    param=f"{param}[{part_index}]",
                )
                total_text_bytes += part_bytes
                canonical_parts.append(canonical_part)
            self._validate_input_item_text_bytes(total_text_bytes, param=param)
            return canonical_parts, total_text_bytes

        _raise(
            param,
            "responses_compact_input_invalid",
            "Responses compact input message content must be text or text content parts.",
        )
        raise AssertionError("unreachable")

    def _validate_compact_text_part(self, part: Any, *, param: str) -> tuple[dict[str, str], int]:
        if not isinstance(part, Mapping):
            _raise(
                param,
                "responses_compact_input_content_part_not_supported",
                "Responses compact input content parts must be text objects.",
            )
        part_type = part.get("type")
        if part_type not in _SUPPORTED_COMPACT_PART_TYPES:
            _raise(
                f"{param}.type",
                "responses_compact_input_content_part_not_supported",
                "Only input_text and output_text content parts are enabled for compaction.",
            )
        unknown = set(part) - _SUPPORTED_COMPACT_TEXT_PART_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_compact_input_content_part_not_supported",
                "This Responses compact content part field is not enabled by this gateway.",
            )
        text = part.get("text")
        if not isinstance(text, str) or not text:
            _raise(
                f"{param}.text",
                "responses_compact_input_invalid",
                "Responses compact text parts require non-empty text.",
            )
        text_bytes = len(text.encode("utf-8"))
        self._validate_input_item_text_bytes(text_bytes, param=f"{param}.text")
        return {"type": part_type, "text": text}, text_bytes

    def _validate_input_item_array(
        self,
        value: list[Any],
        *,
        allow_codex_request_envelope: bool = False,
        allow_codex_client_tools: bool = False,
        allow_codex_streaming_tool_events: bool = False,
        allow_codex_encrypted_reasoning_replay: bool = False,
        allow_codex_compaction_replay: bool = False,
        codex_client_tool_taxonomy: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
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
        total_material_bytes = 0
        total_image_parts = 0
        total_image_data_url_bytes = 0
        total_file_parts = 0
        total_file_data_url_bytes = 0
        codex_client_tool_items = 0
        codex_tool_call_items = 0
        codex_reasoning_items = 0
        encrypted_reasoning_bytes = 0
        for index, item in enumerate(value):
            if isinstance(item, Mapping) and item.get("type") == "additional_tools":
                codex_client_tool_items += 1
                if codex_client_tool_items > 1:
                    _raise(
                        f"input[{index}].type",
                        "responses_codex_client_tools_invalid",
                        "At most one Codex additional_tools input item is allowed.",
                    )
            if isinstance(item, Mapping) and item.get("type") in {
                "function_call",
                "custom_tool_call",
            }:
                codex_tool_call_items += 1
            if isinstance(item, Mapping) and item.get("type") == "reasoning":
                codex_reasoning_items += 1
            (
                canonical_item,
                item_text_bytes,
                item_material_bytes,
                item_image_parts,
                item_image_data_url_bytes,
                item_file_parts,
                item_file_data_url_bytes,
            ) = self._validate_input_item(
                item,
                index=index,
                allow_codex_request_envelope=allow_codex_request_envelope,
                allow_codex_client_tools=allow_codex_client_tools,
                allow_codex_streaming_tool_events=allow_codex_streaming_tool_events,
                allow_codex_encrypted_reasoning_replay=(allow_codex_encrypted_reasoning_replay),
                allow_codex_compaction_replay=allow_codex_compaction_replay,
                codex_client_tool_taxonomy=codex_client_tool_taxonomy,
            )
            if canonical_item.get("type") == "reasoning":
                encrypted_value = canonical_item["encrypted_content"]
                assert isinstance(encrypted_value, str)
                encrypted_reasoning_bytes += len(encrypted_value.encode("utf-8"))
                if encrypted_reasoning_bytes > self._codex_spec.max_encrypted_reasoning_request_bytes:
                    _raise(
                        "input",
                        "responses_codex_encrypted_reasoning_replay_too_large",
                        "Codex encrypted reasoning replay exceeds the gateway size limit.",
                    )
            total_text_bytes += item_text_bytes
            total_material_bytes += item_material_bytes
            total_image_parts += item_image_parts
            total_image_data_url_bytes += item_image_data_url_bytes
            total_file_parts += item_file_parts
            total_file_data_url_bytes += item_file_data_url_bytes
            if total_text_bytes > self._settings.RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES:
                _raise(
                    "input",
                    "responses_input_item_too_large",
                    "The Responses input item text exceeds the gateway size limit.",
                )
            if total_image_parts > self._settings.RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST:
                _raise(
                    "input",
                    "responses_input_image_count_exceeded",
                    "The Responses input item array has too many image content parts.",
                )
            if total_image_data_url_bytes > self._settings.RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES:
                _raise(
                    "input",
                    "responses_input_image_data_url_too_large",
                    "The Responses input image data URLs exceed the gateway size limit.",
                )
            if total_file_parts > self._settings.RESPONSES_MAX_FILE_PARTS_PER_REQUEST:
                _raise(
                    "input",
                    "responses_input_file_count_exceeded",
                    "The Responses input item array has too many file content parts.",
                )
            if total_file_data_url_bytes > self._settings.RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES:
                _raise(
                    "input",
                    "responses_input_file_data_url_too_large",
                    "The Responses input file data URLs exceed the gateway size limit.",
                )
            canonical_items.append(canonical_item)
        if codex_tool_call_items and not codex_client_tool_items:
            _raise(
                "input",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation requires the exact client-tool declarations.",
            )
        if codex_client_tool_items or codex_reasoning_items:
            self._validate_codex_tool_roundtrip_items(
                canonical_items,
                allow_codex_streaming_tool_events=allow_codex_streaming_tool_events,
            )
        return canonical_items, total_material_bytes

    def _validate_input_item(
        self,
        item: Any,
        *,
        index: int,
        allow_codex_request_envelope: bool = False,
        allow_codex_client_tools: bool = False,
        allow_codex_streaming_tool_events: bool = False,
        allow_codex_encrypted_reasoning_replay: bool = False,
        allow_codex_compaction_replay: bool = False,
        codex_client_tool_taxonomy: str | None = None,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        param = f"input[{index}]"
        if not isinstance(item, Mapping):
            _raise(
                param,
                "responses_input_item_invalid",
                "Each Responses input item must be an object.",
            )

        item = self._copy_and_drop_codex_internal_chat_message_metadata(
            item,
            param=param,
            allow_codex_request_envelope=allow_codex_request_envelope,
            allow_codex_client_tools=allow_codex_client_tools,
            allow_codex_streaming_tool_events=allow_codex_streaming_tool_events,
            allow_codex_encrypted_reasoning_replay=allow_codex_encrypted_reasoning_replay,
            allow_codex_compaction_replay=allow_codex_compaction_replay,
        )
        item_type = item.get("type")
        if item_type == "compaction":
            if not allow_codex_compaction_replay:
                _raise(
                    f"{param}.type",
                    "responses_codex_compaction_not_allowed",
                    "Codex compaction replay is not enabled for this gateway key.",
                )
            return self._validate_codex_compaction_replay_item(item, param=param)
        if item_type == "additional_tools":
            if not (allow_codex_request_envelope and allow_codex_client_tools):
                _raise(
                    f"{param}.type",
                    "responses_codex_client_tools_not_allowed",
                    "Codex client tool namespaces are not enabled for this gateway key.",
                )
            return self._validate_codex_additional_tools_item(
                item, param=param, codex_client_tool_taxonomy=codex_client_tool_taxonomy
            )
        if item_type == "reasoning" and (
            "encrypted_content" in item or allow_codex_encrypted_reasoning_replay
        ):
            if not (allow_codex_request_envelope and allow_codex_encrypted_reasoning_replay):
                _raise(
                    f"{param}.type",
                    "responses_codex_encrypted_reasoning_replay_not_allowed",
                    "Codex encrypted reasoning replay is not enabled for this gateway key.",
                )
            return self._validate_codex_reasoning_replay_item(item, param=param)
        if item_type == "function_call":
            if (
                allow_codex_request_envelope
                and allow_codex_client_tools
                and allow_codex_streaming_tool_events
            ):
                return self._validate_codex_tool_call_item(item, param=param, custom=False)
        if item_type == "custom_tool_call":
            if (
                allow_codex_request_envelope
                and allow_codex_client_tools
                and allow_codex_streaming_tool_events
            ):
                return self._validate_codex_tool_call_item(item, param=param, custom=True)
        if item_type == "function_call_output":
            if (
                allow_codex_request_envelope
                and allow_codex_client_tools
                and allow_codex_streaming_tool_events
            ):
                return self._validate_codex_tool_call_output_item(item, param=param, custom=False)
            return self._validate_function_call_output_item(item, param=param)
        if item_type == "custom_tool_call_output":
            if (
                allow_codex_request_envelope
                and allow_codex_client_tools
                and allow_codex_streaming_tool_events
            ):
                return self._validate_codex_tool_call_output_item(item, param=param, custom=True)
            return self._validate_custom_tool_call_output_item(item, param=param)
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

        (
            canonical_content,
            text_bytes,
            material_bytes,
            image_parts,
            image_data_url_bytes,
            file_parts,
            file_data_url_bytes,
        ) = self._validate_input_item_content(
            item["content"],
            param=f"{param}.content",
            role=role,
        )
        canonical_item: dict[str, Any] = {"role": role, "content": canonical_content}
        if item_type == "message":
            canonical_item["type"] = "message"
        if "id" in item:
            if not allow_codex_request_envelope:
                _raise(
                    f"{param}.id",
                    "responses_codex_envelope_not_allowed",
                    "The Codex request envelope is not enabled for this gateway key.",
                )
            item_id = self._validate_codex_message_id(item.get("id"), param=f"{param}.id")
            canonical_item["id"] = item_id
        return (
            canonical_item,
            text_bytes,
            material_bytes,
            image_parts,
            image_data_url_bytes,
            file_parts,
            file_data_url_bytes,
        )

    def _copy_and_drop_codex_internal_chat_message_metadata(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
        allow_codex_request_envelope: bool,
        allow_codex_client_tools: bool,
        allow_codex_streaming_tool_events: bool,
        allow_codex_encrypted_reasoning_replay: bool,
        allow_codex_compaction_replay: bool,
    ) -> dict[str, Any]:
        copied_item = dict(item)
        if self._codex_spec is None:
            return copied_item
        if self._codex_spec.internal_chat_message_metadata_field not in copied_item:
            return copied_item

        fully_gated = all(
            (
                allow_codex_request_envelope,
                allow_codex_client_tools,
                allow_codex_streaming_tool_events,
                allow_codex_encrypted_reasoning_replay,
                allow_codex_compaction_replay,
            )
        )
        if (
            not fully_gated
            or copied_item.get("type")
            not in self._codex_spec.internal_chat_message_metadata_item_types
        ):
            return copied_item

        metadata_param = f"{param}.{self._codex_spec.internal_chat_message_metadata_field}"
        metadata = copied_item[self._codex_spec.internal_chat_message_metadata_field]
        if metadata is not None:
            if not isinstance(metadata, Mapping):
                raise ResponsesRequestPolicyError(
                    "Codex internal chat metadata must be a bounded JSON object or null.",
                    param=metadata_param,
                    error_code="responses_codex_internal_chat_metadata_invalid",
                )
            try:
                metadata_bytes = len(canonical_json_bytes(metadata))
            except ValueError as exc:
                raise ResponsesRequestPolicyError(
                    "Codex internal chat metadata must be a bounded JSON object or null.",
                    param=metadata_param,
                    error_code="responses_codex_internal_chat_metadata_invalid",
                ) from exc
            if metadata_bytes > self._codex_spec.max_internal_chat_message_metadata_bytes:
                raise ResponsesRequestPolicyError(
                    "Codex internal chat metadata must be a bounded JSON object or null.",
                    param=metadata_param,
                    error_code="responses_codex_internal_chat_metadata_invalid",
                )

        del copied_item[self._codex_spec.internal_chat_message_metadata_field]
        return copied_item

    def _validate_codex_additional_tools_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
        codex_client_tool_taxonomy: str | None = None,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        unknown = set(item) - self._codex_spec.additional_tools_fields
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_codex_client_tools_invalid",
                "This Codex additional_tools field is not enabled by this gateway.",
            )
        if item.get("role") != "developer":
            _raise(
                f"{param}.role",
                "responses_codex_client_tools_invalid",
                "Codex additional_tools items require the developer role.",
            )
        namespaces = item.get("tools")
        taxonomy = (
            self._codex_spec.taxonomy_0148
            if codex_client_tool_taxonomy == self._codex_spec.taxonomy_id_0148
            else self._codex_spec.taxonomy_for(namespaces)
        )
        if taxonomy is None:
            _raise(
                f"{param}.tools",
                "responses_codex_client_tools_invalid",
                "Codex additional_tools requires the exact approved namespace set.",
            )

        expected_namespaces = dict(taxonomy)
        canonical_by_namespace: dict[str, dict[str, Any]] = {}
        total_function_schema_bytes = 0
        total_custom_format_bytes = 0
        total_description_bytes = 0
        total_schema_properties = 0
        for namespace_index, namespace in enumerate(namespaces):
            namespace_param = f"{param}.tools[{namespace_index}]"
            if not isinstance(namespace, Mapping):
                _raise(
                    namespace_param,
                    "responses_codex_client_tools_invalid",
                    "Codex client tool namespaces must be objects.",
                )
            unknown_namespace_fields = set(namespace) - self._codex_spec.namespace_fields
            if unknown_namespace_fields:
                _raise(
                    f"{namespace_param}.{sorted(unknown_namespace_fields)[0]}",
                    "responses_codex_client_tools_invalid",
                    "This Codex client tool namespace field is not enabled.",
                )
            if namespace.get("type") != "namespace":
                _raise(
                    f"{namespace_param}.type",
                    "responses_codex_client_tools_invalid",
                    "Codex client tool containers must use type namespace.",
                )
            namespace_name = namespace.get("name")
            if not isinstance(namespace_name, str) or namespace_name not in expected_namespaces:
                _raise(
                    f"{namespace_param}.name",
                    "responses_codex_client_tools_invalid",
                    "This Codex client tool namespace is not approved.",
                )
            if namespace_name in canonical_by_namespace:
                _raise(
                    f"{namespace_param}.name",
                    "responses_codex_client_tools_invalid",
                    "Codex client tool namespace names must be unique.",
                )
            description = namespace.get("description")
            if description is not None:
                if not isinstance(description, str):
                    _raise(
                        f"{namespace_param}.description",
                        "responses_codex_client_tools_invalid",
                        "Codex client tool namespace descriptions must be strings.",
                    )
                self._validate_string_bytes(
                    description,
                    param=f"{namespace_param}.description",
                    max_bytes=self._settings.RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES,
                    code="responses_codex_client_tools_invalid",
                )
                total_description_bytes += len(description.encode("utf-8"))

            tools = namespace.get("tools")
            expected_tools = dict(expected_namespaces[str(namespace_name)])
            if not isinstance(tools, list) or len(tools) != len(expected_tools):
                _raise(
                    f"{namespace_param}.tools",
                    "responses_codex_client_tools_invalid",
                    "This Codex namespace requires its exact approved client tool set.",
                )
            canonical_by_tool: dict[str, dict[str, Any]] = {}
            for tool_index, tool in enumerate(tools):
                tool_param = f"{namespace_param}.tools[{tool_index}]"
                if not isinstance(tool, Mapping):
                    _raise(
                        tool_param,
                        "responses_codex_client_tools_invalid",
                        "Codex namespace tools must be objects.",
                    )
                tool_name = tool.get("name")
                if not isinstance(tool_name, str) or tool_name not in expected_tools:
                    _raise(
                        f"{tool_param}.name",
                        "responses_codex_client_tools_invalid",
                        "This Codex client tool name is not approved in this namespace.",
                    )
                if tool_name in canonical_by_tool:
                    _raise(
                        f"{tool_param}.name",
                        "responses_codex_client_tools_invalid",
                        "Codex client tool names must be unique within a namespace.",
                    )
                if tool.get("type") != expected_tools[str(tool_name)]:
                    _raise(
                        f"{tool_param}.type",
                        "responses_codex_client_tools_invalid",
                        "This Codex client tool has an invalid declaration type.",
                    )
                if namespace_name == "functions" and tool_name == "request_user_input":
                    allowed_authority_key_paths = self._codex_spec.request_user_input_allowed_authority_key_paths
                elif namespace_name == "functions" and tool_name == "exec_command":
                    allowed_authority_key_paths = self._codex_spec.exec_command_allowed_authority_key_paths
                else:
                    allowed_authority_key_paths = frozenset()
                if _contains_recursive_codex_authority_marker(
                    tool, allowed_key_paths=allowed_authority_key_paths
                ):
                    _raise(
                        tool_param,
                        "responses_codex_client_tools_provider_authority_not_supported",
                        "Provider authority and hosted tool shapes are not enabled here.",
                    )
                canonical_tool, schema_bytes, format_bytes = self._validate_local_tool(
                    tool,
                    param=tool_param,
                    description_max_bytes=self._codex_spec.max_client_tool_description_bytes,
                )
                if canonical_tool["type"] == "function":
                    total_schema_properties += _validate_codex_schema_complexity(
                        canonical_tool["parameters"],
                        param=f"{tool_param}.parameters",
                        client_spec=self._codex_spec,
                    )
                    if total_schema_properties > self._codex_spec.max_client_tool_schema_properties:
                        _raise(
                            f"{param}.tools",
                            "responses_codex_client_tools_property_count_exceeded",
                            "The Codex client function schemas have too many properties.",
                        )
                    total_function_schema_bytes += schema_bytes
                else:
                    format_value = canonical_tool.get("format")
                    if (
                        tool_name != "exec"
                        or not isinstance(format_value, Mapping)
                        or format_value.get("type") != "grammar"
                        or format_value.get("syntax") not in _CUSTOM_TOOL_GRAMMAR_SYNTAXES
                    ):
                        _raise(
                            f"{tool_param}.format",
                            "responses_codex_client_tools_invalid",
                            "The Codex exec tool requires an approved bounded grammar format.",
                        )
                    total_custom_format_bytes += format_bytes
                tool_description = canonical_tool.get("description")
                if isinstance(tool_description, str):
                    total_description_bytes += len(tool_description.encode("utf-8"))
                canonical_by_tool[str(tool_name)] = canonical_tool

            canonical_tools = [
                canonical_by_tool[tool_name]
                for tool_name, _tool_type in expected_namespaces[str(namespace_name)]
            ]
            canonical_namespace: dict[str, Any] = {
                "type": "namespace",
                "name": namespace_name,
            }
            if description is not None:
                canonical_namespace["description"] = description
            canonical_namespace["tools"] = canonical_tools
            canonical_by_namespace[str(namespace_name)] = canonical_namespace

        if (
            total_function_schema_bytes
            > self._settings.RESPONSES_MAX_TOTAL_FUNCTION_TOOL_SCHEMA_BYTES
        ):
            _raise(
                f"{param}.tools",
                "responses_function_tool_schema_too_large",
                "The total Codex client function schema size exceeds the gateway limit.",
            )
        if total_custom_format_bytes > self._settings.RESPONSES_MAX_TOTAL_CUSTOM_TOOL_FORMAT_BYTES:
            _raise(
                f"{param}.tools",
                "responses_custom_tool_format_too_large",
                "The total Codex client custom format size exceeds the gateway limit.",
            )
        if total_description_bytes > self._codex_spec.max_client_tool_total_description_bytes:
            _raise(
                f"{param}.tools",
                "responses_codex_client_tools_too_large",
                "The total Codex client tool description size exceeds the gateway limit.",
            )
        canonical_item = {
            "type": "additional_tools",
            "role": "developer",
            "tools": [
                canonical_by_namespace[namespace_name]
                for namespace_name, _tools in taxonomy
            ],
        }
        if len(canonical_json_bytes(canonical_item)) > self._codex_spec.max_client_tool_declaration_bytes:
            _raise(
                param,
                "responses_codex_client_tools_too_large",
                "The Codex client tool declaration exceeds the gateway size limit.",
            )
        # Declaration bytes are accounted separately as safe non-message evidence.
        return canonical_item, 0, 0, 0, 0, 0, 0

    def _validate_codex_client_tool_controls(self, body: Mapping[str, Any]) -> None:
        if not responses_codex_client_tools_requested(body):
            return
        if "tools" in body:
            _raise(
                "tools",
                "responses_codex_client_tools_invalid",
                "Codex additional_tools cannot be combined with top-level Responses tools.",
            )

    def _validate_codex_reasoning_replay_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        unknown = set(item) - self._codex_spec.reasoning_replay_fields
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_codex_encrypted_reasoning_replay_invalid",
                "This Codex encrypted reasoning field is not enabled.",
            )
        if item.get("type") != "reasoning":
            _raise(
                f"{param}.type",
                "responses_codex_encrypted_reasoning_replay_invalid",
                "Codex encrypted reasoning replay requires type reasoning.",
            )
        item_id_value = item.get("id")
        if item_id_value is None:
            _raise(
                f"{param}.id",
                "responses_codex_encrypted_reasoning_replay_invalid",
                "Codex encrypted reasoning replay requires a bounded item ID.",
            )
        item_id = self._validate_codex_message_id(item_id_value, param=f"{param}.id")
        encrypted_content = item.get("encrypted_content")
        if encrypted_content is not None and (not isinstance(encrypted_content, str) or not encrypted_content):
            _raise(
                f"{param}.encrypted_content",
                "responses_codex_encrypted_reasoning_replay_invalid",
                "Codex encrypted reasoning replay requires an opaque encrypted value.",
            )
        self._validate_string_bytes(
            encrypted_content,
            param=f"{param}.encrypted_content",
            max_bytes=self._codex_spec.max_encrypted_reasoning_item_bytes,
            code="responses_codex_encrypted_reasoning_replay_too_large",
        )
        if "content" in item and item.get("content") is not None:
            _raise(
                f"{param}.content",
                "responses_codex_encrypted_reasoning_replay_invalid",
                "Codex encrypted reasoning replay permits only null content.",
            )
        summary_value = item.get("summary", [])
        if (
            not isinstance(summary_value, list)
            or len(summary_value) > self._codex_spec.max_reasoning_summary_parts
        ):
            _raise(
                f"{param}.summary",
                "responses_codex_encrypted_reasoning_replay_invalid",
                "Codex reasoning summaries must use the bounded summary-text array.",
            )
        canonical_summary: list[dict[str, str]] = []
        summary_bytes = 0
        for summary_index, part in enumerate(summary_value):
            part_param = f"{param}.summary[{summary_index}]"
            if (
                not isinstance(part, Mapping)
                or set(part) != self._codex_spec.reasoning_summary_fields
            ):
                _raise(
                    part_param,
                    "responses_codex_encrypted_reasoning_replay_invalid",
                    "Codex reasoning summaries require exact summary-text parts.",
                )
            if part.get("type") != "summary_text" or not isinstance(part.get("text"), str):
                _raise(
                    part_param,
                    "responses_codex_encrypted_reasoning_replay_invalid",
                    "Codex reasoning summaries require exact summary-text parts.",
                )
            text_value = str(part["text"])
            summary_bytes += len(text_value.encode("utf-8"))
            if summary_bytes > self._codex_spec.max_reasoning_summary_bytes:
                _raise(
                    f"{param}.summary",
                    "responses_codex_encrypted_reasoning_replay_too_large",
                    "Codex reasoning summaries exceed the gateway size limit.",
                )
            canonical_summary.append({"type": "summary_text", "text": text_value})
        canonical = {
            "type": "reasoning",
            "id": item_id,
            "summary": canonical_summary,
            "encrypted_content": encrypted_content,
        }
        if "content" in item:
            canonical["content"] = None
        text_bytes = len(encrypted_content.encode("utf-8")) + summary_bytes
        material_bytes = len(canonical_json_bytes(canonical))
        return canonical, text_bytes, material_bytes, 0, 0, 0, 0

    def _validate_codex_compaction_replay_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        if set(item) != self._codex_spec.compaction_replay_fields:
            _raise(
                param,
                "responses_codex_compaction_replay_invalid",
                "Codex compaction replay requires the exact opaque item shape.",
            )
        item_id = self._validate_codex_message_id(item.get("id"), param=f"{param}.id")
        encrypted_content = item.get("encrypted_content")
        if not isinstance(encrypted_content, str) or not encrypted_content:
            _raise(
                f"{param}.encrypted_content",
                "responses_codex_compaction_replay_invalid",
                "Codex compaction replay requires a non-empty opaque value.",
            )
        self._validate_string_bytes(
            encrypted_content,
            param=f"{param}.encrypted_content",
            max_bytes=self._codex_spec.max_compaction_item_bytes,
            code="responses_codex_compaction_replay_too_large",
        )
        canonical = {
            "type": "compaction",
            "id": item_id,
            "encrypted_content": encrypted_content,
        }
        material_bytes = len(canonical_json_bytes(canonical))
        return canonical, material_bytes, material_bytes, 0, 0, 0, 0

    def _validate_codex_tool_call_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
        custom: bool,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        allowed_fields = (
            self._codex_spec.custom_tool_call_fields
            if custom
            else self._codex_spec.function_call_fields
        )
        unknown = set(item) - allowed_fields
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_codex_tool_roundtrip_invalid",
                "This Codex tool-call continuation field is not enabled.",
            )
        expected_type = "custom_tool_call" if custom else "function_call"
        if item.get("type") != expected_type:
            _raise(
                f"{param}.type",
                "responses_codex_tool_roundtrip_invalid",
                "This Codex tool-call continuation type is invalid.",
            )
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or self._codex_spec.tool_call_id_pattern.fullmatch(call_id) is None:
            _raise(
                f"{param}.call_id",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation requires a bounded call ID.",
            )
        name = item.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                f"{param}.name",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation requires a declared tool name.",
            )
        self._validate_string_bytes(
            name,
            param=f"{param}.name",
            max_bytes=(
                self._settings.RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES
                if custom
                else self._settings.RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES
            ),
            code="responses_codex_tool_roundtrip_invalid",
        )
        namespace = item.get("namespace")
        if namespace is not None:
            if not isinstance(namespace, str) or not namespace:
                _raise(
                    f"{param}.namespace",
                    "responses_codex_tool_roundtrip_invalid",
                    "Codex tool-call namespace must be a bounded string.",
                )
            self._validate_string_bytes(
                namespace,
                param=f"{param}.namespace",
                max_bytes=self._settings.RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES,
                code="responses_codex_tool_roundtrip_invalid",
            )
        status = item.get("status")
        if status is not None and status not in self._codex_spec.tool_call_statuses:
            _raise(
                f"{param}.status",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation status is not supported.",
            )
        item_id_value = item.get("id")
        if item_id_value is None:
            _raise(
                f"{param}.id",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation requires a bounded item ID.",
            )
        item_id = self._validate_codex_message_id(item_id_value, param=f"{param}.id")
        text_field = "input" if custom else "arguments"
        text_value = item.get(text_field)
        if not isinstance(text_value, str):
            _raise(
                f"{param}.{text_field}",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation payload must be a string.",
            )
        self._validate_string_bytes(
            text_value,
            param=f"{param}.{text_field}",
            max_bytes=(
                self._settings.RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES
                if custom
                else self._settings.RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES
            ),
            code="responses_codex_tool_roundtrip_too_large",
        )
        canonical: dict[str, Any] = {
            "type": expected_type,
            "call_id": call_id,
            "name": name,
        }
        canonical["id"] = item_id
        if status is not None:
            canonical["status"] = status
        if namespace is not None:
            canonical["namespace"] = namespace
        canonical[text_field] = text_value
        material_bytes = len(canonical_json_bytes(canonical))
        return canonical, material_bytes, material_bytes, 0, 0, 0, 0

    def _validate_codex_tool_roundtrip_items(
        self,
        items: list[dict[str, Any]],
        *,
        allow_codex_streaming_tool_events: bool,
    ) -> None:
        declarations = _codex_declarations_from_input_items(items)
        calls: dict[str, tuple[str, str, str]] = {}
        outputs: dict[str, str] = {}
        item_ids: set[str] = set()
        for index, item in enumerate(items):
            item_type = item.get("type")
            item_id = item.get("id")
            if isinstance(item_id, str):
                if item_id in item_ids:
                    _raise(
                        f"input[{index}].id",
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex replay item IDs must be unique within one request.",
                    )
                item_ids.add(item_id)
            if item_type == "reasoning":
                continue
            if item_type in {"function_call", "custom_tool_call"}:
                if not allow_codex_streaming_tool_events:
                    _raise(
                        f"input[{index}].type",
                        "responses_codex_streaming_tool_events_not_allowed",
                        "Codex tool-call continuation is not enabled for this gateway key.",
                    )
                tool_type = "custom" if item_type == "custom_tool_call" else "function"
                name = str(item["name"])
                namespace = item.get("namespace")
                matches = [
                    declaration
                    for declaration in declarations
                    if declaration[1] == name
                    and declaration[2] == tool_type
                    and (namespace is None or declaration[0] == namespace)
                ]
                if len(matches) != 1 or (
                    tool_type == "custom" and matches[0] != ("functions", "exec", "custom")
                ):
                    _raise(
                        f"input[{index}].name",
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex tool calls must match the exact declared client-tool taxonomy.",
                    )
                call_id = str(item["call_id"])
                if call_id in calls:
                    _raise(
                        f"input[{index}].call_id",
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex tool-call IDs must be unique.",
                    )
                calls[call_id] = matches[0]
                if index + 1 >= len(items):
                    _raise(
                        "input",
                        "responses_codex_tool_roundtrip_invalid",
                        "Each Codex tool call must be followed immediately by its output.",
                    )
                next_item = items[index + 1]
                expected_output_type = (
                    "custom_tool_call_output"
                    if item_type == "custom_tool_call"
                    else "function_call_output"
                )
                if (
                    next_item.get("type") != expected_output_type
                    or next_item.get("call_id") != call_id
                ):
                    _raise(
                        f"input[{index + 1}]",
                        "responses_codex_tool_roundtrip_invalid",
                        "Each Codex tool output must immediately follow its matching call.",
                    )
            elif item_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(item["call_id"])
                if call_id in outputs:
                    _raise(
                        f"input[{index}].call_id",
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex tool-call output IDs must be unique.",
                    )
                outputs[call_id] = str(item_type)
                if index == 0:
                    _raise(
                        f"input[{index}]",
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex tool outputs must follow their matching call.",
                    )
                previous = items[index - 1]
                expected_call_type = (
                    "custom_tool_call"
                    if item_type == "custom_tool_call_output"
                    else "function_call"
                )
                if previous.get("type") != expected_call_type or previous.get("call_id") != call_id:
                    _raise(
                        f"input[{index}]",
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex tool outputs must immediately follow their matching call.",
                    )

        for call_id, output_type in outputs.items():
            declaration = calls.get(call_id)
            expected_type = (
                "custom_tool_call_output"
                if declaration is not None and declaration[2] == "custom"
                else "function_call_output"
            )
            if declaration is None or output_type != expected_type:
                _raise(
                    "input",
                    "responses_codex_tool_roundtrip_invalid",
                    "Codex tool outputs must match one approved tool call and call ID.",
                )
        if set(calls) != set(outputs):
            _raise(
                "input",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool-call continuation requires exactly one matching bounded output.",
            )

    def _validate_codex_tool_call_output_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
        custom: bool,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        allowed_fields = (
            self._codex_spec.custom_tool_call_output_fields
            if custom
            else self._codex_spec.function_call_output_fields
        )
        unknown = set(item) - allowed_fields
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_codex_tool_roundtrip_invalid",
                "This Codex tool output field is not enabled.",
            )
        expected_type = "custom_tool_call_output" if custom else "function_call_output"
        call_id = item.get("call_id")
        if item.get("type") != expected_type or not isinstance(call_id, str):
            _raise(
                f"{param}.call_id",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool outputs require the matching bounded call ID.",
            )
        if self._codex_spec.tool_call_id_pattern.fullmatch(call_id) is None:
            _raise(
                f"{param}.call_id",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool outputs require the matching bounded call ID.",
            )
        output = item.get("output")
        max_bytes = (
            self._settings.RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES
            if custom
            else self._settings.RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES
        )
        canonical_output: str | list[dict[str, str]]
        if isinstance(output, str):
            self._validate_string_bytes(
                output,
                param=f"{param}.output",
                max_bytes=max_bytes,
                code="responses_codex_tool_roundtrip_too_large",
            )
            canonical_output = output
        elif custom and isinstance(output, list) and 0 < len(output) <= 8:
            canonical_parts: list[dict[str, str]] = []
            total_text_bytes = 0
            for part_index, part in enumerate(output):
                part_param = f"{param}.output[{part_index}]"
                if not isinstance(part, Mapping):
                    _raise(
                        part_param,
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex custom tool output parts must be bounded text objects.",
                    )
                unknown_part_fields = set(part) - self._codex_spec.tool_output_content_fields
                text = part.get("text")
                if (
                    unknown_part_fields
                    or part.get("type") != "input_text"
                    or not isinstance(text, str)
                ):
                    _raise(
                        part_param,
                        "responses_codex_tool_roundtrip_invalid",
                        "Codex custom tool output parts must be bounded input_text objects.",
                    )
                total_text_bytes += len(text.encode("utf-8"))
                if total_text_bytes > max_bytes:
                    _raise(
                        f"{param}.output",
                        "responses_codex_tool_roundtrip_too_large",
                        "Codex custom tool output exceeds the gateway size limit.",
                    )
                canonical_parts.append({"type": "input_text", "text": text})
            canonical_output = canonical_parts
        else:
            _raise(
                f"{param}.output",
                "responses_codex_tool_roundtrip_invalid",
                "Codex tool output must use the approved bounded text shape.",
            )
        canonical = {
            "type": expected_type,
            "call_id": call_id,
            "output": canonical_output,
        }
        if "id" in item:
            canonical["id"] = self._validate_codex_message_id(
                item.get("id"),
                param=f"{param}.id",
            )
        material_bytes = len(canonical_json_bytes(canonical))
        return canonical, material_bytes, material_bytes, 0, 0, 0, 0

    def _validate_function_call_output_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
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
        output_bytes = len(output.encode("utf-8"))
        return (
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
            },
            output_bytes,
            output_bytes,
            0,
            0,
            0,
            0,
        )

    def _validate_custom_tool_call_output_item(
        self,
        item: Mapping[str, Any],
        *,
        param: str,
    ) -> tuple[dict[str, Any], int, int, int, int, int, int]:
        unknown = set(item) - _SUPPORTED_CUSTOM_TOOL_CALL_OUTPUT_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_custom_tool_call_output_invalid",
                "This Responses custom tool call output field is not enabled by this gateway.",
            )
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            _raise(
                f"{param}.call_id",
                "responses_custom_tool_call_output_invalid",
                "Responses custom tool call output items require a non-empty call_id.",
            )
        self._validate_string_bytes(
            call_id,
            param=f"{param}.call_id",
            max_bytes=self._settings.RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES,
            code="responses_custom_tool_call_output_invalid",
        )
        output = item.get("output")
        if not isinstance(output, str):
            _raise(
                f"{param}.output",
                "responses_custom_tool_call_output_invalid",
                "Responses custom tool call output must be a string in this gateway.",
            )
        self._validate_string_bytes(
            output,
            param=f"{param}.output",
            max_bytes=self._settings.RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES,
            code="responses_custom_tool_call_output_too_large",
        )
        output_bytes = len(output.encode("utf-8"))
        return (
            {
                "type": "custom_tool_call_output",
                "call_id": call_id,
                "output": output,
            },
            output_bytes,
            output_bytes,
            0,
            0,
            0,
            0,
        )

    def _validate_input_item_content(
        self,
        content: Any,
        *,
        param: str,
        role: str,
    ) -> tuple[str | list[dict[str, Any]], int, int, int, int, int, int]:
        if isinstance(content, str):
            if not content:
                _raise(
                    param,
                    "responses_input_invalid",
                    "Responses input message text content must be non-empty.",
                )
            text_bytes = len(content.encode("utf-8"))
            self._validate_input_item_text_bytes(text_bytes, param=param)
            return content, text_bytes, text_bytes, 0, 0, 0, 0

        if isinstance(content, list):
            if not content:
                _raise(
                    param,
                    "responses_input_invalid",
                    "Responses input message content arrays must contain at least one text part.",
                )
            canonical_parts: list[dict[str, Any]] = []
            total_text_bytes = 0
            total_material_bytes = 0
            image_parts = 0
            image_data_url_bytes = 0
            file_parts = 0
            file_data_url_bytes = 0
            text_parts = 0
            for part_index, part in enumerate(content):
                if isinstance(part, Mapping) and part.get("type") == "input_image":
                    canonical_part, part_bytes, part_data_bytes = self._validate_input_image_part(
                        part,
                        param=f"{param}[{part_index}]",
                        role=role,
                    )
                    image_parts += 1
                    image_data_url_bytes += part_data_bytes
                elif isinstance(part, Mapping) and part.get("type") == "input_file":
                    canonical_part, part_bytes, part_data_bytes = self._validate_input_file_part(
                        part,
                        param=f"{param}[{part_index}]",
                        role=role,
                    )
                    file_parts += 1
                    file_data_url_bytes += part_data_bytes
                else:
                    canonical_part, part_bytes = self._validate_input_text_part(
                        part,
                        param=f"{param}[{part_index}]",
                    )
                    text_parts += 1
                    total_text_bytes += part_bytes
                total_material_bytes += part_bytes
                canonical_parts.append(canonical_part)
            if text_parts > self._settings.RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM:
                _raise(
                    param,
                    "responses_input_item_count_exceeded",
                    "Responses input message content has too many text parts.",
                )
            self._validate_input_item_text_bytes(total_text_bytes, param=param)
            return (
                canonical_parts,
                total_text_bytes,
                total_material_bytes,
                image_parts,
                image_data_url_bytes,
                file_parts,
                file_data_url_bytes,
            )

        raise ResponsesRequestPolicyError(
            "Responses input message content must be text or a text content-part array.",
            param=param,
            error_code="responses_input_invalid",
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
                if part_type
                in {"input_image", "input_file", "input_audio", "image", "file", "audio"}
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

    def _validate_input_image_part(
        self,
        part: Mapping[str, Any],
        *,
        param: str,
        role: str,
    ) -> tuple[dict[str, str], int, int]:
        if role != "user":
            _raise(
                f"{param}.type",
                "responses_input_image_part_invalid",
                "Responses image input content parts are supported only on user messages.",
            )
        unknown = set(part) - _SUPPORTED_INPUT_IMAGE_PART_FIELDS - {"file_id"}
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_input_image_part_invalid",
                "This Responses image input field is not enabled by this gateway.",
            )
        if "file_id" in part:
            _raise(
                f"{param}.file_id",
                "responses_input_image_file_id_not_supported",
                "Responses image file IDs are not enabled by this gateway.",
            )
        image_url = part.get("image_url")
        if not isinstance(image_url, str) or not image_url:
            _raise(
                f"{param}.image_url",
                "responses_input_image_url_invalid",
                "Responses image input requires a non-empty image_url string.",
            )
        detail = part.get("detail")
        if detail is not None and (
            not isinstance(detail, str) or detail not in _IMAGE_DETAIL_VALUES
        ):
            _raise(
                f"{param}.detail",
                "responses_input_image_detail_invalid",
                "Responses image detail must be auto, low, high, or original.",
            )
        url_bytes, data_url_bytes = self._validate_input_image_url(
            image_url,
            param=f"{param}.image_url",
        )
        canonical_part = {"type": "input_image", "image_url": image_url}
        if detail is not None:
            canonical_part["detail"] = detail
        return canonical_part, url_bytes, data_url_bytes

    def _validate_input_image_url(self, value: str, *, param: str) -> tuple[int, int]:
        if value.startswith(_IMAGE_DATA_URL_PREFIX):
            data_url_bytes = self._validate_input_image_data_url(value, param=param)
            return data_url_bytes, data_url_bytes
        url_bytes = len(value.encode("utf-8"))
        self._validate_string_bytes(
            value,
            param=param,
            max_bytes=self._settings.RESPONSES_MAX_IMAGE_URL_BYTES,
            code="responses_input_image_url_too_large",
        )
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            _raise(
                param,
                "responses_input_image_url_invalid",
                "Responses image URLs must use fully qualified http or https URLs.",
            )
        if parsed.username is not None or parsed.password is not None:
            _raise(
                param,
                "responses_input_image_url_invalid",
                "Responses image URLs must not include embedded credentials.",
            )
        if parsed.fragment:
            _raise(
                param,
                "responses_input_image_url_invalid",
                "Responses image URLs must not include fragments.",
            )
        return url_bytes, 0

    def _validate_input_image_data_url(self, value: str, *, param: str) -> int:
        self._validate_string_bytes(
            value,
            param=param,
            max_bytes=self._settings.RESPONSES_MAX_IMAGE_DATA_URL_BYTES,
            code="responses_input_image_data_url_too_large",
        )
        header, separator, encoded = value.partition(",")
        if not separator:
            _raise(
                param,
                "responses_input_image_url_invalid",
                "Responses image data URLs must be base64 data URLs.",
            )
        if not header.endswith(_IMAGE_DATA_URL_BASE64_SUFFIX):
            _raise(
                param,
                "responses_input_image_url_invalid",
                "Responses image data URLs must use base64 encoding.",
            )
        mime_type = header[
            len(_IMAGE_DATA_URL_PREFIX) : -len(_IMAGE_DATA_URL_BASE64_SUFFIX)
        ].lower()
        if mime_type not in _allowed_responses_image_mime_types(self._settings):
            _raise(
                param,
                "responses_input_image_mime_not_supported",
                "The Responses image data URL MIME type is not supported by this gateway.",
            )
        normalized = "".join(encoded.split())
        if not normalized or len(normalized) % 4 != 0 or not _BASE64_CHARS_RE.fullmatch(normalized):
            _raise(
                param,
                "responses_input_image_url_invalid",
                "Responses image data URLs must include valid base64 data.",
            )
        try:
            base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ResponsesRequestPolicyError(
                "Responses image data URLs must include valid base64 data.",
                param=param,
                error_code="responses_input_image_url_invalid",
            ) from exc
        return len(value.encode("utf-8"))

    def _validate_input_file_part(
        self,
        part: Mapping[str, Any],
        *,
        param: str,
        role: str,
    ) -> tuple[dict[str, str], int, int]:
        if role != "user":
            _raise(
                f"{param}.type",
                "responses_input_file_part_invalid",
                "Responses file input content parts are supported only on user messages.",
            )
        unknown = set(part) - _SUPPORTED_INPUT_FILE_PART_FIELDS - {"file_id"}
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_input_file_part_invalid",
                "This Responses file input field is not enabled by this gateway.",
            )
        if "file_id" in part:
            _raise(
                f"{param}.file_id",
                "responses_input_file_id_not_supported",
                "Responses file IDs are not enabled by this gateway.",
            )

        has_file_url = "file_url" in part
        has_file_data = "file_data" in part
        if has_file_url == has_file_data:
            _raise(
                param,
                "responses_input_file_source_invalid",
                "Responses file input requires exactly one supported file source.",
            )

        if has_file_url:
            file_url = part.get("file_url")
            if not isinstance(file_url, str) or not file_url:
                _raise(
                    f"{param}.file_url",
                    "responses_input_file_url_invalid",
                    "Responses file input requires a non-empty file_url string.",
                )
            if "filename" in part:
                _raise(
                    f"{param}.filename",
                    "responses_input_file_source_invalid",
                    "Responses file_url input must not include filename.",
                )
            url_bytes = self._validate_input_file_url(file_url, param=f"{param}.file_url")
            return {"type": "input_file", "file_url": file_url}, url_bytes, 0

        filename = part.get("filename")
        if not isinstance(filename, str) or not filename:
            _raise(
                f"{param}.filename",
                "responses_input_file_name_invalid",
                "Responses inline file input requires a non-empty safe filename.",
            )
        canonical_filename = self._validate_input_file_name(
            filename,
            param=f"{param}.filename",
        )

        file_data = part.get("file_data")
        if not isinstance(file_data, str) or not file_data:
            _raise(
                f"{param}.file_data",
                "responses_input_file_data_invalid",
                "Responses inline file input requires a non-empty file_data data URL.",
            )
        data_url_bytes = self._validate_input_file_data_url(
            file_data,
            param=f"{param}.file_data",
        )
        return (
            {
                "type": "input_file",
                "filename": canonical_filename,
                "file_data": file_data,
            },
            data_url_bytes + len(canonical_filename.encode("utf-8")),
            data_url_bytes,
        )

    def _validate_input_file_url(self, value: str, *, param: str) -> int:
        url_bytes = len(value.encode("utf-8"))
        self._validate_string_bytes(
            value,
            param=param,
            max_bytes=self._settings.RESPONSES_MAX_FILE_URL_BYTES,
            code="responses_input_file_url_too_large",
        )
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            _raise(
                param,
                "responses_input_file_url_invalid",
                "Responses file URLs must use fully qualified https URLs.",
            )
        if parsed.username is not None or parsed.password is not None:
            _raise(
                param,
                "responses_input_file_url_invalid",
                "Responses file URLs must not include embedded credentials.",
            )
        if parsed.fragment:
            _raise(
                param,
                "responses_input_file_url_invalid",
                "Responses file URLs must not include fragments.",
            )
        path = parsed.path.lower()
        allowed_extensions = _allowed_responses_file_extensions(self._settings)
        if allowed_extensions and not any(
            path.endswith(extension) for extension in allowed_extensions
        ):
            _raise(
                param,
                "responses_input_file_extension_not_supported",
                "The Responses file URL extension is not supported by this gateway.",
            )
        return url_bytes

    def _validate_input_file_name(self, value: str, *, param: str) -> str:
        self._validate_string_bytes(
            value,
            param=param,
            max_bytes=self._settings.RESPONSES_MAX_FILE_NAME_BYTES,
            code="responses_input_file_name_invalid",
        )
        if (
            "/" in value
            or "\\" in value
            or "\x00" in value
            or "?" in value
            or "#" in value
            or any(ord(ch) < 32 for ch in value)
        ):
            _raise(
                param,
                "responses_input_file_name_invalid",
                "Responses inline file input requires a safe basename filename.",
            )
        lowered = value.lower()
        if any(marker in lowered for marker in ("sk-", "bearer", "token", "secret", "password")):
            _raise(
                param,
                "responses_input_file_name_invalid",
                "Responses inline file input requires a safe basename filename.",
            )
        allowed_extensions = _allowed_responses_file_extensions(self._settings)
        if allowed_extensions and not any(
            lowered.endswith(extension) for extension in allowed_extensions
        ):
            _raise(
                param,
                "responses_input_file_extension_not_supported",
                "The Responses file extension is not supported by this gateway.",
            )
        return value

    def _validate_input_file_data_url(self, value: str, *, param: str) -> int:
        self._validate_string_bytes(
            value,
            param=param,
            max_bytes=self._settings.RESPONSES_MAX_FILE_DATA_URL_BYTES,
            code="responses_input_file_data_url_too_large",
        )
        header, separator, encoded = value.partition(",")
        if not separator:
            _raise(
                param,
                "responses_input_file_data_invalid",
                "Responses file data URLs must be base64 data URLs.",
            )
        if not header.startswith(_FILE_DATA_URL_PREFIX):
            _raise(
                param,
                "responses_input_file_data_invalid",
                "Responses file data URLs must be base64 data URLs.",
            )
        if not header.endswith(_FILE_DATA_URL_BASE64_SUFFIX):
            _raise(
                param,
                "responses_input_file_data_invalid",
                "Responses file data URLs must use base64 encoding.",
            )
        mime_type = header[len(_FILE_DATA_URL_PREFIX) : -len(_FILE_DATA_URL_BASE64_SUFFIX)].lower()
        if mime_type not in _allowed_responses_file_mime_types(self._settings):
            _raise(
                param,
                "responses_input_file_mime_not_supported",
                "The Responses file data URL MIME type is not supported by this gateway.",
            )
        normalized = "".join(encoded.split())
        if not normalized or len(normalized) % 4 != 0 or not _BASE64_CHARS_RE.fullmatch(normalized):
            _raise(
                param,
                "responses_input_file_data_invalid",
                "Responses file data URLs must include valid base64 data.",
            )
        try:
            base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ResponsesRequestPolicyError(
                "Responses file data URLs must include valid base64 data.",
                param=param,
                error_code="responses_input_file_data_invalid",
            ) from exc
        return len(value.encode("utf-8"))

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

    def _validate_storage_fields(self, body: dict[str, Any], *, allow_store: bool) -> None:
        if "stream" in body and (
            body.get("stream") is not None and not isinstance(body.get("stream"), bool)
        ):
            _raise(
                "stream",
                "responses_field_invalid_type",
                "The 'stream' field must be a boolean when provided.",
            )
        store = body.get("store")
        if store is True and not allow_store:
            raise ResponsesRequestPolicyError(
                "Provider-side Responses storage is not enabled by this gateway.",
                param="store",
                error_code="responses_store_not_supported",
            )
        if store is True and body.get("stream") is True:
            raise ResponsesRequestPolicyError(
                "Streaming stored Responses are not enabled by this gateway.",
                param="stream",
                error_code="responses_stored_response_streaming_not_supported",
            )
        if "store" in body and store not in (None, False, True):
            _raise(
                "store",
                "responses_field_invalid_type",
                "The 'store' field must be a boolean when provided.",
            )
        body["store"] = store is True

        service_tier = body.get("service_tier")
        if service_tier not in (None, "auto"):
            _raise(
                "service_tier",
                "responses_service_tier_not_supported",
                "Non-default Responses service tiers are not enabled by this gateway.",
            )

    def _validate_scalar_controls(self, body: Mapping[str, Any]) -> None:
        self._validate_number_range(
            body.get("temperature"), param="temperature", minimum=0, maximum=2
        )
        self._validate_number_range(body.get("top_p"), param="top_p", minimum=0, maximum=1)
        if "max_tool_calls" in body:
            value = body.get("max_tool_calls")
            if type(value) is not int or value <= 0:
                _raise(
                    "max_tool_calls",
                    "responses_external_tool_invalid",
                    "The hosted tool call limit must be a positive integer.",
                )

    def _validate_input_token_count_controls(self, body: Mapping[str, Any]) -> None:
        parallel_tool_calls = body.get("parallel_tool_calls")
        if parallel_tool_calls is not None and not isinstance(parallel_tool_calls, bool):
            _raise(
                "parallel_tool_calls",
                "responses_field_invalid_type",
                "The 'parallel_tool_calls' field must be a boolean when provided.",
            )
        truncation = body.get("truncation")
        if truncation is not None and truncation not in {"auto", "disabled"}:
            _raise(
                "truncation",
                "responses_field_value_not_supported",
                "The 'truncation' field must be 'auto' or 'disabled' when provided.",
            )

    def _validate_previous_response_id(self, body: Mapping[str, Any]) -> None:
        if "previous_response_id" not in body:
            return
        value = body.get("previous_response_id")
        if not isinstance(value, str) or not value:
            _raise(
                "previous_response_id",
                "responses_previous_response_id_invalid",
                "The 'previous_response_id' field must be a non-empty string.",
            )
        self._validate_string_bytes(
            value,
            param="previous_response_id",
            max_bytes=self._settings.RESPONSES_MAX_PREVIOUS_RESPONSE_ID_BYTES,
            code="responses_previous_response_id_too_large",
        )
        if any(ord(char) < 32 for char in value):
            _raise(
                "previous_response_id",
                "responses_previous_response_id_invalid",
                "The 'previous_response_id' field contains unsupported characters.",
            )

    def _validate_conversation(self, body: Mapping[str, Any]) -> None:
        if "conversation" not in body:
            return
        value = body.get("conversation")
        if not isinstance(value, str) or not value:
            _raise(
                "conversation",
                "responses_conversation_invalid",
                "The 'conversation' field must be a non-empty string provider conversation ID.",
            )
        self._validate_string_bytes(
            value,
            param="conversation",
            max_bytes=self._settings.RESPONSES_MAX_CONVERSATION_ID_BYTES,
            code="responses_conversation_too_large",
        )
        if any(ord(char) < 32 for char in value):
            _raise(
                "conversation",
                "responses_conversation_invalid",
                "The 'conversation' field contains unsupported characters.",
            )

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

    def _validate_text_config(
        self,
        value: Any,
        *,
        stream: Any,
        allow_codex_request_envelope: bool = False,
    ) -> None:
        if value is None:
            return
        if not isinstance(value, Mapping):
            _raise(
                "text",
                "responses_field_invalid_type",
                "The 'text' field must be an object.",
            )
        allowed_fields = {"format"}
        if allow_codex_request_envelope:
            allowed_fields.add("verbosity")
        unknown = set(value) - allowed_fields
        if unknown:
            _raise(
                f"text.{sorted(unknown)[0]}",
                "responses_field_not_supported",
                "This Responses text configuration field is not enabled by this gateway.",
            )
        if "verbosity" in value:
            verbosity = value.get("verbosity")
            if verbosity not in self._codex_spec.text_verbosities:
                _raise(
                    "text.verbosity",
                    "responses_codex_envelope_invalid",
                    "The Responses text verbosity is not supported.",
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

    def _validate_codex_request_envelope(
        self,
        body: dict[str, Any],
        *,
        allow_codex_request_envelope: bool,
    ) -> None:
        if not allow_codex_request_envelope:
            return

        if "include" in body:
            include = body.get("include")
            if not isinstance(include, list) or not include:
                _raise(
                    "include",
                    "responses_codex_envelope_invalid",
                    "The Codex include field must contain the supported value.",
                )
            if len(include) > self._codex_spec.max_include_items:
                _raise(
                    "include",
                    "responses_codex_envelope_invalid",
                    "The Codex include field contains too many values.",
                )
            if any(item != self._codex_spec.include_value for item in include):
                _raise(
                    "include",
                    "responses_codex_envelope_invalid",
                    "The Codex include field contains an unsupported value.",
                )
            body["include"] = [self._codex_spec.include_value]

        if "parallel_tool_calls" in body and not isinstance(body.get("parallel_tool_calls"), bool):
            _raise(
                "parallel_tool_calls",
                "responses_codex_envelope_invalid",
                "The Codex parallel_tool_calls field must be a boolean.",
            )

        if "prompt_cache_key" in body:
            prompt_cache_key = body.get("prompt_cache_key")
            if not isinstance(prompt_cache_key, str) or not prompt_cache_key:
                _raise(
                    "prompt_cache_key",
                    "responses_codex_envelope_invalid",
                    "The Codex prompt_cache_key field must be a non-empty string.",
                )
            if _contains_control_character(prompt_cache_key):
                _raise(
                    "prompt_cache_key",
                    "responses_codex_envelope_invalid",
                    "The Codex prompt_cache_key field contains unsupported characters.",
                )
            self._validate_string_bytes(
                prompt_cache_key,
                param="prompt_cache_key",
                max_bytes=self._codex_spec.max_prompt_cache_key_bytes,
                code="responses_codex_envelope_invalid",
            )

        if "reasoning" in body:
            reasoning = body.get("reasoning")
            if not isinstance(reasoning, Mapping):
                _raise(
                    "reasoning",
                    "responses_codex_envelope_invalid",
                    "The Codex reasoning field must be an object.",
                )
            unknown = set(reasoning) - {"context", "effort"}
            if unknown:
                _raise(
                    "reasoning",
                    "responses_codex_envelope_invalid",
                    "The Codex reasoning field contains an unsupported member.",
                )
            if not reasoning:
                _raise(
                    "reasoning",
                    "responses_codex_envelope_invalid",
                    "The Codex reasoning field must not be empty.",
                )
            if "effort" not in reasoning:
                _raise(
                    "reasoning.effort",
                    "responses_codex_envelope_invalid",
                    "The Codex reasoning effort is required.",
                )
            canonical_reasoning: dict[str, str] = {}
            effort = reasoning.get("effort")
            if effort not in self._codex_spec.reasoning_efforts:
                _raise(
                    "reasoning.effort",
                    "responses_codex_envelope_invalid",
                    "The Codex reasoning effort is not supported.",
                )
            canonical_reasoning["effort"] = str(effort)
            if "context" in reasoning:
                context = reasoning.get("context")
                if context != self._codex_spec.reasoning_context:
                    _raise(
                        "reasoning.context",
                        "responses_codex_envelope_invalid",
                        "The Codex reasoning context is not supported.",
                    )
                canonical_reasoning["context"] = self._codex_spec.reasoning_context
            if len(canonical_json_bytes(canonical_reasoning)) > self._codex_spec.max_reasoning_bytes:
                _raise(
                    "reasoning",
                    "responses_codex_envelope_invalid",
                    "The Codex reasoning field exceeds the gateway size limit.",
                )
            body["reasoning"] = canonical_reasoning

        if "client_metadata" in body:
            self._validate_and_drop_codex_client_metadata(body)

        text = body.get("text")
        if isinstance(text, Mapping):
            body["text"] = {
                field: copy.deepcopy(text[field])
                for field in ("format", "verbosity")
                if field in text
            }

    def _validate_and_drop_codex_client_metadata(self, body: dict[str, Any]) -> None:
        metadata = body.get("client_metadata")
        if not isinstance(metadata, Mapping):
            _raise(
                "client_metadata",
                "responses_codex_envelope_invalid",
                "The Codex client_metadata field must be an object.",
            )
        if len(metadata) > self._codex_spec.max_client_metadata_keys:
            _raise(
                "client_metadata",
                "responses_codex_envelope_invalid",
                "The Codex client_metadata field contains too many keys.",
            )
        for key, value in metadata.items():
            if not isinstance(key, str) or key not in self._codex_spec.client_metadata_keys:
                _raise(
                    "client_metadata",
                    "responses_codex_envelope_invalid",
                    "The Codex client_metadata field contains an unsupported key.",
                )
            if len(key.encode("utf-8")) > self._codex_spec.max_client_metadata_key_bytes:
                _raise(
                    "client_metadata",
                    "responses_codex_envelope_invalid",
                    "The Codex client_metadata key exceeds the gateway size limit.",
                )
            if not isinstance(value, str):
                _raise(
                    f"client_metadata.{key}",
                    "responses_codex_envelope_invalid",
                    "Codex client_metadata values must be strings.",
                )
            if _contains_control_character(value):
                _raise(
                    f"client_metadata.{key}",
                    "responses_codex_envelope_invalid",
                    "A Codex client_metadata value contains unsupported characters.",
                )
            if len(value.encode("utf-8")) > self._codex_spec.max_client_metadata_value_bytes:
                _raise(
                    f"client_metadata.{key}",
                    "responses_codex_envelope_invalid",
                    "A Codex client_metadata value exceeds the gateway size limit.",
                )
        if len(canonical_json_bytes(dict(metadata))) > self._codex_spec.max_client_metadata_bytes:
            _raise(
                "client_metadata",
                "responses_codex_envelope_invalid",
                "The Codex client_metadata field exceeds the gateway size limit.",
            )
        body.pop("client_metadata", None)

    def _validate_codex_message_id(self, value: Any, *, param: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 128:
            _raise(
                param,
                "responses_codex_envelope_invalid",
                "The Codex message item ID is invalid.",
            )
        if not value.isascii() or not self._codex_spec.message_id_pattern.fullmatch(value):
            _raise(
                param,
                "responses_codex_envelope_invalid",
                "The Codex message item ID contains unsupported characters.",
            )
        if "://" in value or _looks_secret_like_identifier(value):
            _raise(
                param,
                "responses_codex_envelope_invalid",
                "The Codex message item ID is not an approved opaque identifier.",
            )
        return value

    def _validate_tools(
        self,
        body: dict[str, Any],
        *,
        allow_external_tool_request: bool = False,
        allow_codex_client_tools: bool = False,
        adapter_managed_declaration_candidates: frozenset[str] = frozenset(),
        adapter_managed_declaration_shapes: Mapping[str, frozenset[str]] | None = None,
    ) -> int:
        value = body.get("tools")
        if value is None:
            return 0
        if not isinstance(value, list):
            _raise(
                "tools",
                "responses_tool_invalid_shape",
                "The 'tools' field must be a list of local Responses tools.",
            )
        if not value:
            _raise(
                "tools",
                "responses_tool_invalid_shape",
                "The 'tools' field must contain at least one local tool when provided.",
            )
        if len(value) > self._settings.RESPONSES_MAX_TOOLS_PER_REQUEST:
            _raise(
                "tools",
                "responses_tool_count_exceeded",
                "The Responses tools array has too many entries.",
            )

        canonical_tools: list[dict[str, Any]] = []
        total_function_schema_bytes = 0
        total_custom_format_bytes = 0
        function_tools_count = 0
        custom_tools_count = 0
        seen_names: set[str] = set()
        for index, tool in enumerate(value):
            if (
                isinstance(tool, Mapping)
                and isinstance(tool.get("type"), str)
                and tool.get("type") in adapter_managed_declaration_candidates
            ):
                tool_type = tool.get("type")
                expected_fields = (adapter_managed_declaration_shapes or {}).get(tool_type)
                if not isinstance(tool_type, str) or expected_fields is None:
                    _raise(
                        f"tools[{index}]",
                        "responses_adapter_managed_tool_invalid",
                        "This adapter-managed tool declaration is not enabled.",
                    )
                if set(tool) != expected_fields:
                    _raise(
                        f"tools[{index}]",
                        "responses_adapter_managed_tool_invalid",
                        "This adapter-managed tool declaration has an unrecognized shape.",
                    )
                self._validate_adapter_managed_tool(tool, param=f"tools[{index}]")
                canonical_tools.append(copy.deepcopy(dict(tool)))
                continue
            if allow_external_tool_request and isinstance(tool, Mapping) and tool.get("type") == "web_search":
                allowed_fields = {"type", "search_context_size"}
                if set(tool) - allowed_fields:
                    _raise(
                        f"tools[{index}]",
                        "responses_external_tool_invalid",
                        "The hosted web-search declaration contains unsupported fields.",
                    )
                context = tool.get("search_context_size")
                if context is not None and context not in {"low", "medium", "high"}:
                    _raise(
                        f"tools[{index}].search_context_size",
                        "responses_external_tool_invalid",
                        "The hosted web-search context size is invalid.",
                    )
                canonical_tools.append(
                    {"type": "web_search", **({"search_context_size": context} if context is not None else {})}
                )
                continue
            canonical_tool, schema_bytes, format_bytes = self._validate_local_tool(
                tool,
                param=f"tools[{index}]",
                allow_namespace=allow_codex_client_tools,
            )
            name = canonical_tool["name"]
            if name in seen_names:
                _raise(
                    f"tools[{index}].name",
                    "responses_tool_invalid_shape",
                    "Responses local tool names must be unique.",
                )
            seen_names.add(name)
            if canonical_tool["type"] == "function":
                function_tools_count += 1
                if function_tools_count > self._settings.RESPONSES_MAX_FUNCTION_TOOLS_PER_REQUEST:
                    _raise(
                        "tools",
                        "responses_tool_count_exceeded",
                        "The Responses function tools array has too many entries.",
                    )
                total_function_schema_bytes += schema_bytes
            elif canonical_tool["type"] == "custom":
                custom_tools_count += 1
                if custom_tools_count > self._settings.RESPONSES_MAX_CUSTOM_TOOLS_PER_REQUEST:
                    _raise(
                        "tools",
                        "responses_tool_count_exceeded",
                        "The Responses custom tools array has too many entries.",
                    )
                total_custom_format_bytes += format_bytes
            if (
                total_function_schema_bytes
                > self._settings.RESPONSES_MAX_TOTAL_FUNCTION_TOOL_SCHEMA_BYTES
            ):
                _raise(
                    "tools",
                    "responses_function_tool_schema_too_large",
                    "The total Responses function tool schema size exceeds the gateway limit.",
                )
            if (
                total_custom_format_bytes
                > self._settings.RESPONSES_MAX_TOTAL_CUSTOM_TOOL_FORMAT_BYTES
            ):
                _raise(
                    "tools",
                    "responses_custom_tool_format_too_large",
                    "The total Responses custom tool format size exceeds the gateway limit.",
                )
            canonical_tools.append(canonical_tool)

        body["tools"] = canonical_tools
        return len(canonical_json_bytes({"tools": canonical_tools}))

    def _validate_adapter_managed_tool(
        self,
        tool: Mapping[str, Any],
        *,
        param: str,
    ) -> None:
        """Validate observed client candidates without granting provider authority."""
        tool_type = tool.get("type")
        if tool_type == "tool_search":
            description = tool.get("description")
            execution = tool.get("execution")
            parameters = tool.get("parameters")
            if (
                not isinstance(description, str)
                or not isinstance(execution, str)
                or _ADAPTER_MANAGED_TOOL_TOKEN.fullmatch(execution) is None
                or not isinstance(parameters, Mapping)
            ):
                _raise(
                    param,
                    "responses_adapter_managed_tool_invalid",
                    "The captured tool_search declaration has invalid field types.",
                )
            self._validate_string_bytes(
                description,
                param=f"{param}.description",
                max_bytes=self._settings.RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES,
                code="responses_adapter_managed_tool_invalid",
            )
            self._validate_json_bytes(
                parameters,
                param=f"{param}.parameters",
                max_bytes=self._settings.RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES,
                too_large_code="responses_adapter_managed_tool_invalid",
                invalid_code="responses_adapter_managed_tool_invalid",
                field_label="Adapter-managed tool_search parameters",
            )
        elif tool_type == "web_search":
            external_web_access = tool.get("external_web_access")
            search_content_types = tool.get("search_content_types")
            if (
                not isinstance(external_web_access, bool)
                or not isinstance(search_content_types, list)
                or not search_content_types
                or len(search_content_types) > 8
                or not all(
                    isinstance(item, str)
                    and _ADAPTER_MANAGED_TOOL_TOKEN.fullmatch(item) is not None
                    for item in search_content_types
                )
            ):
                _raise(
                    param,
                    "responses_adapter_managed_tool_invalid",
                    "The captured web_search declaration has invalid field types.",
                )
        else:
            _raise(
                param,
                "responses_adapter_managed_tool_invalid",
                "This adapter-managed tool type is not enabled.",
            )
        nested = dict(tool)
        nested.pop("type", None)
        if _contains_recursive_codex_authority_marker(nested) or _contains_unsafe_adapter_value(
            nested
        ):
            _raise(
                param,
                "responses_adapter_managed_tool_authority_not_supported",
                "Adapter-managed tool declarations cannot contain provider authority.",
            )

    def _validate_local_tool(
        self,
        tool: Any,
        *,
        param: str,
        description_max_bytes: int | None = None,
        allow_namespace: bool = False,
    ) -> tuple[dict[str, Any], int, int]:
        if not isinstance(tool, Mapping):
            _raise(
                param,
                "responses_tool_invalid_shape",
                "Responses tools must be local tool objects.",
            )
        tool_type = tool.get("type")
        if tool_type == "function":
            canonical_tool, schema_bytes = self._validate_function_tool(
                tool,
                param=param,
                description_max_bytes=description_max_bytes,
            )
            return canonical_tool, schema_bytes, 0
        if tool_type == "custom":
            canonical_tool, format_bytes = self._validate_custom_tool(
                tool,
                param=param,
                description_max_bytes=description_max_bytes,
            )
            return canonical_tool, 0, format_bytes
        if tool_type == "namespace":
            if not allow_namespace:
                code = (
                    "responses_hosted_tool_not_supported"
                    if tool_type in _HOSTED_TOOL_TYPES
                    else "responses_tool_type_not_supported"
                )
                raise ResponsesRequestPolicyError(
                    "Only local Responses function and custom tools are enabled by this gateway.",
                    param=f"{param}.type",
                    error_code=code,
                )
            canonical_tool = self._validate_namespace_tool(tool, param=param)
            return canonical_tool, 0, 0

        code = (
            "responses_hosted_tool_not_supported"
            if tool_type in _HOSTED_TOOL_TYPES
            else "responses_tool_type_not_supported"
        )
        if tool_type == "mcp" or _contains_provider_authority_marker(tool):
            code = "responses_mcp_not_supported"
        raise ResponsesRequestPolicyError(
            "Only local Responses function and custom tools are enabled by this gateway.",
            param=f"{param}.type",
            error_code=code,
        )

    def _validate_namespace_tool(self, tool: Any, *, param: str) -> dict[str, Any]:
        """Validate a Codex client-side namespace tool declaration."""

        allowed_fields = {"type", "name", "description", "tools"}
        unknown = set(tool) - allowed_fields
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_namespace_tool_invalid",
                "Namespace tool declaration contains unsupported fields.",
            )
        name = tool.get("name")
        if not isinstance(name, str) or not name or len(name.encode("utf-8")) > 256:
            _raise(f"{param}.name", "responses_namespace_tool_invalid", "Invalid namespace tool name.")
        nested_tools = tool.get("tools")
        if not isinstance(nested_tools, list) or len(nested_tools) > 128:
            _raise(f"{param}.tools", "responses_namespace_tool_invalid", "Invalid namespace tools list.")
        for index, nested in enumerate(nested_tools):
            if not isinstance(nested, Mapping) or nested.get("type") not in {"function", "custom"}:
                _raise(f"{param}.tools[{index}]", "responses_namespace_tool_invalid", "Invalid namespace nested tool.")
        return {
            "type": "namespace",
            "name": name,
            "description": tool.get("description", ""),
            "tools": copy.deepcopy(nested_tools),
        }

    def _validate_function_tool(
        self,
        tool: Any,
        *,
        param: str,
        description_max_bytes: int | None = None,
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
                max_bytes=(
                    description_max_bytes
                    if description_max_bytes is not None
                    else self._settings.RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES
                ),
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

    def _validate_custom_tool(
        self,
        tool: Mapping[str, Any],
        *,
        param: str,
        description_max_bytes: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        if _contains_provider_authority_marker(tool):
            _raise(
                param,
                "responses_mcp_not_supported",
                "Provider-side tool authority markers are not enabled by this gateway.",
            )
        unknown = set(tool) - _SUPPORTED_CUSTOM_TOOL_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_tool_invalid_shape",
                "This Responses custom tool field is not enabled by this gateway.",
            )

        name = tool.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                f"{param}.name",
                "responses_tool_invalid_shape",
                "Responses custom tools require a non-empty name.",
            )
        if not _CUSTOM_TOOL_NAME_PATTERN.fullmatch(name):
            _raise(
                f"{param}.name",
                "responses_tool_invalid_shape",
                "Responses custom tool names use unsupported characters.",
            )
        self._validate_string_bytes(
            name,
            param=f"{param}.name",
            max_bytes=self._settings.RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES,
            code="responses_tool_invalid_shape",
        )

        canonical_tool: dict[str, Any] = {"type": "custom", "name": name}

        description = tool.get("description")
        if description is not None:
            if not isinstance(description, str):
                _raise(
                    f"{param}.description",
                    "responses_tool_invalid_shape",
                    "Responses custom tool descriptions must be strings.",
                )
            self._validate_string_bytes(
                description,
                param=f"{param}.description",
                max_bytes=(
                    description_max_bytes
                    if description_max_bytes is not None
                    else self._settings.RESPONSES_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES
                ),
                code="responses_tool_invalid_shape",
            )
            canonical_tool["description"] = description

        format_bytes = 0
        if "format" in tool:
            canonical_format, format_bytes = self._validate_custom_tool_format(
                tool.get("format"),
                param=f"{param}.format",
            )
            canonical_tool["format"] = canonical_format
        return canonical_tool, format_bytes

    def _validate_custom_tool_format(
        self,
        value: Any,
        *,
        param: str,
    ) -> tuple[dict[str, str], int]:
        if not isinstance(value, Mapping):
            _raise(
                param,
                "responses_tool_invalid_shape",
                "Responses custom tool format must be an object.",
            )
        format_type = value.get("type")
        if format_type not in _CUSTOM_TOOL_FORMAT_TYPES:
            _raise(
                f"{param}.type",
                "responses_custom_tool_format_not_supported",
                "This Responses custom tool format type is not enabled by this gateway.",
            )
        if format_type == "text":
            unknown = set(value) - _SUPPORTED_CUSTOM_TOOL_TEXT_FORMAT_FIELDS
            if unknown:
                _raise(
                    f"{param}.{sorted(unknown)[0]}",
                    "responses_tool_invalid_shape",
                    "This Responses custom text format field is not enabled by this gateway.",
                )
            canonical_format = {"type": "text"}
            return canonical_format, len(canonical_json_bytes(canonical_format))

        unknown = set(value) - _SUPPORTED_CUSTOM_TOOL_GRAMMAR_FORMAT_FIELDS
        if unknown:
            _raise(
                f"{param}.{sorted(unknown)[0]}",
                "responses_tool_invalid_shape",
                "This Responses custom grammar format field is not enabled by this gateway.",
            )
        syntax = value.get("syntax")
        if syntax not in _CUSTOM_TOOL_GRAMMAR_SYNTAXES:
            _raise(
                f"{param}.syntax",
                "responses_custom_tool_format_not_supported",
                "This Responses custom grammar syntax is not enabled by this gateway.",
            )
        definition = value.get("definition")
        if not isinstance(definition, str) or not definition:
            _raise(
                f"{param}.definition",
                "responses_tool_invalid_shape",
                "Responses custom grammar format requires a non-empty definition.",
            )
        self._validate_string_bytes(
            definition,
            param=f"{param}.definition",
            max_bytes=self._settings.RESPONSES_MAX_CUSTOM_TOOL_FORMAT_DEFINITION_BYTES,
            code="responses_custom_tool_format_too_large",
        )
        canonical_format = {
            "type": "grammar",
            "syntax": syntax,
            "definition": definition,
        }
        return canonical_format, len(canonical_json_bytes(canonical_format))

    def _validate_tool_choice(self, body: dict[str, Any]) -> int:
        if "tool_choice" not in body:
            return 0
        value = body.get("tool_choice")
        tools = body.get("tools")
        codex_client_tools = responses_codex_client_tools_requested(body)
        if tools is None and not codex_client_tools:
            _raise(
                "tool_choice",
                "responses_tool_choice_invalid",
                "Responses tool_choice requires local tools in this gateway.",
            )
        if isinstance(value, str):
            if value not in {"none", "auto", "required"}:
                _raise(
                    "tool_choice",
                    "responses_tool_choice_invalid",
                    "Responses tool_choice must be none, auto, required, or a local tool choice.",
                )
            return len(canonical_json_bytes({"tool_choice": value}))
        if codex_client_tools:
            _raise(
                "tool_choice",
                "responses_codex_client_tools_invalid",
                "Codex client tool namespaces allow only none, auto, or required tool_choice.",
            )
        if not isinstance(value, Mapping):
            _raise(
                "tool_choice",
                "responses_tool_choice_invalid",
                "Responses tool_choice must be none, auto, required, or a local tool choice.",
            )
        if _contains_provider_authority_marker(value):
            _raise(
                "tool_choice",
                "responses_mcp_not_supported",
                "Provider-side tool choices are not enabled by this gateway.",
            )
        choice_type = value.get("type")
        if choice_type not in {"function", "custom"}:
            code = (
                "responses_hosted_tool_not_supported"
                if choice_type in _HOSTED_TOOL_TYPES
                else "responses_tool_choice_invalid"
            )
            if choice_type == "mcp":
                code = "responses_mcp_not_supported"
            _raise(
                "tool_choice.type",
                code,
                "Only local Responses function and custom tool choices are enabled by this gateway.",
            )
        supported_fields = (
            _SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS
            if choice_type == "function"
            else _SUPPORTED_CUSTOM_TOOL_CHOICE_FIELDS
        )
        unknown = set(value) - supported_fields
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
                "Responses local tool choices require a non-empty tool name.",
            )
        declared_names = {
            tool["name"]
            for tool in tools
            if isinstance(tool, Mapping) and tool.get("type") == choice_type
        }
        if name not in declared_names:
            _raise(
                "tool_choice.name",
                "responses_tool_choice_invalid",
                "Responses tool_choice must reference a declared local tool of the same type.",
            )
        canonical_choice = {"type": choice_type, "name": name}
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

    def _resolve_output_token_limit(
        self,
        body: dict[str, Any],
        *,
        hard_max: int | None = None,
    ) -> tuple[int, bool]:
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
        effective_hard_max = hard_max or self._settings.HARD_MAX_OUTPUT_TOKENS
        if value > effective_hard_max:
            _raise(
                "max_output_tokens",
                "output_token_limit_exceeded",
                "The 'max_output_tokens' field exceeds the configured hard maximum.",
            )
        return value, False

    def _estimate_input_tokens(
        self,
        *,
        input_material_bytes: int,
        instructions: str | None,
        body: Mapping[str, Any],
        tools_schema_bytes: int = 0,
        tool_choice_bytes: int = 0,
        codex_client_tool_declaration_bytes: int = 0,
    ) -> tuple[int, int, int, tuple[str, ...]]:
        total_bytes = input_material_bytes
        if instructions is not None:
            total_bytes += len(instructions.encode("utf-8"))
        non_message_bytes = tools_schema_bytes + tool_choice_bytes
        non_message_fields: list[str] = []
        if tools_schema_bytes:
            non_message_fields.append("tools")
        if tool_choice_bytes:
            non_message_fields.append("tool_choice")
        if codex_client_tool_declaration_bytes:
            non_message_bytes += codex_client_tool_declaration_bytes
            non_message_fields.append("input[].additional_tools")
        for field in ("include", "parallel_tool_calls", "prompt_cache_key", "reasoning", "text"):
            if field in body and body[field] is not None:
                non_message_bytes += len(canonical_json_bytes({field: body[field]}))
                non_message_fields.append(field)
        message_id_bytes = _message_id_estimation_bytes(body.get("input"))
        if message_id_bytes:
            non_message_bytes += message_id_bytes
            non_message_fields.append("input[].id")
        total_bytes += non_message_bytes
        estimated_input_tokens = max(1, (total_bytes + 2) // 3)
        estimated_non_message_input_tokens = (
            (non_message_bytes + 2) // 3 if non_message_bytes else 0
        )
        return (
            estimated_input_tokens,
            estimated_non_message_input_tokens,
            non_message_bytes,
            tuple(non_message_fields),
        )

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


def apply_codex_route_limits(
    policy_result: ResponsesPolicyResult,
    *,
    route_capabilities: Mapping[str, object] | None,
    settings: Settings,
    include_output_field: bool = True,
    reserve_route_max_output: bool = False,
) -> ResponsesPolicyResult:
    """Finalize fully gated Codex limits after route resolution and before side effects."""

    limits = parse_codex_route_limits(route_capabilities)
    if limits.default_max_output_tokens > settings.CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS:
        _raise(
            "model",
            "responses_codex_limits_invalid",
            "The route Codex output default exceeds the operator ceiling.",
        )
    if reserve_route_max_output:
        output_tokens = limits.max_output_tokens
    elif policy_result.injected_default_output_tokens:
        output_tokens = limits.default_max_output_tokens
    else:
        output_tokens = policy_result.requested_output_tokens
    if output_tokens > limits.max_output_tokens:
        _raise(
            "max_output_tokens",
            "output_token_limit_exceeded",
            "The Codex output limit exceeds the selected model route maximum.",
        )
    if output_tokens > settings.CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS:
        _raise(
            "max_output_tokens",
            "output_token_limit_exceeded",
            "The Codex output limit exceeds the configured operator maximum.",
        )
    if policy_result.estimated_input_tokens > settings.CODEX_ABSOLUTE_MAX_INPUT_TOKENS:
        _raise(
            "input",
            "input_token_limit_exceeded",
            "Estimated Codex input exceeds the configured operator maximum.",
        )
    if policy_result.estimated_input_tokens + output_tokens > limits.context_window_tokens:
        _raise(
            "input",
            "responses_codex_context_window_exceeded",
            "Estimated Codex input plus output exposure exceeds the route context window.",
        )

    effective_body = copy.deepcopy(policy_result.effective_body)
    if include_output_field:
        effective_body["max_output_tokens"] = output_tokens
    else:
        effective_body.pop("max_output_tokens", None)
    return policy_result.model_copy(
        update={
            "effective_body": effective_body,
            "requested_output_tokens": output_tokens,
            "effective_output_tokens": output_tokens,
            "codex_context_window_tokens": limits.context_window_tokens,
            "codex_limits_applied": True,
        }
    )


def responses_codex_request_envelope_requested(body: Mapping[str, Any]) -> bool:
    """Detect the bounded envelope from body shape only, never headers or model names."""

    if any(
        field in body
        for field in (
            "client_metadata",
            "include",
            "parallel_tool_calls",
            "prompt_cache_key",
            "reasoning",
        )
    ):
        return True
    text = body.get("text")
    if isinstance(text, Mapping) and "verbosity" in text:
        return True
    input_value = body.get("input")
    if isinstance(input_value, list):
        return any(
            isinstance(item, Mapping)
            and (
                (item.get("type") in (None, "message") and "id" in item)
                or (item.get("type") == "reasoning" and "encrypted_content" in item)
                or item.get("type") == "compaction"
            )
            for item in input_value
        )
    return False


def responses_codex_compaction_requested(body: Mapping[str, Any]) -> bool:
    """Detect the pinned Codex V1 compact envelope without model-name inference."""

    if any(
        field in body
        for field in ("tools", "parallel_tool_calls", "reasoning", "prompt_cache_key", "text")
    ):
        return True
    input_value = body.get("input")
    return isinstance(input_value, list) and any(
        isinstance(item, Mapping)
        and item.get("type")
        in {
            "additional_tools",
            "reasoning",
            "function_call",
            "function_call_output",
            "custom_tool_call",
            "custom_tool_call_output",
            "compaction",
        }
        for item in input_value
    )


def _first_codex_compaction_param(body: Mapping[str, Any]) -> str:
    for field in ("tools", "parallel_tool_calls", "reasoning", "prompt_cache_key", "text"):
        if field in body:
            return field
    return "input"


def responses_codex_compaction_replay_requested(body: Mapping[str, Any]) -> bool:
    """Detect an opaque V1 compaction item replay in request history."""

    input_value = body.get("input")
    return isinstance(input_value, list) and any(
        isinstance(item, Mapping) and item.get("type") == "compaction" for item in input_value
    )


def responses_codex_request_envelope_allowed(policy: object) -> bool:
    """Return true only for an explicit, well-formed key capability grant."""

    return _responses_policy_capability_allowed(
        policy,
        RESPONSES_CAPABILITY_CODEX_REQUEST_ENVELOPE,
    )


def responses_codex_client_tools_requested(body: Mapping[str, Any]) -> bool:
    """Detect Codex client tool declarations from input shape only."""

    input_value = body.get("input")
    return isinstance(input_value, list) and any(
        isinstance(item, Mapping) and item.get("type") == "additional_tools" for item in input_value
    )


def responses_codex_encrypted_reasoning_replay_requested(body: Mapping[str, Any]) -> bool:
    """Detect a prior encrypted reasoning item being replayed as request input."""

    input_value = body.get("input")
    return isinstance(input_value, list) and any(
        isinstance(item, Mapping)
        and item.get("type") == "reasoning"
        and "encrypted_content" in item
        for item in input_value
    )


def responses_codex_encrypted_reasoning_output_requested(
    body: Mapping[str, Any],
    *,
    client_spec: ResponsesClientPolicySpec | None = None,
) -> bool:
    """Detect the legacy envelope request for provider encrypted reasoning output."""

    include = body.get("include")
    return (
        client_spec is not None
        and isinstance(include, list)
        and client_spec.include_value in include
    )


def responses_codex_encrypted_reasoning_replay_allowed(policy: object) -> bool:
    """Require independent envelope and encrypted-replay key grants."""

    return responses_codex_request_envelope_allowed(
        policy
    ) and _responses_policy_capability_allowed(
        policy,
        RESPONSES_CAPABILITY_CODEX_ENCRYPTED_REASONING_REPLAY,
    )


def codex_replay_request_candidates(
    body: Mapping[str, Any],
) -> tuple[CodexReplayRequestCandidate | CodexCompactionReplayCandidate, ...]:
    """Extract only validated IDs and approved identities from canonical input."""

    input_value = body.get("input")
    if not isinstance(input_value, list):
        return ()
    declarations = _codex_declarations_from_input_items(
        [dict(item) for item in input_value if isinstance(item, Mapping)]
    )
    candidates: list[CodexReplayRequestCandidate | CodexCompactionReplayCandidate] = []
    for item in input_value:
        if not isinstance(item, Mapping):
            continue
        item_type = item.get("type")
        if item_type == "compaction":
            item_id = item.get("id")
            encrypted_content = item.get("encrypted_content")
            if isinstance(item_id, str) and isinstance(encrypted_content, str):
                candidates.append(
                    CodexCompactionReplayCandidate(
                        item_kind="compaction",
                        item_id=item_id,
                        call_id=None,
                        tool_namespace=None,
                        tool_name=None,
                        encrypted_content=encrypted_content,
                    )
                )
            continue
        if item_type == "reasoning":
            item_id = item.get("id")
            if isinstance(item_id, str):
                candidates.append(
                    CodexReplayRequestCandidate(
                        item_kind="reasoning",
                        item_id=item_id,
                        call_id=None,
                        tool_namespace=None,
                        tool_name=None,
                    )
                )
            continue
        if item_type not in {"function_call", "custom_tool_call"}:
            continue
        item_id = item.get("id")
        call_id = item.get("call_id")
        name = item.get("name")
        tool_type = "custom" if item_type == "custom_tool_call" else "function"
        namespace = item.get("namespace")
        matches = [
            declaration
            for declaration in declarations
            if declaration[1] == name
            and declaration[2] == tool_type
            and (namespace is None or declaration[0] == namespace)
        ]
        if (
            isinstance(item_id, str)
            and isinstance(call_id, str)
            and isinstance(name, str)
            and len(matches) == 1
        ):
            candidates.append(
                CodexReplayRequestCandidate(
                    item_kind=str(item_type),
                    item_id=item_id,
                    call_id=call_id,
                    tool_namespace=matches[0][0],
                    tool_name=name,
                )
            )
    return tuple(candidates)


def responses_codex_client_tools_allowed(policy: object) -> bool:
    """Require independent, well-formed grants for envelope and client tools."""

    return _responses_policy_capability_allowed(
        policy,
        RESPONSES_CAPABILITY_CODEX_REQUEST_ENVELOPE,
    ) and _responses_policy_capability_allowed(
        policy,
        RESPONSES_CAPABILITY_CODEX_CLIENT_TOOLS,
    )


def responses_codex_streaming_tool_events_requested(body: Mapping[str, Any]) -> bool:
    """Detect the streaming declaration or bounded tool-roundtrip request shape."""

    has_namespace_tools = any(
        isinstance(tool, Mapping) and tool.get("type") == "namespace"
        for tool in (body.get("tools") or [])
        if isinstance(body.get("tools"), list)
    )
    input_value = body.get("input")
    if not isinstance(input_value, list):
        return has_namespace_tools and body.get("stream") is True
    item_types = {
        item.get("type")
        for item in input_value
        if isinstance(item, Mapping) and isinstance(item.get("type"), str)
    }
    has_additional_tools = "additional_tools" in item_types
    if not has_additional_tools and not has_namespace_tools:
        return False
    return body.get("stream") is True or bool(
        item_types.intersection(
            {
                "function_call",
                "custom_tool_call",
                "function_call_output",
                "custom_tool_call_output",
            }
        )
    )


def responses_codex_streaming_tool_events_allowed(policy: object) -> bool:
    """Require all three explicit, well-formed Codex key capability grants."""

    return responses_codex_client_tools_allowed(policy) and _responses_policy_capability_allowed(
        policy,
        RESPONSES_CAPABILITY_CODEX_STREAMING_TOOL_EVENTS,
    )


def responses_codex_extended_limits_allowed(policy: object) -> bool:
    """Require the complete pre-compaction Codex key gate set."""

    return responses_codex_streaming_tool_events_allowed(
        policy
    ) and responses_codex_encrypted_reasoning_replay_allowed(policy)


def responses_codex_compaction_allowed(policy: object) -> bool:
    """Require all prior Codex gates plus the independent compaction grant."""

    return responses_codex_extended_limits_allowed(policy) and _responses_policy_capability_allowed(
        policy,
        RESPONSES_CAPABILITY_CODEX_COMPACTION,
    )


def _responses_policy_capability_allowed(policy: object, capability: str) -> bool:
    """Parse the versioned key capability list without accepting partial shapes."""

    if not isinstance(policy, Mapping):
        return False
    version = policy.get("version")
    if isinstance(version, bool) or version != 1:
        return False
    capabilities = policy.get("allowed_capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return False
    if any(
        not isinstance(item, str) or item not in KNOWN_RESPONSES_CAPABILITIES
        for item in capabilities
    ):
        return False
    if len(capabilities) != len(set(capabilities)):
        return False
    return capability in capabilities


def _first_codex_envelope_param(body: Mapping[str, Any]) -> str:
    for field in (
        "client_metadata",
        "include",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
    ):
        if field in body:
            return field
    text = body.get("text")
    if isinstance(text, Mapping) and "verbosity" in text:
        return "text.verbosity"
    input_value = body.get("input")
    if isinstance(input_value, list):
        for index, item in enumerate(input_value):
            if isinstance(item, Mapping) and item.get("type") == "reasoning":
                return f"input[{index}]"
            if isinstance(item, Mapping) and item.get("type") in (None, "message") and "id" in item:
                return f"input[{index}].id"
    return RESPONSES_CAPABILITY_CODEX_REQUEST_ENVELOPE


def _first_codex_encrypted_reasoning_param(body: Mapping[str, Any]) -> str:
    input_value = body.get("input")
    if isinstance(input_value, list):
        for index, item in enumerate(input_value):
            if isinstance(item, Mapping) and item.get("type") == "reasoning":
                return f"input[{index}]"
    return "include"


def _first_codex_client_tools_param(body: Mapping[str, Any]) -> str:
    input_value = body.get("input")
    if isinstance(input_value, list):
        for index, item in enumerate(input_value):
            if isinstance(item, Mapping) and item.get("type") == "additional_tools":
                return f"input[{index}].type"
    return "input"


def _codex_client_tool_declaration_estimation_bytes(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    return sum(
        len(canonical_json_bytes(item))
        for item in value
        if isinstance(item, Mapping) and item.get("type") == "additional_tools"
    )


def codex_client_tool_declarations(
    body: Mapping[str, Any],
) -> frozenset[tuple[str, str, str]]:
    """Return only the canonical namespace/name/type taxonomy from validated input."""

    input_value = body.get("input")
    if not isinstance(input_value, list):
        return frozenset()
    return frozenset(_codex_declarations_from_input_items(input_value))


def _codex_declarations_from_input_items(
    items: list[dict[str, Any]] | list[Any],
) -> set[tuple[str, str, str]]:
    declarations: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping) or item.get("type") != "additional_tools":
            continue
        namespaces = item.get("tools")
        if not isinstance(namespaces, list):
            continue
        for namespace in namespaces:
            if not isinstance(namespace, Mapping) or not isinstance(namespace.get("name"), str):
                continue
            tools = namespace.get("tools")
            if not isinstance(tools, list):
                continue
            for tool in tools:
                if (
                    isinstance(tool, Mapping)
                    and isinstance(tool.get("name"), str)
                    and tool.get("type") in {"function", "custom"}
                ):
                    declarations.add((str(namespace["name"]), str(tool["name"]), str(tool["type"])))
    return declarations


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _looks_secret_like_identifier(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith(("bearer", "ghp_", "github_pat_", "sk-", "sk_")):
        return True
    if any(
        fragment in lowered for fragment in ("api_key", "apikey", "password", "secret", "token")
    ):
        return True
    segments = value.split(".")
    return len(segments) == 3 and all(len(segment) >= 8 for segment in segments)


def _message_id_estimation_bytes(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    return sum(
        len(canonical_json_bytes({"id": item["id"]}))
        for item in value
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
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
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, Mapping) and tool.get("type") == "function":
                return True
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, Mapping) and tool_choice.get("type") == "function":
        return True
    return _input_contains_function_call_output(body.get("input"))


def responses_custom_tools_requested(body: Mapping[str, Any]) -> bool:
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, Mapping) and tool.get("type") == "custom":
                return True
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, Mapping) and tool_choice.get("type") == "custom":
        return True
    return _input_contains_custom_tool_call_output(body.get("input"))


def responses_image_input_requested(body: Mapping[str, Any]) -> bool:
    return _input_contains_image_input(body.get("input"))


def responses_file_input_requested(body: Mapping[str, Any]) -> bool:
    return _input_contains_file_input(body.get("input"))


def previous_response_id_requested(body: Mapping[str, Any]) -> bool:
    return "previous_response_id" in body


def conversation_requested(body: Mapping[str, Any]) -> bool:
    return "conversation" in body


def validate_conversation_items_create_body(
    payload: Mapping[str, Any] | None,
    *,
    settings: Settings,
) -> dict[str, object]:
    """Validate the first supported text-only Conversation item create body."""

    if not isinstance(payload, Mapping):
        raise ResponsesRequestPolicyError(
            "Conversation item create request body must be an object.",
            param="body",
            error_code="conversation_item_create_body_invalid",
        )
    unknown = set(payload) - _SUPPORTED_CONVERSATION_ITEM_CREATE_FIELDS
    if unknown:
        raise ResponsesRequestPolicyError(
            "This Conversation item create field is not enabled by this gateway.",
            param=sorted(unknown)[0],
            error_code="conversation_item_create_field_not_supported",
        )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ResponsesRequestPolicyError(
            "Conversation item create requires an items array.",
            param="items",
            error_code="conversation_item_create_items_invalid",
        )
    canonical_items, _ = ResponsesRequestPolicy(settings=settings)._validate_input_item_array(
        raw_items
    )
    for index, item in enumerate(canonical_items):
        _validate_conversation_text_message_item(item, index=index)
    return {"items": canonical_items}


def validate_conversation_update_body(payload: Mapping[str, Any] | None) -> dict[str, object]:
    """Validate metadata-only Conversation update payloads."""

    if not isinstance(payload, Mapping):
        raise ResponsesRequestPolicyError(
            "Conversation update request body must be an object.",
            param="body",
            error_code="conversation_update_body_invalid",
        )
    unknown = set(payload) - _SUPPORTED_CONVERSATION_UPDATE_FIELDS
    if unknown:
        raise ResponsesRequestPolicyError(
            "This Conversation update field is not enabled by this gateway.",
            param=sorted(unknown)[0],
            error_code="conversation_update_field_not_supported",
        )
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ResponsesRequestPolicyError(
            "Conversation update requires a metadata object.",
            param="metadata",
            error_code="conversation_update_metadata_invalid",
        )
    if len(metadata) > _CONVERSATION_UPDATE_MAX_METADATA_KEYS:
        raise ResponsesRequestPolicyError(
            "Conversation update metadata has too many keys.",
            param="metadata",
            error_code="conversation_update_metadata_invalid",
        )

    canonical_metadata: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key:
            raise ResponsesRequestPolicyError(
                "Conversation update metadata keys must be non-empty strings.",
                param="metadata",
                error_code="conversation_update_metadata_invalid",
            )
        if len(key) > _CONVERSATION_UPDATE_MAX_METADATA_KEY_CHARS or any(
            ord(char) < 32 for char in key
        ):
            raise ResponsesRequestPolicyError(
                "Conversation update metadata keys exceed the gateway limit.",
                param="metadata",
                error_code="conversation_update_metadata_invalid",
            )
        if not isinstance(value, str):
            raise ResponsesRequestPolicyError(
                "Conversation update metadata values must be strings.",
                param="metadata",
                error_code="conversation_update_metadata_invalid",
            )
        if len(value) > _CONVERSATION_UPDATE_MAX_METADATA_VALUE_CHARS or any(
            ord(char) < 32 for char in value
        ):
            raise ResponsesRequestPolicyError(
                "Conversation update metadata values exceed the gateway limit.",
                param="metadata",
                error_code="conversation_update_metadata_invalid",
            )
        _validate_conversation_update_metadata_entry(key=key, value=value)
        canonical_metadata[key] = value

    return {"metadata": canonical_metadata}


def _validate_conversation_text_message_item(item: Mapping[str, Any], *, index: int) -> None:
    item_type = item.get("type")
    if item_type not in (None, "message"):
        raise ResponsesRequestPolicyError(
            "Only text message Conversation items are enabled by this gateway.",
            param=f"items[{index}].type",
            error_code="conversation_item_create_item_not_supported",
        )
    content = item.get("content")
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        raise ResponsesRequestPolicyError(
            "Conversation item message content must be text or input_text parts.",
            param=f"items[{index}].content",
            error_code="conversation_item_create_content_invalid",
        )
    for part_index, part in enumerate(content):
        if not isinstance(part, Mapping) or part.get("type") != "input_text":
            raise ResponsesRequestPolicyError(
                "Conversation item content parts are limited to input_text in this gateway.",
                param=f"items[{index}].content[{part_index}].type",
                error_code="conversation_item_create_content_not_supported",
            )


def _validate_conversation_update_metadata_entry(*, key: str, value: str) -> None:
    lowered_key = key.strip().lower()
    if lowered_key in {
        "authorization",
        "connector_id",
        "headers",
        "password",
        "secret",
        "server_url",
        "token",
    }:
        raise ResponsesRequestPolicyError(
            "Conversation update metadata field is not enabled by this gateway.",
            param="metadata",
            error_code="conversation_update_metadata_not_supported",
        )
    if lowered_key.startswith("mcp") or lowered_key.startswith("tool"):
        raise ResponsesRequestPolicyError(
            "Conversation update metadata field is not enabled by this gateway.",
            param="metadata",
            error_code="conversation_update_metadata_not_supported",
        )
    if value.lower().startswith("bearer "):
        raise ResponsesRequestPolicyError(
            "Conversation update metadata value is not enabled by this gateway.",
            param="metadata",
            error_code="conversation_update_metadata_not_supported",
        )
    if "://" in value:
        parts = urlsplit(value)
        if parts.username is not None or parts.password is not None:
            raise ResponsesRequestPolicyError(
                "Conversation update metadata value is not enabled by this gateway.",
                param="metadata",
                error_code="conversation_update_metadata_not_supported",
            )


def _input_contains_function_call_output(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, Mapping) and item.get("type") == "function_call_output":
            return True
    return False


def _input_contains_custom_tool_call_output(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, Mapping) and item.get("type") == "custom_tool_call_output":
            return True
    return False


def _input_contains_image_input(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "input_image":
                return True
    return False


def _input_contains_file_input(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "input_file":
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


def _contains_recursive_codex_authority_marker(
    value: Any,
    *,
    allowed_key_paths: frozenset[tuple[str, ...]] = frozenset(),
    _path: tuple[str, ...] = (),
) -> bool:
    forbidden_fields = {
        "allowed_tools",
        "approval",
        "approval_request",
        "approval_mode",
        "approval_policy",
        "auth",
        "authentication",
        "authorization",
        "connector",
        "connector_id",
        "connectors",
        "headers",
        "http_headers",
        "request_headers",
        "require_approval",
        "secret",
        "secrets",
        "server_description",
        "server_label",
        "server_url",
        "api_key",
        "api_key_env",
        "mcp",
        "shell",
        "local_shell",
        "apply_patch",
        "computer",
        "computer_use",
        "web_search",
        "file_search",
        "code_interpreter",
        "image_generation",
        "tool_search",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            key_path = (*_path, normalized_key)
            authority_key = normalized_key in forbidden_fields or any(
                marker in normalized_key
                for marker in (
                    "approval",
                    "authorization",
                    "authentication",
                    "connector",
                    "header",
                    "secret",
                )
            )
            if authority_key and key_path not in allowed_key_paths:
                return True
            if normalized_key == "type" and isinstance(nested, str):
                normalized_type = nested.strip().lower().replace("-", "_")
                if normalized_type in _HOSTED_TOOL_TYPES:
                    return True
            if _contains_recursive_codex_authority_marker(
                nested,
                allowed_key_paths=allowed_key_paths,
                _path=key_path,
            ):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(
            _contains_recursive_codex_authority_marker(
                item,
                allowed_key_paths=allowed_key_paths,
                _path=_path,
            )
            for item in value
        )
    return False


def _validate_codex_schema_complexity(
    value: Any,
    *,
    param: str,
    client_spec: ResponsesClientPolicySpec | None,
) -> int:
    if client_spec is None:
        _raise(
            param,
            "responses_codex_client_tools_invalid",
            "The selected client policy specification is unavailable.",
        )
    property_count = 0

    def visit(node: Any, *, depth: int) -> None:
        nonlocal property_count
        if depth > client_spec.max_client_tool_schema_depth:
            _raise(
                param,
                "responses_codex_client_tools_schema_too_deep",
                "A Codex client function schema exceeds the gateway depth limit.",
            )
        if isinstance(node, Mapping):
            properties = node.get("properties")
            if properties is not None:
                if not isinstance(properties, Mapping):
                    _raise(
                        param,
                        "responses_codex_client_tools_invalid",
                        "Codex client function schema properties must be an object.",
                    )
                property_count += len(properties)
                if property_count > client_spec.max_client_tool_schema_properties:
                    _raise(
                        param,
                        "responses_codex_client_tools_property_count_exceeded",
                        "A Codex client function schema has too many properties.",
                    )
            for nested in node.values():
                visit(nested, depth=depth + 1)
        elif isinstance(node, (list, tuple)):
            for nested in node:
                visit(nested, depth=depth + 1)

    visit(value, depth=1)
    return property_count


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


def _allowed_responses_image_mime_types(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.RESPONSES_ALLOWED_IMAGE_MIME_TYPES.split(",")
        if item.strip()
    )


def _allowed_responses_file_mime_types(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.RESPONSES_ALLOWED_FILE_MIME_TYPES.split(",")
        if item.strip()
    )


def _allowed_responses_file_extensions(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.RESPONSES_ALLOWED_FILE_EXTENSIONS.split(",")
        if item.strip()
    )


def _raise(param: str, code: str, message: str) -> NoReturn:
    raise ResponsesRequestPolicyError(message, param=param, error_code=code)
