"""Shared neutral Chat profile engine for statically registered agent clients.

This module implements the first stage of native agent-harness Chat
integration (Hermes 0.22.5 and OpenCode 1.19.3, profile data revision 1).
It is deliberately *neutral*: one pure, data-driven decoder serves every
reviewed Chat profile, and per-harness modules are thin bindings of one
packaged profile document to this engine.

Trust model
-----------
- A profile is selected ONLY from complete, authenticated, server-side key
  metadata (the optional ``chat_client_module`` pin tuple
  ``{id, version, fixture_sha256}``).  Headers, User-Agent strings, model
  names, and client-request metadata never select or widen a profile.
- The decoder classifies and bounds one untrusted dialect.  It does not
  authenticate, route, reserve quota, perform HTTP, execute tools, sign
  requests, or grant authority.  Core policy, caps, routing, pricing, and
  PostgreSQL accounting remain authoritative.
- Absent pin (``None``) means the existing ``openai-default`` Chat behavior
  is unchanged.  A present pin that is malformed, unknown, stale, or
  digest-mismatched fails closed on Chat admission; it never silently
  degrades to the default and never affects the Responses endpoint.
- Tool names are client-local function declarations.  A name such as
  ``tool_search``, ``bash``, or ``task`` grants no hosted, routing, or
  execution authority.
- Chat history keeps the ordinary client-supplied trust model: bounded
  function/name/ID/argument shape plus exact call/result linkage within the
  request.  Historical tool-call names are NOT re-validated against today's
  top-level ``tools`` (native lazy discovery may remove a tool after a
  completed historical call, and Chat carries no declaration snapshots).
  Current declarations are validated against the profile vocabulary; a
  same-request ``tool_choice`` named-function reference must name a tool
  declared in that same request.
- Call/result linkage is tracked positionally within one request: each
  assistant tool-call ID enters a pending state, is consumed exactly once by
  its ``role: tool`` result, and every pending call must be resolved by the
  end of the message list.  Duplicate results, reused IDs (while pending or
  already resolved), unlinked results, and unresolved calls fail closed.
  No Responses HMAC, item-ID, or cross-request snapshot semantics are
  imported.
- The legacy function dialect (top-level ``functions``/``function_call``,
  assistant ``function_call``, ``role: function`` messages) is NOT qualified
  for agent Chat profiles and is rejected fail-closed; the ordinary
  openai-default path is unchanged.
- Numeric ceilings that mirror operator-configured gateway bounds (message
  counts, content/schema byte caps, ...) are NOT duplicated in the decoder:
  configured global bounds and the token estimator stay authoritative at the
  policy layer, while profile-specific ceilings are DATA-owned in the
  profile document.

The decoder is pure: no I/O, no logging, no request-state retention, no
mutation of caller-owned structures, and safe fixed error codes/positions
only (never raw content; diagnostics carry fixed field scopes and numeric
positions, not untrusted field names, schema fragments, or values).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from slaif_gateway.modules.agent_chat_profile_data import (
    AgentChatProfileAssistantField,
    AgentChatProfileClient,
    AgentChatProfileData,
    AgentChatProfileToolCall,
    AgentChatProfileTools,
)
from slaif_gateway.modules.contracts import CanonicalClientRequest, ModuleSelectionError

AGENT_CHAT_ENDPOINT = "/v1/chat/completions"

MAX_AGENT_CHAT_STREAM_OPTION_KEYS = 8

# Engine-structural bounds that no Settings value owns.  Numeric ceilings that
# mirror operator-configured gateway caps (message counts, schema/tool bytes,
# content sizes, ...) are intentionally NOT duplicated here: the configured
# global bounds and the token estimator remain authoritative at the policy
# layer, while profile-specific ceilings are DATA-owned in the profile
# document.  This keeps the decoder from silently defeating a configured
# deployment bound.

# Legacy function dialect is not qualified for agent Chat profiles.  The
# neutral decoder rejects these forms fail-closed with a dedicated code; the
# ordinary openai-default path is unchanged and keeps its existing behavior.
AGENT_CHAT_REJECTED_LEGACY_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {"functions", "function_call"}
)
# Top-level fields the neutral dialect accepts before core policy runs.  This
# mirrors the Chat field registry's non-rejecting surface exactly: hosted,
# lifecycle/state, and explicitly rejected fields are NOT part of any agent
# Chat profile and no profile data can add them.
AGENT_CHAT_STANDARD_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {
        "model",
        "messages",
        "temperature",
        "top_p",
        "stop",
        "seed",
        "user",
        "logit_bias",
        "logprobs",
        "top_logprobs",
        "presence_penalty",
        "frequency_penalty",
        "stream",
        "stream_options",
        "max_tokens",
        "max_completion_tokens",
        "n",
        "tools",
        "tool_choice",
        "functions",
        "function_call",
        "response_format",
        "metadata",
        "reasoning_effort",
        "parallel_tool_calls",
        "modalities",
        "audio",
        "prediction",
        "service_tier",
        "store",
    }
)

# Standard per-role message keys.  Profile data may add bounded string
# assistant fields only (see AgentChatProfileData.assistant_message_fields).
AGENT_CHAT_STANDARD_MESSAGE_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "system": frozenset({"role", "content"}),
        "developer": frozenset({"role", "content"}),
        "user": frozenset({"role", "content"}),
        "assistant": frozenset(
            {"role", "content", "tool_calls", "refusal", "function_call", "audio"}
        ),
        "tool": frozenset({"role", "content", "tool_call_id", "name"}),
        "function": frozenset({"role", "content", "name"}),
    }
)

AGENT_CHAT_KNOWN_ROLES: frozenset[str] = frozenset(AGENT_CHAT_STANDARD_MESSAGE_FIELDS)

_TOOL_CALL_ITEM_KEYS = frozenset({"id", "type", "function"})
_TOOL_CALL_FUNCTION_KEYS = frozenset({"name", "arguments"})
_DECLARATION_KEYS = frozenset({"type", "function"})
_DECLARATION_FUNCTION_KEYS = frozenset({"name", "description", "parameters"})
_TOOL_CHOICE_NAMED_KEYS = frozenset({"type", "function"})
_TOOL_CHOICE_FUNCTION_KEYS = frozenset({"name"})


class AgentChatModuleSelectionError(ModuleSelectionError):
    """A Chat module/pin selection failure (safe fixed codes, no echoes)."""


class AgentChatRequestError(ValueError):
    """A dialect-level Chat request rejection (safe codes and positions)."""

    def __init__(self, message: str, *, error_code: str, param: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.param = param


@dataclass(frozen=True, slots=True)
class AgentChatProfileSpec:
    """Executable, neutral Chat dialect facts consumed by the Gateway core.

    Compiled one-to-one from validated profile DATA.  The spec is the only
    profile surface the service layer may consume; it carries no content and
    grants no authority.  All facts default to the existing ordinary-OpenAI
    behavior when no profile is selected.
    """

    module_id: str
    module_version: str
    fixture_sha256: str
    provenance: AgentChatProfileClient
    reasoning_efforts: frozenset[str]
    assistant_message_fields: tuple[AgentChatProfileAssistantField, ...]
    tools: AgentChatProfileTools
    tool_call: AgentChatProfileToolCall


def compile_agent_chat_profile_spec(data: AgentChatProfileData) -> AgentChatProfileSpec:
    """Compile validated profile DATA into immutable executable facts."""
    return AgentChatProfileSpec(
        module_id=data.profile_id,
        module_version=data.version,
        fixture_sha256=data.fixture_sha256,
        provenance=data.client,
        reasoning_efforts=data.reasoning_efforts,
        assistant_message_fields=data.assistant_message_fields,
        tools=data.tools,
        tool_call=data.tool_call,
    )


class AgentChatClientModule(Protocol):
    """A statically registered, pure Chat client decoder (no authority)."""

    module_id: str
    module_version: str
    fixture_sha256: str
    policy_spec: AgentChatProfileSpec

    def normalize_chat(self, body: Mapping[str, object]) -> CanonicalClientRequest:
        """Validate/canonicalize one /v1/chat/completions dialect request."""
        ...

    def normalize(
        self, endpoint: str, body: Mapping[str, object]
    ) -> CanonicalClientRequest:
        """Normalize only the Chat endpoint; every other endpoint fails."""
        ...


class _DefaultAgentChatClientModule:
    """The concrete, pure, profile-bound decoder shared by all Chat profiles."""

    def __init__(self, spec: AgentChatProfileSpec) -> None:
        self.policy_spec = spec
        self.module_id = spec.module_id
        self.module_version = spec.module_version
        self.fixture_sha256 = spec.fixture_sha256
        self._assistant_fields = {
            field.name: field for field in spec.assistant_message_fields
        }

    def normalize(
        self, endpoint: str, body: Mapping[str, object]
    ) -> CanonicalClientRequest:
        if endpoint != AGENT_CHAT_ENDPOINT:
            raise AgentChatModuleSelectionError(
                "The selected Chat client module does not support this endpoint",
                error_code="unsupported_client_endpoint",
            )
        return self.normalize_chat(body)

    def normalize_chat(self, body: Mapping[str, object]) -> CanonicalClientRequest:
        if not isinstance(body, Mapping):
            raise AgentChatRequestError(
                "The Chat request body is not a mapping.",
                error_code="agent_chat_body_invalid",
            )
        declared_tool_names = self._validate_top_level(body)
        self._validate_messages(body.get("messages"), declared_tool_names=declared_tool_names)
        self._validate_tool_choice(body.get("tool_choice"), declared_tool_names)
        self._validate_stream_controls(body)

        canonical_body = copy.deepcopy(dict(body))
        return CanonicalClientRequest(
            module_id=self.module_id,
            module_version=self.module_version,
            endpoint=AGENT_CHAT_ENDPOINT,
            body=canonical_body,
            profile_facts={
                "agent_chat_module_id": self.module_id,
                "agent_chat_module_version": self.module_version,
                "agent_chat_fixture_sha256": self.fixture_sha256,
            },
        )

    # ------------------------------------------------------------------
    # Top-level dialect surface
    # ------------------------------------------------------------------

    def _validate_top_level(self, body: Mapping[str, object]) -> frozenset[str] | None:
        for field in body:
            if not isinstance(field, str) or field not in AGENT_CHAT_STANDARD_TOP_LEVEL_FIELDS:
                # Safe fixed scope: the raw (potentially untrusted) field name
                # is never echoed into diagnostics.
                raise AgentChatRequestError(
                    "A Chat request field is not enabled by this client profile.",
                    error_code="agent_chat_unknown_field",
                    param="top_level",
                )
        for field in AGENT_CHAT_REJECTED_LEGACY_TOP_LEVEL_FIELDS:
            if field in body:
                raise AgentChatRequestError(
                    "Legacy Chat function fields are not qualified for this client profile.",
                    error_code="agent_chat_legacy_functions_not_allowed",
                    param=field,
                )

        model = body.get("model")
        if not isinstance(model, str) or not model.strip():
            raise AgentChatRequestError(
                "The 'model' field must be a non-empty string.",
                error_code="agent_chat_field_invalid",
                param="model",
            )

        if body.get("messages") is None:
            raise AgentChatRequestError(
                "The 'messages' field is required.",
                error_code="agent_chat_field_invalid",
                param="messages",
            )

        reasoning_effort = body.get("reasoning_effort")
        if reasoning_effort is not None:
            if not isinstance(reasoning_effort, str) or reasoning_effort not in self.policy_spec.reasoning_efforts:
                raise AgentChatRequestError(
                    "The 'reasoning_effort' value is not enabled by this client profile.",
                    error_code="agent_chat_reasoning_effort_not_allowed",
                    param="reasoning_effort",
                )

        return self._validate_tools(body.get("tools"))

    def _validate_tools(self, value: object) -> frozenset[str] | None:
        if value is None:
            return None
        spec = self.policy_spec
        if not isinstance(value, list):
            raise AgentChatRequestError(
                "The 'tools' field must be a list.",
                error_code="agent_chat_field_invalid",
                param="tools",
            )
        if len(value) > spec.tools.max_declarations:
            raise AgentChatRequestError(
                "The 'tools' field declares more functions than this profile allows.",
                error_code="agent_chat_tool_count_exceeded",
                param="tools",
            )
        seen: set[str] = set()
        for index, declaration in enumerate(value):
            name = self._validate_tool_declaration(
                declaration, param=f"tools[{index}]"
            )
            if name in seen:
                raise AgentChatRequestError(
                    "The 'tools' field declares the same function twice.",
                    error_code="agent_chat_tool_repeated",
                    param=f"tools[{index}].function.name",
                )
            seen.add(name)
        return frozenset(seen)

    def _validate_tool_declaration(self, declaration: object, *, param: str) -> str:
        spec = self.policy_spec
        if not isinstance(declaration, Mapping):
            raise AgentChatRequestError(
                "Each tool declaration must be an object.",
                error_code="agent_chat_tool_invalid",
                param=param,
            )
        if set(declaration) != _DECLARATION_KEYS:
            raise AgentChatRequestError(
                "A tool declaration does not match the profile declaration form.",
                error_code="agent_chat_tool_declaration_form",
                param=param,
            )
        if declaration.get("type") != "function":
            raise AgentChatRequestError(
                "A tool declaration must use the nested function form.",
                error_code="agent_chat_tool_declaration_form",
                param=f"{param}.type",
            )
        function = declaration.get("function")
        if not isinstance(function, Mapping) or not set(function) <= _DECLARATION_FUNCTION_KEYS:
            raise AgentChatRequestError(
                "A tool declaration function block is malformed.",
                error_code="agent_chat_tool_declaration_form",
                param=f"{param}.function",
            )
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise AgentChatRequestError(
                "A tool declaration function name must be a non-empty string.",
                error_code="agent_chat_tool_declaration_form",
                param=f"{param}.function.name",
            )
        if name not in spec.tools.names:
            raise AgentChatRequestError(
                "A tool declaration name is not in this profile vocabulary.",
                error_code="agent_chat_tool_name_not_allowed",
                param=f"{param}.function.name",
            )
        description = function.get("description")
        if description is not None:
            if not isinstance(description, str):
                raise AgentChatRequestError(
                    "A tool declaration description must be a string.",
                    error_code="agent_chat_tool_declaration_form",
                    param=f"{param}.function.description",
                )
            if len(description.encode("utf-8")) > spec.tools.max_description_bytes:
                raise AgentChatRequestError(
                    "A tool declaration description is too large.",
                    error_code="agent_chat_field_too_large",
                    param=f"{param}.function.description",
                )
        parameters = function.get("parameters")
        if parameters is not None:
            self._validate_bounded_schema(parameters, param=f"{param}.function.parameters")
        self._validate_declaration_bytes(declaration, param=param)
        return name

    def _validate_declaration_bytes(self, declaration: Mapping[str, object], *, param: str) -> None:
        try:
            serialized = json.dumps(
                dict(declaration), sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
        except (TypeError, ValueError) as exc:
            raise AgentChatRequestError(
                "A tool declaration is not JSON-serializable.",
                error_code="agent_chat_tool_declaration_form",
                param=param,
            ) from exc
        if len(serialized.encode("ascii")) > self.policy_spec.tools.max_declaration_bytes:
            raise AgentChatRequestError(
                "A tool declaration is too large.",
                error_code="agent_chat_field_too_large",
                param=param,
            )

    def _validate_bounded_schema(self, value: object, *, param: str, depth: int = 1) -> None:
        spec = self.policy_spec
        if depth > spec.tools.max_schema_depth:
            raise AgentChatRequestError(
                "A tool declaration schema is nested too deeply.",
                error_code="agent_chat_schema_too_deep",
                param=param,
            )
        if isinstance(value, Mapping):
            if len(value) > spec.tools.max_schema_properties:
                raise AgentChatRequestError(
                    "A tool declaration schema object has too many members.",
                    error_code="agent_chat_schema_too_large",
                    param=param,
                )
            # Positional diagnostics only: schema property names are
            # untrusted content and are never echoed into error params.
            for position, (key, item) in enumerate(value.items()):
                if not isinstance(key, str) or not key:
                    raise AgentChatRequestError(
                        "A tool declaration schema key is malformed.",
                        error_code="agent_chat_schema_malformed",
                        param=param,
                    )
                self._validate_bounded_schema(
                    item, param=f"{param}.{position}", depth=depth + 1
                )
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._validate_bounded_schema(
                    item, param=f"{param}[{index}]", depth=depth + 1
                )
            return
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            return
        if isinstance(value, str):
            return
        raise AgentChatRequestError(
            "A tool declaration schema contains an unsupported value type.",
            error_code="agent_chat_schema_malformed",
            param=param,
        )

    def _validate_tool_choice(
        self, value: object, declared_tool_names: frozenset[str] | None
    ) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if value not in {"none", "auto", "required"}:
                raise AgentChatRequestError(
                    "The 'tool_choice' value is not enabled by this client profile.",
                    error_code="agent_chat_tool_choice_invalid",
                    param="tool_choice",
                )
            return
        if not isinstance(value, Mapping) or set(value) != _TOOL_CHOICE_NAMED_KEYS:
            raise AgentChatRequestError(
                "The 'tool_choice' object is malformed.",
                error_code="agent_chat_tool_choice_invalid",
                param="tool_choice",
            )
        if value.get("type") != "function":
            raise AgentChatRequestError(
                "A named 'tool_choice' must target a function.",
                error_code="agent_chat_tool_choice_invalid",
                param="tool_choice.type",
            )
        function = value.get("function")
        if not isinstance(function, Mapping) or set(function) != _TOOL_CHOICE_FUNCTION_KEYS:
            raise AgentChatRequestError(
                "A named 'tool_choice' function block is malformed.",
                error_code="agent_chat_tool_choice_invalid",
                param="tool_choice.function",
            )
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise AgentChatRequestError(
                "A named 'tool_choice' must name a non-empty function.",
                error_code="agent_chat_tool_choice_invalid",
                param="tool_choice.function.name",
            )
        # Absent/null tools mean NO functions are declared in this request,
        # so a named choice can never be satisfied and fails closed.
        declared = declared_tool_names if declared_tool_names is not None else frozenset()
        if name not in declared:
            raise AgentChatRequestError(
                "A named 'tool_choice' must reference a tool declared in this request.",
                error_code="agent_chat_tool_choice_not_declared",
                param="tool_choice.function.name",
            )

    def _validate_stream_controls(self, body: Mapping[str, object]) -> None:
        stream = body.get("stream")
        if stream is not None and not isinstance(stream, bool):
            raise AgentChatRequestError(
                "The 'stream' field must be a boolean.",
                error_code="agent_chat_field_invalid",
                param="stream",
            )
        stream_options = body.get("stream_options")
        if stream_options is None:
            return
        if not isinstance(stream_options, Mapping) or len(stream_options) > MAX_AGENT_CHAT_STREAM_OPTION_KEYS:
            raise AgentChatRequestError(
                "The 'stream_options' field is malformed.",
                error_code="agent_chat_field_invalid",
                param="stream_options",
            )
        for key, item in stream_options.items():
            if not isinstance(key, str) or not isinstance(item, bool):
                raise AgentChatRequestError(
                    "The 'stream_options' field is malformed.",
                    error_code="agent_chat_field_invalid",
                    param="stream_options",
                )

    # ------------------------------------------------------------------
    # Messages, tool calls, and exact call/result linkage
    # ------------------------------------------------------------------

    def _validate_messages(
        self, value: object, *, declared_tool_names: frozenset[str] | None
    ) -> None:
        _ = declared_tool_names
        if not isinstance(value, list):
            raise AgentChatRequestError(
                "The 'messages' field must be a list.",
                error_code="agent_chat_field_invalid",
                param="messages",
            )
        if not value:
            raise AgentChatRequestError(
                "The 'messages' field must be a non-empty list.",
                error_code="agent_chat_field_invalid",
                param="messages",
            )
        # Within-request positional call/result linkage: a call ID enters
        # ``pending`` when its assistant message is seen, is consumed exactly
        # once by its tool result, and must be fully resolved by the end of
        # the message list.  No HMAC, snapshot, or cross-request semantics.
        pending_tool_call_ids: set[str] = set()
        resolved_tool_call_ids: set[str] = set()
        for index, message in enumerate(value):
            param = f"messages[{index}]"
            if not isinstance(message, Mapping):
                raise AgentChatRequestError(
                    "Each message must be an object.",
                    error_code="agent_chat_message_invalid",
                    param=param,
                )
            role = message.get("role")
            if not isinstance(role, str) or not role.strip():
                raise AgentChatRequestError(
                    "Each message must include a non-empty string role.",
                    error_code="agent_chat_message_invalid",
                    param=f"{param}.role",
                )
            if role == "function":
                raise AgentChatRequestError(
                    "The legacy function role is not qualified for this client profile.",
                    error_code="agent_chat_legacy_functions_not_allowed",
                    param=f"{param}.role",
                )
            if role not in AGENT_CHAT_KNOWN_ROLES:
                raise AgentChatRequestError(
                    "A message role is not enabled by this client profile.",
                    error_code="agent_chat_role_not_allowed",
                    param=f"{param}.role",
                )
            allowed_keys = AGENT_CHAT_STANDARD_MESSAGE_FIELDS[role]
            if role == "assistant":
                allowed_keys = allowed_keys | frozenset(self._assistant_fields)
            for key in message:
                if not isinstance(key, str) or key not in allowed_keys:
                    # Safe fixed scope/index: the raw message key (untrusted
                    # content) is never echoed into diagnostics.
                    raise AgentChatRequestError(
                        "A message field is not enabled for this role.",
                        error_code="agent_chat_message_field_not_allowed",
                        param=param,
                    )
            self._validate_message_content(message.get("content"), role=role, param=param)
            if role == "assistant":
                for field_name, field in self._assistant_fields.items():
                    if field_name in message:
                        raw = message.get(field_name)
                        if not isinstance(raw, str):
                            raise AgentChatRequestError(
                                "An assistant profile field must be a string.",
                                error_code="agent_chat_message_field_invalid",
                                param=f"{param}.{field_name}",
                            )
                        if len(raw.encode("utf-8")) > field.max_bytes:
                            raise AgentChatRequestError(
                                "An assistant profile field is too large.",
                                error_code="agent_chat_field_too_large",
                                param=f"{param}.{field_name}",
                            )
                self._validate_assistant_extras(message, param=param)
                self._validate_tool_calls(
                    message.get("tool_calls"),
                    param=param,
                    pending_ids=pending_tool_call_ids,
                    resolved_ids=resolved_tool_call_ids,
                )
            elif role == "tool":
                self._consume_tool_result(
                    message,
                    param=param,
                    pending_ids=pending_tool_call_ids,
                    resolved_ids=resolved_tool_call_ids,
                )
        if pending_tool_call_ids:
            raise AgentChatRequestError(
                "A tool call in the message history has no linked result.",
                error_code="agent_chat_tool_call_unresolved",
                param="messages",
            )

    def _validate_message_content(self, value: object, *, role: str, param: str) -> None:
        if value is None:
            if role != "assistant":
                raise AgentChatRequestError(
                    "A null message content is not enabled for this role.",
                    error_code="agent_chat_message_content_invalid",
                    param=f"{param}.content",
                )
            return
        if isinstance(value, str):
            return
        if role == "tool":
            raise AgentChatRequestError(
                "A tool message content must be a string.",
                error_code="agent_chat_message_content_invalid",
                param=f"{param}.content",
            )
        if not isinstance(value, list):
            raise AgentChatRequestError(
                "A message content list is malformed.",
                error_code="agent_chat_message_content_invalid",
                param=f"{param}.content",
            )
        for part_index, part in enumerate(value):
            if isinstance(part, str):
                continue
            if not isinstance(part, Mapping):
                raise AgentChatRequestError(
                    "A message content part is malformed.",
                    error_code="agent_chat_message_content_invalid",
                    param=f"{param}.content[{part_index}]",
                )

    def _validate_assistant_extras(self, message: Mapping[str, object], *, param: str) -> None:
        if "audio" in message:
            raise AgentChatRequestError(
                "Assistant previous-audio references are not enabled by this gateway.",
                error_code="agent_chat_assistant_audio_not_allowed",
                param=f"{param}.audio",
            )
        if "function_call" in message:
            raise AgentChatRequestError(
                "Legacy Chat function fields are not qualified for this client profile.",
                error_code="agent_chat_legacy_functions_not_allowed",
                param=f"{param}.function_call",
            )
        refusal = message.get("refusal")
        if refusal is not None:
            if not isinstance(refusal, str):
                raise AgentChatRequestError(
                    "An assistant refusal field is malformed.",
                    error_code="agent_chat_message_field_invalid",
                    param=f"{param}.refusal",
                )

    def _validate_tool_calls(
        self,
        value: object,
        *,
        param: str,
        pending_ids: set[str],
        resolved_ids: set[str],
    ) -> None:
        spec = self.policy_spec
        if value is None:
            return
        if not isinstance(value, list):
            raise AgentChatRequestError(
                "The 'tool_calls' field must be a list.",
                error_code="agent_chat_tool_calls_invalid",
                param=param,
            )
        for index, call in enumerate(value):
            call_param = f"{param}.tool_calls[{index}]"
            if not isinstance(call, Mapping) or set(call) != _TOOL_CALL_ITEM_KEYS:
                raise AgentChatRequestError(
                    "A tool call item is malformed.",
                    error_code="agent_chat_tool_call_invalid",
                    param=call_param,
                )
            if call.get("type") != "function":
                raise AgentChatRequestError(
                    "A tool call must use the function type.",
                    error_code="agent_chat_tool_call_invalid",
                    param=f"{call_param}.type",
                )
            call_id = call.get("id")
            if not isinstance(call_id, str) or not (
                spec.tool_call.id_min_length
                <= len(call_id.encode("utf-8"))
                <= spec.tool_call.id_max_length
            ):
                raise AgentChatRequestError(
                    "A tool call ID is outside the profile grammar.",
                    error_code="agent_chat_tool_call_id_invalid",
                    param=f"{call_param}.id",
                )
            if call_id in pending_ids or call_id in resolved_ids:
                raise AgentChatRequestError(
                    "A tool call ID is reused in the message history.",
                    error_code="agent_chat_tool_call_id_reused",
                    param=f"{call_param}.id",
                )
            pending_ids.add(call_id)
            function = call.get("function")
            if not isinstance(function, Mapping) or set(function) != _TOOL_CALL_FUNCTION_KEYS:
                raise AgentChatRequestError(
                    "A tool call function block is malformed.",
                    error_code="agent_chat_tool_call_invalid",
                    param=f"{call_param}.function",
                )
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                raise AgentChatRequestError(
                    "A tool call function name is malformed.",
                    error_code="agent_chat_tool_call_invalid",
                    param=f"{call_param}.function.name",
                )
            # Historical call names are NOT re-checked against the current
            # declaration set (bounded shape only; see module docstring).
            arguments = function.get("arguments")
            if not isinstance(arguments, str):
                raise AgentChatRequestError(
                    "A tool call arguments value must be a JSON string.",
                    error_code="agent_chat_tool_call_arguments_invalid",
                    param=f"{call_param}.function.arguments",
                )
            if len(arguments.encode("utf-8")) > spec.tool_call.arguments_max_bytes:
                raise AgentChatRequestError(
                    "A tool call arguments value is too large.",
                    error_code="agent_chat_field_too_large",
                    param=f"{call_param}.function.arguments",
                )
            try:
                json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise AgentChatRequestError(
                    "A tool call arguments value is not valid JSON.",
                    error_code="agent_chat_tool_call_arguments_invalid",
                    param=f"{call_param}.function.arguments",
                ) from exc

    def _consume_tool_result(
        self,
        message: Mapping[str, object],
        *,
        param: str,
        pending_ids: set[str],
        resolved_ids: set[str],
    ) -> None:
        spec = self.policy_spec
        tool_call_id = message.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not (
            spec.tool_call.id_min_length
            <= len(tool_call_id.encode("utf-8"))
            <= spec.tool_call.id_max_length
        ):
            raise AgentChatRequestError(
                "A tool message tool_call_id is outside the profile grammar.",
                error_code="agent_chat_tool_call_id_invalid",
                param=f"{param}.tool_call_id",
            )
        if tool_call_id in resolved_ids:
            raise AgentChatRequestError(
                "A tool call ID has more than one linked result.",
                error_code="agent_chat_tool_result_duplicate",
                param=f"{param}.tool_call_id",
            )
        if tool_call_id not in pending_ids:
            raise AgentChatRequestError(
                "A tool message result is not linked to a preceding tool call.",
                error_code="agent_chat_tool_result_not_linked",
                param=f"{param}.tool_call_id",
            )
        pending_ids.discard(tool_call_id)
        resolved_ids.add(tool_call_id)


# ----------------------------------------------------------------------
# Finite static registry and server-side pin selection
# ----------------------------------------------------------------------

_AGENT_CHAT_MODULE_ENTRIES: dict[str, AgentChatClientModule] = {}
AGENT_CHAT_CLIENT_MODULE_REGISTRY: Mapping[str, AgentChatClientModule] = MappingProxyType(
    _AGENT_CHAT_MODULE_ENTRIES
)


def register_agent_chat_client_module(
    module: object, *, expected_module_id: str
) -> None:
    """Statically register one reviewed Chat module (finite, per ID).

    ``expected_module_id`` is a SOURCE literal supplied by the statically
    shipped harness module; the profile DATA's ``id`` must match it exactly.
    Data therefore cannot choose or widen its own registry identity: an
    arbitrary valid document id only becomes resolvable when a source file
    explicitly binds that literal to it.

    Each module ID may be registered exactly once.  Re-registering the same
    identity is an idempotent no-op (repeated same-config initialization);
    registering a different identity under an existing ID fails closed.
    Distinct module IDs (Hermes, OpenCode, ...) register independently;
    registration happens at import time of statically shipped harness
    modules only - there is no dynamic import or plugin path.
    """
    if (
        not isinstance(module, _DefaultAgentChatClientModule)
        or not isinstance(getattr(module, "policy_spec", None), AgentChatProfileSpec)
    ):
        raise AgentChatModuleSelectionError(
            "Chat client module is not a valid neutral Chat module",
            error_code="unsupported_client_module",
        )
    if not isinstance(expected_module_id, str) or not expected_module_id:
        raise AgentChatModuleSelectionError(
            "Chat client module expected identifier is invalid",
            error_code="chat_client_module_identity_mismatch",
        )
    module_id = module.module_id
    if module_id != expected_module_id:
        raise AgentChatModuleSelectionError(
            "Chat client module identity does not match its expected identifier",
            error_code="chat_client_module_identity_mismatch",
        )
    current = _AGENT_CHAT_MODULE_ENTRIES.get(module_id)
    if current is not None:
        if (
            current.module_version == module.module_version
            and current.fixture_sha256 == module.fixture_sha256
        ):
            return
        raise AgentChatModuleSelectionError(
            "A different Chat client module identity is already registered",
            error_code="chat_client_module_conflict",
        )
    _AGENT_CHAT_MODULE_ENTRIES[module_id] = module


def get_agent_chat_client_module(module_id: str) -> AgentChatClientModule:
    """Resolve only a literal, registered Chat client-module identifier."""
    if not isinstance(module_id, str):
        raise AgentChatModuleSelectionError(
            "Chat client module identifier is invalid",
            error_code="client_module_invalid",
        )
    module = _AGENT_CHAT_MODULE_ENTRIES.get(module_id)
    if module is None:
        raise AgentChatModuleSelectionError(
            "Chat client module is not registered",
            error_code="unsupported_client_module",
        )
    return module


def resolve_chat_client_module(raw_pin: object) -> AgentChatClientModule | None:
    """Select a Chat module ONLY from complete server-side key metadata.

    ``None`` (absent pin) preserves the existing default Chat behavior.  A
    present pin must be exactly ``{id, version, fixture_sha256}`` with string
    values matching one registered module; unknown IDs (including
    Responses-only modules), stale versions, and digest mismatches fail
    closed before admission.
    """
    if raw_pin is None:
        return None
    if not isinstance(raw_pin, Mapping) or set(raw_pin) != {"id", "version", "fixture_sha256"}:
        raise AgentChatModuleSelectionError(
            "Chat client-module metadata is invalid",
            error_code="chat_client_module_metadata_invalid",
        )
    module_id = raw_pin.get("id")
    module_version = raw_pin.get("version")
    fixture_sha256 = raw_pin.get("fixture_sha256")
    if (
        not isinstance(module_id, str)
        or not isinstance(module_version, str)
        or not isinstance(fixture_sha256, str)
    ):
        raise AgentChatModuleSelectionError(
            "Chat client-module metadata is invalid",
            error_code="chat_client_module_metadata_invalid",
        )
    module = get_agent_chat_client_module(module_id)
    if module.module_version != module_version:
        raise AgentChatModuleSelectionError(
            "Chat client-module fixture metadata does not match",
            error_code="chat_client_module_fixture_mismatch",
        )
    if module.fixture_sha256 != fixture_sha256:
        raise AgentChatModuleSelectionError(
            "Chat client-module fixture metadata does not match",
            error_code="chat_client_module_fixture_mismatch",
        )
    return module


def agent_chat_profile_metadata(module: AgentChatClientModule) -> dict[str, str]:
    """Return the safe reviewed pin tuple for operator key metadata."""
    spec = getattr(module, "policy_spec", None)
    if not isinstance(spec, AgentChatProfileSpec):
        raise AgentChatModuleSelectionError(
            "Chat client module does not expose reviewed profile facts",
            error_code="chat_client_module_metadata_invalid",
        )
    return {
        "id": module.module_id,
        "version": module.module_version,
        "fixture_sha256": module.fixture_sha256,
    }


def canonicalize_chat_client_module_pin(raw_pin: object) -> dict[str, str] | None:
    """Authoring-time strict canonicalization of an operator Chat pin.

    ``None`` (absent or explicit clear) yields ``None``. A present pin
    must be exactly ``{id, version, fixture_sha256}`` with string values
    resolving to a CURRENTLY REGISTERED module (registry, version, and
    fixture digest; fail-closed). Returns the canonical tuple from
    :func:`agent_chat_profile_metadata` so stored pins are canonical
    today. Raises :class:`AgentChatModuleSelectionError` on malformed,
    stale, or unknown pins.
    """
    if raw_pin is None:
        return None
    module = resolve_chat_client_module(raw_pin)
    return agent_chat_profile_metadata(module)


def build_agent_chat_client_module(data: AgentChatProfileData) -> AgentChatClientModule:
    """Bind one validated profile document to the neutral engine."""
    return _DefaultAgentChatClientModule(compile_agent_chat_profile_spec(data))


def bootstrap_agent_chat_client_modules() -> None:
    """One-shot process bootstrap: import the statically shipped Chat modules.

    Shared factory boundary used by the HTTP app factory and the operator
    CLI key commands, mirroring ``bootstrap_codex_compatibility_profile``.
    Importing a shipped harness module performs its source-literal
    registration into the finite Chat registry as a side effect; repeated
    same-config initialization is an idempotent no-op. The imports below
    are static source literals - there is no dynamic import of
    operator-supplied module paths, no plugin loader, and no executable
    rule.
    """
    # Static shipped Chat harness bindings (registration side effect):
    from slaif_gateway.modules.clients import hermes_0225_chat as _hermes_0225_chat  # noqa: F401
    from slaif_gateway.modules.clients import opencode_1193_chat as _opencode_1193_chat  # noqa: F401
