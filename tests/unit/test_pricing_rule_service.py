import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.db.models import PricingRule
from slaif_gateway.services.pricing_rule_service import PricingRuleService


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _pricing(**overrides) -> PricingRule:
    values = {
        "id": uuid.uuid4(),
        "provider": "openai",
        "upstream_model": "gpt-test-mini",
        "endpoint": "/v1/chat/completions",
        "currency": "EUR",
        "input_price_per_1m": Decimal("0.100000000"),
        "cached_input_price_per_1m": Decimal("0.050000000"),
        "output_price_per_1m": Decimal("0.200000000"),
        "reasoning_price_per_1m": None,
        "request_price": Decimal("0.010000000"),
        "pricing_metadata": {"source": "manual"},
        "valid_from": NOW,
        "valid_until": None,
        "enabled": True,
        "source_url": "https://pricing.example.org/openai",
        "notes": "safe note",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return PricingRule(**values)


class _PricingRepo:
    def __init__(self, row: PricingRule | None = None) -> None:
        self.row = row

    async def create_pricing_rule(self, **kwargs):
        self.row = _pricing(**kwargs)
        return self.row

    async def get_pricing_rule_by_id(self, pricing_rule_id):
        if self.row is not None and self.row.id == pricing_rule_id:
            return self.row
        return None

    async def update_pricing_rule_metadata(self, pricing_rule_id, **kwargs):
        if self.row is None or self.row.id != pricing_rule_id:
            return False
        for key, value in kwargs.items():
            setattr(self.row, key, value)
        return True

    async def set_pricing_rule_enabled(self, pricing_rule_id, *, enabled):
        if self.row is None or self.row.id != pricing_rule_id:
            return False
        self.row.enabled = enabled
        return True


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)


def _service(row: PricingRule | None = None) -> tuple[PricingRuleService, _PricingRepo, _AuditRepo]:
    pricing = _PricingRepo(row)
    audit = _AuditRepo()
    return (
        PricingRuleService(pricing_rules_repository=pricing, audit_repository=audit),
        pricing,
        audit,
    )


@pytest.mark.asyncio
async def test_pricing_rule_create_writes_safe_actor_audit() -> None:
    service, _pricing_repo, audit = _service()
    actor_admin_id = uuid.uuid4()

    row = await service.create_pricing_rule(
        provider="openai",
        model="gpt-test-mini",
        endpoint="chat.completions",
        currency="eur",
        input_price_per_1m=Decimal("0.100000000"),
        output_price_per_1m=Decimal("0.200000000"),
        cached_input_price_per_1m=None,
        reasoning_price_per_1m=None,
        request_price=Decimal("0"),
        pricing_metadata={"source": "manual"},
        valid_from=NOW,
        valid_until=None,
        source_url=None,
        notes="safe note",
        enabled=True,
        actor_admin_id=actor_admin_id,
        reason="pricing setup",
    )

    assert row.endpoint == "/v1/chat/completions"
    assert row.currency == "EUR"
    assert audit.rows[0]["admin_user_id"] == actor_admin_id
    assert audit.rows[0]["action"] == "pricing_rule_created"
    assert audit.rows[0]["new_values"]["request_price"] == "0"
    assert "api_key_value" not in audit.rows[0]["new_values"]


@pytest.mark.asyncio
async def test_pricing_rule_update_writes_safe_actor_audit() -> None:
    existing = _pricing()
    service, _pricing_repo, audit = _service(existing)
    actor_admin_id = uuid.uuid4()

    updated = await service.update_pricing_rule(
        existing.id,
        provider="openai",
        model="gpt-test-mini",
        endpoint="/v1/chat/completions",
        currency="USD",
        input_price_per_1m=Decimal("0.300000000"),
        cached_input_price_per_1m=None,
        output_price_per_1m=Decimal("0.400000000"),
        reasoning_price_per_1m=None,
        request_price=None,
        pricing_metadata={"source": "updated"},
        valid_from=NOW,
        valid_until=None,
        source_url="https://pricing.example.org/new",
        notes="updated note",
        enabled=False,
        actor_admin_id=actor_admin_id,
        reason="maintenance",
    )

    assert updated.enabled is False
    assert updated.currency == "USD"
    assert audit.rows[0]["admin_user_id"] == actor_admin_id
    assert audit.rows[0]["action"] == "pricing_rule_updated"
    assert audit.rows[0]["old_values"]["enabled"] is True
    assert audit.rows[0]["new_values"]["enabled"] is False


@pytest.mark.asyncio
async def test_pricing_rule_enable_disable_writes_safe_actor_audit() -> None:
    existing = _pricing(enabled=False)
    service, _pricing_repo, audit = _service(existing)
    actor_admin_id = uuid.uuid4()

    row = await service.set_pricing_rule_enabled(
        existing.id,
        enabled=True,
        actor_admin_id=actor_admin_id,
        reason="ready",
    )

    assert row.enabled is True
    assert audit.rows[0]["action"] == "pricing_rule_enabled"
    assert audit.rows[0]["admin_user_id"] == actor_admin_id


@pytest.mark.asyncio
async def test_pricing_rule_service_rejects_negative_prices() -> None:
    service, _pricing_repo, _audit = _service()

    with pytest.raises(ValueError, match="input_price_per_1m"):
        await service.create_pricing_rule(
            provider="openai",
            model="gpt-test-mini",
            endpoint="/v1/chat/completions",
            currency="EUR",
            input_price_per_1m=Decimal("-0.1"),
            output_price_per_1m=Decimal("0.2"),
            cached_input_price_per_1m=None,
            reasoning_price_per_1m=None,
            request_price=None,
            pricing_metadata={},
            valid_from=NOW,
            valid_until=None,
            source_url=None,
            notes=None,
            enabled=True,
        )
