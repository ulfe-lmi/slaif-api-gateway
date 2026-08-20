# OAP 017-e execution report

Implementation head SHA: 60cd321a365e4c7276b715d9e5d07ff36e18d33e
Report publication commit: SELF

## Scope and topology

This round amended the existing Objective-017 PR #242 on
`oap/017-external-tool-security-accounting-e2e`. It changed tests only, plus
the required `oap/active=017-e` and activated order. No production code,
migration, documentation, new PR, merge, or auto-merge action was performed.

## Mandatory evidence

1. `test_gateway_inflight_same_key_blocks_and_independent_key_progresses`
   used separate committed PostgreSQL sessions and two keys. The first
   provider call was blocked after entry; the second same-key request returned
   409 with no second provider call, while the independent key completed with
   provider call 2. Releasing the first call produced one successful ledger
   and cleared fence/reservation/counters for each key. Three Redis releases
   were observed (blocked request plus two completed requests), and each key
   had its audit rows and exactly one ledger.
2. `test_gateway_created_hold_finalize_actual_reconciles_once` created a hold
   through a real gateway provider-started failure, proved ordinary and hosted
   follow-up admission blocks, then executed audited `finalize-actual` once.
   It asserted one ledger, one reconciliation audit, cleared fence and
   reservation, exact actual cost/tokens, and exhausted following accounting
   state. Three Redis releases covered the initial and two blocked requests.
3. `test_gateway_created_hold_release_no_charge_reconciles_once` performed the
   same real gateway hold path with audited `release-no-charge`, asserting one
   reconciliation audit, zero actual cost/tokens, cleared fence, and no-charge
   counters. Three Redis releases were observed.
4. `test_gateway_finalization_and_resolve_failure_roll_back_then_hold` ran
   `custom_finalization` and `fence_resolution` cases. Each injected failure
   after provider completion, returned a safe error, rolled back partial
   terminal state, and left exactly one full-balance pending hold ledger,
   held fence, hold-created audit, and Redis release. Canaries were absent.
5. `test_gateway_stream_disconnect_creates_one_streaming_hold` cancelled an
   ASGI client request after the official provider stream entered. It asserted
   no success terminal, one `streaming=true` hold, full reservation, safe
   content-free ledger state, and one Redis release.
6. `test_hosted_pricing_and_max_tool_calls_fail_before_redis_fence_provider`
   covered `max_tool_calls_without_web_search`, `missing_pricing`, and
   `malformed_pricing`; all had zero Redis, fence, and adapter calls.
   `test_allowed_web_search_forwards_canonical_body_and_finalizes` additionally
   proved one pricing lookup and one FX lookup, with the exact same immutable
   pricing and FX objects passed to reservation estimation.
7. `test_web_search_stream_rejects_bounds_and_malformed_actions_without_canaries`
   covered negative sequence/index, missing identifier, unsupported action, and
   the admitted-cap-derived event overflow. The existing
   `test_web_search_stream_validates_all_official_actions_content_free` covered
   `search`, `open_page`, and `find_in_page`; normal assistant message output
   events remain covered by the bounded stream table tests. All retained
   evidence was canary-free.

## Verification

- Focused unit command: `pytest tests/unit/test_openai_web_search_contract.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_v1_responses_quota.py -q -ra`; 368 collected and passed, zero skips.
- PostgreSQL command: `TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/slaif_oap_017e_test_1787265764 pytest tests/integration/test_responses_external_tool_postgres.py -q -ra`; 16 collected and passed, zero skips. The disposable database was created with `sudo -n -u postgres createdb -O ubuntu` and dropped with `sudo -n -u postgres dropdb --if-exists`; drop status was 0.
- Scoped Ruff, compileall, and `git diff --check` passed for all changed test files.
- The focused Responses E2E files were unchanged and were not run locally in
  this tests-only round. GitHub's OpenAI-compatible E2E check passed on the
  implementation head.

## Safety, privacy, and failures

No real provider calls, production systems, real email, or secrets were used.
Private provider, response, stream, and reconciliation canaries were asserted
absent from responses, errors, ledgers, audits, and safe evidence. No provider
content or credentials were persisted. PostgreSQL was authoritative; Redis
was used only for transient reservation/release observation. No test failure
remained at publication.

## GitHub state

All ten fresh implementation-head checks passed: Unit/lint/migration,
PostgreSQL integration, OpenAI-compatible E2E, Playwright browser smoke, Docker
Compose smoke, documentation hygiene, and four CodeQL checks. PR #242 remains
open with base `main`, the existing branch, auto-merge disabled, and no merge
performed.
