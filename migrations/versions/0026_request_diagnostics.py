"""Bounded content-free request-failure diagnostics table.

Revision ID: 0026_request_diagnostics
Revises: 0025_catalog_refresh_applications
Create Date: 2026-10-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0026_request_diagnostics"
down_revision = "0025_catalog_refresh_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_diagnostics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_request_id", sa.String(length=128), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=True),
        sa.Column("client_id_unavailable_reason", sa.String(length=32), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("endpoint_template", sa.String(length=256), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("stream_outcome", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_param", sa.String(length=64), nullable=True),
        sa.Column(
            "positions",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "limits",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("gateway_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("route_pattern", sa.String(length=128), nullable=True),
        sa.Column("deployment_revision", sa.String(length=128), nullable=True),
        sa.Column("estimated_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_allowance_tokens", sa.BigInteger(), nullable=True),
        sa.Column("context_window_tokens", sa.BigInteger(), nullable=True),
        sa.Column("replay_error_code", sa.String(length=64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "stream_outcome in ('http_rejection', 'stream_failure', 'cancelled')",
            name="request_diagnostics_stream_outcome_allowed",
        ),
        sa.CheckConstraint(
            "client_id_unavailable_reason in ('absent', 'unsafe', 'secret_alias')",
            name="request_diagnostics_client_id_reason_allowed",
        ),
        sa.CheckConstraint(
            "positions is null or (jsonb_typeof(positions) = 'object' "
            "and COALESCE(octet_length(positions::text), 0) <= 512)",
            name="request_diagnostics_positions_bounded",
        ),
        sa.CheckConstraint(
            "COALESCE(octet_length(positions::text), 0) "
            "+ COALESCE(octet_length(counts::text), 0) "
            "+ COALESCE(octet_length(limits::text), 0) <= 8192",
            name="request_diagnostics_facts_payload_8kib",
        ),
        sa.UniqueConstraint(
            "gateway_request_id", name="uq_request_diagnostics_gateway_request_id"
        ),
    )
    op.create_index(
        "ix_request_diagnostics_client_request_id",
        "request_diagnostics",
        ["client_request_id"],
    )
    op.create_index(
        "ix_request_diagnostics_occurred_at",
        "request_diagnostics",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_request_diagnostics_gateway_request_id",
        table_name="request_diagnostics",
        type_="unique",
    )
    op.drop_index("ix_request_diagnostics_occurred_at", table_name="request_diagnostics")
    op.drop_index("ix_request_diagnostics_client_request_id", table_name="request_diagnostics")
    op.drop_table("request_diagnostics")
