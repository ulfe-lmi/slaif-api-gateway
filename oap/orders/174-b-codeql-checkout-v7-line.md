# OAP Work Order — 174-b

PR mode: `AMEND_EXISTING_PR`

## Objective

Complete the tracked GitHub Actions v7 update on existing PR #311
(Objective 174) by bumping the single remaining line that the 174-a
order's allowed paths excluded: `.github/workflows/codeql.yml` line 26,
`uses: actions/checkout@v6` -> `uses: actions/checkout@v7`.

This is a focused same-PR correction of the discrepancy recorded by the
immutable 174-a report: the 174-a order specified "11 action-version
lines in ci.yml (6 checkout + 5 setup-python)", but the canonical base
`1bdbb8bf1534ea0b3217ced136972d1bced9c448` contains exactly 10 such
lines in `ci.yml` (6 `actions/checkout@v6` at lines 23, 79, 126, 173,
197, 264; 4 `actions/setup-python@v6` at lines 26, 82, 129, 176) and
exactly 1 `actions/checkout@v6` in `codeql.yml` (line 26). The 174-a
round correctly bumped all 10 `ci.yml` lines, left `codeql.yml`
byte-identical (honoring the 174-a allowed paths verbatim), and left
this residual line for strategic resolution. Strategy's decision is
recorded here: complete the tracked update (the repository's dependabot
configuration tracks the `github-actions` group across `/` with
`patterns: ["*"]`, which legitimately spans both workflow files), so
that PR #224 is fully superseded and the pipeline is uniformly on the
v7 checkout major.

The strategic model machine-verified on 2026-09-17 ~19:20
Europe/Ljubljana: `git grep` on `origin/main` shows exactly those 11
v6 action lines and no others; the 174-a implementation head
`5737c10a71c836f8cd2f12de457f058fed213f0a` carries the 10 bumped
`ci.yml` lines with all nine stable checks plus the intermittent
`CodeQL` suite rollup `success` (run IDs in the immutable 174-a
report). This round changes one line and re-proves the invariant
check set on the amended head.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-17 ~19:20
Europe/Ljubljana from live GitHub and the shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR to amend: **#311** (Objective 174), branch
  `oap/174-ci-actions-v7-bump`, state OPEN, base
  `1bdbb8bf1534ea0b3217ced136972d1bced9c448` (remote `main`, unchanged
  since; all nine main-branch checks `success`).
- 174-a implementation head:
  `5737c10a71c836f8cd2f12de457f058fed213f0a`; 174-a report-only head
  (current PR head at authoring time):
  `d021a04` — `oap/reports/174-a-ci-actions-v7-bump.md` (immutable;
  this round does not modify it).
- `oap/active` is at `174-a` (the active 174 round); this order
  activates `174-b`.
- Open PRs are exactly #224 (the Dependabot `github-actions` signal
  this objective completes; untouched by the coding agent — its
  superseded-closure is a strategic action after the PR merges) and no
  others.
- No other state change: remote `main` is still
  `1bdbb8bf1534ea0b3217ced136972d1bced9c448`; the 173-qualified
  candidate `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` and its dated
  record are untouched by this CI-infrastructure correction.

## PR contract

- Amend existing PR #311 (branch `oap/174-ci-actions-v7-bump`); no new
  PR.
- Round commits on the branch after the 174-a report commit:
  1. activation commit: the unchanged strategic-authored 174-b order
     + `oap/active` set to `174-b`;
  2. implementation commit: the single `codeql.yml` line;
  3. report-only commit: `oap/reports/174-b-codeql-checkout-v7-line.md`.
- The 174-a order and report remain byte-identical (immutable).

## Required change (exact)

The only functional change in this round is in
`.github/workflows/codeql.yml`:

1. Line 26: `uses: actions/checkout@v6` becomes
   `uses: actions/checkout@v7`.
2. Nothing else in any file changes: no other line in `codeql.yml`
   (job names, steps, inputs, permissions, triggers all unchanged), no
   other workflow (`ci.yml` already carries the 174-a bump and stays
   exactly as on the 174-a implementation head), no repository code,
   docs, or dependencies.

## Allowed paths

- `.github/workflows/codeql.yml` (exactly the one line above)
- `oap/orders/174-b-codeql-checkout-v7-line.md` (unchanged strategic
  work order)
- `oap/active` (`174-b`)
- `oap/reports/174-b-codeql-checkout-v7-line.md` (new immutable report
  for this round)

Nothing else. The 174-a order and report, and everything already
committed on the branch, are immutable and must not be modified or
reverted.

## Explicit exclusions (non-goals)

- No change to `ci.yml` (the 174-a state is final); no change to any
  other workflow, trigger, permission, or input; no action version
  change other than the single specified line.
- No application, test, script, migration, nginx, Docker, Compose,
  dependency (`pyproject.toml`), or documentation change of any kind —
  including `tests/unit/test_oap_governance.py` and the order template,
  both stable.
- No SBOM edit (`sbom/cyclonedx.json` byte-identical).
- No edits to any `docs/verification/2026-*` file, `README.md`, or
  `AGENTS.md`.
- No interaction with PR #224 or any other PR; no Dependabot action of
  any kind; no GitHub-settings action (branch protection, rulesets,
  required checks, environments); no release, tag, or deployment; no
  real provider calls; no secrets. No new product capability of any
  kind.
- No clean room, disposable database, or local test run: none is
  required or authorized (no repository code, dependency, or
  configuration other than one action version changes).

## Acceptance criteria

- **AP-1 — Check-set invariance on the amended head (decisive).** On
  the exact final PR head after this round's commits, the emitted check
  runs include all nine stable checks by exact name — `Unit, lint, and
  migration head`; `Documentation hygiene`; `OpenAI-compatible E2E
  tests`; `Playwright browser smoke`; `Docker Compose smoke`;
  `PostgreSQL integration tests`; `Analyze (javascript-typescript)`;
  `Analyze (python)`; `Analyze Python` — each `completed`/`success`,
  with run IDs recorded. The `CodeQL` suite rollup and the CodeQL
  analysis job(s) emitted by the amended `codeql.yml` must also be
  `completed`/`success` (this round directly modifies `codeql.yml`; the
  green CodeQL runs are the direct in-CI proof of the changed file). No
  stable check is missing, renamed, or duplicated.
- **AP-2 — Round diff scope.** `git diff` from the 174-a report head
  (`d021a04` — record the exact full SHA in the report) to this round's
  implementation head touches exactly `.github/workflows/codeql.yml`
  (one insertion, one deletion, the specified line) plus the 174-b
  order and `oap/active`. The cumulative diff vs base
  `1bdbb8bf1534ea0b3217ced136972d1bced9c448` touches exactly:
  `.github/workflows/ci.yml` (the 10 lines from 174-a),
  `.github/workflows/codeql.yml` (the 1 line from this round), and the
  OAP order/active/report files for both rounds — 11 action-version
  lines total, nothing else. Both diffs are recorded verbatim in the
  report.
- **AP-3 — Documentation checker (unchanged surface).** `python
  scripts/check_documentation.py` on the final tree prints
  `DOCUMENTATION_CHECK=OK` with the file count unchanged from the base
  tree (no documentation files added or edited).
- **AP-4 — Immutable report.** One report
  `oap/reports/174-b-codeql-checkout-v7-line.md` with the SELF
  topology: the report commit is the PR head, its first parent is this
  round's implementation head, the report commit changes only the
  report file, the report contains the literal base SHA, the literal
  174-a implementation head SHA, the single verdict line, and the
  merge-not-performed statement, and the remote PR head is verified as
  the report commit before the two-byte `OK` is written to the response
  FIFO. The AP-1 re-query on the final head is a mandatory gate before
  that OK.

## Verification and evidence commands

- AP-2: `git diff --name-only <174-a report head>..<implementation
  head>` and the full round diff; `git diff --name-only
  1bdbb8bf1534ea0b3217ced136972d1bced9c448..<implementation head>` and
  the cumulative diff; `git diff --check`.
- AP-1: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` (record
  the command and every run ID + conclusion on the implementation head;
  re-query on the final head after the report commit).
- AP-3: `python scripts/check_documentation.py`.

## Security, privacy, accounting, and boundaries

- The change is CI-infrastructure only: one upstream action version in
  the CodeQL workflow. No runtime dependency, no schema, no migration,
  no configuration surface, no trust/identity/secret/content boundary
  is touched. No production/staging system, no real provider, no real
  email, no external call of any kind beyond the GitHub API.

## Stop / escalation conditions

- If the amended head emits any missing, renamed, or failing stable
  check, or a non-`success` CodeQL run, for a cause other than a
  labeled environment-only item: record the failing check name and job
  log excerpt (redacted), classify (v7 checkout behavior change in the
  CodeQL job / runner environment / unrelated), revert the single
  `codeql.yml` line in-PR, and report the finding — do not weaken any
  step, input, or check to force green. Strategy decides the follow-up.
- If the round diff would include any line beyond the single specified
  line: do not push it; STOP and report the discrepancy.
- Suffix rounds (`174-c`...) are for bounded correction of this
  objective only; none are anticipated.

## Setup authority

- Standard shared-worktree execution per the coding-agent protocol on
  the existing branch (continue from the current PR head
  `d021a04`...; fetch and verify before committing). No clean room, no
  disposable database, no extra tooling is required or authorized.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and
file, PR mode (`AMEND_EXISTING_PR`), status, the single verdict line,
executive summary, authoritative GitHub state (PR #311 number, URL,
state, base SHA, 174-a implementation head SHA, this round's
implementation head SHA, report publication commit `SELF`,
merge-not-performed), full changed-file list for the round, the
verbatim round diff and cumulative diff, per-AP evidence (the complete
emitted check list with run IDs and conclusions on the implementation
head and the final head, including the CodeQL runs), local
verification, negative evidence (no change beyond the one line,
`ci.yml` unchanged from the 174-a state, 174-a order/report
byte-identical, no code/doc/dependency change, no PR/Dependabot/
GitHub-settings action, no secrets, no release/deploy), CI gate state
on the final head, and the environment-only labels (none expected).

## Merge prohibition

The coding agent never merges and never enables auto-merge. PR #311 is
left OPEN for strategic review and the delegated merge authority; the
strategic model merges the unique PR only after this round's final-head
gates pass and records the superseded-closure of PR #224.
