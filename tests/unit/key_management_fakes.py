from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.config import Settings
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.secrets import generate_secret_key


@dataclass
class FakeGatewayKeyRow:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    public_key_id: str = "public-test-id"
    key_prefix: str = "sk-slaif-"
    key_hint: str | None = "sk-slaif-public"
    token_hash: str = "a" * 64
    hash_algorithm: str = "hmac-sha256"
    hmac_key_version: int = 1
    owner_id: uuid.UUID = field(default_factory=uuid.uuid4)
    cohort_id: uuid.UUID | None = field(default_factory=uuid.uuid4)
    status: str = "active"
    valid_from: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=1))
    valid_until: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=30))
    cost_limit_eur: Decimal | None = Decimal("25.000000000")
    token_limit_total: int | None = 100_000
    request_limit_total: int | None = 1_000
    cost_used_eur: Decimal = Decimal("1.250000000")
    tokens_used_total: int = 100
    requests_used_total: int = 2
    cost_reserved_eur: Decimal = Decimal("0.500000000")
    tokens_reserved_total: int = 50
    requests_reserved_total: int = 1
    rate_limit_requests_per_minute: int | None = 60
    rate_limit_tokens_per_minute: int | None = 12_000
    max_concurrent_requests: int | None = 2
    metadata_json: dict[str, object] = field(default_factory=dict)
    allow_all_models: bool = False
    allowed_models: list[str] = field(default_factory=lambda: ["gpt-test-mini"])
    allow_all_endpoints: bool = False
    allowed_endpoints: list[str] = field(default_factory=lambda: ["/v1/chat/completions"])
    last_used_at: datetime | None = field(default_factory=lambda: datetime.now(UTC))
    last_quota_reset_at: datetime | None = None
    quota_reset_count: int = 0
    created_by_admin_user_id: uuid.UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=2))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=2))
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


@dataclass
class FakeOneTimeSecretRow:
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class FakeGatewayKeysRepository:
    def __init__(self, row: FakeGatewayKeyRow | None = None) -> None:
        self.rows: dict[uuid.UUID, FakeGatewayKeyRow] = {}
        if row is not None:
            self.rows[row.id] = row
        self.created_calls: list[dict[str, object]] = []
        self.status_calls: list[dict[str, object]] = []
        self.limit_calls: list[dict[str, object]] = []
        self.rate_limit_calls: list[dict[str, object]] = []
        self.validity_calls: list[dict[str, object]] = []
        self.reset_calls: list[dict[str, object]] = []
        self.commit_called = False

    async def get_gateway_key_for_update(self, gateway_key_id: uuid.UUID) -> FakeGatewayKeyRow | None:
        return self.rows.get(gateway_key_id)

    async def get_gateway_key_by_id(self, gateway_key_id: uuid.UUID) -> FakeGatewayKeyRow | None:
        return self.rows.get(gateway_key_id)

    async def create_gateway_key_record(self, **kwargs: object) -> FakeGatewayKeyRow:
        self.created_calls.append(kwargs)
        row = FakeGatewayKeyRow(
            public_key_id=str(kwargs["public_key_id"]),
            key_prefix=str(kwargs["key_prefix"]),
            key_hint=str(kwargs["key_hint"]) if kwargs.get("key_hint") is not None else None,
            token_hash=str(kwargs["token_hash"]),
            hmac_key_version=int(kwargs["hmac_key_version"]),
            owner_id=kwargs["owner_id"],
            cohort_id=kwargs.get("cohort_id"),
            status=str(kwargs["status"]),
            valid_from=kwargs["valid_from"],
            valid_until=kwargs["valid_until"],
            cost_limit_eur=kwargs.get("cost_limit_eur"),
            token_limit_total=kwargs.get("token_limit_total"),
            request_limit_total=kwargs.get("request_limit_total"),
            allow_all_models=bool(kwargs.get("allow_all_models", False)),
            allowed_models=list(kwargs.get("allowed_models") or []),
            allow_all_endpoints=bool(kwargs.get("allow_all_endpoints", False)),
            allowed_endpoints=list(kwargs.get("allowed_endpoints") or []),
            rate_limit_requests_per_minute=kwargs.get("rate_limit_requests_per_minute"),
            rate_limit_tokens_per_minute=kwargs.get("rate_limit_tokens_per_minute"),
            max_concurrent_requests=kwargs.get("max_concurrent_requests"),
            metadata_json=dict(kwargs.get("metadata_json") or {}),
            created_by_admin_user_id=kwargs.get("created_by_admin_user_id"),
        )
        self.rows[row.id] = row
        return row

    async def update_gateway_key_status(
        self,
        gateway_key_id: uuid.UUID,
        *,
        status: str,
        revoked_at: datetime | None = None,
        revoked_reason: str | None = None,
    ) -> bool:
        self.status_calls.append(
            {
                "gateway_key_id": gateway_key_id,
                "status": status,
                "revoked_at": revoked_at,
                "revoked_reason": revoked_reason,
            }
        )
        row = self.rows.get(gateway_key_id)
        if row is None:
            return False
        row.status = status
        row.revoked_at = revoked_at
        row.revoked_reason = revoked_reason
        return True

    async def update_gateway_key_rate_limit_policy(
        self,
        gateway_key_id: uuid.UUID,
        *,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
        max_concurrent_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> bool:
        self.rate_limit_calls.append(
            {
                "gateway_key_id": gateway_key_id,
                "requests_per_minute": requests_per_minute,
                "tokens_per_minute": tokens_per_minute,
                "max_concurrent_requests": max_concurrent_requests,
                "window_seconds": window_seconds,
            }
        )
        row = self.rows.get(gateway_key_id)
        if row is None:
            return False
        row.rate_limit_requests_per_minute = requests_per_minute
        row.rate_limit_tokens_per_minute = tokens_per_minute
        row.max_concurrent_requests = max_concurrent_requests
        metadata = dict(row.metadata_json or {})
        if window_seconds is None:
            metadata.pop("rate_limit_policy", None)
        else:
            metadata["rate_limit_policy"] = {"window_seconds": window_seconds}
        row.metadata_json = metadata
        return True

    async def update_gateway_key_limits(
        self,
        gateway_key_id: uuid.UUID,
        *,
        cost_limit_eur: Decimal | None = None,
        token_limit_total: int | None = None,
        request_limit_total: int | None = None,
    ) -> bool:
        self.limit_calls.append(
            {
                "gateway_key_id": gateway_key_id,
                "cost_limit_eur": cost_limit_eur,
                "token_limit_total": token_limit_total,
                "request_limit_total": request_limit_total,
            }
        )
        row = self.rows.get(gateway_key_id)
        if row is None:
            return False
        row.cost_limit_eur = cost_limit_eur
        row.token_limit_total = token_limit_total
        row.request_limit_total = request_limit_total
        return True

    async def update_gateway_key_validity(
        self,
        gateway_key_id: uuid.UUID,
        *,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> bool:
        self.validity_calls.append(
            {
                "gateway_key_id": gateway_key_id,
                "valid_from": valid_from,
                "valid_until": valid_until,
            }
        )
        row = self.rows.get(gateway_key_id)
        if row is None:
            return False
        if valid_from is not None:
            row.valid_from = valid_from
        if valid_until is not None:
            row.valid_until = valid_until
        return True

    async def reset_gateway_key_usage_counters(
        self,
        gateway_key: FakeGatewayKeyRow,
        *,
        reset_used_counters: bool = True,
        reset_reserved_counters: bool = False,
        reset_at: datetime,
    ) -> FakeGatewayKeyRow:
        self.reset_calls.append(
            {
                "gateway_key_id": gateway_key.id,
                "reset_used_counters": reset_used_counters,
                "reset_reserved_counters": reset_reserved_counters,
                "reset_at": reset_at,
            }
        )
        if reset_used_counters:
            gateway_key.cost_used_eur = Decimal("0")
            gateway_key.tokens_used_total = 0
            gateway_key.requests_used_total = 0
            gateway_key.last_used_at = None
        if reset_reserved_counters:
            gateway_key.cost_reserved_eur = Decimal("0")
            gateway_key.tokens_reserved_total = 0
            gateway_key.requests_reserved_total = 0
        gateway_key.last_quota_reset_at = reset_at
        gateway_key.quota_reset_count += 1
        return gateway_key


class FakeOneTimeSecretsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.rows: list[FakeOneTimeSecretRow] = []

    async def create_one_time_secret(self, **kwargs: object) -> FakeOneTimeSecretRow:
        self.calls.append(kwargs)
        row = FakeOneTimeSecretRow()
        self.rows.append(row)
        return row


class FakeAuditRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def make_key_service(
    row: FakeGatewayKeyRow | None = None,
) -> tuple[KeyService, FakeGatewayKeysRepository, FakeOneTimeSecretsRepository, FakeAuditRepository, str]:
    encryption_key = generate_secret_key()
    settings = Settings(
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=encryption_key,
        ONE_TIME_SECRET_KEY_VERSION="v1",
        GATEWAY_KEY_PREFIX="sk-slaif-",
    )
    keys_repo = FakeGatewayKeysRepository(row)
    one_time_repo = FakeOneTimeSecretsRepository()
    audit_repo = FakeAuditRepository()
    service = KeyService(
        settings=settings,
        gateway_keys_repository=keys_repo,
        one_time_secrets_repository=one_time_repo,
        audit_repository=audit_repo,
    )
    return service, keys_repo, one_time_repo, audit_repo, encryption_key
