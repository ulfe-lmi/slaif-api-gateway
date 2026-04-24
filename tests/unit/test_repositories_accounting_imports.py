"""Unit checks for accounting repository module imports and construction."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

from slaif_gateway.db.repositories import QuotaReservationsRepository, UsageLedgerRepository


def test_accounting_repository_modules_import_and_construct() -> None:
    session = AsyncMock()

    repositories = [
        QuotaReservationsRepository(session),
        UsageLedgerRepository(session),
    ]

    assert len(repositories) == 2


def test_accounting_repository_methods_are_async() -> None:
    for repository_cls in (QuotaReservationsRepository, UsageLedgerRepository):
        async_methods = [
            name
            for name, member in inspect.getmembers(repository_cls, predicate=inspect.iscoroutinefunction)
            if not name.startswith("_")
        ]
        assert async_methods


def test_accounting_repository_constructors_accept_injected_session() -> None:
    for repository_cls in (QuotaReservationsRepository, UsageLedgerRepository):
        signature = inspect.signature(repository_cls.__init__)
        assert "session" in signature.parameters
