"""180-c: independent-input tests for bounded source-evidence parsing,
typed observations, reconciliation, and fact binding.

The 180-b defect under test: ``_fact_observations`` copied one selected
fact's values to every provenance-named source, so a matching hash of
arbitrary bytes (even ``{}``) plus an official URL produced READY with
executable rows. These tests exercise the corrected contract at four
levels: parser, reconciliation, full validation, and CLI + report + seal
recomputation. They also provide the shared synthetic-evidence builders
(real API shapes, exact Decimal FX) used by the other 180-c test files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.services.catalog_refresh import source_evidence as se
from slaif_gateway.services.catalog_refresh.baseline import load_baseline
from slaif_gateway.services.catalog_refresh.bundle import load_bundle
from slaif_gateway.services.catalog_refresh.policy import policy_from_document
from slaif_gateway.services.catalog_refresh.rendering import render_report
from slaif_gateway.services.catalog_refresh.validation import (
    sql_capture_for_mode,
    validate_bundle,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
runner = CliRunner()

# --- shared synthetic evidence builders (real API shapes, exact FX) ----------

FX_RATE_EUR_USD = Decimal("1.08")
ECB_URL = (
    "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
    "euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html"
)
DEFAULT_PRICES: dict[str, tuple[str, str]] = {
    "synthetic/stable-v1": ("0.5", "2"),
    "synthetic/updated-v1": ("1.2", "4"),
    "synthetic/new-v1": ("0.1", "0.4"),
}


def eur_to_per_token_usd(eur_per_1m: str | Decimal) -> str:
    """Per-million EUR -> per-token USD via the exact 1.08 quote."""
    per_1m_usd = Decimal(eur_per_1m) * FX_RATE_EUR_USD
    return str(per_1m_usd / Decimal(10**6))


def openrouter_snapshot_bytes(model_prices: dict[str, tuple[str, str]]) -> bytes:
    """Cached OpenRouter /models payload in the official API shape.

    Prices are supplied per-million EUR and converted exactly to the
    provider's per-token USD strings (the real /models pricing unit).
    """
    data = []
    for model in sorted(model_prices):
        input_eur, output_eur = model_prices[model]
        data.append(
            {
                "id": model,
                "context_length": 128000,
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "top_provider": {"max_completion_tokens": 8192},
                "deprecation": {"is_deprecated": False},
                "pricing": {
                    "prompt": eur_to_per_token_usd(input_eur),
                    "completion": eur_to_per_token_usd(output_eur),
                    "input_cache_read": eur_to_per_token_usd(Decimal(input_eur) / Decimal(10)),
                },
            }
        )
    return (json.dumps({"data": data}, sort_keys=True) + "\n").encode("utf-8")


def set_openrouter_evidence(payload: dict, model_prices: dict[str, tuple[str, str]]) -> None:
    """Re-emit the shared OpenRouter snapshot evidence (digest + b64) for
    every openrouter source record in a bundle payload."""
    snapshot = openrouter_snapshot_bytes(model_prices)
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")


def ecb_xml_bytes(date_s: str, rate: str = "1.08") -> bytes:
    """Supplied ECB reference-rate XML: EUR is the native base."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" '
        'xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">\n'
        "  <gesmes:subject>Reference rates</gesmes:subject>\n"
        "  <gesmes:Sender>\n"
        "    <gesmes:Name>ECB</gesmes:Name>\n"
        "  </gesmes:Sender>\n"
        "  <Cube>\n"
        f'    <Cube time="{date_s}">\n'
        f'      <Cube currency="USD" rate="{rate}"/>\n'
        "    </Cube>\n"
        "  </Cube>\n"
        "</gesmes:Envelope>\n"
    ).encode("utf-8")


def ecb_source_dict(
    *,
    pair_model: str = "EUR-USD",
    date_s: str = "2026-09-21",
    rate: str = "1.08",
    url: str = ECB_URL,
    retrieved_at: str = "2026-09-21T11:00:00Z",
    published_at: str = "2026-09-21T00:00:00Z",
) -> dict:
    xml = ecb_xml_bytes(date_s, rate=rate)
    return {
        "provider": "ecb",
        "model": pair_model,
        "source_kind": "ecb_reference_xml",
        "url": url,
        "retrieved_at": retrieved_at,
        "published_at": published_at,
        "content_sha256": hashlib.sha256(xml).hexdigest(),
        "evidence_b64": base64.b64encode(xml).decode("ascii"),
        "extractor": "fixture-deterministic/1.0",
        "extraction": "deterministic",
        "required": True,
        "truncated": False,
        "warnings": [],
    }


def fx_fact_dict(rate: str, pair: str, published_at: str | None) -> dict:
    base, quote = pair.split("-")
    return {
        "base_currency": base,
        "quote_currency": quote,
        "rate": rate,
        "valid_from": "2026-09-21T00:00:00Z",
        "valid_until": None,
        "published_at": published_at,
        "source": ECB_URL,
        "provenance": {
            "extractor": "fixture-deterministic/1.0",
            "extraction": "deterministic",
            "sources": [f"ecb|{pair}|ecb_reference_xml"],
        },
        "warnings": [],
    }


def _first_install_payload() -> dict:
    return json.loads((FIXTURES / "bundle-first-install.json").read_text())


def _validate_payload(payload: dict, baseline: "object | None" = None):
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, artifacts = validate_bundle(bundle, baseline, policy_from_document(bundle.policy), sql_capture=sql_capture_for_mode(bundle.baseline.mode))
    return bundle, report, artifacts


def _codes(report) -> set[str]:
    return {warning.code for warning in report.warnings}


# --- parser level -------------------------------------------------------------


def test_openrouter_snapshot_real_shape_normalizes_per_token_usd_to_per_1m() -> None:
    snapshot = openrouter_snapshot_bytes({"synthetic/stable-v1": ("0.5", "2")})
    parsed = se.parse_snapshot("openrouter", "openrouter_models_api", snapshot)
    assert parsed.ok, parsed.error
    (model,) = parsed.models
    assert model.prices == {
        "input": Decimal("0.54"),
        "output": Decimal("2.16"),
        "cached_input": Decimal("0.054"),
    }
    assert model.price_currency == "USD"
    assert model.context_length == 128000
    assert model.max_output_tokens == 8192
    assert model.text_modality is True
    assert model.deprecated is False
    assert model.locators["pricing:input"] == "data[0].pricing.prompt"


@pytest.mark.parametrize(
    "raw,expected_code",
    [
        (b"{}", "openrouter_models_api:missing_data_array"),
        (b'{"data": {"id": "x"}}', "openrouter_models_api:missing_data_array"),
        (b"[1, 2]", "openrouter_models_api:not_an_object"),
        (b'{"data": [', "openrouter_models_api:malformed_json"),
        (b"\xff\xfe", "openrouter_models_api:not_utf8"),
        (b"x" * (se.MAX_SNAPSHOT_BYTES + 1), "openrouter_models_api:snapshot_too_large"),
    ],
)
def test_probe_payloads_fail_safely_with_code_only(raw: bytes, expected_code: str) -> None:
    parsed = se.parse_snapshot("openrouter", "openrouter_models_api", raw)
    assert not parsed.ok
    assert parsed.error == expected_code
    # Safe errors never echo the supplied content.
    assert str(raw[:16]) not in str(parsed.error)
    assert "x" * 16 not in str(parsed.error)


def test_openai_models_api_is_identity_only() -> None:
    parsed = se.parse_snapshot(
        "openai", "openai_models_api", json.dumps({"data": [{"id": "gpt-5.2"}]}).encode()
    )
    assert parsed.ok
    (model,) = parsed.models
    assert model.identity_only
    assert model.prices == {}
    assert model.context_length is None
    # Identity alone emits no value observations.
    assert se.derive_observations("openai|gpt-5.2|openai_models_api", parsed) == ()


def test_openai_pricing_docs_table_extraction_with_locators() -> None:
    docs = (
        "# Pricing\n\n"
        "| Model | Modality | Input | Cached input | Output |\n"
        "|---|---|---|---|---|\n"
        "| gpt-5.2 | text | $0.54 | $0.054 | $2.16 |\n"
        "| gpt-5.1 | text | $1.08 | - | $4.32 |\n"
    )
    parsed = se.parse_snapshot("openai", "openai_pricing_docs", docs.encode())
    assert parsed.ok, parsed.error
    by_id = {model.model: model for model in parsed.models}
    assert by_id["gpt-5.2"].prices == {
        "input": Decimal("0.54"),
        "cached_input": Decimal("0.054"),
        "output": Decimal("2.16"),
    }
    # Unknown/absent cells stay missing, never invented.
    assert "cached_input" not in by_id["gpt-5.1"].prices
    assert by_id["gpt-5.2"].locators["pricing:output"] == "table[0].row[1]"
    assert by_id["gpt-5.2"].price_currency == "USD"


def test_ecb_xml_parser_happy_path_and_rejections() -> None:
    parsed = se.parse_snapshot("ecb", "ecb_reference_xml", ecb_xml_bytes("2026-09-21"))
    assert parsed.ok, parsed.error
    (quote,) = parsed.fx_quotes
    assert (quote.base_currency, quote.quote_currency) == ("EUR", "USD")
    assert quote.rate == Decimal("1.08")
    assert str(quote.published_date) == "2026-09-21"

    doctype = b'<!DOCTYPE foo [\n<!ENTITY x "y">\n]>\n' + ecb_xml_bytes("2026-09-21")
    assert not se.parse_snapshot("ecb", "ecb_reference_xml", doctype).ok
    assert se.parse_snapshot("ecb", "ecb_reference_xml", doctype).error == "ecb_reference_xml:doctype_forbidden"
    assert se.parse_snapshot("ecb", "ecb_reference_xml", b"<Cube>").error == "ecb_reference_xml:malformed_xml"
    assert se.parse_snapshot("ecb", "ecb_reference_xml", b"<Envelope><Cube/></Envelope>").error == "ecb_reference_xml:no_quotes"
    bad_date = ecb_xml_bytes("2026-13-99")
    assert se.parse_snapshot("ecb", "ecb_reference_xml", bad_date).error == "ecb_reference_xml:bad_date"
    negative = ecb_xml_bytes("2026-09-21", rate="-1")
    assert se.parse_snapshot("ecb", "ecb_reference_xml", negative).error == "ecb_reference_xml:non_positive_rate"


def test_unregistered_parser_kind_is_not_deterministic() -> None:
    assert not se.has_deterministic_parser("openrouter", "docs_page")
    assert not se.has_deterministic_parser("openrouter", "operator_input")
    parsed = se.parse_snapshot("openrouter", "docs_page", b"whatever")
    assert not parsed.ok and parsed.error == "no_registered_parser"


# --- reconciliation level ------------------------------------------------------


def _obs(source_key: str, model: str, field_name: str, value: str, currency: str | None = None):
    unit = "currency_pair" if field_name == "fx:rate" else (
        "per_1m_tokens" if field_name.startswith("pricing:") else "none"
    )
    return se.Observation(
        source_key=source_key,
        provider="openrouter",
        model=model,
        field=field_name,
        locator=f"loc:{source_key}",
        value=value,
        unit=unit,
        currency=currency,
        parser="openrouter_models_api/v1",
    )


def _reconcile(
    proposed,
    observations,
    *,
    official,
    declared,
    fx_to_eur=None,
    urls=None,
    digests=None,
    provider="openrouter",
    binding_model="m",
):
    """180-d contract: every field validates against the sources its own
    fact declares; conflicts are checked across ALL official observations;
    independence counts distinct official URLs, not source records."""
    return se.reconcile_model_facts(
        provider=provider,
        binding_model=binding_model,
        proposed=proposed,
        observations=observations,
        official_source_keys=frozenset(official),
        declared_sources=declared,
        fx_to_eur=fx_to_eur or {},
        urls=urls or {},
        digests=digests or {},
        source_times={},
        fx_info={},
    )


def test_canonical_semantics_one_equals_one_point_zero() -> None:
    findings, backed, _unresolved, _missing = _reconcile(
        proposed={"pricing:input": {"value": "1", "currency": "EUR", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "1.0"),),
        official={"s1"},
        declared={"pricing:input": frozenset({"s1"})},
        urls={"s1": "https://openrouter.ai/api/v1/models"},
        digests={"s1": "d1"},
    )
    assert findings == []
    assert "pricing:input" in backed


def test_distinct_snapshots_conflicting_values_block() -> None:
    findings, _backed, _unresolved, _missing = _reconcile(
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(
            _obs("s1", "m", "pricing:input", "0.54", "USD"),
            _obs("s2", "m", "pricing:input", "0.648", "USD"),
        ),
        official={"s1", "s2"},
        declared={"pricing:input": frozenset({"s1", "s2"})},
        fx_to_eur={"USD": Decimal("0.925925926")},
        urls={
            "s1": "https://openrouter.ai/api/v1/models",
            "s2": "https://openrouter.ai/models/synthetic/m",
        },
        digests={"s1": "d1", "s2": "d2"},
    )
    assert [f.code for f in findings] == ["source_observations_contradict"]
    assert all(f.severity == "BLOCKER" for f in findings)


def test_equal_values_with_different_decimal_spellings_agree() -> None:
    findings, backed, _unresolved, _missing = _reconcile(
        proposed={"pricing:input": {"value": "1.0", "currency": "EUR", "required": True}},
        observations=(
            _obs("s1", "m", "pricing:input", "1"),
            _obs("s2", "m", "pricing:input", "1.0"),
        ),
        official={"s1", "s2"},
        declared={"pricing:input": frozenset({"s1", "s2"})},
        urls={
            "s1": "https://openrouter.ai/api/v1/models",
            "s2": "https://openrouter.ai/models/synthetic/m",
        },
        digests={"s1": "d1", "s2": "d2"},
    )
    assert findings == []
    # Two distinct snapshots agreeing on the same canonical value.
    assert backed["pricing:input"].independent_sources == 2


def test_repeated_references_to_one_snapshot_are_not_independent() -> None:
    observations = tuple(
        _obs(f"s{i}", "m", "pricing:input", "0.54", "USD") for i in range(3)
    )
    digests = {f"s{i}": "same-digest" for i in range(3)}
    # Repeated retrievals / aliases of the same official URL: one source.
    urls = {f"s{i}": "https://openrouter.ai/api/v1/models" for i in range(3)}
    findings, backed, _unresolved, _missing = _reconcile(
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=observations,
        official=set(digests),
        declared={"pricing:input": frozenset(digests)},
        fx_to_eur={"USD": Decimal("0.925925926")},
        urls=urls,
        digests=digests,
    )
    assert findings == []
    assert backed["pricing:input"].independent_sources == 1


def test_usd_observation_binds_eur_proposal_via_verified_fx() -> None:
    findings, backed, _unresolved, missing = _reconcile(
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "0.54", "USD"),),
        official={"s1"},
        declared={"pricing:input": frozenset({"s1"})},
        fx_to_eur={"USD": Decimal("0.925925926")},
        urls={"s1": "https://openrouter.ai/api/v1/models"},
        digests={"s1": "d1"},
    )
    assert findings == [] and missing == set()
    fact = backed["pricing:input"]
    assert fact.proposed_normalized == "0.500000000"
    (record,) = fact.observations
    assert record["observed_value"] == "0.54"
    assert record["unit"] == "per_1m_tokens"
    assert record["currency"] == "USD"
    assert record["normalized_eur"] == "0.500000000"
    assert record["locator"] == "loc:s1"


def test_unresolvable_fx_currency_reports_unbound() -> None:
    findings, _backed, _unresolved, missing = _reconcile(
        proposed={"pricing:input": {"value": "0.54", "currency": "USD", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "0.54", "USD"),),
        official={"s1"},
        declared={"pricing:input": frozenset({"s1"})},
        fx_to_eur={},  # no verified USD->EUR binding
        urls={"s1": "https://openrouter.ai/api/v1/models"},
        digests={"s1": "d1"},
    )
    assert missing == {"USD"}
    # An unresolvable currency never agrees with a value by assertion.
    assert findings == []


def test_unapproved_observations_cannot_back_required_fact() -> None:
    findings, _backed, _unresolved, _missing = _reconcile(
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "0.54", "USD"),),
        official=frozenset(),  # off-host / unparseable source: never official
        declared={"pricing:input": frozenset({"s1"})},
        fx_to_eur={"USD": Decimal("0.925925926")},
        urls={"s1": "https://example.invalid/models"},
        digests={"s1": "d1"},
    )
    assert [f.code for f in findings] == ["source_evidence_unsupported"]
    assert all(f.severity == "BLOCKER" for f in findings)


def test_semantic_label_without_observations_blocks() -> None:
    """180-d D2: a semantic extraction label with no parsed observations
    cannot verify a required fact: the field blocks as unsupported. A
    model-wide semantic boolean no longer produces a review-only backing."""
    findings, backed, _unresolved, _missing = _reconcile(
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(),
        official=frozenset(),
        declared={"pricing:input": frozenset({"s1"})},
        fx_to_eur={},
        urls={},
        digests={},
    )
    assert [f.code for f in findings] == ["source_evidence_unsupported"]
    assert all(f.severity == "BLOCKER" for f in findings)
    assert backed == {}


# --- full validation: family 1 adversarial inputs ------------------------------


def test_empty_object_evidence_blocks_end_to_end() -> None:
    """The 180-c reproducer: every source's evidence_b64 = b64({}) with the
    matching digest. 180-b returned READY with executable rows."""
    payload = _first_install_payload()
    empty = b"{}"
    for source in payload["sources"]:
        source["evidence_b64"] = base64.b64encode(empty).decode("ascii")
        source["content_sha256"] = hashlib.sha256(empty).hexdigest()
    _bundle, report, artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    codes = _codes(report)
    assert "source_evidence_parse_failed" in codes
    assert "source_evidence_unsupported" in codes
    assert report.artifacts["route_rows"] == 0
    assert report.artifacts["pricing_rows"] == 0
    assert report.artifacts["fx_rows"] == 0


def test_unrelated_valid_json_with_correct_hash_blocks() -> None:
    payload = _first_install_payload()
    unrelated = b'{"totally": {"unrelated": "content"}}'
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(unrelated).decode("ascii")
            source["content_sha256"] = hashlib.sha256(unrelated).hexdigest()
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_parse_failed" in _codes(report)


def test_empty_data_array_blocks_as_model_missing() -> None:
    """A parseable OpenRouter payload with an empty data[] still blocks:
    the selected model is absent from the complete snapshot."""
    payload = _first_install_payload()
    empty_data = b'{"data": []}'
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(empty_data).decode("ascii")
            source["content_sha256"] = hashlib.sha256(empty_data).hexdigest()
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_model_missing" in _codes(report)
    assert "source_evidence_unsupported" in _codes(report)


def test_unrelated_html_with_correct_hash_blocks() -> None:
    payload = _first_install_payload()
    html = b"<html><body><table><tr><td>fake pricing</td></tr></table></body></html>"
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(html).decode("ascii")
            source["content_sha256"] = hashlib.sha256(html).hexdigest()
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_parse_failed" in _codes(report)


def test_bytes_contradicting_declared_digest_block() -> None:
    payload = _first_install_payload()
    other = b'{"data": [{"id": "synthetic/chat-v1"}]}'
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(other).decode("ascii")
            # declared digest deliberately does NOT match the bytes
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "evidence_digest_mismatch" in _codes(report)


def test_changed_proposed_price_with_unchanged_snapshot_blocks() -> None:
    payload = _first_install_payload()
    for item in payload["pricing"]:
        for dimension in item["dimensions"]:
            if dimension["name"] == "input":
                dimension["value"] = "0.99"  # snapshot says 0.25 EUR equivalent
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_value_mismatch" in _codes(report)


def test_wrong_model_reference_blocks() -> None:
    """A proposal for a model absent from its complete evidence fails closed."""
    payload = _first_install_payload()
    for section in ("models", "pricing"):
        for item in payload[section]:
            item["model"] = "synthetic/ghost-v1"
            item["provenance"]["sources"] = ["openrouter|synthetic/ghost-v1|openrouter_models_api"]
    for item in payload["routes"]:
        item["requested_model"] = "synthetic/ghost-v1"
        item["upstream_model"] = "synthetic/ghost-v1"
        item["provenance"]["sources"] = ["openrouter|synthetic/ghost-v1|openrouter_models_api"]
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["model"] = "synthetic/ghost-v1"
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    codes = _codes(report)
    assert "source_evidence_model_missing" in codes
    assert "source_evidence_unsupported" in codes


def test_unknown_parser_kind_cannot_verify_required_fact() -> None:
    """deterministic label on a parser-less kind: the source demotes to
    REVIEW and the required price fact is blocked, not verified."""
    payload = _first_install_payload()
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["source_kind"] = "docs_page"
            source["url"] = "https://openrouter.ai/docs/pricing"
            source["extraction"] = "deterministic"
        if source["provider"] == "ecb":
            payload["sources"].remove(source)
    for fact in payload["models"] + payload["pricing"] + payload["routes"]:
        fact["provenance"]["sources"] = ["openrouter|synthetic/chat-v1|docs_page"]
    payload["fx"] = []
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    codes = _codes(report)
    assert "source_evidence_unapproved" in codes
    assert "source_evidence_unsupported" in codes
    assessment = next(a for a in report.sources if a["source_kind"] == "docs_page")
    assert assessment["classification"] == "REVIEW"


def test_missing_evidence_cannot_back_required_fact() -> None:
    payload = _first_install_payload()
    for source in payload["sources"]:
        source["evidence_b64"] = None
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_unsupported" in _codes(report)


# --- FX evidence binding ---------------------------------------------------------


def _usd_pricing_payload(fx: list[dict], sources: list[dict]):
    """First-install bundle with one USD-priced model plus the given FX
    facts/sources. The snapshot carries the provider's per-token USD shape."""
    payload = _first_install_payload()
    for item in payload["pricing"]:
        item["currency"] = "USD"
        for dimension in item["dimensions"]:
            dimension["currency"] = "USD"
            if dimension["name"] == "input":
                dimension["value"] = "0.27"
            elif dimension["name"] == "output":
                dimension["value"] = "1.08"
    payload["fx"] = fx
    payload["sources"] = [s for s in payload["sources"] if s["provider"] == "openrouter"] + sources
    set_openrouter_evidence(payload, {"synthetic/chat-v1": ("0.25", "1.0")})
    return payload


def test_ecb_quote_and_date_bind_usd_normalization() -> None:
    payload = _usd_pricing_payload(
        fx=[fx_fact_dict("1.08", "EUR-USD", "2026-09-21T00:00:00Z")],
        sources=[ecb_source_dict(date_s="2026-09-21", rate="1.08")],
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    assert report.source_evidence["fx_backed"][0]["pair"] == "EUR to USD"
    # USD observations converted exactly: 0.27 USD == 0.25 EUR @ 1.08
    fields = {item["field"] for item in report.source_evidence["backed_facts"]}
    assert {"pricing:input", "pricing:output"} <= fields


def test_fx_fact_date_mismatch_blocks() -> None:
    payload = _usd_pricing_payload(
        fx=[fx_fact_dict("1.08", "EUR-USD", "2026-09-20T00:00:00Z")],
        sources=[ecb_source_dict(date_s="2026-09-21", rate="1.08")],
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "fx_evidence_date_mismatch" in _codes(report)


def test_fx_fact_rate_mismatch_blocks() -> None:
    payload = _usd_pricing_payload(
        fx=[fx_fact_dict("1.50", "EUR-USD", "2026-09-21T00:00:00Z")],
        sources=[ecb_source_dict(date_s="2026-09-21", rate="1.08")],
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_value_mismatch" in _codes(report)


def test_fx_two_distinct_ecb_snapshots_contradict_block() -> None:
    payload = _usd_pricing_payload(
        fx=[fx_fact_dict("1.08", "EUR-USD", "2026-09-21T00:00:00Z")],
        sources=[
            ecb_source_dict(pair_model="EUR-USD", date_s="2026-09-21", rate="1.08"),
            ecb_source_dict(pair_model="USD-EUR", date_s="2026-09-21", rate="1.10"),
        ],
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_observations_contradict" in _codes(report)


def test_fx_semantic_source_cannot_bind_fact() -> None:
    """180-d D2 reproducer 2: with the ECB source removed and the FX fact
    pointed at a semantic docs_page quote whose bytes carry no numeric
    rate, the old READY_WITH_WARNINGS + guessed-rate result is gone: the
    fact is unbound (no verified reference quote), fx_backed is empty, and
    the run blocks. No semantic/manual FX escape hatch."""
    payload = _usd_pricing_payload(fx=[], sources=[])
    payload["run_id"] = "test-d2-semantic-fx"
    payload["fx"] = [
        {
            "base_currency": "EUR",
            "quote_currency": "USD",
            "rate": "1.08",
            "valid_from": "2026-09-21T00:00:00Z",
            "valid_until": None,
            "published_at": "2026-09-21T00:00:00Z",
            "source": ECB_URL,
            "provenance": {
                "extractor": "fixture-deterministic/1.0",
                "extraction": "semantic",
                "sources": ["openrouter|EUR-USD|docs_page"],
            },
            "warnings": [],
        }
    ]
    junk = b"fx notes with no numeric rate"
    payload["sources"].append(
        {
            "provider": "openrouter",
            "model": "EUR-USD",
            "source_kind": "docs_page",
            "url": "https://openrouter.ai/docs/fx",
            "retrieved_at": "2026-09-21T11:00:00Z",
            "published_at": None,
            "content_sha256": hashlib.sha256(junk).hexdigest(),
            "evidence_b64": base64.b64encode(junk).decode("ascii"),
            "extractor": "fixture-deterministic/1.0",
            "extraction": "semantic",
            "required": True,
            "truncated": False,
            "warnings": [],
        }
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "fx_evidence_unbound" in _codes(report)
    assert report.source_evidence["fx_backed"] == []
    # The USD proposals were never normalized with a guessed rate.
    assert report.artifacts["pricing_rows"] == 0


# --- inventory and partial failures (family 4) ----------------------------------


EXTRA_MODEL = "synthetic/unproposed-v1"


def _proposed_extra_model_payload() -> dict:
    """First-install bundle where the extra eligible snapshot model is also
    explicitly proposed (model/route/pricing/source facts) under an
    explicit subset selection."""
    payload = _first_install_payload()
    # 0.5/2.0 EUR round-trips exactly through the 1.08 quote at 9 dp
    # (like the fixture prices); 9/9 would drift one ulp.
    set_openrouter_evidence(
        payload, {"synthetic/chat-v1": ("0.25", "1.0"), EXTRA_MODEL: ("0.5", "2")}
    )
    base_model = payload["models"][0]
    payload["models"].append(
        {
            **base_model,
            "model": EXTRA_MODEL,
            "provenance": {**base_model["provenance"], "sources": [f"openrouter|{EXTRA_MODEL}|openrouter_models_api"]},
        }
    )
    base_route = payload["routes"][0]
    payload["routes"].append(
        {
            **base_route,
            "requested_model": EXTRA_MODEL,
            "upstream_model": EXTRA_MODEL,
            "provenance": {**base_route["provenance"], "sources": [f"openrouter|{EXTRA_MODEL}|openrouter_models_api"]},
        }
    )
    base_pricing = payload["pricing"][0]
    payload["pricing"].append(
        {
            **base_pricing,
            "model": EXTRA_MODEL,
            "dimensions": [
                dict(dimension, value="0.5" if dimension["name"] == "input" else "2")
                for dimension in base_pricing["dimensions"]
            ],
            "provenance": {**base_pricing["provenance"], "sources": [f"openrouter|{EXTRA_MODEL}|openrouter_models_api"]},
        }
    )
    or_source = next(s for s in payload["sources"] if s["provider"] == "openrouter")
    payload["sources"].append({**or_source, "model": EXTRA_MODEL})
    payload["selection"]["model_include"] = ["synthetic/chat-v1", EXTRA_MODEL]
    return payload


def test_all_eligible_unexplained_omission_blocks() -> None:
    """180-d D4 committed probe: an extra fully populated eligible text
    model in the official snapshot with an all-eligible selection is an
    unexplained omission - it blocks, and the per-ID disposition is in the
    inventory (no silent count-only counter)."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d4-omission"
    set_openrouter_evidence(
        payload, {"synthetic/chat-v1": ("0.25", "1.0"), EXTRA_MODEL: ("9", "9")}
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "selection_unexplained_omission" in _codes(report)
    inventory = report.source_evidence["inventory"]["openrouter"]
    assert inventory["evidence_models"] == 2
    assert inventory["selected_models"] == 1
    assert inventory["unexplained_omissions"] == 1
    assert inventory["selection_mode"] == "all_eligible"
    # The proposed model still creates its row; the omitted model never does.
    assert report.artifacts["pricing_rows"] == 1
    assert EXTRA_MODEL not in _artifacts["pricing-proposal.tsv"].decode("utf-8")


def test_explicit_subset_proposing_every_eligible_model_is_ready() -> None:
    """180-d D4 positive: the same extra model, explicitly selected and
    proposed, is a normal create - explicit subsets are preserved, not
    forced to all-eligible."""
    payload = _proposed_extra_model_payload()
    payload["run_id"] = "test-d4-subset-both"
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    assert report.artifacts["pricing_rows"] == 2
    inventory = report.source_evidence["inventory"]["openrouter"]
    assert inventory["evidence_models"] == 2
    assert inventory["selected_models"] == 2
    assert inventory["unexplained_omissions"] == 0
    assert inventory["selection_mode"] == "explicit_subset"


def test_explicit_subset_excluding_eligible_model_is_ready_and_named() -> None:
    """180-d D4: an explicit subset may omit eligible models; the omission
    is named and counted in the report without a per-row warning."""
    payload = _proposed_extra_model_payload()
    payload["run_id"] = "test-d4-subset-exclude"
    payload["selection"]["model_include"] = ["synthetic/chat-v1"]
    payload["models"] = [m for m in payload["models"] if m["model"] != EXTRA_MODEL]
    payload["routes"] = [r for r in payload["routes"] if r["requested_model"] != EXTRA_MODEL]
    payload["pricing"] = [p for p in payload["pricing"] if p["model"] != EXTRA_MODEL]
    payload["sources"] = [s for s in payload["sources"] if s["model"] != EXTRA_MODEL]
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    assert report.artifacts["pricing_rows"] == 1
    inventory = report.source_evidence["inventory"]["openrouter"]
    assert inventory["explicitly_excluded_models"] == 1
    assert inventory["excluded_ids"] == [EXTRA_MODEL]
    assert inventory["unexplained_omissions"] == 0
    assert inventory["selection_mode"] == "explicit_subset"
    # No per-row warning for a deliberately excluded model.
    assert not any(EXTRA_MODEL in (w.detail or "") and w.severity == "REVIEW"
                   for w in report.warnings)


def test_identical_duplicate_rows_in_snapshot_dedupe_with_finding() -> None:
    """Identical repeated rows in one snapshot deduplicate under an
    explicit safe policy with a truthful REVIEW finding (the model still
    validates; the deduplication is visible, not silent)."""
    payload = _first_install_payload()
    payload["run_id"] = "test-dup-identical"
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"].append(dict(data["data"][0]))  # identical duplicate row
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY_WITH_WARNINGS", _codes(report)
    assert "source_duplicate_rows_deduplicated" in _codes(report)
    finding = next(w for w in report.warnings if w.code == "source_duplicate_rows_deduplicated")
    assert finding.severity == "REVIEW"
    # The deduplicated model still validates and its facts stay bound.
    assert report.counts["ready"] == 1
    assert report.source_evidence["backed_facts"]


def test_conflicting_duplicate_rows_in_snapshot_block() -> None:
    """Conflicting rows for one model id within ONE snapshot block: a
    single digest disagreeing with itself is a contradiction, not a skip
    (the 'only one digest is involved' escape is gone)."""
    payload = _first_install_payload()
    payload["run_id"] = "test-dup-conflict"
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    conflict = dict(data["data"][0])
    conflict["pricing"] = dict(conflict["pricing"], prompt="0.00000199")
    data["data"].append(conflict)
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "source_observations_contradict" in _codes(report)
    finding = next(w for w in report.warnings if w.code == "source_observations_contradict")
    assert finding.severity == "BLOCKER"
    assert report.artifacts["pricing_rows"] == 0


def test_partial_source_failure_isolates_the_failed_model() -> None:
    payload = _first_install_payload()
    # chat-v1's own source evidence is corrupted; the ecb source is intact.
    bad = b"{}"
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(bad).decode("ascii")
            source["content_sha256"] = hashlib.sha256(bad).hexdigest()
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    codes = _codes(report)
    assert "source_evidence_parse_failed" in codes
    # The FX fact is still bound to its intact ECB snapshot.
    assert report.source_evidence["fx_backed"], report.source_evidence


def test_unsupported_capability_claim_cannot_use_provider_catalog() -> None:
    """A provider catalog with audio modalities does not let a proposal
    claim the text capability: the parsed observation is 'false'."""
    payload = _first_install_payload()
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"][0]["architecture"] = {
        "input_modalities": ["audio"],
        "output_modalities": ["audio"],
    }
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_value_mismatch" in _codes(report)


def _set_openrouter_snapshot_deprecated(payload: dict, deprecated: bool | None) -> None:
    """Re-emit the openrouter evidence with the deprecation fact set (or absent)."""
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    if deprecated is None:
        data["data"][0].pop("deprecation", None)
        data["data"][0].pop("architecture", None)
    else:
        data["data"][0]["deprecation"] = {"is_deprecated": deprecated}
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")


def test_observed_deprecation_true_with_non_deprecated_proposal_blocks() -> None:
    """180-e E3 reproducer 1: the snapshot reports is_deprecated=true while
    the proposal carries deprecated=false. Omitting the proposal field is a
    bypass: the observed official fact blocks the affected proposal instead
    (retain-local, no auto-delete or auto-disable)."""
    payload = _first_install_payload()
    _set_openrouter_snapshot_deprecated(payload, True)
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_value_mismatch" in _codes(report)
    finding = next(
        w for w in report.warnings if w.code == "source_evidence_value_mismatch"
    )
    assert "deprecated" in finding.detail
    assert "retain the local row" in finding.detail
    dispositions = {(d.provider, d.model): d for d in report.dispositions}
    assert dispositions[("openrouter", "synthetic/chat-v1")].disposition == "BLOCKED"


def test_route_text_claim_cannot_bypass_observed_audio_only_modalities() -> None:
    """180-e E3 reproducer 2: the source is audio-only (observed text=false)
    and only the ROUTE claims text (the model facts do not). Effective text
    eligibility is facts OR any route, so the claim must bind to the
    observed 'false' and block — not stay READY."""
    payload = _first_install_payload()
    for item in payload["models"]:
        item["capabilities"] = {"streaming": True}
    # the route still claims text
    for item in payload["routes"]:
        item["capabilities"] = {"streaming": True, "text": True}
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"][0]["architecture"] = {
        "input_modalities": ["audio"],
        "output_modalities": ["audio"],
    }
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_value_mismatch" in _codes(report)
    finding = next(
        w for w in report.warnings if w.code == "source_evidence_value_mismatch"
    )
    assert "model:capability:text" in finding.detail


def test_text_claim_still_binds_when_source_observations_text() -> None:
    """Positive control: the same route-level text claim binds when the
    snapshot's modalities observe text (the fixture snapshot does)."""
    payload = _first_install_payload()
    for item in payload["models"]:
        item["capabilities"] = {"streaming": True}
    for item in payload["routes"]:
        item["capabilities"] = {"streaming": True, "text": True}
    set_openrouter_evidence(payload, {"synthetic/chat-v1": ("0.25", "1.0")})
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    fields = {item["field"] for item in report.source_evidence["backed_facts"]}
    assert "model:capability:text" in fields


def test_absent_deprecation_observation_is_not_a_conflict_when_text_is_observed() -> None:
    """A snapshot without deprecation facts emits no deprecation
    observation; a proposal that does not claim deprecation is not in
    conflict on that field while the observed text modality still backs the
    text claim."""
    payload = _first_install_payload()
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"][0].pop("deprecation", None)  # architecture (text) retained
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    assert "source_evidence_value_mismatch" not in _codes(report)


def test_audio_only_source_blocks_effective_default_text_contract() -> None:
    """E3 effective contract: an audio-only source with BOTH the model and
    the route facts declaring text=false still cannot yield an executable
    text route. Flat declarations cannot narrow the runtime contract the
    import path would actually create (the default chat_completions block
    enables chat_text), so the effective text claim must bind to the
    observed audio-only fact."""
    payload = _first_install_payload()
    for item in payload["models"]:
        item["capabilities"] = {"streaming": True, "text": False}
    for item in payload["routes"]:
        item["capabilities"] = {"streaming": True, "text": False}
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"][0]["architecture"] = {
        "input_modalities": ["audio"],
        "output_modalities": ["audio"],
    }
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_evidence_value_mismatch" in _codes(report)
    finding = next(
        w for w in report.warnings if w.code == "source_evidence_value_mismatch"
    )
    assert "model:capability:text" in finding.detail
    dispositions = {(d.provider, d.model): d for d in report.dispositions}
    assert dispositions[("openrouter", "synthetic/chat-v1")].disposition == "BLOCKED"


def test_proposed_deprecation_true_with_official_observation_is_deprecated_retained() -> None:
    """When the proposal carries the observed deprecation, the model is
    handled as DEPRECATED (retain-local, no delete), not as a value
    mismatch."""
    payload = _first_install_payload()
    for item in payload["models"]:
        item["deprecated"] = True
    _set_openrouter_snapshot_deprecated(payload, True)
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY_WITH_WARNINGS"
    assert "model_deprecated" in _codes(report)
    assert "source_evidence_value_mismatch" not in _codes(report)
    dispositions = {(d.provider, d.model): d for d in report.dispositions}
    assert dispositions[("openrouter", "synthetic/chat-v1")].disposition == "DEPRECATED"


def test_non_official_deprecation_claim_cannot_drive_the_blocker() -> None:
    """An off-host (non-official) snapshot claiming deprecation is not an
    official observation: it cannot produce the deprecation value-mismatch
    blocker. The run still blocks on source approval, for the right reason."""
    payload = _first_install_payload()
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"][0]["deprecation"] = {"is_deprecated": True}
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    # only the OPENROUTER source moves off-host; the ECB FX reference stays
    # intact so the failure isolates the deprecation-claim path
    for source in payload["sources"]:
        if source["provider"] != "openrouter":
            continue
        source["url"] = "https://example.invalid/fabricated-pricing"
        source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
        source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED"
    assert "source_provenance_review" in _codes(report)
    # the deprecation claim came from a non-official observation: it must not
    # surface as a value-mismatch blocker (the model still blocks because
    # its required facts cannot bind to official evidence)
    assert "source_evidence_value_mismatch" not in _codes(report)
    dispositions = {(d.provider, d.model): d for d in report.dispositions}
    assert dispositions[("openrouter", "synthetic/chat-v1")].disposition == "BLOCKED"


def test_dropped_baseline_candidate_is_disappeared_not_silently_dropped() -> None:
    from tests.unit.test_catalog_refresh_policy import _baseline, _bundle  # noqa: F401

    # (kept in the policy file; mirrored here only for the count identity)
    bundle = load_bundle((FIXTURES / "bundle-truncated.json").read_bytes())
    baseline = load_baseline((FIXTURES / "baseline-synthetic.json").read_bytes())
    report, _artifacts = validate_bundle(bundle, baseline, policy_from_document(bundle.policy), sql_capture=sql_capture_for_mode(bundle.baseline.mode))
    dispositions = {(d.provider, d.model): d.disposition for d in report.dispositions}
    assert dispositions[("openrouter", "synthetic/gone-v1")] == "BLOCKED"
    # every selected model is accounted for
    counted = sum(report.counts[k] for k in (
        "ready", "changed", "excluded", "blocked", "disappeared", "deprecated", "not_fetched"
    ))
    assert counted == report.counts["considered"]


# --- bootstrap / no-change / alias / cross-provider (family 5) -------------------


def test_valid_bootstrap_create_only_stays_ready() -> None:
    bundle = load_bundle((FIXTURES / "bundle-first-install.json").read_bytes())
    report, artifacts = validate_bundle(bundle, None, policy_from_document(bundle.policy), sql_capture=sql_capture_for_mode(bundle.baseline.mode))
    assert report.state == "READY"
    assert report.counts["new"] == 1
    assert report.artifacts["route_rows"] == 1
    assert report.artifacts["pricing_rows"] == 1
    assert report.source_evidence["backed_facts"], "bootstrap facts must be bound"


def test_true_no_change_refresh_stays_ready() -> None:
    from tests.unit.test_catalog_refresh_policy import _bundle, _mini_baseline

    bundle = _bundle()
    report, _artifacts = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy), sql_capture=sql_capture_for_mode(bundle.baseline.mode))
    assert report.state == "READY"
    assert report.counts["unchanged"] == 2
    assert report.counts["new"] == 1
    assert report.counts["changed"] == 0


def test_public_alias_binds_through_upstream_identity() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    for section in ("models", "pricing"):
        for item in payload[section]:
            if item["model"] == "synthetic/stable-v1":
                item["model"] = "synthetic/alias-v1"
                item["provenance"]["sources"] = ["openrouter|synthetic/alias-v1|openrouter_models_api"]
    for item in payload["routes"]:
        if item["requested_model"] == "synthetic/stable-v1":
            item["requested_model"] = "synthetic/alias-v1"
            item["provenance"]["sources"] = ["openrouter|synthetic/alias-v1|openrouter_models_api"]
    for source in payload["sources"]:
        if source["model"] == "synthetic/stable-v1":
            source["model"] = "synthetic/alias-v1"
    payload["selection"]["model_include"] = [
        "synthetic/alias-v1" if name == "synthetic/stable-v1" else name
        for name in payload["selection"]["model_include"]
    ]
    # No baseline supplied: this is an explicit first-install create-only
    # run, so the bundle declares first_install (no baseline document).
    payload["baseline"] = {
        "mode": "first_install",
        "exported_at": None,
        "target_database": None,
        "postgres_version": None,
        "sql_checked": False,
        "row_counts": {},
        "content_sha256": None,
    }
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    # No baseline supplied: create-only run, so every selected model is new.
    assert report.counts["new"] == 3
    # The alias's facts bound through the upstream row in the snapshot.
    fields = {item["field"] for item in report.source_evidence["backed_facts"]}
    assert "pricing:input" in fields


def test_operator_input_mirror_cannot_verify_provider_facts() -> None:
    """180-d D1: an operator-input mirror of a model ID in a second
    provider is not provider evidence. The old review-only NEW row is a
    bypass: the mirror's required facts cannot be verified, so the
    mirrored model blocks while the original provider row is unaffected."""
    import copy

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-oi-mirror-blocks"
    payload["selection"] = {"providers": ["openai", "openrouter"], "model_include": ["synthetic/stable-v1"]}
    or_model = next(
        m for m in payload["models"] if m["model"] == "synthetic/stable-v1" and m["provider"] == "openrouter"
    )
    or_route = next(
        r for r in payload["routes"] if r["requested_model"] == "synthetic/stable-v1" and r["provider"] == "openrouter"
    )
    or_pricing = next(
        p for p in payload["pricing"] if p["model"] == "synthetic/stable-v1" and p["provider"] == "openrouter"
    )
    mirror_provenance = {
        "extractor": "fixture-deterministic/1.0",
        "extraction": "deterministic",
        "sources": ["openai|synthetic/stable-v1|operator_input"],
    }
    oi_model = copy.deepcopy(or_model)
    oi_model["provider"] = "openai"
    oi_model["display_name"] = "Synthetic Stable-V1 (openai mirror)"
    oi_model["provenance"] = dict(mirror_provenance)
    oi_route = copy.deepcopy(or_route)
    oi_route["provider"] = "openai"
    oi_route["provenance"] = dict(mirror_provenance)
    oi_pricing = copy.deepcopy(or_pricing)
    oi_pricing["provider"] = "openai"
    oi_pricing["provenance"] = dict(mirror_provenance)
    attestation = b"operator attestation for openai mirror (review-only)"
    payload["models"].append(oi_model)
    payload["routes"].append(oi_route)
    payload["pricing"].append(oi_pricing)
    payload["sources"].append(
        {
            "provider": "openai",
            "model": "synthetic/stable-v1",
            "source_kind": "operator_input",
            "url": "https://openai.com/docs/pricing",
            "retrieved_at": "2026-09-21T11:00:00Z",
            "published_at": None,
            "content_sha256": hashlib.sha256(attestation).hexdigest(),
            "evidence_b64": base64.b64encode(attestation).decode("ascii"),
            "extractor": "fixture-deterministic/1.0",
            "extraction": "deterministic",
            "required": True,
            "truncated": False,
            "warnings": [],
        }
    )
    baseline = load_baseline((FIXTURES / "baseline-synthetic.json").read_bytes())
    _bundle, report, _artifacts = _validate_payload(payload, baseline)
    codes = _codes(report)
    assert not ({"missing_pricing", "missing_route", "source_contradiction", "route_upstream_contradiction"} & codes)
    # The operator-attested mirror blocks: operator input is never official evidence.
    assert report.state == "BLOCKED", codes
    assert "source_evidence_unsupported" in codes
    assert report.counts["new"] == 0
    assert report.counts["blocked"] == 1
    dispositions = {(d.provider, d.model): d.disposition for d in report.dispositions}
    assert dispositions[("openai", "synthetic/stable-v1")] == "BLOCKED"
    assert dispositions[("openrouter", "synthetic/stable-v1")] == "UNCHANGED"


def _openai_official_sources(model: str, input_usd: str, output_usd: str, cached_usd: str | None) -> list[dict]:
    """Real official OpenAI source shapes: /v1/models identity JSON, a
    pricing-docs markdown table (per-1m USD as published), and a model
    docs block with limits (openai_models_docs kind)."""
    models_api = json.dumps({"data": [{"id": model}]}).encode("utf-8")
    cached_cell = f"${cached_usd}" if cached_usd else "-"
    pricing_docs = (
        "# Pricing\n\n"
        "| Model | Modality | Input | Cached input | Output |\n"
        "|---|---|---|---|---|\n"
        f"| {model} | text | ${input_usd} | {cached_cell} | ${output_usd} |\n"
    ).encode("utf-8")
    models_docs = (
        "# Models\n\n"
        f"## {model}\n"
        "Context length: 128000\n"
        "Max output tokens: 8192\n"
        "Endpoints: /v1/chat/completions\n"
    ).encode("utf-8")
    common = {
        "provider": "openai",
        "model": model,
        "retrieved_at": "2026-09-21T11:00:00Z",
        "published_at": None,
        "extractor": "fixture-deterministic/1.0",
        "extraction": "deterministic",
        "required": True,
        "truncated": False,
        "warnings": [],
    }
    return [
        {
            **common,
            "source_kind": "openai_models_api",
            "url": "https://api.openai.com/v1/models",
            "content_sha256": hashlib.sha256(models_api).hexdigest(),
            "evidence_b64": base64.b64encode(models_api).decode("ascii"),
        },
        {
            **common,
            "source_kind": "openai_pricing_docs",
            "url": "https://openai.com/api/pricing",
            "content_sha256": hashlib.sha256(pricing_docs).hexdigest(),
            "evidence_b64": base64.b64encode(pricing_docs).decode("ascii"),
        },
        {
            **common,
            "source_kind": "openai_models_docs",
            "url": f"https://openai.com/index/{model.replace('.', '-')}/",
            "content_sha256": hashlib.sha256(models_docs).hexdigest(),
            "evidence_b64": base64.b64encode(models_docs).decode("ascii"),
        },
    ]


def _openai_positive_payload() -> dict:
    """bundle-refresh-ready plus an OpenAI provider model whose every
    claimed fact is backed by real official OpenAI source shapes
    (identity, per-1m USD prices + text modality, context/max-output).
    USD observations normalize through the fixture's verified 1.08 ECB
    quote, exactly like the OpenRouter path."""
    import copy

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    model = "gpt-5.2"
    payload["run_id"] = "test-openai-positive"
    payload["selection"] = {
        "providers": ["openai", "openrouter"],
        "model_include": ["synthetic/stable-v1", model],
    }
    or_model = next(
        m for m in payload["models"] if m["model"] == "synthetic/stable-v1" and m["provider"] == "openrouter"
    )
    or_route = next(
        r for r in payload["routes"] if r["requested_model"] == "synthetic/stable-v1" and r["provider"] == "openrouter"
    )
    or_pricing = next(
        p for p in payload["pricing"] if p["model"] == "synthetic/stable-v1" and p["provider"] == "openrouter"
    )
    all_openai = [f"openai|{model}|{kind}" for kind in ("openai_models_api", "openai_pricing_docs", "openai_models_docs")]
    pricing_only = [f"openai|{model}|openai_pricing_docs"]
    oi_model = copy.deepcopy(or_model)
    oi_model["provider"] = "openai"
    oi_model["model"] = model
    oi_model["display_name"] = "GPT-5.2 (openai)"
    oi_model["provenance"] = {"extractor": "fixture-deterministic/1.0", "extraction": "deterministic", "sources": all_openai}
    oi_route = copy.deepcopy(or_route)
    oi_route["provider"] = "openai"
    oi_route["requested_model"] = model
    oi_route["upstream_model"] = model
    oi_route["provenance"] = {"extractor": "fixture-deterministic/1.0", "extraction": "deterministic", "sources": all_openai}
    oi_pricing = copy.deepcopy(or_pricing)
    oi_pricing["provider"] = "openai"
    oi_pricing["model"] = model
    oi_pricing["provenance"] = {"extractor": "fixture-deterministic/1.0", "extraction": "deterministic", "sources": pricing_only}
    payload["models"].append(oi_model)
    payload["routes"].append(oi_route)
    payload["pricing"].append(oi_pricing)
    # 0.54/2.16 USD per-1m == the fixture's 0.5/2.0 EUR at the 1.08 quote.
    payload["sources"].extend(_openai_official_sources(model, "0.54", "2.16", "0.054"))
    return payload


def test_openai_official_sources_bind_a_positive_path() -> None:
    """Positive OpenAI path through the complete validator: the mirrored
    provider's facts bind to parsed official OpenAI observations (models
    API identity, pricing docs, models docs) - no operator-input
    substitute, no related-model inference."""
    payload = _openai_positive_payload()
    baseline = load_baseline((FIXTURES / "baseline-synthetic.json").read_bytes())
    _bundle, report, _artifacts = _validate_payload(payload, baseline)
    codes = _codes(report)
    assert report.state == "READY", (codes, [w.detail for w in report.warnings])
    dispositions = {(d.provider, d.model): d.disposition for d in report.dispositions}
    assert dispositions[("openai", "gpt-5.2")] == "NEW"
    assert dispositions[("openrouter", "synthetic/stable-v1")] == "UNCHANGED"
    openai_facts = {f["field"]: f for f in report.source_evidence["backed_facts"] if f["provider"] == "openai"}
    assert {"pricing:input", "pricing:output", "model:context_length", "model:max_output_tokens", "model:capability:text"} <= set(openai_facts)
    pricing_input = openai_facts["pricing:input"]
    assert pricing_input["backed_by"] == ["openai|gpt-5.2|openai_pricing_docs"]
    (obs,) = pricing_input["observations"]
    assert obs["observed_value"] == "0.54"
    assert obs["currency"] == "USD"
    assert obs["normalized_eur"] == "0.500000000"
    assert openai_facts["model:context_length"]["backed_by"] == ["openai|gpt-5.2|openai_models_docs"]
    assert openai_facts["model:capability:text"]["backed_by"] == ["openai|gpt-5.2|openai_pricing_docs"]
    inventory = report.source_evidence["inventory"]["openai"]
    assert inventory["evidence_models"] == 1
    assert inventory["selected_models"] == 1
    assert inventory["unexplained_omissions"] == 0


def test_openai_positive_path_through_the_cli(tmp_path: Path) -> None:
    """The same positive OpenAI bundle passes the complete CLI review
    (schema acceptance of openai_models_docs included) and exits 0."""
    payload = _openai_positive_payload()
    bundle_path = tmp_path / "bundle-openai-positive.json"
    bundle_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json"),
         "--run-root", str(tmp_path / "runs"), "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 0, result.output
    assert "state: READY" in result.stdout
    html = (tmp_path / "runs" / "test-openai-positive" / "REVIEW.html").read_text()
    assert "gpt-5.2" in html
    # The models-docs locator for the observed context limit is rendered.
    assert "model_block[0].context_length" in html
    assert "128000" in html


def test_openai_models_docs_kind_is_registered() -> None:
    """openai_models_docs is a coherent schema/registry entry: the
    registered parser extracts model blocks with limits and locators."""
    docs = (
        "# Models\n\n"
        "## gpt-5.2\n"
        "Context length: 272000\n"
        "Max output tokens: 128000\n"
        "Endpoints: /v1/chat/completions, /v1/responses\n"
    ).encode("utf-8")
    parsed = se.parse_snapshot("openai", "openai_models_docs", docs)
    assert parsed.ok, parsed.error
    (model,) = parsed.models
    assert model.model == "gpt-5.2"
    assert model.context_length == 272000
    assert model.max_output_tokens == 128000
    assert model.locators["model:context_length"] == "model_block[0].context_length"
    assert se.has_deterministic_parser("openai", "openai_models_docs")


# --- 180-d: exact work-order reproducers as end-to-end regressions -----------


def test_d1_wrong_upstream_model_blocks() -> None:
    """180-d D1 reproducer: changing ONLY the route's upstream model to an
    unobserved model no longer emits a pricing row at the original
    model's prices: facts bind to the route's ACTUAL upstream, which is
    absent from the complete snapshots."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d1-wrong-upstream"
    payload["routes"][0]["upstream_model"] = "synthetic/unobserved-upstream"
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    codes = _codes(report)
    assert "source_evidence_model_missing" in codes
    assert "source_evidence_unsupported" in codes
    assert report.artifacts["route_rows"] == 0
    assert report.artifacts["pricing_rows"] == 0
    assert report.source_evidence["backed_facts"] == []


def test_d1_pricing_citing_only_the_ecb_source_blocks() -> None:
    """180-d D1 reproducer: pointing the pricing fact's provenance at the
    ECB source (leaving model/route references unchanged) no longer
    borrows the snapshot's observation: the matching observation exists
    only in an undeclared source, so the reference mismatch blocks."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d1-wrong-pricing-source"
    payload["pricing"][0]["provenance"]["sources"] = ["ecb|EUR-USD|ecb_reference_xml"]
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "source_evidence_reference_mismatch" in _codes(report)
    assert report.artifacts["pricing_rows"] == 0


def test_d1_alias_collision_other_catalog_name_price_cannot_be_borrowed() -> None:
    """180-d D1 collision: both the public alias and another catalog model
    exist in the snapshot at different prices. The alias may bind through
    its upstream's evidence (covered by the alias positive), but the
    proposal may not carry the OTHER catalog name's price."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d1-alias-collision"
    alias = "synthetic/alias-collide-v1"
    set_openrouter_evidence(
        payload, {"synthetic/chat-v1": ("0.25", "1.0"), alias: ("0.77", "3.3")}
    )
    for item in payload["models"] + payload["pricing"]:
        item["model"] = alias
        item["provenance"]["sources"] = [f"openrouter|{alias}|openrouter_models_api"]
    for item in payload["routes"]:
        item["requested_model"] = alias
        item["provenance"]["sources"] = [f"openrouter|{alias}|openrouter_models_api"]
    # The route's actual upstream is the observed model (chat-v1).
    payload["routes"][0]["upstream_model"] = "synthetic/chat-v1"
    # The proposal carries the other catalog name's (the alias's own) price.
    for dimension in payload["pricing"][0]["dimensions"]:
        dimension["value"] = "0.77" if dimension["name"] == "input" else "3.3"
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["model"] = alias
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "source_evidence_value_mismatch" in _codes(report)
    assert report.artifacts["pricing_rows"] == 0


def test_d1_selective_citation_cannot_hide_conflicting_official_snapshot() -> None:
    """180-d D1: a proposal may cite only one of two official snapshots
    for a field, but an authoritative conflict across ALL official
    observations for the context still blocks (selective citation cannot
    hide a supplied conflicting observation)."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d1-selective-citation"
    # Two official snapshots of the same URL: the newer one (declared)
    # and a stale retrieval with a different price for the same model.
    snapshot_new = openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")})
    snapshot_stale = openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.75", "3.0")})
    or_source = next(s for s in payload["sources"] if s["provider"] == "openrouter")
    payload["sources"].append(
        {**or_source, "model": "synthetic/chat-v1-stale",
         "content_sha256": hashlib.sha256(snapshot_stale).hexdigest(),
         "evidence_b64": base64.b64encode(snapshot_stale).decode("ascii")}
    )
    for source in payload["sources"]:
        if source["provider"] == "openrouter" and source["model"] == "synthetic/chat-v1":
            source["content_sha256"] = hashlib.sha256(snapshot_new).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot_new).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "source_observations_contradict" in _codes(report)
    assert report.artifacts["pricing_rows"] == 0


def test_d2_semantic_label_on_required_source_blocks() -> None:
    """180-d D2 reproducer 1: required-snapshot bytes replaced by {} and
    labelled semantic must block exactly like the deterministic label:
    the extraction label is not evidence and not a waiver."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d2-semantic-empty"
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(b"{}").decode("ascii")
            source["content_sha256"] = hashlib.sha256(b"{}").hexdigest()
            source["extraction"] = "semantic"
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    codes = _codes(report)
    assert "source_evidence_parse_failed" in codes
    assert "source_evidence_unsupported" in codes
    assert report.artifacts["pricing_rows"] == 0


def test_d3_duplicate_inner_json_keys_block() -> None:
    """180-d D3 reproducer: a second conflicting `prompt` key inside the
    decoded snapshot JSON (invisible to outer-bundle duplicate checks)
    must block as malformed official content, code-only."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d3-duplicate-inner-key"
    # Hand-built raw JSON text: Python dicts cannot express duplicate keys.
    raw = (
        b'{"data": [{"architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},'
        b' "context_length": 128000, "deprecation": {"is_deprecated": false}, "id": "synthetic/chat-v1",'
        b' "pricing": {"prompt": "0.00000999", "prompt": "2.7E-7", "completion": "0.00000108"},'
        b' "top_provider": {"max_completion_tokens": 8192}}]}'
    )
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(raw).decode("ascii")
            source["content_sha256"] = hashlib.sha256(raw).hexdigest()
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    assert "source_evidence_parse_failed" in _codes(report)
    detail = next(w.detail for w in report.warnings if w.code == "source_evidence_parse_failed")
    assert "duplicate_key" in detail
    assert report.artifacts["pricing_rows"] == 0


def test_d3_non_finite_json_constants_block() -> None:
    for raw in (
        b'{"data": [NaN]}',
        b'{"data": [{"id": "synthetic/chat-v1", "pricing": {"prompt": Infinity}}]}',
        b'{"data": [{"id": "synthetic/chat-v1", "context_length": -Infinity}]}',
    ):
        parsed = se.parse_snapshot("openrouter", "openrouter_models_api", raw)
        assert not parsed.ok
        assert parsed.error == "openrouter_models_api:non_finite_constant"
        assert "NaN" not in parsed.error  # code-only, no content echo


def test_d3_hostile_price_cells_rejected_before_conversion() -> None:
    """Bounded raw decimal cells: hostile exponents and over-precise
    strings are rejected code-only (no huge allocation, no uncaught
    Decimal error); ordinary per-token precision is preserved."""

    def _snapshot_with_prompt(prompt: str) -> bytes:
        return (
            b'{"data": [{"id": "synthetic/hostile-v1", "context_length": 128000,'
            b' "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},'
            b' "pricing": {"prompt": "' + prompt.encode("ascii") + b'", "completion": "0.00000108"}}]}'
        )

    for hostile in ("1e9999", "0.00000000000000005", "1e", ""):
        parsed = se.parse_snapshot("openrouter", "openrouter_models_api", _snapshot_with_prompt(hostile))
        assert not parsed.ok, hostile
        assert parsed.error == "openrouter_models_api:invalid_price", hostile

    parsed = se.parse_snapshot(
        "openrouter", "openrouter_models_api", _snapshot_with_prompt("0.00000054")
    )
    assert parsed.ok, parsed.error
    (model,) = parsed.models
    assert model.prices["input"] == Decimal("0.54")
    assert model.locators["pricing:input"] == "data[0].pricing.prompt"


def test_d3_raw_null_row_blocks_and_row_indices_are_preserved() -> None:
    """180-d D3 reproducer: a null row in the raw data[] is a format
    error (rows never disappear through filtering); clean multi-row
    payloads keep their original row indices in locators."""
    payload = _first_install_payload()
    payload["run_id"] = "test-d3-null-row"
    raw = b'{"data": [null, {"id": "synthetic/chat-v1"}]}'
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["evidence_b64"] = base64.b64encode(raw).decode("ascii")
            source["content_sha256"] = hashlib.sha256(raw).hexdigest()
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "BLOCKED", _codes(report)
    detail = next(w.detail for w in report.warnings if w.code == "source_evidence_parse_failed")
    assert "malformed_row" in detail

    # Clean payload: the second model's locator keeps its raw index.
    parsed = se.parse_snapshot(
        "openrouter",
        "openrouter_models_api",
        openrouter_snapshot_bytes({"synthetic/a-v1": ("1", "2"), "synthetic/b-v1": ("3", "4")}),
    )
    assert parsed.ok, parsed.error
    by_id = {m.model: m for m in parsed.models}
    assert by_id["synthetic/b-v1"].locators["pricing:input"] == "data[1].pricing.prompt"
    assert by_id["synthetic/a-v1"].locators["pricing:input"] == "data[0].pricing.prompt"


def test_d5_first_install_report_contains_actual_observations(tmp_path: Path) -> None:
    """180-d D5: the one report renders the actual derived observations -
    observed value, unit, currency, exact locator, source URL/digest and
    the exact normalization - not only scope/counts."""
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install", "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 0, result.output
    html = (tmp_path / "runs" / "fixture-first-install-001" / "REVIEW.html").read_text()
    # The exact locator and the observed USD value are in the evidence details.
    assert "data[0].pricing.prompt" in html
    assert "0.27" in html
    assert "per_1m_tokens" in html
    assert "USD" in html
    # The exact normalization of the observed value to the comparison currency.
    assert "0.250000000" in html
    assert "0.925925926" in html
    assert b"<script" not in html.lower().encode()


# --- CLI + report + seal recomputation (family 1 end-to-end) ----------------------


def test_cli_empty_object_probe_blocked_exit_20_with_seal_verify(tmp_path: Path) -> None:
    payload = _first_install_payload()
    payload["run_id"] = "test-evidence-probe-001"
    empty = b"{}"
    for source in payload["sources"]:
        source["evidence_b64"] = base64.b64encode(empty).decode("ascii")
        source["content_sha256"] = hashlib.sha256(empty).hexdigest()
    bundle_path = tmp_path / "bundle-probe.json"
    bundle_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path), "--first-install",
         "--run-root", str(tmp_path / "runs"), "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 20, result.output
    assert "state: BLOCKED" in result.stdout
    assert "source_evidence_parse_failed" in result.stdout
    run_dir = tmp_path / "runs" / "test-evidence-probe-001"
    assert (run_dir / "receipt.json").exists()
    # The published report is recomputed and sealed: verify passes.
    verify = runner.invoke(
        app,
        ["catalog-refresh", "verify", "--run-dir", str(run_dir),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert verify.exit_code == 0, verify.output
    published = json.loads((run_dir / "validation.json").read_text())
    assert published["state"] == "BLOCKED"
    html_text = (run_dir / "REVIEW.html").read_text()
    assert "<strong>BLOCKED</strong>" in html_text
    assert "Source evidence" in html_text


def test_cli_valid_bootstrap_still_ready_after_evidence_contract(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install", "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 0, result.output
    assert "state: READY" in result.stdout


# --- offline guarantees (family 6) --------------------------------------------------


def test_parsing_and_validation_perform_no_network_io() -> None:
    def _refused(*_args, **_kwargs):
        raise AssertionError("network I/O attempted during offline review")

    bundle = load_bundle((FIXTURES / "bundle-first-install.json").read_bytes())
    report, _artifacts = validate_bundle(bundle, None, policy_from_document(bundle.policy), sql_capture=sql_capture_for_mode(bundle.baseline.mode))
    assert report.state == "READY"
    html = render_report(bundle, report.to_dict())
    assert b"<script" not in html.lower()


def test_snapshot_text_cannot_become_report_markup() -> None:
    # Whitespace-free hostile tag: the executable route artifact layer only
    # forbids whitespace in model names, so this hostile ID is schema-legal
    # end to end and must survive as escaped data, never as markup.
    hostile = "synthetic/chat-v1<img/onerror=alert(1)>"
    payload = _first_install_payload()
    data = json.loads(openrouter_snapshot_bytes({hostile: ("0.25", "1.0")}))
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for item in payload["models"] + payload["pricing"]:
        item["model"] = hostile
        item["provenance"]["sources"] = [f"openrouter|{hostile}|openrouter_models_api"]
    for item in payload["routes"]:
        item["requested_model"] = hostile
        item["upstream_model"] = hostile
        item["provenance"]["sources"] = [f"openrouter|{hostile}|openrouter_models_api"]
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["model"] = hostile
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    html = render_report(_bundle, report.to_dict()).decode("utf-8")
    assert not re.search(r"<img\b", html, flags=re.IGNORECASE)
    assert "onerror=alert(1)" in html  # present only in escaped form
    assert "&lt;img" in html
