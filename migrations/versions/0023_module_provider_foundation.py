"""Allow statically registered native module provider configurations.

Revision ID: 0023_module_provider_foundation
Revises: 0022_provider_governance
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_module_provider_foundation"
down_revision = "0022_provider_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "provider_configs_kind_allowed_values",
        "provider_configs",
        type_="check",
    )
    op.create_check_constraint(
        "provider_configs_kind_allowed_values",
        "provider_configs",
        "kind in ('openai_compatible', 'module')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "provider_configs_kind_allowed_values",
        "provider_configs",
        type_="check",
    )
    op.create_check_constraint(
        "provider_configs_kind_allowed_values",
        "provider_configs",
        "kind in ('openai_compatible')",
    )
