# OAP Report — 224-e Demo admin core read gate

- Order: `oap/orders/224-e-demo-admin-core-read-gate.md`
- Order SHA256: `63b80bf59d663ad32f569913e987313ccca0ef7565e3230eb7523291d4736085`
- `oap/active`: `224-e`
- PR: #383 `oap/224-demo-web` (AMEND_EXISTING_PR), base remote main
  `d3762e51c9a323dee6b728c4a45fa21b0bffae86`
- Prior remote head: `05db7090ebeee2049a86780df922d6f5d7ec83cb`
  (224-d report-only SELF)
- Implementation commit (sole parent of this report):
  `f4b55b8b17434036bfa58d224e22f350fc1ff5e5`
- This commit: report-only SELF; sole diff vs the implementation
  commit is this report file.

## 1. What 224-e implements

Bounded first stage of copy-backed admin GUI browsing, in the
standalone `create_demo_app` process ONLY (`main.py`, normal auth,
quota/accounting, providers, 221/222/223 vocabularies, migration 0028,
copy-worker grants, Compose/Nginx all unchanged; no new settings, no
new CLI commands):

1. **Mount**: the 14 existing admin router modules are mounted only in
   the demo process (same fixed order as the ordinary app), served
   with packaged `/admin/static` assets and fixed neutral branding
   (no live branding directory or catalog file). A persistent demo
   banner (identity-masked snapshot, read-only, actions have no
   effect, incomplete core preview) is added to admitted pages in
   demo mode only.
2. **Central default-deny gate** (`api/demo_admin_gate.py`, an ASGI
   wrapper) evaluated BEFORE admin handlers and before form/body
   parsing: zero active fake-admin accounts -> every `/admin` path
   404; `GET /admin/login` -> 303 `/fakeadmin/login` (real login POST
   never dispatched); admitted GETs are exactly dashboard `/admin`
   (and trailing slash), the four core lists, record detail pages
   whose single path component is exactly one canonical lowercase
   `8-4-4-4-12` UUID (uppercase/no-dash/`urn:`/braced forms refused),
   and `GET /admin/record-choices`; every other admin GET is 404.
3. **Unsafe methods**: every POST/PUT/PATCH/DELETE on any `/admin`
   path - known or unknown - is a pre-handler quiet 204 no-content;
   the body is never parsed; no fake success, no audit/accounting/
   mail/provider/custody effect. The ONE exception is demo sign-out:
   `POST /admin/logout` parses a bounded form, verifies the
   page-issued CSRF token with a constant-time compare, revokes
   through the 224-c control service, and clears cookies/redirects
   ONLY on confirmed revocation (or absent session); failed or
   unconfirmed revocation is a safe 400 retry refusal that keeps the
   session valid. The production admin logout service is never
   called.
4. **Per-request binding**: on each admitted read the session is
   revalidated against live account/generation/request state; the
   exact request must be `verified_unpublished`, unexpired, with id
   AND account matching; the closed `demo_snap_<20hex>` target name
   is required; a REQUEST-LOCAL sessionmaker is created under the
   224-d reader credential (NullPool, bounded timeouts, explicit
   `ssl=False` no-TLS stage boundary - trusted private network only,
   no verified TLS guarantee); a preflight verifies
   `current_database()` equals the bound name AND
   `transaction_read_only` is `on`; the engine is disposed after the
   response and on every refusal path. `db/session.py` branches
   FIRST on a fixed `demo_mode` app marker: demo requests use only
   the validated `request.state` factory (fail-closed if absent) and
   the app-global factory is never consulted. Missing/expired/
   revoked/cleanup-racing copies return a fixed safe no-store
   refusal - no DSN, copy name or traceback; no source fallback.
5. **Demo-only display identity**: fixed fictional administrator
   ("Demo Administrator", `demo-admin@example.invalid`,
   deterministic uuid5 placeholders) and a non-authoritative form
   token, without reading/mutating copied `admin_sessions` or the
   normal `AdminSessionService`; the dashboard's direct
   normal-session path has an equally guarded demo branch. Normal
   production behavior is unchanged (regression-verified); in
   normal mode the base template differs by one whitespace-only
   line. Demo mode hides unimplemented action links with honest
   read-only hints and shows exactly five nav sections.

Order-required Code Quality fixes carried in this WIP: the two
d-head threads (unused `Callable` import and lambda-wrapped
`CopyReader` factory in `demo_web.py`) are fixed idiomatically
(module-level `_default_copy_reader_factory` with a real
`Callable[[DemoWebConfig, str], CopyReader]` annotation). Final
scoped Ruff additionally flagged two F821 string annotations, fixed
with a `TYPE_CHECKING` import block (no runtime import cycle).

## 2. Evidence

### 2.1 Focused unit (mocked; `tests/unit/test_demo_web.py`)

91 tests, exit 0 (rerun after the final annotation cleanup). Covers:
mounted route-table enumeration (all `/admin`-only, admitted set
present, no `/v1` at top level); closed admission sets (admitted vs
404 vs 303); canonical-UUID-only detail law; zero-active-account
404s; login redirect; binding refusals (unbound/pending/bad-name/
expired) with no DSN/copy-name leak; preflight wrong-database and
read-only-off dispose-and-refuse (engine disposed asserted); unsafe
no-session 404 with an oversized garbage body never parsed;
operational families and unknown paths -> 204 with no unsafe handler
dispatching across the entire mounted route table; logout
confirmed-revoke 303 + all three cookies cleared, failed revoke
(RuntimeError) -> 400 with the session still live, unconfirmed CAS ->
400; CSRF mismatch/missing -> 400 with zero revocations; static
passthrough; ambient-environment-free display settings
(`Settings.model_construct`, `DATABASE_URL` absent, no ambient env
read); base-template normal render (full nav, no banner) vs demo
variant (banner, five-link nav); and the d-head Code Quality
behaviors. The broader nine-file focused demo unit suite was green
at the gate/template behavior; those files are unchanged since.

### 2.2 Ordinary-main admin regression (unchanged behavior)

Focused, not broad: `test_admin_records_routes.py`,
`test_admin_record_actions_routes.py`, `test_db_session.py`,
`test_admin_csrf.py`, `test_admin_record_choices.py` - 102 tests,
exit 0. This exercises the real `main.create_app` ordinary admin
login/page GET/POST path through `_admin_page_context`, the
`get_sessionmaker_from_app` normal branch, and record-choices
behavior.

### 2.3 Owned PostgreSQL 16 (real;
`tests/integration/test_demo_web_admin_gate_postgres.py`)

Run against the owned live PG16 pair (owner-labeled containers,
exact-ID discipline; web/worker/reader roles, synthetic data only).

- `test_e2e_admin_gate_two_sessions_distinct_copies` - pass
  (15.67 s). Two concurrent logins -> two DISTINCT 224-a requests;
  both processed by the real 224-b worker CLI (real worker role,
  real 221/222/223 chain). Distinct-copy proof at TWO levels: the
  second copy's database holds exactly one more institution than the
  first (a marker row inserted into the SOURCE between the two
  dumps, fictionalized by 222's institution-name law), and session
  B's rendered institutions list shows exactly one more row than
  session A's (rows-shown counter). Privacy canary: the RAW source
  marker name appears in NEITHER rendered page. Every admitted GET
  family renders 200 behind the real SELECT-only reader role
  (dashboard, four lists, key/owner/institution/cohort UUID details,
  record-choices institution+owner). Seven POST paths in total (six operational create/revoke/
  rotate paths plus one unknown path) return 204 with empty bodies
  (200 KB garbage body, never parsed). CSRF-verified sign-out revokes session A
  (303 to the demo entry, cookie cleared, next GET bounces); a wrong
  CSRF on session B is a 400 with B still serving. Source and BOTH
  copies are count-invariant across the whole phase (the marker is
  verified exactly once in the source after the read phase); the
  exact marker finalizer, registered immediately after the insert,
  removes that one source row on any later failure.
- `test_browser_smoke_demo_copy_pages` - pass (12.87 s). Real
  Chromium over loopback uvicorn on a real verified copy: packaged
  CSS and JS load 200 (judged by URL path - `asset_url` appends
  `?v=<digest>`); the demo banner renders; the nav is exactly
  Dashboard/Keys/Owners/Institutions/Cohorts with the unreviewed
  sections absent; table sorting works via the packaged
  `table-sort.js` (aria-sort ascending/descending, rows reorder);
  no copy DB name or reader-role name in the HTML; CSRF sign-out
  clears the session cookie and returns to the demo login. One
  screenshot of the synthetic `/admin/keys` page was saved to the
  run-owned path `/tmp/slaif-224e-browser-492673-426d04f7f0.png`
  (synthetic data only; never committed; its path is printed to
  local test stdout only and never appears in ordinary application
  logs).

### 2.4 d-head hosted CI (context for the order's open item)

The order asked for the terminal result of the in-progress d-head
PostgreSQL integration check. Verified: GitHub run
`43399221609` at head `05db7090` (2026-11-13T09:11Z, 16m38s)
COMPLETED SUCCESS with all six jobs green: Playwright browser
smoke, PostgreSQL integration tests, Unit/lint/migration head,
Docker Compose smoke, OpenAI-compatible E2E tests, Documentation
hygiene. No demonstrated direct defect; nothing repaired from CI.

### 2.5 Hygiene

Scoped Ruff (repo policy pin E4/E7/E9/F) clean on all seven touched
Python files; `git diff --check` clean;
`tests/unit/test_documentation_inventory.py` 16/16 pass after the
doc edits.

## 3. Honest limitations (partial coverage, by design)

- This suffix is an INCOMPLETE CORE PREVIEW. Admitted: dashboard,
  four core lists, their UUID detail families, record-choices,
  `/admin/static`, login-GET redirect. Every remaining admin
  family - providers, routes, pricing, usage, operations, audit,
  email, catalog refresh, accounts, key batch, key clone,
  compatibility, replay maintenance, reports - plus the file-backed
  display panels stays default-denied 404 behind the gate until a
  later same-PR suffix reviews it; the order already assigns the
  remaining families and installed browser acceptance to that
  suffix. The demo is NOT usable for company demonstrations.
- The demo web entry remains DEFAULT OFF and is a standalone
  process; nothing in the ordinary gateway process changed.
- Transport: the copy-reader connection uses an explicit
  `ssl=False` stage boundary (trusted private network only). There
  is NO verified TLS guarantee on this path.
- The two snapshot times (221 DB dump vs later 223 file capture)
  are not transactionally simultaneous; this remains documented in
  `docs/demo-admin.md` (223 section) and unchanged.
- The Chromium smoke is local owned-infrastructure evidence in this
  report; hosted CI's browser job continues to cover the normal
  GUI on the final head.

## 4. Documentation

- `docs/demo-admin.md`: new "Demo admin core read gate (objective
  224-e)" section - gate law, per-request binding, display identity
  and demo-only GUI treatment, evidence, and the explicit
  partial-coverage/next-suffix status.
- `docs/configuration.md`: "Demo admin core read gate (objective
  224-e)" subsection stating NO new settings; behavior described
  against the existing `DEMO_WEB_COPY_*` reader connection.

## 5. Protected untracked files

Hash-only verification (never read/staged/modified), unchanged:

- `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
- `codex.sh`
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
- `uv.lock`
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`

## 6. Protocol state

- One implementation commit + this report-only SELF; no merge, no
  auto-merge, no release, no deployment, no company snapshot, no
  provider or mail call.
- Immutable 224-a/b/c/d orders and reports untouched.
- Objective 225 stays inert. Root independently reviews the
  final-head CI and the same PR continues with the next same-PR
  suffix for the remaining families.
