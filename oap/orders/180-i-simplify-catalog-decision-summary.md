# OAP Work Order — 180-i

PR mode: AMEND_EXISTING_PR

## Objective and strategic decision

Make the operator's normal review genuinely quick and legible. Preserve180-h's
useful expanded evidence cards, offline behavior, deterministic semantics and
wording corrections. Simplify the first screen instead of shrinking its text.
Fix the browser test's fixture-writing behavior and incomplete visual predicates.
This is a narrow presentation/test continuation on the SAME PR317.

The full mandate remains one refresh command -> one trustworthy static report ->
one explicitly confirmed audited apply command. This round completes the remaining
presentation work for Objective180's offline foundation if accepted; it does NOT
complete the later live-source/Codex/apply workflow. Those subsequent numeric
objectives remain required after180 is resolved. Do not pre-activate181.

## Verified state and preceding report disposition

Verified from GitHub and the exact response terminal on2026-09-22:

- Repository ulfe-lmi/slaif-api-gateway; main
  b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Unique open PR317; branch oap/180-catalog-refresh-bundle-review; base main.
- Starting PR/report head686f642e4dd18fcc6844860b3b4ce4a7b0aaed94; report-only
  changes oap/reports/180-h-make-catalog-review-fast-and-readable.md; first parent /
  implementation headfe250ec12263f2e40d33f34ad363e588ca957306.
- H activationfde46beb9488d7baf8587ec12fa1b6ddc1c6364d. H order SHA256
  78d64e96b45826b5ea47df1cff2e47a32ee99d6dc353d5b4bfcc067321d956eb.
- Sole helper59013 returned RESPONSE_OK_EXACT/exit0 and is CLOSED. Prior
  active180-h, clean worktree. Do not reuse it or start a response reader.
- All10 report-head checks are green. Independent291 unit tests passed in33.60s
  on exactfe250ec with stable hashes checked against Git objects; documentation
  checkerOK91files; diff-check clean. H schema change is only renderer180.5 and
  validation change is only the authorized explanatory SQL-capture note.
- Independent browser6cases: no extra network requests; actual document width
  fits1440/1280/375 collapsed AND expanded; useful evidence reflow accepted.
- H quick-review acceptance is NOT satisfied. The committed screenshot splits
  short ordinary words (new/changed/openrouter) inside narrow table cells. Main
  gate/provider text is12.48px and group labels11.52px. The first scope+gate cards
  alone contain276–298words. At1440x900 important findings start839–917px; plan
  starts956–1034px; What changed starts1082–1159px. The real two-provider case
  places even the start of important findings below the viewport.
- H browser DASHBOARD_SELECTORS omits findings/plan/changes, so passing six boxes
  does not prove the requested decision surface. It tests1280 only collapsed,
  and its digest-visibility check searches page.content rather than visible text.
- Ordinary browser-test execution writes tracked PNG/PDF fixtures; PDF metadata
  varies per run. Strategy deliberately did not run that mutating test. It ran
  independent file-URL probes without modifying the coding worktree.
- Evidence: /home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/180-h-review/
  (unit-identity.json, browser-independent.json, six actual screenshots/HTMLs,
  and PDFpage1 raster). Preserve the immutable H report, correct broad claims
  in this new report only.
- Main deletion/non-fast-forward protection and sole releasev0.1.0-rc.1 unchanged.
  No merge/tag/release authority transfers to the coding agent.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/rendering.py
- app/slaif_gateway/schemas/catalog_refresh.py (RENDERER_VERSION constant only,
  180.5 ->180.6; no schema, policy or capability behavior)
- tests/unit/test_catalog_refresh_report.py
- tests/browser/test_catalog_refresh_report.py
- tests/fixtures/catalog_refresh/bundle-first-install.json
- tests/fixtures/catalog_refresh/bundle-refresh-ready.json
- tests/fixtures/catalog_refresh/bundle-blocked.json
- tests/fixtures/catalog_refresh/bundle-truncated.json
  (these four: renderer_version field only)
- tests/fixtures/catalog_refresh/report-layout/ (bounded synthetic presentation
  cases and deliberately regenerated, inspected images/PDFs/metrics only; update
  existing two-provider bundle's renderer field; no keys or live source payloads)
- tests/fixtures/catalog_refresh/browser-screenshots/ (the five existing PNGs,
  deliberately copied from inspected test outputs, not overwritten by routine tests)
- docs/catalog-refresh.md (presentation/print/test-evidence wording only)
- docs/cli-reference.md (catalog-refresh descriptive wording only)
- admin/catalog-refresh/README.md (catalog-refresh descriptive wording only)
- oap/orders/180-i-simplify-catalog-decision-summary.md (unchanged)
- oap/active (exact unchanged strategic bytes180-i)
- oap/reports/180-i-simplify-catalog-decision-summary.md (new immutable report)

No other paths. In particular NO CLI/validation/source/financial/filesystem/sealing
behavior changes, SQL, imports, dependencies, migrations, deployment, workflows,
architecture allowlists or historical-record edits. Do not redo the evidence or
filesystem architecture. Raise an actual new product defect with a reproducer,
not an unsolicited out-of-scope fix.

## I1 — Design the summary for a decision, not a compressed audit

Normal main reading text and metric/check labels must be at least14px at default
browser zoom; prefer15–16px for the operator's decision information. State and
headings should be clearly larger. Secondary compact identity/technical annotations
may be smaller, but do not move all decision content into tiny "annotations".
Short words/provider names must not break inside words at desktop widths.

Fit a concise overview in the first1440x900 viewport by choosing what belongs
there. Keep the full detailed evidence below in native expandable sections.
The overview should make these facts easy to see in30–60seconds:

1. State, concise plain-language reason, blocker/review counts, and the leading
   actionable review/blocking items. Do not print a long comma-separated code list
   as the primary reason; exact codes remain accessible in details.
2. Selected provider/profile, simple baseline mode/date, and compact run identity.
   Example baseline meaning: "Supplied export; not checked against a live database."
   The full SQL attestation explanation belongs in expanded baseline evidence.
3. Per-provider ready/selected/considered counts and a compact change summary
   (new, price/route changes, disappearance/deprecation, unchanged/excluded count
   as relevant). Use readable provider cards or a full-width summary rather than
   two9-column tables squeezed into half-width. Preserve the distinction between
   source inventory and local baseline comparison; detailed reconciliation remains
   available. Never invent a zero when a source is unavailable.
4. A compact checklist of the deterministic checks, with the worst state preserved.
   Show clear human labels and states. Full per-gate technical explanations,
   repeated VERIFIED badges and schema/SQL internals move to a labelled expandable
   section in the SAME artifact. No lost gates or downgraded findings.
5. FX pair/current/proposed/delta/source-date/state when required, or one concise
   truthful N/A line. Keep direct local rates distinct from derived proposals.
6. A concise import-plan limitation/action line. This version is offline review;
   live research/apply remain unavailable, no automatic import. Do not expose a
   nonexistent apply button/command or suggest READY authorizes automatic mutation.

Make "What changed" the next visible section, with its heading/summary and the
first relevant change visible in the normal desktop case. It must not follow a
page of repetitive audit prose. For many findings/changes show ranked aggregates
and an explicit link to the full list rather than expanding everything initially.
Do not hide blockers. Preserve all detailed prices, routes, FX, provenance,
validation, raw proposed rows and unchanged catalogs in the same artifact.

Keep H's expanded reflow and safe links/escaping. This is simplification of the
summary, not deletion of evidence or a new frontend. No JavaScript or network-on-
open, no external assets/fonts, no running application requirement. Retain the
honest offline scope with one concise notice, not repetitive warnings in every card.

## I2 — Test what the administrator sees, without changing the repository

Ordinary tests MUST write generated HTML/screenshots/PDFs/metrics only under
pytest-owned temporary output. They must leave tracked files unchanged and create
no untracked repository output. To update the committed evidence, deliberately
copy the inspected outputs as an explicit implementation step. Do not add a
runtime dependency or a new management interface for artifact regeneration.

Measure the real document scrollWidth and visible reading surface, not only the
selected container boxes. At1440x900 check state, concise scope/identity, grouped
checklist, provider change/completeness summary, FX, leading findings/action line
and the What-changed heading/summary together. Assert the main reading font sizes
and legible short labels; visually inspect the captures. A geometry pass with tiny
text or broken short words does not pass. At1280 and375, test both collapsed and
expanded views. Natural vertical scrolling is fine on narrow screens. Check
actual visible source values/digests after opening relevant outer AND nested
details; searching hidden DOM markup is not proof that a user can see it.

Retain first-install/READY/WARNINGS/BLOCKED/large-unchanged/two-provider-long-ID
cases. Add a representative actual price-change case (the existing full refresh
fixture is usable) and a genuine FX-required case driven through the CURRENT
validator/source contracts, not a hand-forged ValidationReport. Reuse existing
positive FX/source helpers. All-EUR N/A cases alone do not exercise the FX display.
No live provider call or data collection. Preserve deterministic state/counts/
source classifications; no code changes to make a presentation fixture pass.

Preserve print behavior (opened details included, closed details summarized),
inspect an actual PDF with expanded price/FX/source evidence, and verify no clipped
columns or lost values. Keep sensible print type; don't solve printing by making
it unreadably small. Do not turn a browser failure into a skip or assume resizing
artifacts harmless without checking the actual document behavior. The local
mandatory browser run must pass, not skip.

## I3 — Precise claims and narrow verification

Report which H acceptance claims were insufficient and what now proves them.
Preserve H's accepted semantic-neutrality, source/financial gates and trust wording.
Correct remaining descriptive language implying review is the only command that
writes files: review/key creation and export-baseline output have mutation-namespace
requirements; verify is read-only and does not enforce writability as a mutation
policy. Change documentation only, not behavior.

Increment renderer revision180.6 and regenerate fresh evidence; never rewrite or
re-sign archived runs. Prove that states, counts, gate decisions, monetary/capability
comparisons and proposal artifacts are unchanged (renderer identity excluded).
No further SQL note change is needed. Prior source/privacy/accounting protections
remain intact; G's code is read-only in this suffix.

Acceptance:
- AP-I1: legible concise first viewport and changes-led progression as above;
  findings and actual relevant changes visible, all details retained inline.
- AP-I2: current-pipeline price and FX cases, worst-state aggregation/count
  reconciliation, no source/model/price/capability invention, explicit offline scope.
- AP-I3: real geometry and font/short-label checks, visible expanded evidence,
  1440/1280/375 collapsed+expanded usability, inspected print PDF, no network/scripts.
- AP-I4: routine browser tests leave the worktree unchanged; new captures are
  deliberately regenerated once, with exact source identity and actual exit codes.
- AP-I5: focused unit/browser tests, lint, docs/internal links, diff-check and
  ordinary final-head CI green; semantic-neutrality and exact-path proof.

Run focused catalog-refresh unit tests and the standalone browser file; no complete
local/HPC/integrated matrix, PostgreSQL, Redis, Gateway server or Docker required.
Use existing venv/Chromium and synthetic temp data. Never access .env, shared5432,
protected credentials, privileged postgres identity or production systems. Preserve
unrelated worktrees/.local-provider-catalog/rootAGENTS.md/permanentmessage.txt.
Clean only owned temporary resources. No keys in report/screenshot/PDF fixtures.

## Publication and handoff

Commit strategic order/active unchanged on the existing PR. Push implementation
before drafting the report. Report exact SHAs/paths, typography/viewport/actual
visible-data/network/print/test results, worktree-clean-after-test evidence,
semantic-neutrality, H claim corrections, CI and remaining full-workflow objectives.
Do not claim the entire administrator workflow complete because this foundation
passes. Strategy decides whether Objective180 may merge; coding agent never merges,
enables auto-merge, tags or releases.

Publish exactly one immutable report-only SELF commit, first parent equal to the
literal implementation head. Verify it is remote PR317 head before exact two-byteOK
on the verified response FIFO. Do not pre-claim the SELF commit's future CI in the
report; report existing implementation CI and let strategy verify final checks.

The last control wake was corrected by strategy because a detached waiter targeted
pane%2. After this round's report/response, explicitly launch the next control waiter
with TMUX_PANE set to the verified coding pane%3. Do not create a control waiter
while this round is running. No extra FIFO readers or resends; strategy owns the
response helper and the next activation.
