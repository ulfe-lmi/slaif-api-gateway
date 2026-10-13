"""Durable application record for audited catalog refresh applies.

Revision ID: 0025_catalog_refresh_applications
Revises: 0024_quota_reservation_accounting_facts
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


revision = "0025_catalog_refresh_applications"
down_revision = "0024_quota_reservation_accounting_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_refresh_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("bundle_sha256", sa.Text(), nullable=False),
        sa.Column("receipt_hmac_sha256", sa.Text(), nullable=False),
        sa.Column("plan_sha256", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("operator_actor", sa.Text(), nullable=False),
        sa.Column("db_actor", sa.Text(), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "applied_provider_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_route_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_pricing_created_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_pricing_superseded_old_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_pricing_superseded_new_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_fx_created_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_fx_superseded_old_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "applied_fx_superseded_new_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_providers", sa.Integer(), server_default=text("0"), nullable=False),
        sa.Column("created_routes", sa.Integer(), server_default=text("0"), nullable=False),
        sa.Column("created_pricing", sa.Integer(), server_default=text("0"), nullable=False),
        sa.Column("created_fx", sa.Integer(), server_default=text("0"), nullable=False),
        sa.Column("superseded_pricing", sa.Integer(), server_default=text("0"), nullable=False),
        sa.Column("superseded_fx", sa.Integer(), server_default=text("0"), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "mode in ('bootstrap', 'refresh')", name="catalog_refresh_applications_mode_allowed"
        ),
        sa.CheckConstraint("outcome in ('committed')", name="catalog_refresh_applications_outcome_allowed"),
        sa.UniqueConstraint(
            "bundle_sha256", "plan_sha256", name="uq_catalog_refresh_application_identity"
        ),
    )
    op.create_index(
        "ix_catalog_refresh_applications_run_id",
        "catalog_refresh_applications",
        ["run_id"],
    )
    op.create_index(
        "ix_catalog_refresh_applications_effective_at",
        "catalog_refresh_applications",
        ["effective_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_refresh_applications_effective_at", table_name="catalog_refresh_applications")
    op.drop_index("ix_catalog_refresh_applications_run_id", table_name="catalog_refresh_applications")
    op.drop_table("catalog_refresh_applications")

