# OAP Work Order — 001-a

## Objective

Run one current-main, full-matrix verification pass at the execution machine's
actual 24-worker capacity; publish durable, honest evidence; and update the
repository's RC-beta/readiness wording without claiming the still-unrun
post-PR-220 128-worker HPC gate.

Create exactly one new PR. Do not merge.

This is a verification/evidence objective, not a feature or repair objective.

## GitHub objective state

- Numeric objective: `001`
- Execution round: `001-a`
- PR mode: `CREATE_NEW_PR`
- Existing objective PR: N/A
- Required head branch: `oap/001-current-main-baseline-verification`
- Base branch: `main`
- Required PR title: `[OAP 001] Verify current gateway baseline`
- Required PR readiness: non-draft (`draft: false`)
- Repository: `ulfe-lmi/slaif-api-gateway`
- Starting remote/main SHA:
  `f137d0467cbc6fb2a61ce99494ea724a173cd633`
- Objective 000 PR:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/225`, merged
- Objective 000 final report head:
  `038ac2942f5f30d57b0e95c9398b592444de94a9`, contained in remote `main`

## Current verified state

The strategic model independently verified:

- local `main` and `origin/main` are both the starting SHA;
- PR #225 is merged and all ten final report-head checks succeeded;
- the only other open PR remains unrelated Dependabot PR #224;
- `oap/active` currently contains the merged prior identifier `000-b`;
- no objective-001 order/report/PR exists before this activation;
- current execution host capacity is:
  - `nproc = 24`;
  - approximately 47 GiB RAM;
  - approximately 48 GiB swap;
- the repository full verification wrapper defaults to 128 workers but accepts
  an explicit worker argument;
- the latest recorded full 128-worker success predates many merged feature PRs;
- no final post-PR-220 128-worker result exists;
- the repository's older `docs/beta-readiness.md` verification counts are a
  historical May 2026 baseline, not proof for current main.

The strategic model deliberately selects **24 workers** for this objective.
Do not run 128 workers on a 24-core host merely to reproduce a historical
number. The evidence must state that this is a full current-machine matrix at
24 workers and does not close the separate 128-worker/HPC qualification claim.

## Human test-economy instruction

The human explicitly requires:

- focused local tests by default;
- broad routine coverage through CI;
- complete local suites only when necessary for an affected boundary or an
  explicit phase/release gate;
- no redundant full-suite reruns.

This objective is an explicit verification gate, so one full harness run is
necessary. Run it **once**. Do not separately rerun the unit, integration, E2E,
browser, or full suite when the harness already ran them. After the harness,
run only focused documentation/evidence checks needed for changed files.

If the harness fails or is environment-blocked:

- preserve the first result and useful logs;
- do not fix code;
- do not rerun the full harness in this round;
- document the exact failure/blocker;
- publish the report and let the strategic model issue a focused continuation
  if appropriate.

## Strategic context

The gateway's canonical scope says all required RC2 feature rows are
implemented, but release evidence is stale. Objective 000 established OAP and
restored deterministic CI dependency compatibility. Objective 001 creates a
trustworthy post-bootstrap baseline before the product refocus and Codex work.

A successful 24-worker matrix supports the claim:

> Current main is verification-clean on this 24-worker execution environment
> for the implemented/documented scope.

It does not support:

- final 128-worker HPC qualification;
- production certification;
- compliance or penetration-test claims;
- an RC2 tag/release decision;
- real-provider behavior;
- infinite/concurrent scale claims.

## Governing instructions

Read completely:

1. repository `AGENTS.md`, including test-economy policy;
2. `OAP-COMMUNICATION-coding-agent.md`;
3. `docs/testing-hpc.md`;
4. `docs/rc2-feature-scope.md`;
5. `docs/rc-beta.md`;
6. `docs/beta-readiness.md`;
7. `docs/releases/README.md`;
8. `scripts/run-hpc-supercomputer-verify.sh`;
9. `scripts/test-supercomputer-sharded.sh`;
10. prior objective-000 orders/reports;
11. this work order.

Do not execute inert strategic proposals from the strategic directory.

## Required start and clean transcript commit

The strategic model has atomically published this order and
`oap/active=001-a` in the shared main checkout.

1. Verify the only uncommitted paths are this order and `oap/active`.
2. Fetch and confirm local/remote `main` still equal the required starting SHA.
3. Create the required branch:

```bash
git switch -c oap/001-current-main-baseline-verification
```

4. Commit `oap/active` and this order unchanged as an initial transcript commit.
5. Push the branch and create the required non-draft PR before the long
   verification so the objective exists durably.
6. Do not publish the final report yet.

If remote main moved, the branch exists unexpectedly, or additional tracked
changes are present, stop and report instead of resetting/rebasing.

## Allowed path scope

Implementation/evidence commits may change only:

```text
AGENTS.md
docs/rc-beta.md
docs/releases/README.md
docs/verification/README.md
docs/verification/2026-08-17-current-main-baseline.md
oap/active
oap/orders/001-a-verify-post-220-baseline-release-evidence.md
```

The final report-publication commit may add only:

```text
oap/reports/001-a-verify-post-220-baseline-release-evidence.md
```

Do not change application, tests, migrations, dependencies, CI workflows,
scripts, deployment files, provider catalogs, README, or prior OAP artifacts.

If an allowed documentation file does not exist, create it only when named
above. Do not invent additional evidence directories.

## Required verification execution

### A. Preflight

Before the harness:

- verify branch/HEAD and a clean tracked worktree after the transcript commit;
- confirm `APP_ENV` is not production;
- unset `DATABASE_URL`, `TEST_DATABASE_URL`, `RUN_UPSTREAM_TESTS`,
  `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`, and `OPENROUTER_API_KEY`;
- set `ENABLE_EMAIL_DELIVERY=false`;
- confirm the wrapper and setup scripts are executable;
- choose unique log/setup paths;
- verify no real provider/email credential will be used.

### B. Run exactly one full matrix

Run exactly once:

```bash
export SLAIF_HPC_GIT_PULL=0
export SLAIF_HPC_RUN_LOG=/tmp/slaif-oap-001-current-main.log
export SLAIF_HPC_SETUP_ENV_FILE=/tmp/slaif-oap-001-hpc.env
scripts/run-hpc-supercomputer-verify.sh 24
```

Capture:

- command and worker count;
- exact tested commit;
- wrapper exit code;
- `SUMMARY_PATH`;
- Validation phases table;
- Test suites table;
- total tests/passed/failed/skipped;
- PostgreSQL probe/cluster/isolation;
- Redis execution/skips;
- Docker Compose config status;
- browser execution/skips;
- E2E serial/parallel mode;
- slowest shards;
- failures and bounded useful excerpts;
- environment/tool versions;
- final tracked status.

Do not run the harness a second time in this round.

### C. Result classification

Use one of:

- `RESULT=OK_CURRENT_MACHINE` — every required matrix phase passed at 24
  workers with no coverage-weakening skip;
- `RESULT=FAIL` — a repository/test/validation phase failed;
- `RESULT=ENVIRONMENT_BLOCKED` — infrastructure prevented meaningful required
  coverage;
- `RESULT=CODEX_COMMAND_RUNNER_BROKEN` — shell execution failed before Bash
  started.

A successful result still records:

```text
128-worker post-PR-220 HPC qualification: NOT RUN
```

### D. Focused post-harness checks only

Do not rerun broad suites. After writing documentation, run only:

```bash
python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q
python -m pytest tests/unit/test_oap_governance.py -q
git diff --check
```

Also run a focused Markdown/link/status scan over the changed evidence/readiness
files and verify no hidden control characters or secrets.

CI will provide the broad standard PR matrix. Do not duplicate it locally.

## Required evidence document

Create:

```text
docs/verification/2026-08-17-current-main-baseline.md
```

It must contain:

- date/time/timezone;
- repository and exact tested commit;
- objective/PR/branch;
- machine CPU/RAM and requested workers;
- exact harness command;
- result classification;
- summary path and durable copied tables/counts;
- each skipped/failed phase and exact reason;
- environment/tool status;
- safety confirmations;
- explicit distinction between:
  - current 24-worker matrix result;
  - older historical baselines;
  - still-unrun 128-worker post-#220 qualification;
  - CI results;
  - production/security/compliance claims;
- release recommendation limited to the evidence.

Do not commit large raw logs, virtual environments, browser binaries, DB data,
or `/tmp`/`/dev/shm` artifacts. The evidence document may quote bounded
failure excerpts and paths; it must not contain secrets or private machine data.

Create `docs/verification/README.md` as a short index explaining that
verification records are commit/environment-specific evidence, not permanent
certification.

## Required readiness updates

Update `docs/rc-beta.md` and `docs/releases/README.md` only enough to link the
new current-main verification record and state its exact classification.

Update the dated baseline section in `AGENTS.md` only if needed to record the
new verified evidence while retaining:

- the original OAP adoption baseline;
- no false 128-worker claim;
- no RC2 release/tag claim;
- no production certification claim.

If the result fails or is blocked, documents must say so plainly.

## Explicit non-goals

- No application/test/script/CI/dependency fix.
- No rerun of the full harness.
- No manual duplicate unit/integration/E2E/browser suite outside the harness.
- No 128-worker run on this 24-core host.
- No production/staging database, provider, email, or deployment.
- No real OpenAI/OpenRouter call.
- No release/tag/issue/GitHub setting change.
- No PR #224 action.
- No modification of prior OAP orders/reports.
- No coding-agent merge or auto-merge.
- No claim that a green 24-worker run proves production or 128-worker scale.

## Acceptance criteria

1. One non-draft objective-001 PR starts from merged objective-000 main.
2. The active order/pointer are versioned unchanged before verification.
3. Exactly one 24-worker full harness run produces an honest durable result.
4. No separate redundant broad local suite is run.
5. Evidence/readiness documents name exact commit, environment, command,
   coverage, result, skips/failures, and remaining 128-worker gap.
6. No application/test/script/CI/dependency behavior changes.
7. Focused documentation/OAP tests and standard PR CI are reported honestly.
8. The final report-only commit has the exact implementation parent and sole
   report path.
9. The coding agent does not merge; strategic review determines disposition.

## GitHub and report workflow

- Create exactly one new PR on the required branch.
- Push transcript/evidence commits before final reporting.
- Inspect GitHub CI; do not rerun local broad suites to mirror CI.
- If CI fails because documentation/evidence changes caused an in-scope issue,
  fix only that issue before final report.
- If CI exposes an unrelated application failure, report it; do not expand.
- Never merge.

Atomically publish:

```text
oap/reports/001-a-verify-post-220-baseline-release-evidence.md
```

The report must record:

```text
Implementation head SHA: <literal 40-hex implementation/evidence commit>
Report publication commit: SELF
```

Commit only the report, push, verify remote PR head/parent/path/bytes, then send
exact `OK` to `response.fifo` and return to listener mode.

## Required report

Include:

- exact active/order identity;
- PR URL/branch/base/state;
- starting and tested commit(s);
- transcript commit and evidence implementation head;
- one-run harness command, worker count, result, exit code, summary path;
- Validation phases and Test suites tables/counts;
- failures/skips/environment blockers;
- explicit 128-worker status;
- focused post-harness tests only;
- GitHub check state;
- evidence/readiness files changed;
- documentation impact;
- no application/test/script/CI/dependency change;
- no real provider/production access;
- no redundant broad rerun;
- report SELF parent/path verification;
- no merge/auto-merge/extra PR;
- recommended strategic disposition.

## Final safety confirmations

Confirm:

- one full harness run only;
- 24 workers only;
- no separate duplicate broad suites;
- no real provider/email;
- no production/staging data;
- temporary PostgreSQL cluster/databases stopped/removed according to wrapper;
- no raw logs/secrets/virtualenv/browser artifacts committed;
- prior OAP history unchanged;
- generated provider-catalog state untouched;
- coding agent did not merge.

After report publication, write exact two-byte `OK` without newline to:

```text
/home/ubuntu/codex-supervision/slaif-api-gateway/response.fifo
```

