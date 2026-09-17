# OAP Coding-Agent Report — 169-a

## Work order
- Identifier: 169-a
- Work-order file: `oap/orders/169-a-current-main-integrated-requalification.md`
- Numeric objective: 169
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Performed the fresh, verification-only, integrated requalification of the
exact candidate `1043c3f42fb46f06a8d7952273739cefb9de6cc7` (remote
`main`, merge of PR #305 / Objective 168) required by the order, with the
Objective 167/168 determinism property — two consecutive default-no-keep
production-appliance harness runs from a fresh clean-room checkout — as
the decisive test. No capability was implemented, no defect was fixed,
and no release decision was made.

Verdict: `RESULT=NOT-QUALIFIED`, driven by two independent
acceptance-predicate failures, both recorded with exact machine evidence
in the dated record
`docs/verification/2026-09-17-current-main-integrated-requalification.md`:

- **Finding F1 (record P2.3) — AP-1 unsatisfied.** P2 Run A (project
  `slaif-151-1646010-cf7e04`) completed 16/16 phases `RESULT=OK` with all
  four exercised metric families positive, restore restored==source
  (`gateway_keys: 2`, `usage_ledger: 15`), no-keep cleanup all true with
  empty remaining networks/volumes, and `readiness.public_denied: true`.
  The consecutive Run B (project `slaif-151-1670026-685592`) failed at
  phase 9 `redis-concurrency` with
  `ERROR=/v1/chat/completions returned 503, expected [200]` — the phase's
  following chat completion after verified overlap validation, first-stream
  200 termination, accounting finalization, and slot release. Classified:
  non-deterministic transient 503 of the availability class (candidate
  503 paths for a plain free-slot request are the fail-closed Redis
  rate-limit path `redis_rate_limit_unavailable` or a provider error
  passthrough); the same phase passed 168 Run A, 168 Run B (which
  absorbed one recovered 503, `recovery_503_count: 1`) and 169 Run A;
  host evidence for the fail window shows no OOM/pressure/container
  crash; the in-container logs of the failed project were removed by the
  mandatory no-keep cleanup, so root-cause attribution is not conclusive.
  Not a harness-side error; not a labeled environment-only expectation.
  A single `RESULT=FAIL` among the two required consecutive runs makes
  AP-1 unsatisfied and forces the not-qualified verdict (151-d/167
  boundary-strictness precedent).
- **Finding F2 (record P4.1) — AP-3 unsatisfied.** The PR head's
  `Unit, lint, and migration head` check run (`105205788307` on
  `4f84575f092119dba469dc36bdb3dfc44f7080ab`) concluded `failure` on the
  candidate's own governance test
  `tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`
  (`1 failed, 4046 passed, 1 skipped`), which asserts the literal
  `PR mode: \`CREATE_NEW_PR\`` in the active `-a` work order. The
  strategic-authored 169-a order — which the order's PR contract requires
  committing byte-identical — uses a `## PR contract` section and omits
  the literal; the durable protocol mandates no such literal in orders
  (its only `PR mode` occurrence is the report field
  `PR mode: CREATED_NEW_PR | AMENDED_EXISTING_PR`). Classified:
  candidate-side governance-test brittleness (third manifestation of the
  Objective 001/001-b literal-phrase assertion class; the 001-b repair
  relaxed only the one-new-PR invariant). Not a candidate-main regression:
  the candidate's own main-branch checks are 9/9 `success`.

P3 local matrix (clean-room venv, Python 3.12.3, disposable PostgreSQL 16
on `127.0.0.1:5433`): unit **4047 passed / 1 failed / 0 skipped**
(68.75s; the single failure is the known VM-only codex-CLI case, labeled
environment-only, `codex --version` = `codex-cli 0.154.0` vs fixture pin
`0.148.0`); integration **224 passed / 1 skipped / 0 failed** (the skip is
the local-VM `pg_dump` CLI limitation on the `TEST_DATABASE_URL` form,
identical to the 167/168 baseline); official-client E2E **54 passed / 0
failed / 0 skipped** under `openai==3.9.0`. Zero product behavior,
accounting, routing, policy, or compatibility change; the `/metrics`
authentication policy is verified unchanged via `readiness.public_denied`
in both P2 runs. Whether either finding warrants a new numeric objective
is a strategy decision.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 306
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/306
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/169-current-main-integrated-requalification`
- Starting remote SHA: `1043c3f42fb46f06a8d7952273739cefb9de6cc7`
- Implementation head SHA: c34525069728e54b367f27fa3c213129686c318b
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
    - `4f84575f092119dba469dc36bdb3dfc44f7080ab` `oap: activate 169-a current main integrated requalification` (carries the strategic-authored order and `oap/active`)
    - `c34525069728e54b367f27fa3c213129686c318b` `obj169: fresh integrated requalification of current main for RC posture` (carries the dated record and the single README index row)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `docs/verification/2026-09-17-current-main-integrated-requalification.md`
  (new dated record): candidate SHA, single verdict line
  `RESULT=NOT-QUALIFIED`, complete P1–P4 evidence including the two
  findings (P2.3, P4.1), exact CI tables (candidate 9/9; PR head 8/9 +
  the governance-test failure), deployment-path statement, and the
  required limitation sentences.
- `docs/verification/README.md`: exactly one appended index row for the
  new record.
- `oap/orders/169-a-current-main-integrated-requalification.md`:
  strategic work order committed unchanged (byte-identical strategic
  bytes).
- `oap/active`: `169-a` (activated order pointer).
- `oap/reports/169-a-current-main-integrated-requalification.md`: this
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
- `oap/orders/169-a-current-main-integrated-requalification.md`
- `oap/active`
- `oap/reports/169-a-current-main-integrated-requalification.md`

`git diff --name-only 1043c3f42fb46f06a8d7952273739cefb9de6cc7
<implementation-head>` lists exactly the first four paths (the report
file appears only in the report commit); nothing else.

## Acceptance-criteria evidence
- **AP-1 — NOT SATISFIED** (recorded with the exact failure). Two
  consecutive no-keep harness runs on the exact candidate
  (`1043c3f42fb46f06a8d7952273739cefb9de6cc7`) from the fresh clean-room
  checkout `/tmp/obj169-cleanroom/` (fresh venv, command
  `.venv/bin/python scripts/production-qualification/run.py`, default
  no-keep, no code/environment change between the runs):
  - Run A: project `slaif-151-1646010-cf7e04`, exact output line
    `RESULT=OK`, 16/16 phases OK (prepare 0.47s; tls 0.52s; compose
    37.81s; operator-configuration 27.60s;
    async-worker-and-scheduler-liveness 5.95s; chat-and-responses 1.99s;
    provider-failures-and-disconnects 2.80s; redis-and-timeout-controls
    11.74s; redis-concurrency 9.08s;
    api-termination-and-cli-reconciliation 20.25s; persistence 45.36s;
    backup-restore 10.79s; privacy-input-boundaries 0.57s;
    quota-and-key-controls 7.87s; admin-dashboard-session 0.30s; privacy
    32.98s), `metrics.positive_sample_present` all four families `true`
    (`gateway_http_requests_total`,
    `gateway_provider_requests_total`, `gateway_tokens_total`,
    `gateway_cost_eur_total`), `restore_counts` restored==source
    (`gateway_keys: 2`, `usage_ledger: 15`), no-keep cleanup all true
    (`containers_by_compose_label`, `networks`, `runtime`, `volumes` all
    `true`; `remaining_networks: []`, `remaining_volumes: []`),
    `readiness.public_denied: true`, concurrency evidence
    (`overlap_status: 429` `concurrency_rate_limit_exceeded`,
    `following_status: 200`, `recovery_503_count: 0`, slot released).
  - Run B: project `slaif-151-1670026-685592`, exact output lines
    `RESULT=FAIL` /
    `ERROR=/v1/chat/completions returned 503, expected [200]`; phases
    1–8 OK (prepare 0.07s; tls 0.29s; compose 33.69s;
    operator-configuration 27.38s; async-worker-and-scheduler-liveness
    5.93s; chat-and-responses 1.98s;
    provider-failures-and-disconnects 2.79s; redis-and-timeout-controls
    11.71s), phase 9 `redis-concurrency` FAIL (8.99s), phases 10–16 not
    reached; no-keep cleanup after the failure all true with empty
    remaining networks/volumes. The failing request was the phase's
    following chat completion (the phase's only `expect={200}`
    assertion) after every preceding precondition had passed;
    classification with machine evidence in record P2.3.
  - Full stdout/stderr captured locally at
    `/tmp/obj169-harness-runA.log` and `/tmp/obj169-harness-runB.log`
    (local artifacts, not committed).
  Consequence per the order: `RESULT=FAIL` on a required run makes AP-1
  unsatisfied and forces `RESULT=NOT-QUALIFIED`.
- **AP-2 — SATISFIED** (exact P3 matrix counts, every non-pass
  accounted for; only the two labeled environment-only items):
  - Unit: `scripts/test-unit-parallel.sh`
    (`.venv/bin/python -m pytest tests/unit -n 20 --dist loadscope`):
    **4047 passed / 1 failed / 0 skipped** in 68.75s. The single failure
    is the known VM-only case
    `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`;
    recorded proof: `codex --version` → `codex-cli 0.154.0` (fixture pin
    `codex-cli 0.148.0`), environment-only per the order, not chased.
  - Integration: `.venv/bin/python -m pytest tests/integration -q` with
    `TEST_DATABASE_URL` on the user-owned disposable PostgreSQL 16 at
    `127.0.0.1:5433` (database dropped/recreated immediately before the
    run): **224 passed / 1 skipped / 0 failed**. Recorded proof of the
    skip's identity: `tests/integration/test_backup_restore_postgres.py:42`
    (`pg_dump` unavailable or incompatible with the `TEST_DATABASE_URL`
    form), identical to the 167/168 baseline; in-container backup/restore
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
- **AP-3 — NOT SATISFIED** (recorded with the exact CI state). Candidate
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` main-branch checks, all nine
  required `completed`/`success`: `Unit, lint, and migration head`
  105183932538; `Documentation hygiene` 105183932519; `OpenAI-compatible
  E2E tests` 105183932313; `Playwright browser smoke` 105183932551;
  `Docker Compose smoke` 105183932688; `PostgreSQL integration tests`
  105183932545; `Analyze (javascript-typescript)` 105183936436;
  `Analyze (python)` 105183936672; `Analyze Python` 105183932867.
  Exact PR head (`4f84575f092119dba469dc36bdb3dfc44f7080ab`): eight of
  nine required checks `completed`/`success` (`Documentation hygiene`
  105205788004; `OpenAI-compatible E2E tests` 105205788166; `Docker
  Compose smoke` 105205788251; `Playwright browser smoke` 105205788304;
  `PostgreSQL integration tests` 105205788492; `Analyze
  (javascript-typescript)` 105205786791; `Analyze (python)`
  105205787132; `Analyze Python` 105205788690); `Unit, lint, and
  migration head` 105205788307 `completed`/`failure` with the exact
  failing assertion recorded in P4.1 (workflow run `35222480268`,
  `1 failed, 4046 passed, 1 skipped`). The candidate main passes the same
  check, so this is the brittle-test/border-order-content interaction,
  not a main regression. AP-3's nine-success requirement on the exact PR
  head is therefore unsatisfied, independently forcing
  `RESULT=NOT-QUALIFIED`.
- **AP-4 — SATISFIED.** The dated record exists at the allowed path,
  names the exact candidate SHA
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` in its prose, contains
  exactly one verdict line `RESULT=NOT-QUALIFIED`, and states the
  required limitation sentences (mocked-upstream qualification only; not
  a real-provider run, release decision, security review, compliance
  finding, or production approval; dated evidence for the named
  candidate commit only). `python scripts/check_documentation.py` on the
  final tree prints `DOCUMENTATION_CHECK=OK files=82` on the final tree (one
  more than the base tree, for the new dated record).
- **AP-5 — SATISFIED.** Diff scope vs base
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`: exactly the five allowed
  paths; zero changes under `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, and zero changes to `Dockerfile`,
  `docker-compose*.yml`, `pyproject.toml`, or any existing
  documentation file.
- **AP-6 — SATISFIED as specified.** `RESULT=QUALIFIED-RC-POSTURE` was
  not permitted because AP-1 (one `RESULT=FAIL` P2 run) and AP-3 (one
  failed PR-head check) do not hold as specified; the verdict
  `RESULT=NOT-QUALIFIED` is issued with both failures recorded exactly,
  per the 151-d/167 boundary-strictness precedent (no softening,
  re-labeling, or averaging).
- **AP-7 — SATISFIED.** This immutable report contains the literal
  candidate SHA `1043c3f42fb46f06a8d7952273739cefb9de6cc7` and
  `Report publication commit: SELF`; the report-only commit changes only
  `oap/reports/169-a-current-main-integrated-requalification.md`, has the
  recorded implementation head as first parent, and is pushed and
  verified as the remote PR head before the two-byte `OK` is written to
  the response FIFO. The P4 re-query on the final head was performed as
  the mandatory gate before that OK (see CI gate state).

## Local verification (clean-room venv, clean-room tree unless noted)
- Clean room: `/tmp/obj169-cleanroom/` detached checkout of
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`, `git status --short`
  empty, fresh `.venv` (Python 3.12.3; freeze lines in AP-2). All P2/P3
  candidate code ran from the clean room only.
- P2: `.venv/bin/python scripts/production-qualification/run.py` twice
  consecutively (default no-keep), full stdout/stderr captured at
  `/tmp/obj169-harness-runA.log` (`RESULT=OK`) and
  `/tmp/obj169-harness-runB.log` (`RESULT=FAIL`).
- P3: `scripts/test-unit-parallel.sh` (log `/tmp/obj169-p3-unit.log`);
  `.venv/bin/python -m pytest tests/integration -q` (log
  `/tmp/obj169-p3-integration.log`, disposable PG on `127.0.0.1:5433`);
  `.venv/bin/python -m pytest tests/e2e -q` (log
  `/tmp/obj169-p3-e2e.log`, drop/recreated database);
  `codex --version` → `codex-cli 0.154.0` (only to label the known
  VM-only unit failure).
- P4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<sha>/check-runs` for the
  candidate and the PR head (run IDs above); final-head re-query after
  the report-only commit per AP-7 (mandatory gate; see CI gate state).
- Documentation gates on the final tree: `python
  scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK`;
  `git diff --check` → clean.
- Environment-only disclosures (record P1 notes): two stray read-only
  `find /` diagnostic scans (leftover from an earlier local
  investigation) ran during P2/P3 with negligible CPU, no memory
  pressure (PSI zero, no OOM in dmesg), and were present in both harness
  runs (common factor, not a discriminator); terminated after P3. Local
  `psql` TCP password authentication misbehaved all turn while asyncpg
  (the suites' client) TCP authentication succeeded for both disposable
  roles on `127.0.0.1:5433`; classified client-side/environment-only and
  recorded in P1.

## Negative evidence
- No code change of any kind: the implementation diff touches only the
  two documentation paths plus the strategic order and `oap/active`;
  zero product behavior, accounting, routing, policy, pricing,
  compatibility, authentication, error-shape, schema, or migration
  change; the production-qualification harness is byte-identical to the
  candidate (untouched); PostgreSQL remains quota/accounting truth
  (untouched).
- No defect fixes: both findings (F1, F2) are recorded and classified,
  not fixed; no test, fixture, harness, or code modification of any
  kind.
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
  untouched.
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md`; the new record is an additional dated
  evidence file for the named candidate only.

## CI gate state on the final head
- Implementation head `c34525069728e54b367f27fa3c213129686c318b` (first
  parent of the final report-only head, which adds only this report
  file and touches no code, workflow, or configuration path covered by
  any check): eight of the nine required checks SUCCESS —
  `Documentation hygiene` 105208586399; `OpenAI-compatible E2E tests`
  105208586604; `Docker Compose smoke` 105208587052; `Playwright
  browser smoke` 105208586816; `PostgreSQL integration tests`
  105208586832; `Analyze (javascript-typescript)` 105208576869;
  `Analyze (python)` 105208576672; `Analyze Python` 105208585774 — and
  `Unit, lint, and migration head` 105208586801 FAILURE, on the same
  candidate-side governance-test literal-phrase assertion documented in
  P4.1 (confirmed identical on the implementation head: workflow run
  `35223323326`, `1 failed, 4046 passed, 1 skipped`, same assertion
  `assert 'PR mode: `CREATE_NEW_PR`' in <order text>`; the report
  commit cannot change the test's input: `oap/active` and the
  byte-identical order are unchanged). Per AP-7, the final head's check
  runs are re-queried after publication of the report-only commit, and
  that re-query is a mandatory gate before the response-FIFO `OK`
  signal is sent (a report commit cannot carry the run IDs of its own
  commit; the re-query result is part of this objective's execution
  record and is independently re-verified on GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #306 was left OPEN for strategic
review and the human maintainer's delegated merge authority; no merge
was performed, and no merge-related GitHub action of any kind was taken
by this objective.
