# OAP Work Order — 017-b

## Objective

Amend PR #242 to close the phase-gate gaps found in independent review:
pre-Redis pricing order, exact route identity, pre-provider fence cleanup,
post-provider hold completeness, bounded official hosted streaming, consistent
tool-fee FX, and real PostgreSQL gateway evidence for concurrency, overrun,
hold, reconciliation, and streaming. Do not expand beyond OpenAI Responses
`web_search`.

Stop reconnaissance. Start with focused failing tests for pricing-before-Redis,
exact route ID, streaming adapter construction, and streaming hold metadata;
then implement in small slices. Read another file only for a concrete symbol or
failing test.

## Verified state

- Sole Objective 017 PR: #242 on
  `oap/017-external-tool-security-accounting-e2e`.
- 017-a implementation:
  `e96fb0580df4efe8daa0d545813317400b9293b0`.
- 017-a report head:
  `55e38c12e8679df89e89a72d383b7a4a32db0da5`.
- Report topology is valid; all ten report-head checks pass; no reviews or
  auto-merge exist. Prior artifacts are immutable.
- The OpenAI-client E2E proves one non-stream happy path. The new PostgreSQL
  file calls fence/hold services directly and does not exercise the gateway.
  No test proves runtime same-key concurrency, overrun/next admission,
  gateway-created hold/reconciliation, or hosted streaming.

## Required repairs

### Admission and identity

1. A hosted candidate must complete strict active-pricing lookup and external-
   tool pricing validation before Redis reservation, fence mutation, or provider
   construction/call. Pass the validated pricing facts forward; do not perform a
   second mutable lookup after Redis.
2. `max_tool_calls` is valid only with the one canonical admitted web-search
   declaration. Reject it for no tools, local-only tools, denied/malformed
   hosted tools, input-token count, compact, and every other endpoint before
   forwarding.
3. Fence acquisition must use the exact resolved route UUID (normalizing UUID
   object/string only). Missing or malformed route identity fails closed. Remove
   the fallback query by model/pattern/provider because it can bind a different
   route.
4. Reuse the exact reducer decision rather than fabricating a parallel positive
   decision after validation. If a schema change is needed to carry immutable
   decision facts, keep it content-free.

### Transaction and failure semantics

5. Distinguish provider-not-started from provider-started:
   - adapter/provider construction failure before any upstream call must
     atomically create the safe failed/released ledger, clear full reserved
     counters, and resolve the fence using exact terminal evidence;
   - after forwarding/stream iteration starts, provider error, malformed or
     missing usage/call/cost evidence, disconnect, cancellation, accounting
     failure, fence-resolution failure, or unexpected transaction uncertainty
     must roll back partial finalization and atomically place one durable hold.
6. All hosted hold calls must pass the true streaming flag. Streaming failures
   create `streaming=true` held ledgers; non-stream failures remain false.
   Idempotent repeated failure handling must not create a second ledger/audit.
7. Hold partial estimate must conservatively include model estimate plus the
   admitted maximum tool fee converted with the same pricing/FX facts; do not
   understate known maximum exposure.
8. Successful model+tool cost uses the reservation's exact pricing currency and
   FX rate/facts. Do not perform a later FX lookup that can select a different
   rate. Preserve correct native and EUR totals/component labels.
9. Finalization, one ledger, zero counters, and fence resolution remain one
   atomic transaction. Any exception before commit leaves the original pending
   reservation/fence available for the hold transaction.

### Bounded official streaming

10. Replace the unbounded list of synthetic event dictionaries with a bounded
    incremental web-search tracker or equivalently bounded sanitized state.
    Enforce Objective-016 ID/index/sequence/action bounds, lifecycle order,
    unique IDs, admitted cap, and a hard event/state count derived from the cap.
    Never store raw action/query/URL/source/result/text/usage bodies.
11. Validate the actual provider `web_search_call` action before discarding it;
    do not replace arbitrary provider action content with a fabricated
    `{type:"search"}` fact.
12. Support normal official response/message output-item events and text deltas
    that accompany a web-search stream. If ordinary client-tool streaming is
    supported with the web profile, compose validators safely; otherwise reject
    that combination at request policy before Redis/provider work and document
    the exact limitation. Codex `additional_tools` plus hosted tools remains
    denied.
13. Hold `response.completed`/`[DONE]` until authoritative usage, completed-call
    count/fee, atomic finalization, and fence resolution. Malformed/unknown/
    excessive events emit a safe error and create a streaming hold.

## Required gateway evidence

Expand the focused PostgreSQL integration file so it exercises real gateway
services/ASGI with official-shape mocked OpenAI provider behavior, not only
direct fence/hold primitives. Prove:

- strict key, route/provider/cap mismatch, missing/malformed pricing, remote
  MCP, and `max_tool_calls` without web search cause zero Redis/fence/provider
  mutation;
- one allowed non-stream request reserves the full remaining balance, forwards
  only canonical body/server authorization, finalizes exact model tokens plus
  call fee, writes one content-free ledger/audit, and clears the fence;
- a blocking provider mock makes a concurrent same-key request fail while an
  independent key remains usable;
- a permitted actual cost/token overrun completes once, then both ordinary and
  hosted following admissions fail without new reservation/provider mutation;
- provider error after call start, missing usage, malformed/missing call
  evidence, and unexpected finalization/resolve failure each yield exactly one
  held fence/ledger with full reservation; following auth/admission fails;
- existing audited `finalize-actual` and `release-no-charge` reconciliation
  unblock or exhaust the key exactly as documented, with one audit and exact
  counters;
- an official hosted stream forwards intermediate web-search/message/text
  events, counts one call once, withholds completion until atomic success, and
  stores no content; malformed event and client disconnect produce a streaming
  hold and no success terminal;
- Redis concurrency reservation/heartbeat is released on every terminal,
  denial, error, hold, and disconnect path while never becoming quota truth.

Use private canaries in prompt/query/URL/source/result/action/ID/provider error
and assert absence from errors, logs, ledger/audit metadata, reports, and safe
export/detail projections.

## Allowed paths

```text
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/schemas/openai_web_search.py
app/slaif_gateway/schemas/responses_external_tool.py
app/slaif_gateway/services/accounting.py
app/slaif_gateway/services/openai_web_search_contract.py
app/slaif_gateway/services/responses_external_tool_runtime.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
docs/accounting.md
docs/compatibility-matrix.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/runbooks/external-tool-hold-reconciliation.md
tests/e2e/test_openai_python_client_responses.py
tests/integration/test_responses_external_tool_postgres.py
tests/unit/test_openai_web_search_contract.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_usage_report_service.py
tests/unit/test_v1_responses_quota.py
oap/active
oap/orders/017-b-close-runtime-transaction-streaming-and-evidence-gaps.md
```

Final report-only commit may add:

```text
oap/reports/017-b-close-runtime-transaction-streaming-and-evidence-gaps.md
```

No migration, remote MCP/connector, other hosted family, OpenRouter hosted
support, real provider, production, admin/RBAC, or deployment change.

## Verification

Run focused unit files affected by the repair, not the entire unit suite:

```text
.venv/bin/python -m pytest \
  tests/unit/test_responses_request_policy.py \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_responses_codex_streaming_tools.py \
  tests/unit/test_v1_responses_quota.py \
  tests/unit/test_usage_report_service.py -q -ra
```

Create one safe disposable PostgreSQL database and run the required gateway
integration file with zero skips:

```text
TEST_DATABASE_URL=<safe-disposable-url> .venv/bin/python -m pytest \
  tests/integration/test_responses_external_tool_postgres.py -q -ra
```

Run only the Responses OpenAI-client E2E file/group needed for hosted behavior;
zero required skips. Run scoped Ruff/compileall, `git diff --check`, path-scope
and docs checks. Do not run the full local suite, browser suite, Compose suite,
or HPC harness; final GitHub CI supplies broad routine coverage.

The report must give exact test names/counts and state which assertions prove
each admission/concurrency/overrun/hold/reconciliation/streaming/Redis/privacy
criterion. Do not describe a direct fence-service test as gateway E2E.

## PR and report protocol

Use existing PR #242/branch and create no PR. Commit this order and exact
`oap/active=017-b` unchanged. Publish one immutable
`oap/reports/017-b-close-runtime-transaction-streaming-and-evidence-gaps.md`
with literal implementation SHA and `Report publication commit: SELF`; the
report-only commit must parent the implementation head and change only the
report. Verify final remote head, checks, and reviews; signal exact `OK`; return
to control FIFO; never merge/auto-merge.
