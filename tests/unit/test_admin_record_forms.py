import uuid

import pytest

from slaif_gateway.services.admin_record_forms import (
    parse_cohort_form,
    parse_institution_form,
    parse_owner_form,
)


def test_parse_owner_form_normalizes_email_and_uuid() -> None:
    institution_id = uuid.uuid4()

    parsed = parse_owner_form(
        name=" Ada ",
        surname=" Lovelace ",
        email=" ADA@EXAMPLE.ORG ",
        institution_id=str(institution_id),
        external_id=" external-safe ",
        notes=" safe note ",
        is_active="true",
        reason=" records update ",
    )

    assert parsed.name == "Ada"
    assert parsed.surname == "Lovelace"
    assert parsed.email == "ada@example.org"
    assert parsed.institution_id == institution_id
    assert parsed.external_id == "external-safe"
    assert parsed.notes == "safe note"
    assert parsed.is_active is True
    assert parsed.reason == "records update"


def test_parse_owner_form_rejects_invalid_email_and_uuid() -> None:
    with pytest.raises(ValueError, match="email"):
        parse_owner_form(
            name="Ada",
            surname="Lovelace",
            email="not-an-email",
            institution_id="",
            external_id="",
            notes="",
            is_active="true",
            reason="records update",
        )

    with pytest.raises(ValueError, match="institution_id"):
        parse_owner_form(
            name="Ada",
            surname="Lovelace",
            email="ada@example.org",
            institution_id="not-a-uuid",
            external_id="",
            notes="",
            is_active="true",
            reason="records update",
        )


def test_parse_cohort_form_rejects_invalid_window() -> None:
    with pytest.raises(ValueError, match="ends_at"):
        parse_cohort_form(
            name="Workshop",
            description="safe",
            starts_at="2026-02-01T00:00:00+00:00",
            ends_at="2026-01-01T00:00:00+00:00",
            reason="records update",
        )


def test_record_forms_reject_secret_looking_text() -> None:
    with pytest.raises(ValueError, match="secret-looking"):
        parse_institution_form(
            name="SLAIF University",
            country="SI",
            notes="Authorization: Bearer sk-provider-secret-value",
            reason="records update",
        )

    with pytest.raises(ValueError, match="secret-looking"):
        parse_cohort_form(
            name="Workshop",
            description="token_hash should never be stored",
            starts_at="",
            ends_at="",
            reason="records update",
        )

    with pytest.raises(ValueError, match="secret-looking"):
        parse_owner_form(
            name="Ada",
            surname="Lovelace",
            email="ada@example.org",
            institution_id="",
            external_id="",
            notes="sk-slaif-public.secretsecretsecret",
            is_active="true",
            reason="records update",
        )


def test_record_forms_require_reason() -> None:
    with pytest.raises(ValueError, match="audit reason"):
        parse_institution_form(name="SLAIF University", country="", notes="", reason="")
