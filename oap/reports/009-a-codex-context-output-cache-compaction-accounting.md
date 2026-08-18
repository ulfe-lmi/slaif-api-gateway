# OAP Coding-Agent Report — 009-a

## Work order

- Identifier: `009-a`
- Work-order file: `oap/orders/009-a-codex-context-output-cache-compaction-accounting.md`
- Numeric objective: `009`
- PR mode: `CREATED_NEW_PR`

## Status

BLOCKED

## Executive summary

Objective 009-a implemented the bounded Codex context/output, cache-write/read,
long-context, and V1 compaction contracts on one new objective branch and PR.
The focused local evidence, one isolated PostgreSQL integration test, migration
lifecycle, immutable fixture check, and corrected pinned Codex CLI loopback
verifier all pass.

The objective is blocked at GitHub CI because six pre-existing tests hardcode
the former Alembic head `0013_codex_replay_references`. The implementation
correctly adds sole head `0014_codex_context_accounting_compaction`, so those
assertions now fail. All six test paths are outside the 009-a allowed-path list.
The active order explicitly forbids editing such a required test contract and
requires a `BLOCKED` report naming the exact files so a narrow 009-b continuation
can authorize them. No scope exception was invented.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `234`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`
- PR title: `[OAP 009] Bound Codex context, cache, compaction, and accounting`
- PR state at report time: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/009-codex-context-output-cache-compaction-accounting`
- Starting remote SHA: `635f20f6ca9efdc66d13f56bacb2193d00340de3`
- Implementation head SHA: `1fcb90b2e947c1cd4a43c68b34e5f6ad04353600`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `1fcb90b2e947c1cd4a43c68b34e5f6ad04353600` (`OAP 009: bound Codex context and compaction`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Changes made

- Added strict route-level `codex_limits` containing exactly positive integer
  `context_window_tokens`, `default_max_output_tokens`, and
  `max_output_tokens`, with `default <= max < context`. Codex-qualified routes
  are bounded by operator ceilings `CODEX_ABSOLUTE_MAX_INPUT_TOKENS=1050000`
  and `CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS=128000`; an omitted client output limit
  uses the route default of 32,768 in the documented qualification profile.
  Ordinary non-Codex behavior retains its existing 1,024 default.
- Finalized Codex route limits after route selection and before Redis, pricing,
  quota reservation, or provider dispatch. Context/output excess and malformed
  route metadata fail closed; limits are not silently clamped.
- Added strict `pricing_metadata.codex_accounting` parsing and conservative
  reservation/finalization across ordinary input, cache-read input,
  cache-write input, ordinary output, reasoning output, and long-context input
  and output multipliers. The documented profile uses a 272,000 input-token
  threshold with 2x input and 1.5x output multipliers. Malformed, incomplete,
  contradictory, or unpartitionable usage/pricing fails closed.
- Added unary and streaming cache-write token parsing while preserving cache
  read, reasoning, and total-token invariants. Exact finalization partitions
  prompt tokens into mutually exclusive ordinary/cache-read/cache-write
  dimensions and completion tokens into ordinary/reasoning dimensions.
- Added fifth default-off `codex_compaction` key/template/route gate, dependent
  on the four preceding Codex capabilities, plus explicit route-compatible UUID
  allowlisting, same-provider/model enforcement, and exact pinned V1 compact
  request/response handling. V2, background, hosted/provider-state, unknown,
  and unbounded shapes remain denied.
- Extended replay binding with a length-delimited composite HMAC over opaque
  compaction identifier and ciphertext, same-key ownership, expiry, and
  route/model compatibility. Persistence occurs only after finalized usage
  accounting. Raw identifiers, ciphertext, prompts, outputs, request/response
  bodies, cache keys, and reasoning content are not stored.
- Added migration `0014_codex_context_accounting_compaction`, one isolated
  PostgreSQL integration test, focused unit coverage, and an executable bounded
  loopback verifier for pinned Codex CLI `0.147.0`.
- Rejected every non-identity `Content-Encoding` before auth or side effects on
  both `/v1/responses` and `/v1/responses/compact`; no decompression feature was
  added.
- Synchronized accounting, Codex/Responses compatibility, configuration,
  database, provider forwarding, security, matrix, streaming/live-burn, and
  durable repository-governance documentation.

## Files changed

The implementation commit changes exactly these 40 order-authorized paths:

- `.env.example`
- `AGENTS.md`
- `app/slaif_gateway/api/openai_compat.py`
- `app/slaif_gateway/config.py`
- `app/slaif_gateway/db/models.py`
- `app/slaif_gateway/providers/base.py`
- `app/slaif_gateway/schemas/accounting.py`
- `app/slaif_gateway/schemas/policy.py`
- `app/slaif_gateway/schemas/pricing.py`
- `app/slaif_gateway/schemas/providers.py`
- `app/slaif_gateway/services/accounting.py`
- `app/slaif_gateway/services/codex_replay_service.py`
- `app/slaif_gateway/services/key_template_service.py`
- `app/slaif_gateway/services/pricing.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `app/slaif_gateway/services/responses_request_policy.py`
- `app/slaif_gateway/services/responses_route_capabilities.py`
- `app/slaif_gateway/services/upstream_payloads.py`
- `app/slaif_gateway/services/upstream_request_contracts.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/configuration.md`
- `docs/database-schema.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `docs/streaming-live-burn-margin.md`
- `migrations/versions/0014_codex_context_accounting_compaction.py`
- `oap/active`
- `oap/orders/009-a-codex-context-output-cache-compaction-accounting.md`
- `scripts/verify_codex_context_compaction.py`
- `tests/integration/test_codex_context_accounting_postgres.py`
- `tests/unit/test_alembic_codex_context_accounting_compaction.py`
- `tests/unit/test_codex_context_accounting.py`
- `tests/unit/test_codex_replay_service.py`
- `tests/unit/test_key_template_service.py`
- `tests/unit/test_openai_provider_adapter.py`
- `tests/unit/test_openai_provider_streaming.py`
- `tests/unit/test_responses_codex_compaction.py`

The final report-publication commit adds only
`oap/reports/009-a-codex-context-output-cache-compaction-accounting.md`.

## Acceptance-criteria evidence

### Criterion 1 — bounded Codex context and output

- Result: PASSED locally.
- Evidence: strict route and operator bounds, ordering before side effects,
  omitted/default/max behavior, over-context refusal, and unchanged ordinary
  behavior are covered by the focused unit selection. The final selection has
  604 passing tests and zero failures/errors/skips.

### Criterion 2 — cache and long-context accounting

- Result: PASSED locally.
- Evidence: strict pricing parsing, conservative reservation, disjoint exact
  finalization, cache-read/write, reasoning output, threshold-edge behavior,
  multipliers, and malformed/contradictory usage refusal are in the same 604
  passing tests. Existing Responses quota-pipeline coverage separately has 74
  passing tests and zero failures/errors/skips.

### Criterion 3 — conservative metering and privacy

- Result: PASSED locally.
- Evidence: request/history/tool-schema bytes remain part of conservative
  admission metering. Tests assert that raw compaction values are absent from
  persistence and safe errors. A scoped secret/private-value pattern scan found
  no credential-like committed material. The verifier persisted no raw payloads.

### Criterion 4 — exact V1 compaction and HMAC-only replay

- Result: PASSED locally.
- Evidence: default-off five-gate policy, exact V1 schema, V2/background/hosted
  denial, finalized-accounting-before-persistence, composite HMAC binding,
  same-key ownership, expiry, and route/provider/model compatibility have unit
  coverage. The isolated PostgreSQL compaction reference test passed against a
  disposable database and verified absence of raw ID/ciphertext in the HMAC
  row.

### Criterion 5 — compression refusal and pinned client

- Result: PASSED locally.
- Evidence: route-level tests reject `gzip`, `zstd`, and unknown encodings on
  both Responses endpoints before auth/side effects. The successful pinned CLI
  loopback reports `CONTENT_ENCODING_ABSENT=true`; no decompression path exists.

### Criterion 6 — harmless Codex verifier

- Result: PASSED after a safe verifier correction.
- Evidence: `/usr/bin/codex --version` is `codex-cli 0.147.0`. Source checkout
  `/tmp/slaif-oap005-codex-source-YSOVKH` is commit
  `be6e8eac029b183056b7e4402879f15d2c85f61b` at exact tag
  `rust-v0.147.0`. The final command and safe output are recorded below.

### Criterion 7 — schema, migration, docs, and fixture

- Result: PASSED locally; BLOCKED in broad CI by out-of-scope legacy assertions.
- Evidence: local 0014 migration test and lifecycle passed; `alembic heads`
  reports exactly `0014_codex_context_accounting_compaction`; schema/model/docs
  were synchronized; OAP/docs contracts have 17 passing tests. Frozen fixture
  SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
  GitHub CI failures are exclusively six assertions that still expect 0013.

### Criterion 8 — one PR, exact scope, no prohibited execution

- Result: PASSED.
- Evidence: exactly one objective PR (#234); implementation commit contains 40
  allowed paths. No full local unit/integration/E2E/browser/Docker/Compose/HPC
  suite, real provider, production credential/data, or side-effecting provider
  tool was used.

### Criterion 9 — final report-head checks green

- Result: BLOCKED.
- Evidence: implementation-head CI has eight successful checks and two failed
  checks. Both failures are caused by six out-of-scope legacy migration-head
  assertions. The report-only commit may trigger fresh checks; strategic review
  must verify its `SELF` commit without rewriting this immutable report.

### Criterion 10 — merge and report topology

- Result: PASSED for coding-agent-controlled behavior.
- Evidence: no merge and no auto-merge. This report commit is required to have
  implementation head `1fcb90b2e947c1cd4a43c68b34e5f6ad04353600` as first
  parent and to change only this report path; remote topology is verified before
  FIFO response.

## Local verification

- `pytest -q tests/unit/test_config.py tests/unit/test_responses_route_capabilities.py tests/unit/test_pricing_service.py tests/unit/test_accounting_service_usage.py tests/unit/test_openai_provider_adapter.py tests/unit/test_openai_provider_streaming.py tests/unit/test_provider_streaming_sse.py`: FAILED BEFORE COLLECTION — system Python lacked `structlog`; no test executed. Verification then used the repository `.venv`.
- `.venv/bin/python -m pytest -q --junitxml=/tmp/slaif-oap009-focused-unit-final.xml tests/unit/test_codex_context_accounting.py tests/unit/test_responses_codex_compaction.py tests/unit/test_alembic_codex_context_accounting_compaction.py tests/unit/test_accounting_service_finalize.py tests/unit/test_accounting_service_usage.py tests/unit/test_codex_replay_service.py tests/unit/test_config.py tests/unit/test_db_models_accounting.py tests/unit/test_key_template_service.py tests/unit/test_openai_provider_adapter.py tests/unit/test_openai_provider_streaming.py tests/unit/test_pricing_service.py tests/unit/test_provider_streaming_sse.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py tests/unit/test_upstream_payload_reconstruction.py`: PASSED — 604 tests, 0 failures, 0 errors, 0 skipped, 11.272 seconds.
- Earlier focused iterations exposed two implementation defects in encrypted-reasoning candidate shaping and one misplaced new assertion in a Chat test. They were corrected before the final 604-test run; no failing local focused result is represented as a pass.
- `.venv/bin/python -m pytest -q --junitxml=/tmp/slaif-oap009-responses-quota.xml tests/unit/test_v1_responses_quota.py`: PASSED — 74 tests, 0 failures, 0 errors, 0 skipped, 25.209 seconds.
- `.venv/bin/python -m pytest -q --junitxml=/tmp/slaif-oap009-contracts-final.xml tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`: PASSED — 17 tests, 0 failures, 0 errors, 0 skipped, 1.388 seconds.
- `.venv/bin/ruff check tests/unit/test_responses_codex_compaction.py && .venv/bin/python -m pytest -q --junitxml=/tmp/slaif-oap009-compaction-routes.xml tests/unit/test_responses_codex_compaction.py`: PASSED — Ruff clean; 23 tests, 0 failures, 0 errors, 0 skipped, 4.006 seconds.
- `TEST_DATABASE_URL='postgresql+asyncpg:///slaif_oap009_test_codex_context' .venv/bin/python -m pytest -q tests/integration/test_codex_context_accounting_postgres.py`: PASSED — 1 test; one deprecation warning only.
- Disposable database lifecycle: database `slaif_oap009_test_codex_context` did not pre-exist, was explicitly created, used only through `TEST_DATABASE_URL`, migrated through head by the integration fixture, then used for one downgrade `0014 -> 0013` and re-upgrade `0013 -> 0014`, dropped, and independently verified absent. `DATABASE_URL` was not used.
- The first migration lifecycle shell attempt FAILED BEFORE ALEMBIC because of the shell typo `.mvenv=''` (`command not found`). The same database was retained and the corrected command completed current/downgrade/re-upgrade/current, confirmed sole `alembic heads` value 0014, and dropped the database.
- `.venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: first run FAILED SAFELY with `RESULT=ERROR` / `ERROR=Verifier request handling failed safely.` The verifier's inherited request sanitizer hardcoded `/v1/responses` and therefore rejected the expected second request to `/v1/responses/compact`; no private output was emitted or persisted. The verifier was corrected to use endpoint-aware validation while retaining the same header/privacy checks.
- `.venv/bin/ruff format scripts/verify_codex_context_compaction.py && .venv/bin/ruff check scripts/verify_codex_context_compaction.py && .venv/bin/python -m compileall -q scripts/verify_codex_context_compaction.py && .venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: PASSED with the exact safe result keys:

  ```text
  RESULT=OK
  CLI_VERSION_MATCHED=true
  REQUEST_COUNT=3
  PROMPT_CACHE_REUSED=true
  CACHE_READ_USAGE_SEEN=true
  CACHE_WRITE_USAGE_SEEN=true
  REASONING_USAGE_SEEN=true
  BELOW_THRESHOLD_SEEN=true
  THRESHOLD_EDGE_SEEN=true
  ABOVE_THRESHOLD_SEEN=true
  V1_COMPACT_SEEN=true
  POST_COMPACT_CONTINUATION_SEEN=true
  CONTENT_ENCODING_ABSENT=true
  LOOPBACK_ONLY=true
  RAW_PAYLOADS_PERSISTED=false
  ```

- Scoped `.venv/bin/ruff check` over every changed Python path: PASSED.
- `.venv/bin/python -m compileall -q` over affected application, migration, verifier, integration, and unit paths: PASSED.
- `git diff --check`: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact digest above, unchanged.
- Exact implementation path-set and staged-diff checks: PASSED — 40 allowed implementation paths; no `.local-provider-catalog/` artifact staged or committed.
- Full local unit suite: NOT RUN — explicitly prohibited by the active order; broad unit coverage supplied by GitHub CI.
- Full local integration suite: NOT RUN — explicitly prohibited by the active order; only the one new isolated integration file ran locally.
- Local E2E, browser, Docker/Compose, and HPC suites: NOT RUN — explicitly prohibited by the active order.
- Real upstream provider smoke: NOT RUN — explicitly prohibited; the manual verifier was loopback-only.

## GitHub CI / required checks

Check state observed for implementation head
`1fcb90b2e947c1cd4a43c68b34e5f6ad04353600` after a full 30-second wait block:

- `Analyze Python`: SUCCESS — 1m15s.
- `CodeQL`: SUCCESS — 3s.
- `Analyze (javascript-typescript)`: SUCCESS — 41s.
- `Analyze (python)`: SUCCESS — 1m18s.
- `Docker Compose smoke`: SUCCESS — 54s.
- `Documentation hygiene`: SUCCESS — 8s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m26s.
- `Playwright browser smoke`: SUCCESS — 1m14s.
- `Unit, lint, and migration head`: FAILURE — full unit result was 2,642 passed, 5 failed, 10 warnings. The five failures are legacy assertions expecting Alembic head 0013:
  - `tests/unit/test_schema_status.py` — `test_get_alembic_head_revision_reads_single_head`
  - `tests/unit/test_alembic_accounting.py` — `test_alembic_has_exactly_one_head_revision`
  - `tests/unit/test_alembic_email_jobs.py` — `test_alembic_has_exactly_one_head_revision_after_fourth_migration`
  - `tests/unit/test_alembic_key_prefix_default.py` — `test_alembic_has_exactly_one_head_revision_after_fifth_migration`
  - `tests/unit/test_alembic_provider_pricing.py` — `test_alembic_has_exactly_one_head_revision`
- `PostgreSQL integration tests`: FAILURE — 131 passed, 1 failed, 35 warnings in 76.04 seconds. `tests/integration/test_gateway_key_prefix_migration_postgres.py::test_migration_0005_normalizes_gateway_key_prefix_and_default` expects 0013 but correctly observes 0014.
- All required checks green for the implementation head at report drafting: no.
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: pinned `/usr/bin/codex`
  `codex-cli 0.147.0` was made available for the required verifier; its source
  identity was independently checked at the commit/tag recorded above. The
  existing repository `.venv`, local PostgreSQL client/server, and standard Git/
  GitHub tooling were used.
- `sudo`-level setup performed: Codex CLI installation only. No PostgreSQL
  package installation was performed.
- Durable setup changes committed/documented: executable verifier and its
  documented contract only. No generated local setup artifacts were committed.
- Dependency lock changes: none. A generated unallowed `uv.lock` artifact from
  an early environment attempt was removed before staging; no user artifact was
  cleaned or altered.

## Documentation

- Updated `AGENTS.md`, `.env.example`, and the accounting, Codex compatibility,
  Responses compatibility, compatibility matrix, configuration, database
  schema, provider forwarding, security, and streaming/live-burn documents.
- Documentation states the strict limits, accounting dimensions and threshold,
  default-off gate chain, exact supported V1 compact boundary, HMAC-only
  ownership, compression refusal, privacy prohibitions, and unsupported/deferred
  surfaces without claiming production certification or broader Codex support.
- Documentation/OAP drift tests pass locally (17 tests).

## Safety and scope confirmations

- Unrelated files changed: no. The implementation commit contains only the 40
  allowed paths. The unrelated generated `.local-provider-catalog/` state was
  preserved and not committed.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real provider or external side-effecting tool accessed: no; loopback only.
- Real email sent: no.
- Prompts/completions/raw bodies/provider keys/gateway plaintext keys/cache keys/
  compaction identifiers or ciphertext persisted in evidence: no.
- Required tests skipped/not run: yes — broad local suites were deliberately not
  run because the order assigns them to GitHub CI; exact non-runs are listed.
- Scope deviation: no. Six required test-contract updates were intentionally not
  made because their paths are outside 009-a's explicit allowlist.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO; the strategically
  authored bytes were committed unchanged.
- `DATABASE_URL` destructive setup: NO.
- Disposable DB isolation: YES, explicit `TEST_DATABASE_URL` database only,
  dropped and verified absent.
- Report-publication commit changes only this report file: yes (verified before
  commit and again against the remote head before FIFO response).

## Known limitations / blockers

The following six exact required test paths must change their hardcoded expected
Alembic head from `0013_codex_replay_references` to
`0014_codex_context_accounting_compaction`, but 009-a does not authorize them:

1. `tests/unit/test_schema_status.py`
2. `tests/unit/test_alembic_accounting.py`
3. `tests/unit/test_alembic_email_jobs.py`
4. `tests/unit/test_alembic_key_prefix_default.py`
5. `tests/unit/test_alembic_provider_pricing.py`
6. `tests/integration/test_gateway_key_prefix_migration_postgres.py`

No product logic failure appears in either failed GitHub job: the unit job has
2,642 passes around five stale head assertions, and integration has 131 passes
around one stale head assertion. Nevertheless, failed checks are not green, so
criterion 9 and objective completion remain blocked.

## Recommended strategic follow-up

Activate a narrow 009-b amendment on the same PR authorizing only the six legacy
migration-head test paths above, update their expected sole head to 0014, run the
smallest focused local proof permitted by that continuation, push, and allow all
GitHub checks to rerun. The strategic model retains acceptance and merge
authority; the coding agent has not merged and will not merge.
