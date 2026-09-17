# Objective 170 current-main integrated requalification

Date: 2026-09-17 (Europe/Ljubljana; UTC timestamps as recorded by the runs)

Candidate (evidence boundary): `main`
`1043c3f42fb46f06a8d7952273739cefb9de6cc7` (merge of PR #305 / Objective
168), verified remote `main` at execution time.

This is a fresh, verification-only, integrated requalification of that exact
candidate for the intended RC/deployment posture, with the Objective
167/168 determinism property — two consecutive default-no-keep
production-appliance harness runs from a fresh clean-room checkout, both
`RESULT=OK` — as the decisive test. It repeats the abandoned Objective 169
(PR #306, closed unmerged on 2026-09-17) against the same candidate, under
a template-conforming work order. It implements no capability, fixes
nothing, and makes no release decision. All candidate code was executed
only from the clean-room clone (P1); nothing was executed from the shared
worktree. No file from the abandoned 169 branch was imported,
cherry-picked, or re-published; that branch's dated record and report
remain on that branch only. The historical record
[`2026-09-17-current-main-integrated-qualification.md`](2026-09-17-current-main-integrated-qualification.md)
(Objective 167, `RESULT=NOT-QUALIFIED`) and the Objective 168 report are
immutable and are referenced, not rewritten.

## Verdict

`RESULT=QUALIFIED-RC-POSTURE`

Two consecutive default-no-keep production-appliance harness runs from a
fresh clean-room checkout of the exact candidate — Run A (project
`slaif-151-1725392-482e3f`) and Run B (project
`slaif-151-1751638-b838f5`), with no code or environment change between
the runs — each completed with the exact `RESULT=OK` line, 16/16 phases
OK, all four exercised metric families positive on the single authorized
scrape, `restore_counts` restored==source, no-keep cleanup all true with
empty remaining networks/volumes, and `readiness.public_denied: true`
(AP-1). The P3 matrix matched the exact expected counts with only the two
labeled environment-only non-passes (AP-2), and all nine required checks
concluded `success` on the exact PR head (AP-3; table in P4). AP-6
therefore permits the qualified verdict. No code was modified.

## P1 — Clean-room candidate

- Fresh full clone: `/tmp/obj170-cleanroom/`, detached checkout of
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`.
- `git rev-parse HEAD` = candidate SHA; `git status --short` empty.
- Fresh venv at `/tmp/obj170-cleanroom/.venv` (Python 3.12.3) with `.[dev]`
  installed.
- Freeze lines (P1 install):

```text
openai==3.9.0
httpx==0.28.1
httpx2==2.13.0
httpcore2==2.13.0
httpcore==1.0.9
pydantic==2.13.5
respx==0.23.1
pytest==9.1.1
prometheus_client==0.26.0
gunicorn==26.2.0
uvicorn==0.53.0
fastapi==0.141.1
starlette==1.6.0
```

Environment: Linux WSL2 VM (24 visible cores), Docker 29.1.3, Docker
Compose 2.40.3, fresh user-owned disposable PostgreSQL 16 (16.15)
instance at `127.0.0.1:5433` for P3 (fresh `initdb` under
`/tmp/obj170-pg/`; own roles/database; the database was dropped/recreated
immediately before each DB-backed suite; the 5432 system cluster was not
used), host Redis at `127.0.0.1:6379`. `RUN_UPSTREAM_TESTS` unset
throughout; no provider credentials present or used;
`ENABLE_EMAIL_DELIVERY=false`; `DATABASE_URL`, `TEST_REDIS_URL`, and all
upstream key variables explicitly unset from the run environments.

Environment notes (honesty disclosures, no effect on the evidence chain):

- Local `psql` TCP password authentication to the disposable cluster
  misbehaves client-side on this VM, while socket authentication and —
  decisively — asyncpg (the client the suites use) TCP authentication
  succeeded for the disposable role on `127.0.0.1:5433` (fresh
  `asyncpg.connect` `AUTH_OK` before P3, and all three DB-backed suites
  completed end-to-end over that path). Classified as a
  client-side/environment-only local psql/libpq quirk; the database path
  actually used by the test suites was verified end-to-end.
- The two read-only diagnostic `find /` scans left over from the 169
  attempt on this VM were confirmed terminated before P2 Run B of this
  attempt (process check clean at that point).

## P2 — Production-appliance qualification

Command (run twice consecutively from the clean-room tree, default
no-keep mode, no code or environment change between the runs):

```text
env -u DATABASE_URL -u TEST_REDIS_URL -u RUN_UPSTREAM_TESTS \
    -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY \
    ENABLE_EMAIL_DELIVERY=false \
    .venv/bin/python scripts/production-qualification/run.py
```

### P2.1 — Run A (project `slaif-151-1725392-482e3f`): `RESULT=OK`

Exact output line: `RESULT=OK`; 16/16 phases OK.

| Phase | Seconds | Status |
| --- | --- | --- |
| prepare | 0.48 | OK |
| tls | 0.25 | OK |
| compose | 37.29 | OK |
| operator-configuration | 27.43 | OK |
| async-worker-and-scheduler-liveness | 5.87 | OK |
| chat-and-responses | 1.97 | OK |
| provider-failures-and-disconnects | 2.09 | OK |
| redis-and-timeout-controls | 13.9 | OK |
| redis-concurrency | 8.99 | OK |
| api-termination-and-cli-reconciliation | 20.81 | OK |
| persistence | 45.39 | OK |
| backup-restore | 11.09 | OK |
| privacy-input-boundaries | 0.59 | OK |
| quota-and-key-controls | 7.73 | OK |
| admin-dashboard-session | 0.39 | OK |
| privacy | 33.02 | OK |

- `metrics.positive_sample_present` on the single authorized scrape: all
  four exercised families `true` (`gateway_http_requests_total`,
  `gateway_provider_requests_total`, `gateway_tokens_total`,
  `gateway_cost_eur_total`).
- `restore_counts` restored==source: `gateway_keys: 2`, `usage_ledger: 15`.
- No-keep cleanup: `containers_by_compose_label`, `networks`, `runtime`,
  `volumes` all `true`; `remaining_networks: []`,
  `remaining_volumes: []`.
- `readiness.public_denied: true`; `initial_startup`, `api_restart`,
  `api_recreation`, `postgres_api_recreation` each 4 consecutive 200s;
  `redis_outage` 503/`not_ready`; `redis_recovery` 4 consecutive 200s.
- Concurrency evidence: `overlap_status: 429`
  (`concurrency_rate_limit_exceeded`, `overlap_provider_forward_delta: 0`,
  accounting unchanged), `following_status: 200`,
  `recovery_503_count: 0`, slot released.
- Accounting lifecycle sample (16 ledger rows): 9 `finalized` (HTTP 200;
  non-streaming and streaming chat and responses), 5 `failed` with
  reservation `released` (including the one 503 provider-failure sample),
  2 `estimated` with reservation `finalized` and actual==estimated; the
  `api-termination` terminal sample shows
  `accounting_status: failed` / `reservation_status: expired` with
  `provider_count_stable_after_kill: true` and `restart_ready: true`.
- Full stdout/stderr captured locally at `/tmp/obj170-harness-runA.log`
  (local artifact, not committed).

### P2.2 — Run B (project `slaif-151-1751638-b838f5`): `RESULT=OK`

Exact output line: `RESULT=OK`; 16/16 phases OK.

| Phase | Seconds | Status |
| --- | --- | --- |
| prepare | 0.07 | OK |
| tls | 0.27 | OK |
| compose | 34.11 | OK |
| operator-configuration | 27.4 | OK |
| async-worker-and-scheduler-liveness | 5.95 | OK |
| chat-and-responses | 2.01 | OK |
| provider-failures-and-disconnects | 2.76 | OK |
| redis-and-timeout-controls | 12.8 | OK |
| redis-concurrency | 9.13 | OK |
| api-termination-and-cli-reconciliation | 21.39 | OK |
| persistence | 48.01 | OK |
| backup-restore | 12.87 | OK |
| privacy-input-boundaries | 0.59 | OK |
| quota-and-key-controls | 8.07 | OK |
| admin-dashboard-session | 0.4 | OK |
| privacy | 33.14 | OK |

- Every AP-1 per-run field holds for Run B with the same evidence shape as
  P2.1: all four metric families positive on the single authorized scrape;
  `restore_counts` restored==source (`gateway_keys: 2`,
  `usage_ledger: 15`); no-keep cleanup all true with empty remaining
  networks/volumes; `readiness.public_denied: true` with the same
  readiness pattern (four recreation/restart families at 4 consecutive
  200s; `redis_outage` 503/`not_ready`; `redis_recovery` 4 consecutive
  200s); concurrency `overlap_status: 429` / `following_status: 200` /
  `recovery_503_count: 0` / slot released; 16-row accounting lifecycle
  with 9 `finalized`, 5 `failed` with reservation `released` (including
  one 503 provider-failure sample), 2 `estimated`, and the
  `api-termination` terminal sample `failed`/`expired` with provider
  count stable and restart ready.
- In particular, the `redis-concurrency` phase — the phase that produced
  the 169 finding P2.3 — completed OK in Run B with
  `recovery_503_count: 0`; the 169 transient 503 class did not recur in
  this attempt.
- Full stdout/stderr captured locally at `/tmp/obj170-harness-runB.log`
  (local artifact, not committed).

## P3 — Candidate test matrix (clean-room venv, disposable local PostgreSQL)

- Full unit suite via `scripts/test-unit-parallel.sh`
  (`.venv/bin/python -m pytest tests/unit -n 20 --dist loadscope`):
  **4047 passed / 1 failed / 0 skipped** in 73.05s. The single failure is
  the known VM-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (`codex_version_mismatch`: VM `codex --version` = `codex-cli 0.154.0`
  vs fixture pin `codex-cli 0.148.0`; `codex --version` output recorded),
  labeled environment-only per the order and not chased.
- Full PostgreSQL integration suite via
  `.venv/bin/python -m pytest tests/integration -q` with
  `TEST_DATABASE_URL` pointed at the user-owned disposable PostgreSQL 16
  on `127.0.0.1:5433` (database dropped/recreated immediately before the
  run): **224 passed / 1 skipped / 0 failed**. The skip is the local-VM
  `pg_dump` CLI limitation on the `TEST_DATABASE_URL` form
  (`tests/integration/test_backup_restore_postgres.py:42`; skip reason
  "pg_dump unavailable or incompatible" — pg_dump rejects the
  `postgresql+asyncpg` DSN form and falls back to the default socket),
  identical to the 167/168/169 baseline (in-container backup/restore
  re-proven in both P2 runs). The captured log's final summary line was
  lost to a tee/pipe flush race; the counts are the exact tally of the
  225-character pytest progress line (224 pass dots + 1 skip, zero
  fail/error markers).
- Official-client E2E via `.venv/bin/python -m pytest tests/e2e -q` on a
  drop/recreated database: **54 passed / 0 failed / 0 skipped** under
  `openai==3.9.0` (the 54-test official-client matrix; P1 freeze lines
  above). Same progress-line tally method (54 dots, no skip/fail
  markers).

## P4 — Exact CI state

Two states are recorded. (1) The candidate's own main-branch check runs,
verified at the merge and re-queried live against the GitHub API on
2026-09-17 — all nine required checks `completed`/`success` on
`1043c3f42fb46f06a8d7952273739cefb9de6cc7`:

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| Unit, lint, and migration head | completed | success | 105183932538 |
| Documentation hygiene | completed | success | 105183932519 |
| OpenAI-compatible E2E tests | completed | success | 105183932313 |
| Playwright browser smoke | completed | success | 105183932551 |
| Docker Compose smoke | completed | success | 105183932688 |
| PostgreSQL integration tests | completed | success | 105183932545 |
| Analyze (javascript-typescript) | completed | success | 105183936436 |
| Analyze (python) | completed | success | 105183936672 |
| Analyze Python | completed | success | 105183932867 |

(2) The exact PR head of this objective at the time this record was
written, `40984390e9c5564694ff6c84a4c443c39ec510b2` (the activation
commit carrying this order and `oap/active`): all nine required checks
`completed`/`success` (queried 2026-09-17; the mandatory final-head
re-query after the report-only commit per AP-7 is recorded in the
objective report):

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| Unit, lint, and migration head | completed | success | 105227348777 |
| Documentation hygiene | completed | success | 105227349008 |
| OpenAI-compatible E2E tests | completed | success | 105227349239 |
| Playwright browser smoke | completed | success | 105227349007 |
| Docker Compose smoke | completed | success | 105227349093 |
| PostgreSQL integration tests | completed | success | 105227349303 |
| Analyze (javascript-typescript) | completed | success | 105227341951 |
| Analyze (python) | completed | success | 105227341510 |
| Analyze Python | completed | success | 105227348747 |

Notably, `Unit, lint, and migration head` is `success` on the PR head:
this order is template-conforming (its line 3 is the literal
`PR mode: `CREATE_NEW_PR``), so the candidate's governance test
`tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`
passes on the byte-identical committed order — the 169 finding P4.1 does
not recur.

## Relationship to the abandoned 169 attempt

This objective repeats the abandoned Objective 169 (PR #306, CLOSED
unmerged 2026-09-17T13:11:30Z) against the same candidate
`1043c3f42fb46f06a8d7952273739cefb9de6cc7`. The 169 verdict
`RESULT=NOT-QUALIFIED` rested on two findings recorded on the abandoned
branch:

- **P2.3 (169)** — a single transient availability-class 503 on the
  `redis-concurrency` phase's strict following-completion assertion in
  consecutive Run B (project `slaif-151-1670026-685592`; Run A, project
  `slaif-151-1646010-cf7e04`, was fully green), which made AP-1
  unsatisfied; the failure window showed no host OOM/pressure/container
  crash, and root-cause attribution was not conclusive because the
  in-project logs were removed by the mandatory no-keep cleanup.
- **P4.1 (169)** — the 169-a order lacked the template's
  `PR mode: `CREATE_NEW_PR`` literal, so the candidate's governance
  unit test failed on the 169 PR head (`Unit, lint, and migration
  head` failure, check run `105205788307`), which made AP-3
  unsatisfied.

In this attempt: (a) both consecutive harness runs completed `RESULT=OK`
16/16, with `redis-concurrency` OK in Run B and
`recovery_503_count: 0` in both runs — the 169 P2.3 failure class did
not recur; (b) the template-conforming 170-a order passes the governance
test on the PR head — the 169 P4.1 finding does not recur. No file from
the abandoned 169 branch was imported, cherry-picked, or re-published;
this record is freshly authored at the allowed path (the 169 record's
filename was free because that file is not on `main`).

## Deployment-path statement

The documented dev Compose path is mechanically covered at this commit by
the CI `Docker Compose smoke` job (success: run ID 105227349093 on the PR
head, run ID 105183932688 on the candidate). The production topology
(`docker-compose.production.yml`: TLS, NGINX edge, secrets, internal
network, gunicorn API, Celery worker/scheduler) is covered by the P2
harness runs, whose `tls` and `compose` phases passed in both runs.

## Limitations

- The P2 provider is the harness's socket-level OpenAI-compatible double
  (mocked upstream); this is not a real-provider run, and no provider
  credentials were used or present.
- This record is not a release decision, production certification,
  security review, compliance finding, or SLA approval.
- RC2 required-scope completeness is asserted only as
  `docs/rc2-feature-scope.md`'s current classification; it is not
  re-derived here.
- Evidence boundary: this record is dated evidence for the named
  candidate commit `1043c3f42fb46f06a8d7952273739cefb9de6cc7` only; it
  does not transfer to later commits.
- The qualified verdict rests on: two consecutive green no-keep
  production-appliance runs (P2), the exact P3 matrix modulo only the two
  labeled environment-only non-passes (the VM-only codex-version unit
  case; the local-VM pg_dump skip), and 9/9 required checks `success` on
  the PR head (P4). The transient 503 class observed in the abandoned 169
  attempt remains a known environmental risk for this candidate; it did
  not occur in the two runs recorded here.
