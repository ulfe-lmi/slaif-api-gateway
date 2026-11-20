"""Pinned Hermes Agent 0.22.5 native Chat Completions client profile.

Thin binding of one packaged, reviewed profile document
(``clients/profiles/hermes-0.22.5-chat.json``) to the shared neutral Chat
engine (``clients/agent_chat.py``).  This module adds no dialect logic of
its own: identity, vocabulary, and bounds all come from the validated DATA,
and the ``fixture_sha256`` identity is the canonical digest of exactly that
document.  Data-only vocabulary upgrades are new document bytes with a new
digest and a re-pinned operator key; there is no per-tool source path.

Provenance (public facts only): NousResearch hermes-agent v0.22.5, source
commit ``bf0203a794a07aac3ff764972ab9087baa4e4f4e``, OpenAI Python SDK
2.24.0, chat_completions wire API.  The captured profile configuration used
the ``cli: [terminal, file, todo]`` toolsets with client-local discovery
(``tool_search`` / ``tool_describe`` / ``tool_call``); the declared
vocabulary is the bounded union of those toolsets plus the discovery
bridge.  Tool names are client-local function declarations and grant no
hosted, routing, or execution authority.
"""

from __future__ import annotations

from pathlib import Path

from slaif_gateway.modules.agent_chat_profile_data import (
    AgentChatProfileData,
    load_agent_chat_profile_file,
)
from slaif_gateway.modules.clients.agent_chat import (
    AgentChatClientModule,
    build_agent_chat_client_module,
    register_agent_chat_client_module,
)

HERMES_0225_CHAT_CLIENT_MODULE_ID = "hermes-0.22.5-chat-v1"
_PROFILE_PATH = (
    Path(__file__).resolve().parent / "profiles" / "hermes-0.22.5-chat.json"
)

HERMES_0225_CHAT_PROFILE_DATA: AgentChatProfileData = load_agent_chat_profile_file(
    _PROFILE_PATH
)

# The exported module version is derived from the validated DATA, so a
# reviewed document revision never requires a source-constant edit; only
# the module ID remains a source literal.
HERMES_0225_CHAT_CLIENT_MODULE_VERSION = HERMES_0225_CHAT_PROFILE_DATA.version

HERMES_0225_CHAT_CLIENT_MODULE: AgentChatClientModule = (
    build_agent_chat_client_module(HERMES_0225_CHAT_PROFILE_DATA)
)

# Static registration into the finite Chat module registry: the source
# literal ID must match the packaged profile DATA's id exactly.
register_agent_chat_client_module(
    HERMES_0225_CHAT_CLIENT_MODULE,
    expected_module_id=HERMES_0225_CHAT_CLIENT_MODULE_ID,
)
