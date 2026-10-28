"""Strict operator-authoring validation for key-level Responses policy blocks.

Shared authoring validator for the ``responses_policy`` metadata block on
STANDARD gateway keys. The finite contract is derived from the current
runtime consumers and the current existing producers, never from template
rules or product names.

Runtime consumers (all fail closed):

- ``_responses_policy_capability_allowed`` (responses_request_policy) reads
  ``version`` (exactly the integer 1, bool/float rejected) and
  ``allowed_capabilities`` (a list of ``KNOWN_RESPONSES_CAPABILITIES``
  without duplicates); any known capability may appear in a key policy,
  including route-level grants such as ``text``, ``stateless``, and
  ``image_input``.
- The Codex key-gate predicates encode the prerequisite closure enforced
  here: client tools require the request envelope; streaming tool events
  require client tools; encrypted reasoning replay requires the request
  envelope; compaction requires streaming tool events plus encrypted
  reasoning replay.
- ``resolve_responses_client_module`` resolves a client module ONLY from an
  exact ``{id, version, fixture_sha256}`` pin against the static registry
  and fails closed on stale pins. A pin is optional: without one the
  runtime falls back to its existing default/legacy resolution, so
  authoring must not demand a pin for every Codex grant.

Capability vocabulary: the authoring contract accepts the finite
``SUPPORTED_RESPONSES_CAPABILITIES`` set - the runtime-known capabilities
minus the reserved generic authority shapes (``background``, ``storage``,
``multimodal``). Those reserved names are recognized but fail closed as
positive authored grants: they are the stateful/background/media authority
shapes the key policy must not grant. Ordinary Responses function/custom
tool declarations are distinct from the Codex ``additional_tools``
namespaces and keep their own reviewed pairing.

Reviewed existing producers (their finite shapes are accepted):

- the standard key-template producer, which emits ``allowed_local_tool_types``
  ``[]``, ``hosted_tools_allowed`` ``[]``, and the ``stateful``/``storage``/
  ``background``/``multimodal`` flags all ``false``, with an optional
  ``notes`` string;
- the function/custom template variants, which pair the ``function_tools``
  capability with the ``function`` local tool type and the ``custom_tools``
  capability with the ``custom`` local tool type (either or both);
- the admin Qwen Codex policy, which emits Codex gate capabilities plus
  ``image_input`` and an exact client-module pin;
- the Codex qualification policy, which emits the five Codex gates, both
  local tool types, and an exact client-module pin.

Local tool type pairing follows the reviewed producer/module contracts:
the ``function`` type requires the ``function_tools`` policy capability or
the Codex client-tools grant, the ``custom`` type requires the
``custom_tools`` policy capability or the Codex client-tools grant, and
the Codex client-tools grant requires the full local tool type set.

The inert legacy metadata fields grant NO runtime authority (no request
path reads them); they are validated to exactly the safe literals above and
preserved verbatim in the canonical output so exports round-trip. Unknown
fields, unknown or reserved capability values, a non-empty
``hosted_tools_allowed`` list, or any ``true`` inert flag remain rejected.
Template-only rules (base text/stateless requirements, template hosted
authority, the pinned historical 0147 tuple) are deliberately NOT applied
to standard keys.

Canonical output is idempotent: validating its own output yields the same
block. Operator errors use fixed safe vocabulary and field paths only; they
never echo author-supplied field names, values, or file contents.
"""

from __future__ import annotations

from collections.abc import Mapping

from slaif_gateway.modules.clients.registry import get_client_module
from slaif_gateway.modules.contracts import ModuleSelectionError
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.responses_route_capabilities import (
    KNOWN_RESPONSES_CAPABILITIES,
    RESPONSES_CAPABILITY_BACKGROUND,
    RESPONSES_CAPABILITY_CUSTOM_TOOLS,
    RESPONSES_CAPABILITY_FUNCTION_TOOLS,
    RESPONSES_CAPABILITY_MULTIMODAL,
    RESPONSES_CAPABILITY_STORAGE,
)

# Codex capability family: the capabilities whose key-level grants the
# gateway's Codex gate predicates consume.
_CODEX_CAPABILITY_PREFIX = "codex_"
CODEX_RESPONSES_CAPABILITIES: frozenset[str] = frozenset(
    capability
    for capability in KNOWN_RESPONSES_CAPABILITIES
    if capability.startswith(_CODEX_CAPABILITY_PREFIX)
)

# Reserved generic authority shapes: recognized runtime names that the key
# policy must never grant as a positive authored capability.
_RESERVED_RESPONSES_CAPABILITIES: frozenset[str] = frozenset(
    {
        RESPONSES_CAPABILITY_BACKGROUND,
        RESPONSES_CAPABILITY_STORAGE,
        RESPONSES_CAPABILITY_MULTIMODAL,
    }
)

#: Finite capability vocabulary accepted by the authoring contract.
SUPPORTED_RESPONSES_CAPABILITIES: frozenset[str] = frozenset(
    KNOWN_RESPONSES_CAPABILITIES - _RESERVED_RESPONSES_CAPABILITIES
)

CODEX_REQUEST_ENVELOPE = "codex_request_envelope"
CODEX_CLIENT_TOOLS = "codex_client_tools"

# Direct prerequisites exactly as the runtime capability predicates encode
# them (transitive closure is computed at validation time).
_CAPABILITY_PREREQUISITES: dict[str, frozenset[str]] = {
    CODEX_REQUEST_ENVELOPE: frozenset(),
    CODEX_CLIENT_TOOLS: frozenset({CODEX_REQUEST_ENVELOPE}),
    "codex_streaming_tool_events": frozenset({CODEX_CLIENT_TOOLS}),
    "codex_encrypted_reasoning_replay": frozenset({CODEX_REQUEST_ENVELOPE}),
    "codex_compaction": frozenset(
        {
            "codex_streaming_tool_events",
            "codex_encrypted_reasoning_replay",
        }
    ),
}

# Finite top-level shapes accepted: the core contract plus the inert legacy
# metadata emitted by the existing standard template producer.
_RESPONSES_POLICY_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "allowed_capabilities",
        "allowed_local_tool_types",
        "client_module",
        "hosted_tools_allowed",
        "stateful",
        "storage",
        "background",
        "multimodal",
        "notes",
    }
)
_INERT_FALSE_FLAGS: tuple[str, ...] = ("stateful", "storage", "background", "multimodal")
_RESPONSES_POLICY_VERSION = 1
_LOCAL_TOOL_TYPES: tuple[str, ...] = ("function", "custom")
_CLIENT_MODULE_KEYS: frozenset[str] = frozenset({"id", "version", "fixture_sha256"})
_MAX_RESPONSES_NOTES_LENGTH = 1000

MIGRATION_HINT = (
    "Run the reviewed client-module migration for this key before re-pinning "
    "a changed module identity."
)


def _raise(field: str, message: str) -> None:
    raise InvalidGatewayKeyPolicyError(message, param=field)


def _prerequisite_closure(capability: str) -> frozenset[str]:
    """Transitive prerequisites for one capability."""
    seen: set[str] = set()
    stack = [capability]
    while stack:
        current = stack.pop()
        for prerequisite in _CAPABILITY_PREREQUISITES.get(current, frozenset()):
            if prerequisite not in seen:
                seen.add(prerequisite)
                stack.append(prerequisite)
    return frozenset(seen)


def _is_codex_client_module(module: object) -> bool:
    """Structural check (reviewed fixture identity), never a name inference."""
    fixture = getattr(module, "fixture_sha256", None)
    return isinstance(fixture, str)


def validate_key_responses_policy(
    policy: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Validate one operator-authored key-level Responses policy block.

    Returns the canonical block (sorted capability list, stable local tool
    type order, safe inert metadata preserved verbatim) or ``None`` for an
    absent block. Raises :class:`InvalidGatewayKeyPolicyError` with a fixed
    safe message that names only the offending field path, never an
    author-supplied value.

    Presence semantics (deliberate, documented):

    - ``allowed_capabilities``: omitted, ``null``, or ``[]`` all mean "no
      key-level capability grant"; the canonical output omits the key in
      that case (an empty list is inert at the runtime and never emitted).
      Only the finite supported vocabulary is accepted; reserved generic
      authority names (``background``, ``storage``, ``multimodal``) fail
      closed.
    - ``allowed_local_tool_types``: omitted, ``null``, or ``[]`` are inert
      and omitted from the canonical output; a non-empty list requires the
      matching reviewed capability (``function_tools`` or
      ``custom_tools``, or the Codex client-tools grant) for each type, and
      the Codex client-tools grant requires exactly the full local tool
      type set.
    - ``client_module``: optional; when present it must be an exact
      registered Codex module identity. Module identity never grants
      permission by itself, so a retained pin with no or empty capability
      grants is a valid deauthorization state.
    """
    if policy is None:
        return None
    if not isinstance(policy, Mapping):
        _raise("responses_policy", "Responses policy must be an object.")
    if set(policy) - _RESPONSES_POLICY_ALLOWED_KEYS:
        _raise(
            "responses_policy",
            "Responses policy contains unsupported fields.",
        )

    version = policy.get("version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != _RESPONSES_POLICY_VERSION
    ):
        _raise(
            "responses_policy.version",
            f"Responses policy version must be exactly {_RESPONSES_POLICY_VERSION}.",
        )

    capabilities: list[str] = []
    raw_capabilities = policy.get("allowed_capabilities")
    if raw_capabilities is not None:
        if not isinstance(raw_capabilities, list):
            _raise(
                "responses_policy.allowed_capabilities",
                "Responses allowed capabilities must be a list of known capability names or null.",
            )
        for item in raw_capabilities:
            if (
                not isinstance(item, str)
                or not item
                or item not in SUPPORTED_RESPONSES_CAPABILITIES
            ):
                _raise(
                    "responses_policy.allowed_capabilities",
                    "Responses allowed capabilities must be known capability names.",
                )
            if item in capabilities:
                _raise(
                    "responses_policy.allowed_capabilities",
                    "Responses allowed capabilities must not repeat a capability.",
                )
            capabilities.append(item)

    for capability in sorted(capabilities):
        if capability not in CODEX_RESPONSES_CAPABILITIES:
            continue
        missing = sorted(_prerequisite_closure(capability) - set(capabilities))
        if missing:
            _raise(
                "responses_policy.allowed_capabilities",
                f"Capability {capability} requires {', '.join(missing)}.",
            )

    local_tool_types: list[str] = []
    raw_local_tool_types = policy.get("allowed_local_tool_types")
    if raw_local_tool_types is not None:
        if not isinstance(raw_local_tool_types, list):
            _raise(
                "responses_policy.allowed_local_tool_types",
                "Responses allowed local tool types must be a list of tool type names or null.",
            )
        for item in raw_local_tool_types:
            if not isinstance(item, str) or item not in _LOCAL_TOOL_TYPES:
                _raise(
                    "responses_policy.allowed_local_tool_types",
                    "Responses allowed local tool types are limited to the known local tool types.",
                )
            if item in local_tool_types:
                _raise(
                    "responses_policy.allowed_local_tool_types",
                    "Responses allowed local tool types must not repeat a tool type.",
                )
            local_tool_types.append(item)

    has_client_tools = CODEX_CLIENT_TOOLS in capabilities
    function_supported = (
        RESPONSES_CAPABILITY_FUNCTION_TOOLS in capabilities or has_client_tools
    )
    custom_supported = (
        RESPONSES_CAPABILITY_CUSTOM_TOOLS in capabilities or has_client_tools
    )
    if "function" in local_tool_types and not function_supported:
        _raise(
            "responses_policy.allowed_local_tool_types",
            "Responses function local tool type requires the reviewed function-tool policy capability.",
        )
    if "custom" in local_tool_types and not custom_supported:
        _raise(
            "responses_policy.allowed_local_tool_types",
            "Responses custom local tool type requires the reviewed custom-tool policy capability.",
        )
    if has_client_tools and sorted(local_tool_types) != sorted(_LOCAL_TOOL_TYPES):
        _raise(
            "responses_policy.allowed_local_tool_types",
            "The Codex client-tools capability requires the full local tool type set.",
        )

    client_module = policy.get("client_module")
    canonical_module: dict[str, object] | None = None
    if client_module is not None:
        if not isinstance(client_module, Mapping) or set(client_module) != _CLIENT_MODULE_KEYS:
            _raise(
                "responses_policy.client_module",
                "Client module identity must contain exactly id, version, and fixture_sha256.",
            )
        module_id = client_module.get("id")
        module_version = client_module.get("version")
        fixture_sha256 = client_module.get("fixture_sha256")
        for value, field in (
            (module_id, "id"),
            (module_version, "version"),
            (fixture_sha256, "fixture_sha256"),
        ):
            if not isinstance(value, str) or not value.strip():
                _raise(
                    f"responses_policy.client_module.{field}",
                    f"Client module {field} must be a non-empty string.",
                )
        try:
            module = get_client_module(module_id)
        except ModuleSelectionError:
            _raise(
                "responses_policy.client_module.id",
                "Client module is not registered in this installation.",
            )
        if not _is_codex_client_module(module):
            _raise(
                "responses_policy.client_module.id",
                "Client module is not a Codex Responses module.",
            )
        if module.module_version != module_version or module.fixture_sha256 != fixture_sha256:
            _raise(
                "responses_policy.client_module",
                "Client module version or fixture does not match the current registered "
                f"identity. {MIGRATION_HINT}",
            )
        canonical_module = {
            "id": module_id,
            "version": module_version,
            "fixture_sha256": fixture_sha256,
        }

    canonical: dict[str, object] = {"version": _RESPONSES_POLICY_VERSION}
    if capabilities:
        canonical["allowed_capabilities"] = sorted(capabilities)
    if local_tool_types:
        canonical["allowed_local_tool_types"] = [
            tool_type for tool_type in _LOCAL_TOOL_TYPES if tool_type in local_tool_types
        ]
    raw_hosted = policy.get("hosted_tools_allowed")
    if raw_hosted is not None:
        if not isinstance(raw_hosted, list) or raw_hosted:
            _raise(
                "responses_policy.hosted_tools_allowed",
                "Responses hosted tools are unsupported for standard keys.",
            )
        canonical["hosted_tools_allowed"] = []
    for flag in _INERT_FALSE_FLAGS:
        raw_flag = policy.get(flag)
        if raw_flag is None:
            continue
        if raw_flag is not False:
            _raise(
                f"responses_policy.{flag}",
                f"Responses policy flag {flag} must be false for standard keys.",
            )
        canonical[flag] = False
    raw_notes = policy.get("notes")
    if raw_notes is not None:
        if not isinstance(raw_notes, str):
            _raise(
                "responses_policy.notes",
                "Responses policy notes must be a string.",
            )
        notes = raw_notes.strip()
        if len(notes) > _MAX_RESPONSES_NOTES_LENGTH:
            _raise(
                "responses_policy.notes",
                f"Responses policy notes exceed {_MAX_RESPONSES_NOTES_LENGTH} characters.",
            )
        if notes:
            canonical["notes"] = notes
    if canonical_module is not None:
        canonical["client_module"] = canonical_module
    return canonical
