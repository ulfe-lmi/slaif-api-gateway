# Objective 167 current-main integrated qualification

Date: 2026-09-17 (Europe/Ljubljana; UTC timestamps as recorded by the runs)

Candidate (evidence boundary): `main`
`9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` (merge of PR #303 / Objective
166), verified remote `main` at execution time.

This is a fresh, verification-only qualification of that exact candidate for
the intended RC/deployment posture. It implements no capability, fixes
nothing, and makes no release decision. All candidate code was executed only
from the clean-room clone (P1); nothing was executed from the shared
worktree. The historical record
[`2026-08-24-production-appliance-qualification.md`](2026-08-24-production-appliance-qualification.md)
is immutable and is referenced, not rewritten.

## Verdict

`RESULT=NOT-QUALIFIED`

The candidate's own production-appliance qualification harness failed its
`privacy` phase on the first full run against this exact candidate
(`ERROR=authorized /metrics did not expose positive samples for every
exercised family`). The mandatory reproduction run in the identical clean
environment returned `RESULT=OK`. The failure is not environment-only (no
port, Docker-daemon, or leftover-project cause; run 1's own no-keep cleanup
checks were all true and run 2 passed without any environment change), and
static analysis places its root cause in candidate-side behavior: in-process
Prometheus counters under the shipped two-worker production API topology
make the harness's single `/metrics` scrape non-deterministic (see P2.3).
`RESULT=QUALIFIED-RC-POSTURE` requires all P2 phases OK for the candidate,
which this evidence does not establish; no other phase failed in either run,
no candidate code was modified, and fixing the finding is a separate numeric
objective.

## P1 — Clean-room candidate

- Fresh full clone: `/tmp/obj167-cleanroom/`, detached checkout of
  `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc`.
- `git rev-parse HEAD` = candidate SHA; `git status --short` empty.
- Fresh venv at `/tmp/obj167-cleanroom/.venv` with `.[dev]` installed.
- Freeze lines (P1 install; re-verified immediately before the E2E matrix):

```text
openai==3.9.0
httpx==0.28.1
httpx2==2.13.0
httpcore2==2.13.0
pydantic==2.13.5
respx==0.23.1
pytest==9.1.1
```

Environment: Linux VM (24 cores), Python 3.12, Docker 29.1.3, Docker Compose
2.40.3, user-owned disposable local PostgreSQL 16 at `127.0.0.1:5432`
(`TEST_DATABASE_URL` harness mode, drop/recreated before each full
DB-backed suite). `RUN_UPSTREAM_TESTS` unset throughout; no provider
credentials present or used; `ENABLE_EMAIL_DELIVERY=false`;
`DATABASE_URL`, `TEST_REDIS_URL`, and all upstream key variables explicitly
unset from the run environment.

## P2 — Production-appliance qualification

Command (run twice, default no-keep mode, from the clean-room tree):

```text
.venv/bin/python scripts/production-qualification/run.py
```

### P2.1 — Run 1 (project `slaif-151-1288081-b8488c`): `RESULT=FAIL`

Exact failure output:

```text
RESULT=FAIL
ERROR=authorized /metrics did not expose positive samples for every exercised family
```

Per-phase table (run 1):

| Phase | Result | Seconds |
| --- | --- | --- |
| prepare | OK | 0.11 |
| tls | OK | 0.30 |
| compose | OK | 112.21 |
| operator-configuration | OK | 28.55 |
| async-worker-and-scheduler-liveness | OK | 5.86 |
| chat-and-responses | OK | 1.99 |
| provider-failures-and-disconnects | OK | 2.72 |
| redis-and-timeout-controls | OK | 11.64 |
| redis-concurrency | OK | 9.09 |
| api-termination-and-cli-reconciliation | OK | 20.77 |
| persistence | OK | 45.28 |
| backup-restore | OK | 10.78 |
| privacy-input-boundaries | OK | 0.65 |
| quota-and-key-controls | OK | 7.70 |
| admin-dashboard-session | OK | 0.42 |
| privacy | **FAIL** | 0.74 |

Restore verifier (run 1): restored == source,
`gateway_keys: 2`, `usage_ledger: 15`. No-keep cleanup (run 1): all checks
true — `containers_by_compose_label`, `networks`, `runtime`, `volumes` all
true; `remaining_networks` and `remaining_volumes` empty. Quota-phase
evidence (run 1): overlap request rejected `429
concurrency_rate_limit_exceeded` with zero additional provider forwards and
unchanged accounting; API-termination evidence: active reservation present,
kill observed, `terminal_accounting_status=failed`,
`terminal_reservation_status=expired`, `restart_ready=true`, counters
cleared. Readiness evidence (run 1): initial startup, API restart, and
Postgres-API recreation each recovered to `status=200`
(`consecutive_successes=4`); Redis outage correctly fail-closed to `503`
(`state=not_ready`, `consecutive_successes=0`) and recovered to `200`;
public unauthenticated metrics access denied.

The run exercised 16 requests against the socket-level provider double:
9 successful `200` completions finalized with actual cost
(`0.000019`–`0.000040` EUR, 12–32 tokens), 5 designed failure/disconnect
requests correctly released with zero cost, and 2 interrupted streaming
requests finalized under `estimated` accounting. The PostgreSQL usage ledger
(15 rows) carried the actual costs and token counts in the failing run —
PostgreSQL quota/accounting truth was intact.

### P2.2 — Run 2, mandatory reproduction (project `slaif-151-1308665-c76beb`): `RESULT=OK`

Per-phase table (run 2):

| Phase | Result | Seconds |
| --- | --- | --- |
| prepare | OK | 0.07 |
| tls | OK | 0.93 |
| compose | OK | 34.01 |
| operator-configuration | OK | 28.35 |
| async-worker-and-scheduler-liveness | OK | 5.84 |
| chat-and-responses | OK | 1.97 |
| provider-failures-and-disconnects | OK | 2.11 |
| redis-and-timeout-controls | OK | 12.21 |
| redis-concurrency | OK | 9.02 |
| api-termination-and-cli-reconciliation | OK | 20.46 |
| persistence | OK | 45.22 |
| backup-restore | OK | 10.78 |
| privacy-input-boundaries | OK | 0.59 |
| quota-and-key-controls | OK | 7.86 |
| admin-dashboard-session | OK | 0.40 |
| privacy | OK | 32.86 |

Run 2 metrics evidence: positive samples present for all four exercised
families — `gateway_http_requests_total`, `gateway_provider_requests_total`,
`gateway_tokens_total`, `gateway_cost_eur_total`. Restore verifier (run 2):
restored == source, `gateway_keys: 2`, `usage_ledger: 15`. No-keep cleanup
(run 2): all checks true; no remaining networks or volumes. Request shape,
quota-phase evidence, API-termination evidence, and readiness evidence
matched run 1 (16 requests, same success/failure/estimated distribution,
same fail-closed Redis outage behavior).

### P2.3 — Failure classification

- Not environment-only. The order's environment-only causes are port
  binding, Docker daemon state, and leftover projects. None applied: run 1
  reached every phase (all ports and services were up), run 1's own cleanup
  checks were all true before the failure was recorded, no leftover project
  existed (each run creates a unique project), and run 2 passed in the
  identical environment with no environment change at all.
- Root cause in candidate-side behavior, non-deterministic per run. The
  production image's command runs gunicorn with two Uvicorn workers
  (`Dockerfile` CMD, `--workers 2`); `app/slaif_gateway/metrics.py` uses
  in-process `prometheus_client` counters with no multiprocess mode; the
  NGINX upstream (`nginx/production.conf`, `proxy_pass http://api:8000`
  without keepalive pooling) and the harness's in-container scrape each open
  fresh connections, so gunicorn round-robins them across the two workers.
  The `privacy` phase's single authorized `/metrics` scrape therefore
  exposes only the counters of whichever worker happens to serve it. The
  request middleware counts every request it serves (including the scrape
  itself), so `gateway_http_requests_total` is guaranteed positive on the
  scraping worker; the three provider-call families
  (`gateway_provider_requests_total`, `gateway_tokens_total`,
  `gateway_cost_eur_total`) are incremented only in the worker that handled
  a provider call, and read zero when the scrape lands on the other worker.
  Run 1 hit that case; run 2 did not.
- Pre-existing property, not a new regression: within
  `8f2813bf745b90221da33a7cfaf40726c5b1b480..9bb81cb960b6d3ba5373425cbe50cdcc670b93dc`
  there are zero commits touching `app/slaif_gateway/metrics.py`, any
  metrics call site (`observe_http_request`, `observe_provider_call`,
  `record_provider_call_result`, `add_tokens`, `add_cost_eur`),
  `scripts/production-qualification/`, or `Dockerfile`. The 2026-08-24
  passing run passed the same check on the same code, harness, and
  two-worker topology.
- Accounting is not affected: the failing run's PostgreSQL usage ledger
  recorded all costs and tokens, and the restore verifier matched. This is a
  metrics-exposure (observability) defect of the shipped production
  topology, not a quota/accounting defect.
- A diagnostic `--keep` run was not required: the exact failure output is
  captured above, the per-family zero pattern follows from the code cited
  above, and the mandatory clean reproduction already discriminated the
  environment from the candidate. No `--keep` run was performed, so there is
  no `--keep` residue to remove.

## P3 — Candidate test matrix (clean-room venv, disposable local PostgreSQL)

- Unit (full suite): `scripts/test-unit-parallel.sh`
  (24-core machine, xdist parallel) — **4043 passed, 1 failed, 0 skipped**
  in 70.80s. The single failure is the known VM-only environment failure
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`,
  caused by the VM's codex CLI version
  (`codex --version` output: `codex-cli 0.154.0`) versus the fixture pin
  `codex-cli 0.148.0` (version-mismatch raised by
  `scripts/verify_qwen38_text_codex.py`). Labeled environment-only; kept
  distinct from candidate findings.
- PostgreSQL integration (full suite): `python -m pytest tests/integration -q`
  — **224 passed, 1 skipped, 0 failed**. The single skip is
  `tests/integration/test_backup_restore_postgres.py` (fixture skip:
  "pg_dump unavailable or incompatible") — the local VM `pg_dump` CLI cannot
  consume the `TEST_DATABASE_URL` form and attempted the local Unix socket;
  this is a local-VM harness limitation of the disposable-DB mode, not a
  candidate finding. The in-container harness backup/restore phase passed in
  both P2 runs. Counts re-confirmed by a second `-rs` run: 224 passed,
  1 skipped, 0 failed.
- Official-client E2E matrix: `python -m pytest tests/e2e -q` —
  **54 passed, 0 skipped, 0 failed** under the candidate's pinned
  `openai==3.9.0` (pip-freeze proof in P1; re-frozen immediately before this
  run: `openai==3.9.0`, `httpx==0.28.1`, `httpx2==2.13.0`,
  `httpcore2==2.13.0`, `pydantic==2.13.5`, `respx==0.23.1`, `pytest==9.1.1`).
- Browser smoke: not run locally. Cited from CI at the candidate SHA:
  `Playwright browser smoke` SUCCESS, check run ID 105111680605 (see P4).
  CI is the machine for this surface at this exact commit.

## P4 — Exact CI state (re-queried at report time, 2026-09-17)

Command: `gh api repos/ulfe-lmi/slaif-api-gateway/commits/9bb81cb960b6d3ba5373425cbe50cdcc670b93dc/check-runs`

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| Unit, lint, and migration head | completed | success | 105111680700 |
| Documentation hygiene | completed | success | 105111680837 |
| OpenAI-compatible E2E tests | completed | success | 105111680644 |
| Playwright browser smoke | completed | success | 105111680605 |
| Docker Compose smoke | completed | success | 105111680746 |
| PostgreSQL integration tests | completed | success | 105111680437 |
| Analyze (javascript-typescript) | completed | success | 105111682686 |
| Analyze (python) | completed | success | 105111683034 |
| Analyze Python | completed | success | 105111680382 |

All nine required checks are SUCCESS on the candidate SHA. (The same query
also lists non-required `Dependabot` and `update-pip-graph` checks; they are
not part of the nine-check gate.)

## Deployment-path statement

The documented dev Compose path (`cp .env.example .env` -> `docker compose
build` -> `up -d postgres redis mailpit` -> `slaif-gateway db upgrade` ->
`up`) is mechanically covered at this commit by the CI `Docker Compose
smoke` job (SUCCESS, run ID 105111680746). The production topology
(`docker-compose.production.yml`: TLS, NGINX edge, secrets, internal
network, gunicorn API, Celery worker/scheduler) is covered by the P2
harness runs, whose `tls` and `compose` phases passed in both runs.

## Limitations

- The P2 provider is the harness's socket-level OpenAI-compatible double
  (mocked upstream); this is not a real-provider run, and no provider
  credentials were used or present.
- This record is not a release decision, production certification, security
  review, compliance finding, or SLA approval.
- RC2 required-scope completeness is asserted only as
  `docs/rc2-feature-scope.md`'s current classification; it is not re-derived
  here.
- Evidence boundary: this record is dated evidence for the named candidate
  commit `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` only; it does not
  transfer to later commits.
- The verdict reflects the candidate's own qualification harness result on
  the candidate: one failed phase (non-deterministic per-worker
  metrics-exposure finding, P2.3) on run 1 and a fully green run 2, with the
  rest of the local matrix green modulo the labeled environment-only unit
  failure and the labeled local-VM pg_dump skip.
