"""key templates

Revision ID: 0009_key_templates
Revises: 0008_trusted_calibration_keys
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0009_key_templates"
down_revision = "0008_trusted_calibration_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "key_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("current_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("length(btrim(name)) > 0", name="key_templates_name_non_empty"),
        sa.CheckConstraint(
            "status in ('active', 'archived')",
            name="key_templates_status_allowed_values",
        ),
        sa.ForeignKeyConstraint(["archived_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_key_templates_created_by_admin_id", "key_templates", ["created_by_admin_id"])
    op.create_index("ix_key_templates_current_revision_id", "key_templates", ["current_revision_id"])
    op.create_index("ix_key_templates_status_created_at", "key_templates", ["status", "created_at"])
    op.create_index("uq_key_templates_name_lower", "key_templates", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "key_template_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.Text(), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("source_calibration_gateway_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_time_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_time_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_multiplier", sa.Numeric(18, 9), nullable=True),
        sa.Column(
            "allowed_endpoints",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "allowed_models",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "allowed_providers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "allowed_hosted_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "hosted_capabilities_requiring_review",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("request_limit_total", sa.BigInteger(), nullable=False),
        sa.Column("token_limit_total", sa.BigInteger(), nullable=False),
        sa.Column("input_token_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("output_token_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("reasoning_token_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("cost_limit_eur", sa.Numeric(18, 9), nullable=True),
        sa.Column("max_input_tokens_per_request", sa.BigInteger(), nullable=True),
        sa.Column("max_output_tokens_per_request", sa.BigInteger(), nullable=True),
        sa.Column("max_total_tokens_per_request", sa.BigInteger(), nullable=True),
        sa.Column("max_single_request_cost_eur", sa.Numeric(18, 9), nullable=True),
        sa.Column(
            "rate_limit_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("validity_days_default", sa.Integer(), nullable=True),
        sa.Column("email_delivery_mode_default", sa.Text(), nullable=True),
        sa.Column(
            "template_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_audit_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("revision_number > 0", name="key_template_revisions_revision_number_positive"),
        sa.CheckConstraint(
            "source_type in ('manual', 'calibration_proposal')",
            name="key_template_revisions_source_type_allowed_values",
        ),
        sa.CheckConstraint("request_limit_total > 0", name="key_template_revisions_request_limit_positive"),
        sa.CheckConstraint("token_limit_total >= 0", name="key_template_revisions_token_limit_non_negative"),
        sa.CheckConstraint(
            "input_token_limit_total is null or input_token_limit_total >= 0",
            name="key_template_revisions_input_token_limit_non_negative",
        ),
        sa.CheckConstraint(
            "output_token_limit_total is null or output_token_limit_total >= 0",
            name="key_template_revisions_output_token_limit_non_negative",
        ),
        sa.CheckConstraint(
            "reasoning_token_limit_total is null or reasoning_token_limit_total >= 0",
            name="key_template_revisions_reasoning_token_limit_non_negative",
        ),
        sa.CheckConstraint(
            "cost_limit_eur is null or cost_limit_eur >= 0",
            name="key_template_revisions_cost_limit_non_negative",
        ),
        sa.CheckConstraint(
            "max_input_tokens_per_request is null or max_input_tokens_per_request >= 0",
            name="key_template_revisions_max_input_non_negative",
        ),
        sa.CheckConstraint(
            "max_output_tokens_per_request is null or max_output_tokens_per_request >= 0",
            name="key_template_revisions_max_output_non_negative",
        ),
        sa.CheckConstraint(
            "max_total_tokens_per_request is null or max_total_tokens_per_request >= 0",
            name="key_template_revisions_max_total_non_negative",
        ),
        sa.CheckConstraint(
            "max_single_request_cost_eur is null or max_single_request_cost_eur >= 0",
            name="key_template_revisions_max_cost_non_negative",
        ),
        sa.CheckConstraint(
            "source_multiplier is null or source_multiplier > 0",
            name="key_template_revisions_source_multiplier_positive",
        ),
        sa.CheckConstraint(
            "validity_days_default is null or validity_days_default > 0",
            name="key_template_revisions_validity_days_positive",
        ),
        sa.ForeignKeyConstraint(["created_audit_log_id"], ["audit_log.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_calibration_gateway_key_id"], ["gateway_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["key_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "revision_number", name="uq_key_template_revisions_template_revision"),
    )
    op.create_index(
        "ix_key_template_revisions_created_by_admin_id",
        "key_template_revisions",
        ["created_by_admin_id"],
    )
    op.create_index(
        "ix_key_template_revisions_source_calibration_key",
        "key_template_revisions",
        ["source_calibration_gateway_key_id"],
    )
    op.create_index(
        "ix_key_template_revisions_template_id_created_at",
        "key_template_revisions",
        ["template_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_key_template_revisions_template_id_created_at", table_name="key_template_revisions")
    op.drop_index("ix_key_template_revisions_source_calibration_key", table_name="key_template_revisions")
    op.drop_index("ix_key_template_revisions_created_by_admin_id", table_name="key_template_revisions")
    op.drop_table("key_template_revisions")
    op.drop_index("uq_key_templates_name_lower", table_name="key_templates")
    op.drop_index("ix_key_templates_status_created_at", table_name="key_templates")
    op.drop_index("ix_key_templates_current_revision_id", table_name="key_templates")
    op.drop_index("ix_key_templates_created_by_admin_id", table_name="key_templates")
    op.drop_table("key_templates")
