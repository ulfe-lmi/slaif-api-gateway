# OAP Work Order — 224-e

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383,
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. No second PR,
merge, auto-merge, release, deployment, production/company snapshot,
provider call or mail. The human authorized a live fake-admin demo:
fresh per-login identity-masked database AND file-backed snapshot,
the existing admin GUI, read-only browsing, every operational action
silent no-op, and disposable exact-copy cleanup. This suffix makes a
bounded first set of EXISTING database-backed admin pages browse the
224-d verified per-session copy behind a default-deny server-side
gate. It does NOT claim full GUI coverage: the next same-PR suffix
must address the remaining DB/file-backed panels and installed
browser acceptance before objective 224 can merge. Keep the demo
default off and isolated from the ordinary gateway process.

## Current GitHub/OAP state and direct review findings

224-d response was exact `OK`; root FIFO terminal 96952 is CLOSED
exit 0 and MUST NOT be repolled. Remote PR383 head is 224-d
report-only SELF `05db7090ebeee2049a86780df922d6f5d7ec83cb`, sole
parent implementation `155851d0c20a3003b07e6f2562517094ea781835`,
sole diff `oap/reports/224-d-verified-copy-reader.md` SHA256
`09abc81613d25ad3c30a9bbb4887ea162a8a67a40d820e0698f48e394904dc60`.
Immutable 224-d order SHA256 is
`a8c196742f85de4ffa748af58d81d334a1b6da5240e600d89baa113cdae1fe1b`;
`oap/active` is exact `224-d` before this activation. Remote main
remains `d3762e51`; PR383 is OPEN, mergeable, not ready for merge.
Other open PRs #379/#319 are unrelated. Root verified 500 focused
unit tests and owned PostgreSQL16 224-d/224-b/224-c modules
(3+11+3 tests), scoped Ruff/diff clean, protected untracked hashes
unchanged. Exact 224-d hosted CI is IN PROGRESS: Unit, browser,
E2E, Compose, documentation and CodeQL checks are SUCCESS;
PostgreSQL integration is still pending. Inspect its terminal
result and repair only a demonstrated direct defect on
this same PR. Root resolved the five fixed c-head test-hygiene
threads and three new d-head Code Quality false positives on
canonical `DemoWebFacade(Protocol)` ellipsis bodies. Two d-head
Code Quality threads remain: `demo_web.py` unused `Callable` import
and unnecessary `lambda` around `CopyReader` factory. Fix those
idiomatically without changing factory behavior; root resolves the
threads after verifying the next head. No activated order or report
may be edited.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`
retain respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root writes
this order and exact `oap/active=224-e` under the shared checkout
BEFORE one control `OK`. The existing right-pane coding agent owns
Git; no helper agent or model/profile change.

## Verified route/architecture inventory for this bounded stage

The ordinary `main.py` includes 14 admin router modules; the current
source has 94 GET and 96 POST handlers. `api/admin.py` itself has
53 GET/56 POST. Its dashboard GET directly validates and refreshes
a REAL admin session; most other page GETs use
`_admin_page_context`, which also refreshes CSRF in the ordinary
database. `db/session.py:get_sessionmaker_from_app` presently reads
an app-global factory. Those paths CANNOT be reused in the demo
unchanged: the copy role has SELECT-only grants, sessions are in the
separate `demo_control` schema, and two visitors must never share an
app-global copy connection. Existing shared admin templates use
`/admin/static` packaged CSS/JS, absolute `/admin/...` links,
`/admin/logout` POST forms, and the existing list/record-choice
controls. The normal branding context reads `SLAIF_BRANDING_DIR`;
until the next suffix binds the verified file display tree, this
suffix may use ONLY the packaged neutral branding, never a live
operator branding path or catalog file. A safe display settings
object may be constructed from fixed model defaults WITHOUT
reading ambient `get_settings()`/production env; it must not
contain source DB, worker, Redis or provider credentials.

## 224-e requirements

1. Mount the existing admin router/template implementation ONLY in
   the standalone `create_demo_app` process. Never add `/fakeadmin`
   to ordinary `main.create_app`, never call the ordinary app factory,
   and never mount `/v1`, provider, mail or worker routes. Serve the
   bundled `/admin/static` assets from the package without accessing
   a live branding directory. Add a clear persistent demo banner to
   the reused admin pages: identity-masked snapshot, read-only,
   operational actions have no effect; this round is an incomplete
   core preview. Preserve the current admin visual style, sorting,
   filters, dropdowns, row ordinals, typography and accessibility.
   Ordinary admin pages must render exactly as before when not in
   demo mode.
2. Implement a CENTRAL, server-side, default-deny demo-host gate
   BEFORE admin handlers or form/body parsing. The only admin GET
   routes admitted this suffix are: dashboard `/admin` (and its
   harmless trailing slash), list pages `/admin/keys`, `/admin/owners`,
   `/admin/institutions`, `/admin/cohorts`, their existing record
   detail pages with a closed UUID path component, and the GET
   `/admin/record-choices` lookup needed by their existing filters.
   The current static assets are separately allowed. Real
   `/admin/login` GET redirects to `/fakeadmin/login`; the real login
   POST is never dispatched. Every other admin GET stays unavailable
   (404) until explicitly reviewed in a later suffix. The demo nav
   should show only this stage's usable sections so clicking a tab
   does not lead to a dead end. Hide unimplemented action-navigation
   links on these selected pages in DEMO mode with a brief, honest
   read-only hint; leave their normal-GUI rendering unchanged. Do
   not silently route a blocked page to the live gateway.
3. Every unsafe method on `/admin` (POST/PUT/PATCH/DELETE etc.),
   including direct requests to known create/revoke/reset/apply
   handlers, must be cut off BEFORE the handler and return a quiet
   no-content/no-change response for an authenticated demo session.
   Unknown unsafe admin paths stay default-denied; no fake success
   page or audit/accounting/mail/provider/custody effect. The ONE
   explicit exception is demo sign-out: existing `/admin/logout`
   forms must revoke the demo session through the 224-c control
   service with CSRF verification, clear its cookie, and return to
   the demo login/ready flow; they must NEVER call the production
   admin logout service. No active fake-admin account means all
   demo/admin paths 404. A missing/expired/revoked/disabled session
   may redirect to `/fakeadmin/login`, but may not reach a copied
   business table or a no-op success. Keep any browser GET action
   links in the allowed pages from reaching unreviewed handlers;
   hide them with an honest demo hint, while preserving the real GUI
   unchanged. Existing operational POST buttons visible on an
   admitted page remain quiet no-ops, never false success.
4. On EACH admitted admin read, validate the 224-a session against
   live fake-admin account/generation/request state, require its
   exact verified/unexpired `demo_snap_<20hex>` binding, then create
   a REQUEST-LOCAL target-copy sessionmaker under the 224-d reader
   credential. Never assign a per-visitor factory to global
   `app.state`; adapt `get_sessionmaker_from_app(request)` narrowly
   so demo requests use a validated `request.state` factory and
   fail closed if absent. Use a bounded, no-idle-pool connection and
   database-side read-only mode for every copied transaction; verify
   `current_database()` equals the bound name before a handler can
   query. Dispose after the response is finished. Normal app
   sessionmaker behavior remains unchanged. Concurrent visitors
   must read distinct copies. A revoked/missing/cleanup-racing copy
   returns a safe no-store refusal, never a DSN/copy name/error
   traceback or a fallback to the source database.
5. Adapt the minimal shared admin authentication helpers for DEMO
   requests only: pages get a fixed fictional administrator display
   identity and non-authoritative form token without reading or
   mutating copied `admin_sessions` or normal `AdminSessionService`.
   The dashboard's direct normal-session path needs an equally
   guarded demo branch. The normal production branch is unchanged.
   No fake account password/hash/token/copy locator appears in
   templates, logs or response URLs. The selected pages must query
   ONLY copied `public` rows. Existing GET filtering, sorting,
   paging and record-choice search should work; no new CRUD
   service or duplicate table UI.

## Scope, evidence, publication

Expected product paths: `demo_web.py` and `api/fake_admin.py` for
the standalone gate/binding; narrow guarded changes to
`db/session.py` and `api/admin.py` (and `api/admin_record_choices.py`
only if its distinct auth helper needs a demo branch);
`web/templates/base.html` and the selected core list/detail templates
only for demo-only banner/nav/action-link treatment;
one small purpose-built demo-admin bridge module if needed;
`docs/demo-admin.md` and `docs/configuration.md`; focused unit,
owned-PG16 integration and browser/HTML checks. Do NOT change
`main.py`, normal auth/session/permissions, migration 0028,
221/222/223 sanitizer policy, copy-worker grants, provider adapters,
quota/accounting, Compose/Nginx or production routes. The two
Code Quality fixes above stay in scope. Tell root before an
unavoidable path expansion; routine direct fixture/doc corrections
stay in this same order/PR.

Verification: exercise all admitted GETs on an owned synthetic copy
with the real reader role and existing templates; prove real source
tables/counts unchanged. Exercise two concurrent demo sessions with
distinct copied rows and verify no cross-copy/app-global leakage.
Enumerate the mounted demo route table and prove `/v1`/ordinary
admin login and all unreviewed GETs are absent/gated. Direct POST
every major operational family represented by the admitted pages
(key create/revoke/rotate, owner/institution/cohort create/edit,
and an unknown path), assert quiet no-op and zero copied/source
DML, audit, quota, mail, provider or file effects; prove body is
not parsed before the gate. Test zero-account, absent/revoked/
disabled/expired session, wrong/missing copy, CSRF-protected demo
logout, no-store and credential/locator canaries. Test the ordinary
`main` admin login/page POST behavior has not changed (focused
regression, no broad local suite). Include an actual HTML/browser
smoke for packaged CSS/JS, banner/nav, sorting and logout where
the environment supports it; report skips honestly. No live
company data or provider/mail calls. Scoped Ruff/docs/diff; root
will review hosted final-head CI. Document this suffix as partial
coverage and list the remaining admin/file-backed families for the
next order, without claiming the demo is ready for companies.

Commit root-authored order/active unchanged on the existing PR
branch, push implementation, then publish ONE immutable
`oap/reports/224-e-demo-admin-core-read-gate.md` report-only SELF
(sole parent implementation, sole diff report). Verify remote PR383
head/branch/base, order/active/report, protected hashes; send one
exact response FIFO `OK` and rearm one canonical control waiter.
Coding agent never merges; root independently reviews and continues
same PR. Objective 225 stays inert and no demo deployment/release
is authorized.
