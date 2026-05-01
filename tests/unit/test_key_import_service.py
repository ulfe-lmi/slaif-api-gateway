from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from slaif_gateway.services.key_import import (
    KeyImportCohortRef,
    KeyImportOwnerRef,
    KeyImportReadOnlyContext,
    key_import_preview_to_dict,
    parse_key_import_csv,
    parse_key_import_json,
    validate_key_import_rows,
)


OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
INSTITUTION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
COHORT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _context(**overrides) -> KeyImportReadOnlyContext:
    owner = KeyImportOwnerRef(
        id=OWNER_ID,
        email="ada@example.org",
        display_name="Ada Lovelace",
        institution_id=INSTITUTION_ID,
        institution_name="SLAIF",
    )
    values = {
        "owners_by_id": {OWNER_ID: owner},
        "owners_by_email": {owner.email: owner},
        "cohorts_by_id": {COHORT_ID: KeyImportCohortRef(id=COHORT_ID, name="Spring Cohort")},
        "email_delivery_enabled": False,
        "smtp_configured": False,
        "celery_configured": False,
    }
    values.update(overrides)
    return KeyImportReadOnlyContext(**values)


def _valid_row(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "owner_id": str(OWNER_ID),
        "valid_days": "30",
        "cost_limit_eur": "10.50",
        "token_limit_total": "100000",
        "request_limit_total": "1000",
        "allowed_models": "gpt-test\nopenrouter/test",
        "allowed_endpoints": "/v1/chat/completions,/v1/models",
        "allowed_providers": "openai,openrouter",
        "rate_limit_requests_per_minute": "60",
        "rate_limit_tokens_per_minute": "12000",
        "rate_limit_concurrent_requests": "4",
        "rate_limit_window_seconds": "30",
        "email_delivery_mode": "none",
        "note": "safe note",
    }
    row.update(overrides)
    return row


def _preview(rows: list[dict[str, object]], *, max_rows: int = 1000, context=None):
    return validate_key_import_rows(
        rows,
        context=context or _context(),
        max_rows=max_rows,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_valid_csv_and_json_parse() -> None:
    csv_rows = parse_key_import_csv("owner_email,valid_days\nada@example.org,30\n")
    json_rows = parse_key_import_json('[{"owner_email":"ada@example.org","valid_days":"30"}]')

    assert csv_rows[0]["owner_email"] == "ada@example.org"
    assert json_rows[0]["valid_days"] == "30"


def test_valid_row_resolves_owner_policy_and_rate_limits() -> None:
    preview = _preview([_valid_row(owner_id="", owner_email="ada@example.org", cohort_id=str(COHORT_ID))])

    row = preview.rows[0]
    assert preview.valid_count == 1
    assert row.owner_id == OWNER_ID
    assert row.owner_email == "ada@example.org"
    assert row.institution_id == INSTITUTION_ID
    assert row.cohort_id == COHORT_ID
    assert row.cost_limit_eur == "10.50"
    assert row.token_limit == 100000
    assert row.request_limit == 1000
    assert row.allowed_models == ("gpt-test", "openrouter/test")
    assert row.allowed_endpoints == ("/v1/chat/completions", "/v1/models")
    assert row.allowed_providers == ("openai", "openrouter")
    assert row.rate_limit_policy == {
        "requests_per_minute": 60,
        "tokens_per_minute": 12000,
        "max_concurrent_requests": 4,
        "window_seconds": 30,
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unknown", "value", "unknown fields"),
        ("owner_id", str(uuid.uuid4()), "owner_id must reference an existing owner"),
        ("owner_email", "not-an-email", "owner_email must be a valid email address"),
        ("institution_id", str(uuid.uuid4()), "institution_id must match"),
        ("cohort_id", str(uuid.uuid4()), "cohort_id must reference an existing cohort"),
        ("cost_limit_eur", "not-decimal", "cost_limit_eur must be a decimal string"),
        ("cost_limit_eur", "-1", "cost_limit_eur must be positive"),
        ("token_limit_total", "zero", "token_limit must be a positive integer"),
        ("allow_all_models", "maybe", "allow_all_models must be true or false"),
        ("email_delivery_mode", "old-key-resend", "email_delivery_mode must be"),
        ("note", "sk-provider-secret", "note must not contain secret-looking values"),
        ("allowed_models", "Bearer upstream-token", "allowed_models must not contain secret-looking values"),
    ],
)
def test_invalid_rows_are_rejected(field: str, value: str, message: str) -> None:
    preview = _preview([_valid_row(**{field: value})])

    assert preview.invalid_count == 1
    assert message in preview.rows[0].errors[0]


def test_owner_id_and_email_must_match_when_both_supplied() -> None:
    preview = _preview([_valid_row(owner_email="other@example.org")])

    assert preview.invalid_count == 1
    assert "owner_email must match owner_id" in preview.rows[0].errors[0]


def test_missing_owner_email_lookup_is_rejected() -> None:
    preview = _preview([_valid_row(owner_id="", owner_email="missing@example.org")])

    assert preview.invalid_count == 1
    assert "owner_email must reference an existing owner" in preview.rows[0].errors[0]


def test_invalid_validity_window_is_rejected() -> None:
    preview = _preview([_valid_row(valid_days="", valid_until="2025-01-01T00:00:00+00:00")])

    assert preview.invalid_count == 1
    assert "valid_until must be after valid_from" in preview.rows[0].errors[0]


def test_json_numeric_money_and_integer_values_are_rejected() -> None:
    rows = parse_key_import_json(
        '[{"owner_id":"11111111-1111-4111-8111-111111111111",'
        '"valid_days":"30","cost_limit_eur":10.5,"token_limit_total":1000}]'
    )

    preview = _preview(rows)

    assert preview.invalid_count == 1
    assert "cost_limit_eur must be a string" in preview.rows[0].errors[0]


def test_email_delivery_send_now_requires_configuration() -> None:
    preview = _preview([_valid_row(email_delivery_mode="send-now")])

    assert preview.invalid_count == 1
    assert "email delivery must be enabled" in preview.rows[0].errors[0]


def test_email_delivery_modes_validate_when_configured() -> None:
    context = _context(email_delivery_enabled=True, smtp_configured=True, celery_configured=True)

    preview = _preview(
        [_valid_row(email_delivery_mode="send-now"), _valid_row(owner_email="", email_delivery_mode="enqueue")],
        context=context,
    )

    assert preview.valid_count == 2
    assert [row.email_delivery_mode for row in preview.rows] == ["send-now", "enqueue"]


def test_metadata_secret_and_provider_key_values_are_rejected() -> None:
    metadata = _preview([_valid_row(metadata='{"api_key":"sk-provider-secret"}')])
    provider_key = _preview([_valid_row(label="sk-or-provider-secret")])

    assert metadata.invalid_count == 1
    assert "metadata must not contain secret-looking values" in metadata.rows[0].errors[0]
    assert provider_key.invalid_count == 1
    assert "label must not contain secret-looking values" in provider_key.rows[0].errors[0]


def test_max_rows_enforced() -> None:
    with pytest.raises(ValueError, match="at most 1 rows"):
        _preview([_valid_row(), _valid_row(owner_email="")], max_rows=1)


def test_duplicate_owner_rows_are_classified_without_blocking_preview() -> None:
    preview = _preview([_valid_row(), _valid_row(owner_email="")])

    assert preview.valid_count == 2
    assert preview.duplicate_owner_count == 2
    assert [row.classification for row in preview.rows] == ["duplicate", "duplicate"]


def test_preview_dict_does_not_include_raw_content_or_secret_fields() -> None:
    preview = _preview([_valid_row(note="<script>alert(1)</script>")])
    payload = key_import_preview_to_dict(preview)

    assert payload["rows"][0]["owner_email"] == "ada@example.org"
    assert "owner_email,valid_days" not in str(payload)
    assert "token_hash" not in str(payload)
    assert "encrypted_payload" not in str(payload)
    assert "nonce" not in str(payload)
    assert "password_hash" not in str(payload)
    assert "sk-slaif-plaintext.secret" not in str(payload)
