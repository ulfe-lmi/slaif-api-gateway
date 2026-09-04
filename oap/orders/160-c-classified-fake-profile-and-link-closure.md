# OAP Work Order — 160-c

## Objective

Continue Objective 160 on existing PR #297 solely to:

1. correct the permanent evaluator's false-positive doctrine-link checks;
2. surface the compact verifier's already-captured closed Gateway error and
   request-profile classes for the pre-Local failure;
3. run one bounded classified exact-Codex diagnostic; and
4. only if that evidence proves a verifier configuration/profile mismatch,
   correct the verifier and run one final fake two-turn acceptance.

No Gateway product change is authorized. Product `G_clean` remains
`d625af9eb3df45c163342a05e03cda2d3dd0d7c4`, with exact accepted app tree
`bd536a282362cc549cc0c5518db8e743af667b63`.

## Verified starting state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #297, branch `oap/160-idless-tool-replay-clean-stack`, base
  `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`.
- PR mode: `AMEND_EXISTING_PR`.
- Immutable 160-a FAILED report: `e6c7ea11318ad870f2c0aa792b8b360b53591cb7`.
- Immutable 160-b FAILED report/current start:
  `84ee7fe9f6bc7e7dab8948fcdfb530d820af55f6`.
- Current verifier implementation head:
  `82117d2efbda7f1cb9f02ba49d2c0755fbd0b2d7`.
- 160-b fixed the misplaced ASGI observer method and shallow-checkout blob
  anchors. Its unit test and all ten final-head checks are green.
- The decisive 160-b fake returned only
  `gateway_pre_local_rejected`, although `_GatewayObservation` already retains
  allowlisted status/error/request-shape classes.
- The evaluator currently checks four filenames inside `AGENTS.md`; this does
  not prove the three required documentation links and contradicts the report's
  claim.
- PR #291, Local Coding, Qwen, protected systems, product app, and main are
  unchanged.

Do not create another PR, merge, or enable auto-merge.

## Allowed paths

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`
- `oap/active`
- `oap/orders/160-c-classified-fake-profile-and-link-closure.md`
- `oap/reports/160-c-classified-fake-profile-and-link-closure.md`

No other path may change.

## Correct the doctrine-link evaluator

The permanent evaluator must inspect the actual authority/link locations:

- `AGENTS.md` must name root `AGENTIC_CLIENT_INTEGRATION.md` as the detailed
  normative agentic-client authority and retain the concise section;
- `docs/module-architecture.md` must contain a resolving relative link
  `../AGENTIC_CLIENT_INTEGRATION.md`;
- `docs/responses-compatibility.md` must contain that resolving link;
- `docs/compatibility-matrix.md` must contain that resolving link.

Remove the incorrect checks for `docs/provider-forwarding-contract.md` and
`docs/security-model.md` filenames inside `AGENTS.md`. Add mutation tests that
temporarily provide/mimic each missing required authority/link and prove the
evaluator returns that exact fixed missing class. Do not modify the real docs.

The actual evaluator result must remain exactly `missing=[]` on the clean
candidate and must work in a shallow GitHub checkout without relying on an
unavailable ancestor.

## Classified pre-Local diagnostic

Use the existing `_GatewayObservation` fields; do not add raw logging.

When Gateway receives a request but fake Local receives none, emit one closed
failure code composed only from:

- Gateway request count class (`one`, `two`, `other`);
- response status class (`2xx`, `4xx`, `5xx`, `other`);
- exact allowlisted Gateway error code or `other`;
- exact bounded request-profile class already produced by
  `_record_request_shape()`;
- error parameter/type shape from the existing closed projection;
- bounded observer exception class (`none`, `AttributeError`, `ValueError`,
  `TypeError`, `KeyError`, `IndexError`, `other`).

Never include raw values, prompts, descriptions, schemas, IDs, call IDs,
arguments, results, metadata, headers, bodies, credentials, URLs, paths,
digests, or arbitrary exception text. Add unit tests for known and unknown
classes and prove the output stays within a finite allowlist/length bound.

After pure/unit tests pass, run exactly one zero-retry task-local Codex 0.149
diagnostic against real Gateway plus fake Local/disposable PostgreSQL.

## Evidence-driven verifier correction

If and only if the classified diagnostic proves a mismatch in the verifier's
own model catalog, key/route capabilities, fake tool declarations, prompt,
environment, synthetic request profile, or observer/fake-server wiring:

- document the exact closed mismatch;
- correct only the two verifier files;
- preserve exact task-local client behavior rather than hand-writing the
  second request;
- rerun pure/unit preflight; and
- execute exactly one final zero-retry fake two-turn acceptance.

If the diagnostic instead indicates a new Gateway product failure on a
legitimate exact Codex request, or remains `other`/ambiguous, publish FAILED and
stop. Do not change `app/`, Local, Qwen, or policy to make the verifier pass.

## Final fake acceptance

The final run, if authorized by the diagnostic, must emit exactly:

`VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2`

and prove:

- exact task-local `@openai/codex@0.149.0` provenance and zero retries;
- two Gateway requests and two signed fake-Local requests;
- first function lifecycle with non-Codex-prefixed item ID;
- actual client omits the item ID, preserves call ID, executes one approved
  local tool, and sends adjacent matching output;
- Gateway accepts through existing same-key call-ID-HMAC replay with no ID
  fabrication;
- final assistant message completes;
- two finalized reservations/ledgers and zero pending;
- no public bearer forwarding, hosted authority, abnormal close, raw-value
  evidence, or protected/external service.

## Verification

- Run the complete compact-verifier unit file, including observer, link
  mutation, closed diagnostic, manifest, output/privacy, and cleanup tests.
- Run Ruff check, Python compilation, and `git diff --check` on the two files.
- Prove the non-OAP diff from `82117d2...` is exactly the two verifier files.
- Reverify product `G_clean`, exact app tree, six production/five test/five
  fixture blobs, historical machinery absence, and evaluator `missing=[]`.
- Carry forward unchanged 160-a product/replay/PostgreSQL/E2E evidence only
  after verifying its blobs.
- Require all ten GitHub checks successful on the exact final report head.

No required evidence may be skipped, xfailed, pending, cancelled, missing, or
environment-blocked.

## Non-goals

Do not modify product/app, accepted tests/fixtures, docs, doctrine, Local Coding,
Qwen, schema/migrations, PR #291, or main. Do not make protected/provider calls,
fabricate a second request, add Objective-155 diagnostics, begin generic
refactoring, merge, or auto-merge.

## Immutable report

Publish exactly:

`oap/reports/160-c-classified-fake-profile-and-link-closure.md`

It must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact topology and report-only publication facts;
- corrected actual-link evaluator and mutation-test mapping;
- actual `missing=[]` output;
- classified diagnostic result using only closed facts;
- whether verifier correction was authorized and the exact evidence;
- final fake result and all turn/replay/accounting/privacy predicates if run;
- exact unchanged product `G_clean`, app/test/fixture blobs, and historical
  machinery absence;
- focused test/lint/compile/diff and all ten final report-head check states;
- cleanup, documentation impact, and Local OAP-005/release limitations.

The implementation commit may change only the two verifier files. Publish one
report-only commit whose first parent is that implementation head and only
changed path is the report. Verify remote PR head and all claims, write exactly
`OK` to the response FIFO, and return to one blocking control-FIFO read.

Do not contact Local PR #7; strategic performs the handoff after acceptance.
