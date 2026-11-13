# OAP Report — 224-d: verified-copy reader and read-only preview

PR mode: AMEND — objective-224 PR #383 `oap/224-demo-web` (title
`224: Demo administrator login and isolated snapshot UI`, created by
224-a; still OPEN, no merge; root owns CI/review/merge). This report
closes 224-d on the SAME PR; later suffixes (224-d+… i.e. the next
same-PR suffixes) continue the objective with the copy-backed admin
GUI behind a server-side mutation gate, sanitized file-backed
panels, installed browser evidence and final delivery. Per the
order, the demo is NOT usable for company demonstrations at the end
of 224-d: this suffix makes an EXACT fully verified disposable copy
readable under a dedicated target-copy reader role and adds ONE
small authenticated read-only preview page. It does not mount the
normal admin routers and does not claim the demo GUI usable.

## 1. Work order

- Order file: `oap/orders/224-d-verified-copy-reader.md`
- Order SHA256: `a8c196742f85de4ffa748af58d81d334a1b6da5240e600d89baa113cdae1fe1b`
- `oap/active` = exactly `224-d` (5 bytes, no trailing newline).
- Root-authored activation bytes committed first as
  `97e9e86265d2fb2a3f4040bfd9ff82421fbd4721` (order + active,
  unchanged).
- Immutable predecessor verified: 224-c report-only SELF
  `dc128eb98f5699f4abe2b3d9451288831a945894`, sole parent
  `be1ac33d91cf5c78a2c27726067b96e3ba76473c`, sole diff
  `oap/reports/224-c-demo-entry-and-wait.md` SHA256
  `7d1cca7fff36c52256b3b3b75e6d702999d908437ef1d8a8962189d38f0a7582`;
  224-c order SHA256
  `5814354e5152879f209225e055873b5120e1ca84940eca9cf7d4c3efbaad88aa`;
  neither was edited. Remote main unchanged at
  `d3762e51c9a323dee6b728c4a45fa21b0bffae86`.
- Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`
  retain SHA256 `5ae1d77c…7feda`, `66eda802…1247`, `d3d0e80d…5b5b6`
  respectively; re-verified by hash before every commit; never
  staged, read, modified, cleaned or stashed.
- c-head (`dc128eb9`) hosted CI, verified on GitHub at this
  reconciliation (run 43385137610): **PostgreSQL integration
  COMPLETED SUCCESS**, **Playwright COMPLETED SUCCESS**; the "Unit,
  lint, and migration head" job FAILED only
  `tests/unit/test_admin_usability_inventory.py::
  test_every_visible_entry_field_has_linked_guidance` (the demo
  login fields lacked linked help ids). That direct defect is fixed
  in this implementation (Section 3.5). PR #383 carried nine Code
  Quality threads on c-head; root verified and resolved four false
  positives (canonical ellipsis bodies of
  `DemoWebFacade(Protocol)`); the remaining five (three overwritten
  `r` assignments and two unused `r` in
  `tests/unit/test_demo_web.py`) are fixed here (Section 3.5). Root
  owns resolving the threads on GitHub.

## 2. Topology and diff scope

- Implementation head: `155851d0c20a3003b07e6f2562517094ea781835`,
  ONE implementation commit on the activation commit (amended
  locally in response to the pre-report reviews; it was never
  pushed).
- Combined diff `97e9e862..155851d0`: 17 files, `+2155/-44`:
  - New:
    `app/slaif_gateway/web/templates/demo/copy_preview.html` (+68),
    `tests/integration/test_demo_web_copy_reader_postgres.py`
    (+735).
  - Modified:
    `app/slaif_gateway/api/fake_admin.py` (+90: the
    `/fakeadmin/copy-preview` route, the readable-now law and the
    no-store response), `app/slaif_gateway/config.py` (+9:
    `DEMO_SNAPSHOT_TARGET_READER_ROLE`, default empty, gateway boots
    fine without it), `app/slaif_gateway/demo_web.py` (+252: the
    copy-reader config fields + closed-name engine URL, the
    `CopyReader`, the factory seam on `create_demo_app`, and the
    same fail-closed validation for BOTH config sources),
    `app/slaif_gateway/services/demo_web_control.py` (±10: the
    projection docstring now records that the WEB role reads
    `worker_target_db` for the 224-d binding while `to_safe_dict`
    still never emits locators),
    `app/slaif_gateway/services/demo_web_worker.py` (+191: the
    role-law precheck + one-transaction publication grant, its
    wiring as step 5b, the prompt failure marks on both handoff
    refusal paths), `app/slaif_gateway/web/templates/demo/
    login.html` (±10: `aria-describedby` linked help on username
    and password), `app/slaif_gateway/web/templates/demo/
    ready.html` (±10: link to the preview; still states full GUI
    browsing is not enabled), `docs/cli-reference.md` (±22: the
    grant is inside `process-request`; NO new CLI command; the
    preview lives in the standalone web process),
    `docs/configuration.md` (±13: `DEMO_SNAPSHOT_TARGET_READER_ROLE`
    and the four `DEMO_WEB_COPY_*` settings), `docs/demo-admin.md`
    (+129: the 224-d section — secret-safe operator role
    provisioning with `CREATE ROLE … LOGIN` + interactive
    `\password` (no literal password example), the worker grant
    law, the web reader law, safe rollback, still-incomplete
    status), `tests/integration/test_demo_web_postgres.py` (±21:
    the 224-c module's web config carries the copy-reader binding
    and the worker env the reader role — regression adaptation
    only), `tests/integration/test_demo_web_worker_postgres.py`
    (+82: the run-owned static reader role on the owned target,
    the worker env wiring, and the exact role-grant-derived copy
    teardown), `tests/unit/test_admin_usability_inventory.py`
    (±3: 54→55 sortable tables for the preview counts table),
    `tests/unit/test_demo_web.py` (+388: 16 new 224-d tests),
    `tests/unit/test_demo_web_worker.py` (+166: 7 new 224-d tests).
- This report is a report-only SELF commit: sole parent
  `155851d0`, sole diff file this report. No other path was touched;
  `oap/reports/` is otherwise unchanged.
- NO migration: 0028 unchanged. NO new CLI command, NO Compose
  service, NO queue/Celery/Redis. No change to `main.py`, the
  ordinary gateway, admin/API handlers, provider adapters,
  forwarding, quota/accounting, or public web code.

## 3. What was implemented

### 3.1 The worker publication grant (one transaction, no partial
grants)

- `DEMO_SNAPSHOT_TARGET_READER_ROLE` (gateway `Settings`, default
  `""`): the closed-name identifier of the operator-created STATIC
  reader role. Feature-local validation in
  `web_worker_config_from_settings` (223-a precedent): required and
  must match the closed PostgreSQL identifier law, so a malformed
  optional value never breaks an ordinary demo-disabled gateway.
- The operator provisions the role (docs/demo-admin.md): LOGIN,
  its own password (set via interactive `\password`, never printed
  or stored in docs), NO privilege bits, NO role memberships,
  distinct from the target-admin user. The worker NEVER creates or
  alters any role.
- `_grant_target_reader(config, target_db)` runs, through the same
  bounded credential-masked PG client boundary as the 221
  create/drop ops (PGPASSFILE only, finite 30 s deadline, no argv
  passwords):
  1. role-law precheck — one bounded query against `pg_roles` +
     `pg_auth_members` on the target service's `postgres` database
     must return exactly `1` (exists, LOGIN, no
     SUPERUSER/CREATEDB/CREATEROLE/BYPASSRLS/REPLICATION bit, zero
     role memberships); the role must not equal the target-admin
     user (checked before any psql call);
  2. ONE explicit transaction connected to the EXACT target
     copy: `BEGIN; GRANT CONNECT ON DATABASE "<copy>" TO "<role>";
     GRANT USAGE ON SCHEMA public; GRANT SELECT ON ALL TABLES IN
     SCHEMA public; COMMIT;` with `ON_ERROR_STOP` — a
     mid-transaction failure aborts and the open transaction rolls
     back, so a schema-grant refusal leaves NO partial CONNECT
     (proven in real PG, Section 4).
- Wiring: `process_request` step 5b, between the combined
  222+223 worker-held re-proof (`_verify_worker_held`) and
  `record_verified_handoff` — i.e. the grant is complete BEFORE the
  copy becomes browser-authoritative. The grant sees only the exact
  verified copy's database name; a raw, DB-only-sanitized, failed,
  stale-generation, reused or wrong-request copy is never reached
  (those fail earlier with their own codes).
- Failure law: any grant refusal/timeout/malformed state raises
  `DemoWebWorkerError(WEB_READER_GRANT_FAILED)` and the request is
  marked `failed` promptly via `_safe_record_failure` (guarded
  no-op if the row moved) WITHOUT publishing; the exact
  request-associated cleanup then drops the bound target database,
  which removes every grant with it (a failed drop retains the
  inspectable `cleanup_pending` state). Both handoff-refusal paths
  (control error, refusal) now also mark `failed` promptly rather
  than leaving the row `claimed` until lease reap (the bounded reap
  remains the documented backstop).
- The public-table grant is bounded by the 222 fail-closed schema
  inventory: the copy exists only because 222 sanitized exactly the
  reviewed closed table set, so `ALL TABLES IN SCHEMA public` is
  precisely that inventory. The role receives NO source-cluster
  grant, NO target-admin privilege, NO DML/DDL.

### 3.2 The bounded per-request copy reader (`demo_web.py`)

- `DemoWebConfig` gains the independent COPY READER connection
  (`DEMO_WEB_COPY_HOST/PORT/USER/PASSWORD`): never the worker's
  target-admin passfile, source-export credential, normal
  `DATABASE_URL`, Redis or provider secret. Malformed optional
  values are parse-safe with the demo OFF (default-off startup is
  unchanged); when enabled, all four are REQUIRED (fail-closed
  `demo_web_misconfigured`, no value echo). `copy_engine_url`
  enforces the closed `demo_snap_<20hex>` name law BEFORE any
  interpolation.
- `create_demo_app` now enforces the SAME `_validate_enabled()`
  law for a directly supplied enabled config as for the env source
  (the pre-report review gap is closed and unit-tested).
- `CopyReader`: per-request `NullPool` engine (a fresh connection
  per checkout, disposed after use — logout/cleanup is never held
  by an idle web pool). Deterministic private-only contract:
  explicit `connect_args={"ssl": False}` plus a bounded asyncpg
  connect timeout (10 s) and a 10 s server-side `statement_timeout`.
- The whole preview read is ONE database-side READ ONLY
  transaction: `conn.begin()` → `SET TRANSACTION READ ONLY` as the
  first statement of that transaction (verified with
  `current_setting('transaction_read_only') == "on"`), then
  `current_database()` MUST equal the bound copy name (a wrong or
  stale binding refuses without exposing either name), then the
  fixed reviewed allowlist
  `COPY_PREVIEW_TABLES = (owners, gateway_keys, provider_configs,
  model_routes, usage_ledger, audit_log)` is counted with strict
  `count(*)`. A missing table means a malformed copy and fails
  closed — it is not reported as absent.
- No request-derived or unknown table name, raw row, DSN,
  credential or error detail ever leaves the object: `read`
  returns only the fixed six-table allowlist count mapping (its
  keys are module constants, never request input), and every
  failure path raises the ONE safe `DemoWebError("
  copy_binding_unavailable")`. `close()` always attempts disposal
  and wraps raw driver errors in the same safe error: a disposal
  failure can never leak a raw exception, and an otherwise
  successful read surfaces as that safe refusal (the one safe
  note), never as a raw detail (unit-tested).

### 3.3 The read-only preview page (`/fakeadmin/copy-preview`)

- Zero enabled accounts → 404 (the every-route law, unchanged).
- The session token is resolved through `validate_session`, and the
  RETURNED projection is the authoritative request/account binding
  (live account/generation fence); the stored request row must
  match that binding (`id` AND `account_id`), be
  `verified_unpublished` and unexpired (`_copy_readable_now`).
- Reader construction AND the read run inside ONE safe-error
  boundary: a malformed stored copy name, driver failure, stale or
  dropped copy renders the single safe note, never a 500 and never
  the target name/DSN/internal error.
- The response is `Cache-Control: no-store` (the browser cache must
  not retain demo facts after logout) and renders either the six
  bounded counts or the safe note, plus the fixed "Full GUI
  browsing is not enabled yet" statement, a back link and the
  logout form. The ready page links to the preview and still states
  full GUI browsing is not enabled.

### 3.4 The preview template

- `demo/copy_preview.html`: the counts table carries the structural
  ordinal law (first-position `data-ordinal` header,
  `row-ordinal` first cell, exactly one authored data row + one
  fixed `data-no-sort` empty-state row with matching colspan), the
  `data-sortable` annotation and loads the shared fixed
  `table-sort.js` (same static directory the page already uses for
  `admin.css`), so the sortable headers behave exactly like the
  ordinary admin tables. No other template or page changed its
  behavior.

### 3.5 The order-mandated c-head fixes (same PR)

- `demo/login.html`: concise useful hints with `aria-describedby`
  on the username and password fields (pattern copied from the
  ordinary admin login page; visual style, CSRF and form behavior
  preserved) — closes the only c-head CI Unit failure.
- `tests/unit/test_demo_web.py` Code Quality hygiene: the five
  remaining threads fixed by dropping only the dead `r`
  assignments (three overwritten + two unused), keeping every call
  and assertion; no assertion was weakened.

### 3.6 Operator docs

- `docs/demo-admin.md`: new "Demo verified copy reader" section —
  secret-safe role provisioning (`CREATE ROLE … LOGIN;` +
  interactive `\password`; NO literal password example that could
  enter psql history), the worker grant law (role precheck, one
  transaction, prompt `failed` mark on handoff refusal with the
  bounded reap backstop, DROP-removes-grants, `cleanup_pending` on
  failed removal), the web reader law (per-request bounded
  read-only session, no TLS stage boundary — a trusted private
  network is required), safe rollback (drop the copy/role; revoke
  the config), and the still-incomplete status. The 224-b
  copy-uniqueness paragraph was updated for the prompt-failure
  behavior.
- `docs/configuration.md`: `DEMO_SNAPSHOT_TARGET_READER_ROLE` and
  the four `DEMO_WEB_COPY_*` settings with the behavioral law.
- `docs/cli-reference.md`: the grant runs inside the existing
  `process-request` (NO new CLI command); the preview lives in the
  standalone web process.

## 4. Evidence (this stage)

- **Unit** (fake-facade DI; no database): **500 passed** in the
  9-file suite — `test_demo_admin_accounts.py` (43),
  `test_demo_snapshot.py` (42), `test_demo_snapshot_files.py` (68),
  `test_demo_snapshot_sanitize.py` (66), `test_demo_web.py` (70),
  `test_demo_web_control.py` (28), `test_demo_web_worker.py` (41),
  `test_documentation_inventory.py` (16),
  `test_admin_usability_inventory.py` (126). New 224-d coverage:
  `test_demo_web.py` +16 (copy-config law incl. off-bootable
  garbage and the direct-enabled-config-missing-copy-binding
  refusal, `copy_engine_url` closed law, CopyReader ctor refusal,
  dispose-failure-safe close, preview: session required/bounce+
  clear, zero-active 404, unverified safe-note, expired safe-note,
  verified counts + no-store + canary-free + exact factory arg,
  malformed control-row name safe note via the REAL factory,
  reader-failure safe note, wrong-account binding safe note,
  disabled-account bounce); `test_demo_web_worker.py` +7 (grant
  success proves the single BEGIN/COMMIT transaction on the exact
  DB + the closed law; missing role; privileged/member role
  precheck `"0"`; target-admin reuse refused before any psql;
  transaction failure; malformed target name before any psql;
  `process_request` grant failure → `WEB_READER_GRANT_FAILED`, no
  handoff, failure recorded promptly).
- **Owned PostgreSQL 16** (real restricted roles on the owned
  source/target pair, synthetic data only, run-owned teardown with
  residue asserted — zero leftover roles and zero `demo_snap_%`
  databases after every module):
  - `tests/integration/test_demo_web_copy_reader_postgres.py` —
    NEW, 3 tests, exit 0, on the REAL static reader role (LOGIN,
    no privilege bits, no memberships):
    (1) `test_copy_reader_full_cycle`: pre-grant DENIAL — the
    reader cannot CONNECT to a raw (unverified) 221 copy; real
    221+222+223 chain → verified + granted → reader SELECT works
    while INSERT/UPDATE/DELETE/CREATE are refused by the database
    (42501) and any source-cluster connect is refused; the preview
    renders the six counts with `no-store` and no canary; a second
    session gets a DISTINCT copy — a marker row planted in copy one
    (as target admin) is visible to session one (+1) and NOT to
    session two; a control row pointed at the raw ungranted
    database renders the safe note (wrong-copy fails closed); both
    sessions are revoked before cleanup and the exact worker
    `cleanup` drops BOTH bound copies with rows `cleaned` and the
    reader can no longer connect (dropped/42501); source business
    counts are EXACTLY invariant (the seeded fake-admin account
    lives in `demo_control`, never in a counted table); no
    credential/DSN/copy-name canary in worker CLI output, preview
    HTML, or the web-role request projection
    (`to_safe_dict`, asserted locator-free and canary-free in
    serialized form for both bound requests).
    (2) `test_grant_failure_no_publication_exact_cleanup`: worker
    pointed at a NON-EXISTENT reader role → role-law precheck
    fails closed (`WEB_READER_GRANT_FAILED`), row `failed`, zero
    sessions, the created copy is never bound/published, the
    reader cannot connect it, and the exact cleanup drops it with
    the row `cleaned` and no survivor.
    (3) `test_schema_grant_failure_rolls_back_connect`: the role
    law PASSES but the copy's `public` schema is removed (221 ACL
    law mirrored: PUBLIC CONNECT revoked), so `GRANT CONNECT`
    succeeds and the next `GRANT USAGE ON SCHEMA public` fails —
    the real grant step raises the one safe code and the whole
    transaction rolls back: zero shared-catalog (`pg_shdepend`)
    grant entries for the role on that exact database, and the
    reader cannot connect at all. No partial grant can make a
    malformed copy readable.
  - `tests/integration/test_demo_web_worker_postgres.py` — 11
    tests, exit 0, re-run with the 224-d wiring: the module's
    run-owned ROLES now include ONE static reader role on the
    owned TARGET service (created in `_wenv_base` setup, dropped in
    teardown), and the worker env carries
    `DEMO_SNAPSHOT_TARGET_READER_ROLE`. Teardown order is exact:
    it selects ONLY the databases carrying a grant to THIS module's
    role (`pg_shdepend` classid `pg_database`, refclassid
    `pg_authid`, refobjid the role, plus the closed
    `^demo_snap_[0-9a-f]{20}$` name grammar — no prefix sweep),
    drops them, then drops the role and asserts both gone; this
    closes the `DependentObjectsStillExist` teardown failure a
    retained (correctly refused) copy caused.
  - `tests/integration/test_demo_web_postgres.py` (224-c
    regression) — 3 tests, exit 0 after the direct-config
    validation law: its web config now carries the copy-reader
    binding (owned target endpoint under the run-owned reader
    role; validation-only values, the 224-c tests never open a
    copy connection) and its worker env the reader role.
- **Scoped hygiene**: `ruff check` clean on all eleven touched
  Python files (repo policy, no extra flags); `git diff --check`
  clean.
- **Skips, honestly recorded**: the broad 222/223 legacy
  integration chains were NOT re-run locally beyond the modules
  above (per root direction in the b/c rounds); hosted CI covers
  the full matrix on the final head. The pre-existing environment
  failure `test_alembic_fresh_upgrade_postgres.py`
  (testcontainers/psycopg2) was not encountered in these runs and
  is not touched.

## 5. Honest limitations (unchanged product posture)

- The demo remains NOT usable for company demonstrations: the
  browser surface is still entry + wait + ready + the ONE
  read-only counts preview. The copy-backed admin GUI behind a
  server-side mutation gate, sanitized file-backed panels,
  no-op actions, installed browser evidence and final delivery are
  later same-PR suffixes.
- The copy reader has NO verified TLS stage boundary: the config
  sets explicit `ssl=False` and REQUIRES the trusted private
  network (documented); a remote DB over TLS is out of scope for
  this stage.
- The login attempt bound is an in-process bounded window (the
  224-c law), not a distributed rate limit.
- The publication grant runs inside the worker
  `process-request` chain under a finite 30 s deadline; there is no
  separate grant-retry command.
- The 224-b owned-PG fixture creates its reader role on the owned
  target service per module run (run-owned, residue asserted); the
  production operator provisions ONE static role once
  (docs/demo-admin.md).

## 6. Protocol state

- Branch `oap/224-demo-web`: activation commit `97e9e862`,
  implementation head `155851d0`, this report-only SELF on top
  (sole diff: this file). Remote PR383 head before this push was
  the 224-c SELF `dc128eb9`; after the push it is this report
  commit.
- `oap/active` = `224-d`; order SHA256
  `a8c196742f85de4ffa748af58d81d334a1b6da5240e600d89baa113cdae1fe1b`;
  this report's SHA256 is recorded by the root's independent
  verification.
- Protected untracked files retain their Section-1 hashes; no
  merge, no release, no demo deployment; the coding agent never
  merges. Root owns final-head CI, review and merge, and continues
  the same PR. Objective 225 stays inert.
