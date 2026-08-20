# OAP Work Order — 017-c

## Objective

Own and complete the Objective-017 external-tool phase gate on existing PR
#242. The prior rounds established the happy path and some repairs, but they do
not yet prove or fully implement the promised runtime boundary. You have
implementation autonomy inside the bounded Responses/external-tool subsystem:
design or refactor the transaction state machine, streaming tracker, pricing
flow, helpers, and focused tests as needed to make every acceptance outcome
true—not merely to patch individual review sentences.

Do not restart broad reconnaissance. Read the 017-a/b orders, current diff, the
named runtime/fence/hold/accounting services, and affected tests once; then
implement in coherent test-backed slices. You own routine PostgreSQL/Redis/test
setup and CI-log investigation. Do not ask the human to operate the VM.

## Current authoritative state

- Sole Objective 017 PR: #242,
  `oap/017-external-tool-security-accounting-e2e`.
- 017-b implementation:
  `154f7634f843c66b1fc80289a397b6538f623ac0`.
- 017-b report head:
  `eefb821965537ed31bc11f1eadd1c21915907ca5`.
- Prior order/report commits are immutable. Continue on the same branch/PR.
- 017-b fixed some admission/identity/FX/streaming flags but changed no tests.
  Its report explicitly confirms the PostgreSQL file still exercises direct
  fence/hold services, not the gateway-ASGI/provider runtime matrix required by
  017-b. Therefore the phase gate remains open regardless of green broad CI.

## Problems that must genuinely be solved

Treat these as observed failures, not prescribed implementations:

- base and hosted pricing are still selected in separate lookups; the admitted
  immutable pricing/FX fact can drift;
- `max_tool_calls` is accepted/forwarded without an admitted web-search tool;
- streaming provider-adapter construction still follows ordinary release
  behavior without atomically resolving the external fence;
- exceptions outside the narrow Accounting/Quota handlers can leave an active
  fence rather than the required held outcome after provider execution begins;
- hosted streaming evidence still retains copied action/query content, uses a
  fixed 256-event limit unrelated to the admitted cap, has weaker ID/index
  bounds than the qualified contract, and rejects ordinary message output-item
  events that accompany real Responses streams;
- no real gateway PostgreSQL test proves same-key concurrency, independent-key
  progress, overrun and following admission, runtime-created holds and audited
  reconciliation, hosted streaming success/failure/disconnect, Redis cleanup,
  or privacy persistence;
- the report must not use service-only primitives or broad unrelated CI as a
  substitute for those exact gateway outcomes.

## Implementation autonomy

Choose the cleanest internal design. You may:

- refactor the external-tool branch of `responses_gateway` into cohesive
  request-scoped helpers/state objects;
- extend existing fence/hold/accounting/pricing APIs when needed for atomicity
  and immutable pricing facts;
- replace the hosted streaming evidence list with a bounded incremental state
  machine;
- add small content-free schemas/helpers under the existing external-tool or
  Responses naming family;
- add focused test fixtures/helpers inside the authorized test files;
- start PostgreSQL/Redis locally, create/drop a uniquely named disposable test
  database, and use safe mocked provider blocking/failure controls.

Do not preserve a flawed implementation merely because it already exists. Keep
ordinary Responses, Codex-local tools, non-hosted accounting, and existing
public behavior compatible.

## Required outcomes

1. All key/route/provider/shape/cap and one immutable model+tool pricing/FX
   decision complete before Redis, fence mutation, adapter construction, or
   provider work. `max_tool_calls` without admitted web search fails there.
2. Fence acquisition uses only the exact resolved route UUID. No approximate
   model/pattern fallback exists.
3. A clear provider-not-started/provider-started boundary governs cleanup:
   before start, safe failure atomically releases/records/resolves; after start,
   every unknown or failed terminal path atomically creates one durable hold.
   Partial finalization rolls back before hold placement. Repeated handling is
   idempotent and content-free.
4. Successful model-token plus web-search-call accounting uses the exact
   admitted native pricing and FX facts, finalizes one ledger/counters, and
   resolves the fence in one transaction. One request may overrun; later
   ordinary/hosted requests then fail without mutation/provider work.
5. Hosted streaming validation is bounded by admitted cap and absolute limits,
   validates real provider lifecycle/action shapes before discarding content,
   supports the normal message/text events in a web-search response, counts
   calls once, buffers no raw content, and withholds success terminal until
   atomic accounting/fence resolution. Malformed/error/disconnect paths create
   `streaming=true` holds.
6. Redis reservations/heartbeats are released on denial, pre-provider failure,
   success, hold, malformed stream, cancellation, and disconnect; Redis never
   becomes quota/fence truth.
7. Remote MCP/connectors and every unselected hosted family remain denied.
   Client/Codex-local tools retain their independent behavior and no gateway
   tool execution is introduced.
8. Prompt/query/URL/source/result/action/ID/provider-error canaries never enter
   logs, errors, ledgers, audits, reports, exports, or safe DTOs.

## Mandatory evidence before report

Extend `tests/integration/test_responses_external_tool_postgres.py` into a real
gateway/service orchestration matrix using actual PostgreSQL repositories and
official-shape mocked OpenAI behavior. It must include named tests proving:

- allowed non-stream success: full-balance reserve, exact fee/tokens, one
  ledger, zero reserved counters, fence clear, canonical headers/body;
- same-key concurrent rejection while a blocking provider is in flight and
  independent-key progress;
- cost/token overrun followed by ordinary and hosted rejection with zero new
  mutation/provider calls;
- provider error, missing usage, malformed/missing call evidence, finalization
  or resolve failure → exactly one full-reservation hold; auth/admission block;
- audited finalize-actual and release-no-charge reconciliation and exact final
  counters/audits;
- hosted streaming success with normal message/text events and terminal
  withholding; malformed event and client disconnect → streaming hold;
- Redis cleanup assertions and persistence canary scans.

Add focused unit tests for pre-Redis ordering, single pricing lookup/fact,
`max_tool_calls` isolation, exact route ID, pre-provider cleanup, broad
post-start hold fallback, tracker bounds/actions/message events, and true
streaming flags.

The OpenAI-client E2E must retain the happy path and add only the smallest
additional public-wire negative/stream proof needed; no real provider.

The local PostgreSQL matrix is mandatory and must run with zero skips. Set it
up yourself. Do not publish the report until the evidence exists and passes.

## Authorized scope

You may modify relevant files within these bounded families:

```text
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/schemas/openai.py
app/slaif_gateway/schemas/openai_web_search.py
app/slaif_gateway/schemas/pricing.py
app/slaif_gateway/schemas/responses_external_tool*.py
app/slaif_gateway/services/accounting.py
app/slaif_gateway/services/external_tool_fence.py
app/slaif_gateway/services/external_tool_hold.py
app/slaif_gateway/services/openai_web_search_contract.py
app/slaif_gateway/services/pricing.py
app/slaif_gateway/services/responses_external_tool*.py
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
tests/unit/test_external_tool_fence.py
tests/unit/test_external_tool_hold.py
tests/unit/test_openai_web_search_contract.py
tests/unit/test_pricing.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_usage_report_service.py
tests/unit/test_v1_responses_quota.py
oap/active
oap/orders/017-c-own-and-complete-external-tool-phase-gate.md
```

If a genuinely necessary adjacent file is required within the same subsystem,
you may add it only when the report names the exact reason and diff; do not use
this autonomy to add product scope. Final report-only commit may add:

```text
oap/reports/017-c-own-and-complete-external-tool-phase-gate.md
```

## Non-goals

No migration/schema change, remote MCP/connector/OAuth/approval, other hosted
family, OpenRouter hosted support, real provider, production data/credential/
deployment, organization/RBAC work, content retention, release, or broad local
suite. Never merge or enable auto-merge.

## Verification economy

Run the focused affected unit groups, the mandatory disposable-PostgreSQL
gateway matrix, and the Responses OpenAI-client E2E group. Run scoped Ruff,
compileall, diff/path checks, and docs checks. Do not run the full local
unit/browser/Compose/HPC matrix; GitHub CI provides broad regression coverage.

Report criterion-by-criterion evidence with exact test names/counts, DB name/
cleanup, mock boundaries, skips (required groups must have zero), CI truth,
privacy scans, and limitations. Do not claim an outcome from indirect tests.

## PR/report protocol

Use existing PR #242 and branch; create no PR. Commit this order and exact
`oap/active=017-c` unchanged. Publish one immutable
`oap/reports/017-c-own-and-complete-external-tool-phase-gate.md` with literal
implementation SHA and `Report publication commit: SELF`; the report-only
commit must parent the implementation head and change only the report. Verify
remote head/checks/reviews, signal exact `OK`, return to control FIFO, and do
not merge.
