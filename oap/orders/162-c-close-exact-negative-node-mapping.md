# OAP Work Order — 162-c

PR mode: `AMEND_EXISTING_PR`

## Objective

Close the last Objective-162 evidence defect on existing PR #299: replace
broad obligation labels mapped to one generic parameter case with stable,
explicit, one-to-one test nodes that exercise the exact zero-argument omission
branch. Production, docs, fixture, handler E2E, PostgreSQL behavior, and all
accepted 162-a/162-b evidence remain frozen.

This is a finite test-evidence correction, not another compatibility discovery
or diagnostic round.

## Reconciled state

- Repository `ulfe-lmi/slaif-api-gateway`; PR #299 is the unique Objective-162
  PR, OPEN/non-draft/mergeable; branch
  `oap/162-zero-argument-function-stream-closure`; base/main
  `d142fd7f04c46fac3469b9b9bba1bd2068aabad8`.
- Starting immutable 162-b report/current PR head:
  `f8a6315c572313cfb7f4e3eacb0068a9749b705e`.
- 162-b implementation parent:
  `ba425911d0a3da99d6ee9e514f069bd693a36704`.
- 162-b SELF topology and exact order/active bytes verified. Its implementation
  changed only two tests plus orchestration; production app tree remains
  `a7b64d35650b61fbba3558ddb519c6e52a627ec9`.
- The decisive fact-absent/fact-present test and source-exact five-event
  handler E2E are accepted. Do not rewrite them except where the exact manifest
  mapping needs a stable node name.
- All 162-a production behavior/contracts/source pins remain accepted. No
  protected or real-provider reproduction is needed or authorized.

## Exact review finding

The 162-b manifest has an independent literal 25-ID set and valid collected
node strings, but several mappings are not semantically exact. For example:

- `boundary.item_done_identity_status_namespace_caller_extra` maps only to
  `test_codex_0149_function_item_shapes_are_event_specific[<lambda>0]`, which
  exercises one caller mutation on the ordinary delta/done lifecycle;
- `boundary.item_done_fields_and_coordinates` likewise maps one lambda case;
- grouped terminal/provider/close labels map one parameter case while claiming
  multiple states.

The overall suite contains many shared strict controls, but a manifest cannot
claim one node proves unexecuted siblings or a different lifecycle boundary.
Correct the mapping and add only the missing exact omission-branch cases.

## Required correction

### 1. Stable exact omission-item mutation matrix

Add one parameterized test with explicit stable `pytest.param(..., id="...")`
IDs. Every case must:

1. build the exact zero-argument source lifecycle and exact eligible profile;
2. validate created, in-progress, and added successfully;
3. mutate only the direct `response.output_item.done` event;
4. reject at that item completion;
5. expose no replay candidate; and
6. leave terminal completion invalid while the item remains active.

Cover separately, with one stable node per fact:

- missing and mismatched item ID;
- missing and mismatched call ID;
- missing and mismatched output index;
- wrong/missing completed status;
- wrong namespace and non-null caller;
- wrong name and non-empty/canonical-`{}` arguments;
- extra event field and extra item field;
- missing required event/item field; and
- duplicate/non-monotonic sequence coordinate.

Do not use anonymous `<lambda>N` node IDs in the manifest. Mutation helpers may
be small named functions or `pytest.param` values, but the collected IDs must
be stable and descriptive.

### 2. Exact post-completion and terminal matrix

Add or map stable exact nodes proving, on the omission lifecycle itself:

- after a valid omitted-event item completion, duplicate item completion,
  argument delta, arguments-done, and a second function item are rejected;
- terminal function name, empty-string arguments, item type, status, and valid
  detailed usage are required;
- missing/invalid usage, mismatched terminal name/arguments/type/status,
  duplicate terminal completion, and terminal completion before item completion
  are rejected.

It is valid that a transient replay candidate exists after a valid item-done
event even if terminal completion later fails; the Gateway persists it only
after successful final accounting. State this accurately and rely on the
accepted handler/PostgreSQL evidence for durable post-accounting behavior.

Provider failure/incomplete, truncation/disconnect/abnormal close, stale module
metadata, schema eligibility, default/other-pair isolation, HMAC-only durable
state, zero pending accounting, and no external-tool facts may remain mapped to
existing tests only when each mapping names either the complete non-parameterized
test or every exact parameterized node needed for the label. Split a broad
obligation into precise IDs instead of making one node stand for several cases.

### 3. Honest machine mapping

- Keep a literal required obligation-ID set independent of the mapping.
- Require exact set equality, no duplicate/missing/unknown IDs, and safe test
  path prefixes.
- Use one obligation per precise fact or make the mapping value an explicit
  tuple of all exact node IDs needed for a genuinely grouped obligation.
- Outside pytest, collect the affected unit/integration/E2E files verbosely;
  mechanically prove every mapped node string is present in collection. Then
  execute the mapped files/nodes. Report required IDs, mapped node references,
  distinct collected nodes, missing mappings, missing collected nodes, and
  executed/passed counts.
- Do not implement a self-derived required set, invoke pytest recursively from
  tests, or use source greps/prose as execution proof.

## Acceptance and verification

- Only the strict stream unit file plus 162-c orchestration/report changes.
- App/docs/fixture/E2E/PostgreSQL test trees remain byte-identical to 162-b.
- The new exact omission mutation/post-completion/terminal matrices pass and
  their stable nodes are present in the complete affected collection.
- The independently literal obligation set maps exactly to collected, executed
  nodes with `missing=[]`, no unknown/duplicate IDs, and no broad one-case
  overclaim.
- Run both complete affected unit files (client module plus strict stream), the
  unchanged five-event Responses E2E file on a fresh disposable PostgreSQL
  database, and the two unchanged PostgreSQL integration files if the manifest
  continues to cite them. Run governance, pinned Ruff check/format on changed
  test code, compilation, JSON validation, whitespace, and exact path/tree
  preservation checks.
- Require all ten normal GitHub checks SUCCESS on the c implementation head
  before PASSED report; strategic requires all ten on c report head before
  merge. The known unrelated local opt-in Codex-version mismatch remains
  outside scope; no HPC or protected execution.

## Exact allowed paths

Only these paths may change:

- `tests/unit/test_responses_codex_streaming_tools.py`
- `oap/active`
- `oap/orders/162-c-close-exact-negative-node-mapping.md`
- `oap/reports/162-c-close-exact-negative-node-mapping.md`

Every `app/`, docs/contract, source fixture, E2E, integration/PostgreSQL test,
dependency/lock, schema/migration, config, CI, verifier, Local, Qwen, and older
order/report path stays unchanged. Documentation impact must say no update is
needed because c only tightens evidence for unchanged 162-a behavior.

No production/protected/real-provider/Local/Qwen/service/GPU/model/credential/
network mutation, release, deploy, merge by coding, or auto-merge.

## Publication and immutable report

Commit unchanged c order/active and the one test-file correction on the same
PR #299. Publish exactly
`oap/reports/162-c-close-exact-negative-node-mapping.md` once with literal
implementation head and `Report publication commit: SELF`; the final commit is
report-only and must be remote PR head before response `OK`.

Report exact topology/scope/tree preservation; every new stable node; complete
obligation-to-node mapping counts and `missing=[]`; collected/executed/passed
counts; test/CI conclusions; accurate replay/accounting semantics; docs impact;
cleanup; and limits.

Required labels:

```text
PRODUCTION-UNCHANGED-FROM-162-A = YES|NO
EXACT-OMISSION-NEGATIVE-MATRIX = YES|NO
EXACT-TERMINAL-NEGATIVE-MATRIX = YES|NO
OBLIGATION-NODES-COLLECTED-AND-EXECUTED = YES|NO
MODEL-FREE-REGRESSION-ACCEPTED = YES|NO
POSTGRESQL-ACCOUNTING-REPLAY-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
LOCAL-HANDBACK-READY = YES|NO
MERGED = NO
RELEASE-READY = NO
```

Strategic reviews the final c report/checks and merges only if this finite gate
is satisfied. No further diagnostic framework or protected Gateway round is
authorized.
