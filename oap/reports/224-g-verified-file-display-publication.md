# OAP 224-g Report — verified file display publication

Objective 224, PR #383 `oap/224-demo-web`, AMEND_EXISTING_PR.
Order SHA256 `09ecbff83f8e1e69b857021842374ef6a7e9b8b83690997cb652145818af1669`;
`oap/active` = `224-g`. Implementation commit
`1dca080d8121c58fe416b6f7ff64cf044614d601` (sole parent of this
report-only SELF). Remote main remains
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`; PR383 stays OPEN and
unmerged. 224-a..f orders and reports are unchanged and immutable.

## 1. What this suffix does

The session-bound SELECT-only copy reader now reaches the 223-verified
sanitized file display leaves through the TARGET DATABASE, never the
worker file system:

* **Worker ingest (target-only).** After the complete 224-b
  worker-held re-proof (combined 222 + 223: job/request/target
  identity, exact files tree, digests) and BEFORE the 224-a verified
  handoff, the worker opens ONE bounded transaction on the exact
  disposable copy: `CREATE SCHEMA demo_display` + one `leaves`
  table, then streams ONE re-proven leaf at a time (the shared 223
  anchored no-follow re-proof, refactored into a one-leaf-at-a-time
  generator with no 4-GiB aggregate in memory) through parameterized
  `INSERT`s, and commits ONLY after the generator is fully exhausted
  (its final handle name-binding and deadline checks have run). Held
  descriptors are always released (even on a mid-iteration driver
  failure); a failed/torn transaction rolls back completely, leaving
  NO published table, and the request fails with the finite safe code
  `WEB_DISPLAY_INGEST_FAILED` into the exact request-associated
  cleanup state (the drop of the bound target database removes the
  schema and every grant with it).
* **Closed display law.** The private files manifest `logical_name`
  is never copied into the browser-readable index on body-proof alone:
  every entry must match the CLOSED per-kind grammars the 223
  producers can emit (per-copy keyed run/job/upload ids or fixed
  vocabulary only), with duplicate-name, unknown-kind, over-length,
  exact-byte-count and bounded-capture-time checks. The table stores
  ONLY the closed safe index fields (`logical_name`, `kind`, display
  `sha256`, `byte_count`, `captured_at`) plus the sanitized `bytea`
  body. The private manifest fields (`source`, `source_ref`,
  `source_sha256`, inode identity, on-disk leaf names) never enter the
  copy.
* **Grant.** The existing static reader role receives `USAGE` on
  `demo_display` and `SELECT` on its one leaves table in the SAME
  atomic per-copy grant transaction as CONNECT + public SELECT; a
  missing/incomplete schema rolls back the whole bundle (no partial
  CONNECT survives). No DML/DDL, no `PUBLIC` grants.
* **Web reader.** A small request-bound, SELECT-only
  `DisplayReader` (existing `DEMO_WEB_COPY_*` credentials; closed
  `demo_snap_<20hex>` binding; database-side READ ONLY transaction
  with verified `transaction_read_only` + `current_database()`;
  finite row bound; per-request engine disposed after use; no
  filesystem, no worker module import, no source/owner connection, no
  app-global per-visitor state) backs the new
  `/fakeadmin/files-preview` page, which lists ONLY safe bounded
  metadata (logical name, kind, byte count, capture time) as a proof
  of binding. Every response is `no-store`. No file body is rendered
  from a URL in this suffix and no download endpoint exists; a future
  internal method may retrieve one validated leaf body for the later
  panel adapters.
* **Pre-upgrade behavior.** Existing pre-upgrade verified sessions
  whose copies predate this stage have no `demo_display` schema:
  their already-authorized DB-only pages keep working until expiry,
  and the new files preview fails closed for them (safe note). New
  logins after this stage get the full display publication.
  Documented in `docs/demo-admin.md`.

## 2. Scope and boundaries

* No schema change on the source or ordinary gateway DB; the
  `demo_display` schema is target-only and disposable with the copy
  (never in the 222-verified `public` inventory).
* No new CLI command, no new settings (the ingest reuses
  `DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES` /
  `DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES` and the file-job elapsed bound
  as its ONE finite deadline; the reader reuses `DEMO_WEB_COPY_*`).
* 224-f `/admin` admission and every unsafe no-op are unchanged; NO
  file-backed admin panel is mounted yet (later 224 suffixes wire
  them on this publication). `main.py`, ordinary admin
  routers/templates, 0028, provider adapters, quota/accounting,
  Compose/Nginx untouched.
* Storage tradeoff (documented): the sanitized bytes are duplicated
  in the target DB until the copy is dropped - bounded by the
  existing 223/224-b limits (default ≤ 512 MiB across ≤ 4 retained
  copies; configured upper ≤ 16 GiB before PostgreSQL storage
  overhead). Operator target-disk sizing is documented; a capacity or
  deadline failure fails the login closed, never partial file data.

## 3. Evidence

### f-head CI (inspected before publication)

The f-head (224-f SELF `ac59ae3af40f54b807243160bc80a31d6c3d8e66`)
hosted run `43425865747` COMPLETED SUCCESS: Unit/lint/migration head,
OpenAI-compatible E2E, PostgreSQL integration, Playwright browser
smoke, Docker Compose smoke and Documentation hygiene all green. No
direct f-head defects required repair on this PR.

### Focused unit (mocked; no database)

* `tests/unit/test_demo_web_worker.py` — 52 passed (41 prior + 11
  new): the closed per-kind display-name law (all positive shapes;
  foreign/traversal/unknown-kind/wrong-kind/over-length refusals);
  ingest happy path projecting ONLY the closed safe fields (private
  manifest fields asserted absent from every SQL parameter);
  duplicate-name, unknown-kind, illegal-name, changed-leaf,
  main-manifest count drift, invalid capture time and already-elapsed
  deadline refusals (each rolls the transaction back); foreign
  job/request and malformed target name before any DB work; the grant
  transaction carrying the `demo_display` USAGE + SELECT statements
  atomically; the process-request ingest-failure path (no grant, no
  handoff, failure recorded).
* `tests/unit/test_demo_web.py` — 102 passed (93 prior + 9 new):
  DisplayReader closed-name law and safe dispose wrapping; the
  files-preview route/session law (login bounce, forged token,
  zero-active 404, unverified/expired/wrong-account safe notes with
  the reader never constructed, verified metadata-only rendering with
  `no-store` and no copy name/DSN/credential/body in the page,
  pre-upgrade reader-failure safe note, disabled-account bounce).
* `tests/unit/test_demo_snapshot_files.py` — 68 passed (unchanged
  suite re-run once because the shared 223 re-proof was refactored
  into the one-leaf-at-a-time generator; the law is single-sourced).

### Owned PostgreSQL 16 (real source/target pair, owned fixture)

* `tests/integration/test_demo_web_worker_postgres.py` — 14 passed
  (11 prior + 3 new 224-g):
  * a fully DB+files-verified job publishes the EXACT closed leaf
    set: the target table equals the worker's own re-proven custody
    name-for-name (the configured branding + completion-profile
    sources pin `branding/logo` and
    `profiles/completion-choices.json`); the table carries only the
    closed safe columns; worker-private values (control password,
    custody path, passfile path, source database, copy name) are
    absent from every stored body; the real reader role is denied
    INSERT/UPDATE/CREATE TABLE/CREATE SCHEMA (42501);
  * a raw, never-verified copy has NO reader CONNECT grant and NO
    display schema in either its raw or DB-only-sanitized state;
  * a torn ingest transaction (real rollback on the real copy) leaves
    NO published table while an unrelated session-live copy is
    untouched, and the exact request-associated cleanup drops only
    the failed copy and marks it cleaned;
  * a leaf changed after 223 verification refuses publication before
    ingest and grant (no display table, no reader grant; the failed
    row keeps its worker columns NULL by design, ownership resolved
    from the private custody manifest).
* `tests/integration/test_demo_web_admin_gate_postgres.py` — 2
  passed (directly affected: its chains run the new ingest inside
  `process_request` on real PG).
* `tests/integration/test_demo_snapshot_files_postgres.py` — 1 passed
  (directly affected by the shared re-proof generator refactor).

Unchanged suites were not rerun locally (224-a control PG, copy-
reader PG, normal-admin regressions, prior 224-e/f browser smoke):
hosted CI on the final head covers them.

## 4. Verification contract status

* Raw/DB-only copies have no readable `demo_display` — proven (real
  PG, both states).
* Exact fully verified job publishes the complete closed
  leaf set/digests under the real reader role — proven (real PG).
* Private manifest/source canaries absent from the target table,
  HTML, JSON, CLI errors and logs — proven (table body/name scan on
  real PG; unit asserts private fields never projected into SQL;
  preview page renders metadata only; worker output vocabulary
  unchanged and code-only).
* Reader DML/DDL, source-cluster and wrong-session/copy reads denied
  — proven (real PG 42501 matrix; wrong-copy CONNECT refusal;
  wrong-account session binding refused at the control level in unit
  evidence).
* Concurrent sessions get distinct safe file projections — the static
  reader role is granted per copy and each web session is bound to
  exactly its own verified copy's name (control-level exactness
  proven in unit evidence; per-copy grants proven in real PG).
* No source business row, audit, quota, mail or provider effect — the
  ingest is a target-only transaction and the web reader a
  database-side READ ONLY transaction; no source/ordinary-DB write
  path was added.
* Injected failures (leaf changed after verification, torn ingest,
  grant path unchanged, handoff path unchanged) — no
  browser-authoritative partial display; exact cleanup removes the
  right DB/custody with no unrelated copy touched — proven (real PG).
* Default and configured resource bounds / no 4-GiB allocation /
  safe error codes and rollback — proven (one-leaf-at-a-time
  streaming, per-leaf/aggregate bound checks, finite deadline,
  `WEB_DISPLAY_INGEST_FAILED`).
* Preview with a sanitized fixture leaf and no-store — proven (unit
  ASGI evidence on the metadata page).

## 5. Limitations (honest)

* File-backed admin PANELS are still unmounted: 224-g is the bounded
  publication/reader foundation; a later 224 suffix wires the panels
  (and any single-leaf body retrieval) on this schema. Objective 225
  remains the installed acceptance gate. The demo is NOT usable for
  company demonstrations.
* The demo web entry is default-OFF and is a bounded preview, not a
  production feature. The control/copy connections use an explicit
  `ssl=False` stage boundary (trusted private network only); no TLS
  guarantee is claimed or provided.
* Pre-upgrade verified sessions keep DB-only pages until expiry and
  see a safe note (not file data) on the new files preview; this is
  the documented upgrade behavior, not a defect.
* The target database duplicates the verified sanitized file bytes
  until the copy is dropped (bounded; operator target-disk sizing
  documented).

## 6. Protocol state

* Implementation commit `1dca080d8121c58fe416b6f7ff64cf044614d601`;
  this report is its sole diff (report-only SELF).
* f-head CI terminal result: SUCCESS (all jobs), inspected before
  publication.
* Protected untracked files verified by hash only, unmodified:
  `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`.
* The 224-a..f orders and reports are unchanged and immutable.
