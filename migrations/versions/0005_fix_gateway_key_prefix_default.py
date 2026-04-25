"""fix gateway key prefix default

Revision ID: 0005_fix_gateway_key_prefix_default
Revises: 0004_email_secrets_and_background_jobs
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_fix_gateway_key_prefix_default"
down_revision = "0004_email_secrets_and_background_jobs"
branch_labels = None
depends_on = None



def upgrade() -> None:
    op.alter_column(
        "gateway_keys",
        "key_prefix",
        existing_type=sa.Text(),
        server_default=sa.text("'sk-slaif-'"),
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE gateway_keys SET key_prefix = 'sk-slaif-' WHERE key_prefix = 'sk-slaif'"
        )
    )



def downgrade() -> None:
    op.alter_column(
        "gateway_keys",
        "key_prefix",
        existing_type=sa.Text(),
        server_default=sa.text("'sk-slaif'"),
        existing_nullable=False,
    )
