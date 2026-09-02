# OAP Work Order — 155-af

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 1a7c8c51a01d4abcb8b8529e1b9ec272baaa20d6

## Exact authorization and non-goals

The human explicitly authorized `155-af` on existing PR #291 from immutable 155-ae
FAILED report head `1a7c8c51a01d4abcb8b8529e1b9ec272baaa20d6`.
This is one source-proven correction and final acceptance attempt. It does not
authorize `155-ag`, broad Objective-155 refactoring, Local Coding or Qwen changes,
weakening the permanent 155-ae visible-reasoning contract, granting encrypted replay
as a workaround, merge, auto-merge, cutover, or release.

Preserve the permanent 155-ae Codex-0.149 visible-reasoning implementation. Do not
revert, strip, redact, summarize, or fabricate identity for accepted visible reasoning.
Preserve every earlier activated order/report as immutable.

## Objective

Prove and correct the early null-encrypted replay misclassification, extend the closed
Gateway error projection, correct the verifier's terminal accounting-pair predicate,
run one protected two-turn diagnostic, and—only if fully green—remove temporary
qualification hooks and run one fresh hook-free protected acceptance.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, without auto-merge, at
  report-only head `1a7c8c51a01d4abcb8b8529e1b9ec272baaa20d6`.
- Its first parent is diagnostic implementation head
  `956ec1e08b5f951f482ae12d0bbd265219bcadef`; the report commit changes only
  `oap/reports/155-ae-codex-0149-idless-visible-reasoning-and-final-acceptance.md`.
  The 155-ae report was created once and is `RESULT=FAILED`.
- All ten report-head checks pass. Remote `main` remains
  `7ffce834915b74809109e8b579d8541cdcfa9df7`; Gateway and exact Local worktrees are
  clean.
- Local Coding PR #7 remains read-only at report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`.
- Permanent 155-ae behavior is present: the exact 0.149 client-policy spec validates
  and preserves absent/null/present IDs, bounded `summary_text`, `reasoning_text`, and
  `text` visible state, including valid multiline UTF-8; it never manufactures IDs;
  default/OpenAI, 0.147, and ID-less encrypted paths remain strict.
- 155-ae's protected turn 1 reached Local/Qwen normally. Turn 2 contained absent ID,
  nonempty visible content, empty summary, and an `encrypted_content` field whose
  value was null, then received a Gateway 4xx before Local. The qualification key
  grants exactly request envelope, client tools, and streaming tool events—not
  encrypted reasoning replay.
- The repository selector test permits ordinary one-letter IDs and exact `155-aa`
  through `155-ae`; add only exact `155-af` and keep `155-ag` and generalized forms
  rejected.
- The private runtime reference will be an owner-only mode-0600 two-key file. Never
  render or retain its values.

## 1. Mandatory pre-fix full-policy reproduction

Before modifying production behavior, add a synthetic application-level
`ResponsesRequestPolicy.apply()` regression structurally equivalent to the 155-ae
turn-2 item:

- `type == "reasoning"`;
- ID absent;
- nonempty valid bounded visible content;
- empty summary;
- `encrypted_content` present and exactly null;
- exact allowed item fields;
- request-envelope capability true;
- encrypted-reasoning-replay capability false;
- exact 0.149 client policy spec and the existing function-call/output continuation
  context as needed.

Run it against the unmodified detector and record only that it fails with exact code
`responses_codex_encrypted_reasoning_replay_not_allowed` before input validation. Do
not use real reasoning text. If this pre-fix reproduction does not uniquely establish
the stated path, stop and publish `RESULT=FAILED`; do not implement the proposed fix.

Source facts to prove:

1. `ResponsesRequestPolicy.apply()` calls
   `responses_codex_encrypted_reasoning_replay_requested()` before `_validate_input()`;
2. the current detector returns true from field presence alone;
3. the capability guard then denies the deliberately non-granted encrypted-replay
   capability;
4. the permanent visible validator would otherwise accept absent/null encrypted state.

## 2. Exact product correction

Only after section 1 passes, change the generic detector so a reasoning input requests
encrypted replay only when `encrypted_content` is present **and its value is not
null**. Do not add a concrete module-ID branch.

Required behavior:

- absent `encrypted_content` -> not encrypted replay;
- `encrypted_content: null` -> not encrypted replay and may reach the selected 0.149
  visible-state validator;
- any non-null value, including malformed types -> encrypted-replay capability path;
- without that capability, any non-null value fails at the existing capability guard;
- with that capability, malformed values fail existing shape validation;
- nonempty encrypted state still requires a valid existing provider reasoning ID;
- ID-less/null-ID encrypted state remains prohibited;
- visible content mixed with non-null encrypted state remains prohibited.

Do not grant `codex_encrypted_reasoning_replay` to the qualification key or route. Do
not modify Local Coding/Qwen, the client-visible content contract, routing, identity,
or accounting production behavior.

Add an application-level post-fix `apply()` test proving the exact null-valued live
shape passes without encrypted-replay capability, preserves visible content and field
presence/value exactly, and gains no ID. A parallel non-null test must still fail at
the capability boundary exactly as before.

## 3. Closed Gateway error projection

Extend only the verifier's source-reviewed Gateway error vocabulary so bounded output
distinguishes at minimum:

    responses_codex_encrypted_reasoning_replay_not_allowed
    responses_codex_reasoning_visible_invalid
    responses_codex_reasoning_visible_too_large
    existing Codex tool-roundtrip/replay/route/request-policy classes

Use fixed safe classes; unknown or malformed values remain `other`. Never retain
arbitrary error code/message/exception text, bodies, or values. Add pure tests for
each exact mapping, cross-boundary values, unknown fallback, ordinal alignment,
tampering, and privacy canaries.

## 4. Qualification accounting predicate correction

Verifier only: amend `_qualification_terminal_sequence_valid()` so the last or sole
admitted turn may be any coherent intentional terminal pair:

    finalized / finalized
    released  / failed
    finalized / estimated

All earlier successful admitted turns in a multi-turn sequence must remain
`finalized/finalized`. Zero admitted turns is valid only with zero rows. Pending,
unknown, mismatched counts, incoherent pairs, or more rows than admitted turns remain
invalid.

Keep the 155-ae correction that derives expected rows from actually admitted Local
turns rather than raw Gateway request attempts. A pre-admission rejection creates no
dummy row. Do not alter production accounting or hide failed/released/estimated/held
state.

Add explicit tests for zero turns, one finalized success, two finalized successes,
failure after reservation, terminal estimated state, mismatched row counts, pending
reservation/ledger, incoherent pairs, and an earlier non-finalized success.

## 5. Pre-protected regression gates

Before any protected request, pass:

- the observed null-encrypted pre-fix failure proof and post-fix full-`apply()` pass;
- visible reasoning content and absent ID exact preservation through normalization,
  policy, replay-candidate, upstream reconstruction, Local HMAC signing, and transport
  tests;
- default/OpenAI and Codex 0.147 missing-ID strictness;
- non-null encrypted capability/valid-ID requirements and malformed/null/mixed edge
  negatives;
- visible part type/field/count/per-part/aggregate-byte bounds;
- function-call/output chronology and taxonomy regressions;
- hosted-search/MCP/provider authority negatives;
- exact Local pair, signed identity, nonce/replay, isolation, privacy, quota,
  reservation/finalization/rollback tests;
- one- and two-turn coherent finalized/finalized accounting tests;
- normal two-turn fake success plus relevant encrypted/null/malformed and accounting
  fake matrices;
- full Ruff/format/compilation, focused affected tests, relevant PostgreSQL tests,
  diff/scope/source checks, and all ten PR checks on the exact implementation head.

Update only affected compatibility/accounting documentation if behavior wording needs
clarification. Preserve the pinned Codex rust-v0.149.0 source contract and synthetic
fixture. No protected traffic occurs before the exact clean green head.

## 6. One protected diagnostic acceptance

Run exactly one zero-retry process:

real task-local Codex 0.149.0 -> Gateway -> unchanged Local Coding at
`4d3ab2f...` -> unchanged protected Qwen.

Do not steer the prompt/tools/config/model/route. Direct bounded stdout only.
Acceptance requires:

- turn 1 reaches Local/Qwen once, returns valid 2xx SSE, and closes normally;
- Codex naturally issues turn 2;
- null encrypted content does not request encrypted-replay authority;
- the permanent 0.149 validator accepts and exactly preserves the state-bearing
  ID-less visible reasoning item without fabricating an ID;
- turn 2 reaches Local and Qwen once;
- function-call/output chronology and final assistant/message lifecycle complete;
- no Gateway 4xx/stream error or Gateway-induced Local disconnect;
- valid usage; coherent terminal accounting for every admitted request; zero pending;
- signed identity, replay/idempotency/tamper/session isolation, hosted-search denial,
  route containment, privacy, cleanup, and post-health remain green.

If another Gateway 4xx occurs, publish its improved exact safe class and stop without
another correction. If Local/Qwen rejects after Gateway admits/forwards turn 2,
publish the bounded ownership evidence and stop. Never modify Local/Qwen or retry.

## 7. Hook-free final

Only if section 6 succeeds completely:

1. remove all temporary `SLAIF_155X_*` qualification hooks/writers and other
   diagnostic-only production machinery required to be removed by 155-ae;
2. retain the permanent 0.149 client-policy contract, source fixture, strict tests,
   ordinary fake verifier, and permanent hook-free `--tool-roundtrip-protected` path;
3. prove hook/artifact/raw-value sink absence outside immutable OAP history;
4. pass full affected pure/fake/PostgreSQL gates, Ruff/format/compile, privacy/scope
   checks, and all ten PR checks on the exact hook-free implementation head;
5. run exactly one fresh zero-retry hook-free protected two-turn qualification with
   the section-6 acceptance criteria.

Only this hook-free run may establish Gateway acceptance. Do not retry if it fails.

## Privacy, cleanup, and allowed paths

Retain no real reasoning text, prompts, bodies, raw SSE/headers, IDs, signatures,
credentials, endpoints, body/signature digests, canonical bytes, nonce/timestamps,
tool content, arbitrary errors/exceptions, or temporary paths. Live visible reasoning
is transient only. Evidence uses closed classes/booleans/counts and synthetic text.

At closure remove the runtime reference and every 155-af root, installed Codex,
diagnostic artifact, process, listener, container, database, bytecode, and temporary
file. Preserve unrelated state and both worktrees.

Allowed paths:

    app/slaif_gateway/services/responses_request_policy.py
    app/slaif_gateway/services/responses_gateway.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_responses_request_policy.py
    tests/unit/test_responses_codex_multiturn_replay.py
    tests/unit/test_upstream_payload_reconstruction.py
    tests/unit/test_v1_responses_quota.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_oap_governance.py
    tests/e2e/test_openai_python_client_responses.py
    docs/accounting.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    oap/active
    oap/orders/155-af-null-encrypted-replay-detector-and-final-acceptance.md
    oap/reports/155-af-null-encrypted-replay-detector-and-final-acceptance.md

`responses_gateway.py` may change only for section-7 removal after a successful
diagnostic. Do not change module/spec/fixture metadata from 155-ae, server registry,
Local/Qwen/Codex, schema, migration, dependency, lockfile, prior order/report,
AGENTS/OAP protocol, merge state, release state, or unlisted product behavior.

## Immutable report, handoff, and response

Before creating the report, assert no `oap/reports/155-af-*` exists. Create exactly
one immutable report-only `SELF` commit whose first parent is the terminal
implementation head. Never amend or recommit it after publication, including after
compaction, restart, CI wait, or wording review. On resume with a report, reconcile
read-only only.

`RESULT=PASSED` requires the protected diagnostic, complete hook removal, and fresh
hook-free protected final all green. Otherwise publish the narrowest `RESULT=FAILED`
evidence and stop. Record pre-fix/post-fix proof, exact safe failure class if any,
accounting semantics/tests, diagnostic/final counts, hook absence, source/fixture and
module policy continuity, security/privacy/replay/tool containment, cleanup, topology,
and all checks.

On pass only, post the exact hook-free implementation and immutable report heads to
Local Coding PR #7 and stop Objective 155. Do not merge or activate 155-ag. Require
all ten checks on the immutable report head, send exactly two response FIFO bytes
`OK` once, return to one blocked control-FIFO read, and stop.
