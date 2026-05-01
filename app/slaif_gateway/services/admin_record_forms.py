"""Safe parsing helpers for admin owner, institution, and cohort forms."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from slaif_gateway.utils.redaction import is_sensitive_key, normalize_sensitive_key, redact_text


@dataclass(frozen=True, slots=True)
class InstitutionFormInput:
    name: str
    country: str | None
    notes: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class CohortFormInput:
    name: str
    description: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class OwnerFormInput:
    name: str
    surname: str
    email: str
    institution_id: uuid.UUID | None
    external_id: str | None
    notes: str | None
    is_active: bool
    reason: str


def parse_institution_form(
    *,
    name: str,
    country: str | None,
    notes: str | None,
    reason: str | None,
) -> InstitutionFormInput:
    cleaned_name = _required_text(name, "Institution name")
    cleaned_country = _optional_text(country, "Country")
    cleaned_notes = _optional_text(notes, "Notes")
    return InstitutionFormInput(
        name=cleaned_name,
        country=cleaned_country,
        notes=cleaned_notes,
        reason=_required_reason(reason),
    )


def parse_cohort_form(
    *,
    name: str,
    description: str | None,
    starts_at: str | None,
    ends_at: str | None,
    reason: str | None,
) -> CohortFormInput:
    cleaned_name = _required_text(name, "Cohort name")
    cleaned_description = _optional_text(description, "Description")
    parsed_starts_at = _parse_optional_datetime(starts_at, "starts_at")
    parsed_ends_at = _parse_optional_datetime(ends_at, "ends_at")
    if parsed_starts_at is not None and parsed_ends_at is not None and parsed_ends_at <= parsed_starts_at:
        raise ValueError("ends_at must be after starts_at")
    return CohortFormInput(
        name=cleaned_name,
        description=cleaned_description,
        starts_at=parsed_starts_at,
        ends_at=parsed_ends_at,
        reason=_required_reason(reason),
    )


def parse_owner_form(
    *,
    name: str,
    surname: str,
    email: str,
    institution_id: str | None,
    external_id: str | None,
    notes: str | None,
    is_active: str | None,
    reason: str | None,
) -> OwnerFormInput:
    cleaned_name = _required_text(name, "Owner name")
    cleaned_surname = _required_text(surname, "Owner surname")
    cleaned_email = _normalize_email(email)
    return OwnerFormInput(
        name=cleaned_name,
        surname=cleaned_surname,
        email=cleaned_email,
        institution_id=_parse_optional_uuid(institution_id, "institution_id"),
        external_id=_optional_text(external_id, "External ID"),
        notes=_optional_text(notes, "Notes"),
        is_active=_is_checked(is_active),
        reason=_required_reason(reason),
    )


def _required_text(value: str | None, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{label} cannot be empty")
    _reject_secret_looking_text(cleaned, label)
    return cleaned


def _optional_text(value: str | None, label: str) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    _reject_secret_looking_text(cleaned, label)
    return cleaned


def _required_reason(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Enter an audit reason before changing record metadata.")
    _reject_secret_looking_text(cleaned, "Reason")
    return cleaned


def _normalize_email(value: str | None) -> str:
    cleaned = _required_text(value, "Owner email").lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise ValueError("Owner email must be valid")
    local, domain = cleaned.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Owner email must be valid")
    return cleaned


def _parse_optional_uuid(value: str | None, field_name: str) -> uuid.UUID | None:
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
    if redact_text(value) != value:
        raise ValueError(f"{label} must not contain secret-looking values")
    normalized = normalize_sensitive_key(value)
    if any(
        marker in normalized
        for marker in (
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
    ):
        raise ValueError(f"{label} must not contain secret-looking values")
    for part in value.replace("=", " ").replace(":", " ").split():
        if is_sensitive_key(part):
            raise ValueError(f"{label} must not contain secret-looking values")


def _is_checked(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "on", "yes"}
