# Objective 169 current-main integrated requalification

Date: 2026-09-17 (Europe/Ljubljana; UTC timestamps as recorded by the runs)

Candidate (evidence boundary): `main`
`1043c3f42fb46f06a8d7952273739cefb9de6cc7` (merge of PR #305 / Objective
168), verified remote `main` at execution time.

This is a fresh, verification-only, integrated requalification of that exact
candidate for the intended RC/deployment posture, with the Objective
167/168 determinism property — two consecutive default-no-keep
production-appliance harness runs from a fresh clean-room checkout, both
`RESULT=OK` — as the decisive test. It implements no capability, fixes
nothing, and makes no release decision. All candidate code was executed only
from the clean-room clone (P1); nothing was executed from the shared
worktree. The historical records
[`2026-09-17-current-main-integrated-qualification.md`](2026-09-17-current-main-integrated-qualification.md)
(Objective 167, `RESULT=NOT-QUALIFIED`) and the Objective 168 report are
immutable and are referenced, not rewritten.

## Verdict

`RESULT=NOT-QUALIFIED`

Run A (project `slaif-151-1646010-cf7e04`) completed all 16 phases with
`RESULT=OK`. The consecutive Run B (project `slaif-151-1670026-685592`)
failed at phase 9 `redis-concurrency` with
`ERROR=/v1/chat/completions returned 503, expected [200]` (exact
`RESULT=FAIL`). AP-1 requires both consecutive runs to be exactly
`RESULT=OK`; a single `RESULT=FAIL` run makes AP-1 unsatisfied and forces
this verdict, with the exact failure recorded (151-d/167
boundary-strictness precedent: no softening, re-labeling, or averaging).
The failure is classified with machine evidence in P2.3 as a
non-deterministic transient 503 of the availability class: not a
harness-side error, not one of the order's two labeled environment-only
expectations, and not conclusively attributable to a candidate-side defect
because the in-container logs of the failed project were removed by the
mandatory no-keep cleanup.

A second, independent acceptance predicate is also unsatisfied: AP-3
requires all nine required checks `success` on the exact PR head, but the
PR head's `Unit, lint, and migration head` check run
(`105205788307`) concluded `failure` on the candidate's own governance
test `tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`, which asserts the literal string
`PR mode: \`CREATE_NEW_PR\`` in the active `-a` work order. The
strategic-authored 169-a order — which this order's PR contract requires
to be committed unchanged — does not contain that literal (it uses a
`## PR contract` section instead), and the literal is not mandated by the
durable protocol (`OAP-COMMUNICATION-coding-agent.md` mentions `PR mode`
only as a report field, `CREATED_NEW_PR`). This is classified in P4.1 as
a candidate-side governance-test brittleness finding (third manifestation
of the literal-phrase assertion class first seen at Objective 001 and
partially relaxed at 001-b). The candidate's own main-branch checks on
`1043c3f42fb46f06a8d7952273739cefb9de6cc7` remain 9/9 `success`, so the
failing check is not a candidate-main regression; it is triggered by the
interaction of the candidate's brittle test with the byte-identical
strategic order content this objective must commit.

No code was modified; whether either finding warrants a new numeric
objective is a strategy decision.

## P1 — Clean-room candidate

- Fresh full clone: `/tmp/obj169-cleanroom/`, detached checkout of
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`.
- `git rev-parse HEAD` = candidate SHA; `git status --short` empty.
- Fresh venv at `/tmp/obj169-cleanroom/.venv` (Python 3.12.3) with `.[dev]`
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
Compose 2.40.3, user-owned disposable PostgreSQL 16 (16.15) instance at
`127.0.0.1:5433` for P3 (own role/database; drop/recreated before each
DB-backed suite), host Redis at `127.0.0.1:6379`. `RUN_UPSTREAM_TESTS`
unset throughout; no provider credentials present or used;
`ENABLE_EMAIL_DELIVERY=false`; `DATABASE_URL`, `TEST_REDIS_URL`, and all
upstream key variables explicitly unset from the run environments.

Environment notes (honesty disclosures, no effect on the evidence chain):

- Two read-only diagnostic `find /` scans left over from an earlier local
  investigation were running on the execution VM during P2/P3 (started
  10:53 UTC and 11:57 UTC); they consumed negligible CPU (<0.2% each),
  showed no memory pressure (PSI zero; no OOM in dmesg), and were present
  in both harness runs (common factor, not a discriminator). They were
  terminated after P3.
- Local `psql` TCP password authentication to the disposable cluster
  misbehaved all turn, while socket authentication and — decisively —
  asyncpg (the client the suites use) TCP authentication succeeded for
  both disposable roles on `127.0.0.1:5433` (fresh `asyncpg.connect`
  `AUTH_OK` for both roles immediately before P3). Classified as a
  client-side/environment-only local psql/libpq quirk; the database path
  actually used by the test suites was verified end-to-end.

## P2 — Production-appliance qualification

Command (run twice consecutively from the clean-room tree, default
no-keep mode, no code or environment change between the runs):

```text
env -u DATABASE_URL -u TEST_REDIS_URL -u RUN_UPSTREAM_TESTS \
    -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY \
    ENABLE_EMAIL_DELIVERY=false \
    .venv/bin/python scripts/production-qualification/run.py
```

### P2.1 — Run A (project `slaif-151-1646010-cf7e04`): `RESULT=OK`

Exact output line: `RESULT=OK`; 16/16 phases OK.

| Phase | Seconds | Status |
| --- | --- | --- |
| prepare | 0.47 | OK |
| tls | 0.52 | OK |
| compose | 37.81 | OK |
| operator-configuration | 27.60 | OK |
| async-worker-and-scheduler-liveness | 5.95 | OK |
| chat-and-responses | 1.99 | OK |
| provider-failures-and-disconnects | 2.80 | OK |
| redis-and-timeout-controls | 11.74 | OK |
| redis-concurrency | 9.08 | OK |
| api-termination-and-cli-reconciliation | 20.25 | OK |
| persistence | 45.36 | OK |
| backup-restore | 10.79 | OK |
| privacy-input-boundaries | 0.57 | OK |
| quota-and-key-controls | 7.87 | OK |
| admin-dashboard-session | 0.30 | OK |
| privacy | 32.98 | OK |

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
- Accounting lifecycle sample (16 ledger rows): 8 `finalized` (HTTP 200;
  non-streaming and streaming chat and responses), 5 `failed` with
  reservation `released` (including the one 503 provider-failure sample),
  2 `estimated` with reservation `finalized` and actual==estimated; the
  `api-termination` terminal sample shows
  `accounting_status: failed` / `reservation_status: expired` with
  `provider_count_stable_after_kill: true` and `restart_ready: true`.
- Full stdout/stderr captured locally at `/tmp/obj169-harness-runA.log`
  (local artifact, not committed).

### P2.2 — Run B (project `slaif-151-1670026-685592`): `RESULT=FAIL`

Exact output lines:

```text
RESULT=FAIL
ERROR=/v1/chat/completions returned 503, expected [200]
```

Phases 1–8 OK; phase 9 failed; phases 10–16 not reached.

| Phase | Seconds | Status |
| --- | --- | --- |
| prepare | 0.07 | OK |
| tls | 0.29 | OK |
| compose | 33.69 | OK |
| operator-configuration | 27.38 | OK |
| async-worker-and-scheduler-liveness | 5.93 | OK |
| chat-and-responses | 1.98 | OK |
| provider-failures-and-disconnects | 2.79 | OK |
| redis-and-timeout-controls | 11.71 | OK |
| redis-concurrency | 8.99 | FAIL |

- The failing request was the phase's final **following** chat completion
  (plain non-streaming, `max_tokens=8`, the phase's only `expect={200}`
  assertion, `scripts/production-qualification/run.py` line 1358 on the
  candidate), issued after: the overlap request was validated within
  `expect={200, 429, 503}`; the 8-second-paused first stream joined with
  HTTP 200 and its accounting finalized; and the harness's own Redis read
  confirmed the concurrency slot released (slot count 0). The following
  request on that free slot returned 503.
- Readiness before the failure: `initial_startup` 4 consecutive 200s,
  `public_denied: true`, `redis_outage` 503/`not_ready`,
  `redis_recovery` 4 consecutive 200s (Redis probed healthy immediately
  before the failing phase).
- No-keep cleanup after the failure: all checks `true`,
  `remaining_networks: []`, `remaining_volumes: []` (no residue).
- Full stdout/stderr captured locally at `/tmp/obj169-harness-runB.log`
  (local artifact, not committed).

### P2.3 — Failure classification

1. **Exact failure surface.** A plain free-slot chat completion returned
   503 where 200 was documented-expected, after every preceding phase
   precondition (overlap validation, first-stream 200 termination,
   accounting finalization, slot release) had passed. In the candidate
   code the 503 paths for such a request are: (a) the Redis rate-limit
   fail-closed path `redis_rate_limit_unavailable` —
   `RedisRateLimitService.check_and_reserve` performs a single `EVAL` with
   no retry and maps any exception to a fail-closed 503
   (`app/slaif_gateway/services/rate_limit_service.py`,
   `app/slaif_gateway/services/chat_completion_gateway.py`); (b) a
   provider error passthrough (the `provider-failures-and-disconnects`
   phase itself maps provider `http_error` to {502, 503}). Both are
   transient-availability classes, not accounting or policy failures.
2. **Recurrent transient in the same code lineage.** Objective 168 Run B's
   `redis-concurrency` recorded `recovery_503_count: 1` — a 503 of the
   same class on the first-stream establishment attempt, absorbed by the
   harness's designed recovery path (phase OK). 168 Run A and 169 Run A
   recorded `recovery_503_count: 0`. The phase passed 3 of the 4 prior
   runs on this lineage, and a same-class 503 transient was observed in 2
   of the 4; whether the transient lands on a recovered first-stream
   attempt or on the unrecovered following request determines the phase
   outcome.
3. **Host evidence for the fail window (12:19:55–12:20:04 UTC).** dmesg
   clean (no OOM or kills); memory PSI zero with ~44 GB free; load
   average ~1. The docker daemon log for the window shows no crash,
   restart, or OOM event for the failed project (routine veth
   attach/detach only). The project teardown (after the failure,
   12:20:20 UTC) needed one SIGTERM force-kill after a 10-second timeout;
   the same pattern appeared in Run A's teardown (12:18:05 UTC),
   consistent with slow container shutdowns on this WSL2 VM.
4. **Attribution limit.** The in-container API/Redis/provider logs of the
   failed project were removed by the mandatory no-keep cleanup
   (verified: no remaining containers, networks, or volumes), so the root
   trigger of the transient is not conclusively attributable to a
   candidate-side defect versus an environment-side stall.

Classification: **non-deterministic transient 503 (availability class) on
the following request** — not a harness-side error (the harness asserted
the documented expected status correctly), not one of the two labeled
environment-only expectations, and not conclusively a candidate-side
defect. The boundary-strict consequence stands regardless of the
unresolvable attribution: AP-1 is unsatisfied and the verdict is
`RESULT=NOT-QUALIFIED`.

## P3 — Candidate test matrix (clean-room venv, disposable local PostgreSQL)

- Full unit suite via `scripts/test-unit-parallel.sh`
  (`.venv/bin/python -m pytest tests/unit -n 20 --dist loadscope`):
  **4047 passed / 1 failed / 0 skipped** in 68.75s. The single failure is
  the known VM-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (VM `codex --version` = `codex-cli 0.154.0` vs fixture pin
  `codex-cli 0.148.0`), labeled environment-only per the order and not
  chased.
- Full PostgreSQL integration suite via
  `.venv/bin/python -m pytest tests/integration -q` with
  `TEST_DATABASE_URL` pointed at the user-owned disposable PostgreSQL 16
  on `127.0.0.1:5433` (database dropped/recreated immediately before the
  run): **224 passed / 1 skipped / 0 failed**. The skip is the local-VM
  `pg_dump` CLI limitation on the `TEST_DATABASE_URL` form
  (`tests/integration/test_backup_restore_postgres.py:42`), identical to
  the 167/168 baseline (in-container backup/restore re-proven in both P2
  runs). The captured log's final summary line was lost to a tee/pipe
  flush race; the counts are the exact tally of the 225-character pytest
  progress line (224 pass dots + 1 skip, zero fail/error markers).
- Official-client E2E via `.venv/bin/python -m pytest tests/e2e -q` on a
  drop/recreated database: **54 passed / 0 failed / 0 skipped** under
  `openai==3.9.0` (the 54-test official-client matrix; P1 freeze lines
  above). Same progress-line tally method (54 dots, no skip/fail
  markers).

## P4 — Exact CI state

Two states are recorded. (1) The candidate's own main-branch check runs,
verified at the merge and re-queried live on 2026-09-17 — all nine
required checks `completed`/`success` on
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

(2) The exact PR head of this objective,
`4f84575f092119dba469dc36bdb3dfc44f7080ab` (the implementation commit
carrying this order and `oap/active`): eight of the nine required checks
`completed`/`success`; `Unit, lint, and migration head`
`completed`/`failure` (queried 2026-09-17; see P4.1 for the exact
failure and classification; the mandatory final-head re-query after the
report-only commit per AP-7 is recorded in the objective report):

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| Unit, lint, and migration head | completed | failure | 105205788307 |
| Documentation hygiene | completed | success | 105205788004 |
| OpenAI-compatible E2E tests | completed | success | 105205788166 |
| Playwright browser smoke | completed | success | 105205788304 |
| Docker Compose smoke | completed | success | 105205788251 |
| PostgreSQL integration tests | completed | success | 105205788492 |
| Analyze (javascript-typescript) | completed | success | 105205786791 |
| Analyze (python) | completed | success | 105205787132 |
| Analyze Python | completed | success | 105205788690 |


### P4.1 — PR-head `Unit, lint, and migration head` failure (finding F2)

- Check run: `105205788307` (workflow run `35222480268`), GitHub-hosted
  runner, Python 3.12.14.
- Job result: `1 failed, 4046 passed, 1 skipped, 16 warnings in
  111.73s` (the one skipped test's identity is not shown in the captured
  summary; it is not one of this order's labeled environment-only items).
- Exact failure:
  `tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`
  — `AssertionError: assert 'PR mode: `CREATE_NEW_PR`' in
  '# OAP Work Order — 169-a\n\n## Objective and business reason\n...'`
  (`tests/unit/test_oap_governance.py:54`).
- Mechanism: the test reads `oap/active` (`169-a`), loads the matching
  order file, and for any `-a` round asserts the literal
  `PR mode: \`CREATE_NEW_PR\`` in the order text. The 167-a and 168-a
  orders contain that literal (line 3 of each); the 169-a order does not
  (it declares the PR contract in a `## PR contract` section). The
  durable protocol does not mandate the literal in orders: its only
  `PR mode` occurrence is the report field
  `PR mode: CREATED_NEW_PR | AMENDED_EXISTING_PR`.
- Classification: **candidate-side governance-test brittleness** (test
  coupled to a strategic order phrasing that is not protocol-mandated).
  It is not a product-code regression — the candidate main
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` passes the same check 9/9
  (its active order at that commit is `168-a`, which contains the
  literal) — and it is not environment-only (it is a deterministic
  string assertion over committed repository files). It is the third
  manifestation of the literal-phrase governance-assertion class first
  seen at Objective 001 (fixed at 001-b only for the one-new-PR
  invariant, which the test now reads from the durable protocol file;
  the `PR mode` literal assertion on order text remained).
- Consequence: any objective whose strategic `-a` order omits the literal
  will fail this check on its PR head while the order must be committed
  byte-identical per the work-order contract; neither side of the
  interaction was modifiable inside this verification-only objective.
  Fixing the test (or the order format) is a separate numeric objective
  or a strategic format decision.
## Deployment-path statement

The documented dev Compose path is mechanically covered at this commit by
the CI `Docker Compose smoke` job (SUCCESS, run ID 105183932688 on the
candidate). The production topology (`docker-compose.production.yml`:
TLS, NGINX edge, secrets, internal network, gunicorn API, Celery
worker/scheduler) is covered by the P2 harness runs, whose `tls` and
`compose` phases passed in both runs.

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
- The verdict reflects two independent disqualifying findings on the
  candidate: (1) the candidate's own qualification harness result —
  fully green Run A (16/16) and Run B failed at phase 9
  (`redis-concurrency`, non-deterministic transient 503, P2.3) — and
  (2) the candidate's brittle OAP governance test failing on the
  byte-identical strategic 169-a order at the PR head (P4.1), with the
  rest of the local matrix green modulo the labeled environment-only
  unit failure and the labeled local-VM pg_dump skip.
