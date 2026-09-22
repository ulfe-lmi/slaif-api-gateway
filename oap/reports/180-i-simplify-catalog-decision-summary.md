# OAP Immutable Report — 180-i: simplify catalog decision summary

PR mode: AMEND_EXISTING_PR on PR #317 (branch
`oap/180-catalog-refresh-bundle-review`, base `main`).

## Identity

- Starting SHA (committed PR head when this order started):
  `686f642e4dd18fcc6844860b3b4ce4a7b0aaed94` (the 180-h report commit;
  its sole changed file is the 180-h report, whose implementation parent
  is `fe250ec12263f2e40d33f34ad363e588ca957306`)
- Activation commit (order file + `oap/active` pointer, exact strategic
  bytes `180-i`): `743055cdd942cb2213aab6e730ad7f61074fb21c`
- Implementation commit:
  `b45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a` (23 files, +1277/−413)
- Implementation head SHA:
  `b45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a`
- Report publication commit: SELF
- PR #317 remains OPEN. Never merged, auto-merge not enabled, no tag, no
  release. The only published release remains `v0.1.0-rc.1`. No
  production-certification claim follows. Objective 180 is NOT complete;
  181 is NOT pre-activated.

## Changed paths (implementation head vs starting SHA)

Protocol commit `743055cdd942cb2213aab6e730ad7f61074fb21c` (activation
only):

- `oap/orders/180-i-simplify-catalog-decision-summary.md` (new order,
  unchanged since activation)
- `oap/active` (exact strategic bytes `180-i`)

Implementation commit
`b45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a` (all within the order's exact
allowed paths; no other path touched):

- `app/slaif_gateway/schemas/catalog_refresh.py` — exactly one line:
  `RENDERER_VERSION` `180.5` → `180.6` (diff-verified; no schema, policy
  or capability behavior change).
- `app/slaif_gateway/services/catalog_refresh/rendering.py` —
  presentation-layer rewrite only (validation, sealing, filesystem
  boundary, and all state/count/price/FX logic untouched):
  - Banner: state + concise plain-language reason
    (`_plain_reason_html`; BLOCKED leads with "N blocking issue(s):" plus
    at most 3 human labels from `_finding_label`, e.g. "currency
    inconsistency", "pricing import plan blocked", "required data
    missing"; exact codes remain in the findings) plus
    BLOCKERS/REVIEW/all-findings chips.
  - `grid-2` card row: `#scope-baseline` card (selected providers/profile,
    plain-language baseline meaning — "First install — explicitly empty;
    no database was read" / "Live export performed by this review (SQL
    ran during the review)" / "Supplied export of <date> — not checked
    against a live database" — source-evidence line, and a compact
    `#run-identity-compact` annotation carrying run/schema/renderer/policy
    revisions with a link to the expanded `#run-identity` evidence) and a
    `#checks` card "Deterministic checks" with one compact checkline per
    `_GATE_GROUPS` group (group label, worst-state chip, "n/m ok")
    linking to the full `#gates-full` checklist.
  - Full-width `#per-provider` section "Providers & changes": one
    summary line plus a single `.table-scroll` table
    (Provider|New|Changed|Mutations|Unchanged|Excluded|Blocked|
    Disappeared|Deprecated|Not fetched[|In snapshot|Selected in snapshot
    when an inventory exists]) instead of two 9-column tables squeezed
    into half-width; an honest "No source snapshots parsed in this run…"
    line when no inventory was parsed (never an invented zero); a
    not-additive footnote; and a "Counts (recomputed):" kv-chip row.
  - `#fx-line`: per pair current → proposed, signed delta %, state,
    published date, source; when no FX is required, exactly one concise
    truthful line: "FX: not required — all selected prices are EUR (not
    an error)."
  - `#plan-line`: truthful variants (at least one execution plan
    BLOCKED / create-only / NO CHANGES — "nothing to create"), all
    linking `#plan-details`.
  - `#findings-line`: top-3 ranked "SEV × N — code — human label" lines
    with a link to the full ranked list, or "No blockers, no review
    findings."
  - `_render_changes` now wrapped in `<section id='changes'>` so
    "What changed" is a first-class section with heading and summary.
  - `_render_details` gained `#plan-details` (open only when a plan is
    actually blocked or the state is BLOCKED; the banner "At least one
    execution plan is BLOCKED: …" prints only when a plan is truly
    blocked — truthful for data-gate-blocked fixtures with zero
    executable rows) and `#gates-full` (open only when BLOCKED; the full
    per-gate checklist with every gate's own state, name and detail).
  - Typography: body 15px/1.4, h1 24, h2 17, h3 15, `.state` 18px,
    `.chip` 14px, `dl.kv` 15px, table 14px, `.line`/`.checkline` 15px;
    only secondary technical annotations (`.annot`, run-identity
    compact) are 12.5px.
  - Wide tables (provider 12-col, price 9-col, route 5-col,
    all-findings 5-col, backed-facts 7-col) wrapped in `.table-scroll`
    (overflow-x auto; in print, overflow visible + width auto so closed
    `<details>` content never widens the page).
- `tests/unit/test_catalog_refresh_report.py` —
  `test_first_screen_contains_required_decision_facts` rewritten for the
  new labels (BLOCKERS 0, "Scope & baseline", the three baseline
  meanings, "Deterministic checks", the five group labels,
  "gates-full", "Providers & changes", "Counts (recomputed)", "FX:",
  "Import plan", "No blockers, no review findings", "What changed",
  "run-identity-compact", "Run identity (expanded)", NOT_RUN, footer
  offline-scope phrase);
  `test_first_screen_blocks_are_visually_blocked` corrected to truth:
  the blocked fixture has ZERO executable plan rows (all blocked by data
  gates), so it asserts the honest "nothing to create (NO CHANGES)"
  plan line, the ABSENCE of the false plan-blocked banner, and
  `<details id='plan-details' open>` + `<details id='gates-full' open>`.
- `tests/browser/test_catalog_refresh_report.py` — full rewrite
  (405 lines changed): 8 cases (first-install CLI exit 0, blocked CLI
  exit 20, ready, warnings, large-unchanged 120 models,
  two-provider-long-IDs, price-change, fx-required). All generated
  HTML/screenshots/PDFs/metrics are written only under pytest-owned tmp
  output. Per case the test asserts: exactly 1 network request
  (the document itself, file://); static offline scans (no `<script>`,
  no external http(s)/asset references, no fonts); every internal link
  target exists; every FIRST_SCREEN_SELECTOR
  (`.state`, `#scope-baseline`, `#checks`, `#per-provider`, `#fx-line`,
  `#plan-line`, `#findings-line`, `#changes > h2`, `#changes >
  :nth-child(2)`) lies within the 1440x900 first viewport;
  `documentElement.scrollWidth` equals the viewport at 1440, 1280 and
  375 in BOTH collapsed and expanded views (fresh loads at 1280x800 and
  375x812); computed-font floors (body ≥15, h1 ≥20, h2 ≥16, dl.kv ≥14,
  table ≥13.5, chip ≥13.5, .state ≥17); short headers and provider
  cells stay single-line at 1440; after opening outer AND nested
  details, visible `inner_text()` contains the full 64-hex content
  digests and case-specific value needles (hidden-DOM `page.content()`
  is not accepted as visibility); `%PDF` magic for the two print cases;
  and it writes `metrics-final.json` to tmp.
  - `price-change` = the full existing `bundle-refresh-ready.json`
    driven through the CURRENT validator (updated-v1 input price
    1 → 1.2, +20.000 %): BLOCKED by `gate:import.pricing` +
    `gate:import.routes`; per-provider changed 1 / mutations 1 / new 1 /
    unchanged 1.
  - `fx-required` = a genuine FX-required case built with the existing
    policy/source helpers (`_bundle_payload` + real USD pricing + a real
    ECB reference XML source document in USD-EUR form + matching USD
    baseline): READY, USD→EUR 1.08 → 1.08, delta 0E-9, state UNCHANGED,
    published 2026-09-21T11:00, source ecb eurofxref — driven through
    the CURRENT validator/source contracts, not a hand-forged
    ValidationReport.
- `tests/fixtures/catalog_refresh/bundle-{first-install,refresh-ready,blocked,truncated}.json`
  — `revision.renderer_version` field only (180.5 → 180.6, one line
  each, diff-verified).
- `tests/fixtures/catalog_refresh/report-layout/` —
  `two-provider-long-ids.bundle.json` (renderer field only); DELETED
  superseded `print/ready-expanded-print.pdf`; NEW deliberately
  regenerated and inspected evidence: `two-provider-1440.png`,
  `price-change-1440.png`, `fx-required-1440.png`,
  `print/price-change-expanded-print.pdf` (180862 B),
  `print/fx-required-expanded-print.pdf` (168916 B),
  `metrics-final.json` (copied from the final passing run's pytest tmp,
  run directory `pytest-377`; values identical to the previous run except
  the tmp path prefix). The two print PDFs were copied from inspected
  outputs of the first passing run; the final re-run reproduced them
  byte-identically except the embedded CreationDate timestamp
  (identical sizes 180862 / 168916 B), which is exactly why routine
  tests never write tracked PDFs. Synthetic data only; no keys,
  tokens, or live source payloads.
- `tests/fixtures/catalog_refresh/browser-screenshots/` — the five
  existing PNGs (blocked, first-install, large-unchanged, ready,
  warnings), deliberately copied from inspected outputs of the final
  passing run (not overwritten by routine tests).
- `docs/catalog-refresh.md` — first-screen section rewritten ("First
  screen (decision overview)"), 180.6 versioning note appended,
  mutation-namespace bullet corrected (review refuses a group/other
  writable run root or seal-key parent; export-baseline refuses a
  group/other writable output parent; verify is read-only and enforces
  no writability), and the print/test-evidence paragraph now states that
  routine tests write pytest tmp only and committed artifacts are
  deliberately copied. Presentation/print/test-evidence wording only.
- `docs/cli-reference.md` — catalog-refresh descriptive wording only
  (exit 65 writability refusals for the writing commands; verify
  read-only).
- `admin/catalog-refresh/README.md` — checked; wording already
  accurate; unchanged.

## Before: the 180-h first screen (strategic review measurements)

From the order's verified state and
`/home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/180-h-review/
browser-independent.json` (independent file-URL probes on the exact
`fe250ec` bytes):

- Main gate/provider text 12.48px, run-identity annotation 12.48px,
  group labels 11.52px — below the order's 14px reading floor.
- The first scope+gate cards alone contained 276–298 words
  (first-install 276, blocked 291, ready 291, warnings 293,
  two-provider 298, large-unchanged 295).
- At 1440x900: scope+checks cards 113→530px; per-provider/FX
  538→805px; the top of the findings started 839–917px (two-provider
  917px — below the 900px viewport); the import-plan line started
  956–1034px; the "What changed" heading started 1082–1163px, i.e.
  after a full page of audit prose.
- The H browser `DASHBOARD_SELECTORS` omitted findings/plan/changes,
  tested 1280 only in the collapsed view, and its digest-visibility
  check searched `page.content()` (hidden DOM) rather than visible
  text.
- The committed screenshots split short ordinary words (new, changed,
  openrouter) inside narrow table cells.
- Ordinary browser-test execution wrote tracked PNG/PDF fixtures, and
  PDF metadata varied per run.

## I1 — A concise decision overview in the first viewport (closed)

The first screen is now a decision overview, not a compressed audit.
Computed at 1440x900 in the final run (all 8 cases; worst case =
`blocked`):

| first-screen element | bottom (px) at 1440x900 |
| --- | --- |
| `.state` banner | ≤ 176.1 |
| `#scope-baseline` card | ≤ 488.6 |
| `#checks` card | ≤ 488.6 |
| `#per-provider` section | ≤ 694.3 |
| `#fx-line` | ≤ 734.2 |
| `#plan-line` | ≤ 759.2 |
| `#findings-line` | ≤ 842.9 |
| `#changes` heading ("What changed") | ≤ 865.0 |
| first relevant change below it | ≤ 891.0 |

So the state/reason, scope+baseline, grouped checks, provider change
summary, FX, plan line, leading findings AND the "What changed"
heading with the first relevant change all fit in the first 1440x900
viewport in every case, including the worst (blocked) case. The six
order facts map to: (1) banner state + plain-language reason +
BLOCKERS/REVIEW chips + top-3 ranked findings line (no long
comma-separated code list as the primary reason; exact codes remain in
the findings); (2) `#scope-baseline` card with the plain baseline
meaning + compact run identity (full SQL attestation stays in expanded
`#run-identity`); (3) the full-width single provider table with a
recomputed-counts row (source-inventory vs baseline-comparison
columns kept distinct; no invented zeros); (4) `#checks` grouped
checklist with worst-state chips (full per-gate detail in
`#gates-full`, open when BLOCKED — no lost gates, no downgraded
findings); (5) `#fx-line` per pair or the single truthful N/A line
(local current rates kept distinct from derived proposals); (6)
`#plan-line` honest variant + the one concise footer notice
"offline scope: review/export/verify only — live source retrieval and
apply are unavailable in this version." (no apply button/command
exposed; READY never implies automatic mutation). All detailed
prices, routes, FX, provenance, validation, raw proposed rows and
unchanged catalogs remain inline in the same artifact in native
expandable sections; no JavaScript, no network-on-open, no external
assets/fonts.

Typography (computed, 1440): body 15, h1 24, h2 17, table 14, chip 14,
`.state` 18, `dl.kv` 15, `.line`/checklines 15 — every primary reading
surface ≥ 14px; only secondary technical annotations are 12.5px. Short
headers and provider cells stay single-line at 1440 in all 8 cases
(`short_labels_single_line_1440: true`), fixing H's mid-word breaks.

## I2 — Test what the administrator sees, without changing the repository (closed)

The browser test was rewritten as described in Changed paths. Final
actual run: 1 passed in 176.83s, exit 0 (8 cases; tmp
`/tmp/pytest-of-ubuntu/pytest-377/catalog-report0`). Per-case actuals
from `metrics-final.json`:

| case | state | requests | scrollW 1440/1280/375 | visible digests | details opened |
| --- | --- | --- | --- | --- | --- |
| first-install | READY | 1 | 1440/1280/375 | — (no sources) | 14 |
| blocked | BLOCKED (4) | 1 | 1440/1280/375 | 5 | 15 |
| ready | READY | 1 | 1440/1280/375 | 5 | 15 |
| warnings | READY_WITH_WARNINGS (5) | 1 | 1440/1280/375 | 5 | 24 |
| large-unchanged | READY (120 models) | 1 | 1440/1280/375 | 5 | 410 |
| two-provider | READY (long IDs) | 1 | 1440/1280/375 | 7 | 23 |
| price-change | BLOCKED (2) | 1 | 1440/1280/375 | 5 | 22 |
| fx-required | READY (FX UNCHANGED) | 1 | 1440/1280/375 | 5 | 25 |

- Document `scrollWidth` equals the viewport width at all three widths
  in both collapsed and expanded views (expanded values asserted in
  the test; 1280/375 recorded in metrics; the old 1440 overflow came
  from normal-flow tables, now `.table-scroll`; a closed `<details>`
  does not expand document width — probe-verified).
- Exactly one network request per case; static scans prove no scripts,
  no external assets/fonts; all internal link targets resolve.
- Visible-text proof: after opening outer AND nested details,
  `inner_text()` contains the full 64-hex content digests (5, or 7 for
  two-provider) plus case needles (e.g. the +20.000 % price row, the
  USD→EUR 1.08/1.08 0E-9 UNCHANGED FX row with ecb eurofxref).
- Print: `price-change` (180862 B) and `fx-required` (168916 B) PDFs
  carry `%PDF` magic (asserted in test); both were visually inspected
  page by page — full price table with 1.2 / +20.000 % CHANGED, full
  64-hex digests, the FX line with source/date, no clipped columns,
  sensible print type.
- The new price-change and fx-required cases exercise the CURRENT
  validator/source contracts (real validator gates for the blocked
  price change; a real ECB document + USD baseline for the FX case).
  All-EUR N/A cases alone no longer stand in for the FX display.
- State/counts/source classifications remain deterministic and
  unchanged (neutrality proof below); no code change was made to make
  a presentation fixture pass; the local mandatory browser run passes,
  it does not skip.

## I3 — Precise claims and narrow verification (closed)

H acceptance claims that were insufficient, and what now proves them:

1. Font sizes: H's main gate/provider text measured 12.48px (group
   labels 11.52px). Now every primary reading surface computes ≥ 14px
   (body 15 / table 14 / chip 14 / state 18) with computed-font floors
   asserted in the browser test.
2. First-screen completeness: H's DASHBOARD_SELECTORS omitted
   findings/plan/changes and its geometry pass could not see the
   decision surface (findings began 839–917px; What-changed
   1082–1163px; two-provider findings below the viewport). Now
   FIRST_SCREEN_SELECTORS covers state, scope/identity, grouped
   checklist, provider summary, FX, plan line, findings line AND the
   What-changed heading + first relevant change, all asserted ≤ 900px
   in all 8 cases.
3. Mid-word short-label breaks: H's committed screenshots split new /
   changed / openrouter inside narrow cells. Now single-line checks on
   short headers and provider cells pass in all 8 cases at 1440 and
   the committed screenshots were visually inspected.
4. Geometry predicates: H measured selected container boxes at 1280
   collapsed only and checked digests in hidden DOM. Now the real
   document `scrollWidth` is measured at 1440/1280/375 collapsed AND
   expanded, and visibility is asserted on visible `inner_text()`
   after expanding outer and nested details.

H's accepted semantic-neutrality, source/financial gates and trust
wording are preserved (trust wording in the expanded source-evidence
and digest annotations is unchanged; reflow and safe link/escaping
behavior retained).

Documentation corrections (I3, documentation only — no behavior
change): the docs no longer imply review is the only command that
writes files. Verified in code and now stated precisely: `review`
refuses a group/other-writable run-root directory and seal-key parent
directory (exit 65; `assert_mutation_namespace("run root directory")`
in the CLI and `"seal key parent directory"` in the filesystem
module); `export-baseline` refuses a group/other-writable output
parent (`publish_new_only_file` →
`_assert_mutation_namespace(parent_fd, "output parent directory")`);
`verify` is read-only and does not enforce writability as a mutation
policy.

Renderer revision incremented to 180.6 and evidence regenerated; no
archived run was rewritten or re-signed. Semantic neutrality proof:
five cases (first-install READY, refresh-ready BLOCKED, blocked
BLOCKED, truncated BLOCKED, two-provider READY) were rendered through
`validate_bundle` on the exact `fe250ec` bytes (temporary worktree at
`/tmp/obj180i/neutrality-fe250ec`, module load verified via printed
`__file__`) and on the final tree, and the typed reports + artifacts
(`routes-proposal.tsv`, `pricing-proposal.tsv`, `fx-proposal.json`)
were recursively diffed: the ONLY difference is
`renderer_version` 180.5 → 180.6. States, counts, gate decisions,
warnings, monetary and capability comparisons, dispositions, import
gates and all artifact digests are identical.

## Acceptance results (AP-I1 .. AP-I5)

- AP-I1 (legible concise first viewport, changes-led progression,
  findings and actual relevant changes visible, all details retained
  inline): MET — first-viewport table above (worst case ≤ 891.0px at
  1440x900 in all 8 cases), computed fonts ≥ 14px for primary text,
  inspected 8 screenshots + 2 print PDFs, full detail sections inline.
- AP-I2 (current-pipeline price and FX cases, worst-state
  aggregation/count reconciliation, no invention, explicit offline
  scope): MET — price-change and fx-required driven through the
  current validator/source contracts; worst-state chips per gate
  group; "Counts (recomputed)" row; honest no-inventory line; single
  footer offline-scope notice.
- AP-I3 (real geometry and font/short-label checks, visible expanded
  evidence, 1440/1280/375 collapsed+expanded, inspected print PDF, no
  network/scripts): MET — document scrollWidth = viewport at all
  widths collapsed and expanded; computed-font floors; single-line
  short labels; visible 64-hex digests after expanding details;
  `%PDF` + page-by-page visual inspection; exactly 1 request/case and
  static offline scans.
- AP-I4 (routine browser tests leave the worktree unchanged; new
  captures deliberately regenerated once with exact source identity
  and actual exit codes): MET — `git status --short` after the final
  browser run shows only the intended implementation paths and no
  untracked repository output; the five browser-screenshots PNGs and
  the three report-layout PNGs were verified byte-identical to the
  final passing run's outputs (tmp `pytest-377`); metrics copied from
  that same run (values identical to the previous run except the tmp
  path prefix); the two report-layout PDFs were verified identical to
  the final run's PDFs apart from the embedded CreationDate timestamp;
  actual exit codes recorded below.
- AP-I5 (focused unit/browser tests, lint, docs/internal links,
  diff-check, ordinary final-head CI green; semantic-neutrality and
  exact-path proof): MET — 284 unit tests passed, browser file passed,
  ruff clean, documentation checker OK (91 files), diff-check clean,
  CI green at the implementation head (see CI), neutrality and
  exact-path proofs above.

## Local verification and actual exit codes

All commands run with the repository `.venv` (Python 3.12) on the
final tree (commit `b45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a`):

- Focused unit suite (9 files:
  `test_catalog_refresh_{baseline,bundle,filesystem,policy,report,seal,source_evidence}.py`,
  `test_cli_catalog_refresh.py`, `test_oap_governance.py`):
  **284 passed in 34.59s**, exit 0.
- Standalone browser file
  `tests/browser/test_catalog_refresh_report.py`: **1 passed in
  176.83s**, exit 0 (8 cases; pytest tmp
  `/tmp/pytest-of-ubuntu/pytest-377/catalog-report0`).
- `ruff check` on the four changed `.py` files: All checks passed
  (exit 0). (The repository gate is `ruff check` only; `ruff format
  --check` was not applied to avoid reformatting untouched files.)
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK files=91`
  (exit 0).
- `git diff --check 686f642`: clean (exit 0).
- Semantic-neutrality probe (five cases, `fe250ec` vs final tree):
  only `renderer_version` differs (recorded above; summary kept at
  `/tmp/obj180i/neutrality-diff-summary.txt`).
- No complete local/HPC/integrated matrix, PostgreSQL, Redis, gateway
  server or Docker run was required or performed for this suffix.

## CI (PR #317 implementation head)

At implementation head
`b45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a`, all ten final-head checks
are `completed`/`success` (verified via the commit check-runs API at
2026-09-22T18:59:59+02:00, `total=10 pending=0 not_green=0`; checks
completed 2026-09-22T16:57:02Z–16:59:53Z): Analyze
(javascript-typescript), Analyze (python), Analyze Python, CodeQL,
Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E
tests, Playwright browser smoke, PostgreSQL integration tests, and
Unit, lint, and migration head. The rewritten browser file is CI-safe
(no database, Redis, provider, Docker, or network dependency; real
file:// documents rendered by the repository venv's Playwright
Chromium, which the Playwright browser smoke job already provisions).
The report-only SELF commit adds one markdown file under `oap/reports/
` and no executable path; its report-head checks run after this
publication (see Status).

## Privacy and no-mutation proof

- No shared 5432 instance, its configuration or logs, the privileged
  `postgres` identity, protected credentials, `.env` files, or any
  live source collector was accessed in this round. All evidence is
  synthetic: fixtures carry no keys, tokens, or secrets (the URLs are
  the public pricing/models listing and ECB reference pages already
  used by existing fixtures); screenshots and PDFs contain only
  synthetic fixture data.
- No application metadata mutation, no production import, no real
  upstream calls, no email.
- `oap/orders/180-i-*.md` and `oap/active` bytes are unchanged since
  the activation commit (protocol bytes only); no other `oap/` path
  touched before this report.
- No repository path outside the order's exact allowed list was
  modified by the implementation commit (23 files, checked against
  the list); the four bundle fixtures and the schema file are
  diff-verified one-line changes.

## Resource identity and cleanup

- Temporary worktree `/tmp/obj180i/neutrality-fe250ec` (checked out at
  the exact `fe250ec` bytes, clean status) was used only for the
  neutrality probe and is removed after publication.
- `/tmp/obj180i/` holds this round's probes, patch scripts, inspected
  screenshot/PDF rasters and logs; cleaned after the protocol OK,
  retaining `ci-poll.log` and the FIFO OK marker.
- Unrelated worktrees, `.local-provider-catalog/`, the root
  `AGENTS.md`, and the permanent `message.txt` are preserved; earlier
  objective scratch (`/tmp/obj180a*` … `/tmp/obj180h*`) is preserved.

## Corrections to the 180-h report (this report only)

- The 180-h report's acceptance narrative for the first screen (H1/H2
  legibility and first-viewport completeness) is superseded by the
  strategic review measurements quoted in "Before" (12.48px main
  text, 276–298 words in the first cards, findings/plan/changes
  starting 839–1163px, mid-word breaks in the committed screenshots,
  geometry predicates that omitted those surfaces). The I1/I2
  measurements in this report replace those specific claims. The 180-h
  report's accepted semantic-neutrality proof, source/financial gates,
  and trust wording remain as recorded and are re-proven here where
  relevant.
- Documentation wording implying that review is the only command that
  writes files is corrected (I3): `review` (run root + seal-key
  parent) and `export-baseline` (output parent) carry
  writability-refusal policy (exit 65); `verify` is read-only and does
  not enforce writability. Documentation-only change; no behavior
  change.

## Still REQUIRED for later objectives (not implemented here)

- Live source retrieval and the Codex research workflow;
  supersession handling; the explicitly confirmed audited apply
  command; and the surrounding administrator workflow. These remain
  required subsequent numeric objectives after Objective 180 is
  resolved. This suffix completes the presentation work for the
  offline foundation only. Objective 180 is NOT complete; 181 is NOT
  pre-activated.

## Status

Objective 180 remains OPEN and NOT complete. PR #317 is OPEN at the
report commit (this report is the single report-only SELF commit whose
first parent is the literal implementation head
`b45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a`). The
implementation-head CI state is recorded above as already-existing
GitHub state; the report-only SELF commit's own checks run AFTER this
publication and are independently verified by strategy — they are
inspected before the protocol OK is sent where feasible, without
rewriting this report. The coding agent never merges or enables
auto-merge; no tag or release was created; awaiting the next strategic
order (a same-PR suffix may follow without resolving the numeric
objective first).
