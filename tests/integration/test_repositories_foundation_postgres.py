"""Repository integration smoke checks on real PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AdminUser, GatewayKey, Institution, Owner
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository


pytestmark = pytest.mark.asyncio

async def test_foundation_repositories_create_and_read(async_test_session: AsyncSession) -> None:
    institutions = InstitutionsRepository(async_test_session)
    cohorts = CohortsRepository(async_test_session)
    owners = OwnersRepository(async_test_session)
    admins = AdminUsersRepository(async_test_session)
    gateway_keys = GatewayKeysRepository(async_test_session)

    institution = await institutions.create_institution(
        name="Integration University", country="SI", notes="integration-test"
    )
    cohort = await cohorts.create_cohort(name="integration-cohort", description="repository smoke")
    owner = await owners.create_owner(
        name="Test",
        surname="Owner",
        email="owner.integration@example.org",
        institution_id=institution.id,
    )
    admin = await admins.create_admin_user(
        email="admin.integration@example.org",
        display_name="Integration Admin",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$integration$placeholder",
    )

    now = datetime.now(UTC)
    created_key = await gateway_keys.create_gateway_key_record(
        public_key_id="k_integration_repo",
        token_hash="hmac-sha256:integration-demo-digest",
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now,
        valid_until=now + timedelta(days=30),
        created_by_admin_user_id=admin.id,
        key_hint="...demo",
    )

    await async_test_session.flush()

    stored_institution = await async_test_session.scalar(
        select(Institution).where(Institution.id == institution.id)
    )
    stored_owner = await async_test_session.scalar(select(Owner).where(Owner.id == owner.id))
    stored_admin = await async_test_session.scalar(select(AdminUser).where(AdminUser.id == admin.id))
    stored_key = await async_test_session.scalar(
        select(GatewayKey).where(GatewayKey.id == created_key.id)
    )

    assert stored_institution is not None
    assert stored_owner is not None
    assert stored_admin is not None
    assert stored_key is not None
    assert stored_key.token_hash == "hmac-sha256:integration-demo-digest"
