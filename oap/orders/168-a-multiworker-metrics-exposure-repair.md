# OAP Work Order — 168-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Repair the exact defect that Objective 167 found and recorded: in the
shipped two-worker production topology, `app/slaif_gateway/metrics.py`
registers in-process `prometheus_client` counters/histograms (no
multiprocess mode), the production image runs gunicorn with two Uvicorn
workers (`Dockerfile` CMD `--workers 2`), and the NGINX upstream
(`nginx/production.conf`, `proxy_pass http://api:8000`) has no keepalive
pooling — so a single authorized `/metrics` scrape exposes only the
counters of whichever worker serves it, and the three provider-call
families (`gateway_provider_requests_total`, `gateway_tokens_total`,
`gateway_cost_eur_total`) read zero when the scrape lands on the other
worker. The Objective-167 record
(`docs/verification/2026-09-17-current-main-integrated-qualification.md`,
P2.3) documents this on candidate `9bb81cb9...` with verdict
`RESULT=NOT-QUALIFIED`.

Objective: make cross-worker metrics aggregation part of the shipped
production topology so that the harness's privacy-phase metrics assertion
— a single authorized `/metrics` scrape exposes positive samples for every
exercised family — holds **deterministically** under the shipped two-worker
topology, and prove it with two consecutive full production-harness runs
(`RESULT=OK` each) on the PR-head tree. Then the next objective (169) can
requalify the exact current `main` for the RC posture ahead of the human
release decision.

This is a bounded observability repair. It changes no product behavior,
no accounting, no routing, no policy, and no OpenAI-compatibility surface.
It must not weaken the qualification assertion in any way.

## Reconciled authority and current state

Verified 2026-09-17 by the strategic model against live GitHub and the
shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (base): `08ca421bee1ddca62078302b910e8be88cf705be`,
  merge of PR #304 (Objective 167), merged 2026-09-17T08:30:55Z; parents
  exactly `9bb81cb9...` and final report `4b56deee...`. Post-merge
  main-branch checks: all nine emitted checks SUCCESS on `08ca421b`
  (verified by the strategic model).
- Objective 167 is terminal and verified (PR #304 merged; zero code diff;
  dated record `RESULT=NOT-QUALIFIED` with the exact defect evidence, P2.3).
  Shared `oap/active` starts at terminal `167-a`. Objective 168 is unused:
  no `168-*` order, report, branch, or PR exists.
- Open PRs are exactly #250 (Dependabot; openai half superseded by #303;
  ruff half retained as update signal; strategic comment posted) and #224
  (Dependabot github-actions, stale). Both remain untouched by this
  objective.
- Defect evidence (from the immutable 167 record, P2.3): run 1
  `slaif-151-1288081-b8488c` `RESULT=FAIL` (`ERROR=authorized /metrics did
  not expose positive samples for every exercised family`; 15/16 phases
  OK); run 2 `slaif-151-1308665-c76beb` `RESULT=OK` (16/16) in the
  identical environment with zero environment change; root cause
  candidate-side, non-deterministic per run; pre-existing (zero commits in
  `8f2813bf..9bb81cb` touch `metrics.py`, its call sites,
  `scripts/production-qualification/`, or `Dockerfile`); PostgreSQL
  accounting intact in the failing run.
- Current metrics code: `app/slaif_gateway/metrics.py` (277 lines)
  registers module-level `Counter`/`Histogram` objects on the default
  `prometheus_client` registry (no `PROMETHEUS_MULTIPROC_DIR`, no MPM
  prefix, no cleanup); `prometheus_response_body()` returns
  `generate_latest()`; call sites span `api/middleware.py`,
  `api/metrics.py`, the gateways (`chat_completion_gateway.py`,
  `audio_gateway.py`, `embeddings_gateway.py`, `realtime_gateway.py`),
  `workers/tasks_reconciliation.py`, and others. The `/metrics` route
  denies unauthenticated access (verified in the 167 record: "public
  unauthenticated metrics access denied").
- Production topology: `Dockerfile` CMD `gunicorn
  slaif_gateway.main:app --worker-class uvicorn.workers.UvicornWorker
  --bind 0.0.0.0:8000 --workers 2 --timeout 120`;
  `docker-compose.production.yml` (secrets, TLS, NGINX edge, internal
  network); `nginx/production.conf` upstream without keepalive pooling.
  Dev topology `docker-compose.yml` runs the same gunicorn two-worker
  command via `WEB_CONCURRENCY:-2`.
- Harness: `scripts/production-qualification/run.py` (default no-keep;
  prints `RESULT=OK` or `RESULT=FAIL`); its `privacy` phase performs an
  authorized in-container `/metrics` scrape and requires positive samples
  for every exercised family (`gateway_http_requests_total`,
  `gateway_provider_requests_total`, `gateway_tokens_total`,
  `gateway_cost_eur_total`).
- Known execution-VM environment facts: Docker 29.1.3, Compose 2.40.3,
  disposable local PostgreSQL `TEST_DATABASE_URL` harness, and the
  environment-only unit failure
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (VM `codex-cli 0.154.0` vs fixture pin `0.148.0`) — label it, do not
  chase it.
- `docs/observability.md` documents the metrics surface; the qualified
  official-client SDK pin is `openai==3.9.0` (Objective 166).

## PR contract

- Base: `main` at `08ca421bee1ddca62078302b910e8be88cf705be`.
- Branch: `oap/168-multiworker-metrics-exposure-repair`.
- Title: `obj168: repair multi-worker metrics exposure in production topology`.
- One new PR for `168-a`; later `168-b`... rounds amend the same PR.

## Required design and changes

F1 — Cross-worker aggregation for the API (gunicorn) process group.
Expected approach: `prometheus_client` **multiprocess mode** —
`PROMETHEUS_MULTIPROC_DIR` pointing at a shared `tmpfs` volume mounted in
both gunicorn workers of the production compose project; an MPM metric
prefix; `generate_latest` over the multiprocess registry in
`prometheus_response_body()`; and multiprocess metric cleanup on worker
exit (gunicorn `worker_exit` hook, which runs for UvicornWorker
processes). An equally minimal deterministic mechanism is permitted only
if it is proven equivalent in the report (same guarantee, no assertion
weakening, no new external dependency on the metrics path).

F2 — Compose/Docker changes. `docker-compose.production.yml`: add the
shared `tmpfs` volume and the required environment for the `api` service
only. `Dockerfile`: no change unless the entrypoint/CMD must carry the
environment (prefer compose-level env). `docker-compose.yml` (dev path):
apply the same volume/env to the `api` service so dev and production
topologies behave identically; the CI `Docker Compose smoke` job must
remain green.

F3 — Harness family-name update (bounded, no weakening). Multiprocess
mode exposes MPM-prefixed metric names. Update
`scripts/production-qualification/run.py` **only** where the exercised
family names are referenced, so the same four families are asserted under
their new deterministic names. The report must prove non-weakening:
(old name -> new name) bijection for exactly these four families, the
assertion logic otherwise byte-identical (diff shown), the positive-sample
requirement unchanged, and the unauthenticated-denial check unchanged.
No other harness phase, check, or cleanup logic may change.

F4 — Unit tests. Add focused unit tests proving cross-worker aggregation:
two simulated worker registries writing into one `PROMETHEUS_MULTIPROC_DIR`
(under `tmp_path`), then a single aggregated scrape shows the summed
positive values for the exercised families; plus the existing metrics unit
tests remain green (updated for the MPM names where they assert names).

F5 — Documentation. `docs/observability.md` (or wherever the `/metrics`
surface is documented): state the multi-worker aggregation behavior, the
MPM-prefixed exposed names, and — honestly — that Celery worker/scheduler
process counters remain per-process (out of scope for this objective,
pre-existing boundary) and that the scrape now reflects the aggregate of
the API worker group. Include the documentation-impact statement in the
report.

## Allowed paths

Exactly these (plus the OAP protocol files):

- `app/slaif_gateway/metrics.py`
- `app/slaif_gateway/main.py` and `app/slaif_gateway/api/metrics.py`
  (only where the multiprocess registry/wiring requires it)
- `Dockerfile` (only if F1 requires an entrypoint/CMD/env change)
- `docker-compose.production.yml` (api service volume/env only)
- `docker-compose.yml` (api service volume/env only)
- `scripts/production-qualification/run.py` (F3 bounded family-name
  update only)
- `tests/unit/` (metrics aggregation tests; name updates in existing
  metrics tests where required)
- `docs/observability.md`
- `oap/orders/168-a-multiworker-metrics-exposure-repair.md` (unchanged
  strategic bytes), `oap/active`,
  `oap/reports/168-a-multiworker-metrics-exposure-repair.md`

No other path may appear in the diff.

## Explicit exclusions (non-goals)

- No assertion weakening: the privacy-phase metrics requirement stays
  "every exercised family positive on a single authorized scrape"; the
  family set is the same four (renamed per F3 bijection); the
  unauthenticated-denial check is unchanged.
- No Celery worker/scheduler aggregation (their counters remain
  per-process; document, do not fix).
- No product behavior change: no routing, policy, quota, accounting,
  pricing, compatibility, authentication, or error-shape change; the
  `/metrics` route's auth policy is unchanged.
- No new runtime dependency on the metrics path (no Redis/PostgreSQL
  state for metrics; the only new element is the `tmpfs` volume and
  `prometheus_client`'s existing multiprocess mode).
- No migrations, workflow-file changes, release/tag, deployment,
  GitHub-settings change, or Dependabot interaction.
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md` (immutable historical records).
- No real provider calls (`RUN_UPSTREAM_TESTS` unset); no `--keep`
  harness mode; no secrets in any artifact.

## Qualification design (required sequence)

Q1 — Implement F1-F5 on the PR-head tree.
Q2 — Local fast proof: unit tests (including the new aggregation tests)
green; `ruff check app tests` (ruff 0.15.16) clean; `alembic heads`
unchanged (no migration expected); `python scripts/check_documentation.py`
OK.
Q3 — Determinism proof (the core acceptance): from a fresh clean-room
clone of the PR head (or a clean detached checkout of the exact PR-head
SHA with a fresh venv, as in Objective 167), run
`.venv/bin/python scripts/production-qualification/run.py` (default
no-keep) **twice consecutively**. Both runs must print `RESULT=OK` with
16/16 phases OK, per-family positive metrics evidence in both runs,
restore-verifier counts matching, and no-keep cleanup checks all true in
both runs. If either run fails: capture the exact output, do not weaken
anything, diagnose (candidate fix defect vs environment), and either
repair within this objective's scope and re-run (both runs must still
succeed) or report the blocker with evidence.
Q4 — Full matrix (clean-room venv, disposable local PostgreSQL):
`scripts/test-unit-parallel.sh`; `python -m pytest tests/integration -q`;
`python -m pytest tests/e2e -q` (54 tests under `openai==3.9.0`).
Q5 — Publish, open the PR, and wait until all nine required checks
succeed on the final head.

## Acceptance criteria

- **AP-1** — Two consecutive full no-keep production-harness runs on the
  exact PR-head tree both print `RESULT=OK` (16/16 phases each), with
  per-family positive metrics evidence recorded for both runs and all
  no-keep cleanup checks true in both runs; the report lists both project
  names and both exact `RESULT=` lines.
- **AP-2** — Non-weakening proof: the (old name -> new name) bijection for
  exactly the four exercised families, the harness diff confined to those
  name references (shown in the report), positive-sample requirement
  unchanged, unauthenticated-denial check unchanged, and no other harness
  logic changed.
- **AP-3** — Exact local matrix counts on the PR head: full unit suite
  (new aggregation tests included; the known VM-only codex-CLI failure, if
  present, labeled with `codex --version` proof), full PostgreSQL
  integration suite, and the 54-test official-client E2E matrix under
  `openai==3.9.0` with pip-freeze proof.
- **AP-4** — All nine required checks SUCCESS on the final PR head
  (re-queried after the report-only commit).
- **AP-5** — Diff scope: exactly the allowed paths; `nginx/`,
  `migrations/`, `.github/`, `pyproject.toml`, all other `app/` modules,
  and all other `tests/` untouched (prove by `git diff --name-only`
  listing); no product behavior change (the report states this with the
  touched-file list).
- **AP-6** — `docs/observability.md` (or the named metrics doc) states the
  aggregation behavior, the MPM-prefixed names, and the Celery
  per-process boundary honestly; `python scripts/check_documentation.py`
  prints `DOCUMENTATION_CHECK=OK files=<n>`.
- **AP-7** — One immutable report
  `oap/reports/168-a-multiworker-metrics-exposure-repair.md` with literal
  implementation head SHA and `Report publication commit: SELF`; the final
  report-only commit changes only that report file, has the recorded
  implementation head as first parent, and is pushed and verified as the
  remote PR head before signalling `OK` on the response FIFO.

## Verification and evidence commands

Run and report exactly (clean-room environment for Q3/Q4 as in
Objective 167):

- Q2: `python -m pytest tests/unit -q` (or `scripts/test-unit-parallel.sh`
  for the full parallel run), `python -m ruff check app tests`,
  `alembic heads`, `python scripts/check_documentation.py`,
  `git diff --check`.
- Q3: `.venv/bin/python scripts/production-qualification/run.py` twice
  consecutively (default no-keep); capture full stdout/stderr of both
  runs.
- Q4: `scripts/test-unit-parallel.sh`; `python -m pytest tests/integration
  -q`; `python -m pytest tests/e2e -q`; `codex --version` (only to label
  the known VM-only failure if it appears).
- CI: the nine required checks on the final head (record check names and
  run IDs).

## Security, privacy, accounting, and boundaries

- No secrets, keys, prompts, completions, or canary values in any changed
  file or report; the harness uses only generated credentials/canaries
  inside its disposable project.
- PostgreSQL remains quota/accounting truth; no accounting code, schema,
  or behavior is touched (the metrics fix is observation-only).
- The `/metrics` authentication policy is unchanged (unauthenticated
  access remains denied). No trust, identity, secret, or content boundary
  widened. Local/hosted tool boundaries untouched.
- No production/staging system, no real provider, no real email, no
  production database. Disposable local PostgreSQL and the harness's
  unique Compose projects only.

## Stop / escalation conditions

- If `prometheus_client` multiprocess mode proves incompatible with the
  UvicornWorker process lifecycle after genuine investigation (e.g.,
  worker-exit cleanup demonstrably does not run or counters are
  demonstrably lost/leaked across the two required runs), and no equally
  minimal deterministic mechanism exists without weakening the assertion
  or adding a metrics-state dependency (Redis/PostgreSQL): stop, report
  `ESCALATION` with the exact evidence of both dead ends. Do not weaken
  the assertion and do not ship a single-worker regression.
- If a Q3 run fails for a candidate-fix defect: repair within scope and
  re-run until two consecutive `RESULT=OK` runs; if that is not
  achievable, report the blocker with full evidence.
- Suffix rounds (`168-b`...) are for bounded correction of this objective
  only (CI failures, review findings, verification gaps).

## Setup authority

- Clean-room clone/checkout of the PR head plus fresh venv under `/tmp`
  (disposable) for Q3/Q4; disposable local PostgreSQL via the standard
  `TEST_DATABASE_URL` harness; Docker daemon use for the harness projects
  and their cleanup.
- No provider credentials; no network egress beyond the GitHub clone,
  PyPI, and Docker Hub image pulls; no release/deploy; no Dependabot
  interaction; no GitHub settings.

## OAP report requirements

Standard report fields per `OAP-COMMUNICATION-coding-agent.md`:
identifier, work-order file, numeric objective, PR mode, status,
executive summary, authoritative GitHub state (PR number, state, branch,
base, head, starting SHA, implementation head, `SELF` topology), changes
made, files changed, acceptance-criteria evidence (AP-1 through AP-7),
local verification, negative evidence (non-weakening bijection; zero
product-behavior change; no `--keep` residue; no live provider calls; no
secrets in artifacts), CI gate state on the final head, and the
merge-not-performed statement.
