# Objective 155-ak — conformance repair and final acceptance

RESULT=PASSED

Report publication commit: SELF

## Topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR: `#291`
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting report head: `c2c8f01c25c7f63701b85e8cd4d55e0055931f3b`
- Activation head: `a926e49a1255b33683b1ada10b9abfc6508c347f`
- Frozen production candidate: `e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4`
- Implementation head: `acea2af4ca0f4586fc159c91607e1848f53f1107`
- Local Coding authority: `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`
- Final report path: `oap/reports/155-ak-conformance-repair-and-final-acceptance.md`

The implementation commit changed only the verifier and verifier tests. The
`app/` tree is byte-identical to `e503f964`; Local Coding was unchanged and
clean at its pinned authority head. The report commit is report-only and has
this implementation head as its first parent.

## Discrepancy, snapshot, HMAC, and Local evidence

- The machine-derived 155-aj discrepancy inventory matched its fixed expected
  values: four missing reasoning vocabulary names, eight frozen Local rows,
  two claimed snapshot cases, the recorded HMAC gap, and the bounded baseline
  stage.
- Snapshot predicate coverage executed all 30 required cases and all seven
  closed outcome cases. The collected/executed obligation manifest reported
  `missing=[]`, 80 required nodes, 363 collected nodes, and 80 executed nodes.
- The HMAC rotation, ID-less lookup, ambiguity, version, scope, and privacy
  obligations executed through the allowed replay tests with production replay
  code unchanged.
- The actual Local signed-identity matrix executed 19 rows, including the
  legacy punctuation vectors. Derivation, canonical-body signing, independent
  verification, tamper rejection, replay rejection, and privacy assertions
  passed.

## Exact 0.148 candidate/baseline differential

The task-controlled `@openai/codex@0.148.0` wrapper and hoisted Linux platform
package were overlaid at the exact resolved package paths. In the same
namespace, package metadata, executable provenance, version stdout, exit code,
and empty stderr all matched the 0.148 contract. The host `/usr/bin/codex`
resolved target, digest, and version were unchanged before candidate and after
baseline.

The unchanged candidate test and the unchanged exact PR-base test each
returned `13 passed, 1 failed` with empty stderr. Their bounded result was
identical before candidate-specific behavior, so the Objective-155 baseline
waiver applies. The auxiliary counter also matched at the closed
`second_mocked_request_timeout` stage with request count class `0` and both
request ordinal booleans false; it did not provide candidate-specific traffic
evidence.

## PostgreSQL, fake, and CI gates

- `tests/integration/test_codex_replay_references_postgres.py`: 1 passed,
  zero skipped/xfail/failure/error cases.
- `tests/integration/test_codex_context_accounting_postgres.py`: 1 passed,
  zero skipped/xfail/failure/error cases.
- `tests/integration/test_local_coding_server_module_postgres.py`: 1 passed,
  zero skipped/xfail/failure/error cases.
- The full integration reproduction returned `222 passed, 1 skipped`.
  The sole unrelated skip was
  `tests/integration/test_backup_restore_postgres.py`; `pg_dump` treated the
  SQLAlchemy `postgresql+asyncpg` URL as a database name and used the default
  socket, so the test classified the tool as unavailable/incompatible.
- The final dedicated fake composed stream passed at direct, Local, and
  Gateway boundaries. The tool-roundtrip fake passed; provider-failure and
  validator-failure modes returned their expected sanitized nonzero results;
  the successful qualification fake passed with two turns and two accounting
  rows.
- The corrected Local matrix and focused verifier tests passed (`330 passed`),
  Ruff passed for `app tests`, and all ten checks passed on implementation head
  `acea2af4`.

## Single protected run

After all pre-protected gates were green, the restored owner-only runtime
reference passed its mode/ownership check and authenticated model-health
preflight without exposing values. Exactly one hook-free zero-retry protected
Codex 0.149 process was executed. It passed with two Gateway-to-Local turns,
two Local-to-Qwen inference turns, one function lifecycle on the first turn,
one message lifecycle on the second turn, valid SSE completion/accounting, and
`accounting_rows=2`. No protected retry or direct-provider request occurred.

## Privacy, cleanup, and limitations

No credential, endpoint, request/response body, prompt, completion, tool
argument, raw identity, raw ID, digest, signature, or arbitrary exception text
was retained in the report or evidence. Temporary installs, databases,
PostgreSQL/Redis processes, listeners, bytecode, and task roots were removed;
the restored runtime reference was removed after the protected run. Repository
and Local checkouts were clean after cleanup.

Documentation checked, no update needed because this objective changes only verifier/tests/OAP evidence and preserves public/product behavior.
