# OAP Work Order — 155-j

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 9c29eb5bb5d95d75dd600c3b629c589d797ab1d8

## Objective and reason

Locate the real streaming terminal-event loss at exactly one boundary—protected
Qwen, Local Coding, or Gateway—using bounded privacy-safe wire facts. Correct only
Gateway if and only if the differential proves Gateway ownership. Close the stream
gate before any full protected acceptance is repeated.

155-i established a complete FAKE_REHEARSAL=OK through exact real Codex, Gateway,
Local Coding, fake Qwen, identity/cache/replay/accounting/failure/privacy, and
cleanup assertions. Its one protected attempt then passed ordinary real-Qwen
Responses and failed stream_completion_event_missing; no later real matrix traffic
or retry ran.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-i report
  head 9c29eb5bb5d95d75dd600c3b629c589d797ab1d8; first parent is
  621af9f74d0229db5bdb6d21b98e31b6dcefc73a, and only the 155-i report changed.
- The complete 155-i report restores the 155-h ledger and records all ten checks
  successful on its implementation head.
- Local Coding PR #7 remains exact, OPEN, clean, and green at
  6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8; signed-contract head
  356be8345dd71d6fddf829278651d18e485731d4 remains an ancestor.
- Both repositories and Local ignored state are clean; all fake/real task state is
  absent. Strategic cleanup removed the prior task runtime reference after 155-i.
- No real composed streaming acceptance or merge authorization exists.

## Safe stream evidence contract

Extend or reuse the redacted SSE recorder. For each stream retain only:

- boundary class: direct_qwen, local_output, or gateway_output;
- numeric HTTP status class and content-type class;
- ordered allowlisted event sequence and counts;
- unknown/duplicate flags and DONE-sentinel presence;
- finite response field-name sets;
- safe value relations only: resp_-shaped ID present/equal, expected status
  progression, expected model boolean, terminal output shape class, usage field
  presence/nonnegative boolean;
- first-event-before-upstream-completion and normal-close booleans.

Never retain or print raw IDs, values, model text, body/chunks, prompts, endpoints,
arbitrary paths, headers/credentials, identity/signature/nonce, exception text, or
runtime-reference fields. RuntimeReference repr/str remains fixed redacted. Unit-test
reorder, duplicate, unknown, sentinel, missing terminal, wrong status/model/usage/
output, non-SSE, truncation, and bounds.

## Two-request protected differential

After exact topology/runtime/model/cleanliness checks and green CI, run at most two
minimal text-only protected streaming diagnostics with no tools, image, governance,
or customer data:

1. direct_qwen: official client -> scrubbed task relay -> protected Qwen.
2. composed: official client -> disposable Gateway/PostgreSQL -> signed relay ->
   exact Local PR #7 -> scrubbed Qwen relay -> protected Qwen.

The composed diagnostic captures local_output at the Gateway-to-Local relay and
gateway_output at the official-client/Gateway boundary. Use one synthetic owner/key/
session/repository and ordinary strict-bounded accounting. Clean after each. No Codex,
compiler, cache, image, replay, or broader matrix traffic is allowed in the differential.

## Ownership decision

- Direct Qwen lacks valid response.completed: protected Qwen/current dialect is the
  source. Gateway must not fabricate completion. Local Coding owns model-specific
  compatibility adaptation; publish a safe handoff and stop without Gateway product
  change.
- Direct Qwen has completion but local_output does not: Local Coding owns the defect;
  publish the safe handoff and stop without Gateway product change.
- Direct Qwen and local_output have completion but gateway_output does not: Gateway
  owns the defect; only then may conditional Gateway correction proceed.
- All three have completion but the official-client check misses it: verifier/client
  observation is wrong. Correct only verifier/tests and repeat composed diagnostic once.
- Ambiguous, truncated, non-SSE, or unavailable evidence fails closed without product
  change.

## Conditional Gateway correction

Only on exact Gateway-owned evidence, make the smallest correction within:

    app/slaif_gateway/modules/servers/local_coding/adapter.py
    app/slaif_gateway/providers/openai_compatible.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_responses_streaming.py
    tests/e2e/test_openai_python_client_responses.py

Preserve valid raw event bytes/order; never fabricate provider usage, completion, or
tool authority. Preserve incremental forwarding, cancellation, disconnect, validation,
reservation/finalization/rollback, hosted-search denial, signed identity, and privacy.
Add exact failing-then-passing and negative stream regressions.

After a Gateway fix, rerun full fake rehearsal, affected tests, and all ten checks,
then run exactly one full protected composition for the complete 155-i matrix. No retry
after real topology starts. If evidence is Qwen- or Local-owned, do not run a full
protected composition in this Gateway round.

## Acceptance

Diagnostic acceptance requires an unambiguous decision-table result and cleanup.
Integration PASS additionally requires a valid composed response.completed and one
full RESULT=OK status=real_composed_acceptance matrix with accounting, signed identity/
isolation, cache/rehydration, replay/tamper, controlled rollback, Qwen filtering,
privacy, and cleanup.

Do not claim MVP, deployment, release, certification, persistent replay, or hostile
same-key isolation from this round alone.

## Allowed paths

Unconditional evidence paths:

    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    docs/module-architecture.md
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/security-model.md
    docs/accounting.md
    docs/compatibility-matrix.md
    oap/orders/155-j-protected-stream-boundary-differential-and-closure.md
    oap/reports/155-j-protected-stream-boundary-differential-and-closure.md
    oap/active

Conditional product paths are allowed only after exact Gateway-owned evidence. No Local
repository, schema/migration/dependency/lockfile, route/pair/tool policy, Compose/
deployment, protected service, release, or production mutation is authorized.

## Cleanup, publication, and merge gate

- Use unique task roots and mode-0600 in-root logs; clean environments, relays,
  processes/listeners, PostgreSQL state/new image, runtime reference, generated lock/
  bytecode, and all diagnostic state in finally blocks.
- Preserve tracked Local uv.lock; verify both repositories and ignored state clean and
  protected health/model unchanged.
- Keep both PRs open during coding. Coding agent never merges or enables auto-merge.
- Publish one complete immutable 155-j report with literal implementation head,
  Report publication commit: SELF, and full safe differential/ran-not-run/check/
  cleanup/limitations ledger. Report parent is implementation head and only report
  path changes.
- After publication make no repository mutation; verify remote topology/checks, remove
  the exact runtime reference without rendering it, and signal exact FIFO OK.
- Only a complete PASS creates the merge pair. Strategic then merges Local PR #7 first
  and Gateway PR #291 second after exact revalidation. Do not start Objective 156 or
  Local Objective 006 before resolution.

