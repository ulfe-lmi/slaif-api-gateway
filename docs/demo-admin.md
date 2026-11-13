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
roles and proves every forbidden surface is denied with 42501. The
exact CREATE ROLE / GRANT statements for the operator are in the
224-b section below.

### Rollback

`alembic downgrade 0027_demo_admin_accounts` drops exactly the two 0028
tables; the schema and 0027 tables survive. The downgrade is
destructive for demo request/session state (see the schema doc). No
business table is affected in either direction.

### What 224-b supplies

The worker-side exact handoff ONLY: the private
`demo-snapshot-worker process-request` / `cleanup` worker commands
(claim → ONE fresh 221/222/223 copy → worker-held proof → verified
handoff; bounded session-aware cleanup), the structural verified-copy
eviction law, and the durable request→job association with crash-safe
recovery. No HTTP route in 224-b: the `/fakeadmin` login route,
session UI, and copy-backed demo reads are later suffixes of
objective 224 (224-c or later). The demo remains unusable from a
browser. See the 224-b section below.

## Demo exact worker handoff and cleanup (objective 224-b, worker-only)

Objective 224-b adds a purpose-built PRIVATE worker orchestration on
the 224-a foundation: one bounded CLI invocation that claims a
pending demo snapshot request, builds exactly ONE fresh
221→222→223-verified copy for it, proves the worker still holds that
exact artifact, and publishes the verified handoff; and one bounded
invocation that reaps stuck rows and cleans up exactly the artifacts
the request state machine has released.

### What this stage is and is NOT

- Worker-only. NO new HTTP route, NO Celery/Redis/queue, NO browser.
  The demo remains UNUSABLE from a browser: the `/fakeadmin` login
  route, session UI, copy-backed demo reads, no-op actions and browser
  qualification are later suffixes of objective 224 (224-c or later).
- NO migration: it runs on the 0028 schema of 224-a unchanged.
- NO generic cross-file identity engine: the per-copy ID laws of
  222/223 are unchanged.
- The worker connects to the control database with a dedicated
  worker-only role (`DEMO_WEB_WORKER_CONTROL_*`, see Configuration →
  Demo web worker control connection) — NEVER the owner
  `DATABASE_URL` credential.
- Legacy `run`/`expire`/`sanitize`/`files`/`recover` commands keep
  their existing contracts; the verified-copy eviction law below also
  binds them (fail-closed, never weaker).

### Invocation

```bash
slaif-gateway demo-snapshot-worker process-request REQUEST_ID [--json]
slaif-gateway demo-snapshot-worker cleanup [--limit N] [--json]
```

`process-request` processes exactly ONE request row end-to-end:

1. claim (224-a worker role; pending only; statement-time account
   gate);
2. ONE fresh 221 raw copy for that request — the private custody
   manifest records the request identity BEFORE the target database is
   created (the durable crash-safe request→job association);
3. 222 sanitization of THAT exact job only (never a global scan);
4. 223 file capture/verification of THAT exact job only;
5. worker-held proof: re-read the manifest through the anchored held
   job handle (state, files state, target grammar, exact request
   association) and re-prove the COMPLETE 223 display-tree law —
   files-directory identity, the exact leaf set (no foreign entry, no
   duplicate or invalid name), per-leaf regular type / 0600 mode /
   inode / byte count, digests and display policy — through anchored
   no-follow bounded reads; the SAME job-directory identity binds both
   reads, and the re-proven leaf count and total bytes must equal the
   main manifest's recorded `files_count` / `files_bytes`;
6. record the verified handoff (224-a CAS; statement-time
   generation fence).

It exits 0 with `state: verified_unpublished` only on full success.
Refused claims exit 1 with `state: claim_refused`. Every failure
exits 1 with a finite safe `code`; pipeline, proof and internal
failures additionally mark the row `failed` (claimed → failed)
through the guarded worker-failure transition, so the recovery path
can later find the artifacts it owns. Most handoff refusals mark the
row `failed` themselves (`state_conflict` for a disabled account or
generation reset, `late_completion` for an expired copy,
`verification_failed` for a non-verified manifest state). The one
handoff refusal the CAS itself does NOT mark is a copy-uniqueness
violation (`web_request_copy_reused`): the handoff transaction is
aborted without committing anything; since 224-d the worker then
attempts the guarded `claimed -> failed` mark promptly as well (a
no-op if the row already moved), and only if THAT write is refused
(e.g. a control outage) does the row stay `claimed` until the
bounded recovery reap marks it `failed` (`late_completion`) at its
full lifetime. The same reap also covers a control-side refusal of a
failure write itself (e.g. a control outage mid-pipeline), which
likewise leaves the row `claimed`. In
every case the recovery path resolves the exact owned job through
the durable private association. The output never contains a job
id, target database name, custody path, DSN, password or row
content.

`cleanup [--limit N]` (bounded 1..100 candidate rows, schedulable)
runs the recovery pass: reap stuck pending/claimed rows; mark failed
rows and session-released verified rows `cleanup_pending`; then for
each `cleanup_pending` row drop ONLY its bound target database FIRST
and remove ONLY its owned custody leaves, marking `cleaned` only after
the database is proven gone. Retained rows (cleanup refused or
failed) stay `cleanup_pending` — inspectable and retryable — and are
never marked `cleaned` while artifacts exist.

### Operator setup: create the two control roles and apply the reviewed grants

The 0028 migration creates NO roles and grants NOTHING. Before running
`process-request` / `cleanup`, the operator creates two dedicated LOGIN
roles and applies EXACTLY the reviewed matrix (the same statements
`demo_web_control.web_role_grant_sql` / `worker_role_grant_sql` generate).
Role names must match the closed PostgreSQL identifier law. Set each
role's password out-of-band (e.g. `ALTER ROLE ... PASSWORD ...` with a
strong value supplied through the operator's own secret channel); the
GRANT statements below contain NO password and the CLI/grant SQL never
prints one. Against the control database:

```sql
-- web control role (future 224-c+ login; column-limited by design)
CREATE ROLE demo_web LOGIN;
GRANT USAGE ON SCHEMA demo_control TO demo_web;
GRANT SELECT (id, username, password_hash, is_enabled,
              credential_generation)
  ON demo_control.fake_admin_accounts TO demo_web;
GRANT SELECT ON demo_control.demo_snapshot_requests TO demo_web;
GRANT INSERT (id, account_id, credential_generation, created_at,
              deadline_at, expires_at)
  ON demo_control.demo_snapshot_requests TO demo_web;
GRANT SELECT ON demo_control.demo_web_sessions TO demo_web;
GRANT INSERT (id, token_hash, account_id, credential_generation,
              request_id, created_at, expires_at)
  ON demo_control.demo_web_sessions TO demo_web;
GRANT UPDATE (revoked_at) ON demo_control.demo_web_sessions TO demo_web;

-- snapshot worker control role (facts only; never token_hash or
-- username/password_hash)
CREATE ROLE demo_snap_worker LOGIN;
GRANT USAGE ON SCHEMA demo_control TO demo_snap_worker;
GRANT SELECT (id, is_enabled, credential_generation)
  ON demo_control.fake_admin_accounts TO demo_snap_worker;
GRANT SELECT ON demo_control.demo_snapshot_requests TO demo_snap_worker;
GRANT UPDATE (state, failure_code, claimed_at, worker_job_id,
              worker_target_db, verified_at)
  ON demo_control.demo_snapshot_requests TO demo_snap_worker;
GRANT SELECT (id, request_id, expires_at, revoked_at)
  ON demo_control.demo_web_sessions TO demo_snap_worker;
```

Neither role has any business-table grant. `DEMO_WEB_WORKER_CONTROL_*`
points the worker control connection at the WORKER role (its password is
`DEMO_WEB_WORKER_CONTROL_PASSWORD`, never emitted). The worker invocation
additionally needs the 221 source-reader role and target user from the
221 operator setup. Apply the web role only when the later web login
suffix lands; nothing in 224-b uses it yet.

### Structural verified-copy eviction law (binds every generic 221 path)

A copy in `DB_AND_FILES_VERIFIED_UNPUBLISHED` state is NEVER evicted
by any generic 221 path: not retention expiry, not copy-budget
overflow, not a bare `run`/`expire` CLI invocation, not a concurrent
worker's startup pass — regardless of age or any caller input. Only
the exact control-owned cleanup (`cleanup` above, gated by the request
state machine and the live-session law) may remove it. This makes a
published (verified, session-usable) copy — and a copy between the
worker's proof and its publication CAS — immune to generic eviction by
construction: the exemption is read from the copy's OWN persisted
manifest state, so a cross-worker race or a stale state read cannot
remove it, and no caller-supplied set is involved or relied upon.

Verified copies still OCCUPY their finite budget slot: they count in
both the overflow computation and the fail-closed admission check.
When the budget is full of verified copies, a new copy is refused
with `SNAPSHOT_BUDGET_FULL` instead of evicting anything.

`CLEANUP_FAILED` copies (a previous removal attempt left surviving
custody/target artifacts) are subject to the same capacity law:
they occupy their slot and are never generic-evicted either — only
the exact recovery path retries their removal — so repeated failed
cleanups fill the finite budget and admission fails closed instead
of allowing unbounded surviving artifacts. The exact admission law:
a new copy is refused when, after adding it, the total (raw +
sanitized + verified + CLEANUP_FAILED) would exceed the cap and
evicting every evictable copy (raw/sanitized only) could not bring
the total back within the cap; otherwise the new copy is admitted
only when the post-eviction total stays within the cap. No
caller-supplied set participates at all: the persisted copy state is
the only eviction protection. Example at the default cap of 4 with
three verified copies and one evictable (raw/sanitized) copy: the
evictable copy is removed and the new copy IS admitted as the fourth;
a refusal happens only when the fourth occupied slot is held by a
never-evictable copy (verified or CLEANUP_FAILED).

### Request→job association and recovery

Because the 221 manifest records the request identity before the
target database is created, a request row that fails mid-pipeline
(222/223 failure, worker crash, restart) still durably points at its
EXACT one owned job. Recovery resolves ownership only through that
recorded association: an unbound failed row resolves to zero owned
jobs (nothing to remove — but only after the exact association scan
confirms zero) and is marked cleaned as no-op; a row resolving to
more than one candidate is refused and retained. Cleanup never
infers ownership from timestamps, names or global scans, and the
exact-job selectors (222/223) mean a copy of one request can never be
promoted or consumed by another.

A claimed request whose worker dies within the 60-minute lifetime
cannot be re-claimed (claims are pending-only); it is reaped at TTL
as `late_completion` (failed), and the recovery path then cleans its
exactly associated copy. Orphan verified copies from pre-224-b
operator runs (no recorded request) are structurally never
auto-expired: they occupy budget (fail-closed admission) and remain
inspectable for exact operator cleanup — a deliberate limitation, not
a silent sweep.

### Cleanup and live-session law

`cleanup_pending` from `verified_unpublished` is allowed only when no
USABLE live session still binds the copy: no unrevoked unexpired
session exists, OR the bound account is disabled, OR its credential
generation was reset. An account disable or reset releases the copy
immediately — every session of that account is already dead at first
use (the per-use recheck law) — so cleanup is no longer gated on the
60-minute lifetime. A live session with an enabled,
generation-matching account still refuses cleanup
(`web_cleanup_refused_live_session`).

Residual window (documented, test-proven): the cleanup count and its
state CAS are separate statements. A web session issued inside that
window (after the count, before the CAS) is INVALIDATED EARLY: its
first use is refused (`web_request_not_verified`, the bound request is
no longer `verified_unpublished`) and fresh issuance on that request
is refused. No browser can ever reach a copy cleanup is about to
remove; the safe direction is a not-yet-used demo session losing its
one shot, never a browser touching removed data.

### Transport boundary

Same as 221/222/223 for the target side: worker-only PG client tools
through a 0600 pgpass file, separate target service, and `ssl=False`
on the 222 asyncpg target connection. The NEW 224-b control
connection to the control database likewise connects with an EXPLICIT
`ssl=False` (the same deterministic no-TLS stage boundary): no TLS is
ever negotiated, so the operator MUST keep the control endpoint on a
trusted private loopback/Compose network. This stage does not support
verified remote DB TLS for either connection; do not point the
control endpoint at an untrusted network.

### Failure, restart, no survivors

A failure after 221 (222/223 error, mid-job crash, worker restart)
leaves the failed request row durably bound to its job; recovery finds
exactly that job through the association, drops the target database
first, then the owned custody leaves, and only then marks `cleaned`.
Foreign, extra-leaf or identity-mismatched custody cases are refused
and retained as `cleanup_pending` with the private manifest intact for
operator inspection (safe aggregate code `cleanup_failed`). Nothing
here is browser-visible; the demo remains unusable until the later
224 suffixes.

## Demo web entry (objective 224-c, browser entry only)

Objective 224-c adds the demo's BROWSER ENTRY: a purpose-built
STANDALONE ASGI application (`slaif_gateway.demo_web.create_demo_app`)
serving ONLY the `/fakeadmin` entry surface — login, wait, ready and
logout — on a dedicated demo hostname. It is default OFF, configured
by its own `DEMO_WEB_*` environment prefix (see Configuration → Demo
web entry), and is deliberately NOT part of the normal gateway
process: it registers NO `/v1` or `/admin` routes, holds no owner
`DATABASE_URL`, no 224-b worker credential, no provider credential, no
Redis and no catalog seal key. A web request NEVER imports or spawns
the privileged snapshot worker: the copy is still produced by the
separate 224-b `demo-snapshot-worker process-request` CLI invocation
(worker role, its own process) — the browser only ever enters, waits,
receives one session, and logs out.

**What this stage is and is NOT:**

- Browser ENTRY only. Copy-backed browsing (the demo `/admin` pages
  over the verified copy) is NOT enabled in 224-c and the ready page
  says so explicitly. The demo remains unusable beyond this entry
  surface until the later 224 suffixes.
- Standalone ASGI factory only. This stage ships NO CLI command and NO
  Compose service for the entry process: the operator runs
  `create_demo_app` as a standalone ASGI app (for example a uvicorn
  factory wrapper) on the dedicated demo host, with the `DEMO_WEB_*`
  environment set on that process only.
- The web process's ONLY database connection is the dedicated demo WEB
  control role (the reviewed 224-a column grants, applied at 224-b)
  with an EXPLICIT `ssl=False` stage boundary (no TLS is negotiated):
  the operator MUST keep the control endpoint on a trusted private
  loopback/Compose network. This stage does not support verified
  remote DB TLS.

### Entry law

- **Zero enabled accounts → 404 on every demo route** (login, wait,
  wait status, ready, logout): the demo surface is indistinguishable
  from an unknown path, so no credential or account-existence oracle
  exists.
- **Login**: finite field lengths, a small finite request-body bound
  enforced on bytes actually received (chunked bodies included) before
  any parsing, signed double-submit CSRF, a bounded in-process failed
  attempt window (429 with `Retry-After` beyond it), and a
  column-scoped credential lookup. One real Argon2id verification
  always runs on either path — against the real hash for a known
  enabled account, or against a precomputed fixed dummy hash
  (computed once at process startup) for unknown or disabled
  accounts — so the dominant verification cost is uniform even though
  the surrounding database lookup and branching are not mathematically
  constant; the failure message is one constant "Incorrect username
  or password."
  A successful login creates ONE fresh pending snapshot request
  (224-a) bound to the LIVE credential generation and moves the
  browser to the wait surface with a signed pending cookie whose
  lifetime is tied to the request's 60-minute TTL (a legitimate
  bounded worker chain can exceed 15 minutes; the request's own
  expiry remains the absolute bound, re-checked on every poll).
- **Wait**: the signed pending cookie binds
  `account:request:generation`. Every poll (page and the JSON
  `/wait/status`) re-reads the live request facts AND the live account
  fence: a disabled or deleted account, or a credential reset
  (generation moved), denies the wait surface immediately, even while
  other fake admins remain active. `/wait/status` reports only
  (`waiting` | `ready` | `timed_out` | `failed` | `unavailable`) and
  NEVER issues a session. Session issuance happens exactly once, in
  the wait page handler at the verified moment
  (`verified_unpublished`, unexpired, live fence rechecked): one
  `create_session` call, the raw opaque token delivered ONCE in the
  session cookie, then a redirect to the ready page. Terminal states
  clear the pending cookie.
- **Ready**: every use revalidates the session (224-a per-use law:
  not revoked, not expired, bound request still verified-unpublished
  and unexpired, account still enabled with the SAME generation,
  active account count nonzero). The page states that copy-backed
  browsing is not enabled yet and offers logout.
- **Logout**: signed CSRF; revokes the session idempotently (web-owned
  `revoked_at` only — the request row is never touched by the web
  role) and clears ALL demo cookies.

### Demo cookies

All demo cookies are `HttpOnly`, `Secure`, `SameSite=Strict`:

| Cookie | Path | Carries |
| --- | --- | --- |
| `slaif_demo_csrf` | `/fakeadmin` | a signed, expiring CSRF token (double-submit with the form field) |
| `slaif_demo_pending` | `/fakeadmin` | a signed `account:request:generation` binding (lifetime tied to the request's 60-minute TTL; consumed at issuance) |
| `slaif_demo_session` | `/` | the raw opaque session token only (its SHA-256 hash is the only stored form) |

The session cookie deliberately uses `Path=/` on the dedicated demo
hostname (while the pending/CSRF cookies stay strictly `/fakeadmin`):
the authorized later copy-backed GUI stage will serve demo `/admin`
pages on that same host and must receive the demo session cookie
there. This is safe because this process has NO normal `/admin` or
`/v1` routes, the cookie has a distinct demo-only name, and it is
deleted with the same path on logout/refusal.

### Operator setup

1. The control database has the 0028 schema (224-a) and the demo WEB
   role exists with EXACTLY the 224-a web grant matrix (224-b
   applied it for the worker side; the web role is the same matrix
   from `web_role_grant_sql`).
2. At least one ENABLED fake-admin account exists (trusted operator
   path; the web role can never create or mutate accounts).
3. Run the standalone demo app on the dedicated demo host with the
   `DEMO_WEB_*` environment (`DEMO_WEB_ENABLED=true` plus the web
   role control connection and a strong `DEMO_WEB_COOKIE_SECRET`);
   see Configuration → Demo web entry.
4. The 224-b worker (`demo-snapshot-worker process-request` /
   `cleanup`) runs on its own schedule/invocation with the worker
   role — nothing in the web process triggers it.

### Evidence

- Unit (fake facade): default-off refusal, config validation, signed
  token law, zero-active 404s, constant login failures with the
  precomputed dummy-Argon2 uniform path, CSRF/pending tamper and
  expiry, the live account fence on every poll (disable, reset,
  delete), bounded form bodies (oversized 413, wrong content type
  400), exact one-session issuance, per-use session validation,
  logout revocation, cookie paths, `/v1`+`/admin` absence, web-path
  import isolation (no privileged worker module in the web process).
- Owned PostgreSQL 16 (real restricted web role, real worker-role CLI
  chain): the full cycle login → request → `process-request` → wait →
  one session (stored form is the SHA-256 hash only) → ready → logout
  → worker `cleanup` drops the bound target database and the row
  reaches `cleaned`; the web role's 42501 boundary (full-row account
  read, business tables, `state` in INSERT, any request UPDATE);
  zero-active 404s and re-enable.

## Demo verified copy reader (objective 224-d, read-only preview)

224-d makes an EXACT fully verified disposable database readable under
a dedicated target-copy READER role and proves per-session copy
isolation with one small authenticated read-only preview
(`/fakeadmin/copy-preview`). It does NOT mount the normal admin
routers and does NOT claim the demo GUI usable: the next same-PR
suffix binds the admin GUI behind a server-side mutation gate, and
later suffixes complete file-backed panels, installed browser
evidence and final delivery. The demo is still NOT usable for
company demonstrations at the end of 224-d.

### The static reader role (operator-provisioned; nothing creates it)

The operator creates ONE static login role on the SEPARATE target
PostgreSQL service, with its own password:

```sql
-- target service, run by the target admin (operator path). The
-- password is set through the interactive psql prompt (or the
-- operator's secret-management step), so it never appears in a
-- command line, psql history or this document:
CREATE ROLE slaif_demo_copy_reader LOGIN;
\password slaif_demo_copy_reader
```

The role law the worker enforces BEFORE any grant (fail-closed):

* LOGIN role;
* carries NO `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `BYPASSRLS` or
  `REPLICATION` bit;
* has NO role memberships (`pg_auth_members` empty);
* is NOT the target-admin user.

It starts with NO `CONNECT` on any new raw target database (221's
closed create + `REVOKE CONNECT FROM PUBLIC` is unchanged). No role or
grant is created implicitly by an HTTP request.

### Worker-side publication grant (exact verified copy only)

After 222 database sanitation AND 223 file capture/verification finish
for the exact job, and the 224-b worker-held proof (job, request,
target identity, combined verified state, exact file tree) passes, the
`process-request` worker (target-admin boundary, bounded, credential-
masked, finite 30 s deadline) performs, in ONE explicit transaction on
the EXACT target database:

1. `GRANT CONNECT ON DATABASE "<the one copy>" TO "<reader role>"`;
2. `GRANT USAGE ON SCHEMA public TO "<reader role>"`;
3. `GRANT SELECT ON ALL TABLES IN SCHEMA public TO "<reader role>"`.

A mid-transaction failure rolls back EVERYTHING (no partial CONNECT).
The grant is idempotent for that exact copy and is bounded by the 222
fail-closed schema inventory: the copy exists only because 222
sanitized exactly the reviewed closed table set. The role receives no
source-cluster grant, no target-admin privilege, no DML/DDL. A raw,
DB-only-sanitized, failed, stale-generation, reused or wrong-request
copy is never granted. The grant is complete BEFORE 224-a
`record_verified_handoff` makes the copy browser-authoritative; if the
grant or the handoff fails, the copy is NEVER labeled published. On a
handoff refusal the worker marks the request `failed` promptly
(guarded `claimed -> failed`; a no-op if the row already moved) so the
exact request-associated cleanup drops the bound target database — a
database DROP removes its grants with it (a failed drop retains the
inspectable `cleanup_pending` state). If a control outage prevented
even the guarded failure mark, the bounded 224-a claim-lease reap
remains the backstop that moves the row to `failed` for the same
cleanup. No schema migration and no general grant framework.

Worker configuration: `DEMO_SNAPSHOT_TARGET_READER_ROLE` (required,
closed identifier; the worker fails closed without it).

### Web-side session-bound copy reader

The standalone demo web process receives ONLY the reader role's own
connection (`DEMO_WEB_COPY_HOST/PORT/USER/PASSWORD`), separate from
its control WEB role, the worker's target-admin passfile, the
source-export credential, the owner `DATABASE_URL`, Redis and any
provider secret. On EVERY preview read:

* the 224-a demo session is revalidated (live account/generation
  fence) and the stored session binding is used authoritatively;
* the EXACT request is re-read and must be `verified_unpublished` and
  unexpired, with id AND account matching the session;
* the closed `demo_snap_<20hex>` target database name is required from
  the control row (no other shape is ever interpolated);
* ONE per-request read-only connection (`NullPool`, bounded connect
  and statement timeouts, explicit no-TLS stage boundary) inside a
  database-side `READ ONLY` transaction (verified with
  `transaction_read_only`): `current_database()` must equal the bound
  name, then the fixed reviewed public-table allowlist is counted;
* the connection is disposed after use, so logout/cleanup is never
  held by an idle web pool.

No pathname/custody read from the web process. A stale, disabled,
revoked, expired, wrong-request or missing copy fails closed with ONE
safe page note — no target name, DSN or internal error is exposed.
The preview response is `Cache-Control: no-store`.

### Still-incomplete status and safe rollback

* The preview shows bounded counts only (identity-masked data); it is
  a proof of the copy binding, not an admin UI. Two concurrent demo
  sessions read their OWN distinct copies; the control/source business
  tables are never queried through the reader role.
* Safe rollback: revoke the reader role's access by dropping the bound
  target database (the worker `cleanup` path does this on the exact
  request association) or, while the copy still exists,
  `REVOKE CONNECT ON DATABASE "<copy>" FROM "<reader role>"` plus
  `REVOKE USAGE, SELECT` on the schema/tables; the role itself can be
  dropped by the operator once no demo copy needs it.

## Demo admin core read gate (objective 224-e, first admin page set)

224-e mounts the EXISTING admin router/template implementation ONLY in
the standalone `create_demo_app` process and makes a bounded FIRST set
of existing database-backed admin pages browse the session's 224-d
verified copy behind a central, server-side, default-deny gate. This
is an incomplete core preview, not full GUI coverage: the remaining
DB/file-backed families (providers, routes, pricing, usage,
operations, audit, email, catalog refresh, accounts, key batch, key
clone, compatibility, replay maintenance, reports, and the
file-backed display panels) are still default-denied 404 behind the
gate and belong to a later same-PR suffix. The demo is still NOT
usable for company demonstrations at the end of 224-e.

### Gate law (default-deny, before handlers and body parsing)

The gate wraps the mounted admin app and is evaluated BEFORE any
admin handler and BEFORE form/body parsing:

* with ZERO active fake-admin accounts, every `/admin` path 404s
  (fail-closed; no credential or existence oracle);
* `GET /admin/login` redirects to `/fakeadmin/login`; the real
  login POST is never dispatched;
* the ONLY admitted admin GETs this suffix: dashboard `/admin` (and
  the harmless trailing slash), the list pages `/admin/keys`,
  `/admin/owners`, `/admin/institutions`, `/admin/cohorts`, their
  record detail pages where the path component is EXACTLY one
  canonical lowercase `8-4-4-4-12` UUID (uppercase, no-dash, `urn:`
  and braced forms are refused), and the `GET /admin/record-choices`
  lookup their existing filters need;
* every other admin GET is 404 until explicitly reviewed in a later
  suffix (nothing is silently rerouted to the live gateway);
* the packaged `/admin/static` assets are served from the package
  (fixed neutral branding; no live branding directory or catalog
  file is ever read by the demo process).

Every unsafe method (POST/PUT/PATCH/DELETE, ...) on any `/admin`
path - KNOWN or UNKNOWN - is cut before the handler as a quiet
204 no-content: the request body is never parsed, no fake success
page renders, and there is no audit, accounting, mail, provider or
custody effect. The ONE explicit exception is demo sign-out:
`POST /admin/logout` parses a bounded form, verifies the page-issued
CSRF token with a constant-time compare, and revokes the demo
session through the 224-c control service; it clears the demo
cookies and returns to the demo login flow ONLY when the revocation
is confirmed (or the session is already absent). A failed or
unconfirmed revocation is a safe 400 retry refusal that keeps the
session valid - never a false sign-out success. It never calls the
production admin logout service.

### Per-request copy binding (no app-global factory)

On EACH admitted admin read:

* the 224-a session is revalidated against live fake-admin
  account/generation/request state;
* the exact request is re-read and must be `verified_unpublished`
  and unexpired, with id AND account matching the session;
* the control row's closed `demo_snap_<20hex>` target database name
  is required (no other shape is ever interpolated);
* a REQUEST-LOCAL sessionmaker is created under the 224-d reader
  credential (`NullPool`, bounded connect/statement timeouts,
  explicit no-TLS `ssl=False` stage boundary - trusted private
  network only, NO verified TLS guarantee), and a preflight on the
  connection verifies `current_database()` equals the bound name
  AND `transaction_read_only` is `on` before any handler may query;
* the engine is disposed after the response completes - and on
  every refusal path.

Demo requests never consult the app-global sessionmaker:
`get_sessionmaker_from_app` branches FIRST on a fixed `demo_mode`
app marker and fails closed when the validated request-local factory
is absent. Concurrent visitors read DISTINCT copies. A missing,
expired, revoked, disabled or cleanup-racing copy returns a fixed
safe no-store refusal note - no DSN, copy name or error traceback -
and never falls back to the source database. Admitted pages query
ONLY copied `public` rows with the existing filtering, sorting,
paging and record-choice behavior (no new CRUD surface).

### Display identity and GUI treatment (demo mode only)

Admitted pages render a fixed fictional administrator display
identity ("Demo Administrator", `demo-admin@example.invalid`,
deterministic uuid5 placeholder identifiers) and a
non-authoritative form token, without reading or mutating copied
`admin_sessions` or the normal `AdminSessionService`; the normal
production branch is unchanged in behavior, visible DOM content and
auth/action semantics (one whitespace-only line in the base template
HTML aside - regression verified). In demo mode only: every admitted page carries a
persistent banner (identity-masked snapshot data, read-only,
operational actions have no effect, incomplete core preview); the
nav shows exactly the five usable sections (Dashboard, Keys,
Owners, Institutions, Cohorts); and unimplemented action links
(create/batch/clone/calibration/config-download, the
providers-and-models and usage-and-operations groups, replay
maintenance) are hidden with honest read-only hints where a hint
is warranted. Normal-mode markup renders as before.

### Evidence

* Focused unit: closed admission sets (admitted vs 404 vs 303),
  canonical-UUID-only detail law, zero-account 404, pre-handler
  unsafe 204 (oversized garbage body never parsed; the unit
  evidence samples representative unsafe paths - ten cases across
  the mounted families - and the uniform `DemoAdminGate.__call__`
  branch structurally cuts ALL authenticated unsafe `/admin`
  methods before inner-app dispatch),
  CSRF-verified logout with no false success (failed/unconfirmed
  revocation keeps the session live), binding refusals with no
  DSN/copy-name leak, preflight wrong-database and
  read-only-off dispose-and-refuse, request-local factory
  fail-closed with a deliberately populated global factory,
  ambient-environment-free display settings, and normal-vs-demo
  base-template rendering.
* Owned PostgreSQL 16: two concurrent sessions produce two
  DISTINCT verified copies - proven by one extra institution row in
  the second copy's database and in its rendered list (222
  fictionalizes institution names, so a raw source marker name
  never appears in either page); every admitted GET family renders
  behind the real SELECT-only reader role; operational POST
  families and an unknown path are zero-effect no-ops; source and
  both copies are count-invariant; CSRF sign-out revokes and
  bounces. A real Chromium smoke (loopback uvicorn) additionally
  proves packaged CSS/JS loading, the banner/nav, table sorting and
  logout, saving one screenshot to a run-owned `/tmp` path (never
  committed; its path is printed to local test stdout only and never
  appears in ordinary application logs).

## Demo db-backed admin sections (objective 224-f)

224-f expands the 224-e request-local read gate to the seven
remaining straightforward DATABASE-BACKED list/detail sections and
closes a demonstrated browser-cache privacy gap. Each of the 14
candidate handlers was source-reviewed before admission: all read
ONLY copied `public` rows through the existing repositories and the
request-local sessionmaker, with no file, process or network read
(no exceptions; nothing was kept gated for that reason). The demo
is still an INCOMPLETE preview - forms, file-backed displays and
process/network panels stay gated - and still NOT usable for
company demonstrations.

### Admission (224-f)

Admitted in addition to the 224-e core set:

* `/admin/providers`, `/admin/providers/{uuid}`
* `/admin/pricing`, `/admin/pricing/{uuid}`
* `/admin/templates`, `/admin/templates/{uuid}`
* `/admin/fx`, `/admin/fx/{uuid}`
* `/admin/usage`, `/admin/usage/{uuid}`
* `/admin/audit`, `/admin/audit/{uuid}`
* `/admin/email-deliveries`, `/admin/email-deliveries/{uuid}`

The same closed law applies: one canonical lowercase `8-4-4-4-12`
UUID per detail path, live session/account/generation/request fence,
exact `verified_unpublished` unexpired `demo_snap_<20hex>` binding,
request-local SELECT-only/read-only sessionmaker with disposal.
Action GETs (edit/discover/import/reports/forms/exports), the
routes, operations, catalog, compatibility, OpenAI-assisted,
accounting-recovery, replay-maintenance, accounts, key batch/clone
and branding sections stay 404; their POSTs remain the
authenticated pre-handler 204 no-op and sign-out remains the sole
CSRF-checked mutation exception.

The demo nav now lists exactly the admitted sections (twelve);
in demo mode the new pages hide links to still-gated forms,
edit/export, network-discovery and file-backed routes with plain
text or honest read-only treatment (no orphan separators or empty
action panels), while visible operational POST buttons remain
quiet no-ops. A small shared template helper fixes the
singular/plural list-count label (`1 row shown` / `N rows shown`)
on all admitted list pages - a GUI polish with no data or
accounting change.

### Browser-cache privacy boundary (224-f)

224-e left successful admitted HTML and JSON responses WITHOUT
`Cache-Control: no-store`; a browser could retain the
identity-masked snapshot after sign-out. 224-f installs ONE
central, demo-only, ASGI response-start guard: EVERY dynamic
`/admin` response the demo process emits - admitted pages, JSON,
error pages, the zero-account 404, no-ops and redirects - carries
exactly one `Cache-Control: private, no-store` header (existing
cache-control headers are replaced, never duplicated). The
revisioned `/admin/static` passthrough deliberately bypasses the
guard and keeps its own cache policy, and the ordinary app never
runs behind it. Scope honestly: this prevents NORMAL HTTP
caching, and every dynamic reload rechecks authorization; no
absolute browser history or back-forward-cache erasure is claimed.

### Still-gated families (for 224-g/h)

Routes, operations (diagnostics etc.), catalog refresh,
compatibility, OpenAI-assisted, accounting-recovery, replay
maintenance, admin accounts, key batch, key clone, all unreviewed
form GETs, exports/downloads, `/admin/branding`, and the
file-backed display panels.

### Evidence (224-f)

* Focused unit: the closed admission sets and near-misses for all
  eleven detail families (extra suffix, action GET, variant UUIDs),
  the no-store guard on successful HTML, JSON, handler-level
  errors, the zero-account 404, login redirect and no-op, the
  static passthrough retaining its cache policy, and the expanded
  demo nav.
* Owned PostgreSQL 16: two concurrent sessions still read two
  DISTINCT copies; EVERY new list/detail renders from its own copy
  behind the real SELECT-only reader role; REAL identity/secret
  canaries are absent from the pages while the 222-fictionalized
  identities are the ones shown; the rendered usage ROW COUNT
  equals the copied `usage_ledger` table count (the token/cost
  quantities themselves are 222's verified masking contract, not
  re-verified by this round); source and both copies remain
  count-invariant; direct unsafe methods still 204 before
  handler/body parse. A real Chromium smoke covers the new nav,
  one new section's sorting, the no-store header, and that a
  fresh reload after sign-out rechecks authorization instead of
  serving a cached snapshot.

## Demo verified file display publication (objective 224-g)

224-g gives the SAME session-bound SELECT-only copy reader access to
the 223-verified sanitized file display leaves - through the TARGET
DATABASE, never the worker file system. The worker ingests ONLY that
job's verified leaves into a fresh, target-only `demo_display`
schema inside the exact disposable copy, and the existing static
reader role receives `USAGE`/`SELECT` on it in the SAME bounded grant
transaction that grants the public tables. The standalone web process
gets a small request-bound read-only display reader on its EXISTING
`DEMO_WEB_COPY_*` credentials, and the new
`/fakeadmin/files-preview` page lists ONLY safe bounded metadata
(logical name, kind, byte count, capture time) as a proof of binding.
No file BODY is rendered from a URL in this suffix, and NO
file-backed admin panel is mounted yet. The `demo_display` schema is
disposable with the copy: it is never in the source database, never
in the ordinary gateway DB, and never in the 222-verified `public`
inventory.

### Worker ingest (target-only, 224-g)

* Runs ONLY after the complete 224-b worker-held re-proof (combined
  222 + 223: job/request/target identity, exact files tree, digests)
  and BEFORE the 224-a verified handoff.
* ONE finite deadline - the existing file-job elapsed bound
  (`DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS`, reused; no new
  setting). Since 224-h it is a REAL wall-clock cap: an already
  exhausted budget is refused before any connection, and ONE
  `asyncio.timeout` covers the connect, the DDL, every `INSERT`
  and the final COMMIT, so once the budget elapses NO ingest,
  grant or handoff is confirmed (the cancellation/rollback/
  connection-close cleanup after a timeout may still take extra
  time; the exact target cleanup is authoritative). A timed-out or
  uncertain commit fails closed with no handoff and no grant; the connection close is the rollback backstop, and
  the exact request-associated copy cleanup remains authoritative
  (if a driver cancellation ever leaves a transient, UNGRANTED
  target-only table behind, it can never be browser-authoritative
  and is removed with the copy).
* ONE bounded target transaction: creates the `demo_display` schema
  + one `leaves` table, streams ONE re-proven leaf at a time through
  parameterized `INSERT`s (no body, password or source value in
  argv, SQL text or logs), and commits ONLY after the held re-proof
  generator is fully exhausted (its final handle name-binding and
  deadline checks have run). The generator's held descriptors are
  always released, even on a mid-iteration driver failure.
* A CLOSED display law applies to every entry: the exact per-kind
  logical-name grammars the 223 producers can emit (per-copy keyed
  ids or fixed vocabulary only), no duplicate names, no unknown
  kind, exact byte counts, capture times in the representable
  range (below `datetime`'s year-9999 ceiling, so current and
  post-2038 capture times stay valid), and the per-leaf /
  aggregate byte bounds. Since 224-h the commit additionally
  requires BOTH the leaf COUNT and the AGGREGATE BYTE total to
  equal the worker-held custody manifest, and the manifest's exact
  `target_db` must equal the verified copy binding BEFORE any
  target connection - the caller's target name is never authority.
* The table stores ONLY the closed safe index fields
  (`logical_name`, `kind`, display `sha256`, `byte_count`,
  `captured_at`) plus the sanitized `bytea` body. The private
  manifest fields (`source`, `source_ref`, `source_sha256`, inode
  identity, on-disk leaf names) NEVER enter the copy.
* A failed or torn transaction leaves NO published table: the
  request fails with the finite safe code
  `WEB_DISPLAY_INGEST_FAILED`, and the exact request-associated
  cleanup drops the bound target database - removing the schema and
  every grant with it (a failed drop retains the inspectable
  `cleanup_pending` state).

### Storage tradeoff (operator target-disk sizing, 224-g)

This deliberately duplicates verified sanitized file bytes in the
target database until the copy is dropped. The payload is bounded by
the existing 223/224-b limits: 32 MiB per leaf / 128 MiB aggregate
by default (configurable upper 128 MiB / 4 GiB), at most four
retained copies - so the additional target payload is at most 512 MiB
by default and 16 GiB at the configured upper bound, before
PostgreSQL storage overhead. The private 223 custody retains its own
sanitized leaves until cleanup as well. Size the operator's TARGET
disk for that; a capacity or deadline failure fails the login
closed and never publishes partial file data.

### Pre-upgrade session behavior (224-g)

Existing pre-upgrade verified sessions whose copies predate this
stage have NO `demo_display` schema. Their already-authorized
DB-only pages keep working until expiry, but the new files preview
FAILS CLOSED for them (the page renders the safe note instead). New
logins after this stage get the full display publication.

### Reader law (224-g)

The web display reader uses the existing `DEMO_WEB_COPY_*` static
reader credential against the exact copy named by the verified
control row (closed `demo_snap_<20hex>` law): one per-request
engine, a database-side READ ONLY transaction with verified
read-only mode and `current_database()` binding, the fixed closed
table with a finite row bound, and disposal after every use. No
filesystem access, no worker module import, no source/owner
connection, no app-global per-visitor state. EVERY response of the
`/fakeadmin/files-preview` route (login redirect, zero-active 404,
safe note and successful page) is explicitly
`Cache-Control: no-store`; nothing reveals the database name,
credential, private manifest, raw source reference or secret. The
preview formats only representable finite capture times; a stored
value outside that range renders the SAME safe note instead of a
500. A future internal method
may retrieve one validated leaf body for the later panel adapters;
this suffix ships no download endpoint or body rendering.

### Boundary repair (224-h)

224-h closes four review findings on the 224-g seam (same PR):

1. **Target equality before any connection**: the worker-held
   main manifest's exact `target_db` must equal the verified copy
   binding; a foreign but syntactically valid target name refuses
   with `WEB_DISPLAY_INGEST_FAILED` before any connection, grant
   or publication.
2. **Count AND aggregate bytes**: the ingest commits only after
   BOTH `count == files_count` and `total_bytes == files_bytes`
   against the worker-held custody manifest, after full exhaustion
   of the held re-proof iterator.
3. **Wall-clock deadline over connect/DDL/INSERT/commit**: one
   `asyncio.timeout` (the file-job elapsed bound) covers every
   await of the ingest; an already-expired budget refuses before
   connecting; a timed-out or uncertain commit fails closed (no
   handoff, no grant). If a driver cancellation can leave a
   transient ungranted target-only table, exact copy cleanup
   removes it; such a table is never browser-authoritative.
4. **Preview response + time law**: every files-preview response
   category is explicitly `no-store`, and only representable
   finite capture times are formatted (same safe note otherwise,
   never a 500); the worker-side capture-time bound is the
   representable range below year 9999.

The 224-g files-preview table also corrected the admin usability
inventory count (+1 sortable table). For the four points above,
this repair supersedes the 224-g report's claims.

### Still-gated after 224-g

All file-backed admin PANELS remain unmounted (a later 224 suffix
wires them on top of this publication), along with the still-gated
224-f families. The demo remains NOT usable for company
demonstrations; objective 225 remains the installed acceptance gate.

### Evidence (224-g)

* Focused unit: the closed per-kind display-name law (positive
  shapes and foreign/traversal/unknown-kind refusals); the ingest
  happy path projecting ONLY the closed safe fields (private
  manifest fields asserted absent from every SQL parameter);
  duplicate-name, unknown-kind, illegal-name, changed-leaf,
  main-manifest count drift, invalid capture time and elapsed
  deadline refusals (each rolling back the target transaction);
  foreign job/request and malformed target name before any DB work;
  the grant transaction now carrying the `demo_display` USAGE +
  `SELECT ON demo_display.leaves` statements atomically; the
  process-request ingest-failure path (no grant, no handoff,
  failure recorded); and the files-preview route/session law
  (bounce, safe note for unverified/expired/wrong-account/pre-upgrade
  copies, no-store, metadata-only rendering, no canary).
* Owned PostgreSQL 16 (real target service): a fully verified
  job publishes the EXACT closed leaf set - the target table equals
  the worker's own re-proven custody name-for-name with the two
  configured sources pinned; the table carries only the closed safe
  columns; worker-private values (control password, custody path,
  passfile, source database, copy name) are absent from every stored
  body; the real reader role is denied DML/DDL on the table
  (42501); a raw copy has NO reader CONNECT and NO display schema in
  either its raw or DB-only-sanitized state; a torn ingest
  transaction (real rollback on the real copy) leaves NO published
  table while an unrelated session-live copy is untouched, and the
  exact request-associated cleanup drops only the failed copy and
  marks it cleaned; a leaf changed after 223 verification refuses
  publication before ingest and grant (no display table, no reader
  grant).

## Demo admin core forms and route read pages (objective 224-i)

224-i (same PR #383) admits, through the same closed default-deny
gate, the next closed set of EXISTING GET/HEAD read pages:

* the routes list (`/admin/routes`) and the route detail
  (`/admin/routes/{uuid}`);
* the twelve fixed core form GETs: `/admin/keys/create`,
  `/admin/keys/bulk-import`, `/admin/owners/new`,
  `/admin/institutions/new`, `/admin/cohorts/new`,
  `/admin/providers/new`, `/admin/routes/new`,
  `/admin/routes/import`, `/admin/pricing/new`,
  `/admin/pricing/import`, `/admin/fx/new`, `/admin/fx/import`;
* the seven canonical-UUID edit forms:
  `/admin/{owners,institutions,cohorts,providers,routes,pricing,fx}/{uuid}/edit`;
* the provider discover read-only form
  (`/admin/providers/{uuid}/discover`).

The demo nav gains a **Routes** entry (between Providers and Pricing,
matching the normal nav order). The create/import/edit links that the
224-f/g demo conditionals hid (their targets were 404 at the time)
are shown again in demo mode now that their targets are admitted;
links whose targets stay gated (key batch, reports, operations)
remain hidden.

### Form semantics (read-only demo)

Every admitted form is the REAL administrator form rendered from the
session's verified copy (field choices, hints and copied values).
The persistent banner stays on every page; the four data-ingest
forms (key bulk-import and the route/pricing/FX import preview
forms) add one concise local hint above their preview submit.
Submitting any form produces the SAME quiet server-side 204 no-op
BEFORE routing and body parsing: nothing is written to the copy,
the source or the normal database, and no provider or network call
occurs. The operational buttons are deliberately NOT removed -
their server-side no-op is the safety boundary, and the banner
explains it.

### Route detail demo-safe presentation (224-i)

* the Codex profile artifact block is NOT rendered in demo mode:
  `render_codex_profile` is skipped entirely, because the demo host
  cannot forward `/v1` and a profile built from the neutral demo
  base URL would be misleading; a one-line read-only hint replaces
  the block. Normal admin rendering is unchanged.
* the still-404 "Reviewed configuration change" and "Codex
  compatibility" links are hidden in demo mode;
* the provider config section shows only the 222-fictionalized
  copied `base_url` / `api_key_env_var` values (222 preserves the
  provider slug and remaps/fictionalizes the row ID, URL and
  env-var name - proven in the owned-PG evidence).

### Remaining 404 families (still default-denied)

Operations (all subpaths), reports, catalog, compatibility,
branding, process-configuration, OpenAI-assisted, accounts, key
batch/clone (and specifically `/admin/keys/{uuid}/edit` and
`/admin/templates/{uuid}/edit`), route configuration-change and
codex-profile downloads, exports, and every action GET, unknown
path or non-canonical path shape. All file-backed admin panels
remain unmounted (their read data is published by 224-g; wiring is a
later 224 suffix). The demo remains NOT usable for company
demonstrations; objective 225 is the installed acceptance gate.

### Evidence (224-i)

* Focused unit (`test_demo_web.py`, 106 passed, +2 new): the closed
  admission law (every 224-i positive shape admitted, unknown/extra/
  malformed/action GETs denied, keys/templates edits denied, edit
  middle-segment UUID variants denied, discover only on providers);
  no-store on an admitted form response; the demo nav includes
  Routes (thirteen sections) with normal rendering unchanged; and
  the route-detail handler skips `render_codex_profile` in demo mode
  (asserted never called) so the demo HTML carries no localhost/live
  URL, no profile TOML and no download links, while normal mode
  still renders the artifact block.
* Owned PostgreSQL 16 (real reader role, real worker chain, two
  concurrent sessions on distinct copies): the routes list (rendered
  row count equals the copied `model_routes` count) and route
  detail, all twelve form GETs, all seven edit forms and the
  discover form render 200 with banner and no-store; the route
  detail shows the copied fictionalized provider URL/env-name while
  the raw SOURCE values are absent; the still-gated GETs
  (keys/templates edit, route configuration, codex-profile
  download, exports) stay 404; and the whole read phase leaves the
  source and BOTH copies unchanged (`model_routes` added to the
  invariance set).
* Real Chromium: the new Routes nav link is visible and follows to
  the list, a route detail row opens, and the cohorts create form
  renders; its operational submit returns the quiet 204 no-op with
  the rendered cohort row count unchanged. One screenshot is saved
  to a run-owned /tmp path (never committed and not in ordinary
  application logs).
* The 224-h exact-head CI unit failure (governance identifier test
  versus the immutable 224-h order's title suffix) is recovered by
  this identifier-only order: the unchanged governance suite passes
  9/9 locally against `oap/active=224-i`.
## Database-backed reporting and administrator review GETs (objective 224-j)

224-j (same PR #383) admits, through the same closed default-deny
gate, the next closed set of EXISTING database-backed reporting and
administrator review GET pages. Every one reads ONLY the
session's verified disposable copy through the 224-e request-local
sessionmaker; none reads the source/owner DB, Redis, providers,
operator files or live credentials, and none mutates on GET:

* reporting (5): `/admin/reports/` (usage summary report),
  `/admin/reports/live-burn`, `/admin/reports/export` (the export
  FORM page; the export attachment GETs stay denied),
  `/admin/reports/pricing-disable`, `/admin/reports/fx-lookup`;
* accounting candidate/review entry (5):
  `/admin/accounting-operations/`,
  `/admin/accounting-operations/expired-reservations`,
  `/admin/accounting-operations/external-tool-fences`,
  `/admin/accounting-operations/external-tool-holds`,
  `/admin/accounting-operations/provider-completed-recovery`;
* administrator accounts (3): `/admin/accounts`,
  `/admin/accounts/create`, `/admin/accounts/reset` (the existing
  validated `admin_id` query semantics unchanged);
* key batch entry (1): `/admin/key-batch`.

These are EXACT positive paths, not prefix passthrough:
missing-slash paths (`/admin/reports`,
`/admin/accounting-operations`), extra suffixes
(`/admin/reports/usage`, `/admin/accounts/reset/`), export
attachments (`/admin/reports/export.csv`) and unknown account
actions (`/admin/accounts/revoke`) stay 404.

### Display superadmin for the demo-only session

The three account GETs carry the existing server-side
`superadmin` role gate. The demo session's isolated fictional
identity (never persisted, never written to any database) is now
presented with `role="superadmin"`, so the demo administrator sees
the copied account list and the create/reset forms like a real
superadmin. This never alters real admin roles, source accounts,
auth decisions outside this demo process, or the central 204
no-op boundary. The copied `admin_users` records remain
222-anonymized (fictional email/display name, fixed dummy password
hash, NULL MFA secret, preserved role). The account pages render
safe metadata only: no password hash, MFA secret, session token or
source email appears in the HTML (proved by the owned-PG canaries).

### Request-time calculations carry a demo-only hint

The reports and accounting candidate lists operate on FROZEN
copied rows. Two handlers evaluate a window at REQUEST TIME
(expired-reservations compares `expires_at` with the current time;
fx-lookup resolves the effective rate at UTC now). Each of those
two pages carries one concise demo-only hint that the rows are
snapshot data and the derived value is calculated/resolved at view
time against the snapshot - not at snapshot time. They are never
presented as live production metrics, and the hint does not imply
the derived value was frozen at login. Normal-admin behavior and
labels are unchanged.

### Links restored in this stage

* Usage list: "Usage reports" to `/admin/reports/`;
* Keys list: "Change existing keys" to `/admin/key-batch`;
* FX list: "Effective rate lookup" to `/admin/reports/fx-lookup`;
* Pricing list and detail: "Review pricing disable" to
  `/admin/reports/pricing-disable`;
* the demo nav gains an **Accounts** entry (last), and the
  create/reset pages are reached from the account list.

Still hidden in demo mode: replay maintenance, diagnostics,
operations (including the "Operations" header link on the
accounting index), OpenAI-assisted, catalog, compatibility,
branding, clone/receipts, process-configuration, downloads, and
the accounting review ACTION pages. Every unsafe method on the
admitted pages - report export, account create/reset, batch plan
and accounting review - stays the SAME silent 204 no-op BEFORE
body parsing/handler dispatch.

### Remaining 404 families after 224-j (still default-denied)

Operations (all subpaths), replay maintenance, diagnostics,
catalog, compatibility, branding, process-configuration,
OpenAI-assisted, key clone (and specifically
`/admin/keys/{uuid}/edit` and `/admin/templates/{uuid}/edit`),
route configuration-change and codex-profile downloads, export
attachments and file-backed GETs, the accounting review action
pages, and every unknown/non-canonical path shape. All file-backed
admin panels remain unmounted (their read data is published by
224-g; wiring is a later 224 suffix). The demo remains NOT usable
for company demonstrations; objective 225 is the installed
acceptance gate.

### Evidence (224-j)

* Focused unit (`test_demo_web.py`): the closed admission law
  admits all fourteen exact GETs (no session -> demo-entry
  redirect) and denies the near-misses (missing slash, extra
  suffix, export attachment, unknown account action); every unsafe
  method on the admitted pages - report export, account
  create/reset, batch plan, accounting review - is the quiet 204
  cut with a 200 KB garbage body that is never parsed; the demo
  nav includes Accounts (fourteen sections).
* Owned PostgreSQL 16 (real reader role, real worker chain, two
  concurrent sessions on distinct copies): all fourteen GETs
  render 200 with the banner and `private, no-store`; the account
  list shows the 222-anonymized COPIED emails while the SOURCE
  emails and the copied dummy password hashes are absent from the
  HTML; the usage summary report's rendered group count equals the
  copied ledger's distinct provider:model group count (page limit
  50) and the report's sole fixture group renders the COPIED
  amounts: its token total `data-sort-value` equals
  `SELECT sum(total_tokens)` over the session's copied
  `usage_ledger` (200) and its actual-cost `data-sort-value`
  equals `SELECT sum(actual_cost_eur)` (0.0023 EUR), compared with
  the copy, never the source; the expired-reservations row count
  equals the copied
  `quota_reservations` pending-and-expired row count (view limit
  200); both request-time pages carry the demo-only view-time
  hint; the near-misses stay 404; the unsafe methods stay quiet
  204; and the whole read/POST/logout phase leaves the source and
  BOTH copies unchanged (`quota_reservations` added to the
  invariance set).
* Real Chromium at desktop width: the nav -> Accounts entry, the
  usage summary report, the expired-reservations page and the key
  batch entry render with the banner and no-store. One screenshot
  is saved to a run-owned /tmp path (never committed and not in
  ordinary application logs).

## Catalog snapshot index (objective 224-k)

224-k (same PR #383) makes the captured catalog's SAFE FILE INDEX
visible inside the demo GUI: ONE demo-only read handler for the
exact `GET /admin/operations/catalog/`, mounted ahead of the normal
catalog router only in `create_demo_app` (the normal custody-backed
handler is never reached for that path in the demo process). Only
that exact path is added to the central gate; all deeper catalog
GETs, downloads, original apply-status, preview/verify endpoints and
unknown variants remain 404, and every unsafe method on `/admin`
remains the unchanged quiet 204 cut before body parsing and
dispatch.

This is NOT full catalog browsing: body previews, run detail,
uploads/proposals, attachments, downloads, live apply status and
process settings remain closed for later same-PR suffixes. The page
is built ONLY from the gate-validated request-local demo state and
its exact session target through the existing
`demo_display_reader_factory(...).read_index()` seam (the reader's
database-side read-only / `current_database()` checks stay
authoritative). To be precise about credentials: reaching the
handler first required the gate's LIVE demo-control authorization
(reads on the `demo_control` rows under the demo web role), and the
index read itself uses the operator's restricted SELECT-only
copy-reader credential against the verified target copy only. What
the handler never touches: source public business tables, live
operator custody, the catalog HMAC seal, Redis, the worker
filesystem, provider network or provider credentials.

### What the page shows

* only the closed `catalog/...` remapped leaves of the verified
  target-only display index (runs, jobs, uploads, proposals), each
  projected to: area, remapped demo run/job ID, bounded remapped
  artifact name, closed kind, byte count and the per-leaf capture
  time (UTC);
* a structural first-column ordinal and the current link-based
  sortable headers (the shared `table-sort.js`);
* the bounded-index wording: at most 4,096 entries (the existing
  display-index cap) with an explicit no-completeness-claim beyond
  that bound;
* the separate-phase wording: each capture time belongs to that
  file's own bounded file-capture phase, distinct from the database
  snapshot time;
* the explicit no-authority wording: the sanitized display copy
  carries no original seal or apply authority and proves nothing
  about live operator state;
* if no catalog leaves are present: exactly "This copy has no
  captured catalog artifacts" plus the note that this does not
  establish whether operator catalog storage was configured (no
  inference);
* if the display index is missing/corrupt/unreadable, or a row
  violates the closed remapped name law (bounded areas, remapped
  run/job ID shapes, bounded ASCII artifact segments, no dot
  traversal), the bounded kind/size law or the finite
  representable-time law: the whole page fails to ONE fixed safe
  unavailable note (503, no raw DB value, path or traceback).

Source paths, original run/job IDs, seal/HMAC values and secret
material never exist in the index and are never rendered; no
download URL is derived.

### Reachability

The demo-only dashboard carries one "Catalog snapshot" card
linking the exact index path (the normal dashboard is unchanged and
the top navigation gains no item). No other link or route was
added; no body reader, download endpoint, background job or worker
change exists in this round.

### Remaining closed surface after 224-k

Every catalog path except the exact index (proposals, collect,
review, export-baseline, run/job artifacts, apply-status, package
downloads, verify) stays default-denied (404 GET / quiet 204
unsafe), and body previews, run detail, uploads/proposals browsing,
downloads and live apply status remain closed for later same-PR
suffixes. Objective 225 remains the installed acceptance gate.

### Evidence (224-k)

* Focused unit (new `test_demo_catalog_index.py` + `test_demo_web.py`
  224-k section): the pure projection accepts the four canonical
  remapped catalog areas (24-hex `demo-run-...` ids, 32-hex job
  ids, bounded artifact segments, closed kinds, bounded sizes,
  finite representable capture times) and fails the whole index
  safely on source-like ids, overlong names (>200 chars), dot
  traversal, unknown areas, bad kinds/sizes/times (bool, negative,
  NaN/Inf, unrepresentable, above the size bound), non-dict leaves
  and >4096 rows; the gate admits EXACTLY `/admin/operations/catalog/`
  (no session -> demo-entry redirect) and keeps every near-miss
  404; the exact path and deeper catalog paths answer every unsafe
  method with the quiet 204 cut (200 KB garbage body never
  parsed); the gated positive page (mocked reader) renders the
  remapped metadata with comma byte counts and per-leaf UTC capture
  times, `private, no-store`, the bounded-index / separate-phase /
  no-seal wording, and no copy name or credential; the
  empty-catalog and reader-failure states render their exact
  honest notes; corrupt-row canaries (source-like id, secret-shaped
  kind, traversal, oversized name) fail the whole page to the safe
  note without rendering any raw value; the handler refuses
  without gate-validated request-local state (404); the demo
  dashboard shows the card once while the normal dashboard stays
  unchanged; the usability/table-rows inventories accept the new
  table (57 sortable tables, structural ordinal + authored
  empty-state row).
* Owned PostgreSQL 16 (real reader role, real worker chain, two
  concurrent sessions on distinct copies): for BOTH sessions the
  exact index path renders 200 with the banner and
  `private, no-store`; the owned fixture has NO configured catalog
  source, so the honest state is the empty-catalog note ("0
  captured catalog artifacts", "This copy has no captured catalog
  artifacts", "does not establish whether operator catalog storage
  was configured") — no real catalog artifact was displayed or
  claimed, and positive artifact rendering is proven by the mocked
  unit coverage only (the complete configured-file installed
  workflow is reserved for objective 225); the source database,
  custody path, worker credential, copy names and reader role never
  appear in the HTML; the near-misses stay 404; the unsafe methods
  stay quiet 204; and the whole read/POST/logout phase leaves the
  source and BOTH copies unchanged (existing invariance counts).
* Real Chromium at desktop width (1280x720): the dashboard
  "Catalog snapshot" card navigates to the index page, which
  renders 200 with `private, no-store`, the demo banner/nav, the
  bounded-index note, the sortable table with the authored
  empty-state row and the no-storage-inference note; the top
  navigation still lists the same fourteen sections (no 15th item).
  One screenshot is saved to a run-owned /tmp path (never committed
  and not in ordinary application logs) and was visually
  inspected.

## Sanitized display-copy artifact download (objective 224-l)

224-l (same PR #383) lets the authenticated demo visitor DOWNLOAD
the already-published sanitized catalog artifacts from the 224-k
index: ONE demo-only handler for the exact
`GET /admin/operations/catalog/artifact`, admitted through the
central gate like the index. Each Artifact cell on the index page
is now a normal hyperlink to that path carrying the exact remapped
logical name as its bounded `name` query selector; the ordinal
column and sortable headers are unchanged and no action column is
added. This is a SANITIZED DISPLAY COPY download only: the body
carries no original seal and no apply authority, proves nothing
about live operator state, and is served exclusively as a forced
file attachment — it is never rendered inline as active content,
even for an artifact named `REVIEW.html`.

The `name` value is a selector ONLY — never authorization, HMAC,
replay, apply or source-file authority. Before ANY body query it
must satisfy the same closed remapped catalog name law as the 224-k
index (bounded areas, remapped run/job ID shapes, bounded ASCII
artifact segments, no dot traversal, ≤200 chars); unknown,
non-catalog, traversal, source-like or overlong values — and
duplicate/unknown query parameters — get ONE fixed safe 404 with
no input echo. The leaf is selected by ONE parameterized exact
`logical_name` lookup (no SQL identifier interpolation, no
pathname).

The read uses the gate's SAME request-local copy engine
(`get_sessionmaker_from_app` on `request.state.demo_admin` — the
only copy binding a demo request may use): one read-only
transaction that FIRST re-verifies `current_database()` equals the
session's exact verified copy and `transaction_read_only` is `on`,
then reads `kind`, `byte_count`, `sha256` and
`octet_length(body)` (computed by the database, so a corrupt row
that claims a small size while storing an oversized body is
refused before any body bytes transfer). Invalid closed
kind/name/size/hash, or a stored body length that disagrees with
the claimed count, is ONE fixed safe 503. The existing 32 MiB
catalog per-file maximum (`DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES`
default; the worker's bundle cap is tighter) is enforced BEFORE
any body fetch, and the bytea is fetched by a second parameterized
query that re-asserts kind, byte count, SHA256 and the cap as bound
parameters. The fetched body must match the exact byte count AND
SHA256 or the request is the same fixed safe 503 — an
incomplete/corrupt artifact is never labeled complete.

A successful download carries `application/octet-stream`, forced
`Content-Disposition: attachment` with the safe ASCII basename,
`X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'` and
`Cache-Control: private, no-store` (the 404/503 refusals are the
fixed safe HTML bodies, also `private, no-store`). The stored SHA,
copy name, DSN,
credential, source path, raw original, HMAC receipt or server error
never appears in the public response. The handler never touches
source public business tables, live operator custody, the catalog
seal, Redis, the worker filesystem, provider network or provider
credentials; there is no global cache and no content persistence.
Every unsafe method on `/admin` (including this path) remains the
unchanged quiet 204 cut before body parsing and dispatch; all
deeper catalog GETs and the original custody-backed catalog routes
are untouched.

### Evidence (224-l)

* Focused unit: the shared closed name law (`_catalog_name_parts`)
  accepts the four canonical remapped shapes and refuses every
  unknown/non-catalog/traversal/source-like/overlong selector; the
  gate admits EXACTLY the artifact path (no session -> demo-entry
  redirect) and keeps every near-miss (trailing slash, prefix
  sibling, deeper path) 404; zero-active accounts are 404; every
  unsafe method is the quiet 204 cut (200 KB garbage body never
  parsed); missing/empty/duplicate/unknown query parameters and
  abusive selectors are fixed 404s with no echo and NO copy query;
  the handler's own in-transaction recheck (wrong database or
  read-only off) is a fixed 503 with no SQL executed; a missing
  leaf is 404 after exactly one parameterized metadata lookup;
  every invalid single-field metadata corruption (uppercase kind,
  unbounded kind, negative/bool size, claimed or actual length
  above 32 MiB, non-hex/short/long/non-str/null digest, actual
  length disagreeing with the claimed count, null metadata) is a
  fixed 503 in which the body query NEVER runs; a re-fetched row
  that no longer satisfies the bounded conditions (bound
  parameters: name, kind, size, digest, cap) or a body whose length
  or SHA disagrees is a fixed 503 with no bytes served; the
  positive case is byte-accurate with the full forced-attachment
  header set and no stored hash/DSN/credential echo; an artifact
  literally named `REVIEW.html` is still a forced octet-stream
  attachment; the rendered index links each row to the exact
  remapped name and the mocked-ASGI follow of that rendered href
  serves the byte-accurate body.
* Owned PostgreSQL 16 (real target-only `demo_display.leaves`
  table, real restricted reader role, two sessions on distinct
  copies): one TEST-ONLY sanitized `catalog/jobs/<32hex>.json`
  leaf inserted into copy A through the owned target-owner
  connection (honest label: this proves transport/binding through
  the real table and role, NOT 223 source-file capture or
  sanitization — the configured-file installed workflow remains
  objective 225). Session A receives the byte-accurate body with
  `application/octet-stream`, forced attachment, nosniff, locked
  CSP and `private, no-store`, with the stored digest and copy
  name never echoed; session B is a fixed safe 404 for the same
  selector (copy isolation); duplicate/unknown query parameters
  and a traversal selector are fixed 404s with no echo; corrupting
  the stored SHA or the claimed byte count in copy A is the fixed
  safe 503 without any body bytes; the artifact path and a deeper
  catalog path stay the quiet 204 cut; the synthetic leaf is
  deleted afterwards and the 404 re-proven, leaving the
  worker-published state unchanged (the existing public-table
  invariance counts still hold).
* Real Chromium: the owned browser fixture has NO configured
  catalog leaf, so the honest empty index page renders NO download
  link at all and the exact artifact path is a fixed safe 404 in
  the real browser; the positive rendered-link transport is proven
  by the mocked-ASGI follow test above (that limit is stated, not
  papered over).
* Direct hosted 224-k CI defect: the stale
  `test_table_wrappers_are_labeled_and_focusable` wrapper count
  (51 -> 52) is repaired in this round after verifying the new
  labeled/focusable catalog table wrapper; the strict wrapper
  checks are preserved.

## Sanitized catalog run detail (objective 224-m)

224-m (same PR #383) adds ONE demo-only
`GET /admin/operations/catalog/runs/{run_id}/` handler to the same
demo catalog router, mounted ahead of the normal custody-backed
routes, which remain unchanged. It displays ONE captured run's
sanitized `validation.json` summary plus the bounded list of the
run's seven captured artifacts from the visitor's OWN verified
copy. This is a HISTORICAL SNAPSHOT DISPLAY: the page carries no
original seal, no live run status and no apply authority, and the
sanitized copy proves nothing about the original run's readiness or
identity. A prominent neutral banner states exactly that, and the
snapshot state/generation time are labeled historical, not live.

The central gate admits ONLY the exact canonical remapped run-id
shape — `demo-run-` plus 24 lowercase hex and a required trailing
slash; near misses, uppercase/other-length hex, missing slash,
prefix/deeper siblings and noncanonical or source-like run IDs are
not admitted (404 with no echo). The catalog index links the
remapped run ID only on run rows (jobs keep their plain cells); the
artifact cells still link to the exact 224-l forced-attachment
download, and the run-detail page links each of the seven captured
artifact names to the SAME 224-l exact download path (full remapped
logical name, forced octet-stream attachment, never inline) —
there is no second download mechanism and no new action button.

The read uses the gate's SAME request-local copy engine
(`get_sessionmaker_from_app` on `request.state.demo_admin`). In ONE
read-only transaction the handler FIRST independently re-verifies
`current_database()` equals the session's exact verified copy and
`transaction_read_only` is `on`, then reads a BOUNDED inventory for
exactly this remapped run: the closed seven worker-published run
content files (`catalog-refresh.json`, `catalog-baseline.json`,
`routes-proposal.tsv`, `pricing-proposal.tsv`, `fx-proposal.json`,
`validation.json`, `REVIEW.html` — a closed name/kind set, never a
directory scan) through one parameterized `IN (...)` lookup with
per-row kind, byte count, SHA256, `octet_length(body)` (computed by
the database before any body transfer), and capture-time checks. A
missing run is a fixed safe 404; an incomplete run (1..6 of the
seven files), any corrupt row, or a driver failure is ONE fixed
safe 503 with no raw value, path or traceback echoed. Only then is
`validation.json`'s body loaded through the shared 224-l bounded
fetch (metadata first, 32 MiB cap before body, bound-parameter
re-asserts, exact length + SHA256 after fetch).

The stored body is re-proved against the worker's exact typed
`demo-display-1` / `validation_json` shape spec
(`demo_snapshot_files._verify_json_policy`) and the document's run
ID must equal the exact gate-admitted run ID before anything
renders. The page renders only bounded sanitized fields already
present in that projection: snapshot state, run generation time
(historical, UTC) and policy version; "count categories retained"
(the number of count categories the sanitized copy keeps from the
original counts map — explicitly NOT a count of catalog or model
entries); bounded per-provider totals (each the sum of that
provider's original count metrics in the captured run, not a model
or request count); and bounded warnings, dispositions and price
comparison rows (signed percent values, no sign doubling). Free-
text detail (state reasons, evidence) is neutralized and never
displayed, and gates and the apply plan are not displayed. The
artifact list is a compact ordinal-first sortable table
(artifact, kind, bytes, captured UTC) with download links. The
page and every 404/503 refusal are `private, no-store`; every
unsafe `/admin` method remains the unchanged pre-body quiet 204
cut. The stored SHA, copy name, DSN, credential, source path,
original run ID, HMAC receipt or server error never appears in
the public response; the handler never touches source public
business tables, live operator custody,
the catalog seal, Redis, the worker filesystem, provider network or
provider credentials.

### Evidence (224-m)

* Focused unit (mocked ASGI, no database): canonical run-id
  admission and every near-miss denial; zero-active accounts 404;
  every unsafe method the quiet 204 cut before body parsing;
  missing demo state and noncanonical/source-shaped ids 404, and a
  gate-admitted CANONICAL id whose demo state lacks a usable
  request-local sessionmaker is a fixed safe 503;
  the handler's in-transaction binding recheck (wrong database or
  read-only off, after the gate passes) is a fixed 503; a missing
  run is 404 after one parameterized inventory; every incomplete
  row set (1..6 of 7) and every corrupt row (wrong kind, bad
  digest, size/actual mismatch, bad capture time) is a fixed 503
  with no echo; a validation body that is non-JSON, belongs to
  another run, or fails the typed re-proof is a fixed 503; the
  positive page renders the sanitized fields (real 223
  sanitizer-produced synthetic projection as fixture), escapes an
  HTML canary, renders exactly the seven forced-download links and
  no original run ID or copy name; the index links the remapped run
  ID on run rows only.
* Owned PostgreSQL 16 (real target-only `demo_display.leaves`
  table, real restricted reader role, two sessions on distinct
  copies): after the worker run and its honest empty-index
  assertions, ONE synthetic run's seven TEST-ONLY leaves are
  inserted into copy A through the owned target-owner connection
  (honest label: only the `validation.json` body is ACTUAL 223
  sanitizer output for a synthetic original document; the other
  six bodies are harmless `b"{}"` test-only placeholders and are
  NOT valid typed outputs for their kinds — this proves
  route/reader/inventory transport/binding, NOT complete worker
  publication or artifact content validation; the configured-file
  installed workflow remains objective 225). Session A receives the
  200 page with the banner, bounded fields and all seven
  forced-download hrefs, with neither the copy name nor the
  original run ID echoed; session B is a fixed safe 404 for the
  same canonical path (copy isolation); the missing-trailing-slash
  near miss stays 404; corrupting the stored SHA or reducing the
  run to six of seven files is the fixed safe 503; the path stays
  the quiet 204 cut. The seven leaves are deleted afterwards by
  EXACT names (never a prefix match) and the 404 re-proven,
  leaving the worker-published state unchanged.
* Real Chromium: the owned browser fixture has NO configured run,
  so the canonical run-detail shape is a fixed safe 404 in the
  real browser (honest empty state; the positive page is proven by
  owned-PG transport and mocked-ASGI coverage above, and the
  configured-file installed browser workflow remains objective
  225).
