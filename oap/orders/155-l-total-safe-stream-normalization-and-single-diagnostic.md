# OAP Work Order — 155-l

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: cc2def438ee60cab92e0fb28305c89d2be7f4051

## Objective and reason

Make protected stream observation normalization total, bounded, and durable so a
single new no-retry differential cannot again collapse to an opaque
`differential_summary_invalid`. Then assign the missing terminal-event boundary
from retained safe evidence and proceed only along the proven ownership branch.

155-k implemented disconnect-safe upstream draining and passed a complete fake
rehearsal, but its one protected verifier invocation failed in the CLI projector.
The exact boundary observations were discarded. A post-failure correction handles
one suspected missing-structure shape, but that shape was not proven by retained
evidence and other live shapes can still fail projection.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-k report
  head `cc2def438ee60cab92e0fb28305c89d2be7f4051`; first parent is
  `598915417f510aa592374ec6624905d37546aa18`, and only the exact 155-k report
  changed.
- All ten report-head checks pass.
- Local Coding PR #7 remains exact, OPEN, non-draft, MERGEABLE/CLEAN at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- The Gateway and Local linked worktrees are clean. No 155-k task root, runtime
  reference, credential source, process, listener, or container remains.
- No stream owner, real full-stack acceptance, merge authorization, deployment,
  or release claim exists.

## Audit correction carried by this continuation

The immutable 155-k report must not be rewritten. The 155-l report must state:

- a mode-0600 task-owned credential-source file temporarily persisted the
  protected credential declaration during 155-k;
- the credential value was never rendered, logged, hashed, or committed;
- the credential source and runtime reference were removed after 155-k report
  publication;
- eleven mode-0700 `slaif-155k.*` test roots remained after interrupted local
  commands despite the 155-k cleanup claim; strategic cleanup validated and
  removed those exact roots;
- these corrections affect audit accuracy, not the protected ownership result.

## 1. Total safe observation normalization

Replace the current late projector with a normalization boundary that runs
immediately after each diagnostic boundary is observed and before raw in-memory
facts can be discarded.

Every value shape produced by `_SSEStructuralRecorder`, `_ForwardingRelay`,
`_QwenRelayServer`, and `_stream_observation` under their existing bounds
must map to exactly one bounded public summary. No producer-valid shape may
raise `differential_summary_invalid`.

The public summary is finite and contains only:

- boundary enum and ran/not-run truth;
- normalized status class: `2xx`, `4xx`, `5xx`, or `unknown`;
- content type: `sse`, `json`, `other`, or `unknown`;
- compact ordered event trace plus bounded counts;
- response-completed presence and the existing safe relation/status/model/output/
  usage booleans or enums;
- upstream-normal-close, downstream-closed-early, handler-error, truncation, and
  official-client-completion booleans;
- normalization status: `complete`, `degraded`, or `invalid`;
- one finite normalization/failure reason enum;
- final ownership decision enum.

Never retain or emit raw IDs, response fields/values, bodies/chunks, model text,
prompts, endpoints, arbitrary paths, headers, credentials, identity/signature/
nonce, exception text, runtime-reference fields, or private values.

## 2. Bounded event trace for real streams

The current 64-item summary cap must not reject an otherwise valid stream merely
because it contains many repeated text-delta events.

Implement a bounded representation that preserves terminal ordering and exact
bounded counts, for example consecutive allowlisted event runs
`[{event,count}, ...]` with a finite run cap plus total counts. Requirements:

- repeated deltas do not consume one summary entry each;
- `response.created`, `response.completed`, `error`, unknown-event, and
  DONE-sentinel relations remain observable;
- completion beyond many deltas remains observable;
- if transition/run bounds overflow, emit a fixed overflow reason and classify
  ambiguous; never raise an opaque projector error;
- counts are nonnegative and bounded by the recorder capture limit;
- ordering, duplication, unknown, and truncation facts remain honest.

Do not fabricate or reorder provider events.

## 3. Safe projector failure envelope

Even if a non-producer-valid internal shape reaches normalization, emit a minimal
fixed envelope for the known boundary containing only safe enums/booleans and:

    normalization_status=invalid
    normalization_reason=<finite enum>
    decision=ambiguous_stream_evidence

The CLI must never discard the ran-boundary list or collapse a protected result
to only `differential_summary_invalid`. Unexpected Python/handler errors still
produce no traceback or private exception text.

Persist exact safe stdout in a mode-0600 task artifact until its byte-identical
contents are included in the immutable report; remove the task artifact only
after report publication.

## 4. Exhaustive fake-only proof before protected traffic

Before any protected request:

- enumerate and test every observation shape reachable from the four producer
  types;
- cover missing structure, non-SSE, JSON, 1xx/3xx/unexpected status, 4xx/5xx,
  no events, long repeated delta sequences, terminal beyond 64 events, many
  event runs, run overflow, duplicate/unknown/DONE, invalid/oversized/truncated
  SSE, handler error, downstream disconnect, upstream failure, official-client
  failure, and all ownership branches;
- assert exact stdout bytes/order/length and empty stderr;
- assert exact direct-only ran/not-run output and conditional composed gating;
- assert no raw/private marker can enter any normal or failure envelope;
- run focused verifier tests, Ruff, Python compilation, `git diff --check`, and
  the complete fake rehearsal;
- push the implementation head and require all ten checks green on that exact
  head.

Any failure blocks protected traffic.

## 5. Newly authorized protected differential

Only after section 4 is complete and green, read the activation runtime reference
without rendering it, verify protected health/model unchanged, and run exactly
one no-retry differential invocation:

1. Direct official OpenAI client -> scrubbed task relay -> protected Qwen.
2. The verifier may run the composed boundary only if normalized direct evidence
   has a valid `response.completed`: official client -> disposable
   Gateway/PostgreSQL -> signed relay -> exact Local PR #7 -> scrubbed relay ->
   protected Qwen.

Maximum: one direct protected request and, conditionally, one composed protected
request. No retry in 155-l for any reason.

The exact safe stdout artifact must survive until report publication. Stderr must
be empty. If normalization is degraded/invalid, stop with its exact finite reason.

## 6. Ownership and conditional action

Use only retained normalized evidence:

- Direct normally closes without `response.completed`: `qwen_owned`. Gateway
  must not fabricate completion. Stop with an exact Local Coding dialect-adaptation
  handoff; no Gateway product change.
- Direct has valid completion; Local output normally closes without it:
  `local_owned`. Stop with an exact Local Coding handoff; no Gateway product
  change.
- Direct and Local have valid completion; Gateway output normally closes without
  it: `gateway_owned`. Only then make the smallest conditional Gateway correction.
- All three have valid completion but official client fails/closes:
  `official_client_observation`. Correct only deterministic verifier/client
  observation without protected retry; otherwise stop.
- Any normalization degradation, upstream truncation, non-SSE failure, handler
  error, overflow, missing fact, or unexplained failure is
  `ambiguous_stream_evidence`.

Downstream closure alone does not assign ownership when upstream was fully
drained and normalized.

## 7. Conditional Gateway correction and final acceptance

Only on exact `gateway_owned` evidence, modify the smallest subset of:

    app/slaif_gateway/modules/servers/local_coding/adapter.py
    app/slaif_gateway/providers/openai_compatible.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_responses_streaming.py
    tests/e2e/test_openai_python_client_responses.py

Preserve provider event bytes/order, incremental forwarding, cancellation,
disconnect, reservation/finalization/rollback, signed identity, replay/
idempotency, route containment, hosted-search denial, privacy, and accounting.
Never fabricate completion, usage, cost, or tool authority. Add exact negative
and failing-then-passing regressions.

After a Gateway fix, rerun the complete fake rehearsal and all affected checks,
then exactly one no-retry full protected Codex 0.149 -> Gateway -> Local Coding
-> Qwen acceptance matrix. If the differential is
`all_boundaries_completed` with official-client completion, do the same full
fake rehearsal and one full protected matrix on the unchanged product head.

Do not run the full matrix for Qwen-owned, Local-owned,
official-client-observation, or ambiguous evidence.

## Required full-stack evidence

Integration PASS requires a fresh real run proving:

- real Codex 0.149 ordinary and streaming Responses;
- exact Gateway -> Local Coding route and signed identity accepted;
- PostgreSQL reservation/finalization and correct usage/accounting;
- same-session reuse and independent-session/cache isolation;
- replay/tamper rejection and request idempotency semantics;
- controlled failure rollback without accounting/state corruption;
- Qwen filtering/privacy invariants;
- complete temporary-state cleanup.

Mocks and fake rehearsal are necessary but not substitutes.

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
    oap/orders/155-l-total-safe-stream-normalization-and-single-diagnostic.md
    oap/reports/155-l-total-safe-stream-normalization-and-single-diagnostic.md
    oap/active

Conditional product paths are allowed only after exact Gateway-owned evidence
as listed in section 7.

No Local Coding repository mutation, schema/migration/dependency/lockfile,
route/pair/tool policy, Compose/deployment, protected service, release, or
production mutation is authorized.

## Security, privacy, accounting, and cleanup

- Use unique mode-0700 task roots and mode-0600 in-root logs/artifacts.
- The activation runtime reference and task-owned credential source are
  intentionally temporary persistent task secret material. Keep both mode 0600;
  never render them; remove both during final post-report cleanup.
- Preserve tracked Local `uv.lock`; never create/use Local `.venv`; use a
  task-owned `UV_PROJECT_ENVIRONMENT`.
- Clean every environment, safe-output artifact, relay, process/listener,
  PostgreSQL state/new image, generated lock/bytecode, runtime reference,
  credential source, and task root in finally paths.
- Verify Gateway and Local tracked/ignored state clean and protected health/model
  unchanged.
- Keep both PRs open. Coding agent never merges or enables auto-merge.

## Verification and publication

Publish one complete immutable 155-l report with:

- literal implementation head and `Report publication commit: SELF`;
- report parent equal to implementation head and report-only diff;
- byte-identical exact safe stdout from every boundary actually run;
- explicit ran/not-run protected counts;
- normalization/ownership decision and finite reason;
- fake/full-matrix/Gateway/Local ran-not-run ledger;
- focused and all-ten-check ledger;
- restored 155-k audit corrections above;
- security/privacy/accounting/cleanup/limitations ledger.

After report publication make no repository mutation. Wait for report-head
checks; verify remote topology and mergeability; remove the exact runtime
reference, task-owned credential source, safe artifact, and task roots without
rendering; signal exact FIFO `OK`; stop.

Only a complete integration PASS creates the merge pair. Strategic then
revalidates and merges Local Coding PR #7 first and Gateway PR #291 second.
Do not start Objective 156 or Local Objective 006 before resolution.

