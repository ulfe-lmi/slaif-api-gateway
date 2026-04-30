from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from slaif_gateway.services.pricing_import import (
    classify_pricing_import_preview,
    parse_pricing_import_csv,
    parse_pricing_import_json,
    pricing_import_preview_to_dict,
    validate_pricing_import_rows,
)


def _valid_row(**overrides) -> dict[str, object]:
    values: dict[str, object] = {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "endpoint": "chat.completions",
        "currency": "eur",
        "input_price_per_1m": "0.100000000",
        "cached_input_price_per_1m": "0.050000000",
        "output_price_per_1m": "0.200000000",
        "reasoning_price_per_1m": "",
        "request_price": "0",
        "pricing_metadata": '{"source": "manual"}',
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_until": "",
        "source_url": "https://pricing.example.org/catalog",
        "notes": "safe note",
        "enabled": "true",
    }
    values.update(overrides)
    return values


def test_parse_pricing_import_csv_validates_rows_without_mutation() -> None:
    rows = parse_pricing_import_csv(
        "provider,model,input_price_per_1m,output_price_per_1m\n"
        "openai,gpt-4.1-mini,0.10,0.20\n"
    )

    preview = validate_pricing_import_rows(
        rows,
        max_rows=10,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert preview.total_rows == 1
    assert preview.valid_count == 1
    assert preview.invalid_count == 0
    row = preview.rows[0]
    assert row.provider == "openai"
    assert row.model == "gpt-4.1-mini"
    assert row.endpoint == "/v1/chat/completions"
    assert row.currency == "EUR"
    assert row.input_price_per_1m == "0.10"
    assert row.output_price_per_1m == "0.20"
    assert row.classification == "create"


def test_parse_pricing_import_json_rejects_numeric_money_values() -> None:
    rows = parse_pricing_import_json(
        '[{"provider":"openai","model":"gpt-4.1-mini",'
        '"input_price_per_1m":0.10,"output_price_per_1m":"0.20"}]'
    )

    preview = validate_pricing_import_rows(rows, max_rows=10)

    assert preview.valid_count == 0
    assert preview.invalid_count == 1
    assert "decimal string" in preview.rows[0].errors[0]


def test_pricing_import_rejects_unknown_secret_negative_and_window_errors() -> None:
    rows = [
        _valid_row(extra="nope"),
        _valid_row(source_url="https://user:password@pricing.example.org/catalog"),
        _valid_row(pricing_metadata={"api_key": "sk-real-looking-secret"}),
        _valid_row(input_price_per_1m="-0.1"),
        _valid_row(
            valid_from="2026-02-01T00:00:00+00:00",
            valid_until="2026-01-01T00:00:00+00:00",
        ),
        _valid_row(currency="EURO"),
    ]

    preview = validate_pricing_import_rows(rows, max_rows=10)

    assert preview.valid_count == 0
    assert preview.invalid_count == 6
    error_text = "\n".join(row.errors[0] for row in preview.rows)
    assert "unknown fields: extra" in error_text
    assert "source_url must not contain credentials" in error_text
    assert "pricing_metadata must not contain secret-looking values" in error_text
    assert "input_price_per_1m must be non-negative" in error_text
    assert "valid_until must be after valid_from" in error_text
    assert "currency must be a 3-letter code" in error_text


def test_pricing_import_limits_row_count() -> None:
    with pytest.raises(ValueError, match="at most 1 rows"):
        validate_pricing_import_rows([_valid_row(), _valid_row()], max_rows=1)


def test_pricing_import_classifies_duplicate_and_existing_rows() -> None:
    valid_from = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [_valid_row(), _valid_row(), _valid_row(model="gpt-other")]
    preview = validate_pricing_import_rows(rows, max_rows=10, now=valid_from)
    existing = SimpleNamespace(
        currency="EUR",
        valid_from=valid_from,
        valid_until=None,
        enabled=True,
    )

    classified = classify_pricing_import_preview(
        preview,
        existing_rules_by_row={1: [existing], 3: [SimpleNamespace(currency="EUR", valid_from=valid_from - timedelta(days=1), valid_until=None, enabled=True)]},
    )

    assert classified.rows[0].classification == "duplicate"
    assert classified.rows[1].classification == "duplicate"
    assert classified.rows[2].classification == "overlap"
    payload = pricing_import_preview_to_dict(classified)
    assert "sk-real-looking-secret" not in str(payload)
    assert "token_hash" not in str(payload)
