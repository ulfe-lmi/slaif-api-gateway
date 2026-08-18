# OAP Coding-Agent Report — 009-e

## Work order

- Identifier: `009-e`
- Work-order file: `oap/orders/009-e-distinguish-request-user-input-ui-header.md`
- Numeric objective: `009`
- PR mode: `AMENDED_EXISTING_PR`

## Status

BLOCKED

## Executive summary

The reviewed 009-e UI-header distinction is implemented and published on the
existing objective PR. The recursive Codex authority detector now recognizes
the benign JSON-schema key `header` only at the complete normalized path
`parameters.properties.questions.items.properties.header`, and only after the
exact fully gated `functions.request_user_input` function taxonomy is proven.
Every other header-bearing key/path/tool and every authorization, secret,
connector, server, approval, MCP, hosted-tool, and ordinary-tool denial remains
active. Focused local tests, contracts, quality checks, fixture integrity, and
all ten implementation-head GitHub checks pass.

The unchanged exact Codex 0.147.0 verifier remains blocked after that false
positive is resolved. It now rejects the captured compact request with safe
code `responses_input_item_invalid` at
`input[2].internal_chat_message_metadata_passthrough`. No raw request, tool,
message, or response content was printed or persisted. The order requires
`BLOCKED` when the unchanged verifier exposes another mismatch, so no further
policy change or scope expansion was attempted. A strategic continuation must
independently review this new exact mismatch.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `234`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`
- PR title: `[OAP 009] Bound Codex context, cache, compaction, and accounting`
- PR state at report time: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/009-codex-context-output-cache-compaction-accounting`
- Starting remote/report SHA: `6a0d062f6c1832ae781bcd1bdc9db86dfba9b165`
- Remote `main`: `635f20f6ca9efdc66d13f56bacb2193d00340de3`
- Implementation head SHA: `32bded4c3881d1a4e70796dd6550c2ac81c1f9f7`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Implementation commit pushed before the report commit:
  `32bded4c3881d1a4e70796dd6550c2ac81c1f9f7`
  (`OAP 009-e: distinguish pinned UI header schema`)
- Report commit first parent: same as Implementation head SHA
- Objective-009 PR count: exactly one, PR #234
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Changes made

- Added one immutable allowed authority-key path containing only
  `parameters.properties.questions.items.properties.header`.
- Made the recursive detector path-aware while keeping its default/no-allowlist
  behavior semantically strict.
- Supplies the exception only inside the exact pinned Codex child declaration
  after namespace `functions`, name `request_user_input`, and type `function`
  all match. Other namespaces, tools, types, paths, and ordinary Responses tools
  receive no exception.
- Preserved recursive scanning below the allowed `header` property's schema and
  across all siblings; the implementation does not skip the tool or parameters
  scan.
- Added focused coverage for the exact pinned schema, conservative metering,
  plural and alternate paths, other tools, authority/secret/connector/server/
  approval/MCP/hosted siblings, safe-evidence privacy, ordinary behavior, and
  compact policy.
- Updated only the three authorized contracts that needed to describe the
  path-exact UI-label distinction and unchanged provider-header/authority
  denial.
- Left `scripts/verify_codex_context_compaction.py` unchanged and ran its exact
  pinned command once. A bounded diagnostic used an in-memory helper
  replacement only to expose the safe rejection code/parameter above; it
  changed no file and printed no captured content.

## Files changed

The implementation commit changes exactly these eight order-authorized paths:

- `app/slaif_gateway/services/responses_request_policy.py`
- `docs/codex-compatibility.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/009-e-distinguish-request-user-input-ui-header.md`
- `tests/unit/test_responses_codex_client_tools.py`
- `tests/unit/test_responses_codex_compaction.py`

The final report-publication commit adds only
`oap/reports/009-e-distinguish-request-user-input-ui-header.md`.

## Acceptance-criteria evidence

### Criterion 1 — exact pinned UI-header exception only

- Result: PASSED locally and in GitHub CI.
- Evidence: the exact pinned request-user-input schema passes under every gate.
  `headers` at that location, singular `header` one level higher or lower, the
  same complete path under `wait` or a collaboration tool, and ordinary uses
  remain denied. The allowlist has one immutable complete normalized path and
  is supplied only to the exact `functions.request_user_input` function tuple.

### Criterion 2 — recursive denials, bounds, taxonomy, metering, and privacy

- Result: PASSED locally and in GitHub CI.
- Evidence: focused tests preserve nested `authorization`, `secret`,
  `connector_id`, `server_url`, `approval_mode`, MCP, and hosted-type rejection.
  The allowed property's nested schema and every sibling are still scanned.
  Existing declaration/schema/depth/property/type/additional-properties bounds,
  taxonomy, canonicalization, and ordinary behavior remain green. The exact
  pinned schema remains conservatively included in byte/token metering, while
  private canaries and paths do not enter safe messages or evidence.

### Criterion 3 — unchanged exact Codex 0.147.0 verifier

- Result: BLOCKED.
- Evidence: the exact required command ran once against numeric loopback and
  emitted only:

  ```text
  RESULT=ERROR
  ERROR=Captured V1 compact request failed gateway policy.
  ```

  The bounded in-memory diagnostic rerun emitted only:

  ```text
  SAFE_POLICY_CODE=responses_input_item_invalid
  SAFE_POLICY_PARAM=input[2].internal_chat_message_metadata_passthrough
  ```

  The verifier did not emit `RESULT=OK`, `REQUEST_COUNT=3`, or
  `GATEWAY_COMPACT_POLICY_ACCEPTED=true`, and this report does not claim that it
  did. No raw input item, message metadata, body, tool declaration, request, or
  response was output or persisted. No real provider was called. No policy was
  widened for the newly exposed mismatch.

### Criterion 4 — focused checks, paths, fixture, and GitHub CI

- Result: PASSED except for the unchanged verifier in Criterion 3.
- Evidence: 111 focused tests and 17 OAP/documentation contract tests pass;
  scoped Ruff/compile, diff hygiene, exact pointer/order/report topology, and
  exact eight-path staging pass. The fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
  All ten implementation-head GitHub checks completed successfully. Fresh
  report-head checks may run after SELF publication and are not represented as
  implementation-head evidence.

### Criterion 5 — one PR, no merge, immutable report topology

- Result: PASSED for coding-agent-controlled behavior.
- Evidence: exactly one objective-009 PR exists, remains open, and has no
  auto-merge request. No merge was performed. This report commit is required to
  change only this report and have the literal implementation SHA as first
  parent; remote topology is verified before the FIFO response.

## Local verification

- `.venv/bin/ruff check app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py`: PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py`: PASSED.
- `.venv/bin/python -m pytest -q tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py`: PASSED — 111 tests, zero failures/errors/skips; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`: PASSED — 17 tests, zero failures/errors/skips.
- `git diff --check`: PASSED.
- `test "$(cat oap/active)" = "009-e"`, exact single-order/no-preexisting-report topology checks, and exact eight-path staged check: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact approved digest above.
- `/usr/bin/codex --version`: PASSED — `codex-cli 0.147.0`.
- `git -C /tmp/slaif-oap005-codex-source-YSOVKH rev-parse HEAD` and `git describe --tags --exact-match HEAD`: PASSED — `be6e8eac029b183056b7e4402879f15d2c85f61b`, `rust-v0.147.0`.
- Pinned source file `codex-rs/core/src/tools/handlers/request_user_input_spec.rs`: INSPECTED — confirms the benign `header` UI-label schema at the exact allowed path.
- `.venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: BLOCKED — exact safe output shown in Criterion 3; the verifier file was unchanged, no raw payload was printed/persisted, and no real provider was called.
- One diagnostic loopback rerun used an in-memory helper replacement only to emit the safe code/parameter shown above: BLOCKED consistently; no repository file or captured content was written.
- Other failed development attempts: NONE.
- Full local unit suite: NOT RUN — explicitly prohibited by the active order.
- Full local integration suite and PostgreSQL: NOT RUN — explicitly prohibited by the active order.
- Local E2E, browser, Docker/Compose, and HPC suites: NOT RUN — explicitly prohibited by the active order.
- Real upstream provider/tool smoke: NOT RUN — explicitly prohibited; both verifier calls were numeric-loopback-only with a dummy key.

## GitHub CI / required checks

Check state observed for implementation head
`32bded4c3881d1a4e70796dd6550c2ac81c1f9f7` after exact 30-second wait
blocks:

- `Unit, lint, and migration head`: SUCCESS — 1m56s.
- `Analyze (javascript-typescript)`: SUCCESS — 41s.
- `Analyze Python`: SUCCESS — 1m05s.
- `Analyze (python)`: SUCCESS — 1m35s.
- `PostgreSQL integration tests`: SUCCESS — 2m03s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m25s.
- `Playwright browser smoke`: SUCCESS — 1m22s.
- `Docker Compose smoke`: SUCCESS — 1m00s.
- `Documentation hygiene`: SUCCESS — 7s.
- `CodeQL`: SUCCESS — 1s.

## Documentation impact

- `docs/codex-compatibility.md` identifies the pinned benign UI-label path,
  exact taxonomy gate, and unchanged recursive/provider authority behavior.
- `docs/responses-compatibility.md` distinguishes this complete path from HTTP
  or provider headers and records ordinary-tool isolation.
- `docs/security-model.md` records the single path-and-taxonomy exception while
  preserving all adjacent header, authority, secret, connector, server, MCP,
  approval, and hosted-tool denials.
- No accounting, configuration, schema, model, migration, repository, pricing,
  admin, template, dependency, fixture, verifier, CI, deployment, README, or
  prior OAP history changed.

## Security and privacy notes

- The exception is a single immutable complete schema-key path reachable only
  through the exact fully gated pinned taxonomy. It is not a substring, value,
  general `header`, provider-header, or ordinary-tool exemption.
- The detector continues recursive traversal below the UI-label property and
  through all siblings. All existing provider/hosted/MCP/secret/connector/
  approval checks remain active.
- Tests and diagnostics retain only aggregate byte/token evidence and fixed safe
  errors; no raw body, schema, prompt, message metadata, response, key, ID,
  ciphertext, or subprocess output was persisted or printed.
- No real provider, production service, external tool, email, database, or
  deployment action ran locally. No `.local-provider-catalog/` artifact was
  staged or committed.

## Human/strategic review notes

- A future order must determine why the exact pinned compact request contains
  `input[2].internal_chat_message_metadata_passthrough` and whether any safe,
  shape-specific compatibility treatment is appropriate. This turn makes no
  architecture or risk-acceptance decision about that item.
- The approved UI-header distinction is independently green and retains all
  ordinary and authority safeguards. Strategic review can isolate its next
  decision to the exact newly exposed input-item mismatch.
- PR #234 must not be merged while this criterion remains blocked unless the
  strategic model/human explicitly resolves it in a subsequent order. The
  coding agent did not merge and did not enable auto-merge.

## Final safety statement

This turn amended only PR #234, published a truthful blocked result, preserved
the immutable report protocol, and performed no merge or auto-merge action.
Coding-agent `OK` after remote SELF verification means only that this execution
turn, immutable report, and claimed GitHub state are published; it does not mean
the work is accepted.
