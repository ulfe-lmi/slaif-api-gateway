# OAP Report — 229-e (final): CI completion repair for PR #403 — execution complete

## Status

- Objective: 229-e (`oap/active` working-tree bytes `229-e`, sha256 `56f6595f2cff092144d5686dcd8443860414ebfe9724fb1d0a5e23ec5c5899a1`, committed byte-unchanged in this PR); order `oap/orders/229-e-key-creation-ci-completion.md` (sha256 `4bf224554e458183893f454b4c01f5412716465de6bf143c36d89ee4630df49e`), committed with the objective.
- PR: #403 (same PR; created by 229-a, amended by 229-b, 229-c, 229-d and 229-e), branch `oap/229-key-creation-active-profiles`, base `main` at `f1feec6bca0fd55f83d78c5badef2ab0b13ee304`; PR is open/ready, unmerged, no auto-merge; the coding agent never merges.
- RESULT: **PASS** — all four demonstrated final-CI blockers of the 229-d head are repaired (one real shared-template product regression; three fixture/portability/test-alignment issues in tests only) and re-proven below; the remaining delivery (final-head CI gates, root review, guarded merge, actual-main verification) is root-owned and pending.
- No production certification, release, tag, or security/compliance claim. No provider traffic, no real email, no production `DATABASE_URL` at any point.

## Identification

Implementation head SHA: 129bd9c51eaed7157cb46b7abd47fe0cfd5a1f9e

Report publication commit: SELF

- PR #403 head at publication: the implementation head `129bd9c5` (verified via GitHub before this report commit: head sha `129bd9c51eaed7157cb46b7abd47fe0cfd5a1f9e`, open).
- Canonical record: `docs/verification/2026-11-27-key-creation-active-profiles.md` (top status paragraph updated to the five-continuation 229-e current end state; new "229-e continuation" section; 229-a/229-b/229-c/229-d sections preserved as historical continuations).
- Unrelated untracked local files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) preserved; they are not part of this PR.

## Original blocking evidence (root-fetched exact-head CI)

CI run 46064198175 on the 229-d head (implementation `4cc0b2d5`, report SELF `7f4eec9c`) FAILED exactly two jobs: unit/lint job 140725539904 — **2 failed, 8943 passed, 1 skipped** — and browser job 140725539535 — **11 failed, 134 passed**. PostgreSQL, E2E, Docker, documentation, both security workflows, and the CodeQL aggregate PASSED. Main was unchanged; PR #403 ready/unmerged/no auto-merge.

## Implementation (one product regression; three test-only fixes)

1. **Shared create-result template regression (product code).** Template create POSTed `/admin/keys/create` with a template revision and got 500: Jinja `UndefinedError: 'client_module_pins' is undefined` — the shared `keys/create_result.html` gained the optional pin explanation in 229-b, but only the NATIVE create caller supplied the context. Fix (code + template only): the template defaults the variable to `{}` before first use, and the template-create caller passes `_safe_client_module_pins(...)` derived from the stored template snapshot's `responses_policy` (template creation never pins chat, so `None`). No key or template metadata changed; native creation still shows correct pin facts. Two new unit regressions: the result template renders WITHOUT any pin context (no fabricated pin facts) and shows the stored Responses pin (id, version, digest prefix, no chat row) when present.
2. **Portable browser screenshot artifacts (test portability).** Nine 229b browser failures wrote the personal path `/home/janezp/codex-work/slaif-229-task`, absent on the CI runner. Replaced with a session-scoped `artifact_dir` fixture: pytest temporary directory (0700) by default — no setup, no personal home, no privileged permission, no repository write — plus a test-only `SLAIF_229B_ARTIFACT_DIR` override for operator-owned local provenance. All ten screenshot call sites (helper and direct full-page/element) route through the fixture; no skips, no catch-and-ignore, no CI-side home creation. Existing private screenshots stay as review provenance.
3. **Date-dependent unit fixture (test clock).** `test_cli_keys_effective_policy.py::test_policy_effective_json_shape` used hardcoded `NOW = 2026-10-28`; its fixture key (`valid_until = NOW + 30 days`) genuinely expired on 2026-11-27 and the code correctly reported `expired`. Production expiry/authorization is correct and untouched. Fix: wall-clock relative test key (`datetime.now(UTC)`), valid from shortly before the run until 30 days after, against the same clock the inspection checks. Expired/future-key negative coverage stays in `test_key_policy_inspection.py` via the injected `now` seam.
4. **Lazy-throttling browser alignment (test fixture).** Two failures after the intentional 229-c layout/help changes: (a) the old literal combined ceiling sentence no longer exists — the tests now assert the ACTUAL per-field help ceilings rendered by 229-c ("the operator ceiling of 120 seconds", "the operator ceiling of 16"); (b) the lazy fields live in the new native "Request speed controls" `<details>` disclosure (closed by default) — both tests now open it by clicking its summary, a browser built-in, so the no-JS context works without any script. The full wait create → detail → update → back-to-reject flow, persisted wait policy, escaped invalid-bounds redisplay, and no-JS create still execute and assert exactly as before; no waiting/ceiling/security assertion weakened, no hidden control forced open with JS. No product regression was exposed once the tests reached the controls.

No schema change, no migration, no preset-file/DATA byte change, no existing-key migration, no key-material/permissions/quota change, no request-runtime law change, no new framework.

## Audit and documentation impact

Canonical verification record updated in place (top status paragraph: five continuations, 229-e current end state, 229-a/b/c/d historical; new "229-e continuation" section with exact original CI failures, product-vs-test distinction, focused results/skips, reused evidence, and the remaining final-CI gate). Operator notes: none affected — the product fix changes no operator-visible text or workflow beyond rendering the already-existing pin explanation for every legitimate create-result caller.

## Results (exact; mocked vs live)

Environment: owned disposable PostgreSQL (module fixture, self-tearing-down), repo venv, Playwright Chromium against local uvicorn on free loopback ports. Providers and email MOCKED; no real inference, no real mail, no production DB.

- `tests/unit/test_cli_keys_effective_policy.py` + `tests/unit/test_admin_keys_routes.py` — **56 passed** (30.01 s), including the previously failing template-create node and the relative-clock `test_policy_effective_json_shape`.
- `tests/unit/test_admin_key_create_templates.py` — **10 passed** (5.33 s) with the two new result-template regressions.
- `tests/browser/test_admin_key_create_229b.py` (13) + `tests/browser/test_admin_lazy_throttling.py` (3) — **16 passed** (45.26 s); all 10 creation screenshots verified inside the test-owned 0700 temporary artifacts directory, old owned task directory untouched.
- `ruff check` on all changed Python files — all checks passed; `git diff --check` — clean.
- Doc guards (`test_documentation_inventory`, `test_documentation_contract_drift`, `test_documentation_asof`) — **44 passed**.
- REUSED unchanged (not re-run): `test_admin_key_create_client_use_postgres.py` 13 passed (its "Responses client module" assertion already proves the native pin-facts display), the rev16/17 GUI pin and readiness evidence, the email sendability/retry integration coverage, and the security/accounting suites.
- Not run yet: the broad CI rerun on the new final head is the remaining required gate (root-owned); no full 128-worker harness; no live-provider qualification claim.

## Deployment and migration conclusions

- Fix 1 is code/template only; fixes 2–4 are test-file only. No schema, no migration, no preset-file or DATA byte change, no existing-key migration, no key-material or quota change.
- Rollback: revert the implementation commit; no state revert is required (no persisted format, pin, or policy change for existing keys).

## Claims not made

- No CI-green claim: the final-head workflow results on `129bd9c5` are root-owned and pending at publication.
- No claim that the previously passing jobs (PostgreSQL, E2E, Docker, documentation, security, CodeQL) re-verified this change locally; their CI re-run is part of the same pending gate.
- No operator-behavior change claim beyond the rendered shared result template; no email or provider-traffic claim.
- No next objective activated; 229 terminal (review/merge) remains root-owned.
