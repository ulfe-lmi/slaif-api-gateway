"""Pinned Codex CLI 0.162.1 responses-lite additional-tools client dialect.

This module carries the separately qualified 0.162.1 profile: the client
builds a single ``additional_tools`` developer item carrying an optional
``at_``-style identifier and a bounded set of client-local ``function``
declarations.  The namespace vocabulary is strictly limited to the built-in
namespaces ``functions`` and ``multi_agent_v1`` plus validated bounded
``mcp__codex_apps__`` plugin namespaces.  Tool names in every namespace are
validated against a bounded lower-case pattern with function-only types,
per-namespace uniqueness, and the approved finite cardinality and byte
limits; the official isolated capture records a 12-tool sample of the
built-in vocabulary, not its complete set, so no exact tool list is pinned.
Declarations are client-operated function facts: they grant no
provider-hosted, connector, or Gateway-execution authority, and the item ID
is a bounded opaque value with no identity, replay, or audit derivation.

For the registered Local Coding pair only, the gateway lowers the single
validated initial declaration to the existing top-level ``tools`` namespace
array immediately before provider serialization and HMAC signing: the
declaration item and its ID never reach the provider body while
validation, admission, and accounting still run over the original
declaration.  A non-initial or repeated declaration, or a mixed
top-level declaration, fails closed.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_POLICY_SPEC,
    Codex0149ResponsesClientModule,
)
from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    ModuleSelectionError,
)

CODEX_0162_CLIENT_MODULE_ID = "codex-0.162-responses-v1"
CODEX_0162_CLIENT_MODULE_VERSION = "2"
CODEX_0162_CLI_VERSION = "0.162.1"
CODEX_0162_PROFILE_ID = "additional-tools-profile-v2"
CODEX_0162_FIXTURE_SHA256 = (
    "b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85"
)
CODEX_0162_FIXTURE_RELATIVE_PATH = (
    "tests/fixtures/codex/0.162.1/additional-tools-profile-v2.json"
)
CODEX_0162_SOURCE_CONTRACT_TAG = "rust-v0.162.1"
CODEX_0162_SOURCE_CONTRACT_COMMIT = "092d3acd6bec3e3a14bdc7e7a2810ab628ab759d"
CODEX_0162_OFFICIAL_CAPTURE_ARCHIVE_SHA256 = (
    "a676f5722aae0d86cbe3764332f08eab1fdd89dc0a300b3ad4ffbf48611fa3e3"
)
CODEX_0162_OFFICIAL_CAPTURE_BINARY_SHA256 = (
    "628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1"
)

# Strict built-in namespace vocabulary for the 0.162 profile.  Tool names
# inside these namespaces are bounded-validated (pattern, function type,
# uniqueness, finite limits) exactly like the plugin namespaces: the official
# isolated capture observed 7 functions and 5 multi_agent_v1 tools, a sample
# of a larger built-in vocabulary (the operator profile reports 11
# functions), so no exact built-in tool list is pinned.
CODEX_0162_BUILTIN_NAMESPACES = frozenset({"functions", "multi_agent_v1"})

_CODEX_0162_MCP_NAMESPACE_PATTERN = re.compile(r"^mcp__codex_apps__[a-z][a-z0-9_.-]{0,63}$")
_CODEX_0162_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
# Version-2 connector rule: approved mcp__codex_apps__ connector namespaces
# additionally accept a bounded single leading underscore preceding a
# lowercase-letter-led name.  The character vocabulary and the 64-character
# total name cap are unchanged; builtin namespaces keep the
# lowercase-letter-first rule.  Empty, all-underscore, doubled-underscore,
# uppercase/number-first after the underscore, and non-vocabulary names are
# rejected.  Accepted names are preserved exactly; nothing is stripped,
# renamed, or normalized.
_CODEX_0162_CONNECTOR_TOOL_NAME_PATTERN = re.compile(
    r"^(?:[a-z][a-z0-9_.-]{0,63}|_[a-z][a-z0-9_.-]{0,62})$"
)

# Finite 0.162 profile ceilings supporting the observed 197-tool / 11-namespace
# operator summary.  The older modules keep their smaller limits.
CODEX_0162_MAX_NAMESPACES = 16
CODEX_0162_MAX_TOTAL_TOOLS = 256
CODEX_0162_MAX_NAMESPACE_TOOLS = 256
CODEX_0162_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES = 262_144
CODEX_0162_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES = 4_096

_PROFILE_FACTS = MappingProxyType(
    {
        "client_module_id": CODEX_0162_CLIENT_MODULE_ID,
        "client_module_version": CODEX_0162_CLIENT_MODULE_VERSION,
        "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
        "source_contract_tag": CODEX_0162_SOURCE_CONTRACT_TAG,
        "source_contract_commit": CODEX_0162_SOURCE_CONTRACT_COMMIT,
    }
)


def _error(message: str, code: str = "codex_0162_request_invalid") -> ModuleSelectionError:
    return ModuleSelectionError(message, error_code=code)


def codex_0162_additional_tools_taxonomy_for(
    namespaces: object,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    """Validate one bounded 0.162 local declaration set in declared order.

    Returns the canonical (namespace, (tool, type)) sequence in declared
    order, or None when the declaration falls outside the strict 0.162
    namespace vocabulary or its bounded tool validation.  Field, schema,
    byte, and authority validation stays in the shared request policy, which
    re-checks every returned name and type exactly.
    """
    if not isinstance(namespaces, list) or not namespaces:
        return None
    if len(namespaces) > CODEX_0162_MAX_NAMESPACES:
        return None
    seen_namespaces: set[str] = set()
    total_tools = 0
    ordered: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for namespace in namespaces:
        if not isinstance(namespace, Mapping):
            return None
        namespace_name = namespace.get("name")
        if (
            not isinstance(namespace_name, str)
            or not namespace_name
            or namespace_name in seen_namespaces
        ):
            return None
        tools = namespace.get("tools")
        if not isinstance(tools, list) or not tools:
            return None
        is_builtin = namespace_name in CODEX_0162_BUILTIN_NAMESPACES
        is_dynamic = _CODEX_0162_MCP_NAMESPACE_PATTERN.fullmatch(namespace_name) is not None
        if not is_builtin and not is_dynamic:
            return None
        if len(tools) > CODEX_0162_MAX_NAMESPACE_TOOLS:
            return None
        declared_names: set[str] = set()
        declared_tools: list[tuple[str, str]] = []
        name_pattern = (
            _CODEX_0162_CONNECTOR_TOOL_NAME_PATTERN
            if is_dynamic
            else _CODEX_0162_TOOL_NAME_PATTERN
        )
        for tool in tools:
            if not isinstance(tool, Mapping):
                return None
            name = tool.get("name")
            tool_type = tool.get("type")
            if (
                not isinstance(name, str)
                or name_pattern.fullmatch(name) is None
                or tool_type != "function"
                or name in declared_names
            ):
                return None
            declared_names.add(name)
            declared_tools.append((name, "function"))
        seen_namespaces.add(namespace_name)
        total_tools += len(declared_tools)
        ordered.append((namespace_name, tuple(declared_tools)))
    if total_tools > CODEX_0162_MAX_TOTAL_TOOLS:
        return None
    return tuple(ordered)


def codex_0162_lower_initial_additional_tools(
    effective_body: Mapping[str, object],
) -> Mapping[str, object]:
    """Lower ONE validated initial additional_tools prefix to top-level tools.

    Exact bounded provider-declaration translation for the
    ``codex-0.162-responses-v1`` x ``local-coding-v1`` pair.  The initial
    additional_tools developer item's validated namespace declarations become
    top-level namespace tool entries in declared order, the item and its ID
    are deliberately omitted from the provider body, and every subsequent
    input item is preserved in order.  A request without the prefix is
    returned unchanged.  A non-initial or repeated additional_tools item, a
    mixed top-level declaration, or a malformed prefix fails closed; the
    canonical policy representation keeps the declaration and its ID.
    """
    input_value = effective_body.get("input")
    if not isinstance(input_value, list):
        return effective_body
    positions = [
        index
        for index, item in enumerate(input_value)
        if isinstance(item, Mapping) and item.get("type") == "additional_tools"
    ]
    if len(positions) > 1:
        raise _error(
            "The Codex 0.162 request declares local tools more than once",
            "codex_0162_tool_declaration",
        )
    if not positions:
        return effective_body
    if positions[0] != 0:
        raise _error(
            "The Codex 0.162 local tool declaration must be the initial input prefix",
            "codex_0162_tool_declaration",
        )
    existing_tools = effective_body.get("tools")
    if existing_tools not in (None, []):
        raise _error(
            "The Codex 0.162 local tool declaration cannot be combined with top-level tools",
            "codex_0162_tool_declaration",
        )
    prefix = input_value[0]
    if not isinstance(prefix, Mapping) or prefix.get("role") != "developer":
        raise _error(
            "The Codex 0.162 local tool declaration is invalid",
            "codex_0162_tool_declaration",
        )
    namespaces = prefix.get("tools")
    if not isinstance(namespaces, list) or not namespaces:
        raise _error(
            "The Codex 0.162 local tool declaration is empty",
            "codex_0162_tool_declaration",
        )
    lowered_tools: list[dict[str, object]] = []
    for namespace in namespaces:
        if not isinstance(namespace, Mapping) or namespace.get("type") != "namespace":
            raise _error(
                "The Codex 0.162 local tool declaration container is invalid",
                "codex_0162_tool_declaration",
            )
        namespace_tools = namespace.get("tools")
        if not isinstance(namespace_tools, list) or not namespace_tools:
            raise _error(
                "The Codex 0.162 local tool declaration namespace is empty",
                "codex_0162_tool_declaration",
            )
        entry: dict[str, object] = {
            "type": "namespace",
            "name": namespace.get("name"),
        }
        description = namespace.get("description")
        if description is not None:
            entry["description"] = description
        entry["tools"] = copy.deepcopy(list(namespace_tools))
        lowered_tools.append(entry)
    lowered: dict[str, object] = {}
    for key, value in effective_body.items():
        if key in ("input", "tools"):
            continue
        lowered[key] = copy.deepcopy(value)
    lowered["tools"] = lowered_tools
    lowered["input"] = [copy.deepcopy(item) for item in input_value[1:]]
    return lowered


CODEX_0162_POLICY_SPEC = replace(
    CODEX_0149_POLICY_SPEC,
    taxonomy_for=codex_0162_additional_tools_taxonomy_for,
    taxonomy_id_0148="codex_0_162",
    max_client_tool_schema_properties=CODEX_0162_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES,
    max_client_tool_total_description_bytes=CODEX_0162_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES,
)




class Codex0162ResponsesClientModule(Codex0149ResponsesClientModule):
    """Validate the pinned 0.162.1 dialect and return non-authoritative facts.

    The 0.162 responses-lite profile declares local tools exclusively through
    the additional_tools input item; a non-empty top-level tools field is a
    dialect mismatch for this module and is rejected before the shared
    validator runs.

    Version 2 is namespace-scoped name compatibility only: approved
    ``mcp__codex_apps__`` connector namespaces additionally accept a bounded
    single leading underscore preceding a lowercase-letter-led name (same
    character vocabulary and 64-character total cap), while builtin
    namespaces keep the lowercase-letter-first rule.  No downstream shared
    validator was widened; accepted names pass through canonicalization,
    provider translation, tool-call events, and replay unchanged.
    """

    module_id = CODEX_0162_CLIENT_MODULE_ID
    module_version = CODEX_0162_CLIENT_MODULE_VERSION
    fixture_sha256 = CODEX_0162_FIXTURE_SHA256
    policy_spec = CODEX_0162_POLICY_SPEC

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        if endpoint == "/v1/responses" and isinstance(body, Mapping):
            tools = body.get("tools")
            if tools is not None and tools != []:
                raise _error(
                    "The Codex 0.162 client dialect declares local tools only through additional_tools",
                    "codex_0162_tool_declaration",
                )
        canonical = super().normalize(endpoint, body)
        # The shared 0.149 validator embeds the 0.149 profile facts; this
        # module must return its own version-owned identity and source facts.
        return replace(canonical, profile_facts=_PROFILE_FACTS)


CODEX_0162_CLIENT_MODULE = Codex0162ResponsesClientModule()
