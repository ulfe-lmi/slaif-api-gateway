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
- ROUTE-CAPABILITY MASKING (objective 223-b): the 222 DB sanitizer now
  rewrites `model_routes.capabilities` with a route-specific typed
  transformation (action `RC`) that reuses the installed per-group
  parsers, so a non-empty nested capability document the normal
  configuration accepts is representable in the display copy when it uses
  only the eleven reviewed groups below. Those eleven are: the five
  boolean blocks
  (`chat_completions`, `responses`, `audio_endpoints`, `embeddings`,
  `realtime`), `codex_limits`, `media_input_estimation` and
  `vllm_chat_video` preserved as reviewed non-identifying
  booleans/numeric limits/finite codes; `codex_compaction_compatible_route_ids`
  is remapped entry-for-entry to the copied route ids (list order
  preserved); `completion_service.profile` is rewritten to the SAME
  per-copy fictional id the 223 completion-choices leaf uses, so a
  copied route links to exactly its captured choice; and the
  `external_tools` `approved_destination_ids` opaque names are remapped
  per copy (kind preserved). The independent 222 verifier re-proves the
  stored transformed document, and a combined DB/files gate fails the
  copy BEFORE publication if a copied completion profile does not link
  to the captured choices. Documented limit: the three preserved
  transport groups (`local_coding`, `local_coding_vllm`,
  `upstream_llm`) carry configuration secrets or operator transport
  references that cannot be safely projected, so a route using them
  FAILS 222 closed; unknown groups, unknown flags, wrong types and
  secret-shaped payloads also fail closed, exactly like the installed
  configuration law. The ordinary empty `{}` route remains supported.
  The 222/223 worker validates the capability-document grammar but does
  NOT run the full route-level `validate_merged_route_candidate` law
  (which additionally requires a loadable completion profile with
  matching models), so a synthetic completion-service route in the
  owned test fixture proves the DB/files link but is not asserted to be
  a fully route-validated installed candidate.

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
descriptor). The private files manifest is written LAST; a torn or
interrupted write can therefore leave leaves WITHOUT their manifest
(and no complete job is ever presented in that state — the copy
stays unverified, exact cleanup refuses, and the artifacts are
retained for the operator, as described in State machine and failure
law). Cleanup order is load-bearing: the 221 dump unlink and the EXACT
target database removal happen FIRST; the display files are removed
only after the target database is confirmed gone, so a failed DB drop
keeps the files and manifest available for retry. If exact-leaf
cleanup cannot be completed (foreign entry, identity drift, tampered
manifest) the job reports `FILES_CLEANUP_FAILED` and retains the
artifacts — no broad prefix or owner sweep is ever performed.

Operator procedure (same order as 222): inspect the private custody
manifest (0600; it retains the private source records, the private id
maps and the exact file inventory — never display/commit it), retry
`files`, expire/recover the exact copies, and only then remove custody
files. The private files manifest and pre-state files are NOT
public-safe; CLI output, ordinary logs and reports omit raw names, data
and credentials.

### Two snapshot times (not one instant)

A per-login copy combines TWO snapshots taken at different times: the
221 PostgreSQL `pg_dump` database snapshot (a consistent dump cut) and
the later 223 per-source file capture, which reads each configured
file source during the files run. These two snapshots are NOT
transactionally simultaneous; a value visible in a file source at the
223 capture moment is not guaranteed to match the database state at
the 221 dump moment (or vice versa). Both snapshot times are recorded
and inspectable in the private custody manifest (the 221
`capture_started_at`/`capture_finished_at`/`restore_finished_at`
fields and the 223 `capture_started_at`/`capture_finished_at` fields
in the private files manifest), so an operator can see exactly when
each half was taken. Do not describe the combined copy as a
single-instant snapshot.

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

## Demo control session foundation (objective 224-a, no HTTP yet)

Objective 224-a adds the PostgreSQL control foundation for the demo
administrator login and isolated snapshot UI: two tables in the existing
`demo_control` schema (`demo_snapshot_requests`, `demo_web_sessions` —
see `docs/database-schema.md` §5.28/§5.29) plus a finite,
transactional state machine in
`slaif_gateway.services.demo_web_control` with the reviewed
least-privilege grant matrix for the future web/worker control roles.
The migration creates NO roles and grants NOTHING; the grant SQL is
generated by the service for the operator at 224-b+ and role names are
validated against a closed identifier law before interpolation.

### What this stage is NOT

- There is still NO demo HTTP endpoint, no `/fakeadmin/login`, no
  browser, and no worker integration with 221/222/223. The demo is
  STILL UNUSABLE; 224-b+ must build the web route, the worker
  handoff, and the cleanup path on top of this foundation.
- No normal `/admin` auth change: fake-admin rows still cannot
  authenticate through `admin_users`-based login.
- No new business-table grants; no source-provider credential access.

### State law (finite reviewed vocabulary)

```text
request:  pending -> claimed -> verified_unpublished -> cleanup_pending -> cleaned
          pending/claimed -> failed (safe finite failure code)
          verified_unpublished/failed -> cleanup_pending
```

- `pending` is created by the web role with a COLUMN-LIMITED INSERT
  (the `state` column is not nameable by that role; the database
  default `'pending'` applies).
- `claimed` is reached only by the worker role's ATOMIC GUARDED UPDATE
  (compare-and-set on the current state): exactly one concurrent
  claimer wins; a late claim past `deadline_at` fails the row with
  `claim_expired`.
- `verified_unpublished` is reached only by the worker's verified
  handoff with the EXACT worker-held 223 binding (closed
  `snap-<32 hex>` job id + `demo_snap_<20 hex>` copy locator, both
  unique across all requests so two requests can never bind one copy)
  and the live account fence (enabled + recorded credential
  generation) rechecked IN THE SAME ATOMIC STATEMENT as the
  transition. Late completions fail with `late_completion`; a
  reset/disable mid-job makes the transition match 0 rows, so a stale
  worker result can never become browser-authoritative.
- `cleanup_pending`/`cleaned` are worker-owned (224-b): cleanup is
  refused while a live session binds the copy (unless the copy
  expired) and must proceed even after the account is disabled.
- Failure codes are a closed vocabulary (`claim_expired`,
  `late_completion`, `worker_failed`, `verification_failed`,
  `copy_mismatch`, `state_conflict`, `internal_error`); safe error
  messages never echo copy identities or other operator data (owned
  PG16 canary-echo negative).

Session law: at most ONE live session per verified copy (partial
unique index), issued only for a verified-unpublished, unexpired,
account-owned request with the matching generation; the session
expires exactly when the copy does; revocation is ONE atomic guarded
UPDATE of `revoked_at` (web role) and does NOT mutate the request.
The browser token is returned exactly once and only its SHA-256 hex
digest is stored (owned PG16 test: exactly one stored hash per issued
token, the raw canary absent from every stored value of all three
demo tables).

### Locking law (verified against the PostgreSQL 16 privilege docs)

Every row-locking read (`FOR UPDATE`/`FOR NO KEY UPDATE`/`FOR SHARE`/
`FOR KEY SHARE`) requires UPDATE privilege on at least one column of
the locked table (verified live on PG16: column-SELECT-only roles get
42501 on `FOR SHARE`; a role with one column's UPDATE may `FOR SHARE`).
Consequences, enforced by the implementation:

- The control service takes NO row locks at all. All reads are plain
  MVCC SELECTs; every transition is an atomic guarded UPDATE, the
  single serialization point (a `FOR SHARE` pre-read followed by the
  guarded UPDATE on the same row would deadlock under concurrent
  claimers).
- Neither role can row-lock `fake_admin_accounts` (column-SELECT
  only). The credential fence is therefore enforced
  STATEMENT-TIME inside the guarded claim/handoff CAS plus live
  rechecks in create/validate session on every use. Residual window:
  an operator reset in the instant between a session-issuance
  recheck and its INSERT can create a session row; that session is
  refused at its FIRST use by the per-use live account recheck, so a
  reset/disable still prevents any usable session (the web role's
  UPDATE-free request reads and the worker's guarded writes are the
  boundary).
- The worker role CAN `FOR SHARE` request rows (it holds column
  UPDATE on that table); the PG16 test proves that capability and the
  web role's denial, while the service itself remains lock-free.

### Role matrix (operator applies at 224-b+)

See `docs/database-schema.md` §5.28 "Reviewed 224-a role grant
matrix". In short: the web role gets a column-scoped account SELECT
(login hash check), request SELECT, a column-limited request INSERT
(state not nameable), session SELECT/INSERT and `UPDATE(revoked_at)`;
it has NO UPDATE on requests at all. The worker role gets the
account facts SELECT (never username/password_hash), request SELECT,
column-limited request UPDATE, and session revocation-facts SELECT
(never token_hash). Neither role has any business-table grant. The
owned PG16 test runs the REAL service methods under both restricted
roles and proves every forbidden surface is denied with 42501.

### Rollback

`alembic downgrade 0027_demo_admin_accounts` drops exactly the two 0028
tables; the schema and 0027 tables survive. The downgrade is
destructive for demo request/session state (see the schema doc). No
business table is affected in either direction.

### What 224-b supplies

The `/fakeadmin` login route on this foundation (web role), the
worker-side claim → 221/222/223 snapshot job → verified handoff
wiring, and the bounded cleanup path (file + target-database removal
after confirmed DB drop, manifest retention on failure) that consumes
`cleanup_pending`/`cleaned`.
