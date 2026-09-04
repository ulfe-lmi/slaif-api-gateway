# OAP Work Order — 158-a

## Objective and business reason

Create the third clean post-Objective-155 decomposition PR from merged
Objective-157 main. Reconstruct the accepted exact pair-local Codex-0.149
Responses SSE validation for reasoning, function-call, and assistant-message
lifecycles, plus permanent regression evidence.

This objective owns response-stream semantics only. It must not add the
second-turn continuation request contract, visible-reasoning request replay,
ID-less tool-call replay, call-ID-HMAC lookup, or final protected acceptance
assigned to Objectives 159–160.

## Verified starting state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` is exact merged Objective-157 commit
  `05fdbbc0ac623f49b87ee632d3f047120234941f`.
- Objective 157 PR #294 is merged. Product/docs/fixture implementation head is
  `f3bdd0bcccc7e7c6b643e75d3cb30d4931967600`; test-transition head is
  `83a9cbaa7473f38066ccb558a7fba55f842d5e4a`; immutable PASSED report head is
  `9ddf4c3aba248cd31698b8c78a14598f9c3a6ecc`.
- Main now has the default-denied Codex-0.149 client contract, exact
  `local-coding-v1` server/pair, final secure signed identity, Responses-only
  transport, and mocked/cross-contract accounting evidence.
- The production streaming validator and pair-local advanced stream profile
  are still absent.
- Objective 155 remains permanently closed. PR #291 stays immutable at report
  head `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`; accepted implementation head is
  `acea2af4ca0f4586fc159c91607e1848f53f1107`.
- Accepted final stream validator/test/E2E blobs are identical at Objective-155
  stream milestone `b7b7f7ec00ec365fb245185a7e7588aa6c41ccbc` and final
  `acea2af4...`, as listed below.
- `responses_gateway.py` at `b7b7f7...` is not a whole-file target: it contains
  Objective-specific qualification-hook machinery and second-turn request
  work. Use it only to identify stream-profile hunks, cross-check against the
  hook-free final source, and reconstruct the bounded semantics below.
- No Objective-158 branch or PR exists at activation.

## PR contract

- PR mode: `CREATE_NEW_PR`
- Base: `main` at `05fdbbc0ac623f49b87ee632d3f047120234941f`
- Branch: `oap/158-codex-0149-local-stream-lifecycles`
- Title: `obj158: reconstruct Codex 0.149 Local stream lifecycles`
- Create exactly one PR for Objective 158.
- Do not merge or enable auto-merge.
- Do not alter PR #291 or any prior objective branch/history.
- If main moves, retain the exact authorized base and report the state; do not
  silently absorb unrelated work.

Use a new clean isolated worktree. Preserve all existing worktrees and local
artifacts. Commit this exact order and `oap/active` unchanged.

## Required reading

Read completely before editing:

- current `AGENTS.md` and `AGENTIC_CLIENT_INTEGRATION.md`, especially stream
  state-machine, evidence, and decomposition rules;
- `OAP-COMMUNICATION-coding-agent.md`;
- merged Objective-156/157 reports and current client/server/pair contracts;
- current `app/slaif_gateway/providers/streaming.py` and
  `app/slaif_gateway/services/responses_gateway.py`;
- accepted final stream validator and stream tests at `acea2af4...`;
- Objective-155 stream milestone source at `b7b7f7...`, while treating all
  qualification hooks and request-continuation code as excluded;
- affected permanent Responses/forwarding/compatibility/accounting docs.

## Allowed paths

Production:

- `app/slaif_gateway/providers/streaming.py`
- `app/slaif_gateway/services/responses_gateway.py`

Permanent tests:

- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/e2e/test_openai_python_client_responses.py`

Permanent documentation:

- `docs/accounting.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`

OAP transcript:

- `oap/active`
- `oap/orders/158-a-codex-0149-local-stream-lifecycles.md`
- `oap/reports/158-a-codex-0149-local-stream-lifecycles.md`

No other path is authorized. Client modules/specs, request policy, Local
server/identity, replay repositories/services, schemas/migrations, root
doctrine, Local Coding, and Qwen are read-only.

## Exact accepted targets and exclusions

- Set `app/slaif_gateway/providers/streaming.py` to exact accepted blob
  `bd54aeb9a203be52b2cdba626344cf74adf46c0c`.
- Set `tests/e2e/test_openai_python_client_responses.py` to exact accepted blob
  `aa95589294f48f883b1c174a5a3a43428d9c44f0`.
- Do not copy the complete final
  `tests/unit/test_responses_codex_streaming_tools.py`, because its
  request-continuation/replay tests belong to Objectives 159–160. Reconstruct
  only the stream-profile and validator test families specified below.
- Do not copy any whole historical `responses_gateway.py`. Apply only
  permanent pair-local stream-profile wiring to current main.
- No string beginning `SLAIF_155`, qualification artifact writer, report path,
  protected-runtime hook, or diagnostic-only branch may exist under `app/`.
- No import/use of `responses_codex_tool_roundtrip_requested`, new
  `codex_replay_request_candidates` behavior, ID-less replay flag, visible
  reasoning request validation, or call-ID-HMAC lookup belongs in this PR.

## Required production behavior

### Pair-local profile selection

- Enable the strict Codex 0.149 reasoning/function/message stream profile only
  when all static facts match the exact
  `codex-0.149-responses-v1 -> local-coding-v1` pair.
- Require the existing independent key/route request-envelope, client-tool,
  and streaming-tool-event capabilities where the declared tool profile needs
  them.
- Derive only bounded declared local tool taxonomy from the already-normalized
  request. A declaration is not execution authority.
- Ordinary OpenAI/default, Codex 0.147, generic compatible servers, hosted-tool
  routes, arbitrary clients, and other pairings must not obtain the profile.
- For the exact Local pair, omit only the already-reviewed transient
  `prompt_cache_key` from the upstream body; preserve all other canonical
  accepted fields and retain tests proving no broader mutation.

### Exact stream state machines

Implement the final accepted validator behavior for the active profile:

- exactly one ordered `response.created`, optional reviewed
  `response.in_progress`, and exactly one terminal `response.completed` with
  matching response identity/status/model/output and valid usage;
- reasoning item lifecycle:
  `response.output_item.added` -> `response.reasoning_part.added` -> one or
  more bounded `response.reasoning_text.delta` ->
  `response.reasoning_text.done` -> `response.reasoning_part.done` ->
  `response.output_item.done`, with exact item/part shapes, output/content
  indices, identity relations, summary/content/status, cardinality, and bytes;
- function/custom tool lifecycle for the already-declared exact local tool:
  output item added, bounded argument/input deltas, exact done event, and output
  item done with exact call/name/namespace/status/index/field relations;
- assistant message lifecycle: output item added, content part added, bounded
  output text deltas, text done, content part done, output item done, then
  terminal completion with exact role/status/content/logprobs/annotation/phase
  shapes;
- response completion is rejected while any item/part/delta lifecycle remains
  incomplete or duplicated.

Keep all counts, individual delta size, aggregate size, identifier shape,
index, output cardinality, terminal usage, and active-item bounds exactly as
the accepted implementation.

### Fail-closed behavior

Reject before successful forwarding/completion for:

- unknown event types or wildcard/prefix variants;
- orphan, reordered, duplicate, skipped, conflicting, or post-terminal events;
- wrong response/item/call identity relation;
- undeclared or mismatched tool name/namespace/call type;
- inner/outer coordinate smuggling or wrong indices;
- extra/missing fields, malformed types/statuses/content/logprobs/usage;
- excessive per-delta or cumulative bytes/cardinality;
- message/tool events smuggled into reasoning lifecycle or vice versa;
- hosted search, MCP, connector, arbitrary tool, or provider authority;
- profile activation outside the exact pair/capability route.

Do not normalize, fabricate, synthesize, or repair invalid provider events.
Do not fabricate `response.completed` or change accounting to conceal a stream
failure.

## Accounting and privacy

- Final valid provider usage remains authoritative for ordinary reservation/
  ledger finalization.
- Invalid/truncated/error streams use existing rollback/failure law and leave
  no pending reservation.
- Adapter-managed candidates remain ordinary strict-bounded input, never
  external-tool pricing/fence/hold metadata.
- Stream validation may inspect transient event state but must not persist or
  log reasoning text, output text, arguments/input, IDs, call IDs, raw events,
  bodies, headers, credentials, or arbitrary errors.

## Required permanent tests

In `tests/unit/test_responses_codex_streaming_tools.py`, add the accepted
pair-profile and pure validator coverage for:

- exact-pair reasoning stream containment;
- exact Local-pair `prompt_cache_key` omission and no other body mutation;
- top-level declared local tools activating only after exact pair resolution;
- positive ordered function lifecycle and final message lifecycle;
- response terminal semantics based on exact response content rather than
  arbitrary stream IDs;
- reasoning lifecycle, including nonzero output index;
- exact function/message/reasoning item and event-specific shapes;
- every lifecycle ordering, duplicate, orphan, coordinate, undeclared tool,
  extra field, status, per-delta, cumulative-size, terminal output, usage, and
  smuggling negative represented in the accepted final tests;
- ordinary/non-strict behavior unchanged where its existing contract differs.

Exclude tests whose subject is second-turn request input chronology,
function-call-output request admission, replay ownership, ID-less request
items, visible-reasoning request validation, or call-ID-HMAC fallback.

The E2E exact target must prove one mocked official-client Local streaming
request, exact candidate preservation to Local, expected message lifecycle,
valid usage, one finalized strict-bounded accounting row, zero pending state,
and no external-tool facts.

## Required verification

Use focused evidence:

1. Run the complete changed stream unit file.
2. Run the exact Local streaming E2E test with disposable PostgreSQL and
   loopback mocked Local response; no Local/Qwen/provider process or credential.
3. Run selected existing ordinary/default/Codex-0.147 streaming regressions to
   prove no profile leakage.
4. Run provider-failure, unknown-event, truncated-stream, disconnect, usage,
   and accounting rollback tests affected by the validator profile.
5. Run repository Ruff check, Python compilation, and `git diff --check` for
   changed paths.
6. Verify the exact accepted provider-streaming and E2E blob identities.
7. Mechanically inspect `responses_gateway.py` diff to prove it contains only
   pair-local stream-profile and prompt-cache wiring, no Objective-155 hook or
   later request/replay behavior.
8. Verify no diff to any non-allowed app path, client/policy blob, Local module,
   replay repository/service, schema/migration, doctrine, Local checkout, or
   Qwen state.
9. Push implementation, create the unique PR, and require all ten normal
   GitHub checks successful on the exact final report head.

No required test may be skipped, xfailed, pending, cancelled, missing, or
environment-blocked.

## Documentation

Update only the allowed permanent documents. Describe:

- exact pair-local reasoning/function/message lifecycle support;
- event state-machine and terminal usage constraints;
- default-false/capability containment and unknown-event failure;
- transient/no-content-retention behavior;
- ordinary strict-bounded accounting finalization/rollback;
- mocked/state-machine qualification only at this layer.

Do not claim second-turn request admission, replay ownership, protected
Gateway->Local->Qwen qualification, deployment, release, or production
readiness. Preserve permanent root doctrine links and exclude Objective-155
verifier/report/PR-head/runtime prose.

## Explicit non-goals

Do not:

- modify Local Coding or Qwen;
- make protected or real-provider calls;
- implement Objectives 159 or 160;
- modify request policy/client policy/replay/schema/migrations;
- admit second-turn function outputs or visible/ID-less replay;
- globally permit unknown Responses events or wildcard reasoning events;
- grant hosted search/MCP/provider/Gateway tool authority;
- change Local identity, secret, route, or transport contracts;
- copy Objective-155 diagnostic hooks/verifier/tests;
- modify PR #291;
- merge or auto-merge;
- claim final clean-stack or release acceptance.

## Setup and cleanup

Routine task-local dependencies, loopback mocks, and disposable PostgreSQL are
authorized. No protected credentials or external services are authorized.
Clean only uniquely created resources and report their absence.

## Immutable report

Publish exactly:

`oap/reports/158-a-codex-0149-local-stream-lifecycles.md`

The report must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact repository/base/branch/PR/head/no-auto-merge state;
- implementation head and `Report publication commit: SELF`;
- report-only topology and complete changed-path/app inventory;
- exact provider/E2E blobs and bounded `responses_gateway.py` semantic diff;
- exact profile/pair/capability activation facts;
- positive and negative reasoning/function/message lifecycle test mapping;
- ordinary/default profile non-regression evidence;
- E2E/accounting/failure/privacy results with test counts and skips explicit;
- explicit proof no second-turn request/replay or Objective-155 hook entered;
- all ten final report-head check states;
- cleanup, documentation impact, and limitations.

Commit implementation, then one report-only commit whose first parent is the
implementation head and whose only changed path is the report. Verify it is
the remote PR head and all claims exist, write exactly `OK` to the response
FIFO, and return to one blocking control-FIFO read.
