"""Service-layer workflow for safe gateway key creation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.schemas.rate_limits import parse_lazy_throttling_policy_metadata
from slaif_gateway.schemas.key_configuration import KeyConfiguration, key_configuration_export
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
    UpdateGatewayKeyChatStreamingLiveBurnInput,
    UpdateGatewayKeyConfigurationInput,
    UpdateGatewayKeyExternalToolPolicyInput,
    UpdateGatewayKeyLimitsInput,
    UpdateGatewayKeyLazyThrottlingInput,
    UpdateGatewayKeyPolicyInput,
    UpdateGatewayKeyRateLimitsInput,
    UpdateGatewayKeyValidityInput,
)
from slaif_gateway.services.key_policy_configuration import (
    KeyConfigurationExportError,
    canonical_rate_policy_members,
    is_quota_group_present,
    is_request_policy_group_present,
    proposed_matches_stored_binding,
    quota_group_values,
    request_policy_group_values,
    UNBOUND,
    stored_module_binding,
)
from slaif_gateway.services.external_tool_policy_contract import (
    EXTERNAL_TOOL_FENCED,
    ExternalToolKeyPolicy,
    parse_key_external_tool_policy,
    strict_key_policy,
)
from slaif_gateway.services.chat_streaming_live_burn import (
    CHAT_STREAMING_LIVE_BURN_METADATA_KEY,
    ChatStreamingLiveBurnPolicy,
    ChatStreamingLiveBurnPolicyError,
    chat_streaming_live_burn_policy_from_metadata,
    default_chat_streaming_live_burn_policy,
    metadata_with_chat_streaming_live_burn_policy,
    normalize_chat_streaming_live_burn_policy,
)
from slaif_gateway.services.key_errors import (
    GatewayKeyAlreadyActiveError,
    KeyManagementError,
    GatewayKeyAlreadyRevokedError,
    GatewayKeyAlreadySuspendedError,
    GatewayKeyNotFoundError,
    GatewayKeyRotationError,
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyPolicyError,
    InvalidGatewayKeyStatusTransitionError,
    InvalidGatewayKeyUsageResetError,
    InvalidGatewayKeyValidityError,
)
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_STANDARD,
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    CAPABILITY_POLICY_MODE_VALUES,
    KEY_PURPOSE_STANDARD,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
    KEY_PURPOSE_VALUES,
    default_capability_policy_mode_for_purpose,
    is_trusted_calibration_key,
)
from slaif_gateway.services.key_policy_validation import (
    GatewayKeyPolicy,
    validate_gateway_key_policy,
)
from slaif_gateway.services.responses_policy_validation import (
    validate_key_responses_policy,
)
from slaif_gateway.services.responses_streaming_live_burn import (
    default_responses_streaming_live_burn_policy,
    metadata_with_responses_streaming_live_burn_policy,
    ResponsesStreamingLiveBurnPolicyError,
)
from slaif_gateway.utils.crypto import generate_gateway_key, hmac_sha256_token
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping
from slaif_gateway.utils.secrets import encrypt_secret


class GatewayKeyExternalToolFenceActiveError(KeyManagementError):
    status_code = 409
    error_type = "conflict_error"
    error_code = "gateway_key_external_tool_fence_active"
    message = (
        "This gateway key has an active exclusive external-tool fence; "
        "the management operation is blocked until the reservation is settled"
    )


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
        model_routes_repository: object | None = None,
    ) -> None:
        self._settings = settings
        self._gateway_keys_repository = gateway_keys_repository
        self._one_time_secrets_repository = one_time_secrets_repository
        self._audit_repository = audit_repository
        self._model_routes_repository = model_routes_repository

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

        key_purpose, capability_policy_mode = self._validate_key_purpose_and_policy_mode(
            key_purpose=payload.key_purpose,
            capability_policy_mode=payload.capability_policy_mode,
        )
        self._validate_trusted_calibration_create_policy(
            key_purpose=key_purpose,
            capability_policy_mode=capability_policy_mode,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            request_limit_total=payload.request_limit_total,
            confirmed=payload.confirm_trusted_calibration,
            reason=payload.note,
        )
        external_tool_policy = self._validate_external_tool_policy(
            payload.external_tool_policy,
            key_purpose=key_purpose,
            request_limit_total=payload.request_limit_total,
            token_limit_total=payload.token_limit_total,
            cost_limit_eur=payload.cost_limit_eur,
            confirmed=payload.confirm_external_tool_fenced,
            reason=payload.note,
            require_reason=True,
        )
        rate_limit_policy = self._validate_rate_limit_policy(payload.rate_limit_policy)
        lazy_throttling_policy = self._validate_lazy_throttling_policy(
            payload.lazy_throttling_policy
        )
        chat_live_burn_policy = self._validate_chat_streaming_live_burn_policy(
            payload.chat_streaming_live_burn_policy
        )
        if is_trusted_calibration_key(
            key_purpose=key_purpose,
            capability_policy_mode=capability_policy_mode,
        ):
            allowed_models = []
            allowed_endpoints = []
            allow_all_models = True
            allow_all_endpoints = True
        else:
            allowed_models = payload.allowed_models
            allowed_endpoints = payload.allowed_endpoints
            allow_all_models = payload.allow_all_models
            allow_all_endpoints = payload.allow_all_endpoints
        request_policy = await self._validate_request_policy(
            allowed_models=allowed_models,
            allowed_endpoints=allowed_endpoints,
            allow_all_models=allow_all_models,
            allow_all_endpoints=allow_all_endpoints,
        )
        metadata_json = self._metadata_with_lazy_throttling_policy(
            self._metadata_with_rate_limit_window(
                self._metadata_with_responses_streaming_live_burn_policy(
                    self._metadata_with_chat_streaming_live_burn_policy(
                        self._metadata_with_responses_policy(
                            self._metadata_with_provider_policy({}, payload.allowed_providers),
                            payload.responses_policy,
                        ),
                        chat_live_burn_policy,
                    ),
                    default_responses_streaming_live_burn_policy(),
                ),
                rate_limit_policy,
            ),
            lazy_throttling_policy,
        )
        if external_tool_policy.mode == EXTERNAL_TOOL_FENCED:
            metadata_json = self._metadata_with_external_tool_policy(
                metadata_json,
                external_tool_policy,
            )
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
            allowed_models=request_policy.allowed_models,
            allowed_endpoints=request_policy.allowed_endpoints,
            allow_all_models=request_policy.allow_all_models,
            allow_all_endpoints=request_policy.allow_all_endpoints,
            key_purpose=key_purpose,
            capability_policy_mode=capability_policy_mode,
            calibration_metadata=self._safe_calibration_metadata(payload.calibration_metadata),
            template_id=payload.template_id,
            template_revision_id=payload.template_revision_id,
            rate_limit_requests_per_minute=rate_limit_policy.get("requests_per_minute"),
            rate_limit_tokens_per_minute=rate_limit_policy.get("tokens_per_minute"),
            max_concurrent_requests=rate_limit_policy.get("max_concurrent_requests"),
            metadata_json=metadata_json,
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
                "allowed_models": request_policy.allowed_models,
                "allowed_endpoints": request_policy.allowed_endpoints,
                "allow_all_models": request_policy.allow_all_models,
                "allow_all_endpoints": request_policy.allow_all_endpoints,
                "key_purpose": key_purpose,
                "capability_policy_mode": capability_policy_mode,
                "calibration_metadata": self._safe_calibration_metadata(
                    payload.calibration_metadata
                ),
                "template_id": str(payload.template_id) if payload.template_id else None,
                "template_revision_id": (
                    str(payload.template_revision_id) if payload.template_revision_id else None
                ),
                "allowed_providers": list(payload.allowed_providers)
                if payload.allowed_providers is not None
                else None,
                "responses_policy": self._safe_responses_policy(payload.responses_policy),
                "chat_streaming_live_burn_policy": chat_live_burn_policy.to_metadata(),
                "rate_limit_policy": self._rate_limit_policy_from_key(gateway_key),
                "lazy_throttling_policy": lazy_throttling_policy,
                "external_tool_policy": external_tool_policy.to_metadata(),
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
            lazy_throttling_policy=lazy_throttling_policy,
            chat_streaming_live_burn_policy=chat_live_burn_policy.to_metadata(),
            key_purpose=key_purpose,
            capability_policy_mode=capability_policy_mode,
            template_id=payload.template_id,
            template_revision_id=payload.template_revision_id,
            external_tool_policy=external_tool_policy.to_metadata(),
        )

    async def suspend_gateway_key(
        self, payload: SuspendGatewayKeyInput
    ) -> GatewayKeyManagementResult:
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

    async def update_gateway_key_policy(
        self,
        payload: UpdateGatewayKeyPolicyInput,
    ) -> GatewayKeyManagementResult:
        """Update endpoint/model request policy without mutating key material or quotas."""
        cleaned_reason = payload.reason.strip() if payload.reason else ""
        if not cleaned_reason:
            raise InvalidGatewayKeyPolicyError(
                "Enter an audit reason before updating request policy.",
                param="reason",
            )

        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_not_external_tool_fenced(gateway_key, operation="policy update")
        request_policy = await self._validate_request_policy(
            allowed_models=payload.allowed_models,
            allowed_endpoints=payload.allowed_endpoints,
            allow_all_models=payload.allow_all_models,
            allow_all_endpoints=payload.allow_all_endpoints,
        )

        old_values = self._policy_audit_values(gateway_key)
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_request_policy(
            gateway_key.id,
            allowed_models=request_policy.allowed_models,
            allowed_endpoints=request_policy.allowed_endpoints,
            allow_all_models=request_policy.allow_all_models,
            allow_all_endpoints=request_policy.allow_all_endpoints,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.allowed_models = request_policy.allowed_models
        gateway_key.allowed_endpoints = request_policy.allowed_endpoints
        gateway_key.allow_all_models = request_policy.allow_all_models
        gateway_key.allow_all_endpoints = request_policy.allow_all_endpoints
        if payload.update_allowed_providers:
            new_metadata = self._metadata_with_provider_policy(
                gateway_key.metadata_json,
                payload.allowed_providers,
            )
            if new_metadata != (gateway_key.metadata_json or {}):
                metadata_updated = await self._gateway_keys_repository.update_gateway_key_metadata(
                    gateway_key.id,
                    metadata_json=new_metadata,
                )
                if not metadata_updated:
                    raise GatewayKeyNotFoundError()
                gateway_key.metadata_json = new_metadata
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="update_key_policy",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=cleaned_reason,
            old_values=old_values,
            new_values=self._policy_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def activate_gateway_key(
        self, payload: ActivateGatewayKeyInput
    ) -> GatewayKeyManagementResult:
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

    async def revoke_gateway_key(
        self, payload: RevokeGatewayKeyInput
    ) -> GatewayKeyManagementResult:
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
        if not (new_valid_from <= now < payload.valid_until):
            self._require_not_external_tool_fenced(
                gateway_key, operation="validity window update"
            )
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
        self._require_not_external_tool_fenced(gateway_key, operation="limit update")
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
        current_external_policy = self._external_tool_policy_from_key(gateway_key)
        if current_external_policy.mode == EXTERNAL_TOOL_FENCED:
            self._validate_external_tool_limits(
                request_limit_total=payload.request_limit_total,
                token_limit_total=payload.token_limit_total,
                cost_limit_eur=cost_limit,
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

    async def update_gateway_key_external_tool_policy(
        self,
        payload: UpdateGatewayKeyExternalToolPolicyInput,
    ) -> GatewayKeyManagementResult:
        """Replace external-tool policy after canonical validation and safe audit."""
        cleaned_reason = payload.reason.strip() if payload.reason else ""
        if not cleaned_reason:
            raise InvalidGatewayKeyPolicyError(
                "Enter an audit reason before updating external-tool policy.",
                param="reason",
            )
        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_not_external_tool_fenced(
            gateway_key, operation="external-tool policy update"
        )
        policy = self._validate_external_tool_policy(
            payload.external_tool_policy,
            key_purpose=str(getattr(gateway_key, "key_purpose", KEY_PURPOSE_STANDARD)),
            request_limit_total=gateway_key.request_limit_total,
            token_limit_total=gateway_key.token_limit_total,
            cost_limit_eur=gateway_key.cost_limit_eur,
            confirmed=payload.confirm_external_tool_fenced,
            reason=cleaned_reason,
            require_reason=True,
        )
        old_values = self._external_tool_policy_audit_values(gateway_key)
        new_metadata = self._metadata_with_external_tool_policy(
            gateway_key.metadata_json,
            policy,
        )
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_metadata(
            gateway_key.id,
            metadata_json=new_metadata,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.metadata_json = new_metadata
        self._set_updated_at(gateway_key, now)
        await self._audit_gateway_key_change(
            action="update_external_tool_policy",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=cleaned_reason,
            old_values=old_values,
            new_values=self._external_tool_policy_audit_values(gateway_key),
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

    async def update_gateway_key_lazy_throttling(
        self,
        payload: UpdateGatewayKeyLazyThrottlingInput,
    ) -> GatewayKeyManagementResult:
        """Update the key's bounded lazy (waiting) throttling policy.

        Persists the strictly validated policy in the existing key metadata
        (same transaction as the audit, safe old/new values). ``None`` removes
        the stored policy (default immediate rejection). An audit reason is
        required.
        """
        cleaned_reason = payload.reason.strip() if payload.reason else ""
        if not cleaned_reason:
            raise InvalidGatewayKeyLimitsError(
                "Enter an audit reason before updating lazy throttling policy.",
                param="reason",
            )

        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        policy = self._validate_lazy_throttling_policy(payload.lazy_throttling_policy)
        old_values = self._lazy_throttling_audit_values(gateway_key)
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_metadata(
            gateway_key.id,
            metadata_json=self._metadata_with_lazy_throttling_policy(
                gateway_key.metadata_json,
                policy,
            ),
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.metadata_json = self._metadata_with_lazy_throttling_policy(
            gateway_key.metadata_json,
            policy,
        )
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="update_key_lazy_throttling",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=cleaned_reason,
            old_values=old_values,
            new_values=self._lazy_throttling_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def update_gateway_key_chat_streaming_live_burn(
        self,
        payload: UpdateGatewayKeyChatStreamingLiveBurnInput,
    ) -> GatewayKeyManagementResult:
        """Update Chat Completions streaming live-burn policy without mutating quotas."""
        cleaned_reason = payload.reason.strip() if payload.reason else ""
        if not cleaned_reason:
            raise InvalidGatewayKeyPolicyError(
                "Enter an audit reason before updating Chat streaming live-burn policy.",
                param="reason",
            )

        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        policy = self._validate_chat_streaming_live_burn_policy(
            payload.chat_streaming_live_burn_policy
        )
        old_values = self._chat_streaming_live_burn_audit_values(gateway_key)
        new_metadata = self._metadata_with_chat_streaming_live_burn_policy(
            gateway_key.metadata_json,
            policy,
        )
        now = self._now()
        updated = await self._gateway_keys_repository.update_gateway_key_metadata(
            gateway_key.id,
            metadata_json=new_metadata,
        )
        if not updated:
            raise GatewayKeyNotFoundError()
        gateway_key.metadata_json = new_metadata
        self._set_updated_at(gateway_key, now)

        await self._audit_gateway_key_change(
            action="update_chat_streaming_live_burn_policy",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=cleaned_reason,
            old_values=old_values,
            new_values=self._chat_streaming_live_burn_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def update_gateway_key_configuration(
        self,
        payload: UpdateGatewayKeyConfigurationInput,
    ) -> GatewayKeyManagementResult:
        """Apply a presence-aware typed key-configuration update.

        Omission law: only the fields PRESENT in the configuration are
        requested changes; absent fields preserve the key's current state.
        Every resulting value is prepared and validated under the row lock
        (route-aware request policy, rate per-member patch, complete
        live-burn blocks, finite fenced-quota invariant, client-module
        migration law) BEFORE any write. Key material, status, validity,
        counters, reservations, and holds are never touched; one audit
        record covers the update and every write stays in the
        caller-owned transaction.
        """
        cleaned_reason = payload.reason.strip() if payload.reason else ""
        if not cleaned_reason:
            raise InvalidGatewayKeyPolicyError(
                "Enter an audit reason before updating key configuration.",
                param="reason",
            )
        config = payload.configuration
        if config.is_empty():
            raise InvalidGatewayKeyPolicyError(
                "No requested key configuration change.",
                param="configuration",
            )

        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_not_external_tool_fenced(
            gateway_key, operation="configuration update"
        )

        raw_metadata = (
            gateway_key.metadata_json
            if isinstance(gateway_key.metadata_json, dict)
            else {}
        )

        # ---- Prepare and validate the complete resulting state ----------
        quotas_requested = is_quota_group_present(config)
        resulting_cost, resulting_tokens, resulting_requests = quota_group_values(
            config,
            current_cost_limit_eur=gateway_key.cost_limit_eur,
            current_token_limit_total=gateway_key.token_limit_total,
            current_request_limit_total=gateway_key.request_limit_total,
        )
        resulting_cost = self._validate_optional_positive_decimal(
            resulting_cost, param="cost_limit_eur"
        )
        self._validate_optional_positive_int(
            resulting_tokens, param="token_limit_total"
        )
        self._validate_optional_positive_int(
            resulting_requests, param="request_limit_total"
        )

        request_requested = is_request_policy_group_present(config)
        if request_requested:
            (
                allowed_models,
                allow_all_models,
                allowed_endpoints,
                allow_all_endpoints,
            ) = request_policy_group_values(
                config,
                current_allowed_models=gateway_key.allowed_models,
                current_allow_all_models=gateway_key.allow_all_models,
                current_allowed_endpoints=gateway_key.allowed_endpoints,
                current_allow_all_endpoints=gateway_key.allow_all_endpoints,
            )
            request_policy = await self._validate_request_policy(
                allowed_models=allowed_models,
                allowed_endpoints=allowed_endpoints,
                allow_all_models=allow_all_models,
                allow_all_endpoints=allow_all_endpoints,
            )

        providers_requested = config.has("allowed_providers")

        responses_requested = config.has("responses_policy")
        resulting_responses = None
        existing_binding = stored_module_binding(raw_metadata.get("responses_policy"))
        if responses_requested:
            if config.responses_policy is not None:
                resulting_responses = validate_key_responses_policy(
                    config.responses_policy
                )
        # Migration law (the current resolver is the authority): a key whose
        # stored block carries a client-module binding - a currently
        # resolvable identity (explicit registered pin or the implicit legacy
        # five-gate shape) OR a stale/unregistered/malformed stored pin - may
        # only retain that exact binding, including deauthorizing grants while
        # retaining the same pin. A stale binding is NOT initial binding:
        # re-pinning it to the current registered identity (or to any other
        # identity), or clearing it, requires the reviewed client-module
        # migration workflow. Only a genuinely unbound key may be initially
        # bound through a configuration update.
        if responses_requested and existing_binding is not UNBOUND:
            if resulting_responses is None:
                raise InvalidGatewayKeyPolicyError(
                    "Clearing a Responses policy that binds a client module "
                    "identity is not allowed here; use the reviewed "
                    "client-module migration workflow.",
                    param="responses_policy.client_module",
                )
            if not proposed_matches_stored_binding(
                existing_binding, resulting_responses
            ):
                raise InvalidGatewayKeyPolicyError(
                    "Changing the client module identity of an existing key is "
                    "not allowed here; use the reviewed client-module migration "
                    "workflow.",
                    param="responses_policy.client_module",
                )

        rate_requested = config.has("rate_limit_policy")
        resulting_rate: dict[str, int | None] = {}
        if rate_requested and config.rate_limit_policy is not None:
            # Strict vocabulary FIRST: unknown members (including legacy
            # aliases with no canonical spelling) and ambiguous alias pairs
            # fail before any projection or merge - an ignored member is
            # never a successful configuration. The historical
            # concurrent_requests alias canonicalizes to
            # max_concurrent_requests.
            canonical_members = canonical_rate_policy_members(
                config.rate_limit_policy
            )
            # Per-member patch: absent members keep the current configured
            # overrides; explicit null resets the member (inherit).
            merged_rate: dict[str, object] = dict(
                self._rate_limit_policy_from_key(gateway_key) or {}
            )
            for member, value in canonical_members.items():
                merged_rate[member] = value
            resulting_rate = self._validate_rate_limit_policy(dict(merged_rate))

        lazy_requested = config.has("lazy_throttling_policy")
        resulting_lazy = None
        if lazy_requested:
            resulting_lazy = self._validate_lazy_throttling_policy(
                config.lazy_throttling_policy
            )

        live_burn_requested = config.has("chat_streaming_live_burn_policy")
        resulting_live_burn = None
        if live_burn_requested:
            live_burn_block = config.chat_streaming_live_burn_policy
            if not isinstance(live_burn_block, dict) or not {
                "enabled",
                "cost_margin_eur",
                "token_margin",
            } <= set(live_burn_block):
                raise InvalidGatewayKeyPolicyError(
                    "Chat streaming live-burn configuration carries complete "
                    "blocks with enabled, cost_margin_eur, and token_margin.",
                    param="chat_streaming_live_burn_policy",
                )
            resulting_live_burn = self._validate_chat_streaming_live_burn_policy(
                live_burn_block
            )

        external_requested = config.has("external_tool_policy")
        resulting_external = self._external_tool_policy_from_key(gateway_key)
        if external_requested:
            resulting_external = self._validate_external_tool_policy(
                config.external_tool_policy,
                key_purpose=str(
                    getattr(gateway_key, "key_purpose", KEY_PURPOSE_STANDARD)
                ),
                request_limit_total=resulting_requests,
                token_limit_total=resulting_tokens,
                cost_limit_eur=resulting_cost,
                confirmed=(
                    bool(config.confirm_external_tool_fenced)
                    if config.has("confirm_external_tool_fenced")
                    else False
                ),
                reason=cleaned_reason,
                require_reason=True,
            )
        # Final-state cross-check: a retained (or newly set) fenced policy
        # must keep its finite quota prerequisites, exactly as the existing
        # quota mutator law requires.
        if resulting_external.mode == EXTERNAL_TOOL_FENCED:
            self._validate_external_tool_limits(
                request_limit_total=resulting_requests,
                token_limit_total=resulting_tokens,
                cost_limit_eur=resulting_cost,
            )

        # ---- Write phase (caller-owned transaction) ----------------------
        old_values = self._configuration_audit_values(gateway_key)
        now = self._now()

        if quotas_requested:
            updated = await self._gateway_keys_repository.update_gateway_key_limits(
                gateway_key.id,
                cost_limit_eur=resulting_cost,
                token_limit_total=resulting_tokens,
                request_limit_total=resulting_requests,
            )
            if not updated:
                raise GatewayKeyNotFoundError()
            gateway_key.cost_limit_eur = resulting_cost
            gateway_key.token_limit_total = resulting_tokens
            gateway_key.request_limit_total = resulting_requests

        if request_requested:
            updated = await self._gateway_keys_repository.update_gateway_key_request_policy(
                gateway_key.id,
                allowed_models=request_policy.allowed_models,
                allowed_endpoints=request_policy.allowed_endpoints,
                allow_all_models=request_policy.allow_all_models,
                allow_all_endpoints=request_policy.allow_all_endpoints,
            )
            if not updated:
                raise GatewayKeyNotFoundError()
            gateway_key.allowed_models = request_policy.allowed_models
            gateway_key.allowed_endpoints = request_policy.allowed_endpoints
            gateway_key.allow_all_models = request_policy.allow_all_models
            gateway_key.allow_all_endpoints = request_policy.allow_all_endpoints

        metadata = dict(raw_metadata)
        if providers_requested:
            metadata = self._metadata_with_provider_policy(
                metadata, config.allowed_providers
            )
        if responses_requested:
            metadata = self._metadata_with_responses_policy(
                metadata, resulting_responses
            )
        if rate_requested:
            updated = await self._gateway_keys_repository.update_gateway_key_rate_limit_policy(
                gateway_key.id,
                requests_per_minute=resulting_rate.get("requests_per_minute"),
                tokens_per_minute=resulting_rate.get("tokens_per_minute"),
                max_concurrent_requests=resulting_rate.get("max_concurrent_requests"),
                window_seconds=resulting_rate.get("window_seconds"),
            )
            if not updated:
                raise GatewayKeyNotFoundError()
            gateway_key.rate_limit_requests_per_minute = resulting_rate.get(
                "requests_per_minute"
            )
            gateway_key.rate_limit_tokens_per_minute = resulting_rate.get(
                "tokens_per_minute"
            )
            gateway_key.max_concurrent_requests = resulting_rate.get(
                "max_concurrent_requests"
            )
            metadata = self._metadata_with_rate_limit_window(metadata, resulting_rate)
        if lazy_requested:
            metadata = self._metadata_with_lazy_throttling_policy(
                metadata, resulting_lazy
            )
        if live_burn_requested:
            metadata = self._metadata_with_chat_streaming_live_burn_policy(
                metadata, resulting_live_burn
            )
        if external_requested:
            metadata = self._metadata_with_external_tool_policy(
                metadata, resulting_external
            )

        if metadata != raw_metadata:
            updated = await self._gateway_keys_repository.update_gateway_key_metadata(
                gateway_key.id,
                metadata_json=metadata,
            )
            if not updated:
                raise GatewayKeyNotFoundError()
            gateway_key.metadata_json = metadata

        self._set_updated_at(gateway_key, now)
        await self._audit_gateway_key_change(
            action="update_key_configuration",
            gateway_key=gateway_key,
            actor_admin_id=payload.actor_admin_id,
            reason=cleaned_reason,
            old_values=old_values,
            new_values=self._configuration_audit_values(gateway_key),
        )
        return self._management_result(gateway_key, updated_at=now)

    async def export_gateway_key_configuration(
        self,
        gateway_key_id: object,
    ) -> dict[str, object]:
        """Render the key's administtered policy state as a version-1 document.

        Faithful full-config export: known policy groups are always emitted
        (explicit null when absent) so export-then-create AND
        export-then-update reproduce the source key's configured semantics
        on any target. Stored blocks are inspected RAW with strict typed
        validators: malformed or unsupported policy fails the export
        explicitly instead of falling back to runtime-safe defaults. A fresh
        operation confirmation is NEVER emitted - confirmations are
        operation controls, not inherited configuration.
        """
        gateway_key = await self._get_gateway_key(gateway_key_id)
        raw_metadata = (
            gateway_key.metadata_json
            if isinstance(gateway_key.metadata_json, dict)
            else {}
        )
        config = KeyConfiguration()
        config.allowed_models = list(gateway_key.allowed_models or [])
        config.allow_all_models = bool(gateway_key.allow_all_models)
        config.allowed_endpoints = list(gateway_key.allowed_endpoints or [])
        config.allow_all_endpoints = bool(gateway_key.allow_all_endpoints)

        raw_providers = raw_metadata.get("allowed_providers")
        if raw_providers is None:
            config.allowed_providers = None
        elif isinstance(raw_providers, list) and all(
            isinstance(item, str) and item.strip() for item in raw_providers
        ):
            config.allowed_providers = [item.strip() for item in raw_providers]
        else:
            raise KeyConfigurationExportError(
                "Stored provider policy is not a valid provider allow-list.",
                param="allowed_providers",
            )

        raw_responses = raw_metadata.get("responses_policy")
        if raw_responses is None:
            config.responses_policy = None
        elif not isinstance(raw_responses, dict):
            raise KeyConfigurationExportError(
                param="responses_policy",
            )
        else:
            try:
                config.responses_policy = validate_key_responses_policy(raw_responses)
            except InvalidGatewayKeyPolicyError as exc:
                raise KeyConfigurationExportError(
                    param=exc.param,
                ) from exc

        raw_rate_metadata = raw_metadata.get("rate_limit_policy")
        if raw_rate_metadata is not None:
            if not isinstance(raw_rate_metadata, dict) or any(
                key != "window_seconds" for key in raw_rate_metadata
            ):
                raise KeyConfigurationExportError(
                    param="rate_limit_policy",
                )
            window = raw_rate_metadata.get("window_seconds")
            if window is not None and (
                isinstance(window, bool) or not isinstance(window, int)
            ):
                raise KeyConfigurationExportError(
                    param="rate_limit_policy",
                )
        projected_rate = self._rate_limit_policy_from_key(gateway_key)
        config.rate_limit_policy = dict(projected_rate) if projected_rate else None

        raw_lazy = raw_metadata.get("lazy_throttling_policy")
        if raw_lazy is None:
            config.lazy_throttling_policy = None
        elif not isinstance(raw_lazy, dict):
            raise KeyConfigurationExportError(param="lazy_throttling_policy")
        else:
            try:
                # Strict authoring validator: malformed/unknown/ceiling-
                # exceeding stored blocks fail the export explicitly.
                config.lazy_throttling_policy = self._validate_lazy_throttling_policy(
                    raw_lazy
                )
            except InvalidGatewayKeyLimitsError as exc:
                raise KeyConfigurationExportError(
                    param=exc.param or "lazy_throttling_policy",
                ) from exc

        raw_live_burn = raw_metadata.get(CHAT_STREAMING_LIVE_BURN_METADATA_KEY)
        if raw_live_burn is None:
            config.chat_streaming_live_burn_policy = (
                default_chat_streaming_live_burn_policy().to_metadata()
            )
        else:
            try:
                config.chat_streaming_live_burn_policy = (
                    self._validate_chat_streaming_live_burn_policy(raw_live_burn)
                    .to_metadata()
                )
            except InvalidGatewayKeyPolicyError as exc:
                raise KeyConfigurationExportError(
                    param=exc.param or "chat_streaming_live_burn_policy",
                ) from exc

        raw_external = raw_metadata.get("external_tool_policy")
        if raw_external is None:
            config.external_tool_policy = strict_key_policy().to_metadata()
        else:
            parsed_external = parse_key_external_tool_policy(
                raw_external,
                ceilings=self._settings.get_external_tool_operator_ceilings(),
            )
            if not parsed_external.valid or parsed_external.policy is None:
                raise KeyConfigurationExportError(
                    param="external_tool_policy",
                )
            config.external_tool_policy = parsed_external.policy.to_metadata()

        config.cost_limit_eur = gateway_key.cost_limit_eur
        config.token_limit_total = gateway_key.token_limit_total
        config.request_limit_total = gateway_key.request_limit_total
        return key_configuration_export(config)

    async def reset_gateway_key_usage(
        self,
        payload: ResetGatewayKeyUsageInput,
    ) -> GatewayKeyManagementResult:
        """Reset selected counters without deleting usage ledger history."""
        if not payload.reset_used_counters and not payload.reset_reserved_counters:
            raise InvalidGatewayKeyUsageResetError("At least one counter family must be reset")

        gateway_key = await self._get_gateway_key(payload.gateway_key_id)
        self._require_not_external_tool_fenced(gateway_key, operation="usage reset")
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
        self._require_not_external_tool_fenced(old_key, operation="key rotation")

        active_hmac_version, active_hmac_secret = self._settings.get_active_hmac_secret()
        if not self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY:
            raise GatewayKeyRotationError(
                "ONE_TIME_SECRET_ENCRYPTION_KEY is required for key rotation"
            )

        new_valid_from = payload.new_valid_from or old_key.valid_from
        new_valid_until = payload.new_valid_until or old_key.valid_until
        self._validate_validity_window(valid_from=new_valid_from, valid_until=new_valid_until)
        external_tool_policy = self._external_tool_policy_from_key(old_key)
        if external_tool_policy.mode == EXTERNAL_TOOL_FENCED and not payload.preserve_limits:
            raise GatewayKeyRotationError(
                "External-tool fenced keys must preserve finite limits during rotation"
            )

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
            allowed_endpoints=list(old_key.allowed_endpoints)
            if payload.preserve_allowed_endpoints
            else [],
            allow_all_models=old_key.allow_all_models if payload.preserve_allowed_models else False,
            allow_all_endpoints=old_key.allow_all_endpoints
            if payload.preserve_allowed_endpoints
            else False,
            key_purpose=getattr(old_key, "key_purpose", KEY_PURPOSE_STANDARD),
            capability_policy_mode=getattr(
                old_key,
                "capability_policy_mode",
                CAPABILITY_POLICY_MODE_STANDARD,
            ),
            calibration_metadata=dict(getattr(old_key, "calibration_metadata", {}) or {}),
            template_id=getattr(old_key, "template_id", None),
            template_revision_id=getattr(old_key, "template_revision_id", None),
            rate_limit_requests_per_minute=(
                old_key.rate_limit_requests_per_minute
                if payload.preserve_rate_limit_policy
                else None
            ),
            rate_limit_tokens_per_minute=(
                old_key.rate_limit_tokens_per_minute if payload.preserve_rate_limit_policy else None
            ),
            max_concurrent_requests=(
                old_key.max_concurrent_requests if payload.preserve_rate_limit_policy else None
            ),
            metadata_json=self._metadata_with_external_tool_policy(
                self._metadata_with_chat_streaming_live_burn_policy(
                    self._metadata_with_responses_streaming_live_burn_policy(
                        self._metadata_with_lazy_throttling_policy(
                            (
                                self._metadata_with_rate_limit_window(
                                    self._metadata_with_provider_policy(
                                        self._metadata_with_responses_policy(
                                            {},
                                            self._responses_policy_from_key(old_key),
                                        ),
                                        self._allowed_providers_from_key(old_key),
                                    ),
                                    self._rate_limit_policy_from_key(old_key) or {},
                                )
                                if payload.preserve_rate_limit_policy
                                else self._metadata_with_provider_policy(
                                    self._metadata_with_responses_policy(
                                        {},
                                        self._responses_policy_from_key(old_key),
                                    ),
                                    self._allowed_providers_from_key(old_key),
                                )
                            ),
                            (
                                self._lazy_throttling_policy_from_key(old_key)
                                if payload.preserve_rate_limit_policy
                                else None
                            ),
                        ),
                        default_responses_streaming_live_burn_policy(),
                    ),
                    self._chat_streaming_live_burn_policy_from_key(old_key),
                ),
                external_tool_policy,
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
        expires_at = self._now() + timedelta(
            seconds=self._settings.EMAIL_KEY_SECRET_MAX_AGE_SECONDS
        )
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
            owner_id=old_key.owner_id,
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
    def _require_not_external_tool_fenced(gateway_key: object, *, operation: str) -> None:
        """Block management mutations while an exclusive external-tool fence is bound.

        Suspend, revoke, and activate are intentionally not guarded here; they change
        key status only and must never clear a bound fence or its reservation.
        """
        if getattr(gateway_key, "external_tool_fence_state", "none") in ("active", "held"):
            raise GatewayKeyExternalToolFenceActiveError(
                f"{GatewayKeyExternalToolFenceActiveError.message} (blocked operation: {operation})"
            )

    @staticmethod
    def _require_status(
        gateway_key: GatewayKey, *, allowed: tuple[str, ...], operation: str
    ) -> None:
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
            raise InvalidGatewayKeyValidityError(
                "valid_from must be timezone-aware", param="valid_from"
            )
        if valid_until.tzinfo is None:
            raise InvalidGatewayKeyValidityError(
                "valid_until must be timezone-aware", param="valid_until"
            )
        if valid_until <= valid_from:
            raise InvalidGatewayKeyValidityError(
                "valid_until must be after valid_from", param="valid_until"
            )

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
        for key in (
            "requests_per_minute",
            "tokens_per_minute",
            "max_concurrent_requests",
            "window_seconds",
        ):
            value = policy.get(key)
            if key == "max_concurrent_requests" and value is None:
                value = policy.get("concurrent_requests")
            if value is None:
                continue
            self._validate_optional_positive_int(value, param=key)
            normalized[key] = value
        return normalized

    def _validate_lazy_throttling_policy(
        self,
        policy: dict[str, object] | None,
    ) -> dict[str, object] | None:
        """Strictly validate an explicit lazy (waiting) throttling policy.

        Returns the normalized metadata dict, or ``None`` for the default
        immediate-rejection policy. Unknown keys, booleans, zero/negative,
        non-integer, or ceiling-exceeding values are refused. ``mode`` must
        be exactly ``reject`` or ``wait``; ``reject`` (or absent policy)
        never stores waiting fields.
        """
        if policy is None:
            return None
        if not isinstance(policy, dict):
            raise InvalidGatewayKeyLimitsError(
                "Lazy throttling policy must be an object.",
                param="lazy_throttling_policy",
            )
        allowed = {"mode", "max_wait_seconds", "max_waiting_requests"}
        unknown = sorted(str(k) for k in set(policy) - allowed)
        if unknown:
            raise InvalidGatewayKeyLimitsError(
                f"Unknown lazy throttling policy field: {unknown[0]}",
                param=unknown[0],
            )
        if not all(isinstance(k, str) for k in policy):
            raise InvalidGatewayKeyLimitsError(
                "Lazy throttling policy fields must be named.",
                param="lazy_throttling_policy",
            )
        mode = policy.get("mode")
        if mode is None:
            if "max_wait_seconds" in policy or "max_waiting_requests" in policy:
                raise InvalidGatewayKeyLimitsError(
                    "Waiting fields require lazy throttling mode wait.",
                    param="mode",
                )
            return None
        if not isinstance(mode, str) or mode not in ("reject", "wait"):
            raise InvalidGatewayKeyLimitsError(
                "Lazy throttling mode must be reject or wait.",
                param="mode",
            )
        if mode == "reject":
            # Deterministic default; any waiting fields are stripped so a
            # disabled policy can never silently grant waiting.
            return None

        def _strict_bounded_int(value: object, *, param: str, ceiling: int) -> int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidGatewayKeyLimitsError(
                    f"Lazy throttling {param} must be an integer.",
                    param=param,
                )
            if value <= 0:
                raise InvalidGatewayKeyLimitsError(
                    f"Lazy throttling {param} must be positive.",
                    param=param,
                )
            if value > ceiling:
                raise InvalidGatewayKeyLimitsError(
                    f"Lazy throttling {param} exceeds the operator ceiling.",
                    param=param,
                )
            return value

        max_wait = policy.get("max_wait_seconds", 30)
        max_waiting = policy.get("max_waiting_requests", 2)
        return {
            "mode": "wait",
            "max_wait_seconds": _strict_bounded_int(
                max_wait,
                param="max_wait_seconds",
                ceiling=self._settings.LAZY_THROTTLING_MAX_WAIT_SECONDS,
            ),
            "max_waiting_requests": _strict_bounded_int(
                max_waiting,
                param="max_waiting_requests",
                ceiling=self._settings.LAZY_THROTTLING_MAX_WAITING_PER_KEY,
            ),
        }

    def _validate_chat_streaming_live_burn_policy(
        self,
        policy: dict[str, object] | ChatStreamingLiveBurnPolicy | None,
    ) -> ChatStreamingLiveBurnPolicy:
        try:
            return normalize_chat_streaming_live_burn_policy(
                policy,
                max_abs_cost_margin_eur=self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
                max_abs_token_margin=self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError as exc:
            raise InvalidGatewayKeyPolicyError(str(exc), param=exc.param) from exc

    def _validate_key_purpose_and_policy_mode(
        self,
        *,
        key_purpose: str,
        capability_policy_mode: str,
    ) -> tuple[str, str]:
        purpose = str(key_purpose or KEY_PURPOSE_STANDARD).strip()
        mode = str(
            capability_policy_mode or default_capability_policy_mode_for_purpose(purpose)
        ).strip()
        if purpose not in KEY_PURPOSE_VALUES:
            raise InvalidGatewayKeyPolicyError("Unsupported key purpose.", param="key_purpose")
        if mode not in CAPABILITY_POLICY_MODE_VALUES:
            raise InvalidGatewayKeyPolicyError(
                "Unsupported capability policy mode.",
                param="capability_policy_mode",
            )
        if purpose == KEY_PURPOSE_STANDARD and mode != CAPABILITY_POLICY_MODE_STANDARD:
            raise InvalidGatewayKeyPolicyError(
                "Standard keys must use standard capability policy mode.",
                param="capability_policy_mode",
            )
        if (
            purpose == KEY_PURPOSE_TRUSTED_CALIBRATION
            and mode != CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
        ):
            raise InvalidGatewayKeyPolicyError(
                "Trusted calibration keys must use trusted calibration discovery mode.",
                param="capability_policy_mode",
            )
        return purpose, mode

    def _validate_trusted_calibration_create_policy(
        self,
        *,
        key_purpose: str,
        capability_policy_mode: str,
        valid_from: datetime,
        valid_until: datetime,
        request_limit_total: int | None,
        confirmed: bool,
        reason: str | None,
    ) -> None:
        if not is_trusted_calibration_key(
            key_purpose=key_purpose,
            capability_policy_mode=capability_policy_mode,
        ):
            return
        if not self._settings.CALIBRATION_KEYS_ENABLED:
            raise InvalidGatewayKeyPolicyError(
                "Trusted calibration keys are disabled by configuration.",
                param="key_purpose",
            )
        if not confirmed:
            raise InvalidGatewayKeyPolicyError(
                "Confirm trusted calibration mode before creating this key.",
                param="confirm_trusted_calibration",
            )
        if not reason or not reason.strip():
            raise InvalidGatewayKeyPolicyError(
                "Enter an audit reason for trusted calibration key creation.",
                param="reason",
            )
        if request_limit_total is None:
            raise InvalidGatewayKeyLimitsError(
                "Trusted calibration keys require request_limit_total.",
                param="request_limit_total",
            )
        if request_limit_total > self._settings.TRUSTED_CALIBRATION_MAX_REQUESTS:
            raise InvalidGatewayKeyLimitsError(
                "Trusted calibration request limit exceeds the configured maximum.",
                param="request_limit_total",
            )
        max_validity = timedelta(days=self._settings.TRUSTED_CALIBRATION_MAX_VALID_DAYS)
        if valid_until - valid_from > max_validity:
            raise InvalidGatewayKeyValidityError(
                "Trusted calibration validity exceeds the configured maximum.",
                param="valid_until",
            )

    @staticmethod
    def _safe_calibration_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
        return sanitize_metadata_mapping(metadata or {}, drop_content_keys=True)

    @staticmethod
    def _safe_responses_policy(policy: dict[str, object] | None) -> dict[str, object] | None:
        if policy is None:
            return None
        sanitized = sanitize_metadata_mapping(policy, drop_content_keys=True)
        return sanitized if isinstance(sanitized, dict) else None

    async def _validate_request_policy(
        self,
        *,
        allowed_models: list[str],
        allowed_endpoints: list[str],
        allow_all_models: bool,
        allow_all_endpoints: bool,
    ) -> GatewayKeyPolicy:
        return await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=allowed_models,
                allowed_endpoints=allowed_endpoints,
                allow_all_models=allow_all_models,
                allow_all_endpoints=allow_all_endpoints,
            ),
            model_routes_repository=self._model_routes_repository,
        )

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


    @staticmethod
    def _metadata_with_lazy_throttling_policy(
        metadata_json: dict[str, object] | None,
        policy: dict[str, object] | None,
    ) -> dict[str, object]:
        metadata = dict(metadata_json or {})
        if policy:
            metadata["lazy_throttling_policy"] = dict(policy)
        else:
            metadata.pop("lazy_throttling_policy", None)
        return metadata

    def _metadata_with_chat_streaming_live_burn_policy(
        self,
        metadata_json: dict[str, object] | None,
        policy: dict[str, object] | ChatStreamingLiveBurnPolicy | None,
    ) -> dict[str, object]:
        try:
            return metadata_with_chat_streaming_live_burn_policy(
                metadata_json,
                policy,
                max_abs_cost_margin_eur=self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
                max_abs_token_margin=self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError as exc:
            raise InvalidGatewayKeyPolicyError(str(exc), param=exc.param) from exc

    def _metadata_with_responses_streaming_live_burn_policy(
        self,
        metadata_json: dict[str, object] | None,
        policy: dict[str, object] | None,
    ) -> dict[str, object]:
        try:
            return metadata_with_responses_streaming_live_burn_policy(
                metadata_json,
                policy,
                max_abs_cost_margin_eur=(
                    self._settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR
                ),
                max_abs_token_margin=(
                    self._settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN
                ),
            )
        except ResponsesStreamingLiveBurnPolicyError as exc:
            raise InvalidGatewayKeyPolicyError(str(exc), param=exc.param) from exc

    @staticmethod
    def _metadata_with_provider_policy(
        metadata_json: dict[str, object] | None,
        allowed_providers: list[str] | None,
    ) -> dict[str, object]:
        metadata = dict(metadata_json or {})
        if allowed_providers is None:
            metadata.pop("allowed_providers", None)
            return metadata
        metadata["allowed_providers"] = [
            str(provider).strip() for provider in allowed_providers if str(provider).strip()
        ]
        return metadata

    @classmethod
    def _metadata_with_responses_policy(
        cls,
        metadata_json: dict[str, object] | None,
        responses_policy: dict[str, object] | None,
    ) -> dict[str, object]:
        metadata = dict(metadata_json or {})
        safe_policy = cls._safe_responses_policy(responses_policy)
        if safe_policy is None:
            metadata.pop("responses_policy", None)
            return metadata
        metadata["responses_policy"] = safe_policy
        return metadata

    @staticmethod
    def _metadata_with_external_tool_policy(
        metadata_json: dict[str, object] | None,
        policy: ExternalToolKeyPolicy,
    ) -> dict[str, object]:
        metadata = dict(metadata_json or {})
        metadata["external_tool_policy"] = policy.to_metadata()
        return metadata

    def _validate_external_tool_policy(
        self,
        value: object,
        *,
        key_purpose: str,
        request_limit_total: int | None,
        token_limit_total: int | None,
        cost_limit_eur: Decimal | None,
        confirmed: bool,
        reason: str | None,
        require_reason: bool,
    ) -> ExternalToolKeyPolicy:
        parsed = parse_key_external_tool_policy(
            value,
            ceilings=self._settings.get_external_tool_operator_ceilings(),
        )
        if not parsed.valid or parsed.policy is None:
            raise InvalidGatewayKeyPolicyError(
                "External-tool policy is invalid or exceeds installation ceilings.",
                param="external_tool_policy",
            )
        policy = parsed.policy
        if policy.mode != EXTERNAL_TOOL_FENCED:
            return policy
        if key_purpose != KEY_PURPOSE_STANDARD:
            raise InvalidGatewayKeyPolicyError(
                "External-tool fenced policy is available only to standard keys.",
                param="external_tool_policy",
            )
        if not confirmed:
            raise InvalidGatewayKeyPolicyError(
                "Confirm the external-tool fenced overrun and hold policy.",
                param="confirm_external_tool_fenced",
            )
        if require_reason and not (reason or "").strip():
            raise InvalidGatewayKeyPolicyError(
                "Enter an audit reason before updating external-tool policy.",
                param="reason",
            )
        self._validate_external_tool_limits(
            request_limit_total=request_limit_total,
            token_limit_total=token_limit_total,
            cost_limit_eur=cost_limit_eur,
        )
        return policy

    @staticmethod
    def _validate_external_tool_limits(
        *,
        request_limit_total: int | None,
        token_limit_total: int | None,
        cost_limit_eur: Decimal | None,
    ) -> None:
        if (
            type(request_limit_total) is not int
            or request_limit_total <= 0
            or type(token_limit_total) is not int
            or token_limit_total <= 0
            or not isinstance(cost_limit_eur, Decimal)
            or not cost_limit_eur.is_finite()
            or cost_limit_eur <= 0
        ):
            raise InvalidGatewayKeyPolicyError(
                "External-tool fenced policy requires positive finite request, token, and EUR limits.",
                param="external_tool_policy",
            )

    def _external_tool_policy_from_key(self, gateway_key: GatewayKey) -> ExternalToolKeyPolicy:
        metadata = getattr(gateway_key, "metadata_json", None)
        raw_policy = metadata.get("external_tool_policy") if isinstance(metadata, dict) else None
        parsed = parse_key_external_tool_policy(
            raw_policy,
            ceilings=self._settings.get_external_tool_operator_ceilings(),
        )
        return parsed.policy if parsed.valid and parsed.policy is not None else strict_key_policy()

    @classmethod
    def _responses_policy_from_key(cls, gateway_key: GatewayKey) -> dict[str, object] | None:
        metadata = getattr(gateway_key, "metadata_json", None)
        raw_policy = metadata.get("responses_policy") if isinstance(metadata, dict) else None
        return cls._safe_responses_policy(raw_policy if isinstance(raw_policy, dict) else None)

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

    def _lazy_throttling_policy_from_key(
        self,
        gateway_key: GatewayKey,
    ) -> dict[str, object] | None:
        """Strictly project the key's stored lazy-throttling policy.

        Malformed, unknown, or ceiling-exceeding stored values never surface
        as policy: they parse to the safe default (immediate rejection)
        instead of being copied into DTOs, audit values, or rotated keys.
        """
        metadata = getattr(gateway_key, "metadata_json", None) or {}
        raw = metadata.get("lazy_throttling_policy")
        policy = parse_lazy_throttling_policy_metadata(
            raw,
            max_wait_seconds_ceiling=self._settings.LAZY_THROTTLING_MAX_WAIT_SECONDS,
            max_waiting_per_key_ceiling=self._settings.LAZY_THROTTLING_MAX_WAITING_PER_KEY,
        )
        # A stored reject-mode policy means "no waiting", exactly like a
        # missing one; only an explicit wait policy projects through.
        if policy is None or not policy.is_wait_mode():
            return None
        return policy.to_metadata()

    def _lazy_throttling_audit_values(self, gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "lazy_throttling_policy": self._lazy_throttling_policy_from_key(gateway_key),
        }

    def _chat_streaming_live_burn_audit_values(self, gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "chat_streaming_live_burn_policy": self._chat_streaming_live_burn_policy_from_key(
                gateway_key
            ).to_metadata(),
        }

    def _external_tool_policy_audit_values(self, gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "external_tool_policy": self._external_tool_policy_from_key(gateway_key).to_metadata(),
        }

    @staticmethod
    def _policy_audit_values(gateway_key: GatewayKey) -> dict[str, object]:
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "allowed_models": list(gateway_key.allowed_models or []),
            "allowed_endpoints": list(gateway_key.allowed_endpoints or []),
            "allowed_providers": KeyService._allowed_providers_from_key(gateway_key),
            "allow_all_models": gateway_key.allow_all_models,
            "allow_all_endpoints": gateway_key.allow_all_endpoints,
        }

    def _configuration_audit_values(self, gateway_key: GatewayKey) -> dict[str, object]:
        """Full administtered-policy projection for one configuration audit."""
        return {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "allowed_models": list(gateway_key.allowed_models or []),
            "allowed_endpoints": list(gateway_key.allowed_endpoints or []),
            "allowed_providers": self._allowed_providers_from_key(gateway_key),
            "allow_all_models": gateway_key.allow_all_models,
            "allow_all_endpoints": gateway_key.allow_all_endpoints,
            "responses_policy": self._responses_policy_audit_projection(
                (gateway_key.metadata_json or {}).get("responses_policy")
                if isinstance(gateway_key.metadata_json, dict)
                else None
            ),
            "rate_limit_policy": self._rate_limit_policy_from_key(gateway_key),
            "lazy_throttling_policy": self._lazy_throttling_policy_from_key(gateway_key),
            "chat_streaming_live_burn_policy": self._chat_streaming_live_burn_policy_from_key(
                gateway_key
            ).to_metadata(),
            "external_tool_policy": self._external_tool_policy_from_key(gateway_key).to_metadata(),
            "cost_limit_eur": (
                str(gateway_key.cost_limit_eur)
                if gateway_key.cost_limit_eur is not None
                else None
            ),
            "token_limit_total": gateway_key.token_limit_total,
            "request_limit_total": gateway_key.request_limit_total,
        }

    # Allowlisted responses-policy fields projected into configuration
    # audits. Unknown stored keys are counted with a fixed marker and never
    # copied; wrong-typed known values are omitted the same way.
    _RESPONSES_AUDIT_FIELDS: frozenset[str] = frozenset(
        {
            "version",
            "allowed_capabilities",
            "allowed_local_tool_types",
            "client_module",
            "hosted_tools_allowed",
            "stateful",
            "storage",
            "background",
            "multimodal",
            "notes",
        }
    )
    _RESPONSES_AUDIT_TOOL_TYPES: frozenset[str] = frozenset({"function", "custom"})
    _RESPONSES_AUDIT_PIN_KEYS: tuple[str, ...] = ("id", "version", "fixture_sha256")
    _RESPONSES_AUDIT_NOTES_MAX = 1000

    @classmethod
    def _responses_policy_audit_projection(
        cls, raw_policy: object
    ) -> dict[str, object] | str | None:
        """Secret-safe allowlisted projection of the stored Responses policy.

        Only reviewed field names with safe types are projected. Unknown
        names/values and wrong-typed known fields never reach the audit:
        they increment a fixed ``unsupported_fields`` count instead. A
        non-object stored block projects to the fixed ``"unsupported"``
        marker.
        """
        if raw_policy is None:
            return None
        if not isinstance(raw_policy, dict):
            return "unsupported"
        projected: dict[str, object] = {}
        unsupported = 0
        for key in sorted(set(raw_policy) - cls._RESPONSES_AUDIT_FIELDS):
            unsupported += 1
        if "version" in raw_policy:
            version = raw_policy["version"]
            if isinstance(version, int) and not isinstance(version, bool):
                projected["version"] = version
            else:
                unsupported += 1
        if "allowed_capabilities" in raw_policy:
            caps = raw_policy["allowed_capabilities"]
            if isinstance(caps, list) and all(isinstance(c, str) for c in caps):
                projected["allowed_capabilities"] = sorted(caps)
            else:
                unsupported += 1
        if "allowed_local_tool_types" in raw_policy:
            tool_types = raw_policy["allowed_local_tool_types"]
            if isinstance(tool_types, list) and all(
                isinstance(t, str) and t in cls._RESPONSES_AUDIT_TOOL_TYPES
                for t in tool_types
            ):
                projected["allowed_local_tool_types"] = list(tool_types)
            else:
                unsupported += 1
        if "client_module" in raw_policy:
            pin = raw_policy["client_module"]
            if (
                isinstance(pin, dict)
                and set(pin) == set(cls._RESPONSES_AUDIT_PIN_KEYS)
                and all(
                    isinstance(pin[key], str) and pin[key].strip()
                    for key in cls._RESPONSES_AUDIT_PIN_KEYS
                )
            ):
                projected["client_module"] = {
                    key: pin[key] for key in cls._RESPONSES_AUDIT_PIN_KEYS
                }
            else:
                unsupported += 1
        if "hosted_tools_allowed" in raw_policy:
            hosted = raw_policy["hosted_tools_allowed"]
            if isinstance(hosted, list) and not hosted:
                projected["hosted_tools_allowed"] = []
            else:
                unsupported += 1
        for flag in ("stateful", "storage", "background", "multimodal"):
            if flag in raw_policy:
                if raw_policy[flag] is False:
                    projected[flag] = False
                else:
                    unsupported += 1
        if "notes" in raw_policy:
            notes = raw_policy["notes"]
            if isinstance(notes, str) and len(notes) <= cls._RESPONSES_AUDIT_NOTES_MAX:
                projected["notes"] = notes
            else:
                unsupported += 1
        if unsupported:
            projected["unsupported_fields"] = unsupported
        return projected

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

    def _management_result(
        self,
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
            rate_limit_policy=self._rate_limit_policy_from_key(gateway_key),
            lazy_throttling_policy=self._lazy_throttling_policy_from_key(gateway_key),
            allowed_models=list(gateway_key.allowed_models or []),
            allowed_endpoints=list(gateway_key.allowed_endpoints or []),
            allow_all_models=gateway_key.allow_all_models,
            allow_all_endpoints=gateway_key.allow_all_endpoints,
            key_purpose=gateway_key.key_purpose,
            capability_policy_mode=gateway_key.capability_policy_mode,
            chat_streaming_live_burn_policy=self._chat_streaming_live_burn_policy_from_key_static(
                gateway_key
            ).to_metadata(),
            external_tool_policy=self._external_tool_policy_from_key(gateway_key).to_metadata(),
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

    def _chat_streaming_live_burn_policy_from_key(
        self,
        gateway_key: GatewayKey,
    ) -> ChatStreamingLiveBurnPolicy:
        try:
            return chat_streaming_live_burn_policy_from_metadata(
                gateway_key.metadata_json,
                max_abs_cost_margin_eur=self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
                max_abs_token_margin=self._settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError:
            return default_chat_streaming_live_burn_policy()

    @staticmethod
    def _allowed_providers_from_key(gateway_key: GatewayKey) -> list[str] | None:
        metadata_json = getattr(gateway_key, "metadata_json", None)
        if not isinstance(metadata_json, dict):
            return None
        providers = metadata_json.get("allowed_providers")
        if providers is None:
            return None
        if isinstance(providers, list):
            return [str(provider).strip() for provider in providers if str(provider).strip()]
        return []

    @staticmethod
    def _chat_streaming_live_burn_policy_from_key_static(
        gateway_key: GatewayKey,
    ) -> ChatStreamingLiveBurnPolicy:
        metadata_json = getattr(gateway_key, "metadata_json", None)
        if isinstance(metadata_json, dict):
            policy = metadata_json.get(CHAT_STREAMING_LIVE_BURN_METADATA_KEY)
            if isinstance(policy, dict):
                enabled = policy.get("enabled", True)
                cost_margin = policy.get("cost_margin_eur", "0.000000000")
                token_margin = policy.get("token_margin", 0)
                try:
                    return ChatStreamingLiveBurnPolicy(
                        enabled=enabled if isinstance(enabled, bool) else True,
                        cost_margin_eur=Decimal(str(cost_margin)),
                        token_margin=token_margin
                        if isinstance(token_margin, int)
                        else int(str(token_margin)),
                    )
                except (InvalidOperation, ValueError, TypeError):
                    return default_chat_streaming_live_burn_policy()
        return default_chat_streaming_live_burn_policy()
