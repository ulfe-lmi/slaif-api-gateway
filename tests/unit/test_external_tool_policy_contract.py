from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from slaif_gateway.services.external_tool_policy_contract import (
    ABSOLUTE_MAX_APPROVED_DESTINATIONS,
    ABSOLUTE_MAX_DISTINCT_CAPABILITIES,
    ABSOLUTE_MAX_PROVIDER_TOOL_CALLS,
    ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS,
    CLIENT_OPERATED_AUTHORITY,
    CLIENT_TOOL_ALIASES,
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    DESTINATION_CAPABILITIES,
    EXTERNAL_TOOL_FENCED,
    KNOWN_EXTERNAL_CAPABILITIES,
    PROVIDER_CODE_INTERPRETER,
    PROVIDER_COMPUTER_USE,
    PROVIDER_CONNECTOR,
    PROVIDER_EXTERNAL_AUTHORITY,
    PROVIDER_FILE_SEARCH,
    PROVIDER_HOSTED_SHELL,
    PROVIDER_IMAGE_GENERATION,
    PROVIDER_REMOTE_MCP,
    PROVIDER_SKILL,
    PROVIDER_TOOL_SEARCH,
    PROVIDER_URL_FETCH,
    PROVIDER_WEB_SEARCH,
    STRICT_BOUNDED,
    UNKNOWN_EXTERNAL_AUTHORITY,
    ClassifiedExternalToolRequest,
    ExternalToolKeyLimitFacts,
    ExternalToolOperatorCeilings,
    classify_external_tool_request,
    classify_reviewed_external_tool,
    classify_tool_choice,
    classify_tool_declaration,
    decide_external_tool_admission,
    is_search_specific_chat_completion_model,
    parse_key_external_tool_policy,
    parse_route_external_tool_policy,
    strict_key_policy,
    strict_route_policy,
)


def _key_policy(
    *,
    capabilities: list[str] | None = None,
    destinations: list[str] | None = None,
    call_cap: int = 4,
) -> dict[str, object]:
    return {
        "version": 1,
        "mode": EXTERNAL_TOOL_FENCED,
        "allowed_capabilities": capabilities or [PROVIDER_WEB_SEARCH],
        "allowed_destination_ids": destinations or [],
        "max_provider_tool_calls_per_request": call_cap,
        "single_request_overrun_acknowledged": True,
    }


def _route_policy(
    *,
    capabilities: list[str] | None = None,
    destinations: list[str] | None = None,
    call_cap: int = 3,
) -> dict[str, object]:
    return {
        "version": 1,
        "supported_capabilities": capabilities or [PROVIDER_WEB_SEARCH],
        "approved_destination_ids": destinations or [],
        "max_provider_tool_calls_per_request": call_cap,
        "call_limit_enforced": True,
        "final_usage_required": True,
        "final_cost_required": True,
    }


def _limits(**overrides: object) -> ExternalToolKeyLimitFacts:
    values: dict[str, object] = {
        "key_purpose": "standard",
        "request_limit_total": 10,
        "token_limit_total": 100_000,
        "cost_limit_eur": Decimal("5.00"),
    }
    values.update(overrides)
    return ExternalToolKeyLimitFacts(**values)  # type: ignore[arg-type]


def _request(
    *,
    capabilities: tuple[str, ...] = (PROVIDER_WEB_SEARCH,),
    destinations: tuple[str, ...] = (),
    declaration_count: int = 1,
    call_cap: int = 2,
    unknown: bool = False,
    unreviewed: bool = False,
    unsupported_state: bool = False,
    approval_floor_satisfied: bool = True,
) -> ClassifiedExternalToolRequest:
    return ClassifiedExternalToolRequest(
        capabilities=capabilities,
        destination_ids=destinations,
        provider_tool_declaration_count=declaration_count,
        requested_provider_tool_calls_per_request=call_cap,
        unknown_external_authority=unknown,
        unreviewed_external_authority=unreviewed,
        unsupported_external_state=unsupported_state,
        approval_floor_satisfied=approval_floor_satisfied,
    )


@pytest.mark.parametrize(
    ("alias", "capability"),
    [
        ("web_search", PROVIDER_WEB_SEARCH),
        ("web_search_preview", PROVIDER_WEB_SEARCH),
        ("file_search", PROVIDER_FILE_SEARCH),
        ("code_interpreter", PROVIDER_CODE_INTERPRETER),
        ("shell", PROVIDER_HOSTED_SHELL),
        ("image_generation", PROVIDER_IMAGE_GENERATION),
        ("computer", PROVIDER_COMPUTER_USE),
        ("computer_use", PROVIDER_COMPUTER_USE),
        ("computer_use_preview", PROVIDER_COMPUTER_USE),
        ("tool_search", PROVIDER_TOOL_SEARCH),
        ("skill", PROVIDER_SKILL),
        ("skills", PROVIDER_SKILL),
    ],
)
def test_reviewed_provider_aliases_map_to_one_canonical_capability(
    alias: str, capability: str
) -> None:
    result = classify_tool_declaration({"type": alias})

    assert result.authority_class == PROVIDER_EXTERNAL_AUTHORITY
    assert result.capability_id == capability
    assert result.provider_tool_declaration is True
    assert result.unreviewed_external_authority is False


@pytest.mark.parametrize(
    "tool",
    [
        {"type": "function", "name": "local_function"},
        {"type": "function", "function": {"name": "chat_function"}},
        {"type": "custom", "name": "local_custom"},
        {"type": "custom", "custom": {"name": "chat_custom"}},
        {"type": "namespace", "name": "functions", "tools": []},
        {"type": "local_shell"},
        {"type": "apply_patch"},
    ],
)
def test_exact_local_aliases_remain_client_operated_without_provider_markers(
    tool: dict[str, object],
) -> None:
    result = classify_tool_declaration(tool)

    assert result.authority_class == CLIENT_OPERATED_AUTHORITY
    assert result.capability_id is None
    assert result.provider_tool_declaration is False
    assert tool["type"] in CLIENT_TOOL_ALIASES


@pytest.mark.parametrize(
    "tool",
    [
        {"type": "function"},
        {"type": "custom", "name": " custom"},
        {"type": "namespace", "name": "functions"},
        {"type": "namespace", "name": "", "tools": []},
    ],
)
def test_incomplete_client_tool_shapes_fail_closed(tool: dict[str, object]) -> None:
    result = classify_tool_declaration(tool)

    assert result.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
    assert result.reason_code == "malformed_client_tool_shape"


OPAQUE_BUSINESS_FIELD_NAMES = (
    "headers",
    "authorization",
    "server_url",
    "connector_id",
    "api_key",
    "bearer_token",
    "cookie",
    "token",
)


@pytest.mark.parametrize("marker", OPAQUE_BUSINESS_FIELD_NAMES)
def test_function_parameter_business_fields_are_opaque_to_authority(marker: str) -> None:
    secret = "raw-secret-sentinel"
    responses_style = classify_tool_declaration(
        {
            "type": "function",
            "name": "local_function",
            "description": f"Collect a business {marker} value",
            "parameters": {
                "type": "object",
                "properties": {marker: {"type": "string", "example": secret}},
            },
        }
    )
    chat_style = classify_tool_declaration(
        {
            "type": "function",
            "function": {
                "name": "local_function",
                "description": f"Collect a business {marker} value",
                "parameters": {
                    "type": "object",
                    "properties": {marker: {"type": "string", "example": secret}},
                },
            },
        }
    )

    assert responses_style.authority_class == CLIENT_OPERATED_AUTHORITY
    assert chat_style.authority_class == CLIENT_OPERATED_AUTHORITY
    assert secret not in repr((responses_style, chat_style))


@pytest.mark.parametrize("nested_container", [False, True])
@pytest.mark.parametrize(
    "marker",
    [
        "server_url",
        "connector_id",
        "authorization",
        "require_approval",
        "defer_loading",
        "server_label",
        "allowed_tools",
        "headers",
        "cookie",
        "bearer_token",
    ],
)
def test_provider_marker_at_local_declaration_control_level_is_unknown_external(
    marker: str,
    nested_container: bool,
) -> None:
    secret = "raw-secret-sentinel"
    tool: dict[str, object] = {"type": "function", "name": "local_function"}
    if nested_container:
        tool = {
            "type": "function",
            "function": {"name": "local_function", marker: secret},
        }
    else:
        tool[marker] = secret
    result = classify_tool_declaration(tool)

    assert result.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
    assert result.reason_code == "mixed_local_external_authority"
    assert secret not in repr(result)


def test_custom_description_format_and_grammar_are_opaque_and_not_retained() -> None:
    secret = "raw-custom-payload-sentinel"
    responses_style = classify_tool_declaration(
        {
            "type": "custom",
            "name": "local_custom",
            "description": f"Grammar mentions authorization and server_url: {secret}",
            "format": {
                "type": "grammar",
                "definition": {
                    "headers": secret,
                    "authorization": secret,
                    "connector_id": secret,
                },
            },
        }
    )
    nested_style = classify_tool_declaration(
        {
            "type": "custom",
            "custom": {
                "name": "local_custom",
                "description": f"Grammar mentions headers: {secret}",
                "format": {"grammar": {"authorization": secret}},
            },
        }
    )

    assert responses_style.authority_class == CLIENT_OPERATED_AUTHORITY
    assert nested_style.authority_class == CLIENT_OPERATED_AUTHORITY
    assert responses_style.reason_code == "client_operated_tool"
    assert secret not in repr((responses_style, nested_style))


def test_client_classification_does_not_claim_endpoint_schema_acceptance() -> None:
    result = classify_tool_declaration(
        {
            "type": "function",
            "name": "local_function",
            "parameters": {"type": "not-a-valid-json-schema-type", "headers": object()},
        }
    )

    # Authority classification is deliberately narrower than endpoint validation.
    assert result.authority_class == CLIENT_OPERATED_AUTHORITY


def test_namespace_with_local_children_keeps_opaque_payloads_client_operated() -> None:
    secret = "raw-namespace-child-sentinel"
    result = classify_tool_declaration(
        {
            "type": "namespace",
            "name": "functions",
            "description": f"Namespace mentions authorization: {secret}",
            "tools": [
                {
                    "type": "function",
                    "name": "local_function",
                    "parameters": {"properties": {"server_url": {"default": secret}}},
                },
                {
                    "type": "custom",
                    "name": "local_custom",
                    "format": {"grammar": {"headers": secret}},
                },
                {"type": "local_shell"},
                {"type": "apply_patch"},
                {
                    "type": "namespace",
                    "name": "collaboration",
                    "tools": [
                        {
                            "type": "function",
                            "name": "nested_local",
                            "parameters": {"properties": {"authorization": {}}},
                        }
                    ],
                },
            ],
        }
    )

    assert result.authority_class == CLIENT_OPERATED_AUTHORITY
    assert secret not in repr(result)


def test_namespace_control_marker_remains_mixed_external_authority() -> None:
    result = classify_tool_declaration(
        {
            "type": "namespace",
            "name": "functions",
            "tools": [],
            "require_approval": "never",
        }
    )

    assert result.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
    assert result.reason_code == "mixed_local_external_authority"


def test_namespace_children_cannot_hide_external_unknown_malformed_or_cycles() -> None:
    children: list[object] = [
        {"type": "mcp", "server_url": "https://raw.example/mcp"},
        {"type": "web_search"},
        {"type": "unknown"},
        {"type": "function"},
        "not-a-declaration",
    ]
    for child in children:
        result = classify_tool_declaration(
            {"type": "namespace", "name": "functions", "tools": [child]}
        )
        assert result.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
        assert result.reason_code == "namespace_child_external_or_invalid"

    cyclic: dict[str, object] = {"type": "namespace", "name": "cycle"}
    cyclic["tools"] = [cyclic]
    cycle_result = classify_tool_declaration(cyclic)
    assert cycle_result.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
    assert cycle_result.reason_code == "namespace_child_external_or_invalid"


def test_namespace_depth_and_total_child_count_are_bounded() -> None:
    too_many = classify_tool_declaration(
        {
            "type": "namespace",
            "name": "functions",
            "tools": [{"type": "function", "name": f"function_{index}"} for index in range(17)],
        }
    )
    nested: dict[str, object] = {
        "type": "namespace",
        "name": "level_5",
        "tools": [{"type": "function", "name": "leaf"}],
    }
    for depth in range(4, 0, -1):
        nested = {"type": "namespace", "name": f"level_{depth}", "tools": [nested]}
    too_deep = classify_tool_declaration(nested)

    assert too_many.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
    assert too_deep.authority_class == UNKNOWN_EXTERNAL_AUTHORITY


def test_cyclic_opaque_function_schema_does_not_enter_authority_traversal() -> None:
    cyclic_schema: dict[str, object] = {"type": "object"}
    cyclic_schema["properties"] = cyclic_schema

    result = classify_tool_declaration(
        {"type": "function", "name": "local_function", "parameters": cyclic_schema}
    )

    assert result.authority_class == CLIENT_OPERATED_AUTHORITY


def test_provider_configuration_payload_is_opaque_but_control_markers_still_deny() -> None:
    opaque = classify_tool_declaration(
        {"type": "web_search", "filters": {"headers": "business-field"}}
    )
    control = classify_tool_declaration({"type": "web_search", "headers": "raw-header"})

    assert opaque.authority_class == PROVIDER_EXTERNAL_AUTHORITY
    assert opaque.capability_id == PROVIDER_WEB_SEARCH
    assert control.authority_class == UNKNOWN_EXTERNAL_AUTHORITY
    assert control.reason_code == "malformed_provider_tool_authority"


def test_wire_mcp_distinguishes_connector_and_remote_but_never_trusts_raw_destination() -> None:
    connector = classify_tool_declaration(
        {
            "type": "mcp",
            "connector_id": "raw-connector-sentinel",
            "authorization": "raw-auth-sentinel",
            "require_approval": "never",
        }
    )
    remote = classify_tool_declaration(
        {
            "type": "mcp",
            "server_url": "https://raw.example/mcp",
            "tool_filter": {"connector_id": "opaque-business-filter-value"},
        }
    )

    assert connector.capability_id == PROVIDER_CONNECTOR
    assert remote.capability_id == PROVIDER_REMOTE_MCP
    assert connector.unreviewed_external_authority is True
    assert remote.unreviewed_external_authority is True
    assert connector.destination_id is None
    assert remote.destination_id is None
    safe = repr((connector, remote))
    assert "raw-connector-sentinel" not in safe
    assert "raw-auth-sentinel" not in safe
    assert "raw.example" not in safe


@pytest.mark.parametrize(
    "tool",
    [
        {"type": "mcp"},
        {"type": "mcp", "server_url": "https://one", "connector_id": "two"},
        {"type": "unknown"},
        {"type": " function"},
        {"type": 7},
        {},
        "function",
    ],
)
def test_malformed_unknown_and_ambiguous_tools_fail_closed(tool: object) -> None:
    assert classify_tool_declaration(tool).authority_class == UNKNOWN_EXTERNAL_AUTHORITY


@pytest.mark.parametrize("choice", ["none", "auto", "required", None])
def test_neutral_tool_choices_are_not_external(choice: object) -> None:
    assert classify_tool_choice(choice).authority_class == CLIENT_OPERATED_AUTHORITY


def test_tool_choice_classifies_provider_aliases_and_denies_unknown_shapes() -> None:
    provider = classify_tool_choice({"type": "web_search"})
    unknown = classify_tool_choice({"type": "made_up"})

    assert provider.capability_id == PROVIDER_WEB_SEARCH
    assert provider.provider_tool_declaration is False
    assert unknown.authority_class == UNKNOWN_EXTERNAL_AUTHORITY


def test_reviewed_destination_fact_requires_exact_opaque_kind_and_no_secret_shape() -> None:
    connector = classify_reviewed_external_tool(
        PROVIDER_CONNECTOR, destination_id="connector:dst_alpha"
    )
    remote = classify_reviewed_external_tool(
        PROVIDER_REMOTE_MCP, destination_id="remote_mcp:dst_beta"
    )

    assert connector.destination_id == "connector:dst_alpha"
    assert remote.destination_id == "remote_mcp:dst_beta"
    assert connector.unreviewed_external_authority is False

    with pytest.raises(ValueError, match="does not match"):
        classify_reviewed_external_tool(PROVIDER_CONNECTOR, destination_id="remote_mcp:dst_beta")
    with pytest.raises(ValueError, match="does not match"):
        classify_reviewed_external_tool(PROVIDER_CONNECTOR, destination_id="connector:secret")
    with pytest.raises(ValueError, match="does not accept"):
        classify_reviewed_external_tool(PROVIDER_WEB_SEARCH, destination_id="connector:dst_alpha")


def test_request_classifier_combines_reviewed_alias_model_url_and_destination_facts() -> None:
    reviewed = classify_reviewed_external_tool(
        PROVIDER_CONNECTOR, destination_id="connector:dst_alpha"
    )
    result = classify_external_tool_request(
        tools=[{"type": "file_search"}, {"type": "function", "name": "local_function"}],
        tool_choice={"type": "file_search"},
        web_search_options_present=True,
        search_specific_model=True,
        provider_url_fetch_requested=True,
        reviewed_external_tools=[reviewed],
        requested_provider_tool_calls_per_request=4,
    )

    assert result.capabilities == (
        PROVIDER_CONNECTOR,
        PROVIDER_FILE_SEARCH,
        PROVIDER_URL_FETCH,
        PROVIDER_WEB_SEARCH,
    )
    assert result.destination_ids == ("connector:dst_alpha",)
    assert result.provider_tool_declaration_count == 3
    assert result.requested_provider_tool_calls_per_request == 4
    assert result.unknown_external_authority is False
    assert result.has_external_authority is True


def test_request_classifier_marks_non_json_collection_bad_booleans_and_call_caps_unknown() -> None:
    result = classify_external_tool_request(
        tools=({"type": "function", "name": "local_function"},),
        web_search_options_present=1,  # type: ignore[arg-type]
        requested_provider_tool_calls_per_request=True,
    )

    assert result.unknown_external_authority is True
    assert result.requested_provider_tool_calls_per_request == 0


def test_direct_request_and_key_fact_dtos_reject_arbitrary_or_coerced_values_safely() -> None:
    with pytest.raises(ValueError, match="request facts are not canonical") as request_exc:
        _request(capabilities=("raw-arbitrary-label",))
    assert "raw-arbitrary-label" not in str(request_exc.value)

    with pytest.raises(ValueError, match="key purpose is not canonical") as purpose_exc:
        _limits(key_purpose="raw-purpose-label")
    assert "raw-purpose-label" not in str(purpose_exc.value)

    with pytest.raises(ValueError, match="integer limit facts are not canonical"):
        _limits(request_limit_total=True)
    with pytest.raises(ValueError, match="cost limit fact is not canonical"):
        _limits(cost_limit_eur=1.0)


def test_search_model_recognition_is_exact_and_low_cardinality() -> None:
    assert is_search_specific_chat_completion_model("gpt-5-search-api") is True
    assert is_search_specific_chat_completion_model("vendor-model-search-preview") is True
    assert is_search_specific_chat_completion_model(" gpt-5-search-api") is False
    assert is_search_specific_chat_completion_model(7) is False


def test_operator_ceiling_defaults_are_exact_immutable_absolute_maxima() -> None:
    ceilings = DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS

    assert ceilings.max_distinct_capabilities == ABSOLUTE_MAX_DISTINCT_CAPABILITIES == 16
    assert ceilings.max_approved_destinations == ABSOLUTE_MAX_APPROVED_DESTINATIONS == 8
    assert (
        ceilings.max_provider_tool_declarations_per_request
        == ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS
        == 16
    )
    assert ceilings.max_provider_tool_calls_per_request == ABSOLUTE_MAX_PROVIDER_TOOL_CALLS == 16
    with pytest.raises(FrozenInstanceError):
        ceilings.max_provider_tool_calls_per_request = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_distinct_capabilities": 0},
        {"max_approved_destinations": True},
        {"max_provider_tool_declarations_per_request": 17},
        {"max_provider_tool_calls_per_request": 17},
    ],
)
def test_operator_ceilings_reject_zero_coerced_and_above_absolute_values(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="outside the contract bounds"):
        ExternalToolOperatorCeilings(**overrides)  # type: ignore[arg-type]


def test_missing_and_exact_strict_key_policy_are_canonical_strict_default() -> None:
    missing = parse_key_external_tool_policy(None)
    exact = parse_key_external_tool_policy(
        {
            "version": 1,
            "mode": STRICT_BOUNDED,
            "allowed_capabilities": [],
            "allowed_destination_ids": [],
            "max_provider_tool_calls_per_request": 0,
            "single_request_overrun_acknowledged": False,
        }
    )

    assert missing.valid is True and missing.present is False
    assert missing.policy == strict_key_policy()
    assert exact.valid is True and exact.present is True
    assert exact.policy == strict_key_policy()


def test_valid_external_key_policy_is_sorted_and_exact() -> None:
    parsed = parse_key_external_tool_policy(
        _key_policy(capabilities=[PROVIDER_WEB_SEARCH, PROVIDER_FILE_SEARCH])
    )

    assert parsed.valid is True
    assert parsed.policy is not None
    assert parsed.policy.allowed_capabilities == (
        PROVIDER_FILE_SEARCH,
        PROVIDER_WEB_SEARCH,
    )
    assert parsed.policy.single_request_overrun_acknowledged is True


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"drop": "version"}, "key_policy_invalid_fields"),
        ({"extra": ("unexpected", True)}, "key_policy_invalid_fields"),
        ({"replace": ("version", True)}, "key_policy_invalid_version"),
        ({"replace": ("mode", "external")}, "key_policy_invalid_mode"),
        (
            {"replace": ("allowed_capabilities", "provider_web_search")},
            "key_policy_invalid_capabilities",
        ),
        (
            {
                "replace": (
                    "allowed_capabilities",
                    [PROVIDER_WEB_SEARCH, PROVIDER_WEB_SEARCH],
                )
            },
            "key_policy_invalid_capabilities",
        ),
        ({"replace": ("allowed_capabilities", ["unknown"])}, "key_policy_invalid_capabilities"),
        (
            {"replace": ("allowed_destination_ids", ["https://example.test"])},
            "key_policy_invalid_destinations",
        ),
        (
            {"replace": ("allowed_destination_ids", ["connector:secret"])},
            "key_policy_invalid_destinations",
        ),
        (
            {"replace": ("allowed_destination_ids", ["connector:" + ("a" * 60)])},
            "key_policy_invalid_destinations",
        ),
        ({"replace": ("max_provider_tool_calls_per_request", True)}, "key_policy_invalid_call_cap"),
        (
            {"replace": ("single_request_overrun_acknowledged", 1)},
            "key_policy_invalid_acknowledgement",
        ),
    ],
)
def test_key_schema_rejects_partial_extra_coerced_duplicate_unknown_and_secret_values(
    mutation: dict[str, object], reason: str
) -> None:
    value = _key_policy()
    if "drop" in mutation:
        value.pop(str(mutation["drop"]))
    if "extra" in mutation:
        key, extra_value = mutation["extra"]  # type: ignore[misc]
        value[key] = extra_value
    if "replace" in mutation:
        key, replacement = mutation["replace"]  # type: ignore[misc]
        value[key] = replacement

    parsed = parse_key_external_tool_policy(value)

    assert parsed.valid is False
    assert parsed.policy is None
    assert parsed.reason_code == reason


def test_key_schema_rejects_over_ceiling_and_destination_capability_mismatch() -> None:
    narrow = ExternalToolOperatorCeilings(
        max_distinct_capabilities=1,
        max_approved_destinations=1,
        max_provider_tool_declarations_per_request=1,
        max_provider_tool_calls_per_request=1,
    )
    too_many_capabilities = parse_key_external_tool_policy(
        _key_policy(capabilities=[PROVIDER_WEB_SEARCH, PROVIDER_FILE_SEARCH], call_cap=1),
        ceilings=narrow,
    )
    too_many_calls = parse_key_external_tool_policy(_key_policy(call_cap=2), ceilings=narrow)
    missing_destination = parse_key_external_tool_policy(
        _key_policy(capabilities=[PROVIDER_CONNECTOR], destinations=[])
    )

    assert too_many_capabilities.valid is False
    assert too_many_calls.valid is False
    assert missing_destination.valid is False


def test_route_policy_missing_strict_and_valid_external_shapes() -> None:
    missing = parse_route_external_tool_policy(None)
    strict = parse_route_external_tool_policy(
        {
            "version": 1,
            "supported_capabilities": [],
            "approved_destination_ids": [],
            "max_provider_tool_calls_per_request": 0,
            "call_limit_enforced": False,
            "final_usage_required": False,
            "final_cost_required": False,
        }
    )
    external = parse_route_external_tool_policy(_route_policy())

    assert missing.valid is True and missing.present is False
    assert missing.policy == strict_route_policy()
    assert strict.valid is True and strict.policy == strict_route_policy()
    assert external.valid is True
    assert external.policy is not None
    assert external.policy.call_limit_enforced is True


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("version", "1", "route_policy_invalid_version"),
        ("supported_capabilities", ["unknown"], "route_policy_invalid_capabilities"),
        ("approved_destination_ids", ["connector:token"], "route_policy_invalid_destinations"),
        ("max_provider_tool_calls_per_request", 1.0, "route_policy_invalid_call_cap"),
        ("call_limit_enforced", 1, "route_policy_invalid_evidence_flags"),
        ("final_usage_required", False, "route_policy_external_requirements_not_met"),
        ("final_cost_required", False, "route_policy_external_requirements_not_met"),
    ],
)
def test_route_schema_rejects_coerced_unknown_secret_and_incomplete_evidence(
    field: str, value: object, reason: str
) -> None:
    route = _route_policy()
    route[field] = value

    parsed = parse_route_external_tool_policy(route)

    assert parsed.valid is False
    assert parsed.reason_code == reason


def test_destination_lists_are_required_only_for_matching_destination_capabilities() -> None:
    capabilities = [PROVIDER_CONNECTOR, PROVIDER_REMOTE_MCP]
    destinations = ["connector:dst_one", "remote_mcp:dst_two"]

    key = parse_key_external_tool_policy(
        _key_policy(capabilities=capabilities, destinations=destinations)
    )
    route = parse_route_external_tool_policy(
        _route_policy(capabilities=capabilities, destinations=destinations)
    )

    assert key.valid is True
    assert route.valid is True
    assert DESTINATION_CAPABILITIES == frozenset(capabilities)


def test_no_external_authority_preserves_strict_processing_without_valid_policies() -> None:
    decision = decide_external_tool_admission(
        request=_request(capabilities=(), declaration_count=0, call_cap=0),
        key_policy=parse_key_external_tool_policy({"bad": "shape"}),
        route_policy=parse_route_external_tool_policy({"bad": "shape"}),
        ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        key_limits=_limits(key_purpose="trusted_calibration"),
    )

    assert decision.allowed is True
    assert decision.quota_mode == STRICT_BOUNDED
    assert decision.reason_code == "no_external_authority"
    assert decision.exclusive_key_fence_required is False


def test_exact_standard_finite_intersection_returns_all_positive_obligations() -> None:
    decision = decide_external_tool_admission(
        request=_request(),
        key_policy=parse_key_external_tool_policy(_key_policy()),
        route_policy=parse_route_external_tool_policy(_route_policy()),
        ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        key_limits=_limits(),
    )

    assert decision.to_safe_dict() == {
        "allowed": True,
        "quota_mode": EXTERNAL_TOOL_FENCED,
        "effective_tool_call_cap": 3,
        "reason_code": "external_tool_fenced_allowed",
        "exclusive_key_fence_required": True,
        "single_request_overrun_accepted": True,
        "hold_on_missing_or_ambiguous_final_cost": True,
        "following_requests_block_after_exhaustion": True,
    }


def test_reviewed_destination_must_intersect_key_and_route_lists() -> None:
    request = _request(
        capabilities=(PROVIDER_CONNECTOR,),
        destinations=("connector:dst_alpha",),
    )
    key = parse_key_external_tool_policy(
        _key_policy(capabilities=[PROVIDER_CONNECTOR], destinations=["connector:dst_alpha"])
    )
    route = parse_route_external_tool_policy(
        _route_policy(capabilities=[PROVIDER_CONNECTOR], destinations=["connector:dst_alpha"])
    )

    assert decide_external_tool_admission(
        request=request,
        key_policy=key,
        route_policy=route,
        ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        key_limits=_limits(),
    ).allowed

    mismatch = _request(
        capabilities=(PROVIDER_CONNECTOR,),
        destinations=("connector:dst_other",),
    )
    denied = decide_external_tool_admission(
        request=mismatch,
        key_policy=key,
        route_policy=route,
        ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        key_limits=_limits(),
    )
    assert denied.allowed is False
    assert denied.reason_code == "key_destination_mismatch"


@pytest.mark.parametrize(
    ("request_fact", "key_value", "route_value", "limits", "reason"),
    [
        (
            _request(unknown=True),
            _key_policy(),
            _route_policy(),
            _limits(),
            "unknown_external_authority",
        ),
        (
            _request(unsupported_state=True),
            _key_policy(),
            _route_policy(),
            _limits(),
            "unsupported_external_state",
        ),
        (
            _request(unreviewed=True),
            _key_policy(),
            _route_policy(),
            _limits(),
            "unreviewed_external_authority",
        ),
        (
            _request(approval_floor_satisfied=False),
            _key_policy(),
            _route_policy(),
            _limits(),
            "approval_floor_not_satisfied",
        ),
        (
            _request(call_cap=0),
            _key_policy(),
            _route_policy(),
            _limits(),
            "provider_tool_call_cap_required",
        ),
        (_request(), None, _route_policy(), _limits(), "key_policy_missing"),
        (_request(), {"bad": True}, _route_policy(), _limits(), "key_policy_invalid"),
        (
            _request(),
            {
                "version": 1,
                "mode": STRICT_BOUNDED,
                "allowed_capabilities": [],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 0,
                "single_request_overrun_acknowledged": False,
            },
            _route_policy(),
            _limits(),
            "strict_bounded_external_authority_denied",
        ),
        (_request(), _key_policy(), None, _limits(), "route_external_support_missing"),
        (_request(), _key_policy(), {"bad": True}, _limits(), "route_policy_invalid"),
        (
            _request(capabilities=(PROVIDER_FILE_SEARCH,)),
            _key_policy(),
            _route_policy(capabilities=[PROVIDER_FILE_SEARCH]),
            _limits(),
            "key_capability_mismatch",
        ),
        (
            _request(capabilities=(PROVIDER_FILE_SEARCH,)),
            _key_policy(capabilities=[PROVIDER_FILE_SEARCH]),
            _route_policy(),
            _limits(),
            "route_capability_mismatch",
        ),
        (
            _request(),
            _key_policy(),
            _route_policy(),
            _limits(key_purpose="trusted_calibration"),
            "standard_key_required",
        ),
        (
            _request(),
            _key_policy(),
            _route_policy(),
            _limits(request_limit_total=None),
            "positive_finite_key_limits_required",
        ),
        (
            _request(),
            _key_policy(),
            _route_policy(),
            _limits(token_limit_total=0),
            "positive_finite_key_limits_required",
        ),
        (
            _request(),
            _key_policy(),
            _route_policy(),
            _limits(cost_limit_eur=Decimal("Infinity")),
            "positive_finite_key_limits_required",
        ),
    ],
)
def test_admission_matrix_denies_every_missing_ambiguous_or_unbounded_fact(
    request_fact: ClassifiedExternalToolRequest,
    key_value: object,
    route_value: object,
    limits: ExternalToolKeyLimitFacts,
    reason: str,
) -> None:
    decision = decide_external_tool_admission(
        request=request_fact,
        key_policy=parse_key_external_tool_policy(key_value),
        route_policy=parse_route_external_tool_policy(route_value),
        ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        key_limits=limits,
    )

    assert decision.allowed is False
    assert decision.reason_code == reason
    assert decision.effective_tool_call_cap == 0
    assert decision.exclusive_key_fence_required is False
    assert decision.single_request_overrun_accepted is False
    assert decision.hold_on_missing_or_ambiguous_final_cost is False
    assert decision.following_requests_block_after_exhaustion is False


def test_operator_declaration_and_call_ceilings_precede_policy_allowance() -> None:
    ceilings = ExternalToolOperatorCeilings(
        max_distinct_capabilities=2,
        max_approved_destinations=1,
        max_provider_tool_declarations_per_request=1,
        max_provider_tool_calls_per_request=2,
    )
    too_many_declarations = decide_external_tool_admission(
        request=_request(declaration_count=2),
        key_policy=parse_key_external_tool_policy(_key_policy(call_cap=2), ceilings=ceilings),
        route_policy=parse_route_external_tool_policy(_route_policy(call_cap=2), ceilings=ceilings),
        ceilings=ceilings,
        key_limits=_limits(),
    )
    too_many_calls = decide_external_tool_admission(
        request=_request(call_cap=3),
        key_policy=parse_key_external_tool_policy(_key_policy(call_cap=2), ceilings=ceilings),
        route_policy=parse_route_external_tool_policy(_route_policy(call_cap=2), ceilings=ceilings),
        ceilings=ceilings,
        key_limits=_limits(),
    )

    assert too_many_declarations.reason_code == "operator_declaration_ceiling_exceeded"
    assert too_many_calls.reason_code == "operator_call_ceiling_exceeded"


def test_policy_results_decisions_and_errors_never_echo_malformed_raw_values() -> None:
    secret = "sk-secret-provider-value-that-must-not-appear"
    key = parse_key_external_tool_policy({"authorization": secret})
    route = parse_route_external_tool_policy({"server_url": secret})
    request = classify_external_tool_request(
        tools=[{"type": "function", "name": "local_function", "authorization": secret}],
        requested_provider_tool_calls_per_request=1,
    )
    decision = decide_external_tool_admission(
        request=request,
        key_policy=key,
        route_policy=route,
        ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        key_limits=_limits(),
    )

    assert secret not in repr((key, route, request, decision))
    assert set(KNOWN_EXTERNAL_CAPABILITIES) == {
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
