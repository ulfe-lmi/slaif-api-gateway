# OAP Work Order — 155-k

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 37c84c9cf32fb63303fe1f1897ca97bb170abb2c

## Objective and reason

Make the protected-stream differential evidence complete and disconnect-safe,
then use the smallest newly authorized diagnostic to assign the missing
`response.completed` boundary without weakening Gateway, Local Coding,
accounting, privacy, or stream semantics.

155-j used its two authorized protected diagnostics but returned only
`ambiguous_stream_evidence`. Its CLI discarded the already-bounded
per-boundary observations, and a relay emitted a `BrokenPipeError` after a
client-side stream ended. The result is truthful but cannot identify Qwen,
Local Coding, Gateway, or official-client ownership. This continuation corrects
the evidence path before any new protected request.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-j report
  head `37c84c9cf32fb63303fe1f1897ca97bb170abb2c`; first parent is
  `c2b7cdaeb5d7c595a4882c2bf841b1fc8704a42f`, and only the exact 155-j report
  changed.
- All ten report-head checks pass: both analysis checks, Analyze Python, CodeQL,
  Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E,
  Playwright browser smoke, PostgreSQL integration, and Unit/lint/migration.
- Local Coding PR #7 remains exact, OPEN, non-draft, MERGEABLE/CLEAN at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Both linked worktrees are clean. The 155-j runtime reference, processes,
  listeners, task roots, and containers are absent.
- No stream owner, full real acceptance, merge authorization, deployment, or
  release claim exists.

## 1. Correct the bounded evidence contract before protected traffic

Extend the existing verifier and its unit tests without changing Gateway
product behavior.

For each `direct_qwen`, `local_output`, and `gateway_output` boundary,
retain and emit only this finite schema:

- boundary enum;
- HTTP status class enum: `2xx`, `4xx`, `5xx`, or `unknown`;
- content type enum: `sse`, `json`, `other`, or `unknown`;
- allowlisted ordered event-name sequence and bounded counts;
- booleans for `response.completed` present, duplicate, unknown, DONE sentinel,
  valid response-id relation, completed status, expected model, terminal output
  shape, nonnegative usage, upstream normal close, downstream closed early, and
  official-client completion;
- one fixed failure-code enum or `none`;
- one final decision enum.

Never retain or emit raw IDs, values, bodies/chunks, model text, prompts,
endpoints, arbitrary paths, headers, credentials, identity/signature/nonce,
exception text, runtime-reference fields, or private values. Exact CLI output
must be fixed-format and bounded. Stdlib server tracebacks are prohibited.

## 2. Preserve upstream evidence after downstream disconnect

A downstream `BrokenPipeError` or `ConnectionResetError` is an observation,
not permission to lose the upstream stream.

- Mark `downstream_closed_early=true` once.
- Stop writing to the closed downstream socket.
- Continue draining the already-open upstream response to its normal end within
  the existing timeout/capture bounds.
- Continue feeding the structural recorder and finalize its safe snapshot.
- Record upstream status/content type and normal-close truth independently from
  downstream close.
- Do not retry, reconnect, fabricate events/usage/completion, swallow upstream
  errors, or convert a truncated upstream into normal close.
- Suppress raw handler tracebacks and expose only a fixed safe failure code or
  boolean.

Unit-test incremental forwarding, disconnect before the terminal event,
disconnect on the first/last chunk, upstream truncation, upstream HTTP failure,
non-SSE, invalid/oversized SSE, duplicate/unknown/DONE, and normal downstream
completion. Prove the recorder still sees a terminal event delivered by the
upstream after downstream closure.

## 3. Prove the CLI evidence path entirely with fake topology

Before protected traffic:

- use only fake upstreams and disposable local listeners;
- assert exact stdout lines and bounded length for all three boundaries and the
  final decision;
- assert stderr is empty, including on downstream disconnect;
- cover each ownership branch and ambiguous branch;
- prove no request/body/header/private value can enter the summary;
- run the focused verifier tests, Ruff, Python compilation, and
  `git diff --check`;
- push the implementation head and require all ten PR checks green on that exact
  head.

A failure in this phase blocks protected traffic.

## 4. Newly authorized protected differential

Only after section 3 passes and the exact head is green, recreate/read the
mode-0600 activation runtime reference without rendering it, verify protected
health/model unchanged, and run a maximum of two minimal text-only protected
streaming diagnostics with no Codex, compiler, cache, image, tool, replay,
governance, customer data, or full-matrix traffic.

Run sequentially:

1. `direct_qwen`: official OpenAI client -> scrubbed disconnect-safe relay ->
   protected Qwen.
2. Run the composed diagnostic only if direct evidence has a valid
   `response.completed`: official client -> disposable Gateway/PostgreSQL ->
   signed disconnect-safe relay -> exact Local PR #7 -> scrubbed Qwen relay ->
   protected Qwen.

Use one synthetic owner/key/session/repository and strict-bounded accounting.
No retry is permitted in this round.

## 5. Ownership decision and conditional action

Apply only the recorded safe facts:

- Direct upstream normally closes without `response.completed`:
  `qwen_owned`. Gateway must not fabricate completion. Stop with a precise
  Local Coding compatibility handoff; do not mutate Gateway product code.
- Direct has valid completion, but Local output normally closes without it:
  `local_owned`. Stop with a precise Local Coding handoff; do not mutate
  Gateway product code.
- Direct and Local have valid completion, but Gateway output normally closes
  without it: `gateway_owned`. Only then make the smallest Gateway correction
  in the conditional paths below.
- All three contain valid completion but the official client closes/fails:
  `official_client_observation`. Correct only the verifier/client observation
  if deterministically reproducible without protected traffic; otherwise stop.
- Any missing summary, upstream truncation, non-SSE response, invalid completion
  shape, recorder overflow, unexplained failure code, or incomplete cleanup is
  `ambiguous_stream_evidence` and fails closed.

Downstream closure alone does not assign ownership when the relay successfully
drains and records the upstream boundary.

## 6. Conditional Gateway correction and final acceptance

Only on exact `gateway_owned` evidence, make the smallest correction within:

    app/slaif_gateway/modules/servers/local_coding/adapter.py
    app/slaif_gateway/providers/openai_compatible.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_responses_streaming.py
    tests/e2e/test_openai_python_client_responses.py

Preserve provider event bytes/order and incremental forwarding. Never fabricate
completion, usage, cost, or tool authority. Preserve cancellation/disconnect,
reservation/finalization/rollback, signed identity, replay/idempotency, route
containment, hosted-search denial, and privacy. Add an exact failing-then-passing
regression.

After a Gateway fix, rerun the complete fake rehearsal and all affected checks.
Then, and only then, run exactly one no-retry full protected
Codex 0.149 -> Gateway -> Local Coding -> Qwen acceptance matrix defined by
155-i. If the differential is `all_boundaries_completed` with the official
client completing, the evidence/verifier defect is closed without a product
change; rerun the complete fake rehearsal and exactly one no-retry full
protected matrix on the unchanged product head.

Do not run the full matrix for Qwen-owned, Local-owned,
official-client-observation, or ambiguous evidence.

## Required acceptance evidence

Diagnostic acceptance requires:

- exact fixed safe summary for every boundary actually run;
- unambiguous decision-table result;
- protected request count within the authorized maximum;
- real Gateway reservation/finalization for the composed diagnostic, if run;
- complete cleanup and unchanged protected health/model.

Integration PASS additionally requires one fresh real full-stack run proving:

- real Codex 0.149 successful ordinary and streaming Responses;
- exact Gateway -> Local Coding route and signed identity accepted;
- PostgreSQL reservation/finalization and correct usage/accounting;
- same-session reuse and independent-session/cache isolation;
- replay/tamper rejection and request idempotency semantics;
- controlled failure rollback with no accounting/state corruption;
- Qwen filtering/privacy invariants;
- no temporary state after cleanup.

Mocks and structural tests do not substitute for this full-stack evidence.

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
    oap/orders/155-k-disconnect-safe-boundary-evidence-and-stream-closure.md
    oap/reports/155-k-disconnect-safe-boundary-evidence-and-stream-closure.md
    oap/active

Conditional product paths are allowed only after exact Gateway-owned evidence
as listed in section 6.

No Local Coding repository mutation, schema/migration/dependency/lockfile,
route/pair/tool policy, Compose/deployment, protected service, release, or
production mutation is authorized.

## Security, privacy, accounting, and cleanup

- Use unique mode-0700 task roots and mode-0600 in-root logs.
- Keep the activation runtime reference and any task-owned credential source
  mode 0600; never print/read them through diagnostic output. Remove both only
  during final cleanup.
- Preserve tracked Local `uv.lock`; never create/use Local `.venv`.
- Use the task-owned `UV_PROJECT_ENVIRONMENT`.
- Clean environments, relays, processes/listeners, PostgreSQL state/new image,
  generated lock/bytecode, runtime reference, credential source, and diagnostic
  state in finally paths.
- Verify Gateway and Local tracked/ignored state clean and protected
  health/model unchanged.
- Keep both PRs open. Coding agent never merges or enables auto-merge.

## Verification and publication

Publish one complete immutable 155-k report with:

- literal implementation head and `Report publication commit: SELF`;
- report parent equal to implementation head and report-only diff;
- full safe boundary summary and exact decision;
- protected ran/not-run counts;
- Gateway/Local/fake/full-matrix ran/not-run ledger;
- focused and all-ten-check ledger on the final implementation head;
- security/privacy/accounting/cleanup/limitations ledger;
- no ownership or acceptance claim beyond evidence.

After report publication, make no repository mutation. Wait for report-head
checks, verify remote topology/mergeability, remove the exact runtime reference
and task-owned credential source without rendering them, signal exact FIFO
`OK`, and stop.

Only a complete integration PASS creates the merge pair. Strategic then
revalidates and merges Local Coding PR #7 first and Gateway PR #291 second.
Do not start Objective 156 or Local Objective 006 before resolution.

