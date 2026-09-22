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
from slaif_gateway.services.catalog_refresh.validation import validate_bundle

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
    report, artifacts = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))
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


def test_canonical_semantics_one_equals_one_point_zero() -> None:
    findings, backed, _unresolved, _missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "1", "currency": "EUR", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "1.0"),),
        official_source_keys=frozenset({"s1"}),
        semantic_provenance=False,
        fx_to_eur={},
        digests={"s1": "d1"},
    )
    assert findings == []
    assert "pricing:input" in backed


def test_distinct_snapshots_conflicting_values_block() -> None:
    findings, _backed, _unresolved, _missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "0.54", "currency": "USD", "required": True}},
        observations=(
            _obs("s1", "m", "pricing:input", "0.54"),
            _obs("s2", "m", "pricing:input", "0.648"),
        ),
        official_source_keys=frozenset({"s1", "s2"}),
        semantic_provenance=False,
        fx_to_eur={},
        digests={"s1": "d1", "s2": "d2"},
    )
    assert [f.code for f in findings] == ["source_observations_contradict"]


def test_equal_values_with_different_decimal_spellings_agree() -> None:
    findings, backed, _unresolved, _missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "1.0", "currency": "EUR", "required": True}},
        observations=(
            _obs("s1", "m", "pricing:input", "1"),
            _obs("s2", "m", "pricing:input", "1.0"),
        ),
        official_source_keys=frozenset({"s1", "s2"}),
        semantic_provenance=False,
        fx_to_eur={},
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
    findings, backed, _unresolved, _missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=observations,
        official_source_keys=frozenset(digests),
        semantic_provenance=False,
        fx_to_eur={"USD": Decimal("0.925925926")},
        digests=digests,
    )
    assert findings == []
    assert backed["pricing:input"].independent_sources == 1


def test_usd_observation_binds_eur_proposal_via_verified_fx() -> None:
    findings, backed, _unresolved, missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "0.54", "USD"),),
        official_source_keys=frozenset({"s1"}),
        semantic_provenance=False,
        fx_to_eur={"USD": Decimal("0.925925926")},
        digests={"s1": "d1"},
    )
    assert findings == [] and missing == set()
    assert "pricing:input" in backed


def test_unresolvable_fx_currency_reports_unbound() -> None:
    findings, _backed, _unresolved, missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "0.54", "currency": "USD", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "0.54", "USD"),),
        official_source_keys=frozenset({"s1"}),
        semantic_provenance=False,
        fx_to_eur={},
        digests={"s1": "d1"},
    )
    assert missing == {"USD"}


def test_unapproved_observations_cannot_back_required_fact() -> None:
    findings, _backed, _unresolved, _missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(_obs("s1", "m", "pricing:input", "0.54", "USD"),),
        official_source_keys=frozenset(),  # off-host / unparseable source
        semantic_provenance=False,
        fx_to_eur={"USD": Decimal("0.925925926")},
        digests={"s1": "d1"},
    )
    assert [f.code for f in findings] == ["source_evidence_unapproved"]


def test_semantic_provenance_is_review_only_never_verified() -> None:
    findings, backed, _unresolved, _missing = se.reconcile_model_facts(
        provider="openrouter",
        model="m",
        upstream_model=None,
        proposed={"pricing:input": {"value": "0.5", "currency": "EUR", "required": True}},
        observations=(),
        official_source_keys=frozenset(),
        semantic_provenance=True,
        fx_to_eur={},
        digests={},
    )
    assert [f.code for f in findings] == ["source_evidence_semantic_only"]
    assert "pricing:input" not in backed


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


def test_fx_semantic_source_is_review_only() -> None:
    """An FX fact cited to a non-ECB docs source never verifies: the run is
    at least READY_WITH_WARNINGS with the semantic-only finding."""
    payload = _usd_pricing_payload(fx=[], sources=[])
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
    junk = b"fx notes"
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
    assert report.state == "READY_WITH_WARNINGS"
    assert "fx_evidence_semantic_only" in _codes(report)


# --- inventory and partial failures (family 4) ----------------------------------


def test_inventory_counts_unproposed_candidates() -> None:
    payload = _first_install_payload()
    # The snapshot also lists a model the selection does not propose.
    set_openrouter_evidence(
        payload, {"synthetic/chat-v1": ("0.25", "1.0"), "synthetic/unproposed-v1": ("9", "9")}
    )
    _bundle, report, _artifacts = _validate_payload(payload)
    inventory = report.source_evidence["inventory"]["openrouter"]
    assert inventory["evidence_models"] == 2
    assert inventory["selected_models"] == 1
    assert inventory["unproposed_candidates"] == 1
    # Counting an unproposed candidate is not a finding on its own.
    assert report.state == "READY"


def test_duplicate_model_id_in_snapshot_is_review_not_ready_clean() -> None:
    payload = _first_install_payload()
    data = json.loads(openrouter_snapshot_bytes({"synthetic/chat-v1": ("0.25", "1.0")}))
    data["data"].append(dict(data["data"][0]))  # identical duplicate row
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in payload["sources"]:
        if source["provider"] == "openrouter":
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY_WITH_WARNINGS"
    assert "source_duplicate_model_id" in _codes(report)


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


def test_dropped_baseline_candidate_is_disappeared_not_silently_dropped() -> None:
    from tests.unit.test_catalog_refresh_policy import _baseline, _bundle  # noqa: F401

    # (kept in the policy file; mirrored here only for the count identity)
    bundle = load_bundle((FIXTURES / "bundle-truncated.json").read_bytes())
    baseline = load_baseline((FIXTURES / "baseline-synthetic.json").read_bytes())
    report, _artifacts = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))
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
    report, artifacts = validate_bundle(bundle, None, policy_from_document(bundle.policy))
    assert report.state == "READY"
    assert report.counts["new"] == 1
    assert report.artifacts["route_rows"] == 1
    assert report.artifacts["pricing_rows"] == 1
    assert report.source_evidence["backed_facts"], "bootstrap facts must be bound"


def test_true_no_change_refresh_stays_ready() -> None:
    from tests.unit.test_catalog_refresh_policy import _bundle, _mini_baseline

    bundle = _bundle()
    report, _artifacts = validate_bundle(bundle, _mini_baseline(), policy_from_document(bundle.policy))
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
    _bundle, report, _artifacts = _validate_payload(payload)
    assert report.state == "READY", _codes(report)
    # No baseline supplied: create-only run, so every selected model is new.
    assert report.counts["new"] == 3
    # The alias's facts bound through the upstream row in the snapshot.
    fields = {item["field"] for item in report.source_evidence["backed_facts"]}
    assert "pricing:input" in fields


def test_same_model_id_is_independent_across_providers() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
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
    import copy

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
    # The operator-attested mirror is review-only, never verified.
    assert report.state == "READY_WITH_WARNINGS"
    assert "source_evidence_semantic_only" in codes
    dispositions = {(d.provider, d.model): d.disposition for d in report.dispositions}
    assert dispositions[("openai", "synthetic/stable-v1")] == "NEW"
    assert dispositions[("openrouter", "synthetic/stable-v1")] == "UNCHANGED"


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
    report, _artifacts = validate_bundle(bundle, None, policy_from_document(bundle.policy))
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
