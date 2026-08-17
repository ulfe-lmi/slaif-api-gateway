# OAP Coding-Agent Report — 001-a

## Work order

- Identifier: 001-a
- Work-order file: `oap/orders/001-a-verify-post-220-baseline-release-evidence.md`
- Numeric objective: 001
- PR mode: CREATED_NEW_PR
- Active-pointer SHA-256:
  `1615a1a18dcf328b6d268c2dc0d9dabaa16493412b8b57bf9d03de6901422099`
- Active-order SHA-256:
  `a25f510202761dac52495adf68e6aaff766d121766820b332bc47a1671a3117c`

## Status

FAILED

## Executive summary

Created the required non-draft objective-001 PR from merged objective-000
`main`, versioned the strategic transcript unchanged, and ran the full harness
exactly once at the host's actual 24-worker capacity. The objective result is
`RESULT=FAIL`: 2,533 of 2,534 tests passed, with one OAP governance unit test
failing because the immutable `001-a` order does not contain a literal phrase
the existing test requires for every initial round. Integration 130/130, E2E
43/43, browser 2/2, all validation phases, Redis-backed coverage, PostgreSQL
isolation, and Docker Compose config passed. No fix or full rerun was attempted.

Published durable evidence and minimal readiness/release links that state the
failure plainly. The post-PR-220 128-worker HPC qualification remains NOT RUN;
this result is not production certification, an RC2 release decision, or a
real-provider result. PR #226 remains open and unmerged for strategic review.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 226
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/226
- PR state at report time: OPEN, non-draft
- Base branch: `main`
- Head branch: `oap/001-current-main-baseline-verification`
- Required title: `[OAP 001] Verify current gateway baseline`
- Starting remote/main SHA: `f137d0467cbc6fb2a61ce99494ea724a173cd633`
- Transcript commit: `0f09de476f643e5879baeaf08eeb1d7393529758`
- Exact harness-tested commit: `0f09de476f643e5879baeaf08eeb1d7393529758`
- Implementation head SHA: `a4a44e88da907a66d9bb21878dd330279a1201b0`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `0f09de476f643e5879baeaf08eeb1d7393529758`
    (`Activate OAP 001 baseline verification`)
  - `a4a44e88da907a66d9bb21878dd330279a1201b0`
    (`Document failed 24-worker baseline verification`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes, exactly one
- Amended an existing PR this turn: no
- Objective-result comment:
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/226#issuecomment-5319685536
- Other open PRs: unrelated Dependabot PR #224 only
- Merge performed: NO
- Auto-merge enabled: NO

## Baseline reconciliation

- Local `main` and `origin/main` both resolved to the required starting SHA
  `f137d0467cbc6fb2a61ce99494ea724a173cd633` before branching.
- Objective-000 PR #225 was independently verified merged at that starting SHA.
- Its final report head `038ac2942f5f30d57b0e95c9398b592444de94a9`
  is an ancestor of remote `main`, and all ten final-head checks passed.
- The only GitHub release remained `v0.1.0-rc.1`; no RC2 release/tag exists.
- The required objective-001 local/remote branch, PR, and report did not exist
  before activation.
- The only uncommitted pre-branch paths were the strategic-authored `oap/active`
  pointer and uniquely selected 001-a order.

## Changes made

- Committed the exact strategic-authored `oap/active=001-a` pointer and order
  before verification.
- Created the required branch and non-draft PR #226 before the long run.
- Ran exactly one 24-worker full current-machine matrix.
- Added a durable commit/environment-specific failed verification record and a
  short verification index.
- Added minimal links/classification to RC-beta and release-index documentation.
- Added a post-adoption evidence note to `AGENTS.md` without replacing or
  rewriting the original adoption baseline.
- Added the exact one-run result summary to PR #226.

## Files changed

Transcript commit:

- `oap/active` (strategic-authored bytes committed unchanged)
- `oap/orders/001-a-verify-post-220-baseline-release-evidence.md`
  (strategic-authored bytes committed unchanged)

Evidence implementation commit:

- `AGENTS.md`
- `docs/rc-beta.md`
- `docs/releases/README.md`
- `docs/verification/README.md`
- `docs/verification/2026-08-17-current-main-baseline.md`

Report-publication commit:

- `oap/reports/001-a-verify-post-220-baseline-release-evidence.md`

No application, existing test, migration, dependency, CI workflow, script,
deployment, provider-catalog, or prior OAP artifact changed.

## Acceptance-criteria evidence

### Criterion 1 — One non-draft objective-001 PR

- Result: PASSED
- Evidence: PR #226 is the sole PR on the required branch, is open/non-draft,
  targets `main`, has the exact title, and starts from merged objective-000
  `main`.

### Criterion 2 — Transcript versioned unchanged before verification

- Result: PASSED
- Evidence: transcript commit `0f09de476f643e5879baeaf08eeb1d7393529758`
  has starting `main` as its parent and changes only `oap/active` and the 001-a
  order. Both strategic-authored hashes remained unchanged.

### Criterion 3 — Exactly one 24-worker full harness run

- Result: PASSED for execution; gate result FAILED
- Evidence: the wrapper ran once with argument 24 and exited 1 after emitting
  one complete summary. It was not rerun after the unit failure.

### Criterion 4 — No redundant broad local suite

- Result: PASSED
- Evidence: no separate unit, integration, E2E, browser, or other broad suite
  ran outside the one harness execution. Only the two authorized focused test
  files ran after documentation was written.

### Criterion 5 — Durable honest evidence/readiness wording

- Result: PASSED
- Evidence: the committed evidence names the exact tested commit, environment,
  command, result, counts, failure, lack of skips, safety posture, and remaining
  128-worker gap. Readiness/release links classify the run as failed.

### Criterion 6 — No runtime/behavior change

- Result: PASSED
- Evidence: the two implementation commits contain only the OAP transcript and
  the five allowed evidence/readiness files.

### Criterion 7 — Focused checks and PR CI reported honestly

- Result: FAILED at the OAP governance assertion
- Evidence: RC2 feature-scope documentation tests passed 4/4, `git diff --check`
  passed, and OAP governance passed 7/8 with the same assertion as the full run.
  GitHub has nine successful checks and one matching failed unit job.

### Criterion 8 — Final report-only commit

- Result: PASSED by publication protocol
- Evidence: this report is the sole path in the `SELF` commit; its remote head,
  first parent, changed path, and committed bytes are verified before the FIFO
  signal.

### Criterion 9 — Strategic merge authority retained

- Result: PASSED
- Evidence: the coding agent did not merge or enable auto-merge. PR #226 has a
  failed required check and remains for strategic disposition.

## Full-matrix execution

### Command and identity

The following command block was executed exactly once:

```bash
unset DATABASE_URL TEST_DATABASE_URL RUN_UPSTREAM_TESTS OPENAI_API_KEY OPENAI_UPSTREAM_API_KEY OPENROUTER_API_KEY
export ENABLE_EMAIL_DELIVERY=false
export SLAIF_HPC_GIT_PULL=0
export SLAIF_HPC_RUN_LOG=/tmp/slaif-oap-001-current-main.log
export SLAIF_HPC_SETUP_ENV_FILE=/tmp/slaif-oap-001-hpc.env
scripts/run-hpc-supercomputer-verify.sh 24
```

- Worker count: 24
- Host logical CPU capacity: 24
- Exact tested commit: `0f09de476f643e5879baeaf08eeb1d7393529758`
- Wrapper exit code: 1
- Objective classification: `RESULT=FAIL`
- Harness classification: `RESULT=FAIL_REAL_TEST`
- Matrix start: 2026-08-17 22:01:39 CEST (Europe/Ljubljana)
- Matrix duration: 202 seconds
- Run directory:
  `/dev/shm/slaif-gateway-tests-ubuntu-20260817-200139-1150731`
- Summary path:
  `/dev/shm/slaif-gateway-tests-ubuntu-20260817-200139-1150731/SUMMARY.md`
- Summary SHA-256:
  `220f837d2ede0647455d5f946f6cd041d20d375513b2b71962f4d0592430d97b`
- Wrapper log: `/tmp/slaif-oap-001-current-main.log`
- 128-worker post-PR-220 HPC qualification: NOT RUN

### Validation phases

| Phase | Status | Duration (s) | Note |
| --- | --- | ---: | --- |
| environment | PASS | 0 | Clean tracked tree at tested commit |
| dependency_sanity | PASS | 0 | pytest, xdist, Ruff, Alembic available |
| ruff | PASS | 0 | Complete configured lint command |
| alembic_heads | PASS | 0 | One migration head |
| git_diff_check | PASS | 0 | No tracked diff at test time |
| hidden_unicode | PASS | 2 | Repository scan passed |
| safety_scan | PASS | 0 | Harness safety assertions passed |
| docker_compose_config | PASS | 0 | Config validation passed |

No validation phase failed or skipped.

### Test suites

| Suite | Status | Duration (s) | Tests | Passed | Failed | Skipped | Note |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| unit | FAIL | 53 | 2,359 | 2,358 | 1 | 0 | 24 xdist workers |
| integration | PASS | 40 | 130 | 130 | 0 | 0 | 59 files, max concurrency 24 |
| E2E | PASS | 90 | 43 | 43 | 0 | 0 | 8 files, default serial concurrency 1 |
| browser | PASS | 14 | 2 | 2 | 0 | 0 | Serial isolated database |
| **Total** | **FAIL** |  | **2,534** | **2,533** | **1** | **0** |  |

- Skipped tests/phases: none.
- Coverage-weakening environment gaps: none.
- E2E mode: default serial, max concurrency 1.
- Browser status: ran serial and passed 2/2.

### Failure

The single failure was:

```text
FAILED tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr
assert "one numeric objective as exactly one PR" in order_text
1 failed, 2358 passed, 30 warnings in 52.81s
```

The active `001-a` order declares `PR mode: CREATE_NEW_PR` and requires exactly
one new PR, but it does not contain the separate literal phrase the existing
test asserts for every `-a` order. The order is strategic-authored and immutable;
the existing test is outside this verification-only order's allowed paths. No
repair or second full run was attempted.

Failure log:
`/dev/shm/slaif-gateway-tests-ubuntu-20260817-200139-1150731/logs/unit.log`.
There were no failing integration/E2E shard entries or shard log paths.

### Slowest shards

| Seconds | Suite | Test file |
| ---: | --- | --- |
| 24 | integration | `tests/integration/test_cli_routing_pricing_postgres.py` |
| 22 | E2E | `tests/e2e/test_openai_python_client_responses.py` |
| 20 | integration | `tests/integration/test_cli_keys_postgres.py` |
| 19 | integration | `tests/integration/test_cli_admin_owner_records_postgres.py` |
| 18 | integration | `tests/integration/test_admin_key_actions_postgres.py` |
| 18 | integration | `tests/integration/test_admin_web_auth_postgres.py` |
| 17 | integration | `tests/integration/test_admin_route_actions_postgres.py` |
| 17 | integration | `tests/integration/test_admin_email_delivery_actions_postgres.py` |
| 16 | E2E | `tests/e2e/test_openai_python_client_chat.py` |

## Environment, isolation, and cleanup

- Execution environment: Linux 6.18.33.2 WSL2 x86_64, 24 logical CPUs,
  approximately 47 GiB RAM, 48 GiB swap, and 24 GiB `/dev/shm` capacity.
- Python 3.12.3; pytest 9.0.3; Ruff 0.15.16; PostgreSQL 16.15; Redis 7.0.15;
  Docker CLI 29.1.3; Docker Compose 2.40.3; Playwright 1.60.0; OpenAI 2.41.0;
  RESPX 0.23.1.
- The setup helper refreshed ignored `.venv` dependencies and logged several
  conda-forge package-shard timeouts. Provisioning nevertheless completed and
  no phase skipped because of those warnings.
- PostgreSQL create/drop probing passed.
- `DATABASE_URL` was unset and never used for destructive setup.
- Database-backed shards received generated isolated `TEST_DATABASE_URL`
  values under the safe run prefix.
- Generated databases were dropped by safe per-shard cleanup because
  `SLAIF_SUPERCOMPUTER_KEEP_DBS` was not enabled.
- The user-local PostgreSQL cluster on `127.0.0.1:55432` was stopped by the
  wrapper and independently verified stopped. Its reusable transient data files
  remain only under `/dev/shm`, outside the repository.
- Redis-backed integration tests ran instead of skipping: 10 tests passed
  across three Redis-specific files.
- Docker Compose config passed without installing or requiring a Docker daemon.
- Playwright Chromium libraries resolved and the serial browser suite passed.
- Real email delivery was disabled in every shard subprocess.

## Focused post-harness verification

- `python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q`: PASSED —
  4/4.
- `python -m pytest tests/unit/test_oap_governance.py -q`: FAILED — 7/8 passed;
  same literal-phrase assertion at line 54. This was not a broad rerun.
- `git diff --check`: PASSED after documentation changes.
- Focused changed-document link/status scan: PASSED — local links resolve,
  failure and 128-worker status terms are present, and no false
  `RESULT=OK_CURRENT_MACHINE` appears.
- Changed-document hidden-control-character scan: PASSED.
- Changed-document credential/secret-pattern scan: PASSED.
- Prior OAP history hash check: PASSED — 000-a and 000-b order/report hashes
  remained unchanged.
- `.local-provider-catalog/` remained present, ignored, and untouched.
- Transcript staging check: the immutable strategic-authored 001-a order has a
  `new blank line at EOF` warning at line 395. The pointer-only check passed;
  editing the order bytes is prohibited.
- Evidence implementation staged-path and whitespace checks: PASSED — exactly
  the five allowed evidence/readiness files, with no whitespace warning.

## GitHub CI / required checks

Check state observed for implementation head
`a4a44e88da907a66d9bb21878dd330279a1201b0`: 9 SUCCESS, 1 FAILURE,
0 PENDING.

- `Analyze (javascript-typescript)`: SUCCESS — 39s.
- `Analyze (python)`: SUCCESS — 1m37s.
- `Analyze Python`: SUCCESS — 58s.
- `CodeQL`: SUCCESS — 2s.
- `Docker Compose smoke`: SUCCESS — 49s.
- `Documentation hygiene`: SUCCESS — 5s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m20s.
- `Playwright browser smoke`: SUCCESS — 1m59s.
- `PostgreSQL integration tests`: SUCCESS — 2m5s.
- `Unit, lint, and migration head`: FAILURE — 2m5s; the unit step reproduced
  the same governance assertion with 1 failed and 2,358 passed, and the job
  stopped on that failure.
- CI run: https://github.com/ulfe-lmi/slaif-api-gateway/actions/runs/32064249450
- All required checks green for the implementation head at report drafting: no.
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report.

## Documentation impact

- Added `docs/verification/2026-08-17-current-main-baseline.md` with the durable
  failed result, exact environment/commit/command/counts, no skips, failure,
  isolation, safety, evidence boundaries, and limited release recommendation.
- Added `docs/verification/README.md` as a commit/environment-specific evidence
  index, not a certification index.
- Updated `docs/rc-beta.md` and `docs/releases/README.md` minimally to link and
  classify the failed record.
- Added a post-adoption evidence note to `AGENTS.md` while retaining the original
  OAP adoption baseline and all no-128-worker/no-release/no-production claims.
- Read `docs/beta-readiness.md` as the historical May 2026 baseline but did not
  modify it because it is outside this order's allowed write paths.

## Local setup / dependencies

- Packages/tools/services installed or configured: the repository setup helper
  refreshed ignored `.venv` packages; prepared user-local PostgreSQL, Redis,
  Compose, and browser assets under `/dev/shm`; and wrote the requested temporary
  environment export file under `/tmp`.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: no setup artifact; only the OAP
  transcript and allowed evidence/readiness documents.
- Temporary raw log size was approximately 12 KiB, environment file 4 KiB, run
  directory 1.9 MiB, and stopped PostgreSQL cache 102 MiB. None is tracked or
  committed.
- The GitHub publication skill used local Git for branch/commits/push and the
  connected GitHub app for the explicitly required non-draft PR and result
  comment; `gh` independently verified PR/check state.

## Safety and scope confirmations

- One full harness run only: yes.
- Harness worker argument: 24 only.
- Separate duplicate broad suites: no.
- Required focused checks skipped: no.
- Unrelated files changed: no.
- Application/existing test/script/CI/dependency/migration change: no.
- Production secrets accessed: no.
- Real provider/API call performed: no.
- Real email sent: no.
- Production/staging data, database, credentials, deployment, or catalog action:
  no.
- `RUN_UPSTREAM_TESTS=1`: not set; real upstream execution remained disabled.
- `DATABASE_URL` used for destructive setup: no.
- Isolated per-shard `TEST_DATABASE_URL`: yes.
- PostgreSQL generated databases safely dropped and cluster stopped: yes.
- Raw logs, summary, virtualenv, browser binaries, or DB data committed: no.
- Prior OAP history edited: no.
- `.local-provider-catalog/` modified, staged, or committed: no.
- Strategic-side file committed: no.
- Second objective-001 PR created: NO.
- PR #224 modified: NO.
- Release/tag/issue/GitHub setting changed: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order or `oap/active` content edited by coding agent: NO; exact
  strategic-authored bytes were submitted unchanged.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- The full current-machine gate failed one required unit test, so current main
  is not verification-clean on this evidence and PR #226 must not merge in its
  current failed-check state.
- The missing literal phrase is in an immutable strategic-authored active order,
  while the assertion is in an existing test outside this round's write scope.
  Resolving that contract mismatch requires a separately authorized focused
  continuation.
- The one full harness run cannot be rerun in 001-a under the explicit
  test-economy instruction.
- The 128-worker post-PR-220 HPC qualification remains NOT RUN.
- This evidence does not exercise real providers and does not constitute a
  release decision, production certification, penetration test, compliance
  attestation, or scale proof.
- The setup helper encountered recoverable package-index timeouts. Required
  tools and coverage nevertheless completed with no skip.
- The strategic-authored order's EOF blank-line warning remains immutable.

## Recommended strategic follow-up

Treat objective 001-a as a failed, honestly evidenced verification gate. Do not
merge PR #226 while its required unit check fails. If the strategic model wants
to continue objective 001, activate a focused `001-b` order that deliberately
resolves the order/test contract mismatch and defines whether a new full gate
is authorized; the coding agent must not infer or rerun it. The separate
128-worker qualification and any RC2 release decision remain outstanding.
