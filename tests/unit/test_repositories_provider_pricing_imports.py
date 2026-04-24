"""Unit checks for provider/routing/pricing/fx repository module imports and construction."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

from slaif_gateway.db.repositories import (
    FxRatesRepository,
    ModelRoutesRepository,
    PricingRulesRepository,
    ProviderConfigsRepository,
)


def test_provider_pricing_repository_modules_import_and_construct() -> None:
    session = AsyncMock()

    repositories = [
        ProviderConfigsRepository(session),
        ModelRoutesRepository(session),
        PricingRulesRepository(session),
        FxRatesRepository(session),
    ]

    assert len(repositories) == 4


def test_provider_pricing_repository_methods_are_async() -> None:
    for repository_cls in (
        ProviderConfigsRepository,
        ModelRoutesRepository,
        PricingRulesRepository,
        FxRatesRepository,
    ):
        async_methods = [
            name
            for name, member in inspect.getmembers(repository_cls, predicate=inspect.iscoroutinefunction)
            if not name.startswith("_")
        ]
        assert async_methods


def test_provider_pricing_repository_constructors_accept_injected_session() -> None:
    for repository_cls in (
        ProviderConfigsRepository,
        ModelRoutesRepository,
        PricingRulesRepository,
        FxRatesRepository,
    ):
        signature = inspect.signature(repository_cls.__init__)
        assert "session" in signature.parameters
