"""Finite client-module registry and default selection."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from slaif_gateway.modules.clients.base import ClientModule
from slaif_gateway.modules.clients.openai_default import OpenAIDefaultClientModule
from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    DEFAULT_CLIENT_MODULE_ID,
    ModuleSelectionError,
)

DEFAULT_CLIENT_MODULE = OpenAIDefaultClientModule()
CLIENT_MODULE_REGISTRY: Mapping[str, ClientModule] = MappingProxyType(
    {DEFAULT_CLIENT_MODULE_ID: DEFAULT_CLIENT_MODULE}
)


def get_client_module(module_id: str = DEFAULT_CLIENT_MODULE_ID) -> ClientModule:
    """Resolve only a literal, reviewed client-module identifier."""
    if not isinstance(module_id, str):
        raise ModuleSelectionError("Client module identifier is invalid", error_code="client_module_invalid")
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
    return DEFAULT_CLIENT_MODULE.normalize(endpoint, body)
