"""response references

Revision ID: 0011_response_references
Revises: 0010_gateway_key_template_provenance
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0011_response_references"
down_revision = "0010_gateway_key_template_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "response_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_response_id", sa.Text(), nullable=False),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("requested_model", sa.Text(), nullable=True),
        sa.Column("upstream_model", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("provider_request_id", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            name="response_references_status_allowed_values",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["cohorts.id"],
            name="fk_response_references_cohort_id_cohorts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_key_id"],
            ["gateway_keys.id"],
            name="fk_response_references_gateway_key_id_gateway_keys",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name="fk_response_references_institution_id_institutions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["owners.id"],
            name="fk_response_references_owner_id_owners",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["model_routes.id"],
            name="fk_response_references_route_id_model_routes",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_response_id",
            name="uq_response_references_provider_response",
        ),
    )
    op.create_index("ix_response_references_created_at", "response_references", ["created_at"], unique=False)
    op.create_index("ix_response_references_expires_at", "response_references", ["expires_at"], unique=False)
    op.create_index(
        "ix_response_references_gateway_key_id_status",
        "response_references",
        ["gateway_key_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_response_references_provider_response_id",
        "response_references",
        ["provider", "provider_response_id"],
        unique=False,
    )
    op.create_index("ix_response_references_route_id", "response_references", ["route_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_response_references_route_id", table_name="response_references")
    op.drop_index("ix_response_references_provider_response_id", table_name="response_references")
    op.drop_index("ix_response_references_gateway_key_id_status", table_name="response_references")
    op.drop_index("ix_response_references_expires_at", table_name="response_references")
    op.drop_index("ix_response_references_created_at", table_name="response_references")
    op.drop_table("response_references")
