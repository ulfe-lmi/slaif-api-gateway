from slaif_gateway.db.base import Base
from slaif_gateway.db import models  # noqa: F401


def _check_sqltext_for_table(table_name: str) -> str:
    checks = [str(c.sqltext) for c in Base.metadata.tables[table_name].constraints if hasattr(c, "sqltext")]
    return "\n".join(checks).lower()


def test_accounting_tables_exist_in_metadata() -> None:
    table_names = set(Base.metadata.tables.keys())

    assert "quota_reservations" in table_names
    assert "usage_ledger" in table_names
    assert "usage_profiles" in table_names


def test_quota_reservations_has_gateway_key_fk_and_request_id() -> None:
    table = Base.metadata.tables["quota_reservations"]
    column_names = {c.name for c in table.columns}

    assert "gateway_key_id" in column_names
    assert "request_id" in column_names

    fk_targets = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}
    assert ("gateway_key_id", "gateway_keys") in fk_targets


def test_quota_reservations_status_check_constraint_exists() -> None:
    checks = _check_sqltext_for_table("quota_reservations")

    assert "status" in checks
    assert "pending" in checks
    assert "finalized" in checks
    assert "released" in checks
    assert "expired" in checks


def test_usage_ledger_foreign_keys_for_accounting_core() -> None:
    table = Base.metadata.tables["usage_ledger"]
    fk_targets = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}

    assert ("gateway_key_id", "gateway_keys") in fk_targets
    assert ("quota_reservation_id", "quota_reservations") in fk_targets


def test_usage_ledger_has_token_and_cost_columns() -> None:
    table = Base.metadata.tables["usage_ledger"]
    column_names = {c.name for c in table.columns}

    for column in (
        "prompt_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        assert column in column_names

    for column in ("estimated_cost_eur", "actual_cost_eur", "actual_cost_native", "native_currency"):
        assert column in column_names


def test_usage_ledger_has_no_prompt_or_secret_content_columns() -> None:
    table = Base.metadata.tables["usage_ledger"]
    column_names = {c.name for c in table.columns}

    forbidden_columns = {
        "prompt_content",
        "completion_content",
        "response_body",
        "plaintext_key",
        "api_key_plaintext",
        "token_plaintext",
    }
    assert forbidden_columns.isdisjoint(column_names)


def test_usage_profiles_has_safe_profile_columns_and_fks() -> None:
    table = Base.metadata.tables["usage_profiles"]
    column_names = {c.name for c in table.columns}

    for column in (
        "usage_ledger_id",
        "gateway_key_id",
        "endpoint_path",
        "provider",
        "requested_model",
        "resolved_upstream_model",
        "provider_host",
        "provider_endpoint_path",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "tool_call_counts",
        "function_tool_names",
        "provider_reported_cost",
        "slaif_calculated_cost",
        "cost_currency",
        "cost_source",
        "gateway_request_id",
        "profile_metadata",
    ):
        assert column in column_names

    fk_targets = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}
    assert ("usage_ledger_id", "usage_ledger") in fk_targets
    assert ("gateway_key_id", "gateway_keys") in fk_targets


def test_usage_profiles_has_no_prompt_completion_or_raw_body_columns() -> None:
    table = Base.metadata.tables["usage_profiles"]
    column_names = {c.name for c in table.columns}

    forbidden_columns = {
        "prompt",
        "prompt_text",
        "prompt_content",
        "messages",
        "message_content",
        "completion",
        "completion_text",
        "completion_content",
        "request_body",
        "response_body",
        "raw_request",
        "raw_response",
        "provider_key",
        "gateway_plaintext_key",
        "token_hash",
        "encrypted_payload",
        "nonce",
        "session_token",
        "email_body",
        "tool_schema",
        "tool_arguments",
        "tool_results",
    }
    assert forbidden_columns.isdisjoint(column_names)


def test_usage_profiles_has_non_negative_checks() -> None:
    checks = _check_sqltext_for_table("usage_profiles")

    assert "input_tokens >= 0" in checks
    assert "output_tokens >= 0" in checks
    assert "total_tokens >= 0" in checks
    assert "reasoning_tokens is null or reasoning_tokens >= 0" in checks
    assert "cached_tokens is null or cached_tokens >= 0" in checks
    assert "provider_reported_cost is null or provider_reported_cost >= 0" in checks
    assert "slaif_calculated_cost is null or slaif_calculated_cost >= 0" in checks
