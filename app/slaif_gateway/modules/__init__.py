"""Statically registered downstream module adapter contracts."""

from slaif_gateway.modules.base import (
    MODULE_ADAPTER_REGISTRY,
    ModuleAdapter,
    ModuleAdapterFactory,
    get_module_adapter,
)

__all__ = [
    "MODULE_ADAPTER_REGISTRY",
    "ModuleAdapter",
    "ModuleAdapterFactory",
    "get_module_adapter",
]
