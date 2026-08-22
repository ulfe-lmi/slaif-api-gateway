"""Add oidc_identities table for OIDC human identity linking.

Revision ID: 0017_oidc_identities
Revises: 0016_organization_team_project
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_oidc_identities"
down_revision = "0016_organization_team_project"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"),
        {"name": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    if not _table_exists("oidc_identities"):
        op.create_table(
            "oidc_identities",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False),
            sa.Column("issuer_url", sa.Text(), nullable=False),
            sa.Column("subject", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("issuer_url", "subject", name="uq_oidc_identities_issuer_subject"),
        )
        op.create_index("ix_oidc_identities_owner_id", "oidc_identities", ["owner_id"])
        op.create_index("ix_oidc_identities_email", "oidc_identities", ["email"])


def downgrade() -> None:
    op.drop_table("oidc_identities")
