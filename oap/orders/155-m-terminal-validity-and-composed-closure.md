# OAP Work Order — 155-m

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 264f15fbcfe513882597a48f41095f108849ee74

## Objective and reason

Separate terminal-completion validity from response-event vocabulary review,
reuse the immutable 155-l direct-Qwen proof, and run only the composed
Gateway -> Local Coding -> Qwen stream boundary. Correct only the proven owner
and, if every terminal boundary is valid, execute the first complete real
Codex 0.149 full-stack acceptance.

155-l proved that direct protected Qwen returns a valid terminal response but
also emits many event types outside the verifier's small review allowlist. Those
unknown names are a compatibility limitation; they do not erase the observed
`response.completed` and must not be conflated with request-side tool authority.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-l report
  head `264f15fbcfe513882597a48f41095f108849ee74`; first parent is
  `e1e2395c4d77ea9772a2471e6d5e55102484a440`, and only the exact 155-l report
  changed.
- All ten report-head checks pass.
- Local Coding PR #7 remains exact, OPEN, non-draft, MERGEABLE/CLEAN at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Gateway and Local linked worktrees are clean. The 155-l runtime reference,
  credential source, safe artifact, roots, processes, listeners, and containers
  are absent.
- No stream owner, real full-stack acceptance, merge authorization, deployment,
  or release claim exists.

## Immutable direct baseline

The verifier must pin and parse only the strict safe-schema direct boundary from
the 155-l report. It must verify:

- exact report commit, parent, report-only path, ancestry, and remote head;
- the embedded direct line is unique and strict-schema normalized;
- `ran=true`, status `2xx`, content type `sse`, normalization complete,
  failure none, no handler error, no upstream truncation, normal close, no
  downstream close, official client completion;
- exact one `response.created` and one `response.completed`;
- response-ID relation, created/completed statuses, expected model, nonempty
  terminal output, and valid nonnegative usage;
- event-trace overflow false.

The immutable line also records `unknown_events=true`, 1,259 normalized
`other` events, and 386 output-text deltas. Preserve these as compatibility
facts. Do not infer raw event names or contents.

If the report cannot be parsed exactly into the strict safe schema, stop before
protected traffic.

## 1. Distinct terminal and vocabulary verdicts

Introduce two independent verdicts:

1. `terminal_completion_valid`: true only for 2xx SSE, exact one created and
   completed terminal, valid ID/status/model/output/usage relations, upstream
   normal close, no handler/truncation/error event, and official-client
   completion where applicable.
2. `event_vocabulary_reviewed`: true only when every event type belongs to the
   reviewed allowlist.

Repeated deltas, DONE presence, and unreviewed response event names must remain
reported but must not by themselves falsify `terminal_completion_valid`.
Unknown/error content is never retained. An explicit `error` event, missing
terminal, bad relations, invalid usage/output, truncation, or client failure
still fails terminal validity.

Unknown response-event names cannot grant request-side tools, hosted search,
MCP, network, filesystem, or execution authority. Request tool policy remains
independently deny-by-default and the composed diagnostic contains no tools.

## 2. Bound recorder memory

The recorder must not retain an unbounded full event sequence. Use only:

- compact bounded event runs;
- bounded per-type counts;
- explicit created/completed/error presence and count facts;
- overflow/invalid flags.

Remove or strictly cap full per-event storage. A long stream with thousands of
events must have bounded memory and preserve a terminal beyond repeated deltas.
Unit-test streams near and beyond capture/event limits.

Do not fabricate, reorder, or drop provider bytes in forwarding; this change is
evidence storage only.

## 3. Composed-only verifier path

Add an explicit composed-only diagnostic mode that:

- never sends a new direct protected request;
- loads the pinned 155-l direct baseline above;
- starts disposable PostgreSQL, Gateway, exact Local PR #7, signed relay, and
  scrubbed Qwen relay;
- sends one minimal text-only official-client streaming request with one
  synthetic owner/key/session/repository and no tools/images/governance/customer
  data;
- captures strict safe summaries for `local_output` and `gateway_output`;
- performs strict-bounded Gateway reservation/finalization verification;
- emits the pinned direct baseline plus the two new boundary summaries and final
  decision to an exclusive mode-0600 artifact in a validated mode-0700 root.

Unit-test that the direct diagnostic function cannot be called from this mode.

## 4. Fake-only gate

Before protected traffic:

- test terminal validity independently from vocabulary review;
- cover unknown events with valid terminal, repeated deltas, DONE, explicit
  error, duplicate terminal, missing terminal, bad status/model/output/usage/ID,
  non-SSE, client failure, disconnect, handler error, truncation, and overflow;
- prove bounded recorder memory with long synthetic streams;
- prove exact strict parsing of the 155-l baseline and reject altered/multiple/
  malformed report lines;
- prove composed-only mode cannot call direct;
- assert exact stdout bytes/order/length, empty stderr, and raw/private marker
  exclusion;
- run focused tests, Ruff, Python compilation, `git diff --check`, the complete
  fake rehearsal, and all ten checks on the pushed implementation head.

Any failure blocks protected traffic.

## 5. Newly authorized composed diagnostic

Only after section 4 is complete and green, read the activation runtime reference
without rendering it, verify protected health/model unchanged, and run exactly
one composed-only protected diagnostic. Maximum new protected requests in 155-m:
one. No direct request and no retry.

Retain the exact safe artifact through report publication.

## 6. Ownership decision

Use the pinned direct terminal baseline and the new composed summaries:

- Local terminal invalid: `local_owned`; stop with exact Local Coding handoff.
- Local terminal valid and Gateway terminal invalid: `gateway_owned`; only then
  make the smallest conditional Gateway correction.
- Local and Gateway terminal valid, and official client completed:
  `terminal_boundaries_completed`; event-vocabulary review remains a documented
  limitation but the missing-terminal gate is closed.
- Any malformed baseline, non-SSE, handler/truncation/error, missing accounting,
  invalid normalization, or unexplained failure is
  `ambiguous_stream_evidence`.

Do not assign ownership from event-vocabulary completeness alone.

## 7. Conditional Gateway correction

Only on exact `gateway_owned` evidence, modify the smallest subset of:

    app/slaif_gateway/modules/servers/local_coding/adapter.py
    app/slaif_gateway/providers/openai_compatible.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_responses_streaming.py
    tests/e2e/test_openai_python_client_responses.py

Preserve provider bytes/order, incremental forwarding, cancellation, disconnect,
reservation/finalization/rollback, signed identity, replay/idempotency, route
containment, hosted-search denial, privacy, and accounting. Never fabricate
completion, usage, cost, or tool authority. Add exact negative and
failing-then-passing regressions.

After a Gateway fix, rerun complete fake rehearsal and all affected checks before
one newly authorized composed-only verification. This conditional verification
is not a retry of ambiguous evidence; it is allowed only for a proven and fixed
Gateway defect. If that verification fails, stop.

## 8. Full real acceptance

If the first composed diagnostic yields `terminal_boundaries_completed`, or a
proven Gateway fix is subsequently verified:

- update the full verifier's real-stream acceptance to use terminal validity
  while retaining vocabulary facts; keep exact fake-pair assertions for fake
  rehearsal;
- rerun the complete fake rehearsal and require all ten checks green on the
  exact final implementation head;
- run exactly one no-retry full protected
  real Codex 0.149 -> Gateway -> Local Coding -> Qwen matrix.

The full matrix must prove:

- ordinary and streaming Responses success through real Codex 0.149;
- exact Gateway -> Local route and signed identity acceptance;
- PostgreSQL reservation/finalization and correct usage/accounting;
- same-session reuse and independent-session/cache isolation;
- replay/tamper rejection and request idempotency semantics;
- controlled failure rollback without accounting/state corruption;
- request tool filtering and no hosted-search authority;
- Qwen credential and privacy boundaries;
- complete temporary-state cleanup.

Do not run the full matrix for Local-owned or ambiguous evidence.

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
    oap/orders/155-m-terminal-validity-and-composed-closure.md
    oap/reports/155-m-terminal-validity-and-composed-closure.md
    oap/active

Conditional product paths are allowed only after exact Gateway-owned evidence
as listed in section 7.

No Local Coding repository mutation, schema/migration/dependency/lockfile,
route/pair/tool policy, Compose/deployment, protected service, release, or
production mutation is authorized.

## Security, privacy, accounting, and cleanup

- Use unique mode-0700 task roots and atomically created mode-0600 logs/artifacts.
- Runtime reference and task credential source are temporary persistent secret
  material; never render them; remove both during final post-report cleanup.
- Preserve Local tracked `uv.lock`; never create/use Local `.venv`; use a
  task-owned `UV_PROJECT_ENVIRONMENT`.
- Clean every environment, safe artifact, relay, process/listener, PostgreSQL
  state/new image, generated lock/bytecode, runtime reference, credential source,
  and task root.
- Verify Gateway/Local tracked and ignored state clean and protected health/model
  unchanged.
- Keep both PRs open. Coding agent never merges or enables auto-merge.

## Verification and publication

Publish one complete immutable 155-m report with:

- literal implementation head and `Report publication commit: SELF`;
- report parent equal to implementation head and report-only diff;
- exact pinned direct baseline and byte-identical new safe artifact;
- terminal and vocabulary verdicts for each boundary;
- exact protected ran/not-run counts;
- accounting, identity, cache, replay, rollback, privacy, and cleanup ledgers as
  applicable;
- fake/full-matrix/Gateway/Local ran-not-run ledger;
- focused and all-ten-check ledger;
- explicit limitations and no claim beyond evidence.

After report publication make no repository mutation. Wait for report-head
checks; verify topology/mergeability; remove exact runtime reference, task
credential source, safe artifact, and task roots without rendering; signal exact
FIFO `OK`; stop.

Only a complete full-stack PASS creates the merge pair. Strategic then
revalidates and merges Local Coding PR #7 first and Gateway PR #291 second.
Do not start Objective 156 or Local Objective 006 before resolution.

