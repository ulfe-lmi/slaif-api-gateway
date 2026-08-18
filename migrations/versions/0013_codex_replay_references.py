"""HMAC-only Codex replay references.

Revision ID: 0013_codex_replay_references
Revises: 0012_conversation_references
Create Date: 2026-08-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0013_codex_replay_references"
down_revision = "0012_conversation_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "codex_replay_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_request_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upstream_model", sa.Text(), nullable=False),
        sa.Column("item_kind", sa.Text(), nullable=False),
        sa.Column("item_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("call_id_hmac", sa.String(length=64), nullable=True),
        sa.Column("hmac_key_version", sa.Integer(), nullable=False),
        sa.Column("tool_namespace", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_kind in ('reasoning', 'function_call', 'custom_tool_call')",
            name="codex_replay_references_item_kind_allowed_values",
        ),
        sa.CheckConstraint(
            "item_id_hmac ~ '^[0-9a-f]{64}$'",
            name="codex_replay_references_item_hmac_format",
        ),
        sa.CheckConstraint(
            "call_id_hmac is null or call_id_hmac ~ '^[0-9a-f]{64}$'",
            name="codex_replay_references_call_hmac_format",
        ),
        sa.CheckConstraint(
            "hmac_key_version > 0",
            name="codex_replay_references_hmac_version_positive",
        ),
        sa.CheckConstraint(
            "length(btrim(source_request_id)) > 0",
            name="codex_replay_references_source_request_non_empty",
        ),
        sa.CheckConstraint(
            "length(btrim(provider)) > 0",
            name="codex_replay_references_provider_non_empty",
        ),
        sa.CheckConstraint(
            "length(btrim(upstream_model)) > 0",
            name="codex_replay_references_upstream_model_non_empty",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="codex_replay_references_expiry_after_creation",
        ),
        sa.CheckConstraint(
            "((item_kind = 'reasoning' and call_id_hmac is null and "
            "tool_namespace is null and tool_name is null) or "
            "(item_kind in ('function_call', 'custom_tool_call') and "
            "call_id_hmac is not null and tool_namespace is not null and tool_name is not null))",
            name="codex_replay_references_kind_shape",
        ),
        sa.CheckConstraint(
            "tool_namespace is null or "
            "(length(btrim(tool_namespace)) > 0 and length(tool_namespace) <= 256)",
            name="codex_replay_references_tool_namespace_bounded",
        ),
        sa.CheckConstraint(
            "tool_name is null or (length(btrim(tool_name)) > 0 and length(tool_name) <= 256)",
            name="codex_replay_references_tool_name_bounded",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name="fk_codex_replay_references_gateway_key_id_gateway_keys",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["model_routes.id"],
            name="fk_codex_replay_references_route_id_model_routes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usage_ledger_id"],
            ["usage_ledger.id"],
            name="fk_codex_replay_references_usage_ledger_id_usage_ledger",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "gateway_key_id",
            "item_kind",
            "item_id_hmac",
            name="uq_codex_replay_references_key_kind_item",
        ),
        sa.UniqueConstraint(
            "gateway_key_id",
            "item_kind",
            "call_id_hmac",
            name="uq_codex_replay_references_key_kind_call",
        ),
    )
    op.create_index(
        "ix_codex_replay_references_expires_at",
        "codex_replay_references",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_codex_replay_references_key_kind_call_expiry",
        "codex_replay_references",
        ["gateway_key_id", "item_kind", "call_id_hmac", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_codex_replay_references_key_kind_item_expiry",
        "codex_replay_references",
        ["gateway_key_id", "item_kind", "item_id_hmac", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_codex_replay_references_usage_ledger_id",
        "codex_replay_references",
        ["usage_ledger_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_codex_replay_references_usage_ledger_id",
        table_name="codex_replay_references",
    )
    op.drop_index(
        "ix_codex_replay_references_key_kind_item_expiry",
        table_name="codex_replay_references",
    )
    op.drop_index(
        "ix_codex_replay_references_key_kind_call_expiry",
        table_name="codex_replay_references",
    )
    op.drop_index(
        "ix_codex_replay_references_expires_at",
        table_name="codex_replay_references",
    )
    op.drop_table("codex_replay_references")
