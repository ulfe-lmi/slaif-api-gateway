# OAP Coding-Agent Report — 173-a

## Work order
- Identifier: 173-a
- Work-order file: `oap/orders/173-a-current-main-integrated-requalification-2b61312e.md`
- Numeric objective: 173
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Verdict
`RESULT=QUALIFIED-RC-POSTURE`

## Executive summary
Performed the fresh, verification-only, integrated requalification of the
exact remote `main` `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (merge of
PR #309 / Objective 172; `main` has not moved since) — the commit a
release decision would actually point at — applying the strict 170
acceptance set plus the new P0 runtime-tree identity proof anchoring the
candidate to the 170-qualified tree `1043c3f4`. No capability was
implemented, no defect was fixed, and no release decision was made.

Verdict: `RESULT=QUALIFIED-RC-POSTURE`. All acceptance predicates hold,
with the complete evidence recorded in the dated record
`docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`:

- **AP-0 — SATISFIED.** The P0 runtime-tree identity holds: the exact
  strategic candidate-to-candidate range
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7..2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
  is exactly 12 paths (dev pins, dated records, index rows, one
  compatibility-doc sentence, OAP order/report/active files), and the
  runtime-surface `git diff --name-only` over `app tests scripts
  .github migrations nginx Dockerfile docker-compose.yml
  docker-compose.production.yml Makefile` is empty — the runtime tree is
  byte-identical to the 170-qualified candidate (verbatim outputs in the
  record).
- **AP-1 — SATISFIED.** Two consecutive default-no-keep
  production-appliance harness runs from a fresh clean-room checkout of
  the exact PR head, with no code or environment change between the
  runs: Run A (project `slaif-151-1924777-02dacd`) and Run B (project
  `slaif-151-1955105-264d12`), each with the exact `RESULT=OK` line and
  16/16 phases, all four exercised metric families positive on the
  single authorized scrape, `restore_counts` restored==source
  (`gateway_keys: 2`, `usage_ledger: 15`), no-keep cleanup all true with
  empty remaining networks/volumes, and `readiness.public_denied: true`.
  The transient availability-class 503 of the abandoned 169 attempt
  (P2.3) did not recur (`recovery_503_count: 0` in both runs).
- **AP-2 — SATISFIED.** Exact P3 matrix counts with only the two labeled
  environment-only non-passes: unit **4047 passed / 1 failed / 0
  skipped** (the failure is the known VM-only codex-CLI case,
  `codex --version` = `codex-cli 0.154.0` vs fixture pin `0.148.0`);
  integration **224 passed / 1 skipped / 0 failed** (the skip is the
  local-VM `pg_dump` DSN-form limitation, identical to the
  167/168/170/172 baseline); official-client E2E **54 passed / 0 failed /
  0 skipped** under `openai==3.14.1`.
- **AP-3 — SATISFIED.** All nine required checks `success` on the exact
  PR head at both the activation head and the implementation head, and
  the candidate's own ten emitted main-branch checks are `success`.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 310
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/310
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/173-current-main-integrated-requalification-2b61312e`
- Starting remote SHA (base): `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
- 170-qualified candidate (P0 identity anchor):
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7`
- Implementation head SHA: `33f811b679bd0148c46ac7b422c7e36eeb4e9b79`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived
  from GitHub)
- Implementation commits pushed before the report commit:
    - `3e6a213d2f8ed1553494513c80b2080245f6e692` `oap: activate 173-a current main integrated requalification 2b61312e` (carries the strategic-authored order and `oap/active`)
    - `ddfbc7026e5321b907382743c0b07dee0e177fdc` `obj173: fresh integrated requalification naming the exact current main candidate` (carries the dated record and the single README index row)
    - `33f811b679bd0148c46ac7b422c7e36eeb4e9b79` `obj173: correct the 170-relationship merge enumeration in the dated record` (documentation-only correction to the new record, before the report commit; see the transparency note)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`
  (new dated record): candidate SHA, exactly one verdict line
  `RESULT=QUALIFIED-RC-POSTURE`, complete P0–P4 evidence (P0 verbatim
  identity outputs; P1 clean-room proof and freeze lines; P2 two
  consecutive `RESULT=OK` 16/16 runs with every AP-1 field; P3 exact
  matrix counts; P4 candidate and PR-head CI tables), the required
  "Relationship to the 170 qualification" note, the SBOM status note,
  the deployment-path statement, and the required limitation sentences.
- `docs/verification/README.md`: exactly one appended index row for the
  new record.
- `oap/orders/173-a-current-main-integrated-requalification-2b61312e.md`:
  strategic work order committed unchanged (byte-identical strategic
  bytes; template-conforming, `PR mode: `CREATE_NEW_PR`` literal on line
  3).
- `oap/active`: `173-a` (activated order pointer).
- `oap/reports/173-a-current-main-integrated-requalification-2b61312e.md`:
  this report (report-only commit).

Not touched (verified by diff scope, AP-5): everything outside the five
allowed paths — in particular zero changes under `app/`, `tests/`,
`scripts/` (including the entire production-qualification harness and
`tests/unit/test_oap_governance.py`), `.github/`, `migrations/`,
`nginx/`, `Dockerfile`, `docker-compose*.yml`, `pyproject.toml`,
`sbom/`, and all existing `docs/verification/2026-*` files and
`docs/beta-readiness.md`.

## Files changed (full, including the report commit)
- `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`
- `docs/verification/README.md`
- `oap/orders/173-a-current-main-integrated-requalification-2b61312e.md`
- `oap/active`
- `oap/reports/173-a-current-main-integrated-requalification-2b61312e.md`

`git diff --name-only 2b61312e0eb569aa7c6f953f52e35b44e84b91c1
33f811b679bd0148c46ac7b422c7e36eeb4e9b79` lists exactly the first four
paths (the report file appears only in the report commit); nothing else.

## Acceptance-criteria evidence
- **AP-0 — SATISFIED (runtime-tree identity, verbatim from the clean
  room at HEAD = exact PR head `3e6a213d2f8ed1553494513c80b2080245f6e692`).**
  - `git diff --stat 1043c3f42fb46f06a8d7952273739cefb9de6cc7..HEAD`:
    13 files changed, 2972 insertions(+), 5 deletions(-) — the
    strategic 12 paths plus the 173-a order file itself (expected OAP
    addition at the PR head; `oap/active` is a shared path). Verbatim
    output in the record (P0).
  - The strategic exact candidate-to-candidate range `git diff --stat
    1043c3f42fb46f06a8d7952273739cefb9de6cc7..2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
    reports exactly `12 files changed, 2554 insertions(+), 5 deletions(-)`
    — matching the strategic machine verification recorded in the order.
  - `git diff --name-only 1043c3f42fb46f06a8d7952273739cefb9de6cc7..HEAD
    -- app tests scripts .github migrations nginx Dockerfile
    docker-compose.yml docker-compose.production.yml Makefile`: **empty**
    (0 lines) — the runtime surface is byte-identical to the
    170-qualified candidate.
  - No discrepancy: AP-0 satisfied.
- **AP-1 — SATISFIED (decisive determinism property, both runs).**
  - Command (twice consecutively from the clean-room tree, default
    no-keep, no code or environment change between the runs):
    `env -u DATABASE_URL -u TEST_REDIS_URL -u RUN_UPSTREAM_TESTS -u
    OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY
    ENABLE_EMAIL_DELIVERY=false .venv/bin/python
    scripts/production-qualification/run.py`.
  - Run A (project `slaif-151-1924777-02dacd`): exact `RESULT=OK` line;
    16/16 phases OK (phase table with per-phase seconds in the record);
    `metrics.positive_sample_present` all four exercised families
    `true` on the single authorized scrape
    (`gateway_http_requests_total`, `gateway_provider_requests_total`,
    `gateway_tokens_total`, `gateway_cost_eur_total`); `restore_counts`
    restored==source (`gateway_keys: 2`, `usage_ledger: 15`); no-keep
    cleanup all true with `remaining_networks: []`,
    `remaining_volumes: []`; `readiness.public_denied: true`;
    concurrency `overlap_status: 429`
    (`concurrency_rate_limit_exceeded`,
    `overlap_provider_forward_delta: 0`, accounting unchanged),
    `following_status: 200`, `recovery_503_count: 0`, slot released;
    16-row accounting lifecycle: 9 `finalized`, 5 `failed` with
    reservation `released` (including one 503 provider-failure sample),
    2 `estimated`. Full stdout/stderr: `/tmp/obj173-harness-runA.log`.
  - Run B (project `slaif-151-1955105-264d12`): same evidence shape,
    every AP-1 per-run field holds (phase table with per-phase seconds
    in the record). Full stdout/stderr: `/tmp/obj173-harness-runB.log`.
  - The transient availability-class 503 of the abandoned 169 attempt
    (P2.3, not observed in 170) did not recur in either run.
- **AP-2 — SATISFIED (exact P3 matrix, clean room, every non-pass
  accounted for).**
  - Unit: `scripts/test-unit-parallel.sh` — **4047 passed / 1 failed /
    0 skipped** in 70.70s. The single failure is the labeled VM-only
    case `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
    (`codex_version_mismatch`: `codex --version` → `codex-cli 0.154.0`
    vs fixture pin `codex-cli 0.148.0`); labeled environment-only per
    the order and not chased.
  - Integration: `python -m pytest tests/integration -q` with
    `TEST_DATABASE_URL` on the fresh user-owned disposable PostgreSQL 16
    (16.15) on `127.0.0.1:5433` (database dropped/recreated immediately
    before the run) — **224 passed / 1 skipped / 0 failed** (exact
    tally of the 225-character progress line: 224 pass dots + 1 skip,
    zero fail/error markers). The skip is the local-VM `pg_dump`
    CLI limitation on the `TEST_DATABASE_URL` form
    (`tests/integration/test_backup_restore_postgres.py:42`), identical
    to the 167/168/170/172 baseline (in-container backup/restore
    re-proven in both P2 runs).
  - E2E: `python -m pytest tests/e2e -q` on a drop/recreated database —
    **54 passed / 0 failed / 0 skipped** under `openai==3.14.1`
    (the 54-test official-client matrix; P1 freeze lines recorded).
- **AP-3 — SATISFIED (CI gates, all nine required checks
  `completed`/`success`).**
  - Candidate `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` main-branch
    checks (re-queried live against the GitHub API on 2026-09-17): all
    ten emitted checks `success` — `Unit, lint, and migration head`
    105269969558; `Documentation hygiene` 105269969826;
    `OpenAI-compatible E2E tests` 105269969770; `Playwright browser
    smoke` 105269969765; `Docker Compose smoke` 105269969774;
    `PostgreSQL integration tests` 105269969259; `Analyze
    (javascript-typescript)` 105269976365; `Analyze (python)`
    105269975660; `Analyze Python` 105269969446; `update-pip-graph`
    105270000064.
  - Activation head `3e6a213d2f8ed1553494513c80b2080245f6e692` (record
    P4): all nine required checks `success` — `Unit, lint, and
    migration head` 105274257033; `Documentation hygiene` 105274256882;
    `OpenAI-compatible E2E tests` 105274256944; `Playwright browser
    smoke` 105274256616; `Docker Compose smoke` 105274256983;
    `PostgreSQL integration tests` 105274257039; `Analyze
    (javascript-typescript)` 105274252827; `Analyze (python)`
    105274252409; `Analyze Python` 105274257375.
  - Implementation head `33f811b679bd0148c46ac7b422c7e36eeb4e9b79`:
    all nine required checks `success` — `Unit, lint, and migration
    head` 105285681719; `Documentation hygiene` 105285681792;
    `OpenAI-compatible E2E tests` 105285681901; `Playwright browser
    smoke` 105285681919; `Docker Compose smoke` 105285681911;
    `PostgreSQL integration tests` 105285681645; `Analyze
    (javascript-typescript)` 105285673293; `Analyze (python)`
    105285673668; `Analyze Python` 105285682719. `Unit, lint, and
    migration head` is `success` on both PR heads because the committed
    order is template-conforming (byte-identical strategic bytes,
    `PR mode: `CREATE_NEW_PR`` literal on line 3), so the candidate's
    governance test passes on this PR head (169 finding P4.1 does not
    recur).
- **AP-4 — SATISFIED.** The dated record exists at the allowed path,
  names the exact candidate SHA
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` in its prose, contains
  exactly one verdict line `RESULT=QUALIFIED-RC-POSTURE` (verified by
  literal count on the committed record), contains the required
  "Relationship to the 170 qualification" note, the SBOM status note,
  and the required limitation sentences (mocked-upstream qualification
  only; not a real-provider run, release decision, security
  certification, or production approval; dated evidence for the named
  candidate commit only). `python scripts/check_documentation.py` on the
  final tree prints `DOCUMENTATION_CHECK=OK files=84` — exactly one more
  than the base tree, for the new dated record.
- **AP-5 — SATISFIED.** Diff scope vs base
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`: exactly the five allowed
  paths; zero changes under `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, and zero changes to `Dockerfile`,
  `docker-compose*.yml`, `pyproject.toml`, `sbom/`, or any existing
  documentation file.
- **AP-6 — SATISFIED as specified.** `RESULT=QUALIFIED-RC-POSTURE` is
  permitted because AP-0, AP-1, AP-2 (with only the two labeled
  environment-only exceptions), and AP-3 all hold as specified; no
  predicate was softened, re-labeled, or averaged; the 151-d/167
  boundary-strictness precedent applies.
- **AP-7 — SATISFIED.** This immutable report contains the literal
  candidate SHA `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` and
  `Report publication commit: SELF`; the report-only commit changes only
  `oap/reports/173-a-current-main-integrated-requalification-2b61312e.md`,
  has the recorded implementation head as first parent, and is pushed
  and verified as the remote PR head before the two-byte `OK` is written
  to the response FIFO. The P4 re-query on the final head is performed
  as the mandatory gate before that OK (see CI gate state).

## Local verification (clean-room venv, clean-room tree unless noted)
- P0: from the clean-room checkout of the exact PR head
  `3e6a213d2f8ed1553494513c80b2080245f6e692`, both `git diff` outputs
  captured verbatim (record P0; local files
  `/tmp/obj173-p0-diffstat.txt`, `/tmp/obj173-p0-runtime.txt`).
- P1: fresh clone `/tmp/obj173-cleanroom/`, detached checkout of
  `3e6a213d2f8ed1553494513c80b2080245f6e692`, `git status --short`
  empty, fresh `.venv` (Python 3.12.3, `.[dev]`); freeze lines recorded
  in the record (P1), `openai==3.14.1` and `ruff==0.16.7` as required
  (full freeze at `/tmp/obj173-freeze.txt`); Docker 29.1.3 (build
  29.1.3-0ubuntu3~24.04.2) and Compose 2.40.3+ds1-0ubuntu1~24.04.1
  (actual outputs); fresh user-owned disposable PostgreSQL 16 (16.15)
  under `/tmp/obj173-pg/` on `127.0.0.1:5433` (own role/database;
  database dropped/recreated immediately before each DB-backed suite;
  the 5432 system cluster was not used); fresh `asyncpg.connect`
  `AUTH_OK` for the disposable role before P3. All candidate code ran
  from the clean room only.
- P2: `.venv/bin/python scripts/production-qualification/run.py` (default
  no-keep) twice consecutively; full stdout/stderr captured at
  `/tmp/obj173-harness-runA.log` and `/tmp/obj173-harness-runB.log`.
- P3: `scripts/test-unit-parallel.sh` (log `/tmp/obj173-p3-unit.log`);
  `python -m pytest tests/integration -q` (log
  `/tmp/obj173-p3-integration.log`); `python -m pytest tests/e2e -q`
  (log `/tmp/obj173-p3-e2e.log`); `codex --version` → `codex-cli
  0.154.0` (recorded to label the known VM-only unit case).
- P4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<sha>/check-runs` for the
  candidate, the activation head, and the implementation head (run IDs
  above and in the record); final-head re-query after the report-only
  commit per AP-7 (mandatory gate; see CI gate state).
- Documentation gates on the final tree: `python
  scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=84`;
  `git diff --check` → clean.
- Environment-only disclosures (labeled, with proof): (1) VM
  `codex-cli 0.154.0` vs fixture pin `0.148.0` (one labeled unit case);
  (2) local-VM `pg_dump` DSN-form skip (identity recorded in AP-2);
  (3) local `psql` TCP password authentication to the disposable cluster
  misbehaves client-side on this VM while socket authentication and
  asyncpg (the suites' client) TCP authentication succeeded
  end-to-end — classified client-side/environment-only, no effect on
  the evidence chain. Host Redis at `127.0.0.1:6379` (PONG) served the
  integration suite with `TEST_REDIS_URL` unset, per the documented
  default.

## Transparency note (pre-report documentation correction)
Before the report commit, one documentation-only correction was made to
the new dated record (commit
`33f811b679bd0148c46ac7b422c7e36eeb4e9b79`): the "Relationship to the
170 qualification" note had described the intermediate merges as
"exactly two" (171, 172), omitting the merged publication of Objective
170's own report (PR #307), which the 12-path P0 diff itself includes.
The note now enumerates all three intermediate merges
(PR #307, PR #308, PR #309), each CI-verified at merge time. The
correction changed no evidence, no count, no verdict, and touched no
file other than the new record; it is the implementation head and is
CI-verified 9/9 (run IDs above).

## Negative evidence
- No code change of any kind: the implementation diff touches only the
  documentation paths plus the strategic order and `oap/active`; zero
  product behavior, accounting, routing, policy, pricing,
  compatibility, authentication, error-shape, schema, or migration
  change; `pyproject.toml` is byte-identical to the candidate;
  `tests/unit/test_oap_governance.py` and the entire
  production-qualification harness are byte-identical (untouched);
  PostgreSQL remains quota/accounting truth (untouched).
- No defect fixes: P0–P4 exposed no candidate-side finding; the only
  non-passes are the two labeled environment-only items (recorded, not
  chased, not suppressed).
- No SBOM edit or regeneration: `sbom/cyclonedx.json` is byte-identical
  to the candidate (stale 2026-08-23 snapshot, excluded from this
  order; regeneration remains a release-time decision of the human
  maintainer).
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
- No cherry-pick, import, or re-publication of any file from the
  abandoned 169 branch or any other closed/abandoned objective branch;
  no edits to any existing `docs/verification/2026-*` file or to
  `docs/beta-readiness.md`; no new tests, fixtures, or harness
  modifications.
- No release, tag, or deployment to any real system; no
  production/staging database; no real email; no GitHub-settings action
  (branch protection, rulesets, required checks); no Dependabot
  interaction.
- No PR interaction: PR #224 and every other PR were not touched in any
  way; PR #306 (abandoned Objective 169) was not re-opened or modified;
  PR #250 remains closed.
- No new product capability of any kind.

## CI gate state on the final head
- Implementation head `33f811b679bd0148c46ac7b422c7e36eeb4e9b79` (first
  parent of the final report-only head, which adds only this report file
  and touches no code, workflow, or configuration path covered by any
  check): all nine required checks SUCCESS — `Unit, lint, and migration
  head` 105285681719; `Documentation hygiene` 105285681792;
  `OpenAI-compatible E2E tests` 105285681901; `Playwright browser
  smoke` 105285681919; `Docker Compose smoke` 105285681911;
  `PostgreSQL integration tests` 105285681645; `Analyze
  (javascript-typescript)` 105285673293; `Analyze (python)`
  105285673668; `Analyze Python` 105285682719. Per AP-7, the final
  head's check runs are re-queried after publication of the report-only
  commit, and that re-query is a mandatory gate before the response-FIFO
  `OK` signal is sent (a report commit cannot carry the run IDs of its
  own commit; the re-query result is part of this objective's execution
  record and is independently re-verified on GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #310 was left OPEN for strategic
review and the human maintainer's delegated merge authority; no merge
was performed, and no merge-related GitHub action of any kind was taken
by this objective.
