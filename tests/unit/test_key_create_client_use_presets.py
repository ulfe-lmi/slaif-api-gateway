"""Unit evidence for 229-a client-use key-creation presets.

Covers the active-module facts helper, the client-use conflict rules, the
Chat preset pin, the OpenCode Responses gate predicate, the one-time result
pin surface, and the Codex policy fix: the frozen qualification profile
records the DATA revision a route was qualified against, while the new key
pin is built from the ACTIVE installed snapshot (stable module ID check
only). No database, no provider traffic.
"""

from __future__ import annotations

import asyncio

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from slaif_gateway.api import admin as admin_api
from slaif_gateway.modules.clients.agent_chat import AgentChatModuleSelectionError
from slaif_gateway.modules.clients.hermes_0225_chat import (
    HERMES_0225_CHAT_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.opencode_1193_chat import (
    OPENCODE_1193_CHAT_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.registry import (
    ActiveClientModuleFacts,
    active_client_module_facts,
)
from slaif_gateway.modules.contracts import ModuleSelectionError
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_CODEX_PROFILE_ID,
    get_codex_profile,
)


def _key_input(**overrides) -> CreateGatewayKeyInput:
    now = datetime.now(UTC)
    values = dict(
        owner_id=uuid.uuid4(),
        valid_from=now,
        valid_until=now.replace(hour=12),
        allowed_models=["gpt-test"],
        allowed_endpoints=["/v1/chat/completions"],
        allowed_providers=["syn-provider"],
    )
    values.update(overrides)
    return CreateGatewayKeyInput(**values)  # type: ignore[arg-type]


# --- active_client_module_facts -------------------------------------------


def test_active_client_module_facts_codex_default_snapshot() -> None:
    facts = active_client_module_facts("codex-0.162-responses-v1")
    assert facts.module_id == "codex-0.162-responses-v1"
    assert facts.module_version == "8"
    assert facts.fixture_sha256 == (
        "1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11"
    )
    assert facts.cli_version == "0.162.1"
    assert facts.pin == {
        "id": "codex-0.162-responses-v1",
        "version": "8",
        "fixture_sha256": facts.fixture_sha256,
    }


def test_active_client_module_facts_opencode_responses() -> None:
    facts = active_client_module_facts(OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID)
    assert facts.module_id == OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID
    assert facts.module_version == "1"
    assert facts.fixture_sha256.startswith("592c5d1b")
    assert set(facts.pin) == {"id", "version", "fixture_sha256"}


@pytest.mark.parametrize(
    ("module_id", "expected_version"),
    [
        (OPENCODE_1193_CHAT_CLIENT_MODULE_ID, "1"),
        (HERMES_0225_CHAT_CLIENT_MODULE_ID, "2"),
    ],
)
def test_active_client_module_facts_chat_fallback(
    module_id: str, expected_version: str
) -> None:
    facts = active_client_module_facts(module_id)
    assert facts.module_id == module_id
    assert facts.module_version == expected_version
    assert facts.pin["fixture_sha256"] == facts.fixture_sha256


@pytest.mark.parametrize("bad_id", ["nope", "codex-0.162-responses-v2", 123])
def test_active_client_module_facts_unknown_module_fails_closed(bad_id: object) -> None:
    with pytest.raises(ModuleSelectionError):
        active_client_module_facts(bad_id)  # type: ignore[arg-type]


def test_active_client_module_facts_chat_unknown_is_chat_error() -> None:
    with pytest.raises(AgentChatModuleSelectionError):
        active_client_module_facts("hermes-9.9.9-chat-v9")


# --- client-use conflict rules --------------------------------------------


def _selection(**overrides) -> None:
    kwargs = dict(
        client_use_selected=True,
        use_codex=False,
        use_opencode_chat=False,
        use_opencode_responses=False,
        use_hermes=False,
        advanced_codex_selected=False,
        document_mode=False,
        trusted_calibration_selected=False,
    )
    kwargs.update(overrides)
    admin_api._validate_admin_client_use_selection(**kwargs)


def test_client_use_allows_each_single_choice() -> None:
    _selection(use_codex=True)
    _selection(use_opencode_chat=True)
    _selection(use_opencode_responses=True)
    _selection(use_hermes=True)


def test_client_use_allows_chat_plus_responses_pair() -> None:
    _selection(use_opencode_chat=True, use_opencode_responses=True)
    _selection(use_hermes=True, use_opencode_responses=True)
    _selection(use_codex=True, use_opencode_chat=True)
    _selection(use_codex=True, use_hermes=True)


def test_client_use_nothing_selected_is_allowed() -> None:
    admin_api._validate_admin_client_use_selection(
        client_use_selected=False,
        use_codex=False,
        use_opencode_chat=False,
        use_opencode_responses=False,
        use_hermes=False,
        advanced_codex_selected=True,
        document_mode=False,
        trusted_calibration_selected=True,
    )


def test_client_use_conflicts_chat_family() -> None:
    with pytest.raises(ValueError, match="single Chat client binding"):
        _selection(use_opencode_chat=True, use_hermes=True)


def test_client_use_conflicts_responses_family() -> None:
    with pytest.raises(ValueError, match="single Responses client binding"):
        _selection(use_codex=True, use_opencode_responses=True)


def test_client_use_conflicts_document_mode() -> None:
    with pytest.raises(ValueError, match="guided-mode only"):
        _selection(use_codex=True, document_mode=True)


def test_client_use_conflicts_trusted_calibration() -> None:
    with pytest.raises(ValueError, match="Trusted calibration"):
        _selection(use_hermes=True, trusted_calibration_selected=True)


def test_client_use_conflicts_advanced_codex() -> None:
    with pytest.raises(ValueError, match="advanced Codex sections"):
        _selection(use_codex=True, advanced_codex_selected=True)


# --- Chat preset ------------------------------------------------------------


def test_chat_preset_requires_chat_endpoint() -> None:
    key_input = _key_input(allowed_endpoints=["/v1/responses"])
    with pytest.raises(ValueError, match="/v1/chat/completions"):
        admin_api._apply_admin_chat_client_preset(
            key_input,
            module_id=OPENCODE_1193_CHAT_CLIENT_MODULE_ID,
            client_label="OpenCode Chat",
        )


def test_chat_preset_pins_active_module_and_keeps_fields() -> None:
    key_input = _key_input()
    preset = admin_api._apply_admin_chat_client_preset(
        key_input,
        module_id=HERMES_0225_CHAT_CLIENT_MODULE_ID,
        client_label="Hermes",
    )
    active = active_client_module_facts(HERMES_0225_CHAT_CLIENT_MODULE_ID)
    assert preset.chat_client_module == active.pin
    assert preset.allowed_models == key_input.allowed_models
    assert preset.allowed_endpoints == key_input.allowed_endpoints
    assert preset.responses_policy is None


def test_chat_preset_allow_all_endpoints_satisfies_endpoint_rule() -> None:
    key_input = _key_input(allow_all_endpoints=True, allowed_endpoints=[])
    preset = admin_api._apply_admin_chat_client_preset(
        key_input,
        module_id=OPENCODE_1193_CHAT_CLIENT_MODULE_ID,
        client_label="OpenCode Chat",
    )
    assert preset.chat_client_module is not None


# --- OpenCode Responses gate predicate --------------------------------------


def _route(responses: object | None = None, capabilities: object | None = None) -> object:
    if capabilities is None:
        capabilities = {"responses": responses}
    return SimpleNamespace(capabilities=capabilities)


def test_route_supports_opencode_responses_gates_all_true() -> None:
    route = _route(
        {
            "text": True,
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": True,
        }
    )
    assert admin_api._route_supports_opencode_responses_gates(route) is True


@pytest.mark.parametrize("gate", admin_api.OPENCODE_RESPONSES_PRESET_GATES)
def test_route_supports_opencode_responses_gates_one_false(gate: str) -> None:
    gates = {
        "codex_request_envelope": True,
        "codex_client_tools": True,
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": True,
    }
    gates[gate] = False
    assert admin_api._route_supports_opencode_responses_gates(_route(gates)) is False


def test_route_supports_opencode_responses_gates_truthy_not_true_rejected() -> None:
    gates = {
        "codex_request_envelope": 1,
        "codex_client_tools": True,
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": True,
    }
    assert admin_api._route_supports_opencode_responses_gates(_route(gates)) is False


@pytest.mark.parametrize(
    "route",
    [
        _route(capabilities=None),
        _route(capabilities={}),
        _route(responses=None),
        _route(responses="yes"),
        _route(),
    ],
)
def test_route_supports_opencode_responses_gates_missing_shape(route: object) -> None:
    assert admin_api._route_supports_opencode_responses_gates(route) is False


# --- one-time result pin surface --------------------------------------------


def _valid_pin() -> dict[str, str]:
    return {
        "id": "opencode-1.19.3-responses-v1",
        "version": "1",
        "fixture_sha256": "f" * 64,
    }


def test_safe_client_module_pins_returns_complete_pins_only() -> None:
    pins = admin_api._safe_client_module_pins(
        {"version": 1, "client_module": _valid_pin()},
        _valid_pin(),
    )
    assert pins == {"responses": _valid_pin(), "chat": _valid_pin()}


def test_safe_client_module_pins_ignores_malformed_pins() -> None:
    extra_key = dict(_valid_pin())
    extra_key["note"] = "nope"
    empty_version = dict(_valid_pin(), version="")
    pins = admin_api._safe_client_module_pins(
        {"client_module": extra_key},
        empty_version,
    )
    assert pins == {}
    assert admin_api._safe_client_module_pins(None, "not-a-pin") == {}


# --- policy summary recognition ---------------------------------------------


def test_codex_policy_summary_accepts_active_opencode_pin() -> None:
    active = active_client_module_facts(OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID)
    policy = {
        "version": 1,
        "allowed_capabilities": list(admin_api.OPENCODE_RESPONSES_PRESET_GATES),
        "allowed_local_tool_types": ["function", "custom"],
        "client_module": active.pin,
    }
    summary = admin_api._safe_codex_responses_policy_summary(policy)
    assert summary is not None
    assert tuple(summary["allowed_capabilities"]) == admin_api.OPENCODE_RESPONSES_PRESET_GATES


def test_codex_policy_summary_rejects_stale_or_foreign_pin() -> None:
    active = active_client_module_facts(OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID)
    stale = dict(active.pin, fixture_sha256="0" * 64)
    policy = {
        "version": 1,
        "allowed_capabilities": list(admin_api.OPENCODE_RESPONSES_PRESET_GATES),
        "allowed_local_tool_types": ["function", "custom"],
        "client_module": stale,
    }
    assert admin_api._safe_codex_responses_policy_summary(policy) is None


# --- Qwen Codex policy: active pin, not frozen equality ----------------------


def _fake_session_factory():
    @asynccontextmanager
    async def _ctx() -> SimpleNamespace:
        yield SimpleNamespace()

    def _factory():
        return _ctx()

    return _factory


def _stub_qualification(
    monkeypatch: pytest.MonkeyPatch, *, ready: bool, provider: str = "syn-provider"
) -> None:
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None

    result = SimpleNamespace(
        requested_model=profile.public_model,
        endpoint="/v1/responses",
        provider=provider,
        ready=ready,
        profile_id=profile.profile_id,
    )

    class _FakeService:
        def __init__(self, **_kwargs: object) -> None:
            self._result = result

        async def inspect(self) -> list[object]:
            return [self._result]

    monkeypatch.setattr(admin_api, "CodexQualificationService", _FakeService)
    monkeypatch.setattr(admin_api, "get_sessionmaker_from_app", lambda _req: _fake_session_factory())


def test_qwen_policy_pins_active_revision_even_when_profile_is_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The root-cause repair: a rev16 active snapshot must be accepted for a
    route qualified against frozen evidence, and the NEW key pin must be the
    active snapshot - with no version constants patched anywhere."""
    monkeypatch.setattr(
        admin_api,
        "active_client_module_facts",
        lambda _module_id: ActiveClientModuleFacts(
            module_id="codex-0.162-responses-v1",
            module_version="16",
            fixture_sha256="ab" * 32,
            cli_version="0.167.1",
        ),
    )
    _stub_qualification(monkeypatch, ready=True)
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    key_input = _key_input(
        allowed_models=[profile.public_model],
        allowed_providers=["syn-provider"],
        allowed_endpoints=["/v1/models", "/v1/responses"],
    )
    policy = asyncio.run(
        admin_api._validated_admin_qwen_codex_policy(SimpleNamespace(), key_input)
    )
    assert policy["client_module"] == {
        "id": "codex-0.162-responses-v1",
        "version": "16",
        "fixture_sha256": "ab" * 32,
    }


def test_qwen_policy_rejects_profile_outside_installed_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin_api,
        "active_client_module_facts",
        lambda _module_id: ActiveClientModuleFacts(
            module_id="some-other-module",
            module_version="1",
            fixture_sha256="cd" * 32,
        ),
    )
    _stub_qualification(monkeypatch, ready=True)
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    key_input = _key_input(
        allowed_models=[profile.public_model],
        allowed_providers=["syn-provider"],
        allowed_endpoints=["/v1/models", "/v1/responses"],
    )
    with pytest.raises(ValueError, match="not qualified for the installed Codex module"):
        asyncio.run(
            admin_api._validated_admin_qwen_codex_policy(SimpleNamespace(), key_input)
        )


def test_qwen_policy_requires_ready_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_qualification(monkeypatch, ready=False)
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    key_input = _key_input(
        allowed_models=[profile.public_model],
        allowed_providers=["syn-provider"],
        allowed_endpoints=["/v1/models", "/v1/responses"],
    )
    with pytest.raises(ValueError, match="exactly one ready Codex route"):
        asyncio.run(
            admin_api._validated_admin_qwen_codex_policy(SimpleNamespace(), key_input)
        )


def test_qwen_policy_requires_exact_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_qualification(monkeypatch, ready=True)
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    key_input = _key_input(
        allowed_models=[profile.public_model],
        allowed_providers=["syn-provider"],
        allowed_endpoints=["/v1/models", "/v1/responses", "/v1/chat/completions"],
    )
    with pytest.raises(ValueError, match="exactly /v1/models and /v1/responses"):
        asyncio.run(
            admin_api._validated_admin_qwen_codex_policy(SimpleNamespace(), key_input)
        )


def test_qwen_policy_rejects_allow_all_models(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_qualification(monkeypatch, ready=True)
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    key_input = _key_input(
        allowed_models=[],
        allow_all_models=True,
        allowed_providers=["syn-provider"],
        allowed_endpoints=["/v1/models", "/v1/responses"],
    )
    with pytest.raises(ValueError):
        asyncio.run(
            admin_api._validated_admin_qwen_codex_policy(SimpleNamespace(), key_input)
        )
