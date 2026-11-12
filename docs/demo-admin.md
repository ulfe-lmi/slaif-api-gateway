# Demo fake-admin accounts (objective 220 foundation)

> **Status:** Foundation — DISABLED until later objectives complete
> **Scope:** CLI-managed demo fake-admin control and isolated schema only
> **Authority:** This page plus [`database-schema.md`](database-schema.md)
> sections 5.26/5.27 and the [`cli-reference.md`](cli-reference.md)
> demo-admin section.

This page documents the objective 220 foundation of the fake-admin
demonstration feature. It is a foundation stage only: the complete
authorized feature (a fresh source snapshot after each successful
fake-admin login, a wait page, identity masking while real usage
patterns remain, a private disposable copy, silent no-op operational
actions, zero-active-account 404, and logout/expiry cleanup) is owned by
later objectives. This PR ships NO fake-admin login route, NO public
demo application, and NO Nginx/Compose profile: on the default live
gateway, `/fakeadmin/login` returns 404.

## What this foundation implements

- A dedicated `demo_control` PostgreSQL schema, fully separate from
  `admin_users`, `admin_sessions`, and every business table.
- Two tables: `demo_control.fake_admin_accounts` and
  `demo_control.fake_admin_account_events` (safe append-only events).
  See [`database-schema.md`](database-schema.md) sections 5.26/5.27 for
  exact columns, constraints, and indexes.
- One backward-compatible Alembic migration,
  `0027_demo_admin_accounts` (successor of `0026_request_diagnostics`).
  Upgrade creates the schema and tables; downgrade drops them and
  `DROP SCHEMA demo_control`. **The downgrade is destructive for
  CLI-created demo state** (password hashes and event history are
  deleted); back up and review before downgrading past this revision.
  Ordinary gateway business tables are unaffected in both directions.
- The trusted operator CLI group
  [`slaif-gateway demo-admin`](cli-reference.md#demo-fake-admin-control-objective-220-foundation)
  with bounded `create`, `list`, `enable`, `disable`, and
  `reset-password` commands — the ONLY writable path for these tables.

## What this foundation does NOT implement

- No HTTP endpoint creates, resets, enables, disables, or lists
  fake-admin credentials; no fake-admin login route exists yet.
- No session platform. `credential_generation` is only the
  monotonically increasing fence (bumped on reset/disable/enable) that
  the later session layer will use to invalidate stale sessions.
- No GUI, no demo web application, no Nginx/Compose profile, and no
  real demo credentials anywhere in fixtures or documentation.
- No changes to normal admin authentication, admin roles, quota or
  accounting law, provider/Codex/client modules, replay ownership,
  default content storage, or inference routes. A fake-admin row can
  never authenticate through the existing `/admin/login` path, which
  reads `admin_users` only.

## Security law of the control path

- Passwords exist only as salted Argon2id hashes (the existing password
  primitive); plaintext is never persisted, listed, logged, or
  displayed.
- Password input is via hidden confirmation prompt or `--password-stdin`
  (one bounded line, at most 128 characters; extra data refused). There
  is no `--password` argv option, so credentials never appear in argv or
  process listings.
- Documented strong minimum for publicly reachable demo accounts:
  16..128 characters. Credential-shaped usernames, passwords, or audit
  reasons are refused with fixed safe messages that never echo the
  value.
- Every account change is ONE owned PostgreSQL transaction: the state
  change and one safe append-only event (bounded reason, no secret)
  commit or roll back together. A failed late event/write rolls back the
  account change. Repeat enable/disable is a defined idempotent no-op
  with no event and no fake success audit. A password reset never
  re-enables a disabled account.
- Disabling the last active account makes the database-side active
  account count zero immediately; the later demo login layer uses
  exactly that fact to answer 404.
- CLI failures emit fixed safe errors only: no raw DB URL, password,
  hash, or user-supplied secret in stdout/stderr/JSON/audit/OAP
  artifacts.

## How the later demo service will use the restricted role

The migration creates NO roles and grants NOTHING. When the later demo
web application lands, the operator bootstraps a dedicated PostgreSQL
role (e.g. `demo_web`) with exactly these least-privilege grants:

```text
USAGE on schema demo_control
SELECT on demo_control.fake_admin_accounts
```

That role receives NO INSERT/UPDATE/DELETE on the account or event rows,
NO SELECT/DML on any business table, and NO source-provider
credentials. Narrow future session/job-table grants may be added by the
later objectives only after those tables exist.

Scope of this CONTROL role, stated precisely:

- It cannot read any production business table and cannot mutate or
  delete accounts or events: a compromised fake-admin browser reaches no
  production business state through this role.
- The table-level `SELECT` on `fake_admin_accounts` does include the
  salted Argon2id `password_hash` column, because the later demo login
  authenticates against it. A compromised web PROCESS holding this role
  could therefore read those hashes (offline attack material only, by
  design of salted Argon2id); the HTTP layer must never expose the hash
  (or any credential material) to the browser.
- This control role is separate from the later snapshot database read
  role, which will read the identity-masked copied business data of the
  private disposable copy (a later objective).

Bootstrap instructions must never print a live DSN. The normal admin
application does NOT use this role.

## Verification boundary of this stage

The foundation is verified by focused unit tests (CLI/password/
credential-leak oracles) and real owned-PostgreSQL-16 integration
evidence (migration upgrade, account lifecycle, the restricted-role
privilege boundary, duplicate/disable/reset behavior, no-write
refusals, transactional late-failure rollback, and safe CLI output).
There is no new GUI yet, so no browser feature qualification is claimed.
The full fresh-snapshot/no-op demonstration UX remains a later
objective and is not silently complete.

## Demo snapshot worker (objective 221, worker-only)

Objective 221 adds the SECOND bounded stage of the fake-admin demonstration:
a fresh, consistent business-data snapshot of the live PostgreSQL, exported
with `pg_dump` and restored as a NEW UNIQUE database in a SEPARATE demo
PostgreSQL service. This stage owns raw snapshot creation, custody,
resource limits and cleanup ONLY.

### What this stage is NOT

- No demo browser authentication and no `/fakeadmin/login` behavior
  (objective 224).
- No data masking and no file-backed panel capture (objectives 222/223).
- No public demo is available: a completed copy is recorded in the explicit
  `RAW_UNVERIFIED` custody state that no web reader can mistake for
  published. The complete demonstration requires 222 + 223 sanitization
  and verification AND 224 browser binding before any use.
- No generic job framework, queue or scheduler: one worker invocation per
  future login, driven by the operator (later: the 224 login flow).

### Trust boundaries

- **Worker-only surface.** There is no API route, admin template or web role
  that can invoke or read the raw copy. The CLI group
  `slaif-gateway demo-snapshot-worker` is the ONLY entry point.
- **Read-only source.** The snapshot connects to the live business database
  as a dedicated SELECT/USAGE-only role on the business schema. It cannot
  DML, cannot read `demo_control`, and never receives provider credentials:
  the PG client tools run with a minimal explicit environment that contains
  no provider or application variables. The dump is limited to the business
  `public` schema by a positive allowlist (`pg_dump --schema=public` plus
  the two fixed approved extensions), so `demo_control` can never enter
  the archive.
- **Separate target service.** The raw copy is a new unique database
  (`demo_snap_<id>`) created on a separate demo PostgreSQL service — never
  `CREATE DATABASE ... TEMPLATE` against the live source, and never a new
  server process per demo account. The copy is created CLOSED
  (`ALLOW_CONNECTIONS = false`); while closed the worker revokes `CONNECT`
  from `PUBLIC` and grants it only to the configured target user, and only
  then reopens the database — so there is no window in which a web role can
  connect. The single dump archive carries the business `public` schema
  plus the fixed trusted extensions required by migration 0001
  (`pgcrypto`, `citext`, selected explicitly by name), and is restored
  into the fresh empty database with `--clean --if-exists`; no broader
  schema or extension set is ever installed.
  The worker re-verifies the separate-service contract before EVERY
  create: if the target host/port is the source endpoint, or a bounded
  `pg_database` catalog query on the target service reports a database
  named `DEMO_SNAPSHOT_SOURCE_DATABASE` (or the check cannot be
  verified), the job fails closed with `TARGET_NOT_SEPARATE` before any
  `CREATE DATABASE`.
- **No PG client tooling by default.** The normal API image and default
  deployment do NOT include `pg_dump`/`pg_restore`/`psql`. Build the
  optional worker target for them:
  `docker build --target demo-snapshot-worker .` (pinned PostgreSQL 16
  clients; prove with `docker run --rm <image> pg_dump --version`).
- **Secrets.** Source and target passwords come from a restrictive
  `PGPASSFILE` (0600), never argv or logs. The raw target database name,
  archive path, DSNs and passwords are redacted from all CLI output, logs
  and reports.
- **Custody.** Job state lives in an operator-owned `0700` directory
  that the setup requires OUTSIDE the repository and databases (an
  operator requirement — the worker enforces the no-symlink and
  owner-only `0700` boundary, not repository exclusion); every artifact
  (manifest, dump, stderr tails) is `0600`. Symlinked or
  group/world-accessible custody roots are refused. The custody
  manifest is the durable private record
  that stages 222/223/224 address by `target_db` — deliberately a file,
  not a PostgreSQL table, so the SELECT-only source role can never read or
  influence bookkeeping.
- **Limits.** A finite per-job export byte cap (streamed and counted; the
  dump is SIGKILLed as a process group before a complete claim can exceed
  it), an elapsed-time cap that is ONE absolute deadline shared by
  create, dump and restore (no phase spends a second full budget), a
  race-safe single-worker cross-process fence (kernel `flock`, released
  automatically when the worker dies), retention expiry and a finite copy
  budget. An incomplete dump is never marked complete; every failure leaves
  a safe finite code and no browser-readable artifact.

### Operator setup (all optional; default OFF)

1. Target service: a separate PostgreSQL 16 instance with a dedicated
   target user (password in the PGPASSFILE). No business databases.
2. Source role on the live business database:

   ```sql
   CREATE ROLE demo_snap_reader LOGIN PASSWORD '<restricted-password>';
   GRANT USAGE ON SCHEMA public TO demo_snap_reader;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO demo_snap_reader;
   -- No grants on demo_control, no DML, no provider credential paths.
   ```

3. Custody directory: `mkdir -m 0700 /var/lib/slaif/demo-snapshot`
   (outside the repository, on a bounded volume).
4. PGPASSFILE (0600), one line per endpoint:

   ```text
   <source-host>:<source-port>:<source-db>:demo_snap_reader:<restricted-password>
   <target-host>:<target-port>:*:<target-user>:<target-password>
   ```

5. Configure every `DEMO_SNAPSHOT_*` setting and set
   `DEMO_SNAPSHOT_ENABLED=true` (see Configuration → Demo Snapshot
   Worker). Missing or relative values refuse with a safe
   `SNAPSHOT_MISCONFIGURED`.

### Running

```bash
slaif-gateway demo-snapshot-worker run      # one bounded snapshot job
slaif-gateway demo-snapshot-worker expire   # retention + copy budget
slaif-gateway demo-snapshot-worker recover  # idempotent dead-worker cleanup
```

Output is a fixed safe vocabulary: state, finite failure code, export
bytes, elapsed milliseconds, custody copy count — never a database name,
DSN, password or row content. A successful run records exactly one
`RAW_UNVERIFIED` copy.

### Realistic source cost and failure behavior

A snapshot takes one consistent read pass over the business tables
(`pg_dump` holds its snapshot lock briefly and streams; concurrent writes
continue). Cost is proportional to business-data size plus compression
I/O; the byte cap bounds the transfer regardless. Dump or restore errors,
cap breaches, cancellation, crashes and restarts all: abort before any
complete claim, record a safe finite code, clean partial files and the
partial target database (`DROP ... WITH (FORCE)`), and leave the custody
manifest inspectable. If cleanup itself fails the manifest records
`CLEANUP_FAILED` (operator-only, inspectable) and `recover` retries
idempotently. Rollback is `expire`/`recover` plus removing the custody
directory contents; nothing in the business database is ever touched.

The file-backed capture of objective 223 will have its OWN capture
timestamp; the snapshot capture interval recorded here is not it.

## Demo database masking and verification (objective 222, worker-only)

Objective 222 adds the THIRD bounded stage: it sanitizes and
independently verifies the private PostgreSQL raw copy created by
objective 221 BEFORE any web role can read it. This stage owns the
complete copied-database field policy and the fictional identity
mapping. The live source PostgreSQL stays entirely read-only.

### What this stage is NOT

- No demo browser authentication, no login, no `/fakeadmin/*` behavior
  and NO public demo (objective 224).
- No file-backed panel capture and no demo web process (objectives
  223/224).
- No demo web role is created or granted in this stage; the copy stays
  readable by the worker target user only.
- `DB_SANITIZED_UNPUBLISHED` explicitly means the sanitized copy exists
  but file-backed verification (223) and browser binding (224) are still
  absent. The demonstration is not usable until 223 AND 224 complete.
- No migration, no business schema change, no provider/mail calls.

### Target service transport boundary

The sanitizer connects to the target copy database over asyncpg with
`ssl=False` (mirroring the objective 221 worker). Target PostgreSQL
traffic must therefore stay on a trusted private loopback or Compose
network; this stage does NOT support verified remote database TLS. Do
not point the target endpoint at an untrusted network.

### Masking policy (reviewed, fail-closed)

The sanitizer inventories the ACTUAL restored catalog (every public
user table, column, SQL type, nullability, extension and the complete
reviewed constraint set including the 64 FK definitions) and refuses
closed with `SANITIZE_SCHEMA_UNKNOWN` on any new table/column/type,
changed type/nullability, or constraint/FK drift — before any
modification. Row budgets (per table and total) are enforced before any
value materialization.

Every restored table/column has an explicit reviewed action: preserve
(`P`, descriptive quantities/times/costs/statuses/route-model-provider
choices), per-copy remap (`U` UUIDs with FK links preserved, `S`
string identifiers, `H` bare 64-hex for the CHECK-constrained replay
HMAC columns), NULL out free text (`N`), fixed fictional values from the
shipped `app/slaif_gateway/data/demo_identities.json` (`F:`/`FC:`,
including credential-invalidation dummies), and JSONB reduction (`J0`/`JA`
to fixed empty shapes, `JU` element-wise UUID remap, `JJ` only for
reviewed typed shapes that fail closed otherwise). Entity-bound free
text (owner/institution/cohort/org/team/project/budget/template/admin
names and emails, including denormalized usage/audit/email snapshots)
maps to fixed plausible fictional lists with per-copy unique, stable
assignments that stay consistent across all referencing rows and handle
more rows than list entries without collisions. The copied database
cannot authenticate or forward: key hashes, admin credentials/sessions,
MFA, one-time secrets and provider authority are invalidated, and the
verifier refuses any PUBLIC CONNECT grant (including the NULL/default
ACL case).

Two operator/client identifier fields are fictionalized rather than
preserved (222-c repair): `gateway_keys.key_prefix` (a configurable
source prefix that may carry an organization slug and renders verbatim
in the admin key list/detail and owner/institution/cohort key links) is
replaced with the fixed fictional demo prefix, and
`codex_replay_references.tool_namespace` (client/organization free text)
is replaced with a fixed fictional namespace — non-NULL for
function/custom tool rows and NULL for reasoning/compaction rows,
matching the `kind_shape` CHECK. The independent verifier re-proves both
values per row in addition to the whole-copy canary scan.

### Privacy limitation of the masked copy (explicitly accepted)

Masking is NOT irreversible anonymity. Usage quantities, timestamps,
costs, quota shapes and route/model/provider choices are preserved by
design so the admin read views stay realistic; the resulting activity
pattern of a copied account can still be recognizable. The human
maintainer explicitly accepted this limitation for the bounded demo.

### State machine and failure law

A copy advances from `RAW_UNVERIFIED` to the distinct private state
`DB_SANITIZED_UNPUBLISHED` only after BOTH a committed deterministic
sanitizer transaction AND a separate read-only verification (row
counts, preserved-value checksums, per-column invalidation law, and the
keyed per-copy remap aggregate for the HMAC columns) pass. A crash,
rollback, unknown schema, verifier failure, credential error, timeout or
cleanup failure leaves the copy `RAW_UNVERIFIED` with a safe finite
code (`SANITIZE_SCHEMA_UNKNOWN`, `SANITIZE_FAILED`,
`SANITIZE_VERIFY_FAILED`, `UNEXPECTED`) — never interpreted as
available. Repeated invocation is idempotent: sanitized copies are
skipped, failed copies are retried safely without re-exposing source
values, and each fresh copy is seeded by its own private job id so no
copy can reuse another copy's identity mapping or authority.
Retention/`expire` now covers sanitized-but-unpublished copies as well.

### Private operator inspect / retry / cleanup

Operate in this order: retry first, then drop the exact recorded
copies, and only remove custody files last — deleting the manifests
before `expire`/`recover` would orphan their target databases.

- Inspect: the private custody manifest (0600) records the exact state,
  failure code AND the exact target database name plus the private
  metadata the later stages and exact-copy cleanup address; the private
  pre-state file (0600) records the pre-rewrite budget/checksum
  evidence, including source-derived entity IDs and aggregate checksums
  the independent verifier needs. The custody directory must be
  configured OUTSIDE the repository and databases (an operator
  requirement — the worker enforces the no-symlink and owner-only 0700
  boundary, not repository exclusion); the custody files are
  operator-owned `0600` under the existing custody access and retention
  rules, and the raw dump/copy already exists in private custody. The
  private files are NOT sanitized and NOT public-safe — they may retain
  source-derived values — so never move, display, commit or attach
  them.
- Retry: re-run `slaif-gateway demo-snapshot-worker sanitize` (fenced,
  idempotent).
- Cleanup: `expire` and `recover` behave as in objective 221 and drop
  the EXACT recorded copies (never a prefix sweep). Rollback is that
  exact-copy cleanup followed by removing the custody directory
  contents. No business database is ever touched. CLI output, ordinary
  logs, reports and committed artifacts omit the target database name,
  secrets and source identifiers; that rendered-output law does not
  apply to the private custody files above, which intentionally retain
  them.

### 224 prerequisite

Objective 224 (browser binding/login) is inert until its own activation
and MUST complete before any demonstration use; this stage never grants
the demo web role and never exposes a public URL. Objective 223
(file-backed panel capture) is the following stage.

## Demo file-backed snapshot (objective 223, worker-only)

Objective 223 adds the FOURTH bounded stage: it captures the CLOSED set
of file-backed artifacts the admin GET/download routes can address,
replaces every identifying or free-text value with a reviewed typed
display projection, and independently re-verifies the resulting
display tree BEFORE the copy may advance. The live source — including
the catalog custody files — stays entirely read-only: the worker never
creates, modifies or deletes a catalog source file, and no original
seal/receipt/apply authority is ever copied into a demo artifact.

This stage is implemented and tested, but the demonstration as a whole
is NOT usable yet:

- Objective 224 (browser binding/login) is still required.
- KNOWN DB CAPABILITY LIMITATION (same-PR 223-b follow-up): the 222 DB
  sanitizer's JSONB law for `model_routes.capabilities` accepts only
  top-level boolean flags, while real route configuration/CLI supports
  nested blocks (`codex_limits`, `media_input_estimation`,
  `chat`/`responses`, `completion_service {version, profile}`). A source
  database containing routes with such nested capabilities FAILS 222 DB
  sanitization, which blocks the whole chain for that source. The 223
  FILE stage already carries the typed nested capability blocks (baseline
  documents), and the same-PR follow-up adds the matching typed,
  privacy-safe capabilities mapping to the 222 sanitizer before any 224
  browser binding. Until that lands, do not point the worker at a source
  whose routes use nested capabilities.

### What this stage is NOT

- No demo web process, no demo browser authentication, no login, no
  public demo (objective 224).
- No generic file-copy/ETL platform: only the closed, admin-addressable
  source families below, each with an explicit typed display projection.
  An unknown configured source shape FAILS the job closed; it is never
  copied through.
- No new framework, queue or scheduler: one bounded worker invocation
  over the existing 222 verified copies, under the same custody fence.

### Configured sources and their display projections

Every configured source is read through the held anchored no-follow
descriptor boundary (identity-rechecked, bounded reads; the worker
itself never re-opens a checked pathname). One documented exception:
branding slot selection reuses the EXISTING validated `resolve_slot`
resolver, which performs its own anchored no-follow open of the
configured slot path; before trusting the resolved bytes the worker
re-asserts the name binding of the held branding directory, and the
candidate PRESENCE itself was already inspected through the held
directory descriptor (a present non-regular or ambiguous candidate
fails closed before resolution). A configured source that is missing,
changed during capture, unsafe (mode/ownership), unreadable or
unrecognized fails the job with a safe finite code
(`FILES_SOURCE_MISSING`, `FILES_SOURCE_CHANGED`,
`FILES_SOURCE_UNSAFE`, `FILES_SOURCE_UNSUPPORTED`,
`FILES_SOURCE_TOO_LARGE`); unconfigured optional sources simply stay
unconfigured (recorded as such, neutral display substitutes where the
admin panel needs one).

| Source (operator setting) | What is captured | Display projection |
| --- | --- | --- |
| Catalog custody (`CATALOG_REFRESH_ROOT` + `CATALOG_REFRESH_SEAL_KEY`, both-or-neither) | The seven sealed-run content files of every retained run (authenticated through the existing seal seam), bounded job uploads, the six proposal artifacts, five per-package files (fixed product preset vocabulary) and the admin-visible job records. The seal key, manifest/receipt and locks are NEVER captured. | Typed per-kind projections: IDs remapped per copy (demo run/job/upload ids), free text (notes, progress, error detail, URLs) neutralized, capabilities against the closed catalog vocabulary, row-count maps against the four closed catalog table names, job records against the product's finite family/status vocabularies. |
| Branding (`SLAIF_BRANDING_DIR`) | The five fixed slots, selected by the existing validated resolution law. | EVERY slot displays the shipped neutral substitute (packaged logo / empty stylesheet); the operator's own CSS/images are recorded privately (name/type) and never copied. A present candidate the resolution law rejects (invalid content, ambiguous dual candidate, non-regular file) fails closed. |
| Completion profiles (`COMPLETION_SERVICE_PROFILE_DIR`) | Profile ID stems only (`<id>.json`, shared loader law); profile BODIES are never read. | A choice projection with per-copy fictional profile ids; the private custody manifest keeps the private stem map for link consistency. Group/world-writable or unreadable profile files fail closed. |
| Upstream LLM profiles (`UPSTREAM_LLM_PROFILES_FILE`) | The operator profile document (bounded size). | Typed projection: finite protocol fields preserved, operator profile ids fictionalized per copy, digest recomputed. |
| Packaged data + `PUBLIC_BASE_URL` | Nothing is copied. | Packaged Codex presets/profile/upstream-LLM defaults are referenced by pinned digests only; the operator `PUBLIC_BASE_URL` is recorded as a PRESENCE MARKER — its value never enters any artifact (stage 224 renders profile downloads against the demo hostname, not the live URL). |

### Resource bounds (worker-enforced, feature-local)

- Per-file byte cap `DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES`
  (default 32 MiB; 1–128 MiB) and aggregate byte cap
  `DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES` (default 128 MiB; 64 MiB–4 GiB)
  bound BOTH the raw admission (checked before any parsing) and the
  sanitized display bytes (checked before retention). Raw bytes are
  sanitized and discarded per file; only the bounded display leaves are
  retained.
- Finite file-count bound (4096 flat leaves per job) and one ABSOLUTE
  elapsed deadline per copy (`DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS`,
  default 300 s) shared by capture, write and verification. An
  over-budget copy is cleaned and refused — never published.
- The independent verifier enforces the SAME configured caps (bounded
  by absolute ceilings) on its re-reads; the untrusted manifest counts
  can only shrink a read, never raise a cap.

### State machine and failure law

A copy advances from `DB_SANITIZED_UNPUBLISHED` to
`DB_AND_FILES_VERIFIED_UNPUBLISHED` only after the display tree passes
the independent read-only verifier (exact flat leaf set under the job's
`0700` `files/` directory, per-leaf 0600 mode/size/digest/inode
identity, per-kind display policy re-proved, cumulative caps, deadline
re-checked before every leaf read and before a clean return). Any
drift, an unregistered kind, or a malformed manifest entry is
`FILES_VERIFY_FAILED`. Capture/write/budget failures keep the 222
state `DB_SANITIZED_UNPUBLISHED` and record `files_state: FAILED` with
a safe finite code (`FILES_BUDGET_EXCEEDED`, `FILES_WRITE_FAILED`,
`FILES_VERIFY_FAILED`, `FILES_CLEANUP_FAILED`) for operator inspection
and retry. Repeated invocation is idempotent: file-verified copies are
skipped; an interrupted prior attempt is cleaned EXACTLY (manifest-
recorded flat leaves only, through held directory descriptors, identity
rechecked, absence proven) before the retry — and a torn write that left
leaves without their manifest refuses cleanup and RETAINS the artifacts
for the operator.

### Display files, cleanup order and rollback

Display leaves are written FLAT under the job's private `files/`
directory (each `0600`, created `O_EXCL` through a held directory
descriptor; the private files manifest is written LAST, so a torn write
can never present leaves without their exact-leaf record). Cleanup
order is load-bearing: the 221 dump unlink and the EXACT target
database removal happen FIRST; the display files are removed only after
the target database is confirmed gone, so a failed DB drop keeps the
files and manifest available for retry. If exact-leaf cleanup cannot be
completed (foreign entry, identity drift, tampered manifest) the job
reports `FILES_CLEANUP_FAILED` and retains the artifacts — no broad
prefix or owner sweep is ever performed.

Operator procedure (same order as 222): inspect the private custody
manifest (0600; it retains the private source records, the private id
maps and the exact file inventory — never display/commit it), retry
`files`, expire/recover the exact copies, and only then remove custody
files. The private files manifest and pre-state files are NOT
public-safe; CLI output, ordinary logs and reports omit raw names, data
and credentials.

### Target transport boundary (unchanged from 221/222)

All target PostgreSQL traffic (221 restore, 222 sanitize, 223 state
checks) uses asyncpg/libpq on a trusted private loopback or Compose
network with `ssl=False`; this stage does not support verified remote
database TLS. Do not point the target endpoint at an untrusted network.

### Privacy limitation (explicitly accepted)

As with 222, the demo copy is a bounded realistic substitute, not
anonymous data: usage quantities, timestamps, costs, route/model/
provider choices and finite codes are preserved by design so the admin
read views stay realistic, while identity-bearing values (names,
emails, URLs, operator free text, seal authority, source code
revisions) are removed or fictionalized. The activity pattern of a
copied account can still be recognizable; the human maintainer
explicitly accepted this limitation for the bounded demo. The file
artifacts are DISPLAY-ONLY copies: they lose all original seal/apply
authority and are valid only as rendered panel data for the 224 binding.
