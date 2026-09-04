# OAP Work Order — 155-ab

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 9b99c0c52e2786598efba23767aa2635ffde080a

## Human-authorized continuation and architectural decision

The human explicitly authorized one further bounded continuation, `155-ab`, after
immutable 155-aa report head `9b99c0c52e2786598efba23767aa2635ffde080a`.
This is a naming/selection exception only and does not authorize `155-ac`, a general
multi-letter protocol, weaker evidence, wider scope, or altered merge/release rules.

The architectural decision is fixed:

> Canonicalize away a proven-empty Codex compatibility artifact; never manufacture
> missing reasoning identity and never generalize the exception to state-bearing
> reasoning.

Do not synthesize an `rs_*`, UUID, hash-derived, positional, request-derived, or any
other reasoning ID. Do not accept arbitrary ID-less reasoning in strict policy.

## Objective and reason

Prove that the exact real Codex 0.149 rejected reasoning object is semantically empty;
if and only if proven, remove that one exact versioned compatibility placeholder in
the Codex 0.149 client canonicalization before ordinary strict Responses validation,
remove all temporary diagnostics, and execute one hook-free real protected two-turn
acceptance through unchanged Local Coding and Qwen.

155-aa is immutable and terminally failed. Its single protected diagnostic selected
the `responses_input_item_invalid` malformed-item branch and safely observed one
object of type `reasoning` with field/type classes `content:array`,
`encrypted_content:null`, `summary:array`, `type:string`, with no observed `id` field.
It did not retain content/summary cardinality, so emptiness is not yet proved and no
product correction exists.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, no auto-merge, at report-only head
  `9b99c0c52e2786598efba23767aa2635ffde080a`.
- Its first parent is diagnostic/governance implementation head
  `d4fbb42447409d7e7bca0843a8a2b70008c957f9`; the report commit changes only
  `oap/reports/155-aa-input-item-branch-and-hook-free-acceptance.md`.
- All ten report-head checks pass. The Gateway and exact Local checkout are clean.
- The repository governance test permits ordinary one-letter selectors and exact
  `155-aa` only; 155-ab must add only the exact current exception while continuing to
  reject `155-ac`, other multi-letter objectives, malformed lengths, and suffixes.
  Do not alter AGENTS or durable OAP communication documents.
- Local Coding PR #7 remains immutable/green at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, read-only checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- Local Coding, protected Qwen, Codex, and accepted first-turn stream behavior are
  unchanged. Strategic provides the private mode-0600 runtime reference before
  signaling; never render or retain its values.
- Every prior order/report, including failed 155-z and 155-aa, is immutable.

## 1. Prove exact semantic emptiness before production changes

Extend only the privacy-safe transient verifier discriminator. For the selected
second-request `reasoning` item, retain exactly these bounded facts:

- item type is exactly `reasoning` (boolean);
- `id` state is `absent`, `null`, or `other`;
- `content` state is `empty_array`, `nonempty_array`, `absent`, or `malformed`;
- `summary` state is the same closed class;
- `encrypted_content` state is `null`, `absent`, `non_null`, or `malformed`;
- unexpected semantic/state-bearing fields present (boolean);
- exact allowed-key-set match (boolean);
- exactly one candidate placeholder in the request (boolean);
- candidate immediately precedes one adjacent `function_call` /
  `function_call_output` pair (boolean);
- `exact_empty_reasoning_placeholder` predicate (boolean).

The predicate is true only when:

1. item is an object and `type == "reasoning"`;
2. `id` is absent or explicitly null;
3. `content` exists and is exactly an empty JSON array;
4. `summary` exists and is exactly an empty JSON array;
5. `encrypted_content` exists and is exactly null;
6. keys are exactly `{type, content, summary, encrypted_content}` or those keys plus
   `id` whose value is null;
7. exactly one such candidate exists in the request;
8. it immediately precedes exactly one adjacent function-call/output continuation.

Retain no field values, reasoning text, prompt/content, ID, index, body, SSE, tool
name/arguments/result, headers, credentials, endpoint, digest, or exception text.
Nonempty arrays are recorded only as `nonempty_array`; non-null encrypted content only
as `non_null`. No lengths beyond empty/nonempty and no arbitrary keys may be emitted.

Add pure/fake tests for every state and conjunction, including absent/null/non-null
ID; absent/empty/nonempty/malformed content and summary; absent/null/non-null/
malformed encrypted content; every extra field; non-object/wrong type; duplicate
candidates; candidate without/improperly ordered/multiple tool pairs; privacy
canaries; tampered/duplicate/misaligned evidence; and source/AST proof that no ID
generator or raw-value sink is involved.

Update exact 155-ab topology/order/active/task/temp anchors and the governance test to
permit only ordinary one-letter IDs plus exact `155-aa` and `155-ab`; prove `155-ac`,
`156-aa`, arbitrary multi-letter IDs, suffixes, and malformed forms fail.

Run full Ruff, compilation, focused verifier/governance/privacy/policy tests, all
three direct fake qualification modes, push the diagnostic-only head, and require all
ten checks green. No protected request occurs first.

## 2. Exactly one protected empty-predicate diagnostic

On the exact clean green diagnostic head, run exactly one zero-retry real Codex 0.149
-> Gateway -> exact Local -> unchanged protected Qwen diagnostic, direct stdout only
without redirection, piping, command substitution, or private output retention.

Require expected g2/l1/q1 boundary facts and the complete closed predicate result.
If `exact_empty_reasoning_placeholder` is not true, or any constituent is unexpected,
stop with an immutable FAILED report: no correction, retry, or final.

If the run unexpectedly completes two turns, make no product correction; continue
only through temporary removal and hook-free final verification.

## 3. Exact compatibility canonicalization

Only after the predicate is proven true, implement a versioned client compatibility
canonicalization before strict Responses input validation.

The canonicalization must:

- live in the exact `codex-0.149-responses-v1` client module and advance its reviewed
  compatibility/module version;
- remain constrained by the static registry to the exact `local-coding-v1` server
  pair; add a test proving no other server pair can use it;
- remove exactly one object matching all section-1 predicate conditions;
- require `stream=true`, a nonempty reviewed top-level local function/custom taxonomy,
  and the placeholder immediately before exactly one adjacent function-call/output
  pair;
- operate on a defensive deep copy and preserve the order and exact values of every
  remaining input item and top-level field;
- pass the canonicalized body to ordinary strict request policy, replay, route,
  accounting, upstream reconstruction, exact-byte signing, and transport;
- leave no replay candidate or accounting material for the removed object, because
  the proven object has no ID, encrypted content, summary/content parts, or other
  state;
- emit no runtime log/audit/metric/content marker for the removed object beyond an
  existing bounded compatibility profile/version fact.

It must not remove more than one candidate, any candidate outside the exact function
continuation position, or any near-neighbor. Near-neighbors must remain unchanged by
the client module and fail through ordinary strict validation where invalid.

Required positive tests cover absent ID and explicit null ID for the exact empty
shape, exact remaining-body equality, function-call/output chronology, top-level
tool preservation, upstream body equality, signed request behavior, accounting
estimation, and exact pair selection.

Required negative tests prove no canonicalization for:

- nonempty summary or content;
- non-null or absent encrypted content;
- absent/malformed content or summary;
- non-null ID or any valid ID-bearing reasoning item;
- unexpected/additional fields, including status/phase/internal metadata;
- wrong/malformed field types or item type;
- duplicate placeholders;
- no, reordered, mismatched, duplicate, custom-substituted, or unbounded tool pairs;
- non-streaming requests or missing/invalid local tool declarations;
- default, Codex 0.147, or any non-Local server pairing.

Ordinary valid reasoning items containing IDs must remain byte/value-equivalent and
continue through the preexisting strict replay path. No ID manufacture, replay bypass,
tool-authority widening, hosted search authority, route widening, identity/session
authority, content retention, or quota/accounting weakening is permitted.

Do not modify Local Coding, Qwen, Codex, the first-turn stream validator, schema,
migrations, dependencies, lockfiles, or unrelated Gateway behavior.

## 4. Mandatory diagnostic removal and hook-free gates

After product/fake tests pass and before final protected traffic:

- remove all temporary 155-v through 155-ab qualification/diagnostic machinery:
  production hook/env/writer, rejection/summary/item/cardinality artifacts, forced
  failure modes, qualification-only CLI/modes/stages, temporary symbols/paths, and
  diagnostic-only tests;
- preserve only the permanent versioned canonicalization, its strict positive/
  negative tests, zero-retry capture configuration, ordinary fake verifier, permanent
  hook-free `--tool-roundtrip-protected`, and the exact aa/ab governance selector
  exception needed while the objective remains active;
- prove diagnostic/hook/qualification/raw-value/ID-generator absence with AST/source
  searches scoped to product/scripts/tests, excluding immutable OAP history;
- run permanent fake two-turn success, affected client/policy/replay/route/signing/
  upstream/accounting/privacy tests, full Ruff, compilation, and diff/scope checks;
- push the hook-free implementation head and require all ten checks green;
- revalidate exact Local head/cleanliness, runtime permissions/shape, Qwen health,
  clean Gateway worktree, zero pending test accounting, and no task root/process/
  listener/container residue. No protected traffic during cleanup/CI.

## 5. One hook-free protected acceptance

On the exact clean hook-free green head, run exactly one zero-retry permanent
`--tool-roundtrip-protected` execution:

real Codex 0.149 -> Gateway -> unchanged Local Coding -> unchanged protected Qwen ->
streamed final response through Local/Gateway to Codex.

Acceptance requires:

- first Gateway request reaches Local/Qwen once and completes normally;
- second function-result request reaches Gateway;
- exactly one proven-empty placeholder is canonicalized and no state-bearing item is
  removed;
- second request reaches Local/Qwen once;
- function-call/output chronology and replay/integrity checks remain correct;
- final assistant response completes normally with expected terminal semantics;
- no Gateway-generated 4xx and no Gateway-induced Local disconnect;
- valid detailed usage, two finalized reservations/ledger rows as required, coherent
  aggregate accounting, and zero failed/estimated/pending residue;
- signed identity, same-session reuse, independent-session isolation, replay/
  idempotency/tamper/route containment, hosted-search absence, privacy/secret/header
  boundaries, full cleanup, and protected post-health;
- all ten PR checks remain green on the exact hook-free head.

Do not retry a failed final. Publish its narrowest safe evidence and stop; do not
create `155-ac`.

## Allowed paths

    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/services/responses_gateway.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/upstream_request_contracts.py
    app/slaif_gateway/schemas/openai.py
    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_oap_governance.py
    tests/unit/test_codex_client_modules.py
    tests/unit/test_responses_request_policy.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_upstream_payload_reconstruction.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/e2e/test_openai_python_client_responses.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-ab-proven-empty-reasoning-canonicalization-and-acceptance.md
    oap/reports/155-ab-proven-empty-reasoning-canonicalization-and-acceptance.md

No AGENTS/OAP protocol rewrite, general multi-letter support, Local/Qwen/Codex
mutation, arbitrary reasoning acceptance, ID fabrication, authority expansion,
unrelated cleanup, merge, auto-merge, release, or next objective is authorized.

## Report and Local handoff

Publish one immutable report-only commit. `RESULT=PASSED` requires the fresh hook-free
protected acceptance; otherwise `RESULT=FAILED`. Record the human decision,
activation/predicate/canonicalization/removal/final/report topology, exact safe
predicate facts, module/pair version, strict negatives, security/privacy/replay/
accounting evidence, all checks, live counts/usage/close, hook absence, and cleanup
without prohibited values.

On pass, post the hook-free Gateway implementation and report heads directly to Local
Coding PR #7 for prepared 005-n. Do not merge/auto-merge. Require all ten report-head
checks, then write exactly two response FIFO bytes `OK` once.
