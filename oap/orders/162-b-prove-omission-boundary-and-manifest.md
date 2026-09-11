# OAP Work Order — 162-b

PR mode: `AMEND_EXISTING_PR`

## Objective

Close three concrete strategic-review defects in Objective 162's evidence on
the existing PR #299 without changing the accepted production implementation:

1. make the absent-request-fact negative reach and reject the zero-argument
   `output_item.done` boundary after a valid added item;
2. replace the five-boolean self-check with an auditable finite obligation/
   test-node matrix covering the required 162 boundary; and
3. make the handler E2E reproduce vLLM 0.27.1's source-proven
   `response.in_progress` event as part of the exact lifecycle.

This is an evidence-only same-PR correction. Preserve the implementation and
all documented behavior from 162-a byte-for-byte.

## Reconciled state

- Repository `ulfe-lmi/slaif-api-gateway`; PR #299 is the unique Objective-162
  PR, OPEN, non-draft, CLEAN/mergeable, with no reviews/threads/auto-merge.
- Base/current main remains
  `d142fd7f04c46fac3469b9b9bba1bd2068aabad8`.
- Branch: `oap/162-zero-argument-function-stream-closure`.
- Starting immutable 162-a report/current PR head:
  `79fd5aec71aeba9a26b03f390518364164f92ddf`.
- Literal 162-a implementation head:
  `732e3bad17d93909f210321b97bedd8e5718fb7b`.
- Report-only topology is correct; the 162-a order/active bytes match the
  strategic activation; all 22 changed paths are allowed.
- All ten report-head checks are SUCCESS. This is necessary but did not prove
  the report's detailed negative-evidence claim.
- Accepted frozen production app tree:
  `a7b64d35650b61fbba3558ddb519c6e52a627ec9`.
- 162-a's source fixture is canonical at SHA-256
  `4845044674df7f8861626e3fb5c928ba12907e0cef9010964298358f24cec0b8`
  and correctly lists `created -> in_progress -> added -> done -> completed`.
- Local 005-am, vLLM 0.27.1 source pins, module-version-4 decision, exact
  eligibility predicate, empty-string omission rule, canonical-`{}` ordinary
  lifecycle, and no-protected boundary remain accepted and unchanged.

Verify these identities. Do not create another PR, rebase/rewrite published
history, or modify Local/Qwen.

## Exact findings to correct

### Finding 1 — absent-fact test stops at the wrong boundary

`test_codex_0149_zero_argument_fact_is_pair_scoped_and_default_denied`
currently tests profiles that reject `response.output_item.added`: one declares
only `wait`, while the event names `local_lookup`; the other does not enable the
exact function-event branch. It therefore never proves that an otherwise valid
active `local_lookup` item cannot use the omission completion when
`zero_argument_function_names` is empty.

Construct an exact function-event profile with `local_lookup` declared and all
existing pair-local function/reasoning/stream flags enabled, but with an empty
zero-argument set. Require created, in-progress, and added to validate; require
the direct empty-string completed item to fail. Assert no replay candidate and
no valid terminal completion follows. Keep separate default/other-profile and
undeclared-tool denials, but label the boundary each actually tests.

Add the inverse control: the identical event prefix/profile with only
`zero_argument_function_names={"local_lookup"}` accepts item completion and
terminal completion. This must demonstrate that the declarative fact—not an
unrelated declaration or branch failure—is decisive.

### Finding 2 — claimed obligation manifest is incomplete

`test_codex_0149_zero_argument_obligation_manifest_is_complete` currently
constructs five booleans inside one test. It does not enumerate or prove
collection/execution of the positive/negative obligations required by 162-a,
and two of its negative booleans stop at the added event rather than the new
omission boundary.

Replace it with a finite auditable structure:

- define an exact required obligation-ID set for the new boundary;
- drive the new branch-specific cases through a parameterized test/table keyed
  by those IDs, or map an obligation ID to an exact existing test node when the
  pre-existing test directly proves the invariant;
- add a separate completeness assertion that collected case/mapping IDs equal
  the required set exactly—no missing, duplicate, or unknown ID;
- use `pytest --collect-only -q` outside pytest to capture exact relevant node
  IDs, then execute those nodes/files and report collected/executed/passed
  counts. Do not launch pytest recursively from a test.

At minimum, the matrix must account for:

- exact vLLM source sequence and eligible empty-string success;
- decisive fact-absent failure at item completion;
- default/other-pair or profile isolation and undeclared/wrong tool failure;
- schema eligibility: empty properties, optional empty required, strict
  absent/true positives; property, non-empty required, wrong/missing type,
  `additionalProperties` not false, extra schema key, strict false/null,
  custom/non-top-level negatives;
- empty string versus canonical `{}` separation;
- empty delta, arguments-done without delta, and non-empty delta followed by
  omitted arguments-done;
- done-item name/arguments/item ID/call ID/output index/status/namespace/
  caller/extra-field mismatches at the new omission boundary;
- duplicate/reordered/non-monotonic completion, second function item, terminal
  name/arguments/type/usage/duplicate/missing completion, provider failure/
  incomplete, truncation/abnormal-close behavior;
- replay candidate only after valid item completion, persistence only after
  accounting finalization, HMAC-only durable data, zero pending state, and no
  hosted/external-tool accounting facts;
- stale module version 3 no-side-effect denial.

Existing direct generic/function/terminal/E2E/PostgreSQL tests may satisfy an
obligation when the mapping names the exact node and the assertion genuinely
reaches the relevant boundary. Do not duplicate large existing matrices merely
to increase counts. A prose claim, a source grep, or a test that rejects earlier
for an unrelated reason is not proof.

### Finding 3 — handler E2E source sequence omits in-progress

The source fixture and vLLM 0.27.1 `responses_stream_generator` include
`response.in_progress` after `response.created`; the new handler E2E helper
currently emits only `created -> added -> done -> completed`.

Add the exact bounded `response.in_progress` event with the same response ID,
`status="in_progress"`, and strictly increasing sequence. Update expected
client event order and prove the complete handler path still finalizes one
reservation/ledger, persists one replay reference after accounting, leaves zero
pending/reserved state, and has no external-tool facts. Do not broaden the
production validator to require or omit this event globally.

## Acceptance and verification

- Production implementation, module version, source fixture, contracts/docs,
  and behavior remain byte-identical to 162-a implementation head.
- The corrected decisive no-fact test reaches a valid added item and rejects
  only at omitted-event item completion; the fact-present twin succeeds.
- The exact obligation set and case/node mapping close with `missing=[]`, no
  duplicates/unknowns, and each named node is collected and executed.
- The exact source-derived five-event lifecycle is present in both pure and
  real-handler paths.
- Complete affected unit files pass. Complete Responses E2E passes on a fresh
  disposable PostgreSQL database. Run the two 162-a PostgreSQL integration
  files again if referenced by the final obligation map; they must execute, not
  skip. Run governance, pinned Ruff check/format for changed test files,
  compilation, JSON validation, whitespace, and allowed-path checks.
- Normal CI is the full Gateway gate. Require all ten checks SUCCESS on the
  implementation head before a PASSED report; strategic requires all ten again
  on the 162-b report head before merge.
- The known unrelated local full-unit opt-in Codex-version mismatch may be
  carried truthfully from 162-a; do not modify Objective-160/Qwen candidate
  tests or invoke protected tools to make it green. No HPC run is required.

No Qwen/protected inference, real provider, Local mutation, vLLM import, GPU or
model initialization, production system, real email, release, deploy, merge,
or auto-merge is authorized.

## Exact allowed paths

Only these paths may change:

- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/e2e/test_openai_python_client_responses.py`
- `oap/active`
- `oap/orders/162-b-prove-omission-boundary-and-manifest.md`
- `oap/reports/162-b-prove-omission-boundary-and-manifest.md`

The PostgreSQL test files are verification-only and must not change. Every
`app/`, docs/contract, fixture, migration/schema, dependency/lock, config, CI,
server module, verifier, earlier order/report, Local, and Qwen path stays
unchanged. Report:
`Documentation checked, no update needed because 162-b changes only evidence
and preserves the 162-a behavior/contracts.`

## Publication and report

Commit the unchanged 162-b order/active and evidence corrections on the same
PR #299. Never create a second Objective-162 PR. Publish exactly
`oap/reports/162-b-prove-omission-boundary-and-manifest.md` once with
`RESULT=PASSED|FAILED`, literal implementation head, and
`Report publication commit: SELF`. Its commit is report-only with that first
parent and must be verified as remote PR head before response `OK`.

The report must include exact topology/scope/app-tree preservation; each review
finding and corrected boundary; the complete obligation-ID set, mapped test
nodes and `missing=[]`; collected/executed/passed counts; exact E2E chronology;
PostgreSQL/accounting/replay/privacy evidence; commands and actual failures;
all ten implementation-head check conclusions; docs impact; cleanup; and honest
limits.

Required lifecycle labels:

```text
PRODUCTION-UNCHANGED-FROM-162-A = YES|NO
ABSENT-FACT-ITEM-DONE-REJECTED = YES|NO
OBLIGATION-MANIFEST-COMPLETE = YES|NO
VLLM-FIVE-EVENT-HANDLER-E2E = YES|NO
MODEL-FREE-REGRESSION-ACCEPTED = YES|NO
POSTGRESQL-ACCOUNTING-REPLAY-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
LOCAL-HANDBACK-READY = YES|NO
MERGED = NO
RELEASE-READY = NO
```

Strategic independently reviews the final report head and checks before merge.
If accepted and merged, strategic—not Gateway coding—posts the exact merged pin
and final protected-acceptance handback to Local PR #7.
