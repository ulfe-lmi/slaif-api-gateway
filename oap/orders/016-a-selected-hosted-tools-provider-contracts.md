# OAP Work Order — 016-a

## Objective and business reason

Create the first exact provider-hosted execution contract for OpenAI Responses
native `web_search`, so Objective 017 can activate it through the gateway
without generic hosted-tool passthrough, unknown pricing, content retention, or
ambiguous call counting. This objective qualifies a pure provider contract;
runtime forwarding remains deny-only until Objective 017.

Do not enter a reconnaissance loop. Reconcile once, then begin with
`tests/unit/test_openai_web_search_contract.py` and the new contract service.
Work in small test → implementation → focused-test slices. Read another file
only for a concrete imported symbol, contract dependency, or failing test.

## Verified current state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main`: `181a23be25a9c636127a756c86bd2d9c8477c971`, merge of
  Objective 015 PR #240.
- Objective 015 is terminally merged; its fence, full-balance reservation,
  accounting hold, manual reconciliation, ordinary-admission blocking, and
  concurrency evidence are present on `main`.
- The only unrelated open PR is Dependabot PR #224; do not reuse or modify it.
- The only release is `v0.1.0-rc.1`; no release/production claim follows.
- Current runtime still denies all provider-hosted tools before provider
  forwarding. Existing policy vocabulary includes `provider_web_search`,
  `provider_remote_mcp`, and `provider_connector`; only web search is selected
  here.
- Current pricing rows already have `pricing_metadata`; no migration is needed.
- Project pins `openai==2.41.0`. Official OpenAI documentation checked on
  2026-08-20 defines the canonical new Responses tool as `web_search`, a
  top-level `max_tool_calls` cap, `web_search_call` output items, and per-call
  web-search pricing plus model-priced search-content tokens.
- Official docs also define remote MCP/connector authorization, approval,
  tool-list/call output, and destination risks. Those surfaces are explicitly
  excluded here because credential, approval/state, destination, and external
  service-cost contracts are not yet complete.
- The primary checkout contains unrelated human/strategic governance changes
  in `AGENTS.md`, `OAP-COMMUNICATION-coding-agent.md`,
  `ARCHITECTURE-for-agents.md`, and `oap/strategic-instructions/`. Preserve them
  byte-for-byte and do not stage them. Use a fresh clean linked worktree from
  the exact remote `main`, then copy only this activated order and
  `oap/active` into the objective branch unchanged.

Official contract sources:

- <https://developers.openai.com/api/docs/guides/tools-web-search>
- <https://developers.openai.com/api/reference/resources/responses/methods/create>
- <https://developers.openai.com/api/docs/pricing>
- <https://developers.openai.com/api/docs/guides/tools-connectors-mcp>

## PR contract

- Mode: `CREATE_NEW_PR`
- Base: `main` at the verified SHA above
- Branch: `oap/016-selected-hosted-tools-provider-contracts`
- Title: `[OAP 016] Add the OpenAI hosted web-search contract`
- Create exactly one PR for numeric objective 016. Never merge or enable
  auto-merge. Continuations, if ordered, amend the same PR.

## Allowed paths

```text
app/slaif_gateway/schemas/openai_web_search.py
app/slaif_gateway/schemas/pricing.py
app/slaif_gateway/services/openai_web_search_contract.py
app/slaif_gateway/services/pricing.py
docs/accounting.md
docs/compatibility-matrix.md
docs/database-schema.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
tests/unit/test_openai_web_search_contract.py
tests/unit/test_pricing.py
tests/unit/test_external_tool_policy_contract.py
oap/active
oap/orders/016-a-selected-hosted-tools-provider-contracts.md
```

The final report-only commit may add exactly:

```text
oap/reports/016-a-selected-hosted-tools-provider-contracts.md
```

Do not edit outside this set. If the exact contract requires another
production path, report the blocker; do not widen scope yourself.

## Required implementation

### 1. Exact request contract

Add immutable schemas and a pure service for an already policy-admitted OpenAI
Responses web-search candidate. It must:

- require exactly one canonical hosted declaration with
  `type="web_search"`; reject preview/versioned aliases in this first contract;
- allow only `type` and optional `search_context_size` (`low|medium|high`) in
  that declaration; reject filters, user location, external-web-access
  controls, returned-token-budget controls, arbitrary instructions, and all
  unknown keys;
- require top-level `max_tool_calls` as a real positive integer, never bool,
  bounded by the effective `ExternalToolAdmissionDecision` cap;
- allow coexistence only with client/local declarations already accepted by
  the existing Responses policy; reject duplicate web-search declarations,
  every other hosted type, remote MCP, connectors, and mixed unknown authority;
- require stateless Responses (`store=false`, no background,
  previous-response, conversation, or approval continuation) and neutral
  absent/`auto` tool choice;
- consume the existing key/route policy reducer and require its exact
  `provider_web_search` fenced decision rather than creating parallel policy
  semantics;
- return canonical provider-body facts that contain only the approved
  declaration and `max_tool_calls`; never add gateway state, policy, quota,
  secrets, or diagnostics.

Do not wire this contract into `ResponsesRequestPolicy`,
`responses_gateway.py`, provider adapters, or streaming runtime in this
objective. Existing runtime denial must stay effective.

### 2. Pricing contract without migration

Use the active pricing row's existing `pricing_metadata` with this exact
optional object:

```json
{
  "external_tool_pricing": {
    "openai_web_search_call_price_native": "0.010000000",
    "source": "openai_published_per_call"
  }
}
```

- Parse it strictly and content-free: exact keys, finite non-negative Decimal,
  inherited pricing-row currency, and exact source literal.
- Expose the parsed unit price through safe pricing/service schemas without a
  database migration or public admin/API behavior change.
- Missing/malformed/negative/unknown pricing must fail closed for the selected
  contract, while ordinary non-hosted pricing behavior stays unchanged.
- Provide deterministic helpers for maximum tool fee
  (`max_tool_calls * unit price`) and actual tool fee
  (`completed_call_count * unit price`). Search-content tokens remain part of
  provider token usage/model pricing; do not invent a second token source.

### 3. Official output/event accounting contract

Parse official-shape non-streaming output and streaming event sequences into
safe, content-free evidence:

- recognize `web_search_call` items and
  `response.web_search_call.in_progress`, `.searching`, and `.completed`
  events plus matching output-item completion;
- count each unique successfully completed call exactly once even when both a
  specific completed event and `response.output_item.done` are present;
- enforce the admitted maximum, bounded IDs/indexes/sequence numbers, coherent
  lifecycle, and final completed status;
- treat failed, duplicate-conflicting, cap-exceeding, malformed, incomplete,
  or missing-terminal evidence as non-authoritative and requiring an
  accounting hold;
- validate action shape only enough to recognize official `search`,
  `open_page`, and `find_in_page`; never return, log, persist, or include in
  safe evidence the queries, URLs, sources, patterns, citations, arguments,
  results, or response text;
- expose only low-cardinality facts: provider, capability, admitted cap,
  completed-call count, pricing source, unit/total tool fee, authoritative
  boolean, and safe reason code.

No raw provider response, SSE payload, search content, or identifiers may be
stored by this contract.

### 4. Documentation truth

Update affected contracts to say:

- OpenAI Responses web-search is provider-contract-qualified only; production
  gateway forwarding remains denied pending Objective 017;
- the supported initial shape and exact excluded controls;
- per-call fee plus provider-reported token accounting, full-balance fenced
  admission, possible one-request overrun, and hold-on-unknown evidence;
- remote MCP/connectors and every other hosted family remain denied;
- no prompt, query, URL, source, result, tool content, OAuth token, or provider
  secret is persisted.

Remove stale statements that Objective 015 hold/reconciliation is unimplemented,
but do not claim Objective 017 E2E, real-provider qualification, production
readiness, or remote-MCP support.

## Explicit non-goals

- No runtime request admission/forwarding activation and no provider call.
- No remote MCP, connector, OAuth, approval continuation, server URL, tunnel,
  domain filter, user location, source/result include, file search, code
  interpreter, hosted shell, computer use, image generation, tool search,
  skills, URL fetch, background, or provider-stored state.
- No OpenRouter support or generic provider abstraction claim.
- No migration, new table/column, admin/CLI/browser surface, credential store,
  content retention, Redis change, deployment change, or release claim.
- No full local unit/E2E/browser/HPC suite.

## Acceptance criteria

1. Canonical web-search request facts and upstream reconstruction are exact,
   cap-bound, policy-bound, stateless, and content/secret-free.
2. Every unsupported/unknown/mixed hosted shape fails in the pure contract;
   the live gateway remains deny-before-reservation/provider-forwarding.
3. Exact pricing metadata provides maximum and actual per-call fee arithmetic;
   missing or malformed tool pricing fails closed without affecting ordinary
   pricing.
4. Official non-stream and stream fixtures count completed calls once, enforce
   the cap, and turn ambiguous/missing/failed evidence into a hold-required
   result with no raw content in safe evidence/errors.
5. Remote MCP/connectors and all unselected hosted families remain denied and
   documented as unsupported.
6. Scope is one new PR, no migration/provider call/runtime activation, focused
   tests and final CI are green, and report topology is exact.

## Verification

Run only focused local checks:

```text
.venv/bin/python -m pytest \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_external_tool_policy_contract.py \
  tests/unit/test_pricing.py -q -ra
.venv/bin/python -m compileall -q \
  app/slaif_gateway/schemas/openai_web_search.py \
  app/slaif_gateway/schemas/pricing.py \
  app/slaif_gateway/services/openai_web_search_contract.py \
  app/slaif_gateway/services/pricing.py
```

Run scoped Ruff only if the repository environment provides it, plus
`git diff --check`, allowed-path verification, and relevant documentation
checks. Do not install/run a broad suite merely to obtain Ruff. Let standard
GitHub CI provide broad routine coverage.

Required negative/privacy evidence includes malformed prices, bool/zero/
over-cap counts, duplicates, preview/unknown types, forbidden optional fields,
MCP/connectors, mixed authority, lifecycle conflicts, cap overflow, missing
terminal evidence, and private-canary queries/URLs/tokens absent from every
safe result, exception, repr, log capture, and documentation fixture.

## Safety and publication

Use no production/provider credentials, real upstream calls, external MCP
server, or production data. Preserve unrelated worktree changes. Commit/push
the implementation to the named branch, create the unique PR, and wait for
required checks. Publish exactly one immutable
`oap/reports/016-a-selected-hosted-tools-provider-contracts.md` recording the
literal implementation head and `Report publication commit: SELF`. The final
report-only commit must parent the implementation head and change only the
report. Verify remote PR head, then signal exact `OK` on `response.fifo` and
return to the control FIFO. Never merge.
