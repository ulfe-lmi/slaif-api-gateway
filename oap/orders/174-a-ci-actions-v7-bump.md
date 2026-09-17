# OAP Work Order — 174-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Bump the two foundational CI actions in `.github/workflows/ci.yml` from
their current majors to the tracked Dependabot targets —
`actions/checkout@v6 -> v7` (6 occurrences) and
`actions/setup-python@v6 -> v7` (5 occurrences) — and prove that the
emitted check set of the pipeline is **invariant**: the same nine stable
checks, by exact name, still run and pass on the bumped pipeline.

This closes the last open repository PR (#224, Dependabot
`github-actions` group, 2 updates) with a clean OAP transcript: a fresh
objective and fresh PR against current `main`, not a merge of the stale
Dependabot PR (its head `4c73ee34` was built on an August base; the
repository's established discipline since the #250 decomposition is that
Dependabot PRs are signals, not merge vehicles). The repository's
dependabot configuration explicitly tracks this action group, so keeping
the pipeline on the current action majors is honoring declared policy,
not momentum: `v6` majors of these actions will eventually be
deprecated, and the bump is the tracked update the repo opted into.

Strategic facts (machine-verified by the strategic model on
2026-09-17 ~18:55 Europe/Ljubljana):

- The full diff of PR #224 is exactly those 11 action-version lines in
  `.github/workflows/ci.yml` and nothing else (verified verbatim).
- PR #224's head check runs (on its stale August base) show the entire
  pipeline green under the v7 actions — the in-CI proof that v7
  checkout/setup-python run this pipeline's jobs without breaking
  behavior (workspaces, Python 3.12 env, pip cache, Docker, PostgreSQL,
  browser, E2E all exercised).
- Check names are emitted from the `ci.yml`/`codeql.yml` job names,
  which this diff does not touch; the invariance predicate (AP-1)
  machine-verifies that on the fresh PR head rather than assuming it.
- The intermittent checks `CodeQL` (suite rollup) and
  `update-pip-graph` (the Dependabot "Configured Graph Update: pip"
  dynamic job, app = GitHub Actions, not a repository workflow) are NOT
  part of the nine stable checks and are not required by this order;
  they run non-deterministically and are not PR-scoped.
- This bump has no application, test, documentation, or dependency
  surface: it changes only which upstream action versions the pipeline
  runs. The nine-check suite itself (unit matrix, E2E, integration,
  Compose smoke, browser smoke, docs hygiene, CodeQL analyses) is the
  verification: no local clean-room or matrix run is required because no
  repository code, dependency, or configuration other than the action
  versions changes.

The outcome must be decisive in this round: either the bumped pipeline
emits the invariant nine-check set with all nine `success`
(`OUTCOME=A`, bump kept) or it does not (`OUTCOME=NO-GO`, the version
lines are reverted in-PR so the functional diff is empty, every
deviation classified with machine evidence, strategy decides).

## Reconciled authority and current state

Verified by the strategic model on 2026-09-17 ~18:55 Europe/Ljubljana
from live GitHub and the shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (the base for this order):
  `1bdbb8bf1534ea0b3217ced136972d1bced9c448` — merge of PR #310
  (Objective 173, merged 2026-09-17T16:34:19Z). All nine emitted
  main-branch checks on this commit are `completed`/`success`
  (re-verified at the same time).
- Objective 173 is terminal and verified (PR #310 merged:
  `RESULT=QUALIFIED-RC-POSTURE` for candidate
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`; runtime tree
  byte-identical to current main). Objectives 171, 172, 170, 168, 166
  are terminal and verified; 169 is terminal-abandoned.
- Shared `oap/active` is terminal at `173-a`. This order activates
  `174-a`.
- Open PRs are exactly #224 (Dependabot `github-actions` group; head
  `4c73ee3441d6a00fe6aeaac09a739b35ee53ae50`; diff = the 11 action
  version lines; all check runs on that head green; base stale).
  **This order does not touch PR #224**; its closure as superseded is a
  strategic action performed after this objective merges.
- The dated qualification record
  `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`
  is on `main` and names candidate `2b61312e`; this objective does not
  alter any verification record (a CI-infrastructure change is not a
  requalification event; the runtime tree is untouched).
- `docs/rc2-feature-scope.md` classification summary: 27
  `RC2_REQUIRED_IMPLEMENTED`, 0 `RC2_REQUIRED_MISSING`, 17
  `RC2_EXPLICITLY_DEFERRED`, 1 `RC2_UNSUPPORTED_BY_POLICY`, 6
  `NEEDS_MAINTAINER_DECISION`.
- Branch protection: ruleset `protect main` (id 23580289) active with
  `non_fast_forward` + `deletion` only, no bypass actors;
  `basic-protect` and `Code Quality Copilot review` rulesets disabled.
  Completion of branch protection is a human GitHub-administration
  action and is explicitly outside this order. The human-facing
  required-check list is the nine stable check names (below); the
  intermittent `CodeQL` suite rollup and `update-pip-graph` (Dependabot
  graph-update dynamic job) must NOT be made required checks because
  they are not PR-scoped.
- Known environment-only items (label, do not chase): unchanged from
  the 167/168/170/171/172/173 baseline (VM `codex-cli 0.154.0` vs
  fixture pin `0.148.0`; local-VM `pg_dump` DSN-form skip; local `psql`
  TCP-auth quirk). They are CI-side only for this order and do not
  affect the nine-check predicate.

## PR contract

- Base: `main` at `1bdbb8bf1534ea0b3217ced136972d1bced9c448`.
- Branch: `oap/174-ci-actions-v7-bump`.
- Title: `obj174: bump CI checkout/setup-python actions to v7`.
- One new PR for `174-a`; later `174-b`... rounds amend the same PR.
- Commit the unchanged strategic-authored order and `oap/active` per
  the coding-agent protocol. The order file is template-conforming as
  authored (first content line after the title is
  `PR mode: \`CREATE_NEW_PR\``); it must reach the PR head
  byte-identical so the candidate's governance unit test
  `tests/unit/test_oap_governance.py` passes on this PR head (the 169
  P4.1 precedent: the governance test and the order template are to be
  treated as stable; do not attempt to alter them).

## Required change (exact)

The only functional change is in `.github/workflows/ci.yml`:

1. All six occurrences of `uses: actions/checkout@v6` become
   `uses: actions/checkout@v7`.
2. All five occurrences of `uses: actions/setup-python@v6` become
   `uses: actions/setup-python@v7`.
3. Nothing else in any file changes: no job names, no step names, no
   inputs (`python-version: "3.12"`, `cache: pip`, etc. stay exactly as
   written), no triggers, no permissions, no other workflow
   (`codeql.yml` byte-identical), no repository code, docs, or
   dependencies.

## Allowed paths

- `.github/workflows/ci.yml` (exactly the 11 action-version lines
  above)
- `oap/orders/174-a-ci-actions-v7-bump.md` (unchanged strategic work
  order)
- `oap/active` (`174-a`)
- `oap/reports/174-a-ci-actions-v7-bump.md` (new immutable report)

Nothing else.

## Explicit exclusions (non-goals)

- No change to `codeql.yml` or any other workflow, trigger,
  permission, or input; no action version change other than the exact
  11 lines specified.
- No application, test, script, migration, nginx, Docker, Compose,
  dependency (`pyproject.toml`), or documentation change of any kind —
  including `tests/unit/test_oap_governance.py` and the order template,
  both stable.
- No SBOM edit (`sbom/cyclonedx.json` byte-identical; its regeneration
  remains a release-time maintainer decision).
- No edits to any `docs/verification/2026-*` file, `README.md`, or
  `AGENTS.md`.
- No interaction with PR #224 or any other PR (no close, rebase, merge,
  comment, or Dependabot action of any kind — the superseded-closure of
  #224 happens after this merge, by strategy).
- No GitHub-settings action (branch protection, rulesets, required
  checks, environments). No release, tag, or deployment. No real
  provider calls; no secrets. No new product capability of any kind.

## Acceptance criteria

- **AP-1 — Check-set invariance (decisive).** On the exact PR head,
  the emitted check runs include all nine stable checks by exact name —
  `Unit, lint, and migration head`; `Documentation hygiene`;
  `OpenAI-compatible E2E tests`; `Playwright browser smoke`;
  `Docker Compose smoke`; `PostgreSQL integration tests`; `Analyze
  (javascript-typescript)`; `Analyze (python)`; `Analyze Python` — each
  `completed`/`success`, with run IDs recorded. The `CodeQL` suite
  rollup may additionally be present (record its conclusion if so). No
  other, renamed, missing, or duplicated stable check name is
  permitted: the emitted set is invariant under the bump. Any missing
  or renamed stable check, or any non-`success` stable check, makes
  AP-1 unsatisfied.
- **AP-2 — Diff scope.** `git diff` vs base touches exactly
  `.github/workflows/ci.yml` (plus the OAP order/active/report files),
  and the `ci.yml` diff consists of exactly the 11 action-version lines
  specified (6 checkout + 5 setup-python; 11 insertions, 11
  deletions, no other changed line). The full diff is recorded in the
  report.
- **AP-3 — Pipeline behavior.** The nine green stable checks on the PR
  head constitute the in-CI proof that the v7 actions run the identical
  pipeline (same job definitions, same code, same dependencies) without
  behavior break: the unit/lint/migration check carries the full unit
  matrix and ruff gate, the E2E check carries the 54-test
  official-client matrix under `openai==3.14.1`, the PostgreSQL
  integration check carries the integration suite, and the Compose and
  browser smoke checks carry the deployment-path smoke. No local
  clean-room or matrix run is required (no repository code,
  dependency, or configuration other than the action versions
  changed); record this scoping statement with the AP-2 diff evidence.
- **AP-4 — Documentation checker (unchanged surface).** `python
  scripts/check_documentation.py` on the final tree prints
  `DOCUMENTATION_CHECK=OK` with the file count unchanged (no
  documentation files are added or edited).
- **AP-5 — Outcome branching.** If AP-1 and AP-2 hold on the bumped
  head: `OUTCOME=A` (the bump is the final functional state). If AP-1
  fails for a cause other than a labeled environment-only item: revert
  the 11 version lines in-PR (the functional diff becomes empty),
  classify every deviation with exact machine evidence (failing check
  name, job log excerpt, root-cause attribution: v7 action behavior
  change / GitHub-runner environment / unrelated), publish the report
  with `OUTCOME=NO-GO`, and leave the PR open for strategy — do not
  weaken any step, input, or check to force green.
- **AP-6 — Immutable report.** One report
  `oap/reports/174-a-ci-actions-v7-bump.md` with the SELF topology: the
  report commit is the PR head, its first parent is the recorded
  implementation (or documentation, on the NO-GO branch) head, the
  report commit changes only the report file, the report contains the
  literal base SHA `1bdbb8bf1534ea0b3217ced136972d1bced9c448`, the
  single verdict line (`OUTCOME=A` or `OUTCOME=NO-GO`), and the
  merge-not-performed statement, and the remote PR head is verified as
  the report commit before the two-byte `OK` is written to the response
  FIFO. The AP-1 re-query on the final head is a mandatory gate before
  that OK.

## Verification and evidence commands

- AP-2: `git diff --name-only <base>..HEAD` and the full `git diff` of
  `ci.yml` (record verbatim in the report).
- AP-1: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` (record
  the command and every run ID + conclusion on the implementation head;
  re-query on the final head after the report commit).
- AP-4: `python scripts/check_documentation.py`.
- `git diff --check`.

## Security, privacy, accounting, and boundaries

- The change is CI-infrastructure only: upstream action versions used
  by the check pipeline. No runtime dependency, no schema, no
  migration, no configuration surface, no trust/identity/secret/content
  boundary is touched. PostgreSQL remains quota/accounting truth and is
  untouched by this objective (it is exercised only inside the checks
  themselves, as always).
- Job log excerpts recorded in the report (NO-GO branch only) must be
  redacted of any secret, key, or canary value; only check names,
  conclusions, run IDs, and safe log fragments are recorded.
- No production/staging system, no real provider, no real email, no
  external call of any kind beyond the GitHub API.

## Stop / escalation conditions

- If a stable check is missing or renamed on the PR head: STOP, record
  the full emitted check list verbatim, classify the cause, and issue
  `OUTCOME=NO-GO` with the revert — do not attempt to "fix" the check
  naming or add jobs to restore the set.
- If a stable check is `failure` on the PR head for a cause other than
  a labeled environment-only item: record the failing job log excerpt,
  classify (v7 action behavior change / runner environment /
  unrelated), revert the 11 lines in-PR, and issue `OUTCOME=NO-GO`.
  Strategy alone decides the follow-up (explicit v6 retention with
  justification, or a deeper fix objective).
- If the `ci.yml` diff would include any line beyond the 11 specified
  version lines: do not push it; STOP and report the discrepancy.
- Suffix rounds (`174-b`...) are for bounded correction of this
  objective only, not for scope growth, additional action bumps, or
  pipeline redesign.

## Setup authority

- Standard shared-worktree execution per the coding-agent protocol
  (branch from `origin/main` at the base SHA). No clean room, no
  disposable database, no extra tooling is required or authorized for
  this objective; do not create them.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and
file, PR mode, status, the single verdict line, executive summary,
authoritative GitHub state (PR number, URL, state, base/head SHAs,
starting remote SHA `1bdbb8bf1534ea0b3217ced136972d1bced9c448`,
implementation head, report publication commit `SELF`,
merge-not-performed), full changed-file list, the verbatim `ci.yml`
diff, per-AP evidence (the complete emitted check list with run IDs and
conclusions on the implementation head and the final head, the
invariance statement naming all nine stable checks, the AP-3 scoping
statement, and — NO-GO branch only — the classification table with
redacted log excerpts), local verification, negative evidence (no
change beyond the 11 lines or the NO-GO revert, no other workflow
change, no code/doc/dependency change, no PR/Dependabot/GitHub-settings
action, no secrets, no release/deploy), CI gate state on the final
head, and the environment-only labels (none expected on the PASS
branch).

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is
left OPEN for strategic review and the delegated merge authority.
