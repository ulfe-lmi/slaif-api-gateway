"""Snapshot safe route facts on quota reservations.

Revision ID: 0024_quota_reservation_accounting_facts
Revises: 0023_module_provider_foundation
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0024_quota_reservation_accounting_facts"
down_revision = "0023_module_provider_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quota_reservations", sa.Column("provider", sa.Text(), nullable=True))
    op.add_column("quota_reservations", sa.Column("resolved_model", sa.Text(), nullable=True))
    op.add_column("quota_reservations", sa.Column("streaming", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("quota_reservations", "streaming")
    op.drop_column("quota_reservations", "resolved_model")
    op.drop_column("quota_reservations", "provider")
