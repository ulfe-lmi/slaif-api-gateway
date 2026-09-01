# OAP Work Order — 155-aa

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: c8dff50ea60d4e4f515d970751508e9630455eda

## One-time human protocol exception

The human explicitly authorized exactly one continuation beyond exhausted
`155-a` through `155-z`: `155-aa` on existing PR #291 from immutable report head
`c8dff50ea60d4e4f515d970751508e9630455eda`.

This exception changes naming/selection only. It does not waive scope, evidence,
privacy, acceptance, immutability, review, merge, security, accounting, or report
constraints. Do not create `155-ab`, generalize multi-letter continuation support,
alter durable OAP governance, or advance another numeric objective. The exact human
authorization and this immutable order are the selector evidence.

## Objective and reason

Distinguish the two remaining `responses_input_item_invalid` branches on the second
real Codex 0.149 request, prove the exact rejected Gateway contract, implement only
the evidence-backed exact-pair correction, remove all temporary diagnostics, and run
one hook-free protected two-turn acceptance.

155-z is immutable and terminally failed. Its single protected diagnostic proved:

- Gateway requests/responses 2, status classes 2xx then 4xx;
- Local requests/responses 1, 2xx SSE;
- protected Qwen inference 1, 2xx SSE normal close;
- second request profile `top_level_function_pair_without_additional_tools`;
- second input types: three messages, reasoning, function call, function output;
- top-level tool counts: custom 1, function 5, tool_search 1, web_search 1;
- Gateway error parameter root `input`, leaf class `other`;
- one finalized accounting row and zero pending.

The immutable z report conservatively retained Gateway error code class `other`.
Post-report read-only source reduction uniquely identifies the raw code as
`responses_input_item_invalid`, but not one of its two reachable branches:

1. malformed input item, parameter shape `input[index]`; or
2. unsupported input-item field, parameter shape `input[index].field`.

The prior safe projection retained the function pair’s fields but omitted the
rejected preceding message/reasoning item’s field set. No correction may be selected
until 155-aa distinguishes these branches and, for a field branch, identifies a
pinned legitimate protocol field from a closed allowlist.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, no auto-merge, at report-only head
  `c8dff50ea60d4e4f515d970751508e9630455eda`.
- Its first parent is diagnostic implementation head
  `65d20cf5d9ed58db95847f8f60f6a122dc3ec77f`; the report commit changes only
  `oap/reports/155-z-exact-second-request-error-and-decisive-closure.md`.
- All ten report-head checks pass. Gateway/Local worktrees and z resources are clean.
- Local Coding PR #7 remains immutable/green at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, read-only checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- Local Coding and protected Qwen are unchanged. The private runtime reference is an
  owner-only mode-0600 regular file with the exact expected key shape; never render
  or retain its values.
- All prior orders/reports, including failed 155-z, are immutable.

## 1. Privacy-safe branch discriminator before traffic

Use pinned Codex 0.149/OpenAI Responses types/source already available in the task
environment and the reviewed 0.149 client module to build a closed allowlist of
legitimate input-item field names. Do not browse mutable general examples or infer
from arbitrary observed strings.

Extend only the task verifier/capture evidence path to correlate the second Gateway
error parameter with the already task-memory-only second request. Retain:

- `input_item_error_shape_class`: exactly `item`, `field`, or `other`;
  - `item` only for full-match `input[index]`;
  - `field` only for full-match `input[index].field`;
- rejected item JSON-type class and allowlisted item-type class;
- sorted, unique rejected-item field-name/coarse-type classes;
- for `field`, the exact field-name class only when it is in the pinned closed
  allowlist; otherwise `other`;
- booleans for parameter index syntactically bounded, in range, selected-item object,
  and rejected field present on that item;
- existing ordered request profiles, Gateway/Local/Qwen counts/status classes,
  function-pair field/type sets, and accounting classes.

The numeric index may be parsed in memory solely to select the item, but must never be
retained, logged, reported, hashed, or emitted. No item value, prompt, content,
reasoning, argument/result, ID, tool name, header, body, SSE, credential, endpoint,
arbitrary field name, or exception text may leave task memory. Unknown or malformed
facts map to `other` and fail closed.

Add pure/fake tests for both branches; dotted/undotted parameters; zero/large/out-of-
range/malformed indices; nested/injected/control-character field text; non-object
items; missing/present fields; unknown fields; duplicate/tampered evidence; ordering,
size and ordinal alignment; and privacy canaries in every prohibited value position.
Prove the discriminator never emits the index or an unallowlisted field.

Update exact 155-aa topology/order/active/task/temp anchors. Run full Ruff,
compilation, focused verifier/privacy/policy tests and all three direct fake
qualification modes. Push the diagnostic-only head and require all ten checks green.
No protected request occurs before these gates.

## 2. Exactly one pre-correction protected diagnostic

On the exact clean green diagnostic head, run exactly one zero-retry real Codex 0.149
-> Gateway -> exact Local -> unchanged protected Qwen diagnostic, direct stdout only
with no redirect, pipe, command substitution, or private output retention.

Require the expected bounded g2/l1/q1 topology and retain the exact branch class,
rejected item type/field classes, safe booleans, raw error class
`responses_input_item_invalid`, accounting snapshot, and cleanup/post-health.

Stop without correction or retry if:

- branch class is `other`;
- the item cannot be safely selected;
- a field name is not in the pinned closed allowlist;
- evidence is inconsistent, malformed, missing, or privacy-unsafe;
- more than one product branch remains reachable; or
- a new external/Local/Qwen boundary appears.

If the diagnostic unexpectedly completes both turns, make no product correction;
continue only through temporary removal and the hook-free final.

## 3. Implement only the proved contract correction

Reproduce the exact branch with pure tests before product edits. Confirm from pinned
Codex/OpenAI source whether the observed item/field shape is legitimate current
Responses semantics.

For an unsupported-field branch:

- accept only the exact proved field on the exact proved item type;
- scope behavior to `codex-0.149-responses-v1`; the reviewed server-pair registry must
  still constrain that client to `local-coding-v1`;
- validate an exact enum/type/cardinality/size contract from pinned authority;
- decide explicitly whether the field is forwarded because it is upstream semantic,
  or stripped during client normalization because it is client-only metadata;
- if stripped, exclude it from upstream bytes, signing, accounting estimates,
  identity/replay authority, storage, logs, and diagnostics;
- do not treat its value as identity/session/tool/route authority.

For a malformed-item branch, accept only a pinned legitimate exact item shape and
validate every field/type/value bound. Do not coerce arbitrary objects or unknown
types.

Negative tests must preserve rejection for generic/default/0.147 clients, non-Local
routes, wrong item types, wrong field values/types, duplicate fields/items, unknown
fields, malformed/reordered/missing/unbounded tool pairs, smuggled additional tools,
hosted search/MCP authority, cross-key/session/route replay, content/secret leakage,
and quota/replay failures before provider side effects as currently required.

Do not modify Local Coding or Qwen; do not change first-turn streaming/event
validation; do not weaken tool, hosted-search, identity, replay, route, idempotency,
privacy, reservation, finalization, or PostgreSQL accounting invariants. No schema,
migration, dependency, lockfile, or unrelated refactor is authorized.

## 4. Mandatory removal and hook-free gates

After the correction passes pure/fake tests and before final protected traffic:

- remove all temporary qualification/diagnostic machinery inherited from 155-v
  through 155-aa: production hook/env/writer, rejection/summary/branch artifacts,
  forced failure modes, qualification-only CLI/modes/stages, temporary symbols/paths,
  and diagnostic-only tests;
- preserve the permanent exact product correction, strict negative regressions,
  zero-retry Codex capture configuration, ordinary fake verifier, and permanent
  hook-free `--tool-roundtrip-protected` runner;
- prove absence with AST/source/search over product/scripts/tests, excluding immutable
  OAP history;
- run permanent fake two-turn success, all affected policy/replay/route/accounting/
  identity/privacy/upstream tests, full Ruff, compilation, diff/scope checks;
- push the hook-free implementation head and require all ten checks green;
- revalidate exact Local head and clean checkout, runtime permissions/shape, protected
  model health, zero pending test accounting, and no task root/process/listener/
  container residue. No protected traffic during cleanup/CI.

## 5. One fresh hook-free protected acceptance

On the exact clean hook-free green head, execute exactly one zero-retry permanent
`--tool-roundtrip-protected` run:

real Codex 0.149 -> real Gateway -> exact unchanged Local Coding -> exact unchanged
protected Qwen -> streamed final answer back through Local/Gateway to Codex.

Acceptance requires:

- exactly two successful Gateway requests/responses and no Gateway second-turn 4xx;
- exactly two successful Local requests/responses;
- exactly two successful Qwen inferences for the intended topology, normal close;
- one valid function-call lifecycle, one client function execution/result, accepted
  adjacent second-turn continuation, and a normal final message/completion;
- expected created/completed cardinality and valid detailed usage for each turn;
- correct signed identity, same-session reuse, independent-session isolation,
  replay/idempotency/tamper/route containment, hosted-search absence;
- two finalized reservations/ledger rows as required, coherent aggregate usage,
  zero failed/estimated/pending accounting residue;
- no Gateway-induced Local disconnect, no secret/content/internal-header retention,
  complete cleanup and protected post-health.

Do not retry a failed final. If a new reason fails, publish only its narrowest safe
evidence and stop; do not create `155-ab`.

## Allowed paths

    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/services/responses_gateway.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/upstream_request_contracts.py
    app/slaif_gateway/schemas/openai.py
    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_codex_client_modules.py
    tests/unit/test_responses_request_policy.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_upstream_payload_reconstruction.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/e2e/test_openai_python_client_responses.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-aa-input-item-branch-and-hook-free-acceptance.md
    oap/reports/155-aa-input-item-branch-and-hook-free-acceptance.md

Do not alter durable OAP protocol/constitution files unless an actual repository test
rejects the literal human-authorized selector. If that happens, stop and report the
exact test rather than generalizing multi-letter continuations.

## Report and handoff

Publish one immutable report-only commit. `RESULT=PASSED` requires the fresh decisive
hook-free protected acceptance; otherwise `RESULT=FAILED`. Record the human exception,
activation/diagnostic/correction/cleanup/final/report topology, exact safe branch and
pinned authority, negative/privacy/security/accounting evidence, all checks, live
counts/usage/close, hook absence, and cleanup without prohibited values.

On pass, post the hook-free Gateway implementation and report heads directly to Local
Coding PR #7 for prepared 005-n. Do not merge/auto-merge. Require all ten report-head
checks, then write exactly two response FIFO bytes `OK` once.
