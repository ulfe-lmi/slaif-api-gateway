"""PostgreSQL smoke coverage for stored Conversation reference ownership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.conversation_references import ConversationReferencesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository


@pytest.mark.asyncio
async def test_conversation_reference_repository_ownership_and_safe_metadata(
    async_test_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    institutions = InstitutionsRepository(async_test_session)
    owners = OwnersRepository(async_test_session)
    cohorts = CohortsRepository(async_test_session)
    keys = GatewayKeysRepository(async_test_session)
    references = ConversationReferencesRepository(async_test_session)

    institution = await institutions.create_institution(
        name="Conversation References Integration",
        country="SI",
    )
    owner = await owners.create_owner(
        name="Conversation",
        surname="References",
        email="conversation-reference@example.org",
        institution_id=institution.id,
    )
    cohort = await cohorts.create_cohort(name="conversation-reference")
    key = await keys.create_gateway_key_record(
        public_key_id="conversation_ref_key",
        token_hash="conversation_ref_hash",
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )
    other_key = await keys.create_gateway_key_record(
        public_key_id="conversation_other_key",
        token_hash="conversation_other_hash",
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )

    reference = await references.create_conversation_reference(
        provider_conversation_id="conv_reference_owned",
        gateway_key_id=key.id,
        owner_id=owner.id,
        institution_id=institution.id,
        cohort_id=cohort.id,
        provider="openai",
        endpoint="/v1/conversations",
        provider_request_id="upstream-conversation-request-id",
        metadata={"prompt": "must not persist", "safe": "value"},
    )

    owned = await references.get_active_reference_for_key(
        provider_conversation_id="conv_reference_owned",
        gateway_key_id=key.id,
    )
    non_owned = await references.get_active_reference_for_key(
        provider_conversation_id="conv_reference_owned",
        gateway_key_id=other_key.id,
    )
    assert owned is not None
    assert owned.id == reference.id
    assert non_owned is None
    assert owned.provider == "openai"
    assert owned.reference_metadata == {"safe": "value"}

    await references.mark_deleted(reference, deleted_at=now)
    deleted_lookup = await references.get_active_reference_for_key(
        provider_conversation_id="conv_reference_owned",
        gateway_key_id=key.id,
    )
    assert deleted_lookup is None
