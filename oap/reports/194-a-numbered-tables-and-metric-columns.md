# OAP Objective 194-a — final report: numbered admin tables and independent usage/quota metric columns

Work order: `oap/orders/194-a-numbered-tables-and-metric-columns.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `194-a`; order sha256
`1f0d1a175023347d10a59ea638f2480537d584a29190950bc24e05e6b5d6f0be`).
Branch: `oap/194-numbered-tables-and-metric-columns`, base `main`
`90a114a236a80469780fb9341b751520d5a3f964` (PR #344 merge; remote `main`
verified at that base at publication).
PR mode: CREATE_NEW_PR (Objective 194 = exactly one new PR, draft #346,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/346).
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: 5708b848661c67e3f902e02331f2f46d5e5c5315
Report publication commit: SELF

## Implementation commits (branch order)

1. `5708b848661c67e3f902e02331f2f46d5e5c5315` — "Number admin table rows
   and separate usage and quota columns (194-a)": all implementation,
   docs, and tests together with the unchanged activated order and
   `oap/active` (40 files).

## Process honesty

This report closes the SAME continuously activated 194-a execution: the
original strategic control `OK` was delivered and consumed exactly once
(no re-signal, no new control reader, no profile/model/effort change, no
195 activation). Strategic review notes received during the execution
(grouped-header selection, literal count text, empty-state colspan,
per-column widths, inventory-guard false passes, verification-doc
reconciliation) were applied within the same bounded scope. All WIP, the
activated order/active bytes, and the protected unrelated untracked
artifacts (`CODEX-SESSIONS.md`, `codex.sh`; gitignored `.codex/` and
`.local-provider-catalog/`) were preserved untouched. The order's A5 test
economy rule was honored: focused evidence only, no full-matrix rerun.

## What changed

Presentation only — row numbering, split metric columns, and Rows
selectors (195 owns multi-value OR-within/AND-between list filters; no
server OR support is claimed in this PR):

1. **R1 structural ordinals.** Every one of the 25 admin tables (24
   templates, including provider-detail's two tables) and every generated
   catalog-refresh `REVIEW.html` table family gets a real first-position
   `#` column: server-rendered `{{ loop.index }}` data cells (coherent
   with JS disabled), a plain non-sortable ordinal header, and
   renumbering by the fixed shared `table-sort.js` after every sort
   (plain `th[data-ordinal]`; positional `td.ord` 1..N per displayed
   logical row; `data-no-sort` rows excluded). Initial business ordering
   remains until a data-header click.
2. **R2 provenance stays distinct.** Import preview/result "Row" →
   "Source row" (separately labeled, sortable provenance column, distinct
   from the ordinal in all eight import templates); report apply-plan
   `#` → `Plan #` (stable sortable reference, no bare sortable `#`).
   Group head + continuation rows count as ONE record with no misleading
   second ordinal; empty-state/summary/footer/fixed rows are never
   numbered and carry `data-no-sort` with colspans equal to the leaf
   column count (keys table: single `colspan="13"` row). Row groups,
   IDs, URLs, forms, CSRF, inputs/checkboxes, review selections, and
   import-line references are preserved.
3. **R3 split metrics.** Key list: grouped Usage (Requests/Tokens/Cost
   (EUR)) and Quotas (Requests/Tokens/Budget (EUR)); bulk-import
   preview/result split their combined quota cell into Budget (EUR)/
   Tokens/Requests. Each actual metric has its own typed raw sort key and
   is independently sortable; no metrics invented on tables that never
   had them. `0` displays `0` with exact fixed-point raw key (not the DB
   `0E-9` string), `NULL` displays `Unlimited` with an empty raw key
   (missing, last in both directions), money displays via the existing
   `dec` filter; exact signed-64 integers and Numeric(18,9) precision
   preserved; no accounting recomputation, quota enforcement,
   reservation, cost, or ledger change.
4. **R4 key-list structure.** Approved mockup order: ordinal, key public
   identity/hint, owner/name/email/institution, dedicated cohort,
   status, Valid from / Expires, Usage group, Quotas group. Duplicated
   cohort removed from the owner secondary line; human-readable UTC dates
   (`%d %b %Y`) via the new bounded `utc_date_display` presentation
   filter, full precise timestamp still accessible (title), raw-datetime
   sort retains the actual instant.
5. **R5 readability.** Per-column minimum widths (key 12rem, owner 9rem,
   cohort 7rem, email 13rem, subject 14rem; table-wide 64rem, 56rem at
   ≤1100px), tabular right-aligned numbers, whole status labels; the wide
   keys table scrolls INSIDE its labeled region at 390/768 without
   page-wide overflow.
6. **R6 visible Rows controls.** All eleven GET-limit lists expose a
   visible `Rows` select (`name="limit"`, bound to the existing GET
   filter form via `form=`; presets 10/25/50/100/200 plus a preserved
   `N (current)` custom option; no duplicate hidden limit field) and the
   real `{{ collection|length }} rows shown` count (the ten batch-
   generated toolbars were literal-count bugs repaired in this PR).
   These controls are classified as bounded NUMERIC preset/custom
   selectors, not database reference pickers.
7. **R7 trusted/offline behavior.** The SAME fixed `table-sort.js` bytes
   (report embedding byte-exact against the current shared source,
   asserted); the unused `data-col`/`bodyCol` explicit-mapping feature is
   removed from doc and code (leaf position equals body position in every
   authored table; no rowspan-first-row sorting is claimed); no eval,
   network, dynamic code, or user-data-as-code added; `model-review.md`
   stays NON-GUI static Markdown; data artifact/import CSV schemas
   unchanged.

## Explicit non-changes

No schema, migration, model, quota/accounting, provider/adapter,
Responses-compatibility, transport, content-capture, or dependency
change. `services/key_import.py` untouched. `api/admin.py` gained only
the bounded `utc_date_display` presentation filter and its registration
(no route/query refactor; the display DTO already carried cohort,
validity, and all metrics). `services/catalog_refresh/rendering.py`
gained only the ordinal injection pass and `td.ord` fixed CSS. No
production DB/SSH/deploy/release/tag; no real provider/model/email/
credential use.

## Verification (this objective; focused; ALL synthetic data)

Environment: venv `/tmp/slaif192-coding-venv`, `PYTHONPATH=app`,
explicit `TEST_DATABASE_URL` only via the `owned_pg_url` fixture (unique
owner-labeled, 127.0.0.1-loopback, tmpfs-backed disposable PostgreSQL 16
container, identity inspected before use, removed by exact ID after use;
no ambient `DATABASE_URL`, no foreign containers), native Playwright
Chromium, real pytest exits captured via `PIPESTATUS[0]`, JUnit XML
under `/tmp/slaif194/`.

### Layer 1 — unit (no DB; pure rendering / mocked ASGI)

- Focused group — new `tests/unit/test_admin_table_rows_194.py` (zero/
  one/many SSR ordinals, zero-row fixed empty state, one/many rows, typed
  metric cells, keys Rows selector through a real ASGI render, and the
  all-11 Rows source guard over the eleven templates + route signatures,
  proven to reject a literal-`{{ var|length }}` count and a form-unbound
  select via a throwaway in-memory mutation probe); strengthened
  25-table structural-ordinal + Source-row guards in
  `tests/unit/test_admin_usability_inventory.py` (proven to reject
  "ordinal moved to last cell" and "empty-row marker removed"
  regressions); report ordinal injection + `Plan #` in
  `tests/unit/test_catalog_refresh_report.py`:
  **131 passed / 0 failed / 0 skipped** (`unit-final.xml`, real exit 0).
- Re-run focused and green in the same session (proportionate stale-
  oracle updates only): catalog-refresh unit family (152 passed, exit 0)
  and admin template-safety/routes/branding/design/inventory unit files
  (184 passed, exit 0). No broad local matrix rerun (order A5; routine
  CI supplies the broad matrix).

### Layer 2 — real authenticated admin HTTP + owned PostgreSQL + native Chromium

- `tests/browser/test_admin_usability.py` focused 4 tests
  (`browser-usab-1.xml`, 4 passed, real exit 0) plus the focused
  `test_keys_metric_columns_sort_independently` node re-run after the
  budget fixture change (`browser-metric-1.xml`, 1 passed, real exit 0):
  owners-table sorting with the shifted column indices and ordinal
  renumbering after every sort; the NEW six-metric-column independent
  sort proof — ALL SIX columns (usage Requests/Tokens/Cost, quota
  Requests/Tokens/Budget), both directions, exact typed orders from
  divergent seeds (budget: `0, 0.000000001, 7.75, 10×7, 12.5, ∅` with the
  `NULL` limit last in BOTH directions), faithful zeros in cost, per-row
  metric-tuple association preserved, ordinals 1..12 after every sort, a
  plain ordinal header with no link, Enter activation on a metric
  header; bulk-import preview/result Source-row ordering with split
  Budget/Tokens/Requests and the execute form's action/checkbox/CSRF
  state preserved across a sort; institution/cohort filters with the
  shifted name column index.
- `tests/browser/test_admin_visual_screenshots.py`: **9 passed**
  (`browser-visual-1.xml`; refreshed after the budget fixture change in
  `browser-refresh-1.xml`, 10 passed = 9 visual + 1 import — overlap, not
  additional unique cases; real exit 0): dashboard and keys list at four
  viewports with the grouped thead (plain group row, 13-cell leaf row,
  12 hyperlink sort headers, plain ordinal), SSR ordinals 1..12, "12
  rows shown", custom limit 37 preserved as the selected `(current)`
  option, 390px per-column minimum widths (key ≥190px, owner ≥142px,
  cohort ≥110px) with the wide table scrolling inside its labeled region
  while the page does not overflow; the 193 chips-grow-down proof
  unchanged. Screenshots at `/tmp/slaif194/screenshots/`.
- `tests/browser/test_admin_dashboard_smoke.py`,
  `test_admin_slaif_design.py`, `test_admin_branding.py`,
  `test_admin_lazy_throttling.py`: 12 collected = **10 passed + 2
  skipped**, 0 failed/error (`browser-misc-1.xml`, real exit 0). The two
  skips are the optional Playwright admin-smoke tests skipped with the
  specific reason "TEST_DATABASE_URL is required for optional Playwright
  admin smoke tests" — an explicit-URL environment gap of this local
  invocation (skips are not passes; routine CI supplies the URL and runs
  them).
- Beyond-float-precision and signed-64 upper-edge numeric proofs came
  from root's separate Jinja-template/mock-HTTP/Chromium component
  probes; they are NOT claimed as permanent PG-suite coverage.
- Two test-side oracle repairs during this execution (recorded in the
  verification record; no product code changed): the cost-column
  expected list miscounted the seeded zeros, and a grouped-thead label
  expectation compared against markup text while the rendered text is
  CSS-uppercased.

### Layer 3 — offline generated report (file URL, Chromium; NO gateway, NO auth, NO PostgreSQL)

- `tests/browser/test_catalog_refresh_report.py`: **2 passed**
  (`browser-report-1.xml`, real exit 0): generated `REVIEW.html` fixture
  files opened by file URL against mock research fixtures — the all-case
  layout contract (provider name the second cell behind the ordinal;
  single-line headers at 1440/1280/375) and the JS-on sort proof: the
  fixed script sorts the field table and the per-provider summary
  independently, ordinals renumber 1..N after the sort, the plain ordinal
  header carries no link, and the report still makes exactly one network
  request (the document). This layer shares no gateway/auth/PostgreSQL
  dependency with Layer 2.

### Layer 4 — static checks

- `ruff check app tests`: clean (exit 0). `git diff --check`: clean.
- `table-sort.js` contains no `data-col`/`bodyCol` feature (doc and
  code); the report embeds the same fixed bytes (byte-equality asserted
  by the existing report tests).

### Honest layer separation

Unit evidence (mocked ASGI / pure renderer) does NOT prove browser
behavior; browser evidence (real PG + Chromium) does NOT prove the broad
unit/integration matrix; the offline report layer shares no gateway/auth/
PG dependency. The full local unit/browser matrix was deliberately NOT
repeated for fresh evidence (order A5 test economy); routine CI supplies
the broad matrix.

## CI status at the implementation head (5708b84)

All ten check-runs for the literal implementation head
`5708b848661c67e3f902e02331f2f46d5e5c5315` are SUCCESS (observed
2026-10-25 at 17:51:48 UTC via the GitHub check-runs API):

| Check | State |
| --- | --- |
| Unit, lint, and migration head | success |
| PostgreSQL integration tests | success |
| Playwright browser smoke | success |
| OpenAI-compatible E2E tests | success |
| Docker Compose smoke | success |
| Documentation hygiene | success |
| CodeQL | success |
| Analyze Python | success |
| Analyze (python) | success |
| Analyze (javascript-typescript) | success |

No failures, cancelled, or missing checks were observed for that head.
Pushing the report-only commit triggers a new CI run at the report head;
checks for the report-containing commit are pending/not observed at the
moment this report is published and remain the strategic/root gate
before acceptance/merge.

## Pending root follow-up (pre-merge finding, truthful record)

Root's independent pre-merge review recorded
`OBJECTIVE-194-RENDERER-IDENTITY-FINDING.md` (strategic side): these
presentation changes alter `REVIEW.html` bytes, so pre-194 sealed reports
(renderer identity `183.1`) are no longer byte-stable-replayable under
the current renderer while the sealed-report contract still pins
`RENDERER_VERSION="183.1"`. The 194-a immutable order excludes
schema/constant changes, so the renderer identity was intentionally NOT
advanced in this round. A bounded SAME-PR continuation (renderer
metadata `194.1` + focused upgrade proof/docs, no schema change) is
expected as a root-activated 194-b after this handoff. No historical
renderer framework, silent re-derivation/reseal, or DB migration is in
scope. Until it lands, objective 194 must NOT be claimed merge-ready and
its final-head merge gates are NOT complete.

## Honest limits / skips

- No full local unit/browser/all-layer matrix or 128-worker sharded run
  was performed; routine CI supplies the broad matrix at the PR head.
- Native Chromium on this machine only; no other browser/mobile claim.
- Two optional Playwright admin-smoke tests skipped locally with the
  specific TEST_DATABASE_URL reason stated above; routine CI runs them.
- The signed-64 / beyond-float-precision edge numeric proofs are root's
  separate component probes, not permanent PG-suite cases.
- Screenshot/review directories (`/tmp/slaif194/`) are local review
  artifacts, not repository content.

## Docs impact statement

Updated: `docs/admin-usability.md` (194-a law: structural ordinal,
provenance distinctness, split metrics, key-list structure, readability,
the eleven Rows controls classified as bounded numeric selectors and NOT
reference pickers, report `td.ord` vs admin row ordinals stated
accurately), `docs/first-time-operator-guide.md` (the eleven GET-limit
Rows lists), `docs/verification/README.md` (index entry). New:
`docs/verification/2026-10-25-admin-numbered-tables-and-metric-columns.md`
(bounded verification record with exact JUnit counts, layer separation,
real exit codes, honest skips, and CI/publication state). Deployment:
no schema/migration/key change; the standard documented
upgrade/restart path applies; shared CSS/JS asset revision URLs change
automatically because their bytes changed.

## Safe boundary statement

- No schema/migration/model change; no quota/accounting/reservation/
  cost/ledger change; no provider/adapter, Responses-compatibility,
  transport, or content-capture change; no dependency change.
- Auth/session/CSRF semantics unchanged; forms, inputs, checkboxes,
  review selections, hidden values, and import-line references are
  verified preserved across sorts (Layer 2).
- No eval/network/dynamic code in the shared report script; the embedding
  is byte-exact against the current shared source; no secrets printed or
  committed; all data synthetic.
- The coding agent never merged and did not enable auto-merge; draft PR
  #346 remains open for strategic review, final-head check verification,
  the bounded renderer-identity continuation, and guarded merge.
  Objective 195 is NOT activated by this execution.
