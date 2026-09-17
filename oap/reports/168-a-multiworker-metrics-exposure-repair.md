# OAP Coding-Agent Report — 168-a

## Work order
- Identifier: 168-a
- Work-order file: `oap/orders/168-a-multiworker-metrics-exposure-repair.md`
- Numeric objective: 168
- PR mode: CREATE_NEW_PR

## Status
COMPLETE

## Executive summary
Repaired the exact multi-worker metrics-exposure defect recorded by Objective
167 (P2.3: in-process `prometheus_client` counters under the shipped two-worker
gunicorn topology made the single authorized `/metrics` scrape non-deterministic
— run 1 `RESULT=FAIL`, run 2 `RESULT=OK` in an identical environment) so that
cross-worker aggregation is part of the shipped production topology and the
harness privacy-phase assertion holds **deterministically**.

Implementation (F1–F5, exactly the allowed paths):

- **F1 — multiprocess mode.** `app/slaif_gateway/metrics.py` now activates
  `prometheus_client` (0.26.0) mmap-based multiprocess mode when
  `PROMETHEUS_MULTIPROC_DIR` is set (imports fail closed with `RuntimeError`
  if it is set but is not a directory). Metric objects are then created with
  `registry=None`, and a single `MultiProcessCollector` is registered on the
  default `REGISTRY` so `generate_latest()` in `prometheus_response_body()`
  exposes the **aggregate of all live API workers**. Without the environment
  variable the previous single-process behavior is byte-for-byte unchanged
  (unit tests, CLI, Celery processes). Crucially, prometheus_client's mmap MPM
  encodes per-process identity in the **file names**
  (`counter_<name>_<pid>.db`), not in the sample names, so the exposition
  keeps the **original metric names** — which made the F3 harness
  family-name update unnecessary (zero-line harness diff; AP-2).
- **F1 — worker-exit cleanup.** `cleanup_multiproc_metrics()` removes the
  calling process's own `*_<pid>.db` files (pid resolved at call time because
  gunicorn imports the app in the master and forks the workers). It is wired
  as the deterministic shutdown point in `app/slaif_gateway/main.py`: the
  existing `build_lifespan(app_settings)` is wrapped in `app_lifespan`, whose
  `finally` block calls the cleanup. This is the shutdown phase that
  deterministically runs under the shipped UvicornWorker topology: empirical
  probing (local artifact `/tmp/mpm_probe`) showed that uvicorn 0.52/0.53
  `capture_signals` **re-raises the captured SIGTERM under the restored
  `SIG_DFL` after graceful shutdown**, so the worker terminates by signal and
  neither `atexit` handlers nor gunicorn's child `finally` (`worker_exit`
  hook, "Worker exiting" log) execute; gunicorn 26.x exposes no CLI flag for
  the hook. `slaif_gateway.metrics.on_worker_exit` remains the entry point
  for config-file deployments whose workers exit through a normal interpreter
  shutdown (e.g. sync workers), and an `atexit`-registered call of the same
  cleanup covers normal-exit paths. A SIGKILL-terminated worker leaves its
  files behind; stale files can only **inflate**, never zero or reduce, the
  aggregate (documented), so scrape determinism is unaffected, and each
  Compose project gets a fresh tmpfs mount at container start.
  `main.py` stays at 68 lines (under the 70-line structural guard in
  `tests/unit/test_main_app_structure.py`).
- **F2 — compose topologies.** `docker-compose.production.yml` and
  `docker-compose.yml` each add, to the `api` service only,
  `PROMETHEUS_MULTIPROC_DIR: /var/slaif/metrics` and
  `tmpfs: [/var/slaif/metrics:mode=1777]`. `mode=1777` was empirically
  required: a bare `tmpfs:` mount is created 1777 but **re-mounted root-owned
  755 on container restart**, which made worker boot fail with
  `PermissionError: /var/slaif/metrics/counter_<pid>.db` (reproduced locally,
  log `/tmp/obj168-harness-run1b.log`); with `mode=1777`, kill/restart of the
  api container in-container was verified end-to-end (graceful "Application
  shutdown complete" in both workers, MPM directory emptied on shutdown,
  clean restart). `Dockerfile` is unchanged (compose-level env, as the order
  prefers). An earlier design iteration used a named volume with
  `driver: tmpfs`; that is a volume-*plugin* reference, absent in the CI
  environment, and failed the CI `Docker Compose smoke` check on the first
  push; it was replaced by the bare `tmpfs:` mount before the Q3 runs, and
  the final tree is green (see CI gate state).
- **F3 — harness family-name update: not required.** Because MPM keeps the
  original names, `git diff 08ca421 2468d01 -- scripts/production-qualification/`
  is exactly **0 lines**: the `EXERCISED_METRIC_FAMILIES` tuple,
  `positive_prometheus_sample_counts()`, the positive-sample requirement, and
  the unauthenticated-denial check are all byte-identical (AP-2).
- **F4 — unit tests.** New `tests/unit/test_metrics_multiprocess.py`
  (4 tests, all green): two simulated worker registries writing into one
  `PROMETHEUS_MULTIPROC_DIR` aggregate positively on a single scrape; the
  worker-exit hook removes only its own worker's files; the lifespan-shutdown
  path removes the multiprocess files; and dead-worker files remain until
  reaped (documented stale-file semantics). Existing metrics unit tests
  needed no name updates (names unchanged) and remain green.
- **F5 — documentation.** `docs/observability.md` gained the
  "Multi-worker metrics aggregation" section stating the aggregate-of-live-API
  workers behavior under the original metric names, the lifespan-shutdown
  cleanup rationale, the SIGKILL stale-file semantics, and — honestly — the
  pre-existing boundary that Celery worker/scheduler process counters remain
  per-process in memory and are not aggregated or exposed (out of scope,
  observation-only).

Q3 determinism proof: two consecutive default-no-keep production-harness runs
from a fresh clean-room checkout of the exact PR head (FRESH venv), both
`RESULT=OK` with 16/16 phases, all four exercised families positive on the
single authorized scrape in both runs, restore-verifier counts matching
(`gateway_keys: 2`, `usage_ledger: 15`, restored==source), and no-keep
cleanup checks all true in both runs. Q4 full matrix: unit 4047 passed / 1
failed (known VM-only codex-CLI case, labeled) / 0 skipped; PostgreSQL
integration 224 passed / 1 skipped (local-VM `pg_dump` limitation, identical
environment-only skip as the 167 baseline) / 0 failed on a user-owned
disposable PostgreSQL 16; official-client E2E 54 passed / 0 failed / 0 skipped
under `openai==3.9.0`. CI: all nine required checks SUCCESS on the
implementation head, re-queried after the report-only commit per AP-4.
Zero product behavior, accounting, routing, policy, or compatibility change;
the `/metrics` authentication policy is unchanged (unauthenticated access
remains denied in both harness runs).

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 305
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/305
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/168-multiworker-metrics-exposure-repair`
- Starting remote SHA: `08ca421bee1ddca62078302b910e8be88cf705be`
- Implementation head SHA: 2468d01f588d03cc726b0a524f4146f8f6bc51b6
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
    - `23cb8e51da327d534eb211fb423da383c5e3b319` `obj168: repair multi-worker metrics exposure in production topology`
  - `2468d01f588d03cc726b0a524f4146f8f6bc51b6` `oap: activate 168-a multiworker metrics exposure repair` (carries the strategic-authored order and `oap/active` unchanged)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `app/slaif_gateway/metrics.py`: multiprocess-mode wiring — MPM activation
  gated on `PROMETHEUS_MULTIPROC_DIR` (fail-closed `RuntimeError` if set but
  not a directory); `_counter`/`_histogram` factories registering with
  `registry=None` in MPM mode and `REGISTRY` otherwise; single
  `MultiProcessCollector(REGISTRY)` in MPM mode; `cleanup_multiproc_metrics()`
  (lazy pid, removes only this process's `*_<pid>.db` files);
  `on_worker_exit` gunicorn hook entry point; `atexit` registration in MPM
  mode; module docstring documenting the mode. All existing metric names,
  labels, and call sites unchanged.
- `app/slaif_gateway/main.py`: wraps `build_lifespan(app_settings)` in
  `app_lifespan` whose `finally` calls
  `metrics_module.cleanup_multiproc_metrics()` (the deterministic shutdown
  point under the shipped UvicornWorker topology). File stays 68 lines (< 70
  structural guard). No other behavior changed.
- `docker-compose.production.yml`: `api` service only — added
  `PROMETHEUS_MULTIPROC_DIR: /var/slaif/metrics` and
  `tmpfs: [/var/slaif/metrics:mode=1777]`.
- `docker-compose.yml`: `api` service only — same environment variable and
  tmpfs mount, so dev and production topologies behave identically.
- `tests/unit/test_metrics_multiprocess.py`: new — 4 focused tests proving
  cross-worker aggregation, worker-exit file removal, lifespan-shutdown
  removal, and stale dead-worker file semantics (AP-3 unit suite includes
  them).
- `docs/observability.md`: new "Multi-worker metrics aggregation" section
  (aggregate behavior, original metric names, lifespan-shutdown cleanup
  rationale with the empirical SIGTERM re-raise finding, SIGKILL stale-file
  semantics, Celery per-process boundary, `/metrics` auth policy unchanged).
- `oap/orders/168-a-multiworker-metrics-exposure-repair.md`: strategic work
  order committed unchanged (byte-identical strategic bytes).
- `oap/active`: `168-a` (activated order pointer).
- `oap/reports/168-a-multiworker-metrics-exposure-repair.md`: this report
  (report-only commit).

Not touched (verified by diff scope, AP-5): `Dockerfile` (compose-level env
sufficed), `nginx/`, `migrations/`, `.github/`, `pyproject.toml`,
`scripts/` (including the entire production-qualification harness), all other
`app/slaif_gateway/` modules, and all other `tests/`.

## Files changed (full, including the report commit)
- `app/slaif_gateway/metrics.py`
- `app/slaif_gateway/main.py`
- `docker-compose.production.yml`
- `docker-compose.yml`
- `docs/observability.md`
- `tests/unit/test_metrics_multiprocess.py`
- `oap/orders/168-a-multiworker-metrics-exposure-repair.md`
- `oap/active`
- `oap/reports/168-a-multiworker-metrics-exposure-repair.md`

`git diff --name-only 08ca421bee1ddca62078302b910e8be88cf705be
2468d01f588d03cc726b0a524f4146f8f6bc51b6` lists exactly the first eight
paths (the report file appears only in the report commit); nothing else.

## Acceptance-criteria evidence
- **AP-1** — Two consecutive full no-keep production-harness runs on the
  exact PR-head tree (clean-room checkout of `2468d01f588d03cc726b0a524f4146f8f6bc51b6`
  at `/tmp/obj168-cleanroom/`, fresh venv, command
  `.venv/bin/python scripts/production-qualification/run.py`, default
  no-keep, no code/environment change between the two runs):
  - Run A: project `slaif-151-1521317-1a5005`, exact output line
    `RESULT=OK`, 16/16 phases OK, `metrics.positive_sample_present` all four
    families `true` (`gateway_http_requests_total`,
    `gateway_provider_requests_total`, `gateway_tokens_total`,
    `gateway_cost_eur_total`), `restore_counts` restored==source
    (`gateway_keys: 2`, `usage_ledger: 15`), no-keep cleanup all true
    (`containers_by_compose_label`, `networks`, `runtime`, `volumes` all
    `true`; `remaining_networks: []`, `remaining_volumes: []`).
  - Run B: project `slaif-151-1546169-b5c76b`, exact output line
    `RESULT=OK`, 16/16 phases OK, identical per-family positive metrics
    evidence, restore counts restored==source, no-keep cleanup all true.
  Full stdout/stderr captured locally at `/tmp/obj168-harness-runA.log` and
  `/tmp/obj168-harness-runB.log` (local artifacts, not committed).
- **AP-2** — Non-weakening proof: prometheus_client 0.26.0 mmap MPM encodes
  per-process identity in the mmap file names, so the (old name → new name)
  mapping for the exactly four exercised families is the **identity
  bijection**: `gateway_http_requests_total → gateway_http_requests_total`,
  `gateway_provider_requests_total → gateway_provider_requests_total`,
  `gateway_tokens_total → gateway_tokens_total`, `gateway_cost_eur_total →
  gateway_cost_eur_total`. The harness diff is therefore zero lines:
  `git diff 08ca421bee1ddca62078302b910e8be88cf705be
  2468d01f588d03cc726b0a524f4146f8f6bc51b6 -- scripts/production-qualification/`
  outputs nothing (0 lines). The `EXERCISED_METRIC_FAMILIES` tuple and
  `positive_prometheus_sample_counts()` in `run.py` are byte-identical to the
  base; the positive-sample requirement (`count < 1` → `authorized /metrics
  did not expose positive samples for every exercised family`) is unchanged;
  the unauthenticated-denial check is unchanged and passed in both runs
  (`readiness.public_denied: true`). No other harness phase, check, or
  cleanup logic changed. The F3 bounded family-name update was a contingency
  for MPM-renamed metrics and was empirically unnecessary.
- **AP-3** — Exact local matrix counts on the PR head (clean-room venv,
  Python 3.12.3): full unit suite via `scripts/test-unit-parallel.sh`
  (`pytest tests/unit -n 20 --dist loadscope`): **4047 passed / 1 failed /
  0 skipped** in 72.11s — the new aggregation tests included; the single
  failure is the known VM-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (VM `codex --version` = `codex-cli 0.154.0` vs fixture pin
  `codex-cli 0.148.0`), labeled environment-only per the order, not chased.
  Full PostgreSQL integration suite via
  `.venv/bin/python -m pytest tests/integration -q` with a user-owned
  disposable PostgreSQL 16 instance on `127.0.0.1:5433`
  (`TEST_DATABASE_URL=postgresql+asyncpg://slaif:***@127.0.0.1:5433/slaif_gateway_test`,
  database dropped/recreated before the run): **224 passed / 1 skipped /
  0 failed** — the skip is the local-VM `pg_dump` CLI limitation on the
  `TEST_DATABASE_URL` form (identical environment-only skip as the 167
  baseline; in-container backup/restore passed in both Q3 runs). Official
  client E2E via `.venv/bin/python -m pytest tests/e2e -q` on a
  drop/recreated database: **54 passed / 0 failed / 0 skipped** under
  `openai==3.9.0`; pip-freeze proof: `openai==3.9.0`, `httpx==0.28.1`,
  `httpx2==2.13.0`, `httpcore2==2.13.0`, `httpcore==1.0.9`,
  `pydantic==2.13.5`, `respx==0.23.1`, `pytest==9.1.1`,
  `prometheus_client==0.26.0`, `gunicorn==26.2.0`, `uvicorn==0.53.0`,
  `fastapi==0.141.1`, `starlette==1.6.0`.
- **AP-4** — All nine required checks SUCCESS on the implementation head
  `2468d01f588d03cc726b0a524f4146f8f6bc51b6` (re-queried with
  `gh api repos/ulfe-lmi/slaif-api-gateway/commits/2468d01f588d03cc726b0a524f4146f8f6bc51b6/check-runs`
  at report time; the final-head re-query after the report-only commit was
  performed per the order — see CI gate state): `Unit, lint, and migration
  head` 105165090248; `Documentation hygiene` 105165090185;
  `OpenAI-compatible E2E tests` 105165089925; `Playwright browser smoke`
  105165090230; `Docker Compose smoke` 105165090192; `PostgreSQL
  integration tests` 105165090331; `Analyze (javascript-typescript)`
  105165078531; `Analyze (python)` 105165078382; `Analyze Python`
  105165088286 — all `completed`/`success`. (An additional out-of-required-set
  `CodeQL` analysis also completed `success`, run ID 105165395050.)
- **AP-5** — Diff scope: `git diff --name-only 08ca421bee1ddca62078302b910e8be88cf705be
  2468d01f588d03cc726b0a524f4146f8f6bc51b6` lists exactly the eight allowed
  paths (`app/slaif_gateway/metrics.py`, `app/slaif_gateway/main.py`,
  `docker-compose.production.yml`, `docker-compose.yml`,
  `docs/observability.md`, `tests/unit/test_metrics_multiprocess.py`,
  `oap/orders/168-a-multiworker-metrics-exposure-repair.md`, `oap/active`),
  plus this report file in the report commit. `nginx/`, `migrations/`,
  `.github/`, `pyproject.toml`, `Dockerfile`, all other `app/` modules, and
  all other `tests/` are untouched. Zero product behavior change: the
  touched implementation files contain only metrics-registry wiring,
  worker-metric-file cleanup, and Compose volume/env for the metrics
  directory; no routing, policy, quota, accounting, pricing,
  compatibility, authentication, or error-shape code was modified, and the
  `/metrics` route's auth policy is unchanged (unauthenticated denial
  verified in both Q3 runs).
- **AP-6** — `docs/observability.md` "Multi-worker metrics aggregation"
  states: both shipped topologies set `PROMETHEUS_MULTIPROC_DIR` to a tmpfs
  mount on the `api` service; MPM mode is active in the API worker group; a
  single `MultiProcessCollector` exposes **the aggregate of all live API
  workers under the original metric names**; a single authorized `/metrics`
  scrape reflects the whole worker group deterministically; graceful-exit
  cleanup runs during application lifespan shutdown (with the empirical
  UvicornWorker SIGTERM re-raise rationale), SIGKILL stale files can only
  inflate never reduce the aggregate, and each Compose project gets a fresh
  tmpfs mount at container start; the `/metrics` authentication/IP policy is
  unchanged; and the boundary statement: "Celery worker and scheduler
  processes are not part of the API worker group. Their `slaif_gateway.metrics`
  updates (e.g. reconciliation counters) remain per-process in memory and are
  not aggregated or exposed; that boundary is pre-existing and out of scope
  for the API metrics surface." `python scripts/check_documentation.py` on
  the final tree printed `DOCUMENTATION_CHECK=OK files=81`.
- **AP-7** — This immutable report contains the literal implementation head
  SHA `2468d01f588d03cc726b0a524f4146f8f6bc51b6` and
  `Report publication commit: SELF`; the report-only commit changes only
  `oap/reports/168-a-multiworker-metrics-exposure-repair.md`, has the
  recorded implementation head as first parent, and is pushed and verified as
  the remote PR head before the two-byte `OK` is written to the response
  FIFO.

## Local verification (clean-room venv, clean-room tree unless noted)
- Clean room: `/tmp/obj168-cleanroom/` detached checkout,
  `git rev-parse HEAD` = `2468d01f588d03cc726b0a524f4146f8f6bc51b6`,
  `git status --short` empty, fresh `.venv` (Python 3.12.3, freeze lines in
  AP-3). All Q3/Q4 candidate code ran from the clean room only.
- Q2 (clean room): `.venv/bin/python -m ruff check app tests` (ruff 0.15.16)
  → `All checks passed!`; `.venv/bin/python -m alembic heads` →
  `0024_quota_reservation_accounting_facts (head)` (unchanged, no migration);
  `.venv/bin/python scripts/check_documentation.py` →
  `DOCUMENTATION_CHECK=OK files=81`; `git diff --check` → clean.
- Q3: `.venv/bin/python scripts/production-qualification/run.py` twice
  consecutively (default no-keep), full stdout/stderr captured at
  `/tmp/obj168-harness-runA.log` and `/tmp/obj168-harness-runB.log`; both
  runs `RESULT=OK`, 16/16 phases, per-family positive metrics, restore
  counts restored==source (`gateway_keys: 2`, `usage_ledger: 15`), no-keep
  cleanup all true, no remaining harness containers, networks, or volumes.
- Q4: `scripts/test-unit-parallel.sh` (20 xdist workers, log
  `/tmp/obj168-q4-unit.log`); `.venv/bin/python -m pytest tests/integration
  -q` (log `/tmp/obj168-q4-integration-5433.log`); `.venv/bin/python -m
  pytest tests/e2e -q` (log `/tmp/obj168-q4-e2e-5433.log`);
  `codex --version` → `codex-cli 0.154.0` (only to label the known VM-only
  unit failure).
- Q5: `gh api repos/ulfe-lmi/slaif-api-gateway/commits/2468d01f588d03cc726b0a524f4146f8f6bc51b6/check-runs`
  — nine required checks, all `completed`/`success` (run IDs above).
- `main.py` structural guard: 68 lines (< 70); `tests/unit/test_main_app_structure.py`
  green in the unit suite.

## Negative evidence
- Non-weakening bijection: identity mapping for exactly the four exercised
  families (MPM keeps original names); `git diff` against the base over
  `scripts/production-qualification/` is 0 lines; positive-sample
  requirement and unauthenticated-denial check byte-identical and re-proven
  by both green Q3 runs.
- Zero product-behavior change: touched files are limited to
  metrics-registry wiring, worker-metric-file cleanup, Compose metrics
  volume/env, the new metrics unit tests, and the observability doc (full
  list under AP-5); no accounting, schema, routing, policy, pricing,
  compatibility, authentication, or error-shape change; PostgreSQL remains
  quota/accounting truth (untouched).
- No `--keep` residue: no `--keep` run was performed at all; both harness
  runs used default no-keep mode with automatic cleanup, and post-run
  verification found no leftover harness containers, networks, or volumes
  (`remaining_networks: []`, `remaining_volumes: []` in both runs).
- No live provider calls: `RUN_UPSTREAM_TESTS` unset throughout; no provider
  credentials present or used; the harness's socket-level
  `qualification-double` provider only.
- No secrets in artifacts: the report contains no generated secret, key,
  password, prompt, completion, or canary value (the disposable PostgreSQL
  password is redacted as `***`); only safe booleans, counts, timing values,
  project names, SHAs, and CI run IDs are recorded.
- No release, tag, or deployment to any real system; no production/staging
  database; no email delivery; no GitHub-settings change; no Dependabot
  interaction. Open PRs #250 and #224 remain untouched.
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md` (this objective commits no dated verification
  record; all evidence is in this report).

## CI gate state on the final head
- All nine required checks on the implementation head
  `2468d01f588d03cc726b0a524f4146f8f6bc51b6` (first parent of the final
  report-only head, which adds only this report file and touches no code,
  workflow, or configuration path covered by any check): SUCCESS.
  Run IDs: `Unit, lint, and migration head` 105165090248; `Documentation
  hygiene` 105165090185; `OpenAI-compatible E2E tests` 105165089925;
  `Playwright browser smoke` 105165090230; `Docker Compose smoke`
  105165090192; `PostgreSQL integration tests` 105165090331; `Analyze
  (javascript-typescript)` 105165078531; `Analyze (python)` 105165078382;
  `Analyze Python` 105165088286. Per AP-4, the final head's check runs are
  re-queried after publication of the report-only commit, and that re-query
  is a mandatory gate before the response-FIFO `OK` signal is sent (a report
  commit cannot carry the run IDs of its own commit; the re-query result is
  part of this objective's execution record and is independently re-verified
  on GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #305 was left OPEN for strategic review
and the human maintainer's delegated merge authority; no merge was
performed, and no merge-related GitHub action of any kind was taken by this
objective.
