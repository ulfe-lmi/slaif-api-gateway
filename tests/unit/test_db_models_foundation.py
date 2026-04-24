from slaif_gateway.db.base import Base
from slaif_gateway.db import models  # noqa: F401


FOUNDATIONAL_TABLES = {
    "institutions",
    "cohorts",
    "owners",
    "admin_users",
    "admin_sessions",
    "gateway_keys",
    "audit_log",
}


def test_foundational_tables_exist_in_metadata() -> None:
    table_names = set(Base.metadata.tables.keys())

    assert FOUNDATIONAL_TABLES.issubset(table_names)


def test_legacy_or_future_tables_not_in_first_models_slice() -> None:
    table_names = set(Base.metadata.tables.keys())

    assert "key_owners" not in table_names
    assert "model_pricing" not in table_names


def test_gateway_keys_has_only_safe_key_storage_columns() -> None:
    gateway_keys_table = Base.metadata.tables["gateway_keys"]
    column_names = {column.name for column in gateway_keys_table.columns}

    assert "token_hash" in column_names

    forbidden_columns = {
        "plaintext_key",
        "api_key_plaintext",
        "secret_plaintext",
        "key_plaintext",
        "token_plaintext",
    }
    assert forbidden_columns.isdisjoint(column_names)


def test_gateway_keys_status_does_not_store_expired() -> None:
    gateway_keys_table = Base.metadata.tables["gateway_keys"]

    check_clauses = [str(constraint.sqltext) for constraint in gateway_keys_table.constraints if hasattr(constraint, "sqltext")]

    joined = "\n".join(check_clauses).lower()
    assert "active" in joined
    assert "suspended" in joined
    assert "revoked" in joined
    assert "expired" not in joined


def test_identity_and_audit_tables_have_expected_columns() -> None:
    owners_columns = {column.name for column in Base.metadata.tables["owners"].columns}
    admin_users_columns = {column.name for column in Base.metadata.tables["admin_users"].columns}
    audit_log_columns = {column.name for column in Base.metadata.tables["audit_log"].columns}

    assert "email" in owners_columns
    assert "email" in admin_users_columns
    assert "action" in audit_log_columns
