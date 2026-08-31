# OAP Work Order — 155-v

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 5cc47a716d3a426ea0f87882951a1491c810dae7

## Objective and reason

Make the dedicated real-Codex failure path incapable of losing bounded boundary,
count, and terminal-accounting evidence when its classifier itself fails; prove that
path with actual composed fake failures; then perform at most one new protected
qualification and, only after success plus mandatory hook removal, one decisive
hook-free protected roundtrip.

155-u is immutable and terminally failed. Its forced-invalid fake and valid fake
qualification gates passed, Codex request and stream retries were pinned to zero,
and all ten checks were green on qualification head
`a3af8dca0f40c5a67b57556db25cb8d4e5c83828`. Exactly one protected qualification
then failed with
`unexpected_composed_tool_roundtrip_failure_localization_KeyError`. No protected
event, owner, per-hop counts, or accounting result was retained, so none is inferred.
No 155-u retry or final run is authorized.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN with no auto-merge at immutable
  report-only head `5cc47a716d3a426ea0f87882951a1491c810dae7`.
- Its first parent is `a3af8dca0f40c5a67b57556db25cb8d4e5c83828`; its only
  changed path is
  `oap/reports/155-u-evidence-lifecycle-and-protected-tool-closure.md`.
- All ten report-head checks pass; local/remote heads match and the worktree is clean.
- 155-v activation is a continuation of the same Objective 155 / PR #291.
- The exact Local dependency remains immutable PR #7 report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`, clean read-only checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`, green `test`.
- The current Gateway tree contains the temporary exact-profile qualification hook,
  artifact sanitizer/reader, qualification modes, forced-invalid fake, and permanent
  hook-free protected runner. Temporary qualification code must not survive final
  acceptance.
- The private runtime reference was removed by 155-u cleanup. Strategic will recreate
  it mode 0600 outside the repository before signaling. Its endpoint and credential
  values must never be rendered or committed.

Preserve all established permanent evidence from 155-t/155-u: exact 0.149 envelope
and pair-local taxonomy, function lifecycle, top-level continuation/replay ownership,
Local-only raw prompt-cache alias scrub, strict negatives, zero Codex retries,
hook-free composed valid fake success, and unchanged Local/Qwen product trees.

Immutable reports 155-t and 155-u must not be rewritten. The 155-v report must record
their complete ancestry and limitations, including the 155-t starting-head label
nuance already documented in the strategic ledger.

## 1. Localize and eliminate classifier KeyError

Before Docker, PostgreSQL, Local, Qwen, protected health, or credentials:

1. Split `tool_roundtrip_failure_localization` into fixed stages covering:
   Codex failure-class projection, Gateway/Local snapshots, Qwen status projection,
   request-shape projection, accounting status projection, qualification artifact
   read/sanitize, and final decision.
2. Audit every direct mapping/index access reachable from those stages. Missing,
   malformed, extra, reordered, or type-wrong safe facts must map to an allowlisted
   `unknown`/`other` class or a fixed `VerificationError`, never `KeyError`.
3. Add fault-injection/table tests with empty and partial Gateway, Local, Qwen,
   accounting, request-projection, and artifact dictionaries. Prove no raw exception
   message/value can escape.
4. Preserve the 155-u in-memory artifact merge fix: retained sanitized evidence is
   authoritative; a second file read proves equality/absence and never overwrites it.
5. Treat a success result plus a rejection artifact, differing dual artifacts, or a
   failure result with no safe summary as inconsistent and fail closed.

## 2. Pre-classification safe summary

Before calling the final failure decision, atomically write and fsync one
qualification-only summary under the mode-0700 task root using mode 0600,
owner-only, regular-file, no-follow, no-overwrite semantics.

The summary may retain only:

- schema/version and last completed allowlisted stage;
- allowlisted Codex failure category;
- Gateway request/response count classes and status/content-type classes;
- Local request/response count classes and disconnect/truncation/error booleans;
- Qwen inference count/status/content-type/normal-close classes and path-error flags;
- safe request profile class (top-level function pair/no additional-tools/other);
- qualification rejection present/absent and sanitized artifact digest/equality
  boolean, never artifact values duplicated into logs;
- reservation/ledger row and terminal-status classes, zero-pending boolean;
- no IDs, text, prompts, arguments/results, event values, credentials, endpoints,
  exception messages, raw SSE, bodies, or headers.

The outer runner must read/sanitize and preserve this summary before task-root cleanup
even if a later classifier raises. Inconsistent memory/file summaries fail closed.
The CLI must print only a fixed code plus the sanitized summary and exit nonzero.

Required artifact negatives: wrong root/name/owner/mode/type, symlink, overwrite,
truncation, excessive bytes/fields/nesting, malformed JSON, unknown keys/classes,
unsafe values, duplicate entries, missing terminal fields, and memory/file mismatch.

## 3. Actual composed fake failure rehearsals

Run both through real installed Codex 0.149 -> Gateway -> exact Local -> fake-Qwen,
with request and stream retries fixed at zero:

1. The existing parser-safe forced validator rejection. Require the sanitized event
   artifact, pre-classification summary, one bounded request chain, coherent terminal
   released/failed or finalized/estimated accounting, cleanup, and nonzero CLI.
2. A new qualification-only fake provider/transport failure that produces no
   validator artifact but enters the same failure-localization path used by the
   protected failure. Require an allowlisted Qwen/Local/Gateway owner classification,
   preserved summary, coherent terminal accounting, cleanup, and nonzero CLI—never
   `KeyError` or an unbounded exception.

Also rerun the valid hook-enabled fake qualification: exactly two turns, one function
result, one final message, two finalized rows, no artifact/summary, normal closes,
privacy, and cleanup.

Temporary failure doubles and summaries are rehearsal/qualification infrastructure;
remove them with the hook after successful protected qualification.

## 4. Qualification-head gates

Before protected traffic:

- exact 155-v topology/order/active/Local anchors pass;
- private runtime reference and credential source pass owner/mode/type/no-symlink
  checks without rendering;
- protected model health passes;
- all pure KeyError/fault-injection and artifact tests pass;
- both actual composed fake failures preserve safe evidence and exit nonzero;
- valid fake qualification passes artifact-free;
- strict function/message/reasoning, policy, replay, identity, privacy, accounting,
  rollback, tamper, and hosted-tool-denial tests pass;
- worktrees are clean; full Ruff, compilation, diff checks, and all ten CI checks pass
  on the pushed qualification head.

## 5. One protected qualification

On that exact head run one no-retry real Codex 0.149 -> Gateway -> exact Local ->
unchanged protected Qwen qualification.

Success requires exactly two turns/hops/inferences, one reviewed function lifecycle,
one executed and returned function result, one final message lifecycle, one created
and completed terminal per turn, valid detailed usage, two finalized accounting rows
and aggregate counters, signed identity, raw-alias/secret/internal-header absence,
hosted-search absence, normal close, no Gateway-induced Local disconnect, cleanup,
and protected post-health.

Reviewed reasoning events may precede the function/message. Turn one must have no
assistant message lifecycle; turn two must have no function/custom/hosted lifecycle.

If qualification rejects or otherwise fails, do not retry and do not run final.
Publish the sanitized event artifact if present plus the pre-classification summary,
fixed stage/code, terminal accounting and cleanup. Do not infer beyond those facts.

## 6. Mandatory hook removal after qualification success

Only after qualification passes:

- remove every temporary production hook/env/writer, artifact/summary reader and
  sanitizer, qualification-only/forced-failure CLI and fake mode, and temporary test;
- preserve the permanent hook-free `--tool-roundtrip-protected` runner and all
  permanent product corrections/negatives;
- prove complete hook/summary/env/path absence by source/AST/search tests;
- rerun the valid hook-free composed fake, affected suites, Ruff, compilation, and
  all ten checks on the pushed hook-free head;
- send no protected traffic during cleanup or CI.

## 7. One decisive hook-free protected final

On the exact clean hook-free green head, privately revalidate topology, runtime,
credential source, protected model, and Local head, then run exactly one no-retry
permanent protected tool roundtrip. Require all section-5 success facts plus hook
absence and protected post-cleanup health.

If it fails, do not retry. Publish only the bounded first failing boundary/contract,
terminal accounting, and cleanup facts.

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
    oap/orders/155-v-failure-localization-summary-and-protected-closure.md
    oap/reports/155-v-failure-localization-summary-and-protected-closure.md

No Local Coding/Qwen mutation, dependency/lockfile/schema/migration, generic route
redesign, hosted/custom/unknown authority expansion, unrelated cleanup, merge,
release, or Objective 006 is authorized.

## Report and handoff

Publish one immutable report-only final commit. `RESULT=PASSED` requires the decisive
hook-free protected run; otherwise `RESULT=FAILED`. Include complete 155-t/u/v
topology, exact protected process/inference counts, pure/fake/CI evidence, sanitized
failure summaries if any, hook absence, accounting/privacy/security/cleanup, and no
raw values/endpoints/credentials/content.

On pass, post the hook-free implementation and report heads directly to Local PR #7
for prepared 005-n. Do not merge either PR or enable auto-merge. Require all ten
checks on the report head, then write exactly `OK` (two bytes, no newline) to the
verified response FIFO.
