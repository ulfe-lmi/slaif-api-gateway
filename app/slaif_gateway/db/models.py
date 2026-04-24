"""Foundational SQLAlchemy ORM models for SLAIF gateway persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from slaif_gateway.db.base import Base


STATUS_VALUES_GATEWAY_KEYS = ("active", "suspended", "revoked")
ROLE_VALUES_ADMIN_USERS = ("viewer", "operator", "admin", "superadmin")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    owners: Mapped[list[Owner]] = relationship(back_populates="institution")

    __table_args__ = (
        Index("uq_institutions_name_lower", func.lower(name), unique=True),
    )


class Cohort(Base):
    __tablename__ = "cohorts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    gateway_keys: Mapped[list[GatewayKey]] = relationship(back_populates="cohort")

    __table_args__ = (Index("ix_cohorts_starts_at_ends_at", "starts_at", "ends_at"),)


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    surname: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    institution: Mapped[Institution | None] = relationship(back_populates="owners")
    gateway_keys: Mapped[list[GatewayKey]] = relationship(back_populates="owner")

    __table_args__ = (Index("ix_owners_institution_id", "institution_id"), Index("ix_owners_is_active", "is_active"))


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="admin", server_default=text("'admin'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    sessions: Mapped[list[AdminSession]] = relationship(back_populates="admin_user")
    gateway_keys_created: Mapped[list[GatewayKey]] = relationship(back_populates="created_by_admin_user")

    __table_args__ = (
        CheckConstraint(
            f"role in {ROLE_VALUES_ADMIN_USERS}",
            name="admin_users_role_allowed_values",
        ),
        Index("ix_admin_users_is_active", "is_active"),
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    session_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    admin_user: Mapped[AdminUser] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_admin_sessions_admin_user_id", "admin_user_id"),
        Index("ix_admin_sessions_expires_at", "expires_at"),
        Index("ix_admin_sessions_revoked_at", "revoked_at"),
    )


class GatewayKey(Base):
    __tablename__ = "gateway_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_key_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False, default="sk-slaif", server_default=text("'sk-slaif'"))
    key_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hash_algorithm: Mapped[str] = mapped_column(
        Text, nullable=False, default="hmac-sha256", server_default=text("'hmac-sha256'")
    )
    hmac_key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default=text("'active'"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cost_limit_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    token_limit_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_limit_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    cost_used_eur: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    tokens_used_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    requests_used_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))

    cost_reserved_eur: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    tokens_reserved_total: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    requests_reserved_total: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )

    rate_limit_requests_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_tokens_per_minute: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_concurrent_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)

    allow_all_models: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    allowed_models: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    allow_all_endpoints: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    allowed_endpoints: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_quota_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quota_reset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    created_by_admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped[Owner] = relationship(back_populates="gateway_keys")
    cohort: Mapped[Cohort | None] = relationship(back_populates="gateway_keys")
    created_by_admin_user: Mapped[AdminUser | None] = relationship(back_populates="gateway_keys_created")

    __table_args__ = (
        CheckConstraint(
            f"status in {STATUS_VALUES_GATEWAY_KEYS}",
            name="gateway_keys_status_allowed_values",
        ),
        CheckConstraint("cost_used_eur >= 0", name="gateway_keys_cost_used_eur_non_negative"),
        CheckConstraint("cost_reserved_eur >= 0", name="gateway_keys_cost_reserved_eur_non_negative"),
        CheckConstraint("tokens_used_total >= 0", name="gateway_keys_tokens_used_total_non_negative"),
        CheckConstraint(
            "tokens_reserved_total >= 0",
            name="gateway_keys_tokens_reserved_total_non_negative",
        ),
        CheckConstraint(
            "requests_used_total >= 0",
            name="gateway_keys_requests_used_total_non_negative",
        ),
        CheckConstraint(
            "requests_reserved_total >= 0",
            name="gateway_keys_requests_reserved_total_non_negative",
        ),
        CheckConstraint("valid_until > valid_from", name="gateway_keys_valid_until_after_valid_from"),
        Index("ix_gateway_keys_owner_id", "owner_id"),
        Index("ix_gateway_keys_cohort_id", "cohort_id"),
        Index("ix_gateway_keys_status", "status"),
        Index("ix_gateway_keys_valid_until", "valid_until"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    old_values: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    admin_user: Mapped[AdminUser | None] = relationship()

    __table_args__ = (
        Index("ix_audit_log_admin_user_id_created_at", "admin_user_id", "created_at"),
        Index("ix_audit_log_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_log_action_created_at", "action", "created_at"),
        Index("ix_audit_log_request_id", "request_id"),
    )
