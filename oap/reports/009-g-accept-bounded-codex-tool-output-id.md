# OAP Coding-Agent Report — 009-g

## Work order

- Identifier: `009-g`
- Work-order file: `oap/orders/009-g-accept-bounded-codex-tool-output-id.md`
- Numeric objective: `009`
- PR mode: `AMENDED_EXISTING_PR`

## Status

COMPLETE

## Executive summary

The bounded 009-g Codex tool-output item-ID repair is implemented and published
on the existing objective PR. Fully gated Codex `function_call_output` and
`custom_tool_call_output` items may now carry the optional `id` defined by
pinned Codex 0.147.0. A present value passes the existing 128-character,
ASCII-safe, non-secret Codex item-ID validator, is preserved in the canonical
provider/model history, contributes its complete canonical bytes to input-token
and cost estimation, and participates in the existing request-wide item-ID
uniqueness check. Absent IDs retain the previous canonical shape.

The output ID grants no authority and creates no separate replay/HMAC
reference. Immediate call/output adjacency, exact call/output type and
`call_id`, declared taxonomy, call/output uniqueness, HMAC-owned call
reference, and complete call/output set equality remain mandatory. Ordinary
non-Codex outputs continue to reject `id`; malformed, duplicate, unknown,
orphan, reordered, mismatched, and cross-type shapes remain fail-closed. Raw
output IDs and outputs do not enter safe evidence or persistence.

All 143 focused tests, all 17 OAP/documentation contract tests, scoped quality
checks, fixture/transcript/path checks, and all ten implementation-head GitHub
checks passed. The unchanged exact Codex 0.147.0 verifier completed the required
three-request V1 compaction loop with gateway policy accepted, loopback-only
execution, and no raw payload persistence. No broad local suite or real
provider/tool call ran.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `234`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`
- PR title: `[OAP 009] Bound Codex context, cache, compaction, and accounting`
- PR state at report time: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/009-codex-context-output-cache-compaction-accounting`
- Starting remote/report SHA: `77dd6a3e0ad9a73b2edd435cd8c505feb330eee5`
- Remote `main`: `635f20f6ca9efdc66d13f56bacb2193d00340de3`
- Implementation head SHA: `25e6e4090bcbdab652b073bbe3056867660ba6d7`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Implementation commit pushed before the report commit:
  `25e6e4090bcbdab652b073bbe3056867660ba6d7`
  (`OAP 009-g: accept bounded Codex tool output IDs`)
- Report commit first parent: same as Implementation head SHA
- Objective-009 PR count: exactly one, PR #234
- Created a new PR this turn: NO
- Amended existing PR this turn: YES
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Pinned source and boundary reconciliation

- `/usr/bin/codex --version` returned `codex-cli 0.147.0`; the installed binary
  SHA-256 is
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`.
- Pinned source checkout `/tmp/slaif-oap005-codex-source-YSOVKH` remains at
  `be6e8eac029b183056b7e4402879f15d2c85f61b`, exact tag
  `rust-v0.147.0`, detached and clean.
- `codex-rs/protocol/src/models.rs` independently confirms optional
  `ResponseItemId` on both `FunctionCallOutput` and `CustomToolCallOutput`, and
  includes both variants in the common item-ID accessors.
- The gateway's existing item-ID helper accepts only non-empty ASCII matching
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`, rejects secret-like/URL-shaped values,
  and uses fixed safe errors without value echo.
- The pre-change tool-output validator used ordinary output field sets, which
  made the optional pinned ID the exact unknown field reported by 009-f. The
  existing request-wide uniqueness scan already covered every canonical string
  `id`, while replay candidate extraction already intentionally covered calls,
  reasoning, and compaction only—not outputs.

## Changes made

- Added separate exact Codex function/custom output field sets containing only
  the previous `type`, `call_id`, and `output` fields plus optional `id`.
- Reused the existing Codex item-ID helper for every present output ID. Null,
  non-string, empty, invalid-character, oversized, URL-like, or secret-like
  values remain rejected by that bounded validator.
- Inserts a validated output ID into the canonical output dictionary before
  canonical JSON material-byte calculation. The existing item-ID estimator
  also includes the canonical `{"id": ...}` bytes, preserving conservative
  admission/cost behavior.
- Left the ordinary function/custom output field sets unchanged, so ordinary
  requests still reject `id` at the exact field.
- Left `_validate_codex_tool_roundtrip_items` and replay candidate/HMAC
  extraction unchanged. Canonical output IDs naturally participate in the
  existing request-wide uniqueness set but do not create a candidate or
  authority record.
- Added focused coverage for the pinned 41-byte custom output ID, a valid
  function output ID, optional absence, all required malformed/unknown cases,
  duplicate output IDs, collisions with call/reasoning/message IDs, exact
  canonical and non-message byte changes, exact token estimation, unchanged
  HMAC candidates, compact reconstruction, and retained negative linkage and
  ordinary behavior.
- Updated the five authorized compatibility, accounting, forwarding, and
  security contracts.
- Left `scripts/verify_codex_context_compaction.py` and the approved fixture
  unchanged.

## Files changed

The implementation commit changes exactly these eleven order-authorized paths:

- `app/slaif_gateway/services/responses_request_policy.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/009-g-accept-bounded-codex-tool-output-id.md`
- `tests/unit/test_responses_codex_compaction.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`
- `tests/unit/test_responses_codex_streaming_tools.py`

The final report-publication commit adds only
`oap/reports/009-g-accept-bounded-codex-tool-output-id.md`.

## Acceptance-criteria evidence

### Criterion 1 — bounded canonical output IDs and global uniqueness

- Result: PASSED locally, in the unchanged verifier, and in GitHub CI.
- Evidence: focused tests preserve a pinned 41-byte/ASCII custom output ID and
  a valid function output ID, while absence preserves the old canonical shape.
  Raw canonical material increases by exactly the output item's canonical JSON
  delta; non-message bytes increase by exactly canonical `{"id": ...}` bytes;
  the resulting token estimates equal the policy's exact byte-to-token formula.
  Duplicate output IDs and collision with call, reasoning, or message IDs fail
  at the colliding output `input[N].id`.

### Criterion 2 — immediate HMAC-owned linkage remains authoritative

- Result: PASSED locally, in the unchanged verifier, and in GitHub CI.
- Evidence: orphan, reordered, unknown-tool, mismatched call ID, and cross-type
  call/output cases remain denied with
  `responses_codex_tool_roundtrip_invalid`, including when the output has a
  valid ID. Replay/HMAC candidate tuples are byte-for-byte identical with and
  without the output ID and contain only the existing call item ID and linkage;
  no output-ID candidate or reference is created.

### Criterion 3 — malformed/unknown/ordinary denials and privacy

- Result: PASSED locally and in GitHub CI.
- Evidence: non-string, empty, invalid-character, and 129-character IDs fail at
  the exact output field through the fixed safe Codex ID error. Extra `name`,
  `status`, or `metadata` fields remain denied. Ordinary function and custom
  outputs with `id` retain their distinct ordinary safe error codes. Tests
  prove private output canaries and output IDs do not enter safe messages,
  stringified errors, aggregate admission evidence, or replay candidates.

### Criterion 4 — unchanged exact Codex 0.147.0 verifier

- Result: PASSED.
- Evidence: the exact required command ran once against numeric loopback and
  emitted only:

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
  GATEWAY_COMPACT_POLICY_ACCEPTED=true
  POST_COMPACT_CONTINUATION_SEEN=true
  CONTENT_ENCODING_ABSENT=true
  LOOPBACK_ONLY=true
  RAW_PAYLOADS_PERSISTED=false
  ```

  No diagnostic rerun was needed. No raw input item, output ID, message,
  metadata, body, tool declaration, request, response, or subprocess payload
  was printed or persisted, and no real provider was called.

### Criterion 5 — focused checks, paths, fixture, and GitHub CI

- Result: PASSED.
- Evidence: 143 focused tests and 17 OAP/documentation contract tests pass;
  scoped Ruff/compile, diff hygiene, exact pointer/order/report topology, exact
  eleven-path staging, prior 009 SELF topology, and fixture integrity pass. The
  fixture SHA-256 remains
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

- `.venv/bin/python -m pytest -q tests/unit/test_responses_codex_compaction.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py`: PASSED — 143 tests (54 + 25 + 64), zero failures/errors/skips; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`: PASSED — 17 tests, zero failures/errors/skips.
- `.venv/bin/ruff check app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_compaction.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py`: PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway/services/responses_request_policy.py tests/unit/test_responses_codex_compaction.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py`: PASSED.
- `git diff --check`: PASSED.
- Exact `oap/active=009-g`, one matching order, no preexisting report, prior
  objective-009 report-only SELF parent/path topology, and exact eleven-path
  implementation staging checks: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact approved digest above.
- `/usr/bin/codex --version`: PASSED — `codex-cli 0.147.0`.
- `git -C /tmp/slaif-oap005-codex-source-YSOVKH rev-parse HEAD` and
  `git describe --tags --exact-match HEAD`: PASSED — pinned commit/tag above.
- `.venv/bin/python scripts/verify_codex_context_compaction.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: PASSED — exact safe output shown in Criterion 4; verifier unchanged, numeric-loopback-only, dummy key, no raw persistence/output, and no real provider call.
- Failed development attempt: one read-only topology shell wrapper failed
  because Markdown backticks inside a `sed` pattern were interpreted as shell
  command substitution, producing a command-not-found and invalid-reference
  error. It changed, staged, and committed nothing. The same checks were
  immediately retried with a backtick-free fixed-SHA extractor and passed.
- Other failed development attempts: NONE.
- Full local unit suite: NOT RUN — explicitly prohibited by the active order.
- Full local integration suite and PostgreSQL: NOT RUN — explicitly prohibited by the active order.
- Local E2E, browser, Docker/Compose, and HPC suites: NOT RUN — explicitly prohibited by the active order.
- Real upstream provider/tool smoke: NOT RUN — explicitly prohibited; the
  verifier was numeric-loopback-only with a dummy key.

## GitHub CI / required checks

Check state observed for implementation head
`25e6e4090bcbdab652b073bbe3056867660ba6d7` after exact 30-second wait
blocks:

- `Unit, lint, and migration head`: SUCCESS — 2m00s.
- `Analyze (javascript-typescript)`: SUCCESS — 41s.
- `Analyze Python`: SUCCESS — 1m11s.
- `Analyze (python)`: SUCCESS — 1m14s.
- `PostgreSQL integration tests`: SUCCESS — 2m27s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m19s.
- `Playwright browser smoke`: SUCCESS — 1m16s.
- `Docker Compose smoke`: SUCCESS — 58s.
- `Documentation hygiene`: SUCCESS — 5s.
- `CodeQL`: SUCCESS — 3s.
- All required checks green for the implementation head at report drafting: YES.
- The report-only commit may trigger fresh checks; the strategic model must
  verify the SELF commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: NONE.
- `sudo`-level setup performed: NONE.
- Durable setup changes committed/documented: NONE.

## Documentation impact

Documentation updated: docs/accounting.md, docs/codex-compatibility.md, docs/provider-forwarding-contract.md, docs/responses-compatibility.md, docs/security-model.md

- The contracts now record the exact optional-ID gate, bounded validation,
  canonical/provider preservation, complete byte/token estimation,
  request-wide uniqueness, immediate HMAC-owned linkage, no separate output-ID
  authority/reference, ordinary rejection, and privacy boundary.
- No configuration, schema, model, migration, repository, pricing, admin,
  template, dependency, fixture, verifier, CI, deployment, README, or prior
  OAP history changed.

## Safety and scope confirmations

- Unrelated files changed: NO.
- Production secrets accessed: NO.
- Production systems accessed: NO.
- Real provider or side-effecting external tool called: NO.
- Required tests skipped/not run: NO for the order's focused verification;
  broad local suites were intentionally NOT RUN by explicit order.
- Scope deviation: NO.
- Extra PR created for the same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO; exact strategic
  bytes were committed unchanged.
- `.local-provider-catalog/` accessed, modified, staged, or committed: NO.
- Report-publication commit changes only this report file: YES, verified before
  the FIFO response.

## Security and privacy notes

- Output IDs are bounded non-secret opaque provider/model history. They grant
  no route, provider, tool, execution, replay, or ownership authority.
- The output remains authorized only through its immediately preceding exact
  call/type/`call_id`, declaration match, and existing HMAC-owned call
  reference. No output-ID database reference, HMAC, cache, or state path was
  added.
- Complete output-ID canonical bytes are conservatively metered; provider
  final usage/cost remains authoritative. Safe evidence exposes only aggregate
  byte/token/category data, never raw IDs or outputs.
- No prompt, completion, body, tool argument/result, output ID, gateway key,
  provider key, ciphertext, raw subprocess payload, or other prohibited content
  was printed, logged, persisted, or committed.

## Known limitations / blockers

- NONE within the active 009-g order. This result does not expand SLAIF beyond
  the documented partial client-side tool loop and opaque V1 compaction
  boundary, does not authorize hosted/provider tools, and is not a production
  or release claim.

## Recommended strategic follow-up

The 009-g implementation and exact verifier are green. The strategic model
must independently inspect the SELF commit, fresh report-head checks, complete
PR #234 diff, and all objective-009 reports before deciding acceptance or
merge. The coding agent makes no continuation or merge decision.

## Final safety statement

This turn amended only PR #234, published a truthful complete result, preserved
the immutable report protocol, and performed no merge or auto-merge action.
Coding-agent `OK` after remote SELF verification means only that this execution
turn, immutable report, and claimed GitHub state are published; it does not
mean the work is accepted.
