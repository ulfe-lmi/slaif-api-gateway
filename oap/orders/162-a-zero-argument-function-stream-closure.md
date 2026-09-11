# OAP Work Order — 162-a

PR mode: `CREATE_NEW_PR`

## Objective

Implement and qualify the smallest safe compatibility rule for the exact
`codex-0.149-responses-v1 -> local-coding-v1` pair when reviewed vLLM 0.27.1
emits a declared zero-argument function as:

```text
response.output_item.added(arguments="")
-> no response.function_call_arguments.delta
-> no response.function_call_arguments.done
-> response.output_item.done(arguments="")
-> response.completed with the same empty-argument function semantics
```

The rule must be request-derived, declarative, version-owned, pair-local, and
default false. It must not relax ordinary Responses, Codex 0.147, another
Codex 0.149 server pair, custom tools, hosted tools, or a non-eligible function.

This is the Gateway-owned resolution of the human-accepted Local 005-am
source handoff. Do not request or run another pre-fix protected reproduction.

## Business and compatibility reason

No-parameter local functions are legitimate, and the exact installed vLLM
0.27.1 source can close a named function item without argument delta/done
events when its accumulated argument text is empty. Current Gateway main
requires a non-empty delta and an arguments-done transition before it accepts
the completed item, so the reviewed producer and consumer disagree. The
failure is in the Gateway's exact pair stream contract, not a request for a
Local workaround or another diagnostic framework.

The change must preserve fail-closed stream state, replay/HMAC ownership,
PostgreSQL accounting truth, provider-secret isolation, and content-minimizing
defaults. It must not turn an empty string into a generic JSON or protocol
exception.

## Reconciled authoritative state

- Repository: `ulfe-lmi/slaif-api-gateway`; default/base branch `main`.
- Exact activation base/current remote main:
  `d142fd7f04c46fac3469b9b9bba1bd2068aabad8`, the normal merge commit for
  Objective 161 / PR #298. Its parents are prior main `910ddaa...` and final
  immutable 161-r report `ad1c556...`; tree `5d03e894...`.
- Objective 161 is terminally merged. `oap/active` intentionally remained at
  terminal `161-r`; its timing-ledger resolution is complete.
- PR #298 is MERGED at 2026-09-09T11:35:20Z. Its unique branch/report head is
  `ad1c556a539130c08dc1063b3e9a25a0af2e5a85`; report-only first parent is
  implementation `50dcc3b85d614eb1d0c6196595bf22ef5779f846`.
- All ten PR #298 final-head checks and all ten post-merge main checks are
  SUCCESS. No review or unresolved review thread and no auto-merge exists.
- No Objective-162 PR or `oap/162-*` remote branch exists.
- Existing open Gateway PRs #291, #250, and #224 are unrelated. PR #291 is the
  old Objective-155 evidence branch and is DIRTY; do not reuse or modify it.
- `main` has no branch protection configured. This does not weaken this order's
  strategic final-head check and review gates.
- Only published release remains prerelease `v0.1.0-rc.1`. This objective is
  not a release, deployment, production, certification, or compliance action.
- Create exactly one new PR from the exact base. Suggested branch:
  `oap/162-zero-argument-function-stream-closure`; suggested title:
  `OAP 162: Accept pair-scoped zero-argument function stream closure`.

## Accepted source handoff and immutable pins

- Human steering and Local 005-am are authoritative pre-fix proof. Gateway
  PR #298 handoff comment:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298#issuecomment-5633348915`.
- Local repository `ulfe-lmi/slaif-local-coding`, PR #7 is OPEN/CLEAN at final
  immutable 005-am report head
  `0210ae11b53234d85848a61e6ee0a56cbe0cb290`; implementation parent
  `f32b72607ceff25d1bef668d687f55816e365e50`; required check `test` SUCCESS.
  Do not modify Local, its PR, active pointer, source, fixtures, services, or
  Qwen.
- Local's exact synthetic `local_lookup` declaration has top-level type
  `function` and parameters
  `{"type":"object","properties":{},"additionalProperties":false}`.
- Reviewed provider: vLLM `v0.27.1`, tag commit
  `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`.
- Exact installed/tag source hashes independently match:
  - `vllm/entrypoints/openai/responses/streaming_events.py`:
    `cf1d8f5e0619148374ce10be15b1a9f7640016d810f1fe766c2dd451a918aa1f`;
  - `vllm/entrypoints/openai/responses/serving.py`:
    `628429902ff26b87f86eae1a45297f647f3712d7b421ca9a4866a3fd0f046a5b`.
- The source initializes empty accumulated arguments, emits an argument delta
  only for truthy combined text, emits `arguments.done` only after a delta,
  always emits `output_item.done`, and places the same empty string in that
  completed item. The simple serving loop closes the item before terminal
  response completion.
- Current Gateway `providers/streaming.py` rejects an empty delta, requires
  `_function_delta_seen` before `arguments.done`, and requires
  `_function_arguments_done` before `output_item.done`. The accepted model-free
  witness reproduces this producer/validator mismatch.
- Official OpenAI function-calling guidance supports functions with no
  parameters but does not define this exact vLLM streaming omission. Do not
  overstate the official contract.

These pins eliminate any need for another pre-fix protected request. Re-read
the exact Local 005-am order/report/evidence and the cited public vLLM tag only
as needed; never import or initialize vLLM/GPU/model runtime for this objective.

## Required reading and implementation authority

Read current `AGENTS.md`, `OAP-COMMUNICATION-coding-agent.md`,
`AGENTIC_CLIENT_INTEGRATION.md`, this order, merged 161-r order/report, the
Local handoff, exact affected production functions/tests, and the current
module/Responses/Codex/provider/security/accounting contracts.

The detailed agentic-client contract requires a new module version when a
stream lifecycle changes. Bump `CODEX_0149_CLIENT_MODULE_VERSION` from `3` to
`4` while retaining the exact module ID and its current client-capture fixture
identity unless source review demonstrates that a separate fixture pin must
also change. Version-3 policy metadata must continue to fail closed after the
bump; do not silently accept old metadata as version 4. Update exact operator/
test metadata and documentation truth for version 4.

## Exact authorized behavior

### 1. Declarative request-derived eligibility

Add a default-empty/default-false client-policy or canonical-request fact that
identifies only eligible zero-argument top-level function declarations. The
Codex 0.149 client module owns derivation; generic stream code consumes only
the bounded request-scoped fact and must contain no provider-name or concrete
client/server string special case.

An eligible declaration must:

- already pass every existing Codex 0.149 declaration/name/shape/depth/size/
  authority check;
- be a top-level local `function`, never custom, namespace, adapter candidate,
  hosted, MCP/connector, shell/computer, or unknown authority;
- have a safe unique name present in the existing declared-tool taxonomy;
- have an exact zero-parameter object schema: `type == "object"`,
  `properties == {}`, `additionalProperties is false`, and `required` either
  absent or exactly `[]`; no other parameter-schema key makes it eligible;
- have `strict` absent or true; explicit false is not eligible for the omission
  rule;
- be carried into stream validation only after the exact Codex 0.149 client
  module, exact `local-coding-v1` server resolution/pair, streaming request,
  and all existing request-envelope/client-tool/streaming-tool gates pass.

Do not infer zero-argument status from a function name, provider name, empty
runtime output, lack of required fields alone, or a schema with any property.
The fact grants stream-shape compatibility only; it grants no tool, route,
provider, replay, hosted, accounting, or execution authority.

### 2. Exact empty-string omission branch

For an eligible request-scoped function only, accept the reviewed no-argument-
event closure when:

- the normal added event already established the exact item ID, call ID,
  output index, safe declared name, namespace/caller/status, sequence, and
  `arguments == ""`;
- no function argument delta and no function arguments-done event has occurred;
- the next function transition is the exact completed output-item event for
  that same active item, output index, call ID, name, namespace/caller/status,
  with `arguments == ""`;
- the terminal completed response is otherwise fully valid and its function
  summary has the same name and exact empty-string argument semantics required
  by the existing semantic terminal comparison.

Mark the function complete through the same bounded state/candidate path as a
normally completed function, so existing post-accounting replay-reference HMAC
ownership remains intact. Forward the validated provider events unchanged.
Do not synthesize a delta or done event, do not fabricate identity, and do not
canonicalize the provider payload.

### 3. Empty string versus canonical empty object

Keep the representations distinct.

- The new omission branch accepts only exact empty string `""` throughout the
  added/completed-item/terminal-summary semantics described above.
- Canonical empty-object text `"{}"` remains accepted only through the existing
  ordinary lifecycle: at least one non-empty argument delta whose concatenation
  is exactly `"{}"`, followed by matching `arguments.done`, matching
  `output_item.done`, and matching terminal summary.
- A zero-length delta remains invalid. `arguments.done` without a prior
  non-empty delta remains invalid. A no-event path ending in `"{}"`, or any
  mixed/mismatched `""`/`"{}"` path, remains invalid.
- Do not parse, replace, normalize, or claim semantic equivalence between the
  two wire encodings in generic validation.

### 4. Preserve all other invariants

Retain the current exact checks for event fields; response/item/call identity
where currently required; declared tool name/type; output/content indexes;
strictly increasing sequence numbers; one function item; lifecycle cardinality;
terminal response status/output/usage; provider failure, incomplete, truncation,
disconnect, and abnormal-close rejection; live-burn counting; final usage;
PostgreSQL reservation/finalization; and replay persistence only after
accounting succeeds.

The existing terminal comparison intentionally matches function name and
arguments semantically rather than requiring terminal parser IDs to equal
stream IDs. Preserve that current reviewed rule; do not broaden it, and do not
claim new terminal-ID equivalence.

## Required tests and evidence

### Source-derived model-free positive controls

- Add one sanitized source-derived fixture or equivalent finite test vector
  pinned to vLLM 0.27.1/tag commit and both exact source hashes above. It must
  contain only public provenance and synthetic structural event data.
- Reproduce the exact source lifecycle with an eligible `local_lookup`-class
  declaration and prove the strict pair profile accepts the complete stream,
  emits no synthetic event, preserves empty string, creates the normal
  transient function replay candidate, and accepts valid terminal usage.
- Prove canonical `"{}"` continues to pass only through delta -> arguments.done
  -> item.done -> terminal completion.
- Add a mocked loopback/official-client or existing Gateway E2E case showing
  the exact pair admits and accounts the zero-event closure through the real
  handler path with one finalized reservation/ledger, zero pending state, and
  no hosted/external-tool accounting facts.

### Strict negative controls

Prove failure, without successful completion/replay persistence or hidden
accounting success, for at least:

- default client, Codex 0.147, exact Codex 0.149 with wrong/no Local pair, and
  an eligible-looking declaration when the request-scoped fact is absent;
- any function schema with a property, non-empty `required`, missing/wrong
  object type, `additionalProperties` not false, another schema key, explicit
  `strict=false`, custom/namespace/hosted/candidate/unknown declaration, wrong
  or undeclared tool name;
- non-empty/malformed added arguments, empty delta, delta followed by omitted
  arguments-done, arguments-done without a prior delta, omitted events ending
  in `"{}"`, and every mixed `""`/`"{}"` mismatch;
- wrong/missing/duplicated item ID or call ID where currently required, name,
  output index, status, namespace/caller, extra field, duplicate/reordered item
  completion, non-monotonic sequence, a second function item, terminal summary
  mismatch, invalid/missing usage, duplicate/missing terminal completion,
  provider error/incomplete, truncation, and abnormal close;
- replay candidate/persistence before final accounting, raw ID/argument/schema/
  content leakage to durable rows, logs, metrics, audit, report, or errors.

Use parameterized tests and source-derived helpers rather than duplicating a
large verifier. Generate or assert a finite obligation map with all required
positive/negative nodes collected and executed; final state must be
`missing=[]`.

### Verification economy

Run locally, from a task-private environment as needed:

- complete affected client-module, strict Codex streaming, Gateway Responses
  E2E, replay/accounting, and governance test files;
- the required PostgreSQL tests against a uniquely named disposable
  `TEST_DATABASE_URL`, with actual execution (not skip) and cleanup;
- pinned Ruff check and format check for changed Python, compilation, fixture
  JSON validation, `git diff --check`, and exact allowed-path checks.

Do not run Qwen, protected inference, a real provider, or another pre-fix
diagnostic. Do not run the unrelated HPC 128-worker harness. Standard GitHub
CI is the full Gateway gate: require all ten normal checks SUCCESS on the exact
implementation head before a PASSED report, and strategic will require all ten
again on the immutable report head before merge. Skipped, xfailed, pending,
missing, cancelled, blocked, or not-run required evidence is not a pass.

## Exact allowed paths

Only these paths may change:

- `app/slaif_gateway/modules/contracts.py`
- `app/slaif_gateway/modules/clients/codex_0149.py`
- `app/slaif_gateway/providers/streaming.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `tests/fixtures/codex/0.149.0/vllm-0.27.1-zero-argument-function-stream.json`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/integration/test_codex_client_modules_postgres.py`
- `tests/integration/test_codex_replay_references_postgres.py`
- `tests/e2e/test_openai_python_client_responses.py`
- `docs/module-architecture.md`
- `docs/responses-compatibility.md`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`
- `docs/openai-compatibility.md`
- `docs/accounting.md`
- `docs/streaming-live-burn-margin.md`
- `docs/security-model.md`
- `AGENTIC_CLIENT_INTEGRATION.md`
- `README.md`
- `oap/active`
- `oap/orders/162-a-zero-argument-function-stream-closure.md`
- `oap/reports/162-a-zero-argument-function-stream-closure.md`

Documentation changes are required for the implemented pair-specific lifecycle
and module version. Check every listed contract and update only those whose
behavior/status text changes. README may remain unchanged only with the exact
required report explanation that no top-level user-facing support claim
changed. No schema, migration, dependency/lock, configuration, deployment,
admin/CLI, provider adapter, Local Coding server module, Objective-160/161
verifier, historical order/report, or CI workflow may change.

## Non-goals and hard boundaries

- No generic OpenAI/Responses relaxation and no provider-name conditional in
  generic stream validation.
- No acceptance of empty arguments for functions with parameters, optional
  properties, ambiguous schemas, custom tools, or other client/server pairs.
- No synthesized/canonicalized argument bytes or event translation.
- No new endpoint, tool execution authority, hosted tool, MCP/connector,
  provider state, identity source, replay fallback, pricing, quota, schema, or
  retention behavior.
- No vLLM dependency/import/vendor copy and no GPU/model initialization.
- No Local/Qwen code, branch, active pointer, service, model, profile,
  credential, port, network, or protected-system mutation.
- No real provider/protected request, production mutation, deployment, release,
  tag, compliance/certification claim, merge by coding, or auto-merge.
- Do not rewrite any immutable historical report or reuse PR #291/#298.

## Publication and immutable report

Commit the unchanged strategic order and exact `oap/active` together with the
bounded implementation on the new Objective-162 branch. Create exactly one PR;
never create another PR for numeric objective 162. Push all non-report commits
and record the literal implementation head.

Publish exactly
`oap/reports/162-a-zero-argument-function-stream-closure.md` once with
`RESULT=PASSED|FAILED`, the literal implementation head, and
`Report publication commit: SELF`. The final publication commit changes only
that report and has the implementation head as first parent. Verify it as the
remote PR head before response `OK`.

The report must include:

- exact PR/base/branch/commits/report topology and allowed-path diff;
- module version 3 -> 4 and fail-closed stale-version behavior;
- the declarative request/pair fact and exact eligibility predicate;
- exact empty-string omission rule and distinct canonical-`{}` lifecycle;
- source fixture/tag/commit/hashes and Local 005-am handoff identity;
- positive and strict-negative obligation nodes/counts with `missing=[]`;
- Gateway handler/E2E, PostgreSQL replay/accounting, terminal/close/privacy
  evidence and zero pending state;
- local commands/counts and all ten implementation-head check conclusions;
- documentation impact, unchanged trust/authority/accounting/storage boundaries,
  cleanup, and exact limitations;
- no protected/real-provider inference and no Local/Qwen mutation.

Required lifecycle labels:

```text
LOCAL-005-AM-SOURCE-HANDOFF-ACCEPTED = YES
MODULE-VERSIONED = YES|NO
PAIR-LOCAL-ZERO-ARGUMENT-CLOSURE-IMPLEMENTED = YES|NO
MODEL-FREE-REGRESSION-ACCEPTED = YES|NO
POSTGRESQL-ACCOUNTING-REPLAY-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
LOCAL-HANDBACK-READY = YES|NO
MERGED = NO
RELEASE-READY = NO
```

After response, strategic independently reviews code, report, actual test
collection, diff, final-head checks, docs, security/privacy/accounting, and
mergeability. Merge is strategic-only. If accepted and merged, strategic will
post the exact merged Gateway pin to Local PR #7 and explicitly hand back one
final protected Objective-005 acceptance continuation; Gateway coding does not
activate or execute Local work.
