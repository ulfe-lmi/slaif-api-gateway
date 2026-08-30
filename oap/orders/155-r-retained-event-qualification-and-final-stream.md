# OAP Work Order — 155-r

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: a5154d68db3999c3df7c8d03cb13eed86c7fcea2

## Objective and reason

Retain and qualify the first protected Qwen/vLLM Responses SSE event rejected
by Gateway, make only the exact validator change justified by current
Responses semantics, remove the temporary qualification path, and prove one
final protected composed stream through Gateway, exact Local Coding, and
unchanged protected Qwen.

155-q sent its one protected qualification request and reproduced the Gateway
typed stream error, but its verifier discarded the already-bounded rejection
artifact with the temporary root before surfacing it. This is a concrete
Gateway verifier evidence-retention defect. It is not a Local/Qwen ownership
finding and does not revive the stale `local_qwen_owned` conclusion.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable
  `RESULT=FAILED` 155-q report head
  `a5154d68db3999c3df7c8d03cb13eed86c7fcea2`; its first parent is
  `a3db9c88065a0cb5d7c0af797332752024d0f289`, and only
  `oap/reports/155-q-qualify-rejected-qwen-event-and-final-stream.md`
  changed.
- All ten Gateway report-head checks pass.
- The 155-q implementation already passes the safe
  `qualification_rejection` object from the mode-0700 temporary root into
  fixed verifier output before cleanup. This correction was pure/fake tested
  after the failed protected request; no second protected request occurred.
- The bounded write-once hook remains opt-in on this unmerged PR. Its prior
  negative tests cover disabled mode, existing/symlinked/wrong-parent paths,
  unsafe root mode, invalid names, bounded fields/nesting, oversized no-write,
  raw/private-marker exclusion, and fake-path artifact absence.
- Local Coding PR #7 remains OPEN at exact immutable report head
  `1a87ce1c6628885e567cecc8f4a9e78ce7078341`; implementation parent
  `2d1e362f4e1bf7eb6b4f29f9f116ed612fce9e78`; signed-contract ancestor
  `356be8345dd71d6fddf829278651d18e485731d4`. The detached checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005l` is exact and clean.
- Accepted Local 005-j/005-l evidence remains authoritative: Local receives a
  protected Qwen 2xx SSE stream containing real reasoning events, one valid
  `response.created`, one valid terminal `response.completed` with usage,
  normal close, and byte/digest-equivalent forwarding. In composition,
  Gateway emits its typed validator error and cancels Local.
- No 155-q task root, runtime reference, credential copy, process, listener,
  container, or Trash copy remains. Gateway and Local checkouts are clean.
- Local Coding and protected Qwen are read-only dependencies for this round.

## 1. Repair and prove the evidence boundary before protected traffic

Update the verifier topology to exact 155-r activation and the immutable 155-q
report/implementation heads. Preserve exact Local report-head topology.

Before any protected request, prove with pure tests that:

- `qualification_rejection` survives temporary-root cleanup and is emitted
  exactly once only when the hook produced the exact bounded schema;
- malformed, extra, nested, oversized, or value-bearing/tampered artifact
  objects cannot be serialized into verifier output;
- fake qualification completes with terminal SSE, finalized accounting, and
  no rejection artifact or `QUALIFICATION_REJECTION` line;
- ordinary/final verifier modes cannot activate the hook;
- every existing `ResponsesStreamEventValidator` lifecycle, ordering, shape,
  size, tool/search authority, provider failure, and terminal-usage branch
  remains covered and fail-closed.

The verifier may emit only the existing bounded event type, sorted bounded
field names/type classes, finite profile classes, and fixed rejection code.
It must never emit values, deltas, text, IDs, reasoning, usage values, bodies,
headers, credentials, signatures, sessions, endpoints, paths, error messages,
or arbitrary exceptions.

Run focused validator/streaming/verifier/privacy/accounting/official-client
tests, full Ruff, AST compilation, and `git diff --check`. Push this
pre-qualification head and require all ten checks green. Then run exactly one
fresh fake composed qualification and require terminal completion, finalized
accounting, zero rejection artifact, and complete cleanup.

Any failure blocks protected traffic.

## 2. One corrected protected qualification request

After section 1 passes, execute exactly one no-retry minimal text-only
protected composed stream:

    official OpenAI client
    -> disposable Gateway and PostgreSQL
    -> exact Local Coding 1a87ce1c
    -> unchanged protected Qwen

Use the opt-in bounded hook. Do not send a direct-provider request, a second
qualification request, tools, images, governance/customer data, or a retry.

Require the verifier to emit exactly one bounded
`QUALIFICATION_REJECTION` record if Gateway rejects. Preserve only that safe
record and fixed request/accounting/disconnect facts. If the stream instead
reaches one valid `response.completed` with usage, normal close, finalized
accounting, and zero Gateway-induced Local disconnect, remove the hook and use
that successful qualification as the final protected proof; do not send a
redundant final request.

## 3. Legitimate-semantics decision

Compare the exact bounded rejected shape against all three current authorities:

1. the pinned official OpenAI Python SDK Responses stream event types/schemas;
2. upstream vLLM OpenAI-compatible Responses source/documentation matching the
   protected service behavior/version as closely as safely verifiable;
3. Gateway's exact Codex 0.149 `codex-0.149-responses-v1 ->
   local-coding-v1` contract and ordered validator state machine.

Use primary sources and record exact package/source versions or commit/tag
identities. No source may be inferred from event-name resemblance alone.

If the event is malformed, provider-specific but not legitimate Responses
semantics, authority-widening, or cannot be justified, make no Gateway
relaxation. Remove the hook, publish the exact external blocker with the safe
shape/source comparison, and do not send a final protected request.

If the event is legitimate, implement only its exact type, required/optional
fields, field types and bounds, response/item/content/index relations, and
ordered state transition. Do not accept by type alone, allow arbitrary extra
fields, globally permit unknown events, weaken hosted-tool/search gates, or
conflate reasoning/content/tool authority.

Required permanent negative tests include extra/unknown authority-bearing
fields, wrong types, missing required fields, invalid indices/IDs/statuses,
size overflow, orphan/invalid ordering, duplicates, lifecycle/response-ID
mismatch, terminal-after-terminal, and content/tool/search smuggling.

## 4. Remove the complete temporary qualification path

Before final protected verification, remove every 155-q/155-r production hook,
environment variable, artifact writer, qualification-only branch/CLI mode, and
temporary safe-shape output path. Retain only the justified validator
correction, permanent tests, final composed verifier, and any narrow truthful
compatibility documentation.

Pure/static tests must prove the final production tree cannot emit or persist
rejected-event shapes. Run the exact Gateway -> Local -> fake-Qwen final
composition and require terminal completion, finalized accounting, normal
close, and zero downstream disconnect. Push the final implementation head and
require all ten checks green.

## 5. One final protected composed stream

Only after section 4 passes, run exactly one no-retry final protected composed
standard stream against the same Local report head. Require:

- 2xx SSE and official-client completion;
- exactly one valid `response.created` and one terminal
  `response.completed`;
- valid completed status/output/usage and response-ID relation;
- normal Local and Gateway stream close;
- exactly one Gateway -> Local and one Local -> Qwen provider call;
- PostgreSQL reservation and ledger finalized with correct nonnegative usage
  and no pending/corrupt accounting state;
- no Gateway error or `responses_stream_event_not_supported`;
- zero Gateway-induced Local downstream-disconnect delta;
- unchanged protected model/service and complete disposable cleanup.

Do not run the broader Codex/governance/image/isolation/replay matrix in this
round. A green immutable 155-r Gateway report is the exact resume artifact for
Local strategy to execute that remaining final acceptance matrix.

## Allowed paths

Temporary evidence work, exact correction, and final cleanup may touch only:

    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_responses_streaming.py
    tests/e2e/test_openai_python_client_responses.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-r-retained-event-qualification-and-final-stream.md
    oap/reports/155-r-retained-event-qualification-and-final-stream.md

No Local Coding or Qwen mutation, dependency/lockfile/schema/migration,
route/pair/request-tool policy, Compose/deployment, release, or production
service mutation is authorized.

## Security, accounting, cleanup, and publication

Preserve incremental forwarding, cancellation semantics, quota reservation and
finalization, PostgreSQL accounting authority, replay/idempotency, signed
identity, Local route containment, provider credential secrecy, hosted-search
denial, and no-default-content/reasoning retention.

Use unique mode-0700 task roots and mode-0600 artifacts. The strategic runtime
reference contains only the protected endpoint and credential-source pathname;
never render, commit, hash, or retain its contents. Pass the protected
credential only to the Local -> Qwen process environment.

Publish one immutable
`oap/reports/155-r-retained-event-qualification-and-final-stream.md` with
literal final implementation head, `Report publication commit: SELF`,
report-only topology, the exact safe rejected shape, source/legitimacy
decision, correction and negative-test ledger, qualification/final protected
request counts, terminal/accounting/disconnect facts, checks, privacy/security,
cleanup, and limitations.

After publication make no repository mutation. Wait for all ten report-head
checks; verify topology, mergeability, clean Gateway/Local state, and exact
resource absence. Permanently delete only exact task roots/runtime/credential
copies without moving secrets to Trash. Signal exactly two bytes `OK` on the
response FIFO and stop.

No merge/auto-merge, Objective 156, release, cutover, certification, or MVP
completion claim is authorized by this round alone.
