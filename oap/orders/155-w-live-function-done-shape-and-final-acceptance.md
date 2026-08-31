# OAP Work Order — 155-w

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 307a491e511638779c4ecc67a7f9f09dbff1143f

## Objective and exact reason

Correct the one live-proven Gateway function `response.output_item.done` shape,
qualify the real two-turn protected path once, remove every temporary diagnostic on
success, and perform one decisive hook-free protected roundtrip.

155-v is immutable and terminally failed with one protected attempt and no retry.
Unlike 155-t/u, it retained enough evidence to identify the product boundary:

- Gateway, Local, and protected Qwen each observed one request/response/inference;
- Local and Qwen returned `2xx` SSE and Qwen closed normally;
- the exact pair-local Gateway validator wrote a sanitized rejection for
  `response.output_item.done` under a profile with reasoning=true, exact 0.149
  function events=true, streaming tools=true, bounded declarations, hosted search
  false;
- the live completed function item fields were exactly `arguments`, `call_id`,
  nullable `caller`, `id`, `name`, nullable `namespace`, `status`, and `type`;
- `output_index` and `sequence_number` existed at the event top level but not inside
  `item`;
- the current validator/fake require those two fields inside the done item.

Therefore the remaining product defect is Gateway strict validation of the live
function done item. The generic 155-v localization code does not erase the direct
artifact/normal-hop evidence. Do not modify Local or Qwen and do not reopen prior
tool-envelope, identity, prompt-cache, added/delta/arguments.done, or ordinary stream
work without contradictory direct evidence.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, no auto-merge, at immutable
  report-only head `307a491e511638779c4ecc67a7f9f09dbff1143f`.
- Its first parent is qualification implementation head
  `ce664052266b7a1cbd43b8083eaea22d3fa9c0fd`; its only changed path is
  `oap/reports/155-v-failure-localization-summary-and-protected-closure.md`.
- All ten report-head checks pass; local/remote heads and clean worktree agree.
- Local PR #7 remains OPEN/CLEAN at immutable report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation
  `258ae2ebad39651076937b9f027e60831b8d2786`, green `test`, read-only checkout
  `/home/ubuntu/codex-work/slaif-local-coding-005m`.
- The current Gateway tree contains temporary exact-profile rejection and
  pre-classification-summary hooks/modes plus the permanent hook-free protected
  runner. Temporary code must not survive final acceptance.
- The private runtime reference was removed by cleanup. Strategic will recreate it
  mode 0600 outside the repository before signaling; never render/commit values.

Immutable 155-t/u/v reports must not be rewritten. The 155-w report must record the
strategic correction above: 155-v's artifact and normal hop summary establish the
Gateway validator boundary even though its final classifier code remained generic.

## 1. Exact done-item correction

Use the protected artifact, pinned OpenAI Python 2.41.0 response models, vLLM 0.27.1
source, and actual protected serialization behavior.

For the exact Codex 0.149 -> Local function profile only:

- `response.output_item.done` must require the same bounded completed function base
  fields observed live, with optional `caller` only at null and `namespace` only at
  null;
- require event-level `output_index` and `sequence_number`, stable item/call IDs,
  declared name/type, completed status, accumulated argument equality, prior
  arguments.done, strict monotonic sequence, and exactly one function item;
- do not require, copy, synthesize, or authorize `item.output_index` or
  `item.sequence_number`;
- reject either inner field as an extra/smuggled field for this exact runtime
  contract;
- preserve added/delta/arguments.done/terminal response, reasoning/message,
  replay/idempotency, size/cardinality, privacy, accounting, hosted-tool, and generic
  route behavior unchanged.

Update the deterministic fake Qwen function done item to the exact live shape. Do not
retain dual permissive shapes merely because vLLM source attempted to pass extras;
the pinned OpenAI model and observed protected wire serialization omit them.

Required focused negatives: missing/wrong top-level index/sequence, inner index or
sequence present, duplicate/reordered done, mismatched ID/call/name/arguments/status,
non-null caller/namespace, undeclared function, second function, custom/MCP/hosted/
unknown smuggling, overflow, post-terminal event, inactive/non-pair profile.

## 2. Pure/fake and qualification-head gates

Before protected traffic:

- exact live artifact fixture passes the strict validator;
- prior fake shape with inner terminal fields fails;
- normal reasoning/message and all permanent negatives pass;
- real Codex valid composed fake passes two turns with one function result, one final
  message, two finalized rows, privacy, normal close, no artifact/summary;
- parser-safe forced validator rejection and summary-only provider failure still
  preserve bounded evidence and exit nonzero;
- fine-grained/fault-injected localization never raises raw `KeyError`;
- exact 155-w topology/order/active/Local anchors pass;
- private runtime/credential/model preflight passes without rendering;
- full Ruff, compilation, diff checks, and all ten CI checks pass on the pushed
  qualification head; worktrees are clean.

## 3. One protected qualification

Run exactly one zero-retry real Codex 0.149 -> Gateway -> exact Local -> unchanged
protected Qwen qualification.

Require:

- exactly two Gateway/Local/Qwen turns/hops/inferences;
- turn one: reviewed reasoning if emitted, one full function lifecycle including the
  corrected done item, no assistant message lifecycle;
- exactly one local function execution/result returned by Codex;
- turn two: reviewed reasoning if emitted, exactly one final message lifecycle, no
  function/custom/hosted lifecycle;
- one created/completed terminal and valid detailed usage per turn;
- two finalized PostgreSQL reservations/ledgers and correct aggregate counters;
- signed identity, replay ownership, route containment, raw-alias/secret/internal-
  header absence, hosted-search absence;
- normal upstream/downstream closes, zero Gateway-induced Local disconnect, no
  unknown/error/duplicate event, cleanup, and protected post-health.

If qualification rejects/fails, do not retry or run final. Preserve sanitized event
and pre-classification evidence, terminal accounting and cleanup; publish FAILED.

## 4. Mandatory temporary-code removal

Only after qualification passes:

- remove every temporary production hook/env/writer, rejection and summary artifact
  sanitizer/reader, forced validator/provider fake, qualification-only CLI/modes,
  temporary stages/tests, and all 155-t/u/v qualification symbols/paths;
- preserve the permanent strict validator correction, real-Codex fake verifier,
  zero-retry command, top-level continuation/replay, prompt-cache scrub, and permanent
  hook-free `--tool-roundtrip-protected` runner;
- prove hook/summary/env/path absence by AST/source/search tests;
- rerun hook-free valid composed fake, affected tests, Ruff, compilation, and all ten
  checks on the pushed hook-free implementation;
- send no protected traffic during cleanup or CI.

## 5. One decisive hook-free protected final

On the exact clean hook-free green head, privately revalidate topology/runtime/
credential/model/Local head and run exactly one zero-retry permanent protected tool
roundtrip. Require every section-3 success fact, hook absence, complete cleanup, and
protected post-health. If it fails, do not retry; report the exact safe boundary,
accounting, and cleanup facts.

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
    oap/orders/155-w-live-function-done-shape-and-final-acceptance.md
    oap/reports/155-w-live-function-done-shape-and-final-acceptance.md

No Local Coding/Qwen mutation, dependency/lockfile/schema/migration, envelope/
identity/route redesign, hosted/custom authority expansion, unrelated cleanup,
merge, release, or Objective 006 is authorized.

## Report and handoff

Publish one immutable report-only commit. `RESULT=PASSED` requires the decisive
hook-free protected run; otherwise FAILED. Include complete 155-t/u/v/w topology,
the 155-v ownership correction, exact live/fake event contracts, protected process/
inference counts, CI, accounting, security/privacy/close/cleanup, and hook absence.
Retain no values, IDs, content, endpoint, or credential.

On pass, post the hook-free implementation and report heads directly to Local PR #7
for prepared 005-n. Do not merge or enable auto-merge. Require all ten report-head
checks, then write exactly `OK` (two bytes, no newline) to the verified response FIFO.
