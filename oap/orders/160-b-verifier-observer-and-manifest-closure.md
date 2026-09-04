# OAP Work Order — 160-b

## Objective

Continue Objective 160 on existing PR #297 solely to correct the compact
verifier's misplaced request-shape observer method, turn its static obligation
labels into a real machine evaluation returning `missing=[]`, and execute one
decisive exact-Codex fake two-turn acceptance run.

The Gateway product implementation is frozen at
`d625af9eb3df45c163342a05e03cda2d3dd0d7c4`. Its `app/` tree already equals
accepted Objective-155 tree `bd536a282362cc549cc0c5518db8e743af667b63`.
No product, replay, test-blob, fixture, documentation, Local, or Qwen change is
authorized.

## Verified state and diagnosis

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #297, branch `oap/160-idless-tool-replay-clean-stack`, base
  `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`.
- PR mode: `AMEND_EXISTING_PR`.
- 160-a clean implementation head:
  `d625af9eb3df45c163342a05e03cda2d3dd0d7c4`.
- Immutable 160-a FAILED report/current starting head:
  `e6c7ea11318ad870f2c0aa792b8b360b53591cb7`.
- All six production/five permanent test/five fixture targets, full app-tree
  equivalence, focused tests, PostgreSQL, E2E, lint/compile, historical-
  machinery absence, and ten report-head checks are already green.
- The 160-a compact verifier failed with safe class
  `gateway_pre_local_rejected` before fake Local.
- Source proves `_GatewayObservation.__call__()` invokes
  `self._record_request_shape(...)`, but `_record_request_shape()` is
  accidentally indented/owned by `_GatewayExceptionObservation`.
  `_GatewayObservation` therefore raises `AttributeError` in its wrapper before
  the real Gateway app receives the request. This is verifier-owned, not a
  Gateway product rejection.
- The current obligation test checks only that static labels are nonempty; it
  does not mechanically compute missing obligations.
- PR #291, Local Coding, Qwen, protected systems, and main are unchanged.

Do not create another PR, merge, or enable auto-merge.

## Allowed paths

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`
- `oap/active`
- `oap/orders/160-b-verifier-observer-and-manifest-closure.md`
- `oap/reports/160-b-verifier-observer-and-manifest-closure.md`

No other path may change.

## Required verifier correction

1. Move `_record_request_shape()` to `_GatewayObservation`, where
   `observed_receive()` calls it.
2. `_GatewayExceptionObservation` must retain only its bounded exception-class
   responsibility and must not own request parsing/projection.
3. Preserve the existing bounded request projection: retain only request
   ordinal/profile/type/field-name/type-class/cardinality booleans needed by
   the verifier. Never retain values, prompts, descriptions, schemas,
   arguments, results, IDs, call IDs, metadata values, bodies, headers,
   credentials, endpoints, paths, or arbitrary exception text.
4. Add a pure regression proving a synthetic ASGI Responses request passes
   through `_GatewayObservation` to a dummy app, records one bounded shape, and
   raises no observer exception.
5. Add an ownership/source regression proving `_GatewayObservation` owns the
   method and `_GatewayExceptionObservation` does not.
6. On a future non-2xx Gateway response, prefer an allowlisted fixed
   `gateway_<error-code>_<safe-shape>` failure class over the coarse generic
   boundary code. Unknown values remain `other`; never expose raw error text.

Do not weaken the fake Local, signed-header/body checks, exact client
provenance, zero-retry settings, accounting predicates, or cleanup.

## Real obligation manifest

Replace the static-only assertion with a callable permanent evaluation, for
example `evaluate_obligations() -> list[str]`, which returns only missing fixed
obligation names.

It must mechanically verify at least:

- `HEAD:app` tree equals
  `bd536a282362cc549cc0c5518db8e743af667b63`;
- the six accepted production blobs;
- the five accepted replay/client/stream test blobs;
- the five permanent fixture blobs;
- required replay/no-downgrade/rotation, identity, stream, accounting, privacy,
  and compact-verifier test paths exist;
- historical `scripts/verify_local_coding_full_stack.py` and
  `tests/unit/test_local_coding_full_stack_verifier.py` are absent;
- no `SLAIF_155X_` occurs under `app/`;
- `tests/unit/test_oap_governance.py` and
  `AGENTIC_CLIENT_INTEGRATION.md` retain their merged pre-160 content;
- all four permanent doctrine links remain.

The unit test must assert the actual result is exactly `[]` and expose the
fixed human-readable state `missing=[]`. A static mapping of nonempty strings
alone is not sufficient. Do not make the evaluator depend on GitHub, PR/OAP
reports, protected resources, mutable branch names, or external services.

## Decisive fake two-turn run

After pure/unit preflight is green, run exactly one decisive zero-retry:

`task-local @openai/codex@0.149.0 -> real Gateway d625af9 app semantics -> fake Local`

using numeric loopback and disposable PostgreSQL only.

Acceptance requires:

- exact package/executable/version provenance;
- two Gateway requests;
- two signed fake-Local requests;
- first valid function lifecycle with deliberately non-Codex-prefixed item ID;
- actual client naturally omits that item ID, preserves the call ID, executes
  one approved local tool, and sends adjacent matching output;
- Gateway authenticates the continuation through same-key call-ID HMAC without
  fabricating an item ID;
- final assistant-message lifecycle succeeds;
- two finalized reservations and ledgers, zero pending;
- no public bearer forwarding, hosted authority, raw-value retention, retry,
  or abnormal close;
- exact one-line success output
  `VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2`.

If the observer fix reveals another failure, publish its allowlisted safe code
and stop. Do not change product behavior or make another product correction in
160-b. Development pure/unit tests may be repeated; do not retry the decisive
post-preflight client process.

## Verification

- Run complete `tests/unit/test_codex_0149_local_roundtrip.py`.
- Run repository Ruff check and Python compilation for the two allowed Python
  files.
- Run `git diff --check`.
- Prove the non-OAP diff from `d625af9...` is exactly the two allowed verifier
  files.
- Reverify `app/` tree/hash/diff, all production/test/fixture blobs, and
  `missing=[]` with the permanent evaluator.
- Carry forward the immutable 160-a replay/PostgreSQL/E2E/security/accounting
  evidence only after verifying all referenced files are unchanged.
- Require all ten GitHub checks successful on the exact final report head.

No required evidence may be skipped, xfailed, pending, cancelled, missing, or
environment-blocked.

## Non-goals

Do not modify app/product behavior, accepted permanent test blobs, fixtures,
docs, doctrine, Local Coding, Qwen, schema/migrations, PR #291, or main. Do not
make protected/provider calls, add Objective-155 diagnostics, begin generic
refactoring, merge, or auto-merge.

## Immutable report

Publish exactly:

`oap/reports/160-b-verifier-observer-and-manifest-closure.md`

It must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact PR/base/branch/starting/implementation/report heads;
- `Report publication commit: SELF` and report-only topology;
- exact two-file implementation diff and observer ownership correction;
- permanent evaluator output `missing=[]` and mapped checks;
- unchanged `G_clean=d625af9...`, app tree, production/test/fixture blobs;
- unit/lint/compile/diff results;
- exact decisive Codex provenance, one-line result, turn/signature/ID/call/
  accounting/privacy/cleanup predicates;
- carried-forward 160-a evidence and all ten final report-head check states;
- documentation impact statement and honest Local OAP-005/release limitations.

The 160-b implementation commit may change only the two verifier files. Then
publish a report-only commit whose first parent is that implementation commit
and whose only changed path is the report. The report must continue to identify
`d625af9...` as the exact product `G_clean`, while also naming the verifier
implementation head separately.

Verify remote PR head and all claims, write exactly `OK` to the response FIFO,
and return to one blocking control-FIFO read. Do not contact Local PR #7; the
strategic model performs the final handoff after acceptance/merge.
