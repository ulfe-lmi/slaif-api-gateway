# OAP Work Order — 009-a

## Objective

Make pinned Codex CLI 0.147.0 sessions economically usable beyond the legacy
workshop-sized output default while remaining strictly bounded: add explicit
route/model context and output limits, conservative cache-write/reasoning/
long-context accounting, and a safe same-key remote-compaction round trip on
one new objective-009 PR.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote default branch: `main`.
- Starting remote `main`:
  `635f20f6ca9efdc66d13f56bacb2193d00340de3`, merge commit for PR #233.
- Objective dependencies 005 through 008 are merged. Objective 008 added strict
  Codex tool/reasoning replay and migration head
  `0013_codex_replay_references`.
- PR mode: `CREATE_NEW_PR`.
- Create exactly one new PR from current remote `main`.
- Required branch:
  `oap/009-codex-context-output-cache-compaction-accounting`.
- Required PR title:
  `[OAP 009] Bound Codex context, cache, compaction, and accounting`.
- No existing PR was found for that exact branch at activation.
- The only unrelated open PR is Dependabot #224. Do not modify or reuse it.
- The primary worktree is clean. Preserve ignored
  `.local-provider-catalog/` and every unrelated worktree/artifact.
- Frozen Codex fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.

GitHub is authoritative. Reconcile all of this again before editing. If a
different objective-009 PR or divergent main exists, stop and report it.

## Pinned protocol and pricing evidence

Use the installed `/usr/bin/codex` only if its version is exactly `0.147.0` and
the pinned source checkout remains exactly:

```text
tag: rust-v0.147.0
commit: be6e8eac029b183056b7e4402879f15d2c85f61b
checkout: /tmp/slaif-oap005-codex-source-YSOVKH
model: gpt-5.6-sol
wire API: responses
auth profile: API key through the custom SLAIF provider
```

Pinned source establishes these facts:

- `ResponseCompletedInputTokensDetails` parses both `cached_tokens` and
  `cache_write_tokens`; Codex exposes reasoning output separately.
- API-key custom-provider Responses calls use `Compression::None`. Zstd request
  compression is limited to the Codex backend/OpenAI-provider path.
- Codex reuses its session ID as `prompt_cache_key` across root/subagent turns.
- the provider defaults to remote compaction; V1 uses unary
  `POST /v1/responses/compact`, and its compact request shares model, history,
  instructions, tools, `parallel_tool_calls`, reasoning, prompt-cache key, and
  text controls with ordinary Responses while omitting ordinary-only fields;
- compact output is an `output` array containing an opaque `compaction` item
  that Codex replays in later Responses history.

Official OpenAI documentation checked at activation records for
`gpt-5.6-sol`: 1,050,000 context tokens, 128,000 maximum output tokens, standard
prices of USD 5/M input, USD 0.50/M cached input, and USD 30/M output; prompts
over 272,000 input tokens use 2x input and 1.5x output pricing for the full
request; cache writes cost 1.25x uncached input. Treat these as qualification
test data, not hardcoded universal provider truth. Objective 010 owns the
operator/model-profile materialization.

Primary references:

```text
https://developers.openai.com/api/docs/models/gpt-5.6-sol
https://developers.openai.com/api/docs/guides/latest-model
```

Do not use current unpinned Codex behavior to silently widen the 0.147.0
contract. Do not call a real provider in this objective.

## Strategic decisions

1. Ordinary non-Codex Responses and Chat behavior keep their current global
   defaults. Larger limits are available only through the complete Codex key
   gates plus strict numeric route metadata and operator-configured absolute
   Codex ceilings.
2. An omitted Codex `max_output_tokens` must no longer become the legacy 1,024
   default. Use a conservative explicit Codex route default (qualification
   value 32,768), bounded by both the route maximum and an operator absolute
   ceiling. Never forward an unbounded request.
3. Admission must enforce `estimated input + effective maximum output <= route
   context window`; malformed/missing/unknown numeric metadata fails before
   Redis, pricing, quota, or provider work. No silent clamp.
4. Cache reads, cache writes, uncached input, ordinary output, reasoning output,
   and configured long-context tiers are disjoint accounting dimensions.
   Reservation uses the maximum plausible configured price; actual provider
   usage finalizes exact supported components. Missing required prices or
   inconsistent/unknown billable token dimensions fail closed.
5. `prompt_cache_key` remains transient only. No key, message/history content,
   cache key, raw request, compact payload, or raw usage body enters logs,
   audits, metrics labels, exports, reports, or new content storage.
6. Qualify the dedicated V1 remote compact endpoint. Keep V2
   `compaction_trigger` unsupported and document/configure objective 010 to
   disable that client feature for the SLAIF profile.
7. Add a default-off `codex_compaction` capability. A compact call requires the
   endpoint/model/provider permissions plus every prior Codex gate and this new
   key/route gate. It never grants hosted tools or gateway tool execution.
8. A returned compact item becomes reusable only after its request has final
   provider usage and finalized PostgreSQL accounting, before the HTTP success
   is returned. Bind it to the same key/provider/upstream model and an explicitly
   compatible Responses/compact route using a versioned HMAC over both its
   provider item ID and opaque encrypted content. Store neither raw value.
9. The intended API-key profile is uncompressed. Reject non-identity request
   content encodings safely; do not add transparent zstd decompression.

## Required implementation

### A. Route/model context and output limits

- Define one strict documented numeric metadata object alongside (not inside)
  the existing boolean Responses capability registry. It must carry positive
  integer context window, default output, and maximum output values with
  `default <= maximum < context`, reject booleans/floats/strings/unknown keys,
  and be meaningful only when the complete Codex envelope gate is active.
- Add explicit safe operator absolute Codex input/output ceilings with
  conservative defaults sufficient for the qualified 1.05M/128K model. Never
  raise existing ordinary endpoint defaults implicitly.
- After route resolution but before Redis/pricing/quota/provider, replace only
  an injected legacy default with the validated route Codex default, reject an
  explicit request above the route/operator maximum, and reject the estimated
  input plus output exposure above the route context window.
- Recompute every policy/reservation value from the final effective request;
  upstream body, quota tokens, cost estimate, and ledger evidence must agree.
- Add boundary tests for missing/unknown/malformed metadata, 1,024 regression,
  exact 32,768 qualification default, exact maximum, maximum+1, context edge,
  and ordinary non-Codex behavior unchanged.

### B. Cache, reasoning, and long-context accounting

- Parse non-negative `input_tokens_details.cache_write_tokens` on unary and
  streaming provider usage and carry it as safe typed usage/accounting data.
- Strictly partition provider input into cached-read, cache-write, and ordinary
  uncached tokens. Their sum may not exceed provider input tokens. Reasoning
  remains a subset of provider output. Malformed, negative, boolean, overflow,
  contradictory, or unknown configured billable dimensions fail safely.
- Extend the existing pricing result/estimate contract using validated
  `pricing_metadata` (no guessed defaults) for cache-write price/multiplier and
  long-context threshold/input/output multipliers. Reject partial, unknown,
  non-decimal, negative, or internally inconsistent Codex pricing metadata.
- Admission must reserve all estimated input at the maximum applicable
  ordinary/cache-write/long-context rate and all possible output/reasoning at
  the maximum applicable output/long-context rate. Cached-read discounts are
  actual-finalization benefits, never optimistic admission assumptions.
- Actual cost must charge the disjoint supported components exactly and apply
  the long-context tier to the full request when provider input exceeds the
  configured threshold. Persist only safe counts, costs, tier/multiplier IDs or
  values, warnings/status, and existing pricing/FX provenance.
- Preserve existing provider-reported OpenRouter authority rules and existing
  non-Codex fallback behavior unless a malformed known dimension would make
  final cost unsafe. Never claim provider invoice equivalence.
- Add matrices for below/at/above 272K, cached read, cache write at 1.25x,
  reasoning, mixed components, missing prices, contradictory components,
  quota exhaustion across multiple turns, and actual-finalization overrun.

### C. Safe Codex V1 remote compaction

- Add exact default-off `codex_compaction` key/template/route vocabulary with
  dependencies on `codex_request_envelope`, `codex_client_tools`,
  `codex_streaming_tool_events`, and `codex_encrypted_reasoning_replay`.
- Expand only the gated `/v1/responses/compact` request path to accept and
  canonicalize the exact pinned compact fields/history. Reuse the already
  hardened message/tool/reasoning/compaction replay validators and byte/token
  caps. Continue to reject store/stream/include/tool-choice/background,
  provider-hosted tools, MCP, V2 triggers, stateful provider IDs, and unknown
  fields.
- Verify all prior reasoning/tool/compaction history HMAC ownership before
  Redis, pricing, quota, or provider work. A compact route may differ in route
  row ID from the ordinary Responses route only through an explicit narrow
  same-provider/same-upstream-model compact compatibility rule; no general
  route relaxation is allowed.
- Strictly validate the compact provider response as one bounded opaque
  `compaction` output item with a required safe provider ID and non-empty capped
  encrypted content plus final supported usage. Codex may receive the validated
  provider response shape, but SLAIF must not inspect/decrypt/log/store its
  encrypted content.
- After accounting finalization, HMAC the composite item ID + encrypted content
  immediately and persist only versioned digest/ownership/route/expiry metadata
  by extending the objective-008 replay-reference design through a new 0014
  successor. Persistence failure is a charged safe failure and suppresses the
  normal compact success.
- Later `/v1/responses` or gated compact history must prove the composite HMAC
  for the same key/provider/model/compatible route before side effects. Cross-
  key, altered ciphertext, altered ID, expired reference, unavailable HMAC
  version, route/model/provider mismatch, replay mixed with provider state, and
  missing accounting all fail closed without echoing IDs/digests/content.
- Preserve the current non-Codex compact subset honestly; do not call it Codex
  compatible unless the complete new gates and strict history are active.

### D. Compression and harmless qualification harness

- Prove from pinned source and a focused test that the API-key custom-provider
  profile emits ordinary JSON with no request `Content-Encoding`. Add a safe
  ingress negative test for zstd/gzip/unknown content encoding and no body echo.
- Add one executable manual verifier for exact Codex 0.147.0 that binds only a
  numeric loopback address, invokes no real provider, persists no raw payload,
  and exercises a bounded multi-turn sequence including prompt-cache reuse,
  cached/cache-write/reasoning usage, threshold-accounting decisions, one V1
  compact request, returned opaque compaction, and post-compact continuation.
- The mock may expose only fixed safe booleans/counts/types. It must not print or
  write prompts, assistant text, tools, arguments/results, IDs, cache keys,
  encrypted compact/reasoning values, raw headers/bodies, subprocess output, or
  request diffs. It must use only side-effect-free in-memory/local client tools
  already approved by objectives 006–008.
- If exact automatic compaction cannot be induced safely through the installed
  CLI, report that precise blocker instead of substituting a hand-authored
  request and calling it CLI E2E. Pure unit coverage may supplement but not
  falsify the result.

## Schema and documentation

Update `docs/database-schema.md` first/in the same PR for the strict numeric
route/pricing metadata and the 0014 replay-kind/shape change. Preserve one
Alembic head and exact migration/model/schema agreement; never rewrite 0013.

Keep all affected current contracts synchronized, including AGENTS,
accounting, configuration, provider forwarding, security, Responses/Codex
compatibility, compatibility matrix, and live-burn behavior. State clearly:

- 32,768 is a bounded qualification default, not unlimited output;
- 1.05M/128K and pricing multipliers are configured qualified-model data, not
  universal hardcoded facts;
- cache-write/long-context costs are locally calculated and not invoice truth;
- V1 compact is client-managed opaque history, not local content storage;
- V2 compaction/background/hosted tools remain unsupported;
- no real provider or production qualification occurred.

README is not in scope unless the implementation makes its existing top-level
current-status statement materially false. If changed, preserve its exact top
SLAIF logo/link block and justify the change in the report.

## Allowed paths

Implementation may change only these paths:

```text
.env.example
AGENTS.md
app/slaif_gateway/api/openai_compat.py
app/slaif_gateway/config.py
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/codex_replay.py
app/slaif_gateway/providers/base.py
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/schemas/accounting.py
app/slaif_gateway/schemas/policy.py
app/slaif_gateway/schemas/pricing.py
app/slaif_gateway/schemas/providers.py
app/slaif_gateway/services/accounting.py
app/slaif_gateway/services/codex_replay_service.py
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/pricing.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/upstream_payloads.py
app/slaif_gateway/services/upstream_request_contracts.py
docs/accounting.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/streaming-live-burn-margin.md
migrations/versions/0014_codex_context_accounting_compaction.py
oap/active
oap/orders/009-a-codex-context-output-cache-compaction-accounting.md
scripts/verify_codex_context_compaction.py
tests/integration/test_codex_context_accounting_postgres.py
tests/unit/test_accounting_service_finalize.py
tests/unit/test_accounting_service_usage.py
tests/unit/test_alembic_codex_context_accounting_compaction.py
tests/unit/test_codex_context_accounting.py
tests/unit/test_codex_replay_service.py
tests/unit/test_config.py
tests/unit/test_db_models_accounting.py
tests/unit/test_key_template_service.py
tests/unit/test_openai_provider_adapter.py
tests/unit/test_openai_provider_streaming.py
tests/unit/test_pricing_service.py
tests/unit/test_provider_streaming_sse.py
tests/unit/test_responses_codex_compaction.py
tests/unit/test_responses_codex_multiturn_replay.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_route_capabilities.py
tests/unit/test_upstream_payload_reconstruction.py
```

Final report-only commit adds only:

```text
oap/reports/009-a-codex-context-output-cache-compaction-accounting.md
```

If a genuinely required implementation/test contract lies outside this list,
do not edit it. Publish a `BLOCKED` report naming the exact file and reason so a
narrow 009-b continuation can authorize it. Do not touch dependencies, CI,
deployment, frozen fixtures/capture evidence, prior OAP history, README without
the exception above, provider catalogs, admin UI, or unrelated paths.

## Focused verification and test economy

Run the smallest evidence set that proves the affected boundary:

- new context/accounting/compact unit files plus directly affected existing
  pricing/provider/policy/replay/route/template files;
- the new migration test and exactly one new disposable-PostgreSQL integration
  file against an explicitly named `TEST_DATABASE_URL` database;
- one Alembic upgrade/downgrade/re-upgrade through 0014 and `alembic heads`;
- the exact harmless manual Codex verifier once, after pure tests pass;
- focused OAP/documentation contract tests, scoped Ruff/compile, fixture digest,
  `git diff --check`, exact path set, and PR/check inspection.

Do not run full unit, integration, E2E, browser, Docker/Compose, or HPC suites
locally. GitHub CI supplies routine broad coverage. Never use `DATABASE_URL` for
destructive testing. Never install PostgreSQL packages. Never call a real
provider or external tool/service.

Record literal commands, test counts, safe database name/lifecycle, installed
Codex/source identity, verifier output keys, every skipped/not-run suite, and
all failures honestly. Skipped, missing, pending, cancelled, neutral, blocked,
and not-run checks are not passes.

## Acceptance criteria

1. Gated Codex requests use strict route/operator context and output bounds; an
   omitted maximum no longer becomes 1,024, and ordinary behavior is unchanged.
2. Reservation/finalization safely cover cache read/write, ordinary input,
   ordinary/reasoning output, and configured long-context tier dimensions;
   malformed/unknown required pricing or usage fails closed.
3. Prompt-cache/history/tool schema bytes remain conservatively metered and no
   prohibited value enters persistence, evidence, logs, errors, or exports.
4. Exact default-off V1 compact gating, canonical request/response handling,
   finalized accounting, HMAC-only same-key replay, expiry, and route/model
   compatibility pass positive and adversarial tests.
5. Non-identity compression fails safely; pinned API-key Codex remains proven
   uncompressed and no decompression feature is added.
6. The exact harmless Codex verifier completes its bounded cache/compact/
   continuation sequence, or the report is `BLOCKED` with precise non-fabricated
   evidence.
7. Schema/model/migration/docs agree, exactly one 0014 head exists, focused
   tests pass, and the frozen 004 fixture remains unchanged.
8. Exactly one objective PR and only allowed implementation paths; no broad
   local suite, real provider, production credential/data, or side-effecting
   tool.
9. Every final report-head GitHub check is successful. Pending/skipped/missing/
   cancelled/neutral/failed is not green.
10. Coding agent never merges or enables auto-merge; report topology satisfies
    the OAP `SELF` contract.

## GitHub and report contract

Commit the unchanged 009-a order and `oap/active=009-a` with the implementation,
push the required branch, and create exactly one non-draft PR against `main`
with the exact title. Inspect actual GitHub checks and repair only in-scope
failures before reporting.

Publish exactly one immutable report at
`oap/reports/009-a-codex-context-output-cache-compaction-accounting.md`. It must
record the literal implementation head SHA, `Report publication commit: SELF`,
PR topology, exact context/pricing/usage/compact/HMAC/compression contracts,
local and GitHub evidence, database lifecycle, privacy review, docs impact,
known limitations, broad suites not run, and explicit no-merge/no-auto-merge.
The final commit changes only that report and has the recorded implementation
head as first parent. Push and verify the remote report head, then signal exact
`OK` to the strategic FIFO. Never merge.

If a safe bounded reservation, exact cost partition, composite compact replay
binding, or real pinned-CLI mock cannot be proven, report `BLOCKED` rather than
weakening the contract.
