from __future__ import annotations

import uuid

import pytest

from slaif_gateway.schemas.keys import UpdateGatewayKeyPolicyInput
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError

from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service


@pytest.mark.asyncio
async def test_update_gateway_key_policy_updates_only_policy_and_audits() -> None:
    row = FakeGatewayKeyRow(
        allowed_models=["old-model"],
        allowed_endpoints=["/v1/models"],
        allow_all_models=False,
        allow_all_endpoints=False,
    )
    service, keys_repo, _, audit_repo, _ = make_key_service(row)
    actor_id = uuid.uuid4()

    result = await service.update_gateway_key_policy(
        UpdateGatewayKeyPolicyInput(
            gateway_key_id=row.id,
            allowed_models=["gpt-5.2", "gpt-5.2", "gpt-5.1"],
            allowed_endpoints=["/v1/models", "/v1/chat/completions"],
            actor_admin_id=actor_id,
            reason="fix request policy",
        )
    )

    assert keys_repo.policy_calls == [
        {
            "gateway_key_id": row.id,
            "allowed_models": ["gpt-5.2", "gpt-5.1"],
            "allowed_endpoints": ["/v1/models", "/v1/chat/completions"],
            "allow_all_models": False,
            "allow_all_endpoints": False,
        }
    ]
    assert row.allowed_models == ["gpt-5.2", "gpt-5.1"]
    assert row.allowed_endpoints == ["/v1/models", "/v1/chat/completions"]
    assert row.cost_limit_eur is not None
    assert row.token_hash == "a" * 64
    assert result.allowed_models == ["gpt-5.2", "gpt-5.1"]

    audit = audit_repo.calls[-1]
    assert audit["action"] == "update_key_policy"
    assert audit["entity_id"] == row.id
    assert audit["admin_user_id"] == actor_id
    assert audit["note"] == "fix request policy"
    assert audit["old_values"]["allowed_models"] == ["old-model"]
    assert audit["new_values"]["allowed_models"] == ["gpt-5.2", "gpt-5.1"]
    assert "token_hash" not in str(audit)


@pytest.mark.asyncio
async def test_update_gateway_key_policy_requires_reason() -> None:
    row = FakeGatewayKeyRow()
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    with pytest.raises(InvalidGatewayKeyPolicyError, match="audit reason"):
        await service.update_gateway_key_policy(
            UpdateGatewayKeyPolicyInput(
                gateway_key_id=row.id,
                allowed_models=["gpt-5.2"],
                allowed_endpoints=["/v1/chat/completions"],
                reason="",
            )
        )

    assert keys_repo.policy_calls == []
    assert audit_repo.calls == []
