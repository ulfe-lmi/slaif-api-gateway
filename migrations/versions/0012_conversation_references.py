"""conversation references

Revision ID: 0012_conversation_references
Revises: 0011_response_references
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0012_conversation_references"
down_revision = "0011_response_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_conversation_id", sa.Text(), nullable=False),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("provider_request_id", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('active', 'deleted')",
            name="conversation_references_status_allowed_values",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["cohorts.id"],
            name="fk_conversation_references_cohort_id_cohorts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name="fk_conversation_references_gateway_key_id_gateway_keys",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name="fk_conversation_references_institution_id_institutions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["owners.id"],
            name="fk_conversation_references_owner_id_owners",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["model_routes.id"],
            name="fk_conversation_references_route_id_model_routes",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_conversation_id",
            name="uq_conversation_references_provider_conversation",
        ),
    )
    op.create_index(
        "ix_conversation_references_created_at",
        "conversation_references",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_references_gateway_key_id_status",
        "conversation_references",
        ["gateway_key_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_references_provider_conversation_id",
        "conversation_references",
        ["provider", "provider_conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_references_route_id",
        "conversation_references",
        ["route_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_references_route_id", table_name="conversation_references")
    op.drop_index(
        "ix_conversation_references_provider_conversation_id",
        table_name="conversation_references",
    )
    op.drop_index(
        "ix_conversation_references_gateway_key_id_status",
        table_name="conversation_references",
    )
    op.drop_index("ix_conversation_references_created_at", table_name="conversation_references")
    op.drop_table("conversation_references")
