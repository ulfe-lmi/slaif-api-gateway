from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, RotateGatewayKeyInput
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.crypto import hmac_sha256_token
from slaif_gateway.utils.secrets import generate_secret_key
from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service

_DISALLOWED_IMPORT_TERMS = (
    "openai",
    "openrouter",
    "aiosmtplib",
    "celery",
    "fastapi",
    "redis",
    "dashboard",
    "create_async_engine",
    "get_sessionmaker",
)


class _NoopRepo:
    async def create_gateway_key_record(self, **kwargs: object):
        return type("Row", (), {"id": uuid.uuid4()})()

    async def create_one_time_secret(self, **kwargs: object):
        return type("Row", (), {"id": uuid.uuid4()})()

    async def add_audit_log(self, **kwargs: object):
        return None


@pytest.mark.asyncio
async def test_create_gateway_key_requires_token_hmac_secret() -> None:
    service = KeyService(
        settings=Settings(ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key()),
        gateway_keys_repository=_NoopRepo(),
        one_time_secrets_repository=_NoopRepo(),
        audit_repository=_NoopRepo(),
    )
    payload = CreateGatewayKeyInput(
        owner_id=uuid.uuid4(),
        valid_from=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(days=7),
    )

    with pytest.raises(ValueError, match="TOKEN_HMAC_SECRET_V1"):
        await service.create_gateway_key(payload)


@pytest.mark.asyncio
async def test_create_gateway_key_requires_one_time_secret_encryption_key() -> None:
    service = KeyService(
        settings=Settings(TOKEN_HMAC_SECRET_V1="h" * 64),
        gateway_keys_repository=_NoopRepo(),
        one_time_secrets_repository=_NoopRepo(),
        audit_repository=_NoopRepo(),
    )
    payload = CreateGatewayKeyInput(
        owner_id=uuid.uuid4(),
        valid_from=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(days=7),
    )

    with pytest.raises(ValueError, match="ONE_TIME_SECRET_ENCRYPTION_KEY"):
        await service.create_gateway_key(payload)


def test_key_service_module_does_not_import_disallowed_runtime_layers() -> None:
    import slaif_gateway.services.key_service as key_service_module

    source = inspect.getsource(key_service_module)
    import_lines = [
        line.strip().lower() for line in source.splitlines() if line.strip().startswith(("import ", "from "))
    ]

    for line in import_lines:
        for term in _DISALLOWED_IMPORT_TERMS:
            assert term not in line, f"forbidden import term '{term}' in key_service: {line}"


def test_key_service_module_does_not_own_transaction_boundaries() -> None:
    import slaif_gateway.services.key_service as key_service_module

    source = inspect.getsource(key_service_module)

    assert ".commit(" not in source
    assert "create_async_engine" not in source


def test_hmac_digest_is_not_raw_token() -> None:
    token = "sk-slaif-public.secret"
    digest = hmac_sha256_token(token, "h" * 64)

    assert digest != token
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_rotation_preserves_normalized_lazy_throttling_policy() -> None:
    old_key = FakeGatewayKeyRow(
        status="active",
        metadata_json={
            "lazy_throttling_policy": {
                "mode": "wait",
                "max_wait_seconds": 45,
                "max_waiting_requests": 3,
            },
            "rate_limit_policy": {"window_seconds": 30},
        },
    )
    service, keys_repo, _, _, _ = make_key_service(old_key)

    await service.rotate_gateway_key(
        RotateGatewayKeyInput(gateway_key_id=old_key.id, reason="replacement")
    )

    create_call = keys_repo.created_calls[0]
    assert create_call["metadata_json"]["lazy_throttling_policy"] == {
        "mode": "wait",
        "max_wait_seconds": 45,
        "max_waiting_requests": 3,
    }
    assert create_call["rate_limit_requests_per_minute"] == old_key.rate_limit_requests_per_minute


@pytest.mark.asyncio
async def test_rotation_without_preserve_rate_policy_removes_lazy_throttling_policy() -> None:
    old_key = FakeGatewayKeyRow(
        status="active",
        metadata_json={
            "lazy_throttling_policy": {
                "mode": "wait",
                "max_wait_seconds": 45,
                "max_waiting_requests": 3,
            }
        },
    )
    service, keys_repo, _, _, _ = make_key_service(old_key)

    await service.rotate_gateway_key(
        RotateGatewayKeyInput(
            gateway_key_id=old_key.id,
            reason="replacement",
            preserve_rate_limit_policy=False,
        )
    )

    assert "lazy_throttling_policy" not in keys_repo.created_calls[0]["metadata_json"]


@pytest.mark.asyncio
async def test_rotation_preserve_rate_policy_never_propagates_malformed_lazy_policy() -> None:
    old_key = FakeGatewayKeyRow(
        status="active",
        metadata_json={
            "lazy_throttling_policy": {
                "mode": "wait",
                "synthetic_only_marker": "never-propagated",
            }
        },
    )
    service, keys_repo, _, _, _ = make_key_service(old_key)

    await service.rotate_gateway_key(
        RotateGatewayKeyInput(gateway_key_id=old_key.id, reason="replacement")
    )

    assert "lazy_throttling_policy" not in keys_repo.created_calls[0]["metadata_json"]


@pytest.mark.asyncio
async def test_rotation_preserve_rate_policy_ignores_stored_reject_mode_lazy_policy() -> None:
    old_key = FakeGatewayKeyRow(
        status="active",
        metadata_json={
            "lazy_throttling_policy": {
                "mode": "reject",
                "max_wait_seconds": 5,
                "max_waiting_requests": 1,
            }
        },
    )
    service, keys_repo, _, _, _ = make_key_service(old_key)

    await service.rotate_gateway_key(
        RotateGatewayKeyInput(gateway_key_id=old_key.id, reason="replacement")
    )

    assert "lazy_throttling_policy" not in keys_repo.created_calls[0]["metadata_json"]
