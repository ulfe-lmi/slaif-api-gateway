# OAP Work Order — 155-t

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: e7fedae6562cdfd7df6a605128e5bc93fc224119

## Objective and reason

Correct and prove the exact real Codex 0.149 raw-tool-envelope to canonical
Gateway declared-tool profile, then validate only the observed legitimate
vLLM/OpenAI function-call streaming lifecycle through exact Local Coding and
unchanged protected Qwen. Preserve immutable 155-r ordinary streaming and
immutable 155-s failed qualification evidence.

155-s proved that one real Codex process reached Local and Qwen exactly once
and Gateway rejected a legitimate-looking `response.output_item.added`
function-call item. Its safe request-scoped profile was
`codex_streaming_tool_events=false` with
`declared_client_tools_class=none`. No product relaxation was authorized.
The next required step is no-provider proof of the raw envelope and canonical
profile activation, not another speculative protected request.

## Verified starting state

Gateway:

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable failed 155-s report
  head `e7fedae6562cdfd7df6a605128e5bc93fc224119`; first parent
  `ce725def4b931c2bf86770d8c6bd75c7e37247ef`; report-only path
  `oap/reports/155-s-real-codex-tool-stream-lifecycle-and-acceptance.md`.
- All ten report-head checks pass; no auto-merge exists.
- Hook-free 155-s implementation differs from 155-s activation only in
  verifier topology pins and a pure reproduction test. No product tool
  acceptance change exists.
- 155-r ordinary reasoning/message acceptance remains immutable at report head
  `2527030f5bbb90a7f0f354eb5347caee333ce4a7`, implementation
  `19d9686636b0fbf27ab96d41c610a37dad3c087a`.

Local:

- PR #7 remains OPEN, non-draft, MERGEABLE/CLEAN at immutable 005-m report
  head `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`; implementation
  `258ae2ebad39651076937b9f027e60831b8d2786`; current `test` passes.
- Clean detached read-only checkout:
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- Local production and protected Qwen were unchanged by 005-m/155-s.

Exact 155-s safe evidence:

- one real Codex 0.149 process request;
- one Gateway -> Local request and one Local -> Qwen inference;
- Gateway rejected `response.output_item.added`;
- item fields/type classes:
  `arguments:string`, `call_id:string`, `caller:null`, `id:string`,
  `name:string`, `namespace:null`, `status:string`, `type:string`;
- top-level fields:
  `item:object`, `output_index:integer`, `sequence_number:integer`,
  `type:string`;
- profile:
  reasoning pair active by topology, but
  `codex_streaming_tool_events=false`,
  `declared_client_tools_class=none`, hosted web search false;
- no second request, no correction, no final run, exact cleanup.

Historical audit correction: immutable 155-s report labels activation
`62f8063...` as its starting head. The actual pre-activation starting head
was immutable 155-r report `2527030f...`; activation head was
`62f8063c9f4fc304f5b835741b1a263202285b56`. Do not rewrite the report.

A later local-only formatting commit `91e049f...` was never pushed. The
checked-out branch/index were restored exactly to remote `e7fedae...`.

## 1. Mandatory no-provider real-Codex envelope proof

Before Docker, PostgreSQL, Local, Qwen, or any protected inference:

1. Pin topology to exact 155-t activation, immutable 155-s report/parent, and
   exact Local 005-m report/parent.
2. Install/verify official Codex 0.149.0 in one private mode-0700 task root;
   verify literal version and expected checksum.
3. Launch exactly one loopback capture that returns a fixed synthetic
   rejection before model/provider work. Run real Codex from a synthetic
   workspace with an instruction requiring one ordinary local shell/function
   action.
4. Retain raw request only transiently in memory. Emit/persist only:
   top-level field classes; tool type/count classes; reviewed function/custom
   declaration field-name classes; adapter-managed search presence classes;
   stream/tool-choice classes; and finite Codex version/process facts. Never
   retain tool schemas, descriptions, names, arguments, IDs, prompts, bodies,
   or values.
5. Feed that exact transient request through the actual Codex 0.149 client
   normalizer, Responses request policy, exact Local route capabilities, and
   profile-construction helpers. Delete the raw request immediately.
6. Prove with safe facts that:
   - real Codex raw envelope contains reviewed ordinary function/custom tools
     and adapter-managed disabled-search declarations;
   - hosted search remains adapter-managed/denied;
   - canonical effective body yields a nonempty bounded declared ordinary-tool
     taxonomy;
   - streaming tool events are requested only for stream requests with the
     exact reviewed envelope;
   - exact Codex/Local pair activates the tool profile;
   - the same client on non-Local route, non-Codex client, missing capability,
     malformed/unknown tools, hosted choice, or absent envelope does not.

No protected traffic may run if any fact is missing, inferred, fixture-only, or
based solely on the archived structural fixture.

## 2. Minimal canonical envelope/profile correction

If the live no-provider proof shows the current normalizer/profile loses the
reviewed ordinary declarations, correct only that exact boundary.

Preferred design law:

- canonical tool authority must derive from the already validated effective
  request plus exact client/server pair and key/route capabilities;
- top-level real-Codex function/custom declarations may contribute only a
  bounded namespace/name/type taxonomy after full request-policy validation;
- adapter-managed `tool_search`/`web_search` never become declared provider
  tools or hosted authority;
- no arbitrary raw client field, description, schema, or value becomes
  authority;
- generic OpenAI/non-Local routes remain unchanged.

Determine whether the narrowest correction belongs in the 0.149 normalizer or
in exact-pair declaration/profile extraction. Do not duplicate competing
canonical representations. Record the chosen single authority.

Required pure negatives: duplicate/ambiguous names, namespace ambiguity,
unknown type, missing name, malformed schema, excessive declaration count or
bytes, route/capability mismatch, hosted search choice, non-stream request,
unrelated client/server pair, and smuggled authority fields.

## 3. Exact legitimate function-call stream contract

Use primary sources and 155-s evidence:

- official OpenAI Python 2.41.0 tag/commit
  `v2.41.0` / `2d955a1ac69df0288b8072bbcd25905639e9b2ed`;
- protected vLLM 0.27.1 tag/commit
  `v0.27.1` / `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`;
- real Codex no-provider captured envelope;
- exact Local 005-m filter contract.

The observed initial function-call item is legitimate only if its tool resolves
uniquely to the canonical declared taxonomy. Permit optional provider fields
only at their exact reviewed values: `namespace=null` and `caller=null`
may not carry authority.

Implement the exact ordered function lifecycle required by vLLM 0.27.1:

1. `response.output_item.added` with one declared function item,
   in-progress status, empty arguments, unique bounded item/call IDs, stable
   output index, and exact field set;
2. one or more bounded
   `response.function_call_arguments.delta` events for that active item;
3. exact `response.function_call_arguments.done` with bounded name,
   accumulated arguments equality, stable item/output index, and sequence;
4. exactly one `response.output_item.done` with completed status, exact
   declared tool relation, stable IDs/index, and terminal arguments equality;
5. one terminal `response.completed` after all active reasoning/message/tool
   items close, with bounded final function-call output, detailed usage, and
   token-total relation.

Compose, do not replace, the 155-r strict reasoning/message state machine.
When the exact tool profile is inactive, every tool event remains denied.

Required negatives include missing/extra/wrong fields, non-null caller,
unauthorized namespace/name/type, duplicate item/call ID, orphan/reordered/
duplicate delta/done, non-monotonic sequence, index mismatch, terminal
argument/name/call mismatch, per-delta/cumulative/item/cardinality overflow,
events after done/completed, function-call final output without declared
authority, hosted-search/MCP/code-interpreter/custom smuggling, and unknown
event types.

Do not add a custom-tool lifecycle unless fresh no-provider and live evidence
proves it is required. Do not globally allow tool event names.

## 4. Temporary bounded qualification evidence

After the no-provider correction and pure tests, a temporary 155-r-style
write-once hook may be used only to catch the next validator rejection during
one product qualification. It must retain only strict event/field/type/profile
classes, use canonical sanitizer, mode-0700 validated /tmp root, mode-0600
no-follow/no-overwrite artifact, bounded bytes/nesting/counts, and no values.

Before protected qualification:

- exact raw-to-canonical no-provider proof passes;
- realistic fake function-call stream and fake real-Codex tool roundtrip pass;
- ordinary 155-r fake/official-client paths remain green;
- affected unit/E2E/privacy/accounting tests, Ruff, compilation, diff checks,
  and all ten checks pass on the pushed qualification head.

Then run exactly one no-retry protected real Codex 0.149 tool qualification
through exact Gateway -> exact Local -> unchanged Qwen.

If a rejection occurs, publish only the exact safe first failing contract; no
retry or final run. If the complete tool roundtrip passes, remove all
diagnostics before final acceptance.

## 5. Remove diagnostics and hook-free gates

Before the decisive final run:

- remove every 155-t hook/env/writer/sanitizer/qualification CLI/path and
  temporary test;
- prove hook-symbol absence;
- preserve only canonical envelope/profile correction, exact function
  lifecycle, permanent negatives, real-Codex tool verifier, and truthful docs;
- run hook-free realistic fake Qwen state that emits one function call on the
  initial turn and a normal reasoning/message terminal answer after Codex
  returns the local tool result;
- require real Codex 0.149 process exit 0, exactly one local tool execution,
  expected per-turn Local/Qwen calls, terminal completions, detailed usage,
  finalized accounting, normal closes, hosted-search absence, and cleanup;
- push the final implementation and require all ten checks green.

Fake evidence is rehearsal only.

## 6. One decisive protected real-Codex tool roundtrip

On the unchanged hook-free green head, privately revalidate protected
health/model and run exactly one no-retry real Codex 0.149 tool roundtrip from
a synthetic workspace through exact Local 005-m and unchanged Qwen.

Require:

- safe live proof that the initial real Codex request contains the reviewed
  tool envelope and activates bounded declared tools;
- each Codex Responses turn reaches Local exactly once and Qwen exactly once;
- exactly one intended ordinary local shell/function call is emitted, passes
  Gateway validation, executes locally, and is returned in the next request;
- adapter-managed search does not reach Qwen; no hosted-tool authority;
- exact function added/delta/arguments.done/item.done lifecycle;
- one valid response.completed for each required turn and final Codex exit 0;
- no Gateway error or `responses_stream_event_not_supported`;
- normal upstream/downstream close and zero Gateway-induced Local disconnect;
- valid detailed usage, finalized reservation/ledger per admitted turn, correct
  aggregate request/provider counts, and zero pending/corrupt accounting;
- signed identity/route containment and no credential/internal-header leakage;
- complete task cleanup and unchanged protected Qwen.

Retain only fixed statuses, safe tool/event/count classes, versions/commits,
and timing buckets. Never retain source/tool/model text, arguments/results,
raw SSE, IDs, identities, credentials, or private endpoint facts.

## Allowed paths

    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_responses_streaming_live_burn.py
    tests/e2e/test_openai_python_client_responses.py
    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-t-codex-envelope-activation-and-function-roundtrip.md
    oap/reports/155-t-codex-envelope-activation-and-function-roundtrip.md

No Local Coding or Qwen mutation, dependency/lockfile/schema/migration,
generic route-pair redesign, deployment/cutover/release, or unrelated Gateway
feature is authorized.

## Cleanup, publication, and handoff

Preserve signed identity, replay/idempotency, quota/accounting, provider
credential secrecy, Local containment, hosted-search denial, incremental
cancellation, and no-default-content/tool retention.

Use exact mode-0700 task roots and mode-0600 private references. Permanently
delete exact task roots/secrets without Trash. Preserve Local detached
checkouts through report publication.

Publish one immutable
`oap/reports/155-t-codex-envelope-activation-and-function-roundtrip.md` with
literal implementation head, `Report publication commit: SELF`, report-only
topology, no-provider envelope/profile proof, chosen authority, primary-source
tool contract, permanent negatives, qualification/final real-Codex counts,
terminal/accounting/disconnect facts, checks, privacy, cleanup, and
limitations.

After publication make no repository mutation. Verify all ten report-head
checks, topology, clean state, and resource absence; send exact FIFO `OK`.
Post a passing head directly to Local PR #7 for prepared 005-n. Neither PR
merges. No Objective 156/release/cutover/MVP-complete claim is authorized by
155-t alone.
