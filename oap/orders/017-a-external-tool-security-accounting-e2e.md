# OAP Work Order — 017-a

## Objective and business reason

Activate the Objective-016 OpenAI Responses `web_search` contract through the
real gateway and close the Phase-2 external-tool promise end-to-end: default
denial before provider work; exact per-key/per-route opt-in; exclusive
PostgreSQL fence; full-balance reservation; provider token plus per-call fee
finalization; one-request overrun and following-request rejection; durable hold
for unknown outcomes; safe reconciliation; content-free audit/reporting; and
no confusion with existing client/Codex-local tools.

This is the final planned external-tool objective before strategic evaluation.
It does not authorize remote MCP/connectors or any other hosted family.

Do not enter reconnaissance. Reconcile once, then start with a failing focused
gateway test for strict-key denial and allowed non-stream web search, followed
by the smallest runtime slice. Work test → implementation → focused test. Read
another file only for a concrete symbol, transaction boundary, or failing test.

## Verified current state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main`: `13615984d5b5da824f498eaa6c9237aff0f87ac0`, merge of
  Objective 016 PR #241.
- Objective 016 qualifies only OpenAI Responses canonical `web_search` request,
  pricing, official output/event, action, provider, terminal, and privacy
  contracts. Its runtime remains deny-only.
- Objectives 014–015 provide the exclusive fence/full-balance reservation,
  hold, manual reconciliation, ordinary admission blocking, and concurrency
  foundations.
- Existing Responses runtime performs policy, route, Redis, ordinary quota,
  provider forwarding, typed SSE validation, and accounting, but rejects hosted
  tools. It must retain ordinary behavior for non-hosted requests.
- Existing key/template/route admin and CLI surfaces persist the canonical v1
  external-tool policy. No migration is required.
- The only unrelated open PR is Dependabot #224. The only release remains
  `v0.1.0-rc.1`; no release/production claim follows.
- The primary checkout contains unrelated human/strategic governance files;
  preserve them. Objective 016 used linked worktree
  `/home/ubuntu/codex-work/slaif-api-gateway-oap-016-a`; do not continue on its
  merged branch. Create a new clean linked worktree
  `/home/ubuntu/codex-work/slaif-api-gateway-oap-017-a` from exact remote main
  and copy this order plus `oap/active` into it byte-for-byte.

Official OpenAI contracts checked for this phase:

- <https://developers.openai.com/api/docs/guides/tools-web-search>
- <https://developers.openai.com/api/reference/resources/responses/methods/create>
- <https://developers.openai.com/api/docs/pricing>
- <https://developers.openai.com/api/docs/guides/tools-connectors-mcp>

## PR contract

- PR mode: `CREATE_NEW_PR`
- Base: `main` at `13615984d5b5da824f498eaa6c9237aff0f87ac0`
- Branch: `oap/017-external-tool-security-accounting-e2e`
- Title: `[OAP 017] Activate and prove OpenAI hosted web search`
- Create exactly one PR for numeric objective 017. Never merge or enable
  auto-merge. Any continuation amends that same PR.

## Allowed paths

```text
app/slaif_gateway/api/external_tool_errors.py
app/slaif_gateway/cli/routes.py
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/schemas/openai.py
app/slaif_gateway/schemas/openai_web_search.py
app/slaif_gateway/schemas/responses_external_tool.py
app/slaif_gateway/services/accounting.py
app/slaif_gateway/services/admin_key_dashboard.py
app/slaif_gateway/services/openai_web_search_contract.py
app/slaif_gateway/services/responses_external_tool_runtime.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/upstream_payloads.py
app/slaif_gateway/services/upstream_request_contracts.py
docs/accounting.md
docs/compatibility-matrix.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/runbooks/external-tool-hold-reconciliation.md
tests/e2e/test_openai_python_client_responses.py
tests/integration/test_responses_external_tool_postgres.py
tests/unit/test_admin_keys_dashboard_service.py
tests/unit/test_cli_routes.py
tests/unit/test_openai_web_search_contract.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_usage_report_service.py
tests/unit/test_v1_responses_quota.py
oap/active
oap/orders/017-a-external-tool-security-accounting-e2e.md
```

The final report-only commit may add exactly:

```text
oap/reports/017-a-external-tool-security-accounting-e2e.md
```

If a required symbol lives outside this list, report a blocker rather than
widening scope. No migration path is authorized.

## Required implementation

### 1. Candidate parsing and exact admission order

- Add `max_tool_calls` to the bounded Responses create schema/field registry.
- Extend `ResponsesRequestPolicy` with an explicit internal flag that permits
  only the Objective-016 canonical web-search candidate shape while default
  callers remain deny-only. It may coexist with already validated ordinary
  local function/custom declarations, but not Codex `additional_tools` in the
  same request.
- After authentication and ordinary request-shape validation, resolve the
  route, then call the exact Objective-016 contract using:
  authenticated key external policy, route `capabilities.external_tools`,
  finite key limits, installation ceilings, OpenAI provider, and the canonical
  body. Key/route/provider/cap/count/overrun mismatch denies before Redis,
  PostgreSQL reservation/fence mutation, or provider forwarding.
- Keep `strict_bounded`, missing/malformed historical metadata, preview aliases,
  filters/location/live-web/returned-token controls, remote MCP/connectors,
  all other hosted tools, unknown authority, state/background/approval, and
  non-OpenAI routes denied.
- Build the upstream body from existing canonical ordinary fields plus exactly
  the qualified hosted fragment. Never forward gateway policy, key metadata,
  quota/fence facts, pricing, secrets, or diagnostics.

### 2. Pricing and exclusive admission

- Resolve the active model pricing row before mutation and strictly require
  Objective-016 `external_tool_pricing`; missing/malformed pricing fails before
  fence/provider work.
- Compute the bounded maximum tool fee for safe evidence, but acquire the
  existing PostgreSQL full-remaining-balance fence/reservation—not an ordinary
  quota reservation and not merely the estimated fee.
- Use exact route/provider/capability facts and no destinations for web search.
  Commit acquisition before provider forwarding. Redis remains operational
  rate/concurrency coordination only; PostgreSQL is the sole hard authority.
- Map fence/contract failures to fixed OpenAI-compatible errors without raw
  request, provider, pricing, or tool content.

### 3. Non-stream success/failure accounting

- On a successful OpenAI response, require provider usage and authoritative
  Objective-016 call evidence. Compute model token cost using existing pricing,
  add exact completed-call fee, convert consistently to EUR, and finalize the
  fenced reservation/ledger with safe component metadata.
- In the same database transaction, resolve the fence only after terminal
  reservation, exactly one ledger, zero reserved counters, and exact bound
  facts. A successful request may exceed remaining quota; the next request
  must then fail ordinary quota admission.
- Store only low-cardinality external-tool metadata: contract version,
  capability, admitted cap, completed count, pricing source, unit/total native
  fee, cost source/confidence, and overrun facts. Never store provider output,
  response items, queries, URLs, sources, citations, action content, IDs,
  prompts, or credentials.
- After provider forwarding begins, provider error, missing usage, missing or
  non-authoritative call/cost evidence, malformed response, disconnect, or
  finalization uncertainty must atomically transition the active fence to the
  existing durable hold with the safest exact reason/evidence quality and keep
  the full reservation. Never release as zero-cost failure merely because the
  final cost is unknown.

### 4. Streaming

- Extend request-scoped Responses SSE validation with an explicit web-search
  profile. Accept only the official web-search lifecycle/output-item events
  qualified in Objective 016 alongside existing safe text events.
- Track lifecycle incrementally with bounded in-memory IDs/indexes/sequence and
  content-free counters; do not buffer raw events, queries, URLs, results, or
  response content to calculate fees. Avoid specific-event/output-item double
  counting.
- Hold `response.completed`/`[DONE]` until authoritative provider usage,
  authoritative call evidence, custom cost finalization, and fence resolution
  all succeed. Forward supported intermediate events without persisting them.
- Provider failure, unsupported/malformed event, missing usage/call/cost
  evidence, client disconnect, or accounting failure after forwarding begins
  emits a safe typed error, suppresses normal completion, and places a durable
  hold. Use cancellation shielding where needed so disconnect cannot skip the
  hold transaction.

### 5. Operator/user evidence and separation

- Existing admin/CLI key/route summaries must state web-search runtime is
  available only for the exact OpenAI fenced contract; strict keys and all
  other hosted families remain denied. Do not claim generic hosted-tool/MCP
  support.
- Usage/report projections expose only the safe low-cardinality tool accounting
  facts and remain spreadsheet/log/content safe.
- Update docs/runbook for deny, allow, one-request overrun, concurrent block,
  hold, manual reconciliation, and exact limitations.
- Prove client/local function/custom and Codex-local tools keep their ordinary
  independent behavior. A key may permit both policy classes in separate
  requests, but Codex `additional_tools` plus hosted `tools` in one request
  remains denied. The gateway never executes client tools.

## Explicit non-goals

- No remote MCP, connectors, OAuth/authorization, server URL/tunnel, approval
  continuation, domain filter, user location, sources/results include, file
  search, code interpreter, shell, computer, image generation, tool search,
  skills, URL fetch, background, or provider-stored state.
- No OpenRouter hosted-tool claim, generic provider abstraction, real provider
  call, production credential/data/deployment, or external service.
- No schema migration, new table/column, new credential store, content logging,
  invoice guarantee, exact mid-request interruption claim, or release claim.
- No full local unit/E2E/browser/HPC matrix.

## Acceptance criteria

1. Strict/malformed/key/route/provider/pricing/cap/unknown/remote-MCP cases fail
   before Redis reservation, PostgreSQL mutation, or provider invocation.
2. An exact allowed non-stream request acquires the full-balance fence, forwards
   only canonical fields with server provider auth, finalizes provider tokens
   plus exact per-call fee, writes one content-free ledger, and clears the
   fence atomically.
3. While the provider call is unresolved, concurrent authentication/admission
   for the same key fails; another key remains independent.
4. A permitted request may overrun; after finalization the fence clears and the
   next ordinary or hosted request fails normal quota admission without new
   mutation/provider work.
5. Missing/ambiguous usage, cost, call evidence, provider error, malformed SSE,
   and disconnect create one durable held fence/ledger with full reservation;
   later requests fail until audited existing reconciliation completes.
6. Streaming forwards official intermediate web-search/text events, counts
   completed calls once, stores no content, and releases terminal success only
   after accounting plus fence resolution.
7. Existing local/Codex tool flows remain independent; remote MCP and every
   unselected hosted family remain denied.
8. Admin/CLI/usage/docs state exact current behavior and limitations; no
   secret/content appears in errors, logs, ledger metadata, audit, reports, or
   exports.
9. One PR, no migration/real provider/production action, focused local evidence
   plus all final-head CI green, no unresolved review, exact report topology.

## Required verification

Use one disposable PostgreSQL database for the new integration file and the
smallest Redis/mock setup already used by Responses tests. Run focused groups,
not the full suite:

```text
.venv/bin/python -m pytest \
  tests/unit/test_responses_request_policy.py \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_responses_codex_streaming_tools.py \
  tests/unit/test_v1_responses_quota.py \
  tests/unit/test_admin_keys_dashboard_service.py \
  tests/unit/test_cli_routes.py \
  tests/unit/test_usage_report_service.py -q -ra

TEST_DATABASE_URL=<safe-disposable-url> .venv/bin/python -m pytest \
  tests/integration/test_responses_external_tool_postgres.py -q -ra

.venv/bin/python -m pytest \
  tests/e2e/test_openai_python_client_responses.py -q -ra
```

The integration/E2E evidence must use official-shape mocked OpenAI responses
and SSE only—no network provider. Include deterministic blocking mock(s) for
same-key concurrency, overrun and next-admission, missing usage/cost/call
evidence, provider error, malformed event, disconnect, hold/reconciliation,
exact DB counters/reservation/fence/ledger/audit, Redis release, header
substitution, and privacy canaries. Do not accept skips in required focused
groups; report environment blockers honestly.

Run scoped Ruff/compileall, `git diff --check`, allowed-path verification, and
relevant documentation checks. Standard GitHub CI supplies broad routine
coverage; do not repeat a full local matrix.

## Safety and publication

Use no real provider, MCP server, OAuth token, provider credential beyond safe
mock configuration, production database, or production system. Preserve all
unrelated worktrees/files. Create/push the named branch and unique PR, inspect
checks, and publish exactly one immutable
`oap/reports/017-a-external-tool-security-accounting-e2e.md` with literal
implementation SHA and `Report publication commit: SELF`. The report-only
commit must parent the implementation head and change only the report. Verify
remote head, signal exact `OK` on `response.fifo`, return to control FIFO, and
never merge/auto-merge.
