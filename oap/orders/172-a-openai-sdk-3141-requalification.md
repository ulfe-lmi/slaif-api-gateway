# OAP Work Order — 172-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Deliberately re-qualify the Gateway's declared official OpenAI Python
client compatibility contract against the **current stable** SDK release
`openai==3.14.1`, starting from the current qualified baseline
`openai==3.9.0` (Objective 166, PR #303, `OUTCOME=A`).

The question this objective answers is exactly one:

> Does the current Gateway preserve its declared official OpenAI-client
> compatibility contract when exercised through OpenAI Python SDK 3.14.1?

This is qualification-first compatibility work, not dependency cleanup.
The compatibility claim in `docs/openai-compatibility.md` currently reads
"qualified under the dev/test pin `openai==3.9.0`"; six stable SDK
releases (3.10.0, 3.11.0, 3.12.0, 3.13.0, 3.14.0, 3.14.1) have shipped
since the 3.9.0 qualification (2026-09-08). A user installing the current
official client today gets 3.14.1, which is not qualified. Requalifying
against the current client is truth debt for the release posture; the
qualified pin is a versioned, evidenced claim, and it must be current or
explicitly bounded.

Strategic facts (machine-verified by the strategic model on
2026-09-17 ~17:10 Europe/Ljubljana):

- PyPI stable release timeline (verified via the PyPI JSON API):
  `3.9.0` uploaded 2026-09-08T16:43:12Z, `3.13.0` 2026-09-10T19:38:25Z,
  `3.14.0` 2026-09-14T23:29:08Z, `3.14.1` 2026-09-15T23:13:33Z. The
  latest stable release is `3.14.1`. The candidate for this order is
  exactly `3.14.1`; if a newer stable release appears before execution,
  do not chase it — `3.14.1` is the candidate under qualification and the
  order remains valid.
- The closed Dependabot PR #250 targeted `3.13.0` (its last sync) —
  already stale relative to PyPI; it is closed as decomposed and is NOT a
  merge vehicle for this objective.
- `openai` is a development/test dependency (official-client E2E
  matrix); production/runtime code does not import it. The change surface
  on a pass is one dev-pin line plus a documentation update; on a fail it
  is zero functional change.
- The openai SDK is used by `tests/e2e/` (the 54-test official-client
  matrix) and by unit/integration tests that import the client library.
  Any harness-side adjustment forced by a changed SDK client API is
  in-scope under the strict P3 class-1 rule; any production behavior
  change is out of scope.

The outcome must be decisive in this round: either the contract holds at
3.14.1 (`OUTCOME=A`, pin moved, evidence recorded) or it does not
(`OUTCOME=NO-GO`, pin unchanged, every failure classified with machine
evidence). A NO-GO is a complete, successful execution of this objective —
it is not a failure of the objective — and it feeds the strategic
decision about pin policy without any production change.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-17 ~17:10 Europe/Ljubljana from
live GitHub, the shared worktree, and PyPI:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (the base for this order):
  `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09` — merge of PR #308
  (Objective 171, merged 2026-09-17T14:56:14Z). All ten emitted
  main-branch checks on this commit are `completed`/`success`
  (re-verified 2026-09-17 ~17:05 Europe/Ljubljana, including
  `OpenAI-compatible E2E tests` and `Unit, lint, and migration head`).
- Objective 171 is terminal: `ruff==0.16.7` with the explicit
  `[tool.ruff.lint] select = ["E4", "E7", "E9", "F"]` policy pin is on
  `main`; its report and dated evidence are on `main`.
- Shared `oap/active` is terminal at `171-a`. This order activates
  `172-a`.
- `pyproject.toml` on `main`: `"openai==3.9.0"` (dev dependency, line 43)
  and `"ruff==0.16.7"` with the lint policy pin — both verified. No
  lockfile exists.
- Open PRs are exactly #224 (Dependabot GitHub Actions group; stale). PR
  #250 is CLOSED (decomposed: ruff half via #308/171; openai half
  deferred as this strategic question). **This order touches no PR.**
- Objectives 166 (`openai==3.9.0`, `OUTCOME=A`, PR #303), 168 (PR #305),
  170 (PR #307) are terminal and verified; the 3.9.0 qualified record is
  `docs/verification/2026-09-17-openai-sdk3-qualification.md` (dated,
  historical, byte-stable).
- PR #291 (Objective 155) remains closed-as-superseded; PR #306 remains
  closed-abandoned (Objective 169); branches retained as historical
  evidence only.
- `docs/rc2-feature-scope.md` classification summary: 27
  `RC2_REQUIRED_IMPLEMENTED`, 0 `RC2_REQUIRED_MISSING`, 17
  `RC2_EXPLICITLY_DEFERRED`, 1 `RC2_UNSUPPORTED_BY_POLICY`, 6
  `NEEDS_MAINTAINER_DECISION`.
- Branch protection: ruleset `protect main` (id 23580289) active with
  `non_fast_forward` + `deletion` only, no bypass actors; `basic-protect`
  and `Code Quality Copilot review` rulesets disabled. Completion of
  branch protection is a human GitHub-administration action and is
  explicitly outside this order.
- Known environment-only items (label, do not chase): execution VM
  `codex-cli 0.154.0` vs the fixture pin `0.148.0` (one labeled unit
  case); local-VM `pg_dump` DSN-form skip in the integration suite
  (identical to the 167/168/170/171 baseline); the 5432 system PG
  cluster carries diagnostic residue — use a fresh disposable cluster
  for the integration suite.

## PR contract

- Base: `main` at `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`.
- Branch: `oap/172-openai-sdk-3141-requalification`.
- Title: `obj172: qualify OpenAI Python SDK 3.14.1 official-client compatibility`.
- One new PR for `172-a`; later `172-b`... rounds amend the same PR.
- Commit the unchanged strategic-authored order and `oap/active` per the
  coding-agent protocol. The order file is template-conforming as authored
  (first content line after the title is `PR mode: \`CREATE_NEW_PR\``); it
  must reach the PR head byte-identical so the candidate's governance unit
  test `tests/unit/test_oap_governance.py` passes on this PR head.

## Qualification design (required sequence)

Execute exactly the following, in order, from the clean room:

- **P1 — Clean room, dual-phase environment.** Fresh clone of the remote
  into `/tmp/obj172-cleanroom/`, detached checkout of the exact PR head,
  `git status --short` empty, fresh `.venv` (Python 3.12.x). Two phases,
  no code or environment change between them except the openai pin:
  - **Phase B (baseline):** install the `main` pin `openai==3.9.0`;
    record `pip freeze` lines for `openai`, `httpx`, `httpcore`,
    `pydantic`, `respx`, `pytest`, `anyio`, `distro`, `jiter`, `sniffio`,
    `tqdm`, `typing-extensions`.
  - **Phase C (candidate):** install `openai==3.14.1`; record the same
    `pip freeze` selection. All candidate code runs only from the clean
    room.
- **P2 — Decisive matrix (both phases).**
  - Phase B: `python -m pytest tests/e2e -q` on a drop/recreated
    database — the 54-test official-client matrix under the qualified
    baseline; report exact counts. **Phase B must be 54 passed / 0
    failed / 0 skipped** to establish harness soundness for this run; a
    Phase B non-pass is an environment/harness finding: STOP the
    qualification, classify it with machine evidence, do NOT proceed to
    a candidate claim, and report.
  - Phase C: `python -m pytest tests/e2e -q` on a fresh drop/recreated
    database — the same 54-test matrix under `openai==3.14.1`; report
    exact counts.
  - Phase C ripple check: `scripts/test-unit-parallel.sh` (full unit
    suite; report exact counts; the only permitted non-pass is the
    labeled codex-cli case with `codex --version` proof) and
    `python -m pytest tests/integration -q` against a fresh user-owned
    disposable PostgreSQL 16 on `127.0.0.1:5433` (drop/recreated
    database; stop and remove after; the only permitted non-pass is the
    labeled pg_dump DSN-form skip with its recorded identity).
- **P3 — Failure classification (only if Phase C has any non-pass).**
  For each failing E2E test record: test id, the exact SDK call, the
  exact request body sent (redacted of secrets), the exact response
  received (status, headers of note, body), and classify as exactly one:
  1. **SDK test-harness change** — the test file itself uses an
     SDK client API that changed (renamed/removed/retyped). A harness
     fix in `tests/e2e/**` is permitted ONLY under this class, and only
     if the asserted wire/behavioral contract is unchanged: record the
     before/after diff of every changed test and a one-line justification
     per change that no assertion was weakened.
  2. **Legitimate new official-client behavior the Gateway should
     support** — no change in this order; `OUTCOME=NO-GO`; strategy
     decides whether the gap warrants a new objective.
  3. **Unsupported/deferred behavior newly exercised by the client** —
     cite the exact `docs/rc2-feature-scope.md` or
     `docs/openai-compatibility.md` deferral/limitation; no change;
     `OUTCOME=NO-GO`.
  4. **Gateway defect** — exact evidence; NO fix in this order (even if
     obvious); `OUTCOME=NO-GO`; strategy decides.
  5. **Version-specific incompatibility** — `OUTCOME=NO-GO`; strategy
     decides pin policy.
  No production code change is permitted under any class in this order.
- **P4 — Outcome branching.**
  - **PASS (`OUTCOME=A`)** — Phase C E2E is 54/0/0, the ripple check
    matches the labeled baseline, and no unclassified non-pass exists:
    1. `pyproject.toml`: `"openai==3.9.0"` becomes
       `"openai==3.14.1"` (the only functional edit; the ruff pin and
       `[tool.ruff.lint]` policy pin are untouched).
    2. `docs/openai-compatibility.md`: update the single sentence
       "The official OpenAI Python client E2E matrix (54 tests in
       `tests/e2e/`) is qualified under the dev/test pin
       `openai==3.9.0` per the dated record ..." so that it names
       `openai==3.14.1` and points at the new dated record, preserving
       the existing mocked-upstream limitation wording. No other
       sentence in that file changes.
    3. New dated record
       `docs/verification/2026-09-17-openai-sdk-3141-requalification.md`
       plus exactly one appended index row in
       `docs/verification/README.md` (same format as the existing 166
       row). The record names the exact base SHA and candidate version
       `3.14.1`, carries the single verdict line
       `OUTCOME=A` (or `OUTCOME=NO-GO`), the complete P1–P4 evidence
       (both freeze-line selections, both E2E count lines, ripple
       counts, CI table, any class-1 harness diff with justifications),
       and honest limitation sentences (mocked-upstream qualification
       only; not a real-provider run, release decision, security
       certification, or production approval; dated evidence for the
       named candidate only). The existing
       `docs/verification/2026-09-17-openai-sdk3-qualification.md`
       (3.9.0) remains byte-identical.
  - **FAIL (`OUTCOME=NO-GO`)** — any Phase C E2E non-pass that is not a
    fully justified class-1 harness fix, or any Phase B failure:
    1. `pyproject.toml` unchanged (`openai==3.9.0` stays the qualified
       pin).
    2. `docs/openai-compatibility.md` unchanged (its claim remains
       accurate).
    3. New dated record
       `docs/verification/2026-09-17-openai-sdk-3141-requalification.md`
       plus exactly one appended index row in
       `docs/verification/README.md`, carrying `OUTCOME=NO-GO`, the full
       P1–P3 evidence including the complete per-failure classification
       table with machine evidence, and the same honest limitation
       sentences.
- **P5 — Immutable report.** Publish the report per the report
  obligations below, as the report-only final commit.

## Allowed paths

- `pyproject.toml` (PASS branch only: the single openai pin line)
- `tests/e2e/**` (P3 class-1 harness compatibility only, with the
  required before/after diff and per-change justification)
- `docs/openai-compatibility.md` (PASS branch only: the single
  qualification sentence)
- `docs/verification/2026-09-17-openai-sdk-3141-requalification.md`
  (new dated record; both branches)
- `docs/verification/README.md` (exactly one appended index row)
- `oap/orders/172-a-openai-sdk-3141-requalification.md` (unchanged
  strategic work order)
- `oap/active` (`172-a`)
- `oap/reports/172-a-openai-sdk-3141-requalification.md` (new immutable
  report)

Nothing else.

## Explicit exclusions (non-goals)

- **No intermediate or other SDK version:** the candidate is exactly
  `3.14.1`. No 3.10–3.13 ladder, no 4.x, no pre-release, and no chase of
  a newer stable release published after order authoring.
- **No production code change of any kind**: `app/` is byte-identical in
  both outcome branches. A class-4 Gateway defect is reported, not
  fixed, in this order.
- **No contract loosening or capability addition:** no new accepted
  field, endpoint, tool behavior, error shape, or streaming form is
  introduced to satisfy new-SDK behavior; no feature work of any kind,
  even trivial.
- **No other dependency change:** the ruff pin and the
  `[tool.ruff.lint]` policy pin stay exactly as on `main`; no other
  dev/production dependency moves.
- **No test weakening:** no assertion is deleted, loosened, xfail-ed, or
  skipped to make the matrix green; the two labeled environment-only
  non-passes (codex-cli version case; pg_dump DSN-form skip) are the only
  permitted non-passes in the ripple check and each carries its proof.
- **No SBOM edit** (`sbom/cyclonedx.json` byte-identical; regeneration
  remains deferred to the next release-qualification objective).
- **No documentation edits** outside the two allowed documentation
  changes; in particular no edits to any existing
  `docs/verification/2026-*` file, `README.md`, or `AGENTS.md`.
- **No real provider calls:** the E2E matrix runs against the mocked
  official-client upstream infrastructure only; `RUN_UPSTREAM_TESTS` must
  remain unset throughout; no provider credentials present or used.
- **No PR interaction** (no touching of #224 or any other PR; no
  Dependabot action of any kind). No GitHub-settings action (branch
  protection, rulesets, required checks). No release, tag, or
  deployment. No edits to `tests/unit/test_oap_governance.py` or the
  order template — both are stable.

## Acceptance criteria

- **AP-1 — Decisive matrix (both phases, clean room, exact PR head).**
  The report contains: Phase B (3.9.0) E2E exact counts and the
  Phase-B-soundness statement (54/0/0 required); Phase C (3.14.1) E2E
  exact counts; both `pip freeze` selections verbatim. Every Phase C
  non-pass is classified per P3 with the exact machine evidence.
  `OUTCOME=A` requires Phase C 54 passed / 0 failed / 0 skipped with no
  unclassified non-pass; otherwise the verdict is `OUTCOME=NO-GO`.
- **AP-2 — Ripple check (Phase C only).** Unit suite exact counts with
  only the labeled codex-cli non-pass (proof: `codex --version` output);
  integration suite exact counts with only the labeled pg_dump skip
  (identity proof vs the 167/168/170/171 baseline). Any other
  non-pass is a finding to be classified per P3 and forces
  `OUTCOME=NO-GO` if it cannot be classified as environment-only with
  proof.
- **AP-3 — Diff scope per outcome branch.** PASS branch: `git diff` vs
  base touches exactly `pyproject.toml` (single openai line),
  `docs/openai-compatibility.md` (single sentence), the new dated
  record, the one index row, and the OAP order/active/report files —
  plus `tests/e2e/**` only if class-1 harness fixes were required, each
  with its recorded before/after diff and justification. NO-GO branch:
  `git diff` vs base touches exactly the new dated record, the one index
  row, and the OAP order/active/report files. Zero changes under `app/`
  in both branches; zero changes to the ruff pin or the
  `[tool.ruff.lint]` table; the 3.9.0 dated record byte-identical.
- **AP-4 — CI gates.** All nine emitted checks `success` on the exact
  final head, with run IDs recorded: `Unit, lint, and migration head`;
  `Documentation hygiene`; `OpenAI-compatible E2E tests`; `Playwright
  browser smoke`; `Docker Compose smoke`; `PostgreSQL integration
  tests`; `Analyze (javascript-typescript)`; `Analyze (python)`;
  `Analyze Python`. On the PASS branch the `OpenAI-compatible E2E tests`
  check is the in-CI proof that the matrix passes under `3.14.1`.
  Re-query all nine after the report-only commit per AP-6.
- **AP-5 — Documentation checker.** `python scripts/check_documentation.py`
  on the final tree prints `DOCUMENTATION_CHECK=OK` (file count grows by
  exactly one, the new dated record).
- **AP-6 — Immutable report.** One report
  `oap/reports/172-a-openai-sdk-3141-requalification.md` with the SELF
  topology: the report commit is the PR head, its first parent is the
  recorded implementation (or documentation, on the NO-GO branch) head,
  the report commit changes only the report file, the report contains the
  literal base SHA `1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`, the
  literal candidate version `3.14.1`, the single verdict line, and the
  merge-not-performed statement, and the remote PR head is verified as
  the report commit before the two-byte `OK` is written to the response
  FIFO. The AP-4 re-query on the final head is a mandatory gate before
  that OK.

## Verification and evidence commands

- P1: clone + checkout + `git rev-parse HEAD` + `git status --short` +
  per-phase `pip freeze` selection.
- P2: `python -m pytest tests/e2e -q` (Phase B, then Phase C, each on a
  drop/recreated database); `scripts/test-unit-parallel.sh` (Phase C);
  `.venv/bin/python -m pytest tests/integration -q` (Phase C, fresh
  disposable PG on `127.0.0.1:5433`); `codex --version`.
- P3: per failing test — the recorded SDK call, request/response capture,
  and the classification line with its citation or diff.
- P4: `git diff --name-only <base>..<head>` and the full diff of every
  non-OAP changed file; `python scripts/check_documentation.py`.
- AP-4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` (record
  the command and run IDs; re-query after the report commit).
- `git diff --check`.

## Security, privacy, accounting, and boundaries

- The change (PASS branch) is a development/test pin plus a
  documentation update; no runtime dependency, no schema, no migration,
  no configuration surface, no trust/identity/secret/content boundary is
  touched. PostgreSQL remains quota/accounting truth and is untouched.
- No production/staging system, no real provider, no real email, no
  external call of any kind beyond the local disposable stack, the PyPI
  index for dependency installation, and the GitHub API for check
  queries.
- Request/response evidence in the report and record must be redacted of
  any secret, key, prompt, completion, or canary value; only safe
  booleans, counts, statuses, SHAs, and redacted payloads are recorded.

## Stop / escalation conditions

- If Phase B (baseline 3.9.0) E2E is not 54/0/0: STOP the qualification,
  classify the baseline non-pass with exact machine evidence (harness /
  environment / candidate), do not proceed to a candidate claim, and
  report; strategy decides the follow-up.
- If any Phase C failure falls in P3 classes 2–5: do not fix, do not
  expand scope, do not change production code; classify with exact
  evidence and issue `OUTCOME=NO-GO`. Strategy alone decides whether the
  discovered gap warrants a new numeric objective.
- If a class-1 harness fix would require weakening or deleting any
  assertion: it is NOT class-1; reclassify per P3 and the verdict is
  `OUTCOME=NO-GO`.
- If a required CI check is not `success` on the final head for a cause
  other than the labeled environment-only items: record the exact
  failing assertion and report; do not weaken the governance test, the
  order template, or any acceptance predicate.
- Suffix rounds (`172-b`...) are for bounded correction of this
  objective only, not for scope growth, pin-policy decisions, or defect
  fixing.

## Setup authority

- Fresh clone and venv under `/tmp/obj172-cleanroom/` (disposable; remove
  after the objective).
- Fresh disposable PostgreSQL 16 under `/tmp/obj172-pg/` on
  `127.0.0.1:5433` for the integration suite and the E2E database
  (stop and remove after).
- Disposable/generated credentials only; no reuse of the 5432 system
  cluster.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and file,
PR mode, status, executive summary, authoritative GitHub state (PR
number, URL, state, base/head SHAs, starting remote SHA
`1f76ece6e0457fe78fe29b5e188ea484cf0bfa09`, implementation head, report
publication commit `SELF`, merge-not-performed), the single verdict line
(`OUTCOME=A` or `OUTCOME=NO-GO`), full changed-file list, per-AP
evidence (both phases' `pip freeze` selections, both E2E count lines,
ripple counts, the complete P3 classification table if any non-pass, the
nine check run IDs on the final head, and the class-1 before/after diffs
if any), local verification, negative evidence (no `app/` change, no
other dependency change, no contract loosening, no test weakening, no
SBOM edit, no other documentation edit, no PR/Dependabot/GitHub-settings
action, no real provider calls, no secrets), CI gate state on the final
head, and the environment-only labels with proofs.

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is left
OPEN for strategic review and the delegated merge authority.
