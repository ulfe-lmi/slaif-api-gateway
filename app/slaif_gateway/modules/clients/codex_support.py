"""Pure Codex client-dialect constants and taxonomies."""

from __future__ import annotations

import re
from collections.abc import Mapping

_SUPPORTED_CODEX_COMPACT_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "tools",
        "parallel_tool_calls",
        "reasoning",
        "prompt_cache_key",
        "text",
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
_SUPPORTED_CODEX_FUNCTION_CALL_OUTPUT_FIELDS = frozenset({"type", "id", "call_id", "output"})
_SUPPORTED_CODEX_CUSTOM_TOOL_CALL_OUTPUT_FIELDS = frozenset({"type", "id", "call_id", "output"})
_SUPPORTED_CODEX_TOOL_OUTPUT_CONTENT_FIELDS = frozenset({"type", "text"})
_SUPPORTED_CODEX_FUNCTION_CALL_FIELDS = frozenset(
    {"type", "id", "status", "namespace", "name", "arguments", "call_id"}
)
_SUPPORTED_CODEX_CUSTOM_TOOL_CALL_FIELDS = frozenset(
    {"type", "id", "status", "namespace", "name", "input", "call_id"}
)
_SUPPORTED_CODEX_REASONING_REPLAY_FIELDS = frozenset(
    {"type", "id", "summary", "encrypted_content", "content"}
)
_SUPPORTED_CODEX_COMPACTION_REPLAY_FIELDS = frozenset({"type", "id", "encrypted_content"})
_SUPPORTED_CODEX_REASONING_SUMMARY_FIELDS = frozenset({"type", "text"})
_SUPPORTED_FUNCTION_TOOL_FIELDS = frozenset({"type", "name", "description", "parameters", "strict"})
_SUPPORTED_CUSTOM_TOOL_FIELDS = frozenset({"type", "name", "description", "format"})
_SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS = frozenset({"type", "name"})
_SUPPORTED_CUSTOM_TOOL_CHOICE_FIELDS = frozenset({"type", "name"})
_SUPPORTED_CUSTOM_TOOL_TEXT_FORMAT_FIELDS = frozenset({"type"})
_SUPPORTED_CUSTOM_TOOL_GRAMMAR_FORMAT_FIELDS = frozenset({"type", "syntax", "definition"})
_SUPPORTED_CODEX_ADDITIONAL_TOOLS_FIELDS = frozenset({"type", "role", "tools"})
_SUPPORTED_CODEX_NAMESPACE_FIELDS = frozenset({"type", "name", "description", "tools"})
_SUPPORTED_CONVERSATION_ITEM_CREATE_FIELDS = frozenset({"items"})
_SUPPORTED_CONVERSATION_UPDATE_FIELDS = frozenset({"metadata"})
_CONVERSATION_UPDATE_MAX_METADATA_KEYS = 16
_CONVERSATION_UPDATE_MAX_METADATA_KEY_CHARS = 64
_CONVERSATION_UPDATE_MAX_METADATA_VALUE_CHARS = 512
_FUNCTION_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_CUSTOM_TOOL_NAME_PATTERN = _FUNCTION_TOOL_NAME_PATTERN
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
_CODEX_INCLUDE_VALUE = "reasoning.encrypted_content"
_CODEX_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
)
_CODEX_REASONING_CONTEXT = "all_turns"
_CODEX_TEXT_VERBOSITIES = frozenset({"low", "medium", "high"})
_CODEX_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CODEX_TOOL_CALL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_CODEX_TOOL_CALL_STATUSES = frozenset({"completed"})
_CODEX_CLIENT_METADATA_KEYS = frozenset(
    {
        "x-codex-installation-id",
        "session_id",
        "root_turn_id",
        "thread_id",
        "turn_id",
        "x-codex-window-id",
        "x-codex-turn-metadata",
    }
)
_CODEX_MAX_INCLUDE_ITEMS = 8
_CODEX_MAX_PROMPT_CACHE_KEY_BYTES = 256
_CODEX_MAX_REASONING_BYTES = 256
_CODEX_MAX_CLIENT_METADATA_KEYS = len(_CODEX_CLIENT_METADATA_KEYS)
_CODEX_MAX_CLIENT_METADATA_KEY_BYTES = 64
_CODEX_MAX_CLIENT_METADATA_VALUE_BYTES = 4096
_CODEX_MAX_CLIENT_METADATA_BYTES = 8192
_CODEX_MAX_CLIENT_TOOL_SCHEMA_DEPTH = 16
_CODEX_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES = 256
_CODEX_MAX_CLIENT_TOOL_DESCRIPTION_BYTES = 20_000
_CODEX_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES = 32_768
_CODEX_MAX_CLIENT_TOOL_DECLARATION_BYTES = 589_824
_CODEX_REQUEST_USER_INPUT_ALLOWED_AUTHORITY_KEY_PATHS = frozenset(
    {
        (
            "parameters",
            "properties",
            "questions",
            "items",
            "properties",
            "header",
        )
    }
)
_CODEX_EXEC_COMMAND_ALLOWED_AUTHORITY_KEY_PATHS = frozenset(
    {("parameters", "properties", "shell")}
)
_CODEX_MAX_ENCRYPTED_REASONING_ITEM_BYTES = 262_144
_CODEX_MAX_ENCRYPTED_REASONING_REQUEST_BYTES = 1_048_576
_CODEX_MAX_REASONING_SUMMARY_BYTES = 65_536
_CODEX_MAX_REASONING_SUMMARY_PARTS = 64
_CODEX_MAX_COMPACTION_ITEM_BYTES = 1_048_576
_CODEX_INTERNAL_CHAT_MESSAGE_METADATA_FIELD = "internal_chat_message_metadata_passthrough"
_CODEX_MAX_INTERNAL_CHAT_MESSAGE_METADATA_BYTES = 32_768
_CODEX_INTERNAL_CHAT_MESSAGE_METADATA_ITEM_TYPES = frozenset(
    {
        None,
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "compaction",
    }
)
_CODEX_CLIENT_TOOL_TAXONOMY: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "functions",
        (
            ("exec", "custom"),
            ("wait", "function"),
            ("request_user_input", "function"),
        ),
    ),
    (
        "collaboration",
        (
            ("followup_task", "function"),
            ("interrupt_agent", "function"),
            ("list_agents", "function"),
            ("send_message", "function"),
            ("spawn_agent", "function"),
            ("wait_agent", "function"),
        ),
    ),
)
_CODEX_CLIENT_TOOL_TAXONOMY_0148: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "functions",
        (
            ("exec_command", "function"),
            ("write_stdin", "function"),
            ("update_plan", "function"),
            ("request_user_input", "function"),
            ("view_image", "function"),
        ),
    ),
    (
        "multi_agent_v1",
        (
            ("close_agent", "function"),
            ("resume_agent", "function"),
            ("send_input", "function"),
            ("spawn_agent", "function"),
            ("wait_agent", "function"),
        ),
    ),
)


def _codex_client_tool_taxonomy_for(
    value: object,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    if not isinstance(value, list):
        return None
    names = frozenset(
        item.get("name")
        for item in value
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    )
    if names == frozenset(namespace for namespace, _tools in _CODEX_CLIENT_TOOL_TAXONOMY):
        return _CODEX_CLIENT_TOOL_TAXONOMY
    return None


def codex_client_tool_taxonomy_id(policy: object) -> str | None:
    if isinstance(policy, Mapping) and policy.get("codex_client_tool_taxonomy") == "codex_0_148":
        return "codex_0_148"
    return None

__all__ = [
    "STRUCTURED_TEXT_FORMAT_TYPES",
    "TEXT_FORMAT_JSON_OBJECT",
    "TEXT_FORMAT_JSON_SCHEMA",
    "TEXT_FORMAT_TEXT",
    "_BASE64_CHARS_RE",
    "_CODEX_CLIENT_METADATA_KEYS",
    "_CODEX_CLIENT_TOOL_TAXONOMY",
    "_CODEX_CLIENT_TOOL_TAXONOMY_0148",
    "_CODEX_EXEC_COMMAND_ALLOWED_AUTHORITY_KEY_PATHS",
    "_CODEX_INCLUDE_VALUE",
    "_CODEX_INTERNAL_CHAT_MESSAGE_METADATA_FIELD",
    "_CODEX_INTERNAL_CHAT_MESSAGE_METADATA_ITEM_TYPES",
    "_CODEX_MAX_CLIENT_METADATA_BYTES",
    "_CODEX_MAX_CLIENT_METADATA_KEYS",
    "_CODEX_MAX_CLIENT_METADATA_KEY_BYTES",
    "_CODEX_MAX_CLIENT_METADATA_VALUE_BYTES",
    "_CODEX_MAX_CLIENT_TOOL_DECLARATION_BYTES",
    "_CODEX_MAX_CLIENT_TOOL_DESCRIPTION_BYTES",
    "_CODEX_MAX_CLIENT_TOOL_SCHEMA_DEPTH",
    "_CODEX_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES",
    "_CODEX_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES",
    "_CODEX_MAX_COMPACTION_ITEM_BYTES",
    "_CODEX_MAX_ENCRYPTED_REASONING_ITEM_BYTES",
    "_CODEX_MAX_ENCRYPTED_REASONING_REQUEST_BYTES",
    "_CODEX_MAX_INCLUDE_ITEMS",
    "_CODEX_MAX_INTERNAL_CHAT_MESSAGE_METADATA_BYTES",
    "_CODEX_MAX_PROMPT_CACHE_KEY_BYTES",
    "_CODEX_MAX_REASONING_BYTES",
    "_CODEX_MAX_REASONING_SUMMARY_BYTES",
    "_CODEX_MAX_REASONING_SUMMARY_PARTS",
    "_CODEX_MESSAGE_ID_RE",
    "_CODEX_REASONING_CONTEXT",
    "_CODEX_REASONING_EFFORTS",
    "_CODEX_REQUEST_USER_INPUT_ALLOWED_AUTHORITY_KEY_PATHS",
    "_CODEX_TEXT_VERBOSITIES",
    "_CODEX_TOOL_CALL_ID_RE",
    "_CODEX_TOOL_CALL_STATUSES",
    "_CONVERSATION_UPDATE_MAX_METADATA_KEYS",
    "_CONVERSATION_UPDATE_MAX_METADATA_KEY_CHARS",
    "_CONVERSATION_UPDATE_MAX_METADATA_VALUE_CHARS",
    "_CUSTOM_TOOL_FORMAT_TYPES",
    "_CUSTOM_TOOL_GRAMMAR_SYNTAXES",
    "_CUSTOM_TOOL_NAME_PATTERN",
    "_FILE_DATA_URL_BASE64_SUFFIX",
    "_FILE_DATA_URL_PREFIX",
    "_FUNCTION_TOOL_NAME_PATTERN",
    "_HOSTED_TOOL_TYPES",
    "_IMAGE_DATA_URL_BASE64_SUFFIX",
    "_IMAGE_DATA_URL_PREFIX",
    "_IMAGE_DETAIL_VALUES",
    "_MULTIMODAL_INPUT_ITEM_TYPES",
    "_SUPPORTED_CODEX_ADDITIONAL_TOOLS_FIELDS",
    "_SUPPORTED_CODEX_COMPACTION_REPLAY_FIELDS",
    "_SUPPORTED_CODEX_COMPACT_FIELDS",
    "_SUPPORTED_CODEX_CUSTOM_TOOL_CALL_FIELDS",
    "_SUPPORTED_CODEX_CUSTOM_TOOL_CALL_OUTPUT_FIELDS",
    "_SUPPORTED_CODEX_FUNCTION_CALL_FIELDS",
    "_SUPPORTED_CODEX_FUNCTION_CALL_OUTPUT_FIELDS",
    "_SUPPORTED_CODEX_NAMESPACE_FIELDS",
    "_SUPPORTED_CODEX_REASONING_REPLAY_FIELDS",
    "_SUPPORTED_CODEX_REASONING_SUMMARY_FIELDS",
    "_SUPPORTED_CODEX_TOOL_OUTPUT_CONTENT_FIELDS",
    "_SUPPORTED_COMPACT_MESSAGE_FIELDS",
    "_SUPPORTED_COMPACT_MESSAGE_STATUSES",
    "_SUPPORTED_COMPACT_PART_TYPES",
    "_SUPPORTED_COMPACT_TEXT_PART_FIELDS",
    "_SUPPORTED_CONVERSATION_ITEM_CREATE_FIELDS",
    "_SUPPORTED_CONVERSATION_UPDATE_FIELDS",
    "_SUPPORTED_CUSTOM_TOOL_CALL_OUTPUT_FIELDS",
    "_SUPPORTED_CUSTOM_TOOL_CHOICE_FIELDS",
    "_SUPPORTED_CUSTOM_TOOL_FIELDS",
    "_SUPPORTED_CUSTOM_TOOL_GRAMMAR_FORMAT_FIELDS",
    "_SUPPORTED_CUSTOM_TOOL_TEXT_FORMAT_FIELDS",
    "_SUPPORTED_FUNCTION_CALL_OUTPUT_FIELDS",
    "_SUPPORTED_FUNCTION_TOOL_CHOICE_FIELDS",
    "_SUPPORTED_FUNCTION_TOOL_FIELDS",
    "_SUPPORTED_INPUT_FILE_PART_FIELDS",
    "_SUPPORTED_INPUT_IMAGE_PART_FIELDS",
    "_SUPPORTED_INPUT_MESSAGE_FIELDS",
    "_SUPPORTED_INPUT_MESSAGE_ROLES",
    "_SUPPORTED_INPUT_TEXT_PART_FIELDS",
    "_TEXT_FORMAT_TYPES",
    "_TOOL_INPUT_ITEM_TYPES",
    "_codex_client_tool_taxonomy_for",
    "codex_client_tool_taxonomy_id",
]
