"""Pure Codex-version support facts consumed through a selected policy spec."""

from __future__ import annotations

import re
from collections.abc import Mapping

from slaif_gateway.modules.contracts import ResponsesClientPolicySpec

CODEX_0147_INCLUDE_VALUE = "reasoning.encrypted_content"
CODEX_0148_TAXONOMY_ID = "codex_0_148"
CODEX_0147_COMPACT_FIELDS = frozenset(
    {"model", "input", "instructions", "tools", "parallel_tool_calls", "reasoning", "prompt_cache_key", "text"}
)
CODEX_0147_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
)
CODEX_0147_REASONING_CONTEXT = "all_turns"
CODEX_0147_TEXT_VERBOSITIES = frozenset({"low", "medium", "high"})
CODEX_0147_MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CODEX_0147_TOOL_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CODEX_0147_TOOL_CALL_STATUSES = frozenset({"completed"})
CODEX_0147_CLIENT_METADATA_KEYS = frozenset(
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
CODEX_0147_MAX_INCLUDE_ITEMS = 8
CODEX_0147_MAX_PROMPT_CACHE_KEY_BYTES = 256
CODEX_0147_MAX_REASONING_BYTES = 256
CODEX_0147_MAX_CLIENT_METADATA_KEYS = len(CODEX_0147_CLIENT_METADATA_KEYS)
CODEX_0147_MAX_CLIENT_METADATA_KEY_BYTES = 64
CODEX_0147_MAX_CLIENT_METADATA_VALUE_BYTES = 4096
CODEX_0147_MAX_CLIENT_METADATA_BYTES = 8192
CODEX_0147_MAX_CLIENT_TOOL_SCHEMA_DEPTH = 16
CODEX_0147_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES = 256
CODEX_0147_MAX_CLIENT_TOOL_DESCRIPTION_BYTES = 20_000
CODEX_0147_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES = 32_768
CODEX_0147_MAX_CLIENT_TOOL_DECLARATION_BYTES = 589_824
CODEX_0147_REQUEST_USER_INPUT_ALLOWED_AUTHORITY_KEY_PATHS = frozenset(
    {("parameters", "properties", "questions", "items", "properties", "header")}
)
CODEX_0147_EXEC_COMMAND_ALLOWED_AUTHORITY_KEY_PATHS = frozenset(
    {("parameters", "properties", "shell")}
)
CODEX_0147_MAX_ENCRYPTED_REASONING_ITEM_BYTES = 262_144
CODEX_0147_MAX_ENCRYPTED_REASONING_REQUEST_BYTES = 1_048_576
CODEX_0147_MAX_REASONING_SUMMARY_BYTES = 65_536
CODEX_0147_MAX_REASONING_SUMMARY_PARTS = 64
CODEX_0147_MAX_COMPACTION_ITEM_BYTES = 1_048_576
CODEX_0147_INTERNAL_CHAT_MESSAGE_METADATA_FIELD = "internal_chat_message_metadata_passthrough"
CODEX_0147_MAX_INTERNAL_CHAT_MESSAGE_METADATA_BYTES = 32_768
CODEX_0147_INTERNAL_CHAT_MESSAGE_METADATA_ITEM_TYPES = frozenset(
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
CODEX_0147_FUNCTION_CALL_OUTPUT_FIELDS = frozenset({"type", "id", "call_id", "output"})
CODEX_0147_CUSTOM_TOOL_CALL_OUTPUT_FIELDS = frozenset({"type", "id", "call_id", "output"})
CODEX_0147_TOOL_OUTPUT_CONTENT_FIELDS = frozenset({"type", "text"})
CODEX_0147_FUNCTION_CALL_FIELDS = frozenset(
    {"type", "id", "status", "namespace", "name", "arguments", "call_id"}
)
CODEX_0147_CUSTOM_TOOL_CALL_FIELDS = frozenset(
    {"type", "id", "status", "namespace", "name", "input", "call_id"}
)
CODEX_0147_REASONING_REPLAY_FIELDS = frozenset(
    {"type", "id", "summary", "encrypted_content", "content"}
)
CODEX_0147_COMPACTION_REPLAY_FIELDS = frozenset({"type", "id", "encrypted_content"})
CODEX_0147_REASONING_SUMMARY_FIELDS = frozenset({"type", "text"})
CODEX_0147_ADDITIONAL_TOOLS_FIELDS = frozenset({"type", "role", "tools"})
CODEX_0147_NAMESPACE_FIELDS = frozenset({"type", "name", "description", "tools"})
CODEX_0147_CLIENT_TOOL_TAXONOMY: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "functions",
        (("exec", "custom"), ("wait", "function"), ("request_user_input", "function")),
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


def codex_0147_taxonomy_for(
    value: object,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    if not isinstance(value, list):
        return None
    names = frozenset(
        item.get("name")
        for item in value
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    )
    if names == frozenset(namespace for namespace, _tools in CODEX_0147_CLIENT_TOOL_TAXONOMY):
        return CODEX_0147_CLIENT_TOOL_TAXONOMY
    return None


def build_codex_0147_policy_spec(
    *,
    taxonomy_0148: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
) -> ResponsesClientPolicySpec:
    """Build the immutable 0.147 spec with its exact pure facts."""
    return ResponsesClientPolicySpec(
        compact_fields=CODEX_0147_COMPACT_FIELDS,
        function_call_output_fields=CODEX_0147_FUNCTION_CALL_OUTPUT_FIELDS,
        custom_tool_call_output_fields=CODEX_0147_CUSTOM_TOOL_CALL_OUTPUT_FIELDS,
        function_call_fields=CODEX_0147_FUNCTION_CALL_FIELDS,
        custom_tool_call_fields=CODEX_0147_CUSTOM_TOOL_CALL_FIELDS,
        tool_output_content_fields=CODEX_0147_TOOL_OUTPUT_CONTENT_FIELDS,
        reasoning_replay_fields=CODEX_0147_REASONING_REPLAY_FIELDS,
        compaction_replay_fields=CODEX_0147_COMPACTION_REPLAY_FIELDS,
        reasoning_summary_fields=CODEX_0147_REASONING_SUMMARY_FIELDS,
        additional_tools_fields=CODEX_0147_ADDITIONAL_TOOLS_FIELDS,
        namespace_fields=CODEX_0147_NAMESPACE_FIELDS,
        include_value=CODEX_0147_INCLUDE_VALUE,
        reasoning_efforts=CODEX_0147_REASONING_EFFORTS,
        reasoning_context=CODEX_0147_REASONING_CONTEXT,
        text_verbosities=CODEX_0147_TEXT_VERBOSITIES,
        message_id_pattern=CODEX_0147_MESSAGE_ID_PATTERN,
        tool_call_id_pattern=CODEX_0147_TOOL_CALL_ID_PATTERN,
        tool_call_statuses=CODEX_0147_TOOL_CALL_STATUSES,
        client_metadata_keys=CODEX_0147_CLIENT_METADATA_KEYS,
        max_include_items=CODEX_0147_MAX_INCLUDE_ITEMS,
        max_prompt_cache_key_bytes=CODEX_0147_MAX_PROMPT_CACHE_KEY_BYTES,
        max_reasoning_bytes=CODEX_0147_MAX_REASONING_BYTES,
        max_client_metadata_keys=CODEX_0147_MAX_CLIENT_METADATA_KEYS,
        max_client_metadata_key_bytes=CODEX_0147_MAX_CLIENT_METADATA_KEY_BYTES,
        max_client_metadata_value_bytes=CODEX_0147_MAX_CLIENT_METADATA_VALUE_BYTES,
        max_client_metadata_bytes=CODEX_0147_MAX_CLIENT_METADATA_BYTES,
        max_client_tool_schema_depth=CODEX_0147_MAX_CLIENT_TOOL_SCHEMA_DEPTH,
        max_client_tool_schema_properties=CODEX_0147_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES,
        max_client_tool_description_bytes=CODEX_0147_MAX_CLIENT_TOOL_DESCRIPTION_BYTES,
        max_client_tool_total_description_bytes=CODEX_0147_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES,
        max_client_tool_declaration_bytes=CODEX_0147_MAX_CLIENT_TOOL_DECLARATION_BYTES,
        request_user_input_allowed_authority_key_paths=CODEX_0147_REQUEST_USER_INPUT_ALLOWED_AUTHORITY_KEY_PATHS,
        exec_command_allowed_authority_key_paths=CODEX_0147_EXEC_COMMAND_ALLOWED_AUTHORITY_KEY_PATHS,
        max_encrypted_reasoning_item_bytes=CODEX_0147_MAX_ENCRYPTED_REASONING_ITEM_BYTES,
        max_encrypted_reasoning_request_bytes=CODEX_0147_MAX_ENCRYPTED_REASONING_REQUEST_BYTES,
        max_reasoning_summary_bytes=CODEX_0147_MAX_REASONING_SUMMARY_BYTES,
        max_reasoning_summary_parts=CODEX_0147_MAX_REASONING_SUMMARY_PARTS,
        max_compaction_item_bytes=CODEX_0147_MAX_COMPACTION_ITEM_BYTES,
        internal_chat_message_metadata_field=CODEX_0147_INTERNAL_CHAT_MESSAGE_METADATA_FIELD,
        max_internal_chat_message_metadata_bytes=CODEX_0147_MAX_INTERNAL_CHAT_MESSAGE_METADATA_BYTES,
        internal_chat_message_metadata_item_types=CODEX_0147_INTERNAL_CHAT_MESSAGE_METADATA_ITEM_TYPES,
        taxonomy_for=codex_0147_taxonomy_for,
        taxonomy_0148=taxonomy_0148,
        taxonomy_id_0148=CODEX_0148_TAXONOMY_ID,
    )
