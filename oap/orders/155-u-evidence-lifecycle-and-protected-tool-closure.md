# OAP Work Order — 155-u

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 9046ccda503d0393ab5df155fdf028810d1726f5

## Objective and reason

Repair and prove the bounded qualification-evidence lifecycle that failed in
155-t, then close the real Codex 0.149 function-tool path with at most one new
protected qualification and, only after that succeeds and every temporary hook
is removed, one decisive hook-free protected roundtrip.

155-t is immutable and terminally failed. It consumed exactly one protected
qualification on green head `bb45e0813a15b41541c5b1ef48537fa835995106`
and returned `qualification_evidence_incomplete`. No rejected event, boundary
owner, per-hop counts, or terminal accounting outcome was retained, so none may
be inferred. No 155-t retry or final run is authorized.

The current code makes one bounded verifier defect directly testable: the inner
tool-roundtrip helper can return `codex_exit_success=false` only after it has read
and sanitized a qualification rejection, but the outer dedicated runner performs
a second file read, overwrites the retained in-memory rejection with that result,
and can turn it into `qualification_evidence_incomplete`. Prove this with pure
and forced-fake evidence before any new protected request.

## Verified starting state

Gateway:

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN with no auto-merge at immutable
  report-only head `9046ccda503d0393ab5df155fdf028810d1726f5`.
- Its first parent is qualification implementation head
  `bb45e0813a15b41541c5b1ef48537fa835995106`; its only changed path is
  `oap/reports/155-t-codex-envelope-activation-and-function-roundtrip.md`.
- All ten report-head checks pass.
- The worktree and remote branch are clean and equal.
- 155-t activation remains `ad3ab547052d8a7600db9802e25da45bbf4b07da`.
- The current tree still contains the temporary qualification hook and
  qualification-only CLI added by `bb45e08...`; environment enablement is off.
  They must not survive final acceptance.
- The protected runtime reference was removed by 155-t cleanup. Strategic will
  recreate the exact mode-0600 runtime reference privately before signaling this
  order. It and its credential source must never be rendered or committed.

Established 155-t product/fake evidence:

- exact no-provider Codex 0.149 capture and canonical top-level function/custom
  taxonomy activation passed;
- exact Codex 0.149 -> Local Coding pairing is post-route and fail-closed;
- the strict vLLM 0.27.1 function lifecycle is implemented with order, ID,
  index, sequence, cardinality, size, terminal-output, usage, replay, and
  smuggling negatives;
- the real Codex top-level function continuation is accepted without inventing
  an `additional_tools` item, while replay ownership remains mandatory;
- the exact Local pair drops only raw alias-bearing `prompt_cache_key` from the
  newly built Local-bound body; generic/default behavior and the validated policy
  body remain unchanged;
- hook-free real Codex -> Gateway -> Local -> fake-Qwen passed two turns with one
  function result, one final message, two terminal accounting rows, privacy,
  normal close, and cleanup;
- hook-enabled fake qualification also passed with no artifact;
- one protected 155-t attempt then failed only as
  `qualification_evidence_incomplete`; no protected event contract was retained.

Local:

- PR #7 remains OPEN, non-draft, MERGEABLE/CLEAN at immutable 005-m report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`; implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`; current `test` passes.
- Clean detached read-only checkout:
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- Local production and protected Qwen remain unchanged.

Immutable audit notes:

- Do not rewrite 155-t. Its report truthfully denies acceptance but does not
  identify the evidence-lifecycle overwrite described above and labels
  `8966df2...` as its starting implementation head even though 155-t began at the
  prior 155-s report and accumulated earlier implementation commits. Record the
  complete ancestry and correction in 155-u evidence.
- The 155-s report's previously recorded starting-head label correction remains
  unchanged and must not be rewritten.

## 1. Pure evidence-lifecycle proof

Before Docker, PostgreSQL, Local, Qwen, or protected health:

1. Add a focused test that supplies a sanitized in-memory rejection from the
   inner helper while the second artifact read is absent. Reproduce the current
   overwrite to `qualification_evidence_incomplete` without private values.
2. Correct the dedicated wrapper so the inner sanitized result is authoritative.
   A second read may only prove equality or absence; it must never overwrite a
   retained sanitized artifact.
3. Reject inconsistent dual evidence, malformed safe evidence, or a file artifact
   that differs from the retained sanitized result.
4. Preserve nonzero CLI status for `QUALIFICATION=REJECTED` and fixed error codes
   for incomplete/malformed evidence.

No raw subprocess output, request body, event value, ID, argument, completion,
endpoint, credential, or exception text may enter tests, stdout, logs, or the
repository.

## 2. Forced fake rejection rehearsal

Add a qualification-only fake mode that deliberately emits one bounded invalid
event through the real Codex 0.149 -> Gateway -> exact Local -> fake-Qwen
composition. It exists only to test rejection evidence and must not alter product
acceptance.

Require:

- exact 0.149 process and exact Local pair/profile activation;
- exactly one write-once rejection artifact with mode 0600, correct owner,
  no-follow/no-overwrite behavior, bounded bytes/fields/nesting, and no values;
- exact profile scoping: reasoning=true, exact 0.149 function events=true,
  streaming tools=true, nonempty bounded declarations, hosted web search=false;
- the inner sanitized artifact survives process/composed cleanup and is returned
  unchanged through the outer wrapper;
- the CLI prints only the sanitized rejection and exits nonzero;
- observed Gateway/Local/fake-Qwen turn counts are equal and either one or two;
- the function-call-output count is derived, not hardcoded;
- accounting has no pending/corrupt rows: completed prior turns are
  finalized/finalized and the failing terminal is only released/failed or
  finalized/estimated;
- task roots, Docker/PostgreSQL, processes, bytecode, and Local checkout state are
  clean afterward.

Also rerun the valid hook-enabled fake qualification and require two successful
turns, two finalized rows, and no artifact.

The forced-invalid fake, artifact hook, artifact reader/sanitizer, qualification
environment variables, and qualification-only CLI are temporary and must be
removed after a successful protected qualification.

## 3. Qualification-head gates

Before any protected request:

- exact current topology and Local dependency pass;
- the private runtime reference is mode 0600, owner-only, regular, non-symlink,
  and references the exact previously reviewed protected model/credential source;
- protected health/model and credential-source checks pass without rendering
  values;
- pure overwrite reproduction/correction passes;
- forced-rejection fake preservation passes;
- valid fake qualification passes artifact-free;
- strict function and ordinary reasoning/message suites pass;
- request-policy/replay/identity/privacy/accounting/rollback negatives pass;
- full Ruff, compilation, diff checks, and all ten PR checks pass on the pushed
  qualification head;
- repository and Local checkout are clean.

## 4. One protected qualification

On that exact green head, run exactly one no-retry real Codex 0.149 function-tool
qualification through real Gateway -> exact Local -> unchanged protected Qwen.

Success requires:

- exactly two Codex Responses turns, two Gateway -> Local requests, and two
  Local -> Qwen inference requests;
- first turn contains reviewed reasoning if emitted plus exactly one legitimate
  function lifecycle and no assistant message lifecycle;
- Codex executes exactly one ordinary local shell/function action and returns
  exactly one matching `function_call_output`;
- second turn contains reviewed reasoning if emitted plus exactly one final
  message lifecycle and no function/custom/hosted lifecycle;
- one `response.created` and one `response.completed` per turn, valid detailed
  usage, normal close, and no error/unknown/duplicate event;
- no Gateway-induced Local disconnect, handler error, truncation, or retry;
- signed identity accepted and no raw aliases, Gateway key, credential, internal
  header, prompt, argument/result, or content retained;
- adapter-managed search absent from protected Qwen and no hosted-tool authority;
- two finalized reservations/ledgers with correct aggregate request/token/cost
  counters and zero pending/corrupt state;
- protected model healthy after complete cleanup.

If the qualification rejects or otherwise fails:

- do not retry and do not run the decisive final;
- preserve the exact sanitized artifact/boundary/count/accounting facts if they
  exist;
- if no artifact exists, report the exact fixed external/harness/boundary code and
  do not infer an event or owner;
- remove runtime secrets and disposable state;
- publish immutable `RESULT=FAILED` evidence.

## 5. Hook removal and hook-free gates

Only after the protected qualification passes:

1. Remove every temporary production hook, env constant, artifact writer/reader,
   sanitizer, qualification-only CLI/mode, forced-invalid fake, and temporary test.
2. Preserve the permanent hook-free `--tool-roundtrip-protected` runner, strict
   product validator, top-level continuation/replay correction, exact Local
   `prompt_cache_key` scrub, permanent negatives, and valid fake verifier.
3. Prove hook-symbol/env/path absence by source/AST tests and repository search.
4. Rerun the valid hook-free real-Codex fake roundtrip and all affected tests.
5. Push the hook-free implementation and require all ten checks green.

No protected traffic is allowed during hook removal or CI.

## 6. One decisive hook-free protected final

On the exact clean hook-free green head, privately revalidate the runtime,
credential source, protected model, Local report head, and PR topology. Then run
exactly one no-retry permanent `--tool-roundtrip-protected` roundtrip.

Require every success fact from section 4, no qualification artifact/path/env,
and post-cleanup protected health. Fake, fixture, unit, ordinary-text, or prior
qualification evidence is not a substitute.

If this final run fails, do not retry. Publish the exact safe first failing
boundary/contract and terminal accounting/cleanup facts without weakening product
behavior.

## 7. Required permanent negatives

Preserve or add focused tests proving fail-closed behavior for:

- unrelated/default client or non-Local server pair;
- missing envelope/client-tool/streaming grant or route capability;
- absent, malformed, duplicate, ambiguous, conflicting, excessive, or unsafe
  top-level taxonomy;
- custom, MCP, code-interpreter, hosted-search, unknown, or authority-field
  smuggling;
- multiple/non-adjacent/mismatched call/output pairs and non-stream continuation;
- replay ownership not found, route mismatch, tamper, duplicate/reorder/index/ID/
  sequence/size/cardinality violations;
- raw session/thread/turn/installation/window metadata on any Local-bound body or
  non-signed header, including cross-turn replay and `prompt_cache_key`;
- pending, missing, incoherent, or corrupt reservation/ledger terminal pairs;
- artifact wrong owner/mode/root/name, symlink, overwrite, excessive bytes/fields,
  malformed JSON, unsafe values, wrong profile, or inconsistent memory/file facts;
- hook-free final source containing any qualification symbol/env/path.

Do not request the complete historical local suite unless a focused failure requires
it. All ten CI checks remain mandatory on qualification, hook-free implementation,
and report heads.

## Allowed paths

    app/slaif_gateway/modules/clients/codex_0149.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/responses_gateway.py
    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_responses_codex_streaming_tools.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/e2e/test_openai_python_client_responses.py
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-u-evidence-lifecycle-and-protected-tool-closure.md
    oap/reports/155-u-evidence-lifecycle-and-protected-tool-closure.md

No Local Coding or Qwen mutation, dependency/lockfile/schema/migration, generic
route redesign, hosted-tool expansion, unrelated Gateway feature, merge, release,
or Objective 006 work is authorized.

## Documentation and immutable report

Update permanent docs only for behavior proven by the final hook-free protected
run. Do not claim MVP completion, cutover, release, certification, or merge.

Publish exactly one immutable report with:

- `RESULT=PASSED` only if the decisive hook-free protected run passes every gate;
  otherwise `RESULT=FAILED`;
- complete 155-t/155-u topology and the immutable report corrections above;
- pure overwrite reproduction/fix and forced fake rejection preservation;
- qualification and final exact head(s), check names/conclusions, Codex/OpenAI/
  vLLM/Local versions and commits;
- bounded request/event/count/usage/accounting/identity/privacy/close evidence;
- exact number of protected Codex processes and Qwen inference calls;
- hook removal/absence proof;
- cleanup and protected post-health;
- no raw values, IDs, content, credentials, endpoints, or bodies.

If final acceptance passes, post the immutable hook-free Gateway implementation
head and report head directly to Local Coding PR #7 for prepared 005-n. Do not
merge either PR and do not enable auto-merge.

Commit and push the report as a report-only final commit, require all ten checks on
that exact head, and only then write exactly `OK` (two bytes, no newline) to the
verified response FIFO.
