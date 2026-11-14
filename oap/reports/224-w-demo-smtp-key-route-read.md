# OAP 224-w — Final Report (read-only SMTP test, key JSON attachments, route configuration reads)

## Commit topology

- Activation commit: `bf9f1f6cdca9f09113df6848c15539ec398d7f4f`
  (tree `502fafa95d1e81574fc8497e50e71521ff2abf05`, sole parent
  `5e7df7ffcf510e5dffc99b09a448173f6e843884`) — committed the
  root-authored order and the exact `oap/active` = `224-w` pointer
  unchanged, FIRST.
- Immutable order: `oap/orders/224-w-demo-smtp-key-route-read.md`,
  SHA256
  `127bc99815267ea3e4c833c0e6ac1b69285bcf778d222ec051d9e4568fd56213`.
- Implementation head (sole SELF parent):
  `6b8bbbb85447d65d546b93f89b5b6651f8157ce8`
  ("224-w: repair 224-v unit failures and add read-only SMTP,
  key-attachment and route-configuration demo GETs"; 18 files,
  +3180/−82).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file. No merge; PR #383
  (`oap/224-demo-web`, base `main`) left open for strategic
  review.

## Prior objective state (224-v, terminal)

- v report-only SELF `5e7df7ffcf510e5dffc99b09a448173f6e843884`
  (sole parent `660f2ec85e581a92cf082f0f32570b6b9ed67286`, tree
  `e1f21c63cddd3d4ca567578dd11ceefcc530bd0c`, sole diff
  `oap/reports/224-v-demo-diagnostics-replay-read.md`); exact
  two-byte response `OK` delivered and CLOSED. The v response log
  was not repolled and v was not re-signaled.
- v exact SELF-head CI workflow run `43563620930` terminal
  FAILURE at `2026-11-14T06:11:14Z`: 9 of 10 checks SUCCESS
  (including hosted PostgreSQL and real Chromium); the single
  failing Unit/lint job `132352532339` reported 7,886 passed /
  3 failed / 1 skipped — exactly the three unit failures this
  order repairs (usability sortable-table inventory 58 → 62;
  missing linked help on the new demo lookup controls; duplicate
  source-level guidance IDs across mutually exclusive branches).
- CodeQL run `43563620919` SUCCESS (`05:54:13Z`); CodeQL - Code
  Quality run `435617556`→`43563617556` SUCCESS (`05:55:28Z`).

## Correction of the 224-v alias-withholding claim

The immutable 224-v report stated that output-side alias
withholding applied to the found/recent diagnostics projections.
That was OVERSTATED: the found detail's raw `gateway_key_id` /
`route_id` UUID strings were NOT withheld at 224-v time (the
withholding covered only the string fields). 224-w withholds
those UUIDs in the DEMO branch whenever the UUID string matches a
known incoming bearer/cookie/session/proxy alias, exactly like the
other displayed fields (no echo, no link). The v report was NOT
edited; this correction stands here, and the v docs section's
overstatement is explicitly noted in the new `docs/demo-admin.md`
224-w section.

## What 224-w changed (bounded, per order)

1. **224-v unit repairs**: sortable-table inventory 58 → 62;
   specific linked help (`aria-describedby`) for the new demo
   lookup input and namespace select; `cleanup-confirm-help`,
   `cleanup-reason-help`, `preview-expired-help` and
   `preview-reason-help` made unique in template source and
   correctly linked in both branches.
2. **224-v review findings**: the demo diagnostics page now shows
   ONLY the working GET lookup (the normal POST lookup was a
   silent no-op; the normal branch stays byte-identical; the
   cleanup action control stays visible as a labeled no-op); the
   demo not-found wording no longer suggests a live retention
   window and the replay preview help no longer implies ongoing
   traffic changes a frozen copy; found-detail UUID alias
   withholding (see correction above) with a narrow canary.
3. **Exact admission law** in `demo_admin_gate.py`: GET
   `/admin/email-operations/smtp-test`,
   `/admin/email-operations/smtp-test/apply` (query-free);
   `/admin/keys/{canonical-lowercase-UUID}/calibration/summary.json`
   (bounded positive query law: whole-raw-byte ceiling, strict
   single-pass percent-decode, closed `start_at`/`end_at`/
   `multiplier` name/value grammars, no unknown/duplicate/
   oversized values, enforced before any copy binding);
   `/admin/keys/{canonical-lowercase-UUID}/configuration.json`
   (query-free); `/admin/routes/{canonical-lowercase-UUID}/configuration`
   (query-free);
   `/admin/routes/{canonical-lowercase-UUID}/codex-profile/{base|profile|catalog}`
   (one finite artifact vocabulary, query-free). No alternate
   slash/subpath/broad prefix/arbitrary query admitted; every
   unsafe method stays the pre-body quiet 204 (except the
   CSRF-verified demo logout).
4. **New demo-only read-only adapters** (all: gate-bound
   request-local SELECT-only copy session; in-transaction
   `current_database()` / `transaction_read_only` recheck;
   bounded reads; fixed safe refusals; no source/ambient
   fallback): `demo_admin_smtp.py` (the 223 capture records NO
   SMTP facts, so both pages render the fixed "not recorded"
   state; the demo process's dummy SMTP settings are never used;
   visible review/send controls labeled quiet no-ops; apply-
   recovery is a fixed no-send notice),
   `demo_admin_key_attachments.py` (the SAME allowlisted strict
   version-1 configuration document and the SAME calibration
   service/strict parsers as the normal downloads, bound to the
   copy session and the demo app's fixed neutral settings;
   calibration is copied-data recalculation over frozen copied
   usage; whole-output refusal when any nested string matches a
   known incoming authentication alias or complete credential -
   no partial substitution, no echo; path-identity alias refusal
   before any copy binding; 1 MiB ceiling; private no-store/
   nosniff attachment headers),
   `demo_admin_route_configuration.py` (copied route + the four
   copy-backed choice families; optional operator completion
   choices ONLY from the 223-verified sanitized
   `profiles/completion-choices.json` leaf - metadata-first,
   bounded body re-asserted as bound parameters, exact length +
   SHA256, typed verifier; absent = unconfigured → package-
   defaults labeling; corrupt = fixed safe 503; no live
   `COMPLETION_SERVICE_PROFILE_DIR` or filesystem fallback),
   `demo_admin_codex_artifacts.py` (eligibility via the SAME pure
   copy-bound `CodexQualificationService.inspect()`; inert
   reference attachments rendered with the reserved non-routable
   `https://api.slaif.invalid/v1` placeholder and `.reference`
   filenames; catalog only where the profile has one; ineligible/
   unknown/unavailable = safe 404).
5. **Templates (demo branches only)**: `smtp_test.html` /
   `smtp_test_review.html` (not-recorded banners, labeled no-op
   button), `routes/configuration_form.html` (frozen/no-op cue,
   unconfigured/completed-leaf wording), `routes/detail.html`
   (truthful inert-artifact links for eligible routes),
   `keys/detail.html` (demo download label), `operations/
   diagnostics.html` and `replay_maintenance/scope.html` (item 2).
   Normal-admin output is byte-identical (render oracle below).
6. **Docs**: new `docs/demo-admin.md` section with the provenance
   and limits above, the explicit v overstatement correction, and
   the evidence boundary.

No schema/role/grant change; no source DB/file/settings/
provider/mail access; no runnable credential-bearing export; no
new PR, merge, release, deployment or company data.

## Evidence (all local/owned; hosted checks NOT observed yet)

* **Focused mocked units**: 29 new `test_w_` tests in
  `tests/unit/test_demo_web.py` (gate exact-path/near-miss/
  query-law/percent-decode/unsafe-204; SMTP not-recorded render,
  preflight-mismatch 503, no-demo-state 404; key attachment
  positive/missing/alias/oversized/preflight incl. the
  path-identity refusal with a never-called copy session; route
  configuration copy-backed positive, unconfigured labeling,
  corrupt-leaf 503, missing-route 404, selected-completion
  hydration; codex eligible-inert bytes, no-catalog 404,
  ineligible 404, render-failure 404) plus the four repaired
  regression expectations (closed-set, demo route detail, 224-q
  and 224-t exact-path tests) and the usability inventory
  58 → 62. The three affected unit files
  (`test_demo_web.py`, `test_admin_usability_inventory.py`,
  `test_admin_slaif_design.py`) ran green (`pytest -q` reached
  `[100%]` with no failure summary; `-q` omits the total count on
  success). Ruff clean on every changed `.py`.
* **Byte-identity oracle**: the modified templates render
  byte-identical under representative NORMAL contexts against the
  activation-commit originals (16/16 contexts, zero failures),
  and the demo branches render the expected content in a separate
  demo smoke render.
* **Documentation hygiene**: `scripts/check_documentation.py` →
  `DOCUMENTATION_CHECK=OK files=137`.
* **Owned PostgreSQL, two simultaneous copies** (owned PG16
  containers, disposable source + two disposable target copies;
  `pytest -q` → 2/2, EXIT=0): the new 224-w block proves the SMTP
  "not recorded" pages for both sessions with the fixed 404/204
  boundaries; the calibration summary over frozen copied usage
  for a TEST-ONLY trusted-calibration key row inserted into copy
  A only through the owned target-owner connection (honest
  label: transport proof, NOT 222 source capture or worker
  publication; exact-id cleanup before the invariance phase);
  the allowlisted configuration document with the copied policy
  fields and copied identity filename; the purpose-gate 400; the
  semantic-input 400 (gate-legal month-13 value refused by the
  normal strict parsers before any copy read); the gate query-
  law 404s; the path-identity and whole-output alias refusals
  with no echo; per-copy configuration isolation (copy B 404s
  copy A's inserted key and renders its own key from its own
  copy); the route-configuration copy-backed form over the REAL
  worker-built completion-choices leaf (the copied route's DB
  value linked to its copy's leaf, per-copy leaf reads, and the
  corrupt-leaf 503 with exact digest restore); and the codex
  artifact 404 boundary for the fixture's non-eligible route.
  The whole read/insert/corrupt/restore phase ends with the
  source and both copies byte-count-invariant (the test's own
  invariance phase).
* **Real Chromium** (same owned fixture): the SMTP form render
  and the REAL submit landing on the quiet 204 no-op (nothing
  sent), the apply-recovery no-send notice, a REAL
  authenticated-context download of the copied key's
  configuration document (attachment bytes, safety headers,
  copied identity filename), the standard-key calibration 400 in
  the browser, the route-detail page without any codex artifact
  link, the exact artifact-path 404, and the route-configuration
  render with the persistent no-op cue.

These are mocked, owned-PG and owned-browser checks on
disposable local databases; they are NOT a real company
installation and NOT a hosted-verification result.

## Limitations (honest)

* The codex eligible-path INERT BYTES are proven by the mocked
  unit suite only: the fixture route has no registered codex
  profile, so the owned PG/Chromium runs prove the 404 boundary
  and gate, not the eligible render.
* The key-attachment positives use a TEST-ONLY key row (copy A
  only); they prove route/handler/reader transport and the
  refusal laws over a worker-built copy, not 223 source-file
  capture (the configured-file installed proof remains
  objective 225).
* The SMTP pages prove the fixed "not recorded" state end to
  end; a configured-source SMTP capture path does not exist in
  the 223 capture scope, so no positive SMTP facts are claimed.
* Hosted CI for the w head is NOT reported here: at report time
  no w-head hosted run had completed, and the final-head gate
  reconciliation is owned by the strategic side after the
  response. The v-head hosted evidence above is the last
  observed terminal CI state (unit job failing exactly the three
  repaired tests).

## GitHub state (observed at report time)

* PR #383 uniquely OPEN / MERGEABLE, branch
  `oap/224-demo-web`, base `main`; remote `main`
  `d3762e51c9a323dee6b728c4a45fa21b0bffae86` (unchanged).
* Only release remains `v0.1.0-rc.1`; unrelated open PRs
  #379/#319 untouched; `protect main` ruleset active.
* No merge and no auto-merge by the coding agent.

## Protected untracked files (untouched, unread, unstaged)

* `CODEX-SESSIONS.md` SHA256
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
* `codex.sh` SHA256
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
* `uv.lock` SHA256
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`

## Objective status

Objective 224 remains INCOMPLETE (this order's scope is
complete as bounded); the strategic side independently reviews,
waits/rechecks final-head gates, and continues objective 224 on
the same PR. Objective 225 (installed acceptance) stays later.
