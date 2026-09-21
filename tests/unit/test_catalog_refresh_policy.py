"""Deterministic policy thresholds and freshness semantics for Objective 180."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from slaif_gateway.schemas.catalog_refresh import RefreshBundle
from slaif_gateway.services.catalog_refresh.baseline import load_baseline
from slaif_gateway.services.catalog_refresh.bundle import load_bundle
from slaif_gateway.services.catalog_refresh.policy import (
    DEFAULT_POLICY_VERSION,
    policy_from_document,
)
from slaif_gateway.schemas.catalog_refresh import PolicyDocument
from slaif_gateway.services.catalog_refresh.validation import (
    OVERALL_BLOCKED,
    OVERALL_READY,
    OVERALL_READY_WITH_WARNINGS,
    validate_bundle,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
GENERATED_AT = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


def _baseline():
    return load_baseline((FIXTURES / "baseline-synthetic.json").read_bytes())


def _bundle(**overrides) -> RefreshBundle:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
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


def _codes(report) -> set[str]:
    return {warning.code for warning in report.warnings}


def test_policy_document_defaults_and_version() -> None:
    policy = policy_from_document(PolicyDocument(version=DEFAULT_POLICY_VERSION))
    assert policy.price_change_review == Decimal("0.25")
    assert policy.fx_change_review == Decimal("0.03")
    assert policy.source_stale_review == timedelta(hours=24)
    assert policy.source_stale_blocked == timedelta(hours=72)
    assert policy.fx_stale_review == timedelta(days=3)
    assert policy.fx_stale_blocked == timedelta(days=7)


def test_policy_document_rejects_unsupported_version() -> None:
    with pytest.raises(ValueError):
        PolicyDocument(version=99)


def test_policy_document_rejects_inverted_thresholds() -> None:
    with pytest.raises(ValueError):
        PolicyDocument(source_stale_blocked_hours=1, source_stale_review_hours=24)
    with pytest.raises(ValueError):
        PolicyDocument(fx_stale_blocked_days=1, fx_stale_review_days=3)
    with pytest.raises(ValueError):
        PolicyDocument(price_change_review="0")


def _price_move_report(input_value: str):
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = input_value
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    return report


def test_price_move_exactly_25_percent_is_not_review() -> None:
    # baseline input 1.00 -> 1.25 is exactly the 0.25 threshold; strict >
    report = _price_move_report("1.25")
    assert "price_moved_review" not in _codes(report)
    assert report.state in {OVERALL_READY, OVERALL_READY_WITH_WARNINGS}
    changed = [c for c in report.price_comparisons if c.model == "synthetic/updated-v1" and c.dimension == "input"]
    assert Decimal(changed[0].percent_change) == Decimal("0.25")
    assert changed[0].state == "CHANGED"


def test_price_move_above_25_percent_is_review() -> None:
    report = _price_move_report("1.26")
    assert "price_moved_review" in _codes(report)
    assert report.state == OVERALL_READY_WITH_WARNINGS


def test_price_zero_transitions_are_review_without_percent_division() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    for item in payload["pricing"]:
        if item["model"] == "synthetic/stable-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = "0"
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    codes = _codes(report)
    assert "price_zero_transition" in codes
    assert "price_moved_review" not in codes  # no division by zero
    moved = [c for c in report.price_comparisons if c.model == "synthetic/stable-v1" and c.dimension == "input"]
    assert moved[0].state == "ZERO_TRANSITION"
    assert moved[0].percent_change is None
    assert report.state == OVERALL_READY_WITH_WARNINGS


def _source_age_report(hours: float):
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    retrieved = (GENERATED_AT - timedelta(hours=hours)).isoformat()
    for source in payload["sources"]:
        source["retrieved_at"] = retrieved
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    return report


def test_source_age_boundaries_are_strict() -> None:
    assert _source_age_report(23).state == OVERALL_READY
    assert _source_age_report(24).state == OVERALL_READY_WITH_WARNINGS  # age == 24h -> review
    assert "source_stale_review" in _codes(_source_age_report(25))
    assert "source_stale_blocked" not in _codes(_source_age_report(72))  # age == 72h -> review
    assert "source_stale_blocked" in _codes(_source_age_report(72 + 1 / 60))
    assert _source_age_report(72 + 1 / 60).state == OVERALL_BLOCKED


def test_future_source_timestamp_blocks() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    for source in payload["sources"]:
        source["retrieved_at"] = (GENERATED_AT + timedelta(hours=1)).isoformat()
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    assert "future_source_timestamp" in _codes(report)
    assert report.state == OVERALL_BLOCKED


def _fx_report(rate: str, published_hours_ago: float | None):
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-fx-policy-001"
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            item["currency"] = "USD"
            for dimension in item["dimensions"]:
                dimension["currency"] = "USD"
    published = (
        (GENERATED_AT - timedelta(hours=published_hours_ago)).isoformat() if published_hours_ago is not None else None
    )
    payload["fx"] = [
        {
            "base_currency": "EUR",
            "quote_currency": "USD",
            "rate": rate,
            "valid_from": "2026-09-21T00:00:00+00:00",
            "valid_until": None,
            "published_at": published,
            "source": "https://www.ecb.europa.eu/stats/eurofxref.html",
            "provenance": {
                "sources": ["openrouter|synthetic/stable-v1|openrouter_models_api"],
                "extractor": "fixture-deterministic/1.0",
                "extraction": "deterministic",
                "authoritative": True,
            },
            "warnings": [],
        }
    ]
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    return report


def test_fx_move_exactly_3_percent_is_not_review() -> None:
    # baseline EUR->USD 1.08 * 1.03 = 1.1124 exactly
    report = _fx_report("1.1124", 1)
    assert "fx_moved_review" not in _codes(report)


def test_fx_move_above_3_percent_is_review() -> None:
    report = _fx_report("1.1125", 1)
    assert "fx_moved_review" in _codes(report)


def test_fx_publication_age_boundaries_are_calendar_days() -> None:
    assert "fx_stale_review" not in _codes(_fx_report("1.08", 3 * 24 - 1))
    assert "fx_stale_review" in _codes(_fx_report("1.08", 3 * 24))  # == 3 days -> review
    assert "fx_stale_blocked" not in _codes(_fx_report("1.08", 7 * 24))  # == 7 days -> review
    assert "fx_stale_blocked" in _codes(_fx_report("1.08", 7 * 24 + 1))
    assert _fx_report("1.08", 7 * 24 + 1).state == OVERALL_BLOCKED


def test_fx_missing_publication_date_is_review() -> None:
    report = _fx_report("1.08", None)
    assert "fx_no_publication_date" in _codes(report)


def test_fx_future_publication_blocks() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-fx-future-001"
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            item["currency"] = "USD"
            for dimension in item["dimensions"]:
                dimension["currency"] = "USD"
    payload["fx"] = [
        {
            "base_currency": "EUR",
            "quote_currency": "USD",
            "rate": "1.08",
            "valid_from": "2026-09-21T00:00:00+00:00",
            "valid_until": None,
            "published_at": (GENERATED_AT + timedelta(hours=1)).isoformat(),
            "source": "https://www.ecb.europa.eu/stats/eurofxref.html",
            "provenance": {
                "sources": ["openrouter|synthetic/stable-v1|openrouter_models_api"],
                "extractor": "fixture-deterministic/1.0",
                "extraction": "deterministic",
                "authoritative": True,
            },
            "warnings": [],
        }
    ]
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    assert "fx_future_publication" in _codes(report)
    assert report.state == OVERALL_BLOCKED


def test_all_eur_selected_pricing_marks_fx_na_not_missing() -> None:
    bundle = _bundle()
    report, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    fx_gate = next(gate for gate in report.gates if gate.name == "import.fx")
    assert fx_gate.evidence == "N/A"
    assert "EUR" in fx_gate.detail
    assert not any(warning.code == "fx_missing_required_pair" for warning in report.warnings)


def test_missing_eur_quote_pair_blocks_when_non_eur_pricing_selected() -> None:
    report = _fx_report("1.08", 1)  # provides EUR->USD
    assert not any(warning.code == "fx_missing_required_pair" for warning in report.warnings)
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            item["currency"] = "USD"
            for dimension in item["dimensions"]:
                dimension["currency"] = "USD"
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report2, _ = validate_bundle(bundle, _baseline(), policy_from_document(bundle.policy))
    assert "fx_missing_required_pair" in _codes(report2)
    assert report2.state == OVERALL_BLOCKED
