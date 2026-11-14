# OAP Work Order — 224-c

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383, branch
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. This is the third
same-PR suffix. Do not create another PR, merge, enable auto-merge,
release, deploy, or use real company data. The human authorized the
complete live fake-admin demo: a new snapshot after each successful
login with a wait page; plausible fictional identities while real
usage patterns remain; CLI-only fake-admin credentials; all admin
GUI operational actions silent no-op; fresh disposable database and
file-backed copy; logout/expiry cleanup. This suffix adds ONLY the
separate demo entry/login/wait/session/logout surface and the narrowly
listed corrections below. Later suffixes on THIS PR supply copy-backed
admin browsing, sanitized file panels, server-enforced no-op actions,
installed wiring/browser evidence and final delivery. Do not claim
the demo is usable for company demonstrations at the end of 224-c.

## Verified state, immutable predecessor, and required correction

224-b response was EXACT `OK`; root FIFO response terminal 70036 is
CLOSED exit 0 and MUST NOT be repolled. Remote PR383 head is 224-b
report-only SELF `d6bd6984d0c2c5d248f21877b94317b4d9c3cda8`,
sole parent implementation `f86a744b3c7c906933b4f3953162e232a99d7ed1`,
sole diff `oap/reports/224-b-exact-worker-handoff-and-cleanup.md`,
SHA256 `e1b6ca9ce63d1c9fbc60d13189cb41468145a041d2de234cbf71739af3bf91ba`.
The immutable 224-b order SHA256 is
`a3523919d930e9a286b1203306cf6d2cfc5ffa942d3487b0240a90d4b060ae5d`;
`oap/active` is exact `224-b` (5 bytes) before this activation. Remote
main is still `d3762e51`; PR383 is OPEN and mergeable, no merge. Other
open PRs #379 and #319 are unrelated. Protected untracked
`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` retain respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean, or stash them. Root writes
this order and `oap/active=224-c` in the shared checkout BEFORE one
control FIFO `OK`; the existing right-pane coding agent owns Git.
Use no helper agents or model/profile changes.

The intermediate 224-b exact-SELF CI Unit job FAILED two focused tests:
`tests/unit/test_demo_web_worker.py::test_process_request_leaf_inode_drift_refuses_publication`
is flaky because unlink/rewrite may reuse the inode on CI; make the
old inode remain allocated during replacement (e.g. hold an open fd)
so the negative is deterministic. `tests/unit/test_oap_governance.py::
test_active_identifier_resolves_exactly_one_matching_order` rejects
224-b's root-authored heading with a colon. Activated orders and reports
are immutable: NEVER edit the 224-b order. The first line of THIS order
is intentionally the exact required heading and activating 224-c must
make the current-active governance check pass. Two unresolved Code
Quality threads on PR383 flag `tests/unit/test_demo_web_control.py`
line ~648's unused `verified` and line ~834's no-effect state expression;
fix them narrowly (the latter should assert state remained `bogus`),
preserve test meaning, and tell root; root owns resolving review threads.
The other intermediate checks were green or pending at reconciliation;
inspect the actual 224-b-head PostgreSQL/browser completions and fix a
demonstrated directly affected failure in this SAME PR before report.

The 224-b report is an immutable claim, not authority. Its cap example
is factually wrong: with max 4, three verified + one evictable raw copy,
`run_snapshot_job` evicts the raw copy and may admit a new copy at four
(the focused test proves this); it refuses only if the fourth copy is
not evictable. The report also says the worker-derived
`protected_job_ids` protects in-flight UNVERIFIED copies, but its SQL
selects only `verified_unpublished` control rows, whose copies are
already structurally excluded from generic expiry. Correct the
operator docs/current behavior and explicitly correct these claims in
the 224-c report. Do not edit the 224-b report. Keep the actual
verified-copy non-eviction law. Review whether this redundant protected
set/query can be removed within these exact paths without weakening
any reachable protection; if it is dead machinery, remove it with
focused tests rather than carrying a misleading guarantee. Also count
surviving `CLEANUP_FAILED` custody/target artifacts against finite
copy admission, or prove they are independently bounded: repeated
failed cleanup must not allow unbounded new copies. Keep this correction
small; no new migration or generalized retention framework.

## 224-c: isolated demo entry, not normal admin

1. Add one optional, purpose-built ASGI demo web entrypoint (e.g.
   `slaif_gateway.demo_web:create_demo_app`) with a SMALL independent
   configuration object: default OFF; dedicated demo WEB control-role
   connection settings and independent cookie-signing secret; no
   owner `DATABASE_URL`, production admin secret, source export/target
   admin credential, provider credential, Redis broker, worker custody
   directory, catalog seal key or other operator-owned source file.
   Do not call/import `main.create_app` or its lifespan; it bootstraps
   provider modules, normal routes and normal database/Redis services.
   The demo app registers only the exact `/fakeadmin` entry routes and
   packaged static assets it needs. `/v1`, `/admin`, ordinary
   `/admin/login`, normal API keys and provider forwarding remain
   unreachable on this demo process. No route is added to the normal
   production app in this suffix. Web control DB role gets only the
   reviewed 224-a column grants; its URL/engine must be distinct from
   the 224-b worker control URL/credentials. No implicit role creation.
2. GET `/fakeadmin/login` renders a visually consistent **Demo Admin
   Login** page. State plainly that after login a fresh snapshot is
   taken and identities are fictionalized while usage patterns remain;
   show a wait indication. POST verifies username/password against a
   column-scoped account lookup under the WEB role using the existing
   Argon2id verifier, never loading the full ORM row (timestamps are
   not granted). Use a purpose-specific CSRF token and dedicated
   signed HttpOnly/SameSite/Secure cookie boundary; never reuse normal
   admin cookies/secrets. Constant safe error text prevents username
   enumeration; no credential, hash, token, prompt or raw request in
   logs, URL, page, or response body. Set finite field/body limits and
   login-attempt bounds appropriate for the single demo process; do
   not require normal audit/Redis/business-table grants. On valid
   credentials create ONE fresh pending 224-a request bound to live
   account/generation. Two successful logins create distinct requests
   and later distinct snapshots. Zero enabled fake-admin accounts:
   GET/POST login and all demo pages return 404, not a credential
   oracle; disabling the last account takes effect on later checks.
3. GET `/fakeadmin/wait` and a small poll/status endpoint use a
   short-lived, integrity-protected pending cookie bound to the exact
   account/request/generation; direct URL/body guessing must not reveal
   another request. Recheck live account/generation, zero-active gate,
   request ownership/state/deadline on EVERY poll. Show only safe
   finite states and a finite timeout/failure message; no job ID,
   target DB/custody path, manifest, password or internal exception.
   A pending request must never yield an authenticated admin session.
   Only after the exact worker-verified state is reached may the web
   role invoke 224-a `create_session`; store the raw opaque token only
   in a separate HttpOnly/Secure/SameSite demo session cookie, with
   its hash alone in PostgreSQL. Recheck the database session on every
   subsequent demo page. A successful wait may land on a simple
   `/fakeadmin/ready` page in this suffix; it must visibly say that
   full copy-backed browsing is not enabled yet and must not expose
   normal admin routes. POST logout revokes the exact session,
   clears both demo cookies and makes subsequent use fail; the
   224-b worker cleanup command then removes its copy. No silent
   no-op behavior applies to logout.
4. The web request must NEVER spawn or import the privileged snapshot
   worker. The 224-b `process-request REQUEST_ID` CLI remains the
   private separate-process handoff for this stage; tests may drive
   it against a pending request. If a bounded worker `work-once`
   selector is necessary to make the eventual wait workflow automatic,
   keep it a separate worker-only CLI path using the existing atomic
   claim and exact job pipeline, and report its deployment/wiring
   limitation honestly. Do not add a general queue, Celery/Redis
   dependency, background job framework, schema, or in-process
   worker. Installed automatic scheduling and host proxy are later
   224 suffix work.

## Scope, evidence, and publication

Expected product paths: new narrow `app/slaif_gateway/demo_web.py`,
`app/slaif_gateway/api/fake_admin.py` and purpose-specific demo
auth/cookie helper if necessary; a column-scoped login projection in
`db/repositories/fake_admin_accounts.py`; small `services/demo_web_control.py`
query/projection additions if needed; `services/demo_snapshot.py` and
`services/demo_web_worker.py` only for the finite-cap/dead-protection
correction described above; `config.py` only if the independent demo
config cannot be kept separate; new packaged demo login/wait/ready
templates and minimal CSS reuse. The normal `main.py`, ordinary admin
routers/auth/session, provider adapters, quotas/accounting, migrations,
Compose/Nginx and existing branding source handling remain untouched
in this suffix. Expected tests: purpose-built unit and owned-PG16
web/control integration plus the exact CI/review test fixes above.
Direct `docs/demo-admin.md`, `docs/configuration.md`, `docs/cli-reference.md`
and schema contract only if directly affected; no new documentation
framework. Tell root before an unavoidable new path or authority
expansion; routine fixture/doc corrections remain in this order/PR.

Acceptance: default-off/zero-account 404; valid and invalid login,
CSRF/cookie tamper/expiry, non-enumerating safe errors, no raw secret
echo; a valid login creates a fresh request; pending/wait cannot
access another request or issue a session; worker failure/expiry
renders safe finite status; exact verified worker result issues one
session only and its database gates are checked on every use;
disable/reset/last-account removal denies immediately; logout revokes
and later cleanup is exact. Test direct `/admin` and `/v1` denial on
the demo app, absence of worker/source/provider credentials/Redis from
the demo app, and real web-role 42501 refusal of business tables and
worker-owned verification fields. Add deterministic negative for the
old-inode replacement, current-active governance heading, and the two
Code Quality test hygiene items. Verify cleanup-failed artifacts
consume capacity. Use synthetic owned data only. Run focused unit,
owned-PG16 and web-client tests, scoped Ruff/docs/diff; no full local
unchanged provider/Codex matrices. Browser evidence is required when
the full GUI is wired in later suffixes, not claimed here. Skips and
mocked coverage must be labelled honestly.

Commit the already root-authored order/active bytes unchanged on
the existing PR branch. Push implementation, then publish ONE
immutable `oap/reports/224-c-demo-entry-and-wait.md` report-only SELF
(sole parent implementation, sole diff report); verify PR383 remote
head, branch/base, order/active/report and protected hashes. Report
the corrected 224-b claims, exact tests and limitations. Then send
one exact response FIFO `OK` and rearm one canonical control waiter.
Never merge or claim the full demo available; root owns final-head
CI/review/merge only after later 224 suffixes complete.
