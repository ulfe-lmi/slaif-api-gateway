# OAP Work Order — 155-y

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: db7d67a83fa72b6e642147195d759556d33527b0

## Objective and reason

Localize and correct only the second real Codex 0.149 function-result
continuation that Gateway rejected with 4xx before a second Local Coding call,
then close the real protected two-turn path with one diagnostic qualification
and, only after temporary-code removal, one hook-free final.

155-x is immutable and terminally failed. Its bounded evidence proves a moved
Gateway-owned admission boundary: Gateway handled two requests with 2xx then
4xx; Local and unchanged protected Qwen each handled exactly one 2xx SSE request;
Qwen closed normally; neither Gateway nor Local disconnected; no stream-validator
rejection artifact existed; one accounting row finalized with zero pending; Codex
reported `turn_failed`. Therefore the first function-call stream is accepted and
the second request is rejected before provider execution. Do not revisit the
already-corrected `response.output_item.done` shape or modify Local/Qwen.

The 155-x summary's `request_profile_class=other` classified only projection zero,
the initial request, not the rejected second request. It is not evidence that the
second envelope is unsupported. This round must classify the two request ordinals
separately and decide from the actual/pinned Codex contract.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, no auto-merge, at immutable
  report-only head `db7d67a83fa72b6e642147195d759556d33527b0`.
- Its first parent is implementation head
  `00a50beaa91caa524c98476e4c42d86ea0e22e55`; the publication commit changes
  only `oap/reports/155-x-preserved-qualification-output-and-final-closure.md`.
- All ten 155-x report-head checks pass.
- Local Coding PR #7 remains immutable/green at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, with read-only checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- Existing 155-r through 155-x reports and all earlier reports are immutable.
- The exact Codex 0.149 / Local Coding pair, signed identity, first-turn function
  stream, ordinary stream, prompt-cache privacy correction, replay persistence,
  zero-retry capture command, accounting machinery, and fake composed path are
  provisionally green.
- Strategic provides the private mode-0600 runtime reference before signaling;
  never render or commit endpoint/credential values.

## 1. Pure/fake reproduction and pinned contract decision

Before protected traffic, inspect the pinned Codex 0.149 types/source already
available to the repository and the reviewed client/server pairing. Reproduce the
exact two-turn function lifecycle in pure/fake tests, including the expected second
request produced after a first-turn function call with encrypted reasoning when the
real contract includes it.

Record only bounded structural facts:

- request ordinal;
- sorted top-level field names with coarse JSON types;
- bounded ordered input-item type sequence;
- bounded top-level tool-type counts;
- stream boolean class;
- continuation class;
- Gateway status/error-code/error-param class.

No fixture, diagnostic, log, exception, report, or GitHub artifact may retain
prompts, instructions, tool arguments/results, IDs, credentials, bodies, headers,
raw SSE, endpoint values, arbitrary strings, or arbitrary exception text.

Prove why projection zero was `other`, and classify projection one independently.
Determine the first pre-Local Gateway contract producing 4xx. In particular test,
without assuming the answer, whether the legitimate second request is an encrypted
reasoning replay plus one standalone `function_call_output`, rather than an adjacent
`function_call`/`function_call_output` pair in the same request.

Pure/fake evidence must fail on the pre-correction contract for the same bounded
reason and pass only after the correction. If the actual second-turn shape cannot be
established from pinned source/types and exact fake capture, add only a temporary
155-y pair-scoped pre-provider classification hook that emits the safe schema above;
the sole protected post-correction qualification below must both validate the
classification and prove the correction. Do not send a pre-correction protected
request merely to explore.

## 2. Minimum fail-closed correction

If the second envelope is legitimate for pinned Codex 0.149 Responses semantics,
accept only the exact `codex-0.149-responses-v1` -> `local-coding-v1` continuation
shape. Do not globally relax Responses input validation or infer authority from a
caller-controlled value.

If a standalone function output is the proved shape, it must be authorized against
exactly one unexpired first-turn function-call reference already persisted by
Gateway after finalized accounting, for the same authenticated Gateway key, provider,
route, upstream model, function taxonomy/name/namespace, and call identifier. The
output may not create its own authority. Ambiguous, missing, expired, cross-key,
cross-route, unfinalized, wrong-kind, or multiply matching references fail closed
before quota/provider side effects. Reuse existing HMAC-only reference storage where
possible; no schema/migration change is authorized.

Preserve request ordering, cardinality and size bounds. Accept at most the one
function-output continuation required by this lifecycle. Reject malformed fields,
unknown fields, duplicate outputs/call IDs, reordered or mixed call/output shapes,
custom/function kind substitution, undeclared tools, namespace/name mismatch,
smuggled `additional_tools`, hosted/search/MCP authority, unsupported output media,
oversize results, missing ownership, replay across users/keys/routes/sessions, and
replay after expiry. Keep PostgreSQL accounting truth, reservation/finalization,
route containment, signed Local identity, idempotency, privacy, and zero content
retention unchanged.

Do not change Local Coding, Qwen, the resolved first-turn streaming validator, hosted
tool policy, route capabilities outside the exact pair, dependency/lock files,
database models/migrations, or unrelated Gateway behavior.

## 3. Qualification-head gates

Before protected traffic require:

- exact 155-y topology and Local head anchors;
- the pure/fake two-turn test demonstrates the expected initial and continuation
  classes and exact pre-fix failure contract;
- the corrected fake composed run reaches Gateway/Local/Qwen twice and terminates;
- focused request-policy, replay/HMAC ownership, route, tool-policy, identity,
  privacy, accounting, upstream reconstruction, and verifier tests pass;
- all strict malformed/smuggled/duplicate/unbounded/unauthorized/cross-owner/
  cross-route/replay negatives pass;
- provider-failure and forced-validation fake paths remain bounded and leave zero
  pending accounting;
- full Ruff, compilation, diff checks, clean worktrees, pushed head, and all ten
  required PR checks pass;
- the private runtime/credential/model/Local preflight passes without rendering
  protected values.

## 4. Exactly one protected qualification after correction

On the exact clean green qualification head, execute exactly one zero-retry real
Codex 0.149 -> Gateway -> exact Local -> unchanged protected Qwen two-turn function
qualification. Invoke it directly so only its bounded sanitized result is visible;
do not redirect, pipe, command-substitute, or persist private output.

Acceptance requires:

- Gateway requests/responses exactly 2, both successful SSE and no Gateway 4xx;
- Local requests/responses exactly 2, both successful SSE;
- protected Qwen inference count exactly 2 if confirmed as the intended topology,
  both successful with normal close;
- first function-call turn accepted;
- second function-result continuation authorized and forwarded exactly once;
- final assistant/message turn and terminal lifecycle complete normally;
- expected created/completed cardinality and valid detailed usage per turn;
- two finalized accounting rows/reservations as required, no failed/estimated/
  pending residue, and coherent aggregate usage;
- signed identity, same-session reuse, replay/route ownership, hosted-search absence,
  privacy/secret/internal-header boundaries, no Gateway-induced Local disconnect,
  cleanup, and protected post-health.

The temporary safe evidence must state both request profile classes and the exact
allowlisted second-request error class if failure occurs. If qualification fails,
do not retry and do not run the final. Publish the bounded first failing contract in
the immutable FAILED report; infer no broader owner or accounting result.

## 5. Mandatory temporary-code removal and hook-free final

Only after qualification passes:

- remove every 155-y/x/v temporary hook/env/writer, rejection/summary artifact,
  forced qualification mode, classification-only mode/stage/test, and temporary
  path/symbol while preserving permanent corrections, zero-retry capture config,
  ordinary fake verifier, and permanent hook-free `--tool-roundtrip-protected`;
- prove absence with AST/source/search scoped to product/scripts/tests;
- run the permanent fake two-turn path, affected tests, Ruff, compilation, diff
  checks, push the hook-free implementation, and require all ten checks green;
- on that exact clean hook-free green head, revalidate private topology/runtime and
  execute exactly one zero-retry permanent protected two-turn final;
- require every section-4 success fact, complete temporary-hook absence, cleanup,
  and post-health. Do not retry a failed final.

## Allowed paths

    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/services/responses_gateway.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/codex_replay_service.py
    app/slaif_gateway/db/repositories/codex_replay.py
    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_codex_replay_service.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_upstream_payload_reconstruction.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/e2e/test_openai_python_client_responses.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-y-second-turn-continuation-admission-and-final-closure.md
    oap/reports/155-y-second-turn-continuation-admission-and-final-closure.md

No Local/Qwen mutation, schema/migration, dependency/lockfile, generalized Responses
relaxation, hosted/custom/MCP authority expansion, unrelated cleanup, merge,
auto-merge, release, or next numeric objective is authorized.

## Report and cross-repository handoff

Publish one immutable report-only commit. `RESULT=PASSED` requires the decisive
hook-free protected final; otherwise report `RESULT=FAILED`. Record exact activation,
implementation/report topology, preserved 155-r through 155-x reports, bounded
first/second request classifications, exact safe error/result classes, tests/checks,
process counts, accounting, replay ownership, security/privacy, close/cleanup, and
temporary-hook absence without any prohibited value.

On pass, post the hook-free Gateway implementation and report heads directly to
Local Coding PR #7 for prepared 005-n. Do not merge or enable auto-merge. Require all
ten report-head checks, then write exactly two response FIFO bytes `OK` once.
