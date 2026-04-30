from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.services.fx_import import (
    classify_fx_import_preview,
    fx_import_preview_to_dict,
    parse_fx_import_csv,
    parse_fx_import_json,
    validate_fx_import_rows,
)


def _valid_row(**overrides) -> dict[str, object]:
    row = {
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": "0.920000000",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "source": "safe source",
        "metadata": '{"provider": "manual"}',
        "notes": "safe note",
    }
    row.update(overrides)
    return row


def _preview(rows: list[dict[str, object]], *, max_rows: int = 1000):
    return validate_fx_import_rows(rows, max_rows=max_rows, now=datetime(2026, 1, 1, tzinfo=UTC))


def test_valid_csv_and_json_parse() -> None:
    csv_rows = parse_fx_import_csv("base_currency,quote_currency,rate\nUSD,EUR,0.920000000\n")
    json_rows = parse_fx_import_json('[{"base_currency":"USD","quote_currency":"EUR","rate":"0.920000000"}]')

    assert csv_rows[0]["base_currency"] == "USD"
    assert json_rows[0]["quote_currency"] == "EUR"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unknown", "value", "unknown fields"),
        ("base_currency", "USDX", "currency must be a 3-letter code"),
        ("quote_currency", "USDX", "currency must be a 3-letter code"),
        ("quote_currency", "USD", "base_currency and quote_currency must differ"),
        ("rate", "not-decimal", "rate must be a decimal string"),
        ("rate", "0", "rate must be positive"),
        ("rate", "-0.1", "rate must be positive"),
        ("valid_until", "2025-01-01T00:00:00+00:00", "valid_until must be after valid_from"),
    ],
)
def test_invalid_rows_are_rejected(field: str, value: str, message: str) -> None:
    preview = _preview([_valid_row(**{field: value})])

    assert preview.invalid_count == 1
    assert message in preview.rows[0].errors[0]


def test_json_numeric_rate_is_rejected() -> None:
    rows = parse_fx_import_json('[{"base_currency":"USD","quote_currency":"EUR","rate":0.92}]')

    preview = _preview(rows)

    assert preview.invalid_count == 1
    assert "rate must be a decimal string" in preview.rows[0].errors[0]


def test_secret_looking_source_note_and_metadata_are_rejected() -> None:
    source = _preview([_valid_row(source="sk-provider-secret")])
    notes = _preview([_valid_row(notes="Bearer provider-secret")])
    metadata = _preview([_valid_row(metadata='{"api_key":"sk-provider-secret"}')])

    assert source.invalid_count == 1
    assert "source must not contain secret-looking values" in source.rows[0].errors[0]
    assert notes.invalid_count == 1
    assert "notes must not contain secret-looking values" in notes.rows[0].errors[0]
    assert metadata.invalid_count == 1
    assert "metadata must not contain secret-looking values" in metadata.rows[0].errors[0]


def test_max_rows_enforced() -> None:
    with pytest.raises(ValueError, match="at most 1 rows"):
        _preview([_valid_row(), _valid_row(base_currency="GBP")], max_rows=1)


def test_duplicate_and_existing_classification() -> None:
    preview = _preview(
        [
            _valid_row(),
            _valid_row(),
            _valid_row(base_currency="GBP", rate="1.160000000"),
            _valid_row(base_currency="CAD", rate="0.680000000"),
            _valid_row(base_currency="CHF", rate="1.040000000"),
        ]
    )
    classified = classify_fx_import_preview(
        preview,
        existing_rates_by_row={
            1: [
                SimpleNamespace(
                    base_currency="USD",
                    quote_currency="EUR",
                    rate=Decimal("0.920000000"),
                    source="safe source",
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                    valid_until=None,
                )
            ],
            3: [
                SimpleNamespace(
                    base_currency="GBP",
                    quote_currency="EUR",
                    rate=Decimal("1.150000000"),
                    source="old source",
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                    valid_until=None,
                )
            ],
            4: [
                SimpleNamespace(
                    base_currency="CAD",
                    quote_currency="EUR",
                    rate=Decimal("0.670000000"),
                    source="old source",
                    valid_from=datetime(2025, 12, 1, tzinfo=UTC),
                    valid_until=datetime(2026, 2, 1, tzinfo=UTC),
                )
            ],
        },
    )

    assert [row.classification for row in classified.rows] == [
        "duplicate",
        "duplicate",
        "update",
        "conflict",
        "create",
    ]


def test_preview_dict_does_not_include_raw_content() -> None:
    preview = _preview([_valid_row(notes="<script>alert(1)</script>")])
    payload = fx_import_preview_to_dict(preview)

    assert payload["rows"][0]["base_currency"] == "USD"
    assert "base_currency,quote_currency" not in str(payload)
    assert "token_hash" not in str(payload)
    assert "encrypted_payload" not in str(payload)
    assert "nonce" not in str(payload)
    assert "password_hash" not in str(payload)
