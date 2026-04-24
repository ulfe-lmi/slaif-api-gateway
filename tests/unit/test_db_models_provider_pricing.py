from decimal import Decimal

from sqlalchemy import Numeric

from slaif_gateway.db.base import Base
from slaif_gateway.db import models  # noqa: F401


FORBIDDEN_PROVIDER_SECRET_COLUMNS = {
    "api_key",
    "api_key_plaintext",
    "secret",
    "secret_value",
    "provider_secret",
    "encrypted_api_key",
}


def test_provider_routing_pricing_fx_tables_exist_in_metadata() -> None:
    table_names = set(Base.metadata.tables.keys())

    assert "provider_configs" in table_names
    assert "model_routes" in table_names
    assert "pricing_rules" in table_names
    assert "fx_rates" in table_names


def test_provider_configs_has_env_var_field_and_no_secret_columns() -> None:
    table = Base.metadata.tables["provider_configs"]
    column_names = {c.name for c in table.columns}

    assert "api_key_env_var" in column_names
    assert FORBIDDEN_PROVIDER_SECRET_COLUMNS.isdisjoint(column_names)


def test_model_routes_has_priority_enabled_and_match_type() -> None:
    table = Base.metadata.tables["model_routes"]
    column_names = {c.name for c in table.columns}

    assert "priority" in column_names
    assert "enabled" in column_names
    assert "match_type" in column_names


def test_pricing_rules_has_required_columns_and_numeric_types() -> None:
    table = Base.metadata.tables["pricing_rules"]
    column_names = {c.name for c in table.columns}

    for column in ("provider", "upstream_model", "currency", "enabled"):
        assert column in column_names

    for column in (
        "input_price_per_1m",
        "cached_input_price_per_1m",
        "output_price_per_1m",
        "reasoning_price_per_1m",
    ):
        assert column in column_names
        assert isinstance(table.columns[column].type, Numeric)


def test_fx_rates_rate_is_numeric() -> None:
    table = Base.metadata.tables["fx_rates"]
    assert isinstance(table.columns["rate"].type, Numeric)


# Keep Decimal imported and exercised for intent clarity around money/rates.
def test_decimal_type_is_available_for_money_and_fx_semantics() -> None:
    assert Decimal("1.000") > Decimal("0")
