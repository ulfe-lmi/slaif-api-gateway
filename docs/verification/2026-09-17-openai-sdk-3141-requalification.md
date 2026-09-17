# 2026-09-17 OpenAI Python SDK 3.14.1 Official-Client Compatibility Requalification

**Objective:** OAP 172-a
(`oap/orders/172-a-openai-sdk-3141-requalification.md`).
**Question:** does the current Gateway preserve its declared official
OpenAI-client compatibility contract when exercised through OpenAI Python
SDK `3.14.1` (the current stable release at order authoring; PyPI upload
2026-09-15T23:13:33Z), starting from the qualified baseline
`openai==3.9.0` (Objective 166, PR #303, `OUTCOME=A`)?

**Result: OUTCOME=A** — the declared compatibility surface holds under
`openai==3.14.1`. The dev/test pin was deliberately updated from
`openai==3.9.0` to `openai==3.14.1`; the complete 54-test official-client
E2E matrix passes under that pin with zero code change (no gateway change,
no test-harness change, no class-1 fix was required). This requalification
closes the truth debt created by the six stable SDK releases (3.10.0,
3.11.0, 3.12.0, 3.13.0, 3.14.0, 3.14.1) shipped since the 3.9.0
qualification (2026-09-08).

## Evidence boundary

- Base `main` SHA (candidate tree): `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`
  (merge of PR #308 / Objective 171; all ten emitted main-branch checks
  `completed`/`success`, live-reverified 2026-09-17 — run IDs in the CI
  state section below).
- PR: `oap/172-openai-sdk-3141-requalification` against `main`.
- PR head at the time this record was written: the activation commit
  `42bc20ee4b313ddcbbedb29c8a6ae5c489d065a0` (carries the
  strategic-authored order and `oap/active`); the implementation head
  (first parent of the report-publication `SELF` commit) carries the pin,
  the single documentation sentence, and this record. The OAP report for
  172-a records the literal implementation-head SHA.
- All local matrix runs used a fresh user-owned disposable PostgreSQL 16
  (16.15) database `slaif_gateway_test` on `127.0.0.1:5433` (dropped and
  recreated before every DB-backed run; owner role `slaif`; the 5432
  system cluster was not used; never `DATABASE_URL`); upstream providers
  were mocked at the transport level (respx) inside the E2E
  infrastructure; no live provider calls; `RUN_UPSTREAM_TESTS` unset.

## P1 — Clean-room, dual-phase environment

- Fresh full clone: `/tmp/obj172-cleanroom/`, detached checkout of the
  exact PR head `42bc20ee4b313ddcbbedb29c8a6ae5c489d065a0`;
  `git status --short` empty; fresh `.venv` (Python 3.12.3) with
  `.[dev]`. All candidate code ran only from the clean room.
- Phase B (baseline) freeze selection, `openai==3.9.0` installed from the
  `main` pin:

```text
anyio==4.15.1
distro: ABSENT
httpcore==1.0.9
httpcore2==2.13.0
httpx==0.28.1
httpx2==2.13.0
jiter==0.17.0
openai==3.9.0
pydantic==2.13.5
pytest==9.1.1
respx==0.23.1
sniffio==1.3.1
tqdm: ABSENT
typing_extensions==4.16.0
```

- Phase C (candidate) freeze selection, after `pip install
  openai==3.14.1` (the only environment change between phases):

```text
anyio==4.15.1
distro: ABSENT
httpcore==1.0.9
httpcore2==2.13.0
httpx==0.28.1
httpx2==2.13.0
jiter==0.17.0
openai==3.14.1
pydantic==2.13.5
pytest==9.1.1
respx==0.23.1
sniffio==1.3.1
tqdm: ABSENT
typing_extensions==4.16.0
```

- Single-variable check: the only version change between Phase B and
  Phase C is `openai 3.9.0 -> 3.14.1`; every transitive dependency
  (including the SDK's own `httpx2`/`httpcore2` transport stack, `jiter`,
  `anyio`, `sniffio`) is unchanged, so the two phases differ exactly in
  the variable under qualification. `distro` and `tqdm` are absent in
  both phases (not dependencies of openai 3.x in this tree).

## P2 — Decisive matrix (both phases)

### Phase B (baseline `openai==3.9.0`) — harness soundness

`python -m pytest tests/e2e -q` on a drop/recreated disposable database:
**54 passed / 0 failed / 0 skipped** (progress-line tally: 54 dots, no
skip/fail markers). Phase-B soundness established for this run.

### Phase C (candidate `openai==3.14.1`)

`python -m pytest tests/e2e -q` on a fresh drop/recreated database:
**54 passed / 0 failed / 0 skipped** (progress-line tally: 54 dots, no
skip/fail markers). The declared official-client compatibility contract
holds under the candidate; no P3 failure classification was triggered.

### Phase C ripple check

- Full unit suite via `scripts/test-unit-parallel.sh`:
  **4047 passed / 1 failed / 0 skipped** in 66.16s. The single failure is
  the labeled environment-only case
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (`codex_version_mismatch`: VM `codex --version` = `codex-cli 0.154.0`
  vs fixture pin `codex-cli 0.148.0`; `codex --version` output recorded),
  identical to the 167/168/170/171 baseline; not chased.
- Full PostgreSQL integration suite via `python -m pytest
  tests/integration -q` with `TEST_DATABASE_URL` on the fresh disposable
  PostgreSQL 16 (database dropped/recreated immediately before the run):
  **224 passed / 1 skipped / 0 failed** (progress-line tally: 225
  characters, 224 pass dots + 1 skip, zero fail/error markers). The skip
  is the labeled local-VM `pg_dump` CLI limitation on the
  `TEST_DATABASE_URL` form
  (`tests/integration/test_backup_restore_postgres.py:42`), identical to
  the 167/168/170/171 baseline.

## P3 — Failure classification

Not triggered: no Phase C E2E non-pass occurred, and the ripple check
shows only the two labeled environment-only non-passes (each with its
recorded proof). No class-1 harness fix was required; no test file was
changed.

## P4 — Outcome (PASS branch)

- `pyproject.toml`: the single dev dependency line
  `"openai==3.9.0"` → `"openai==3.14.1"` (the only functional edit; the
  `ruff==0.16.7` pin and the `[tool.ruff.lint]` policy pin are
  untouched).
- `docs/openai-compatibility.md`: the single qualification sentence now
  names `openai==3.14.1` and points at this dated record; the existing
  mocked-upstream limitation sentence is preserved unchanged; no other
  sentence in that file changes.
- The existing `2026-09-17-openai-sdk3-qualification.md` (3.9.0) record
  remains byte-identical (dated, historical).

## CI state

- Candidate `main` `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`: all ten
  emitted main-branch checks `completed`/`success` (live-reverified
  2026-09-17): `Unit, lint, and migration head` 105255061887;
  `Documentation hygiene` 105255061603; `OpenAI-compatible E2E tests`
  105255061990; `Playwright browser smoke` 105255062071; `Docker Compose
  smoke` 105255061965; `PostgreSQL integration tests` 105255061897;
  `Analyze (javascript-typescript)` 105255069828; `Analyze (python)`
  105255070098; `Analyze Python` 105255061670; `update-pip-graph`
  105255084671.
- Exact PR head at the time this record was written,
  `42bc20ee4b313ddcbbedb29c8a6ae5c489d065a0` (activation commit; its
  `OpenAI-compatible E2E tests` runs under the still-qualified 3.9.0
  pin): all nine required checks `completed`/`success` (queried
  2026-09-17): `Unit, lint, and migration head` 105260737209;
  `Documentation hygiene` 105260736824; `OpenAI-compatible E2E tests`
  105260736914; `Playwright browser smoke` 105260736887; `Docker Compose
  smoke` 105260736453; `PostgreSQL integration tests` 105260736788;
  `Analyze (javascript-typescript)` 105260728607; `Analyze (python)`
  105260728383; `Analyze Python` 105260739134. The implementation head
  (this record's parent chain) carries the `openai==3.14.1` pin; its
  `OpenAI-compatible E2E tests` run is the in-CI proof that the matrix
  passes under 3.14.1, and the mandatory final-head re-query after the
  report-only commit per AP-6 is recorded in the objective report.

## Deployment-path statement

The documented deployment paths (dev Compose and production Compose) are
mechanically covered at this commit by the CI `Docker Compose smoke` job
(success on the candidate and on the PR head, run IDs above); this
objective changes no deployment artifact.

## Limitations

- The E2E upstream is mocked at the transport level (respx) inside the
  disposable test infrastructure; this is not a real-provider run, and no
  provider credentials were used or present.
- This record is not a release decision, production certification,
  security review, compliance finding, or SLA approval.
- RC2 required-scope completeness is asserted only as
  `docs/rc2-feature-scope.md`'s current classification; it is not
  re-derived here.
- Evidence boundary: this record is dated evidence for the named base
  candidate commit `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09` and the
  candidate SDK version `3.14.1` only; it does not transfer to later
  commits or newer SDK releases.
- The `OUTCOME=A` verdict rests on: Phase B soundness 54/0/0 at the
  qualified baseline; Phase C 54/0/0 under the candidate with an exactly
  single-variable dependency delta; the ripple check green modulo only
  the two labeled environment-only non-passes; and 9/9 required checks
  `success` on the PR head with the implementation head's E2E check as
  the in-CI proof under 3.14.1.
