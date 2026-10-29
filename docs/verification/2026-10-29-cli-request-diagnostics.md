# Objective 201-a — Content-free request-failure diagnostics verification

Recorded 2026-10-29 for the 201 PR (base `main` at
`7cf8a7dbf02c8a5934ff25d3b28ad88b66f81afa`, the merged 200 PR #356).
This record describes what the bounded local runs below actually proved.
It is not provider, model, client, SMTP, credential, performance, security,
compliance, or release qualification, and it is not the 205 executable-only
transcript. Final-head CI for the publication commit is gated by root and
is reported honestly in the objective report, not certified here.

## Scope

Objective 201 added a default-OFF, content-free, bounded index for FAILED
terminal `/v1` outcomes so operators can inspect *why* a failed request was
rejected, by ID:

- One new PostgreSQL table `request_diagnostics` (migration
  `0026_request_diagnostics`, single head after `0025_catalog_refresh_applications`;
  32 -> 33 tables) with a stable unique server diagnostic ID
  (`gw-<uuid>`), a nonunique client-ID lookup column, bounded typed
  failure facts, `JSONB(none_as_null=True)` fact columns (absent fact =
  SQL NULL), a NULL-safe 8 KiB facts payload CHECK, and PG16-safe shape
  CHECKs (no `jsonb_object_length`).
- Typed shared service (`services/request_diagnostics.py` +
  `db/repositories/request_diagnostics.py`): finite reviewed vocabularies
  (source/reason/error-code/replay-code; 1-8 known param components within
  the 64-char column bound), known-secret client-ID masking (fail-closed:
  incomplete/faulty discovery omits the value with a fixed reason),
  best-effort `record_failure` (ordinary internal failures become typed
  drop outcomes; an external `CancelledError` propagates by design),
  capacity-true writes under a
  nonblocking transactional lock (repeat -> idempotent no-op BEFORE any
  prune/eviction; bounded expiry prune; bounded oldest eviction; honest
  `DROPPED_CAPACITY` instead of exceeding the cap), bounded
  `resolve` (explicit namespace, ambiguity capped at 100 with honest
  count/overflow), `status`, and table-only bounded `cleanup`.
- Narrow observation hooks: terminal-outcome observer (pure ASGI; actual
  wire status wins over classifier hints; normal-auth-only key identity),
  route-limit decision facts in `responses_request_policy.py`
  (`apply_codex_route_limits` rejections, operator
  `CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS` only when that ceiling rejects),
  resolution-boundary route facts and stream-failure facts in
  `responses_gateway.py`, fixed-safe error boundaries in
  `api/errors.py` / `api/policy_errors.py`, and request-ID log-binding
  alias masking in `api/middleware.py` (wire echo and auth unchanged;
  masking fault omits the binding, never 500s).
- Four startup settings (all default-OFF/no-op):
  `REQUEST_DIAGNOSTICS_ENABLED=false`,
  `REQUEST_DIAGNOSTICS_RETENTION_SECONDS=604800` (1..2592000),
  `REQUEST_DIAGNOSTICS_MAX_RECORDS=10000` (1..100000),
  `REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=100` (10..1000).
- CLI `slaif-gateway diagnostics status | request show | cleanup`
  (`--json` honored, including the fixed safe error boundary).

## Layers and exact commands

Environment for every run: existing Python 3.12 venv
(`/tmp/slaif192-coding-venv`), ambient `DATABASE_URL`/`TEST_DATABASE_URL`
unset, `-p no:cacheprovider`. No real provider/model/client/SMTP/Redis
contact; the upstream provider in the API layer is a respx mock with a
fail-closed `assert_all_mocked` module guard. PostgreSQL 16 evidence used a
freshly created unique-owned container (name prefix `slaif201a`, owner
label `slaif201a.owner`, loopback binding, tmpfs-backed), identity
inspected BEFORE readiness/migration, removed by exact container ID after.

### 1. New unit suites (61 PASS / 0 SKIP)

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_request_diagnostics.py \
  tests/unit/test_request_diagnostics_middleware.py \
  tests/unit/test_cli_diagnostics.py \
  tests/unit/test_alembic_request_diagnostics.py \
  -p no:cacheprovider -q
# 61 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Per-file counts derived from the JUnit `testcase.classname`:
`test_request_diagnostics` 25 (finite vocabularies with unknown values
made unavailable, the 71-char overlong known-param specimen against the
64-char column bound with the remaining failure facts preserved, closed
counts/positions key vocabularies, the 8 KiB whole-record bound,
unsafe-revision unavailability, client-ID/credential masking incl.
incomplete-discovery and fault cases, default-off never touching the
store, and route-fact/operator-ceiling facts at the resolution
boundary), `test_request_diagnostics_middleware` 24 (wire-status-wins,
normal-auth-only identity, log-binding alias masking, masker fault
isolation, capture-OFF determinism), `test_cli_diagnostics` 8
(actual-Typer status/show/cleanup, `--json`, exit codes, namespace
refusals), `test_alembic_request_diagnostics` 4 (0026 up/down, single
head, model parity).
This unit file does NOT prove the repository capacity/eviction/repeat/
resolve/status/cleanup algorithms; those algorithms are proven at the
owned-PostgreSQL-16 service layer (Section 3), the CLI layer, and by the
root probes.

### 2. Unchanged consumers, head-literal files, governance (727 PASS / 0 SKIP)

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_request_id_middleware.py \
  tests/unit/test_request_policy_errors.py \
  tests/unit/test_responses_request_policy.py \
  tests/unit/test_responses_stream_failures.py \
  tests/unit/test_responses_codex_streaming_tools.py \
  tests/unit/test_responses_codex_multiturn_replay.py \
  tests/unit/test_responses_codex_client_tools.py \
  tests/unit/test_codex_replay_service.py \
  tests/unit/test_capture_redaction.py \
  tests/unit/test_request_capture.py \
  tests/unit/test_codex_context_accounting.py \
  tests/unit/test_auth_error_mapping.py \
  tests/unit/test_openai_error_helpers.py \
  tests/unit/test_alembic_codex_replay_references.py \
  tests/unit/test_schema_status.py \
  tests/unit/test_alembic_accounting.py \
  tests/unit/test_alembic_email_jobs.py \
  tests/unit/test_alembic_external_tool_fence.py \
  tests/unit/test_alembic_key_prefix_default.py \
  tests/unit/test_alembic_provider_pricing.py \
  tests/unit/test_alembic_quota_reservation_accounting_facts.py \
  tests/unit/test_documentation_inventory.py \
  tests/unit/test_oap_governance.py \
  tests/unit/test_documentation_contract_drift.py \
  -p no:cacheprovider -q
# 727 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

`tests/unit/test_codex_context_accounting.py` (16) is byte-identical to
base. The eight head-literal files carry only the one-line migration-head
update. Per-file counts from JUnit: `test_responses_request_policy` 214,
`test_responses_codex_streaming_tools` 196,
`test_responses_codex_client_tools` 116,
`test_responses_codex_multiturn_replay` 44, `test_codex_replay_service` 24,
`test_documentation_inventory` 16, `test_request_capture` 15,
`test_documentation_contract_drift` 15, `test_responses_stream_failures`
15, `test_codex_context_accounting` 16, `test_oap_governance` 9,
`test_alembic_external_tool_fence` 7, `test_schema_status` 6,
`test_capture_redaction` 5, `test_request_id_middleware` 4,
`test_alembic_request_diagnostics`-sibling one-line head files 3/3/3/3/2,
`test_auth_error_mapping` 3, `test_request_policy_errors` 3,
`test_openai_error_helpers` 2.

### 3. Owned-PostgreSQL-16 service layer (11 PASS / 0 SKIP)

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_request_diagnostics_postgres.py \
  -p no:cacheprovider -q
# 11 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Normal record with absent positions persists as SQL NULL; gateway-ID repeat
is an idempotent single row; the 71-char all-known-component `error_param`
stores the row with `error_param` SQL NULL and the other facts intact
(regression for the root-reproduced VARCHAR(64) drop); an unrelated primary
key collision with a different gateway ID is unavailable, never "stored";
the positions/8 KiB CHECKs fire on real PG16; capacity eviction keeps the
configured max; a repeat AT full capacity is a true no-op (original row
byte-identical); lowering the max beyond what one write's bounded phases
clear keeps a true cap and drains across subsequent non-repeat writes;
expiry is pruned on write and by `cleanup`;
namespace/overflow lookups; concurrent writers never exceed the cap.

### 4. Owned-PostgreSQL-16 real-app API layer (11 PASS / 0 SKIP)

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_request_diagnostics_api_postgres.py \
  -p no:cacheprovider -q
# 11 passed, 0 failed, 0 errors, 0 skipped, exit 0 (~20 s)
```

The actual FastAPI application (real middleware stack including the
diagnostics observer) against owned PG16, provider mocked with a
fail-closed module egress guard; the write timeout raised to the maximum
allowed 1000 ms (the production default remains 100 ms). Every
query/assertion is correlated by that response's own
`X-SLAIF-Diagnostic-ID`: pre-auth 401 recorded with no key identity and no
ledger/reservation rows; capability denial records the actually resolved
route identity with byte/row-identical public response and accounting
state across disabled/enabled/failing-writer modes; unsupported stream
event after HTTP 200 records `stream_failure` with the actual wire status;
endpoint denial records key identity with NO route facts; Codex context
rejection records route UUID/pattern plus the actual decision numbers;
replay reference authorized (real persisted reference via the actual
`CodexReplayService`, positive 200, mock provider called) then denied 404
`responses_codex_replay_reference_not_found` with ZERO accounting change
once ONLY that controlled reference's expiry is set to `created_at + 30s`
(deterministic chronology: seeded at now-60s inside the key validity with
the long default lifetime; the stored `expires_at > created_at` invariant
is preserved; no sleep and no TTL race); the real CLI retrieves the
recorded failure by the returned diagnostic ID (and honest not-found /
namespace behavior); a truly slow awaited capacity-lock write exercises
the write-timeout boundary with a byte-identical public response;
content-free canaries (secret aliased into `X-Request-ID`, unknown fact
field, raw model wildcard suffix on a MATCHED configured prefix route)
never reach the stored row, the CLI output, or the logs, while the wire
request ID is preserved.

### 5. Static gates

```bash
/tmp/slaif192-coding-venv/bin/python -m ruff check app/ tests/
# 0 issues
python3 scripts/check_documentation.py
# DOCUMENTATION_CHECK=OK
git diff --check
# clean
```

## Root independent evidence (credited to root; not re-run)

These are ROOT actual-PG / actual-executable / pure-service probes, not
native pytest counts and not 205 installed-wheel/client/backend
qualification:

- `postgres-corrected-schema-probe.json` — actual PG16: 0026
  upgrade/down, 33 tables, normal record with absent positions as SQL
  NULL, exact gateway-ID repeat single row, CHECK failure NOT reported
  stored, unrelated primary-key collision NOT reported stored.
- `postgres-repeat-capacity-probe.json` — full-capacity repeat is a true
  no-op preserving the original row (re-run by root after the fix: PASS).
- `postgres-param-bound-probe.json` — the 71-char all-known-component
  `error_param` reproduced the pre-fix VARCHAR(64) insert rejection
  (whole diagnostic dropped); root recheck after the projection bound:
  STORED, `error_param` NULL, diagnostic retained, all earlier
  schema/history checks still PASS.
- `postgres-disabled-history-probe.json` — disabled drops new writes;
  retained resolve/status/cleanup work while OFF; the actual CLI finds the
  retained row while OFF; temporarily missing schema yields unavailable
  (not not_found) with nonzero CLI exit; status distinguishes
  disabled+unavailable; restoring the schema preserves the original row.
- `projection-masking-v3-probe.json` — 14 probe checks (13 behavior
  checks plus 1 source-stability check; these are probe assertions, not
  14 pytest tests) covering known-secret discovery/masking, finite
  vocabularies, indexed-param positives, and client-ID fail-closed
  behavior.
- `cli-missing-config-probe.json` / `cli-status-combination-probe.json` —
  the three `--json` commands with unset DB config exit nonzero with safe
  JSON; status text distinguishes disabled + store unavailable.
- `request-id-log-alias-probe.json` / `request_id_masker_fault_probe.py` —
  in-process log-alias leak reproduction (pre-fix) and masker fault
  isolation (post-fix).
- `observer-projection-boundary-probe.json` — observer projection
  boundaries (normal_auth attribution, wire-status-wins, typed counts).
- Strategic receipts under
  `/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/cli-feature-round/201-a-*.json`.

## Privacy, atomicity, and concurrency statements

- No request/response content is persisted anywhere by this facility: no
  bodies, prompts, tool arguments/results, media URLs, headers, queries,
  raw path values, or credentials. Verified by canary rows (row + CLI +
  log surfaces), the 8 KiB serialized bound, and the finite
  service-boundary vocabularies.
- Client IDs are untrusted: known incoming authentication shapes (custom
  gateway prefixes, bearer, cookie/session, proxy credentials, X-API-Key)
  are masked or omitted with fixed reasons (`secret_alias` / `unsafe` /
  `absent`); discovery failure or incompleteness omits the value
  (fail-closed). This is known-shape protection, not universal content
  sanitization.
- The write is an independent, bounded, best-effort transaction (never the
  accounting transaction); ordinary internal `record_failure` failures
  become typed drop outcomes (never raised to the caller) while an
  externally propagated `CancelledError` propagates by design; the write
  adds
  only the bounded awaited timeout/cleanup overhead; response
  status/body, admission, accounting, holds/fences, and cancellation are
  unchanged (proven byte/row-identical across recording modes).
- The cap is TRUE under concurrency (advisory nonblocking lock + bounded
  prune/evict + recount + `DROPPED_CAPACITY`), and a repeat of a retained
  row is idempotent even at full capacity (point lookup BEFORE any
  prune/eviction; the unique constraint remains the race fallback).
- There is no background expiry daemon; cleanup is bounded and
  table-only; lookup IDs grant no authentication authority.

## Documentation impact

- `docs/database-schema.md` — head `0026_request_diagnostics`, 33 tables,
  new section 5.25 (columns, indexes, NULL-safe CHECKs, retention/cap law),
  inventory row.
- `docs/configuration.md` — new "Request Failure Diagnostics (default
  OFF)" section: settings table, behavioral guarantees, honest drop and
  latency policy, startup-scope/recreate-container requirement, status
  semantics (calling-process setting, not live worker inspection).
- `docs/cli-reference.md` — diagnostics command subsection + complete
  command inventory entries.
- `docs/cli-field-administration.md` — objective 201 operational-surface
  section; stale proposed row removed.
- `docs/observability.md` — new facility section (failure-only,
  content-free, correlated, best-effort, log-binding protection,
  independent of capture).
- `docs/security-model.md` — new content-free boundary section;
  Redaction And Logging notes the request-ID log-binding alias masking
  (`api/middleware.py`; `logging.py` unchanged).

## Limitations

- The 100 ms default write timeout is tight by design: a cold
  first-connection statement preparation can legitimately be dropped as
  `DROPPED_TIMEOUT`; verification uses the maximum allowed 1000 ms.
- When the writer cannot make room through bounded eviction, the NEW
  record is dropped (`DROPPED_CAPACITY`); that drop commits the bounded
  prune already performed without inserting. The expiry-prune and
  oldest-eviction phases each have their own bound; pre-existing excess
  (e.g. after lowering the cap) drains across subsequent non-repeat
  writes, never by an unbounded sweep. Capacity-lock acquisition makes at
  most three bounded nonblocking attempts with 10 ms retry intervals, all
  inside the single configured awaited-write budget (no background jobs,
  no unbounded retries, no queue, no scheduler).
  These are honest documented losses, not silent over-capacity.
- No background expiry daemon: idle storage requires repeated `cleanup`
  (or the bounded prune-on-write).
- The param/code/reason vocabularies are finite and reviewed, not
  exhaustive; unknown fact FIELDS drop the write, while unsafe optional
  code/reason/param PATH VALUES become unavailable (other facts
  preserved).
- Client-ID and log-binding protection is known-shape; arbitrary private
  strings that match no known shape are not claimed sanitized.
- `diagnostics status` reports the CALLING CLI process's loaded setting,
  not a live worker inspection (no worker heartbeat/config registry);
  retained rows cannot prove current recording state.
- The replay API-layer evidence seeds the finalized ledger and the
  reference through the ACTUAL `CodexReplayService` on owned PG16 and
  drives the real app; it is fixture-level replay coverage, not full
  Codex client qualification.
- No release, RC, production, security, or compliance certification
  follows from this record; final-head CI is the root merge gate.

## 201-b addendum — CI repair, completed evidence, documentation accuracy, and operator recipe

### What changed in 201-b (allowed paths only)

- CI repair: `app/slaif_gateway/main.py` 87 -> 83 lines by removing four
  redundant middleware-order comments only (the `install_request_*`
  docstrings already document the ordering). Executable AST verified
  identical to 201-a SELF `1ba0b30`; the UNCHANGED
  `tests/unit/test_main_app_structure.py` now passes 5/5 including the
  `< 84` guard (the 201-a final-head `Unit, lint, and migration head`
  failure was exactly `test_main_app_only_wires_app_and_routes`; root
  independently reproduced 4 passed / 1 failed with the unchanged file).
- Code-quality repair: the new middleware test file now uses ONE
  consistent import style for the middleware module
  (`import slaif_gateway.api.middleware as mw`, referenced as
  `mw.RequestIdMiddleware`); no semantic change.
- Completed accounting evidence in
  `tests/integration/test_request_diagnostics_api_postgres.py`:
  `_key_state` now also selects the five external-tool fence columns
  (state/reservation binding/request id/acquired/expiry); the stream
  failure test compares per-request reserved-counter deltas across
  disabled/enabled/failing-writer modes, verifies the released
  reservation leaves ZERO residual reserved quota, and asserts the fence
  boundary stays `none`/unbound in every mode; the pre-admission 401 and
  slow-write timeout tests assert the COMPLETE before/after accounting
  state (all six counters zero, no ledger/reservation rows, fence
  none/unbound). Exact response-ID correlation and the fail-closed
  mock-egress guard preserved; no production accounting changes.
- ONE new focused unit case
  (`tests/unit/test_request_diagnostics.py`): an externally propagated
  `asyncio.CancelledError` is NOT swallowed by an enabled
  `record_failure` (controlled `_record` double, no DB); existing
  middleware cancellation evidence unchanged.
- Docstrings only in `services/request_diagnostics.py`:
  `record_failure` qualifies "never raises" (ordinary internal failures
  become typed drop outcomes; external cancellation propagates by
  design), and `_record` states the accurate two-phase bounded prune /
  drop / drain semantics with the three-attempt/10 ms bounded
  lock-acquisition inside the single awaited-write budget. Executable
  AST verified identical to `1ba0b30`.
- Documentation accuracy (in place): "never raises" qualifications;
  "one bound minus one row" replaced by the two-phase bounded semantics;
  "rather than slowing the response" removed; "NO new telemetry
  channels" replaced by "no remote exporter / extra content logs /
  admin UI / metrics pipeline"; probe attribution corrected (14 probe
  checks = 13 behavior + 1 source-stability, not 14 pytest tests);
  status semantics (calling-process setting, not live worker
  inspection) in configuration/CLI docs.

### 201-b verification evidence (exact layers)

Agent runs (existing venv, ambient `DATABASE_URL`/`TEST_DATABASE_URL`
unset, `-p no:cacheprovider`):

- Unit batch — JUnit `tests=126 failures=0 errors=0 skipped=0`, actual
  exit 0: 62 new diagnostics units (`test_request_diagnostics` 26 = 25
  from 201-a plus the 1 NEW cancellation case; middleware 24; CLI 8;
  alembic 4), 5 unchanged `test_main_app_structure` (now passing), 4
  `test_request_id_middleware` + 15 `test_responses_stream_failures`
  (unchanged consumers), and 40 governance (inventory 16 + OAP 9 +
  drift 15).
- Owned-PostgreSQL-16 real-app API layer re-run — JUnit
  `tests=11 failures=0 errors=0 skipped=0`, actual exit 0 (~20 s): the
  SAME 11 tests with the strengthened accounting oracles; fresh owned
  container (prefix `slaif201a`, label `slaif201a.owner`, loopback,
  tmpfs, identity inspected before migration) removed by exact ID; zero
  owned containers remaining.
- Static gates: `ruff check app/ tests/` all checks passed;
  `python3 scripts/check_documentation.py` OK (128 files);
  `git diff --check` clean.
- AST identity vs `1ba0b30`: `main.py` full AST identical (comments
  only); `services/request_diagnostics.py` AST with docstrings stripped
  identical (docstring-only delta). All other product/migration/settings
  bytes unchanged.

Prior versus new counts (JUnit-derived; the earlier "71 tests" terminal
prose was a partial count and is superseded): 201-a introduced 83
UNIQUE new cases (61 unit + 11 storage PG + 11 API PG across distinct
runs). 201-b adds exactly ONE unique new case (the cancellation
regression; 84 total). Every other 201-b run is a rerun of the same
tests with strengthened oracles and counts as OVERLAP, not additional
unique evidence. The unit Typer/CliRunner CLI cases are typed-service
boundary tests; the actual CLI+PG subprocess evidence is the API/PG
layer's real-CLI test and the root probes; the 205 installed-wheel
transcript remains outstanding and unclaimed.

### Explicit corrections to the 201-a report overclaims (old report stays immutable)

- "6 new test files (71 tests)" -> 83 unique new cases (61 unit + 11
  storage PG + 11 API PG); 201-b adds 1 (84).
- "14/14 probe" -> 14 probe checks = 13 behavior + 1 source-stability
  (probe assertions, not 14 pytest tests).
- "drains at up to one bound minus one row" -> two-phase bounded
  semantics (expiry-prune and oldest-eviction phases each have their own
  bound; a capacity drop commits the prune without inserting; at most
  three bounded nonblocking lock attempts with 10 ms retries inside the
  single awaited-write budget).
- "record_failure never raises" -> ordinary internal failures become
  typed drop outcomes; an external `CancelledError` propagates by design.
- "NO new telemetry channels" -> this is an authorized PostgreSQL index;
  no remote exporter / extra content logs / admin UI / metrics pipeline
  is added. The independent full-capture section and its privacy
  boundary are unchanged.
- "rather than slowing the response" -> removed; the awaited bounded
  completion latency is disclosed with no zero-latency/performance
  claim.
- The 25 service UNIT cases prove projection/masking/default-off/
  route-fact boundaries; the repository capacity/eviction/repeat/
  resolve/status/cleanup algorithms are proven at the owned-PG service
  layer, the CLI layer, and by the root probes — not by the unit file.

### Operator deployment and operation recipe (instructions only)

These are copyable instructions, NOT authorization to deploy, contact
production, or run real clients/providers. Use the pinned revision
(the merged PR commit); the application performs NO automatic
production migration — the single explicit `db upgrade` below is the
only schema change, and it is 201-a's already-authorized migration.
No gateway-key/module identity or policy migration is required; no key
recreation/rotation and no accounting-data rewrite.

1) Back up the database first (existing operations runbook
   `docs/runbooks/database-backup-restore.md`):

   ```bash
   docker compose exec -T postgres pg_dump \
     -U slaif -d slaif_gateway --format=custom \
     --file=/tmp/slaif_gateway.dump
   docker compose cp postgres:/tmp/slaif_gateway.dump ./backups/slaif_gateway.dump
   ```

2) Build the pinned revision and run the ONE explicit migration:

   ```bash
   docker compose build
   docker compose up -d postgres redis
   docker compose run --rm api slaif-gateway db current   # pre-state
   docker compose run --rm api slaif-gateway db upgrade
   docker compose run --rm api slaif-gateway db current   # expect head 0026_request_diagnostics (33 tables)
   ```

3) Deploy default-OFF (nothing is recorded until explicitly enabled):

   ```bash
   docker compose up -d api worker scheduler
   ```

4) Optional enablement via the four existing settings — EDIT or ADD
   these lines in the existing operator `.env` file (dotenv syntax,
   preserving all other existing settings); this snippet is a file
   edit, NOT shell assignments to paste and run. Configure them
   consistently for ALL API workers (the facility does not detect or
   reconcile per-worker differences); none of these are secrets, so do
   not expose them beyond the operator environment:

   ```dotenv
   REQUEST_DIAGNOSTICS_ENABLED=true
   REQUEST_DIAGNOSTICS_RETENTION_SECONDS=604800     # 1 .. 2592000
   REQUEST_DIAGNOSTICS_MAX_RECORDS=10000            # 1 .. 100000
   REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=100         # 10 .. 1000
   ```

   In Docker Compose the `api` service loads `env_file`; after changing
   `.env`, RECREATE the affected containers (a same-container restart
   does not reload `env_file`):

   ```bash
   docker compose up -d --force-recreate api
   ```

5) Reproduce an operator's EXISTING failing request (keep credentials
   and content out of docs/logs — prefer a bounded synthetic input):
   issue the failing request as before, capture the returned
   `X-SLAIF-Diagnostic-ID` response header, then look it up:

   ```bash
   docker compose run --rm api slaif-gateway diagnostics request show \
     --request-id gw-... --namespace gateway --json
   docker compose run --rm api slaif-gateway diagnostics status --json
   ```

   An absent record is an honest `not_found`/`unavailable` outcome
   (recording was off, retention expired, or the write was dropped) —
   it is not a claim about why a particular unrecorded historical
   request is absent.

6) Disable recording while PRESERVING retained lookup/cleanup: set
   `REQUEST_DIAGNOSTICS_ENABLED=false` and recreate the api containers.
   Retained rows stay readable/cleanable; TTL and the cap still apply.
   There is no background expiry daemon, so idle storage needs bounded,
   repeated explicit cleanup. Use `--json` and repeat the bounded
   cleanup while `store_available` is true and `deleted_count` is
   greater than 0, until a cleanup reports `deleted_count` 0:

   ```bash
   docker compose run --rm api slaif-gateway diagnostics cleanup --json
   # repeat the cleanup command above while store_available=true and
   # deleted_count > 0; physical cleanup is finished only when a
   # cleanup reports deleted_count = 0
   ```

   `diagnostics status` alone cannot prove physical cleanup is
   finished: `retained_records` counts only NON-expired rows, so rows
   that have merely passed their TTL no longer appear there, and the
   TEXT status while recording is OFF in particular shows no expiry
   state. Do not arm the separate full-capture facility for this
   purpose. `diagnostics status` reports the CALLING process's loaded
   setting, not a live inspection of the API workers.

7) Rollback: disable + recreate FIRST — retaining the new table keeps
   the diagnostics history readable for a diagnostics-capable reader,
   including a later RE-UPGRADE, while the rolled-back code ignores it.
   Note that an OLDER CLI has no `diagnostics` command at all even
   though the older runtime safely ignores the extra table, so retained
   rows are reachable only through a diagnostics-capable CLI or the
   database itself. An explicit
   `0026_request_diagnostics` downgrade irreversibly deletes only the
   diagnostic history and must be coordinated with the old code and
   stopped writers. Disabling recording never erases retained records;
   no all-record delete command exists.

### CI / final-head state (201-b)

- 201-a SELF `1ba0b30` final head: nine of the ten checks succeeded;
  `Unit, lint, and migration head` failed solely on the main-structure
  line guard (6217 passed / 1 failed / 1 skipped in the CI job).
  201-b repairs exactly that with comments-only changes.
- The new 201-b SELF requires ALL ten final-head checks; they are
  PENDING at this publication and remain the root-gated merge gate. No
  all-green claim is made here.
