"""Pinned OpenCode 1.19.3 native Chat Completions client profile.

Thin binding of one packaged, reviewed profile document
(``clients/profiles/opencode-1.19.3-chat.json``) to the shared neutral Chat
engine (``clients/agent_chat.py``).  This module adds no dialect logic of
its own: identity, vocabulary, and bounds all come from the validated DATA,
and the ``fixture_sha256`` identity is the canonical digest of exactly that
document.  Data-only vocabulary upgrades are new document bytes with a new
digest and a re-pinned operator key; there is no per-tool source path.

Provenance (public facts only): anomalyco/opencode v1.19.3 (release tag
commit ``e3c4eb242585dcd77be1a867391b7c25fd47ce52``), glibc single-file
executable pinned by SHA-256 (see
``tests/fixtures/opencode/1.19.3/chat/provenance.json``),
``@ai-sdk/openai-compatible`` 2.0.41 on ai 6.0.168, chat_completions wire
API.  The reviewed capture baseline is the 9-tool denied-web-baseline
configuration; the configuration-dependent ``webfetch`` extension observed
under a permissive task configuration is documented in the dossier and
deliberately outside the v1 vocabulary until a reviewed DATA revision.
Tool names are client-local function declarations and grant no hosted,
routing, or execution authority.
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

OPENCODE_1193_CHAT_CLIENT_MODULE_ID = "opencode-1.19.3-chat-v1"
OPENCODE_1193_CHAT_CLIENT_MODULE_VERSION = "1"

_PROFILE_PATH = (
    Path(__file__).resolve().parent / "profiles" / "opencode-1.19.3-chat.json"
)

OPENCODE_1193_CHAT_PROFILE_DATA: AgentChatProfileData = load_agent_chat_profile_file(
    _PROFILE_PATH
)

OPENCODE_1193_CHAT_CLIENT_MODULE: AgentChatClientModule = (
    build_agent_chat_client_module(OPENCODE_1193_CHAT_PROFILE_DATA)
)

# Static registration into the finite Chat module registry: the source
# literal ID must match the packaged profile DATA's id exactly.
register_agent_chat_client_module(
    OPENCODE_1193_CHAT_CLIENT_MODULE,
    expected_module_id=OPENCODE_1193_CHAT_CLIENT_MODULE_ID,
)
