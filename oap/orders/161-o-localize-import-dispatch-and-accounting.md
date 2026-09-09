# OAP Work Order — 161-o

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 to localize the 161-n `imports/other` failure with
per-import stages, closed exception categories, and a pure accounting-mode
dispatch smoke. Preserve the canonical provider env and accounting-snapshot
control, then run exactly one fresh accounting-before-rejection diagnostic.

Do not change production/docs, accounting expectations, command/catalog/image
behavior, or assistant-history acceptance. If imports pass, the same one run
must expose the safe first-session accounting snapshot and stop before resume.
If an import fails, report its exact closed stage/category. Always publish
FAILED because the resumed target remains unaccepted. No second run.

## Exact current state

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-n implementation head:
  `ce1a0fe19b4a1b97b95a7f39e7f2382b861fddad`.
- Immutable 161-n FAILED report/current PR head:
  `369205e10760515899194765716058b6c8fef155`.
- Report: `oap/reports/161-n-first-session-accounting-snapshot.md`.
- Report commit is report-only with exact implementation first parent;
  implementation includes one verifier/test commit and one order/active commit,
  all within allowed paths.
- All ten implementation checks passed. Require all ten report-head checks
  before signalling this activation. PR #298 is open, non-draft, mergeable,
  unique for Objective 161, without reviews/threads/auto-merge.
- Remote main/release, unrelated PRs #224/#250, historical PR #291, and frozen
  Local PR #7 remain unchanged/out of scope. Local PR #7 stays at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Objective 161 still changes only OAP transcript, one verifier, and unit tests;
  no production/dependency/schema/CI/contract/docs path has changed.

161-n added the accounting diagnostic and one pure test; 110 focused tests and
8 governance tests passed. Its one fresh private module-mode run failed with
`unexpected_imports_other` before Local/observer initialization and before
cleanup, so no scenario or accounting query occurred. Exactly one run occurred
and the corrected 161-l wording was finally recorded.

Source inspection shows `run_prefixed_reproduction()` accepts and forwards the
accounting flag and the body signature accepts it. The body sets only one
`imports` stage around six sequential imports, then advances to
`database_setup`. A primary stage of `imports` with category `other` therefore
means a non-ImportError exception inside that combined region or an equivalent
pre-body dispatch failure. Independent combined import preflight passed, but
it did not prove dispatch through `run_prefixed_reproduction()` with this mode.

Abort on topology/env/source/frozen-Local discrepancy. Never create another PR.

## Exact allowed paths

Only these may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-o-localize-import-dispatch-and-accounting.md`
- `oap/reports/161-o-localize-import-dispatch-and-accounting.md`

Do not change app, fixtures/helpers, Objective-160, Local, production replay/
accounting, DB/schema/migrations, dependencies/lockfiles, CI, contracts,
doctrine, or docs.

## Required diagnostic refinement

1. Extend the closed stage vocabulary with exact stages before each import:
   `import_capture`, `import_responses_helper`, `import_chat_helper`,
   `import_gateway_config`, `import_gateway_app`, and `import_codex_module`.
   Retain existing stages and reject unknown/non-monotonic transitions.
2. Advance immediately before each exact import and advance
   `database_setup` only after all six succeed. Do not reorder imports or
   change imported objects.
3. Extend exception classification only with closed categories needed to
   distinguish safe built-in/runtime families such as attribute, type/value,
   runtime, import, and other. Emit no arbitrary class name/message/MRO,
   traceback, args, path, or repr.
4. Record fixed module-context facts only: `__name__` is main/module/other,
   package present boolean, exact verifier package module present boolean, and
   whether a duplicate verifier module object is loaded. Do not report module
   paths, dictionaries, loaders, specs, or names outside the allowlist.
5. Add a pure dispatch test that monkeypatches the body with a no-side-effect
   stub, invokes `run_prefixed_reproduction(...,
   accounting_before_rejection=True)`, proves the flag reaches the body exactly
   once, and proves no conflict/default-mode change. Add exceptions at each
   import stage and verify fixed output/privacy.
6. Preserve accounting diagnostic behavior exactly: successful imports proceed
   through the full-image first session, one safe snapshot query, and stop
   before resume. Do not alter `_accounting_snapshot_is_two_terminal_successes`
   or apply it in control mode.
7. Preserve canonical env, module-mode invocation, package provenance, command,
   catalog, images, zero retries, Gateway/fake Local, and cleanup.

## Tests and one diagnostic

Starting focused collection is exactly 110. Collect before edits; add and
report exact final collection/execution. Test every import stage/category,
module-context booleans, dispatch forwarding/conflicts, accounting control,
and raw-value exclusion. Preserve all existing tests.

Before the run: complete verifier/governance tests, compilation, Ruff check/
format, focused diagnostic/accounting/privacy tests, `git diff --check`, exact
allowed paths, no report collision, fresh private Python 3.12 `.[dev]` pip/
combined-import/module/provenance/canonical-env gates, and all ten normal
checks on the exact pushed implementation head. Missing/skipped/pending/stale/
failed evidence is not a pass. Repair only before the run.

Run exactly once:

```text
env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
  <task-python> -m scripts.verify_codex_0149_assistant_output_history
  --diagnostic-accounting-before-rejection
```

If imports pass, require Gateway `200,200`, first image `full`, later first-
session images `none`, fake Local two signed requests/one function/one message,
one private session, one bounded accounting snapshot, no resume, and complete
cleanup. If not, report exact closed import stage/category/context/progress.
No second process or post-run mutation.

## Boundaries and report

Routine private Python/npm and disposable PostgreSQL setup are authorized.
Never mutate global state or `DATABASE_URL`. No protected service/credential,
Local mutation, Qwen, real provider, hosted tool, deployment, release, or
production system. PostgreSQL remains accounting truth.

Never retain/report prompts, media, bodies/JSONL, messages, tool payloads,
IDs/HMACs, secrets, DB URLs/rows/amounts, private paths, environment/package
output, tracebacks, arbitrary types/errors, or diagnostic hashes. Docs need no
update because behavior is unchanged.

Commit unchanged 161-o order/active with verifier/tests. After one run publish
only `oap/reports/161-o-localize-import-dispatch-and-accounting.md` with
`RESULT=FAILED`, mechanically verified implementation SHA, `Report publication
commit: SELF`, topology/diff, exact test counts/preflight/checks, one-run closed
import result or every accounting/Gateway/image/Local class, privacy/cleanup/
docs/skips/deviations, and:

```text
PREFX-IMPORT-DISPATCH-ACCEPTED = YES|NO
PREFX-ACCOUNTING-SNAPSHOT-ACCEPTED = YES|NO
PREFX-PROVIDER-ENV-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

Final commit changes only report, has literal implementation first parent, and
is remote PR #298 head before response `OK`. Report-head checks may be pending;
strategic verifies. Coding never merges/auto-merges and returns to permanent
control-wake helper.
