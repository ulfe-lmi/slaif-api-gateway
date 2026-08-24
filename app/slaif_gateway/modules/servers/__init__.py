"""Statically registered approved upstream server modules."""

from slaif_gateway.modules.servers.registry import (
    SERVER_MODULE_REGISTRY,
    build_server_adapter,
    ensure_client_server_pair,
    get_server_module,
    resolve_server_module,
)

__all__ = [
    "SERVER_MODULE_REGISTRY",
    "build_server_adapter",
    "ensure_client_server_pair",
    "get_server_module",
    "resolve_server_module",
]
