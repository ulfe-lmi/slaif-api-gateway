import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.services.admin_key_dashboard import (
    AdminKeyDashboardService,
    AdminKeyNotFoundError,
    compute_key_display_status,
)


@dataclass
class _Owner:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Ada"
    surname: str = "Lovelace"
    email: str = "ada@example.org"
    institution: object | None = None


@dataclass
class _Institution:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "SLAIF University"


@dataclass
class _Cohort:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Spring Workshop"


@dataclass
class _GatewayKey:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    public_key_id: str = "public-id"
    key_prefix: str = "sk-slaif-"
    key_hint: str | None = "sk-slaif-public"
    token_hash: str = "token_hash_must_not_escape"
    owner_id: uuid.UUID = field(default_factory=uuid.uuid4)
    owner: _Owner | None = None
    cohort_id: uuid.UUID | None = None
    cohort: _Cohort | None = None
    status: str = "active"
    valid_from: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=1))
    valid_until: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=1))
    cost_limit_eur: Decimal | None = Decimal("10.000000000")
    token_limit_total: int | None = 1000
    request_limit_total: int | None = 100
    cost_used_eur: Decimal = Decimal("1.000000000")
    tokens_used_total: int = 10
    requests_used_total: int = 2
    cost_reserved_eur: Decimal = Decimal("0.100000000")
    tokens_reserved_total: int = 5
    requests_reserved_total: int = 1
    allow_all_models: bool = False
    allowed_models: list[str] = field(default_factory=lambda: ["gpt-test"])
    allow_all_endpoints: bool = False
    allowed_endpoints: list[str] = field(default_factory=lambda: ["/v1/chat/completions"])
    metadata_json: dict[str, object] = field(
        default_factory=lambda: {
            "allowed_providers": ["openai"],
            "rate_limit_policy": {"window_seconds": 60},
        }
    )
    rate_limit_requests_per_minute: int | None = 30
    rate_limit_tokens_per_minute: int | None = 1000
    max_concurrent_requests: int | None = 2
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=2))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=1))
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    created_by_admin_user_id: uuid.UUID | None = None
    last_used_at: datetime | None = None
    last_quota_reset_at: datetime | None = None
    quota_reset_count: int = 0


class _Repo:
    def __init__(self, row: _GatewayKey | None) -> None:
        self.row = row
        self.list_calls: list[dict[str, object]] = []

    async def list_keys_for_admin(self, **kwargs):
        self.list_calls.append(kwargs)
        return [self.row] if self.row is not None else []

    async def get_key_for_admin_detail(self, gateway_key_id: uuid.UUID):
        if self.row is not None and self.row.id == gateway_key_id:
            return self.row
        return None


def _row() -> _GatewayKey:
    institution = _Institution()
    owner = _Owner(institution=institution)
    cohort = _Cohort()
    return _GatewayKey(owner_id=owner.id, owner=owner, cohort_id=cohort.id, cohort=cohort)


@pytest.mark.asyncio
async def test_list_keys_returns_safe_rows_and_passes_filters() -> None:
    repo = _Repo(_row())
    service = AdminKeyDashboardService(gateway_keys_repository=repo)
    institution_id = uuid.uuid4()
    cohort_id = uuid.uuid4()

    rows = await service.list_keys(
        status="active",
        owner_email="ada@example.org",
        public_key_id="public-id",
        institution_id=institution_id,
        cohort_id=cohort_id,
        expired=False,
        limit=25,
        offset=5,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.public_key_id == "public-id"
    assert row.owner_display_name == "Ada Lovelace"
    assert row.owner_email == "ada@example.org"
    assert row.institution_name == "SLAIF University"
    assert row.cohort_name == "Spring Workshop"
    assert row.allowed_models_summary == "gpt-test"
    assert row.allowed_endpoints_summary == "/v1/chat/completions"
    assert row.allowed_providers_summary == "openai"
    assert "30 req/min" in row.rate_limit_policy_summary
    assert row.can_suspend is True
    assert row.can_activate is False
    assert row.can_revoke is True
    assert "token_hash" not in row.__dataclass_fields__
    assert repo.list_calls[0]["institution_id"] == institution_id
    assert repo.list_calls[0]["cohort_id"] == cohort_id
    assert repo.list_calls[0]["limit"] == 25
    assert repo.list_calls[0]["offset"] == 5


@pytest.mark.asyncio
async def test_detail_returns_safe_data_or_not_found() -> None:
    key = _row()
    service = AdminKeyDashboardService(gateway_keys_repository=_Repo(key))

    detail = await service.get_key_detail(key.id)

    assert detail.id == key.id
    assert detail.revoked_reason is None
    assert "token_hash" not in detail.__dataclass_fields__

    with pytest.raises(AdminKeyNotFoundError):
        await service.get_key_detail(uuid.uuid4())


def test_computed_display_status_values() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert compute_key_display_status("active", now - timedelta(days=1), now + timedelta(days=1), now=now) == "active"
    assert compute_key_display_status("active", now + timedelta(days=1), now + timedelta(days=2), now=now) == "not_yet_valid"
    assert compute_key_display_status("active", now - timedelta(days=2), now - timedelta(days=1), now=now) == "expired"
    assert compute_key_display_status("suspended", now - timedelta(days=2), now - timedelta(days=1), now=now) == "suspended"
    assert compute_key_display_status("revoked", now - timedelta(days=1), now + timedelta(days=1), now=now) == "revoked"


@pytest.mark.asyncio
async def test_lifecycle_action_flags_follow_stored_status() -> None:
    active = _row()
    active.status = "active"
    active_detail = await AdminKeyDashboardService(gateway_keys_repository=_Repo(active)).get_key_detail(active.id)
    assert active_detail.can_suspend is True
    assert active_detail.can_activate is False
    assert active_detail.can_revoke is True

    suspended = _row()
    suspended.status = "suspended"
    suspended_detail = await AdminKeyDashboardService(
        gateway_keys_repository=_Repo(suspended)
    ).get_key_detail(suspended.id)
    assert suspended_detail.can_suspend is False
    assert suspended_detail.can_activate is True
    assert suspended_detail.can_revoke is True

    revoked = _row()
    revoked.status = "revoked"
    revoked_detail = await AdminKeyDashboardService(gateway_keys_repository=_Repo(revoked)).get_key_detail(revoked.id)
    assert revoked_detail.can_suspend is False
    assert revoked_detail.can_activate is False
    assert revoked_detail.can_revoke is False
