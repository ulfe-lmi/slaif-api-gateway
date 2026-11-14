# OAP Report — 224-f Db-backed admin sections

- Order: `oap/orders/224-f-db-backed-admin-sections.md`
- Order SHA256: `00d27226d37d912b26c61b3057c15276acd4a8e89d34dddb6bffb685ec0709ba`
- `oap/active`: `224-f`
- PR: #383 `oap/224-demo-web` (AMEND_EXISTING_PR), base remote main
  `d3762e51c9a323dee6b728c4a45fa21b0bffae86`
- Prior remote head: `c1494f28a3c86f6a368ba97446114f79405d41bd`
  (224-e report-only SELF)
- Activation-bytes commit (root-authored order + active):
  `432951cbaf5e7581dece0e2d16278d925b7a3d4b`
- Implementation commit (sole parent of this report):
  `f67dc807b6ec73c1c36d0fcffc01f4e6c8fc6248`
- This commit: report-only SELF; sole diff vs the implementation
  commit is this report file.

## 1. What 224-f implements

1. **Seven more database-backed sections admitted** to the closed
   GET admission law (lists + canonical-lowercase-UUID details):
   providers, pricing, templates, fx, usage, audit,
   email-deliveries. Every one of the 14 candidate handlers was
   source-reviewed before admission: all read ONLY copied
   `public` rows through the existing repositories
   (`get_sessionmaker_from_app` request-local factory in demo
   mode), pure display helpers and the fixed neutral display
   settings - NO file, process or network read was found, so no
   family was kept gated for that reason and nothing was reported
   as an exception. No generic `/admin/{path}` passthrough; the
   UUID grammar is unchanged; all still-gated families (routes,
   operations, catalog, compatibility, OpenAI-assisted,
   accounting-recovery, replay maintenance, accounts, key
   batch/clone, form GETs, exports, `/admin/branding`) stay 404,
   their POSTs stay the authenticated pre-handler 204 no-op, and
   sign-out remains the sole CSRF-checked mutation exception.
2. **Browser-cache privacy fix**: one central, demo-only, ASGI
   response-start guard makes EVERY dynamic `/admin` response the
   demo process emit - admitted pages, JSON, handler error pages,
   the zero-account 404, no-ops and redirects - carry exactly one
   `Cache-Control: private, no-store` header (any pre-existing
   cache-control header is replaced, never duplicated). The
   revisioned `/admin/static` passthrough deliberately bypasses
   the guard and keeps its own cache policy; the ordinary app
   never runs behind it. Scope: this prevents NORMAL HTTP
   caching and every dynamic reload rechecks authorization; no
   absolute browser history or back-forward-cache erasure is
   claimed.
3. **Demo nav** now lists exactly the twelve admitted sections
   (Dashboard, Keys, Owners, Institutions, Cohorts, Providers,
   Pricing, Templates, FX, Usage, Audit, Email); normal nav and
   rendering unchanged. In DEMO mode only, the new pages hide
   links to still-gated forms, edit/export, network-discovery
   (discover models, SMTP test, diagnostics lookup) and file-backed
   routes (routes rows render as plain text), with no orphan
   separators or empty action panels; visible operational POST
   buttons remain quiet no-ops. A small shared template helper
   (`rows_shown_label`) fixes the pre-existing singular/plural
   list-count grammar (`1 row shown` / `N rows shown`) on all ten
   admitted list pages that use the counter - GUI polish, no data
   or accounting change; the still-gated routes list page is left
   for the suffix that admits it.

No new settings, no schema change (0028 unchanged), no new CLI
commands, no changes to `main.py`, `demo_web.py` core control/copy
roles, `db/session.py`, normal admin auth/session, 221/222/223
masking/worker, provider adapters, quota/accounting or
Compose/Nginx.

## 2. e-head hosted CI (the order's open item)

Run `43420051376` at e-head `c1494f28` COMPLETED SUCCESS with all
six jobs green: Playwright browser smoke, PostgreSQL integration
tests, Unit/lint/migration head, Docker Compose smoke,
OpenAI-compatible E2E, Documentation hygiene. No demonstrated
direct defect; nothing was repaired from CI.

## 3. Evidence

### 3.1 Focused unit (mocked; `tests/unit/test_demo_web.py`)

93 tests, exit 0. New/updated coverage: the closed admission sets
including all seven new families (admitted vs default-denied);
the canonical-UUID detail law across all eleven detail prefixes
with near-misses (action GETs `/edit`/`/discover`, extra suffix,
uppercase/no-dash/urn/braced variants); the no-store guard on
successful admitted HTML, admitted JSON, handler-level 404
error pages, the zero-account 404, the login redirect and the
uniform 204 no-op; the static passthrough retaining its own cache
policy (no no-store injected); the twelve-section demo nav; and
the existing refusal/preflight/logout law (header values
normalized to `private, no-store` where the guard applies; the
`/fakeadmin/copy-preview` route keeps its own `no-store`).

### 3.2 Ordinary-main regression (unchanged behavior)

`test_admin_records_routes.py`,
`test_admin_record_actions_routes.py`, `test_db_session.py`,
`test_admin_csrf.py`, `test_admin_record_choices.py` - 102 tests,
exit 0 (real `main.create_app` path through
`_admin_page_context` and the normal sessionmaker branch). The
194 rows-selector inventory test was updated to accept the
pluralization helper over the same `|length` interpolation
(5/5 pass); all 122 templates compile through the app env;
`test_documentation_inventory.py` 16/16 pass after the doc
edits.

### 3.3 Owned PostgreSQL 16 (real;
`tests/integration/test_demo_web_admin_gate_postgres.py`)

2 tests, exit 0, on the owned live PG16 pair (owner-labeled
containers; web/worker/reader roles; synthetic data only).

- `test_e2e_admin_gate_two_sessions_distinct_copies`: two
  concurrent sessions still read two DISTINCT verified copies
  (extra institution row proven in the copy DB and rendered
  list; raw source marker absent from both pages). EVERY admitted
  list and detail now renders from its own copy behind the real
  SELECT-only reader role - the four core families plus all seven
  new families (11 list pages, 11 UUID detail pages,
  record-choices). Real identity/secret canaries are absent from
  the pages while the 222-fictionalized identities are the ones
  shown; the rendered usage ROW COUNT equals the copied
  `usage_ledger` table count (the token/cost quantities
  themselves are 222's verified masking contract, not
  re-verified by this round). Still-gated paths (routes,
  operations, reports, provider edit, usage export) stay 404
  under the same live session. Every admitted response carries
  `private, no-store`. Source and both copies remain
  count-invariant across the whole phase (count set extended to
  the new tables); the exact marker finalizer is retained.
- `test_browser_smoke_demo_copy_pages`: real Chromium over
  loopback uvicorn on a real verified copy: packaged CSS/JS load
  200; the demo banner renders and the nav is exactly the twelve
  admitted sections; a NEW section (`/admin/providers`) renders
  with `private, no-store`, its gated create-form link hidden and
  its packaged table-sort working (aria-sort ascending); the
  existing institutions sort and CSRF sign-out still pass; and a
  FRESH RELOAD of the dynamic page after sign-out is answered by
  a reauthorization bounce (`private, no-store`) ending at the
  demo login instead of a cached snapshot - history/BFCache
  erasure is not claimed. The synthetic `/admin/keys` screenshot
  is saved to a run-owned `/tmp` path (never committed; path
  printed to local test stdout only, never ordinary application
  logs).

### 3.4 Hygiene

Scoped Ruff (repo policy pin E4/E7/E9/F) clean on all touched
Python files; `git diff --check` clean.

## 4. Honest limitations

- Still-gated for the next suffixes (224-g/h): routes,
  operations, catalog refresh, compatibility, OpenAI-assisted,
  accounting-recovery, replay maintenance, admin accounts, key
  batch, key clone, all unreviewed form GETs, exports/downloads,
  `/admin/branding`, and the file-backed display panels. The demo
  remains an incomplete preview and is NOT usable for company
  demonstrations.
- The no-store guard prevents normal HTTP caching of dynamic
  `/admin` responses; it does not guarantee erasure from browser
  history or the back-forward cache.
- Copy-reader transport remains an explicit `ssl=False` no-TLS
  stage boundary (trusted private network only); no verified TLS
  guarantee.
- The demo web entry remains DEFAULT OFF in a standalone process.
- 224-e evidence wording: the immutable 224-e report is preserved
  unchanged; `docs/demo-admin.md` now states the precise
  evidence - the unit test samples representative unsafe paths
  (ten cases) and the uniform `DemoAdminGate.__call__` branch
  structurally cuts all authenticated unsafe `/admin` methods
  before inner-app dispatch.

## 5. Protected untracked files

Hash-only verification (never read/staged/modified), unchanged:

- `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
- `codex.sh`
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
- `uv.lock`
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`

## 6. Protocol state

- Root-authored order/active committed unchanged; one
  implementation commit + this report-only SELF; no merge, no
  auto-merge, no release, no deployment, no company snapshot, no
  provider or mail call.
- Immutable 224-a/b/c/d/e orders and reports untouched.
- Objective 225 stays inert. Root independently reviews the
  final-head CI and the same PR continues with 224-g/h for the
  remaining form/file-backed panels and installed browser
  acceptance.
