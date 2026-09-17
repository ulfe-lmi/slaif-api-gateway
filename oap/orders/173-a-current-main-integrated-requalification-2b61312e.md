# OAP Work Order — 173-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Perform a fresh, current-main, integrated qualification of the exact
remote `main` `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (the merge of
PR #309 / Objective 172; `main` has not moved since) and publish a new
dated verification record answering exactly one question:

> Is this exact candidate — the current `main` itself — sufficiently
> verified for the intended RC/deployment posture?

This is the plan's "fresh current-main integrated qualification" step
re-grounded on the actual current `main` after the SDK-qualification
work completed. Objective 170 produced
`RESULT=QUALIFIED-RC-POSTURE` for candidate
`1043c3f42fb46f06a8d7952273739cefb9de6cc7` (PR #305 merge), but `main`
has since advanced through Objective 171 (PR #308: `ruff==0.16.7` +
explicit lint policy pin) and Objective 172 (PR #309: `openai==3.14.1`
qualified pin). The strategic model machine-verified on
2026-09-17 ~17:44 Europe/Ljubljana that the full diff
`1043c3f4..2b61312e` is exactly 12 paths — `pyproject.toml` (dev pins
only: `ruff==0.16.7`, the `[tool.ruff.lint]` policy pin,
`openai==3.14.1`), two new dated verification records, the
`docs/verification/README.md` index rows, one sentence in
`docs/openai-compatibility.md`, and the OAP orders/reports/active files
for 170/171/172 — with **zero changes** under `app/`, `tests/`,
`scripts/`, `.github/`, `migrations/`, `nginx/`, `Dockerfile`,
`docker-compose.yml`, `docker-compose.production.yml`, or `Makefile`.
The runtime surface is therefore byte-identical to the 170-qualified
candidate; this objective re-proves that on the exact current candidate
and makes the dated record name the commit a release decision would
actually point at. AP-0 below makes that identity proof part of the
record.

This is a verification-only objective. It must not introduce capability,
fix defects, or expand scope. If the candidate fails any acceptance
predicate, the correct outcome is `RESULT=NOT-QUALIFIED` with exact
machine evidence; strategy then decides whether the finding warrants a
new numeric objective.

The acceptance predicates are the strict 170 set: the determinism
property is two consecutive default-no-keep production-appliance
harness runs, both `RESULT=OK` 16/16, on the exact candidate. If a
similar single transient availability-class 503 recurs (the 169 P2.3
class, which did not recur in 170), do not chase, retry, or re-label
it: record it with machine evidence (exact request, phase,
preconditions, host evidence) and the verdict is `RESULT=NOT-QUALIFIED`
per AP-1; strategy will then weigh the accumulated evidence (a third
independent requalification attempt with the same failure class) for the
follow-up decision. No pre-emptive softening of any acceptance
predicate is permitted by this order.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-17 ~17:44 Europe/Ljubljana
from live GitHub and the shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (the candidate for this order):
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` — merge of PR #309
  (Objective 172, merged 2026-09-17T15:35:38Z; parents exactly prior
  main `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09` and final report
  `d14c19e` — the report commit of PR #309). All ten emitted
  main-branch checks on the candidate are `completed`/`success`
  (re-verified at the same time).
- Objective 172 is terminal and verified (PR #309 merged:
  `openai==3.14.1` qualified, `OUTCOME=A`, dual-phase 54/0/0 matrix).
  Objective 171 is terminal and verified (PR #308 merged:
  `ruff==0.16.7` + explicit lint policy pin, zero code change).
  Objective 170 is terminal and verified (PR #307 merged: candidate
  `1043c3f4` verdict `RESULT=QUALIFIED-RC-POSTURE`, dated record
  `docs/verification/2026-09-17-current-main-integrated-requalification.md`
  on `main`). Objective 169 is terminal-abandoned (PR #306 closed;
  findings preserved on its branch). Objectives 166, 167, 168 are
  terminal and verified (PR #303: `openai==3.9.0` qualified,
  `OUTCOME=A`; PR #304: candidate `9bb81cb9` verdict
  `RESULT=NOT-QUALIFIED`; PR #305: multi-worker metrics exposure
  repaired).
- **Runtime-tree identity (machine-verified, recorded above):**
  `git diff --stat 1043c3f42fb46f06a8d7952273739cefb9de6cc7..2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
  lists exactly 12 paths (docs, OAP, `pyproject.toml` dev pins);
  `git diff --name-only` over `app/ tests/ scripts/ .github/
  migrations/ nginx/ Dockerfile docker-compose.yml
  docker-compose.production.yml Makefile` over the same range is empty.
- Shared `oap/active` is terminal at `172-a`. This order activates
  `173-a`.
- Open PRs are exactly #224 (Dependabot GitHub Actions group; stale —
  do not touch). PR #250 is CLOSED (decomposed, 2026-09-17T14:56:50Z).
- PR #291 (Objective 155) is CLOSED as superseded; PR #306 (Objective
  169) is CLOSED as abandoned; their branches are retained as
  historical evidence only and must not be imported.
- `docs/rc2-feature-scope.md` classification summary: 27
  `RC2_REQUIRED_IMPLEMENTED`, 0 `RC2_REQUIRED_MISSING`, 17
  `RC2_EXPLICITLY_DEFERRED`, 1 `RC2_UNSUPPORTED_BY_POLICY`, 6
  `NEEDS_MAINTAINER_DECISION`.
- Branch protection: ruleset `protect main` (id 23580289) is active
  with `non_fast_forward` + `deletion` only, no bypass actors;
  `basic-protect` and `Code Quality Copilot review` rulesets are
  disabled. Completion of branch protection is a human
  GitHub-administration action and is explicitly outside this order.
- The reusable production-appliance qualification harness
  (`scripts/production-qualification/run.py`, default no-keep) exists
  on the candidate and is byte-identical to the 168/170-verified state
  (zero `scripts/` change in the 171/172 merges).
- Documented deployment paths: dev Compose (`docker-compose.yml`) and
  production Compose (`docker-compose.production.yml`), both carrying
  the 168 metrics tmpfs mount on the `api` service; unchanged in
  171/172.
- `sbom/cyclonedx.json` is a point-in-time snapshot (timestamp
  2026-08-23, rc1 era, specVersion 1.5, no `tools` signature) that is
  stale w.r.t. the 166/171/172 dev pins. It is **excluded** from this
  order: its generation method is not recorded in the repository, so a
  regenerated artifact would be methodologically non-comparable. Its
  regeneration remains a release-time decision of the human maintainer
  (the dated record states its status).
- The execution VM has Docker 29.1.3 and Compose 2.40.3 available
  (versions recorded in the 170 order; re-verify at execution and
  record the actual output), the `slaif`/`postgres` local cluster on
  127.0.0.1:5432 (note: the 5432 cluster carries 168-era diagnostic
  residue — extra roles and a changed local `slaif` password — so use a
  fresh disposable cluster for the integration suite), and
  `codex --version` = `codex-cli 0.154.0` (known VM-only environment
  fact; see AP-2).

## PR contract

- Base: `main` at `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`.
- Branch: `oap/173-current-main-integrated-requalification-2b61312e`.
- Title: `obj173: fresh integrated requalification naming the exact current main candidate`.
- One new PR for `173-a`; later `173-b`... rounds amend the same PR.
- Commit the unchanged strategic-authored order and `oap/active` per
  the coding-agent protocol. The order file is template-conforming as
  authored (first content line after the title is
  `PR mode: \`CREATE_NEW_PR\``); it must reach the PR head
  byte-identical so the candidate's governance unit test
  `tests/unit/test_oap_governance.py` passes on this PR head (the 169
  P4.1 precedent: the governance test and the order template are to be
  treated as stable; do not attempt to alter them).

## Qualification design (required sequence)

Execute exactly the following, in order, from the clean room:

- **P0 — Runtime-tree identity proof (scope anchor).** From the clean
  room, record the verbatim outputs of:
  - `git diff --stat 1043c3f42fb46f06a8d7952273739cefb9de6cc7..HEAD`
    (HEAD = exact PR head; candidate code identical to remote
    `main` `2b61312e` plus the OAP order/active files only), and
  - `git diff --name-only 1043c3f42fb46f06a8d7952273739cefb9de6cc7..HEAD -- app tests scripts .github migrations nginx Dockerfile docker-compose.yml docker-compose.production.yml Makefile`.
  Both must match the strategic verification recorded above (12
  paths; empty runtime-surface list). Any discrepancy is a candidate
  finding: classify, record, and the verdict must be
  `RESULT=NOT-QUALIFIED`.
- **P1 — Clean-room proof.** Fresh clone of the remote into
  `/tmp/obj173-cleanroom/`, detached checkout of the exact PR head,
  `git status --short` empty, fresh `.venv` (Python 3.12.x), record
  `pip freeze` lines for: `openai` (must be `3.14.1`), `ruff`
  (must be `0.16.7`), `httpx`, `httpx2`, `httpcore`, `httpcore2`,
  `pydantic`, `respx`, `pytest`, `prometheus_client`, `gunicorn`,
  `uvicorn`, `fastapi`, `starlette`. All candidate code runs only from
  the clean room.
- **P2 — Deterministic production-appliance proof (decisive).** Run
  `.venv/bin/python scripts/production-qualification/run.py` (default
  no-keep) **twice consecutively** in the clean room, with no code or
  environment change between the runs, capturing full stdout/stderr of
  each run. Both runs must complete. Record per run: project name,
  exact `RESULT=` line, phase table (all 16 phases),
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
    integration suite (e.g. `initdb` under `/tmp/obj173-pg/`,
    `127.0.0.1:5433`, own role/database; do not reuse the 5432 system
    cluster or any prior diagnostic cluster; drop the database before
    the run, stop and remove the instance after); `python -m pytest
    tests/integration -q` with `TEST_DATABASE_URL` pointed at it;
    report exact counts.
  - `python -m pytest tests/e2e -q` on a drop/recreated database — the
    54-test official-client matrix under the qualified
    `openai==3.14.1`; report exact counts.
- **P4 — CI evidence.** Query GitHub check runs for the exact PR head
  and record the nine required checks (`Unit, lint, and migration
  head`; `Documentation hygiene`; `OpenAI-compatible E2E tests`;
  `Playwright browser smoke`; `Docker Compose smoke`; `PostgreSQL
  integration tests`; `Analyze (javascript-typescript)`; `Analyze
  (python)`; `Analyze Python`) with run IDs and conclusions; re-query
  after the report-only commit per AP-7. All nine must be `success` on
  the PR head.
- **P5 — Dated record.** Publish
  `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`
  and append exactly one index row to `docs/verification/README.md`.
  The record must name the exact candidate SHA
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`, carry the single verdict
  line, the complete P0–P4 evidence, a short "Relationship to the 170
  qualification" note (runtime tree byte-identical to the 170-qualified
  candidate `1043c3f4` per P0; 171/172 are dev-tooling/documentation
  only, each CI-verified at merge), the SBOM status note (point-in-time
  2026-08-23 snapshot, stale w.r.t. the 166/171/172 dev pins, excluded
  from this order, regeneration a release-time maintainer decision),
  and honest limitation statements (mocked-upstream qualification only;
  not a real-provider run, release decision, security certification,
  or production approval). It is dated evidence for the named candidate
  commit only — it must not be phrased as a current-state claim for
  later commits, and no existing `docs/verification/2026-*` file may
  be edited.
- **P6 — Immutable report.** Publish the report per the report
  obligations below, as the report-only final commit.

Known environment-only expectations (label, do not chase):

- The unit suite may fail exactly the known VM-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  because the execution VM runs `codex-cli 0.154.0` against the fixture
  pin `0.148.0` (record `codex --version` as evidence).
- The integration suite may skip exactly the local-VM `pg_dump` case
  (the `TEST_DATABASE_URL` form limitation), identical to the
  167/168/170/172 baseline; in-container backup/restore is re-proven by
  the P2 runs.

Any other non-pass, ERROR, or skip in P0–P3 is a candidate finding and
must be classified with machine evidence (candidate defect / harness-side
/ environment-only with proof), not chased or suppressed.

## Allowed paths

- `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`
  (new dated record)
- `docs/verification/README.md` (one appended index row)
- `oap/orders/173-a-current-main-integrated-requalification-2b61312e.md`
  (unchanged strategic work order)
- `oap/active` (`173-a`)
- `oap/reports/173-a-current-main-integrated-requalification-2b61312e.md`
  (new immutable report)

Nothing else.

## Explicit exclusions (non-goals)

- No code change of any kind: `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, `Dockerfile`, `docker-compose*.yml`,
  `pyproject.toml`, lockfiles, or any other repository file outside the
  allowed paths. This includes `tests/unit/test_oap_governance.py` —
  the governance test and the order template are to be treated as
  stable.
- No defect fixes of any kind. If P0–P4 exposes a candidate-side
  failure, classify and record it with exact evidence and continue the
  remaining safe phases; the verdict must then be
  `RESULT=NOT-QUALIFIED`. Strategy alone decides any follow-up numeric
  objective.
- No SBOM edit or regeneration: `sbom/cyclonedx.json` stays
  byte-identical (see the rationale in the reconciled state).
- No cherry-pick, import, or re-publication of any file from the
  abandoned 169 branch or any other closed/abandoned objective branch.
- No real provider calls: the harness uses only its own socket-level
  `qualification-double` provider; no provider credentials, and
  `RUN_UPSTREAM_TESTS` must remain unset throughout.
- No `--keep` mode; the no-keep cleanup must complete and be evidenced
  in both P2 runs.
- No release, tag, or deployment to any real system; no
  production/staging database; no real email.
- No GitHub-settings action (branch protection, rulesets, required
  checks), no re-opening or modification of any other PR, and no
  Dependabot interaction (PR #224 stays untouched).
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md`; no new tests, fixtures, or harness
  modifications of any kind.
- No new product capability, even if trivially attractive.

## Acceptance criteria

- **AP-0 — Runtime-tree identity.** The report and the dated record
  contain the verbatim P0 outputs, and they match the strategic
  verification (the 12-path diff; the empty runtime-surface list over
  `app/ tests/ scripts/ .github/ migrations/ nginx/ Dockerfile
  docker-compose.yml docker-compose.production.yml Makefile`). Any
  discrepancy makes AP-0 unsatisfied and forces
  `RESULT=NOT-QUALIFIED` with the exact diff recorded.
- **AP-1** — The report and the dated record contain the P2 evidence:
  two consecutive no-keep harness runs from a fresh clean-room checkout
  of the exact PR head with no change between runs; both runs with
  exact `RESULT=OK`, all 16 phases OK, all four exercised metric
  families positive on the single authorized scrape
  (`gateway_http_requests_total`, `gateway_provider_requests_total`,
  `gateway_tokens_total`, `gateway_cost_eur_total`), `restore_counts`
  restored==source, no-keep cleanup all true with empty remaining
  networks/volumes, and `readiness.public_denied: true`. A run of
  `RESULT=FAIL` or of missing/zero positive families makes AP-1
  unsatisfied and forces the `RESULT=NOT-QUALIFIED` verdict with the
  exact failure recorded.
- **AP-2** — Exact P3 matrix counts on the candidate, with every
  non-pass accounted for: the only permitted non-passes are the two
  labeled environment-only items above (each with its recorded proof:
  `codex --version` output; the `pg_dump` skip identity vs the
  167/168/170/172 baseline). E2E must be 54 passed / 0 failed / 0
  skipped under `openai==3.14.1` with the P1 freeze lines recorded.
- **AP-3** — The record contains the P4 CI table: all nine required
  checks `success` on the exact PR head, with run IDs.
- **AP-4** — The dated record exists at the allowed path, names the
  exact candidate SHA `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` in
  its prose, contains exactly one verdict line of the form
  `RESULT=QUALIFIED-RC-POSTURE` or `RESULT=NOT-QUALIFIED`, contains
  the "Relationship to the 170 qualification" note, the SBOM status
  note, and the required limitation sentences. `python
  scripts/check_documentation.py` on the final tree prints
  `DOCUMENTATION_CHECK=OK` (file count grows by exactly one).
- **AP-5** — Diff scope vs base: exactly the five allowed paths; zero
  changes under `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, and zero changes to `Dockerfile`,
  `docker-compose*.yml`, `pyproject.toml`, `sbom/`, or any existing
  documentation file.
- **AP-6** — `RESULT=QUALIFIED-RC-POSTURE` is permitted only when
  AP-0, AP-1, AP-2 (with only the labeled environment-only
  exceptions), and AP-3 all hold as specified; any deviation yields
  `RESULT=NOT-QUALIFIED`. Do not soften, re-label, or average a
  failure; the 151-d/167 boundary-strictness precedent applies.
- **AP-7** — One immutable report
  `oap/reports/173-a-current-main-integrated-requalification-2b61312e.md`
  with the SELF topology: the report commit is the PR head, its first
  parent is the recorded implementation (documentation) head, the
  report commit changes only the report file, the report contains the
  literal candidate SHA and the merge-not-performed statement, and the
  remote PR head is verified as the report commit before the two-byte
  `OK` is written to the response FIFO. The P4 re-query on the final
  head is a mandatory gate before that OK.

## Verification and evidence commands

- P0: the two `git diff` commands recorded verbatim.
- P1: clone + checkout + `git rev-parse HEAD` + `git status --short` +
  `pip freeze` selection.
- P2: `.venv/bin/python scripts/production-qualification/run.py`
  (default no-keep) twice; retain full stdout/stderr files locally and
  cite the exact `RESULT=` lines, project names, and per-family
  evidence in the record and report.
- P3: `scripts/test-unit-parallel.sh`; `python -m pytest
  tests/integration -q` (disposable PG, drop/recreated database);
  `python -m pytest tests/e2e -q` (drop/recreated database);
  `codex --version`; `docker --version`; `docker compose version`.
- P4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs`
  (record the command and run IDs; re-query after the report commit).
- `python scripts/check_documentation.py` (must print
  `DOCUMENTATION_CHECK=OK`).
- `git diff --check`.

## Security, privacy, accounting, and boundaries

- The harness uses only generated credentials and canaries inside the
  disposable Compose project; no real secret, key, prompt, completion,
  or canary value may appear in the record or report (redact any
  disposable password).
- No production/staging system, no real provider, no real email, no
  external call of any kind beyond the local disposable stack and the
  GitHub API for check queries.
- PostgreSQL remains quota/accounting truth; no accounting code,
  schema, or migration is touched by this objective.
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
- If a P0 identity discrepancy appears: do not reconcile it by
  re-basing or any tree surgery; record it and the verdict must be
  `RESULT=NOT-QUALIFIED`.
- If a P4 required check is not `success` on the candidate and the
  cause is not a labeled environment-only item: record it and the
  verdict must be `RESULT=NOT-QUALIFIED`.
- Suffix rounds (`173-b`...) are for bounded correction of this
  objective only, not for scope growth or defect fixing.

## Setup authority

- Fresh clone and venv under `/tmp/obj173-cleanroom/` (disposable;
  remove after the objective).
- Fresh disposable PostgreSQL 16 under `/tmp/obj173-pg/` on
  `127.0.0.1:5433` for the integration suite (stop and remove after).
- Generated credentials only; all harness state inside the disposable
  Compose project, removed by no-keep cleanup.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and
file, PR mode, status, executive summary, authoritative GitHub state
(PR number, URL, state, base/head SHAs, starting remote SHA
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1`, implementation head,
report publication commit `SELF`, merge-not-performed), full
changed-file list, per-AP evidence (including the verbatim P0 diff
outputs, the P2 per-run evidence, the P3 exact counts, and the P4 CI
table with run IDs on the implementation head and the final head),
local verification, negative evidence (no code change, no SBOM edit,
no `--keep` residue, no live provider calls, no secrets, no
release/deploy/GitHub-settings/Dependabot action, no historical-record
or abandoned-branch file imports, no PR #224 or any other PR
modification), CI gate state on the final head, and the
environment-only labels with proofs.

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is
left OPEN for strategic review and the delegated merge authority.
