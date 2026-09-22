"""REVIEW.html rendering: determinism, escaping, offline scope, and layout."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from pathlib import Path

from slaif_gateway.schemas.catalog_refresh import (
    BaselineCounts,
    BaselineDocument,
    BaselinePricingRow,
    BaselineProviderRow,
    BaselineRouteRow,
    BaselineTarget,
)
import test_catalog_refresh_source_evidence as _evidence_tests

from slaif_gateway.services.catalog_refresh.baseline import canonical_baseline_content, load_baseline
from slaif_gateway.services.catalog_refresh.bundle import load_bundle
from slaif_gateway.services.catalog_refresh.policy import policy_from_document
from slaif_gateway.services.catalog_refresh.rendering import (
    build_manifest,
    render_report,
    safe_href,
)
from slaif_gateway.services.catalog_refresh.validation import (
    OVERALL_BLOCKED,
    OVERALL_READY,
    OVERALL_READY_WITH_WARNINGS,
    validate_bundle,
    validation_json_bytes,
)
from slaif_gateway.cli.catalog_refresh import _minimal_blocked_html

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"


def _bundle(name: str):
    return load_bundle((FIXTURES / name).read_bytes())


def _baseline():
    return load_baseline((FIXTURES / "baseline-synthetic.json").read_bytes())


def _report_for(bundle, baseline):
    report, _ = validate_bundle(bundle, baseline, policy_from_document(bundle.policy))
    return report


def test_render_is_deterministic_and_byte_stable() -> None:
    bundle = _bundle("bundle-refresh-ready.json")
    report = _report_for(bundle, _baseline())
    first = render_report(bundle, report.to_dict())
    again = render_report(bundle, copy.deepcopy(report.to_dict()))
    assert first == again
    assert validation_json_bytes(report) == validation_json_bytes(_report_for(bundle, _baseline()))


def test_safe_href_allowlist() -> None:
    assert safe_href("https://openrouter.ai/models") is not None
    assert safe_href("http://example.test") is not None
    assert safe_href("javascript:alert(1)") is None
    assert safe_href("data:text/html,hi") is None
    assert safe_href("https://user:pw@example.test/") is None
    assert safe_href("") is None


def _assert_no_external_or_executable_resources(html_text: str) -> None:
    """Real tags only: data payloads are escaped, so they cannot form markup.

    Attribute checks therefore look at actual tags, and CSS constraints are
    checked inside the <style> block where they can take effect.
    """
    lowered = html_text.lower()
    for tag in ("script", "link", "img", "iframe", "form", "object", "embed", "video", "audio"):
        assert not re.search(rf"<{tag}\b", lowered), f"forbidden real tag <{tag}>"
    assert not re.search(r"<[a-z][^>]*\ssrc=", lowered), "real tag carries src="
    assert not re.search(r"<[a-z][^>]*\son\w+=", lowered), "real tag carries an on* event attribute"
    style_block = re.search(r"<style>(.*?)</style>", html_text, flags=re.DOTALL)
    assert style_block is not None
    assert "@import" not in style_block.group(1)
    assert "url(" not in style_block.group(1)
    for href in re.findall(r"href='([^']+)'", html_text):
        assert href.startswith(("http://", "https://")), f"unsafe href {href!r}"


def test_first_screen_contains_required_decision_facts() -> None:
    bundle = _bundle("bundle-first-install.json")
    report = _report_for(bundle, None)
    assert report.state == OVERALL_READY
    html_text = render_report(bundle, report.to_dict()).decode("utf-8")
    assert html_text.startswith("<!DOCTYPE html>")
    assert "<h1>SLAIF catalog refresh review</h1>" in html_text
    assert "fixture-first-install-001" in html_text
    # State and why, with blocker/review counts, on the first screen.
    assert "<strong>READY</strong>" in html_text
    assert "Why this state" in html_text
    assert "Blockers" in html_text
    assert "Review findings" in html_text
    assert "Selected scope" in html_text
    assert "Baseline" in html_text
    assert "NOT_RUN" in html_text
    # Compact scope/baseline/plan/FX/gates/counts all above the details.
    assert "Per-provider summary" in html_text
    assert "Execution plan (create-only)" in html_text
    assert "FX (current vs proposed, native → EUR)" in html_text
    assert "Gate checklist" in html_text
    assert "Counts (recomputed)" in html_text
    assert "What changed" in html_text
    assert "Run identity (expanded)" in html_text
    # Product language: no internal objective numbers anywhere in the report.
    import re as _re

    assert not _re.search(r"objective\s+\d+", html_text, flags=_re.IGNORECASE)
    assert "live source retrieval is unavailable in this version" in html_text
    _assert_no_external_or_executable_resources(html_text)


def test_first_screen_blocks_are_visually_blocked() -> None:
    bundle = _bundle("bundle-blocked.json")
    report = _report_for(bundle, _baseline())
    html_text = render_report(bundle, report.to_dict()).decode("utf-8")
    assert "<strong>BLOCKED</strong>" in html_text
    assert "state-blocked" in html_text
    assert "At least one execution plan is BLOCKED" in html_text
    assert "currency_inconsistency" in html_text
    assert "missing_required_dimension" in html_text


def test_source_strings_are_escaped_and_event_attributes_cannot_inject() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-escape-001"
    payload["notes"] = (
        "</script><script>alert(1)</script>"
        "<img src=x onerror=alert(2)>"
        "<svg/onload=alert(3)>"
        "javascript:alert(4)"
    )
    for item in payload["models"]:
        item["display_name"] = '<b onclick="xss()">Synthetic <script>x</script></b>'
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = _report_for(bundle, _baseline())
    html_text = render_report(bundle, report.to_dict()).decode("utf-8")

    # Raw tags must never survive escaping; the escaped forms must be present.
    assert not re.search(r"<script\b", html_text, flags=re.IGNORECASE)
    assert not re.search(r"<img\b", html_text, flags=re.IGNORECASE)
    assert not re.search(r"<svg\b", html_text, flags=re.IGNORECASE)
    assert not re.search(r"<b\b", html_text, flags=re.IGNORECASE)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    assert "&lt;img src=x onerror=alert(2)&gt;" in html_text
    assert "&lt;svg/onload=alert(3)&gt;" in html_text
    assert "&lt;b onclick=&quot;xss()&quot;&gt;" in html_text
    # No link may use a dangerous scheme (javascript:/data: payloads stay inert text).
    assert not re.search(r"href='[^']*(javascript|data):", html_text, flags=re.IGNORECASE)
    _assert_no_external_or_executable_resources(html_text)


def test_unchanged_only_plan_is_truthful_no_changes() -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-no-changes-001"
    payload["selection"]["model_include"] = ["synthetic/stable-v1"]
    payload["models"] = [m for m in payload["models"] if m["model"] == "synthetic/stable-v1"]
    payload["routes"] = [r for r in payload["routes"] if r["requested_model"] == "synthetic/stable-v1"]
    payload["pricing"] = [p for p in payload["pricing"] if p["model"] == "synthetic/stable-v1"]
    payload["sources"] = [
        s for s in payload["sources"]
        if s["model"] == "synthetic/stable-v1" or s["provider"] == "ecb"
    ]
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = _report_for(bundle, _baseline())
    assert report.state == OVERALL_READY
    assert report.counts["unchanged"] == 1
    assert report.counts["new"] == 0
    assert report.counts["changed"] == 0
    html_text = render_report(bundle, report.to_dict()).decode("utf-8")
    assert "No price movements" in html_text
    assert "No route or model attribute changes" in html_text
    assert "Unchanged models (1) — collapsed" in html_text


def test_ready_with_warnings_report_shows_findings() -> None:
    """A source-age REVIEW (no mutations) is the canonical READY_WITH_WARNINGS."""
    from datetime import UTC, datetime, timedelta

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-stale-source-001"
    # Make updated-v1 identical to the baseline so the only finding is the
    # aged source (25h: past the 24h review threshold, below the 72h block).
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = "1"
    # The evidence must carry the proposed price (the fixture snapshot pins
    # 1.2/4 EUR for updated-v1; the baseline carries 1/4).
    _evidence_tests.set_openrouter_evidence(
        payload, {**_evidence_tests.DEFAULT_PRICES, "synthetic/updated-v1": ("1", "4")}
    )
    for route in payload["routes"]:
        if route["requested_model"] == "synthetic/updated-v1":
            route["priority"] = 100
    retrieved = (datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC) - timedelta(hours=25)).isoformat()
    for source in payload["sources"]:
        source["retrieved_at"] = retrieved
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report = _report_for(bundle, _baseline())
    assert report.state == OVERALL_READY_WITH_WARNINGS
    html_text = render_report(bundle, report.to_dict()).decode("utf-8")
    assert "READY_WITH_WARNINGS" in html_text
    assert "source_stale_review" in html_text
    # Four aged sources (three openrouter plus the ecb reference source)
    # plus the derived sources-gate finding.
    assert "All warnings and findings (5)" in html_text


def test_blocked_report_lists_blockers_on_first_screen() -> None:
    bundle = _bundle("bundle-blocked.json")
    report = _report_for(bundle, _baseline())
    assert report.state == OVERALL_BLOCKED
    html_text = render_report(bundle, report.to_dict()).decode("utf-8")
    assert "BLOCKED" in html_text
    assert "currency_inconsistency" in html_text
    assert "missing_required_dimension" in html_text
    assert "CURRENCY_MISMATCH" in html_text


def test_minimal_blocked_html_is_safe_and_states_unsealed() -> None:
    html_text = _minimal_blocked_html(
        run_id="blocked-invalid-<script>alert(1)</script>",
        code="bundle_invalid_json",
        detail="duplicate JSON key 'run_id'",
        generated_at="2026-09-21T12:00:00+00:00",
    ).decode("utf-8")
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    assert "not sealed" in html_text
    _assert_no_external_or_executable_resources(html_text)


def _big_unchanged_case(model_count: int) -> tuple[object, object]:
    """Build an N-model unscoped baseline + identical bundle deterministically."""
    providers = (BaselineProviderRow(
        id="11111111-1111-4111-8111-111111111111", provider="openrouter",
        display_name="OpenRouter (synthetic)", kind="openai_compatible",
        base_url="https://openrouter.ai/api/v1", api_key_env_var="OPENROUTER_API_KEY",
        enabled=True, timeout_seconds=300, max_retries=2,
        created_at="2026-09-01T00:00:00+00:00", updated_at="2026-09-01T00:00:00+00:00"),)
    routes = tuple(BaselineRouteRow(
        id=f"22222222-0000-4000-8000-{i:012d}", requested_model=f"big/model-{i:02d}",
        match_type="exact", endpoint="/v1/chat/completions", provider="openrouter",
        upstream_model=f"big/model-{i:02d}", priority=100, enabled=True,
        visible_in_models=True, supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        created_at="2026-09-01T00:00:00+00:00", updated_at="2026-09-01T00:00:00+00:00",
    ) for i in range(model_count))
    pricing = tuple(BaselinePricingRow(
        id=f"33333333-0000-4000-8000-{i:012d}", provider="openrouter",
        upstream_model=f"big/model-{i:02d}", endpoint="/v1/chat/completions",
        currency="EUR", input_price_per_1m="0.10", output_price_per_1m="0.40",
        valid_from="2026-09-01T00:00:00+00:00", valid_until=None,
        enabled=True, source_url="https://openrouter.ai/models",
        created_at="2026-09-01T00:00:00+00:00", updated_at="2026-09-01T00:00:00+00:00",
    ) for i in range(model_count))
    baseline = BaselineDocument(
        schema_version="1", exported_at="2026-09-21T10:00:00+00:00",
        target=BaselineTarget(server_host="127.0.0.1", server_port=5433,
                              database="slaif-synthetic-baseline", postgres_version="16.4"),
        sql_checked=True,
        counts=BaselineCounts(providers=1, routes=model_count, pricing_rules=model_count, fx_rates=0),
        content_sha256="0" * 64, providers=providers, routes=routes, pricing=pricing, fx=(),
    )
    digest = hashlib.sha256(
        canonical_baseline_content(baseline.model_copy(update={"content_sha256": "0" * 64}))
    ).hexdigest()
    baseline = baseline.model_copy(update={"content_sha256": digest})

    # One real OpenRouter /models snapshot (official shape, per-token USD at
    # the 1.08 reference quote) carrying every model at 0.10/0.40 EUR
    # equivalents; all per-model source records reference the same digest
    # (repeated references are one observation, not corroboration).
    snapshot = _evidence_tests.openrouter_snapshot_bytes(
        {f"big/model-{i:02d}": ("0.10", "0.40") for i in range(model_count)}
    )
    snapshot_digest = hashlib.sha256(snapshot).hexdigest()
    snapshot_b64 = base64.b64encode(snapshot).decode("ascii")

    models, routes_b, pricing_b, sources = [], [], [], []
    for i in range(model_count):
        model = f"big/model-{i:02d}"
        source_ref = f"openrouter|{model}|openrouter_models_api"
        sources.append({
            "provider": "openrouter", "model": model, "source_kind": "openrouter_models_api",
            "url": "https://openrouter.ai/api/v1/models",
            "retrieved_at": "2026-09-21T11:00:00+00:00", "published_at": None,
            "content_sha256": snapshot_digest,
            "evidence_b64": snapshot_b64,
            "extractor": "fixture-deterministic/1.0", "extraction": "deterministic",
            "required": True, "truncated": False, "warnings": [],
        })
        models.append({
            "provider": "openrouter", "model": model, "display_name": f"Big {i:02d}",
            "context_length": 128000, "max_output_tokens": 8192, "supports_streaming": True,
            "capabilities": {"text": True, "streaming": True}, "deprecated": False,
            "provenance": {"sources": [source_ref], "extractor": "fixture-deterministic/1.0",
                            "extraction": "deterministic"},
            "warnings": [],
        })
        routes_b.append({
            "provider": "openrouter", "requested_model": model, "upstream_model": model,
            "match_type": "exact", "endpoint": "/v1/chat/completions", "priority": 100,
            "enabled": True, "visible_in_models": True, "supports_streaming": True,
            "capabilities": {"text": True, "streaming": True},
            "provenance": {"sources": [source_ref], "extractor": "fixture-deterministic/1.0",
                            "extraction": "deterministic"},
            "warnings": [],
        })
        pricing_b.append({
            "provider": "openrouter", "model": model, "endpoint": "/v1/chat/completions",
            "currency": "EUR",
            "dimensions": [
                {"name": "input", "value": "0.10", "unit": "per_1m_tokens", "currency": "EUR"},
                {"name": "output", "value": "0.40", "unit": "per_1m_tokens", "currency": "EUR"},
            ],
            "valid_from": "2026-09-01T00:00:00+00:00",
            "provenance": {"sources": [source_ref], "extractor": "fixture-deterministic/1.0",
                            "extraction": "deterministic"},
            "warnings": [],
        })
    bundle_payload = {
        "schema_version": "1", "run_id": "test-big-unchanged-001",
        "generated_at": "2026-09-21T12:00:00+00:00",
        "revision": {"schema_version": "1", "slaif_revision": "fixture-revision-180"},
        "research": {"status": "NOT_RUN", "codex_version": "N/A", "prompt_version": "N/A",
                      "extractor_version": "fixture/1.0", "tool_version": "fixture/1.0"},
        "policy": {"version": 1},
        "profile": {"name": "standard-v1", "endpoint": "/v1/chat/completions",
                     "supports_streaming": True, "local_models_visible": True,
                     "capability_allowlist": []},
        "selection": {"providers": ["openrouter"], "model_include": []},
        "sources": sources + [_evidence_tests.ecb_source_dict()],
        "models": models, "routes": routes_b, "pricing": pricing_b,
        "fx": [_evidence_tests.fx_fact_dict("1.08", "EUR-USD", "2026-09-21T00:00:00Z")],
        "baseline": {
            "mode": "exported_file", "exported_at": "2026-09-21T10:00:00+00:00",
            "target_database": "slaif-synthetic-baseline", "sql_checked": True,
            "content_sha256": digest,
            "row_counts": {"providers": 1, "routes": model_count, "pricing_rules": model_count, "fx_rates": 0},
        },
        "notes": "Large unchanged synthetic case.",
    }
    bundle = load_bundle(json.dumps(bundle_payload, sort_keys=True).encode("utf-8"))
    return bundle, baseline


def test_large_unchanged_report_renders_and_stays_deterministic() -> None:
    bundle, baseline = _big_unchanged_case(80)
    report = _report_for(bundle, baseline)
    assert report.state == OVERALL_READY
    assert report.counts["unchanged"] == 80
    html_bytes = render_report(bundle, report.to_dict())
    assert len(html_bytes) > 100_000
    html_text = html_bytes.decode("utf-8")
    assert "Unchanged models (80) — collapsed" in html_text
    assert html_bytes == render_report(bundle, report.to_dict())


def test_build_manifest_is_sorted_and_digests_files() -> None:
    files = {"b.tsv": b"beta\n", "a.tsv": b"alpha\n"}
    manifest = json.loads(build_manifest(files).decode("utf-8"))
    assert [entry["path"] for entry in manifest["files"]] == ["a.tsv", "b.tsv"]
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"alpha\n").hexdigest()
    assert manifest["files"][0]["bytes"] == len(b"alpha\n")
