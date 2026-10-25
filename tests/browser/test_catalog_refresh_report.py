"""Browser file-URL layout tests for the catalog-refresh REVIEW.html.

Standalone on purpose: no gateway server, PostgreSQL, Redis,
TEST_DATABASE_URL, or provider dependency. Real pipeline documents
(CLI-published sealed runs for first-install and blocked; in-process
validate+render for the rest — the same pure functions the CLI uses) are
opened as ``file://`` URLs in a JavaScript-disabled Chromium context with
full request recording. 192-a adds one JavaScript-ENABLED document open:
the single fixed bundled table-sorting script must stay offline (exactly
one request, the document) while real header-button clicks sort the
rendered rows (aria-sort ascending → descending, tables independent).

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
from tests.unit import catalog_report_script_audit as _script_audit  # noqa: E402
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
    ACQUISITION_LIVE,
    ACQUISITION_OFFLINE,
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

# first-install is READY_WITH_WARNINGS (exit 10) since 182 (A2): the
# bootstrap route create is new public model exposure requiring ACK.
_CLI_EXPECTED_EXIT = {"first-install": 10, "blocked": 20}


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
    # Since 182 (A2) the openai long-id route is NEW against the
    # fixture baseline: exactly one REVIEW new_model_exposure finding
    # (no blocker) flips the canonical READY to READY_WITH_WARNINGS.
    # The long-identifier wrap layout under test renders identically.
    assert report.state == OVERALL_READY_WITH_WARNINGS
    two_warnings = report.to_dict()["warnings"]
    assert {w["code"] for w in two_warnings} == {"new_model_exposure"}
    assert all(w["severity"] == "REVIEW" for w in two_warnings)
    assert len(two_warnings) == 1
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


def _collection_bundle() -> object:
    """The ACTUAL mocked-collect output (real collector identity with
    measured code revision, real retrieval records, and inventory) —
    181-i browser coverage uses the genuine collect pipeline, not
    hand-built collection metadata. The scope is a RUNNER-SELECTED
    context of the reviewing invocation, never a property of these
    bytes."""
    import test_catalog_refresh_collection as _collect_tests

    return _collect_tests._collect(_collect_tests.World(), providers=("openai", "openrouter"))


def _collection_case() -> tuple[object, dict]:
    """The intact collected bundle reviewed under the RUNNER-SELECTED
    LIVE context (the collect invocation itself): live_collection scope,
    the scope-card Collection row, and the #collection-details section."""
    bundle = _collection_bundle()
    report, _ = validate_bundle(
        bundle,
        None,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        acquisition=ACQUISITION_LIVE,
    )
    # Since 182 (A2): with no baseline every collected route is new
    # public model exposure: READY_WITH_WARNINGS carrying only the
    # REVIEW new_model_exposure findings (never a blocker); the
    # collection scope-card layout under test renders identically.
    assert report.state == OVERALL_READY_WITH_WARNINGS, report.state_reason
    live_warnings = report.to_dict()["warnings"]
    assert {w["code"] for w in live_warnings} == {"new_model_exposure"}
    assert all(w["severity"] == "REVIEW" for w in live_warnings)
    assert report.to_dict()["source_evidence"]["scope"] == "live_collection"
    return bundle, report


def _supplied_collection_case() -> tuple[object, dict]:
    """The SAME intact bundle reviewed under the runner-selected OFFLINE
    context (a supplied review): supplied_collection scope — the recorded
    collection identity is historical provenance, preserved and labeled,
    and this invocation performed no live retrieval (181-i I1)."""
    bundle = _collection_bundle()
    report, _ = validate_bundle(
        bundle,
        None,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        acquisition=ACQUISITION_OFFLINE,
    )
    # Same A2 exposure findings under the OFFLINE supplied context;
    # historical provenance rendering is unchanged by the state flip.
    assert report.state == OVERALL_READY_WITH_WARNINGS, report.state_reason
    off_warnings = report.to_dict()["warnings"]
    assert {w["code"] for w in off_warnings} == {"new_model_exposure"}
    assert all(w["severity"] == "REVIEW" for w in off_warnings)
    assert report.to_dict()["source_evidence"]["scope"] == "supplied_collection"
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


class _attr_patch:
    """Minimal setattr/restore shim so the unit-suite pipeline builder can
    run here (module-scoped fixture cannot use the function-scoped
    monkeypatch fixture)."""

    def __init__(self) -> None:
        self._undo: list[tuple[object, str, object]] = []

    def setattr(self, target: object, name: str, value: object) -> None:
        self._undo.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def undo(self) -> None:
        for target, name, original in reversed(self._undo):
            setattr(target, name, original)
        self._undo = []


def _research_pipeline_bundle(tmp: Path):
    """The unit-suite full-pipeline builder: one openrouter first-install
    collect whose single unresolved limit is completed by the qualification
    mock research transport (stand-in execute_task; the grounding,
    collection, bundle, validation and rendering layers are the real
    product code)."""
    from tests.unit.test_catalog_refresh_research import _pipeline_bundle

    patch = _attr_patch()
    try:
        return _pipeline_bundle(tmp, patch)
    finally:
        patch.undo()


def _research_case(tmp: Path, acquisition: str) -> tuple[object, dict]:
    """Research-backed bundle through the real validate path: LIVE = the
    collect invocation's runner-selected scope; OFFLINE = an intact
    supplied review of the same sealed bytes (facts re-grounded, CLI
    execution never re-claimed)."""
    tmp.mkdir(parents=True, exist_ok=True)  # research workspace root (distinct from the report dir)
    bundle = _research_pipeline_bundle(tmp)
    assert bundle.research.status == "SUCCEEDED"
    assert len(bundle.research_facts) == 5
    report, _ = validate_bundle(
        bundle,
        None,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        acquisition=acquisition,
    )
    return bundle, report


def _research_live_case(tmp: Path) -> tuple[object, dict]:
    return _research_case(tmp, ACQUISITION_LIVE)


def _research_supplied_case(tmp: Path) -> tuple[object, dict]:
    return _research_case(tmp, ACQUISITION_OFFLINE)


def _research_docs_page_pipeline_bundle(tmp: Path):
    """The unit-suite docs-page pipeline builder (183-b B3): a first-install
    OpenAI collect over the captured official docs-page layout derivative
    (pinned fixture bytes) whose two prose-layout limits are completed by
    the qualification mock research transport (stand-in execute_task;
    grounding, collection, bundle, validation and rendering are the real
    product code)."""
    from tests.unit.test_catalog_refresh_research import (
        _docs_page_pipeline_bundle,
    )

    patch = _attr_patch()
    try:
        return _docs_page_pipeline_bundle(tmp, patch)
    finally:
        patch.undo()


def _research_docs_page_case(tmp: Path) -> tuple[object, dict]:
    """Docs-page research-backed bundle through the real validate path:
    LIVE = the collect invocation's runner-selected scope."""
    tmp.mkdir(parents=True, exist_ok=True)  # research workspace root (distinct from the report dir)
    bundle = _research_docs_page_pipeline_bundle(tmp)
    assert bundle.research.status == "SUCCEEDED"
    assert len(bundle.research_facts) == 2
    report, _ = validate_bundle(
        bundle,
        None,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        acquisition=ACQUISITION_LIVE,
    )
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


def _fixed_sort_source() -> str:
    """The single fixed bundled script allowed in generated reports (192-a)."""
    return (
        REPO / "app" / "slaif_gateway" / "web" / "static" / "js" / "table-sort.js"
    ).read_text(encoding="utf-8")


def _assert_static_offline_html(html_text: str) -> None:
    """The executable surface is exactly the one fixed bundled sort
    script; no event handlers, external resources, or CSS fetches.
    Parsed with the shared stdlib HTML parser (no regex tag matching)."""
    auditor = _script_audit.audit_fixed_report_script(
        html_text, fixed_source=_fixed_sort_source()
    )
    assert auditor.styles, "the report must keep its inline stylesheet"
    for style_body in auditor.styles:
        assert "@import" not in style_body
        assert "url(" not in style_body
    for href in auditor.href_values():
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
        # 194-a: the first cell is the structural ordinal; the provider
        # name is the second cell.
        provider_cells = page.locator("#per-provider tbody tr:first-child td:nth-child(2)")
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
        ("supplied-collection", _supplied_collection_case),
        ("warnings", _warnings_case),
        ("large-unchanged", _large_unchanged_case),
        ("two-provider", _two_provider_case),
        ("price-change", _price_change_case),
        ("fx-required", _fx_required_case),
        ("research-live", lambda: _research_live_case(tmp / "research-live-ws")),
        ("research-supplied", lambda: _research_supplied_case(tmp / "research-supplied-ws")),
        ("research-docs-page",
         lambda: _research_docs_page_case(tmp / "research-docs-page-ws")),
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
    "supplied-collection": {
        "has_sources": True,
        "pdf": False,
        "visible": (
            "Collection details",
            "historical provenance",
            "supplied-collection scope",
            "reviewed offline",
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
    "research-live": {
        "has_sources": True,
        "pdf": False,
        "visible": (
            "research 5/5 re-grounded",
            "Research evidence (semantic fallback)",
            "Mock model (declaration)",
            "live-collection scope",
        ),
    },
    "research-supplied": {
        "has_sources": True,
        "pdf": False,
        "visible": (
            "research 5/5 re-grounded",
            "Research evidence (semantic fallback)",
            "Mock model (declaration)",
            "supplied-collection scope",
        ),
    },
    "research-docs-page": {
        "has_sources": True,
        "pdf": False,
        "visible": (
            "research 2/2 re-grounded",
            "Research evidence (semantic fallback)",
            "Mock model (declaration)",
            "live-collection scope",
        ),
    },
}


def test_browser_layout_all_cases(playwright, case_html) -> None:
    metrics: dict = {}
    out_dir: Path = case_html["_out"]
    for case in (
        "first-install",
        "ready",
        "collection",
        "supplied-collection",
        "warnings",
        "blocked",
        "large-unchanged",
        "two-provider",
        "price-change",
        "fx-required",
        "research-live",
        "research-supplied",
        "research-docs-page",
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


def test_browser_report_sort_script_js_on(playwright, case_html) -> None:
    """192-a: with JavaScript enabled the report must still perform exactly
    one network request (the document itself), and real header-hyperlink
    clicks must sort the rendered rows (193-a): aria-sort none → ascending
    → descending, visible row order following, tables independent."""
    html_path = case_html["two-provider"]
    requests: list[str] = []
    browser = playwright.chromium.launch()
    try:
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            java_script_enabled=True,
        )
        page = context.new_page()
        page.on("request", lambda req: requests.append(f"{req.resource_type}:{req.url}"))
        page.goto(html_path.as_uri())
        assert requests == ["document:" + html_path.as_uri()], (
            f"JS-on report made extra requests: {requests}"
        )

        def prov_order() -> list[str]:
            rows = page.locator("#per-provider tbody tr")
            return [
                # 194-a: first cell is the structural ordinal column.
                rows.nth(i).locator("td").nth(1).inner_text()
                for i in range(rows.count())
            ]

        # Field detail table of the single NEW model in this fixture:
        # fixed business field order, unsorted at load.
        field_table = page.locator(
            'details:has(summary:has-text("New models")) table[data-sortable]'
        ).first
        assert field_table.count() == 1
        rows = field_table.locator("tbody tr")
        count = rows.count()
        assert count >= 2
        # 194-a: first cell is the structural ordinal; the field name is
        # the second cell. Server-rendered ordinals are 1..N in the
        # initial business order.
        initial = [rows.nth(i).locator("td").nth(1).inner_text() for i in range(count)]
        assert [
            rows.nth(i).locator("td").first.inner_text() for i in range(count)
        ] == [str(i + 1) for i in range(count)]
        assert initial[0] == "display_name", f"business order lost: {initial}"
        assert initial != sorted(initial), "fixture field order must not pre-sort"
        # The structural ordinal header is plain (no aria-sort, no link);
        # the sortable "Field" header starts unsorted.
        ordinal_th = field_table.locator("thead th").first
        assert ordinal_th.get_attribute("data-ordinal") is not None
        assert ordinal_th.locator("a.ts-link").count() == 0
        field_th = field_table.locator("thead th").filter(has_text="Field")
        assert field_th.get_attribute("aria-sort") == "none"

        # Independent real table order before any click (this fixture's
        # per-provider summary is alphabetized at render time).
        prov_before = prov_order()
        assert prov_before == ["openai", "openrouter"], prov_before

        field_th.locator("a.ts-link").click()
        assert field_th.get_attribute("aria-sort") == "ascending"
        ascending = [
            field_table.locator("tbody tr").nth(i).locator("td").nth(1).inner_text()
            for i in range(count)
        ]
        assert ascending == sorted(initial), f"ascending sort wrong: {ascending}"
        assert ascending != initial
        # 194-a: the ordinal column renumbers 1..N in the NEW displayed
        # order after the sort.
        assert [
            field_table.locator("tbody tr").nth(i).locator("td").first.inner_text()
            for i in range(count)
        ] == [str(i + 1) for i in range(count)]
        assert prov_order() == prov_before, "independent table must not move"

        field_th.locator("a.ts-link").click()
        assert field_th.get_attribute("aria-sort") == "descending"
        descending = [
            field_table.locator("tbody tr").nth(i).locator("td").nth(1).inner_text()
            for i in range(count)
        ]
        assert descending == list(reversed(ascending)), (
            f"descending sort wrong: {descending}"
        )

        # Numeric column in the per-provider summary: openai New=1,
        # openrouter New=0. Ascending must flip to openrouter first;
        # descending flips back to openai first.
        new_header = page.locator("#per-provider thead th").filter(has_text="New")
        new_header.locator("a.ts-link").click()
        assert new_header.get_attribute("aria-sort") == "ascending"
        assert prov_order() == ["openrouter", "openai"], "numeric ascending wrong"
        new_header.locator("a.ts-link").click()
        assert new_header.get_attribute("aria-sort") == "descending"
        assert prov_order() == ["openai", "openrouter"], "numeric descending wrong"

        # The fixed script is offline: still exactly one request after a
        # full round of real interaction.
        assert requests == ["document:" + html_path.as_uri()], (
            f"fixed sort script caused requests: {requests}"
        )
    finally:
        browser.close()
