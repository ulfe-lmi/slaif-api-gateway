"""Static server-module descriptors and one production adapter dispatch path."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from slaif_gateway.modules.contracts import (
    DEFAULT_CLIENT_MODULE_ID,
    ClientServerPair,
    ModuleSelectionError,
    ServerModuleDescriptor,
)
from slaif_gateway.modules.servers.completion_service import CompletionServiceAdapter
from slaif_gateway.modules.servers.completion_service.profiles import (
    MODULE_ID as COMPLETION_SERVICE_MODULE_ID, load_profile, load_bindings, resolve_profile_id,
)
from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_ROUTE_CAPABILITY_KEY,
    LOCAL_CODING_SERVER_MODULE_ID,
    LOCAL_CODING_SERVER_MODULE_VERSION,
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.local_coding_vllm.adapter import LocalCodingVLLMAdapter
from slaif_gateway.modules.servers.local_coding_vllm.contract import (
    VLLM_SERVER_MODULE_ID, VLLM_ROUTE_CAPABILITY_KEY, parse_vllm_route_contract,
)
from slaif_gateway.modules.servers.vllm_chat_video import MODULE_ID as VIDEO_MODULE_ID, CAPABILITY_KEY as VIDEO_CAPABILITY_KEY, VLLMChatVideoAdapter, parse_video_frames
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.providers.openai_compatible import OpenAICompatibleProviderAdapter
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter

OPENAI_SERVER_MODULE_ID = "openai"
OPENROUTER_SERVER_MODULE_ID = "openrouter"
OPENAI_COMPATIBLE_SERVER_MODULE_ID = "openai-compatible"


def _openai_factory(settings: object, **kwargs: object) -> object:
    return OpenAIProviderAdapter(settings, **kwargs)


def _openrouter_factory(settings: object, **kwargs: object) -> object:
    kwargs.pop("provider_name", None)
    return OpenRouterProviderAdapter(settings, **kwargs)


def _openai_compatible_factory(settings: object, **kwargs: object) -> object:
    return OpenAICompatibleProviderAdapter(settings, **kwargs)


def _completion_service_factory(settings: object, **kwargs: object) -> object:
    _ = settings
    return CompletionServiceAdapter(**kwargs)


def _local_coding_factory(settings: object, **kwargs: object) -> object:
    return LocalCodingAdapter(settings, **kwargs)


def _vllm_factory(settings: object, **kwargs: object) -> object:
    return LocalCodingVLLMAdapter(settings, **kwargs)


def _video_factory(settings: object, **kwargs: object) -> object:
    return VLLMChatVideoAdapter(settings, **kwargs)


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
        COMPLETION_SERVICE_MODULE_ID: (
            ServerModuleDescriptor(
                module_id=COMPLETION_SERVICE_MODULE_ID, module_version="1",
                provider_slugs=frozenset(), provider_kinds=frozenset({"module"}),
            ),
            _completion_service_factory,
        ),
        VIDEO_MODULE_ID: (
            ServerModuleDescriptor(module_id=VIDEO_MODULE_ID, module_version="1", provider_slugs=frozenset(), provider_kinds=frozenset({"openai_compatible"})),
            _video_factory,
        ),
        VLLM_SERVER_MODULE_ID: (
            ServerModuleDescriptor(module_id=VLLM_SERVER_MODULE_ID, module_version="1",
                                   provider_slugs=frozenset(), provider_kinds=frozenset({"openai_compatible"})),
            _vllm_factory,
        ),
        LOCAL_CODING_SERVER_MODULE_ID: (
            ServerModuleDescriptor(
                module_id=LOCAL_CODING_SERVER_MODULE_ID,
                module_version=LOCAL_CODING_SERVER_MODULE_VERSION,
                provider_slugs=frozenset(),
                provider_kinds=frozenset({"openai_compatible"}),
            ),
            _local_coding_factory,
        ),
    }
)

CLIENT_SERVER_COMPATIBILITY = frozenset(
    {
        *(
            ClientServerPair(DEFAULT_CLIENT_MODULE_ID, module_id)
            for module_id in SERVER_MODULE_REGISTRY
        ),
        ClientServerPair("codex-0.147-responses-v1", OPENAI_SERVER_MODULE_ID),
        ClientServerPair(DEFAULT_CLIENT_MODULE_ID, LOCAL_CODING_SERVER_MODULE_ID),
        ClientServerPair("codex-0.149-responses-v1", LOCAL_CODING_SERVER_MODULE_ID),
        ClientServerPair("codex-0.162-responses-v1", LOCAL_CODING_SERVER_MODULE_ID),
        ClientServerPair("codex-0.162-responses-v1", VLLM_SERVER_MODULE_ID),
    }
)


def get_server_module(module_id: str) -> ServerModuleDescriptor:
    """Return a reviewed descriptor by static identifier."""
    entry = SERVER_MODULE_REGISTRY.get(module_id)
    if entry is None:
        raise ModuleSelectionError("Server module is not registered", error_code="unsupported_server_module")
    return entry[0]


def resolve_server_module(
    provider: str,
    provider_kind: str | None,
    route_capabilities: Mapping[str, object] | None = None,
) -> ServerModuleDescriptor:
    """Resolve provider configuration to one static server descriptor."""
    normalized_provider = provider.strip().lower() if isinstance(provider, str) else ""
    normalized_kind = provider_kind.strip() if isinstance(provider_kind, str) else ""
    has_profile = isinstance(route_capabilities, Mapping) and "completion_service" in route_capabilities
    if has_profile or (normalized_kind == "module" and normalized_provider in load_bindings().providers):
        if normalized_kind != "module" or any(
            key in (route_capabilities or {}) for key in (VLLM_ROUTE_CAPABILITY_KEY, LOCAL_CODING_ROUTE_CAPABILITY_KEY, VIDEO_CAPABILITY_KEY)
        ):
            raise ProviderConfigurationError(error_code="completion_service_profile_invalid")
        resolve_profile_id(normalized_provider, route_capabilities)
        return SERVER_MODULE_REGISTRY[COMPLETION_SERVICE_MODULE_ID][0]

    if isinstance(route_capabilities, Mapping) and VIDEO_CAPABILITY_KEY in route_capabilities:
        try:
            if normalized_kind != "openai_compatible":
                raise ValueError("Native video requires compatible provider kind")
            parse_video_frames(route_capabilities)
        except ValueError as exc:
            raise ProviderConfigurationError(provider=normalized_provider or None, error_code="vllm_video_contract_invalid") from exc
        return SERVER_MODULE_REGISTRY[VIDEO_MODULE_ID][0]
    if isinstance(route_capabilities, Mapping) and VLLM_ROUTE_CAPABILITY_KEY in route_capabilities:
        try:
            if normalized_kind != "openai_compatible":
                raise ValueError("Native vLLM requires openai_compatible provider kind")
            parse_vllm_route_contract(route_capabilities)
        except ValueError as exc:
            raise ProviderConfigurationError(provider=normalized_provider or None,
                error_code="vllm_route_contract_invalid") from exc
        return SERVER_MODULE_REGISTRY[VLLM_SERVER_MODULE_ID][0]
    local_contract_present = (
        isinstance(route_capabilities, Mapping)
        and LOCAL_CODING_ROUTE_CAPABILITY_KEY in route_capabilities
    )
    if local_contract_present:
        if normalized_kind != "openai_compatible":
            raise ProviderConfigurationError(
                "Local Coding contract requires an openai_compatible provider kind",
                provider=normalized_provider or None,
                error_code="local_coding_provider_kind_invalid",
            )
        try:
            contract = parse_local_coding_route_contract(route_capabilities)
        except ValueError as exc:
            raise ProviderConfigurationError(
                "Local Coding route contract is invalid",
                provider=normalized_provider or None,
                error_code="local_coding_route_contract_invalid",
            ) from exc
        if contract is not None:
            return SERVER_MODULE_REGISTRY[LOCAL_CODING_SERVER_MODULE_ID][0]
    for descriptor, _factory in SERVER_MODULE_REGISTRY.values():
        built_in_provider = descriptor.module_id in {OPENAI_SERVER_MODULE_ID, OPENROUTER_SERVER_MODULE_ID}
        if normalized_provider in descriptor.provider_slugs and (
            normalized_kind in descriptor.provider_kinds or built_in_provider
        ):
            return descriptor
        if descriptor.module_id not in {VLLM_SERVER_MODULE_ID, VIDEO_MODULE_ID, COMPLETION_SERVICE_MODULE_ID} and not descriptor.provider_slugs and normalized_kind in descriptor.provider_kinds:
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


def ensure_client_module_has_server_pair(client_module_id: str) -> None:
    """Reject a client dialect that has no reviewed server implementation."""
    if not any(pair.client_module_id == client_module_id for pair in CLIENT_SERVER_COMPATIBILITY):
        raise ProviderConfigurationError(
            "The selected client module has no compatible server module",
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
    route_capabilities: Mapping[str, object] | None = None,
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
        "timeout_seconds": timeout_seconds or None,
        "max_retries": max_retries,
        "provider_name": provider_name,
    }
    if base_url is not None:
        kwargs["base_url"] = base_url
    if descriptor.module_id in {LOCAL_CODING_SERVER_MODULE_ID, VLLM_SERVER_MODULE_ID, VIDEO_MODULE_ID}:
        kwargs["route_capabilities"] = route_capabilities
    if descriptor.module_id == COMPLETION_SERVICE_MODULE_ID:
        profile_id = resolve_profile_id(provider_name, route_capabilities)
        profile = load_profile(
            profile_id, getattr(settings, "COMPLETION_SERVICE_PROFILE_DIR", ""),
        )
        if profile.module_id != descriptor.module_id:
            raise ProviderConfigurationError(error_code="completion_service_profile_invalid")
        kwargs["profile"] = profile
        kwargs["timeout_seconds"] = timeout_seconds or 30
    return factory(settings, **kwargs)
