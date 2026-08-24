"""Static server-module descriptors and one production adapter dispatch path."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from slaif_gateway.modules.contracts import (
    ClientServerPair,
    DEFAULT_CLIENT_MODULE_ID,
    ModuleSelectionError,
    ServerModuleDescriptor,
)
from slaif_gateway.modules.servers.facial_scoring import FacialScoringAdapter
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.providers.openai_compatible import OpenAICompatibleProviderAdapter
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter

OPENAI_SERVER_MODULE_ID = "openai"
OPENROUTER_SERVER_MODULE_ID = "openrouter"
OPENAI_COMPATIBLE_SERVER_MODULE_ID = "openai-compatible"
FACIAL_SCORING_SERVER_MODULE_ID = "facial_scoring"


def _openai_factory(settings: object, **kwargs: object) -> object:
    return OpenAIProviderAdapter(settings, **kwargs)


def _openrouter_factory(settings: object, **kwargs: object) -> object:
    kwargs.pop("provider_name", None)
    return OpenRouterProviderAdapter(settings, **kwargs)


def _openai_compatible_factory(settings: object, **kwargs: object) -> object:
    return OpenAICompatibleProviderAdapter(settings, **kwargs)


def _facial_scoring_factory(settings: object, **kwargs: object) -> object:
    _ = settings
    return FacialScoringAdapter(**kwargs)


SERVER_MODULE_REGISTRY: Mapping[str, tuple[ServerModuleDescriptor, Callable[..., object]]] = MappingProxyType(
    {
        OPENAI_SERVER_MODULE_ID: (
            ServerModuleDescriptor(
                module_id=OPENAI_SERVER_MODULE_ID,
                module_version="1",
                provider_slugs=frozenset({"openai"}),
                provider_kinds=frozenset({"", "openai"}),
            ),
            _openai_factory,
        ),
        OPENROUTER_SERVER_MODULE_ID: (
            ServerModuleDescriptor(
                module_id=OPENROUTER_SERVER_MODULE_ID,
                module_version="1",
                provider_slugs=frozenset({"openrouter"}),
                provider_kinds=frozenset({"", "openrouter"}),
            ),
            _openrouter_factory,
        ),
        OPENAI_COMPATIBLE_SERVER_MODULE_ID: (
            ServerModuleDescriptor(
                module_id=OPENAI_COMPATIBLE_SERVER_MODULE_ID,
                module_version="1",
                provider_slugs=frozenset(),
                provider_kinds=frozenset({"openai_compatible"}),
            ),
            _openai_compatible_factory,
        ),
        FACIAL_SCORING_SERVER_MODULE_ID: (
            ServerModuleDescriptor(
                module_id=FACIAL_SCORING_SERVER_MODULE_ID,
                module_version="1",
                provider_slugs=frozenset({"facial_scoring"}),
                provider_kinds=frozenset({"module"}),
            ),
            _facial_scoring_factory,
        ),
    }
)

CLIENT_SERVER_COMPATIBILITY = frozenset(
    ClientServerPair(DEFAULT_CLIENT_MODULE_ID, module_id)
    for module_id in SERVER_MODULE_REGISTRY
)


def get_server_module(module_id: str) -> ServerModuleDescriptor:
    """Return a reviewed descriptor by static identifier."""
    entry = SERVER_MODULE_REGISTRY.get(module_id)
    if entry is None:
        raise ModuleSelectionError("Server module is not registered", error_code="unsupported_server_module")
    return entry[0]


def resolve_server_module(provider: str, provider_kind: str | None) -> ServerModuleDescriptor:
    """Resolve provider configuration to one static server descriptor."""
    normalized_provider = provider.strip().lower() if isinstance(provider, str) else ""
    normalized_kind = provider_kind.strip() if isinstance(provider_kind, str) else ""
    for descriptor, _factory in SERVER_MODULE_REGISTRY.values():
        if normalized_kind in descriptor.provider_kinds and (
            not descriptor.provider_slugs or normalized_provider in descriptor.provider_slugs
        ):
            return descriptor
    if normalized_kind == "module":
        raise ProviderConfigurationError(
            "The configured native module is not registered",
            provider=normalized_provider or None,
            error_code="unsupported_module",
        )
    raise ProviderConfigurationError(
        "Unsupported provider configured for route",
        provider=normalized_provider or None,
        error_code="unsupported_provider",
    )


def ensure_client_server_pair(client_module_id: str, server_module_id: str) -> None:
    """Fail closed when the static compatibility registry has no pair."""
    pair = ClientServerPair(client_module_id, server_module_id)
    if pair not in CLIENT_SERVER_COMPATIBILITY:
        raise ProviderConfigurationError(
            "The selected client and server modules are incompatible",
            provider=server_module_id,
            error_code="incompatible_module_pair",
        )


def build_server_adapter(
    descriptor: ServerModuleDescriptor,
    settings: object,
    *,
    provider_name: str,
    api_key: str,
    base_url: str | None,
    timeout_seconds: int | None,
    max_retries: int,
) -> object:
    """Build an adapter through the descriptor's single static factory."""
    entry = SERVER_MODULE_REGISTRY.get(descriptor.module_id)
    if entry is None or entry[0] != descriptor:
        raise ProviderConfigurationError(
            "The selected server module is not registered",
            provider=provider_name,
            error_code="unsupported_server_module",
        )
    factory = entry[1]
    kwargs: dict[str, object] = {
        "api_key": api_key,
        "timeout_seconds": timeout_seconds or (300 if descriptor.module_id == FACIAL_SCORING_SERVER_MODULE_ID else None),
        "max_retries": max_retries,
        "provider_name": provider_name,
    }
    if base_url is not None:
        kwargs["base_url"] = base_url
    return factory(settings, **kwargs)
