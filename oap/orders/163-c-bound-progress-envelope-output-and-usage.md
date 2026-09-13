# OAP Work Order — 163-c

PR mode: `AMEND_EXISTING_PR`

## Objective

Close the one remaining semantic/framing-contract inconsistency found by
strategic review of the immutable 163-b report on existing PR #300. The exact
strict Codex/Local `response.created` and `response.in_progress` validator
currently excludes `response.output` and `response.usage` from the one-MiB
envelope bound without validating those two progress-state values separately.
It therefore accepts malformed or arbitrarily large progress payloads that the
finite transport framer correctly rejects. Make the progress-state contract
match the exact reviewed vLLM 0.27.1 emitter and prove that every strict
response event admitted by the typed validator is coherently bounded.

This is a focused same-PR correction. Do not change the derived framer limits,
weaken typed validation, create another PR, perform protected/model traffic, or
publish an intermediate failure report. Diagnose and correct routine failures
inside this continuation, then publish one final immutable 163-c report only
after the exact final implementation head is fully green.

## Reconciled state and independent witness

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Unique Objective-163 PR: #300,
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/300`, OPEN/non-draft,
  mergeable, base `main`, branch
  `oap/163-local-coding-sse-framing-bounds`; no auto-merge and no reviews.
- Mechanically verified remote main remains
  `5ea38325ef3a3ebc69524b4679b795fab0c52935`.
- Current immutable 163-b report/PR head:
  `9497c326a0b45762fe34231bc683171bcd4bea94`.
- Report-only topology is valid: its first parent is final 163-b implementation
  `ee12ff8885b86192e60b302ef76fa089471efb2c`, and it adds only
  `oap/reports/163-b-close-source-and-resource-bound-proof.md`.
- The 163-b report and all earlier reports/orders are immutable and must remain
  in history unchanged. `RESULT=PASSED` in that report is superseded for merge
  qualification by this independently discovered issue.
- Existing 163-b final-head evidence, derived limits, exact 32-field protocol
  fixture, content-state cleanup, real cancellation, accounting behavior, and
  Objective-162 lifecycle tests remain useful and must be preserved.
- Public exact-provider source: vLLM tag `v0.27.1`, commit
  `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`, file
  `vllm/entrypoints/openai/responses/serving.py`, SHA-256
  `628429902ff26b87f86eae1a45297f647f3712d7b421ca9a4866a3fd0f046a5b`.
  The reviewed emitter constructs the shared initial response with
  `output=[]`, `status="in_progress"`, and `usage=None`, then emits that object
  in `ResponseCreatedEvent` followed by `ResponseInProgressEvent`.
- Independent model-free witness against `9497c326...` / implementation
  `ee12ff8...`:

  ```text
  CREATED_WITH_60MB_UNVALIDATED_OUTPUT_USAGE_ACCEPTED=True
  CREATED_WITH_MALFORMED_OUTPUT_USAGE_ACCEPTED=True
  ```

  The witness used the exact strict function profile and a full source-shaped
  progress envelope, replacing `output`/`usage` first with two 30-MB values and
  then with malformed mapping/list values. No provider/model process ran.

## Business and security reason

The production raw SSE bound must be finite before parsing and large enough
for every event the reviewed typed profile intentionally permits. An
unbounded typed progress carve-out contradicts that invariant and makes the
163-b derivation/report claim inaccurate even though the transport itself
fails safely. The correct resolution is to bound the narrow exact-pair typed
progress state to the source-emitted empty/no-usage representation, not to
raise the frame ceiling or add another magic allowance.

## Allowed paths

- `app/slaif_gateway/providers/streaming.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/unit/test_local_coding_sse_framing.py` only for the Objective-163
  obligation manifest or a directly coupled bound regression
- one new content-free source fact fixture under
  `tests/fixtures/codex/0.149.0/`, preferably
  `vllm-0.27.1-responses-progress-emission.json`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/openai-compatibility.md` only if needed to keep the exact pair contract
  synchronized
- `oap/active`
- `oap/orders/163-c-bound-progress-envelope-output-and-usage.md`
- `oap/reports/163-c-bound-progress-envelope-output-and-usage.md`

If a tightly coupled test-only helper outside this list is indispensable,
explain it in the report before changing it. No other production path is
authorized without strategic continuation.

## Required implementation

1. In the exact strict Codex response progress path only, validate the
   separately excluded response fields before acceptance:
   - when `output` is present it must be exactly the empty list `[]`;
   - when `usage` is present it must be exactly `None`;
   - non-empty output, wrong output type, non-null usage, wrong usage type, and
     arbitrarily large values fail closed;
   - absence may remain accepted if needed for existing intentionally minimal
     strict fixtures because absence contributes no unbounded state.
2. Keep the completed terminal contract unchanged: terminal `output` and
   `usage` continue through their existing independent strict cardinality,
   semantic-size, shape, usage, lifecycle, call/item/sequence, and terminal
   consistency validation.
3. Keep the exact 32-name response-envelope allowlist and its one-MiB
   non-output/usage serialization ceiling. Do not re-add `error`, `store`,
   `prompt_cache_key`, or any provider echo not in the pinned source model.
4. Do not change `MAX_CODEX_TYPED_RESPONSE_SEMANTIC_BYTES`, any SSE
   line/frame/joined-data/segment constant, Local adapter behavior, error code,
   event rewriting, raw/accounting semantics, or provider/client selection.
5. Add a content-free source fact pinned to the exact serving file/tag/commit/
   digest and the initial `output=[]`, `status=in_progress`, `usage=None`
   emission. Test its digest and required fact values without importing or
   initializing vLLM.
6. Add strict positive tests for exact source-shaped created and in-progress
   events, including full default/null fields, empty output, and null usage.
   Preserve the maximum valid 64-event lifecycle/framer proof.
7. Add explicit negative controls for both `response.created` and
   `response.in_progress` covering at least:
   - non-empty output list;
   - output mapping/string/null or another wrong representation as applicable;
   - non-null otherwise-shaped usage;
   - malformed usage type; and
   - a generated large value demonstrating rejection by typed validation.
   Verify failures do not echo the supplied content.
8. Audit all three exact strict response envelope states—created, in-progress,
   completed—and document/test that every field excluded from the envelope
   byte calculation is either source-fixed and small in progress or separately
   bounded in completion. If another direct progress carve-out has the same
   defect, correct it here rather than reporting another intermediate NO-GO.
9. Extend the independent literal Objective-163 obligation set and map with
   separately named created/in-progress positive and negative nodes. Require
   exact set equality, collect every mapped node, and execute every unique node
   with no missing nodes or skips. Do not map one parameterized sibling as
   proof of another sibling.

## Fail-closed and preserved invariants

Preserve all current checks for unknown fields, response/item/call identity,
declared tools, sequence/order monotonicity, duplicate lifecycle events,
function/reasoning/message content bounds, terminal output/usage consistency,
zero-argument and ordinary function lifecycles, replay/HMAC behavior,
provider accounting, cancellation/upstream close, malformed/truncated streams,
and terminal success. Preserve default/other profile behavior. The rule is
owned by the exact versioned strict Codex/Local validator path, not a generic
provider-name exception.

No content, reasoning, tool arguments, response bodies, identifiers, secrets,
or canary values may enter reports, logs, metrics, diagnostics, audit rows, or
accounting metadata. Only content-free sizes/types/source facts may be used as
evidence. PostgreSQL remains accounting truth; no schema or reservation law
changes are authorized.

## Verification

Use the existing clean Objective-163 worktree and environment. No Qwen, Local
service mutation, GPU, protected inference, Codex evidence-tool action, real
provider request, deployment, release, email, or production credential.

At minimum:

1. Run the focused strict Responses and Local framing unit files, including the
   exact model-free witness converted to negative regression tests.
2. Run all 34 previously mapped nodes plus every new 163-c node from the
   independent obligation map; mechanically prove `missing=[]` and zero skips.
3. Rerun the complete affected unit/governance set used by 163-b.
4. On one fresh uniquely named task PostgreSQL database, rerun the complete
   official-client Responses E2E file and required PostgreSQL integration files
   if the existing test architecture requires DB state for the mapped set.
   Reconcile zero pending/reserved state, drop every exact Objective-163 task
   database, and confirm no `slaif_oap163%` database remains.
5. Run Ruff format/check, compile/static JSON validation, and `git diff --check`.
6. Push the implementation to the existing branch, wait for all ten required
   checks on that exact implementation head, and resolve any routine failure
   before report publication.

Focused verification is sufficient; do not run protected inference or invent
a full local matrix beyond the changed boundary and the normal GitHub gate.

## Documentation and report

Update the framing/Responses contract to state explicitly that progress
`output` is absent/empty and progress `usage` is absent/null, while completed
values are separately strictly bounded. Keep the 4-MiB and SSE equations
unchanged unless the requested source audit proves a direct arithmetic error;
if so, correct the coherent contract inside this same continuation.

Publish exactly one immutable report at
`oap/reports/163-c-bound-progress-envelope-output-and-usage.md` only after the
final implementation is pushed and every required implementation-head check is
successful. The report must include:

- `RESULT=PASSED` or a precise genuine authority-boundary reason;
- PR/base/branch, activation base, all b/c implementation commits, and exact
  implementation head;
- `SELF` report commit whose first parent is that implementation head and whose
  sole changed path is the 163-c report;
- source tag/commit/path/digest and new fixture digest;
- before/after witness results and exact created/in-progress negative nodes;
- full audit result for every excluded response field/state;
- local/mapped/E2E/PostgreSQL/static counts and exact commands;
- exact ten-check implementation-head GitHub evidence;
- database reconciliation/removal and privacy/accounting statements;
- diff scope, corrected failures, docs impact, and limitations;
- literal final labels:

  ```text
  PROGRESS-OUTPUT-EMPTY-ONLY = YES|NO
  PROGRESS-USAGE-NULL-ONLY = YES|NO
  ALL-EXCLUDED-RESPONSE-FIELDS-BOUNDED = YES|NO
  VLLM-0271-PROGRESS-SOURCE-PINNED = YES|NO
  MAXIMUM-TYPED-EVENT-WITHIN-FRAMER = YES|NO
  OBJECTIVE-163-REGRESSION-ACCEPTED = YES|NO
  TASK-DATABASES-CLEANED = YES|NO
  PROTECTED-ACCEPTED = NO
  MERGED = NO
  RELEASE-READY = NO
  ```

Do not merge or enable auto-merge. Signal exact response `OK` only after the
immutable report commit is pushed and its topology is verified. Strategic owns
final report-head CI review, merge, remote-main verification, timing, and
post-merge CI.

