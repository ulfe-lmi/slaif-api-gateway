# OAP Coding-Agent Report — 011-a

## Work order

- Identifier: `011-a`
- Work-order file:
  `oap/orders/011-a-codex-cli-gateway-e2e-pilot-readiness.md`
- Work-order SHA-256:
  `dbad70afa0339d9d2c9ec61407592d33dedd1e9330ebaa854b4be0b094bf0ba5`
- Numeric objective: `011`
- PR mode: `CREATE_NEW_PR`

## Status

IMPLEMENTED

## Executive summary

Objective 011-a closes the first pinned Codex phase gate with one opt-in manual
verifier. Exact `/usr/bin/codex` 0.147.0 and bundled `gpt-5.6-sol` ran through
the real local SLAIF app, real PostgreSQL quota/accounting state in a dedicated
disposable database, private no-persistence Redis, and a scripted
numeric-loopback OpenAI Responses mock.

Five actual-Codex scenarios passed: text plus client-side exec/edit and
multi-round encrypted replay; below/edge/above long-context, cache read/write,
reasoning usage, V1 compact, and post-compact continuation; hard request-quota
rejection before upstream; interrupted provider stream; and structured
provider error. Seven successful reservations finalized, two provider-failure
reservations released, and none remained pending. Fixed usage produced exact
key and ledger counters/component accounting. The mock saw only the dummy
server-side upstream authorization and no client/admin/internal headers.
HMAC-only replay rows and a scan of all known text/JSON columns proved that no
per-run prompt, final text, tool marker, reasoning/compaction material,
gateway key, provider key, or raw payload sentinel persisted.

The human-only bounded real-OpenAI pilot procedure is documented with explicit
authorization, non-production target, exact profile, low finite key/call/token/
EUR limits, credential separation, preflight, postflight, revocation,
reconciliation, rollback, and cleanup gates. It was not executed.

The exact support result is:

```text
local_gateway_e2e_qualified=true
bounded_real_openai_pilot_prepared=true
real_provider_e2e=false
```

This is not full Codex compatibility, real-provider qualification, production
readiness, pilot completion, release readiness, or evidence for another
Codex/model/profile. No real provider, production/staging gateway, hosted
tool, MCP/connector, or non-loopback endpoint was called.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Starting and current remote `main` at report drafting:
  `7f35b1107037a9e351fc1128715eccbca1181693`
- Starting commit is the merge commit for PR #235.
- Implementation head SHA:
  `aacabeabf52c0f865aca4eaa87848a5929cb6ea2`
- Implementation-head first parent:
  `7f35b1107037a9e351fc1128715eccbca1181693`
- Implementation-head commit message:
  `OAP 011-a: prove local Codex gateway E2E`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `236`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/236`
- PR title: `[OAP 011] Prove Codex gateway E2E and pilot readiness`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE` / `CLEAN`
- Base branch: `main`
- Head branch: `oap/011-codex-cli-e2e-openai-pilot-readiness`
- Objective-011 PR count: exactly one, PR #236
- Created a new PR this turn: YES
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Unified verifier topology and isolation

The manual script is `scripts/verify_codex_gateway_e2e.py`. It is absent from
pytest/CI/application/startup/packaging/Docker/HPC invocation paths and accepts
no command-line options or positional values.

Its exact trust path was:

```text
Codex 0.147.0 child
  -> 127.0.0.1 ephemeral SLAIF gateway
  -> 127.0.0.1 ephemeral scripted OpenAI Responses mock

SLAIF gateway
  -> dedicated 127.0.0.1 PostgreSQL test database
  -> private 127.0.0.1 ephemeral Redis with persistence disabled
```

The verifier:

- required `TEST_DATABASE_URL` and rejected ambient `DATABASE_URL`;
- accepted only PostgreSQL schemes, numeric `127.0.0.1`, and a database name
  containing `test`, `dev`, or `local`;
- refused `RUN_UPSTREAM_TESTS`, `OPENAI_API_KEY`,
  `OPENAI_UPSTREAM_API_KEY`, and `OPENROUTER_API_KEY` at startup;
- used the validated test URL as the app's database setting only after that
  validation;
- started Redis with an ephemeral port and temporary directory, `--save ""`,
  `--appendonly no`, protected mode, and no operator Redis reuse/flush;
- bound the gateway and mock only to `127.0.0.1`, recorded every gateway/mock
  peer, and required all peers and configured targets to be numeric loopback;
- gave each Codex process a private temporary 0700 root, empty workspace,
  private home/cache/config/data paths, and two 0600 credential-free
  profile-v2 files from the objective-010 renderer;
- invoked only `--profile slaif` with no CLI model/provider override,
  `--ephemeral`, approval `never`, retries zero, bounded output, exact pinned
  bundled model, V2 compaction disabled, and dead external proxies;
- used read-only sandboxes except the single private-workspace exec/edit
  scenario;
- generated all gateway keys through real `KeyService`, kept plaintext only in
  bounded memory/child environments, and stored only the normal HMAC and
  encrypted one-time-secret state;
- kept HTTP/SSE and Codex stdout/stderr in bounded memory, suppressed internal
  logs, discarded payloads, and printed only fixed booleans/counts;
- did not access user `~/.codex`, repository `.codex`, project/user auth,
  history, rules, memories, plugins, or provider configuration.

## Seeded state

The dedicated empty database was migrated to
`0014_codex_context_accounting_compaction` and seeded only with verifier-owned
rows through current repositories/services:

- one reserved/example institution, owner, and cohort using no real identity;
- one enabled `openai` provider pointed to the loopback mock with a
  verifier-only dummy upstream environment-variable name and zero retries;
- reciprocal exact `/v1/responses` and `/v1/responses/compact` routes for
  `gpt-5.6-sol` with exact visibility/streaming behavior, strict known
  Responses booleans, all five gates, 1,050,000/32,768/128,000 Codex limits,
  reciprocal UUIDs, and the unchanged objective-010 qualification object;
- active EUR pricing for both endpoints with ordinary input, cached input,
  cache write, output, reasoning, 272,000 long-context threshold, 2x input,
  and 1.5x output accounting;
- five standard finite keys, each restricted to provider `openai`, model
  `gpt-5.6-sol`, the three exact endpoints, five gates, and local
  `function`/`custom` types; the quota key had request limit one and all keys
  had positive finite request/token/EUR/rate/concurrency limits.

No allow-all flag, trusted-calibration mode, real identity, real URL, real
provider key, hosted tool, MCP/connector, background/provider state, or
production/staging value was seeded.

## Scenario evidence

### A — text, local exec/edit, and encrypted multi-round replay

- Exact Codex completed three admitted `/v1/responses` rounds.
- The mock selected one fixed `tools.exec_command` call limited to `pwd` in the
  private workspace, followed by one fixed `tools.apply_patch` call creating
  only `oap011-marker.txt` there.
- The marker file exactly matched the per-run high-entropy expected content.
- Subsequent gateway requests replayed linked custom-tool output and the exact
  encrypted reasoning item through owned HMAC references.
- Final streamed text completed successfully.
- The gateway forwarded the client tool protocol but did not execute the tool;
  only the Codex child changed its private workspace.
- The workspace and profile root were deleted after validation.
- Exact database result: three finalized reservations/ledgers, three requests,
  six total tokens, and zero reserved request/token counters.

### B — cache/context tiers, V1 compact, and continuation

- Exact path order was `/v1/responses`, `/v1/responses/compact`, then
  `/v1/responses`.
- Fixed provider usage was:
  - above threshold: input 600,000, cached read 200,000, cache write 100,000,
    output 10, reasoning 4, total 600,010;
  - threshold edge: input 272,000, cached read 100,000, cache write 50,000,
    output 2, reasoning 1, total 272,002;
  - below threshold: input 10, cached read 5, cache write 1, output 2,
    reasoning 1, total 12.
- Exact key totals were three requests and 872,024 tokens.
- Component token/cost metadata proved the above/edge/below classification,
  cached-read and cache-write charges, ordinary input/output, reasoning, and
  configured long-context multipliers. Cache-write counts were derived from
  the privacy-reduced component accounting representation and matched
  100,000/50,000/1 exactly.
- Codex reused the prompt-cache key, sent uncompressed requests, performed one
  V1 compact call under the 128,000 reservation policy, replayed one owned
  opaque compaction item, and completed the post-compact continuation.
- Three reservations/ledgers finalized and no reservation remained.

### C — hard quota rejection before upstream

- The request-limit-one key admitted and finalized the first tool round with
  two tokens.
- The required Codex continuation failed non-successfully at the gateway.
- The mock request count remained one, proving rejection before provider side
  effect.
- A following direct OpenAI-shaped request using the same gateway key also
  returned 429 while the mock count remained unchanged, proving sticky normal
  hard-quota truth.
- Only one finalized reservation/ledger existed; key totals were one request,
  two tokens, zero reserved counters, and zero pending reservations.

### D — interruption and structured provider error

- One exact Codex process received a deliberately incomplete chunked SSE
  stream after the provider call; retries were disabled and Codex exited
  non-successfully.
- One exact Codex process received a safe OpenAI-shaped HTTP 429 provider
  error; retries were disabled and Codex exited non-successfully.
- The mock observed exactly one call for each path.
- The interruption ledger failed as `provider_request_error`; the structured
  error ledger failed as `provider_http_error`.
- Both reservations released. Both keys retained zero used and reserved
  request/token counters, and neither path was recorded as successful.
- No missing usage was converted into zero-cost success and no replay
  reference was persisted for either failed call.

## Authentication, accounting, and privacy proof

- Every one of the nine upstream requests carried only
  `Bearer <fixed dummy server-side key>`; none carried a gateway key.
- The outbound allowlist removed cookies, set-cookie, admin auth, internal
  auth, and forwarded-authorization headers.
- All upstream and client peers/targets were numeric loopback.
- Seven successful reservations were `finalized`; two provider-failure
  reservations were `released`; `pending=0` globally.
- Every successful usage ledger was `finalized/success=true`; both failure
  ledgers were `failed/success=false` with current contract error types.
- All five key rows had zero reserved request/token counters after completion.
- Replay rows comprised one compaction, one reasoning, and four
  custom-tool-call references. Every item/call digest was exact lowercase
  64-character HMAC hex with safe ownership/routing/expiry metadata only.
- High-entropy sentinels covered each prompt, workspace marker, final text,
  reasoning/compaction source and encoded value, and every plaintext gateway
  key. The fixed dummy provider key was also included.
- A typed SQLAlchemy read-only scan of every known model table's text/string/
  JSON column found none of those values.
- Raw request/response bodies, tool inputs/outputs, prompts, completions,
  ciphertext, keys, DSNs, arbitrary IDs/URLs, and database rows were never
  printed or persisted as verifier artifacts.

## Final exact manual verifier

Pinned evidence:

```text
/usr/bin/codex --version: codex-cli 0.147.0
model: gpt-5.6-sol
fixture SHA-256: 436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
profile: API-key Responses profile v1 / profile-v2 file layout
```

Dedicated database:

```text
slaif_gateway_oap011_test_20260818a
```

The database was absent before creation, created explicitly with owner
`slaif`, migrated and used only by the verifier, and dropped by its exact
literal name after every attempt. Final PostgreSQL confirmation returned zero
matching databases. Drops were irreversible, but the target contained only
disposable generated verifier data and required no recovery. `DATABASE_URL`
was never used for creation, migration authority, reset, truncation, or drop.

Final command (the DSN contained only the repository-documented local dummy
test-role credential and was not printed by the verifier):

```text
unset DATABASE_URL OPENAI_API_KEY OPENAI_UPSTREAM_API_KEY OPENROUTER_API_KEY RUN_UPSTREAM_TESTS
TEST_DATABASE_URL='postgresql+asyncpg://slaif:<local-test-password>@127.0.0.1:5432/slaif_gateway_oap011_test_20260818a' .venv/bin/python scripts/verify_codex_gateway_e2e.py
```

Final safe output:

```text
RESULT=OK
CLI_VERSION_MATCHED=true
FIXTURE_DIGEST_MATCHED=true
SCENARIO_COUNT=5
TEXT_COMPLETION_SEEN=true
LOCAL_EXEC_SEEN=true
LOCAL_EDIT_SEEN=true
WORKSPACE_MARKER_MATCHED=true
MULTI_ROUND_REPLAY_SEEN=true
ENCRYPTED_REASONING_REPLAY_SEEN=true
CACHE_READ_USAGE_SEEN=true
CACHE_WRITE_USAGE_SEEN=true
LONG_CONTEXT_TIERS_SEEN=true
V1_COMPACT_SEEN=true
POST_COMPACT_CONTINUATION_SEEN=true
QUOTA_REJECTION_SEEN=true
QUOTA_REJECTED_BEFORE_UPSTREAM=true
STREAM_INTERRUPTION_SEEN=true
PROVIDER_ERROR_SEEN=true
ACCOUNTING_MATCHED=true
OUTSTANDING_RESERVATIONS=0
PROVIDER_AUTH_REPLACED=true
OUTBOUND_HEADERS_SANITIZED=true
LOOPBACK_ONLY=true
RAW_PAYLOADS_PERSISTED=false
REDIS_PRIVATE_EPHEMERAL=true
WORKSPACES_REMOVED=true
REAL_PROVIDER_CALLED=false
```

Final wall time was 10.98 seconds. Post-run checks found zero matching
databases, zero `slaif-oap011-codex-*` temporary roots, and zero matching
Redis/Uvicorn verifier processes.

## Failed attempts and repairs

Every failed attempt is recorded here. None contacted a real provider,
production/staging system, or non-loopback endpoint.

1. Initial static command used bare `ruff`, which was not on the system `PATH`;
   the project-local `.venv/bin/ruff` was then used. Its first pass found one
   unused import and required formatting; both were repaired. The same compound
   probe also used system `python` for an argument-refusal check and failed to
   import project `uvicorn`; subsequent commands used `.venv/bin/python`.
2. Direct `.venv/bin/pytest` collection omitted the repository root from that
   entry-point's import path and could not import the namespace `scripts`.
   `.venv/bin/python -m pytest` was used thereafter.
3. The first module-form verifier unit run had three test-construction failures
   because `ParsedHttpRequest.version` was omitted. The tests were corrected;
   no runtime code or external state was involved.
4. Two broad multi-file documentation patch attempts failed exact context
   matching and applied nothing. The same edits were applied as smaller
   reviewed patches.
5. A read-only TCP auth probe for role `ubuntu` correctly refused without a
   password. The documented local dummy `slaif` test role was then validated;
   no credential search occurred.
6. Manual verifier attempt 1 ran for 11.25 seconds and returned only
   `RESULT=FAIL`, `ERROR_CODE=verification_failed`, and
   `REAL_PROVIDER_CALLED=false`. The error was too coarse, so reviewed fixed
   stage codes were added. Its exact disposable database was dropped and
   recreated empty.
7. Manual verifier attempt 2 ran for 11.03 seconds and returned only
   `RESULT=FAIL`, `ERROR_CODE=final_reduction_failed`, and
   `REAL_PROVIDER_CALLED=false`. Safe aggregate inspection showed exact
   requests/tokens, seven finalized and two released reservations, zero
   pending, and HMAC-only replay rows. The reducer had expected a top-level
   cache-write field that privacy sanitization intentionally removes. It was
   corrected to derive the exact 100,000/50,000/1 write counts from retained
   component token/cost facts. The database was dropped and recreated empty.
8. Manual verifier attempt 3 passed in 11.41 seconds. A final hardening edit
   then added explicit recording/validation of every gateway peer and 0600
   modes for the tool scenario's profile files. Because code changed, that
   passing database was dropped and a fresh final run was performed.
9. The final-code attempt passed in 10.98 seconds with the exact output above.
   Its database and all temporary processes/files were removed.

One initial process-cleanup `pgrep` count matched the diagnostic command's own
literal pattern. The pattern was made self-excluding and returned zero; this
was a diagnostic correction, not a leaked process.

## Changes and exact paths

The implementation commit changes only these 13 order-allowed paths:

```text
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/openai-compatibility.md
docs/runbooks/README.md
docs/runbooks/codex-openai-pilot.md
docs/security-model.md
docs/testing-parallelism.md
oap/active
oap/orders/011-a-codex-cli-gateway-e2e-pilot-readiness.md
scripts/verify_codex_gateway_e2e.py
tests/unit/test_codex_gateway_e2e_verifier.py
```

`oap/active` is exactly `011-a`; exactly one `011-a` order exists and no report
existed before publication. The activated order remained byte-for-byte
unchanged at the recorded SHA-256. The final report-publication commit adds
only `oap/reports/011-a-codex-cli-gateway-e2e-pilot-readiness.md`.

## Local focused verification

- `.venv/bin/python -m pytest -q tests/unit/test_codex_gateway_e2e_verifier.py tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_supercomputer_sharded_script.py`:
  PASSED — 62 tests in the final focused run, 3.50 seconds; zero
  failures/errors/skips.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py` after report drafting:
  PASSED — 17 tests; zero failures/errors/skips.
- `.venv/bin/ruff check scripts/verify_codex_gateway_e2e.py tests/unit/test_codex_gateway_e2e_verifier.py`:
  PASSED.
- `.venv/bin/ruff format --check scripts/verify_codex_gateway_e2e.py tests/unit/test_codex_gateway_e2e_verifier.py`:
  PASSED.
- `.venv/bin/python -m py_compile scripts/verify_codex_gateway_e2e.py tests/unit/test_codex_gateway_e2e_verifier.py`:
  PASSED.
- Final exact manual verifier: PASSED with the command, output, topology,
  accounting, privacy, auth, cleanup, and elapsed time recorded above.
- Fixture SHA-256: PASSED — exact approved digest above.
- Work-order SHA-256: PASSED — exact activated digest above.
- Exact branch, pointer, unique order/no-preexisting-report topology, allowed
  paths, implementation first parent, local/remote implementation head, and
  one objective PR: PASSED.
- `git diff --check`: product paths PASSED. Staged checking reported only the
  unchanged activated order's pre-existing extra blank line at EOF. Its exact
  digest is recorded above and those strategic bytes were preserved.
- Full local unit suite: NOT RUN — prohibited by the active order's focused
  test economy; GitHub CI owns broad routine coverage.
- Additional local PostgreSQL integration suite: NOT RUN — prohibited. The
  required single unified manual verifier used its own dedicated database.
- Additional local OpenAI-client E2E suite: NOT RUN — prohibited.
- Local Playwright/browser suite: NOT RUN — prohibited.
- Local Docker/Compose validation: NOT RUN — prohibited.
- Local HPC/supercomputer suite: NOT RUN — prohibited.
- Older manual Codex verifiers: NOT RUN — prohibited because the unified proof
  covers the required boundaries.
- Upstream-optional/real-provider tests: NOT RUN — prohibited.
- Real OpenAI pilot: NOT RUN — requires fresh human authorization and
  credentials.

## GitHub CI / checks

All ten checks completed successfully for implementation head
`aacabeabf52c0f865aca4eaa87848a5929cb6ea2`, observed after exact 30-second
wait blocks:

- `Analyze (javascript-typescript)`: SUCCESS — 45s.
- `Analyze (python)`: SUCCESS — 1m15s.
- `Analyze Python`: SUCCESS — 1m01s.
- `CodeQL`: SUCCESS — 3s.
- `Docker Compose smoke`: SUCCESS — 1m13s.
- `Documentation hygiene`: SUCCESS — 5s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m32s.
- `Playwright browser smoke`: SUCCESS — 1m23s.
- `PostgreSQL integration tests`: SUCCESS — 2m23s.
- `Unit, lint, and migration head`: SUCCESS — 2m05s.
- Cancelled: 0.
- Failed: 0.
- Skipped: 0.
- Pending: 0.
- In-scope CI repair required: NO.
- Fresh report-head checks may run after SELF publication; the response FIFO
  remains withheld until the report-only remote head and its required checks
  are verified.

## Real-OpenAI pilot preparation

`docs/runbooks/codex-openai-pilot.md` is indexed from the operator runbooks and
begins with a hard stop unless a human separately authorizes the exact real
provider call and chooses a non-production target. It requires:

- exact Codex 0.147.0, `gpt-5.6-sol`, and profile v1;
- server-side `OPENAI_UPSTREAM_API_KEY` only and a one-time standard gateway
  key supplied to Codex only as `OPENAI_API_KEY` without argv/history exposure;
- one provider/model, three endpoints, five gates, local function/custom
  types, no allow-all/trusted-calibration/hosted/MCP/background/provider-state/
  external authority, and low finite request/token/EUR/rate/concurrency limits;
- credential-free `codex inspect`/profile generation, `/v1/models` visibility,
  cost/quota ceiling review, zero-reservation preflight, one fixed harmless
  prompt, one Codex process, and at most four admitted provider requests;
- safe postflight ledger/quota/component/provider-request-ID evidence, HMAC/
  privacy/auth checks, immediate key revocation, environment/workspace cleanup,
  reservation reconciliation, and explicit route-disable/abort criteria;
- fresh authorization for any retry and explicit human acceptance before any
  later strategic order may consider `real_provider_e2e=true`.

The procedure was not executed by this PR. No CI hook, automatic script,
credential argument, or normal-test provider call was added.

## Documentation impact

Documentation updated: `AGENTS.md`, `docs/codex-compatibility.md`,
`docs/compatibility-matrix.md`, `docs/configuration.md`,
`docs/openai-compatibility.md`, `docs/security-model.md`,
`docs/testing-parallelism.md`, `docs/runbooks/README.md`, and
`docs/runbooks/codex-openai-pilot.md`.

The contracts now distinguish strict route `protocol_qualified` state from the
passing local gateway E2E phase gate and the unexecuted real-provider pilot.
They document the exact manual command/isolation/accounting/privacy boundary,
normal-test exclusion, three supported status booleans, and the human
authorization/revocation/rollback procedure without making a production,
release, full-compatibility, or real-provider claim.

No README, runtime policy, provider, accounting, quota, HMAC, schema,
migration, dependency, CI, Compose, fixture, or prior OAP-history file changed.

## Local setup and cleanup

- Packages installed: NONE.
- Services installed or reconfigured: NONE.
- Existing operator PostgreSQL databases modified: NO.
- Existing operator Redis used/flushed: NO.
- Disposable PostgreSQL database created/dropped: YES, exact generated test
  target recorded above; absent after final cleanup.
- Private Redis children/temp directories created/removed: YES; persistence
  disabled and zero matching processes remained.
- Temporary Codex homes/workspaces created/removed: YES; zero matching roots
  remained.
- Real key/provider credential discovered, read, printed, or stored: NO.
- Durable setup changes outside the repository: NONE.

## Safety and scope confirmations

- Unrelated files changed: NO.
- `.local-provider-catalog/` accessed, modified, staged, or committed: NO.
- Linked worktrees or unrelated artifacts changed: NO.
- Production/staging systems accessed: NO.
- Real provider called: NO (`REAL_PROVIDER_CALLED=false`).
- Real email sent: NO.
- Hosted tool, MCP/connector, web search, external network/tool authority, or
  provider-managed state used: NO.
- Prompts/completions/raw bodies/tool payloads/reasoning/ciphertext/keys/DSNs
  printed or committed: NO.
- `DATABASE_URL` used for destructive setup: NO.
- Dedicated `TEST_DATABASE_URL` isolation for the manual DB: YES.
- Required focused tests/manual evidence skipped: NO.
- Broad local suites intentionally not run: YES, as enumerated above.
- Scope deviation: NO.
- Extra PR created for objective 011: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order or active pointer rewritten by coding agent: NO; exact
  strategic bytes were committed unchanged.
- Report-publication commit changes only this report file: YES, to be verified
  before the FIFO response.

## Continuation / residual boundary

The local phase gate and prepared runbook are complete for 011-a. Strategic
review still owns acceptance and any continuation decision. A real OpenAI
pilot, any setting of `real_provider_e2e=true`, support for a different
Codex/model/profile, V2 compaction, production certification, release decision,
or merge requires a separate authorized strategic objective/human decision.

The coding agent did not merge and did not enable auto-merge.
