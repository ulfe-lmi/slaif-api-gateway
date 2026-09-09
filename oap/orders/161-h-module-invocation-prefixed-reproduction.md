# OAP Work Order — 161-h

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 with an activation/setup-only round that
invokes the unchanged accepted verifier as the repository module
`scripts.verify_codex_0149_assistant_output_history` from the exact repository
root. Reuse the accepted private Python 3.12 `.[dev]` environment, prove the
combined import/module boundary, and run exactly one fresh zero-retry pre-fix
reproduction.

Do not change verifier, test, or production bytes. If the exact full-image/
resumed-crop assistant-history rejection is established, publish PASSED and
stop for strategic review. Any setup, import, or reproduction failure is
FAILED with the existing closed diagnostic and stops the round. Immutable
161-g remains FAILED and must not be rerun, amended, or relabeled.

## Exact current state and strategic review

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-h`; amend existing PR #298. Never create another PR.
- PR/branch: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`,
  `oap/161-codex-assistant-output-history`.
- Base and current remote `main`:
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-g starting report head:
  `af9cf789cd9e316090b8b41704cebeeebbb59723`.
- 161-g activation-only implementation head:
  `1504fb5ff3798183b06073eb29d10ad222765fc5`.
- Immutable 161-g FAILED report/current PR head:
  `4f3f76953a9ddbbb7348c06379fd8b1c9303ae34`.
- Report path:
  `oap/reports/161-g-task-local-dev-interpreter-reproduction.md`.
- The implementation commit changed only `oap/active` and the 161-g order.
  The report commit changes only that report and has the implementation head
  as first parent.
- All ten checks are successful on both the activation head and current report
  head. PR #298 is open, non-draft, CLEAN/mergeable, with no reviews, review
  threads, or auto-merge, and remains the only Objective-161 PR.
- Remote `main`, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical
  PR #291, and frozen Local PR #7 remain unchanged and out of scope. Local PR
  #7 remains at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Current Objective-161 diff contains only immutable OAP transcript files, the
  verifier, and its unit-test file. No app, dependency, schema, migration, CI,
  contract, accepted fixture, Local, Qwen, or documentation path has changed.

161-g correctly created a private Python 3.12.3 environment, installed current
`.[dev]`, passed `pip check`, all six independent imports, 81 verifier tests,
8 governance tests, compile/Ruff/format, package/native provenance, and all ten
activation-head checks. Exactly one reproduction used the absolute task
interpreter, `PYTHONPATH=app`, the linked repository as working directory, and
file-mode invocation:

```text
<task-python> scripts/verify_codex_0149_assistant_output_history.py
```

It failed at `imports/capture` with zero Gateway/Local activity. Coding-session
command metadata corroborates exactly one execution command; a later matching
string occurred only inside report publication, not a second execution.

Source and invocation review prove why the independent probes and reproduction
differed:

- `python -c` places the current repository directory on `sys.path`, so
  `from scripts import capture_codex_protocol` succeeds;
- executing `python scripts/verify_codex_0149_assistant_output_history.py`
  sets the script directory as `sys.path[0]`;
- `PYTHONPATH=app` adds the application package but not the repository parent
  needed to import the top-level `scripts` package;
- the first statement inside the instrumented `imports` stage is exactly
  `from scripts import capture_codex_protocol as capture`;
- Python module execution from the exact repository root preserves the package
  parent and is the normal non-mutating fix:
  `<task-python> -m scripts.verify_codex_0149_assistant_output_history`.

This is an invocation-mode defect, not a dependency, verifier, Gateway,
package-provenance, Local, or product defect. Do not add `sys.path` mutation,
weaken imports, duplicate capture code, or edit the verifier.

Abort and report any discrepancy in PR/base/head/report topology, exact
verifier bytes, private-environment prerequisites, frozen Local authority, or
unique-order state. Never create a replacement PR.

## Exact allowed paths

Only these repository paths may change:

- `oap/active`
- `oap/orders/161-h-module-invocation-prefixed-reproduction.md`
- `oap/reports/161-h-module-invocation-prefixed-reproduction.md`

Do not change `scripts/`, `tests/`, `app/`, dependency manifests,
requirements, lockfiles, accepted fixtures, Local modules, replay/HMAC,
database/schema/migrations, CI, doctrine, contracts, or documentation.

## Required task environment and import proof

1. Start from exact PR head `4f3f769...`. Create a new uniquely named private
   0700 temporary root outside the repository and a Python 3.12 virtual
   environment beneath it. Do not reuse the deleted 161-g environment.
2. Install the current exact checkout non-editably with `.[dev]` using the
   absolute task interpreter. Require Python major/minor 3.12 and `pip check`
   success. Do not mutate global packages, use inherited virtualenv state,
   create a repository `.venv`, or change dependency declarations.
3. From the exact repository root with `PYTHONPATH=app`, run one combined
   import-only process in the exact verifier order and require all imports in
   that single interpreter process:
   - `scripts.capture_codex_protocol`;
   - Responses E2E `_create_responses_test_data`;
   - Chat E2E `_run_uvicorn_server`;
   - `slaif_gateway.config.get_settings`;
   - `slaif_gateway.main.create_app`;
   - Codex-0.149 module version/fixture constants.
4. Use `importlib.util.find_spec` or equivalent bounded checks to prove the
   `scripts` package and exact verifier module resolve beneath the current
   reviewed repository root. Retain only equality/containment booleans; never
   print private or repository paths.
5. Run `<task-python> -m scripts.verify_codex_0149_assistant_output_history
   --help` once as a non-reproduction module-resolution/argument-parser gate.
   It must exit successfully without package install, DB, Gateway, Local,
   provider, or scenario activity.
6. Invoke all Python tests and compilation through the exact absolute task
   interpreter. Invoke Ruff from the same task environment. Do not rely on
   shell activation, bare interpreter lookup, aliases, or inherited PATH.
7. The only authorized real reproduction command form is:

   ```text
   env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
     ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
     <task-python> -m scripts.verify_codex_0149_assistant_output_history
   ```

   Run it from the exact repository root. Do not use the file path form,
   `PYTHONPATH=.:app`, `runpy`, a wrapper script, a copied verifier, or an
   editable install as a workaround.
8. After the result, remove the private Python environment, pip/cache/build
   state, verifier/npm roots, disposable DB, listeners, and processes. Verify
   cleanup with booleans/count classes and commit no generated artifact.

## Required preflight and activation head

Before the one reproduction:

- commit/push only the unchanged 161-h order and `oap/active` as the new
  activation-only implementation head on the same PR;
- require the tracked/untracked repository state clean at that exact head;
- require all ten normal Gateway CI/CodeQL checks successful on that exact
  activation head;
- complete the private environment, combined import, module resolution,
  `--help`, and `pip check` gates above;
- run all 81 retained verifier tests and all 8 active governance tests;
- compile the verifier/test paths and run Ruff check/format with task tools;
- run exact package/native provenance, catalog/source/privacy checks,
  `git diff --check`, exact allowed-path proof, and report-collision check;
- prove no repository artifact beyond the activation files was created.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or blocked
required evidence is not a pass. Repair only the private environment before
the real run. Any source/repository change is out of scope and must produce
FAILED without a reproduction. Once the real run begins, no environment
reinstall, source/order mutation, alternate invocation, or second run is
authorized.

## One exact module-mode reproduction

After every gate passes, run the exact module command once with zero request
and stream retries:

```text
private task Python 3.12 + current .[dev]
  -> module-mode accepted 161-f verifier
       -> exact task-local Codex 0.149 launcher/native provenance
            -> exact Local-005-q vision catalog
                 -> unchanged Gateway production behavior
                      -> signed fake Local
                           -> fake provider
```

This is one newly authorized 161-h run, not a rerun of 161-g.

PASSED requires:

- every environment/import/module/provenance gate above;
- Gateway statuses exactly `200,200,400` and zero retries;
- first Gateway request has the expected full-image wire class;
- rejected resumed request has the distinct crop-image wire class;
- resumed history contains one prior `assistant` item with one exact
  `output_text` part, fields exactly `type,text`, bounded nonempty valid-Unicode
  text, and exactly one expected crop image;
- exact Gateway rejection `responses_input_content_part_not_supported` at
  `input[5].content[0].type`;
- fake Local exactly two signed requests, one function lifecycle, one message
  lifecycle, and no rejected-turn advance;
- rejected pre-admission request creates no reservation, ledger, replay, or
  other side effect;
- unchanged fixed success line and complete task cleanup.

If any predicate fails, publish FAILED with the existing closed stage/category/
progress snapshot or known `VerificationError` code. Do not run a second
reproduction, switch back to file mode, add a path workaround, or mutate
anything after the result.

## Security, privacy, accounting, and external boundaries

Routine private Python/npm installation and safe disposable PostgreSQL setup
are authorized. Never mutate global state, use `DATABASE_URL` destructively,
install system packages, access production data, or retain task environments.

No production/protected credential, Local PR mutation, Qwen/protected model,
real provider, hosted tool, connector, deployment, cutover, release, or
production system is authorized. Synthetic credentials remain ephemeral.
PostgreSQL remains accounting truth; the expected rejected request remains
pre-admission/no-side-effect.

No prompt, completion, assistant text, reasoning, media, body, stream, tool
argument/result, raw ID, secret, signature, endpoint, DB URL, private path,
environment value, package output, traceback, or arbitrary exception may enter
logs, reports, commits, or durable evidence. Documentation is checked and no
update is needed because this is invocation/evidence only.

## Immutable report and stop law

Preserve all prior orders/reports byte-for-byte. The activation-only commit is
the literal implementation head. After the one run, publish exactly one
immutable report and no other mutation:

`oap/reports/161-h-module-invocation-prefixed-reproduction.md`

The report must contain `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, exact topology/diff, private interpreter and
combined import/module gates, retained package/native provenance, all preflight
and activation-head checks, exact one-run command/result, every target
predicate, safe failure snapshot if any, privacy/accounting/cleanup evidence,
documentation impact, skips/deviations, and:

```text
PREFX-ENVIRONMENT-ACCEPTED = YES|NO
PREFX-MODULE-INVOCATION-ACCEPTED = YES|NO
PREFX-DIAGNOSTIC-ACCEPTED = YES|NO
PREFX-PROVENANCE-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = YES|NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The report-only commit has the implementation head as first parent, changes
only that report, and is verified as remote PR #298 head before response `OK`.
Report-head checks may be pending then; strategic verifies them independently.
Coding never merges or enables auto-merge. Return to the permanent control-wake
helper. Strategic alone decides the next continuation.
