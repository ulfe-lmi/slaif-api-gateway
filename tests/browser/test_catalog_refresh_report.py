"""Browser file-URL layout tests for the catalog-refresh REVIEW.html.

Standalone on purpose: no gateway server, PostgreSQL, Redis,
TEST_DATABASE_URL, or provider dependency. Real pipeline documents
(CLI-published sealed runs for first-install and blocked; in-process
validate+render for the rest — the same pure functions the CLI uses) are
opened as ``file://`` URLs in a JavaScript-disabled Chromium context with
full request recording.

180-i: generated HTML, screenshots, PDFs and metrics are written ONLY
under pytest-owned temporary output (tmp_path / tmp_path_factory); tracked
repository files are never written by this suite, and the run must leave
the worktree unchanged. The committed browser-screenshots/ and
report-layout/ artifacts are deliberately copied, inspected outputs of
exactly this renderer (a separate explicit implementation step).

Geometry is measured on the real document, not only on selected container
boxes: ``documentElement.scrollWidth`` (collapsed AND fully expanded, at
1440, 1280 and 375) plus the first 1440x900 reading surface — state,
concise scope/identity, grouped checklist, provider change summary, FX,
plan line, findings line, and the "What changed" heading with its first
content element must share one viewport. Main reading font sizes and
single-line short labels are asserted. Visible (rendered) text — not
hidden DOM markup — is asserted for the expanded evidence (full 64-hex
digests, price-change values, the FX quote identity).

Run:  python -m pytest tests/browser -m playwright
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from datetime import timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.playwright

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "catalog_refresh"

# Reuse the unit-suite pipeline builders (the same code the CLI drives).
# Qualified import (repo root on sys.path via ``python -m pytest``) avoids a
# basename collision with this file's own pytest module name. The plain
# path entry below is needed for those modules' internal bare imports.
sys.path.insert(0, str(REPO / "tests" / "unit"))

from tests.unit.test_catalog_refresh_report import (  # noqa: E402
    _big_unchanged_case as _report_big_unchanged_case,
    _baseline as _unit_baseline,
)
from tests.unit.test_catalog_refresh_source_evidence import (  # noqa: E402
    DEFAULT_PRICES as _default_prices,
    ecb_source_dict as _ecb_source_dict,
    set_openrouter_evidence as _set_openrouter_evidence,
)
from tests.unit.test_catalog_refresh_policy import (  # noqa: E402
    GENERATED_AT as _generated_at,
    _bundle_payload as _policy_bundle_payload,
    _fx_facts_dict as _policy_fx_facts_dict,
    _mini_usd_baseline as _mini_usd_baseline,
    _usd_pricing as _usd_pricing,
)

from slaif_gateway.services.catalog_refresh.baseline import (  # noqa: E402
    load_baseline,
)
from slaif_gateway.services.catalog_refresh.bundle import load_bundle  # noqa: E402
from slaif_gateway.services.catalog_refresh.policy import (  # noqa: E402
    policy_from_document,
)
from slaif_gateway.services.catalog_refresh.rendering import (  # noqa: E402
    render_report,
)
from slaif_gateway.services.catalog_refresh.validation import (  # noqa: E402
    OVERALL_BLOCKED,
    OVERALL_READY,
    OVERALL_READY_WITH_WARNINGS,
    sql_capture_for_mode,
    validate_bundle,
)

playwright_sync = pytest.importorskip("playwright.sync_api")

# The 1440x900 decision surface: every selector below must be visible in
# the first viewport (top >= 0, bottom <= 900) in the normal desktop case.
FIRST_SCREEN_SELECTORS = (
    ".state",
    "#scope-baseline",
    "#checks",
    "#per-provider",
    "#fx-line",
    "#plan-line",
    "#findings-line",
    "#changes > h2",
    "#changes > :nth-child(2)",
)

# Main reading text floors (px at default zoom).
FONT_FLOOR = (
    ("body", 15.0),
    ("h1", 20.0),
    ("h2", 16.0),
    ("dl.kv", 14.0),
    ("table", 13.5),
    (".chip", 13.5),
    (".state", 17.0),
)

# Short column headers that must stay on a single line at 1440 (a wrapped
# short word is exactly the 180-h defect this round removes at desktop).
SINGLE_LINE_HEADERS = (
    "New",
    "Changed",
    "Mutations",
    "Unchanged",
    "Excluded",
    "Blocked",
    "Disappeared",
    "Deprecated",
)

_CLI_EXPECTED_EXIT = {"first-install": 0, "blocked": 20}


# --------------------------------------------------------------------------
# Case construction (actual pipeline outputs)
# --------------------------------------------------------------------------


def _two_provider_case() -> tuple[object, dict]:
    bundle = load_bundle(
        (FIXTURES / "report-layout" / "two-provider-long-ids.bundle.json").read_bytes()
    )
    baseline = load_baseline(
        (FIXTURES / "report-layout" / "two-provider-long-ids.baseline.json").read_bytes()
    )
    report, _ = validate_bundle(
        bundle,
        baseline,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_READY
    return bundle, report


def _ready_case() -> tuple[object, dict]:
    """Unchanged-only refresh (the canonical READY, no changes)."""
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "browser-ready-001"
    payload["selection"]["model_include"] = ["synthetic/stable-v1"]
    payload["models"] = [m for m in payload["models"] if m["model"] == "synthetic/stable-v1"]
    payload["routes"] = [r for r in payload["routes"] if r["requested_model"] == "synthetic/stable-v1"]
    payload["pricing"] = [p for p in payload["pricing"] if p["model"] == "synthetic/stable-v1"]
    payload["sources"] = [
        s for s in payload["sources"]
        if s["model"] == "synthetic/stable-v1" or s["provider"] == "ecb"
    ]
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(
        bundle,
        _unit_baseline(),
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_READY
    return bundle, report


def _collection_case() -> tuple[object, dict]:
    """A 181 live-collected bundle (same refresh as the ready case plus a
    recorded collection identity whose ok retrieval records match the
    sources' URLs and digests): exercises the live-collection scope line,
    the scope-card Collection row, and the #collection-details section."""
    from datetime import UTC, datetime

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "browser-collection-001"
    payload["selection"]["model_include"] = ["synthetic/stable-v1"]
    payload["models"] = [m for m in payload["models"] if m["model"] == "synthetic/stable-v1"]
    payload["routes"] = [r for r in payload["routes"] if r["requested_model"] == "synthetic/stable-v1"]
    payload["pricing"] = [p for p in payload["pricing"] if p["model"] == "synthetic/stable-v1"]
    payload["sources"] = [
        s for s in payload["sources"]
        if s["model"] == "synthetic/stable-v1" or s["provider"] == "ecb"
    ]
    by_url: dict[str, dict] = {}
    for source in payload["sources"]:
        by_url.setdefault(source["url"], source)
    or_source = by_url["https://openrouter.ai/api/v1/models"]
    ecb_source = by_url[
        "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html"
    ]
    started = datetime(2026, 9, 21, 11, 59, 0, tzinfo=UTC)
    finished = datetime(2026, 9, 21, 12, 0, 30, tzinfo=UTC)
    payload["collection"] = {
        "tool": "slaif-gateway/0.1.0",
        "code_revision": "slaif-api-gateway==0.1.0",
        "profile": "standard-v1",
        "providers": ["openrouter"],
        "model_include": ["synthetic/stable-v1"],
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "retrievals": [
            {
                "requested_url": or_source["url"],
                "final_url": None,
                "retrieved_at": started.isoformat(),
                "outcome": "ok",
                "status": 200,
                "failure_code": None,
                "content_type": "application/json",
                "content_bytes": 1024,
                "content_sha256": or_source["content_sha256"],
                "attempts": 1,
                "redirects": 0,
                "published_at": None,
            },
            {
                "requested_url": ecb_source["url"],
                "final_url": None,
                "retrieved_at": started.isoformat(),
                "outcome": "ok",
                "status": 200,
                "failure_code": None,
                "content_type": "text/html",
                "content_bytes": 512,
                "content_sha256": ecb_source["content_sha256"],
                "attempts": 1,
                "redirects": 0,
                "published_at": None,
            },
        ],
        "inventory": [],
        "deduplicated_fetches": False,
    }
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(
        bundle,
        _unit_baseline(),
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_READY, report.state_reason
    assert report.to_dict()["source_evidence"]["scope"] == "live_collection"
    return bundle, report


def _warnings_case() -> tuple[object, dict]:
    """Aged-source READY_WITH_WARNINGS (mirrors the unit-suite case)."""
    from datetime import UTC, datetime

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "browser-warnings-001"
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = "1"
    _set_openrouter_evidence(
        payload,
        {**_default_prices, "synthetic/updated-v1": ("1", "4")},
    )
    for route in payload["routes"]:
        if route["requested_model"] == "synthetic/updated-v1":
            route["priority"] = 100
    retrieved = (datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC) - timedelta(hours=25)).isoformat()
    for source in payload["sources"]:
        source["retrieved_at"] = retrieved
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(
        bundle,
        _unit_baseline(),
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_READY_WITH_WARNINGS
    return bundle, report


def _large_unchanged_case() -> tuple[object, dict]:
    bundle, baseline = _report_big_unchanged_case(80)
    report, _ = validate_bundle(
        bundle,
        baseline,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_READY
    return bundle, report


def _price_change_case() -> tuple[object, dict]:
    """The full canonical refresh bundle through the unchanged validator:
    a real price change (updated-v1 input 1 -> 1.2, +20 %), one NEW and
    one unchanged model, and the existing-row update makes the create-only
    import plans BLOCKED."""
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "browser-price-change-001"
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    report, _ = validate_bundle(
        bundle,
        _unit_baseline(),
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_BLOCKED
    changed = [
        c for c in report.price_comparisons
        if c.state not in ("UNCHANGED", "NEW") and c.model == "synthetic/updated-v1"
    ]
    assert changed, "expected a real changed price comparison"
    return bundle, report


def _fx_required_case() -> tuple[object, dict]:
    """USD-priced bundle with one FX fact bound to a supplied ECB quote
    (current validator/source contracts, unchanged policy helpers); the
    mini baseline carries the same USD->EUR pair, so the display exercises
    a genuine FX comparison, not the all-EUR N/A line."""
    payload = _policy_bundle_payload()
    payload["run_id"] = "browser-fx-required-001"
    _usd_pricing(payload)  # fixture snapshot carries exactly these USD values
    published = _generated_at - timedelta(hours=1)
    xml_rate = str((Decimal(1) / Decimal("1.08")).quantize(Decimal("0.000000001")))
    payload["fx"] = [_policy_fx_facts_dict("1.08", pair="USD-EUR", published_hours_ago=1)]
    payload["sources"] = [s for s in payload["sources"] if s["provider"] != "ecb"]
    payload["sources"].append(
        _ecb_source_dict(
            pair_model="USD-EUR",
            date_s=published.date().isoformat(),
            rate=xml_rate,
            retrieved_at=published.isoformat().replace("+00:00", "Z"),
            published_at=published.isoformat().replace("+00:00", "Z"),
        )
    )
    bundle = load_bundle(json.dumps(payload, sort_keys=True).encode("utf-8"))
    baseline = _mini_usd_baseline(
        fx=[{"base": "USD", "quote": "EUR", "rate": "1.08",
             "valid_from": "2026-09-20T00:00:00+00:00"}]
    )
    report, _ = validate_bundle(
        bundle,
        baseline,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    assert report.state == OVERALL_READY
    assert len(report.fx_comparisons) == 1
    comparison = report.fx_comparisons[0]
    assert comparison["state"] == "UNCHANGED"
    return bundle, report


def _cli_run_report(tmp_path: Path, name: str, extra: list[str]) -> Path:
    """Drive the real CLI to publish a sealed run; return REVIEW.html."""
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = CliRunner().invoke(
        app,
        [
            "catalog-refresh",
            "review",
            str(FIXTURES / f"bundle-{name}.json"),
            *extra,
            "--run-root",
            str(run_root),
            "--seal-key",
            str(key),
        ],
    )
    assert result.exit_code == _CLI_EXPECTED_EXIT[name], result.output
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1, f"expected exactly one published run, got {run_dirs}"
    report = run_dirs[0] / "REVIEW.html"
    assert report.is_file()
    return report


# --------------------------------------------------------------------------
# Assertions
# --------------------------------------------------------------------------


def _assert_static_offline_html(html_text: str) -> None:
    """No scripts, event handlers, external resources, or CSS fetches."""
    lowered = html_text.lower()
    assert not re.search(r"<script\b", lowered), "real <script> tag present"
    assert not re.search(r"<[a-z][^>]*\son\w+=", lowered), "real tag carries an on* handler"
    assert not re.search(r"<[a-z][^>]*\ssrc=", lowered), "real tag carries src="
    for tag in ("link", "iframe", "object", "embed", "form", "video", "audio", "img"):
        assert not re.search(rf"<{tag}\b", lowered), f"forbidden real tag <{tag}>"
    style = re.search(r"<style>(.*?)</style>", html_text, flags=re.DOTALL)
    assert style is not None
    assert "@import" not in style.group(1)
    assert "url(" not in style.group(1)
    for href in re.findall(r"href='([^']+)'", html_text):
        assert href.startswith(("http://", "https://", "#")), f"unsafe href {href!r}"


def _assert_internal_link_targets(html_text: str) -> None:
    ids = set(re.findall(r"\bid=['\"]([^'\"]+)['\"]", html_text))
    for target in re.findall(r"href=['\"]#([^'\"]+)['\"]", html_text):
        assert target in ids, f"internal link #{target} has no matching id"


def _open_all_details(page) -> int:
    """Click every unopened summary until none remain (handles nesting)."""
    total = page.locator("details").count()
    opened = 0
    for _ in range(total + 2):  # bounded: each click opens one details
        unopened = page.locator("details:not([open]) > summary")
        if unopened.count() == 0:
            break
        unopened.first.click()
        opened += 1
    assert page.locator("details:not([open]) > summary").count() == 0, (
        "nested details could not be fully expanded"
    )
    return opened


def _document_scroll_width(page) -> int:
    """The real document width (what the user can scroll), not a box set."""
    return page.evaluate("document.documentElement.scrollWidth")


def _computed_font_px(page, selector: str) -> float:
    return page.evaluate(
        "(sel) => parseFloat(getComputedStyle(document.querySelector(sel)).fontSize)",
        selector,
    )


def _check_case(
    playwright,
    case: str,
    html_path: Path,
    expected: dict,
    out_dir: Path,
    metrics: dict,
) -> None:
    requests: list[str] = []

    def _record(request) -> None:
        requests.append(f"{request.resource_type}:{request.url}")

    browser = playwright.chromium.launch()
    try:
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            java_script_enabled=False,
        )
        page = context.new_page()
        page.on("request", _record)
        page.goto(html_path.as_uri())
        # Exactly one network interaction: the document itself.
        assert requests == ["document:" + html_path.as_uri()], (
            f"unexpected requests: {requests}"
        )

        html_text = html_path.read_text(encoding="utf-8")
        _assert_static_offline_html(html_text)
        _assert_internal_link_targets(html_text)

        case_metrics: dict = {"case": case, "requests": len(requests)}

        # 1) The whole decision surface fits the first 1440x900 viewport:
        #    state, scope/identity, checklist, provider summary, FX, plan,
        #    findings, and the "What changed" heading with its first
        #    content element — together.
        boxes: dict[str, dict] = {}
        for selector in FIRST_SCREEN_SELECTORS:
            locator = page.locator(selector)
            assert locator.count() == 1, (
                f"{selector}: expected exactly one element, got {locator.count()}"
            )
            box = locator.bounding_box()
            assert box is not None, f"{selector}: not visible (no bounding box)"
            boxes[selector] = box
            assert box["y"] >= 0, f"{selector}: above the viewport top"
            assert box["y"] + box["height"] <= 900, (
                f"{selector} not in the first 1440x900 viewport: "
                f"top={box['y']:.1f} bottom={box['y'] + box['height']:.1f}"
            )
        case_metrics["first_viewport_boxes_1440x900"] = {
            k: {"top": round(v["y"], 1), "bottom": round(v["y"] + v["height"], 1)}
            for k, v in boxes.items()
        }
        case_metrics["state_visible_text"] = page.locator(".state").inner_text()[:200]

        # 2) Real document width: no page-wide horizontal overflow.
        scroll_width = _document_scroll_width(page)
        assert scroll_width <= 1440, (
            f"page-wide horizontal overflow at 1440 (collapsed): {scroll_width}"
        )
        case_metrics["document_scroll_width_1440"] = scroll_width

        # 3) Main reading font sizes (tiny text is a geometry fail).
        fonts: dict[str, float] = {}
        for selector, floor in FONT_FLOOR:
            size = _computed_font_px(page, selector)
            fonts[selector] = size
            assert size >= floor, f"{selector}: font {size}px below the {floor}px floor"
        case_metrics["computed_font_px_1440"] = fonts

        # 4) Short column headers and provider names stay on one line at
        #    desktop (mid-word breaks of short words are the 180-h defect).
        header_line_height = page.evaluate(
            "parseFloat(getComputedStyle("
            "document.querySelector('#per-provider thead th')).lineHeight)"
        )
        for label in SINGLE_LINE_HEADERS:
            cell = page.locator("#per-provider thead th").filter(
                has_text=re.compile(rf"^{label}$")
            )
            assert cell.count() == 1, f"header cell {label!r} not found exactly once"
            box = cell.first.bounding_box()
            assert box is not None, f"header cell {label!r} not visible"
            assert box["height"] <= header_line_height * 1.6 + 1, (
                f"short header {label!r} wrapped to multiple lines at 1440 "
                f"(height={box['height']:.1f})"
            )
        provider_cells = page.locator("#per-provider tbody tr:first-child td:first-child")
        for cell in provider_cells.all():
            box = cell.bounding_box()
            assert box is not None
            assert box["height"] <= header_line_height * 1.6 + 1, (
                f"provider name {cell.inner_text()!r} wrapped at 1440 "
                f"(height={box['height']:.1f})"
            )
        case_metrics["short_labels_single_line_1440"] = True

        # 5) Screenshot of the first 1440x900 viewport (tmp output only).
        shot = out_dir / f"{case}-1440.png"
        page.screenshot(path=str(shot), clip={"x": 0, "y": 0, "width": 1440, "height": 900})
        case_metrics["screenshot"] = str(shot)

        # 6) 1280x800 and 375x812: fresh loads at each viewport (the way a
        #    user sees those widths), collapsed AND fully expanded. Fresh
        #    pages avoid stale geometry from a same-page resize in
        #    headless Chromium, which a real narrow-viewport user never
        #    sees.
        for width, height in ((1280, 800), (375, 812)):
            narrow = context.new_page()
            narrow_requests: list[str] = []
            narrow.on(
                "request",
                lambda req, _r=narrow_requests: _r.append(f"{req.resource_type}:{req.url}"),
            )
            try:
                narrow.set_viewport_size({"width": width, "height": height})
                narrow.goto(html_path.as_uri())
                assert narrow_requests == ["document:" + html_path.as_uri()], (
                    f"extra requests at {width}px: {narrow_requests}"
                )
                collapsed = _document_scroll_width(narrow)
                assert collapsed <= width, (
                    f"page-wide horizontal overflow at {width}px (collapsed): {collapsed}"
                )
                case_metrics[f"document_scroll_width_{width}"] = collapsed
                _open_all_details(narrow)
                expanded = _document_scroll_width(narrow)
                assert expanded <= width, (
                    f"page-wide horizontal overflow at {width}px (expanded): {expanded}"
                )
                case_metrics[f"document_scroll_width_{width}_expanded"] = expanded
                if width == 375:
                    # 375 must stay usable with the evidence expanded too.
                    assert narrow.locator(".state").bounding_box() is not None, (
                        "375px: state banner not visible with evidence expanded"
                    )
            finally:
                narrow.close()

        # 7) Fully expanded at 1440: the VISIBLE rendered text must carry
        #    the deep evidence (hidden DOM markup is not proof that a user
        #    can see it).
        opened = _open_all_details(page)
        case_metrics["details_opened"] = opened
        visible_text = page.locator("body").inner_text()
        if expected["has_sources"]:
            full_digests = set(re.findall(r"\b[0-9a-f]{64}\b", visible_text))
            assert full_digests, "no full 64-hex digest visible in the expanded report"
            case_metrics["full_digests_visible"] = len(full_digests)
        for needle in expected["visible"]:
            assert needle in visible_text, (
                f"expected visible value {needle!r} missing from the expanded report"
            )
        case_metrics["findings_summary_visible_text"] = (
            page.locator("#all-findings > summary").inner_text()
        )

        # 8) Actual print evidence of the expanded document (price/FX
        #    cases): a real PDF with expanded price/FX/source evidence.
        if expected["pdf"]:
            pdf_path = out_dir / f"{case}-expanded-print.pdf"
            pdf_bytes = page.pdf(path=str(pdf_path), print_background=True)
            assert pdf_bytes[:4] == b"%PDF", "PDF does not start with %PDF"
            assert len(pdf_bytes) > 0
            case_metrics["print_pdf"] = str(pdf_path)
            case_metrics["print_pdf_bytes"] = len(pdf_bytes)

        metrics[case] = case_metrics
    finally:
        browser.close()


# --------------------------------------------------------------------------
# Fixtures and test
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def playwright():
    try:
        with playwright_sync.sync_playwright() as pw:
            probe = pw.chromium.launch()  # fail fast without a browser
            probe.close()
            yield pw
    except Exception as exc:  # noqa: BLE001 - a missing toolchain is a skip
        pytest.skip(f"playwright chromium unavailable: {exc}")


@pytest.fixture(scope="module")
def case_html(tmp_path_factory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("catalog-report")
    out: dict[str, Path] = {}
    out["_out"] = tmp
    out["first-install"] = _cli_run_report(
        tmp / "first-install", "first-install", ["--first-install"]
    )
    out["blocked"] = _cli_run_report(
        tmp / "blocked",
        "blocked",
        ["--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
    )
    for case, builder in (
        ("ready", _ready_case),
        ("collection", _collection_case),
        ("warnings", _warnings_case),
        ("large-unchanged", _large_unchanged_case),
        ("two-provider", _two_provider_case),
        ("price-change", _price_change_case),
        ("fx-required", _fx_required_case),
    ):
        bundle, report = builder()
        html = tmp / case / "REVIEW.html"
        html.parent.mkdir(parents=True)
        html.write_bytes(render_report(bundle, report.to_dict()))
        out[case] = html
    return out


CASE_EXPECTATIONS = {
    # has_sources: full digests must be visible once the evidence is open;
    # pdf: capture an actual expanded print artifact; visible: case-specific
    # values that must be in the rendered (not hidden) text.
    "first-install": {"has_sources": False, "pdf": False, "visible": ()},
    "blocked": {"has_sources": True, "pdf": False, "visible": ()},
    "ready": {"has_sources": True, "pdf": False, "visible": ()},
    "collection": {
        "has_sources": True,
        "pdf": False,
        "visible": (
            "Collection details",
            "recorded collection identity",
            "live-collection scope",
            "Measured retrieval records",
            "NOT_RUN",
        ),
    },
    "warnings": {"has_sources": True, "pdf": False, "visible": ()},
    "large-unchanged": {"has_sources": True, "pdf": False, "visible": ()},
    "two-provider": {"has_sources": True, "pdf": False, "visible": ()},
    "price-change": {
        "has_sources": True,
        "pdf": True,
        "visible": ("1.2", "+20.000 %"),
    },
    "fx-required": {"has_sources": True, "pdf": True, "visible": ("1.08", "eurofxref")},
}


def test_browser_layout_all_cases(playwright, case_html) -> None:
    metrics: dict = {}
    out_dir: Path = case_html["_out"]
    for case in (
        "first-install",
        "ready",
        "collection",
        "warnings",
        "blocked",
        "large-unchanged",
        "two-provider",
        "price-change",
        "fx-required",
    ):
        _check_case(playwright, case, case_html[case], CASE_EXPECTATIONS[case], out_dir, metrics)
    metrics_path = out_dir / "metrics-final.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("\nbrowser layout metrics (per case: viewport boxes, document widths, "
          "fonts, requests, details opened, visible digests, print PDFs):")
    print(f"metrics written to {metrics_path}")
    print(json.dumps(metrics, indent=1, sort_keys=True))
