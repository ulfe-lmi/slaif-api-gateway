"""Service workflow for pending gateway-key email delivery."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.email_templates import (
    GatewayKeyEmailContext,
    gateway_key_email_subject,
    render_gateway_key_email,
)
from slaif_gateway.services.secret_service import SecretService
from slaif_gateway.utils.redaction import redact_text

KEY_EMAIL_PURPOSES = ("gateway_key_email", "gateway_key_rotation_email")


@dataclass(frozen=True, slots=True)
class PendingKeyEmailResult:
    """Safe result metadata for key email delivery."""

    email_delivery_id: uuid.UUID
    one_time_secret_id: uuid.UUID
    gateway_key_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    recipient_email: str | None
    status: str
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class EmailDeliveryService:
    """Coordinates secret consumption, rendering, SMTP sending, and audit rows."""

    def __init__(
        self,
        *,
        settings: Settings,
        one_time_secrets_repository: OneTimeSecretsRepository,
        email_deliveries_repository: EmailDeliveriesRepository,
        gateway_keys_repository: GatewayKeysRepository,
        owners_repository: OwnersRepository,
        audit_repository: AuditRepository,
        email_service: EmailService,
        now_factory: object | None = None,
    ) -> None:
        self._settings = settings
        self._one_time_secrets_repository = one_time_secrets_repository
        self._email_deliveries_repository = email_deliveries_repository
        self._gateway_keys_repository = gateway_keys_repository
        self._owners_repository = owners_repository
        self._audit_repository = audit_repository
        self._email_service = email_service
        self._now_factory = now_factory

    async def send_pending_key_email(
        self,
        *,
        one_time_secret_id: uuid.UUID,
        email_delivery_id: uuid.UUID | None = None,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> PendingKeyEmailResult:
        """Send a gateway key from an existing encrypted one-time-secret row.

        Policy: the secret row is locked and decrypted, SMTP is attempted while
        the transaction remains open, and `consumed_at` is set only after SMTP
        success. Failed SMTP attempts mark the delivery failed without consuming
        the one-time secret.
        """
        now = self._now()
        delivery_id_for_failure = email_delivery_id
        secret_service = SecretService(
            settings=self._settings,
            one_time_secrets_repository=self._one_time_secrets_repository,
        )
        try:
            decrypted = None
            for purpose in KEY_EMAIL_PURPOSES:
                try:
                    decrypted = await secret_service.decrypt_pending_one_time_secret_for_update(
                        one_time_secret_id,
                        purpose=purpose,
                        now=now,
                    )
                    break
                except EmailError as exc:
                    if exc.error_code == "one_time_secret_wrong_purpose":
                        continue
                    raise
            if decrypted is None:
                raise EmailError("One-time secret purpose is not deliverable by email")

            payload = _parse_secret_payload(decrypted.plaintext)
            gateway_key_id = _coerce_uuid(payload.get("gateway_key_id")) or decrypted.row.gateway_key_id
            owner_id = _coerce_uuid(payload.get("owner_id")) or decrypted.row.owner_id
            gateway_key = (
                await self._gateway_keys_repository.get_gateway_key_by_id(gateway_key_id)
                if gateway_key_id is not None
                else None
            )
            owner = await self._owners_repository.get_owner_by_id(owner_id) if owner_id is not None else None
            if gateway_key is None or owner is None:
                raise EmailError("Key email metadata is incomplete")

            subject = gateway_key_email_subject(rotation=decrypted.row.purpose == "gateway_key_rotation_email")
            email_delivery = await self._resolve_email_delivery(
                email_delivery_id=email_delivery_id,
                owner_id=owner.id,
                gateway_key_id=gateway_key.id,
                one_time_secret_id=decrypted.row.id,
                recipient_email=owner.email,
                subject=subject,
            )
            delivery_id_for_failure = email_delivery.id
            body = render_gateway_key_email(
                GatewayKeyEmailContext(
                    owner_name=owner.name,
                    owner_surname=owner.surname,
                    owner_email=owner.email,
                    plaintext_gateway_key=str(payload["plaintext_key"]),
                    api_base_url=self._settings.PUBLIC_BASE_URL,
                    valid_from=gateway_key.valid_from,
                    valid_until=gateway_key.valid_until,
                    cost_limit_eur=gateway_key.cost_limit_eur,
                    token_limit_total=gateway_key.token_limit_total,
                    request_limit_total=gateway_key.request_limit_total,
                    rotation=decrypted.row.purpose == "gateway_key_rotation_email",
                )
            )
            send_result = await self._email_service.send_email(
                to=owner.email,
                subject=subject,
                text_body=body,
            )
            consumed = await secret_service.mark_consumed(decrypted.row.id, consumed_at=self._now())
            if not consumed:
                raise EmailError("One-time secret was consumed by another delivery attempt")

            sent_at = self._now()
            await self._email_deliveries_repository.mark_sent(
                email_delivery.id,
                sent_at=sent_at,
                provider_message_id=send_result.message_id,
            )
            await self._audit_repository.add_audit_log(
                action="email_key",
                entity_type="email_delivery",
                entity_id=email_delivery.id,
                admin_user_id=actor_admin_id,
                note=reason,
                new_values={
                    "email_delivery_id": str(email_delivery.id),
                    "one_time_secret_id": str(decrypted.row.id),
                    "gateway_key_id": str(gateway_key.id),
                    "owner_id": str(owner.id),
                    "status": "sent",
                },
            )
            return PendingKeyEmailResult(
                email_delivery_id=email_delivery.id,
                one_time_secret_id=decrypted.row.id,
                gateway_key_id=gateway_key.id,
                owner_id=owner.id,
                recipient_email=owner.email,
                status="sent",
                provider_message_id=send_result.message_id,
            )
        except EmailError as exc:
            return await self._record_failed_delivery(
                one_time_secret_id=one_time_secret_id,
                email_delivery_id=delivery_id_for_failure,
                actor_admin_id=actor_admin_id,
                reason=reason,
                error=exc,
            )

    async def create_pending_key_email_delivery(
        self,
        *,
        gateway_key_id: uuid.UUID,
        one_time_secret_id: uuid.UUID,
        owner_id: uuid.UUID,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> PendingKeyEmailResult:
        """Create safe pending delivery metadata for an existing one-time secret."""
        one_time_secret = await self._one_time_secrets_repository.get_one_time_secret_by_id(
            one_time_secret_id
        )
        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id(gateway_key_id)
        owner = await self._owners_repository.get_owner_by_id(owner_id)
        if one_time_secret is None or gateway_key is None or owner is None:
            raise EmailError("Key email metadata is incomplete")
        if one_time_secret.gateway_key_id != gateway_key.id or one_time_secret.owner_id != owner.id:
            raise EmailError("One-time secret does not match the requested key email metadata")
        if one_time_secret.purpose not in KEY_EMAIL_PURPOSES:
            raise EmailError("One-time secret purpose is not deliverable by email")
        if one_time_secret.status != "pending" or one_time_secret.consumed_at is not None:
            raise EmailError("One-time secret is not pending")

        subject = gateway_key_email_subject(rotation=one_time_secret.purpose == "gateway_key_rotation_email")
        email_delivery = await self._email_deliveries_repository.create_email_delivery(
            recipient_email=owner.email,
            subject=subject,
            template_name="gateway_key_email",
            owner_id=owner.id,
            gateway_key_id=gateway_key.id,
            one_time_secret_id=one_time_secret.id,
            status="pending",
        )
        await self._audit_repository.add_audit_log(
            action="email_key_delivery_created",
            entity_type="email_delivery",
            entity_id=email_delivery.id,
            admin_user_id=actor_admin_id,
            note=reason,
            new_values={
                "email_delivery_id": str(email_delivery.id),
                "one_time_secret_id": str(one_time_secret.id),
                "gateway_key_id": str(gateway_key.id),
                "owner_id": str(owner.id),
                "status": "pending",
            },
        )
        return PendingKeyEmailResult(
            email_delivery_id=email_delivery.id,
            one_time_secret_id=one_time_secret.id,
            gateway_key_id=gateway_key.id,
            owner_id=owner.id,
            recipient_email=owner.email,
            status="pending",
        )

    async def _resolve_email_delivery(
        self,
        *,
        email_delivery_id: uuid.UUID | None,
        owner_id: uuid.UUID,
        gateway_key_id: uuid.UUID,
        one_time_secret_id: uuid.UUID,
        recipient_email: str,
        subject: str,
    ):
        if email_delivery_id is not None:
            existing = await self._email_deliveries_repository.get_email_delivery_by_id(email_delivery_id)
            if existing is not None:
                return existing

        return await self._email_deliveries_repository.create_email_delivery(
            recipient_email=recipient_email,
            subject=subject,
            template_name="gateway_key_email",
            owner_id=owner_id,
            gateway_key_id=gateway_key_id,
            one_time_secret_id=one_time_secret_id,
            status="pending",
        )

    async def _record_failed_delivery(
        self,
        *,
        one_time_secret_id: uuid.UUID,
        email_delivery_id: uuid.UUID | None,
        actor_admin_id: uuid.UUID | None,
        reason: str | None,
        error: EmailError,
    ) -> PendingKeyEmailResult:
        failed_at = self._now()
        safe_message = redact_text(error.safe_message)
        delivery_id = email_delivery_id
        if delivery_id is not None:
            await self._email_deliveries_repository.mark_failed(
                delivery_id,
                failed_at=failed_at,
                error_message=safe_message,
            )
        await self._audit_repository.add_audit_log(
            action="email_key_failed",
            entity_type="email_delivery",
            entity_id=delivery_id,
            admin_user_id=actor_admin_id,
            note=reason,
            new_values={
                "email_delivery_id": str(delivery_id) if delivery_id else None,
                "one_time_secret_id": str(one_time_secret_id),
                "status": "failed",
                "error_code": error.error_code,
            },
        )
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id or uuid.UUID(int=0),
            one_time_secret_id=one_time_secret_id,
            gateway_key_id=None,
            owner_id=None,
            recipient_email=None,
            status="failed",
            error_code=error.error_code,
            error_message=safe_message,
        )

    def _now(self) -> datetime:
        if self._now_factory is not None:
            return self._now_factory()  # type: ignore[operator]
        return datetime.now(UTC)


def _parse_secret_payload(plaintext: str) -> dict[str, object]:
    payload = json.loads(plaintext)
    if not isinstance(payload, dict) or not payload.get("plaintext_key"):
        raise EmailError("One-time secret payload is invalid")
    return payload


def _coerce_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str) and value:
        return uuid.UUID(value)
    return None
