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
  best-effort `record_failure` (never raises), capacity-true writes under a
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
`test_request_diagnostics` 25 (finite vocabularies, the 64-char overlong
known-param boundary with facts preserved, client-ID masking incl.
incomplete-discovery and fault cases, 8 KiB record bound, capacity/eviction
law, repeat no-op, resolve namespaces/overflow, status/cleanup),
`test_request_diagnostics_middleware` 24 (wire-status-wins, normal-auth-only
identity, log-binding alias masking, masker fault isolation,
capture-OFF determinism), `test_cli_diagnostics` 8 (actual-Typer
status/show/cleanup, `--json`, exit codes, namespace refusals),
`test_alembic_request_diagnostics` 4 (0026 up/down, single head, model
parity).

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
byte-identical); lowering the max by more than one eviction bound keeps a
true cap then drains; expiry is pruned on write and by `cleanup`;
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
- `projection-masking-v3-probe.json` — 14/14 pure projection/masking
  checks (known-secret discovery/masking, finite vocabularies,
  indexed-param positives, client-ID fail-closed).
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
  accounting transaction); `record_failure` never raises; the write adds
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
  record is dropped (`DROPPED_CAPACITY`); pre-existing excess drains at up
  to one eviction bound minus one row per subsequent non-repeat write.
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
