"""usage profiles

Revision ID: 0007_usage_profiles
Revises: 0006_email_delivery_attempt_state
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0007_usage_profiles"
down_revision = "0006_email_delivery_attempt_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("endpoint_path", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("requested_model", sa.Text(), nullable=True),
        sa.Column("resolved_upstream_model", sa.Text(), nullable=True),
        sa.Column("provider_host", sa.Text(), nullable=True),
        sa.Column("provider_endpoint_path", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=True),
        sa.Column("cached_tokens", sa.BigInteger(), nullable=True),
        sa.Column(
            "tool_call_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "function_tool_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("provider_reported_cost", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("slaif_calculated_cost", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("cost_currency", sa.Text(), nullable=True),
        sa.Column("cost_source", sa.Text(), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("gateway_request_id", sa.Text(), nullable=True),
        sa.Column(
            "profile_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "cost_source in ('provider_reported', 'slaif_calculated', 'mixed', 'unknown')",
            name=op.f("ck_usage_profiles_usage_profiles_cost_source_allowed_values"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_input_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_output_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "total_tokens >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_total_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "reasoning_tokens is null or reasoning_tokens >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_reasoning_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "cached_tokens is null or cached_tokens >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_cached_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "provider_reported_cost is null or provider_reported_cost >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_provider_reported_cost_non_negative"),
        ),
        sa.CheckConstraint(
            "slaif_calculated_cost is null or slaif_calculated_cost >= 0",
            name=op.f("ck_usage_profiles_usage_profiles_slaif_calculated_cost_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["cohorts.id"],
            name=op.f("fk_usage_profiles_cohort_id_cohorts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name=op.f("fk_usage_profiles_gateway_key_id_gateway_keys"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_usage_profiles_institution_id_institutions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["owners.id"],
            name=op.f("fk_usage_profiles_owner_id_owners"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["usage_ledger_id"],
            ["usage_ledger.id"],
            name=op.f("fk_usage_profiles_usage_ledger_id_usage_ledger"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_profiles")),
        sa.UniqueConstraint("usage_ledger_id", name=op.f("uq_usage_profiles_usage_ledger_id")),
    )
    op.create_index(
        "ix_usage_profiles_gateway_key_id_created_at",
        "usage_profiles",
        ["gateway_key_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_profiles_owner_id_created_at",
        "usage_profiles",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_profiles_institution_id_created_at",
        "usage_profiles",
        ["institution_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_profiles_cohort_id_created_at",
        "usage_profiles",
        ["cohort_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_profiles_endpoint_provider_model_created_at",
        "usage_profiles",
        ["endpoint_path", "provider", "requested_model", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_profiles_endpoint_provider_model_created_at", table_name="usage_profiles")
    op.drop_index("ix_usage_profiles_cohort_id_created_at", table_name="usage_profiles")
    op.drop_index("ix_usage_profiles_institution_id_created_at", table_name="usage_profiles")
    op.drop_index("ix_usage_profiles_owner_id_created_at", table_name="usage_profiles")
    op.drop_index("ix_usage_profiles_gateway_key_id_created_at", table_name="usage_profiles")
    op.drop_table("usage_profiles")
