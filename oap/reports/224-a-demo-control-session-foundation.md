# OAP Report — 224-a: demo control session foundation

PR mode: CREATE_NEW_PR — branch `oap/224-demo-web` from verified remote
main `d3762e51c9a323dee6b728c4a45fa21b0bffae86` (objective-223 merge;
223 is TERMINAL). PR title: `224: Demo administrator login and isolated
snapshot UI` (created after this report; root owns CI/review/merge).

## 1. Work order

- Order file: `oap/orders/224-a-demo-control-session-foundation.md`
- Order SHA256: `1829d7375dc20e07e43620efb68bcca99c371a8eb67f4eb31a4cff026e86b8da`
- `oap/active` = exactly `224-a` (5 bytes, no trailing newline).
- Root-authored activation bytes committed first as
  `d79060975e3877cbbb1b571e30e89f1388edcff6` (order + active, unchanged).

## 2. Topology and diff scope

- Implementation head: `6cf41974b9ba264afee0e79f44f2b3b81a7c0b9e`,
  sole parent the activation commit.
- Diff `d7906097..6cf41974`: 21 files, `+4111/-22`:
  - New: `migrations/versions/0028_demo_web_control.py` (+265),
    `app/slaif_gateway/db/repositories/demo_web_control.py` (+322),
    `app/slaif_gateway/services/demo_web_control.py` (+1077),
    `tests/unit/test_demo_web_control.py` (+898),
    `tests/integration/test_demo_web_control_postgres.py` (+998).
  - Modified: `app/slaif_gateway/db/models.py` (+185: the two ORM
    models + eager_defaults), `app/slaif_gateway/db/repositories/
    fake_admin_accounts.py` (+54: read-only facts helper),
    `docs/database-schema.md` (+160), `docs/demo-admin.md` (+121),
    and 12 migration-head test literals (8 unit + 4 integration,
    current-head `0027_demo_admin_accounts` -> `0028_demo_web_control`
    only; historical migration assertions untouched).
- This report is a report-only SELF commit: sole parent
  `6cf41974b9ba264afee0e79f44f2b3b81a7c0b9e`, sole diff file this
  report. No other path was touched; `oap/reports/` is otherwise
  unchanged.
- Scope disclosures (both review-driven, within the order's intent):
  1. The order names `app/slaif_gateway/services/fake_admin_accounts.py`
     for "a small read-only account/generation helper if demonstrably
     necessary". The helper (`FakeAdminAccountFacts` +
     `get_account_facts`) was added instead to the EXISTING
     `app/slaif_gateway/db/repositories/fake_admin_accounts.py`, which
     already owns `FakeAdminAccountsRepository`. It is strictly
     read-only (column-scoped SELECT of id/is_enabled/
     credential_generation; no mutation code, no new write path); root's
     224-a review explicitly directed this facts-only column-scoped
     SELECT plus a worker-safe projection query. No account mutation
     change anywhere.
  2. Root (in-conversation strategic extension) independently verified
     and authorized six additional head-pinning unit files beyond the
     order's list — `test_alembic_email_jobs.py`,
     `test_alembic_quota_reservation_accounting_facts.py`,
     `test_alembic_external_tool_fence.py`,
     `test_alembic_key_prefix_default.py`, `test_alembic_accounting.py`,
     `test_alembic_provider_pricing.py` — with the same allowance:
     current-head literal/comment updated to 0028 only, historical
     assertions preserved.
- No change to `main.py`, ordinary admin/API handlers, the snapshot
  worker, CLI, provider adapters, forwarding, quota/accounting,
  Compose/image/Nginx, or public web code.

## 3. What was implemented

### 3.1 Migration 0028 (demo_control only)

Single successor head after `0027_demo_admin_accounts`; creates NO
roles and grants NOTHING; creates exactly two tables in the EXISTING
`demo_control` schema (verified: no ACL on either table; a fresh probe
role holds no privileges; neither table exists in `public`, so 221's
`pg_dump --schema=public` exclusion is structurally unchanged — the
order's "reuse accepted 221 evidence" clause applies since schema
separation is unchanged, and no production dump was run):

- `demo_control.demo_snapshot_requests`: fresh UUID bound to the
  fake-admin account UUID (FK RESTRICT) and its LIVE
  `credential_generation`; `state text NOT NULL DEFAULT 'pending'`
  (DB default: the web role's column-limited INSERT cannot name the
  column); closed failure-code vocabulary
  (`claim_expired`, `late_completion`, `worker_failed`,
  `verification_failed`, `copy_mismatch`, `state_conflict`,
  `internal_error`); closed-grammar copy identities
  `worker_job_id ~ '^snap-[0-9a-f]{32}$'` (exactly the 221
  SnapshotManifest.job_id) and `worker_target_db ~ '^demo_snap_[0-9a-f]{20}$'`
  (the 221 randomized target database NAME — never a path/DSN), each
  unique across ALL requests (partial unique indexes), so two requests
  can never bind one copy; bounded `created_at < deadline_at <
  expires_at` CHECKs. No password, bearer, provider secret, raw dump
  path/body, or arbitrary error text is storable.
- `demo_control.demo_web_sessions`: `token_hash ~ '^[0-9a-f]{64}$'`
  (SHA-256 hex of the opaque random browser token; the raw token is
  returned exactly once and never persisted/logged/echoed);
  account/generation fence; exactly one verified request binding
  (FK RESTRICT); `expires_at >= created_at`; `uq_demo_web_sessions_
  one_active_per_request UNIQUE (request_id) WHERE revoked_at IS NULL`
  — a reused copy can never carry two concurrent sessions.
- Downgrade drops exactly the two tables; the schema and 0027 tables
  survive (0027's downgrade remains the one that drops the schema).

### 3.2 State machine (`slaif_gateway.services.demo_web_control`)

One-transaction, PostgreSQL-authoritative, finite state machine
(`DemoWebControlService`, repositories injected for unit fakes):

- Web role: `create_request` (enabled account + database-side
  nonzero-active gate; column-limited INSERT — `state` comes from the
  DB default; distinct UUID/deadline/expiry per login),
  `create_session` (verified + unexpired + owned + generation +
  nonzero-active + one-live-session gates; raw token returned once),
  `validate_session` (ALL gates rechecked on EVERY use),
  `revoke_session` (idempotent atomic guarded UPDATE of `revoked_at`
  only; never mutates the request).
- Worker role: `claim_request` (exactly-once guarded transition;
  expired lease -> failed/claim_expired; stale account ->
  failed/state_conflict), `record_verified_handoff` (closed grammars;
  claimed-only; LIVE account fence rechecked; copy lifetime; EXACT
  223 verified manifest state; copy-uniqueness IntegrityError -> safe
  `web_request_copy_reused`; late -> failed/late_completion),
  `record_worker_failure` (finite worker codes only),
  `mark_cleanup_pending` (refuses a verified copy with a live session
  unless expired; must proceed after account disable),
  `mark_cleaned`, `reap_expired` (bounded).
- Projections' `to_safe_dict()` omit worker_job_id/worker_target_db and
  all token material. Crashes leave inspectable finite states; nothing
  is ever silently published.

### 3.3 Locking law (verified against the PostgreSQL 16 privilege docs
and a live PG16 probe)

Every row-locking read (FOR UPDATE/FOR NO KEY UPDATE/FOR SHARE/FOR KEY
SHARE) requires UPDATE privilege on at least one column of the locked
table. Probes on a scratch PG16: a column-SELECT-only role gets
`permission denied for table` (SQLSTATE 42501) on `FOR SHARE`; a role
with UPDATE on one column succeeds `FOR SHARE`; plain SELECT works
under column grants; a guarded UPDATE with an `EXISTS` account-fence
predicate executes under the worker-shaped grants (UPDATE 1 with
enabled+matching generation, UPDATE 0 after disable).

Consequences implemented:

- The service takes NO row locks at all. All reads are plain MVCC
  SELECTs; every transition is an ATOMIC GUARDED UPDATE
  (compare-and-set on current state) — the single serialization point.
  A `FOR SHARE` pre-read followed by the guarded UPDATE on the same row
  was proven to DEADLOCK under three concurrent claimers on the owned
  PG16 (ShareLock-on-transaction cycle) and was removed.
- Neither role can row-lock `fake_admin_accounts` (column-SELECT only),
  so the credential fence rides STATEMENT-TIME inside the guarded
  claim/handoff CAS: the bound account must still be enabled with the
  recorded generation IN THE SAME atomic statement. A mid-job
  reset/disable makes the CAS match 0 rows — a stale worker result can
  never reach verified_unpublished, and the owned PG16 test proves no
  session row exists for a reset request.
- Residual window (documented in code and docs): an operator reset in
  the instant between a session-issuance recheck and its INSERT can
  create a session row; that session is refused at its FIRST use by
  the per-use live account recheck, so disable/reset still prevents any
  usable session.
- The web role holds no UPDATE on the request table (cannot row-lock
  it; its INSERT is column-limited, its revocation is the one
  session-column UPDATE it holds).

### 3.4 Role contract (applied by the operator at 224-b+)

`web_role_grant_sql` / `worker_role_grant_sql` generate the exact
reviewed matrix; role names are validated against a closed identifier
law before interpolation (safe finite error, no echo). Web:
USAGE(demo_control); column-scoped account SELECT (id, username,
password_hash, is_enabled, credential_generation — login hash check at
224-b); request SELECT; column-limited request INSERT (state not
nameable); session SELECT/INSERT; `UPDATE(revoked_at)`. NO UPDATE on
requests at all, no account/event writes, no business-table grants.
Worker: USAGE; account facts SELECT (id, is_enabled,
credential_generation — never username/password_hash); request SELECT;
column-limited request UPDATE (state, failure_code, claimed_at,
worker_job_id, worker_target_db, verified_at); session revocation-
facts SELECT (id, request_id, expires_at, revoked_at — never
token_hash/account_id/credential_generation). NO INSERT anywhere, no
business-table grants; the 221 source-export role is a separate
SELECT-only public-schema role, unchanged.

## 4. Focused verification (actual exits, host .venv)

- Unit, no database: `tests/unit/test_demo_web_control.py` — 26
  tests, exit 0 (state transitions, generation/revocation/
  zero-active gates, token hashing/no echo, deadlines, idempotent
  revoke, distinct requests/copies across two logins, unknown-state
  refusal, copy-uniqueness and one-live-session IntegrityError paths,
  safe-error no-echo). The in-memory fakes model DB defaults, CAS
  atomicity, and integrity errors; they do NOT model the
  statement-time account fence (the service's own rechecks cover the
  unit-level semantics; the fence is proven on real PG below).
- Migration-head units (root-allowed set, current-head literals only):
  `test_schema_status.py` (6), `test_alembic_request_diagnostics.py`
  (4), `test_alembic_email_jobs.py` (3),
  `test_alembic_quota_reservation_accounting_facts.py` (2),
  `test_alembic_external_tool_fence.py` (7),
  `test_alembic_key_prefix_default.py` (3),
  `test_alembic_accounting.py` (3),
  `test_alembic_provider_pricing.py` (3) — all exit 0 (57 tests
  together with the 26 above in one run, exit 0).
- OWNED PostgreSQL 16 (one new owned, labeled, loopback-bound,
  tmpfs-backed postgres:16 docker container per run; identity
  inspected before readiness/migration; exact run-owned cleanup):
  `tests/integration/test_demo_web_control_postgres.py` — 10 tests,
  `10 passed, 3 warnings in 5.96s`, exit 0:
  1. `test_migration_0028_shape_no_grants_not_public` — shape, no ACL,
     probe-role denial, NOT in public.
  2. `test_strict_downgrade_reupgrade` — downgrade to 0027 drops
     exactly the two tables (schema + 0027 tables survive); re-upgrade
     restores them at the exact head.
  3. `test_role_grant_matrix_denials` — real restricted roles; every
     forbidden surface denied 42501: web cannot UPDATE any request
     column, INSERT a named state/worker column, write accounts, FOR
     SHARE request rows, or read business tables; worker cannot
     INSERT request/session rows, UPDATE sessions, SELECT
     username/password_hash/token_hash/account_id, or FOR SHARE
     account rows; worker CAN FOR SHARE request rows (its one legal
     lock form) and reads the session facts projection.
  4. `test_restricted_role_service_lifecycle` — the REAL service under
     both restricted roles: web column-limited INSERT (stored state
     provably the DB default 'pending'), worker claim + verified
     handoff via column-level UPDATE CAS, worker facts read, web
     issue/validate session, worker cleanup refused while a live
     session binds the copy, web revoke, worker cleanup proceeds to
     cleaned; safe projection carries no token material.
  5. `test_token_never_stored_raw` — exactly one stored 64-hex hash per
     issued token; the raw canary token absent from `to_jsonb` of every
     row of all three demo tables.
  6. `test_concurrent_claims_exactly_once` — three concurrent worker
     claims: exactly one 'claimed', the rest the safe refusal code,
     final state 'claimed'.
  7. `test_stale_account_mid_job_refuses_handoff` — generation bump
     mid-job AND account disable mid-job both end
     failed/state_conflict; zero session rows for either request;
     neither reached verified_unpublished.
  8. `test_late_verified_result_refused` — aged copy ->
     failed/late_completion (CHECK-law-preserving timestamps).
  9. `test_safe_errors_no_canary_echo` — the canary copy identities are
     persisted on one request, then the SAME canary is handed off to a
     second claimed request: refused by copy uniqueness with
     `web_request_copy_reused`, and neither canary string appears in
     the safe message.
  10. `test_run_owned_exact_cleanup` — deletes only the recorded
     run-owned IDs (FK-safe order), REVOKES then drops the exact run
     roles, asserts zero table residue and zero role residue.
- Directly affected integration files:
  `tests/integration/test_demo_admin_accounts_postgres.py` +
  `tests/integration/test_gateway_key_prefix_migration_postgres.py` —
  exit 0 (2 items collected; 1 environment skip unrelated to the diff).
- Scoped Ruff (pinned E4/E7/E9/F policy) over all 19 changed code/test
  files: `All checks passed!`. `git diff --check`: clean.
- Protected untracked files verified hash-only, still untracked and
  unmodified: `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
  `codex.sh` `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
  `uv.lock` `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.

## 5. Negative / security / privacy / accounting evidence

- Security: 42501 denial matrix (item 4.3 above) incl. the verified
  row-locking privilege law; web can never move a request out of
  pending and never mark a copy verified; worker never reads token
  hashes or account credentials; raw browser token never stored;
  safe-error messages never echo canary copy identities (they were
  persisted to prove absence); no role/grant/RLA introduced by the
  migration.
- Privacy: all demo data is synthetic run-tagged canaries; no real
  company data, no real provider credentials, no mail, no browser, no
  production dump. The copy locator is a database NAME (never a path
  or DSN) and is omitted from every public-safe projection.
- Accounting: no business table, quota/accounting law, provider/Codex
  module, or inference route changed in either direction (schema diff
  limited to the two demo_control tables); the fresh-upgrade
  head assertion was updated accordingly.

## 6. Honest limitations

1. The demo is STILL UNUSABLE. No `/fakeadmin/login`, no demo HTTP, no
   worker wiring, no cleanup executor exists yet; 224-b+ on the SAME PR
   must supply the web route, the worker claim -> 221/222/223 job ->
   verified-handoff wiring, and the bounded cleanup path. Objective 225
   remains inert until this PR is terminal.
2. Residual session-issuance TOCTOU window (see 3.3) is documented,
   bounded by the per-use live recheck.
3. `tests/integration/test_demo_snapshot_sanitize_postgres.py` was NOT
   re-run locally for this diff: it requires
   `DEMO_SAN_TEST_SOURCE_URL`/`DEMO_SAN_TEST_TARGET_URL` owned 127.0.0.1
   PG16 URLs (the full 222 chain) and root directed that the unchanged
   legacy chain not be re-run for its one Alembic-head literal; its
   head literal was updated to 0028 and hosted CI will run it on the
   final head.
4. `tests/integration/test_alembic_fresh_upgrade_postgres.py::
   test_bare_fresh_alembic_upgrade_head_creates_wide_version_table`
   fails in THIS environment for a pre-existing, unrelated reason:
   current testcontainers defaults its connection URL to
   `postgresql+psycopg2://` and the host venv has no psycopg2. The
   identical failure reproduces on the pre-change file (verified by
   swapping in the HEAD version) — not caused by this diff; the other
   tests in that file that can run here pass, and hosted CI is the
   broad gate.
5. Unit fakes intentionally do not model the statement-time account
   fence (real-PG proof in item 4, test 7).
6. All PostgreSQL evidence is synthetic owned-PG16 docker runs; no
   installed-worker, browser, provider, or mail evidence exists yet.

## 7. Next same-PR stages (224-b and later)

Per the order: the dedicated `/fakeadmin/login`/wait/browser app on
this foundation under the web role; the privileged snapshot-worker
integration (claim -> 221 raw copy -> 222 sanitize -> 223 files ->
verified handoff via `VerifiedCopyBinding`, copy-role grants only after
complete 222+223 verification); web-readable publication of ONLY
verified sanitized file leaves; API-process finite settings captured at
login with an explicit capture timestamp; logout/expiry exact cleanup
consuming `cleanup_pending`/`cleaned`; installed-flow qualification.
No merge or next numeric objective while this PR remains open.
