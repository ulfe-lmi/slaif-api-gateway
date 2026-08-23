"""Statically registered downstream module adapter contracts."""

from slaif_gateway.modules.base import (
    MODULE_ADAPTER_REGISTRY,
    ModuleAdapter,
    ModuleAdapterFactory,
    get_module_adapter,
)
from slaif_gateway.modules.facial_scoring import FacialScoringAdapter

# Native modules are explicit reviewed source-code registrations.  Configuration
# selects this stable identifier but never an import path or user-supplied class.
MODULE_ADAPTER_REGISTRY["facial_scoring"] = FacialScoringAdapter

__all__ = [
    "MODULE_ADAPTER_REGISTRY",
    "ModuleAdapter",
    "ModuleAdapterFactory",
    "FacialScoringAdapter",
    "get_module_adapter",
]
