# OAP Coding-Agent Report — 170-a

## Work order
- Identifier: 170-a
- Work-order file: `oap/orders/170-a-current-main-integrated-requalification.md`
- Numeric objective: 170
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Performed the fresh, verification-only, integrated requalification of the
exact candidate `1043c3f42fb46f06a8d7952273739cefb9de6cc7` (remote
`main`, merge of PR #305 / Objective 168) required by the order, with the
Objective 167/168 determinism property — two consecutive default-no-keep
production-appliance harness runs from a fresh clean-room checkout — as
the decisive test. The objective repeats the abandoned Objective 169
(PR #306, closed unmerged 2026-09-17) against the same candidate, under a
template-conforming work order. No capability was implemented, no defect
was fixed, and no release decision was made.

Verdict: `RESULT=QUALIFIED-RC-POSTURE`. All acceptance predicates hold,
with the complete evidence recorded in the dated record
`docs/verification/2026-09-17-current-main-integrated-requalification.md`:

- **AP-1 — SATISFIED.** Both consecutive no-keep harness runs from the
  fresh clean-room checkout completed with the exact `RESULT=OK` line and
  16/16 phases: Run A (project `slaif-151-1725392-482e3f`) and Run B
  (project `slaif-151-1751638-b838f5`), with no code or environment
  change between the runs. Every AP-1 per-run field holds in both runs:
  all four exercised metric families positive on the single authorized
  scrape, `restore_counts` restored==source (`gateway_keys: 2`,
  `usage_ledger: 15`), no-keep cleanup all true with empty remaining
  networks/volumes, and `readiness.public_denied: true`. Notably, the
  `redis-concurrency` phase completed OK in both runs with
  `recovery_503_count: 0` — the 169 finding P2.3 (transient
  availability-class 503 on the following completion) did not recur.
- **AP-3 — SATISFIED.** All nine required checks `success` on the exact
  PR head, including `Unit, lint, and migration head` — the 169 finding
  P4.1 (candidate governance test failing on the non-template-conforming
  169-a order) does not recur: this order is template-conforming, so the
  governance test passes on the byte-identical committed order.

P3 local matrix (clean-room venv, Python 3.12.3, fresh disposable
PostgreSQL 16 on `127.0.0.1:5433`): unit **4047 passed / 1 failed / 0
skipped** (the single failure is the known VM-only codex-CLI case,
labeled environment-only, `codex --version` = `codex-cli 0.154.0` vs
fixture pin `0.148.0`); integration **224 passed / 1 skipped / 0 failed**
(the skip is the local-VM `pg_dump` CLI limitation on the
`TEST_DATABASE_URL` form, labeled environment-only, identical to the
167/168/169 baseline); official-client E2E **54 passed / 0 failed / 0
skipped** under `openai==3.9.0`. Zero product behavior, accounting,
routing, policy, or compatibility change; the `/metrics` authentication
policy is verified unchanged via `readiness.public_denied` in both P2
runs.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 307
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/307
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/170-current-main-integrated-requalification`
- Starting remote SHA: `1043c3f42fb46f06a8d7952273739cefb9de6cc7`
- Implementation head SHA: `8914ad41aa91c4a5de92eb8282ae5c2c917d297e`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from
  GitHub)
- Implementation commits pushed before the report commit:
    - `40984390e9c5564694ff6c84a4c443c39ec510b2` `oap: activate 170-a current main integrated requalification` (carries the strategic-authored order and `oap/active`)
    - `8914ad41aa91c4a5de92eb8282ae5c2c917d297e` `obj170: fresh integrated requalification of current main for RC posture` (carries the dated record and the single README index row)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `docs/verification/2026-09-17-current-main-integrated-requalification.md`
  (new dated record): candidate SHA, single verdict line
  `RESULT=QUALIFIED-RC-POSTURE`, complete P1–P4 evidence (P1 clean-room
  proof and freeze; P2 two consecutive `RESULT=OK` 16/16 runs with all
  AP-1 fields; P3 exact matrix counts; P4 candidate 9/9 and PR-head 9/9
  CI tables), the required "Relationship to the abandoned 169 attempt"
  note, deployment-path statement, and the required limitation
  sentences.
- `docs/verification/README.md`: exactly one appended index row for the
  new record.
- `oap/orders/170-a-current-main-integrated-requalification.md`:
  strategic work order committed unchanged (byte-identical strategic
  bytes; template-conforming, `PR mode: `CREATE_NEW_PR`` literal on line
  3).
- `oap/active`: `170-a` (activated order pointer).
- `oap/reports/170-a-current-main-integrated-requalification.md`: this
  report (report-only commit).

Not touched (verified by diff scope, AP-5): everything outside the five
allowed paths — in particular zero changes under `app/`, `tests/`,
`scripts/` (including the entire production-qualification harness),
`.github/`, `migrations/`, `nginx/`, `Dockerfile`, `docker-compose*.yml`,
`pyproject.toml`, and all existing `docs/verification/2026-*` files and
`docs/beta-readiness.md`.

## Files changed (full, including the report commit)
- `docs/verification/2026-09-17-current-main-integrated-requalification.md`
- `docs/verification/README.md`
- `oap/orders/170-a-current-main-integrated-requalification.md`
- `oap/active`
- `oap/reports/170-a-current-main-integrated-requalification.md`

`git diff --name-only 1043c3f42fb46f06a8d7952273739cefb9de6cc7
8914ad41aa91c4a5de92eb8282ae5c2c917d297e` lists exactly the first four
paths (the report file appears only in the report commit); nothing else.

## Acceptance-criteria evidence
- **AP-1 — SATISFIED.** Two consecutive no-keep harness runs on the exact
  candidate `1043c3f42fb46f06a8d7952273739cefb9de6cc7` from the fresh
  clean-room checkout `/tmp/obj170-cleanroom/` (fresh venv, command
  `.venv/bin/python scripts/production-qualification/run.py`, default
  no-keep, no code/environment change between the runs):
  - Run A: project `slaif-151-1725392-482e3f`, exact output line
    `RESULT=OK`, 16/16 phases OK (prepare 0.48s; tls 0.25s; compose
    37.29s; operator-configuration 27.43s;
    async-worker-and-scheduler-liveness 5.87s; chat-and-responses 1.97s;
    provider-failures-and-disconnects 2.09s; redis-and-timeout-controls
    13.9s; redis-concurrency 8.99s;
    api-termination-and-cli-reconciliation 20.81s; persistence 45.39s;
    backup-restore 11.09s; privacy-input-boundaries 0.59s;
    quota-and-key-controls 7.73s; admin-dashboard-session 0.39s; privacy
    33.02s), `metrics.positive_sample_present` all four families `true`
    (`gateway_http_requests_total`,
    `gateway_provider_requests_total`, `gateway_tokens_total`,
    `gateway_cost_eur_total`), `restore_counts` restored==source
    (`gateway_keys: 2`, `usage_ledger: 15`), no-keep cleanup all true
    (`containers_by_compose_label`, `networks`, `runtime`, `volumes` all
    `true`; `remaining_networks: []`, `remaining_volumes: []`),
    `readiness.public_denied: true`, readiness pattern
    (`initial_startup`/`api_restart`/`api_recreation`/
    `postgres_api_recreation` each 4 consecutive 200s; `redis_outage`
    503/`not_ready`; `redis_recovery` 4 consecutive 200s), concurrency
    evidence (`overlap_status: 429`
    `concurrency_rate_limit_exceeded`, `overlap_provider_forward_delta:
    0`, `following_status: 200`, `recovery_503_count: 0`, slot
    released), 16-row accounting lifecycle (9 `finalized`, 5 `failed`
    with reservation `released` including one 503 provider-failure
    sample, 2 `estimated`; `api-termination` terminal sample
    `failed`/`expired`, provider count stable, restart ready).
  - Run B: project `slaif-151-1751638-b838f5`, exact output line
    `RESULT=OK`, 16/16 phases OK (prepare 0.07s; tls 0.27s; compose
    34.11s; operator-configuration 27.4s;
    async-worker-and-scheduler-liveness 5.95s; chat-and-responses 2.01s;
    provider-failures-and-disconnects 2.76s; redis-and-timeout-controls
    12.8s; redis-concurrency 9.13s;
    api-termination-and-cli-reconciliation 21.39s; persistence 48.01s;
    backup-restore 12.87s; privacy-input-boundaries 0.59s;
    quota-and-key-controls 8.07s; admin-dashboard-session 0.4s; privacy
    33.14s), with every AP-1 per-run field holding as in Run A (all four
    metric families positive; `restore_counts` restored==source;
    no-keep cleanup all true with empty remaining networks/volumes;
    `readiness.public_denied: true` with the same readiness pattern;
    concurrency `overlap_status: 429` / `following_status: 200` /
    `recovery_503_count: 0` / slot released; 16-row accounting lifecycle
    with the same shape, including one 503 provider-failure sample and
    the `api-termination` terminal sample `failed`/`expired`).
  - Full stdout/stderr captured locally at
    `/tmp/obj170-harness-runA.log` and `/tmp/obj170-harness-runB.log`
    (local artifacts, not committed).
- **AP-2 — SATISFIED** (exact P3 matrix counts, every non-pass
  accounted for; only the two labeled environment-only items):
  - Unit: `scripts/test-unit-parallel.sh`
    (`.venv/bin/python -m pytest tests/unit -n 20 --dist loadscope`):
    **4047 passed / 1 failed / 0 skipped** in 73.05s. The single failure
    is the known VM-only case
    `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
    (`codex_version_mismatch`); recorded proof: `codex --version` →
    `codex-cli 0.154.0` (fixture pin `codex-cli 0.148.0`),
    environment-only per the order, not chased.
  - Integration: `.venv/bin/python -m pytest tests/integration -q` with
    `TEST_DATABASE_URL` on the fresh user-owned disposable PostgreSQL 16
    (16.15) at `127.0.0.1:5433` (database dropped/recreated immediately
    before the run): **224 passed / 1 skipped / 0 failed**. Recorded
    proof of the skip's identity:
    `tests/integration/test_backup_restore_postgres.py:42` (skip reason
    "pg_dump unavailable or incompatible" — pg_dump rejects the
    `postgresql+asyncpg` DSN form and falls back to the default socket),
    identical to the 167/168/169 baseline; in-container backup/restore
    re-proven in both P2 runs. The captured log's final summary line was
    lost to a tee/pipe flush race; counts are the exact tally of the
    225-character pytest progress line (224 pass dots + 1 skip, zero
    fail/error markers).
  - E2E: `.venv/bin/python -m pytest tests/e2e -q` on a drop/recreated
    database: **54 passed / 0 failed / 0 skipped** under
    `openai==3.9.0` (54-test official-client matrix; same progress-line
    tally: 54 dots, no skip/fail markers).
  - P1 freeze proof (clean-room venv, Python 3.12.3):
    `openai==3.9.0`, `httpx==0.28.1`, `httpx2==2.13.0`,
    `httpcore2==2.13.0`, `httpcore==1.0.9`, `pydantic==2.13.5`,
    `respx==0.23.1`, `pytest==9.1.1`, `prometheus_client==0.26.0`,
    `gunicorn==26.2.0`, `uvicorn==0.53.0`, `fastapi==0.141.1`,
    `starlette==1.6.0`.
- **AP-3 — SATISFIED** (record contains the exact CI tables). Candidate
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` main-branch checks, all
  nine required `completed`/`success` (re-queried live against the
  GitHub API on 2026-09-17): `Unit, lint, and migration head`
  105183932538; `Documentation hygiene` 105183932519;
  `OpenAI-compatible E2E tests` 105183932313; `Playwright browser
  smoke` 105183932551; `Docker Compose smoke` 105183932688;
  `PostgreSQL integration tests` 105183932545; `Analyze
  (javascript-typescript)` 105183936436; `Analyze (python)`
  105183936672; `Analyze Python` 105183932867. Exact PR head as of the
  record (`40984390e9c5564694ff6c84a4c443c39ec510b2`): all nine
  required checks `completed`/`success` — `Unit, lint, and migration
  head` 105227348777; `Documentation hygiene` 105227349008;
  `OpenAI-compatible E2E tests` 105227349239; `Playwright browser
  smoke` 105227349007; `Docker Compose smoke` 105227349093;
  `PostgreSQL integration tests` 105227349303; `Analyze
  (javascript-typescript)` 105227341951; `Analyze (python)`
  105227341510; `Analyze Python` 105227348747. `Unit, lint, and
  migration head` is `success` on the PR head because this order is
  template-conforming, so the candidate's governance test
  `tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`
  passes on the byte-identical committed order — the 169 finding P4.1
  does not recur.
- **AP-4 — SATISFIED.** The dated record exists at the allowed path,
  names the exact candidate SHA
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` in its prose, contains
  exactly one verdict line `RESULT=QUALIFIED-RC-POSTURE`, contains the
  required "Relationship to the abandoned 169 attempt" note (same
  candidate; 169's P2.3 transient 503 and P4.1 order-format finding as
  recorded on the abandoned branch), and states the required limitation
  sentences (mocked-upstream qualification only; not a real-provider
  run, release decision, security certification, or production
  approval; dated evidence for the named candidate commit only).
  `python scripts/check_documentation.py` on the final tree prints
  `DOCUMENTATION_CHECK=OK files=82` (one more than the base tree, for
  the new dated record).
- **AP-5 — SATISFIED.** Diff scope vs base
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`: exactly the five allowed
  paths; zero changes under `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, and zero changes to `Dockerfile`,
  `docker-compose*.yml`, `pyproject.toml`, or any existing
  documentation file.
- **AP-6 — SATISFIED as specified.** `RESULT=QUALIFIED-RC-POSTURE` is
  permitted because AP-1, AP-2 (with only the two labeled
  environment-only exceptions), and AP-3 all hold as specified; no
  predicate was softened, re-labeled, or averaged.
- **AP-7 — SATISFIED.** This immutable report contains the literal
  candidate SHA `1043c3f42fb46f06a8d7952273739cefb9de6cc7` and
  `Report publication commit: SELF`; the report-only commit changes only
  `oap/reports/170-a-current-main-integrated-requalification.md`, has the
  recorded implementation head as first parent, and is pushed and
  verified as the remote PR head before the two-byte `OK` is written to
  the response FIFO. The P4 re-query on the final head is performed as
  the mandatory gate before that OK (see CI gate state).

## Local verification (clean-room venv, clean-room tree unless noted)
- Clean room: `/tmp/obj170-cleanroom/` detached checkout of
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`, `git status --short`
  empty, fresh `.venv` (Python 3.12.3; freeze lines in AP-2). All P2/P3
  candidate code ran from the clean room only.
- P2: `.venv/bin/python scripts/production-qualification/run.py` twice
  consecutively (default no-keep), full stdout/stderr captured at
  `/tmp/obj170-harness-runA.log` (`RESULT=OK`) and
  `/tmp/obj170-harness-runB.log` (`RESULT=OK`).
- P3: `scripts/test-unit-parallel.sh` (log `/tmp/obj170-p3-unit.log`);
  `.venv/bin/python -m pytest tests/integration -q` (log
  `/tmp/obj170-p3-integration.log`, fresh disposable PG on
  `127.0.0.1:5433`); `.venv/bin/python -m pytest tests/e2e -q` (log
  `/tmp/obj170-p3-e2e.log`, drop/recreated database); `codex
  --version` → `codex-cli 0.154.0` (recorded only to label the known
  VM-only unit failure; output at `/tmp/obj170-codex-version.txt`).
- P4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<sha>/check-runs` for the
  candidate, the activation head, and the implementation head (run IDs
  above and in the record); final-head re-query after the report-only
  commit per AP-7 (mandatory gate; see CI gate state).
- Documentation gates on the final tree: `python
  scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=82`;
  `git diff --check` → clean.
- Environment-only disclosures (record P1 notes): local `psql` TCP
  password authentication to the disposable cluster misbehaves
  client-side on this VM while socket authentication and asyncpg (the
  suites' client) TCP authentication succeeded for the disposable role
  on `127.0.0.1:5433`; classified client-side/environment-only. The two
  stray read-only `find /` diagnostic scans left over from the 169
  attempt were confirmed terminated before P2 Run B of this attempt
  (process check clean).

## Negative evidence
- No code change of any kind: the implementation diff touches only the
  documentation paths plus the strategic order and `oap/active`; zero
  product behavior, accounting, routing, policy, pricing,
  compatibility, authentication, error-shape, schema, or migration
  change; the production-qualification harness and
  `tests/unit/test_oap_governance.py` are byte-identical to the
  candidate (untouched); PostgreSQL remains quota/accounting truth
  (untouched).
- No defect fixes: this objective produced no candidate-side finding to
  fix; the only non-passes are the two labeled environment-only items
  (recorded, not chased, not suppressed).
- No `--keep` residue: no `--keep` run was performed; both P2 runs used
  default no-keep mode; post-run verification found no leftover harness
  containers, networks, or volumes (`remaining_networks: []`,
  `remaining_volumes: []` in both runs).
- No live provider calls: `RUN_UPSTREAM_TESTS` unset throughout; no
  provider credentials present or used; the harness's socket-level
  `qualification-double` provider only.
- No secrets in artifacts: the record and this report contain no
  generated secret, key, password, prompt, completion, or canary value
  (the disposable PostgreSQL password is redacted); only safe booleans,
  counts, timings, project names, SHAs, and CI run IDs are recorded.
- No release, tag, or deployment to any real system; no
  production/staging database; no real email; no GitHub-settings
  action; no Dependabot interaction. Open PRs #250 and #224 remain
  untouched. PR #306 (abandoned Objective 169) was not re-opened or
  modified in any way.
- No cherry-pick, import, or re-publication of any file from the
  abandoned 169 branch: its dated record and report remain on branch
  `oap/169-current-main-integrated-requalification` only; this record
  was freshly authored (the 169 record's filename was free because that
  file is not on `main`). No edits to any existing
  `docs/verification/2026-*` file or to `docs/beta-readiness.md`.

## CI gate state on the final head
- Implementation head `8914ad41aa91c4a5de92eb8282ae5c2c917d297e` (first
  parent of the final report-only head, which adds only this report
  file and touches no code, workflow, or configuration path covered by
  any check): all nine required checks SUCCESS — `Unit, lint, and
  migration head` 105230251209; `Documentation hygiene` 105230251168;
  `OpenAI-compatible E2E tests` 105230251397; `Playwright browser
  smoke` 105230252051; `Docker Compose smoke` 105230250797;
  `PostgreSQL integration tests` 105230251201; `Analyze
  (javascript-typescript)` 105230235596; `Analyze (python)`
  105230235139; `Analyze Python` 105230250684. Per AP-7, the final
  head's check runs are re-queried after publication of the report-only
  commit, and that re-query is a mandatory gate before the response-FIFO
  `OK` signal is sent (a report commit cannot carry the run IDs of its
  own commit; the re-query result is part of this objective's execution
  record and is independently re-verified on GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #307 was left OPEN for strategic
review and the human maintainer's delegated merge authority; no merge
was performed, and no merge-related GitHub action of any kind was taken
by this objective.
