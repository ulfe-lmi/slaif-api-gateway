# OAP Report — 224-c: isolated demo web entry

PR mode: AMEND — objective-224 PR #383 `oap/224-demo-web` (title
`224: Demo administrator login and isolated snapshot UI`, created by
224-a; still OPEN, no merge; root owns CI/review/merge). This report
closes 224-c on the SAME PR; later suffixes (224-d+) continue the
objective with copy-backed browsing, sanitized file panels,
server-enforced no-op actions, installed wiring/browser evidence and
final delivery. Per the order, the demo is NOT usable for company
demonstrations at the end of 224-c: this suffix adds ONLY the
separate demo entry/login/wait/session/logout surface plus the
narrowly listed 224-b corrections.

## 1. Work order

- Order file: `oap/orders/224-c-demo-entry-and-wait.md`
- Order SHA256: `5814354e5152879f209225e055873b5120e1ca84940eca9cf7d4c3efbaad88aa`
- `oap/active` = exactly `224-c` (5 bytes, no trailing newline).
- Root-authored activation bytes committed first as
  `6ca5a45ac6298c69b290a892178bd3265df32d89` (order + active,
  unchanged). The first line of this order is intentionally the exact
  governance heading, which makes the current-active governance check
  pass (the 224-b colon-heading failure is thereby closed without
  touching the immutable 224-b order).
- Immutable predecessor verified: 224-b report-only SELF
  `d6bd6984d0c2c5d248f21877b94317b4d9c3cda8` (report SHA256
  `e1b6ca9ce63d1c9fbc60d13189cb41468145a041d2de234cbf71739af3bf91ba`),
  224-b order SHA256
  `a3523919d930e9a286b1203306cf6d2cfc5ffa942d3487b0240a90d4b060ae5d`;
  neither was edited. Remote main unchanged at `d3762e51`.
- Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`
  retain SHA256 `5ae1d77c…7feda`, `66eda802…1247`, `d3d0e80d…5b5b6`
  respectively; re-verified by hash before every commit; never
  staged, read, modified, cleaned or stashed.

## 2. Topology and diff scope

- Implementation head: `be1ac33d`, four impl commits on the
  activation commit:
  - `57f3b43f` — the 224-c implementation (17 files, +3183/-154):
    the standalone demo web app, the `/fakeadmin` entry surface and
    templates, the 224-b corrections (dead protected-set removal,
    CLEANUP_FAILED capacity law), docs, 43 focused unit tests and 3
    owned-PG tests.
  - `ff242dec` — doc/code wording fidelity (2 files, +25/-15): the
    structural eviction law now reads from the copy's own persisted
    manifest state (no protected-set phrasing anywhere) with the
    exact 3-verified+1-evictable example; login verification is
    phrased as ONE real Argon2id verification on either path (uniform
    dominant cost), not a blanket constant-time guarantee.
  - `9ed9d9fd` — constant-time CSRF double-submit equality
    (2 files): `_check_csrf` now uses `hmac.compare_digest` on
    UTF-8 bytes for the cookie/field equality (after type/length
    checks, finite bound on BOTH values), matching its docstring;
    focused non-ASCII cookie negative added.
  - `be1ac33d` — pending wait cookie lifetime tied to the request
    TTL (4 files, +68/-5): `PENDING_TTL_S` was 900 s, but a
    legitimate bounded worker chain (221 dump + 222 sanitation +
    223 file stage + pre-publication re-proof, each capped at 300 s,
    plus queue time) can exceed that; it now derives from the 224-a
    `REQUEST_TTL` (3600 s). The request's own `expires_at` remains
    the absolute bound (re-checked on every poll); the
    zero/disable/generation fences are unchanged. Focused tests:
    TTL-equality and a >900 s-old pending cookie completing a
    still-unexpired verified request (fence still denies after
    disable).
- Combined diff `6ca5a45a..be1ac33d`: 17 files, `+3287/-158`:
  - New: `app/slaif_gateway/demo_web.py` (+491),
    `app/slaif_gateway/api/fake_admin.py` (+571),
    `app/slaif_gateway/web/templates/demo/{login,wait,ready}.html`
    (+128), `tests/unit/test_demo_web.py` (+1056),
    `tests/integration/test_demo_web_postgres.py` (+499).
  - Modified:
    `app/slaif_gateway/db/repositories/fake_admin_accounts.py` (+48:
    column-scoped `FakeAdminLoginCredential` login projection for
    the web role), `app/slaif_gateway/services/demo_snapshot.py`
    (±96: dead `protected_job_ids` removal on the 221 admission/
    expiry paths, CLEANUP_FAILED capacity law),
    `app/slaif_gateway/services/demo_web_control.py` (±77: lazy
    worker-only `VERIFIED_COPY_STATE` import (module `__getattr__`)
    so the web chain never loads the privileged snapshot module
    chain; web-side `request_facts`/`session_facts_by_token`
    SELECT-only projections),
    `app/slaif_gateway/services/demo_web_worker.py` (±46: dead
    protected-set SQL/query/call sites removed; deliberate-`pass`
    comments), `docs/demo-admin.md` (+165: the 224-c section —
    entry law, cookies, operator setup, evidence — plus the
    corrected eviction-law paragraph), `docs/configuration.md`
    (+41: the `DEMO_WEB_*` settings), `docs/cli-reference.md`
    (±18: 224-c-accurate forward references; NO new CLI command was
    added), `tests/unit/test_demo_snapshot.py` (±137: protected-set
    tests converted to the structural law, CLEANUP_FAILED capacity
    tests), `tests/unit/test_demo_web_control.py` (±4: the two Code
    Quality thread fixes), `tests/unit/test_demo_web_worker.py`
    (±68: protected-set references removed from the fake control,
    leaf-inode-drift flake fix).
- This report is a report-only SELF commit: sole parent
  `be1ac33d`, sole diff file this report. No other path was touched;
  `oap/reports/` is otherwise unchanged.
- NO migration: 0028 unchanged. NO new CLI command, NO Compose
  service, NO queue/Celery/Redis. No change to `main.py`, the
  ordinary gateway, admin/API handlers, provider adapters,
  forwarding, quota/accounting, or public web code.

## 3. What was implemented

### 3.1 The standalone demo web app (`services`-free, `demo_web.py`)

- `create_demo_app(config, *, facade=None)`: a purpose-built
  STANDALONE ASGI app serving ONLY the `/fakeadmin` routes and their
  packaged static assets. It does not import or call
  `main.create_app` or its lifespan; it registers NO `/v1`, `/admin`
  or ordinary admin routes (proven 404 in unit and owned-PG
  evidence); a generic safe 500 handler ensures no traceback or
  internal value ever reaches a browser; the facade is closed in the
  lifespan.
- `DemoWebConfig` (deliberately NOT part of gateway `Settings`):
  independent `DEMO_WEB_*` environment prefix, default OFF. A
  malformed optional value (e.g. the port) never breaks a
  default-off startup (safe parse, no raw `ValueError`); when
  enabled, the complete control-connection set and a ≥32-char
  cookie secret are REQUIRED (fail-closed `demo_web_misconfigured`,
  no value echo); closed PostgreSQL identifier law for
  user/database; `repr` never echoes the password/secret;
  `engine_url` quotes credentials.
- Signed-value helpers: `b64(ts:payload).sig` (HMAC-SHA256,
  constant-time signature comparison, finite age bound, future-
  rejection) with a finite inbound length bound checked BEFORE any
  decode; `_b64decode` uses matching str types (the earlier
  `str + bytes` defect is fixed and covered).
- `DemoWebFacade` Protocol (the web app's ENTIRE control boundary:
  active-account count, column-scoped login credential, account
  facts, request facts, create request/session, validate/revoke
  session, session facts by token) + `PgDemoWebFacade`: ONE bounded
  web-role engine (`pool 5/5`, `pool_pre_ping`, `pool_timeout=10`),
  one transaction per unit of work, DSN built from the explicit
  web-role fields ONLY with an EXPLICIT `connect_args={"ssl":
  False}` stage boundary (no TLS is ever negotiated; the operator
  must keep the control endpoint on a trusted private
  loopback/Compose network; no verified remote DB TLS).
- Web-path import isolation: `demo_web_control`'s worker-only
  `VERIFIED_COPY_STATE` constant is now imported lazily (module
  `__getattr__` + a local import in the worker-only handoff path),
  so importing the demo web chain does NOT load
  `demo_snapshot`/`demo_web_worker`/222/223 modules; proven in a
  fresh-interpreter subprocess unit test.

### 3.2 The `/fakeadmin` entry surface (`api/fake_admin.py` + templates)

- **Zero enabled accounts → 404 on EVERY demo route** (login, wait,
  wait status, ready, logout): no credential or account-existence
  oracle; the surface is indistinguishable from an unknown path.
- **Login**: finite field lengths (128); a small finite
  request-body bound (8 KiB) enforced on BYTES ACTUALLY RECEIVED
  while streaming — chunked/unknown-length bodies included — before
  any parsing (oversized → 413 with no credential lookup; non-
  urlencoded → 400); signed double-submit CSRF (constant-time
  equality AND signature verification); a bounded in-process failed
  attempt window (20 per 300 s → 429 with `Retry-After`);
  column-scoped credential lookup (web-role grant columns only);
  one real Argon2id verification on either path (real hash for a
  known enabled account; a precomputed fixed dummy hash — computed
  ONCE at process startup, so the first unknown-user attempt has no
  extra hash-generation timing signature — for unknown/disabled
  accounts); one constant failure message; no raw secret, username
  or request detail is ever rendered. Success creates ONE fresh
  pending snapshot request (224-a, live credential generation) and
  hands off a signed pending cookie.
- **Wait**: the signed pending cookie binds
  `account:request:generation`; its lifetime is tied to the request
  TTL (60 minutes — a legitimate bounded worker chain can exceed
  15 minutes; the request's own expiry is the absolute bound).
  EVERY poll (page and JSON `/wait/status`) re-reads the live
  request facts AND the live account fence (disabled/deleted
  account, credential reset, cookie↔request↔live generation
  agreement) and denies immediately. `/wait/status` reports only
  (`waiting|ready|timed_out|failed|unavailable`) and NEVER issues a
  session. Issuance happens exactly once, in the wait page handler
  at the verified moment: one `create_session`, the raw opaque
  token delivered ONCE in the session cookie, then 303 to ready;
  terminal states clear the pending cookie.
- **Ready**: every use revalidates the session (224-a per-use law);
  any refusal bounces to login and clears the cookie; the page
  states that copy-backed browsing is NOT enabled yet.
- **Logout**: signed CSRF; idempotent revocation (web-owned
  `revoked_at` only — the web role never touches the request row);
  clears ALL demo cookies.
- **Cookies** (all HttpOnly/Secure/SameSite=Strict): `slaif_demo_csrf`
  and `slaif_demo_pending` are `Path=/fakeadmin`; the session
  cookie `slaif_demo_session` (raw opaque token only — its SHA-256
  hash is the only stored form) is deliberately `Path=/` on the
  dedicated demo hostname so the authorized later copy-backed GUI
  stage (demo `/admin` pages on the same host) receives it; safe
  because this process has NO normal `/admin`/`/v1` routes and the
  cookie is demo-named; deleted with the same path. Cookie-path
  behavior is unit-tested.
- The web request path NEVER imports or spawns the privileged
  worker: the copy is produced by the separate 224-b
  `demo-snapshot-worker process-request` CLI (worker role, its own
  process). No `work-once` worker selector was needed, so none was
  added (stated honestly per the order).

### 3.3 The order-mandated 224-b corrections (same PR)

- The worker-derived `protected_job_ids` SQL/query/parameters/call
  sites are REMOVED as dead machinery (Section 6b explains why it
  could never protect what the docs claimed). The structural
  verified-state law (read from the copy's own persisted manifest
  state) is the only eviction protection; the bare `run`/`expire`
  CLI paths are covered by it without any caller-supplied set.
- CLEANUP_FAILED capacity law: a job directory in `CLEANUP_FAILED`
  (surviving custody/target artifacts) OCCUPIES its finite budget
  slot and is never generic-evicted (only the exact recovery path
  retries removal), so repeated failed cleanups fill the budget and
  admission fails closed; admission refuses when, after adding a
  new copy, the total (raw + sanitized + verified + CLEANUP_FAILED)
  would exceed the cap and evicting every evictable copy could not
  bring it back. Focused tests prove the 3-verified+1-evictable
  admission, the 3-verified+1-CLEANUP_FAILED refusal, and that
  neither state is ever generic-evicted.
- Operator docs corrected to the actual law (no protected-set
  phrasing; the exact cap example).

### 3.4 The intermediate 224-b CI/review items (fixed in this PR)

B-head (`d6bd6984`) hosted CI, verified on GitHub at this
reconciliation (run 43373532202): the **PostgreSQL integration
tests job COMPLETED SUCCESS** (15m53s, 05:40:21Z-05:56:14Z UTC), as
did E2E, Playwright, Docker Compose, Documentation hygiene and
CodeQL. Only the "Unit, lint, and migration head" job failed, on
exactly two tests, both closed at the current head:

- `test_process_request_leaf_inode_drift_refuses_publication`
  flake: the test now HOLDS AN OPEN FD on the leaf across
  unlink/rewrite so the old inode stays allocated and the negative
  is deterministic.
- `test_oap_governance.py::
  test_active_identifier_resolves_exactly_one_matching_order`: the
  224-b order's first line is
  `# OAP Work Order — 224-b: exact worker handoff and cleanup`,
  whose `: ...` suffix the exact-heading check rejects; the 224-c
  activation heading is the exact `# OAP Work Order — 224-c`, so
  the check passes by activation without touching the immutable
  224-b order; 9/9 green.

PR #383 carried SIX unresolved Code Quality review threads at b-
head (two test hygiene, three "empty except", one "file not
closed"); all are addressed at the current head:

- `tests/unit/test_demo_web_control.py` ~648 (unused local
  variable): `verified = await _full_cycle(...)` is now used in
  `request_id=verified.id`.
- `tests/unit/test_demo_web_control.py` ~834 (statement with no
  effect): the loop now asserts per-coroutine that the state
  remained `bogus` (it actually did).
- `demo_web_worker.py` ~435/719/786 ("empty except" x3): each
  deliberate `pass` now carries an explanatory comment stating the
  best-effort law and the bounded fallback path.
- `demo_web_worker.py` ~692 "File is not always closed" (the
  custody fence): FALSE POSITIVE — the fence fd is released by
  `ds._release_fence(fence_fd)` in the `finally` of the same
  function; the analyzer does not see the cross-module pairing. No
  code change; reported for root to close.

Root owns resolving the review threads on GitHub.

Evidence honesty for this section: NO separate local re-run of the
222/223 worker PG module was performed in the c round, and none is
claimed; the verified b-head hosted PostgreSQL integration SUCCESS
above is the recorded chain evidence for that head, and the c
round's local owned-PG evidence is the NEW 224-c web module only
(3 tests, exit 0, Section 4). The broad 222/223 legacy chains were
NOT re-run locally per root direction; hosted CI covers them on
the final head (recorded as skipped).

## 4. Evidence (this stage)

- **Unit** (fake-fade DI; no database): 317 passed in the 8-file
  suite — `test_demo_snapshot.py`, `test_demo_snapshot_files.py`,
  `test_demo_snapshot_sanitize.py`, `test_demo_web_control.py`,
  `test_demo_web_worker.py`, `test_documentation_inventory.py`,
  `test_demo_web.py`, `test_oap_governance.py`. `test_demo_web.py`
  contributes 46 focused tests: default-off refusal; config
  validation (malformed port off-safe / on-refused, weak secret,
  bad identifiers, missing fields); signed token law (tamper/
  expiry/future/oversize/malformed, purpose separation); zero-
  active 404 on every route; valid login → 303 + pending cookie;
  constant 401 for wrong password / unknown user / disabled
  account; precomputed dummy-hash uniform path (valid Argon2id,
  first-attempt cost class); field-too-long; CSRF mismatch/expiry/
  non-ASCII refusal; attempt bound 429 + window pruning; oversized
  body 413 (explicit and chunked) with NO credential lookup; wrong
  content type 400; waiting state shows no session; `/wait/status`
  never issues; EXACT one-session issuance (pending cookie
  consumed); bad-signature/expired/foreign pending cookie refused;
  failed/timed-out/unavailable terminal states; the LIVE fence on
  every poll (disable, credential reset, account deleted);
  pending TTL = request TTL and a >900 s-old cookie completing an
  unexpired verified request; ready requires a valid session (per-
  use validation; forged/revoked bounce); ready page states
  browsing not enabled; logout revokes and clears ALL cookies (with
  matching paths); logout without session; cookie-path law
  (session `Path=/`, pending/CSRF `Path=/fakeadmin`, deletions
  match); `/v1`+`/admin` absent; web-path import isolation in a
  fresh interpreter.
- **Owned PostgreSQL 16** (real restricted web role + real
  worker-role CLI on the owned source/target pair, synthetic data
  only, run-owned teardown with residue asserted):
  `tests/integration/test_demo_web_postgres.py` — 3 tests, exit 0:
  (1) the FULL cycle: web-role HTTP login (real Argon2id verify
  under the web role's column-scoped read) → fresh pending request
  → `process-request` CLI (real 221/222/223 chain; safe
  vocabulary, no canaries in output) → wait → exactly one session
  (stored form is the SHA-256 hash, never the raw token; revoked
  on logout) → ready (per-use validation) → a second login yields a
  DISTINCT request while the verified copy stays bound → the
  revoked session is refused on next use → worker `cleanup` drops
  the bound target database and the row reaches `cleaned` (target
  database proven absent); (2) the web role's 42501 boundary:
  granted column reads succeed while full-row account read,
  business-table read, `state` named in a request INSERT, and ANY
  request UPDATE (including worker-owned columns) are refused by
  the database; (3) zero enabled accounts → 404 on every demo
  route, re-enable restores.
- **Hygiene**: scoped Ruff (repository policy, no extra flags)
  clean on every touched file; `py_compile` clean; `git diff
  --check` clean; governance 9/9.
- **NOT re-run locally** (hosted CI covers on the final head; root
  direction): the 222/223 legacy integration chains, including
  their worker PG module (the b-head hosted PostgreSQL integration
  job's SUCCESS, Section 3.4, is the recorded evidence for that
  head). The c round's local owned-PG evidence is the new 224-c web
  module above.

## 5. Honest limitations

- ENTRY ONLY: copy-backed browsing is NOT enabled; the demo is NOT
  usable for company demonstrations. The ready page says so.
  224-d+ supplies copy-backed admin browsing, sanitized file
  panels, server-enforced no-op actions, installed wiring/browser
  evidence and final delivery.
- No CLI command or Compose service ships with the entry process:
  the operator runs `create_demo_app` as a standalone ASGI app
  (e.g. a uvicorn factory wrapper) on the dedicated demo host with
  the `DEMO_WEB_*` environment on that process only (documented in
  `docs/demo-admin.md` and `docs/configuration.md`).
- The login attempt bound is in-memory per process (a single
  operator-facing demo process, documented); it resets on process
  restart.
- Transport: the web control connection uses an EXPLICIT
  `ssl=False` stage boundary (no TLS negotiated; no verified remote
  DB TLS) — the operator must keep the control endpoint on a
  trusted private loopback/Compose network.
- The pending cookie grants nothing by itself; the absolute bound
  is the request's `expires_at`, re-checked on every poll, with the
  zero/disable/generation fences throughout.

## 6. Explicit corrections to the immutable 224-b report's claims

The 224-b report is an immutable claim, not authority; the order
required these corrections here (the 224-b report itself is
untouched):

- **(a) Cap example.** The 224-b cap example was factually wrong:
  with `max_copies=4`, three verified copies + ONE evictable
  (raw/sanitized) copy, `run_snapshot_job` EVICTS the raw copy and
  ADMITS the new copy, finishing at exactly the cap (4). A refusal
  happens only when the fourth occupied slot is held by a
  never-evictable copy (verified or CLEANUP_FAILED). Proven by
  `tests/unit/test_demo_snapshot.py::
  test_three_verified_plus_one_unverified_new_run_never_exceeds_cap`
  (raw copy dropped, verified copies untouched, total == cap, new
  copy present) and
  `test_three_verified_plus_one_cleanup_failed_new_run_refused`
  (refusal). The operator docs now state this exact law with the
  example.
- **(b) `protected_job_ids`.** The 224-b docs/report claimed the
  worker-derived `protected_job_ids` set protects in-flight
  UNVERIFIED copies. Its SQL selected only control rows with
  `state='verified_unpublished'` — whose copies are ALREADY
  structurally excluded from generic expiry — so the set could
  never have protected what the docs claimed; it was redundant
  dead machinery. It is now REMOVED (worker SQL/query/parameters/
  call sites and their tests); the structural persisted-state law
  is the only eviction protection, and the docs no longer mention
  any protected set. No reachable protection was weakened: every
  previously protected copy is a verified copy, which the
  structural law still never generic-evicts.

## 7. Protocol state

- No merge, no auto-merge, no release, no deploy, no real company
  data. The coding agent does not merge; root owns CI/review/merge
  on the final head.
- The next numeric objective is not activated until objective 224
  is resolved; 224-d+ continues on this same PR.
- Handoff: this report-only SELF is pushed on `oap/224-demo-web`;
  one exact two-byte `OK` is sent on the canonical response FIFO
  and exactly one canonical control waiter is rearmed after remote
  verification. No second signal.
