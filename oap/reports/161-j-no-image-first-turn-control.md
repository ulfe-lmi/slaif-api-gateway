# OAP Coding-Agent Report — 161-j

## Work order

- Identifier: 161-j
- Work-order file: `oap/orders/161-j-no-image-first-turn-control.md`
- Numeric objective: 161
- PR mode: `AMENDED_EXISTING_PR`

## Status

FAILED

## Executive summary

The verifier now supports one explicit diagnostic no-image first-turn mode.
The control argv is derived from the accepted baseline by removing exactly one
`--image` pair; all other arguments, prompt/configuration, workdir, output
binding, executable, and retry settings remain identical. Pure tests cover the
differential and rejection cases, and accounting checks are bounded to count
and pending-state classes.

The one authorized no-image control run executed exactly once from clean
implementation head `c7b50cede420f1d938b29de69e44eb9928641eba` and returned:

```text
VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code=codex_first_turn_turn_failed_exact_other_generic_events_one_gateway_zero_status_none_error_other_param_other_local_zero
```

The control failed before Gateway admission with zero Gateway/Local progress.
The target image reproduction was not run in this round.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 298
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/298
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/161-codex-assistant-output-history`
- Starting remote SHA: `fed0834332ad2aee305617350f73afb8057fc124`
- Implementation head SHA: `c7b50cede420f1d938b29de69e44eb9928641eba`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `c7b50cede420f1d938b29de69e44eb9928641eba`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO

## Changes made

- Added explicit `--diagnostic-no-image-first-turn` CLI mode.
- Derived and validated the exact one-pair no-image argv differential.
- Stopped the control after the first session and required bounded two-request,
  zero-image, fake-Local lifecycle, and accounting predicates.
- Added pure command-differential tests.
- Preserved the strategic 161-j order and `oap/active` bytes unchanged.

## Acceptance-criteria evidence

### Preflight

- Fresh private Python 3.12.3 `.[dev]` environment: PASS.
- `pip check`: PASS.
- Combined imports/module resolution/`--help`: PASS.
- Verifier tests: PASS — 102 tests.
- OAP governance: PASS — 8 tests.
- Compile, Ruff, format, diff: PASS.
- Exact package/native provenance: PASS.
- All ten implementation-head CI checks: PASS.
- Report collision check: PASS.

### One no-image control

- Control count: exactly one.
- Command: `env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app <task-python> -m
  scripts.verify_codex_0149_assistant_output_history
  --diagnostic-no-image-first-turn`.
- Result: FAILED — known `codex_first_turn_turn_failed` projection.
- Turn-failure shape/domain/relation/events: `exact` / `other` / `generic` /
  `one`.
- Gateway request/status/error/parameter classes:
  `zero` / `none` / `other` / `other`.
- Local request count: `zero`.
- Successful two-request lifecycle: NOT ESTABLISHED.
- Zero-image wire predicate: NOT ESTABLISHED.
- Accounting terminal-count/pending-state predicate: NOT ESTABLISHED.
- Target full-image/resumed-crop reproduction: NOT RUN.
- Second control or image run: NOT RUN.

## GitHub CI / required checks

- Check state observed for implementation head `c7b50cede420f1d938b29de69e44eb9928641eba`: all ten required checks SUCCESS.
- `Unit, lint, and migration head`: SUCCESS.
- `Analyze (javascript-typescript)`: SUCCESS.
- `Analyze Python`: SUCCESS.
- `Analyze (python)`: SUCCESS.
- `PostgreSQL integration tests`: SUCCESS.
- `OpenAI-compatible E2E tests`: SUCCESS.
- `Playwright browser smoke`: SUCCESS.
- `Docker Compose smoke`: SUCCESS.
- `Documentation hygiene`: SUCCESS.
- `CodeQL`: SUCCESS.
- All required checks green for the implementation head at report drafting: yes.
- Report-only commit may trigger fresh checks: strategic model must verify the
  SELF commit without rewriting this report.

## Cleanup and safety

- Fresh private task environment removed: true.
- Repository status after cleanup: clean.
- Verifier temporary roots/listeners/disposable state: cleaned by verifier and
  private task-root removal; no repository artifacts remain.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real upstream/provider calls: no.
- Real email: no.
- Prompt, completion, assistant text, reasoning, media, bodies, headers,
  credentials, signatures, endpoints, database URLs, private paths,
  environment values, package output, tracebacks, raw turn-failure text, raw
  IDs, and diagnostic hashes retained in evidence: no.
- Required evidence not established: yes — the no-image control failed before
  Gateway admission; no image run or rerun was authorized.
- No mutation followed the control except this immutable report publication.

## Documentation

Documentation checked, no update needed because this round changes only
verifier-local diagnostic control behavior and makes no compatibility claim.

## Known limitations / blockers

The no-image control reaches the same bounded first-client failure class as the
previous module-mode run, with zero Gateway/Local progress. It does not prove
an image-specific boundary because the no-image session did not reach Gateway.
The underlying foreign operation remains undisclosed by the privacy boundary.

PREFX-NO-IMAGE-CONTROL-ACCEPTED = NO
PREFX-TURN-FAILURE-DIAGNOSTIC-ACCEPTED = YES
PREFX-ENVIRONMENT-ACCEPTED = YES
PREFX-PROVENANCE-ACCEPTED = YES
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
