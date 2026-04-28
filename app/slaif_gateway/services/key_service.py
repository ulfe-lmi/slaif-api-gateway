"""Service-layer workflow for safe gateway key creation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.schemas.keys import (
    ActivateGatewayKeyInput,
    CreateGatewayKeyInput,
    CreatedGatewayKey,
    GatewayKeyManagementResult,
    ResetGatewayKeyUsageInput,
    RevokeGatewayKeyInput,
    RotateGatewayKeyInput,
    RotatedGatewayKeyResult,
    SuspendGatewayKeyInput,
    UpdateGatewayKeyLimitsInput,
    UpdateGatewayKeyRateLimitsInput,
    UpdateGatewayKeyValidityInput,
)
from slaif_gateway.services.key_errors import (
    GatewayKeyAlreadyActiveError,
    GatewayKeyAlreadyRevokedError,
    GatewayKeyAlreadySuspendedError,
    GatewayKeyNotFoundError,
    GatewayKeyRotationError,
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyStatusTransitionError,
    InvalidGatewayKeyUsageResetError,
    InvalidGatewayKeyValidityError,
)
from slaif_gateway.utils.crypto import generate_gateway_key, hmac_sha256_token
from slaif_gateway.utils.secrets import encrypt_secret


class KeyService:
    """Orchestrates gateway key creation across repositories.

    This service is intentionally flush-only and does not call `commit`; callers own
    transaction boundaries.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        gateway_keys_repository: GatewayKeysRepository,
        one_time_secrets_repository: OneTimeSecretsRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._settings = settings
        self._gateway_keys_repository = gateway_keys_repository
        self._one_time_secrets_repository = one_time_secrets_repository
        self._audit_repository = audit_repository

    async def create_gateway_key(self, payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        """Create key metadata and encrypted one-time delivery payload safely."""
        active_hmac_version, active_hmac_secret = self._settings.get_active_hmac_secret()
        if not self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY:
            raise ValueError("ONE_TIME_SECRET_ENCRYPTION_KEY is required for gateway key creation")

        active_prefix = self._settings.get_gateway_key_prefix()
        generated = generate_gateway_key(prefix=active_prefix)
        token_hash = hmac_sha256_token(
            token=generated.plaintext_key,
            secret=active_hmac_secret,
        )

        rate_limit_policy = self._validate_rate_limit_policy(payload.rate_limit_policy)
        gateway_key = await self._gateway_keys_repository.create_gateway_key_record(
            public_key_id=generated.public_key_id,
            key_prefix=active_prefix,
            key_hint=generated.display_prefix,
            token_hash=token_hash,
            owner_id=payload.owner_id,
            cohort_id=payload.cohort_id,
            status="active",
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            cost_limit_eur=payload.cost_limit_eur,
            token_limit_total=payload.token_limit_total,
            request_limit_total=payload.request_limit_total,
            allowed_models=payload.allowed_models,
            allowed_endpoints=payload.allowed_endpoints,
            rate_limit_requests_per_minute=rate_limit_policy.get("requests_per_minute"),
            rate_limit_tokens_per_minute=rate_limit_policy.get("tokens_per_minute"),
            max_concurrent_requests=rate_limit_policy.get("max_concurrent_requests"),
            metadata_json=self._metadata_with_rate_limit_window({}, rate_limit_policy),
            created_by_admin_user_id=payload.created_by_admin_id,
            hmac_key_version=int(active_hmac_version),
        )

        one_time_plaintext = json.dumps(
            {
                "plaintext_key": generated.plaintext_key,
                "public_key_id": generated.public_key_id,
                "gateway_key_id": str(gateway_key.id),
                "owner_id": str(payload.owner_id),
                "purpose": "gateway_key_email",
            },
            separators=(",", ":"),
        )
        encrypted = encrypt_secret(
            plaintext=one_time_plaintext,
            master_key=self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
        )
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.EMAIL_KEY_SECRET_MAX_AGE_SECONDS
        )
        one_time_secret = await self._one_time_secrets_repository.create_one_time_secret(
            purpose="gateway_key_email",
            encrypted_payload=encrypted.ciphertext,
            nonce=encrypted.nonce,
            encryption_key_version=self._extract_version_number(
                self._settings.ONE_TIME_SECRET_KEY_VERSION
            ),
            gateway_key_id=gateway_key.id,
            owner_id=payload.owner_id,
            expires_at=expires_at,
            status="pending",
        )

        await self._audit_repository.add_audit_log(
            action="gateway_key_created",
            entity_type="gateway_key",
            entity_id=gateway_key.id,
            admin_user_id=payload.created_by_admin_id,
            note=payload.note,
            new_values={
                "gateway_key_id": str(gateway_key.id),
                "public_key_id": generated.public_key_id,
                "owner_id": str(payload.owner_id),
                "cohort_id": str(payload.cohort_id) if payload.cohort_id else None,
                "valid_from": payload.valid_from.isoformat(),
                "valid_until": payload.valid_until.isoformat(),
                "cost_limit_eur": str(payload.cost_limit_eur) if payload.cost_limit_eur else None,
                "token_limit_total": payload.token_limit_total,
                "request_limit_total": payload.request_limit_total,
                "rate_limit_policy": self._rate_limit_policy_from_key(gateway_key),
            },
        )

        return CreatedGatewayKey(
            gateway_key_id=gateway_key.id,
            owner_id=payload.owner_id,
            public_key_id=generated.public_key_id,
            display_prefix=generated.display_prefix,
            plaintext_key=generated.plaintext_key,
            one_time_secret_id=one_time_secret.id,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            rate_limit_policy=self._rate_limit_policy_from_key(gateway_key),
        )

    async def suspend_gateway_key(self, payload: SuspendGatewayKeyInput) -> GatewayKeyManagementResult:
        """Suspend an active gateway key."""
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_status(gateway_key, allowed=("active",), operation="suspend")

        old_values = self._status_audit_values(gateway_key)
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_status(
            gateway_key.id,
            status="suspended",
            revoked_at=None,
            revoked_reason=None,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.status = "suspended"
        gateway_key.revoked_at = None
        gateway_key.revoked_reason = None
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="suspend_key",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values=self._status_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def activate_gateway_key(self, payload: ActivateGatewayKeyInput) -> GatewayKeyManagementResult:
        """Activate a suspended gateway key."""
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_status(gateway_key, allowed=("suspended",), operation="activate")
        self._validate_validity_window(
            valid_from=gateway_key.valid_from,
            valid_until=gateway_key.valid_until,
        )

        old_values = self._status_audit_values(gateway_key)
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_status(
            gateway_key.id,
            status="active",
            revoked_at=None,
            revoked_reason=None,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.status = "active"
        gateway_key.revoked_at = None
        gateway_key.revoked_reason = None
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="activate_key",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values=self._status_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def revoke_gateway_key(self, payload: RevokeGatewayKeyInput) -> GatewayKeyManagementResult:
        """Revoke an active or suspended gateway key."""
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_status(gateway_key, allowed=("active", "suspended"), operation="revoke")

        old_values = self._status_audit_values(gateway_key)
        now = self._now()
        revoked_reason = payload.reason or "revoked by administrator"
        updated = await self._gateway_keys_repository.update_gateway_key_status(
            gateway_key.id,
            status="revoked",
            revoked_at=now,
            revoked_reason=revoked_reason,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.status = "revoked"
        gateway_key.revoked_at = now
        gateway_key.revoked_reason = revoked_reason
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="revoke_key",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values=self._status_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def update_gateway_key_validity(
        self,
        payload: UpdateGatewayKeyValidityInput,
    ) -> GatewayKeyManagementResult:
        """Extend or shorten a non-revoked gateway key validity window."""
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        if gateway_key.status == "revoked":
            raise InvalidGatewayKeyStatusTransitionError("Revoked gateway keys cannot be extended")

        new_valid_from = payload.valid_from or gateway_key.valid_from
        self._validate_validity_window(valid_from=new_valid_from, valid_until=payload.valid_until)

        old_values = self._validity_audit_values(gateway_key)
        action = "extend_key" if payload.valid_until > gateway_key.valid_until else "shorten_key"
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_validity(
            gateway_key.id,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.valid_from = new_valid_from
        gateway_key.valid_until = payload.valid_until
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action=action,
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values=self._validity_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def update_gateway_key_limits(
        self,
        payload: UpdateGatewayKeyLimitsInput,
    ) -> GatewayKeyManagementResult:
        """Update key limits. Lowering below current use is allowed; future reservations fail."""
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        cost_limit = self._validate_optional_positive_decimal(
            payload.cost_limit_eur,
            param="cost_limit_eur",
        )
        self._validate_optional_positive_int(
            payload.token_limit_total,
            param="token_limit_total",
        )
        self._validate_optional_positive_int(
            payload.request_limit_total,
            param="request_limit_total",
        )

        old_values = self._limits_audit_values(gateway_key)
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_limits(
            gateway_key.id,
            cost_limit_eur=cost_limit,
            token_limit_total=payload.token_limit_total,
            request_limit_total=payload.request_limit_total,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.cost_limit_eur = cost_limit
        gateway_key.token_limit_total = payload.token_limit_total
        gateway_key.request_limit_total = payload.request_limit_total
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="update_key_limits",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values=self._limits_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def update_gateway_key_rate_limits(
        self,
        payload: UpdateGatewayKeyRateLimitsInput,
    ) -> GatewayKeyManagementResult:
        """Update Redis-backed operational rate-limit policy for a key."""
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        rate_limit_policy = self._validate_rate_limit_policy(payload.rate_limit_policy)

        old_values = self._rate_limit_audit_values(gateway_key)
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_rate_limit_policy(
            gateway_key.id,
            requests_per_minute=rate_limit_policy.get("requests_per_minute"),
            tokens_per_minute=rate_limit_policy.get("tokens_per_minute"),
            max_concurrent_requests=rate_limit_policy.get("max_concurrent_requests"),
            window_seconds=rate_limit_policy.get("window_seconds"),
        )
        if not updated:
            raise GatewayKeyNotFoundError()

        gateway_key.rate_limit_requests_per_minute = rate_limit_policy.get("requests_per_minute")
        gateway_key.rate_limit_tokens_per_minute = rate_limit_policy.get("tokens_per_minute")
        gateway_key.max_concurrent_requests = rate_limit_policy.get("max_concurrent_requests")
        gateway_key.metadata_json = self._metadata_with_rate_limit_window(
            gateway_key.metadata_json,
            rate_limit_policy,
        )
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="update_key_rate_limits",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values=self._rate_limit_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def reset_gateway_key_usage(
        self,
        payload: ResetGatewayKeyUsageInput,
    ) -> GatewayKeyManagementResult:
        """Reset selected counters without deleting usage ledger history."""
        if not payload.reset_used_counters and not payload.reset_reserved_counters:
            raise InvalidGatewayKeyUsageResetError("At least one counter family must be reset")

        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        old_values = self._usage_audit_values(gateway_key)
        now = self._now()
        await self._gateway_keys_repository.reset_gateway_key_usage_counters(
            gateway_key,
            reset_used_counters=payload.reset_used_counters,
            reset_reserved_counters=payload.reset_reserved_counters,
            reset_at=now,
        )
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="reset_quota",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values={
                **self._usage_audit_values(gateway_key),
                "reset_used_counters": payload.reset_used_counters,
                "reset_reserved_counters": payload.reset_reserved_counters,
            },
        )
        return self._management_result(gateway_key, updated_at=now)

    async def rotate_gateway_key(self, payload: RotateGatewayKeyInput) -> RotatedGatewayKeyResult:
        """Rotate a non-revoked gateway key and return replacement plaintext once."""
        old_key = await self._get_gateway_key(payload.gateway_key_id)
        if old_key.status == "revoked":
            raise GatewayKeyRotationError("Revoked gateway keys cannot be rotated")

        active_hmac_version, active_hmac_secret = self._settings.get_active_hmac_secret()
        if not self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY:
            raise GatewayKeyRotationError("ONE_TIME_SECRET_ENCRYPTION_KEY is required for key rotation")

        new_valid_from = payload.new_valid_from or old_key.valid_from
        new_valid_until = payload.new_valid_until or old_key.valid_until
        self._validate_validity_window(valid_from=new_valid_from, valid_until=new_valid_until)

        active_prefix = self._settings.get_gateway_key_prefix()
        generated = generate_gateway_key(prefix=active_prefix)
        token_hash = hmac_sha256_token(
            token=generated.plaintext_key,
            secret=active_hmac_secret,
        )

        new_key = await self._gateway_keys_repository.create_gateway_key_record(
            public_key_id=generated.public_key_id,
            key_prefix=active_prefix,
            key_hint=generated.display_prefix,
            token_hash=token_hash,
            owner_id=old_key.owner_id,
            cohort_id=old_key.cohort_id,
            status="active",
            valid_from=new_valid_from,
            valid_until=new_valid_until,
            cost_limit_eur=old_key.cost_limit_eur if payload.preserve_limits else None,
            token_limit_total=old_key.token_limit_total if payload.preserve_limits else None,
            request_limit_total=old_key.request_limit_total if payload.preserve_limits else None,
            allowed_models=list(old_key.allowed_models) if payload.preserve_allowed_models else [],
            allowed_endpoints=list(old_key.allowed_endpoints) if payload.preserve_allowed_endpoints else [],
            allow_all_models=old_key.allow_all_models if payload.preserve_allowed_models else False,
            allow_all_endpoints=old_key.allow_all_endpoints if payload.preserve_allowed_endpoints else False,
            rate_limit_requests_per_minute=(
                old_key.rate_limit_requests_per_minute if payload.preserve_rate_limit_policy else None
            ),
            rate_limit_tokens_per_minute=(
                old_key.rate_limit_tokens_per_minute if payload.preserve_rate_limit_policy else None
            ),
            max_concurrent_requests=(
                old_key.max_concurrent_requests if payload.preserve_rate_limit_policy else None
            ),
            metadata_json=(
                self._metadata_with_rate_limit_window(
                    {},
                    self._rate_limit_policy_from_key(old_key) or {},
                )
                if payload.preserve_rate_limit_policy
                else {}
            ),
            created_by_admin_user_id=payload.actor_admin_id,
            hmac_key_version=int(active_hmac_version),
        )

        one_time_plaintext = json.dumps(
            {
                "plaintext_key": generated.plaintext_key,
                "public_key_id": generated.public_key_id,
                "gateway_key_id": str(new_key.id),
                "old_gateway_key_id": str(old_key.id),
                "owner_id": str(old_key.owner_id),
                "purpose": "gateway_key_rotation_email",
            },
            separators=(",", ":"),
        )
        encrypted = encrypt_secret(
            plaintext=one_time_plaintext,
            master_key=self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
        )
        expires_at = self._now() + timedelta(seconds=self._settings.EMAIL_KEY_SECRET_MAX_AGE_SECONDS)
        one_time_secret = await self._one_time_secrets_repository.create_one_time_secret(
            purpose="gateway_key_rotation_email",
            encrypted_payload=encrypted.ciphertext,
            nonce=encrypted.nonce,
            encryption_key_version=self._extract_version_number(
                self._settings.ONE_TIME_SECRET_KEY_VERSION
            ),
            gateway_key_id=new_key.id,
            owner_id=old_key.owner_id,
            expires_at=expires_at,
            status="pending",
        )

        old_status = old_key.status
        old_values = self._status_audit_values(old_key)
        if payload.revoke_old_key:
            now = self._now()
            revoked_reason = payload.reason or "rotated by administrator"
            updated = await self._gateway_keys_repository.update_gateway_key_status(
                old_key.id,
                status="revoked",
                revoked_at=now,
                revoked_reason=revoked_reason,
            )
            if not updated:
                raise GatewayKeyNotFoundError()
            old_key.status = "revoked"
            old_key.revoked_at = now
            old_key.revoked_reason = revoked_reason
            self._set_updated_at(old_key, now)

        await self._audit_gateway_key_change(
            action="rotate_key",
            gateway_key=old_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=old_values,
            new_values={
                **self._status_audit_values(old_key),
                "new_gateway_key_id": str(new_key.id),
                "new_public_key_id": generated.public_key_id,
                "old_key_revoked": payload.revoke_old_key,
            },
        )
        await self._audit_gateway_key_change(
            action="gateway_key_rotation_created",
            gateway_key=new_key,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
            old_values=None,
            new_values={
                "gateway_key_id": str(new_key.id),
                "public_key_id": generated.public_key_id,
                "owner_id": str(old_key.owner_id),
                "cohort_id": str(old_key.cohort_id) if old_key.cohort_id else None,
                "valid_from": new_valid_from.isoformat(),
                "valid_until": new_valid_until.isoformat(),
                "old_gateway_key_id": str(old_key.id),
                "one_time_secret_id": str(one_time_secret.id),
            },
        )

        return RotatedGatewayKeyResult(
            old_gateway_key_id=old_key.id,
            new_gateway_key_id=new_key.id,
            new_plaintext_key=generated.plaintext_key,
            new_public_key_id=generated.public_key_id,
            one_time_secret_id=one_time_secret.id,
            old_status=old_key.status if payload.revoke_old_key else old_status,
            new_status=new_key.status,
            valid_from=new_valid_from,
            valid_until=new_valid_until,
        )

    @staticmethod
    def _extract_version_number(version: str) -> int:
        match = re.fullmatch(r"v(\d+)", version.strip().lower())
        if not match:
            raise ValueError(f"invalid version format: {version!r}")
        return int(match.group(1))

    async def _get_gateway_key(self, gateway_key_id: object) -> GatewayKey:
        getter = getattr(
            self._gateway_keys_repository,
            "get_gateway_key_for_update",
            self._gateway_keys_repository.get_gateway_key_by_id,
        )
        gateway_key = await getter(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        return gateway_key

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _set_updated_at(gateway_key: object, updated_at: datetime) -> None:
        if hasattr(gateway_key, "updated_at"):
            gateway_key.updated_at = updated_at

    @staticmethod
    def _require_status(gateway_key: GatewayKey, *, allowed: tuple[str, ...], operation: str) -> None:
        if gateway_key.status in allowed:
            return
        if gateway_key.status == "revoked":
            raise GatewayKeyAlreadyRevokedError()
        if operation == "suspend" and gateway_key.status == "suspended":
            raise GatewayKeyAlreadySuspendedError()
        if operation == "activate" and gateway_key.status == "active":
            raise GatewayKeyAlreadyActiveError()
        raise InvalidGatewayKeyStatusTransitionError(
            f"Cannot {operation} gateway key with status {gateway_key.status!r}"
        )

    @staticmethod
    def _validate_validity_window(*, valid_from: datetime, valid_until: datetime) -> None:
        if valid_from.tzinfo is None:
            raise InvalidGatewayKeyValidityError("valid_from must be timezone-aware", param="valid_from")
        if valid_until.tzinfo is None:
            raise InvalidGatewayKeyValidityError("valid_until must be timezone-aware", param="valid_until")
        if valid_until <= valid_from:
            raise InvalidGatewayKeyValidityError("valid_until must be after valid_from", param="valid_until")

    @staticmethod
    def _validate_optional_positive_decimal(value: Decimal | None, *, param: str) -> Decimal | None:
        if value is None:
            return None
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if decimal_value <= 0:
            raise InvalidGatewayKeyLimitsError(f"{param} must be positive or None", param=param)
        return decimal_value

    @staticmethod
    def _validate_optional_positive_int(value: int | None, *, param: str) -> None:
        if value is None:
            return
        if value <= 0:
            raise InvalidGatewayKeyLimitsError(f"{param} must be positive or None", param=param)

    def _validate_rate_limit_policy(
        self,
        policy: dict[str, int | None] | None,
    ) -> dict[str, int | None]:
        if not policy:
            return {}

        allowed_keys = {
            "requests_per_minute",
            "tokens_per_minute",
            "max_concurrent_requests",
            "concurrent_requests",
            "window_seconds",
        }
        unknown = sorted(set(policy) - allowed_keys)
        if unknown:
            raise InvalidGatewayKeyLimitsError(
                f"Unknown rate-limit policy field: {unknown[0]}",
                param=unknown[0],
            )

        normalized: dict[str, int | None] = {}
        for key in ("requests_per_minute", "tokens_per_minute", "max_concurrent_requests", "window_seconds"):
            value = policy.get(key)
            if key == "max_concurrent_requests" and value is None:
                value = policy.get("concurrent_requests")
            if value is None:
                continue
            self._validate_optional_positive_int(value, param=key)
            normalized[key] = value
        return normalized

    @staticmethod
    def _metadata_with_rate_limit_window(
        metadata_json: dict[str, object] | None,
        policy: dict[str, int | None],
    ) -> dict[str, object]:
        metadata = dict(metadata_json or {})
        existing_rate_policy = metadata.get("rate_limit_policy")
        rate_policy = dict(existing_rate_policy) if isinstance(existing_rate_policy, dict) else {}
        window_seconds = policy.get("window_seconds")
        if window_seconds is None:
            rate_policy.pop("window_seconds", None)
        else:
            rate_policy["window_seconds"] = window_seconds

        if rate_policy:
            metadata["rate_limit_policy"] = rate_policy
        else:
            metadata.pop("rate_limit_policy", None)
        return metadata

    async def _audit_gateway_key_change(
        self,
        *,
        action: str,
        gateway_key: GatewayKey,
        actor_admin_id: object | None,
        reason: str | None,
        old_values: dict[str, object] | None,
        new_values: dict[str, object] | None,
    ) -> None:
        await self._audit_repository.add_audit_log(
            action=action,
            entity_type="gateway_key",
            entity_id=gateway_key.id,
            admin_user_id=actor_admin_id,
            old_values=old_values,
            new_values=new_values,
            note=reason,
        )

    @staticmethod
    def _status_audit_values(gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "status": gateway_key.status,
            "revoked_at": gateway_key.revoked_at.isoformat() if gateway_key.revoked_at else None,
            "revoked_reason": gateway_key.revoked_reason,
        }

    @staticmethod
    def _validity_audit_values(gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "valid_from": gateway_key.valid_from.isoformat(),
            "valid_until": gateway_key.valid_until.isoformat(),
        }

    @staticmethod
    def _limits_audit_values(gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "cost_limit_eur": str(gateway_key.cost_limit_eur)
            if gateway_key.cost_limit_eur is not None
            else None,
            "token_limit_total": gateway_key.token_limit_total,
            "request_limit_total": gateway_key.request_limit_total,
        }

    @classmethod
    def _rate_limit_audit_values(cls, gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "rate_limit_policy": cls._rate_limit_policy_from_key(gateway_key),
        }

    @staticmethod
    def _usage_audit_values(gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "cost_used_eur": str(gateway_key.cost_used_eur),
            "tokens_used_total": gateway_key.tokens_used_total,
            "requests_used_total": gateway_key.requests_used_total,
            "cost_reserved_eur": str(gateway_key.cost_reserved_eur),
            "tokens_reserved_total": gateway_key.tokens_reserved_total,
            "requests_reserved_total": gateway_key.requests_reserved_total,
            "last_quota_reset_at": (
                gateway_key.last_quota_reset_at.isoformat()
                if gateway_key.last_quota_reset_at
                else None
            ),
            "quota_reset_count": gateway_key.quota_reset_count,
        }

    @classmethod
    def _management_result(
        cls,
        gateway_key: GatewayKey,
        *,
        updated_at: datetime,
    ) -> GatewayKeyManagementResult:
        return GatewayKeyManagementResult(
            gateway_key_id=gateway_key.id,
            public_key_id=gateway_key.public_key_id,
            status=gateway_key.status,
            updated_at=updated_at,
            valid_from=gateway_key.valid_from,
            valid_until=gateway_key.valid_until,
            cost_limit_eur=gateway_key.cost_limit_eur,
            token_limit_total=gateway_key.token_limit_total,
            request_limit_total=gateway_key.request_limit_total,
            cost_used_eur=gateway_key.cost_used_eur,
            tokens_used_total=gateway_key.tokens_used_total,
            requests_used_total=gateway_key.requests_used_total,
            cost_reserved_eur=gateway_key.cost_reserved_eur,
            tokens_reserved_total=gateway_key.tokens_reserved_total,
            requests_reserved_total=gateway_key.requests_reserved_total,
            last_quota_reset_at=gateway_key.last_quota_reset_at,
            quota_reset_count=gateway_key.quota_reset_count,
            rate_limit_policy=cls._rate_limit_policy_from_key(gateway_key),
        )

    @staticmethod
    def _rate_limit_policy_from_key(gateway_key: GatewayKey) -> dict[str, int] | None:
        policy: dict[str, int] = {}
        requests_per_minute = getattr(gateway_key, "rate_limit_requests_per_minute", None)
        tokens_per_minute = getattr(gateway_key, "rate_limit_tokens_per_minute", None)
        max_concurrent_requests = getattr(gateway_key, "max_concurrent_requests", None)
        if requests_per_minute is not None:
            policy["requests_per_minute"] = requests_per_minute
        if tokens_per_minute is not None:
            policy["tokens_per_minute"] = tokens_per_minute
        if max_concurrent_requests is not None:
            policy["max_concurrent_requests"] = max_concurrent_requests

        metadata_policy = None
        metadata_json = getattr(gateway_key, "metadata_json", None)
        if isinstance(metadata_json, dict):
            metadata_policy = metadata_json.get("rate_limit_policy")
        if isinstance(metadata_policy, dict):
            window_seconds = metadata_policy.get("window_seconds")
            if isinstance(window_seconds, int) and not isinstance(window_seconds, bool):
                policy["window_seconds"] = window_seconds

        return policy or None
