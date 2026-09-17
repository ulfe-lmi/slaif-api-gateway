# OAP Coding-Agent Report — 171-a

## Work order
- Identifier: 171-a
- Work-order file: `oap/orders/171-a-ruff-0-16-7-policy-pinned-bump.md`
- Numeric objective: 171
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Bumped the pinned development lint tool from `ruff==0.15.16` to
`ruff==0.16.7` and, in the same one-file change to `pyproject.toml`, made
the repository's effective lint policy explicit and version-stable by
pinning exactly the default rule set that ruff 0.15.16 applied
(`select = ["E4", "E7", "E9", "F"]` in a new `[tool.ruff.lint]` table,
with the order's normative comment). This closes the ruff half of the
live Dependabot signal (PR #250) with a clean OAP transcript; the openai
half of #250 (`3.9.0 -> 3.13.0`) is untouched and remains a separate
strategic question.

Decisive evidence (AP-1, clean-room venv at the exact PR head):
`pip show ruff` → `Version: 0.16.7`; `python -m ruff check app tests` →
`All checks passed!` (0 findings); `--show-settings`
`linter.rules.enabled` resolves to exactly the 59-rule baseline set with
an **empty diff** against the order's embedded baseline — the effective
policy is byte-identical to the 0.15.16-era default under the new
dependency version. Without the pin, ruff 0.16.7 would report 1293
findings (190 non-auto-fixable) on this tree; adopting that larger
policy is a separate, deliberately decided objective and is explicitly
deferred.

All nine emitted checks are `success` on the exact PR head (AP-4),
including `Unit, lint, and migration head` — the in-CI proof that the
unpinned-bump failure mode (PR #250, job 105112572194) is resolved by the
pin. The full local matrix (AP-3) is green modulo only the two labeled
environment-only items. No application, test, CI, documentation, or SBOM
file was changed; no rule was adopted or loosened; no `noqa`/ignore
entries were added.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 308
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/308
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/171-ruff-0-16-7-policy-pinned-bump`
- Starting remote SHA (base): `cff2d798d6b170070674ca0f69e234d2d1bad8f6`
- Candidate ruff version: `0.16.7`
- Implementation head SHA: `1b6a156387e1b8b5bb3f53031fb815283555df4d`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from
  GitHub)
- Implementation commits pushed before the report commit:
    - `84087a82d5cf5f89bbcc69abd22f4214cd93b85e` `oap: activate 171-a ruff 0.16.7 policy-pinned bump` (carries the strategic-authored order and `oap/active`)
    - `1b6a156387e1b8b5bb3f53031fb815283555df4d` `obj171: pin lint policy and bump ruff to 0.16.7` (carries the exact two-line `pyproject.toml` change)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `pyproject.toml` (the only functional change, exactly two edits):
  1. dev dependency list: `"ruff==0.15.16"` → `"ruff==0.16.7"`
  2. new nested `[tool.ruff.lint]` table (under the existing
     `[tool.ruff]` with `line-length = 100` retained) containing exactly
     the order's normative comment and `select = ["E4", "E7", "E9", "F"]`
- `oap/orders/171-a-ruff-0-16-7-policy-pinned-bump.md`: strategic work
  order committed unchanged (byte-identical strategic bytes;
  template-conforming, `PR mode: `CREATE_NEW_PR`` literal on line 3).
- `oap/active`: `171-a` (activated order pointer).
- `oap/reports/171-a-ruff-0-16-7-policy-pinned-bump.md`: this report
  (report-only commit).

Not touched (verified by diff scope, AP-2): everything outside the four
allowed paths — in particular zero changes under `app/`, `tests/`,
`scripts/`, `.github/`, `migrations/`, `nginx/`, `docs/`, `sbom/`, and
zero changes to `Dockerfile`, `docker-compose*.yml`, `README.md`,
`AGENTS.md`, or `Makefile`.

## Files changed (full, including the report commit)
- `pyproject.toml`
- `oap/orders/171-a-ruff-0-16-7-policy-pinned-bump.md`
- `oap/active`
- `oap/reports/171-a-ruff-0-16-7-policy-pinned-bump.md`

`git diff --name-only cff2d798d6b170070674ca0f69e234d2d1bad8f6
1b6a156387e1b8b5bb3f53031fb815283555df4d` lists exactly the first three
paths (the report file appears only in the report commit); nothing else.

## Acceptance-criteria evidence
- **AP-1 — SATISFIED (policy identity, decisive).** In the clean-room
  venv created from the exact PR head (P1):
  - `pip show ruff`:
    ```text
    Name: ruff
    Version: 0.16.7
    Summary: An extremely fast Python linter and code formatter, written in Rust.
    ```
  - `python -m ruff check app tests` → `All checks passed!` (0
    findings).
  - `python -m ruff check app tests --show-settings` →
    `linter.rules.enabled` extracted (59 entries; 0.16.7 prints each as
    `rule-name (CODE)`), codes normalized, sorted, and diffed against
    the order's embedded 59-rule baseline: **empty diff** (recorded
    locally at `/tmp/obj171-rules-cleanroom.txt` vs
    `/tmp/obj171-rules-baseline-sorted.txt`; raw extraction at
    `/tmp/obj171-raw-enabled.txt`). The effective set is exactly:
    E401, E402, E701, E702, E703, E711, E712, E713, E714, E721, E722,
    E731, E741, E742, E743, E902, F401, F402, F403, F404, F405, F406,
    F407, F501, F502, F503, F504, F505, F506, F507, F508, F509, F521,
    F522, F523, F524, F525, F541, F601, F602, F621, F622, F631, F632,
    F633, F634, F701, F702, F704, F706, F707, F722, F811, F821, F822,
    F823, F841, F842, F901.
  - No extra or missing rule: no STOP/escalation condition triggered.
- **AP-2 — SATISFIED (diff scope).** `git diff --name-only
  cff2d798d6b170070674ca0f69e234d2d1bad8f6 <implementation-head>` lists
  exactly `pyproject.toml`, the order file, and `oap/active` (plus the
  report file in the report-only commit — the four allowed paths). The
  `pyproject.toml` diff contains exactly the version line and the new
  `[tool.ruff.lint]` table (10 insertions, 1 deletion; full diff in the
  commit). Zero changes under `app/`, `tests/`, `scripts/`, `.github/`,
  `migrations/`, `nginx/`, `docs/`, `sbom/`, `Dockerfile`,
  `docker-compose*.yml`, `README.md`, `AGENTS.md`, or `Makefile`.
- **AP-3 — SATISFIED (full local matrix, behavior unchanged; clean room,
  fresh disposable PostgreSQL 16 (16.15) on `127.0.0.1:5433`)**:
  - Unit: `scripts/test-unit-parallel.sh`
    (`.venv/bin/python -m pytest tests/unit -n 20 --dist loadscope`):
    **4047 passed / 1 failed / 0 skipped** in 67.74s. The single failure
    is the known VM-only case
    `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
    (`codex_version_mismatch`); recorded proof: `codex --version` →
    `codex-cli 0.154.0` (fixture pin `codex-cli 0.148.0`),
    environment-only per the order, not chased.
  - Integration: `.venv/bin/python -m pytest tests/integration -q` with
    `TEST_DATABASE_URL` on the fresh user-owned disposable PostgreSQL 16
    (database dropped/recreated immediately before the run):
    **224 passed / 1 skipped / 0 failed**. Recorded proof of the
    skip's identity:
    `tests/integration/test_backup_restore_postgres.py:42` (skip reason
    "pg_dump unavailable or incompatible" — pg_dump rejects the
    `postgresql+asyncpg` DSN form and falls back to the default socket),
    identical to the 167/168/170 baseline. The captured log's final
    summary line was lost to a tee/pipe flush race; counts are the exact
    tally of the 225-character pytest progress line (224 pass dots + 1
    skip, zero fail/error markers).
  - E2E: `.venv/bin/python -m pytest tests/e2e -q` on a drop/recreated
    database: **54 passed / 0 failed / 0 skipped** (54-test
    official-client matrix; progress-line tally: 54 dots, no skip/fail
    markers). `openai` pin unchanged — P1 freeze line `openai==3.9.0`.
  - P1 freeze lines (clean-room venv, Python 3.12.3):
    `ruff==0.16.7`, `openai==3.9.0`, `fastapi==0.141.1`,
    `pydantic==2.13.5`, `httpx==0.28.1`, `respx==0.23.1`,
    `pytest==9.1.1`, `asyncpg==0.31.0`, `prometheus_client==0.26.0`,
    `gunicorn==26.2.0`, `uvicorn==0.53.0`.
- **AP-4 — SATISFIED (CI gates).** All nine emitted checks
  `completed`/`success` on the exact PR head (implementation head
  `1b6a156387e1b8b5bb3f53031fb815283555df4d`; queried 2026-09-17):
  `Unit, lint, and migration head` 105248119436; `Documentation
  hygiene` 105248118910; `OpenAI-compatible E2E tests` 105248119203;
  `Playwright browser smoke` 105248119367; `Docker Compose smoke`
  105248119349; `PostgreSQL integration tests` 105248119333; `Analyze
  (javascript-typescript)` 105248120633; `Analyze (python)`
  105248121283; `Analyze Python` 105248119639. `Unit, lint, and
  migration head` success on this head is the in-CI proof that the
  unpinned-bump failure mode (PR #250 run 35193923676 / job
  105112572194, `Found 1290 errors`) is resolved by the pin. The
  mandatory final-head re-query after the report-only commit per AP-6 is
  performed before the two-byte OK (see CI gate state).
- **AP-5 — SATISFIED.** `python scripts/check_documentation.py` on the
  final tree prints `DOCUMENTATION_CHECK=OK files=82` — the file count
  is unchanged vs the base tree (no documentation files added or
  edited).
- **AP-6 — SATISFIED.** This immutable report contains the literal base
  SHA `cff2d798d6b170070674ca0f69e234d2d1bad8f6`, the literal candidate
  ruff version `0.16.7`, and `Report publication commit: SELF`; the
  report-only commit changes only
  `oap/reports/171-a-ruff-0-16-7-policy-pinned-bump.md`, has the
  recorded implementation head as first parent, and is pushed and
  verified as the remote PR head before the two-byte `OK` is written to
  the response FIFO. The AP-4 re-query on the final head is the
  mandatory gate before that OK (see CI gate state).

## Local verification (clean-room venv, clean-room tree unless noted)
- P1: fresh clone `/tmp/obj171-cleanroom/`, detached checkout of the
  exact PR head `1b6a156387e1b8b5bb3f53031fb815283555df4d`,
  `git status --short` empty, fresh `.venv` (Python 3.12.3, `.[dev]`).
  All candidate code ran from the clean room only.
- AP-1 commands (clean room): `pip show ruff` (file
  `/tmp/obj171-pip-show-ruff.txt`); `python -m ruff check app tests`
  (file `/tmp/obj171-ruff-check.txt`); `python -m ruff check app tests
  --show-settings` (file `/tmp/obj171-show-settings.txt`; normalized
  code list `/tmp/obj171-rules-cleanroom.txt`; baseline
  `/tmp/obj171-rules-baseline-sorted.txt`; diff empty).
- AP-3: `scripts/test-unit-parallel.sh` (log
  `/tmp/obj171-p3-unit.log`); `.venv/bin/python -m pytest
  tests/integration -q` (log `/tmp/obj171-p3-integration.log`, fresh
  disposable PG on `127.0.0.1:5433`); `.venv/bin/python -m pytest
  tests/e2e -q` (log `/tmp/obj171-p3-e2e.log`, drop/recreated
  database); `codex --version` → `codex-cli 0.154.0`.
- AP-4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` for the
  implementation head (run IDs above) and the final head after the
  report-only commit (mandatory gate; see CI gate state).
- Documentation gate on the final tree: `python
  scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=82`;
  `git diff --check` → clean.
- Environment-only disclosures (labeled, with proof): execution VM
  `codex-cli 0.154.0` vs fixture pin `0.148.0` (one labeled unit case);
  local-VM `pg_dump` DSN-form skip (identity recorded in AP-3). The 5432
  system cluster was not used; the fresh disposable cluster under
  `/tmp/obj171-pg/` on `127.0.0.1:5433` was used for both DB-backed
  suites and asyncpg TCP authentication was verified before the runs.

## Negative evidence
- No `openai` change of any kind: `openai==3.9.0` remains pinned (P1
  freeze line recorded); the `3.9.0 -> 3.13.0` half of Dependabot PR
  #250 was not folded in.
- No code change of any kind: the functional diff is exactly the two
  `pyproject.toml` edits; zero application, test, CI, Docker,
  nginx, migration, or schema change; `tests/unit/test_oap_governance.py`
  and the order template are untouched.
- No new-rule adoption and no loosening: the pinned set is exactly the
  59-rule 0.15.16-era default baseline (AP-1 empty diff); no
  `--fix`/`--unsafe-fixes`/mass-edit run; no `# noqa`, per-file ignores,
  `extend-select`, `ignore`, or other lint override added.
- No SBOM edit: `sbom/cyclonedx.json` is byte-identical to the base. It
  is a point-in-time snapshot (2026-08-23, rc1 era) that already predates
  the Objective 166 `openai==3.9.0` pin; hand-editing its ruff version
  would produce an internally inconsistent SBOM. **SBOM regeneration is
  deferred to the next release-qualification objective** (stale w.r.t.
  both the 166 openai pin and this ruff bump).
- No documentation edit: `README.md`, `AGENTS.md`, `docs/**`, and all
  existing `docs/verification/2026-*` files are byte-identical to the
  base.
- No PR interaction: PR #250 and PR #224 were not closed, rebased,
  merged, commented on, or touched in any way; no Dependabot action of
  any kind.
- No real provider calls: `RUN_UPSTREAM_TESTS` unset throughout; no
  provider credentials present or used.
- No secrets in artifacts: this report and the order contain no
  generated secret, key, password, prompt, completion, or canary value
  (the disposable PostgreSQL password is redacted); only safe booleans,
  counts, timings, SHAs, rule codes, and CI run IDs are recorded.
- No release, tag, or deployment; no production/staging system; no real
  email; no GitHub-settings action (branch protection, rulesets,
  required checks).
- No new product capability of any kind.

## CI gate state on the final head
- Implementation head `1b6a156387e1b8b5bb3f53031fb815283555df4d` (first
  parent of the final report-only head, which adds only this report file
  and touches no code, workflow, or configuration path covered by any
  check): all nine required checks SUCCESS — `Unit, lint, and migration
  head` 105248119436; `Documentation hygiene` 105248118910;
  `OpenAI-compatible E2E tests` 105248119203; `Playwright browser
  smoke` 105248119367; `Docker Compose smoke` 105248119349;
  `PostgreSQL integration tests` 105248119333; `Analyze
  (javascript-typescript)` 105248120633; `Analyze (python)`
  105248121283; `Analyze Python` 105248119639. Per AP-6, the final
  head's check runs are re-queried after publication of the report-only
  commit, and that re-query is a mandatory gate before the response-FIFO
  `OK` signal is sent (a report commit cannot carry the run IDs of its
  own commit; the re-query result is part of this objective's execution
  record and is independently re-verified on GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #308 was left OPEN for strategic
review and the human maintainer's delegated merge authority; no merge
was performed, and no merge-related GitHub action of any kind was taken
by this objective.
