"""Neutral pure Responses primitives shared by client dialects and core."""

from __future__ import annotations

import re

TEXT_FORMAT_TEXT = "text"
TEXT_FORMAT_JSON_OBJECT = "json_object"
TEXT_FORMAT_JSON_SCHEMA = "json_schema"
STRUCTURED_TEXT_FORMAT_TYPES = frozenset({TEXT_FORMAT_JSON_OBJECT, TEXT_FORMAT_JSON_SCHEMA})
_TEXT_FORMAT_TYPES = frozenset(
    {TEXT_FORMAT_TEXT, TEXT_FORMAT_JSON_OBJECT, TEXT_FORMAT_JSON_SCHEMA}
)
_TEXT_FORMAT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_SUPPORTED_INPUT_MESSAGE_ROLES = frozenset({"user", "assistant", "system", "developer"})
_SUPPORTED_INPUT_MESSAGE_FIELDS = frozenset({"id", "type", "role", "content"})
_SUPPORTED_INPUT_TEXT_PART_FIELDS = frozenset({"type", "text"})
_SUPPORTED_COMPACT_MESSAGE_FIELDS = frozenset({"id", "type", "status", "role", "content"})
_SUPPORTED_COMPACT_TEXT_PART_FIELDS = frozenset({"type", "text"})
_SUPPORTED_COMPACT_PART_TYPES = frozenset({"input_text", "output_text"})
_SUPPORTED_COMPACT_MESSAGE_STATUSES = frozenset({"completed", "in_progress", "incomplete"})
_SUPPORTED_INPUT_IMAGE_PART_FIELDS = frozenset({"type", "image_url", "detail"})
_SUPPORTED_INPUT_FILE_PART_FIELDS = frozenset({"type", "file_url", "filename", "file_data"})
_SUPPORTED_FUNCTION_CALL_OUTPUT_FIELDS = frozenset({"type", "call_id", "output"})
_SUPPORTED_CUSTOM_TOOL_CALL_OUTPUT_FIELDS = frozenset({"type", "call_id", "output"})
_SUPPORTED_FUNCTION_TOOL_FIELDS = frozenset(
    {"type", "name", "description", "parameters", "strict"}
)
_SUPPORTED_CUSTOM_TOOL_FIELDS = frozenset({"type", "name", "description", "format"})
_SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS = frozenset({"type", "name"})
_SUPPORTED_CUSTOM_TOOL_CHOICE_FIELDS = frozenset({"type", "name"})
_SUPPORTED_CUSTOM_TOOL_TEXT_FORMAT_FIELDS = frozenset({"type"})
_SUPPORTED_CUSTOM_TOOL_GRAMMAR_FORMAT_FIELDS = frozenset({"type", "syntax", "definition"})
_SUPPORTED_CONVERSATION_ITEM_CREATE_FIELDS = frozenset({"items"})
_SUPPORTED_CONVERSATION_UPDATE_FIELDS = frozenset({"metadata"})
_CONVERSATION_UPDATE_MAX_METADATA_KEYS = 16
_CONVERSATION_UPDATE_MAX_METADATA_KEY_CHARS = 64
_CONVERSATION_UPDATE_MAX_METADATA_VALUE_CHARS = 512
_FUNCTION_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_CUSTOM_TOOL_NAME_PATTERN = _FUNCTION_TOOL_NAME_PATTERN
_MULTIMODAL_INPUT_ITEM_TYPES = frozenset(
    {"input_image", "input_file", "input_audio", "image", "file", "audio"}
)
_TOOL_INPUT_ITEM_TYPES = frozenset(
    {
        "function_call",
        "custom_tool_call",
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
    }
)
_CUSTOM_TOOL_FORMAT_TYPES = frozenset({"text", "grammar"})
_CUSTOM_TOOL_GRAMMAR_SYNTAXES = frozenset({"lark", "regex"})
_IMAGE_DETAIL_VALUES = frozenset({"auto", "low", "high", "original"})
_IMAGE_DATA_URL_PREFIX = "data:"
_IMAGE_DATA_URL_BASE64_SUFFIX = ";base64"
_FILE_DATA_URL_PREFIX = "data:"
_FILE_DATA_URL_BASE64_SUFFIX = ";base64"
_BASE64_CHARS_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")
