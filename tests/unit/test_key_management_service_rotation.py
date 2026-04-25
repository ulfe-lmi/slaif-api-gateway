from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.schemas.keys import RotateGatewayKeyInput
from slaif_gateway.services.key_errors import GatewayKeyRotationError
from slaif_gateway.utils.crypto import hmac_sha256_token, parse_gateway_key_public_id
from slaif_gateway.utils.secrets import EncryptedSecret, decrypt_secret
from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service


pytestmark = pytest.mark.asyncio


async def test_rotation_returns_new_plaintext_once_and_persists_only_digest() -> None:
    old_key = FakeGatewayKeyRow(
        status="active",
        cost_limit_eur=Decimal("20.000000000"),
        token_limit_total=20_000,
        request_limit_total=200,
        allowed_models=["anthropic/claude-test"],
        allowed_endpoints=["/v1/chat/completions", "/v1/models"],
    )
    service, keys_repo, one_time_repo, audit_repo, encryption_key = make_key_service(old_key)

    result = await service.rotate_gateway_key(
        RotateGatewayKeyInput(gateway_key_id=old_key.id, reason="replacement")
    )

    assert result.new_plaintext_key.startswith("sk-slaif-")
    assert result.new_public_key_id == parse_gateway_key_public_id(
        result.new_plaintext_key,
        ("sk-slaif-",),
    )
    assert result.old_status == "revoked"
    assert result.new_status == "active"
    assert old_key.status == "revoked"

    create_call = keys_repo.created_calls[0]
    assert create_call["token_hash"] == hmac_sha256_token(result.new_plaintext_key, "h" * 48)
    assert create_call["token_hash"] != result.new_plaintext_key
    assert len(str(create_call["token_hash"])) == 64
    assert "plaintext_key" not in create_call
    assert create_call["cost_limit_eur"] == Decimal("20.000000000")
    assert create_call["allowed_models"] == ["anthropic/claude-test"]
    assert create_call["allowed_endpoints"] == ["/v1/chat/completions", "/v1/models"]

    one_time_call = one_time_repo.calls[0]
    assert one_time_call["purpose"] == "gateway_key_rotation_email"
    assert one_time_call["gateway_key_id"] == result.new_gateway_key_id
    assert one_time_call["encrypted_payload"]
    assert one_time_call["nonce"]
    assert "plaintext_key" not in one_time_call

    decrypted = decrypt_secret(
        EncryptedSecret(
            ciphertext=str(one_time_call["encrypted_payload"]),
            nonce=str(one_time_call["nonce"]),
        ),
        encryption_key,
    )
    decrypted_payload = json.loads(decrypted.decode("utf-8"))
    assert decrypted_payload["plaintext_key"] == result.new_plaintext_key
    assert decrypted_payload["public_key_id"] == result.new_public_key_id
    assert decrypted_payload["gateway_key_id"] == str(result.new_gateway_key_id)
    assert decrypted_payload["old_gateway_key_id"] == str(old_key.id)

    serialized_audit = json.dumps(audit_repo.calls, default=str)
    assert result.new_plaintext_key not in serialized_audit
    assert str(create_call["token_hash"]) not in serialized_audit
    assert str(one_time_call["encrypted_payload"]) not in serialized_audit
    assert str(one_time_call["nonce"]) not in serialized_audit
    assert "encrypted_payload" not in serialized_audit
    assert "nonce" not in serialized_audit
    assert not hasattr(result, "token_hash")


async def test_rotation_can_leave_old_key_active_when_requested() -> None:
    old_key = FakeGatewayKeyRow(status="active")
    service, keys_repo, _, audit_repo, _ = make_key_service(old_key)

    result = await service.rotate_gateway_key(
        RotateGatewayKeyInput(gateway_key_id=old_key.id, revoke_old_key=False)
    )

    assert result.old_status == "active"
    assert old_key.status == "active"
    assert keys_repo.status_calls == []
    assert audit_repo.calls[0]["new_values"]["old_key_revoked"] is False


async def test_rotation_can_override_validity_and_drop_preserved_policies() -> None:
    now = datetime.now(UTC)
    old_key = FakeGatewayKeyRow(
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        cost_limit_eur=Decimal("10.000000000"),
        token_limit_total=100,
        request_limit_total=10,
        allowed_models=["gpt-test-mini"],
        allowed_endpoints=["/v1/chat/completions"],
        rate_limit_requests_per_minute=15,
    )
    service, keys_repo, _, _, _ = make_key_service(old_key)

    await service.rotate_gateway_key(
        RotateGatewayKeyInput(
            gateway_key_id=old_key.id,
            new_valid_from=now,
            new_valid_until=now + timedelta(days=7),
            preserve_limits=False,
            preserve_allowed_models=False,
            preserve_allowed_endpoints=False,
            preserve_rate_limit_policy=False,
        )
    )

    create_call = keys_repo.created_calls[0]
    assert create_call["valid_from"] == now
    assert create_call["valid_until"] == now + timedelta(days=7)
    assert create_call["cost_limit_eur"] is None
    assert create_call["token_limit_total"] is None
    assert create_call["request_limit_total"] is None
    assert create_call["allowed_models"] == []
    assert create_call["allowed_endpoints"] == []
    assert create_call["rate_limit_requests_per_minute"] is None


async def test_rotation_of_revoked_key_fails() -> None:
    revoked = FakeGatewayKeyRow(status="revoked")
    service, keys_repo, one_time_repo, audit_repo, _ = make_key_service(revoked)

    with pytest.raises(GatewayKeyRotationError):
        await service.rotate_gateway_key(RotateGatewayKeyInput(gateway_key_id=revoked.id))

    assert keys_repo.created_calls == []
    assert one_time_repo.calls == []
    assert audit_repo.calls == []
