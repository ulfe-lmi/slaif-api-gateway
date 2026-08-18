# OAP Coding-Agent Report — 009-c

## Work order

- Identifier: `009-c`
- Work-order file: `oap/orders/009-c-fix-compact-exposure-and-success-ordering.md`
- Numeric objective: `009`
- PR mode: `AMENDED_EXISTING_PR`

## Status

BLOCKED

## Executive summary

The in-scope 009-c repair is published on the existing objective PR. Gated
Codex V1 compact admission now uses the validated route maximum as its
effective/requested output exposure while keeping `max_output_tokens` absent
upstream. Unary compact success now occurs in the required order: finalized
accounting, committed HMAC replay reference, success metric, then JSON success.
The Codex compact response envelope and usage are strict, and the verifier now
passes its captured body through the real compact policy and route-limit code.
Focused local tests, contracts, quality checks, fixture integrity, and all ten
implementation-head GitHub checks pass.

The turn is blocked by the exact new verifier proof. The captured Codex 0.147.0
compact body fails the existing strict policy with safe code
`responses_tool_invalid_shape` at
`input[0].tools[0].tools[0].description`: the pinned client sends an 18,137-byte
description while `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES` is 4,096.
No raw description or request body was printed or persisted. Expanding this
security boundary was not an authorized 009-c finding, and the work order
explicitly requires `BLOCKED` rather than weakening the contract when the exact
captured body cannot pass. A strategic decision is required about whether and
how a future continuation may qualify this pinned declaration shape.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `234`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`
- PR title: `[OAP 009] Bound Codex context, cache, compaction, and accounting`
- PR state at report time: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/009-codex-context-output-cache-compaction-accounting`
- Starting remote/report SHA: `0b4b24d3ff7465210be2db9ba43e8dfb99a1c5b7`
- Remote `main`: `635f20f6ca9efdc66d13f56bacb2193d00340de3`
- Implementation head SHA: `ff1fe09d29764eb0284f9be0d7755965989a994a`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Implementation commit pushed before the report commit:
  `ff1fe09d29764eb0284f9be0d7755965989a994a`
  (`OAP 009-c: harden compact exposure and success ordering`)
- Report commit first parent: same as Implementation head SHA
- Objective-009 PR count: exactly one, PR #234
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Changes made

- Added an explicit `reserve_route_max_output` route-limit mode. The gated V1
  compact handler selects `codex_limits.max_output_tokens` for context checks,
  operator ceilings, rate/quota admission, pricing, and safe policy evidence,
  but its canonical/upstream body still omits `max_output_tokens`. The normal
  Codex create default, ordinary Responses default, and non-Codex compact path
  are unchanged.
- Moved normal compact success metrics after successful replay-reference HMAC
  persistence. A persistence failure remains charged after accounting,
  releases operational concurrency through the exception path, returns the
  existing safe 500-class OpenAI-compatible error, and emits neither the normal
  success metric nor a normal compact response.
- Restricted Codex compact provider responses to required `output` and `usage`
  plus optional validated `id`, `object`, and `created_at`. Usage must contain
  bounded non-boolean integer input/output/total counts with exact totals,
  supported bounded cache/cache-write/reasoning details, and agreement with the
  parsed provider usage. Unknown dimensions, malformed metadata, extra output,
  and extra/plaintext item fields fail closed with fixed safe errors.
- Made the loopback verifier feed the exact in-memory compact request into
  `ResponsesRequestPolicy.apply_compact` and `apply_codex_route_limits`. A
  successful run would add only the fixed boolean
  `GATEWAY_COMPACT_POLICY_ACCEPTED=true`; no body output or persistence was
  added. This new proof exposed the strict-description blocker above.
- Added focused route-exposure, response-envelope, safe failure, verifier, and
  full mocked handler-timeline tests. Updated only the five authorized contract
  documents whose exposure, response, or success-boundary wording changed.

## Files changed

The implementation commit changes exactly these 12 order-authorized paths:

- `app/slaif_gateway/services/responses_gateway.py`
- `app/slaif_gateway/services/responses_request_policy.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/009-c-fix-compact-exposure-and-success-ordering.md`
- `scripts/verify_codex_context_compaction.py`
- `tests/unit/test_codex_context_accounting.py`
- `tests/unit/test_responses_codex_compaction.py`

The final report-publication commit adds only
`oap/reports/009-c-fix-compact-exposure-and-success-ordering.md`.

## Acceptance-criteria evidence

### Criterion 1 — route-maximum compact exposure without upstream field

- Result: PASSED locally and in GitHub CI.
- Evidence: focused unit and full mocked handler tests prove effective/requested
  exposure 128,000 for the qualification route, context rejection at 922,001
  estimated input tokens, and absence of `max_output_tokens` from both policy
  and provider bodies. Existing ordinary-path assertions remain green.

### Criterion 2 — accounting, HMAC, metric, response ordering

- Result: PASSED locally and in GitHub CI.
- Evidence: the success timeline is exactly
  `accounting -> hmac -> metrics -> release:false`. The injected persistence
  failure timeline is exactly
  `accounting -> hmac-failed -> release:true`; it raises status 500/code
  `responses_codex_replay_persistence_failed`, records no success metric, and
  echoes neither the opaque item ID nor ciphertext.

### Criterion 3 — exact compact response envelope and privacy

- Result: PASSED locally and in GitHub CI.
- Evidence: minimal `output`+`usage` and optional safe metadata pass. Unknown
  top-level fields, bad ID/object/timestamp, missing/malformed/contradictory or
  unknown usage, zero/multiple output items, empty ciphertext, and plaintext or
  extra item fields fail with fixed safe errors. Canary values do not enter
  error strings.

### Criterion 4 — exact pinned CLI body passes gateway policy and limits

- Result: BLOCKED.
- Evidence: the exact command still produces three loopback requests, but the
  newly required real policy call fails safely before the verifier can declare
  success:

  ```text
  RESULT=ERROR
  ERROR=Captured V1 compact request failed gateway policy.
  ```

  Two bounded in-memory diagnostic reruns exposed no request content. They
  reported only the safe policy code/parameter/type and then the byte count:

  ```text
  SAFE_POLICY_CODE=responses_tool_invalid_shape
  SAFE_POLICY_PARAM=input[0].tools[0].tools[0].description
  SAFE_VALUE_TYPE=str
  SAFE_DESCRIPTION_BYTES=18137
  SAFE_CONFIGURED_MAX=4096
  ```

  Raising or bypassing the bound would weaken an existing security contract and
  was therefore not attempted. The required fixed success boolean was not
  falsely emitted.

### Criterion 5 — focused checks, paths, fixture, and documentation

- Result: PASSED except for the exact pinned proof in Criterion 4.
- Evidence: 51 focused tests and 17 OAP/documentation contract tests pass;
  scoped Ruff/compile, diff hygiene, pointer/order/report topology checks, and
  exact implementation paths pass. The frozen fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.

### Criterion 6 — implementation-head GitHub checks

- Result: PASSED.
- Evidence: all ten checks on implementation head
  `ff1fe09d29764eb0284f9be0d7755965989a994a` completed successfully. Fresh
  report-head checks may run after SELF publication and are not misreported as
  implementation-head evidence.

### Criterion 7 — one PR, no merge, immutable report topology

- Result: PASSED for coding-agent-controlled behavior.
- Evidence: exactly one objective-009 PR exists; it is open and has no
  auto-merge request. No merge was performed. This report commit is required to
  contain only this report and have the literal implementation head as first
  parent; remote topology is verified before the FIFO response.

## Local verification

- `pytest -q tests/unit/test_codex_context_accounting.py tests/unit/test_responses_codex_compaction.py`: FAILED BEFORE COLLECTION — system Python lacked `structlog`; no test executed. Verification then used the repository `.venv`.
- `.venv/bin/python -m pytest -q tests/unit/test_codex_context_accounting.py tests/unit/test_responses_codex_compaction.py`: PASSED — 51 tests, zero failures/errors/skips; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`: PASSED — 17 tests, zero failures/errors/skips.
- `.venv/bin/ruff check app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/responses_request_policy.py scripts/verify_codex_context_compaction.py tests/unit/test_codex_context_accounting.py tests/unit/test_responses_codex_compaction.py`: PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/responses_request_policy.py scripts/verify_codex_context_compaction.py tests/unit/test_codex_context_accounting.py tests/unit/test_responses_codex_compaction.py`: PASSED.
- `git diff --check`: PASSED.
- `test "$(cat oap/active)" = "009-c"`, exact single-order/no-preexisting-report topology checks, and exact 12-path staged check: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact approved digest above.
- `.venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: BLOCKED — exact safe failure shown in Criterion 4; no raw payload printed or persisted and no real provider called.
- Two diagnostic loopback reruns used an in-memory helper replacement only to emit the safe code/parameter/type/count above: BLOCKED consistently; repository files were not changed by the diagnostic and no request content was exposed.
- Full local unit suite: NOT RUN — explicitly prohibited by the active order.
- Full local integration suite and PostgreSQL: NOT RUN — explicitly prohibited by the active order.
- Local E2E, browser, Docker/Compose, and HPC suites: NOT RUN — explicitly prohibited by the active order.
- Real upstream provider/tool smoke: NOT RUN — explicitly prohibited; all verifier calls were numeric-loopback-only with a dummy key.

## GitHub CI / required checks

Check state observed for implementation head
`ff1fe09d29764eb0284f9be0d7755965989a994a` after three exact 30-second wait
blocks:

- `Unit, lint, and migration head`: SUCCESS — 2m07s.
- `Analyze (javascript-typescript)`: SUCCESS — 40s.
- `Analyze Python`: SUCCESS — 1m08s.
- `Analyze (python)`: SUCCESS — 1m44s.
- `PostgreSQL integration tests`: SUCCESS — 2m09s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m25s.
- `Playwright browser smoke`: SUCCESS — 1m21s.
- `Docker Compose smoke`: SUCCESS — 52s.
- `Documentation hygiene`: SUCCESS — 7s.
- `CodeQL`: SUCCESS — 3s.

## Documentation impact

- `docs/accounting.md` distinguishes route-default ordinary Codex admission
  from the route-maximum/no-field V1 compact exception and documents the
  post-HMAC success-metric boundary.
- `docs/codex-compatibility.md` documents maximum compact exposure, strict
  response metadata, persistence ordering, and the verifier's in-memory gateway
  policy proof.
- `docs/provider-forwarding-contract.md`, `docs/responses-compatibility.md`, and
  `docs/security-model.md` align forwarding, response allowlist/usage, charged
  failure, metrics, and privacy behavior.
- No README, schema, migration, model, repository, pricing arithmetic,
  dependency, fixture, CI, or deployment document changed.

## Security and privacy notes

- No real provider, production service, external tool, email, PostgreSQL, or
  deployment action ran locally.
- The loopback verifier used a dummy key and private temporary directories.
  Captured bodies remained transient in memory and were deleted; requests,
  responses, headers, IDs, ciphertext, cache keys, prompts, tool payloads,
  subprocess output, and descriptions were neither printed nor persisted.
- Only fixed safe error categories and bounded type/byte-count diagnostics were
  emitted. The 18,137-byte description itself was never exposed.
- No `.local-provider-catalog/` artifact was staged or committed.
- The existing per-description security bound was preserved; no gate, schema,
  context, quota, or response validation was weakened to obtain a pass.

## Human/strategic review notes

- A future continuation must deliberately decide whether the pinned 18,137-byte
  client-tool description can be admitted under a reviewed Codex-specific
  bound/profile or whether the pinned declaration must be normalized elsewhere.
  This report makes no architecture or risk-acceptance decision.
- The other 009-c defects are repaired and have green local/GitHub evidence, so
  the strategic review can isolate its continuation decision to the exact
  captured declaration-policy mismatch.
- PR #234 must not be merged while the active criterion remains blocked unless
  the strategic model/human explicitly resolves the risk under a subsequent
  work order. The coding agent did not merge and did not enable auto-merge.

## Final safety statement

This turn amended only PR #234, published a truthful blocked result, preserved
the immutable report protocol, and performed no merge or auto-merge action.
Coding-agent `OK` after remote SELF verification means only that this execution
turn, immutable report, and claimed GitHub state are published; it does not mean
the work is accepted.
