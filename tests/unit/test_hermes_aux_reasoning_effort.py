"""Focused synthetic regression: auxiliary ``reasoning_effort`` compatibility.

The pinned Hermes 0.22.5 native client emits its auxiliary ``session_title``
requests with ``reasoning_effort="none"`` while its main requests carry the
configured effort (``xhigh`` in the captured profile).  DATA revision 2 of
the packaged Hermes profile therefore admits the finite ``none`` vocabulary
value; the neutral engine, the default (no-profile) Chat policy, and the
OpenCode 1.19.3 profile (five efforts, unchanged digest) are untouched.

Synthetic request bodies only: no raw capture replay, no provider calls.
"""

from __future__ import annotations

import pytest

from slaif_gateway.modules.clients.agent_chat import (
    AgentChatModuleSelectionError,
    AgentChatRequestError,
    resolve_chat_client_module,
)
from slaif_gateway.modules.agent_chat_profile_data import (
    AGENT_CHAT_REASONING_EFFORT_VOCABULARY,
    AgentChatProfileDataError,
    parse_agent_chat_profile_document,
)
from slaif_gateway.modules.clients.hermes_0225_chat import (
    HERMES_0225_CHAT_CLIENT_MODULE,
    HERMES_0225_CHAT_CLIENT_MODULE_ID,
    HERMES_0225_CHAT_CLIENT_MODULE_VERSION,
    HERMES_0225_CHAT_PROFILE_DATA,
)
from slaif_gateway.modules.clients.opencode_1193_chat import (
    OPENCODE_1193_CHAT_CLIENT_MODULE,
    OPENCODE_1193_CHAT_PROFILE_DATA,
)

# Historical reviewed pin tuple of DATA revision 1 (pre-fix document bytes).
HERMES_V1_FIXTURE_SHA256 = "b70ef47e95385a2ec01e16021a66b27db5c3ceba90a79620ca7ebd3fa51394a9"
# The OpenCode profile is unchanged by this fix.
OPENCODE_FIXTURE_SHA256 = "2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14"


def _title_shape_body(effort: str) -> dict:
    """The native auxiliary session_title request shape (synthetic)."""
    return {
        "model": "synthetic-model",
        "reasoning_effort": effort,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "session_title",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                    "additionalProperties": False,
                },
            },
        },
        "messages": [
            {"role": "system", "content": "You name chat sessions."},
            {"role": "user", "content": "synthetic opening message"},
        ],
    }


def _main_shape_body(effort: str) -> dict:
    """A streaming main-request shape with one tool declaration (synthetic)."""
    return {
        "model": "synthetic-model",
        "reasoning_effort": effort,
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
        "messages": [
            {"role": "system", "content": "synthetic system"},
            {"role": "user", "content": "synthetic prompt"},
        ],
    }


class TestHermesAuxEffortAcceptance:
    def test_title_shape_none_is_accepted(self):
        request = HERMES_0225_CHAT_CLIENT_MODULE.normalize_chat(_title_shape_body("none"))
        assert request.body["reasoning_effort"] == "none"

    def test_main_shape_xhigh_is_unchanged(self):
        request = HERMES_0225_CHAT_CLIENT_MODULE.normalize_chat(_main_shape_body("xhigh"))
        assert request.body["reasoning_effort"] == "xhigh"

    def test_known_efforts_other_than_none_still_accepted(self):
        for effort in ("minimal", "low", "medium", "high"):
            request = HERMES_0225_CHAT_CLIENT_MODULE.normalize_chat(_title_shape_body(effort))
            assert request.body["reasoning_effort"] == effort

    def test_unknown_effort_is_denied(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            HERMES_0225_CHAT_CLIENT_MODULE.normalize_chat(_title_shape_body("ultra"))
        assert excinfo.value.error_code == "agent_chat_reasoning_effort_not_allowed"
        assert excinfo.value.param == "reasoning_effort"


class TestHermesDataIdentity:
    def test_version_bumped_to_two_with_new_digest(self):
        assert HERMES_0225_CHAT_PROFILE_DATA.profile_id == "hermes-0.22.5-chat-v1"
        assert HERMES_0225_CHAT_PROFILE_DATA.version == "2"
        assert len(HERMES_0225_CHAT_PROFILE_DATA.fixture_sha256) == 64
        assert HERMES_0225_CHAT_PROFILE_DATA.fixture_sha256 != HERMES_V1_FIXTURE_SHA256

    def test_exported_module_version_derives_from_data(self):
        assert HERMES_0225_CHAT_CLIENT_MODULE_ID == "hermes-0.22.5-chat-v1"
        assert HERMES_0225_CHAT_CLIENT_MODULE_VERSION == HERMES_0225_CHAT_PROFILE_DATA.version
        assert (
            HERMES_0225_CHAT_CLIENT_MODULE.module_version
            == HERMES_0225_CHAT_PROFILE_DATA.version
        )

    def test_effort_vocabulary_is_finite_six_value_set(self):
        assert AGENT_CHAT_REASONING_EFFORT_VOCABULARY == frozenset(
            {"minimal", "low", "medium", "high", "xhigh", "none"}
        )
        assert HERMES_0225_CHAT_PROFILE_DATA.reasoning_efforts == (
            AGENT_CHAT_REASONING_EFFORT_VOCABULARY
        )

    def test_current_pin_tuple_resolves(self):
        module = resolve_chat_client_module(
            {
                "id": HERMES_0225_CHAT_CLIENT_MODULE_ID,
                "version": "2",
                "fixture_sha256": HERMES_0225_CHAT_PROFILE_DATA.fixture_sha256,
            }
        )
        assert module is HERMES_0225_CHAT_CLIENT_MODULE

    def test_stale_version_one_pin_is_denied(self):
        with pytest.raises(AgentChatModuleSelectionError) as excinfo:
            resolve_chat_client_module(
                {
                    "id": HERMES_0225_CHAT_CLIENT_MODULE_ID,
                    "version": "1",
                    "fixture_sha256": HERMES_V1_FIXTURE_SHA256,
                }
            )
        assert excinfo.value.error_code == "chat_client_module_fixture_mismatch"

    def test_version_one_digest_with_current_version_is_denied(self):
        with pytest.raises(AgentChatModuleSelectionError) as excinfo:
            resolve_chat_client_module(
                {
                    "id": HERMES_0225_CHAT_CLIENT_MODULE_ID,
                    "version": "2",
                    "fixture_sha256": HERMES_V1_FIXTURE_SHA256,
                }
            )
        assert excinfo.value.error_code == "chat_client_module_fixture_mismatch"


class TestEffortVocabularyBounds:
    def test_arbitrary_effort_string_is_denied_in_data(self):
        document = {
            "schema_version": 1,
            "id": "acme-1.0.0-chat-v1",
            "version": "1",
            "client": {
                "name": "acme-agent",
                "distribution_version": "1.0.0",
                "source_tag": "v1.0.0",
                "source_commit": "bf0203a794a07aac3ff764972ab9087baa4e4f4e",
                "sdk_name": "openai-python",
                "sdk_version": "2.24.0",
                "wire_api": "chat_completions",
            },
            "dialect": {
                "reasoning_efforts": ["low", "medium", "high", "xhigh", "none", "ultra"],
                "assistant_message_fields": [],
                "tools": {
                    "names": ["read_file"],
                    "max_declarations": 8,
                    "max_description_bytes": 512,
                    "max_schema_depth": 4,
                    "max_schema_properties": 16,
                    "max_declaration_bytes": 8192,
                },
                "tool_call": {
                    "id_min_length": 1,
                    "id_max_length": 64,
                    "arguments_max_bytes": 4096,
                },
            },
        }
        with pytest.raises(AgentChatProfileDataError) as excinfo:
            parse_agent_chat_profile_document(document)
        assert excinfo.value.field == "dialect.reasoning_efforts"

    def test_six_efforts_is_the_count_ceiling(self):
        document = {
            "schema_version": 1,
            "id": "acme-1.0.0-chat-v1",
            "version": "1",
            "client": {
                "name": "acme-agent",
                "distribution_version": "1.0.0",
                "source_tag": "v1.0.0",
                "source_commit": "bf0203a794a07aac3ff764972ab9087baa4e4f4e",
                "sdk_name": "openai-python",
                "sdk_version": "2.24.0",
                "wire_api": "chat_completions",
            },
            "dialect": {
                "reasoning_efforts": [
                    "minimal",
                    "low",
                    "medium",
                    "high",
                    "xhigh",
                    "none",
                    "extra",
                ],
                "assistant_message_fields": [],
                "tools": {
                    "names": ["read_file"],
                    "max_declarations": 8,
                    "max_description_bytes": 512,
                    "max_schema_depth": 4,
                    "max_schema_properties": 16,
                    "max_declaration_bytes": 8192,
                },
                "tool_call": {
                    "id_min_length": 1,
                    "id_max_length": 64,
                    "arguments_max_bytes": 4096,
                },
            },
        }
        with pytest.raises(AgentChatProfileDataError):
            parse_agent_chat_profile_document(document)


class TestOpenCodeProfileUnchanged:
    def test_opencode_digest_and_version_unchanged(self):
        assert OPENCODE_1193_CHAT_PROFILE_DATA.version == "1"
        assert OPENCODE_1193_CHAT_PROFILE_DATA.fixture_sha256 == OPENCODE_FIXTURE_SHA256

    def test_opencode_none_still_denied(self):
        with pytest.raises(AgentChatRequestError) as excinfo:
            OPENCODE_1193_CHAT_CLIENT_MODULE.normalize_chat(_title_shape_body("none"))
        assert excinfo.value.error_code == "agent_chat_reasoning_effort_not_allowed"
