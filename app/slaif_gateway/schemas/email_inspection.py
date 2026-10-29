"""Typed request/result schemas for read-only email delivery inspection.

These schemas bound the CLI `email list` / `email show` inspection surface.
They carry allowlisted metadata only: no subject, rendered body, template
data, raw error prose, provider message IDs, encrypted payloads, nonces,
plaintext keys, or generic record dumps.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

# Persisted email_deliveries.status values (see models.STATUS_VALUES_EMAIL_DELIVERIES).
# `queued` is a CLI broker-submission result, NOT a persisted delivery status.
EMAIL_DELIVERY_STATUSES = ("pending", "sending", "sent", "failed", "ambiguous", "cancelled")

# Finite known email error codes, mirroring services/email_errors.py.
# Anything else recorded in audit metadata is projected to unavailable.
KNOWN_EMAIL_ERROR_CODES = frozenset(
    {
        "email_error",
        "email_delivery_disabled",
        "smtp_configuration_error",
        "smtp_send_error",
        "email_delivery_not_sendable",
        "email_delivery_in_progress",
        "email_delivery_ambiguous",
        "email_delivery_finalization_failed",
        "email_delivery_attempt_state_error",
        "one_time_secret_error",
        "one_time_secret_not_found",
        "one_time_secret_expired",
        "one_time_secret_already_consumed",
        "one_time_secret_wrong_purpose",
    }
)

# Fixed provenance label for the latest matching audit entry. The row may be
# historical (a `sent` delivery can retain a last-recorded failure) and is
# never labeled as the current attempt's error.
PROVENANCE_LAST_RECORDED_AUDIT_ERROR = "last recorded audit error"

# Service-derived secret lifecycle meanings (existing sendability vocabulary).
# `present` = pending usable material, NOT proof the email was sent.
SECRET_LIFECYCLE_VALUES = ("present", "consumed", "expired", "unavailable")

LIST_LIMIT_MIN = 1
LIST_LIMIT_MAX = 100
LIST_LIMIT_DEFAULT = 50
LIST_OFFSET_MIN = 0
LIST_OFFSET_MAX = 1000000


class EmailInspectionValidationError(ValueError):
    """Fixed safe validation failure for inspection inputs.

    Messages name the field only; supplied private values are never echoed.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.safe_message = message


@dataclass(frozen=True, slots=True)
class EmailDeliveryListItem:
    """Allowlisted metadata for one persisted email delivery row."""

    delivery_id: uuid.UUID
    owner_id: uuid.UUID | None
    gateway_key_id: uuid.UUID | None
    one_time_secret_id: uuid.UUID | None
    recipient_email: str
    status: str
    created_at: datetime
    sent_at: datetime | None = None
    failed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EmailDeliveryListPage:
    """One deterministic page of inspection results.

    Ordering is deterministic `(created_at DESC, id DESC)`; `total` is
    omitted because no count query is issued (honest lower-bound paging).
    """

    items: list[EmailDeliveryListItem] = field(default_factory=list)
    limit: int = LIST_LIMIT_DEFAULT
    offset: int = 0
    has_more: bool = False
    next_offset: int | None = None


@dataclass(frozen=True, slots=True)
class EmailDeliverySecretLifecycle:
    """Existing service-derived one-time-secret lifecycle/sendability.

    Reuses `EmailDeliveryService.get_key_email_delivery_sendability`
    meanings; `present` means pending usable material, not proof sent.
    """

    status: str
    can_send: bool
    blocking_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EmailDeliveryLastRecordedFailure:
    """Finite known email error code from the latest matching audit entry."""

    error_code: str
    action: str
    recorded_at: datetime
    provenance: str = PROVENANCE_LAST_RECORDED_AUDIT_ERROR


@dataclass(frozen=True, slots=True)
class EmailDeliveryDetail:
    """Allowlisted metadata for one delivery plus safe derived facts."""

    item: EmailDeliveryListItem
    secret_lifecycle: EmailDeliverySecretLifecycle | None = None
    last_recorded_failure: EmailDeliveryLastRecordedFailure | None = None


def validate_delivery_status(status: str) -> str:
    """Return the status when it is a persisted status; else raise."""
    if status not in EMAIL_DELIVERY_STATUSES:
        raise EmailInspectionValidationError(
            "status must be one of: " + ", ".join(EMAIL_DELIVERY_STATUSES)
        )
    return status


def normalize_owner_email(value: str) -> str:
    """Normalize an owner email exactly like OwnerService (strip/lower).

    Exact match semantics only; never a substring identity guess.
    """
    normalized = value.strip().lower()
    if not normalized:
        raise EmailInspectionValidationError("owner_email cannot be empty")
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise EmailInspectionValidationError("owner_email must be a valid email")
    return normalized


def require_aware_utc(value: datetime, *, field_name: str) -> datetime:
    """Inspection time bounds must be explicit aware UTC instants."""
    if value.tzinfo is None:
        raise EmailInspectionValidationError(f"{field_name} must be an explicit aware UTC datetime")
    return value


def validate_creation_window(
    created_from: datetime | None, created_until: datetime | None
) -> tuple[datetime | None, datetime | None]:
    """Validate inclusive creation bounds without echoing supplied values."""
    if created_from is not None:
        require_aware_utc(created_from, field_name="created_from")
    if created_until is not None:
        require_aware_utc(created_until, field_name="created_until")
    if created_from is not None and created_until is not None and created_from > created_until:
        raise EmailInspectionValidationError("created_from must not be later than created_until")
    return created_from, created_until


def validate_page(limit: int, offset: int) -> tuple[int, int]:
    """Bounded deterministic paging parameters."""
    if not LIST_LIMIT_MIN <= limit <= LIST_LIMIT_MAX:
        raise EmailInspectionValidationError(
            f"limit must be between {LIST_LIMIT_MIN} and {LIST_LIMIT_MAX}"
        )
    if not LIST_OFFSET_MIN <= offset <= LIST_OFFSET_MAX:
        raise EmailInspectionValidationError(
            f"offset must be between {LIST_OFFSET_MIN} and {LIST_OFFSET_MAX}"
        )
    return limit, offset
