"""Real 197-tool Codex names/types regression for the 0.162 data profile.

The fixture ``connector-tool-names-197-v1.json`` is the complete
human-supplied names/types-only diagnostic summary (11 namespaces, 197
tools, all ``function`` type, 181 single-leading-underscore connector
names, longest name 42).  It is SUPPLEMENTAL regression evidence only: it
is never a runtime allowlist, selected policy identity, or tool inventory.
The tool schemas/descriptions wrapped around the real names in these tests
are SYNTHETIC.  The fixture and its provenance sidecar must remain
byte-for-byte immutable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
    CODEX_0162_CLIENT_MODULE_VERSION,
    CODEX_0162_FIXTURE_SHA256,
)
from slaif_gateway.modules.clients.registry import (
    CLIENT_MODULE_REGISTRY,
    resolve_responses_client_module,
)
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy

FIXTURE = Path("tests/fixtures/codex/0.162.1/connector-tool-names-197-v1.json")
PROVENANCE = Path("tests/fixtures/codex/0.162.1/connector-tool-names-197-v1.provenance.json")
EXPECTED_FIXTURE_SHA256 = "a32bbf25de4e0be15690feaf3a86a4f453aac2d281b9b67d2cd21daa1bd1c8c4"
EXPECTED_COUNTS = [11, 5, 40, 3, 89, 1, 11, 6, 5, 1, 25]

_settings = Settings(
    DEFAULT_MAX_OUTPUT_TOKENS=12,
    HARD_MAX_OUTPUT_TOKENS=80,
    HARD_MAX_INPUT_TOKENS=200_000,
)
_APPLY_KW = dict(
    allow_store=True,
    allow_codex_request_envelope=True,
    allow_codex_client_tools=True,
    allow_codex_streaming_tool_events=True,
)


def _fixture_document() -> dict:
    document = json.loads(FIXTURE.read_text())
    assert document["namespace_count"] == len(document["namespaces"])
    return document


def _synthetic_function_tool(name: str) -> dict:
    # SYNTHETIC schema/description wrapper; only the name is real data.
    return {
        "type": "function",
        "name": name,
        "description": f"synthetic description for {name}",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _registered_module():
    policy = {
        "version": 1,
        "client_module": {
            "id": CODEX_0162_CLIENT_MODULE_ID,
            "version": CODEX_0162_CLIENT_MODULE_VERSION,
            "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
        },
    }
    module = resolve_responses_client_module(policy)
    assert module is CLIENT_MODULE_REGISTRY[CODEX_0162_CLIENT_MODULE_ID]
    return module


def _real_namespaces() -> list[dict]:
    document = _fixture_document()
    return [
        {
            "type": "namespace",
            "name": namespace["name"],
            "tools": [_synthetic_function_tool(tool["name"]) for tool in namespace["tools"]],
        }
        for namespace in document["namespaces"]
    ]


def _body(namespaces: list[dict]) -> dict:
    return {
        "model": "codex-0162-real-names-model",
        "input": [
            {
                "type": "additional_tools",
                "role": "developer",
                "tools": namespaces,
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "bounded 0162 real-names request"}],
            },
        ],
    }


# --- fixture integrity and provenance ---


def test_real_197_fixture_is_byte_immutable_with_provenance() -> None:
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_FIXTURE_SHA256
    provenance = json.loads(PROVENANCE.read_text())
    assert provenance["sha256"] == EXPECTED_FIXTURE_SHA256
    assert provenance["counts"] == EXPECTED_COUNTS
    assert provenance["leadingUnderscoreConnectorTools"] == 181
    assert provenance["maxToolNameLength"] == 42
    assert "actual" in provenance["evidenceClass"]


def test_real_197_fixture_shape_counts_types_and_order() -> None:
    document = _fixture_document()
    assert document["input_index"] == 0
    assert document["namespace_count"] == 11
    assert document["total_tool_count"] == 197
    counts = [namespace["tool_count"] for namespace in document["namespaces"]]
    assert counts == EXPECTED_COUNTS
    assert sum(counts) == 197
    for namespace in document["namespaces"]:
        assert namespace["type"] == "namespace"
        assert namespace["tools_container_type"] == "list"
        assert len(namespace["tools"]) == namespace["tool_count"]
        for tool in namespace["tools"]:
            assert set(tool) == {"name", "type"}
            assert tool["type"] == "function"
    # 181 connector names, every one with exactly one leading underscore.
    connector_names = [
        tool["name"]
        for namespace in document["namespaces"]
        if namespace["name"].startswith("mcp__codex_apps__")
        for tool in namespace["tools"]
    ]
    assert len(connector_names) == 181
    assert all(name.startswith("_") and not name.startswith("__") for name in connector_names)
    assert (
        max(
            len(tool["name"]) for namespace in document["namespaces"] for tool in namespace["tools"]
        )
        == 42
    )


# --- full registered module + shared policy accepts all 197 ---


def test_full_registered_module_accepts_all_real_197_names() -> None:
    module = _registered_module()
    normalized = module.normalize_responses(_body(_real_namespaces()))
    assert normalized.module_version == CODEX_0162_CLIENT_MODULE_VERSION
    result = ResponsesRequestPolicy(_settings, client_spec=module.policy_spec).apply(
        normalized.body, **_APPLY_KW
    )
    item = result.effective_body["input"][0]
    assert item["type"] == "additional_tools"
    document = _fixture_document()
    # Canonical/provider names are preserved exactly, in declared order.
    assert [namespace["name"] for namespace in item["tools"]] == [
        namespace["name"] for namespace in document["namespaces"]
    ]
    for namespace in item["tools"]:
        for tool in namespace["tools"]:
            assert tool["type"] == "function"
    canonical_names = [tool["name"] for namespace in item["tools"] for tool in namespace["tools"]]
    fixture_names = [
        tool["name"] for namespace in document["namespaces"] for tool in namespace["tools"]
    ]
    assert canonical_names == fixture_names
    assert len(canonical_names) == 197


def test_real_names_lowered_provider_declaration_preserves_names() -> None:
    from slaif_gateway.modules.clients.codex_0162 import (
        codex_0162_lower_initial_additional_tools,
    )

    module = _registered_module()
    normalized = module.normalize_responses(_body(_real_namespaces()))
    lowered = codex_0162_lower_initial_additional_tools(normalized.body)
    tools = lowered["tools"]
    assert [namespace["name"] for namespace in tools] == [
        namespace["name"] for namespace in _fixture_document()["namespaces"]
    ]
    flattened = [tool["name"] for namespace in tools for tool in namespace["tools"]]
    fixture_names = [
        tool["name"]
        for namespace in _fixture_document()["namespaces"]
        for tool in namespace["tools"]
    ]
    assert flattened == fixture_names
    assert len(normalized.body["input"]) == 2
    assert lowered["input"][0]["type"] == "message"


# --- negatives remain denied around the real-name evidence ---


def test_builtin_real_namespace_rejects_leading_underscore() -> None:
    module = _registered_module()
    namespaces = _real_namespaces()
    namespaces[0]["tools"][0] = _synthetic_function_tool("_exec_command")
    normalized = module.normalize_responses(_body(namespaces))
    with pytest.raises(Exception):
        ResponsesRequestPolicy(_settings, client_spec=module.policy_spec).apply(
            normalized.body, **_APPLY_KW
        )


def test_duplicate_real_name_in_one_namespace_is_rejected() -> None:
    module = _registered_module()
    namespaces = _real_namespaces()
    first_name = namespaces[0]["tools"][0]["name"]
    namespaces[0]["tools"].append(_synthetic_function_tool(first_name))
    normalized = module.normalize_responses(_body(namespaces))
    with pytest.raises(Exception):
        ResponsesRequestPolicy(_settings, client_spec=module.policy_spec).apply(
            normalized.body, **_APPLY_KW
        )


def test_unknown_authority_fields_still_rejected() -> None:
    module = _registered_module()
    namespaces = _real_namespaces()
    namespaces[0]["tools"][0]["hosted"] = True
    normalized = module.normalize_responses(_body(namespaces))
    with pytest.raises(Exception):
        ResponsesRequestPolicy(_settings, client_spec=module.policy_spec).apply(
            normalized.body, **_APPLY_KW
        )


def test_missing_local_tool_grant_denies_real_197_declaration() -> None:
    module = _registered_module()
    normalized = module.normalize_responses(_body(_real_namespaces()))
    with pytest.raises(Exception):
        ResponsesRequestPolicy(_settings, client_spec=module.policy_spec).apply(
            normalized.body,
            allow_store=True,
            allow_codex_request_envelope=True,
            allow_codex_client_tools=False,
            allow_codex_streaming_tool_events=True,
        )
