# OAP Work Order — 219-b

PR mode: CONTINUE_EXISTING_PR

## Objective, authority, and current state

Finish the APPROVED whole207–219 GUI mandate on the SAME PR376. Root found
demonstrated post-handoff security, completeness, guidance and CI defects in219-a.
This continuation repairs those defects; it is not a new phase or an invitation
to defer work to220+. The complete219-a order remains the acceptance contract
except where this continuation corrects its current state and verification plan.
The previous self-imposed product freeze was a measurement boundary, not a rule
preventing these authorized fixes. Make the bounded product changes, stabilize
them, then qualify the actual final installed code.

Verified root state on2026-11-11:

- PR376 is OPEN/ready/MERGEABLE, base main, branch
  `oap/219-gui-completion-gate`, exact SELF
  66be09592a75a89a5912e035eb3e149d61bb2a3c. Sole parent/implementation head
  00737d176c9e13efee5d6e01f0062f7f0781175c; SELF differs ONLY by the report.
  Earlier product commit45893daa4b7d665a3b9a306cdd56851a426ad7b1 follows activation
  commit07396b0d65d886b3ad042b52efa2740ce67dc63f. Append; no amend/force/rebase.
- Actual remote main remains663c673494d4c0daeb4d5b1269b428ee13277448, accepted
  predecessor218 terminal, all9checks/3workflows SUCCESS before219 activation.
- Immutable219-a order29183bytes SHA256
  78cf72bed89e783fe068c002928cf08eac70ecbba12d09530c52dd4364d5d4e7;
  report12802bytes 27d279601d15769d016970f6acba035b70cd20963c61b87c076bbdd40ef1eeba.
  Active was219-a exact5bytes. Preserve that order/report/history, including the
  report's mistakes; correct claims in CURRENT docs/PR and your NEW report.
- Root consumed sole response terminal66648: exact RESPONSE_OK_EXACT, exit0.
  It is CLOSED forever, as are29941/70483/78268/64194. Never repoll or resignal
  219-a/218-a/b. No root CI watch is retained for the blocked219-a head.
- Final-SELF CI42996987860: unit job130443552589 FAILED (5 failed,7259 passed,
  1 skipped); browser job130443552640 FAILED (1 failed,130 passed). Exact causes
  and required bounded repairs below. PostgreSQL still running at review;
  E2E/Compose/docs and both CodeQL workflows passed. Refresh remaining old-head
  results without treating them as final-B passes.
- One quality thread was reviewed/resolved by root: BaseException in the
  browser fixture is the existing cross-thread bridge that rethrows to caller.
  Do not add cleanup solely for that advisory.
- Root material review: https://github.com/ulfe-lmi/slaif-api-gateway/pull/376#issuecomment-6792660202.
  It does NOT accept the whole task; it accepts only the scoped evidence below.
- Same existing coding CLI PID3308462/right pane%9/early-beta/Qwen3.8-27B A100Q8
  medium. No helpers, subagents, nested Codex, new coding process, profile/model/
  effort changes. Native same-CLI context maintenance is allowed when needed;
  reload active/order and preserve the whole mandate through compaction.
- ONE canonical control waiter PID1421693, cwd
  /home/janezp/codex-supervision/slaif-api-gateway, TMUX_PANE=%9. Canonical FIFOs
  there: control.fifo inode4501469 and response.fifo inode4501470, actual FIFOs.
  Shared repository: /home/janezp/codex-work/slaif-api-gateway. Root publishes
  this order plus219-b before ONE control OK; root alone owns the new response
  reader. A consumed control wake requires execution, not another FIFO read.
- Unrelated PR319 Dependabot and PR374 Codex namespace remain untouched. Main
  protection/no-bypass and release boundaries unchanged. No release/tag/deploy,
  production/provider credentials, real provider inference, or real mail.

## 1. Repair the new calibration JSON boundary

Root reproduced200 plus complete known incoming cookie alias in the JSON by
placing that alias in owner_display_name of a valid typed summary. This was a
preauthorized fake summary plus REAL ASGI route, no DB/network/browser; it is
handler-boundary proof, not a deployed/backend exploit claim. The actual summary
service copies owner names into its typed projection, so the projection alone
does not establish secret exclusion. The response also lacks nosniff, and the
new route has no explicit export byte ceiling. The existing tests do not test
alias refusal despite the report's claim.

- Reuse existing pure request-aware secret classification/redaction primitives
  to refuse a summary/proposal export containing known incoming authentication
  aliases or recognized complete credential material. No new redaction framework
  or server credential introspection. Preserve legitimate public IDs, ordinary
  owner names and exact protocol values; refuse the complete artifact with a
  fixed useful safe error rather than silently deleting fields or changing the
  CLI-compatible machine projection. Check nested canonical strings, not only
  query parameters or selected fields. Do not echo the refused value in errors,
  logs or filenames.
- Add a documented finite attachment ceiling (a local1MiB output ceiling is
  sufficient unless an existing applicable bound is reused). Refuse oversize
  output explicitly and advise narrowing the time scope; never truncate and
  label it complete, or change Core aggregation/accounting to fit the export.
- Set private no-store/no-cache and X-Content-Type-Options:nosniff for this
  route's success/refusal responses. Preserve same trusted-key/time/multiplier
  validation, exact Decimal/UUID/datetime serialization and raw units.
- Preserve the existing NON-ROTATING read-only attachment session context and
  successful download then same-page confirmed template creation. Do not add
  writes, a signing/custody/job platform, settings, schema or inference.
- Add focused complete-body/log canaries for cookie/bearer aliases represented
  in nested summary text, credential shapes, valid public IDs, safe ordinary
  text, bounds, failure headers and no token rotation. Reuse unchanged service/
  CLI tests; do not claim fake-ASGI coverage as native DB proof.

## 2. Finish the specified guidance and interaction requirements

Root's isolated REAL Chromium probe with the actual _record_choice macro and JS
shows the enhanced menu's visible .rc-search has no aria-describedby while the
main input does. The new static inventory and browser helper pass because they
check source presence or whether SOME control references each help ID. Close
the actual visible-control gap in the SAME shared macro/JS. No second picker,
automatic help overlay, new endpoint/taxonomy or dependency.

- Associate meaningful help with every actual visible enhanced input, including
  menu search, and with its no-JS counterpart. Preserve existing selectors,
  caller field names, hidden serialization, selected values/older-label hydration,
  dependencies, multi-chip behavior and lookup authorization/bounds.
- Strengthen the existing inventory/render audit and browser helper to verify
  ACTUAL visible entry controls, including unnamed enhanced inputs, unique and
  resolving meaningful descriptions, conditional/error/no-JS states. Do not
  equate111 selector fields with all fields or assert only that some help exists.
  Use the SAME existing inventory module; no second inventory/catalog/framework.
- Create policy source: disclose/hide the complete document label/editor/help
  together; compact inactive guided groups in document mode. Current code only
  hides the textarea and leaves its label/help and long guided panels visible.
  Preserve no-JS usability, existing choices and strict single-source submission.
- Key detail: expose the advanced policy choice/section before the long guided
  policy groups using its existing separate forms/contracts. Do not redesign
  the policy engine or invent an unhandled form field.
- Explain-model: use the EXISTING searchable known-model picker with latest100
  plus older search, retaining manual unknown-model entry. The current datalist
  is not that integrated older-search behavior. Preserve unknown-model results
  and configuration-only/no-inference semantics.
- Clone validity: coherent duration and absolute-time mode groups; no orphaned
  end-date control under the current arbitrary grid. Preserve exact seconds,
  UTC, all three modes, server validation, keyboard and no-JS behavior.
- Compatibility readiness: replace unexplained None artifacts with fixed useful
  setup/readiness direction, including invalid PUBLIC_BASE_URL. Preserve the
  canonical verified-HTTPS/numeric-loopback rules; no arbitrary exception echo,
  new URL validator, configuration writer or destination relaxation.
- Route media-estimation help: explain per-typed-part admission/reservation
  allowances versus final usage, current token bounds1..1050000 and video-frame
  bounds1..32, and their actual purpose. Routing-priority guidance already added
  is valid; preserve lower-first and0-valid semantics.
- Finish concise plain account guidance as approved; keep exact nonempty/128
  GUI password bounds, all session/role consequences and confirmations. Twelve
  characters is advice, not a new minimum. Remove technical schema/row prose
  from ordinary touched hints where it does not help the operator's decision.
- Preserve the completed batch membership disclosure and existing105+/1000-key
  scope law. Preserve sorting hyperlinks/neutral markers/ordinals/typed raw
  values, separate request/token columns, exact zero/comma/M-token formatting,
  local branding, focus/contrast, downward-growing chips, pagination and all
  submitted values. Root compared static field-name/form-action counters across
  the44 changed templates: unchanged. That is useful preservation evidence,
  not a replacement for rendered or business-outcome proof.

## 3. Finish the installed workflow's missing outcomes and oracles

Reuse and extend tests/integration/test_gui_parity_installed_workflow.py and its
existing owned fixtures. Do not build another runner or duplicate already-good
component evidence. Accepted17-test installed receipt is PARTIAL relative to
the full order; a green named test is not evidence of the outcomes it omits.

Concrete corrections required by the ORIGINAL219 scope:

- G01: replace final unrestricted assertion `in (None, [])` with the exact
  canonical unrestricted state. None and[] are deliberately different. Verify
  create/update/export preserve unrestricted, list and deny-all, without a
  truthiness shortcut or weaker production acceptance.
- G06: perform an actual reviewed partial capability LEAF change, then assert
  untouched deep siblings on THAT SAME route are retained. Changing priority
  and comparing a different route does not establish this requirement.
- G07: actually create/prepare or update provider state, clear existing notes,
  and explicitly activate the prepared provider/route using existing GUI
  operations. Current GETs of seeded provider pages do not qualify mutations.
  Assert persisted values/audits and separation of preparation from activation.
- G10: keep actual upgrade/rollback. For data-profile migration assert the EXACT
  expected active snapshot identity, not just inequality from the old pin.
  Exercise the existing credential-free route profile/config/catalog artifacts
  with a valid configured public gateway URL; preserve exact identity and
  no-key/nonrotating download law. Do not change compatibility modules or use
  unrelated PR374. Readiness help gets a focused invalid-URL case.
- G11: actually exercise grouped usage, live-burn report and safe JSON report
  export with exact scope/known-missing/provenance outcomes. The legacy usage
  CSV and list pagination are valid retained evidence but not those surfaces.
  Preserve G13 complete filter paging/sort/ordinal behavior and G18 actual
  pricing-disable/effective-FX outcomes; assert honest unavailable FX wording,
  not merely HTTP200.
- Representative LEGACY outcomes remain mandatory in this final stage: existing
  owner/record and standard-key creation; suspend/activate plus rotation with
  correct one-time destination and old material invalidation; validity and hard
  quota edits without usage reset; lazy-waiting/external-tool configuration;
  provider discovery/import review/application against the synthetic provider;
  template issue from the calibration-created revision; GUI audit inspection,
  existing safe export; login/logout and credential-free download then usable
  still-displayed form. Use a few coherent scenarios, not every historical
  matrix. All are existing operations; no new feature/permission is implied.
- Preserve successful unchanged clone/batch/replay/diagnostics/email/accounting/
  catalog/account/calibration outcomes. G14's fence family is correctly read-only:
  inspect its authoritative state, never invent a fence apply or forgive an
  unknown cost. Preserve exact actor/session/replay ownership and audit oracles.
- Make the negative-matrix description match actual evidence. Current test16
  does anonymous/wrong-CSRF/tampered-batch/recovery plus selected body sweeps;
  it does NOT itself prove wrong actor/session, expired/stale review or all logs/
  audit claims. Reuse accepted unchanged component proofs explicitly for those
  cases, and add focused final changed-integration cases where necessary. Do
  not count a random400/redirect or refused ordinary path as happy-path delivery.
- Check complete response bodies and captured ordinary app/worker logs/audit
  metadata for the known synthetic secrets/passwords/provider values/hashes/
  session aliases relevant to the final changed surfaces. Public key names are
  not bearer secrets; intentional one-time key display and session Set-Cookie
  remain functional exceptions. No real credentials or private contents.

## 4. Repair demonstrated CI consumers without weakening them

Old-head unit CI failed exactly these5 cases:

- tests/unit/test_admin_key_actions_templates.py:
  test_key_detail_renders_lazy_throttling_wait_values_and_usable_inputs;
  test_key_detail_renders_lazy_throttling_reject_defaults_and_inactive_warning.
- tests/unit/test_admin_key_create_templates.py:
  test_create_form_renders_lazy_throttling_defaults_ceilings_and_inactive_note;
  test_create_form_lazy_defaults_fit_lowered_operator_ceilings.
- tests/unit/test_admin_table_rows_194.py:
  test_keys_list_rows_selector_binds_to_filter_form.

These include brittle complete-tag/attribute-order strings changed by adding
aria-describedby and expected operator-ceiling copy. Adapt assertions to the
actual DOM/state/association and preserve all checked-mode, usable-field,
ceiling, bound-form, refusal and no-JS guarantees. Do not remove help, reorder
attributes solely to appease a string, skip a test or change Core behavior.

The changed help also hardcodes default30s/2 while creation's defaults fit lower
deployment ceilings. Explain actual rendered defaults/ceilings faithfully; do
not change the runtime defaults to match copy. Old-head browser failure is
tests/browser/test_admin_lazy_throttling.py::test_admin_lazy_throttling_wait_create_update_and_reject
(expected operator-ceiling sentence). Requalify this ONE affected consumer on
owned services, preserving its real create/update/reject outcomes. Inspect any
new old-head failure specifically before broadening this bounded repair.

## Allowed files, preservation, and setup

Original219-a allowed product paths apply ONLY to the above remaining guidance/
interaction/export fixes: api/admin.py; existing shared record-choice/policy JS
and macro; relevant templates (including compatibility and account forms); CSS
only a necessary bounded responsive/grouping fix. No mutation engines, schema,
adapters, runtime permissions, quota/accounting/replay or dependency changes.

Tests: the existing219 unit/browser/installed modules and SAME usability
inventory/design modules; the three named existing CI unit modules and ONE
named lazy browser consumer; existing test-only catalog worker driver only a
directly necessary installed-identity/fixture correction. No new test platform.
Do not add product endpoints for test identity or fabricate resulting state.

Docs: current MISSING_GUI_FUNCTIONALITY.md, admin-usability.md,
verification/gui-cli-parity.md, configuration/deployment/runbook/security/README
where actual final behavior affects claims. Preserve README logo, dated history
and all immutable orders/reports. Root-authored this order/active byte-unchanged;
one unique new immutable219-b report. No220 activation or invented roadmap.

Keep existing qualified /tmp/slaif216-qualification-venv. Same owned PG16/Redis7,
synthetic provider/SMTP, wheel/venv tooling; no reinstall/new infrastructure.
Use the existing unique owner-label/full-container-ID/loopback/tmpfs identity
checks and exact cleanup. Never ambient databases/Redis, broad process/container
cleanup, unowned resources, real provider inference or mail. If the older browser
consumer reads a DB URL at collection, reuse the qualified owned-driver pattern
rather than supplying an ambient URL or creating another fixture framework.

Protected untracked files BY HASH ONLY, never content-read/staged/modified:
CODEX-SESSIONS.md7881bytes SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda;
codex.sh492bytes 66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247;
uv.lock405520bytes d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6.
Preserve ignored.env/.codex, local catalogs and unowned worktrees/processes.

## Verification economy and provenance

Root verified219-a receipts: unit240/0/0 start08:59:50.469615Z SHA256
32979fcf674ef49fc5875cc88dfced4bfcdada52637a792fa91e282be72978b3;
browser5/0/0 start08:05:48.841807Z 0533bd443bbb1e35c91ffd2e3a0b5f3df30d1492c9d5fb609f184a9a92722bf3;
installed17/0/0 start09:31:18.564329Z,41.393s,
0b5d796b31848ee99cc67bed9311a690845fb832302043b21b10ef2eb134d347.
Their .rc files contain actual PYTEST_EXIT=0. Preserve and cite accepted unchanged
component evidence207–218 and good219-a outcomes at their exact scope. Do not
repeat unchanged backend service/CLI matrices, inventories or debug attempts
solely for a new filename. Root's two probes above are separately qualified
ASGI-fake/isolated-Chromium checks, not extra pytest/native passes.

After changes, run focused affected components: new219 unit/render tests,
existing strict inventory/design/OAP, the3 named CI unit modules; real-browser
219 changed guidance/conditional cases and the ONE affected lazy consumer.
Run docs checks only for final touched docs and scoped Ruff for ALL changed
Python, not just newly created test files. Capture direct pytest exit before
display and keep bounded log/JUnit receipts. No full local historical matrix.

Then run ONE complete installed workflow after final product code stabilizes:

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  RUN_GUI_PARITY_INSTALLED_WORKFLOW=1 \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/integration/test_gui_parity_installed_workflow.py \
  -q -p no:cacheprovider --junit-xml=/tmp/slaif219/junit-installed-workflow-219b.xml
```

This additional full run is justified by demonstrated product fixes and missing
outcomes; it is not a repeat for presentation. Use focused debugging before it.
No skip/missing/error/pending outcome counts as success. Keep opt-in test-only,
no runtime config. API AND worker product origins must be the selected installed
wheel, outside source cwd/PYTHONPATH; all packaged templates/assets match source
and selected installed payload. Actual source commit/tree must exist BEFORE the
run. Later report/docs/fixture-only commits may be identified separately with
explicit byte-equality proof; do not invent a later implementation SHA as the
build source. Record wheel hash/version/import origins and honest test-environment
extras (including packaging installed for the broker) rather than claiming a
minimal wheel-only dependency closure that was not tested.

Root independently verified the219-a wheel503 packaged files equal final app
bytes (four missing source files are empty.gitkeep placeholders), and app bytes
at45893daa equalSELF. However00737d17 was created09:32:51Z, AFTER the final run
09:31:18–09:32:00Z; the report's build-source assertion is wrong. Its actual
source HEAD was45893daa. Correct this provenance in the NEW report, retaining
the immutable219-a report unchanged. Do not throw away valid wheel/component
proof or present it as full original-scope completion.

## Documentation, immutable report, final handoff

Rewrite the current PR title/body around the complete PRODUCT change and useful
operator behavior. It is not a test-only diff. Current guides/status must state
what is actually implemented/verified; remove unsupported220+ deferrals and false
completion claims, and keep operator-only exceptions honest. Complete ordinary
upgrade/restart/no-schema/no-key-migration instructions and the single current
GUI verification record; no duplicate per-template proof files. No release/
production/universal-compatibility/certification claim.

Routine fixture/doc/help corrections stay in THIS order and PR until the whole
scope is satisfied. Do not freeze partial implementation and hand it off merely
because some tests pass or context compacts. Report a concrete unresolved blocker
to root while continuing independent work; do not silently redefine acceptance.

Follow repository AGENTS/OAP protocol. Append/push implementation; never merge,
auto-merge, amend/force-push, or alter prior reports/orders. Prepare the report
away from its final path, publish once with same-directory temp, flush/fsync/
close/atomic rename/directory fsync. Include Documentation updated:/checked
impact, actual commands/exits/counts/source/wheel identities, exact scoped reused
evidence and corrected old provenance, ALL original outcomes and real limitations.
Report-only SELF must have literal implementation head as SOLE parent and only
the matching new report diff. Verify exact remote topology/bytes/head, then send
ONE exact two-byte response OK and rearm ONE canonical waiter to%9. Do not search
for FIFO readers, send duplicate OK, self-activate another number or mutate the
repository after handoff. Root requires all final-head CI/review/material/visual
gates, guarded merge, actual-main9checks/3workflows and FULL original-scope audit
before calling this goal complete.
