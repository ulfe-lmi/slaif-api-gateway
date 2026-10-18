"""Finite client-module registry and default selection."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from slaif_gateway.modules.clients.base import ClientModule
from slaif_gateway.modules.clients.codex_0147 import (
    CODEX_0147_CLIENT_MODULE_ID,
    Codex0147ResponsesClientModule,
)
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_CLIENT_MODULE_ID,
    Codex0149ResponsesClientModule,
)
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE,
    CODEX_0162_CLIENT_MODULE_ID,
    Codex0162ResponsesClientModule,
)
from slaif_gateway.modules.clients.openai_default import OpenAIDefaultClientModule
from slaif_gateway.modules.contracts import (
    DEFAULT_CLIENT_MODULE_ID,
    CanonicalClientRequest,
    ModuleSelectionError,
)

DEFAULT_CLIENT_MODULE = OpenAIDefaultClientModule()
CODEX_0147_CLIENT_MODULE = Codex0147ResponsesClientModule()
CODEX_0149_CLIENT_MODULE = Codex0149ResponsesClientModule()
# The 0.162 registry entry is the concrete module bound to the loaded data
# profile.  It is rebuilt exactly once at process bootstrap when an operator
# profile file is configured; the historical v1/v2 tuples are not live
# runtime pins and resolve to nothing here.
CODEX_0162_CLIENT_MODULE_INSTANCE = CODEX_0162_CLIENT_MODULE
_CLIENT_MODULE_REGISTRY_ENTRIES: dict[str, ClientModule] = {
    DEFAULT_CLIENT_MODULE_ID: DEFAULT_CLIENT_MODULE,
    CODEX_0147_CLIENT_MODULE_ID: CODEX_0147_CLIENT_MODULE,
    CODEX_0149_CLIENT_MODULE_ID: CODEX_0149_CLIENT_MODULE,
    CODEX_0162_CLIENT_MODULE_ID: CODEX_0162_CLIENT_MODULE_INSTANCE,
}
CLIENT_MODULE_REGISTRY: Mapping[str, ClientModule] = MappingProxyType(
    _CLIENT_MODULE_REGISTRY_ENTRIES
)


_CODEX_0162_BOOTSTRAP_BOUND = False


def bind_codex_0162_client_module(module: Codex0162ResponsesClientModule) -> None:
    """Bind the registry's 0.162 entry to one concrete data-profile module.

    The one-shot guard lives on this actual registry binding.  The
    import-time entry is the packaged default; re-binding that same
    identity (repeated same-config app/CLI initialization) is an
    idempotent no-op that does not consume the binding.  The first bind to
    a different profile identity completes the bootstrap; any later bind to
    a different identity (a reconfiguration) fails closed.  The registry
    mapping object stays stable for every importer; the guarded bootstrap
    write happens on the private backing dict under the immutable proxy.
    """
    global _CODEX_0162_BOOTSTRAP_BOUND
    global CODEX_0162_CLIENT_MODULE_INSTANCE
    if not isinstance(module, Codex0162ResponsesClientModule):
        raise ModuleSelectionError(
            "Client module is not registered", error_code="unsupported_client_module"
        )
    current = _CLIENT_MODULE_REGISTRY_ENTRIES[CODEX_0162_CLIENT_MODULE_ID]
    if current.module_version == module.module_version and (
        current.fixture_sha256 == module.fixture_sha256
    ):
        # Repeated same-config initialization: keep the existing binding.
        CODEX_0162_CLIENT_MODULE_INSTANCE = current
        return
    if _CODEX_0162_BOOTSTRAP_BOUND:
        raise ModuleSelectionError(
            "The Codex 0162 client module bootstrap has already completed",
            error_code="codex_0162_bootstrap_locked",
        )
    _CODEX_0162_BOOTSTRAP_BOUND = True
    CODEX_0162_CLIENT_MODULE_INSTANCE = module
    _CLIENT_MODULE_REGISTRY_ENTRIES[CODEX_0162_CLIENT_MODULE_ID] = module


_LEGACY_CODEX_GATES = frozenset(
    {
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "codex_encrypted_reasoning_replay",
        "codex_compaction",
    }
)


def get_client_module(module_id: str = DEFAULT_CLIENT_MODULE_ID) -> ClientModule:
    """Resolve only a literal, reviewed client-module identifier."""
    if not isinstance(module_id, str):
        raise ModuleSelectionError(
            "Client module identifier is invalid", error_code="client_module_invalid"
        )
    module = CLIENT_MODULE_REGISTRY.get(module_id)
    if module is None:
        raise ModuleSelectionError(
            "Client module is not registered",
            error_code="unsupported_client_module",
        )
    return module


def normalize_default_client_request(
    endpoint: str,
    body: Mapping[str, object],
) -> CanonicalClientRequest:
    """Normalize a request through the core-owned default module."""
    return get_client_module(DEFAULT_CLIENT_MODULE_ID).normalize(endpoint, body)


def resolve_responses_client_module(policy: object) -> ClientModule:
    """Resolve a Responses client only from complete server-side key metadata."""
    if policy is None:
        return DEFAULT_CLIENT_MODULE
    if not isinstance(policy, Mapping):
        raise ModuleSelectionError(
            "Responses client-module metadata is invalid",
            error_code="client_module_metadata_invalid",
        )
    raw_module = policy.get("client_module")
    if raw_module is None:
        allowed = policy.get("allowed_capabilities")
        local_tools = policy.get("allowed_local_tool_types")
        if (
            policy.get("version") == 1
            and isinstance(allowed, list)
            and set(allowed) == _LEGACY_CODEX_GATES
            and isinstance(local_tools, list)
            and set(local_tools) == {"function", "custom"}
        ):
            return CODEX_0147_CLIENT_MODULE
        return DEFAULT_CLIENT_MODULE
    if not isinstance(raw_module, Mapping) or set(raw_module) != {
        "id",
        "version",
        "fixture_sha256",
    }:
        raise ModuleSelectionError(
            "Responses client-module metadata is invalid",
            error_code="client_module_metadata_invalid",
        )
    module_id = raw_module.get("id")
    module_version = raw_module.get("version")
    fixture_sha256 = raw_module.get("fixture_sha256")
    if not isinstance(module_id, str) or not isinstance(module_version, str):
        raise ModuleSelectionError(
            "Responses client-module metadata is invalid",
            error_code="client_module_metadata_invalid",
        )
    module = get_client_module(module_id)
    if module.module_version != module_version or module.fixture_sha256 != fixture_sha256:
        # Legacy and stale pins fail closed; the 0.162 historical v1/v2
        # tuples are audited migration destinations, not live runtime pins.
        raise ModuleSelectionError(
            "Responses client-module fixture metadata does not match",
            error_code="client_module_fixture_mismatch",
        )
    return module


def client_module_metadata(module: ClientModule) -> dict[str, str]:
    """Return safe profile facts for reviewed operator metadata."""
    fixture_sha256 = getattr(module, "fixture_sha256", None)
    if not isinstance(fixture_sha256, str):
        raise ModuleSelectionError(
            "Client module does not expose a reviewed fixture digest",
            error_code="client_module_metadata_invalid",
        )
    return {
        "id": module.module_id,
        "version": module.module_version,
        "fixture_sha256": fixture_sha256,
    }
