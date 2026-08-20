# OAP Work Order — 015-b

## Objective

Amend PR #240 to close the exact hold-shape, CLI authorization, audit, and
missing-evidence gaps found in independent review of 015-a. Preserve the
no-migration held-fence design and working reconciliation arithmetic, but do
not merge a hold service that can silently repair corrupted held state, list or
retry a mismatched ledger, require audit identity for read-only dry-run, ignore
incompatible action flags, or claim unexecuted overrun/no-charge/restart/CLI
proof.

## Authoritative current state

- Remote `main`: `ef3fdb8ce37381327ebf784b141ab9f7d5f75729`.
- Existing objective PR: #240,
  <https://github.com/ulfe-lmi/slaif-api-gateway/pull/240>.
- Existing branch: `oap/015-external-tool-accounting-hold-reconciliation`.
- Current report head: `ee73dfccb16d08a96c3f1b2ac6af955d23fc2e61`.
- Its first parent/015-a implementation head:
  `ecb0400de0db0e9ef1a19fbf14cfb6c560f1e62b`.
- PR #240 is the only objective-015 PR. Continue it; never create another.
- 015-a correctly adds the basic active→held placement, content-free ledger,
  finalize/no-charge arithmetic, CLI surfaces, inspection metrics/alerts, and
  no-provider boundary without a migration.
- Independent review found:
  - `_validate_reconciliation_input` requires actor/reason even for dry-run,
    contrary to execute-only authorization;
  - release-no-charge accepts and ignores incompatible actual cost/token/
    success fields;
  - reconciliation audit uses a fixed note instead of the operator reason;
  - a held fence with zero ledgers falls through and creates a ledger instead
    of failing invariant;
  - list/retry do not prove held state plus exact ledger key/request/provider/
    endpoint/model, actual-cost-null, empty usage_raw, and canonical metadata;
  - `permit_held=True` fence resolution can accept an unexpected current
    active state instead of requiring held throughout;
  - no hold CLI/config tests were added, and PostgreSQL coverage contains only
    placement, charged failure/idempotency, and one 8-worker finalize race;
  - the report therefore overclaims no-charge, overrun/next rejection,
    rollback/restart/expiry/auth blocking, mismatch negatives, and CLI evidence.
- No schema/migration change is required or allowed.

The 015-a order/report are immutable. Reconcile these facts once and implement
immediately.

## Execution discipline

Do not perform general reconnaissance.

1. First repair `services/external_tool_hold.py` state/authorization checks and
   the audit reason.
2. Add focused unit negatives and run the new hold unit file.
3. Add CLI/config tests and the missing PostgreSQL scenarios.
4. Run the named focused matrix only and publish.

Read another file only for a concrete failing symbol. No migration discovery,
broad search, whole-file formatting, or full local suite.

## Exact hold shape and retry/list behavior

For new placement, require fence state exactly `active` and zero linked
ledgers. For an exact retry, require fence state exactly `held` and exactly one
linked ledger. A held fence with zero or multiple ledgers is an invariant
failure and must never be silently repaired.

Create one reusable exact-held validator for placement retry, listing, dry-run,
and execute. It must require:

- held key fence with exact reservation/request pointer;
- pending `external_tool_fenced` reservation owned by that key with bound
  provider/route facts;
- exactly one ledger linked to reservation and same key/request;
- matching endpoint/provider/requested model;
- accounting status `estimated` or `interrupted`, `success is None`, actual EUR
  and native cost null, and `usage_raw == {}`;
- version-1 hold metadata with state held, needs-reconciliation true, canonical
  reason/evidence enum and parseable held timestamp;
- key reserved counters exactly equal the full reservation.

List only this exact shape. Corrupt/mismatched candidates may be skipped from a
read-only list but must not be projected as valid. Exact placement retry must
also compare streaming, partial total tokens, estimated EUR, reason, evidence,
and every safe ledger fact. Changed facts conflict; malformed shape is an
invariant failure. Preserve explicit zero partial facts in projections instead
of converting zero to absent.

## Reconciliation and authorization rules

- Dry-run validates target/action/proposed numeric evidence and exact held
  shape but does not require actor admin or reason and performs zero mutation.
- Execute alone requires actor UUID and bounded non-empty reason.
- `finalize-actual` requires actual EUR, total tokens, success/failure and
  rejects `confirm_no_charge`.
- `release-no-charge` requires confirmation and rejects any supplied actual
  EUR, total-token, or success/failure field rather than ignoring it.
- Convert hold domain errors into the existing safe reconciliation error
  hierarchy so CLI JSON/text exposes a fixed safe error code/message rather
  than generic `command_failed` or raw exceptions.
- The reconciliation audit must record the sanitized operator reason as its
  audit note and retain actor ID; do not store arbitrary evidence.
- After mutation, clear a held fence only if both the initial and freshly
  locked state are held when `permit_held=True`. The ordinary active-resolution
  path must require active. A state transition between reads fails/no-ops
  without clearing unrelated state.
- Recheck exactly one ledger after acquiring locks before mutation.
- Exact repeated execute remains idempotent; changed repeated inputs conflict.

## Required CLI/config evidence

Add focused Typer tests for:

- help lists both new commands;
- safe text/JSON hold listing and empty state;
- dry-run without actor/reason succeeds and sends `execute=False`;
- execute without actor or reason fails safely;
- finalize and release flag matrices, invalid decimal/UUID/action, no-charge
  confirmation, charged failure, and domain error code;
- no secret/content terms in output.

Use the existing shared decimal parser rather than a function-local Decimal
import so invalid decimals receive the established safe parameter behavior.

Extend configuration tests/docs for both new settings: environment load,
positive hold limit, non-negative alert threshold, and defaults. Preserve the
hard rule that no auto-execute-holds setting/task exists.

## Required PostgreSQL evidence

Add focused tests, using safe disposable PostgreSQL and independent sessions
where needed, for:

1. parameterized placement for every canonical reason; partial estimate gives
   `estimated`, missing facts gives `interrupted`;
2. transaction rollback leaves active/no-ledger/no-hold-audit; committed held
   state survives new engine/session and expiry;
3. held blocks bearer auth and ordinary quota; ordinary/scheduled stale paths
   leave reservation/counters/fence/ledger unchanged;
4. list excludes active-fence ledger and wrong-key/provider/model/contentful/
   actual-cost/malformed metadata shapes;
5. held-without-ledger, multiple ledgers, mismatched reservation/key/fence,
   negative/non-finite evidence, missing execute actor/reason, and incompatible
   action fields fail without mutation;
6. finalize within limits clears and a later normal quota reservation succeeds;
7. finalize above cost and token remainder charges actual, clears only after
   terminal evidence, leaves used counters over limit, and the next ordinary
   quota admission fails;
8. finalized charged provider failure (`success=false`) clears with actual
   charge;
9. explicit no-charge release clears with zero actual and permits later normal
   admission when balance remains;
10. 2-worker and 8-worker exact concurrent execute under bounded timeout yield
    one mutation, N-1 idempotent results, one ledger/reservation/audit, exact
    counters, and no deadlock; a changed concurrent request conflicts.

Do not fabricate provider usage, call a provider, or add runtime forwarding.

## Scheduled inspection, alerts, and documentation

Keep scheduled behavior inspection-only. Add/adjust focused task/alert tests so
only exact held candidates affect counts/IDs/thresholds and no hold mutation
method or auto-execute configuration exists.

Update docs/configuration and the hold runbook with exact new settings, dry-run
authorization, mutually exclusive action flags, audit reason, exact shape, and
the tested overrun/no-charge outcomes. Correct 015-a overclaims only in the new
immutable 015-b report.

## Allowed paths

Only:

```text
.env.example
app/slaif_gateway/cli/quota.py
app/slaif_gateway/config.py
app/slaif_gateway/db/repositories/usage.py
app/slaif_gateway/services/external_tool_fence.py
app/slaif_gateway/services/external_tool_hold.py
docs/accounting.md
docs/configuration.md
docs/runbooks/external-tool-hold-reconciliation.md
docs/security-model.md
oap/active
oap/orders/015-b-close-hold-shape-cli-and-evidence-gaps.md
tests/integration/test_external_tool_fence_postgres.py
tests/integration/test_external_tool_hold_concurrency_postgres.py
tests/integration/test_external_tool_hold_postgres.py
tests/integration/test_reconciliation_tasks_postgres.py
tests/unit/test_cli_quota_reconciliation.py
tests/unit/test_cli_quota_reconciliation_safety.py
tests/unit/test_config.py
tests/unit/test_external_tool_fence.py
tests/unit/test_external_tool_hold.py
tests/unit/test_reconciliation_tasks.py
```

Final report-only commit adds only:

```text
oap/reports/015-b-close-hold-shape-cli-and-evidence-gaps.md
```

Do not change schema/models/migrations, provider/request handlers, dashboard,
dependencies, CI, prior OAP artifacts, or other paths. Report a concrete
outside-path blocker instead of expanding.

## Test economy

Run only the named hold/fence/CLI/config/task unit files and hold/fence/task
PostgreSQL files. Use one explicit disposable `TEST_DATABASE_URL`, no skips.
Run scoped Ruff/format-check/compile, Alembic one-head, diff/path/privacy checks,
then GitHub CI. Do not run full local unit/integration/E2E/browser/Docker/HPC/
manual-Codex/provider suites.

## Acceptance criteria

1. New placement requires active/zero-ledger; retry/list/dry-run/execute require
   one exact content-free held ledger and never repair corruption silently.
2. Dry-run needs no actor/reason and never mutates; execute requires both and
   records the reason in audit.
3. Finalize/no-charge options are strictly mutually exclusive and CLI/domain
   errors are fixed and safe.
4. Held clearing is state-specific and all locked ownership/ledger/counter
   invariants are rechecked.
5. Restart, expiry, auth/quota block, stale/scheduled non-mutation, rollback,
   mismatch, within-limit, overrun/next rejection, charged failure, and
   no-charge paths have real PostgreSQL evidence.
6. 2/8-worker exact concurrency is bounded, deadlock-free, exact-once and
   changed-input fail-closed.
7. CLI/config/task/alert tests and docs match implemented behavior; scheduled
   hold auto-execution remains impossible.
8. No provider/content/secret/Redis-authority/schema/migration expansion.
9. Focused tests and all final report-head checks pass; no broad local suite.
10. Same PR #240 only; no merge/auto-merge; report `SELF` topology exact.

## GitHub and immutable report

Commit the unchanged 015-b order and `oap/active=015-b`, push to the existing
branch/PR #240, inspect CI, and repair only in-scope failures. Never merge.

Publish exactly one immutable report at
`oap/reports/015-b-close-hold-shape-cli-and-evidence-gaps.md` with literal
implementation SHA, `Report publication commit: SELF`, exact shape/CLI/audit/
config evidence, every required PostgreSQL scenario and worker count, commands/
counts/skips/cleanup, scheduled non-mutation, correction of 015-a overclaims,
privacy/no-provider/no-broad-suite/scope/check/no-merge facts. The report-only
commit must parent implementation and change only the report; verify it, signal
exact `OK`, and return to `control.fifo`.
