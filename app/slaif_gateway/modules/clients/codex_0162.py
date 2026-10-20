"""Pinned Codex CLI 0.162.1 responses-lite additional-tools client dialect.

This module carries the separately qualified 0.162.1 profile: the client
builds a single ``additional_tools`` developer item carrying an optional
``at_``-style identifier and a bounded set of client-local ``function``
declarations.  The namespace vocabulary is strictly limited to the built-in
namespaces ``functions`` and ``multi_agent_v1`` plus validated bounded
``mcp__codex_apps__`` plugin namespaces.  Tool names in every namespace are
validated against a bounded grammar with function-only types, per-namespace
uniqueness, and the approved finite cardinality and byte limits; the official
isolated capture records a 12-tool sample of the built-in vocabulary, not its
complete set, so no exact tool list is pinned.  Declarations are
client-operated function facts: they grant no provider-hosted, connector, or
Gateway-execution authority, and the item ID is a bounded opaque value with
no identity, replay, or audit derivation.

The executable engine (module ID ``codex-0.162-responses-v1``) is
one-time-upgraded to be data-driven: its identity and its namespace/tool
grammar and ceilings come from a validated Codex compatibility profile DATA
snapshot.  The packaged default profile
``clients/profiles/codex_0162.json`` (frozen revision 8) is loaded once when this
module is imported and, in a deployment that configures an operator profile
file, that file is loaded once at process bootstrap before any traffic.
The effective module version is the validated data revision and the
``fixture_sha256`` identity is the canonical digest of the profile DATA.
A request key is admitted only when its pinned (version, fixture_sha256)
tuple exactly matches the loaded data profile; legacy and stale pins fail
closed and are repaired exclusively through the explicit audited key
migration.  The historical revision 1 and 2 identities are frozen literal
tuples retained for that audited migration/rollback path only; they are not
live runtime decoders and no compiled policy documents for them exist in
this module.  Data cannot grant permissions or replace identity, replay, signing, privacy,
stream-state-machine, or accounting code. Schema-2 data selects bounded
metadata rules and existing parser modes, and it is never re-read per
request.

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
from slaif_gateway.modules.compatibility_rules import CompatibilityRuleError
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_POLICY_SPEC,
    Codex0149ResponsesClientModule,
)
from slaif_gateway.modules.codex_profile_data import (
    CodexProfileData,
    load_codex_profile_file,
    load_default_codex_profile,
)
from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    CodexTaxonomyResult,
    ModuleSelectionError,
    ResponsesClientPolicySpec,
)

CODEX_0162_CLIENT_MODULE_ID = "codex-0.162-responses-v1"
CODEX_0162_CLI_VERSION = "0.162.1"
CODEX_0162_PROFILE_ID = "additional-tools-profile-v2"
CODEX_0162_SOURCE_CONTRACT_TAG = "rust-v0.162.1"
CODEX_0162_SOURCE_CONTRACT_COMMIT = "092d3acd6bec3e3a14bdc7e7a2810ab628ab759d"
CODEX_0162_OFFICIAL_CAPTURE_ARCHIVE_SHA256 = (
    "a676f5722aae0d86cbe3764332f08eab1fdd89dc0a300b3ad4ffbf48611fa3e3"
)
CODEX_0162_OFFICIAL_CAPTURE_BINARY_SHA256 = (
    "628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1"
)

# Frozen historical identity tuples, retained for the explicit audited
# key-migration/rollback path ONLY.  They are migration targets, not live
# runtime pins: a key pinned to either tuple is rejected at request time
# until it is explicitly migrated to the loaded data profile (or rolled
# back to a frozen legacy deployment).  The digests are frozen literals of
# the byte-for-byte immutable historical fixtures.
CODEX_0162_V1_CLIENT_MODULE = MappingProxyType(
    {
        "id": CODEX_0162_CLIENT_MODULE_ID,
        "version": "1",
        "fixture_sha256": "724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e",
    }
)
CODEX_0162_V2_CLIENT_MODULE = MappingProxyType(
    {
        "id": CODEX_0162_CLIENT_MODULE_ID,
        "version": "2",
        "fixture_sha256": "b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85",
    }
)
CODEX_0162_V2_FIXTURE_RELATIVE_PATH = (
    "tests/fixtures/codex/0.162.1/additional-tools-profile-v2.json"
)
CODEX_0162_V1_FIXTURE_RELATIVE_PATH = (
    "tests/fixtures/codex/0.162.1/additional-tools-profile-v1.json"
)
# Backward-compatible names: they now identify the packaged default data
# profile (revision 3), not the historical v2 fixture.
CODEX_0162_FIXTURE_RELATIVE_PATH = "app/slaif_gateway/modules/clients/profiles/codex_0162.json"


def _error(message: str, code: str = "codex_0162_request_invalid") -> ModuleSelectionError:
    return ModuleSelectionError(message, error_code=code)


# Stable, content-free rejection reason codes for additional_tools taxonomy
# classification.  They are observability markers only: the structured
# classifier below both decides acceptance and names the first failure, and the
# historical tuple acceptance surface is preserved through the compatibility
# wrapper.
TAXONOMY_REASON_NOT_LIST = "additional_tools_not_a_nonempty_list"
TAXONOMY_REASON_TOO_MANY_NAMESPACES = "too_many_namespaces"
TAXONOMY_REASON_NAMESPACE_NOT_OBJECT = "namespace_not_object"
TAXONOMY_REASON_NAMESPACE_NAME_INVALID = "namespace_name_invalid"
TAXONOMY_REASON_NAMESPACE_NAME_UNAPPROVED = "namespace_name_unapproved"
TAXONOMY_REASON_TOOLS_NOT_LIST = "tools_not_a_nonempty_list"
TAXONOMY_REASON_TOO_MANY_TOOLS_PER_NAMESPACE = "too_many_tools_per_namespace"
TAXONOMY_REASON_TOOL_NOT_OBJECT = "tool_not_object"
TAXONOMY_REASON_TOOL_NAME_NOT_ALLOWED = "tool_name_not_allowed"
TAXONOMY_REASON_TOOL_TYPE_INVALID = "tool_type_invalid"
TAXONOMY_REASON_TOOL_NAME_DUPLICATE = "tool_name_duplicate"
TAXONOMY_REASON_TOO_MANY_TOTAL_TOOLS = "too_many_total_tools"
TAXONOMY_REASON_UNAPPROVED_SET = "unapproved_namespace_set"


def classify_additional_tools(
    namespaces: object, profile: CodexProfileData
) -> CodexTaxonomyResult:
    """Classify a declared Codex additional_tools set in a single pass.

    On acceptance, returns the canonical ordered
    ``(namespace, ((tool, "function"), ...), ...)`` tuple in ``taxonomy``.
    On rejection, returns the first failing check (original check order) with
    stable, content-free facts: ``reason_code``, the offending
    ``namespace_index`` / ``tool_index`` / ``field``, and the observed count
    plus relevant limit for cardinality checks.  This is the single shared
    classifier: the request policy consumes this result directly.  It carries
    no raw request content, grants no authority, performs no I/O, and does not
    mutate the input.
    """
    if not isinstance(namespaces, list) or not namespaces:
        return CodexTaxonomyResult(
            accepted=False, reason_code=TAXONOMY_REASON_NOT_LIST
        )
    if len(namespaces) > profile.max_namespaces:
        return CodexTaxonomyResult(
            accepted=False,
            reason_code=TAXONOMY_REASON_TOO_MANY_NAMESPACES,
            field="tools",
            observed=len(namespaces),
            limit=profile.max_namespaces,
        )
    seen_namespaces: set[str] = set()
    total_tools = 0
    ordered: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for namespace_index, namespace in enumerate(namespaces):
        if not isinstance(namespace, Mapping):
            return CodexTaxonomyResult(
                accepted=False,
                reason_code=TAXONOMY_REASON_NAMESPACE_NOT_OBJECT,
                namespace_index=namespace_index,
                field="tools",
            )
        namespace_name = namespace.get("name")
        if (
            not isinstance(namespace_name, str)
            or not namespace_name
            or namespace_name in seen_namespaces
        ):
            return CodexTaxonomyResult(
                accepted=False,
                reason_code=TAXONOMY_REASON_NAMESPACE_NAME_INVALID,
                namespace_index=namespace_index,
                field="name",
            )
        kind = profile.classify_namespace_name(namespace_name)
        if kind is None:
            return CodexTaxonomyResult(
                accepted=False,
                reason_code=TAXONOMY_REASON_NAMESPACE_NAME_UNAPPROVED,
                namespace_index=namespace_index,
                field="name",
            )
        tools = namespace.get("tools")
        if not isinstance(tools, list) or not tools:
            return CodexTaxonomyResult(
                accepted=False,
                reason_code=TAXONOMY_REASON_TOOLS_NOT_LIST,
                namespace_index=namespace_index,
                field="tools",
            )
        if len(tools) > profile.max_tools_per_namespace:
            return CodexTaxonomyResult(
                accepted=False,
                reason_code=TAXONOMY_REASON_TOO_MANY_TOOLS_PER_NAMESPACE,
                namespace_index=namespace_index,
                field="tools",
                observed=len(tools),
                limit=profile.max_tools_per_namespace,
            )
        declared_names: set[str] = set()
        declared_tools: list[tuple[str, str]] = []
        for tool_index, tool in enumerate(tools):
            if not isinstance(tool, Mapping):
                return CodexTaxonomyResult(
                    accepted=False,
                    reason_code=TAXONOMY_REASON_TOOL_NOT_OBJECT,
                    namespace_index=namespace_index,
                    tool_index=tool_index,
                    field="tools",
                )
            name = tool.get("name")
            tool_type = tool.get("type")
            if not profile.is_tool_name_allowed(kind, name):
                return CodexTaxonomyResult(
                    accepted=False,
                    reason_code=TAXONOMY_REASON_TOOL_NAME_NOT_ALLOWED,
                    namespace_index=namespace_index,
                    tool_index=tool_index,
                    field="name",
                )
            if tool_type != "function" and (
                not isinstance(tool_type, str)
                or (namespace_name, name, tool_type) not in profile.dialect.custom_tools
            ):
                return CodexTaxonomyResult(
                    accepted=False,
                    reason_code=TAXONOMY_REASON_TOOL_TYPE_INVALID,
                    namespace_index=namespace_index,
                    tool_index=tool_index,
                    field="type",
                )
            if name in declared_names:
                return CodexTaxonomyResult(
                    accepted=False,
                    reason_code=TAXONOMY_REASON_TOOL_NAME_DUPLICATE,
                    namespace_index=namespace_index,
                    tool_index=tool_index,
                    field="name",
                )
            declared_names.add(name)
            declared_tools.append((name, tool_type))
        seen_namespaces.add(namespace_name)
        total_tools += len(declared_tools)
        ordered.append((namespace_name, tuple(declared_tools)))
    if total_tools > profile.max_total_tools:
        return CodexTaxonomyResult(
            accepted=False,
            reason_code=TAXONOMY_REASON_TOO_MANY_TOTAL_TOOLS,
            field="tools",
            observed=total_tools,
            limit=profile.max_total_tools,
        )
    return CodexTaxonomyResult(accepted=True, taxonomy=tuple(ordered))


def _taxonomy_for_profile(profile: CodexProfileData):
    """Compatibility wrapper: the tuple form of :func:`classify_additional_tools`.

    Returns a ``taxonomy_for(namespaces)`` callable whose output is exactly
    ``classify_additional_tools(namespaces, profile).taxonomy`` (the canonical
    tuple, or ``None`` when rejected).  The structured classifier above is the
    single source of truth; this wrapper keeps the historical tuple API for
    pre-observability consumers unchanged.
    """

    def taxonomy_for(
        namespaces: object,
    ) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
        return classify_additional_tools(namespaces, profile).taxonomy

    return taxonomy_for




def _build_policy_spec(profile: CodexProfileData) -> ResponsesClientPolicySpec:
    return replace(
        CODEX_0149_POLICY_SPEC,
        taxonomy_for=_taxonomy_for_profile(profile),
        taxonomy_classifier=lambda namespaces: classify_additional_tools(namespaces, profile),
        taxonomy_id_0148="codex_0_162",
        max_client_tool_schema_depth=profile.max_schema_depth,
        max_client_tool_schema_properties=profile.max_schema_properties,
        max_client_tool_description_bytes=profile.max_tool_description_bytes,
        max_client_tool_total_description_bytes=profile.max_total_description_bytes,
        max_client_tool_declaration_bytes=profile.max_declaration_bytes,
        # Preset data selects known bounded modes, never inferred from revisions.
        # JSON Schema property labels are data, not provider authority.
        allow_schema_property_names="schema_property_names" in profile.dialect.features,
        allow_sparse_visible_reasoning="sparse_visible_reasoning" in profile.dialect.features,
        allow_empty_visible_reasoning="empty_visible_reasoning" in profile.dialect.features,
        allow_sparse_function_events="sparse_function_events" in profile.dialect.features,
        allow_tool_output_images="tool_output_images" in profile.dialect.features,
        dialect_rules=profile.dialect,
        custom_client_tools=profile.dialect.custom_tools,
        **dict(profile.replay_limits),
    )


def _profile_facts_for(profile: CodexProfileData) -> Mapping[str, str]:
    return MappingProxyType(
        {
            "client_module_id": profile.module_id,
            "client_module_version": profile.revision,
            "fixture_sha256": profile.digest,
            "source_contract_tag": profile.source_tag,
            "source_contract_commit": profile.source_commit,
        }
    )


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


class Codex0162ResponsesClientModule(Codex0149ResponsesClientModule):
    """Validate the pinned 0.162.1 dialect under one immutable data profile.

    The instance is bound at construction to exactly one validated profile
    DATA snapshot; its module version and fixture digest identity, its
    policy spec (taxonomy and ceilings), and the version-owned profile facts
    returned on every canonical request all come from that snapshot.  The
    0.162 responses-lite profile declares local tools exclusively through
    the additional_tools input item; a non-empty top-level tools field is a
    dialect mismatch for this module and is rejected before the shared
    validator runs.

    Accepted names pass through canonicalization, provider translation,
    tool-call events, and replay unchanged; no downstream shared validator
    is widened.  A key whose pinned tuple does not exactly match the bound
    snapshot is rejected before any side effect.
    """

    module_id = CODEX_0162_CLIENT_MODULE_ID

    def __init__(self, profile: CodexProfileData) -> None:
        self._profile = profile
        self.module_version: str = profile.revision
        self.fixture_sha256: str = profile.digest
        self.policy_spec: ResponsesClientPolicySpec = _build_policy_spec(profile)

    @property
    def profile(self) -> CodexProfileData:
        return self._profile

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        if not isinstance(body, Mapping):
            return super().normalize(endpoint, body)
        if endpoint == "/v1/responses" and isinstance(body, Mapping):
            tools = body.get("tools")
            if tools is not None and tools != []:
                raise _error(
                    "The Codex 0.162 client dialect declares local tools only through additional_tools",
                    "codex_0162_tool_declaration",
                )
        try:
            stripped, _, _ = self._profile.dialect.split(body, "request")
        except CompatibilityRuleError:
            raise _error("The request does not match the selected client preset.", "codex_dialect_value_invalid") from None
        canonical = super().normalize(endpoint, stripped)
        # The shared 0.149 validator embeds the 0.149 profile facts; this
        # module must return its own version-owned identity and source facts
        # from the bound data profile.
        return replace(
            canonical,
            # Keep even explicitly droppable fields until independent core
            # capability gates run. Only the core applies normalization.
            body={**canonical.body, **{k: copy.deepcopy(body[k]) for k in body if k not in stripped}},
            profile_facts=_profile_facts_for(self._profile),
        )


def build_codex_0162_client_module(profile: CodexProfileData) -> Codex0162ResponsesClientModule:
    """Build one concrete 0.162 module bound to one validated data profile."""
    if (
        not isinstance(profile, CodexProfileData)
        or profile.module_id != CODEX_0162_CLIENT_MODULE_ID
    ):
        raise ModuleSelectionError(
            "The Codex 0.162 client module profile is invalid",
            error_code="codex_0162_profile_invalid",
        )
    return Codex0162ResponsesClientModule(profile)


# Packaged default profile DATA, loaded once when this module is imported.
# The constants below are facts of that packaged default; an operator
# profile file configured at bootstrap changes only the concrete registry
# module, never these from-import default facts.
CODEX_0162_DEFAULT_PROFILE = load_default_codex_profile()
CODEX_0162_CLIENT_MODULE = build_codex_0162_client_module(CODEX_0162_DEFAULT_PROFILE)
CODEX_0162_CLIENT_MODULE_VERSION = CODEX_0162_CLIENT_MODULE.module_version
CODEX_0162_FIXTURE_SHA256 = CODEX_0162_CLIENT_MODULE.fixture_sha256
CODEX_0162_POLICY_SPEC = CODEX_0162_CLIENT_MODULE.policy_spec

# Strict built-in namespace vocabulary and connector prefix of the packaged
# default profile data.  The official isolated capture observed 7 functions
# and 5 multi_agent_v1 tools, a sample of a larger built-in vocabulary, so
# no exact built-in tool list is pinned.
CODEX_0162_BUILTIN_NAMESPACES = frozenset(CODEX_0162_DEFAULT_PROFILE.builtin_names)
CODEX_0162_CONNECTOR_NAMESPACE_PREFIX = CODEX_0162_DEFAULT_PROFILE.connector_prefixes[0]

# Finite 0.162 profile ceilings of the packaged default profile data,
# supporting the observed 197-tool / 11-namespace operator summary.  The
# shared request policy re-applies the loaded profile's ceilings from the
# concrete registry module for every request.
CODEX_0162_MAX_NAMESPACES = CODEX_0162_DEFAULT_PROFILE.max_namespaces
CODEX_0162_MAX_TOTAL_TOOLS = CODEX_0162_DEFAULT_PROFILE.max_total_tools
CODEX_0162_MAX_NAMESPACE_TOOLS = CODEX_0162_DEFAULT_PROFILE.max_tools_per_namespace
CODEX_0162_MAX_SCHEMA_DEPTH = CODEX_0162_DEFAULT_PROFILE.max_schema_depth
CODEX_0162_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES = CODEX_0162_DEFAULT_PROFILE.max_schema_properties
CODEX_0162_MAX_CLIENT_TOOL_DESCRIPTION_BYTES = CODEX_0162_DEFAULT_PROFILE.max_tool_description_bytes
CODEX_0162_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES = (
    CODEX_0162_DEFAULT_PROFILE.max_total_description_bytes
)
CODEX_0162_MAX_CLIENT_TOOL_DECLARATION_BYTES = CODEX_0162_DEFAULT_PROFILE.max_declaration_bytes


def install_codex_0162_client_module(profile: CodexProfileData) -> Codex0162ResponsesClientModule:
    """Bootstrap install of one validated data profile for this process.

    Process bootstrap (HTTP app factory or CLI entry) calls this before
    serving: with the packaged default when no operator file is configured,
    or with the operator file's validated snapshot otherwise.  Repeating the
    same-config initialization is an idempotent no-op; binding a different
    profile after the registry binding exists fails closed.  There is no
    hot reload and no in-flight reference is ever mutated; active metadata
    is always read from the concrete registry module.
    """
    module = build_codex_0162_client_module(profile)
    # Deferred import: the registry module imports this module.
    from slaif_gateway.modules.clients import registry as _registry

    _registry.bind_codex_0162_client_module(module)
    return module


def bootstrap_codex_compatibility_profile(profile_path: str = "") -> CodexProfileData:
    """One-shot process bootstrap: load and bind the Codex data profile.

    Shared factory boundary used by the HTTP app factory and the CLI: an
    operator-only profile file (``CODEX_COMPATIBILITY_PROFILE_FILE``) is
    validated exactly once and any failure fails closed (no silent
    fallback); an empty path uses the packaged default profile.  This
    helper lives outside the app module so offline CLI commands never
    import or construct the HTTP application.  The bind is idempotent for
    repeated same-config initialization; the returned snapshot is the one
    every caller of this process must use.
    """
    profile = (
        load_codex_profile_file(profile_path) if profile_path else load_default_codex_profile()
    )
    install_codex_0162_client_module(profile)
    return profile


def codex_0162_additional_tools_taxonomy_for(
    namespaces: object,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    """Validate one bounded 0.162 local declaration set in declared order.

    Bounded classifier of the packaged default data profile (revision 3),
    retained as the stable regression surface for the 0.162 dialect.  The
    registered module resolves per-request behavior through the profile
    snapshot bound to the key's pinned identity.  Returns the canonical
    (namespace, (tool, type)) sequence in declared order, or None when the
    declaration falls outside the strict namespace vocabulary or its
    bounded tool validation.
    """
    return _taxonomy_for_profile(CODEX_0162_CLIENT_MODULE.profile)(namespaces)


__all__ = [
    "bootstrap_codex_compatibility_profile",
    "classify_additional_tools",
    "CODEX_0162_BUILTIN_NAMESPACES",
    "CODEX_0162_CLIENT_MODULE",
    "CODEX_0162_CLIENT_MODULE_ID",
    "CODEX_0162_CLIENT_MODULE_VERSION",
    "CODEX_0162_CLI_VERSION",
    "CODEX_0162_CONNECTOR_NAMESPACE_PREFIX",
    "CODEX_0162_FIXTURE_RELATIVE_PATH",
    "CODEX_0162_FIXTURE_SHA256",
    "CODEX_0162_MAX_CLIENT_TOOL_DECLARATION_BYTES",
    "CODEX_0162_MAX_CLIENT_TOOL_DESCRIPTION_BYTES",
    "CODEX_0162_MAX_CLIENT_TOOL_SCHEMA_PROPERTIES",
    "CODEX_0162_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES",
    "CODEX_0162_MAX_NAMESPACES",
    "CODEX_0162_MAX_NAMESPACE_TOOLS",
    "CODEX_0162_MAX_SCHEMA_DEPTH",
    "CODEX_0162_MAX_TOTAL_TOOLS",
    "CODEX_0162_OFFICIAL_CAPTURE_ARCHIVE_SHA256",
    "CODEX_0162_OFFICIAL_CAPTURE_BINARY_SHA256",
    "CODEX_0162_POLICY_SPEC",
    "CODEX_0162_PROFILE_ID",
    "CODEX_0162_SOURCE_CONTRACT_COMMIT",
    "CODEX_0162_SOURCE_CONTRACT_TAG",
    "CODEX_0162_V1_CLIENT_MODULE",
    "CODEX_0162_V1_FIXTURE_RELATIVE_PATH",
    "CODEX_0162_V2_CLIENT_MODULE",
    "CODEX_0162_V2_FIXTURE_RELATIVE_PATH",
    "CODEX_0162_DEFAULT_PROFILE",
    "Codex0162ResponsesClientModule",
    "build_codex_0162_client_module",
    "codex_0162_additional_tools_taxonomy_for",
    "codex_0162_lower_initial_additional_tools",
    "install_codex_0162_client_module",
]
