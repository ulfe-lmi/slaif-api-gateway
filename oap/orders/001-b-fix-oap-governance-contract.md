# OAP Work Order — 001-b

## Objective

Repair the single OAP governance contract mismatch found by the one-pass
24-worker baseline verification, amend PR #226 only, and document the focused
remediation without rerunning the full harness.

Do not create a new PR. Do not rerun any broad local suite.

## GitHub objective state

- Numeric objective: `001`
- Execution round: `001-b`
- PR mode: `AMEND_EXISTING_PR`
- Existing PR: `#226`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/226`
- Required head branch: `oap/001-current-main-baseline-verification`
- Base branch: `main`
- Starting remote PR head:
  `4e4cbe6a48e8974c096ea1dfebf3ea491598e693`
- Prior implementation/evidence head:
  `a4a44e88da907a66d9bb21878dd330279a1201b0`
- Harness-tested transcript commit:
  `0f09de476f643e5879baeaf08eeb1d7393529758`
- Prior round: `001-a`
- Repository: `ulfe-lmi/slaif-api-gateway`

## Why 001-a is insufficient

Round `001-a` correctly ran the full current-machine matrix exactly once at 24
workers and did not rerun it.

Recorded result:

- `RESULT=FAIL` / `RESULT=FAIL_REAL_TEST`;
- 2,534 total tests;
- 2,533 passed;
- 1 failed;
- 0 skipped;
- all validation phases passed;
- integration 130/130 passed;
- E2E 43/43 passed;
- browser 2/2 passed;
- Redis, PostgreSQL isolation, Docker Compose config, Ruff, Alembic, safety,
  and hidden-Unicode phases passed.

The only failure:

```text
tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr
```

The existing test requires every active `NNN-a` order to contain the literal
sentence:

```text
one numeric objective as exactly one PR
```

The immutable `001-a` order correctly declares:

- `PR mode: CREATE_NEW_PR`;
- `Create exactly one new PR`;
- no second PR;
- the complete OAP/GitHub contract.

The literal wording assertion is brittle and duplicates the durable invariant
already stated in `OAP-COMMUNICATION-coding-agent.md`:

```text
`NNN-a` creates exactly one new PR for that numeric objective.
```

Fix the test. Do not edit the immutable `001-a` order/report and do not rerun
the full harness.

## Human test-economy instruction

The human explicitly instructed that full suites must not become routine.

For this continuation:

- run only the focused OAP governance test;
- run only the focused RC2 documentation test because evidence/readiness files
  are updated;
- lint only the changed test file;
- run `git diff --check` and focused document scans;
- rely on GitHub CI for the broad standard matrix;
- do not run the HPC wrapper, full unit suite, integration, E2E, browser, or
  Docker locally.

## Governing instructions

Re-read:

1. repository `AGENTS.md`, especially test-economy policy;
2. `OAP-COMMUNICATION-coding-agent.md`;
3. prior `001-a` order/report;
4. `tests/unit/test_oap_governance.py`;
5. the current baseline evidence/readiness files;
6. this `001-b` order.

Verify PR #226 remains open on the required branch and current remote head
matches the starting head. Never create a replacement PR.

## Required start sequence

The strategic model has atomically published `oap/active=001-b` and this order
in the shared checkout.

Verify the only uncommitted paths are `oap/active` and this order. If so, do
not discard or overwrite them. Fetch GitHub, verify the local branch/HEAD and
PR, and continue on the existing branch. Any additional dirty tracked path is a
blocker.

## Allowed path scope

Implementation/remediation commits may change only:

```text
AGENTS.md
docs/rc-beta.md
docs/releases/README.md
docs/verification/2026-08-17-current-main-baseline.md
oap/active
oap/orders/001-b-fix-oap-governance-contract.md
tests/unit/test_oap_governance.py
```

The final report-publication commit may add only:

```text
oap/reports/001-b-fix-oap-governance-contract.md
```

Do not edit prior OAP orders/reports, application code, migrations,
dependencies, CI, scripts, deployment, provider catalogs, README, or unrelated
docs.

## Required implementation

### A. Make the OAP test structural

Update
`test_initial_round_declares_new_pr_and_one_objective_one_pr` so an active
`NNN-a` round proves:

1. its active order contains `PR mode: CREATE_NEW_PR`; and
2. the coding-agent protocol contains the durable `NNN-a` one-new-PR invariant.

Do not require every future strategic order to repeat one exact prose sentence.

A suitable structural assertion may verify the exact durable protocol text:

```text
`NNN-a` creates exactly one new PR for that numeric objective.
```

Keep the test identifier-generic. Do not special-case `001-a`, weaken
new-PR behavior, or remove one-objective/one-PR coverage.

### B. Preserve the original verification result

Do not change the recorded `001-a` harness classification from `RESULT=FAIL`.
Do not alter its tables/counts/command/timestamps.

Append a focused remediation section to
`docs/verification/2026-08-17-current-main-baseline.md` containing:

- root cause: brittle literal order wording assertion;
- focused test change and commit;
- no second full harness run;
- focused governance result;
- final PR CI status as observed when the implementation head completes;
- explicit statement that 128-worker post-PR-220 qualification remains NOT RUN;
- exact evidence interpretation:
  - original one-pass full matrix remains a failed historical run;
  - focused remediation plus final standard CI can qualify the corrected PR
    candidate without rewriting history;
  - no production/RC2/compliance claim follows.

Update `docs/rc-beta.md`, `docs/releases/README.md`, and the post-adoption note in
`AGENTS.md` minimally so they link the remediation state without calling the
original run green.

If implementation-head CI is still pending at documentation time, state it as
pending. Do not predict success. The final immutable report records the actual
observed check state, and the strategic model verifies the final report head.

## Explicit non-goals

- No second full harness run.
- No full local unit, integration, E2E, browser, or Docker suite.
- No application behavior change.
- No dependency/CI/script/migration/deployment change.
- No edit of immutable `001-a` order/report or objective-000 history.
- No production/provider/database/email/catalog action.
- No 128-worker run.
- No release/tag/issue/GitHub setting change.
- No second PR, merge, or auto-merge.

## Acceptance criteria

1. The governance test checks PR mode from the active order and the
   one-new-PR invariant from the durable coding protocol rather than arbitrary
   order prose.
2. The focused OAP governance test passes.
3. Focused RC2 documentation tests and changed-file lint/whitespace checks pass.
4. No broad local suite or second harness is run.
5. Original `001-a` result/tables remain immutable in meaning and the focused
   remediation is appended honestly.
6. PR #226 is amended on the same branch with no unrelated path.
7. Final required GitHub checks are reported accurately; strategic merge waits
   for the final report head to be green.
8. The final report-only commit has the required implementation parent and sole
   report path.
9. The coding agent does not merge.

## Required focused local verification only

Run:

```bash
python -m pytest tests/unit/test_oap_governance.py -q
python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q
python -m ruff check tests/unit/test_oap_governance.py
git diff --check
```

Also run focused checks that:

- prior `001-a` order/report hashes are unchanged;
- original evidence tables/counts and `RESULT=FAIL` remain;
- the remediation section says no second harness run;
- 128-worker qualification remains NOT RUN;
- changed files contain no hidden controls or secret material;
- staged paths are exactly allowed;
- `.local-provider-catalog/` remains ignored and untouched.

Do not run anything broader locally. Standard GitHub CI is the broad evidence.

## GitHub and report workflow

1. Commit the focused test, documentation, `oap/active`, and this order to the
   existing branch.
2. Push to PR #226.
3. Verify the new literal implementation head.
4. Inspect CI; do not duplicate CI suites locally.
5. Repair only a direct in-scope focused-test/documentation error if needed.
6. Never merge.
7. Atomically publish:

```text
oap/reports/001-b-fix-oap-governance-contract.md
```

8. Record literal implementation head and
   `Report publication commit: SELF`.
9. Commit only the report, push, and verify remote head/first parent/sole path.
10. Send exact two-byte `OK` to `response.fifo` and return to listener mode.

## Required report

Include:

- same PR/branch confirmation;
- exact test change and why it is more structural, not weaker;
- exact focused commands/results;
- explicit confirmation that no full/broad suite/harness reran;
- unchanged original one-pass result and evidence;
- current implementation-head CI state;
- all changed files and documentation impact;
- prior OAP hash verification;
- no application/dependency/CI/migration/provider/production change;
- report-only parent/path/bytes verification;
- no extra PR, merge, or auto-merge;
- recommended strategic disposition.

## Final safety confirmations

Confirm:

- no second harness or broad local suite;
- only focused tests ran;
- original `001-a` evidence was not rewritten as a pass;
- prior OAP artifacts remained immutable;
- no real provider/email or production/staging data;
- no generated catalog modification;
- no application/dependency/CI/script/migration change;
- only PR #226 was amended;
- coding agent did not merge.

After remote report publication, write exact `OK` without newline to:

```text
/home/ubuntu/codex-supervision/slaif-api-gateway/response.fifo
```
