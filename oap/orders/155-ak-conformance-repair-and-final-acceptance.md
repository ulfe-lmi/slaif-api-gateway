# OAP Work Order — 155-ak

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Starting remote/report head: c2c8f01c25c7f63701b85e8cd4d55e0055931f3b
Frozen cleaned production candidate: e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4
Functionally demonstrated product head: 3cce1a7612fc9919adf26df9952baabaf703c348
Exact Local Coding authority: 4d3ab2fd97d249710f952dd3d2c28936138cc8fa

## Authority, purpose, and hard boundary

The human explicitly authorizes this exceptional Objective-155 continuation,
`155-ak`, only because immutable 155-aj did not faithfully implement or report
its authorized acceptance obligations. Continue on existing PR #291 from exact
immutable 155-aj FAILED report head
`c2c8f01c25c7f63701b85e8cd4d55e0055931f3b`.

155-ak is evidence, test, and verifier closure only. It authorizes no Gateway
product compatibility behavior. Do not change Local Coding, Qwen, replay
semantics, identity, production SSE validation, accounting, quota, routing,
provider behavior, or tool authority. Do not activate or infer 155-al. Do not
merge, enable auto-merge, cut over, deploy, or release.

Preserve immutable
`oap/reports/155-aj-final-hook-free-objective-155-acceptance.md` exactly as
published with `RESULT=FAILED`; never amend, replace, rewrite, or reinterpret
it. Preserve every earlier activated order/report byte-for-byte.

Production behavior is frozen at cleaned candidate
`e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4`. Its only `app/` semantic delta
from functional head `3cce1a7612fc9919adf26df9952baabaf703c348`
must remain deletion of Objective-155 diagnostic qualification-hook machinery.
The final implementation head must satisfy:

```text
git diff --exit-code e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4 -- app
```

Do not alter the accepted Local-Coding signed-identity grammar correction,
Codex-0.149 visible reasoning, null-encrypted handling, ID-less tool-call
handling, call-ID-HMAC replay behavior, or any other production behavior.

## Verified starting state

- PR #291 is open, non-draft, mechanically mergeable/CLEAN, unmerged, and has
  no auto-merge request. It is the only Objective-155 PR.
- Remote feature head and the clean task worktree are exactly `c2c8f01...`.
  Its only changed path is the immutable 155-aj report; its first parent is
  cleaned candidate `e503f964...`.
- Immutable 155-aj is `RESULT=FAILED`. All ten checks pass on its report head.
- Remote `main` is exactly `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Local Coding is read-only and clean at exact head `4d3ab2f...`.
- No 155-ak order/report existed before this activation.
- The owner-only mode-0600 runtime reference
  `/tmp/slaif-155f-runtime.env` contains exactly the approved endpoint and
  credential-source keys. Protected model discovery returned 2xx. Never print,
  hash, log, commit, or retain either value or the sourced credential.
- Exactly one coding-agent reader was blocked on the verified control FIFO.
- The unchanged 0.148 test and its verifier are blob-identical between PR base
  `7ffce834...` and cleaned candidate `e503f964...`:
  test blob `4928a55cf3cc336d8a419f0c053471e9f050d7db`, verifier blob
  `1b8dd153ee1b4e195ad0af2cb7081add3d02c714`.

## Allowed repository paths

Only these tracked paths may change in the implementation commit(s):

- `scripts/verify_local_coding_full_stack.py`;
- `scripts/verify_qwen38_text_codex.py`, only for a proved bounded verifier
  stage-classification correction;
- `tests/unit/test_local_coding_full_stack_verifier.py`;
- `tests/unit/test_codex_replay_service.py`;
- `tests/integration/test_codex_replay_references_postgres.py`, only if needed
  for explicit replay test coverage without production changes;
- `tests/unit/test_oap_governance.py`;
- `oap/active` and this exact activated order;
- final report
  `oap/reports/155-ak-conformance-repair-and-final-acceptance.md` in its own
  report-only commit.

The existing `tests/unit/test_qwen38_text_codex_candidate.py` is read-only and
must be executed unchanged. No `app/`, Local Coding, Qwen, schema, migration,
dependency, lockfile, public documentation, deployment, or unrelated test
change is allowed. Temporary detached worktrees, exact tool installations,
containers, PostgreSQL databases, Redis processes, and private bounded
evidence under owner-only `/tmp` roots are allowed and must be removed.

## 1. Machine-checked 155-aj discrepancy inventory

Before changing verifier/test behavior, compare the exact 155-aj order,
implementation head `e503f964...`, immutable 155-aj report, actual collected
tests, and source. Encode the discrepancy inventory in machine-checkable
verifier/test data, then reproduce it as a bounded table in the 155-ak report.
At minimum prove and report:

- the 155-aj report implies complete verifier SSE vocabulary, but its verifier
  set omits all four required approved reasoning lifecycle names;
- the report maps all six downstream outcomes plus `other` to
  `test_boundary_snapshot_classification_has_fixed_downstream_outcomes`, while
  that test has only two collected parameter cases;
- the exact Local matrix definition/executed row count is eight, not the
  claimed sixteen, and lacks the mandated fixed legacy `-`/`_` rows;
- required HMAC rotation cases versus actual collected tests, including that
  the claimed new-v2 function/ID-less case is not created by the cited test;
- the report records `postgres_start_failed`, while strategic reproduction
  passed PostgreSQL setup and reached a timeout waiting for the second mocked
  upstream request. Reproduce the truthful candidate and baseline stages.

Report prose is not evidence. The discrepancy manifest must be derived from
source, collection, and executed results and must fail if an expected
discrepancy silently changes.

## 2. Repair only the verifier SSE vocabulary

Source-check the exact production `ResponsesStreamEventValidator.validate()`
branches used by the active Codex-0.149 Local profile. Add exactly these
already-production-reviewed names to the verifier's closed vocabulary:

```text
response.reasoning_part.added
response.reasoning_text.delta
response.reasoning_text.done
response.reasoning_part.done
```

Do not use prefix/regex/wildcard matching, copy unrelated generic event sets,
or permit reasoning-summary, hosted, or other profile-only events. Do not edit
the production stream validator.

Add tests proving each exact name individually; a valid ordered lifecycle;
the 155-ai structural lifecycle without `other`; exact counts and
`unknown_events=false`; arbitrary unknown `response.reasoning.*` maps to
`other`; orphan, duplicate, reordered, and malformed lifecycles remain
invalid; and recognition of a name cannot bypass lifecycle validation.

Add a mechanical source/AST contract showing the verifier active-profile
vocabulary covers every event type accepted by the exact production branches
used by this pairing while excluding unrelated profiles. Prove the vocabulary
cannot silently grow via prefix, `startswith`, regex, or wildcard behavior.

## 3. Complete the snapshot predicate matrix

Add an explicit parameterized case or dedicated test for every item below.
Each case must mutate/assert its named bounded predicate independently and
must not be replaced by a generic sanitizer test:

- missing/non-list structure collection;
- one rather than two structures;
- more than two structures;
- absent ordinal 0; absent ordinal 1; `invalid=true`;
- missing/duplicate `response.created`;
- missing/duplicate `response.completed`;
- response-ID relationship false;
- wrong created status; wrong completed status; model mismatch;
- missing terminal output; invalid terminal output;
- missing usage; invalid usage;
- genuine unknown event; error event; trace overflow;
- abnormal close; downstream early close; handler error; upstream truncation;
- reasoning lifecycle mismatch; function lifecycle mismatch; message lifecycle
  mismatch.

Independently construct and assert all seven closed outcome values:

1. `local_turn2_rejected_before_qwen`;
2. `local_invoked_qwen_turn2_qwen_rejected_or_failed`;
3. `qwen_turn2_completed_local_stream_invalid`;
4. `local_qwen_turn2_completed_gateway_stream_invalid`;
5. `producer_boundaries_valid_verifier_expectation_wrong`;
6. `full_two_turn_path_succeeded`;
7. `other`.

No outcome may follow from a status name without its required ordinal/count/
terminal evidence. Add a meta-test inspecting collected parameter definitions
and proving the exact seven-value enum coverage. The final report maps every
predicate and outcome to actual passing node IDs generated from test evidence.

## 4. Complete machine-checked HMAC rotation coverage

Production replay code is frozen. Add explicit independent tests for:

- old-v1 present-item lookup after v2 activation with v1 material available;
- old-v1 ID-less call-ID lookup under the same rotation;
- new-v2 function call by present item ID and then that same reference through
  ID-less call-ID fallback;
- equivalent new-v2 custom-tool present/ID-less lookup because the implemented
  contract supports it;
- old-v1 present-item and ID-less call lookup both failing when v1 material is
  unavailable;
- wrong present item ID plus correct call ID never downgrading;
- deterministic ambiguous cross-version call-ID rows failing closed;
- unavailable/incorrect stored HMAC version failing closed;
- cross-key, route, provider, model, and tool mismatches failing closed;
- raw item ID, call ID, HMAC digest, and privacy canaries absent from exception,
  log, CLI, report, and bounded evidence outputs.

Represent this requirement as a source-checked obligation table or meta-test
derived from exact test names. Do not weaken same-key/kind/tool/expiry/route/
provider/model or PostgreSQL truth. If any test exposes a production defect,
publish FAILED and stop; no replay correction is authorized.

## 5. Actual Local matrix of at least sixteen rows

Define a finite reviewable synthetic matrix in verifier/test code and assert
`len(matrix) >= 16`. Span multiple owner UUIDs, Gateway-key UUIDs, canonical
session UUIDs, and repository scopes. Include the fixed domain/input vectors
whose legacy unprefixed base64url representations began with `-` and `_`.

For every row, invoke corrected Gateway derivation/signing and the actual
unchanged Local `verify_signed_identity()` from exact clean head `4d3ab2f...`.
Prove all four grammar predicates, exact-body signing, Local acceptance, body
tamper rejection with fresh replay state, signature tamper rejection, nonce
replay rejection, and absence of raw source values from derived identities and
retained evidence. Prevent sibling bytecode/cache writes and restore process
state. Retain and report only the runner-derived row count and booleans.

## 6. Truthful exact-0.148 candidate/baseline differential

Use one identical owner-only isolated environment, identical timeout and
infrastructure, and exact verified task-controlled
`@openai/codex@0.148.0` exposed only as `/usr/bin/codex` inside that boundary.
Never modify the host Codex. Prove package name/version, executable provenance,
`codex-cli 0.148.0`, isolated path resolution, and unchanged host identity/
version before and after.

Run unchanged `tests/unit/test_qwen38_text_codex_candidate.py` first against
cleaned candidate `e503f964...`, then against PR base `7ffce834...`, using the
same disposable safety-valid PostgreSQL/Redis infrastructure and test timeout.
The test/verifier blobs are identical at those heads, so do not substitute a
different test. Retain only collected/passed counts, failing node/class,
bounded stage, first/second mocked-request observation booleans, timeout/
process-exit class, and PostgreSQL readiness/start boolean. Retain no request,
response, prompt, credential, path, arbitrary exception, or raw process output.

Classify exactly:

- candidate passes: gate closed;
- candidate fails and baseline passes: PR regression, publish FAILED and stop;
- both fail identically before candidate-specific behavior: pre-existing
  baseline/test-harness defect; it may be explicitly waived only for this
  Objective-155 non-regression gate if every other requirement is green;
- failures differ: publish FAILED and stop for strategic review.

Strategic evidence already disproves 155-aj's `postgres_start_failed` as the
terminal stage: with safety-valid disposable PostgreSQL and required Redis
binaries, exact 0.148 reached `facts_since(0, 2)` and timed out waiting for the
second mocked request. Reproduce both heads and determine the bounded truthful
class. Correct only a proved verifier stage-projection error; never alter or
weaken the unchanged legacy test.

## 7. Automatic obligation manifest and pre-protected gate

Build a verifier-generated obligation manifest backed by test collection and
executed results. It must enumerate every requirement in Sections 1–6 and the
gates below, name its proving test/evidence, and produce exact `missing=[]`.
Tests must fail if a required enum/case/test disappears. Manually written
report prose cannot satisfy or override the manifest.

Before protected traffic, all of these must pass on a clean pushed exact
implementation head:

- four-event verifier vocabulary, lifecycle positives, and unknown/malformed
  negatives;
- every individual snapshot predicate and all seven outcome classes;
- complete HMAC rotation matrix and its meta-check;
- actual Local matrix with runner-derived count at least sixteen;
- truthful candidate/baseline 0.148 differential and any allowed identical-
  baseline waiver;
- fake prefixed-ID and ID-less two-turn paths;
- fake provider failure and verifier-owned fake validator failure;
- PostgreSQL replay tests executed, not skipped;
- PostgreSQL accounting/context tests executed, not skipped;
- privacy, source, scope, and AST gates;
- no `SLAIF_155X_` or qualification writer under `app/`;
- no `app/` diff from frozen candidate `e503f964...`;
- Ruff, formatting, compile, and full relevant tests with no unexplained skip,
  xfail, cancellation, pending result, or environment exclusion;
- all ten GitHub checks successful on that exact candidate head.

If `missing` is not exactly empty or a non-waived gate fails, do not source the
protected runtime reference and do not send protected traffic. Publish a
truthful immutable FAILED report with the narrowest bounded evidence.

## 8. Exactly one final protected hook-free run

Only after the machine-checked manifest is complete and every pre-protected
gate above is green, execute exactly one zero-retry process:

```text
task-local Codex 0.149.0
  -> Gateway with frozen e503f964 production semantics
  -> unchanged Local Coding 4d3ab2f
  -> unchanged protected Qwen
```

Use the existing owner-only runtime reference without printing or retaining
its values. Preserve the exact intended route, model, tools, and workload.
Require and retain only bounded facts proving:

- two Gateway requests and two 2xx SSE responses;
- two Local requests and two 2xx SSE responses;
- two signed identities fully verified;
- two Qwen inference calls and successful terminal completions;
- exact reviewed reasoning names, no `other`/unknown event;
- valid function lifecycle on turn 1 and message lifecycle on turn 2;
- no error event; normal close; no early close, handler error, or truncation;
- Codex exit success;
- exactly two finalized reservations and ledger rows; zero pending;
- privacy, replay, route containment, and hosted-tool authority invariants.

If this one run fails, publish its complete bounded snapshot and stop. No
retry, product correction, Local/Qwen change, or new continuation is allowed.

## 9. Verification, privacy, cleanup, and immutable publication

Use only synthetic/disposable data before the protected run. Never retain or
emit prompts, completions, reasoning text, tool names/arguments/results, item/
call/identity values, raw IDs/HMACs/digests, credentials, endpoints, headers,
bodies, SSE, arbitrary errors, or temporary paths. Keep error/event/stage
vocabularies closed and source-reviewed; unknown values become `other`.

Remove every task-created install, worktree, container, database, Redis/server
process, listener, cache, bytecode, artifact, runtime reference, and temporary
file. Leave both product worktrees clean and exact Local head unchanged.

Publish exactly one immutable final report:

```text
oap/reports/155-ak-conformance-repair-and-final-acceptance.md
```

The report must include: `RESULT=PASSED` or `RESULT=FAILED`; exact PR/base/
branch/start/activation/implementation heads; `Report publication commit:
SELF`; machine-generated discrepancy, snapshot/outcome, HMAC, Local-matrix,
0.148 differential, obligation-manifest, test/CI, protected-run-or-not-run,
privacy/accounting, cleanup, and limitation evidence; and exactly one required
documentation line, expected here as
`Documentation checked, no update needed because this objective changes only verifier/tests/OAP evidence and preserves public/product behavior.`

`RESULT=PASSED` requires `missing=[]`, every non-waived gate green, any 0.148
waiver supported by identical baseline failure, all ten checks, and the single
hook-free protected run green. The implementation commit must be pushed before
report drafting. The report must be a final report-only commit whose first
parent is the literal implementation head and whose only changed path is the
report. Never amend it. Wait for all ten report-head checks, verify the remote
PR head, then signal exactly two bytes `OK` once on the response FIFO and
return to exactly one control-FIFO wait.

Do not merge or auto-merge. On PASSED, state only that Objective 155 technical
acceptance is established and exact Gateway/Local heads are ready for
post-acceptance PR decomposition/review and Local OAP-005 resumption. Do not
activate 155-al.
