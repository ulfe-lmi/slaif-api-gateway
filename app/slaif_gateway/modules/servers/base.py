"""Server-module adapter contract and compatibility alias."""

from slaif_gateway.modules.base import ModuleAdapter, ModuleAdapterFactory

ServerModuleAdapter = ModuleAdapter
ServerModuleAdapterFactory = ModuleAdapterFactory

__all__ = [
    "ModuleAdapter",
    "ModuleAdapterFactory",
    "ServerModuleAdapter",
    "ServerModuleAdapterFactory",
]
