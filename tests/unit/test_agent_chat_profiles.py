"""Focused pure tests for the neutral agent Chat profile engine and DATA.

These tests exercise only the shared, profile-agnostic machinery
(``modules/agent_chat_profile_data.py`` and ``modules/clients/agent_chat.py``)
plus the packaged Hermes binding as a registered instance. They are pure:
no database, no network, no real client, no real provider.
"""

from __future__ import annotations

import copy
import json

import pytest
from slaif_gateway.modules.agent_chat_profile_data import (
    AgentChatProfileDataError,
    MAX_AGENT_CHAT_PROFILE_FILE_BYTES,
    canonical_profile_digest,
    load_agent_chat_profile_file,
    parse_agent_chat_profile_document,
)
from slaif_gateway.modules.clients.agent_chat import (
    AGENT_CHAT_CLIENT_MODULE_REGISTRY,
    AGENT_CHAT_ENDPOINT,
    AGENT_CHAT_STANDARD_TOP_LEVEL_FIELDS,
    AgentChatModuleSelectionError,
    AgentChatProfileSpec,
    AgentChatRequestError,
    agent_chat_profile_metadata,
    build_agent_chat_client_module,
    get_agent_chat_client_module,
    register_agent_chat_client_module,
    resolve_chat_client_module,
)
# Importing the packaged Hermes binding performs its static, source-literal
# registration into the finite Chat module registry under test.
from slaif_gateway.modules.clients.hermes_0225_chat import (
    HERMES_0225_CHAT_CLIENT_MODULE,
    HERMES_0225_CHAT_CLIENT_MODULE_ID,
)

COMMIT = "bf0203a794a07aac3ff764972ab9087baa4e4f4e"


def _document(**overrides):
    doc = {
        "schema_version": 1,
        "id": "acme-1.0.0-chat-v1",
        "version": "1",
        "client": {
            "name": "acme-agent",
            "distribution_version": "1.0.0",
            "source_tag": "v1.0.0",
            "source_commit": COMMIT,
            "sdk_name": "openai-python",
            "sdk_version": "2.24.0",
            "wire_api": "chat_completions",
        },
        "dialect": {
            "reasoning_efforts": ["low", "medium", "high", "xhigh"],
            "assistant_message_fields": [
                {"name": "reasoning", "max_bytes": 4096},
            ],
            "tools": {
                "names": ["read_file", "terminal"],
                "max_declarations": 8,
                "max_description_bytes": 512,
                "max_schema_depth": 4,
                "max_schema_properties": 16,
                "max_declaration_bytes": 8192,
            },
            "tool_call": {"id_min_length": 1, "id_max_length": 64, "arguments_max_bytes": 4096},
        },
    }
    for key, value in overrides.items():
        doc[key] = value
    return doc


def _spec_from(document):
    return build_agent_chat_client_module(parse_agent_chat_profile_document(document))


# ----------------------------------------------------------------------
# Profile DATA loader
# ----------------------------------------------------------------------


class TestProfileDataLoader:
    def test_valid_document_parses_and_digests(self):
        data = parse_agent_chat_profile_document(_document())
        assert data.profile_id == "acme-1.0.0-chat-v1"
        assert data.version == "1"
        assert data.reasoning_efforts == frozenset({"low", "medium", "high", "xhigh"})
        assert data.tools.names == frozenset({"read_file", "terminal"})
        assert len(data.fixture_sha256) == 64
        # The digest describes exactly the exposed (frozen) document.
        assert canonical_profile_digest(data.document) == data.fixture_sha256

    def test_digest_is_stable_under_key_order(self):
        a = parse_agent_chat_profile_document(_document())
        reordered = json.loads(json.dumps(_document()))
        # Rebuild with a different insertion order by re-parsing a fresh dict.
        fresh = {
            "dialect": reordered["dialect"],
            "client": reordered["client"],
            "version": reordered["version"],
            "id": reordered["id"],
            "schema_version": reordered["schema_version"],
        }
        b = parse_agent_chat_profile_document(fresh)
        assert a.fixture_sha256 == b.fixture_sha256

    def test_exposed_document_is_deep_frozen_and_independent(self):
        mutable = _document()
        data = parse_agent_chat_profile_document(mutable)
        # Mutating the caller's original after parsing must not affect the
        # exposed document or its digest.
        mutable["dialect"]["tools"]["names"].append("evil_tool")
        mutable["dialect"]["tools"]["max_declarations"] = 999
        mutable["client"]["name"] = "hacked"
        assert "evil_tool" not in data.tools.names
        assert data.tools.max_declarations == 8
        assert data.client.name == "acme-agent"
        assert canonical_profile_digest(data.document) == data.fixture_sha256
        with pytest.raises((TypeError, AttributeError)):
            data.document["dialect"]["tools"]["names"].append("x")  # type: ignore[index]

    def test_scoped_sdk_name_supported(self):
        doc = _document()
        doc["client"]["sdk_name"] = "@ai-sdk/openai-compatible"
        assert parse_agent_chat_profile_document(doc).client.sdk_name == "@ai-sdk/openai-compatible"

    @pytest.mark.parametrize("bad", ["@bad scope/x", "@", "a/b/c/d", "@lead/", "has space"])
    def test_malformed_sdk_name_rejected(self, bad):
        doc = _document()
        doc["client"]["sdk_name"] = bad
        with pytest.raises(AgentChatProfileDataError):
            parse_agent_chat_profile_document(doc)

    def test_tool_name_grammar_admits_observed_forms(self):
        for good in ("_read_page", "readFile", "browser_navigate", "t1", "a-b_c.d"):
            doc = _document()
            doc["dialect"]["tools"]["names"] = [good]
            assert good in parse_agent_chat_profile_document(doc).tools.names

    @pytest.mark.parametrize("bad", ["-lead", ".lead", "has/slash", "has space", "Ünicode", ""])
    def test_tool_name_grammar_rejects_out_of_form(self, bad):
        doc = _document()
        doc["dialect"]["tools"]["names"] = [bad]
        with pytest.raises(AgentChatProfileDataError):
            parse_agent_chat_profile_document(doc)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.pop("schema_version"),
            lambda d: d.update(schema_version=2),
            lambda d: d.update(extra="x"),
            lambda d: d["client"].update(extra="x"),
            lambda d: d["dialect"].update(extra="x"),
            lambda d: d["dialect"]["tools"].pop("max_schema_depth"),
            lambda d: d["dialect"].update(reasoning_efforts=[]),
            lambda d: d["dialect"].update(reasoning_efforts=["ultra"]),
            lambda d: d["dialect"].update(reasoning_efforts=["high", "high"]),
            lambda d: d["client"].update(wire_api="responses"),
            lambda d: d["client"].update(source_commit="nothex"),
            lambda d: d["dialect"].update(
                assistant_message_fields=[{"name": "content", "max_bytes": 10}]
            ),
            lambda d: d["dialect"]["tool_call"].update(id_min_length=9, id_max_length=2),
        ],
    )
    def test_strict_document_rejections(self, mutate):
        doc = _document()
        mutate(doc)
        with pytest.raises(AgentChatProfileDataError):
            parse_agent_chat_profile_document(doc)

    def test_file_round_trip_matches_memory(self, tmp_path):
        doc = _document()
        target = tmp_path / "profile.json"
        target.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
        loaded = load_agent_chat_profile_file(target)
        assert loaded.fixture_sha256 == parse_agent_chat_profile_document(doc).fixture_sha256

    def test_oversized_file_rejected_with_bounded_read(self, tmp_path):
        target = tmp_path / "big.json"
        target.write_bytes(b"{" + b'"pad": "' + b"x" * (MAX_AGENT_CHAT_PROFILE_FILE_BYTES - 4) + b'"' + b"}")
        with pytest.raises(AgentChatProfileDataError) as excinfo:
            load_agent_chat_profile_file(target)
        assert "size" in excinfo.value.problem.lower()

    @pytest.mark.parametrize("payload", [b"\xff\xfe{", b"{not json", b"null"])
    def test_invalid_file_payloads_rejected(self, tmp_path, payload):
        target = tmp_path / "bad.json"
        target.write_bytes(payload)
        with pytest.raises(AgentChatProfileDataError):
            load_agent_chat_profile_file(target)


# ----------------------------------------------------------------------
# Neutral engine: selection, purity, and the standard surface
# ----------------------------------------------------------------------


class TestNeutralEngine:
    def test_standard_surface_mirrors_field_registry_non_rejecting_set(self):
        from slaif_gateway.services.chat_completion_field_policy import (
            CHAT_COMPLETION_FIELD_REGISTRY,
        )

        excluded = {
            "web_search_options",  # hosted capability: no profile may grant it
            "background",
            "previous_response_id",
            "conversation",
            "external_web_access",
            "defer_loading",
        }
        assert AGENT_CHAT_STANDARD_TOP_LEVEL_FIELDS == (
            set(CHAT_COMPLETION_FIELD_REGISTRY) - excluded
        )

    def test_absent_pin_resolves_to_none_default(self):
        assert resolve_chat_client_module(None) is None

    def test_pin_selection_and_fail_closed(self):
        module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        pin = agent_chat_profile_metadata(module)
        assert resolve_chat_client_module(pin) is module
        with pytest.raises(AgentChatModuleSelectionError) as bad_shape:
            resolve_chat_client_module({"id": pin["id"]})
        assert bad_shape.value.error_code == "chat_client_module_metadata_invalid"
        with pytest.raises(AgentChatModuleSelectionError):
            resolve_chat_client_module("not-a-mapping")
        with pytest.raises(AgentChatModuleSelectionError) as stale:
            resolve_chat_client_module({**pin, "version": "999"})
        assert stale.value.error_code == "chat_client_module_fixture_mismatch"
        with pytest.raises(AgentChatModuleSelectionError) as mismatch:
            resolve_chat_client_module({**pin, "fixture_sha256": "0" * 64})
        assert mismatch.value.error_code == "chat_client_module_fixture_mismatch"
        with pytest.raises(AgentChatModuleSelectionError) as unknown:
            resolve_chat_client_module({"id": "nope-1.0.0-chat-v1", "version": "1", "fixture_sha256": "0" * 64})
        assert unknown.value.error_code == "unsupported_client_module"
        # Responses-only module IDs are not Chat modules.
        with pytest.raises(AgentChatModuleSelectionError):
            resolve_chat_client_module(
                {"id": "codex-0.162-responses-v1", "version": "1", "fixture_sha256": "0" * 64}
            )

    def test_get_module_requires_registered_literal(self):
        assert (
            get_agent_chat_client_module("hermes-0.22.5-chat-v1")
            is AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        )
        with pytest.raises(AgentChatModuleSelectionError):
            get_agent_chat_client_module("")
        with pytest.raises(AgentChatModuleSelectionError):
            get_agent_chat_client_module(123)  # type: ignore[arg-type]

    def test_packaged_hermes_module_static_registration_identity(self):
        # The top-of-module import of the packaged Hermes binding performs its
        # static, source-literal registration as an explicit side effect. The
        # registry lookup must return that exact module identity.
        assert (
            get_agent_chat_client_module(HERMES_0225_CHAT_CLIENT_MODULE_ID)
            is HERMES_0225_CHAT_CLIENT_MODULE
        )

    def test_registration_is_per_id_and_idempotent(self):
        module = _spec_from(_document())
        # A fresh ID registers against its source-literal expected ID; an
        # identical re-registration is a no-op.
        register_agent_chat_client_module(module, expected_module_id=module.module_id)
        try:
            assert AGENT_CHAT_CLIENT_MODULE_REGISTRY[module.module_id] is module
            register_agent_chat_client_module(module, expected_module_id=module.module_id)
            # A different identity under the same ID fails closed.
            other = _spec_from(_document(version="2"))
            with pytest.raises(AgentChatModuleSelectionError) as conflict:
                register_agent_chat_client_module(other, expected_module_id=other.module_id)
            assert conflict.value.error_code == "chat_client_module_conflict"
            # A distinct ID still registers independently (no global lock).
            third = _spec_from(_document(id="acme-1.0.1-chat-v1"))
            register_agent_chat_client_module(third, expected_module_id="acme-1.0.1-chat-v1")
            assert AGENT_CHAT_CLIENT_MODULE_REGISTRY[third.module_id] is third
        finally:
            from slaif_gateway.modules.clients import agent_chat as engine

            engine._AGENT_CHAT_MODULE_ENTRIES.pop(module.module_id, None)
            engine._AGENT_CHAT_MODULE_ENTRIES.pop("acme-1.0.1-chat-v1", None)

    def test_registration_requires_source_literal_expected_id(self):
        module = _spec_from(_document())
        try:
            # Data cannot pick its own registry identity: a wrong source
            # literal fails closed before any registry entry exists.
            with pytest.raises(AgentChatModuleSelectionError) as mismatch:
                register_agent_chat_client_module(module, expected_module_id="other-1.0.0-chat-v1")
            assert mismatch.value.error_code == "chat_client_module_identity_mismatch"
            assert module.module_id not in AGENT_CHAT_CLIENT_MODULE_REGISTRY
            with pytest.raises(AgentChatModuleSelectionError):
                register_agent_chat_client_module(module, expected_module_id="")
        finally:
            from slaif_gateway.modules.clients import agent_chat as engine

            engine._AGENT_CHAT_MODULE_ENTRIES.pop(module.module_id, None)

    def test_normalize_only_accepts_chat_endpoint(self):
        module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        body = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
        assert module.normalize(AGENT_CHAT_ENDPOINT, body).endpoint == AGENT_CHAT_ENDPOINT
        with pytest.raises(AgentChatModuleSelectionError) as excinfo:
            module.normalize("/v1/responses", body)
        assert excinfo.value.error_code == "unsupported_client_endpoint"

    def test_decoder_is_pure_and_side_effect_free(self):
        module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        body = {
            "model": "m",
            "reasoning_effort": "xhigh",
            "messages": [
                {"role": "user", "content": "canary-secret-provider-key-value"},
                {
                    "role": "assistant",
                    "content": None,
                    "reasoning": "r",
                    "tool_calls": [
                        {"id": "x" * 16, "type": "function",
                         "function": {"name": "read_file", "arguments": "{}"}}
                    ],
                },
                {"role": "tool", "tool_call_id": "x" * 16, "content": "result"},
            ],
        }
        before = copy.deepcopy(body)
        first = module.normalize_chat(body)
        second = module.normalize_chat(body)
        assert body == before  # caller-owned input untouched
        assert first.body is not body and second.body is not body
        assert first.body == second.body
        # Independent output copies: mutating one result cannot affect the next.
        first.body["model"] = "tampered"
        assert module.normalize_chat(body).body["model"] == "m"
        # Safe profile facts only (public reviewed identity, no content).
        assert first.profile_facts["agent_chat_module_id"] == module.module_id
        assert first.profile_facts["agent_chat_fixture_sha256"] == module.fixture_sha256

    def test_hints_never_select_or_widen_profile(self):
        module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        base = {
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
        }
        with_metadata = {
            **base,
            "metadata": {"client": "hermes-agent", "user_agent": "OpenAI/Python 2.24.0"},
        }
        assert module.normalize_chat(base).body == base
        assert module.normalize_chat(with_metadata).body == with_metadata
        # A model named like a harness never widens anything.
        with pytest.raises(AgentChatRequestError):
            module.normalize_chat({**base, "reasoning_effort": "ultra"})

    def test_unknown_top_level_field_fails_closed(self):
        module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        with pytest.raises(AgentChatRequestError) as excinfo:
            module.normalize_chat(
                {"model": "m", "messages": [{"role": "user", "content": "x"}], "hosted": True}
            )
        assert excinfo.value.error_code == "agent_chat_unknown_field"

    def test_spec_is_immutable(self):
        module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]
        assert isinstance(module.policy_spec, AgentChatProfileSpec)
        with pytest.raises((AttributeError, TypeError)):
            module.policy_spec.module_id = "tampered"


# ----------------------------------------------------------------------
# Named tool_choice must reference the CURRENT request's declarations
# ----------------------------------------------------------------------


def _named_choice(name: str) -> dict[str, object]:
    return {"type": "function", "function": {"name": name}}


class TestNamedToolChoiceDeclarationMembership:
    def setup_method(self):
        self.module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]

    @pytest.mark.parametrize(
        "tools_value",
        [None, [], "missing"],
        ids=["tools_null", "tools_empty", "tools_absent"],
    )
    def test_named_choice_fails_closed_without_declarations(self, tools_value):
        body = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
        if tools_value != "missing":
            body["tools"] = tools_value
        body["tool_choice"] = _named_choice("read_file")
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_tool_choice_not_declared"

    def test_named_choice_fails_for_undeclared_name(self):
        body = {
            "model": "m",
            "messages": [{"role": "user", "content": "x"}],
            "tools": [
                {"type": "function", "function": {"name": "write_file"}},
            ],
            "tool_choice": _named_choice("read_file"),
        }
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_tool_choice_not_declared"

    def test_named_choice_accepted_for_declared_name(self):
        body = {
            "model": "m",
            "messages": [{"role": "user", "content": "x"}],
            "tools": [
                {"type": "function", "function": {"name": "read_file"}},
                {"type": "function", "function": {"name": "write_file"}},
            ],
            "tool_choice": _named_choice("read_file"),
        }
        result = self.module.normalize_chat(body)
        assert result.body["tool_choice"] == _named_choice("read_file")

    @pytest.mark.parametrize("choice", ["auto", "none", "required"])
    def test_string_choices_never_require_declarations(self, choice):
        body = {
            "model": "m",
            "messages": [{"role": "user", "content": "x"}],
            "tool_choice": choice,
        }
        result = self.module.normalize_chat(body)
        assert result.body["tool_choice"] == choice


# ----------------------------------------------------------------------
# Demonstrated pre-checkpoint gap regressions
# ----------------------------------------------------------------------


def _call(id_value, name="read_file"):
    return {
        "id": id_value,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


class TestLegacyDialectRejected:
    def setup_method(self):
        self.module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]

    def test_top_level_functions_rejected(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(
                {
                    "model": "m",
                    "messages": [{"role": "user", "content": "x"}],
                    "functions": [{"name": "read_file", "parameters": {}}],
                }
            )
        assert excinfo.value.error_code == "agent_chat_legacy_functions_not_allowed"

    def test_top_level_function_call_rejected(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(
                {
                    "model": "m",
                    "messages": [{"role": "user", "content": "x"}],
                    "function_call": {"name": "read_file"},
                }
            )
        assert excinfo.value.error_code == "agent_chat_legacy_functions_not_allowed"

    def test_assistant_function_call_rejected(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(
                {
                    "model": "m",
                    "messages": [
                        {"role": "user", "content": "x"},
                        {"role": "assistant", "content": None,
                         "function_call": {"name": "read_file"}},
                    ],
                }
            )
        assert excinfo.value.error_code == "agent_chat_legacy_functions_not_allowed"

    def test_function_role_rejected(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(
                {
                    "model": "m",
                    "messages": [
                        {"role": "user", "content": "x"},
                        {"role": "assistant", "content": None,
                         "tool_calls": [_call("a" * 16)]},
                        {"role": "tool", "tool_call_id": "a" * 16, "content": "r"},
                        {"role": "function", "name": "read_file", "content": "r"},
                    ],
                }
            )
        assert excinfo.value.error_code == "agent_chat_legacy_functions_not_allowed"


class TestCallResultLinkage:
    def setup_method(self):
        self.module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]

    def _body(self, messages):
        return {"model": "m", "messages": messages}

    def test_duplicate_result_rejected(self):
        body = self._body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": None, "tool_calls": [_call("a" * 16)]},
                {"role": "tool", "tool_call_id": "a" * 16, "content": "r1"},
                {"role": "tool", "tool_call_id": "a" * 16, "content": "r2"},
            ]
        )
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_tool_result_duplicate"

    def test_reuse_of_still_pending_call_id_rejected(self):
        body = self._body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": None,
                 "tool_calls": [_call("a" * 16), _call("a" * 16)]},
            ]
        )
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_tool_call_id_reused"

    def test_reuse_of_resolved_call_id_rejected(self):
        body = self._body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": None, "tool_calls": [_call("a" * 16)]},
                {"role": "tool", "tool_call_id": "a" * 16, "content": "r"},
                {"role": "assistant", "content": None, "tool_calls": [_call("a" * 16)]},
                {"role": "tool", "tool_call_id": "a" * 16, "content": "r2"},
            ]
        )
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_tool_call_id_reused"

    def test_unresolved_call_rejected(self):
        body = self._body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": None,
                 "tool_calls": [_call("a" * 16), _call("b" * 16)]},
                {"role": "tool", "tool_call_id": "a" * 16, "content": "r"},
            ]
        )
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_tool_call_unresolved"

    def test_sequential_multi_call_loop_accepted(self):
        body = self._body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": None,
                 "tool_calls": [_call("a" * 16), _call("b" * 16)]},
                {"role": "tool", "tool_call_id": "b" * 16, "content": "rb"},
                {"role": "tool", "tool_call_id": "a" * 16, "content": "ra"},
            ]
        )
        self.module.normalize_chat(body)


class TestSafeDiagnostics:
    def setup_method(self):
        self.module = AGENT_CHAT_CLIENT_MODULE_REGISTRY["hermes-0.22.5-chat-v1"]

    def test_unknown_field_param_does_not_echo_raw_key(self):
        secret_like_key = "Authorization: Bearer sk-slaif-secret-canary"
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(
                {"model": "m", "messages": [{"role": "user", "content": "x"}],
                 secret_like_key: "v"}
            )
        assert excinfo.value.param == "top_level"
        assert secret_like_key not in str(excinfo.value)

    def test_disallowed_message_field_param_does_not_echo_raw_key(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(
                {
                    "model": "m",
                    "messages": [
                        {"role": "user", "content": "x"},
                        {"role": "assistant", "content": None,
                         "leaked_secret_field": "v"},
                    ],
                }
            )
        assert excinfo.value.param == "messages[1]"
        assert "leaked_secret_field" not in str(excinfo.value)

    def test_schema_recursion_params_are_positional_only(self):
        deep = {"secret_schema_key": {"nested_secret": [1, 2]}}
        body = {
            "model": "m",
            "messages": [{"role": "user", "content": "x"}],
            "tools": [
                {"type": "function",
                 "function": {"name": "read_file",
                              "parameters": {"type": "object", "properties": deep}}}
            ],
        }
        self.module.normalize_chat(body)  # valid: names are data, not diagnostics
        # Force a depth failure and assert the param stays positional.
        nested = {}
        level = nested
        for _ in range(12):
            level["child"] = {}
            level = level["child"]
        body["tools"][0]["function"]["parameters"] = nested
        with pytest.raises(AgentChatRequestError) as excinfo:
            self.module.normalize_chat(body)
        assert excinfo.value.error_code == "agent_chat_schema_too_deep"
        assert "child" not in excinfo.value.param
        assert excinfo.value.param.startswith("tools[0].function.parameters")
