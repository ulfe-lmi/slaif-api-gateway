"""Add exclusive external-tool quota fence foundation.

Revision ID: 0015_external_tool_exclusive_fence
Revises: 0014_codex_context_accounting_compaction
Create Date: 2026-08-19

This migration adds durable, PostgreSQL-authoritative coordination for a
future provider-hosted external-tool fenced mode. It stores:

- per-key fence state on the already-serialized ``gateway_keys`` row so the
  key row lock remains the single concurrency truth;
- quota-mode and canonical external-tool facts on ``quota_reservations``.

Defaults double as the safe backfill for existing rows: every prior key is
``none`` with all fence fields null, and every prior reservation is
``strict_bounded`` with empty external arrays. Objective 014 writes only the
``none`` and ``active`` fence states; the reserved ``held`` transition and
provider-hosted execution are owned by later objectives. No prompt, body,
tool argument/result, raw MCP value/URL, authorization, or provider response
content is stored by this migration.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0015_external_tool_exclusive_fence"
down_revision = "0014_codex_context_accounting_compaction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_keys",
        sa.Column(
            "external_tool_fence_state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    op.add_column(
        "gateway_keys",
        sa.Column(
            "external_tool_fence_reservation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quota_reservations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "gateway_keys",
        sa.Column("external_tool_fence_request_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "gateway_keys",
        sa.Column("external_tool_fence_acquired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gateway_keys",
        sa.Column("external_tool_fence_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "gateway_keys_external_tool_fence_state_allowed_values",
        "gateway_keys",
        "external_tool_fence_state in ('none', 'active', 'held')",
    )
    op.create_check_constraint(
        "gateway_keys_external_tool_fence_none_shape",
        "gateway_keys",
        "(external_tool_fence_state = 'none') = "
        "(external_tool_fence_reservation_id is null "
        "and external_tool_fence_request_id is null "
        "and external_tool_fence_acquired_at is null "
        "and external_tool_fence_expires_at is null)",
    )
    op.create_check_constraint(
        "gateway_keys_external_tool_fence_bound_shape",
        "gateway_keys",
        "(external_tool_fence_state in ('active', 'held')) = "
        "(external_tool_fence_reservation_id is not null "
        "and external_tool_fence_request_id is not null "
        "and external_tool_fence_acquired_at is not null "
        "and external_tool_fence_expires_at is not null)",
    )
    op.create_index(
        "ix_gateway_keys_external_tool_fence_state_expires_at",
        "gateway_keys",
        ["external_tool_fence_state", "external_tool_fence_expires_at"],
        unique=False,
    )

    op.add_column(
        "quota_reservations",
        sa.Column(
            "quota_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'strict_bounded'"),
        ),
    )
    op.add_column(
        "quota_reservations",
        sa.Column(
            "external_tool_capabilities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "quota_reservations",
        sa.Column(
            "external_tool_destination_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "quota_reservations_quota_mode_allowed_values",
        "quota_reservations",
        "quota_mode in ('strict_bounded', 'external_tool_fenced')",
    )
    op.create_check_constraint(
        "quota_reservations_strict_mode_empty_external_facts",
        "quota_reservations",
        "(quota_mode = 'strict_bounded') = "
        "(external_tool_capabilities = '[]'::jsonb "
        "and external_tool_destination_ids = '[]'::jsonb)",
    )
    op.create_check_constraint(
        "quota_reservations_fenced_mode_nonempty_capabilities",
        "quota_reservations",
        "(quota_mode = 'external_tool_fenced') = "
        "(jsonb_typeof(external_tool_capabilities) = 'array' "
        "and external_tool_capabilities <> '[]'::jsonb)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "quota_reservations_fenced_mode_nonempty_capabilities",
        "quota_reservations",
        type_="check",
    )
    op.drop_constraint(
        "quota_reservations_strict_mode_empty_external_facts",
        "quota_reservations",
        type_="check",
    )
    op.drop_constraint(
        "quota_reservations_quota_mode_allowed_values",
        "quota_reservations",
        type_="check",
    )
    op.drop_column("quota_reservations", "external_tool_destination_ids")
    op.drop_column("quota_reservations", "external_tool_capabilities")
    op.drop_column("quota_reservations", "quota_mode")

    op.drop_index(
        "ix_gateway_keys_external_tool_fence_state_expires_at",
        table_name="gateway_keys",
    )
    op.drop_constraint(
        "gateway_keys_external_tool_fence_bound_shape",
        "gateway_keys",
        type_="check",
    )
    op.drop_constraint(
        "gateway_keys_external_tool_fence_none_shape",
        "gateway_keys",
        type_="check",
    )
    op.drop_constraint(
        "gateway_keys_external_tool_fence_state_allowed_values",
        "gateway_keys",
        type_="check",
    )
    op.drop_column("gateway_keys", "external_tool_fence_expires_at")
    op.drop_column("gateway_keys", "external_tool_fence_acquired_at")
    op.drop_column("gateway_keys", "external_tool_fence_request_id")
    op.drop_column("gateway_keys", "external_tool_fence_reservation_id")
    op.drop_column("gateway_keys", "external_tool_fence_state")
