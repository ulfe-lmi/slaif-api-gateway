"""Typed partial-edit inputs for single-record owner/cohort updates (204).

This is the smallest typed omission boundary for the ``owners update`` /
``cohorts update`` CLI surface:

- ``None`` means "omitted" and the current stored value is preserved;
- explicit clears exist ONLY for nullable fields (owner
  institution/external ID/notes, cohort description/starts_at/ends_at)
  and conflict with a simultaneous replacement (refused here, before any
  repository access);
- a no-field patch is refused;
- known-credential-shape values and unsafe audit reasons are refused
  with FIXED safe errors (finite recognized shapes through the existing
  redaction helpers, not a universal sanitizer);
- datetimes use the existing UTC-aware CLI convention (naive values are
  interpreted as UTC).

The shared services merge the parsed patch with the CURRENT stored row
under the row lock and then reuse the existing complete-update
normalization/validation/repository write/audit law.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from slaif_gateway.utils.redaction import (
    is_sensitive_key,
    normalize_sensitive_key,
    redact_text,
)

# Consistent with the existing operator audit-reason bound
# (services/openai_compatible_setup.py: 1024 UTF-8 bytes).
RECORD_UPDATE_REASON_MAX_BYTES = 1024

_SECRET_MARKERS = (
    "apikey",
    "authorization",
    "bearer",
    "encryptedpayload",
    "gatewaykey",
    "nonce",
    "passwordhash",
    "plaintextkey",
    "providerkey",
    "secret",
    "sessiontoken",
    "tokenhash",
)


@dataclass(frozen=True, slots=True)
class OwnerUpdatePatch:
    """Typed owner partial edit; None fields are omitted (preserved)."""

    name: str | None
    surname: str | None
    email: str | None
    institution_id: uuid.UUID | None
    clear_institution: bool
    external_id: str | None
    clear_external_id: bool
    notes: str | None
    clear_notes: bool
    is_active: bool | None


@dataclass(frozen=True, slots=True)
class CohortUpdatePatch:
    """Typed cohort partial edit; None fields are omitted (preserved)."""

    name: str | None
    description: str | None
    clear_description: bool
    starts_at: datetime | None
    clear_starts_at: bool
    ends_at: datetime | None
    clear_ends_at: bool


def parse_owner_update_patch(
    *,
    name: str | None,
    surname: str | None,
    email: str | None,
    institution_id: str | None,
    clear_institution: bool,
    external_id: str | None,
    clear_external_id: bool,
    notes: str | None,
    clear_notes: bool,
    active: bool,
    inactive: bool,
    actor_admin_id: str | None,
    reason: str | None,
) -> tuple[OwnerUpdatePatch, uuid.UUID | None, str]:
    """Strict, no-echo parsing of the owner partial-edit CLI inputs."""
    if clear_institution and institution_id is not None:
        raise ValueError(
            "Use either --institution-id or --clear-institution, not both."
        )
    if clear_external_id and external_id is not None:
        raise ValueError(
            "Use either --external-id or --clear-external-id, not both."
        )
    if clear_notes and notes is not None:
        raise ValueError("Use either --notes or --clear-notes, not both.")
    if active and inactive:
        raise ValueError("Use either --active or --inactive, not both.")
    is_active: bool | None = True if active else False if inactive else None

    parsed_institution_id = _parse_optional_uuid(
        institution_id, field_name="institution_id"
    )
    if not (
        name is not None
        or surname is not None
        or email is not None
        or parsed_institution_id is not None
        or external_id is not None
        or notes is not None
        or is_active is not None
        or clear_institution
        or clear_external_id
        or clear_notes
    ):
        raise ValueError(
            "Provide at least one field to update (or an explicit clear)."
        )

    return (
        OwnerUpdatePatch(
            name=_optional_replacement(name, "name"),
            surname=_optional_replacement(surname, "surname"),
            email=_optional_email(email),
            institution_id=parsed_institution_id,
            clear_institution=clear_institution,
            external_id=_optional_replacement(external_id, "external_id"),
            clear_external_id=clear_external_id,
            notes=_optional_replacement(notes, "notes"),
            clear_notes=clear_notes,
            is_active=is_active,
        ),
        _parse_optional_uuid(actor_admin_id, field_name="actor_admin_id"),
        _required_reason(reason),
    )


def parse_cohort_update_patch(
    *,
    name: str | None,
    description: str | None,
    clear_description: bool,
    starts_at: str | None,
    clear_starts_at: bool,
    ends_at: str | None,
    clear_ends_at: bool,
    actor_admin_id: str | None,
    reason: str | None,
) -> tuple[CohortUpdatePatch, uuid.UUID | None, str]:
    """Strict, no-echo parsing of the cohort partial-edit CLI inputs."""
    if clear_description and description is not None:
        raise ValueError(
            "Use either --description or --clear-description, not both."
        )
    if clear_starts_at and starts_at is not None:
        raise ValueError("Use either --starts-at or --clear-starts-at, not both.")
    if clear_ends_at and ends_at is not None:
        raise ValueError("Use either --ends-at or --clear-ends-at, not both.")
    parsed_starts_at = _parse_optional_datetime(starts_at, "starts_at")
    parsed_ends_at = _parse_optional_datetime(ends_at, "ends_at")
    if parsed_starts_at is not None and parsed_ends_at is not None:
        if parsed_ends_at <= parsed_starts_at:
            raise ValueError("ends_at must be after starts_at")
    if not (
        name is not None
        or description is not None
        or parsed_starts_at is not None
        or parsed_ends_at is not None
        or clear_description
        or clear_starts_at
        or clear_ends_at
    ):
        raise ValueError(
            "Provide at least one field to update (or an explicit clear)."
        )

    return (
        CohortUpdatePatch(
            name=_optional_replacement(name, "name"),
            description=_optional_replacement(description, "description"),
            clear_description=clear_description,
            starts_at=parsed_starts_at,
            clear_starts_at=clear_starts_at,
            ends_at=parsed_ends_at,
            clear_ends_at=clear_ends_at,
        ),
        _parse_optional_uuid(actor_admin_id, field_name="actor_admin_id"),
        _required_reason(reason),
    )


def _optional_replacement(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"The {label} replacement cannot be empty.")
    _reject_secret_looking_text(cleaned, label)
    return cleaned


def _optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("The email replacement cannot be empty.")
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise ValueError("The email replacement must be valid.")
    _reject_secret_looking_text(cleaned, "email")
    return cleaned


def _required_reason(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Enter an audit reason before changing record metadata.")
    if len(cleaned.encode("utf-8")) > RECORD_UPDATE_REASON_MAX_BYTES:
        raise ValueError("The audit reason exceeds the bounded length.")
    _reject_secret_looking_text(cleaned, "Reason")
    return cleaned


def _parse_optional_uuid(value: str | None, *, field_name: str) -> uuid.UUID | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        return uuid.UUID(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _parse_optional_datetime(value: str | None, field_name: str) -> datetime | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _reject_secret_looking_text(value: str, label: str) -> None:
    """Finite recognized-shape refusal with a FIXED safe error (no echo)."""
    if redact_text(value) != value:
        raise ValueError(f"The {label} must not contain secret-looking values.")
    normalized = normalize_sensitive_key(value)
    if any(marker in normalized for marker in _SECRET_MARKERS):
        raise ValueError(f"The {label} must not contain secret-looking values.")
    for part in value.replace("=", " ").replace(":", " ").split():
        if is_sensitive_key(part):
            raise ValueError(f"The {label} must not contain secret-looking values.")
