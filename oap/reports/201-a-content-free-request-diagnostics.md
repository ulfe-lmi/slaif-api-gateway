# OAP Objective 201-a — final report: content-free request-failure diagnostics

Work order: `oap/orders/201-a-content-free-request-diagnostics.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `201-a` (5 bytes, no trailing newline); order sha256
`d672e05c8fb2aa8d130d942d3b030d654887adb12b6577b2f06dc95b2f31696e`
(19,920 bytes), active pointer sha256
`f54b470ec1d09f71b75b696b1d28dc7fabe013601db010365e5a8ad901735f94`,
both verified before committing and re-verified at HEAD).
Branch: `oap/201-content-free-request-diagnostics`; base: `main`
`7cf8a7dbf02c8a5934ff25d3b28ad88b66f81afa` (merged 200 PR #356; unchanged).
PR mode: CREATE_NEW_PR — the ONE new PR for objective 201, #357,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/357, base `main`.
The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: 98d7b01111027663251f4f5bb9b37492225c3641
Report publication commit: SELF

## Implementation commit (this round)

1. `98d7b01111027663251f4f5bb9b37492225c3641` — "Add content-free
   request-failure diagnostics with bounded CLI lookup (201-a)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `201-a` + the allowed changes listed below
   (40 files total). First parent is `main`
   `7cf8a7dbf02c8a5934ff25d3b28ad88b66f81afa`.

## What changed (allowed paths only)

New product surface (all new files):

- `app/slaif_gateway/db/models.py` — `RequestDiagnostic` (33rd table;
  unique `uq_request_diagnostics_gateway_request_id`; NULL-safe
  COALESCE size CHECKs, 8 KiB facts payload bound; PG16-safe, no
  `jsonb_object_length`).
- `migrations/versions/0026_request_diagnostics.py` — single head after
  `0025_catalog_refresh_applications` (up/down verified on real PG16).
- `app/slaif_gateway/schemas/request_diagnostics.py` — typed
  record/lookup/status/cleanup schemas and bounds.
- `app/slaif_gateway/services/request_diagnostics.py` — typed shared
  service: finite reviewed vocabularies; 1-8 known param components
  within the 64-char column bound (overlong known paths project to
  unavailable with the other facts preserved); known-secret client-ID
  masking reusing the pure capture-redaction discovery/masking
  (fail-closed on incomplete discovery or fault); `record_failure`
  never raises; capacity-true writes under a nonblocking transactional
  lock (repeat of a retained row = idempotent no-op BEFORE any
  prune/eviction; bounded expiry prune; bounded oldest eviction; honest
  `DROPPED_CAPACITY` instead of exceeding the cap; unique constraint as
  race fallback); bounded `resolve` (explicit namespace, ambiguity
  capped at 100, honest count/overflow); `status`; table-only bounded
  `cleanup`.
- `app/slaif_gateway/db/repositories/request_diagnostics.py` — bounded
  repository (advisory nonblocking capacity lock, point repeat lookup,
  bounded prune/evict, single-statement windowed resolve counts).
- `app/slaif_gateway/api/request_diagnostics.py` — pure-ASGI
  terminal-outcome observer (actual observed wire status wins over
  classifier hints; normal-auth-only key identity; bounded best-effort
  write at the final outcome).
- `app/slaif_gateway/cli/diagnostics.py` — `diagnostics status |
  request show | cleanup` (typed, `--json` honored including the fixed
  safe error boundary; lookup IDs grant no authority).

Narrow integration points (modified, allowed):
`app/slaif_gateway/api/errors.py`, `app/slaif_gateway/api/policy_errors.py`,
`app/slaif_gateway/api/middleware.py` (request-ID log-binding alias
masking; wire echo and auth decisions unchanged; masking fault omits the
binding, never 500s), `app/slaif_gateway/services/responses_gateway.py`
(resolution-boundary route facts + stream-failure facts),
`app/slaif_gateway/services/responses_request_policy.py` (route-limit
decision facts, operator ceiling only when that ceiling rejects),
`app/slaif_gateway/cli/main.py`, `app/slaif_gateway/main.py`,
`app/slaif_gateway/config.py` (four default-OFF/no-op settings with the
documented ranges), `.env.example`.

Tests (new): `tests/unit/test_request_diagnostics.py` (25),
`tests/unit/test_request_diagnostics_middleware.py` (24),
`tests/unit/test_cli_diagnostics.py` (8),
`tests/unit/test_alembic_request_diagnostics.py` (4),
`tests/integration/test_request_diagnostics_postgres.py` (11),
`tests/integration/test_request_diagnostics_api_postgres.py` (11).

Existing tests: ONLY the eight required current-head literal updates
(one line each: migration head `0025_...` -> `0026_request_diagnostics`),
all behavioral assertions preserved; `tests/unit/test_codex_context_accounting.py`
remains byte-identical to base and was RUN unchanged.

Docs: as listed under Documentation impact below.

No UI, no client/server module/profile changes, no provider adapter
changes, no new dependencies or workflows, no
replay/ledger/accounting/hold/fence/rate implementation changes, no
full-capture changes, no email/batch/owner features, no global event
bus, no generic logging framework, no 202+ work.

## Verified evidence (exact layers, commands, exits)

Agent-run evidence (this execution; ambient
`DATABASE_URL`/`TEST_DATABASE_URL` unset; existing Python 3.12 venv
`/tmp/slaif192-coding-venv`; `-p no:cacheprovider`):

- New unit suites — 61 PASS / 0 SKIP (JUnit
  `tests=61 failures=0 errors=0 skipped=0`, actual exit 0):
  service 25 (finite vocabularies, the 71-char overlong known-param
  boundary with facts preserved, client-ID masking incl.
  incomplete-discovery/fault cases, 8 KiB bound, capacity/eviction law,
  repeat no-op, resolve namespaces/overflow, status/cleanup),
  middleware 24, actual-Typer CLI 8, alembic 0026 up/down/single-head/
  model-parity 4.
- Unchanged consumers + head-literal files + governance — 727 PASS /
  0 SKIP (JUnit `tests=727 failures=0 errors=0 skipped=0`, actual exit
  0): request-ID middleware 4, policy errors 3, Responses request
  policy 214, stream failures 15, Codex streaming tools 196,
  multi-turn replay 44, client tools 116, replay service 24, capture
  redaction 5, request capture 15, `test_codex_context_accounting` 16
  (byte-identical), auth error mapping 3, error helpers 2, replay
  references alembic 3, schema status 6, the seven other head-literal
  files 3/3/7/3/3/2, documentation inventory 16, OAP governance 9,
  contract drift 15.
- Owned-PostgreSQL-16 service layer — 11 PASS / 0 SKIP (JUnit
  `tests=11 failures=0 errors=0 skipped=0`, actual exit 0): normal
  record absent positions as SQL NULL; repeat idempotent single row;
  the 71-char all-known-component `error_param` stores the row with
  `error_param` SQL NULL and other facts intact; unrelated PK
  collision never "stored"; positions/8 KiB CHECKs fire on PG16;
  capacity eviction keeps the max; repeat AT full capacity is a true
  no-op (original row byte-identical); lowered-max true cap then
  drains; expiry pruned on write and by cleanup; namespace/overflow
  lookups; concurrent writers never exceed the cap. Owned container
  (prefix `slaif201a`, label `slaif201a.owner`, loopback, tmpfs,
  identity inspected BEFORE migration) removed by exact ID.
- Owned-PostgreSQL-16 real-app API layer — 11 PASS / 0 SKIP (JUnit
  `tests=11 failures=0 errors=0 skipped=0`, actual exit 0, ~20 s):
  actual FastAPI app with the real middleware stack against owned
  PG16; provider mocked behind a fail-closed `assert_all_mocked`
  module egress guard; write timeout raised to the maximum allowed
  1000 ms (production default remains 100 ms). All queries correlated
  by each response's own `X-SLAIF-Diagnostic-ID`: pre-auth 401 without
  key identity or ledger/reservation rows; capability denial with the
  actually resolved route identity and byte/row-identical public
  response and accounting across disabled/enabled/failing-writer
  modes; unsupported stream event after 200 records `stream_failure`
  with the actual wire status; endpoint denial with key identity and NO
  route facts; Codex context rejection with route UUID/pattern and the
  actual decision numbers; replay authorized against a REAL persisted
  reference (actual `CodexReplayService` seed, positive 200, mock
  provider called) then denied 404 with zero accounting change once
  ONLY that controlled reference's expiry is set to `created_at + 30s`
  (deterministic chronology — seeded at now-60s inside key validity
  with the long default lifetime; the stored `expires_at > created_at`
  invariant preserved; no sleep, no TTL race); real CLI lookup against
  the owned database; a truly slow awaited capacity-lock write
  exercising the write-timeout boundary with a byte-identical public
  response; content-free canaries (secret aliased into `X-Request-ID`,
  unknown fact field, raw model wildcard suffix on a MATCHED configured
  prefix route) absent from stored row, CLI output, and logs while the
  wire request ID is preserved.
- Static gates: `ruff check app/ tests/` — all checks passed;
  `python3 scripts/check_documentation.py` — OK (128 files), run before
  and after the docs finalization; `git diff --check` — clean.

Root-independent evidence (root-run; credited as ROOT evidence, not an
agent run; not re-run here). Actual PG16 / actual-executable /
pure-service probes, no native pytest count and no 205
installed-wheel/client/backend qualification:

- `postgres-corrected-schema-probe.json` — 0026 upgrade/down, 33
  tables, normal record with absent positions as SQL NULL, exact
  gateway-ID repeat single row, CHECK failure NOT reported stored,
  unrelated primary-key collision NOT reported stored.
- `postgres-repeat-capacity-probe.json` — full-capacity repeat is a
  true no-op preserving the original row (re-run by root after the
  repeat-before-eviction fix: PASS).
- `postgres-param-bound-probe.json` — the 71-char all-known-component
  `error_param` reproduced the pre-fix VARCHAR(64) insert rejection
  (whole diagnostic dropped); root recheck after the projection bound:
  STORED, `error_param` NULL, diagnostic retained, all earlier
  schema/history checks still PASS (service bytes stable during the
  recheck).
- `postgres-disabled-history-probe.json` — disabled drops new writes;
  retained resolve/status/cleanup work while OFF; the actual CLI finds
  the retained row while OFF; temporarily missing schema yields
  unavailable (not not_found) with nonzero CLI exit; status
  distinguishes disabled+unavailable; restoring the schema preserves
  the original row.
- `projection-masking-v3-probe.json` — 14/14 pure projection/masking
  checks. `cli-missing-config-probe.json` /
  `cli-status-combination-probe.json` — safe JSON error boundary and
  status text distinctions. `request-id-log-alias-probe.json` /
  `request_id_masker_fault_probe.py` — log-alias leak reproduction
  (pre-fix) and masker fault isolation (post-fix).
  `observer-projection-boundary-probe.json` — observer projection
  boundaries. Strategic receipts under
  `review-artifacts/cli-feature-round/201-a-*.json`.

Full command lists and per-file counts:
`docs/verification/2026-10-29-cli-request-diagnostics.md`.

## CI / final-head state

Final-head CI for this publication head (SELF) is PENDING at this
publication and remains the root-gated merge gate; no all-green claim is
made here. All final SELF checks are mandatory before any merge. No
merge, auto-merge, or self-activation by the coding agent; no 202
activation; no new control signal sent by this report. ONE new PR #357
for objective 201.

## Limitations

- The 100 ms default write timeout is tight by design: a cold
  first-connection statement preparation can legitimately be dropped as
  `DROPPED_TIMEOUT`; verification used the maximum allowed 1000 ms.
- When the writer cannot make room through bounded eviction, the NEW
  record is dropped (`DROPPED_CAPACITY`); pre-existing excess drains at
  up to one eviction bound minus one row per subsequent non-repeat
  write. Documented honest losses, not silent over-capacity.
- No background expiry daemon: idle storage needs repeated `cleanup`
  (or the bounded prune-on-write).
- Param/code/reason vocabularies are finite and reviewed, not
  exhaustive; unknown fact FIELDS drop the write, while unsafe
  optional code/reason/param PATH VALUES become unavailable (other
  facts preserved).
- Client-ID and log-binding protection is known-shape (reusing the
  existing redaction primitives); arbitrary private strings matching no
  known shape are not claimed sanitized.
- `diagnostics status` reports the CALLING CLI process's loaded
  setting, not a live worker inspection (no worker heartbeat/config
  registry); retained rows cannot prove current recording state.
- The replay API-layer evidence seeds the ledger/reference through the
  ACTUAL `CodexReplayService` on owned PG16 and drives the real app; it
  is fixture-level replay coverage, not full Codex client
  qualification.
- No full local matrix rerun; final-head CI is the broad mandatory
  gate and is PENDING here. No release, RC, production, security, or
  compliance certification follows; the 205 installed-executable
  transcript remains outstanding.

## Documentation impact

Documentation updated: docs/database-schema.md, docs/configuration.md, docs/cli-reference.md, docs/cli-field-administration.md, docs/observability.md, docs/security-model.md, docs/verification/2026-10-29-cli-request-diagnostics.md, docs/verification/README.md

- `docs/database-schema.md`: head `0026_request_diagnostics`, 33
  tables, new section 5.25 (columns, indexes, NULL-safe CHECKs,
  retention/cap law), inventory row.
- `docs/configuration.md`: new "Request Failure Diagnostics (default
  OFF)" section (settings table, guarantees, honest drop/latency
  policy, startup-scope/container-recreate requirement, status
  semantics).
- `docs/cli-reference.md`: diagnostics command subsection + complete
  command inventory entries.
- `docs/cli-field-administration.md`: objective 201 operational-surface
  section; stale proposed row removed.
- `docs/observability.md`: new facility section.
- `docs/security-model.md`: new content-free boundary section;
  Redaction And Logging note on the request-ID log-binding alias
  masking (`api/middleware.py`; `logging.py` unchanged).
- `docs/verification/2026-10-29-cli-request-diagnostics.md` (new) +
  `docs/verification/README.md` index entry.
