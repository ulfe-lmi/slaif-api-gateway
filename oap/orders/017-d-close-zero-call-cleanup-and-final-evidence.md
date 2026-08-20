# OAP Work Order — 017-d

## Objective

Amend PR #242 to close the final Objective-017 phase-gate gaps: restore
authoritative zero-call auto-choice outcomes, atomically clean up a fenced
request when streaming provider construction fails before provider start,
complete the missing real gateway evidence, support all qualified official
web-search action variants in bounded streaming, and resolve the sole review
thread. Own the implementation inside the authorized subsystem; do not merely
silence tests.

## Verified state

- Sole Objective 017 PR #242 on
  `oap/017-external-tool-security-accounting-e2e`.
- 017-c implementation:
  `e3c88ef0b642de305848e5e2c764c4f35dc0eb18`.
- 017-c report head:
  `74ae39367ecb6bbde2709cab230db14c363a0e5c`.
- All ten report-head checks pass; report topology is valid; auto-merge is off.
- One unresolved review thread (`PRRT_kwDOSLm-qM6a-QSh`) flags duplicate module
  import styles in the integration test. Fix the import cleanly and resolve the
  thread after the remote fix.

## Required outcomes

1. Restore the Objective-016 contract: with absent/`auto` tool choice, a fully
   completed official response/stream with valid pricing and zero
   `web_search_call` items is authoritative with count/fee zero. A model is
   allowed not to invoke the declared tool. Missing pricing or incomplete/
   failed lifecycle remains non-authoritative. Restore focused regression tests.
2. If `get_provider_adapter` or equivalent construction fails before a hosted
   streaming provider call/iteration starts, atomically create the safe failed
   ledger, release full counters/reservation, and resolve the external fence.
   Do not leave an active fence pointing at a released reservation. Add a real
   PostgreSQL gateway test asserting exact final reservation/ledger/counters/
   fence/audit state and Redis release.
3. Add an actual in-flight concurrency test: block the first provider call
   after its fence commits, then prove a second same-key request is rejected
   without provider work while a separately created key progresses
   independently. Release the first call and prove both final states.
4. Take a hold created by a real gateway provider-error/missing-evidence path,
   prove following auth/admission blocks, then execute existing audited
   `finalize-actual` and `release-no-charge` reconciliation scenarios against
   gateway-created holds. Assert one audit, exact counters, fence state, and
   subsequent admission/exhaustion behavior.
5. Inject a failure after provider completion during custom finalization or
   fence resolution. Prove partial transaction rollback followed by exactly one
   durable full-reservation hold, no second ledger/audit, and Redis release.
6. Exercise real streaming client cancellation/disconnect after provider
   iteration begins. Prove no success terminal, one `streaming=true` hold, full
   reservation, and content-free persistence.
7. Hosted streaming validates/discards all Objective-016 official action
   variants (`search`, `open_page`, `find_in_page`) rather than only `search`.
   Reuse one content-free contract helper instead of duplicating weaker action
   semantics. Test normal message output-item events, identifier/index/sequence
   bounds, admitted-cap-derived event/state limits, and absence of canaries from
   retained evidence/repr/logs.
8. Add direct ordering regressions proving `max_tool_calls` without admitted
   web search and missing/malformed hosted pricing fail before Redis, fence,
   adapter, or provider work; one immutable pricing/FX lookup feeds reservation
   and finalization.
9. Fix the duplicate import style in
   `tests/integration/test_responses_external_tool_postgres.py`, retain the
   review check, and resolve the exact thread only after pushing.

## Authorized scope and autonomy

You may refactor relevant files within:

```text
app/slaif_gateway/providers/streaming.py
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
tests/e2e/test_openai_python_client_responses.py
tests/integration/test_responses_external_tool_postgres.py
tests/unit/test_external_tool_fence.py
tests/unit/test_external_tool_hold.py
tests/unit/test_openai_web_search_contract.py
tests/unit/test_pricing.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_v1_responses_quota.py
oap/active
oap/orders/017-d-close-zero-call-cleanup-and-final-evidence.md
```

If a small adjacent helper in the same Responses/external-tool subsystem is
needed, add it and explain why in the report. No migration, remote MCP,
connector, other hosted tool, OpenRouter hosted path, real provider, production,
RBAC/organization, or deployment change.

Final report-only commit may add:

```text
oap/reports/017-d-close-zero-call-cleanup-and-final-evidence.md
```

## Mandatory verification

- Run focused affected unit groups with zero skips.
- Create/migrate/drop one uniquely named disposable PostgreSQL DB and run the
  expanded gateway integration matrix with zero skips. The named tests above
  must actually exist; do not substitute direct fence-service tests.
- Run the focused Responses OpenAI-client E2E group with mocked provider and
  zero required skips.
- Run scoped Ruff/compileall, `git diff --check`, path/docs checks, and final
  GitHub CI. No full local unit/browser/Compose/HPC suite.

Report each outcome against exact test names, final DB facts, provider/Redis
call counts, cleanup result, privacy canaries, CI state, and review-thread
resolution. Do not publish a report while any named evidence is absent.

## PR/report protocol

Use existing PR #242/branch; create no PR. Commit this order and exact
`oap/active=017-d` unchanged. Publish one immutable
`oap/reports/017-d-close-zero-call-cleanup-and-final-evidence.md` with literal
implementation SHA and `Report publication commit: SELF`; its report-only
commit must parent implementation and change only the report. Verify final
remote head/checks/reviews, signal exact `OK`, return to control FIFO, and never
merge/auto-merge.
