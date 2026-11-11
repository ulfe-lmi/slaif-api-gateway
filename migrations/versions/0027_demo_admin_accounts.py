# OAP Work Order 220-a: CLI-managed fake-admin accounts in isolated control
# tables (demo-admin foundation).
#
# Creates the dedicated ``demo_control`` PostgreSQL schema containing:
#
# * ``fake_admin_accounts`` - demo fake-admin identities, fully separate
#   from ``admin_users``/``admin_sessions`` and gateway keys. Rows are
#   writable ONLY through the trusted operator CLI path (objective 220
#   boundary); no HTTP route creates, resets, enables, disables, or lists
#   these credentials at this stage.
# * ``fake_admin_account_events`` - safe append-only account-change events
#   (bounded reason, generation, action vocabulary; no hash or secret).
#
# The migration creates NO roles and grants NOTHING: explicit least-
# privilege grants for the future demo-web role happen only after that
# role exists (later objective), per the 220-a boundary.
#
# Migration head after this revision: 0027_demo_admin_accounts (35 tables).

"""Isolated demo-control schema: fake-admin accounts and account events.

Revision ID: 0027_demo_admin_accounts
Revises: 0026_request_diagnostics
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0027_demo_admin_accounts"
down_revision = "0026_request_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA demo_control")
    op.create_table(
        "fake_admin_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", postgresql.CITEXT(length=64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "credential_generation",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "char_length(username) >= 3 and char_length(username) <= 64",
            name="demo_fake_admin_accounts_username_length",
        ),
        sa.CheckConstraint(
            r"username ~ '^[A-Za-z][A-Za-z0-9_-]{2,63}$'",
            name="demo_fake_admin_accounts_username_shape",
        ),
        sa.CheckConstraint(
            "credential_generation >= 0",
            name="demo_fake_admin_accounts_generation_nonnegative",
        ),
        sa.UniqueConstraint("username", name="uq_demo_fake_admin_accounts_username"),
        schema="demo_control",
    )
    op.create_index(
        "ix_demo_fake_admin_accounts_is_enabled",
        "fake_admin_accounts",
        ["is_enabled"],
        schema="demo_control",
    )
    op.create_table(
        "fake_admin_account_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "credential_generation",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["demo_control.fake_admin_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action in ('created', 'enabled', 'disabled', 'password_reset')",
            name="demo_fake_admin_account_events_action_allowed",
        ),
        sa.CheckConstraint(
            "reason is null or char_length(reason) <= 512",
            name="demo_fake_admin_account_events_reason_bounded",
        ),
        sa.CheckConstraint(
            "credential_generation >= 0",
            name="demo_fake_admin_account_events_generation_nonnegative",
        ),
        schema="demo_control",
    )
    op.create_index(
        "ix_demo_fake_admin_account_events_account_created",
        "fake_admin_account_events",
        ["account_id", "created_at"],
        schema="demo_control",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demo_fake_admin_account_events_account_created",
        table_name="fake_admin_account_events",
        schema="demo_control",
    )
    op.drop_table("fake_admin_account_events", schema="demo_control")
    op.drop_index(
        "ix_demo_fake_admin_accounts_is_enabled",
        table_name="fake_admin_accounts",
        schema="demo_control",
    )
    op.drop_table("fake_admin_accounts", schema="demo_control")
    op.execute("DROP SCHEMA demo_control")
