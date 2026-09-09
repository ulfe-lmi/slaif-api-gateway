# OAP Work Order — 161-g

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Gateway Objective-161 PR #298 with an activation/setup-only round that
runs the accepted 161-f verifier under one private task-local Python 3.12
environment containing the repository's declared development dependencies.
Prove the exact import boundary before execution, preserve every verifier and
production byte, then run exactly one fresh zero-retry pre-fix reproduction.

Do not change verifier tests or production code. If the exact full-image/
resumed-crop assistant-history rejection is established, publish PASSED and
stop for strategic review. If setup, import, or reproduction fails, publish
FAILED with the existing closed 161-f diagnostic and stop. Immutable 161-f
remains FAILED and must not be rerun, amended, or relabeled.

## Exact current state and strategic review

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-g`; amend existing PR #298. Do not create another PR.
- PR/branch: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/298`,
  `oap/161-codex-assistant-output-history`.
- Base and current remote `main`:
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-f starting report head:
  `9fb52d4a045d7374bef003df1b733087db96f032`.
- 161-f implementation head:
  `02184784a5b0b696355b6b5f9557f40e3bbec943`.
- Immutable 161-f FAILED report/current PR head:
  `af9cf789cd9e316090b8b41704cebeeebbb59723`.
- Report path:
  `oap/reports/161-f-localize-unexpected-reproduction-failure.md`.
- The report commit changes only that report and has the implementation head
  as first parent. The implementation commit changed only its order/active
  pointer and the two verifier/test paths.
- All ten normal checks are successful on both the 161-f implementation head
  and current report head. PR #298 is open, non-draft, CLEAN/mergeable, with no
  reviews, review threads, or auto-merge, and is the only Objective-161 PR.
- Remote `main`, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical
  PR #291, and frozen Local PR #7 remain unchanged and out of scope. Local PR
  #7 remains at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Current Objective-161 diff contains only immutable OAP transcript files, the
  verifier, and its unit-test file. No app, dependency declaration, schema,
  migration, CI, contract, accepted fixture, Local, Qwen, or documentation path
  has changed.

161-f added and tested a closed stage/category/progress diagnostic without
changing the scenario. Eighty-one verifier tests, eight governance tests,
focused static checks, package/native provenance, implementation-head CI, and
one zero-retry run completed. The immutable result was:

```text
primary stage = imports
primary category = capture
Gateway request/status/error/parameter = zero/none/none/none
Local request/signed/function/message = zero/zero/zero/zero
observer initialized = false
Local initialized = false
```

The report and coding-session command metadata corroborate exactly one matching
161-f reproduction launch and no second launch. All ten report-head checks are
now successful. The run correctly stopped without production or protected
traffic.

Independent strategic import-only probes under the same bare `python` class
used by the report prove the underlying environment boundary without invoking
the verifier, Codex, Gateway server, database, Local, or provider:

- system interpreter: Python `3.12.3`;
- `scripts.capture_codex_protocol`: imports successfully;
- first subsequent import,
  `tests.e2e.test_openai_python_client_responses`, fails because declared dev
  dependency `respx` is absent;
- the Chat E2E helper has the same absent `respx` dependency;
- Gateway configuration/main/client-module imports additionally lack declared
  runtime packages including `pydantic-settings` and `fastapi` in that bare
  interpreter.

The exact source import order and 161-f closed classification therefore explain
`unexpected_imports_capture`: the reproduction was invoked with a bare system
interpreter instead of the isolated development environment used for tests.
The dependencies already belong to `pyproject.toml` (`.[dev]`); no dependency
or verifier change is required.

Abort and report any discrepancy in PR/base/head/report topology, exact
verifier bytes, dependency declarations, frozen Local authority, or unique
order state. Never create a replacement PR.

## Exact allowed paths

Only these repository paths may change:

- `oap/active`
- `oap/orders/161-g-task-local-dev-interpreter-reproduction.md`
- `oap/reports/161-g-task-local-dev-interpreter-reproduction.md`

Do not change `scripts/`, `tests/`, `app/`, dependency manifests,
requirements, lockfiles, accepted fixtures, Local modules, replay/HMAC,
database/schema/migrations, CI, doctrine, contracts, or documentation.

## Required task-local environment

1. Start from exact PR head `af9cf789...` and preserve a clean tracked tree
   except the unchanged strategic order and active pointer. Create a uniquely
   named private temporary root outside the repository with mode 0700.
2. Use the available Python 3.12 interpreter only to create a private virtual
   environment beneath that root. Require `sys.version_info` major/minor
   exactly `3.12`; do not use the host Codex Python environment, a global
   package mutation, `sudo pip`, Conda, or an inherited virtual environment.
3. Install the current exact checkout non-editably into that environment with
   its declared development extra using the task interpreter's pip equivalent
   to `python -m pip install ".[dev]"`. Do not alter dependency declarations,
   create a repository `.venv`, or retain package-manager output in evidence.
4. Run `pip check` with the task interpreter and require success. Record only
   Python major/minor, task-root/interpreter containment booleans, import
   booleans, and public installed package names/versions needed to explain the
   environment. Never report the temporary path, environment values, caches,
   or arbitrary installer output.
5. From the exact repository root and with `PYTHONPATH=app`, prove all six
   imports independently with the same task interpreter:
   - `scripts.capture_codex_protocol`;
   - `_create_responses_test_data` from the Responses E2E helper;
   - `_run_uvicorn_server` from the Chat E2E helper;
   - `slaif_gateway.config.get_settings`;
   - `slaif_gateway.main.create_app`;
   - Codex-0.149 client-module version and fixture constants.
6. Invoke every Python test, compile check, package preflight, and the one real
   reproduction by the exact absolute task-interpreter path. Do not rely on
   shell activation, bare `python`, `python3`, inherited `VIRTUAL_ENV`, PATH
   precedence, aliases, or subprocess command lookup.
7. The verifier may create its own task-local npm installation and disposable
   PostgreSQL database exactly as already implemented. No package or DB setup
   may escape the two bounded task roots.
8. After the result, remove the task virtual environment, pip/cache/build
   state, generated bytecode, verifier roots, database, listeners, and
   processes. Verify cleanup with only booleans/count classes.

This setup is execution state only. Commit no environment, package artifact,
cache, generated metadata, or interpreter path.

## Required preflight and publication head

Before the one reproduction:

- commit/push only the unchanged 161-g order and `oap/active` as the new
  non-report implementation head on the existing branch;
- require the branch checkout tracked tree clean at that exact head;
- require all ten normal Gateway CI/CodeQL checks successful on that exact
  activation-only implementation head;
- create and verify the private task environment as above;
- run complete `tests/unit/test_codex_0149_assistant_output_history.py` with the
  exact task interpreter and require all 81 retained tests;
- run active OAP governance tests with the same interpreter and require all
  eight tests;
- compile both verifier/test Python paths and run repository Ruff check/format
  checks using tools from that same environment;
- run the exact import matrix, `pip check`, package/native provenance preflight,
  catalog/source/privacy checks, `git diff --check`, exact allowed-path proof,
  and report-collision check;
- prove no tracked or untracked repository artifact exists beyond the allowed
  activation files before the run.

Skipped, xfailed, missing, cancelled, pending, neutral, stale-head, or
environment-blocked required evidence is not a pass. Repair only task-local
environment setup before the real run. Any required repository/source change
is out of scope and must produce FAILED without a reproduction. Once the real
run begins, no environment reinstall, verifier/test/order/product mutation, or
second run is authorized.

## One exact reproduction

After every gate passes, run exactly one fresh zero-retry reproduction using
the exact absolute task interpreter and unchanged verifier:

```text
private task Python 3.12 + current .[dev]
  -> exact accepted 161-f verifier bytes
       -> exact task-local Codex 0.149 launcher/native provenance
            -> exact Local-005-q vision catalog
                 -> unchanged Gateway production behavior
                      -> signed fake Local
                           -> fake provider
```

The report may spell the command only with `<task-python>` in place of the
private absolute path. This is a newly authorized 161-g run, not a rerun of
161-f.

PASSED requires all of:

- task environment/import/provenance gates above;
- exact Gateway statuses `200,200,400` and zero request/stream retries;
- first actual Gateway request has the expected full-image wire class;
- rejected resumed request has the distinct crop-image wire class;
- resumed history contains one prior `assistant` item with exactly one
  `output_text` content part, exact fields `type,text`, and bounded nonempty
  valid-Unicode text, plus exactly one expected crop image;
- exact Gateway rejection `responses_input_content_part_not_supported` at
  `input[5].content[0].type`;
- fake Local exactly two signed requests, one function lifecycle, one message
  lifecycle, and no rejected-turn advance;
- rejected pre-admission request creates no reservation, ledger, replay, or
  other side effect;
- unchanged fixed verifier success line and complete cleanup.

If any predicate fails, publish FAILED with the existing closed 161-f
stage/category/progress snapshot or known `VerificationError` code. Do not run
a second reproduction, alter setup, expose raw diagnostics, or make a
correction after the result.

## Security, privacy, accounting, and external boundaries

Routine network installation into the private task environment, task-local npm
installation, and safe disposable PostgreSQL setup are authorized. Never use
`DATABASE_URL` for destructive setup, mutate global Python/npm state, install
system packages, access production data, or retain the environment.

No production/protected credential, Local PR mutation, Qwen/protected model,
real provider, hosted tool, connector, deployment, cutover, release, or
production system is authorized. Synthetic credentials remain ephemeral.
PostgreSQL remains accounting truth; the expected rejected request remains
pre-admission/no-side-effect.

No prompt, completion, assistant text, reasoning, media, body, stream, tool
argument/result, raw ID, secret, signature, endpoint, DB URL, private path,
environment value, package output, traceback, or arbitrary exception may enter
logs, reports, commits, or durable evidence. Documentation is checked and no
update is needed because this is setup/evidence only and changes no behavior.

## Immutable report and stop law

Preserve all prior orders/reports byte-for-byte. The activation-only commit is
the literal implementation head. After one reproduction, publish exactly one
immutable report and no other mutation:

`oap/reports/161-g-task-local-dev-interpreter-reproduction.md`

The report must contain `RESULT=PASSED|FAILED`, literal implementation SHA,
`Report publication commit: SELF`, topology/diff, task interpreter containment
and import gates, retained package/native provenance, all preflight and
implementation-head checks, exactly-one-run result, every target predicate,
safe stage/category/progress on failure, privacy/accounting/cleanup evidence,
documentation impact, skips/deviations, and:

```text
PREFX-ENVIRONMENT-ACCEPTED = YES|NO
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
helper. Strategic alone decides any next continuation.
