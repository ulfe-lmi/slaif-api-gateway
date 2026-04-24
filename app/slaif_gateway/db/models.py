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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from slaif_gateway.db.base import Base


STATUS_VALUES_GATEWAY_KEYS = ("active", "suspended", "revoked")
ROLE_VALUES_ADMIN_USERS = ("viewer", "operator", "admin", "superadmin")
STATUS_VALUES_QUOTA_RESERVATIONS = ("pending", "finalized", "released", "expired")
STATUS_VALUES_USAGE_LEDGER_ACCOUNTING = (
    "pending",
    "finalized",
    "estimated",
    "failed",
    "interrupted",
    "released",
)
KIND_VALUES_PROVIDER_CONFIGS = ("openai_compatible",)
MATCH_TYPE_VALUES_MODEL_ROUTES = ("exact", "prefix", "glob")
PURPOSE_VALUES_ONE_TIME_SECRETS = ("gateway_key_email", "gateway_key_rotation_email")
STATUS_VALUES_ONE_TIME_SECRETS = ("pending", "consumed", "expired", "revoked")
STATUS_VALUES_EMAIL_DELIVERIES = ("pending", "sent", "failed", "cancelled")
STATUS_VALUES_BACKGROUND_JOBS = ("queued", "running", "succeeded", "failed", "cancelled")


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
    usage_ledger_rows: Mapped[list[UsageLedger]] = relationship(back_populates="institution")

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
    usage_ledger_rows: Mapped[list[UsageLedger]] = relationship(back_populates="cohort")

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
    usage_ledger_rows: Mapped[list[UsageLedger]] = relationship(back_populates="owner")
    one_time_secrets: Mapped[list[OneTimeSecret]] = relationship(back_populates="owner")
    email_deliveries: Mapped[list[EmailDelivery]] = relationship(back_populates="owner")

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
    background_jobs: Mapped[list[BackgroundJob]] = relationship(back_populates="created_by_admin_user")

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
    quota_reservations: Mapped[list[QuotaReservation]] = relationship(back_populates="gateway_key")
    usage_ledger_rows: Mapped[list[UsageLedger]] = relationship(back_populates="gateway_key")
    one_time_secrets: Mapped[list[OneTimeSecret]] = relationship(back_populates="gateway_key")
    email_deliveries: Mapped[list[EmailDelivery]] = relationship(back_populates="gateway_key")

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


class QuotaReservation(Base):
    __tablename__ = "quota_reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gateway_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gateway_keys.id", ondelete="RESTRICT"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    requested_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    reserved_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    reserved_requests: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    gateway_key: Mapped[GatewayKey] = relationship(back_populates="quota_reservations")
    usage_ledger_rows: Mapped[list[UsageLedger]] = relationship(back_populates="quota_reservation")

    __table_args__ = (
        CheckConstraint(
            f"status in {STATUS_VALUES_QUOTA_RESERVATIONS}",
            name="quota_reservations_status_allowed_values",
        ),
        CheckConstraint("reserved_cost_eur >= 0", name="quota_reservations_reserved_cost_eur_non_negative"),
        CheckConstraint("reserved_tokens >= 0", name="quota_reservations_reserved_tokens_non_negative"),
        CheckConstraint("reserved_requests >= 0", name="quota_reservations_reserved_requests_non_negative"),
        Index("ix_quota_reservations_gateway_key_id", "gateway_key_id"),
        Index("ix_quota_reservations_status_expires_at", "status", "expires_at"),
    )


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    client_request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    quota_reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quota_reservations.id", ondelete="SET NULL"), nullable=True
    )
    gateway_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gateway_keys.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="SET NULL"), nullable=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True
    )
    owner_email_snapshot: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    owner_name_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_surname_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    institution_name_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    cohort_name_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    http_method: Mapped[str] = mapped_column(Text, nullable=False, default="POST", server_default=text("'POST'"))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    requested_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    upstream_request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accounting_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default=text("'pending'")
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    cached_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    reasoning_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    estimated_cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    actual_cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    actual_cost_native: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    native_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_raw: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    response_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    quota_reservation: Mapped[QuotaReservation | None] = relationship(back_populates="usage_ledger_rows")
    gateway_key: Mapped[GatewayKey] = relationship(back_populates="usage_ledger_rows")
    owner: Mapped[Owner | None] = relationship(back_populates="usage_ledger_rows")
    institution: Mapped[Institution | None] = relationship(back_populates="usage_ledger_rows")
    cohort: Mapped[Cohort | None] = relationship(back_populates="usage_ledger_rows")

    __table_args__ = (
        CheckConstraint(
            f"accounting_status in {STATUS_VALUES_USAGE_LEDGER_ACCOUNTING}",
            name="usage_ledger_accounting_status_allowed_values",
        ),
        CheckConstraint("prompt_tokens >= 0", name="usage_ledger_prompt_tokens_non_negative"),
        CheckConstraint("completion_tokens >= 0", name="usage_ledger_completion_tokens_non_negative"),
        CheckConstraint("input_tokens >= 0", name="usage_ledger_input_tokens_non_negative"),
        CheckConstraint("output_tokens >= 0", name="usage_ledger_output_tokens_non_negative"),
        CheckConstraint("cached_tokens >= 0", name="usage_ledger_cached_tokens_non_negative"),
        CheckConstraint("reasoning_tokens >= 0", name="usage_ledger_reasoning_tokens_non_negative"),
        CheckConstraint("total_tokens >= 0", name="usage_ledger_total_tokens_non_negative"),
        CheckConstraint(
            "estimated_cost_eur is null or estimated_cost_eur >= 0",
            name="usage_ledger_estimated_cost_eur_non_negative",
        ),
        CheckConstraint(
            "actual_cost_eur is null or actual_cost_eur >= 0",
            name="usage_ledger_actual_cost_eur_non_negative",
        ),
        Index("ix_usage_ledger_gateway_key_id_created_at", "gateway_key_id", "created_at"),
        Index("ix_usage_ledger_owner_id_created_at", "owner_id", "created_at"),
        Index("ix_usage_ledger_institution_id_created_at", "institution_id", "created_at"),
        Index("ix_usage_ledger_cohort_id_created_at", "cohort_id", "created_at"),
        Index("ix_usage_ledger_provider_resolved_model", "provider", "resolved_model"),
        Index("ix_usage_ledger_endpoint_created_at", "endpoint", "created_at"),
        Index("ix_usage_ledger_accounting_status_created_at", "accounting_status", "created_at"),
    )


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="openai_compatible", server_default=text("'openai_compatible'")
    )
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_env_var: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300, server_default=text("300"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default=text("2"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            f"kind in {KIND_VALUES_PROVIDER_CONFIGS}",
            name="provider_configs_kind_allowed_values",
        ),
        Index("ix_provider_configs_enabled", "enabled"),
    )


class ModelRoute(Base):
    __tablename__ = "model_routes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requested_model: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(Text, nullable=False, default="exact", server_default=text("'exact'"))
    endpoint: Mapped[str] = mapped_column(
        Text, nullable=False, default="/v1/chat/completions", server_default=text("'/v1/chat/completions'")
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_model: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default=text("100"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    visible_in_models: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    capabilities: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            f"match_type in {MATCH_TYPE_VALUES_MODEL_ROUTES}",
            name="model_routes_match_type_allowed_values",
        ),
        Index("ix_model_routes_requested_model_enabled", "requested_model", "enabled"),
        Index("ix_model_routes_provider_enabled", "provider", "enabled"),
        Index("ix_model_routes_endpoint_enabled", "endpoint", "enabled"),
        Index("ix_model_routes_priority", "priority"),
    )


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_model: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(
        Text, nullable=False, default="/v1/chat/completions", server_default=text("'/v1/chat/completions'")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD", server_default=text("'USD'"))
    input_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    cached_input_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    output_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    reasoning_price_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    request_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    pricing_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "input_price_per_1m is null or input_price_per_1m >= 0",
            name="pricing_rules_input_price_per_1m_non_negative",
        ),
        CheckConstraint(
            "cached_input_price_per_1m is null or cached_input_price_per_1m >= 0",
            name="pricing_rules_cached_input_price_per_1m_non_negative",
        ),
        CheckConstraint(
            "output_price_per_1m is null or output_price_per_1m >= 0",
            name="pricing_rules_output_price_per_1m_non_negative",
        ),
        CheckConstraint(
            "reasoning_price_per_1m is null or reasoning_price_per_1m >= 0",
            name="pricing_rules_reasoning_price_per_1m_non_negative",
        ),
        CheckConstraint("request_price is null or request_price >= 0", name="pricing_rules_request_price_non_negative"),
        UniqueConstraint("provider", "upstream_model", "endpoint", "valid_from", name="uq_pricing_rules_identity"),
        Index("ix_pricing_rules_provider_upstream_model_endpoint_enabled", "provider", "upstream_model", "endpoint", "enabled"),
        Index("ix_pricing_rules_valid_from_valid_until", "valid_from", "valid_until"),
    )


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    base_currency: Mapped[str] = mapped_column(Text, nullable=False)
    quote_currency: Mapped[str] = mapped_column(Text, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("rate > 0", name="fx_rates_rate_positive"),
        UniqueConstraint("base_currency", "quote_currency", "valid_from", name="uq_fx_rates_pair_valid_from"),
        Index(
            "ix_fx_rates_base_quote_valid_from_valid_until",
            "base_currency",
            "quote_currency",
            "valid_from",
            "valid_until",
        ),
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


class OneTimeSecret(Base):
    __tablename__ = "one_time_secrets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="SET NULL"), nullable=True
    )
    gateway_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gateway_keys.id", ondelete="CASCADE"), nullable=True
    )
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    owner: Mapped[Owner | None] = relationship(back_populates="one_time_secrets")
    gateway_key: Mapped[GatewayKey | None] = relationship(back_populates="one_time_secrets")
    email_deliveries: Mapped[list[EmailDelivery]] = relationship(back_populates="one_time_secret")

    __table_args__ = (
        CheckConstraint(
            f"purpose in {PURPOSE_VALUES_ONE_TIME_SECRETS}",
            name="one_time_secrets_purpose_allowed_values",
        ),
        CheckConstraint(
            f"status in {STATUS_VALUES_ONE_TIME_SECRETS}",
            name="one_time_secrets_status_allowed_values",
        ),
        Index("ix_one_time_secrets_status_expires_at", "status", "expires_at"),
        Index("ix_one_time_secrets_gateway_key_id", "gateway_key_id"),
        Index("ix_one_time_secrets_expires_at", "expires_at"),
        Index("ix_one_time_secrets_consumed_at", "consumed_at"),
    )


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="SET NULL"), nullable=True
    )
    gateway_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gateway_keys.id", ondelete="SET NULL"), nullable=True
    )
    one_time_secret_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("one_time_secrets.id", ondelete="SET NULL"), nullable=True
    )
    recipient_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[Owner | None] = relationship(back_populates="email_deliveries")
    gateway_key: Mapped[GatewayKey | None] = relationship(back_populates="email_deliveries")
    one_time_secret: Mapped[OneTimeSecret | None] = relationship(back_populates="email_deliveries")

    __table_args__ = (
        CheckConstraint(
            f"status in {STATUS_VALUES_EMAIL_DELIVERIES}",
            name="email_deliveries_status_allowed_values",
        ),
        Index("ix_email_deliveries_owner_id", "owner_id"),
        Index("ix_email_deliveries_gateway_key_id", "gateway_key_id"),
        Index("ix_email_deliveries_status_created_at", "status", "created_at"),
        Index("ix_email_deliveries_one_time_secret_id", "one_time_secret_id"),
    )


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    celery_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued", server_default=text("'queued'"))
    created_by_admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    payload_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_admin_user: Mapped[AdminUser | None] = relationship(back_populates="background_jobs")

    __table_args__ = (
        CheckConstraint(
            f"status in {STATUS_VALUES_BACKGROUND_JOBS}",
            name="background_jobs_status_allowed_values",
        ),
        Index("ix_background_jobs_celery_task_id", "celery_task_id"),
        Index("ix_background_jobs_job_type_created_at", "job_type", "created_at"),
        Index("ix_background_jobs_status_created_at", "status", "created_at"),
        Index("ix_background_jobs_created_by_admin_user_id_created_at", "created_by_admin_user_id", "created_at"),
    )
