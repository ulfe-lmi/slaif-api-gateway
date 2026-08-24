"""Statically registered untrusted client-dialect modules."""

from slaif_gateway.modules.clients.registry import (
    CLIENT_MODULE_REGISTRY,
    CODEX_0147_CLIENT_MODULE,
    CODEX_0149_CLIENT_MODULE,
    DEFAULT_CLIENT_MODULE,
    client_module_metadata,
    get_client_module,
    normalize_default_client_request,
    resolve_responses_client_module,
)

__all__ = [
    "CLIENT_MODULE_REGISTRY",
    "CODEX_0147_CLIENT_MODULE",
    "CODEX_0149_CLIENT_MODULE",
    "DEFAULT_CLIENT_MODULE",
    "client_module_metadata",
    "get_client_module",
    "normalize_default_client_request",
    "resolve_responses_client_module",
]
