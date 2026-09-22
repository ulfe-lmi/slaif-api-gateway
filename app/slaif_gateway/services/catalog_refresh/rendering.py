"""Deterministic REVIEW.html rendering and manifest building.

The renderer is a pure function of (bundle, validation report): no clock
reads, no environment access, stable ordering. Every data value is escaped;
only schema-validated http/https URLs may become links. No external
resources, no JavaScript, no event attributes, no user-controlled markup.

Layout contract (180-h): the first screen at 1440x900 is a compact decision
dashboard — state and reason, blocker/review counts, scope and baseline,
the grouped deterministic gate checklist, per-provider reconciliation
(source snapshots vs baseline comparison, clearly separated), FX current
vs proposed, the create-only execution plan, the top aggregated findings
with ranked counts and a link to the full list, and a compact run
identity — with every piece of detailed evidence available in expandable
sections of the same self-contained file. Long identifiers, URLs and
digests wrap without truncating their accessible value. Printing keeps
state borders and textual labels (colour is not relied on), wraps rather
than clips long values, and prints opened (expanded) sections in full.
Source trust labels are derived (OFFICIAL / REVIEW / BLOCKED from
provider/method/host/evidence rules), never caller-declared
"authoritative" labels (180-b, R3).
"""

from __future__ import annotations

import hashlib
import html
import json
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from slaif_gateway.schemas.catalog_refresh import RefreshBundle

_STATE_CLASS = {
    "READY": "state-ready",
    "READY_WITH_WARNINGS": "state-review",
    "BLOCKED": "state-blocked",
}
_EVIDENCE_CLASS = {
    "VERIFIED": "ev-verified",
    "N/A": "ev-na",
    "REVIEW": "ev-review",
    "BLOCKED": "ev-blocked",
}
_EVIDENCE_CHIP = {
    "VERIFIED": "chip-verified",
    "N/A": "chip-na",
    "REVIEW": "chip-review",
    "BLOCKED": "chip-blocked",
}
_EVIDENCE_RANK = {"BLOCKED": 3, "REVIEW": 2, "VERIFIED": 1, "N/A": 0}
_CLASSIFICATION_CLASS = {
    "OFFICIAL": "ev-verified",
    "REVIEW": "ev-review",
    "BLOCKED": "ev-blocked",
    "N/A": "ev-na",
}
_COUNT_KEYS = (
    "selected",
    "considered",
    "ready",
    "new",
    "changed",
    "unchanged",
    "excluded",
    "blocked",
    "disappeared",
    "deprecated",
    "not_fetched",
    "out_of_scope_facts",
)
_BASE_KEYS = ("new", "changed", "unchanged", "excluded", "blocked", "disappeared", "deprecated", "not_fetched")
# Display grouping of the existing deterministic gates (worst state per
# group; every individual gate keeps its own state and detail).
_GATE_GROUPS = (
    ("Source evidence", ("sources",)),
    ("Schema & pricing completeness", ("schema", "pricing.complete")),
    ("Pairing & supported capabilities", ("pairing", "unsupported")),
    ("Changes & reconciliation", ("changes", "completeness")),
    ("Import plan validation", ("import.routes", "import.pricing", "import.fx")),
)
# Concise human labels for recurring finding codes; the exact code is
# always shown alongside.
_FINDING_LABELS = {
    "source_stale_review": "source snapshot older than the review threshold",
    "source_stale_blocked": "source snapshot older than the block threshold",
    "source_warning": "source carries a warning",
    "source_truncated_optional": "optional source was truncated",
    "source_evidence_parse_failed": "evidence snapshot failed to parse",
    "source_provenance_review": "provenance requires review",
    "source_provenance_blocked": "provenance is blocked",
    "future_source_timestamp": "source timestamp is in the future",
    "missing_pricing": "pricing is missing",
    "missing_required_dimension": "required pricing dimension is missing",
    "missing_required_selection": "required selection is missing",
    "missing_route": "route is missing",
    "model_deprecated": "model is deprecated",
    "model_disappeared": "model absent from the source set (observation, not a delete)",
    "price_moved_review": "price movement beyond the review threshold",
    "price_zero_transition": "price moved to or from zero",
    "route_upstream_contradiction": "route and upstream model disagree",
    "unsupported_capability_excluded": "model excluded (unsupported capability)",
    "baseline_ambiguous_rows": "ambiguous baseline rows",
    "evidence_too_large": "evidence exceeds its size bound",
    "currency_inconsistency": "inconsistent currency",
    "CURRENCY_MISMATCH": "currency mismatch",
    "fx_stale_review": "FX quote older than the review threshold",
    "fx_stale_blocked": "FX quote older than the block threshold",
    "fx_moved_review": "FX movement beyond the review threshold",
    "fx_missing_required_pair": "required FX pair is missing",
    "fx_contradictory_rates": "contradictory FX rates",
    "fx_invalid_reciprocal": "invalid FX reciprocal derivation",
    "fx_no_publication_date": "FX quote has no publication date",
    "fx_future_publication": "FX publication date is in the future",
    "fx_baseline_ambiguous": "ambiguous FX baseline rows",
    "fx_row_invalid": "invalid FX row",
    "fx_provenance_invalid_reference": "FX source reference invalid",
}

_CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 10px 16px; color: #1a202c; background: #ffffff; line-height: 1.35; }
main { max-width: 1160px; margin: 0 auto; }
h1 { font-size: 1.15rem; margin: 0 0 1px; }
h2 { font-size: 0.95rem; margin: 0 0 3px; }
h3 { font-size: 0.82rem; margin: 4px 0 2px; }
p.sub { color: #4a5568; margin: 0 0 5px; font-size: 0.78rem; }
.banner-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: stretch; margin: 4px 0; }
.state { font-size: 0.95rem; font-weight: 600; padding: 5px 10px; border-radius: 6px; border: 1px solid; margin: 0; flex: 1 1 340px; }
.state-ready { background: #f0fff4; border-color: #2f855a; color: #22543d; }
.state-review { background: #fffaf0; border-color: #b7791f; color: #744210; }
.state-blocked { background: #fff5f5; border-color: #c53030; color: #742a2a; }
.chips { display: flex; flex-direction: row; flex-wrap: wrap; gap: 4px 6px; justify-content: center; align-items: center; }
.chip { display: inline-block; border: 1px solid #cbd5e0; border-radius: 999px; padding: 0 8px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; background: #f7fafc; }
.chip-blocker { border-color: #c53030; color: #742a2a; background: #fff5f5; }
.chip-review { border-color: #b7791f; color: #744210; background: #fffaf0; }
.chip-verified { border-color: #2f855a; color: #22543d; background: #f0fff4; }
.chip-na { border-color: #cbd5e0; color: #718096; background: #ffffff; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 6px 0; }
.card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px 10px 6px; min-width: 0; }
.card h2 { border-bottom: 1px solid #edf2f7; padding-bottom: 2px; }
.card + .card { margin-top: 10px; }
.grid-2 .card + .card { margin-top: 0; }
dl.kv { display: grid; grid-template-columns: max-content 1fr; gap: 0 10px; margin: 2px 0 0; font-size: 0.78rem; }
dl.kv dt { font-weight: 600; color: #2d3748; }
dl.kv dd { margin: 0; overflow-wrap: anywhere; }
.gate-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.gate-group-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #718096; margin: 5px 0 1px; }
.gate-grid { display: grid; grid-template-columns: 1fr; gap: 0; font-size: 0.78rem; }
.gate-line { margin: 1px 0; overflow-wrap: anywhere; }
.gate-line .muted { font-size: 0.78rem; }
table { border-collapse: collapse; width: 100%; margin: 3px 0 6px; font-size: 0.78rem; }
th, td { border: 1px solid #cbd5e0; padding: 2px 5px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #f7fafc; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.wrap { word-break: break-all; }
.plan-blocked { background: #fff5f5; border: 1px solid #c53030; color: #742a2a; border-radius: 6px; padding: 5px 9px; font-weight: 600; margin: 4px 0; font-size: 0.8rem; }
.plan-ok { background: #f0fff4; border: 1px solid #2f855a; color: #22543d; border-radius: 6px; padding: 5px 9px; margin: 4px 0; font-size: 0.8rem; }
ul.plan-list { margin: 3px 0 0; padding-left: 18px; font-size: 0.8rem; }
.findings-link { font-size: 0.78rem; margin: 2px 0 0; }
.runline { color: #4a5568; font-size: 0.78rem; margin: 4px 0 0; overflow-wrap: anywhere; }
.runline code { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0 4px; }
.countsline { font-size: 0.78rem; color: #2d3748; margin: 4px 0 3px; }
.pp-footnote { font-size: 0.74rem; }
.kvchip { display: inline-block; border: 1px solid #e2e8f0; background: #f7fafc; border-radius: 4px; padding: 0 6px; margin: 1px 2px 1px 0; white-space: nowrap; font-variant-numeric: tabular-nums; }
details { margin: 7px 0; border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px 9px; }
summary { cursor: pointer; font-weight: 600; font-size: 0.86rem; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.8rem; }
pre { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
.muted { color: #718096; }
.ev-verified { color: #22543d; font-weight: 600; }
.ev-na { color: #718096; }
.ev-review { color: #744210; font-weight: 600; }
.ev-blocked { color: #742a2a; font-weight: 700; }
.sev-BLOCKER { color: #742a2a; font-weight: 700; }
.sev-REVIEW { color: #744210; font-weight: 600; }
.sev-INFO { color: #2d3748; }
a { color: #2b6cb0; overflow-wrap: anywhere; }
.src-card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 10px; margin: 6px 0; }
.src-card h3 { margin: 2px 0 4px; }
footer { margin-top: 20px; color: #718096; font-size: 0.78rem; border-top: 1px solid #e2e8f0; padding-top: 8px; overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .grid-2 { display: block; }
  .grid-2 .card { margin-bottom: 8px; }
  .grid-2 .card + .card { margin-top: 0; }
  .gate-columns { display: block; }
  .gate-grid { display: block; }
}
@media print {
  body { padding: 0; font-size: 10.5px; }
  main { max-width: none; }
  .grid-2 { display: block; }
  .grid-2 .card { margin: 6px 0 10px; }
  .card, details, .src-card { border-color: #000; }
  .state, .chip { border-width: 2px; }
  .sev-BLOCKER, .ev-blocked { text-decoration: underline; }
  .sev-REVIEW, .ev-review { text-decoration: underline dotted; }
  .muted { color: #222222; }
  table { font-size: 9.5px; margin: 4px 0 8px; }
  th, td { padding: 2px 4px; }
  tr { page-break-inside: avoid; }
  h1, h2, h3 { page-break-after: avoid; }
  a { color: #000000; }
  pre { font-size: 9px; }
}
"""


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_href(url: str) -> str | None:
    """Only schema-validated http/https URLs may become links."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return url


def _link(url: str, label: str | None = None) -> str:
    href = safe_href(url)
    if href is None:
        return f"<span class='muted wrap'>{esc(url or 'no url')}</span>"
    return f"<a href='{esc(href)}' rel='noopener noreferrer'>{esc(label or url)}</a>"


def _cell(value: Any) -> str:
    if value is None:
        return "<span class='muted'>—</span>"
    return esc(value)


def _fmt_decimal(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        return str(Decimal(str(value)))
    except InvalidOperation:
        return esc(value)


def _signed_percent(ratio: str | None) -> str:
    """Render a stored ratio (e.g. '0.250000') as a signed percentage."""
    if ratio is None:
        return "—"
    try:
        percent = (Decimal(ratio) * Decimal(100)).quantize(Decimal("0.001"))
    except InvalidOperation:
        return esc(ratio)
    text = f"{percent:f}"
    if percent > 0:
        return f"+{text} %"
    return f"{text} %"


def _finding_label(code: str) -> str:
    label = _FINDING_LABELS.get(code)
    if not label:
        return code
    return f"{esc(code)} — {esc(label)}"


def _source_index(bundle: RefreshBundle) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source in bundle.sources:
        index[f"{source.provider}|{source.model}|{source.source_kind}"] = {
            "url": source.url,
            "retrieved_at": source.retrieved_at.isoformat(),
            "published_at": source.published_at.isoformat() if source.published_at else None,
            "extractor": source.extractor,
            "extraction": source.extraction,
            "truncated": source.truncated,
            "sha256": source.content_sha256,
        }
    return index


def _assessment_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Derived trust assessments from validation (never caller-declared)."""
    return {
        f"{item['provider']}|{item['model']}|{item['source_kind']}": item
        for item in report.get("sources", [])
    }


def _evidence_label(assessment: dict[str, Any] | None) -> str:
    if not assessment:
        return "—"
    state = assessment.get("evidence_state")
    if state == "verified":
        return "evidence verified (bytes match declared digest)"
    if state == "invalid":
        return "evidence contradicts declared digest"
    return "evidence not supplied (not verifiable offline)"


def _provenance_cells(
    provenance: Any,
    source_index: dict[str, dict[str, Any]],
    assessments: dict[str, dict[str, Any]],
) -> list[str]:
    """Provenance cells with *derived* trust classification, never a
    caller-declared "authoritative" label."""
    cells: list[str] = []
    for key in provenance.sources:
        source = source_index.get(key, {})
        assessment = assessments.get(key)
        parts: list[str] = []
        classification = assessment.get("classification") if assessment else None
        if classification:
            parts.append(f"<span class='{_CLASSIFICATION_CLASS.get(classification, 'ev-na')}'>{esc(classification)}</span>")
        parts.append(f"<span class='wrap'>{esc(key)}</span>")
        if source:
            # The link is labeled by its own URL; trust is the derived class.
            parts.append(_link(source.get("url", "")))
            parts.append(f"retrieved {esc(source.get('retrieved_at'))}")
            if source.get("published_at"):
                parts.append(f"published {esc(source['published_at'])}")
            parts.append(f"extractor {esc(source.get('extractor'))} ({esc(source.get('extraction'))})")
            if source.get("truncated"):
                parts.append("<strong>TRUNCATED</strong>")
        if assessment:
            parts.append(f"<span class='muted'>{esc(_evidence_label(assessment))}</span>")
        cells.append("<br>".join(parts))
    return cells


def _plan_lines(report: dict[str, Any]) -> tuple[list[str], bool]:
    """Execution-plan summary lines; the boolean is True when any plan is blocked."""
    import_gates = {gate["kind"]: gate for gate in report.get("import_gates", [])}
    lines: list[str] = []
    blocked = False
    for kind in ("routes", "pricing", "fx"):
        gate = import_gates.get(kind)
        if gate is None:
            continue
        excluded = gate.get("excluded_mutations", 0)
        ready = gate.get("plan_ready_rows", 0)
        plan_blocked = gate.get("plan_blocked_rows", 0)
        if excluded or plan_blocked:
            blocked = True
            lines.append(
                f"<li>\u2022 {esc(kind)}: <strong class='ev-blocked'>BLOCKED</strong> — "
                f"{esc(ready)} create row(s) executable, {esc(excluded + plan_blocked)} row(s) require an apply "
                "operation that does not exist in this version (excluded from the executable artifact)</li>"
            )
        elif gate.get("total_rows", 0) == 0:
            lines.append(f"<li>\u2022 {esc(kind)}: nothing to create (NO CHANGES)</li>")
        else:
            lines.append(
                f"<li>\u2022 {esc(kind)}: {esc(ready)} create row(s) executable "
                "(create-only plan)</li>"
            )
    return lines, blocked


def _source_evidence_line(report: dict[str, Any]) -> str:
    """Compact truthful source-evidence summary for the decision box."""
    evidence = report.get("source_evidence", {}) or {}
    backed = evidence.get("backed_facts", []) or []
    inventory = evidence.get("inventory", {}) or {}
    evidence_models = sum(values.get("evidence_models", 0) for values in inventory.values())
    selected = sum(values.get("selected_models", 0) for values in inventory.values())
    retained = sum(values.get("retained_local_models", 0) for values in inventory.values())
    excluded = sum(
        values.get("explicitly_excluded_models", 0) + values.get("unsupported_excluded_models", 0)
        for values in inventory.values()
    )
    unexplained = sum(values.get("unexplained_omissions", 0) for values in inventory.values())
    parts = [f"{len(backed)} proposed facts bound to parsed snapshot observations"]
    parts.append(
        f"{evidence_models} model(s) in official snapshots: {selected} selected, "
        f"{retained} retained local, {excluded} excluded, {unexplained} unexplained omission(s)"
    )
    parts.append("offline replay of supplied bytes — registered deterministic parsers, not a live retrieval")
    return esc(" · ".join(parts))


def _render_gate_checklist(gates: list[dict[str, Any]]) -> list[str]:
    """Grouped deterministic checklist: worst state per group, every
    individual gate keeps its own state chip and detail."""
    by_name = {gate["name"]: gate for gate in gates}
    groups: list[str] = []
    for label, names in _GATE_GROUPS:
        members = [by_name[name] for name in names if name in by_name]
        if not members:
            continue
        worst_rank = max(_EVIDENCE_RANK.get(m["evidence"], 0) for m in members)
        worst_state = next(state for state, rank in _EVIDENCE_RANK.items() if rank == worst_rank)
        group = [
            f"<div class='gate-group-label'>{esc(label)} — "
            f"<span class='chip {_EVIDENCE_CHIP[worst_state]}'>{esc(worst_state)}</span></div>"
        ]
        group.append("<div class='gate-grid'>")
        for gate in members:
            group.append(
                "<div class='gate-line'>"
                f"<span class='chip {_EVIDENCE_CHIP.get(gate['evidence'], 'chip-na')}'>{esc(gate['evidence'])}</span> "
                f"<span>{esc(gate['name'])}</span> — <span class='muted'>{esc(gate['detail'])}</span>"
                "</div>"
            )
        group.append("</div>")
        groups.append("".join(group))
    # Any gate not covered by the display groups (future-proofing) is listed
    # individually so nothing is ever hidden.
    grouped_names = {name for _, names in _GATE_GROUPS for name in names}
    leftovers = [gate for gate in gates if gate["name"] not in grouped_names]
    if leftovers:
        group = ["<div class='gate-group-label'>Other gates</div>", "<div class='gate-grid'>"]
        for gate in leftovers:
            group.append(
                "<div class='gate-line'>"
                f"<span class='chip {_EVIDENCE_CHIP.get(gate['evidence'], 'chip-na')}'>{esc(gate['evidence'])}</span> "
                f"<span>{esc(gate['name'])}</span> — <span class='muted'>{esc(gate['detail'])}</span>"
                "</div>"
            )
        group.append("</div>")
        groups.append("".join(group))
    # Deterministic two-column flow: left column takes the 1st, 3rd, 5th...
    # group; every gate and its detail stays visible in reading order.
    parts = [
        "<div class='gate-columns'>",
        "<div class='gate-col'>" + "".join(groups[0::2]) + "</div>",
        "<div class='gate-col'>" + "".join(groups[1::2]) + "</div>",
        "</div>",
    ]
    return parts


def _render_scope_card(bundle: RefreshBundle, report: dict[str, Any]) -> str:
    counts = report.get("counts", {})
    warnings = report.get("warnings", [])
    blockers = [warning for warning in warnings if warning["severity"] == "BLOCKER"]
    reviews = [warning for warning in warnings if warning["severity"] == "REVIEW"]
    baseline = report.get("baseline", {})
    sql_checks = report.get("sql_checks", {})
    blocker_codes = sorted({warning["code"] for warning in blockers})
    review_codes = sorted({warning["code"] for warning in reviews})
    model_filter = ", ".join(esc(m) for m in bundle.selection.model_include) or "all models of selected providers"
    providers = ", ".join(esc(p) for p in bundle.selection.providers)
    return (
        "<section class='card' id='scope-baseline'>"
        "<h2>Decision — scope &amp; baseline</h2>"
        "<dl class='kv'>"
        f"<dt>Why this state</dt><dd>{esc(report['state_reason'])}</dd>"
        f"<dt>Blockers</dt><dd>{len(blockers)} finding(s)"
        + (f" — codes: {esc(', '.join(blocker_codes))}" if blocker_codes else "")
        + "</dd>"
        f"<dt>Review findings</dt><dd>{len(reviews)} finding(s)"
        + (f" — codes: {esc(', '.join(review_codes))}" if review_codes else "")
        + "</dd>"
        f"<dt>Selected scope</dt><dd>providers: {providers}; models: <span class='wrap'>{model_filter}</span>"
        f" (selected {esc(counts.get('selected', 0))}, considered {esc(counts.get('considered', 0))},"
        f" out-of-scope facts {esc(counts.get('out_of_scope_facts', 0))})</dd>"
        f"<dt>Baseline</dt><dd>{esc(baseline.get('mode'))}"
        + (f" — exported {esc(baseline.get('exported_at'))}" if baseline.get("exported_at") else " — FIRST INSTALL (explicitly empty, no database read)")
        + (f" — target {esc(baseline.get('target'))}" if baseline.get("target") else "")
        + "</dd>"
        f"<dt>Baseline SQL evidence</dt><dd>{esc(sql_checks.get('note', ''))}</dd>"
        f"<dt>Live research</dt><dd>{esc(report.get('research', {}).get('status'))} — live source retrieval is unavailable in this version; only supplied offline evidence is assessed</dd>"
        f"<dt>Source evidence</dt><dd>{_source_evidence_line(report)}</dd>"
        "</dl>"
        "</section>"
    )


def _render_per_provider_card(per_provider: dict[str, dict[str, int]], inventory: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = ["<h2>Per-provider summary</h2>"]
    if inventory:
        parts.append("<h3>Source snapshots (offline replay of supplied documents)</h3>")
        parts.append(
            "<table><thead><tr><th>Provider</th><th>models in snapshot</th><th>selected</th>"
            "<th>retained local</th><th>excluded</th><th>unexplained</th></tr></thead><tbody>"
        )
        for provider in sorted(inventory):
            values = inventory[provider]
            parts.append(
                f"<tr><td>{esc(provider)}</td>"
                f"<td class='num'>{esc(values.get('evidence_models', 0))}</td>"
                f"<td class='num'>{esc(values.get('selected_models', 0))}</td>"
                f"<td class='num'>{esc(values.get('retained_local_models', 0))}</td>"
                f"<td class='num'>{esc(values.get('explicitly_excluded_models', 0) + values.get('unsupported_excluded_models', 0))}</td>"
                f"<td class='num'>{esc(values.get('unexplained_omissions', 0))}</td></tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<p class='muted'>No source snapshots parsed for this run; only the baseline comparison below applies.</p>")
    if per_provider:
        parts.append("<h3>Baseline comparison (this run)</h3>")
        parts.append(
            "<table><thead><tr><th>Provider</th><th>new</th><th>changed</th><th>unchanged</th><th>excluded</th>"
            "<th>blocked</th><th>disappeared</th><th>deprecated</th><th>not fetched</th></tr></thead><tbody>"
        )
        for provider in sorted(per_provider):
            values = per_provider[provider]
            parts.append(
                f"<tr><td>{esc(provider)}</td>"
                + "".join(f"<td class='num'>{esc(values.get(key, 0))}</td>" for key in _BASE_KEYS)
                + "</tr>"
            )
        parts.append("</tbody></table>")
    parts.append(
        "<p class='muted pp-footnote'>Different populations, not additive: source snapshots = supplied "
        "documents replayed offline; baseline comparison = rows in effect at review time. No count is "
        "invented for a source that did not parse.</p>"
    )
    return "<section class='card' id='per-provider'>" + "".join(parts) + "</section>"


def _render_fx_card(report: dict[str, Any]) -> str:
    comparisons = report.get("fx_comparisons", [])
    parts: list[str] = ["<h2>FX (current vs proposed, native → EUR)</h2>"]
    if comparisons:
        parts.append("<table><thead><tr><th>Pair</th><th>Current rate</th><th>Proposed rate</th><th>Δ</th><th>State</th><th>Publication</th><th>Source</th></tr></thead><tbody>")
        for row in comparisons:
            current = _fmt_decimal(row.get("current_rate"))
            if row.get("current_derived"):
                current += " <span class='muted'>(derived reciprocal)</span>"
            proposed = _fmt_decimal(row.get("proposed_rate"))
            if row.get("derived"):
                proposed += f" <span class='muted'>(reciprocal of supplied {esc(row.get('source_pair'))})</span>"
            parts.append(
                f"<tr><td>{esc(row.get('pair'))}</td>"
                f"<td class='num'>{current}</td>"
                f"<td class='num'>{proposed}</td>"
                f"<td class='num'>{_signed_percent(row.get('delta_pct'))}</td>"
                f"<td>{esc(row.get('state'))}</td>"
                f"<td>{_cell(row.get('published_at'))}</td>"
                f"<td>{_link(row.get('source') or '')}</td></tr>"
            )
        parts.append("</tbody></table>")
        parts.append("<p class='muted'>Current rates are the baseline (local runtime) rows; proposed rates come from the bundle. A 'derived reciprocal' is the reviewed inversion of the supplied quote, not an independent observation.</p>")
    else:
        fx_gate = next((g for g in report.get("gates", []) if g["name"] == "import.fx"), None)
        if fx_gate is not None:
            parts.append(
                f"<p class='muted'>{esc(fx_gate['detail'])}"
                + (" (not an error)." if fx_gate["evidence"] == "N/A" else "")
                + "</p>"
            )
        else:
            parts.append("<p class='muted'>FX not required (all selected prices are EUR; shown as N/A, not an error).</p>")
    return "<section class='card' id='fx'>" + "".join(parts) + "</section>"


def _render_findings_card(warnings: list[dict[str, Any]]) -> str:
    parts: list[str] = ["<h2>Important findings (aggregated)</h2>"]
    if not warnings:
        parts.append("<p class='muted'>No blockers and no review findings.</p>")
        return "<section class='card' id='findings-top'>" + "".join(parts) + "</section>"
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for warning in warnings:
        key = (warning["severity"], warning["code"])
        entry = grouped.setdefault(key, {"count": 0, "details": []})
        entry["count"] += 1
        if len(entry["details"]) < 3:
            entry["details"].append(f"{warning.get('provider') or ''}/{warning.get('model') or ''}: {warning['detail']}".strip(": "))
    ordered = sorted(grouped.items(), key=lambda item: (item[0][0] != "BLOCKER", item[0][1], item[1]["count"] * -1))
    shown = ordered[:3]
    parts.append("<table><thead><tr><th>Severity</th><th>Code</th><th>Count</th><th>First example in group</th></tr></thead><tbody>")
    for (severity, code), entry in shown:
        parts.append(
            f"<tr><td class='sev-{esc(severity)}'>{esc(severity)}</td>"
            f"<td>{_finding_label(code)}</td>"
            f"<td class='num'>{esc(entry['count'])}</td>"
            f"<td>{esc(entry['details'][0]) if entry['details'] else '—'}</td></tr>"
        )
    parts.append("</tbody></table>")
    if len(ordered) > 3:
        parts.append(
            f"<p class='findings-link'>Showing the top {len(shown)} of {len(ordered)} finding groups, ranked by severity — "
            f"<a href='#all-findings'>all {len(warnings)} findings with per-item detail</a>.</p>"
        )
    else:
        parts.append(f"<p class='findings-link'><a href='#all-findings'>All {len(warnings)} findings with per-item detail</a>.</p>")
    return "<section class='card' id='findings-top'>" + "".join(parts) + "</section>"


def _render_first_screen(bundle: RefreshBundle, report: dict[str, Any]) -> list[str]:
    state = report["state"]
    counts = report.get("counts", {})
    warnings = report.get("warnings", [])
    blockers = [warning for warning in warnings if warning["severity"] == "BLOCKER"]
    reviews = [warning for warning in warnings if warning["severity"] == "REVIEW"]
    per_provider = report.get("per_provider", {})
    inventory = (report.get("source_evidence", {}) or {}).get("inventory", {}) or {}

    parts: list[str] = [
        "<div class='banner-row'>",
        f"<p class='state {_STATE_CLASS[state]}'><strong>{esc(state)}</strong> — {esc(report['state_reason'])}</p>",
        "<div class='chips'>",
        f"<span class='chip {'chip-blocker' if blockers else ''}'>BLOCKERS {len(blockers)}</span>",
        f"<span class='chip {'chip-review' if reviews else ''}'>REVIEW findings {len(reviews)}</span>",
        f"<span class='chip'>all findings {len(warnings)}</span>",
        "</div>",
        "</div>",
        "<div class='grid-2'>",
        _render_scope_card(bundle, report),
        "<section class='card' id='checks'><h2>Gate checklist — deterministic</h2>"
        + "".join(_render_gate_checklist(report.get("gates", [])))
        + "</section>",
        _render_per_provider_card(per_provider, inventory),
        _render_fx_card(report),
        "</div>",
    ]

    # Compact run identity and recomputed counts close the dashboard, so the
    # decision facts (state, scope/baseline, checklist, reconciliation, FX,
    # identity) share one viewport at 1440x900.
    parts.append(
        f"<p class='runline' id='run-identity-compact'>Run <code class='wrap'>{esc(report.get('run_id'))}</code> · generated at "
        f"{esc(report.get('generated_at'))} (run time) · revision {esc(bundle.revision.slaif_revision)} "
        f"(schema {esc(bundle.revision.schema_version)}, renderer {esc(bundle.revision.renderer_version)}, "
        f"policy v{esc(report.get('policy_version'))}) · profile {esc(bundle.profile.name)} {esc(bundle.profile.endpoint)} · "
        "<a href='#run-identity'>full identity</a></p>"
    )
    parts.append(
        "<p class='countsline'><strong>Counts (recomputed):</strong> "
        + " ".join(f"<span class='kvchip'>{esc(key.replace('_', ' '))} {esc(counts.get(key, 0))}</span>" for key in _COUNT_KEYS)
        + "</p>"
    )
    parts.append(_render_findings_card(warnings))

    # Create-only execution plan (visually impossible to mistake for READY when blocked).
    plan_lines, plan_blocked = _plan_lines(report)
    if plan_lines:
        parts.append("<section class='card' id='plan'><h2>Execution plan (create-only)</h2>")
        if plan_blocked or state == "BLOCKED":
            parts.append(
                "<p class='plan-blocked'>At least one execution plan is BLOCKED: existing-row updates/supersessions "
                "are not apply operations in this version. Only create rows enter the executable artifacts.</p>"
            )
        elif state == "READY":
            parts.append("<p class='plan-ok'>All executable plans are create-only and pass their import gates.</p>")
        else:
            parts.append(
                "<p class='plan-ok'>All executable plans are create-only and pass their import gates; the "
                "READY_WITH_WARNINGS state comes from the review findings listed above, not from the plan.</p>"
            )
        parts.append("<ul class='plan-list'>" + "".join(plan_lines) + "</ul>")
        parts.append("</section>")
    return parts


def _render_changes(bundle: RefreshBundle, report: dict[str, Any], source_index: dict[str, dict[str, Any]]) -> list[str]:
    parts: list[str] = ["<h2>What changed</h2>"]
    comparisons = report.get("price_comparisons", [])
    changed_comparisons = [row for row in comparisons if row["state"] not in ("UNCHANGED",)]
    if changed_comparisons:
        parts.append("<h3>Price changes (old → new, with unit and currency; source timestamps are never counted as price changes)</h3>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Dimension</th><th>Old</th><th>Old currency</th><th>New</th><th>New currency</th><th>Δ (signed)</th><th>State</th></tr></thead><tbody>")
        for row in changed_comparisons:
            parts.append(
                f"<tr><td>{esc(row['provider'])}</td><td class='wrap'>{esc(row['model'])}</td><td>{esc(row['dimension'])}</td>"
                f"<td class='num'>{_fmt_decimal(row['old'])}</td><td>{_cell(row['currency_old'])}</td>"
                f"<td class='num'>{_fmt_decimal(row['new'])}</td><td>{_cell(row['currency_new'])}</td>"
                f"<td class='num'>{_signed_percent(row['percent_change'])}</td>"
                f"<td>{esc(row['state'])}</td></tr>"
            )
        parts.append("</tbody></table>")
        parts.append(
            "<p class='muted'>Displayed percentages are rounded to 0.001 %; the gate decision uses the exact "
            "stored ratio, so a strictly above-threshold movement can display at the threshold value.</p>"
        )
    else:
        parts.append("<p class='muted'>No price movements among comparable selected dimensions.</p>")

    dispositions = report.get("dispositions", [])
    changed_models = [d for d in dispositions if d["disposition"] == "CHANGED"]
    if changed_models:
        parts.append("<h3>Route / model attribute changes (current → proposed, with reason)</h3>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Changed fields (current → proposed)</th><th>Proposed route</th><th>Reason</th></tr></thead><tbody>")
        for d in changed_models:
            route = next((r for r in bundle.routes if r.provider == d["provider"] and r.requested_model == d["model"]), None)
            proposed = (
                f"<span class='wrap'>{esc(route.upstream_model)}</span> via {esc(route.provider)}"
                f" (priority {esc(route.priority)}, streaming {esc(route.supports_streaming)}, visible {esc(route.visible_in_models)})"
                if route
                else "—"
            )
            reason = (
                "existing-row update/supersession; no apply operation exists in this version — excluded from the executable artifact"
            )
            parts.append(
                f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td><td>{esc(d['detail'])}</td><td>{proposed}</td><td>{esc(reason)}</td></tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<p class='muted'>No route or model attribute changes.</p>")

    unchanged_count = sum(1 for d in dispositions if d["disposition"] == "UNCHANGED")
    if unchanged_count:
        parts.append(
            f"<p><strong>Unchanged: {unchanged_count} model(s)</strong> — collapsed by default in "
            f"<a href='#unchanged'>the unchanged section</a>; disappearance above is an observation, not a delete.</p>"
        )
    else:
        parts.append(
            "<p><strong>Unchanged: 0 model(s)</strong> — no unchanged section exists; "
            "disappearance above is an observation, not a delete.</p>"
        )
    return parts


def _kv_block(pairs: list[tuple[str, Any]], html_keys: frozenset[str] = frozenset()) -> str:
    """Label/value rows; values in html_keys are already-safe rendered HTML
    (e.g. safe_href links), every other value is escaped."""
    rows = []
    for label, value in pairs:
        if value is None:
            cell = "—"
        elif label in html_keys:
            cell = str(value)
        else:
            cell = esc(value)
        rows.append(f"<dt>{esc(label)}</dt><dd>{cell}</dd>")
    return "<dl class='kv'>" + "".join(rows) + "</dl>"


def _render_details(bundle: RefreshBundle, report: dict[str, Any], source_index: dict[str, dict[str, Any]]) -> list[str]:
    assessments = _assessment_index(report)
    parts: list[str] = []
    dispositions = report.get("dispositions", [])
    models_by_key = {(m.provider, m.model): m for m in bundle.models}

    def group(kind: str) -> list[dict[str, Any]]:
        return [d for d in dispositions if d["disposition"] == kind]

    metadata_by_key = {
        (row["provider"], row["model"]): row["fields"] for row in report.get("baseline_metadata", [])
    }

    def model_detail_rows(rows: list[dict[str, Any]], show_provenance: bool) -> list[str]:
        out: list[str] = []
        for d in rows:
            facts = models_by_key.get((d["provider"], d["model"]))
            out.append(f"<h3>{esc(d['provider'])}/<span class='wrap'>{esc(d['model'])}</span> — {esc(d['detail'])}</h3>")
            preserved = metadata_by_key.get((d["provider"], d["model"]))
            if preserved:
                pairs = ", ".join(f"{esc(key)}={esc(value)}" for key, value in sorted(preserved.items()))
                out.append(f"<p class='muted'>Preserved baseline monetary metadata (active baseline row): {pairs}</p>")
            if facts is not None:
                out.append("<table><thead><tr><th>Field</th><th>Proposed</th>" + ("<th>Provenance (derived classification)</th>" if show_provenance else "") + "</tr></thead><tbody>")
                rows_out = [
                    ("display_name", facts.display_name),
                    ("context_length", facts.context_length),
                    ("max_output_tokens", facts.max_output_tokens),
                    ("supports_streaming", facts.supports_streaming),
                    ("capabilities", ", ".join(sorted(k for k, v in facts.capabilities.items() if v)) or "—"),
                    ("deprecated", facts.deprecated),
                ]
                for field_name, value in rows_out:
                    provenance = (
                        "<br>".join(_provenance_cells(facts.provenance, source_index, assessments)) if show_provenance else ""
                    )
                    out.append(
                        f"<tr><td>{esc(field_name)}</td><td class='wrap'>{esc(value)}</td>"
                        + (f"<td>{provenance}</td>" if show_provenance else "")
                        + "</tr>"
                    )
                out.append("</tbody></table>")
        return out

    new_models = group("NEW")
    if new_models:
        parts.append(f"<details open><summary>New models ({len(new_models)})</summary>")
        parts.extend(model_detail_rows(new_models, show_provenance=True))
        parts.append("</details>")
    changed_models = group("CHANGED")
    if changed_models:
        parts.append(f"<details open><summary>Changed models — excluded from executable artifacts ({len(changed_models)})</summary>")
        parts.extend(model_detail_rows(changed_models, show_provenance=True))
        parts.append("</details>")
    disappeared = group("DISAPPEARED")
    if disappeared:
        parts.append(f"<details open><summary>Disappeared models — retain-local, no delete ({len(disappeared)})</summary>")
        parts.append("<p class='muted'>These models exist in the baseline but were absent from the complete offline source set. This version never deletes; the local rows are retained. Disappearance is a REVIEW, not an error; outage, truncated retrieval, or missing mandatory selection is never reported as disappearance.</p>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Note</th></tr></thead><tbody>")
        for d in disappeared:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    deprecated = group("DEPRECATED")
    if deprecated:
        parts.append(f"<details><summary>Deprecated models ({len(deprecated)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Note</th></tr></thead><tbody>")
        for d in deprecated:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    excluded = group("EXCLUDED")
    if excluded:
        parts.append(f"<details><summary>Excluded (unsupported) rows ({len(excluded)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Reason</th></tr></thead><tbody>")
        for d in excluded:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    blocked = group("BLOCKED")
    if blocked:
        parts.append(f"<details open><summary>Blocked rows ({len(blocked)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Reason</th></tr></thead><tbody>")
        for d in blocked:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    not_fetched = group("NOT_FETCHED")
    if not_fetched:
        parts.append(f"<details><summary>Not fetched ({len(not_fetched)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Note</th></tr></thead><tbody>")
        for d in not_fetched:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    unchanged = group("UNCHANGED")
    if unchanged:
        parts.append(f"<details id='unchanged'><summary>Unchanged models ({len(unchanged)}) — collapsed</summary>")
        parts.append("<p class='muted'>Compared fields identical to the active baseline; no-op rows are excluded from the executable artifacts and aggregated by design.</p>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th></tr></thead><tbody>")
        for d in unchanged:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td class='wrap'>{esc(d['model'])}</td></tr>")
        parts.append("</tbody></table></details>")

    warnings = report.get("warnings", [])
    if warnings:
        parts.append(f"<details id='all-findings' open><summary>All warnings and findings ({len(warnings)})</summary>")
        parts.append("<table><thead><tr><th>Severity</th><th>Code</th><th>Provider</th><th>Model</th><th>Detail</th></tr></thead><tbody>")
        for warning in warnings:
            parts.append(
                f"<tr><td class='sev-{esc(warning['severity'])}'>{esc(warning['severity'])}</td>"
                f"<td class='wrap'>{esc(warning['code'])}</td><td>{_cell(warning['provider'])}</td>"
                f"<td class='wrap'>{_cell(warning['model'])}</td><td>{esc(warning['detail'])}</td></tr>"
            )
        parts.append("</tbody></table></details>")
    else:
        parts.append("<details id='all-findings'><summary>All warnings and findings (0)</summary><p class='muted'>None.</p></details>")

    parts.append("<details id='validator-outputs'><summary>Full validator outputs (validation.json)</summary>")
    parts.append(f"<pre>{esc(json.dumps({k: v for k, v in report.items() if k not in ('gates',)}, sort_keys=True, indent=1, default=str))}</pre></details>")

    import_gates = report.get("import_gates", [])
    if import_gates:
        parts.append("<details id='import-gates' open><summary>Import gate details (schema-valid vs execution-plan-valid)</summary>")
        for gate in import_gates:
            parts.append(f"<div class='src-card'><h3>Import gate: {esc(gate['kind'])}</h3>")
            parts.append(_kv_block([
                ("Schema valid", "yes" if gate["schema_valid"] else "no"),
                ("Rows", gate["total_rows"]),
                ("Valid / invalid", f"{gate['valid_rows']} / {gate['invalid_rows']}"),
                ("Classifications", ", ".join(f"{k}={v}" for k, v in gate["classifications"].items()) or "—"),
                ("Plan ready / blocked", f"{gate['plan_ready_rows']} / {gate['plan_blocked_rows']}"),
                ("Excluded mutations", gate.get("excluded_mutations", 0)),
                ("Detail", gate["detail"]),
            ]))
            parts.append("</div>")
        parts.append("<p class='muted'>Existing create-only execution remains unchanged. Updates/supersessions are represented as changed rows above; their apply plan is BLOCKED because no apply operation exists in this version. An empty unchanged plan is a truthful NO CHANGES result, not an invalid import.</p>")
        parts.append("</details>")

    parts.append("<details id='source-inventory'><summary>Source inventory and reconciliation (trust derived, never declared)</summary>")
    if bundle.sources:
        for source in sorted(bundle.sources, key=lambda s: (s.provider, s.model, s.source_kind)):
            assessment = assessments.get(f"{source.provider}|{source.model}|{source.source_kind}", {})
            classification = assessment.get("classification", "—")
            parse_state = assessment.get("parse_state", "—")
            parts.append(f"<div class='src-card'><h3>{esc(source.provider)}/<span class='wrap'>{esc(source.model)}</span> — {esc(source.source_kind)}</h3>")
            parts.append(_kv_block([
                ("URL", _link(source.url)),
                ("Derived classification", classification),
                ("Evidence", _evidence_label(assessment or None)),
                ("Parser (registry)", assessment.get("parser") or "—"),
                ("Parse", parse_state),
                ("Models parsed", assessment.get("parsed_models", 0)),
                ("FX quotes", assessment.get("parsed_fx_quotes", 0)),
                ("Age", assessment.get("age_state", "—")),
                ("Retrieved", source.retrieved_at.isoformat()),
                ("Published", source.published_at.isoformat() if source.published_at else None),
                ("Extractor", source.extractor),
                ("Method", source.extraction),
                ("Required", source.required),
                ("Truncated", source.truncated),
                ("SHA-256 (full)", source.content_sha256),
            ], html_keys=frozenset({"URL"})))
            parts.append("</div>")
        parts.append("<p class='muted'>OFFICIAL requires the exact official host for the (provider, source kind) rule, a reviewed registered deterministic parser, supplied evidence whose bytes match the declared digest, and a successful bounded parse of those bytes. A matching digest of arbitrary bytes is not content trust: a safe URL is not an authoritative source (operator-supplied, semantic, off-host, or unverifiable-offline sources classify as REVIEW), and unsupported, contradictory, or unparseable required sources classify as BLOCKED. Supplied/cached evidence parsed offline is explicitly distinguished from live retrieval, which this process never performs.</p>")
    else:
        parts.append("<p class='muted'>No sources recorded in the bundle.</p>")
    parts.append("</details>")

    parts.extend(_render_source_evidence_details(report))

    baseline = report.get("baseline", {})
    sql_checks = report.get("sql_checks", {})
    parts.append("<details id='baseline-identity'><summary>Baseline identity (historical capture vs current checks)</summary>")
    parts.append(_kv_block([
        ("Mode", baseline.get("mode")),
        ("Capture path (this execution)", sql_checks.get("capture")),
        ("Exported at (historical capture)", baseline.get("exported_at")),
        ("Baseline document digest verified", "yes" if baseline.get("mode") not in (None, "first_install") else "n/a (first install)"),
        ("SQL checked at document export (declared)", "yes" if baseline.get("sql_checked") else "no"),
        ("SQL executed during this review", "yes" if sql_checks.get("sql_executed_during_review") else "no"),
        ("Note", sql_checks.get("note")),
        ("Target", baseline.get("target")),
        ("PostgreSQL version", baseline.get("postgres_version")),
        ("Baseline age (seconds at run time)", baseline.get("age")),
    ]))
    parts.append("<p class='muted'>The unkeyed content digest is an integrity check on the document bytes; it is not authentication and not proof that the baseline is current, and a supplied document's capture metadata is a declaration, not an independent attestation. A connection failure must never become an empty bootstrap; bootstrap requires an explicitly empty first-install baseline.</p>")
    parts.append("</details>")

    # Expanded run identity (technical identifiers off the first screen).
    artifacts = report.get("artifacts", {})
    parts.append("<details id='run-identity'><summary>Run identity (expanded)</summary>")
    parts.append(_kv_block([
        ("Run ID", report.get("run_id")),
        ("Generated at (run time)", report.get("generated_at")),
        ("SLAIF revision", bundle.revision.slaif_revision),
        ("Schema version", bundle.revision.schema_version),
        ("Renderer version", bundle.revision.renderer_version),
        ("Policy version", report.get("policy_version")),
        ("Profile", f"{bundle.profile.name} — {bundle.profile.endpoint}"
                     + (" (streaming)" if bundle.profile.supports_streaming else "")
                     + (" (local models visible)" if bundle.profile.local_models_visible else "")),
        ("Research", f"{report.get('research', {}).get('status')} (extractor {report.get('research', {}).get('extractor_version')}, tool {report.get('research', {}).get('tool_version')})"),
        ("Routes artifact sha256", artifacts.get("routes_tsv_sha256")),
        ("Pricing artifact sha256", artifacts.get("pricing_tsv_sha256")),
        ("FX artifact sha256", artifacts.get("fx_json_sha256")),
    ]))
    parts.append("</details>")

    if bundle.notes:
        parts.append(f"<details id='bundle-notes'><summary>Bundle notes</summary><p class='wrap'>{esc(bundle.notes)}</p></details>")
    return parts


def _obs_card(item: dict[str, Any]) -> list[str]:
    """One observed price/evidence value as a readable label/value group."""
    parts = [f"<div class='src-card'><h3>Observation: {esc(item.get('observed_value', ''))} {esc(item.get('unit') or '')}".strip() + "</h3>"]
    parts.append(_kv_block([
        ("Source", item.get("source", "")),
        ("Locator", item.get("locator", "")),
        ("Observed value", item.get("observed_value", "")),
        ("Unit", item.get("unit", "")),
        ("Currency", item.get("currency") or "—"),
        ("Normalized (EUR)", item.get("normalized_eur") if item.get("normalized_eur") is not None else "—"),
        ("Conversion", item.get("conversion") or "—"),
        ("URL", _link(item.get("url", ""))),
        ("Content digest (full)", item.get("digest", "")),
        ("Parser", item.get("parser", "")),
        ("Retrieved", item.get("retrieved_at", "")),
    ], html_keys=frozenset({"URL"})))
    parts.append("</div>")
    return parts


def _render_source_evidence_details(report: dict[str, Any]) -> list[str]:
    """Expanded offline evidence: per-source parse status, the exact
    observations that bound each proposed fact, conflicts, and the
    independently derived snapshot inventory. All values escaped; no JS or
    network."""
    parts: list[str] = [
        "<details id='source-evidence'><summary>Source evidence — parsed snapshot observations (offline replay)</summary>"
    ]
    evidence = report.get("source_evidence", {}) or {}
    parts.append(
        f"<p class='muted'>{esc(evidence.get('note', 'offline replay of supplied snapshots'))}. "
        "Snapshot origin/retrieval claims (retrieved_at, published_at) are caller-supplied "
        "labels assessed against freshness policy; they are not authenticated retrievals.</p>"
    )
    sources = report.get("sources", []) or []
    if sources:
        parts.append("<h3>Source parse status (registry parser, bounded deterministic parsing)</h3>")
        for assessment in sources:
            parse_state = assessment.get("parse_state", "—")
            parts.append(
                f"<div class='src-card'><h3>{esc(assessment.get('provider'))}/<span class='wrap'>{esc(assessment.get('model'))}</span> "
                f"({esc(assessment.get('source_kind'))})</h3>"
            )
            parts.append(_kv_block([
                ("Parser (registry)", assessment.get("parser") or "—"),
                ("Parse", parse_state),
                ("Models parsed", assessment.get("parsed_models", 0)),
                ("FX quotes", assessment.get("parsed_fx_quotes", 0)),
                ("Classification", assessment.get("classification", "—")),
                ("Evidence", _evidence_label(assessment)),
                ("Content digest (full)", assessment.get("content_sha256", "")),
            ]))
            parts.append("</div>")
    else:
        parts.append("<p class='muted'>No sources recorded in the bundle.</p>")
    backed = evidence.get("backed_facts", []) or []
    parts.append(f"<h3>Proposed facts bound to parsed observations ({len(backed)})</h3>")
    if backed:
        parts.append("<table><thead><tr><th>Provider/Model</th><th>Field</th><th>Proposed</th><th>Normalized (EUR)</th><th>Declared backing sources</th><th>Independent sources (distinct URLs)</th><th>State</th></tr></thead><tbody>")
        for item in backed:
            parts.append(
                f"<tr><td>{esc(item.get('provider'))}/<span class='wrap'>{esc(item.get('model'))}</span> (upstream <span class='wrap'>{esc(item.get('upstream_model', item.get('model')))}</span>)</td>"
                f"<td>{esc(item.get('field'))}</td>"
                f"<td>{esc(item.get('proposed'))}</td>"
                f"<td>{esc(item.get('proposed_normalized')) if item.get('proposed_normalized') is not None else esc(chr(8212))}</td>"
                f"<td class='wrap'>{esc(', '.join(item.get('backed_by', []))) or esc(chr(8212))}</td>"
                f"<td class='num'>{esc(item.get('independent_sources', 0))}</td>"
                "<td><span class='ev-verified'>BOUND (deterministic parser)</span></td></tr>"
            )
        parts.append("</tbody></table>")
        for item in backed:
            observations = item.get("observations", []) or []
            if not observations:
                continue
            parts.append(
                f"<details><summary>Observations binding {esc(item.get('field'))} for "
                f"{esc(item.get('provider'))}/<span class='wrap'>{esc(item.get('model'))}</span> ({len(observations)} shown)</summary>"
            )
            for obs in observations:
                parts.extend(_obs_card(obs))
            parts.append("</details>")
        parts.append("<p class='muted'>Each observation is an actual derived value from the parsed snapshot bytes: the observed value with its unit, currency and exact row/field locator, the source URL, full content digest, parser identity and retrieval time, and the exact normalization to the comparison currency. Repeated retrievals or aliases of the same official URL count as one independent source, not corroboration. Facts that could not be bound appear in the findings table with their blocker/REVIEW code; a fact with no verified supporting observation is never silently treated as verified, and a semantic label is never evidence.</p>")
    else:
        parts.append("<p class='muted'>No proposed facts carried bindable non-null values in this run.</p>")
    fx_backed = evidence.get("fx_backed", []) or []
    if fx_backed:
        parts.append("<h3>FX facts bound to verified reference quotes</h3>")
        for item in fx_backed:
            parts.append(f"<div class='src-card'><h3>FX fact: {esc(item.get('pair'))}</h3>")
            parts.append(_kv_block([
                ("Proposed rate", item.get("rate")),
                ("Observed quote", item.get("observed_quote")),
                ("Quote locator", item.get("quote_locator", "")),
                ("Derivation", "reciprocal of native quote" if item.get("derived_reciprocal") else "native quote"),
                ("Quote date", item.get("quote_date")),
                ("Fact published", item.get("fact_published_at", "")),
                ("Backing source", item.get("backed_by")),
                ("Quote URL", _link(item.get("quote_url", ""))),
                ("Quote digest (full)", item.get("quote_digest", "")),
                ("Quote parser", item.get("quote_parser", "")),
            ], html_keys=frozenset({"Quote URL"})))
            parts.append("</div>")
    inventory = evidence.get("inventory", {}) or {}
    if inventory:
        parts.append("<h3>Inventory (independently derived from official snapshots, every identifier reconciled)</h3>")
        for provider in sorted(inventory):
            values = inventory[provider]
            excluded_ids = values.get("excluded_ids", [])
            retained_ids = values.get("retained_local_ids", [])
            ids_note = []
            if excluded_ids:
                ids_note.append(f"excluded: {', '.join(esc(i) for i in excluded_ids)}")
            if retained_ids:
                ids_note.append(f"retained: {', '.join(esc(i) for i in retained_ids)}")
            parts.append(f"<div class='src-card'><h3>Inventory: {esc(provider)}</h3>")
            parts.append(_kv_block([
                ("Selection mode", values.get("selection_mode", "")),
                ("Models in official snapshots", values.get("evidence_models", 0)),
                ("Selected/proposed", values.get("selected_models", 0)),
                ("Retained local (baseline)", values.get("retained_local_models", 0)),
                ("Explicitly excluded (subset)", values.get("explicitly_excluded_models", 0)),
                ("Unsupported excluded", values.get("unsupported_excluded_models", 0)),
                ("Unexplained omissions", values.get("unexplained_omissions", 0)),
                ("Excluded/retained IDs", " · ".join(ids_note) if ids_note else "—"),
            ]))
            parts.append("</div>")
        parts.append("<p class='muted'>Every model identifier parsed from an official snapshot is reconciled into exactly one disposition. An unexplained omission under an all-eligible selection blocks the run; explicitly excluded (subset) and unsupported (text capability not observed) models are listed by name and count, not warned per row. Retained local models keep historical local state with no automatic deletion.</p>")
    parts.append("</details>")
    return parts


def render_report(bundle: RefreshBundle, report: dict[str, Any]) -> bytes:
    """Render the sealed one-page REVIEW.html. Pure function of inputs."""
    source_index = _source_index(bundle)
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
        f"<title>SLAIF catalog refresh review — {esc(report['state'])} — {esc(report['run_id'])}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<h1>SLAIF catalog refresh review</h1>",
        "<p class='sub'>One-page offline review artifact. This version reviews supplied snapshots; live collection and apply are not implemented. "
        "Everything needed for the decision is inside this file; detailed evidence is in the expandable sections below. "
        "No external resources, no JavaScript, no network on open.</p>",
        "</header>",
    ]
    parts.extend(_render_first_screen(bundle, report))
    parts.extend(_render_changes(bundle, report, source_index))
    parts.extend(_render_details(bundle, report, source_index))
    parts.append(
        "<footer>"
        f"Run {esc(report.get('run_id'))} · generated at {esc(report.get('generated_at'))} · "
        f"renderer {esc(bundle.revision.renderer_version)} · policy v{esc(report.get('policy_version'))} · "
        "offline scope: review/export/verify only — live source retrieval and apply are unavailable in this version. "
        "Print behaviour: state borders and textual labels are preserved (colour is not relied on), long values wrap instead of clipping, "
        "and opened (expanded) sections print in full; closed sections print their summary line only. "
        "This file is self-contained: no network requests, no scripts, no external assets."
        "</footer>"
    )
    parts.extend(["</main>", "</body>", "</html>"])
    return ("\n".join(parts) + "\n").encode("utf-8")


def build_manifest(files: dict[str, bytes]) -> bytes:
    """Deterministic manifest: strict relative paths, sha256, byte sizes."""
    entries = [
        {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        for name, data in sorted(files.items())
    ]
    payload = {"schema_version": "1", "files": entries}
    return (json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8")


def canonical_report_bytes(bundle: RefreshBundle, report: dict[str, Any]) -> bytes:
    return render_report(bundle, report)
