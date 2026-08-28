from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from slaif_gateway.modules.clients.codex_0147 import (
    CODEX_0147_CLIENT_MODULE_ID,
    CODEX_0147_FIXTURE_SHA256,
)
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_CLIENT_MODULE_ID,
    CODEX_0149_ADAPTER_MANAGED_CANDIDATE_TYPES,
    CODEX_0149_ADAPTER_MANAGED_CANDIDATE_SHAPES,
    CODEX_0149_CLIENT_MODULE_VERSION,
    CODEX_0149_FIXTURE_SHA256,
    CODEX_0149_POLICY_SPEC,
)
from slaif_gateway.modules.clients.registry import (
    CODEX_0147_CLIENT_MODULE,
    CODEX_0149_CLIENT_MODULE,
    DEFAULT_CLIENT_MODULE,
    resolve_responses_client_module,
)
from slaif_gateway.modules.contracts import ModuleSelectionError
from slaif_gateway.modules.servers.registry import (
    SERVER_MODULE_REGISTRY,
    ensure_client_module_has_server_pair,
    ensure_client_server_pair,
)
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.services.responses_request_policy import _HOSTED_TOOL_TYPES

FIXTURE = Path("tests/fixtures/codex/0.149.0/responses-structural-v2.json")
HISTORICAL_FIXTURE = Path("tests/fixtures/codex/0.149.0/responses-structural.json")


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "synthetic-capture-model",
        "input": [{"type": "message", "role": "user", "content": "synthetic"}],
        "tools": [
            {"type": "function", "name": "safe", "parameters": {}, "strict": True},
            {
                "type": "tool_search",
                "description": "synthetic adapter-managed candidate",
                "execution": "client",
                "parameters": {},
            },
            {
                "type": "web_search",
                "external_web_access": False,
                "search_content_types": ["text", "image"],
            },
        ],
        "tool_choice": "auto",
    }
    body.update(overrides)
    return body


def test_0149_fixture_is_canonical_structural_only() -> None:
    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)
    canonical = (json.dumps(fixture, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()

    assert raw == canonical
    assert hashlib.sha256(raw).hexdigest() == CODEX_0149_FIXTURE_SHA256
    assert fixture["identity"]["cli_version"] == "0.149.0"
    assert fixture["capture"]["subprocess"]["model_call"] == "not_performed"
    assert fixture["gateway_compatibility"]["compatible_server_pairs"] == [
        "codex-0.149-responses-v1->local-coding-v1"
    ]
    historical = HISTORICAL_FIXTURE.read_bytes()
    assert hashlib.sha256(historical).hexdigest() == (
        "0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d"
    )
    observed_types = {
        shape["type"]
        for variant in fixture["capture"]["variants"]
        for shape in variant.get("request", {}).get("tool_declarations", {}).get("shapes", [])
    }
    observed_candidates = {tool_type for tool_type in observed_types if tool_type in {"web_search", "tool_search"}}
    assert observed_candidates == set(CODEX_0149_ADAPTER_MANAGED_CANDIDATE_TYPES)
    assert set(fixture["findings"]["adapter_managed_candidate_types"]) == observed_candidates
    observed_shapes = {
        shape["type"]: frozenset(shape["field_names"])
        for variant in fixture["capture"]["variants"]
        for shape in variant.get("request", {}).get("tool_declarations", {}).get("shapes", [])
        if shape["type"] in observed_candidates
    }
    assert observed_shapes == CODEX_0149_ADAPTER_MANAGED_CANDIDATE_SHAPES
    for forbidden in (
        "/home/",
        "session.jsonl",
        "authorization",
        "Bearer ",
        "SLAIF_CAPTURE_PROMPT",
    ):
        assert forbidden not in raw.decode("utf-8")


def test_0147_module_keeps_exact_qualified_identity() -> None:
    request = CODEX_0147_CLIENT_MODULE.normalize_responses(_body())

    assert request.module_id == CODEX_0147_CLIENT_MODULE_ID
    assert request.profile_facts["fixture_sha256"] == CODEX_0147_FIXTURE_SHA256
    assert request.stream_profile == CODEX_0147_CLIENT_MODULE_ID


def test_0149_classifies_search_candidates_without_hosted_authority() -> None:
    body = _body()
    request = CODEX_0149_CLIENT_MODULE.normalize_responses(body)

    assert request.body == body
    assert request.adapter_managed_declaration_candidates == ("tool_search", "web_search")
    assert request.capability_intents == ("adapter_managed_codex_search",)
    assert request.profile_facts == {
        "client_module_id": CODEX_0149_CLIENT_MODULE_ID,
        "client_module_version": CODEX_0149_CLIENT_MODULE_VERSION,
        "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
    }
    assert CODEX_0149_CLIENT_MODULE.policy_spec is CODEX_0149_POLICY_SPEC


@pytest.mark.parametrize(
    "tool_type",
    sorted(_HOSTED_TOOL_TYPES - {"web_search", "namespace", "tool_search"}),
)
def test_0149_rejects_hosted_authority_shapes(tool_type: str) -> None:
    with pytest.raises(ModuleSelectionError, match="authority|unknown") as exc_info:
        CODEX_0149_CLIENT_MODULE.normalize_responses(
            _body(tools=[{"type": tool_type}])
        )
    assert exc_info.value.error_code == (
        "codex_0149_authority_shape"
    )


@pytest.mark.parametrize(
    ("tool_choice", "code"),
    [
        ("web_search", "codex_0149_authority_shape"),
        ("tool_search", "codex_0149_authority_shape"),
        ({"type": "web_search"}, "codex_0149_authority_shape"),
        ({"type": "tool_search"}, "codex_0149_authority_shape"),
    ],
)
def test_0149_rejects_explicit_search_choices(tool_choice: object, code: str) -> None:
    with pytest.raises(ModuleSelectionError) as exc_info:
        CODEX_0149_CLIENT_MODULE.normalize_responses(
            _body(tool_choice=tool_choice)
        )
    assert exc_info.value.error_code == code


def test_0149_required_search_choice_rejects_before_gateway_policy() -> None:
    with pytest.raises(ModuleSelectionError) as exc_info:
        CODEX_0149_CLIENT_MODULE.normalize_responses(
            _body(
                tools=[
                    {
                        "type": "tool_search",
                        "description": "candidate",
                        "execution": "client",
                        "parameters": {},
                    },
                    {
                        "type": "web_search",
                        "external_web_access": False,
                        "search_content_types": ["text"],
                    },
                ],
                tool_choice="required",
            )
        )
    assert exc_info.value.error_code == "codex_0149_authority_shape"


def test_0149_required_choice_survives_with_a_local_tool() -> None:
    request = CODEX_0149_CLIENT_MODULE.normalize_responses(
        _body(tool_choice="required")
    )
    assert request.adapter_managed_declaration_candidates == ("tool_search", "web_search")


def test_0149_rejects_unknown_and_provider_authority_fields() -> None:
    with pytest.raises(ModuleSelectionError):
        CODEX_0149_CLIENT_MODULE.normalize_responses(_body(unexpected=True))
    with pytest.raises(ModuleSelectionError) as exc_info:
        CODEX_0149_CLIENT_MODULE.normalize_responses(
            _body(tools=[{"type": "function", "name": "safe", "headers": {}}])
        )
    assert exc_info.value.error_code == "codex_0149_authority_shape"


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "type": "tool_search",
            "description": "https://authority.invalid",
            "execution": "client",
            "parameters": {},
        },
        {
            "type": "tool_search",
            "description": "safe",
            "execution": "client",
            "parameters": {"nested": {"type": "web_search"}},
        },
    ],
)
def test_0149_rejects_candidate_urls_and_nested_search_types(
    candidate: dict[str, object],
) -> None:
    with pytest.raises(ModuleSelectionError) as exc_info:
        CODEX_0149_CLIENT_MODULE.normalize_responses(_body(tools=[candidate]))
    assert exc_info.value.error_code == "codex_0149_authority_shape"


def test_registry_uses_only_server_side_metadata_and_legacy_0147_path() -> None:
    assert resolve_responses_client_module(None) is DEFAULT_CLIENT_MODULE
    legacy = {
        "version": 1,
        "allowed_capabilities": [
            "codex_request_envelope",
            "codex_client_tools",
            "codex_streaming_tool_events",
            "codex_encrypted_reasoning_replay",
            "codex_compaction",
        ],
        "allowed_local_tool_types": ["function", "custom"],
    }
    assert resolve_responses_client_module(legacy) is CODEX_0147_CLIENT_MODULE
    assert resolve_responses_client_module(
        {
            "client_module": {
                "id": CODEX_0149_CLIENT_MODULE_ID,
                "version": CODEX_0149_CLIENT_MODULE_VERSION,
                "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
            }
        }
    ) is CODEX_0149_CLIENT_MODULE

    with pytest.raises(ModuleSelectionError, match="does not match"):
        resolve_responses_client_module(
            {
                "client_module": {
                    "id": CODEX_0149_CLIENT_MODULE_ID,
                    "version": "1",
                    "fixture_sha256": "0" * 64,
                }
            }
        )


def test_0149_has_only_the_local_coding_server_pair() -> None:
    ensure_client_server_pair(CODEX_0147_CLIENT_MODULE_ID, "openai")
    ensure_client_module_has_server_pair(CODEX_0149_CLIENT_MODULE_ID)
    ensure_client_server_pair(CODEX_0149_CLIENT_MODULE_ID, "local-coding-v1")
    for server_module_id in SERVER_MODULE_REGISTRY:
        if server_module_id == "local-coding-v1":
            continue
        with pytest.raises(ProviderConfigurationError, match="incompatible"):
            ensure_client_server_pair(CODEX_0149_CLIENT_MODULE_ID, server_module_id)
    with pytest.raises(ProviderConfigurationError, match="incompatible"):
        ensure_client_server_pair(CODEX_0147_CLIENT_MODULE_ID, "local-coding-v1")


def test_codex_client_modules_have_no_gateway_authority_imports() -> None:
    client_root = Path("app/slaif_gateway/modules/clients")
    forbidden = (
        "slaif_gateway.db",
        "slaif_gateway.cache",
        "slaif_gateway.providers",
        "slaif_gateway.services",
        "sqlalchemy",
        "redis",
        "httpx",
    )
    for path in client_root.glob("codex_*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(value in source for value in forbidden), path

    for path in (
        Path("app/slaif_gateway/services/accounting.py"),
        Path("app/slaif_gateway/services/responses_external_tool_runtime.py"),
        Path("app/slaif_gateway/providers/streaming.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "codex-0.149-responses-v1" not in source
        assert "adapter_managed_codex_search" not in source


def test_generic_responses_primitives_are_neutral_and_policy_receives_a_spec() -> None:
    policy_source = Path(
        "app/slaif_gateway/services/responses_request_policy.py"
    ).read_text(encoding="utf-8")
    codex_support_source = Path(
        "app/slaif_gateway/modules/clients/codex_support.py"
    ).read_text(encoding="utf-8")
    responses_support_source = Path(
        "app/slaif_gateway/modules/clients/responses_support.py"
    ).read_text(encoding="utf-8")

    assert "codex_support" not in policy_source
    assert "_SUPPORTED_CODEX" not in policy_source
    assert "codex_0_148" not in policy_source
    assert "_HOSTED_TOOL_TYPES" in responses_support_source
    assert "_SUPPORTED_FUNCTION_TOOL_FIELDS" in responses_support_source
    assert "_HOSTED_TOOL_TYPES" not in codex_support_source
    assert "_SUPPORTED_FUNCTION_TOOL_FIELDS" not in codex_support_source
    assert "client_spec: ResponsesClientPolicySpec | None" in policy_source


def test_responses_handler_denies_0149_before_policy_or_provider_work(monkeypatch) -> None:
    from slaif_gateway.services import responses_gateway

    payload = SimpleNamespace(
        model_dump=lambda **_: _body(),
        model_fields_set=set(),
    )
    key = SimpleNamespace(
        responses_policy={
            "client_module": {
                "id": CODEX_0149_CLIENT_MODULE_ID,
                "version": "1",
                "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
            }
        }
    )
    monkeypatch.setattr(
        responses_gateway.ResponsesRequestPolicy,
        "apply",
        lambda *_args, **_kwargs: pytest.fail("policy must not run before pair denial"),
    )

    with pytest.raises(responses_gateway.OpenAICompatibleError) as exc_info:
        asyncio.run(
            responses_gateway.handle_response_create(
                payload=payload,
                authenticated_key=key,
                settings=SimpleNamespace(),
            )
        )
    assert exc_info.value.code == "client_module_fixture_mismatch"


def test_0149_required_search_choice_denies_before_policy_or_provider_work(monkeypatch) -> None:
    from slaif_gateway.services import responses_gateway

    payload = SimpleNamespace(
        model_dump=lambda **_: _body(
            tools=[
                {
                    "type": "tool_search",
                    "description": "candidate",
                    "execution": "client",
                    "parameters": {},
                },
                {
                    "type": "web_search",
                    "external_web_access": False,
                    "search_content_types": ["text"],
                },
            ],
            tool_choice="required",
        ),
        model_fields_set=set(),
    )
    key = SimpleNamespace(
        responses_policy={
            "client_module": {
                "id": CODEX_0149_CLIENT_MODULE_ID,
                "version": CODEX_0149_CLIENT_MODULE_VERSION,
                "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
            }
        }
    )
    monkeypatch.setattr(
        responses_gateway.ResponsesRequestPolicy,
        "apply",
        lambda *_args, **_kwargs: pytest.fail("policy must not run after choice rejection"),
    )

    with pytest.raises(responses_gateway.OpenAICompatibleError) as exc_info:
        asyncio.run(
            responses_gateway.handle_response_create(
                payload=payload,
                authenticated_key=key,
                settings=SimpleNamespace(),
            )
        )
    assert exc_info.value.code == "codex_0149_authority_shape"
