"""Add provider governance metadata.

Revision ID: 0022_provider_governance
Revises: 0021_policy_bundles_approved_catalogs
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_provider_governance"
down_revision = "0021_policy_bundles_approved_catalogs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_configs", sa.Column("governance_region", sa.Text(), nullable=True))
    op.add_column("provider_configs", sa.Column("retention_policy", sa.Text(), nullable=True))
    op.add_column("provider_configs", sa.Column("training_use", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("provider_configs", sa.Column("zdr_claimed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("provider_configs", sa.Column("tool_destinations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("provider_configs", sa.Column("evidence_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("provider_configs", sa.Column("reviewer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_configs", "reviewer")
    op.drop_column("provider_configs", "evidence_date")
    op.drop_column("provider_configs", "tool_destinations")
    op.drop_column("provider_configs", "zdr_claimed")
    op.drop_column("provider_configs", "training_use")
    op.drop_column("provider_configs", "retention_policy")
    op.drop_column("provider_configs", "governance_region")
