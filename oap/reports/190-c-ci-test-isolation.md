# OAP Objective 190-c — final report: bounded CI test isolation for file-backed Codex profiles

Work order: `oap/orders/190-c-ci-test-isolation.md` (committed
unchanged in this implementation commit; `oap/active` = `190-c`).
Branch: `oap/190-codex-connector-tool-names`.
PR mode: AMEND_EXISTING_PR — PR #328, base `main`
`86ae51c929b85ace6ef257239e4e900e7488754f` (verified unchanged at
publication); predecessor implementation
`3d5a694c74999249a892f62935dc40d3439fa524`, predecessor SELF
`aed19ec75e7bd98d65018067d650acbf4bc69f69`. The coding agent never
merges; no auto-merge is enabled; root reviews independently.

Implementation head SHA: 0375f0826e21b0d6db8eea2e1089e09b54bfb19c
Report publication commit: SELF

## What changed (TEST-ONLY)

CI run `39141210876` on the 190-b head failed exactly two unit cases
(4942 passed, 1 skipped); both were test assumptions broken by the
legitimate 190-b startup wiring, not product regressions:

- `tests/unit/test_branding.py::test_read_error_does_not_break_login_or_errors`
  — the test patched `branding.os.read` (the shared `os` module)
  **before** `create_app`, which unintentionally broke the required
  Codex profile startup read. Fix: the genuine app is now created
  successfully first (real profile bootstrap, no loader mock, no
  cache-away, no suppressed profile errors), and the synthetic
  `os.read` failure is injected only for the subsequent branding
  request reads. The real branding reader, fallback empty CSS,
  successful login, and 404 assertions are retained unchanged.
  Fail-closed startup remains fully intact.
- `tests/unit/test_main_app_structure.py::test_main_app_only_wires_app_and_routes`
  — the module assumed < 70 lines while the legitimate one-call
  Codex profile bootstrap plus its `app.state` binding yields 75.
  Fix: a documented modest ceiling (< 80) that explicitly accounts
  for that wiring; the router assertions and the prohibitions on
  business orchestration in the module are unchanged. No production
  restructuring was done to satisfy the cap.

Diff scope: exactly the two test files (11 insertions, 3 deletions)
plus the unchanged strategic order and exact `oap/active`. No other
file changed.

## Verification (this objective; JUnit-derived, focused, test-only)

Current run — `tests/unit/test_branding.py` (24),
`tests/unit/test_main_app_structure.py` (5),
`tests/unit/test_codex_profile_registry.py` (17),
`tests/unit/test_codex_profile_data.py` (16): **62/62 PASS, 0 failed,
0 skipped** in `/tmp/slaif-181c-strategic-venv`, no production or
ambient DB.

- `ruff check` on the changed Python: clean (CI lint gate
  `python -m ruff check app tests`; the branding file was already
  `ruff format`-nonconformant at the 190-b head, so no incidental
  reformatting was applied — the diff is minimized to the affected
  test).
- `git diff --check`: clean.
- Production immutability: `git diff` of `app/`, `pyproject.toml`, and
  `.env.example` against the 190-b implementation head
  `3d5a694c74999249a892f62935dc40d3439fa524` is **empty** — app
  production bytes and the default profile JSON are unchanged.

## Carried-forward evidence (historical, not reruns)

Explicitly labeled historical (190-b implementation head): the
480/480 focused unit pass, the 30/30 owned-PostgreSQL migration pass,
the 7/7 real-Gateway E2E pass (2 fresh-process file-backed + 5
adapted 0162 local-tools), the wheel packaging proof, and root's
installed-wheel file3→file4→file3, real CLI pin-migration, six
real-HTTP all-197-name requests, owned-PG exact-name replay/HMAC,
accounting 6 requests/30 tokens, full-row preservation, immutable
process-snapshot, and six canary CLI proofs. None were rerun for this
test-only fix, per the order; the final GitHub CI reruns its required
matrix normally.

## Current GitHub state at publication (reconciled before push)

- PR #328: OPEN, `MERGEABLE`, no auto-merge request; branch
  `oap/190-codex-connector-tool-names`.
- `main` unchanged at
  `86ae51c929b85ace6ef257239e4e900e7488754f`.
- Latest CI on the 190-b head: run `39141210876` completed with the
  two test-case unit-job failure this objective repairs; sibling check
  `39141210859` succeeded. Historical (190-a): run `39131525022`
  succeeded on the 190-a SELF head
  `1549384cbdabdbfadf94de349358017bb8f623cb` (2026-10-18 13:26:05Z);
  it is not evidence for the 190-b head. Any checks still pending at
  publication are pending, not passes; final-head CI on this commit
  runs normally after push.

## Limitations and safety confirmations

- Test-only: no production source, profile DATA, packaging, docs,
  dependency, schema, workflow, provider, auth, signing, replay, or
  accounting change. No deployment, production DB, SSH, real
  provider/model call, release/tag, or profile-download UI.
- No secret/environment dumps, no new diagnostics, no profile
  permission expansion, no identity-authority or provider-credential
  exposure. All 197 names remain fixture evidence, never a runtime
  inventory.
- Untracked local files (`CODEX-SESSIONS.md`, `codex.sh`) preserved
  and uncommitted; previous orders/reports byte-immutable; no
  merge/auto-merge performed; exact two-byte `OK` sent once to
  `response.fifo` only after this report's publication, then the sole
  control FIFO blocking waiter is attached.
