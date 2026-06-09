from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.key_errors import (
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyPolicyError,
    InvalidGatewayKeyValidityError,
)
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.crypto import hmac_sha256_token, parse_gateway_key_public_id
from slaif_gateway.utils.secrets import EncryptedSecret, decrypt_secret, generate_secret_key


@dataclass
class _FakeGatewayKeyRow:
    id: uuid.UUID
    rate_limit_requests_per_minute: int | None = None
    rate_limit_tokens_per_minute: int | None = None
    max_concurrent_requests: int | None = None
    key_purpose: str = "standard"
    capability_policy_mode: str = "standard"
    calibration_metadata: dict[str, object] | None = None
    metadata_json: dict[str, object] | None = None


@dataclass
class _FakeOneTimeSecretRow:
    id: uuid.UUID


class _FakeGatewayKeysRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_gateway_key_record(self, **kwargs: object) -> _FakeGatewayKeyRow:
        self.calls.append(kwargs)
        return _FakeGatewayKeyRow(
            id=uuid.uuid4(),
            rate_limit_requests_per_minute=kwargs.get("rate_limit_requests_per_minute"),
            rate_limit_tokens_per_minute=kwargs.get("rate_limit_tokens_per_minute"),
            max_concurrent_requests=kwargs.get("max_concurrent_requests"),
            key_purpose=str(kwargs.get("key_purpose") or "standard"),
            capability_policy_mode=str(kwargs.get("capability_policy_mode") or "standard"),
            calibration_metadata=kwargs.get("calibration_metadata"),
            metadata_json=kwargs.get("metadata_json"),
        )


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
        rate_limit_policy={
            "requests_per_minute": 60,
            "tokens_per_minute": 12000,
            "window_seconds": 30,
        },
        note="initial creation",
    )

    result = await service.create_gateway_key(payload)

    assert result.plaintext_key.startswith("sk-slaif-")
    assert result.public_key_id == parse_gateway_key_public_id(result.plaintext_key, ("sk-slaif-",))

    key_call = keys_repo.calls[0]
    assert key_call["key_prefix"] == "sk-slaif-"
    assert key_call["token_hash"] != result.plaintext_key
    assert len(str(key_call["token_hash"])) == 64
    assert key_call["token_hash"] == hmac_sha256_token(result.plaintext_key, "h" * 48)
    assert "plaintext_key" not in key_call
    assert key_call["rate_limit_requests_per_minute"] == 60
    assert key_call["rate_limit_tokens_per_minute"] == 12000
    assert key_call["metadata_json"] == {
        "chat_streaming_live_burn": {
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
        },
        "responses_streaming_live_burn": {
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
            "token_margin": 0,
        },
        "rate_limit_policy": {"window_seconds": 30},
    }
    assert result.chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": True,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }
    assert result.rate_limit_policy == {
        "requests_per_minute": 60,
        "tokens_per_minute": 12000,
        "window_seconds": 30,
    }

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


@pytest.mark.asyncio
async def test_standard_key_defaults_to_standard_purpose_and_mode() -> None:
    service, keys_repo, _, _ = _make_service()
    payload = _base_create_payload()

    result = await service.create_gateway_key(payload)

    assert result.key_purpose == "standard"
    assert result.capability_policy_mode == "standard"
    assert keys_repo.calls[0]["key_purpose"] == "standard"
    assert keys_repo.calls[0]["capability_policy_mode"] == "standard"


@pytest.mark.asyncio
async def test_create_gateway_key_can_persist_allowed_providers_in_metadata() -> None:
    service, keys_repo, _, audit_repo = _make_service()
    payload = _base_create_payload(allowed_providers=["openai"])

    await service.create_gateway_key(payload)

    assert keys_repo.calls[0]["metadata_json"] == {
        "allowed_providers": ["openai"],
        "chat_streaming_live_burn": {
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
        },
        "responses_streaming_live_burn": {
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
            "token_margin": 0,
        },
    }
    assert audit_repo.calls[0]["new_values"]["allowed_providers"] == ["openai"]


@pytest.mark.asyncio
async def test_trusted_calibration_key_can_be_created_with_confirmation() -> None:
    service, keys_repo, _, audit_repo = _make_service()
    payload = _trusted_calibration_payload()

    result = await service.create_gateway_key(payload)

    assert result.key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION
    assert result.capability_policy_mode == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    created = keys_repo.calls[0]
    assert created["request_limit_total"] == 5
    assert created["allow_all_models"] is True
    assert created["allow_all_endpoints"] is True
    assert created["allowed_models"] == []
    assert created["allowed_endpoints"] == []
    assert created["calibration_metadata"] == {"workflow": "lesson-1"}
    audit_values = audit_repo.calls[0]["new_values"]
    assert audit_values["key_purpose"] == KEY_PURPOSE_TRUSTED_CALIBRATION
    assert "plaintext" not in json.dumps(audit_values).lower()


@pytest.mark.asyncio
async def test_trusted_calibration_key_creation_fails_without_confirmation() -> None:
    service, _, _, _ = _make_service()
    payload = _trusted_calibration_payload(confirm_trusted_calibration=False)

    with pytest.raises(InvalidGatewayKeyPolicyError, match="Confirm trusted calibration"):
        await service.create_gateway_key(payload)


@pytest.mark.asyncio
async def test_trusted_calibration_key_creation_fails_without_request_limit() -> None:
    service, _, _, _ = _make_service()
    payload = _trusted_calibration_payload(request_limit_total=None)

    with pytest.raises(InvalidGatewayKeyLimitsError, match="request_limit_total"):
        await service.create_gateway_key(payload)


@pytest.mark.asyncio
async def test_trusted_calibration_key_creation_fails_when_request_limit_too_high() -> None:
    service, _, _, _ = _make_service()
    payload = _trusted_calibration_payload(request_limit_total=11)

    with pytest.raises(InvalidGatewayKeyLimitsError, match="request limit"):
        await service.create_gateway_key(payload)


@pytest.mark.asyncio
async def test_trusted_calibration_key_creation_fails_when_validity_too_long() -> None:
    service, _, _, _ = _make_service()
    valid_from = datetime.now(UTC)
    payload = _trusted_calibration_payload(
        valid_from=valid_from,
        valid_until=valid_from + timedelta(days=8),
    )

    with pytest.raises(InvalidGatewayKeyValidityError, match="validity"):
        await service.create_gateway_key(payload)


@pytest.mark.asyncio
async def test_trusted_calibration_key_creation_requires_audit_reason() -> None:
    service, _, _, _ = _make_service()
    payload = _trusted_calibration_payload(note="")

    with pytest.raises(InvalidGatewayKeyPolicyError, match="audit reason"):
        await service.create_gateway_key(payload)


def _make_service() -> tuple[
    KeyService,
    _FakeGatewayKeysRepository,
    _FakeOneTimeSecretsRepository,
    _FakeAuditRepository,
]:
    settings = Settings(
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
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
    return service, keys_repo, one_time_repo, audit_repo


def _base_create_payload(**overrides: object) -> CreateGatewayKeyInput:
    valid_from = overrides.pop("valid_from", datetime.now(UTC))
    values = {
        "owner_id": uuid.uuid4(),
        "valid_from": valid_from,
        "valid_until": overrides.pop("valid_until", valid_from + timedelta(days=1)),
        "request_limit_total": 100,
        "allowed_models": ["gpt-4.1-mini"],
        "allowed_endpoints": ["/v1/chat/completions"],
        "note": "safe test creation",
    }
    values.update(overrides)
    return CreateGatewayKeyInput(**values)


def _trusted_calibration_payload(**overrides: object) -> CreateGatewayKeyInput:
    valid_from = overrides.pop("valid_from", datetime.now(UTC))
    values = {
        "owner_id": uuid.uuid4(),
        "valid_from": valid_from,
        "valid_until": overrides.pop("valid_until", valid_from + timedelta(days=2)),
        "request_limit_total": 5,
        "allowed_models": ["participant-model-ignored"],
        "allowed_endpoints": ["/v1/models"],
        "key_purpose": KEY_PURPOSE_TRUSTED_CALIBRATION,
        "capability_policy_mode": CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        "calibration_metadata": {"workflow": "lesson-1"},
        "confirm_trusted_calibration": True,
        "note": "trusted organizer calibration run",
    }
    values.update(overrides)
    return CreateGatewayKeyInput(**values)
