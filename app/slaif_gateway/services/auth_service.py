"""Service-layer gateway key authentication and validation."""

from __future__ import annotations

from datetime import UTC, datetime

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnPolicyError,
    chat_streaming_live_burn_policy_from_metadata,
    default_chat_streaming_live_burn_policy,
)
from slaif_gateway.services.responses_streaming_live_burn import (
    ResponsesStreamingLiveBurnPolicyError,
    default_responses_streaming_live_burn_policy,
    responses_streaming_live_burn_policy_from_metadata,
)
from slaif_gateway.services.key_modes import is_trusted_calibration_key
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping
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
        accepted_prefixes = self._settings.get_gateway_key_accepted_prefixes()

        try:
            public_key_id = parse_gateway_key_public_id(token, accepted_prefixes)
        except ValueError as exc:
            raise MalformedGatewayKeyError() from exc

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_public_key_id(public_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()

        hmac_secret = self._settings.get_hmac_secret(str(gateway_key.hmac_key_version))
        if not hmac_secret:
            raise MissingTokenHmacSecretError()

        if not verify_hmac_sha256_token(
            token=token,
            expected_hex_digest=gateway_key.token_hash,
            secret=hmac_secret,
        ):
            raise GatewayKeyDigestMismatchError()

        self._validate_status(gateway_key.status)

        check_now = now or datetime.now(UTC)
        self._validate_time_window(gateway_key=gateway_key, now=check_now)

        allowed_providers = None
        rate_limit_metadata: dict[str, object] = {}
        responses_policy: dict[str, object] | None = None
        chat_streaming_live_burn_policy = default_chat_streaming_live_burn_policy()
        responses_streaming_live_burn_policy = default_responses_streaming_live_burn_policy()
        if isinstance(gateway_key.metadata_json, dict):
            providers = gateway_key.metadata_json.get("allowed_providers")
            if isinstance(providers, list):
                allowed_providers = tuple(str(item) for item in providers)
            raw_rate_limit_metadata = gateway_key.metadata_json.get("rate_limit_policy")
            if isinstance(raw_rate_limit_metadata, dict):
                rate_limit_metadata = raw_rate_limit_metadata
            raw_responses_policy = gateway_key.metadata_json.get("responses_policy")
            if isinstance(raw_responses_policy, dict):
                sanitized_policy = sanitize_metadata_mapping(
                    raw_responses_policy,
                    drop_content_keys=True,
                )
                responses_policy = sanitized_policy if isinstance(sanitized_policy, dict) else None
            try:
                chat_streaming_live_burn_policy = chat_streaming_live_burn_policy_from_metadata(
                    gateway_key.metadata_json,
                    max_abs_cost_margin_eur=(
                        self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                    ),
                    max_abs_token_margin=(
                        self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN
                    ),
                )
            except ChatStreamingLiveBurnPolicyError:
                chat_streaming_live_burn_policy = default_chat_streaming_live_burn_policy()
            try:
                responses_streaming_live_burn_policy = (
                    responses_streaming_live_burn_policy_from_metadata(
                        gateway_key.metadata_json,
                        max_abs_cost_margin_eur=(
                            self._settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                        ),
                        max_abs_token_margin=(
                            self._settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN
                        ),
                    )
                )
            except ResponsesStreamingLiveBurnPolicyError:
                responses_streaming_live_burn_policy = (
                    default_responses_streaming_live_burn_policy()
                )

        window_seconds = rate_limit_metadata.get("window_seconds")
        if isinstance(window_seconds, bool) or not isinstance(window_seconds, int):
            window_seconds = None

        trusted_calibration = is_trusted_calibration_key(
            key_purpose=getattr(gateway_key, "key_purpose", "standard"),
            capability_policy_mode=getattr(gateway_key, "capability_policy_mode", "standard"),
        )

        return AuthenticatedGatewayKey(
            gateway_key_id=gateway_key.id,
            owner_id=gateway_key.owner_id,
            cohort_id=gateway_key.cohort_id,
            public_key_id=gateway_key.public_key_id,
            status=gateway_key.status,
            valid_from=gateway_key.valid_from,
            valid_until=gateway_key.valid_until,
            allow_all_models=gateway_key.allow_all_models or trusted_calibration,
            allowed_models=tuple(gateway_key.allowed_models),
            allow_all_endpoints=gateway_key.allow_all_endpoints or trusted_calibration,
            allowed_endpoints=tuple(gateway_key.allowed_endpoints),
            allowed_providers=allowed_providers,
            cost_limit_eur=gateway_key.cost_limit_eur,
            token_limit_total=gateway_key.token_limit_total,
            request_limit_total=gateway_key.request_limit_total,
            cost_used_eur=gateway_key.cost_used_eur,
            tokens_used_total=gateway_key.tokens_used_total,
            cost_reserved_eur=gateway_key.cost_reserved_eur,
            tokens_reserved_total=gateway_key.tokens_reserved_total,
            rate_limit_policy={
                "requests_per_minute": gateway_key.rate_limit_requests_per_minute,
                "tokens_per_minute": gateway_key.rate_limit_tokens_per_minute,
                "max_concurrent_requests": gateway_key.max_concurrent_requests,
                "window_seconds": window_seconds,
            },
            responses_policy=responses_policy,
            chat_streaming_live_burn_policy=chat_streaming_live_burn_policy.to_metadata(),
            responses_streaming_live_burn_policy=(
                responses_streaming_live_burn_policy.to_metadata()
            ),
            key_purpose=getattr(gateway_key, "key_purpose", "standard"),
            capability_policy_mode=getattr(gateway_key, "capability_policy_mode", "standard"),
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
