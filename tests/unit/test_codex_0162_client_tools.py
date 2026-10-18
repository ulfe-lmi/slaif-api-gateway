"""Registered 0.162 additional-tools profile contract tests.

These unit tests pin the profile of the REAL registered
``codex-0.162-responses-v1`` module (resolved through the static client
registry, never a substituted spec): the exact synthetic 197-tool
namespace counts (11 + 5 + 181, operator-supplied and explicitly not a
capture of installed plugins), optional ID states, strict
vocabulary/shape negatives, missing-grant rejections, coherent
version-owned facts, the canonical fixture hash, pair registration, and
the 0.162 finite boundaries while the shared/global limits remain
intact.  They are pure in-memory tests with no database or network
dependency.  The independent 21-case profile probe remains external
evidence, not part of this regression suite.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_POLICY_SPEC
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_BUILTIN_NAMESPACES,
    CODEX_0162_CLIENT_MODULE_ID,
    CODEX_0162_CLIENT_MODULE_VERSION,
    CODEX_0162_CLI_VERSION,
    CODEX_0162_FIXTURE_RELATIVE_PATH,
    CODEX_0162_FIXTURE_SHA256,
    CODEX_0162_MAX_NAMESPACES,
    CODEX_0162_MAX_NAMESPACE_TOOLS,
    CODEX_0162_MAX_TOTAL_TOOLS,
    CODEX_0162_POLICY_SPEC,
    CODEX_0162_SOURCE_CONTRACT_COMMIT,
    CODEX_0162_SOURCE_CONTRACT_TAG,
)
from slaif_gateway.modules.clients.registry import (
    CLIENT_MODULE_REGISTRY,
    ModuleSelectionError,
    resolve_responses_client_module,
)
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
)
from slaif_gateway.modules.servers.registry import (
    CLIENT_SERVER_COMPATIBILITY,
    OPENAI_SERVER_MODULE_ID,
    ClientServerPair,
    ensure_client_server_pair,
    ensure_client_module_has_server_pair,
)
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy

FIXTURE = Path(CODEX_0162_FIXTURE_RELATIVE_PATH)
AT_UUID = "at_123e4567-e89b-12d3-a456-426614174000"
MCP_NAMESPACE_COUNTS = {
    "mcp__codex_apps__chatgpt_space": 40,
    "mcp__codex_apps__codex_document_control": 3,
    "mcp__codex_apps__github": 89,
    "mcp__codex_apps__hotline": 1,
    "mcp__codex_apps__pets": 11,
    "mcp__codex_apps__plugin_management": 6,
    "mcp__codex_apps__safety_settings": 5,
    "mcp__codex_apps__search_service": 1,
    "mcp__codex_apps__sites": 25,
}
FUNCTION_TOOL_NAMES = (
    "exec_command",
    "write_stdin",
    "request_user_input",
    "view_image",
    "get_goal",
    "create_goal",
    "update_goal",
    "plan_step",
    "read_file",
    "list_files",
    "apply_diff",
)
MULTI_AGENT_TOOL_NAMES = (
    "close_agent",
    "resume_agent",
    "send_input",
    "spawn_agent",
    "wait_agent",
)


def _settings(hard_max_input_tokens: int = 20_000) -> Settings:
    return Settings(
        DEFAULT_MAX_OUTPUT_TOKENS=12,
        HARD_MAX_OUTPUT_TOKENS=80,
        HARD_MAX_INPUT_TOKENS=hard_max_input_tokens,
    )


def _module():
    """Resolve the real registered 0.162 module through key metadata."""
    policy = {
        "version": 1,
        "allowed_capabilities": [
            "codex_request_envelope",
            "codex_client_tools",
            "codex_streaming_tool_events",
        ],
        "client_module": {
            "id": CODEX_0162_CLIENT_MODULE_ID,
            "version": CODEX_0162_CLIENT_MODULE_VERSION,
            "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
        },
    }
    return resolve_responses_client_module(policy)


def _apply(body: dict[str, object], **overrides: object):
    hard_max = int(overrides.pop("hard_max_input_tokens", 20_000))  # type: ignore[arg-type]
    module = _module()
    normalized = module.normalize_responses(body)
    kwargs: dict[str, object] = {
        "allow_store": True,
        "allow_codex_request_envelope": True,
        "allow_codex_client_tools": True,
        "allow_codex_streaming_tool_events": True,
    }
    kwargs.update(overrides)
    policy = ResponsesRequestPolicy(_settings(hard_max), client_spec=module.policy_spec)
    return module, policy.apply(normalized.body, **kwargs)


def _function_tool(name: str, **overrides: object) -> dict[str, object]:
    tool: dict[str, object] = {
        "type": "function",
        "name": name,
        "description": f"bounded description for {name}",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    tool.update(overrides)
    return tool


def _namespace(name: str, tools: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    namespace: dict[str, object] = {"type": "namespace", "name": name, "tools": tools}
    namespace.update(overrides)
    return namespace


def _item(namespaces: list[dict[str, object]], *, id_value: object = "omitted") -> dict[str, object]:
    item: dict[str, object] = {"type": "additional_tools", "role": "developer", "tools": namespaces}
    if id_value != "omitted":
        item["id"] = id_value
    return item


def _body(item: dict[str, object], *, stream: bool = False) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "codex-0162-unit-model",
        "input": [
            item,
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "bounded 0162 unit request"}],
            },
        ],
    }
    if stream:
        body["stream"] = True
    return body


def _synthetic_197_namespaces() -> list[dict[str, object]]:
    namespaces = [
        _namespace("functions", [_function_tool(name) for name in FUNCTION_TOOL_NAMES]),
        _namespace(
            "multi_agent_v1", [_function_tool(name) for name in MULTI_AGENT_TOOL_NAMES]
        ),
    ]
    for namespace_name, count in MCP_NAMESPACE_COUNTS.items():
        prefix = namespace_name.split("__")[-1][:6]
        namespaces.append(
            _namespace(
                namespace_name,
                [_function_tool(f"{prefix}_tool_{index:03d}") for index in range(count)],
            )
        )
    return namespaces


def _canonical_item(module, result) -> dict[str, object]:
    input_value = result.effective_body["input"]
    assert input_value[0]["type"] == "additional_tools"
    return dict(input_value[0])


# --- registry, identity facts, fixture ---


def test_registered_module_resolves_with_coherent_version_owned_facts() -> None:
    module = _module()
    assert module is CLIENT_MODULE_REGISTRY[CODEX_0162_CLIENT_MODULE_ID]
    assert module.module_id == CODEX_0162_CLIENT_MODULE_ID
    assert module.module_version == CODEX_0162_CLIENT_MODULE_VERSION
    assert module.fixture_sha256 == CODEX_0162_FIXTURE_SHA256
    assert module.policy_spec is CODEX_0162_POLICY_SPEC

    module = _module()
    normalized = module.normalize_responses(_body(_item(_synthetic_197_namespaces())))
    facts = normalized.profile_facts
    assert facts["client_module_id"] == CODEX_0162_CLIENT_MODULE_ID
    assert facts["client_module_version"] == CODEX_0162_CLIENT_MODULE_VERSION
    assert facts["fixture_sha256"] == CODEX_0162_FIXTURE_SHA256
    assert facts["source_contract_tag"] == CODEX_0162_SOURCE_CONTRACT_TAG
    assert facts["source_contract_commit"] == CODEX_0162_SOURCE_CONTRACT_COMMIT
    # 0.162 facts are version-owned: no 0.149 session-fixture or dialect
    # values leak into the canonical profile facts.
    assert "source_contract_fixture_sha256" not in facts
    assert "reasoning_dialect_version" not in facts


def test_stale_or_mismatched_0162_metadata_is_rejected() -> None:
    with pytest.raises(ModuleSelectionError) as wrong_version:
        resolve_responses_client_module(
            {
                "version": 1,
                "client_module": {
                    "id": CODEX_0162_CLIENT_MODULE_ID,
                    "version": "0",
                    "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
                },
            }
        )
    assert wrong_version.value.error_code == "client_module_fixture_mismatch"
    with pytest.raises(ModuleSelectionError) as wrong_digest:
        resolve_responses_client_module(
            {
                "version": 1,
                "client_module": {
                    "id": CODEX_0162_CLIENT_MODULE_ID,
                    "version": CODEX_0162_CLIENT_MODULE_VERSION,
                    "fixture_sha256": "0" * 64,
                },
            }
        )
    assert wrong_digest.value.error_code == "client_module_fixture_mismatch"


def test_canonical_0162_fixture_is_pinned_and_honest() -> None:
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CODEX_0162_FIXTURE_SHA256
    fixture = json.loads(raw)
    assert fixture["schema_version"] == "codex_0162_additional_tools_profile_v1"
    contract = fixture["contract"]
    assert contract["client_version"] == CODEX_0162_CLI_VERSION
    assert fixture["source"]["commit"] == CODEX_0162_SOURCE_CONTRACT_COMMIT
    profile = fixture["synthetic_197_profile"]
    assert profile["totalChildTools"] == 197
    assert sum(profile["namespaceCounts"].values()) == 197
    assert profile["label"].endswith("NOT a capture of actually installed plugins.")
    capture = fixture["official_isolated_capture"]
    assert "mock" in str(capture["backend"]) or "fake" in str(capture["backend"])


# --- exact 197 counts through the real module + policy ---


def test_exact_197_declaration_normalizes_through_the_registered_module() -> None:
    module, result = _apply(_body(_item(_synthetic_197_namespaces(), id_value=AT_UUID)))
    _ = module
    canonical = _canonical_item(_module(), result)
    assert canonical["role"] == "developer"
    assert canonical["id"] == AT_UUID
    namespaces = canonical["tools"]
    assert [namespace["name"] for namespace in namespaces] == [
        "functions",
        "multi_agent_v1",
        *MCP_NAMESPACE_COUNTS,
    ]
    counts = {str(namespace["name"]): len(namespace["tools"]) for namespace in namespaces}
    assert counts["functions"] == 11
    assert counts["multi_agent_v1"] == 5
    for name, count in MCP_NAMESPACE_COUNTS.items():
        assert counts[name] == count
    assert sum(counts.values()) == 197
    for namespace in namespaces:
        assert namespace["type"] == "namespace"
        for tool in namespace["tools"]:
            assert tool["type"] == "function"
            assert "parameters" in tool
    # The remaining input item is preserved in order.
    assert result.effective_body["input"][1]["type"] == "message"


@pytest.mark.parametrize("id_value", ["omitted", None, AT_UUID], ids=["omitted", "null", "valid"])
def test_optional_id_states(id_value: object) -> None:
    marker = "omitted" if id_value == "omitted" else id_value
    _, result = _apply(_body(_item(_synthetic_197_namespaces(), id_value=marker)))
    canonical = _canonical_item(_module(), result)
    if id_value == AT_UUID:
        assert canonical["id"] == AT_UUID
    else:
        assert "id" not in canonical


@pytest.mark.parametrize(
    "bad_id",
    ["a" * 129, "at_中文", "https://id", "sk-1234567890", "abcdefgh.ijklmnop.qrstuvwx"],
    ids=["over-128", "non-ascii", "scheme", "secret-prefix", "jwt-shape"],
)
def test_invalid_ids_are_rejected_at_the_id_param(bad_id: str) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(_item(_synthetic_197_namespaces(), id_value=bad_id)))
    assert exc_info.value.error_code == "responses_codex_envelope_invalid"
    assert exc_info.value.param == "input[0].id"


# --- strict vocabulary / shape negatives ---


@pytest.mark.parametrize(
    "mutate",
    ["unknown_item_field", "unknown_namespace_field", "unknown_tool_field"],
)
def test_unknown_fields_are_rejected_at_the_precise_param(mutate: str) -> None:
    namespaces = _synthetic_197_namespaces()[:1]
    if mutate == "unknown_item_field":
        item = _item(namespaces)
        item["weight"] = 1
    elif mutate == "unknown_namespace_field":
        namespaces[0]["schema"] = {}
        item = _item(namespaces)
    else:
        namespaces[0]["tools"][0]["temperature"] = 0.2
        item = _item(namespaces)
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(item))
    if mutate == "unknown_item_field":
        assert exc_info.value.param == "input[0].weight"
        assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    elif mutate == "unknown_namespace_field":
        assert exc_info.value.param == "input[0].tools[0].schema"
        assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    else:
        assert exc_info.value.param.startswith("input[0].tools[0].tools[0]")
        assert exc_info.value.error_code == "responses_tool_invalid_shape"


def test_unknown_namespace_and_tool_names_are_rejected() -> None:
    for bad_namespace in (
        _namespace("web_tools", [_function_tool("some_tool")]),
        _namespace("mcp__other__demo", [_function_tool("some_tool")]),
        # Bounded built-in namespaces approve any pattern-valid function
        # name; a pattern violation is the reject class here.
        _namespace("functions", [_function_tool("Bad Name")]),
    ):
        with pytest.raises(RequestPolicyError) as exc_info:
            _apply(_body(_item([bad_namespace])))
        assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
        assert exc_info.value.param == "input[0].tools"


def test_non_function_tool_types_and_duplicates_are_rejected() -> None:
    custom_tool = _function_tool("exec", type="custom", format={"type": "grammar"})
    for namespaces in (
        [custom_tool and _namespace("functions", [custom_tool])],
        [_namespace("functions", [_function_tool("dup"), _function_tool("dup")])],
        [
            _namespace("functions", [_function_tool("a_tool")]),
            _namespace("functions", [_function_tool("b_tool")]),
        ],
        [_namespace("mcp__codex_apps__demo", [_function_tool("t", type="custom", format={"type": "grammar"})])],
    ):
        with pytest.raises(RequestPolicyError) as exc_info:
            _apply(_body(_item(namespaces)))
        assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
        assert exc_info.value.param == "input[0].tools"


def test_wrong_role_is_rejected() -> None:
    item = _item(_synthetic_197_namespaces()[:1])
    item["role"] = "user"
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(item))
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].role"


# --- missing grants fail closed before canonicalization ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"allow_codex_client_tools": False},
        {"allow_codex_request_envelope": False},
    ],
    ids=["no-client-tools-grant", "no-envelope-grant"],
)
def test_missing_declaration_grants_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(_item(_synthetic_197_namespaces()[:1])), **overrides)
    assert exc_info.value.error_code == "responses_codex_client_tools_not_allowed"
    assert exc_info.value.param == "input[0].type"


def test_streaming_declaration_without_streaming_grant_is_rejected() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(
            _body(_item(_synthetic_197_namespaces()[:1]), stream=True),
            allow_codex_streaming_tool_events=False,
        )
    assert exc_info.value.error_code == "responses_codex_streaming_tool_events_not_allowed"


# --- pair registration ---


def test_0162_pair_registration_is_local_only() -> None:
    ensure_client_server_pair(CODEX_0162_CLIENT_MODULE_ID, LOCAL_CODING_SERVER_MODULE_ID)
    ensure_client_module_has_server_pair(CODEX_0162_CLIENT_MODULE_ID)
    with pytest.raises(ProviderConfigurationError) as exc_info:
        ensure_client_server_pair(CODEX_0162_CLIENT_MODULE_ID, OPENAI_SERVER_MODULE_ID)
    assert exc_info.value.error_code == "incompatible_module_pair"
    # Earlier pairs remain registered and unchanged.
    assert (
        ClientServerPair("codex-0.149-responses-v1", LOCAL_CODING_SERVER_MODULE_ID)
        in CLIENT_SERVER_COMPATIBILITY
    )
    assert (
        ClientServerPair("codex-0.147-responses-v1", OPENAI_SERVER_MODULE_ID)
        in CLIENT_SERVER_COMPATIBILITY
    )


# --- 0.162 finite boundaries; shared/global limits intact ---


def test_spec_boundaries_are_version_owned_and_shared_limits_intact() -> None:
    assert CODEX_0162_POLICY_SPEC.max_client_tool_schema_properties == 4_096
    assert CODEX_0162_POLICY_SPEC.max_client_tool_total_description_bytes == 262_144
    assert CODEX_0162_MAX_NAMESPACES == 16
    assert CODEX_0162_MAX_TOTAL_TOOLS == 256
    assert CODEX_0162_MAX_NAMESPACE_TOOLS == 256
    assert CODEX_0162_BUILTIN_NAMESPACES == frozenset({"functions", "multi_agent_v1"})
    # Shared ceilings were not widened for the new profile.
    assert CODEX_0162_POLICY_SPEC.max_client_tool_schema_depth == (
        CODEX_0149_POLICY_SPEC.max_client_tool_schema_depth
    ) == 16
    assert CODEX_0162_POLICY_SPEC.max_client_tool_declaration_bytes == (
        CODEX_0149_POLICY_SPEC.max_client_tool_declaration_bytes
    ) == 589_824
    assert CODEX_0162_POLICY_SPEC.max_client_tool_description_bytes == (
        CODEX_0149_POLICY_SPEC.max_client_tool_description_bytes
    ) == 20_000
    # The historical 0.149 profile keeps its own smaller profile ceilings.
    assert CODEX_0149_POLICY_SPEC.max_client_tool_schema_properties == 256
    assert CODEX_0149_POLICY_SPEC.max_client_tool_total_description_bytes == 32_768


def test_total_tool_boundaries_256_pass_257_fail() -> None:
    namespaces_256 = [
        _namespace("functions", [_function_tool(f"f_tool_{index:03d}") for index in range(255)]),
        _namespace("multi_agent_v1", [_function_tool("agent_tool_000")]),
    ]
    _apply(_body(_item(namespaces_256)))
    namespaces_257 = [
        _namespace("functions", [_function_tool(f"f_tool_{index:03d}") for index in range(255)]),
        _namespace(
            "multi_agent_v1",
            [_function_tool(f"agent_tool_{index:03d}") for index in range(2)],
        ),
    ]
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(_item(namespaces_257)))
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].tools"


def test_namespace_boundaries_16_pass_17_fail() -> None:
    def _namespaces(count: int) -> list[dict[str, object]]:
        return [
            _namespace(f"mcp__codex_apps__ns{index:02d}", [_function_tool("t_tool_000")])
            for index in range(count)
        ]

    _apply(_body(_item(_namespaces(CODEX_0162_MAX_NAMESPACES))))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(_item(_namespaces(CODEX_0162_MAX_NAMESPACES + 1))))
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].tools"


def test_per_namespace_tool_boundary_256_pass_257_fail() -> None:
    _apply(
        _body(
            _item(
                [
                    _namespace(
                        "functions",
                        [_function_tool(f"b_tool_{index:03d}") for index in range(256)],
                    )
                ]
            )
        )
    )
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(
            _body(
                _item(
                    [
                        _namespace(
                            "functions",
                            [_function_tool(f"b_tool_{index:03d}") for index in range(257)],
                        )
                    ]
                )
            )
        )
    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].tools"


def test_per_tool_description_ceiling_20k_pass_20k1_fail() -> None:
    passing = _item(
        [_namespace("functions", [_function_tool("t", description="d" * 20_000)])]
    )
    _apply(_body(passing))
    failing = _item(
        [_namespace("functions", [_function_tool("t", description="d" * 20_001)])]
    )
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(failing))
    assert exc_info.value.error_code == "responses_tool_invalid_shape"
    assert exc_info.value.param == "input[0].tools[0].tools[0].description"


def test_total_description_ceiling_262k_162_profile() -> None:
    # 13 tools x 20_000 = 260_000 stays under the 0.162 262_144 ceiling;
    # 14 tools x 20_000 = 280_000 exceeds it.  Under the historical 0.149
    # 32_768 ceiling both would already fail, which stays true via the
    # pinned 0.149 spec above.  The hard input maximum is raised so the
    # profile ceiling under test - not the global estimation gate - decides.
    _apply(
        _body(
            _item(
                [
                    _namespace(
                        "functions",
                        [_function_tool(f"d_tool_{index:02d}", description="d" * 20_000)
                         for index in range(13)],
                    )
                ]
            )
        ),
        hard_max_input_tokens=200_000,
    )
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(
            _body(
                _item(
                    [
                        _namespace(
                            "functions",
                            [_function_tool(f"d_tool_{index:02d}", description="d" * 20_000)
                             for index in range(14)],
                        )
                    ]
                )
            ),
            hard_max_input_tokens=200_000,
        )
    assert exc_info.value.error_code == "responses_codex_client_tools_too_large"
    assert exc_info.value.param == "input[0].tools"


def test_schema_property_ceiling_4096_pass_4097_fail() -> None:
    # The aggregate property ceiling spans tools; each single-tool schema
    # stays under the shared 65_536-byte schema gate.
    def _schema_tool(count: int, name: str) -> dict[str, object]:
        return _function_tool(
            name,
            parameters={
                "type": "object",
                "properties": {f"p{index:05d}": {"type": "string"} for index in range(count)},
                "additionalProperties": False,
            },
        )

    _apply(
        _body(
            _item(
                [
                    _namespace(
                        "functions",
                        [_schema_tool(2_048, "p_tool_000"), _schema_tool(2_048, "p_tool_001")],
                    )
                ]
            )
        ),
        hard_max_input_tokens=200_000,
    )
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(
            _body(
                _item(
                    [
                        _namespace(
                            "functions",
                            [_schema_tool(2_048, "p_tool_000"), _schema_tool(2_049, "p_tool_001")],
                        )
                    ]
                )
            ),
            hard_max_input_tokens=200_000,
        )
    assert exc_info.value.error_code == "responses_codex_client_tools_property_count_exceeded"


def test_schema_depth_ceiling_16_shared() -> None:
    # The walk starts at the parameters object (depth 0); each wrapper
    # object advances two node levels, so 7 wrappers reach exactly depth 16
    # and 8 wrappers cross it.
    def _deep_tool(wrappers: int) -> dict[str, object]:
        node: dict[str, object] = {"type": "string"}
        for _index in range(wrappers):
            node = {"type": "object", "properties": {"nested": node}}
        return _function_tool("t", parameters=node)

    _apply(_body(_item([_namespace("functions", [_deep_tool(7)])])))
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(_item([_namespace("functions", [_deep_tool(8)])])))
    assert exc_info.value.error_code == "responses_codex_client_tools_schema_too_deep"
