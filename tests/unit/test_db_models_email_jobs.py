from sqlalchemy import CheckConstraint

from slaif_gateway.db import models  # noqa: F401
from slaif_gateway.db.base import Base

FORBIDDEN_PLAINTEXT_COLUMNS = {
    "plaintext_key",
    "secret_plaintext",
    "plaintext_secret",
    "raw_secret",
    "raw_key",
    "api_key_plaintext",
    "secret",
}


def _table_check_sql(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_email_and_jobs_tables_exist_in_metadata() -> None:
    table_names = set(Base.metadata.tables.keys())

    assert "one_time_secrets" in table_names
    assert "email_deliveries" in table_names
    assert "background_jobs" in table_names


def test_one_time_secrets_has_encrypted_fields_and_no_plaintext_columns() -> None:
    table = Base.metadata.tables["one_time_secrets"]
    column_names = {c.name for c in table.columns}

    assert "encrypted_payload" in column_names
    assert "nonce" in column_names
    assert "expires_at" in column_names
    assert FORBIDDEN_PLAINTEXT_COLUMNS.isdisjoint(column_names)


def test_one_time_secrets_has_status_constraint() -> None:
    checks = _table_check_sql("one_time_secrets")

    assert any("status in" in c for c in checks)


def test_email_deliveries_has_expected_foreign_keys_and_no_plaintext_columns() -> None:
    table = Base.metadata.tables["email_deliveries"]
    column_names = {c.name for c in table.columns}
    fk_tables = {fk.column.table.name for fk in table.foreign_keys}

    assert {"owner_id", "gateway_key_id", "one_time_secret_id"}.issubset(column_names)
    assert {"owners", "gateway_keys", "one_time_secrets"}.issubset(fk_tables)
    assert FORBIDDEN_PLAINTEXT_COLUMNS.isdisjoint(column_names)


def test_email_deliveries_has_status_constraint() -> None:
    checks = _table_check_sql("email_deliveries")

    assert any("status in" in c for c in checks)


def test_background_jobs_has_no_plaintext_columns() -> None:
    table = Base.metadata.tables["background_jobs"]
    column_names = {c.name for c in table.columns}

    assert FORBIDDEN_PLAINTEXT_COLUMNS.isdisjoint(column_names)
