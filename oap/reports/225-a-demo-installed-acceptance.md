# OAP 225-a — Final Report (installed acceptance for the isolated fake-admin demo)

## Commit topology

- Activation commit: `443ab0d5d8976201298e676237cd4e5175796b2b`
  (tree `6b590b338c3a25735a5a41953fad562e5e0c38a6`, sole parent
  `b593e5e96484dd9979dfe2960e0a7fbbc57c8301`, the merged main) —
  committed the root-authored order and the exact `oap/active` =
  `225-a` pointer unchanged, FIRST.
- Immutable order:
  `oap/orders/225-a-demo-installed-acceptance.md`, SHA256
  `c5e288d721cd36425d14634c8b25a899b38af2a0b3d08f2013d175031e50fdb9`
  (re-verified at report time).
- Implementation head (sole SELF parent):
  `e2b8fb45ddb224b44329867beb2533e4c37f8526` ("225-a: installed
  acceptance evidence and closed demo ergonomics defects"; 12 files,
  +849/−97: `demo_web.py` docstring, `admin.css`, `base.html`,
  `openai_assisted/{index,pricing,routes}.html`,
  `docs/{demo-admin,configuration,cli-reference}.md`,
  `tests/integration/test_demo_web_admin_gate_postgres.py`,
  `tests/integration/test_demo_web_postgres.py`,
  `tests/unit/test_demo_web.py`).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file.
- PR: per the order's `CREATE_NEW_PR`, exactly ONE new PR is opened
  from this branch after this report commit, base `main`, head
  `oap/225-demo-installed-acceptance`, title exactly
  `225: Installed acceptance for isolated fake-admin demo`; branch,
  base and head are verified per protocol and the PR number is
  recorded on the strategic terminal. No merge.

## Prior objective state (224, MERGED — from the order's verified
activation state, re-checked at report time)

- PR #383 MERGED as main commit `b593e5e96484dd9979dfe2960e0a7fbbc57c8301`
  at 2026-11-14T23:21:31Z after the one-time 224-aa human-authorized
  suffix exception (report-only SELF
  `6c7473df1dcce915df9d062afb629f16fc221114`).
- Main CI `43652843523` terminal SUCCESS (GitHub
  `updatedAt=2026-11-14T23:33:54Z`); CodeQL `43652843467` SUCCESS;
  Code Quality `43652843497` SUCCESS; all nine check runs on the exact
  merge commit COMPLETED/SUCCESS (including PostgreSQL and real
  Chromium).
- At activation the only open PRs were #379/#319; re-verified at
  report time (fresh fetch): `origin/main` = `b593e5e9...`, open PRs
  only #379/#319, and NO objective-225 PR exists yet.
- Only release `v0.1.0-rc.1`; protect-main ruleset active.

## Acceptance item 1 — CLI fake-admin lifecycle (installed)

Evidence: new
`tests/integration/test_demo_web_postgres.py::test_cli_fake_admin_lifecycle_installed`
(passed in the definitive owned-PG16 run below).

- The REAL installed `slaif-gateway demo-admin` console script runs in
  a subprocess (the installed-CLI code path, not an in-process
  runner) against the owned source database. The child environment is
  minimal and fixture-derived (fixed safe `PATH` including the owned
  PG16 toolchain, a fresh 0700 `TemporaryDirectory` `HOME` removed
  after the call, `LANG`, `TZ`, and `DATABASE_URL` only); the
  test-process environment is never copied in.
- `create`: password supplied via stdin only (never argv); the JSON
  payload returns `username`, `is_enabled` and
  `credential_generation` and never the Argon2 hash or the DSN.
  `list --json` carries the account (`active_account_count == 1`).
- No `delete` command exists: the CLI refuses with
  `No such command` (the 224-aa runbook law, re-asserted).
- Zero active fake admins makes the WHOLE demo entry surface 404:
  after disabling the sole account, both `GET /fakeadmin/login` and
  the CSRF flow `POST /fakeadmin/login` return 404 (no oracle).
  Re-enabling restores `303` logins with the same credentials.
- `reset-password`: the old password is uniformly refused (401 while
  the entry surface is active), the new one works (303).
- Normal admin login is NEVER dispatched by the demo app:
  `GET /admin/login` is the gate's fixed `303` with
  `Location: /fakeadmin/login` (active surface); a sessionless
  `POST /admin/login` is default-denied `404` (with a session it is
  the pre-body quiet 204 — proven by the browser-test mutation
  battery, item 4); and the `public.admin_sessions` row count is
  unchanged across the probe.
- CLI output never carries the passwords, an Argon2 hash or the DSN
  (checked for every step); every failure reports a FIXED safe code
  (`225a_cli_*_failed: rc=N`, `225a_cli_*_leak`,
  `225a_admin_login_*_wire`, `225a_admin_session_created`) — raw CLI
  streams are never reported.
- Cleanup is exact, run-owned and FK-ordered (account events →
  sessions → snapshot requests → account), with a final assertion
  that the account row is gone; no unrelated rows are touched.

## Acceptance item 2 — browser-driven fresh snapshot with a separate
installed worker

Evidence: reworked
`tests/integration/test_demo_web_admin_gate_postgres.py::test_browser_smoke_demo_copy_pages`
(passed in the definitive run; real-Chromium screenshot
`/tmp/slaif-225a-nav-2411572-b1f381424b.png`, 2026-11-15 00:28).

- Real Chromium (Playwright) fills and submits `/fakeadmin/login`
  itself — no injected prebuilt session: the browser fetches the CSRF
  cookie, the hidden form field is asserted equal to that cookie, and
  the browser holds every cookie from then on.
- The browser observes the wait progress: `GET /fakeadmin/wait/status`
  is `{"state": "waiting"}` BEFORE the worker runs.
- The SEPARATE worker is the real installed console script
  (`slaif-gateway demo-snapshot-worker process-request <id> --json`)
  in its own subprocess with a minimal fixture-derived environment
  (worker settings + fixed safe PATH + fresh 0700 HOME; provider/host
  secrets never leak in); it processes exactly the resulting request
  (output carries `verified_unpublished`). On failure only a fixed
  code plus the numeric exit code is raised
  (`225a_worker_failed: rc=N`); captured streams are held in memory
  for success parsing only, never written to disk or reported.
- The request's `worker_target_db` is a fresh `demo_snap_` copy
  database (per-login verified snapshot).
- The SAME browser session then observes `{"state": "ready"}`, the
  wait surface 303s it to the ready page (Playwright follows the
  redirect to the 200 ready page; the exact 303 wire law is asserted
  by the HTTP-driven session B's wait phase in the same test), and
  the browser clicks the primary link
  `Open the admin dashboard (demo view)` to reach `/admin`.
- Two snapshot times are recorded SEPARATELY — the control request
  row's `created_at`/`verified_at` (read from the source control
  database) and the copy's `demo_display.leaves`
  `min(captured_at)`/`max(captured_at)` — both at/after the browser
  login instant. This is NOT an instant-at-login claim.
- A second fake-admin session (HTTP-driven, 224-r law) yields a
  DISJOINT copy B: a different `demo_snap_` database, built after the
  224-r flow rows leave the source, so copy B does not carry the flow
  keys or the receipt (its receipts page renders the honest empty
  chooser state and it carries exactly one copied key).
- No partially verified copy is reachable: the gate holds `/admin`
  until the worker marks the request ready (the browser observed
  `waiting` before and `ready` after).
- Reused verified 221–224 component evidence for negative cases
  already fully covered (order-allowed): the HTTP-driven two-copy e2e
  test (`test_e2e_admin_gate_two_sessions_distinct_copies`, also in
  this run) re-asserts CSRF-verified sign-out, the wrong-CSRF logout
  refusal (the other session stays valid), copy isolation, and exact
  source + all-copy invariance after the whole read/POST/logout phase.

## Acceptance item 3 — real 200 pages and copy data across
representative GET families

The real browser navigates representative normal-admin GET families
with content assertions (200, `private, no-store`, `Demo preview:`
banner where the demo branch renders it), not just route
classifier/303:

- The exact 16-link demo nav renders: Dashboard, Keys, Owners,
  Institutions, Cohorts, Providers, Routes, Pricing, Templates, FX,
  Usage, Operations, Audit, Email, OpenAI, Accounts.
- Dashboard; keys list + one copied key's detail; owners/institutions
  (packaged table-sort JS: asc/desc, `aria-sort`, real reordering when
  >= 2 rows, names match the copy's institutions); providers (+ new
  link); routes (+ first row's detail); accounts; reports (groups
  shown); accounting expired-reservations (calculated at view time
  against the snapshot); key-batch.
- Operations: catalog index (non-empty with the fixture's seven
  test-only run artifact rows, their direct download hrefs, the
  bounded-index note and no-storage-inference honesty; artifact and
  run-detail near-misses are fixed safe 404 in the real browser),
  proposals (honest empty artifact-group state), collect (lists
  exactly the one captured run, "7 files"), jobs (honest empty
  state), review/export-baseline (illustrative demo-only forms, no
  live claim); process-configuration (copy A's worker ran with a
  custom non-default projection — canaries, not secrets — and the
  page shows the FROZEN worker-observed values, never the live
  process settings; copy B, built without them, shows the defaults);
  diagnostics (bounded recent table; the fixture's seeded row renders
  under its sanitizer-remapped demo-prefixed ID and the raw
  `canary-diagreq-` string is ABSENT); replay maintenance index and
  all-active (worker-captured TTL `31,536,000 seconds`; "HMAC
  maintenance eligibility is NOT shown"); no-slash operations path is
  a fixed 404, the trailing-slash index is admitted.
- Five branding slots (favicon, style.css, logo, logo-compact, hero):
  the browser explicitly requests every fixed slot URL and compares
  exact neutral bytes plus `nosniff`/`private, no-store`;
  near-misses (directory, `logos`, query on a slot) are fixed 404.
- Compatibility: index, every package preset, and this copy's own
  copied key (frozen key binding; the form "has no effect");
  near-misses are fixed 404.
- Key detail + clone receipts: the SELECT-only chooser lists the
  copied operation and the positive read-only projection renders
  remapped links/values; RAW source identifiers (receipt operation
  UUID, source public key ID, second source key) never render.
- Email operations: SMTP test page with the fixed "no message is ever
  sent" state; the real form submit is the quiet pre-body 204; the
  apply page is the fixed no-send notice.
- OpenAI-assisted index renders the "Frozen demo display" demo
  branch.
- Sorting/filtering/paging and copy-backed choices are exercised as
  listed above (sortable tables, rows/groups-shown copy, compatibility
  presets from the package, copied key/operation IDs from the copy).
- Normal-admin byte oracle for the demo-only template/CSS changes:
  the four modified templates render byte-identical under normal
  contexts (see Verification evidence; FAILURES: 0).
- Exact intentional exclusion: the key-configuration JSON export
  stays a fixed safe 503 with NO link in demo (224-x/w law): the
  KR sanitizer discards the ordinary policy members the v1 document
  renderer reads, and the demo process carries fixed neutral
  settings; until a separately verified policy projection exists
  (HUMAN DECISION PENDING) the demo emits no configuration export.
  Documented in `docs/demo-admin.md`.

## Acceptance item 4 — mutation battery: every family is a silent
pre-body no-op, with exact digest equality

- 23 representative POSTs — one per operational action family
  (keys create/bulk-import, owners, institutions, providers, routes,
  pricing, FX, templates, accounts, key-batch, reports export,
  catalog collect/review/export-baseline, OpenAI propose,
  diagnostics lookup/cleanup, replay inspect/preview/apply, SMTP
  review, cohorts) — each with a 304-byte urlencoded body, all
  `204` with an EMPTY body: the gate refuses unsafe methods
  pre-body, so no normal handler runs.
- Plus ONE malformed oversized body (90,000 raw bytes,
  `content-type: text/garbage`) → `204` empty, refused pre-body.
- Exact invariance, measured before and after the battery (no vague
  no-op claim):
  - 17 tables on BOTH the source database and copy A — 12 business
    tables (owners, institutions, cohorts, gateway_keys,
    provider_configs, model_routes, pricing_rules, key_templates,
    fx_rates, usage_ledger, audit_log, email_deliveries) plus the
    accounting/job side-effect tables `quota_reservations`,
    `background_jobs`, `catalog_refresh_applications`,
    `request_diagnostics` and the normal `admin_sessions` table —
    each as row count + md5 over the full row text in id order;
  - `demo_control` request and session counts;
  - copy A's `demo_display.leaves` digest (name:sha256:byte_count,
    md5);
  - bounded SHA-256 digests of the CONFIGURED source file set (owned
    completion-profile directory; fixed allowlist, at most 64 files,
    at most 1 MiB each).
- All digests and counts are EQUAL before and after: no source or
  copy business DML, no audit mutation, no quota/accounting change,
  no job creation, no mail, no provider call, no file change, no
  normal admin session created.
- Sign-out is the authorized separate control action (CSRF-verified;
  proven in the browser session below).

## Acceptance item 5 — fences, failure paths and bounded cleanup

- Login CSRF fence: the form's hidden field must equal the cookie
  (asserted in the real browser before submit); wrong/missing
  tokens are refused per the verified 221–224 components and the
  e2e test in this run (the wrong-CSRF logout refusal left the other
  session valid).
- Cross-session old/new references: copy B's session sees none of
  copy A's flow keys or receipt (honest empty chooser); raw source
  identifiers never render (only per-copy remapped values).
- Disabled account: zero-active 404 law (item 1); re-enable 303;
  reset-password old-refused/new-works (item 1).
- Immediate logical inaccessibility on logout: after the
  CSRF-verified sign-out the session cookie is gone and a fresh
  reload of a dynamic page bounces to the login surface with the
  full response chain carrying `private, no-store` (History/BFCache
  erasure is NOT claimed).
- Expiry and worker-restart recovery: reused verified 221–224
  component evidence (order-allowed; PR #383 final-head checks all
  green) for the negative cases already fully covered; the installed
  workflow itself exercised representative failure paths (near-miss
  404s, malformed body, wrong-surface wire laws, zero-active 404s).
- Failure and capacity limits: the worker subprocess and the CLI
  report fixed safe codes with no raw streams; the demo copy's
  bounded index (4,096), bounded recent list and bounded
  profile-file digests are enforced.
- Bounded cleanup: exact test names only — FK-ordered CLI
  lifecycle cleanup (item 1), finalizer-guarded exact-name deletion
  of the seven test-only run leaves and of the 224-r flow rows
  (id-set-diff); both copies and all pre-existing owned data are
  otherwise preserved — no unrelated copy deletion.

## Acceptance item 6 — canaries and honest privacy limit

- The source carries the 222-fixture canaries (secret canaries in
  fields/free text/JSONB, auth/session material, provider credential
  fields, the `canary-diagreq-` diagnostic row, allowed file leaves in
  the profile directory).
- Proven ABSENT from browser responses: the target copy database
  name, the reader role, any `postgresql` string on the operations
  pages, the raw `canary-diagreq-` value (only the remapped
  demo-prefixed ID renders), and the raw receipt UUIDs / source
  public key IDs (only per-copy remapped values render).
- Proven ABSENT from the copy database and display files by the
  sanitizer law (222/224-r) plus the exact digest equality of item 4;
  the seven test-only run leaves are explicitly labeled (validation
  .json is an ACTUAL 223 sanitizer output for a synthetic original
  document; the other six bodies are honest `b"{}"` placeholders —
  transport/binding proof, NOT artifact content validation).
- No secrets are written to disk or reported: worker/CLI captured
  streams are memory-only with fixed-code failures, screenshots go
  to run-owned `/tmp` paths only, and nothing secret enters OAP
  artifacts.
- Honest privacy limitation: usage PATTERNS (timing, volumes, model
  usage) remain in the copy and CAN be identifying. The demo is an
  operator-owned demonstration surface, not a privacy wash.

## Ergonomics and docs (order items)

- 1280 px demo-nav orphan-row fix: a demo-only `demo-admin-nav`
  class on the nav (`base.html`) plus demo-scoped rules in
  `admin.css`; the real browser asserts at 1280 px that the last nav
  row carries >= 2 links (no single orphan) and, at 390 px, that the
  nav collapses behind the toggle which opens the full 16-link list
  (`.admin-header.is-open`).
- Repeated OpenAI warning blocks consolidated in the demo branches of
  `openai_assisted/{index,pricing,routes}.html` only (frozen/no-call/
  no-op and packaged-reference truth preserved).
- Normal render is byte-identical (byte oracle below).
- `docs/demo-admin.md`: new "Installed start / restart / stop
  (objective 225 acceptance)" section — an operator-owned 0600
  `EnvironmentFile` (never inline passwords/cookie secret; clean
  minimal environment; inherited shell variables are NOT claimed
  harmless), the verified standalone uvicorn factory invocation
  (`slaif_gateway.demo_web:create_demo_app --factory`, verified
  against the local uvicorn), role/custody (0700 custody, 0600
  pgpass), cleanup/rollback; no packaged Compose profile claim; no
  release/certification statement.
- `docs/configuration.md`: current-state prose corrected (the demo
  process serves the admitted read surface, not only `/fakeadmin`).
- `docs/cli-reference.md`: stale sentence fixed.
- `demo_web.py` docstring: now states BOTH the control connection
  and the request-local copy-reader connections (the obsolete
  control-DB-only claim is removed).

## Verification evidence (all local/owned; hosted checks NOT
observed at report time)

- DEFINITIVE owned-PG16 installed run (the two integration files,
  6 tests total), exact command:
  `PATH=/tmp/pg16/bin:$PATH DEMO_SAN_TEST_SOURCE_URL=postgresql+asyncpg://test:***@127.0.0.1:54351/slaif_gateway_test DEMO_SAN_TEST_TARGET_URL=postgresql+asyncpg://test:***@127.0.0.1:54352/postgres .venv/bin/python -m pytest tests/integration/test_demo_web_admin_gate_postgres.py tests/integration/test_demo_web_postgres.py -p no:warnings -q`
  (via the `set -o pipefail` runner `/tmp/run-225a-pg.sh`). Result:
  `......  [100%]` (6/6) and `PYTEST_EXIT=0`
  (`/tmp/225a-pg-final.log`, 2026-11-15 00:29). The run-owned browser
  screenshot `/tmp/slaif-225a-nav-2411572-b1f381424b.png` (00:28)
  proves the real-Chromium phase executed.
- Owned infrastructure: disposable PG16 containers
  `slaif222d-src-pg` (127.0.0.1:54351, database
  `slaif_gateway_test`) and `slaif222d-tgt-pg` (127.0.0.1:54352,
  database `postgres`), real `test` role, owned PG16 toolchain at
  `/tmp/pg16/bin`; the existing disposable data setup from prior
  rounds was preserved.
- Focused units on the FINAL code:
  `tests/unit/test_demo_web.py` 301/301 (including the extended
  base-template normal/demo variant test),
  `tests/unit/test_admin_assets.py` 5/5,
  `tests/unit/test_admin_slaif_design.py` 12/12.
- Ruff on the four touched `.py` files: All checks passed
  (re-verified at report time).
- Docs hygiene: `DOCUMENTATION_CHECK=OK files=137` (re-run at report
  time).
- Normal-render byte oracle (re-run at report time): the four
  modified templates (`base.html` + the three openai-assisted pages)
  rendered from the activation commit against the worktree under
  representative normal-admin contexts — FAILURES: 0 (byte-identical).
- Test counts from source: the gate file carries 2 test functions,
  the web-postgres file 4 (1 new), the unit demo-web file 301.
- No unchanged local full matrices were rerun (the order says hosted
  CI supplies the broad routine check).
- KNOWN CI FAILURE, disclosed (not a product/test defect):
  `tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`
  fails because the ROOT-AUTHORED immutable order line
  `PR mode: CREATE_NEW_PR. Objective 225: ...` is inline while the
  governance test requires a standalone `PR mode: CREATE_NEW_PR`
  line. Neither the order nor the test was edited, per strategic
  ruling; root will issue a bounded 225-b canonical-header
  continuation on the SAME PR.

## Real vs mock (exact)

- REAL: Chromium (Playwright sync; real rendering, viewports,
  cookies); the owned PG16 pair (real servers, real role/grant
  matrix, 0700 custody, 0600 pgpass); the real installed
  `demo-snapshot-worker` console script as a SEPARATE subprocess;
  the real installed `slaif-gateway` CLI subprocess; the standalone
  demo ASGI app on loopback uvicorn; the pg_dump/pg_restore 16 worker
  path through the installed script.
- SYNTHETIC: all source data is the fictional 222 fixture (owners,
  users, keys, cohorts, institutions, routes, pricing/FX, usage,
  audit, email) with secret canaries; no real provider, mail or
  company data, no production credentials.
- Test-only copy leaves: the seven 224-x run leaves (one ACTUAL 223
  sanitizer output + six honest `b"{}"` placeholders, labeled as
  transport proof).
- In-process ASGI (httpx ASGITransport) is used ONLY for the CLI
  test's login wire-law probes (303/404/401/204); the browser path is
  real Chromium against the real uvicorn server.
- No docker image was built (the order admits the installed CLI);
  no Redis, no real upstream calls, no real mail.
- Hosted final-head CI: PENDING at report time; root owns final-head
  reconciliation.

## Limitations (honest)

- This is ACCEPTANCE, not release/deployment/company data; no
  release, RC, deployment or certification statement follows.
- Hosted final-head CI is pending at report time, and one known
  governance CI failure is disclosed above (root 225-b plan).
- The key-configuration JSON export remains safely unavailable in
  demo (fixed 503, no link) until a verified policy projection
  exists (human decision pending; 224-x/w).
- The 200-page evidence is the order's "representative normal-admin
  GET families" (browsed in the real browser as listed in item 3),
  not a full route matrix; the broader route inventory and routine
  checks come from the merged 224 work and hosted CI.
- Expiry/worker-restart recovery and some failure/capacity paths rest
  on the verified 221–224 component evidence (merged, CI green) plus
  the representative failure paths exercised by this run, not on a
  re-demonstration of every one.
- Usage patterns remain identifying (item 6).

## GitHub state (observed at report time)

- `origin/main` = `b593e5e96484dd9979dfe2960e0a7fbbc57c8301`
  (fresh fetch).
- Open PRs: only #379 and #319 (unchanged since activation).
- No objective-225 PR exists at report time; exactly one is opened
  from this branch after this commit (title
  `225: Installed acceptance for isolated fake-admin demo`, base
  `main`, head `oap/225-demo-installed-acceptance`). No merge, no
  auto-merge.

## Protected untracked files (untouched, unread, unstaged)

- `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
- `codex.sh`
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
- `uv.lock`
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`
(SHAs re-verified at report time; they match the activation order's
recorded values exactly.)

## Objective status

All six acceptance items, the ergonomics fixes and the docs updates
are complete with the local/owned evidence above. The PR awaits
hosted CI and strategic review; nothing is merged. The one known
governance CI failure is disclosed above with its root-side 225-b
resolution path.
