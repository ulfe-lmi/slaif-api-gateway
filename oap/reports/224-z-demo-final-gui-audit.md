# OAP 224-z — Final Report (final fake-admin GUI usability and route-coverage audit)

## Commit topology

- Activation commit: `9c8414e140ef02aa3d8e58c1f21b4005a6c1ebe5`
  (sole parent `aefd0340263deb83f0e5f254feff27de92b2d2b5`, the y
  SELF) — committed the root-authored z order and the exact
  `oap/active` = `224-z` pointer unchanged, FIRST.
- Immutable order:
  `oap/orders/224-z-demo-final-gui-audit.md`, SHA256
  `bbaabd7edea2824bfd5a1de9060bbc7d4899b7497da38986b4cdfbb54cfe821d`.
- Implementation head (sole SELF parent): `cc27c805`
  ("224-z: final GUI audit — truthful demo entry/orientation, the
  nav-hole repair, the 103-route finite GET inventory audit with
  focused units, owned-PG/Chromium truthful-entry proof, and the
  current-state docs matrix/runbook"; 15 files, +495/-49; tree
  `dd180e99bd78424407bad40d2f71fdb459155375`).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file. No merge; PR #383
  (`oap/224-demo-web`, base `main`) left open for strategic review.

## Prior objective state (224-y, terminal)

- y order SHA256
  `befad6d57dcfebe6a002c2f629ec3f401b12b8e7a4fc272ab6b66daf8e94bdcc`;
  y report SHA256
  `91e09db1b94fe6a9e35e1479890b3c3f2d75e124ec86ecf3640caadbaab3ac44`
  (immutable; untouched by this objective).
- y report-only SELF `aefd0340263deb83f0e5f254feff27de92b2d2b5` with
  all ten exact-head hosted checks SUCCESS (CI run `43593468842`,
  CodeQL `43593468820`, Code Quality `43593464675`) and all twelve
  recent review threads resolved; the y exact two-byte response `OK`
  was already delivered and was not repolled or re-signaled.

## Item 1 — truthful entry and orientation

Production changes (all demo-conditional or demo-only):

- `templates/demo/login.html`: exact title/heading "Demo Admin
  Login"; concise warning that signing in starts a FRESH per-session
  snapshot captured AFTER sign-in and available only once verified
  and anonymized, that the frozen view retains usage patterns, and
  that operational controls have no effect. The stale "Copy browsing
  is enabled in a later stage" line is removed.
- `templates/demo/ready.html`: primary link
  `<a class="primary-link" href="/admin">Open the admin dashboard
  (demo view)</a>`; truthful "frozen view of the source captured at
  sign-in (database and file captures carry their own recorded
  times)"; optional copy/files preview links; logout kept. The
  "not enabled yet" block is removed.
- `templates/demo/copy_preview.html`: the "Full GUI browsing is not
  enabled yet" note replaced by a truthful pointer to the full demo
  GUI from the ready page.
- `templates/demo/files_preview.html`: "in this stage" → "on this
  preview page".
- `templates/base.html` demo banner: "This is an incomplete core
  preview." removed; now "identity-masked snapshot data, frozen at
  capture time. Read-only - operational actions have no effect."
  Normal render is structurally unchanged (the whole banner is
  `{% if demo_admin %}`-scoped).
- `api/admin.py` `_DEMO_NAV_SECTIONS`: added
  `("/admin/operations/", "Operations")` (trailing slash REQUIRED by
  the gate law) and `("/admin/openai-assisted", "OpenAI")`. Normal
  nav data untouched.
- `demo_web.py` module docstring: distinguishes the 224-c history
  (no `/admin` routes) from the CURRENT mounted read GUI behind the
  central default-deny gate (224-e+). No historical immutable report
  was modified.

Zero-active-404, CSRF, bound login and secure-cookie laws are
unchanged (existing focused coverage).

## Item 2 — finite admin GET coverage audit

- The audit walked the ACTUAL mounted router at the final head
  (including FastAPI's lazy `_IncludedRouter` entries): **103**
  unique admin GET routes (98 admin + 5 branding assets). Root's
  99-row checkpoint TSV (94 admin + 5 branding) is a subset; the
  four additional mounted GETs are the demo-adapter
  `/admin/keys/{key_id}/calibration/summary.json` and
  `/admin/keys/{key_id}/configuration.json` attachment aliases plus
  the 224-l/224-m `/admin/operations/catalog/artifact` and
  `/admin/operations/catalog/jobs/` read pages. All four were
  already gate-admitted; the discrepancy is disclosed here rather
  than claimed as identical to the checkpoint.
- Every one of the 103 canonical routes is gate-admitted:
  sessionless GET → 303 to `/fakeadmin/login` (the five branding
  assets are static packaged files, served 200 without a session).
  Intentional exclusions: `/admin/login` (normal admin surface; the
  demo GET 303-redirects to the demo entry — the same wire shape)
  and the key-configuration JSON (admitted shape, but the demo
  handler is the fixed safe 503 because the 222 sanitizer strips
  key policy metadata; no verified sanitized projection exists yet
  and there is no source fallback).
- **The one real audit hole and its repair:** four templates
  (`dashboard.html`, `email_operations/smtp_test.html`,
  `email_operations/smtp_test_review.html`,
  `catalog_refresh/index.html`) linked `href="/admin/operations"`
  (no trailing slash), which the demo gate default-denies (404).
  All four now use
  `href="/admin/operations{% if demo_admin %}/{% endif %}"` — the
  demo render takes the gate-admitted trailing-slash form, the
  normal render is byte-identical to the original.
- The persistent demo nav was missing two CURRENT working major
  sections; Operations and OpenAI are now in the demo nav (with the
  gate-required slash on the operations index).
- The focused audit test
  `test_z_router_get_inventory_all_admitted_or_excluded` pins the
  full 103-route set (count + the four beyond-checkpoint literals),
  the admitted 303/200 law per canonical route, the `/admin/login`
  exclusion behavior, and near misses (no-slash operations,
  `/admin/branding`, query on a query-free family, bad run id,
  out-of-vocabulary artifact names, bad preset, non-UUID replay
  scope) staying 404. It re-walks the live router, so a newly
  mounted admin GET without a gate admission fails it.
- No gate admission change was required by the audit (the only
  demo-specific findings were the nav content and the four template
  link shapes); no route-catchall, source fallback or invented
  content was added.

## Item 3 — quiet actions and usable browsing

- The pre-body quiet 204 cut, the demo sign-out exception, and the
  visible no-op hints from 224-e..224-y are unchanged by this
  objective; the real-browser proof in the owned fixture re-ran them
  (cohort create, SMTP "Prepare reviewed test", OpenAI pricing
  propose: pre-body 204, row counts unchanged) as part of the
  rerun evidence below.
- No new action surface was added; no normal-admin behavior or
  rendering changed (see the byte oracle below).

## Item 4 — current documentation/operator path

- `docs/demo-admin.md` now opens with ONE current-state section
  ("SLAIF demo fake-admin — current state (objective 224 final
  audit, 224-z)"): a current-state route matrix
  (surface/family → demo outcome → provenance: verified copy /
  sanitized captured file / fixed packaged vocabulary /
  intentionally unavailable → reason/limit, built from the 103-route
  inventory) and the operator runbook (default-OFF standalone
  service, CLI-only fake-admin credentials, separate web +
  privileged worker + restrictive roles, private source/target
  DB/file custody, TLS/reverse-proxy boundary, snapshot wait and
  expiry/disposal, restart/configuration requirements,
  zero-active 404, privacy limitations — usage patterns retained,
  key-config export intentionally unavailable — and stop/cleanup).
  It states that Objective 225 installed acceptance remains pending
  on a separate PR after 224 merges and that nothing here is live
  company evidence, certification, or a release; no packaged
  Compose/demo-host automation is claimed.
- Every older stage section (220 through 224-y) is explicitly
  marked a HISTORICAL stage record, with the pointer at the top;
  none were copied or deleted.
- `docs/rc2-feature-scope.md` carries no demo feature-status line
  requiring a current-state correction, so it was not touched.
- Out-of-scope observation for root: `docs/configuration.md`
  (not in this order's allowed file set) still contains a
  stage-scoped "incomplete core preview" sentence in its 224-e
  settings paragraph; it was left unchanged here.
- `scripts/check_documentation.py`: OK (137 files).

## Verification evidence (local; hosted CI covers the full matrix)

- Focused 224-z units (`tests/unit/test_demo_web.py`): 5 new
  `test_z_` tests (login title/warning, copy-preview truthful
  pointer, the four template link shapes, rendered persistent-nav
  on an admitted page, the 103-route inventory audit) plus 2
  updated pre-existing tests (ready page now asserts the truthful
  admin-dashboard entry; the base-template demo-variant test asserts
  the fifteen demo nav entries and the new banner). All pass.
- Affected unit files: `tests/unit/test_demo_web.py` (301),
  `tests/unit/test_admin_slaif_design.py` (12),
  `tests/unit/test_admin_usability_inventory.py` (126) — 439
  collected, all passed.
- Normal-admin byte oracle (`/tmp/render_diff_224z.py`): activation
  `9c8414e1` originals vs worktree for `base.html`,
  `dashboard.html`, `email_operations/smtp_test.html`,
  `email_operations/smtp_test_review.html`,
  `catalog_refresh/index.html` — NORMAL renders (demo_admin=None)
  byte-identical for all five; DEMO renders differ only in the
  intended banner text and the trailing-slash Operations link (the
  dashboard body link is inside `{% if not demo_admin %}`, so its
  demo render shows no link change). PASS.
- Owned PostgreSQL 16 (containers `slaif222d-src-pg` 127.0.0.1:54351
  / `slaif222d-tgt-pg` 127.0.0.1:54352, role test/test, existing
  disposable data preserved), real worker per-login two-copy
  fixture: `tests/integration/test_demo_web_admin_gate_postgres.py`
  2/2 passed (real pytest exit 0 via `set -o pipefail` +
  `${PIPESTATUS[0]}`): the e2e asserts the new nav law on every
  admitted page (both copies), the truthful ready page, and the
  operations no-slash 404 / slash 200 law; the real-Chromium smoke
  asserts the 16-entry demo nav (Operations + OpenAI in place), the
  truthful banner, the ready page in-browser, the operations near
  miss, and re-proves the inert 204 submits and CSRF sign-out.
  Screenshot: `/tmp/slaif-224z-browser-ready-*.png`.
- `tests/integration/test_demo_web_postgres.py::test_e2e_web_entry_full_cycle`
  1/1 passed (real pytest exit 0): its stale ready assertion
  ("not enabled yet") was the ONE directly-affected assertion forced
  by the ready.html template change and was corrected in place
  (now asserts the `/admin` entry link and the absence of the stale
  claim). This file is outside the order's named test files; the
  change is a forced stale-assertion correction, disclosed here.
- Ruff: clean on all touched Python files. `py_compile` clean on
  the touched test files.
- Hosted CI for the z SELF head: NOT awaited by this report (root
  owns final-head reconciliation after the response, per the
  standing arrangement); prior y-head CI was terminal SUCCESS.

## Limitations and honesty notes

- All fixture evidence is SYNTHETIC (owned disposable PostgreSQL 16
  pair + owned source rows + test-only display leaves). No real
  installed/company apply, no real company/provider tests, no
  upstream provider call. Objective 225 owns the installed
  acceptance on a separate PR after 224 merges.
- The key-configuration JSON export remains intentionally
  unavailable (fixed safe 503, no link) until a separately verified
  sanitized policy projection exists; no faithful-configuration
  claim is made anywhere.
- The four beyond-checkpoint GET routes are disclosed (see Item 2);
  the 99-row checkpoint claim from the activation state is
  superseded by the runtime 103-route inventory for this report.
- No merge, no next objective, no helper agents, no control FIFO
  reads beyond the consumed activation OK.
