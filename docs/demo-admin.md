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

## Captured proposals page (objective 224-n)

224-n (same PR #383) opens ONE existing GUI path as a demo-only
`GET /admin/operations/catalog/proposals` in the existing demo
catalog router, admitted in the central gate by exact path only
(near misses, extra suffixes and the `/generate` POST family stay
refused; every unsafe `/admin` method remains the unchanged pre-body
quiet 204 cut). The normal custody-backed proposal handler, template
behavior and routes are unchanged; the demo page links from the
catalog index header without adding a top-nav item.

The page renders the FAMILIAR proposal form controls as an
ILLUSTRATIVE demo-only form: the static provider-scope/currency/
endpoint/preset options are fixed product vocabularies, the model-ID
choices are COPY-BACKED (read SELECT-only from this visitor's copy
`catalog_upstream`; a failed copy query is a fixed safe refusal,
never a silent empty dropdown), and a prominent neutral banner
states that submitting has NO effect (no job is generated and no
provider is called) — the form submit remains a no-op through the
gate. Live operator settings, source catalog custody, ambient
credentials, the worker filesystem and the original HMAC seal are
never read.

Below the form, the page presents a bounded, clearly HISTORICAL list
of the captured `catalog/proposals/<remapped-job-id>/...` artifact
leaves from the verified target-only display index: the worker's
closed file law (six top-level proposal files AND optional
`packages/<closed-preset>/<five closed files>` entries) with per-row
kind/size/capture-time validation, grouped by remapped job ID,
sorted most-recently-captured first, AT MOST 100 groups with the
bound stated on the page. A native selection control offers the
captured groups (usable labels + help) and accepts only ONE canonical
optional `job` query value: unknown, duplicate or extra parameters
refuse safely (fixed 404) without falling back to another job. For
the selected group, only the captured artifacts actually present are
listed, each linked through the exact 224-l forced-attachment route
(never inline). When the same copy holds the group's sanitized
`catalog/jobs/<same id>.json` record, ONLY that body is loaded —
metadata-first, the existing 32 MiB cap BEFORE the body, exact
length + SHA256 after — re-proved against the worker's typed
`job_record` shape with `family=proposal` and the EXACT selected job
ID required before status/created/updated render, labeled
historical at capture time (not live or actionable). A missing
record shows a bounded "status unavailable in this snapshot" note; a
corrupt record or corrupt index row is ONE fixed safe 503 with no
raw echo. The label law is exact: the list covers captured proposal
ARTIFACT leaves only — a status-only job without captured artifacts
is not listed, and an empty list never means the copy has no
proposal jobs (or that operator catalog storage was configured).
The read runs in ONE read-only transaction on the gate's SAME
request-local copy engine with the independent `current_database()`
/ `transaction_read_only` recheck; the inventory SELECT carries a
BOUND row limit (`LIMIT 4097`), transferring at most 4,097 metadata
rows and refusing when the bound is reached. Every output is
`private, no-store` and Jinja-escaped; no source path, original job
ID, manifest field, DSN, credential or copy name ever renders.

### Evidence (224-n)

* Focused unit (mocked ASGI, no database; all new `test_proposals_*`
  tests passed, exit 0): exact path admission and every near-miss
  denial; zero-active 404; every unsafe method (including
  `/proposals/generate` and imports/cancel paths) the quiet 204 cut
  with a 200 KB body never parsed; the query law refuses duplicate,
  extra, unknown, empty, wrong-length, uppercase, non-hex and
  overlong `job` values with fixed 404s BEFORE any copy-seam access
  (proven by a call-recording refusing sessionmaker plus the
  zero-call assertion); a gate-admitted page whose demo state lacks
  a usable sessionmaker is a fixed 503; the in-transaction binding
  recheck (wrong database or read-only off, after the gate passes)
  is a fixed 503 with zero copy queries; the inventory bound (a
  4097-row result) is a fixed 503 and the statement carries the
  bound `LIMIT :limit` parameter; an
  honest empty page (demo banner, illustrative form, empty-group
  note with the no-inference wording, no custody last-job section,
  no copy-name echo); the positive page (fixture = ACTUAL 223
  sanitizer job-record output for a synthetic original record)
  selects the most-recently-captured group by default, honors an
  explicit `?job=` selection, renders both captured artifacts (top
  level + closed preset) through the exact 224-l forced-download
  hrefs, the typed historical status/times, the stated 100 bound,
  and never the original job ID, progress free text or copy name;
  the bound-parameter body re-asserts are verified on the recorded
  statements; a job without a record leaf shows the bounded
  "status unavailable" note; every job-record refusal (non-JSON,
  foreign family, different job ID, size mismatch, and a metadata
  size above 32 MiB in which the body query NEVER runs) is a fixed
  503 with no echo; an unknown canonical `job` value is a fixed 404
  with no fallback; a 101-group inventory lists exactly 100 with
  the oldest dropped; every closed-file-law corruption (unknown
  file, unknown preset, unknown package file, bare `packages`
  segment, kind mismatch) is a fixed 503; a model-option HTML
  canary renders escaped/inert; the index header links the page.
  Directly affected unit files re-run green (290 passed).
* Owned PostgreSQL 16 (real target-only `demo_display.leaves`, real
  restricted reader role, two sessions on distinct copies): after
  the worker run and its honest empty-index assertions, ONE
  test-only captured proposal job is inserted into copy A through
  the owned target-owner connection (honest label: the two TSV
  bodies are `b"{}"` test-only placeholders and are NOT valid TSV
  content for their kinds — the page reads only their metadata,
  never artifact bodies; the job record body IS actual 223
  sanitizer output for a synthetic original record; this proves
  route/reader/inventory transport/binding, NOT 223 source capture,
  worker publication or sanitization of a real job — the
  configured-file installed workflow remains objective 225).
  Session A receives the 200 page (demo banner, the one captured
  artifact group selected, both exact forced-download hrefs, typed
  historical status `ready` with created/updated, no original job
  ID or copy name); explicit selection, an unknown canonical job
  and duplicate/extra query parameters behave as the fixed 404
  refusals; session B (its own exact copy, no proposal leaves)
  renders the honest empty artifact-group state (copy isolation);
  corrupting the stored SHA on the job record is the fixed safe 503
  without body echo; the path stays the quiet 204 cut; the three
  leaves are deleted afterwards by EXACT names (`ANY($1::text[])`,
  never a prefix match) and the empty state re-proven.
* Real Chromium: the owned browser fixture has NO configured
  proposal leaves, so the page renders 200 in the real browser with
  the demo banner, the illustrative form and the honest empty
  artifact-group state (stated limit; the positive page is proven
  by owned-PG transport and mocked-ASGI coverage; the
  configured-file installed browser workflow remains objective 225).

## Collect page and captured complete runs (objective 224-o)

224-o (same PR #383) opens ONE existing GUI path as a demo-only
`GET /admin/operations/catalog/collect` in the existing demo catalog
router, admitted in the central gate by exact path only (near misses
and subpaths such as `/collect/submit` stay refused; every unsafe
`/admin` method remains the unchanged pre-body quiet 204 cut, and no
body is ever parsed). The normal custody-backed collect handler,
template behavior and route families are unchanged; the demo catalog
index header links the page alongside the captured-proposals link
(no new top-nav item).

The page renders the familiar collect form controls and their help
as ILLUSTRATIVE demo-only controls: the mode/provider options are
fixed product vocabularies, the model-ID choices are COPY-BACKED
(one SELECT-only read of `catalog_upstream` through the gate's SAME
request-local copy engine; a failed copy query is a fixed safe 503
refusal, never a silent empty dropdown), the optional baseline file
input and the research control are displayed for inspection only,
and a neutral banner states that submitting has NO effect (no source
is collected, no baseline is imported, no provider or research is
called). Live setup is never falsely claimed: the page does NOT
display a live DATABASE_URL availability state and does NOT infer
research-runner configuration from the absence of a demo secret —
narrowly scoped demo text states that live setup (DATABASE_URL) and
the research runner are NOT available to this copy. Ambient
production settings, credentials, live catalog files, the provider
network and the research runner are never read.

Below the form, the page presents a bounded, clearly HISTORICAL list
of at most the 100 most-recently-captured COMPLETE catalog run
groups from the target-only `demo_display.leaves` metadata, labeled
as covering ALL acquisition paths (the list is explicitly NOT
attributed to the collect form): each group must contain the
worker's closed seven sealed-run content files exactly once (exact
remapped run ID, kind/size/capture-time metadata checked, no body
transfer); a partial group (1..6 of the seven files), a wrong
kind/size/time, a duplicate file row or the server-side row bound
(transferring at most 4,097 metadata rows via a BOUND `LIMIT 4097`)
is a fixed safe 503, never silently omitted. The 100-group bound is
stated on the page. Each run links to the exact 224-m historical
run-detail page (never the original custody). The label law is
exact: an empty run list proves neither that no collect job exists
nor that live catalog storage is unconfigured, and status-only jobs
without captured complete runs are not listed; no live job state or
original seal/apply readiness is shown. The read runs in ONE
read-only transaction on the gate's SAME request-local copy engine
with the independent `current_database()` / `transaction_read_only`
recheck; the demo page defines NO query parameters, so ANY query
string refuses with a fixed 404 before any copy-seam access. Every
output is `private, no-store` and Jinja-escaped; no source path,
original run ID, DSN, credential or copy name ever renders.

### Evidence (224-o)

* Focused unit (mocked ASGI, no database; all new `test_collect_*`
  tests passed, exit 0): exact path admission and every near-miss /
  subpath denial (including the `/submit` GET); zero-active 404;
  every unsafe method on the page path and `/submit`/
  `/export-baseline` paths the quiet 204 cut with a 200 KB body
  never parsed; the query law (any parameter, including the normal
  page's `job` value) a fixed 404 BEFORE any copy-seam access
  (proven by a call-recording refusing sessionmaker plus the
  zero-call assertion); a gate-admitted page whose demo state lacks
  a usable sessionmaker a fixed 503; the in-transaction binding
  recheck (wrong database or read-only off, after the gate passes) a
  fixed 503 with zero copy queries; the inventory bound (a 4097-row
  result) a fixed 503 with the bound `LIMIT :limit` parameter
  verified on the recorded statement; the honest empty page (demo
  banner, illustrative form with every familiar control, the
  no-false-availability demo wording — the normal "shown as"
  live-DB text never renders — the research "not available in this
  copy" wording, the honest empty complete-run state with the
  no-inference note, no custody last-job section, no copy-name
  echo); the positive page (two complete seven-file groups) links
  each run to the EXACT 224-m run-detail path, most-recently-
  captured first, with the per-group file count/bytes/capture
  metadata, the stated 100 bound, the all-acquisition-paths
  labeling, and NEVER a body transfer (verified on the recorded
  statements), no original run ID or copy name; every partial group
  (1 and 6 of 7 files) a fixed 503; every closed-file-law
  corruption (unknown file, deeper runs path, kind mismatch) a
  fixed 503; a 101-group inventory lists exactly 100 with the
  oldest dropped; a model-option HTML canary rendered escaped/inert;
  the index header link.
* Owned PostgreSQL 16 (real target-only `demo_display.leaves`, real
  restricted reader role, two sessions on distinct copies): after
  the worker run and its honest empty-index assertions, ONE
  test-only captured complete run's seven sealed-run content leaves
  are inserted into copy A through the owned target-owner
  connection (honest label: ALL seven bodies are `b"{}"` test-only
  placeholders and are NOT valid sealed-run content for their kinds
  — the collect page reads only their metadata, never any run
  body; this proves route/reader/inventory transport/binding, NOT
  223 source capture, worker publication or sanitization of a real
  run — the configured-file installed workflow remains objective
  225). Session A gets the 200 page (demo banner, the one captured
  complete run group linked to the exact 224-m run-detail path,
  seven-file metadata, the stated bound, no original run ID or copy
  name, no false live-availability claim); session B (its own exact
  copy) renders the honest empty complete-run state with the
  no-inference note (copy isolation); reducing the run to six of
  the seven files is the fixed safe 503 with no run ID echo; the
  path stays the quiet 204 cut; the seven leaves are deleted
  afterwards by EXACT names (`ANY($1::text[])`, never a prefix
  match) and the empty state re-proven.
* Real Chromium: the owned browser fixture has NO configured run
  leaves, so the collect page renders 200 in the real browser with
  `private, no-store`, the demo banner, the illustrative form and
  the honest empty complete-run state (stated limit; the positive
  page is proven by owned-PG transport and mocked-ASGI coverage;
  the configured-file installed browser workflow remains objective
  225).

## Review / export / job-record pages (objective 224-p)

224-p (same PR #383) opens THREE more existing catalog GUI paths as
demo-only exact GETs in the existing demo catalog router, admitted in
the central gate by exact path only: `/admin/operations/catalog/review`,
`/admin/operations/catalog/export-baseline` (both take NO trailing
slash) and `/admin/operations/catalog/jobs/` (REQUIRED trailing
slash). Near misses, source IDs and subpaths (including every
`/submit`, cancel/remove and upload POST path) stay 404; every unsafe
`/admin` method remains the unchanged pre-body quiet 204 cut (no body
is ever parsed, no provider, source, file, DML, accounting or mail
effect). The normal custody-backed review/export handlers, template
behavior and routes are unchanged; the demo catalog index header links
the three pages with concise labels (no new top-nav item).

The review and export pages reuse their familiar controls and help as
clearly ILLUSTRATIVE demo-only forms: review keeps the bundle/baseline
file inputs and first-install checkbox; export keeps its export action
description. Submitting has NO effect (no bundle is sealed or
reviewed, no baseline is exported, no provider or research is called)
and no request body is ever parsed by the demo gate. Live setup
(DATABASE_URL) and operator source custody are NOT available to this
copy and are never inferred: the export page's normal "Database
target: configured / not configured" line is suppressed by its narrow
`{% if demo_admin %}` template branch (which renders a fixed
"NOT available to this demo copy" line instead), and neither page
claims a live configuration or renders the NORMAL custody-backed
`last_job` sections or their links as live (the demo context passes
`last_job=None`, so those branches never render). Both forms link the
captured historical job-record page. `_setup_context`, `_settings`, a
live job resolver, the normal review/export handlers, provider/research
runners and original file paths are never called. Each form page opens
ONE SELECT-only/read-only copy transaction carrying the independent
`current_database() == demo.target_db` / `transaction_read_only = on`
recheck; ANY query string on these two pages refuses with fixed 404
BEFORE copy access.

The job-record page (`/jobs/`) lists at most the 100
most-recently-captured `catalog/jobs/<remapped-32hex>.json` metadata
rows from the target-only `demo_display.leaves`, covering EVERY
captured job family (collect, supplied-bundle review, baseline export,
proposals) — the generic history is NOT attributed to any one demo
form and must not be read as exclusively review or export jobs. The
read runs in ONE read-only transaction on the gate's SAME
request-local copy engine with the independent recheck and a BOUND
`LIMIT :limit` inventory (transferring at most 4,097 metadata rows,
refusing when reached); no body is transferred while listing. The
closed remapped name, exact `job_record` kind, <=1 MiB metadata size,
canonical SHA256, finite representable capture time and
duplicate/unknown jobs-area shape are checked before rendering (any
violation is the fixed safe 503, never silently omitted). The count
and the 100 bound are stated truthfully on the page; an empty list
does not prove live catalog storage was unconfigured or that no job
ran. The selector accepts ZERO parameters or exactly ONE canonical
`job=<remapped-32hex>` value chosen from the bounded list; duplicates,
extra, unknown, missing/overlong or noncanonical values refuse fixed
404 BEFORE body transfer (structurally invalid values before copy
access), never falling back to another job; without a selector the
most-recently-captured record is chosen.

For ONLY the selected job, the sanitized body is fetched from the
SAME copy after metadata validation, with the 1 MiB cap re-asserted as
a bound parameter before transfer, exact size + SHA256 re-checks, the
existing 223 typed `job_record` re-proof, and the body job ID required
to equal the selected remapped ID (finite family/status vocabulary).
Only the sanitized family, HISTORICAL status (labeled frozen at
capture time, not live or actionable), created/updated/captured times,
neutral (neutralized) progress, cancel-requested, dispatch and
explicit `error_code=None` render. A remapped run reference is linked
to the exact 224-m run-detail page, and a remapped upload reference to
the 224-l forced download, ONLY when the matching captured
target-only leaf is independently verified from the same bounded
metadata inventory (all seven sealed-run content leaves with their
exact kinds, or the exact upload leaf with its expected closed kind
and closed metadata); otherwise the reference renders as plain text.
No original ID, source path or copy DB name ever renders. Corrupt
body, mismatched ID/kind/SHA/size or read failure is the fixed safe
503 with no raw echo. Every output is `private, no-store` and
Jinja-escaped. No schema, worker, sanitizer, custody, normal router,
Compose/Nginx or public endpoint change.

### Evidence (224-p)

* Focused unit (mocked ASGI, no database; all new `test_p_*` tests
  passed, exit 0): the three exact paths admitted and every near
  miss/subpath denied (including the missing-slash jobs path);
  zero-active 404; every unsafe method on the page paths and the
  submit/cancel/remove/upload subpaths the quiet 204 cut with a
  200 KB body never parsed; the review/export query law (ANY
  parameter, including a `job` value) a fixed 404 BEFORE any
  sessionmaker/copy access (proven by a call-recording refusing
  sessionmaker with the zero-call assertion); the jobs query law
  (duplicate/extra/unknown/empty/wrong-length/uppercase/non-hex/
  overlong) fixed 404 BEFORE copy access, a structurally valid but
  unknown canonical id fixed 404 AFTER the inventory with no body
  transfer and no fallback; a gate-admitted page whose demo state
  lacks a usable sessionmaker a fixed 503 on all three pages; the
  in-transaction binding recheck (wrong database or read-only off,
  after the gate passes) a fixed 503 on all three pages with zero
  copy queries; the inventory bound (a 4097-row result) a fixed 503
  with the bound `LIMIT :limit` parameter verified on the recorded
  statement; the honest empty jobs page (no-inference note, no
  body transfer); the positive page (two ACTUAL 223 sanitizer
  outputs for synthetic original records): newest-first ordering,
  default and explicit selection, the sanitized typed fields, the
  neutralized progress (free text never renders), the explicit
  `error_code=None`, BOTH independently verified references linked
  to the exact 224-m/224-l paths, the bound 1 MiB cap/exact
  name/size/digest parameters verified on the recorded body
  statement, no original IDs or copy name; unverified references
  (a six-of-seven captured run, an absent upload leaf) rendered as
  PLAIN TEXT with the non-inference note while the page still
  renders; every metadata-law corruption (wrong kind, over 1 MiB,
  noncanonical SHA, duplicate record, unknown jobs-area shape,
  deeper jobs path, non-finite capture time) a fixed 503 with no
  row echo; a 101-record inventory lists exactly 100 with the
  oldest dropped; every body refusal (stored SHA/size mismatch,
  foreign job id, unknown family vocabulary at the 223 typed
  re-proof, absent row) a fixed 503 with no raw body echo; the
  review/export illustrative pages (familiar controls render, the
  NORMAL last-job sections and their links never render, no
  "Database target" claim on export, the jobs-page link present,
  zero copy queries beyond the recheck); the index header links.
* Owned PostgreSQL 16 (real target-only `demo_display.leaves`, real
  restricted reader role, two sessions on distinct copies): after
  the worker run and its honest empty-index assertions, ONE
  test-only captured job record plus its captured run's seven
  sealed-run content leaves and its captured upload leaf are
  inserted into copy A through the owned target-owner connection.
  Honest labels: the job record body is the ACTUAL 223 sanitizer
  output for a synthetic original record (family
  `review_supplied`, remapped run and upload references); the seven
  run content bodies and the upload body are `b"{}"` test-only
  placeholders (the jobs page reads ONLY their metadata, never any
  run/upload body) — this proves route/reader/inventory
  transport/binding, NOT 223 source capture, worker publication or
  sanitization of a real job (the configured-file installed
  workflow remains objective 225). Proven: session A gets the 200
  page (the one captured record, sanitized HISTORICAL fields, both
  verified references linked to the exact 224-m/224-l paths, no
  original ids or copy name); explicit selection, an unknown
  canonical job and duplicate/extra query parameters the fixed 404
  refusals without fallback; session B (its own exact copy) renders
  the honest empty state (copy isolation); corrupting the stored
  SHA on the job record is the fixed safe 503 without body echo;
  the path stays the quiet 204 cut; the nine leaves are deleted
  afterwards by EXACT names (`ANY($1::text[])`, never a prefix
  match) and the empty state re-proven.
* Real Chromium (owned fixture, loopback uvicorn): the fixture has
  NO configured job records, so the jobs page renders 200 in the
  real browser with `private, no-store` and the honest empty state
  (no-inference note), and the review/export pages render their
  illustrative demo forms with NO live "Database target" claim
  (stated limit; the positive page is proven by owned-PG transport
  and mocked-ASGI coverage; the configured-file installed browser
  workflow remains objective 225).

Documentation correction (224-o explanatory slip): in the 224-o
report, the suppression of the normal "shown as available / not
configured" live-DB wording on the collect page was attributed to
the handler passing `dispatched=None`. That wording is actually
suppressed by the `{% if demo_admin %}` template branch itself,
which renders the fixed "NOT available to this copy" line instead
of the normal "shown as" line. This section states the mechanism
correctly; it is a documentation correction, not a runtime change.


## Key calibration / clone read pages (objective 224-q)

224-q (same PR #383) opens THREE more existing admin GUI paths as
demo-only exact GETs, admitted in the central gate by exact shape
only: `/admin/keys/<canonical-uuid>/calibration`,
`/admin/keys/<canonical-uuid>/clone` and
`/admin/keys/<canonical-uuid>/clone/receipts`, where the ID must be a
lowercase dashed 8-4-4-4-12 UUID and the suffix exact, with no extra
path components. Malformed, uppercase, undashed or source-like IDs
and every near miss (extra segments, trailing slashes, the
`summary.json`/`configuration.json` attachment GETs, and every
`preview`/`create-template`/`review`/`apply` subpath) stay 404 BEFORE
routing; every unsafe `/admin` method remains the unchanged pre-body
quiet 204 cut. The NORMAL read-only handlers, routes and normal-admin
template output are unchanged - the gate stores the verified
request-local copy sessionmaker and the fictional admin context on
`request.state`, and the normal handlers use them exactly as they do
for every other admitted DB-backed section (the request-local copy
binding is the only copy a demo request may use; a demo request
without it fails closed).

The three GETs are read-only by construction and were verified
against the copied rows only: the calibration form GET loads the
copied key detail and fixed form defaults; the clone form GET loads
the copied key detail, runs the existing pure `build_plan` eligibility
probe (which mutates nothing and writes no audit row) and the
SELECT-only owner/cohort record choices; the receipts GET loads the
copied key detail and, only with a present `operation` selector, the
explicitly read-only receipt projection (no lock, no clone, no
audit, no redisplayed plaintext). Copied key/owner/cohort/receipt
rows are the only dynamic data; no source DB, provider, mail, Redis,
file custody or background job is reached, and the demo process
intentionally carries no live configuration (the fixed neutral
display settings are the only settings in the process).

Narrow `{% if demo_admin %}` template notes (the demo banner stays
visible and every response is `private, no-store`):

* the key detail page now shows the three admitted read links in
  demo mode (calibration for trusted-calibration keys; clone and
  clone receipts for any key detail) with a demo note that those
  pages are read-only views of data frozen at snapshot time and that
  their forms are illustrative; the non-admitted action links
  (Codex compatibility, replay maintenance, the configuration JSON
  download) stay hidden in demo mode;
* the calibration form states that the source key data is a copy
  frozen at snapshot time and that the preview form is ILLUSTRATIVE -
  submitting has NO effect (no calibration preview, key template,
  participant key, route, or pricing is created) and no live
  configuration is read;
* the clone form states that the source key and owner/cohort choices
  are copied rows frozen at snapshot time (their timestamps, limits
  and statuses are as captured in that snapshot) and that the
  eligibility line is COMPUTED FOR THIS COPIED SNAPSHOT AT VIEW TIME
  from those frozen rows only - not a live operational eligibility
  decision; the form is illustrative and submitting has NO effect;
* the receipts page states that any outcome is HISTORICAL, recovered
  from the copy's receipt rows, and that a not-found or unknown
  outcome never implies anything about source operations outside the
  snapshot; the normal guidance that suggests retrying a reviewed
  plan, resubmitting a delivery or rotating a key is suppressed in
  demo mode (kept verbatim for normal renders).

**Sanitizer limitation (224-q).** Clone receipts live in the
`metadata` column of `gateway_keys`, and the current 222 sanitizer
maps that column to an empty value (J0). A real worker-built demo
copy therefore carries NO historical clone receipts, and the
receipts page on a real snapshot always renders the honest
not-found/help state (never implying anything about source
operations outside the snapshot). The 224-q receipts evidence
(mocked-ASGI fake projections plus the target-only owned-PG
insertion) proves route/gate/query-law transport and the honesty of
the not-found state only - NOT receipt availability in a real
snapshot. A bounded sanitizer projection repair that preserves
sanitized clone receipts is a separately ordered follow-up and is
required before objective 224 can be complete.

That follow-up is objective 224-r (below): it repairs the sanitizer
with the dedicated, closed `gateway_keys.metadata` clone-receipt
projection, so a worker-built copy from a source that has a real
clone receipt now carries the projected (remapped) receipt, and the
receipts page can render it positively.

A copied key may be unsupported for calibration or cloning: the
existing safe refusal / eligibility warning renders instead of a
false success. Query handling stays bounded at the gate (raw bytes,
no percent-decode): the calibration and clone form GETs define NO
query parameters in demo and refuse ANY query string with the fixed
default-denied 404 BEFORE session resolution, routing or echo; the
receipts GET accepts zero parameters or exactly ONE raw
`operation=<value>` selector, with the whole raw query checked
against a small byte ceiling before any split and the value bounded
at 64 bytes - duplicates, extra or unknown parameters and overlong
or credential-shaped values refuse (the handler additionally
redacts recognized credential shapes and never uses them as
authority). No plaintext key material, one-time secret, original
source ID, raw metadata or unmasked personal identity is exposed.

### Evidence (224-q)

* Focused unit (mocked ASGI / template-level, no database; the new
  `test_q_*` tests in `test_demo_web.py` and
  `test_admin_key_actions_templates.py` passed, exit 0): the three
  exact shapes admitted (no-session entry redirect) and every
  near-miss/malformed ID/subpath 404; the closed-set inventory
  updated with the three admitted GETs; the query law through ASGI
  with a verified session (calibration/clone ANY query fixed 404;
  receipts zero or exactly one bounded `operation` admitted, proven
  by the handler-rendered page; duplicate/extra/unknown/overlong
  refused; the raw `?` byte form httpx would normalize away refused
  via a raw ASGI scope; oversized whole-query beyond the raw ceiling
  refused before any split); every unsafe method on the page paths
  and the preview/create-template/review/apply subpaths the quiet
  204 cut with a 200 KB body never parsed (anonymous POST 404);
  zero-active 404; the demo key-detail rendering (admitted read
  links + demo note; non-admitted links hidden) and the normal
  rendering unchanged; the calibration demo banner and the existing
  safe 400 refusal for non-trusted copied keys; the clone form demo
  banner with the AT-VIEW-TIME eligibility label; the receipts demo
  banner and the honest created / not-found / projection-error
  outcomes with the retry guidance suppressed in demo and preserved
  in normal renders.
* Owned PostgreSQL/browser fixture (owned PG16 source/target, real
  worker snapshot, real Chromium; target-side insertion of TWO
  test-only key rows into copy A - labeled transport-only evidence,
  NOT 223/222 source capture; the configured-file installed proof
  remains objective 225): the base-key clone/receipts pages render
  with the demo banner; the calibration page is purpose-gated
  (200 banner for a trusted-calibration copied key, the existing
  safe 400 refusal otherwise); the gate query law (404s for
  unexpected, duplicate and overlong selectors); the two inserted
  rows render positively in session A (trusted key detail link +
  calibration page with the frozen/illustrative banner; standard key
  clone form with the AT-VIEW-TIME label; receipts help page and the
  honest not-found for an absent operation) with no copy name,
  reader role or DSN fragment; session B (its own copy, no inserted
  rows) gets honest handler-level 404s (copy isolation); POST on the
  page paths the quiet 204 cut; exact-ID cleanup re-proven by
  404s; the whole phase leaves source and both copies' counts
  unchanged; the real-Chromium key detail shows the admitted read
  links and the receipts page renders the honest help/banner state.

## Clone-receipt sanitizer projection and demo chooser (objective 224-r)

224-r (same PR #383) repairs the sanitizer limitation documented under
224-q: a worker-built demo copy from a source that has a real clone
receipt now carries the projected (per-copy remapped) receipt, and the
224-q receipts page can render it positively. The scope is exactly the
follow-up that was ordered - a dedicated narrow sanitizer projection
plus its verifier proof and the demo chooser. No schema, migration,
route, job or normal-admin change.

* **Sanitizer (`gateway_keys.metadata`, new closed `KR` action).**
  Ordinary metadata is cleared to `{}` exactly as before. A
  recognized, well-formed 208 clone receipt (the exact 17 reviewed
  members, no more, no less) is projected into the copy with EVERY
  identifying value remapped per copy: UUIDs through the global
  per-copy bijection, the source public key ID through the string
  remap, and both fingerprints through the column-salted 64-hex remap.
  The bounded nonsecret validity members and the display status are
  preserved, but each optional timestamp member (`source_valid_until`,
  `validity_from`, `validity_until`) is checked PER FIELD against its
  actual producer's acceptance set (224-s repair): `source_valid_until`
  is always the flow's `datetime.isoformat()` output, so it must be a
  full ISO-8601 timestamp (a bare date can never appear there);
  absolute-mode `validity_from`/`validity_until` are the operator's
  plan text preserved verbatim (the plan schema accepts any
  `datetime.fromisoformat`-parseable ISO-8601 value, and the
  CLI/service clone path persists it raw - a bare ISO date included,
  which the product's own `_aware_fromiso` interprets as midnight UTC;
  the GUI form instead normalizes to a full timestamp), so those two
  members accept any well-formed ISO-8601 value, bare date included.
  Blank, padded and arbitrary free-text values are NOT rewritten or
  discarded - they fail the whole copy closed (nothing is published;
  the error carries only the member name, never the raw value). A
  malformed, unknown or secret-bearing receipt fails the whole copy
  closed likewise. The receipt vocabulary and validity modes are
  imported from the product's own 208 schema constants, so the demo law
  cannot drift from the supported clone flow's shape.
* **Independent post-commit verifier.** On a separate read-only
  connection after commit, the verifier re-proves the per-row
  receipt law: the SET of stored non-empty receipts exactly equals the
  pre-state expectation set; every stored receipt's keyed digest
  (computed from the STORED value, keyed by the per-copy seed and the
  remapped row ID) equals the expectation projected from the RAW
  source receipt before the rewrite, so an adversarial mutation of any
  single projected field fails publication; and link consistency
  holds (the receipt's target ID equals its containing key row, and
  its source ID is a real copied `gateway_keys.id` - no dangling or
  cross-copy links).
* **U-column verifier repair (224-r demonstrated blocker).** The old
  blanket U-distinctness law rejected any repeated FK value, which
  wrongly refused two legitimate gateway keys of the SAME owner - the
  approved demo clone scenario. It is replaced by (a) a per-column
  keyed multiset digest over EVERY U column (pre-state projects the
  raw UUIDs to the expected per-copy remaps; the verifier recomputes
  over the stored values and requires equality), which proves repeated
  FK values keep the SAME per-copy mapping while an un-remapped raw
  value or any substitution breaks it; and (b) a distinctness
  re-check ONLY where the reviewed schema declares a single-column
  UNIQUE or PRIMARY KEY on that column (a composite UNIQUE proves no
  per-column distinctness and is not enforced).
* **S-column verifier repair (224-s demonstrated defect).** The old
  blanket S-distinctness law assumed every remapped string-ID value is
  unique, which wrongly refused `catalog_refresh_applications.
  operator_actor` / `db_actor` - nonunique text fields that naturally
  repeat across applies. It is replaced by the same reviewed pattern
  as the U law: a per-column keyed multiset digest over EVERY S column
  (pre-state projects the raw values through the existing
  `remap_str_id` to the expected per-copy remaps; the independent
  post-commit verifier recomputes over the stored values and requires
  equality), so repeated raw values keep the SAME per-copy remapped
  value while a raw pass-through, a dropped duplicate or a substitution
  fails publication; distinctness is re-checked ONLY where the reviewed
  schema declares a single-column UNIQUE or PRIMARY KEY on that column.
  The structural check for S columns is shape-only.
* **Demo-only chooser (224-r).** On the 224-q receipts page in demo
  mode, a bounded, SELECT-only chooser lists at most the 100 newest
  copied operations whose receipt references this source (a capped
  note when more exist), each linked to the exact 224-q
  `?operation=` selector, which renders the existing read-only
  projection. The chooser runs only on a demo request, on the
  request-local gate-validated copy sessionmaker, and re-verifies
  `current_database()` and `transaction_read_only` inside a read-only
  transaction; a refused or failed copy query is a fixed safe refusal
  (an explicit "unavailable" note), never a silent empty list and
  never a leak. An empty chooser list is an honest
  snapshot-only statement (it does not establish whether the source
  had clone operations).

Guarantee and limits: the receipt and its projection are HISTORICAL
display data frozen at snapshot time. The demo chooser and projection
carry NO replay, retry, delivery or clone authority; selecting an
operation only renders the copied receipt's read-only projection. The
copy is SELECT-only for every demo read, and no plaintext key
material, one-time secret, original source ID or raw metadata is
exposed - only per-copy remapped values.

### Evidence (224-r)

* Focused unit (mocked, no database): the closed KR projection
  (well-formed receipt remapped/preserved; ordinary metadata cleared;
  sibling members dropped; deterministic and seed-dependent; unknown,
  missing, wrong-typed, invalid-UUID, invalid-fingerprint, wrong-mode
  and wrong-status members fail closed; optional UUID nulls stay
  null); the per-field validity law (224-s: absolute-mode
  `validity_from`/`validity_until` accept any well-formed ISO-8601
  value the plan schema can write - full timestamps preserved verbatim
  AND a bare ISO date, which the CLI/service flow persists raw;
  `source_valid_until` accepts only a full timestamp, so a bare date
  there FAILS THE COPY CLOSED; padded/free-text/blank/wrong-type
  non-null values always fail closed with a member-name-only error, and
  the independent structural check rejects a stored value the
  projection could never emit); the GUI-form normalization law (a bare
  date submitted through the guided form is re-emitted as a full aware
  timestamp before the plan is built); the U-column keyed multiset law
  (repeated FK values keep the same remapped value twice; an
  un-remapped raw pass-through, a dropped duplicate or a substitution
  breaks the digest; same column name in a different table has a
  separate key space; per-copy seed dependence); the S-column keyed
  multiset law (224-s: repeated raw actor values keep the same
  remapped value twice; raw pass-through / dropped duplicate /
  substitution break the digest; S key space is separate from U's);
  the declared-unique
  parser (single-column PK/UNIQUE declared, composite UNIQUE
  excluded, non-unique constraints ignored); the demo chooser law
  against REAL SQLAlchemy 2.0 Row objects (the asyncpg/SQLAlchemy
  stack's Row API - 2.0 removed string subscripting from Row):
  no-admin, refused read-only recheck, wrong current database,
  happy path, failed query, no-sessionmaker fail-closed, and the
  101 -> 100 cap.
* Owned PostgreSQL 16 fixture (owned source/target services, real
  worker snapshot + real sanitizer/verifier chain): the positive
  chain runs the SUPPORTED clone flow (208 guided flow - live create
  key, review, apply) against the source for the SAME owner as the
  seeded canary key, so the receipt ground truth is the row the flow
  itself persisted (not a hand-built seed), and its flow-shape
  relationships are asserted before the snapshot (the receipt matches
  the source key's real public ID; its one-time secret is
  TARGET-linked, never a source-linked row). After snapshot +
  sanitize + independent verification, the copy carries exactly the
  expected projection: three copied keys all sharing the ONE remapped
  owner (the two-keys-of-one-owner regression that the old blanket
  law wrongly refused), the receipt on the remapped flow target with
  every identifying value per-copy remapped (never the raw value),
  the copied one-time secret still target-linked, the raw flow
  identifiers absent, and the source left byte-identical (flow-owned
  rows removed by exact id-set diff). The full owned sanitize module
  passes on the repaired verifier.
* Owned Chromium browser proof (real worker-built copy over the owned
  PG16 source carrying the flow's real receipt): the copied source
  key's receipts page renders the chooser with the copied operation
  (real SQLAlchemy Row transport), selecting it renders the read-only
  projection (copied target key ID, validity mode, fingerprints -
  never the raw source operation UUID, public ID or key ID, and
  never the copy DB name); a second copy built after the flow rows
  left the source renders the honest empty chooser state and carries
  exactly the one canary key (copy isolation - copy B does not see
  copy A's receipt or flow keys).

## Operations index and captured process configuration (objective 224-t)

The demo host admits two more exact GETs, after the same
session/account/copy checks:

* `GET /admin/operations/` - the static Operations index (REQUIRED
  trailing slash), rendered with a narrow demo branch: it describes
  the FROZEN copied data of this session, links only the read pages
  this demo host already admits, and visibly marks the
  not-yet-admitted operations read pages (request diagnostics, Codex
  compatibility, replay maintenance, SMTP test) as
  "unavailable in this demo" (no usability is implied; later
  suffixes restore them);
* `GET /admin/operations/process-configuration` - the captured
  worker-observed process-configuration page (NO trailing slash).

Every near miss, alternate slash shape, subpath and unknown query
stays default-denied (fixed 404); both pages define NO query
parameters at all, and every unsafe method on both paths remains the
unchanged pre-body quiet 204 cut. Diagnostics, compatibility,
replay-maintenance, branding, downloads and actions remain
default-denied for later suffixes.

### Capture source and timing (worker-owned, at copy time)

The 223 worker-owned, per-login verified display-file manifest gains
ONE finite projection leaf, `configuration/process-configuration.json`
(kind `process_configuration`), captured by `capture_all` for EVERY
copy: the existing reviewed `CONFIG_INSPECTION_ALLOWLIST` projection
(`inspect_process_configuration`, "api" scope) of the WORKER
process's cached `Settings` at capture time - each allowlisted
numeric/nullable-numeric value plus its configured/default provenance
(from the worker process's `model_fields_set`). There is no wildcard
`model_dump`, no environment scan, no file read and no credential,
host, path or free text in the projection. A missing, unknown,
oversize or corrupt required projection fails the copy publication
closed through the existing manifest/ingest law (no database schema
change; the closed logical name is added to the existing display
name law). The leaf's capture time is its OWN display-leaf capture
time, separate from (not falsely simultaneous with) the PostgreSQL
snapshot.

### Scope difference from the normal API process

The normal process-configuration page reads the CURRENT API
process's cached `Settings` and the app-global loaded profiles. The
snapshot worker is a DIFFERENT process and may hold different cached
settings, so the demo page never reads `_settings(request)`, live
`request.app.state.upstream_llm_profiles`, the live environment, the
app filesystem, the provider network or the source database. It is
labeled the **worker-observed deployment configuration captured at
copy time**, with its own truthful capture time. The page is frozen
for the session: changing ambient demo-web or deployment settings
after the copy was built does not change the page. The package
version row is explicitly labeled the demo web process's LIVE build
identity (not a worker-captured value); the deployed revision and
revision provenance were NOT captured in this stage and render as
"not recorded in this demo snapshot"; the 223-captured upstream LLM
profile identities and the worker-pinned Codex client reference are
not displayed on this page yet - never fabricated, never read
live.

### Read law (demo process, verified copy only)

The demo GET reads ONLY the verified per-login display projection
from the session's exact bound disposable copy, in one request-local
SELECT-only transaction on the gate-bound engine with the
independent `current_database()` / `transaction_read_only` recheck.
The closed metadata law (exact kind, nonnegative size under the
1 MiB display cap, canonical SHA256, database-computed
`octet_length(body)` equal to the claimed byte count, finite
representable capture time) runs BEFORE any body fetch; the bounded
body fetch re-asserts every condition as bound parameters and the
fetched bytes are re-verified (exact length + SHA256) and re-proven
against the 223 typed verifier law before projection. Any missing
leaf, invalid metadata, bound violation, digest/size mismatch,
verification failure or driver error is one fixed safe 503 with no
input echo (a healthy worker-built copy always carries the leaf).
No credential-shaped value, original operator identity, source path,
copy name or DSN fragment appears in the response, logs or errors;
every demo response stays private no-store.

### Deployment needs and limits

No new operator configuration, role, grant, administration UI or
schema migration: the projection rides the existing worker file stage
and display ingest. The displayed values are deployment-level
operator bounds observed by the worker at copy time - they are not
per-key policy, not the limits of every worker or the reverse proxy,
and "configured" means explicitly supplied to the worker process at
construction time (a configured database URL is not connectivity
proof).

## Neutral branding assets and read-only Codex compatibility views (objective 224-u)

The demo host admits two more exact GET families, after the same
session/account/copy checks:

* the FIVE literal branding slot paths
  `GET /admin/branding/style.css`, `/admin/branding/logo`,
  `/admin/branding/logo-compact`, `/admin/branding/favicon` and
  `GET /admin/branding/hero` - no query, alternate slash, arbitrary
  slot, prefix passthrough or unsafe method;
* the exact read-only Codex compatibility GET family -
  `GET /admin/operations/compatibility/` (REQUIRED trailing slash),
  `GET /admin/operations/compatibility/preset/{shipped-name}`,
  `GET /admin/operations/compatibility/preset/{shipped-name}/download`
  and `GET /admin/operations/compatibility/key/{canonical-lowercase-UUID}`
  - with NO query parameters at all.

Every near miss, alternate slash shape, subpath, unknown slot/preset,
non-canonical key UUID and unknown query stays default-denied (fixed
404); every unsafe method on every admitted path (including the
compatibility review/apply POSTs) remains the unchanged pre-body
quiet 204 cut (no key pin, quota, usage, replay, audit or permission
mutation, no review signed, nothing applied). All other
not-yet-admitted surfaces remain default-denied for later suffixes.

### Neutral branding: capture law (worker-owned, at copy time)

The 223 worker display capture now publishes the COMPLETE finite
five-slot branding leaf set for EVERY new copy, whether the operator
source's branding directory was configured or not:

* a CONFIGURED source directory is replaced by the 223 worker policy
  with the packaged neutral substitutes - the operator's original
  CSS/image bytes never enter the display copy (source paths,
  filenames and tokens never appear);
* an UNCONFIGURED source yields the same packaged neutral bytes
  (empty stylesheet, packaged neutral logo);
* the private custody `source_records` keeps the configured flag and
  per-slot facts for custody only - that flag is NOT part of the
  display copy, so absence of a leaf is never treated as
  "unconfigured".

### Neutral branding: read law (demo process, verified copy only)

* **Pre-login** (no demo session): the fixed packaged neutral
  fallback is served (package default) - NO database read, no
  login redirect; the five slot URLs resolve publicly only to that
  fallback.
* **With a demo session**: one request-local SELECT-only
  transaction on the gate-bound engine, with the independent
  `current_database()` / `transaction_read_only` recheck INSIDE the
  transaction. The metadata query (parameterized exact slot names,
  database-computed `octet_length(body)`) runs FIRST and enforces
  the **complete finite five-slot copy law**: the copy must carry
  EXACTLY the five fixed `branding/<slot>` leaves. ZERO leaves (a
  damaged copy or an older PRE-UPGRADE copy built before this stage)
  or a PARTIAL set (a damaged configured copy) is one fixed safe 503
  refusal - the packaged fallback never masks a corrupted
  configured leaf, and a pre-upgrade copy safely refuses (re-login
  rebuilds a conforming copy). Each leaf must satisfy the closed
  metadata law (kind `branding`, non-boolean integer size within the
  reviewed 256 KiB slot maximum, canonical SHA256, actual bytes
  equal to the claimed byte count) BEFORE any body fetch; the
  bounded body fetch re-asserts name/size/digest/kind as bound
  parameters and the fetched bytes are re-verified (exact length +
  SHA256) and re-proven against the 223 `branding` display policy
  verifier. Any violation or driver error is one fixed safe 503 with
  no input echo. Every response carries `nosniff` and private
  no-store. The live operator branding directory is NEVER read by
  the demo process, and the normal admin rendering and assets are
  byte-identical (the normal app never carries the demo state).
* The demo template branding context references the FIVE exact
  fixed slot URLs (icon, stylesheet, logo, logo-compact, hero), so
  every rendered link resolves privately to the same visitor's
  neutral copy leaves (or the pre-login package fallback).

### Codex compatibility: copy-backed read law (demo process)

The compatibility index and key pages compute ALL qualification
facts from the request-local verified SELECT-only copy (same
`current_database()` / read-only recheck law; a failed recheck is
one fixed safe 503). The demo process's dummy Settings, the
current app-global Codex startup profile, the live public base URL,
the environment and the provider network are NEVER used as
installation facts. Concretely:

* **Index** (`/admin/operations/compatibility/`): the copy-backed
  qualification display with the existing known-incoming-secret-alias
  withholding applied to rendered facts. NO runnable profile
  artifact is offered: the startup-profile section renders a demo
  note stating the demo process adopts no API startup compatibility
  profile and that the 223-captured module identity is not
  published as display data to this page yet (never fabricated,
  never read live). The shipped preset list comes from the
  package's finite preset loader, and each preset link is a demo
  read of that package-owned document.
* **Preset page / download**: the exact canonical credential-free
  bytes of the shipped preset, validated by the existing package
  loader (finite shipped names only), explicitly labeled
  package-owned credential-free reference material - not a
  per-login operator file. The download offers the exact bytes as an
  attachment and remains withheld (403) whenever the existing
  secret-alias check fires.
* **Key page** (`/key/{canonical-lowercase-UUID}`): the same
  copy-bound key dashboard scope and pin/options projection the
  normal page uses, rendered over the verified copy only, with the
  persistent demo note that the key binding shown is a FROZEN read
  of this session's verified copy and the form has NO effect
  (submitting changes nothing, signs no review, applies nothing,
  and grants no compatibility or replay authority).

The Operations index's compatibility marker is a real link to the
admitted index once these GETs work (previously "unavailable in
this demo"). No raw key, provider credential, operator source
path/host or signed review payload appears in any demo response;
links remain safe links to copy-backed pages only. (224-v
correction: the compatibility review form does carry a visible
POST action, but the central demo gate makes it a pre-body quiet
204 no-op with no effective write authority.)

### Evidence (224-u)

* **Focused mocked units**: 18 new `test_u_` unit tests in
  `tests/unit/test_demo_web.py` (gate exact-path/near-miss/unsafe-204
  law for both families; branding positive five-leaf law with
  bound-parameter assertions, zero/partial-set refusal, corrupt
  metadata, body mismatch/policy refusal, copy-mismatch and
  pre-login no-DB fallback; compatibility index/preset/key/download
  positives with alias withholding and exact credential-free bytes,
  near misses, recheck refusals) - plus the directly affected
  pre-existing unit sweep (demo web, snapshot files, worker,
  design/usability inventory, documentation contract) green.
* **Owned PostgreSQL, two simultaneous copies**: the owned two-copy
  fixture (disposable source + two disposable target copies, each
  worker capturing a DISTINCT configured source branding with canary
  tokens) proves both sessions serve the SAME packaged neutral bytes
  for every slot (source tokens never appear), the complete
  five-slot leaf set per copy (metadata self-consistent,
  database-computed actual bytes), cross-copy isolation and
  corruption refusal (corrupting copy A's leaf makes A a fixed safe
  503 while B stays 200; deleting one of A's five leaves is the
  same refusal; exact restore verified), and the compatibility
  family per copy (copy-backed facts, exact preset download bytes,
  key page for the copy's own remapped key, near misses, pre-body
  204 cuts). The 223 sanitize owned-PG suite also re-ran green
  (unconfigured captures now carry the five neutral leaves).
* **Real Chromium**: the owned browser fixture (one copy, real
  worker) proves the rendered slot href/src values, explicit
  per-slot requests with exact neutral bytes and safety headers,
  near-miss 404s, the operations-index compatibility link, the
  compatibility index/preset/key demo renders and the quiet 204
  review POST boundary in the real browser context.
* Normal admin rendering and assets are byte-identical (the normal
  app never carries the demo state; the demo branches are
  state-gated), and no schema migration, role, grant,
  configuration, release, deployment or merge is introduced.
* Synthetic fixtures are not a real company installation; objective
  225's configured-file installed acceptance remains later.

## Request diagnostics and replay maintenance reads (objective 224-v)

The demo host admits two more exact GET families, after the same
session/account/copy checks:

* `GET /admin/operations/diagnostics` (exact path; an optional
  bounded read-only selector `lookup=<safe diagnostic ID>` and/or
  `namespace=<any|gateway|client>`);
* `GET /admin/operations/replay-maintenance/` (index, REQUIRED
  trailing slash);
* `GET /admin/operations/replay-maintenance/all-active` (the
  explicit every-active-key scope);
* `GET /admin/operations/replay-maintenance/key/{uuid}`;
* `GET /admin/operations/replay-maintenance/cohort/{uuid}`.

The central demo gate admits ONLY these exact shapes (canonical
lowercase dashed UUIDs, query-free replay family; the diagnostics
page carries its bounded selector law) and keeps EVERY unsafe
method - including the normal diagnostics lookup/cleanup POSTs and
the replay inspect/preview/apply POSTs - the pre-body quiet 204
cut. The operations index links both pages.

### Diagnostics: selector law (gate, before the copy)

The page defines ZERO parameters or at most ONE of each of the two
exact read-only selectors. The law runs on the RAW query bytes
before session resolution, routing or any echo:

1. the whole raw query must fit the small byte ceiling (420 bytes,
   the worst-case percent-encoding of a 128-character safe ID plus
   the namespace pair) BEFORE it is split;
2. parameter names must be the exact ASCII literals `lookup` /
   `namespace` (names are never percent-decoded); unknown,
   duplicated or empty parameters refuse;
3. each value is percent-decoded EXACTLY ONCE (a strict single
   pass: invalid escapes stay literal and then fail the grammar, a
   decoded value is never decoded again);
4. `lookup` must match the existing safe diagnostic ID grammar, and
   a decoded lookup that is or embeds a KNOWN incoming
   authentication alias is refused HERE, before the session is
   resolved and the copy is bound - a credential-shaped value can
   fit the safe-ID grammar. The classifier runs against the raw
   scope with the DEMO APP'S fixed neutral accepted-prefix tuple
   (never ambient global settings); an unavailable prefix set is
   an explicit sentinel (a derivation failure is never conflated
   with a legitimately empty configured set) that denies every
   nonempty selector, and any classifier error refuses;
5. `namespace` must be `any`, `gateway` or `client`.

The boundary this code proves: a refused value does not reach the
copy session, application-rendered HTML, an
application-produced redirect, or any application echo or log
under this process's control. An upstream proxy or access log
that records the raw request line before the ASGI gate is outside
this code's reach and is not claimed.

### Diagnostics: read law (demo process, verified copy only)

One request-local SELECT-only transaction on the gate-bound engine
with the independent `current_database()` / `transaction_read_only`
recheck. The page reads ONLY content-free diagnostic rows from the
copy: a bounded newest-first recent list (100 rows) plus, when the
selector is present, the exact safe-ID lookup reusing the normal
service's bounded candidate law with NO retention cutoff - the
source deployment's retention/recording settings were not captured
in the demo projection and are never displayed (labeled "not
recorded in this demo snapshot"). The adapter re-proves the
selector before use (a value that cannot be re-proven renders the
cleared not-found, never the value). Output-side alias withholding
applies to the found/recent projections and to ambiguous
candidates (a withheld candidate keeps its row - the count stays
honest - but shows no ID and no resolve link). Corrupt or absent
copy data is the fixed safe 503, never an ambient fallback. No raw
capture artifact, prompt, credential or source-DB access occurs;
every response is private no-store.

### Replay maintenance: read law (demo process, verified copy only)

The four GETs share one request-local SELECT-only transaction with
the same recheck. The summary reuses ONLY the pure-read,
copy-bound repository aggregate statements (selected-key states,
reference aggregates, per-key aggregates, route/model groups) plus
two small bounded SELECTs (kind counts; up to 100 newest SAFE
metadata rows - no HMAC digests, no opaque tokens, no
source_request_id, no usage-ledger IDs). The explicit
every-active scope refuses the 1,000-key bound without truncating
(a larger copied scope says exactly that and reads nothing more).
The key/cohort scope must exist in the visitor's copy (fixed 404),
and a scope ID equal to an incoming credential of THIS request is
the fixed 400 refusal (the value never renders).

The worker-captured `CODEX_REPLAY_REFERENCE_TTL_SECONDS` comes
from the verified process-configuration display leaf (the 224-t
capture law, 1 MiB bound, metadata-first, typed verifier); an
absent or corrupt leaf is labeled "unavailable (not recorded in
this demo snapshot)" - never the demo process's own settings and
never a live deployment value. The demo process NEVER reads HMAC
keys: no HMAC eligibility is shown, no preview/apply authority and
no signed plan is implied, and the active/expired split is a plain
comparison of the copied expiry timestamps against view time.

### Visible no-op action controls (demo)

Per the agreed behavior the fake admin sees EVERYTHING the real
admin sees: the normal diagnostics cleanup form and the replay
inspect/preview forms stay visible in demo with honest persistent
no-op notes, and their submission is the gate's quiet pre-body
204 - nothing is written, no plan is produced, no deletion,
extension or audit record occurs, and no false success is
rendered. Demo-only wording replaces the effect-promising help
lines (deletion / plan / extension / audit) so no demo text
promises a write; the normal-branch markup and text are
unchanged. The demo adds the read-only GET lookup form
(diagnostics) and the copy-backed summary sections (replay scope
pages).

### Evidence (224-v)

* **Focused mocked units**: 12 new `test_v_` unit tests in
  `tests/unit/test_demo_web.py` (gate exact-path/near-miss/
  query-law/unsafe-204 law for both families, including the
  percent-encoded colon selector, the invalid-escape refusal, the
  420-byte raw ceiling and the pre-copy alias refusal proven with
  a never-called sessionmaker; diagnostics positive FOUND render,
  alias-candidate withholding, copy-mismatch 503 with no count
  SQL; replay index worker-TTL render, key-scope copy-backed
  summary with bound-parameter LIMIT proof, oversize refusal,
  missing-key 404, alias-scope 400, TTL-unavailable labeling) -
  plus the directly affected pre-existing unit sweep (demo web,
  design/usability wrapper inventory 53→57, documentation
  contract) green and Ruff clean.
* **Byte-identity oracle**: the four modified templates
  (operations index, diagnostics, replay index, replay scope)
  render byte-identical under representative NORMAL contexts
  against the activation-commit originals (10/10 contexts), so
  the normal admin output is unchanged.
* **Owned PostgreSQL, two simultaneous copies**: the owned
  two-copy fixture (disposable source + two disposable target
  copies) proves, with TEST-ONLY target-side rows inserted into
  copy A only through the owned target-owner connection (honest
  label: transport proof, NOT source capture; exact-ID cleanup
  before the invariance phase), the copy-backed diagnostics
  recent list + FOUND lookup per copy, cross-copy lookup
  isolation, the key-scope copy-backed summary with the
  worker-captured TTL and the cross-copy reference isolation,
  the gate's pre-copy alias 404 over a real copy, and the
  near-miss/query/unsafe-method boundaries.
* **Real Chromium**: the owned browser fixture proves the
  operations-index links, the diagnostics page render (banner,
  bounded recent table, visible no-op cleanup note) and the
  replay index/all-active renders (banner, scope links, HMAC-not-
  shown note) in the real browser context.
* No schema migration, role, grant, configuration, release,
  deployment or merge is introduced; the fake admin remains a
  sanitized display surface with no write authority.
## Read-only SMTP test, key calibration JSON attachment, and route configuration reads (objective 224-w)

The demo surface gains four further exact read-only families, all
over the visitor's verified per-login SELECT-only copy. As before,
every operational submission stays the gate's quiet pre-body 204
no-op (except the CSRF-verified demo logout), no source
database/file/settings/provider/mail access is reachable, and every
new read re-checks `current_database()` and
`transaction_read_only` inside its one request-local transaction.

### 224-v repairs folded into 224-w

* The demo diagnostics page now shows ONLY the working read-only
  GET lookup (the normal POST lookup was a silent no-op, so it is
  not offered); the normal lookup branch stays byte-identical, and
  the cleanup action control stays visible as a labeled no-op.
* The demo not-found wording no longer suggests the copied row fell
  outside a live retention window ("No copied record matches this
  exact ID in this frozen snapshot."), and the replay preview help
  no longer implies ongoing traffic can change the frozen copy.
* The duplicate source-level guidance IDs
  (`cleanup-confirm-help`, `cleanup-reason-help`,
  `preview-expired-help`, `preview-reason-help`) are unique in the
  template source and correctly linked in both rendered branches;
  the new lookup input and namespace select carry their own linked
  help.
* **Correction of the 224-v claim**: the 224-v report stated that
  output-side alias withholding applied to the found/recent
  projections. That was overstated: the found detail's raw
  `gateway_key_id` / `route_id` UUID strings were NOT withheld at
  224-v time. 224-w withholds them in the demo branch whenever the
  UUID string matches a known incoming bearer/cookie/session/proxy
  alias, exactly like the other displayed fields (no echo, no
  link). Normal-admin output is unchanged.

### Admission law (central gate, before the copy)

Admitted (GET only): `/admin/email-operations/smtp-test`,
`/admin/email-operations/smtp-test/apply` (both query-free);
`/admin/keys/{canonical-lowercase-UUID}/calibration/summary.json`
(the one bounded positive query law below);
`/admin/keys/{canonical-lowercase-UUID}/configuration.json`
(query-free); `/admin/routes/{canonical-lowercase-UUID}/configuration`
(query-free); and
`/admin/routes/{canonical-lowercase-UUID}/codex-profile/{base|profile|catalog}`
(ONE finite artifact vocabulary, query-free). No alternate slash,
subpath, broad prefix or arbitrary query is admitted; every unsafe
method on the admitted paths is the pre-body quiet 204.

The calibration summary carries a bounded POSITIVE query law
enforced before any copy binding: a small whole-raw-byte ceiling
first, then a strict single-pass percent-decode (the normal
template link urlencodes the datetimes; an invalid or truncated
escape is refused, `+` is not a space), then at most one of each of
the exact parameters `start_at` / `end_at` / `multiplier` - no
unknown names, no duplicates, no oversized values, and strict value
grammars (ISO-8601 date/datetime; positive decimal) that no
credential-shaped value can fit. The handler re-runs the normal
strict parsers, so a grammar-level value that is semantically
invalid (for example month 13) is a fixed safe 400 before any copy
read.

### SMTP test reads (no captured facts)

The 223 capture records NO source email/SMTP facts (there is no
SMTP display leaf and no copied SMTP settings table), so both GETs
render the fixed "not recorded" state: the demo process's own dummy
SMTP settings are NEVER used as source readiness, and no SMTP host,
user or password is displayed or used. The existing styled form and
recovery views are shown with their useful recipient/subject/body
product-constant hints and visible review/send controls clearly
labeled quiet no-ops; the apply-recovery page is a fixed no-send
notice. There is no live one-use token, no test send, no
broker/mail access, and no false success.

### Key JSON attachments (calibration only; configuration safely unavailable)

* `calibration/summary.json`: produced by the SAME proven read-only
  normal rendering service and the SAME strict input validation as
  the normal download, bound to the request-local copy session and
  recalculated over the FROZEN copied usage rows (copied-data
  recalculation, never live current usage). The key must exist in
  THIS copy (fixed 404 otherwise); non-trusted-calibration keys
  get the fixed safe 400 refusal.
* `configuration.json`: SAFELY UNAVAILABLE - a fixed safe 503 with
  NO JSON body and NO copy read. The 222/224-r sanitizer projects
  `gateway_keys.metadata` by the clone-receipt-only KR law,
  discarding the ordinary policy members
  (`allowed_providers`, `responses_policy`, `rate_limit_policy`,
  `lazy_throttling_policy`, `live_burn`, `external_tool_policy`)
  that the normal `render_key_configuration_document` export
  reads, and the demo process only carries fixed neutral settings,
  so its operator ceilings are never the source deployment's.
  Rendering the version-1 document from the stripped copy plus
  neutral settings would FABRICATE default policy for real keys;
  until a separately verified policy projection exists (bounded
  follow-on sanitizer work, a human choice pending), this exact GET
  emits no configuration export at all - no source fallback, no
  raw metadata passthrough, no default guessing. The key-detail
  page keeps the action visible and labels it unavailable in this
  demo.

All refusals (404/400/503) are fixed HTML pages. A SUCCESSFUL
calibration download is application/json with the attachment
disposition, and the gate then normalizes every dynamic /admin
response's cache policy to exactly one
`Cache-Control: private, no-store` (a pre-existing header is
replaced, never duplicated) plus nosniff.

Whole-output refusal (calibration only): when ANY nested string of
the serialized artifact equals or embeds a known incoming
authentication alias (the same pure request-aware classifier as
the normal calibration export), the WHOLE output is refused with a
fixed safe error - no partial secret substitution, no echo of the
refused value. The path key id itself as an incoming alias is
refused BEFORE any copy binding on BOTH attachments (fixed safe
400, before configuration would otherwise reach the fixed safe
503). A finite 1 MiB output ceiling refuses oversize calibration
output explicitly (never truncated).

### Route configuration form (copy-backed choices only)

The route and the four database-backed choice families (provider,
requested model, upstream model, endpoint) are loaded from the
visitor's verified SELECT-only copy with the same bounded read-only
choice law as the normal form. The optional operator completion
choices come ONLY from the 223-verified sanitized
`profiles/completion-choices.json` display leaf - metadata first
(kind/size/digest/actual length), the bounded body re-asserting
every condition as bound parameters, exact length + SHA256, and the
typed verifier law. There is NO live
`COMPLETION_SERVICE_PROFILE_DIR` or filesystem fallback in the demo
process: an absent leaf means the source deployment recorded no
operator completion profiles, and the picker then shows the finite
packaged completion-profile defaults (the bundled profile data the
normal form offers when the operator directory is absent), clearly
labeled as package defaults - not copied source state; a corrupt
configured leaf is the fixed safe 503.
The existing form, field hints and visible action controls are
kept with a persistent frozen/no-op cue. No provider network or
source file read occurs.

### Inert Codex reference artifacts (no runnable profile)

The demo host cannot forward `/v1`, so the normal live
`PUBLIC_BASE_URL` is never used to emit a runnable profile. For a
copied route that is eligible under the same pure copy-bound
qualification inspection the normal route detail uses, the three
finite attachments (`base`, `profile`, and `catalog` only where the
profile includes one) are rendered by the same pure renderer over
the finite packaged profile data with the reserved non-routable
placeholder URL `https://api.slaif.invalid/v1`, under clearly
labeled `.reference` inert filenames. They contain no bearer, no
real source host, no provider credential and point to no usable
endpoint. An ineligible route, an unknown/unsupported profile id,
or an unavailable catalog is a safe 404; every response is private
no-store and nosniff. The demo route-detail page links the inert
artifacts truthfully for eligible routes and stays
byte-identical for the normal admin.

### Evidence (224-w)

* **Focused mocked units**: the new `test_w_` unit suite in
  `tests/unit/test_demo_web.py` (gate exact-path/near-miss/
  query-law/percent-decode/unsafe-204 law; SMTP not-recorded
  render, preflight-mismatch 503 and no-demo-state 404;
  configuration 503-no-JSON/no-copy-read, configuration
  shape-refusal 404s and the fixed 503 no-alias-echo case;
  calibration positive/missing/alias/oversized/preflight cases
  including the path-identity refusal proven with a never-called
  copy session; route-configuration copy-backed positive,
  unconfigured-leaf labeling and corrupt-leaf 503; codex artifact
  eligible-inert bytes, no-catalog 404, ineligible 404 and
  render-failure 404), plus the repaired 224-v unit failures
  (usability sortable-table inventory 58 -> 62, the linked demo
  lookup help, the unique guidance IDs, and the diagnostics
  found-UUID alias withholding canary) - all green with Ruff
  clean.
* **Byte-identity oracle**: the modified templates (smtp test
  form/review, route configuration form, route detail, key detail,
  diagnostics, replay scope) render byte-identical under
  representative NORMAL contexts against the activation-commit
  originals; the demo branches render the expected content in a
  separate demo smoke render.
* **Owned PostgreSQL, two simultaneous copies**: the owned
  two-copy fixture proves, with ONE test-only trusted-calibration
  key row inserted into copy A only through the owned target-owner
  connection (honest label: transport proof, NOT 222 source
  capture or worker publication; exact-id cleanup before the
  invariance phase), the SMTP "not recorded" pages for both
  sessions, the calibration summary over frozen copied usage for
  the test-only trusted-calibration key, the fixed safe 503 with
  NO JSON for configuration (both copies' copied key metadata
  proven clone-receipt-only, with the source-policy-divergence
  seed proving the copied metadata omitted the nondefault source
  policy), the purpose-gate 400, the semantic-input 400, the gate
  query-law 404s, the path-identity and whole-output alias
  refusals with no echo, the configuration 503 for BOTH sessions
  (copy A's inserted key and copy B's own key - no configuration
  JSON exists in either copy), the route-configuration copy-backed
  form over the REAL worker-built completion-choices leaf (the
  copied route's DB value linked to its copy's leaf, per-copy leaf
  reads, and the corrupt-leaf 503 with exact digest restore), and
  the codex artifact 404 boundary for the fixture's non-eligible
  route (the eligible inert bytes are proven by the unit suite).
* **Real Chromium**: the owned browser fixture proves the SMTP
  form render and the REAL submit landing on the quiet 204 no-op
  (nothing sent), the apply-recovery no-send notice, the key
  detail page labeling the frozen-configuration action unavailable
  in this demo with NO configuration.json link, the standard-key
  calibration 400 in the browser, the route-detail page without
  any codex artifact
  link, the exact artifact-path 404, and the route-configuration
  render with the persistent no-op cue.
* No schema migration, role, grant, configuration, release,
  deployment or merge is introduced; the fake admin remains a
  sanitized display surface with no write authority.

## Catalog final reads: direct artifact downloads and frozen apply-status (objective 224-x)

The demo catalog surface gains its remaining four read-only exact
GET families, all over the visitor's verified per-login SELECT-only
copy and all query-free:

* `/admin/operations/catalog/runs/{run-id}/artifact/{file}` (the
  run-id is exactly `demo-run-` plus 24 lowercase hex) - one of
  the closed seven worker-published run content files
  (`catalog-refresh.json`, `catalog-baseline.json`,
  `routes-proposal.tsv`, `pricing-proposal.tsv`,
  `fx-proposal.json`, `validation.json`, `REVIEW.html`), each
  intersected with the already-published sanitized leaf law for
  that exact file's worker-published kind.
* `/admin/operations/catalog/runs/{run-id}/apply-status` (same
  exact run-id shape) - the frozen historical apply status for one
  captured run.
* `/admin/operations/catalog/jobs/{32hex}/artifact/{file}` - one of
  the closed job upload names (`bundle-` / `baseline-` /
  `baseline-export-` plus 32 hex) and the six sanitized proposal
  artifact names (`source-manifest.json`,
  `provider-catalog-normalized.json`, `routes-proposal.tsv`,
  `pricing-proposal.tsv`, `provider-catalog-report.md`,
  `warnings.json`).
* `/admin/operations/catalog/jobs/{32hex}/package/{preset}/{file}`
  - the finite five presets crossed with the five closed package
  file names (`routes-proposal.tsv`, `pricing-proposal.tsv`,
  `package-report.md`, `model-review.md`,
  `package-manifest.json`).

The run detail page links the seven run files to these DIRECT
downloads (never the `?name=` selector); the catalog index keeps
the 224-l `?name=` selector. No query, subpath, alternate-slash or
non-canonical-ID variant is admitted (fixed 404); every unsafe
method on the admitted paths is the pre-body quiet 204.

### Metadata-first bounded reads

Each download runs in ONE SELECT-only/read-only transaction on the
gate's SAME request-local copy engine with the independent in-
transaction `current_database()` / `transaction_read_only` recheck
(mismatch is the fixed safe 503). The FIRST query is metadata-only:
a parameterized lookup of the exact validated logical name with a
DB-computed `octet_length(body)` - no body transfer. It requires
`byte_count` and the actual length to be nonnegative integers no
greater than 32 MiB and equal, plus the exact closed kind. The
SECOND query fetches the body only under `kind` / `byte_count` /
`sha256` and `octet_length(body) <= :cap` re-asserted as BOUND
parameters, and the fetched bytes are re-checked in memory for
length and SHA256 before release. A missing leaf is the fixed 404;
any corruption, bound violation, digest/size mismatch or driver
failure is the fixed safe 503 - never the bytes, never a partial
artifact, never a source value. No filesystem, network, original-
custody or seal-key access occurs.

### Wire law

A SUCCESSFUL download carries `application/octet-stream`, a forced
`Content-Disposition: attachment` with the safe closed base name,
`X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'`, and exactly one
`Cache-Control: private, no-store` (the gate normalizes every
dynamic /admin response to that single header). 404/503 are
fixed HTML refusals carrying `X-Content-Type-Options: nosniff`
plus that same gate-normalized single
`Cache-Control: private, no-store` header (no name, kind, hash,
DSN or error value echoed). Copy isolation holds: a session sees
only its own copy's leaves, so a name that exists only in another
copy is a fixed 404.

### Frozen apply-status page (fixed explicit unavailability)

The apply-status page first verifies, in ONE
SELECT-only/read-only transaction with the in-transaction
`current_database()` / `transaction_read_only` recheck, that the
run exists in THIS copy via the SAME closed seven-file
metadata-only inventory (missing run is a fixed 404; a partial or
kind-mismatched run is the fixed safe 503). It then renders the
FIXED explicit "Apply status is unavailable for this run in this
copy." state with ZERO records.

Reported limitation: the worker remaps captured run identifiers
for the display leaves (the `demo-run-` keyed-HMAC slug) while the
sanitizer remaps the copied `catalog_refresh_applications.run_id`
values by an INDEPENDENT per-copy string remap; the web process
holds neither the original run id nor the per-copy seed, so NO
verified mapping exists between a copied application record and
the display run id. Presenting copied rows as this run's status
would mislead, so the copied applications table is NOT read or
listed on this page at all. The unavailable state is a historical
display limitation of the sanitized copy - it is NOT a statement
that the run was never applied. The page keeps the "status at
snapshot time" / "NOT live authoritative source status" framing,
and visible operational controls are labeled quiet no-ops.

### Key configuration export remains safely unavailable

The 224-w `configuration.json` fixed safe 503 stands. The owned
fixture now additionally seeds a NONDEFAULT source policy into the
first source key's `gateway_keys.metadata` (restored by a
test-local finalizer) and proves BOTH copies' metadata for that
key is clone-receipt-only - a direct source-policy-divergence
proof that a faithful version-1 configuration export cannot be
reconstructed from the sanitized copy. A bounded sanitizer policy
projection remains pending human choice.

### Evidence (224-x)

* **Focused mocked units**: the 17 new `test_x_` unit tests in
  `tests/unit/test_demo_web.py` (calibration default multiplier 3
  and the rebuilt raw-byte gate query law - literal ASCII
  parameter names, one percent-decode per bounded value,
  encoded-name/delimiter/equals refusals, and date-shaped /
  numeric incoming-alias refusals; route-picker packaged defaults
  and alias withholding; catalog gate exact shapes with the
  32-hex "original" id admitted (same canonical shape) and the
  true near-misses 404; unsafe-method 204s; run-artifact positive
  with exact bytes + wire law + the metadata-first DB-computed
  `octet_length` + bound-parameter body re-assert; missing 404;
  seven corruption cases refused BEFORE any body query; body
  digest-mismatch 503, each refusal asserting the exact refusal
  wire law (nosniff plus the gate-normalized single
  `Cache-Control: private, no-store`); job artifact positives for
  ALL THREE closed upload kinds (the longest-prefix
  `baseline-export-`) plus proposal, and package positives;
  apply-status missing-run 404 and partial-run 503, the
  run-present fixed-unavailable page, and the rows-never-rendered
  no-misattribution negative (101+ copied rows, including a
  tampered row and an incoming-alias canary, are never read or
  echoed)) - all green with Ruff clean; plus the repaired 224-w
  admin key-actions template suite (21/21; the hosted w-head
  failure `test_q_detail_demo_shows_admitted_read_links`
  reproduced locally and repaired).
* **Byte-identity oracle**: the 224-x-modified templates
  (apply_result, proposals, smtp_test, configuration_form,
  keys/detail link block, run detail, catalog jobs) render
  byte-identical under representative NORMAL contexts against the
  activation-commit originals; the demo branches render expected
  content in separate demo smoke renders.
* **Owned PostgreSQL, two simultaneous copies**: one test-only
  complete run (seven leaves - six honest `b"{}"` placeholders
  plus one REAL 223 `_san_validation_json` body), one test-only
  job (upload, proposal warnings, package manifest) and one
  test-only `catalog_refresh_applications` row are inserted
  through the owned target-owner connection AFTER the
  earlier empty-state assertions (honest label: transport/binding
  proof, NOT 222 source capture or worker publication; exact-name
  / exact-id cleanup in a finally). Proven: run-artifact /
  job-artifact / package exact bytes + wire law over the session
  clients; copy-B isolation 404; stored-SHA corruption 503 with
  digest restore; the seven near-miss 404s; the apply-status
  fixed-unavailable page with zero records BEFORE and AFTER
  inserting the ONE test-only application row (the row's values
  are never rendered - no misattribution without a verified
  run-id mapping), copy-B 404 for the same canonical run, the
  quiet 204 cuts with a 200,000-byte garbage body, and the
  partial-run 503; plus the source-policy-divergence proof
  (both copies' `gateway_keys` metadata clone-receipt-only
  despite the nondefault source policy).
* **Real Chromium**: the browser copy carries the same seven
  test-only run leaves (six honest `b"{}"` placeholders plus one
  real `_san_validation_json` body): the NON-EMPTY catalog index
  with the seven `?name=` sanitized-selector hrefs (the 224-l
  selector, unchanged) and no empty-state note, the run detail
  page with the seven DIRECT
  `/runs/{run-id}/artifact/{file}` hrefs plus the apply-status
  link, a REAL authenticated-context artifact
  download (exact bytes + forced attachment wire law), the
  collect page listing exactly that one Captured run group, the
  apply-status fixed-unavailable page with zero records DESPITE
  the real copied applications row from the source fixture (the
  no-misattribution negative in a real browser) plus the labeled
  no-op control, and the key detail page labeling the
  configuration action unavailable with no configuration.json
  link.
* The six placeholder bodies (owned-PG and browser fixtures) are
  TEST-ONLY and are not valid typed outputs for their kinds; they
  prove route/reader/transport and the bounded-read law, not
  artifact content validation or worker publication. The
  configured-file installed workflow remains objective 225.
* Hosted checks are recorded as observed at report time, not
  presumed. No schema migration, role, grant, configuration,
  release, deployment or merge is introduced; the fake admin
  remains a sanitized display surface with no write authority.
