"""Schema and canonical-bundle behavior for Objective 180 bundles."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from slaif_gateway.schemas.catalog_refresh import RefreshBundle
from slaif_gateway.services.catalog_refresh.bundle import (
    MAX_BUNDLE_BYTES,
    PRICING_TSV_FIELDS,
    ROUTE_TSV_FIELDS,
    canonical_bundle_bytes,
    generate_fx_json,
    generate_pricing_tsv,
    generate_route_tsv,
    load_bundle,
    selected_model_keys,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.pricing_import import parse_pricing_import_tsv
from slaif_gateway.services.route_import import parse_route_import_tsv
from slaif_gateway.services.fx_import import parse_fx_import_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"


def _load_fixture(name: str) -> RefreshBundle:
    return load_bundle((FIXTURES / name).read_bytes())


def _mutate(bundle: RefreshBundle, **overrides) -> RefreshBundle:
    payload = copy.deepcopy(bundle.model_dump(mode="json"))
    for dotted, value in overrides.items():
        node = payload
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        last = parts[-1]
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value
    return load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))


def test_first_install_fixture_loads_and_is_canonical() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    assert bundle.schema_version == "1"
    assert bundle.baseline.mode == "first_install"
    assert bundle.research.status == "NOT_RUN"
    again = load_bundle((FIXTURES / "bundle-first-install.json").read_bytes())
    assert canonical_bundle_bytes(bundle) == canonical_bundle_bytes(again)


def test_selected_model_keys_respects_single_model_include() -> None:
    bundle = _load_fixture("bundle-refresh-ready.json")
    assert selected_model_keys(bundle) == {
        ("openrouter", "synthetic/stable-v1"),
        ("openrouter", "synthetic/updated-v1"),
        ("openrouter", "synthetic/new-v1"),
    }
    single = _mutate(bundle, **{"selection.model_include": ["synthetic/stable-v1"]})
    assert selected_model_keys(single) == {("openrouter", "synthetic/stable-v1")}


def test_bundle_rejects_unknown_fields() -> None:
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _load_raw_with_extra("readiness")
    assert excinfo.value.code == "bundle_schema_invalid"


def _load_raw_with_extra(field: str, value: object = "READY") -> RefreshBundle:
    raw = (FIXTURES / "bundle-first-install.json").read_text()
    mutated = raw.rstrip().removesuffix("}")
    return load_bundle((mutated + f', "{field}": {json.dumps(value)}\n}}').encode("utf-8"))


@pytest.mark.parametrize(
    "field",
    ["readiness", "confidence", "counts", "validation_results", "state"],
)
def test_caller_supplied_readiness_confidence_counters_are_impossible(field: str) -> None:
    assert field not in RefreshBundle.model_fields
    with pytest.raises(CatalogRefreshBlockedError):
        _load_raw_with_extra(field)


def test_bundle_rejects_duplicate_json_key() -> None:
    raw = (FIXTURES / "bundle-duplicate-key.json").read_bytes()
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(raw)
    assert excinfo.value.code == "bundle_invalid_json"
    assert "duplicate JSON key" in excinfo.value.detail


def test_bundle_rejects_non_finite_values() -> None:
    raw = b'{"run_id": "x", "value": NaN}'
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(raw)
    assert excinfo.value.code == "bundle_invalid_json"
    raw = b'{"run_id": "x", "value": Infinity}'
    with pytest.raises(CatalogRefreshBlockedError):
        load_bundle(raw)


def test_bundle_rejects_non_utf8() -> None:
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(b"\xff\xfe\x00{")
    assert excinfo.value.code == "bundle_not_utf8"


def test_bundle_rejects_over_8_mib() -> None:
    oversized = b"x" * (MAX_BUNDLE_BYTES + 1)
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(oversized)
    assert excinfo.value.code == "bundle_too_large"


def test_error_detail_does_not_leak_secret_input() -> None:
    secret = "SUPERSECRETVALUE123"
    raw = (FIXTURES / "bundle-first-install.json").read_text()
    # A schema-invalid payload carrying the secret must not echo it back.
    bad = json.loads(raw)
    bad["models"][0]["model"] = "x" * 201  # exceeds the 200-char model bound
    bad["models"][0]["display_name"] = secret
    try:
        load_bundle(json.dumps(bad).encode("utf-8"))
        leaked = True
    except CatalogRefreshBlockedError as exc:
        leaked = secret in (exc.code + exc.detail)
    assert not leaked, "schema error leaked caller-supplied secret"


def test_bundle_rejects_naive_datetimes() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"generated_at": "2026-09-21T12:00:00"})
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"sources.0.retrieved_at": "2026-09-21T11:00:00"})


def test_bundle_rejects_float_money() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    payload = copy.deepcopy(bundle.model_dump(mode="json"))
    payload["pricing"][0]["dimensions"][0]["value"] = 0.25  # float, not exact string
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    assert excinfo.value.code == "bundle_schema_invalid"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:password@openrouter.ai/models",
        "ftp://openrouter.ai/models",
        "http:///path-without-host",
    ],
)
def test_bundle_rejects_unsafe_source_urls(url: str) -> None:
    bundle = _load_fixture("bundle-first-install.json")
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"sources.0.url": url})


def test_bundle_rejects_unknown_provider_and_source_kind() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"selection.providers": ["anthropic"]})
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"sources.0.source_kind": "web_scrape"})


def test_bundle_rejects_bad_run_id() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"run_id": "Bad Run ID"})
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"run_id": "x" * 65})


def test_first_install_baseline_cannot_carry_sql_evidence() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"baseline": {"mode": "first_install", "exported_at": "2026-09-21T10:00:00+00:00"}})
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"baseline": {"mode": "first_install", "row_counts": {"providers": 0}}})


def test_research_status_must_be_not_run() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    with pytest.raises(CatalogRefreshBlockedError):
        _mutate(bundle, **{"research.status": "RUN"})


def test_generated_artifacts_round_trip_through_existing_import_parsers() -> None:
    bundle = _load_fixture("bundle-first-install.json")
    assert selected_model_keys(bundle) == {("openrouter", "synthetic/chat-v1")}
    # The artifact generators serialize exactly the rows the caller permits
    # (create rows); for a bootstrap that is every proposed row.
    route_tsv = generate_route_tsv(bundle, list(bundle.routes))
    pricing_tsv = generate_pricing_tsv(
        bundle,
        list(bundle.pricing),
        {(r.provider, r.requested_model): r.upstream_model for r in bundle.routes},
    )
    fx_json = generate_fx_json([])

    route_lines = route_tsv.decode("utf-8").splitlines()
    assert route_lines[0].split("\t") == ROUTE_TSV_FIELDS
    assert len(route_lines) == 2  # header + one row

    pricing_lines = pricing_tsv.decode("utf-8").splitlines()
    assert pricing_lines[0].split("\t") == PRICING_TSV_FIELDS
    assert len(pricing_lines) == 2

    route_rows = parse_route_import_tsv(route_tsv.decode("utf-8"))
    assert route_rows[0]["requested_model"] == "synthetic/chat-v1"
    assert route_rows[0]["provider"] == "openrouter"

    pricing_rows = parse_pricing_import_tsv(pricing_tsv.decode("utf-8"))
    assert pricing_rows[0]["model"] == "synthetic/chat-v1"
    assert pricing_rows[0]["input_price_per_1m"] == "0.25"

    fx_rows = parse_fx_import_json(fx_json.decode("utf-8"))
    assert fx_rows == []


def test_generated_artifacts_carry_only_the_permitted_create_rows() -> None:
    """Excluded/changed rows must not leak into the executable artifacts."""
    bundle = _load_fixture("bundle-refresh-ready.json")
    # Only the genuinely new row is a permitted create; the unchanged and
    # changed rows are no-ops/mutations and must stay out of the artifacts.
    new_routes = [r for r in bundle.routes if r.requested_model == "synthetic/new-v1"]
    new_pricing = [p for p in bundle.pricing if p.model == "synthetic/new-v1"]
    upstream_by_key = {
        (r.provider, r.requested_model): r.upstream_model for r in bundle.routes
    }
    route_tsv = generate_route_tsv(bundle, new_routes)
    pricing_tsv = generate_pricing_tsv(bundle, new_pricing, upstream_by_key)
    assert "synthetic/stable-v1" not in route_tsv.decode("utf-8")
    assert "synthetic/updated-v1" not in route_tsv.decode("utf-8")
    assert "synthetic/stable-v1" not in pricing_tsv.decode("utf-8")
    assert "synthetic/updated-v1" not in pricing_tsv.decode("utf-8")
    assert "synthetic/new-v1" in route_tsv.decode("utf-8")
    assert "synthetic/new-v1" in pricing_tsv.decode("utf-8")


def test_pricing_tsv_uses_upstream_model_for_aliased_routes() -> None:
    """Public aliases need not equal upstream IDs: the executable pricing
    row must carry the route's upstream model."""
    bundle = _load_fixture("bundle-first-install.json")
    payload = copy.deepcopy(bundle.model_dump(mode="json"))
    payload["run_id"] = "test-alias-001"
    for route in payload["routes"]:
        route["requested_model"] = "public/alias-v1"  # public alias
        route["upstream_model"] = "synthetic/chat-v1"  # real upstream
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    upstream_by_key = {
        (r.provider, r.requested_model): r.upstream_model for r in bundle.routes
    }
    tsv = generate_pricing_tsv(bundle, list(bundle.pricing), upstream_by_key).decode("utf-8")
    rows = parse_pricing_import_tsv(tsv)
    assert rows[0]["model"] == "synthetic/chat-v1"  # upstream ID, not the alias
    assert "public/alias-v1" not in tsv


def test_bundle_rejects_hostile_money_exponents() -> None:
    # R2: huge exponent/precision values are rejected before any arithmetic.
    bundle = _load_fixture("bundle-first-install.json")
    for hostile in ("1E+100", "999999999.9999999999", "0.2500000001"):
        payload = copy.deepcopy(bundle.model_dump(mode="json"))
        payload["pricing"][0]["dimensions"][0]["value"] = hostile
        with pytest.raises(CatalogRefreshBlockedError) as excinfo:
            load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
        assert excinfo.value.code == "bundle_schema_invalid"


def test_provenance_authoritative_field_is_rejected() -> None:
    # R3: caller-declared authority labels are no longer part of the schema.
    raw = (FIXTURES / "bundle-first-install.json").read_text()
    payload = json.loads(raw)
    payload["models"][0]["provenance"]["authoritative"] = True
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    assert excinfo.value.code == "bundle_schema_invalid"


def test_generate_fx_json_serializes_rates_as_exact_strings() -> None:
    """Canonical artifact direction is native -> EUR (the runtime direction)."""
    from decimal import Decimal, ROUND_HALF_UP

    from slaif_gateway.services.catalog_refresh.bundle import NormalizedFxRow

    bundle = _load_fixture("bundle-first-install.json")
    direct = NormalizedFxRow(
        base_currency="USD",
        quote_currency="EUR",
        rate="0.925925926",
        source="https://www.ecb.europa.eu/stats/eurofxref.html",
        valid_from=bundle.generated_at,
        valid_until=None,
        published_at=None,
        derived_reciprocal=False,
    )
    reciprocal_rate = str((Decimal(1) / Decimal("1.085")).quantize(
        Decimal("0.000000001"), rounding=ROUND_HALF_UP
    ))
    derived = NormalizedFxRow(
        base_currency="USD",
        quote_currency="EUR",
        rate=reciprocal_rate,
        source="https://www.ecb.europa.eu/stats/eurofxref.html",
        valid_from=bundle.generated_at,
        valid_until=None,
        published_at=None,
        derived_reciprocal=True,
        source_pair="EUR-USD",
    )
    fx_json = generate_fx_json([derived, direct])
    rows = parse_fx_import_json(fx_json.decode("utf-8"))
    # Both rows are native -> EUR; the reciprocal row keeps its derivation
    # metadata instead of being silently relabeled.
    assert {row["base_currency"] for row in rows} == {"USD"}
    assert {row["quote_currency"] for row in rows} == {"EUR"}
    by_rate = {row["rate"]: row for row in rows}
    assert by_rate["0.925925926"]["metadata"]["derived_reciprocal"] is False
    assert by_rate[reciprocal_rate]["metadata"]["derived_reciprocal"] is True
    assert by_rate[reciprocal_rate]["metadata"]["source_pair"] == "EUR-USD"
    text = fx_json.decode("utf-8")
    assert reciprocal_rate in text
    assert "1.085" not in text  # the original EUR->USD quotation is not the artifact rate
