"""email one-time secrets deliveries and background jobs tables

Revision ID: 0004_email_secrets_and_background_jobs
Revises: 0003_provider_routing_pricing_fx
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_email_secrets_and_background_jobs"
down_revision = "0003_provider_routing_pricing_fx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "one_time_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("encryption_key_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose in ('gateway_key_email', 'gateway_key_rotation_email')",
            name=op.f("ck_one_time_secrets_one_time_secrets_purpose_allowed_values"),
        ),
        sa.CheckConstraint(
            "status in ('pending', 'consumed', 'expired', 'revoked')",
            name=op.f("ck_one_time_secrets_one_time_secrets_status_allowed_values"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_one_time_secrets_owner_id_owners"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name=op.f("fk_one_time_secrets_gateway_key_id_gateway_keys"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_one_time_secrets")),
    )
    op.create_index("ix_one_time_secrets_status_expires_at", "one_time_secrets", ["status", "expires_at"], unique=False)
    op.create_index("ix_one_time_secrets_gateway_key_id", "one_time_secrets", ["gateway_key_id"], unique=False)
    op.create_index("ix_one_time_secrets_expires_at", "one_time_secrets", ["expires_at"], unique=False)
    op.create_index("ix_one_time_secrets_consumed_at", "one_time_secrets", ["consumed_at"], unique=False)

    op.create_table(
        "email_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("one_time_secret_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_email", postgresql.CITEXT(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('pending', 'sent', 'failed', 'cancelled')",
            name=op.f("ck_email_deliveries_email_deliveries_status_allowed_values"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_email_deliveries_owner_id_owners"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name=op.f("fk_email_deliveries_gateway_key_id_gateway_keys"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["one_time_secret_id"],
            ["one_time_secrets.id"],
            name=op.f("fk_email_deliveries_one_time_secret_id_one_time_secrets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_deliveries")),
    )
    op.create_index("ix_email_deliveries_owner_id", "email_deliveries", ["owner_id"], unique=False)
    op.create_index("ix_email_deliveries_gateway_key_id", "email_deliveries", ["gateway_key_id"], unique=False)
    op.create_index("ix_email_deliveries_status_created_at", "email_deliveries", ["status", "created_at"], unique=False)
    op.create_index("ix_email_deliveries_one_time_secret_id", "email_deliveries", ["one_time_secret_id"], unique=False)

    op.create_table(
        "background_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("celery_task_id", sa.Text(), nullable=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("created_by_admin_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_background_jobs_background_jobs_status_allowed_values"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_background_jobs_created_by_admin_user_id_admin_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_background_jobs")),
    )
    op.create_index("ix_background_jobs_status_created_at", "background_jobs", ["status", "created_at"], unique=False)
    op.create_index("ix_background_jobs_celery_task_id", "background_jobs", ["celery_task_id"], unique=False)
    op.create_index("ix_background_jobs_job_type_created_at", "background_jobs", ["job_type", "created_at"], unique=False)
    op.create_index(
        "ix_background_jobs_created_by_admin_user_id_created_at",
        "background_jobs",
        ["created_by_admin_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_created_by_admin_user_id_created_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_job_type_created_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_celery_task_id", table_name="background_jobs")
    op.drop_index("ix_background_jobs_status_created_at", table_name="background_jobs")
    op.drop_table("background_jobs")

    op.drop_index("ix_email_deliveries_one_time_secret_id", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_status_created_at", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_gateway_key_id", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_owner_id", table_name="email_deliveries")
    op.drop_table("email_deliveries")

    op.drop_index("ix_one_time_secrets_consumed_at", table_name="one_time_secrets")
    op.drop_index("ix_one_time_secrets_expires_at", table_name="one_time_secrets")
    op.drop_index("ix_one_time_secrets_gateway_key_id", table_name="one_time_secrets")
    op.drop_index("ix_one_time_secrets_status_expires_at", table_name="one_time_secrets")
    op.drop_table("one_time_secrets")
