"""Strict, versioned profile DATA for neutral agent Chat client dialects.

This module owns the reviewed, trusted, *data-only* profile documents that
drive the neutral Chat profile engine (``modules/clients/agent_chat.py``).
It is shared by the Hermes 0.22.5 and OpenCode 1.19.3 Chat profiles (and any
future profile that stays inside this bounded grammar) and is deliberately
free of Gateway authority: data cannot grant routes, capabilities, replay,
signing, or accounting behavior.

Document law
------------
- ``schema_version`` is exactly 1; unknown or missing keys fail closed.
- The canonical identity of a reviewed document is the SHA-256 of its
  sorted-key, compact, ASCII JSON serialization
  (:func:`canonical_profile_digest`). A key's Chat pin carries
  ``(id, version, fixture_sha256)``; the digest is bound to the exact
  reviewed DATA, never to a brand name or host-default executable.
- Data-only vocabulary upgrades are published as new document bytes, which
  changes the digest; operators re-pin keys and restart. There is no
  per-tool source upgrade path.
- Error messages use fixed, safe vocabulary and structural positions only;
  they never echo document values.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

AGENT_CHAT_PROFILE_SCHEMA_VERSION = 1

MAX_AGENT_CHAT_PROFILE_FILE_BYTES = 64 * 1024
MAX_AGENT_CHAT_PROFILE_ID_LENGTH = 64
MAX_AGENT_CHAT_PROFILE_NAME_LENGTH = 64
MAX_AGENT_CHAT_PROFILE_VERSION_LENGTH = 9
MAX_AGENT_CHAT_PROFILE_SOURCE_TAG_LENGTH = 64
MAX_AGENT_CHAT_PROFILE_SDK_VERSION_LENGTH = 32
MAX_AGENT_CHAT_PROFILE_REASONING_VALUES = 6
MAX_AGENT_CHAT_PROFILE_ASSISTANT_FIELDS = 8
MAX_AGENT_CHAT_PROFILE_TOOL_NAMES = 64
MAX_AGENT_CHAT_PROFILE_FIELD_NAME_LENGTH = 32
MAX_AGENT_CHAT_PROFILE_TOOL_NAME_LENGTH = 64
MAX_AGENT_CHAT_PROFILE_MAX_BYTES_BOUND = 262144

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*-v[0-9]+$")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SDK_NAME_RE = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")
_VERSION_RE = re.compile(r"^[0-9]+$")
_DISTRIBUTION_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z][0-9A-Za-z.-]*)?$")
_SOURCE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SOURCE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ASSISTANT_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# Finite standard Chat function-name identifier grammar: first character is a
# letter, digit, or underscore; the remainder may add dots and dashes. This
# admits observed forms such as ``_read_page`` or ``readFile`` while staying
# bounded; per-profile admission is still controlled by the name whitelist.
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")

# Finite standard Chat reasoning-effort vocabulary. ``none`` is the
# observed auxiliary (session-title) request value of the pinned Hermes
# 0.22.5 client; profiles opt in explicitly, the default Chat policy is
# unchanged.
AGENT_CHAT_REASONING_EFFORT_VOCABULARY = frozenset(
    {"minimal", "low", "medium", "high", "xhigh", "none"}
)
AGENT_CHAT_WIRE_API = "chat_completions"

# Standard assistant message fields that a profile may never re-declare.
AGENT_CHAT_RESERVED_ASSISTANT_FIELDS = frozenset(
    {"role", "content", "tool_calls", "refusal", "function_call", "audio"}
)

_CLIENT_KEYS = frozenset(
    {
        "name",
        "distribution_version",
        "source_tag",
        "source_commit",
        "sdk_name",
        "sdk_version",
        "wire_api",
    }
)
_ASSISTANT_FIELD_KEYS = frozenset({"name", "max_bytes"})
_TOOLS_KEYS = frozenset(
    {
        "names",
        "max_declarations",
        "max_description_bytes",
        "max_schema_depth",
        "max_schema_properties",
        "max_declaration_bytes",
    }
)
_TOOL_CALL_KEYS = frozenset({"id_min_length", "id_max_length", "arguments_max_bytes"})
_DIALECT_KEYS = frozenset(
    {"reasoning_efforts", "assistant_message_fields", "tools", "tool_call"}
)
_DOCUMENT_KEYS = frozenset({"schema_version", "id", "version", "client", "dialect"})


class AgentChatProfileDataError(ValueError):
    """A safe, fixed-message profile DATA error (never echoes values)."""

    def __init__(self, field: str, problem: str) -> None:
        super().__init__(f"{field}: {problem}")
        self.field = field
        self.problem = problem


def _freeze_mapping(value: Any) -> Any:
    """Deep-freeze validated document structure (nested proxies, tuples)."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_mapping(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_mapping(item) for item in value)
    return value


def _fail(field: str, problem: str) -> None:
    raise AgentChatProfileDataError(field, problem)


def _strict_pairs_hook(pairs: list[tuple[Any, Any]]) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key, _value in pairs:
        if not isinstance(key, str):
            _fail("file", "JSON object keys must be strings.")
        if key in seen:
            _fail("file", "JSON object contains a duplicate key.")
        seen.add(key)
    return dict(pairs)


def _strict_constant(name: str) -> Any:
    _fail("file", f"JSON constant {name} is not allowed.")


def _require_keys(document: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    if set(document) != allowed:
        _fail(where, "Object members do not match the profile data schema.")


def _str(
    document: Mapping[str, Any],
    key: str,
    *,
    max_length: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        _fail(key, "Value must be a non-empty string.")
    if len(value) > max_length:
        _fail(key, "Value is too long.")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail(key, "Value does not match the required form.")
    return value


def _int(document: Mapping[str, Any], key: str, *, minimum: int, maximum: int) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(key, "Value must be an integer.")
    if value < minimum or value > maximum:
        _fail(key, "Value is outside the allowed range.")
    return value


@dataclass(frozen=True, slots=True)
class AgentChatProfileClient:
    """Public, reviewed client provenance facts for one profile document."""

    name: str
    distribution_version: str
    source_tag: str
    source_commit: str
    sdk_name: str
    sdk_version: str
    wire_api: str


@dataclass(frozen=True, slots=True)
class AgentChatProfileAssistantField:
    """One allowed extra assistant message field (bounded string value)."""

    name: str
    max_bytes: int


@dataclass(frozen=True, slots=True)
class AgentChatProfileTools:
    """Bounded nested-function declaration vocabulary and ceilings."""

    names: frozenset[str]
    max_declarations: int
    max_description_bytes: int
    max_schema_depth: int
    max_schema_properties: int
    max_declaration_bytes: int


@dataclass(frozen=True, slots=True)
class AgentChatProfileToolCall:
    """Bounded assistant tool-call identity and argument grammar."""

    id_min_length: int
    id_max_length: int
    arguments_max_bytes: int


@dataclass(frozen=True, slots=True)
class AgentChatProfileData:
    """One fully validated agent Chat profile document with its identity.

    ``document`` is a deep, independent, immutable copy of the reviewed bytes
    (nested mappings are read-only proxies, lists are tuples);
    ``fixture_sha256`` is the canonical digest of exactly that content.
    """

    document: Mapping[str, Any]
    schema_version: int
    profile_id: str
    version: str
    client: AgentChatProfileClient
    reasoning_efforts: frozenset[str]
    assistant_message_fields: tuple[AgentChatProfileAssistantField, ...]
    tools: AgentChatProfileTools
    tool_call: AgentChatProfileToolCall
    fixture_sha256: str


def canonical_profile_digest(document: Mapping[str, Any]) -> str:
    """SHA-256 of the sorted-key, compact, ASCII serialization of a document.

    Accepts plain or deeply frozen documents: nested mappings (including
    read-only proxies) and tuples are converted to plain dicts/lists before
    serialization, so the digest of the exposed ``profile.document`` always
    equals the stored ``fixture_sha256``.
    """
    serialized = json.dumps(
        _canonical_value(document),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _parse_client(document: Mapping[str, Any]) -> AgentChatProfileClient:
    _require_keys(document, _CLIENT_KEYS, "client")
    wire_api = _str(document, "wire_api", max_length=32)
    if wire_api != AGENT_CHAT_WIRE_API:
        _fail("client.wire_api", "Value must be the Chat Completions wire API.")
    return AgentChatProfileClient(
        name=_str(document, "name", max_length=MAX_AGENT_CHAT_PROFILE_NAME_LENGTH, pattern=_NAME_RE),
        distribution_version=_str(
            document,
            "distribution_version",
            max_length=32,
            pattern=_DISTRIBUTION_VERSION_RE,
        ),
        source_tag=_str(
            document,
            "source_tag",
            max_length=MAX_AGENT_CHAT_PROFILE_SOURCE_TAG_LENGTH,
            pattern=_SOURCE_TAG_RE,
        ),
        source_commit=_str(document, "source_commit", max_length=40, pattern=_SOURCE_COMMIT_RE),
        sdk_name=_str(document, "sdk_name", max_length=MAX_AGENT_CHAT_PROFILE_NAME_LENGTH, pattern=_SDK_NAME_RE),
        sdk_version=_str(document, "sdk_version", max_length=MAX_AGENT_CHAT_PROFILE_SDK_VERSION_LENGTH),
        wire_api=wire_api,
    )


def _parse_reasoning_efforts(document: Mapping[str, Any]) -> frozenset[str]:
    value = document.get("reasoning_efforts")
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_AGENT_CHAT_PROFILE_REASONING_VALUES:
        _fail("dialect.reasoning_efforts", "Value must be a non-empty list within bounds.")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item in seen:
            _fail("dialect.reasoning_efforts", "Values must be unique strings.")
        if item not in AGENT_CHAT_REASONING_EFFORT_VOCABULARY:
            _fail("dialect.reasoning_efforts", "Value is outside the approved vocabulary.")
        seen.add(item)
    return frozenset(seen)


def _parse_assistant_message_fields(
    document: Mapping[str, Any],
) -> tuple[AgentChatProfileAssistantField, ...]:
    value = document.get("assistant_message_fields")
    if not isinstance(value, list) or len(value) > MAX_AGENT_CHAT_PROFILE_ASSISTANT_FIELDS:
        _fail("dialect.assistant_message_fields", "Value must be a list within bounds.")
    fields: list[AgentChatProfileAssistantField] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        where = f"dialect.assistant_message_fields[{index}]"
        if not isinstance(entry, Mapping):
            _fail(where, "Value must be an object.")
        _require_keys(entry, _ASSISTANT_FIELD_KEYS, where)
        name = _str(
            entry,
            "name",
            max_length=MAX_AGENT_CHAT_PROFILE_FIELD_NAME_LENGTH,
            pattern=_ASSISTANT_FIELD_RE,
        )
        if name in AGENT_CHAT_RESERVED_ASSISTANT_FIELDS:
            _fail(where, "Field name is reserved by the standard dialect.")
        if name in seen:
            _fail(where, "Field name is repeated.")
        seen.add(name)
        max_bytes = _int(entry, "max_bytes", minimum=1, maximum=MAX_AGENT_CHAT_PROFILE_MAX_BYTES_BOUND)
        fields.append(AgentChatProfileAssistantField(name=name, max_bytes=max_bytes))
    return tuple(fields)


def _parse_tools(document: Mapping[str, Any]) -> AgentChatProfileTools:
    _require_keys(document, _TOOLS_KEYS, "dialect.tools")
    names = document.get("names")
    if not isinstance(names, list) or not 1 <= len(names) <= MAX_AGENT_CHAT_PROFILE_TOOL_NAMES:
        _fail("dialect.tools.names", "Value must be a non-empty list within bounds.")
    seen: set[str] = set()
    for index, item in enumerate(names):
        where = f"dialect.tools.names[{index}]"
        if not isinstance(item, str) or item in seen:
            _fail(where, "Values must be unique strings.")
        if len(item) > MAX_AGENT_CHAT_PROFILE_TOOL_NAME_LENGTH or _TOOL_NAME_RE.fullmatch(item) is None:
            _fail(where, "Value does not match the tool-name form.")
        seen.add(item)
    return AgentChatProfileTools(
        names=frozenset(seen),
        max_declarations=_int(document, "max_declarations", minimum=1, maximum=64),
        max_description_bytes=_int(
            document, "max_description_bytes", minimum=1, maximum=MAX_AGENT_CHAT_PROFILE_MAX_BYTES_BOUND
        ),
        max_schema_depth=_int(document, "max_schema_depth", minimum=1, maximum=16),
        max_schema_properties=_int(document, "max_schema_properties", minimum=1, maximum=256),
        max_declaration_bytes=_int(
            document, "max_declaration_bytes", minimum=1, maximum=MAX_AGENT_CHAT_PROFILE_MAX_BYTES_BOUND
        ),
    )


def _parse_tool_call(document: Mapping[str, Any]) -> AgentChatProfileToolCall:
    _require_keys(document, _TOOL_CALL_KEYS, "dialect.tool_call")
    id_min_length = _int(document, "id_min_length", minimum=1, maximum=512)
    id_max_length = _int(document, "id_max_length", minimum=1, maximum=512)
    if id_min_length > id_max_length:
        _fail("dialect.tool_call", "ID minimum length exceeds maximum length.")
    return AgentChatProfileToolCall(
        id_min_length=id_min_length,
        id_max_length=id_max_length,
        arguments_max_bytes=_int(
            document, "arguments_max_bytes", minimum=1, maximum=MAX_AGENT_CHAT_PROFILE_MAX_BYTES_BOUND
        ),
    )


def parse_agent_chat_profile_document(document: Any) -> AgentChatProfileData:
    """Strictly validate one profile document into immutable DATA."""
    if not isinstance(document, Mapping):
        _fail("file", "Top level must be a JSON object.")
    _require_keys(document, _DOCUMENT_KEYS, "file")

    schema_version = document.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        _fail("schema_version", "Value must be an integer.")
    if schema_version != AGENT_CHAT_PROFILE_SCHEMA_VERSION:
        _fail("schema_version", "Value must be the current profile schema version.")

    profile_id = _str(document, "id", max_length=MAX_AGENT_CHAT_PROFILE_ID_LENGTH, pattern=_ID_RE)
    version = _str(document, "version", max_length=MAX_AGENT_CHAT_PROFILE_VERSION_LENGTH, pattern=_VERSION_RE)

    client_doc = document.get("client")
    if not isinstance(client_doc, Mapping):
        _fail("client", "Value must be an object.")
    client = _parse_client(client_doc)

    dialect_doc = document.get("dialect")
    if not isinstance(dialect_doc, Mapping):
        _fail("dialect", "Value must be an object.")
    _require_keys(dialect_doc, _DIALECT_KEYS, "dialect")

    reasoning_efforts = _parse_reasoning_efforts(dialect_doc)
    assistant_message_fields = _parse_assistant_message_fields(dialect_doc)
    tools_doc = dialect_doc.get("tools")
    if not isinstance(tools_doc, Mapping):
        _fail("dialect.tools", "Value must be an object.")
    tools = _parse_tools(tools_doc)
    tool_call_doc = dialect_doc.get("tool_call")
    if not isinstance(tool_call_doc, Mapping):
        _fail("dialect.tool_call", "Value must be an object.")
    tool_call = _parse_tool_call(tool_call_doc)

    # The exposed document is a deep, independent, immutable copy: later
    # mutation of the caller's original structure cannot change it, and the
    # fixture digest is computed over exactly this frozen content.
    frozen_document = _freeze_mapping(document)
    return AgentChatProfileData(
        document=frozen_document,
        schema_version=schema_version,
        profile_id=profile_id,
        version=version,
        client=client,
        reasoning_efforts=reasoning_efforts,
        assistant_message_fields=assistant_message_fields,
        tools=tools,
        tool_call=tool_call,
        fixture_sha256=canonical_profile_digest(frozen_document),
    )


def load_agent_chat_profile_file(path: str | Path) -> AgentChatProfileData:
    """Load one packaged/reviewed profile document file (bounded, strict)."""
    try:
        handle = Path(path).open("rb")
    except OSError as exc:
        raise AgentChatProfileDataError("file", "Profile file is not readable.") from exc
    with handle:
        raw = handle.read(MAX_AGENT_CHAT_PROFILE_FILE_BYTES + 1)
    if len(raw) > MAX_AGENT_CHAT_PROFILE_FILE_BYTES:
        _fail("file", "File exceeds the profile data size limit.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentChatProfileDataError("file", "File must be valid UTF-8 JSON.") from exc
    try:
        document = json.loads(
            text,
            object_pairs_hook=_strict_pairs_hook,
            parse_constant=_strict_constant,
        )
    except AgentChatProfileDataError:
        raise
    except json.JSONDecodeError as exc:
        raise AgentChatProfileDataError("file", "File is not valid JSON.") from exc
    return parse_agent_chat_profile_document(document)
