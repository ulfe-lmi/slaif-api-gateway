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
  OUTSIDE the repository and databases; every artifact (manifest, dump,
  stderr tails) is `0600`. Symlinked or group/world-accessible custody
  roots are refused. The custody manifest is the durable private record
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

- Inspect: the private custody manifest (0600, outside the repository)
  plus the private pre-state file record the exact state, failure code
  and pre-rewrite budget/checksum evidence.
- Retry: re-run `slaif-gateway demo-snapshot-worker sanitize` (fenced,
  idempotent).
- Cleanup: `expire` and `recover` behave as in objective 221 and drop
  the EXACT recorded copies (never a prefix sweep). Rollback is that
  exact-copy cleanup followed by removing the custody directory
  contents. No business database is ever touched, and no raw value
  appears in CLI output, logs, reports or committed artifacts.

### 223 / 224 prerequisites

Objective 223 (file-backed panel capture/verification) and objective
224 (browser binding/login) are inert until their own activation and
MUST complete before any demonstration use; this stage never grants the
demo web role and never exposes a public URL.
