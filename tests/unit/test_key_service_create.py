from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.crypto import hmac_sha256_token, parse_gateway_key_public_id
from slaif_gateway.utils.secrets import EncryptedSecret, decrypt_secret, generate_secret_key


@dataclass
class _FakeGatewayKeyRow:
    id: uuid.UUID


@dataclass
class _FakeOneTimeSecretRow:
    id: uuid.UUID


class _FakeGatewayKeysRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_gateway_key_record(self, **kwargs: object) -> _FakeGatewayKeyRow:
        self.calls.append(kwargs)
        return _FakeGatewayKeyRow(id=uuid.uuid4())


class _FakeOneTimeSecretsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_one_time_secret(self, **kwargs: object) -> _FakeOneTimeSecretRow:
        self.calls.append(kwargs)
        return _FakeOneTimeSecretRow(id=uuid.uuid4())


class _FakeAuditRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_create_gateway_key_happy_path_encrypts_and_audits() -> None:
    encryption_key = generate_secret_key()
    settings = Settings(
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=encryption_key,
        ONE_TIME_SECRET_KEY_VERSION="v1",
        GATEWAY_KEY_PREFIX="sk-slaif-",
    )
    keys_repo = _FakeGatewayKeysRepository()
    one_time_repo = _FakeOneTimeSecretsRepository()
    audit_repo = _FakeAuditRepository()
    service = KeyService(
        settings=settings,
        gateway_keys_repository=keys_repo,
        one_time_secrets_repository=one_time_repo,
        audit_repository=audit_repo,
    )

    payload = CreateGatewayKeyInput(
        owner_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        created_by_admin_id=uuid.uuid4(),
        valid_from=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(days=30),
        cost_limit_eur=Decimal("50.0"),
        token_limit_total=100_000,
        request_limit_total=1_000,
        allowed_models=["gpt-4.1-mini"],
        allowed_endpoints=["/v1/chat/completions"],
        rate_limit_policy={"requests_per_minute": 60, "tokens_per_minute": 12000},
        note="initial creation",
    )

    result = await service.create_gateway_key(payload)

    assert result.plaintext_key.startswith("sk-slaif-")
    assert result.public_key_id == parse_gateway_key_public_id(result.plaintext_key, ("sk-slaif-",))

    key_call = keys_repo.calls[0]
    assert key_call["key_prefix"] == "sk-slaif"
    assert key_call["token_hash"] != result.plaintext_key
    assert len(str(key_call["token_hash"])) == 64
    assert key_call["token_hash"] == hmac_sha256_token(result.plaintext_key, "h" * 48)
    assert "plaintext_key" not in key_call

    one_time_call = one_time_repo.calls[0]
    assert one_time_call["encrypted_payload"]
    assert one_time_call["nonce"]
    assert "plaintext_key" not in one_time_call
    assert "raw_secret" not in one_time_call

    decrypted = decrypt_secret(
        EncryptedSecret(
            ciphertext=str(one_time_call["encrypted_payload"]),
            nonce=str(one_time_call["nonce"]),
        ),
        encryption_key,
    )
    decrypted_payload = json.loads(decrypted.decode("utf-8"))
    assert decrypted_payload["plaintext_key"] == result.plaintext_key

    assert len(audit_repo.calls) == 1
    audit_call = audit_repo.calls[0]
    serialized_audit = json.dumps(audit_call, default=str)
    assert result.plaintext_key not in serialized_audit
    assert str(key_call["token_hash"]) not in serialized_audit
    assert str(one_time_call["encrypted_payload"]) not in serialized_audit
    assert str(one_time_call["nonce"]) not in serialized_audit
