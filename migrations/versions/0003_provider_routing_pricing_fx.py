"""provider routing pricing and fx tables

Revision ID: 0003_provider_routing_pricing_fx
Revises: 0002_quota_reservations_and_usage_ledger
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_provider_routing_pricing_fx"
down_revision = "0002_quota_reservations_and_usage_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default=sa.text("'openai_compatible'"), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_env_var", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("300"), nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind in ('openai_compatible')",
            name=op.f("ck_provider_configs_provider_configs_kind_allowed_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_configs")),
        sa.UniqueConstraint("provider", name=op.f("uq_provider_configs_provider")),
    )
    op.create_index("ix_provider_configs_enabled", "provider_configs", ["enabled"], unique=False)

    op.create_table(
        "model_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_model", sa.Text(), nullable=False),
        sa.Column("match_type", sa.Text(), server_default=sa.text("'exact'"), nullable=False),
        sa.Column("endpoint", sa.Text(), server_default=sa.text("'/v1/chat/completions'"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("upstream_model", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("visible_in_models", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supports_streaming", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "match_type in ('exact', 'prefix', 'glob')",
            name=op.f("ck_model_routes_model_routes_match_type_allowed_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_routes")),
    )
    op.create_index("ix_model_routes_requested_model_enabled", "model_routes", ["requested_model", "enabled"], unique=False)
    op.create_index("ix_model_routes_provider_enabled", "model_routes", ["provider", "enabled"], unique=False)
    op.create_index("ix_model_routes_endpoint_enabled", "model_routes", ["endpoint", "enabled"], unique=False)
    op.create_index("ix_model_routes_priority", "model_routes", ["priority"], unique=False)

    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("upstream_model", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), server_default=sa.text("'/v1/chat/completions'"), nullable=False),
        sa.Column("currency", sa.Text(), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("input_price_per_1m", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("cached_input_price_per_1m", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("output_price_per_1m", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("reasoning_price_per_1m", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("request_price", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("pricing_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_price_per_1m is null or input_price_per_1m >= 0",
            name=op.f("ck_pricing_rules_pricing_rules_input_price_per_1m_non_negative"),
        ),
        sa.CheckConstraint(
            "cached_input_price_per_1m is null or cached_input_price_per_1m >= 0",
            name=op.f("ck_pricing_rules_pricing_rules_cached_input_price_per_1m_non_negative"),
        ),
        sa.CheckConstraint(
            "output_price_per_1m is null or output_price_per_1m >= 0",
            name=op.f("ck_pricing_rules_pricing_rules_output_price_per_1m_non_negative"),
        ),
        sa.CheckConstraint(
            "reasoning_price_per_1m is null or reasoning_price_per_1m >= 0",
            name=op.f("ck_pricing_rules_pricing_rules_reasoning_price_per_1m_non_negative"),
        ),
        sa.CheckConstraint(
            "request_price is null or request_price >= 0",
            name=op.f("ck_pricing_rules_pricing_rules_request_price_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_rules")),
        sa.UniqueConstraint(
            "provider",
            "upstream_model",
            "endpoint",
            "valid_from",
            name="uq_pricing_rules_identity",
        ),
    )
    op.create_index(
        "ix_pricing_rules_provider_upstream_model_endpoint_enabled",
        "pricing_rules",
        ["provider", "upstream_model", "endpoint", "enabled"],
        unique=False,
    )
    op.create_index("ix_pricing_rules_valid_from_valid_until", "pricing_rules", ["valid_from", "valid_until"], unique=False)

    op.create_table(
        "fx_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_currency", sa.Text(), nullable=False),
        sa.Column("quote_currency", sa.Text(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=18, scale=9), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rate > 0", name=op.f("ck_fx_rates_fx_rates_rate_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_rates")),
        sa.UniqueConstraint("base_currency", "quote_currency", "valid_from", name="uq_fx_rates_pair_valid_from"),
    )
    op.create_index(
        "ix_fx_rates_base_quote_valid_from_valid_until",
        "fx_rates",
        ["base_currency", "quote_currency", "valid_from", "valid_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fx_rates_base_quote_valid_from_valid_until", table_name="fx_rates")
    op.drop_table("fx_rates")

    op.drop_index("ix_pricing_rules_valid_from_valid_until", table_name="pricing_rules")
    op.drop_index("ix_pricing_rules_provider_upstream_model_endpoint_enabled", table_name="pricing_rules")
    op.drop_table("pricing_rules")

    op.drop_index("ix_model_routes_priority", table_name="model_routes")
    op.drop_index("ix_model_routes_endpoint_enabled", table_name="model_routes")
    op.drop_index("ix_model_routes_provider_enabled", table_name="model_routes")
    op.drop_index("ix_model_routes_requested_model_enabled", table_name="model_routes")
    op.drop_table("model_routes")

    op.drop_index("ix_provider_configs_enabled", table_name="provider_configs")
    op.drop_table("provider_configs")
