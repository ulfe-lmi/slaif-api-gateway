"""Typed partial-edit boundary for owners/cohorts (204-b): parsers,
service-boundary asserts, and fixed no-echo refusal law.

Pure schema tests (no database, no CLI): omission semantics, nullable-only
clears, replace/clear conflicts, no-field refusal, required bounded
reason, finite recognized-shape refusal, UTC-aware datetime convention,
and the fresh-current-metadata guard used by the shared services.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from slaif_gateway.schemas.record_edits import (
    RECORD_UPDATE_REASON_MAX_BYTES,
    CohortUpdatePatch,
    OwnerUpdatePatch,
    assert_cohort_current_metadata_safe,
    assert_cohort_update_patch_safe,
    assert_owner_current_metadata_safe,
    assert_owner_update_patch_safe,
    parse_cohort_update_patch,
    parse_owner_update_patch,
)

# Recognized provider-key shape (synthetic; the finite redaction
# patterns match it in any surrounding context).
CANARY = "sk-proj-canary204b0000000000000"
OTHER = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _owner_args(**overrides) -> dict[str, object]:
    args: dict[str, object] = {
        "name": None,
        "surname": None,
        "email": None,
        "institution_id": None,
        "clear_institution": False,
        "external_id": None,
        "clear_external_id": False,
        "notes": None,
        "clear_notes": False,
        "active": False,
        "inactive": False,
        "actor_admin_id": None,
        "reason": "move owner to another institution",
    }
    args.update(overrides)
    return args


def _cohort_args(**overrides) -> dict[str, object]:
    args: dict[str, object] = {
        "name": None,
        "description": None,
        "clear_description": False,
        "starts_at": None,
        "clear_starts_at": False,
        "ends_at": None,
        "clear_ends_at": False,
        "actor_admin_id": None,
        "reason": "adjust cohort window",
    }
    args.update(overrides)
    return args


def _empty_owner_patch() -> OwnerUpdatePatch:
    return OwnerUpdatePatch(
        name=None,
        surname=None,
        email=None,
        institution_id=None,
        clear_institution=False,
        external_id=None,
        clear_external_id=False,
        notes=None,
        clear_notes=False,
        is_active=None,
    )


def _empty_cohort_patch() -> CohortUpdatePatch:
    return CohortUpdatePatch(
        name=None,
        description=None,
        clear_description=False,
        starts_at=None,
        clear_starts_at=False,
        ends_at=None,
        clear_ends_at=False,
    )


# --- owner parser ---------------------------------------------------------


def test_owner_parse_full_replacement() -> None:
    patch, actor, reason = parse_owner_update_patch(
        **_owner_args(
            name="  Ada  ",
            surname="Lovelace",
            email="  ADA@example.ORG ",
            institution_id=str(OTHER),
            external_id=" ext-1 ",
            notes=" note ",
            active=True,
            actor_admin_id=str(uuid.UUID(int=7)),
        )
    )
    assert patch.name == "Ada"
    assert patch.surname == "Lovelace"
    assert patch.email == "ada@example.org"
    assert patch.institution_id == OTHER
    assert patch.external_id == "ext-1"
    assert patch.notes == "note"
    assert patch.is_active is True
    assert actor == uuid.UUID(int=7)
    assert reason == "move owner to another institution"


def test_owner_parse_omission_is_none_tri_state() -> None:
    patch, actor, _ = parse_owner_update_patch(**_owner_args(institution_id=str(OTHER)))
    assert patch.name is None
    assert patch.surname is None
    assert patch.email is None
    assert patch.is_active is None  # neither --active nor --inactive
    assert patch.clear_institution is False
    assert actor is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"institution_id": str(OTHER), "clear_institution": True},
         "Use either --institution-id or --clear-institution, not both."),
        ({"external_id": "e", "clear_external_id": True},
         "Use either --external-id or --clear-external-id, not both."),
        ({"notes": "n", "clear_notes": True},
         "Use either --notes or --clear-notes, not both."),
        ({"active": True, "inactive": True},
         "Use either --active or --inactive, not both."),
    ],
)
def test_owner_parse_replace_clear_conflicts_refused(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_owner_update_patch(**_owner_args(**overrides))


def test_owner_parse_no_field_refused() -> None:
    with pytest.raises(ValueError, match="Provide at least one field to update"):
        parse_owner_update_patch(**_owner_args())


def test_owner_parse_blank_replacements_refused() -> None:
    for field in ("name", "surname", "external_id", "notes"):
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_owner_update_patch(**_owner_args(**{field: "   "}))
    with pytest.raises(ValueError, match="email"):
        parse_owner_update_patch(**_owner_args(email="  "))


@pytest.mark.parametrize("bad", ["no-at-sign", "@example.org", "ada@"])
def test_owner_parse_invalid_email_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="email"):
        parse_owner_update_patch(**_owner_args(email=bad))


@pytest.mark.parametrize("field", ["institution_id", "actor_admin_id"])
def test_owner_parse_invalid_uuid_refused(field: str) -> None:
    overrides: dict[str, object] = {field: "not-a-uuid"}
    if field == "actor_admin_id":
        # the actor is not an editable field: supply one so the no-field
        # refusal cannot mask the UUID validation.
        overrides["external_id"] = "e-1"
    with pytest.raises(ValueError, match="must be a valid UUID"):
        parse_owner_update_patch(**_owner_args(**overrides))


def test_owner_parse_datetime_naive_becomes_utc_z_suffix() -> None:
    # cohort parser owns datetimes; owner has none, so exercise the shared
    # convention through the cohort path here.
    patch, _, _ = parse_cohort_update_patch(
        **_cohort_args(starts_at="2026-02-01T00:00:00")
    )
    assert patch.starts_at == datetime(2026, 2, 1, tzinfo=UTC)
    patch, _, _ = parse_cohort_update_patch(
        **_cohort_args(starts_at="2026-02-01T01:00:00Z")
    )
    assert patch.starts_at == datetime(2026, 2, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="ISO datetime"):
        parse_cohort_update_patch(**_cohort_args(starts_at="not-a-date"))


def test_cohort_parse_both_sides_window_checked_at_parse() -> None:
    with pytest.raises(ValueError, match="ends_at must be after starts_at"):
        parse_cohort_update_patch(
            **_cohort_args(
                starts_at="2026-02-02T00:00:00Z", ends_at="2026-02-01T00:00:00Z"
            )
        )
    # A single side is fine at parse time: the FINAL merged window is the
    # shared service's law (omitted side still participates).
    patch, _, _ = parse_cohort_update_patch(**_cohort_args(ends_at="2026-02-01T00:00:00Z"))
    assert patch.starts_at is None and patch.ends_at is not None


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("field", ["institution_id", "actor_admin_id"])
def test_owner_parse_supplied_blank_uuid_refused(blank: str, field: str) -> None:
    # Supplied blanks are NOT omissions (None is the omission
    # convention): even alongside a valid edit they must be refused with
    # a fixed no-echo error.
    overrides: dict[str, object] = {field: blank, "name": "Ada"}
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_owner_update_patch(**_owner_args(**overrides))


@pytest.mark.parametrize("blank", ["", "  "])
def test_owner_parse_blank_institution_with_clear_refused(blank: str) -> None:
    # A supplied blank replacement must not silently become a clear.
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_owner_update_patch(
            **_owner_args(institution_id=blank, clear_institution=True)
        )


@pytest.mark.parametrize("blank", ["", "  "])
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_cohort_parse_supplied_blank_datetime_refused(blank: str, field: str) -> None:
    overrides: dict[str, object] = {field: blank, "name": "Group"}
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_cohort_update_patch(**_cohort_args(**overrides))


@pytest.mark.parametrize("blank", ["", "  "])
def test_cohort_parse_blank_datetime_with_clear_refused(blank: str) -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_cohort_update_patch(
            **_cohort_args(starts_at=blank, clear_starts_at=True)
        )


def test_none_stays_omitted_and_clears_stay_valid() -> None:
    # None remains "omitted" and explicit clears remain valid (the
    # supplied-blank refusals above must not weaken either).
    patch, actor, _ = parse_owner_update_patch(**_owner_args(clear_institution=True))
    assert patch.institution_id is None
    assert patch.clear_institution is True
    assert actor is None
    patch, actor, _ = parse_cohort_update_patch(
        **_cohort_args(clear_starts_at=True, clear_ends_at=True, clear_description=True)
    )
    assert (
        patch.starts_at is None
        and patch.ends_at is None
        and patch.clear_starts_at is True
        and patch.clear_ends_at is True
        and patch.clear_description is True
    )


def test_owner_parse_canary_values_refused_without_echo() -> None:
    for field in ("name", "surname", "external_id", "notes"):
        with pytest.raises(ValueError, match="secret-looking") as exc:
            parse_owner_update_patch(**_owner_args(**{field: CANARY}))
        assert CANARY not in str(exc.value)
    with pytest.raises(ValueError, match="secret-looking"):
        parse_owner_update_patch(**_owner_args(email=f"{CANARY}@example.org"))
    with pytest.raises(ValueError, match="secret-looking"):
        parse_cohort_update_patch(**_cohort_args(description=CANARY))


def test_ordinary_metadata_values_are_accepted() -> None:
    # Finding 11: ordinary free-form values WITHOUT credential/bearer/
    # credential-assignment shape must pass the finite value guard.
    patch, _, _ = parse_owner_update_patch(
        **_owner_args(
            notes="Contact the faculty secretariat",
            external_id="session-2026-04",
            email="session.owner@example.invalid",
        )
    )
    assert patch.notes == "Contact the faculty secretariat"
    assert patch.external_id == "session-2026-04"
    assert patch.email == "session.owner@example.invalid"

    patch, _, _ = parse_cohort_update_patch(
        **_cohort_args(name="Workshop Session 1",
                       description="Token usage follow-up")
    )
    assert patch.name == "Workshop Session 1"
    assert patch.description == "Token usage follow-up"

    patch, _, reason = parse_owner_update_patch(
        **_owner_args(external_id="e-1", reason="Adjust token budget")
    )
    assert reason == "Adjust token budget"
    assert_owner_update_patch_safe(patch, reason=reason)


def test_current_metadata_guard_accepts_ordinary_existing_cohort() -> None:
    # An entirely ordinary existing cohort (e.g. "Workshop Session 1")
    # must remain editable through the NEW partial boundary.
    assert_cohort_current_metadata_safe(
        name="Workshop Session 1",
        description="Token usage follow-up",
    )
    assert_owner_current_metadata_safe(
        name="Ada", surname="L.", email="session.owner@example.invalid",
        external_id="session-2026-04",
        notes="Contact the faculty secretariat",
    )


@pytest.mark.parametrize("reason", ["", "   ", "x" * (RECORD_UPDATE_REASON_MAX_BYTES + 1)])
def test_owner_parse_required_bounded_reason(reason: str) -> None:
    with pytest.raises(ValueError):
        parse_owner_update_patch(**_owner_args(institution_id=str(OTHER), reason=reason))


def test_owner_parse_canary_reason_refused_without_echo() -> None:
    with pytest.raises(ValueError, match="secret-looking") as exc:
        parse_owner_update_patch(
            **_owner_args(institution_id=str(OTHER), reason=CANARY)
        )
    assert CANARY not in str(exc.value)


# --- service-boundary asserts (direct non-CLI callers) --------------------


def test_owner_patch_asserts_accept_valid() -> None:
    patch, _, reason = parse_owner_update_patch(**_owner_args(external_id="e-1"))
    assert_owner_update_patch_safe(patch, reason=reason)


def test_owner_patch_asserts_catch_hand_built_conflict() -> None:
    patch = _empty_owner_patch()
    conflict = OwnerUpdatePatch(
        name=None, surname=None, email=None, institution_id=OTHER,
        clear_institution=True, external_id=None, clear_external_id=False,
        notes=None, clear_notes=False, is_active=None,
    )
    assert patch is not None
    with pytest.raises(ValueError, match="not both"):
        assert_owner_update_patch_safe(conflict, reason="ok")


def test_owner_patch_asserts_catch_no_field_and_blank_reason() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        assert_owner_update_patch_safe(_empty_owner_patch(), reason="ok")
    with pytest.raises(ValueError, match="audit reason"):
        assert_owner_update_patch_safe(
            OwnerUpdatePatch(
                name=None, surname=None, email=None, institution_id=OTHER,
                clear_institution=False, external_id=None,
                clear_external_id=False, notes=None, clear_notes=False,
                is_active=None,
            ),
            reason="   ",
        )


def test_owner_patch_asserts_catch_canary_in_hand_built_fields() -> None:
    patch = OwnerUpdatePatch(
        name=None, surname=CANARY, email=None, institution_id=OTHER,
        clear_institution=False, external_id=None, clear_external_id=False,
        notes=None, clear_notes=False, is_active=None,
    )
    with pytest.raises(ValueError, match="secret-looking") as exc:
        assert_owner_update_patch_safe(patch, reason="ok")
    assert CANARY not in str(exc.value)


def test_cohort_patch_asserts() -> None:
    patch, _, reason = parse_cohort_update_patch(**_cohort_args(name="  Group "))
    assert_cohort_update_patch_safe(patch, reason=reason)
    assert patch.name == "Group"
    conflict = CohortUpdatePatch(
        name=None, description="d", clear_description=True,
        starts_at=None, clear_starts_at=False, ends_at=None, clear_ends_at=False,
    )
    with pytest.raises(ValueError, match="not both"):
        assert_cohort_update_patch_safe(conflict, reason="ok")
    with pytest.raises(ValueError, match="at least one field"):
        assert_cohort_update_patch_safe(_empty_cohort_patch(), reason="ok")
    with pytest.raises(ValueError, match="secret-looking"):
        assert_cohort_update_patch_safe(
            CohortUpdatePatch(
                name=CANARY, description=None, clear_description=False,
                starts_at=None, clear_starts_at=False, ends_at=None,
                clear_ends_at=False,
            ),
            reason="ok",
        )


# --- fresh-current-metadata guard (item 8 boundary) ------------------------


def test_owner_current_metadata_guard_refuses_stored_canary() -> None:
    with pytest.raises(ValueError, match="secret-looking") as exc:
        assert_owner_current_metadata_safe(
            name="Ada", surname="L.", email="ada@example.org",
            external_id=None, notes=CANARY,
        )
    assert CANARY not in str(exc.value)
    with pytest.raises(ValueError, match="secret-looking"):
        assert_owner_current_metadata_safe(
            name="Ada", surname=CANARY, email="ada@example.org",
            external_id=None, notes=None,
        )
    # Ordinary metadata passes (fail-open for legitimate values).
    assert_owner_current_metadata_safe(
        name="Ada", surname="L.", email="ada@example.org",
        external_id="ext-9", notes="plain note",
    )


def test_cohort_current_metadata_guard() -> None:
    with pytest.raises(ValueError, match="secret-looking"):
        assert_cohort_current_metadata_safe(name="Group", description=CANARY)
    assert_cohort_current_metadata_safe(
        name="Group", description="plain description"
    )
