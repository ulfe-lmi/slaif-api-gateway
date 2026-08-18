"""Allow HMAC-only opaque Codex compaction replay references.

Revision ID: 0014_codex_context_accounting_compaction
Revises: 0013_codex_replay_references
Create Date: 2026-08-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_codex_context_accounting_compaction"
down_revision = "0013_codex_replay_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "codex_replay_references_kind_shape",
        "codex_replay_references",
        type_="check",
    )
    op.drop_constraint(
        "codex_replay_references_item_kind_allowed_values",
        "codex_replay_references",
        type_="check",
    )
    op.create_check_constraint(
        "codex_replay_references_item_kind_allowed_values",
        "codex_replay_references",
        "item_kind in ('reasoning', 'function_call', 'custom_tool_call', 'compaction')",
    )
    op.create_check_constraint(
        "codex_replay_references_kind_shape",
        "codex_replay_references",
        "((item_kind in ('reasoning', 'compaction') and call_id_hmac is null and "
        "tool_namespace is null and tool_name is null) or "
        "(item_kind in ('function_call', 'custom_tool_call') and "
        "call_id_hmac is not null and tool_namespace is not null and tool_name is not null))",
    )


def downgrade() -> None:
    op.execute(sa.text("delete from codex_replay_references where item_kind = 'compaction'"))
    op.drop_constraint(
        "codex_replay_references_kind_shape",
        "codex_replay_references",
        type_="check",
    )
    op.drop_constraint(
        "codex_replay_references_item_kind_allowed_values",
        "codex_replay_references",
        type_="check",
    )
    op.create_check_constraint(
        "codex_replay_references_item_kind_allowed_values",
        "codex_replay_references",
        "item_kind in ('reasoning', 'function_call', 'custom_tool_call')",
    )
    op.create_check_constraint(
        "codex_replay_references_kind_shape",
        "codex_replay_references",
        "((item_kind = 'reasoning' and call_id_hmac is null and "
        "tool_namespace is null and tool_name is null) or "
        "(item_kind in ('function_call', 'custom_tool_call') and "
        "call_id_hmac is not null and tool_namespace is not null and tool_name is not null))",
    )
