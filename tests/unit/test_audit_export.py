
from slaif_gateway.services.audit_export import (
    FINANCE_COLUMNS, anonymize_owner_rows, to_cef, to_csv, to_json,
)


def test_csv_escapes_formula_injection():
    csv_value = to_csv(FINANCE_COLUMNS, [{"timestamp": "=cmd", "organization_id": "@bad", "team_id": "+x",
                                          "project_id": "-y", "owner_id": "o", "gateway_key_id": "k",
                                          "provider": "p", "model": "m", "input_tokens": 1,
                                          "output_tokens": 2, "cost_eur": 3}])
    assert "'=cmd" in csv_value
    assert "'+x" in csv_value
    assert "'-y" in csv_value


def test_json_export_is_deterministic_and_metadata_only():
    value = to_json([{"b": 2, "a": 1}])
    assert value == '[{"a":1,"b":2}]'


def test_cef_escapes_delimiters():
    cef = to_cef([{"timestamp": "2026-01-01T00:00:00Z", "event_type": "auth|failure",
                   "subject_id": "user=1\n", "outcome": "denied"}])
    assert "auth\\|failure" in cef
    assert "user\\=1 " in cef


def test_anonymization_is_stable_without_direct_ids():
    rows = anonymize_owner_rows([{"owner_id": "direct-uuid"}, {"owner_id": "direct-uuid"}])
    assert all(row["owner_id"] != "direct-uuid" for row in rows)
    assert rows[0]["owner_id"] == rows[1]["owner_id"]
