"""Deterministic policy thresholds, freshness semantics, and FX direction.

State model under test (180-b): a genuinely unchanged row is a no-op (READY
contribution), a real changed row is a blocked mutation (overall BLOCKED,
because no apply operation exists in this version), and REVIEW findings make
the state at least READY_WITH_WARNINGS. The exact boundary tests use a
programmatic mini-baseline whose scope matches the bundle exactly, so the
overall state isolates the property under test.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import test_catalog_refresh_source_evidence as _evidence_tests

from slaif_gateway.schemas.catalog_refresh import (
    BaselineCounts,
    BaselineDocument,
    BaselineFxRow,
    BaselinePricingRow,
    BaselineProviderRow,
    BaselineRouteRow,
    BaselineTarget,
    PolicyDocument,
    RefreshBundle,
)
from slaif_gateway.services.catalog_refresh.baseline import (
    canonical_baseline_content,
    load_baseline,
)
from slaif_gateway.services.catalog_refresh.bundle import load_bundle
from slaif_gateway.services.catalog_refresh.policy import (
    DEFAULT_POLICY_VERSION,
    policy_from_document,
)
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


def _bundle_payload(**overrides) -> dict:
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
    return payload


def _bundle(**overrides) -> RefreshBundle:
    return load_bundle(json.dumps(_bundle_payload(**overrides), sort_keys=True).encode("utf-8"))


def _codes(report) -> set[str]:
    return {warning.code for warning in report.warnings}


# Per-1m USD values carried by the fixture OpenRouter snapshot (the 1.08
# reference quote of the EUR fixture prices). Pricing a whole bundle in
# these exact values keeps the price facts bound to parsed observations for
# any claimed FX rate, so FX tests exercise the FX gate, not price binding.
USD_PER_1M = {
    "synthetic/stable-v1": ("0.54", "2.16"),
    "synthetic/updated-v1": ("1.296", "4.32"),
    "synthetic/new-v1": ("0.108", "0.432"),
}


def _usd_pricing(payload: dict) -> None:
    for item in payload["pricing"]:
        input_v, output_v = USD_PER_1M[item["model"]]
        item["currency"] = "USD"
        for dimension in item["dimensions"]:
            dimension["currency"] = "USD"
            dimension["value"] = input_v if dimension["name"] == "input" else output_v


def _mini_usd_baseline(*, fx: list[dict] | None = None) -> BaselineDocument:
    return _mini_baseline(
        pricing={
            model: {"input": in_v, "output": out_v} for model, (in_v, out_v) in USD_PER_1M.items()
        },
        fx=fx,
        currencies={model: "USD" for model in USD_PER_1M},
    )


# --- programmatic mini-baseline (exact scope control) ----------------------

def _fx_source_dict(model_part: str = "USD-EUR") -> dict:
    """An FX-specific, official-host docs source with bound evidence bytes."""
    evidence = f"fx-evidence-{model_part}".encode("utf-8")
    return {
        "provider": "openrouter",
        "model": model_part,
        "source_kind": "docs_page",
        "url": "https://openrouter.ai/docs/fx",
        "retrieved_at": (GENERATED_AT - timedelta(hours=1)).isoformat(),
        "published_at": None,
        "content_sha256": hashlib.sha256(evidence).hexdigest(),
        "evidence_b64": base64.b64encode(evidence).decode("ascii"),
        "extractor": "fixture-deterministic/1.0",
        "extraction": "deterministic",
        "required": True,
        "truncated": False,
        "warnings": [],
    }


def _fx_facts_dict(
    rate: str,
    *,
    pair: str = "USD-EUR",
    published_hours_ago: float | None = 1,
    provider: str = "ecb",
    kind: str = "ecb_reference_xml",
) -> dict:
    base, quote = pair.split("-")
    published = (
        (GENERATED_AT - timedelta(hours=published_hours_ago)).isoformat()
        if published_hours_ago is not None
        else None
    )
    return {
        "base_currency": base,
        "quote_currency": quote,
        "rate": rate,
        "valid_from": "2026-09-20T00:00:00+00:00",
        "valid_until": None,
        "published_at": published,
        "source": "https://www.ecb.europa.eu/stats/eurofxref.html",
        "provenance": {
            "sources": [f"{provider}|{pair}|{kind}"],
            "extractor": "fixture-deterministic/1.0",
            "extraction": "deterministic",
        },
        "warnings": [],
    }


def _mini_baseline(
    *,
    pricing: dict[str, dict] | None = None,
    fx: list[dict] | None = None,
    priorities: dict[str, int] | None = None,
    currencies: dict[str, str] | None = None,
) -> BaselineDocument:
    """Build a BaselineDocument scoped to the pre-existing baseline models.

    ``pricing`` maps model -> {"input": str, "output": str}; the default
    covers only stable-v1 and updated-v1 (the models that existed before the
    refresh) and mirrors the fixture bundle's proposed values, so the bundle
    is a true no-change refresh for them while new-v1 stays a genuine NEW
    create. Route priorities default to the fixture values (200 for
    updated-v1). ``fx`` is a list of {"base", "quote", "rate", "valid_from"}
    rows.
    """
    default = {
        "synthetic/stable-v1": {"input": "0.5", "output": "2"},
        "synthetic/updated-v1": {"input": "1.2", "output": "4"},
    }
    pricing = default if pricing is None else pricing
    priorities = priorities if priorities is not None else {"synthetic/updated-v1": 200}
    fx_rows = tuple(
        BaselineFxRow(
            id=f"44444444-0000-4000-8000-{index:012d}",
            base_currency=entry["base"],
            quote_currency=entry["quote"],
            rate=entry["rate"],
            valid_from=datetime.fromisoformat(entry["valid_from"]),
            valid_until=(
                datetime.fromisoformat(entry["valid_until"]) if entry.get("valid_until") else None
            ),
            source="https://www.ecb.europa.eu/stats/eurofxref.html",
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        )
        for index, entry in enumerate(fx or [])
    )
    baseline = BaselineDocument(
        schema_version="1",
        exported_at="2026-09-21T10:00:00+00:00",
        target=BaselineTarget(
            server_host="127.0.0.1",
            server_port=5433,
            database="slaif-mini-baseline",
            postgres_version="16.4",
        ),
        sql_checked=True,
        counts=BaselineCounts(
            providers=1,
            routes=len(pricing),
            pricing_rules=len(pricing),
            fx_rates=len(fx_rows),
        ),
        content_sha256="0" * 64,
        providers=(
            BaselineProviderRow(
                id="11111111-1111-4111-8111-111111111111",
                provider="openrouter",
                display_name="OpenRouter (synthetic)",
                kind="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                api_key_env_var="OPENROUTER_API_KEY",
                enabled=True,
                timeout_seconds=300,
                max_retries=2,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
            ),
        ),
        routes=tuple(
            BaselineRouteRow(
                id=f"22222222-0000-4000-8000-{index:012d}",
                requested_model=model,
                match_type="exact",
                endpoint="/v1/chat/completions",
                provider="openrouter",
                upstream_model=model,
                priority=priorities.get(model, 100),
                enabled=True,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={"text": True, "streaming": True},
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
            )
            for index, model in enumerate(pricing)
        ),
        pricing=tuple(
            BaselinePricingRow(
                id=f"33333333-0000-4000-8000-{index:012d}",
                provider="openrouter",
                upstream_model=model,
                endpoint="/v1/chat/completions",
                currency=(currencies or {}).get(model, "EUR"),
                input_price_per_1m=values["input"],
                cached_input_price_per_1m=None,
                output_price_per_1m=values["output"],
                reasoning_price_per_1m=None,
                request_price=None,
                valid_from="2026-09-01T00:00:00+00:00",
                valid_until=None,
                enabled=True,
                source_url="https://openrouter.ai/models",
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
            )
            for index, (model, values) in enumerate(pricing.items())
        ),
        fx=fx_rows,
    )
    digest = hashlib.sha256(
        canonical_baseline_content(baseline.model_copy(update={"content_sha256": "0" * 64}))
    ).hexdigest()
    return baseline.model_copy(update={"content_sha256": digest})


def _review(bundle: RefreshBundle, baseline: BaselineDocument | None = None):
    return validate_bundle(
        bundle, baseline if baseline is not None else _baseline(), policy_from_document(bundle.policy)
    )[0]


# --- policy documents -------------------------------------------------------

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


# --- price movement boundaries (findings, not state drivers) ----------------

def _price_move_report(input_value: str):
    payload = _bundle_payload()
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = input_value
    # The evidence must carry the proposed price: re-emit the shared
    # OpenRouter snapshot so the proposed value matches a parsed
    # observation (the fixture snapshot pins 1.2/4 EUR for updated-v1).
    _evidence_tests.set_openrouter_evidence(
        payload, {**_evidence_tests.DEFAULT_PRICES, "synthetic/updated-v1": (input_value, "4")}
    )
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    # updated-v1 baseline input is 1.0, so the threshold is exercised
    # directly against 1.25/1.26.
    baseline = _mini_baseline(
        pricing={
            "synthetic/stable-v1": {"input": "0.5", "output": "2"},
            "synthetic/updated-v1": {"input": "1", "output": "4"},
        }
    )
    return validate_bundle(bundle, baseline, policy_from_document(bundle.policy))[0]


def test_price_move_exactly_25_percent_is_not_review() -> None:
    # baseline input 1.00 -> 1.25 is exactly the 0.25 threshold; strict >
    report = _price_move_report("1.25")
    assert "price_moved_review" not in _codes(report)
    changed = [c for c in report.price_comparisons if c.model == "synthetic/updated-v1" and c.dimension == "input"]
    assert Decimal(changed[0].percent_change) == Decimal("0.25")
    assert changed[0].state == "CHANGED"
    # The changed row itself blocks: updates are not apply operations in
    # this version (the finding threshold is no longer the state driver).
    assert report.state == OVERALL_BLOCKED


def test_price_move_above_25_percent_adds_review_finding() -> None:
    report = _price_move_report("1.26")
    assert "price_moved_review" in _codes(report)
    changed = [c for c in report.price_comparisons if c.model == "synthetic/updated-v1" and c.dimension == "input"]
    assert changed[0].state == "CHANGED_REVIEW"
    assert report.state == OVERALL_BLOCKED


def test_price_zero_transitions_are_review_without_percent_division() -> None:
    payload = _bundle_payload()
    for item in payload["pricing"]:
        if item["model"] == "synthetic/stable-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = "0"
    _evidence_tests.set_openrouter_evidence(
        payload, {**_evidence_tests.DEFAULT_PRICES, "synthetic/stable-v1": ("0", "2")}
    )
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    baseline = _mini_baseline()  # stable baseline input 0.5
    report = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))[0]
    codes = _codes(report)
    assert "price_zero_transition" in codes
    assert "price_moved_review" not in codes  # no division by zero
    moved = [c for c in report.price_comparisons if c.model == "synthetic/stable-v1" and c.dimension == "input"]
    assert moved[0].state == "ZERO_TRANSITION"
    assert moved[0].percent_change is None
    assert report.state == OVERALL_BLOCKED  # the zero crossing is a real change


# --- baseline active-row selection (no fallback) ----------------------------

def test_expired_baseline_rows_are_not_fallback() -> None:
    bundle = _bundle()
    # All baseline pricing expired before the run time: no before-values are
    # invented; the compared dimensions read as NEW against an existing row,
    # i.e. a real mutation (update) rather than a no-op.
    baseline = _mini_baseline()
    expired = baseline.model_copy(
        update={
            "pricing": tuple(
                row.model_copy(update={"valid_until": datetime(2026, 9, 20, tzinfo=UTC)})
                for row in baseline.pricing
            )
        }
    )
    digest = hashlib.sha256(
        canonical_baseline_content(expired.model_copy(update={"content_sha256": "0" * 64}))
    ).hexdigest()
    expired = expired.model_copy(update={"content_sha256": digest})
    report = validate_bundle(bundle, expired, policy_from_document(bundle.policy))[0]
    states = {
        (c.model, c.dimension): c.state for c in report.price_comparisons
    }
    assert all(state == "NEW" for state in states.values())
    assert all(c.old is None for c in report.price_comparisons)
    assert report.counts["unchanged"] == 0
    assert report.state == OVERALL_BLOCKED  # existing rows would need updates


def test_future_baseline_rows_are_not_active() -> None:
    bundle = _bundle()
    baseline = _mini_baseline()
    future = baseline.model_copy(
        update={
            "pricing": tuple(
                row.model_copy(update={"valid_from": datetime(2026, 9, 22, tzinfo=UTC)})
                for row in baseline.pricing
            )
        }
    )
    digest = hashlib.sha256(
        canonical_baseline_content(future.model_copy(update={"content_sha256": "0" * 64}))
    ).hexdigest()
    future = future.model_copy(update={"content_sha256": digest})
    report = validate_bundle(bundle, future, policy_from_document(bundle.policy))[0]
    assert all(c.old is None for c in report.price_comparisons)
    assert report.counts["unchanged"] == 0
    assert report.state == OVERALL_BLOCKED


def test_ambiguous_overlapping_active_baseline_rows_block() -> None:
    bundle = _bundle()
    baseline = _mini_baseline()
    extra = BaselinePricingRow(
        id="33333333-0000-4000-8000-999999999999",
        provider="openrouter",
        upstream_model="synthetic/stable-v1",
        endpoint="/v1/chat/completions",
        currency="EUR",
        input_price_per_1m="0.6",  # different value, same active window
        cached_input_price_per_1m=None,
        output_price_per_1m="2",
        reasoning_price_per_1m=None,
        request_price=None,
        valid_from="2026-09-05T00:00:00+00:00",
        valid_until=None,
        enabled=True,
        source_url="https://openrouter.ai/models",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
    )
    ambiguous = baseline.model_copy(
        update={
            "pricing": baseline.pricing + (extra,),
            "counts": BaselineCounts(providers=1, routes=3, pricing_rules=4, fx_rates=0),
        }
    )
    digest = hashlib.sha256(
        canonical_baseline_content(ambiguous.model_copy(update={"content_sha256": "0" * 64}))
    ).hexdigest()
    ambiguous = ambiguous.model_copy(update={"content_sha256": digest})
    report = validate_bundle(bundle, ambiguous, policy_from_document(bundle.policy))[0]
    assert "baseline_ambiguous_rows" in _codes(report)
    assert report.state == OVERALL_BLOCKED


# --- source age boundaries (isolated state) ---------------------------------

def _source_age_report(hours: float):
    payload = _bundle_payload()
    retrieved = (GENERATED_AT - timedelta(hours=hours)).isoformat()
    for source in payload["sources"]:
        source["retrieved_at"] = retrieved
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    baseline = _mini_baseline()  # mirrors the proposal: no mutations at all
    return validate_bundle(bundle, baseline, policy_from_document(bundle.policy))[0]


def test_source_age_boundaries_are_strict() -> None:
    assert _source_age_report(23).state == OVERALL_READY
    assert _source_age_report(24).state == OVERALL_READY_WITH_WARNINGS  # age == 24h -> review
    assert "source_stale_review" in _codes(_source_age_report(25))
    assert "source_stale_blocked" not in _codes(_source_age_report(72))  # age == 72h -> review
    assert "source_stale_blocked" in _codes(_source_age_report(72 + 1 / 60))
    assert _source_age_report(72 + 1 / 60).state == OVERALL_BLOCKED


def test_future_source_timestamp_blocks() -> None:
    payload = _bundle_payload()
    for source in payload["sources"]:
        source["retrieved_at"] = (GENERATED_AT + timedelta(hours=1)).isoformat()
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy))[0]
    assert "future_source_timestamp" in _codes(report)
    assert report.state == OVERALL_BLOCKED


# --- FX direction and publication age ---------------------------------------



def _bound_ecb_source(pair_model: str = "EUR-USD", *, rate: str = "1.08",
                      date_s: str = "2026-09-21") -> dict:
    """An official ECB reference-rate source whose single quote matches the
    180-d binding rules (rate, date, own publisher identity)."""
    return _evidence_tests.ecb_source_dict(
        pair_model=pair_model,
        date_s=date_s,
        rate=rate,
        retrieved_at=(GENERATED_AT - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        published_at=f"{date_s}T00:00:00Z",
    )


def _fx_report(rate: str, published_hours_ago: float | None, *, pair: str = "USD-EUR"):
    """USD-priced bundle with one FX fact bound to a supplied ECB reference
    quote; the mini baseline controls the pair. ``published_hours_ago`` must
    be a number: an ECB-backed fact without a publication date blocks, while
    the review-only undated case is exercised by
    test_fx_missing_publication_date_is_review."""
    payload = _bundle_payload()
    payload["run_id"] = "test-fx-policy-001"
    _usd_pricing(payload)  # fixture snapshot carries exactly these USD values
    # Keep the mini-baseline FX scope consistent with the proposed pair.
    if pair == "USD-EUR":
        fx = [{"base": "USD", "quote": "EUR", "rate": "1", "valid_from": "2026-09-20T00:00:00+00:00"}]
    else:
        fx = []
    published = GENERATED_AT - timedelta(hours=published_hours_ago)
    # The ECB snapshot is EUR-based: the supplied quote must equal the
    # proposed fact (EUR->USD) or its exact Decimal reciprocal (USD->EUR).
    if pair == "EUR-USD":
        xml_rate = rate
    else:
        xml_rate = str((Decimal(1) / Decimal(rate)).quantize(Decimal("0.000000001")))
    payload["fx"] = [_fx_facts_dict(rate, pair=pair, published_hours_ago=published_hours_ago)]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(
        _evidence_tests.ecb_source_dict(
            pair_model=pair,
            date_s=published.date().isoformat(),
            rate=xml_rate,
            retrieved_at=(GENERATED_AT - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            published_at=published.isoformat().replace("+00:00", "Z"),
        )
    )
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    baseline = _mini_usd_baseline(fx=fx)
    report, artifacts = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))
    return report, artifacts


def test_fx_move_exactly_3_percent_is_not_review() -> None:
    # baseline USD->EUR 1 -> proposed 1.03 is exactly the 0.03 threshold.
    report, _ = _fx_report("1.03", 1)
    assert "fx_moved_review" not in _codes(report)
    comparison = next(c for c in report.fx_comparisons if c["pair"] == "USD→EUR")
    assert comparison["state"] == "CHANGED"
    # The moved existing rate is a real update: no apply operation exists in
    # this version, so the run blocks even without the review finding.
    assert report.state == OVERALL_BLOCKED


def test_fx_move_above_3_percent_is_review() -> None:
    report, _ = _fx_report("1.030000001", 1)
    assert "fx_moved_review" in _codes(report)
    comparison = next(c for c in report.fx_comparisons if c["pair"] == "USD→EUR")
    assert comparison["state"] == "CHANGED_REVIEW"
    assert report.state == OVERALL_BLOCKED


def test_fx_eur_to_native_is_reciprocated_deterministically() -> None:
    """Supplying EUR->USD must yield a derived USD->EUR fact, never a
    silently relabeled pair (R2)."""
    report, fx_artifacts = _fx_report("1.08", 1, pair="EUR-USD")
    comparison = next(c for c in report.fx_comparisons if c["pair"] == "USD→EUR")
    assert comparison["derived"] is True
    assert comparison["source_pair"] == "EUR-USD"
    # 1 / 1.08 quantized to 9 dp with ROUND_HALF_UP
    assert comparison["proposed_rate"] == "0.925925926"
    # The executable artifact carries the canonical native->EUR row and the
    # derivation metadata (never the original EUR->USD quotation as a rate).
    from slaif_gateway.services.fx_import import parse_fx_import_json

    rows = parse_fx_import_json(fx_artifacts["fx-proposal.json"].decode("utf-8"))
    assert rows == [
        {
            "base_currency": "USD",
            "quote_currency": "EUR",
            "rate": "0.925925926",
            "source": "https://www.ecb.europa.eu/stats/eurofxref.html",
            "valid_from": "2026-09-20T00:00:00+00:00",
            "valid_until": None,
            "metadata": {
                "published_at": (GENERATED_AT - timedelta(hours=1)).isoformat(),
                "derived_reciprocal": True,
                "source_pair": "EUR-USD",
            },
            "notes": "",
        }
    ]
    assert "fx_missing_required_pair" not in _codes(report)
    assert "fx_contradictory_rates" not in _codes(report)


def test_fx_direct_and_reciprocal_must_agree() -> None:
    """Both a direct USD->EUR fact and its EUR->USD reciprocal bind to the
    one verified quote, and the FX gate confirms they agree. Under the
    180-d binding, a genuine direct/reciprocal disagreement can no longer
    reach the gate unbound - it blocks at evidence binding first (see the
    value-mismatch test below)."""
    payload = _bundle_payload()
    payload["run_id"] = "test-fx-agreement-001"
    _usd_pricing(payload)
    direct = _fx_facts_dict("0.925925926", pair="USD-EUR")
    reciprocal = _fx_facts_dict("1.08", pair="EUR-USD")
    # Both facts declare the one official quote source that verifies them.
    for fact in (direct, reciprocal):
        fact["provenance"]["sources"] = ["ecb|EUR-USD|ecb_reference_xml"]
    payload["fx"] = [direct, reciprocal]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(_bound_ecb_source())
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = validate_bundle(bundle, _mini_usd_baseline(), policy_from_document(bundle.policy))[0]
    assert "fx_contradictory_rates" not in _codes(report)
    assert "source_observations_contradict" not in _codes(report)
    comparison = next(c for c in report.fx_comparisons if c["pair"] == "USD\u2192EUR")
    assert comparison["state"] == "NEW"
    # Both facts are bound to the verified quote, with derivation recorded.
    assert len(report.source_evidence["fx_backed"]) == 2


def test_fx_ambiguous_active_rows_block() -> None:
    """Overlapping active FX rows with different rates can no longer both
    bind to one verified quote: the rate the quote does not verify fails
    evidence binding, so the run blocks before the gate could silently
    pick one of the overlapping rows."""
    payload = _bundle_payload()
    payload["run_id"] = "test-fx-ambiguous-001"
    _usd_pricing(payload)
    first = _fx_facts_dict("0.925925926", pair="USD-EUR")     # agrees with the 1.08 quote
    second = _fx_facts_dict("0.9", pair="USD-EUR")            # disagrees
    second["valid_from"] = "2026-09-21T06:00:00+00:00"  # overlapping window, new identity
    for fact in (first, second):
        fact["provenance"]["sources"] = ["ecb|EUR-USD|ecb_reference_xml"]
    payload["fx"] = [first, second]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(_bound_ecb_source())
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = validate_bundle(bundle, _mini_usd_baseline(), policy_from_document(bundle.policy))[0]
    assert "source_evidence_value_mismatch" in _codes(report)
    assert report.state == OVERALL_BLOCKED


def test_fx_publication_age_boundaries_are_calendar_days() -> None:
    assert "fx_stale_review" not in _codes(_fx_report("1", 3 * 24 - 1)[0])
    assert "fx_stale_review" in _codes(_fx_report("1", 3 * 24)[0])  # == 3 days -> review
    assert "fx_stale_blocked" not in _codes(_fx_report("1", 7 * 24)[0])  # == 7 days -> review
    assert "fx_stale_blocked" in _codes(_fx_report("1", 7 * 24 + 1)[0])
    assert _fx_report("1", 7 * 24 + 1)[0].state == OVERALL_BLOCKED


def test_fx_missing_publication_date_blocks() -> None:
    """An ECB-verified quote with an undated fact cannot bind: the missing
    publication date is a BLOCKER (fx_evidence_date_mismatch), never a
    review-only finding. Missing dates/quotes cannot be warning-only."""
    payload = _bundle_payload()
    payload["run_id"] = "test-fx-nodate-001"
    _usd_pricing(payload)
    # Truthful USD->EUR rate (reciprocal of the quote's 1.08) so the only
    # failure under test is the missing publication date.
    fact = _fx_facts_dict("0.925925926", pair="USD-EUR", published_hours_ago=None)
    fact["provenance"]["sources"] = ["ecb|EUR-USD|ecb_reference_xml"]
    payload["fx"] = [fact]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(_bound_ecb_source())
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    baseline = _mini_usd_baseline(
        fx=[{"base": "USD", "quote": "EUR", "rate": "0.925925926", "valid_from": "2026-09-20T00:00:00+00:00"}]
    )
    report = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))[0]
    assert "fx_evidence_date_mismatch" in _codes(report)
    assert report.state == OVERALL_BLOCKED
    assert report.source_evidence["fx_backed"] == []


def test_fx_future_publication_blocks() -> None:
    payload = _bundle_payload()
    payload["run_id"] = "test-fx-future-001"
    _usd_pricing(payload)
    facts = _fx_facts_dict("0.925925926", pair="USD-EUR")
    # Publication date in the future but equal to the quote's date, so the
    # fact binds and the FX gate's publication-age check fires.
    facts["published_at"] = (GENERATED_AT + timedelta(hours=1)).isoformat()
    facts["provenance"]["sources"] = ["ecb|EUR-USD|ecb_reference_xml"]
    payload["fx"] = [facts]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(_bound_ecb_source())
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = validate_bundle(bundle, _mini_usd_baseline(), policy_from_document(bundle.policy))[0]
    assert "fx_future_publication" in _codes(report)
    assert report.state == OVERALL_BLOCKED


def test_fx_provenance_may_not_borrow_a_model_source() -> None:
    payload = _bundle_payload()
    payload["run_id"] = "test-fx-provenance-001"
    _usd_pricing(payload)
    facts = _fx_facts_dict("0.925925926", pair="USD-EUR")
    # Declares the verified quote source AND borrows a model's OpenRouter
    # API reference: schema-shaped but semantically invalid for an FX
    # fact, so the fact binds and the gate's provenance rule still fires.
    facts["provenance"]["sources"] = [
        "ecb|EUR-USD|ecb_reference_xml",
        "openrouter|synthetic/stable-v1|openrouter_models_api",
    ]
    payload["fx"] = [facts]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(_bound_ecb_source())
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = validate_bundle(bundle, _mini_usd_baseline(), policy_from_document(bundle.policy))[0]
    assert "fx_provenance_invalid_reference" in _codes(report)
    assert report.state == OVERALL_BLOCKED


def test_all_eur_selected_pricing_marks_fx_na_not_missing() -> None:
    bundle = _bundle()
    report = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy))[0]
    fx_gate = next(gate for gate in report.gates if gate.name == "import.fx")
    assert fx_gate.evidence == "N/A"
    assert "EUR" in fx_gate.detail
    assert not any(warning.code == "fx_missing_required_pair" for warning in report.warnings)


def test_missing_required_pair_blocks_when_non_eur_pricing_selected() -> None:
    payload = _bundle_payload()
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            item["currency"] = "USD"
            for dimension in item["dimensions"]:
                dimension["currency"] = "USD"
                if dimension["name"] == "input":
                    dimension["value"] = "1.296"
                elif dimension["name"] == "output":
                    dimension["value"] = "4.32"
    payload["fx"] = []  # no FX fact at all
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    _evidence_tests.set_openrouter_evidence(
        payload, {**_evidence_tests.DEFAULT_PRICES, "synthetic/updated-v1": ("1.296", "4.32")}
    )
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    baseline = _mini_baseline(
        pricing={
            "synthetic/stable-v1": {"input": "0.5", "output": "2"},
            "synthetic/updated-v1": {"input": "1.296", "output": "4.32"},
        },
        currencies={"synthetic/updated-v1": "USD"},
    )
    report = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))[0]
    assert "fx_missing_required_pair" in _codes(report)
    assert report.state == OVERALL_BLOCKED


# --- unchanged/no-op versus blocked mutation --------------------------------

def test_true_no_change_refresh_is_ready() -> None:
    bundle = _bundle()
    report = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy))[0]
    assert report.state == OVERALL_READY
    assert report.counts["unchanged"] == 2
    assert report.counts["new"] == 1
    assert report.counts["changed"] == 0
    assert report.counts["ready"] == 3


def test_changed_row_alone_blocks_the_run() -> None:
    bundle = _bundle()  # updated-v1 proposes input 1.2
    baseline = _mini_baseline(
        pricing={
            "synthetic/stable-v1": {"input": "0.5", "output": "2"},
            "synthetic/updated-v1": {"input": "1.1", "output": "4"},
        }
    )
    report = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))[0]
    assert report.counts["changed"] == 1
    assert report.state == OVERALL_BLOCKED
    pricing_gate = next(g for g in report.import_gates if g.kind == "pricing")
    assert pricing_gate.excluded_mutations == 1


def test_new_row_is_create_ready_not_changed() -> None:
    bundle = _bundle()
    report = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy))[0]
    dispositions = {d.model: d.disposition for d in report.dispositions}
    assert dispositions["synthetic/new-v1"] == "NEW"
    assert dispositions["synthetic/stable-v1"] == "UNCHANGED"
    route_gate = next(g for g in report.import_gates if g.kind == "routes")
    assert route_gate.total_rows == 1  # only the new route enters the artifact
    assert route_gate.classifications == {"create": 1}


# --- R1: pairing by provider + upstream model + endpoint -------------------


def test_pricing_identity_matching_nothing_fails_closed() -> None:
    """A pricing row whose identity matches neither the route public name nor
    its upstream model cannot pair implicitly: under an explicit selection it
    is excluded as a counted out-of-scope fact (never silently adopted), and
    the real route loses its pricing and blocks as missing pricing."""
    payload = _bundle_payload()
    payload["run_id"] = "test-unpaired-pricing-001"
    for item in payload["pricing"]:
        if item["model"] == "synthetic/stable-v1":
            item["model"] = "synthetic/phantom-pricing-v1"
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = _review(bundle, _mini_baseline())
    codes = _codes(report)
    assert "missing_pricing" in codes
    assert report.state == OVERALL_BLOCKED
    assert report.counts["out_of_scope_facts"] >= 1  # phantom identity counted, never adopted
    dispositions = {(d.provider, d.model): d.disposition for d in report.dispositions}
    assert dispositions[("openrouter", "synthetic/stable-v1")] == "BLOCKED"


def test_public_alias_pairs_by_upstream_model() -> None:
    """Public aliases need not equal upstream IDs: the alias route's pricing
    row pairs through the route's upstream identity (no missing pairing), the
    route artifact keeps both names, and the already-existing upstream pricing
    rule is not duplicated into the create-only pricing artifact."""
    payload = _bundle_payload()
    payload["run_id"] = "test-alias-pairing-001"
    payload["selection"]["model_include"] = ["synthetic/alias-v1"]
    for section in ("models", "pricing"):
        for item in payload[section]:
            if item["model"] == "synthetic/stable-v1":
                item["model"] = "synthetic/alias-v1"
                item["provenance"]["sources"] = ["openrouter|synthetic/alias-v1|openrouter_models_api"]
    for item in payload["routes"]:
        if item["requested_model"] == "synthetic/stable-v1":
            item["requested_model"] = "synthetic/alias-v1"
            item["provenance"]["sources"] = ["openrouter|synthetic/alias-v1|openrouter_models_api"]
    # Keep the fixture snapshot bytes: they carry the upstream row
    # synthetic/stable-v1 that the alias binds through. Only the source's
    # model label is renamed to the public alias.
    for item in payload["sources"]:
        if item["model"] == "synthetic/stable-v1":
            item["model"] = "synthetic/alias-v1"
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, artifacts = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy))
    codes = _codes(report)
    assert not ({"missing_pricing", "missing_route", "route_upstream_contradiction"} & codes)
    assert report.state == OVERALL_READY
    assert report.counts["new"] == 1
    assert report.counts["changed"] == 0
    route_tsv = artifacts["routes-proposal.tsv"].decode("utf-8")
    assert "synthetic/alias-v1" in route_tsv
    assert "synthetic/stable-v1" in route_tsv  # upstream preserved on the route row
    pricing_tsv = artifacts["pricing-proposal.tsv"].decode("utf-8")
    assert "synthetic/alias-v1" not in pricing_tsv
    assert "synthetic/stable-v1" not in pricing_tsv  # existing upstream rule, no duplicate create


def test_same_model_id_is_independent_across_providers() -> None:
    """openai and openrouter rows sharing one model ID must pair within their
    own provider only: neither may borrow the other provider's route/pricing
    identity, and the shared ID does not create a phantom selected model."""
    payload = _bundle_payload()
    payload["run_id"] = "test-provider-collision-001"
    payload["selection"] = {
        "providers": ["openai", "openrouter"],
        "model_include": ["synthetic/stable-v1"],
    }
    or_model = next(m for m in payload["models"]
                    if m["model"] == "synthetic/stable-v1" and m["provider"] == "openrouter")
    or_route = next(r for r in payload["routes"]
                    if r["requested_model"] == "synthetic/stable-v1" and r["provider"] == "openrouter")
    or_pricing = next(pt for pt in payload["pricing"]
                      if pt["model"] == "synthetic/stable-v1" and pt["provider"] == "openrouter")
    or_source = next(s for s in payload["sources"]
                     if s["model"] == "synthetic/stable-v1" and s["provider"] == "openrouter")
    mirror_provenance = {
        "extractor": "fixture-deterministic/1.0",
        "extraction": "deterministic",
        "sources": ["openai|synthetic/stable-v1|operator_input"],
    }
    oi_model = copy.deepcopy(or_model)
    oi_model["provider"] = "openai"
    oi_model["display_name"] = "Synthetic Stable-V1 (openai mirror)"
    oi_model["provenance"] = copy.deepcopy(mirror_provenance)
    oi_route = copy.deepcopy(or_route)
    oi_route["provider"] = "openai"
    oi_route["provenance"] = copy.deepcopy(mirror_provenance)
    oi_pricing = copy.deepcopy(or_pricing)
    oi_pricing["provider"] = "openai"
    oi_pricing["provenance"] = copy.deepcopy(mirror_provenance)
    # Operator attestation bytes (digest-bound): review-only provenance,
    # never a verified provider fact. A synthetic ID could not parse from a
    # real OpenAI snapshot anyway, so no fabricated models-API source.
    attestation = b"operator attestation for openai mirror (review-only)"
    oi_source = copy.deepcopy(or_source)
    oi_source["provider"] = "openai"
    oi_source["source_kind"] = "operator_input"
    oi_source["url"] = "https://openai.com/docs/pricing"
    oi_source["published_at"] = None
    oi_source["content_sha256"] = hashlib.sha256(attestation).hexdigest()
    oi_source["evidence_b64"] = base64.b64encode(attestation).decode("ascii")
    payload["models"].append(oi_model)
    payload["routes"].append(oi_route)
    payload["pricing"].append(oi_pricing)
    payload["sources"].append(oi_source)
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = _review(bundle, _mini_baseline())
    codes = _codes(report)
    assert not (
        {"missing_pricing", "missing_route", "source_contradiction",
         "source_provenance_blocked", "route_upstream_contradiction"}
        & codes
    )
    # 180-d: the operator-attested mirror is never provider evidence: its
    # required facts cannot be verified, so the mirrored model blocks
    # (the old review-only NEW row was the bypass). The shared ID still
    # pairs within its own provider: the openrouter row is unchanged.
    assert report.state == OVERALL_BLOCKED
    assert "source_evidence_unsupported" in codes
    assert report.counts["new"] == 0
    assert report.counts["unchanged"] == 1
    assert report.counts["blocked"] == 1
    dispositions = {(d.provider, d.model): d.disposition for d in report.dispositions}
    assert dispositions[("openai", "synthetic/stable-v1")] == "BLOCKED"
    assert dispositions[("openrouter", "synthetic/stable-v1")] == "UNCHANGED"


def test_fabricated_host_urls_are_review_not_ready() -> None:
    """180-b R3 probe, 180-c semantics: replacing every source URL with a
    fabricated off-rule host must not remain READY. A syntactically safe URL
    is not an authoritative source: the (provider, source kind) host rule
    fails, so each source is REVIEW-classified. Evidence bytes still match
    their digests (the host rule, not the evidence, is the failure), but an
    off-host source cannot back a required fact, so the run blocks with
    source_evidence_unapproved."""
    payload = json.loads((FIXTURES / "bundle-first-install.json").read_text())
    payload["run_id"] = "test-fabricated-hosts-001"
    for item in payload["sources"]:
        item["url"] = "https://example.invalid/fabricated-pricing"
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = validate_bundle(bundle, None, policy_from_document(bundle.policy))[0]
    assert report.state == OVERALL_BLOCKED
    assert "source_provenance_review" in _codes(report)
    assert "source_evidence_unapproved" in _codes(report)
    assert report.sources, "source assessments must be present"
    for assessment in report.sources:
        assert assessment["classification"] == "REVIEW"
        assert assessment["evidence_state"] == "verified"
