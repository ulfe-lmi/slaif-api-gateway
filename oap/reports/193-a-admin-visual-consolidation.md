# OAP Objective 193-a — final report: admin visual consolidation and hyperlink table sorting

Work order: `oap/orders/193-a-admin-visual-consolidation.md` (strategic-authored,
committed unchanged with `oap/active` = `193-a`; order sha256
`334a1230ab2dec40299de38adafdfdd6b0d2418508f072a61609f4748e71b1fd`).
Branch: `oap/193-admin-visual-consolidation`, base `main`
`e814f37024b96ce01ea96d601a2676ded3dc45b3` (remote `main` verified at that
base at publication).
PR mode: CREATE_NEW_PR (Objective 193 = exactly one new PR, #344,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/344).
The coding agent never merges; no auto-merge is enabled; root reviews and
guard-merges independently.

Implementation head SHA: 096b2149bb6ccc9623d7da97eea413278c50a736
Report publication commit: SELF

## Implementation commits (branch order)

1. `4253229a0d7c188a76da237919779c831aad7e39` — "Consolidate admin
   dashboard and table-control appearance (193-a)": all implementation,
   docs, and tests together with the unchanged activated order and
   `oap/active` (82 files).
2. `4d70fcd7d6f0b1b4c8fb5a4c3ce7a2de35d7bf33` — "Repair dashboard route
   unit oracle for the 193-a grouped dashboard" (in-scope CI repair, see
   "CI repairs during this objective").
3. `096b2149bb6ccc9623d7da97eea413278c50a736` — "Repair browser-smoke and
   PG web-auth oracles for the 193-a dashboard copy" (in-scope CI repair).

## Recovery note (process honesty)

The original activated 193-a execution hit the model context-window limit
before publication. This report closes the SAME already-activated execution,
recovered under the same running profile: the original strategic control
`OK` was delivered and consumed exactly once (no re-signal, no new control
reader, no profile/model/effort change, no 194/195 activation). All WIP, the
activated order/active bytes, and the protected unrelated untracked files
(`CODEX-SESSIONS.md`, `codex.sh`, `.codex/`, `.local-provider-catalog/`)
were preserved untouched.

## What changed

Operator-facing admin visual foundations plus sorting-control semantics only
(194 owns row numbers/metric columns; 195 owns multi OR/AND filters; neither
is in this PR):

1. **Dashboard (R1).** `dashboard.html`: the main heading is now the product
   name INSIDE the dashboard body — `SLAIF API Gateway` with an
   Administration eyebrow/purpose/sign-in context — and the existing
   destinations are grouped under "Access management", "Providers and
   models", and "Usage and operations" with descriptions and a primary
   "Create gateway key" action. The implementation-oriented
   "Dashboard Foundation" auth/session/CSRF status prose is removed. Only
   existing destinations/actions are used; no fake metrics or backend
   capability. Sign-out REMAINS a real CSRF-protected POST button (styled
   as a plain text link; it is not an anchor and no logout semantics
   changed).
2. **Shared stable layout (R2).** `.page-shell` vertical centering removed
   for admin management pages (top-anchored; login/auth layout untouched);
   filter bars top-align labels/primary controls; chips, help, and new
   rows expand DOWNWARD — preceding headers/inputs and the Filter button
   stay fixed while the table below moves down and back up as chips are
   added/removed (proved by a real grow-down browser case). No fixed
   heights, clipping, or sticky hacks.
3. **Controls (R3).** Unified 42px bordered geometry, 13px/600 muted
   labels, 14px/400 values, shared radius tokens; native single dropdowns
   get a token-driven decorative arrow (`select:not([multiple]):not([size])`,
   so policy dual-lists keep the native box; native behavior/keyboard/
   options unchanged); the record-choice picker reads as ONE integrated
   control with the arrow inside the border and a compact clear
   affordance; a single selected value stays a CHIP below the box while
   the box keeps a BLANK search prompt (default "Search or select…",
   explicit caller placeholders win); the managed hidden field stays the
   scalar form authority (clear retains exactly one empty hidden field);
   no-JS behavior unchanged (multi 96px/auto overflow without JS, 42px
   no-resize after enhancement). All existing classes and data-* hooks are
   preserved; 193-a only ADDED wrapper classes (`rc-main`,
   `rc-main-multi`, `rc-js`) and chevron spans.
4. **Hyperlink table headings (R4).** Shared `table-sort.js` creates real
   focusable text hyperlinks (`<a class="ts-link" href="#ts-sort">`, safe
   local fragment, no network) with native Enter activation; a normal
   click and Enter toggle the sort, Space does NOT activate (link
   semantics); readable accent hover/focus without a button background
   fill; a subtle neutral sortability marker (U+2195) with reserved
   indicator space BEFORE the first click, then the specific up (U+2191) /
   down (U+2193) marker; `aria-sort` and all typed exact
   BigInteger/Decimal comparisons, missing-last in both directions,
   ties/groups/forms/report selections, initial business order, and
   displayed-only sorting are preserved; no header button remains in
   upgraded tables; existing action buttons remain actions. The generated
   catalog-refresh `REVIEW.html` fixed style carries the hyperlink-header
   look and its `<main id="ts-sort">` is the local fragment target for the
   report internal-link audit; the report STILL embeds the EXACT CURRENT
   shared script bytes through the same byte-exact loader (single-source
   law retained and asserted by tests) — the embedded bytes changed WITH
   the shared source (button -> hyperlink headers). No report
   manifest/auth/apply/collection semantics change.
5. **Asset freshness (R5).** New `web/assets.py` + ONE
   `templates.env.globals` registration in `api/admin.py`: deterministic
   local asset revision URLs for the seven bundled admin CSS/JS assets
   (fixed literal allowlist — never request/user input — mapped to static
   paths; `?v=` is the first 16 hex chars of the sha256 of the EXACT file
   bytes). Changed bytes -> changed URL; unchanged bytes -> stable URL.
   The digest covers content only (no paths, environment values, or
   secret material); no remote asset service, cache framework, service
   worker, database, or build step; the normal static mount serves the
   query URLs unchanged; unknown static names 404 (no arbitrary
   filesystem read). All base/conditional JS includes are versioned.

## Explicit non-changes

No schema, migration, model, quota/accounting, provider/adapter,
Responses-compatibility, transport, content-capture, or dependency change.
`services/key_import.py` untouched. `api/admin.py` gained exactly the
`asset_url` import plus the one `templates.env.globals` registration.
Existing branding rules/provider registry unchanged; the branding override
CSS still loads after the base CSS. No production DB/SSH/deploy/release/tag;
no real provider/model/email/credentials use.

## Verification (this objective; focused; ALL synthetic data)

Environment: owned temporary PostgreSQL 16 (loopback/tmpfs disposable
containers, identity verified before use, removed by exact ID after use),
real authenticated admin HTTP (uvicorn), native Chromium (Playwright
1.64.1, Chrome 156), venv `/tmp/slaif192-coding-venv`, `PYTHONPATH=app`,
explicit `TEST_DATABASE_URL` where a DB URL is consumed, JUnit XML plus
real pytest exit codes.

### Final local focused groups (pre-repair source state)

| Suite | JUnit | Result |
| --- | --- | --- |
| Focused unit set (13 modules incl. OAP governance, asset-revision proofs, 102-field/34-template inventory, record-choice macro, catalog-report fixed-script/security) | `final-unit-affected.xml` | 401 passed / 0 failed / 0 error / 0 skipped (49.610s, exit 0) |
| A1 screenshots: real rendered authenticated dashboard + keys list at 1440/1600/768/390, top-anchored panel, unified 42px/14px/400 + 13px/600 geometry, `a.ts-link` headers, default prompt, real-mouse chip grow-down + restoration | `final-a1.xml` | 9 passed / 0 failed (15.308s, exit 0) |
| 192-a usability regressions (hyperlink sorting: click AND Enter activate, Space does NOT toggle; record-choice batch/older search/keyboard/mouse; dependent clear; physical typing; import tables) | `final-usability.xml` | 9 passed / 0 failed (25.864s, exit 0) |
| Branding + SLAIF design (order/override, default + alternate theme contrast incl. transparent secondary links measured against their effective opaque surface, named regions, 768/375 surfaces) | `final-branding-design.xml` | 7 passed / 0 failed (31.022s, exit 0) |
| Offline report audit (13 generated `REVIEW.html` cases: exact fixed-script bytes, no external network, no untrusted script, internal links incl. `#ts-sort`) + lazy-throttling real app/PG (file NOT modified in 193; its record-choice helper repair is a 192-a change) | `final-report-lazy.xml` (shared) | 2 + 3 passed / 0 failed (215.215s, exit 0) |

The report suite is offline file-based by design (generated `REVIEW.html`
opened from disk; no PG/admin app); the other four groups run the real
rendered admin over real authenticated HTTP. The A1 grow-down proof covers
the real keys filter bar (owner picker); the other pages share the same
top-aligned filter-bar CSS.

### A1 Ruff-only repair recheck (post-noqa, same source behavior)

`tests/browser/test_admin_visual_screenshots.py` gained `# noqa: F401/F811`
markers for the shared pytest-fixture imports/parameters only (no behavior
change):

- full file re-run: 9 passed / 0 failed / 0 error / 0 skipped
  (`recheck-a1-recovery.xml`, 12.914s, real pytest exit 0);
- the one strategic-named regression
  `test_keys_chip_grow_down`: passed (`fixture-alias-check.xml`, real
  pytest exit 0); collect-only lists exactly 9 cases.

### OAP governance + lint checks

- `tests/unit/test_oap_governance.py`: 9 passed (real exit 0).
- `ruff check app tests` (pinned default policy, the exact CI scope):
  clean. (One pre-existing `migrations/versions/0023_*.py` F401 exists
  outside the CI scope and on `main` before this branch; untouched.)
- `git diff --check`: clean.

### Repaired-oracle focused evidence (post-repair heads)

- `tests/unit/test_admin_routes.py` module (repaired unit oracle):
  11 passed (real exit 0); full local unit suite re-run after the repair:
  real exit 0 with no failures (not re-run a second time for cleaner
  evidence; CI's full unit job is the final broad gate).
- Repaired PG target
  `tests/integration/test_admin_web_auth_postgres.py::test_admin_web_auth_session_and_csrf_flow`:
  1 passed / 0 failed (`repair-pg-webauth.xml`, 4.498s, real pytest exit 0).
- Repaired browser target
  `tests/browser/test_admin_dashboard_smoke.py::test_admin_dashboard_browser_smoke`:
  1 passed / 0 failed (`repair-browser-smoke.xml`, 14.474s, real pytest exit 0).

Both ran against a FRESH disposable loopback-bound, tmpfs-backed
`postgres:16` container created for this recheck (docker-inspect verified
BEFORE use: owner label `slaif193a.oracle.owner`, tmpfs mount at
`/var/lib/postgresql/data`, 127.0.0.1-only published port, no binds), with
an explicit `TEST_DATABASE_URL`; the container was stopped and removed by
exact ID afterward. No ambient `DATABASE_URL` and no foreign container were
used. All real-DB session/CSRF lifecycle and secret-output assertions in
the PG test are preserved unchanged.

### A1 screenshot evidence (strategic review accepted)

Full-page screenshots of the real authenticated dashboard and keys list
(synthetic records; keys table shows opaque prefix + public id only — no
one-time plaintext cells, CSRF values, or cookies read or screenshotted):
`/tmp/slaif193/screenshots/dashboard-{desktop-1440,desktop-1600,tablet-768,
narrow-390}.png`, `keys-{...}.png`, and `keys-chips-selected-desktop-1440.png`
(selected-chip state: chip row below the controls, primary control tops
unchanged, table moved down). Root independently rendered the real
authenticated visual subset (4 cases, owned PG, 8.160s, exit 0; all 7 source
hashes stable — `final-app-visual-receipt.json/.xml` under
`/tmp/slaif193-review`) and accepted the 193 visual scope.

## CI repairs during this objective (in-scope, no product rollback)

The first implementation head (`4253229`) failed EXACTLY THREE checks, all
stale pre-193 dashboard-copy oracles — no product-behavior failures:

| CI job (head 4253229) | Result | Stale oracle |
| --- | --- | --- |
| Unit, lint, and migration head | 1 FAIL / 5545 PASS / 1 SKIP | `test_admin_routes.py::test_get_admin_returns_dashboard_when_authenticated` (line 227) expected the removed "Dashboard Foundation" prose |
| Playwright browser smoke | 1 FAIL / 31 PASS | `test_admin_dashboard_smoke.py::test_admin_dashboard_browser_smoke` expected the old "Admin Dashboard" heading copy (lines 382 and 481) |
| PostgreSQL integration tests | 1 FAIL / 358 PASS / 9 SKIP | `test_admin_web_auth_postgres.py::test_admin_web_auth_session_and_csrf_flow` (line 157) expected the removed "Dashboard Foundation" prose |

Each repair changed only the stale positive-copy assertion to the 193-a
dashboard contract (product heading inside the dashboard body, the three
destination groups, and the ABSENCE of the foundation prose). All
response-status, authentication, CSRF, secret-output, and smoke-page
assertions are unchanged; no assertion was weakened; no production UI
rollback. All other jobs in that run passed (CodeQL, both Analyze suites,
Analyze Python, Docker Compose smoke, Documentation hygiene,
OpenAI-compatible E2E tests).

## CI status at the implementation head (096b214)

All ten checks for the literal implementation head
`096b2149bb6ccc9623d7da97eea413278c50a736` are SUCCESS (observed 2026-10-25,
run 40207219227 / 40207216755 / 40207216756 family):

| Check | State |
| --- | --- |
| Unit, lint, and migration head | pass (1m59s) |
| PostgreSQL integration tests | pass (5m0s) |
| Playwright browser smoke | pass (4m12s) |
| OpenAI-compatible E2E tests | pass (1m52s) |
| Docker Compose smoke | pass (53s) |
| Documentation hygiene | pass (7s) |
| CodeQL | pass (3s) |
| Analyze (python) | pass (2m39s) |
| Analyze Python | pass (1m9s) |
| Analyze (javascript-typescript) | pass (41s) |

No failures, pending, cancelled, or missing checks for that head. Pushing
the report-only commit may trigger a new CI run; checks for the
report-containing commit may therefore be pending at the moment `OK` is
sent — the strategic model independently verifies those final-head checks
before acceptance/merge.

## Honest limits / skips

- No full local suite / 128-worker sharded matrix was run for this
  objective; standard CI supplies the broad matrix at the PR head.
- Native Chromium on this machine only; no other browser/mobile claim.
- The no-JS fallback is exercised (raw field fill, visible original
  inputs), not a separate accessibility audit.
- The native-select arrow is decorative and token-driven; native select
  behavior/keyboard/options are unchanged, and multiple/size listboxes
  (policy dual-lists) intentionally keep the native box.
- Screenshot review directories (`/tmp/slaif193/`,
  `/tmp/slaif193-review/`) are local review artifacts, not repository
  content.

## Docs impact statement

Updated: `docs/admin-usability.md` (hyperlink sort semantics incl.
Enter/Space, neutral-then-directional indicators, report fragment target;
integrated-control visual contract; asset-revision URL section;
verification pointers), `docs/first-time-operator-guide.md` (sort/Enter
wording, chip/blank-prompt behavior, cache/upgrade/restart instructions —
no manual cache step for new pages, one hard refresh for already-open
tabs, no schema/migration/key change), `docs/verification/README.md`
(index entry). New: `docs/verification/2026-10-25-admin-visual-consolidation.md`
(bounded verification record with focused JUnit counts, actual-browser
facts, owned-PostgreSQL facts, and honest skips). Branding/security/catalog
docs needed no change: no changed contract wording (branding override
contract, admin session/CSRF boundary, and catalog refresh semantics are
unchanged).

## Safe boundary statement

- No schema/migration/model change; no quota/accounting change; no
  provider/adapter or Responses-compatibility change; no transport or
  content-capture change; no dependency change.
- Auth/session/CSRF semantics unchanged: login, session validation,
  per-form CSRF, and the CSRF-protected POST logout are exactly as before
  (the logout button is only restyled as a text link).
- Bundled-asset URLs now carry a content-only digest; no secret,
  environment, or path material appears in any URL; unknown static names
  are not arbitrary filesystem reads.
- No real provider/model/email/production calls anywhere in this
  verification; all records synthetic; no secrets printed or committed.
- The coding agent never merges and did not enable auto-merge; PR #344
  remains open for strategic review, final-head check verification, and
  guarded merge. Objectives 194 and 195 are NOT activated by this
  execution.
