# OAP Work Order — 167-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Answer one decisive verification question with fresh, dated, machine-
verifiable evidence: **is exact `main`
`9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` (merge of PR #303 / Objective
166) verified for the intended RC/deployment posture?**

This is a verification-only objective. It re-proves the current candidate on
its exact commit and publishes a new dated record in
`docs/verification/`; it implements no capability, fixes nothing, and makes
no release decision. The last integrated qualification record is dated to
main `8f2813bf745b90221da33a7cfaf40726c5b1b480` (2026-08-24), which is now
~20 commits and ten merged OAP objectives behind the candidate; the
Objective-165 authority model requires any "current" evidence to be a new
dated record for the named commit, never a rewrite of the historical one.

Strategic context: this is plan step 3 of the human's post-165 path
(governance hardening [human, partially done] -> SDK 3.x compatibility [done,
Objective 166] -> fresh current-main integrated qualification [this
objective] -> release decision [human]). The candidate already carries the
`openai==3.9.0`-qualified official-client surface from Objective 166, so
this qualification exercises the final candidate, including that surface.

If any phase reveals a genuine candidate defect, the objective is still
decisive: record the exact evidence, mark the record
`RESULT=NOT-QUALIFIED` with a per-phase failure table, and stop. Fixing the
defect is a separate numeric objective that strategy will scope from your
evidence. Do not repair anything in this objective.

## Reconciled authority and current state

Verified 2026-09-17 by the strategic model against live GitHub and the
shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (candidate):
  `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc`, merge of PR #303 (Objective
  166), merged 2026-09-17T07:15:34Z; parents exactly `1fccaa74...` and final
  report `61d9c566...`.
- All nine emitted main-branch checks on the candidate are SUCCESS
  (verified 2026-09-17 after merge): `Unit, lint, and migration head`;
  `Documentation hygiene`; `OpenAI-compatible E2E tests`; `Playwright
  browser smoke`; `Docker Compose smoke`; `PostgreSQL integration tests`;
  `Analyze (javascript-typescript)`; `Analyze (python)`; `Analyze Python`.
  The E2E job ran the 54-test official-client matrix under
  `openai==3.9.0` (job log: `Successfully installed ... openai-3.9.0
  httpx2-2.13.0 httpcore2-2.13.0 truststore-0.10.4 ...`, `54 passed`).
- Objective 166 is terminal and verified (PR #303 merged). Shared
  `oap/active` starts at terminal `166-a`. Objective 167 is unused: no
  `167-*` order, report, branch, or PR exists.
- Open PRs are exactly #250 (Dependabot; openai half superseded by #303,
  comment posted 2026-09-17; ruff half retained as update signal) and #224
  (Dependabot github-actions, stale). Both remain untouched by this
  objective.
- `docs/rc2-feature-scope.md`: 27 `RC2_REQUIRED_IMPLEMENTED`, 0
  `RC2_REQUIRED_MISSING`, 17 `RC2_EXPLICITLY_DEFERRED`.
- The reusable production-appliance qualification harness exists on the
  candidate: `scripts/production-qualification/run.py` (invoked as
  `python scripts/production-qualification/run.py`, optional `--keep`;
  prints `RESULT=OK` on success or `RESULT=FAIL` + `ERROR=...` on failure;
  default mode is no-keep with automatic project/volume cleanup and
  independent cleanup checks) plus
  `scripts/production-qualification/provider_double.py` (socket-level
  OpenAI-compatible provider double; records only safe booleans/counters,
  never bodies/keys/canary values). Historical evidence for this harness
  lives in `docs/verification/2026-08-24-production-appliance-qualification.md`
  (Objective 151-c; immutable).
- The documented deployment paths: dev Compose path
  (`cp .env.example .env` -> `docker compose build` -> `up -d postgres redis
  mailpit` -> explicit `slaif-gateway db upgrade` -> `up`) is mechanically
  reproduced by the CI `Docker Compose smoke` job on every push/PR; the
  production topology is `docker-compose.production.yml` (secrets, TLS,
  internal network) and is the harness's target.
- The execution VM has Docker 29.1.3 and Compose 2.40.3 available, the
  disposable local PostgreSQL `TEST_DATABASE_URL` harness (as used by
  Objectives 163-166), and a known environment-only unit failure:
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (VM codex CLI `codex-cli 0.154.0` versus fixture pin `codex-cli 0.148.0`);
  it must be reported as environment-only, distinct from any candidate
  finding.
- Branch `main` has the active ruleset `protect main` (non-fast-forward +
  deletion). No GitHub-settings change is part of this objective.

## PR contract

- Base: `main` at `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc`.
- Branch: `oap/167-current-main-integrated-qualification`.
- Title: `obj167: fresh integrated qualification of current main for RC posture`.
- One new PR for `167-a`; later `167-b`... rounds amend the same PR.

## Qualification design (required sequence)

P1 — Clean-room candidate. Create a fresh full clone of the canonical
repository under `/tmp/obj167-cleanroom/` and check out exactly
`9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` (detached); verify
`git rev-parse HEAD` equals the candidate SHA and `git status` is clean.
Create a fresh venv there and install `.[dev]`; record `pip freeze` lines
for at least `openai`, `httpx`, `httpx2`, `httpcore2`, `pydantic`, `respx`,
`pytest`. All subsequent runs use this clean-room tree and venv; never run
the candidate's code from the shared worktree.

P2 — Production-appliance qualification. From the clean-room tree run:
`.venv/bin/python scripts/production-qualification/run.py` (default no-keep
mode). Capture: the unique project name, the exact `RESULT=` line, the full
per-phase table, the restore-verifier bounded counts, the quota-phase
evidence, and the automatic no-keep cleanup checks. Expected: `RESULT=OK`.
If any phase fails: do not fix anything. Capture the exact failure output,
reproduce it once to separate environment-only causes (port binding, Docker
daemon state, leftover projects — clean those and re-run once) from
candidate defects (deterministic failure of candidate code); record both
classification and evidence. If it is a candidate defect, the record
carries `RESULT=NOT-QUALIFIED` with the per-phase table and this objective
completes on that evidence.

P3 — Candidate test matrix (clean-room venv, disposable local PostgreSQL
via `TEST_DATABASE_URL`, exactly as in Objectives 163-166):
- `scripts/test-unit-parallel.sh` — full unit suite; report exact
  passed/failed/skipped. The known VM-only codex-CLI-version failure, if
  present, must be re-verified environment-only (record `codex --version`
  output) and kept distinct.
- `python -m pytest tests/integration -q` — full PostgreSQL-backed
  integration suite; report exact counts.
- `python -m pytest tests/e2e -q` — the 54-test official-client matrix
  under the candidate's pinned `openai==3.9.0` (pip-freeze proof); report
  exact counts.
- Browser smoke: cite the green CI `Playwright browser smoke` job on the
  candidate (run ID); do not run a local browser suite (CI is the machine
  for this surface at this exact commit).

P4 — Exact CI state. Re-query GitHub for all nine required checks on the
candidate SHA at report time; record each check name with its run ID and
conclusion. All nine must be SUCCESS for `RESULT=QUALIFIED-RC-POSTURE`;
any non-success must be named in the record and prevents that verdict.

P5 — Dated record. Create
`docs/verification/2026-09-17-current-main-integrated-qualification.md`
(use the actual execution date in the filename if the run lands on a
different calendar date; report the exact path) containing: the exact
candidate SHA as evidence boundary; execution date and environment
(P1 freeze lines); the P2 command, project name, RESULT line, full
per-phase table, restore counts, and cleanup checks; the P3 exact counts
with the VM-only failure labeled; the P4 CI table with run IDs; the
deployment-path statement (documented dev Compose path covered by the CI
`Docker Compose smoke` job at this commit; production topology covered by
this harness run); a single unambiguous verdict line
(`RESULT=QUALIFIED-RC-POSTURE` or `RESULT=NOT-QUALIFIED`); and honest
limitations: provider double is mocked (not a real-provider run); not a
release decision, production certification, security review, compliance
finding, or SLA approval; RC2 required-scope completeness is asserted only
as the scope-lock document's current classification, not re-derived here.
Append one index row to `docs/verification/README.md` describing the record
as dated evidence for the named candidate commit only.

P6 — Publish. Commit the record (+ index row + OAP protocol files), open
the PR, wait until all nine required checks succeed on the final head.

## Allowed paths

Exactly these (plus the OAP protocol files):

- `docs/verification/2026-09-1*-current-main-integrated-qualification.md`
  (new dated record; date component = execution date)
- `docs/verification/README.md` (one appended index row)
- `oap/orders/167-a-current-main-integrated-qualification.md` (unchanged
  strategic bytes), `oap/active`,
  `oap/reports/167-a-current-main-integrated-qualification.md`

No other path may appear in the diff.

## Explicit exclusions (non-goals)

- No code change of any kind: `app/`, `tests/`, `scripts/`, `.github/`,
  `deploy/`, `nginx/`, `migrations/`, `pyproject.toml`,
  `docker-compose*.yml`, `Makefile`, and all other repository code are
  immutable in this objective. A discovered defect is evidence, not a task.
- No real provider calls: the harness uses its own provider double;
  `RUN_UPSTREAM_TESTS` stays unset; no provider credentials in any
  artifact.
- No `--keep` mode; the no-keep cleanup must complete and be evidenced. If
  a diagnostic `--keep` run is ever needed, the exact project must be
  removed afterward with cleanup proof in the report.
- No release/tag/deploy to any real system, no production/staging
  database, no email delivery, no GitHub-settings change, no Dependabot
  interaction.
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md` (all immutable historical records); the new
  record may reference them.
- No new tests, no new fixtures, no harness modifications of any kind.

## Acceptance criteria

- **AP-1** — The report contains the P1 clean-room proof (clone location,
  exact HEAD SHA, clean status, freeze lines) and the P2 production
  harness evidence: exact command, unique project name, exact `RESULT=`
  line, full per-phase table, restore-verifier counts, and no-keep cleanup
  checks — or, on failure, the exact failure output plus the
  environment-only/candidate-defect classification with reproduction
  evidence.
- **AP-2** — Exact local matrix counts on the candidate: full unit suite
  (with the VM-only failure labeled and proven environment-only if
  present), full PostgreSQL integration suite, and the 54-test
  official-client E2E matrix under `openai==3.9.0` with pip-freeze proof.
- **AP-3** — The record contains the P4 CI table: all nine required check
  names on the candidate SHA with run IDs and conclusions, re-queried at
  report time.
- **AP-4** — The dated record exists at the allowed path with the exact
  candidate SHA as evidence boundary, the single unambiguous verdict line,
  and the required limitations; `docs/verification/README.md` carries the
  index row; `python scripts/check_documentation.py` passes on the final
  code; no document claims certification, compliance, SLA, real-provider
  qualification, or current-state authority beyond its named commit.
- **AP-5** — Diff scope: exactly the allowed paths; zero changes under
  `app/`, `tests/`, `scripts/`, `.github/`, `deploy/`, `nginx/`,
  `migrations/`, `pyproject.toml`, or any compose file (prove by
  `git diff --name-only` listing).
- **AP-6** — The record's verdict is exactly one of
  `RESULT=QUALIFIED-RC-POSTURE` (all P2 phases OK, P3 matrix green modulo
  the labeled VM-only failure, P4 nine/ nine SUCCESS) or
  `RESULT=NOT-QUALIFIED` (with the exact failing phase/check table).
- **AP-7** — One immutable report
  `oap/reports/167-a-current-main-integrated-qualification.md` with literal
  implementation head SHA and `Report publication commit: SELF`; the final
  report-only commit changes only that report file, has the recorded
  implementation head as first parent, and is pushed and verified as the
  remote PR head before signalling `OK` on the response FIFO.

## Verification and evidence commands

Run and report exactly (clean-room venv, clean-room tree):

- P1: clone + checkout + `git rev-parse HEAD` + `git status --short`
  (empty) + venv install + the required `pip freeze` lines.
- P2: `.venv/bin/python scripts/production-qualification/run.py` (default
  no-keep) — capture full stdout/stderr.
- P3: `scripts/test-unit-parallel.sh`; `python -m pytest tests/integration
  -q`; `python -m pytest tests/e2e -q`; `codex --version` (only to label
  the known VM-only failure if it appears).
- P4: `gh` check-run queries for the candidate SHA (record the command
  output in the report).
- `python scripts/check_documentation.py` (must print
  `DOCUMENTATION_CHECK=OK files=<n>`).
- `git diff --check`.

## Security, privacy, accounting, and boundaries

- The harness uses only generated credentials and canaries inside the
  disposable Compose project; it never prints request bodies, keys,
  passwords, or canary values. The report and the dated record must not
  contain any secret, key, password, prompt, completion, canary value, or
  private artifact URL.
- No production/staging system, no real provider, no real email, no
  production database is touched. Disposable local PostgreSQL
  (`TEST_DATABASE_URL` harness) and the harness's unique Compose project
  only.
- PostgreSQL remains quota/accounting truth; no accounting code, schema, or
  boundary is touched (nothing is touched at all outside the record).
- No trust, identity, secret, or content boundary is widened.

## Stop / escalation conditions

- If Docker is unavailable or the harness cannot start after environment
  repair attempts (leftover-project cleanup, port release, daemon check)
  and a single clean re-run still cannot start: stop, report
  `ESCALATION` with the exact environment evidence; do not modify
  repository code or the harness.
- If a P2 phase fails as a candidate defect: do not fix, do not expand
  scope; publish the full evidence and complete the objective with
  `RESULT=NOT-QUALIFIED` (that is the decisive answer this objective owes).
- Suffix rounds (`167-b`...) are for bounded correction of this objective
  only (CI failures, review findings, verification gaps), not for fixing
  discovered candidate defects or for scope growth.

## Setup authority

- Fresh clone and venv under `/tmp/obj167-cleanroom/` (disposable; remove
  after the objective unless the report needs to reference it).
- Disposable local PostgreSQL via the standard `TEST_DATABASE_URL` harness
  (same mode as Objectives 163-166); the harness's own unique Compose
  project with generated secrets.
- Docker daemon use is authorized for the harness project and its cleanup.
- No provider credentials; no network egress beyond the GitHub clone,
  PyPI, and Docker Hub image pulls; no release/deploy; no Dependabot
  interaction; no GitHub settings.

## OAP report requirements

Standard report fields per `OAP-COMMUNICATION-coding-agent.md`:
identifier, work-order file, numeric objective, PR mode, status,
executive summary, authoritative GitHub state (PR number, state, branch,
base, head, starting SHA, implementation head, `SELF` topology), changes
made, files changed, acceptance-criteria evidence (AP-1 through AP-7),
local verification, negative evidence (zero code diff; no `--keep`
residue; no live provider calls; no secrets in artifacts), CI gate state
on the final head, and the merge-not-performed statement.
