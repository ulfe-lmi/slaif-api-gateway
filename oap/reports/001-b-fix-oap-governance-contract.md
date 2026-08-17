# OAP Coding-Agent Report — 001-b

## Work order

- Identifier: 001-b
- Work-order file: `oap/orders/001-b-fix-oap-governance-contract.md`
- Numeric objective: 001
- PR mode: AMENDED_EXISTING_PR
- Active-pointer SHA-256:
  `3b3a102cc3fabffe117ccbdfe438e7799bf92c772361600cba5636213b39349b`
- Active-order SHA-256:
  `c776eb4f3aa46bc0be68d1af94bff2698f22ca917870219a75760c3dd06e824c`

## Status

COMPLETE

## Executive summary

Amended existing PR #226 with the focused OAP governance-contract repair. The
active `NNN-a` order still must declare `PR mode: CREATE_NEW_PR`; the test now
reads the one-new-PR invariant from the durable coding-agent protocol instead
of requiring every strategic order to repeat arbitrary prose. This preserves
the invariant while making the check structural and identifier-generic.

Only focused local checks ran: OAP governance 8/8, RC2 feature-scope docs 4/4,
changed-test Ruff, and `git diff --check` all passed. No full harness or broad
local suite reran. All ten standard GitHub checks passed on the 001-b
implementation head. The original one-pass 001-a matrix remains immutable
historical `RESULT=FAIL` evidence; the 128-worker post-PR-220 qualification
remains NOT RUN. PR #226 remains open and unmerged for strategic review.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 226
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/226
- PR state at report time: OPEN, non-draft
- Base branch: `main`
- Head branch: `oap/001-current-main-baseline-verification`
- Starting remote PR head: `4e4cbe6a48e8974c096ea1dfebf3ea491598e693`
- Prior implementation/evidence head: `a4a44e88da907a66d9bb21878dd330279a1201b0`
- Harness-tested transcript commit: `0f09de476f643e5879baeaf08eeb1d7393529758`
- Focused remediation commit: `76e99e2598e0ceadd98baadba82890249e4b5bd2`
- Implementation head SHA: `9d1ce7f561662806bb80dc4491ea65aa7497a7c8`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `76e99e2598e0ceadd98baadba82890249e4b5bd2`
    (`Make OAP PR invariant test structural`)
  - `9d1ce7f561662806bb80dc4491ea65aa7497a7c8`
    (`Document focused OAP governance remediation`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended an existing PR this turn: yes, PR #226 only
- Focused-remediation comment:
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/226#issuecomment-5319813582
- Second objective-001 PR created: no
- Merge performed: NO
- Auto-merge enabled: NO

## Starting-state reconciliation

- Local branch, remote branch, and PR #226 all resolved to the required starting
  head `4e4cbe6a48e8974c096ea1dfebf3ea491598e693` before editing.
- PR #226 was open, non-draft, targeted `main`, and used the required branch.
- Its report-head checks were nine success and one failure; the failure was the
  same OAP governance literal-order-prose assertion recorded by 001-a.
- The only uncommitted paths were the strategic-authored `oap/active=001-b`
  pointer and uniquely selected 001-b order.
- Prior 001-a order/report hashes matched their immutable published values.
- No 001-b report or replacement PR existed.

## Exact test change

```diff
 def test_initial_round_declares_new_pr_and_one_objective_one_pr() -> None:
     identifier, _order_path, order_text = _active_order()

     if identifier.endswith("-a"):
+        protocol_text = PROTOCOL_FILE.read_text(encoding="utf-8")
         assert "PR mode: `CREATE_NEW_PR`" in order_text
-        assert "one numeric objective as exactly one PR" in order_text
+        assert "`NNN-a` creates exactly one new PR for that numeric objective." in protocol_text
```

Why this is structural rather than weaker:

- the test remains generic for every active `NNN-a` identifier;
- the active order must still declare `PR mode: CREATE_NEW_PR`;
- the durable coding-agent protocol must still contain the exact one-new-PR
  invariant;
- the test no longer makes every future strategic order repeat one arbitrary
  prose fragment; and
- no `001-a` special case or invariant removal was introduced.

## Changes made

- Submitted the exact strategic-authored 001-b active pointer/order unchanged.
- Replaced the brittle order-prose assertion with the durable protocol assertion.
- Appended a focused remediation section to the existing verification record.
- Minimally updated AGENTS, RC-beta, and release-index wording to distinguish
  original failed-run history from the corrected candidate's focused/CI
  evidence.
- Added a concise focused-remediation result comment to PR #226.

## Files changed

Focused remediation commit:

- `oap/active` (strategic-authored bytes committed unchanged)
- `oap/orders/001-b-fix-oap-governance-contract.md`
  (strategic-authored bytes committed unchanged)
- `tests/unit/test_oap_governance.py`

Documentation commit:

- `AGENTS.md`
- `docs/rc-beta.md`
- `docs/releases/README.md`
- `docs/verification/2026-08-17-current-main-baseline.md`

Report-publication commit:

- `oap/reports/001-b-fix-oap-governance-contract.md`

No application, migration, dependency, CI, script, deployment,
provider-catalog, README, unrelated documentation, or prior OAP path changed.

## Acceptance-criteria evidence

### Criterion 1 — Structural invariant check

- Result: PASSED
- Evidence: the active order supplies PR mode; the durable coding protocol
  supplies the one-new-PR invariant. The test remains identifier-generic.

### Criterion 2 — Focused governance test

- Result: PASSED
- Evidence: `python -m pytest tests/unit/test_oap_governance.py -q` passed 8/8.

### Criterion 3 — Focused docs/lint/whitespace checks

- Result: PASSED
- Evidence: RC2 docs passed 4/4, Ruff passed on the changed test file, and
  `git diff --check` passed.

### Criterion 4 — No broad local rerun

- Result: PASSED
- Evidence: no HPC wrapper, full unit, integration, E2E, browser, Docker, or
  other broad local suite ran in 001-b.

### Criterion 5 — Original 001-a history preserved

- Result: PASSED
- Evidence: the original evidence file's first 203 lines retain exact SHA-256
  `3f81541428b48fedcc35280b39c23d8d8f7c0fcaa94de3134c1b7f7116e39354`.
  Its `RESULT=FAIL`, command, timestamps, tables, and 2,533/2,534 counts are
  unchanged; remediation was appended after them.

### Criterion 6 — Same PR and allowed scope

- Result: PASSED
- Evidence: only PR #226 was amended on its existing branch. The two
  implementation commits contain exactly the seven allowed paths listed above.

### Criterion 7 — Required GitHub checks

- Result: PASSED on the implementation head
- Evidence: all ten standard checks completed successfully, including the
  formerly failing unit/lint/migration job.

### Criterion 8 — Final report-only commit

- Result: PASSED by publication protocol
- Evidence: this report is the sole path in the `SELF` commit; the remote head,
  first parent, changed path, and exact bytes are verified before FIFO `OK`.

### Criterion 9 — Merge authority retained

- Result: PASSED
- Evidence: the coding agent did not merge or enable auto-merge. Strategic
  review determines disposition after final-head verification.

## Focused local verification only

- `python -m pytest tests/unit/test_oap_governance.py -q`: PASSED — 8 passed.
- `python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q`: PASSED —
  4 passed.
- `python -m ruff check tests/unit/test_oap_governance.py`: PASSED —
  `All checks passed!`.
- `git diff --check`: PASSED.
- Focused original-evidence prefix/hash check: PASSED — first 203 lines still
  hash to `3f81541428b48fedcc35280b39c23d8d8f7c0fcaa94de3134c1b7f7116e39354`.
- Original result/table/status scan: PASSED — `RESULT=FAIL`, 2,359 unit tests
  with 2,358 pass/1 fail, 2,534 total with 2,533 pass/1 fail, original matrix
  start/duration, and 128-worker NOT RUN remain.
- Remediation wording scan: PASSED — exact remediation commit, no-second-harness,
  historical-failure, CI-evidence, and 128-worker NOT RUN terms are present.
- Changed-path control-character scan: PASSED.
- Changed-path credential/secret-pattern scan: PASSED.
- Remediation staged-path and whitespace checks: PASSED — exactly active/order/
  test for the first commit and exactly four allowed docs for the second.
- Prior 001-a order/report hash verification: PASSED — order
  `a25f510202761dac52495adf68e6aaff766d121766820b332bc47a1671a3117c`,
  report
  `a79ab9206879191a16ea71e2d3eab4d1e4a357df33b6fe78d41d6841a36bf338`.
- `.local-provider-catalog/`: present, ignored, unstaged, and untouched.

No other local pytest command or harness/wrapper command ran during 001-b.

## Original verification evidence remains historical

- 001-a objective classification: `RESULT=FAIL`.
- Harness classification: `RESULT=FAIL_REAL_TEST`.
- One 24-worker matrix only: 2,534 total, 2,533 passed, 1 failed, 0 skipped.
- Original failed assertion: literal order-prose requirement in the governance
  test.
- The original full run was not rewritten, reclassified, or rerun.
- Focused 001-b remediation plus standard PR CI qualify the corrected PR
  candidate as separate evidence; they do not turn the historical run green.
- 128-worker post-PR-220 HPC qualification: NOT RUN.
- No production, RC2 release, security, compliance, penetration-test, provider,
  or scale claim follows.

## GitHub CI / required checks

Check state observed for implementation head
`9d1ce7f561662806bb80dc4491ea65aa7497a7c8`: 10 SUCCESS, 0 FAILURE,
0 PENDING.

- `Analyze (javascript-typescript)`: SUCCESS — 42s.
- `Analyze (python)`: SUCCESS — 1m42s.
- `Analyze Python`: SUCCESS — 55s.
- `CodeQL`: SUCCESS — 2s.
- `Docker Compose smoke`: SUCCESS — 1m1s.
- `Documentation hygiene`: SUCCESS — 8s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m27s.
- `Playwright browser smoke`: SUCCESS — 1m23s.
- `PostgreSQL integration tests`: SUCCESS — 2m12s.
- `Unit, lint, and migration head`: SUCCESS — 1m48s.
- CI run containing the standard workflow jobs:
  https://github.com/ulfe-lmi/slaif-api-gateway/actions/runs/32065417064
- All required checks green for the implementation head at report drafting: yes.
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report.

## Documentation impact

- Appended the exact root cause, remediation commit, structural test change,
  focused results, no-second-harness statement, CI reporting boundary, evidence
  interpretation, and 128-worker NOT RUN statement to the 001-a record.
- Updated `AGENTS.md` without replacing the original adoption baseline or the
  original failed-run evidence.
- Updated RC-beta and release-index wording minimally; the original 001-a run
  remains `RESULT=FAIL`, while focused remediation/standard CI are separate
  corrected-candidate evidence.
- No product behavior or public API documentation changed.

## Local setup / dependencies

- Packages/tools/services installed or configured in 001-b: none.
- `sudo`-level setup performed in 001-b: none.
- Database, Redis, browser, Docker, provider, or email setup in 001-b: none.
- Existing ignored artifacts from 001-a were not modified or committed.
- GitHub publication used local Git to push the existing branch and the
  connected GitHub app to add the focused-remediation comment; `gh`
  independently verified PR/check state.

## Safety and scope confirmations

- Second full harness run: NO.
- Broad local suite run: NO.
- Only focused tests/lint/checks ran: yes.
- Original 001-a evidence rewritten as a pass: NO.
- Prior OAP artifact edited: NO.
- Unrelated file changed: no.
- Application, dependency, CI, script, migration, deployment change: no.
- Production secret accessed: no.
- Real provider/API/email call: no.
- Production/staging database, data, credentials, deployment, or catalog action:
  no.
- Generated provider-catalog state modified/staged/committed: no.
- Raw log, virtualenv, browser binary, or database data committed: no.
- Strategic-side file committed: no.
- Second PR created: NO.
- PR #224 modified: NO.
- Release/tag/issue/GitHub setting changed: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order or `oap/active` content edited by coding agent: NO; exact
  strategic-authored bytes were submitted unchanged.
- Report-publication commit changes only this report file: yes.

## Known limitations / residual risk

- The original 001-a full matrix remains a failed historical run and must not
  be relabeled green.
- Standard CI passed for the corrected implementation head, but the final
  report-containing head requires independent strategic check verification.
- The 128-worker post-PR-220 HPC qualification remains NOT RUN.
- No real-provider, production, security, compliance, penetration-test, release,
  or scale claim is established by this focused repair or standard CI.

## Recommended strategic follow-up

Independently verify the `SELF` report commit, its first parent/path/bytes, the
final-head checks, and the seven-path focused scope. If all required final-head
checks are successful and review is satisfactory, the strategic model may
exercise its OAP merge authority for PR #226. The original one-pass matrix must
remain historical `RESULT=FAIL`, and the 128-worker qualification/release
decision remain separate future gates. The coding agent did not merge or enable
auto-merge.
