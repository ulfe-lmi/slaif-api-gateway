"""Add versioned policy bundles and approved catalogs.

Revision ID: 0021_policy_bundles_approved_catalogs
Revises: 0020_hierarchical_recurring_budgets
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_policy_bundles_approved_catalogs"
down_revision = "0020_hierarchical_recurring_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_bundles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "policy_bundle_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("policy_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["bundle_id"], ["policy_bundles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("bundle_id", "revision", name="uq_policy_bundle_revision"),
    )
    op.create_table(
        "approved_catalog_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_kind", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["revision_id"], ["policy_bundle_revisions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("revision_id", "entry_kind", "provider", "name", name="uq_approved_catalog_entry"),
    )


def downgrade() -> None:
    op.drop_table("approved_catalog_entries")
    op.drop_table("policy_bundle_revisions")
    op.drop_table("policy_bundles")
