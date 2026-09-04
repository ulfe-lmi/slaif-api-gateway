# OAP Work Order — 155-x

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 5385d066d2a869afd217e354996fe2027770a276

## Objective and reason

Preserve the already-sanitized qualification CLI evidence outside task-root cleanup,
then use the existing live done-item correction for at most one protected
qualification and, only after success plus temporary-code removal, one hook-free
protected final.

155-w is immutable and terminally failed. It corrected the live
`response.output_item.done` item shape, aligned the fake, passed focused suites and
all ten checks, and passed validator-failure/provider-failure/valid composed fake
gates on clean head `b7b7f7ec00ec365fb245185a7e7588aa6c41ccbc`. Exactly one
protected qualification then returned exit 1 / `QUALIFICATION=FAILED`. The outer
shell redirected the sanitized JSON into a task-owned file and deleted that file on
exit, retaining only the result class. No protected contract/owner/count/accounting
fact survived; no retry or final occurred.

This is an operational evidence-preservation defect, not contradictory product
evidence. Do not revert the live done-item correction or modify Local/Qwen.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, no auto-merge, at immutable
  report-only head `5385d066d2a869afd217e354996fe2027770a276`.
- First parent `b7b7f7ec00ec365fb245185a7e7588aa6c41ccbc`; report-only path
  `oap/reports/155-w-live-function-done-shape-and-final-acceptance.md`.
- All ten report-head checks pass; remote/local/worktree are clean.
- Local PR #7 remains immutable/green at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, read-only checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- The tree contains the temporary exact-profile event hook, pre-classification
  summary, forced failure modes, qualification CLI, and permanent hook-free runner.
- Strategic will recreate the private mode-0600 runtime reference before signaling;
  never render or commit endpoint/credential values.

Preserve immutable 155-t/u/v/w reports. The 155-x report must record that 155-v
directly established the Gateway done-item boundary and that 155-w lost only the
sanitized stdout after its corrected qualification.

## 1. Evidence-preserving invocation proof

Before protected traffic, update all operative topology/order/active/task/temp/env
anchors to 155-x and add a focused command/AST test or documented verifier helper
proving the qualification CLI emits exactly one bounded line to stdout and no private
stderr.

Run the summary-only fake provider failure with the exact shell pattern that will be
used for protected qualification:

- do not redirect stdout or stderr to a task file;
- do not use command substitution to retain the JSON;
- invoke the verifier directly so its safe `QUALIFICATION=FAILED {...}` line is
  present in the coding-agent tool result;
- capture only the numeric exit status afterward with shell control flow;
- require nonzero status, sanitized summary visible in tool output, empty stderr,
  coherent terminal accounting, cleanup, and no raw values.

Run the forced validator rejection the same way and require visible sanitized event
plus summary and nonzero status. Run valid fake qualification directly and require
the exact success line and zero status.

If any fake output is suppressed, redirected, deleted, malformed, multi-line beyond
bounded wrapping, or missing, stop before protected traffic.

## 2. Qualification-head gates

Before protected traffic:

- exact 155-x topology and Local anchors pass;
- live base-field function done shape passes and inner coordinate smuggling fails;
- all strict lifecycle/policy/replay/identity/privacy/accounting/hosted-tool negatives
  pass;
- all three evidence-preserving fake invocations pass;
- private runtime/credential/model preflight passes without rendering;
- worktrees are clean; full Ruff, compilation, diff checks, and all ten checks pass on
  the pushed qualification head.

## 3. One protected qualification with visible safe stdout

On the exact clean green head, execute exactly one zero-retry real Codex 0.149 ->
Gateway -> exact Local -> unchanged protected Qwen qualification using the direct
stdout invocation proven above. Do not redirect, pipe, command-substitute, or delete
the safe line.

Success requires exactly two turns/hops/inferences, one function execution/result,
one final message, reviewed optional reasoning, one created/completed terminal and
valid detailed usage per turn, two finalized accounting rows and aggregate counters,
signed identity/replay/route containment, privacy/secret/internal-header and hosted-
search absence, normal close, zero Gateway-induced Local disconnect, cleanup, and
protected post-health.

If qualification returns REJECTED/FAILED, do not retry or run final. Preserve the
visible sanitized event/summary/fixed code in the immutable report and make no claim
beyond it.

## 4. Mandatory temporary-code removal after success

Only after qualification passes:

- remove every temporary hook/env/writer, rejection/summary artifact code, forced
  failure fake/mode/CLI, qualification-only modes/stages/tests, and all historical
  qualification symbols/paths;
- preserve the live done-item validator fix, exact fake shape, zero-retry command,
  permanent product corrections/negatives, valid fake verifier, and permanent
  hook-free `--tool-roundtrip-protected` runner;
- prove hook/summary/env/path absence via AST/source/search;
- rerun hook-free valid fake, affected suites, Ruff, compilation, and all ten checks
  on the pushed hook-free head; no protected traffic during cleanup/CI.

## 5. One decisive hook-free protected final

On the exact clean hook-free green head, privately revalidate topology/runtime/
credential/model/Local head and run one zero-retry permanent protected roundtrip.
Require every section-3 success fact plus complete hook absence and protected post-
cleanup health. Do not retry a failure.

## Allowed paths

    app/slaif_gateway/providers/streaming.py
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
    oap/orders/155-x-preserved-qualification-output-and-final-closure.md
    oap/reports/155-x-preserved-qualification-output-and-final-closure.md

No Local/Qwen mutation, dependency/lockfile/schema/migration, product redesign,
hosted/custom authority expansion, unrelated cleanup, merge, release, or Objective
006 is authorized.

## Report and handoff

Publish one immutable report-only commit. PASSED requires the decisive hook-free
protected run; otherwise FAILED. Include complete 155-t/u/v/w/x topology, visible
safe qualification/final evidence, exact process/inference counts, CI, accounting,
privacy/security/close/cleanup, and hook absence. Retain no values, IDs, content,
endpoint, or credential.

On pass, post hook-free implementation/report heads directly to Local PR #7 for
prepared 005-n. Do not merge/auto-merge. Require all ten report-head checks, then
write exactly two response FIFO bytes `OK` once.
