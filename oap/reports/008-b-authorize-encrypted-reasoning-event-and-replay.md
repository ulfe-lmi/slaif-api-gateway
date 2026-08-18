# OAP Coding-Agent Report — 008-b

## Work order

- Identifier: `008-b`
- Work-order file:
  `oap/orders/008-b-authorize-encrypted-reasoning-event-and-replay.md`
- Numeric objective: `008`
- PR mode: `AMENDED_EXISTING_PR`

## Status

BLOCKED

## Executive summary

The authorized 008-b implementation is complete and published on the existing
PR #233. It adds the exact gated encrypted-reasoning done event, pinned
`content=null` replay request shape, HMAC-only same-key replay references,
post-accounting persistence, strict tool/reasoning linkage, a single Alembic
successor, focused unit/PostgreSQL coverage, and the harmless isolated
three-request Codex verifier.

All objective-specific local verification passed: 343 focused unit tests, 17
OAP/documentation tests, one disposable PostgreSQL migration and repository
proof, scoped Ruff/compile/diff checks, one Alembic head, the unchanged frozen
fixture digest, and the exact manual Codex verifier.

GitHub CI exposed a mechanical scope blocker rather than an implementation
failure. The unit job passed 2,600 tests and failed five pre-existing tests that
hardcode the former `0012_conversation_references` head. The PostgreSQL job
passed 130 tests and failed one pre-existing integration assertion with the same
hardcoded head. All six required test-file edits are outside 008-b's explicit
allowed paths. Hiding the new head, changing migration history, or editing
out-of-scope files would violate the work order. A narrow continuation must
authorize those six expectation updates before CI can become green.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: `233`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/233`
- PR state at report time: `OPEN`
- PR title: `[OAP 008] Bind Codex encrypted replay to gateway keys`
- Base branch: `main`
- Head branch: `oap/008-codex-multiturn-reasoning-replay`
- Starting remote SHA: `96cbbcd9b8a40fa8a5f30a804f50fc0bb3607035`
- Implementation head SHA: `f8a67a12b494295c04a77bd67b3be6379147ed49`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `f8a67a12b494295c04a77bd67b3be6379147ed49` —
    `feat: bind Codex replay to HMAC references`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO
- Auto-merge enabled: NO

GitHub was independently reconciled before implementation and again before
push. At report drafting, PR #233 was the only PR found for the exact objective
branch, was non-draft/open against `main`, and its remote head was the literal
implementation SHA above. Remote `main` was
`064be428a58d9d1c0581d36d16a37853bb7d5952`.

## Changes made

- Added `codex_replay_references` as revision
  `0013_codex_replay_references`, the single successor to
  `0012_conversation_references`.
- Added exact ORM/migration/schema parity for restrictive key, usage-ledger,
  and route foreign keys; constrained replay kind; fixed-length item/call HMAC
  columns; HMAC version; safe provider/model/tool identity; timestamps; fixed
  24-hour expiry; uniqueness; and indexed key/digest/expiry lookup.
- Added a batch repository and service that use the existing versioned HMAC
  secret infrastructure with domain-separated item/call inputs, refuse missing
  historical key material, verify same-key ownership before route work, verify
  provider/route/model/tool compatibility before later side effects, and
  remove private database exception chains.
- Added default-off `codex_encrypted_reasoning_replay` key-template and route
  vocabulary with the request-envelope prerequisite and no default/calibration
  grant.
- Added exact replay request validation for bounded opaque encrypted reasoning,
  exact summary parts, required bounded ID, and the pinned client's exact
  optional `content=null`. Plaintext/non-null content, status, unknown fields,
  empty ciphertext, malformed summary, and per-item/request overflow fail
  closed.
- Added strict immediate call/output adjacency, unique item/call IDs, declared
  function or `functions.exec` identity, ordinary non-Codex output separation,
  and prohibition on combining client replay with provider-managed
  `previous_response_id` or conversation state.
- Added exact encrypted reasoning validation only on
  `response.output_item.done` with `type`, `id`, `summary`, and
  `encrypted_content`, under the new gate and per-item/per-stream caps. The raw
  upstream frame is forwarded unchanged; validator state retains only safe
  aggregate counts and transient linkage IDs.
- Added completion ordering: provider-completed ledger record, successful
  PostgreSQL accounting finalization, finalized-ledger recheck, HMAC-reference
  persistence/commit, then held `response.completed`. Persistence failure is a
  safe charged failure and suppresses normal completion. Missing usage,
  malformed/error events, and disconnects create no usable reference.
- Added focused unit/migration/PostgreSQL tests and an executable manual-only
  three-request verifier for pinned Codex CLI 0.147.0.
- Updated every named governance, database, accounting, forwarding, security,
  Codex, Responses, and compatibility contract. README was unchanged.
- Committed the strategic `oap/active=008-b` pointer and 008-b order bytes with
  the implementation. The 008-a order/report/history were unchanged.

## Acceptance evidence

### Criterion 1 — exact gated encrypted reasoning event and caps

- Result: SATISFIED for the implementation.
- Evidence: the event validator accepts encrypted reasoning only on the exact
  `response.output_item.done` four-field item when the relevant request/event
  gates are active. Per-item and cumulative encrypted-byte tests pass; unknown,
  status, plaintext content, wrong placement, empty, and oversized values fail.
  Tests prove the original frame remains unchanged and the private canary is
  absent from validator state and safe evidence.

### Criterion 2 — HMAC-only same-key/provider/route binding

- Result: SATISFIED for the implementation.
- Evidence: versioned domain-separated HMAC item/call digests, same-key indexed
  lookup, fixed expiry, safe tool identity, provider/route/model compatibility,
  cross-key/expired/name/route negatives, unavailable-version refusal, and
  retry idempotency pass unit and disposable-PostgreSQL tests.

### Criterion 3 — no content/identifier/digest exposure

- Result: SATISFIED for the implementation.
- Evidence: schema/model/migration contain no raw provider item/call ID or
  content columns. Candidate dataclasses are `repr=False` and carry only
  transient linkage IDs. Encrypted content, summaries, arguments, results,
  raw IDs, and HMAC digests do not enter ledger metadata, metrics, audits,
  exports, errors, or safe evidence. A canary test proves a failed digest lookup
  has no private exception cause or value.

### Criterion 4 — references only after usage and accounting

- Result: SATISFIED for the implementation.
- Evidence: tests prove `accounting:record -> accounting:finalize ->
  replay:persist -> client:completed`. Persistence rechecks a successful,
  finalized same-key/source-request ledger row. Persistence failure happens
  after charged accounting and suppresses completion; interruption paths never
  call replay persistence.

### Criterion 5 — exact replay order/linkage and state separation

- Result: SATISFIED for the implementation.
- Evidence: exact reasoning shape, unique IDs, immediate function/custom
  call-output adjacency, declarations, namespace/name matching, duplicate/
  orphan/reordered/mismatch negatives, ordinary non-Codex function-output
  behavior, and `previous_response_id`/conversation prohibition pass focused
  tests.

### Criterion 6 — harmless three-request Codex mock

- Result: SATISFIED.
- Evidence: pinned CLI/version/model/profile checks passed. Exactly three
  in-memory loopback requests replayed one opaque reasoning item and two linked
  `custom` tool pairs, then completed the assistant sequence. The only Code Mode
  sources were the two fixed safe `text(...)` calls. The verifier reported
  `LOOPBACK_ONLY=true` and `RAW_PAYLOADS_PERSISTED=false`; it exposed no raw
  request, ID, ciphertext, summary, argument, result, prompt, header, body,
  subprocess output, or assistant text.

### Criterion 7 — schema/focused tests/fixture

- Result: SATISFIED locally; broad GitHub migration-head expectations BLOCKED.
- Evidence: exact objective files pass 343 unit tests and one PostgreSQL test;
  real upgrade/downgrade/re-upgrade passed; Alembic reports exactly
  `0013_codex_replay_references (head)`; fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
  GitHub's six failures are old expected-head literals outside the allowed set.

### Criterion 8 — PR/path/test economy

- Result: SATISFIED.
- Evidence: one existing PR only; implementation commit contains the exact 27
  allowed implementation/order/pointer paths; no dependency, CI, deployment,
  README, provider-adapter, fixture, old harness, or unrelated artifact change.
  No broad local suite or real provider/service call ran.

### Criterion 9 — all final checks green

- Result: BLOCKED.
- Evidence: eight GitHub checks passed; two failed solely on six hardcoded
  `0012` expectations. Those files are outside 008-b's allowed paths.

### Criterion 10 — report/merge safety

- Result: SATISFIED through report publication.
- Evidence: this immutable report records the literal implementation SHA and
  `SELF`; its report-only commit has that implementation SHA as first parent.
  No merge or auto-merge action was performed.

## Local verification

- `.venv/bin/python -m pytest -o addopts='' -q tests/unit/test_codex_replay_service.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_alembic_codex_replay_references.py tests/unit/test_key_template_service.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py`:
  PASSED — `343 passed in 4.19s` on the final implementation tree.
- `.venv/bin/python -m pytest -o addopts='' -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`:
  PASSED — `17 passed in 1.59s`.
- The exact disposable-PostgreSQL command was:

  ```bash
  set -euo pipefail
  unset DATABASE_URL TEST_DATABASE_URL
  createdb slaif_gateway_test_oap008b_20260818
  trap 'dropdb --if-exists slaif_gateway_test_oap008b_20260818' EXIT
  export TEST_DATABASE_URL='postgresql+asyncpg://ubuntu@/slaif_gateway_test_oap008b_20260818?host=/var/run/postgresql'
  .venv/bin/python -c 'import os; from alembic import command; from alembic.config import Config; c=Config("alembic.ini"); c.set_main_option("sqlalchemy.url", os.environ["TEST_DATABASE_URL"]); command.upgrade(c, "head"); command.downgrade(c, "0012_conversation_references"); command.upgrade(c, "head")'
  .venv/bin/python -m pytest -q tests/integration/test_codex_replay_references_postgres.py
  ```

  PASSED — upgrade/downgrade/re-upgrade and `1 passed`; the explicitly named
  disposable database was dropped by the command trap, and a subsequent
  `pg_database` query returned `0`. `DATABASE_URL` remained unset.
- `.venv/bin/python scripts/verify_codex_reasoning_replay.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`:
  PASSED — exact safe output included `REQUEST_COUNT=3`,
  `REASONING_ITEM_COUNT=1`, `TOOL_PAIR_COUNT=2`, all match/replay/completion
  booleans true, `LOOPBACK_ONLY=true`, and `RAW_PAYLOADS_PERSISTED=false`.
  Earlier development runs failed safely on an assumed four-field replay
  request and then identified only safe shape facts: five fields and a null
  content type. The final request validator accepts only absent/exact null
  content and still rejects plaintext/non-null content.
- `.venv/bin/python -m ruff check app/slaif_gateway/db/models.py app/slaif_gateway/db/repositories/codex_replay.py app/slaif_gateway/providers/streaming.py app/slaif_gateway/services/codex_replay_service.py app/slaif_gateway/services/key_template_service.py app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_route_capabilities.py migrations/versions/0013_codex_replay_references.py scripts/verify_codex_reasoning_replay.py tests/integration/test_codex_replay_references_postgres.py tests/unit/test_alembic_codex_replay_references.py tests/unit/test_codex_replay_service.py tests/unit/test_key_template_service.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py`:
  PASSED — `All checks passed!`.
- `.venv/bin/python -m compileall -q app/slaif_gateway/db/models.py app/slaif_gateway/db/repositories/codex_replay.py app/slaif_gateway/providers/streaming.py app/slaif_gateway/services/codex_replay_service.py app/slaif_gateway/services/key_template_service.py app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_route_capabilities.py migrations/versions/0013_codex_replay_references.py scripts/verify_codex_reasoning_replay.py`:
  PASSED.
- `.venv/bin/alembic heads`: PASSED — exactly
  `0013_codex_replay_references (head)`.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`:
  PASSED — approved immutable digest unchanged.
- `git -C /tmp/slaif-oap005-codex-source-YSOVKH rev-parse HEAD` and
  `git -C /tmp/slaif-oap005-codex-source-YSOVKH describe --tags --exact-match HEAD`:
  PASSED — `be6e8eac029b183056b7e4402879f15d2c85f61b` and
  `rust-v0.147.0`.
- `git diff --check` and `git diff --cached --check`: PASSED.
- `git fetch origin`, `gh auth status`, `gh pr view 233 ...`, and exact-branch
  PR listing: PASSED — authenticated `gh`, expected repository/PR/topology,
  no second objective-008 PR, and expected starting/implementation heads.
- The GitHub CI-fix skill's bundled inspector was attempted but BLOCKED by the
  installed `gh` version rejecting its internal `gh pr checks --json` call.
  Manual `gh run view ... --log-failed` fallback succeeded and supplied the
  bounded failure evidence below.
- Full local unit suite: NOT RUN — prohibited by the work order; GitHub ran it.
- Full local integration suite: NOT RUN — prohibited by the work order; GitHub
  ran it.
- Local E2E suite: NOT RUN — prohibited by the work order; GitHub ran it.
- Local browser suite: NOT RUN — prohibited by the work order; GitHub ran it.
- Local Docker/Compose suite: NOT RUN — prohibited by the work order; GitHub
  ran it.
- Local HPC/supercomputer suite: NOT RUN — prohibited by the work order.
- Real OpenAI/OpenRouter inference: NOT RUN — prohibited; no real provider key
  or provider traffic was used.
- Full CLI-through-gateway Codex validation: NOT RUN — objective 011 remains
  separate. The manual verifier called only the fixed numeric loopback mock.

## GitHub CI / required checks

Check state observed for implementation head
`f8a67a12b494295c04a77bd67b3be6379147ed49` at report drafting:

- `Analyze (javascript-typescript)`: SUCCESS — 42s.
- `Analyze (python)`: SUCCESS — 1m27s.
- `Analyze Python`: SUCCESS — 1m13s.
- `CodeQL`: SUCCESS — 2s.
- `Docker Compose smoke`: SUCCESS — 1m4s.
- `Documentation hygiene`: SUCCESS — 6s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m28s.
- `Playwright browser smoke`: SUCCESS — 1m22s.
- `Unit, lint, and migration head`: FAILURE — 1m52s; unit phase reported
  `5 failed, 2600 passed`. Every failure expected
  `0012_conversation_references` while Alembic correctly returned
  `0013_codex_replay_references`:
  - `tests/unit/test_schema_status.py`
  - `tests/unit/test_alembic_email_jobs.py`
  - `tests/unit/test_alembic_key_prefix_default.py`
  - `tests/unit/test_alembic_provider_pricing.py`
  - `tests/unit/test_alembic_accounting.py`
- `PostgreSQL integration tests`: FAILURE — 2m27s; reported
  `1 failed, 130 passed`. The sole failure was the same stale head assertion in
  `tests/integration/test_gateway_key_prefix_migration_postgres.py`; migration
  upgrade through 0013 itself succeeded.
- All required checks green for the implementation head at report drafting:
  no.
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report.

## CI blocker and required strategic continuation

The focused repair is to update only the current-head expectations in these six
files from `0012_conversation_references` to
`0013_codex_replay_references`, preserving their historical migration-specific
assertions:

```text
tests/unit/test_schema_status.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_alembic_accounting.py
tests/integration/test_gateway_key_prefix_migration_postgres.py
```

None is in the 008-b allowed-path list. No workaround within the allowed files
can honestly make Alembic's sole head remain 0012 while adding required revision
0013. Strategic authorization of a narrow 008-c path expansion is required.

## Safety and scope

- Used only the existing objective branch and PR #233.
- Did not merge, approve, close, or enable auto-merge.
- Did not create a second PR or branch.
- Did not edit 008-a history, the immutable fixture/capture, 007 harnesses,
  dependencies, CI, deployment, README, provider adapters, or unrelated files.
- Preserved unrelated generated state and did not stage or commit
  `.local-provider-catalog/`.
- No `DATABASE_URL` destructive setup; the one test database was explicit,
  disposable, isolated through `TEST_DATABASE_URL`, and confirmed dropped.
- No prompts, completions, raw bodies, provider events, raw replay IDs, HMAC
  digests, ciphertext, summaries, tool arguments/results, gateway/provider
  secrets, email, or production data were printed or committed.
- No real upstream/tool service, shell tool, filesystem tool, network tool, or
  nested tool was invoked by the harmless Codex mock. The mock's only network
  scope was numeric loopback.
- No full local suite was run; GitHub's broad evidence is reported exactly and
  not substituted with local focused passes.

## Documentation impact

Updated `AGENTS.md`, `docs/database-schema.md`, `docs/accounting.md`,
`docs/provider-forwarding-contract.md`, `docs/security-model.md`,
`docs/codex-compatibility.md`, `docs/responses-compatibility.md`, and
`docs/compatibility-matrix.md` with the exact capability gates, request/event
shapes, 24-hour HMAC-only reference schema/lifecycle, ownership and route
semantics, accounting/completion ordering, failure/privacy boundaries,
three-request verifier, client-state/provider-state separation, and remaining
cache/compaction/full-E2E gaps. README was intentionally unchanged.

## Residual risks and blockers

- BLOCKER: six stale migration-head expectation files require a strategic
  allowed-path expansion before the two failed GitHub jobs can pass.
- The report-containing `SELF` commit will retrigger CI but cannot repair those
  out-of-scope assertions; the strategic model must not treat rerun failures as
  acceptance.
- Full CLI-through-gateway validation, prompt-cache guarantees, compaction
  replay, provider-managed state composition, hosted/MCP/background authority,
  and production certification remain outside this objective.
- HMAC replay rows deliberately expire after 24 hours; there is no cleanup job
  in this objective, and expiry-filtered lookups remain authoritative.
- This is an RC-beta foundation, not a production certification or release.

## Completion signal meaning

The coding-agent `OK` for this BLOCKED turn means only that implementation,
immutable report, and claimed remote GitHub/CI state are published. It does not
mean the objective is accepted, checks are green, or PR #233 may be merged.
