"""Pure contracts shared by statically registered client and server modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from re import Pattern
from typing import Callable

DEFAULT_CLIENT_MODULE_ID = "openai-default"
DEFAULT_CLIENT_MODULE_VERSION = "1"


class ModuleSelectionError(ValueError):
    """Raised when a static module or module pair is not supported."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class CodexTaxonomyResult:
    """Immutable outcome of structurally classifying Codex additional_tools.

    ``accepted`` is ``True`` only when the declared namespace/tool set exactly
    matches an approved set for the profile; ``taxonomy`` then carries the
    canonical ordered ``(namespace, ((tool, "function"), ...), ...)`` tuple.
    On rejection, ``reason_code`` is a stable, content-free marker and the
    offending ``namespace_index`` / ``tool_index`` / ``field`` name the first
    failing check (original check order); ``observed`` and ``limit`` carry the
    observed count and the relevant cap for cardinality failures.  This type
    carries no raw request content and grants no execution, replay, or
    authority.  It is the single shared classifier result consumed by the
    request policy, so the historical acceptance surface is preserved exactly.
    """

    accepted: bool
    taxonomy: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None = None
    reason_code: str | None = None
    namespace_index: int | None = None
    tool_index: int | None = None
    field: str | None = None
    observed: int | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ResponsesClientPolicySpec:
    """Pure, module-selected Responses dialect facts consumed by core policy."""

    compact_fields: frozenset[str]
    function_call_output_fields: frozenset[str]
    custom_tool_call_output_fields: frozenset[str]
    function_call_fields: frozenset[str]
    custom_tool_call_fields: frozenset[str]
    tool_output_content_fields: frozenset[str]
    reasoning_replay_fields: frozenset[str]
    compaction_replay_fields: frozenset[str]
    reasoning_summary_fields: frozenset[str]
    additional_tools_fields: frozenset[str]
    namespace_fields: frozenset[str]
    include_value: str
    reasoning_efforts: frozenset[str]
    reasoning_context: str
    text_verbosities: frozenset[str]
    message_id_pattern: Pattern[str]
    tool_call_id_pattern: Pattern[str]
    tool_call_statuses: frozenset[str]
    client_metadata_keys: frozenset[str]
    max_include_items: int
    max_prompt_cache_key_bytes: int
    max_reasoning_bytes: int
    max_client_metadata_keys: int
    max_client_metadata_key_bytes: int
    max_client_metadata_value_bytes: int
    max_client_metadata_bytes: int
    max_client_tool_schema_depth: int
    max_client_tool_schema_properties: int
    max_client_tool_description_bytes: int
    max_client_tool_total_description_bytes: int
    max_client_tool_declaration_bytes: int
    request_user_input_allowed_authority_key_paths: frozenset[tuple[str, ...]]
    exec_command_allowed_authority_key_paths: frozenset[tuple[str, ...]]
    max_encrypted_reasoning_item_bytes: int
    max_encrypted_reasoning_request_bytes: int
    max_reasoning_summary_bytes: int
    max_reasoning_summary_parts: int
    max_compaction_item_bytes: int
    internal_chat_message_metadata_field: str
    max_internal_chat_message_metadata_bytes: int
    internal_chat_message_metadata_item_types: frozenset[object]
    taxonomy_for: Callable[[object], tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None]
    taxonomy_0148: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    taxonomy_id_0148: str
    taxonomy_classifier: Callable[[object], CodexTaxonomyResult] | None = None
    function_call_item_id_optional: bool = False
    custom_tool_call_item_id_optional: bool = False
    allow_idless_tool_call_replay: bool = False
    reasoning_visible_id_optional: bool = False
    reasoning_visible_content_fields: frozenset[str] = frozenset()
    reasoning_visible_content_types: frozenset[str] = frozenset()
    max_reasoning_visible_parts: int = 0
    max_reasoning_visible_part_bytes: int = 0
    max_reasoning_visible_bytes: int = 0
    allow_idless_encrypted_reasoning: bool = False
    assistant_history_content_types: frozenset[str] = frozenset()
    allow_schema_property_names: bool = False
    custom_client_tools: frozenset[tuple[str, str, str]] = frozenset({("functions", "exec", "custom")})
    allow_sparse_visible_reasoning: bool = False
    allow_empty_visible_reasoning: bool = False
    allow_sparse_function_events: bool = False


@dataclass(frozen=True, slots=True)
class CanonicalClientRequest:
    """Content-bearing request facts returned only to the Gateway core."""

    module_id: str
    module_version: str
    endpoint: str
    body: Mapping[str, object]
    capability_intents: tuple[str, ...] = ()
    adapter_managed_declaration_candidates: tuple[str, ...] = ()
    adapter_managed_declaration_shapes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    stream_profile: str | None = None
    zero_argument_function_names: frozenset[str] = frozenset()
    profile_facts: Mapping[str, str] = field(default_factory=dict)
    identity_hints: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ServerModuleDescriptor:
    """Static identity and compatibility metadata for one server module."""

    module_id: str
    module_version: str
    provider_slugs: frozenset[str]
    provider_kinds: frozenset[str]


@dataclass(frozen=True, slots=True)
class ClientServerPair:
    """A finite compatibility declaration, not an authority grant."""

    client_module_id: str
    server_module_id: str
