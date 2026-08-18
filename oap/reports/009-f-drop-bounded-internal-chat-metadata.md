# OAP Coding-Agent Report — 009-f

## Work order

- Identifier: `009-f`
- Work-order file:
  `oap/orders/009-f-drop-bounded-internal-chat-metadata.md`
- Numeric objective: `009`
- PR mode: `AMENDED_EXISTING_PR`

## Status

BLOCKED

## Executive summary

The bounded 009-f internal-chat-metadata privacy repair is implemented and
published on the existing objective PR. Under all five Codex key gates, exact
`internal_chat_message_metadata_passthrough` is accepted only on the seven
authorized history types, including an omitted message type, as null or a JSON
mapping whose canonical encoding is at most 32,768 bytes. Each input item is
copied, the value is validated without interpreting nested contents, and the
entire field is deleted before ordinary item validation, canonical/effective
body construction, provider reconstruction, metering, replay/HMAC extraction,
safe evidence, logging, audit, metrics, export, or persistence. It contributes
zero model-input tokens. Ordinary, partially gated, additional-tools, hosted,
and unknown item paths retain strict rejection.

Focused local tests, contract checks, quality checks, topology and fixture
integrity, and all ten implementation-head GitHub checks pass. The unchanged
exact Codex 0.147.0 verifier remains blocked after the metadata mismatch is
resolved: it rejects the captured compact request with safe code
`responses_codex_tool_roundtrip_invalid` at `input[8].id`. No raw request,
tool, message, metadata, identifier, or response content was printed or
persisted. The order requires `BLOCKED` when the unchanged verifier exposes
another mismatch, so no further policy change or scope expansion was
attempted. Strategic review must independently decide the next action.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `234`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`
- PR title: `[OAP 009] Bound Codex context, cache, compaction, and accounting`
- PR state at report time: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/009-codex-context-output-cache-compaction-accounting`
- Starting remote/report SHA: `973e8b9a20e3c1ad49c5efc66a00a9e900ddf66c`
- Remote `main`: `635f20f6ca9efdc66d13f56bacb2193d00340de3`
- Implementation head SHA: `3a427e9abd039c22e9309c4e767f772369f7496a`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Implementation commit pushed before the report commit:
  `3a427e9abd039c22e9309c4e767f772369f7496a`
  (`OAP 009-f: drop bounded internal chat metadata`)
- Report commit first parent: same as Implementation head SHA
- Objective-009 PR count: exactly one, PR #234
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Changes made

- Added an exact field constant, a fixed 32,768-byte canonical JSON cap, and an
  immutable supported-type set for message (typed or omitted type), reasoning,
  function call, function call output, custom tool call, custom tool call
  output, and compaction history items.
- Copies every input-item mapping before compatibility handling and never
  mutates the caller's input mapping in place.
- Drops the exact field only when request-envelope, client-tool,
  streaming-tool-event, encrypted-reasoning-replay, and compaction-replay
  gates are all true and the item has one exact authorized type.
- Accepts only null or a JSON mapping. Canonical JSON serialization must
  succeed and encode to no more than 32,768 bytes. Invalid or oversized values
  receive fixed safe code
  `responses_codex_internal_chat_metadata_invalid` at the exact field
  parameter without echoing the value.
- Deletes the field before the existing strict item-type validators. Paths
  outside the exact gate/type boundary keep the field and therefore retain
  their existing unknown-field rejection behavior.
- Added focused coverage for all authorized item types in one linked history,
  unchanged caller input, clean-body equivalence, upstream reconstruction,
  replay/HMAC candidates, zero metering, exact cap edges, null, malformed and
  non-JSON values, every missing gate, ordinary requests, additional tools,
  hosted and unknown types, and private-canary absence.
- Updated only the five affected accounting, compatibility, forwarding,
  privacy, and security contracts.
- Left `scripts/verify_codex_context_compaction.py` unchanged and ran its exact
  pinned command once. One bounded diagnostic rerun used only an in-memory
  helper replacement to expose the fixed safe rejection code and parameter; it
  changed no repository file and printed no captured content.

## Files changed

The implementation commit changes exactly these ten order-authorized paths:

- `app/slaif_gateway/services/responses_request_policy.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/009-f-drop-bounded-internal-chat-metadata.md`
- `tests/unit/test_responses_codex_compaction.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`

The final report-publication commit adds only
`oap/reports/009-f-drop-bounded-internal-chat-metadata.md`.

## Acceptance-criteria evidence

### Criterion 1 — exact fully gated drop and downstream absence

- Result: PASSED locally and in GitHub CI.
- Evidence: focused tests exercise typed and omitted-type message, reasoning,
  linked function/custom call-output pairs, and compaction items together.
  They prove the caller body remains unchanged while the effective body,
  compact upstream reconstruction, replay candidates, HMAC inputs, and
  metering evidence exactly match the corresponding clean body with the field
  absent. Private metadata canaries are absent from safe evidence, upstream
  bodies, candidates, exceptions, and stringified safe output.

### Criterion 2 — type, size, privacy, and unsupported-path denials

- Result: PASSED locally and in GitHub CI.
- Evidence: null and an exactly 32,768-byte canonical object pass and are
  dropped; a 32,769-byte canonical object fails safely. Strings, lists,
  integers, booleans, and non-JSON mappings fail with the fixed safe code and
  exact field parameter. Removing each of the five gates individually rejects
  the field. Ordinary requests, `additional_tools`, hosted
  `web_search_call`, and unknown item types reject rather than drop it, with no
  private-canary echo.

### Criterion 3 — existing validation, HMAC, accounting, and metering

- Result: PASSED locally and in GitHub CI.
- Evidence: the field is removed before existing item validation and all
  canonical downstream derivations. Existing message, reasoning, function and
  custom tool linkage, compaction, replay ownership/HMAC, route, and metering
  tests remain green. Clean and metadata-bearing inputs yield identical
  metering and candidate/HMAC inputs, proving the discarded field contributes
  zero input tokens or bytes.

### Criterion 4 — unchanged exact Codex 0.147.0 verifier

- Result: BLOCKED.
- Evidence: the exact required command ran once against numeric loopback and
  emitted only:

  ```text
  RESULT=ERROR
  ERROR=Captured V1 compact request failed gateway policy.
  ```

  The bounded in-memory diagnostic rerun emitted only:

  ```text
  SAFE_POLICY_CODE=responses_codex_tool_roundtrip_invalid
  SAFE_POLICY_PARAM=input[8].id
  ```

  The verifier did not emit `RESULT=OK`, `REQUEST_COUNT=3`, or
  `GATEWAY_COMPACT_POLICY_ACCEPTED=true`, and this report does not claim that it
  did. No raw input item, ID, message metadata, body, tool declaration,
  request, or response was output or persisted. No real provider was called.
  No policy was widened for the newly exposed mismatch.

### Criterion 5 — focused checks, paths, fixture, and GitHub CI

- Result: PASSED except for the unchanged verifier in Criterion 4.
- Evidence: 71 focused tests and 17 OAP/documentation contract tests pass;
  scoped Ruff/compile, diff hygiene, exact pointer/order/report topology, exact
  ten-path staging, and fixture integrity pass. The fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
  All ten implementation-head GitHub checks completed successfully. Fresh
  report-head checks may run after SELF publication and are not represented as
  implementation-head evidence.

### Criterion 6 — one PR, no merge, immutable report topology

- Result: PASSED for coding-agent-controlled behavior.
- Evidence: exactly one objective-009 PR exists, remains open, and has no
  auto-merge request. No merge was performed. This report commit is required
  to change only this report and have the literal implementation SHA as first
  parent; remote topology is verified before the FIFO response.

## Local verification

- `.venv/bin/python -m pytest -q tests/unit/test_responses_codex_compaction.py tests/unit/test_responses_codex_multiturn_replay.py`: PASSED — 71 tests, zero failures/errors/skips; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`: PASSED — 17 tests, zero failures/errors/skips.
- `.venv/bin/ruff check app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_compaction.py tests/unit/test_responses_codex_multiturn_replay.py`: PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_compaction.py tests/unit/test_responses_codex_multiturn_replay.py`: PASSED.
- `git diff --check`: PASSED.
- `test "$(cat oap/active)" = "009-f"`, exact single-order/no-preexisting-report topology checks, and exact ten-path staged check: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact approved digest above.
- `/usr/bin/codex --version`: PASSED — `codex-cli 0.147.0`.
- `git -C /tmp/slaif-oap005-codex-source-YSOVKH rev-parse HEAD` and `git describe --tags --exact-match HEAD`: PASSED — `be6e8eac029b183056b7e4402879f15d2c85f61b`, `rust-v0.147.0`.
- Pinned source files `codex-rs/core/src/client.rs` and
  `codex-rs/model-provider/src/provider.rs`: INSPECTED — confirm OpenAI
  identity preserves internal chat metadata while non-OpenAI clears it, and
  OpenAI/Azure supports the required remote compaction path while ordinary
  custom providers do not.
- Pinned executed-tool metadata source: INSPECTED — confirms an approximately
  32-KiB attempted-tool metadata boundary and that tool arguments can be
  present, supporting complete discard rather than downstream use.
- `.venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: BLOCKED — exact safe output shown in Criterion 4; the verifier file was unchanged, no raw payload was printed/persisted, and no real provider was called.
- One diagnostic loopback rerun used an in-memory helper replacement only to
  emit the safe code/parameter shown above: BLOCKED consistently; no
  repository file or captured content was written.
- Failed development attempt: the first exact-staging wrapper was rejected by
  the command safety filter before Bash started because it contained `rm -f`
  temporary-file cleanup. Nothing ran, staged, or changed. The wrapper was
  retried without a temporary file and succeeded.
- Other failed development attempts: NONE.
- Full local unit suite: NOT RUN — explicitly prohibited by the active order.
- Full local integration suite and PostgreSQL: NOT RUN — explicitly prohibited by the active order.
- Local E2E, browser, Docker/Compose, and HPC suites: NOT RUN — explicitly prohibited by the active order.
- Real upstream provider/tool smoke: NOT RUN — explicitly prohibited; verifier calls were numeric-loopback-only with a dummy key.

## GitHub CI / required checks

Check state observed for implementation head
`3a427e9abd039c22e9309c4e767f772369f7496a` after exact 30-second wait
blocks:

- `Unit, lint, and migration head`: SUCCESS — 1m40s.
- `Analyze (javascript-typescript)`: SUCCESS — 47s.
- `Analyze Python`: SUCCESS — 1m07s.
- `Analyze (python)`: SUCCESS — 1m48s.
- `PostgreSQL integration tests`: SUCCESS — 2m11s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m13s.
- `Playwright browser smoke`: SUCCESS — 1m20s.
- `Docker Compose smoke`: SUCCESS — 53s.
- `Documentation hygiene`: SUCCESS — 5s.
- `CodeQL`: SUCCESS — 3s.

## Documentation impact

Documentation updated: docs/accounting.md, docs/codex-compatibility.md, docs/provider-forwarding-contract.md, docs/responses-compatibility.md, docs/security-model.md

- The contracts now record the exact five-gate/type/canonical-size boundary,
  copy-before-drop behavior, zero model-input accounting, complete downstream
  absence, and unchanged strict denial outside that boundary.
- No configuration, schema, model, migration, repository, pricing, admin,
  template, dependency, fixture, verifier, CI, deployment, README, or prior
  OAP history changed.

## Security and privacy notes

- Internal chat metadata can contain turn identity and executed-tool details or
  arguments. SLAIF validates only the outer null/mapping type and canonical
  size, never interprets nested contents, and deletes the complete field.
- The exception requires every Codex gate and an exact history type. It does
  not authorize nested values, ordinary requests, additional tools, hosted
  tools, unknown types, MCP/connectors, provider authority, or any other
  endpoint.
- Tests and diagnostics retain only aggregate byte/token comparisons and fixed
  safe errors. No raw body, metadata, prompt, message, tool argument, response,
  key, identifier, ciphertext, or subprocess payload was persisted or printed.
- No real provider, production service, external tool, email, database, or
  deployment action ran locally. No `.local-provider-catalog/` artifact was
  staged or committed.

## Human/strategic review notes

- The exact next mismatch is safe code
  `responses_codex_tool_roundtrip_invalid` at `input[8].id`. A future order
  must independently reconcile the pinned source and privacy/accounting
  contracts before deciding whether any bounded treatment is appropriate.
  This turn makes no architecture, compatibility, or risk-acceptance decision
  about that identifier.
- The approved internal-chat-metadata drop is independently green and stays
  absent from all downstream and evidence surfaces. Strategic review can
  isolate its next decision to the newly exposed exact tool-roundtrip mismatch.
- PR #234 must not be merged while this criterion remains blocked unless the
  strategic model/human explicitly resolves it in a subsequent order. The
  coding agent did not merge and did not enable auto-merge.

## Final safety statement

This turn amended only PR #234, published a truthful blocked result, preserved
the immutable report protocol, and performed no merge or auto-merge action.
Coding-agent `OK` after remote SELF verification means only that this execution
turn, immutable report, and claimed GitHub state are published; it does not
mean the work is accepted.
