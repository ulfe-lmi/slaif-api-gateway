# OAP Work Order — 017-e

## Objective

Amend PR #242 with the final direct evidence missing from 017-d. This round is
tests-only: prove actual in-flight concurrency and independent-key progress,
reconcile gateway-created holds through both operator actions, inject
finalization/resolve rollback-to-hold, prove disconnect-to-streaming-hold, and
prove hosted ordering before Redis/fence/provider. Do not change production
code unless a required test demonstrates a concrete defect; if so, report the
defect for a narrow continuation rather than widening this round.

## Verified state

- Sole Objective 017 PR #242 on the existing branch.
- 017-d implementation:
  `e0c537d004e1f70f87c1759ea490450e6e822234`.
- 017-d report head:
  `815308295f5c67252f3cf34899ed577e7e6c8e27`.
- All ten final-head checks pass; report topology is valid; the sole review
  thread is resolved; auto-merge is off.
- Zero-call auto-choice and all action variants are restored; pre-provider
  streaming failure now releases and resolves atomically.
- Current PostgreSQL file has eight test functions/ten parameterized cases but
  still uses a pre-acquired fence instead of a blocked in-flight provider, has
  no independent-key proof, no reconciliation of a gateway-created hold, no
  injected finalization/resolve failure, no disconnect test, and no direct
  pre-Redis pricing/max-tool ordering test.

## Mandatory new evidence

Add and run tests with these exact semantic outcomes (names may differ only
slightly, but each must be individually identifiable in the report):

1. `gateway_inflight_same_key_blocks_and_independent_key_progresses`:
   use separate DB sessions and a blocking mocked provider. Wait until the first
   request's committed fence and provider entry are observable; prove a second
   same-key request fails with zero second provider call while a distinct key
   completes; release the first request and assert exact final fences,
   reservations, ledgers, counters, audits, and Redis releases.
2. `gateway_created_hold_finalize_actual_reconciles_once`: create the hold via
   a real gateway provider-started failure, prove following auth/ordinary and
   hosted admission block, execute existing audited `finalize-actual`, assert
   one reconciliation audit/exact counters/fence, and prove expected following
   admission or exhaustion.
3. `gateway_created_hold_release_no_charge_reconciles_once`: same, using
   `release-no-charge`; assert zero actual usage/cost, one audit, fence clear,
   and a fitting following admission.
4. `gateway_finalization_and_resolve_failure_roll_back_then_hold`: parameterize
   injected custom-finalization and fence-resolution failures after provider
   completion. Assert rollback of partial terminal state, then exactly one
   pending full-balance reservation, held fence, hold ledger/audit, auth block,
   and Redis release; no duplicate ledger/audit.
5. `gateway_stream_disconnect_creates_one_streaming_hold`: begin an official
   hosted stream, consume at least one provider event, cancel/close the client
   path, and assert no success terminal, one `streaming=true` hold, full
   reservation, content-free state, and Redis release.
6. `hosted_pricing_and_max_tool_calls_fail_before_redis_fence_provider`:
   direct spies/counters prove missing/malformed hosted pricing and
   `max_tool_calls` without admitted web search perform zero Redis reservation,
   fence/acquisition, adapter construction, and provider call. Also prove one
   valid hosted request uses a single immutable pricing/FX lookup/fact.
7. Add a bounded-stream regression proving event/state overflow, oversized or
   malformed IDs/indexes/sequences/actions, and normal assistant message events
   behave exactly as documented without canary retention.

Use private canaries and assert they are absent from responses/errors/logs,
ledger/audit metadata, safe DTOs, and report fixtures.

## Allowed paths

```text
tests/integration/test_responses_external_tool_postgres.py
tests/unit/test_openai_web_search_contract.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_v1_responses_quota.py
tests/e2e/test_openai_python_client_responses.py
oap/active
oap/orders/017-e-prove-final-phase-gate-scenarios.md
```

Final report-only commit may add:

```text
oap/reports/017-e-prove-final-phase-gate-scenarios.md
```

No production/doc/migration/runtime change is authorized in this round.

## Verification

- Run focused affected unit files with zero skips.
- Create/migrate/drop one uniquely named disposable PostgreSQL DB and run the
  expanded external-tool gateway matrix with zero skips.
- Run the focused Responses OpenAI-client E2E group only if changed; zero
  required skips.
- Run scoped Ruff/compileall for changed tests, `git diff --check`, exact path
  check, and final GitHub CI. No broad local unit/browser/Compose/HPC suite.

The report must map every numbered outcome above to exact test name/result and
durable DB/provider/Redis/privacy facts. Do not cite pre-existing service-only
tests or broad CI as substitutes. If any mandatory test exposes a production
defect, publish a truthful blocker report without changing production files.

## PR/report protocol

Use existing PR #242/branch; create no PR. Commit this order and exact
`oap/active=017-e` unchanged. Publish one immutable
`oap/reports/017-e-prove-final-phase-gate-scenarios.md` with literal
implementation SHA and `Report publication commit: SELF`; report-only commit
parents implementation and changes only the report. Verify remote head/checks/
reviews, signal exact `OK`, return to control FIFO, and never merge/auto-merge.
