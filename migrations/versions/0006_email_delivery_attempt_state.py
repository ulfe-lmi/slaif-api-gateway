"""email delivery attempt state

Revision ID: 0006_email_delivery_attempt_state
Revises: 0005_fix_gateway_key_prefix_default
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0006_email_delivery_attempt_state"
down_revision = "0005_fix_gateway_key_prefix_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_email_deliveries_email_deliveries_status_allowed_values"),
        "email_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_email_deliveries_email_deliveries_status_allowed_values"),
        "email_deliveries",
        "status in ('pending', 'sending', 'sent', 'failed', 'ambiguous', 'cancelled')",
    )


def downgrade() -> None:
    op.execute("UPDATE email_deliveries SET status = 'failed' WHERE status in ('sending', 'ambiguous')")
    op.drop_constraint(
        op.f("ck_email_deliveries_email_deliveries_status_allowed_values"),
        "email_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_email_deliveries_email_deliveries_status_allowed_values"),
        "email_deliveries",
        "status in ('pending', 'sent', 'failed', 'cancelled')",
    )
