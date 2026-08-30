# OAP Work Order — 155-q

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 306ecb186b5c12db991a684e7c04e5c9f174eba2

## Objective and reason

Qualify the first legitimate protected Qwen/vLLM Responses SSE event rejected
by Gateway, add only its exact bounded validation if justified, remove the
temporary diagnostic hook, and prove one final protected composed stream with
terminal usage/accounting and no Gateway-induced Local disconnect.

The 2026-08-30 PR #291 comment “Cross-repository handoff — Local Coding 005-l
to Gateway PR #291” is authoritative and supersedes the prior unqualified
local_qwen_owned hold for this failure.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-p report
  head 306ecb186b5c12db991a684e7c04e5c9f174eba2; first parent is
  a8a2a7a8a2e84fbe7dd42658173dd6358f709444, and only the exact 155-p report
  changed.
- All ten Gateway report-head checks pass.
- Local Coding PR #7 handoff report head is
  1a87ce1c6628885e567cecc8f4a9e78ce7078341; implementation parent
  2d1e362f4e1bf7eb6b4f29f9f116ed612fce9e78; report-head test passes.
- A clean detached, read-only Local dependency checkout exists at
  /home/ubuntu/codex-work/slaif-local-coding-005l at that exact report head.
- Local 005-j proves Local -> protected Qwen 2xx SSE, real reasoning events, one
  valid created/completed lifecycle with usage, normal close, and byte/digest-
  equivalent Local forwarding. No Local production correction was required.
- Local 005-l proves that in composition Gateway receives created, emits its
  typed error, and cancels the downstream Local stream. Its Local disconnect
  counter is downstream cancellation, not Qwen failure.
- Gateway source matches that wire lifecycle: every event passes through
  ResponsesStreamEventValidator.validate(); a legitimate rejected event
  produces responses_stream_event_not_supported, incomplete accounting, a
  typed Gateway error, and stream termination.
- Gateway, both Local worktrees, and task state are clean. No runtime reference,
  credential source, listener, process, artifact, or container remains.

## 1. Pure validator reproduction before protected traffic

Exercise every existing ResponsesStreamEventValidator branch with pure fake
tests, including:

- text lifecycle;
- output-item/message/reasoning lifecycle;
- reasoning part/text/summary events;
- function/custom-tool deltas and done events;
- terminal completed usage/status/output relations;
- provider failure events;
- web-search gated events;
- ordering/state prerequisites, duplicates, bounds, sizes, wrong types, missing
  required fields, and unknown/extra authority-bearing fields.

Preserve deny-by-default hosted-tool/search authority. Do not broaden any event
type or shape in this phase.

## 2. Temporary privacy-safe rejection evidence

Add the smallest temporary, opt-in qualification hook around the existing
validator rejection path. It may record only the first rejected event:

- bounded event type (strict Responses event-name grammar and length; otherwise
  other);
- sorted bounded top-level field names and JSON type classes;
- sorted bounded immediate nested-object field names/type classes;
- finite validator profile booleans/classes;
- fixed rejection outcome/code.

Never retain or emit values, deltas, text, IDs, reasoning, usage values, bodies,
headers, credentials, signatures, sessions, endpoints, error messages, or
arbitrary exceptions. Bound field count, key length, nesting depth, and output
bytes.

The hook must be disabled when its exact task environment is absent; allowed
only in the disposable test/qualification environment; atomically write-once to
a validated mode-0700 task root as mode 0600; incapable of following symlinks
or overwriting; and absent from the final implementation tree and production
behavior after qualification.

Pure tests must prove exact safe output and raw/private-marker exclusion.

## 3. Exact pre-qualification gate

Before the first protected request:

- pin Gateway topology to 155-q and Local dependency to exact report head
  1a87ce1c;
- use the detached Local checkout read-only; never edit/commit/push Local;
- run the exact Gateway -> Local -> fake-Qwen composed stream and require
  terminal completion, finalized accounting, and zero rejection evidence;
- run affected validator, streaming, accounting, privacy, official-client E2E,
  focused verifier, Ruff, compilation, and git diff --check;
- push the temporary qualification head and require all ten checks green.

Any failure blocks protected traffic.

## 4. One protected qualification request

After section 3 passes, run exactly one minimal text-only protected composed
standard stream through official client -> disposable Gateway/PostgreSQL ->
exact Local 1a87ce1c -> unchanged protected Qwen.

Use no direct-provider request, tools, images, governance/customer data, or
retry. Stop at the first rejected event and retain only the safe rejection
artifact plus fixed accounting/Local-disconnect facts.

If no rejection occurs and terminal/accounting pass, skip directly to final
cleanup/report; do not send a redundant final stream.

## 5. Event-shape decision

Compare the safe rejected shape against current official OpenAI Responses
streaming event schemas/types available in the pinned SDK, current vLLM
OpenAI-compatible Responses semantics, and the exact Codex 0.149 Gateway module
contract and ordered state machine.

If malformed, provider-specific, authority-widening, unbounded, or not supported
by legitimate current semantics, make no Gateway relaxation and publish the
precise external handoff.

If legitimate, implement only that exact event type/shape and state transition.
Do not accept by type alone and do not globally permit unknown events.

Required negative tests include extra fields, wrong types, missing required
fields, invalid indices/IDs/statuses, size overflow, invalid ordering/orphans,
duplicates, lifecycle mismatch, and content/tool-authority smuggling.

## 6. Remove qualification hook and prove final tree

Before final protected verification:

- remove every temporary hook, environment variable, artifact writer, and
  qualification-only production path;
- retain only the exact validator correction and permanent tests/docs;
- prove production tree cannot emit/persist rejected-event shapes;
- run affected unit/E2E/privacy/accounting tests, complete fake composition,
  and all ten checks on the exact final implementation head.

## 7. One final protected composed stream

Run exactly one no-retry final composed standard stream against the same exact
Local report head. Require:

- 2xx SSE and official-client completion;
- one valid response.created and one terminal response.completed;
- valid terminal status/output/usage and response-ID relation;
- normal close;
- Gateway reservation and ledger finalized with correct nonnegative usage;
- one provider call;
- no responses_stream_event_not_supported or Gateway error event;
- zero Gateway-induced Local downstream-disconnect delta;
- complete disposable cleanup and unchanged protected service/model.

Do not run the broader Codex/governance/image/isolation/replay matrix in this
round. A fully green immutable Gateway report is the resume artifact for Local
strategy to run that remaining matrix.

## Allowed paths

Temporary qualification and final correction may touch only:

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
    oap/orders/155-q-qualify-rejected-qwen-event-and-final-stream.md
    oap/reports/155-q-qualify-rejected-qwen-event-and-final-stream.md

No Local Coding or Qwen mutation, schema/migration/dependency/lockfile,
route/pair/request-tool policy, Compose/deployment, release, or production
service mutation is authorized.

## Security, accounting, cleanup, and publication

Preserve incremental forwarding, client disconnect/cancellation, quota
reservation/finalization, PostgreSQL authority, replay/idempotency, signed
identity, Local route containment, hosted-search denial, and raw-content privacy.

Use unique mode-0700 roots and mode-0600 artifacts. Runtime reference and task
credential source are temporary persistent secret material; never render them;
remove them after report publication. Remove detached task environments,
processes/listeners, PostgreSQL/container/image state, bytecode/locks, and
qualification artifacts. Preserve the clean exact Local dependency checkout
until the report is published; remove its worktree only after coordinated
evidence no longer needs it.

Publish one immutable 155-q report with literal final implementation head,
Report publication commit: SELF, report-only topology, exact safe rejected
shape, legitimacy decision and source basis, exact correction/negative tests,
qualification/final protected counts, terminal/accounting/Local-disconnect
facts, checks, privacy/security/cleanup, and limitations.

After publication make no repository mutation. Wait for report-head checks,
verify topology/mergeability, remove exact runtime/credential/temporary artifact
state without rendering, signal exact FIFO OK, and stop.

No merge/auto-merge, Objective 156, release, cutover, certification, or MVP
completion claim is authorized by this round alone.

