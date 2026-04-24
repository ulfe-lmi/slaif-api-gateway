"""Service-layer gateway key authentication and validation."""

from __future__ import annotations

from datetime import UTC, datetime

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.utils.crypto import parse_gateway_key_public_id, verify_hmac_sha256_token


class GatewayAuthError(Exception):
    """Base domain error for gateway-key authentication failures."""

    status_code = 401
    error_type = "authentication_error"
    error_code = "authentication_failed"
    message = "Authentication failed"

    def __init__(self, message: str | None = None) -> None:
        self.safe_message = message or self.message
        super().__init__(self.safe_message)


class MissingAuthorizationError(GatewayAuthError):
    error_code = "missing_authorization"
    message = "Missing Authorization header"


class InvalidAuthorizationSchemeError(GatewayAuthError):
    error_code = "invalid_authorization_scheme"
    message = "Authorization scheme must be Bearer"


class MalformedGatewayKeyError(GatewayAuthError):
    error_code = "malformed_gateway_key"
    message = "Malformed gateway key"


class GatewayKeyNotFoundError(GatewayAuthError):
    error_code = "gateway_key_not_found"
    message = "Gateway key not found"


class GatewayKeyDigestMismatchError(GatewayAuthError):
    error_code = "gateway_key_invalid_digest"
    message = "Gateway key is invalid"


class GatewayKeySuspendedError(GatewayAuthError):
    status_code = 403
    error_type = "permission_error"
    error_code = "gateway_key_suspended"
    message = "Gateway key is suspended"


class GatewayKeyRevokedError(GatewayAuthError):
    status_code = 403
    error_type = "permission_error"
    error_code = "gateway_key_revoked"
    message = "Gateway key is revoked"


class GatewayKeyExpiredError(GatewayAuthError):
    error_code = "gateway_key_expired"
    message = "Gateway key is expired"


class GatewayKeyNotYetValidError(GatewayAuthError):
    error_code = "gateway_key_not_yet_valid"
    message = "Gateway key is not yet valid"


class MissingTokenHmacSecretError(GatewayAuthError):
    status_code = 500
    error_type = "server_error"
    error_code = "missing_token_hmac_secret"
    message = "Server authentication configuration is incomplete"


class GatewayAuthService:
    """Validates Authorization Bearer headers against persisted gateway keys."""

    def __init__(self, *, settings: Settings, gateway_keys_repository: GatewayKeysRepository) -> None:
        self._settings = settings
        self._gateway_keys_repository = gateway_keys_repository

    async def authenticate_authorization_header(
        self,
        authorization_header: str | None,
        now: datetime | None = None,
    ) -> AuthenticatedGatewayKey:
        token = self._extract_bearer_token(authorization_header)

        try:
            public_key_id = parse_gateway_key_public_id(token)
        except ValueError as exc:
            raise MalformedGatewayKeyError() from exc

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_public_key_id(public_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()

        if not self._settings.TOKEN_HMAC_SECRET:
            raise MissingTokenHmacSecretError()

        if not verify_hmac_sha256_token(
            token=token,
            expected_hex_digest=gateway_key.token_hash,
            secret=self._settings.TOKEN_HMAC_SECRET,
        ):
            raise GatewayKeyDigestMismatchError()

        self._validate_hmac_key_version(gateway_key)
        self._validate_status(gateway_key.status)

        check_now = now or datetime.now(UTC)
        self._validate_time_window(gateway_key=gateway_key, now=check_now)

        allowed_providers = None
        if isinstance(gateway_key.metadata_json, dict):
            providers = gateway_key.metadata_json.get("allowed_providers")
            if isinstance(providers, list):
                allowed_providers = tuple(str(item) for item in providers)

        return AuthenticatedGatewayKey(
            gateway_key_id=gateway_key.id,
            owner_id=gateway_key.owner_id,
            cohort_id=gateway_key.cohort_id,
            public_key_id=gateway_key.public_key_id,
            status=gateway_key.status,
            valid_from=gateway_key.valid_from,
            valid_until=gateway_key.valid_until,
            allow_all_models=gateway_key.allow_all_models,
            allowed_models=tuple(gateway_key.allowed_models),
            allow_all_endpoints=gateway_key.allow_all_endpoints,
            allowed_endpoints=tuple(gateway_key.allowed_endpoints),
            allowed_providers=allowed_providers,
            cost_limit_eur=gateway_key.cost_limit_eur,
            token_limit_total=gateway_key.token_limit_total,
            request_limit_total=gateway_key.request_limit_total,
            rate_limit_policy={
                "requests_per_minute": gateway_key.rate_limit_requests_per_minute,
                "tokens_per_minute": gateway_key.rate_limit_tokens_per_minute,
                "max_concurrent_requests": gateway_key.max_concurrent_requests,
            },
        )

    @staticmethod
    def _extract_bearer_token(authorization_header: str | None) -> str:
        if not authorization_header:
            raise MissingAuthorizationError()

        parts = authorization_header.strip().split(maxsplit=1)
        if not parts:
            raise MissingAuthorizationError()

        scheme = parts[0]
        if scheme.lower() != "bearer":
            raise InvalidAuthorizationSchemeError()

        if len(parts) == 1:
            raise MalformedGatewayKeyError()

        token = parts[1].strip()
        if not token:
            raise MalformedGatewayKeyError()

        return token

    def _validate_hmac_key_version(self, gateway_key: GatewayKey) -> None:
        expected_version = self._extract_version_number(self._settings.TOKEN_HMAC_KEY_VERSION)
        if gateway_key.hmac_key_version != expected_version:
            raise MissingTokenHmacSecretError(
                "Server authentication configuration does not support this key version"
            )

    @staticmethod
    def _extract_version_number(version: str) -> int:
        normalized = version.strip().lower()
        if not normalized.startswith("v") or not normalized[1:].isdigit():
            raise MissingTokenHmacSecretError()
        return int(normalized[1:])

    @staticmethod
    def _validate_status(status: str) -> None:
        if status == "active":
            return
        if status == "suspended":
            raise GatewayKeySuspendedError()
        if status == "revoked":
            raise GatewayKeyRevokedError()
        raise GatewayAuthError(f"Invalid gateway key status: {status}")

    @staticmethod
    def _validate_time_window(*, gateway_key: GatewayKey, now: datetime) -> None:
        if now.tzinfo is None:
            raise GatewayAuthError("Current time must be timezone-aware")
        if gateway_key.valid_from.tzinfo is None or gateway_key.valid_until.tzinfo is None:
            raise GatewayAuthError("Gateway key validity timestamps must be timezone-aware")

        if now < gateway_key.valid_from:
            raise GatewayKeyNotYetValidError()
        if now >= gateway_key.valid_until:
            raise GatewayKeyExpiredError()
