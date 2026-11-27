"""Finite client-module registry and default selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE,
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.contracts import (
    DEFAULT_CLIENT_MODULE_ID,
    CanonicalClientRequest,
    ModuleSelectionError,
)

DEFAULT_CLIENT_MODULE = OpenAIDefaultClientModule()
CODEX_0147_CLIENT_MODULE = Codex0147ResponsesClientModule()
CODEX_0149_CLIENT_MODULE = Codex0149ResponsesClientModule()
# 228-a: static reviewed OpenCode 1.19.3 Responses client module instance
# (no bootstrap binding; the profile DATA is frozen in the repository).
OPENCODE_1193_RESPONSES_CLIENT_MODULE_INSTANCE = OPENCODE_1193_RESPONSES_CLIENT_MODULE
# The 0.162 registry entry is the concrete module bound to the loaded data
# profile.  It is rebuilt exactly once at process bootstrap when an operator
# profile file is configured; the historical v1/v2 tuples are not live
# runtime pins and resolve to nothing here.
CODEX_0162_CLIENT_MODULE_INSTANCE = CODEX_0162_CLIENT_MODULE
_CLIENT_MODULE_REGISTRY_ENTRIES: dict[str, ClientModule] = {
    DEFAULT_CLIENT_MODULE_ID: DEFAULT_CLIENT_MODULE,
    CODEX_0147_CLIENT_MODULE_ID: CODEX_0147_CLIENT_MODULE,
    CODEX_0149_CLIENT_MODULE_ID: CODEX_0149_CLIENT_MODULE,
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID: OPENCODE_1193_RESPONSES_CLIENT_MODULE_INSTANCE,
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


@dataclass(frozen=True, slots=True)
class ActiveClientModuleFacts:
    """Identity and provenance of the ACTIVE module installed in this process.

    The distinct concepts are kept separate: ``module_id`` is the stable
    executable identifier; ``module_version`` and ``fixture_sha256`` are the
    current compatibility DATA revision and canonical digest; the provenance
    fields describe the CLI/source that produced that DATA.  Frozen
    qualification profile evidence (the revision a route was qualified
    against) is deliberately not part of this active state.
    """

    module_id: str
    module_version: str
    fixture_sha256: str
    cli_version: str | None = None
    source_tag: str | None = None
    source_commit: str | None = None

    @property
    def pin(self) -> dict[str, str]:
        """The exact (id, version, fixture_sha256) pin for new key metadata."""
        return {
            "id": self.module_id,
            "version": self.module_version,
            "fixture_sha256": self.fixture_sha256,
        }


def active_client_module_facts(module_id: str) -> ActiveClientModuleFacts:
    """Resolve ACTIVE module facts from the installed registry snapshot.

    Reads only the concrete registry module bound at process bootstrap
    (packaged default or the operator's validated profile file); it never
    re-reads profile files per call and never falls back to a historical
    frozen identity.  Responses-family modules resolve from the Responses
    registry; Chat-family modules resolve from the separate static Chat
    registry.  Provenance fields are populated only when the bound module
    exposes a reviewed DATA snapshot.
    """
    try:
        module = get_client_module(module_id)
    except ModuleSelectionError:
        # Deferred import: agent_chat does not import this registry module.
        from slaif_gateway.modules.clients.agent_chat import (
            get_agent_chat_client_module,
        )

        module = get_agent_chat_client_module(module_id)
    metadata = client_module_metadata(module)
    cli_version: str | None = None
    source_tag: str | None = None
    source_commit: str | None = None
    profile = getattr(module, "profile", None)
    if profile is not None:
        for attribute, target in (
            ("cli_version", "cli_version"),
            ("source_tag", "source_tag"),
            ("source_commit", "source_commit"),
        ):
            value = getattr(profile, attribute, None)
            if isinstance(value, str) and value:
                if target == "cli_version":
                    cli_version = value
                elif target == "source_tag":
                    source_tag = value
                else:
                    source_commit = value
    if cli_version is None:
        spec = getattr(module, "policy_spec", None)
        provenance = getattr(spec, "provenance", None) if spec is not None else None
        if provenance is not None:
            for attribute, target in (
                ("distribution_version", "cli_version"),
                ("source_tag", "source_tag"),
                ("source_commit", "source_commit"),
            ):
                value = getattr(provenance, attribute, None)
                if isinstance(value, str) and value:
                    if target == "cli_version" and cli_version is None:
                        cli_version = value
                    elif target == "source_tag" and source_tag is None:
                        source_tag = value
                    elif target == "source_commit" and source_commit is None:
                        source_commit = value
    return ActiveClientModuleFacts(
        module_id=metadata["id"],
        module_version=metadata["version"],
        fixture_sha256=metadata["fixture_sha256"],
        cli_version=cli_version,
        source_tag=source_tag,
        source_commit=source_commit,
    )
