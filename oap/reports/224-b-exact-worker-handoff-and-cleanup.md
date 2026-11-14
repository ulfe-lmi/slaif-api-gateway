# OAP Report — 224-b: exact worker handoff and cleanup

PR mode: AMEND — objective-224 PR #383 `oap/224-demo-web` (title
`224: Demo administrator login and isolated snapshot UI`, created by
224-a; still OPEN, no merge; root owns CI/review/merge). This report
closes 224-b on the SAME PR; 224-c+ continues the objective.

## 1. Work order

- Order file: `oap/orders/224-b-exact-worker-handoff-and-cleanup.md`
- Order SHA256: `a3523919d930e9a286b1203306cf6d2cfc5ffa942d3487b0240a90d4b060ae5d`
- `oap/active` = exactly `224-b` (5 bytes, no trailing newline).
- Root-authored activation bytes committed first as
  `268bc26961bb0d59cb90193c4ee23d75ca0ca41e` (order + active,
  unchanged).

## 2. Topology and diff scope

- Implementation head: `f86a744b3c7c906933b4f3953162e232a99d7ed1`,
  two impl commits on the activation commit:
  - `3d6c7cbb8605ac2c1296684e21bb9d6327f3da23` — the 224-b
    implementation (15 files, +4269/-73).
  - `f86a744b3c7c906933b4f3953162e232a99d7ed1` — review-driven
    tightening to actual code (2 files, +98/-17): docs honesty
    (failure-row states, proof law, transport) plus the exact
    operator role-creation/grant instructions, and an explicit
    no-TLS connect argument on the control connection so the
    documented private-only transport boundary is enforced in code
    (within the order's transport intent; no behavior change beyond
    the documented no-TLS boundary).
- Combined diff `268bc269..f86a744b`: 15 files, `+4351/-74`:
  - New: `app/slaif_gateway/services/demo_web_worker.py` (+881),
    `tests/integration/test_demo_web_worker_postgres.py` (+935),
    `tests/unit/test_demo_web_worker.py` (+1313).
  - Modified: `app/slaif_gateway/cli/demo_snapshot_worker.py` (+94:
    `process-request` / `cleanup` commands + safe output),
    `app/slaif_gateway/services/demo_snapshot.py` (+241: structural
    verified-copy eviction law, durable request→job association,
    exact-set cleanup preflight),
    `app/slaif_gateway/services/demo_snapshot_files.py` (+180:
    shared read-only tree re-proof with job-identity binding),
    `app/slaif_gateway/services/demo_snapshot_sanitize.py` (+67:
    exact-job-only sanitation entry point),
    `app/slaif_gateway/services/demo_web_control.py` (+55: worker
    transitions used by the worker; 224-a matrix/locking law
    unchanged), `app/slaif_gateway/config.py` (+15: the five
    `DEMO_WEB_WORKER_CONTROL_*` settings),
    `docs/demo-admin.md` (+242: the 224-b section incl. operator
    role setup, eviction law, recovery/cleanup law, transport),
    `docs/cli-reference.md` (+40), `docs/configuration.md` (+25),
    `docs/database-schema.md` (+16: current-head sentence corrected
    to 0028/37 tables — the repair of the intermediate 224-a
    documentation-inventory CI failure), `tests/unit/
    test_demo_snapshot.py` (+240), `tests/unit/test_demo_web_control.
    py` (+74).
- This report is a report-only SELF commit: sole parent
  `f86a744b3c7c906933b4f3953162e232a99d7ed1`, sole diff file this
  report. No other path was touched; `oap/reports/` is otherwise
  unchanged.
- No change to `main.py`, ordinary admin/API handlers, provider
  adapters, forwarding, quota/accounting, Compose/image/Nginx, or
  public web code. NO migration in 224-b: it runs on the 0028
  schema of 224-a unchanged. No schema change was needed.

## 3. What was implemented

### 3.1 The private worker orchestration (`services/demo_web_worker.py`)

- `DemoWebWorkerConfig` + `web_worker_config_from_settings`:
  feature-local validation (223-a precedent) of the 221/223 demo
  configuration and the five `DEMO_WEB_WORKER_CONTROL_*` fields, so
  an ordinary demo-disabled gateway never fails to start because of
  optional demo settings; closed PostgreSQL identifier law for user/
  database (no interpolation escape); the control password is
  `repr=False` and never rendered.
- `_ControlConnection`: ONE bounded control-connection factory per
  invocation (`pool_size=1, max_overflow=0, pool_pre_ping=True,
  pool_timeout=10`), DSN built from the explicit worker-role fields
  ONLY — never the owner `DATABASE_URL` — with an EXPLICIT
  `connect_args={"ssl": False}`: the same deterministic no-TLS stage
  boundary as the 222 asyncpg target connection (no TLS is ever
  negotiated; the operator must keep the control endpoint on a
  trusted private loopback/Compose network).
- `process_request` (one bounded invocation, worker-only):
  1. claim — the 224-a atomic guarded transition (pending only;
     statement-time account gate); a lost/replayed/stale claim is a
     safe `claim_refused` result and no pipeline runs;
  2. ONE fresh 221 raw copy — the private custody manifest records
     the request identity BEFORE the target database is created (the
     durable crash-safe request→job association);
  3. 222 sanitation of THAT exact job only (exact-job selector; no
     global scan, no promotion of unrelated copies);
  4. 223 file capture/verification of THAT exact job only;
  5. worker-held proof (`_verify_worker_held`): re-read the main
     manifest through the ANCHORED held job handle (no pathname read;
     name-binding asserted) proving job identity, the EXACT request
     association, the combined 222+223 verified manifest state and
     target grammar, then re-prove the COMPLETE 223 display-tree law
     through the shared read-only re-proof (files-directory identity,
     exact leaf set — no foreign entry, no duplicate/invalid name —
     per-leaf regular type / 0600 mode / byte count / inode
     identity, digests, display policy) with the SAME job-directory
     identity binding both reads and the re-proven leaf count /
     total bytes equal to the main manifest's `files_count` /
     `files_bytes`; a per-copy elapsed deadline bounds the re-proof
     (checked before each leaf read and before promotion);
  6. record the verified handoff (224-a CAS: statement-time
     account fence, copy lifetime, exact manifest state, copy
     uniqueness).
  Every stage runs off the control loop (`asyncio.to_thread` around
  the synchronous 221/222/223 entry points; worker-only single-task
  invocation). It exits 0 with `state: verified_unpublished` only on
  full success; every failure exits 1 with a finite safe code and
  never publishes.
- `recover_and_cleanup` (one bounded invocation, `--limit` 1..100,
  schedulable): reap stuck pending/claimed rows (224-a bounded
  law); mark failed rows and session-released verified rows
  `cleanup_pending` (the 224-a service enforces the live usable-
  session gate; a refused row is counted retained); then for each
  `cleanup_pending` row drop ONLY its bound target database FIRST,
  remove ONLY its owned custody leaves under the custody fence,
  prove the files directory absent through the held job dirfd, and
  mark `cleaned` only after the database is proven gone. Ownership
  is resolved ONLY through the durable private association
  (`manifest.request_id`, written before target creation): exactly
  ONE matching job is cleaned; ZERO (positively confirmed, every
  manifest readable) is marked cleaned as no-op; AMBIGUOUS (double-
  bound or unreadable manifest) RETAINS the row and every artifact.
  Nothing is inferred from directory order, names or timestamps.

### 3.2 Structural verified-copy eviction law (binds every generic 221 path)

A copy in `DB_AND_FILES_VERIFIED_UNPUBLISHED` state is NEVER evicted
by any generic 221 path — not retention expiry, not copy-budget
overflow, not a bare `run`/`expire` CLI invocation, not a
concurrent worker's startup pass — regardless of protected set and
age. Only the exact control-owned cleanup (gated by the request
state machine and the live-session law) may remove it. This closes
the publication/expiry races: a stale worker-derived protected-set
read (computed before the fence) or a cross-worker race cannot evict
a published or about-to-publish verified copy. Verified copies still
occupy their finite budget slot: they count in both the overflow
computation and the fail-closed admission check, which refuses a new
copy whenever post-expiry total + 1 exceeds the maximum
(`SNAPSHOT_BUDGET_FULL`, e.g. 3 verified + 1 unverified at max 4 →
the new run is refused, never a fifth copy). In-flight unverified
copies named in the worker-derived `protected_job_ids` (derived from
authoritative live control state, never caller-supplied) are
additionally never generic-evicted.

### 3.3 Exact-owned cleanup preflight (221 custody)

`_clean_job_files` first lists the files directory under the HELD
files fd (exact-set preflight): an empty directory (a pre-existing
partial cleanup) is safely `rmdir`ed; otherwise the private files
manifest must list EXACTLY the created leaves plus the manifest
itself (flat-name grammar, no foreign entries, no duplicates) —
any mismatch causes ZERO removals and a refusal, leaving manifest +
leaves intact so a later retry after foreign-leaf removal succeeds.
Deletion then proceeds only through the held-handle staged cleanup
with identity rechecks; the 223 DB-first ordering and the final
absence proof are preserved.

### 3.4 223 shared read-only re-proof

`run_files_job(config, settings, job_id=...)` gained the exact-job
selector; `_reprove_files_tree` is now a shared READ-ONLY verifier
(anchored no-follow reads, trusted configured caps with finite
absolute ceilings, deadline, optional `expected_job_identity` job-
directory binding) that the 223 verifier, the 224-b worker proof and
the cleanup preflight all use — a promoted tree is re-proven exactly
as hard as a fresh one.

### 3.5 CLI, config, docs

- `slaif-gateway demo-snapshot-worker process-request REQUEST_ID
  [--json]` and `slaif-gateway demo-snapshot-worker cleanup
  [--limit N] [--json]`: fixed safe output vocabulary (state,
  finite counts, safe aggregate `failure_code` only when non-None,
  elapsed ms) — never a job id, target database name, custody path,
  DSN, password or row content.
- Five new `DEMO_WEB_WORKER_CONTROL_*` settings (all optional,
  default OFF; documented in `docs/configuration.md`).
- `docs/demo-admin.md` 224-b section: what/is-NOT, invocation and
  failure-row states (including that a copy-uniqueness handoff
  refusal aborts without a failure write and the row is reaped at
  full lifetime as `failed`/`late_completion`), the exact operator
  CREATE ROLE / GRANT statements for the web and worker control
  roles (the reviewed `web_role_grant_sql` / `worker_role_grant_sql`
  matrix; passwords set out-of-band, never printed), the eviction
  law, the request→job association/recovery law, the cleanup and
  live-session law (incl. the documented residual window and its
  safe direction), the transport boundary, and the no-survivors
  guarantee.

## 4. Focused verification (actual exits, host .venv)

- Unit, no database — the six directly affected files:
  `tests/unit/test_demo_snapshot.py` (40), `tests/unit/
  test_demo_snapshot_files.py` (68), `tests/unit/
  test_demo_snapshot_sanitize.py` (66), `tests/unit/
  test_demo_web_control.py` (28), `tests/unit/
  test_demo_web_worker.py` (34), `tests/unit/
  test_documentation_inventory.py` (16) — TOGETHER 252 tests, exit 0
  (re-run after the final no-TLS code change). The 34 worker tests
  cover: claim/protected-set law; the structural eviction law and
  the exact 3 verified + 1 unverified → new-run refusal; durable
  association ZERO/ONE/AMBIGUOUS resolution; cleanup preflight
  (foreign leaf → zero removals and refusal, retry after removal,
  empty-dir retry, tampered manifest refusal); worker-held proof
  negatives (directory rebinding, extra leaf, duplicate, inode
  drift, identity mismatch, leaf count/bytes mismatch); deadline
  lapse (no promotion, `SNAPSHOT_BUDGET_FULL` aggregate); safe
  output (no canary job/target/path in stdout/JSON); config
  validation negatives (disabled-demo base code vs enabled-worker
  malformed cap; source/seal both-or-neither).
- OWNED PostgreSQL 16 (the two pre-existing owned, labeled,
  loopback-bound postgres:16 containers `slaif222d-src-pg` at
  127.0.0.1:54351 and `slaif222d-tgt-pg` at 127.0.0.1:54352, owned
  by this objective's stages; identity re-verified before the run;
  exact run-owned cleanup): `tests/integration/
  test_demo_web_worker_postgres.py` — 11 tests, exit 0 (re-run after
  the no-TLS change, which exercises the real control engine):
  1. `test_e2e_one_request_yields_one_exact_verified_copy` — one
     request end-to-end: claim → ONE fresh 221→222→223 copy → proof
     → `verified_unpublished` with the exact bound job/target;
     source DB fingerprint proves the source rows unchanged.
  2. `test_second_request_gets_distinct_copy` — a second request
     yields a DISTINCT copy (no reuse, no promotion of the first).
  3. `test_two_racing_workers_claim_exactly_once` — two concurrent
     `process_request` invocations: exactly one claim wins.
  4. `test_unbound_legacy_copy_never_promoted_by_request_run` — a
     pre-existing unbound (pre-224-b style) copy is never promoted
     or consumed by a request run.
  5. `test_reset_mid_job_refuses_late_handoff` — a credential reset
     mid-job makes the handoff CAS match 0 rows: the stale worker
     result never reaches verified_unpublished (statement-time
     fence).
  6. `test_copy_locator_reuse_refused_by_unique_index` — re-handing
     the same copy to a second request is refused by the partial
     unique index (`web_request_copy_reused`), no canary echoed.
  7. `test_budget_full_of_verified_refuses_second_request` — budget
     full of verified copies → `SNAPSHOT_BUDGET_FULL`, nothing
     evicted.
  8. `test_session_aware_cleanup_matrix` — cleanup refused while a
     live usable session binds the copy; proceeds after revocation /
     account disable / reset; DB dropped first, leaves removed,
     `cleaned` only after proven absence.
  9. `test_restart_recovery_removes_crashed_worker_artifacts` — a
     crash/restart mid-pipeline leaves NO survivor before
     `cleaned`; the exact owned job is found through the durable
     association.
  10. `test_restricted_role_matrix_denials` — the REAL service and
      worker paths run under the restricted web/worker roles; every
      forbidden surface denied (42501), worker never reads
      token_hash/username/password_hash, web never moves a request
      out of pending.
  11. `test_cli_process_request_and_cleanup_never_render_canaries`
      — the real CLI renders no canary job id, target database name,
      custody path, DSN or password on any path.
- Scoped Ruff (repository policy) over every changed code/test
  file: clean. `git diff --check`: clean. `py_compile`: clean.
- CI: the intermediate 224-a head (`d23b13d7`) Unit job failed ONLY
  `tests/unit/test_documentation_inventory.py::
  test_every_sqlalchemy_table_is_named_in_schema_contract` (the
  schema doc's current-head sentence still said 0027/35 tables);
  repaired in this PR (`0028`/37) and that file is 16/16 green
  locally. Final-head CI is pending on push; root owns CI/review/
  merge.
- Protected untracked files verified hash-only, still untracked and
  unmodified: `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
  `codex.sh` `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
  `uv.lock` `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.

## 5. Negative / security / privacy / accounting evidence

- Security: least-privilege enforced under the REAL restricted
  roles on PG16 (items 4.10/4.11): the worker control connection
  uses the dedicated worker role only (never the owner
  `DATABASE_URL`); web can never move a request out of pending or
  mark a copy verified; the worker never reads browser token hashes
  or account credentials; copy identities are published no earlier
  than the verified handoff CAS; a stale worker result can never
  become browser-authoritative (statement-time account fence +
  copy lifetime + exact manifest state, proven in 4.5/4.6); the
  generic 221 paths cannot evict a verified copy by construction
  (3.2). Transport: explicit no-TLS (`ssl=False`) on both the 222
  target and the 224-b control connections — a deterministic
  private-only boundary requiring a trusted loopback/Compose
  network, not a verified remote TLS claim.
- Privacy: all demo data is synthetic run-tagged canaries on owned
  PG16; no real company data, no real provider credentials, no mail,
  no browser, no production dump. The 222/223 per-copy ID laws and
  display-only file artifacts are unchanged; the private custody
  manifest (worker-only, 0600) retains the target database name and
  request association for exact cleanup — never in any public
  CLI/log/projection.
- Accounting: no business table, quota/accounting law, provider/
  Codex module, inference route, or migration changed in this stage
  (0028 unchanged; the 221 source fingerprint test proves the source
  rows are unchanged by a worker run).

## 6. Honest limitations

1. The demo is STILL UNUSABLE. No `/fakeadmin/login`, no demo HTTP
   route, no copy-backed demo reads, no no-op actions, no browser:
   224-c+ on the SAME PR must supply the web route under the web
   role and the browser binding; objective 225 (installed-flow
   qualification) remains inert until this PR is terminal.
2. Transport: BOTH the 222 target and the 224-b control connections
   connect with explicit `ssl=False` (no TLS ever negotiated). The
   operator MUST keep both endpoints on a trusted private
   loopback/Compose network; this stage does not support verified
   remote DB TLS.
3. Orphan verified copies from pre-224-b operator runs (no recorded
   request association) are structurally NEVER auto-expired: they
   occupy budget (fail-closed admission) and remain inspectable for
   exact operator cleanup — a deliberate limitation, not a silent
   sweep.
4. A claimed request whose worker dies cannot be re-claimed (claims
   are pending-only); it is reaped at its full lifetime as
   `failed`/`late_completion` and then cleaned. A copy-uniqueness
   handoff refusal likewise leaves the row `claimed` until that
   bounded reap (documented in `docs/demo-admin.md`).
5. The 221/222/223 broad owned-PG chains were NOT re-run locally for
   this diff (root-directed; hosted CI runs the matrix on the final
   head; 221's PG test uses the separate `DEMO_SNAP_TEST_*` env vars
   and raw-only copies, so it does not exercise the new cleanup
   preflight). The directly affected 222/223 unit suites were
   re-run (item 4).
6. `tests/integration/test_alembic_fresh_upgrade_postgres.py::
   test_bare_fresh_alembic_upgrade_head_creates_wide_version_table`
   fails in THIS environment for a pre-existing, unrelated reason
   (testcontainers defaults to `postgresql+psycopg2://`; the host
   venv has no psycopg2) — recorded in the 224-a report and
   unchanged here.
7. All PostgreSQL evidence is synthetic owned-PG16 docker runs; no
   installed-worker, browser, provider, or mail evidence exists yet.
8. No merge and no next numeric objective while this PR remains
   open.

## 7. Next same-PR stages (224-c and later)

Per the order: the dedicated `/fakeadmin/login`/wait/browser app on
the 224-a foundation under the web role (login against the column-
scoped credential SELECT; request creation via the column-limited
INSERT; session issuance/revocation); web-readable publication of
ONLY verified sanitized file leaves bound to the session's copy; the
finite API-process settings projection captured at login with an
explicit capture timestamp (the existing safe
`inspect_process_configuration(settings, process_scope='api')`
projection); logout/expiry exact cleanup consuming
`cleanup_pending`/`cleaned` (web side, coordinated with the worker
cleanup law); the demo no-op actions; and installed-flow
qualification (objective 225 remains separate).
