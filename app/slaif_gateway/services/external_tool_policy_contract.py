"""Pure, fail-closed contract for future provider-hosted external tools.

This module defines policy vocabulary and admission facts only. It is not wired
into request handling, persistence, provider adapters, settings, or operator
surfaces. Current runtime hosted-tool denials therefore remain unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
import re

EXTERNAL_TOOL_POLICY_VERSION = 1

STRICT_BOUNDED = "strict_bounded"
EXTERNAL_TOOL_FENCED = "external_tool_fenced"

CLIENT_OPERATED_AUTHORITY = "client_operated"
PROVIDER_EXTERNAL_AUTHORITY = "provider_external"
UNKNOWN_EXTERNAL_AUTHORITY = "unknown_external_authority"

PROVIDER_WEB_SEARCH = "provider_web_search"
PROVIDER_FILE_SEARCH = "provider_file_search"
PROVIDER_CODE_INTERPRETER = "provider_code_interpreter"
PROVIDER_HOSTED_SHELL = "provider_hosted_shell"
PROVIDER_IMAGE_GENERATION = "provider_image_generation"
PROVIDER_COMPUTER_USE = "provider_computer_use"
PROVIDER_TOOL_SEARCH = "provider_tool_search"
PROVIDER_SKILL = "provider_skill"
PROVIDER_REMOTE_MCP = "provider_remote_mcp"
PROVIDER_CONNECTOR = "provider_connector"
PROVIDER_URL_FETCH = "provider_url_fetch"

KNOWN_EXTERNAL_CAPABILITIES = frozenset(
    {
        PROVIDER_WEB_SEARCH,
        PROVIDER_FILE_SEARCH,
        PROVIDER_CODE_INTERPRETER,
        PROVIDER_HOSTED_SHELL,
        PROVIDER_IMAGE_GENERATION,
        PROVIDER_COMPUTER_USE,
        PROVIDER_TOOL_SEARCH,
        PROVIDER_SKILL,
        PROVIDER_REMOTE_MCP,
        PROVIDER_CONNECTOR,
        PROVIDER_URL_FETCH,
    }
)

DESTINATION_CAPABILITIES = frozenset({PROVIDER_REMOTE_MCP, PROVIDER_CONNECTOR})

CLIENT_TOOL_ALIASES = frozenset(
    {
        "function",
        "custom",
        "namespace",
        "local_shell",
        "apply_patch",
    }
)

PROVIDER_TOOL_ALIAS_TO_CAPABILITY = {
    "web_search": PROVIDER_WEB_SEARCH,
    "web_search_preview": PROVIDER_WEB_SEARCH,
    "file_search": PROVIDER_FILE_SEARCH,
    "code_interpreter": PROVIDER_CODE_INTERPRETER,
    "shell": PROVIDER_HOSTED_SHELL,
    "image_generation": PROVIDER_IMAGE_GENERATION,
    "computer": PROVIDER_COMPUTER_USE,
    "computer_use": PROVIDER_COMPUTER_USE,
    "computer_use_preview": PROVIDER_COMPUTER_USE,
    "tool_search": PROVIDER_TOOL_SEARCH,
    "skill": PROVIDER_SKILL,
    "skills": PROVIDER_SKILL,
}

NEUTRAL_TOOL_CHOICES = frozenset({"none", "auto", "required"})
SEARCH_SPECIFIC_CHAT_COMPLETIONS_MODELS = frozenset(
    {
        "gpt-5-search-api",
        "gpt-4o-search-preview",
        "gpt-4o-mini-search-preview",
    }
)

ABSOLUTE_MAX_DISTINCT_CAPABILITIES = 16
ABSOLUTE_MAX_APPROVED_DESTINATIONS = 8
ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS = 16
ABSOLUTE_MAX_PROVIDER_TOOL_CALLS = 16

_KEY_POLICY_FIELDS = frozenset(
    {
        "version",
        "mode",
        "allowed_capabilities",
        "allowed_destination_ids",
        "max_provider_tool_calls_per_request",
        "single_request_overrun_acknowledged",
    }
)
_ROUTE_POLICY_FIELDS = frozenset(
    {
        "version",
        "supported_capabilities",
        "approved_destination_ids",
        "max_provider_tool_calls_per_request",
        "call_limit_enforced",
        "final_usage_required",
        "final_cost_required",
    }
)
_PROVIDER_AUTHORITY_MARKERS = frozenset(
    {
        "server_url",
        "connector_id",
        "authorization",
        "require_approval",
        "defer_loading",
        "server_label",
        "server_description",
        "allowed_tools",
        "api_key",
        "bearer_token",
        "cookie",
        "cookies",
        "oauth",
        "headers",
    }
)
_MCP_DESTINATION_MARKERS = frozenset({"server_url", "connector_id"})
_MAX_NAMESPACE_DEPTH = 4
_MAX_NAMESPACE_CHILD_DECLARATIONS = 16
_DESTINATION_ID_PATTERN = re.compile(
    r"^(?P<kind>connector|remote_mcp):(?P<opaque>[a-z0-9][a-z0-9_-]{0,47})$"
)
_SECRET_WORDS = frozenset(
    {
        "apikey",
        "api_key",
        "authorization",
        "bearer",
        "credential",
        "oauth",
        "password",
        "secret",
        "token",
    }
)


@dataclass(frozen=True, slots=True)
class ExternalToolOperatorCeilings:
    """Immutable operator ceilings bounded by contract-level absolute maxima."""

    max_distinct_capabilities: int = ABSOLUTE_MAX_DISTINCT_CAPABILITIES
    max_approved_destinations: int = ABSOLUTE_MAX_APPROVED_DESTINATIONS
    max_provider_tool_declarations_per_request: int = ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS
    max_provider_tool_calls_per_request: int = ABSOLUTE_MAX_PROVIDER_TOOL_CALLS

    def __post_init__(self) -> None:
        values = (
            (self.max_distinct_capabilities, ABSOLUTE_MAX_DISTINCT_CAPABILITIES),
            (self.max_approved_destinations, ABSOLUTE_MAX_APPROVED_DESTINATIONS),
            (
                self.max_provider_tool_declarations_per_request,
                ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS,
            ),
            (
                self.max_provider_tool_calls_per_request,
                ABSOLUTE_MAX_PROVIDER_TOOL_CALLS,
            ),
        )
        if any(
            type(value) is not int or value <= 0 or value > maximum for value, maximum in values
        ):
            raise ValueError("External-tool operator ceilings are outside the contract bounds.")


DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS = ExternalToolOperatorCeilings()


@dataclass(frozen=True, slots=True)
class ExternalToolKeyPolicy:
    """Canonical v1 per-key policy; values are safe low-cardinality identifiers."""

    version: int
    mode: str
    allowed_capabilities: tuple[str, ...]
    allowed_destination_ids: tuple[str, ...]
    max_provider_tool_calls_per_request: int
    single_request_overrun_acknowledged: bool


@dataclass(frozen=True, slots=True)
class ExternalToolRoutePolicy:
    """Canonical v1 per-route support contract."""

    version: int
    supported_capabilities: tuple[str, ...]
    approved_destination_ids: tuple[str, ...]
    max_provider_tool_calls_per_request: int
    call_limit_enforced: bool
    final_usage_required: bool
    final_cost_required: bool


@dataclass(frozen=True, slots=True)
class KeyPolicyParseResult:
    """Safe parse result that never retains malformed input."""

    valid: bool
    present: bool
    policy: ExternalToolKeyPolicy | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class RoutePolicyParseResult:
    """Safe route parse result that never retains malformed input."""

    valid: bool
    present: bool
    policy: ExternalToolRoutePolicy | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class ToolAuthorityClassification:
    """One safe authority classification without raw wire values."""

    authority_class: str
    capability_id: str | None
    destination_id: str | None
    provider_tool_declaration: bool
    unreviewed_external_authority: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class ClassifiedExternalToolRequest:
    """Canonical request facts consumed by the pure admission reducer."""

    capabilities: tuple[str, ...]
    destination_ids: tuple[str, ...]
    provider_tool_declaration_count: int
    requested_provider_tool_calls_per_request: int
    unknown_external_authority: bool
    unreviewed_external_authority: bool
    unsupported_external_state: bool
    approval_floor_satisfied: bool

    def __post_init__(self) -> None:
        if (
            type(self.capabilities) is not tuple
            or self.capabilities != tuple(sorted(set(self.capabilities)))
            or any(item not in KNOWN_EXTERNAL_CAPABILITIES for item in self.capabilities)
            or type(self.destination_ids) is not tuple
            or self.destination_ids != tuple(sorted(set(self.destination_ids)))
            or any(not _is_normalized_destination_id(item) for item in self.destination_ids)
            or not _is_non_negative_int(self.provider_tool_declaration_count)
            or not _is_non_negative_int(self.requested_provider_tool_calls_per_request)
            or any(
                type(item) is not bool
                for item in (
                    self.unknown_external_authority,
                    self.unreviewed_external_authority,
                    self.unsupported_external_state,
                    self.approval_floor_satisfied,
                )
            )
        ):
            raise ValueError("External-tool request facts are not canonical.")

    @property
    def has_external_authority(self) -> bool:
        return bool(
            self.capabilities
            or self.unknown_external_authority
            or self.unreviewed_external_authority
            or self.unsupported_external_state
        )

    @property
    def requires_provider_tool_calls(self) -> bool:
        return bool(set(self.capabilities) - {PROVIDER_URL_FETCH})


@dataclass(frozen=True, slots=True)
class ExternalToolKeyLimitFacts:
    """Safe key-purpose and finite-limit facts for admission."""

    key_purpose: str
    request_limit_total: int | None
    token_limit_total: int | None
    cost_limit_eur: Decimal | None

    def __post_init__(self) -> None:
        if self.key_purpose not in {"standard", "trusted_calibration"}:
            raise ValueError("External-tool key purpose is not canonical.")
        if (self.request_limit_total is not None and type(self.request_limit_total) is not int) or (
            self.token_limit_total is not None and type(self.token_limit_total) is not int
        ):
            raise ValueError("External-tool integer limit facts are not canonical.")
        if self.cost_limit_eur is not None and not isinstance(self.cost_limit_eur, Decimal):
            raise ValueError("External-tool cost limit fact is not canonical.")


@dataclass(frozen=True, slots=True)
class ExternalToolAdmissionDecision:
    """Deterministic safe result; it contains no raw request or provider values."""

    allowed: bool
    quota_mode: str
    effective_tool_call_cap: int
    reason_code: str
    exclusive_key_fence_required: bool
    single_request_overrun_accepted: bool
    hold_on_missing_or_ambiguous_final_cost: bool
    following_requests_block_after_exhaustion: bool

    def to_safe_dict(self) -> dict[str, object]:
        return asdict(self)


def strict_key_policy() -> ExternalToolKeyPolicy:
    """Return the exact strict/default v1 key policy."""
    return ExternalToolKeyPolicy(
        version=EXTERNAL_TOOL_POLICY_VERSION,
        mode=STRICT_BOUNDED,
        allowed_capabilities=(),
        allowed_destination_ids=(),
        max_provider_tool_calls_per_request=0,
        single_request_overrun_acknowledged=False,
    )


def strict_route_policy() -> ExternalToolRoutePolicy:
    """Return the exact strict/default v1 route policy."""
    return ExternalToolRoutePolicy(
        version=EXTERNAL_TOOL_POLICY_VERSION,
        supported_capabilities=(),
        approved_destination_ids=(),
        max_provider_tool_calls_per_request=0,
        call_limit_enforced=False,
        final_usage_required=False,
        final_cost_required=False,
    )


def parse_key_external_tool_policy(
    value: object,
    *,
    ceilings: ExternalToolOperatorCeilings = DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
) -> KeyPolicyParseResult:
    """Parse an exact v1 key policy; missing means strict default, malformed denies."""
    if value is None:
        return KeyPolicyParseResult(
            valid=True,
            present=False,
            policy=strict_key_policy(),
            reason_code="key_policy_missing_strict_default",
        )
    if not isinstance(value, Mapping):
        return _invalid_key_policy("key_policy_invalid_shape")
    if set(value) != _KEY_POLICY_FIELDS:
        return _invalid_key_policy("key_policy_invalid_fields")
    if not _is_exact_version(value.get("version")):
        return _invalid_key_policy("key_policy_invalid_version")

    mode = value.get("mode")
    if not isinstance(mode, str) or mode not in {STRICT_BOUNDED, EXTERNAL_TOOL_FENCED}:
        return _invalid_key_policy("key_policy_invalid_mode")

    capabilities = _parse_capability_list(
        value.get("allowed_capabilities"),
        maximum=ceilings.max_distinct_capabilities,
    )
    if capabilities is None:
        return _invalid_key_policy("key_policy_invalid_capabilities")
    destinations = _parse_destination_list(
        value.get("allowed_destination_ids"),
        maximum=ceilings.max_approved_destinations,
    )
    if destinations is None:
        return _invalid_key_policy("key_policy_invalid_destinations")

    call_cap = value.get("max_provider_tool_calls_per_request")
    acknowledged = value.get("single_request_overrun_acknowledged")
    if not _is_non_negative_int(call_cap):
        return _invalid_key_policy("key_policy_invalid_call_cap")
    if type(acknowledged) is not bool:
        return _invalid_key_policy("key_policy_invalid_acknowledgement")

    if mode == STRICT_BOUNDED:
        if capabilities or destinations or call_cap != 0 or acknowledged is not False:
            return _invalid_key_policy("key_policy_invalid_strict_shape")
    else:
        if (
            not capabilities
            or not _is_positive_int(call_cap)
            or call_cap > ceilings.max_provider_tool_calls_per_request
            or acknowledged is not True
            or not _destinations_match_capabilities(capabilities, destinations)
        ):
            return _invalid_key_policy("key_policy_external_requirements_not_met")

    return KeyPolicyParseResult(
        valid=True,
        present=True,
        policy=ExternalToolKeyPolicy(
            version=EXTERNAL_TOOL_POLICY_VERSION,
            mode=mode,
            allowed_capabilities=capabilities,
            allowed_destination_ids=destinations,
            max_provider_tool_calls_per_request=call_cap,
            single_request_overrun_acknowledged=acknowledged,
        ),
        reason_code="key_policy_valid",
    )


def parse_route_external_tool_policy(
    value: object,
    *,
    ceilings: ExternalToolOperatorCeilings = DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
) -> RoutePolicyParseResult:
    """Parse exact v1 route support; missing/invalid metadata grants no support."""
    if value is None:
        return RoutePolicyParseResult(
            valid=True,
            present=False,
            policy=strict_route_policy(),
            reason_code="route_policy_missing_strict_default",
        )
    if not isinstance(value, Mapping):
        return _invalid_route_policy("route_policy_invalid_shape")
    if set(value) != _ROUTE_POLICY_FIELDS:
        return _invalid_route_policy("route_policy_invalid_fields")
    if not _is_exact_version(value.get("version")):
        return _invalid_route_policy("route_policy_invalid_version")

    capabilities = _parse_capability_list(
        value.get("supported_capabilities"),
        maximum=ceilings.max_distinct_capabilities,
    )
    if capabilities is None:
        return _invalid_route_policy("route_policy_invalid_capabilities")
    destinations = _parse_destination_list(
        value.get("approved_destination_ids"),
        maximum=ceilings.max_approved_destinations,
    )
    if destinations is None:
        return _invalid_route_policy("route_policy_invalid_destinations")

    call_cap = value.get("max_provider_tool_calls_per_request")
    call_limit_enforced = value.get("call_limit_enforced")
    final_usage_required = value.get("final_usage_required")
    final_cost_required = value.get("final_cost_required")
    if not _is_non_negative_int(call_cap):
        return _invalid_route_policy("route_policy_invalid_call_cap")
    if any(
        type(item) is not bool
        for item in (call_limit_enforced, final_usage_required, final_cost_required)
    ):
        return _invalid_route_policy("route_policy_invalid_evidence_flags")

    flags = (call_limit_enforced, final_usage_required, final_cost_required)
    if not capabilities:
        if destinations or call_cap != 0 or any(flag is not False for flag in flags):
            return _invalid_route_policy("route_policy_invalid_strict_shape")
    elif (
        not _is_positive_int(call_cap)
        or call_cap > ceilings.max_provider_tool_calls_per_request
        or any(flag is not True for flag in flags)
        or not _destinations_match_capabilities(capabilities, destinations)
    ):
        return _invalid_route_policy("route_policy_external_requirements_not_met")

    return RoutePolicyParseResult(
        valid=True,
        present=True,
        policy=ExternalToolRoutePolicy(
            version=EXTERNAL_TOOL_POLICY_VERSION,
            supported_capabilities=capabilities,
            approved_destination_ids=destinations,
            max_provider_tool_calls_per_request=call_cap,
            call_limit_enforced=call_limit_enforced,
            final_usage_required=final_usage_required,
            final_cost_required=final_cost_required,
        ),
        reason_code="route_policy_valid",
    )


def classify_tool_declaration(value: object) -> ToolAuthorityClassification:
    """Classify one exact wire tool declaration without retaining raw values."""
    if not isinstance(value, Mapping):
        return _unknown_classification("malformed_tool_declaration")
    tool_type = value.get("type")
    if not isinstance(tool_type, str) or not tool_type or tool_type != tool_type.strip():
        return _unknown_classification("malformed_tool_type")

    if tool_type in CLIENT_TOOL_ALIASES:
        markers = _client_declaration_control_markers(tool_type, value)
        if markers:
            return _unknown_classification("mixed_local_external_authority")
        if not _is_recognizable_client_tool_shape(tool_type, value):
            return _unknown_classification("malformed_client_tool_shape")
        if tool_type == "namespace" and not _namespace_children_are_client_operated(value):
            return _unknown_classification("namespace_child_external_or_invalid")
        return ToolAuthorityClassification(
            authority_class=CLIENT_OPERATED_AUTHORITY,
            capability_id=None,
            destination_id=None,
            provider_tool_declaration=False,
            unreviewed_external_authority=False,
            reason_code="client_operated_tool",
        )

    if tool_type == "mcp":
        return _classify_wire_mcp(value)

    capability = PROVIDER_TOOL_ALIAS_TO_CAPABILITY.get(tool_type)
    if capability is not None:
        markers = _declaration_control_markers(value)
        if markers:
            return _unknown_classification("malformed_provider_tool_authority")
        return ToolAuthorityClassification(
            authority_class=PROVIDER_EXTERNAL_AUTHORITY,
            capability_id=capability,
            destination_id=None,
            provider_tool_declaration=True,
            unreviewed_external_authority=False,
            reason_code="provider_external_tool",
        )

    return _unknown_classification("unknown_tool_type")


def classify_tool_choice(value: object) -> ToolAuthorityClassification:
    """Classify a tool-choice shape; unknown choices fail closed."""
    if value is None or (isinstance(value, str) and value in NEUTRAL_TOOL_CHOICES):
        return ToolAuthorityClassification(
            authority_class=CLIENT_OPERATED_AUTHORITY,
            capability_id=None,
            destination_id=None,
            provider_tool_declaration=False,
            unreviewed_external_authority=False,
            reason_code="neutral_tool_choice",
        )
    if isinstance(value, Mapping):
        classification = classify_tool_declaration(value)
        return ToolAuthorityClassification(
            authority_class=classification.authority_class,
            capability_id=classification.capability_id,
            destination_id=classification.destination_id,
            provider_tool_declaration=False,
            unreviewed_external_authority=classification.unreviewed_external_authority,
            reason_code=classification.reason_code,
        )
    return _unknown_classification("unknown_tool_choice", provider_declaration=False)


def classify_reviewed_external_tool(
    capability_id: str,
    *,
    destination_id: str | None = None,
) -> ToolAuthorityClassification:
    """Create a fact only after a future provider contract resolved server-side config."""
    if capability_id not in KNOWN_EXTERNAL_CAPABILITIES:
        raise ValueError("The reviewed external-tool capability is not canonical.")
    if capability_id in DESTINATION_CAPABILITIES:
        if not _destination_matches_capability(destination_id, capability_id):
            raise ValueError("The reviewed destination does not match the capability.")
    elif destination_id is not None:
        raise ValueError("This external-tool capability does not accept a destination.")
    return ToolAuthorityClassification(
        authority_class=PROVIDER_EXTERNAL_AUTHORITY,
        capability_id=capability_id,
        destination_id=destination_id,
        provider_tool_declaration=True,
        unreviewed_external_authority=False,
        reason_code="reviewed_provider_external_tool",
    )


def classify_external_tool_request(
    *,
    tools: object = None,
    tool_choice: object = None,
    web_search_options_present: bool = False,
    search_specific_model: bool = False,
    provider_url_fetch_requested: bool = False,
    reviewed_external_tools: Sequence[ToolAuthorityClassification] = (),
    requested_provider_tool_calls_per_request: int = 0,
    unsupported_external_state: bool = False,
    approval_floor_satisfied: bool = True,
) -> ClassifiedExternalToolRequest:
    """Reduce exact wire/selected facts to a canonical, content-free request DTO."""
    classifications: list[ToolAuthorityClassification] = []
    malformed_flag = False
    if tools is None:
        pass
    elif not isinstance(tools, list):
        classifications.append(_unknown_classification("malformed_tools_collection"))
    else:
        classifications.extend(classify_tool_declaration(tool) for tool in tools)

    choice = classify_tool_choice(tool_choice)
    if choice.capability_id is not None or choice.authority_class == UNKNOWN_EXTERNAL_AUTHORITY:
        classifications.append(choice)

    bool_values = (
        web_search_options_present,
        search_specific_model,
        provider_url_fetch_requested,
        unsupported_external_state,
        approval_floor_satisfied,
    )
    if any(type(value) is not bool for value in bool_values):
        malformed_flag = True
    else:
        if web_search_options_present or search_specific_model:
            classifications.append(
                ToolAuthorityClassification(
                    authority_class=PROVIDER_EXTERNAL_AUTHORITY,
                    capability_id=PROVIDER_WEB_SEARCH,
                    destination_id=None,
                    provider_tool_declaration=True,
                    unreviewed_external_authority=False,
                    reason_code="provider_external_web_search",
                )
            )
        if provider_url_fetch_requested:
            classifications.append(
                ToolAuthorityClassification(
                    authority_class=PROVIDER_EXTERNAL_AUTHORITY,
                    capability_id=PROVIDER_URL_FETCH,
                    destination_id=None,
                    provider_tool_declaration=False,
                    unreviewed_external_authority=False,
                    reason_code="provider_external_url_fetch",
                )
            )

    for item in reviewed_external_tools:
        if not isinstance(item, ToolAuthorityClassification) or (
            item.authority_class != PROVIDER_EXTERNAL_AUTHORITY
            or item.capability_id not in KNOWN_EXTERNAL_CAPABILITIES
            or item.unreviewed_external_authority
        ):
            malformed_flag = True
            continue
        classifications.append(item)

    capabilities = tuple(
        sorted(
            {
                item.capability_id
                for item in classifications
                if item.capability_id in KNOWN_EXTERNAL_CAPABILITIES
            }
        )
    )
    destinations = tuple(
        sorted({item.destination_id for item in classifications if item.destination_id is not None})
    )
    return ClassifiedExternalToolRequest(
        capabilities=capabilities,
        destination_ids=destinations,
        provider_tool_declaration_count=sum(
            item.provider_tool_declaration for item in classifications
        ),
        requested_provider_tool_calls_per_request=(
            requested_provider_tool_calls_per_request
            if _is_non_negative_int(requested_provider_tool_calls_per_request)
            else 0
        ),
        unknown_external_authority=malformed_flag
        or any(item.authority_class == UNKNOWN_EXTERNAL_AUTHORITY for item in classifications)
        or not _is_non_negative_int(requested_provider_tool_calls_per_request),
        unreviewed_external_authority=any(
            item.unreviewed_external_authority for item in classifications
        ),
        unsupported_external_state=(
            unsupported_external_state if type(unsupported_external_state) is bool else True
        ),
        approval_floor_satisfied=(
            approval_floor_satisfied if type(approval_floor_satisfied) is bool else False
        ),
    )


def is_search_specific_chat_completion_model(model: object) -> bool:
    """Recognize only reviewed Chat Completions search-model aliases."""
    if not isinstance(model, str) or model != model.strip():
        return False
    return model in SEARCH_SPECIFIC_CHAT_COMPLETIONS_MODELS or model.endswith("-search-preview")


def decide_external_tool_admission(
    *,
    request: ClassifiedExternalToolRequest,
    key_policy: KeyPolicyParseResult,
    route_policy: RoutePolicyParseResult,
    ceilings: ExternalToolOperatorCeilings,
    key_limits: ExternalToolKeyLimitFacts,
) -> ExternalToolAdmissionDecision:
    """Return the pure external-tool policy decision; this does not forward anything."""
    if not request.has_external_authority:
        return _decision(True, STRICT_BOUNDED, 0, "no_external_authority")
    if request.unknown_external_authority:
        return _decision(False, STRICT_BOUNDED, 0, "unknown_external_authority")
    if request.unsupported_external_state:
        return _decision(False, STRICT_BOUNDED, 0, "unsupported_external_state")
    if request.unreviewed_external_authority:
        return _decision(False, STRICT_BOUNDED, 0, "unreviewed_external_authority")
    if not request.approval_floor_satisfied:
        return _decision(False, STRICT_BOUNDED, 0, "approval_floor_not_satisfied")
    if len(request.capabilities) > ceilings.max_distinct_capabilities:
        return _decision(False, STRICT_BOUNDED, 0, "operator_capability_ceiling_exceeded")
    if len(request.destination_ids) > ceilings.max_approved_destinations:
        return _decision(False, STRICT_BOUNDED, 0, "operator_destination_ceiling_exceeded")
    if (
        request.provider_tool_declaration_count
        > ceilings.max_provider_tool_declarations_per_request
    ):
        return _decision(False, STRICT_BOUNDED, 0, "operator_declaration_ceiling_exceeded")
    if (
        request.requested_provider_tool_calls_per_request
        > ceilings.max_provider_tool_calls_per_request
    ):
        return _decision(False, STRICT_BOUNDED, 0, "operator_call_ceiling_exceeded")
    if request.requires_provider_tool_calls and not _is_positive_int(
        request.requested_provider_tool_calls_per_request
    ):
        return _decision(False, STRICT_BOUNDED, 0, "provider_tool_call_cap_required")

    if not key_policy.valid or key_policy.policy is None:
        return _decision(False, STRICT_BOUNDED, 0, "key_policy_invalid")
    if not key_policy.present:
        return _decision(False, STRICT_BOUNDED, 0, "key_policy_missing")
    if key_policy.policy.mode != EXTERNAL_TOOL_FENCED:
        return _decision(False, STRICT_BOUNDED, 0, "strict_bounded_external_authority_denied")
    if not route_policy.valid or route_policy.policy is None:
        return _decision(False, STRICT_BOUNDED, 0, "route_policy_invalid")
    if not route_policy.present or not route_policy.policy.supported_capabilities:
        return _decision(False, STRICT_BOUNDED, 0, "route_external_support_missing")

    key = key_policy.policy
    route = route_policy.policy
    if not set(request.capabilities).issubset(key.allowed_capabilities):
        return _decision(False, STRICT_BOUNDED, 0, "key_capability_mismatch")
    if not set(request.capabilities).issubset(route.supported_capabilities):
        return _decision(False, STRICT_BOUNDED, 0, "route_capability_mismatch")
    if not set(request.destination_ids).issubset(key.allowed_destination_ids):
        return _decision(False, STRICT_BOUNDED, 0, "key_destination_mismatch")
    if not set(request.destination_ids).issubset(route.approved_destination_ids):
        return _decision(False, STRICT_BOUNDED, 0, "route_destination_mismatch")
    if any(
        capability in DESTINATION_CAPABILITIES
        and not any(
            _destination_matches_capability(destination, capability)
            for destination in request.destination_ids
        )
        for capability in request.capabilities
    ):
        return _decision(False, STRICT_BOUNDED, 0, "request_destination_missing")

    effective_cap = min(
        key.max_provider_tool_calls_per_request,
        route.max_provider_tool_calls_per_request,
        ceilings.max_provider_tool_calls_per_request,
    )
    if request.requested_provider_tool_calls_per_request > effective_cap:
        return _decision(False, STRICT_BOUNDED, 0, "effective_call_cap_exceeded")
    if not (route.call_limit_enforced and route.final_usage_required and route.final_cost_required):
        return _decision(False, STRICT_BOUNDED, 0, "route_evidence_contract_missing")
    if not key.single_request_overrun_acknowledged:
        return _decision(False, STRICT_BOUNDED, 0, "single_request_overrun_not_acknowledged")
    if key_limits.key_purpose != "standard":
        return _decision(False, STRICT_BOUNDED, 0, "standard_key_required")
    if not (
        _is_positive_int(key_limits.request_limit_total)
        and _is_positive_int(key_limits.token_limit_total)
        and isinstance(key_limits.cost_limit_eur, Decimal)
        and key_limits.cost_limit_eur.is_finite()
        and key_limits.cost_limit_eur > 0
    ):
        return _decision(False, STRICT_BOUNDED, 0, "positive_finite_key_limits_required")

    return _decision(True, EXTERNAL_TOOL_FENCED, effective_cap, "external_tool_fenced_allowed")


def _decision(
    allowed: bool,
    quota_mode: str,
    effective_cap: int,
    reason_code: str,
) -> ExternalToolAdmissionDecision:
    fenced = allowed and quota_mode == EXTERNAL_TOOL_FENCED
    return ExternalToolAdmissionDecision(
        allowed=allowed,
        quota_mode=quota_mode,
        effective_tool_call_cap=effective_cap,
        reason_code=reason_code,
        exclusive_key_fence_required=fenced,
        single_request_overrun_accepted=fenced,
        hold_on_missing_or_ambiguous_final_cost=fenced,
        following_requests_block_after_exhaustion=fenced,
    )


def _classify_wire_mcp(value: Mapping[object, object]) -> ToolAuthorityClassification:
    markers = _declaration_control_markers(value)
    destinations = markers & _MCP_DESTINATION_MARKERS
    if len(destinations) != 1:
        return _unknown_classification("mcp_destination_ambiguous_or_missing")
    capability = PROVIDER_CONNECTOR if "connector_id" in destinations else PROVIDER_REMOTE_MCP
    return ToolAuthorityClassification(
        authority_class=PROVIDER_EXTERNAL_AUTHORITY,
        capability_id=capability,
        destination_id=None,
        provider_tool_declaration=True,
        unreviewed_external_authority=True,
        reason_code="client_mcp_destination_not_reviewed",
    )


def _is_recognizable_client_tool_shape(tool_type: str, value: Mapping[object, object]) -> bool:
    if tool_type in {"local_shell", "apply_patch"}:
        return True
    if tool_type in {"function", "custom"}:
        top_level_name = value.get("name")
        nested = value.get(tool_type)
        nested_name = nested.get("name") if isinstance(nested, Mapping) else None
        return (
            isinstance(top_level_name, str)
            and bool(top_level_name)
            and top_level_name == top_level_name.strip()
        ) or (
            isinstance(nested_name, str)
            and bool(nested_name)
            and nested_name == nested_name.strip()
        )
    if tool_type == "namespace":
        name = value.get("name")
        tools = value.get("tools")
        return (
            isinstance(name, str)
            and bool(name)
            and name == name.strip()
            and isinstance(tools, list)
        )
    return False


def _client_declaration_control_markers(
    tool_type: str,
    value: Mapping[object, object],
) -> frozenset[str]:
    """Inspect authority-bearing container keys, never client-owned payloads."""
    found = set(_declaration_control_markers(value))
    if tool_type in {"function", "custom"}:
        nested = value.get(tool_type)
        if isinstance(nested, Mapping):
            found.update(_declaration_control_markers(nested))
    return frozenset(found)


def _declaration_control_markers(value: Mapping[object, object]) -> frozenset[str]:
    """Return reviewed markers only when they are keys at this control level."""
    return frozenset(
        key for key in value if isinstance(key, str) and key in _PROVIDER_AUTHORITY_MARKERS
    )


def _namespace_children_are_client_operated(value: Mapping[object, object]) -> bool:
    """Validate bounded namespace authority without entering opaque child schemas."""
    stack: list[tuple[Mapping[object, object], int]] = [(value, 1)]
    seen_namespaces: set[int] = set()
    child_count = 0

    while stack:
        namespace, depth = stack.pop()
        namespace_id = id(namespace)
        if namespace_id in seen_namespaces or depth > _MAX_NAMESPACE_DEPTH:
            return False
        seen_namespaces.add(namespace_id)

        if _client_declaration_control_markers("namespace", namespace):
            return False
        if not _is_recognizable_client_tool_shape("namespace", namespace):
            return False
        children = namespace.get("tools")
        if not isinstance(children, list):
            return False
        child_count += len(children)
        if child_count > _MAX_NAMESPACE_CHILD_DECLARATIONS:
            return False

        for child in children:
            if not isinstance(child, Mapping):
                return False
            child_type = child.get("type")
            if not isinstance(child_type, str) or child_type not in CLIENT_TOOL_ALIASES:
                return False
            if child_type == "namespace":
                stack.append((child, depth + 1))
                continue
            if _client_declaration_control_markers(child_type, child):
                return False
            if not _is_recognizable_client_tool_shape(child_type, child):
                return False
    return True


def _parse_capability_list(value: object, *, maximum: int) -> tuple[str, ...] | None:
    if not isinstance(value, list) or len(value) > maximum:
        return None
    if any(not isinstance(item, str) or item not in KNOWN_EXTERNAL_CAPABILITIES for item in value):
        return None
    if len(set(value)) != len(value):
        return None
    return tuple(sorted(value))


def _parse_destination_list(value: object, *, maximum: int) -> tuple[str, ...] | None:
    if not isinstance(value, list) or len(value) > maximum:
        return None
    if any(not _is_normalized_destination_id(item) for item in value):
        return None
    if len(set(value)) != len(value):
        return None
    return tuple(sorted(value))


def _destinations_match_capabilities(
    capabilities: tuple[str, ...], destinations: tuple[str, ...]
) -> bool:
    capability_set = set(capabilities)
    required_kinds = {
        kind
        for kind, capability in (
            ("connector", PROVIDER_CONNECTOR),
            ("remote_mcp", PROVIDER_REMOTE_MCP),
        )
        if capability in capability_set
    }
    actual_kinds = {_destination_kind(destination) for destination in destinations}
    return actual_kinds == required_kinds


def _destination_matches_capability(destination_id: object, capability_id: str) -> bool:
    if not _is_normalized_destination_id(destination_id):
        return False
    expected = "connector" if capability_id == PROVIDER_CONNECTOR else "remote_mcp"
    return (
        capability_id in DESTINATION_CAPABILITIES and _destination_kind(destination_id) == expected
    )


def _is_normalized_destination_id(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    match = _DESTINATION_ID_PATTERN.fullmatch(value)
    if match is None:
        return False
    opaque = match.group("opaque")
    terms = set(filter(None, re.split(r"[-_]", opaque)))
    return not opaque.startswith(("sk-", "sk_")) and not terms.intersection(_SECRET_WORDS)


def _destination_kind(destination_id: str) -> str:
    match = _DESTINATION_ID_PATTERN.fullmatch(destination_id)
    if match is None:
        raise ValueError("The destination identifier is not canonical.")
    return match.group("kind")


def _invalid_key_policy(reason_code: str) -> KeyPolicyParseResult:
    return KeyPolicyParseResult(valid=False, present=True, policy=None, reason_code=reason_code)


def _invalid_route_policy(reason_code: str) -> RoutePolicyParseResult:
    return RoutePolicyParseResult(valid=False, present=True, policy=None, reason_code=reason_code)


def _unknown_classification(
    reason_code: str,
    *,
    provider_declaration: bool = True,
) -> ToolAuthorityClassification:
    return ToolAuthorityClassification(
        authority_class=UNKNOWN_EXTERNAL_AUTHORITY,
        capability_id=None,
        destination_id=None,
        provider_tool_declaration=provider_declaration,
        unreviewed_external_authority=False,
        reason_code=reason_code,
    )


def _is_exact_version(value: object) -> bool:
    return type(value) is int and value == EXTERNAL_TOOL_POLICY_VERSION


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _is_non_negative_int(value: object) -> bool:
    return type(value) is int and value >= 0
