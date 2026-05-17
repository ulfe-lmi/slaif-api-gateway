"""trusted calibration keys

Revision ID: 0008_trusted_calibration_keys
Revises: 0007_usage_profiles
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0008_trusted_calibration_keys"
down_revision = "0007_usage_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_keys",
        sa.Column(
            "key_purpose",
            sa.Text(),
            server_default=sa.text("'standard'"),
            nullable=False,
        ),
    )
    op.add_column(
        "gateway_keys",
        sa.Column(
            "capability_policy_mode",
            sa.Text(),
            server_default=sa.text("'standard'"),
            nullable=False,
        ),
    )
    op.add_column(
        "gateway_keys",
        sa.Column(
            "calibration_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "gateway_keys_key_purpose_allowed_values",
        "gateway_keys",
        "key_purpose in ('standard', 'trusted_calibration')",
    )
    op.create_check_constraint(
        "gateway_keys_capability_policy_mode_allowed_values",
        "gateway_keys",
        "capability_policy_mode in ('standard', 'trusted_calibration_discovery')",
    )
    op.create_check_constraint(
        "gateway_keys_purpose_policy_mode_pair",
        "gateway_keys",
        "((key_purpose = 'standard' and capability_policy_mode = 'standard') or "
        "(key_purpose = 'trusted_calibration' and "
        "capability_policy_mode = 'trusted_calibration_discovery'))",
    )
    op.create_check_constraint(
        "gateway_keys_trusted_calibration_request_limit_required",
        "gateway_keys",
        "key_purpose != 'trusted_calibration' or request_limit_total is not null",
    )
    op.create_index("ix_gateway_keys_key_purpose", "gateway_keys", ["key_purpose"], unique=False)
    op.create_index(
        "ix_gateway_keys_capability_policy_mode",
        "gateway_keys",
        ["capability_policy_mode"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gateway_keys_capability_policy_mode", table_name="gateway_keys")
    op.drop_index("ix_gateway_keys_key_purpose", table_name="gateway_keys")
    op.drop_constraint(
        "gateway_keys_trusted_calibration_request_limit_required",
        "gateway_keys",
        type_="check",
    )
    op.drop_constraint("gateway_keys_purpose_policy_mode_pair", "gateway_keys", type_="check")
    op.drop_constraint(
        "gateway_keys_capability_policy_mode_allowed_values",
        "gateway_keys",
        type_="check",
    )
    op.drop_constraint("gateway_keys_key_purpose_allowed_values", "gateway_keys", type_="check")
    op.drop_column("gateway_keys", "calibration_metadata")
    op.drop_column("gateway_keys", "capability_policy_mode")
    op.drop_column("gateway_keys", "key_purpose")
