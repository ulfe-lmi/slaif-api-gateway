# OAP Work Order — 171-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Bump the pinned development lint tool from `ruff==0.15.16` to
`ruff==0.16.7` and, in the same one-file change, make the repository's
effective lint policy **explicit and version-stable** by pinning exactly the
default rule set that ruff 0.15.16 applied.

This objective is driven by live Dependabot signal (PR #250 proposes
`ruff 0.15.16 -> 0.16.7`; its openai half is explicitly out of scope here)
and closes the ruff half of that signal with a clean OAP transcript. It is
governance/toolchain debt, not capability.

Strategic finding that shapes this order (machine-verified by the strategic
model on 2026-09-17 ~16:40 Europe/Ljubljana against the shared worktree at
remote `main`):

- `ruff==0.15.16` on current `main`: `ruff check app tests` reports
  **0 findings** (`All checks passed!`).
- `ruff==0.16.7` on the same tree, same config, **without** a pin:
  **`Found 1293 errors`** (1008 `--fix`-able, 93 unsafe-fix, 190
  non-fixable) across 429 files.
- Cause, verified via `--show-settings` on both versions: **ruff 0.16
  expanded its default rule selection** from the 0.15.16-era default
  (59 rules; prefixes E4, E7, E9, F) to a much larger default set covering
  B, BLE, C4, DTZ, ASYNC, FLY, FURB, I, ISC, PIE, PLR/PLW/PLC, RET, RUF,
  S, SIM, TRY, UP, YTT and others. The repository config carries no
  explicit `lint.select`, so its effective lint policy silently changes
  with the dependency version.
- Consequence: a naive version bump is not a drop-in; it is an implicit
  adoption of a materially stricter policy, including ~190 non-auto-fixable
  findings that touch error-handling and evaluation semantics (e.g. B008
  function-call-in-default-argument, BLE001 blind-except, PLW1510
  subprocess-run-without-check, TRY004, S112, DTZ001, ASYNC220/ASYNC221,
  RUF012). That policy migration is a separate, larger, deliberately
  decided objective. **It is explicitly deferred and out of scope here.**
- The strategic model verified that pinning `select = ["E4", "E7", "E9",
  "F"]` makes `ruff==0.16.7` report **0 findings** on current `main`, and
  that the effective `linter.rules.enabled` set under that pin is
  **byte-identical (59 rules)** between ruff 0.15.16 and ruff 0.16.7.
  The exact baseline set is embedded in AP-1 below.

The resulting change is two lines in `pyproject.toml` (version bump +
explicit `select` pin) with zero application/test code changes. It converts
an implicit, version-drift-prone lint policy into an explicit, auditable
one: from now on, adopting any new rule or rule family is a deliberate,
separately scoped policy decision rather than a silent side effect of a
dependency bump.

The PR #250 evidence showing the red check for the unpinned bump: run
35193923676 / job 105112572194 (`Unit, lint, and migration head` =
failure, `Found 1290 errors` on the 2026-09-17 base; the small count
difference vs the 1293 measured on current `main` is base drift, same
class). This order's acceptance makes that check green by construction and
re-proves it in CI.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-17 ~16:30 Europe/Ljubljana from
live GitHub and the shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main` (the base for this order):
  `cff2d798d6b170070674ca0f69e234d2d1bad8f6` — merge of PR #307
  (Objective 170, merged 2026-09-17T14:14:16Z). All nine emitted
  main-branch checks on this commit are `completed`/`success`
  (re-verified 2026-09-17 ~16:24 Europe/Ljubljana).
- Objectives 166 (`openai==3.9.0` qualified, PR #303), 168 (PR #305), 170
  (PR #307) are terminal and verified. Objective 169 is terminal-abandoned
  (PR #306 closed; findings preserved on its branch).
- Shared `oap/active` is terminal at `170-a`. This order activates `171-a`.
- Open PRs are exactly #250 (Dependabot; head `e42207da`; single changed
  file `pyproject.toml` with diff `openai==3.9.0 -> 3.13.0` and
  `ruff==0.15.16 -> 0.16.7`; `Unit, lint, and migration head` red on its
  head for the unpinned-bump reason above) and #224 (Dependabot GitHub
  Actions group; stale). **This order touches neither PR.** The openai
  half of #250 (`3.9.0 -> 3.13.0`) is a separate compatibility question
  that remains a live update signal for a future strategic decision; the
  ruff half is the subject of this order.
- PR #291 (Objective 155) remains closed-as-superseded; branch retained as
  historical evidence only.
- `docs/rc2-feature-scope.md` classification summary: 27
  `RC2_REQUIRED_IMPLEMENTED`, 0 `RC2_REQUIRED_MISSING`, 17
  `RC2_EXPLICITLY_DEFERRED`, 1 `RC2_UNSUPPORTED_BY_POLICY`, 6
  `NEEDS_MAINTAINER_DECISION`.
- Branch protection: ruleset `protect main` (id 23580289) active with
  `non_fast_forward` + `deletion` only, no bypass actors; `basic-protect`
  and `Code Quality Copilot review` rulesets disabled. Completion of branch
  protection is a human GitHub-administration action and is explicitly
  outside this order.
- `pyproject.toml` line 47 currently reads `"ruff==0.15.16"` (dev
  dependency); `[tool.ruff]` contains only `line-length = 100`.
  `.github/workflows/ci.yml` runs `python -m ruff check app tests` using
  the installed dev pin — no workflow change is needed or allowed.
- The committed `sbom/cyclonedx.json` is a point-in-time snapshot
  (timestamp 2026-08-23, rc1 era) that already predates the Objective 166
  `openai==3.9.0` pin; it carries no per-component hashes and no in-repo
  generator. It is deliberately excluded from this order (see exclusions).
- Known environment-only items (label, do not chase): execution VM
  `codex-cli 0.154.0` vs the fixture pin `0.148.0` (one labeled unit case);
  local-VM `pg_dump` DSN-form skip in the integration suite (identical to
  the 167/168/170 baseline); the 5432 system PG cluster carries 168-era
  diagnostic residue — use a fresh disposable cluster for the integration
  suite.

## PR contract

- Base: `main` at `cff2d798d6b170070674ca0f69e234d2d1bad8f6`.
- Branch: `oap/171-ruff-0-16-7-policy-pinned-bump`.
- Title: `obj171: pin lint policy and bump ruff to 0.16.7`.
- One new PR for `171-a`; later `171-b`... rounds amend the same PR.
- Commit the unchanged strategic-authored order and `oap/active` per the
  coding-agent protocol. The order file is template-conforming as authored
  (first content line after the title is `PR mode: \`CREATE_NEW_PR\``); it
  must reach the PR head byte-identical so the candidate's governance unit
  test `tests/unit/test_oap_governance.py` passes on this PR head.

## Required change (exact)

The only functional change is in `pyproject.toml`:

1. Dev dependency list: `"ruff==0.15.16"` becomes `"ruff==0.16.7"`.
2. The existing `[tool.ruff]` section keeps `line-length = 100` and gains a
   nested `[tool.ruff.lint]` table containing exactly:

   ```toml
   [tool.ruff.lint]
   # Explicit policy pin: the exact default rule set that ruff 0.15.16
   # applied (59 rules; prefixes E4, E7, E9, F). Ruff 0.16 expanded its
   # default selection; without this pin the effective lint policy would
   # silently change with the dependency version (1293 findings on the
   # current tree). Adopting any additional rule or rule family is a
   # separate, deliberate policy objective (see Objective 171 order).
   select = ["E4", "E7", "E9", "F"]
   ```

   The comment text above is normative: it must appear (wording may be
   shortened only if it preserves the same meaning) so future readers see
   that the pin is a deliberate policy decision, not leftover config.

3. Nothing else changes. The candidate version is exactly `0.16.7` — the
   Dependabot target at order-authoring time. If a newer ruff release has
   appeared by execution time, do not chase it; `0.16.7` is the candidate
   under qualification and the order remains valid.

## Allowed paths

- `pyproject.toml` (exactly the two changes above)
- `oap/orders/171-a-ruff-0-16-7-policy-pinned-bump.md` (unchanged
  strategic work order)
- `oap/active` (`171-a`)
- `oap/reports/171-a-ruff-0-16-7-policy-pinned-bump.md` (new immutable
  report)

Nothing else.

## Explicit exclusions (non-goals)

- **No OpenAI SDK change of any kind.** `openai==3.9.0` stays pinned. The
  `3.9.0 -> 3.13.0` half of Dependabot #250 is a separate strategic
  question and must not be folded in.
- **No adoption of any new lint rule or rule family** beyond the pinned
  59-rule baseline set, and no loosening of any currently effective rule.
  No `--fix`, `--unsafe-fixes`, or mass-edit run of any kind. No new
  `# noqa`, per-file ignores, `extend-select`, `ignore`, or
  `lint.flake8-...`-style overrides.
- **No changes to any application, test, or CI code**: `app/`, `tests/`,
  `scripts/`, `.github/`, `migrations/`, `nginx/`, `Dockerfile`,
  `docker-compose*.yml`, `Makefile`, or any other repository file outside
  the allowed paths. This includes `tests/unit/test_oap_governance.py` —
  the governance test and the order template are to be treated as stable.
- **No SBOM edit.** `sbom/cyclonedx.json` stays byte-identical. It is a
  point-in-time snapshot without per-component hashes; hand-editing its
  ruff version would produce an internally inconsistent SBOM. Its
  regeneration (already stale w.r.t. the 166 openai pin) is deferred to the
  next release-qualification objective. State this in the report.
- **No documentation edits**, including `README.md`, `AGENTS.md`, and
  `docs/**` (their ruff references are version-agnostic), and no edits to
  any existing `docs/verification/2026-*` file.
- **No PR interaction**: do not close, rebase, merge, comment on, or
  otherwise touch PR #250, #224, or any other PR; no Dependabot action of
  any kind.
- No GitHub-settings action (branch protection, rulesets, required
  checks). No release, tag, or deployment. No real provider calls;
  `RUN_UPSTREAM_TESTS` must remain unset. No new product capability, even
  if trivially attractive.

## Acceptance criteria

- **AP-1 — Policy identity (decisive).** In a clean-room venv created from
  the exact PR head (see P1), `pip show ruff` reports `Version: 0.16.7`
  installed from the new pin. Then:
  - `python -m ruff check app tests` prints `All checks passed!` (0
    findings).
  - `python -m ruff check app tests --show-settings` resolves
    `linter.rules.enabled` to **exactly** the 59-rule baseline set below,
    with the diff against the baseline empty (record the command and the
    empty diff as evidence):

    ```text
    E401, E402, E701, E702, E703, E711, E712, E713, E714, E721, E722,
    E731, E741, E742, E743, E902, F401, F402, F403, F404, F405, F406,
    F407, F501, F502, F503, F504, F505, F506, F507, F508, F509, F521,
    F522, F523, F524, F525, F541, F601, F602, F621, F622, F631, F632,
    F633, F634, F701, F702, F704, F706, F707, F722, F811, F821, F822,
    F823, F841, F842, F901
    ```

  Any extra or missing rule in the effective set fails AP-1. If 0.16.7
  resolves `["E4", "E7", "E9", "F"]` to a set different from the baseline
  (i.e. new rules were added under those prefixes), STOP and escalate per
  the stop conditions — do not suppress the difference with `ignore`
  entries and do not adopt the difference.
- **AP-2 — Diff scope.** `git diff` vs base touches exactly the four
  allowed paths; zero changes under `app/`, `tests/`, `scripts/`,
  `.github/`, `migrations/`, `nginx/`, `docs/`, `sbom/`, and zero changes
  to `Dockerfile`, `docker-compose*.yml`, `README.md`, `AGENTS.md`, or
  `Makefile`. The `pyproject.toml` diff contains exactly the version line
  and the new `[tool.ruff.lint]` table.
- **AP-3 — Full local matrix (clean room), behavior unchanged.** On the
  exact PR head in the clean room:
  - `scripts/test-unit-parallel.sh` — full unit suite; report exact
    passed/failed/skipped counts. The only permitted non-pass is the
    labeled environment-only case
    `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
    (VM `codex-cli 0.154.0` vs fixture pin `0.148.0`; record
    `codex --version` as proof).
  - `python -m pytest tests/integration -q` against a fresh user-owned
    disposable PostgreSQL on `127.0.0.1:5433` (drop/recreated database;
    stop and remove the instance after); report exact counts. The only
    permitted non-pass is the labeled local-VM `pg_dump` DSN-form skip,
    identical to the 167/168/170 baseline.
  - `python -m pytest tests/e2e -q` on a drop/recreated database — the
    54-test official-client matrix must be **54 passed / 0 failed /
    0 skipped** with `openai==3.9.0` (pin unchanged; record the `pip
    freeze` line for `openai` as proof).
  Any other non-pass, ERROR, or skip is a finding: classify it with machine
  evidence (candidate defect / harness-side / environment-only with proof);
  do not chase or suppress it.
- **AP-4 — CI gates.** All nine emitted checks `success` on the exact PR
  head, with run IDs recorded: `Unit, lint, and migration head`;
  `Documentation hygiene`; `OpenAI-compatible E2E tests`; `Playwright
  browser smoke`; `Docker Compose smoke`; `PostgreSQL integration tests`;
  `Analyze (javascript-typescript)`; `Analyze (python)`; `Analyze Python`.
  `Unit, lint, and migration head` success on this head is the
  in-CI proof that the unpinned-bump failure mode (PR #250 job
  105112572194) is resolved by the pin. Re-query all nine after the
  report-only commit per AP-6.
- **AP-5 — Documentation checker.** `python scripts/check_documentation.py`
  on the final tree prints `DOCUMENTATION_CHECK=OK` with the file count
  unchanged (no documentation files are added or edited).
- **AP-6 — Immutable report.** One report
  `oap/reports/171-a-ruff-0-16-7-policy-pinned-bump.md` with the SELF
  topology: the report commit is the PR head, its first parent is the
  recorded implementation head, the report commit changes only the report
  file, the report contains the literal base SHA, the literal candidate
  ruff version `0.16.7`, and the merge-not-performed statement, and the
  remote PR head is verified as the report commit before the two-byte `OK`
  is written to the response FIFO. The AP-4 re-query on the final head is a
  mandatory gate before that OK.

## Verification and evidence commands

- P1 (clean room): fresh clone of the remote into
  `/tmp/obj171-cleanroom/`, detached checkout of the exact PR head,
  `git status --short` empty, fresh `.venv` (Python 3.12.x), record
  `pip freeze` lines for `ruff`, `openai`, `fastapi`, `pydantic`, `httpx`,
  `respx`, `pytest`, `asyncpg`, `prometheus_client`, `gunicorn`, `uvicorn`.
  All candidate code runs only from the clean room.
- AP-1: `pip show ruff`; `python -m ruff check app tests`;
  `python -m ruff check app tests --show-settings | awk '/linter.rules.enabled = \[/{f=1;next} f&&/^\]/{exit} f'`
  extracted to a file, `sort`ed, diffed against the embedded 59-rule
  baseline (record the empty diff).
- AP-2: `git diff --name-only <base>..HEAD` and the full `git diff` of
  `pyproject.toml`.
- AP-3: as listed in AP-3, plus `codex --version`.
- AP-4: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` (record
  the command and run IDs; re-query after the report commit).
- AP-5: `python scripts/check_documentation.py`.
- `git diff --check`.

## Security, privacy, accounting, and boundaries

- The change is a development-tooling pin plus an explicit lint-policy
  declaration; no runtime dependency, no schema, no migration, no
  configuration surface, no trust/identity/secret/content boundary is
  touched. PostgreSQL remains quota/accounting truth and is untouched.
- No production/staging system, no real provider, no real email, no
  external call of any kind beyond the local disposable stack and the
  GitHub API for check queries.
- No secret, key, prompt, completion, or canary value may appear in the
  report (redact any disposable password).

## Stop / escalation conditions

- If the effective rule set under the pin deviates from the 59-rule
  baseline in AP-1 (missing or extra rule under E4/E7/E9/F in 0.16.7):
  STOP. Do not add `ignore` entries, do not adopt the new rule, do not
  hand-edit the baseline. Record the exact diff and report; strategy
  decides the fallback (candidate: an explicit per-rule `select` list).
- If any AP-3 suite shows a non-pass outside the two labeled
  environment-only items: do not fix, do not expand scope; classify with
  exact machine evidence, complete the remaining safe phases, and report
  the finding. Strategy alone decides any follow-up numeric objective.
- If `Unit, lint, and migration head` is not `success` on the PR head for
  a cause other than the two labeled environment-only items: record the
  exact failing assertion and report; do not weaken the governance test or
  the template.
- Suffix rounds (`171-b`...) are for bounded correction of this objective
  only, not for scope growth, rule adoption, or defect fixing.

## Setup authority

- Fresh clone and venv under `/tmp/obj171-cleanroom/` (disposable; remove
  after the objective).
- Fresh disposable PostgreSQL 16 under `/tmp/obj171-pg/` on
  `127.0.0.1:5433` for the integration suite (stop and remove after).
- Generated/disposable credentials only; no reuse of the 5432 system
  cluster.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and file,
PR mode, status, executive summary, authoritative GitHub state (PR number,
URL, state, base/head SHAs, starting remote SHA
`cff2d798d6b170070674ca0f69e234d2d1bad8f6`, implementation head, report
publication commit `SELF`, merge-not-performed), full changed-file list,
per-AP evidence (including the exact AP-1 command outputs and the empty
baseline diff, the `pip show ruff` / `pip freeze` lines, and the nine
check run IDs on both the implementation head and the final head), local
verification, negative evidence (no `openai` change, no code change, no
new-rule adoption, no `noqa`/ignore additions, no SBOM edit, no
documentation edit, no PR/Dependabot interaction, no real provider calls,
no secrets, no release/deploy/GitHub-settings action), CI gate state on
the final head, the SBOM-staleness deferral statement, and the
environment-only labels with proofs.

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is left
OPEN for strategic review and the delegated merge authority.
