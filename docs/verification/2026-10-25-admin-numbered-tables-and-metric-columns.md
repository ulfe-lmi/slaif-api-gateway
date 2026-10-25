# 2026-10-25 Objective 194-a admin numbered tables and metric columns verification

Recorded 2026-10-25 (UTC) in the OAP coding worktree for objective 194
(`oap/194-numbered-tables-and-metric-columns`, base `origin/main`
`90a114a236a80469780fb9341b751520d5a3f964`, PR #344 merge). This record
describes what the focused runs below actually proved. It is not a
full-matrix rerun, not a release/production claim, and it does not
establish that every 194 merge gate is complete (see
"Outstanding" below).

## Scope under test (194-a)

- R1: structural first-position ordinal column in ALL 25 admin tables
  (24 templates) and the generated catalog-refresh `REVIEW.html`;
  plain header; server-rendered 1..N; renumbered by the fixed shared
  `table-sort.js` after every sort.
- R2: group/empty/fixed rows never numbered; import provenance
  "Row" → "Source row" (sortable, kept distinct from the ordinal);
  report apply-plan `#` → `Plan #` (stable sortable reference).
- R3: combined metrics split (keys: Usage Requests/Tokens/Cost (EUR);
  Quotas Requests/Tokens/Budget (EUR); bulk-import: Budget (EUR)/
  Tokens/Requests) with typed raw keys; `0` displays `0`, `NULL`
  displays `Unlimited` with an empty raw key; `dec` filter for money.
  All SIX keys metric columns (usage Requests/Tokens/Cost, quota
  Requests/Tokens/Budget) are covered by the permanent PG/Chromium
  sort proof, including a budget column seeded with an actual zero, a
  tiny Decimal, ordinary values, a `NULL` limit (missing, last in both
  directions), and the plain 10s.
- R4/R5: keys list per mockup; per-column min-widths; table-contained
  horizontal scroll at 390/768 without page overflow.
- R6: visible Rows selector (presets 10/25/50/100/200 + preserved
  custom limit) bound to the existing GET filter form; displayed-row
  count; no duplicate hidden limit.
- R7: the SAME fixed `table-sort.js` bytes (byte-equality asserted);
  no eval/network; `model-review.md` stays non-GUI.

Strategic rendered-review repairs applied in the same execution:
literal Jinja counts in the ten batch-generated toolbars, empty-state
rows consistently excluded from sort units and numbering (with
colspan corrected on the keys table), per-column minimum widths for
key/owner/cohort (and email/subject) identity columns, and removal of
the unused `data-col` explicit-mapping feature from `table-sort.js`
(leaf position equals body position in every authored table; no
rowspan-first-row sorting is claimed).

## Environment

- Python: `/tmp/slaif192-coding-venv` (project dev venv),
  `PYTHONPATH=app`.
- Database: explicit `TEST_DATABASE_URL` only, via the
  `owned_pg_url` fixture (unique owner label, 127.0.0.1 loopback,
  tmpfs PostgreSQL 16, identity inspected before use, cleanup removes
  only the exact created container). No ambient `DATABASE_URL`, no
  foreign containers.
- Browser: native Playwright Chromium. Synthetic metadata only — no
  real provider/model/email, no production DB/SSH/deploy.

## Layer 1 — unit (no DB; pure rendering / mocked ASGI)

Command shape: `PYTHONPATH=app pytest tests/unit/test_admin_table_rows_194.py
tests/unit/test_admin_usability_inventory.py tests/unit/test_catalog_refresh_report.py
-q -p no:cacheprovider --junitxml=/tmp/slaif194/unit-final.xml`;
REAL pytest exit `0` (captured via `PIPESTATUS[0]`).

- `tests/unit/test_admin_table_rows_194.py` (new, 4 tests): the REAL
  keys page rendered through the ASGI app with the unit fake session —
  zero-row fixed empty state (single `colspan="13"` `data-no-sort`
  row, never numbered), one/many rows with server-rendered ordinals,
  grouped thead (plain group row + 13-column leaf row, first leaf
  header plain ordinal), split metric cells with typed raw keys
  (actual zero `0`, `Unlimited` with empty raw key, `dec` money
  `2.5`/`100`), and the Rows selector bound to the GET filter form
  (presets, no hidden duplicate, `37 (current)` preserved option).
  A further SOURCE-structure audit
  (`test_all_eleven_get_limit_lists_have_bound_rows_selectors`) pins
  EXACTLY the 11 GET-limit lists and each one's wiring (source audit
  over the 11 templates + the route signatures — real-render proof
  exists for the keys page in this unit file and in the Layer 2
  browser tests; root separately probed all 11 pages against owned
  PG; the all-11 guard itself is not a PG/render run): matching
  GET-form id, the select's `form` association, presets, the
  preserved `N (current)` custom option, the REAL
  `{{ <collection>|length }} rows shown` interpolation (the 10-page
  literal-count bug class), no hidden duplicate limit field, and the
  usage/audit CSV-export forms keeping their SEPARATE visible limit
  input. A temporary in-memory mutation probe (not committed, temp
  dir removed after use) confirmed the guard REJECTS both a
  literal-`{ var|length }` count and a form-unbound select. These
  controls are classified as bounded NUMERIC preset/custom selectors,
  not database reference pickers, and are documented as distinct from
  the 102-field known-reference inventory.
- `tests/unit/test_admin_usability_inventory.py` (strengthened):
  `test_every_admin_table_has_structural_ordinal_column` now inspects
  EVERY authored tbody row of all 25 tables — each data row must
  START with the SSR `{{ loop.index }}` ordinal cell, and every
  empty-state row must carry `data-no-sort` on its `<tr>` with
  `colspan` equal to the leaf column count (relative template paths in
  failure messages); `test_import_tables_keep_source_row_provenance_
  distinct` pins the sortable "Source row" header in all eight import
  preview/result templates and forbids a bare "Row" header.
  A temporary in-memory mutation probe (not committed, temp dir
  removed after use) confirmed the strengthened guard REJECTS both
  the "ordinal moved to last cell" and the "empty-row fixed marker
  removed" regressions, with the unmutated baseline passing.
- `tests/unit/test_catalog_refresh_report.py` (extended): the report
  injection pass — exactly one plain ordinal header per sortable
  table (first thead cell), 1..N positional cells per tbody row in the
  initial business order, the apply-plan reference relabeled `Plan #`
  (no bare sortable `#` header remains), and no `data-col` mapping in
  the report or the embedded fixed script.

Combined focused unit group (final run): 131 passed, 0 failed, 0
skipped (JUnit `/tmp/slaif194/unit-final.xml`).

Also re-run focused and green in the same session: the
catalog-refresh unit family (report/seal/apply/admin/filesystem/CLI +
script audit, 152 passed, exit 0) and the admin template-safety/
routes/branding/design/inventory unit files (184 passed, exit 0) —
proportionate updates of stale 193-era oracles only; no broad matrix
rerun was performed locally (routine CI supplies the broad matrix).

## Layer 2 — real authenticated admin HTTP + owned PostgreSQL + native Chromium

All groups: REAL pytest exit `0` (captured via `PIPESTATUS[0]`):

- `tests/browser/test_admin_usability.py` focused 4 tests (JUnit
  `/tmp/slaif194/browser-usab-1.xml`) plus the focused
  `test_keys_metric_columns_sort_independently` node re-run after the
  budget fixture change (JUnit `/tmp/slaif194/browser-metric-1.xml`):
  owners-table sorting with the shifted column indices and ordinal
  renumbering after each sort; the NEW
  `test_keys_metric_columns_sort_independently` covering all SIX
  metric columns with seeded DIVERGENT orders — every column sorted
  ASCENDING with its exact typed order (`0…/1,2,3,4,5` usage
  requests; `0…/25,75,80,90,990,1000` usage tokens; faithful zeros
  in the cost column; `900,900,2000…` quota requests;
  `500×6,700,800,1500×4` quota tokens; and `0, 0.000000001, 7.75,
  10×7, 12.5, ∅` budget with the `∅` NULL limit last), the
  quota-tokens and budget columns additionally sorted DESCENDING with
  exact reversals (the NULL limit stays last in both directions),
  per-row metric-tuple association preserved, ordinals 1..12 after
  every sort, a plain ordinal header with no link, and Enter
  activation on the usage-requests header; bulk-import preview/result with Source-row
  ordering, split Budget/Tokens/Requests cells, and the execute
  form's action/checkbox/CSRF state preserved across a sort;
  institution/cohort name filters with the shifted name column
  index. (The full all-six-columns-BOTH-directions numeric matrix,
  and the beyond-float-precision / signed-64 upper-edge values, were
  proven by root's separate actual-template/mock-HTTP/Chromium
  component probes; they are NOT claimed as permanent PG-suite
  coverage — the permanent case covers every column ascending, the
  quota-tokens and budget columns descending, and Enter activation on
  the usage-requests header.)
- `tests/browser/test_admin_visual_screenshots.py` (9 tests, JUnit
  `/tmp/slaif194/browser-visual-1.xml`, refreshed after the budget
  fixture change in `/tmp/slaif194/browser-refresh-1.xml`): dashboard
  (4 viewports) and keys list (4 viewports) with the grouped thead
  (plain group row, 13-cell leaf row, 12 hyperlink sort headers,
  plain ordinal), SSR ordinals 1..12, "12 rows shown" count, custom
  limit 37 preserved as the selected `(current)` option, and at 390px
  per-column minimum widths (key ≥190px, owner ≥142px, cohort
  ≥110px) with the wide table scrolling inside its labeled region
  while the page does not overflow; chips grow-down layout proof
  unchanged. Screenshots at `/tmp/slaif194/screenshots/` (full-page,
  per viewport).
- `tests/browser/test_admin_dashboard_smoke.py`,
  `test_admin_slaif_design.py`, `test_admin_branding.py`,
  `test_admin_lazy_throttling.py` (12 collected = 10 PASS + 2 SKIP,
  0 fail/error, JUnit `/tmp/slaif194/browser-misc-1.xml`). The two
  skips are the optional Playwright admin-smoke tests, skipped with
  the specific reason "TEST_DATABASE_URL is required for optional
  Playwright admin smoke tests" — an explicit-URL environment gap of
  this local invocation (skips are not passes; routine CI supplies
  the URL and runs them).

Focused oracle repairs during this execution (honest record): the
first run of the focused browser groups produced exactly two test-side
failures, both fixed in the tests and re-run green — (a) the new
cost-column expected list miscounted the seeded zeros (7 instead of
8; keys 3, 5, and 6–11 are zero), and (b) the grouped-thead label
expectation compared against the markup text while the rendered text
is CSS-uppercased (same posture as the existing `.eyebrow` checks).
No product code changed for either.

## Layer 3 — offline generated report (file URL, Chromium; NO gateway, NO auth, NO PostgreSQL)

- `tests/browser/test_catalog_refresh_report.py` (2 tests, REAL exit
  0, JUnit `/tmp/slaif194/browser-report-1.xml`): generated
  `REVIEW.html` fixture files opened by file URL against mock
  research fixtures — the all-case layout contract (provider name now
  the second cell behind the ordinal, single-line headers at
  1440/1280/375) and the JS-on sort proof: the report's fixed script
  sorts the field table and the per-provider summary independently,
  the ordinal column renumbers 1..N after the sort, the plain
  ordinal header carries no link, and the report still makes exactly
  one network request (the document). This layer shares no
  gateway/auth/PostgreSQL dependency with Layer 2.

## Layer 4 — static checks

- `ruff check app tests`: clean (exit 0).
- `git diff --check`: clean.
- `table-sort.js` no longer contains the `data-col`/`bodyCol`
  feature (doc and code); the report embeds the same fixed bytes
  (byte-equality asserted by the existing report tests).

## Honest layer separation and outstanding items

- Unit evidence (mocked ASGI / pure renderer) does NOT prove browser
  behavior; browser evidence (real PG + Chromium) does NOT prove the
  broad unit/integration matrix. The full local unit/browser matrix
  was deliberately NOT repeated for fresh evidence (order A5 test
  economy); routine CI supplies the broad matrix.
- GitHub/CI state at the time of this record: the implementation
  commit exists on the local branch only; no 194 PR, no GitHub checks,
  and no OAP immutable report exist yet. The PR is created as a DRAFT
  by the coding agent after this commit, routine CI then runs on the
  implementation head, and the immutable OAP report is published as
  the final (SELF) commit only after the observed GitHub state
  justifies the claims it carries; final-head and report-only
  publication checks remain the strategic/root gate. Nothing in this
  record claims CI or publication state that does not already exist.
- PENDING ROOT FOLLOW-UP (root-discovered pre-merge, recorded in
  `/home/janezp/codex-supervision/slaif-api-gateway/workorders/
  OBJECTIVE-194-RENDERER-IDENTITY-FINDING.md`): the presentation
  changes alter `REVIEW.html` bytes, so pre-194 sealed reports
  (renderer identity `183.1`) are no longer byte-stable-replayable
  under the current renderer, while the sealed-report contract still
  pins `RENDERER_VERSION="183.1"`. 194-a's immutable order excludes
  schema/constant changes, so the renderer identity was NOT advanced
  in this PR round. A bounded SAME-PR continuation (renderer
  metadata `194.1` + focused upgrade proof/docs, no schema change)
  is expected after this handoff; no historical renderer framework,
  silent re-derivation/reseal, or DB migration is in scope. Until it
  lands, do not claim all 194 merge gates complete.
- The OAP immutable report for 194-a, when published as the final
  (SELF) commit, will state the actual publication state truthfully
  (including this pending-item record) and will not claim checks that
  have not been observed green.
