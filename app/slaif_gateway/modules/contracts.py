"""Pure contracts shared by statically registered client and server modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping

DEFAULT_CLIENT_MODULE_ID = "openai-default"
DEFAULT_CLIENT_MODULE_VERSION = "1"


class ModuleSelectionError(ValueError):
    """Raised when a static module or module pair is not supported."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class CanonicalClientRequest:
    """Content-bearing request facts returned only to the Gateway core."""

    module_id: str
    module_version: str
    endpoint: str
    body: Mapping[str, object]
    capability_intents: tuple[str, ...] = ()
    identity_hints: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ServerModuleDescriptor:
    """Static identity and compatibility metadata for one server module."""

    module_id: str
    module_version: str
    provider_slugs: frozenset[str]
    provider_kinds: frozenset[str]


@dataclass(frozen=True, slots=True)
class ClientServerPair:
    """A finite compatibility declaration, not an authority grant."""

    client_module_id: str
    server_module_id: str
