# OAP Work Order — 011-a

## Objective

Close the first Codex phase gate with one reproducible, content-minimizing,
actual-client end-to-end verifier that sends pinned Codex CLI 0.147.0 through a
real local SLAIF gateway, real disposable PostgreSQL quota/accounting state,
and a numeric-loopback OpenAI mock. Prove the supported text, local exec/edit,
multi-round encrypted replay, V1 compaction, quota rejection, provider
interruption, and provider-error boundaries. Publish an explicit separately
authorized real-OpenAI pilot procedure and rollback plan, but do not call a real
provider in this objective.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote default branch: `main`.
- Starting remote `main`:
  `7f35b1107037a9e351fc1128715eccbca1181693`, merge commit for PR #235.
- Objectives 004 through 010 are merged. Objective 010's final accepted report
  head is `fc33623cf629ab7a145ebcba41b55308f85914bc`.
- Current Alembic head is `0014_codex_context_accounting_compaction`; this
  objective adds no migration.
- Exact supported identity remains:

```text
Codex binary: /usr/bin/codex
CLI version: 0.147.0
source tag: rust-v0.147.0
source commit: be6e8eac029b183056b7e4402879f15d2c85f61b
model: gpt-5.6-sol
fixture SHA-256: 436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
profile: API-key Responses profile v1 / Codex profile-v2 file layout
```

- The only unrelated open PR is Dependabot #224. Do not modify or reuse it.
- No PR or remote branch exists for objective 011 at activation.
- PR mode: `CREATE_NEW_PR`.
- Required branch: `oap/011-codex-cli-e2e-openai-pilot-readiness`.
- Required PR title:
  `[OAP 011] Prove Codex gateway E2E and pilot readiness`.
- Local PostgreSQL is available on numeric loopback and a safe test database
  may be created through the repository's documented narrow postgres commands.
  Local Redis tooling is available. Ambient `TEST_DATABASE_URL` and real
  provider-key variables were not set at activation. Reconcile actual local
  capability again rather than trusting this observation.
- Preserve `.local-provider-catalog/`, linked worktrees, user Codex config,
  secrets, and all unrelated artifacts.

Fetch/reconcile GitHub and these facts before editing. Start the new branch from
current remote `main`, never from the merged objective-010 feature branch.

## Support boundary and authority

This objective may establish:

```text
local_gateway_e2e_qualified=true
bounded_real_openai_pilot_prepared=true
real_provider_e2e=false
```

It may not claim full Codex compatibility, real-provider qualification,
production readiness, pilot completion, release readiness, or support for any
other Codex/model version. Do not alter objective 010's exact
`capabilities.codex_qualification` object or set `real_provider_e2e=true`.

The human has **not** authorized a real OpenAI call or supplied credentials for
this objective. Never read/call/probe OpenAI, a real gateway, production,
staging, hosted tools, MCP/connectors, or any non-loopback endpoint. Do not
search for credentials in shell history, dotfiles, processes, secret stores,
or user config. A missing credential is expected, not a blocker for this local
phase gate.

## Unified actual-Codex gateway verifier

Add one manual verifier, preferably
`scripts/verify_codex_gateway_e2e.py`, with pure helpers covered by unit tests.
It must never be invoked by pytest, CI, application startup, import, migrations,
or packaging. The final manual invocation is deliberate and separately listed
in the report.

### Isolation and topology

The verifier must construct this exact trust path:

```text
Codex 0.147.0 child
  -> numeric-loopback SLAIF gateway
  -> numeric-loopback scripted OpenAI Responses mock

SLAIF gateway
  -> validated disposable PostgreSQL TEST database
  -> private temporary numeric-loopback Redis (no persistence)
```

Requirements:

1. Require `TEST_DATABASE_URL`; never accept or use ambient `DATABASE_URL` as
   the destructive/setup authority. Validate PostgreSQL scheme, non-production
   environment, numeric-loopback host, and a database name containing
   `test`, `dev`, or `local`. Refuse otherwise with a fixed safe error.
2. The verifier may set the validated test URL as `DATABASE_URL` only inside
   the isolated gateway child/runtime after validation. Do not echo the DSN,
   password, or environment.
3. Use a dedicated empty/disposable database for the final run. It is acceptable
   for the executor to create one explicit unique name such as
   `slaif_gateway_oap011_test_<safe-suffix>` with the documented `slaif` test
   role, migrate it, run the verifier, and drop that exact database afterward.
   Never drop/reset/truncate a broad or unresolved target. Record creation,
   cleanup, and recoverability truthfully.
4. Start a private Redis child on numeric loopback with an ephemeral port,
   temporary directory, snapshots disabled, and append-only persistence
   disabled. Do not flush or reuse an operator Redis database.
5. Bind the gateway and upstream mock only to `127.0.0.1` on ephemeral ports.
   Set dead external proxies and numeric-loopback-only proxy exceptions for
   children. Record every accepted peer and fail if any target/peer is not
   numeric loopback.
6. Use a private temporary `CODEX_HOME`, home/cache/config/data directories,
   empty temporary workspace, and objective-010 two-file profile-v2 renderer.
   Use `--profile slaif`, `--ephemeral`, no retries, bounded output, and exact
   pinned model without CLI model/provider overrides. Never access or modify
   `~/.codex`, repository `.codex`, or project-local auth/provider config.
7. Use fixed safe dummy server secrets and a fixed dummy upstream provider key
   only in child environments. Generate gateway keys through the real
   `KeyService`; keep plaintext in bounded memory/child environment only. The
   database must retain only the normal HMAC/encrypted one-time-secret state.
8. The mock must observe the server-side dummy upstream authorization, not the
   gateway key/client Authorization value. Do not print either value. Prove the
   normal outbound allowlist removed client cookies/admin/internal headers.
9. Capture raw HTTP/SSE and Codex subprocess output only in bounded memory for
   validation, then delete it. Never print or persist prompts, completions,
   tool inputs/outputs, reasoning/ciphertext, raw bodies, or full subprocess
   output.

Reuse the exact frozen fixture and existing verifier helpers where practical.
Do not rewrite older evidence or duplicate large pinned model instructions.

### Seeded gateway state

Seed only the verifier-owned rows, through current repositories/services and
normal validation paths:

- one enabled `openai` provider whose base URL is the loopback mock and whose
  key env name is a verifier-only dummy upstream variable;
- exact enabled/visible/streaming `/v1/responses` and exact enabled
  `/v1/responses/compact` routes for `gpt-5.6-sol`, reciprocal UUIDs, baseline
  strict Responses booleans including `text`, all five Codex gates, strict
  limits, and the exact objective-010 qualification declaration;
- complete active EUR pricing for both endpoints with cached input, cache
  write, ordinary input/output, reasoning, and long-context metadata required
  by objective 009;
- reserved/example owner identity and standard gateway keys with the exact
  objective-010 provider/model/three-endpoint/five-gate/local-tool policy and
  positive finite request/token/cost limits;
- no real person, email, provider key, production/staging URL, allow-all flag,
  trusted-calibration mode, hosted tool, MCP, background state, or provider-
  managed response state.

After each scenario, query the real database through safe typed repositories or
explicit reviewed columns. At final cleanup, delete only verifier-owned rows or
drop only the explicitly generated disposable database. Do not log raw row
bodies.

### Exact scenario matrix

Run actual `/usr/bin/codex` separately for these bounded scenarios. Mock
responses are deterministic; Codex executes only mock-selected local actions,
never model-selected external authority.

#### A. Text + local exec/edit + multi-round replay

- Stream one fixed client-side shell/exec call restricted to the private
  workspace and one fixed edit/apply-patch call that creates or changes only a
  verifier marker file there.
- Use harmless fixed commands; no network, package manager, Git mutation,
  credentials, broad filesystem read, or process control.
- Require at least two provider Responses rounds, linked tool output replay,
  encrypted reasoning replay where emitted, final text completion, and the
  exact expected marker file content.
- Verify the gateway itself never executes the client tool and the workspace is
  deleted afterward.

#### B. Cache/context tier + V1 compaction + continuation

- Carry the existing exact objective-009 bounded context/compaction scenario
  through the gateway rather than directly to a mock.
- Observe cache-read and cache-write usage, reasoning usage, below/edge/above
  long-context accounting cases, one `/v1/responses/compact` request, opaque
  HMAC-bound compaction replay, and one successful post-compact continuation.
- Preserve uncompressed Codex requests and the 128,000 compact reservation
  policy. V2 compaction remains disabled.

#### C. Hard quota rejection before upstream

- Use a separate exact pilot key whose finite request limit permits the first
  scripted tool round but rejects the required next Codex continuation.
- Codex must terminate non-successfully with bounded output; the mock must see
  no call for the rejected request.
- Prove the rejection occurred before provider side effect, no pending
  reservation remains, finalized counters reflect only admitted/finalized
  work, and the following request remains blocked as normal hard-quota truth
  requires.

#### D. Provider stream interruption and structured provider error

- With retries disabled, run one scenario where the loopback upstream closes a
  stream before supported final usage/completion, and one scenario returning a
  safe OpenAI-shaped provider error before completion.
- Codex must terminate non-successfully without raw output. Prove the provider
  was called only the intended bounded count, no reservation remains pending,
  failure/recovery accounting matches current gateway contracts, and neither
  path is recorded as normal successful completion.
- Do not weaken accounting or convert missing provider usage into zero-cost
  success merely to satisfy the verifier.

### Accounting and no-content-storage proof

For admitted successful calls, use fixed mock usage/cost facts and assert exact
PostgreSQL key counters, quota reservation states, usage-ledger status,
component token counts/costs, cached/cache-write/reasoning/long-context
classification, and zero outstanding reservations. For rejected/error paths,
assert the documented release/failure semantics and upstream call counts.

Use unique high-entropy sentinel markers in the temporary prompt, tool data,
workspace file, encrypted item, and final text. Query only the known gateway
tables/columns that can store text/JSON/metadata and prove no sentinel/raw body,
tool payload, reasoning content/ciphertext, prompt, or completion is persisted.
HMAC replay/reference rows may contain only their existing digest and safe
ownership/routing/expiry metadata. Do not print sentinel values or raw column
contents.

The final verifier output must be low-cardinality facts only, for example:

```text
RESULT=OK
CLI_VERSION_MATCHED=true
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
LOOPBACK_ONLY=true
RAW_PAYLOADS_PERSISTED=false
REAL_PROVIDER_CALLED=false
```

Exact key names may be refined, but no arbitrary message, identifier, URL,
body, content, secret, DSN, key, or raw row may be printed. A failure prints
only a fixed safe stage/error code and exits nonzero.

## Real-OpenAI bounded pilot procedure — prepare, do not execute

Add `docs/runbooks/codex-openai-pilot.md` and index it from
`docs/runbooks/README.md`. The runbook must be executable by a human later but
must begin with a hard authorization gate:

- separate explicit human authorization for a real provider call;
- non-production local/staging gateway chosen by the human;
- exact Codex 0.147.0 / `gpt-5.6-sol` / profile v1 only;
- server-side upstream secret named `OPENAI_UPSTREAM_API_KEY`, never
  `OPENAI_API_KEY` in the gateway environment;
- one newly issued standard pilot gateway key supplied only as client
  `OPENAI_API_KEY`, with exactly one provider/model, the three endpoints, five
  gates, local function/custom types, and deliberately low positive finite
  request/token/EUR limits;
- hosted tools, MCP/connectors, web search, background, provider state,
  external network/tool authority, allow-all, and trusted calibration disabled;
- one fixed harmless prompt in a disposable workspace, bounded call count, no
  customer/personal/proprietary content, no raw capture/logging;
- preflight `slaif-gateway codex inspect`, credential-free profile generation,
  `/v1/models` visibility, expected cost/quota ceiling, and zero outstanding
  reservations;
- postflight safe usage-ledger/quota/provider-request-ID checks, key revocation,
  environment cleanup, workspace removal, reservation reconciliation, and
  explicit rollback/route-disable criteria;
- exact evidence required before any later strategic order may set
  `real_provider_e2e=true`.

The runbook must clearly state that this PR did not execute the procedure. Do
not add a normal-test upstream call, auto-run script, credential argument, shell
example that places secrets in argv/history, or CI secret dependency. If a
non-network preflight helper is added, it may inspect only local DB readiness
and environment-variable presence/names, must never print values, and must have
an explicit `REAL_PROVIDER_CALLED=false` result.

## Allowed paths

Implementation/evidence may change only:

```text
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/openai-compatibility.md
docs/security-model.md
docs/testing-parallelism.md
docs/runbooks/README.md
docs/runbooks/codex-openai-pilot.md
oap/active
oap/orders/011-a-codex-cli-gateway-e2e-pilot-readiness.md
scripts/verify_codex_gateway_e2e.py
tests/unit/test_codex_gateway_e2e_verifier.py
```

The final report-only commit adds only:

```text
oap/reports/011-a-codex-cli-gateway-e2e-pilot-readiness.md
```

Do not modify existing runtime policy/provider/accounting/quota/HMAC code,
existing verifiers/fixtures, DB models/migrations, dependencies, CI, Compose,
admin/CLI product code, README, or older OAP history in 011-a. This round is the
unified evidence harness and pilot contract. If the exact actual-client gateway
run exposes a product defect or a genuinely required extra path, do not weaken
the scenario or edit outside this list. Publish a sanitized `BLOCKED` report
with the exact stage/path/reason for a narrow strategic 011-b continuation on
the same PR.

## Focused verification and test economy

Run only:

- pure/unit tests for the new verifier's state machine, safe URL/DB validation,
  mock stages, fixed output, argument/env handling, privacy reduction, and
  proof that pytest/CI/import do not invoke Codex;
- focused OAP/documentation tests;
- scoped Ruff/compile, `git diff --check`, fixture digest, exact allowed paths,
  and OAP topology;
- one final exact manual actual-Codex gateway verifier against the dedicated
  disposable PostgreSQL database and private Redis/mock/gateway children.

The actual verifier is the necessary integration proof for this objective; do
not additionally run the full local unit, integration, PostgreSQL, E2E,
Playwright/browser, Docker/Compose, HPC, or upstream-optional suites. GitHub CI
owns broad routine coverage. The human has explicitly asked not to overuse full
suites. Do not invoke all older manual Codex verifiers separately when the new
unified proof covers them. Record exact focused commands/counts, disposable DB
setup/cleanup, elapsed time, every failed attempt, and every broad suite NOT RUN.

Never make a real provider call. The final report must state
`REAL_PROVIDER_CALLED=false` and real-provider pilot `NOT RUN — requires fresh
human authorization and credentials`.

## Acceptance criteria

1. Exact Codex 0.147.0 completes the deterministic text/exec/edit/multi-round
   scenario through the real local gateway and loopback upstream; only the
   temporary workspace changes and the gateway never executes the tool.
2. Exact Codex performs the objective-009 cache/long-context/V1-compaction/
   continuation scenario through the gateway with strict route/key/profile
   qualification and no compression/raw persistence.
3. A finite pilot key rejects the next over-quota continuation before upstream,
   while interruption and structured provider-error scenarios terminate safely
   with correct non-success accounting and zero pending reservations.
4. Exact fixed provider usage yields matching PostgreSQL quotas/ledger/component
   accounting; authentication is substituted server-side; no sentinel/content/
   ciphertext/raw payload is stored or printed.
5. All processes, files, peers, and requests remain inside private temporary or
   numeric-loopback boundaries. The dedicated test database/private Redis and
   verifier-owned rows are cleaned safely and truthfully.
6. The real-OpenAI pilot runbook has explicit authorization, credentials,
   bounded key/call/cost/tool/content, preflight, evidence, revocation, rollback,
   and cleanup gates, but no real call occurs and `real_provider_e2e` stays false.
7. Focused tests/manual evidence/docs/privacy/path checks and all required
   report-head GitHub checks pass. Broad local suites are not used.
8. One new objective-011 PR only; coding agent never merges/enables auto-merge;
   immutable report topology satisfies `SELF`.

## GitHub and report contract

Commit the unchanged 011-a order and `oap/active=011-a` with the implementation,
push the required new branch, and create exactly one non-draft PR against
`main` with the exact title. Inspect actual checks and repair only in-scope
failures. Never merge or enable auto-merge.

Publish exactly one immutable report at
`oap/reports/011-a-codex-cli-gateway-e2e-pilot-readiness.md` with literal
implementation SHA, `Report publication commit: SELF`, exact scenario/results,
safe accounting/privacy/auth facts, disposable DB/Redis/process cleanup, final
verifier output, focused local/GitHub checks, broad suites not run, explicit
real-provider NOT RUN, documentation impact, and no-merge/no-auto-merge. The
final commit changes only that report and has the implementation head as first
parent. Verify remote report head, then signal exact `OK`.

