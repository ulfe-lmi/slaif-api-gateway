# OAP Immutable Report — 180-h: make catalog review fast and readable

PR mode: AMEND_EXISTING_PR on PR #317 (branch
`oap/180-catalog-refresh-bundle-review`, base `main`).

## Identity

- Starting SHA (committed PR head when this order started):
  `e65e5678b45046375a2e326ec24ceb15077a5e48` (the 180-g report commit;
  its sole changed file is the 180-g report, whose implementation parent
  is `07a75f96437e8059d8c8f92d9015e9eb23893641`)
- Activation commit (order file + `oap/active` pointer, exact strategic
  bytes `180-h`): `fde46beb9488d7baf8587ec12fa1b6ddc1c6364d`
- Implementation commits:
  `a80d2897113bd75dfe33c6007147d51c7b196b4c` (presentation rewrite,
  21 files, +1683/−330) and
  `fe250ec12263f2e40d33f34ad363e588ca957306` (verify exit-table wording
  correction, documentation only, 1 file, +10/−5)
- Implementation head SHA:
  `fe250ec12263f2e40d33f34ad363e588ca957306`
- Report publication commit: SELF
- PR #317 remains OPEN. Never merged, auto-merge not enabled, no tag, no
  release. The only published release remains `v0.1.0-rc.1`. No
  production-certification claim follows. Objective 180 is NOT complete.

## Changed paths (implementation head vs starting SHA)

Protocol commit `fde46beb9488d7baf8587ec12fa1b6ddc1c6364d` (activation
only):

- `oap/orders/180-h-make-catalog-review-fast-and-readable.md` (new order,
  unchanged since activation)
- `oap/active` (exact strategic bytes `180-h`)

Implementation commit
`a80d2897113bd75dfe33c6007147d51c7b196b4c` (all within the order's exact
allowed paths; no other path touched):

- `app/slaif_gateway/services/catalog_refresh/rendering.py` (presentation
  layer rewritten; executable behavior of validation, sealing, and the
  filesystem boundary untouched) —
  - First-screen decision dashboard: state banner (state + concise
    reason + BLOCKERS/REVIEW/all-findings chips); two-column card grid
    (below 900 px it collapses to one column) containing the
    scope-and-baseline card (why this state, finding counts with codes,
    compact provider + model-filter selection with considered/selected/
    out-of-scope counts, honest baseline mode/target and capture-path
    note with the exact SQL-evidence text, the
    "live source retrieval is unavailable in this version" line, compact
    source-evidence line), the grouped deterministic gate checklist
    (five display groups — Source evidence; Schema & pricing
    completeness; Pairing & supported capabilities; Changes &
    reconciliation; Import plan validation — each group shows its worst
    state, every individual gate keeps its own state chip, name, and
    detail, and any ungrouped gate is listed individually), the
    per-provider card (two clearly separated sub-tables: "Source
    snapshots (offline replay of supplied documents)" vs "Baseline
    comparison (this run)", an honest "no source snapshots parsed" line
    when no source parsed, and a non-additive footnote), and the FX card
    (per pair: current, proposed, signed delta, state, publication date,
    source, derived-reciprocal markers — or a truthful "not required"
    line); then the create-only execution plan card with a conspicuous
    blocked banner, the aggregated top-findings card (ranked groups with
    counts, concise human labels, exact codes retained, link to the full
    list), the recomputed counts line, and a compact run identity line
    (run ID, generated time, SLAIF revision, schema/renderer revision,
    policy version, profile/endpoint) linking to the expanded identity
    section.
  - Changes-first detail section: "What changed" leads — price changes
    with old/new values, units, currencies and signed percentages plus a
    rounding note (display rounds to 0.001 %; the gate decision uses the
    exact stored ratio, so a strictly above-threshold movement can
    display at the threshold), route/attribute changes with current →
    proposed values and reason (create-only; no apply operation exists),
    an explicit "Unchanged: N model(s)" line pointing to the collapsed
    unchanged section; disappearance is displayed as an observation, not
    a delete operation; conspicuous warnings are preserved and no
    decision is downgraded by presentation logic.
  - Evidence on demand, all inside the same file: native
    `<details>`/`<summary>` sections hold all warnings and findings
    (open by default, per-item detail), full validator outputs,
    import-gate details, source inventory and reconciliation with FULL
    64-hex digests (never truncated), per-source parse status with the
    registry parser, the exact parsed observations that bound each
    proposed fact (observed value, unit, currency, exact locator, URL,
    full digest, parser, retrieval time, normalized value and
    transformation, declared backing sources, distinct-URL
    independence), FX facts bound to verified reference quotes, the
    reconciled evidence inventory with per-provider selection
    dispositions and bounded ID lists, baseline identity with the SQL
    capture-path note, expanded run identity, bundle notes, and the
    unchanged rows. Bounded example lists are labelled with their
    totals; nothing is silently dropped.
  - The formerly overflowing provenance/source tables (up to 17 columns)
    and expanded observation rows (up to 11) are reflowed into label/
    value cards and wrapping tables; long run IDs, model filters, URLs
    and digests wrap (`word-break`) instead of forcing the page wider.
  - Print CSS: 2px borders on state and chips, severities underlined so
    state is legible without colour, `tr { page-break-inside: avoid }`,
    opened sections print in full and closed sections print as their
    summary line only; the behaviour is documented in the report footer
    and verified by an actual browser PDF.
  - The CSP is unchanged (`default-src 'none'; style-src
    'unsafe-inline'`), escaping and the safe-href allowlist
    (http/https + same-document fragment anchors only) are preserved,
    and no script, event handler, external resource, iframe, or network
    fetch exists or is added.
- `app/slaif_gateway/schemas/catalog_refresh.py` — `RENDERER_VERSION`
  constant only: `180.4` → `180.5`. No other schema/policy/capability
  change.
- `app/slaif_gateway/services/catalog_refresh/validation.py` — ONLY the
  explanatory `SQL_CAPTURE_DOCUMENT` note and its adjacent comment: the
  supplied document DECLARES a historical SQL export; consuming the file
  does not verify that execution occurred and the review does not attest
  it. No gate, boolean, comparison, disposition, pricing, capability, or
  SQL change.
- `tests/browser/test_catalog_refresh_report.py` (NEW, 449 lines) —
  standalone file-URL browser tests (no gateway server, PostgreSQL,
  Redis, TEST_DATABASE_URL, or provider dependency): six real pipeline
  documents (CLI-published sealed runs for first-install and blocked;
  in-process `validate_bundle` + `render_report` for ready, warnings,
  large-unchanged, and a new synthetic two-provider case — the same pure
  functions the CLI drives), opened as `file://` in a
  JavaScript-disabled Chromium context with full request recording
  (exactly one request: the document itself); geometry measured with
  bounding boxes (the six dashboard selectors inside the first
  1440x900 viewport for every case; page-wide overflow scans of
  `main, table, pre, .chip, .kvchip, td.num` at 1440 collapsed and
  expanded, fresh 1280x800 loads, and fresh 375px loads collapsed AND
  expanded — 375 expanded is the "usable" guarantee); static HTML scans
  (no `<script>`, `on*` handlers, `src=`, forbidden real tags, `@import`/
  `url(` in CSS, safe-href allowlist), all internal `href="#x"` targets
  exist, full 64-hex digests visible when expanded; the five canonical
  1440x900 first-viewport screenshots are rewritten as actual current-
  renderer captures and an actual print PDF of the expanded ready
  document is captured. The narrow-width checks use a fresh page load
  per viewport on purpose: closed `<details>` content can report stale
  1440-era bounding boxes after a same-page resize in headless Chromium
  (an artifact a real narrow-viewport user never sees); fresh loads are
  clean.
- `tests/fixtures/catalog_refresh/browser-screenshots/*.png` (5 files) —
  replaced with actual captures of the current renderer at 1440x900
  (first-viewport clip); no unrelated binary artifacts.
- `tests/fixtures/catalog_refresh/bundle-first-install.json`,
  `bundle-refresh-ready.json`, `bundle-blocked.json`,
  `bundle-truncated.json` — `renderer_version` field only
  (`180.4` → `180.5`); all other facts preserved.
- `tests/fixtures/catalog_refresh/report-layout/` (NEW) —
  `two-provider-long-ids.bundle.json` + `two-provider-long-ids.baseline.
  json` (synthetic two-provider case: two providers, long model IDs and
  URLs, escaped hostile display names, no keys/secrets — the source
  URLs are the public pricing/models listing and ECB reference pages
  already used by the existing fixtures) and `print/ready-expanded-
  print.pdf` (135,017 bytes, 11 pages, actual `page.pdf()` output of the
  fully expanded ready case).
- `docs/catalog-refresh.md` — one-page-report section rewritten for the
  new layout (first-screen dashboard, changes-first, evidence on
  demand, documented print behaviour), plus the H3 trust-contract
  corrections (see below).
- `docs/cli-reference.md` — catalog-refresh verify exit-code lines and
  the filesystem-boundary paragraph made precise (same corrections,
  presentation/truth only).
- `admin/catalog-refresh/README.md` — verify exit note made precise;
  SQL-capture DECLARES wording; the eventual wrapper contract now says
  it prints the local report path for browser review and must NOT
  require a new management dashboard surface.
- `tests/unit/test_catalog_refresh_report.py` — static-HTML scan now
  accepts same-document fragment anchors (`href="#x"`) as the only
  non-external href form (native internal links, no fetch); the
  pre-existing string-presence test is unchanged in intent.
- `tests/unit/test_cli_catalog_refresh.py` — the expected
  `DOCUMENT_SQL_NOTE` text constant updated to the corrected note.

Implementation commit
`fe250ec12263f2e40d33f34ad363e588ca957306` (documentation only, no
behavior change; see "Corrections to the 180-g report", item 4, and
"Local verification" for the empirical basis):

- `docs/catalog-refresh.md` — the corrected `verify` exit-table row no
  longer claims a peer-writable key parent is refused; the mutation-
  namespace enforcement bullet now states it applies to `review`, the
  only command that mutates, and records that read-only `verify` does
  not enforce writability on the run directory or the key parent.

Allowed but UNCHANGED this round (no change needed):
`app/slaif_gateway/cli/catalog_refresh.py`,
`app/slaif_gateway/services/catalog_refresh/filesystem.py`,
`tests/unit/test_catalog_refresh_seal.py`.

## Before: the current first screen (verified state)

The order's verified state: the committed first-install screenshot at
1440x900 spent most of the viewport on prose and repeated
identity/SQL/execution descriptions; FX started at the bottom and the
gate checklist was below the fold; the pre-existing unit string-
presence test (`test_first_screen_contains_required_decision_facts`)
asserts substrings only and did not establish viewport placement. The
old captures remain in the tree at the starting SHA
(`tests/fixtures/catalog_refresh/browser-screenshots/*.png` at
`e65e5678b45046375a2e326ec24ceb15077a5e48`) and are replaced by the new
captures in this round's implementation commit.

## H1 — A real first screen for a busy administrator (closed)

The new first screen is the decision dashboard described above. Actual
measured geometry (JavaScript disabled; request recording; bounding
boxes, not substring presence; the final run's per-case metrics JSON is
quoted in "Local verification"):

- All six cases (first-install, ready, warnings, blocked,
  large-unchanged, two-provider) have every dashboard element —
  `.state`, `#scope-baseline`, `#checks`, `#per-provider`, `#fx`,
  `#run-identity-compact` — inside the first 1440x900 viewport without
  expanding details: the worst-case bottom edge across all cases is
  889.2 px (two-provider, `#run-identity-compact` bottom; all others
  ≤ 845.5 px), i.e. inside 900.
- No page-wide horizontal overflow in any case, collapsed or fully
  expanded: right edges are 1300 px at 1440 (the centered `main`
  content), 1220 px at 1280, and 359 px at 375 — including 375 with all
  details expanded (the "usable" guarantee).
- Exactly 1 network request per case (the `file://` document itself);
  no scripts, handlers, external resources, or CSS fetches.
- State lines visible in the first viewport: first-install/ready/
  large-unchanged/two-provider `READY — all recomputed gates verified;
  no review findings`; warnings `READY_WITH_WARNINGS — 5 review-level
  finding(s); no blockers`; blocked `BLOCKED — blocked by:
  currency_inconsistency, gate:completeness, gate:pricing.complete,
  missing_required_dimension`.
- The two-provider case is the realistic long-ID/long-URL synthetic:
  two providers, long model identifiers and URLs, escaped hostile
  display names; 7 full 64-hex digests visible when expanded.
- For many findings the dashboard shows ranked aggregate counts with a
  link to the full list (warnings case: summary "All warnings and
  findings (5)"), not pages of codes above the checklist; no obscured
  blocker and no claim of live retrieval anywhere ("live source
  retrieval is unavailable in this version" is explicit in the scope
  card).

## H2 — Changes first, evidence on demand, print without clipping (closed)

- "What changed" leads the detail section (price changes with old/new
  values, units, currencies, signed movement and the display-rounding
  note; route changes with current → proposed and reason; the
  unchanged count pointing to the collapsed unchanged section);
  unchanged rows are collapsed by default; disappearance is labelled an
  observation, not a delete.
- Every detail stays inside the single HTML: full validator outputs,
  per-source parse status, exact parsed observations with full 64-hex
  digests, FX quote bindings, baseline/run identity, exact proposed
  import rows, filtered reasons, unchanged rows. Bounded example lists
  carry their totals.
- Expanded evidence is readable without another file: the 17-column
  provenance and 11-column observation tables are reflowed into cards;
  long values wrap without truncating their accessible value.
- Print: the documented behaviour (opened sections in full; closed
  sections as summary line; 2px borders; severity underlines; rows not
  split across pages) is verified by an actual Chromium PDF of the
  fully expanded ready document:
  `tests/fixtures/catalog_refresh/report-layout/print/ready-expanded-
  print.pdf`, 135,017 bytes, 11 pages (letter, per `pdfinfo`), starts with `%PDF`, captured by
  the browser test itself (`print_pdf_bytes: 135017` in the metrics).
  PDF pages 1–2 and all six first-viewport screenshots were visually
  inspected (dashboard fits, no clipping, honest N/A lines, hostile
  names escaped); at report drafting, expanded PDF pages 4 and 11 were
  additionally re-verified (full 64-hex digests in the expanded
  validator JSON; the documented print-behaviour footer and compact run
  identity on the final page).
- Numbers and worst-state aggregation come from the unchanged validation
  semantics; presentation logic downgrades nothing.

## H3 — Truthful wording and renderer identity (closed)

Renderer revision bumped `180.4` → `180.5`; only that field changed in
the four existing fixtures. New sealed reports were produced by the
browser test's real CLI runs (first-install exits 0 READY, blocked
exits 20 BLOCKED, both sealed and published through the unchanged
filesystem/sealing boundary) and by in-process renderings for the other
cases; no archived run or old evidence was rewritten or re-signed.
Deterministic byte rendering is re-asserted by the unmodified
`test_render_is_deterministic_and_byte_stable` (rendering + validation
JSON byte-stable across recomputation), and new-run seal/verify replay
remains green in the unmodified seal suite.

The seven current-facing wording corrections are applied in
`docs/catalog-refresh.md`, `docs/cli-reference.md`,
`admin/catalog-refresh/README.md`, the `SQL_CAPTURE_DOCUMENT` note, and
this report's "Corrections" section below; the immutable 180-g report
and all earlier reports/orders are unchanged.

## Strategic review rounds

None issued for this suffix before publication; the order's verified
state and the strategic objective-180 provisional review
(`workorders/OBJECTIVE-180-PROVISIONAL-REVIEW.md`, 2026-09-22) informed
the scope, and no `workorders/180-h-*-feedback.md` file exists.

## Acceptance results (AP-H1 .. AP-H6)

- AP-H1 (first viewport for first-install, READY, WARNINGS, BLOCKED,
  large-unchanged + a realistic two-provider long-ID case; ranked
  finding counts; no obscured blocker; no claimed live retrieval):
  PASS — measured bounding boxes as in H1 above (worst dashboard bottom
  889.2 < 900 at 1440x900 for all cases; requests = 1 per case).
- AP-H2 (changes lead, unchanged collapsed, all raw facts accessible
  inline, numbers/worst-state match unchanged validation semantics):
  PASS — changes-first section; unchanged collapsed behind a labelled
  link; inline evidence with full digests; semantic-neutrality proof
  below shows the numbers are untouched.
- AP-H3 (no page-wide overflow expanded at 1440/1280; 375 usable;
  expanded price evidence readable; print/PDF retains documented
  summary/details without clipping): PASS — right edges 1300/1220/359
  (359 also with 375 fully expanded); visual inspection of screenshots
  and PDF pages 1–2.
- AP-H4 (no scripts/handlers/external resources/network on open or
  expand; hostile strings escaped; safe source links; valid internal
  link targets): PASS — per-case static scans + request recording
  (1 request each) + internal-target check in the browser test; hostile
  display names in the two-provider fixture render escaped.
- AP-H5 (deterministic byte rendering, new-run seal/verify replay, all
  prior source/policy/financial/privacy tests, semantic-neutrality
  proof): PASS — 291-test focused unit suite green (determinism and
  seal replay included); neutrality probe below shows only the
  authorized diffs.
- AP-H6 (docs corrected, dated history unchanged, report caveats
  precise, changed paths allowed, documentation checker, internal
  links, changed-Python lint, git diff --check, ordinary final-head CI):
  PASS locally (below); CI at the implementation head in the CI
  section. All changed paths verified against the order's exact allowed
  list.

## Local verification and actual collection counts

All commands run from the repository root in the current venv; actual
process exit codes captured (not pipeline status):

- Focused 9-file unit suite (`test_catalog_refresh_baseline`,
  `test_catalog_refresh_bundle`, `test_catalog_refresh_policy`,
  `test_catalog_refresh_report`, `test_catalog_refresh_seal`,
  `test_catalog_refresh_source_evidence`, `test_cli_catalog_refresh`,
  `test_documentation_contract_drift`, `test_catalog_refresh_filesystem`):
  **291 passed in 34.45s, EXIT=0** (re-run after the final
  documentation correction; the run against
  `a80d2897113bd75dfe33c6007147d51c7b196b4c` was 291 passed in 33.63s,
  EXIT=0).
- NEW standalone browser file (`tests/browser/test_catalog_refresh_report.py`,
  the CI browser job command `python -m pytest tests/browser -m
  playwright` reduced to this file): **1 passed in 280.62s (0:04:40),
  EXIT=0**.
- OAP governance suite (`tests/unit/test_oap_governance.py`): **8
  passed in 0.34s, EXIT=0**.
- `ruff check` on the six changed Python files: **All checks passed**.
- `python3 scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=91`, **EXIT=0**.
- `git diff --check e65e5678b45046375a2e326ec24ceb15077a5e48
  fe250ec12263f2e40d33f34ad363e588ca957306`: clean.
- No database, Redis, provider, Docker, or full local/HPC matrix was
  run this round (the order explicitly scopes them out; no disposable
  PostgreSQL was started). The post-#220 128-worker HPC qualification
  remains **NOT RUN**. Skips are not passes.

Browser per-case metrics (final run, measured with bounding boxes;
requests = network requests recorded while opening the document):

| case | dashboard worst bottom (1440x900) | right edge 1440/1280/375 (collapsed) | 375 expanded | 1440 expanded | details opened | full digests visible | state text |
|---|---|---|---|---|---|---|---|
| first-install | 845.5 | 1300 / 1220 / 359 | 359 | 1300 | 12 | n/a (no sources) | READY — all recomputed gates verified; no review findings |
| ready | 828.7 | 1300 / 1220 / 359 | 359 | 1300 | 13 | 5 | READY — all recomputed gates verified; no review findings |
| warnings | 811.9 | 1300 / 1220 / 359 | 359 | 1300 | 22 | 5 | READY_WITH_WARNINGS — 5 review-level finding(s); no blockers |
| blocked | 845.5 | 1300 / 1220 / 359 | 359 | 1300 | 15 | 5 | BLOCKED — blocked by: currency_inconsistency, gate:completeness, gate:pricing.complete, missing_required_dimension |
| large-unchanged | 845.5 | 1300 / 1220 / 359 | 359 | 1300 | 408 | 5 | READY — all recomputed gates verified; no review findings |
| two-provider | 889.2 | 1300 / 1220 / 359 | 359 | 1300 | 21 | 7 | READY — all recomputed gates verified; no review findings |

Every case recorded exactly 1 request (the document itself).

Semantic-neutrality proof (AP-H5): the four canonical fixtures
(`bundle-first-install.json` with no baseline, `bundle-refresh-ready.
json`, `bundle-blocked.json`, `bundle-truncated.json` against
`baseline-synthetic.json`) were pushed through `validate_bundle` under
the 180-g implementation tree (`07a75f96437e8059d8c8f92d9015e9eb23893641`,
temporary worktree, removed after capture) and under this
implementation head, with each tree's own fixture bytes:

- old output SHA256
  `85f93840c8d068c2989b8d9331632ec09313045972ca3c49205e8766b478e1ff`
- new output SHA256
  `6afe28ceaafd728d1308cef2b8dfe073c357a177937df675ac90aab87265beb5`
- the ONLY semantic diff is the corrected `SQL_CAPTURE_DOCUMENT` note
  text in the three document-baseline cases (the authorized explanatory
  correction); the first-install case is byte-identical; states, gates,
  counts, and all monetary/capability comparisons are unchanged; the
  validation output carries no renderer-version field, so the
  `180.4` → `180.5` identity bump cannot drift into any decision.

Exit-table correction, empirically re-verified this round (real CLI
subprocess runs, sealed first-install fixture run, task-owned temp
tree, cleaned up):

- `verify` on the normal sealed run: **0** (`validation: ok`);
- `verify` with the run directory `chmod 0777` (valid key): **0**
  (`validation: ok`) — read-only verify does not enforce mutation-
  namespace writability;
- `verify` with a symlinked run directory: **30** (`run_dir: missing`);
- `verify` with a missing run directory: **30** (`run_dir: missing`);
- `verify` with a missing key: **65** (`seal key file does not exist
  … (verify never creates keys)`);
- `verify` with a symlinked key parent: **65** (`seal key path is not
  safely accessible`);
- `verify` with the key as a directory: **65** (`seal key must be a
  regular file`);
- `verify` with the key at mode 0644: **65** (`seal key must be mode
  0600`);
- `verify` with the key stored in a group-writable (0775) parent: **0**
  (`validation: ok`) — the basis of the final documentation correction
  (commit `fe250ec12263f2e40d33f34ad363e588ca957306`).

Layout defects found and fixed during this round (recorded honestly):

1. The "Unchanged" line emitted an internal `#unchanged` link even when
   there were zero unchanged rows (target element absent) — the link is
   now conditional.
2. A generic `.card + .card { margin-top }` rule pushed the second grid
   card down 10 px — scoped to non-grid contexts.
3. Headless-Chromium artifact: closed `<details>` content reports stale
   1440-era bounding boxes after a same-page viewport resize — narrow-
   width checks therefore use fresh page loads (documented in the test);
   not a real document overflow.
4. Several CSS tightening passes (spacing, 0.78rem base, group-level
   two-column gate checklist, inline chips, compressed footnotes)
   brought the worst dashboard bottom edge from 1082 px to 889.2 px at
   1440x900.

## CI (PR #317 implementation head)

At implementation head
`fe250ec12263f2e40d33f34ad363e588ca957306`, all ten final-head checks
are `completed`/`success` (verified via the commit check-runs API at
2026-09-22T17:30:25+02:00, `total=10 not_green=0`): Analyze
(javascript-typescript), Analyze (python), Analyze Python, CodeQL,
Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E
tests, Playwright browser smoke, PostgreSQL integration tests, and
Unit, lint, and migration head. The new browser file is CI-safe (no
database, Redis, provider, Docker, or network dependency; real
file:// documents rendered by the repository venv's Playwright
Chromium, which the Playwright browser smoke job already provisions).
The report-only SELF commit adds one markdown file under `oap/reports/
` and no executable path; its report-head checks run after this
publication (see Status).

## Privacy and no-mutation proof

- No shared 5432 instance, its configuration or logs, the privileged
  `postgres` identity, protected credentials, or any live collector was
  accessed in this round. Verified before cleanup: the only
  PostgreSQL/Redis processes present are the pre-existing shared
  cluster (`/var/lib/postgresql/16/main` listening on
  127.0.0.1:5432) and unrelated pre-existing services; no task-owned
  PostgreSQL or Redis process and no 5433 listener exists.
- All evidence is synthetic: the new two-provider fixture carries no
  keys, tokens, or secrets (grep-verified; its URLs are the public
  pricing/models listing and ECB reference pages already used by
  existing fixtures); screenshots and the PDF contain only synthetic
  fixture data.
- No application metadata mutation, no `.env` reads, no secret
  exposure, no production import, no real upstream calls, no email.
- `oap/orders/180-h-*.md` and `oap/active` bytes are unchanged since
  the activation commit (protocol bytes only); no other `oap/` path
  touched before this report.
- No repository path outside the order's exact allowed list was
  modified by the implementation commits (21 + 1 files, checked
  against the list).

## Resource identity and cleanup

- No task-owned PostgreSQL or Redis resources were created this round
  (none needed by the order); nothing was left behind. The temporary
  180-g tree worktree used for the neutrality probe and the CLI probe
  trees were removed after evidence capture.
- Task artifacts under `/tmp/obj180h*` (CI poller, logs, probe outputs,
  neutrality JSON pair) are removed as part of this round's cleanup
  after the report commit, except the CI poll log and the response-OK
  marker which are operational state.
- No global prune/reset/cleanup performed; unrelated worktrees,
  `.local-provider-catalog/`, the root `AGENTS.md`, and the permanent
  `message.txt` are untouched.

## Corrections to the 180-g report (this report only; the 180-g
report is immutable and unchanged)

1. The 180-g report says same-size in-place mutations are refused.
   Precisely: the bounded reader re-proves dev/ino/size on the opened
   descriptor after the read (refusing short reads and growing files
   via the EOF probe), but a same-size in-place mutation that races the
   read is NOT detectable at the byte level. The accepted guarantee is
   the single captured byte snapshot and the authenticated
   correspondence between it, the manifest, and the receipt, within the
   documented platform and threat scope. No new filesystem behavior was
   implemented to satisfy the older prose; the docs now state the
   precise guarantee.
2. The 180-g report attributes the source-identity race closure to the
   pre-rename/pre-rmdir identity check alone. Precisely: the boundary
   combines descriptor anchoring with enforced operator-owned,
   non-peer-writable mutation parents (for `review`, the only command
   that mutates); the identity check and the later name mutation
   (rename/rmdir) are separate operations on held descriptors, and no
   single syscall atomically compares a source inode against a name.
   No immunity against root, key-controlling, or same-uid full-
   authority code is or was claimed; the platform/threat-scope
   paragraph says so.
3. The 180-g report's receipt bounds wording conflated two constants.
   Precisely: verification reads the receipt with the shared
   `MAX_AUX_BYTES` cap (1 MiB); `RECEIPT_MAX_BYTES` (8 KiB) is the
   signing-overhead reservation inside the 128 MiB aggregate budget,
   not the verifier's read cap. The docs now state the actual behavior.
4. The 180-g report's verify exit table was imprecise. Precisely, as
   empirically re-verified this round: a missing, non-directory, or
   symlinked run directory with an otherwise valid key is verification
   invalid, exit 30; a missing or unsafe seal key (unsafe = refused by
   the no-follow walk, non-regular file, not exactly mode 0600, foreign
   ownership, or wrong length/content) is a data error, exit 65; and
   neither the run directory nor the key parent's group/other-
   writability is enforced by read-only `verify` (both empirically
   exit 0 in that case) — mutation-namespace enforcement belongs to
   `review`. CLI behavior was NOT changed to match any wording; the
   wording now matches the CLI.
5. The 180-g report's lifecycle paragraph described verify as keeping
   "the anchored handles for the run root and the seal-key parent".
   Precisely: `verify` anchors the run directory once through the
   no-follow walk (the held descriptor serves every read) and loads the
   existing key separately; it retains no key-parent lifecycle,
   publishes nothing, and never creates, repairs, or re-signs anything.
   The docs now describe the command-specific guarantees.
6. The 180-g wording implied a supplied baseline document proves
   historical SQL execution. Precisely: the document DECLARES a
   historical SQL export at its export time; consuming the file does
   not verify that execution occurred, and the review does not attest
   it. The `SQL_CAPTURE_DOCUMENT` note and all three documents now use
   that wording; the live-export and first-install notes are unchanged.
7. The admin README's eventual-wrapper contract implied surfacing
   `REVIEW.html` "in the admin dashboard". Precisely: the accepted
   architecture is one command producing one static report; the
   eventual wrapper prints the local report path so the operator opens
   it in an ordinary browser, and must NOT require a new management
   dashboard surface. The README now says so.

## Still REQUIRED for later objectives (not implemented here)

- Live OpenAI/OpenRouter/ECB retrieval, isolated Codex research, atomic
  historical price/FX supersession, and the final one-report workflow
  wrappers (which print the local report path) remain subsequent
  numeric objectives after Objective 180 is accepted and resolved.
- Objective 180 as a whole is NOT complete: this round finished the
  operator-facing presentation of the OFFLINE review foundation only.
  The full human goal — one refresh command → one trustworthy report →
  one explicitly confirmed audited apply command — is not met by
  offline tooling. Do not reduce the product to offline review; 181 is
  NOT pre-activated.
- No "perfect" or security-certified claim follows; the documented
  threat scope is local HMAC integrity against unprivileged local peers
  on Linux, not protection from a key-controlling administrator, root,
  or same-uid full-authority code.

## Status

Objective 180 remains OPEN and NOT complete. PR #317 is OPEN at the
report commit (this report is the single report-only SELF commit whose
first parent is the literal implementation head
`fe250ec12263f2e40d33f34ad363e588ca957306`). The implementation-head CI
state is recorded above as already-existing GitHub state; the
report-only SELF commit's own checks run AFTER this publication and are
independently verified by strategy — they are inspected before the
protocol OK is sent where feasible, without rewriting this report. The
coding agent never merges or enables auto-merge; no tag or release was
created; awaiting the next strategic order (a same-PR suffix may follow
without resolving the numeric objective first).
