"""foundational identity and keys tables

Revision ID: 0001_foundational_identity_and_keys
Revises:
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_foundational_identity_and_keys"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institutions")),
    )
    op.create_index(
        "uq_institutions_name_lower",
        "institutions",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "cohorts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cohorts")),
        sa.UniqueConstraint("name", name=op.f("uq_cohorts_name")),
    )
    op.create_index("ix_cohorts_starts_at_ends_at", "cohorts", ["starts_at", "ends_at"], unique=False)

    op.create_table(
        "owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("surname", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["institutions.id"], name=op.f("fk_owners_institution_id_institutions"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owners")),
        sa.UniqueConstraint("email", name=op.f("uq_owners_email")),
    )
    op.create_index(op.f("ix_owners_institution_id"), "owners", ["institution_id"], unique=False)
    op.create_index(op.f("ix_owners_is_active"), "owners", ["is_active"], unique=False)

    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default=sa.text("'admin'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role in ('viewer', 'operator', 'admin', 'superadmin')",
            name=op.f("ck_admin_users_admin_users_role_allowed_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_users")),
        sa.UniqueConstraint("email", name=op.f("uq_admin_users_email")),
    )
    op.create_index(op.f("ix_admin_users_is_active"), "admin_users", ["is_active"], unique=False)

    op.create_table(
        "admin_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["admin_users.id"], name=op.f("fk_admin_sessions_admin_user_id_admin_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        sa.UniqueConstraint("session_token_hash", name=op.f("uq_admin_sessions_session_token_hash")),
    )
    op.create_index(op.f("ix_admin_sessions_admin_user_id"), "admin_sessions", ["admin_user_id"], unique=False)
    op.create_index(op.f("ix_admin_sessions_expires_at"), "admin_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_admin_sessions_revoked_at"), "admin_sessions", ["revoked_at"], unique=False)

    op.create_table(
        "gateway_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_key_id", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.Text(), server_default=sa.text("'sk-slaif'"), nullable=False),
        sa.Column("key_hint", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("hash_algorithm", sa.Text(), server_default=sa.text("'hmac-sha256'"), nullable=False),
        sa.Column("hmac_key_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cost_limit_eur", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("token_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("request_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("cost_used_eur", sa.Numeric(precision=18, scale=9), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_used_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("requests_used_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_reserved_eur", sa.Numeric(precision=18, scale=9), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_reserved_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("requests_reserved_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("rate_limit_requests_per_minute", sa.Integer(), nullable=True),
        sa.Column("rate_limit_tokens_per_minute", sa.BigInteger(), nullable=True),
        sa.Column("max_concurrent_requests", sa.Integer(), nullable=True),
        sa.Column("allow_all_models", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("allowed_models", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("allow_all_endpoints", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("allowed_endpoints", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_quota_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quota_reset_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_admin_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "cost_reserved_eur >= 0",
            name=op.f("ck_gateway_keys_gateway_keys_cost_reserved_eur_non_negative"),
        ),
        sa.CheckConstraint(
            "cost_used_eur >= 0",
            name=op.f("ck_gateway_keys_gateway_keys_cost_used_eur_non_negative"),
        ),
        sa.CheckConstraint(
            "requests_reserved_total >= 0",
            name=op.f("ck_gateway_keys_gateway_keys_requests_reserved_total_non_negative"),
        ),
        sa.CheckConstraint(
            "requests_used_total >= 0",
            name=op.f("ck_gateway_keys_gateway_keys_requests_used_total_non_negative"),
        ),
        sa.CheckConstraint(
            "status in ('active', 'suspended', 'revoked')",
            name=op.f("ck_gateway_keys_gateway_keys_status_allowed_values"),
        ),
        sa.CheckConstraint(
            "tokens_reserved_total >= 0",
            name=op.f("ck_gateway_keys_gateway_keys_tokens_reserved_total_non_negative"),
        ),
        sa.CheckConstraint(
            "tokens_used_total >= 0",
            name=op.f("ck_gateway_keys_gateway_keys_tokens_used_total_non_negative"),
        ),
        sa.CheckConstraint(
            "valid_until > valid_from",
            name=op.f("ck_gateway_keys_gateway_keys_valid_until_after_valid_from"),
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["cohorts.id"], name=op.f("fk_gateway_keys_cohort_id_cohorts"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_gateway_keys_created_by_admin_user_id_admin_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_gateway_keys_owner_id_owners"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gateway_keys")),
        sa.UniqueConstraint("public_key_id", name=op.f("uq_gateway_keys_public_key_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_gateway_keys_token_hash")),
    )
    op.create_index(op.f("ix_gateway_keys_cohort_id"), "gateway_keys", ["cohort_id"], unique=False)
    op.create_index(op.f("ix_gateway_keys_owner_id"), "gateway_keys", ["owner_id"], unique=False)
    op.create_index(op.f("ix_gateway_keys_status"), "gateway_keys", ["status"], unique=False)
    op.create_index(op.f("ix_gateway_keys_valid_until"), "gateway_keys", ["valid_until"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["admin_users.id"], name=op.f("fk_audit_log_admin_user_id_admin_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_action_created_at",
        "audit_log",
        ["action", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_admin_user_id_created_at",
        "audit_log",
        ["admin_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_entity_type_entity_id",
        "audit_log",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index("ix_audit_log_request_id", "audit_log", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_request_id", table_name="audit_log")
    op.drop_index("ix_audit_log_entity_type_entity_id", table_name="audit_log")
    op.drop_index("ix_audit_log_admin_user_id_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_action_created_at", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index(op.f("ix_gateway_keys_valid_until"), table_name="gateway_keys")
    op.drop_index(op.f("ix_gateway_keys_status"), table_name="gateway_keys")
    op.drop_index(op.f("ix_gateway_keys_owner_id"), table_name="gateway_keys")
    op.drop_index(op.f("ix_gateway_keys_cohort_id"), table_name="gateway_keys")
    op.drop_table("gateway_keys")

    op.drop_index(op.f("ix_admin_sessions_revoked_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_expires_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_admin_user_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")

    op.drop_index(op.f("ix_admin_users_is_active"), table_name="admin_users")
    op.drop_table("admin_users")

    op.drop_index(op.f("ix_owners_is_active"), table_name="owners")
    op.drop_index(op.f("ix_owners_institution_id"), table_name="owners")
    op.drop_table("owners")

    op.drop_index("ix_cohorts_starts_at_ends_at", table_name="cohorts")
    op.drop_table("cohorts")

    op.drop_index("uq_institutions_name_lower", table_name="institutions")
    op.drop_table("institutions")
