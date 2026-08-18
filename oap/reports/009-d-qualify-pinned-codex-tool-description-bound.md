# OAP Coding-Agent Report — 009-d

## Work order

- Identifier: `009-d`
- Work-order file: `oap/orders/009-d-qualify-pinned-codex-tool-description-bound.md`
- Numeric objective: `009`
- PR mode: `AMENDED_EXISTING_PR`

## Status

BLOCKED

## Executive summary

The reviewed 009-d description-bound repair is implemented and published on
the existing objective PR. Only exact child function/custom tools inside the
fully gated pinned Codex `additional_tools` taxonomy receive the fixed
20,000-byte per-description cap. Namespace and ordinary tool descriptions keep
their 4,096-byte settings limits, all descriptions retain the unchanged
32,768-byte aggregate cap, every admitted byte is conservatively metered, and
existing recursive provider/hosted/MCP denial remains active. Focused local
tests, contracts, quality checks, fixture integrity, and all ten
implementation-head GitHub checks pass.

The unchanged exact Codex 0.147.0 verifier remains blocked after the authorized
18,137-byte description is admitted. The next safe policy rejection is
`responses_codex_client_tools_provider_authority_not_supported` at
`input[0].tools[0].tools[2]`, the exact pinned `request_user_input` declaration.
No request/tool content was printed or persisted. The order explicitly forbids
weakening authority checks and requires `BLOCKED` when the unchanged verifier
still cannot pass, so no further policy widening was attempted. A strategic
continuation must independently review this exact authority-detector mismatch.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `234`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`
- PR title: `[OAP 009] Bound Codex context, cache, compaction, and accounting`
- PR state at report time: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/009-codex-context-output-cache-compaction-accounting`
- Starting remote/report SHA: `da375ff9488eeb1cbaaff490c2eef9f539e49fa3`
- Remote `main`: `635f20f6ca9efdc66d13f56bacb2193d00340de3`
- Implementation head SHA: `dfcdbbba29cf0f0a04332888ce676cf40ed9ab68`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Implementation commit pushed before the report commit:
  `dfcdbbba29cf0f0a04332888ce676cf40ed9ab68`
  (`OAP 009-d: qualify pinned Codex description bound`)
- Report commit first parent: same as Implementation head SHA
- Objective-009 PR count: exactly one, PR #234
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Changes made

- Added fixed `_CODEX_MAX_CLIENT_TOOL_DESCRIPTION_BYTES = 20_000`.
- Added one narrow optional description bound to the existing local
  function/custom validators. It is supplied only by
  `_validate_codex_additional_tools_item` after exact namespace/name/type/
  placement and recursive authority validation; ordinary top-level tool calls
  omit it and continue to use their settings-based limits.
- Preserved the 4,096-byte namespace cap, ordinary function cap, and ordinary
  custom cap. No configuration default or schema was changed.
- Preserved the 32,768-byte total description cap, declaration/schema/grammar/
  depth/property bounds, exact taxonomy, canonicalization, and recursive
  hosted/MCP/provider-authority denials.
- Added positive boundaries for both custom and function children at 18,137 and
  20,000 bytes; safe rejection at 20,001; aggregate rejection above 32,768;
  ordinary function/custom and Codex namespace rejection at 4,097; large-
  description recursive server/MCP/connector denials; exact byte metering and
  safe evidence privacy; and compact-policy coverage for the pinned 18,137-byte
  declaration.
- Updated only four authorized contracts to distinguish the pinned child cap
  from ordinary/namespace and aggregate bounds.
- Left `scripts/verify_codex_context_compaction.py` unchanged and ran its exact
  pinned command once. A bounded diagnostic used an in-memory helper replacement
  only to expose the safe rejection code/parameter above; it changed no file and
  printed no captured content.

## Files changed

The implementation commit changes exactly these nine order-authorized paths:

- `app/slaif_gateway/services/responses_request_policy.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/009-d-qualify-pinned-codex-tool-description-bound.md`
- `tests/unit/test_responses_codex_client_tools.py`
- `tests/unit/test_responses_codex_compaction.py`

The final report-publication commit adds only
`oap/reports/009-d-qualify-pinned-codex-tool-description-bound.md`.

## Acceptance-criteria evidence

### Criterion 1 — pinned and reviewed child-description boundaries

- Result: PASSED locally and in GitHub CI.
- Evidence: both exact custom and function children pass at 18,137 and 20,000
  bytes under the full Codex gates. Both reject 20,001 with fixed code
  `responses_tool_invalid_shape` and the exact child-description parameter.
  Two individually valid 17,000-byte descriptions plus the remaining taxonomy
  descriptions exceed 32,768 and fail with
  `responses_codex_client_tools_too_large`.

### Criterion 2 — ordinary and namespace caps unchanged

- Result: PASSED locally and in GitHub CI.
- Evidence: ordinary function and custom requests each reject a 4,097-byte
  description at `tools[0].description`; a fully gated Codex namespace also
  rejects 4,097 at `input[0].tools[0].description`. The settings/defaults were
  not edited, and the optional 20,000 bound has exactly one caller: the child
  validator inside the exact `additional_tools` path.

### Criterion 3 — authority, validation, metering, and privacy

- Result: PASSED locally and in GitHub CI for the authorized boundary.
- Evidence: large descriptions do not bypass recursive server URL, nested MCP,
  or connector-ID rejection. Existing taxonomy, field, name/type, schema,
  grammar, depth, property, aggregate, and canonicalization tests remain green.
  The metering test proves the exact 18,137-byte ASCII increase appears in
  `estimated_non_message_input_bytes` and the conservative token estimate,
  while safe evidence and error messages omit the canary description.

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
  SAFE_POLICY_CODE=responses_codex_client_tools_provider_authority_not_supported
  SAFE_POLICY_PARAM=input[0].tools[0].tools[2]
  ```

  The verifier did not emit `RESULT=OK`, `REQUEST_COUNT=3`, or
  `GATEWAY_COMPACT_POLICY_ACCEPTED=true`, and this report does not claim that it
  did. The exact pinned tool is `request_user_input`; no declaration value,
  schema, description, raw request, or response was output or persisted. The
  existing authority detector was not weakened.

### Criterion 5 — focused checks, paths, fixture, and GitHub CI

- Result: PASSED except for the unchanged verifier in Criterion 4.
- Evidence: 97 focused tests and 17 OAP/documentation contract tests pass;
  scoped Ruff/compile, diff hygiene, exact pointer/order/report topology, and
  exact nine-path staging pass. The fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
  All ten implementation-head GitHub checks completed successfully. Fresh
  report-head checks may run after SELF publication and are not represented as
  implementation-head evidence.

### Criterion 6 — one PR, no merge, immutable report topology

- Result: PASSED for coding-agent-controlled behavior.
- Evidence: exactly one objective-009 PR exists, remains open, and has no
  auto-merge request. No merge was performed. This report commit is required to
  change only this report and have the literal implementation SHA as first
  parent; remote topology is verified before the FIFO response.

## Local verification

- `.venv/bin/ruff check app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py`: PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py`: PASSED.
- `.venv/bin/python -m pytest -q tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py`: PASSED — 97 tests, zero failures/errors/skips; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`: PASSED — 17 tests, zero failures/errors/skips.
- `git diff --check`: PASSED.
- `test "$(cat oap/active)" = "009-d"`, exact single-order/no-preexisting-report topology checks, and exact nine-path staged check: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact approved digest above.
- `/usr/bin/codex --version`: PASSED — `codex-cli 0.147.0`.
- `git -C /tmp/slaif-oap005-codex-source-YSOVKH rev-parse HEAD` and `git describe --tags --exact-match HEAD`: PASSED — `be6e8eac029b183056b7e4402879f15d2c85f61b`, `rust-v0.147.0`.
- `.venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: BLOCKED — exact safe output shown in Criterion 4; the verifier file was unchanged, no raw payload was printed/persisted, and no real provider was called.
- One diagnostic loopback rerun used an in-memory helper replacement only to emit the safe code/parameter shown above: BLOCKED consistently; no repository file or captured content was written.
- Full local unit suite: NOT RUN — explicitly prohibited by the active order.
- Full local integration suite and PostgreSQL: NOT RUN — explicitly prohibited by the active order.
- Local E2E, browser, Docker/Compose, and HPC suites: NOT RUN — explicitly prohibited by the active order.
- Real upstream provider/tool smoke: NOT RUN — explicitly prohibited; both verifier calls were numeric-loopback-only with a dummy key.

## GitHub CI / required checks

Check state observed for implementation head
`dfcdbbba29cf0f0a04332888ce676cf40ed9ab68` after four exact 30-second wait
blocks:

- `Unit, lint, and migration head`: SUCCESS — 2m00s.
- `Analyze (javascript-typescript)`: SUCCESS — 45s.
- `Analyze Python`: SUCCESS — 1m10s.
- `Analyze (python)`: SUCCESS — 1m28s.
- `PostgreSQL integration tests`: SUCCESS — 2m11s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m17s.
- `Playwright browser smoke`: SUCCESS — 1m14s.
- `Docker Compose smoke`: SUCCESS — 57s.
- `Documentation hygiene`: SUCCESS — 8s.
- `CodeQL`: SUCCESS — 1s.

## Documentation impact

- `docs/accounting.md` records complete conservative metering and the
  20,000/32,768 Codex-only versus 4,096 ordinary/namespace boundary.
- `docs/codex-compatibility.md` records the pinned 18,137-byte value, exact gate
  scope, fixed per-child and aggregate caps, and non-authoritative/transient
  description behavior.
- `docs/responses-compatibility.md` and `docs/security-model.md` align exact
  taxonomy, ordinary isolation, metering, privacy, and unchanged authority
  denials.
- No configuration, schema, model, migration, repository, pricing, admin,
  template, dependency, fixture, verifier, CI, deployment, README, or prior OAP
  history changed.

## Security and privacy notes

- The 20,000-byte cap is fixed and reachable only through the exact, fully gated
  Codex taxonomy. It is not configurable and does not apply to namespaces or
  ordinary tools.
- All existing recursive provider/hosted/MCP checks remain active. The real
  verifier's next authority rejection was preserved rather than bypassed.
- Descriptions remain transient provider/model input. Tests and diagnostics
  retain only aggregate byte/token evidence and fixed safe errors; no raw body,
  description, schema, prompt, response, key, ID, ciphertext, or subprocess
  output was persisted or printed.
- No real provider, production service, external tool, email, database, or
  deployment action ran locally. No `.local-provider-catalog/` artifact was
  staged or committed.

## Human/strategic review notes

- A future order must identify why the exact pinned `request_user_input`
  declaration triggers recursive authority rejection and decide whether a
  shape-specific safe distinction exists. This turn makes no such architecture
  or risk-acceptance decision.
- The approved description-bound change is independently green and retains all
  ordinary/aggregate/authority limits. Strategic review can isolate its next
  decision to the exact `request_user_input` declaration mismatch.
- PR #234 must not be merged while this criterion remains blocked unless the
  strategic model/human explicitly resolves it in a subsequent order. The
  coding agent did not merge and did not enable auto-merge.

## Final safety statement

This turn amended only PR #234, published a truthful blocked result, preserved
the immutable report protocol, and performed no merge or auto-merge action.
Coding-agent `OK` after remote SELF verification means only that this execution
turn, immutable report, and claimed GitHub state are published; it does not mean
the work is accepted.
