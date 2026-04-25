from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.crypto import hmac_sha256_token
from slaif_gateway.utils.secrets import generate_secret_key

_DISALLOWED_IMPORT_TERMS = ("openai", "openrouter", "aiosmtplib", "celery", "fastapi")


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


def test_hmac_digest_is_not_raw_token() -> None:
    token = "sk-slaif-public.secret"
    digest = hmac_sha256_token(token, "h" * 64)

    assert digest != token
    assert len(digest) == 64
