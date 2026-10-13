"""Canonical apply-plan derivation (objective 182, A2/A3).

The plan is a canonical typed projection of the authenticated sealed bytes:
no effective T, no wall clock, no live database state. Plan identity
(``plan_sha256``) is stable for the same sealed run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from slaif_gateway.schemas.catalog_refresh import (
    APPLY_PLAN_SCHEMA_VERSION,
    BaselineFxRow,
    BaselinePricingRow,
    derived_route_capabilities,
)
from slaif_gateway.services.catalog_refresh import planning
from slaif_gateway.services.catalog_refresh.bundle import load_bundle

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"


def _bundle():
    return load_bundle((FIXTURES / "bundle-first-install.json").read_bytes())


def _pricing_row(**overrides) -> BaselinePricingRow:
    now = datetime(2026, 10, 13, 2, 0, 0, tzinfo=UTC)
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        provider="openrouter",
        upstream_model="synthetic/chat-v1",
        endpoint="/v1/chat/completions",
        currency="EUR",
        input_price_per_1m="0.25",
        cached_input_price_per_1m=None,
        output_price_per_1m="1",
        reasoning_price_per_1m=None,
        request_price=None,
        valid_from=now,
        valid_until=None,
        enabled=True,
        source_url=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return BaselinePricingRow(**base)


def _fx_row(**overrides) -> BaselineFxRow:
    now = datetime(2026, 10, 13, 2, 0, 0, tzinfo=UTC)
    base = dict(
        id="22222222-2222-2222-2222-222222222222",
        base_currency="USD",
        quote_currency="EUR",
        rate="0.9",
        valid_from=now,
        valid_until=None,
        source=None,
        source_label="manual",
        created_at=now,
    )
    base.update(overrides)
    return BaselineFxRow(**base)


def test_create_provider_op_carries_canonical_defaults() -> None:
    for provider, env_var, base_url in (
        ("openai", "OPENAI_UPSTREAM_API_KEY", "https://api.openai.com/v1"),
        ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    ):
        op = planning.create_provider_op(provider)
        assert op["type"] == "create_provider"
        assert op["provider"] == provider
        assert op["display_name"] == provider
        assert op["base_url"] == base_url
        assert op["api_key_env_var"] == env_var
        assert op["kind"] == "openai_compatible"
        assert op["enabled"] is True
        assert op["timeout_seconds"] == 300
        assert op["max_retries"] == 2


def test_create_route_op_carries_derived_capability_contract() -> None:
    route = _bundle().routes[0]
    op = planning.create_route_op(route)
    assert op["type"] == "create_route"
    assert op["provider"] == route.provider
    assert op["requested_model"] == route.requested_model
    assert op["upstream_model"] == route.upstream_model
    assert op["match_type"] == route.match_type
    assert op["priority"] == route.priority
    assert op["endpoint"] == route.endpoint
    assert op["capabilities"] == derived_route_capabilities(
        route.capabilities, supports_streaming=route.supports_streaming
    )


def test_create_pricing_op_uses_upstream_identity_and_effective_t_symbol() -> None:
    bundle = _bundle()
    facts = bundle.pricing[0]
    op = planning.create_pricing_op(bundle, facts, upstream="synthetic/chat-v1")
    assert op["type"] == "create_pricing"
    assert op["provider"] == "openrouter"
    # the executable pricing row carries the UPSTREAM model identity
    assert op["model"] == "synthetic/chat-v1"
    assert op["endpoint"] == "/v1/chat/completions"
    assert op["currency"] == "EUR"
    assert op["dimensions"] == {"input": "0.25", "output": "1"}
    assert op["new_valid_from"] == planning.EFFECTIVE_T_SYMBOL


def test_supersede_pricing_op_records_reviewed_old_facts() -> None:
    bundle = _bundle()
    old = _pricing_row(valid_until=None)
    op = planning.supersede_pricing_op(bundle, old, bundle.pricing[0])
    assert op["type"] == "supersede_pricing"
    assert op["provider"] == "openrouter"
    assert op["model"] == "synthetic/chat-v1"
    assert op["old"]["row_id"] == old.id
    assert op["old"]["currency"] == "EUR"
    assert op["old"]["dimensions"] == {
        "input": "0.25",
        "cached_input": None,
        "output": "1",
        "reasoning": None,
        "request": None,
    }
    assert op["old"]["valid_from"] == old.valid_from.astimezone(UTC).isoformat()
    assert op["old"]["valid_until"] is None
    assert op["old"]["enabled"] is True
    assert op["new"]["currency"] == "EUR"
    assert op["new"]["dimensions"] == {"input": "0.25", "output": "1"}
    assert op["new"]["new_valid_from"] == planning.EFFECTIVE_T_SYMBOL


def test_supersede_fx_op_records_reviewed_old_facts() -> None:
    old = _fx_row()
    op = planning.supersede_fx_op(
        old,
        rate="0.92",
        source="ecb",
        published_at=datetime(2026, 10, 13, 3, 0, 0, tzinfo=UTC),
        derived=False,
        source_pair=None,
    )
    assert op["type"] == "supersede_fx"
    assert op["base_currency"] == "USD"
    assert op["quote_currency"] == "EUR"
    assert op["old"]["row_id"] == old.id
    assert op["old"]["rate"] == "0.9"
    assert op["old"]["valid_until"] is None
    assert op["new"]["rate"] == "0.92"
    assert op["new"]["derived_reciprocal"] is False
    assert op["new"]["new_valid_from"] == planning.EFFECTIVE_T_SYMBOL


def test_create_fx_op_shape() -> None:
    op = planning.create_fx_op(
        ("USD", "EUR"),
        rate="0.9",
        source="ecb",
        published_at=None,
        derived=False,
        source_pair=None,
    )
    assert op["type"] == "create_fx"
    assert op["base_currency"] == "USD"
    assert op["quote_currency"] == "EUR"
    assert op["rate"] == "0.9"
    assert op["published_at"] is None
    assert op["new_valid_from"] == planning.EFFECTIVE_T_SYMBOL


def test_plan_sha256_is_content_and_order_sensitive_as_given() -> None:
    a = planning.create_provider_op("openai")
    b = planning.create_route_op(_bundle().routes[0])
    # plan_sha256 encodes the list exactly as given (canonical encoding of
    # each op, sorted keys); it does NOT re-sort.
    assert planning.plan_sha256([a, b]) != planning.plan_sha256([b, a])
    other = dict(a)
    other["display_name"] = "renamed"
    assert planning.plan_sha256([a, b]) != planning.plan_sha256([other, b])
    # canonicity is a build_apply_plan property: differently ordered inputs
    # yield the identical plan object (and therefore plan identity)
    assert planning.build_apply_plan([a, b]) == planning.build_apply_plan([b, a])


def test_build_apply_plan_sorts_operations_canonically() -> None:
    bundle = _bundle()
    ops = [
        planning.create_pricing_op(bundle, bundle.pricing[0], upstream="synthetic/chat-v1"),
        planning.supersede_fx_op(
            _fx_row(),
            rate="0.92",
            source="ecb",
            published_at=None,
            derived=False,
            source_pair=None,
        ),
        planning.create_route_op(bundle.routes[0]),
        planning.create_provider_op("openrouter"),
        planning.supersede_pricing_op(bundle, _pricing_row(), bundle.pricing[0]),
        planning.create_fx_op(
            ("USD", "EUR"), rate="0.9", source=None, published_at=None,
            derived=False, source_pair=None,
        ),
    ]
    plan = planning.build_apply_plan(ops)
    assert plan["schema_version"] == APPLY_PLAN_SCHEMA_VERSION
    types = [op["type"] for op in plan["operations"]]
    # canonical total order: providers, routes, creates, pricing supersessions,
    # FX creates, FX supersessions
    assert types == [
        "create_provider",
        "create_route",
        "create_pricing",
        "supersede_pricing",
        "create_fx",
        "supersede_fx",
    ]
    assert plan["plan_sha256"] == planning.plan_sha256(plan["operations"])
    # re-deriving from a differently ordered input is byte-identical
    assert planning.build_apply_plan(list(reversed(ops))) == plan


def test_plan_carries_no_wall_clock_or_effective_t_values() -> None:
    bundle = _bundle()
    ops = [
        planning.create_pricing_op(bundle, bundle.pricing[0], upstream="synthetic/chat-v1"),
        planning.supersede_pricing_op(bundle, _pricing_row(), bundle.pricing[0]),
        planning.create_fx_op(
            ("USD", "EUR"), rate="0.9", source=None,
            published_at=None, derived=False, source_pair=None,
        ),
    ]
    plan = planning.build_apply_plan(ops)
    rendered = json.dumps(plan, sort_keys=True)
    # no bundle generation time, no chosen effective instant: the only
    # "new_valid_from" values are the effective_t symbol
    assert bundle.generated_at.isoformat() not in rendered
    for op in plan["operations"]:
        for section in ("new",):
            if section in op:
                assert op[section]["new_valid_from"] == planning.EFFECTIVE_T_SYMBOL
        if "new_valid_from" in op:
            assert op["new_valid_from"] == planning.EFFECTIVE_T_SYMBOL


def test_unknown_operation_type_sorts_are_rejected() -> None:
    with pytest.raises(KeyError):
        planning.op_sort_key({"type": "delete_route"})
