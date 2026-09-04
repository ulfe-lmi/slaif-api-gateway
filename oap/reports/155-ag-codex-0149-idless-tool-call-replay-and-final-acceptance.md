# OAP Report — 155-ag

RESULT=FAILED

Report publication commit: SELF

## Topology

- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `37e923304cf4b1cdb4fb9f8faefe4a7b2fb6db6e`
- Starting head was the immutable 155-af report-only commit; its first parent
  was implementation head `34ab5afd09af026286779838db21cddad1717877`.
- Activation head: `a570d6087ca488bc7fb1ec9a9ed0e51266b52b15`.
- Final implementation head: `b171ada9ed3320c57186283ed4ce6ffd4389a7c3`.
- No merge or auto-merge was performed.

## Source authority and reproduction

The official OpenAI Codex annotated tag `rust-v0.149.0` was verified as tag
object `a4e15bf371341b067c8278d3b70b1a8c7b3d793e`, peeling to commit
`758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`. The inspected source facts were
limited to source paths and structural predicates: function/custom tool-call
item IDs are optional while call IDs are mandatory; matching output IDs are
optional; `ResponseItemId::is_prefixed()` requires nonempty text on both sides
of `_`; request preparation clears a non-prefixed existing ID and generates no
replacement immediately before Responses HTTP/WebSocket construction.

The disposable actual-Codex pre-fix reproduction used the task-local pinned
`@openai/codex@0.149.0` executable against Gateway, Local Coding, and fake
Qwen. Bounded evidence was:

- selected tool type: `function`;
- function-call item ID state: `absent` after Codex preparation;
- prefix predicate class: `none` because the item ID was absent;
- call-ID state: `present_valid`;
- adjacent matching output: `true`;
- Gateway/Local/Qwen request counts: `2/1/1`;
- fixed failure family: `codex_tool_roundtrip_invalid`, parameter root
  `input`; the harness retained only bounded field/type projections and emitted
  no raw field or value;
- accounting: one finalized row and zero pending state.

This matched the 155-af mechanism. No protected request occurred during the
pre-fix reproduction.

## Implementation

The exact `codex-0.149-responses-v1` client policy now owns three default-false
facts: nullable/absent function-call item IDs, nullable/absent custom-tool-call
item IDs, and call-ID-anchored ID-less replay. The static registry pairing is
unchanged and remains exactly `codex-0.149-responses-v1` to
`local-coding-v1`. No database schema or Local/Qwen code was changed.

Present item IDs retain the existing item-HMAC path and never downgrade to a
call-only lookup. An absent/null tool-call item ID is deferred until read-only
exact Local-pair route resolution, then uses a same-key, same-kind, unexpired
call-HMAC lookup. The implementation requires exactly one row, binds the row
to its stored HMAC key version with constant-time comparison, checks the stored
tool and route/provider/model facts, and fails closed on zero or ambiguous
matches. No ID is synthesized.

The verifier also gained bounded mappings for the three previously omitted
reasoning/replay policy errors and content-free reproduction projections.

## Checks and fake evidence

The focused policy, replay service, verifier, streaming, client-module,
governance, and request-policy suites passed. Ruff passed. The PostgreSQL
replay integration test was collected locally but skipped because no test
database was configured. The complete local unit suite had one unrelated
environment failure in the pre-existing Qwen/Codex candidate test because it
used host `/usr/bin/codex` rather than the pinned task-local binary.

All ten required GitHub checks passed on implementation head `b171ada` before
the protected diagnostic. The fake gates passed for the normal prefixed-ID
roundtrip and the non-prefixed-ID roundtrip, each with two Gateway/Local turns,
two fake-Qwen inference turns, one function lifecycle, one message lifecycle,
one function output, two accounting rows, and zero pending state. Fake provider
failure produced one released reservation/failed ledger outcome. Fake
validator rejection produced bounded write-once validator evidence and one
released/failed outcome.

## Protected diagnostic

Exactly one zero-retry protected diagnostic was run after the green
implementation head. It failed at the fixed Gateway-facing SSE validation
gate with:

`composed_tool_roundtrip_gateway_sse_invalid`

The runner did not retain a safe per-boundary artifact for this hook-free
failure, so no protected event-shape, ownership, replay, or accounting claim
is made beyond that fixed failure stage/code. No retry or second protected
request occurred, and the result is not acceptance.

## Scope and cleanup

Implementation changes were limited to the 155-ag client contract, exact
request-policy/replay integration, replay repository lookup, verifier, focused
tests, PostgreSQL replay coverage, and the three named compatibility/accounting
documents. The immutable prior order/report and historical fixtures were not
rewritten. The final report is the only new report path.

The mode-0600 task runtime reference was removed after the diagnostic and
verified absent. The exact 155-ag temporary roots, installed Codex, verifier
processes, listeners, task container, and task database were checked absent;
the linked Local Coding checkout remained unchanged and clean. No credential,
endpoint, raw request/body, item ID, call ID, digest, signature, prompt,
provider response, or arbitrary exception text was persisted or reported.

Acceptance was not established. The PR remains open and unmerged; this report
hands off the narrow protected Gateway SSE failure without inferring ownership
or authorizing a retry.
