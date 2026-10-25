"""Compatibility imports for the static client/server module architecture."""

from types import MappingProxyType

from slaif_gateway.modules.base import (
    ModuleAdapter,
    ModuleAdapterFactory,
    get_module_adapter,
)
from slaif_gateway.modules.servers.completion_service.adapter import CompletionServiceAdapter

from slaif_gateway.modules.servers.completion_service.profiles import load_bindings

FacialScoringAdapter = CompletionServiceAdapter  # deprecated import name only

# Legacy callers receive an immutable compatibility view. Production dispatch
# is owned by modules.servers.registry.
MODULE_ADAPTER_REGISTRY = MappingProxyType({provider: CompletionServiceAdapter for provider in load_bindings().providers})

__all__ = [
    "MODULE_ADAPTER_REGISTRY",
    "ModuleAdapter",
    "ModuleAdapterFactory",
    "FacialScoringAdapter",
    "get_module_adapter",
]
