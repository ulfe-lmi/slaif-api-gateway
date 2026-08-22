"""Add service account fields to gateway_keys.

Revision ID: 0019_service_accounts
Revises: 0018_admin_roles
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0019_service_accounts"
down_revision = "0018_admin_roles"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table_name, "c": column_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    if not _column_exists("gateway_keys", "service_owner_id"):
        op.add_column("gateway_keys", sa.Column("service_owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("owners.id", ondelete="SET NULL"), nullable=True))
    if not _column_exists("gateway_keys", "service_name"):
        op.add_column("gateway_keys", sa.Column("service_name", sa.Text(), nullable=True))
    if not _column_exists("gateway_keys", "rotated_at"):
        op.add_column("gateway_keys", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("gateway_keys", "max_validity_days"):
        op.add_column("gateway_keys", sa.Column("max_validity_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("gateway_keys", "max_validity_days")
    op.drop_column("gateway_keys", "rotated_at")
    op.drop_column("gateway_keys", "service_name")
    op.drop_column("gateway_keys", "service_owner_id")
