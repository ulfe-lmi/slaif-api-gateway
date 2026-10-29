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

from slaif_gateway.utils.redaction import redact_text

# Consistent with the existing operator audit-reason bound
# (services/openai_compatible_setup.py: 1024 UTF-8 bytes).
RECORD_UPDATE_REASON_MAX_BYTES = 1024

# Fixed, no-echo refusal messages (shared by the CLI parser and the
# service-boundary asserts below so both layers refuse identically).
_MSG_CONFLICT_ACTIVE_INACTIVE = "Use either --active or --inactive, not both."
_MSG_CONFLICT_INSTITUTION = (
    "Use either --institution-id or --clear-institution, not both."
)
_MSG_CONFLICT_EXTERNAL_ID = "Use either --external-id or --clear-external-id, not both."
_MSG_CONFLICT_NOTES = "Use either --notes or --clear-notes, not both."
_MSG_CONFLICT_DESCRIPTION = (
    "Use either --description or --clear-description, not both."
)
_MSG_CONFLICT_STARTS_AT = "Use either --starts-at or --clear-starts-at, not both."
_MSG_CONFLICT_ENDS_AT = "Use either --ends-at or --clear-ends-at, not both."
_MSG_NO_FIELD = "Provide at least one field to update (or an explicit clear)."


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
    if active and inactive:
        raise ValueError(_MSG_CONFLICT_ACTIVE_INACTIVE)
    is_active: bool | None = True if active else False if inactive else None

    parsed_institution_id = _parse_optional_uuid(
        institution_id, field_name="institution_id"
    )
    patch = OwnerUpdatePatch(
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
    )
    _assert_no_owner_replace_clear_conflicts(patch)
    _assert_owner_patch_has_field(patch)

    return (
        patch,
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
    parsed_starts_at = _parse_optional_datetime(starts_at, "starts_at")
    parsed_ends_at = _parse_optional_datetime(ends_at, "ends_at")
    if parsed_starts_at is not None and parsed_ends_at is not None:
        if parsed_ends_at <= parsed_starts_at:
            raise ValueError("ends_at must be after starts_at")
    patch = CohortUpdatePatch(
        name=_optional_replacement(name, "name"),
        description=_optional_replacement(description, "description"),
        clear_description=clear_description,
        starts_at=parsed_starts_at,
        clear_starts_at=clear_starts_at,
        ends_at=parsed_ends_at,
        clear_ends_at=clear_ends_at,
    )
    _assert_no_cohort_replace_clear_conflicts(patch)
    _assert_cohort_patch_has_field(patch)

    return (
        patch,
        _parse_optional_uuid(actor_admin_id, field_name="actor_admin_id"),
        _required_reason(reason),
    )


def assert_owner_update_patch_safe(patch: OwnerUpdatePatch, *, reason: str) -> None:
    """Shared service-boundary guard for direct (non-CLI) callers.

    The CLI parser already applies these laws, but a raw caller may
    construct an ``OwnerUpdatePatch`` by hand, so the shared partial-edit
    service re-enforces the SAME fixed, no-echo refusal before any
    repository access: required nonblank bounded reason, replace/clear
    conflicts, no-field refusal, and finite recognized-shape refusal for
    every provided value (existing redaction helpers, not a universal
    sanitizer).

    Supplied blank nullable strings are also refused here (same fixed
    message as the parser): ``None`` means omitted, explicit clear flags
    mean cleared, and a blank string must never silently clear a stored
    field. Existing complete-update semantics are unchanged.
    """
    _required_reason(reason)
    _assert_no_owner_replace_clear_conflicts(patch)
    _assert_owner_patch_has_field(patch)
    if patch.name is not None:
        _assert_replacement_not_blank(patch.name, "name")
        _reject_secret_looking_text(patch.name, "name")
    if patch.surname is not None:
        _assert_replacement_not_blank(patch.surname, "surname")
        _reject_secret_looking_text(patch.surname, "surname")
    if patch.email is not None:
        _assert_replacement_not_blank(patch.email, "email")
        _reject_secret_looking_text(patch.email, "email")
    if patch.external_id is not None:
        _assert_replacement_not_blank(patch.external_id, "external_id")
        _reject_secret_looking_text(patch.external_id, "external_id")
    if patch.notes is not None:
        _assert_replacement_not_blank(patch.notes, "notes")
        _reject_secret_looking_text(patch.notes, "notes")


def assert_cohort_update_patch_safe(patch: CohortUpdatePatch, *, reason: str) -> None:
    """Shared service-boundary guard for direct (non-CLI) callers.

    Same fixed, no-echo refusal law as ``assert_owner_update_patch_safe``
    for the cohort partial edit, including the supplied-blank replacement
    refusal.
    """
    _required_reason(reason)
    _assert_no_cohort_replace_clear_conflicts(patch)
    _assert_cohort_patch_has_field(patch)
    if patch.name is not None:
        _assert_replacement_not_blank(patch.name, "name")
        _reject_secret_looking_text(patch.name, "name")
    if patch.description is not None:
        _assert_replacement_not_blank(patch.description, "description")
        _reject_secret_looking_text(patch.description, "description")


def _assert_no_owner_replace_clear_conflicts(patch: OwnerUpdatePatch) -> None:
    if patch.clear_institution and patch.institution_id is not None:
        raise ValueError(_MSG_CONFLICT_INSTITUTION)
    if patch.clear_external_id and patch.external_id is not None:
        raise ValueError(_MSG_CONFLICT_EXTERNAL_ID)
    if patch.clear_notes and patch.notes is not None:
        raise ValueError(_MSG_CONFLICT_NOTES)


def _assert_no_cohort_replace_clear_conflicts(patch: CohortUpdatePatch) -> None:
    if patch.clear_description and patch.description is not None:
        raise ValueError(_MSG_CONFLICT_DESCRIPTION)
    if patch.clear_starts_at and patch.starts_at is not None:
        raise ValueError(_MSG_CONFLICT_STARTS_AT)
    if patch.clear_ends_at and patch.ends_at is not None:
        raise ValueError(_MSG_CONFLICT_ENDS_AT)


def _assert_owner_patch_has_field(patch: OwnerUpdatePatch) -> None:
    if not (
        patch.name is not None
        or patch.surname is not None
        or patch.email is not None
        or patch.institution_id is not None
        or patch.external_id is not None
        or patch.notes is not None
        or patch.is_active is not None
        or patch.clear_institution
        or patch.clear_external_id
        or patch.clear_notes
    ):
        raise ValueError(_MSG_NO_FIELD)


def _assert_cohort_patch_has_field(patch: CohortUpdatePatch) -> None:
    if not (
        patch.name is not None
        or patch.description is not None
        or patch.starts_at is not None
        or patch.ends_at is not None
        or patch.clear_description
        or patch.clear_starts_at
        or patch.clear_ends_at
    ):
        raise ValueError(_MSG_NO_FIELD)


def assert_owner_current_metadata_safe(
    *,
    name: str,
    surname: str,
    email: str,
    external_id: str | None,
    notes: str | None,
) -> None:
    """Guard the FRESH stored owner metadata at the NEW partial boundary.

    Provided patch values are guarded at the patch boundary; this covers
    the current (omitted or explicitly cleared) side, so an existing
    recognized-secret-shape value already stored on the selected row can
    never be copied into the new audit old/new snapshot or the write,
    even by an unrelated edit or an explicit clear. Fixed safe refusal,
    no value echo; existing complete-update semantics are unchanged.
    """
    _reject_secret_looking_text(name, "name")
    _reject_secret_looking_text(surname, "surname")
    _reject_secret_looking_text(email, "email")
    if external_id is not None:
        _reject_secret_looking_text(external_id, "external_id")
    if notes is not None:
        _reject_secret_looking_text(notes, "notes")


def assert_cohort_current_metadata_safe(*, name: str, description: str | None) -> None:
    """Guard the FRESH stored cohort metadata at the NEW partial boundary.

    Same law as ``assert_owner_current_metadata_safe`` for the cohort
    editable strings.
    """
    _reject_secret_looking_text(name, "name")
    if description is not None:
        _reject_secret_looking_text(description, "description")


def _optional_replacement(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    _assert_replacement_not_blank(value, label)
    cleaned = value.strip()
    _reject_secret_looking_text(cleaned, label)
    return cleaned


def _optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    _assert_replacement_not_blank(value, "email")
    cleaned = value.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise ValueError("The email replacement must be valid.")
    _reject_secret_looking_text(cleaned, "email")
    return cleaned


def _assert_replacement_not_blank(value: str, label: str) -> None:
    """Fixed no-echo refusal for a supplied blank replacement."""
    if not value.strip():
        raise ValueError(f"The {label} replacement cannot be empty.")


def _required_reason(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Enter an audit reason before changing record metadata.")
    if len(cleaned.encode("utf-8")) > RECORD_UPDATE_REASON_MAX_BYTES:
        raise ValueError("The audit reason exceeds the bounded length.")
    _reject_secret_looking_text(cleaned, "Reason")
    return cleaned


def _parse_optional_uuid(value: str | None, *, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"The {field_name} value cannot be empty.")
    try:
        return uuid.UUID(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _parse_optional_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"The {field_name} value cannot be empty.")
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
    """Finite recognized-shape refusal with a FIXED safe error (no echo).

    Uses ONLY the existing finite credential/bearer/credential-assignment
    VALUE patterns (``redact_text``). Bare keyword substrings
    (token/session/secret/nonce) and MAP/HEADER-key classification
    (``is_sensitive_key``) must NOT reject ordinary free-form values such
    as "Workshop Session 1", "Token usage follow-up", or "Contact the
    faculty secretariat".
    """
    if redact_text(value) != value:
        raise ValueError(f"The {label} must not contain secret-looking values.")
