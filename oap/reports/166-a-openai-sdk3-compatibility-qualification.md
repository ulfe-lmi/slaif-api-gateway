# OAP Coding-Agent Report — 166-a

## Work order
- Identifier: 166-a
- Work-order file: `oap/orders/166-a-openai-sdk3-compatibility-qualification.md`
- Numeric objective: 166
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

OUTCOME=A

## Executive summary
Qualified the Gateway's declared official OpenAI-client compatibility
contract against OpenAI Python SDK `3.9.0` on current `main`. Q1 baseline
(repo venv, `openai==2.41.0`, disposable PostgreSQL 16 `slaif_gateway_test`):
`python -m pytest tests/e2e -q` → **54 passed, 0 failed, 0 skipped**. Q2 built
an isolated single-variable candidate venv (Python 3.12.3, every transitive
dependency constrained to the baseline `pip freeze`, then
`openai==3.9.0` forced): the only delta is `openai 2.41.0 -> 3.9.0`,
`jiter 0.15.0 -> 0.17.0`, and the new packages `httpx2==2.13.0`,
`httpcore2==2.13.0`, `truststore==0.10.4` — OpenAI SDK 3.x ships its own HTTP
stack instead of `httpx`. Q3 candidate matrix: **11 passed, 43 failed**, all
43 with the single mechanism `RESPX: some routes were not called!` on the
harness pass-through route at `respx.mock(__exit__)`, after the full
request/response cycle had already succeeded (mocked upstream called, 200
returned, SDK response parsed). A disposable transparent TCP capture harness
(not committed) recorded the exact SDK-issued request for one representative
test per surface under both SDK versions: method/path/body byte-identical
modulo per-run random values (multipart boundary, temp filename);
case-insensitive header sets identical; value differences limited to
`user-agent`/`x-stainless-package-version` version stamps and per-run
Host/token/boundary values. **No new header, field, or body shape** — the
gateway wire contract is preserved. Root cause F1 (class (a), SDK
API/harness change): SDK 3.x performs the SDK-to-gateway leg over
`httpx2`/`httpcore2`, which respx 0.23.1 does not intercept, so the
pass-through route is never observed and `assert_all_called=True` fails as
pure mock bookkeeping; the 11 pre-adaptation passes are exactly the 11
negative-path tests that already used `assert_all_called=False`, and the 43
failures are exactly the 43 `assert_all_called=True` blocks (1:1 by AST
audit). Remedy (tests/e2e only): all 43 blocks flipped to
`assert_all_called=False`; the pass-through route is retained (still required
for `assert_all_mocked=True` under the 2.x transport); every test's explicit
upstream-route `.calls` assertions are unchanged (AST audit: all 43 tests
reference `.calls` after their respx block, so no test lost its
upstream-was-called guarantee). Post-adaptation candidate matrix: **54 passed,
0 failed, 0 skipped**. Zero (b), (c), (d), (e) families: no wire-shape drift,
no declared-contract violation, no product decision, no gateway defect; `app/`
diff is empty. Dev pin set to exactly `openai==3.9.0` (single
`pyproject.toml` line), `docs/openai-compatibility.md` gained the
qualified-version statement, and the dated record
`docs/verification/2026-09-17-openai-sdk3-qualification.md` (with the full
54-row matrix, wire evidence, and classifications) plus one
`docs/verification/README.md` index row were added. CI on the final head ran
the 54-test matrix under 3.9.0 with zero failures, and all nine required
checks are SUCCESS.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 303
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/303
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/166-openai-sdk3-compatibility-qualification`
- Starting remote SHA: `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb`
- Implementation head SHA: fd0f5f516179726f0e9960dc2d9e62260fcec5e5
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
    - `87c1393d1496590dac8f3e9d861734d5a41b62e4` `obj166: qualify OpenAI Python SDK 3.9.0 official-client compatibility`
  - `fd0f5f516179726f0e9960dc2d9e62260fcec5e5` `oap: activate 166-a openai sdk3 compatibility qualification` (carries the strategic-authored order and `oap/active` unchanged)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `pyproject.toml`: exactly one line in `[project.optional-dependencies] dev`:
  `"openai==2.41.0"` → `"openai==3.9.0"`. No other dependency, workflow, or
  tooling line touched; ruff remains pinned `0.15.16`.
- `tests/e2e/test_openai_python_client_{audio,chat,embeddings,realtime,responses,streaming}.py`,
  `tests/e2e/test_openrouter_python_client_{chat,streaming}.py`: in 43 respx
  blocks, `assert_all_mocked=True, assert_all_called=True` (or the
  `assert_all_called=True` default-form equivalent) →
  `assert_all_called=False`; pass-through routes, upstream mock routes,
  request/response fixtures, and all assertions unchanged. 43 lines changed,
  43 lines added; no `def test_` line removed; no skip/xfail introduced.
- `docs/openai-compatibility.md`: added the qualified-version statement
  (54-test official-client E2E matrix qualified under the dev/test pin
  `openai==3.9.0`, per the dated record; mocked-upstream evidence, not a
  real-provider run).
- `docs/verification/2026-09-17-openai-sdk3-qualification.md` (new): dated
  qualification record — evidence boundary (base `main`
  `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` and the Objective 166 PR head,
  identified as the implementation-head commit containing the record / first
  parent of this report's `SELF` commit), environment versions and
  `pip freeze` lines, Q1/Q3 matrix results, root-cause family F1 with wire
  evidence and (a) classification, the 54-row compatibility matrix, OUTCOME=A,
  local verification, and honest limitations.
- `docs/verification/README.md`: one appended index row for the new record.
- `oap/orders/166-a-openai-sdk3-compatibility-qualification.md`,
  `oap/active`: committed and pushed with the objective implementation,
  strategic bytes unchanged.

## Files changed
- `pyproject.toml`
- `tests/e2e/test_openai_python_client_audio.py`
- `tests/e2e/test_openai_python_client_chat.py`
- `tests/e2e/test_openai_python_client_embeddings.py`
- `tests/e2e/test_openai_python_client_realtime.py`
- `tests/e2e/test_openai_python_client_responses.py`
- `tests/e2e/test_openai_python_client_streaming.py`
- `tests/e2e/test_openrouter_python_client_chat.py`
- `tests/e2e/test_openrouter_python_client_streaming.py`
- `docs/openai-compatibility.md`
- `docs/verification/2026-09-17-openai-sdk3-qualification.md` (new)
- `docs/verification/README.md`
- `oap/orders/166-a-openai-sdk3-compatibility-qualification.md` (new, unchanged strategic bytes)
- `oap/active` (strategic update 165-a → 166-a, unchanged strategic bytes)
- `oap/reports/166-a-openai-sdk3-compatibility-qualification.md` (this report, report-only final commit)

## Acceptance-criteria evidence
### AP-1 — all nine required CI checks SUCCESS on the final head
- Result: pass
- Evidence: for implementation head `fd0f5f516179726f0e9960dc2d9e62260fcec5e5`,
  `gh pr checks 303`: `Unit, lint, and migration head` pass (2m23s);
  `Documentation hygiene` pass (7s); `OpenAI-compatible E2E tests` pass
  (1m38s); `Playwright browser smoke` pass (1m11s); `Docker Compose smoke`
  pass (1m3s); `PostgreSQL integration tests` pass (2m40s);
  `Analyze (javascript-typescript)` pass (43s); `Analyze (python)` pass
  (2m13s); `Analyze Python` (CodeQL) pass (1m13s). No pending/failed/cancelled
  required check.

### AP-2 — E2E job ran the 54-test matrix under the final pin, zero failures, installed-version line cited
- Result: pass
- Evidence: CI job 105108073279 log: `Successfully installed ... openai-3.9.0
  ...` (install step) and `54 passed, 54 warnings in 49.11s` (Run E2E tests
  step). Matches final pin `openai==3.9.0`.

### AP-3 — exact pin + verbatim outcome
- Result: pass
- Evidence: `pyproject.toml` dev extras now contain exactly
  `openai==3.9.0` (diff touches exactly that one line); this report states
  `OUTCOME=A` verbatim, and the dated record states it in its `## Outcome`
  section.

### AP-4 — full 54-row matrix, wire evidence, classifications, consistent counts
- Result: pass
- Evidence: `docs/verification/2026-09-17-openai-sdk3-qualification.md`
  contains the 54-row matrix (grouped by surface: audio
  speech/transcription/translation 3; chat multimodal/file/audio forms 5; chat
  non-streaming 2; chat streaming 7; Codex bounded responses slice 4;
  conversations and conversation items 2; embeddings 1; error/auth/omission
  coverage 8; local function/custom tools 2; OpenRouter chat/streaming 2;
  realtime client-secret 1; responses non-streaming 7; responses typed
  streaming 3; responses web_search 1; stored-response lifecycle / input
  tokens / compact 6 — 54 total), each row with baseline 2.41.0 result, candidate 3.9.0
  pre-adaptation result, family ID, and disposition; family F1 (43 tests)
  carries the exact wire capture evidence (method/path/headers/body comparison
  under both SDKs) and its (a) classification. Counts: 54 = 11 unchanged +
  43 F1; 43 harness blocks adapted; 0 gateway fixes; 0 deferred surfaces.

### AP-5 — dated record, index, compatibility-doc statement
- Result: pass
- Evidence: `docs/verification/2026-09-17-openai-sdk3-qualification.md`
  exists with the named evidence boundary; `docs/verification/README.md` has
  the appended index row; `docs/openai-compatibility.md` states the qualified
  SDK version (`openai==3.9.0`) matching the final pin.

### AP-6 — no deletions/loosening; no accounting or boundary changes
- Result: pass
- Evidence: `tests/e2e/` diff is exactly 43 `assert_all_called=True` →
  `False` line pairs (verified by diffing changed lines: 43 removed / 43
  added, no other content); no `def test_` line removed; no skip/xfail;
  `app/` diff empty; no migration, schema, or accounting change; no
  workflow/deployment/release/branch-protection change; no test added for an
  unsupported surface.

### AP-7 — immutable report topology
- Result: in progress by construction
- Evidence: this report is published by atomic rename into
  `oap/reports/`; the following report-only commit changes only
  `oap/reports/166-a-openai-sdk3-compatibility-qualification.md`, has
  `fd0f5f516179726f0e9960dc2d9e62260fcec5e5` as first parent, and is pushed
  and verified as the remote PR head before `OK` is sent.

## Local verification
- Baseline `python -m pytest tests/e2e -q` (repo venv, `openai==2.41.0`,
  disposable `TEST_DATABASE_URL=postgresql+asyncpg://slaif:slaif@127.0.0.1:5432/slaif_gateway_test`,
  fresh DB): PASSED — 54 passed, 0 failed, 0 skipped.
- Candidate `python -m pytest tests/e2e -q` (isolated venv,
  `openai==3.9.0` forced, fresh DB): pre-adaptation 11 passed / 43 failed
  (single mechanism F1, per-failure wire capture taken); post-adaptation
  PASSED — 54 passed, 0 failed, 0 skipped.
- Final `python -m pytest tests/e2e -q` (candidate venv reinstalled from the
  updated pin without constraints — pin-driven `openai==3.9.0`, fresh DB,
  final PR-head code): PASSED — 54 passed, 0 failed, 0 skipped.
- Old-pin harness compatibility `python -m pytest tests/e2e -q` (repo venv
  `openai==2.41.0`, fresh DB, final PR-head code): PASSED — 54 passed,
  0 failed, 0 skipped.
- `python -m pytest tests/unit -q` (repo venv, final PR-head code): 4043
  passed, 1 failed, 0 skipped (4044 collected). The single failure is the
  known environment-only
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (`VerificationError: codex_version_mismatch`, VM codex CLI
  `codex-cli 0.154.0` vs fixture pin `codex-cli 0.148.0`); reproduced
  identically on base commit `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` in a
  read-only detached worktree (`git worktree add --detach`, single test,
  worktree clean, then removed) — environment-only, not diff-caused.
- `python -m ruff check app tests`: PASSED — `All checks passed!`
  (ruff 0.15.16, pin unchanged).
- `alembic heads`: PASSED — single head
  `0024_quota_reservation_accounting_facts (head)`.
- `python scripts/check_documentation.py`: PASSED —
  `DOCUMENTATION_CHECK=OK files=80`.
- `git diff --check`: PASSED — clean (no output, exit 0).

## GitHub CI / required checks
- Check state observed for implementation head
  `fd0f5f516179726f0e9960dc2d9e62260fcec5e5`: all SUCCESS (see AP-1).
- All required checks green for the implementation head at report drafting: yes
- Report-only commit may trigger fresh checks: strategic model must verify
  the `SELF` commit without rewriting this report

## Local setup / dependencies
- Packages/tools/services installed or configured: isolated candidate venv
  `/tmp/obj166-cand-venv3` (Python 3.12.3, disposable, outside the
  repository) for Q2/Q3/Q7; disposable capture harness
  `/tmp/obj166-capture/` (outside the repository, not committed).
- `sudo`-level setup performed: passwordless `sudo -u postgres dropdb/createdb`
  for the disposable `slaif_gateway_test` database only (dropped and
  recreated before each full matrix run; name contains the `test` safe
  marker; never pointed at `DATABASE_URL`; no other database touched).
- Durable setup changes committed/documented: none beyond the files listed.

## Documentation
- Documentation impact statement: `docs/openai-compatibility.md` now states
  the qualified official-client SDK version (`openai==3.9.0`) with a pointer
  to the new dated record; `docs/verification/README.md` gained one index row;
  the new dated record `docs/verification/2026-09-17-openai-sdk3-qualification.md`
  is a dated evidence archive entry (exempt from current-state as-of rules)
  documenting the qualification, its evidence boundary, and its limitations.
  No existing dated verification file, `docs/beta-readiness.md` body, or other
  contract document was edited. `scripts/check_documentation.py` passes
  (`DOCUMENTATION_CHECK=OK files=80`) on the final code.

## Safety and scope confirmations
- Unrelated files changed: no — diff limited to the order's allowed paths.
- Production secrets accessed: no — fake per-test gateway keys and fake
  upstream keys only, as in the existing harness.
- Production systems accessed: no — disposable local PostgreSQL
  (`slaif_gateway_test`), mocked upstreams, no Docker daemon needed.
- Required tests skipped/not run: no — full E2E matrix (54), full unit suite
  (4044 collected), ruff, alembic heads, documentation check all run; the
  single unit failure is the proven environment-only codex-CLI version
  mismatch, documented above.
- Scope deviation: no — no ruff/other dependency change, no Dependabot
  interaction (#250/#224 untouched), no workflow/migration/release/
  branch-protection change, no live provider calls, `RUN_UPSTREAM_TESTS`
  unset throughout.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO
- Report-publication commit changes only this report file: yes (verified via
  staged diff before commit)

## Known limitations / blockers
- Mocked-upstream qualification only: not a real-provider run; proves nothing
  about live OpenAI/OpenRouter wire behavior under SDK 3.9.0. Not a release,
  production certification, security review, compliance finding, or SLA
  approval.
- The SDK 3.x `httpx2`/`httpcore2` transport is outside respx 0.23.1's
  interception boundary in this harness; the SDK-to-gateway leg is covered by
  the gateway's own accepted-request behavior, the explicit upstream-wire
  assertions in every test, and the disposable capture harness used for this
  record. A respx/httpx2-aware interception layer could restore direct
  observation of that leg; that is a harness enhancement, not a contract
  question.
- Environment-only unit failure (VM codex CLI version vs fixture pin) remains
  on this execution VM; it is unrelated to this objective and reproduces on
  the base commit.

## Recommended strategic follow-up
Optional: if the strategic model wants direct respx-level observation of the
SDK 3.x transport leg restored, a bounded follow-up objective could adopt a
respx/httpx2-aware interception or add gateway-side request-count
assertions; no contract question is open from this objective.
