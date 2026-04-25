"""Service-layer workflow for safe gateway key creation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, CreatedGatewayKey
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

        rate_limit_policy = payload.rate_limit_policy or {}
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
        expires_at = datetime.now(UTC) + timedelta(hours=24)
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
        )

    @staticmethod
    def _extract_version_number(version: str) -> int:
        match = re.fullmatch(r"v(\d+)", version.strip().lower())
        if not match:
            raise ValueError(f"invalid version format: {version!r}")
        return int(match.group(1))
