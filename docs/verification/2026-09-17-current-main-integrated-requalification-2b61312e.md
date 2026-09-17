# Objective 173 current-main integrated requalification (candidate 2b61312e)

Date: 2026-09-17 (Europe/Ljubljana; UTC timestamps as recorded by the runs)

Candidate (evidence boundary): `main`
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (merge of PR #309 / Objective
172), verified remote `main` at execution time.

This is a fresh, verification-only, integrated qualification of that exact
candidate — the current `main` itself — for the intended RC/deployment
posture, with the Objective 167/168/170 determinism property — two
consecutive default-no-keep production-appliance harness runs from a
fresh clean-room checkout, both `RESULT=OK` — as the decisive test, plus
the P0 runtime-tree identity proof anchoring the candidate to the
170-qualified tree. It implements no capability, fixes nothing, and makes
no release decision. All candidate code was executed only from the
clean-room clone (P1); nothing was executed from the shared worktree.
No file from any closed/abandoned objective branch was imported or
re-published. The dated records
[`2026-09-17-current-main-integrated-requalification.md`](2026-09-17-current-main-integrated-requalification.md)
(Objective 170),
[`2026-09-17-openai-sdk-3141-requalification.md`](2026-09-17-openai-sdk-3141-requalification.md)
(Objective 172), and
[`2026-09-17-current-main-integrated-qualification.md`](2026-09-17-current-main-integrated-qualification.md)
(Objective 167) are immutable and are referenced, not rewritten.

## Verdict

`RESULT=QUALIFIED-RC-POSTURE`

The P0 runtime-tree identity holds (the candidate's runtime surface is
byte-identical to the 170-qualified candidate `1043c3f4`; the full
delta is dev-pin/documentation/OAP-record paths only — AP-0). Two
consecutive default-no-keep production-appliance harness runs from a
fresh clean-room checkout of the exact candidate — Run A (project
`slaif-151-1924777-02dacd`) and Run B (project
`slaif-151-1955105-264d12`), with no code or environment change between
the runs — each completed with the exact `RESULT=OK` line, 16/16 phases
OK, all four exercised metric families positive on the single authorized
scrape, `restore_counts` restored==source, no-keep cleanup all true with
empty remaining networks/volumes, and `readiness.public_denied: true`
(AP-1). The P3 matrix matched the exact expected counts with only the
two labeled environment-only non-passes (AP-2), and all nine required
checks concluded `success` on the exact PR head (AP-3). AP-6 therefore
permits the qualified verdict. No code was modified.

## P0 — Runtime-tree identity proof (scope anchor)

Verbatim from the clean room (HEAD = exact PR head
`3e6a213d2f8ed1553494513c80b2080245f6e692`):

- `git diff --stat
  1043c3f42fb46f06a8d7952273739cefb9de6cc7..HEAD` (PR head):

```text
 docs/openai-compatibility.md                       |   4 +-
 ...9-17-current-main-integrated-requalification.md | 327 ++++++++++++++++
 .../2026-09-17-openai-sdk-3141-requalification.md  | 199 ++++++++++
 docs/verification/README.md                        |  20 +
 oap/active                                         |   2 +-
 ...70-a-current-main-integrated-requalification.md | 361 ++++++++++++++++++
 oap/orders/171-a-ruff-0-16-7-policy-pinned-bump.md | 345 +++++++++++++++++
 .../172-a-openai-sdk-3141-requalification.md       | 396 +++++++++++++++++++
 ...ent-main-integrated-requalification-2b61312e.md | 418 +++++++++++++++++++++
 ...70-a-current-main-integrated-requalification.md | 345 +++++++++++++++++
 .../171-a-ruff-0-16-7-policy-pinned-bump.md        | 272 ++++++++++++++
 .../172-a-openai-sdk-3141-requalification.md       | 275 ++++++++++++++
 pyproject.toml                                     |  13 +-
 13 files changed, 2972 insertions(+), 5 deletions(-)
```

  The 13th path relative to the strategic 12-path verification is the
  173-a order file itself (expected OAP addition at the PR head;
  `oap/active` is a shared path). The strategic exact
  candidate-to-candidate range `git diff --stat
  1043c3f42fb46f06a8d7952273739cefb9de6cc7..2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
  reports exactly `12 files changed, 2554 insertions(+), 5 deletions(-)`
  — matching the strategic machine verification recorded in the order.
- `git diff --name-only
  1043c3f42fb46f06a8d7952273739cefb9de6cc7..HEAD -- app tests scripts
  .github migrations nginx Dockerfile docker-compose.yml
  docker-compose.production.yml Makefile`: **empty** (0 lines) — the
  runtime surface is byte-identical to the 170-qualified candidate.

No discrepancy: AP-0 satisfied.

## P1 — Clean-room candidate

- Fresh full clone: `/tmp/obj173-cleanroom/`, detached checkout of
  `3e6a213d2f8ed1553494513c80b2080245f6e692` (the exact PR head;
  candidate code identical to remote `main`
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` plus the OAP
  order/active files only, per P0).
- `git rev-parse HEAD` = PR head SHA; `git status --short` empty.
- Fresh venv at `/tmp/obj173-cleanroom/.venv` (Python 3.12.3) with
  `.[dev]` installed.
- Freeze lines (P1 install):

```text
fastapi==0.141.1
gunicorn==26.2.0
httpcore==1.0.9
httpcore2==2.13.0
httpx==0.28.1
httpx2==2.13.0
openai==3.14.1
prometheus_client==0.26.0
pydantic==2.13.5
pytest==9.1.1
respx==0.23.1
ruff==0.16.7
starlette==1.6.0
uvicorn==0.53.0
```

  (`openai==3.14.1` and `ruff==0.16.7` as required by the order.)

Environment: Linux WSL2 VM; Docker version 29.1.3, build
29.1.3-0ubuntu3~24.04.2; Docker Compose version
2.40.3+ds1-0ubuntu1~24.04.1 (actual outputs recorded at execution);
fresh user-owned disposable PostgreSQL 16 (16.15) instance at
`127.0.0.1:5433` for P3 (fresh `initdb` under `/tmp/obj173-pg/`; own
roles/database; the database was dropped/recreated immediately before
each DB-backed suite; the 5432 system cluster was not used), host Redis
at `127.0.0.1:6379`. `RUN_UPSTREAM_TESTS` unset throughout; no provider
credentials present or used; `ENABLE_EMAIL_DELIVERY=false`;
`DATABASE_URL`, `TEST_REDIS_URL`, and all upstream key variables
explicitly unset from the run environments.

Environment notes (honesty disclosures, no effect on the evidence
chain): local `psql` TCP password authentication to the disposable
cluster misbehaves client-side on this VM, while socket authentication
and — decisively — asyncpg (the client the suites use) TCP
authentication succeeded for the disposable role on `127.0.0.1:5433`
(fresh `asyncpg.connect` `AUTH_OK` before P3). Classified as a
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

### P2.1 — Run A (project `slaif-151-1924777-02dacd`): `RESULT=OK`

Exact output line: `RESULT=OK`; 16/16 phases OK.

| Phase | Seconds | Status |
| --- | --- | --- |
| prepare | 0.33 | OK |
| tls | 0.17 | OK |
| compose | 91.19 | OK |
| operator-configuration | 29.9 | OK |
| async-worker-and-scheduler-liveness | 5.92 | OK |
| chat-and-responses | 2.06 | OK |
| provider-failures-and-disconnects | 2.14 | OK |
| redis-and-timeout-controls | 11.93 | OK |
| redis-concurrency | 9.63 | OK |
| api-termination-and-cli-reconciliation | 20.77 | OK |
| persistence | 46.49 | OK |
| backup-restore | 10.87 | OK |
| privacy-input-boundaries | 0.59 | OK |
| quota-and-key-controls | 7.69 | OK |
| admin-dashboard-session | 0.33 | OK |
| privacy | 32.81 | OK |

- `metrics.positive_sample_present` on the single authorized scrape: all
  four exercised families `true` (`gateway_http_requests_total`,
  `gateway_provider_requests_total`, `gateway_tokens_total`,
  `gateway_cost_eur_total`).
- `restore_counts` restored==source: `gateway_keys: 2`, `usage_ledger: 15`.
- No-keep cleanup: `containers_by_compose_label`, `networks`, `runtime`,
  `volumes` all `true`; `remaining_networks: []`,
  `remaining_volumes: []`.
- `readiness.public_denied: true`.
- Concurrency evidence: `overlap_status: 429`
  (`concurrency_rate_limit_exceeded`, `overlap_provider_forward_delta: 0`,
  accounting unchanged), `following_status: 200`,
  `recovery_503_count: 0`, slot released.
- Accounting lifecycle sample (16 ledger rows): 9 `finalized`, 5
  `failed` with reservation `released` (including one 503
  provider-failure sample), 2 `estimated`.
- Full stdout/stderr captured locally at
  `/tmp/obj173-harness-runA.log` (local artifact, not committed).

### P2.2 — Run B (project `slaif-151-1955105-264d12`): `RESULT=OK`

Exact output line: `RESULT=OK`; 16/16 phases OK.

| Phase | Seconds | Status |
| --- | --- | --- |
| prepare | 0.07 | OK |
| tls | 0.19 | OK |
| compose | 33.97 | OK |
| operator-configuration | 27.45 | OK |
| async-worker-and-scheduler-liveness | 5.95 | OK |
| chat-and-responses | 1.98 | OK |
| provider-failures-and-disconnects | 2.79 | OK |
| redis-and-timeout-controls | 16.28 | OK |
| redis-concurrency | 9.05 | OK |
| api-termination-and-cli-reconciliation | 22.72 | OK |
| persistence | 47.96 | OK |
| backup-restore | 12.29 | OK |
| privacy-input-boundaries | 0.58 | OK |
| quota-and-key-controls | 8.81 | OK |
| admin-dashboard-session | 0.42 | OK |
| privacy | 32.65 | OK |

- Every AP-1 per-run field holds for Run B with the same evidence shape
  as P2.1: all four metric families positive on the single authorized
  scrape; `restore_counts` restored==source (`gateway_keys: 2`,
  `usage_ledger: 15`); no-keep cleanup all true with empty remaining
  networks/volumes; `readiness.public_denied: true`; concurrency
  `overlap_status: 429` / `following_status: 200` /
  `recovery_503_count: 0` / slot released; 16-row accounting lifecycle
  with 9 `finalized`, 5 `failed` with reservation `released` (including
  one 503 provider-failure sample), 2 `estimated`.
- Full stdout/stderr captured locally at
  `/tmp/obj173-harness-runB.log` (local artifact, not committed).

## P3 — Candidate test matrix (clean-room venv, disposable local PostgreSQL)

- Full unit suite via `scripts/test-unit-parallel.sh`
  (`.venv/bin/python -m pytest tests/unit -n 20 --dist loadscope`):
  **4047 passed / 1 failed / 0 skipped** in 70.70s. The single failure
  is the known VM-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (`codex_version_mismatch`: VM `codex --version` = `codex-cli 0.154.0`
  vs fixture pin `codex-cli 0.148.0`; `codex --version` output
  recorded), labeled environment-only per the order and not chased.
- Full PostgreSQL integration suite via
  `.venv/bin/python -m pytest tests/integration -q` with
  `TEST_DATABASE_URL` pointed at the user-owned disposable PostgreSQL 16
  on `127.0.0.1:5433` (database dropped/recreated immediately before the
  run): **224 passed / 1 skipped / 0 failed**. The skip is the local-VM
  `pg_dump` CLI limitation on the `TEST_DATABASE_URL` form
  (`tests/integration/test_backup_restore_postgres.py:42`), identical to
  the 167/168/170/172 baseline (in-container backup/restore re-proven in
  both P2 runs). The captured log's final summary line was lost to a
  tee/pipe flush race; the counts are the exact tally of the
  225-character pytest progress line (224 pass dots + 1 skip, zero
  fail/error markers).
- Official-client E2E via `.venv/bin/python -m pytest tests/e2e -q` on a
  drop/recreated database: **54 passed / 0 failed / 0 skipped** under
  `openai==3.14.1` (the 54-test official-client matrix; P1 freeze lines
  above). Same progress-line tally method (54 dots, no skip/fail
  markers).

## P4 — Exact CI state

Two states are recorded. (1) The candidate's own main-branch check runs,
verified at the merge and re-queried live against the GitHub API on
2026-09-17 — all ten emitted checks `completed`/`success` on
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (the nine required checks
plus `update-pip-graph`): `Unit, lint, and migration head`
105269969558; `Documentation hygiene` 105269969826;
`OpenAI-compatible E2E tests` 105269969770; `Playwright browser smoke`
105269969765; `Docker Compose smoke` 105269969774; `PostgreSQL
integration tests` 105269969259; `Analyze (javascript-typescript)`
105269976365; `Analyze (python)` 105269975660; `Analyze Python`
105269969446; `update-pip-graph` 105270000064.

(2) The exact PR head of this objective as of this record,
`3e6a213d2f8ed1553494513c80b2080245f6e692` (the activation commit
carrying this order and `oap/active`): all nine required checks
`completed`/`success` (queried 2026-09-17; the mandatory final-head
re-query after the report-only commit per AP-7 is recorded in the
objective report):

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| Unit, lint, and migration head | completed | success | 105274257033 |
| Documentation hygiene | completed | success | 105274256882 |
| OpenAI-compatible E2E tests | completed | success | 105274256944 |
| Playwright browser smoke | completed | success | 105274256616 |
| Docker Compose smoke | completed | success | 105274256983 |
| PostgreSQL integration tests | completed | success | 105274257039 |
| Analyze (javascript-typescript) | completed | success | 105274252827 |
| Analyze (python) | completed | success | 105274252409 |
| Analyze Python | completed | success | 105274257375 |

## Relationship to the 170 qualification

Objective 170 qualified candidate `1043c3f42fb46f06a8d7952273739cefb9de6cc7`
(PR #305 merge) with the qualified-RC-posture verdict recorded in its
dated record on `main`. Between that candidate and this candidate
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1`, `main` advanced through the
merged publication of Objective 170 itself (PR #307: dated record,
README index row, OAP order/report files, and the `oap/active` pointer;
no runtime change) and through Objectives 171 (PR #308: `ruff==0.16.7`
+ explicit `[tool.ruff.lint]` policy pin; zero code change) and 172
(PR #309: `openai==3.14.1` qualified dev pin + one compatibility-doc
sentence + dated record; zero code change). Every intermediate merge
was CI-verified at merge time. P0 proves the runtime tree of this
candidate is byte-identical to the 170-qualified candidate over
`app/`, `tests/`, `scripts/`, `.github/`, `migrations/`, `nginx/`,
`Dockerfile`, `docker-compose.yml`, `docker-compose.production.yml`, and
`Makefile` (the full 12-path candidate-to-candidate delta, which
includes 170's own publication, is dev-pin/documentation/OAP-record
paths only). This objective
therefore re-proves the strict 170 acceptance set on the exact commit a
release decision would actually point at. The transient 503 class
observed in the abandoned 169 attempt (and not in 170) did not recur in
either P2 run here (`recovery_503_count: 0` in both).

## SBOM status

`sbom/cyclonedx.json` is a point-in-time snapshot (timestamp
2026-08-23, rc1 era, specVersion 1.5, no `tools` signature) that is
stale w.r.t. the 166/171/172 dev pins. It was excluded from this order
(its generation method is not recorded in the repository, so a
regenerated artifact would be methodologically non-comparable); its
regeneration remains a release-time decision of the human maintainer.
The file is byte-identical on this branch.

## Deployment-path statement

The documented dev Compose path is mechanically covered at this commit
by the CI `Docker Compose smoke` job (success: run ID 105274256983 on
the PR head, run ID 105269969774 on the candidate). The production
topology (`docker-compose.production.yml`: TLS, NGINX edge, secrets,
internal network, gunicorn API, Celery worker/scheduler, 168 metrics
tmpfs mount on the `api` service) is unchanged by 171/172 and covered by
the P2 harness runs, whose `tls` and `compose` phases passed in both
runs.

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
  candidate commit `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` only; it
  does not transfer to later commits.
- The qualified verdict rests on: the P0 runtime-tree identity; two
  consecutive green no-keep production-appliance runs (P2); the exact
  P3 matrix modulo only the two labeled environment-only non-passes
  (the VM-only codex-version unit case; the local-VM pg_dump skip); and
  9/9 required checks `success` on the PR head (P4).
