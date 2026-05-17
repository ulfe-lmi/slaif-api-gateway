"""gateway key template provenance

Revision ID: 0010_gateway_key_template_provenance
Revises: 0009_key_templates
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0010_gateway_key_template_provenance"
down_revision = "0009_key_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_keys",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "gateway_keys",
        sa.Column("template_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_gateway_keys_template_id_key_templates",
        "gateway_keys",
        "key_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_gateway_keys_template_revision_id_key_template_revisions",
        "gateway_keys",
        "key_template_revisions",
        ["template_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_gateway_keys_template_id", "gateway_keys", ["template_id"], unique=False)
    op.create_index(
        "ix_gateway_keys_template_revision_id",
        "gateway_keys",
        ["template_revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gateway_keys_template_revision_id", table_name="gateway_keys")
    op.drop_index("ix_gateway_keys_template_id", table_name="gateway_keys")
    op.drop_constraint(
        "fk_gateway_keys_template_revision_id_key_template_revisions",
        "gateway_keys",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_gateway_keys_template_id_key_templates",
        "gateway_keys",
        type_="foreignkey",
    )
    op.drop_column("gateway_keys", "template_revision_id")
    op.drop_column("gateway_keys", "template_id")
