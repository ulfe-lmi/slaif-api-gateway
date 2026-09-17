# OAP Work Order — 169-a

## Objective and business reason

Perform a fresh, current-main, integrated qualification of the exact remote
`main` `1043c3f42fb46f06a8d7952273739cefb9de6cc7` (the merge of PR #305 /
Objective 168) and publish a new dated verification record answering exactly
one question:

> Is this exact candidate sufficiently verified for the intended
> RC/deployment posture?

This is the plan's step 3 (fresh current-main integrated qualification) on the
repaired candidate. Objective 167 produced the verdict `RESULT=NOT-QUALIFIED`
on `9bb81cb9` for a non-deterministic per-worker metrics-exposure defect
(P2.3); Objective 168 repaired that exact defect and was verified
(two consecutive `RESULT=OK` harness runs on the PR head). Objective 169
re-proves qualification on the merged tree, with the determinism property
(now the shipped behavior) as the decisive test.

This is a verification-only objective. It must not introduce capability,
fix defects, or expand scope. If the candidate fails any acceptance
predicate, the correct outcome is `RESULT=NOT-QUALIFIED` with exact machine
evidence; strategy then decides whether the finding warrants a new numeric
objective.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-17 ~13:35 Europe/Ljubljana
from live GitHub and the shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (the candidate for this order):
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` — merge of PR #305
  (Objective 168, merged 2026-09-17T11:27:55Z; parents exactly prior main
  `08ca421bee1ddca62078302b910e8be88cf705be` and final report
  `38eaec3cc3030089a9d133a79d63c12773f80f8a`).
- All nine emitted main-branch checks on the candidate are
  `completed`/`success` (verified on the merge commit).
- Objective 166 is terminal and verified (PR #303 merged):
  `openai==3.9.0` is the qualified official-client dev/test dependency
  (`OUTCOME=A`; dated record
  `docs/verification/2026-09-17-openai-sdk3-qualification.md`).
- Objective 167 is terminal and verified (PR #304 merged): candidate
  `9bb81cb9` verdict `RESULT=NOT-QUALIFIED` (dated record
  `docs/verification/2026-09-17-current-main-integrated-qualification.md`);
  the P2.3 defect class is named there and must remain untouched history.
- Objective 168 is terminal and verified (PR #305 merged): multi-worker
  metrics exposure repaired (prometheus_client multiprocess mode on a shared
  tmpfs metrics volume in both shipped Compose topologies, lifespan-shutdown
  cleanup), AP-1 two consecutive clean-room harness runs `RESULT=OK` 16/16
  with all four exercised families positive, diff scope exactly the allowed
  paths, harness byte-identical, zero product-behavior change.
- Shared `oap/active` is terminal at `168-a`.
- Open PRs are exactly #250 (Dependabot; its `openai 2.41.0 -> 3.9.0` half
  is already represented on `main` via Objective 166 and its Ruff
  `0.15.16 -> 0.16.6` half is retained as an update signal only — do not
  touch) and #224 (Dependabot GitHub Actions; stale — do not touch).
- PR #291 (Objective 155) is CLOSED as superseded (2026-09-16T23:58:19Z,
  not merged); its branch is retained as historical evidence only.
- `docs/rc2-feature-scope.md` classification summary: 27
  `RC2_REQUIRED_IMPLEMENTED`, 0 `RC2_REQUIRED_MISSING`, 17
  `RC2_EXPLICITLY_DEFERRED`, 1 `RC2_UNSUPPORTED_BY_POLICY`, 6
  `NEEDS_MAINTAINER_DECISION`.
- Branch protection: ruleset `protect main` (id 23580289) is active with
  `non_fast_forward` + `deletion` only, no bypass actors; `basic-protect`
  and `Code Quality Copilot review` rulesets are disabled. Completion of
  branch protection (PR-required flow, required status checks, conversation
  resolution) is a human GitHub-administration action and is explicitly
  outside this order.
- The reusable production-appliance qualification harness
  (`scripts/production-qualification/run.py`, default no-keep) exists on
  the candidate and is byte-identical to the 168-verified state (the 168
  diff did not touch `scripts/`).
- Documented deployment paths: dev Compose (`docker-compose.yml`) and
  production Compose (`docker-compose.production.yml`), both carrying the
  168 metrics tmpfs mount on the `api` service.
- The execution VM has Docker 29.1.3 and Compose 2.40.3 available, the
  `slaif`/`postgres` local cluster on 127.0.0.1:5432, and `codex --version`
  = `codex-cli 0.154.0` (known VM-only environment fact; see AP-2).

## PR contract

- Base: `main` at `1043c3f42fb46f06a8d7952273739cefb9de6cc7`.
- Branch: `oap/169-current-main-integrated-requalification`.
- Title: `obj169: fresh integrated requalification of current main for RC posture`.
- One new PR for `169-a`; later `169-b`... rounds amend the same PR.
- Commit the unchanged strategic-authored order and `oap/active` per the
  coding-agent protocol.

## Qualification design (required sequence)

Execute exactly the following, in order, from the clean room:

- **P1 — Clean-room proof.** Fresh clone of the remote into
  `/tmp/obj169-cleanroom/`, detached checkout of the exact PR head,
  `git status --short` empty, fresh `.venv` (Python 3.12.x), record
  `pip freeze` lines for: `openai`, `httpx`, `httpx2`, `httpcore`,
  `httpcore2`, `pydantic`, `respx`, `pytest`, `prometheus_client`,
  `gunicorn`, `uvicorn`, `fastapi`, `starlette`. All candidate code runs
  only from the clean room.
- **P2 — Deterministic production-appliance proof (decisive).** Run
  `.venv/bin/python scripts/production-qualification/run.py` (default
  no-keep) **twice consecutively** in the clean room, with no code or
  environment change between the runs, capturing full stdout/stderr of
  each run. Both runs must complete. Record per run: project name, exact
  `RESULT=` line, phase table (all 16 phases),
  `metrics.positive_sample_present` per family, `restore_counts`,
  `cleanup` booleans and remaining networks/volumes,
  `readiness.public_denied`, and the accounting lifecycle sample
  (finalized/failed/estimated with reservation finalize/release/expire).
  Two consecutive `RESULT=OK` (16/16 phases) on the exact candidate is
  the determinism property under the shipped two-worker topology; a
  single-run pass is not sufficient.
- **P3 — Full local matrix (clean room).**
  - `scripts/test-unit-parallel.sh` — full unit suite; report exact
    passed/failed/skipped counts and identify every non-pass.
  - A fresh user-owned disposable PostgreSQL 16 instance for the
    integration suite (e.g. `initdb` under `/tmp/obj169-pg/`,
    `127.0.0.1:5433`, own role/database; drop the database before the run,
    stop and remove the instance after); `python -m pytest tests/integration -q`
    with `TEST_DATABASE_URL` pointed at it; report exact counts.
  - `python -m pytest tests/e2e -q` on a drop/recreated database — the
    54-test official-client matrix under the qualified `openai==3.9.0`;
    report exact counts.
- **P4 — CI evidence.** Query GitHub check runs for the exact PR head and
  record the nine required checks (`Unit, lint, and migration head`;
  `Documentation hygiene`; `OpenAI-compatible E2E tests`; `Playwright
  browser smoke`; `Docker Compose smoke`; `PostgreSQL integration tests`;
  `Analyze (javascript-typescript)`; `Analyze (python)`; `Analyze
  Python`) with run IDs and conclusions; re-query after the report-only
  commit per AP-7.
- **P5 — Dated record.** Publish
  `docs/verification/2026-09-17-current-main-integrated-requalification.md`
  and append exactly one index row to `docs/verification/README.md`.
  The record must name the exact candidate SHA, carry the single verdict
  line, the complete P1–P4 evidence, and honest limitation statements
  (mocked-upstream qualification only; not a real-provider run, release
  decision, security certification, or production approval). It is dated
  evidence for the named candidate commit only — it must not be phrased
  as a current-state claim for later commits, and no existing
  `docs/verification/2026-*` file may be edited.
- **P6 — Immutable report.** Publish the report per the report
  obligations below, as the report-only final commit.

Known environment-only expectations (label, do not chase):

- The unit suite may fail exactly the known VM-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  because the execution VM runs `codex-cli 0.154.0` against the fixture
  pin `0.148.0` (record `codex --version` as evidence).
- The integration suite may skip exactly the local-VM `pg_dump` case (the
  `TEST_DATABASE_URL` form limitation), identical to the 167/168
  baseline; in-container backup/restore is re-proven by the P2 runs.

Any other non-pass, ERROR, or skip in P2/P3 is a candidate finding and
must be classified with machine evidence (candidate defect / harness
harness-side / environment-only with proof), not chased or suppressed.

## Allowed paths

- `docs/verification/2026-09-17-current-main-integrated-requalification.md`
  (new dated record)
- `docs/verification/README.md` (one appended index row)
- `oap/orders/169-a-current-main-integrated-requalification.md` (unchanged
  strategic work order)
- `oap/active` (`169-a`)
- `oap/reports/169-a-current-main-integrated-requalification.md` (new
  immutable report)

Nothing else.

## Explicit exclusions (non-goals)

- No code change of any kind: `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, `Dockerfile`, `docker-compose*.yml`,
  `pyproject.toml`, `uv.lock`/lockfiles, or any other repository file
  outside the allowed paths.
- No defect fixes of any kind. If P2/P3/P4 exposes a candidate-side
  failure, classify and record it with exact evidence and continue the
  remaining safe phases; the verdict must then be
  `RESULT=NOT-QUALIFIED`. Strategy alone decides any follow-up numeric
  objective.
- No real provider calls: the harness uses only its own socket-level
  `qualification-double` provider; no provider credentials, and
  `RUN_UPSTREAM_TESTS` must remain unset throughout.
- No `--keep` mode; the no-keep cleanup must complete and be evidenced in
  both P2 runs.
- No release, tag, or deployment to any real system; no production/staging
  database; no real email.
- No GitHub-settings action (branch protection, rulesets, required
  checks) and no Dependabot interaction.
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md`; no new tests, fixtures, or harness
  modifications of any kind.
- No new product capability, even if trivially attractive.

## Acceptance criteria

- **AP-1** — The report and the dated record contain the P2 evidence: two
  consecutive no-keep harness runs from a fresh clean-room checkout of the
  exact PR head with no change between runs; both runs with exact
  `RESULT=OK`, all 16 phases OK, all four exercised metric families
  positive on the single authorized scrape
  (`gateway_http_requests_total`, `gateway_provider_requests_total`,
  `gateway_tokens_total`, `gateway_cost_eur_total`), `restore_counts`
  restored==source, no-keep cleanup all true with empty remaining
  networks/volumes, and `readiness.public_denied: true`. A run of
  `RESULT=FAIL` or of missing/zero positive families makes AP-1 unsatisfied
  and forces the `RESULT=NOT-QUALIFIED` verdict with the exact failure
  recorded.
- **AP-2** — Exact P3 matrix counts on the candidate, with every non-pass
  accounted for: the only permitted non-passes are the two labeled
  environment-only items above (each with its recorded proof:
  `codex --version` output; the `pg_dump` skip identity vs the 167/168
  baseline). E2E must be 54 passed / 0 failed / 0 skipped under
  `openai==3.9.0` with the P1 freeze lines recorded.
- **AP-3** — The record contains the P4 CI table: all nine required checks
  `success` on the exact PR head, with run IDs.
- **AP-4** — The dated record exists at the allowed path, names the exact
  candidate SHA in its prose, contains exactly one verdict line of the
  form `RESULT=QUALIFIED-RC-POSTURE` or `RESULT=NOT-QUALIFIED`, and states
  the limitation sentences required by P5. `python
  scripts/check_documentation.py` on the final tree prints
  `DOCUMENTATION_CHECK=OK` (file count may grow by one).
- **AP-5** — Diff scope vs base: exactly the five allowed paths; zero
  changes under `app/`, `tests/`, `scripts/`, `.github/`, `migrations/`,
  `nginx/`, and zero changes to `Dockerfile`, `docker-compose*.yml`,
  `pyproject.toml`, or any existing documentation file.
- **AP-6** — `RESULT=QUALIFIED-RC-POSTURE` is permitted only when AP-1,
  AP-2 (with only the labeled environment-only exceptions), and AP-3 all
  hold as specified; any deviation yields `RESULT=NOT-QUALIFIED`. Do not
  soften, re-label, or average a failure; the 151-d/167 boundary-strictness
  precedent applies.
- **AP-7** — One immutable report
  `oap/reports/169-a-current-main-integrated-requalification.md` with the
  SELF topology: the report commit is the PR head, its first parent is the
  recorded implementation (documentation) head, the report commit changes
  only the report file, the report contains the literal candidate SHA and
  the merge-not-performed statement, and the remote PR head is verified as
  the report commit before the two-byte `OK` is written to the response
  FIFO. The P4 re-query on the final head is a mandatory gate before that
  OK.

## Verification and evidence commands

- P1: clone + checkout + `git rev-parse HEAD` + `git status --short` +
  `pip freeze` selection.
- P2: `.venv/bin/python scripts/production-qualification/run.py` (default
  no-keep) twice; retain full stdout/stderr files locally and cite the
  exact `RESULT=` lines, project names, and per-family evidence in the
  record and report.
- P3: `scripts/test-unit-parallel.sh`; `python -m pytest tests/integration
  -q` (disposable PG, drop/recreated database); `python -m pytest tests/e2e
  -q` (drop/recreated database); `codex --version`.
- P4: `gh api repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs`
  (record the command and run IDs; re-query after the report commit).
- `python scripts/check_documentation.py` (must print
  `DOCUMENTATION_CHECK=OK`).
- `git diff --check`.

## Security, privacy, accounting, and boundaries

- The harness uses only generated credentials and canaries inside the
  disposable Compose project; no real secret, key, prompt, completion, or
  canary value may appear in the record or report (redact any disposable
  password).
- No production/staging system, no real provider, no real email, no
  external call of any kind beyond the local disposable stack and the
  GitHub API for check queries.
- PostgreSQL remains quota/accounting truth; no accounting code, schema, or
  migration is touched by this objective.
- No trust, identity, secret, or content boundary is widened; the
  `/metrics` authentication policy is verified unchanged via
  `readiness.public_denied` in both P2 runs.

## Stop / escalation conditions

- If Docker is unavailable or the harness cannot start after two setup
  attempts: STOP, report the environment evidence, do not substitute a
  weaker test.
- If a P2 phase fails as a candidate defect: do not fix, do not expand
  scope; classify, record the exact machine evidence, complete the
  remaining safe phases if possible, and issue the
  `RESULT=NOT-QUALIFIED` verdict.
- If a P4 required check is not `success` on the candidate and the cause
  is not a labeled environment-only item: record it and the verdict must
  be `RESULT=NOT-QUALIFIED`.
- Suffix rounds (`169-b`...) are for bounded correction of this objective
  only, not for scope growth or defect fixing.

## Setup authority

- Fresh clone and venv under `/tmp/obj169-cleanroom/` (disposable; remove
  after the objective).
- Fresh disposable PostgreSQL 16 under `/tmp/obj169-pg/` on
  `127.0.0.1:5433` for the integration suite (stop and remove after).
- Generated credentials only; all harness state inside the disposable
  Compose project, removed by no-keep cleanup.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and file,
PR mode, status, executive summary, authoritative GitHub state (PR number,
URL, state, base/head SHAs, starting remote SHA, implementation head,
report publication commit `SELF`, merge-not-performed), full changed-file
list, per-AP evidence, local verification, negative evidence (no code
change, no `--keep` residue, no live provider calls, no secrets, no
release/deploy/GitHub-settings/Dependabot action, no historical-record
edits), CI gate state on the final head, and the environment-only labels
with proofs.

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is left
OPEN for strategic review and the delegated merge authority.
