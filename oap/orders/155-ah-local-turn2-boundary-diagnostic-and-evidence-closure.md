# OAP Work Order — 155-ah

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Starting remote head: 855a89b3c14c54da83798914dbc8ea077b122d07
Frozen production implementation: b171ada9ed3320c57186283ed4ce6ffd4389a7c3
Frozen production tree: c11c45bbc8e8d5d2e251d682ecb2d3a1c13237cb

## Exact authority and objective

The human explicitly authorizes this one exact naming/scope exception,
`155-ah`, on existing PR #291 from immutable 155-ag FAILED report head
`855a89b3c14c54da83798914dbc8ea077b122d07`.

155-ah is diagnostic/test/documentation closure only. It must answer what
happened after real turn 2 was forwarded to Local Coding, close the explicit
HMAC-rotation test gap, correct inaccurate digest-persistence wording, and
execute—not skip—the PostgreSQL replay integration evidence.

This authorization permits no Gateway production-behavior change, Local Coding
change, Qwen change, replay-policy relaxation, SSE normalization/validation
change, fabricated identity, migration/schema/dependency change, retry beyond
the one protected diagnostic below, merge, auto-merge, cutover, release,
`155-ai`, or general multi-letter continuation scheme.

The 155-ag production implementation at
`b171ada9ed3320c57186283ed4ce6ffd4389a7c3` is frozen. Preserve the permanent
155-ae visible-reasoning implementation and 155-af null-encrypted detector
correction. Preserve every prior activated order/report byte-for-byte,
especially the immutable 155-ag report.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, with no auto-merge.
- Remote PR head and the clean task worktree are exactly
  `855a89b3c14c54da83798914dbc8ea077b122d07`.
- That report-only commit changes only
  `oap/reports/155-ag-codex-0149-idless-tool-call-replay-and-final-acceptance.md`;
  its first parent is frozen implementation head
  `b171ada9ed3320c57186283ed4ce6ffd4389a7c3`; RESULT=FAILED.
- All ten checks pass on the immutable 155-ag report head.
- Remote `main` remains `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Local Coding remains read-only and Git-clean at PR #7 report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, implementation parent
  `258ae2ebad39651076937b9f027e60831b8d2786`.
- No 155-ah order/report existed before activation.
- The owner-only mode-0600 runtime reference has exactly the two approved
  endpoint/credential-source keys; the unchanged protected model discovery
  preflight returned 2xx. Never print or retain either value.
- The coding agent consumed no 155-ah signal yet and was blocked on the exact
  control FIFO.
- Governance currently permits through exact `155-ag`. Add only exact
  `155-ah`; keep `155-ai`, arbitrary multi-letter forms, and the next numeric
  objective rejected.

## Accepted interpretation of 155-ag

Do not reduce the protected failure to “ownership unknown.”

Source inspection of
`_run_composed_codex_tool_roundtrip()` proves that fixed failure
`composed_tool_roundtrip_gateway_sse_invalid` is raised only after the
successful-Codex path has completed all of these gates:

1. the real Codex process returned success rather than entering the earlier
   failure-localization path;
2. exactly two Gateway-side and two Gateway-to-Local requests were captured;
3. Local-bound input tool-result counts were exactly `[0, 1]`;
4. Local-bound metadata/privacy checks passed;
5. both Local-bound requests passed service-Bearer, session-header, and
   signature-header structural checks;
6. the plaintext Gateway key was absent from forwarded Local bodies and
   Authorization headers;
7. only then were `local_status`, `gateway_status`, and `qwen_status`
   captured and the Gateway SSE assertion called first.

Therefore 155-ag already establishes:

> Real turn 2 passed Gateway request admission sufficiently to be forwarded to
> Local Coding.

The unresolved boundary begins after that forwarding. It must distinguish
Local turn-2 rejection, Local-to-Qwen invocation/failure, Qwen success plus
Local stream failure, Local/Qwen success plus Gateway stream failure, verifier
expectation error, or complete success. Do not make any product correction from
this uncertainty.

## 1. Failure-preserving bounded diagnostic snapshot

Modify only `scripts/verify_local_coding_full_stack.py` and its tests. Before
calling any Gateway, Local, Qwen, lifecycle, status, or accounting assertion
capable of terminating the successful-Codex path, build one deep-sanitized,
bounded, immutable in-memory snapshot from the already available relay/status
state. A frozen dataclass/tuple or equivalently non-mutable validated structure
is acceptable.

The snapshot must survive a verifier exception and be emitted directly by a
dedicated diagnostic result/exception path as closed JSON. It must not depend
on, enable, read, or write any `SLAIF_155X_*` production qualification hook.
Do not change Gateway/Local/Qwen behavior to collect it.

### Gateway-facing snapshot

Retain only:

- request count class and response count class, bounded to expected 0/1/2/other;
- response status classes and content-type classes;
- SSE-structure count class;
- for each of at most two expected ordinals:
  - structure-present;
  - `invalid`;
  - reviewed valid-completion predicate;
  - closed reviewed event-count/trace classes;
  - exactly-one `response.created`;
  - exactly-one `response.completed`;
  - response-ID relation boolean only, never either ID;
  - created/completed status predicates;
  - model-match predicate;
  - terminal output-shape class;
  - completed-usage-valid;
  - duplicate-event class/boolean;
  - unknown-events class/boolean;
  - error-event;
  - normal-close;
  - downstream-closed-early;
  - handler-error;
  - upstream-truncated.

### Local snapshot

Retain only:

- forwarded-request count class;
- response count/status/content-type classes;
- SSE-structure count and the same closed per-ordinal structural predicates;
- exact allowlisted Local error-code and rejection-stage classes;
- existing closed tool-policy, observation/constitution, and upstream boundary
  states;
- normal-close/downstream-close/handler/truncation booleans.

### Qwen snapshot

Retain only:

- inference-call, successful-call, and compiler-call count classes;
- upstream response status/content-type classes;
- SSE-structure count and the same bounded terminal predicates;
- handler-error, truncation, downstream-close, and path-rejection booleans.

### Accounting and Codex snapshot

Retain only:

- exact task-local Codex provenance class and exit-success class;
- bounded reservation and ledger terminal counts/classes;
- coherent terminal-sequence predicate;
- zero-pending predicate.

Never retain response text, reasoning, prompts, identifiers, call IDs, item IDs,
tool values/names/schemas, arbitrary event fields, credentials, endpoints,
headers, bodies, signatures/digests, canonical bytes, nonce/timestamps, raw
SSE, arbitrary errors/exceptions, or temporary paths.

Validate the emitted snapshot against a closed schema/enum allowlist. Unknown,
oversized, malformed, excessive, or privacy-canary evidence must fail closed
without echoing the value.

## 2. Exact diagnostic failure preservation and tests

Refactor the verifier-only control flow so all boundary/accounting statuses and
the sanitized snapshot are constructed before
`_assert_two_turn_sse_structures()`,
`_assert_function_then_message_structure()`,
`_assert_protected_function_then_message_structure()`, or equivalent
terminating assertions.

If an assertion fails, attach/return only the sanitized snapshot and a fixed
assertion-class code. The normal CLI must print the closed snapshot for the
single protected diagnostic instead of collapsing to
`RESULT=BLOCKED code=composed_tool_roundtrip_gateway_sse_invalid`.

Add pure tests that independently trigger and identify at least:

- missing/non-list/wrong SSE-structure count;
- ordinal 1 absent and ordinal 2 absent;
- `invalid=true`;
- created count zero/duplicate;
- completed count zero/duplicate;
- response-ID relation false;
- created/completed status predicate false;
- model-match false;
- terminal output-shape invalid;
- completed usage invalid;
- duplicate event/trace;
- unknown event;
- error event;
- non-normal close/downstream close;
- handler error and upstream truncation;
- the protected function-then-message lifecycle mismatch;
- Local second-turn 4xx before Qwen;
- Qwen second-turn failure;
- Qwen-valid/Local-invalid;
- Qwen+Local-valid/Gateway-invalid;
- all producer snapshots valid while a legacy verifier predicate would fail;
- complete two-turn success;
- malformed/tampered snapshot, excessive ordinals/events, unknown enum, and
  privacy canaries.

Each failure must preserve the exact safe predicate/class and must not expose
raw values. Keep all existing fake success/failure tests green.

## 3. Closed outcome classification

From the snapshot only, emit exactly one reviewed outcome from a closed set
equivalent to:

- `local_turn2_rejected_before_qwen`;
- `local_invoked_qwen_turn2_qwen_rejected_or_failed`;
- `qwen_turn2_completed_local_stream_invalid`;
- `local_qwen_turn2_completed_gateway_stream_invalid`;
- `producer_boundaries_valid_verifier_expectation_wrong`;
- `full_two_turn_path_succeeded`;
- `other`.

Every non-`other` outcome must be supported by explicit ordinal-2 count,
status, close, and terminal predicates. Do not infer owner from absence alone.
`other` means evidence is incomplete and the report must be FAILED.

If the outcome identifies a Local/Qwen/Gateway product defect, record the
bounded predicates and stop without fixing it. If all producer boundaries are
valid and only the verifier predicate is wrong, record that and stop for human
decision. If the full path succeeds, follow section 7 without claiming merge or
release readiness.

## 4. Explicit HMAC-key rotation tests; no product correction

Add test-only coverage against frozen 155-ag replay behavior proving:

1. a tool-call reference persisted under HMAC version 1 remains verifiable
   after version 2 becomes active while the version-1 secret remains configured;
2. a newly persisted version-2 reference verifies under version 2;
3. present-item-ID and ID-less call-ID lookup obey the same active/retiring
   version rules;
4. removal/unavailability of required old key material fails closed;
5. present wrong item ID plus correct call ID never downgrades;
6. duplicate/ambiguous matches across versions fail closed;
7. raw item ID, call ID, HMAC digest, and privacy canaries never appear in
   errors, logs, captured output, or reportable evidence.

Exercise both function and the already-supported custom tool shape where
applicable. Preserve item-ID uniqueness, call-ID uniqueness/index behavior,
same-key/expiry/tool/route/provider/model checks, and the
`_MAX_ACTIVE_HMAC_VERSIONS` bound.

If any test exposes a production correctness issue, do not edit production
code. Publish RESULT=FAILED with the safe failing invariant and request
strategic review.

## 5. Correct digest-persistence documentation

Correct all equivalent inaccurate wording introduced or retained in the three
155-ag-edited documents:

- `docs/accounting.md`;
- `docs/responses-compatibility.md`;
- `docs/compatibility-matrix.md`.

The truthful contract is:

- raw item IDs and raw call IDs are not persisted;
- versioned HMAC digests of replay identifiers are persisted in
  `codex_replay_references` as private replay-control metadata;
- those digests are not billing truth and must never appear in logs, metrics,
  audits, exports, reports, or OAP evidence;
- provider content, reasoning, tool values, raw identifiers, and credentials
  remain excluded.

Do not hide or euphemize the persisted HMAC digest. Keep implemented versus
qualified/accepted status honest because the protected path is not yet
accepted.

## 6. Execute PostgreSQL and complete test evidence

Provision the repository-standard disposable PostgreSQL 16 test environment
with a unique task-owned container/database and a safe test-only URL. Do not
reuse, drop, reset, or mutate any existing database/container. Ensure cleanup
is exact and recoverable.

Run, without skip:

    tests/integration/test_codex_replay_references_postgres.py

Also run the relevant context-accounting integration coverage and assert the
selected replay test executed (not merely collected/skipped). Record pass/test
counts only.

Run the relevant complete unit/integration suites in an isolated environment
where each Codex-dependent test receives its pinned/task-controlled executable.
For the pre-existing Qwen text candidate that hardcodes
`/usr/bin/codex`, use a disposable container or mount namespace containing
the exact required Codex 0.148 binary; never change host `/usr/bin/codex` and
do not modify/skip/xpass that unrelated test. The 155-ah verifier itself must
continue to prove exact task-local Codex 0.149.0.

Run Ruff/format/compile/diff/privacy/source/scope checks. Require all ten PR
checks green on the exact diagnostic implementation head before protected
traffic. Skipped, pending, missing, neutral, or cancelled required checks are
not passes.

## 7. Frozen-product proof and one protected diagnostic

Before protected traffic, prove:

- no path under `app/`, `migrations/`, dependency/lock files, Local Coding,
  or Qwen differs from frozen implementation
  `b171ada9ed3320c57186283ed4ce6ffd4389a7c3`;
- changes since that head are limited to this OAP activation, verifier tests,
  HMAC tests, documentation, governance, and the eventual report;
- no production diagnostic hook was added or enabled;
- Local is exactly `4d3ab2f...` and clean;
- the Codex executable/package/catalog provenance is exactly 0.149.0;
- the protected Qwen/model/route/tools/workload are unchanged;
- the implementation head is clean, remote-matched, and has all ten checks
  successful.

Then run exactly one zero-retry protected diagnostic:

real task-local Codex 0.149.0 -> frozen Gateway product -> unchanged Local
Coding -> unchanged protected Qwen.

Its sole purpose is to answer what happened after real turn 2 was forwarded to
Local. Publish the closed outcome and the complete bounded predicates that
support it.

Do not run a second protected request, alternate prompt/route/model/tool
profile, direct-provider request, or retry. Do not repair a discovered boundary
in 155-ah.

## 8. Unexpected complete success

If the single protected diagnostic reports
`full_two_turn_path_succeeded` with two coherent terminal accounting rows and
zero pending:

- confirm no temporary diagnostic-only production hook exists or participated;
- retain only verifier/test/docs changes;
- do not run a second protected “final” because this authorization permits only
  one protected process;
- do not claim Objective 155, release, cutover, or merge acceptance;
- stop for an explicit human decision on final acceptance and accumulated
  Objective-155 cleanup/review.

If production-hook removal would be required, that is a forbidden production
change: record it and stop. Do not remove it here.

## Privacy, cleanup, and allowed paths

At closure remove the runtime reference and every exact 155-ah task root,
temporary Codex install, namespace/container/database, diagnostic artifact,
process, listener, bytecode tree, and file. Preserve protected Qwen and all
unrelated state. Leave both Gateway and Local worktrees clean.

Allowed paths:

    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_codex_replay_service.py
    tests/integration/test_codex_replay_references_postgres.py
    tests/integration/test_codex_context_accounting_postgres.py
    tests/unit/test_oap_governance.py
    docs/accounting.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    oap/active
    oap/orders/155-ah-local-turn2-boundary-diagnostic-and-evidence-closure.md
    oap/reports/155-ah-local-turn2-boundary-diagnostic-and-evidence-closure.md

Do not modify `tests/unit/test_qwen38_text_codex_candidate.py`; fix its
execution environment only. No `app/`, migration, model/schema, dependency,
lockfile, server registry/pair, Local/Qwen/Codex source, prior order/report,
AGENTS/OAP protocol, release, or unrelated file change is authorized.

## Result, immutable report, and response

Before creating the report, prove no `oap/reports/155-ah-*` exists. Publish
exactly one immutable report-only SELF commit whose first parent is the
terminal verifier/test/docs implementation head and whose only changed path is:

    oap/reports/155-ah-local-turn2-boundary-diagnostic-and-evidence-closure.md

Never amend or replace it. RESULT=PASSED means only that the diagnostic,
rotation-test, documentation, PostgreSQL, privacy, cleanup, and evidence
objective was conclusively completed. It does not mean Objective 155 or PR #291
is accepted or mergeable. RESULT=FAILED is required for incomplete/`other`
classification, privacy/schema failure, exposed production defect in HMAC
rotation, missing execution, or any scope violation.

The report must state explicitly that turn 2 was already proven forwarded to
Local; record the one closed post-forwarding outcome and supporting safe
ordinal predicates; record exact PostgreSQL execution, Codex provenance,
rotation results, frozen-product diff proof, docs correction, all checks,
cleanup, and topology. Never retain prohibited raw data.

Do not merge, auto-merge, activate 155-ai, or infer later work. Require all ten
checks green on the immutable report head, send exactly two response FIFO bytes
`OK` once, return to one blocking control-FIFO read, and stop.
