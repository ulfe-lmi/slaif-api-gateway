"""PostgreSQL persistence checks for metadata redaction."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL metadata redaction tests.",
)


@pytest.mark.asyncio
async def test_postgres_usage_and_audit_metadata_are_sanitized(
    async_test_session: AsyncSession,
) -> None:
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Metadata",
        surname="Tester",
        email=f"metadata-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    gateway_key = await GatewayKeysRepository(async_test_session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        allow_all_models=True,
        allow_all_endpoints=True,
    )

    usage = await UsageLedgerRepository(async_test_session).create_failure_record(
        request_id=f"req-{uuid.uuid4()}",
        gateway_key_id=gateway_key.id,
        endpoint="/v1/chat/completions",
        provider="openai",
        started_at=now,
        estimated_cost_eur=Decimal("0.100000000"),
        actual_cost_eur=Decimal("0"),
        actual_cost_native=Decimal("0"),
        native_currency="EUR",
        usage_raw={
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "prompt": "prompt secret",
            "nested": {
                "providerApiKey": "sk-proj-providersecret123456",
                "tokenHash": "hash-secret",
                "safe": "kept",
            },
        },
        response_metadata={
            "provider": "openai",
            "model": "gpt-test",
            "authorizationHeader": "Bearer sk-or-providersecret123",
            "request_body": {"content": "body secret"},
        },
    )
    audit = await AuditRepository(async_test_session).add_audit_log(
        action="metadata_redaction_test",
        entity_type="gateway_key",
        entity_id=gateway_key.id,
        old_values={"encryptedPayload": "payload-secret", "safe": "kept"},
        new_values={"sessionCookie": "session-secret", "provider": "openai"},
        note="key sk-acme-prod-public123.secretsecretsecret",
    )

    await async_test_session.flush()
    await async_test_session.refresh(usage)
    await async_test_session.refresh(audit)

    serialized = (
        str(usage.usage_raw)
        + str(usage.response_metadata)
        + str(audit.old_values)
        + str(audit.new_values)
        + str(audit.note)
    )

    for forbidden in (
        "prompt secret",
        "providersecret",
        "hash-secret",
        "body secret",
        "payload-secret",
        "session-secret",
        "secretsecretsecret",
    ):
        assert forbidden not in serialized
    assert usage.usage_raw["prompt_tokens"] == 1
    assert usage.usage_raw["completion_tokens"] == 2
    assert usage.usage_raw["nested"]["safe"] == "kept"
    assert usage.response_metadata["provider"] == "openai"
    assert usage.response_metadata["model"] == "gpt-test"
    assert audit.old_values["safe"] == "kept"
    assert audit.new_values["provider"] == "openai"
