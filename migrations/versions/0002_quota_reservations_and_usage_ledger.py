"""quota reservations and usage ledger tables

Revision ID: 0002_quota_reservations_and_usage_ledger
Revises: 0001_foundational_identity_and_keys
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_quota_reservations_and_usage_ledger"
down_revision = "0001_foundational_identity_and_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quota_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("requested_model", sa.Text(), nullable=True),
        sa.Column("reserved_cost_eur", sa.Numeric(precision=18, scale=9), server_default=sa.text("0"), nullable=False),
        sa.Column("reserved_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("reserved_requests", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('pending', 'finalized', 'released', 'expired')",
            name=op.f("ck_quota_reservations_quota_reservations_status_allowed_values"),
        ),
        sa.CheckConstraint(
            "reserved_cost_eur >= 0",
            name=op.f("ck_quota_reservations_quota_reservations_reserved_cost_eur_non_negative"),
        ),
        sa.CheckConstraint(
            "reserved_tokens >= 0",
            name=op.f("ck_quota_reservations_quota_reservations_reserved_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "reserved_requests >= 0",
            name=op.f("ck_quota_reservations_quota_reservations_reserved_requests_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name=op.f("fk_quota_reservations_gateway_key_id_gateway_keys"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quota_reservations")),
        sa.UniqueConstraint("request_id", name=op.f("uq_quota_reservations_request_id")),
    )
    op.create_index("ix_quota_reservations_gateway_key_id", "quota_reservations", ["gateway_key_id"], unique=False)
    op.create_index("ix_quota_reservations_status_expires_at", "quota_reservations", ["status", "expires_at"], unique=False)
    op.create_index("ix_quota_reservations_request_id", "quota_reservations", ["request_id"], unique=False)

    op.create_table(
        "usage_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("quota_reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_email_snapshot", postgresql.CITEXT(), nullable=True),
        sa.Column("owner_name_snapshot", sa.Text(), nullable=True),
        sa.Column("owner_surname_snapshot", sa.Text(), nullable=True),
        sa.Column("institution_name_snapshot", sa.Text(), nullable=True),
        sa.Column("cohort_name_snapshot", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("http_method", sa.Text(), server_default=sa.text("'POST'"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("requested_model", sa.Text(), nullable=True),
        sa.Column("resolved_model", sa.Text(), nullable=True),
        sa.Column("upstream_request_id", sa.Text(), nullable=True),
        sa.Column("streaming", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("accounting_status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("completion_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("cached_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("reasoning_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("estimated_cost_eur", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("actual_cost_eur", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("actual_cost_native", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("native_currency", sa.Text(), nullable=True),
        sa.Column("usage_raw", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("response_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "accounting_status in ('pending', 'finalized', 'estimated', 'failed', 'interrupted', 'released')",
            name=op.f("ck_usage_ledger_usage_ledger_accounting_status_allowed_values"),
        ),
        sa.CheckConstraint("prompt_tokens >= 0", name=op.f("ck_usage_ledger_usage_ledger_prompt_tokens_non_negative")),
        sa.CheckConstraint(
            "completion_tokens >= 0",
            name=op.f("ck_usage_ledger_usage_ledger_completion_tokens_non_negative"),
        ),
        sa.CheckConstraint("input_tokens >= 0", name=op.f("ck_usage_ledger_usage_ledger_input_tokens_non_negative")),
        sa.CheckConstraint("output_tokens >= 0", name=op.f("ck_usage_ledger_usage_ledger_output_tokens_non_negative")),
        sa.CheckConstraint("cached_tokens >= 0", name=op.f("ck_usage_ledger_usage_ledger_cached_tokens_non_negative")),
        sa.CheckConstraint(
            "reasoning_tokens >= 0",
            name=op.f("ck_usage_ledger_usage_ledger_reasoning_tokens_non_negative"),
        ),
        sa.CheckConstraint("total_tokens >= 0", name=op.f("ck_usage_ledger_usage_ledger_total_tokens_non_negative")),
        sa.CheckConstraint(
            "estimated_cost_eur is null or estimated_cost_eur >= 0",
            name=op.f("ck_usage_ledger_usage_ledger_estimated_cost_eur_non_negative"),
        ),
        sa.CheckConstraint(
            "actual_cost_eur is null or actual_cost_eur >= 0",
            name=op.f("ck_usage_ledger_usage_ledger_actual_cost_eur_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["cohorts.id"], name=op.f("fk_usage_ledger_cohort_id_cohorts"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name=op.f("fk_usage_ledger_gateway_key_id_gateway_keys"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_usage_ledger_institution_id_institutions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_usage_ledger_owner_id_owners"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["quota_reservation_id"],
            ["quota_reservations.id"],
            name=op.f("fk_usage_ledger_quota_reservation_id_quota_reservations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_ledger")),
        sa.UniqueConstraint("request_id", name=op.f("uq_usage_ledger_request_id")),
    )
    op.create_index("ix_usage_ledger_gateway_key_id_created_at", "usage_ledger", ["gateway_key_id", "created_at"], unique=False)
    op.create_index("ix_usage_ledger_owner_id_created_at", "usage_ledger", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_usage_ledger_cohort_id_created_at", "usage_ledger", ["cohort_id", "created_at"], unique=False)
    op.create_index("ix_usage_ledger_provider_resolved_model", "usage_ledger", ["provider", "resolved_model"], unique=False)
    op.create_index("ix_usage_ledger_request_id", "usage_ledger", ["request_id"], unique=False)
    op.create_index("ix_usage_ledger_institution_id_created_at", "usage_ledger", ["institution_id", "created_at"], unique=False)
    op.create_index("ix_usage_ledger_endpoint_created_at", "usage_ledger", ["endpoint", "created_at"], unique=False)
    op.create_index(
        "ix_usage_ledger_accounting_status_created_at",
        "usage_ledger",
        ["accounting_status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_accounting_status_created_at", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_endpoint_created_at", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_institution_id_created_at", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_request_id", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_provider_resolved_model", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_cohort_id_created_at", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_owner_id_created_at", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_gateway_key_id_created_at", table_name="usage_ledger")
    op.drop_table("usage_ledger")

    op.drop_index("ix_quota_reservations_request_id", table_name="quota_reservations")
    op.drop_index("ix_quota_reservations_status_expires_at", table_name="quota_reservations")
    op.drop_index("ix_quota_reservations_gateway_key_id", table_name="quota_reservations")
    op.drop_table("quota_reservations")
