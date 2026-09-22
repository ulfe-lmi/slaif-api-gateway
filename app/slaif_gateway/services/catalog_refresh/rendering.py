"""Deterministic REVIEW.html rendering and manifest building.

The renderer is a pure function of (bundle, validation report): no clock
reads, no environment access, stable ordering. Every data value is escaped;
only schema-validated http/https URLs may become links. No external
resources, no JavaScript, no event attributes, no user-controlled markup.

Layout contract (180-b, R6): the first screen prioritizes the decision —
state and why, blocker/REVIEW counts, selected scope and baseline, compact
per-provider change summary, the create-only execution plan, FX current vs
proposed, and aggregated important findings — with the full gate checklist
and counts. Expanded technical identifiers, per-model details, source
inventory, and raw validator output live in on-demand details sections of the
same self-contained file. Source trust labels are derived (OFFICIAL / REVIEW
/ BLOCKED from provider/method/host/evidence rules), never caller-declared
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
_CLASSIFICATION_CLASS = {
    "OFFICIAL": "ev-verified",
    "REVIEW": "ev-review",
    "BLOCKED": "ev-blocked",
    "N/A": "ev-na",
}

_CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 24px; color: #1a202c; background: #ffffff; line-height: 1.45; }
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 28px 0 8px; border-bottom: 1px solid #cbd5e0; padding-bottom: 4px; }
h3 { font-size: 1rem; margin: 18px 0 6px; }
p.sub { color: #4a5568; margin: 0 0 16px; }
.state { font-size: 1.05rem; font-weight: 600; padding: 10px 14px; border-radius: 6px; border: 1px solid; }
.state-ready { background: #f0fff4; border-color: #2f855a; color: #22543d; }
.state-review { background: #fffaf0; border-color: #b7791f; color: #744210; }
.state-blocked { background: #fff5f5; border-color: #c53030; color: #742a2a; }
.runline { color: #4a5568; font-size: 0.88rem; margin: 6px 0 0; }
.runline code { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 0 4px; }
.decision { border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 14px; margin: 12px 0; }
.decision dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 14px; margin: 0; font-size: 0.9rem; }
.decision dt { font-weight: 600; color: #2d3748; }
.decision dd { margin: 0; word-break: break-word; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 0.88rem; }
th, td { border: 1px solid #cbd5e0; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #f7fafc; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.plan-blocked { background: #fff5f5; border: 1px solid #c53030; color: #742a2a; border-radius: 6px; padding: 8px 12px; font-weight: 600; margin: 8px 0; }
.plan-ok { background: #f0fff4; border: 1px solid #2f855a; color: #22543d; border-radius: 6px; padding: 8px 12px; margin: 8px 0; }
dl.identity { display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px; margin: 8px 0 16px; font-size: 0.9rem; }
dl.identity dt { font-weight: 600; color: #2d3748; }
dl.identity dd { margin: 0; word-break: break-all; }
details { margin: 10px 0; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; }
summary { cursor: pointer; font-weight: 600; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.82rem; }
pre { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
.muted { color: #718096; }
.ev-verified { color: #22543d; font-weight: 600; }
.ev-na { color: #718096; }
.ev-review { color: #744210; font-weight: 600; }
.ev-blocked { color: #742a2a; font-weight: 700; }
.sev-BLOCKER { color: #742a2a; font-weight: 700; }
.sev-REVIEW { color: #744210; font-weight: 600; }
.sev-INFO { color: #2d3748; }
a { color: #2b6cb0; }
footer { margin-top: 28px; color: #718096; font-size: 0.8rem; border-top: 1px solid #e2e8f0; padding-top: 10px; }
@media print {
  body { padding: 0; }
  details { border: none; padding: 4px 0; }
  details > summary { display: block; }
  details[open] { border: none; }
  tr { page-break-inside: avoid; }
  .state { break-inside: avoid; }
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
        return f"<span class='muted'>{esc(url or 'no url')}</span>"
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
        parts.append(esc(key))
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
                f"<li class='plan-item'>\u2022 {esc(kind)}: <strong class='ev-blocked'>BLOCKED</strong> — "
                f"{esc(ready)} create row(s) executable, {esc(excluded + plan_blocked)} row(s) require an apply "
                "operation that does not exist in this version (excluded from the executable artifact)</li>"
            )
        elif gate.get("total_rows", 0) == 0:
            lines.append(f"<li class='plan-item'>\u2022 {esc(kind)}: nothing to create (NO CHANGES)</li>")
        else:
            lines.append(
                f"<li class='plan-item'>\u2022 {esc(kind)}: {esc(ready)} create row(s) executable "
                "(create-only plan)</li>"
            )
    return lines, blocked


def _render_first_screen(bundle: RefreshBundle, report: dict[str, Any]) -> list[str]:
    state = report["state"]
    counts = report.get("counts", {})
    warnings = report.get("warnings", [])
    blockers = [warning for warning in warnings if warning["severity"] == "BLOCKER"]
    reviews = [warning for warning in warnings if warning["severity"] == "REVIEW"]
    baseline = report.get("baseline", {})
    sql_checks = report.get("sql_checks", {})

    parts: list[str] = [
        f"<p class='state {_STATE_CLASS[state]}'><strong>{esc(state)}</strong> — {esc(report['state_reason'])}</p>"
    ]

    # Compact run identity (one line); expanded identity moves to details.
    parts.append(
        f"<p class='runline'>Run <code>{esc(report.get('run_id'))}</code> · generated at "
        f"{esc(report.get('generated_at'))} (run time) · revision {esc(bundle.revision.slaif_revision)} "
        f"(schema {esc(bundle.revision.schema_version)}, renderer {esc(bundle.revision.renderer_version)}, "
        f"policy v{esc(report.get('policy_version'))}) · profile {esc(bundle.profile.name)} {esc(bundle.profile.endpoint)}</p>"
    )

    # Decision summary: why this state, scope, baseline.
    blocker_codes = sorted({warning["code"] for warning in blockers})
    review_codes = sorted({warning["code"] for warning in reviews})
    model_filter = ", ".join(esc(m) for m in bundle.selection.model_include) or "all models of selected providers"
    sql_note = sql_checks.get("note", "")
    parts.append(
        "<div class='decision'><dl>"
        f"<dt>Why this state</dt><dd>{esc(report['state_reason'])}</dd>"
        f"<dt>Blockers</dt><dd>{len(blockers)} finding(s)"
        + (f" — codes: {esc(', '.join(blocker_codes))}" if blocker_codes else "")
        + "</dd>"
        f"<dt>Review findings</dt><dd>{len(reviews)} finding(s)"
        + (f" — codes: {esc(', '.join(review_codes))}" if review_codes else "")
        + "</dd>"
        f"<dt>Selected scope</dt><dd>providers: {esc(', '.join(bundle.selection.providers))}; models: {model_filter}"
        f" (selected {esc(counts.get('selected', 0))}, considered {esc(counts.get('considered', 0))}, "
        f"out-of-scope facts {esc(counts.get('out_of_scope_facts', 0))})</dd>"
        f"<dt>Baseline</dt><dd>{esc(baseline.get('mode'))}"
        + (f" — exported {esc(baseline.get('exported_at'))}" if baseline.get("exported_at") else " — FIRST INSTALL (explicitly empty, no database read)")
        + (f" — target {esc(baseline.get('target'))}" if baseline.get("target") else "")
        + "</dd>"
        f"<dt>Baseline SQL evidence</dt><dd>{esc(sql_note)}</dd>"
        f"<dt>Live research</dt><dd>{esc(report.get('research', {}).get('status'))} — live source retrieval is unavailable in this version; only supplied offline evidence is assessed</dd>"
        "</dl></div>"
    )

    # Per-provider change/completeness summary (above the fold).
    per_provider = report.get("per_provider", {})
    if per_provider:
        parts.append("<h2>Per-provider summary</h2>")
        parts.append("<table><thead><tr><th>Provider</th><th>new</th><th>changed</th><th>unchanged</th><th>excluded</th><th>blocked</th><th>disappeared</th><th>deprecated</th><th>not fetched</th></tr></thead><tbody>")
        for provider in sorted(per_provider):
            values = per_provider[provider]
            parts.append(f"<tr><td>{esc(provider)}</td>" + "".join(f"<td class='num'>{esc(values.get(key, 0))}</td>" for key in ("new", "changed", "unchanged", "excluded", "blocked", "disappeared", "deprecated", "not_fetched")) + "</tr>")
        parts.append("</tbody></table>")

    # Create-only execution plan (visually impossible to mistake for READY when blocked).
    plan_lines, plan_blocked = _plan_lines(report)
    if plan_lines:
        parts.append("<h2>Execution plan (create-only)</h2>")
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
        parts.append("<ul>" + "".join(plan_lines) + "</ul>")

    # FX current vs proposed (first screen).
    parts.extend(_render_fx_section(report))

    # Aggregated important findings (BLOCKERs first, then REVIEW).
    parts.extend(_render_aggregated_findings(warnings))

    # Gate checklist (truthful scope: sources, schema, pricing completeness,
    # pairing, unsupported, unusual changes, completeness, execution plans).
    gates = report.get("gates", [])
    if gates:
        parts.append("<h2>Gate checklist</h2>")
        parts.append("<table><thead><tr><th>Gate</th><th>Evidence</th><th>Detail</th></tr></thead><tbody>")
        for gate in gates:
            parts.append(
                f"<tr><td>{esc(gate['name'])}</td>"
                f"<td class='{_EVIDENCE_CLASS.get(gate['evidence'], 'ev-na')}'>{esc(gate['evidence'])}</td>"
                f"<td>{esc(gate['detail'])}</td></tr>"
            )
        parts.append("</tbody></table>")

    parts.append("<h2>Counts (recomputed)</h2>")
    parts.append("<table><thead><tr><th>selected</th><th>considered</th><th>ready</th><th>new</th><th>changed</th><th>unchanged</th><th>excluded</th><th>blocked</th><th>disappeared</th><th>deprecated</th><th>not fetched</th><th>out-of-scope facts</th></tr></thead><tbody><tr>")
    for key in ("selected", "considered", "ready", "new", "changed", "unchanged", "excluded", "blocked", "disappeared", "deprecated", "not_fetched", "out_of_scope_facts"):
        parts.append(f"<td class='num'>{esc(counts.get(key, 0))}</td>")
    parts.append("</tr></tbody></table>")
    return parts


def _render_fx_section(report: dict[str, Any]) -> list[str]:
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
    return parts


def _render_aggregated_findings(warnings: list[dict[str, Any]]) -> list[str]:
    parts: list[str] = ["<h2>Important findings (aggregated)</h2>"]
    if not warnings:
        parts.append("<p class='muted'>No blockers and no review findings.</p>")
        return parts
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for warning in warnings:
        key = (warning["severity"], warning["code"])
        entry = grouped.setdefault(key, {"count": 0, "details": []})
        entry["count"] += 1
        if len(entry["details"]) < 3:
            entry["details"].append(f"{warning.get('provider') or ''}/{warning.get('model') or ''}: {warning['detail']}".strip(": "))
    ordered = sorted(grouped.items(), key=lambda item: (item[0][0] != "BLOCKER", item[0][1], item[1]["count"] * -1))
    parts.append("<table><thead><tr><th>Severity</th><th>Code</th><th>Count</th><th>Examples</th></tr></thead><tbody>")
    for (severity, code), entry in ordered:
        parts.append(
            f"<tr><td class='sev-{esc(severity)}'>{esc(severity)}</td><td>{esc(code)}</td>"
            f"<td class='num'>{esc(entry['count'])}</td><td>{esc(' · '.join(entry['details']))}</td></tr>"
        )
    parts.append("</tbody></table>")
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
                f"<tr><td>{esc(row['provider'])}</td><td>{esc(row['model'])}</td><td>{esc(row['dimension'])}</td>"
                f"<td class='num'>{_fmt_decimal(row['old'])}</td><td>{_cell(row['currency_old'])}</td>"
                f"<td class='num'>{_fmt_decimal(row['new'])}</td><td>{_cell(row['currency_new'])}</td>"
                f"<td class='num'>{_signed_percent(row['percent_change'])}</td>"
                f"<td>{esc(row['state'])}</td></tr>"
            )
        parts.append("</tbody></table>")
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
                f"{esc(route.upstream_model)} via {esc(route.provider)}"
                f" (priority {esc(route.priority)}, streaming {esc(route.supports_streaming)}, visible {esc(route.visible_in_models)})"
                if route
                else "—"
            )
            reason = (
                "existing-row update/supersession; no apply operation exists in this version — excluded from the executable artifact"
            )
            parts.append(
                f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td><td>{esc(d['detail'])}</td><td>{proposed}</td><td>{esc(reason)}</td></tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append("<p class='muted'>No route or model attribute changes.</p>")

    # FX details are already on the first screen; keep an explicit pointer so
    # the section is complete even when FX is N/A.
    return parts


def _render_details(bundle: RefreshBundle, report: dict[str, Any], source_index: dict[str, dict[str, Any]]) -> list[str]:
    assessments = _assessment_index(report)
    parts: list[str] = []
    dispositions = report.get("dispositions", [])
    models_by_key = {(m.provider, m.model): m for m in bundle.models}

    def group(kind: str) -> list[dict[str, Any]]:
        return [d for d in dispositions if d["disposition"] == kind]

    def model_detail_rows(rows: list[dict[str, Any]], show_provenance: bool) -> list[str]:
        out: list[str] = []
        for d in rows:
            facts = models_by_key.get((d["provider"], d["model"]))
            out.append(f"<h3>{esc(d['provider'])}/{esc(d['model'])} — {esc(d['detail'])}</h3>")
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
                        f"<tr><td>{esc(field_name)}</td><td>{esc(value)}</td>"
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
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    deprecated = group("DEPRECATED")
    if deprecated:
        parts.append(f"<details><summary>Deprecated models ({len(deprecated)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Note</th></tr></thead><tbody>")
        for d in deprecated:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    excluded = group("EXCLUDED")
    if excluded:
        parts.append(f"<details><summary>Excluded (unsupported) rows ({len(excluded)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Reason</th></tr></thead><tbody>")
        for d in excluded:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    blocked = group("BLOCKED")
    if blocked:
        parts.append(f"<details open><summary>Blocked rows ({len(blocked)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Reason</th></tr></thead><tbody>")
        for d in blocked:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    not_fetched = group("NOT_FETCHED")
    if not_fetched:
        parts.append(f"<details><summary>Not fetched ({len(not_fetched)})</summary>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th><th>Note</th></tr></thead><tbody>")
        for d in not_fetched:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td><td>{esc(d['detail'])}</td></tr>")
        parts.append("</tbody></table></details>")
    unchanged = group("UNCHANGED")
    if unchanged:
        parts.append(f"<details><summary>Unchanged models ({len(unchanged)}) — collapsed</summary>")
        parts.append("<p class='muted'>Compared fields identical to the active baseline; no-op rows are excluded from the executable artifacts and aggregated by design.</p>")
        parts.append("<table><thead><tr><th>Provider</th><th>Model</th></tr></thead><tbody>")
        for d in unchanged:
            parts.append(f"<tr><td>{esc(d['provider'])}</td><td>{esc(d['model'])}</td></tr>")
        parts.append("</tbody></table></details>")

    warnings = report.get("warnings", [])
    if warnings:
        parts.append(f"<details open><summary>All warnings and findings ({len(warnings)})</summary>")
        parts.append("<table><thead><tr><th>Severity</th><th>Code</th><th>Provider</th><th>Model</th><th>Detail</th></tr></thead><tbody>")
        for warning in warnings:
            parts.append(
                f"<tr><td class='sev-{esc(warning['severity'])}'>{esc(warning['severity'])}</td>"
                f"<td>{esc(warning['code'])}</td><td>{_cell(warning['provider'])}</td>"
                f"<td>{_cell(warning['model'])}</td><td>{esc(warning['detail'])}</td></tr>"
            )
        parts.append("</tbody></table></details>")
    else:
        parts.append("<details><summary>All warnings and findings (0)</summary><p class='muted'>None.</p></details>")

    parts.append("<details><summary>Full validator outputs (validation.json)</summary>")
    parts.append(f"<pre>{esc(json.dumps({k: v for k, v in report.items() if k not in ('gates',)}, sort_keys=True, indent=1, default=str))}</pre></details>")

    import_gates = report.get("import_gates", [])
    if import_gates:
        parts.append("<details open><summary>Import gate details (schema-valid vs execution-plan-valid)</summary>")
        parts.append("<table><thead><tr><th>Kind</th><th>Schema valid</th><th>Rows</th><th>Valid</th><th>Invalid</th><th>Classifications</th><th>Plan ready</th><th>Plan blocked</th><th>Excluded mutations</th><th>Detail</th></tr></thead><tbody>")
        for gate in import_gates:
            parts.append(
                f"<tr><td>{esc(gate['kind'])}</td><td>{esc(gate['schema_valid'])}</td>"
                f"<td class='num'>{esc(gate['total_rows'])}</td><td class='num'>{esc(gate['valid_rows'])}</td>"
                f"<td class='num'>{esc(gate['invalid_rows'])}</td>"
                f"<td>{esc(', '.join(f'{k}={v}' for k, v in gate['classifications'].items()) or '—')}</td>"
                f"<td class='num'>{esc(gate['plan_ready_rows'])}</td><td class='num'>{esc(gate['plan_blocked_rows'])}</td>"
                f"<td class='num'>{esc(gate.get('excluded_mutations', 0))}</td>"
                f"<td>{esc(gate['detail'])}</td></tr>"
            )
        parts.append("</tbody></table>")
        parts.append("<p class='muted'>Existing create-only execution remains unchanged. Updates/supersessions are represented as changed rows above; their apply plan is BLOCKED because no apply operation exists in this version. An empty unchanged plan is a truthful NO CHANGES result, not an invalid import.</p>")
        parts.append("</details>")

    parts.append("<details><summary>Source inventory and reconciliation (trust derived, never declared)</summary>")
    if bundle.sources:
        parts.append("<table><thead><tr><th>Source</th><th>Kind</th><th>URL</th><th>Derived classification</th><th>Evidence</th><th>Age</th><th>Retrieved</th><th>Published</th><th>Extractor</th><th>Method</th><th>Required</th><th>Truncated</th><th>SHA-256</th></tr></thead><tbody>")
        for source in sorted(bundle.sources, key=lambda s: (s.provider, s.model, s.source_kind)):
            assessment = assessments.get(f"{source.provider}|{source.model}|{source.source_kind}", {})
            classification = assessment.get("classification", "—")
            parts.append(
                f"<tr><td>{esc(source.provider)}/{esc(source.model)}</td><td>{esc(source.source_kind)}</td>"
                f"<td>{_link(source.url)}</td>"
                f"<td class='{_CLASSIFICATION_CLASS.get(classification, 'ev-na')}'>{esc(classification)}</td>"
                f"<td>{esc(_evidence_label(assessment or None))}</td>"
                f"<td>{esc(assessment.get('age_state', '—'))}</td>"
                f"<td>{esc(source.retrieved_at.isoformat())}</td>"
                f"<td>{_cell(source.published_at.isoformat() if source.published_at else None)}</td>"
                f"<td>{esc(source.extractor)}</td><td>{esc(source.extraction)}</td>"
                f"<td>{esc(source.required)}</td><td>{esc(source.truncated)}</td>"
                f"<td class='muted'>{esc(source.content_sha256[:16])}…</td></tr>"
            )
        parts.append("</tbody></table>")
        parts.append("<p class='muted'>OFFICIAL requires the exact official host for the (provider, source kind) rule plus supplied evidence whose bytes match the declared digest. A safe URL is not an authoritative source: operator-supplied, semantic, off-host, or unverifiable-offline sources classify as REVIEW, and unsupported or contradictory sources classify as BLOCKED. Supplied/cached evidence is explicitly distinguished from live retrieval, which this process never performs.</p>")
    else:
        parts.append("<p class='muted'>No sources recorded in the bundle.</p>")
    parts.append("</details>")

    baseline = report.get("baseline", {})
    sql_checks = report.get("sql_checks", {})
    parts.append("<details><summary>Baseline identity (historical capture vs current checks)</summary>")
    parts.append("<dl class='identity'>")
    for label, value in (
        ("Mode", baseline.get("mode")),
        ("Exported at (historical capture)", baseline.get("exported_at")),
        ("Baseline document digest verified", "yes" if baseline.get("mode") not in (None, "first_install") else "n/a (first install)"),
        ("SQL checked at document export (historical)", "yes" if baseline.get("sql_checked") else "no"),
        ("SQL executed during this review", "yes" if sql_checks.get("sql_executed_during_review") else "no"),
        ("Note", sql_checks.get("note")),
        ("Target", baseline.get("target")),
        ("PostgreSQL version", baseline.get("postgres_version")),
        ("Baseline age (seconds at run time)", baseline.get("age")),
    ):
        parts.append(f"<dt>{esc(label)}</dt><dd>{esc(value) if value is not None else '—'}</dd>")
    parts.append("</dl>")
    parts.append("<p class='muted'>The unkeyed content digest is an integrity check on the document bytes; it is not authentication and not proof that the baseline is current. A connection failure must never become an empty bootstrap; bootstrap requires an explicitly empty first-install baseline.</p>")
    parts.append("</details>")

    # Expanded run identity (technical identifiers off the first screen).
    artifacts = report.get("artifacts", {})
    parts.append("<details><summary>Run identity (expanded)</summary>")
    parts.append("<dl class='identity'>")
    for label, value in (
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
    ):
        parts.append(f"<dt>{esc(label)}</dt><dd>{esc(value)}</dd>")
    parts.append("</dl></details>")

    if bundle.notes:
        parts.append(f"<details><summary>Bundle notes</summary><p>{esc(bundle.notes)}</p></details>")
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
        "<p class='sub'>One-page offline review artifact. Everything needed for the decision is inside this file; detailed evidence sections exist in the same file for machines and audit. No external resources, no JavaScript. Live source retrieval and plan apply are unavailable in this version.</p>",
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
