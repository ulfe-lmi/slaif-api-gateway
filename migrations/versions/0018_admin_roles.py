"""Add role column to admin_users for RBAC.

Revision ID: 0018_admin_roles
Revises: 0017_oidc_identities
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_admin_roles"
down_revision = "0017_oidc_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='admin_users' AND column_name='role'")
    )
    if not result.scalar():
        op.add_column(
            "admin_users",
            sa.Column("role", sa.Text(), nullable=False, server_default="viewer"),
        )
    result = conn.execute(
        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='admin_users' AND column_name='mfa_secret'")
    )
    if not result.scalar():
        op.add_column("admin_users", sa.Column("mfa_secret", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("admin_users", "mfa_secret")
    op.drop_column("admin_users", "role")
