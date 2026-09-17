# OAP Coding-Agent Report — 167-a

## Work order
- Identifier: 167-a
- Work-order file: `oap/orders/167-a-current-main-integrated-qualification.md`
- Numeric objective: 167
- PR mode: CREATE_NEW_PR

## Status
COMPLETE

Verdict of the dated record: `RESULT=NOT-QUALIFIED` (the objective's
decisive answer; see Executive summary). No capability implemented, nothing
fixed, no release decision made.

## Executive summary
Answered the objective's decisive question — is exact `main`
`9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` (merge of PR #303 / Objective
166) verified for the intended RC/deployment posture? — with fresh, dated,
machine-verifiable evidence. P1: clean-room clone at the exact candidate SHA
with a fresh `.[dev]` venv (`openai==3.9.0`, `httpx==0.28.1`, `httpx2==2.13.0`,
`httpcore2==2.13.0`, `pydantic==2.13.5`, `respx==0.23.1`, `pytest==9.1.1`);
all candidate code ran from the clean room only. P2: the candidate's own
production-appliance qualification harness (default no-keep) **run 1
`RESULT=FAIL`** — 15/16 phases OK, `privacy` failed with `ERROR=authorized
/metrics did not expose positive samples for every exercised family` (project
`slaif-151-1288081-b8488c`); the mandatory reproduction **run 2 `RESULT=OK`**
with all 16 phases, restore verifier restored==source
(`gateway_keys: 2`, `usage_ledger: 15`), and no-keep cleanup all true in both
runs (project `slaif-151-1308665-c76beb`). Classification: **not
environment-only** (no port/daemon/leftover-project cause; identical
environment passed run 2 with zero environment change) and **candidate-side,
non-deterministic per run**: in-process `prometheus_client` counters (no
multiprocess mode) under the shipped two-worker gunicorn production
topology (`Dockerfile` CMD `--workers 2`; NGINX upstream without keepalive
pooling) mean the harness's single authorized `/metrics` scrape exposes only
the counters of whichever worker serves it. The middleware counts every
request it serves (including the scrape itself), so
`gateway_http_requests_total` is guaranteed positive on the scraping worker;
the three provider-call families
(`gateway_provider_requests_total`, `gateway_tokens_total`,
`gateway_cost_eur_total`) read zero when the scrape lands on the other
worker. Pre-existing, not a new regression: zero commits in
`8f2813bf..9bb81cb` touch `app/slaif_gateway/metrics.py`, any metrics call
site, `scripts/production-qualification/`, or `Dockerfile`; the 2026-08-24
passing run passed the same check on the same code, harness, and topology.
PostgreSQL accounting was intact in the failing run (usage ledger carried
actual costs and tokens; restore verifier matched) — this is a
metrics-exposure (observability) defect, not an accounting defect. P3: unit
**4043 passed / 1 failed / 0 skipped** (the one failure is the known VM-only
codex-CLI-version case, `codex --version` = `codex-cli 0.154.0` vs fixture
pin `codex-cli 0.148.0`, labeled environment-only); PostgreSQL integration
**224 passed / 1 skipped / 0 failed** (skip = local-VM `pg_dump` CLI cannot
consume the `TEST_DATABASE_URL` form; in-container harness backup/restore
passed in both P2 runs; counts re-confirmed on a second `-rs` run);
official-client E2E **54 passed / 0 failed / 0 skipped** under the pinned
`openai==3.9.0` (pip-freeze proof); browser smoke cited from the green CI
job at the candidate SHA (not run locally, per the order). P4: all nine
required CI checks re-queried at report time on the candidate SHA — all
SUCCESS. The dated record
`docs/verification/2026-09-17-current-main-integrated-qualification.md` plus
one `docs/verification/README.md` index row carries the full per-phase
tables, classification, and limitations. Because
`RESULT=QUALIFIED-RC-POSTURE` requires all P2 phases OK for the candidate,
the record's verdict is the single line `RESULT=NOT-QUALIFIED`; fixing the
metrics-exposure finding is a separate numeric objective (none was made
here).

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 304
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/304
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/167-current-main-integrated-qualification`
- Starting remote SHA: `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc`
- Implementation head SHA: 41fcb5d5b9ae02e1dd9654a75d7dac85d56dcf28
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
    - `026ea7e59f41ceef35bcfa0c40c21605c605398b` `obj167: fresh integrated qualification of current main for RC posture`
  - `41fcb5d5b9ae02e1dd9654a75d7dac85d56dcf28` `oap: activate 167-a current main integrated qualification` (carries the strategic-authored order and `oap/active` unchanged)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `docs/verification/2026-09-17-current-main-integrated-qualification.md`:
  new dated record for the named candidate commit (P1 freeze, P2 both runs
  with full per-phase tables, restore counts, cleanup checks, exact failure
  output and classification, P3 exact counts with the environment-only
  labels, P4 CI table with run IDs, deployment-path statement, single
  verdict line `RESULT=NOT-QUALIFIED`, and the required limitations).
- `docs/verification/README.md`: exactly one appended index row describing
  the record as dated evidence for the named candidate commit only.
- `oap/orders/167-a-current-main-integrated-qualification.md`: strategic
  work order committed unchanged (byte-identical strategic bytes).
- `oap/active`: `167-a` (activated order pointer).
- `oap/reports/167-a-current-main-integrated-qualification.md`: this report
  (report-only commit).

## Files changed (full, including the report commit)
- `docs/verification/2026-09-17-current-main-integrated-qualification.md`
- `docs/verification/README.md`
- `oap/orders/167-a-current-main-integrated-qualification.md`
- `oap/active`
- `oap/reports/167-a-current-main-integrated-qualification.md`

`git diff --name-only` against the starting SHA lists exactly these five
paths; nothing else.

## Acceptance-criteria evidence
- **AP-1** — P1 clean-room proof (clone location `/tmp/obj167-cleanroom/`,
  exact HEAD SHA, clean status, freeze lines) and P2 evidence (exact command,
  both unique project names, exact `RESULT=` lines, full per-phase tables,
  restore-verifier counts, no-keep cleanup checks, exact failure output, and
  the environment-only/candidate-side classification with reproduction
  evidence) are in the dated record, section P2.
- **AP-2** — Exact local matrix counts in the record, section P3: unit 4043
  passed / 1 failed (VM-only, `codex --version` recorded) / 0 skipped;
  integration 224 passed / 1 skipped (local-VM pg_dump limitation) / 0
  failed; E2E 54 passed / 0 failed / 0 skipped with pip-freeze proof under
  `openai==3.9.0`; browser smoke cited from CI run 105111680605 (SUCCESS).
- **AP-3** — P4 CI table in the record: all nine required check names on the
  candidate SHA `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` with run IDs
  (105111680700, 105111680837, 105111680644, 105111680605, 105111680746,
  105111680437, 105111682686, 105111683034, 105111680382) and conclusions,
  re-queried at report time.
- **AP-4** — The dated record exists at the allowed path with the exact
  candidate SHA as evidence boundary, the single unambiguous verdict line
  `RESULT=NOT-QUALIFIED`, and the required limitations (mocked provider
  double; not a release decision, production certification, security review,
  compliance finding, or SLA approval; RC2 scope asserted only as the
  scope-lock document's current classification). The index row is appended.
  `python scripts/check_documentation.py` on the final tree printed
  `DOCUMENTATION_CHECK=OK files=81`. No document claims certification,
  compliance, SLA, real-provider qualification, or current-state authority
  beyond the named commit.
- **AP-5** — Diff scope: `git diff --name-only` against the starting SHA
  lists exactly the five allowed paths (record, README index, order,
  `oap/active`, this report). Zero changes under `app/`, `tests/`,
  `scripts/`, `.github/`, `deploy/`, `nginx/`, `migrations/`,
  `pyproject.toml`, or any compose file.
- **AP-6** — The record's verdict is exactly `RESULT=NOT-QUALIFIED`, with
  the exact failing phase table (P2.1: `privacy` FAIL with the exact error
  line; all other 15 phases OK in both runs) and the P4 table (nine/ nine
  SUCCESS). `RESULT=QUALIFIED-RC-POSTURE` was not usable because it
  requires all P2 phases OK, which run 1 does not establish.
- **AP-7** — This immutable report contains the literal implementation head
  SHA and `Report publication commit: SELF`; the report-only commit changes
  only `oap/reports/167-a-current-main-integrated-qualification.md`, has the
  recorded implementation head as first parent, and is pushed and verified
  as the remote PR head before the two-byte `OK` is written to the response
  FIFO.

## Local verification (clean-room venv, clean-room tree unless noted)
- P1: `git rev-parse HEAD` = candidate SHA; `git status --short` empty;
  fresh venv `.[dev]`; freeze lines as listed above (re-frozen immediately
  before the E2E run with identical results).
- P2 run 1: `RESULT=FAIL`, `ERROR=authorized /metrics did not expose
  positive samples for every exercised family`; 15/16 phases OK; project
  `slaif-151-1288081-b8488c`; restore counts restored==source
  (`gateway_keys: 2`, `usage_ledger: 15`); no-keep cleanup checks all true.
- P2 run 2: `RESULT=OK`; 16/16 phases OK; project
  `slaif-151-1308665-c76beb`; all four metrics families positive; restore
  counts restored==source; no-keep cleanup checks all true; no remaining
  networks or volumes.
- P3: unit 4043 passed / 1 failed (VM-only) / 0 skipped in 70.80s via
  `scripts/test-unit-parallel.sh`; integration 224 passed / 1 skipped / 0
  failed (re-confirmed on a second `-rs` run) via
  `python -m pytest tests/integration -q` with
  `TEST_DATABASE_URL=postgresql+asyncpg://slaif:***@127.0.0.1:5432/slaif_gateway_test`
  (drop/recreated per run); E2E 54 passed / 0 skipped / 0 failed via
  `python -m pytest tests/e2e -q` on a drop/recreated database;
  `codex --version` → `codex-cli 0.154.0`.
- P4: `gh api repos/ulfe-lmi/slaif-api-gateway/commits/9bb81cb960b6d3ba5373425cbe50cdcc670b93dc/check-runs`
  at report time — nine required checks, all `completed`/`success` (run IDs
  in the record).
- `python scripts/check_documentation.py` (shared worktree, final tree):
  `DOCUMENTATION_CHECK=OK files=81`.
- `git diff --check`: clean.

## Negative evidence
- Zero code diff: `git diff --name-only` against the starting SHA lists
  exactly the five allowed paths; `app/`, `tests/`, `scripts/`, `.github/`,
  `deploy/`, `nginx/`, `migrations/`, `pyproject.toml`, and all compose
  files are untouched (no harness modification of any kind).
- No `--keep` residue: no `--keep` run was performed at all; both harness
  runs used default no-keep mode with automatic cleanup, and post-run
  verification found no leftover harness containers, networks, or volumes.
- No live provider calls: `RUN_UPSTREAM_TESTS` unset throughout, no provider
  credentials present or used; the harness's socket-level provider double
  only.
- No secrets in artifacts: the record and this report contain no generated
  secret, key, password, prompt, completion, or canary value (the harness's
  own privacy scans passed in both runs); only safe booleans, counts,
  timing values, and the two harness project names are recorded.
- No release, tag, or deployment to any real system; no production/staging
  database; no email delivery; no GitHub-settings change; no Dependabot
  interaction. Open PRs #250 and #224 remain untouched.
- No edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md`.

## CI gate state on the final head
- All nine required checks on final head
  `41fcb5d5b9ae02e1dd9654a75d7dac85d56dcf28`: SUCCESS.
  Run IDs: `Unit, lint, and migration head` 105126988881; `Documentation
  hygiene` 105126988909; `OpenAI-compatible E2E tests` 105126988998;
  `Playwright browser smoke` 105126988712; `Docker Compose smoke`
  105126988997; `PostgreSQL integration tests` 105126988877; `Analyze
  (javascript-typescript)` 105126983561; `Analyze (python)` 105126983894;
  `Analyze Python` 105126988383.

## Merge-not-performed statement
The coding agent never merges. PR #304 was left OPEN for strategic review
and the human maintainer's delegated merge authority; no merge was
performed, and no merge-related GitHub action of any kind was taken by this
objective.
