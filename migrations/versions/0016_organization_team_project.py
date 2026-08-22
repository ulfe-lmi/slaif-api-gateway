"""Add organizations, teams, projects, and team_members tables.

Revision ID: 0016_organization_team_project
Revises: 0015_external_tool_exclusive_fence
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_organization_team_project"
down_revision = "0015_external_tool_exclusive_fence"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"),
        {"name": table_name},
    )
    return result.scalar()


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = :name)"),
        {"name": index_name},
    )
    return result.scalar()


def upgrade() -> None:
    if not _table_exists("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False, unique=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        if not _index_exists("uq_organizations_slug"):
            op.create_index("uq_organizations_slug", "organizations", ["slug"], unique=True)

    if not _table_exists("teams"):
        op.create_table(
            "teams",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        if not _index_exists("ix_teams_organization_id"):
            op.create_index("ix_teams_organization_id", "teams", ["organization_id"])
        if not _index_exists("uq_teams_org_slug"):
            op.create_index("uq_teams_org_slug", "teams", ["organization_id", "slug"], unique=True)

    if not _table_exists("projects"):
        op.create_table(
            "projects",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        if not _index_exists("ix_projects_team_id"):
            op.create_index("ix_projects_team_id", "projects", ["team_id"])
        if not _index_exists("uq_projects_team_slug"):
            op.create_index("uq_projects_team_slug", "projects", ["team_id", "slug"], unique=True)

    if not _table_exists("team_members"):
        op.create_table(
            "team_members",
            sa.Column("team_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("owners.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("role", sa.Text(), nullable=False, server_default="member"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("role IN ('member', 'lead', 'admin')", name="ck_team_members_role"),
        )
        if not _index_exists("ix_team_members_owner_id"):
            op.create_index("ix_team_members_owner_id", "team_members", ["owner_id"])

    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='institutions' AND column_name='organization_id'"))
    if not result.scalar():
        op.add_column("institutions", sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True))
    result = conn.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='cohorts' AND column_name='project_id'"))
    if not result.scalar():
        op.add_column("cohorts", sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("cohorts", "project_id")
    op.drop_column("institutions", "organization_id")
    op.drop_table("team_members")
    op.drop_table("projects")
    op.drop_table("teams")
    op.drop_table("organizations")
