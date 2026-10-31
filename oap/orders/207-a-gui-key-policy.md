# OAP Work Order 207-a — GUI key policy, rate overrides and effective inspection

## Objective, human mandate and PR mode

Implement G01–G03 of `docs/MISSING_GUI_FUNCTIONALITY.md`: make key policy
administration faithful to the existing CLI/services, add existing-key rate
editing and effective-policy/route explanations. Correct the empty provider
selection that currently means unrestricted. Begin meaningful accessible help
on every touched key field. Preserve all working GUI flows and SLAIF styling.

Human approved the full GUI parity/guidance round on 2026-10-31 and explicitly
requires ergonomic, visually pleasing controls and explanatory hints on all
new AND existing fields. This order is the bounded first stage, not the entire
round. Strategic plan: `/home/janezp/codex-supervision/slaif-api-gateway/workorders/GUI-PARITY-ROUND-PLAN.md`.
Later stages deliver cloning, batches, route/provider controls, diagnostics,
Codex/replay, reports/paging, email, accounting, catalogs and admin accounts,
then the full-GUI hints/regression gate. Do not implement those in this PR.

PR mode: NEW_OBJECTIVE_NEW_PR. One numeric objective207, exactly ONE new PR
against `main`; branch `oap/207-gui-key-policy`, suggested title
`Complete GUI key policy and rate administration`. Strategic model alone
merges after review and all final-head checks; coding agent never merges or
enables auto-merge. Routine test/fixture/doc corrections belong in this order
and PR. No helpers/subagents or nested coding sessions. Use only the existing
right tmux pane %9; retain its current model/profile/effort settings.

## Verified current GitHub/OAP/shared-worktree state

Remote main = `67604ad6970ff8486e0a9905fdb87ffd37060bd2`, objective206 unique
PR362 MERGED 2026-10-30T02:27:06Z. Its final head is
`40a275c735de38b3961381833be5696a785920b7`, first parent IMPL
`cc9334b5ad3c180d61fb90e7ed25fa185a530685`; immutable report-only topology
previously accepted. All10 PR checks successful; actualmain workflows accepted
and rechecked successful. Shared active206-d is terminal, not pending.
Local coding HEAD is that report head; its tree equals mergedmain tree
`9860b5ea7e5ca7715bb6e6b5d2c1dee52543678c`. Reconcile fresh GitHub before Git
execution; root does not manipulate coding branches/index/state.

Only open PR319 is unrelated Dependabot; leave it alone. No207 PR exists.
Active main ruleset23580289 protects against deletion/non-fast-forward, no
bypass actors; no release newer than v0.1.0-rc.1. No release/deploy authority.

The previous task deliberately left these requested docs in the shared
worktree: new `docs/MISSING_GUI_FUNCTIONALITY.md` (sha256
`4ad805a8ae83c0998651a06254590a04fe97f189abec90dcf89e3661a746819e`), and
two-line navigation addition in `docs/README.md` (whole-file sha256
`aae53aa1ebdd91dad85cc79b36d576d8d76c3f3e59d5ca66c88ec5aa85bafedb`). They
ARE authorized task inputs; preserve and include them in this PR, updating
only delivered status and relevant documentation. They are not unrelated dirt
and do not require permission/stash/reset. Root's analysis remains dated
baseline evidence; add status instead of rewriting historical findings as if
they had always been fixed.

Protected untracked `CODEX-SESSIONS.md` sha256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda` and
`codex.sh` sha256
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
remain unrelated and MUST NOT change or be committed. Preserve ignored
credentials, catalogs, worktrees and all other unrelated state.

Fixed roots/FIFOs are verified at `/home/janezp/...` as named in the protocol.
Control/response true FIFO inodes4501469/4501470; sole coding waiter877851,
PPID1, `bash wait-control-and-wake.sh`, cwd strategicroot, TMUX_PANE=%9.
Root rechecks before one exact signal. Read this complete shared order and
exact `oap/active=207-a` after signal. Publish their unchanged bytes with IMPL.
Keep permanent objective-neutral `message.txt` unchanged.

## Required reading and verified implementation seams

Read repository AGENTS.md, coding OAP protocol and relevant live contracts;
`docs/MISSING_GUI_FUNCTIONALITY.md` sections2–5, docs/admin-usability.md,
docs/visual-design.md, docs/security-model.md relevant admin/policy boundary,
docs/database-schema.md key/policy/rate semantics, docs/cli-field-administration.md
and docs/cli-reference.md for the canonical operations.

Relevant existing implementation:
- `services/key_service.py`: update_gateway_key_configuration,
  project_key_configuration_update, render_key_configuration_document,
  update_gateway_key_rate_limits and existing create/update/audit/fence rules.
- `schemas/key_configuration.py`: schema_version1, strict presence-aware
  parser/export; MAX_KEY_CONFIGURATION_FILE_BYTES=65536. ABSENT != null != [];
  decimal parsing exact; duplicate/unknown fields denied with safe errors.
- `services/key_policy_configuration.py`: shared create/export/partial-update
  helpers and bound-module migration guard. Generic edits cannot repin/remove
  an already bound module or bypass profile restrictions.
- `services/key_policy_inspection.py`: build_key_policy_inspection,
  explain_model_route_access, safe fixed projections and configuration-only
  limitations. Never use inspection DTO construction as authentication.
- `api/admin.py`: existing session/CSRF contexts, request/service scopes,
  create_admin_key, update_admin_key_policy, _parse_admin_allowed_providers,
  safe read models, existing detail/create/error/result rendering.
- `web/templates/keys/create.html`, detail.html, _policy_selector.html,
  shared _record_choice.html; existing policy-selector.js and admin.css.

Root independently confirmed _parse_admin_allowed_providers returns None both
for allow-all and empty explicit selection; update policy always writes
providers. Existing-key rates have summaries but no update form/handler.
Policy editor currently covers only allow-lists; route readiness and lazy
throttling already work. Reuse, do not replace them unnecessarily.

## Allowed paths

- `app/slaif_gateway/api/admin.py`: relevant key handlers, rendering, helpers
  and shared Jinja registration only. A small focused `api/admin_key_policy.py`
  router is permitted if it reuses existing authentication/service scopes and
  is included via main.py without moving unrelated routes. Do not split the
  whole monolith or rewrite admin architecture.
- `app/slaif_gateway/main.py` only if needed to include that focused router.
- `app/slaif_gateway/web/templates/keys/*.html` for these surfaces; optional
  small shared field-help macro under web/templates, and shared base layout
  only for a necessary local link. Preserve all existing actions/fields.
- `app/slaif_gateway/web/static/js/policy-selector.js` (verify actual current
  filename); minimal existing admin.css additions for field help, grouped
  controls and non-overflow layout. No framework/dependency/assets redesign.
- A small GUI adapter under `services/admin_key_policy.py` or `web/` if needed
  for safe projections/presence mapping. Existing key services/schemas may be
  changed only for a demonstrated necessary shared seam extraction preserving
  CLI/runtime behavior; report exact reason and focused proof. No duplicate
  policy validator or direct metadata/SQL writes.
- Focused tests under existing unit/integration/browser directories, new
  `test_admin_key_policy_207.py` or coherent existing cases/fixtures. Minimal
  corrections to directly affected legacy display/control oracles allowed;
  do not weaken auth/privacy/state/selector/sort assertions.
- Docs: authorized analysis/index above; docs/admin-usability.md; new SINGLE
  incremental `docs/verification/gui-cli-parity.md` with index entry in
  docs/verification/README.md. Only relevant contract snippets if actual
  behavior documentation needs alignment. No duplicate inventory/evidence.
- Exact unchanged order, active pointer and new immutable matching report.

No dependencies/lock/workflows, models/migrations/schema, client/server modules,
provider transport, request admission/accounting/replay logic, catalog machinery,
CLI semantics, broad refactor or unrelated UI redesign. No production, real
provider calls or real SMTP; no source/secret dumps. If an actual contract
conflict blocks this bounded work, report it; do not improvise relaxed rules.

## Required behavior and acceptance

1. Provider policy fidelity on key creation AND existing-key edits. Explicitly
   labelled unrestricted, selected providers, deny-all states; null/list/[]
   round-trip, including disabled or older stored choices without erasing
   them. Empty selected mode may either deliberately map deny-all with clear
   wording or fail validation and ask for explicit deny-all; NEVER silently
   grant unrestricted. A legacy no-mode POST with allow-all unchecked and
   empty values must fail closed or represent deny-all. Absent controls in
   partial updates preserve values, not broaden authority. Preserve explicit
   selection, allow-all models/endpoints, catalog-only discovery semantics,
   unknown/invalid ID denial and trusted calibration boundaries. No-JS POSTs
   must faithfully express the same policy.

2. Strict full versioned key configuration accessible in GUI. Routine guided
   controls stay primary. Offer optional advanced JSON entry/upload and safe
   JSON download using the SAME version1 parser, bounds and canonical export
   as CLI (including exact Decimal handling, unknown/duplicate-field denial).
   Cover creation and partial updates of the supported policy/rate/lifetime/
   Responses/Codex/streaming/lazy/external-tool fields. Explicitly choose
   guided or document mode; reject ambiguous contradictory simultaneous
   sources, explain omission/null/empty semantics, preserve identities,
   owner/cohort, expiry and usage except expressly supported actions.
   Config contains configuration only, no arbitrary metadata or server ENV.
   Existing bound-module changes remain blocked and point to later reviewed
   compatibility migration, not this generic editor. Preserve historical
   unsupported-state refusal instead of silently erasing fields on export.
   Confirmation and bounded nonblank reason for mutations; actor from session.
   Show fixed safe validation errors without echoing raw JSON or submitted
   secret-shaped strings into flashes/logs. No plaintext/unsafe blob in URLs,
   localStorage or audit. Download only the service's allowlisted projection,
   attachment with private/no-store behavior, no secret material.

3. Existing-key rates editor. Reuse current canonical per-member patch and
   service operation for request count, token count, window seconds and
   concurrency. Distinguish leave unchanged / explicit value / clear to
   deployment for each; do not use truthiness for0. Follow current validators
   on allowed/nonzero bounds; invalid, conflicting and empty no-op updates
   fail predictably. Support one request per10seconds and concurrency1.
   Explain units and dependency on Redis, show current configured/effective
   values, and preserve lifetime quotas, lazy mode, validity, replay/module
   binding, material, usage and reservations. Editable tokens remain raw token
   counts; read-only counts use shared numeric/M-token format with exact help.

4. Effective inspection and explain model access. Display configured/effective/
   source for relevant key controls using shared safe inspection functions.
   Provider deny-all/list/unrestricted, inherited rates, lazy wait, lifetime
   unlimited/null, module/profile state and blockers are intelligible. Offer
   existing-record/finite-vocabulary endpoint/model choices, authenticated
   bounded read-only explain. Reuse exact shared explanation so policy,
   ranking/ambiguity and returned reasons cannot drift. State prominently
   configuration-only, not live authentication/admission or proof of pricing,
   quota/Redis/provider health; unavailable/unsupported states explicit.
   Preserve safe projection/no content or arbitrary metadata. Inspections
   never write, reset counters, contact upstreams or authenticate as the key.

5. Ergonomics and field guidance for touched key forms. Use existing SLAIF
   cards, typography, form-grid, native select/shared record-choice patterns;
   group routine/advanced actions, meaningful headings, clear primary action,
   optional advanced sections instead of a wall of JSON/control buttons.
   Preserve existing responsive layout and theme overlay. No separate awkward
   dropdown button/new picker library. Existing-record choices use existing
   latest100+oldersearch controls, not UUID-only free typing. Field-specific
   concise help visible beside/below each touched editable/choice field,
   aria-describedby, units/blank/default/inherit/deny meaning and example when
   useful. Password/secret fields not redisplayed; placeholder/hover alone is
   not help. Avoid repeated generic warnings. Keep old creation, calibration,
   pilot/Qwen presets, policy selector, quota/lazy/streaming/external-tool,
   lifecycle/rotation/email interactions; do not remove working fields.

6. Every new table follows existing sortable hyperlink/neutral-arrow, first
   ordinal, raw exact sort key, missing-last, independent request/token,
   readable numeric/M-unit and named-scroll-region law. Preserve no-JS
   usability, keyboard flow, filter chips/semantics and unchanged machine
   values. Do not alter shared table-sort.js for presentation convenience.

## Verification, negative evidence and regression economy

Use existing qualified env `/tmp/slaif192-coding-venv` if still valid and native
fixtures; inspect tool state first. Existing owned loopback/tmpfs PostgreSQL
fixture is authorized for synthetic TEST_DATABASE_URL evidence with exact-ID
cleanup. No ambient DATABASE_URL destructive setup, Docker prune, environment/
container credential dump, fixed-name takeover, apt installation, real mail,
real provider requests or HPC/full local matrix. Reuse existing browser setup,
not a new harness. Record actual commands/results and distinguish fakes from
real app+PostgreSQL+Chromium; skipped/missing/pending is not pass.

Focused proof must include:
- Real create and existing-key edit provider null/list/[] round-trips; empty
  selection never broadens, legacy no-mode/no-JS, older/disabled selections
  preserved. Export/import exact supported policy semantics, 9dp money,
  omission/null/zero, rates/Responses/streaming/lazy/external-tool fields;
  malformed/duplicate/unknown/oversize documents rejected safely.
- Existing bound module repin/removal denied through generic JSON; trusted
  calibration and unresolved/unsupported stored policy cannot bypass guards.
- Rate set/clear/inherit one member without changing siblings; exact
  one-per10s/concurrency1; no accidental resets of usage/reservations/limits,
  identities, expiry or secrets. Audit has actual session actor/reason.
- Configured/effective/source and explain output match shared CLI projections,
  discovery separate, disabled/ambiguous/unknown route states, unsafe values
  never projected, no writes/provider calls during inspection.
- Authentication, wrong/missing CSRF, forged actor, missing confirmation/reason,
  malformed identifiers, stale/not-found targets and secret-shaped canaries
  in rejected JSON/fields; no complete canary in response/log/audit/export.
  HTML escaping/XSS, no-store and unauthorized export denial.
- Actual Chromium workflow on real app/owned PostgreSQL using only synthetic
  data: key create/policy state edit/rate update/export and effective explain;
  reload verifies persisted values, legacy lifecycle/lazy controls still
  usable, keyboard labels/help, desktop+narrow layout without overlapping
  help/actions, no-JS server form fallback. Save a few focused screenshots
  under `/tmp/slaif207/` with no key/session/secret cells. Root reviews visual
  output. Use existing UI selectors where possible; do not blanket rerun all
  browser suites after unchanged edits.
- Directly affected existing key/admin-policy/picker/form/numeric tests plus
  focused new state tests; normal final-head GitHub CI is broad regression
  gate. Ruff touched Python, git diff --check, documentation checker and OAP
  governance. Update strict existing usability field inventory if legitimate
  new finite/record fields need classification; no blanket exemptions.

Do not write tests merely asserting new helper calls itself or source strings
instead of persisted behavior. Required PostgreSQL tests run, not skip. Keep
routine fixture/docs fixes in this order; strategic continuation only for a
real demonstrated blocker after report publication.

## Documentation, publication, report and handoff

Commit the prior human-requested analysis/index. Add delivered status for
G01–G03 without claiming G04–G18 complete. Document new GUI navigation, precise
provider tri-state, advanced format/sample/non-goals, rate units/inheritance,
configuration-only explanations, shared secret/privacy/auth rules and help
patterns in existing admin-usability doc. One incremental verification record
for this GUI round, no duplicate inventories. Record existing deployment
upgrade: normal rebuild/restart to pick up code/assets, no schema migration
or policy mass-update; historical deny-all stays deny-all. Do not deploy.

Create/push exactly one objective207 PR from fresh remote main, explicitly
stage only authorized paths including strategic order/active unchanged.
PR description leads with resulting key behavior, preserved legacy features,
shared backend, focused test/browser evidence and honest limitations.

Publish ONE immutable `oap/reports/207-a-gui-key-policy.md`: literal IMPL SHA,
`Report publication commit: SELF`. SELF first parent is IMPL; SELF changes
ONLY the new report; verify remote unique PR head equals SELF before signal.
Report exact changed paths, requirement proof, native/mocked/real distinctions,
privacy/authorization/accounting/replay invariants, no-schema/upgrade guidance,
visual screenshot paths, documentation-impact statement, tests/checks and
pending limitations. Agent never merges or self-activates another objective.
Send exactly2bytes OK to fixed response.fifo, start ONE detached verified
wait-control-and-wake.sh for %9 and stop. Root alone reviews report/tree/PR,
all final-head checks/reviews, visual/state/security evidence, then merges and
verifies actualmain before expanding208. No production/release authority.
