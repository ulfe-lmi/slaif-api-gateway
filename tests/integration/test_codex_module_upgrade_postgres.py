"""Real owned PostgreSQL proof for the audited Codex client-module upgrade.

Reuses the exact-ID-labelled, loopback-bound, tmpfs-backed owned PostgreSQL
16 fixture from the lazy-throttling module (created, migrated, and removed by
that fixture; no ambient TEST_DATABASE_URL or global testcontainer).  The
module-local ``migrated_postgres_url`` override lets the standard rollback
session fixture serve read-only cases, while committed-mutation, audit-failure
rollback, stale-session, and concurrent-apply evidence use separate committed
sessions with explicit cleanup.  Whole-row preservation is asserted with
SHA-256 digests so raw values never reach test output.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect as sa_inspect, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slaif_gateway.db.models import AuditLog, Cohort, GatewayKey, Institution, Owner
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.services.codex_module_upgrade import (
    CODEX_0149_V4_CLIENT_MODULE,
    UPGRADE_TARGET_CLIENT_MODULES,
    CodexModuleUpgradeError,
    mutate_codex_client_module,
)
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,
)

_REASON = "operator codex module upgrade"
_CANARY_METADATA = {"canary_policy": {"limit": 42}, "canary_flag": "preserve-me"}
# Columns whose change is legitimate: identity, the audited JSON path, and
# the ORM-managed update timestamp.  Everything else must be byte-stable.
_DIGEST_EXCLUDED_COLUMNS = frozenset({"id", "updated_at", "metadata_json"})


@pytest.fixture(scope="module")
def migrated_postgres_url(owned_pg_url: str):  # noqa: F811
    """Owned fixture already ran alembic to head; expose the same URL."""
    yield owned_pg_url


@asynccontextmanager
async def _committed_session(migrated_postgres_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
    await engine.dispose()


def _digest(values: object) -> str:
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()


async def _row_digest(migrated_postgres_url: str, key_id: uuid.UUID) -> tuple[str, str]:
    """Digest of every gateway_keys column except the excluded set."""

    async with _committed_session(migrated_postgres_url) as session:
        row = (await session.execute(select(GatewayKey).where(GatewayKey.id == key_id))).scalar_one()
        columns = [column.key for column in sa_inspect(GatewayKey).columns]
        raw_columns = {
            key: getattr(row, key) for key in columns if key not in _DIGEST_EXCLUDED_COLUMNS
        }
        metadata = dict(getattr(row, "metadata_json"))
        policy = metadata.get("responses_policy")
        if isinstance(policy, dict) and "client_module" in policy:
            metadata["responses_policy"] = {
                k: v for k, v in policy.items() if k != "client_module"
            }
        return _digest(tuple(sorted(raw_columns.items()))), _digest(metadata)


async def _seed_key(
    migrated_postgres_url: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, tuple[str, str]]:
    """Seed owner/cohort/institution/key with non-default restrictions."""

    unique = uuid.uuid4().hex
    now = datetime.now(UTC)
    institution_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    key_id = uuid.uuid4()
    async with _committed_session(migrated_postgres_url) as session:
        async with session.begin():
            institution = Institution(
                id=institution_id, name=f"SLAIF 189 upgrade {unique}", country="SI"
            )
            cohort = Cohort(
                id=cohort_id,
                name=f"189-upgrade-{unique}",
                description="audited module upgrade cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )
            owner = Owner(
                id=owner_id,
                name="Upgrade",
                surname="Probe",
                email=f"upgrade-{unique}@example.org",
                institution_id=institution_id,
                is_active=True,
            )
            key = GatewayKey(
                id=key_id,
                public_key_id=f"pub-189-{unique}",
                key_prefix="sk-slaif-test",
                key_hint="189-probe",
                token_hash=f"sha256:synthetic-{unique}",
                hash_algorithm="hmac-sha256",
                hmac_key_version=2,
                owner_id=owner_id,
                cohort_id=cohort_id,
                status="active",
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(days=7),
                cost_limit_eur=Decimal("12.500000000"),
                token_limit_total=500000,
                request_limit_total=250,
                cost_used_eur=Decimal("1.234567890"),
                tokens_used_total=1234,
                requests_used_total=7,
                rate_limit_requests_per_minute=30,
                rate_limit_tokens_per_minute=60000,
                max_concurrent_requests=4,
                allow_all_models=True,
                allowed_models=["codex-local-model-a", "codex-local-model-b"],
                allow_all_endpoints=False,
                allowed_endpoints=["/v1/responses", "/v1/responses/compact"],
                key_purpose="standard",
                metadata_json={
                    **_CANARY_METADATA,
                    "responses_policy": {
                        "version": 1,
                        "allowed_capabilities": [
                            "text",
                            "stateless",
                            "codex_request_envelope",
                            "codex_client_tools",
                        ],
                        "allowed_local_tool_types": ["function", "custom"],
                        "client_module": dict(CODEX_0149_V4_CLIENT_MODULE),
                    },
                },
            )
            session.add_all([institution, cohort, owner, key])
        return key_id, owner_id, institution_id, cohort_id, await _row_digest(
            migrated_postgres_url, key_id
        )


async def _cleanup_key(
    migrated_postgres_url: str,
    *,
    key_id: uuid.UUID,
    owner_id: uuid.UUID,
    institution_id: uuid.UUID,
    cohort_id: uuid.UUID,
) -> None:
    async with _committed_session(migrated_postgres_url) as session:
        async with session.begin():
            for model, identifier in (
                (GatewayKey, key_id),
                (Owner, owner_id),
                (Cohort, cohort_id),
                (Institution, institution_id),
            ):
                row = await session.get(model, identifier)
                if row is not None:
                    await session.delete(row)


async def _set_client_module(
    migrated_postgres_url: str,
    key_id: uuid.UUID,
    client_module: dict[str, str],
) -> None:
    async with _committed_session(migrated_postgres_url) as session:
        async with session.begin():
            row = (
                await session.execute(select(GatewayKey).where(GatewayKey.id == key_id))
            ).scalar_one()
            metadata = dict(row.metadata_json)
            policy = dict(metadata["responses_policy"])
            policy["client_module"] = client_module
            metadata["responses_policy"] = policy
            row.metadata_json = metadata


async def _audit_count(migrated_postgres_url: str, key_id: uuid.UUID) -> int:
    async with _committed_session(migrated_postgres_url) as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == key_id)
            )
            or 0
        )


async def _mutate(
    migrated_postgres_url: str,
    *,
    key_id: uuid.UUID,
    expected_source: str,
    target: str,
    action: str,
    apply: bool,
    audit_repository: object | None = None,
):
    async with _committed_session(migrated_postgres_url) as session:
        async with session.begin():
            return await mutate_codex_client_module(
                session=session,
                keys_repository=GatewayKeysRepository(session),
                audit_repository=audit_repository or AuditRepository(session),
                gateway_key_id=key_id,
                expected_source=expected_source,
                target=target,
                action=action,
                actor_admin_id=None,
                reason=_REASON,
                apply=apply,
            )


@pytest.mark.asyncio
async def test_dry_run_performs_no_write_and_no_audit(migrated_postgres_url: str) -> None:
    key_id, owner_id, institution_id, cohort_id, before_digest = await _seed_key(
        migrated_postgres_url
    )
    try:
        result = await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0149-v4",
            target="0149-v5",
            action="codex_client_module_upgraded",
            apply=False,
        )
        assert result.status == "dry_run"
        assert result.changed is False
        assert await _row_digest(migrated_postgres_url, key_id) == before_digest
        assert await _audit_count(migrated_postgres_url, key_id) == 0
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_upgrade_apply_preserves_every_other_column_and_audits(
    migrated_postgres_url: str,
) -> None:
    key_id, owner_id, institution_id, cohort_id, before_digest = await _seed_key(
        migrated_postgres_url
    )
    try:
        result = await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0149-v4",
            target="0149-v5",
            action="codex_client_module_upgraded",
            apply=True,
        )
        assert result.status == "applied"
        assert result.changed is True

        # Whole-row digest (all columns except id/updated_at/metadata_json)
        # and metadata-minus-client_module digest must be unchanged: key
        # material, restrictions, dates, status, quotas, and counters stay.
        assert await _row_digest(migrated_postgres_url, key_id) == before_digest

        assert await _audit_count(migrated_postgres_url, key_id) == 1
        async with _committed_session(migrated_postgres_url) as session:
            audit = (
                await session.execute(
                    select(AuditLog).where(AuditLog.entity_id == key_id)
                )
            ).scalar_one()
            assert audit.action == "codex_client_module_upgraded"
            assert audit.entity_type == "gateway_key"
            assert audit.old_values["client_module"] == dict(CODEX_0149_V4_CLIENT_MODULE)
            assert audit.new_values["client_module"] == dict(
                UPGRADE_TARGET_CLIENT_MODULES["0149-v5"]
            )
            assert audit.note == _REASON
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_upgrade_repeat_apply_is_noop_without_new_audit(
    migrated_postgres_url: str,
) -> None:
    key_id, owner_id, institution_id, cohort_id, _before = await _seed_key(
        migrated_postgres_url
    )
    try:
        first = await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0149-v4",
            target="0162-v1",
            action="codex_client_module_upgraded",
            apply=True,
        )
        assert first.status == "applied"
        second = await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0149-v4",
            target="0162-v1",
            action="codex_client_module_upgraded",
            apply=True,
        )
        assert second.status == "already_at_target"
        assert second.changed is False
        assert await _audit_count(migrated_postgres_url, key_id) == 1
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_rollback_apply_returns_to_frozen_v4_and_is_idempotent(
    migrated_postgres_url: str,
) -> None:
    key_id, owner_id, institution_id, cohort_id, _before = await _seed_key(
        migrated_postgres_url
    )
    try:
        await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0149-v4",
            target="0162-v1",
            action="codex_client_module_upgraded",
            apply=True,
        )
        rolled = await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0162-v1",
            target="0149-v4",
            action="codex_client_module_rolled_back",
            apply=True,
        )
        assert rolled.status == "applied"
        repeat = await _mutate(
            migrated_postgres_url,
            key_id=key_id,
            expected_source="0162-v1",
            target="0149-v4",
            action="codex_client_module_rolled_back",
            apply=True,
        )
        assert repeat.status == "already_at_target"
        assert await _audit_count(migrated_postgres_url, key_id) == 2
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drifted",
    [
        {"id": "codex-0.149-responses-v1", "version": "9", "fixture_sha256": "0" * 64},
        {
            "id": "codex-0.149-responses-v1",
            "version": "4",
            "fixture_sha256": "f" * 64,
        },
        {
            "id": "codex-0.149-responses-v1",
            "version": "4",
            "fixture_sha256": "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec",
            "extra": "field",
        },
        {"id": "codex-0.149-responses-v1", "version": "4"},
        None,
    ],
)
async def test_mismatched_or_malformed_identity_fails_closed(
    migrated_postgres_url: str, drifted: dict[str, str] | None
) -> None:
    key_id, owner_id, institution_id, cohort_id, before_digest = await _seed_key(
        migrated_postgres_url
    )
    try:
        if drifted is None:
            async with _committed_session(migrated_postgres_url) as session:
                async with session.begin():
                    await session.execute(
                        sa_update(GatewayKey)
                        .where(GatewayKey.id == key_id)
                        .values(metadata_json={**_CANARY_METADATA})
                    )
            expected_code = "codex_module_upgrade_identity_missing"
        else:
            async with _committed_session(migrated_postgres_url) as session:
                async with session.begin():
                    metadata = {
                        **_CANARY_METADATA,
                        "responses_policy": {"version": 1, "client_module": drifted},
                    }
                    await session.execute(
                        sa_update(GatewayKey)
                        .where(GatewayKey.id == key_id)
                        .values(metadata_json=metadata)
                    )
            expected_code = (
                "codex_module_upgrade_identity_invalid"
                if set(drifted) != {"id", "version", "fixture_sha256"}
                else "codex_module_upgrade_identity_mismatch"
            )
        with pytest.raises(CodexModuleUpgradeError) as exc_info:
            await _mutate(
                migrated_postgres_url,
                key_id=key_id,
                expected_source="0149-v4",
                target="0149-v5",
                action="codex_client_module_upgraded",
                apply=True,
            )
        assert exc_info.value.error_code == expected_code
        assert await _audit_count(migrated_postgres_url, key_id) == 0
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_cross_target_transitions_are_rejected(migrated_postgres_url: str) -> None:
    for expected_source, target in (
        ("0149-v5", "0162-v1"),
        ("0162-v1", "0149-v5"),
        ("0149-v4", "0149-v4"),
        ("0162-v1", "0162-v1"),
    ):
        with pytest.raises(CodexModuleUpgradeError) as exc_info:
            await _mutate(
                migrated_postgres_url,
                key_id=uuid.uuid4(),
                expected_source=expected_source,
                target=target,
                action="codex_client_module_upgraded",
                apply=True,
            )
        assert exc_info.value.error_code == "codex_module_upgrade_transition_invalid"


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_metadata_atomically(
    migrated_postgres_url: str,
) -> None:
    class _FailingAudit:
        async def add_audit_log(self, **_: object) -> None:
            raise RuntimeError("audit storage failure")

    key_id, owner_id, institution_id, cohort_id, before_digest = await _seed_key(
        migrated_postgres_url
    )
    try:
        engine = create_async_engine(migrated_postgres_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            with pytest.raises(RuntimeError, match="audit storage failure"):
                async with session.begin():
                    await mutate_codex_client_module(
                        session=session,
                        keys_repository=GatewayKeysRepository(session),
                        audit_repository=_FailingAudit(),
                        gateway_key_id=key_id,
                        expected_source="0149-v4",
                        target="0162-v1",
                        action="codex_client_module_upgraded",
                        actor_admin_id=None,
                        reason=_REASON,
                        apply=True,
                    )
        await engine.dispose()
        assert await _row_digest(migrated_postgres_url, key_id) == before_digest
        assert await _audit_count(migrated_postgres_url, key_id) == 0
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_stale_session_upgrade_preserves_concurrent_unrelated_updates(
    migrated_postgres_url: str,
) -> None:
    key_id, owner_id, institution_id, cohort_id, _before = await _seed_key(
        migrated_postgres_url
    )
    try:
        engine = create_async_engine(migrated_postgres_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as stale_session:
            # Stale, unlocked read of the V4 row.
            stale = await stale_session.get(GatewayKey, key_id)
            assert stale is not None
            await stale_session.rollback()

        # A second session commits unrelated usage/policy updates while the
        # stale view exists.
        async with _committed_session(migrated_postgres_url) as other:
            async with other.begin():
                await other.execute(
                    sa_update(GatewayKey)
                    .where(GatewayKey.id == key_id)
                    .values(tokens_used_total=99999, requests_used_total=77)
                )
                row = (
                    await other.execute(select(GatewayKey).where(GatewayKey.id == key_id))
                ).scalar_one()
                metadata = dict(row.metadata_json)
                metadata["rate_limit_policy"] = {"window_seconds": 30}
                row.metadata_json = metadata

        # The upgrade session starts from the stale identity map entry; the
        # locked populate_existing refresh must see the committed values and
        # preserve them while changing only client_module.
        async with session_factory() as stale_session:
            await stale_session.get(GatewayKey, key_id)
            await stale_session.rollback()
            async with stale_session.begin():
                result = await mutate_codex_client_module(
                    session=stale_session,
                    keys_repository=GatewayKeysRepository(stale_session),
                    audit_repository=AuditRepository(stale_session),
                    gateway_key_id=key_id,
                    expected_source="0149-v4",
                    target="0162-v1",
                    action="codex_client_module_upgraded",
                    actor_admin_id=None,
                    reason=_REASON,
                    apply=True,
                )
        await engine.dispose()
        assert result.status == "applied"
        async with _committed_session(migrated_postgres_url) as session:
            row = (
                await session.execute(select(GatewayKey).where(GatewayKey.id == key_id))
            ).scalar_one()
            assert row.tokens_used_total == 99999
            assert row.requests_used_total == 77
            assert row.metadata_json["rate_limit_policy"] == {"window_seconds": 30}
            assert row.metadata_json["responses_policy"]["client_module"] == dict(
                UPGRADE_TARGET_CLIENT_MODULES["0162-v1"]
            )
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_concurrent_duplicate_apply_yields_one_mutation_and_one_noop(
    migrated_postgres_url: str,
) -> None:
    key_id, owner_id, institution_id, cohort_id, _before = await _seed_key(
        migrated_postgres_url
    )
    try:
        first, second = await asyncio.gather(
            _mutate(
                migrated_postgres_url,
                key_id=key_id,
                expected_source="0149-v4",
                target="0162-v1",
                action="codex_client_module_upgraded",
                apply=True,
            ),
            _mutate(
                migrated_postgres_url,
                key_id=key_id,
                expected_source="0149-v4",
                target="0162-v1",
                action="codex_client_module_upgraded",
                apply=True,
            ),
        )
        statuses = sorted([first.status, second.status])
        assert statuses == ["already_at_target", "applied"]
        assert await _audit_count(migrated_postgres_url, key_id) == 1
    finally:
        await _cleanup_key(
            migrated_postgres_url,
            key_id=key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
        )


@pytest.mark.asyncio
async def test_missing_key_and_whitespace_reason_fail_closed(
    migrated_postgres_url: str,
) -> None:
    with pytest.raises(CodexModuleUpgradeError) as exc_info:
        await _mutate(
            migrated_postgres_url,
            key_id=uuid.uuid4(),
            expected_source="0149-v4",
            target="0149-v5",
            action="codex_client_module_upgraded",
            apply=True,
        )
    assert exc_info.value.error_code == "codex_module_upgrade_key_not_found"

    with pytest.raises(CodexModuleUpgradeError) as exc_info:
        async with _committed_session(migrated_postgres_url) as session:
            async with session.begin():
                await mutate_codex_client_module(
                    session=session,
                    keys_repository=GatewayKeysRepository(session),
                    audit_repository=AuditRepository(session),
                    gateway_key_id=uuid.uuid4(),
                    expected_source="0149-v4",
                    target="0149-v5",
                    action="codex_client_module_upgraded",
                    actor_admin_id=None,
                    reason="        ",
                    apply=True,
                )
    assert exc_info.value.error_code == "codex_module_upgrade_reason_invalid"
