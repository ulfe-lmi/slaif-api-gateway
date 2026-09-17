# OAP Work Order — 166-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Determine whether the current Gateway preserves its declared official
OpenAI-client compatibility contract when exercised through OpenAI Python
SDK `3.9.0`, and produce one decisive, machine-verifiable qualification
result against current `main`:

- **OUTCOME A** — the declared compatibility surface holds under
  `openai==3.9.0`: update the supported dev/test pin deliberately to
  `openai==3.9.0`, prove the complete official-client E2E matrix under that
  pin in CI, and publish a dated qualification record.
- **OUTCOME B** — one or more surfaces cannot be qualified under
  `openai==3.9.0` within the declared contract without a product decision:
  keep the pin at `openai==2.41.0`, and publish a dated qualification
  record containing the full compatibility matrix, per-failure wire
  evidence, and classified failures, so the boundary becomes explicit
  evidence instead of an assumption.

This is a compatibility qualification, not dependency cleanup. Background
evidence verified by the strategic model: Dependabot PR #250 (`openai
2.41.0 -> 3.9.0` bundled with `ruff 0.15.16 -> 0.16.6`, head
`2b77b1500ff28892eb45ee54d7ab5344001b02d0` on stale base
`d142fd7f04c46fac3469b9b9bba1bd2068aabad8`) has RED CI: the
`OpenAI-compatible E2E tests` job failed 42 of 51 tests with `RESPX: some
routes were not called!` (SDK 3.9.0 wire-shape drift against the mocked
upstream routes), and `Unit, lint, and migration head` failed on ruff
0.16.6 import-sorting drift (run 34649258907, jobs 103427314214 and
103427314492). That log is a drift-signature hypothesis on a stale base;
this objective re-derives the truth on current `main`. The ruff half of
#250 is explicitly out of scope, and #250 is not a merge vehicle for this
objective.

The question is not "does dependency installation succeed?" It is "does the
current Gateway preserve its declared official OpenAI-client compatibility
contract when exercised through OpenAI Python SDK 3.9.0?"

## Reconciled authority and current state

Verified 2026-09-17 by the strategic model against live GitHub and the
shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main`:
  `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` (merge of PR #302 /
  Objective 165, merged 2026-09-17T00:44:18Z), merge tree
  `4aa218be7f78d3281dd87b18d698f648044e19ce`, app tree
  `3cf53dec5abde686d3903f234f05207faf9d5996`.
- All nine emitted main-branch checks on that commit are SUCCESS
  (completed by 2026-09-17T00:47:17Z): `Unit, lint, and migration head`;
  `Documentation hygiene`; `OpenAI-compatible E2E tests`; `Playwright
  browser smoke`; `Docker Compose smoke`; `PostgreSQL integration tests`;
  `Analyze (javascript-typescript)`; `Analyze (python)`; `Analyze Python`.
- Objective 165 is terminal and verified (PR #302; app tree
  byte-identical across the merge). Shared `oap/active` starts at terminal
  `165-a`. Objective 166 is unused: no `166-*` order, report, branch, or
  PR exists.
- Open PRs are exactly #250 (Dependabot python-dependencies group: openai
  2.41.0 -> 3.9.0 plus ruff 0.15.16 -> 0.16.6; MERGEABLE; RED CI as above)
  and #224 (Dependabot github-actions group, stale). Both remain untouched
  by this objective.
- `openai==2.41.0` is pinned only in `[project.optional-dependencies] dev`
  of `pyproject.toml`. No `openai` SDK import exists in `app/` (gateway
  runtime); the SDK is a development/test dependency used exclusively by
  the official-client E2E harness in `tests/e2e/`.
- The official-client E2E suite on current `main`: 8 files, 54 collected
  tests (verified via `pytest tests/e2e --collect-only`):
  `test_openai_python_client_audio.py` (3), `test_openai_python_client_chat.py`
  (15), `test_openai_python_client_embeddings.py` (1),
  `test_openai_python_client_realtime.py` (1),
  `test_openai_python_client_responses.py` (26),
  `test_openai_python_client_streaming.py` (6),
  `test_openrouter_python_client_chat.py` (1),
  `test_openrouter_python_client_streaming.py` (1). The CI `e2e` job
  installs `.[dev]` from this repository and runs `python -m pytest
  tests/e2e` against a real local gateway (uvicorn), real disposable
  PostgreSQL/Redis, and respx-mocked upstream providers; the pyproject pin
  therefore determines the SDK version CI qualifies.
- `docs/rc2-feature-scope.md` reports 27 `RC2_REQUIRED_IMPLEMENTED` and 0
  `RC2_REQUIRED_MISSING`.
- `docs/verification/` is the dated evidence archive under the
  Objective-165 authority model; `docs/beta-readiness.md` is a dated record
  (as-of `8f2813bf745b90221da33a7cfaf40726c5b1b480`) and is immutable for
  this objective.
- Branch `main` currently has the active ruleset `protect main`
  (non-fast-forward and deletion rules). This objective performs no
  GitHub-settings change.
- The execution VM has a known environment-only unit failure:
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (VM codex CLI version versus fixture pin). It reproduces on the base
  commit and is unrelated to dependency changes; it must be reported as
  environment-only and kept distinct from any diff-caused failure.

## PR contract

- Base: `main` at `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb`.
- Branch: `oap/166-openai-sdk3-compatibility-qualification`.
- Title: `obj166: qualify OpenAI Python SDK 3.9.0 official-client compatibility`.
- One new PR for `166-a`; later `166-b`... rounds amend the same PR.

## Qualification design (required sequence)

Q1 — Baseline. On the PR-head code in the shared environment (openai
2.41.0), run the full official-client E2E matrix against the disposable
local PostgreSQL `TEST_DATABASE_URL` harness. Expected: 54 passed,
matching green CI on base. Record exact counts and the installed versions
(`pip freeze` lines for at least `openai`, `httpx`, `pydantic`).

Q2 — Candidate environment. Build an isolated reproducible environment
(separate venv, Python 3.12): install the package with dev dependencies,
then force `openai==3.9.0`. Record `pip freeze` lines for `openai`,
`httpx`, `pydantic`, and every transitive dependency whose version
differs from the baseline environment.

Q3 — Candidate matrix. Run the same 54-test matrix in the candidate
environment. For every failure, capture wire-level evidence: the exact
HTTP request the SDK issued (method, path, query string, full headers,
request body) and the mocked route expectation that was not satisfied.
Use respx diagnostics or a temporary local capture harness; the capture
scaffolding is disposable and must not be committed unless it becomes a
permanent regression assertion inside an allowed path.

Q4 — Root cause and classification. Group all failures into distinct
root-cause families (expected: a small number of families, not per-test
ad-hoc explanations). For each family record the exact wire diff relative
to 2.41.0 baseline behavior and classify it as exactly one of:

- **(a) SDK API/harness change** — test-code adaptation (moved/renamed
  client API, imports, namespaces, typed-streaming event shapes, method
  signatures): update the `tests/e2e` harness only.
- **(b) Contractually-neutral new wire shape** — a standard OpenAI
  header/field the official client now sends that the gateway's declared
  OpenAI-compatible envelope already accepts, forwards, or ignores: update
  the mocked route expectation to assert the new exact wire shape
  (preferred remedy; strengthens the harness).
- **(c) Gateway declared-contract violation** — the gateway rejects a
  standard OpenAI request the official client now sends, in conflict with
  `AGENTS.md` section 1.3/1.4 or `docs/openai-compatibility.md`: minimal
  gateway fix with explicit positive and negative tests; each fix must
  cite the exact contract line it enforces.
- **(d) Product decision required** — behavior beyond the declared scope
  (for example a new endpoint or feature surface such as prompt-cache
  diagnostics): classify unsupported/deferred; do not implement; record
  the evidence and the decision question for strategy.
- **(e) Gateway defect** — a genuine defect exposed by the new SDK: fix
  with evidence.

Q5 — Decision, stated in the report verbatim as `OUTCOME=A` or
`OUTCOME=B`:

- **OUTCOME A** — all 54 tests pass under `openai==3.9.0` using only
  allowed changes (harness expectation updates plus any (c)/(e) fixes,
  each contract-justified): set the `pyproject.toml` dev-extra pin to
  exactly `openai==3.9.0`; update the qualified-version statement in
  `docs/openai-compatibility.md`; the CI E2E job on the final PR head must
  run the matrix under 3.9.0.
- **OUTCOME B** — any surface cannot be qualified under `openai==3.9.0`
  within the declared contract without a product decision: keep the pin
  at exactly `openai==2.41.0`; make no gateway changes beyond (c)/(e)
  fixes already justified; the dated record (Q6) documents the boundary.

Q6 — Dated qualification record. In both outcomes, create
`docs/verification/2026-09-17-openai-sdk3-qualification.md` containing:
evidence boundary (base `main` SHA and exact PR-head SHA), environment
versions, the 54-row compatibility matrix, root-cause families with wire
evidence and classification, the outcome, and honest limitations
(mocked-upstream qualification only; not a real-provider run; not a
release, production, security, compliance, or SLA approval). Append one
index row to `docs/verification/README.md`.

Q7 — Final verification. Re-run the full local verification below on the
final PR-head code in the environment matching the final pin, then wait
until all nine required CI checks succeed on the final head.

## Allowed paths

Exactly these (plus the OAP protocol files):

- `pyproject.toml` — the single `openai` line in
  `[project.optional-dependencies] dev` only
- `tests/e2e/` — the official-client harness files and their shared
  helpers
- `app/` — only for (c)/(e) fixes; every hunk must be contract-justified
  in the report; none is expected
- `docs/openai-compatibility.md` — the qualified-SDK-version statement
  only
- `docs/verification/README.md` — one appended index row
- `docs/verification/2026-09-17-openai-sdk3-qualification.md` (new)
- `oap/orders/166-a-openai-sdk3-compatibility-qualification.md`
  (unchanged strategic bytes), `oap/active`,
  `oap/reports/166-a-openai-sdk3-compatibility-qualification.md`

No other path may appear in the diff.

## Explicit exclusions (non-goals)

- The ruff `0.15.16 -> 0.16.6` update, and every dependency change other
  than the single `openai` pin.
- Dependabot PRs #250 and #224: no merging, closing, rebasing, editing, or
  use as merge vehicles.
- No workflow-file, migration, product-capability, deployment,
  release/tag, or GitHub-settings/branch-protection change (human/admin
  domain).
- No gateway-contract loosening to satisfy the new SDK: no removed
  endpoint/policy gates, no weakened validation or fail-closed behavior,
  no deleted or skipped/xfail-ed tests, no weakened assertions to force a
  pass, and no tests added for explicitly unsupported/deferred surfaces
  to inflate surface area.
- Historical evidence is immutable: no edits to existing
  `docs/verification/2026-*` files (including the `2.41.0` mention in
  `2026-08-17-current-main-baseline.md`) or to the dated bodies of
  `docs/beta-readiness.md`.
- No live provider calls: the E2E matrix runs fully against mocked
  upstreams; `RUN_UPSTREAM_TESTS` stays unset; no provider credentials in
  any artifact.

## Evidence expectations (machine-checkable report content)

- A compatibility matrix with exactly 54 rows (test identities, grouped by
  surface: models; chat non-streaming; chat streaming; chat
  multimodal/file/audio forms; local function/custom tools; responses
  non-streaming; typed responses streaming; stored-response lifecycle;
  input tokens; compact; previous_response_id; conversations and
  conversation items; audio speech/transcription/translation; embeddings;
  realtime client-secret; OpenRouter chat/streaming; error,
  authentication, and omission coverage as exercised): for each row,
  baseline 2.41.0 result, candidate 3.9.0 result, root-cause family ID
  (if any), and disposition.
- Per root-cause family: exact wire evidence (method/path/query/headers/
  body diff versus 2.41.0 baseline behavior), classification (a)-(e), and
  remedy or deferral rationale. Counts must be internally consistent
  (families, tests affected per family, harness adaptations, gateway
  fixes, deferred surfaces).
- Environment proof: `pip freeze` lines (at least `openai`, `httpx`,
  `pydantic`) for both baseline and candidate environments.
- Diff proof: no `def test_` line removed from `tests/e2e/`; the `app/`
  diff is empty or contract-justified per hunk; the `pyproject.toml` diff
  touches exactly one line.
- CI proof: the final-head E2E job log line showing the installed `openai`
  version (the `Successfully installed openai-<version>` line) matching
  the final pin.

## Acceptance criteria

- **AP-1** — CI: all nine required checks SUCCESS on the final PR head:
  `Unit, lint, and migration head`; `Documentation hygiene`;
  `OpenAI-compatible E2E tests`; `Playwright browser smoke`; `Docker
  Compose smoke`; `PostgreSQL integration tests`; `Analyze
  (javascript-typescript)`; `Analyze (python)`; `Analyze Python`.
- **AP-2** — The `OpenAI-compatible E2E tests` job on the final head ran
  the 54-test matrix under the final pin with zero failures; the report
  cites the installed-version log line.
- **AP-3** — `pyproject.toml` dev extras contain exactly `openai==3.9.0`
  (OUTCOME A) or exactly `openai==2.41.0` (OUTCOME B); the report states
  the outcome verbatim.
- **AP-4** — The report contains the full 54-row compatibility matrix
  with per-failure wire evidence, per-family classification, and
  internally consistent counts.
- **AP-5** — `docs/verification/2026-09-17-openai-sdk3-qualification.md`
  exists with the named evidence boundary and is indexed in
  `docs/verification/README.md`; `docs/openai-compatibility.md` states a
  qualified SDK version matching the final pin.
- **AP-6** — No deleted or skipped/xfail-ed tests; no contract loosening
  (per the diff proof); PostgreSQL remains quota/accounting truth (no
  accounting code or schema change); no trust, secret, identity, or
  content boundary widened; local/hosted tool boundaries untouched.
- **AP-7** — One immutable report
  `oap/reports/166-a-openai-sdk3-compatibility-qualification.md` with
  literal implementation head SHA and `Report publication commit: SELF`;
  the final report-only commit changes only that report file, has the
  recorded implementation head as first parent, and is pushed and verified
  as the remote PR head before signalling `OK` on the response FIFO.

## Verification and evidence commands

Run and report exactly:

- Baseline: `python -m pytest tests/e2e -q` (shared environment, openai
  2.41.0, disposable local PostgreSQL via `TEST_DATABASE_URL`, standard
  harness such as `scripts/create-test-db.sh`) — expected 54 passed.
- Candidate: the same command in the isolated `openai==3.9.0`
  environment, with per-failure wire capture per Q3.
- Final: the same command in the environment matching the final pin —
  54 collected, 0 failed.
- `python -m pytest tests/unit -q` (full unit suite; report
  passed/failed/skipped exactly; if the known VM-only codex-CLI-version
  failure appears, prove it environment-only by reproducing it on base
  commit `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` in a read-only
  detached worktree and label it as such).
- `python -m ruff check app tests` (ruff remains 0.15.16)
- `alembic heads`
- `python scripts/check_documentation.py` (must print
  `DOCUMENTATION_CHECK=OK files=<n>`)
- `git diff --check`

## Security, privacy, accounting, and boundaries

- No secrets, keys, prompts, completions, or provider data in any changed
  file or report; the E2E matrix uses only the existing mocked-upstream
  fixtures.
- No real provider calls, no production data, no Local mutation, no
  deployment or release action, no GitHub-settings action.
- PostgreSQL remains quota/accounting truth; no accounting code or schema
  changes. Fail-closed behavior is preserved wherever support is not
  justified.

## Stop / escalation conditions

- If more than three distinct (d) product-decision families surface, or
  any remedy requires a new endpoint/feature/product behavior beyond the
  declared contract: stop. Publish the evidence gathered (the matrix so
  far, wire evidence, classification), the report with status
  `ESCALATION`, no pin change, no gateway change, no scope expansion.
  Strategy decides whether a narrower `166-b` or a new numeric objective
  follows.
- If a (c) fix reveals broader contract drift than a minimal fix
  addresses: stop with the same treatment.
- Suffix rounds (`166-b`...) are for bounded correction of this objective
  only (CI failures, review findings, verification gaps), not for open-
  ended research or scope growth.

## Setup authority

- A local disposable PostgreSQL via the standard `TEST_DATABASE_URL`
  harness (the same mode CI's E2E job uses with its service container) is
  authorized; no existing or production database.
- No provider credentials; no network egress beyond PyPI for the
  isolated environment; no release/deploy; no Dependabot interaction; no
  GitHub settings.

## OAP report requirements

Standard report fields per `OAP-COMMUNICATION-coding-agent.md`:
identifier, work-order file, numeric objective, PR mode, status,
executive summary, authoritative GitHub state (PR number, state, branch,
base, head, starting SHA, implementation head, `SELF` topology), changes
made, files changed, acceptance-criteria evidence (AP-1 through AP-7),
local verification, negative evidence (ruff pin unchanged; no test
deletions; `app/` diff state exact; no live calls), CI gate state on the
final head, and the merge-not-performed statement.
