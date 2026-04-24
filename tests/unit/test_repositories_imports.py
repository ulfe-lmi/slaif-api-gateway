"""Unit checks for repository module imports and construction."""

from __future__ import annotations

from unittest.mock import AsyncMock

from slaif_gateway.db.repositories import (
    AdminSessionsRepository,
    AdminUsersRepository,
    AuditRepository,
    BackgroundJobsRepository,
    CohortsRepository,
    EmailDeliveriesRepository,
    GatewayKeysRepository,
    InstitutionsRepository,
    OneTimeSecretsRepository,
    OwnersRepository,
)


def test_repository_modules_import_and_construct() -> None:
    session = AsyncMock()

    repositories = [
        InstitutionsRepository(session),
        CohortsRepository(session),
        OwnersRepository(session),
        AdminUsersRepository(session),
        AdminSessionsRepository(session),
        GatewayKeysRepository(session),
        AuditRepository(session),
        OneTimeSecretsRepository(session),
        EmailDeliveriesRepository(session),
        BackgroundJobsRepository(session),
    ]

    assert len(repositories) == 10
