"""Static contract and dispatch boundary for native downstream modules.

Modules are deliberately not a plugin system. The registry is populated only
by reviewed source code, and this objective registers no module. Configuration
values never select an import path or a user-supplied class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

from slaif_gateway.config import Settings
from slaif_gateway.providers.base import ProviderAdapter
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.schemas.providers import ProviderRequest

if TYPE_CHECKING:
    from slaif_gateway.schemas.providers import ProviderResponse


class ModuleAdapter(ProviderAdapter, ABC):
    """Minimal native-module adapter contract.

    Authentication, policy, quota, accounting, audit, and content retention
    remain gateway responsibilities. A module receives only the existing safe
    ``ProviderRequest`` envelope and returns the existing safe response type.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        self._provider_name = provider_name
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    @abstractmethod
    def module_id(self) -> str:
        """Return the reviewed static module identifier."""

    @abstractmethod
    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        """Handle one already-authorized Chat Completions request."""


ModuleAdapterFactory = Callable[..., ModuleAdapter]

# This mapping is intentionally empty until a separately reviewed module is
# implemented. Do not populate it from configuration or dynamic imports.
MODULE_ADAPTER_REGISTRY: dict[str, ModuleAdapterFactory] = {}


def get_module_adapter(
    provider: str,
    settings: Settings,
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    max_retries: int,
) -> ModuleAdapter:
    """Build a statically registered module adapter or fail closed."""
    _ = settings
    factory = MODULE_ADAPTER_REGISTRY.get(provider)
    if factory is None:
        raise ProviderConfigurationError(
            "The configured native module is not registered",
            provider=provider,
            error_code="unsupported_module",
        )
    # The provider factory resolves the configured environment variable before
    # dispatch. The client Authorization token is never passed here.
    return factory(
        provider_name=provider,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
