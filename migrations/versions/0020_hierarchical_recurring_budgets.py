"""Add hierarchical recurring budget period definitions.

Revision ID: 0020_hierarchical_recurring_budgets
Revises: 0019_service_accounts
Create Date: 2026-08-23

Budgets are PostgreSQL-authoritative recurring limits linked to the
organizational hierarchy or a service identity. They coexist with lifetime
gateway-key limits; no existing row is converted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_hierarchical_recurring_budgets"
down_revision = "0019_service_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("period_type", sa.Text(), nullable=False, server_default=sa.text("'fixed'")),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cost_limit_eur", sa.Numeric(18, 9), nullable=True),
        sa.Column("token_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("request_limit_total", sa.BigInteger(), nullable=True),
        sa.Column("cost_used_eur", sa.Numeric(18, 9), nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_used_total", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("requests_used_total", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_reserved_eur", sa.Numeric(18, 9), nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_reserved_total", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("requests_reserved_total", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("carryover_policy", sa.Text(), nullable=False, server_default=sa.text("'none'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_account_id"], ["owners.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "period_type in ('fixed', 'rolling')",
            name="budget_periods_period_type_allowed_values",
        ),
        sa.CheckConstraint(
            "period_end > period_start",
            name="budget_periods_valid_window",
        ),
        sa.CheckConstraint(
            "cost_limit_eur is null or cost_limit_eur >= 0",
            name="budget_periods_cost_limit_non_negative",
        ),
        sa.CheckConstraint(
            "token_limit_total is null or token_limit_total >= 0",
            name="budget_periods_token_limit_non_negative",
        ),
        sa.CheckConstraint(
            "request_limit_total is null or request_limit_total >= 0",
            name="budget_periods_request_limit_non_negative",
        ),
        sa.CheckConstraint(
            "(cost_limit_eur is not null or token_limit_total is not null or request_limit_total is not null)",
            name="budget_periods_has_at_least_one_limit",
        ),
    )
    op.create_index("ix_budget_periods_scope", "budget_periods", ["organization_id", "team_id", "project_id"])
    op.create_index("ix_budget_periods_owner_service", "budget_periods", ["owner_id", "service_account_id"])


def downgrade() -> None:
    op.drop_table("budget_periods")
