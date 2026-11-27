# OAP Work Order — 229-e

Repair demonstrated final-CI failures in shared creation results and portable tests

Objective: 229-e
PR mode: AMEND_EXISTING_PR
PR: 403
Repository: ulfe-lmi/slaif-api-gateway
Branch: oap/229-key-creation-active-profiles
Base main: f1feec6bca0fd55f83d78c5badef2ab0b13ee304
Reviewed SELF: 7f4eec9c61004ccefaf1c62c9e53044117c6e356
Reviewed implementation: 4cc0b2d5fba2a0106031e6839a03cf50292a2438

## Actual blocking evidence, accepted scope and ownership

Root final-CI terminal95036 CLOSED exit1. Exact-head CI run46064198175 FAILED: unit/lint job140725539904 (2 failed,8943passed,1skipped), browser job140725539535 (11failed,134passed). PostgreSQL, E2E, Docker, documentation, both security workflows and CodeQL aggregate PASSED. Root fetched the actual failed job logs; this is not an observation timeout or a reason to retry blindly. Main is unchanged, PR403 is ready/unmerged/noauto. The material/form/active-profile review remains ACCEPTED; do not redesign it, repeat inventories or requalify clients. This same-PR continuation fixes specific CI blockers. Existing primary%9 only; secondary idle, no helper agents or prompt handoffs. Preserve untracked trio, earlier immutable reports/orders and neutral message.txt.

## Required narrowly scoped fixes

1. **Actual shared-template regression.** `tests/unit/test_admin_keys_routes.py::test_create_key_from_template_creates_one_key_result` POSTs the template-create path and now gets500: Jinja UndefinedError `'client_module_pins' is undefined`. The shared `keys/create_result.html` gained that optional explanation but other legitimate render callers do not supply it. Trace ALL callers of that shared result template and give it a consistent safe optional context/default; do not merely patch the test fixture or fabricate pin information. Native/client creation must still show correct pin facts, ordinary/template creation must render successfully, and no existing key/template metadata is changed. Add/retain a regression for the actual template POST and the other missing-context caller if present.

2. **Portable browser screenshot artifacts.** Nine failures in `tests/browser/test_admin_key_create_229b.py` try to write `/home/janezp/codex-work/slaif-229-task` on GitHub's `/home/runner` machine (PermissionError/FileNotFoundError). Replace the hardcoded runtime artifact path with an owned pytest temporary directory/fixture (0700) suitable for ANY checkout/user. An explicit test-only output override may be supported if actually useful, but the DEFAULT must need no setup, privileged permission, personal home or repository write. Route ALL screenshot calls (including direct full-page/element screenshots) through that owned fixture/location. Do not install/create /home/janezp on CI, chmod another user's home, skip screenshots/tests, or catch-and-ignore the failure. No new artifact framework. Existing private screenshots stay as review provenance; do not delete them.

3. **Date-dependent pre-existing fixture.** `tests/unit/test_cli_keys_effective_policy.py::test_policy_effective_json_shape` expects active/no status_note, but its hardcoded NOW=2026-10-28 plus30days expired on2026-11-27; actual code correctly reports expired. Fix only the ordinary TEST clock/fixture so it is deterministic or genuinely relative to the clock used for inspection. Prefer the existing injected now seam where available. Do not change production expiry/authorization, extend a fixed expiry to an arbitrary distant date, suppress expiry or modify frozen qualification evidence. Keep expired/future-key negative behavior covered.

4. **Existing lazy-throttling browser workflow after intentional layout/help changes.** Two failures in tests/browser/test_admin_lazy_throttling.py: old literal combined ceiling sentence no longer exists, and no-JS test expects waiting fields visible while their new native Advanced request-speed disclosure is closed. Update the tests to operate the actual new native disclosure (including no-JS), then verify real inputs, persisted wait policy, XSS-safe redisplay, disabled/enabled behavior and correction as before. Do not weaken waiting/ceiling/security assertions or force hidden controls with JS. Current per-field help DOES render configured max wait and queue ceilings; assert those actual numeric limits in the appropriate accessible help instead of restoring the old programmer-facing sentence or dropping the check. Keep ordinary no-JS creation working. If a genuine product regression is exposed after the test can reach the controls, fix it narrowly here.

## Verification, records and publication

Reproduce the failing unit nodes, then run their affected files (`test_admin_keys_routes.py`, `test_cli_keys_effective_policy.py`, focused creation/template/email regression as needed). Run the portable thirteen-test creation browser file AND existing lazy-throttling browser file against owned disposable PostgreSQL, actual Chromium and normal temporary artifacts. Use mocked providers/email, no real inference/mail or production DATABASE_URL. Verify created screenshots are inside the test-owned temp/output directory, not a personal home. Ruff/docs/whitespace/governance checks appropriate to changed files. Reuse already accepted active16/17 pins,13PG/readiness/transactional/other security/accounting evidence; do not repeat unchanged broad local suites. Broad CI reruns on the new final head as a required gate. Routine fixture/doc corrections remain in this order, not another early incomplete report.

Update SAME consolidated verification record and any operator note actually affected with the exact original CI failures, distinction between the shared-template product regression and fixture/portability adjustments, focused results/skips, reused successful evidence and remaining final-CI gate. No new verification framework or separate inventory. No schema, preset/DATA, migration, existing-key/permissions/quotas or request-runtime law changes. No release/deploy/230 activation.

Commit this exact root-authored order and oap/active=229-e unchanged; amend403 only. After complete execution publish ONE immutable `oap/reports/229-e-key-creation-ci-completion.md`, literal Implementation head SHA and Report publication commit: SELF, exact results/docs/limitations and code/assets restart/no schema or key migration conclusions. Report-only SELF sole parent=implementation and sole diff=report; push/verify unique remote403head/noauto BEFORE responseOK once; then one existing control waiter%9. Never reread/resignal229-a/b/c/d or repoll closed95036. Coding agent never merges/enablesauto. Root rechecks all final-head CI/review/material gates, guarded merge and actualmain.
