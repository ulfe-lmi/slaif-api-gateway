"""Statically registered untrusted client-dialect modules."""

from slaif_gateway.modules.clients.registry import (
    CLIENT_MODULE_REGISTRY,
    DEFAULT_CLIENT_MODULE,
    get_client_module,
    normalize_default_client_request,
)

__all__ = [
    "CLIENT_MODULE_REGISTRY",
    "DEFAULT_CLIENT_MODULE",
    "get_client_module",
    "normalize_default_client_request",
]
