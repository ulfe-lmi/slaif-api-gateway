"""PostgreSQL smoke coverage for stored Responses reference ownership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.response_references import ResponseReferencesRepository


@pytest.mark.asyncio
async def test_response_reference_repository_previous_ownership_and_provider_metadata(
    async_test_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    institutions = InstitutionsRepository(async_test_session)
    owners = OwnersRepository(async_test_session)
    cohorts = CohortsRepository(async_test_session)
    keys = GatewayKeysRepository(async_test_session)
    references = ResponseReferencesRepository(async_test_session)

    institution = await institutions.create_institution(
        name="Stored Responses Integration",
        country="SI",
    )
    owner = await owners.create_owner(
        name="Stored",
        surname="Responses",
        email="stored-responses-reference@example.org",
        institution_id=institution.id,
    )
    cohort = await cohorts.create_cohort(name="stored-responses-reference")
    key = await keys.create_gateway_key_record(
        public_key_id="stored_responses_ref_key",
        token_hash="stored_responses_ref_hash",
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )
    other_key = await keys.create_gateway_key_record(
        public_key_id="stored_responses_other_key",
        token_hash="stored_responses_other_hash",
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )

    reference = await references.create_response_reference(
        provider_response_id="resp_reference_owned",
        gateway_key_id=key.id,
        owner_id=owner.id,
        institution_id=institution.id,
        cohort_id=cohort.id,
        provider="openai",
        endpoint="/v1/responses",
        requested_model="classroom-responses",
        upstream_model="gpt-5.2",
        provider_request_id="upstream-request-id",
        metadata={"prompt": "must not persist", "safe": "value"},
    )

    owned = await references.get_active_reference_for_key(
        provider_response_id="resp_reference_owned",
        gateway_key_id=key.id,
    )
    non_owned = await references.get_active_reference_for_key(
        provider_response_id="resp_reference_owned",
        gateway_key_id=other_key.id,
    )
    assert owned is not None
    assert owned.id == reference.id
    assert non_owned is None
    assert owned.provider == "openai"
    assert owned.requested_model == "classroom-responses"
    assert owned.upstream_model == "gpt-5.2"
    assert owned.reference_metadata == {"safe": "value"}

    await references.mark_deleted(reference, deleted_at=now)
    deleted_lookup = await references.get_active_reference_for_key(
        provider_response_id="resp_reference_owned",
        gateway_key_id=key.id,
    )
    assert deleted_lookup is None
