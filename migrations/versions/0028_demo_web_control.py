# OAP Work Order 224-a: durable least-privilege demo control handoff for
# one fresh, disposable, identity-masked snapshot per successful demo login.
#
# Extends the EXISTING ``demo_control`` PostgreSQL schema (created by
# 0027) with two purpose-built control tables:
#
# * ``demo_snapshot_requests`` - one durable, finite-state record per
#   requested demo snapshot copy. Binds a fresh UUID to the fake-admin
#   account UUID and its credential_generation, creation/claim-deadline/
#   expiry times, a small reviewed state vocabulary, a safe finite failure
#   code, and - ONLY at the independently verified handoff - the exact
#   worker job identity (closed ``snap-<32 hex>`` grammar) and the exact
#   copy locator (closed ``demo_snap_<20 hex>`` target-database name).
#   The copy locator is worker-owned and published no earlier than
#   verification; unique on both job and copy identities so two requests
#   can never bind one copy. It is a name, never a path or DSN. It NEVER
#   stores a password, bearer, provider secret, raw dump path/body, or
#   arbitrary error text.
# * ``demo_web_sessions`` - one row per demo browser session. Stores ONLY
#   the SHA-256 hash of a cryptographically random opaque browser token,
#   the account/generation, exactly one verified request/copy binding, and
#   creation/expiry/revocation times. A session must never be issuable for
#   a pending, failed, expired, wrong-account, wrong-generation, or reused
#   copy (enforced by the application state machine plus the partial
#   unique index on active sessions per request).
#
# The migration creates NO production roles and grants NOTHING, exactly as
# 0027 does: explicit least-privilege grants for the future demo web role
# and privileged snapshot worker role are applied only after those roles
# exist (objective 224-b), against the reviewed grant matrix defined in
# ``app/slaif_gateway/services/demo_web_control.py`` and documented in
# ``docs/demo-admin.md``. No business table is touched; the tables are NOT
# in ``public``, so 221's ``pg_dump --schema=public`` still excludes them.
#
# Migration head after this revision: 0028_demo_web_control (37 tables).

"""Demo control handoff: snapshot requests and web sessions.

Revision ID: 0028_demo_web_control
Revises: 0027_demo_admin_accounts
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0028_demo_web_control"
down_revision = "0027_demo_admin_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_snapshot_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "credential_generation",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        # DB default: the future web role's column-limited INSERT cannot
        # name the state column at all, so every web-created row starts
        # 'pending'; only the worker role may move the state.
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        # Safe finite failure code only; never arbitrary error text.
        sa.Column("failure_code", sa.Text(), nullable=True),
        # Exact worker job identity (221 SnapshotManifest.job_id grammar:
        # 'snap-' + 32 lowercase hex). Set by the worker ONLY at the
        # verified handoff; null until then.
        sa.Column("worker_job_id", sa.Text(), nullable=True),
        # Exact copy locator: the 221 randomized target database name
        # ('demo_snap_' + 20 lowercase hex), independently randomized and
        # not derivable from the job id. Worker-owned; published only at
        # the verified handoff. A name, never a path or DSN.
        sa.Column("worker_target_db", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["demo_control.fake_admin_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state in ('pending', 'claimed', 'verified_unpublished', "
            "'failed', 'cleanup_pending', 'cleaned')",
            name="demo_snapshot_requests_state_allowed",
        ),
        sa.CheckConstraint(
            "failure_code is null or failure_code in ('claim_expired', "
            "'late_completion', 'worker_failed', 'verification_failed', "
            "'copy_mismatch', 'state_conflict', 'internal_error')",
            name="demo_snapshot_requests_failure_code_allowed",
        ),
        sa.CheckConstraint(
            "credential_generation >= 0",
            name="demo_snapshot_requests_generation_nonnegative",
        ),
        sa.CheckConstraint(
            "deadline_at > created_at",
            name="demo_snapshot_requests_deadline_after_created",
        ),
        sa.CheckConstraint(
            "expires_at > deadline_at",
            name="demo_snapshot_requests_expires_after_deadline",
        ),
        sa.CheckConstraint(
            "worker_job_id is null or worker_job_id ~ '^snap-[0-9a-f]{32}$'",
            name="demo_snapshot_requests_worker_job_id_shape",
        ),
        sa.CheckConstraint(
            "worker_target_db is null or worker_target_db ~ '^demo_snap_[0-9a-f]{20}$'",
            name="demo_snapshot_requests_worker_target_db_shape",
        ),
        schema="demo_control",
    )
    op.create_index(
        "ix_demo_snapshot_requests_account_created",
        "demo_snapshot_requests",
        ["account_id", "created_at"],
        schema="demo_control",
    )
    op.create_index(
        "ix_demo_snapshot_requests_state_deadline",
        "demo_snapshot_requests",
        ["state", "deadline_at"],
        schema="demo_control",
    )
    # Two requests can never bind the same copy: the exact job identity
    # and the exact copy locator are each unique across all requests
    # (partial: null before the verified handoff).
    op.create_index(
        "uq_demo_snapshot_requests_worker_job_id",
        "demo_snapshot_requests",
        ["worker_job_id"],
        unique=True,
        postgresql_where=sa.text("worker_job_id IS NOT NULL"),
        schema="demo_control",
    )
    op.create_index(
        "uq_demo_snapshot_requests_worker_target_db",
        "demo_snapshot_requests",
        ["worker_target_db"],
        unique=True,
        postgresql_where=sa.text("worker_target_db IS NOT NULL"),
        schema="demo_control",
    )
    op.create_table(
        "demo_web_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # SHA-256 hex digest of the opaque random browser token; the raw
        # token is never persisted, logged, or echoed.
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "credential_generation",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        # Exactly one verified request/copy binding per session.
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["demo_control.fake_admin_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["demo_control.demo_snapshot_requests.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="demo_web_sessions_token_hash_shape",
        ),
        sa.CheckConstraint(
            "credential_generation >= 0",
            name="demo_web_sessions_generation_nonnegative",
        ),
        sa.CheckConstraint(
            "expires_at >= created_at",
            name="demo_web_sessions_expires_after_created",
        ),
        schema="demo_control",
    )
    op.create_index(
        "ix_demo_web_sessions_token_hash",
        "demo_web_sessions",
        ["token_hash"],
        unique=True,
        schema="demo_control",
    )
    # At most ONE live (non-revoked) session per verified copy: a reused
    # copy can never carry a second concurrent session.
    op.create_index(
        "uq_demo_web_sessions_one_active_per_request",
        "demo_web_sessions",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        schema="demo_control",
    )
    op.create_index(
        "ix_demo_web_sessions_account_created",
        "demo_web_sessions",
        ["account_id", "created_at"],
        schema="demo_control",
    )


def downgrade() -> None:
    # 0028 owns ONLY these two tables; the demo_control schema itself
    # belongs to 0027 and is dropped there.
    op.drop_index(
        "uq_demo_snapshot_requests_worker_target_db",
        table_name="demo_snapshot_requests",
        schema="demo_control",
    )
    op.drop_index(
        "uq_demo_snapshot_requests_worker_job_id",
        table_name="demo_snapshot_requests",
        schema="demo_control",
    )
    op.drop_index(
        "ix_demo_web_sessions_account_created",
        table_name="demo_web_sessions",
        schema="demo_control",
    )
    op.drop_index(
        "uq_demo_web_sessions_one_active_per_request",
        table_name="demo_web_sessions",
        schema="demo_control",
    )
    op.drop_index(
        "ix_demo_web_sessions_token_hash",
        table_name="demo_web_sessions",
        schema="demo_control",
    )
    op.drop_table("demo_web_sessions", schema="demo_control")
    op.drop_index(
        "ix_demo_snapshot_requests_state_deadline",
        table_name="demo_snapshot_requests",
        schema="demo_control",
    )
    op.drop_index(
        "ix_demo_snapshot_requests_account_created",
        table_name="demo_snapshot_requests",
        schema="demo_control",
    )
    op.drop_table("demo_snapshot_requests", schema="demo_control")
