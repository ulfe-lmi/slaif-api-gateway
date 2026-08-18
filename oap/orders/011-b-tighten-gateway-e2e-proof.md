# OAP Work Order — 011-b

## Objective

Amend objective-011 PR #236 to make the passing unified verifier prove every
fact it reports: exact monetary/component accounting, successful local-exec and
final-text output rather than request-count inference, provider-failure raw-body
privacy, strict numeric-loopback database targeting, and consistent 0600
profile-file modes. Add a copyable bounded Codex command to the prepared human
pilot runbook. Preserve the five passing scenarios, no-real-provider boundary,
and all accepted 011-a behavior otherwise.

## GitHub objective state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #236,
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/236`.
- PR title: `[OAP 011] Prove Codex gateway E2E and pilot readiness`.
- Required existing branch: `oap/011-codex-cli-e2e-openai-pilot-readiness`.
- Base branch: `main`.
- Remote PR head at activation:
  `fbf1d71d04ac5160a362faa5a74ca33a7bf4a1b5`, the immutable 011-a report
  publication commit.
- Its first parent is implementation head
  `aacabeabf52c0f865aca4eaa87848a5929cb6ea2`.
- All ten report-head GitHub checks were independently observed successful.
- PR #236 is open, non-draft, unique for objective 011, and auto-merge is off.
- Remote `main` remains
  `7f35b1107037a9e351fc1128715eccbca1181693`.
- This is `AMEND_EXISTING_PR`. Reconcile current GitHub state, amend only PR
  #236, and never create another PR, merge, or enable auto-merge.

## Why 011-a is not yet accepted

011-a's actual-client local gateway run is valuable and passed, but independent
strategic review found proof reductions that are weaker than the work order and
one immutable-report claim that does not match code.

### 1. Money is not reconciled exactly

`KeyAccountingFacts` and `_validate_accounting()` assert exact request/token
counts and reservation/ledger statuses. For component money, however, they
only require positive cache-write values and tier flags. They do not load or
compare:

- `gateway_keys.cost_used_eur` / `cost_reserved_eur`;
- each ledger's `actual_cost_eur`, `actual_cost_native`, and native currency;
- the complete exact `component_costs_native` mapping;
- exact per-scenario/key monetary totals under the seeded EUR pricing.

The 011-a report therefore overstates “exact ... component accounting.” This
continuation must calculate and assert exact Decimal costs from the fixed
provider usage and seeded 1/0.5/1.25/2 prices plus 2x/1.5x long-context
multipliers. Compare at the database column's exact scale; do not use floats or
mere positivity/tolerance. Successful tool/context/quota keys and every ledger
must reconcile, reserved cost must return to zero, and failure keys/ledgers must
match the current exact zero/null cost contract. The 011-b report must list safe
per-scenario actual EUR totals and the exact component-cost expectations.

### 2. `LOCAL_EXEC_SEEN` and final text are inferred

The current reducer sets `LOCAL_EXEC_SEEN=true` from process completion plus
three upstream requests. It checks that some custom-tool output replay exists,
but not that the `call_oap011_exec` output contains the expected successful exec
result. A denied/failed tool output could therefore satisfy the boolean. It also
sets `TEXT_COMPLETION_SEEN` from `turn.completed` without requiring the unique
final marker in bounded structured Codex stdout.

Generate a high-entropy per-run exec sentinel. The fixed `pwd` tool source must
emit that sentinel only after successful completion. Inspect the next request's
linked `custom_tool_call_output` for exact call ID and recursively validated
output text containing the sentinel. Require the final streamed marker in the
bounded structured Codex result before setting `TEXT_COMPLETION_SEEN`. Add the
exec sentinel to the no-persistence scan so both tool input and output are
covered. Do not print any marker or raw Codex output.

### 3. Provider failure/interruption bodies lack unique privacy sentinels

The DB-wide scan covers prompts, normal final text, edit marker, reasoning/
compaction material, keys, and dummy upstream auth, but the provider-error body
uses a fixed message not included in the sentinel set. The interrupted stream's
provider response content likewise has no per-run sentinel. Raw provider failure
bodies could be persisted without the current proof detecting them.

Put a unique sentinel into each scripted provider-error and interruption body,
add it to the scan, and still require the exact safe ledger error types:
`provider_request_error` for interruption and `provider_http_error` for the
structured 429. Neither sentinel may reach any known text/JSON column or fixed
output/report. Keep the mock/error shapes valid and retries/call counts
unchanged.

### 4. Test DB URLs with arbitrary query parameters are accepted

The validator requires hostname `127.0.0.1` but permits arbitrary query
parameters except one `sslmode` spelling. PostgreSQL drivers can interpret
connection query options; allowing them is unnecessary and weakens the exact
numeric-loopback target proof. Reject every query string, fragment, control/
whitespace ambiguity, and noncanonical target. Add tests including host/socket
override-style parameters. Keep the final documented local dummy asyncpg URL
valid and never print its password/DSN.

### 5. Profile-file mode claim is false for the tool scenario

The 011-a report says every generated profile file was 0600 and says a final
hardening edit covered the tool scenario. In the committed code, `run_codex()`
calls `chmod` twice per file, while `_run_tool_scenario()` writes the two files
without chmod. The enclosing directory is 0700, so this did not expose a real
credential (the files are credential-free), but the evidence claim is false.

Factor one shared profile/workspace preparation helper used by every scenario.
It must create a 0700 root/home/workspace, write the two credential-free files
once, set each to 0600 once, and verify their modes before the child starts.
Remove duplicated setup/chmod. Cleanup must validate the generated temp root
against the resolved `tempfile.gettempdir()` rather than assuming literal
`/tmp`, while retaining the unique prefix guard. Add pure tests for modes,
targets, credential absence, and safe cleanup-target rejection; do not delete a
unit-test directory outside the helper's own generated root.

### 6. Human pilot runbook lacks the exact Codex command

The prepared runbook describes flags and the fixed harmless prompt but does not
give the human a single copyable command. Add one exact command using the named
profile, ephemeral mode, approval `never`, retries disabled, workspace-write
sandbox, chosen disposable workspace, and the fixed harmless prompt. It must
not place either secret in argv/history or enable search/network/hosted tools.
State what safe exit/marker/output facts to observe and retain the at-most-four
provider-call ceiling. The procedure remains PREPARED, NOT EXECUTED.

## Required implementation and evidence

Change only the verifier, its pure test file, directly affected docs/runbook,
and OAP transcript. Keep output keys and the five-scenario topology stable
unless one additional low-cardinality boolean is genuinely required. The final
manual run must use a newly created empty disposable database, exact no-real-key
environment, private Redis, real local app, numeric-loopback mock, and exact
Codex 0.147.0. Drop only the explicit generated database afterward and prove no
matching DB/process/temp root remains.

The manual verifier must still print only fixed booleans/counts and
`REAL_PROVIDER_CALLED=false`. Exact monetary values belong in the immutable
report, not normal verifier output, unless represented as pre-reviewed fixed
constants without arbitrary row data. Never print sentinels, keys, DSNs, raw
payloads, component metadata blobs, or subprocess output.

Preserve:

- exact profile/fixture/model identity and qualification metadata;
- server-side auth substitution and header proof;
- exec/edit restricted to the generated workspace;
- V1 compaction, quota rejection, interruption, and provider-error behavior;
- HMAC-only replay and DB-wide no-content scan;
- zero pending/reserved counters and safe cleanup;
- `local_gateway_e2e_qualified=true`,
  `bounded_real_openai_pilot_prepared=true`, and
  `real_provider_e2e=false` only after all tightened proofs pass;
- no real provider/gateway/staging/production/hosted/MCP/external call.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/openai-compatibility.md
docs/runbooks/codex-openai-pilot.md
docs/security-model.md
docs/testing-parallelism.md
oap/active
oap/orders/011-b-tighten-gateway-e2e-proof.md
scripts/verify_codex_gateway_e2e.py
tests/unit/test_codex_gateway_e2e_verifier.py
```

The final report-only commit adds only:

```text
oap/reports/011-b-tighten-gateway-e2e-proof.md
```

Preserve 011-a and every earlier order/report byte-for-byte. If a different
path is genuinely required, do not edit it; publish `BLOCKED` with the exact
path/reason for a strategic 011-c decision.

## Focused verification and test economy

Run only:

- `tests/unit/test_codex_gateway_e2e_verifier.py`;
- focused OAP/documentation tests;
- scoped Ruff/format/compile, fixture/order digests, `git diff --check`, exact
  paths/topology;
- one final exact five-scenario manual verifier against a fresh dedicated
  disposable database.

Do not run the full local unit, integration/PostgreSQL, OpenAI-client E2E,
Playwright/browser, Docker/Compose, HPC, old manual Codex verifiers, or
upstream-optional suites. The one unified DB/manual run is the necessary proof;
GitHub CI owns broad routine coverage. The user explicitly asked not to overuse
full suites. Never make a real-provider call or look for credentials.

## Acceptance criteria

1. Every successful ledger and gateway key reconciles exact Decimal component,
   native, and EUR cost under the seeded pricing; reserved money is zero and
   failure cost fields satisfy the exact current contract.
2. Local exec requires the exact linked successful output sentinel, final text
   requires the exact bounded structured-output marker, edit still requires the
   marker file, and none of those values persists or prints.
3. Unique provider-error/interruption sentinels prove raw failure bodies are not
   stored; exact safe failure types/statuses/call counts remain.
4. Database validation rejects all query/fragment/whitespace override forms and
   accepts only a canonical numeric-loopback disposable target.
5. One shared root/profile helper produces verified 0700 directories and 0600
   credential-free files for every scenario with safe portable cleanup; report
   claims exactly match code.
6. The pilot runbook contains one exact safe Codex command but remains explicitly
   unexecuted and separately human-authorized.
7. Focused tests, final manual verifier, privacy/accounting/cleanup evidence,
   docs, and every required report-head GitHub check pass; broad local suites
   and real providers remain not run.
8. Only PR #236 is amended; coding agent never merges/enables auto-merge; final
   011-b report has valid `SELF` topology.

## GitHub and report contract

Commit the unchanged 011-b order and `oap/active=011-b` with the implementation
on the existing branch, push it, and update PR #236's body to the current proof
state. Do not rewrite earlier commits/reports. Inspect GitHub checks and repair
only in-scope failures. Never merge or enable auto-merge.

Publish exactly one immutable report at
`oap/reports/011-b-tighten-gateway-e2e-proof.md` with literal implementation
SHA, `Report publication commit: SELF`, exact cost tables/totals, exec/final/
failure sentinel facts, profile modes, DB validation, final verifier output,
disposable DB/process/root cleanup, focused/GitHub checks, broad suites not run,
explicit real-provider NOT RUN, and no-merge/no-auto-merge. The report-only
commit must parent the implementation head and change only that report. Verify
remote report head and all required checks, then signal exact `OK`.

