# OAP Coding-Agent Report — 172-a

## Work order
- Identifier: 172-a
- Work-order file: `oap/orders/172-a-openai-sdk-3141-requalification.md`
- Numeric objective: 172
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Verdict
`OUTCOME=A`

## Executive summary
Deliberately requalified the Gateway's declared official OpenAI Python
client compatibility contract against the current stable SDK release
`openai==3.14.1`, starting from the qualified baseline `openai==3.9.0`
(Objective 166, `OUTCOME=A`), in a fresh clean-room, dual-phase
environment (Phase B baseline, Phase C candidate; the only environment
change between phases is the openai pin). The decisive 54-test
official-client E2E matrix is **54 passed / 0 failed / 0 skipped in both
phases** (Phase B establishes harness soundness; Phase C is the
candidate claim), and the Phase C ripple check (full unit + integration)
is green modulo only the two labeled environment-only non-passes. No
P3 failure classification was triggered and no class-1 harness fix was
required.

Consequence (PASS branch): the dev/test pin moves
`"openai==3.9.0"` → `"openai==3.14.1"` (single `pyproject.toml` line, the
only functional edit) and the single qualification sentence in
`docs/openai-compatibility.md` now names `openai==3.14.1` and points at
the new dated record
`docs/verification/2026-09-17-openai-sdk-3141-requalification.md` (plus
exactly one README index row). No production code changed (`app/`
byte-identical); no other dependency changed (the `ruff==0.16.7` pin and
the `[tool.ruff.lint]` policy pin are untouched); the 3.9.0 dated record
remains byte-identical; `sbom/cyclonedx.json` is byte-identical (its
regeneration stays deferred to the next release-qualification
objective). All nine emitted checks are `success` on the implementation
head, where `OpenAI-compatible E2E tests` runs under the new pin — the
in-CI proof that the matrix passes under 3.14.1.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 309
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/309
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/172-openai-sdk-3141-requalification`
- Starting remote SHA (base): `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`
- Candidate SDK version: `3.14.1`
- Implementation head SHA: `772c33b70f293598649dc26bbc1025b5197dcd67`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from
  GitHub)
- Implementation commits pushed before the report commit:
    - `42bc20ee4b313ddcbbedb29c8a6ae5c489d065a0` `oap: activate 172-a openai sdk 3.14.1 requalification` (carries the strategic-authored order and `oap/active`)
    - `772c33b70f293598649dc26bbc1025b5197dcd67` `obj172: qualify OpenAI Python SDK 3.14.1 official-client compatibility` (carries the single pin line, the single documentation sentence, the new dated record, and the one README index row)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `pyproject.toml`: the single dev dependency line
  `"openai==3.9.0"` → `"openai==3.14.1"` (only functional edit).
- `docs/openai-compatibility.md`: the single qualification sentence now
  names `openai==3.14.1` and points at the new dated record; the
  existing mocked-upstream limitation sentence and every other sentence
  are unchanged.
- `docs/verification/2026-09-17-openai-sdk-3141-requalification.md`: new
  dated record (base SHA, candidate version, single verdict line
  `OUTCOME=A`, complete P1–P4 evidence, CI tables, limitation
  sentences).
- `docs/verification/README.md`: exactly one appended index row.
- `oap/orders/172-a-openai-sdk-3141-requalification.md`: strategic work
  order committed unchanged (byte-identical strategic bytes;
  template-conforming, `PR mode: `CREATE_NEW_PR`` literal on line 3).
- `oap/active`: `172-a` (activated order pointer).
- `oap/reports/172-a-openai-sdk-3141-requalification.md`: this report
  (report-only commit).

Not touched (verified by diff scope, AP-3): everything outside the
allowed paths — in particular zero changes under `app/`, `tests/`
(including `tests/e2e/**` — no class-1 fix was required), `scripts/`,
`.github/`, `migrations/`, `nginx/`, `sbom/`; zero changes to `Dockerfile`,
`docker-compose*.yml`, `README.md`, `AGENTS.md`, `Makefile`, the ruff
pin, the `[tool.ruff.lint]` table, or any existing
`docs/verification/2026-*` file (the 3.9.0 record byte-identical).

## Files changed (full, including the report commit)
- `pyproject.toml`
- `docs/openai-compatibility.md`
- `docs/verification/2026-09-17-openai-sdk-3141-requalification.md`
- `docs/verification/README.md`
- `oap/orders/172-a-openai-sdk-3141-requalification.md`
- `oap/active`
- `oap/reports/172-a-openai-sdk-3141-requalification.md`

`git diff --name-only 1f76ece6e0457fe78fe29b5e188ea484cf0bfa09
772c33b70f293598649dc26bbc1025b5197dcd67` lists exactly the first six
paths (the report file appears only in the report commit); nothing else.

## Acceptance-criteria evidence
- **AP-1 — SATISFIED (decisive matrix, both phases, clean room, exact PR
  head).**
  - Phase B (`openai==3.9.0`): `python -m pytest tests/e2e -q` on a
    drop/recreated disposable database — **54 passed / 0 failed / 0
    skipped** (progress-line tally: 54 dots, no skip/fail markers).
    Phase-B-soundness statement: harness soundness for this run is
    established at the qualified baseline.
  - Phase C (`openai==3.14.1`): `python -m pytest tests/e2e -q` on a
    fresh drop/recreated database — **54 passed / 0 failed / 0 skipped**
    (progress-line tally: 54 dots, no skip/fail markers).
  - Phase B `pip freeze` selection (verbatim, clean-room venv Python
    3.12.3):
    `anyio==4.15.1`, `distro: ABSENT`, `httpcore==1.0.9`,
    `httpcore2==2.13.0`, `httpx==0.28.1`, `httpx2==2.13.0`,
    `jiter==0.17.0`, `openai==3.9.0`, `pydantic==2.13.5`,
    `pytest==9.1.1`, `respx==0.23.1`, `sniffio==1.3.1`, `tqdm: ABSENT`,
    `typing_extensions==4.16.0`.
  - Phase C `pip freeze` selection (verbatim): identical except
    `openai==3.14.1` — single-variable delta confirmed.
  - No Phase C non-pass exists; no P3 classification was triggered.
- **AP-2 — SATISFIED (ripple check, Phase C).**
  - Unit: `scripts/test-unit-parallel.sh`:
    **4047 passed / 1 failed / 0 skipped** in 66.16s. The single failure
    is the labeled environment-only case
    `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
    (`codex_version_mismatch`); recorded proof: `codex --version` →
    `codex-cli 0.154.0` (fixture pin `codex-cli 0.148.0`), identical to
    the 167/168/170/171 baseline, not chased.
  - Integration: `python -m pytest tests/integration -q` with
    `TEST_DATABASE_URL` on the fresh user-owned disposable PostgreSQL 16
    (database dropped/recreated immediately before the run):
    **224 passed / 1 skipped / 0 failed** (progress-line tally: 225
    characters, 224 pass dots + 1 skip, zero fail/error markers).
    Recorded proof of the skip's identity:
    `tests/integration/test_backup_restore_postgres.py:42` (skip reason
    "pg_dump unavailable or incompatible" — pg_dump rejects the
    `postgresql+asyncpg` DSN form and falls back to the default
    socket), identical to the 167/168/170/171 baseline.
- **AP-3 — SATISFIED (diff scope, PASS branch).** `git diff` vs base
  `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09` touches exactly
  `pyproject.toml` (single openai line; 1 insertion, 1 deletion in that
  file), `docs/openai-compatibility.md` (single sentence), the new dated
  record, the one README index row, and the OAP order/active/report
  files; no `tests/e2e/**` change was required or made. Zero changes
  under `app/`; zero changes to the ruff pin or the `[tool.ruff.lint]`
  table; the 3.9.0 dated record is byte-identical.
- **AP-4 — SATISFIED (CI gates).** All nine required checks
  `completed`/`success` on the exact implementation head
  `772c33b70f293598649dc26bbc1025b5197dcd67` (queried 2026-09-17):
  `Unit, lint, and migration head` 105265859126; `Documentation
  hygiene` 105265859221; `OpenAI-compatible E2E tests` 105265858912;
  `Playwright browser smoke` 105265859162; `Docker Compose smoke`
  105265859289; `PostgreSQL integration tests` 105265858953; `Analyze
  (javascript-typescript)` 105265841412; `Analyze (python)`
  105265840965; `Analyze Python` 105265858417. On the PASS branch the
  `OpenAI-compatible E2E tests` check on this head is the in-CI proof
  that the matrix passes under `openai==3.14.1` (this head carries the
  new pin). The candidate's own main-branch state
  (`1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`: all ten emitted checks
  `success`) is recorded in the dated record. The mandatory final-head
  re-query after the report-only commit per AP-6 is performed before the
  two-byte OK (see CI gate state).
- **AP-5 — SATISFIED.** `python scripts/check_documentation.py` on the
  final tree prints `DOCUMENTATION_CHECK=OK files=83` — the file count
  grows by exactly one (the new dated record).
- **AP-6 — SATISFIED.** This immutable report contains the literal base
  SHA `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`, the literal candidate
  version `3.14.1`, and the single verdict line `OUTCOME=A`; the
  report-only commit changes only
  `oap/reports/172-a-openai-sdk-3141-requalification.md`, has the
  recorded implementation head as first parent, and is pushed and
  verified as the remote PR head before the two-byte `OK` is written to
  the response FIFO. The AP-4 re-query on the final head is the
  mandatory gate before that OK (see CI gate state).

## Local verification (clean-room venv, clean-room tree unless noted)
- P1: fresh clone `/tmp/obj172-cleanroom/`, detached checkout of the
  exact PR head `42bc20ee4b313ddcbbedb29c8a6ae5c489d065a0` (activation
  commit; candidate code identical to the base tree — the PASS-branch
  edits are the dev-pin line and documentation only),
  `git status --short` empty, fresh `.venv` (Python 3.12.3, `.[dev]`).
  Phase C upgrade: `pip install openai==3.14.1` (the only environment
  change between phases). All candidate code ran from the clean room
  only.
- P2: `python -m pytest tests/e2e -q` Phase B (log
  `/tmp/obj172-e2e-phaseB.log`, drop/recreated database, 54/0/0);
  `python -m pytest tests/e2e -q` Phase C (log
  `/tmp/obj172-e2e-phaseC.log`, fresh drop/recreated database, 54/0/0);
  `scripts/test-unit-parallel.sh` Phase C (log
  `/tmp/obj172-unit-phaseC.log`, 4047/1-labeled/0); `python -m pytest
  tests/integration -q` Phase C (log
  `/tmp/obj172-integration-phaseC.log`, fresh disposable PG 16 (16.15)
  on `127.0.0.1:5433`, 224/1-labeled/0); `codex --version` →
  `codex-cli 0.154.0` (recorded at `/tmp/obj172-codex-version.txt`);
  freeze selections at `/tmp/obj172-freeze-phaseB.txt` and
  `/tmp/obj172-freeze-phaseC.txt` (full freezes alongside).
- P4: `git diff --name-only` vs base and the full diffs of
  `pyproject.toml` and `docs/openai-compatibility.md` (each exactly the
  single allowed edit); `python scripts/check_documentation.py` →
  `DOCUMENTATION_CHECK=OK files=83`; `git diff --check` → clean.
- AP-4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` for the
  candidate, the activation head, and the implementation head (run IDs
  in the dated record and above); final-head re-query after the
  report-only commit (mandatory gate; see CI gate state).
- Environment-only disclosures (labeled, with proof): execution VM
  `codex-cli 0.154.0` vs fixture pin `0.148.0` (one labeled unit case);
  local-VM `pg_dump` DSN-form skip (identity recorded in AP-2). The 5432
  system cluster was not used; a fresh disposable cluster under
  `/tmp/obj172-pg/` on `127.0.0.1:5433` served the E2E and integration
  runs (drop/recreated database each time).

## Negative evidence
- No `app/` change of any kind: production code is byte-identical to
  the base in this PASS branch; no runtime dependency, schema,
  migration, or configuration surface touched; PostgreSQL remains
  quota/accounting truth (untouched).
- No other dependency change: the only dev-pin line changed is
  `openai==3.9.0` → `openai==3.14.1`; the `ruff==0.16.7` pin and the
  `[tool.ruff.lint]` policy pin are byte-identical to the base.
- No contract loosening or capability addition: no new accepted field,
  endpoint, tool behavior, error shape, or streaming form introduced.
- No test weakening: no assertion deleted, loosened, xfail-ed, or
  skipped; no `tests/e2e/**` change was required (no class-1 fix); the
  only non-passes in the ripple check are the two labeled
  environment-only items, each with its recorded proof.
- No SBOM edit: `sbom/cyclonedx.json` is byte-identical to the base; its
  regeneration (stale w.r.t. both the 166 openai pin and this bump)
  remains deferred to the next release-qualification objective.
- No documentation edit outside the two allowed changes (the single
  sentence and the one index row); in particular no edit to any
  existing `docs/verification/2026-*` file (the 3.9.0 record is
  byte-identical), `README.md`, or `AGENTS.md`.
- No PR interaction: PR #224 and every other PR (including the closed,
  decomposed #250) were not touched in any way; no Dependabot action of
  any kind. No GitHub-settings action.
- No real provider calls: `RUN_UPSTREAM_TESTS` unset throughout; the E2E
  matrix runs against the mocked official-client upstream
  infrastructure only; no provider credentials present or used.
- No secrets in artifacts: the record and this report contain no
  generated secret, key, password, prompt, completion, or canary value
  (the disposable PostgreSQL password is redacted); only safe booleans,
  counts, versions, SHAs, and CI run IDs are recorded.
- No release, tag, or deployment; no production/staging system; no real
  email.
- No new product capability of any kind.

## CI gate state on the final head
- Implementation head `772c33b70f293598649dc26bbc1025b5197dcd67` (first
  parent of the final report-only head, which adds only this report file
  and touches no code, workflow, or configuration path covered by any
  check): all nine required checks SUCCESS — `Unit, lint, and migration
  head` 105265859126; `Documentation hygiene` 105265859221;
  `OpenAI-compatible E2E tests` 105265858912 (in-CI proof under the new
  `openai==3.14.1` pin); `Playwright browser smoke` 105265859162;
  `Docker Compose smoke` 105265859289; `PostgreSQL integration tests`
  105265858953; `Analyze (javascript-typescript)` 105265841412;
  `Analyze (python)` 105265840965; `Analyze Python` 105265858417. Per
  AP-6, the final head's check runs are re-queried after publication of
  the report-only commit, and that re-query is a mandatory gate before
  the response-FIFO `OK` signal is sent (a report commit cannot carry
  the run IDs of its own commit; the re-query result is part of this
  objective's execution record and is independently re-verified on
  GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #309 was left OPEN for strategic
review and the human maintainer's delegated merge authority; no merge
was performed, and no merge-related GitHub action of any kind was taken
by this objective.
