from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.auth_service import (
    GatewayAuthService,
    GatewayKeyDigestMismatchError,
    GatewayKeyExpiredError,
    GatewayKeyNotFoundError,
    GatewayKeyNotYetValidError,
    GatewayKeyRevokedError,
    GatewayKeySuspendedError,
    InvalidAuthorizationSchemeError,
    MalformedGatewayKeyError,
    MissingAuthorizationError,
    MissingTokenHmacSecretError,
)
from slaif_gateway.utils.crypto import hmac_sha256_token

LONG_SECRET = "s" * 43


@dataclass
class _FakeGatewayKey:
    id: uuid.UUID
    owner_id: uuid.UUID
    public_key_id: str
    token_hash: str
    hmac_key_version: int
    status: str
    valid_from: datetime
    valid_until: datetime
    cohort_id: uuid.UUID | None = None
    allow_all_models: bool = False
    allowed_models: list[str] = field(default_factory=list)
    allow_all_endpoints: bool = False
    allowed_endpoints: list[str] = field(default_factory=list)
    metadata_json: dict[str, object] = field(default_factory=dict)
    cost_limit_eur: Decimal | None = None
    token_limit_total: int | None = None
    request_limit_total: int | None = None
    rate_limit_requests_per_minute: int | None = None
    rate_limit_tokens_per_minute: int | None = None
    max_concurrent_requests: int | None = None
    last_used_at: datetime | None = None


class _FakeGatewayKeysRepository:
    def __init__(self, gateway_key: _FakeGatewayKey | None) -> None:
        self._gateway_key = gateway_key
        self.lookup_calls: list[str] = []

    async def get_gateway_key_by_public_key_id(self, public_key_id: str) -> _FakeGatewayKey | None:
        self.lookup_calls.append(public_key_id)
        return self._gateway_key


@pytest.mark.asyncio
async def test_authenticate_authorization_header_happy_path_returns_safe_context() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(token, "h" * 48),
        hmac_key_version=1,
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allowed_models=["gpt-4.1-mini"],
        allowed_endpoints=["/v1/chat/completions"],
        metadata_json={"allowed_providers": ["openai"]},
        cost_limit_eur=Decimal("5"),
        token_limit_total=1000,
        request_limit_total=100,
        rate_limit_requests_per_minute=60,
    )
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48, TOKEN_HMAC_KEY_VERSION="v1"),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )

    result = await service.authenticate_authorization_header(f"Bearer {token}", now=now)

    assert result.public_key_id == row.public_key_id
    assert result.allowed_providers == ("openai",)
    assert result.rate_limit_policy["requests_per_minute"] == 60
    assert not hasattr(result, "plaintext_key")
    assert not hasattr(result, "token_hash")


@pytest.mark.asyncio
async def test_missing_header_raises_missing_authorization_error() -> None:
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(None),
    )
    with pytest.raises(MissingAuthorizationError):
        await service.authenticate_authorization_header(None)


@pytest.mark.asyncio
async def test_wrong_scheme_raises_invalid_authorization_scheme_error() -> None:
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(None),
    )
    with pytest.raises(InvalidAuthorizationSchemeError):
        await service.authenticate_authorization_header("Basic abc")


@pytest.mark.asyncio
async def test_empty_bearer_token_raises_malformed_gateway_key_error() -> None:
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(None),
    )
    with pytest.raises(MalformedGatewayKeyError):
        await service.authenticate_authorization_header("Bearer   ")


@pytest.mark.asyncio
async def test_malformed_gateway_key_raises_malformed_gateway_key_error() -> None:
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(None),
    )
    with pytest.raises(MalformedGatewayKeyError):
        await service.authenticate_authorization_header("Bearer not-a-gateway-key")


@pytest.mark.asyncio
async def test_unknown_public_key_id_raises_gateway_key_not_found_error() -> None:
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(None),
    )
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    with pytest.raises(GatewayKeyNotFoundError):
        await service.authenticate_authorization_header(f"Bearer {token}")


@pytest.mark.asyncio
async def test_digest_mismatch_raises_gateway_key_digest_mismatch_error() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(f"sk-ulfe-public1234abcd.{'t'*43}", "h" * 48),
        hmac_key_version=1,
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
    )
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )
    with pytest.raises(GatewayKeyDigestMismatchError):
        await service.authenticate_authorization_header(f"Bearer {token}", now=now)


@pytest.mark.asyncio
async def test_missing_hmac_secret_raises_missing_token_hmac_secret_error() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(token, "h" * 48),
        hmac_key_version=1,
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
    )
    service = GatewayAuthService(
        settings=Settings(),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )
    with pytest.raises(MissingTokenHmacSecretError):
        await service.authenticate_authorization_header(f"Bearer {token}", now=now)


@pytest.mark.asyncio
async def test_suspended_key_raises_gateway_key_suspended_error() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(token, "h" * 48),
        hmac_key_version=1,
        status="suspended",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
    )
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )
    with pytest.raises(GatewayKeySuspendedError):
        await service.authenticate_authorization_header(f"Bearer {token}", now=now)


@pytest.mark.asyncio
async def test_revoked_key_raises_gateway_key_revoked_error() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(token, "h" * 48),
        hmac_key_version=1,
        status="revoked",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
    )
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )
    with pytest.raises(GatewayKeyRevokedError):
        await service.authenticate_authorization_header(f"Bearer {token}", now=now)


@pytest.mark.asyncio
async def test_key_before_valid_from_raises_not_yet_valid_error() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(token, "h" * 48),
        hmac_key_version=1,
        status="active",
        valid_from=now + timedelta(minutes=2),
        valid_until=now + timedelta(minutes=30),
    )
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )
    with pytest.raises(GatewayKeyNotYetValidError):
        await service.authenticate_authorization_header(f"Bearer {token}", now=now)


@pytest.mark.asyncio
async def test_key_at_or_after_valid_until_raises_expired_error() -> None:
    token = f"sk-ulfe-public1234abcd.{LONG_SECRET}"
    now = datetime.now(UTC)
    row = _FakeGatewayKey(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        public_key_id="public1234abcd",
        token_hash=hmac_sha256_token(token, "h" * 48),
        hmac_key_version=1,
        status="active",
        valid_from=now - timedelta(minutes=30),
        valid_until=now,
    )
    service = GatewayAuthService(
        settings=Settings(TOKEN_HMAC_SECRET="h" * 48),
        gateway_keys_repository=_FakeGatewayKeysRepository(row),
    )
    with pytest.raises(GatewayKeyExpiredError):
        await service.authenticate_authorization_header(f"Bearer {token}", now=now)
