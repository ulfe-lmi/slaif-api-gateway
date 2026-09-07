# OAP Work Order — 161-b

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 to correct only the repository-owned
prove-before-fix verifier defect established by immutable 161-a. Reproduce the
exact real Codex 0.149 full-image then same-session crop/history request using
the valid distinct synthetic image fixtures and command topology already
proved by Local 005-q. Require the resumed Gateway request to contain both the
prior assistant `output_text` history and the new crop image, then prove the
same exact pre-Local rejection.

This continuation remains pre-production. Do not modify any `app/` or
documentation path and do not implement assistant-history acceptance. A
successful 161-b report authorizes strategic review only; a later continuation
is required for product behavior.

## Reason and accepted 161-a evidence

The 161-a verifier proved the core mechanism against the exact clean Gateway:

- real task-local `@openai/codex@0.149.0`;
- Gateway statuses `200,200,400`;
- exact error `responses_input_content_part_not_supported`;
- exact parameter `input[5].content[0].type`;
- enclosing role `assistant`;
- content part type `output_text`;
- nonempty valid-Unicode text classification with value discarded;
- fake Local remained at two signed requests and did not receive the rejected
  turn;
- zero retry and bounded cleanup/privacy behavior.

It correctly stopped because all three observed requests had image-count class
`zero`. The verifier used one hand-written minimal one-pixel PNG for both
turns, inserted image arguments into generic capture commands, selected the
resume by retained thread ID, and unit-tested only that `--image` occurred
somewhere in argv. That did not reproduce Local 005-q's established
full-image/crop wire evidence.

Source correlation now establishes the bounded verifier correction:

- exact Codex 0.149 `ResumeArgs` accepts `--image` and either a session ID or
  `--last`; the parser is not product authority;
- Local 005-q implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec` uses deterministic valid RGB PNG
  fixtures with correct chunk CRCs, a 4x2 full scene and distinct 2x2 crop;
- Local's exact private-home command suffixes are initial
  `exec --json --strict-config --cd <repo> --image <full>
  --output-last-message <file> <prompt>` and resumed
  `exec resume --last --json --strict-config --image <crop>
  --output-last-message <file> <prompt>`;
- the private task Codex home makes `--last` unambiguous and matches the
  accepted 005-q mechanism without retaining a thread ID.

## Exact current state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-b`; amend the existing Objective-161 PR. Do not create a new PR.
- PR: #298, `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`.
- Base/head: `main` / `oap/161-codex-assistant-output-history`.
- Exact base: `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- Immutable 161-a verifier implementation head:
  `9e9de4fe3bd1e12747021b4a98ab04aa474ea655`.
- Immutable 161-a FAILED report head/current starting PR head:
  `3f9312a3ef00159574607998711cea6146e7734f`.
- Report path:
  `oap/reports/161-a-codex-0149-assistant-output-history.md`.
- The report commit changes only that report and its first parent is the
  literal 161-a implementation head.
- PR #298 is open, non-draft, mergeable, and `UNSTABLE` only because the unit
  job found two active-order governance failures. The nine other checks are
  successful.
- Governance requires the exact first line used by this order. The 161-a
  missing `CREATE_NEW_PR` phrase remains immutable historical evidence; with
  `161-b` active, the initial-round-only assertion is no longer applicable.
- Gateway `main` is unchanged at `910ddaa...`.
- Historical PR #291 remains out of scope and untouched.
- Local PR #7 remains frozen at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.

Abort and report any discrepancy in PR identity, branch, base, starting head,
or Local authority. Never create a replacement PR.

## Exact allowed paths

Only these paths may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-b-exact-image-history-prefixed-reproduction.md`
- `oap/reports/161-b-exact-image-history-prefixed-reproduction.md`

No app, existing fixture, accepted Objective-160 verifier/test, Local server
module, replay/HMAC, database/schema/migration, dependency/lockfile, CI,
doctrine, or documentation path may change.

## Required verifier correction

Preserve every bounded 161-a observer, error, signing, lifecycle, zero-retry,
PostgreSQL no-side-effect, privacy, and cleanup property. Correct only the
image fixture/command/observation proof:

1. Replace the hand-written one-pixel image with two distinct deterministic
   valid RGB PNGs equivalent to the Local 005-q 4x2 full scene and 2x2 newest
   right-side crop. Generate correct PNG chunks/CRCs without adding a
   dependency. Keep dimensions, bytes, paths, and permissions bounded.
2. Use a private task Codex home containing only this session. Build the
   initial and resumed commands with the exact Local-proven exec suffixes above
   while retaining the Gateway verifier's server-selected model/provider
   profile, `--ignore-user-config` isolation where supported, global approval/
   sandbox bypass required by the fixture, and request/stream retry values
   exactly zero.
3. Resume with `exec resume --last`, not a retained explicit thread ID. Prove
   the private home has exactly one eligible session relation before resume.
   Do not print or retain the session/thread ID.
4. Unit-test exact normalized argument order and values, including that the
   initial command binds the full fixture and the resumed command binds the
   distinct crop fixture. Token-presence-only assertions are insufficient.
5. Extend bounded structural observation to distinguish initial full-image and
   resumed crop-image classes using only expected byte length and fixed
   synthetic SHA-256 equality booleans/classes. Do not retain data URLs or
   image bytes after comparison.
6. Prove actual Gateway-bound requests, not argv alone, carry the expected
   image. The initial phase must contain the full-image class; the rejected
   resumed request must contain exactly one image part matching the crop class,
   alongside the prior assistant `output_text` history. Any intervening
   function-result continuation must remain within the established finite
   request progression and may retain only the expected full-image class.
7. Keep the fake Local at exactly two signed accepted requests before the
   resumed rejection. Its existing function then assistant-message lifecycle
   remains unchanged. Do not steer or hand-construct the resumed request.
8. Add negative unit evidence for missing image, same full/crop fixture,
   malformed fixture, wrong argv placement/binding, stale full-image on resume,
   multiple/unexpected images, raw-value retention, and observer overflow.

If source or execution shows the image omission has another cause, publish the
first fixed safe class and stop. Do not introduce a second verifier correction
or any production change in 161-b.

## One exact reproduction

After complete unit, Ruff, format, compilation, diff, governance, and privacy
preflight passes, execute exactly one zero-retry reproduction:

```text
real task-local Codex 0.149.0
  -> unchanged Gateway base behavior
       -> signed fake Local
            -> fake provider
```

Require all of:

- exact package/version and previously accepted binary provenance;
- one private session, initial full-image command, natural function/result and
  assistant output lifecycle, then natural `resume --last` crop command;
- finite Gateway progression `200,200,400` with no retry;
- actual initial full-image wire class and actual resumed distinct crop wire
  class;
- resumed request contains prior role `assistant`, exact part type
  `output_text`, exact fields `type,text`, nonempty valid-Unicode bounded text,
  and exactly one expected crop image;
- exact safe error code
  `responses_input_content_part_not_supported` and parameter
  `input[5].content[0].type`;
- fake Local remains exactly two signed requests and does not advance for the
  rejected turn;
- no reservation, ledger, replay, or other side effect from the rejected
  pre-admission request;
- fixed success output only, with complete task-owned cleanup.

Retain only ordinals, count/size/hash-equality classes, roles, content types,
field-name sets, nonempty/Unicode booleans, status classes, safe code/parameter,
Local-count delta, retry count, and cleanup booleans. Never retain or print
prompts, assistant text, images/data URLs, request/SSE bodies, IDs/call IDs,
headers, credentials, signatures, nonces, endpoints, DB URLs, paths, or
arbitrary errors.

If any required predicate fails, publish `RESULT=FAILED` and stop. Do not run a
second exact reproduction in this round.

## Verification

Run:

- complete `tests/unit/test_codex_0149_assistant_output_history.py`;
- Ruff check and repository format check on both changed Python files;
- Python compilation of both changed Python files;
- active OAP governance tests, including unique order/header behavior;
- `git diff --check` and exact allowed-path proof;
- fixed privacy/output/source scans and cleanup tests;
- the one exact real-Codex reproduction only after all preflight passes;
- all ten normal GitHub CI/CodeQL checks on the exact final report head.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or
environment-blocked required evidence is not a pass. Do not run unrelated full
local suites unless reproducing a normal CI failure.

## Security and non-goals

This is verifier evidence only. Do not change or claim assistant-history
admission, client policy, provider forwarding, Local behavior, authority,
replay/HMAC, identity/signing, route/model/provider selection, hosted/local
tools, limits, pricing, quota/accounting, audit, privacy, or retention.

Do not modify or contact Local PR #7, protected Local/Qwen, provider inference,
production databases, PR #291, deployment, cutover, release, newer Codex,
OpenCode, Antigravity, or future Gateway objectives. No protected credential or
traffic is authorized. Coding never merges or enables auto-merge.

## Publication contract

Commit this order and `oap/active` unchanged on the existing PR branch with the
verifier/test correction. Record the literal final non-report implementation
head. Publish exactly one immutable report:

`oap/reports/161-b-exact-image-history-prefixed-reproduction.md`

The report must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- `Implementation head SHA: <literal 40-hex pre-report commit>`;
- `Report publication commit: SELF`;
- exact same-PR/base/branch/head topology and 161-a immutable parent;
- source-derived fixture/command defect and exact correction;
- complete preflight and one-run chronology;
- actual full/crop wire classes, assistant history/error/Local-delta facts,
  no-side-effect, privacy, cleanup, and retry evidence;
- all ten exact final-report-head check conclusions;
- explicit no-production/no-doc/no-Local/no-protected/no-merge statements;
- lifecycle labels:

```text
PREFX-REPRODUCTION-ACCEPTED = YES|NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The report commit must change only that report, have the literal implementation
head as first parent, and be the verified remote PR #298 head before sending
exactly `OK` to the response FIFO. Return to the blocking control FIFO. Only
strategic review may authorize a production continuation.
