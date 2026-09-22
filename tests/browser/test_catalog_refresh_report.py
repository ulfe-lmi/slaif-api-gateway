"""Browser file-URL layout tests for the catalog-refresh REVIEW.html.

Standalone on purpose: no gateway server, PostgreSQL, Redis, TEST_DATABASE_URL,
or provider dependency. Real pipeline documents (CLI-published sealed runs for
first-install and blocked; in-process validate+render for the rest — the same
pure functions the CLI uses) are opened as ``file://`` URLs in a
JavaScript-disabled Chromium context with full request recording.

Geometry is measured with bounding boxes (not substring presence): the first
1440x900 viewport must contain the decision dashboard for every canonical
case, and no page-wide horizontal overflow is allowed at 1440, 1280, or 375
px, collapsed or fully expanded. All document content sits inside ``main``,
so the page's right edge is the maximum right edge of ``main`` plus its wide
leaves (tables, nowrap chips/spans, code, pre) — that container set is what
is scanned, JS-free.

Run:  python -m pytest tests/browser -m playwright
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.playwright

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "catalog_refresh"
SCREENSHOTS = FIXTURES / "browser-screenshots"
PRINT_DIR = FIXTURES / "report-layout" / "print"

# Reuse the unit-suite pipeline builders (the same code the CLI drives).
# Qualified import (repo root on sys.path via ``python -m pytest``) avoids a
# basename collision with this file's own pytest module name. The plain
# path entry below is needed for that module's internal bare imports.
sys.path.insert(0, str(REPO / "tests" / "unit"))

from tests.unit.test_catalog_refresh_report import (  # noqa: E402
    _big_unchanged_case as _report_big_unchanged_case,
    _baseline as _unit_baseline,
    _report_for as _unit_report_for,
)
from tests.unit.test_catalog_refresh_source_evidence import (  # noqa: E402
    DEFAULT_PRICES as _default_prices,
    set_openrouter_evidence as _set_openrouter_evidence,
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
    sql_capture_for_mode,
    validate_bundle,
)

playwright_sync = pytest.importorskip("playwright.sync_api")

DASHBOARD_SELECTORS = (
    ".state",
    "#scope-baseline",
    "#checks",
    "#per-provider",
    "#fx",
    "#run-identity-compact",
)

# Elements that can widen the page. All document content sits inside <main>
# (max-width 1160px) and every text leaf wraps (overflow-wrap / word-break),
# except: tables (min-content can exceed their container), nowrap chips and
# numeric cells, and pre blocks (wrapped, but scanned for safety).
OVERFLOW_SCAN_SELECTORS = "main, table, pre, .chip, .kvchip, td.num"

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
    return bundle, _unit_report_for(bundle, _unit_baseline())


def _warnings_case() -> tuple[object, dict]:
    """Aged-source READY_WITH_WARNINGS (mirrors the unit-suite case)."""
    from datetime import UTC, datetime, timedelta

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
    return bundle, _unit_report_for(bundle, _unit_baseline())


def _large_unchanged_case() -> tuple[object, dict]:
    bundle, baseline = _report_big_unchanged_case(80)
    report, _ = validate_bundle(
        bundle,
        baseline,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
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


def _max_right_edge(page) -> float:
    """JS-free right-edge scan of the elements that can widen the page."""
    max_right = 0.0
    for element in page.locator(OVERFLOW_SCAN_SELECTORS).all():
        box = element.bounding_box()
        if box is not None:
            max_right = max(max_right, box["x"] + box["width"])
    return max_right


def _check_case(
    playwright,
    case: str,
    html_path: Path,
    has_sources: bool,
    take_screenshot: bool,
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

        # 1440x900: the decision dashboard is inside the first viewport.
        boxes = {}
        for selector in DASHBOARD_SELECTORS:
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
        case_metrics["state_visible_text"] = page.locator(".state").inner_text()[:160]

        # No page-wide horizontal overflow at 1440 (collapsed).
        max_right = _max_right_edge(page)
        assert max_right <= 1440, f"page-wide horizontal overflow at 1440: {max_right:.1f}"
        case_metrics["max_element_right_1440"] = round(max_right, 1)

        # Screenshot: first 1440x900 viewport of the current renderer.
        if take_screenshot:
            SCREENSHOTS.mkdir(parents=True, exist_ok=True)
            shot = SCREENSHOTS / f"{case}.png"
            page.screenshot(
                path=str(shot), clip={"x": 0, "y": 0, "width": 1440, "height": 900}
            )
            case_metrics["screenshot"] = str(shot.relative_to(REPO))

        # 1280x800 and 375px: fresh loads at each viewport (the way a user
        # sees those widths) — no page-wide horizontal overflow. Fresh pages
        # avoid stale geometry from the 1440 pass: closed <details> content
        # can report 1440-era boxes after a same-page resize in headless
        # Chromium, which a real narrow-viewport user never sees.
        for width, height in ((1280, 800), (375, 812)):
            narrow = context.new_page()
            narrow_requests: list[str] = []
            narrow.on("request", lambda req, _r=narrow_requests: _r.append(req.url))
            try:
                narrow.set_viewport_size({"width": width, "height": height})
                narrow.goto(html_path.as_uri())
                assert narrow_requests == [html_path.as_uri()], (
                    f"extra requests at {width}px: {narrow_requests}"
                )
                max_right = _max_right_edge(narrow)
                assert max_right <= width, (
                    f"page-wide horizontal overflow at {width}px (collapsed): {max_right:.1f}"
                )
                case_metrics[f"max_element_right_{width}"] = round(max_right, 1)
                if width == 375:
                    # 375 must stay usable with the evidence expanded too.
                    _open_all_details(narrow)
                    max_right_exp = _max_right_edge(narrow)
                    assert max_right_exp <= 375, (
                        f"page-wide horizontal overflow at 375px (expanded): {max_right_exp:.1f}"
                    )
                    case_metrics["max_element_right_375_expanded"] = round(max_right_exp, 1)
            finally:
                narrow.close()

        # Fully expanded: still no overflow; full digests reachable inline.
        opened = _open_all_details(page)
        case_metrics["details_opened"] = opened
        max_right_expanded = _max_right_edge(page)
        assert max_right_expanded <= 1440, (
            f"page-wide horizontal overflow at 1440 (expanded): {max_right_expanded:.1f}"
        )
        case_metrics["max_element_right_1440_expanded"] = round(max_right_expanded, 1)
        expanded_text = page.content()
        if has_sources:
            full_digests = set(re.findall(r"\b[0-9a-f]{64}\b", expanded_text))
            assert full_digests, "no full 64-hex digest visible in the expanded report"
            case_metrics["full_digests_visible"] = len(full_digests)
        findings_summary = page.locator("#all-findings > summary").inner_text()
        case_metrics["findings_summary_visible_text"] = findings_summary

        metrics[case] = case_metrics

        if case == "ready":
            # Actual browser print evidence of the expanded document.
            PRINT_DIR.mkdir(parents=True, exist_ok=True)
            pdf_path = PRINT_DIR / "ready-expanded-print.pdf"
            pdf_bytes = page.pdf(path=str(pdf_path), print_background=True)
            assert pdf_bytes[:4] == b"%PDF", "PDF does not start with %PDF"
            assert len(pdf_bytes) > 0
            case_metrics["print_pdf"] = str(pdf_path.relative_to(REPO))
            case_metrics["print_pdf_bytes"] = len(pdf_bytes)
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
        ("warnings", _warnings_case),
        ("large-unchanged", _large_unchanged_case),
        ("two-provider", _two_provider_case),
    ):
        bundle, report = builder()
        html = tmp / case / "REVIEW.html"
        html.parent.mkdir(parents=True)
        html.write_bytes(render_report(bundle, report.to_dict()))
        out[case] = html
    return out


def test_browser_layout_all_cases(playwright, case_html) -> None:
    metrics: dict = {}
    has_sources = {
        "first-install": False,
        "ready": True,
        "warnings": True,
        "blocked": True,
        "large-unchanged": True,
        "two-provider": True,
    }
    canonical_screenshots = {
        "first-install",
        "ready",
        "warnings",
        "blocked",
        "large-unchanged",
    }
    for case in (
        "first-install",
        "ready",
        "warnings",
        "blocked",
        "large-unchanged",
        "two-provider",
    ):
        _check_case(
            playwright,
            case,
            case_html[case],
            has_sources[case],
            case in canonical_screenshots,
            metrics,
        )
    print("\nbrowser layout metrics (per case: viewport boxes, right edges, "
          "requests, details opened, digests, print PDF):")
    print(json.dumps(metrics, indent=1, sort_keys=True))
