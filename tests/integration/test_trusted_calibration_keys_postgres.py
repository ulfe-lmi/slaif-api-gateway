"""PostgreSQL checks for trusted calibration key persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)

pytestmark = pytest.mark.asyncio


def _gateway_key_columns(sync_connection) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns("gateway_keys")}


def _gateway_key_indexes(sync_connection) -> set[str]:
    return {index["name"] for index in inspect(sync_connection).get_indexes("gateway_keys")}


async def test_migration_adds_trusted_calibration_key_columns_and_indexes(
    migrated_engine,
) -> None:
    async with migrated_engine.connect() as connection:
        columns = await connection.run_sync(_gateway_key_columns)
        indexes = await connection.run_sync(_gateway_key_indexes)

    assert "key_purpose" in columns
    assert "capability_policy_mode" in columns
    assert "calibration_metadata" in columns
    assert "ix_gateway_keys_key_purpose" in indexes
    assert "ix_gateway_keys_capability_policy_mode" in indexes


async def test_repository_creates_and_reads_standard_and_trusted_calibration_keys(
    async_test_session: AsyncSession,
) -> None:
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Calibration",
        surname="Owner",
        email="calibration-owner@example.org",
    )
    now = datetime.now(UTC)
    keys = GatewayKeysRepository(async_test_session)

    standard = await keys.create_gateway_key_record(
        public_key_id="k_standard_calibration_repo",
        token_hash="standard-calibration-digest",
        owner_id=owner.id,
        valid_from=now,
        valid_until=now + timedelta(days=30),
    )
    trusted = await keys.create_gateway_key_record(
        public_key_id="k_trusted_calibration_repo",
        token_hash="trusted-calibration-digest",
        owner_id=owner.id,
        valid_from=now,
        valid_until=now + timedelta(days=2),
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
        key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
        capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        calibration_metadata={"workflow": "integration"},
    )
    await async_test_session.flush()

    stored_standard = await async_test_session.get(GatewayKey, standard.id)
    stored_trusted = await async_test_session.get(GatewayKey, trusted.id)

    assert stored_standard is not None
    assert stored_standard.key_purpose == "standard"
    assert stored_standard.capability_policy_mode == "standard"
    assert stored_trusted is not None
    assert stored_trusted.key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION
    assert (
        stored_trusted.capability_policy_mode
        == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    )
    assert stored_trusted.calibration_metadata == {"workflow": "integration"}


async def test_db_constraints_reject_invalid_purpose_and_mode(
    async_test_session: AsyncSession,
) -> None:
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Constraint",
        surname="Owner",
        email="calibration-constraint@example.org",
    )
    now = datetime.now(UTC)

    with pytest.raises(IntegrityError):
        async with async_test_session.begin_nested():
            async_test_session.add(
                GatewayKey(
                    public_key_id="k_invalid_calibration_mode",
                    token_hash="invalid-calibration-digest",
                    owner_id=owner.id,
                    valid_from=now,
                    valid_until=now + timedelta(days=1),
                    key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
                    capability_policy_mode="standard",
                    request_limit_total=5,
                )
            )
            await async_test_session.flush()


async def test_trusted_calibration_metadata_is_queryable(async_test_session: AsyncSession) -> None:
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Queryable",
        surname="Owner",
        email="calibration-query@example.org",
    )
    now = datetime.now(UTC)
    trusted = await GatewayKeysRepository(async_test_session).create_gateway_key_record(
        public_key_id="k_trusted_calibration_query",
        token_hash="trusted-calibration-query-digest",
        owner_id=owner.id,
        valid_from=now,
        valid_until=now + timedelta(days=1),
        request_limit_total=3,
        allow_all_models=True,
        allow_all_endpoints=True,
        key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
        capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        calibration_metadata={"workflow": "queryable"},
    )
    await async_test_session.flush()

    result = await async_test_session.execute(
        select(GatewayKey).where(
            GatewayKey.key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION,
            GatewayKey.calibration_metadata["workflow"].astext == "queryable",
        )
    )

    assert result.scalar_one().id == trusted.id


async def test_trusted_calibration_request_limit_constraint(async_test_session: AsyncSession) -> None:
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Limit",
        surname="Owner",
        email="calibration-limit@example.org",
    )
    now = datetime.now(UTC)

    with pytest.raises(IntegrityError):
        async with async_test_session.begin_nested():
            await async_test_session.execute(
                text(
                    """
                    INSERT INTO gateway_keys (
                        public_key_id, token_hash, owner_id, valid_from, valid_until,
                        key_purpose, capability_policy_mode
                    )
                    VALUES (
                        'k_trusted_calibration_no_limit',
                        'trusted-calibration-no-limit-digest',
                        :owner_id,
                        :valid_from,
                        :valid_until,
                        'trusted_calibration',
                        'trusted_calibration_discovery'
                    )
                    """
                ),
                {
                    "owner_id": owner.id,
                    "valid_from": now,
                    "valid_until": now + timedelta(days=1),
                },
            )
